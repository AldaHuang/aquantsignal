"""Performance tracker: measure recommendation accuracy and adapt weights.

Compares today's BUY/SELL signals with next-day actual price movements.
Adjusts strategy weights based on rolling win rate.
"""

import json
import os
import logging
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "tracker.json")


def load_history():
    """Load tracking history from JSON file."""
    if not os.path.exists(TRACKER_FILE):
        return {"records": [], "strategy_weights": {}}
    with open(TRACKER_FILE) as f:
        return json.load(f)


def save_history(data):
    """Save tracking history."""
    os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
    with open(TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_recommendations(recs):
    """Record today's recommendations for tomorrow's validation.

    Saves: symbol, name, verdict, score, price, strategies that agreed.
    """
    from datetime import datetime
    data = load_history()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    entry = {
        "date": today,
        "time": now.strftime("%H:%M"),
        "picks": [],
    }

    for r in recs:
        pick = {
            "symbol": r.symbol,
            "name": r.name,
            "verdict": r.verdict,
            "score": r.score,
            "price": r.price,
            "reasons": r.reasons if hasattr(r, 'reasons') else [],
            "signals": r.signals if hasattr(r, 'signals') else {},
            "entry": r.entry if hasattr(r, 'entry') else r.price,
            "stop_loss": r.stop_loss if hasattr(r, 'stop_loss') else 0,
            "take_profit": r.take_profit if hasattr(r, 'take_profit') else 0,
            "atr": r.atr if hasattr(r, 'atr') else 0,
            "position_pct": r.position_pct if hasattr(r, 'position_pct') else 0,
            "risk_pct": r.risk_pct if hasattr(r, 'risk_pct') else 0,
        }
        entry["picks"].append(pick)

    # Replace today's entry if exists
    data["records"] = [e for e in data["records"] if e["date"] != today]
    data["records"].append(entry)
    save_history(data)
    log.info("Recorded %d recommendations for %s", len(entry["picks"]), today)


def validate_yesterday(feed):
    """Check how yesterday's predictions performed against today's prices.

    Returns dict with performance stats per strategy and per verdict.
    """
    data = load_history()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    yesterday_entry = None
    for e in data["records"]:
        if e["date"] == yesterday:
            yesterday_entry = e
            break

    if not yesterday_entry:
        return None

    results = {"buy_hits": 0, "buy_misses": 0, "sell_hits": 0, "sell_misses": 0,
               "strategy_hits": {}, "strategy_total": {}}

    for pick in yesterday_entry["picks"]:
        symbol = pick["symbol"]
        old_price = pick["price"]
        verdict = pick["verdict"]

        # Get today's price
        try:
            df = feed.get(symbol)
            new_price = float(df["close"].iloc[-1])
        except Exception:
            continue

        if old_price <= 0:
            continue

        change = (new_price - old_price) / old_price
        date_str = str(df.index[-1].date())

        # Validate
        if verdict in ("买入", "关注"):
            if change > 0:
                results["buy_hits"] += 1
            else:
                results["buy_misses"] += 1
        elif verdict == "卖出":
            if change < 0:
                results["sell_hits"] += 1
            else:
                results["sell_misses"] += 1

        # Per-strategy tracking
        for sname, signal in pick.get("signals", {}).items():
            results["strategy_total"][sname] = results["strategy_total"].get(sname, 0) + 1
            if signal == "BUY" and change > 0:
                results["strategy_hits"][sname] = results["strategy_hits"].get(sname, 0) + 1
            elif signal == "SELL" and change < 0:
                results["strategy_hits"][sname] = results["strategy_hits"].get(sname, 0) + 1

    # Calculate win rates
    total = results["buy_hits"] + results["buy_misses"]
    results["buy_win_rate"] = results["buy_hits"] / max(total, 1)

    # Store validation in history
    if yesterday_entry and "validation" not in yesterday_entry:
        yesterday_entry["validation"] = {
            "checked_date": date.today().isoformat(),
            "buy_win_rate": results["buy_win_rate"],
            "buy_hits": results["buy_hits"],
            "buy_misses": results["buy_misses"],
        }
        save_history(data)

    return results


def update_strategy_weights():
    """Update strategy weights based on actual paper trading P&L.

    For each strategy, computes cumulative P&L from closed paper trades.
    Strategies with positive P&L get higher weight.
    Strategies with negative P&L get reduced weight.
    Strategies with P&L < -5% of capital get temporarily disabled.
    """
    import json
    paper_path = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "paper.json")

    base_weights = {"均线交叉": 1.0, "海龟突破": 0.8, "布林回归": 1.0}
    weights = dict(base_weights)

    if not os.path.exists(paper_path):
        return weights

    with open(paper_path) as f:
        paper = json.load(f)

    trades = paper.get("history", [])
    if len(trades) < 5:
        return weights  # Not enough data yet

    # Calculate P&L per strategy from paper trades
    # A trade's P&L is attributed to strategies that voted BUY at entry
    strategy_pnl = {}
    strategy_trades = {}

    # Read tracker to map trades to strategy signals
    data = load_history()
    for entry in data.get("records", []):
        for pick in entry.get("picks", []):
            sym = pick["symbol"]
            signals = pick.get("signals", {})
            verdict = pick.get("verdict", "")

            # Find matching paper trade
            for t in trades:
                if t.get("symbol") == sym:
                    pnl = t.get("pnl", 0)
                    for sname, signal in signals.items():
                        strategy_pnl[sname] = strategy_pnl.get(sname, 0) + pnl
                        strategy_trades[sname] = strategy_trades.get(sname, 0) + 1
                    break

    # Adjust weights based on cumulative P&L
    initial_cash = paper.get("initial_cash", 10000)
    for sname in base_weights:
        pnl = strategy_pnl.get(sname, 0)
        n_trades = strategy_trades.get(sname, 0)
        if n_trades == 0:
            continue

        pnl_pct = pnl / initial_cash

        if pnl_pct < -0.05:
            # Losing badly → disable
            weights[sname] = 0.25
        elif pnl_pct < -0.02:
            # Losing → reduce
            weights[sname] = max(0.3, base_weights[sname] - 0.4)
        elif pnl_pct > 0.05:
            # Winning well → boost
            weights[sname] = min(1.5, base_weights[sname] + 0.4)
        elif pnl_pct > 0.02:
            # Winning → slight boost
            weights[sname] = min(1.3, base_weights[sname] + 0.2)
        # else: near flat → keep base weight

    data["strategy_weights"] = weights
    data["strategy_pnl"] = {k: round(v, 2) for k, v in strategy_pnl.items()}
    data["strategy_trades"] = strategy_trades
    save_history(data)

    return weights


def get_adaptive_weights():
    """Get current adaptive weights (load from file)."""
    data = load_history()
    return data.get("strategy_weights", {
        "均线交叉": 1.0, "海龟突破": 0.8, "布林回归": 1.0,
    })


def get_learning_status():
    """Return learning status for changelog display."""
    data = load_history()
    return {
        "weights": data.get("strategy_weights", {}),
        "pnl": data.get("strategy_pnl", {}),
        "trades": data.get("strategy_trades", {}),
    }
