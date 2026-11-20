import asyncio, json, re, time
from .binance import klines
from .config import cfg, TFS
from .confirmations import analyze

class Client:
    def __init__(self, ws): self.ws, self.sym, self.tf, self.fp, self.rid, self.last, self.lt, self.ver = ws, "BTCUSDT", "15m", False, 0, None, 0.0, -1

class Hub:
    def __init__(self, feed, fp, tracker):
        self.feed, self.fp, self.tr, self.clients = feed, fp, tracker, set()
        self.engine, self.on_view = None, (lambda s: None)
    def symbols(self): return {c.sym for c in self.clients}
    def sync_feed(self): self.feed.set_symbols(set(cfg["watchlist"]) | set(self.tr.active) | self.symbols())
    def sigs(self, s): return {"active": self.tr.active.get(s), "history": self.tr.history(s), "mode": cfg["mode"]}
    def wl(self): return [{"s": s, "p": self.feed.price.get(s), "sig": self.tr.active.get(s)} for s in cfg["watchlist"]]
    def fpbars(self, sym, tf, n): return analyze(self.fp.bars(sym, TFS[tf], n), self.fp.step.get(sym, 0), TFS[tf])
    async def _send(self, c, msg):
        try: await asyncio.wait_for(c.ws.send_text(json.dumps(msg, separators=(",", ":"))), 3)
        except Exception: self.clients.discard(c)
    async def _all(self, make):
        jobs = []
        for c in list(self.clients):
            m = make(c)
            if m: jobs.append(self._send(c, m))
        if jobs: await asyncio.gather(*jobs)
    async def push_signals(self): await self._all(lambda c: {"t": "sigs", "s": c.sym, "d": self.sigs(c.sym)}); await self.push_wl()
    async def push_wl(self): await self._all(lambda c: {"t": "wl", "d": self.wl()})
    async def push_fpsnap(self, sym):
        await self._all(lambda c: {"t": "fpsnap", "s": c.sym, "tf": c.tf, "step": self.fp.step.get(c.sym), "fp": self.fpbars(c.sym, c.tf, 60)} if c.fp and c.sym == sym else None)
    async def snapshot(self, c, rid):
        try: k = await klines(c.sym, c.tf)
        except Exception as e: return await self._send(c, {"t": "err", "m": str(e)})
        if rid != c.rid: return
        c.ver = -1
        await self._send(c, {"t": "snap", "s": c.sym, "tf": c.tf, "c": [x[:6] for x in k], "sigs": self.sigs(c.sym), "wl": self.wl(),
                             "step": self.fp.step.get(c.sym), "fp": self.fpbars(c.sym, c.tf, 60) if c.fp else None})
    async def handle(self, ws):
        await ws.accept(); c = Client(ws); self.clients.add(c)
        try:
            while True:
                try: m = json.loads(await ws.receive_text())
                except ValueError: continue
                if m.get("op") == "sub":
                    s = re.sub(r"[^A-Z0-9]", "", str(m.get("symbol", "")).upper())[:20]
                    if s and m.get("tf") in TFS:
                        c.sym, c.tf, c.fp, c.last, c.rid = s, m["tf"], bool(m.get("fp")), None, c.rid + 1
                        self.sync_feed(); self.on_view(s); asyncio.create_task(self.snapshot(c, c.rid))
                elif m.get("op") == "fp":
                    c.fp, c.ver = bool(m.get("on")), -1
                    if c.fp: await self._send(c, {"t": "fpsnap", "s": c.sym, "tf": c.tf, "step": self.fp.step.get(c.sym), "fp": self.fpbars(c.sym, c.tf, 60)})
        except Exception: pass
        finally: self.clients.discard(c)
    async def mon(self):
        while True:
            await asyncio.sleep(2)
            if not self.engine: continue
            for s in list(self.symbols()):
                d = await self.engine.monitor(s)
                if d: await self._all(lambda c, s=s, d=d: {"t": "mon", "s": s, "d": d} if c.sym == s else None)
    async def run(self):
        n = 0
        while True:
            await asyncio.sleep(0.25); n += 1; now = time.time()
            if n % 4 == 0:
                self.sync_feed(); p = {s: self.feed.price.get(s) for s in set(cfg["watchlist"]) | self.symbols()}; h = self.feed.health()
                await self._all(lambda c: {"t": "prices", "p": p, "feed": h})
            def tick(c):
                p = self.feed.price.get(c.sym)
                if p is None or (p == c.last and now - c.lt < 1): return None   # heartbeat so new candles still open on quiet pairs
                c.last, c.lt = p, now; return {"t": "tick", "s": c.sym, "p": p, "ts": self.feed.ts[c.sym] // 1000 if now - self.feed.tt.get(c.sym, 0) < 5 else int(now)}
            await self._all(tick)
            if n % 2 == 0:
                def fpmsg(c):
                    v = self.fp.ver.get(c.sym, 0)
                    if not c.fp or v == c.ver: return None
                    bars = self.fpbars(c.sym, c.tf, 14)
                    if not bars: return None
                    c.ver = v; return {"t": "fp", "s": c.sym, "tf": c.tf, "step": self.fp.step.get(c.sym), "b": bars[-1]}
                await self._all(fpmsg)
