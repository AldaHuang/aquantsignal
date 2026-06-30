"""Paper trading engine: simulate trades based on daily recommendations.

Records every event: order creation, fills, P&L, commissions, stop losses.
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
        self.positions = data.get("positions", {})
        self.pending = data.get("pending", {})
        self.history = data.get("history", [])
        self.equity_log = data.get("equity_log", [])
        self.order_log = data.get("order_log", [])  # comprehensive event log

    def update(self, recommendations, feed=None):
        """Process today's recommendations, update positions and fill pending orders."""
        today = date.today().isoformat()
        now = datetime.now().strftime("%H:%M")
        rec_map = {r.symbol: r for r in recommendations}

        # ── Step 1: Fill pending orders at today's open ──
        for sym, order in list(self.pending.items()):
            fill_price = order["target_price"]
            if feed:
                try:
                    df = feed.get(sym, force_refresh=True)
                    today_open = float(df["open"].iloc[-1])
                    # Reject stale/anomalous prices
                    target = order["target_price"]
                    if 0.5 * target < today_open < 2.0 * target:
                        fill_price = today_open
                    else:
                        log.warning("Price anomaly %s: target=%.2f open=%.2f", sym, target, today_open)
                except Exception:
                    pass
            order["fill_price"] = fill_price
            order["fill_date"] = today
            order["fill_time"] = now
            self._execute(order)
            del self.pending[sym]

        # ── Step 2: Stop loss check ──
        for sym in list(self.positions):
            pos = self.positions[sym]
            if feed and pos.get("stop_loss", 0) > 0:
                try:
                    df = feed.get(sym)
                    low = float(df["low"].iloc[-1])
                    if low <= pos["stop_loss"]:
                        self._close_position(sym, pos["stop_loss"], today, "止损触发")
                        continue
                except Exception:
                    pass

        # ── Step 3: Process new signals ──
        for sym, r in rec_map.items():
            verdict = r.verdict
            if sym in self.positions:
                if verdict == "卖出":
                    self._close_position(sym, r.price, today, "卖出信号")
                elif hasattr(r, 'stop_loss') and r.stop_loss > 0:
                    self.positions[sym]["stop_loss"] = r.stop_loss
            elif sym in self.pending:
                pass
            elif verdict in ("买入", "关注"):
                price = r.price
                shares = self._calc_shares(price, getattr(r, 'stop_loss', price * 0.9))
                stop_loss = getattr(r, 'stop_loss', 0)
                if shares >= 100:
                    self.pending[sym] = {
                        "shares": shares, "target_price": price,
                        "stop_loss": stop_loss, "signal_date": today,
                        "name": r.name, "side": "buy",
                        "created_time": now,
                    }
                    self._log_event("ORDER_CREATED", sym, {
                        "name": r.name, "side": "buy", "shares": shares,
                        "target_price": round(price, 2),
                        "stop_loss": round(stop_loss, 2),
                    })

        # ── Step 4: Mark to market ──
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
            "date": today, "time": now,
            "equity": round(equity, 2),
            "cash": round(self.cash, 2),
            "position_value": round(position_value, 2),
            "return_pct": round((equity - self.initial_cash) / self.initial_cash * 100, 2),
        })
        if len(self.equity_log) > 90:
            self.equity_log = self.equity_log[-90:]

        self._save()
        return self.summary()

    # ── Order execution ──────────────────────────────────
    def _execute(self, order):
        sym = order.get("symbol", "")
        side = order.get("side", "buy")
        shares = order["shares"]
        price = order["fill_price"]
        fill_date = order.get("fill_date", "?")
        fill_time = order.get("fill_time", "?")

        value = shares * price
        commission = max(value * 0.0003, 5.0)
        stamp_duty = value * 0.001 if side == "sell" else 0
        cash_before = self.cash

        if side == "buy":
            total = value + commission
            if total > self.cash:
                shares = int(self.cash / (price * 1.0003) / 100) * 100
                if shares < 100:
                    self._log_event("ORDER_FAILED", sym, {
                        "reason": "资金不足", "cash": round(self.cash, 2),
                        "needed": round(total, 2),
                    })
                    return
                value = shares * price
                commission = max(value * 0.0003, 5.0)
                total = value + commission
            self.cash -= total

            if sym in self.positions:
                old = self.positions[sym]
                old_cost = old["shares"] * old["avg_cost"]
                old["avg_cost"] = (old_cost + value) / (old["shares"] + shares)
                old["shares"] += shares
            else:
                self.positions[sym] = {
                    "shares": shares, "avg_cost": price,
                    "entry_date": fill_date, "current_price": price,
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
                "symbol": sym, "name": pos.get("name", sym),
                "side": side, "shares": shares,
                "entry_price": round(pos["avg_cost"], 2),
                "exit_price": round(price, 2),
                "exit_date": fill_date, "entry_date": pos.get("entry_date", "?"),
                "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
                "commission": round(commission, 2),
                "stamp_duty": round(stamp_duty, 2),
                "reason": order.get("reason", ""),
            })

            if pos["shares"] < 100:
                del self.positions[sym]

        # ── Log every fill ──
        self._log_event("ORDER_FILLED", sym, {
            "name": order.get("name", sym), "side": side, "shares": shares,
            "price": round(price, 2), "value": round(value, 2),
            "commission": round(commission, 2),
            "stamp_duty": round(stamp_duty, 2),
            "cash_before": round(cash_before, 2),
            "cash_after": round(self.cash, 2),
            "reason": order.get("reason", ""),
        })

    def _close_position(self, sym, price, date_str, reason):
        if sym not in self.positions:
            return
        pos = self.positions[sym]
        self._execute({
            "symbol": sym, "side": "sell", "shares": pos["shares"],
            "fill_price": price, "fill_date": date_str,
            "fill_time": datetime.now().strftime("%H:%M"),
            "stop_loss": 0, "name": pos.get("name", sym),
            "reason": reason,
        })

    def _calc_shares(self, price, stop_loss):
        risk = self.cash * 0.02
        stop_dist = max(price - stop_loss, price * 0.05) if stop_loss > 0 else price * 0.05
        shares = int(risk / stop_dist / 100) * 100
        max_shares = int(self.cash / (price * 1.0003) / 100) * 100
        return min(max(100, shares), max_shares)

    # ── Event log ────────────────────────────────────────
    def _log_event(self, event_type, symbol, details):
        self.order_log.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "event": event_type,
            "symbol": symbol,
            **details,
        })
        # Keep only last 200 events
        if len(self.order_log) > 200:
            self.order_log = self.order_log[-200:]

    # ── Summary for display ──────────────────────────────
    def summary(self):
        total_pnl = sum(t["pnl"] for t in self.history)
        wins = sum(1 for t in self.history if t["pnl"] > 0)
        total_trades = len(self.history)
        latest_eq = self.equity_log[-1]["equity"] if self.equity_log else self.cash
        total_return = (latest_eq - self.initial_cash) / self.initial_cash * 100

        return {
            "cash": round(self.cash, 2),
            "equity": round(latest_eq, 2),
            "total_return_pct": round(total_return, 2),
            "initial_cash": self.initial_cash,
            "positions": len(self.positions),
            "pending": len(self.pending),
            "total_trades": total_trades,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(wins / max(total_trades, 1) * 100, 1),
            "history": self.history[-10:],
            "order_log": self.order_log[-20:],
            "positions_list": [
                {
                    "symbol": sym, "name": p.get("name", sym),
                    "shares": p["shares"], "avg_cost": round(p["avg_cost"], 2),
                    "current_price": round(p.get("current_price", p["avg_cost"]), 2),
                    "market_value": round(p["shares"] * p.get("current_price", p["avg_cost"]), 2),
                    "pnl_pct": round(
                        (p.get("current_price", p["avg_cost"]) - p["avg_cost"])
                        / p["avg_cost"] * 100, 2
                    ),
                    "entry_date": p.get("entry_date", "?"),
                    "stop_loss": round(p.get("stop_loss", 0), 2),
                } for sym, p in self.positions.items()
            ],
        }

    def _save(self):
        with open(PAPER_FILE, "w") as f:
            json.dump({
                "cash": self.cash, "initial_cash": self.initial_cash,
                "positions": self.positions, "pending": self.pending,
                "history": self.history, "equity_log": self.equity_log,
                "order_log": self.order_log,
            }, f, indent=2, ensure_ascii=False, default=str)


def _load():
    if not os.path.exists(PAPER_FILE):
        return {}
    with open(PAPER_FILE) as f:
        return json.load(f)
