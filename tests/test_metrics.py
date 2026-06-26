"""Test performance metrics with known values."""
import unittest
import numpy as np
from aquant.backtest.metrics import (
    total_return, annual_return, sharpe_ratio, max_drawdown,
    max_drawdown_duration, win_rate, profit_factor, calmar_ratio,
    compute_all,
)
from aquant.backtest.portfolio import Trade


class TestMetrics(unittest.TestCase):
    def setUp(self):
        # Simple equity curve: 100 -> 110 -> 105 -> 115
        self.equity = [100.0, 110.0, 105.0, 115.0]

    def test_total_return(self):
        self.assertAlmostEqual(total_return(self.equity), 0.15)  # 15%

    def test_total_return_flat(self):
        self.assertEqual(total_return([100.0, 100.0]), 0.0)

    def test_annual_return(self):
        # 15% over 4 bars = (1.15)^(252/3) - 1
        r = annual_return(self.equity, trading_days=252)
        self.assertGreater(r, 0)  # should be huge annualized

    def test_max_drawdown(self):
        # Peak at 110, trough at 105 = 5/110 = 4.55%
        mdd = max_drawdown(self.equity)
        self.assertAlmostEqual(mdd, 5.0 / 110.0)

    def test_max_drawdown_no_decline(self):
        self.assertEqual(max_drawdown([100, 110, 120]), 0.0)

    def test_max_drawdown_duration(self):
        # [100, 98, 95, 97, 100, 105] - underwater for 4 bars
        eq = [100, 98, 95, 97, 100, 105]
        dur = max_drawdown_duration(eq)
        self.assertEqual(dur, 3)

    def test_sharpe_zero_return(self):
        # Flat equity -> Sharpe should be 0
        self.assertEqual(sharpe_ratio([100, 100, 100, 100]), 0.0)

    def test_sharpe_positive(self):
        # Daily returns with decent mean and some variance
        np.random.seed(42)
        eq = [100.0]
        for i in range(252):
            ret = np.random.normal(0.001, 0.01)  # mean 0.1%, std 1%
            eq.append(eq[-1] * (1 + ret))
        s = sharpe_ratio(eq, risk_free=0.0, trading_days=252)
        self.assertGreater(s, 0.5)  # reasonable Sharpe

    def test_win_rate(self):
        trades = [
            Trade(None, "", "buy", 100, 10, 1000, 5, 0),
            Trade(None, "", "sell", 100, 12, 1200, 5, 1.2, net_pnl=200),
            Trade(None, "", "sell", 100, 8, 800, 5, 0.8, net_pnl=-200),
            Trade(None, "", "sell", 100, 11, 1100, 5, 1.1, net_pnl=100),
        ]
        self.assertAlmostEqual(win_rate(trades), 2.0 / 3.0)  # 2 wins out of 3 sells

    def test_profit_factor(self):
        trades = [
            Trade(None, "", "sell", 100, 12, 1200, 5, 1.2, net_pnl=300),
            Trade(None, "", "sell", 100, 8, 800, 5, 0.8, net_pnl=-100),
        ]
        # Gross profit=300, gross loss=100 -> PF=3.0
        self.assertAlmostEqual(profit_factor(trades), 3.0)

    def test_compute_all(self):
        result = compute_all(self.equity, [], trading_days=252)
        self.assertIn("total_return", result)
        self.assertIn("sharpe_ratio", result)
        self.assertIn("max_drawdown", result)
        self.assertIn("win_rate", result)


if __name__ == "__main__":
    unittest.main()
