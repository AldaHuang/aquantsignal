"""Shared helpers: currency formatting, retry decorator."""

import time
import functools


def format_cny(value):
    """Format a number as CNY: 10000 → ¥1.00万."""
    if abs(value) >= 1e8:
        return f"¥{value/1e8:.2f}亿"
    if abs(value) >= 1e4:
        return f"¥{value/1e4:.2f}万"
    return f"¥{value:,.2f}"


def format_pct(value):
    """Format as percentage string: 0.152 → +15.20%."""
    return f"{value*100:+.2f}%"


def retry(max_attempts=3, delay=1.0, backoff=2.0):
    """Decorator: retry a function on exception with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            d = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    if attempt == max_attempts:
                        raise
                    time.sleep(d)
                    d *= backoff
        return wrapper
    return decorator
