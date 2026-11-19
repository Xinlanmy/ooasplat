#!/bin/sh
# 根目录便利入口 —— 真正的实现只有一份，在 replication/tools/run-dev.sh
#
# 上游的 `npm run dev:local` 会在 prepareBrush() 处卡住：它比对的是 OOOBrush
# 归档中原始二进制的哈希，而实际安装的是从官方 dmg 出来、经重签名的运行时
# 版本，两者按设计永不相等。于是每次启动都判定「安装被篡改」，转而重新下载
# 114 MB。详见 replication/docs/04-踩坑记录.md 的坑 3。
#
# 用法: ./run-dev.sh

exec "$(dirname "$0")/replication/tools/run-dev.sh" "$@"
