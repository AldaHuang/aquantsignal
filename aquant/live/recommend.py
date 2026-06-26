"""Recommendation engine: multi-strategy consensus scoring.

Runs all strategies across the watchlist, combines signals into
a recommendation score (0-100), and ranks stocks with reasoning.
"""

import logging
import pandas as pd
from aquant.live.scanner import SignalScanner, scan_watchlist
from aquant.strategy.examples.ma_cross import MaCross
from aquant.strategy.examples.turtle import Turtle
from aquant.strategy.examples.mean_revert import MeanRevert
from aquant.data.feed import DataFeed

log = logging.getLogger(__name__)

# Strategy lineup — weights are overridden by adaptive tracker if available
_BASE_STRATEGIES = [
    (MaCross, "均线交叉", 1.0),
    (Turtle, "海龟突破", 0.8),
    (MeanRevert, "布林回归", 1.0),
]


def _get_strategies():
    """Return strategy list with adaptive weights from tracker."""
    try:
        from aquant.live.tracker import get_adaptive_weights
        weights = get_adaptive_weights()
    except Exception:
        weights = {}

    result = []
    for cls, name, default_w in _BASE_STRATEGIES:
        w = weights.get(name, default_w)
        result.append((cls, name, w))
    return result


class Recommendation:
    """One stock's recommendation with trade plan."""

    def __init__(self, symbol, name, price):
        self.symbol = symbol
        self.name = name
        self.price = price
        self.score = 0          # 0-100
        self.signals = {}       # strategy_name -> signal string
        self.reasons = []       # list of reason strings
        self.verdict = "观望"    # one-line conclusion
        # Trade plan fields
        self.entry = 0.0        # suggested buy price
        self.stop_loss = 0.0    # stop loss price
        self.take_profit = 0.0  # take profit target
        self.atr = 0.0          # Average True Range (14-day)
        self.position_pct = 0   # suggested position % of capital
        self.risk_pct = 0.0     # risk % of capital if stop hit

    def __repr__(self):
        return f"Rec({self.symbol} {self.name} score={self.score} {self.verdict})"


def recommend(watchlist="cached", min_score=20):
    """Run all strategies, produce ranked recommendations.

    Args:
        watchlist: list of symbols, "cached", or file path
        min_score: minimum score to include in results (0-100)

    Returns:
        list of Recommendation, sorted by score descending
    """
    feed = DataFeed()

    # Resolve symbols
    if isinstance(watchlist, str):
        if watchlist == "cached":
            symbols = feed.cache.get_symbols()
        else:
            with open(watchlist) as f:
                symbols = [line.strip().split("#")[0].strip()
                          for line in f if line.strip() and not line.startswith("#")]
    else:
        symbols = watchlist

    if not symbols:
        log.warning("No symbols to evaluate")
        return []

    # Suppress noise during batch scanning
    logging.getLogger("aquant.strategy.base").setLevel(logging.ERROR)

    # ── Step 1: scan each strategy across all symbols ──
    all_results = {}  # symbol -> {strategy_name: ScanResult}
    for sym in symbols:
        all_results[sym] = {}

    for strategy_cls, sname, weight in _get_strategies():
        scanner = SignalScanner(strategy_cls, feed)
        results = scanner.scan(symbols)
        for r in results:
            all_results[r.symbol][sname] = r

    # ── Step 2: score each stock ──
    recommendations = []
    for sym in symbols:
        rec = _score_stock(sym, all_results.get(sym, {}), feed)
        if rec and rec.score >= min_score:
            recommendations.append(rec)

    recommendations.sort(key=lambda r: r.score, reverse=True)
    return recommendations


