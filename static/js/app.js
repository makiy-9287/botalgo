import { api, Socket } from "./api.js";
import { View, TF, fmt } from "./chart.js";
import { Footprint } from "./footprint.js";

const $ = s => document.querySelector(s);
const S = { sym: localStorage.sym || "BTCUSDT", tf: TF[localStorage.tf] ? localStorage.tf : "15m", fp: false, sig: false, wl: [], prices: {}, sigs: null, mon: null, edit: null, px: 0 };
let SYMS = [], goId = 0;
const view = new View($("#chart")), fp = new Footprint($("#fp"), view);
let tt; const toast = m => { const t = $("#toast"); t.textContent = m; t.classList.add("show"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("show"), 3400); };
const sock = new Socket(onMsg, ok => { if (!ok) feedUI({ state: "offline", error: "Lost connection to server" }); });
const refreshSig = () => { view.renderSigs(S.sigs, S.sig); view.renderCard(S.sigs, S.mon, S.sig); };

function go() {
  localStorage.sym = S.sym; localStorage.tf = S.tf; $("#load").classList.add("show"); fp.clear(); S.mon = null; const my = ++goId;
  sock.send({ op: "sub", symbol: S.sym, tf: S.tf, fp: S.fp });
  setTimeout(() => { if (my === goId && $("#load").classList.contains("show")) { sock.send({ op: "sub", symbol: S.sym, tf: S.tf, fp: S.fp }); setTimeout(() => { if (my === goId) { $("#load").classList.remove("show"); toast("Slow response from Binance — still retrying"); } }, 6000); } }, 6000);
}
function feedUI(h) {
  const e = $("#feed"), st = h.state, bad = st === "offline", ok = st === "live" && !h.rest;
  e.className = "feed " + (ok ? "live" : bad ? "bad" : "warn"); e.title = h.error || "";
  e.querySelector("em").textContent = ok ? "Live" : h.rest ? "Live · REST" : st === "stale" ? "No trades" : bad ? "Offline" : "Connecting";
}
function onMsg(m) {
  switch (m.t) {
    case "snap":
      if (m.s !== S.sym || m.tf !== S.tf) return;
      view.set(m.c, m.tf); S.sigs = m.sigs; if (m.fp) fp.snap(m.step, m.fp); refreshSig(); S.wl = m.wl; renderWL(); $("#load").classList.remove("show"); break;
    case "fpsnap": if (S.fp && m.s === S.sym && m.tf === S.tf) fp.snap(m.step, m.fp); break;
    case "fp": if (S.fp && m.s === S.sym && m.tf === S.tf) fp.upd(m.step, m.b); break;
    case "tick": if (m.s !== S.sym) return; view.tick(m.p, m.ts); { const e = $("#px"); e.textContent = fmt(m.p); e.className = m.p >= S.px ? "up" : "dn"; S.px = m.p; } break;
    case "prices": S.prices = m.p; document.querySelectorAll("[data-p]").forEach(e => e.textContent = fmt(S.prices[e.dataset.p])); feedUI(m.feed); break;
    case "sigs": if (m.s === S.sym) { S.sigs = m.d; refreshSig(); } break;
    case "mon": if (m.s === S.sym) { S.mon = m.d; view.renderCard(S.sigs, S.mon, S.sig); } break;
    case "wl": S.wl = m.d; renderWL(); break;
    case "err": toast(m.m); $("#load").classList.remove("show");
  }
}

/* pair search (works on mobile, validates against Binance's real list) */
const norm = v => v.toUpperCase().replace(/[^A-Z0-9]/g, "");
function resolve(v) {
  const q = norm(v); if (!q) return null; if (!SYMS.length) return q.endsWith("USDT") ? q : q + "USDT";
  return SYMS.includes(q) ? q : SYMS.includes(q + "USDT") ? q + "USDT" : (SYMS.find(s => s.startsWith(q)) || null);
}
function picker(input, onEnter) {
  const box = document.createElement("div"); box.className = "sugg"; document.body.append(box); let items = [], hi = 0;
  const hide = () => box.classList.remove("show");
  const paint = () => { box.innerHTML = items.map((s, i) => `<div data-s="${s}" class="${i === hi ? "a" : ""}">${s.replace("USDT", "")}<em>USDT</em></div>`).join(""); };
  const render = () => {
    const q = norm(input.value); if (!q || !SYMS.length) return hide();
    items = SYMS.filter(s => s.startsWith(q)).concat(SYMS.filter(s => !s.startsWith(q) && s.includes(q))).slice(0, 8); hi = 0; if (!items.length) return hide();
    const r = input.getBoundingClientRect(); Object.assign(box.style, { left: r.left + "px", top: r.bottom + 4 + "px", width: Math.max(r.width, 170) + "px" }); paint(); box.classList.add("show");
  };
  input.addEventListener("input", render); input.addEventListener("focus", render); input.addEventListener("blur", () => setTimeout(hide, 200));
  box.addEventListener("pointerdown", e => e.preventDefault());
  box.addEventListener("click", e => { const d = e.target.closest("[data-s]"); if (d) { input.value = d.dataset.s; hide(); onEnter(d.dataset.s); } });
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (items.length) { hi = (hi + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length; paint(); } }
    else if (e.key === "Enter") { e.preventDefault(); const pick = box.classList.contains("show") && items[hi] ? items[hi] : resolve(input.value); hide(); onEnter(pick); }
  });
}
function applySym(s) {
  if (!s) { toast("Pair not found on Binance USDT-M futures"); $("#sym").value = S.sym; return; }
  $("#sym").value = S.sym = s; $("#sym").blur(); go();
}
picker($("#sym"), applySym);

