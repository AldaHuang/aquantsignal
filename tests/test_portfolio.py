"""Test portfolio accounting: buys, sells, commissions, A-share rules."""
import unittest
from datetime import date
from aquant.backtest.portfolio import Portfolio


class TestPortfolio(unittest.TestCase):
    def setUp(self):
        # A-share rates: commission 0.03%, stamp duty 0.1% (sell only)
        self.p = Portfolio(
            initial_cash=100_000,
            commission_rate=0.0003,
            stamp_duty_rate=0.001,
            min_commission=5.0,
        )

    def test_initial_state(self):
        self.assertEqual(self.p.cash, 100_000)
        self.assertEqual(self.p.position, 0)
        self.assertEqual(len(self.p.trades), 0)

    def test_buy_reduces_cash(self):
        d = date(2024, 1, 2)
        # Buy 1000 shares at 10.00 = 10000 + commission
        trade = self.p.buy(d, 10.00, 1000)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, "buy")
        self.assertEqual(trade.size, 1000)
        # Commission: max(10000 * 0.0003, 5) = 5
        self.assertAlmostEqual(trade.commission, 5.0)
        # Cash reduced by cost + commission
        self.assertAlmostEqual(self.p.cash, 100_000 - 10000 - 5)
        self.assertEqual(self.p.position, 1000)

    def test_buy_rounds_to_lot(self):
        """Buy method (in strategy) rounds to 100-share lots."""
        # Portfolio.buy accepts exact size, rounding happens in strategy
        d = date(2024, 1, 2)
        trade = self.p.buy(d, 10.00, 250)
        self.assertEqual(trade.size, 250)  # Portfolio accepts exact
        self.assertEqual(self.p.position, 250)

    def test_sell_incurs_stamp_duty(self):
        d = date(2024, 1, 2)
        self.p.buy(d, 10.00, 1000)
        d2 = date(2024, 1, 10)
        trade = self.p.sell(d2, 12.00, 1000)
        self.assertIsNotNone(trade)
        # Value = 12000, commission = max(12000*0.0003, 5) = 5
        # Stamp duty = 12000 * 0.001 = 12
        self.assertAlmostEqual(trade.commission, 5.0)
        self.assertAlmostEqual(trade.stamp_duty, 12.0)
        # PnL: net received (12000-5-12) - cost basis (10000) = 1983
        self.assertAlmostEqual(trade.net_pnl, 12000 - 5 - 12 - 10000)
        self.assertEqual(self.p.position, 0)

    def test_sell_cannot_exceed_position(self):
        d = date(2024, 1, 2)
        self.p.buy(d, 10.00, 500)
        d2 = date(2024, 1, 10)
        trade = self.p.sell(d2, 11.00, 1000)  # try to sell more than we have
        self.assertIsNotNone(trade)
        self.assertEqual(trade.size, 500)  # capped

    def test_buy_cannot_exceed_cash(self):
        d = date(2024, 1, 2)
        # Try to buy more than we can afford
        trade = self.p.buy(d, 1000.00, 1000)  # 1M CNY, only have 100k
        self.assertIsNone(trade)  # can't afford
        self.assertEqual(self.p.cash, 100_000)  # unchanged

    def test_equity_curve(self):
        d = date(2024, 1, 2)
        self.p.buy(d, 10.00, 1000)
        self.assertEqual(self.p.position, 1000)

        d2 = date(2024, 1, 5)
        eq = self.p.mark_to_market(d2, 12.00)
        # cash = 100000 - 10000 - 5 = 89995
        # equity = 89995 + 1000*12 = 101995
        self.assertAlmostEqual(eq, 100_000 - 10000 - 5 + 12000)
        self.assertEqual(len(self.p.equity_curve), 1)

    def test_min_commission(self):
        d = date(2024, 1, 2)
        # Very small trade: 100 shares at 5 = 500 CNY
        # Commission would be 500*0.0003=0.15, but minimum is 5
        trade = self.p.buy(d, 5.00, 100)
        self.assertAlmostEqual(trade.commission, 5.0)

    def test_avg_cost_weighted(self):
        d1 = date(2024, 1, 2)
        self.p.buy(d1, 10.00, 1000)  # avg_cost = 10.0
        d2 = date(2024, 1, 5)
        self.p.buy(d2, 12.00, 500)   # avg_cost = (10000 + 6000) / 1500 = 10.667
        self.assertAlmostEqual(self.p.avg_cost, 16000.0 / 1500.0)


if __name__ == "__main__":
    unittest.main()
