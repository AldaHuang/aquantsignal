"""Daily pipeline: single Python script, correct ordering, no race conditions.

Run: python3 -m aquant.scripts.daily
"""

import os, sys, json, logging
from datetime import date, datetime

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("daily")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


def step(msg):
    log.info("  %s", msg)


def main():
    today = date.today().isoformat()
    log.info("aquant daily: %s %s", today, datetime.now().strftime("%H:%M"))

    # ── 1. Validate yesterday ──
    from aquant.data.feed import DataFeed
    from aquant.live.tracker import validate_yesterday
    feed = DataFeed()
    result = validate_yesterday(feed)
    if result:
        step(f"昨日准确率: {result.get('direction_accuracy', 0)*100:.0f}%")

    # ── 2. Recommend ──
    step("推荐扫描...")
    from aquant.cli import main as cli_main
    import argparse
    # Build args for recommend --auto
    sys.argv = ["aquant", "recommend", "--auto", "--top-n", "20", "--save", "--update-watchlist"]
    try:
        from aquant.cli import cmd_recommend
        ns = argparse.Namespace(
            command="recommend", auto=True, top_n=20, max_price=100,
            no_star=True, no_save=False, no_update=False, save=True,
            update_watchlist=True, watchlist=None, symbols=None, min_score=0, top=20,
        )
        cmd_recommend(ns)
    except SystemExit:
        pass

    # ── 3. Paper trading ──
    step("模拟盘更新...")
    from aquant.live.paper import PaperTrader
    from aquant.live.tracker import load_history
    data = load_history()
    records = data.get("records", [])
    if records:
        latest = records[-1]
        class R:
            def __init__(s, p):
                s.symbol = p["symbol"]; s.name = p.get("name", "")
                s.price = p.get("price", 0); s.verdict = p.get("verdict", "")
                s.stop_loss = p.get("stop_loss", 0); s.score = p.get("score", 0)
        recs = [R(p) for p in latest.get("picks", [])]
        trader = PaperTrader()
        summary = trader.update(recs, feed)
        step(f"资产 ¥{summary['equity']:,.0f} | 持仓 {summary['positions']} | 交易 {summary['total_trades']}")

    # ── 3.5. Benchmark vs CSI 300 ──
    try:
        idx_df = feed.get_index("000300", start="2026-06-25")
        if idx_df is not None and len(idx_df) > 0:
            bench_start = float(idx_df["close"].iloc[0])
            bench_now = float(idx_df["close"].iloc[-1])
            bench_return = (bench_now - bench_start) / bench_start * 100
            step(f"沪深300: {bench_start:.0f}→{bench_now:.0f} ({bench_return:+.1f}%)")
            # Store for phone display
            data = load_history()
            data["benchmark"] = {
                "name": "沪深300",
                "start": round(bench_start, 2),
                "current": round(bench_now, 2),
                "return_pct": round(bench_return, 2),
            }
            save_history(data)
    except Exception:
        pass

    # ── 4. Sync ALL data to tracker ──
    step("同步数据...")
    _full_sync(today)

    # ── 5. Learning ──
    from aquant.live.tracker import update_strategy_weights, get_learning_status
    weights = update_strategy_weights()
    step(f"权重: {', '.join(f'{k}={v:.2f}' for k,v in sorted(weights.items()))}")

    # ── 6. Changelog ──
    from aquant.live.changelog import write_changelog
    write_changelog()

    # ── 6.5. Regenerate index.html with version key ──
    step("刷新版本号...")
    _stamp_index(today)

    # ── 7. Git push ──
    step("推送 GitHub...")
    os.system("git add index.html reports/tracker.json reports/paper.json CHANGELOG.md watchlist.txt go.html")
    os.system(f"git commit -m '{today} 每日推荐更新' 2>/dev/null || true")
    os.system("git push origin main 2>&1 | tail -1")

    log.info("Done: %s", datetime.now().strftime("%H:%M"))


