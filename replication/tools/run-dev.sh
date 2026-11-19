#!/bin/bash
# run-dev.sh — 以开发模式启动 OOOSplat（macOS arm64）
#
# 为什么不用 `npm run dev:local`：
#   dev:local 会调用 scripts/brush-runtime.mjs 里的 prepareBrush()，它把已安装的
#   Brush 二进制与 manifest 中记录的 binarySha256 比对。但那个值是 OOOBrush
#   归档中*原始*二进制的哈希，而实际安装的是从 dmg 出来、经重签名的*运行时*
#   版本，两者按设计永不相等。于是每次启动都判定「安装被篡改」，转而重新下载
#   114 MB；网络不稳时直接卡死。
#
#   本脚本跳过 prepareBrush，直接调用 Tauri CLI，并复用上游自己导出的本地配置
#   （scripts/local-tauri.mjs 的 localConfiguration），因此 --features local-colmap
#   与资源映射行为与官方 dev:local 完全一致。
#
# 用法: ./replication/tools/run-dev.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [ ! -d node_modules ]; then
  echo "错误: node_modules 不存在，请先运行 ./replication/tools/setup.sh" >&2
  exit 1
fi

# Rust 装在 ~/.cargo 时不会自动进 PATH
export PATH="$HOME/.cargo/bin:$PATH"

CONFIG=$(node -e "import('./scripts/local-tauri.mjs').then(m => console.log(JSON.stringify(m.localConfiguration('darwin'))))")

echo "启动 OOOSplat（开发模式）…"
exec node node_modules/@tauri-apps/cli/tauri.js dev \
  --features local-colmap \
  --config "$CONFIG"
