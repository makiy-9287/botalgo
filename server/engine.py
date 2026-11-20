import asyncio, time
from . import binance
from .config import cfg, TFS, MODES, is_td

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

    async def scan(self, sym):
        if sym in self.tr.active or self.tr.cool.get(sym, 0) > time.time() or not is_td(): return
        tf, htf, lvf = MODES[cfg["mode"]]
        k, h, L = await asyncio.gather(binance.klines(sym, tf), binance.klines(sym, htf), binance.klines(sym, lvf))
        if len(k) < 100 or len(h) < 60 or len(L) < 30: return
        i = len(k) - 2; c = k[i]; key = (sym, cfg["mode"], c[0]); self.scans += 1
        if key in self.seen or time.time() - (c[0] + TFS[tf]) > TFS[tf]: return   # one evaluation per closed bar, never stale bars
        self.seen.add(key)
        if len(self.seen) > 5000: self.seen.clear()
        a = atr(k[:i + 1])
        if not a: return
        d = [2 * x[6] - x[5] for x in k]; cd, t = [], 0
        for x in d: t += x; cd.append(t)
        h1, l1 = pivots(L[:-1], 3); h2, l2 = pivots(k[:i - 5], 5); highs, lows = h1 + h2, l1 + l2
        av = sum(x[5] for x in k[i - 20:i]) / 20; rng = max(c[2] - c[3], 1e-9)
        w96 = k[i - 95:i + 1]; vw = sum((x[2] + x[3] + x[4]) / 3 * x[5] for x in w96) / max(sum(x[5] for x in w96), 1e-9)
        hc = [x[4] for x in h]; he = ema(hc, 21); hd = sum(2 * x[6] - x[5] for x in h[-11:-1])
        for s in (1, -1):
            cand = [x for x in lows if c[3] < x < c[4] and x - c[3] <= 1.5 * a] if s > 0 else [x for x in highs if c[4] < x < c[2] and c[2] - x <= 1.5 * a]
            if not cand: continue
            lvl = max(cand) if s > 0 else min(cand); win = range(i - 20, i)
            j = min(win, key=lambda x: k[x][3]) if s > 0 else max(win, key=lambda x: k[x][2])
            ext = c[3] <= k[j][3] if s > 0 else c[2] >= k[j][2]
            wick = (min(c[1], c[4]) - c[3]) if s > 0 else (c[2] - max(c[1], c[4]))
            fa = self.absorb(sym, c[0], c[0] + TFS[tf], s, c)
            r = {"sweep": True,
                 "delta_div": bool(ext and ((cd[i] > cd[j]) if s > 0 else (cd[i] < cd[j]))),
                 "delta_shift": d[i] * s > 0 and (c[4] - c[1]) * s > 0,
                 "absorption": bool(fa) if fa is not None else (c[5] > 1.3 * av and wick / rng >= 0.4),
                 "htf_bias": (hc[-2] > he[-2] and hd > 0) if s > 0 else (hc[-2] < he[-2] and hd < 0),
                 "location": (c[4] < vw) if s > 0 else (c[4] > vw),
                 "confluence": sum(1 for x in (lows if s > 0 else highs) if abs(x - lvl) <= 0.3 * a) >= 2}
            score = sum(r.values())
            if score < 5 or not (r["delta_div"] or r["absorption"]): continue
            entry = self.feed.price.get(sym, c[4]); sl = c[3] - 0.25 * a if s > 0 else c[2] + 0.25 * a; risk = (entry - sl) * s
            if not 0.4 * a <= risk <= 2.5 * a: continue
            sg = {"id": f"{sym}-{c[0]}", "sym": sym, "mode": cfg["mode"], "tf": tf, "side": "BUY" if s > 0 else "SELL",
                  "entry": px(entry), "sl": px(sl), "tp1": px(entry + 1.5 * risk * s), "tp2": px(entry + 3 * risk * s),
                  "level": px(lvl), "score": score, "conf": [x for x, v in r.items() if v], "ts": int(time.time()),
                  "bar": c[0], "status": "OPEN", "tp1_hit": False}
            self.tr.open(sg)
            self.notify(f"{'🟢' if s > 0 else '🔴'} <b>{sym} {sg['side']}</b> ({sg['mode']} · {tf})\nEntry: <code>{sg['entry']}</code>\nSL: <code>{sg['sl']}</code>\n"
                        f"TP1: <code>{sg['tp1']}</code>\nTP2: <code>{sg['tp2']}</code>\nLiquidity: {sg['level']}\nConfirmations ({score}/7): {', '.join(sg['conf'])}")
            return
