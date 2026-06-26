"""Portfolio: track cash, position, equity curve, and trade history."""

import pandas as pd


class Trade:
    __slots__ = ("date", "symbol", "side", "size", "price", "value",
                 "commission", "stamp_duty", "net_pnl")

    def __init__(self, date, symbol, side, size, price, value,
                 commission, stamp_duty, net_pnl=None):
        self.date = date
        self.symbol = symbol
        self.side = side
        self.size = size
        self.price = price
        self.value = value
        self.commission = commission
        self.stamp_duty = stamp_duty
        self.net_pnl = net_pnl       # only for sells

    def __repr__(self):
        pnl_str = f" pnl={self.net_pnl:+.2f}" if self.net_pnl is not None else ""
        return (f"Trade({self.date.date()} {self.side.upper()} "
                f"{self.size}@{self.price:.2f}{pnl_str})")


class Portfolio:
    """Tracks a single-stock portfolio with A-share cost model."""

    def __init__(self, initial_cash, commission_rate, stamp_duty_rate,
                 min_commission=5.0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.min_commission = min_commission

        self.position = 0           # shares held
        self.avg_cost = 0.0         # weighted average entry price
        self.trades = []            # list of Trade
        self.equity_curve = []      # list of (date, equity) tuples
        self._realized_pnl = 0.0

    # ── actions ────────────────────────────────────────────
    def buy(self, date, price, size):
        """Execute a buy. Returns Trade."""
        cost = price * size
        commission = max(cost * self.commission_rate, self.min_commission)
        total = cost + commission

        if total > self.cash:
            # Can't afford — scale down
            affordable_shares = int(
                self.cash / (price * (1 + self.commission_rate)) / 100
            ) * 100
            if affordable_shares < 100:
                return None
            size = affordable_shares
            cost = price * size
            commission = max(cost * self.commission_rate, self.min_commission)
            total = cost + commission

        # Update avg cost
        if self.position > 0:
            old_value = self.position * self.avg_cost
            self.avg_cost = (old_value + cost) / (self.position + size)
        else:
            self.avg_cost = price

        self.position += size
        self.cash -= total

        trade = Trade(
            date=date, symbol="", side="buy", size=size,
            price=price, value=cost,
            commission=commission, stamp_duty=0.0,
        )
        self.trades.append(trade)
        return trade

    def sell(self, date, price, size):
        """Execute a sell. Returns Trade with PnL."""
        if size > self.position:
            size = self.position // 100 * 100
        if size < 100:
            return None

        value = price * size
        commission = max(value * self.commission_rate, self.min_commission)
        stamp_duty = value * self.stamp_duty_rate  # A-share: sell side only
        total_fee = commission + stamp_duty
        net = value - total_fee

        # PnL calculation (relative to avg_cost)
        cost_basis = self.avg_cost * size
        net_pnl = net - cost_basis
        self._realized_pnl += net_pnl

        self.position -= size
        self.cash += net

        if self.position == 0:
            self.avg_cost = 0.0

        trade = Trade(
            date=date, symbol="", side="sell", size=size,
            price=price, value=value,
            commission=commission, stamp_duty=stamp_duty,
            net_pnl=net_pnl,
        )
        self.trades.append(trade)
        return trade

    # ── valuation ──────────────────────────────────────────
    def mark_to_market(self, date, current_price):
        """Record equity at current price."""
        equity = self.cash + self.position * current_price
        self.equity_curve.append((date, equity))
        return equity

    @property
    def equity(self):
        return self.cash + self.position * self._last_price

    def _last_price(self):
        return 0.0  # stub
