export const TF = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400 };
export const fmt = x => x == null ? "–" : Number(x).toLocaleString(undefined, { maximumFractionDigits: x < 1 ? 6 : x < 100 ? 4 : 2 });
const LBL = { sweep: "Sweep", delta_div: "Δ Div", delta_shift: "Δ Shift", absorption: "Absorb", htf_bias: "HTF", location: "VWAP", confluence: "Confl", stacked: "Stack", trapped: "Trap" };

export class View {
  constructor(el) {
    this.chart = LightweightCharts.createChart(el, {
      autoSize: true, layout: { background: { color: "#0b0e11" }, textColor: "#848e9c", fontSize: 12 },
      grid: { vertLines: { color: "#14181d" }, horzLines: { color: "#14181d" } },
      rightPriceScale: { borderColor: "#2b3139", scaleMargins: { top: .08, bottom: .08 } },
      timeScale: { borderColor: "#2b3139", timeVisible: true, secondsVisible: false, rightOffset: 8, barSpacing: 10 },
      crosshair: { mode: 0 }, kineticScroll: { touch: true, mouse: false }
    });
    this.ser = this.chart.addCandlestickSeries({ upColor: "#0ecb81", downColor: "#f6465d", wickUpColor: "#0ecb81", wickDownColor: "#f6465d", borderVisible: false });
    this.vw = this.chart.addLineSeries({ color: "#f0b90b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, visible: false });
    this.c = []; this.vol = []; this.pv = []; this.cv = []; this.tf = "15m"; this.lines = [];
  }
  set(rows, tf) {
    this.tf = tf; this.c = rows.map(r => ({ time: r[0], open: r[1], high: r[2], low: r[3], close: r[4] })); this.vol = rows.map(r => r[5]);
    const p = this.c.length ? this.c[this.c.length - 1].close : 1, d = p >= 1000 ? 2 : p >= 100 ? 3 : p >= 1 ? 4 : p >= .1 ? 5 : 6;
    this.ser.applyOptions({ priceFormat: { type: "price", precision: d, minMove: 1 / 10 ** d } });
    this.ser.setData(this.c); this.calcVwap(); this.chart.timeScale().scrollToRealTime();
  }
  calcVwap() {   // session VWAP, resets each UTC day
    const out = []; let pv = 0, cv = 0, day = -1; this.pv = []; this.cv = [];
    this.c.forEach((k, i) => {
      const d = Math.floor(k.time / 86400); if (d !== day) { day = d; pv = 0; cv = 0; }
      const tp = (k.high + k.low + k.close) / 3; pv += tp * this.vol[i]; cv += this.vol[i]; this.pv.push(pv); this.cv.push(cv); out.push({ time: k.time, value: cv ? pv / cv : tp });
    });
    this.vw.setData(out);
  }
  vwapTick() {
    const i = this.c.length - 1, k = this.c[i]; if (this.vol.length < i + 1) { this.vol.push(0); this.pv.push(0); this.cv.push(0); }
    const same = i > 0 && Math.floor(this.c[i - 1].time / 86400) === Math.floor(k.time / 86400), bp = same ? this.pv[i - 1] : 0, bv = same ? this.cv[i - 1] : 0, tp = (k.high + k.low + k.close) / 3;
    this.pv[i] = bp + tp * this.vol[i]; this.cv[i] = bv + this.vol[i]; this.vw.update({ time: k.time, value: this.cv[i] ? this.pv[i] / this.cv[i] : tp });
  }
  tick(p, ts) {
    const L = this.c[this.c.length - 1]; if (!L) return;
    const sec = TF[this.tf], bt = Math.floor(ts / sec) * sec;
    if (bt > L.time) this.c.push({ time: bt, open: p, high: p, low: p, close: p });
    else if (bt === L.time) { L.high = Math.max(L.high, p); L.low = Math.min(L.low, p); L.close = p; }
    else return;
    this.ser.update(this.c[this.c.length - 1]); this.vwapTick();
  }
  fpMode(on) {
    this.vw.applyOptions({ visible: on });
    this.chart.priceScale("right").applyOptions({ scaleMargins: { top: .08, bottom: on ? .24 : .08 } });
  }
  renderSigs(d, on) {   // arrows + Entry/SL/TP lines only
    this.lines.forEach(l => this.ser.removePriceLine(l)); this.lines = [];
    if (!on || !d) { this.ser.setMarkers([]); return; }
    const sec = TF[this.tf], seen = new Set(), m = [];
    for (const s of d.history) {
      const t = Math.floor(s.ts / sec) * sec; if (seen.has(t)) continue; seen.add(t); const b = s.side === "BUY";
      m.push({ time: t, position: b ? "belowBar" : "aboveBar", color: b ? "#0ecb81" : "#f6465d", shape: b ? "arrowUp" : "arrowDown", text: s.side + (s.status !== "OPEN" ? " · " + s.status : "") });
    }
    this.ser.setMarkers(m.sort((a, b) => a.time - b.time));
    const a = d.active; if (!a) return;
    const L = (price, title, color) => this.lines.push(this.ser.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title }));
    L(a.entry, "Entry", "#eaecef"); L(a.sl, "SL", "#f6465d"); L(a.tp1, "TP1", "#0ecb81"); L(a.tp2, "TP2", "#0ecb81");
  }
  renderCard(d, mon, on) {   // active signal + live orderflow confirmation monitor
    const card = document.getElementById("card"); if (!on) { card.style.display = "none"; return; }
    card.style.display = "block"; const a = d && d.active; let h = "";
    h += a ? `<div class="sg"><b class="${a.side.toLowerCase()}" style="font-size:14px">${a.side}</b> ${a.sym} · ${a.mode}/${a.tf}${a.tp1_hit ? " · TP1 hit" : ""}` +
      `<div class="g"><span>Entry <b>${fmt(a.entry)}</b></span><span>SL <b>${fmt(a.sl)}</b></span><span>TP1 <b>${fmt(a.tp1)}</b></span><span>TP2 <b>${fmt(a.tp2)}</b></span><span>Score <b>${a.score}/${a.total || 7}</b></span></div></div>`
      : `<div class="mu">Scanning · ${d ? d.mode : ""} mode — no confirmed setup yet</div>`;
    if (mon) {
      const row = (n, s) => !s ? "" : `<div class="mr ${n.toLowerCase()}"><b>${n}</b><span class="sc">${s.score}/${s.total}</span><div class="ch">${Object.entries(s.conf).map(([k, v]) => `<i class="${v ? "ok" : ""}">${LBL[k] || k}</i>`).join("")}</div></div>`;
      const lv = (x, up) => x ? `${up ? "▲" : "▼"} ${fmt(x.p)} (${x.d > 0 ? "+" : ""}${x.d} ATR)` : "";
      h += `<div class="mon"><div class="mu mt">Orderflow confirmations · ${mon.tf} · bias ${mon.bias} · ${mon.fp ? "footprint data" : "candle proxy"}</div>${row("BUY", mon.sides.buy)}${row("SELL", mon.sides.sell)}` +
        `<div class="liq">Liquidity ${lv(mon.levels.hi[0], true)} &nbsp; ${lv(mon.levels.lo[0], false)}</div></div>`;
    }
    card.innerHTML = h;
  }
}
