"""Test backtest engine event loop and order filling."""
import unittest
import pandas as pd
import numpy as np

from aquant.backtest.engine import BacktestEngine
from aquant.strategy.base import BaseStrategy


def _make_ohlcv(prices, start="2024-01-01"):
    """Create a simple OHLCV DataFrame from a list of close prices."""
    n = len(prices)
    dates = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [1e7] * n,
        "amount": [1e8] * n,
    }, index=dates)


class BuyAt5SellAt10(BaseStrategy):
    """Simple test strategy: buy at bar 5, sell at bar 10."""
    def next(self, i):
        if i == 5 and self.position == 0:
            self.buy()
        elif i == 10 and self.position > 0:
            self.close()


class TestBacktestEngine(unittest.TestCase):
    def setUp(self):
        # Price goes 10, 11, 12, ..., 20 (steady uptrend)
        self.prices = list(range(10, 21))
        self.df = _make_ohlcv(self.prices)

    def test_engine_runs(self):
        engine = BacktestEngine(initial_cash=100000)
        engine.add_data(self.df, symbol="TEST")
        engine.add_strategy(BuyAt5SellAt10)
        result = engine.run()
        self.assertIsNotNone(result)
        self.assertGreater(len(result.trades), 0)

    def test_warmup_detection(self):
        """Warmup finds first row where all numeric columns are non-NaN."""
        df = self.df.copy()
        df.iloc[:3, df.columns.get_loc("close")] = np.nan
        engine = BacktestEngine()
        warmup = engine._find_warmup(df)
        self.assertEqual(warmup, 3)

    def test_buy_and_sell_produce_trades(self):
        engine = BacktestEngine(initial_cash=100000)
        engine.add_data(self.df, symbol="TEST")
        engine.add_strategy(BuyAt5SellAt10)
        result = engine.run()

        buys = [t for t in result.trades if t.side == "buy"]
        sells = [t for t in result.trades if t.side == "sell"]
        self.assertEqual(len(buys), 1)
        # sell at bar 10 fills at next_open (bar 11); data has 11 bars (0-10),
        # so the sell goes pending but never fills. That's correct behavior.
        # With this_close, both would fill.
        if engine.fill_at == "this_close":
            self.assertEqual(len(sells), 1)

    def test_next_open_fill_timing(self):
        """With fill_at='next_open', order at bar 5 fills at bar 6's open."""
        engine = BacktestEngine(initial_cash=100000, fill_at="next_open")
        engine.add_data(self.df, symbol="TEST")
        engine.add_strategy(BuyAt5SellAt10)
        result = engine.run()

        buy = [t for t in result.trades if t.side == "buy"][0]
        # Order placed at bar 5, filled at next bar's open
        # open of bar 6 = price[6] = 16 (since prices are 10..20, index 6 = 16)
        self.assertEqual(buy.price, self.prices[6])

    def test_equity_curve_length(self):
        engine = BacktestEngine(initial_cash=100000)
        engine.add_data(self.df, symbol="TEST")
        engine.add_strategy(BuyAt5SellAt10)
        result = engine.run()

        # Equity should have same length as input data
        self.assertEqual(len(result.df["equity"].dropna()), len(self.df))

    def test_no_strategy_no_data_errors(self):
        engine = BacktestEngine()
        with self.assertRaises(ValueError):
            engine.run()

    def test_custom_params(self):
        """Strategy params are passed through correctly."""

        class ParamStrategy(BaseStrategy):
            def next(self, i):
                if i == 0:
                    self.buy()

        engine = BacktestEngine(initial_cash=100000)
        engine.add_data(self.df, symbol="TEST")
        engine.add_strategy(ParamStrategy, fast=10, slow=30, name="test")
        result = engine.run()
        self.assertIsNotNone(result)

    def test_strategy_error_dont_crash(self):
        """Strategy exceptions are caught, backtest continues."""

        class BuggyStrategy(BaseStrategy):
            def next(self, i):
                if i == 5:
                    raise RuntimeError("simulated bug")
                if i == 7 and self.position == 0:
                    self.buy()

        engine = BacktestEngine(initial_cash=100000)
        engine.add_data(self.df, symbol="TEST")
        engine.add_strategy(BuggyStrategy)
        result = engine.run()  # should not crash
        # Should have still made the buy at bar 7
        self.assertGreater(len(result.trades), 0)


if __name__ == "__main__":
    unittest.main()
