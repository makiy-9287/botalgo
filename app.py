import asyncio, json, math, os, time, datetime as dt
from contextlib import asynccontextmanager
import httpx, websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_F = os.path.join(BASE, "config.json")
REST = "https://fapi.binance.com"
TFS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
MODES = {"scalping": ("5m", "15m", "1h"), "day": ("15m", "1h", "4h"), "swing": ("1h", "4h", "1d")}
cfg = {"watchlist": ["BTCUSDT", "ETHUSDT"], "mode": "day", "tg_token": "", "tg_chat": ""}
if os.path.exists(CFG_F):
    try: cfg.update(json.load(open(CFG_F)))
    except Exception: pass
def save(): json.dump(cfg, open(CFG_F, "w"))

http = httpx.AsyncClient(timeout=15)
PRICE, FP, STEP, ACTIVE, HISTORY, CLIENTS, KC, COOL, SEEN = {}, {}, {}, {}, [], {}, {}, {}, set()

# ---------- helpers ----------
def is_td(): return dt.datetime.now(dt.timezone.utc).weekday() <= 3   # Mon-Thu UTC
def px(x): return float(f"{x:.7g}")
async def tg(text):
    if not cfg["tg_token"] or not cfg["tg_chat"]: return False
    try:
        r = await http.post(f"https://api.telegram.org/bot{cfg['tg_token']}/sendMessage",
                            json={"chat_id": cfg["tg_chat"], "text": text, "parse_mode": "HTML"})
        return r.status_code == 200
    except Exception: return False
async def bcast(msg):
    for w in list(CLIENTS):
        try: await w.send_text(json.dumps(msg))
        except Exception: CLIENTS.pop(w, None)

