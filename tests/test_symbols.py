"""Test stock code normalization and exchange detection."""
import unittest
from aquant.data.symbols import normalize, is_sh, is_sz, has_st_prefix


class TestSymbols(unittest.TestCase):
    def test_normalize_full_code(self):
        self.assertEqual(normalize("000001"), "000001")
        self.assertEqual(normalize("600519"), "600519")

    def test_normalize_short_code(self):
        self.assertEqual(normalize("1"), "000001")
        self.assertEqual(normalize("639"), "000639")

    def test_normalize_int(self):
        self.assertEqual(normalize(1), "000001")
        self.assertEqual(normalize(600519), "600519")

    def test_normalize_preserves_valid(self):
        self.assertEqual(normalize("000001"), "000001")

    def test_is_sh(self):
        self.assertTrue(is_sh("600000"))   # Shanghai main
        self.assertTrue(is_sh("688001"))   # STAR market
        self.assertFalse(is_sh("000001"))  # Shenzhen
        self.assertFalse(is_sh("300750"))  # ChiNext

    def test_is_sz(self):
        self.assertTrue(is_sz("000001"))   # Shenzhen main
        self.assertTrue(is_sz("300750"))   # ChiNext
        self.assertFalse(is_sz("600000"))  # Shanghai

    def test_st_filter(self):
        self.assertTrue(has_st_prefix("ST平安"))
        self.assertTrue(has_st_prefix("*ST康美"))
        self.assertFalse(has_st_prefix("平安银行"))
        self.assertFalse(has_st_prefix(""))


if __name__ == "__main__":
    unittest.main()
