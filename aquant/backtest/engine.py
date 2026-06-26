"""BacktestEngine: orchestrates the event loop, fills orders, returns results."""

import logging
import pandas as pd
import numpy as np

from aquant.config import load as load_config
from aquant.backtest.portfolio import Portfolio, Trade
from aquant.backtest import metrics

log = logging.getLogger(__name__)


class BacktestResult:
    """Holds the output of a backtest run."""

    def __init__(self, df, trades, initial_cash):
        self.df = df               # OHLCV + equity + signals
        self.trades = trades       # list of Trade
        self.initial_cash = initial_cash

        equity = df["equity"].dropna().tolist()
        self.metrics = metrics.compute_all(equity, trades)

    def summary(self):
        """Return a formatted text summary."""
        trading_days = len(self.df)
        start = self.df.index[0].strftime("%Y-%m-%d") if len(self.df) > 0 else "?"
        end = self.df.index[-1].strftime("%Y-%m-%d") if len(self.df) > 0 else "?"
        m = self.metrics

        lines = [
            f"Period:    {start} ~ {end} ({trading_days} trading days)",
            f"",
            f"Initial:   ¥{m['initial']:,.2f}",
            f"Final:     ¥{m['final']:,.2f}",
            f"Return:    {m['total_return']*100:+.2f}%",
            f"Annual:    {m['annual_return']*100:+.2f}%",
            f"Sharpe:    {m['sharpe_ratio']:.2f}",
            f"Max DD:    {m['max_drawdown']*100:.2f}%",
            f"Volatility:{m['volatility']*100:.2f}%",
            f"Calmar:    {m['calmar_ratio']:.2f}",
            f"Win Rate:  {m['win_rate']*100:.1f}%",
            f"Profit Factor: {m['profit_factor']:.2f}",
            f"Trades:    {m['num_trades']}",
        ]
        return "\n".join(lines)

    def plot(self, save_path=None):
        """Generate OHLCV + equity + trade markers chart."""
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        data = self.df
        t_buys = [(t.date, t.price) for t in self.trades if t.side == "buy"]
        t_sells = [(t.date, t.price) for t in self.trades if t.side == "sell"]

        fig, (ax1, ax2, ax3) = plt.subplots(
            3, 1, figsize=(14, 9),
            gridspec_kw={"height_ratios": [3, 2, 1]},
            sharex=True,
        )

        # ── Chart 1: OHLCV + signals ──
        ax1.plot(data.index, data["close"], label="Close", color="black",
                 linewidth=0.8)
        if "ma_fast" in data.columns:
            ax1.plot(data.index, data["ma_fast"], label="MA Fast",
                     color="blue", alpha=0.5, linewidth=0.6)
        if "ma_slow" in data.columns:
            ax1.plot(data.index, data["ma_slow"], label="MA Slow",
                     color="orange", alpha=0.5, linewidth=0.6)

        # Trade markers
        for d, p in t_buys:
            ax1.scatter(d, p, marker="^", color="red", s=80, zorder=5, alpha=0.8)
        for d, p in t_sells:
            ax1.scatter(d, p, marker="v", color="green", s=80, zorder=5, alpha=0.8)

        ax1.set_ylabel("Price (¥)")
        ax1.legend(loc="upper left", fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.set_title("Backtest Result — OHLCV, Indicators, and Trade Signals")

        # ── Chart 2: Equity curve ──
        eq = data["equity"].dropna()
        ax2.plot(eq.index, eq.values, label="Equity", color="navy", linewidth=1.0)
        ax2.axhline(y=self.initial_cash, color="gray", linestyle="--",
                    linewidth=0.5, label="Initial")
        ax2.fill_between(eq.index, eq.values, self.initial_cash,
                         where=(eq.values >= self.initial_cash),
                         alpha=0.1, color="green")
        ax2.fill_between(eq.index, eq.values, self.initial_cash,
                         where=(eq.values < self.initial_cash),
                         alpha=0.1, color="red")
        ax2.set_ylabel("Equity (¥)")
        ax2.legend(loc="upper left", fontsize=8)
        ax2.grid(True, alpha=0.3)

        # ── Chart 3: Drawdown ──
        eq_vals = eq.values
        peak = np.maximum.accumulate(eq_vals)
        drawdown = (peak - eq_vals) / peak * 100
        ax3.fill_between(eq.index, 0, drawdown, color="red", alpha=0.3)
        ax3.set_ylabel("Drawdown %")
        ax3.set_xlabel("Date")
        ax3.grid(True, alpha=0.3)
        ax3.invert_yaxis()

        # Format x-axis
        for ax in (ax1, ax2, ax3):
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
            ax.xaxis.set_major_locator(mdates.YearLocator())

        plt.xticks(rotation=0)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            log.info("Chart saved to %s", save_path)

        plt.show()
        return fig


class BacktestEngine:
    """Orchestrates a single-stock backtest.

    Usage:
        engine = BacktestEngine(initial_cash=100000)
        engine.add_data(df, symbol="000001")
        engine.add_strategy(MaCross, fast=5, slow=20)
        result = engine.run()
        print(result.summary())
        result.plot()
    """

    def __init__(self, initial_cash=None, commission=None, stamp_duty=None,
                 min_commission=None, fill_at=None):
        cfg = load_config()["backtest"]
        self.initial_cash = initial_cash or cfg["initial_cash"]
        self.commission = commission if commission is not None else cfg["commission"]
        self.stamp_duty = stamp_duty if stamp_duty is not None else cfg["stamp_duty"]
        self.min_commission = (min_commission if min_commission is not None
                               else cfg["min_commission"])
        self.fill_at = fill_at or cfg["fill_at"]

        self._data = None
        self._symbol = ""
        self._strategy_cls = None
        self._strategy_params = {}

    def add_data(self, df, symbol="default"):
        """Register price data for one symbol."""
        self._data = df.copy()
        self._symbol = symbol

    def add_strategy(self, strategy_cls, **params):
        """Register strategy class with parameters."""
        self._strategy_cls = strategy_cls
        self._strategy_params = params

    def run(self):
        """Execute the backtest event loop. Returns BacktestResult."""
        if self._data is None or self._data.empty:
            raise ValueError("No data added. Call add_data() first.")
        if self._strategy_cls is None:
            raise ValueError("No strategy added. Call add_strategy() first.")

        df = self._data.copy()
        strategy = self._strategy_cls(**self._strategy_params)
        strategy.data = df
        strategy.symbol = self._symbol

        # ── Step 1: init ──
        strategy.init()

        # ── Step 2: find warmup ──
        warmup = self._find_warmup(df)
        if warmup >= len(df):
            raise ValueError(
                f"Insufficient data: only {len(df)} bars, warmup={warmup}. "
                f"Try a longer date range or a simpler strategy."
            )

        # ── Step 3: event loop ──
        portfolio = Portfolio(
            self.initial_cash, self.commission, self.stamp_duty,
            self.min_commission,
        )

        pending_order = None
        equity_arr = [np.nan] * len(df)
        # Start equity from initial_cash for bars before warmup
        for i in range(warmup):
            equity_arr[i] = float(self.initial_cash)

        for i in range(warmup, len(df)):
            bar = df.iloc[i]
            close_price = float(bar["close"])
            bar_date = df.index[i]

            # Fill pending order at this bar's open
            if pending_order and self.fill_at == "next_open":
                open_price = float(bar["open"])
                self._fill(pending_order, open_price, bar_date, portfolio)
                pending_order = None

            # Mark to market
            portfolio.mark_to_market(bar_date, close_price)

            # Update strategy state
            strategy.cash = portfolio.cash
            strategy.position = portfolio.position
            strategy.position_value = portfolio.position * close_price
            strategy.equity = portfolio.cash + strategy.position_value
            strategy.i = i

            # Call strategy
            try:
                strategy.next(i)
            except Exception as e:
                log.warning("Strategy error at bar %d (%s): %s",
                            i, bar_date, e)

            # Handle new order
            if strategy._pending_order is not None:
                order = strategy._pending_order
                if self.fill_at == "this_close":
                    self._fill(order, close_price, bar_date, portfolio)
                else:
                    pending_order = order
                strategy._pending_order = None

            equity_arr[i] = portfolio.cash + portfolio.position * close_price

        # ── Step 4: finish ──
        strategy.finish()

        # Fill remaining equity NaNs
        for i in range(len(equity_arr)):
            if np.isnan(equity_arr[i]):
                equity_arr[i] = self.initial_cash

        df["equity"] = equity_arr
        return BacktestResult(df, portfolio.trades, self.initial_cash)

    # ── helpers ────────────────────────────────────────────
    def _find_warmup(self, df):
        """First index where all numeric columns are non-NaN."""
        numeric = df.select_dtypes(include="number")
        if numeric.empty:
            return len(df)
        valid = numeric.notna().all(axis=1)
        if not valid.any():
            return len(df)
        # idxmax returns the index label (could be Timestamp); get position
        return int(valid.values.argmax())

    def _fill(self, order, price, date, portfolio):
        """Execute an order at the given price."""
        order.price = price

        if order.side == "buy":
            trade = portfolio.buy(date, price, order.size)
        else:
            trade = portfolio.sell(date, price, order.size)

        if trade:
            order.filled = True
            order.value = trade.value
            order.commission = trade.commission
            order.stamp_duty = trade.stamp_duty
