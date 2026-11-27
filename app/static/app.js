// Single-page interface. Rights are enforced by the server; the interface only hides what a role cannot use.
const $ = (s, r = document) => r.querySelector(s);
const view = $("#view");
let ME = null, META = null, DEB = null;
// the names from the database: a region by its Russian name or an object with name_ru / name_uz, in the language of the interface (the Uzbek one when there is one)
const rname = s => LANG === "uz" && META && (META.regions || []).some(r => r.name_ru === s && r.name_uz) ? META.regions.find(r => r.name_ru === s).name_uz : s;
const nm = o => (LANG === "uz" && o.name_uz) || o.name_ru || o.name || "";
const NAMES = { beds_total: T("Всего коек"), occ_pregnant: T("Госпитализированы: беременные"), occ_children: T("Госпитализированы: дети"), extreme_pregnant: T("Крайне тяжёлые: беременные"), extreme_children: T("Крайне тяжёлые: дети"), visits: T("Обращения"), severe: T("Тяжёлые"), extreme: T("Крайне тяжёлые"), hosp: T("Госпитализации"), disch: T("Выписки"), beds_occupied: T("Занято коек"), occupancy: T("Загрузка, %"), beds_free: T("Свободно коек"), beds_flu: T("Коек для гриппа и ОРВИ") };
// the short name of a question (the head of a column): the one written on the site, else the full name
const indShort = i => LANG === "uz" ? (i.short_uz || i.name_uz || i.short_ru || i.name_ru) : (i.short_ru || i.name_ru);
const labelOf = code => { const i = (META.indicators || []).find(x => x.code === code); return i ? indShort(i) : (NAMES[code] || code); };
const STATE = { sent: T("Отправлен"), corrected: T("Исправлен"), returned: T("Возвращён"), not_sent: T("Не отправлен"), overdue: T("Просрочен"), normal: T("Норма"), elevated: T("Повышенная"), critical: T("Критическая"), none: "—" };

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
  modal(`<h2>${title}</h2>${html}${needReason ? `<label>${T("Причина (попадёт в журнал)")}<textarea id="cf-reason" rows="2"></textarea></label>` : ""}<div id="cf-err" class="err"></div><div class="row mt"><button class="btn bad" id="cf-ok">${okLabel}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#cf-ok").onclick = async () => {
    const reason = needReason ? $("#cf-reason").value.trim() : "";
    if (needReason && !reason) { $("#cf-err").textContent = T("Укажите причину"); return; }
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
function opts(items, val, all) { return (all ? `<option value="">${all}</option>` : "") + items.map(i => `<option value="${i.id}" ${String(i.id) === String(val) ? "selected" : ""}>${esc(nm(i))}</option>`).join(""); }
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
  ${opt.noPeriod ? "" : `<label>${T("Период")}<div class="seg" id="f-pre">${[["day", T("День")], ["week", T("7 дней")], ["month", T("30 дней")], ["custom", T("Свой")]].map(([k, l]) => `<button data-v="${k}" class="${F.preset === k ? "on" : ""}">${l}</button>`).join("")}</div></label>
  <label>${T("С")}<input type="date" id="f-d1" value="${d1}" ${F.preset === "week" || F.preset === "month" ? "disabled" : ""}></label>
  <label ${F.preset === "custom" ? "" : 'hidden'}>${T("По")}<input type="date" id="f-d2" value="${d2}"></label>`}
  <label>${T("Регион")}<select id="f-r">${opts(regs, F.region_id, T("Все регионы"))}</select></label>
  <label>${T("Район")}<select id="f-d" ${F.region_id ? "" : "disabled"}>${opts(dist, F.district_id, T("Все районы"))}</select></label>
  <label>${T("Учреждение")}<select id="f-f" ${F.district_id ? "" : "disabled"}>${opts(fac, F.facility_id, T("Все учреждения"))}</select></label>
  <button class="btn" id="f-reset">${T("Сбросить")}</button></div>`;
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
const KPI = [["reported", T("Сдали отчёт"), "✅", "ok"], ["visits", T("Обращения"), "🚶", "pri"], ["severe", T("Тяжёлые"), "🩺", "warn"], ["extreme", T("Крайне тяжёлые"), "🚨", "bad"],
  ["occ_pc", T("Госпитализированы: беременные / дети"), "🤰", "pur"], ["ext_pc", T("Крайне тяжёлые: беременные / дети"), "👶", "pur"]];
// the exact wording of the questions (Uzbek) behind a card: shown on hover
const KPI_CODES = { visits: ["visits"], severe: ["severe"], extreme: ["extreme"], occ_pc: ["occ_pregnant", "occ_children"], ext_pc: ["extreme_pregnant", "extreme_children"] };
const askedAs = key => (KPI_CODES[key] || []).map(code => { const i = (META.indicators || []).find(x => x.code === code); return i ? `${META.indicators.filter(x => x.active).findIndex(x => x.code === code) + 1}. ${i.name_uz || i.name_ru}` : ""; }).filter(Boolean).join(" · ");
const SORT = { key: "visits", asc: false }, SORT2 = { key: "pct", asc: true }, DRILL = [];
let RT_VIEW = "data";                                       // the card of the regions: the figures of the questionnaire, or the summary of the reporting
const MONTHS = LANG === "uz" ? ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"] : ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const longDate = d => { const [y, m, dd] = d.split("-"); return LANG === "uz" ? `${y}-yil ${+dd}-${MONTHS[+m - 1]}` : `${+dd} ${MONTHS[+m - 1]} ${y}`; };
function kpiValue(key, k) {
  const t = k.totals;
  if (key === "reported") return `<span data-count="${k.reported}">${k.reported}</span><small class="muted"> ${T("из {n}", { n: k.facilities })}</small>`;
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
  OCC_EST = !!t.occ_estimated; NO_OCC = t.occupancy == null && t.beds_occupied == null;                 // no data about the occupied beds: the cards about the occupancy are not drawn
  const occState = t.occupancy == null ? "" : t.occupancy >= th.critical ? "critical" : t.occupancy >= th.elevated ? "warning" : "";
  const isToday = F.preset === "day" && dash.requested === ME.today;
  const canWrite = ME.role !== "viewer";
  const owe = dash.control ? dash.control.not_sent + dash.control.overdue : 0;   // those who still owe today's report (also when nobody has reported yet)
  const rankCard = `<div class="card"><div class="row"><h2>${T("Лидеры по обращениям")}</h2></div><div id="rank" data-keep>…</div></div>`;
  H($("#dash"), silent).innerHTML = `<div class="hero"><div><h1>${F.preset === "day" ? T("Сводка за {date}", { date: longDate(dash.used_date) }) : T("Сводка за период {d1} — {d2}", { d1, d2 })}</h1><div class="sub">${ME.org ? esc(T(ME.org)) + " · " : ""}${T("по {a} из {b} учреждений", { a: k.reported, b: k.facilities })}${dash.fallback ? " · " + T("данных за выбранный день нет, показан последний день с данными") : ""}</div></div>
    <div class="acts"><a class="btn" href="#/export">${T("⬇ Выгрузка")}</a></div></div>
    ${canWrite && isToday && owe > 0 ? `<div class="cta"><span style="font-size:22px">⏰</span><div><b>${T("{n} учреждений ещё не сдали сводку за сегодня", { n: owe })}</b><div class="sub muted">${T("Бот напомнит ответственным одним сообщением с кнопкой отправки")}</div></div><div class="acts"><button class="btn warn" id="remind">${T("🔔 Отправить уведомление не сдавшим")}</button></div></div>` : ""}
    <div class="kpis">${KPI.map(([key, label, ic, tone], i) => `<div class="kpi tilt" data-t="${tone}" style="--i:${i}" title="${esc(askedAs(key))}"><div class="ic">${ic}</div><div class="v">${kpiValue(key, k)}</div><div class="l">${label}</div></div>`).join("")}</div>
    <div class="topgrid">${mapCard()}<div class="sidecol">
      ${NO_OCC ? `<div class="card vcard"><h3>${T("Койки")}</h3><div class="cap" style="margin-top:8px">${T("Выделено коек для гриппа и ОРВИ: <b>{b}</b>", { b: num(t.beds_flu) })}<br>${T("Всего коек в учреждениях: <b>{n}</b>", { n: num(t.beds_total) })}</div></div>`
        : `<div class="card vcard"><h3>${OCC_EST ? T("Загрузка коек (расч.)") : T("Загрузка коек")}</h3>${gaugeChart(t.occupancy, th)}<div class="cap">${T(OCC_EST ? "Расчётно занято <b>{a}</b> из <b>{b}</b> выделенных · свободно <b>{c}</b>" : "Занято <b>{a}</b> из <b>{b}</b> выделенных · свободно <b>{c}</b>", { a: num(t.beds_occupied), b: num(t.beds_flu), c: num(t.beds_free) })}${OCC_EST ? `<div class="muted sm">${T("Считается по числу поступивших с гриппом и ОРВИ за последние {n} дн. (средний срок лечения)", { n: th.stay_days })}</div>` : ""}<br>${T("Всего коек в учреждениях: <b>{n}</b>", { n: num(t.beds_total) })}</div></div>`}
      <div class="card vcard"><h3>${T("Поступили и выписаны")}</h3>${flowCard(t.hosp, t.disch)}</div></div></div>
    <div id="alerts" data-keep></div>
    ${NO_OCC ? rankCard : `<div class="grid2"><div class="card"><h2>${OCC_EST ? T("Нагрузка по регионам (расч.)") : T("Нагрузка по регионам")}</h2><div id="tiles" data-keep>…</div><div class="legend-dots"><span><i style="background:var(--ok)"></i>${T("норма до {n}%", { n: th.elevated })}</span><span><i style="background:var(--warn)"></i>${T("повышенная до {n}%", { n: th.critical })}</span><span><i style="background:var(--bad)"></i>${T("критическая от {n}%", { n: th.critical })}</span></div></div>${rankCard}</div>`}
    <div class="card"><div class="row"><h2>${T("Регионы")}</h2><div class="seg" id="rt-v"><button data-v="data" class="${RT_VIEW === "data" ? "on" : ""}">${T("Показатели")}</button><button data-v="sum" class="${RT_VIEW === "sum" ? "on" : ""}">${T("Сводка")}</button></div><input id="rt-q" placeholder="${T("Поиск")}" class="right"></div><div class="scroll-x" id="rt" data-keep></div></div>
    <div class="grid2"><div class="card"><h3>${T("Динамика")}</h3><div class="lbl">${T("Показатель")}</div><div class="chips" id="dyn-m" data-keep></div><div class="lbl">${T("Сравнить регионы")} <span class="muted">${T("(до 5)")}</span></div><div class="chips" id="dyn-r" data-keep></div><div id="dyn" data-keep></div></div>
    <div class="card"><h3>${T("Госпитализации и выписки")}</h3><div id="hd" data-keep></div></div></div>
    ${NO_OCC ? "" : `<div class="card"><h3>${T("Баланс коек")}</h3><div class="scroll-x" id="beds" data-keep></div></div>`}`;
  if (!silent) countUp($("#dash"));
  tilt($("#dash"));
  const rem = $("#remind"); if (rem) rem.onclick = () => remindDlg(dash.requested);
  api("/api/alerts").then(a => $("#alerts") && ($("#alerts").innerHTML = a.items.slice(0, 6).map(x => `<div class="alert ${x.level}">${esc(TS(x.text))}</div>`).join("") + (a.items.length > 6 ? `<p class="muted sm">${T("Ещё предупреждений: {n} (раздел «Прогноз»)", { n: a.items.length - 6 })}</p>` : ""))).catch(fail);
  const [u1, u2] = dash.fallback ? [dash.used_date, dash.used_date] : [d1, d2];   // tables follow the day the KPI cards show
  $("#rt-v").onclick = e => { const b = e.target.closest("[data-v]"); if (!b || b.dataset.v === RT_VIEW) return; RT_VIEW = b.dataset.v; document.querySelectorAll("#rt-v button").forEach(x => x.classList.toggle("on", x === b)); loadTable(u1, u2); };
  loadTable(u1, u2, silent); loadDyn(silent); loadHD(silent); loadBeds(u1, u2, silent); loadViz(u1, u2, silent);
}
async function loadViz(d1, d2, silent) {
  try {
    const r = await api("/api/regions-table?" + qs({ d1, d2, level: "region" })); const th = ME.thresholds;
    if (!$("#rank")) return;
    if ($("#tiles")) H($("#tiles"), silent).innerHTML = heatTiles(r.rows.slice().sort((a, b) => (b.values.occupancy ?? -1) - (a.values.occupancy ?? -1)), th);
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
  modal(`<h2>${T("🔔 Напомнить не сдавшим")}</h2><p>${T("За <b>{date}</b> не сдали сводку <b>{n}</b> учреждений.", { date: esc(longDate(date)), n: pre.missing })}</p>
    ${people.length ? `<p>${T("Сообщение в Telegram получат <b>{n}</b> ответственных:", { n: people.length })}</p><div class="scroll-x" style="max-height:220px;overflow:auto"><table>${people.map(x => `<tr><td>${esc(x.name)}</td><td class="n">${T("{n} уч.", { n: x.facilities })}</td></tr>`).join("")}</table></div>` : `<div class="note">${T("Некому отправлять: у всех не сдавших нет подключённого ответственного или им уже напоминали в последний час.")}</div>`}
    ${skipped.length ? `<p class="muted sm">${T("Пропущены (напоминали меньше часа назад): {n}", { n: skipped.length })}</p>` : ""}
    ${pre.no_responsible_total ? `<div class="alert">${T("<b>Нет ответственного у {n} учреждений</b> — им уведомление не уйдёт:", { n: pre.no_responsible_total })}<br><span class="sm">${pre.no_responsible.slice(0, 8).map(x => esc(x.replace(/^(.*?) — /, (m, rg) => rname(rg) + " — "))).join("<br>")}${pre.no_responsible_total > 8 ? "<br>…" : ""}</span></div>` : ""}
    <div class="row mt"><button class="btn warn" id="rm-go" ${people.length ? "" : "disabled"}>${T("Отправить {n}", { n: people.length || "" })}</button><button class="btn right" data-close>${T("Закрыть")}</button></div>`);
  const go = $("#rm-go"); if (go) go.onclick = async () => { go.disabled = true; try { const r = await api("/api/notify/remind", { method: "POST", body: { date, region_id: F.region_id || null, dry: false } });
    modal(`<h2>${r.errors ? "⚠️" : "✅"} ${T("Готово")}</h2><p>${T("Отправлено: <b>{n}</b>", { n: r.sent })}${r.errors ? ", " + T("не доставлено: <b>{n}</b> (человек мог заблокировать бота)", { n: r.errors }) : ""}${r.skipped ? ", " + T("пропущено: {n}", { n: r.skipped }) : ""}.</p><button class="btn pri" data-close>${T("Закрыть")}</button>`); } catch (e) { fail(e); go.disabled = false; } };
}
let METRICS = ["visits"], REGSEL = [];
function loadDyn(silent) {
  const mEl = $("#dyn-m"), rEl = $("#dyn-r"); if (!mEl || !rEl) return;
  const short = n => LANG === "uz" ? uzShort(n) : n.replace("Республика ", "").replace(" область", "").replace("город ", "г. ");
  const drawChips = () => {
    mEl.innerHTML = (META.indicators || []).filter(x => x.active).map(x => x.code).map(m => `<button class="chip ${METRICS.includes(m) ? "on" : ""}" data-m="${m}">${esc(labelOf(m))}</button>`).join("");
    rEl.innerHTML = `<button class="chip ${REGSEL.length ? "" : "on"}" data-r="">${T("Вся территория")}</button>` + META.regions.map(r => `<button class="chip ${REGSEL.includes(String(r.id)) ? "on" : ""}" data-r="${r.id}">${esc(short(r.name_ru))}</button>`).join("");
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
      else if (REGSEL.length >= 5) return toast(T("Сравнивать можно до 5 регионов"));
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
      H($("#dyn"), sl).innerHTML = (REGSEL.length >= 2 ? `<p class="muted sm">${T("Сравнение по показателю «{m}»", { m: labelOf(METRICS[0]) })}</p>` : "") +
        lineChart(r.dates, r.series.map(s => { const sn = s.region_id ? rname(s.name) : T(s.name); return { name: REGSEL.length >= 2 ? sn : REGSEL.length === 1 && METRICS.length > 1 ? sn + " — " + labelOf(s.metric) : METRICS.length > 1 ? labelOf(s.metric) : sn, points: s.points }; }));
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
    H($("#hd"), silent).innerHTML = barChart(r.rows.map(x => x.date), [{ name: T("Госпитализации"), values: r.rows.map(x => x.hosp) }, { name: T("Выписки"), values: r.rows.map(x => x.disch) }]) +
      `<div class="scroll-x" style="max-height:200px;overflow:auto"><table><tr><th>${T("Дата")}</th><th class="n">${T("Госп.")}</th><th class="n">${T("Выписки")}</th><th class="n">${T("Разница")}</th><th class="n">${T("Занято")}</th><th class="n">${T("Изм.")}</th></tr>${r.rows.slice().reverse().map(x => `<tr><td>${x.date}</td><td class="n">${num(x.hosp)}</td><td class="n">${num(x.disch)}</td><td class="n">${num(x.diff)}</td><td class="n">${num(x.occupied)}</td><td class="n">${x.occ_change == null ? "—" : (x.occ_change > 0 ? "+" : "") + x.occ_change}</td></tr>`).join("")}</table></div>`;
  } catch (e) { fail(e); }
}
async function loadTable(d1, d2, silent) {
  const level = DRILL.length === 0 ? "region" : "rfac";             // a region opens straight into its facilities
  const pid = DRILL.length ? DRILL[DRILL.length - 1].id : "";
  let r; try { r = await api("/api/regions-table?" + qs({ d1, d2, level, parent_id: pid })); } catch (e) { return fail(e); }
  if (!$("#rt-q")) return;   // the person has already left the dashboard
  const act = (META.indicators || []).filter(x => x.active);           // the columns follow the questionnaire: its questions in their order, with their short names
  const est = r.rows.some(x => x.values.occ_estimated) ? T(" (расч.)") : "";
  const occ = [["beds_occupied", labelOf("beds_occupied") + est], ["beds_free", T("Свободно") + est], ["occupancy", T("Загрузка") + est]];
  const hasOcc = r.rows.some(x => x.values.occupancy != null || x.values.beds_occupied != null);
  const cols = [["name", T("Название")], ["reported", T("Отчёты")]];
  act.forEach(x => { cols.push([x.code, indShort(x)]); if (x.code === "beds_occupied") cols.push(occ[1], occ[2]); });
  if (hasOcc && !act.some(x => x.code === "beds_occupied")) cols.push(...occ);   // the occupied beds are no longer asked, but the days that have them are still shown
  const dn = x => level === "region" ? rname(x.name) : x.name;      // a region is shown in the language of the interface; facilities are named as they are
  const drawSum = sl => {                                                  // the reporting: facilities, sent, not sent, the share with colours
    const q = ($("#rt-q").value || "").toLowerCase();
    const pc = x => x.facilities ? Math.round(1000 * x.reported / x.facilities) / 10 : null;
    const lvl = p => p == null ? "" : p >= 80 ? "normal" : p >= 50 ? "elevated" : "critical";
    const val = (x, k) => k === "name" ? dn(x) : k === "facilities" ? x.facilities : k === "reported" ? x.reported : k === "missing" ? x.facilities - x.reported : pc(x);
    const rows = r.rows.filter(x => dn(x).toLowerCase().includes(q)).sort((a, b) => { const A = val(a, SORT2.key), B = val(b, SORT2.key); const c = typeof A === "string" ? A.localeCompare(B, LANG === "uz" ? "uz" : "ru") : (A ?? -1) - (B ?? -1); return SORT2.asc ? c : -c; });
    const sum = k => rows.reduce((t, x) => t + val(x, k), 0), tf = sum("facilities"), tr = sum("reported"), tp = tf ? Math.round(1000 * tr / tf) / 10 : null;
    const manyDistricts = new Set(r.rows.map(x => x.district)).size > 1;
    const crumbs = `<div class="crumbs"><button class="btn sm${DRILL.length ? "" : " on"}" id="up0">${T("Республика")}</button>${DRILL.map((d, i) => `<span class="sep">›</span><button class="btn sm${i === DRILL.length - 1 ? " on" : ""}" data-up="${i}">${esc(rname(d.name))}</button>`).join("")}</div>`;
    const heads = [["name", T("Название")], ["facilities", T("Учреждений")], ["reported", T("Сдали")], ["missing", T("Не сдали")], ["pct", T("Охват, %")]];
    const bar = p => p == null ? "—" : `<div class="cov"><span class="pill ${lvl(p)}">${num(p)}%</span><div class="cbar"><i class="${lvl(p)}" style="width:${p}%"></i></div></div>`;
    H($("#rt"), sl).innerHTML = crumbs + `<table class="rtab sumtab"><tr>${heads.map(([k, l]) => `<th data-s="${k}" class="${k !== "name" ? "n " : ""}${SORT2.key === k ? "on" + (SORT2.asc ? " asc" : "") : ""}">${esc(l)}</th>`).join("")}</tr>` +
      rows.map(x => { const p = pc(x), miss = x.facilities - x.reported; return `<tr class="${level === "region" ? "link" : ""}" data-id="${x.id}" data-name="${esc(x.name)}"><td>${esc(dn(x))}${level === "rfac" && manyDistricts ? `<div class="muted sm">${esc(x.district || "")}</div>` : ""}</td><td class="n">${num(x.facilities)}</td><td class="n">${num(x.reported)}</td><td class="n ${miss ? "bad-t" : ""}">${num(miss)}</td><td class="cv2">${bar(p)}</td></tr>`; }).join("") +
      `<tr class="total"><td>${T("ИТОГО")}</td><td class="n">${num(tf)}</td><td class="n">${num(tr)}</td><td class="n">${num(tf - tr)}</td><td class="cv2">${bar(tp)}</td></tr></table>`;
    document.querySelectorAll("#rt th[data-s]").forEach(th => th.onclick = () => { SORT2.asc = SORT2.key === th.dataset.s ? !SORT2.asc : th.dataset.s === "name" || th.dataset.s === "pct"; SORT2.key = th.dataset.s; drawSum(); });
    document.querySelectorAll("#rt tr.link").forEach(tr => tr.onclick = () => { DRILL.push({ id: tr.dataset.id, name: tr.dataset.name }); loadTable(d1, d2); });
    $("#up0").onclick = e => { e.preventDefault(); DRILL.length = 0; loadTable(d1, d2); };
    document.querySelectorAll("[data-up]").forEach(a => a.onclick = e => { e.preventDefault(); DRILL.length = +a.dataset.up + 1; loadTable(d1, d2); });
  };
  const draw = sl => {
    if (RT_VIEW === "sum") return drawSum(sl);
    const q = ($("#rt-q").value || "").toLowerCase();
    const val = (x, k) => k === "name" ? dn(x) : k === "reported" ? x.reported : x.values[k];
    const rows = r.rows.filter(x => dn(x).toLowerCase().includes(q)).sort((a, b) => { const A = val(a, SORT.key), B = val(b, SORT.key); const c = typeof A === "string" ? A.localeCompare(B, LANG === "uz" ? "uz" : "ru") : (A ?? -1) - (B ?? -1); return SORT.asc ? c : -c; });
    const manyDistricts = new Set(r.rows.map(x => x.district)).size > 1;
    const crumbs = `<div class="crumbs"><button class="btn sm${DRILL.length ? "" : " on"}" id="up0">${T("Республика")}</button>${DRILL.map((d, i) => `<span class="sep">›</span><button class="btn sm${i === DRILL.length - 1 ? " on" : ""}" data-up="${i}">${esc(rname(d.name))}</button>`).join("")}</div>`;
    H($("#rt"), sl).innerHTML = crumbs + `<table class="rtab"><colgroup>${cols.map(([k]) => `<col class="${k === "name" ? "cn" : "cv"}">`).join("")}</colgroup><tr>${cols.map(([k, l]) => `<th data-s="${k}" class="${k !== "name" ? "n " : ""}${SORT.key === k ? "on" + (SORT.asc ? " asc" : "") : ""}" title="${esc(l)}">${k === "name" ? l : `<span class="vt">${esc(l)}</span>`}</th>`).join("")}</tr>${rows.map(x => `<tr class="${level === "region" ? "link" : ""}" data-id="${x.id}" data-name="${esc(x.name)}"><td>${esc(dn(x))}${level === "rfac" && manyDistricts ? `<div class="muted sm">${esc(x.district || "")}</div>` : ""}</td><td class="n">${x.reported}/${x.facilities}</td>${cols.slice(2).map(([k]) => k === "occupancy" ? `<td class="n">${x.values.occupancy == null ? "—" : `<span class="pill ${x.level_state === "none" ? "" : x.level_state}">${num(x.values.occupancy)}%</span>`}</td>` : `<td class="n">${num(x.values[k])}</td>`).join("")}</tr>`).join("")}</table>`;
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
    H($("#beds"), silent).innerHTML = `${r.estimated ? `<p class="muted sm">${T("Загрузка расчётная: по числу поступивших с гриппом и ОРВИ за последние {n} дн. (средний срок лечения). Предупреждения по ней не рассылаются.", { n: r.stay_days })}</p>` : ""}<p class="muted sm">${T("Пороги: повышенная нагрузка ≥ {a}%, критическая ≥ {b}%, учреждение ≥ {c}%.", { a: th.elevated, b: th.critical, c: th.facility })}</p><table><tr><th>${T("Регион")}</th><th class="n">${T("Коек для гриппа и ОРВИ")}</th><th class="n">${T("Занято")}</th><th class="n">${T("Свободно")}</th><th class="n">${T("Загрузка")}</th><th>${T("Состояние")}</th></tr>${r.rows.map(x => `<tr><td>${esc(rname(x.name))}</td><td class="n">${num(x.beds_flu)}</td><td class="n">${num(x.occupied)}</td><td class="n">${num(x.free)}</td><td class="n">${x.occupancy == null ? "—" : num(x.occupancy) + "%"}</td><td>${pill(x.state)}</td></tr>`).join("")}</table>` +
      (r.hot.length ? `<h3 class="mt">${T("Учреждения с высокой загрузкой")}</h3><table><tr><th>${T("Учреждение")}</th><th>${T("Регион")}</th><th class="n">${T("Загрузка")}</th><th class="n">${T("Свободно")}</th></tr>${r.hot.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(rname(x.region))}${x.district === "Без района" ? "" : ", " + esc(x.district)}</td><td class="n"><span class="pill critical">${num(x.occupancy)}%</span></td><td class="n">${num(x.free)}</td></tr>`).join("")}</table>` : "");
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
      h += `<h3>${esc(labelOf(code))}</h3>`;
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
const tgName = u => [u.first_name, u.last_name].filter(Boolean).join(" ") || (u.username ? "@" + u.username : T("Без имени"));
const tgAv = u => `<span class="tgav">${esc((tgName(u).replace(/^@/, "")[0] || "?").toUpperCase())}<img src="/api/tg-avatar/${esc(u.tg_id)}" alt="" loading="lazy"></span>`;
const tgWho = u => `<div class="tgwho">${tgAv(u)}<div><b>${esc(tgName(u))}</b>${u.active === 0 ? ` <span class="pill critical">${T("отключён")}</span>` : ""}<div class="muted sm">${u.username ? "@" + esc(u.username) + " · " : ""}ID ${esc(u.tg_id)}</div></div></div>`;
const tgLink = u => u.username ? `<a class="btn sm" href="https://t.me/${esc(u.username)}" target="_blank" rel="noopener noreferrer">✈ ${T("Профиль в Telegram")}</a>`
  : `<a class="btn sm" href="tg://user?id=${esc(u.tg_id)}" title="${T("У человека нет @username: профиль откроется, только если он уже есть в ваших чатах Telegram")}">✈ ${T("Профиль в Telegram")}</a>`;
const dropBrokenAvatars = root => root.querySelectorAll(".tgav img").forEach(im => { const rm = () => im.remove(); im.addEventListener("error", rm, { once: true }); if (im.complete && im.naturalWidth === 0) rm(); });
const PROP = { all: false, per: {} };      // the proposals of the bot on the page «Территории»: only the new ones or all
const OPENRG = new Set();           // regions whose group of people is open (kept while the page is reloaded after an action)
async function people() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><div class="row"><h2>${T("Заявки на доступ")}</h2></div><div id="rq" class="scroll-x"></div></div><div class="card"><div class="row"><h2>${T("Записаны заранее")}</h2><span class="muted sm">${T("доступ откроется сам, когда человек впервые напишет боту")}</span></div><div id="pre" class="scroll-x"></div></div><div class="card"><div class="row"><h2>${T("Ответственные (Telegram)")}</h2><button class="btn pri right" id="tg-add">${T("+ Добавить")}</button></div><div id="tgl" class="scroll-x"></div></div><div id="staffbox"></div>`;
  const loadReq = async () => { try { const r = await api("/api/requests?status=pending");
    $("#rq").innerHTML = r.items.length ? `<table><tr><th>${T("Дата")}</th><th>${T("Кто просит")}</th><th>${T("Куда")}</th><th></th></tr>${r.items.map(x => `<tr><td>${esc(x.created_at)}</td><td>${tgWho(x)}<div class="mt">${tgLink(x)}</div></td><td><b>${esc(rname(x.region))}</b>${x.district ? " — " + esc(x.district) : ""}${x.facility ? " — " + esc(x.facility) : ` <span class="pill">${T("весь регион")}</span>`}</td><td class="row"><button class="btn sm pri" data-ap="${x.id}">${T("Одобрить")}</button><button class="btn sm bad" data-no="${x.id}">${T("Отклонить")}</button></td></tr>`).join("")}</table>` : `<p class="muted">${T("Новых заявок нет.")}</p>`;
    dropBrokenAvatars($("#rq"));
    document.querySelectorAll("[data-ap]").forEach(b => b.onclick = () => decide(+b.dataset.ap, true)); document.querySelectorAll("[data-no]").forEach(b => b.onclick = () => decide(+b.dataset.no, false)); } catch (e) { fail(e); } };
  const decide = async (id, approve) => { const note = approve ? "" : prompt(T("Причина отказа (увидит заявитель):")) ?? null; if (note === null) return; try { await api(`/api/requests/${id}/decide`, { method: "POST", body: { approve, note } }); loadReq(); loadTg(); } catch (e) { fail(e); } };
  const loadPre = async () => { try { const r = await api("/api/preapproved");
    $("#pre").innerHTML = r.items.length ? `<table><tr><th>Telegram</th><th>${T("Куда")}</th><th>${T("Тип")}</th><th>${T("Записан")}</th><th></th></tr>${r.items.map(x => `<tr><td><b>@${esc(x.username)}</b> <a class="btn sm" href="https://t.me/${esc(x.username)}" target="_blank" rel="noopener noreferrer">✈ ${T("Профиль")}</a></td><td><b>${esc(rname(x.region))}</b>${x.facility ? " — " + esc(x.facility) : ` <span class="pill">${T("весь регион")}</span>`}${x.fio ? `<div class="muted sm">${esc(x.fio)}</div>` : ""}</td><td>${x.kind === "reserve" ? T("резерв") : T("основной")}</td><td>${esc(x.created_at)}</td><td><button class="btn sm bad" data-pd="${x.id}">${T("Убрать")}</button></td></tr>`).join("")}</table>${r.bot ? `<p class="muted sm">${T("Попросите этих людей открыть бота: {link} и нажать «Start».", { link: `<a href="https://t.me/${esc(r.bot)}" target="_blank" rel="noopener noreferrer">t.me/${esc(r.bot)}</a>` })}</p>` : ""}` : `<p class="muted">${T("Никого. Нажмите «+ Добавить» и укажите @username.")}</p>`;
    document.querySelectorAll("[data-pd]").forEach(b => b.onclick = async () => { if (!confirm(T("Убрать запись? Человек не получит доступ автоматически."))) return; try { await api("/api/preapproved/" + b.dataset.pd, { method: "DELETE" }); loadPre(); } catch (x) { fail(x); } }); } catch (e) { fail(e); } };
  const loadTg = async () => { try { const r = await api("/api/tg-users");
    // grouped by region: a person is listed in every region where they have access (the whole region or single facilities); people with no access are last
    const groups = new Map(META.regions.map(rg => [rg.id, { name: nm(rg), people: new Map() }])), none = [];
    const put = (rid, u) => { const g = groups.get(rid); if (!g) return null; if (!g.people.has(u.tg_id)) g.people.set(u.tg_id, { u, regs: [], facs: [] }); return g.people.get(u.tg_id); };
    r.items.forEach(u => { u.regions.forEach(a => { const e = put(a.region_id, u); if (e) e.regs.push(a); }); u.assignments.forEach(a => { const e = put(a.region_id, u); if (e) e.facs.push(a); }); if (!u.regions.length && !u.assignments.length) none.push(u); });
    const active = [...groups.entries()].filter(([, g]) => g.people.size);
    const acts = u => `${tgLink(u)}<button class="btn sm" data-as="${u.tg_id}">${T("Назначить")}</button><button class="btn sm" data-tog="${u.tg_id}" data-a="${u.active}">${u.active ? T("Отключить") : T("Включить")}</button>`;
    const access = e => e.regs.map(a => `<b>${T("весь регион")}</b>${a.kind === "reserve" ? " " + T("(резерв)") : ""} <a href="#" data-unr="${a.id}">✕</a>`).concat(e.facs.map(a => `${esc(a.facility)} (${a.kind === "reserve" ? T("резерв") : T("основной")}) <a href="#" data-un="${a.id}">✕</a>`)).join("<br>");
    const people_n = new Set(active.flatMap(([, g]) => [...g.people.keys()])).size;
    $("#tgl").innerHTML = `<div class="rgsum">${T("{p} чел. с доступом в {r} регионах · без доступа: {n}", { p: `<b>${people_n}</b>`, r: `<b>${active.length}</b>`, n: `<b>${none.length}</b>` })}</div>
      <div class="chips rgchips">${[...groups.entries()].map(([id, g]) => `<button class="chip${g.people.size ? "" : " dim"}" data-go="${id}" ${g.people.size ? "" : "disabled"}>${esc(LANG === "uz" ? g.name : g.name.replace("Республика ", "").replace(" область", "").replace("город ", "г. "))} <b>${g.people.size}</b></button>`).join("")}${none.length ? `<button class="chip dim" data-go="none">${T("Без доступа")} <b>${none.length}</b></button>` : ""}</div>
      <div class="inl" style="margin:8px 0"><input id="tg-q" placeholder="${T("Найти человека")}" style="max-width:260px"><button class="btn sm" id="rg-open">${T("Развернуть все")}</button><button class="btn sm" id="rg-close">${T("Свернуть все")}</button></div>
      ${active.map(([id, g]) => `<details class="rgrp" data-rg="${id}" ${OPENRG.has(String(id)) ? "open" : ""}><summary><b>${esc(g.name)}</b><span class="pill">${T("{n} чел.", { n: g.people.size })}</span></summary>
        <div class="scroll-x"><table><tr><th>${T("Пользователь")}</th><th>${T("Доступ в этом регионе")}</th><th></th></tr>${[...g.people.values()].map(e => `<tr data-find="${esc((tgName(e.u) + " " + (e.u.username || "") + " " + e.u.tg_id).toLowerCase())}"><td>${tgWho(e.u)}</td><td>${access(e)}</td><td class="row">${acts(e.u)}</td></tr>`).join("")}</table></div></details>`).join("")}
      ${none.length ? `<details class="rgrp" data-rg="none" ${OPENRG.has("none") ? "open" : ""}><summary><b>${T("Без доступа")}</b><span class="pill">${T("{n} чел.", { n: none.length })}</span></summary><div class="scroll-x"><table><tr><th>${T("Пользователь")}</th><th></th></tr>${none.map(u => `<tr data-find="${esc((tgName(u) + " " + (u.username || "") + " " + u.tg_id).toLowerCase())}"><td>${tgWho(u)}</td><td class="row">${acts(u)}</td></tr>`).join("")}</table></div></details>` : ""}
      ${active.length || none.length ? "" : `<p class="muted">${T("Пока никого.")}</p>`}`;
    document.querySelectorAll("#tgl details.rgrp").forEach(d => d.addEventListener("toggle", () => { d.open ? OPENRG.add(d.dataset.rg) : OPENRG.delete(d.dataset.rg); }));
    document.querySelectorAll("#tgl [data-go]").forEach(b => b.onclick = () => { const d = document.querySelector(`#tgl details[data-rg="${b.dataset.go}"]`); if (d) { d.open = true; d.scrollIntoView({ behavior: "smooth", block: "start" }); } });
    $("#rg-open").onclick = () => document.querySelectorAll("#tgl details.rgrp").forEach(d => d.open = true); $("#rg-close").onclick = () => document.querySelectorAll("#tgl details.rgrp").forEach(d => d.open = false);
    $("#tg-q").oninput = e => { const q = e.target.value.trim().toLowerCase(); document.querySelectorAll("#tgl tr[data-find]").forEach(tr => tr.hidden = !!q && !tr.dataset.find.includes(q)); if (q) document.querySelectorAll("#tgl details.rgrp").forEach(d => { d.open = [...d.querySelectorAll("tr[data-find]")].some(tr => !tr.hidden); }); };
    dropBrokenAvatars($("#tgl"));
    document.querySelectorAll("[data-un]").forEach(a => a.onclick = async e => { e.preventDefault(); if (!confirm(T("Снять назначение?"))) return; try { await api("/api/assignments/" + a.dataset.un, { method: "DELETE" }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-unr]").forEach(a => a.onclick = async e => { e.preventDefault(); if (!confirm(T("Снять доступ к региону?"))) return; try { await api("/api/region-access/" + a.dataset.unr, { method: "DELETE" }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-tog]").forEach(b => b.onclick = async () => { try { await api("/api/tg-users/" + b.dataset.tog, { method: "PATCH", body: { active: b.dataset.a !== "1" } }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-as]").forEach(b => b.onclick = () => assignDlg(b.dataset.as, () => { loadTg(); loadPre(); })); } catch (e) { fail(e); } };
  $("#tg-add").onclick = () => assignDlg("", () => { loadTg(); loadPre(); });
  loadReq(); loadPre(); loadTg();
  if (ME.role === "super_admin") staffBox();
}

async function assignDlg(tg, done) {
  modal(`<h2>${tg ? T("Назначить ответственного") : T("Добавить ответственного")}</h2>${tg ? "" : `<label>${T("@username или Telegram ID")}<input id="a-id" placeholder="${T("@username  или  123456789")}" autocomplete="off"></label><p class="muted sm" style="margin:-4px 0 10px">${T("С @username человеку не нужно отправлять запрос: доступ откроется, как только он впервые напишет боту. Числовой ID нужен, если у человека нет @username.")}</p><label>${T("Имя (необязательно)")}<input id="a-n"></label>`}
  <label>${T("Регион")}<select id="a-r">${opts(META.regions.map(r => ({ ...r, name_ru: nm(r) })), "", "—")}</select></label><label>${T("Район (необязательно)")}<select id="a-d" disabled></select></label><label>${T("Учреждение (необязательно; если пусто — доступ ко всему региону)")}<select id="a-f" disabled></select></label>
  <label>${T("Тип")}<select id="a-k"><option value="primary">${T("Основной")}</option><option value="reserve">${T("Резервный")}</option></select></label><label>${T("ФИО (для отчётов)")}<input id="a-fio"></label>
  <div class="row mt"><button class="btn pri" id="a-ok">${T("Сохранить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#a-r").onchange = async e => { const d = await api("/api/districts?region_id=" + e.target.value); $("#a-d").innerHTML = opts(d.items.map(r => ({ ...r, name_ru: nm(r) })), "", "—"); $("#a-d").disabled = false; $("#a-f").disabled = true; };
  $("#a-d").onchange = async e => { const f = await api("/api/facilities?" + qs({ district_id: e.target.value, size: 200 })); $("#a-f").innerHTML = opts(f.items.map(r => ({ ...r, name_ru: nm(r) })), "", "—"); $("#a-f").disabled = false; };
  $("#a-ok").onclick = async () => { if (!+$("#a-r").value) return toast(T("Выберите регион"));
    const id = tg || $("#a-id").value.trim(), numeric = /^\d+$/.test(id), common = { facility_id: +$("#a-f").value || 0, region_id: +$("#a-r").value || 0, kind: $("#a-k").value, fio: $("#a-fio").value || (tg ? "" : $("#a-n").value) };
    if (!id) return toast(T("Укажите @username или Telegram ID"));
    try {
      if (tg) await api("/api/assignments", { method: "POST", body: { tg_id: tg, ...common } });
      else if (numeric) await api("/api/tg-users", { method: "POST", body: { tg_id: id, name: $("#a-n").value, ...common } });
      else { const r = await api("/api/preapproved", { method: "POST", body: { username: id, ...common } }); toast(r.claimed ? T("Человек уже есть в боте: доступ открыт сразу") : T("Записан: доступ откроется при первом сообщении боту")); closeModal(); return done(); }
      closeModal(); toast(T("Сохранено")); done(); } catch (e) { fail(e); } };
}
async function staffBox() {
  const [st] = await Promise.all([api("/api/staff")]);
  if (!$("#staffbox")) return;                                  // the person has left the page while the list was coming
  $("#staffbox").innerHTML = `<div class="card"><div class="row"><h2>${T("Пользователи панели")}</h2><button class="btn pri right" id="st-add">${T("+ Добавить")}</button></div><div class="scroll-x"><table><tr><th>${T("Логин")}</th><th>${T("Имя")}</th><th>${T("Роль")}</th><th>${T("Регионы")}</th><th></th></tr>${st.items.map(s => `<tr><td>${esc(s.login)}${s.active ? "" : ` <span class="pill critical">${T("отключён")}</span>`}</td><td>${esc(roleLabel(s.name))}</td><td>${esc({ super_admin: T("Главный администратор"), admin: T("Администратор"), viewer: T("Просмотр") }[s.role])}</td><td>${s.role === "super_admin" || !s.regions.length ? T("все") : s.regions.map(id => esc(rname(META.regions.find(r => r.id === id)?.name_ru || id))).join(", ")}</td><td class="row"><button class="btn sm" data-ed="${s.id}">${T("Изменить")}</button><button class="btn sm" data-pw="${s.id}">${T("Сбросить пароль")}</button></td></tr>`).join("")}</table></div></div>`;
  const form = s => modal(`<h2>${s ? T("Изменить") : T("Новый пользователь")}</h2>${s ? "" : `<label>${T("Логин")}<input id="s-l"></label>`}<label>${T("Имя")}<input id="s-n" value="${esc(s?.name || "")}"></label>
    <label>${T("Роль")}<select id="s-r">${[["viewer", T("Просмотр")], ["admin", T("Администратор")], ["super_admin", T("Главный администратор")]].map(([k, l]) => `<option value="${k}" ${s?.role === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    <label>${T("Регионы (пусто = все; для администратора регионального уровня выберите свои)")}<select id="s-reg" multiple size="6">${META.regions.map(r => `<option value="${r.id}" ${s?.regions.includes(r.id) ? "selected" : ""}>${esc(nm(r))}</option>`).join("")}</select></label>
    <label>${T("Telegram ID (для сводок)")}<input id="s-tg" value="${esc(s?.tg_id || "")}"></label>
    <label><input type="checkbox" id="s-mu" ${s?.can_manage_users ? "checked" : ""} style="width:auto"> ${T("Может управлять доступами")}</label><label><input type="checkbox" id="s-mt" ${s?.can_manage_territories ? "checked" : ""} style="width:auto"> ${T("Раздел «Территории»: добавлять и удалять районы и учреждения в своих регионах (для администратора)")}</label><label><input type="checkbox" id="s-er" ${s ? (s.can_edit_reports ? "checked" : "") : "checked"} style="width:auto"> ${T("Может исправлять отчёты")}</label>
    ${s ? `<label><input type="checkbox" id="s-ac" ${s.active ? "checked" : ""} style="width:auto"> ${T("Активен")}</label>` : ""}
    <div class="row mt"><button class="btn pri" id="s-ok">${T("Сохранить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  const body = s => ({ name: $("#s-n").value, role: $("#s-r").value, regions: [...$("#s-reg").selectedOptions].map(o => +o.value), tg_id: $("#s-tg").value, can_manage_users: $("#s-mu").checked, can_manage_territories: $("#s-mt").checked, can_edit_reports: $("#s-er").checked, ...(s ? { active: $("#s-ac").checked } : { login: $("#s-l").value }) });
  $("#st-add").onclick = () => { form(null); $("#s-ok").onclick = async () => { try { const r = await api("/api/staff", { method: "POST", body: body(null) }); modal(`<h2>${T("Пользователь создан")}</h2><p>${T("Пароль (показывается один раз):")}</p><p><b id="pwv">${esc(r.password || T("задан вручную"))}</b></p><button class="btn pri" id="pw-ok">${T("Готово")}</button>`); $("#pw-ok").onclick = () => { closeModal(); people(); }; } catch (e) { fail(e); } }; };
  document.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => { const s = st.items.find(x => x.id === +b.dataset.ed); form(s); $("#s-ok").onclick = async () => { try { await api("/api/staff/" + s.id, { method: "PATCH", body: body(s) }); closeModal(); people(); } catch (e) { fail(e); } }; });
  document.querySelectorAll("[data-pw]").forEach(b => b.onclick = async () => { if (!confirm(T("Сгенерировать новый пароль?"))) return; try { const r = await api(`/api/staff/${b.dataset.pw}/password`, { method: "POST", body: {} }); modal(`<h2>${T("Новый пароль")}</h2><p><b id="pwv">${esc(r.password)}</b></p><button class="btn pri" data-close>${T("Готово")}</button>`); } catch (e) { fail(e); } });
}

// ---------- territories
const TERR = { cur: null, q: "", did: "" };      // the region opened on «Территории» (kept while the page is redrawn), the search and the district filter
// phones: digits «998901234567» (the server keeps them so); a person writes them any way
function phonesOf(raw) {
  const out = [];
  for (const part of String(raw || "").split(/[\n;,/]+|\s{3,}/)) {
    const d = part.replace(/\D/g, ""); if (!d) continue;
    let chunks = [d];
    if (d.startsWith("998") && d.length > 12 && d.length % 12 === 0) chunks = d.match(/.{12}/g);
    else if (!d.startsWith("998") && d.length > 9 && d.length % 9 === 0) chunks = d.match(/.{9}/g);
    for (const x of chunks) out.push(x.length === 9 ? "998" + x : x);
  }
  return [...new Set(out)];
}
const fmtPhone = p => /^998\d{9}$/.test(p) ? `+998 ${p.slice(3, 5)} ${p.slice(5, 8)} ${p.slice(8, 10)} ${p.slice(10)}` : p;
const showPhones = s => (Array.isArray(s) ? s : String(s || "").split(",")).filter(Boolean).map(fmtPhone).join(", ");
const mainOf = x => (x.contacts || []).find(c => c.kind === "main") || { fio: "", phone: "" };
const reserveOf = x => (x.contacts || []).find(c => c.kind === "reserve") || { fio: "", phone: "" };
async function territories() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const SUP = ME.role === "super_admin";
  if (nav !== NAVID) return;
  view.innerHTML = `<div class="terr"><aside class="card terr-side"><div class="row"><h3 style="margin:0">${T("Регионы")}</h3>${SUP ? `<button class="btn sm right" id="t-add">${T("+ Регион")}</button>` : ""}</div><div id="tt"></div>
      ${SUP ? `<details class="mt"><summary class="muted sm">${T("Другие загрузки из Excel")}</summary><div class="stack mt"><button class="btn sm" id="t-rep">${T("Учреждения и показатели за 2 дня")}</button><button class="btn sm" id="t-imp">${T("Импорт территорий")}</button></div></details>` : ""}</aside>
      <section class="card terr-main" id="tsub"><p class="muted">${T("Выберите регион слева")}</p></section></div>`;
  let cur = TERR.cur;
  const sideRefresh = async () => {
    let sm, pr; try { [sm, pr] = await Promise.all([api("/api/territory-summary"), api("/api/facility-proposals?status=new&count_only=1")]); sm = sm.items; } catch (e) { return fail(e); }
    PROP.per = pr.per_region; ME.proposals_new = pr.new; badgeProposals();
    if (!$("#tt")) return;
    $("#tt").innerHTML = `<div class="rgl">${META.regions.map(r => { const t = sm[r.id] || { total: 0, with_contact: 0 }, pc = t.total ? Math.round(100 * t.with_contact / t.total) : 0;
      return `<button class="rgb${cur === r.id ? " on" : ""}${r.active ? "" : " off"}" data-id="${r.id}" title="${esc(T("Учреждений: {n}, с ответственным: {k}", { n: t.total, k: t.with_contact }))}"><span class="rgb-n">${esc(rname(r.name_ru))}${PROP.per[r.id] ? ` <span class="pill warning" title="${esc(T("Новых предложений: {n}", { n: PROP.per[r.id] }))}">${PROP.per[r.id]}</span>` : ""}</span><span class="rgb-s">${t.with_contact}/${t.total}</span><i class="rgb-bar"><b style="width:${pc}%"></b></i></button>`; }).join("")}</div>`;
    document.querySelectorAll("#tt .rgb").forEach(b => b.onclick = () => { cur = TERR.cur = +b.dataset.id; TERR.q = ""; TERR.did = ""; sideRefresh(); regionView(cur); });
  };
  const load = async () => {
    META = await api("/api/meta"); await sideRefresh();
    if (!cur || !META.regions.some(r => r.id === cur)) {          // nothing opened yet: the region that has new proposals, else the first one
      const best = Object.entries(PROP.per || {}).sort((a, b) => b[1] - a[1])[0];
      cur = TERR.cur = best ? +best[0] : (META.regions[0] || {}).id || null; TERR.q = ""; TERR.did = "";
      if (cur) await sideRefresh();
    }
    if (cur) regionView(cur);
  };
  // the region opened: its districts and all its facilities in one table, every cell is edited in place and saved when the person leaves it
  const regionView = async rid => {
    const [d, f, rcs] = await Promise.all([api("/api/districts?region_id=" + rid), api("/api/facilities?" + qs({ region_id: rid, district_id: TERR.did, q: TERR.q, size: 200 })), api("/api/region-contacts")]);
    if (!$("#tsub") || cur !== rid) return;
    const reg = META.regions.find(r => r.id === rid) || {};
    const row = (x, i) => { const m = mainOf(x);
      return `<tr data-id="${x.id}" class="${x.active ? "" : "off"}"><td class="n muted">${i + 1}</td>
        <td><input class="ci" data-k="name" value="${esc(x.name_ru)}" title="${esc(nm(x))}"></td>
        <td><select class="ci" data-k="district">${d.items.map(y => `<option value="${y.id}" ${y.id === x.district_id ? "selected" : ""}>${esc(nm(y))}</option>`).join("")}</select></td>
        <td><input class="ci" data-k="fio" value="${esc(m.fio)}" placeholder="${T("Ф.И.Ш.")}"></td>
        <td><input class="ci" data-k="phone" value="${esc(showPhones(m.phone))}" placeholder="+998 __ ___ __ __" inputmode="tel"></td>
        <td><input class="ci num" data-k="beds" value="${x.beds ?? ""}" inputmode="numeric"></td>
        <td class="c"><input type="checkbox" data-k="active" ${x.active ? "checked" : ""} title="${T("Активно (отключённое не входит в отчёты)")}"></td>
        <td class="n">${x.reports}</td>
        <td class="act"><span class="sv"></span>${x.assignments.length ? `<span class="botdot" title="${esc(T("Подключён в боте: {n}", { n: x.assignments.length }))}">🤖</span>` : ""}<button class="btn sm" data-more="${x.id}" title="${T("Изменить")}">⋯</button><button class="btn sm bad" data-df="${x.id}" title="${T("Удалить")}">✕</button></td></tr>`; };
    const withC = f.items.filter(x => mainOf(x).fio || mainOf(x).phone).length, withP = f.items.filter(x => mainOf(x).phone).length;
    const rc = (rcs.items[rid] || []), head = rc.find(x => x.kind === "main"), rsv = rc.find(x => x.kind === "reserve");
    const person = x => `<b>${esc(x.fio) || "—"}</b>${x.phone ? " · " + esc(showPhones(x.phone)) : ""}${x.linked ? ` <span title="${esc(T("Подключён в боте"))}">🤖</span>` : ""}`;
    $("#tsub").innerHTML = `<div class="row"><h2 style="margin:0">${esc(rname(reg.name_ru || ""))}</h2>${SUP ? `<button class="btn sm" id="r-ed">${T("Изменить")}</button><button class="btn sm bad" id="r-del">${T("Удалить регион")}</button>` : ""}
        <button class="btn pri right" id="f-add">${T("+ Учреждение")}</button></div>
      <div class="rhead"><span class="muted">${T("Руководитель отдела здравоохранения")}:</span> ${head ? person(head) : `<span class="muted">${T("не указан")}</span>`}${rsv ? ` <span class="muted">· ${T("резерв")}:</span> ${person(rsv)}` : ""} <button class="btn sm" id="rc-ed">${T("Изменить")}</button></div>
      <div id="tprop" class="props"></div>
      <div class="row mt"><select id="f-d"><option value="">${T("Все районы")}</option>${d.items.map(x => `<option value="${x.id}" ${String(x.id) === String(TERR.did) ? "selected" : ""}>${esc(nm(x))}</option>`).join("")}</select><input id="f-q" type="search" placeholder="${T("Поиск")}" value="${esc(TERR.q)}">
        <span class="muted sm">${T("Учреждений: {n} · с ответственным: {k} · с телефоном: {p}", { n: f.total, k: withC, p: withP })}</span></div>
      <p class="muted sm" style="margin:6px 0">${T("Любую ячейку можно править прямо в таблице: изменение сохраняется, когда вы выходите из ячейки. «⋯» открывает все поля учреждения.")}</p>
      <div class="scroll-x"><table class="ftab"><colgroup><col class="c-i"><col class="c-n"><col class="c-d"><col class="c-f"><col class="c-p"><col class="c-b"><col class="c-a"><col class="c-r"><col class="c-x"></colgroup>
        <tr><th>#</th><th>${T("Учреждение")}</th><th>${T("Район")}</th><th>${T("Ответственный (Ф.И.Ш.)")}</th><th>${T("Телефон")}</th><th>${T("Койки")}</th><th>${T("Активно")}</th><th class="n">${T("Отчётов")}</th><th></th></tr>
        ${f.items.map(row).join("") || `<tr><td colspan="9" class="muted">${T("Учреждений нет")}</td></tr>`}</table></div>
      ${f.total > f.items.length ? `<p class="muted sm">${T("Показаны первые {n} из {total}: уточните поиском или районом.", { n: f.items.length, total: f.total })}</p>` : ""}
      <details class="mt"${d.items.length ? "" : " open"}><summary><b>${T("Районы")}</b> <span class="muted sm">(${d.items.length})</span></summary>
        <table class="mt"><tr><th>${T("Район")}</th><th></th></tr>${d.items.map(x => `<tr><td>${esc(nm(x))}${x.active ? "" : " " + T("(отключён)")}</td><td><button class="btn sm" data-ed="${x.id}">${T("Изменить")}</button> <button class="btn sm bad" data-dd="${x.id}">${T("Удалить")}</button></td></tr>`).join("") || `<tr><td colspan="2" class="muted">${T("Районов нет")}</td></tr>`}</table>
        <button class="btn sm mt" id="d-add">${T("+ Район")}</button></details>`;
    const again = () => { sideRefresh(); return regionView(rid); };
    $("#rc-ed").onclick = () => regionContactDlg(rid, rc, again);
    loadProps(rid);
    $("#d-add").onclick = () => nameDlg("districts", { region_id: rid }, again, true);
    document.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => nameDlg("districts", d.items.find(x => x.id === +b.dataset.ed), again));
    document.querySelectorAll("[data-dd]").forEach(b => b.onclick = () => { const x = d.items.find(y => y.id === +b.dataset.dd); confirmDlg(T("Удалить район"), `<p>${T("Район {name} будет удалён. Если в нём есть учреждения, система откажет: сначала удалите их.", { name: `<b>${esc(nm(x))}</b>` })}</p>`, T("Удалить район"), async () => { await api("/api/districts/" + x.id, { method: "DELETE" }); closeModal(); toast(T("Район удалён")); again(); }); });
    if (SUP) {
      $("#r-ed").onclick = () => nameDlg("regions", reg, load);
      $("#r-del").onclick = () => confirmDlg(T("Удалить регион"), `<p>${T("Регион {name} будет удалён вместе с пустыми районами. Если в нём есть учреждения или доступы, система откажет: сначала удалите их.", { name: `<b>${esc(nm(reg))}</b>` })}</p>`, T("Удалить регион"), async () => { await api("/api/regions/" + reg.id, { method: "DELETE" }); closeModal(); cur = TERR.cur = null; toast(T("Регион удалён")); $("#tsub").innerHTML = ""; load(); });
    }
    $("#f-d").onchange = () => { TERR.did = $("#f-d").value; regionView(rid); };
    $("#f-q").oninput = () => { clearTimeout(DEB); DEB = setTimeout(async () => { TERR.q = $("#f-q").value; const pos = TERR.q.length; await regionView(rid); const el = $("#f-q"); if (el) { el.focus(); el.setSelectionRange(pos, pos); } }, 300); };
    $("#f-add").onclick = () => facDlg(null, d.items.filter(x => x.active), TERR.did, again);
    document.querySelectorAll("[data-more]").forEach(b => b.onclick = () => facDlg(f.items.find(x => x.id === +b.dataset.more), d.items, "", again));
    document.querySelectorAll("[data-df]").forEach(b => b.onclick = () => { const x = f.items.find(y => y.id === +b.dataset.df);
      confirmDlg(T("Удалить учреждение"), `<p>${T("Учреждение {name} ({district}) будет удалено.", { name: `<b>${esc(nm(x))}</b>`, district: esc(x.district) })}</p><ul class="sm"><li>${T("Отчётов, которые удалятся вместе с ним: {n}", { n: `<b>${x.reports}</b>` })}</li><li>${T("Ответственных, у которых пропадёт привязка: {n} (в боте они останутся)", { n: `<b>${x.assignments.length}</b>` })}</li></ul><p class="muted sm">${T("Если нужно только скрыть учреждение из отчётности, снимите галочку «Активно»: данные сохранятся.")}</p>`, T("Удалить безвозвратно"), async () => { await api("/api/facilities/" + x.id + "?force=1", { method: "DELETE" }); closeModal(); toast(T("Учреждение удалено")); again(); }); });
    // the cells: saved when the person leaves a cell (change), Enter leaves it
    const tb = $("#tsub .ftab");
    tb.onkeydown = e => { if (e.key === "Enter" && e.target.matches("input.ci")) { e.preventDefault(); e.target.blur(); } };
    tb.onchange = e => {
      const tr = e.target.closest("tr[data-id]"); if (!tr || !e.target.dataset.k) return;
      const field = e.target.dataset.k;
      // one row is saved one change after another, and every save sends what the cells hold at that moment
      tr._q = (tr._q || Promise.resolve()).then(async () => {
        const x = f.items.find(y => y.id === +tr.dataset.id), g = k => tr.querySelector(`[data-k="${k}"]`), sv = tr.querySelector(".sv");
        const body = { name_ru: g("name").value.trim(), district_id: +g("district").value, active: g("active").checked, beds: g("beds").value.trim(), contacts: [{ kind: "main", fio: g("fio").value, phone: g("phone").value }, ...(x.contacts || []).filter(c => c.kind === "reserve")] };
        if (!body.name_ru) { g("name").value = x.name_ru; return toast(T("Название не может быть пустым")); }
        sv.textContent = "…";
        try {
          await api("/api/facilities/" + x.id, { method: "PATCH", body });
          const ph = phonesOf(body.contacts[0].phone), fio = body.contacts[0].fio.trim().replace(/\s+/g, " ");
          Object.assign(x, { name_ru: body.name_ru, district_id: body.district_id, active: body.active ? 1 : 0, beds: body.beds === "" ? null : +body.beds });
          x.contacts = [{ kind: "main", fio, phone: ph.join(",") }, ...(x.contacts || []).filter(c => c.kind === "reserve")];
          if (field === "phone" && g("phone").value === body.contacts[0].phone) g("phone").value = showPhones(ph);      // only the cell that was changed is rewritten, and only if the person has not typed on
          if (field === "fio" && g("fio").value === body.contacts[0].fio) g("fio").value = fio;
          tr.classList.toggle("off", !body.active);
          sv.textContent = "✓"; setTimeout(() => { if (sv.textContent === "✓") sv.textContent = ""; }, 1500); clearTimeout(sideRefresh.t); sideRefresh.t = setTimeout(sideRefresh, 600);
        } catch (er) { sv.textContent = "⚠"; fail(er); }
      });
    };
  };
  // the proposals of the people of the bot: add / remove a facility; the person with the section decides here (adds or removes it with the usual dialogs, or refuses)
  const loadProps = async rid => {
    let r; try { r = await api("/api/facility-proposals?" + qs({ status: PROP.all ? "all" : "new", region_id: rid })); } catch (e) { return fail(e); }
    const box = $("#tprop"); if (!box || cur !== rid) return;
    ME.proposals_new = r.new; badgeProposals();
    const newHere = r.items.filter(x => x.status === "new").length;
    const who = p => `${esc(p.who)}${p.username ? ` (@${esc(p.username)})` : ""}`;
    const row = p => `<div class="prop ${p.status}"><div class="prop-h"><span class="pill ${p.kind === "add" ? "normal" : "critical"}">${p.kind === "add" ? T("Добавить") : T("Удалить")}</span> <b>${esc(p.kind === "remove" && p.facility ? nm({ name_ru: p.facility, name_uz: p.facility_uz }) : p.name)}</b>
        <span class="muted sm">${esc(rname(p.region))}${p.kind === "remove" && p.district ? " · " + esc(p.district) : ""}</span>
        ${p.status === "done" ? `<span class="pill sent">${T("Выполнено")}</span>` : p.status === "rejected" ? `<span class="pill">${T("Отклонено")}</span>` : ""}</div>
      ${p.comment ? `<div class="prop-c">${esc(p.comment)}</div>` : ""}
      <div class="muted sm">${T("От {who} · {at}", { who: who(p), at: esc(p.at) })}${p.status !== "new" ? ` · ${T("Решил(а): {name}, {at}", { name: esc(p.handled_by || "—"), at: esc(p.handled_at) })}${p.handled_comment ? ` · ${esc(p.handled_comment)}` : ""}` : ""}</div>
      ${p.status === "new" ? `<div class="row mt"><button class="btn sm pri" data-pa="${p.id}">${p.kind === "add" ? T("Добавить учреждение") : p.facility_id ? T("Удалить учреждение") : T("Учреждения уже нет: закрыть")}</button><button class="btn sm" data-pr="${p.id}">${T("Отклонить")}</button></div>` : ""}</div>`;
    if (!newHere && !PROP.all) {          // nothing to decide in this region: one quiet line, not a whole block
      box.innerHTML = `<div class="row"><span class="muted sm">${T("Предложения от пользователей бота")}: ${T("новых нет")}</span><button class="btn sm" data-pf="all">${T("Показать все предложения")}</button></div>`;
      box.querySelectorAll("[data-pf]").forEach(b => b.onclick = () => { PROP.all = true; loadProps(rid); });
      return;
    }
    box.innerHTML = `<div class="row"><h3 style="margin:0">${T("Предложения от пользователей бота")}</h3>${newHere ? `<span class="pill warning">${T("новых: {n}", { n: newHere })}</span>` : ""}<div class="seg right"><button data-pf="new" class="${PROP.all ? "" : "on"}">${T("Новые")}</button><button data-pf="all" class="${PROP.all ? "on" : ""}">${T("Все")}</button></div></div>
      <p class="muted sm">${T("Люди с доступом к региону предлагают в боте добавить или удалить учреждение. Само по себе предложение ничего не меняет: добавьте или удалите учреждение здесь, либо отклоните предложение.")}</p>
      ${r.items.length ? r.items.map(row).join("") : `<p class="muted">${PROP.all ? T("Предложений пока нет.") : T("Новых предложений нет.")}</p>`}`;
    box.querySelectorAll("[data-pf]").forEach(b => b.onclick = () => { PROP.all = b.dataset.pf === "all"; loadProps(rid); });
    const finish = async (p, body, msgText) => { await api(`/api/facility-proposals/${p.id}/resolve`, { method: "POST", body }); toast(msgText); await sideRefresh(); await regionView(cur); };
    box.querySelectorAll("[data-pr]").forEach(b => b.onclick = () => { const p = r.items.find(x => x.id === +b.dataset.pr);
      confirmDlg(T("Отклонить предложение"), `<p>${esc(p.name)} (${esc(rname(p.region))})</p>`, T("Отклонить"), async reason => { await finish(p, { status: "rejected", comment: reason }, T("Предложение отклонено")); closeModal(); }, true); });
    box.querySelectorAll("[data-pa]").forEach(b => b.onclick = async () => { const p = r.items.find(x => x.id === +b.dataset.pa);
      if (p.kind === "add") {
        let d; try { d = await api("/api/districts?region_id=" + p.region_id); } catch (e) { return fail(e); }
        return facAddDlg(d.items.filter(x => x.active), "", id => finish(p, { status: "done", facility_id: id }, T("Учреждение добавлено, предложение закрыто")).catch(fail), p.name);
      }
      if (!p.facility_id) return finish(p, { status: "done", comment: T("Учреждения уже нет") }, T("Предложение закрыто")).catch(fail);
      confirmDlg(T("Удалить учреждение"), `<p>${T("Учреждение {name} ({district}) будет удалено.", { name: `<b>${esc(nm({ name_ru: p.facility, name_uz: p.facility_uz }))}</b>`, district: esc(p.district) })}</p><ul class="sm"><li>${T("Отчётов, которые удалятся вместе с ним: {n}", { n: `<b>${p.reports}</b>` })}</li></ul><p class="muted sm">${T("Если нужно только скрыть учреждение из отчётности, используйте «Изменить» и снимите «Активно»: данные сохранятся.")}</p>`, T("Удалить безвозвратно"), async () => {
        await api("/api/facilities/" + p.facility_id + "?force=1", { method: "DELETE" }); await finish(p, { status: "done" }, T("Учреждение удалено, предложение закрыто")); closeModal(); });
    });
  };
  if (SUP) { $("#t-add").onclick = () => nameDlg("regions", {}, load, true); $("#t-imp").onclick = () => importDlg(load); $("#t-rep").onclick = () => reportImportDlg(load); }
  load();
}
function facAddDlg(districts, did, done, prefill = "") {
  if (!districts.length) { toast(T("Сначала добавьте район")); return; }
  modal(`<h2>${T("Добавить учреждение")}</h2><label>${T("Район")}<select id="fa-d">${districts.map(x => `<option value="${x.id}" ${String(x.id) === String(did) ? "selected" : ""}>${esc(nm(x))}</option>`).join("")}</select></label><label>${T("Название (рус.)")}<input id="fa-ru" value="${esc(prefill)}"></label><label>${T("Название (узб.)")}<input id="fa-uz"></label><div id="fa-err" class="err"></div><div class="row mt"><button class="btn pri" id="fa-ok">${T("Добавить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#fa-ok").onclick = async () => { try { const x = await api("/api/facilities", { method: "POST", body: { district_id: +$("#fa-d").value, name_ru: $("#fa-ru").value, name_uz: $("#fa-uz").value } }); closeModal(); toast(T("Учреждение добавлено")); done(x.id); } catch (e) { $("#fa-err").textContent = e.message; } };
}
// the head of the regional health department and a reserve one: full name and phone (the people of the bot with these phones get the access to the whole region)
function regionContactDlg(rid, rc, done) {
  const m = rc.find(x => x.kind === "main") || { fio: "", phone: "" }, r = rc.find(x => x.kind === "reserve") || { fio: "", phone: "" };
  modal(`<h2>${T("Руководитель отдела здравоохранения")}</h2>
    <div class="row"><label>${T("Ф.И.Ш.")}<input id="rc-f1" value="${esc(m.fio)}"></label><label>${T("Телефон")}<input id="rc-p1" value="${esc(showPhones(m.phone))}" inputmode="tel" placeholder="+998 __ ___ __ __"></label></div>
    <p class="muted sm">${T("Когда этот человек отправит боту свой номер телефона кнопкой, он автоматически получит доступ ко всему региону.")}</p>
    <h3>${T("Резервный ответственный")}</h3><div class="row"><label>${T("Ф.И.Ш.")}<input id="rc-f2" value="${esc(r.fio)}"></label><label>${T("Телефон")}<input id="rc-p2" value="${esc(showPhones(r.phone))}" inputmode="tel" placeholder="+998 __ ___ __ __"></label></div>
    <div id="rc-err" class="err"></div><div class="row mt"><button class="btn pri" id="rc-ok">${T("Сохранить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#rc-ok").onclick = async () => {
    try { await api(`/api/regions/${rid}/contacts`, { method: "PUT", body: { contacts: [{ kind: "main", fio: $("#rc-f1").value, phone: $("#rc-p1").value }, { kind: "reserve", fio: $("#rc-f2").value, phone: $("#rc-p2").value }] } }); closeModal(); toast(T("Сохранено")); done(); }
    catch (e) { $("#rc-err").textContent = e.message; }
  };
}
// the whole facility in one dialog: names, district, beds, the responsible person and a reserve one (full name and phone), who is connected in the bot
function facDlg(x, districts, did, done) {
  if (!districts.length) { toast(T("Сначала добавьте район")); return; }
  const isNew = !x, m = x ? mainOf(x) : { fio: "", phone: "" }, rv = x ? reserveOf(x) : { fio: "", phone: "" }, sel = x ? x.district_id : did;
  modal(`<h2>${isNew ? T("Добавить учреждение") : T("Изменить")}</h2>
    <label>${T("Район")}<select id="fd-d">${districts.map(y => `<option value="${y.id}" ${String(y.id) === String(sel) ? "selected" : ""}>${esc(nm(y))}</option>`).join("")}</select></label>
    <label>${T("Название (рус.)")}<input id="fd-ru" value="${esc(x ? x.name_ru : "")}"></label><label>${T("Название (узб.)")}<input id="fd-uz" value="${esc(x ? x.name_uz : "")}"></label>
    <div class="row"><label>${T("Койки")}<input id="fd-b" inputmode="numeric" value="${x && x.beds != null ? x.beds : ""}" style="width:110px"></label>${isNew ? "" : `<label class="chk"><input type="checkbox" id="fd-ac" ${x.active ? "checked" : ""} style="width:auto"> ${T("Активно (отключённое не входит в отчёты)")}</label>`}</div>
    <h3>${T("Ответственный")}</h3><div class="row"><label>${T("Ф.И.Ш.")}<input id="fd-f1" value="${esc(m.fio)}"></label><label>${T("Телефон")}<input id="fd-p1" value="${esc(showPhones(m.phone))}" inputmode="tel" placeholder="+998 __ ___ __ __"></label></div>
    <p class="muted sm">${T("Когда этот человек отправит боту свой номер телефона кнопкой, он автоматически станет ответственным за учреждение.")}</p>
    <h3>${T("Резервный ответственный")}</h3><div class="row"><label>${T("Ф.И.Ш.")}<input id="fd-f2" value="${esc(rv.fio)}"></label><label>${T("Телефон")}<input id="fd-p2" value="${esc(showPhones(rv.phone))}" inputmode="tel" placeholder="+998 __ ___ __ __"></label></div>
    ${!isNew && x.assignments.length ? `<p class="muted sm">${T("Подключены в боте")}: ${x.assignments.map(a => esc(a.fio || [a.first_name, a.last_name].filter(Boolean).join(" ") || a.tg_id) + (a.username ? " @" + esc(a.username) : "") + (a.kind === "reserve" ? " (" + T("резерв") + ")" : "")).join(", ")}</p>` : ""}
    <div id="fd-err" class="err"></div><div class="row mt"><button class="btn pri" id="fd-ok">${T("Сохранить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#fd-ok").onclick = async () => {
    const body = { district_id: +$("#fd-d").value, name_ru: $("#fd-ru").value, name_uz: $("#fd-uz").value, beds: $("#fd-b").value.trim(), contacts: [{ kind: "main", fio: $("#fd-f1").value, phone: $("#fd-p1").value }, { kind: "reserve", fio: $("#fd-f2").value, phone: $("#fd-p2").value }] };
    if (!isNew) body.active = $("#fd-ac").checked;
    try { await api(isNew ? "/api/facilities" : "/api/facilities/" + x.id, { method: isNew ? "POST" : "PATCH", body }); closeModal(); toast(isNew ? T("Учреждение добавлено") : T("Сохранено")); done(); } catch (e) { $("#fd-err").textContent = e.message; }
  };
}
function nameDlg(kind, o, done, isNew) {
  modal(`<h2>${isNew ? T("Добавить") : T("Изменить")}</h2><label>${T("Название (рус.)")}<input id="n-ru" value="${esc(o.name_ru || "")}"></label><label>${T("Название (узб.)")}<input id="n-uz" value="${esc(o.name_uz || "")}"></label>
  ${isNew ? "" : `<label><input type="checkbox" id="n-ac" ${o.active ? "checked" : ""} style="width:auto"> ${T("Активно (отключённое не входит в отчёты)")}</label>`}<div class="row mt"><button class="btn pri" id="n-ok">${T("Сохранить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#n-ok").onclick = async () => { const body = { name_ru: $("#n-ru").value, name_uz: $("#n-uz").value }; if (!isNew) body.active = $("#n-ac").checked; else Object.assign(body, o);
    try { await api(isNew ? "/api/" + kind : `/api/${kind}/${o.id}`, { method: isNew ? "POST" : "PATCH", body }); closeModal(); done(); } catch (e) { fail(e); } };
}
function reportImportDlg(done) {
  modal(`<h2>${T("Загрузка учреждений и показателей из Excel")}</h2><p class="muted">${T("Файл вида «места для больных»: по листу на область, строка на учреждение (койки, свободные, обращения за 24 часа, поступило и выписано вчера/сегодня). Новые учреждения создаются в своей области, показатели записываются как отчёты. Чего в файле нет (тяжёлые и т.п.), остаётся пустым.")}</p>
  <div class="row"><label>${T("«Вчера» записать на дату")}<input type="date" id="ri-p" value="${addDays(ME.today, -1)}"></label><label>${T("«Сегодня» записать на дату")}<input type="date" id="ri-t" value="${ME.today}"></label></div>
  <input type="file" id="ri-f" accept=".xlsx" class="mt"><div id="ri-r" class="mt"></div><div class="row mt"><button class="btn" id="ri-pre">${T("Проверить")}</button><button class="btn pri" id="ri-go" disabled>${T("Загрузить")}</button><button class="btn right" data-close>${T("Закрыть")}</button></div>`, true);
  const run = async dry => { const f = $("#ri-f").files[0]; if (!f) return toast(T("Выберите файл")); const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/import/reports?" + qs({ dry, d_prev: $("#ri-p").value, d_today: $("#ri-t").value }), { method: "POST", form: fd });
      $("#ri-r").innerHTML = `<p><b>${r.dry ? T("Будет сделано") : T("Готово")}:</b> ${r.errors_total ? T("учреждений в файле {f}, новых {n}, отчётов {r}, ошибок {e}. Даты: {d}.", { f: r.facilities, n: r.new_facilities, r: r.reports, e: r.errors_total, d: r.dates.join(" " + T("и") + " ") }) : T("учреждений в файле {f}, новых {n}, отчётов {r}. Даты: {d}.", { f: r.facilities, n: r.new_facilities, r: r.reports, d: r.dates.join(" " + T("и") + " ") })}</p>${r.errors.length ? `<div class="alert critical">${r.errors.map(esc).join("<br>")}</div>` : ""}${r.new_list.length ? `<details><summary>${T("Новые учреждения ({n})", { n: r.new_facilities })}</summary><p class="sm">${r.new_list.map(esc).join("<br>")}</p></details>` : ""}`;
      $("#ri-go").disabled = !r.dry || !!r.errors_total; if (!r.dry) { toast(T("Загружено")); done(); } } catch (e) { fail(e); } };
  $("#ri-pre").onclick = () => run(1); $("#ri-go").onclick = () => run(0);
}
function importDlg(done) {
  modal(`<h2>${T("Импорт территорий")}</h2><p class="muted">${T("Столбцы: Регион, Район, Учреждение (+ необязательно «Район (узб)», «Учреждение (узб)»). Сначала предпросмотр.")}</p><input type="file" id="i-f" accept=".xlsx,.csv"><div id="i-r" class="mt"></div><div class="row mt"><button class="btn" id="i-pre">${T("Проверить")}</button><button class="btn pri" id="i-go" disabled>${T("Загрузить")}</button><button class="btn right" data-close>${T("Закрыть")}</button></div>`);
  const run = async dry => { const f = $("#i-f").files[0]; if (!f) return toast(T("Выберите файл")); const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/geo/import?dry=" + dry, { method: "POST", form: fd }); $("#i-r").innerHTML = `<pre>${esc(JSON.stringify(r, null, 1))}</pre>`; $("#i-go").disabled = !!dry ? !(r.errors && r.errors.length === 0) : true; if (!dry) { toast(T("Загружено")); done(); } } catch (e) { fail(e); } };
  $("#i-pre").onclick = () => run(1); $("#i-go").onclick = () => run(0);
}

// ---------- the editor of territories: an Excel list of facilities (region, name, beds, head physician, phone) matched with the facilities of the platform
const ED = { data: null, rows: [], disable: new Set(), only: false };      // the preview of the list and what the person decided (kept while the page is redrawn)
async function editorView() {
  const nav = NAVID;
  if (nav !== NAVID) return;
  view.innerHTML = `<div class="card"><h2>${T("Редактор территорий")}</h2>
    <p class="muted">${T("Загрузите Excel со списком учреждений (регион, учреждение, число коек, ответственный, телефон). Каждое учреждение из файла сопоставляется с учреждением платформы в том же регионе: если на платформе оно записано с ошибкой, название исправится на то, что в файле. Ничего не записывается, пока вы не нажмёте «Применить».")}</p>
    <div class="row"><input type="file" id="ed-f" accept=".xlsx"><button class="btn pri" id="ed-go">${T("Проверить файл")}</button><span class="muted sm" id="ed-name"></span></div></div><div id="ed-r"></div>`;
  const regionName = id => rname((META.regions.find(r => r.id === id) || {}).name_ru || "");
  const facOf = (rid, id) => ((ED.data.facilities || {})[rid] || []).find(f => f.id === id);
  const chosen = () => new Set(ED.rows.filter(r => r.action === "match" && r.facility_id).map(r => r.facility_id));
  const render = () => {
    const box = $("#ed-r"); if (!box || !ED.data) return;
    const used = chosen(), dup = new Set(), seen = new Set();
    ED.rows.forEach(r => { if (r.action === "match" && r.facility_id) { if (seen.has(r.facility_id)) dup.add(r.facility_id); seen.add(r.facility_id); } });
    const st = r => r.action === "skip" ? "skip" : r.action === "new" ? "new" : r.action === "review" ? "review" : (r.current && r.current.name === r.name ? "ok" : "fix");
    const cnt = { ok: 0, fix: 0, new: 0, skip: 0, review: 0 }; ED.rows.forEach(r => cnt[st(r)]++);
    const attention = r => st(r) === "new" || st(r) === "review" || (r.action === "skip" && r.reason === "region") || dup.has(r.facility_id) || (r.warn.includes("phone") && !r.phone);
    const regions = [...new Set(ED.rows.map(r => r.region_text))];
    const left = rid => ((ED.data.facilities || {})[rid] || []).filter(f => !used.has(f.id));
    const off = [...ED.disable].filter(id => !used.has(id)).length;
    const rowHtml = (r, i) => { const s = st(r), fac = r.facility_id ? facOf(r.region_id, r.facility_id) : null;
      const opts = [...(r.action === "review" ? [`<option value="" selected disabled>${T("— выберите —")}</option>`] : []), `<option value="new" ${r.action === "new" ? "selected" : ""}>${T("➕ Создать новое учреждение")}</option>`, `<option value="skip" ${r.action === "skip" ? "selected" : ""}>${T("⏭ Пропустить")}</option>`];
      if (r.region_id && r.allowed) {
        const all = (ED.data.facilities[r.region_id] || []), sug = new Map((r.candidates || []).map(c => [c.id, c.score]));
        const o = f => `<option value="m:${f.id}" ${r.action === "match" && r.facility_id === f.id ? "selected" : ""}>${esc(f.name)}${sug.has(f.id) ? ` — ${Math.round(100 * sug.get(f.id))}%` : ""}${used.has(f.id) && r.facility_id !== f.id ? " ✓" : ""}</option>`;
        const top = all.filter(f => sug.has(f.id)).sort((a, b) => sug.get(b.id) - sug.get(a.id));
        if (top.length) opts.push(`<optgroup label="${T("Похожие")}">${top.map(o).join("")}</optgroup>`);
        opts.push(`<optgroup label="${T("Все учреждения региона")}">${all.filter(f => !sug.has(f.id)).map(o).join("")}</optgroup>`);
      }
      const phones = r.phone ? r.phone.split(",").map(p => fmtPhone(p.trim())).join(", ") : "";
      const result = s === "ok" ? `<span class="pill sent">${T("Совпадает")}</span>` : s === "fix" ? `<span class="pill warning">${T("Название исправится")}</span><div class="sm er-old"><s>${esc(r.current.name)}</s></div>` : s === "new" ? `<span class="pill normal">${T("Будет создано")}</span>` : s === "review" ? `<span class="pill critical">${T("Нужно решить")}</span><div class="sm muted">${T("Есть похожее учреждение: выберите его или «создать»")}</div>` : `<span class="pill">${r.reason === "placeholder" ? T("Шаблонная строка") : r.reason === "access" ? T("Не ваш регион") : r.reason === "region" ? T("Регион не распознан") : T("Пропуск")}</span>`;
      const diff = [];
      if (fac && r.action === "match") {
        if (r.beds != null && fac.beds !== r.beds) diff.push(T("койки: {a} → {b}", { a: fac.beds ?? "—", b: r.beds }));
        if ((r.fio && r.fio !== fac.fio) || (r.phone && r.phone.replace(/, /g, ",") !== fac.phone)) diff.push(T("ответственный будет записан"));
      }
      return `<tr class="er ${s}${dup.has(r.facility_id) ? " dup" : ""}" data-i="${i}"><td class="n muted">${r.row}</td>
        <td><b>${esc(r.name)}</b><div class="sm muted">${r.beds != null ? T("коек: {n}", { n: r.beds }) + " · " : ""}${esc(r.fio) || `<span class="warn-t">${T("нет Ф.И.Ш.")}</span>`} · ${phones ? esc(phones) : `<span class="warn-t">${T("нет телефона")}</span>`}${r.warn.includes("phone_format") ? ` <span class="warn-t">${T("проверьте номер")}</span>` : ""}</div></td>
        <td><select class="ci" data-pick="${i}" ${r.reason === "region" || r.reason === "access" ? "disabled" : ""}>${opts.join("")}</select>${dup.has(r.facility_id) ? `<div class="sm err">${T("Это учреждение выбрано для нескольких строк")}</div>` : ""}</td>
        <td>${result}${diff.length ? `<div class="sm muted">${diff.map(esc).join("; ")}</div>` : ""}</td></tr>`; };
    box.innerHTML = `<div class="card"><div class="row"><h3 style="margin:0">${T("Результат проверки")}</h3><span class="muted sm">${esc(ED.file || "")}</span>
        <div class="seg right"><button data-only="0" class="${ED.only ? "" : "on"}">${T("Все строки")}</button><button data-only="1" class="${ED.only ? "on" : ""}">${T("Требуют внимания")}</button></div></div>
      <div class="edsum"><span class="pill sent">${T("Совпадают: {n}", { n: cnt.ok })}</span><span class="pill warning">${T("Название исправится: {n}", { n: cnt.fix })}</span><span class="pill normal">${T("Будут созданы: {n}", { n: cnt.new })}</span><span class="pill">${T("Пропущены: {n}", { n: cnt.skip })}</span>${cnt.review ? `<span class="pill critical">${T("Нужно решить: {n}", { n: cnt.review })}</span>` : ""}${off ? `<span class="pill critical">${T("Будут отключены: {n}", { n: off })}</span>` : ""}</div>
      ${ED.data.problems.length ? `<div class="alert critical">${ED.data.problems.map(p => T("Регион «{name}» не распознан: строки пропущены. Проверьте написание в файле.", { name: esc(p.text) })).join("<br>")}</div>` : ""}
      <div class="row mt"><button class="btn pri" id="ed-apply">${T("Применить")}</button><button class="btn" id="ed-reset">${T("Сбросить")}</button><span class="muted sm">${T("Выбор в списке справа можно менять: «создать», «пропустить» или любое учреждение региона.")}</span></div></div>
      ${regions.map(text => { const rs = ED.rows.map((r, i) => [r, i]).filter(([r]) => r.region_text === text), info = ED.data.regions.find(x => x.text === text) || {}, shown = rs.filter(([r]) => !ED.only || attention(r));
        const rest = info.region_id && info.allowed ? left(info.region_id) : [];
        return `<div class="card"><details ${shown.length || rest.length || !ED.only ? "open" : ""}><summary><b>${esc(info.region_id ? regionName(info.region_id) : text)}</b> <span class="muted sm">${T("строк: {n}", { n: rs.length })}${info.region_id && info.allowed ? " · " + T("учреждений на платформе: {n}", { n: info.facilities }) : ""}</span></summary>
          <div class="scroll-x"><table class="edtab"><colgroup><col class="e-n"><col class="e-x"><col class="e-s"><col class="e-r"></colgroup><tr><th>${T("№")}</th><th>${T("Из файла")}</th><th>${T("Сопоставить с учреждением платформы")}</th><th>${T("Что будет")}</th></tr>${shown.map(([r, i]) => rowHtml(r, i)).join("") || `<tr><td colspan="4" class="muted">${T("Нет строк, требующих внимания")}</td></tr>`}</table></div>
          ${rest.length ? `<details class="mt"><summary class="muted">${T("Есть на платформе, но не выбрано ни для одной строки: {n}", { n: rest.length })}</summary><table class="mt"><tr><th>${T("Учреждение")}</th><th>${T("Район")}</th><th>${T("Что сделать")}</th></tr>${rest.map(f => `<tr><td>${esc(f.name)}${f.active ? "" : ` <span class="pill critical">${T("отключено")}</span>`}</td><td>${esc(f.district)}</td><td><select class="ci" data-off="${f.id}"><option value="keep">${T("Оставить как есть")}</option><option value="off" ${ED.disable.has(f.id) ? "selected" : ""} ${f.active ? "" : "disabled"}>${T("Отключить (данные сохранятся)")}</option></select></td></tr>`).join("")}</table></details>` : ""}
        </details></div>`; }).join("")}`;
    box.querySelectorAll("[data-only]").forEach(b => b.onclick = () => { ED.only = b.dataset.only === "1"; render(); });
    box.querySelectorAll("[data-pick]").forEach(sl => sl.onchange = () => { const r = ED.rows[+sl.dataset.pick], v = sl.value;
      if (v === "new") { r.action = "new"; r.facility_id = null; r.current = null; r.reason = ""; } else if (v === "skip") { r.action = "skip"; r.facility_id = null; r.current = null; r.reason = "manual"; }
      else { const f = facOf(r.region_id, +v.slice(2)); r.action = "match"; r.facility_id = f.id; r.reason = ""; r.current = { name: f.name, beds: f.beds, fio: f.fio, phone: f.phone, district: f.district }; ED.disable.delete(f.id); }
      render(); });
    box.querySelectorAll("[data-off]").forEach(sl => sl.onchange = () => { sl.value === "off" ? ED.disable.add(+sl.dataset.off) : ED.disable.delete(+sl.dataset.off); render(); });
    $("#ed-reset").onclick = () => { ED.data = null; ED.rows = []; ED.disable = new Set(); box.innerHTML = ""; $("#ed-name").textContent = ""; };
    $("#ed-apply").onclick = () => {
      if (cnt.review) return toast(T("Сначала решите строки, отмеченные красным: {n}", { n: cnt.review }));
      if (dup.size) return toast(T("Одно учреждение выбрано для нескольких строк: исправьте выбор"));
      confirmDlg(T("Применить изменения"), `<p>${T("Будет сделано: названий исправить — {a}, создать — {b}, отключить — {c}. Ответственные и койки из файла запишутся для всех сопоставленных и созданных учреждений.", { a: cnt.fix, b: cnt.new, c: off })}</p><p class="muted sm">${T("Исправленные названия записываются в русское и узбекское поле; отчёты не затрагиваются. Изменения попадут в журнал.")}</p>`, T("Применить"), async () => {
        const body = { rows: ED.rows.map(r => ({ region_id: r.region_id, name: r.name, beds: r.beds, fio: r.fio, phone: r.phone, action: r.action, facility_id: r.facility_id })), disable: [...ED.disable].filter(id => !used.has(id)) };
        const res = await api("/api/editor/apply", { method: "POST", body }); closeModal();
        ED.data = null; ED.rows = []; ED.disable = new Set();
        box.innerHTML = `<div class="card"><h3>${T("Готово")}</h3><div class="edsum"><span class="pill warning">${T("Названий исправлено: {n}", { n: res.renamed })}</span><span class="pill sent">${T("Без изменений названия: {n}", { n: res.same })}</span><span class="pill normal">${T("Создано: {n}", { n: res.created })}</span><span class="pill">${T("Ответственных записано: {n}", { n: res.contacts })}</span>${res.linked ? `<span class="pill sent">${T("Подключено в боте: {n}", { n: res.linked })}</span>` : ""}<span class="pill critical">${T("Отключено: {n}", { n: res.disabled })}</span></div>
          ${res.errors.length ? `<div class="alert critical mt"><b>${T("Не удалось применить: {n}", { n: res.errors.length })}</b><br>${res.errors.map(e => esc(e.name) + ": " + esc(TS(e.message))).join("<br>")}</div>` : ""}
          <p class="mt"><a class="btn pri" href="#/territories">${T("Открыть учреждения")}</a></p></div>`; });
    };
  };
  $("#ed-go").onclick = async () => {
    const f = $("#ed-f").files[0]; if (!f) return toast(T("Выберите файл"));
    const fd = new FormData(); fd.append("file", f); $("#ed-go").disabled = true; $("#ed-name").textContent = T("Проверяю…");
    try { ED.data = await api("/api/editor/preview", { method: "POST", form: fd }); ED.rows = ED.data.rows; ED.file = f.name; ED.disable = new Set(); ED.only = false; $("#ed-name").textContent = ""; render(); }
    catch (e) { $("#ed-name").textContent = ""; fail(e); }
    $("#ed-go").disabled = false;
  };
  if (ED.data) render();
}
// ---------- the questionnaire of the bot: the questions (order, texts in two languages, hints, optional, on/off), the limits between them and the check rules; how the bot shows it
const AGG = { sum: T("складывать за период (обращения, поступившие)"), last: T("брать значение последнего дня (койки, тяжёлые)"), max: T("брать максимум за период") };
async function indicators() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const [r, st] = await Promise.all([api("/api/indicators"), api("/api/settings")]);
  if (nav !== NAVID) return;
  const items = r.items, S = st.settings, byCode = Object.fromEntries(items.map(i => [i.code, i]));
  const qn = i => (LANG === "uz" && i.name_uz) || i.name_ru;
  const pos = {}; items.filter(i => i.active).forEach((i, k) => { pos[i.code] = k + 1; });
  const limitOf = code => { const x = r.rules.find(q => q.active && q.kind === "error" && new RegExp(`^\\s*${code}\\s*<=\\s*([a-z][a-z0-9_]*)\\s*$`).test(q.expr)); return x ? x.expr.split("<=")[1].trim() : ""; };
  const words = expr => esc(expr).replace(/\b[a-z][a-z0-9_]*\b/g, m => byCode[m] ? `«${esc(qn(byCode[m]))}»` : m);
  const row = i => `<tr class="${i.active ? "" : "off"}" data-i="${i.code}"><td class="n muted">${pos[i.code] || "—"}</td>
      <td><b>${esc(i.name_ru)}</b>${i.name_uz ? `<div class="muted sm">${esc(i.name_uz)}</div>` : `<div class="sm warn-t">${T("нет узбекского названия")}</div>`}${i.parent_code && byCode[i.parent_code] ? `<div class="sm">↳ ${T("уточняет вопрос")} ${pos[i.parent_code] || "—"}: ${esc(qn(byCode[i.parent_code]))}</div>` : ""}<div class="muted sm"><code>${esc(i.code)}</code>${i.core ? " 🔒" : ""}</div></td>
      <td class="sm">${i.hint_ru ? "RU ✓" : "RU —"} · ${i.hint_uz ? "UZ ✓" : "UZ —"}</td>
      <td class="sm">${limitOf(i.code) && byCode[limitOf(i.code)] ? "≤ " + esc(qn(byCode[limitOf(i.code)])) : '<span class="muted">—</span>'}</td>
      <td class="sm">${i.required ? T("да") : `<span class="muted">${T("нет")}</span>`}</td>
      <td class="c"><input type="checkbox" data-on="${i.code}" ${i.active ? "checked" : ""} title="${T("Включён: бот задаёт этот вопрос")}"></td>
      <td class="act"><button class="btn sm" data-up="${i.code}" title="${T("Выше")}">↑</button><button class="btn sm" data-dn="${i.code}" title="${T("Ниже")}">↓</button><button class="btn sm" data-i="${i.code}">${T("Изменить")}</button>${i.core ? "" : `<button class="btn sm bad" data-del="${i.code}" title="${T("Удалить")}">✕</button>`}</td></tr>`;
  view.innerHTML = `<div class="card"><div class="row"><h2>${T("Вопросник бота")}</h2><button class="btn right" id="q-prev">${T("👁 Как это видит человек в боте")}</button><button class="btn pri" id="i-add">${T("+ Вопрос")}</button></div>
      <p class="muted sm">${T("Бот задаёт включённые вопросы по порядку. Выключенный вопрос не задаётся, а ответы на него в прежних отчётах сохраняются. Основные вопросы (🔒) на панели и в расчётах нельзя удалить, только выключить.")}</p>
      <div class="qsw"><label><input type="checkbox" id="q-note" ${S.note_enabled === "1" ? "checked" : ""}> ${T("Последний вопрос: конфиденциальное сообщение для Министерства")}</label>
        <label><input type="checkbox" id="q-hints" ${S.q_hints === "1" ? "checked" : ""}> ${T("Показывать подсказку под вопросом")}</label></div>
      <div class="scroll-x"><table class="qtab"><colgroup><col class="c-i"><col class="c-n"><col class="c-h"><col class="c-l"><col class="c-q"><col class="c-a"><col class="c-x"></colgroup>
        <tr><th>#</th><th>${T("Вопрос")}</th><th>${T("Подсказка")}</th><th>${T("Ответ не больше")}</th><th>${T("Обязательный")}</th><th>${T("Вкл.")}</th><th></th></tr>${items.map(row).join("")}</table></div></div>
    <div class="card"><div class="row"><h2>${T("Правила проверки")}</h2><button class="btn pri right" id="r-add">${T("+ Правило")}</button></div><p class="muted sm">${T("Правило сравнивает ответы: «ошибка» не даёт отправить сводку, «предупреждение» только предупреждает. Простое правило «ответ не больше другого» человек видит в боте уже у вопроса.")}</p><div class="scroll-x"><table><tr><th>${T("Вид")}</th><th>${T("Условие (должно выполняться)")}</th><th>${T("Сообщение")}</th><th>${T("Вкл.")}</th><th></th></tr>${r.rules.map(x => `<tr><td>${x.kind === "error" ? `<span class="pill critical">${T("ошибка")}</span>` : `<span class="pill warning">${T("предупреждение")}</span>`}</td><td><code>${esc(x.expr)}</code><div class="muted sm">${words(x.expr)}</div></td><td class="sm">${esc((LANG === "uz" && x.message_uz ? x.message_uz : x.message_ru).replace(/\{(\w+)\}/g, (m, k) => byCode[k] ? "…" : m))}</td><td>${x.active ? "✓" : "—"}</td><td><button class="btn sm" data-r="${x.id}">${T("Изменить")}</button></td></tr>`).join("")}</table></div></div>`;
  const reload = async () => { META = await api("/api/meta"); indicators(); };
  $("#i-add").onclick = () => indDlg(null, items, r.rules, reload);
  document.querySelectorAll("button[data-i]").forEach(b => b.onclick = () => indDlg(byCode[b.dataset.i], items, r.rules, reload));
  $("#r-add").onclick = () => ruleDlg(null); document.querySelectorAll("[data-r]").forEach(b => b.onclick = () => ruleDlg(r.rules.find(x => x.id === +b.dataset.r)));
  const setting = async (k, v) => { try { await api("/api/settings", { method: "PUT", body: { [k]: v ? "1" : "0" } }); toast(T("Сохранено")); } catch (e) { fail(e); } };
  $("#q-note").onchange = e => setting("note_enabled", e.target.checked); $("#q-hints").onchange = e => setting("q_hints", e.target.checked);
  document.querySelectorAll("[data-on]").forEach(c => c.onchange = async () => { try { await api("/api/indicators/" + c.dataset.on, { method: "PATCH", body: { active: c.checked } }); await reload(); } catch (e) { fail(e); c.checked = !c.checked; } });
  const move = async (code, d) => { const codes = items.map(i => i.code), k = codes.indexOf(code), j = k + d; if (j < 0 || j >= codes.length) return; [codes[k], codes[j]] = [codes[j], codes[k]];
    try { await api("/api/indicators/reorder", { method: "POST", body: { codes } }); await reload(); } catch (e) { fail(e); } };
  document.querySelectorAll("[data-up]").forEach(b => b.onclick = () => move(b.dataset.up, -1)); document.querySelectorAll("[data-dn]").forEach(b => b.onclick = () => move(b.dataset.dn, 1));
  document.querySelectorAll("[data-del]").forEach(b => b.onclick = () => { const i = byCode[b.dataset.del];
    confirmDlg(T("Удалить вопрос"), `<p>${T("Вопрос «{name}» будет удалён.", { name: `<b>${esc(i.name_ru)}</b>` })}</p><p class="muted sm">${T("Если по нему уже есть данные в отчётах или он используется в правилах, система откажет: тогда вопрос можно выключить.")}</p>`, T("Удалить"), async () => { await api("/api/indicators/" + i.code, { method: "DELETE" }); closeModal(); toast(T("Вопрос удалён")); reload(); }); });
  $("#q-prev").onclick = () => previewDlg(LANG);
}
// the questions exactly as the bot sends them (Telegram's HTML: b, i), in one of the two languages
async function previewDlg(lang) {
  let r; try { r = await api("/api/questionnaire/preview?lang=" + lang); } catch (e) { return fail(e); }
  modal(`<div class="row"><h2>${T("Так спрашивает бот")}</h2><div class="seg right" id="pv-l"><button data-l="uz" class="${lang === "uz" ? "on" : ""}">UZ</button><button data-l="ru" class="${lang === "ru" ? "on" : ""}">RU</button></div></div>
    <p class="muted sm">${T("Вопросов: {n}. Название учреждения и дата подставляются при заполнении; «…» в ограничении заменится ответом на более ранний вопрос.", { n: r.n })}</p>
    <div class="pvlist">${r.items.map((x, k) => `<div class="bcmsg">${x.text.replace(/\n/g, "<br>")}</div>${x.code !== "__note" && !x.required ? `<div class="muted sm" style="margin:-4px 0 8px 8px">${T("можно пропустить")}</div>` : ""}`).join("")}</div>
    <div class="row mt"><button class="btn right" data-close>${T("Закрыть")}</button></div>`, true);
  $("#pv-l").onclick = e => { const b = e.target.closest("[data-l]"); if (b && b.dataset.l !== lang) previewDlg(b.dataset.l); };
}
function indDlg(i, items, rules, done) {
  const cur = i ? ((rules.find(q => q.active && q.kind === "error" && new RegExp(`^\\s*${i.code}\\s*<=\\s*([a-z][a-z0-9_]*)\\s*$`).test(q.expr)) || { expr: "" }).expr.split("<=")[1] || "").trim() : "";
  const others = items.filter(x => x.active && (!i || x.code !== i.code));
  modal(`<h2>${i ? T("Вопрос") : T("Новый вопрос")}</h2>
    <label>${T("Название (рус.)")}<input id="p-n" value="${esc(i?.name_ru || "")}"></label><label>${T("Название (узб.)")}<input id="p-u" value="${esc(i?.name_uz || "")}"></label>
    <div class="grid2"><label>${T("Короткое название (рус.)")}<input id="p-s" maxlength="40" value="${esc(i?.short_ru || "")}" placeholder="${T("для заголовка колонки в таблице")}"></label><label>${T("Короткое название (узб.)")}<input id="p-su" maxlength="40" value="${esc(i?.short_uz || "")}" placeholder="${T("для заголовка колонки в таблице")}"></label></div>
    <div class="grid2"><label>${T("Подсказка (рус.)")}<textarea id="p-h" rows="2">${esc(i?.hint_ru || "")}</textarea></label><label>${T("Подсказка (узб.)")}<textarea id="p-hu" rows="2">${esc(i?.hint_uz || "")}</textarea></label></div>
    <label>${T("Как складывать по периоду")}<select id="p-a">${Object.entries(AGG).map(([k, l]) => `<option value="${k}" ${(i?.agg || "sum") === k ? "selected" : ""}>${k} — ${l}</option>`).join("")}</select></label>
    <label>${T("Ответ не может быть больше ответа на вопрос")}<select id="p-lim"><option value="">${T("— без ограничения —")}</option>${others.map(x => `<option value="${x.code}" ${cur === x.code ? "selected" : ""}>${esc(x.name_ru)}</option>`).join("")}</select></label>
    <label>${T("Уточняет вопрос («Шундан…»: бот показывает его вместе с ответом на тот вопрос)")}<select id="p-par"><option value="">${T("— самостоятельный вопрос —")}</option>${others.map(x => `<option value="${x.code}" ${i?.parent_code === x.code ? "selected" : ""}>${esc(x.name_ru)}</option>`).join("")}</select></label>
    <div class="row"><label class="chk"><input type="checkbox" id="p-rq" ${!i || i.required ? "checked" : ""} style="width:auto"> ${T("Обязательный (без ответа нельзя отправить сводку)")}</label>${i ? `<label class="chk"><input type="checkbox" id="p-ac" ${i.active ? "checked" : ""} style="width:auto"> ${T("Включён")}</label>` : ""}</div>
    ${i ? "" : `<details><summary class="muted sm">${T("Код (латиница), если нужен свой")}</summary><label><input id="p-c" placeholder="${T("создастся сам из названия")}"></label></details>`}
    <div id="p-err" class="err"></div><div class="row mt"><button class="btn pri" id="p-ok">${T("Сохранить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#p-ok").onclick = async () => {
    const body = { name_ru: $("#p-n").value, name_uz: $("#p-u").value, hint_ru: $("#p-h").value, hint_uz: $("#p-hu").value, short_ru: $("#p-s").value, short_uz: $("#p-su").value, agg: $("#p-a").value, required: $("#p-rq").checked, parent_code: $("#p-par").value };
    if (i) body.active = $("#p-ac").checked; else body.code = ($("#p-c") || { value: "" }).value;
    try {
      const x = await api(i ? "/api/indicators/" + i.code : "/api/indicators", { method: i ? "PATCH" : "POST", body }), code = i ? i.code : x.code, want = $("#p-lim").value;
      if (want !== cur) {                                   // the limit is an ordinary rule «this <= that»: the old one goes, the new one is made with a message in both languages
        for (const q of rules.filter(q => q.kind === "error" && new RegExp(`^\\s*${code}\\s*<=\\s*([a-z][a-z0-9_]*)\\s*$`).test(q.expr))) await api("/api/rules/" + q.id, { method: "DELETE" });
        if (want) { const o = items.find(y => y.code === want); await api("/api/rules", { method: "POST", body: { expr: `${code} <= ${want}`, kind: "error", message_ru: `${body.name_ru} ({${code}}) больше, чем «${o.name_ru}» ({${want}}).`, message_uz: `${body.name_uz || body.name_ru} ({${code}}) «${o.name_uz || o.name_ru}» ({${want}}) dan ko‘p.`, active: true } }); }
      }
      closeModal(); toast(T("Сохранено")); done();
    } catch (e) { $("#p-err").textContent = e.message; }
  };
}
function ruleDlg(x) {
  modal(`<h2>${x ? T("Правило") : T("Новое правило")}</h2><label>${T("Условие: оно должно быть верным (например beds_occupied &lt;= beds_flu)")}<input id="q-e" value="${esc(x?.expr || "")}"></label><label>${T("Вид")}<select id="q-k"><option value="error" ${x?.kind === "error" ? "selected" : ""}>${T("Ошибка (блокирует отправку)")}</option><option value="warning" ${x?.kind === "warning" ? "selected" : ""}>${T("Предупреждение")}</option></select></label>
  <label>${T("Сообщение (рус.; можно {код})")}<input id="q-m" value="${esc(x?.message_ru || "")}"></label><label>${T("Сообщение (узб.)")}<input id="q-u" value="${esc(x?.message_uz || "")}"></label><label><input type="checkbox" id="q-a" ${!x || x.active ? "checked" : ""} style="width:auto"> ${T("Включено")}</label>
  <div class="row mt"><button class="btn pri" id="q-ok">${T("Сохранить")}</button>${x && !x.core ? `<button class="btn bad" id="q-del">${T("Удалить")}</button>` : ""}<button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#q-ok").onclick = async () => { const body = { expr: $("#q-e").value, kind: $("#q-k").value, message_ru: $("#q-m").value, message_uz: $("#q-u").value, active: $("#q-a").checked };
    try { await api(x ? "/api/rules/" + x.id : "/api/rules", { method: x ? "PATCH" : "POST", body }); closeModal(); indicators(); } catch (e) { fail(e); } };
  const d = $("#q-del"); if (d) d.onclick = async () => { if (!confirm(T("Удалить правило?"))) return; try { await api("/api/rules/" + x.id, { method: "DELETE" }); closeModal(); indicators(); } catch (e) { fail(e); } };
}

// ---------- settings
const SET = [["deadline_time", "Срок сдачи (время)", "time"], ["deadline_day_offset", "Срок: через сколько дней после отчётной даты (0 = в тот же день)", "number"], ["backfill_days", "Сколько дней назад можно сдавать отчёт", "number"],
  ["allow_user_edit", "Ответственный может исправлять свой отчёт (1/0)", "number"], ["edit_window_hours", "Окно правки для ответственного, часов", "number"], ["lock_after_days", "Закрывать отчёт для правок через, дней", "number"],
  ["remind_enabled", "Напоминания включены (1/0)", "number"], ["remind_times", "Время напоминаний (через запятую, ЧЧ:ММ)", "text"], ["remind_weekdays", "Дни напоминаний (1=пн … 7=вс)", "text"],
  ["admin_summary_time", "Сводка администраторам (время)", "time"], ["admin_overdue_time", "Список не сдавших (время)", "time"],
  ["occ_elevated", "Порог: повышенная нагрузка, %", "number"], ["occ_critical", "Порог: критическая загрузка, %", "number"], ["fac_occ_warn", "Порог для учреждения, %", "number"], ["stay_days", "Средний срок лечения, дней (для расчётной загрузки коек)", "number"],
  ["growth_warn_pct", "Рост обращений: предупреждение, %", "number"], ["growth_crit_pct", "Рост: тревога, %", "number"], ["severe_growth_pct", "Рост тяжёлых, %", "number"], ["hosp_growth_pct", "Рост госпитализаций, %", "number"], ["org_title", "Название организации (для отчётов)", "text"]];
async function settings() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const r = await api("/api/settings");
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><h2>${T("Настройки")}</h2><p class="muted">${T("Бот:")} ${r.bot.configured ? T("подключён") + (r.bot.username ? " (@" + esc(r.bot.username) + ")" : "") : T("токен не задан (TELEGRAM_BOT_TOKEN)")} ${r.bot.error ? "· " + T("ошибка:") + " " + esc(r.bot.error) : ""}</p><div class="fields">${SET.map(([k, l, t]) => `<label>${T(l)}<input data-k="${k}" type="${t === "time" ? "time" : t}" value="${esc(r.settings[k] ?? "")}"></label>`).join("")}</div>
  <div class="row mt"><button class="btn pri" id="s-save">${T("Сохранить")}</button><button class="btn" id="s-run">${T("Проверить рассылку (без отправки)")}</button><button class="btn" id="s-bk">${T("Резервная копия")}</button></div><pre id="s-out"></pre></div>`;
  $("#s-save").onclick = async () => { try { await api("/api/settings", { method: "PUT", body: Object.fromEntries([...document.querySelectorAll("[data-k]")].map(i => [i.dataset.k, i.value])) }); toast(T("Сохранено")); } catch (e) { fail(e); } };
  $("#s-run").onclick = async () => { try { const x = await api("/api/notify/run", { method: "POST", body: { dry: true, force: true } }); $("#s-out").textContent = JSON.stringify(x.items, null, 1); } catch (e) { fail(e); } };
  $("#s-bk").onclick = async () => { try { toast(T("Создана: {file}", { file: (await api("/api/backup", { method: "POST" })).file })); } catch (e) { fail(e); } };
}

// ---------- audit
async function audit() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const r = await api("/api/audit?limit=300");
  if (nav !== NAVID) return; view.innerHTML = `<div class="card"><h2>${T("Журнал действий")}</h2><p class="muted sm">${T("Записи неизменяемы: изменить или удалить их нельзя.")}</p><div class="scroll-x"><table><tr><th>${T("Когда")}</th><th>${T("Кто")}</th><th>${T("Действие")}</th><th>${T("Объект")}</th><th>${T("Подробности")}</th></tr>${r.items.map(x => `<tr><td>${esc(x.at || x.created_at)}</td><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td>${esc(x.entity)} ${esc(x.entity_id)}</td><td class="sm">${esc(typeof x.details === "string" ? x.details : JSON.stringify(x.details))}</td></tr>`).join("")}</table></div></div>`;
}

// ---------- export
async function exportView() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  const fb = await filterBar(exportView);
  if (nav !== NAVID) return; view.innerHTML = fb.html + `<div class="card"><h2>${T("Выгрузка")}</h2><p class="muted">${T("Сводный отчёт за выбранный период и территорию. В Excel — 3 листа (сводка, детали, динамика), печать A4 с повтором шапки и полями для подписей.")}</p>
  <div class="row"><label>${T("Вид")}<select id="x-k"><option value="daily">${T("Ежедневный")}</option><option value="weekly">${T("Недельный")}</option><option value="monthly">${T("Месячный")}</option><option value="custom" selected>${T("Произвольный период")}</option></select></label>
  ${["xlsx", "pdf", "csv"].map(f => `<a class="btn pri" data-f="${f}" href="#">${f.toUpperCase()}</a>`).join("")}</div></div>`; fb.bind();
  document.querySelectorAll("[data-f]").forEach(a => a.onclick = e => { e.preventDefault(); location.href = "/api/export?" + scopeQ() + "&" + qs({ fmt: a.dataset.f, kind: $("#x-k").value }); });
}

// ---------- broadcast: a message written here goes to the people of the bot (chosen by role, region and today's report), now or by a schedule; the text may hold figures: {name} {unsent_list} …
let BCPOLL = null;
const normAud = a => { a = a || {}; const regions = (a.regions || []).map(Number);
  if ("roles" in a || "report" in a) return { roles: ["heads", "responsibles"].includes(a.roles) ? a.roles : "all", report: ["unsent", "sent"].includes(a.report) ? a.report : "any", regions };
  const m = a.mode || "all"; return { roles: ["heads", "responsibles"].includes(m) ? m : "all", report: m === "unsent" ? "unsent" : "any", regions }; };
const audLabel = a => { a = normAud(a);
  const roles = { all: T("Все, у кого есть доступ"), heads: T("Руководители регионов"), responsibles: T("Ответственные учреждений") }[a.roles], rep = { any: "", unsent: T("не сдали сегодня"), sent: T("сдали сегодня") }[a.report];
  const regs = a.regions.length ? a.regions.map(id => rname((META.regions.find(r => r.id === id) || {}).name_ru || id)).join(", ") : T("все регионы");
  return [roles, rep, regs].filter(Boolean).join(" · "); };
const whenLabel = x => x.repeat === "daily" ? T("каждый день в {t}", { t: x.at_time }) : x.repeat === "weekdays" ? T("по будням в {t}", { t: x.at_time }) : T("{d} в {t}", { d: x.run_date, t: x.at_time });
async function broadcastView() {
  const nav = NAVID;                                         // this page's number: a late answer after the person moved on must not draw over the new page
  clearTimeout(BCPOLL);
  const regs = (ME.regions === null ? META.regions : META.regions.filter(r => ME.regions.includes(r.id)));
  let spec = { roles: "all", report: "any", regions: [] }, when = "now", sample = "", tpls = [], phs = [], lastTa = null;
  const seg = (id, items, cur) => `<div class="seg" id="${id}">${items.map(([k, l]) => `<button data-v="${k}" class="${k === cur ? "on" : ""}">${l}</button>`).join("")}</div>`;
  const PH = { name: T("Имя получателя"), facility: T("Его учреждение (учреждения)"), region: T("Регион"), date: T("Сегодняшняя дата"), deadline: T("Срок сдачи"), sent: T("Сколько учреждений сдали"), total: T("Сколько учреждений всего"),
    unsent: T("Сколько не сдали"), percent: T("Процент сдавших"), unsent_list: T("Список не сдавших (руководителю региона: с телефонами ответственных)"), status: T("Статус его учреждений: сдал / не сдал") };
  if (nav !== NAVID) return;
  view.innerHTML = `<div class="bc-grid"><div class="card bc-main"><div class="row"><h2>${T("Рассылка")}</h2><span class="muted sm">${T("сообщение придёт в Telegram тем, кто пользуется ботом")}</span></div>
    <div class="bc-step"><div class="bc-h"><b>1</b> ${T("Кому")}</div>
      <div class="bc-line"><span class="muted sm">${T("Кто")}</span>${seg("bc-roles", [["all", T("Все")], ["heads", T("Руководители регионов")], ["responsibles", T("Ответственные учреждений")]], spec.roles)}</div>
      <p class="muted sm" id="bc-role-hint" style="margin:0 0 6px"></p>
      <div class="bc-line"><span class="muted sm">${T("Сводка за сегодня")}</span>${seg("bc-report", [["any", T("Любые")], ["unsent", T("Не сдали")], ["sent", T("Сдали")]], spec.report)}</div>
      <div class="bc-line"><span class="muted sm">${T("Регионы")}</span><div class="chips" id="bc-regs"><button class="chip on" data-r="all">${T("Все регионы")}</button>${regs.map(r => `<button class="chip" data-r="${r.id}">${esc(LANG === "uz" ? nm(r) : r.name_ru.replace("Республика ", "").replace(" область", "").replace("город ", "г. "))}</button>`).join("")}</div></div>
      <div class="bc-count" id="bc-count"><span class="muted">${T("Считаю получателей…")}</span></div></div>
    <div class="bc-step"><div class="bc-h"><b>2</b> ${T("Текст")}</div>
      <div class="row"><select id="bc-tpl" style="min-width:260px"></select><button class="btn sm" id="bc-tpl-save">${T("Сохранить как шаблон")}</button><button class="btn sm bad" id="bc-tpl-del" hidden>${T("Удалить шаблон")}</button></div>
      <div class="bc-ph"><span class="muted sm">${T("Вставить в текст (у каждого получателя подставятся его данные):")}</span><div class="chips" id="bc-ph"></div></div>
      <div class="grid2 bc-ta"><label>${T("Текст по-узбекски (O‘zbekcha)")}<textarea id="bc-uz" rows="7" maxlength="3500" placeholder="Xabar matni"></textarea><span class="muted sm" id="bc-uz-n">0 / 3500</span></label>
        <label>${T("Текст по-русски")}<textarea id="bc-ru" rows="7" maxlength="3500" placeholder="${T("Текст сообщения")}"></textarea><span class="muted sm" id="bc-ru-n">0 / 3500</span></label></div>
      <p class="muted sm">${T("Каждый получит текст на своём языке бота. Если один язык оставить пустым, его получатели увидят текст на другом. Перед текстом бот добавит строку «📢 Объявление».")}</p></div>
    <div class="bc-step"><div class="bc-h"><b>3</b> ${T("Когда")}</div>
      <div class="bc-line">${seg("bc-when", [["now", T("Сейчас")], ["later", T("По расписанию")]], when)}</div>
      <div class="bc-sched" id="bc-sched" hidden><div class="row"><label>${T("Повтор")}<select id="bc-rep"><option value="once">${T("Один раз")}</option><option value="daily">${T("Каждый день")}</option><option value="weekdays">${T("По будням (пн–пт)")}</option></select></label>
        <label id="bc-date-l">${T("Дата")}<input type="date" id="bc-date" value="${ME.today}" min="${ME.today}"></label><label>${T("Время")}<input type="time" id="bc-time" value="18:30"></label><label>${T("Название")}<input id="bc-title" placeholder="${T("Например: вечерняя сводка")}" style="min-width:220px"></label></div>
        <p class="muted sm">${T("Получатели и цифры в тексте берутся в момент отправки, а не сейчас.")}</p></div></div>
    <div class="row mt"><button class="btn pri" id="bc-go">${T("Предпросмотр и отправка")}</button><button class="btn" id="bc-test">${T("🧪 Тест себе")}</button><input id="bc-tid" placeholder="${T("Telegram ID для теста (если не указан в профиле)")}" style="max-width:300px"></div></div>
    <aside class="card bc-side"><h3 style="margin:0 0 8px">${T("Так увидит получатель")}</h3><select id="bc-who" style="width:100%" hidden></select><div id="bc-prev" class="bc-prev"><p class="muted sm">${T("Напишите текст: здесь появится сообщение с данными реального получателя.")}</p></div></aside></div>
    <div class="card"><div class="row"><h2>${T("Запланированные рассылки")}</h2></div><div id="bc-sch" class="scroll-x"></div></div>
    <div class="card"><div class="row"><h2>${T("История рассылок")}</h2></div><div id="bc-list" class="scroll-x"></div></div>`;
  const body = () => ({ audience: spec, text_ru: $("#bc-ru").value, text_uz: $("#bc-uz").value });
  const bubble = t => `<div class="bcmsg">${String(t).replace(/\n/g, "<br>")}</div>`;
  // the counter that follows the choice of the people, and the message as one of them will see it
  let timer;
  const countNow = async () => {
    try { const r = await api("/api/broadcasts/audience", { method: "POST", body: { audience: spec } }); if (!$("#bc-count")) return;
      const unl = (r.unlinked_heads || []).length ? `<details class="inl warn"><summary>${T("Руководителей без подключения: {n}", { n: r.unlinked_heads.length })}</summary><p class="sm">${T("Они получат рассылку, когда напишут боту /start и отправят свой номер телефона кнопкой.")}</p><ul class="sm">${r.unlinked_heads.map(x => `<li>${esc(rname(x.region))}: ${esc(x.fio)}${x.phone ? ", " + esc(showPhones(x.phone)) : ""}</li>`).join("")}</ul></details>` : "";
      $("#bc-count").innerHTML = r.total ? `<b>${T("Получателей: {n}", { n: r.total })}</b> <span class="muted">${T("(по-узбекски {uz}, по-русски {ru})", { uz: r.uz, ru: r.ru })}</span> <details class="inl"><summary>${T("кто")}</summary><p class="sm">${r.list.map(x => esc(x.name)).join(", ")}${r.total > r.list.length ? "…" : ""}</p></details>${unl}` : `<span class="err">${T("Получателей нет: никто не подходит под выбор.")}</span>${unl}`; }
    catch (e) { if ($("#bc-count")) $("#bc-count").innerHTML = `<span class="err">${esc(e.message)}</span>`; }
  };
  const prevNow = async () => {
    if (!$("#bc-ru").value.trim() && !$("#bc-uz").value.trim()) { $("#bc-prev").innerHTML = `<p class="muted sm">${T("Напишите текст: здесь появится сообщение с данными реального получателя.")}</p>`; $("#bc-who").hidden = true; return; }
    try { const r = await api("/api/broadcasts/preview", { method: "POST", body: { ...body(), sample_tg_id: sample } }); if (!$("#bc-prev")) return;
      const who = $("#bc-who"); who.hidden = !r.list.length; who.innerHTML = r.list.map(x => `<option value="${x.tg_id}" ${r.sample && x.tg_id === r.sample.tg_id ? "selected" : ""}>${esc(x.name)} (${x.lang === "uz" ? "UZ" : "RU"})</option>`).join("");
      $("#bc-prev").innerHTML = r.sample ? bubble(r.sample.text) + (r.fallback ? `<p class="muted sm">${T("У {n} человек язык, на котором вы ничего не написали: они получат текст на другом языке.", { n: r.fallback })}</p>` : "") : `<p class="muted sm">${T("Получателей нет.")}</p>`; }
    catch (e) { if ($("#bc-prev")) $("#bc-prev").innerHTML = `<p class="err sm">${esc(e.message)}</p>`; }
  };
  const later = fn => { clearTimeout(timer); timer = setTimeout(fn, 400); };
  $("#bc-who").onchange = () => { sample = $("#bc-who").value; prevNow(); };
  // the people
  const setSeg = (id, v) => $(id).querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === v));
  const roleHint = () => { $("#bc-role-hint").textContent = { all: "", heads: T("Руководитель региона: основной человек из списка региона (один на регион), подтверждённый номером телефона в боте."), responsibles: T("Ответственные: все остальные, у кого есть доступ к региону или к учреждению.") }[spec.roles]; };
  $("#bc-roles").onclick = e => { const b = e.target.closest("[data-v]"); if (!b) return; spec.roles = b.dataset.v; setSeg("#bc-roles", spec.roles); roleHint(); countNow(); sample = ""; prevNow(); };
  $("#bc-report").onclick = e => { const b = e.target.closest("[data-v]"); if (!b) return; spec.report = b.dataset.v; setSeg("#bc-report", spec.report); countNow(); sample = ""; prevNow(); };
  const drawRegs = () => $("#bc-regs").querySelectorAll(".chip").forEach(b => b.classList.toggle("on", b.dataset.r === "all" ? !spec.regions.length : spec.regions.includes(+b.dataset.r)));
  $("#bc-regs").onclick = e => { const b = e.target.closest("[data-r]"); if (!b) return; if (b.dataset.r === "all") spec.regions = []; else { const id = +b.dataset.r; spec.regions = spec.regions.includes(id) ? spec.regions.filter(x => x !== id) : [...spec.regions, id]; } drawRegs(); countNow(); sample = ""; prevNow(); };
  const setAud = a => { spec = normAud(a); roleHint(); setSeg("#bc-roles", spec.roles); setSeg("#bc-report", spec.report); drawRegs(); countNow(); };
  // the text
  ["uz", "ru"].forEach(l => { const ta = $("#bc-" + l); ta.onfocus = () => { lastTa = ta; }; ta.oninput = () => { $("#bc-" + l + "-n").textContent = ta.value.length + " / 3500"; later(prevNow); }; });
  const phBox = () => { $("#bc-ph").innerHTML = (phs.length ? phs : Object.keys(PH)).map(k => `<button class="chip" data-p="${k}" title="${esc(PH[k] || k)}">{${k}}</button>`).join(""); };
  $("#bc-ph").onclick = e => { const b = e.target.closest("[data-p]"); if (!b) return; const ta = lastTa || $("#bc-uz"), ins = `{${b.dataset.p}}`, p = ta.selectionStart ?? ta.value.length;
    ta.value = ta.value.slice(0, p) + ins + ta.value.slice(ta.selectionEnd ?? p); ta.focus(); ta.setSelectionRange(p + ins.length, p + ins.length); ta.dispatchEvent(new Event("input")); };
  const loadTpl = async (keep) => {
    try { const r = await api("/api/broadcast-templates"); tpls = r.items; phs = r.placeholders; } catch (e) { return fail(e); }
    if (!$("#bc-tpl")) return; phBox();
    const opt = x => `<option value="${x.id}" ${String(x.id) === String(keep) ? "selected" : ""}>${esc(x.builtin ? (LANG === "uz" ? x.name_uz : x.name_ru) : x.name)}</option>`;
    $("#bc-tpl").innerHTML = `<option value="">${T("— Шаблон текста —")}</option><optgroup label="${T("Готовые")}">${tpls.filter(x => x.builtin).map(opt).join("")}</optgroup>${tpls.some(x => !x.builtin) ? `<optgroup label="${T("Мои шаблоны")}">${tpls.filter(x => !x.builtin).map(opt).join("")}</optgroup>` : ""}`;
    $("#bc-tpl-del").hidden = !tpls.some(x => String(x.id) === String(keep) && !x.builtin);
  };
  $("#bc-tpl").onchange = () => { const x = tpls.find(t => String(t.id) === $("#bc-tpl").value); $("#bc-tpl-del").hidden = !x || x.builtin; if (!x) return;
    $("#bc-uz").value = x.text_uz; $("#bc-ru").value = x.text_ru; ["uz", "ru"].forEach(l => $("#bc-" + l + "-n").textContent = $("#bc-" + l).value.length + " / 3500"); setAud(x.audience); sample = ""; prevNow(); };
  $("#bc-tpl-save").onclick = () => { if (!$("#bc-ru").value.trim() && !$("#bc-uz").value.trim()) return toast(T("Сначала напишите текст"));
    modal(`<h2>${T("Сохранить как шаблон")}</h2><label>${T("Название")}<input id="tp-n" maxlength="80"></label><p class="muted sm">${T("Сохранятся тексты и выбор получателей.")}</p><div id="tp-err" class="err"></div><div class="row mt"><button class="btn pri" id="tp-ok">${T("Сохранить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
    $("#tp-ok").onclick = async () => { try { const r = await api("/api/broadcast-templates", { method: "POST", body: { ...body(), name: $("#tp-n").value } }); closeModal(); toast(T("Шаблон сохранён")); await loadTpl(r.id); } catch (e) { $("#tp-err").textContent = e.message; } }; };
  $("#bc-tpl-del").onclick = () => { const x = tpls.find(t => String(t.id) === $("#bc-tpl").value); if (!x || x.builtin) return;
    confirmDlg(T("Удалить шаблон"), `<p>${esc(x.name)}</p>`, T("Удалить"), async () => { await api("/api/broadcast-templates/" + x.id, { method: "DELETE" }); closeModal(); toast(T("Шаблон удалён")); await loadTpl(""); }); };
  // when
  $("#bc-when").onclick = e => { const b = e.target.closest("[data-v]"); if (!b) return; when = b.dataset.v; setSeg("#bc-when", when); $("#bc-sched").hidden = when !== "later"; $("#bc-go").textContent = when === "later" ? T("Поставить в расписание") : T("Предпросмотр и отправка"); };
  $("#bc-rep").onchange = () => { $("#bc-date-l").hidden = $("#bc-rep").value !== "once"; };
  $("#bc-test").onclick = async () => { try { const r = await api("/api/broadcasts/test", { method: "POST", body: { ...body(), tg_id: $("#bc-tid").value.trim() } }); toast(T("Тест отправлен (Telegram ID {id})", { id: r.sent_to })); } catch (e) { fail(e); } };
  $("#bc-go").onclick = async () => {
    let pv; try { pv = await api("/api/broadcasts/preview", { method: "POST", body: { ...body(), sample_tg_id: sample } }); } catch (e) { return fail(e); }
    const sch = when === "later" ? { repeat: $("#bc-rep").value, at_time: $("#bc-time").value, run_date: $("#bc-date").value, title: $("#bc-title").value } : null;
    modal(`<h2>${sch ? T("🕒 Проверьте расписание") : T("📢 Проверьте рассылку")}</h2><p>${T("Кому: <b>{aud}</b> · получателей: <b>{total}</b> (по-узбекски {uz}, по-русски {ru})", { aud: esc(audLabel(spec)), total: pv.total, uz: pv.uz, ru: pv.ru })}</p>
      ${sch ? `<p>${T("Когда: <b>{w}</b>", { w: esc(whenLabel(sch)) })}</p><div class="note">${T("Получатели и цифры в тексте будут взяты в момент отправки; сейчас показан пример по текущим данным.")}</div>` : ""}
      ${pv.fallback ? `<div class="note">${T("У {n} человек язык, на котором вы ничего не написали: они получат текст на другом языке.", { n: pv.fallback })}</div>` : ""}
      ${pv.total ? `<div class="bcsample"><div class="muted sm">${T("Пример: {name}", { name: esc(pv.sample.name) })}</div>${bubble(pv.sample.text)}</div>
      <details><summary>${T("Получатели ({n})", { n: pv.total })}</summary><p class="sm">${pv.people.map(esc).join(", ")}${pv.total > pv.people.length ? "…" : ""}</p></details>` : `<div class="alert critical">${T("Получателей нет.")}</div>`}
      <div class="row mt"><button class="btn pri" id="bc-ok" ${pv.total || sch ? "" : "disabled"}>${sch ? T("Поставить в расписание") : T("Отправить") + " " + (pv.total || "")}</button><button class="btn right" data-close>${T("Назад")}</button></div>`, true);
    const ok = $("#bc-ok"); if (ok) ok.onclick = async () => { ok.disabled = true;
      try { if (sch) { await api("/api/broadcast-schedules", { method: "POST", body: { ...body(), ...sch } }); closeModal(); toast(T("Рассылка поставлена в расписание")); schList(); }
        else { await api("/api/broadcasts", { method: "POST", body: { ...body(), confirm: true } }); closeModal(); toast(T("Рассылка запущена")); $("#bc-ru").value = $("#bc-uz").value = ""; prevNow(); list(); } }
      catch (e) { fail(e); ok.disabled = false; } };
  };
  // the broadcasts that go by themselves
  const schList = async () => {
    let r; try { r = await api("/api/broadcast-schedules"); } catch (e) { return fail(e); }
    if (!$("#bc-sch")) return;
    $("#bc-sch").innerHTML = r.items.length ? `<table><tr><th>${T("Название")}</th><th>${T("Когда")}</th><th>${T("Кому")}</th><th>${T("Текст")}</th><th>${T("Последний запуск")}</th><th></th></tr>${r.items.map(x => `<tr><td><b>${esc(x.title || "—")}</b> ${x.active ? `<span class="pill sent">${T("Включено")}</span>` : `<span class="pill">${T("Не действует")}</span>`}</td><td>${esc(whenLabel(x))}</td><td class="sm">${esc(audLabel(x.audience))}</td>
        <td class="sm" style="max-width:280px">${esc((x.text_uz || x.text_ru).slice(0, 90))}${(x.text_uz || x.text_ru).length > 90 ? "…" : ""}</td><td class="sm">${x.last_run_date ? esc(x.last_run_date) + (x.last_result ? ": " + esc(TS(x.last_result)) : "") : (x.last_result ? esc(TS(x.last_result)) : "—")}</td>
        <td class="row"><button class="btn sm" data-sa="${x.id}" data-v="${x.active ? 0 : 1}">${x.active ? T("Пауза") : T("Включить")}</button><button class="btn sm bad" data-sd="${x.id}">${T("Удалить")}</button></td></tr>`).join("")}</table>` : `<p class="muted">${T("Расписаний нет: выберите «По расписанию» в шаге 3.")}</p>`;
    $("#bc-sch").querySelectorAll("[data-sa]").forEach(b => b.onclick = async () => { try { await api(`/api/broadcast-schedules/${b.dataset.sa}/active`, { method: "POST", body: { active: b.dataset.v === "1" } }); schList(); } catch (e) { fail(e); } });
    $("#bc-sch").querySelectorAll("[data-sd]").forEach(b => b.onclick = () => confirmDlg(T("Удалить расписание"), `<p>${T("Рассылка больше не будет уходить по этому расписанию. Уже отправленные остаются в истории.")}</p>`, T("Удалить"), async () => { await api("/api/broadcast-schedules/" + b.dataset.sd, { method: "DELETE" }); closeModal(); schList(); }));
  };
  const STX = { sending: ["warning", T("Отправляется")], done: ["sent", T("Готово")], interrupted: ["critical", T("Прервана")] };
  const list = async () => {
    clearTimeout(BCPOLL);
    let r; try { r = await api("/api/broadcasts"); } catch (e) { return fail(e); }
    if (!$("#bc-list")) return;
    $("#bc-list").innerHTML = r.items.length ? `<table><tr><th>${T("Когда")}</th><th>${T("От кого")}</th><th>${T("Текст")}</th><th>${T("Кому")}</th><th>${T("Итог")}</th><th></th></tr>${r.items.map(b => { const a = JSON.parse(b.audience || "{}"), [cls, lbl] = STX[b.status] || ["", b.status]; const pct = b.total ? Math.round(100 * (b.sent + b.failed) / b.total) : 0;
      return `<tr><td>${esc(b.created_at)}</td><td>${esc(b.by_name)}</td><td class="sm" style="max-width:320px">${esc((b.text_uz || b.text_ru).slice(0, 110))}${(b.text_uz || b.text_ru).length > 110 ? "…" : ""}</td><td>${esc(audLabel(a))}</td>
        <td><span class="pill ${cls}">${lbl}</span> ${T("отправлено <b>{sent}</b> из {total}", { sent: b.sent, total: b.total })}${b.failed ? `, ${T("не доставлено <b>{n}</b>", { n: b.failed })}` : ""}${b.status === "sending" ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ""}</td>
        <td class="row">${b.failed ? `<button class="btn sm" data-fl="${b.id}">${T("Кому не дошло")}</button>` : ""}${(b.status === "interrupted" || (b.status === "done" && b.failed)) ? `<button class="btn sm" data-rs="${b.id}">${b.status === "interrupted" ? T("Продолжить") : T("Повторить")}</button>` : ""}</td></tr>`; }).join("")}</table>` : `<p class="muted">${T("Рассылок пока не было.")}</p>`;
    $("#bc-list").querySelectorAll("[data-rs]").forEach(b => b.onclick = async () => { try { await api(`/api/broadcasts/${b.dataset.rs}/resume`, { method: "POST", body: {} }); list(); } catch (e) { fail(e); } });
    $("#bc-list").querySelectorAll("[data-fl]").forEach(b => b.onclick = async () => { try { const f = await api(`/api/broadcasts/${b.dataset.fl}/failures`); modal(`<h2>${T("Не доставлено")}</h2><p class="muted sm">${T("Обычно человек остановил или заблокировал бота.")}</p><div class="scroll-x"><table><tr><th>${T("Кто")}</th><th>${T("Причина")}</th></tr>${f.items.map(x => `<tr><td>${esc(x.name || x.username || x.tg_id)} <span class="muted">${esc(x.tg_id)}</span></td><td class="sm">${esc(x.error)}</td></tr>`).join("")}</table></div><div class="row mt"><button class="btn right" data-close>${T("Закрыть")}</button></div>`); } catch (e) { fail(e); } });
    if (r.items.some(b => b.status === "sending")) BCPOLL = setTimeout(() => { if (location.hash.startsWith("#/broadcast")) list(); }, 2000);
  };
  list(); schList(); loadTpl(""); countNow();
}

// ---------- confidential messages of the facilities for the Ministry: one chat per Telegram profile (the super administrator only)
const MSG = { sel: null, q: "", only: false, region: "", drafts: {}, keepUnread: null };
// a date in Uzbek by hand (browsers without the full locale data print «2026 M11 22»): «25-noyabr, 2026» or «25.11»
const UZ_MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
const uzDate = (d, full) => isNaN(d) ? "" : full ? `${d.getDate()}-${UZ_MONTHS[d.getMonth()]}, ${d.getFullYear()}` : String(d.getDate()).padStart(2, "0") + "." + String(d.getMonth() + 1).padStart(2, "0");
const roleLabel = s => ["Главный администратор", "Администратор", "Просмотр"].includes(s) ? T(s) : s;      // the role label that the server gives as the name of an account without a name
async function messagesView() {
  const nav = NAVID;
  let items = [], unreadAll = 0;
  const dt = at => new Date(String(at).replace(" ", "T")), pad = n => String(n).padStart(2, "0");
  const hhmm = at => { const d = dt(at); return isNaN(d) ? "" : pad(d.getHours()) + ":" + pad(d.getMinutes()); };
  const dayKey = at => String(at).slice(0, 10);
  const dayLabel = at => { const k = dayKey(at), y = new Date(dt(ME.today + " 00:00").getTime() - 864e5), yk = `${y.getFullYear()}-${pad(y.getMonth() + 1)}-${pad(y.getDate())}`;
    return k === ME.today ? T("Сегодня") : k === yk ? T("Вчера") : LANG === "uz" ? uzDate(dt(at), true) : dt(at).toLocaleDateString(LOCALE, { day: "numeric", month: "long", year: "numeric" }); };
  const listTime = at => dayKey(at) === ME.today ? hhmm(at) : LANG === "uz" ? uzDate(dt(at), false) : dt(at).toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit" });
  const person = t => ({ tg_id: t.tg_id, first_name: t.name || "", last_name: "", username: t.username });
  const placeText = m => `${rname(m.region)} — ${m.facility}` + (m.report_date ? ` · ${T("отчёт за {d}", { d: m.report_date })}` : "");
  const cur = () => items.find(t => t.tg_id === MSG.sel);
  const shown = () => {
    const q = MSG.q.trim().toLowerCase();
    return items.filter(t => (!MSG.only || t.unread) && (!MSG.region || String(t.region_id) === MSG.region)
      && (!q || [t.name, t.username, t.tg_id, ...t.places.map(p => `${p.region} ${rname(p.region)} ${p.district} ${p.facility}`), ...t.messages.map(m => m.text)].join(" ").toLowerCase().includes(q)));
  };
  const setUnread = n => { ME.messages_unread = n; badgeMessages(); };
  const markRead = async (t, read) => {
    try { await api(`/api/messages/${t.thread_id}/read`, { method: "POST", body: { read } }); } catch (e) { return fail(e); }
    const was = t.unread; t.unread = read ? 0 : t.messages.filter(m => m.direction === "in").length; unreadAll += t.unread - was; setUnread(unreadAll); drawList(); drawChat(false);
  };
  const itemHtml = t => { const last = t.messages[t.messages.length - 1];
    return `<button class="mchat${t.tg_id === MSG.sel ? " on" : ""}${t.unread ? " unread" : ""}" data-c="${esc(t.tg_id)}">${tgAv(person(t))}
      <span class="mc-txt"><span class="mc-top"><b>${esc(t.name || T("Без имени"))}</b><span class="mc-time">${esc(listTime(t.last_at))}</span></span>
      <span class="mc-place">${esc(rname(t.region))} · ${esc(t.facility)}${t.places.length > 1 ? ` <i>+${t.places.length - 1}</i>` : ""}</span>
      <span class="mc-top"><span class="mc-last">${last.direction === "out" ? T("Вы: ") : ""}${esc(last.text.replace(/\s+/g, " "))}</span>${t.unread ? `<span class="pill critical">${t.unread}</span>` : ""}</span></span></button>`; };
  function drawList() {
    const box = $("#ml"); if (!box) return;
    const list = shown(), top = box.scrollTop;
    box.innerHTML = list.length ? list.map(itemHtml).join("") : `<p class="muted sm" style="padding:14px">${MSG.q || MSG.region || MSG.only ? T("Ничего не найдено.") : T("Сообщений пока нет. Люди могут оставить его последним вопросом бота.")}</p>`;
    box.scrollTop = top; dropBrokenAvatars(box);
    box.querySelectorAll("[data-c]").forEach(b => b.onclick = () => select(b.dataset.c));
  }
  const bubble = m => `<div class="bub ${m.direction === "out" ? "out" : "in"}"><div class="msgtext">${esc(m.text)}</div><div class="bubmeta">${m.direction === "out" ? T("Министерство") + (m.by ? " · " + esc(roleLabel(m.by)) : "") + " · " : ""}${esc(hhmm(m.at))}</div>${m.error ? `<div class="bubwarn">${T("⚠️ В Telegram не доставлено: {err}", { err: esc(TS(m.error)) })}</div>` : ""}</div>`;
  function drawChat(scroll = true) {
    const box = $("#mc"); if (!box) return;
    const t = cur(), wrap = $("#msgs");
    wrap.classList.toggle("has-chat", !!t);
    if (!t) { box.innerHTML = `<div class="mc-empty"><div style="font-size:42px">💬</div><p class="muted">${T("Выберите чат слева")}</p></div>`; return; }
    const keepDraft = MSG.drafts[t.tg_id] || "";
    let html = "", day = "", ctx = "";
    for (const m of t.messages) {
      if (dayKey(m.at) !== day) { day = dayKey(m.at); html += `<div class="mdate"><span>${esc(dayLabel(m.at))}</span></div>`; }
      const c = placeText(m); if (c !== ctx) { ctx = c; html += `<div class="mctx">📍 ${esc(c)}</div>`; }
      html += bubble(m);
    }
    box.innerHTML = `<div class="mc-head"><button class="btn sm mc-back" id="m-back">←</button>${tgAv(person(t))}<div class="mc-who"><b>${esc(t.name || T("Без имени"))}</b><div class="muted sm">${t.username ? "@" + esc(t.username) + " · " : ""}ID ${esc(t.tg_id)}</div></div>
        <div class="mc-act">${tgLink(person(t))}<button class="btn sm" id="m-unread">${t.unread ? T("Отметить прочитанным") : T("Отметить непрочитанным")}</button></div></div>
      <div class="mc-places">${t.places.map(p => `<span class="chip-s" title="${esc(p.district)}">${esc(rname(p.region))} — ${esc(p.facility)}</span>`).join("")}</div>
      <div class="mc-body" id="m-body"><div class="thread">${html}</div></div>
      <div class="replybox"><textarea rows="2" maxlength="1000" id="m-ta" placeholder="${T("Ответ получит {who} в Telegram с кнопкой «Ответить». Ctrl+Enter — отправить", { who: esc(t.name || T("учреждение")) })}">${esc(keepDraft)}</textarea><button class="btn pri" id="m-send">${T("Ответить")}</button></div>`;
    dropBrokenAvatars(box);
    const body = $("#m-body"); if (scroll) body.scrollTop = body.scrollHeight;
    const ta = $("#m-ta");
    ta.oninput = () => { MSG.drafts[t.tg_id] = ta.value; };
    const send = async () => { const text = ta.value.trim(); if (!text) return toast(T("Напишите ответ"));
      try { const x = await api(`/api/messages/${t.thread_id}/reply`, { method: "POST", body: { text } }); MSG.drafts[t.tg_id] = ""; toast(x.delivered ? T("Ответ отправлен") : T("Ответ сохранён, но Telegram его не принял: {err}", { err: TS(x.error) })); await load(true); } catch (e) { fail(e); } };
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
  view.innerHTML = `<div class="card msgcard-wrap"><div class="row"><h2>${T("Сообщения для Министерства")}</h2><span class="muted sm">${T("🔒 конфиденциально: видны только главному администратору; областные администраторы и просмотр их не видят, в выгрузки они не попадают")}</span></div>
    <div class="msgs" id="msgs"><div class="ml-col"><div class="ml-head"><input type="search" id="m-q" placeholder="${T("Поиск: имя, учреждение, текст…")}" value="${esc(MSG.q)}"><div class="row" style="gap:6px;flex-wrap:nowrap"><div class="seg" id="m-f"><button data-f="all">${T("Все")}</button><button data-f="unread">${T("Непрочитанные")}</button></div><select id="m-r" style="min-width:0;flex:1"><option value="">${T("Все области")}</option></select></div></div><div class="ml" id="ml"></div></div>
    <div class="mc" id="mc"></div></div></div>`;
  const seg = () => view.querySelectorAll("#m-f button").forEach(b => b.classList.toggle("on", (b.dataset.f === "unread") === MSG.only));
  seg();
  view.querySelectorAll("#m-f button").forEach(b => b.onclick = () => { MSG.only = b.dataset.f === "unread"; seg(); drawList(); });
  $("#m-q").oninput = e => { MSG.q = e.target.value; drawList(); };
  $("#m-r").onchange = e => { MSG.region = e.target.value; drawList(); };
  await load(true);
  const sel = $("#m-r"); if (sel) { const seen = new Map(items.map(t => [String(t.region_id), t.region])); sel.innerHTML = `<option value="">${T("Все области")}</option>` + [...seen].sort((a, b) => rname(a[1]).localeCompare(rname(b[1]), LANG)).map(([id, n]) => `<option value="${id}">${esc(rname(n))}</option>`).join(""); sel.value = MSG.region; }
}
function badgeProposals() { const a = document.querySelector('#tabs a[data-t="territories"]'); if (a) a.innerHTML = T("Территории") + (ME.proposals_new ? ` <span class="pill warning">${ME.proposals_new}</span>` : ""); }
function badgeMessages() { const a = document.querySelector('#tabs a[data-t="messages"]'); if (a) a.innerHTML = T("Сообщения") + (ME.messages_unread ? ` <span class="pill critical blink">${ME.messages_unread}</span>` : ""); }

// ---------- shell
// [name, label, page, right, group]: the pages of a group share one tab of the menu and a row of sub-tabs under it (SUBTABS lists them in the order of the row)
const TABS = [["dashboard", T("Панель"), dashboard, null], ["messages", T("Сообщения"), messagesView, "s"], ["forecast", T("Прогноз"), forecastView, null], ["reports", T("Отчёты"), reportsView, "w"], ["people", T("Доступы"), people, "u"],
  ["export", T("Выгрузка"), exportView, null], ["territories", T("Территории"), territories, "t", "territories"], ["editor", T("Редактор"), editorView, "t", "territories"], ["broadcast", T("Рассылка"), broadcastView, "u"],
  ["settings", T("Настройки"), settings, "s", "settings"], ["control", T("Контроль"), control, "w", "settings"], ["indicators", T("Вопросник"), indicators, "s", "settings"], ["audit", T("Журнал"), audit, "s"]];
const SUBTABS = { territories: [["territories", T("Учреждения")], ["editor", T("Редактор")]], settings: [["settings", T("Общие")], ["control", T("Контроль")], ["indicators", T("Вопросник")]] };
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
$("#pwbtn").onclick = () => { modal(`<h2>${T("Смена пароля")}</h2><label>${T("Текущий пароль")}<input type="password" id="o"></label><label>${T("Новый пароль (от 8 знаков)")}<input type="password" id="n"></label><div class="row mt"><button class="btn pri" id="ok">${T("Сменить")}</button><button class="btn right" data-close>${T("Отмена")}</button></div>`);
  $("#ok").onclick = async () => { try { await api("/api/me/password", { method: "POST", body: { old: $("#o").value, new: $("#n").value } }); closeModal(); toast(T("Пароль изменён")); } catch (e) { fail(e); } }; };
(async () => {
  try { ME = await api("/api/me"); META = await api("/api/meta"); } catch (e) { return; }
  $("#who").textContent = `${ME.name && ME.name !== ME.role_label ? ME.name : ME.login} · ${roleLabel(ME.role_label)}`;
  $("#tabs").innerHTML = menuTabs().map(t => `<a href="#/${t.href}" data-t="${t.name}">${t.label}</a>`).join("");
  window.addEventListener("hashchange", route); route(); badgeMessages(); badgeProposals();
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
      if (pl.proposals !== undefined && ME.proposals_new !== pl.proposals) { ME.proposals_new = pl.proposals; badgeProposals(); }
      if (last !== null && t !== last) {
        const name = (location.hash.slice(2) || "dashboard").split("?")[0];
        if (LIVE.includes(name) && idle()) {
          view.style.minHeight = view.offsetHeight + "px";   // keep the scroll position while the page is redrawn
          if (name === "dashboard") dashboard(true).catch(fail); else route();            // the dashboard is patched in place, the other pages are drawn again
          toast(T("Данные обновлены: получена новая сводка")); setTimeout(() => view.style.minHeight = "", 2500);
          last = t;
        }   // otherwise try again at the next beat: `last` stays old
      } else last = t;
    } catch (e) { /* offline or logged out: the next beat tries again */ }
    busy = false;
  };
  setInterval(tick, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
}
