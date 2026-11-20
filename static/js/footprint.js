const sh = v => { const a = Math.abs(v); return a >= 1000 ? (v / 1000).toFixed(1) + "K" : a >= 100 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : v.toFixed(2); };

export class Footprint {
  constructor(cv, view) {
    this.cv = cv; this.v = view; this.on = false; this.bars = new Map(); this.step = 0; this.sig = ""; this.dirty = true;
    this.loop = this.loop.bind(this); requestAnimationFrame(this.loop);
  }
  snap(step, bars) { this.step = step || 0; this.bars = new Map((bars || []).map(b => [b.t, b.l])); this.dirty = true; }
  upd(step, b) { this.step = step || this.step; this.bars.set(b.t, b.l); this.dirty = true; }
  clear() { this.bars = new Map(); this.dirty = true; }
  loop() {   // redraws only when something visible changed
    const v = this.v, c = v.c; let s = "";
    if (this.on && c.length > 1) {
      const ts = v.chart.timeScale(), l = c[c.length - 1];
      s = [this.cv.clientWidth, this.cv.clientHeight, ts.timeToCoordinate(l.time), ts.timeToCoordinate(c[c.length - 2].time),
        v.ser.priceToCoordinate(l.close), v.ser.priceToCoordinate(l.close * 1.01), this.bars.size].join();
    }
    if (this.dirty || s !== this.sig) { this.sig = s; this.dirty = false; this.draw(); }
    requestAnimationFrame(this.loop);
  }
  draw() {
    const cv = this.cv, w = cv.clientWidth, h = cv.clientHeight, d = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(w * d) || cv.height !== Math.round(h * d)) { cv.width = Math.round(w * d); cv.height = Math.round(h * d); }
    const g = cv.getContext("2d"); g.setTransform(d, 0, 0, d, 0, 0); g.clearRect(0, 0, w, h);
    const v = this.v, c = v.c; if (!this.on || c.length < 2) return;
    const ts = v.chart.timeScale(), bs = Math.abs(ts.timeToCoordinate(c[c.length - 1].time) - ts.timeToCoordinate(c[c.length - 2].time));
    if (!(bs > 6)) return;
    if (!this.bars.size) {
      g.fillStyle = "#848e9c"; g.textAlign = "center"; g.font = "13px Inter,sans-serif";
      g.fillText("Collecting live trades… the footprint builds from now on", w / 2, 60); return;
    }
    const st = this.step || 1, bw = Math.max(2, bs * .86), ix = p => Math.round(p / st); g.textBaseline = "middle";
    for (const [t, lv] of this.bars) {
      const x = ts.timeToCoordinate(t); if (x == null || x < -bs || x > w + bs) continue;
      const m = new Map(); let mx = 1, poc = null, dl = 0;
      for (const [p, b, a] of lv) { m.set(ix(p), [b, a]); dl += a - b; if (b + a > mx) { mx = b + a; poc = ix(p); } }
      for (const [p, b, a] of lv) {
        const y1 = v.ser.priceToCoordinate(p + st), y2 = v.ser.priceToCoordinate(p); if (y1 == null || y2 == null || y2 < -10 || y1 > h + 10) continue;
        const ch = y2 - y1, k = Math.min(1, (a + b) / mx), i = ix(p);
        g.fillStyle = a >= b ? `rgba(14,203,129,${.1 + .4 * k})` : `rgba(246,70,93,${.1 + .4 * k})`; g.fillRect(x - bw / 2, y1 + .5, bw, Math.max(1, ch - 1));
        const lo = m.get(i - 1), hi = m.get(i + 1); g.lineWidth = 1.2;
        if (a >= mx * .05 && a >= 3 * (lo ? lo[0] : 0)) { g.strokeStyle = "#0ecb81"; g.strokeRect(x, y1 + .5, bw / 2, Math.max(1, ch - 1)); }   // buy imbalance (diagonal)
        if (b >= mx * .05 && b >= 3 * (hi ? hi[1] : 0)) { g.strokeStyle = "#f6465d"; g.strokeRect(x - bw / 2, y1 + .5, bw / 2, Math.max(1, ch - 1)); }   // sell imbalance
        if (i === poc) { g.strokeStyle = "#f0b90b"; g.lineWidth = 1.6; g.strokeRect(x - bw / 2, y1 + .5, bw, Math.max(1, ch - 1)); }
        if (bs > 38 && ch >= 9) {
          g.font = `${Math.min(11, ch - 2)}px Inter,sans-serif`; g.fillStyle = "#eaecef";
          g.textAlign = "right"; g.fillText(sh(b), x - 2, y1 + ch / 2); g.textAlign = "left"; g.fillText(sh(a), x + 2, y1 + ch / 2);
        }
      }
      if (bs > 30) { g.font = "bold 10px Inter,sans-serif"; g.textAlign = "center"; g.fillStyle = dl >= 0 ? "#0ecb81" : "#f6465d"; g.fillText((dl >= 0 ? "+" : "") + sh(dl), x, h - 10); }
    }
  }
}
