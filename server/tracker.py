import time
from .config import Store, TFS

class Tracker:
    def __init__(self, notify, emit):
        self.st = Store("signals.json", {"active": {}, "history": []}); self.notify, self.emit, self.cool = notify, emit, {}
    @property
    def active(self): return self.st["active"]
    def open(self, sg):
        self.active[sg["sym"]] = sg; self.st["history"] = (self.st["history"] + [sg])[-300:]; self.st.save(); self.emit()
    def on_price(self, s, p):
        sg = self.active.get(s)
        if not sg: return
        L = sg["side"] == "BUY"
        if (p <= sg["sl"]) if L else (p >= sg["sl"]): return self.finish(sg, "TP1 then SL" if sg["tp1_hit"] else "SL")
        if (p >= sg["tp2"]) if L else (p <= sg["tp2"]): return self.finish(sg, "TP2")
        if not sg["tp1_hit"] and ((p >= sg["tp1"]) if L else (p <= sg["tp1"])):
            sg["tp1_hit"] = True; self.st.save(); self.emit()
            self.notify(f"✅ <b>{s}</b> {sg['side']} — TP1 hit at <code>{sg['tp1']}</code>")
    def finish(self, sg, status):
        sg["status"], sg["closed"] = status, int(time.time()); self.active.pop(sg["sym"], None)
        self.cool[sg["sym"]] = time.time() + 3 * TFS[sg["tf"]]; self.st.save(); self.emit()
        icon = "🎯" if status == "TP2" else "🛑" if status == "SL" else "⚠️"
        self.notify(f"{icon} <b>{sg['sym']}</b> {sg['side']} closed: <b>{status}</b>\nPair reset — scanning again.")
    def history(self, sym): return [x for x in self.st["history"] if x["sym"] == sym][-40:]
