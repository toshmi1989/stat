// Single-page interface. Rights are enforced by the server; the interface only hides what a role cannot use.
const $ = (s, r = document) => r.querySelector(s);
const view = $("#view");
let ME = null, META = null, DEB = null;
const NAMES = { visits: "Обращения", severe: "Тяжёлые", extreme: "Крайне тяжёлые", hosp: "Госпитализации", disch: "Выписки", beds_occupied: "Занято коек", occupancy: "Загрузка, %", beds_free: "Свободно коек", beds_flu: "Коек для гриппа" };
const STATE = { sent: "Отправлен", corrected: "Исправлен", returned: "Возвращён", not_sent: "Не отправлен", overdue: "Просрочен", normal: "Норма", elevated: "Повышенная", critical: "Критическая", none: "—" };

async function api(path, opt = {}) {
  const o = { method: opt.method || "GET", headers: {} };
  if (opt.body !== undefined) { o.body = JSON.stringify(opt.body); o.headers["Content-Type"] = "application/json"; }
  if (opt.form) o.body = opt.form;
  const r = await fetch(path, o);
  if (r.status === 401) { location.href = "/login"; throw new Error("auth"); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(j.error || "Ошибка " + r.status); e.details = j.details; throw e; }
  return j;
}
function toast(m) { const t = $("#toast"); t.textContent = m; t.style.display = "block"; clearTimeout(toast.t); toast.t = setTimeout(() => t.style.display = "none", 3500); }
const fail = e => { if (e.message !== "auth") toast(e.message); };
function qs(o) { return Object.entries(o).filter(([, v]) => v !== "" && v != null).map(([k, v]) => k + "=" + encodeURIComponent(v)).join("&"); }
const num = v => v == null ? "—" : (+v).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
function modal(html, wide) { $("#modal").innerHTML = `<div class="modal${wide ? " wide" : ""}">${html}</div>`; $("#modal").onclick = ev => { if (ev.target.id === "modal") closeModal(); }; }
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
const KPI = [["reported", "Сдали отчёт", t => `${t.reported} из ${t.facilities}`, null], ["not_reported", "Не сдали", t => t.not_reported, "bad"],
  ["visits", "Обращения"], ["severe", "Тяжёлые"], ["extreme", "Крайне тяжёлые"], ["sp", "Тяжёлые беременные / дети", t => `${num(t.totals.severe_pregnant)} / ${num(t.totals.severe_children)}`],
  ["hosp", "Госпитализации"], ["disch", "Выписки"], ["beds_flu", "Коек для гриппа"], ["beds_occupied", "Занято коек"], ["beds_free", "Свободно коек"], ["occupancy", "Загрузка коек", t => t.totals.occupancy == null ? "—" : num(t.totals.occupancy) + "%", "occ"]];
