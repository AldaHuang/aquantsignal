"""CLI dispatcher: aquant data|backtest|scan|web"""

import sys
import argparse

from aquant import __version__


def cmd_data(args):
    """aquant data <subcommand>"""
    from aquant.data.feed import DataFeed
    feed = DataFeed()

    if args.data_action == "fetch":
        from aquant.data.symbols import normalize
        symbol = normalize(args.symbol)
        print(f"Downloading {symbol} ...")
        try:
            df = feed.get(symbol, start=args.start, end=args.end,
                          force_refresh=args.force)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        print(f"Downloaded {symbol}: {len(df)} rows ("
              f"{df.index[0].strftime('%Y-%m-%d')} to "
              f"{df.index[-1].strftime('%Y-%m-%d')})")

    elif args.data_action == "list":
        stats = feed.list_cache()
        if stats.empty:
            print("No cached data.")
            return
        print(stats.to_string(index=False))


def cmd_backtest(args):
    """aquant backtest <symbol> --strategy <name>"""
    from aquant.data.feed import DataFeed
    from aquant.data.symbols import normalize
    from aquant.backtest.engine import BacktestEngine
    from aquant.backtest.reporter import print_summary, print_trades

    symbol = normalize(args.symbol)
    print(f"Symbol: {symbol}")

    # Data
    if args.mock:
        import numpy as np, pandas as pd
        np.random.seed(hash(symbol) % 2**31)
        n = 500
        close = 10.0 * np.cumprod(1 + np.random.normal(0.0005, 0.015, n))
        dates = pd.date_range('2023-01-01', periods=n, freq='B')
        df = pd.DataFrame({
            'open': close * (1 + np.random.normal(0, 0.003, n)),
            'high': close * (1 + np.abs(np.random.normal(0, 0.008, n))),
            'low': close * (1 - np.abs(np.random.normal(0, 0.008, n))),
            'close': close,
            'volume': np.random.randint(1e6, 1e8, n).astype(float),
            'amount': np.random.randint(5e7, 5e9, n).astype(float),
        }, index=dates)
        for i in range(len(df)):
            o, h, l, c = df.iloc[i][['open','high','low','close']]
            df.iloc[i, df.columns.get_loc('high')] = max(o, c, h)
            df.iloc[i, df.columns.get_loc('low')] = min(o, c, l)
        print(f"Using mock data: {len(df)} bars")
    else:
        feed = DataFeed()
        start = args.start or "2020-01-01"
        print(f"Loading data from {start} ...")
        try:
            df = feed.get(symbol, start=start, end=args.end)
        except Exception as e:
            print(f"Error loading data for {symbol}: {e}")
            print("Tip: use --mock to test with synthetic data")
            sys.exit(1)

    if df is None or len(df) < 50:
        print(f"Not enough data for {symbol}: {len(df) if df is not None else 0} bars")
        sys.exit(1)

    # Strategy lookup
    strategy_cls = _resolve_strategy(args.strategy)
    params = _parse_params(args.param)

    # Engine
    engine = BacktestEngine(
        initial_cash=args.cash,
        fill_at=args.fill_at,
    )
    engine.add_data(df, symbol=symbol)
    engine.add_strategy(strategy_cls, **params)

    print(f"Running backtest: {args.strategy} ...")
    result = engine.run()

    # Output
    strategy_label = f"{args.strategy}({', '.join(f'{k}={v}' for k,v in params.items())})"
    print_summary(result, symbol=symbol, strategy_name=strategy_label)
    print_trades(result, top_n=args.trades)

    if args.plot:
        print("Displaying chart (close window to continue)...")
        result.plot()


