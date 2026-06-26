"""Bollinger Band mean reversion strategy.

Buy:  price touches lower band
Sell: price returns to middle band (SMA) or touches upper band
"""

from aquant.strategy.base import BaseStrategy


class MeanRevert(BaseStrategy):
    """Bollinger Band mean reversion. Parameters: period=20, std=2.0."""

    def init(self):
        period = self.params.get("period", 20)
        std_mult = self.params.get("std", 2.0)

        close = self.data["close"]
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()

        self.data["_mid"] = sma
        self.data["_upper"] = sma + std_mult * std
        self.data["_lower"] = sma - std_mult * std

    def next(self, i: int):
        if i < 1:
            return
        bar = self.data.iloc[i]
        prev = self.data.iloc[i - 1]
        close = bar["close"]

        if self.position == 0:
            # Price touches lower band relative to previous day's band
            if bar["low"] <= prev["_lower"]:
                self.buy()
        else:
            # Price returns to middle band
            if bar["high"] >= prev["_mid"]:
                self.close()
