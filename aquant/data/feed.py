"""DataFeed: cache-first data provider for A-share daily data.

Primary source: Sina Finance API (free, no API key needed).
Secondary source: AKShare / EastMoney (may be blocked on some networks).
"""

import json
import ssl
import urllib.request
import pandas as pd
from pathlib import Path

from aquant.config import load as load_config
from aquant.data.cache import KlineCache, COLUMNS
from aquant.data.symbols import normalize, is_sh
from aquant.utils import retry


def _ssl_context():
    """Create SSL context using certifi certificates if available."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class DataFeed:
    """Primary data interface. Checks SQLite cache first, fetches from
    Sina Finance API on miss. Uses 前复权 (qfq) by default."""

    SINA_URL = (
        "https://money.finance.sina.com.cn/quotes_service/api/"
        "json_v2.php/CN_MarketData.getKLineData"
    )

    def __init__(self, adjust=None, cache_dir=None):
        cfg = load_config()
        self.adjust = adjust or cfg["data"]["default_adjust"]
        self.cache_dir = Path(cache_dir or cfg["data"]["cache_dir"])
        self.cache_dir = Path(self.cache_dir).expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = KlineCache(self.cache_dir / "aquant.db")

    # ── main data method ──────────────────────────────────
    def get(self, symbol, start=None, end=None, force_refresh=False):
        """Return OHLCV DataFrame for one symbol.

        Columns: date(index), open, high, low, close, volume, amount,
                 amplitude, pct_change, turnover
        """
        symbol = normalize(symbol)

        # Try cache first
        if not force_refresh:
            cached = self.cache.get(symbol, start, end, self.adjust)
            if cached is not None and len(cached) > 0:
                if start is None or cached.index.min() <= pd.Timestamp(start):
                    if end is None or cached.index.max() >= pd.Timestamp(end):
                        return cached

        # Fetch from Sina
        df = self._fetch_sina(symbol)
        if df is None or df.empty:
            # Fallback: try AKShare
            try:
                df = self._fetch_akshare(symbol)
            except Exception:
                pass

        if df is None or df.empty:
            raise ValueError(f"No data returned for {symbol}")

        # Cache
        self.cache.put(symbol, self.adjust, df)

        # Slice to requested range
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]

        return df

    # ── Sina Finance API ───────────────────────────────────
    def _sina_symbol(self, symbol):
        """Convert 6-digit code to Sina format: sh000001 or sz000001."""
        return f"sh{symbol}" if is_sh(symbol) else f"sz{symbol}"

    @retry(max_attempts=3, delay=1.5)
    def _fetch_sina(self, symbol):
        """Download from Sina Finance API."""
        sina_sym = self._sina_symbol(symbol)
        url = f"{self.SINA_URL}?symbol={sina_sym}&scale=240&ma=no&datalen=5000"

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Referer": "https://finance.sina.com.cn/",
        })
        resp = urllib.request.urlopen(req, timeout=15, context=_ssl_context())
        raw = json.loads(resp.read().decode("gbk"))

        if not raw:
            return None

        df = pd.DataFrame(raw)
        df.rename(columns={
            "day": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
        }, inplace=True)

        keep = [c for c in ["date", "open", "high", "low", "close", "volume"]
                if c in df.columns]
        df = df[keep].copy()

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df.dropna(subset=["date"], inplace=True)
        df.set_index("date", inplace=True)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Add derived columns for cache compatibility
        if "amount" not in df.columns:
            df["amount"] = 0.0
        if "amplitude" not in df.columns:
            df["amplitude"] = 0.0
        if "pct_change" not in df.columns:
            df["pct_change"] = 0.0
        if "turnover" not in df.columns:
            df["turnover"] = 0.0

        return df.sort_index()

    # ── AKShare fallback ───────────────────────────────────
    def _fetch_akshare(self, symbol):
        """Fallback: download from AKShare / EastMoney."""
        import akshare as ak

        raw = ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date="19900101", end_date="20991231",
            adjust=self.adjust,
        )
        if raw is None or raw.empty:
            return None

        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "振幅": "amplitude",
            "涨跌幅": "pct_change", "换手率": "turnover",
        }
        df = raw.rename(columns=col_map)
        keep = [c for c in COLUMNS if c in df.columns]
        df = df[keep].copy()

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df.dropna(subset=["date"], inplace=True)
        df.set_index("date", inplace=True)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return df.sort_index()

    # ── convenience ────────────────────────────────────────
    def get_realtime(self):
        """Return live A-share snapshot from AKShare (may fail on some networks)."""
        try:
            import akshare as ak
            return ak.stock_zh_a_spot_em()
        except Exception:
            return None

    def get_index(self, code="000300", start=None, end=None):
        """Get index OHLCV. 000300=沪深300, 000001=上证指数."""
        code = normalize(code)
        # Sina index API
        sina_map = {"000001": "sh000001", "000300": "sh000300",
                     "399001": "sz399001", "399006": "sz399006"}
        sina_sym = sina_map.get(code, self._sina_symbol(code))

        url = f"{self.SINA_URL}?symbol={sina_sym}&scale=240&ma=no&datalen=5000"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/",
        })
        try:
            resp = urllib.request.urlopen(req, timeout=15, context=_ssl_context())
            raw = json.loads(resp.read().decode("gbk"))
        except Exception:
            return None

        if not raw:
            return None

        df = pd.DataFrame(raw)
        df.rename(columns={
            "day": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
        }, inplace=True)
        keep = [c for c in ["date", "open", "high", "low", "close", "volume"]
                if c in df.columns]
        df = df[keep].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df.set_index("date", inplace=True)
        for c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
        return df.sort_index()

    def list_cache(self):
        """Return summary of cached data."""
        return self.cache.stats()

    def get_symbol_list(self):
        """Return list of all A-share symbols."""
        spot = self.get_realtime()
        if spot is not None and "代码" in spot.columns:
            return spot["代码"].tolist()
        return []
