import { api, Socket } from "./api.js";
import { View, TF, fmt } from "./chart.js";
import { Footprint } from "./footprint.js";

const $ = s => document.querySelector(s);
const S = { sym: localStorage.sym || "BTCUSDT", tf: TF[localStorage.tf] ? localStorage.tf : "15m", fp: false, sig: false, wl: [], prices: {}, sigs: null, edit: null, px: 0 };
const view = new View($("#chart")), fp = new Footprint($("#fp"), view);
let tt; const toast = m => { const t = $("#toast"); t.textContent = m; t.classList.add("show"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("show"), 3200); };
const sock = new Socket(onMsg, ok => { if (!ok) feedUI({ state: "offline", error: "Lost connection to server" }); });

function go() {
  localStorage.sym = S.sym; localStorage.tf = S.tf; $("#load").classList.add("show"); fp.clear();
  sock.send({ op: "sub", symbol: S.sym, tf: S.tf, fp: S.fp });
}
function feedUI(h) {
  const e = $("#feed"), st = h.state, cls = st === "live" ? "live" : st === "offline" ? "bad" : "warn";
  e.className = "feed " + cls; e.title = h.error || ""; e.querySelector("em").textContent = st === "live" ? "Live" : st === "stale" ? "No trades" : st === "offline" ? "Offline" : "Connecting";
}
function onMsg(m) {
  switch (m.t) {
    case "snap":
      if (m.s !== S.sym || m.tf !== S.tf) return;
      view.set(m.c, m.tf); S.sigs = m.sigs; view.renderSigs(S.sigs, S.sig); if (m.fp) fp.snap(m.step, m.fp);
      S.wl = m.wl; renderWL(); $("#load").classList.remove("show"); break;
    case "fpsnap": if (m.s === S.sym && m.tf === S.tf) fp.snap(m.step, m.fp); break;
    case "fp": if (S.fp && m.s === S.sym && m.tf === S.tf) fp.upd(m.step, m.b); break;
    case "tick":
      if (m.s !== S.sym) return; view.tick(m.p, m.ts);
      { const e = $("#px"); e.textContent = fmt(m.p); e.className = m.p >= S.px ? "up" : "dn"; S.px = m.p; } break;
    case "prices": S.prices = m.p; document.querySelectorAll("[data-p]").forEach(e => e.textContent = fmt(S.prices[e.dataset.p])); feedUI(m.feed); break;
    case "sigs": if (m.s === S.sym) { S.sigs = m.d; view.renderSigs(S.sigs, S.sig); } break;
    case "wl": S.wl = m.d; renderWL(); break;
    case "err": toast(m.m); $("#load").classList.remove("show");
  }
}

/* header */
const tfs = $("#tfs");
Object.keys(TF).forEach(k => { const b = document.createElement("button"); b.textContent = k; b.onclick = () => { S.tf = k; mark(); go(); }; tfs.append(b); });
const mark = () => [...tfs.children].forEach(b => b.setAttribute("aria-pressed", b.textContent === S.tf));
mark(); $("#sym").value = S.sym;
const applySym = () => { let s = $("#sym").value.toUpperCase().replace(/[^A-Z0-9]/g, ""); if (!s) return; if (!s.endsWith("USDT")) s += "USDT"; $("#sym").value = S.sym = s; go(); };
$("#sym").onchange = applySym; $("#sym").onkeydown = e => { if (e.key === "Enter") { applySym(); e.target.blur(); } };
$("#bfp").onclick = e => {
  S.fp = fp.on = !S.fp; e.currentTarget.setAttribute("aria-pressed", S.fp); sock.send({ op: "fp", on: S.fp }); if (!S.fp) fp.clear(); fp.dirty = true;
};
$("#bsig").onclick = e => { S.sig = !S.sig; e.currentTarget.setAttribute("aria-pressed", S.sig); view.renderSigs(S.sigs, S.sig); };
$("#mode").onchange = async e => { try { await api("/api/mode", { m: "POST", b: { mode: e.target.value } }); toast("Mode: " + e.target.value); } catch (x) { toast(x.message); } };

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
  try { await saveSet(); const r = await api("/api/telegram/test", { m: "POST" }); o.style.color = "var(--up)"; o.textContent = "✓ " + r.msg; }
  catch (x) { o.style.color = "var(--dn)"; o.textContent = "✗ " + x.message; }
  b.disabled = false;
};
$("#bwl").onclick = () => { show($("#drawer"), true); renderWL(); };
$("#xwl").onclick = () => show($("#drawer"), false);

/* watchlist */
function renderWL() {
  if (S.edit) return; $("#cnt").textContent = `${S.wl.length}/10`;
  $("#list").innerHTML = S.wl.length ? S.wl.map(w => `<div class="it" data-s="${w.s}"><span class="n" data-a="open">${w.s}</span>` +
    `${w.sig ? `<span class="tag ${w.sig.side}">${w.sig.side}</span>` : ""}<span class="p" data-p="${w.s}">${fmt(S.prices[w.s] ?? w.p)}</span>` +
    `<button data-a="edit">Edit</button><button data-a="del" aria-label="Remove">✕</button></div>`).join("")
    : '<p class="mu">No pairs yet. Add one above to start scanning it.</p>';
}
$("#list").onclick = async e => {
  const b = e.target.closest("[data-a]"); if (!b) return; const row = b.closest(".it"), s = row.dataset.s, a = b.dataset.a;
  if (a === "open") { S.sym = s; $("#sym").value = s; closeAll(); go(); }
  else if (a === "del") { try { S.wl = await api("/api/watchlist/" + s, { m: "DELETE" }); renderWL(); } catch (x) { toast(x.message); } }
  else if (a === "edit") {
    S.edit = s; row.querySelector(".n").outerHTML = `<input class="ed" list="syms" value="${s}" autocapitalize="characters" autocomplete="off" spellcheck="false">`;
    const i = row.querySelector(".ed"); i.focus(); i.select();
    i.onkeydown = async ev => {
      if (ev.key === "Escape") { S.edit = null; renderWL(); }
      if (ev.key === "Enter") { try { S.wl = await api("/api/watchlist/" + s, { m: "PUT", b: { symbol: i.value } }); S.edit = null; renderWL(); } catch (x) { toast(x.message); } }
    };
    i.onblur = () => setTimeout(() => { if (S.edit === s) { S.edit = null; renderWL(); } }, 200);
  }
};
async function add() {
  const i = $("#ns"), v = i.value.trim(); if (!v) return; $("#badd").disabled = true; $("#wlerr").textContent = "";
  try { S.wl = await api("/api/watchlist", { m: "POST", b: { symbol: v } }); i.value = ""; renderWL(); } catch (e) { $("#wlerr").textContent = e.message; }
  $("#badd").disabled = false;
}
$("#badd").onclick = add; $("#ns").onkeydown = e => { if (e.key === "Enter") add(); };

/* boot */
api("/api/symbols").then(l => { $("#syms").innerHTML = l.map(s => `<option value="${s}">`).join(""); }).catch(() => { });
api("/api/state").then(s => { $("#mode").value = s.mode; S.wl = s.wl; renderWL(); }).catch(e => toast(e.message));
go();
