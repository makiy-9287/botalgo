import asyncio, re
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import binance
from .config import BASE, cfg, MODES, MAX_WL
from .engine import Engine
from .feed import Feed
from .footprint import FootprintStore
from .hub import Hub
from .telegram import Telegram
from .tracker import Tracker

tg, fp = Telegram(), FootprintStore()
tracker = Tracker(tg.notify, lambda: asyncio.create_task(hub.push_signals()))
def on_trade(s, p, q, sell, ms): fp.add(s, p, q, sell, ms); tracker.on_price(s, p)
feed = Feed(on_trade); hub = Hub(feed, fp, tracker); engine = Engine(feed, fp, tracker, tg.notify, hub.symbols)

def command(c, a):
    if c == "/status":
        return f"Mode: <b>{cfg['mode']}</b> · Feed: {feed.health()['state']} · Open signals: {len(tracker.active)}\n" + "\n".join(f"{s['sym']} {s['side']} @ {s['entry']} (SL {s['sl']} TP1 {s['tp1']})" for s in tracker.active.values())
    if c == "/watchlist": return "Watchlist: " + (", ".join(cfg["watchlist"]) or "empty")
    if c == "/mode" and a and a[0].lower() in MODES:
        cfg["mode"] = a[0].lower(); cfg.save(); return f"Mode set to <b>{cfg['mode']}</b>"
    return "Commands: /status /watchlist /mode scalping|day|swing"

@asynccontextmanager
async def life(app):
    ts = [asyncio.create_task(f) for f in (feed.run(), hub.run(), engine.run(), tg.poll(command))]
    yield
    for t in ts: t.cancel()

app = FastAPI(lifespan=life)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

@app.exception_handler(binance.BinanceError)
async def be(_: Request, e): return JSONResponse({"detail": str(e)}, status_code=e.code if e.code in (400, 429) else 502)

@app.get("/")
def index(): return FileResponse(BASE / "static" / "index.html", headers={"Cache-Control": "no-cache"})
@app.get("/api/symbols")
async def symbols(): return await binance.symbols()
@app.get("/api/state")
def state(): return {"mode": cfg["mode"], "wl": hub.wl(), "max": MAX_WL}
@app.get("/api/health")
def health(): return {"feed": feed.health(), "engine": {"error": engine.err, "scans": engine.scans}, "clients": len(hub.clients), "telegram": tg.ready}

class Sym(BaseModel): symbol: str
class Mode(BaseModel): mode: str
class Settings(BaseModel): tg_token: str = ""; tg_chat: str = ""

async def norm(x):
    s = re.sub(r"[^A-Z0-9]", "", x.upper())
    if not s: raise HTTPException(400, "Enter a symbol")
    if not s.endswith("USDT"): s += "USDT"
    try: ok = s in await binance.symbols()
    except binance.BinanceError: await binance.klines(s, "1h"); ok = True   # symbol list unavailable: verify via klines
    if not ok: raise HTTPException(400, f"{s} is not a Binance USDT-M perpetual")
    return s

@app.post("/api/watchlist")
async def wl_add(b: Sym):
    s = await norm(b.symbol)
    if s in cfg["watchlist"]: raise HTTPException(400, f"{s} is already in the watchlist")
    if len(cfg["watchlist"]) >= MAX_WL: raise HTTPException(400, f"Watchlist is full (max {MAX_WL})")
    cfg["watchlist"].append(s); cfg.save(); await hub.push_wl(); return hub.wl()
@app.put("/api/watchlist/{old}")
async def wl_edit(old: str, b: Sym):
    old = old.upper(); s = await norm(b.symbol)
    if old not in cfg["watchlist"]: raise HTTPException(404, "Not in watchlist")
    if s != old and s in cfg["watchlist"]: raise HTTPException(400, f"{s} is already in the watchlist")
    cfg["watchlist"][cfg["watchlist"].index(old)] = s; cfg.save(); await hub.push_wl(); return hub.wl()
@app.delete("/api/watchlist/{s}")
async def wl_del(s: str):
    s = s.upper()
    if s in cfg["watchlist"]: cfg["watchlist"].remove(s); cfg.save()
    await hub.push_wl(); return hub.wl()
@app.post("/api/mode")
def set_mode(b: Mode):
    if b.mode not in MODES: raise HTTPException(400, "Unknown mode")
    cfg["mode"] = b.mode; cfg.save(); return {"mode": b.mode}
@app.get("/api/settings")
def get_set(): t = cfg["tg_token"]; return {"tg_token": ("••••" + t[-4:]) if t else "", "tg_chat": cfg["tg_chat"]}
@app.post("/api/settings")
def put_set(b: Settings):
    if b.tg_token.strip() and not b.tg_token.startswith("••••"): cfg["tg_token"] = b.tg_token.strip()
    cfg["tg_chat"] = b.tg_chat.strip(); cfg.save(); return {"ok": True}
@app.post("/api/telegram/test")
async def tg_test():
    ok, msg = await tg.test()
    if not ok: raise HTTPException(400, msg)
    return {"ok": True, "msg": msg}
@app.websocket("/ws")
async def ws(w: WebSocket): await hub.handle(w)