const SORT = { key: "visits", asc: false }, DRILL = [];
async function dashboard() {
  const fb = await filterBar(dashboard);
  view.innerHTML = fb.html + `<div id="dash"></div>`; fb.bind();
  const [d1, d2] = periodOf();
  const q = scopeQ() + (F.preset === "day" ? "&date=" + d1 : "");
  let dash;
  try { dash = await api("/api/dashboard?" + q.replace(/(^|&)d[12]=[^&]*/g, "").replace(/^&/, "") + (F.preset === "day" ? "" : "&d1=" + d1 + "&d2=" + d2)); } catch (e) { return fail(e); }
  const k = dash.kpis, th = ME.thresholds, t = k.totals;
  const kv = k.totals; k.facilities = k.facilities;
  const occState = kv.occupancy == null ? "" : kv.occupancy >= th.critical ? "critical" : kv.occupancy >= th.elevated ? "warning" : "";
  $("#dash").innerHTML = (dash.fallback ? `<div class="note">За ${esc(dash.requested)} данных пока нет, показан последний день с данными: ${esc(dash.used_date)}.</div>` : "") +
    `<div class="kpis">${KPI.map(([key, label, f, tone]) => {
      const val = f ? f(k) : num(t[key]); const cls = tone === "occ" ? occState : tone === "bad" && k.not_reported ? "warning" : "";
      return `<div class="kpi ${cls}"><div class="l">${label}</div><div class="v">${val}</div></div>`; }).join("")}</div>
    <div id="alerts"></div>
    <div class="card"><div class="row"><h2>Регионы</h2><input id="rt-q" placeholder="Поиск" class="right"></div><div class="scroll-x" id="rt"></div></div>
    <div class="grid2"><div class="card"><h3>Динамика</h3><div class="row"><div id="dyn-m"></div><label class="sm">Сравнить регионы <select id="dyn-r" multiple size="3">${META.regions.map(r => `<option value="${r.id}">${esc(r.name_ru)}</option>`).join("")}</select></label></div><div id="dyn"></div></div>
    <div class="card"><h3>Госпитализации и выписки</h3><div id="hd"></div></div></div>
    <div class="card"><h3>Баланс коек</h3><div class="scroll-x" id="beds"></div></div>`;
  api("/api/alerts").then(a => $("#alerts") && ($("#alerts").innerHTML = a.items.slice(0, 6).map(x => `<div class="alert ${x.level}">${esc(x.text)}</div>`).join("") + (a.items.length > 6 ? `<p class="muted sm">Ещё предупреждений: ${a.items.length - 6} (раздел «Прогноз»)</p>` : ""))).catch(fail);
  const [u1, u2] = dash.fallback ? [dash.used_date, dash.used_date] : [d1, d2];   // tables follow the day the KPI cards show
  loadTable(u1, u2); loadDyn(); loadHD(); loadBeds(u1, u2);
}
let METRICS = ["visits"];
function loadDyn() {
  const mEl = $("#dyn-m"); if (!mEl) return;
  mEl.innerHTML = ["visits", "severe", "extreme", "hosp", "disch"].map(m => `<label class="sm"><input type="checkbox" value="${m}" ${METRICS.includes(m) ? "checked" : ""}> ${NAMES[m]}</label> `).join("");
  const draw = async () => {
    const regions = [...$("#dyn-r").selectedOptions].map(o => o.value).join("");
    const [d1, d2] = periodOf(); const a = d2 === d1 ? addDays(d1, -13) : d1;
    try {
      const r = await api("/api/dynamics?" + qs({ d1: a, d2, metrics: METRICS.join(","), regions, region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id }));
      if (!$("#dyn")) return;
      $("#dyn").innerHTML = lineChart(r.dates, r.series.map(s => ({ name: s.name + (METRICS.length > 1 ? " — " + NAMES[s.metric] : ""), points: s.points })));
    } catch (e) { fail(e); }
  };
  mEl.onchange = () => { METRICS = [...mEl.querySelectorAll("input:checked")].map(i => i.value); if (!METRICS.length) METRICS = ["visits"]; draw(); };
  $("#dyn-r").onchange = draw; draw();
}
async function loadHD() {
  const [d1, d2] = periodOf(); const a = d2 === d1 ? addDays(d1, -13) : d1;
  try {
    const r = await api("/api/hosp-disch?" + qs({ d1: a, d2, region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id }));
    if (!$("#hd")) return;
    $("#hd").innerHTML = barChart(r.rows.map(x => x.date), [{ name: "Госпитализации", values: r.rows.map(x => x.hosp) }, { name: "Выписки", values: r.rows.map(x => x.disch) }]) +
      `<div class="scroll-x" style="max-height:200px;overflow:auto"><table><tr><th>Дата</th><th class="n">Госп.</th><th class="n">Выписки</th><th class="n">Разница</th><th class="n">Занято</th><th class="n">Изм.</th></tr>${r.rows.slice().reverse().map(x => `<tr><td>${x.date}</td><td class="n">${num(x.hosp)}</td><td class="n">${num(x.disch)}</td><td class="n">${num(x.diff)}</td><td class="n">${num(x.occupied)}</td><td class="n">${x.occ_change == null ? "—" : (x.occ_change > 0 ? "+" : "") + x.occ_change}</td></tr>`).join("")}</table></div>`;
  } catch (e) { fail(e); }
}
async function loadTable(d1, d2) {
  const level = DRILL.length === 0 ? "region" : DRILL.length === 1 ? "district" : "facility";
  const pid = DRILL.length ? DRILL[DRILL.length - 1].id : "";
  let r; try { r = await api("/api/regions-table?" + qs({ d1, d2, level, parent_id: pid })); } catch (e) { return fail(e); }
  if (!$("#rt-q")) return;   // the person has already left the dashboard
  const cols = [["name", "Название"], ["reported", "Отчётов"], ["visits", "Обращения"], ["severe", "Тяжёлые"], ["extreme", "Крайне тяж."], ["hosp", "Госп."], ["disch", "Выписки"], ["beds_flu", "Коек"], ["beds_occupied", "Занято"], ["beds_free", "Своб."], ["occupancy", "Загрузка"]];
  const draw = () => {
    const q = ($("#rt-q").value || "").toLowerCase();
    const val = (x, k) => k === "name" ? x.name : k === "reported" ? x.reported : x.values[k];
    const rows = r.rows.filter(x => x.name.toLowerCase().includes(q)).sort((a, b) => { const A = val(a, SORT.key), B = val(b, SORT.key); const c = typeof A === "string" ? A.localeCompare(B, "ru") : (A ?? -1) - (B ?? -1); return SORT.asc ? c : -c; });
    const crumbs = `<p class="sm"><a href="#" id="up0">Республика</a>${DRILL.map((d, i) => ` › <a href="#" data-up="${i}">${esc(d.name)}</a>`).join("")}</p>`;
    $("#rt").innerHTML = crumbs + `<table><tr>${cols.map(([k, l]) => `<th data-s="${k}" class="${k !== "name" ? "n " : ""}${SORT.key === k ? "on" + (SORT.asc ? " asc" : "") : ""}">${l}</th>`).join("")}</tr>${rows.map(x => `<tr class="${level !== "facility" ? "link" : ""}" data-id="${x.id}" data-name="${esc(x.name)}"><td>${esc(x.name)}</td><td class="n">${x.reported}/${x.facilities}</td>${cols.slice(2, 10).map(([k]) => `<td class="n">${num(x.values[k])}</td>`).join("")}<td class="n">${x.values.occupancy == null ? "—" : `<span class="pill ${x.level_state === "none" ? "" : x.level_state}">${num(x.values.occupancy)}%</span>`}</td></tr>`).join("")}</table>`;
    document.querySelectorAll("#rt th[data-s]").forEach(th => th.onclick = () => { SORT.asc = SORT.key === th.dataset.s ? !SORT.asc : false; SORT.key = th.dataset.s; draw(); });
    document.querySelectorAll("#rt tr.link").forEach(tr => tr.onclick = () => { DRILL.push({ id: tr.dataset.id, name: tr.dataset.name }); loadTable(d1, d2); });
    $("#up0").onclick = e => { e.preventDefault(); DRILL.length = 0; loadTable(d1, d2); };
    document.querySelectorAll("[data-up]").forEach(a => a.onclick = e => { e.preventDefault(); DRILL.length = +a.dataset.up + 1; loadTable(d1, d2); });
  };
  $("#rt-q").oninput = draw; draw();
}
async function loadBeds(d1, d2) {
  try {
    const r = await api("/api/beds?" + qs({ d1, d2 })); const th = r.thresholds;
    if (!$("#beds")) return;
    $("#beds").innerHTML = `<p class="muted sm">Пороги: повышенная нагрузка ≥ ${th.elevated}%, критическая ≥ ${th.critical}%, учреждение ≥ ${th.facility}%.</p><table><tr><th>Регион</th><th class="n">Коек для гриппа</th><th class="n">Занято</th><th class="n">Свободно</th><th class="n">Загрузка</th><th>Состояние</th></tr>${r.rows.map(x => `<tr><td>${esc(x.name)}</td><td class="n">${num(x.beds_flu)}</td><td class="n">${num(x.occupied)}</td><td class="n">${num(x.free)}</td><td class="n">${x.occupancy == null ? "—" : num(x.occupancy) + "%"}</td><td>${pill(x.state)}</td></tr>`).join("")}</table>` +
      (r.hot.length ? `<h3 class="mt">Учреждения с высокой загрузкой</h3><table><tr><th>Учреждение</th><th>Регион</th><th class="n">Загрузка</th><th class="n">Свободно</th></tr>${r.hot.map(x => `<tr><td>${esc(x.name)}</td><td>${esc(x.region)}${x.district === "Без района" ? "" : ", " + esc(x.district)}</td><td class="n"><span class="pill critical">${num(x.occupancy)}%</span></td><td class="n">${num(x.free)}</td></tr>`).join("")}</table>` : "");
  } catch (e) { fail(e); }
}

