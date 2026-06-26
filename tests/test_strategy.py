"""Test strategy base class: lifecycle, order methods, state updates."""
import unittest
import pandas as pd
from aquant.strategy.base import BaseStrategy, Order


class TestOrder(unittest.TestCase):
    def test_order_creation(self):
        o = Order("000001", "buy", 1000)
        self.assertEqual(o.symbol, "000001")
        self.assertEqual(o.side, "buy")
        self.assertEqual(o.size, 1000)
        self.assertFalse(o.filled)
        self.assertEqual(o.price, 0.0)

    def test_order_repr(self):
        o = Order("TEST", "sell", 500)
        o.price = 12.50
        o.bar_index = 3
        r = repr(o)
        self.assertIn("SELL", r)
        self.assertIn("500", r)
        self.assertIn("12.50", r)


class TestBaseStrategy(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "open": [10, 11, 12, 11, 10],
            "high": [10.5, 11.5, 12.5, 11.5, 10.5],
            "low": [9.5, 10.5, 11.5, 10.5, 9.5],
            "close": [10, 11, 12, 11, 10],
            "volume": [1e6] * 5,
        })

    def test_strategy_lifecycle_hooks_exist(self):
        s = BaseStrategy()
        # These should exist and be callable without error
        s.data = self.df
        s.init()
        s.next(0)
        s.next(1)
        s.finish()

    def test_strategy_params(self):
        s = BaseStrategy(fast=5, slow=20)
        self.assertEqual(s.params, {"fast": 5, "slow": 20})

    def test_buy_creates_order(self):
        s = BaseStrategy()
        s.data = self.df
        s.i = 0
        s.cash = 100000
        s.symbol = "TEST"
        order = s.buy(percent=1.0)
        self.assertIsNotNone(order)
        self.assertEqual(order.side, "buy")
        self.assertTrue(order.size >= 100)  # rounded to lot

    def test_buy_no_cash(self):
        s = BaseStrategy()
        s.data = self.df
        s.i = 0
        s.cash = 0
        order = s.buy()
        self.assertIsNone(order)

    def test_sell_no_position(self):
        s = BaseStrategy()
        s.position = 0
        order = s.sell()
        self.assertIsNone(order)

    def test_sell_creates_order(self):
        s = BaseStrategy()
        s.data = self.df
        s.i = 0
        s.position = 1000
        order = s.sell(percent=0.5)
        self.assertIsNotNone(order)
        self.assertEqual(order.side, "sell")
        self.assertEqual(order.size, 500)  # half of 1000

    def test_close_is_full_sell(self):
        s = BaseStrategy()
        s.data = self.df
        s.i = 0
        s.position = 1000
        order = s.close()
        self.assertIsNotNone(order)
        self.assertEqual(order.side, "sell")
        self.assertEqual(order.size, 1000)

    def test_current_close(self):
        s = BaseStrategy()
        s.data = self.df
        s.i = 2
        self.assertAlmostEqual(s._current_close(), 12.0)

    def test_buy_round_to_lot(self):
        """Buy rounds down to nearest 100 shares."""
        s = BaseStrategy()
        s.data = pd.DataFrame({
            "open": [50], "high": [51], "low": [49],
            "close": [50], "volume": [1e6],
        })
        s.i = 0
        s.cash = 10000
        s.symbol = "TEST"
        order = s.buy()
        # 10000 / 50 = 200 shares -> already a lot
        self.assertEqual(order.size, 200)

        s.cash = 9500
        order = s.buy()
        # 9500 / 50 = 190, rounded to 100
        self.assertEqual(order.size, 100)


if __name__ == "__main__":
    unittest.main()
