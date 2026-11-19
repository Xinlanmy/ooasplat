#!/usr/bin/env python3
"""preview_ply.py — 用 COLMAP 的真实相机位姿渲染 Brush 导出的 PLY。

为什么需要它
------------
OOOSplat 的预览器跑在应用内的 PlayCanvas 上，不开 GUI 就看不到结果。这个脚本
直接读取项目里的 COLMAP 稀疏模型，取出训练时真实的相机位姿，把高斯按针孔模型
投回二维，再和原始帧并排显示——用来判断重建是否对齐、颜色是否正确。

它不是完整的 splatting 实现，只为「验证」而写：
  * 只使用球谐的零阶项（DC），忽略视角相关的高阶颜色变化
  * 用加权顺序无关混合（weighted OIT）代替逐像素深度排序
  * 未实现 Mip-Splatting 的 3D 滤波与反锯齿
因此它渲染出的画面比真实预览器噪点更多，不要用它评判画质上限。

数学
----
投影     x = K · (R·X + t)，K 只含单一焦距 f 与主点 (cx, cy)（SIMPLE_RADIAL 模型）
二维协方差 Σ₂ᴅ = J · Σ₃ᴅ · Jᵀ，其中 J 为投影的雅可比，Σ₃ᴅ = R·S·Sᵀ·Rᵀ
半径取 Σ₂ᴅ 最大特征值的平方根乘以 2（即 2σ），按半径分桶后圆盘近似椭圆的投影

公式来源：Kerbl et al., "3D Gaussian Splatting for Real-Time Radiance Field
Rendering", ACM TOG 42(4), SIGGRAPH 2023. arXiv:2308.04079

依赖: numpy, Pillow
用法: python3 preview_ply.py <项目目录> [-n 4] [-o out.jpg]
"""

from __future__ import annotations

import argparse
import logging
import os
import struct

import numpy as np
from PIL import Image

log = logging.getLogger("preview")

# 球谐零阶基函数，用于把 DC 分量还原成 RGB
SH_C0 = 0.28209479177387814


# ---------------------------------------------------------------- PLY 解析
def read_ply(path: str) -> tuple[np.ndarray, list[str]]:
    """读取二进制小端 PLY，返回 (顶点表, 属性名列表)。"""
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            raise ValueError("不是 PLY 文件")
        fmt, count, props = None, 0, []
        while True:
            line = f.readline()
            if not line:
                raise ValueError("PLY 头未正常结束")
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == b"format":
                fmt = parts[1].decode()
            elif parts[0] == b"element" and parts[1] == b"vertex":
                count = int(parts[2])
            elif parts[0] == b"property":
                if parts[1] != b"float":
                    raise ValueError(f"暂不支持的属性类型: {parts[1]!r}")
                props.append(parts[2].decode())
            elif parts[0] == b"end_header":
                break
        if fmt != "binary_little_endian":
            raise ValueError(f"暂不支持的 PLY 格式: {fmt}")
        data = np.frombuffer(f.read(count * len(props) * 4), dtype="<f4")
    if data.size != count * len(props):
        raise ValueError("PLY 数据长度与头部声明不符（文件可能被截断）")
    return data.reshape(count, len(props)), props


def unpack(verts: np.ndarray, props: list[str]):
    """把顶点表拆成位置 / 尺度 / 不透明度 / 颜色 / 旋转四元数。"""
    col = {name: i for i, name in enumerate(props)}
    for need in ("x", "scale_0", "opacity", "rot_0", "f_dc_0"):
        if need not in col:
            raise ValueError(f"PLY 缺少必要属性: {need}")

    xyz = verts[:, [col["x"], col["y"], col["z"]]].astype(np.float64)
    scale = np.exp(verts[:, [col["scale_0"], col["scale_1"], col["scale_2"]]].astype(np.float64))
    alpha = 1.0 / (1.0 + np.exp(-verts[:, col["opacity"]].astype(np.float64)))
    dc = verts[:, [col["f_dc_0"], col["f_dc_1"], col["f_dc_2"]]].astype(np.float64)
    rgb = np.clip(0.5 + SH_C0 * dc, 0.0, 1.0)
    quat = verts[:, [col["rot_0"], col["rot_1"], col["rot_2"], col["rot_3"]]].astype(np.float64)
    quat /= np.linalg.norm(quat, axis=1, keepdims=True) + 1e-12
    return xyz, scale, alpha, rgb, quat


# ---------------------------------------------------------------- COLMAP 模型
# cameras.bin: uint64 数量，每条 {uint32 id, int32 model, uint64 w, uint64 h, double params[]}
# SIMPLE_RADIAL 的 params = (f, cx, cy, k)，共 4 个
_CAM_PARAM_COUNT = {0: 2, 1: 3, 2: 4, 3: 4}


