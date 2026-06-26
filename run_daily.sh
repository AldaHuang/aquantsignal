#!/bin/bash
# aquant 每日自动运行脚本
# 建议在市场收盘后运行（15:30 以后）
# 用 cron 定时: crontab -e 添加
#   30 15 * * 1-5 cd /Users/dh/AI/aquant && ./run_daily.sh >> logs/daily.log 2>&1

set -e

cd "$(dirname "$0")"
PY=~/python312/python-extracted/Python_Framework.pkg/Payload/Versions/3.12/bin/python3.12
DATE=$(date +%Y-%m-%d)

# Mark today's run to prevent duplicate from wakeup_check
mkdir -p ~/.aquant
echo "$DATE" > ~/.aquant/last_run
mkdir -p logs

echo "=============================================="
echo "aquant daily run: $DATE"
echo "$(date '+%H:%M:%S') Starting..."
echo "=============================================="

# Step 1: Validate yesterday's recommendations
echo ""
echo "[1/5] Validating yesterday's picks..."
$PY -c "
from aquant.data.feed import DataFeed
from aquant.live.tracker import validate_yesterday
result = validate_yesterday(DataFeed())
if result:
    print(f'  Yesterday buy win rate: {result[\"buy_win_rate\"]*100:.0f}%')
    print(f'  Buy hits: {result[\"buy_hits\"]}, misses: {result[\"buy_misses\"]}')
else:
    print('  No yesterday data to validate')
" 2>&1

# Step 2: Update adaptive weights
echo ""
echo "[2/5] Learning from paper trades..."
$PY -c "
from aquant.live.tracker import update_strategy_weights, get_learning_status
weights = update_strategy_weights()
learn = get_learning_status()
pnl = learn.get('pnl', {})
print('  Strategy weights (P&L-driven):')
for s, w in sorted(weights.items()):
    p = pnl.get(s, 0)
    tag = '📈' if p > 5 else '📉' if p < -5 else '➖'
    print(f'  {tag} {s}: {w:.2f}  (累计盈亏: ¥{p:+.0f})')
" 2>&1

# Step 3: Run recommendation
echo ""
echo "[3/3] Running daily recommendation..."
$PY -m aquant recommend --auto --top-n 20 --save --update-watchlist 2>&1 | grep -v "Insufficient cash" | tail -60

# Step 4: Update paper trading
echo ""
echo "[4/5] Updating paper trading..."
$PY -c "
from aquant.data.feed import DataFeed
from aquant.live.paper import PaperTrader
from aquant.live.tracker import load_history

# Load today's recommendations
data = load_history()
records = data.get('records', [])
if records:
    latest = records[-1]
    picks = latest.get('picks', [])
    # Convert to simple objects for the paper trader
    class Rec:
        def __init__(self, d):
            self.symbol = d['symbol']
            self.name = d.get('name', '')
            self.price = d.get('price', 0)
            self.verdict = d.get('verdict', '')
            self.score = d.get('score', 0)
            self.stop_loss = d.get('stop_loss', 0)
            self.entry = d.get('entry', 0)
    recs = [Rec(p) for p in picks]

    trader = PaperTrader()
    feed = DataFeed()
    summary = trader.update(recs, feed)
    print(f'  总资产: ¥{summary[\"equity\"]:,.2f}')
    print(f'  收益率: {summary[\"total_return_pct\"]:+.2f}%')
    print(f'  持仓: {summary[\"positions\"]} 只 | 待成交: {summary[\"pending\"]} 只')
    print(f'  累计交易: {summary[\"total_trades\"]} 笔 | 胜率: {summary[\"win_rate\"]}%')
    print(f'  累计盈亏: ¥{summary[\"total_pnl\"]:+,.2f}')
" 2>&1

# Step 5: Append to changelog
echo ""
echo "Writing changelog..."
$PY -c "
from aquant.live.changelog import write_changelog
write_changelog()
# Also copy paper summary to tracker for phone display
import json, os
paper_path = 'reports/paper.json'
tracker_path = 'reports/tracker.json'
if os.path.exists(paper_path):
    with open(paper_path) as f:
        paper = json.load(f)
    with open(tracker_path) as f:
        tracker = json.load(f)
    tracker['paper'] = {
        'equity': paper.get('equity', 0),
        'cash': paper.get('cash', 0),
        'initial_cash': paper.get('initial_cash', 10000),
        'total_pnl': sum(t.get('pnl',0) for t in paper.get('history',[])),
        'total_trades': len(paper.get('history',[])),
        'positions': len(paper.get('positions',{})),
        'equity_log': paper.get('equity_log', [])[-30:],
        'history': paper.get('history', [])[-10:],
    }
    with open(tracker_path, 'w') as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)
    print('  Paper trading synced to tracker')
print('  CHANGELOG.md updated')
" 2>&1

# Step 6: Deploy to GitHub Pages
echo ""
echo "Deploying to GitHub Pages..."
bash deploy.sh 2>&1 | tail -3

echo ""
echo "$(date '+%H:%M:%S') Done."
