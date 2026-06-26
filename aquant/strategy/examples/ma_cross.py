"""Dual moving average crossover strategy.

Golden cross:  fast MA crosses above slow MA → BUY
Dead cross:   fast MA crosses below slow MA → SELL
"""

from aquant.strategy.base import BaseStrategy
import warnings


class MaCross(BaseStrategy):
    """Moving average crossover. Parameters: fast=5, slow=20."""

    def init(self):
        fast = self.params.get("fast", 5)
        slow = self.params.get("slow", 20)

        close = self.data["close"]
        self.data["ma_fast"] = close.rolling(fast).mean()
        self.data["ma_slow"] = close.rolling(slow).mean()
        # Cross signals:
        # +1 when fast crosses above slow (golden cross)
        # -1 when fast crosses below slow (dead cross)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            fast_above = (self.data["ma_fast"] > self.data["ma_slow"]).astype(bool)
            prev = fast_above.shift(1).fillna(False).astype(bool)
        cross_up = fast_above & ~prev
        cross_down = ~fast_above & prev
        self.data["_cross"] = 0
        self.data.loc[cross_up, "_cross"] = 1
        self.data.loc[cross_down, "_cross"] = -1

    def next(self, i: int):
        cross = self.data["_cross"].iloc[i]

        if cross == 1 and self.position == 0:
            self.buy()
        elif cross == -1 and self.position > 0:
            self.close()