def read_cameras(path: str) -> dict[int, dict]:
    cams: dict[int, dict] = {}
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            cid, model_id, w, h = struct.unpack("<IiQQ", f.read(24))
            k = _CAM_PARAM_COUNT.get(model_id, 4)
            params = struct.unpack("<" + "d" * k, f.read(8 * k))
            cams[cid] = {"model": model_id, "w": w, "h": h, "params": params}
    return cams


def read_images(path: str) -> list[dict]:
    out: list[dict] = []
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            iid, qw, qx, qy, qz, tx, ty, tz, cid = struct.unpack("<I4d3dI", f.read(64))
            name = b""
            while True:
                ch = f.read(1)
                if ch == b"\x00":
                    break
                name += ch
            (npts,) = struct.unpack("<Q", f.read(8))
            f.seek(24 * npts, 1)  # 跳过该图的 2D 观测
            out.append({
                "id": iid, "q": (qw, qx, qy, qz),
                "t": np.array([tx, ty, tz]), "cam": cid,
                "name": name.decode("utf-8", "replace"),
            })
    return out


def quat_to_rotm(q: tuple[float, float, float, float]) -> np.ndarray:
    """四元数 (w, x, y, z) → 旋转矩阵，约定与 COLMAP 一致。"""
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


# ---------------------------------------------------------------- 渲染
def render_view(xyz, scale, alpha, rgb, quat, R, t, f, cx, cy, W, H,
                max_radius: int = 5) -> np.ndarray:
    """把全部高斯投到指定相机上，返回 uint8 的 H×W×3 图像。"""
    # 世界 → 相机：X_cam = R·X_world + t
    cam = xyz @ R.T + t
    z = cam[:, 2]
    keep = z > 1e-6
    if not np.any(keep):
        return np.full((H, W, 3), 245, dtype=np.uint8)

    xyz_k, sc_k, al_k, rgb_k, q_k = xyz[keep], scale[keep], alpha[keep], rgb[keep], quat[keep]
    xc, yc, zc = cam[keep, 0], cam[keep, 1], z[keep]

    # 像素坐标
    px = f * xc / zc + cx
    py = f * yc / zc + cy

    # Σ₃ᴅ = M·Mᵀ, M = R_gauss · diag(scale)
    Rg = _batch_rotm(q_k)
    M = Rg * sc_k[:, None, :]
    sig3 = M @ np.transpose(M, (0, 2, 1))

    # 投影雅可比 J (2×3)：J = [[f/z, 0, -f·x/z²], [0, f/z, -f·y/z²]]
    J = np.zeros((len(zc), 2, 3))
    J[:, 0, 0] = f / zc
    J[:, 0, 2] = -f * xc / zc ** 2
    J[:, 1, 1] = f / zc
    J[:, 1, 2] = -f * yc / zc ** 2

    sig2 = J @ sig3 @ np.transpose(J, (0, 2, 1))
    a, b, d = sig2[:, 0, 0], sig2[:, 0, 1], sig2[:, 1, 1]
    lam = (a + d) / 2 + np.sqrt(np.maximum(((a - d) / 2) ** 2 + b * b, 0.0))
    radius = np.clip(np.sqrt(np.maximum(lam, 1e-9)) * 2.0, 0.8, max_radius)

    # 从远到近排序，保证近处覆盖远处
    order = np.argsort(-zc)
    px, py, radius = px[order], py[order], radius[order]
    col, alv = rgb_k[order], np.clip(al_k[order], 0.0, 1.0)

    wsum = np.zeros(H * W, dtype=np.float64)
    csum = np.zeros((H * W, 3), dtype=np.float64)

    for r_int in range(1, max_radius + 1):
        sel = (radius >= r_int - 0.5) & (radius < r_int + 0.5)
        if not sel.any():
            continue
        dy, dx = np.mgrid[-r_int:r_int + 1, -r_int:r_int + 1]
        kernel = np.exp(-0.5 * (dy ** 2 + dx ** 2) / max(r_int * 0.6, 0.7) ** 2)
        mask = kernel > 0.02
        oy, ox, kw = dy[mask], dx[mask], kernel[mask]
        span = oy.size

        cx_pix = np.rint(px[sel]).astype(np.int64)
        cy_pix = np.rint(py[sel]).astype(np.int64)
        a_sel, c_sel = alv[sel], col[sel]

        # 分块处理，避免 (N × span) 的索引矩阵过大
        for start in range(0, cx_pix.size, 15000):
            sl = slice(start, start + 15000)
            ii = cy_pix[sl, None] + oy[None, :]
            jj = cx_pix[sl, None] + ox[None, :]
            w = a_sel[sl, None] * kw[None, :]
            valid = (ii >= 0) & (ii < H) & (jj >= 0) & (jj < W)
            ii, jj, w = ii[valid], jj[valid], w[valid]
            cols = np.repeat(c_sel[sl], span, axis=0)[valid.ravel()]

            flat = ii * W + jj
            wsum += np.bincount(flat, weights=w, minlength=H * W)
            for ch in range(3):
                csum[:, ch] += np.bincount(flat, weights=w * cols[:, ch], minlength=H * W)

    img = np.zeros((H * W, 3))
    nz = wsum > 1e-6
    img[nz] = csum[nz] / wsum[nz, None]
    img = img.reshape(H, W, 3)
    coverage = np.clip(wsum.reshape(H, W, 1), 0.0, 1.0)
    img = img * coverage + 0.95 * (1.0 - coverage)  # 未覆盖处用浅灰，便于看出空洞
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def _batch_rotm(q: np.ndarray) -> np.ndarray:
    """向量化版四元数转旋转矩阵。"""
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    r = np.empty((q.shape[0], 3, 3))
    r[:, 0, 0] = 1 - 2 * (y * y + z * z)
    r[:, 0, 1] = 2 * (x * y - w * z)
    r[:, 0, 2] = 2 * (x * z + w * y)
    r[:, 1, 0] = 2 * (x * y + w * z)
    r[:, 1, 1] = 1 - 2 * (x * x + z * z)
    r[:, 1, 2] = 2 * (y * z - w * x)
    r[:, 2, 0] = 2 * (x * z - w * y)
    r[:, 2, 1] = 2 * (y * z + w * x)
    r[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return r


# ---------------------------------------------------------------- 主流程
def main() -> None:
    ap = argparse.ArgumentParser(description="按 COLMAP 真实位姿渲染 Brush 导出的 PLY")
    ap.add_argument("project", help="OOOSplat 项目目录（含 final.ply 与 work/）")
    ap.add_argument("-n", "--views", type=int, default=4, help="渲染几张对比图，默认 4")
    ap.add_argument("-o", "--out", default="preview_vs_original.jpg", help="输出文件名")
    ap.add_argument("--max-width", type=int, default=1600, help="输出图总宽度上限")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    ply_path = os.path.join(args.project, "final.ply")
    sparse = os.path.join(args.project, "work/colmap/authoritative")
    frames = os.path.join(args.project, "work/frames")
    for p in (ply_path, sparse, frames):
        if not os.path.exists(p):
            raise SystemExit(f"缺少路径: {p}")

    log.info("读取 PLY …")
    verts, props = read_ply(ply_path)
    xyz, scale, alpha, rgb, quat = unpack(verts, props)
    n_rest = sum(1 for p in props if p.startswith("f_rest_"))
    log.info("  高斯数量 %d，球谐总系数 %d/通道（%d 阶）",
             len(xyz), n_rest // 3 + 1, int(round(((n_rest // 3 + 1) ** 0.5) - 1)))

    cams = read_cameras(os.path.join(sparse, "cameras.bin"))
    images = read_images(os.path.join(sparse, "images.bin"))
    log.info("  已注册视角 %d，相机模型 %s", len(images), list(cams.values())[0]["model"])

    step = max(1, len(images) // args.views)
    picked = [images[i] for i in range(0, len(images), step)][: args.views]

    rows = []
    for im in picked:
        c = cams[im["cam"]]
        f, cxp, cyp = c["params"][:3]
        W, H = c["w"], c["h"]
        R = quat_to_rotm(im["q"])
        rendered = render_view(xyz, scale, alpha, rgb, quat, R, im["t"], f, cxp, cyp, W, H)

        src = os.path.join(frames, im["name"])
        if os.path.exists(src):
            orig = np.asarray(Image.open(src).convert("RGB").resize((W, H)))
            rows.append(np.concatenate([orig, rendered], axis=1))
        else:
            rows.append(rendered)
        log.info("  渲染 %s", im["name"])

    h = max(r.shape[0] for r in rows)
    rows = [np.pad(r, ((0, h - r.shape[0]), (0, 0), (0, 0)), constant_values=245) for r in rows]
    grid = np.concatenate(rows, axis=0)

    out_path = os.path.join(args.project, args.out)
    img = Image.fromarray(grid)
    if img.width > args.max_width:
        ratio = args.max_width / img.width
        img = img.resize((args.max_width, int(img.height * ratio)), Image.LANCZOS)
    img.save(out_path, quality=90, optimize=True)
    log.info("已写出 %s（左：原始帧，右：重建）", out_path)


if __name__ == "__main__":
    main()
