#!/bin/bash
# setup.sh — 准备运行时引擎并安装前端依赖（macOS arm64）
#
# 本仓库是 OOOSplat 的 fork，源码已在仓库里，不需要克隆。
# 这个脚本只解决两件事：装依赖、把四个引擎放到正确位置。
#
# 为什么不用 `npm run setup:engines`：
#   上游 macOS 的引擎清单从未锁定分发哈希（engines/manifest.macos.json 中
#   buildStatus 为 pending-first-build-and-hash-lock），脚本会主动拒绝安装。
#   这是设计行为，不是 bug。而官方发布包（dmg）里已完整打包
#   FFmpeg 8.1.2 / FFprobe 8.1.2 / COLMAP 4.2.1 / OOOBrush ooo-v1.0.0，
#   版本与应用一致，比自行编译更可靠。
#
#   引擎二进制受 LGPL / BSD 约束，不随仓库分发，只能从官方渠道获取。
#
# 用法: ./replication/tools/setup.sh

set -euo pipefail

UPSTREAM_TAG="0.8.1"
DMG_URL="https://github.com/ooolabdev/ooosplat/releases/download/${UPSTREAM_TAG}/OOOSplat-${UPSTREAM_TAG}-arm64-macos.dmg"
DMG_SHA256="b4159bb8abe22484ae1293747888ae8eb43e73018407db9bb66fb071f92c1037"
DMG_BYTES=225608021

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31m错误: %s\033[0m\n' "$*" >&2; exit 1; }

say "检查环境"
[ "$(uname -s)" = "Darwin" ] || die "本脚本仅支持 macOS；上游另有 Windows / Ubuntu 版本"
[ "$(uname -m)" = "arm64" ] || die "仅支持 Apple Silicon；上游未提供 Intel Mac 版本"
for bin in git node npm cargo; do
  command -v "$bin" >/dev/null 2>&1 || die "缺少 $bin（Rust 先安装：https://rustup.rs）"
done
xcode-select -p >/dev/null 2>&1 || die "缺少 Xcode Command Line Tools（xcode-select --install）"
echo "  node  $(node -v)"
echo "  cargo $(cargo --version | awk '{print $2}')"

say "安装前端依赖（约 470 MB）"
npm ci

ENGINE_DIR="$ROOT/engines/macos/arm64"
if [ -x "$ENGINE_DIR/bin/ffmpeg" ] && [ -x "$ENGINE_DIR/bin/brush_app" ] \
   && [ -x "$ENGINE_DIR/colmap/bin/colmap" ]; then
  say "引擎已就位，跳过下载"
else
  CACHE="$ROOT/.cache"
  mkdir -p "$CACHE"
  DMG="$CACHE/ooosplat-${UPSTREAM_TAG}-arm64.dmg"

  if [ ! -s "$DMG" ] || [ "$(stat -f%z "$DMG" 2>/dev/null || echo 0)" -lt "$DMG_BYTES" ]; then
    say "下载官方 dmg（约 215 MB，支持断点续传）"
    for attempt in $(seq 1 20); do
      size=$(stat -f%z "$DMG" 2>/dev/null || echo 0)
      [ "$size" -ge "$DMG_BYTES" ] && break
      echo "  第 $attempt 次，当前 $size / $DMG_BYTES 字节"
      curl -L --fail --connect-timeout 20 --max-time 900 -C - -o "$DMG" "$DMG_URL" || true
    done
  fi

  say "校验 SHA-256"
  actual=$(shasum -a 256 "$DMG" | awk '{print $1}')
  [ "$actual" = "$DMG_SHA256" ] || die "校验失败（实际 ${actual:0:16}…）。删除 $DMG 后重试"
  echo "  ok"

  say "挂载并提取引擎"
  MOUNT=$(hdiutil attach -nobrowse -readonly "$DMG" | awk -F'\t' '/\/Volumes\//{print $NF}' | tail -1)
  [ -d "$MOUNT" ] || die "挂载失败"
  SRC="$MOUNT/OOOSplat.app/Contents/Resources/engines/macos/arm64"
  [ -d "$SRC" ] || { hdiutil detach "$MOUNT" >/dev/null 2>&1 || true; die "dmg 内未找到引擎"; }

  mkdir -p "$ENGINE_DIR"
  ditto "$SRC" "$ENGINE_DIR"
  hdiutil detach "$MOUNT" >/dev/null 2>&1 || true
  xattr -dr com.apple.quarantine "$ENGINE_DIR" 2>/dev/null || true

  say "验证四个引擎"
  "$ENGINE_DIR/bin/ffmpeg"  -version | head -1
  "$ENGINE_DIR/bin/ffprobe" -version | head -1
  "$ENGINE_DIR/colmap/bin/colmap" -h 2>&1 | head -1
  "$ENGINE_DIR/bin/brush_app" --help 2>&1 | head -1
fi

say "完成"
cat <<EOF

下一步：

  启动桌面应用
    ./replication/tools/run-dev.sh

  命令行跑整条链路
    cargo build --release --manifest-path src-tauri/Cargo.toml --bin splatstudio
    ./src-tauri/target/release/splatstudio generate <视频路径> \\
      --quality balanced --projects-root "\$(cd .. && pwd)/splat-projects"

  注意：--projects-root 必须是绝对路径，相对路径报 INVALID_PATH。

EOF
