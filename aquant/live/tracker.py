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
    """Validate yesterday's picks against today's actual price movement.

    Two metrics:
      - direction_accuracy: % of BUY picks that rose today vs yesterday's close
      - The more meaningful metric is paper trading P&L, tracked separately.
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

    picks = yesterday_entry.get("picks", [])
    buy_picks = [p for p in picks if p.get("verdict") in ("买入", "关注")]

    if not buy_picks:
        return None

    hits, misses, total_change = 0, 0, 0.0
    for pick in buy_picks:
        try:
            df = feed.get(pick["symbol"])
            old_close = pick["price"]
            today_open = float(df["open"].iloc[-1])  # actual fill price
            if old_close > 0:
                change = (today_open - old_close) / old_close
                total_change += change
                if change > 0:
                    hits += 1
                else:
                    misses += 1
        except Exception:
            continue

    total = hits + misses
    if total == 0:
        return None

    results = {
        "buy_count": len(buy_picks),
        "validated": total,
        "direction_hits": hits,
        "direction_accuracy": hits / total,
        "avg_gap": round(total_change / total * 100, 2),  # average overnight gap %
    }

    # Store
    if yesterday_entry and "validation" not in yesterday_entry:
        yesterday_entry["validation"] = {
            "checked_date": date.today().isoformat(),
            "direction_accuracy": results["direction_accuracy"],
            "avg_gap_pct": results["avg_gap"],
        }
        save_history(data)

    return results


def _backtest_sharpe_weights():
    """Use historical backtest Sharpe to set initial strategy weights."""
    import json
    cache_path = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "opt_cache.json")
    if not os.path.exists(cache_path):
        return {}
    with open(cache_path) as f:
        cache = json.load(f)
    # Average Sharpe per strategy across all optimized stocks
    sharpes = {"均线交叉": [], "海龟突破": [], "布林回归": []}
    for key, entry in cache.items():
        for sname in sharpes:
            if key.endswith("_" + {"均线交叉": "ma_cross", "海龟突破": "turtle", "布林回归": "mean_revert"}[sname]):
                s = entry.get("sharpe", -999)
                if s > -900:
                    sharpes[sname].append(s)
    weights = {}
    for sname, vals in sharpes.items():
        if vals:
            avg = sum(vals) / len(vals)
            # Map Sharpe to weight: -0.5→0.4, 0→0.8, 0.5→1.2
            weights[sname] = round(max(0.25, min(1.5, 0.8 + avg * 0.8)), 2)
    return weights if weights else {}


def update_strategy_weights():
    """Update strategy weights: backtest Sharpe baseline + paper P&L micro-adjust.

    - Uses backtest Sharpe for initial weights (reflects historical edge)
    - Paper P&L makes small adjustments (±0.1) after just 2 closed trades
    - Full activation with larger adjustments after 10 trades
    """
    import json
    paper_path = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "paper.json")

    # Load previous weights as starting point (compound over time)
    data = load_history()
    prev_weights = data.get("strategy_weights", {})
    defaults = {"均线交叉": 1.0, "海龟突破": 0.8, "布林回归": 1.0}
    weights = dict(defaults)
    weights.update(prev_weights)  # carry forward previous adjustments
    # Also blend in backtest Sharpe baseline
    base = _backtest_sharpe_weights()
    for s in weights:
        if s in base:
            weights[s] = round(weights[s] * 0.7 + base[s] * 0.3, 2)  # 70% carry-forward, 30% baseline pull

    if not os.path.exists(paper_path):
        return weights

    with open(paper_path) as f:
        paper = json.load(f)

    trades = paper.get("history", [])
    n_trades = len(trades)
    if n_trades < 2:
        data = load_history()
        data["strategy_weights"] = weights
        save_history(data)
        return weights

    # Micro-adjust from paper P&L (each closed trade counted once)
    strategy_pnl = {}
    seen_trades = set()
    for entry in data.get("records", []):
        for pick in entry.get("picks", []):
            sym = pick["symbol"]
            signals = pick.get("signals", {})
            for i, t in enumerate(trades):
                trade_id = f"{t.get('symbol')}_{t.get('exit_date')}_{t.get('pnl')}"
                if t.get("symbol") == sym and trade_id not in seen_trades:
                    seen_trades.add(trade_id)
                    pnl = t.get("pnl", 0)
                    for sname in signals:
                        strategy_pnl[sname] = strategy_pnl.get(sname, 0) + pnl
                    break

    initial_cash = paper.get("initial_cash", 10000)
    for sname in base:
        pnl = strategy_pnl.get(sname, 0)
        pnl_pct = pnl / max(initial_cash, 1)

        # Progressive adjustment based on trade count
        if n_trades >= 10:
            step = 0.15  # Full activation
        elif n_trades >= 5:
            step = 0.10  # Medium
        else:
            step = 0.05  # Micro-adjust (2-4 trades)

        if pnl_pct > 0.02:
            weights[sname] = round(min(1.5, weights[sname] + step), 2)
        elif pnl_pct < -0.02:
            weights[sname] = round(max(0.2, weights[sname] - step), 2)

    data["strategy_weights"] = weights
    data["strategy_pnl"] = {k: round(v, 2) for k, v in strategy_pnl.items()}
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