/* header */
const tfs = $("#tfs");
Object.keys(TF).forEach(k => { const b = document.createElement("button"); b.textContent = k; b.onclick = () => { S.tf = k; mark(); go(); }; tfs.append(b); });
const mark = () => [...tfs.children].forEach(b => b.setAttribute("aria-pressed", b.textContent === S.tf));
mark(); $("#sym").value = S.sym;
$("#bfp").onclick = e => { S.fp = fp.on = !S.fp; e.currentTarget.setAttribute("aria-pressed", S.fp); view.fpMode(S.fp); sock.send({ op: "fp", on: S.fp }); if (!S.fp) fp.clear(); fp.dirty = true; };
$("#bsig").onclick = e => { S.sig = !S.sig; e.currentTarget.setAttribute("aria-pressed", S.sig); refreshSig(); };
$("#card").onclick = () => $("#card").classList.toggle("min");
$("#mode").onchange = async e => { try { await api("/api/mode", { m: "POST", b: { mode: e.target.value } }); toast("Mode: " + e.target.value); S.mon = null; } catch (x) { toast(x.message); } };

/* modal + drawer */
const show = (el, v) => el.classList.toggle("show", v);
const closeAll = () => { show($("#scrim"), false); show($("#drawer"), false); };
document.addEventListener("keydown", e => { if (e.key === "Escape") closeAll(); });
$("#bset").onclick = async () => { try { const s = await api("/api/settings"); $("#tt").value = s.tg_token; $("#tc").value = s.tg_chat; } catch (e) { } $("#tgmsg").textContent = ""; show($("#scrim"), true); };
$("#bclose").onclick = () => show($("#scrim"), false);
$("#scrim").onclick = e => { if (e.target.id === "scrim") show($("#scrim"), false); };
const saveSet = () => api("/api/settings", { m: "POST", b: { tg_token: $("#tt").value, tg_chat: $("#tc").value } });
$("#bsave").onclick = async () => { try { await saveSet(); toast("Settings saved"); show($("#scrim"), false); } catch (e) { toast(e.message); } };
$("#btest").onclick = async e => {
  const b = e.currentTarget, o = $("#tgmsg"); b.disabled = true; o.style.color = ""; o.textContent = "Sending…";
  try { await saveSet(); const r = await api("/api/telegram/test", { m: "POST" }); o.style.color = "var(--up)"; o.textContent = "✓ " + r.msg; } catch (x) { o.style.color = "var(--dn)"; o.textContent = "✗ " + x.message; }
  b.disabled = false;
};
$("#bwl").onclick = () => { show($("#drawer"), true); renderWL(); };
$("#xwl").onclick = () => show($("#drawer"), false);

/* watchlist */
function renderWL() {
  if (S.edit) return; $("#cnt").textContent = `${S.wl.length}/10`;
  $("#list").innerHTML = S.wl.length ? S.wl.map(w => `<div class="it" data-s="${w.s}"><span class="n" data-a="open">${w.s}</span>` +
    `${w.sig ? `<span class="tag ${w.sig.side}">${w.sig.side}</span>` : ""}<span class="p" data-p="${w.s}">${fmt(S.prices[w.s] ?? w.p)}</span>` +
    `<button data-a="edit">Edit</button><button data-a="del" aria-label="Remove">✕</button></div>`).join("") : '<p class="mu">No pairs yet. Add one above to start scanning it.</p>';
}
$("#list").onclick = async e => {
  const b = e.target.closest("[data-a]"); if (!b) return; const row = b.closest(".it"), s = row.dataset.s, a = b.dataset.a;
  if (a === "open") { S.sym = s; $("#sym").value = s; closeAll(); go(); }
  else if (a === "del") { try { S.wl = await api("/api/watchlist/" + s, { m: "DELETE" }); renderWL(); } catch (x) { toast(x.message); } }
  else if (a === "edit") {
    S.edit = s; row.querySelector(".n").outerHTML = `<input class="ed" value="${s}" autocapitalize="characters" autocomplete="off" spellcheck="false">`;
    const i = row.querySelector(".ed"); i.focus(); i.select();
    const save = async p => { const n = p && resolve(p); if (!n) return toast("Pair not found"); try { S.wl = await api("/api/watchlist/" + s, { m: "PUT", b: { symbol: n } }); S.edit = null; renderWL(); } catch (x) { toast(x.message); } };
    picker(i, save); i.addEventListener("keydown", ev => { if (ev.key === "Escape") { S.edit = null; renderWL(); } });
    i.onblur = () => setTimeout(() => { if (S.edit === s) { S.edit = null; renderWL(); } }, 300);
  }
};
async function add(pick) {
  const i = $("#ns"), n = pick && resolve(typeof pick === "string" ? pick : i.value); if (!i.value.trim()) return;
  if (!n) { $("#wlerr").textContent = "Pair not found on Binance USDT-M futures"; return; }
  $("#badd").disabled = true; $("#wlerr").textContent = "";
  try { S.wl = await api("/api/watchlist", { m: "POST", b: { symbol: n } }); i.value = ""; renderWL(); } catch (e) { $("#wlerr").textContent = e.message; }
  $("#badd").disabled = false;
}
picker($("#ns"), add); $("#badd").onclick = () => add(true);

/* boot */
api("/api/symbols").then(l => { SYMS = l; }).catch(() => { });
api("/api/state").then(s => { $("#mode").value = s.mode; S.wl = s.wl; renderWL(); }).catch(e => toast(e.message));
go();
