import asyncio, json, time, websockets
from .config import WSURL

class Feed:
    """One combined Binance aggTrade socket. Streams are (un)subscribed live, so switching pairs never reconnects."""
    def __init__(self, on_trade):
        self.on_trade, self.want, self.price, self.ts = on_trade, set(), {}, {}
        self.state, self.error, self.last = "starting", "", 0.0
    def set_symbols(self, syms): self.want = {s.lower() for s in sorted(syms)[:40]}
    def health(self):
        age = time.time() - self.last if self.last else None
        st = "stale" if self.state == "live" and (age is None or age > 20) else self.state
        return {"state": st, "error": self.error, "age": None if age is None else round(age, 1)}
    async def _sync(self, w, subs):
        n = 0
        while True:
            add, rem = sorted(self.want - subs), sorted(subs - self.want)
            for op, lst in (("SUBSCRIBE", add), ("UNSUBSCRIBE", rem)):
                for i in range(0, len(lst), 20):
                    n += 1; part = lst[i:i + 20]
                    await w.send(json.dumps({"method": op, "params": [f"{s}@aggTrade" for s in part], "id": n}))
                    (subs.update if op == "SUBSCRIBE" else subs.difference_update)(part); await asyncio.sleep(0.4)
            await asyncio.sleep(1)
    async def run(self):
        back = 1
        while True:
            try:
                self.state = "connecting"
                async with websockets.connect(WSURL + "/stream", ping_interval=20, ping_timeout=20, max_queue=None, open_timeout=10) as w:
                    self.state, self.error, back, t0 = "live", "", 1, time.time()
                    sync = asyncio.create_task(self._sync(w, set()))
                    try:
                        async for m in w:
                            d = json.loads(m).get("data")
                            if not d: continue
                            s, p = d["s"], float(d["p"]); self.price[s] = p; self.ts[s] = d["T"]; self.last = time.time()
                            self.on_trade(s, p, float(d["q"]), d["m"], d["T"])
                            if time.time() - t0 > 23 * 3600: break   # Binance closes sockets at 24h
                    finally: sync.cancel()
            except asyncio.CancelledError: raise
            except Exception as e:
                self.state = "reconnecting"; self.error = ("Binance blocks this region (HTTP 451/403)" if any(x in str(e) for x in ("451", "403")) else f"{type(e).__name__}: {e}")[:140]
            await asyncio.sleep(back); back = min(back * 2, 15)
