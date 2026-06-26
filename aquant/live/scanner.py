"""Signal scanner: run strategy across a list of stocks, output buy/sell signals."""

import pandas as pd
import logging

from aquant.backtest.engine import BacktestEngine
from aquant.data.feed import DataFeed

log = logging.getLogger(__name__)


class ScanResult:
    """One stock's scan output."""
    __slots__ = ("symbol", "name", "signal", "price", "date", "strategy")

    def __init__(self, symbol, name, signal, price, date, strategy):
        self.symbol = symbol
        self.name = name
        self.signal = signal    # "BUY", "SELL", "HOLD", "N/A"
        self.price = price
        self.date = date
        self.strategy = strategy

    def __repr__(self):
        return (f"ScanResult({self.symbol} {self.name} "
                f"{self.signal}@{self.price} {self.date})")


class SignalScanner:
    """Scan multiple stocks with a strategy, return actionable signals.

    Usage:
        feed = DataFeed()
        scanner = SignalScanner(MaCross, feed, fast=5, slow=20)
        results = scanner.scan(["000001", "600519"])
        for r in results:
            print(f"{r.symbol} {r.name}: {r.signal} at {r.price}")
    """

    def __init__(self, strategy_cls, data_feed=None, **params):
        self.strategy_cls = strategy_cls
        self.feed = data_feed or DataFeed()
        self.params = params

    def scan(self, symbols=None, lookback="2020-01-01"):
        """Scan a list of symbols. If symbols is None, use all cached.

        Returns list of ScanResult, sorted: BUY first, then SELL, then HOLD.
        """
        if symbols is None:
            symbols = self.feed.cache.get_symbols()
        if not symbols:
            log.warning("No symbols to scan")
            return []

        results = []
        for symbol in symbols:
            try:
                result = self._scan_one(symbol, lookback)
                if result:
                    results.append(result)
            except Exception as e:
                log.warning("Scan error for %s: %s", symbol, e)

        # Sort: BUY > SELL > HOLD
        order = {"BUY": 0, "SELL": 1, "HOLD": 2, "N/A": 3}
        results.sort(key=lambda r: order.get(r.signal, 3))
        return results

    def _scan_one(self, symbol, lookback="2020-01-01"):
        """Run strategy on one symbol, extract last signal."""
        from aquant.data.symbols import normalize
        symbol = normalize(symbol)

        # Load data
        try:
            df = self.feed.get(symbol, start=lookback)
        except Exception:
            return None

        if df is None or len(df) < 50:
            return None

        # Suppress "insufficient cash" noise during scan
        import logging
        logging.getLogger("aquant.strategy.base").setLevel(logging.ERROR)

        # Run backtest
        engine = BacktestEngine(initial_cash=10_000)
        engine.add_data(df, symbol=symbol)
        engine.add_strategy(self.strategy_cls, **self.params)

        try:
            result = engine.run()
        except Exception:
            return None

        # Determine signal from the last bar
        signal, sig_price, sig_date = self._extract_signal(
            result.df, result.trades, symbol
        )

        # Get stock name (from realtime if available)
        name = self._lookup_name(symbol)

        return ScanResult(symbol, name, signal, sig_price, sig_date,
                          self.strategy_cls.__name__)

    def _extract_signal(self, df, trades, symbol):
        """Determine current signal from backtest result.

        Returns (signal: str, price: float, date: str).
        """
        last_bar = df.iloc[-1]
        last_date = str(df.index[-1].date()) if len(df) > 0 else "?"
        last_price = float(last_bar["close"])

        # Method 1: check if strategy left a _cross column
        if "_cross" in df.columns:
            recent = df["_cross"].dropna()
            if len(recent) > 0:
                last_cross = int(recent.iloc[-1])
                cross_date = str(recent.index[-1].date())
                if last_cross == 1:
                    return ("BUY", last_price, cross_date)
                elif last_cross == -1:
                    return ("SELL", last_price, cross_date)

        # Method 2: check trades for most recent action
        if trades:
            last_trade = trades[-1]
            trade_date = str(last_trade.date)[:10] if last_trade.date else "?"
            if last_trade.side == "buy":
                return ("BUY", last_price, trade_date)
            elif last_trade.side == "sell":
                return ("SELL", last_price, trade_date)

        # Method 3: check position
        if "equity" in df.columns:
            eq = df["equity"].iloc[-1]
            eq_prev = df["equity"].iloc[-2] if len(df) > 1 else eq
            # If equity differs from initial, position was taken at some point
            # but we can't determine current direction → HOLD

        return ("HOLD", last_price, last_date)

    def _lookup_name(self, symbol):
        """Try to get stock name from Sina API or return symbol."""
        try:
            import json, urllib.request, ssl
            from aquant.data.feed import _ssl_context
            from aquant.data.symbols import is_sh
            prefix = "sh" if is_sh(symbol) else "sz"
            url = (
                "https://hq.sinajs.cn/list=" + prefix + symbol
            )
            req = urllib.request.Request(url, headers={
                "Referer": "https://finance.sina.com.cn/",
            })
            resp = urllib.request.urlopen(req, timeout=5, context=_ssl_context())
            text = resp.read().decode("gbk")
            # Format: var hq_str_sh000001="name,open,close,..."
            if '="' in text:
                name = text.split('="')[1].split(",")[0]
                if name and len(name) < 20:
                    return name
        except Exception:
            pass
        return symbol

    def to_dataframe(self, results):
        """Convert scan results to a printable DataFrame."""
        rows = []
        for r in results:
            rows.append({
                "代码": r.symbol,
                "名称": r.name,
                "信号": r.signal,
                "现价": f"{r.price:.2f}",
                "日期": r.date,
            })
        return pd.DataFrame(rows)


def scan_watchlist(strategy_cls, watchlist, **params):
    """Convenience: scan a predefined watchlist.

    watchlist can be:
      - a list of stock codes: ["000001", "600519"]
      - a path to a text file (one code per line)
      - the string "cached" to scan all cached symbols
    """
    feed = DataFeed()

    if isinstance(watchlist, str):
        if watchlist == "cached":
            symbols = feed.cache.get_symbols()
        else:
            # File path
            with open(watchlist) as f:
                symbols = [line.strip().split("#")[0].strip()
                          for line in f if line.strip() and not line.startswith("#")]
    else:
        symbols = watchlist

    scanner = SignalScanner(strategy_cls, feed, **params)
    return scanner.scan(symbols)
