import math

class FootprintStore:
    """Per-minute price-level volume: m[sym][minute] = {price: [sellVol(bid), buyVol(ask)]}"""
    def __init__(self): self.m, self.step, self.ver = {}, {}, {}
    def add(self, sym, p, q, sell, ms):
        st = self.step.get(sym)
        if not st: st = self.step[sym] = 10 ** math.floor(math.log10(p * 0.0002))
        b = round(math.floor(p / st + 1e-9) * st, 10); mt = ms // 60000 * 60
        d = self.m.setdefault(sym, {})
        d.setdefault(mt, {}).setdefault(b, [0.0, 0.0])[0 if sell else 1] += q
        if len(d) > 1500: d.pop(min(d))
        self.ver[sym] = self.ver.get(sym, 0) + 1
    def levels(self, sym, t0, t1):
        out, d = {}, self.m.get(sym, {})
        for mt in range(t0, t1, 60):
            for p, (b, a) in d.get(mt, {}).items():
                x = out.setdefault(p, [0.0, 0.0]); x[0] += b; x[1] += a
        return out
    def coverage(self, sym, t0, t1):
        d = self.m.get(sym, {}); return sum(1 for mt in range(t0, t1, 60) if mt in d)
    def _fmt(self, t, lv): return {"t": t, "l": [[p, round(v[0], 3), round(v[1], 3)] for p, v in sorted(lv.items())]}
    def bars(self, sym, sec, n=60):
        out = {}
        for mt, lv in self.m.get(sym, {}).items():
            o = out.setdefault(mt // sec * sec, {})
            for p, (b, a) in lv.items():
                x = o.setdefault(p, [0.0, 0.0]); x[0] += b; x[1] += a
        return [self._fmt(t, out[t]) for t in sorted(out)[-n:]]
    def current(self, sym, sec):
        d = self.m.get(sym)
        if not d: return None
        t = max(d) // sec * sec; return self._fmt(t, self.levels(sym, t, t + sec))
