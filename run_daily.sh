#!/bin/bash
# aquant 每日自动运行 — 由 cron 调用
set -e
cd "$(dirname "$0")"
DATE=$(date +%Y-%m-%d)
mkdir -p ~/.aquant logs reports

PY=~/python312/python-extracted/Python_Framework.pkg/Payload/Versions/3.12/bin/python3.12
$PY -m aquant.scripts.daily 2>&1
echo "$(date +%Y-%m-%d)" > ~/.aquant/last_run
