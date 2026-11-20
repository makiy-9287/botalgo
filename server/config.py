import json, os
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"; DATA.mkdir(exist_ok=True)
REST = os.getenv("BINANCE_REST", "https://fapi.binance.com").rstrip("/")
WSURL = os.getenv("BINANCE_WS", "wss://fstream.binance.com").rstrip("/")
TFS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
MODES = {"scalping": ("5m", "15m", "1h"), "day": ("15m", "1h", "4h"), "swing": ("1h", "4h", "1d")}  # trigger, bias, levels
MAX_WL = 10

class Store(dict):
    def __init__(self, name, default):
        super().__init__(json.loads(json.dumps(default))); self.path = DATA / name
        try: self.update(json.loads(self.path.read_text()))
        except Exception: pass
    def save(self):
        t = self.path.with_suffix(".tmp"); t.write_text(json.dumps(self)); os.replace(t, self.path)

cfg = Store("config.json", {"watchlist": ["BTCUSDT", "ETHUSDT"], "mode": "day", "tg_token": "", "tg_chat": ""})