def _score_stock(symbol, strategy_results, feed):
    """Calculate recommendation score for one stock.

    Scoring dimensions (0-100 total):
      - Signal consensus (0-40): how many strategies agree on direction
      - Signal recency (0-30): how fresh is the signal
      - Historical edge (0-30): average Sharpe from backtests
    """
    from aquant.data.symbols import normalize
    symbol = normalize(symbol)

    # Get current price and name
    price = 0.0
    name = symbol
    for sname, r in strategy_results.items():
        price = r.price
        name = r.name if r.name != symbol else name
        break

    if price == 0:
        try:
            df = feed.get(symbol)
            price = float(df["close"].iloc[-1])
        except Exception:
            return None

    rec = Recommendation(symbol, name, price)

    signals = {sname: r.signal for sname, r in strategy_results.items()}

    # ── Dimension 1: Signal Consensus (40 points) ──
    buy_count = sum(1 for s in signals.values() if s == "BUY")
    sell_count = sum(1 for s in signals.values() if s == "SELL")
    hold_count = sum(1 for s in signals.values() if s == "HOLD")
    total = len(strategy_results)

    if total == 0:
        return None

    if buy_count > sell_count:
        # Bullish consensus
        consensus_score = 25 + (buy_count / total) * 15
        rec.verdict = "买入" if buy_count >= 2 else "关注"
    elif sell_count > buy_count:
        # Bearish consensus
        consensus_score = (sell_count / total) * 10
        rec.verdict = "卖出"
    else:
        # Mixed
        consensus_score = 15
        rec.verdict = "观望"

    rec.score += consensus_score

    # ── Dimension 2: Signal Recency (30 points) ──
    from datetime import datetime, timedelta
    today = datetime.now().date()
    freshness_total = 0
    count = 0

    for sname, r in strategy_results.items():
        if r.signal in ("BUY", "SELL"):
            try:
                sig_date = datetime.strptime(r.date, "%Y-%m-%d").date()
                days_ago = (today - sig_date).days
                if days_ago <= 1:
                    freshness_total += 30
                elif days_ago <= 5:
                    freshness_total += 20
                elif days_ago <= 20:
                    freshness_total += 10
                elif days_ago <= 60:
                    freshness_total += 5
                count += 1
            except (ValueError, TypeError):
                pass

    recency_score = min(30, freshness_total / max(total, 1))
    rec.score += recency_score

    # ── Dimension 3: Historical Edge (30 points) ──
    # Run a quick backtest (using cached data) to get Sharpe
    edge_total = 0.0
    edge_count = 0

    for strategy_cls, sname, weight in _get_strategies():
        if sname not in strategy_results:
            continue
        try:
            df = feed.get(symbol, start="2020-01-01")
            if df is None or len(df) < 100:
                continue
            from aquant.backtest.engine import BacktestEngine
            engine = BacktestEngine(initial_cash=10_000)
            engine.add_data(df, symbol=symbol)
            engine.add_strategy(strategy_cls)
            result = engine.run()
            sharpe = result.metrics.get("sharpe_ratio", 0)
            # Map Sharpe to points: 0.5 -> 10, 1.0 -> 20, 2.0 -> 30
            edge_total += min(30, max(0, sharpe * 20))
            edge_count += 1
        except Exception:
            pass

    edge_score = min(30, edge_total / max(edge_count, 1))
    rec.score += edge_score

    # ── Build reasons ──
    rec.score = round(min(100, rec.score))
    rec.signals = signals

    if buy_count > sell_count:
        rec.reasons.append(
            f"{buy_count}/{total} 策略看多（{', '.join(k for k,v in signals.items() if v=='BUY')}）"
        )
    elif sell_count > buy_count:
        rec.reasons.append(
            f"{sell_count}/{total} 策略看空（{', '.join(k for k,v in signals.items() if v=='SELL')}）"
        )
    else:
        rec.reasons.append("策略信号分歧，方向不明")

    if recency_score >= 20:
        rec.reasons.append("信号新鲜（近期触发）")
    elif recency_score >= 10:
        rec.reasons.append("信号较新")
    else:
        rec.reasons.append("信号较旧，需确认")

    if edge_score >= 20:
        rec.reasons.append("历史回测表现优秀")
    elif edge_score >= 10:
        rec.reasons.append("历史回测表现尚可")
    else:
        rec.reasons.append("历史回测表现一般，谨慎")

    # Affordability check
    lot_cost = price * 100
    if lot_cost > 10_000:
        rec.reasons.append(f"一手需 ¥{lot_cost:,.0f}，资金不足")
        rec.score = max(0, rec.score - 15)

    # ── Trade plan ──
    if rec.verdict in ("买入", "关注"):
        _build_trade_plan(rec, feed)

    return rec


