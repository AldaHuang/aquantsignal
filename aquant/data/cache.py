"""SQLite cache for daily OHLCV data, keyed by (symbol, adjust)."""

import sqlite3
import pandas as pd
from datetime import date


SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_kline (
    symbol      TEXT NOT NULL,
    date        TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    amplitude   REAL,
    pct_change  REAL,
    turnover    REAL,
    adjust      TEXT NOT NULL DEFAULT 'qfq',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, date, adjust)
);

CREATE INDEX IF NOT EXISTS idx_kline_symbol_date
    ON daily_kline(symbol, date);

CREATE INDEX IF NOT EXISTS idx_kline_updated
    ON daily_kline(symbol, adjust, updated_at);
"""

COLUMNS = ["date", "open", "high", "low", "close", "volume",
           "amount", "amplitude", "pct_change", "turnover"]


class KlineCache:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # ── read ──────────────────────────────────────────────
    def get(self, symbol, start=None, end=None, adjust="qfq"):
        """Return cached OHLCV DataFrame, or None if no data."""
        where = "symbol = ? AND adjust = ?"
        params = [symbol, adjust]

        if start:
            where += " AND date >= ?"
            params.append(str(start))
        if end:
            where += " AND date <= ?"
            params.append(str(end))

        sql = f"SELECT {', '.join(COLUMNS)} FROM daily_kline WHERE {where} ORDER BY date"
        try:
            with self._connect() as conn:
                df = pd.read_sql_query(sql, conn, params=params, parse_dates=["date"])
        except Exception:
            return None

        if df.empty:
            return None
        df.set_index("date", inplace=True)
        return df

    # ── write ──────────────────────────────────────────────
    def put(self, symbol, adjust, df):
        """Upsert rows from DataFrame. Columns must match COLUMNS."""
        df = df.reset_index() if df.index.name == "date" else df.copy()
        # Keep only columns we know
        keep = [c for c in COLUMNS if c in df.columns]
        df = df[keep].copy()
        df["symbol"] = symbol
        df["adjust"] = adjust
        df["date"] = df["date"].astype(str)

        with self._connect() as conn:
            cols = list(df.columns)
            placeholders = ", ".join([f":{c}" for c in cols])
            updates = ", ".join([
                f"{c}=excluded.{c}" for c in cols
                if c not in ("symbol", "date", "adjust")
            ])
            sql = (
                f"INSERT INTO daily_kline ({', '.join(cols)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(symbol, date, adjust) DO UPDATE SET {updates}, "
                f"updated_at=datetime('now')"
            )
            conn.executemany(sql, df.to_dict("records"))

    # ── info ──────────────────────────────────────────────
    def get_symbols(self):
        """Return list of cached symbols."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM daily_kline ORDER BY symbol"
            ).fetchall()
        return [r[0] for r in rows]

    def get_date_range(self, symbol, adjust="qfq"):
        """Return (min_date, max_date) for a symbol, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MIN(date), MAX(date) FROM daily_kline "
                "WHERE symbol=? AND adjust=?",
                (symbol, adjust),
            ).fetchone()
        if row and row[0]:
            return (row[0], row[1])
        return None

    def is_stale(self, symbol, max_age_days=1, adjust="qfq"):
        """Check if cached data hasn't been updated recently."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(updated_at) FROM daily_kline WHERE symbol=? AND adjust=?",
                (symbol, adjust),
            ).fetchone()
        if not row or not row[0]:
            return True
        # updated_at is ISO format, compare naively
        today = str(date.today())
        return row[0] < today

    def stats(self):
        """Return summary DataFrame of cached data."""
        with self._connect() as conn:
            df = pd.read_sql_query(
                "SELECT symbol, adjust, COUNT(*) AS rows, "
                "MIN(date) AS first_date, MAX(date) AS last_date, "
                "MAX(updated_at) AS last_updated "
                "FROM daily_kline GROUP BY symbol, adjust ORDER BY symbol",
                conn,
            )
        return df

    def delete(self, symbol, adjust=None):
        """Delete cached data for a symbol/adj combo."""
        with self._connect() as conn:
            if adjust:
                conn.execute(
                    "DELETE FROM daily_kline WHERE symbol=? AND adjust=?",
                    (symbol, adjust),
                )
            else:
                conn.execute("DELETE FROM daily_kline WHERE symbol=?", (symbol,))
