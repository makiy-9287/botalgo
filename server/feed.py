import asyncio, json, time, websockets
from . import binance
from .config import WSURL

class Feed:
    """Binance USD-M aggTrade feed on the NEW /market endpoint (legacy /stream and /ws were retired 2026-04-23).
    Streams are (un)subscribed live. Falls back to REST last-price polling so the chart never freezes."""
    def __init__(self, on_trade):
        self.on_trade, self.on_first = on_trade, (lambda s: None)
        self.want, self.price, self.ts, self.tt, self.first_id, self.hist = {"btcusdt"}, {}, {}, {}, {}, set()
        self.state, self.error, self.last, self.mode, self.rest_ts = "starting", "", 0.0, 0, 0.0
    def set_symbols(self, syms): self.want = {s.lower() for s in sorted(syms)[:40]} | {"btcusdt"}
    def health(self):
        age = time.time() - self.last if self.last else None
        st = "stale" if self.state == "live" and (age is None or age > 20) else self.state
        return {"state": st, "error": self.error, "age": None if age is None else round(age, 1), "rest": time.time() - self.rest_ts < 5}
    def _url(self, streams):
        j = "/".join(f"{s}@aggTrade" for s in streams)
        return f"{WSURL}/market/stream?streams={j}" if self.mode == 0 else f"{WSURL}/market/ws/{j}"
    async def _sync(self, w, subs):
        n = 0
        while True:
            add, rem = sorted(self.want - subs), sorted(subs - self.want)
            for op, lst in (("SUBSCRIBE", add), ("UNSUBSCRIBE", rem)):
                for i in range(0, len(lst), 20):
                    n += 1; part = lst[i:i + 20]
                    await w.send(json.dumps({"method": op, "params": [f"{s}@aggTrade" for s in part], "id": n}))
                    (subs.update if op == "SUBSCRIBE" else subs.difference_update)(part); await asyncio.sleep(0.4)
            await asyncio.sleep(0.5)
    async def _dog(self, w, t0):
        await asyncio.sleep(25)
        if self.last < t0: self.error = "No trades on this endpoint - switching"; await w.close()
    def _trade(self, d):
        s, p, now = d["s"], float(d["p"]), time.time()
        if s not in self.first_id: self.first_id[s] = d["a"]; self.on_first(s)
        self.price[s], self.ts[s], self.tt[s], self.last = p, d["T"], now, now
        self.on_trade(s, p, float(d["q"]), d["m"], d["T"])
    async def run(self):
        back = 1
        while True:
            got, t0 = False, time.time()
            try:
                self.state = "connecting"; init = sorted(self.want)
                async with websockets.connect(self._url(init), ping_interval=20, ping_timeout=20, max_queue=None, open_timeout=10) as w:
                    self.state, self.error = "live", ""
                    sync, dog = asyncio.create_task(self._sync(w, set(init))), asyncio.create_task(self._dog(w, t0))
                    try:
                        async for m in w:
                            d = json.loads(m); d = d.get("data", d)
                            if not isinstance(d, dict) or d.get("e") != "aggTrade": continue
                            got = True; self._trade(d)
                            if time.time() - t0 > 23 * 3600: break   # Binance closes sockets at 24h
                    finally: sync.cancel(); dog.cancel()
            except asyncio.CancelledError: raise
            except Exception as e:
                self.error = ("Binance blocks this region (HTTP 451/403)" if any(x in str(e) for x in ("451", "403")) else f"{type(e).__name__}: {e}")[:140]
            self.state = "reconnecting"
            if got: back = 1
            else: self.mode = 1 - self.mode   # nothing received: try the other URL style
            await asyncio.sleep(back); back = min(back * 2, 10)
    async def rest_loop(self, symbols):
        while True:
            await asyncio.sleep(1); now = time.time()
            for s in list(symbols())[:6]:
                if now - self.tt.get(s, 0) > 3:
                    try: p = await binance.last_price(s)
                    except Exception: continue
                    self.price[s], self.ts[s] = p, int(time.time() * 1000)
                    if self.state != "live" or now - self.last > 10: self.rest_ts = time.time()
