const sh = v => { const a = Math.abs(v); return a >= 1000 ? (v / 1000).toFixed(1) + "K" : a >= 100 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : v.toFixed(2); };
const label = e => ({ abs: "Absorption", trap: e.s === "bull" ? "Trapped shorts" : "Trapped longs", stack: e.s === "bull" ? "Stacked buy" : "Stacked sell", div: e.s === "bull" ? "Bull div" : "Bear div", sdiv: "Δ div", exh: "Exhaustion" })[e.k] || e.k;

export class Footprint {
  constructor(cv, view) {
    this.cv = cv; this.v = view; this.on = false; this.bars = new Map(); this.step = 0; this.sig = ""; this.dirty = true;
    this.loop = this.loop.bind(this); requestAnimationFrame(this.loop);
  }
  snap(step, bars) { this.step = step || 0; this.bars = new Map((bars || []).map(b => [b.t, b])); this.dirty = true; }
  upd(step, b) { this.step = step || this.step; this.bars.set(b.t, b); this.dirty = true; }
  clear() { this.bars = new Map(); this.dirty = true; }
  loop() {   // redraws only when something visible changed
    const v = this.v, c = v.c; let s = "";
    if (this.on && c.length > 1) {
      const ts = v.chart.timeScale(), l = c[c.length - 1];
      s = [this.cv.clientWidth, this.cv.clientHeight, ts.timeToCoordinate(l.time), ts.timeToCoordinate(c[c.length - 2].time), v.ser.priceToCoordinate(l.close), v.ser.priceToCoordinate(l.close * 1.01), this.bars.size].join();
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
    if (!this.bars.size) { g.fillStyle = "#848e9c"; g.textAlign = "center"; g.font = "13px Inter,sans-serif"; g.fillText("Collecting trades… footprint fills in a few seconds", w / 2, 70); return; }
    const axW = v.chart.priceScale("right").width(), axH = ts.height ? ts.height() : 26, pw = w - axW, ph = h - axH, sy = ph - 46;
    const st = this.step || 1, bw = Math.max(2, bs * .86), ix = p => Math.round(p / st), Y = p => v.ser.priceToCoordinate(p);
    g.save(); g.beginPath(); g.rect(0, 0, pw, ph); g.clip(); g.textBaseline = "middle";
    const vis = [], stats = new Map(); let cum = 0;
    for (const t of [...this.bars.keys()].sort((a, b) => a - b)) {
      const b = this.bars.get(t); let vol = 0, dl = 0; for (const [, bd, a] of b.l) { vol += bd + a; dl += a - bd; } cum += dl; stats.set(t, { vol, dl, cum });
      const x = ts.timeToCoordinate(t); if (x != null && x > -bs && x < pw + bs) vis.push([x, b]);
    }
    /* cells */
    for (const [x, b] of vis) {
      const m = new Map(); let mx = 1, poc = null;
      for (const [p, bd, a] of b.l) { m.set(ix(p), [bd, a]); if (bd + a > mx) { mx = bd + a; poc = ix(p); } }
      for (const [p, bd, a] of b.l) {
        const y1 = Y(p + st), y2 = Y(p); if (y1 == null || y2 == null || y2 < -10 || y1 > ph + 10) continue;
        const ch = y2 - y1, k = Math.min(1, (a + bd) / mx), i = ix(p), hh = Math.max(1, ch - 1);
        g.fillStyle = a >= bd ? `rgba(14,203,129,${.1 + .4 * k})` : `rgba(246,70,93,${.1 + .4 * k})`; g.fillRect(x - bw / 2, y1 + .5, bw, hh);
        const lo = m.get(i - 1), hi = m.get(i + 1); g.lineWidth = 1.2;
        if (a >= mx * .05 && a >= 3 * (lo ? lo[0] : 0)) { g.strokeStyle = "#0ecb81"; g.strokeRect(x, y1 + .5, bw / 2, hh); }
        if (bd >= mx * .05 && bd >= 3 * (hi ? hi[1] : 0)) { g.strokeStyle = "#f6465d"; g.strokeRect(x - bw / 2, y1 + .5, bw / 2, hh); }
        if (i === poc) { g.strokeStyle = "#f0b90b"; g.lineWidth = 1.6; g.strokeRect(x - bw / 2, y1 + .5, bw, hh); }
        if (bs > 38 && ch >= 9) { g.font = `${Math.min(11, ch - 2)}px Inter,sans-serif`; g.fillStyle = "#eaecef"; g.textAlign = "right"; g.fillText(sh(bd), x - 2, y1 + ch / 2); g.textAlign = "left"; g.fillText(sh(a), x + 2, y1 + ch / 2); }
      }
    }
    /* visible-range profile with POC / VAH / VAL */
    const agg = new Map(); let tot = 0;
    for (const [, b] of vis) for (const [p, bd, a] of b.l) { const i = ix(p), o = agg.get(i) || 0; agg.set(i, o + bd + a); tot += bd + a; }
    if (agg.size) {
      const keys = [...agg.keys()].sort((a, b) => a - b), lo = keys[0], hi = keys[keys.length - 1], val = i => agg.get(i) || 0;
      let poc = keys[0]; for (const k of keys) if (val(k) > val(poc)) poc = k;
      let vl = poc, vh = poc, acc = val(poc);
      while (acc < .7 * tot && (vl > lo || vh < hi)) { const u = vh < hi ? val(vh + 1) : -1, dn = vl > lo ? val(vl - 1) : -1; if (u >= dn) { vh++; acc += val(vh); } else { vl--; acc += val(vl); } }
      const mxv = val(poc), len = Math.min(90, pw * .2), xr = pw - 2;
      for (let i = lo; i <= hi; i++) {
        const y1 = Y((i + 1) * st), y2 = Y(i * st); if (y1 == null || y2 == null) continue;
        g.fillStyle = i === poc ? "rgba(240,185,11,.85)" : i >= vl && i <= vh ? "rgba(70,120,235,.6)" : "rgba(70,120,235,.28)"; const L = val(i) / mxv * len; g.fillRect(xr - L, y1 + .5, L, Math.max(1, y2 - y1 - 1));
      }
      const line = (price, col, txt) => { const y = Y(price); if (y == null) return; g.strokeStyle = col; g.lineWidth = 1; g.setLineDash([5, 4]); g.beginPath(); g.moveTo(0, y); g.lineTo(pw - len - 4, y); g.stroke(); g.setLineDash([]);
        g.fillStyle = col; g.font = "bold 10px Inter,sans-serif"; g.textAlign = "right"; g.fillText(txt, pw - len - 8, y - 6); };
      line((poc + .5) * st, "#f0b90b", "POC"); line((vh + 1) * st, "#848e9c", "VAH"); line(vl * st, "#848e9c", "VAL");
    }
    /* volume / delta / cumulative delta strip */
    g.fillStyle = "rgba(11,14,17,.94)"; g.fillRect(0, sy, pw, 46); g.fillStyle = "#2b3139"; g.fillRect(0, sy, pw, 1);
    g.font = "10px Inter,sans-serif"; g.textAlign = "left"; g.fillStyle = "#5e6673"; g.fillText("Vol", 4, sy + 9); g.fillText("Δ", 4, sy + 23); g.fillText("ΣΔ", 4, sy + 37);
    let md = 1; for (const [, b] of vis) md = Math.max(md, Math.abs(stats.get(b.t).dl));
    for (const [x, b] of vis) {
      const s = stats.get(b.t); g.textAlign = "center";
      if (bs > 34) { g.fillStyle = "#848e9c"; g.fillText(sh(s.vol), x, sy + 9); g.fillStyle = s.dl >= 0 ? "#0ecb81" : "#f6465d"; g.fillText((s.dl >= 0 ? "+" : "") + sh(s.dl), x, sy + 23); g.fillStyle = s.cum >= 0 ? "#0ecb81" : "#f6465d"; g.fillText(sh(s.cum), x, sy + 37); }
      else { const hh = Math.max(1, Math.abs(s.dl) / md * 14); g.fillStyle = s.dl >= 0 ? "#0ecb81" : "#f6465d"; g.fillRect(x - Math.max(1, bs * .3), s.dl >= 0 ? sy + 30 - hh : sy + 30, Math.max(2, bs * .6), hh); }
    }
    /* orderflow confirmation labels */
    for (const [x, b] of vis) {
      let up = 0, dn = 0;
      for (const e of b.ev || []) {
        const y = Y(e.p); if (y == null) continue; const bull = e.s === "bull", col = bull ? "#0ecb81" : "#f6465d";
        if (bs < 36) { const yy = bull ? y + 8 + dn++ * 8 : y - 8 - up++ * 8; g.fillStyle = col; g.beginPath(); g.moveTo(x, bull ? yy - 4 : yy + 4); g.lineTo(x - 4, bull ? yy + 3 : yy - 3); g.lineTo(x + 4, bull ? yy + 3 : yy - 3); g.fill(); continue; }
        const txt = label(e); g.font = "600 10px Inter,sans-serif"; const tw = g.measureText(txt).width + 10, yy = bull ? y + 12 + dn++ * 17 : y - 12 - up++ * 17;
        g.fillStyle = bull ? "rgba(14,203,129,.18)" : "rgba(246,70,93,.18)"; g.fillRect(x - tw / 2, yy - 8, tw, 16); g.strokeStyle = col; g.lineWidth = 1; g.strokeRect(x - tw / 2 + .5, yy - 7.5, tw - 1, 15);
        g.fillStyle = col; g.textAlign = "center"; g.fillText(txt, x, yy);
      }
    }
    g.restore();
  }
}
