"""Text report and console output for backtest results."""

from aquant.utils import format_cny, format_pct


def print_summary(result, symbol="", strategy_name=""):
    """Print a formatted text summary to stdout."""
    m = result.metrics
    df = result.df
    start = df.index[0].strftime("%Y-%m-%d")
    end = df.index[-1].strftime("%Y-%m-%d")

    print()
    if strategy_name:
        print(f"  Strategy:  {strategy_name}")
    if symbol:
        print(f"  Symbol:    {symbol}")
    print(f"  Period:    {start} ~ {end} ({len(df)} trading days)")
    print(f"  " + "-" * 50)
    print(f"  Initial:   {format_cny(m['initial'])}")
    print(f"  Final:     {format_cny(m['final'])}")
    print(f"  Return:    {format_pct(m['total_return'])}")
    print(f"  Annual:    {format_pct(m['annual_return'])}")
    print(f"  Sharpe:    {m['sharpe_ratio']:.2f}")
    print(f"  Max DD:    {m['max_drawdown']*100:.2f}% ({m['max_drawdown_duration']} days)")
    print(f"  Volatility:{m['volatility']*100:.2f}%")
    print(f"  Calmar:    {m['calmar_ratio']:.2f}")
    print(f"  Win Rate:  {m['win_rate']*100:.1f}%")
    print(f"  Profit Factor: {m['profit_factor']:.2f}")
    print(f"  Trades:    {m['num_trades']}")
    print(f"  " + "-" * 50)
    print()


def print_trades(result, top_n=20):
    """Print recent trades."""
    trades = result.trades
    if not trades:
        print("  No trades recorded.")
        return

    print(f"  Trade Log ({min(len(trades), top_n)} of {len(trades)}):")
    print(f"  {'Date':<12} {'Side':<6} {'Size':>8} {'Price':>10} {'Value':>12} {'P&L':>10}")
    print(f"  " + "-" * 58)

    for t in trades[:top_n]:
        pnl_str = format_cny(t.net_pnl) if t.net_pnl is not None else "—"
        print(f"  {str(t.date)[:10]:<12} {t.side.upper():<6} {t.size:>8} "
              f"{t.price:>10.2f} {format_cny(t.value):>12} {pnl_str:>10}")

    if len(trades) > top_n:
        print(f"  ... and {len(trades) - top_n} more trades")
    print()
