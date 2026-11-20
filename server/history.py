import time
from . import binance

async def backfill(fp, feed, sym, minutes=45, max_calls=14):
    """Fill footprint history for a viewed pair from REST aggTrades (pages backwards from the first live trade)."""
    a0 = feed.first_id.get(sym)
    if a0 is None or sym in feed.hist: return False
    feed.hist.add(sym); stop, end, n = (time.time() - minutes * 60) * 1000, a0 - 1, 0
    while end >= 0 and n < max_calls and binance.weight() < 1500:
        start = max(0, end - 999)
        try: rows = await binance.agg_trades(sym, start, end - start + 1)
        except Exception: break
        n += 1
        if not rows: break
        for r in rows:
            if r["a"] <= end: fp.add(sym, float(r["p"]), float(r["q"]), r["m"], r["T"])
        if rows[0]["T"] < stop or start == 0: break
        end = start - 1
    return n > 0
