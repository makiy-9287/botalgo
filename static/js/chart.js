export const TF = { "1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400 };
export const fmt = x => x == null ? "–" : Number(x).toLocaleString(undefined, { maximumFractionDigits: x < 1 ? 6 : x < 100 ? 4 : 2 });

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
    this.c = []; this.tf = "15m"; this.lines = [];
  }
  set(rows, tf) {
    this.tf = tf; this.c = rows.map(r => ({ time: r[0], open: r[1], high: r[2], low: r[3], close: r[4] }));
    const p = this.c.length ? this.c[this.c.length - 1].close : 1, d = p >= 1000 ? 2 : p >= 100 ? 3 : p >= 1 ? 4 : p >= .1 ? 5 : 6;
    this.ser.applyOptions({ priceFormat: { type: "price", precision: d, minMove: 1 / 10 ** d } });
    this.ser.setData(this.c); this.chart.timeScale().scrollToRealTime();
  }
  tick(p, ts) {
    const L = this.c[this.c.length - 1]; if (!L) return;
    const sec = TF[this.tf], bt = Math.floor(ts / sec) * sec;
    if (bt > L.time) this.c.push({ time: bt, open: p, high: p, low: p, close: p });
    else if (bt === L.time) { L.high = Math.max(L.high, p); L.low = Math.min(L.low, p); L.close = p; }
    else return;
    this.ser.update(this.c[this.c.length - 1]);
  }
  renderSigs(d, on) {
    this.lines.forEach(l => this.ser.removePriceLine(l)); this.lines = [];
    const card = document.getElementById("card");
    if (!on || !d) { this.ser.setMarkers([]); card.style.display = "none"; return; }
    const sec = TF[this.tf], seen = new Set(), m = [];
    for (const s of d.history) {
      const t = Math.floor(s.ts / sec) * sec; if (seen.has(t)) continue; seen.add(t);
      const b = s.side === "BUY";
      m.push({ time: t, position: b ? "belowBar" : "aboveBar", color: b ? "#0ecb81" : "#f6465d", shape: b ? "arrowUp" : "arrowDown", text: s.side + (s.status !== "OPEN" ? " · " + s.status : "") });
    }
    this.ser.setMarkers(m.sort((a, b) => a.time - b.time));
    card.style.display = "block"; const a = d.active;
    if (a) {
      const L = (price, title, color) => this.lines.push(this.ser.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title }));
      L(a.entry, "Entry", "#eaecef"); L(a.sl, "SL", "#f6465d"); L(a.tp1, "TP1", "#0ecb81"); L(a.tp2, "TP2", "#0ecb81");
      card.innerHTML = `<b class="${a.side.toLowerCase()}">${a.side}</b> ${a.sym} · ${a.mode}/${a.tf}${a.tp1_hit ? " · TP1 hit" : ""}` +
        `<div class="g"><span>Entry <b>${fmt(a.entry)}</b></span><span>SL <b>${fmt(a.sl)}</b></span><span>TP1 <b>${fmt(a.tp1)}</b></span><span>TP2 <b>${fmt(a.tp2)}</b></span><span>Score <b>${a.score}/7</b></span></div>`;
    } else card.innerHTML = `<span class="mu">${d.td ? `Scanning · ${d.mode} mode — waiting for a confirmed setup` : "Signals paused — trading days are Mon–Thu (UTC)"}</span>`;
  }
}
