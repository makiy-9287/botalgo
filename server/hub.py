import asyncio, json, re
from .binance import klines
from .config import cfg, TFS, is_td

class Client:
    def __init__(self, ws): self.ws, self.sym, self.tf, self.fp, self.rid, self.last, self.ver = ws, "BTCUSDT", "15m", False, 0, None, -1

class Hub:
    def __init__(self, feed, fp, tracker): self.feed, self.fp, self.tr, self.clients = feed, fp, tracker, set()
    def symbols(self): return {c.sym for c in self.clients}
    def sigs(self, s): return {"active": self.tr.active.get(s), "history": self.tr.history(s), "mode": cfg["mode"], "td": is_td()}
    def wl(self): return [{"s": s, "p": self.feed.price.get(s), "sig": self.tr.active.get(s)} for s in cfg["watchlist"]]
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
    async def snapshot(self, c, rid):
        try: k = await klines(c.sym, c.tf)
        except Exception as e: return await self._send(c, {"t": "err", "m": str(e)})
        if rid != c.rid: return
        c.ver = -1
        await self._send(c, {"t": "snap", "s": c.sym, "tf": c.tf, "c": [x[:6] for x in k], "sigs": self.sigs(c.sym), "wl": self.wl(),
                             "step": self.fp.step.get(c.sym), "fp": self.fp.bars(c.sym, TFS[c.tf]) if c.fp else None})
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
                        asyncio.create_task(self.snapshot(c, c.rid))
                elif m.get("op") == "fp":
                    c.fp, c.ver = bool(m.get("on")), -1
                    if c.fp: await self._send(c, {"t": "fpsnap", "s": c.sym, "tf": c.tf, "step": self.fp.step.get(c.sym), "fp": self.fp.bars(c.sym, TFS[c.tf])})
        except Exception: pass
        finally: self.clients.discard(c)
    async def run(self):
        n = 0
        while True:
            await asyncio.sleep(0.25); n += 1
            if n % 4 == 0:
                self.feed.set_symbols(set(cfg["watchlist"]) | set(self.tr.active) | self.symbols())
                p = {s: self.feed.price.get(s) for s in set(cfg["watchlist"]) | self.symbols()}
                h = self.feed.health(); td = is_td()
                await self._all(lambda c: {"t": "prices", "p": p, "feed": h, "td": td})
            def tick(c):
                p = self.feed.price.get(c.sym)
                if p is None or p == c.last: return None
                c.last = p; return {"t": "tick", "s": c.sym, "p": p, "ts": self.feed.ts[c.sym] // 1000}
            await self._all(tick)
            if n % 2 == 0:
                def fpmsg(c):
                    v = self.fp.ver.get(c.sym, 0)
                    if not c.fp or v == c.ver: return None
                    b = self.fp.current(c.sym, TFS[c.tf])
                    if not b: return None
                    c.ver = v; return {"t": "fp", "s": c.sym, "tf": c.tf, "step": self.fp.step.get(c.sym), "b": b}
                await self._all(fpmsg)