// ---------- forecast
async function forecastView() {
  const fb = await filterBar(forecastView, { noPeriod: true });
  view.innerHTML = fb.html + `<div id="fc" class="card">Загрузка…</div><div id="al" class="card"></div>`; fb.bind();
  try {
    const [fc, al] = await Promise.all([api("/api/forecast?" + qs({ region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id })), api("/api/alerts")]);
    const rel = { low: "critical", medium: "warning", high: "normal" };
    let h = `<h2>Прогноз на 3 и 7 дней</h2><p class="note">Это инструмент оперативного планирования, а не эпидемиологический вывод. Метод: ${esc(Object.values(fc.metrics)[0]?.method || "")}. Серая зона — 90% интервал.</p>`;
    for (const [code, m] of Object.entries(fc.metrics)) {
      h += `<h3>${NAMES[code]}</h3>`;
      if (!m.ok) { h += `<p class="muted">${esc(m.reliability_text)}</p>`; continue; }
      h += `<p>Последнее значение ${num(m.current)} (${m.current_date}). Через 3 дня: <b>${num(m.days[2].value)}</b> (${num(m.days[2].low)}–${num(m.days[2].high)}); через 7 дней: <b>${num(m.days[6].value)}</b> (${num(m.days[6].low)}–${num(m.days[6].high)}). Надёжность: <span class="pill ${rel[m.reliability]}">${esc(m.reliability_text)}</span></p>`;
    }
    if (fc.beds) {
      const b = fc.beds;
      h += `<h3>Прогноз загрузки коек</h3><p>Сейчас занято ${num(b.occupied)} из ${num(b.beds_flu)} (${b.current_date}). Надёжность: <span class="pill ${rel[b.reliability]}">${esc(b.reliability_text)}</span></p><p class="muted sm">${esc(b.method)}</p>` +
        lineChart(b.days.map(d => d.date), [{ name: "Занято коек", points: b.days.map(d => d.occupied), dashed: true }, { name: "Коек для гриппа", points: b.days.map(() => b.beds_flu), color: "#d64545" }]) +
        `<table><tr><th>Дата</th><th class="n">Занято</th><th class="n">Свободно</th><th class="n">Загрузка</th><th class="n">Дефицит</th></tr>${b.days.map(d => `<tr><td>${d.date}</td><td class="n">${num(d.occupied)}</td><td class="n">${num(d.free)}</td><td class="n">${num(d.occupancy)}%</td><td class="n">${d.deficit ? `<span class="pill critical">${num(d.deficit)}</span>` : "—"}</td></tr>`).join("")}</table>`;
    } else h += `<p class="muted">Прогноз коек недоступен: нужны данные о госпитализациях, выписках и коечном фонде.</p>`;
    $("#fc").innerHTML = h;
    $("#al").innerHTML = `<h2>Предупреждения</h2>` + (al.items.length ? al.items.map(x => `<div class="alert ${x.level}">${esc(x.text)}</div>`).join("") : `<p class="muted">Предупреждений нет.</p>`);
  } catch (e) { fail(e); }
}

// ---------- control table
async function control() {
  const fb = await filterBar(control, { noPeriod: true });
  view.innerHTML = fb.html + `<div class="row"><label>Дата <input type="date" id="c-d" value="${F.d1 || ME.today}"></label><div class="seg" id="c-f"></div></div><div id="ct" class="card">Загрузка…</div>`; fb.bind();
  $("#c-d").onchange = e => { F.d1 = e.target.value; control(); };
  try {
    const r = await api("/api/control?" + qs({ date: F.d1 || ME.today, region_id: F.region_id, district_id: F.district_id, facility_id: F.facility_id })); const c = r.counts;
    let filt = control.filter || "";
    const draw = () => {
      const rows = r.rows.filter(x => !filt || (filt === "noresp" ? !x.has_responsible : x.state === filt));
      $("#ct").innerHTML = `<p>Срок сдачи: <b>${r.deadline}</b>. Всего ${c.total}; сдали ${c.sent} (из них исправлено ${c.corrected}); возвращено ${c.returned}; не сдали ${c.not_sent + c.overdue}; без ответственного: ${c.no_responsible}.</p>
      <div class="scroll-x"><table><tr><th>Регион</th><th>Район</th><th>Учреждение</th><th>Ответственный</th><th>Статус</th><th>Время</th></tr>${rows.map(x => `<tr ${x.report_id ? `class="link" data-rep="${x.report_id}"` : ""}><td>${esc(x.region)}</td><td>${esc(x.district)}</td><td>${esc(x.facility)}</td><td>${x.has_responsible ? esc(x.responsible) : '<span class="muted">не назначен</span>'}</td><td>${pill(x.state)}${x.late ? ' <span class="pill warning">поздно</span>' : ""}</td><td>${x.time}</td></tr>`).join("")}</table></div>`;
      document.querySelectorAll("#ct tr[data-rep]").forEach(tr => tr.onclick = () => openReport(+tr.dataset.rep));
    };
    $("#c-f").innerHTML = [["", "Все"], ["sent", "Сдали"], ["corrected", "Исправлены"], ["returned", "Возвращены"], ["not_sent", "Не сдали"], ["overdue", "Просрочены"], ["noresp", "Без ответственного"]].map(([k, l]) => `<button data-v="${k}" class="${filt === k ? "on" : ""}">${l}</button>`).join("");
    document.querySelectorAll("#c-f button").forEach(b => b.onclick = () => { control.filter = b.dataset.v; filt = b.dataset.v; document.querySelectorAll("#c-f button").forEach(x => x.classList.toggle("on", x === b)); draw(); });
    draw();
  } catch (e) { fail(e); }
}