def cmd_scan(args):
    """aquant scan --strategy <name> [--symbols <codes>]"""
    from aquant.live.scanner import SignalScanner, scan_watchlist
    from aquant.data.symbols import normalize

    strategy_cls = _resolve_strategy(args.strategy)
    params = _parse_params(args.param or [])
    watchlist = ([s.strip() for s in args.symbols.split(",")] if args.symbols
                 else "cached")

    print(f"Scanning with {args.strategy} ...")
    results = scan_watchlist(strategy_cls, watchlist, **params)

    if not results:
        print("No signals found.")
        return

    scanner = SignalScanner(strategy_cls)
    df = scanner.to_dataframe(results)
    # Colorize
    def _color(s):
        if s == "BUY": return "\033[1;31mBUY \033[0m"
        if s == "SELL": return "\033[1;32mSELL\033[0m"
        return s
    df["信号"] = df["信号"].apply(_color)
    print(df.to_string(index=False))
    buys = sum(1 for r in results if r.signal == "BUY")
    sells = sum(1 for r in results if r.signal == "SELL")
    print(f"\nTotal: {len(results)}, \033[1;31m{buys} BUY\033[0m, \033[1;32m{sells} SELL\033[0m")


def cmd_recommend(args):
    """aquant recommend [--auto] [--watchlist <file>] [--min-score <n>]"""
    from aquant.live.recommend import recommend, print_recommendations
    from aquant.data.feed import DataFeed
    import os, sys

    watchlist = None

    if args.auto:
        # Auto mode: enable save + update-watchlist by default
        if not args.no_save:
            args.save = True
        if not args.no_update:
            args.update_watchlist = True

        # Auto-discover + rank by strategy Sharpe
        from aquant.data.universe import build_universe
        max_price = args.max_price or 100
        top_n = args.top_n or 30
        no_star = args.no_star
        boards = "沪深主板+创业板" if no_star else "全市场"
        print(f"Universe: price < ¥{max_price}, top {top_n}, 板块: {boards}")
        print()
        selected = build_universe(max_price=max_price, top_n=top_n,
                                  exclude_star=no_star)
        if not selected:
            print("No stocks passed filters. Try --max-price 200 or --top-n 50")
            return

        watchlist = [code for code, _, _ in selected]

    elif args.watchlist:
        watchlist = args.watchlist
    elif args.symbols:
        watchlist = [s.strip() for s in args.symbols.split(",")]
    else:
        # Default: use watchlist.txt in project dir
        default_wl = os.path.join(os.path.dirname(__file__), "..", "watchlist.txt")
        if os.path.exists(default_wl):
            watchlist = default_wl
        else:
            watchlist = "cached"

    if watchlist is None:
        print("No stocks to analyze. Use --auto, --watchlist, or --symbols.")
        return

    label = (f"{len(watchlist)} stocks" if isinstance(watchlist, list)
             else str(watchlist))
    print(f"Analyzing {label} ...")
    recs = recommend(watchlist, min_score=args.min_score)
    print_recommendations(recs, top_n=args.top)

    # ── Save report ──
    if args.save:
        _save_report(recs, args)
        from aquant.live.tracker import record_recommendations
        record_recommendations(recs)
        # Sync changelog to tracker immediately
        _sync_changelog_to_tracker()
    if args.update_watchlist:
        _update_watchlist_file(recs, args)


