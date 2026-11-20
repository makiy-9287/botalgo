"""Orderflow confirmations per footprint bar. Events: {k, s:'bull'|'bear', p}
k: abs (absorption) | trap (trapped traders) | stack (stacked imbalance) | div (swing delta divergence) | sdiv (single-bar divergence) | exh (exhaustion)"""

def _runs(js):
    out, cur = [], []
    for j in sorted(js):
        if cur and j == cur[-1] + 1: cur.append(j)
        else:
            if len(cur) >= 3: out.append(cur)
            cur = [j]
    if len(cur) >= 3: out.append(cur)
    return out

def analyze(bars, step, sec):
    n, info, cd = len(bars), [], 0.0
    step = step or 1e-9
    for b in bars:
        lv = b["l"]; b["ev"] = []; vol = sum(x[1] + x[2] for x in lv) or 1e-9; dl = sum(x[2] - x[1] for x in lv); cd += dl
        info.append({"vol": vol, "dl": dl, "cd": cd, "lo": lv[0][0] if lv else 0, "hi": lv[-1][0] + step if lv else 0})
    avg = sum(i["vol"] for i in info) / max(n, 1)
    for i, b in enumerate(bars):
        lv = b["l"]
        if len(lv) < 3: continue
        I = info[i]; rng = max(I["hi"] - I["lo"], step); o = b.get("o") or lv[0][0]; c = b.get("c") or lv[-1][0]; ev = b["ev"]; prev = info[max(0, i - 5):i]
        zl = [x for x in lv if x[0] < I["lo"] + .25 * rng]; zh = [x for x in lv if x[0] >= I["hi"] - .25 * rng]
        bl, al, bh, ah = sum(x[1] for x in zl), sum(x[2] for x in zl), sum(x[1] for x in zh), sum(x[2] for x in zh)
        idx = {round(x[0] / step): x for x in lv}; mx = max(x[1] + x[2] for x in lv)
        buy = [j for j, x in idx.items() if x[2] >= .05 * mx and x[2] >= 3 * (idx[j - 1][1] if j - 1 in idx else 0)]    # diagonal 300%
        sell = [j for j, x in idx.items() if x[1] >= .05 * mx and x[1] >= 3 * (idx[j + 1][2] if j + 1 in idx else 0)]
        for js, s in ((buy, "bull"), (sell, "bear")):
            r = _runs(js)
            if r: run = max(r, key=len); ev.append({"k": "stack", "s": s, "p": (run[len(run) // 2] + .5) * step})
        if bl > 1.5 * max(al, 1e-9) and bl >= .15 * I["vol"] and I["vol"] >= .8 * avg and c >= I["lo"] + .4 * rng: ev.append({"k": "abs", "s": "bull", "p": I["lo"]})
        if ah > 1.5 * max(bh, 1e-9) and ah >= .15 * I["vol"] and I["vol"] >= .8 * avg and c <= I["hi"] - .4 * rng: ev.append({"k": "abs", "s": "bear", "p": I["hi"]})
        if prev and I["lo"] < min(x["lo"] for x in prev) and bl >= .25 * I["vol"] and any((bars[j].get("c") or 0) > I["lo"] + .5 * rng for j in range(i, min(n, i + 3))): ev.append({"k": "trap", "s": "bull", "p": I["lo"]})
        if prev and I["hi"] > max(x["hi"] for x in prev) and ah >= .25 * I["vol"] and any((bars[j].get("c") or 1e18) < I["hi"] - .5 * rng for j in range(i, min(n, i + 3))): ev.append({"k": "trap", "s": "bear", "p": I["hi"]})
        if len(lv) >= 6 and prev:
            if I["hi"] > max(x["hi"] for x in prev) and lv[-1][1] + lv[-1][2] < .03 * I["vol"]: ev.append({"k": "exh", "s": "bear", "p": I["hi"]})
            if I["lo"] < min(x["lo"] for x in prev) and lv[0][1] + lv[0][2] < .03 * I["vol"]: ev.append({"k": "exh", "s": "bull", "p": I["lo"]})
        if abs(I["dl"]) >= .1 * I["vol"]:
            if c > o and I["dl"] < 0: ev.append({"k": "sdiv", "s": "bear", "p": I["hi"]})
            if c < o and I["dl"] > 0: ev.append({"k": "sdiv", "s": "bull", "p": I["lo"]})
        w = range(max(0, i - 8), i)
        if len(w):
            j = max(w, key=lambda x: info[x]["hi"])
            if I["hi"] > info[j]["hi"] and I["cd"] < info[j]["cd"]: ev.append({"k": "div", "s": "bear", "p": I["hi"]})
            j = min(w, key=lambda x: info[x]["lo"])
            if I["lo"] < info[j]["lo"] and I["cd"] > info[j]["cd"]: ev.append({"k": "div", "s": "bull", "p": I["lo"]})
    return bars
