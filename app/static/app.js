// Single-page interface. Rights are enforced by the server; the interface only hides what a role cannot use.
const $ = (s, r = document) => r.querySelector(s);
const view = $("#view");
let ME = null, META = null, DEB = null;
// the names from the database: a region by its Russian name or an object with name_ru / name_uz, in the language of the interface (the Uzbek one when there is one)
const rname = s => LANG === "uz" && META && (META.regions || []).some(r => r.name_ru === s && r.name_uz) ? META.regions.find(r => r.name_ru === s).name_uz : s;
const nm = o => (LANG === "uz" && o.name_uz) || o.name_ru || o.name || "";
const NAMES = { beds_total: "Всего коек", occ_pregnant: "Занято: беременные", occ_children: "Занято: дети", extreme_pregnant: "Крайне тяжёлые: беременные", extreme_children: "Крайне тяжёлые: дети", visits: "Обращения", severe: "Тяжёлые", extreme: "Крайне тяжёлые", hosp: "Госпитализации", disch: "Выписки", beds_occupied: "Занято коек", occupancy: "Загрузка, %", beds_free: "Свободно коек", beds_flu: "Коек для гриппа и ОРВИ" };
const STATE = { sent: "Отправлен", corrected: "Исправлен", returned: "Возвращён", not_sent: "Не отправлен", overdue: "Просрочен", normal: "Норма", elevated: "Повышенная", critical: "Критическая", none: "—" };

