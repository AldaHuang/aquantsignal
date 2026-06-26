"""Test SQLite cache: write, read, upsert, list, delete."""
import unittest
import tempfile
import os
import pandas as pd
import numpy as np
from aquant.data.cache import KlineCache


class TestKlineCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.cache = KlineCache(self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_cache_returns_none(self):
        result = self.cache.get("000001")
        self.assertIsNone(result)

    def test_put_and_get(self):
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        df = pd.DataFrame({
            "date": dates,
            "open": [10.0] * 5,
            "high": [10.5] * 5,
            "low": [9.5] * 5,
            "close": [10.2] * 5,
            "volume": [1e7] * 5,
            "amount": [1e8] * 5,
            "amplitude": [1.0] * 5,
            "pct_change": [0.1] * 5,
            "turnover": [0.5] * 5,
        })
        self.cache.put("000001", "qfq", df)

        result = self.cache.get("000001")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 5)
        self.assertIn("close", result.columns)

    def test_get_with_date_range(self):
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        df = pd.DataFrame({
            "date": dates,
            "open": np.arange(10, 20, dtype=float),
            "high": np.arange(10.5, 20.5, dtype=float),
            "low": np.arange(9.5, 19.5, dtype=float),
            "close": np.arange(10.2, 20.2, dtype=float),
            "volume": [1e7] * 10,
            "amount": [1e8] * 10,
        })
        self.cache.put("000001", "qfq", df)

        # Get subset
        result = self.cache.get("000001", start="2024-01-03", end="2024-01-07")
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), 5)

    def test_upsert_does_not_duplicate(self):
        dates = pd.date_range("2024-01-01", periods=3, freq="B")
        df = pd.DataFrame({
            "date": dates,
            "open": [10.0] * 3, "high": [10.5] * 3,
            "low": [9.5] * 3, "close": [10.2] * 3,
            "volume": [1e7] * 3, "amount": [1e8] * 3,
        })
        self.cache.put("000001", "qfq", df)
        self.cache.put("000001", "qfq", df)  # put again
        result = self.cache.get("000001")
        self.assertEqual(len(result), 3)  # no duplicates

    def test_get_symbols(self):
        dates = pd.date_range("2024-01-01", periods=2, freq="B")
        df = pd.DataFrame({
            "date": dates, "open": [10.0] * 2, "high": [10.5] * 2,
            "low": [9.5] * 2, "close": [10.2] * 2,
            "volume": [1e7] * 2, "amount": [1e8] * 2,
        })
        self.cache.put("000001", "qfq", df)
        self.cache.put("600519", "qfq", df)

        symbols = self.cache.get_symbols()
        self.assertIn("000001", symbols)
        self.assertIn("600519", symbols)

    def test_date_range(self):
        dates = pd.date_range("2024-06-01", periods=5, freq="B")
        df = pd.DataFrame({
            "date": dates, "open": [10.0] * 5, "high": [10.5] * 5,
            "low": [9.5] * 5, "close": [10.2] * 5,
            "volume": [1e7] * 5, "amount": [1e8] * 5,
        })
        self.cache.put("000001", "qfq", df)
        dr = self.cache.get_date_range("000001")
        self.assertIsNotNone(dr)
        self.assertIn("2024-06", dr[0])

    def test_delete(self):
        dates = pd.date_range("2024-01-01", periods=3, freq="B")
        df = pd.DataFrame({
            "date": dates, "open": [10.0] * 3, "high": [10.5] * 3,
            "low": [9.5] * 3, "close": [10.2] * 3,
            "volume": [1e7] * 3, "amount": [1e8] * 3,
        })
        self.cache.put("000001", "qfq", df)
        self.cache.delete("000001")
        result = self.cache.get("000001")
        self.assertIsNone(result)

    def test_stats(self):
        dates = pd.date_range("2024-01-01", periods=3, freq="B")
        df = pd.DataFrame({
            "date": dates, "open": [10.0] * 3, "high": [10.5] * 3,
            "low": [9.5] * 3, "close": [10.2] * 3,
            "volume": [1e7] * 3, "amount": [1e8] * 3,
        })
        self.cache.put("000001", "qfq", df)
        stats = self.cache.stats()
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats.iloc[0]["rows"], 3)


if __name__ == "__main__":
    unittest.main()