async def klines(sym, tf, limit=500):
    k = (sym, tf); c = KC.get(k)
    if c and time.time() - c[0] < (8 if tf in ("1m", "5m") else 20): return c[1]
    r = await http.get(f"{REST}/fapi/v1/klines", params={"symbol": sym, "interval": tf, "limit": limit})
    if r.status_code != 200: raise HTTPException(400, "Invalid symbol or Binance error")
    d = [[x[0] // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), float(x[9])] for x in r.json()]
    KC[k] = (time.time(), d); return d   # row: t,o,h,l,c,vol,takerBuyVol

# ---------- live trades -> footprint + signal tracking ----------
def on_trade(s, p, q, sell, t):
    PRICE[s] = p
    if s not in STEP: STEP[s] = 10 ** math.floor(math.log10(p * 0.0002))
    st = STEP[s]; b = round(math.floor(p / st + 1e-9) * st, 10); mt = t // 60000 * 60
    m = FP.setdefault(s, {})
    m.setdefault(mt, {}).setdefault(b, [0.0, 0.0])[0 if sell else 1] += q
    if len(m) > 1600: del m[min(m)]
    track(s, p)

def track(s, p):
    sg = ACTIVE.get(s)
    if not sg: return
    L = sg["side"] == "BUY"
    if (p <= sg["sl"]) if L else (p >= sg["sl"]): return finish(sg, "TP1 then SL" if sg["tp1_hit"] else "SL")
    if (p >= sg["tp2"]) if L else (p <= sg["tp2"]): return finish(sg, "TP2")
    if not sg["tp1_hit"] and ((p >= sg["tp1"]) if L else (p <= sg["tp1"])):
        sg["tp1_hit"] = True
        asyncio.create_task(tg(f"✅ <b>{s}</b> TP1 hit ({sg['side']}) — {sg['tp1']}"))
        asyncio.create_task(bcast({"type": "signal"}))

def finish(sg, status):
    sg["status"] = status; sg["closed"] = int(time.time()); ACTIVE.pop(sg["sym"], None)
    COOL[sg["sym"]] = time.time() + 3 * TFS[sg["tf"]]
    icon = "🎯" if status == "TP2" else ("🛑" if status == "SL" else "⚠️")
    asyncio.create_task(tg(f"{icon} <b>{sg['sym']}</b> {sg['side']} closed: <b>{status}</b>\nPair reset — scanning again."))
    asyncio.create_task(bcast({"type": "signal"}))

async def ws_run(syms):
    url = "wss://fstream.binance.com/stream?streams=" + "/".join(f"{s}@aggTrade" for s in syms)
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, max_queue=None) as w:
                t0 = time.time()
                async for m in w:
                    d = json.loads(m)["data"]
                    on_trade(d["s"], float(d["p"]), float(d["q"]), d["m"], d["T"])
                    if time.time() - t0 > 23 * 3600: break   # Binance drops sockets at 24h
        except asyncio.CancelledError: raise
        except Exception: await asyncio.sleep(3)

async def stream_mgr():
    cur, task = set(), None
    while True:
        want = set(sorted({s.lower() for s in set(cfg["watchlist"]) | set(CLIENTS.values())})[:30])
        if want != cur:
            if task: task.cancel()
            cur = want; task = asyncio.create_task(ws_run(sorted(want))) if want else None
        await asyncio.sleep(2)

async def pump():
    n = 0
    while True:
        await asyncio.sleep(0.25); n += 1
        allp = {s: PRICE.get(s) for s in cfg["watchlist"]} if n % 4 == 0 else None
        for w, s in list(CLIENTS.items()):
            if PRICE.get(s) is None: continue
            try: await w.send_text(json.dumps({"type": "tick", "s": s, "p": PRICE[s], "all": allp}))
            except Exception: CLIENTS.pop(w, None)

# ---------- orderflow engine ----------
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

def fp_absorb(sym, t0, t1, s, c):
    mins = [m for m in FP.get(sym, {}) if t0 <= m < t1]
    if len(mins) < 0.8 * (t1 - t0) / 60: return None   # not enough live coverage -> fall back to proxy
    lv = {}
    for m in mins:
        for p, (b, a) in FP[sym][m].items():
            x = lv.setdefault(p, [0, 0]); x[0] += b; x[1] += a
    q = (c[2] - c[3]) * 0.3
    if s > 0:
        z = [v for p, v in lv.items() if p <= c[3] + q]
        return sum(v[0] for v in z) > 1.5 * max(sum(v[1] for v in z), 1e-9) and c[4] > c[3] + q
    z = [v for p, v in lv.items() if p >= c[2] - q]
    return sum(v[1] for v in z) > 1.5 * max(sum(v[0] for v in z), 1e-9) and c[4] < c[2] - q

async def analyze(sym):
    if sym in ACTIVE or COOL.get(sym, 0) > time.time() or not is_td(): return
    tf, htf, lvf = MODES[cfg["mode"]]
    k, h, L = await klines(sym, tf), await klines(sym, htf), await klines(sym, lvf)
    if len(k) < 100 or len(h) < 60 or len(L) < 30: return
    i = len(k) - 2; c = k[i]; key = (sym, cfg["mode"], c[0])
    if key in SEEN or time.time() - (c[0] + TFS[tf]) > TFS[tf]: return
    SEEN.add(key)
    if len(SEEN) > 5000: SEEN.clear()
    a = atr(k[:i + 1])
    if not a: return
    d = [2 * x[6] - x[5] for x in k]; cd = []; t = 0
    for x in d: t += x; cd.append(t)
    h1, l1 = pivots(L[:-1], 3); h2, l2 = pivots(k[:i - 5], 5)
    highs, lows = h1 + h2, l1 + l2
    av = sum(x[5] for x in k[i - 20:i]) / 20; rng = max(c[2] - c[3], 1e-9)
    vw = sum((x[2] + x[3] + x[4]) / 3 * x[5] for x in k[i - 95:i + 1]) / max(sum(x[5] for x in k[i - 95:i + 1]), 1e-9)
    hc = [x[4] for x in h]; he = ema(hc, 21); hd = sum(2 * x[6] - x[5] for x in h[-11:-1])
    for s in (1, -1):
        cand = [x for x in lows if c[3] < x < c[4] and x - c[3] <= 1.5 * a] if s > 0 else \
               [x for x in highs if c[4] < x < c[2] and c[2] - x <= 1.5 * a]
        if not cand: continue
        lvl = max(cand) if s > 0 else min(cand)
        w = range(i - 20, i)
        j = min(w, key=lambda x: k[x][3]) if s > 0 else max(w, key=lambda x: k[x][2])
        ext = c[3] <= k[j][3] if s > 0 else c[2] >= k[j][2]
        wick = (min(c[1], c[4]) - c[3]) if s > 0 else (c[2] - max(c[1], c[4]))
        fa = fp_absorb(sym, c[0], c[0] + TFS[tf], s, c)
        r = {"sweep": True,
             "delta_div": bool(ext and ((cd[i] > cd[j]) if s > 0 else (cd[i] < cd[j]))),
             "delta_shift": d[i] * s > 0 and (c[4] - c[1]) * s > 0,
             "absorption": bool(fa) if fa is not None else (c[5] > 1.3 * av and wick / rng >= 0.4),
             "htf_bias": (hc[-2] > he[-2] and hd > 0) if s > 0 else (hc[-2] < he[-2] and hd < 0),
             "location": (c[4] < vw) if s > 0 else (c[4] > vw),
             "confluence": sum(1 for x in (lows if s > 0 else highs) if abs(x - lvl) <= 0.3 * a) >= 2}
        score = sum(r.values())
        if score < 5 or not (r["delta_div"] or r["absorption"]): continue
        entry = PRICE.get(sym, c[4]); sl = c[3] - 0.25 * a if s > 0 else c[2] + 0.25 * a
        risk = (entry - sl) * s
        if not 0.4 * a <= risk <= 2.5 * a: continue
        sg = {"id": f"{sym}-{c[0]}", "sym": sym, "mode": cfg["mode"], "tf": tf, "side": "BUY" if s > 0 else "SELL",
              "entry": px(entry), "sl": px(sl), "tp1": px(entry + 1.5 * risk * s), "tp2": px(entry + 3 * risk * s),
              "level": px(lvl), "score": score, "conf": [x for x, v in r.items() if v], "ts": int(time.time()),
              "bar": c[0], "status": "OPEN", "tp1_hit": False}
        ACTIVE[sym] = sg; HISTORY.append(sg); del HISTORY[:-300]
        await tg(f"{'🟢' if s > 0 else '🔴'} <b>{sym} {sg['side']}</b> ({cfg['mode']} · {tf})\nEntry: <code>{sg['entry']}</code>\n"
                 f"SL: <code>{sg['sl']}</code>\nTP1: <code>{sg['tp1']}</code>\nTP2: <code>{sg['tp2']}</code>\n"
                 f"Liquidity level: {sg['level']}\nConfirmations ({score}/7): {', '.join(sg['conf'])}")
        await bcast({"type": "signal"}); return

async def engine():
    while True:
        for s in list(set(cfg["watchlist"]) | set(CLIENTS.values())):
            try: await analyze(s)
            except Exception as e: print("engine", s, e)
        await asyncio.sleep(5)

# ---------- API ----------
@asynccontextmanager
async def life(app):
    ts = [asyncio.create_task(f()) for f in (stream_mgr, pump, engine)]
    yield
    for t in ts: t.cancel()
app = FastAPI(lifespan=life)

@app.get("/")
def index(): return FileResponse(os.path.join(BASE, "static", "index.html"))

@app.get("/api/klines")
async def api_klines(symbol: str, tf: str = "15m"):
    if tf not in TFS: raise HTTPException(400, "bad timeframe")
    k = await klines(symbol.upper(), tf)
    return [{"time": x[0], "open": x[1], "high": x[2], "low": x[3], "close": x[4], "volume": x[5]} for x in k]

@app.get("/api/footprint")
def api_fp(symbol: str, tf: str = "15m"):
    s = symbol.upper(); sec = TFS.get(tf, 60); out = {}
    for mt, lv in FP.get(s, {}).items():
        o = out.setdefault(mt // sec * sec, {})
        for p, (b, a) in lv.items():
            x = o.setdefault(p, [0, 0]); x[0] += b; x[1] += a
    return {"step": STEP.get(s, 0), "bars": [{"t": t, "l": [[p, round(v[0], 4), round(v[1], 4)] for p, v in sorted(out[t].items())]} for t in sorted(out)[-80:]]}

@app.get("/api/signals")
def api_sig(symbol: str):
    s = symbol.upper()
    return {"active": ACTIVE.get(s), "history": [x for x in HISTORY if x["sym"] == s][-40:], "mode": cfg["mode"], "trading_day": is_td()}

@app.get("/api/state")
def api_state():
    return {"mode": cfg["mode"], "trading_day": is_td(), "max": 10,
            "watchlist": [{"s": s, "p": PRICE.get(s), "sig": ACTIVE.get(s)} for s in cfg["watchlist"]]}

class Sym(BaseModel): symbol: str
class Mode(BaseModel): mode: str
class Settings(BaseModel): tg_token: str = ""; tg_chat: str = ""

async def norm(x):
    s = x.strip().upper().replace("/", "").replace("-", "")
    if not s.endswith("USDT"): s += "USDT"
    await klines(s, "1h"); return s

@app.post("/api/watchlist")
async def wl_add(b: Sym):
    s = await norm(b.symbol)
    if s in cfg["watchlist"]: raise HTTPException(400, "Already in watchlist")
    if len(cfg["watchlist"]) >= 10: raise HTTPException(400, "Watchlist is full (max 10)")
    cfg["watchlist"].append(s); save(); return cfg["watchlist"]

@app.put("/api/watchlist/{old}")
async def wl_edit(old: str, b: Sym):
    old = old.upper(); s = await norm(b.symbol)
    if old not in cfg["watchlist"]: raise HTTPException(404, "Not found")
    if s != old and s in cfg["watchlist"]: raise HTTPException(400, "Already in watchlist")
    ACTIVE.pop(old, None); cfg["watchlist"][cfg["watchlist"].index(old)] = s; save(); return cfg["watchlist"]

@app.delete("/api/watchlist/{s}")
def wl_del(s: str):
    s = s.upper()
    if s in cfg["watchlist"]: cfg["watchlist"].remove(s); save()
    return cfg["watchlist"]

@app.post("/api/mode")
def set_mode(b: Mode):
    if b.mode not in MODES: raise HTTPException(400, "bad mode")
    cfg["mode"] = b.mode; save(); return {"mode": b.mode}

@app.get("/api/settings")
def get_set():
    t = cfg["tg_token"]
    return {"tg_token": ("••••" + t[-4:]) if t else "", "tg_chat": cfg["tg_chat"]}

@app.post("/api/settings")
def put_set(b: Settings):
    if b.tg_token and not b.tg_token.startswith("••••"): cfg["tg_token"] = b.tg_token.strip()
    cfg["tg_chat"] = b.tg_chat.strip(); save(); return {"ok": True}

@app.post("/api/telegram/test")
async def tg_test():
    ok = await tg("✅ <b>Orderflow Terminal</b>: test notification works.")
    if not ok: raise HTTPException(400, "Telegram failed — check bot token and chat ID (send /start to the bot first)")
    return {"ok": True}

@app.websocket("/ws")
async def ws(w: WebSocket):
    await w.accept(); CLIENTS[w] = "BTCUSDT"
    try:
        while True:
            m = json.loads(await w.receive_text())
            if m.get("symbol"): CLIENTS[w] = m["symbol"].upper()
    except (WebSocketDisconnect, Exception): CLIENTS.pop(w, None)
