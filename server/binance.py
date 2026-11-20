import asyncio, time, httpx
from .config import REST, TFS

class BinanceError(Exception):
    def __init__(self, msg, code=502): super().__init__(msg); self.code = code

http = httpx.AsyncClient(base_url=REST, timeout=httpx.Timeout(7, connect=4), headers={"User-Agent": "orderflow-terminal"})
_sem = asyncio.Semaphore(8); W = {"used": 0, "t": 0.0}
def weight(): return W["used"] if time.time() - W["t"] < 60 else 0   # Binance used-weight (1m window)

async def _get(path, **params):
    err = BinanceError("Binance unreachable")
    for i in range(2):
        try:
            async with _sem: r = await http.get(path, params=params)
            w = r.headers.get("x-mbx-used-weight-1m")
            if w: W["used"], W["t"] = int(w), time.time()
            if r.status_code == 200: return r.json()
            if r.status_code in (418, 429): raise BinanceError("Binance rate limit hit - wait a minute", 429)
            if r.status_code in (403, 451): raise BinanceError(f"Binance blocks this server's region (HTTP {r.status_code}). Use a non-US VPS or set BINANCE_REST/BINANCE_WS.", 451)
            if r.status_code == 400: raise BinanceError("Unknown symbol", 400)
            err = BinanceError(f"Binance HTTP {r.status_code}")
        except BinanceError: raise
        except Exception as e: err = BinanceError(f"Cannot reach Binance: {type(e).__name__}")
        await asyncio.sleep(0.3 * (i + 1))
    raise err

_kc, _fl = {}, {}
async def klines(sym, tf, limit=500):
    k = (sym, tf); c = _kc.get(k); ttl = 5 if TFS[tf] <= 300 else 15
    if c and time.time() - c[0] < ttl: return c[1]
    if k in _fl: return await _fl[k]
    async def go():
        j = await _get("/fapi/v1/klines", symbol=sym, interval=tf, limit=limit)
        d = [[x[0] // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), float(x[9])] for x in j]
        if len(_kc) > 300: _kc.clear()
        _kc[k] = (time.time(), d); return d   # t,o,h,l,c,vol,takerBuyVol
    t = _fl[k] = asyncio.ensure_future(go())
    try: return await t
    finally: _fl.pop(k, None)

async def agg_trades(sym, from_id, limit=1000): return await _get("/fapi/v1/aggTrades", symbol=sym, fromId=from_id, limit=limit)
async def last_price(sym): return float((await _get("/fapi/v1/ticker/price", symbol=sym))["price"])

_sy = (0, [])
async def symbols():
    global _sy
    if _sy[1] and time.time() - _sy[0] < 3600: return _sy[1]
    j = await _get("/fapi/v1/exchangeInfo")
    _sy = (time.time(), sorted(s["symbol"] for s in j["symbols"] if s["quoteAsset"] == "USDT" and s["contractType"] == "PERPETUAL" and s["status"] == "TRADING"))
    return _sy[1]