// ---------- reports
async function reportsView() {
  if (F.preset === "day" && !F.d1) F.preset = "week";   // a single empty day is a useless first view of the list
  const fb = await filterBar(reportsView);
  view.innerHTML = fb.html + `<div class="card"><div class="row"><h2>Отчёты</h2><select id="r-st"><option value="">Все</option><option value="sent">Отправленные</option><option value="returned">Возвращённые</option><option value="corrected">Исправленные</option><option value="late">С опозданием</option></select><input id="r-q" placeholder="Поиск по учреждению"><button class="btn pri right" id="r-new">+ Внести отчёт</button></div><div id="rl" class="scroll-x"></div></div>`; fb.bind();
  $("#r-new").onclick = () => editReport(null);
  if (!ME.can_edit_reports) $("#r-new").hidden = true;
  const load = async () => {
    try {
      const r = await api("/api/reports?" + scopeQ() + "&" + qs({ status: $("#r-st").value, q: $("#r-q").value, size: 200 }));
      $("#rl").innerHTML = `<p class="muted sm">Найдено: ${r.total}</p><table><tr><th>Дата</th><th>Регион</th><th>Район</th><th>Учреждение</th><th>Статус</th><th>Версия</th><th>Кто</th></tr>${r.items.map(x => `<tr class="link" data-id="${x.id}"><td>${x.report_date}</td><td>${esc(x.region)}</td><td>${esc(x.district)}</td><td>${esc(x.facility)}</td><td>${pill(x.status === "returned" ? "returned" : x.corrected ? "corrected" : "sent")}${x.late ? ' <span class="pill warning">поздно</span>' : ""}${x.locked ? " 🔒" : ""}</td><td>${x.version}</td><td>${esc(x.submitted_by)}</td></tr>`).join("")}</table>`;
      document.querySelectorAll("#rl tr[data-id]").forEach(tr => tr.onclick = () => openReport(+tr.dataset.id));
    } catch (e) { fail(e); }
  };
  $("#r-st").onchange = load; $("#r-q").oninput = () => { clearTimeout(DEB); DEB = setTimeout(load, 300); }; load();
}
async function openReport(id) {
  let r; try { r = await api("/api/reports/" + id); } catch (e) { return fail(e); }
  const ind = META.indicators.filter(i => i.active);
  modal(`<h2>${esc(r.facility)}</h2><p class="muted">${esc(r.region)}, ${esc(r.district)} · за ${r.report_date} · версия ${r.version} · ${pill(r.status === "returned" ? "returned" : r.corrected ? "corrected" : "sent")}${r.late ? " поздно" : ""}${r.locked_now ? " 🔒 закрыт" : ""}</p>
  ${r.return_reason ? `<div class="note">Возвращён: ${esc(r.return_reason)}</div>` : ""}
  <table>${ind.map(i => `<tr><td>${esc(i.name_ru)}</td><td class="n"><b>${num(r.values[i.code])}</b></td></tr>`).join("")}</table>
  <div class="row mt">${ME.can_edit_reports ? '<button class="btn pri" id="m-ed">Исправить</button><button class="btn" id="m-ret">Вернуть на исправление</button>' : ""}<button class="btn" id="m-lock">${r.locked ? "Открыть" : "Закрыть"} для правок</button><button class="btn right" onclick="closeModal()">Закрыть окно</button></div>
  <h3 class="mt">История версий</h3><div class="scroll-x"><table><tr><th>Версия</th><th>Когда</th><th>Кто</th><th>Действие</th><th>Причина</th><th>Что изменено</th><th></th></tr>${r.versions.map(v => `<tr><td>${v.version}</td><td>${esc(v.at || v.created_at || "")}</td><td>${esc(v.by_name || v.by || "")}</td><td>${esc(v.action)}</td><td>${esc(v.reason || "")}</td><td class="sm">${Object.entries(v.changes || {}).map(([k, c]) => `${esc(k)}: ${c[0] ?? "—"} → ${c[1] ?? "—"}`).join("<br>")}</td><td>${ME.can_edit_reports && v.version !== r.version ? `<button class="btn sm" data-restore="${v.version}">Вернуть</button>` : ""}</td></tr>`).join("")}</table></div>`, true);
  const ed = $("#m-ed"); if (ed) ed.onclick = () => editReport(r);
  const rt = $("#m-ret"); if (rt) rt.onclick = async () => { const reason = prompt("Причина возврата:"); if (!reason) return; try { await api(`/api/reports/${id}/return`, { method: "POST", body: { reason } }); toast("Отчёт возвращён"); closeModal(); route(); } catch (e) { fail(e); } };
  $("#m-lock").onclick = async () => { try { await api(`/api/reports/${id}/lock`, { method: "POST", body: { locked: !r.locked } }); toast("Готово"); openReport(id); } catch (e) { fail(e); } };
  document.querySelectorAll("[data-restore]").forEach(b => b.onclick = async () => { const reason = prompt("Причина восстановления версии " + b.dataset.restore + ":"); if (!reason) return; try { await api(`/api/reports/${id}/restore`, { method: "POST", body: { version: +b.dataset.restore, reason } }); toast("Версия восстановлена (создана новая)"); openReport(id); } catch (e) { fail(e); } });
}
async function editReport(r) {
  const ind = META.indicators.filter(i => i.active);
  let facs = [];
  if (!r) { try { facs = (await api("/api/facilities?" + qs({ region_id: F.region_id, district_id: F.district_id, size: 200 }))).items; } catch (e) { return fail(e); } }
  modal(`<h2>${r ? "Исправление отчёта" : "Внести отчёт"}</h2>
  ${r ? "" : `<label>Учреждение<select id="e-f">${facs.map(f => `<option value="${f.id}">${esc(f.region)} — ${esc(f.district)} — ${esc(f.name_ru)}</option>`).join("")}</select></label><label>Дата<input type="date" id="e-d" value="${ME.today}"></label>`}
  <div class="fields">${ind.map(i => `<label>${esc(i.name_ru)}<input type="number" min="0" step="1" data-code="${i.code}" value="${r ? (r.values[i.code] ?? "") : ""}"></label>`).join("")}</div>
  <label>Причина изменения (обязательно для журнала)<textarea id="e-reason" rows="2"></textarea></label><div id="e-msg"></div>
  <div class="row mt"><button class="btn pri" id="e-save">Сохранить</button><button class="btn" id="e-chk">Проверить</button><button class="btn right" onclick="closeModal()">Отмена</button></div>`, true);
  const vals = () => Object.fromEntries([...document.querySelectorAll("[data-code]")].filter(i => i.value !== "").map(i => [i.dataset.code, +i.value]));
  const ctx = () => ({ facility_id: r ? r.facility_id : +$("#e-f").value, date: r ? r.report_date : $("#e-d").value });
  const show = v => $("#e-msg").innerHTML = v.errors.map(x => `<div class="alert critical">${esc(x)}</div>`).join("") + v.warnings.map(x => `<div class="alert">${esc(x)}</div>`).join("");
  $("#e-chk").onclick = async () => { try { show(await api("/api/validate", { method: "POST", body: { values: vals(), ...ctx() } })); } catch (e) { fail(e); } };
  $("#e-save").onclick = async () => {
    try { await api("/api/reports", { method: "PUT", body: { values: vals(), reason: $("#e-reason").value, ...ctx() } }); toast("Сохранено"); closeModal(); route(); }
    catch (e) { if (e.details) show({ errors: e.details.errors || [], warnings: e.details.warnings || [] }); fail(e); }
  };
}