def _full_sync(today):
    """Sync paper + klines + changelog to tracker.json in one atomic write."""
    tracker_path = "reports/tracker.json"
    if not os.path.exists(tracker_path):
        return
    with open(tracker_path) as f:
        tracker = json.load(f)

    tracker["_version"] = f"{today} {datetime.now().strftime('%H:%M:%S')}"

    # Paper data
    paper_path = "reports/paper.json"
    if os.path.exists(paper_path):
        with open(paper_path) as pf:
            paper = json.load(pf)
        pos_list = []; total_mv = 0
        for s, p in paper.get("positions", {}).items():
            cp = p.get("current_price", p.get("avg_cost", 0))
            mv = p["shares"] * cp; total_mv += mv
            pos_list.append({
                "symbol": s, "name": p.get("name", s), "shares": p["shares"],
                "avg_cost": round(p["avg_cost"], 2), "current_price": round(cp, 2),
                "market_value": round(mv, 2),
                "pnl_pct": round((cp - p["avg_cost"]) / p["avg_cost"] * 100, 2) if p["avg_cost"] > 0 else 0,
                "entry_date": p.get("entry_date", "?"),
                "stop_loss": round(p.get("stop_loss", 0), 2), "days_held": p.get("days_held", 0),
            })
        pdc = sum(o.get("target_price", 0) * o.get("shares", 0) for o in paper.get("pending", {}).values())
        tracker["paper"] = {
            "equity": round(paper.get("cash", 0) + total_mv, 2),
            "cash": round(paper.get("cash", 0), 2),
            "pending_cash": round(pdc, 2),
            "free_cash": round(paper.get("cash", 0) - pdc, 2),
            "initial_cash": paper.get("initial_cash", 10000),
            "total_pnl": sum(t.get("pnl", 0) for t in paper.get("history", [])),
            "total_trades": len(paper.get("history", [])),
            "positions": len(paper["positions"]),
            "history": paper.get("history", [])[-10:],
            "order_log": paper.get("order_log", [])[-20:],
            "positions_list": pos_list,
        }

    # Changelog
    if os.path.exists("CHANGELOG.md"):
        with open("CHANGELOG.md") as cf:
            tracker["changelog"] = cf.read()[:15000]

    # K-lines (already synced in recommend step, keep existing if present)
    if "klines" not in tracker:
        tracker["klines"] = {}

    with open(tracker_path, "w") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)


def _stamp_index(today):
    """Update index.html version key + regenerate now.html with fresh data."""
    import re
    idx_path = os.path.join(ROOT, "index.html")
    now_path = os.path.join(ROOT, "now.html")
    tracker_path = os.path.join(ROOT, "reports", "tracker.json")
    if not os.path.exists(tracker_path):
        return

    with open(tracker_path) as f:
        data = json.load(f)
    version = data.get("_version", today).replace(" ", "_").replace(":", "-")

    # Update index.html fetch URL
    if os.path.exists(idx_path):
        with open(idx_path) as f:
            html = f.read()
        html = re.sub(
            r"fetch\('reports/tracker\.json\?v=[^']*&t=",
            f"fetch('reports/tracker.json?v={version}&t=",
            html
        )
        with open(idx_path, "w") as f:
            f.write(html)

    # Regenerate now.html with embedded data
    if os.path.exists(now_path):
        with open(now_path) as f:
            html = f.read()
        # Replace the inline data blob
        html = re.sub(
            r'var D=\{.*?\};',
            f'var D={json.dumps(data, ensure_ascii=False)};',
            html, count=1, flags=re.DOTALL
        )
        # Update timestamp display
        html = html.replace(
            "document.getElementById('ts').textContent=(D._version||'').slice(0,16)",
            f"document.getElementById('ts').textContent='{version[:16]}'"
        )
        with open(now_path, "w") as f:
            f.write(html)


if __name__ == "__main__":
    main()
