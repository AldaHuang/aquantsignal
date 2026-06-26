"""A-share symbol utilities: normalization, exchange detection, filtering."""

import re

# A-share code ranges
# Shanghai: 60xxxx (main), 68xxxx (STAR/科创板)
# Shenzhen: 00xxxx (main), 30xxxx (ChiNext/创业板)


def normalize(code):
    """Normalize a stock code to 6-digit string. '1' -> '000001'."""
    code = str(code).strip().zfill(6)
    if not re.match(r"^\d{6}$", code):
        raise ValueError(f"Invalid stock code: {code}")
    return code


def is_sh(code):
    """True if Shanghai (60xxxx, 68xxxx)."""
    code = normalize(code)
    return code.startswith("60") or code.startswith("68")


def is_sz(code):
    """True if Shenzhen (00xxxx, 30xxxx)."""
    code = normalize(code)
    return code.startswith("00") or code.startswith("30")


def market_prefix(code):
    """Return 'sh' or 'sz' for a code."""
    return "sh" if is_sh(code) else "sz"


def has_st_prefix(name):
    """Check if stock name contains ST/*ST risk warning marker."""
    if not name:
        return False
    return "ST" in str(name).upper().split()[0] if str(name).strip() else False


NO_TRADE_KEYWORDS = ["退市", "终止上市", "暂停上市"]


def is_suspended(name):
    """Check if the stock appears suspended or delisted by its name."""
    if not name:
        return False
    name = str(name)
    return any(kw in name for kw in NO_TRADE_KEYWORDS)
