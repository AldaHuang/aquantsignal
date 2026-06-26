#!/bin/bash
# 唤醒兜底：每小时检查一次，如果今天还没跑就补上
# 用 launchd 注册：~/Library/LaunchAgents/com.aquant.daily.plist

MARKER="$HOME/.aquant/last_run"
TODAY=$(date +%Y-%m-%d)
NOW_H=$(date +%H)

# 只在 15:30-23:59 之间运行
if [ "$NOW_H" -lt 15 ]; then
  exit 0
fi

# 今天已跑过则跳过
if [ -f "$MARKER" ]; then
  LAST=$(cat "$MARKER")
  if [ "$LAST" = "$TODAY" ]; then
    exit 0
  fi
fi

# 记录并运行
mkdir -p "$HOME/.aquant"
echo "$TODAY" > "$MARKER"
cd /Users/dh/AI/aquant
bash run_daily.sh >> logs/daily.log 2>&1
