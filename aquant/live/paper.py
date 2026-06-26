"""Paper trading engine: simulate trades based on daily recommendations.

Rules:
- BUY signal → open position at estimated fill price (next open)
- SELL signal → close position
- Stock dropped from recs → hold, sell only on explicit SELL or stop loss
- A-share costs: 0.03% commission, 0.1% stamp duty (sell only), min ¥5
"""

import os
import json
import logging
from datetime import date, datetime

log = logging.getLogger(__name__)

PAPER_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "paper.json")


class PaperTrader:
    def __init__(self, initial_cash=10_000):
        data = _load()
        self.cash = data.get("cash", initial_cash)
        self.initial_cash = data.get("initial_cash", initial_cash)
        self.positions = data.get("positions", {})   # symbol -> {shares, avg_cost}
        self.pending = data.get("pending", {})         # symbol -> {shares, target_price}
        self.history = data.get("history", [])          # list of closed trades
        self.equity_log = data.get("equity_log", [])    # [{date, equity, cash, position_value}]

    def update(self, recommendations, feed=None):
        """Process today's recommendations, update positions and fill pending orders.

        Args:
            recommendations: list of Recommendation objects
            feed: DataFeed for fetching current prices
        """
        today = date.today().isoformat()
        rec_map = {r.symbol: r for r in recommendations}

        # ── Step 1: Fill yesterday's pending orders at today's open ──
        for sym, order in list(self.pending.items()):
            fill_price = order["target_price"]
            # Actual fill: yesterday's signal → today's opening auction
            if feed:
                try:
                    df = feed.get(sym)
                    fill_price = float(df["open"].iloc[-1])  # today's open
                except Exception:
                    pass

            order["fill_price"] = fill_price
            order["fill_date"] = today
            self._execute(order)
            del self.pending[sym]

        # ── Step 2: Stop loss check on existing positions ──
        for sym in list(self.positions):
            pos = self.positions[sym]
            if feed and pos.get("stop_loss", 0) > 0:
                try:
                    df = feed.get(sym)
                    low = float(df["low"].iloc[-1])
                    if low <= pos["stop_loss"]:
                        self._close_position(sym, pos["stop_loss"], today, "止损")
                        continue
                except Exception:
                    pass

        # ── Step 3: Process new signals ──
        for sym, r in rec_map.items():
            verdict = r.verdict

            if sym in self.positions:
                # Already holding
                if verdict == "卖出":
                    self._close_position(sym, r.price, today, "卖出信号")
                else:
                    # Update stop loss
                    if hasattr(r, 'stop_loss') and r.stop_loss > 0:
                        self.positions[sym]["stop_loss"] = r.stop_loss

            elif sym in self.pending:
                pass  # Already pending, wait for fill

            elif verdict in ("买入", "关注"):
                # New buy signal — queue for tomorrow
                price = r.price
                shares = self._calc_shares(price, getattr(r, 'stop_loss', price * 0.9))
                stop_loss = getattr(r, 'stop_loss', 0)
                if shares >= 100:
                    self.pending[sym] = {
                        "shares": shares,
                        "target_price": price,
                        "stop_loss": stop_loss,
                        "signal_date": today,
                        "name": r.name,
                    }

        # ── Step 4: Mark positions to market ──
        position_value = 0
        if feed:
            for sym, pos in self.positions.items():
                try:
                    df = feed.get(sym)
                    pos["current_price"] = float(df["close"].iloc[-1])
                    position_value += pos["shares"] * pos["current_price"]
                except Exception:
                    position_value += pos["shares"] * pos.get("avg_cost", 0)

        equity = self.cash + position_value
        self.equity_log.append({
            "date": today,
            "equity": round(equity, 2),
            "cash": round(self.cash, 2),
            "position_value": round(position_value, 2),
        })

        # Keep only last 90 days
        if len(self.equity_log) > 90:
            self.equity_log = self.equity_log[-90:]

        self._save()
        return self.summary()

    def _execute(self, order):
        """Execute a filled order."""
        sym = order.get("symbol", "")
        side = order.get("side", "buy")
        shares = order["shares"]
        price = order["fill_price"]
        value = shares * price
        commission = max(value * 0.0003, 5.0)
        stamp_duty = value * 0.001 if side == "sell" else 0

        if side == "buy":
            total = value + commission
            if total > self.cash:
                shares = int(self.cash / (price * 1.0003) / 100) * 100
                if shares < 100:
                    return
                value = shares * price
                commission = max(value * 0.0003, 5.0)
                total = value + commission
            self.cash -= total
            # Average cost
            if sym in self.positions:
                old = self.positions[sym]
                old_cost = old["shares"] * old["avg_cost"]
                new_cost = value
                total_shares = old["shares"] + shares
                old["avg_cost"] = (old_cost + new_cost) / total_shares
                old["shares"] = total_shares
            else:
                self.positions[sym] = {
                    "shares": shares,
                    "avg_cost": price,
                    "entry_date": order.get("fill_date", "?"),
                    "current_price": price,
                    "stop_loss": order.get("stop_loss", 0),
                    "name": order.get("name", sym),
                }

        else:  # sell
            if sym not in self.positions:
                return
            pos = self.positions[sym]
            if shares > pos["shares"]:
                shares = pos["shares"]
            value = shares * price
            commission = max(value * 0.0003, 5.0)
            stamp_duty = value * 0.001
            net = value - commission - stamp_duty
            cost = shares * pos["avg_cost"]
            pnl = net - cost
            pnl_pct = pnl / cost * 100 if cost > 0 else 0

            self.cash += net
            pos["shares"] -= shares

            self.history.append({
                "symbol": sym,
                "name": pos.get("name", sym),
                "side": side,
                "shares": shares,
                "entry_price": pos["avg_cost"],
                "exit_price": price,
                "exit_date": order.get("fill_date", "?"),
                "entry_date": pos.get("entry_date", "?"),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "reason": order.get("reason", ""),
            })

            if pos["shares"] < 100:
                del self.positions[sym]

    def _close_position(self, sym, price, date_str, reason):
        """Execute a sell order to close an existing position immediately."""
        if sym not in self.positions:
            return
        pos = self.positions[sym]
        order = {
            "symbol": sym,
            "shares": pos["shares"],
            "side": "sell",
            "fill_price": price,
            "fill_date": date_str,
            "name": pos.get("name", sym),
            "reason": reason,
        }
        self._execute(order)

    def _calc_shares(self, price, stop_loss):
        """Calculate position size: risk 2% of capital per trade."""
        risk = self.cash * 0.02
        stop_dist = price - stop_loss if stop_loss > 0 else price * 0.05
        if stop_dist <= 0.01:
            stop_dist = price * 0.05
        shares = int(risk / stop_dist / 100) * 100
        # Cap at available cash
        max_shares = int(self.cash / (price * 1.0003) / 100) * 100
        return min(max(100, shares), max_shares)

    def summary(self):
        """Return a dict summary for display."""
        total_pnl = sum(t["pnl"] for t in self.history)
        wins = sum(1 for t in self.history if t["pnl"] > 0)
        total_trades = len(self.history)
        latest_eq = self.equity_log[-1]["equity"] if self.equity_log else self.cash
        total_return = (latest_eq - self.initial_cash) / self.initial_cash * 100

        return {
            "cash": round(self.cash, 2),
            "equity": round(latest_eq, 2),
            "total_return_pct": round(total_return, 2),
            "positions": len(self.positions),
            "pending": len(self.pending),
            "total_trades": total_trades,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(wins / max(total_trades, 1) * 100, 1),
            "history": self.history[-10:],
            "positions_list": [
                {
                    "symbol": sym,
                    "name": p.get("name", sym),
                    "shares": p["shares"],
                    "avg_cost": round(p["avg_cost"], 2),
                    "current_price": round(p.get("current_price", p["avg_cost"]), 2),
                    "pnl_pct": round(
                        (p.get("current_price", p["avg_cost"]) - p["avg_cost"])
                        / p["avg_cost"] * 100, 2
                    ),
                }
                for sym, p in self.positions.items()
            ],
        }

    def _save(self):
        with open(PAPER_FILE, "w") as f:
            json.dump({
                "cash": self.cash,
                "initial_cash": self.initial_cash,
                "positions": self.positions,
                "pending": self.pending,
                "history": self.history,
                "equity_log": self.equity_log,
            }, f, indent=2, ensure_ascii=False, default=str)


def _load():
    if not os.path.exists(PAPER_FILE):
        return {}
    with open(PAPER_FILE) as f:
        return json.load(f)
