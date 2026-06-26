"""Base strategy class with lifecycle hooks and order methods."""

import logging
import pandas as pd

log = logging.getLogger(__name__)


class Order:
    """Simple order value object."""
    __slots__ = ("symbol", "side", "size", "price", "bar_index",
                 "filled", "value", "commission", "stamp_duty")

    def __init__(self, symbol, side, size):
        self.symbol = symbol
        self.side = side          # "buy" or "sell"
        self.size = size          # shares
        self.price = 0.0          # filled by engine
        self.bar_index = -1       # bar index when placed
        self.filled = False
        self.value = 0.0          # size * price
        self.commission = 0.0
        self.stamp_duty = 0.0

    def __repr__(self):
        return (f"Order({self.side.upper()} {self.size}@{self.price:.2f}"
                f" bar={self.bar_index})")


class BaseStrategy:
    """Strategy base class.

    Usage: subclass and override init() and next(i).

    Lifecycle:
        __init__(params) -> init() -> next(0) ... next(N-1) -> finish()

    Access in next():
        self.data            - DataFrame (OHLCV + indicators)
        self.i               - current bar index
        self.cash            - available cash
        self.position        - shares held
        self.position_value  - position * close_price
        self.equity          - cash + position_value
        self.symbol          - current symbol
        self.params          - strategy parameters dict

    Place orders: self.buy(percent), self.sell(percent), self.close()
    """

    def __init__(self, **params):
        self.params = params

        # Set by engine before event loop
        self.data = pd.DataFrame()
        self.symbol = ""
        self.i = 0
        self.cash = 0.0
        self.position = 0
        self.position_value = 0.0
        self.equity = 0.0

        # Internal: the engine reads this
        self._pending_order = None

    # ── hooks (override these) ─────────────────────────────
    def init(self):
        """Calculate indicators. Called once before the event loop.
        Add columns to self.data, e.g.:
            self.data['ma20'] = self.data['close'].rolling(20).mean()
        """

    def next(self, i: int):
        """Trading logic. Called for every bar after warmup.
        Use self.buy() / self.sell() / self.close() to place orders.
        """

    def finish(self):
        """Called once after all bars are processed. Optional."""

    # ── order methods ──────────────────────────────────────
    def buy(self, percent=1.0):
        """Buy using `percent` of available cash at next bar's open."""
        if self.cash <= 0:
            log.debug("buy: no cash available")
            return None
        amount = self.cash * percent
        price = self._current_close()
        if price <= 0:
            return None
        # A-shares trade in lots of 100 shares
        lots = int(amount / (price * 100))
        if lots < 1:
            log.warning(
                "Insufficient cash for 1 lot of %s: need ¥%.0f, have ¥%.0f",
                self.symbol, price * 100, self.cash,
            )
            return None
        size = lots * 100
        order = Order(self.symbol, "buy", size)
        order.bar_index = self.i
        self._pending_order = order
        return order

    def sell(self, percent=1.0):
        """Sell `percent` of current position."""
        if self.position <= 0:
            return None
        size = int(self.position * percent / 100) * 100
        if size < 100:
            return None
        order = Order(self.symbol, "sell", size)
        order.bar_index = self.i
        self._pending_order = order
        return order

    def close(self):
        """Sell entire position."""
        return self.sell(1.0)

    def _current_close(self):
        """Helper: current bar's close price."""
        if self.data.empty or self.i >= len(self.data):
            return 0.0
        return float(self.data["close"].iloc[self.i])
