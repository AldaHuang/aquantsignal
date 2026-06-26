"""Turtle trading strategy (Donchian channel breakout).

Buy:  price breaks above N-day high
Sell: price breaks below M-day low (stop loss)
"""

from aquant.strategy.base import BaseStrategy


class Turtle(BaseStrategy):
    """Donchian channel breakout. Parameters: entry=20, exit=10."""

    def init(self):
        entry = self.params.get("entry", 20)
        exit_p = self.params.get("exit", 10)

        self.data["_high_n"] = self.data["high"].rolling(entry).max()
        self.data["_low_m"] = self.data["low"].rolling(exit_p).min()

    def next(self, i: int):
        if i < 1:
            return
        bar = self.data.iloc[i]
        prev = self.data.iloc[i - 1]
        close = bar["close"]

        if self.position == 0:
            # Breakout above previous N-day high
            if close > prev["_high_n"]:
                self.buy()
        else:
            # Breakdown below previous M-day low
            if close < prev["_low_m"]:
                self.close()