// ---------- people (Telegram users, requests, staff)
async function people() {
  view.innerHTML = `<div class="card"><div class="row"><h2>Заявки на доступ</h2></div><div id="rq" class="scroll-x"></div></div><div class="card"><div class="row"><h2>Ответственные (Telegram)</h2><button class="btn pri right" id="tg-add">+ Добавить</button></div><div id="tgl" class="scroll-x"></div></div><div id="staffbox"></div>`;
  const loadReq = async () => { try { const r = await api("/api/requests?status=pending");
    $("#rq").innerHTML = r.items.length ? `<table><tr><th>Дата</th><th>Telegram</th><th>Учреждение</th><th></th></tr>${r.items.map(x => `<tr><td>${esc(x.created_at)}</td><td>${esc(x.name || x.tg_id)} <span class="muted">${esc(x.tg_id)}</span></td><td><b>${esc(x.region)}</b>${x.district ? " — " + esc(x.district) : ""}${x.facility ? " — " + esc(x.facility) : ' <span class="pill">весь регион</span>'}</td><td class="row"><button class="btn sm pri" data-ap="${x.id}">Одобрить</button><button class="btn sm bad" data-no="${x.id}">Отклонить</button></td></tr>`).join("")}</table>` : `<p class="muted">Новых заявок нет.</p>`;
    document.querySelectorAll("[data-ap]").forEach(b => b.onclick = () => decide(+b.dataset.ap, true)); document.querySelectorAll("[data-no]").forEach(b => b.onclick = () => decide(+b.dataset.no, false)); } catch (e) { fail(e); } };
  const decide = async (id, approve) => { const note = approve ? "" : prompt("Причина отказа (увидит заявитель):") ?? null; if (note === null) return; try { await api(`/api/requests/${id}/decide`, { method: "POST", body: { approve, note } }); loadReq(); loadTg(); } catch (e) { fail(e); } };
  const loadTg = async () => { try { const r = await api("/api/tg-users");
    $("#tgl").innerHTML = `<table><tr><th>Пользователь</th><th>Telegram ID</th><th>Доступ</th><th></th></tr>${r.items.map(u => `<tr><td>${esc([u.first_name, u.last_name].filter(Boolean).join(" ") || "—")} ${u.username ? "@" + esc(u.username) : ""}${u.active ? "" : ' <span class="pill critical">отключён</span>'}</td><td>${esc(u.tg_id)}</td><td>${u.regions.map(a => `<b>${esc(a.region)}</b> — весь регион${a.kind === "reserve" ? " (резерв)" : ""} <a href="#" data-unr="${a.id}">✕</a>`).join("<br>")}${u.regions.length && u.assignments.length ? "<br>" : ""}${u.assignments.map(a => `${esc(a.facility)} (${a.kind === "reserve" ? "резерв" : "основной"}) <a href="#" data-un="${a.id}">✕</a>`).join("<br>")}</td><td class="row"><button class="btn sm" data-as="${u.tg_id}">Назначить</button><button class="btn sm" data-tog="${u.tg_id}" data-a="${u.active}">${u.active ? "Отключить" : "Включить"}</button></td></tr>`).join("")}</table>`;
    document.querySelectorAll("[data-un]").forEach(a => a.onclick = async e => { e.preventDefault(); if (!confirm("Снять назначение?")) return; try { await api("/api/assignments/" + a.dataset.un, { method: "DELETE" }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-unr]").forEach(a => a.onclick = async e => { e.preventDefault(); if (!confirm("Снять доступ к региону?")) return; try { await api("/api/region-access/" + a.dataset.unr, { method: "DELETE" }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-tog]").forEach(b => b.onclick = async () => { try { await api("/api/tg-users/" + b.dataset.tog, { method: "PATCH", body: { active: b.dataset.a !== "1" } }); loadTg(); } catch (x) { fail(x); } });
    document.querySelectorAll("[data-as]").forEach(b => b.onclick = () => assignDlg(b.dataset.as, loadTg)); } catch (e) { fail(e); } };
  $("#tg-add").onclick = () => assignDlg("", loadTg);
  loadReq(); loadTg();
  if (ME.role === "super_admin") staffBox();
}
async function assignDlg(tg, done) {
  modal(`<h2>Назначить ответственного</h2>${tg ? "" : `<label>Telegram ID<input id="a-id" inputmode="numeric"></label><label>Имя<input id="a-n"></label>`}
  <label>Регион<select id="a-r">${opts(META.regions, "", "—")}</select></label><label>Район (необязательно)<select id="a-d" disabled></select></label><label>Учреждение (необязательно; если пусто — доступ ко всему региону)<select id="a-f" disabled></select></label>
  <label>Тип<select id="a-k"><option value="primary">Основной</option><option value="reserve">Резервный</option></select></label><label>ФИО (для отчётов)<input id="a-fio"></label>
  <div class="row mt"><button class="btn pri" id="a-ok">Сохранить</button><button class="btn right" onclick="closeModal()">Отмена</button></div>`);
  $("#a-r").onchange = async e => { const d = await api("/api/districts?region_id=" + e.target.value); $("#a-d").innerHTML = opts(d.items, "", "—"); $("#a-d").disabled = false; $("#a-f").disabled = true; };
  $("#a-d").onchange = async e => { const f = await api("/api/facilities?" + qs({ district_id: e.target.value, size: 200 })); $("#a-f").innerHTML = opts(f.items, "", "—"); $("#a-f").disabled = false; };
  $("#a-ok").onclick = async () => { if (!+$("#a-r").value) return toast("Выберите регион"); const body = { tg_id: tg || $("#a-id").value.trim(), name: tg ? "" : $("#a-n").value, facility_id: +$("#a-f").value || 0, region_id: +$("#a-r").value || 0, kind: $("#a-k").value, fio: $("#a-fio").value };
    try { if (tg) await api("/api/assignments", { method: "POST", body }); else await api("/api/tg-users", { method: "POST", body }); closeModal(); toast("Сохранено"); done(); } catch (e) { fail(e); } };
}
async function staffBox() {
  const [st] = await Promise.all([api("/api/staff")]);
  $("#staffbox").innerHTML = `<div class="card"><div class="row"><h2>Пользователи панели</h2><button class="btn pri right" id="st-add">+ Добавить</button></div><div class="scroll-x"><table><tr><th>Логин</th><th>Имя</th><th>Роль</th><th>Регионы</th><th></th></tr>${st.items.map(s => `<tr><td>${esc(s.login)}${s.active ? "" : ' <span class="pill critical">отключён</span>'}</td><td>${esc(s.name)}</td><td>${esc({ super_admin: "Главный администратор", admin: "Администратор", viewer: "Просмотр" }[s.role])}</td><td>${s.role === "super_admin" || !s.regions.length ? "все" : s.regions.map(id => esc(META.regions.find(r => r.id === id)?.name_ru || id)).join(", ")}</td><td class="row"><button class="btn sm" data-ed="${s.id}">Изменить</button><button class="btn sm" data-pw="${s.id}">Сбросить пароль</button></td></tr>`).join("")}</table></div></div>`;
  const form = s => modal(`<h2>${s ? "Изменить" : "Новый пользователь"}</h2>${s ? "" : `<label>Логин<input id="s-l"></label>`}<label>Имя<input id="s-n" value="${esc(s?.name || "")}"></label>
    <label>Роль<select id="s-r">${[["viewer", "Просмотр"], ["admin", "Администратор"], ["super_admin", "Главный администратор"]].map(([k, l]) => `<option value="${k}" ${s?.role === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    <label>Регионы (пусто = все; для администратора регионального уровня выберите свои)<select id="s-reg" multiple size="6">${META.regions.map(r => `<option value="${r.id}" ${s?.regions.includes(r.id) ? "selected" : ""}>${esc(r.name_ru)}</option>`).join("")}</select></label>
    <label>Telegram ID (для сводок)<input id="s-tg" value="${esc(s?.tg_id || "")}"></label>
    <label><input type="checkbox" id="s-mu" ${s?.can_manage_users ? "checked" : ""} style="width:auto"> Может управлять доступами</label><label><input type="checkbox" id="s-er" ${s ? (s.can_edit_reports ? "checked" : "") : "checked"} style="width:auto"> Может исправлять отчёты</label>
    ${s ? `<label><input type="checkbox" id="s-ac" ${s.active ? "checked" : ""} style="width:auto"> Активен</label>` : ""}
    <div class="row mt"><button class="btn pri" id="s-ok">Сохранить</button><button class="btn right" onclick="closeModal()">Отмена</button></div>`);
  const body = s => ({ name: $("#s-n").value, role: $("#s-r").value, regions: [...$("#s-reg").selectedOptions].map(o => +o.value), tg_id: $("#s-tg").value, can_manage_users: $("#s-mu").checked, can_edit_reports: $("#s-er").checked, ...(s ? { active: $("#s-ac").checked } : { login: $("#s-l").value }) });
  $("#st-add").onclick = () => { form(null); $("#s-ok").onclick = async () => { try { const r = await api("/api/staff", { method: "POST", body: body(null) }); modal(`<h2>Пользователь создан</h2><p>Пароль (показывается один раз):</p><p><b id="pwv">${esc(r.password || "задан вручную")}</b></p><button class="btn pri" onclick="closeModal();people()">Готово</button>`); } catch (e) { fail(e); } }; };
  document.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => { const s = st.items.find(x => x.id === +b.dataset.ed); form(s); $("#s-ok").onclick = async () => { try { await api("/api/staff/" + s.id, { method: "PATCH", body: body(s) }); closeModal(); people(); } catch (e) { fail(e); } }; });
  document.querySelectorAll("[data-pw]").forEach(b => b.onclick = async () => { if (!confirm("Сгенерировать новый пароль?")) return; try { const r = await api(`/api/staff/${b.dataset.pw}/password`, { method: "POST", body: {} }); modal(`<h2>Новый пароль</h2><p><b id="pwv">${esc(r.password)}</b></p><button class="btn pri" onclick="closeModal()">Готово</button>`); } catch (e) { fail(e); } });
}

// ---------- territories
async function territories() {
  view.innerHTML = `<div class="card"><div class="row"><h2>Территории</h2><button class="btn right" id="t-rep">Загрузить данные из Excel (учреждения и показатели за 2 дня)</button><button class="btn" id="t-imp">Импорт территорий</button><button class="btn pri" id="t-add">+ Регион</button></div><div id="tt"></div></div>`;
  const load = async () => {
    META = await api("/api/meta");
    $("#tt").innerHTML = `<table><tr><th>Регион</th><th>Название (узб.)</th><th></th></tr>${META.regions.map(r => `<tr class="link" data-id="${r.id}"><td>${esc(r.name_ru)}${r.active ? "" : ' <span class="pill critical">отключён</span>'}</td><td>${esc(r.name_uz)}</td><td><button class="btn sm" data-er="${r.id}">Изменить</button></td></tr>`).join("")}</table><div id="tsub"></div>`;
    document.querySelectorAll("#tt tr[data-id]").forEach(tr => tr.onclick = ev => { if (ev.target.dataset.er) return; subList(+tr.dataset.id); });
    document.querySelectorAll("[data-er]").forEach(b => b.onclick = () => nameDlg("regions", META.regions.find(r => r.id === +b.dataset.er), load));
  };
  const subList = async rid => {
    const d = await api("/api/districts?region_id=" + rid);
    $("#tsub").innerHTML = `<h3 class="mt">Районы <button class="btn sm" id="d-add">+ Район</button></h3><table><tr><th>Район</th><th></th></tr>${d.items.map(x => `<tr><td>${esc(x.name_ru)}${x.active ? "" : " (отключён)"}</td><td><button class="btn sm" data-ed="${x.id}">Изменить</button> <button class="btn sm" data-fl="${x.id}">Учреждения</button></td></tr>`).join("")}</table><div id="tfac"></div>`;
    $("#d-add").onclick = () => nameDlg("districts", { region_id: rid }, () => subList(rid), true);
    document.querySelectorAll("[data-ed]").forEach(b => b.onclick = () => nameDlg("districts", d.items.find(x => x.id === +b.dataset.ed), () => subList(rid)));
    document.querySelectorAll("[data-fl]").forEach(b => b.onclick = () => facList(+b.dataset.fl));
  };
  const facList = async did => {
    const f = await api("/api/facilities?" + qs({ district_id: did, size: 200 }));
    $("#tfac").innerHTML = `<h3 class="mt">Учреждения <button class="btn sm" id="f-add">+ Учреждение</button></h3><table><tr><th>Учреждение</th><th>Ответственные</th><th></th></tr>${f.items.map(x => `<tr><td>${esc(x.name_ru)}${x.active ? "" : " (отключено)"}</td><td>${x.assignments.map(a => esc(a.fio || a.first_name || a.tg_id) + (a.kind === "reserve" ? " (резерв)" : "")).join(", ") || '<span class="muted">нет</span>'}</td><td><button class="btn sm" data-ef="${x.id}">Изменить</button></td></tr>`).join("")}</table>`;
    $("#f-add").onclick = () => nameDlg("facilities", { district_id: did }, () => facList(did), true);
    document.querySelectorAll("[data-ef]").forEach(b => b.onclick = () => nameDlg("facilities", f.items.find(x => x.id === +b.dataset.ef), () => facList(did)));
  };
  $("#t-add").onclick = () => nameDlg("regions", {}, load, true);
  $("#t-imp").onclick = () => importDlg(load);
  $("#t-rep").onclick = () => reportImportDlg(load);
  load();
}
function nameDlg(kind, o, done, isNew) {
  modal(`<h2>${isNew ? "Добавить" : "Изменить"}</h2><label>Название (рус.)<input id="n-ru" value="${esc(o.name_ru || "")}"></label><label>Название (узб.)<input id="n-uz" value="${esc(o.name_uz || "")}"></label>
  ${isNew ? "" : `<label><input type="checkbox" id="n-ac" ${o.active ? "checked" : ""} style="width:auto"> Активно (отключённое не входит в отчёты)</label>`}<div class="row mt"><button class="btn pri" id="n-ok">Сохранить</button><button class="btn right" onclick="closeModal()">Отмена</button></div>`);
  $("#n-ok").onclick = async () => { const body = { name_ru: $("#n-ru").value, name_uz: $("#n-uz").value }; if (!isNew) body.active = $("#n-ac").checked; else Object.assign(body, o);
    try { await api(isNew ? "/api/" + kind : `/api/${kind}/${o.id}`, { method: isNew ? "POST" : "PATCH", body }); closeModal(); done(); } catch (e) { fail(e); } };
}
function reportImportDlg(done) {
  modal(`<h2>Загрузка учреждений и показателей из Excel</h2><p class="muted">Файл вида «места для больных»: по листу на область, строка на учреждение (койки, свободные, обращения за 24 часа, поступило и выписано вчера/сегодня). Новые учреждения создаются в своей области, показатели записываются как отчёты. Чего в файле нет (тяжёлые и т.п.), остаётся пустым.</p>
  <div class="row"><label>«Вчера» записать на дату<input type="date" id="ri-p" value="${addDays(ME.today, -1)}"></label><label>«Сегодня» записать на дату<input type="date" id="ri-t" value="${ME.today}"></label></div>
  <input type="file" id="ri-f" accept=".xlsx" class="mt"><div id="ri-r" class="mt"></div><div class="row mt"><button class="btn" id="ri-pre">Проверить</button><button class="btn pri" id="ri-go" disabled>Загрузить</button><button class="btn right" onclick="closeModal()">Закрыть</button></div>`, true);
  const run = async dry => { const f = $("#ri-f").files[0]; if (!f) return toast("Выберите файл"); const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/import/reports?" + qs({ dry, d_prev: $("#ri-p").value, d_today: $("#ri-t").value }), { method: "POST", form: fd });
      $("#ri-r").innerHTML = `<p><b>${r.dry ? "Будет сделано" : "Готово"}:</b> учреждений в файле ${r.facilities}, новых ${r.new_facilities}, отчётов ${r.reports}${r.errors_total ? `, ошибок ${r.errors_total}` : ""}. Даты: ${r.dates.join(" и ")}.</p>${r.errors.length ? `<div class="alert critical">${r.errors.map(esc).join("<br>")}</div>` : ""}${r.new_list.length ? `<details><summary>Новые учреждения (${r.new_facilities})</summary><p class="sm">${r.new_list.map(esc).join("<br>")}</p></details>` : ""}`;
      $("#ri-go").disabled = !r.dry || !!r.errors_total; if (!r.dry) { toast("Загружено"); done(); } } catch (e) { fail(e); } };
  $("#ri-pre").onclick = () => run(1); $("#ri-go").onclick = () => run(0);
}
function importDlg(done) {
  modal(`<h2>Импорт территорий</h2><p class="muted">Столбцы: Регион, Район, Учреждение (+ необязательно «Район (узб)», «Учреждение (узб)»). Сначала предпросмотр.</p><input type="file" id="i-f" accept=".xlsx,.csv"><div id="i-r" class="mt"></div><div class="row mt"><button class="btn" id="i-pre">Проверить</button><button class="btn pri" id="i-go" disabled>Загрузить</button><button class="btn right" onclick="closeModal()">Закрыть</button></div>`);
  const run = async dry => { const f = $("#i-f").files[0]; if (!f) return toast("Выберите файл"); const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/geo/import?dry=" + dry, { method: "POST", form: fd }); $("#i-r").innerHTML = `<pre>${esc(JSON.stringify(r, null, 1))}</pre>`; $("#i-go").disabled = !!dry ? !(r.errors && r.errors.length === 0) : true; if (!dry) { toast("Загружено"); done(); } } catch (e) { fail(e); } };
  $("#i-pre").onclick = () => run(1); $("#i-go").onclick = () => run(0);
}

// ---------- indicators and rules
async function indicators() {
  const r = await api("/api/indicators");
  view.innerHTML = `<div class="card"><div class="row"><h2>Показатели</h2><button class="btn pri right" id="i-add">+ Показатель</button></div><p class="muted sm">«Способ сложения»: sum — потоки (обращения), last — состояние на последний день (койки), max — максимум за период.</p><div class="scroll-x"><table><tr><th>Код</th><th>Название</th><th>Сложение</th><th>Активен</th><th></th></tr>${r.items.map(i => `<tr><td>${esc(i.code)}${i.core ? " 🔒" : ""}</td><td>${esc(i.name_ru)}</td><td>${i.agg}</td><td>${i.active ? "да" : "нет"}</td><td><button class="btn sm" data-i="${i.code}">Изменить</button></td></tr>`).join("")}</table></div></div>
  <div class="card"><div class="row"><h2>Правила проверки</h2><button class="btn pri right" id="r-add">+ Правило</button></div><div class="scroll-x"><table><tr><th>Вид</th><th>Условие (должно выполняться)</th><th>Сообщение</th><th>Вкл.</th><th></th></tr>${r.rules.map(x => `<tr><td>${x.kind === "error" ? '<span class="pill critical">ошибка</span>' : '<span class="pill warning">предупреждение</span>'}</td><td><code>${esc(x.expr)}</code></td><td>${esc(x.message_ru)}</td><td>${x.active ? "да" : "нет"}</td><td><button class="btn sm" data-r="${x.id}">Изменить</button></td></tr>`).join("")}</table></div></div>`;
  $("#i-add").onclick = () => indDlg(null); document.querySelectorAll("[data-i]").forEach(b => b.onclick = () => indDlg(r.items.find(i => i.code === b.dataset.i)));
  $("#r-add").onclick = () => ruleDlg(null); document.querySelectorAll("[data-r]").forEach(b => b.onclick = () => ruleDlg(r.rules.find(x => x.id === +b.dataset.r)));
}
function indDlg(i) {
  modal(`<h2>${i ? "Показатель" : "Новый показатель"}</h2>${i ? "" : `<label>Код (латиница)<input id="p-c"></label>`}<label>Название (рус.)<input id="p-n" value="${esc(i?.name_ru || "")}"></label><label>Название (узб.)<input id="p-u" value="${esc(i?.name_uz || "")}"></label><label>Подсказка<input id="p-h" value="${esc(i?.hint_ru || "")}"></label>
  <label>Сложение<select id="p-a">${["sum", "last", "max"].map(a => `<option ${i?.agg === a ? "selected" : ""}>${a}</option>`).join("")}</select></label>${i ? `<label><input type="checkbox" id="p-ac" ${i.active ? "checked" : ""} style="width:auto"> Активен</label>` : ""}<div class="row mt"><button class="btn pri" id="p-ok">Сохранить</button><button class="btn right" onclick="closeModal()">Отмена</button></div>`);
  $("#p-ok").onclick = async () => { const body = { name_ru: $("#p-n").value, name_uz: $("#p-u").value, hint_ru: $("#p-h").value, agg: $("#p-a").value }; if (i) body.active = $("#p-ac").checked; else body.code = $("#p-c").value;
    try { await api(i ? "/api/indicators/" + i.code : "/api/indicators", { method: i ? "PATCH" : "POST", body }); META = await api("/api/meta"); closeModal(); indicators(); } catch (e) { fail(e); } };
}
function ruleDlg(x) {
  modal(`<h2>${x ? "Правило" : "Новое правило"}</h2><label>Условие: оно должно быть верным (например beds_occupied &lt;= beds_flu)<input id="q-e" value="${esc(x?.expr || "")}"></label><label>Вид<select id="q-k"><option value="error" ${x?.kind === "error" ? "selected" : ""}>Ошибка (блокирует отправку)</option><option value="warning" ${x?.kind === "warning" ? "selected" : ""}>Предупреждение</option></select></label>
  <label>Сообщение (рус.; можно {код})<input id="q-m" value="${esc(x?.message_ru || "")}"></label><label>Сообщение (узб.)<input id="q-u" value="${esc(x?.message_uz || "")}"></label><label><input type="checkbox" id="q-a" ${!x || x.active ? "checked" : ""} style="width:auto"> Включено</label>
  <div class="row mt"><button class="btn pri" id="q-ok">Сохранить</button>${x && !x.core ? '<button class="btn bad" id="q-del">Удалить</button>' : ""}<button class="btn right" onclick="closeModal()">Отмена</button></div>`);
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
  const r = await api("/api/settings");
  view.innerHTML = `<div class="card"><h2>Настройки</h2><p class="muted">Бот: ${r.bot.configured ? "подключён" + (r.bot.username ? " (@" + esc(r.bot.username) + ")" : "") : "токен не задан (TELEGRAM_BOT_TOKEN)"} ${r.bot.error ? "· ошибка: " + esc(r.bot.error) : ""}</p><div class="fields">${SET.map(([k, l, t]) => `<label>${l}<input data-k="${k}" type="${t === "time" ? "time" : t}" value="${esc(r.settings[k] ?? "")}"></label>`).join("")}</div>
  <div class="row mt"><button class="btn pri" id="s-save">Сохранить</button><button class="btn" id="s-run">Проверить рассылку (без отправки)</button><button class="btn" id="s-bk">Резервная копия</button></div><pre id="s-out"></pre></div>`;
  $("#s-save").onclick = async () => { try { await api("/api/settings", { method: "PUT", body: Object.fromEntries([...document.querySelectorAll("[data-k]")].map(i => [i.dataset.k, i.value])) }); toast("Сохранено"); } catch (e) { fail(e); } };
  $("#s-run").onclick = async () => { try { const x = await api("/api/notify/run", { method: "POST", body: { dry: true, force: true } }); $("#s-out").textContent = JSON.stringify(x.items, null, 1); } catch (e) { fail(e); } };
  $("#s-bk").onclick = async () => { try { toast("Создана: " + (await api("/api/backup", { method: "POST" })).file); } catch (e) { fail(e); } };
}

// ---------- audit
async function audit() {
  const r = await api("/api/audit?limit=300");
  view.innerHTML = `<div class="card"><h2>Журнал действий</h2><p class="muted sm">Записи неизменяемы: изменить или удалить их нельзя.</p><div class="scroll-x"><table><tr><th>Когда</th><th>Кто</th><th>Действие</th><th>Объект</th><th>Подробности</th></tr>${r.items.map(x => `<tr><td>${esc(x.at || x.created_at)}</td><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td>${esc(x.entity)} ${esc(x.entity_id)}</td><td class="sm">${esc(typeof x.details === "string" ? x.details : JSON.stringify(x.details))}</td></tr>`).join("")}</table></div></div>`;
}

// ---------- export
async function exportView() {
  const fb = await filterBar(exportView);
  view.innerHTML = fb.html + `<div class="card"><h2>Выгрузка</h2><p class="muted">Сводный отчёт за выбранный период и территорию. В Excel — 3 листа (сводка, детали, динамика), печать A4 с повтором шапки и полями для подписей.</p>
  <div class="row"><label>Вид<select id="x-k"><option value="daily">Ежедневный</option><option value="weekly">Недельный</option><option value="monthly">Месячный</option><option value="custom" selected>Произвольный период</option></select></label>
  ${["xlsx", "pdf", "csv"].map(f => `<a class="btn pri" data-f="${f}" href="#">${f.toUpperCase()}</a>`).join("")}</div></div>`; fb.bind();
  document.querySelectorAll("[data-f]").forEach(a => a.onclick = e => { e.preventDefault(); location.href = "/api/export?" + scopeQ() + "&" + qs({ fmt: a.dataset.f, kind: $("#x-k").value }); });
}

// ---------- shell
const TABS = [["dashboard", "Панель", dashboard, null], ["forecast", "Прогноз", forecastView, null], ["control", "Контроль", control, "w"], ["reports", "Отчёты", reportsView, "w"], ["people", "Доступы", people, "u"],
  ["export", "Выгрузка", exportView, null], ["territories", "Территории", territories, "s"], ["indicators", "Показатели", indicators, "s"], ["settings", "Настройки", settings, "s"], ["audit", "Журнал", audit, "s"]];
function allowed(t) { return !t[3] || (t[3] === "s" && ME.role === "super_admin") || (t[3] === "w" && ME.role !== "viewer") || (t[3] === "u" && ME.role !== "viewer" && ME.can_manage_users); }
function route() {
  const name = (location.hash.slice(2) || "dashboard").split("?")[0];
  const tab = TABS.find(t => t[0] === name && allowed(t)) || TABS[0];
  document.querySelectorAll("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.t === tab[0]));
  Promise.resolve(tab[2]()).catch(fail);
}
$("#pwbtn").onclick = () => { modal(`<h2>Смена пароля</h2><label>Текущий пароль<input type="password" id="o"></label><label>Новый пароль (от 8 знаков)<input type="password" id="n"></label><div class="row mt"><button class="btn pri" id="ok">Сменить</button><button class="btn right" onclick="closeModal()">Отмена</button></div>`);
  $("#ok").onclick = async () => { try { await api("/api/me/password", { method: "POST", body: { old: $("#o").value, new: $("#n").value } }); closeModal(); toast("Пароль изменён"); } catch (e) { fail(e); } }; };
(async () => {
  try { ME = await api("/api/me"); META = await api("/api/meta"); } catch (e) { return; }
  $("#who").textContent = `${ME.name && ME.name !== ME.role_label ? ME.name : ME.login} · ${ME.role_label}`;
  $("#tabs").innerHTML = TABS.filter(allowed).map(t => `<a href="#/${t[0]}" data-t="${t[0]}">${t[1]}</a>`).join("");
  window.addEventListener("hashchange", route); route();
})();
