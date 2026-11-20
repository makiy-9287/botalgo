import asyncio, time
from . import binance
from .config import cfg, TFS, MODES
from .confirmations import analyze

def ema(a, n):
    k = 2 / (n + 1); o = [a[0]]
    for x in a[1:]: o.append(x * k + o[-1] * (1 - k))
    return o
def atr(k, n=14):
    tr = [max(k[j][2] - k[j][3], abs(k[j][2] - k[j - 1][4]), abs(k[j][3] - k[j - 1][4])) for j in range(1, len(k))]
    return sum(tr[-n:]) / n if len(tr) >= n else 0
def pivots(k, n):
    hi, lo = [], []
    for j in range(n, len(k) - n):
        if k[j][2] == max(x[2] for x in k[j - n:j + n + 1]): hi.append(k[j][2])
        if k[j][3] == min(x[3] for x in k[j - n:j + n + 1]): lo.append(k[j][3])
    return hi, lo
px = lambda x: float(f"{x:.7g}")

class Engine:
    """Trades any day of the week. One evaluation per closed bar; the same evaluate() feeds the live confirmation monitor."""
    def __init__(self, feed, fp, tracker, notify, symbols):
        self.feed, self.fp, self.tr, self.notify, self.symbols = feed, fp, tracker, notify, symbols
        self.seen, self.err, self.scans = set(), "", 0
    async def run(self):
        while True:
            await asyncio.gather(*(self._safe(s) for s in set(cfg["watchlist"]) | set(self.symbols())))
            await asyncio.sleep(5)
    async def _safe(self, s):
        try: await self.scan(s)
        except asyncio.CancelledError: raise
        except Exception as e: self.err = f"{s}: {type(e).__name__}: {e}"[:160]
    def absorb(self, sym, t0, t1, s, c):
        if self.fp.coverage(sym, t0, t1) < 0.8 * (t1 - t0) / 60: return None   # not enough live data -> candle proxy
        lv = self.fp.levels(sym, t0, t1); q = (c[2] - c[3]) * 0.3
        if s > 0:
            z = [v for p, v in lv.items() if p <= c[3] + q]
            return sum(v[0] for v in z) > 1.5 * max(sum(v[1] for v in z), 1e-9) and c[4] > c[3] + q
        z = [v for p, v in lv.items() if p >= c[2] - q]
        return sum(v[1] for v in z) > 1.5 * max(sum(v[0] for v in z), 1e-9) and c[4] < c[2] - q

    async def evaluate(self, sym):
        tf, htf, lvf = MODES[cfg["mode"]]; sec = TFS[tf]
        k, h, L = await asyncio.gather(binance.klines(sym, tf), binance.klines(sym, htf), binance.klines(sym, lvf))
        if len(k) < 100 or len(h) < 60 or len(L) < 30: return None
        i = len(k) - 2; c = k[i]; a = atr(k[:i + 1])
        if not a: return None
        d = [2 * x[6] - x[5] for x in k]; cd, t = [], 0
        for x in d: t += x; cd.append(t)
        h1, l1 = pivots(L[:-1], 3); h2, l2 = pivots(k[:i - 5], 5); highs, lows = h1 + h2, l1 + l2
        av = sum(x[5] for x in k[i - 20:i]) / 20; rng = max(c[2] - c[3], 1e-9)
        w96 = k[i - 95:i + 1]; vw = sum((x[2] + x[3] + x[4]) / 3 * x[5] for x in w96) / max(sum(x[5] for x in w96), 1e-9)
        hc = [x[4] for x in h]; he = ema(hc, 21); hd = sum(2 * x[6] - x[5] for x in h[-11:-1])
        price = self.feed.price.get(sym, k[-1][4]); cover = self.fp.coverage(sym, c[0], c[0] + sec) >= 0.8 * sec / 60; evs = []
        if cover:
            bars = analyze(self.fp.bars(sym, sec, 30), self.fp.step.get(sym, 0), sec)
            evs = next((b["ev"] for b in bars if b["t"] == c[0]), [])
        lv = lambda arr, up: [{"p": px(x), "d": round((x - price) / a, 2)} for x in (sorted(y for y in arr if y > price)[:3] if up else sorted((y for y in arr if y <= price), reverse=True)[:3])]
        out = {"sym": sym, "tf": tf, "mode": cfg["mode"], "bar": c[0], "price": px(price), "atr": px(a), "vwap": px(vw), "fp": cover,
               "bias": "bull" if hc[-2] > he[-2] and hd > 0 else "bear" if hc[-2] < he[-2] and hd < 0 else "flat",
               "levels": {"hi": lv(highs, True), "lo": lv(lows, False)}, "sides": {}, "_c": c, "_a": a}
        for sd, name in ((1, "buy"), (-1, "sell")):
            ev_side = "bull" if sd > 0 else "bear"
            cand = [x for x in lows if c[3] < x < c[4] and x - c[3] <= 1.5 * a] if sd > 0 else [x for x in highs if c[4] < x < c[2] and c[2] - x <= 1.5 * a]
            lvl = (max(cand) if sd > 0 else min(cand)) if cand else None
            win = range(i - 20, i); j = min(win, key=lambda x: k[x][3]) if sd > 0 else max(win, key=lambda x: k[x][2])
            ext = c[3] <= k[j][3] if sd > 0 else c[2] >= k[j][2]
            wick = (min(c[1], c[4]) - c[3]) if sd > 0 else (c[2] - max(c[1], c[4]))
            fa = self.absorb(sym, c[0], c[0] + sec, sd, c)
            conf = {"sweep": lvl is not None,
                    "delta_div": bool(ext and ((cd[i] > cd[j]) if sd > 0 else (cd[i] < cd[j]))),
                    "delta_shift": d[i] * sd > 0 and (c[4] - c[1]) * sd > 0,
                    "absorption": bool(fa) if fa is not None else (c[5] > 1.3 * av and wick / rng >= 0.4),
                    "htf_bias": (hc[-2] > he[-2] and hd > 0) if sd > 0 else (hc[-2] < he[-2] and hd < 0),
                    "location": (c[4] < vw) if sd > 0 else (c[4] > vw),
                    "confluence": lvl is not None and sum(1 for x in (lows if sd > 0 else highs) if abs(x - lvl) <= 0.3 * a) >= 2}
            if cover:
                conf["stacked"] = any(e["k"] == "stack" and e["s"] == ev_side for e in evs)
                conf["trapped"] = any(e["k"] == "trap" and e["s"] == ev_side for e in evs)
            score = sum(conf.values())
            out["sides"][name] = {"conf": conf, "score": score, "total": len(conf), "level": px(lvl) if lvl else None,
                                  "ready": conf["sweep"] and score >= 5 and (conf["delta_div"] or conf["absorption"])}
        return out

    async def monitor(self, sym):
        try: o = await self.evaluate(sym)
        except asyncio.CancelledError: raise
        except Exception as e: self.err = f"{sym}: {type(e).__name__}: {e}"[:160]; return None
        return {k: v for k, v in o.items() if not k.startswith("_")} if o else None

    async def scan(self, sym):
        if sym in self.tr.active or self.tr.cool.get(sym, 0) > time.time(): return
        o = await self.evaluate(sym)
        if not o: return
        tf, key = o["tf"], (sym, cfg["mode"], o["bar"]); self.scans += 1
        if key in self.seen or time.time() - (o["bar"] + TFS[tf]) > TFS[tf]: return   # one evaluation per closed bar, never stale bars
        self.seen.add(key)
        if len(self.seen) > 5000: self.seen.clear()
        c, a = o["_c"], o["_a"]
        for sd, name in ((1, "buy"), (-1, "sell")):
            sc = o["sides"][name]
            if not sc["ready"]: continue
            entry = self.feed.price.get(sym, c[4]); sl = c[3] - 0.25 * a if sd > 0 else c[2] + 0.25 * a; risk = (entry - sl) * sd
            if not 0.4 * a <= risk <= 2.5 * a: continue
            sg = {"id": f"{sym}-{c[0]}", "sym": sym, "mode": cfg["mode"], "tf": tf, "side": name.upper(),
                  "entry": px(entry), "sl": px(sl), "tp1": px(entry + 1.5 * risk * sd), "tp2": px(entry + 3 * risk * sd),
                  "level": sc["level"], "score": sc["score"], "total": sc["total"], "conf": [x for x, v in sc["conf"].items() if v],
                  "ts": int(time.time()), "bar": c[0], "status": "OPEN", "tp1_hit": False}
            self.tr.open(sg)
            self.notify(f"{'🟢' if sd > 0 else '🔴'} <b>{sym} {sg['side']}</b> ({sg['mode']} · {tf})\nEntry: <code>{sg['entry']}</code>\nSL: <code>{sg['sl']}</code>\n"
                        f"TP1: <code>{sg['tp1']}</code>\nTP2: <code>{sg['tp2']}</code>\nLiquidity: {sg['level']}\nConfirmations ({sg['score']}/{sg['total']}): {', '.join(sg['conf'])}")
            return
