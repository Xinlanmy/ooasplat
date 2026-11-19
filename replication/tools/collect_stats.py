#!/usr/bin/env python3
"""collect_stats.py — 从 OOOSplat 项目目录汇总指标，输出 CSV。

读取每个项目中的四类信息：
  project.json          档位、状态、总耗时
  logs/activity-*.log   SplatBudget 行（注册数、平均轨迹长度、有效像素、splat 上限）
                        以及「预计提取 N 帧」告警行（首次抽帧的计划帧数）
  work/frames/          实际落盘的帧数（含 Bridge 补帧，可能大于计划帧数）
  final.ply             最终高斯数量与文件大小

注意两个口径差异：
  注册率 = 注册数 / **计划抽帧数**（不是落盘帧数）。Bridge 补帧会让落盘帧数
  大于计划帧数，用落盘数做分母会低估注册率。
  落盘帧数 - 计划帧数 = Bridge 补进来的帧数。

用法:
  python3 collect_stats.py <projects_root> [-o runs.csv] [--all]
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys

_PLAN_RE = re.compile(r"预计提取\s+(\d+)\s+帧")
_NAME_RE = re.compile(r"^\d{8}-\d{6}_(.+)$")


def ply_vertex_count(path: str) -> int:
    """只读 PLY 头部，取出 element vertex 的数量。"""
    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("latin-1").strip()
            if line.startswith("element vertex"):
                return int(line.split()[-1])
            if line == "end_header":
                break
    return 0


def scan_logs(project_dir: str) -> tuple[dict, int]:
    """返回 (SplatBudget 字段, 计划抽帧数)。"""
    budget: dict = {}
    planned = 0
    for log_path in sorted(glob.glob(os.path.join(project_dir, "logs", "activity-*.log"))):
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not planned:
                    m = _PLAN_RE.search(line)
                    if m:
                        planned = int(m.group(1))
                if "SplatBudget" not in line:
                    continue
                start = line.find('{"operation"')
                if start < 0:
                    continue
                try:
                    msg = json.loads(line[start:]).get("message", "")
                except json.JSONDecodeError:
                    continue
                body = msg.split("]", 1)[-1].strip()
                for pair in body.split():
                    if "=" not in pair:
                        continue
                    key, value = pair.split("=", 1)
                    try:
                        budget[key] = float(value) if "." in value else int(value)
                    except ValueError:
                        budget[key] = value
    return budget, planned


def collect(project_dir: str) -> dict | None:
    meta_path = os.path.join(project_dir, "project.json")
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    budget, planned = scan_logs(project_dir)

    frames_dir = os.path.join(project_dir, "work", "frames")
    on_disk = len(glob.glob(os.path.join(frames_dir, "*"))) if os.path.isdir(frames_dir) else 0
    planned = planned or on_disk

    ply = os.path.join(project_dir, "final.ply")
    splats = ply_vertex_count(ply) if os.path.exists(ply) else 0
    ply_bytes = os.path.getsize(ply) if os.path.exists(ply) else 0

    registered = int(budget.get("registeredImages", 0) or 0)
    name = meta.get("name", "")
    m = _NAME_RE.match(name)

    return {
        "project": os.path.basename(project_dir),
        "created": meta.get("createdAt", "")[:19].replace("T", " "),
        "quality": meta.get("quality", ""),
        "status": meta.get("status", ""),
        "source": m.group(1) if m else name,
        "frames_planned": planned,
        "frames_on_disk": on_disk,
        "bridge_added": max(on_disk - planned, 0),
        "registered": registered,
        "reg_rate": round(registered / planned, 4) if planned else "",
        "mean_track": budget.get("meanTrackLength", ""),
        "eff_pixels": budget.get("effectivePixels", ""),
        "max_splats": budget.get("maxSplats", ""),
        "splats": splats,
        "ply_mb": round(ply_bytes / 1048576, 1) if ply_bytes else "",
        "minutes": round(meta.get("durationMs", 0) / 60000, 1) if meta.get("durationMs") else "",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="汇总 OOOSplat 项目指标为 CSV")
    ap.add_argument("root", help="存放各项目目录的根路径")
    ap.add_argument("-o", "--out", default="runs.csv", help="输出 CSV 路径")
    ap.add_argument("--all", action="store_true", help="包含中断/失败的项目（默认只统计已完成）")
    args = ap.parse_args()

    rows = []
    for entry in sorted(os.listdir(args.root)):
        path = os.path.join(args.root, entry)
        if not os.path.isdir(path):
            continue
        row = collect(path)
        if not row:
            continue
        if not args.all and row["status"] != "completed":
            continue
        rows.append(row)

    if not rows:
        print("没有可统计的项目（试试加 --all）", file=sys.stderr)
        sys.exit(1)

    rows.sort(key=lambda r: r["created"])
    fields = list(rows[0].keys())
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"已写出 {args.out}（{len(rows)} 行）")
    for r in rows:
        print(f"  {r['created']}  {r['quality']:8s}  {r['splats']:>7,} splats  "
              f"{r['minutes']:>6} min  {r['source']}")


if __name__ == "__main__":
    main()
