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
echo "[1/4] Validating yesterday's picks..."
$PY -c "
from aquant.data.feed import DataFeed
from aquant.live.tracker import validate_yesterday
result = validate_yesterday(DataFeed())
if result:
    acc = result.get('direction_accuracy', 0) * 100
    gap = result.get('avg_gap', 0)
    print(f'  Direction accuracy: {acc:.0f}% ({result.get(\"validated\",0)} picks)')
    print(f'  Avg overnight gap: {gap:+.2f}%')
else:
    print('  No yesterday data to validate')
" 2>&1

# Step 2: Run recommendation
echo ""
echo "[2/5] Running daily recommendation..."
$PY -m aquant recommend --auto --top-n 20 --save --update-watchlist 2>&1 | grep -v "Insufficient cash" | tail -60

# Step 2.5: Add K-line data for charts
echo ""
echo "  Adding K-line data..."
$PY -c "
import json
from aquant.data.feed import DataFeed
feed = DataFeed()
with open('reports/tracker.json') as f: tracker = json.load(f)
latest = tracker['records'][-1] if tracker.get('records') else None
if latest:
    klines = {}
    for p in latest['picks']:
        try:
            df = feed.get(p['symbol'])
            if df is not None and len(df)>=10:
                recent = df.tail(30)
                klines[p['symbol']] = {
                    'dates': [str(d.date()) for d in recent.index],
                    'open': [round(float(x),2) for x in recent['open']],
                    'high': [round(float(x),2) for x in recent['high']],
                    'low': [round(float(x),2) for x in recent['low']],
                    'close': [round(float(x),2) for x in recent['close']],
                }
        except Exception: pass
    tracker['klines'] = klines
    with open('reports/tracker.json','w') as f: json.dump(tracker,f,indent=2,ensure_ascii=False)
    print(f'  K-line data: {len(klines)} stocks')
" 2>&1

# Step 3: Update paper trading
echo ""
echo "[3/5] Updating paper trading..."
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
    print(f'  总资产: ¥{summary[\"equity\"]:,.2f} ({summary[\"total_return_pct\"]:+.2f}%)')
    print(f'  持仓: {summary[\"positions\"]} 只 | 待成交: {summary[\"pending\"]} 只')
    print(f'  累计交易: {summary[\"total_trades\"]} 笔 | 累计盈亏: ¥{summary[\"total_pnl\"]:+,.2f}')
    for p in summary.get('positions_list', []):
        dist_to_stop = (p['current_price'] - p['stop_loss']) / p['current_price'] * 100 if p.get('stop_loss',0) > 0 else 0
        dist_to_tp = (p.get('take_profit', p['avg_cost']*1.1) - p['current_price']) / p['current_price'] * 100
        print(f'    {p[\"name\"]} {p[\"shares\"]}股 ¥{p[\"avg_cost\"]:.2f}→¥{p[\"current_price\"]:.2f} ({p[\"pnl_pct\"]:+.1f}%) 距止损{dist_to_stop:.0f}% 止盈剩{dist_to_tp:.0f}%')
" 2>&1

# Step 4: Update adaptive weights (runs AFTER recommend + paper, so weights persist)
echo ""
echo "[4/5] Learning from paper trades..."
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
    positions = paper.get('positions', {})
    pos_list = []
    total_mv = 0
    for s, p in positions.items():
        cp = p.get('current_price', p.get('avg_cost', 0))
        mv = p['shares'] * cp
        total_mv += mv
        pos_list.append({
            'symbol': s, 'name': p.get('name',s),
            'shares': p['shares'], 'avg_cost': round(p['avg_cost'],2),
            'current_price': round(cp,2), 'market_value': round(mv,2),
            'pnl_pct': round((cp-p['avg_cost'])/p['avg_cost']*100,2) if p['avg_cost']>0 else 0,
            'entry_date': p.get('entry_date','?'),
            'stop_loss': round(p.get('stop_loss',0),2),
        })
    pending_cash = sum(o.get('target_price',0)*o.get('shares',0) for o in paper.get('pending',{}).values())
    tracker['paper'] = {
        'equity': round(paper.get('cash',0) + total_mv, 2),
        'cash': round(paper.get('cash', 0), 2),
        'pending_cash': round(pending_cash, 2),
        'free_cash': round(paper.get('cash',0) - pending_cash, 2),
        'initial_cash': paper.get('initial_cash', 10000),
        'total_pnl': sum(t.get('pnl',0) for t in paper.get('history',[])),
        'total_trades': len(paper.get('history',[])),
        'positions': len(positions),
        'equity_log': paper.get('equity_log', [])[-30:],
        'history': paper.get('history', [])[-10:],
        'order_log': paper.get('order_log', [])[-20:],
        'positions_list': pos_list,
    }
    with open(tracker_path, 'w') as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)
    # Also sync CHANGELOG content
    import os
    clog_path = 'CHANGELOG.md'
    if os.path.exists(clog_path):
        with open(clog_path) as cf:
            clog = cf.read()
        tracker['changelog'] = clog[:15000]  # cap for mobile
    print('  Paper + changelog synced to tracker')
" 2>&1

# Step 6: Deploy to GitHub Pages
echo ""
echo "Deploying to GitHub Pages..."
bash deploy.sh 2>&1 | tail -3

echo ""
echo "$(date '+%H:%M:%S') Done."