def _compute_atr(df, period=14):
    """Compute Average True Range."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    tr = pd.DataFrame({"tr1": tr1, "tr2": tr2, "tr3": tr3}).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _build_trade_plan(rec, feed):
    """Compute entry, stop loss, take profit, and position size."""
    import numpy as np
    try:
        df = feed.get(rec.symbol, start="2024-01-01")
        if df is None or len(df) < 50:
            return
    except Exception:
        return

    price = rec.price
    atr = _compute_atr(df)

    if atr <= 0 or np.isnan(atr):
        return

    rec.atr = round(atr, 2)

    # Suggested entry: current price (or next bar's open)
    rec.entry = price

    # Stop loss: entry - 2×ATR for longs
    rec.stop_loss = round(price - 2.0 * atr, 2)

    # Take profit: entry + 3×ATR (1.5:1 reward-to-risk)
    rec.take_profit = round(price + 3.0 * atr, 2)

    # Position sizing: risk 2% of 10k = 200 CNY per trade
    risk_per_share = price - rec.stop_loss
    if risk_per_share <= 0.01:
        risk_per_share = atr
    risk_capital = 200.0  # 2% of 10,000
    shares = int(risk_capital / risk_per_share / 100) * 100
    shares = max(100, shares)
    position_value = shares * price
    rec.position_pct = min(100, int(position_value / 10_000 * 100))

    # Risk % if stop loss hits
    max_loss = shares * risk_per_share
    rec.risk_pct = round(max_loss / 10_000 * 100, 1)

    # Add reason
    rec.reasons.append(
        f"止损¥{rec.stop_loss:.2f}(-{((price-rec.stop_loss)/price*100):.1f}%) "
        f"止盈¥{rec.take_profit:.2f}(+{((rec.take_profit-price)/price*100):.1f}%) "
        f"仓位{rec.position_pct}%"
    )


def print_recommendations(recs, top_n=20):
    """Format recommendations for terminal output."""
    if not recs:
        print("\n  没有符合条件的推荐。试试：")
        print("  aquant data fetch <code>  # 先下载数据")
        print("  aquant recommend          # 重新扫描\n")
        return

    # Header
    print(f"\n  {'代码':<8} {'名称':<10} {'现价':>8} {'评分':>6} {'建议':<6}  理由")
    print(f"  {'-'*8} {'-'*10} {'-'*8} {'-'*6}  {'-'*6}  {'-'*50}")

    for r in recs[:top_n]:
        # Color-code verdict
        if r.verdict == "买入":
            v = f"\033[1;31m{r.verdict}\033[0m"
        elif r.verdict == "卖出":
            v = f"\033[1;32m{r.verdict}\033[0m"
        elif r.verdict == "关注":
            v = f"\033[1;33m{r.verdict}\033[0m"
        else:
            v = r.verdict

        # Score bar
        bar_len = 6
        filled = int(r.score / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)

        # Short reasons (skip the trade plan reason, show it separately)
        short_reasons = [x for x in r.reasons if not x.startswith("止损")]
        reasons = "；".join(short_reasons[:3])

        print(f"  {r.symbol:<8} {r.name:<10} {r.price:>8.2f} {r.score:>3}/{bar}  {v:<12} {reasons}")

    # Trade plan details for BUY picks
    buy_recs = [r for r in recs if r.verdict in ("买入", "关注")]
    if buy_recs:
        print()
        print(f"  ━━━ 买入操作指南 ━━━")
        print(f"  {'股票':<12} {'买入价':>8} {'止损价':>8} {'止盈价':>8} {'ATR':>6} {'仓位':>5} {'风险':>5}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*6} {'-'*5} {'-'*5}")
        for r in buy_recs[:8]:
            if r.stop_loss > 0:
                print(f"  {r.name:<12} {r.entry:>8.2f} {r.stop_loss:>8.2f} "
                      f"{r.take_profit:>8.2f} {r.atr:>6.2f} "
                      f"{r.position_pct:>4}% {r.risk_pct:>4.1f}%")
        print()
        print(f"  💡 操作说明：")
        print(f"     买入价 = 次日开盘价或当前价")
        print(f"     止损价 = 买入价 - 2×ATR（跌破即卖，控制亏损）")
        print(f"     止盈价 = 买入价 + 3×ATR（涨到即卖，锁定利润）")
        print(f"     仓位 = 按单笔亏损≤2%资金计算（¥10,000中最多亏¥200/笔）")
        print(f"     ATR = 14日平均真实波幅（衡量日常波动大小）")
        print()
        print(f"  \033[1;31m推荐关注: {', '.join(r.name for r in buy_recs)}\033[0m")
    print(f"  共 {len(recs)} 只股票有明确信号\n")
