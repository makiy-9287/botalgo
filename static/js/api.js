export async function api(u, o) {
  const r = await fetch(u, o && { method: o.m, headers: { "Content-Type": "application/json" }, body: JSON.stringify(o.b || {}) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "Request failed");
  return j;
}
export class Socket {
  constructor(onmsg, onstate) { this.onmsg = onmsg; this.onstate = onstate; this.last = null; this.back = 500; this.open(); }
  open() {
    const ws = this.ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
    ws.onopen = () => { this.back = 500; this.onstate(true); if (this.last) ws.send(JSON.stringify(this.last)); };
    ws.onmessage = e => { try { this.onmsg(JSON.parse(e.data)); } catch (x) { console.error(x); } };
    ws.onclose = () => { this.onstate(false); setTimeout(() => this.open(), this.back); this.back = Math.min(this.back * 2, 5000); };
  }
  send(o) {
    if (o.op === "sub") this.last = o; else if (o.op === "fp" && this.last) this.last.fp = o.on;
    if (this.ws.readyState === 1) this.ws.send(JSON.stringify(o));
  }
}