async function api(path, opt = {}) {
  const o = { method: opt.method || "GET", headers: {} };
  if (opt.body !== undefined) { o.body = JSON.stringify(opt.body); o.headers["Content-Type"] = "application/json"; }
  if (opt.form) o.body = opt.form;
  const r = await fetch(path, o);
  if (r.status === 401) { location.href = "/login"; throw new Error("auth"); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(TS(j.error) || T("Ошибка") + " " + r.status); e.details = j.details; throw e; }
  return j;
}
function toast(m) { const t = $("#toast"); t.textContent = m; t.style.display = "block"; clearTimeout(toast.t); toast.t = setTimeout(() => t.style.display = "none", 3500); }
const fail = e => {
  if (e.message === "auth") return;
  if (e instanceof TypeError && /of null/.test(e.message)) { console.debug("a late answer for a page that is no longer open was ignored:", e.message); return; }   // not an error for the person
  toast(e.message);
};
function qs(o) { return Object.entries(o).filter(([, v]) => v !== "" && v != null).map(([k, v]) => k + "=" + encodeURIComponent(v)).join("&"); }
const num = v => v == null ? "—" : (+v).toLocaleString(LOCALE, { maximumFractionDigits: 1 });
function modal(html, wide) { $("#modal").innerHTML = `<div class="modal${wide ? " wide" : ""}">${html}</div>`; $("#modal").onclick = ev => { if (ev.target.id === "modal") closeModal(); }; }
document.addEventListener("click", e => { if (e.target.closest("[data-close]")) closeModal(); });
// a confirmation with an optional required reason; onOk(reason) runs on "ok"
function confirmDlg(title, html, okLabel, onOk, needReason) {
  modal(`<h2>${title}</h2>${html}${needReason ? `<label>Причина (попадёт в журнал)<textarea id="cf-reason" rows="2"></textarea></label>` : ""}<div id="cf-err" class="err"></div><div class="row mt"><button class="btn bad" id="cf-ok">${okLabel}</button><button class="btn right" data-close>Отмена</button></div>`);
  $("#cf-ok").onclick = async () => {
    const reason = needReason ? $("#cf-reason").value.trim() : "";
    if (needReason && !reason) { $("#cf-err").textContent = "Укажите причину"; return; }
    $("#cf-ok").disabled = true;
    try { await onOk(reason); } catch (e) { $("#cf-err").textContent = e.message; $("#cf-ok").disabled = false; }
  };
}
// A refresh that does not redraw: the new HTML is built off-screen and only what differs is changed in the live page, so nothing that stayed the same is
// replaced (no animations restart, no hover or typing is lost). Children are matched by id / data-rid / data-id when they have one, otherwise by position.
const keyOf = n => n.nodeType === 1 ? (n.id || n.getAttribute("data-rid") || n.getAttribute("data-id") || "") : "";
function patchNode(x, y) {
  if (x.nodeType !== y.nodeType || x.nodeName !== y.nodeName) { const c = document.importNode(y, true); x.replaceWith(c); return c; }
  if (x.nodeType !== 1) { if (x.nodeValue !== y.nodeValue) x.nodeValue = y.nodeValue; return x; }
  if (x.id !== "map-tip") {                                    // the tooltip is driven by the pointer, not by the data
    for (const a of y.attributes) if (x.getAttribute(a.name) !== a.value) x.setAttribute(a.name, a.value);
    for (const a of [...x.attributes]) if (!y.hasAttribute(a.name)) x.removeAttribute(a.name);
  }
  if (!(y.hasAttribute("data-keep") && x.firstChild)) patchChildren(x, y);   // filled by its own loader: the loader patches it
  return x;
}
function patchChildren(a, b) {
  const old = [...a.childNodes], keyed = new Map(), used = new Set(), out = [];
  old.forEach(n => { const k = keyOf(n); if (k && !keyed.has(k)) keyed.set(k, n); });
  let oi = 0;
  for (const y of b.childNodes) {
    const k = keyOf(y);
    let x = null;
    if (k) x = keyed.get(k) || null;
    else { while (oi < old.length && (used.has(old[oi]) || keyOf(old[oi]))) oi++; if (oi < old.length) x = old[oi++]; }
    if (x && !used.has(x)) { used.add(x); out.push(patchNode(x, y)); } else out.push(document.importNode(y, true));
  }
  old.forEach(n => { if (!used.has(n)) n.remove(); });
  out.forEach((n, i) => { if (a.childNodes[i] !== n) a.insertBefore(n, a.childNodes[i] || null); });
}
function morph(el, html) { const t = document.createElement("template"); t.innerHTML = html; patchChildren(el, t.content); }
const put = (el, html, silent) => { if (silent && el.firstChild) morph(el, html); else el.innerHTML = html; };
// `H(el, silent).innerHTML = html` reads like the plain assignment but patches instead of replacing when silent
const H = (el, silent) => ({ set innerHTML(v) { put(el, v, silent); } });
function closeModal() { $("#modal").innerHTML = ""; }
function pill(state) { return `<span class="pill ${state}">${STATE[state] || state}</span>`; }
function opts(items, val, all) { return (all ? `<option value="">${all}</option>` : "") + items.map(i => `<option value="${i.id}" ${String(i.id) === String(val) ? "selected" : ""}>${esc(i.name_ru || i.name)}</option>`).join(""); }
const iso = d => d.toISOString().slice(0, 10);
const addDays = (s, n) => { const d = new Date(s + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return iso(d); };

// ---------- shared filter bar
const F = { preset: "day", d1: "", d2: "", region_id: "", district_id: "", facility_id: "" };
function periodOf() {
  const t = ME.today;
  if (F.preset === "day") return [F.d1 || t, F.d1 || t];
  if (F.preset === "week") return [addDays(t, -6), t];
  if (F.preset === "month") return [addDays(t, -29), t];
  return [F.d1 || t, F.d2 || F.d1 || t];
}
function scopeQ() { const [d1, d2] = periodOf(); return qs({ d1, d2, region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id }); }
async function filterBar(onChange, opt = {}) {
  const regs = META.regions, dist = F.region_id ? (await api("/api/districts?region_id=" + F.region_id)).items : [];
  const fac = F.district_id ? (await api("/api/facilities?" + qs({ district_id: F.district_id, size: 200 }))).items : [];
  const [d1, d2] = periodOf();
  const html = `<div class="filters card">
  ${opt.noPeriod ? "" : `<label>Период<div class="seg" id="f-pre">${[["day", "День"], ["week", "7 дней"], ["month", "30 дней"], ["custom", "Свой"]].map(([k, l]) => `<button data-v="${k}" class="${F.preset === k ? "on" : ""}">${l}</button>`).join("")}</div></label>
  <label>С<input type="date" id="f-d1" value="${d1}" ${F.preset === "week" || F.preset === "month" ? "disabled" : ""}></label>
  <label ${F.preset === "custom" ? "" : 'hidden'}>По<input type="date" id="f-d2" value="${d2}"></label>`}
  <label>Регион<select id="f-r">${opts(regs, F.region_id, "Все регионы")}</select></label>
  <label>Район<select id="f-d" ${F.region_id ? "" : "disabled"}>${opts(dist, F.district_id, "Все районы")}</select></label>
  <label>Учреждение<select id="f-f" ${F.district_id ? "" : "disabled"}>${opts(fac, F.facility_id, "Все учреждения")}</select></label>
  <button class="btn" id="f-reset">Сбросить</button></div>`;
  return { html, bind() {
    const ch = () => onChange();
    document.querySelectorAll("#f-pre button").forEach(b => b.onclick = () => { F.preset = b.dataset.v; if (F.preset !== "day" && F.preset !== "custom") F.d1 = F.d2 = ""; ch(); });
    const d1e = $("#f-d1"), d2e = $("#f-d2");
    if (d1e) d1e.onchange = () => { F.d1 = d1e.value; if (F.preset === "week" || F.preset === "month") F.preset = "day"; ch(); };
    if (d2e) d2e.onchange = () => { F.d2 = d2e.value; ch(); };
    $("#f-r").onchange = e => { F.region_id = e.target.value; F.district_id = F.facility_id = ""; ch(); };
    $("#f-d").onchange = e => { F.district_id = e.target.value; F.facility_id = ""; ch(); };
    $("#f-f").onchange = e => { F.facility_id = e.target.value; ch(); };
    $("#f-reset").onclick = () => { Object.assign(F, { preset: "day", d1: "", d2: "", region_id: "", district_id: "", facility_id: "" }); ch(); };
  } };
}

// ---------- dashboard
// only what no other card shows: the beds are in the gauge, admitted/discharged in the flow card, who has not reported follows from "сдали отчёт"
const KPI = [["reported", "Сдали отчёт", "✅", "ok"], ["visits", "Обращения", "🚶", "pri"], ["severe", "Тяжёлые", "🩺", "warn"], ["extreme", "Крайне тяжёлые", "🚨", "bad"],
  ["occ_pc", "Занято коек: беременные / дети", "🤰", "pur"], ["ext_pc", "Крайне тяжёлые: беременные / дети", "👶", "pur"]];
// the exact wording of the questions (Uzbek) behind a card: shown on hover
const KPI_CODES = { visits: ["visits"], severe: ["severe"], extreme: ["extreme"], occ_pc: ["occ_pregnant", "occ_children"], ext_pc: ["extreme_pregnant", "extreme_children"] };
const askedAs = key => (KPI_CODES[key] || []).map(code => { const i = (META.indicators || []).find(x => x.code === code); return i ? `${META.indicators.filter(x => x.active).findIndex(x => x.code === code) + 1}. ${i.name_uz || i.name_ru}` : ""; }).filter(Boolean).join(" · ");
const SORT = { key: "visits", asc: false }, DRILL = [];
const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const longDate = d => { const [y, m, dd] = d.split("-"); return `${+dd} ${MONTHS[+m - 1]} ${y}`; };
function kpiValue(key, k) {
  const t = k.totals;
  if (key === "reported") return `<span data-count="${k.reported}">${k.reported}</span><small class="muted"> из ${k.facilities}</small>`;
  if (key === "not_reported") return `<span data-count="${k.not_reported}">${k.not_reported}</span>`;
  if (key === "occ_pc") return `${num(t.occ_pregnant)} / ${num(t.occ_children)}`;
  if (key === "ext_pc") return `${num(t.extreme_pregnant)} / ${num(t.extreme_children)}`;
  if (key === "occupancy") return t.occupancy == null ? "—" : `<span data-count="${t.occupancy}" data-dec="1" data-suf="%">${t.occupancy}%</span>`;
  return t[key] == null ? "—" : `<span data-count="${t[key]}">${num(t[key])}</span>`;
}
async function dashboard(silent) {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  silent = silent === true;                                   // a refresh from the pulse: the same page, patched in place
  if (!silent) { const fb = await filterBar(dashboard); if (nav !== NAVID) return; view.innerHTML = fb.html + `<div id="dash"></div>`; fb.bind(); }
  const [d1, d2] = periodOf();
  let dash;
  try { dash = await api("/api/dashboard?" + (F.preset === "day" ? qs({ date: d1, region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id }) : scopeQ())); } catch (e) { return fail(e); }
  if (nav !== NAVID || !$("#dash")) return;                          // moved to another page while the data was coming
  const k = dash.kpis, th = ME.thresholds, t = k.totals;
  const occState = t.occupancy == null ? "" : t.occupancy >= th.critical ? "critical" : t.occupancy >= th.elevated ? "warning" : "";
  const isToday = F.preset === "day" && dash.requested === ME.today;
  const canWrite = ME.role !== "viewer";
  const owe = dash.control ? dash.control.not_sent + dash.control.overdue : 0;   // those who still owe today's report (also when nobody has reported yet)
  H($("#dash"), silent).innerHTML = `<div class="hero"><div><h1>${F.preset === "day" ? "Сводка за " + longDate(dash.used_date) : "Сводка за период " + d1 + " — " + d2}</h1><div class="sub">${ME.org ? esc(ME.org) + " · " : ""}по ${k.reported} из ${k.facilities} учреждений${dash.fallback ? " · данных за выбранный день нет, показан последний день с данными" : ""}</div></div>
    <div class="acts"><a class="btn" href="#/export">⬇ Выгрузка</a></div></div>
    ${canWrite && isToday && owe > 0 ? `<div class="cta"><span style="font-size:22px">⏰</span><div><b>${owe} учреждений ещё не сдали сводку за сегодня</b><div class="sub muted">Бот напомнит ответственным одним сообщением с кнопкой отправки</div></div><div class="acts"><button class="btn warn" id="remind">🔔 Отправить уведомление не сдавшим</button></div></div>` : ""}
    <div class="kpis">${KPI.map(([key, label, ic, tone], i) => `<div class="kpi tilt" data-t="${tone}" style="--i:${i}" title="${esc(askedAs(key))}"><div class="ic">${ic}</div><div class="v">${kpiValue(key, k)}</div><div class="l">${label}</div></div>`).join("")}</div>
    <div class="topgrid">${mapCard()}<div class="sidecol">
      <div class="card vcard"><h3>Загрузка коек</h3>${gaugeChart(t.occupancy, th)}<div class="cap">Занято <b>${num(t.beds_occupied)}</b> из <b>${num(t.beds_flu)}</b> выделенных · свободно <b>${num(t.beds_free)}</b><br>Всего коек в учреждениях: <b>${num(t.beds_total)}</b></div></div>
      <div class="card vcard"><h3>Поступили и выписаны</h3>${flowCard(t.hosp, t.disch)}</div></div></div>
    <div id="alerts" data-keep></div>
    <div class="grid2"><div class="card"><h2>Нагрузка по регионам</h2><div id="tiles" data-keep>…</div><div class="legend-dots"><span><i style="background:var(--ok)"></i>норма до ${th.elevated}%</span><span><i style="background:var(--warn)"></i>повышенная до ${th.critical}%</span><span><i style="background:var(--bad)"></i>критическая от ${th.critical}%</span></div></div>
      <div class="card"><div class="row"><h2>Лидеры по обращениям</h2></div><div id="rank" data-keep>…</div></div></div>
    <div class="card"><div class="row"><h2>Регионы</h2><input id="rt-q" placeholder="Поиск" class="right"></div><div class="scroll-x" id="rt" data-keep></div></div>
    <div class="grid2"><div class="card"><h3>Динамика</h3><div class="lbl">Показатель</div><div class="chips" id="dyn-m" data-keep></div><div class="lbl">Сравнить регионы <span class="muted">(до 5)</span></div><div class="chips" id="dyn-r" data-keep></div><div id="dyn" data-keep></div></div>
    <div class="card"><h3>Госпитализации и выписки</h3><div id="hd" data-keep></div></div></div>
    <div class="card"><h3>Баланс коек</h3><div class="scroll-x" id="beds" data-keep></div></div>`;
  if (!silent) countUp($("#dash"));
  tilt($("#dash"));
  const rem = $("#remind"); if (rem) rem.onclick = () => remindDlg(dash.requested);
  api("/api/alerts").then(a => $("#alerts") && ($("#alerts").innerHTML = a.items.slice(0, 6).map(x => `<div class="alert ${x.level}">${esc(x.text)}</div>`).join("") + (a.items.length > 6 ? `<p class="muted sm">Ещё предупреждений: ${a.items.length - 6} (раздел «Прогноз»)</p>` : ""))).catch(fail);
  const [u1, u2] = dash.fallback ? [dash.used_date, dash.used_date] : [d1, d2];   // tables follow the day the KPI cards show
  loadTable(u1, u2, silent); loadDyn(silent); loadHD(silent); loadBeds(u1, u2, silent); loadViz(u1, u2, silent);
}
async function loadViz(d1, d2, silent) {
  try {
    const r = await api("/api/regions-table?" + qs({ d1, d2, level: "region" })); const th = ME.thresholds;
    if (!$("#tiles")) return;
    H($("#tiles"), silent).innerHTML = heatTiles(r.rows.slice().sort((a, b) => (b.values.occupancy ?? -1) - (a.values.occupancy ?? -1)), th);
    H($("#rank"), silent).innerHTML = rankBars(r.rows, "visits");
    const pick = rid => { F.region_id = rid; F.district_id = F.facility_id = ""; dashboard(); };
    document.querySelectorAll("#tiles .tile, #rank .rk").forEach(el => el.onclick = () => pick(el.dataset.rid));
    bindMap(r.rows, th, pick, silent);
  } catch (e) { fail(e); }
}
// the button "remind those who have not reported": first shows who will get a message
async function remindDlg(date) {
  let pre; try { pre = await api("/api/notify/remind", { method: "POST", body: { date, region_id: F.region_id || null, dry: true } }); } catch (e) { return fail(e); }
  const people = pre.items.filter(x => x.status === "would_send"), skipped = pre.items.filter(x => x.status === "skipped");
  modal(`<h2>🔔 Напомнить не сдавшим</h2><p>За <b>${esc(longDate(date))}</b> не сдали сводку <b>${pre.missing}</b> учреждений.</p>
    ${people.length ? `<p>Сообщение в Telegram получат <b>${people.length}</b> ответственных:</p><div class="scroll-x" style="max-height:220px;overflow:auto"><table>${people.map(x => `<tr><td>${esc(x.name)}</td><td class="n">${x.facilities} уч.</td></tr>`).join("")}</table></div>` : `<div class="note">Некому отправлять: у всех не сдавших нет подключённого ответственного или им уже напоминали в последний час.</div>`}
    ${skipped.length ? `<p class="muted sm">Пропущены (напоминали меньше часа назад): ${skipped.length}</p>` : ""}
    ${pre.no_responsible_total ? `<div class="alert"><b>Нет ответственного у ${pre.no_responsible_total} учреждений</b> — им уведомление не уйдёт:<br><span class="sm">${pre.no_responsible.slice(0, 8).map(esc).join("<br>")}${pre.no_responsible_total > 8 ? "<br>…" : ""}</span></div>` : ""}
    <div class="row mt"><button class="btn warn" id="rm-go" ${people.length ? "" : "disabled"}>Отправить ${people.length || ""}</button><button class="btn right" data-close>Закрыть</button></div>`);
  const go = $("#rm-go"); if (go) go.onclick = async () => { go.disabled = true; try { const r = await api("/api/notify/remind", { method: "POST", body: { date, region_id: F.region_id || null, dry: false } });
    modal(`<h2>${r.errors ? "⚠️" : "✅"} Готово</h2><p>Отправлено: <b>${r.sent}</b>${r.errors ? `, не доставлено: <b>${r.errors}</b> (человек мог заблокировать бота)` : ""}${r.skipped ? `, пропущено: ${r.skipped}` : ""}.</p><button class="btn pri" data-close>Закрыть</button>`); } catch (e) { fail(e); go.disabled = false; } };
}
let METRICS = ["visits"], REGSEL = [];
function loadDyn(silent) {
  const mEl = $("#dyn-m"), rEl = $("#dyn-r"); if (!mEl || !rEl) return;
  const short = n => n.replace("Республика ", "").replace(" область", "").replace("город ", "г. ");
  const drawChips = () => {
    mEl.innerHTML = ["visits", "hosp", "disch", "beds_occupied", "occ_pregnant", "occ_children", "severe", "extreme"].map(m => `<button class="chip ${METRICS.includes(m) ? "on" : ""}" data-m="${m}">${NAMES[m]}</button>`).join("");
    rEl.innerHTML = `<button class="chip ${REGSEL.length ? "" : "on"}" data-r="">Вся территория</button>` + META.regions.map(r => `<button class="chip ${REGSEL.includes(String(r.id)) ? "on" : ""}" data-r="${r.id}">${esc(short(r.name_ru))}</button>`).join("");
    mEl.querySelectorAll("[data-m]").forEach(b => b.onclick = () => {
      const m = b.dataset.m;
      if (REGSEL.length >= 2) METRICS = [m];                       // regions are compared on one figure at a time
      else METRICS = METRICS.includes(m) ? METRICS.filter(x => x !== m) : [...METRICS, m];
      if (!METRICS.length) METRICS = ["visits"]; drawChips(); draw();
    });
    rEl.querySelectorAll("[data-r]").forEach(b => b.onclick = () => {
      const r = b.dataset.r;
      if (!r) REGSEL = [];
      else if (REGSEL.includes(r)) REGSEL = REGSEL.filter(x => x !== r);
      else if (REGSEL.length >= 5) return toast("Сравнивать можно до 5 регионов");
      else REGSEL = [...REGSEL, r];
      if (REGSEL.length >= 2 && METRICS.length > 1) METRICS = [METRICS[0]];
      drawChips(); draw();
    });
  };
  const draw = async sl => {
    const [d1, d2] = periodOf(); const a = d2 === d1 ? addDays(d1, -13) : d1;
    try {
      const r = await api("/api/dynamics?" + qs({ d1: a, d2, metrics: METRICS.join(","), regions: REGSEL.join(","), region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id }));
      if (!$("#dyn")) return;
      H($("#dyn"), sl).innerHTML = (REGSEL.length >= 2 ? `<p class="muted sm">Сравнение по показателю «${NAMES[METRICS[0]]}»</p>` : "") +
        lineChart(r.dates, r.series.map(s => ({ name: REGSEL.length >= 2 ? s.name : REGSEL.length === 1 && METRICS.length > 1 ? s.name + " — " + NAMES[s.metric] : METRICS.length > 1 ? NAMES[s.metric] : s.name, points: s.points })));
    } catch (e) { fail(e); }
  };
  if (!(silent && mEl.firstChild)) drawChips();               // the choice of figures and regions is the person's, a refresh keeps it
  draw(silent);
}
async function loadHD(silent) {
  const [d1, d2] = periodOf(); const a = d2 === d1 ? addDays(d1, -13) : d1;
  try {
    const r = await api("/api/hosp-disch?" + qs({ d1: a, d2, region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id }));
    if (!$("#hd")) return;
    H($("#hd"), silent).innerHTML = barChart(r.rows.map(x => x.date), [{ name: "Госпитализации", values: r.rows.map(x => x.hosp) }, { name: "Выписки", values: r.rows.map(x => x.disch) }]) +
      `<div class="scroll-x" style="max-height:200px;overflow:auto"><table><tr><th>Дата</th><th class="n">Госп.</th><th class="n">Выписки</th><th class="n">Разница</th><th class="n">Занято</th><th class="n">Изм.</th></tr>${r.rows.slice().reverse().map(x => `<tr><td>${x.date}</td><td class="n">${num(x.hosp)}</td><td class="n">${num(x.disch)}</td><td class="n">${num(x.diff)}</td><td class="n">${num(x.occupied)}</td><td class="n">${x.occ_change == null ? "—" : (x.occ_change > 0 ? "+" : "") + x.occ_change}</td></tr>`).join("")}</table></div>`;
  } catch (e) { fail(e); }
}
async function loadTable(d1, d2, silent) {
  const level = DRILL.length === 0 ? "region" : "rfac";             // a region opens straight into its facilities
  const pid = DRILL.length ? DRILL[DRILL.length - 1].id : "";
  let r; try { r = await api("/api/regions-table?" + qs({ d1, d2, level, parent_id: pid })); } catch (e) { return fail(e); }
  if (!$("#rt-q")) return;   // the person has already left the dashboard
  const cols = [["name", "Название"], ["reported", "Отчётов"], ["visits", "Обращения"], ["hosp", "Госп."], ["disch", "Выписки"], ["beds_total", "Коек всего"], ["beds_flu", "Для гриппа и ОРВИ"], ["beds_occupied", "Занято"], ["occ_pregnant", "Берем."], ["occ_children", "Дети"], ["beds_free", "Своб."], ["occupancy", "Загрузка"], ["severe", "Тяжёлые"], ["extreme", "Крайне тяж."], ["extreme_pregnant", "Кр.тяж. берем."], ["extreme_children", "Кр.тяж. дети"]];
  const draw = sl => {
    const q = ($("#rt-q").value || "").toLowerCase();
    const val = (x, k) => k === "name" ? x.name : k === "reported" ? x.reported : x.values[k];
    const rows = r.rows.filter(x => x.name.toLowerCase().includes(q)).sort((a, b) => { const A = val(a, SORT.key), B = val(b, SORT.key); const c = typeof A === "string" ? A.localeCompare(B, "ru") : (A ?? -1) - (B ?? -1); return SORT.asc ? c : -c; });
    const manyDistricts = new Set(r.rows.map(x => x.district)).size > 1;
    const crumbs = `<p class="sm"><a href="#" id="up0">Республика</a>${DRILL.map((d, i) => ` › <a href="#" data-up="${i}">${esc(d.name)}</a>`).join("")}</p>`;
    H($("#rt"), sl).innerHTML = crumbs + `<table><tr>${cols.map(([k, l]) => `<th data-s="${k}" class="${k !== "name" ? "n " : ""}${SORT.key === k ? "on" + (SORT.asc ? " asc" : "") : ""}">${l}</th>`).join("")}</tr>${rows.map(x => `<tr class="${level === "region" ? "link" : ""}" data-id="${x.id}" data-name="${esc(x.name)}"><td>${esc(x.name)}${level === "rfac" && manyDistricts ? `<div class="muted sm">${esc(x.district || "")}</div>` : ""}</td><td class="n">${x.reported}/${x.facilities}</td>${cols.slice(2).map(([k]) => k === "occupancy" ? `<td class="n">${x.values.occupancy == null ? "—" : `<span class="pill ${x.level_state === "none" ? "" : x.level_state}">${num(x.values.occupancy)}%</span>`}</td>` : `<td class="n">${num(x.values[k])}</td>`).join("")}</tr>`).join("")}</table>`;
    document.querySelectorAll("#rt th[data-s]").forEach(th => th.onclick = () => { SORT.asc = SORT.key === th.dataset.s ? !SORT.asc : false; SORT.key = th.dataset.s; draw(); });
    document.querySelectorAll("#rt tr.link").forEach(tr => tr.onclick = () => { DRILL.push({ id: tr.dataset.id, name: tr.dataset.name }); loadTable(d1, d2); });
    $("#up0").onclick = e => { e.preventDefault(); DRILL.length = 0; loadTable(d1, d2); };
    document.querySelectorAll("[data-up]").forEach(a => a.onclick = e => { e.preventDefault(); DRILL.length = +a.dataset.up + 1; loadTable(d1, d2); });
  };
  $("#rt-q").oninput = () => draw(); draw(silent);
}
async function loadBeds(d1, d2, silent) {
  try {
    const r = await api("/api/beds?" + qs({ d1, d2 })); const th = r.thresholds;
    if (!$("#beds")) return;
    H($("#beds"), silent).innerHTML = `<p class="muted sm">Пороги: повышенная нагрузка ≥ ${th.elevated}%, критическая ≥ ${th.critical}%, учреждение ≥ ${th.facility}%.</p><table><tr><th>Регион</th><th class="n">Коек для гриппа и ОРВИ</th><th class="n">Занято</th><th class="n">Свободно</th><th class="n">Загрузка</th><th>Состояние</th></tr>${r.rows.map(x => `<tr><td>${esc(x.name)}</td><td class="n">${num(x.beds_flu)}</td><td class="n">${num(x.occupied)}</td><td class="n">${num(x.free)}</td><td class="n">${x.occupancy == null ? "—" : num(x.occupancy) + "%"}</td><td>${pill(x.state)}</td></tr>`).join("")}</table>` +
      (r.hot.length ? `<h3 class="mt">Учреждения с высокой загрузкой</h3><table><tr><th>Учреждение</th><th>Регион</th><th class="n">Загрузка</th><th class="n">Свободно</th></tr>${r.hot.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.region)}${x.district === "Без района" ? "" : ", " + esc(x.district)}</td><td class="n"><span class="pill critical">${num(x.occupancy)}%</span></td><td class="n">${num(x.free)}</td></tr>`).join("")}</table>` : "");
  } catch (e) { fail(e); }
}

// ---------- forecast
async function forecastView() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const fb = await filterBar(forecastView, { noPeriod: true });
  if (nav !== NAVID) return; view.innerHTML = fb.html + `<div id="fc" class="card">${T("Загрузка…")}</div><div id="al" class="card"></div>`; fb.bind();
  try {
    const [fc, al] = await Promise.all([api("/api/forecast?" + qs({ region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id })), api("/api/alerts")]);
    const rel = { low: "critical", medium: "warning", high: "normal" };
    let h = `<h2>${T("Прогноз на 3 и 7 дней")}</h2><p class="note">${T("Это инструмент оперативного планирования, а не эпидемиологический вывод. Метод: {method}. Серая зона — 90% интервал.", { method: esc(TS(Object.values(fc.metrics)[0]?.method || "")) })}</p>`;
    for (const [code, m] of Object.entries(fc.metrics)) {
      h += `<h3>${T(NAMES[code])}</h3>`;
      if (!m.ok) { h += `<p class="muted">${esc(TS(m.reliability_text))}</p>`; continue; }
      h += `<p>${T("Последнее значение {cur} ({date}). Через 3 дня: <b>{v3}</b> ({l3}–{h3}); через 7 дней: <b>{v7}</b> ({l7}–{h7}). Надёжность: {rel}", { cur: num(m.current), date: m.current_date, v3: num(m.days[2].value), l3: num(m.days[2].low), h3: num(m.days[2].high), v7: num(m.days[6].value), l7: num(m.days[6].low), h7: num(m.days[6].high), rel: `<span class="pill ${rel[m.reliability]}">${esc(TS(m.reliability_text))}</span>` })}</p>`;
    }
    if (fc.beds) {
      const b = fc.beds;
      h += `<h3>${T("Прогноз загрузки коек")}</h3><p>${T("Сейчас занято {occ} из {flu} ({date}). Надёжность: {rel}", { occ: num(b.occupied), flu: num(b.beds_flu), date: b.current_date, rel: `<span class="pill ${rel[b.reliability]}">${esc(TS(b.reliability_text))}</span>` })}</p><p class="muted sm">${esc(TS(b.method))}</p>` +
        lineChart(b.days.map(d => d.date), [{ name: T("Занято коек"), points: b.days.map(d => d.occupied), dashed: true }, { name: T("Коек для гриппа и ОРВИ"), points: b.days.map(() => b.beds_flu), color: "#d64545" }]) +
        `<table><tr><th>${T("Дата")}</th><th class="n">${T("Занято")}</th><th class="n">${T("Свободно")}</th><th class="n">${T("Загрузка")}</th><th class="n">${T("Дефицит")}</th></tr>${b.days.map(d => `<tr><td>${d.date}</td><td class="n">${num(d.occupied)}</td><td class="n">${num(d.free)}</td><td class="n">${num(d.occupancy)}%</td><td class="n">${d.deficit ? `<span class="pill critical">${num(d.deficit)}</span>` : "—"}</td></tr>`).join("")}</table>`;
    } else h += `<p class="muted">${T("Прогноз коек недоступен: нужны данные о госпитализациях, выписках и коечном фонде.")}</p>`;
    $("#fc").innerHTML = h;
    $("#al").innerHTML = `<h2>${T("Предупреждения")}</h2>` + (al.items.length ? al.items.map(x => `<div class="alert ${x.level}">${esc(TS(x.text))}</div>`).join("") : `<p class="muted">${T("Предупреждений нет.")}</p>`);
  } catch (e) { fail(e); }
}

// ---------- control table
async function control() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const fb = await filterBar(control, { noPeriod: true });
  if (nav !== NAVID) return; view.innerHTML = fb.html + `<div class="row"><label>${T("Дата")} <input type="date" id="c-d" value="${F.d1 || ME.today}"></label><div class="seg" id="c-f"></div><button class="btn warn right" id="c-rem">${T("🔔 Напомнить не сдавшим")}</button></div><div id="ct" class="card">${T("Загрузка…")}</div>`; fb.bind();
  $("#c-rem").onclick = () => remindDlg(F.d1 || ME.today);
  $("#c-d").onchange = e => { F.d1 = e.target.value; control(); };
  try {
    const r = await api("/api/control?" + qs({ date: F.d1 || ME.today, region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id })); const c = r.counts;
    let filt = control.filter || "";
    const draw = () => {
      const rows = r.rows.filter(x => !filt || (filt === "noresp" ? !x.has_responsible : x.state === filt));
      $("#ct").innerHTML = `<p>${T("Срок сдачи: <b>{deadline}</b>. Всего {total}; сдали {sent} (из них исправлено {corrected}); возвращено {returned}; не сдали {notsent}; без ответственного: {noresp}.", { deadline: r.deadline, total: c.total, sent: c.sent, corrected: c.corrected, returned: c.returned, notsent: c.not_sent + c.overdue, noresp: c.no_responsible })}</p>
      <div class="scroll-x"><table><tr><th>${T("Регион")}</th><th>${T("Район")}</th><th>${T("Учреждение")}</th><th>${T("Ответственный")}</th><th>${T("Статус")}</th><th>${T("Время")}</th></tr>${rows.map(x => `<tr ${x.report_id ? `class="link" data-rep="${x.report_id}"` : ""}><td>${esc(rname(x.region))}</td><td>${esc(x.district)}</td><td>${esc(x.facility)}</td><td>${x.has_responsible ? esc(x.responsible) : `<span class="muted">${T("не назначен")}</span>`}</td><td>${pill(x.state)}${x.late ? ` <span class="pill warning">${T("поздно")}</span>` : ""}</td><td>${x.time}</td></tr>`).join("")}</table></div>`;
      document.querySelectorAll("#ct tr[data-rep]").forEach(tr => tr.onclick = () => openReport(+tr.dataset.rep));
    };
    $("#c-f").innerHTML = [["", "Все"], ["sent", "Сдали"], ["corrected", "Исправлены"], ["returned", "Возвращены"], ["not_sent", "Не сдали"], ["overdue", "Просрочены"], ["noresp", "Без ответственного"]].map(([k, l]) => `<button data-v="${k}" class="${filt === k ? "on" : ""}">${T(l)}</button>`).join("");
    document.querySelectorAll("#c-f button").forEach(b => b.onclick = () => { control.filter = b.dataset.v; filt = b.dataset.v; document.querySelectorAll("#c-f button").forEach(x => x.classList.toggle("on", x === b)); draw(); });
    draw();
  } catch (e) { fail(e); }
}

// ---------- reports
async function reportsView() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  if (F.preset === "day" && !F.d1) F.preset = "week";   // a single empty day is a useless first view of the list
  const fb = await filterBar(reportsView);
  if (nav !== NAVID) return; view.innerHTML = fb.html + `<div class="card"><div class="row"><h2>${T("Отчёты")}</h2><select id="r-st"><option value="">${T("Все")}</option><option value="sent">${T("Отправленные")}</option><option value="returned">${T("Возвращённые")}</option><option value="corrected">${T("Исправленные")}</option><option value="late">${T("С опозданием")}</option></select><input id="r-q" placeholder="${T("Поиск по учреждению")}">${ME.role === "super_admin" ? `<button class="btn bad right" id="r-del" hidden>${T("🗑 Удалить выбранные")}</button>` : ""}<button class="btn pri ${ME.role === "super_admin" ? "" : "right"}" id="r-new">${T("+ Внести отчёт")}</button></div><div id="rl" class="scroll-x"></div></div>`; fb.bind();
  $("#r-new").onclick = () => editReport(null);
  if (!ME.can_edit_reports) $("#r-new").hidden = true;
  const SU = ME.role === "super_admin";
  const load = async () => {
    try {
      const r = await api("/api/reports?" + scopeQ() + "&" + qs({ status: $("#r-st").value, q: $("#r-q").value, size: 200 }));
      $("#rl").innerHTML = `<p class="muted sm">${T("Найдено: {n}", { n: r.total })}</p><table><tr>${SU ? `<th><input type="checkbox" id="r-all" title="${T("Выбрать все")}"></th>` : ""}<th>${T("Дата")}</th><th>${T("Регион")}</th><th>${T("Район")}</th><th>${T("Учреждение")}</th><th>${T("Статус")}</th><th>${T("Версия")}</th><th>${T("Кто")}</th></tr>${r.items.map(x => `<tr class="link" data-id="${x.id}">${SU ? `<td><input type="checkbox" class="r-one" data-rid="${x.id}"></td>` : ""}<td>${x.report_date}</td><td>${esc(rname(x.region))}</td><td>${esc(x.district)}</td><td>${esc(x.facility)}</td><td>${pill(x.status === "returned" ? "returned" : x.corrected ? "corrected" : "sent")}${x.late ? ` <span class="pill warning">${T("поздно")}</span>` : ""}${x.locked ? " 🔒" : ""}</td><td>${x.version}</td><td>${esc(x.submitted_by)}</td></tr>`).join("")}</table>`;
      document.querySelectorAll("#rl tr[data-id]").forEach(tr => tr.onclick = ev => { if (ev.target.type === "checkbox") return; openReport(+tr.dataset.id); });
      const chosen = () => [...document.querySelectorAll(".r-one:checked")].map(x => +x.dataset.rid);
      const sync = () => { const b = $("#r-del"); if (b) { const n = chosen().length; b.hidden = !n; b.textContent = T("🗑 Удалить выбранные ({n})", { n }); } };
      document.querySelectorAll(".r-one").forEach(x => x.onchange = sync);
      const all = $("#r-all"); if (all) all.onchange = () => { document.querySelectorAll(".r-one").forEach(x => x.checked = all.checked); sync(); };
      const del = $("#r-del"); if (del) del.onclick = () => deleteReportsDlg(chosen(), load);
      sync();
    } catch (e) { fail(e); }
  };
  $("#r-st").onchange = load; $("#r-q").oninput = () => { clearTimeout(DEB); DEB = setTimeout(load, 300); }; load();
}
function deleteReportsDlg(ids, done) {
  confirmDlg(T("🗑 Удалить отчёты"), `<p>${T("Будет удалено отчётов: <b>{n}</b> вместе с историей версий. Это нельзя отменить. В журнале действий останется запись о каждом удалённом отчёте (учреждение, дата, цифры, причина).", { n: ids.length })}</p><p class="muted sm">${T("Учреждение снова будет считаться не сдавшим за эту дату, отчёт можно внести заново.")}</p>`, T("Удалить безвозвратно"), async reason => {
    const r = await api("/api/reports/delete", { method: "POST", body: { ids, reason } }); closeModal(); toast(T("Удалено отчётов: {n}", { n: r.deleted })); done();
  }, true);
}
async function openReport(id) {
  let r; try { r = await api("/api/reports/" + id); } catch (e) { return fail(e); }
  const ind = META.indicators.filter(i => i.active);
  modal(`<h2>${esc(r.facility)}</h2><p class="muted">${esc(rname(r.region))}, ${esc(r.district)} · ${T("за {date}", { date: r.report_date })} · ${T("версия {n}", { n: r.version })} · ${pill(r.status === "returned" ? "returned" : r.corrected ? "corrected" : "sent")}${r.late ? " " + T("поздно") : ""}${r.locked_now ? " 🔒 " + T("закрыт") : ""}</p>
  ${r.return_reason ? `<div class="note">${T("Возвращён: {reason}", { reason: esc(r.return_reason) })}</div>` : ""}
  <table>${ind.map(i => `<tr><td>${esc(nm(i))}</td><td class="n"><b>${num(r.values[i.code])}</b></td></tr>`).join("")}</table>
  <div class="row mt">${ME.can_edit_reports ? `<button class="btn pri" id="m-ed">${T("Исправить")}</button><button class="btn" id="m-ret">${T("Вернуть на исправление")}</button>` : ""}<button class="btn" id="m-lock">${r.locked ? T("Открыть для правок") : T("Закрыть для правок")}</button>${ME.role === "super_admin" ? `<button class="btn bad" id="m-del">${T("🗑 Удалить отчёт")}</button>` : ""}<button class="btn right" data-close>${T("Закрыть окно")}</button></div>
  <h3 class="mt">${T("История версий")}</h3><div class="scroll-x"><table><tr><th>${T("Версия")}</th><th>${T("Когда")}</th><th>${T("Кто")}</th><th>${T("Действие")}</th><th>${T("Причина")}</th><th>${T("Что изменено")}</th><th></th></tr>${r.versions.map(v => `<tr><td>${v.version}</td><td>${esc(v.at || v.created_at || "")}</td><td>${esc(v.by_name || v.by || "")}</td><td>${esc(v.action)}</td><td>${esc(v.reason || "")}</td><td class="sm">${Object.entries(v.changes || {}).map(([k, c]) => `${esc(k)}: ${c[0] ?? "—"} → ${c[1] ?? "—"}`).join("<br>")}</td><td>${ME.can_edit_reports && v.version !== r.version ? `<button class="btn sm" data-restore="${v.version}">${T("Вернуть")}</button>` : ""}</td></tr>`).join("")}</table></div>`, true);
  const ed = $("#m-ed"); if (ed) ed.onclick = () => editReport(r);
  const dl = $("#m-del"); if (dl) dl.onclick = () => deleteReportsDlg([id], route);
  const rt = $("#m-ret"); if (rt) rt.onclick = async () => { const reason = prompt(T("Причина возврата:")); if (!reason) return; try { await api(`/api/reports/${id}/return`, { method: "POST", body: { reason } }); toast(T("Отчёт возвращён")); closeModal(); route(); } catch (e) { fail(e); } };
  $("#m-lock").onclick = async () => { try { await api(`/api/reports/${id}/lock`, { method: "POST", body: { locked: !r.locked } }); toast(T("Готово")); openReport(id); } catch (e) { fail(e); } };
  document.querySelectorAll("[data-restore]").forEach(b => b.onclick = async () => { const reason = prompt(T("Причина восстановления версии {n}:", { n: b.dataset.restore })); if (!reason) return; try { await api(`/api/reports/${id}/restore`, { method: "POST", body: { version: +b.dataset.restore, reason } }); toast(T("Версия восстановлена (создана новая)")); openReport(id); } catch (e) { fail(e); } });
}
async function editReport(r) {
  const ind = META.indicators.filter(i => i.active);
  let facs = [];
  if (!r) { try { facs = (await api("/api/facilities?" + qs({ region_id: F.region_id, district_id: F.district_id, size: 200 }))).items; } catch (e) { return fail(e); } }
  modal(`<h2>${r ? T("Исправление отчёта") : T("Внести отчёт")}</h2>
  ${r ? "" : `<label>${T("Учреждение")}<select id="e-f">${facs.map(f => `<option value="${f.id}">${esc(rname(f.region))} — ${esc(f.district)} — ${esc(nm(f))}</option>`).join("")}</select></label><label>${T("Дата")}<input type="date" id="e-d" value="${ME.today}"></label>`}
  <div class="fields">${ind.map(i => `<label>${esc(nm(i))}<input type="number" min="0" step="1" data-code="${i.code}" value="${r ? (r.values[i.code] ?? "") : ""}"></label>`).join("")}</div>
  <label>${T("Причина изменения (обязательно для журнала)")}<textarea id="e-reason" rows="2"></textarea></label><div id="e-msg"></div>
  <div class="row mt"><button class="btn pri" id="e-save">${T("Сохранить")}</button><button class="btn" id="e-chk">${T("Проверить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`, true);
  const vals = () => Object.fromEntries([...document.querySelectorAll("[data-code]")].filter(i => i.value !== "").map(i => [i.dataset.code, +i.value]));
  const ctx = () => ({ facility_id: r ? r.facility_id : +$("#e-f").value, date: r ? r.report_date : $("#e-d").value });
  const show = v => $("#e-msg").innerHTML = v.errors.map(x => `<div class="alert critical">${esc(TS(x))}</div>`).join("") + v.warnings.map(x => `<div class="alert">${esc(TS(x))}</div>`).join("");
  $("#e-chk").onclick = async () => { try { show(await api("/api/validate", { method: "POST", body: { values: vals(), ...ctx() } })); } catch (e) { fail(e); } };
  $("#e-save").onclick = async () => {
    try { await api("/api/reports", { method: "PUT", body: { values: vals(), reason: $("#e-reason").value, ...ctx() } }); toast(T("Сохранено")); closeModal(); route(); }
    catch (e) { if (e.details) show({ errors: e.details.errors || [], warnings: e.details.warnings || [] }); fail(e); }
  };
}

// ---------- people (Telegram users, requests, staff)
// a person of Telegram: the avatar (fetched by the server; initials until it loads or when there is none), the name, @username, and a button to the profile
const tgName = u => [u.first_name, u.last_name].filter(Boolean).join(" ") || (u.username ? "@" + u.username : "Без имени");
const tgAv = u => `<span class="tgav">${esc((tgName(u).replace(/^@/, "")[0] || "?").toUpperCase())}<img src="/api/tg-avatar/${esc(u.tg_id)}" alt="" loading="lazy"></span>`;
const tgWho = u => `<div class="tgwho">${tgAv(u)}<div><b>${esc(tgName(u))}</b>${u.active === 0 ? ' <span class="pill critical">отключён</span>' : ""}<div class="muted sm">${u.username ? "@" + esc(u.username) + " · " : ""}ID ${esc(u.tg_id)}</div></div></div>`;
const tgLink = u => u.username ? `<a class="btn sm" href="https://t.me/${esc(u.username)}" target="_blank" rel="noopener noreferrer">✈ Профиль в Telegram</a>`
  : `<a class="btn sm" href="tg://user?id=${esc(u.tg_id)}" title="У человека нет @username: профиль откроется, только если он уже есть в ваших чатах Telegram">✈ Профиль в Telegram</a>`;
const dropBrokenAvatars = root => root.querySelectorAll(".tgav img").forEach(im => { const rm = () => im.remove(); im.addEventListener("error", rm, { once: true }); if (im.complete && im.naturalWidth === 0) rm(); });
const OPENRG = new Set();           // regions whose group of people is open (kept while the page is reloaded after an action)
async function people() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><div class="row"><h2>Заявки на доступ</h2></div><div id="rq" class="scroll-x"></div></div><div class="card"><div class="row"><h2>Записаны заранее</h2><span class="muted sm">доступ откроется сам, когда человек впервые напишет боту</span></div><div id="pre" class="scroll-x"></div></div><div class="card"><div class="row"><h2>Ответственные (Telegram)</h2><button class="btn pri right" id="tg-add">+ Добавить</button></div><div id="tgl" class="scroll-x"></div></div><div id="staffbox"></div>`;
  const loadReq = async () => { try { const r = await api("/api/requests?status=pending");
    $("#rq").innerHTML = r.items.length ? `<table><tr><th>Дата</th><th>Кто просит</th><th>Куда</th><th></th></tr>${r.items.map(x => `<tr><td>${esc(x.created_at)}</td><td>${tgWho(x)}<div class="mt">${tgLink(x)}</div></td><td><b>${esc(x.region)}</b>${x.district ? " — " + esc(x.district) : ""}${x.facility ? " — " + esc(x.facility) : ' <span class="pill">весь регион</span>'}</td><td class="row"><button class="btn sm pri" data-ap="${x.id}">Одобрить</button><button class="btn sm bad" data-no="${x.id}">Отклонить</button></td></tr>`).join("")}</table>` : `<p class="muted">Новых заявок нет.</p>`;
    dropBrokenAvatars($("#rq"));
    document.querySelectorAll("[data-ap]").forEach(b => b.onclick = () => decide(+b.dataset.ap, true)); document.querySelectorAll("[data-no]").forEach(b => b.onclick = () => decide(+b.dataset.no, false)); } catch (e) { fail(e); } };
  const decide = async (id, approve) => { const note = approve ? "" : prompt("Причина отказа (увидит заявитель):") ?? null; if (note === null) return; try { await api(`/api/requests/${id}/decide`, { method: "POST", body: { approve, note } }); loadReq(); loadTg(); } catch (e) { fail(e); } };
  const loadPre = async () => { try { const r = await api("/api/preapproved");
    $("#pre").innerHTML = r.items.length ? `<table><tr><th>Telegram</th><th>Куда</th><th>Тип</th><th>Записан</th><th></th></tr>${r.items.map(x => `<tr><td><b>@${esc(x.username)}</b> <a class="btn sm" href="https://t.me/${esc(x.username)}" target="_blank" rel="noopener noreferrer">✈ Профиль</a></td><td><b>${esc(x.region)}</b>${x.facility ? " — " + esc(x.facility) : ' <span class="pill">весь регион</span>'}${x.fio ? `<div class="muted sm">${esc(x.fio)}</div>` : ""}</td><td>${x.kind === "reserve" ? "резерв" : "основной"}</td><td>${esc(x.created_at)}</td><td><button class="btn sm bad" data-pd="${x.id}">Убрать</button></td></tr>`).join("")}</table>${r.bot ? `<p class="muted sm">Попросите этих людей открыть бота: <a href="https://t.me/${esc(r.bot)}" target="_blank" rel="noopener noreferrer">t.me/${esc(r.bot)}</a> и нажать «Start».</p>` : ""}` : `<p class="muted">Никого. Нажмите «+ Добавить» и укажите @username.</p>`;
    document.querySelectorAll("[data-pd]").forEach(b => b.onclick = async () => { if (!confirm("Убрать запись? Человек не получит доступ автоматически.")) return; try { await api("/api/preapproved/" + b.dataset.pd, { method: "DELETE" }); loadPre(); } catch (x) { fail(x); } }); } catch (e) { fail(e); } };
  const loadTg = async () => { try { const r = await api("/api/tg-users");
    // grouped by region: a person is listed in every region where they have access (the whole region or single facilities); people with no access are last
    const groups = new Map(META.regions.map(rg => [rg.id, { name: rg.name_ru, people: new Map() }])), none = [];
    const put = (rid, u) => { const g = groups.get(rid); if (!g) return null; if (!g.people.has(u.tg_id)) g.people.set(u.tg_id, { u, regs: [], facs: [] }); return g.people.get(u.tg_id); };
    r.items.forEach(u => { u.regions.forEach(a => { const e = put(a.region_id, u); if (e) e.regs.push(a); }); u.assignments.forEach(a => { const e = put(a.region_id, u); if (e) e.facs.push(a); }); if (!u.regions.length && !u.assignments.length) none.push(u); });
    const active = [...groups.entries()].filter(([, g]) => g.people.size);
    const acts = u => `${tgLink(u)}<button class="btn sm" data-as="${u.tg_id}">Назначить</button><button class="btn sm" data-tog="${u.tg_id}" data-a="${u.active}">${u.active ? "Отключить" : "Включить"}</button>`;
    const access = e => e.regs.map(a => `<b>весь регион</b>${a.kind === "reserve" ? " (резерв)" : ""} <a href="#" data-unr="${a.id}">✕</a>`).concat(e.facs.map(a => `${esc(a.facility)} (${a.kind === "reserve" ? "резерв" : "основной"}) <a href="#" data-un="${a.id}">✕</a>`)).join("<br>");
    const people_n = new Set(active.flatMap(([, g]) => [...g.people.keys()])).size;
    $("#tgl").innerHTML = `<div class="rgsum"><b>${people_n}</b> чел. с доступом в <b>${active.length}</b> регионах · без доступа: <b>${none.length}</b></div>
      <div class="chips rgchips">${[...groups.entries()].map(([id, g]) => `<button class="chip${g.people.size ? "" : " dim"}" data-go="${id}" ${g.people.size ? "" : "disabled"}>${esc(g.name.replace("Республика ", "").replace(" область", "").replace("город ", "г. "))} <b>${g.people.size}</b></button>`).join("")}${none.length ? `<button class="chip dim" data-go="none">Без доступа <b>${none.length}</b></button>` : ""}</div>
      <div class="inl" style="margin:8px 0"><input id="tg-q" placeholder="Найти человека" style="max-width:260px"><button class="btn sm" id="rg-open">Развернуть все</button><button class="btn sm" id="rg-close">Свернуть все</button></div>
      ${active.map(([id, g]) => `<details class="rgrp" data-rg="${id}" ${OPENRG.has(String(id)) ? "open" : ""}><summary><b>${esc(g.name)}</b><span class="pill">${g.people.size} чел.</span></summary>
        <div class="scroll-x"><table><tr><th>Пользователь</th><th>Доступ в этом регионе</th><th></th></tr>${[...g.people.values()].map(e => `<tr data-find="${esc((tgName(e.u) + " " + (e.u.username || "") + " " + e.u.tg_id).toLowerCase())}"><td>${tgWho(e.u)}</td><td>${access(e)}</td><td class="row">${acts(e.u)}</td></tr>`).join("")}</table></div></details>`).join("")}
      ${none.length ? `<details class="rgrp" data-rg="none" ${OPENRG.has("none") ? "open" : ""}><summary><b>Без доступа</b><span class="pill">${none.length} чел.</span></summary><div class="scroll-x"><table><tr><th>Пользователь</th><th></th></tr>${none.map(u => `<tr data-find="${esc((tgName(u) + " " + (u.username || "") + " " + u.tg_id).toLowerCase())}"><td>${tgWho(u)}</td><td class="row">${acts(u)}</td></tr>`).join("")}</table></div></details>` : ""}
      ${active.length || none.length ? "" : '<p class="muted">Пока никого.</p>'}`;
    document.querySelectorAll("#tgl details.rgrp").forEach(d => d.addEventListener("toggle", () => { d.open ? OPENRG.add(d.dataset.rg) : OPENRG.delete(d.dataset.rg); }));
    document.querySelectorAll("#tgl [data-go]").forEach(b => b.onclick = () => { const d = document.querySelector(`#tgl details[data-rg="${b.dataset.go}"]`); if (d) { d.open = true; d.scrollIntoView({ behavior: "smooth", block: "start" }); } });
    $("#rg-open").onclick = () => document.querySelectorAll("#tgl details.rgrp").forEach(d => d.open = true); $("#rg-close").onclick = () => document.querySelectorAll("#tgl details.rgrp").forEach(d => d.open = false);
    $("#tg-q").oninput = e => { const q = e.target.value.trim().toLowerCase(); document.querySelectorAll("#tgl tr[data-find]").forEach(tr => tr.hidden = !!q && !tr.dataset.find.includes(q)); if (q) document.querySelectorAll("#tgl details.rgrp").forEach(d => { d.open = [...d.querySelectorAll("tr[data-find]")].some(tr => !tr.hidden); }); };
    dropBrokenAvatars($("#tgl"));
    document.querySelectorAll("[data-un]").forEach(a => a.onclick = async e => { e.preventDefault(); if (!confirm("Снять назначение?")) return; try { await api("/api/assignments/" + a.dataset.un, { method: "DELETE" }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-unr]").forEach(a => a.onclick = async e => { e.preventDefault(); if (!confirm("Снять доступ к региону?")) return; try { await api("/api/region-access/" + a.dataset.unr, { method: "DELETE" }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-tog]").forEach(b => b.onclick = async () => { try { await api("/api/tg-users/" + b.dataset.tog, { method: "PATCH", body: { active: b.dataset.a !== "1" } }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-as]").forEach(b => b.onclick = () => assignDlg(b.dataset.as, () => { loadTg(); loadPre(); })); } catch (e) { fail(e); } };
  $("#tg-add").onclick = () => assignDlg("", () => { loadTg(); loadPre(); });
  loadReq(); loadPre(); loadTg();
  if (ME.role === "super_admin") staffBox();
}

async function assignDlg(tg, done) {
  modal(`<h2>${tg ? "Назначить ответственного" : "Добавить ответственного"}</h2>${tg ? "" : `<label>@username или Telegram ID<input id="a-id" placeholder="@username  или  123456789" autocomplete="off"></label><p class="muted sm" style="margin:-4px 0 10px">С @username человеку не нужно отправлять запрос: доступ откроется, как только он впервые напишет боту. Числовой ID нужен, если у человека нет @username.</p><label>Имя (необязательно)<input id="a-n"></label>`}
  <label>Регион<select id="a-r">${opts(META.regions, "", "—")}</select></label><label>Район (необязательно)<select id="a-d" disabled></select></label><label>Учреждение (необязательно; если пусто — доступ ко всему региону)<select id="a-f" disabled></select></label>
  <label>Тип<select id="a-k"><option value="primary">Основной</option><option value="reserve">Резервный</option></select></label><label>ФИО (для отчётов)<input id="a-fio"></label>
  <div class="row mt"><button class="btn pri" id="a-ok">Сохранить</button><button class="btn right" data-close>Отмена</button></div>`);
  $("#a-r").onchange = async e => { const d = await api("/api/districts?region_id=" + e.target.value); $("#a-d").innerHTML = opts(d.items, "", "—"); $("#a-d").disabled = false; $("#a-f").disabled = true; };
  $("#a-d").onchange = async e => { const f = await api("/api/facilities?" + qs({ district_id: e.target.value, size: 200 })); $("#a-f").innerHTML = opts(f.items, "", "—"); $("#a-f").disabled = false; };
  $("#a-ok").onclick = async () => { if (!+$("#a-r").value) return toast("Выберите регион");
    const id = tg || $("#a-id").value.trim(), numeric = /^\d+$/.test(id), common = { facility_id: +$("#a-f").value || 0, region_id: +$("#a-r").value || 0, kind: $("#a-k").value, fio: $("#a-fio").value || (tg ? "" : $("#a-n").value) };
    if (!id) return toast("Укажите @username или Telegram ID");
    try {
      if (tg) await api("/api/assignments", { method: "POST", body: { tg_id: tg, ...common } });
      else if (numeric) await api("/api/tg-users", { method: "POST", body: { tg_id: id, name: $("#a-n").value, ...common } });
      else { const r = await api("/api/preapproved", { method: "POST", body: { username: id, ...common } }); toast(r.claimed ? "Человек уже есть в боте: доступ открыт сразу" : "Записан: доступ откроется при первом сообщении боту"); closeModal(); return done(); }
      closeModal(); toast("Сохранено"); done(); } catch (e) { fail(e); } };
}
async function staffBox() {
  const [st] = await Promise.all([api("/api/staff")]);
  if (!$("#staffbox")) return;                                  // the person has left the page while the list was coming
  $("#staffbox").innerHTML = `<div class="card"><div class="row"><h2>Пользователи панели</h2><button class="btn pri right" id="st-add">+ Добавить</button></div><div class="scroll-x"><table><tr><th>Логин</th><th>Имя</th><th>Роль</th><th>Регионы</th><th></th></tr>${st.items.map(s => `<tr><td>${esc(s.login)}${s.active ? "" : ' <span class="pill critical">отключён</span>'}</td><td>${esc(s.name)}</td><td>${esc({ super_admin: "Главный администратор", admin: "Администратор", viewer: "Просмотр" }[s.role])}</td><td>${s.role === "super_admin" || !s.regions.length ? "все" : s.regions.map(id => esc(META.regions.find(r => r.id === id)?.name_ru || id)).join(", ")}</td><td class="row"><button class="btn sm" data-ed="${s.id}">Изменить</button><button class="btn sm" data-pw="${s.id}">Сбросить пароль</button></td></tr>`).join("")}</table></div></div>`;
  const form = s => modal(`<h2>${s ? "Изменить" : "Новый пользователь"}</h2>${s ? "" : `<label>Логин<input id="s-l"></label>`}<label>Имя<input id="s-n" value="${esc(s?.name || "")}"></label>
    <label>Роль<select id="s-r">${[["viewer", "Просмотр"], ["admin", "Администратор"], ["super_admin", "Главный администратор"]].map(([k, l]) => `<option value="${k}" ${s?.role === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    <label>Регионы (пусто = все; для администратора регионального уровня выберите свои)<select id="s-reg" multiple size="6">${META.regions.map(r => `<option value="${r.id}" ${s?.regions.includes(r.id) ? "selected" : ""}>${esc(r.name_ru)}</option>`).join("")}</select></label>
    <label>Telegram ID (для сводок)<input id="s-tg" value="${esc(s?.tg_id || "")}"></label>
    <label><input type="checkbox" id="s-mu" ${s?.can_manage_users ? "checked" : ""} style="width:auto"> Может управлять доступами</label><label><input type="checkbox" id="s-mt" ${s?.can_manage_territories ? "checked" : ""} style="width:auto"> Раздел «Территории»: добавлять и удалять районы и учреждения в своих регионах (для администратора)</label><label><input type="checkbox" id="s-er" ${s ? (s.can_edit_reports ? "checked" : "") : "checked"} style="width:auto"> Может исправлять отчёты</label>
    ${s ? `<label><input type="checkbox" id="s-ac" ${s.active ? "checked" : ""} style="width:auto"> Активен</label>` : ""}
    <div class="row mt"><button class="btn pri" id="s-ok">Сохранить</button><button class="btn right" data-close>Отмена</button></div>`);
  const body = s => ({ name: $("#s-n").value, role: $("#s-r").value, regions: [...$("#s-reg").selectedOptions].map(o => +o.value), tg_id: $("#s-tg").value, can_manage_users: $("#s-mu").checked, can_manage_territories: $("#s-mt").checked, can_edit_reports: $("#s-er").checked, ...(s ? { active: $("#s-ac").checked } : { login: $("#s-l").value }) });
  $("#st-add").onclick = () => { form(null); $("#s-ok").onclick = async () => { try { const r = await api("/api/staff", { method: "POST", body: body(null) }); modal(`<h2>Пользователь создан</h2><p>Пароль (показывается один раз):</p><p><b id="pwv">${esc(r.password || "задан вручную")}</b></p><button class="btn pri" id="pw-ok">Готово</button>`); $("#pw-ok").onclick = () => { closeModal(); people(); }; } catch (e) { fail(e); } }; };
  document.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => { const s = st.items.find(x => x.id === +b.dataset.ed); form(s); $("#s-ok").onclick = async () => { try { await api("/api/staff/" + s.id, { method: "PATCH", body: body(s) }); closeModal(); people(); } catch (e) { fail(e); } }; });
  document.querySelectorAll("[data-pw]").forEach(b => b.onclick = async () => { if (!confirm("Сгенерировать новый пароль?")) return; try { const r = await api(`/api/staff/${b.dataset.pw}/password`, { method: "POST", body: {} }); modal(`<h2>Новый пароль</h2><p><b id="pwv">${esc(r.password)}</b></p><button class="btn pri" data-close>Готово</button>`); } catch (e) { fail(e); } });
}

// ---------- territories
async function territories() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const SUP = ME.role === "super_admin";
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><div class="row"><h2>Территории</h2>${SUP ? `<button class="btn right" id="t-rep">Загрузить данные из Excel (учреждения и показатели за 2 дня)</button><button class="btn" id="t-imp">Импорт территорий</button><button class="btn pri" id="t-add">+ Регион</button>` : ""}</div><p class="muted sm">Нажмите на регион: откроются его районы и учреждения, их можно добавлять, менять и удалять${SUP ? "" : " (только в ваших регионах)"}.</p><div id="tt"></div></div>`;
  let cur = null;
  const load = async () => {
    META = await api("/api/meta");
    $("#tt").innerHTML = `<table><tr><th>Регион</th><th>Название (узб.)</th><th></th></tr>${META.regions.map(r => `<tr class="link${cur === r.id ? " sel" : ""}" data-id="${r.id}"><td>${esc(r.name_ru)}${r.active ? "" : ' <span class="pill critical">отключён</span>'}</td><td>${esc(r.name_uz)}</td><td>${SUP ? `<button class="btn sm" data-er="${r.id}">Изменить</button> <button class="btn sm bad" data-dr="${r.id}">Удалить</button>` : ""}</td></tr>`).join("")}</table><div id="tsub"></div>`;
    document.querySelectorAll("#tt tr[data-id]").forEach(tr => tr.onclick = ev => { if (ev.target.dataset.er || ev.target.dataset.dr) return; cur = +tr.dataset.id; load().then(() => regionView(cur)); });
    document.querySelectorAll("[data-er]").forEach(b => b.onclick = () => nameDlg("regions", META.regions.find(r => r.id === +b.dataset.er), load));
    document.querySelectorAll("[data-dr]").forEach(b => b.onclick = () => { const r = META.regions.find(x => x.id === +b.dataset.dr); confirmDlg("Удалить регион", `<p>Регион <b>${esc(r.name_ru)}</b> будет удалён вместе с пустыми районами. Если в нём есть учреждения или доступы, система откажет: сначала удалите их.</p>`, "Удалить регион", async () => { await api("/api/regions/" + r.id, { method: "DELETE" }); closeModal(); if (cur === r.id) cur = null; toast("Регион удалён"); load(); }); });
  };
  // the region opened: its districts and all its facilities in one place
  const regionView = async (rid, q = "", did = "") => {
    const [d, f] = await Promise.all([api("/api/districts?region_id=" + rid), api("/api/facilities?" + qs({ region_id: rid, district_id: did, q, size: 200 }))]);
    if (!$("#tsub")) return;
    $("#tsub").innerHTML = `<h3 class="mt">Районы <button class="btn sm" id="d-add">+ Район</button></h3>
      <table><tr><th>Район</th><th></th></tr>${d.items.map(x => `<tr><td>${esc(x.name_ru)}${x.active ? "" : " (отключён)"}</td><td><button class="btn sm" data-ed="${x.id}">Изменить</button> <button class="btn sm bad" data-dd="${x.id}">Удалить</button></td></tr>`).join("") || '<tr><td colspan="2" class="muted">Районов нет</td></tr>'}</table>
      <div class="row mt"><h3 style="margin:0">Учреждения региона <span class="muted sm">(${f.total})</span></h3><select id="f-d"><option value="">Все районы</option>${d.items.map(x => `<option value="${x.id}" ${String(x.id) === String(did) ? "selected" : ""}>${esc(x.name_ru)}</option>`).join("")}</select><input id="f-q" placeholder="Поиск" value="${esc(q)}"><button class="btn pri right" id="f-add">+ Учреждение</button></div>
      <div class="scroll-x"><table><tr><th>Учреждение</th><th>Район</th><th>Ответственные</th><th>Отчётов</th><th></th></tr>${f.items.map(x => `<tr><td>${esc(x.name_ru)}${x.active ? "" : " (отключено)"}</td><td>${esc(x.district)}</td><td>${x.assignments.map(a => esc(a.fio || a.first_name || a.tg_id) + (a.kind === "reserve" ? " (резерв)" : "")).join(", ") || '<span class="muted">нет</span>'}</td><td class="n">${x.reports}</td><td><button class="btn sm" data-ef="${x.id}">Изменить</button> <button class="btn sm bad" data-df="${x.id}">Удалить</button></td></tr>`).join("") || '<tr><td colspan="5" class="muted">Учреждений нет</td></tr>'}</table></div>${f.total > f.items.length ? `<p class="muted sm">Показаны первые ${f.items.length} из ${f.total}: уточните поиском или районом.</p>` : ""}`;
    const again = () => regionView(rid, $("#f-q") ? $("#f-q").value : q, $("#f-d") ? $("#f-d").value : did);
    $("#d-add").onclick = () => nameDlg("districts", { region_id: rid }, again, true);
    document.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => nameDlg("districts", d.items.find(x => x.id === +b.dataset.ed), again));
    document.querySelectorAll("[data-dd]").forEach(b => b.onclick = () => { const x = d.items.find(y => y.id === +b.dataset.dd); confirmDlg("Удалить район", `<p>Район <b>${esc(x.name_ru)}</b> будет удалён. Если в нём есть учреждения, система откажет: сначала удалите их.</p>`, "Удалить район", async () => { await api("/api/districts/" + x.id, { method: "DELETE" }); closeModal(); toast("Район удалён"); again(); }); });
    $("#f-d").onchange = again; $("#f-q").oninput = () => { clearTimeout(DEB); DEB = setTimeout(async () => { const pos = $("#f-q").value; await again(); const el = $("#f-q"); if (el) { el.focus(); el.setSelectionRange(pos.length, pos.length); } }, 300); };
    $("#f-add").onclick = () => facAddDlg(d.items.filter(x => x.active), did, again);
    document.querySelectorAll("[data-ef]").forEach(b => b.onclick = () => nameDlg("facilities", f.items.find(x => x.id === +b.dataset.ef), again));
    document.querySelectorAll("[data-df]").forEach(b => b.onclick = () => { const x = f.items.find(y => y.id === +b.dataset.df);
      confirmDlg("Удалить учреждение", `<p>Учреждение <b>${esc(x.name_ru)}</b> (${esc(x.district)}) будет удалено.</p><ul class="sm"><li>Отчётов, которые удалятся вместе с ним: <b>${x.reports}</b></li><li>Ответственных, у которых пропадёт привязка: <b>${x.assignments.length}</b> (в боте они останутся)</li></ul><p class="muted sm">Если нужно только скрыть учреждение из отчётности, используйте «Изменить» и снимите «Активно»: данные сохранятся.</p>`, "Удалить безвозвратно", async () => { await api("/api/facilities/" + x.id + "?force=1", { method: "DELETE" }); closeModal(); toast("Учреждение удалено"); again(); }); });
  };
  if (SUP) { $("#t-add").onclick = () => nameDlg("regions", {}, load, true); $("#t-imp").onclick = () => importDlg(load); $("#t-rep").onclick = () => reportImportDlg(load); }
  load();
}
function facAddDlg(districts, did, done) {
  if (!districts.length) { toast("Сначала добавьте район"); return; }
  modal(`<h2>Добавить учреждение</h2><label>Район<select id="fa-d">${districts.map(x => `<option value="${x.id}" ${String(x.id) === String(did) ? "selected" : ""}>${esc(x.name_ru)}</option>`).join("")}</select></label><label>Название (рус.)<input id="fa-ru"></label><label>Название (узб.)<input id="fa-uz"></label><div id="fa-err" class="err"></div><div class="row mt"><button class="btn pri" id="fa-ok">Добавить</button><button class="btn right" data-close>Отмена</button></div>`);
  $("#fa-ok").onclick = async () => { try { await api("/api/facilities", { method: "POST", body: { district_id: +$("#fa-d").value, name_ru: $("#fa-ru").value, name_uz: $("#fa-uz").value } }); closeModal(); toast("Учреждение добавлено"); done(); } catch (e) { $("#fa-err").textContent = e.message; } };
}
function nameDlg(kind, o, done, isNew) {
  modal(`<h2>${isNew ? "Добавить" : "Изменить"}</h2><label>Название (рус.)<input id="n-ru" value="${esc(o.name_ru || "")}"></label><label>Название (узб.)<input id="n-uz" value="${esc(o.name_uz || "")}"></label>
  ${isNew ? "" : `<label><input type="checkbox" id="n-ac" ${o.active ? "checked" : ""} style="width:auto"> Активно (отключённое не входит в отчёты)</label>`}<div class="row mt"><button class="btn pri" id="n-ok">Сохранить</button><button class="btn right" data-close>Отмена</button></div>`);
  $("#n-ok").onclick = async () => { const body = { name_ru: $("#n-ru").value, name_uz: $("#n-uz").value }; if (!isNew) body.active = $("#n-ac").checked; else Object.assign(body, o);
    try { await api(isNew ? "/api/" + kind : `/api/${kind}/${o.id}`, { method: isNew ? "POST" : "PATCH", body }); closeModal(); done(); } catch (e) { fail(e); } };
}
function reportImportDlg(done) {
  modal(`<h2>Загрузка учреждений и показателей из Excel</h2><p class="muted">Файл вида «места для больных»: по листу на область, строка на учреждение (койки, свободные, обращения за 24 часа, поступило и выписано вчера/сегодня). Новые учреждения создаются в своей области, показатели записываются как отчёты. Чего в файле нет (тяжёлые и т.п.), остаётся пустым.</p>
  <div class="row"><label>«Вчера» записать на дату<input type="date" id="ri-p" value="${addDays(ME.today, -1)}"></label><label>«Сегодня» записать на дату<input type="date" id="ri-t" value="${ME.today}"></label></div>
  <input type="file" id="ri-f" accept=".xlsx" class="mt"><div id="ri-r" class="mt"></div><div class="row mt"><button class="btn" id="ri-pre">Проверить</button><button class="btn pri" id="ri-go" disabled>Загрузить</button><button class="btn right" data-close>Закрыть</button></div>`, true);
  const run = async dry => { const f = $("#ri-f").files[0]; if (!f) return toast("Выберите файл"); const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/import/reports?" + qs({ dry, d_prev: $("#ri-p").value, d_today: $("#ri-t").value }), { method: "POST", form: fd });
      $("#ri-r").innerHTML = `<p><b>${r.dry ? "Будет сделано" : "Готово"}:</b> учреждений в файле ${r.facilities}, новых ${r.new_facilities}, отчётов ${r.reports}${r.errors_total ? `, ошибок ${r.errors_total}` : ""}. Даты: ${r.dates.join(" и ")}.</p>${r.errors.length ? `<div class="alert critical">${r.errors.map(esc).join("<br>")}</div>` : ""}${r.new_list.length ? `<details><summary>Новые учреждения (${r.new_facilities})</summary><p class="sm">${r.new_list.map(esc).join("<br>")}</p></details>` : ""}`;
      $("#ri-go").disabled = !r.dry || !!r.errors_total; if (!r.dry) { toast("Загружено"); done(); } } catch (e) { fail(e); } };
  $("#ri-pre").onclick = () => run(1); $("#ri-go").onclick = () => run(0);
}
function importDlg(done) {
  modal(`<h2>Импорт территорий</h2><p class="muted">Столбцы: Регион, Район, Учреждение (+ необязательно «Район (узб)», «Учреждение (узб)»). Сначала предпросмотр.</p><input type="file" id="i-f" accept=".xlsx,.csv"><div id="i-r" class="mt"></div><div class="row mt"><button class="btn" id="i-pre">Проверить</button><button class="btn pri" id="i-go" disabled>Загрузить</button><button class="btn right" data-close>Закрыть</button></div>`);
  const run = async dry => { const f = $("#i-f").files[0]; if (!f) return toast("Выберите файл"); const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/geo/import?dry=" + dry, { method: "POST", form: fd }); $("#i-r").innerHTML = `<pre>${esc(JSON.stringify(r, null, 1))}</pre>`; $("#i-go").disabled = !!dry ? !(r.errors && r.errors.length === 0) : true; if (!dry) { toast("Загружено"); done(); } } catch (e) { fail(e); } };
  $("#i-pre").onclick = () => run(1); $("#i-go").onclick = () => run(0);
}

// ---------- indicators and rules
async function indicators() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const r = await api("/api/indicators");
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><div class="row"><h2>Показатели</h2><button class="btn pri right" id="i-add">+ Показатель</button></div><p class="muted sm">«Способ сложения»: sum — потоки (обращения), last — состояние на последний день (койки), max — максимум за период.</p><div class="scroll-x"><table><tr><th>Код</th><th>Название</th><th>Сложение</th><th>Активен</th><th></th></tr>${r.items.map(i => `<tr><td>${esc(i.code)}${i.core ? " 🔒" : ""}</td><td>${esc(i.name_ru)}</td><td>${i.agg}</td><td>${i.active ? "да" : "нет"}</td><td><button class="btn sm" data-i="${i.code}">Изменить</button></td></tr>`).join("")}</table></div></div>
  <div class="card"><div class="row"><h2>Правила проверки</h2><button class="btn pri right" id="r-add">+ Правило</button></div><div class="scroll-x"><table><tr><th>Вид</th><th>Условие (должно выполняться)</th><th>Сообщение</th><th>Вкл.</th><th></th></tr>${r.rules.map(x => `<tr><td>${x.kind === "error" ? '<span class="pill critical">ошибка</span>' : '<span class="pill warning">предупреждение</span>'}</td><td><code>${esc(x.expr)}</code></td><td>${esc(x.message_ru)}</td><td>${x.active ? "да" : "нет"}</td><td><button class="btn sm" data-r="${x.id}">Изменить</button></td></tr>`).join("")}</table></div></div>`;
  $("#i-add").onclick = () => indDlg(null); document.querySelectorAll("[data-i]").forEach(b => b.onclick = () => indDlg(r.items.find(i => i.code === b.dataset.i)));
  $("#r-add").onclick = () => ruleDlg(null); document.querySelectorAll("[data-r]").forEach(b => b.onclick = () => ruleDlg(r.rules.find(x => x.id === +b.dataset.r)));
}
function indDlg(i) {
  modal(`<h2>${i ? "Показатель" : "Новый показатель"}</h2>${i ? "" : `<label>Код (латиница)<input id="p-c"></label>`}<label>Название (рус.)<input id="p-n" value="${esc(i?.name_ru || "")}"></label><label>Название (узб.)<input id="p-u" value="${esc(i?.name_uz || "")}"></label><label>Подсказка<input id="p-h" value="${esc(i?.hint_ru || "")}"></label>
  <label>Сложение<select id="p-a">${["sum", "last", "max"].map(a => `<option ${i?.agg === a ? "selected" : ""}>${a}</option>`).join("")}</select></label>${i ? `<label><input type="checkbox" id="p-ac" ${i.active ? "checked" : ""} style="width:auto"> Активен</label>` : ""}<div class="row mt"><button class="btn pri" id="p-ok">Сохранить</button><button class="btn right" data-close>Отмена</button></div>`);
  $("#p-ok").onclick = async () => { const body = { name_ru: $("#p-n").value, name_uz: $("#p-u").value, hint_ru: $("#p-h").value, agg: $("#p-a").value }; if (i) body.active = $("#p-ac").checked; else body.code = $("#p-c").value;
    try { await api(i ? "/api/indicators/" + i.code : "/api/indicators", { method: i ? "PATCH" : "POST", body }); META = await api("/api/meta"); closeModal(); indicators(); } catch (e) { fail(e); } };
}
function ruleDlg(x) {
  modal(`<h2>${x ? "Правило" : "Новое правило"}</h2><label>Условие: оно должно быть верным (например beds_occupied &lt;= beds_flu)<input id="q-e" value="${esc(x?.expr || "")}"></label><label>Вид<select id="q-k"><option value="error" ${x?.kind === "error" ? "selected" : ""}>Ошибка (блокирует отправку)</option><option value="warning" ${x?.kind === "warning" ? "selected" : ""}>Предупреждение</option></select></label>
  <label>Сообщение (рус.; можно {код})<input id="q-m" value="${esc(x?.message_ru || "")}"></label><label>Сообщение (узб.)<input id="q-u" value="${esc(x?.message_uz || "")}"></label><label><input type="checkbox" id="q-a" ${!x || x.active ? "checked" : ""} style="width:auto"> Включено</label>
  <div class="row mt"><button class="btn pri" id="q-ok">Сохранить</button>${x && !x.core ? '<button class="btn bad" id="q-del">Удалить</button>' : ""}<button class="btn right" data-close>Отмена</button></div>`);
  $("#q-ok").onclick = async () => { const body = { expr: $("#q-e").value, kind: $("#q-k").value, message_ru: $("#q-m").value, message_uz: $("#q-u").value, active: $("#q-a").checked };
    try { await api(x ? "/api/rules/" + x.id : "/api/rules", { method: x ? "PATCH" : "POST", body }); closeModal(); indicators(); } catch (e) { fail(e); } };
  const d = $("#q-del"); if (d) d.onclick = async () => { if (!confirm("Удалить правило?")) return; try { await api("/api/rules/" + x.id, { method: "DELETE" }); closeModal(); indicators(); } catch (e) { fail(e); } };
}

// ---------- settings
const SET = [["deadline_time", "Срок сдачи (время)", "time"], ["deadline_day_offset", "Срок: через сколько дней после отчётной даты (0 = в тот же день)", "number"], ["backfill_days", "Сколько дней назад можно сдавать отчёт", "number"],
  ["allow_user_edit", "Ответственный может исправлять свой отчёт (1/0)", "number"], ["edit_window_hours", "Окно правки для ответственного, часов", "number"], ["lock_after_days", "Закрывать отчёт для правок через, дней", "number"],
  ["remind_enabled", "Напоминания включены (1/0)", "number"], ["remind_times", "Время напоминаний (через запятую, ЧЧ:ММ)", "text"], ["remind_weekdays", "Дни напоминаний (1=пн … 7=вс)", "text"],
  ["admin_summary_time", "Сводка администраторам (время)", "time"], ["admin_overdue_time", "Список не сдавших (время)", "time"],
  ["occ_elevated", "Порог: повышенная нагрузка, %", "number"], ["occ_critical", "Порог: критическая загрузка, %", "number"], ["fac_occ_warn", "Порог для учреждения, %", "number"],
  ["growth_warn_pct", "Рост обращений: предупреждение, %", "number"], ["growth_crit_pct", "Рост: тревога, %", "number"], ["severe_growth_pct", "Рост тяжёлых, %", "number"], ["hosp_growth_pct", "Рост госпитализаций, %", "number"], ["org_title", "Название организации (для отчётов)", "text"]];
async function settings() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const r = await api("/api/settings");
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><h2>Настройки</h2><p class="muted">Бот: ${r.bot.configured ? "подключён" + (r.bot.username ? " (@" + esc(r.bot.username) + ")" : "") : "токен не задан (TELEGRAM_BOT_TOKEN)"} ${r.bot.error ? "· ошибка: " + esc(r.bot.error) : ""}</p><div class="fields">${SET.map(([k, l, t]) => `<label>${l}<input data-k="${k}" type="${t === "time" ? "time" : t}" value="${esc(r.settings[k] ?? "")}"></label>`).join("")}</div>
  <div class="row mt"><button class="btn pri" id="s-save">Сохранить</button><button class="btn" id="s-run">Проверить рассылку (без отправки)</button><button class="btn" id="s-bk">Резервная копия</button></div><pre id="s-out"></pre></div>`;
  $("#s-save").onclick = async () => { try { await api("/api/settings", { method: "PUT", body: Object.fromEntries([...document.querySelectorAll("[data-k]")].map(i => [i.dataset.k, i.value])) }); toast("Сохранено"); } catch (e) { fail(e); } };
  $("#s-run").onclick = async () => { try { const x = await api("/api/notify/run", { method: "POST", body: { dry: true, force: true } }); $("#s-out").textContent = JSON.stringify(x.items, null, 1); } catch (e) { fail(e); } };
  $("#s-bk").onclick = async () => { try { toast("Создана: " + (await api("/api/backup", { method: "POST" })).file); } catch (e) { fail(e); } };
}

// ---------- audit
async function audit() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const r = await api("/api/audit?limit=300");
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><h2>Журнал действий</h2><p class="muted sm">Записи неизменяемы: изменить или удалить их нельзя.</p><div class="scroll-x"><table><tr><th>Когда</th><th>Кто</th><th>Действие</th><th>Объект</th><th>Подробности</th></tr>${r.items.map(x => `<tr><td>${esc(x.at || x.created_at)}</td><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td>${esc(x.entity)} ${esc(x.entity_id)}</td><td class="sm">${esc(typeof x.details === "string" ? x.details : JSON.stringify(x.details))}</td></tr>`).join("")}</table></div></div>`;
}

// ---------- export
async function exportView() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const fb = await filterBar(exportView);
  if (nav !== NAVID) return; view.innerHTML = fb.html + `<div class="card"><h2>Выгрузка</h2><p class="muted">Сводный отчёт за выбранный период и территорию. В Excel — 3 листа (сводка, детали, динамика), печать A4 с повтором шапки и полями для подписей.</p>
  <div class="row"><label>Вид<select id="x-k"><option value="daily">Ежедневный</option><option value="weekly">Недельный</option><option value="monthly">Месячный</option><option value="custom" selected>Произвольный период</option></select></label>
  ${["xlsx", "pdf", "csv"].map(f => `<a class="btn pri" data-f="${f}" href="#">${f.toUpperCase()}</a>`).join("")}</div></div>`; fb.bind();
  document.querySelectorAll("[data-f]").forEach(a => a.onclick = e => { e.preventDefault(); location.href = "/api/export?" + scopeQ() + "&" + qs({ fmt: a.dataset.f, kind: $("#x-k").value }); });
}

// ---------- broadcast: a message written here goes to the people of the bot
let BCPOLL = null;
async function broadcastView() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  clearTimeout(BCPOLL);
  const AUD = { all: "Все, у кого есть доступ", regions: "Выбранные регионы", unsent: "Не сдавшие сводку сегодня" };
  const regs = (ME.regions === null ? META.regions : META.regions.filter(r => ME.regions.includes(r.id)));
  let mode = "all", chosen = new Set();
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><div class="row"><h2>Рассылка</h2><span class="muted sm">сообщение придёт в Telegram тем, кто пользуется ботом</span></div>
    <div class="lbl">Кому</div><div class="chips" id="bc-mode">${Object.entries(AUD).map(([k, l]) => `<button class="chip${k === mode ? " on" : ""}" data-m="${k}">${l}</button>`).join("")}</div>
    <div class="chips" id="bc-regs" hidden>${regs.map(r => `<button class="chip" data-r="${r.id}">${esc(r.name_ru.replace("Республика ", "").replace(" область", "").replace("город ", "г. "))}</button>`).join("")}</div>
    <div class="grid2"><label>Текст по-узбекски (O‘zbekcha)<textarea id="bc-uz" rows="6" maxlength="3500" placeholder="Xabar matni"></textarea><span class="muted sm" id="bc-uz-n">0 / 3500</span></label>
    <label>Текст по-русски<textarea id="bc-ru" rows="6" maxlength="3500" placeholder="Текст сообщения"></textarea><span class="muted sm" id="bc-ru-n">0 / 3500</span></label></div>
    <p class="muted sm">Каждый получит текст на своём языке бота. Если один язык оставить пустым, его получатели увидят текст на другом. Перед текстом бот добавит строку «📢 Объявление».</p>
    <div class="row mt"><button class="btn pri" id="bc-go">Предпросмотр и отправка</button><button class="btn" id="bc-test">🧪 Тест себе</button><input id="bc-tid" placeholder="Telegram ID для теста (если не указан в профиле)" style="max-width:300px"></div></div>
    <div class="card"><div class="row"><h2>История рассылок</h2></div><div id="bc-list" class="scroll-x"></div></div>`;
  const spec = () => ({ mode, regions: [...chosen] });
  const body = () => ({ audience: spec(), text_ru: $("#bc-ru").value, text_uz: $("#bc-uz").value });
  ["uz", "ru"].forEach(l => $("#bc-" + l).oninput = () => { $("#bc-" + l + "-n").textContent = $("#bc-" + l).value.length + " / 3500"; });
  $("#bc-mode").onclick = e => { const b = e.target.closest("[data-m]"); if (!b) return; mode = b.dataset.m; $("#bc-mode").querySelectorAll(".chip").forEach(x => x.classList.toggle("on", x === b)); $("#bc-regs").hidden = mode !== "regions"; };
  $("#bc-regs").onclick = e => { const b = e.target.closest("[data-r]"); if (!b) return; const id = b.dataset.r; chosen.has(id) ? chosen.delete(id) : chosen.add(id); b.classList.toggle("on", chosen.has(id)); };
  $("#bc-test").onclick = async () => { try { const r = await api("/api/broadcasts/test", { method: "POST", body: { ...body(), tg_id: $("#bc-tid").value.trim() } }); toast("Тест отправлен (Telegram ID " + r.sent_to + ")"); } catch (e) { fail(e); } };
  $("#bc-go").onclick = async () => {
    let pv; try { pv = await api("/api/broadcasts/preview", { method: "POST", body: body() }); } catch (e) { return fail(e); }
    modal(`<h2>📢 Проверьте рассылку</h2><p>Кому: <b>${esc(AUD[mode])}</b>${mode === "regions" ? ` (${chosen.size})` : ""} · получателей: <b>${pv.total}</b> (по-узбекски ${pv.uz}, по-русски ${pv.ru})</p>
      ${pv.fallback ? `<div class="note">У ${pv.fallback} человек язык, на котором вы ничего не написали: они получат текст на другом языке.</div>` : ""}
      ${pv.total ? `<div class="bcsample"><div class="muted sm">Так увидит человек с узбекским ботом:</div><div class="bcmsg">${pv.sample_uz.replace(/\n/g, "<br>")}</div><div class="muted sm">С русским:</div><div class="bcmsg">${pv.sample_ru.replace(/\n/g, "<br>")}</div></div>
      <details><summary>Получатели (${pv.total})</summary><p class="sm">${pv.people.map(esc).join(", ")}${pv.total > pv.people.length ? "…" : ""}</p></details>` : `<div class="alert critical">Получателей нет.</div>`}
      <div class="row mt"><button class="btn pri" id="bc-ok" ${pv.total ? "" : "disabled"}>Отправить ${pv.total || ""}</button><button class="btn right" data-close>Назад</button></div>`, true);
    const ok = $("#bc-ok"); if (ok) ok.onclick = async () => { ok.disabled = true; try { await api("/api/broadcasts", { method: "POST", body: { ...body(), confirm: true } }); closeModal(); toast("Рассылка запущена"); $("#bc-ru").value = $("#bc-uz").value = ""; list(); } catch (e) { fail(e); ok.disabled = false; } };
  };
  const STX = { sending: ["warning", "Отправляется"], done: ["sent", "Готово"], interrupted: ["critical", "Прервана"] };
  const list = async () => {
    clearTimeout(BCPOLL);
    let r; try { r = await api("/api/broadcasts"); } catch (e) { return fail(e); }
    if (!$("#bc-list")) return;
    $("#bc-list").innerHTML = r.items.length ? `<table><tr><th>Когда</th><th>От кого</th><th>Текст</th><th>Кому</th><th>Итог</th><th></th></tr>${r.items.map(b => { const a = JSON.parse(b.audience || "{}"), [cls, lbl] = STX[b.status] || ["", b.status]; const pct = b.total ? Math.round(100 * (b.sent + b.failed) / b.total) : 0;
      return `<tr><td>${esc(b.created_at)}</td><td>${esc(b.by_name)}</td><td class="sm" style="max-width:320px">${esc((b.text_uz || b.text_ru).slice(0, 110))}${(b.text_uz || b.text_ru).length > 110 ? "…" : ""}</td><td>${esc(AUD[a.mode || "all"] || "")}</td>
        <td><span class="pill ${cls}">${lbl}</span> отправлено <b>${b.sent}</b> из ${b.total}${b.failed ? `, не доставлено <b>${b.failed}</b>` : ""}${b.status === "sending" ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ""}</td>
        <td class="row">${b.failed ? `<button class="btn sm" data-fl="${b.id}">Кому не дошло</button>` : ""}${(b.status === "interrupted" || (b.status === "done" && b.failed)) ? `<button class="btn sm" data-rs="${b.id}">${b.status === "interrupted" ? "Продолжить" : "Повторить"}</button>` : ""}</td></tr>`; }).join("")}</table>` : `<p class="muted">Рассылок пока не было.</p>`;
    $("#bc-list").querySelectorAll("[data-rs]").forEach(b => b.onclick = async () => { try { await api(`/api/broadcasts/${b.dataset.rs}/resume`, { method: "POST", body: {} }); list(); } catch (e) { fail(e); } });
    $("#bc-list").querySelectorAll("[data-fl]").forEach(b => b.onclick = async () => { try { const f = await api(`/api/broadcasts/${b.dataset.fl}/failures`); modal(`<h2>Не доставлено</h2><p class="muted sm">Обычно человек остановил или заблокировал бота.</p><div class="scroll-x"><table><tr><th>Кто</th><th>Причина</th></tr>${f.items.map(x => `<tr><td>${esc(x.name || x.username || x.tg_id)} <span class="muted">${esc(x.tg_id)}</span></td><td class="sm">${esc(x.error)}</td></tr>`).join("")}</table></div><div class="row mt"><button class="btn right" data-close>Закрыть</button></div>`); } catch (e) { fail(e); } });
    if (r.items.some(b => b.status === "sending")) BCPOLL = setTimeout(() => { if (location.hash.startsWith("#/broadcast")) list(); }, 2000);
  };
  list();
}

// ---------- confidential messages of the facilities for the Ministry: one chat per Telegram profile (the super administrator only)
const MSG = { sel: null, q: "", only: false, region: "", drafts: {}, keepUnread: null };
async function messagesView() {
  const nav = NAVID;
  let items = [], unreadAll = 0;
  const dt = at => new Date(String(at).replace(" ", "T")), pad = n => String(n).padStart(2, "0");
  const hhmm = at => { const d = dt(at); return isNaN(d) ? "" : pad(d.getHours()) + ":" + pad(d.getMinutes()); };
  const dayKey = at => String(at).slice(0, 10);
  const dayLabel = at => { const k = dayKey(at), y = new Date(dt(ME.today + " 00:00").getTime() - 864e5), yk = `${y.getFullYear()}-${pad(y.getMonth() + 1)}-${pad(y.getDate())}`;
    return k === ME.today ? "Сегодня" : k === yk ? "Вчера" : dt(at).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }); };
  const listTime = at => dayKey(at) === ME.today ? hhmm(at) : dt(at).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
  const person = t => ({ tg_id: t.tg_id, first_name: t.name || "", last_name: "", username: t.username });
  const placeText = m => `${m.region} — ${m.facility}` + (m.report_date ? ` · отчёт за ${m.report_date}` : "");
  const cur = () => items.find(t => t.tg_id === MSG.sel);
  const shown = () => {
    const q = MSG.q.trim().toLowerCase();
    return items.filter(t => (!MSG.only || t.unread) && (!MSG.region || String(t.region_id) === MSG.region)
      && (!q || [t.name, t.username, t.tg_id, ...t.places.map(p => `${p.region} ${p.district} ${p.facility}`), ...t.messages.map(m => m.text)].join(" ").toLowerCase().includes(q)));
  };
  const setUnread = n => { ME.messages_unread = n; badgeMessages(); };
  const markRead = async (t, read) => {
    try { await api(`/api/messages/${t.thread_id}/read`, { method: "POST", body: { read } }); } catch (e) { return fail(e); }
    const was = t.unread; t.unread = read ? 0 : t.messages.filter(m => m.direction === "in").length; unreadAll += t.unread - was; setUnread(unreadAll); drawList(); drawChat(false);
  };
  const itemHtml = t => { const last = t.messages[t.messages.length - 1];
    return `<button class="mchat${t.tg_id === MSG.sel ? " on" : ""}${t.unread ? " unread" : ""}" data-c="${esc(t.tg_id)}">${tgAv(person(t))}
      <span class="mc-txt"><span class="mc-top"><b>${esc(t.name || "Без имени")}</b><span class="mc-time">${esc(listTime(t.last_at))}</span></span>
      <span class="mc-place">${esc(t.region)} · ${esc(t.facility)}${t.places.length > 1 ? ` <i>+${t.places.length - 1}</i>` : ""}</span>
      <span class="mc-top"><span class="mc-last">${last.direction === "out" ? "Вы: " : ""}${esc(last.text.replace(/\s+/g, " "))}</span>${t.unread ? `<span class="pill critical">${t.unread}</span>` : ""}</span></span></button>`; };
  function drawList() {
    const box = $("#ml"); if (!box) return;
    const list = shown(), top = box.scrollTop;
    box.innerHTML = list.length ? list.map(itemHtml).join("") : `<p class="muted sm" style="padding:14px">${MSG.q || MSG.region || MSG.only ? "Ничего не найдено." : "Сообщений пока нет. Люди могут оставить его последним вопросом бота."}</p>`;
    box.scrollTop = top; dropBrokenAvatars(box);
    box.querySelectorAll("[data-c]").forEach(b => b.onclick = () => select(b.dataset.c));
  }
  const bubble = m => `<div class="bub ${m.direction === "out" ? "out" : "in"}"><div class="msgtext">${esc(m.text)}</div><div class="bubmeta">${m.direction === "out" ? "Министерство" + (m.by ? " · " + esc(m.by) : "") + " · " : ""}${esc(hhmm(m.at))}</div>${m.error ? `<div class="bubwarn">⚠️ В Telegram не доставлено: ${esc(m.error)}</div>` : ""}</div>`;
  function drawChat(scroll = true) {
    const box = $("#mc"); if (!box) return;
    const t = cur(), wrap = $("#msgs");
    wrap.classList.toggle("has-chat", !!t);
    if (!t) { box.innerHTML = `<div class="mc-empty"><div style="font-size:42px">💬</div><p class="muted">Выберите чат слева</p></div>`; return; }
    const keepDraft = MSG.drafts[t.tg_id] || "";
    let html = "", day = "", ctx = "";
    for (const m of t.messages) {
      if (dayKey(m.at) !== day) { day = dayKey(m.at); html += `<div class="mdate"><span>${esc(dayLabel(m.at))}</span></div>`; }
      const c = placeText(m); if (c !== ctx) { ctx = c; html += `<div class="mctx">📍 ${esc(c)}</div>`; }
      html += bubble(m);
    }
    box.innerHTML = `<div class="mc-head"><button class="btn sm mc-back" id="m-back">←</button>${tgAv(person(t))}<div class="mc-who"><b>${esc(t.name || "Без имени")}</b><div class="muted sm">${t.username ? "@" + esc(t.username) + " · " : ""}ID ${esc(t.tg_id)}</div></div>
        <div class="mc-act">${tgLink(person(t))}<button class="btn sm" id="m-unread">${t.unread ? "Отметить прочитанным" : "Отметить непрочитанным"}</button></div></div>
      <div class="mc-places">${t.places.map(p => `<span class="chip-s" title="${esc(p.district)}">${esc(p.region)} — ${esc(p.facility)}</span>`).join("")}</div>
      <div class="mc-body" id="m-body"><div class="thread">${html}</div></div>
      <div class="replybox"><textarea rows="2" maxlength="1000" id="m-ta" placeholder="Ответ получит ${esc(t.name || "учреждение")} в Telegram с кнопкой «Ответить». Ctrl+Enter — отправить">${esc(keepDraft)}</textarea><button class="btn pri" id="m-send">Ответить</button></div>`;
    dropBrokenAvatars(box);
    const body = $("#m-body"); if (scroll) body.scrollTop = body.scrollHeight;
    const ta = $("#m-ta");
    ta.oninput = () => { MSG.drafts[t.tg_id] = ta.value; };
    const send = async () => { const text = ta.value.trim(); if (!text) return toast("Напишите ответ");
      try { const x = await api(`/api/messages/${t.thread_id}/reply`, { method: "POST", body: { text } }); MSG.drafts[t.tg_id] = ""; toast(x.delivered ? "Ответ отправлен" : "Ответ сохранён, но Telegram его не принял: " + x.error); await load(true); } catch (e) { fail(e); } };
    $("#m-send").onclick = send;
    ta.onkeydown = e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } };
    $("#m-unread").onclick = () => { MSG.keepUnread = t.unread ? null : t.tg_id; markRead(t, !!t.unread); };
    $("#m-back").onclick = () => { MSG.sel = null; drawList(); drawChat(); };
  }
  function select(id) {
    MSG.sel = id; MSG.keepUnread = null; drawList(); drawChat();
    const t = cur(); if (t && t.unread) markRead(t, true);
  }
  async function load(scroll) {
    let r; try { r = await api("/api/messages"); } catch (e) { return fail(e); }
    if (nav !== NAVID) return;
    items = r.items; unreadAll = r.unread; setUnread(unreadAll);
    if (MSG.sel && !cur()) MSG.sel = null;
    if (!MSG.sel && window.innerWidth > 820 && items.length) MSG.sel = (shown().find(t => t.unread) || shown()[0] || items[0]).tg_id;
    drawList(); drawChat(scroll);
    const t = cur(); if (t && t.unread && MSG.keepUnread !== t.tg_id && !document.hidden) markRead(t, true);        // the chat is open: what arrived is read
  }
  view.innerHTML = `<div class="card msgcard-wrap"><div class="row"><h2>Сообщения для Министерства</h2><span class="muted sm">🔒 конфиденциально: видны только главному администратору; областные администраторы и просмотр их не видят, в выгрузки они не попадают</span></div>
    <div class="msgs" id="msgs"><div class="ml-col"><div class="ml-head"><input type="search" id="m-q" placeholder="Поиск: имя, учреждение, текст…" value="${esc(MSG.q)}"><div class="row" style="gap:6px;flex-wrap:nowrap"><div class="seg" id="m-f"><button data-f="all">Все</button><button data-f="unread">Непрочитанные</button></div><select id="m-r" style="min-width:0;flex:1"><option value="">Все области</option></select></div></div><div class="ml" id="ml"></div></div>
    <div class="mc" id="mc"></div></div></div>`;
  const seg = () => view.querySelectorAll("#m-f button").forEach(b => b.classList.toggle("on", (b.dataset.f === "unread") === MSG.only));
  seg();
  view.querySelectorAll("#m-f button").forEach(b => b.onclick = () => { MSG.only = b.dataset.f === "unread"; seg(); drawList(); });
  $("#m-q").oninput = e => { MSG.q = e.target.value; drawList(); };
  $("#m-r").onchange = e => { MSG.region = e.target.value; drawList(); };
  await load(true);
  const sel = $("#m-r"); if (sel) { const seen = new Map(items.map(t => [String(t.region_id), t.region])); sel.innerHTML = `<option value="">Все области</option>` + [...seen].sort((a, b) => a[1].localeCompare(b[1], "ru")).map(([id, n]) => `<option value="${id}">${esc(n)}</option>`).join(""); sel.value = MSG.region; }
}
function badgeMessages() { const a = document.querySelector('#tabs a[data-t="messages"]'); if (a) a.innerHTML = "Сообщения" + (ME.messages_unread ? ` <span class="pill critical blink">${ME.messages_unread}</span>` : ""); }

// ---------- shell
// [name, label, page, right, group]: the pages of a group share one tab of the menu and a row of sub-tabs under it (SUBTABS lists them in the order of the row)
const TABS = [["dashboard", "Панель", dashboard, null], ["messages", "Сообщения", messagesView, "s"], ["forecast", "Прогноз", forecastView, null], ["reports", "Отчёты", reportsView, "w"], ["people", "Доступы", people, "u"],
  ["export", "Выгрузка", exportView, null], ["territories", "Территории", territories, "t"], ["broadcast", "Рассылка", broadcastView, "u"],
  ["settings", "Настройки", settings, "s", "settings"], ["control", "Контроль", control, "w", "settings"], ["indicators", "Показатели", indicators, "s", "settings"], ["audit", "Журнал", audit, "s"]];
const SUBTABS = { settings: [["settings", "Общие"], ["control", "Контроль"], ["indicators", "Показатели"]] };
function allowed(t) { return !t[3] || (t[3] === "s" && ME.role === "super_admin") || (t[3] === "w" && ME.role !== "viewer") || (t[3] === "u" && ME.role !== "viewer" && ME.can_manage_users) || (t[3] === "t" && ME.can_manage_territories); }
const tabOf = name => TABS.find(t => t[0] === name);
// the menu: a group is one tab (its label is its first page's) that leads to the first page of the group the person may open
const menuTabs = () => TABS.filter(t => !t[4] || t[0] === t[4]).map(t => { const g = (t[4] ? SUBTABS[t[4]].map(x => tabOf(x[0])) : [t]).filter(allowed); return g.length ? { name: t[0], label: t[4] && g.length === 1 ? g[0][1] : t[1], href: g[0][0] } : null; }).filter(Boolean);
function drawSubtabs(tab) {
  const box = $("#subtabs"), g = tab[4] ? SUBTABS[tab[4]].filter(x => allowed(tabOf(x[0]))) : [];
  box.innerHTML = g.length > 1 ? g.map(x => `<a href="#/${x[0]}" class="${x[0] === tab[0] ? "on" : ""}">${x[1]}</a>`).join("") : ""; box.hidden = g.length < 2;
}
let NAVID = 0;
function route() {
  NAVID++;
  const name = (location.hash.slice(2) || "dashboard").split("?")[0];
  const tab = TABS.find(t => t[0] === name && allowed(t)) || TABS[0];
  document.querySelectorAll("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.t === (tab[4] || tab[0])));
  drawSubtabs(tab);
  Promise.resolve(tab[2]()).catch(fail);
}
$("#pwbtn").onclick = () => { modal(`<h2>Смена пароля</h2><label>Текущий пароль<input type="password" id="o"></label><label>Новый пароль (от 8 знаков)<input type="password" id="n"></label><div class="row mt"><button class="btn pri" id="ok">Сменить</button><button class="btn right" data-close>Отмена</button></div>`);
  $("#ok").onclick = async () => { try { await api("/api/me/password", { method: "POST", body: { old: $("#o").value, new: $("#n").value } }); closeModal(); toast("Пароль изменён"); } catch (e) { fail(e); } }; };
(async () => {
  try { ME = await api("/api/me"); META = await api("/api/meta"); } catch (e) { return; }
  $("#who").textContent = `${ME.name && ME.name !== ME.role_label ? ME.name : ME.login} · ${ME.role_label}`;
  $("#tabs").innerHTML = menuTabs().map(t => `<a href="#/${t.href}" data-t="${t.name}">${t.label}</a>`).join("");
  window.addEventListener("hashchange", route); route(); badgeMessages();
  livePulse();
})();
// the data refreshes itself: when a report arrives (from the bot or another person) the open page reloads in place
const LIVE = ["dashboard", "control", "forecast", "reports", "messages"];
function livePulse() {
  let last = null, busy = false;
  const idle = () => {   // do not disturb the person: an open dialog, typing, a selection in the list
    const a = document.activeElement;
    if ($("#modal").innerHTML.trim()) return false;
    if (a && (a.tagName === "TEXTAREA" || (a.tagName === "INPUT" && !["checkbox", "radio", "button"].includes(a.type)))) return false;
    if ([...view.querySelectorAll("textarea")].some(x => x.value.trim())) return false;     // a reply that is being written
    if (document.querySelector(".r-one:checked") || ($("#r-q") && $("#r-q").value) || ($("#rt-q") && $("#rt-q").value)) return false;
    return true;
  };
  const tick = async () => {
    if (busy || document.hidden) return; busy = true;
    try {
      const pl = await api("/api/pulse"), t = pl.token;
      if (pl.unread !== undefined && ME.messages_unread !== pl.unread) { ME.messages_unread = pl.unread; badgeMessages(); }
      if (last !== null && t !== last) {
        const name = (location.hash.slice(2) || "dashboard").split("?")[0];
        if (LIVE.includes(name) && idle()) {
          view.style.minHeight = view.offsetHeight + "px";   // keep the scroll position while the page is redrawn
          if (name === "dashboard") dashboard(true).catch(fail); else route();            // the dashboard is patched in place, the other pages are drawn again
          toast("Данные обновлены: получена новая сводка"); setTimeout(() => view.style.minHeight = "", 2500);
          last = t;
        }   // otherwise try again at the next beat: `last` stays old
      } else last = t;
    } catch (e) { /* offline or logged out: the next beat tries again */ }
    busy = false;
  };
  setInterval(tick, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
}
