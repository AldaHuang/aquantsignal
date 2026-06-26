"""Market regime detection and strategy parameter optimization.

Regime: uses ADX + price structure to classify market as trending/ranging.
Optimizer: grid-search parameters per stock, cache results, reuse on re-run.
"""

import json
import os
import logging
from datetime import date

log = logging.getLogger(__name__)

OPT_CACHE = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "opt_cache.json")


# ── Market Regime Detection ──────────────────────────────

def detect_regime(df):
    """Classify market state from recent price data.

    Returns one of: "trending" | "ranging" | "mixed"
    Also returns regime strength (0-100) for weighting.
    """
    import numpy as np

    close = df["close"]
    high = df["high"]
    low = df["low"]
    n = len(close)

    if n < 60:
        return "mixed", 50

    # ── ADX (14-day) ──
    period = 14
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1)),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 0.0001)
    adx = float(dx.rolling(period).mean().iloc[-1])

    # ── Price vs MA spread ──
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean() if n >= 200 else ma50
    price_vs_ma = abs(float(close.iloc[-1] / ma50.iloc[-1] - 1))

    # ── Recent volatility ratio ──
    recent_vol = float(close.pct_change().iloc[-20:].std())
    long_vol = float(close.pct_change().iloc[-60:].std())
    vol_ratio = recent_vol / (long_vol + 0.001)

    # ── Classify ──
    if adx > 25 and vol_ratio < 1.3:
        regime = "trending"
        strength = min(100, int(adx * 3))
    elif adx < 18 or (adx < 22 and price_vs_ma < 0.05 and vol_ratio > 0.8):
        regime = "ranging"
        strength = min(100, int((25 - adx) * 5))
    else:
        regime = "mixed"
        strength = 50

    log.debug("Regime: %s (ADX=%.1f, vol_ratio=%.2f, price_vs_ma=%.3f) strength=%d",
              regime, adx, vol_ratio, price_vs_ma, strength)

    return regime, strength


def get_regime_weights(regime, strength):
    """Convert regime detection to strategy weight multipliers.

    Trending: boost MA Cross + Turtle, reduce Mean Revert
    Ranging:  boost Mean Revert, reduce MA Cross + Turtle
    Mixed:    default weights
    """
    if regime == "trending":
        # Boost trend-following strategies
        return {
            "均线交叉": 1.0 + 0.01 * strength,    # up to 2.0
            "海龟突破": 0.8 + 0.01 * strength,    # up to 1.8
            "布林回归": 1.0 - 0.005 * strength,   # down to 0.5
        }
    elif regime == "ranging":
        return {
            "均线交叉": 1.0 - 0.005 * strength,
            "海龟突破": 0.8 - 0.004 * strength,
            "布林回归": 1.0 + 0.01 * strength,
        }
    else:  # mixed
        return {}


# ── Parameter Optimization ──────────────────────────────

import pandas as pd

# Parameter grids for grid search
GRIDS = {
    "ma_cross": {
        "fast": [5, 8, 10, 15, 20],
        "slow": [20, 30, 40, 60],
    },
    "turtle": {
        "entry": [10, 15, 20, 30],
        "exit": [5, 8, 10, 15],
    },
    "mean_revert": {
        "period": [10, 15, 20, 30],
        "std": [1.5, 2.0, 2.5],
    },
}

STRATEGY_MAP = {
    "ma_cross": "aquant.strategy.examples.ma_cross",
    "turtle": "aquant.strategy.examples.turtle",
    "mean_revert": "aquant.strategy.examples.mean_revert",
}


def _load_cache():
    if not os.path.exists(OPT_CACHE):
        return {}
    with open(OPT_CACHE) as f:
        return json.load(f)


def _save_cache(data):
    os.makedirs(os.path.dirname(OPT_CACHE), exist_ok=True)
    with open(OPT_CACHE, "w") as f:
        json.dump(data, f, indent=2)


def optimize_params(symbol, feed, strategy_name, strategy_cls, max_combos=8):
    """Grid-search best parameters for one strategy on one stock.

    Returns (best_params, best_sharpe) or ({}, -999).
    Uses cache to avoid re-running on consecutive days.
    """
    cache = _load_cache()
    cache_key = f"{symbol}_{strategy_name}"
    today = date.today().isoformat()

    # Return cached if fresh (< 5 days old)
    if cache_key in cache:
        entry = cache[cache_key]
        if entry.get("date", "") >= today:
            return entry.get("params", {}), entry.get("sharpe", -999)

    grid = GRIDS.get(strategy_name, {})
    if not grid:
        return {}, -999

    # Load data once
    try:
        df = feed.get(symbol, start="2022-01-01")
    except Exception:
        return {}, -999
    if df is None or len(df) < 100:
        return {}, -999

    # Generate parameter combinations (limit to max_combos)
    import itertools
    keys = list(grid.keys())
    values = list(grid.values())
    combos = list(itertools.product(*values))

    # If too many, sample evenly
    if len(combos) > max_combos:
        step = max(1, len(combos) // max_combos)
        combos = combos[::step][:max_combos]

    from aquant.backtest.engine import BacktestEngine

    best_params = None
    best_sharpe = -999

    for combo in combos:
        params = dict(zip(keys, combo))
        try:
            engine = BacktestEngine(initial_cash=10_000)
            engine.add_data(df, symbol=symbol)
            engine.add_strategy(strategy_cls, **params)
            result = engine.run()
            sharpe = result.metrics.get("sharpe_ratio", -999)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = params
        except Exception:
            pass

    if best_params:
        cache[cache_key] = {
            "date": today,
            "params": best_params,
            "sharpe": round(best_sharpe, 3),
        }
        _save_cache(cache)

    return best_params or {}, best_sharpe


def get_optimized_params(symbol, strategy_name):
    """Get cached optimized parameters for a stock+strategy combo."""
    cache = _load_cache()
    entry = cache.get(f"{symbol}_{strategy_name}", {})
    return entry.get("params", {}), entry.get("sharpe", -999)
