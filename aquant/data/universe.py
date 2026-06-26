"""Auto stock discovery: fetch all A-shares, filter by quality, download data."""

import json
import ssl
import urllib.request
import time
import logging

log = logging.getLogger(__name__)

# Chinese stock boards
# sh60xxxx - Shanghai Main
# sh68xxxx - Shanghai STAR (科创板)
# sz00xxxx - Shenzhen Main
# sz30xxxx - Shenzhen ChiNext (创业板)
# bjxxxxxx - Beijing Stock Exchange (北交所) — illiquid, skip by default


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_all_stocks(max_pages=60):
    """Fetch all A-share stocks with snapshot data from Sina.

    Returns list of dicts with keys: code, name, price, volume, amount, mktcap, ...
    """
    ctx = _ssl_ctx()
    all_stocks = []
    page_size = 100

    for page in range(1, max_pages + 1):
        url = (
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
            f"json_v2.php/Market_Center.getHQNodeData?page={page}"
            f"&num={page_size}&sort=symbol&asc=1&node=hs_a"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://vip.stock.finance.sina.com.cn/",
        })
        try:
            resp = urllib.request.urlopen(req, timeout=10, context=ctx)
            text = resp.read().decode("gbk")
            data = json.loads(text)
        except Exception as e:
            log.warning("Stock list page %d failed: %s", page, e)
            time.sleep(1)
            continue

        if not data:
            break  # no more data

        for item in data:
            all_stocks.append({
                "code": item["code"],
                "name": item["name"],
                "price": float(item.get("trade", 0) or 0),
                "volume": int(float(item.get("volume", 0) or 0)),
                "amount": float(item.get("amount", 0) or 0),
                "mktcap": float(item.get("mktcap", 0) or 0),
                "turnover": float(item.get("turnoverratio", 0) or 0),
                "pe": float(item.get("per", 0) or 0),
                "pb": float(item.get("pb", 0) or 0),
                "change_pct": float(item.get("changepercent", 0) or 0),
            })

        # If this page has fewer than page_size items, we're done
        if len(data) < page_size:
            break

        time.sleep(0.1)  # be polite

    log.info("Fetched %d stocks from market center", len(all_stocks))
    return all_stocks


def filter_stocks(stocks, max_price=100, min_volume=500_000,
                  min_mktcap=100_000, exclude_bj=True,
                  exclude_star=True, exclude_st=True, top_n=100):
    """Filter the stock universe.

    Args:
        max_price: max stock price (CNY)
        min_volume: min daily volume in shares
        min_mktcap: min market cap in 万元 (100_000 = ~1B CNY)
        exclude_bj: exclude Beijing Exchange (8xxxxx/9xxxxx)
        exclude_star: exclude STAR Market 科创板 (68xxxx)
        exclude_st: exclude ST stocks
        top_n: return top N by trading amount

    Note: Sina API returns mktcap in 万元 (ten-thousands CNY).
    """
    result = []
    for s in stocks:
        code = s["code"]
        name = s.get("name", "")
        price = s.get("price", 0)

        # Beijing Exchange: 8xxxxx, 9xxxxx
        if exclude_bj and code.startswith(("8", "9")):
            continue

        # STAR Market (科创板): 68xxxx
        if exclude_star and code.startswith("68"):
            continue

        # ST filter
        if exclude_st and ("ST" in name or "*ST" in name):
            continue

        # Price filter
        if price <= 0 or price > max_price:
            continue

        # Volume filter
        if s.get("volume", 0) < min_volume:
            continue

        # Market cap filter
        if s.get("mktcap", 0) < min_mktcap:
            continue

        result.append(s)

    # Sort by trading amount (most liquid first) as pre-filter for Sharpe ranking
    result.sort(key=lambda x: x.get("amount", 0), reverse=True)
    return result[:top_n]


def _backtest_one(symbol, feed):
    """Run all 3 strategies on one stock, return best Sharpe.
    Returns (best_sharpe, best_strategy) or (-999, None).
    """
    import logging
    from aquant.backtest.engine import BacktestEngine
    from aquant.strategy.examples.ma_cross import MaCross
    from aquant.strategy.examples.turtle import Turtle
    from aquant.strategy.examples.mean_revert import MeanRevert

    # Suppress noise during mass backtesting
    logging.getLogger("aquant.strategy.base").setLevel(logging.ERROR)

    strategies = [("均线", MaCross), ("海龟", Turtle), ("布林", MeanRevert)]
    best_sharpe = -999
    best_name = None

    try:
        df = feed.get(symbol, start="2022-01-01")
    except Exception:
        return best_sharpe, best_name

    if df is None or len(df) < 100:
        return best_sharpe, best_name

    for sname, scls in strategies:
        try:
            engine = BacktestEngine(initial_cash=10_000)
            engine.add_data(df, symbol=symbol)
            engine.add_strategy(scls)
            result = engine.run()
            sharpe = result.metrics.get("sharpe_ratio", -999)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_name = sname
        except Exception:
            pass

    return best_sharpe, best_name


def rank_by_sharpe(stocks, feed, top_n=30):
    """Download data, backtest all strategies, rank by best Sharpe.

    Returns list of (code, name, price, sharpe, strategy) sorted by Sharpe desc.
    """
    import sys

    scored = []
    for i, s in enumerate(stocks):
        code = s["code"]
        name = s.get("name", "")
        price = s.get("price", 0)

        sys.stdout.write(f"\r  Backtesting: {i+1}/{len(stocks)} {code} {name}...")
        sys.stdout.flush()

        sharpe, strategy = _backtest_one(code, feed)
        if sharpe > -900:
            scored.append((code, name, price, sharpe, strategy))

    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()

    scored.sort(key=lambda x: x[3], reverse=True)
    return scored[:top_n]


def build_universe(max_price=100, top_n=20, exclude_star=True,
                   pre_filter=300):
    """One-stop: fetch → liquidity filter → Sharpe rank → top N.

    Pipeline:
      1. Fetch all A-shares (5000+)
      2. Basic filters + sort by liquidity, keep top `pre_filter` (e.g. 300)
      3. Backtest all 3 strategies on those 300
      4. Rank by best historical Sharpe across strategies
      5. Return top N stocks ready for recommendation

    Returns list of (code, name, price) tuples.
    """
    log.info("Step 1/3: Fetching A-share universe...")
    all_stocks = fetch_all_stocks()

    log.info("Step 2/3: Liquidity pre-filter (top %d, price<%.0f)...",
             pre_filter, max_price)
    candidates = filter_stocks(
        all_stocks, max_price=max_price, top_n=pre_filter,
        exclude_star=exclude_star,
    )
    log.info("Candidates: %d stocks (most liquid, filtered)", len(candidates))

    if not candidates:
        log.warning("No stocks passed basic filters")
        return []

    from aquant.data.feed import DataFeed
    feed = DataFeed()

    log.info("Step 3/3: Ranking by Sharpe (%d stocks × 3 strategies)...",
             len(candidates))
    ranked = rank_by_sharpe(candidates, feed, top_n=top_n)

    result = [(code, name, price) for code, name, price, _, _ in ranked]

    # Print ranking summary
    log.info("Top picks by Sharpe:")
    for i, (code, name, price, sharpe, strategy) in enumerate(ranked[:10]):
        bar = "█" * min(5, max(1, int((sharpe + 1) * 2)))
        log.info("  %2d. %s %s  ¥%.2f  Sharpe=%.2f [%s] %s",
                 i + 1, code, name, price, sharpe, strategy, bar)

    log.info("Universe: %d stocks selected", len(result))
    return result
