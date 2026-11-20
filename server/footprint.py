import math

class FootprintStore:
    """m[sym][minute] = {price: [sellVol(bid), buyVol(ask)]};  oc[sym][minute] = [t_first, p_first, t_last, p_last]"""
    def __init__(self): self.m, self.oc, self.step, self.ver = {}, {}, {}, {}
    def add(self, sym, p, q, sell, ms):
        st = self.step.get(sym)
        if not st: st = self.step[sym] = 10 ** math.floor(math.log10(p * 0.0002))
        b = round(math.floor(p / st + 1e-9) * st, 10); mt = ms // 60000 * 60
        d, oc = self.m.setdefault(sym, {}), self.oc.setdefault(sym, {})
        d.setdefault(mt, {}).setdefault(b, [0.0, 0.0])[0 if sell else 1] += q
        o = oc.get(mt)
        if not o: oc[mt] = [ms, p, ms, p]
        else:
            if ms < o[0]: o[0], o[1] = ms, p
            if ms >= o[2]: o[2], o[3] = ms, p
        if len(d) > 1500: old = min(d); d.pop(old); oc.pop(old, None)
        self.ver[sym] = self.ver.get(sym, 0) + 1
    def levels(self, sym, t0, t1):
        out, d = {}, self.m.get(sym, {})
        for mt in range(t0, t1, 60):
            for p, (b, a) in d.get(mt, {}).items():
                x = out.setdefault(p, [0.0, 0.0]); x[0] += b; x[1] += a
        return out
    def coverage(self, sym, t0, t1):
        d = self.m.get(sym, {}); return sum(1 for mt in range(t0, t1, 60) if mt in d)
    def _oc(self, sym, t0, t1):
        oc, f, l = self.oc.get(sym, {}), None, None
        for mt in range(t0, t1, 60):
            x = oc.get(mt)
            if not x: continue
            if f is None or x[0] < f[0]: f = x
            if l is None or x[2] >= l[2]: l = x
        return (f[1], l[3]) if f else (None, None)
    def bars(self, sym, sec, n=60):
        out = []
        for bt in sorted({mt // sec * sec for mt in self.m.get(sym, {})})[-n:]:
            o, c = self._oc(sym, bt, bt + sec)
            out.append({"t": bt, "o": o, "c": c, "l": [[p, round(v[0], 3), round(v[1], 3)] for p, v in sorted(self.levels(sym, bt, bt + sec).items())]})
        return out
