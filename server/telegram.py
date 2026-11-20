import asyncio, httpx
from .config import cfg

class Telegram:
    def __init__(self): self.http = httpx.AsyncClient(timeout=httpx.Timeout(12, connect=6))
    @property
    def ready(self): return bool(cfg["tg_token"] and cfg["tg_chat"])
    def notify(self, text): asyncio.create_task(self.send(text))
    async def send(self, text):
        if not self.ready: return False, "Add the bot token and chat ID in Settings first"
        err = "Unknown error"
        for i in range(3):
            try:
                r = await self.http.post(f"https://api.telegram.org/bot{cfg['tg_token']}/sendMessage",
                    json={"chat_id": cfg["tg_chat"], "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
                j = r.json()
                if j.get("ok"): return True, ""
                err = j.get("description", "Telegram error")
                if r.status_code == 429: await asyncio.sleep(j.get("parameters", {}).get("retry_after", 2)); continue
                if "chat not found" in err.lower(): err += " — open your bot in Telegram and press Start first (groups use a negative chat ID)"
                return False, err
            except Exception as e:
                err = f"Cannot reach Telegram from this server ({type(e).__name__})"; await asyncio.sleep(1)
        return False, err
    async def test(self):
        if not self.ready: return False, "Add the bot token and chat ID first"
        try:
            j = (await self.http.get(f"https://api.telegram.org/bot{cfg['tg_token']}/getMe")).json()
            if not j.get("ok"): return False, "Invalid bot token — copy it exactly from @BotFather"
            name = j["result"]["username"]
        except Exception as e: return False, f"Cannot reach Telegram from this server ({type(e).__name__})"
        ok, err = await self.send("✅ <b>Orderflow Terminal</b>: test notification works.")
        return ok, (f"Sent via @{name}" if ok else err)
    async def poll(self, handle):
        off = 0
        while True:
            if not self.ready: await asyncio.sleep(5); continue
            try:
                j = (await self.http.post(f"https://api.telegram.org/bot{cfg['tg_token']}/getUpdates",
                     json={"offset": off, "timeout": 25, "allowed_updates": ["message"]}, timeout=35)).json()
                if not j.get("ok"): await asyncio.sleep(10); continue
                for u in j["result"]:
                    off = u["update_id"] + 1; m = u.get("message") or {}; t = (m.get("text") or "").strip()
                    if t.startswith("/") and str(m.get("chat", {}).get("id")) == str(cfg["tg_chat"]):
                        c, *a = t.split(); await self.send(handle(c.split("@")[0].lower(), a))
            except asyncio.CancelledError: raise
            except Exception: await asyncio.sleep(5)
