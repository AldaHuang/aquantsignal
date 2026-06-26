"""Performance metrics. All functions are stateless (take data, return numbers)."""

import numpy as np
import pandas as pd


def total_return(equity):
    """(final - initial) / initial."""
    if len(equity) < 2:
        return 0.0
    return float((equity[-1] - equity[0]) / equity[0])


def annual_return(equity, trading_days=252):
    """Compound annual growth rate (CAGR)."""
    if len(equity) < 2:
        return 0.0
    total = total_return(equity)
    n = len(equity)
    if n <= 1 or total <= -1:
        return total
    return float((1 + total) ** (trading_days / n) - 1)


def max_drawdown(equity):
    """Maximum peak-to-trough decline as a positive ratio (e.g., 0.25 = 25%)."""
    if len(equity) < 2:
        return 0.0
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    return float(np.max(drawdown))


def max_drawdown_duration(equity):
    """Longest number of consecutive periods underwater."""
    if len(equity) < 2:
        return 0
    peak = np.maximum.accumulate(equity)
    underwater = equity < peak
    if not np.any(underwater):
        return 0
    # Count longest run of True
    max_dur = 0
    cur = 0
    for u in underwater:
        if u:
            cur += 1
            max_dur = max(max_dur, cur)
        else:
            cur = 0
    return max_dur


def sharpe_ratio(equity, risk_free=0.03, trading_days=252):
    """Annualized Sharpe ratio."""
    if len(equity) < 2:
        return 0.0
    eq = np.asarray(equity, dtype=float)
    # If equity is effectively flat (first == last), return 0
    if abs(eq[-1] - eq[0]) < 1e-9:
        return 0.0
    daily_returns = (eq[1:] - eq[:-1]) / np.maximum(eq[:-1], 1e-9)
    if len(daily_returns) == 0:
        return 0.0
    excess = daily_returns - risk_free / trading_days
    std = float(np.std(excess, ddof=1))
    if std < 1e-9:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(trading_days))


def win_rate(trades):
    """Fraction of sell trades with positive net PnL."""
    sells = [t for t in trades if t.side == "sell" and t.net_pnl is not None]
    if not sells:
        return 0.0
    return sum(1 for t in sells if t.net_pnl > 0) / len(sells)


def profit_factor(trades):
    """Gross profit / gross loss."""
    sells = [t for t in trades if t.side == "sell" and t.net_pnl is not None]
    gross_profit = sum(t.net_pnl for t in sells if t.net_pnl > 0)
    gross_loss = abs(sum(t.net_pnl for t in sells if t.net_pnl < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 1.0
    return gross_profit / gross_loss


def calmar_ratio(equity, trading_days=252):
    """Annual return / max drawdown."""
    ann = annual_return(equity, trading_days)
    mdd = max_drawdown(equity)
    if mdd == 0:
        return float("inf") if ann > 0 else 0.0
    return ann / mdd


def daily_returns(equity):
    """Series of daily returns."""
    if len(equity) < 2:
        return np.array([])
    eq = np.asarray(equity, dtype=float)
    return (eq[1:] - eq[:-1]) / eq[:-1]


def volatility(equity, trading_days=252):
    """Annualized volatility."""
    rets = daily_returns(equity)
    if len(rets) == 0:
        return 0.0
    return float(np.std(rets, ddof=1) * np.sqrt(trading_days))


def compute_all(equity, trades, trading_days=252):
    """Compute all metrics and return as a dict."""
    return {
        "initial": float(equity[0]) if len(equity) > 0 else 0.0,
        "final": float(equity[-1]) if len(equity) > 0 else 0.0,
        "total_return": total_return(equity),
        "annual_return": annual_return(equity, trading_days),
        "sharpe_ratio": sharpe_ratio(equity, 0.03, trading_days),
        "max_drawdown": max_drawdown(equity),
        "max_drawdown_duration": max_drawdown_duration(equity),
        "volatility": volatility(equity, trading_days),
        "calmar_ratio": calmar_ratio(equity, trading_days),
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "num_trades": len([t for t in trades if t.side == "sell"]),
    }