def _save_report(recs, args):
    """Save recommendations to reports/YYYY-MM-DD.md and reports/latest.md."""
    import os
    from datetime import date

    report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(report_dir, exist_ok=True)

    today = date.today().isoformat()
    is_auto = getattr(args, 'auto', False)

    lines = [
        f"# aquant 每日推荐 — {today}",
        "",
        f"**模式**: {'自动选股（夏普排名）' if is_auto else '自选股'}",
        f"**策略**: 均线交叉 + 海龟突破 + 布林回归 联合评分",
        "",
        "## 推荐结果",
        "",
    ]

    # Buy recommendations
    buy_recs = [r for r in recs if r.verdict in ("买入", "关注")]
    if buy_recs:
        lines.append("### 🔴 买入 / 关注")
        lines.append("")
        lines.append("| 排名 | 代码 | 名称 | 现价 | 评分 | 理由 |")
        lines.append("|------|------|------|------|------|------|")
        for i, r in enumerate(buy_recs):
            lines.append(
                f"| {i+1} | {r.symbol} | {r.name} | "
                f"¥{r.price:.2f} | {r.score}/100 | "
                f"{'; '.join(r.reasons[:2])} |"
            )
        lines.append("")

    # Sell recommendations
    sell_recs = [r for r in recs if r.verdict == "卖出"]
    if sell_recs:
        lines.append("### 🟢 卖出信号")
        lines.append("")
        lines.append("| 排名 | 代码 | 名称 | 现价 | 评分 | 理由 |")
        lines.append("|------|------|------|------|------|------|")
        for i, r in enumerate(sell_recs):
            lines.append(
                f"| {i+1} | {r.symbol} | {r.name} | "
                f"¥{r.price:.2f} | {r.score}/100 | "
                f"{'; '.join(r.reasons[:2])} |"
            )
        lines.append("")

    # Hold
    hold_recs = [r for r in recs if r.verdict == "观望"]
    if hold_recs:
        lines.append("### ⚪ 观望")
        lines.append("")
        lines.append("| 代码 | 名称 | 现价 | 评分 |")
        lines.append("|------|------|------|------|")
        for r in hold_recs:
            lines.append(f"| {r.symbol} | {r.name} | ¥{r.price:.2f} | {r.score}/100 |")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*自动生成于 {today}，仅供参考，不构成投资建议*")

    content = "\n".join(lines)

    # Write dated report
    dated_path = os.path.join(report_dir, f"{today}.md")
    with open(dated_path, "w") as f:
        f.write(content)

    # Write latest symlink-equivalent
    latest_path = os.path.join(report_dir, "latest.md")
    with open(latest_path, "w") as f:
        f.write(content)

    print(f"\n📄 报告已保存: reports/{today}.md")
    print(f"📄 最新报告:   reports/latest.md")


def _sync_changelog_to_tracker():
    """Write changelog then sync it to tracker.json for phone display."""
    import os, json
    from aquant.live.changelog import write_changelog
    write_changelog()
    clog_path = os.path.join(os.path.dirname(__file__), "..", "CHANGELOG.md")
    tracker_path = os.path.join(os.path.dirname(__file__), "..", "reports", "tracker.json")
    if os.path.exists(clog_path) and os.path.exists(tracker_path):
        with open(clog_path) as cf: clog = cf.read()
        with open(tracker_path) as f: tracker = json.load(f)
        tracker["changelog"] = clog[:15000]
        with open(tracker_path, "w") as f:
            json.dump(tracker, f, indent=2, ensure_ascii=False)


def _update_watchlist_file(recs, args):
    """Update watchlist.txt with today's BUY recommendations."""
    import os

    wl_path = os.path.join(os.path.dirname(__file__), "..", "watchlist.txt")
    buy_recs = [r for r in recs if r.verdict in ("买入", "关注")]

    lines = [
        "# aquant 自选股 — 由推荐引擎自动更新",
        f"# 更新日期: {__import__('datetime').date.today().isoformat()}",
        "# 买入/关注推荐:",
    ]
    for r in buy_recs:
        lines.append(f"{r.symbol}  # {r.name} ¥{r.price:.2f} 评分{r.score}")

    with open(wl_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"📋 自选股已更新: watchlist.txt ({len(buy_recs)} 只)\n")


# ── strategy registry ─────────────────────────────────
_STRATEGY_REGISTRY = {}


def _init_registry():
    if _STRATEGY_REGISTRY:
        return
    from aquant.strategy.examples.ma_cross import MaCross
    from aquant.strategy.examples.turtle import Turtle
    from aquant.strategy.examples.mean_revert import MeanRevert
    _STRATEGY_REGISTRY["ma_cross"] = MaCross
    _STRATEGY_REGISTRY["macross"] = MaCross
    _STRATEGY_REGISTRY["turtle"] = Turtle
    _STRATEGY_REGISTRY["mean_revert"] = MeanRevert


def _resolve_strategy(name):
    _init_registry()
    key = name.lower().replace("-", "_")
    if key in _STRATEGY_REGISTRY:
        return _STRATEGY_REGISTRY[key]
    print(f"Unknown strategy: {name}")
    print(f"Available: {', '.join(sorted(_STRATEGY_REGISTRY.keys()))}")
    sys.exit(1)


