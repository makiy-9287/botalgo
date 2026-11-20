# Orderflow Terminal
Run: `./run.sh` -> open `http://VPS_IP:8000` (`sudo ufw allow 8000`; change with `PORT=9000 ./run.sh`).
Always-on: copy to /opt/orderflow-terminal, `sudo cp deploy/orderflow.service /etc/systemd/system/ && sudo systemctl enable --now orderflow`.
Lock the port to your own IP: the Telegram token is stored in data/config.json and the site has no login.

## Layout
server/config.py  settings, modes, atomic JSON persistence      server/binance.py  REST client (retry, cache, de-dupe)
server/feed.py    one Binance aggTrade WebSocket, live (un)subscribe  server/footprint.py  per-level bid/ask store
server/engine.py  orderflow signal engine                       server/tracker.py  signal lifecycle TP1/TP2/SL, persisted
server/telegram.py alerts + /status /watchlist /mode /help      server/hub.py      browser WebSocket (ticks, footprint, signals)
server/main.py    FastAPI routes                                static/            UI (vendored chart lib, no CDN)

## What the chart shows
Footprint toggle: bid x ask cells, 300% diagonal imbalances, POC box, visible-range profile with POC/VAH/VAL, session VWAP, Volume/Delta/CumDelta strip, and orderflow confirmation labels (Absorption, Trapped longs/shorts, Stacked buy/sell, Bull/Bear div, delta div, Exhaustion).
Signal toggle: BUY/SELL arrows, Entry/SL/TP lines, and a live confirmation monitor (tap the card to collapse) showing which confirmations are met for BUY and SELL plus the nearest liquidity levels.

## Notes
- Binance retired the old futures WebSocket URLs (/ws, /stream) on 2026-04-23. This app uses wss://fstream.binance.com/market/... If the header says "Live" the feed works; "Live - REST" means WebSocket trades are not arriving and prices come from REST.
- Telegram uses the plain Bot HTTP API through httpx, so no extra package is needed. In Telegram open your bot and press Start before testing. Use your numeric chat ID (groups: negative ID).
- Header dot shows feed health. If it says blocked/451, Binance blocks the VPS region: use a non-US VPS or set BINANCE_REST / BINANCE_WS.
- Footprint builds from live trades after the server starts (no history backfill). Absorption uses footprint data once a bar is fully covered, otherwise volume+wick.
- Signals run 7 days a week. One Binance WebSocket, subscriptions changed live (far under 1024 streams / 10 msgs per s).
