# Orderflow Terminal
Run on VPS: `./run.sh` then open `http://VPS_IP:8000` (open the port in your firewall; set PORT=xxxx to change).
Keep it private: the Telegram token is stored server-side in config.json, so restrict the port to your own IP.
- Chart: candlesticks (Binance USDT-M futures) + Footprint toggle + Signal toggle.
- Footprint/absorption data is collected live from the aggTrade WebSocket, so it fills in from the moment the server (or a new pair) starts.
- Modes: scalping (5m trigger / 15m bias / 1h levels), day (15m/1h/4h), swing (1h/4h/1d). Signals only Mon-Thu UTC.
- Signal = liquidity sweep (mandatory) + >=4 more of: delta divergence, delta shift, absorption, HTF bias+delta, VWAP location, level confluence (>=5 of 7, incl. delta divergence or absorption). SL beyond sweep extreme, TP1 1.5R, TP2 3R.
- After TP/SL the pair resets (short cooldown) and keeps scanning. Watchlist max 10 -> one combined aggTrade stream (far under Binance's 1024-stream / 10 msg/s limits).