def _parse_params(params_list):
    """Parse key=value pairs from CLI."""
    params = {}
    if params_list:
        for p in params_list:
            if "=" in p:
                k, raw = p.split("=", 1)
                k = k.strip()
                raw = raw.strip()
                # Try int first, then float, fallback to string
                try:
                    v = int(raw)
                except ValueError:
                    try:
                        v = float(raw)
                    except ValueError:
                        v = raw
                params[k] = v
    return params


# ── main ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="aquant",
        description="A-share quantitative trading system",
    )
    parser.add_argument("--version", action="version", version=f"aquant {__version__}")

    sub = parser.add_subparsers(dest="command")

    # data
    p_data = sub.add_parser("data", help="Data management")
    p_data_subs = p_data.add_subparsers(dest="data_action")

    p_fetch = p_data_subs.add_parser("fetch", help="Download and cache data")
    p_fetch.add_argument("symbol", help="Stock code (e.g., 000001)")
    p_fetch.add_argument("--start", default=None)
    p_fetch.add_argument("--end", default=None)
    p_fetch.add_argument("--force", action="store_true", help="Force re-download")

    p_list = p_data_subs.add_parser("list", help="List cached data")

    # backtest
    p_bt = sub.add_parser("backtest", help="Run a backtest")
    p_bt.add_argument("symbol", help="Stock code (e.g., 000001)")
    p_bt.add_argument("--strategy", "-s", required=True, help="Strategy name")
    p_bt.add_argument("--start", default=None)
    p_bt.add_argument("--end", default=None)
    p_bt.add_argument("--cash", type=float, default=None, help="Initial cash")
    p_bt.add_argument("--fill-at", default=None, choices=["next_open", "this_close"])
    p_bt.add_argument("--param", "-p", action="append",
                      help="Strategy params (key=value)")
    p_bt.add_argument("--trades", type=int, default=20, help="Show top N trades")
    p_bt.add_argument("--plot", action="store_true", help="Show chart")
    p_bt.add_argument("--mock", action="store_true", help="Use synthetic data for testing")

    # scan
    p_scan = sub.add_parser("scan", help="Scan stocks for buy/sell signals")
    p_scan.add_argument("--strategy", "-s", default="ma_cross")
    p_scan.add_argument("--symbols", default=None,
                        help="Comma-separated stock codes")
    p_scan.add_argument("--param", "-p", action="append",
                        help="Strategy params (key=value)")

    # web
    # recommend
    p_rec = sub.add_parser("recommend", help="Multi-strategy stock recommendations")
    p_rec.add_argument("--auto", action="store_true",
                       help="Auto-discover stocks from A-share market")
    p_rec.add_argument("--no-star", action="store_true", default=True,
                       help="Exclude STAR Market 科创板 (enabled by default)")
    p_rec.add_argument("--max-price", type=float, default=None,
                       help="Max stock price filter (default: 100)")
    p_rec.add_argument("--top-n", type=int, default=None,
                       help="Auto-universe size (default: 30)")
    p_rec.add_argument("--watchlist", "-w", default=None)
    p_rec.add_argument("--symbols", default=None,
                       help="Comma-separated stock codes")
    p_rec.add_argument("--min-score", type=int, default=0,
                       help="Minimum recommendation score (0-100)")
    p_rec.add_argument("--top", "-n", type=int, default=20,
                       help="Show top N recommendations")
    p_rec.add_argument("--save", action="store_true",
                       help="Save report to reports/YYYY-MM-DD.md")
    p_rec.add_argument("--update-watchlist", action="store_true",
                       help="Update watchlist.txt with BUY picks")
    p_rec.add_argument("--no-save", action="store_true",
                       help="Skip saving report (overrides --auto default)")
    p_rec.add_argument("--no-update", action="store_true",
                       help="Skip updating watchlist (overrides --auto default)")

    args = parser.parse_args()

    if args.command == "data":
        cmd_data(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "recommend":
        cmd_recommend(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
