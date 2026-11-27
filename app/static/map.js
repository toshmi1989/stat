// Map of Uzbekistan: regions pulse by the numbers the regions report. Outlines: uzmap.js (tools/build_map.py).
const MAP_METRICS = [["occupancy", T("Загрузка коек"), "%"], ["visits", T("Обращения"), ""], ["severe", T("Тяжёлые"), ""], ["extreme", T("Крайне тяжёлые"), ""], ["not_reported", T("Не сдали отчёт"), ""]];
let MAPM = "occupancy", NO_OCC = false, OCC_EST = false;                       // NO_OCC: nobody reports the occupied beds (the question is switched off): no occupancy view
const mapMetrics = () => (NO_OCC ? MAP_METRICS.filter(x => x[0] !== "occupancy") : MAP_METRICS).map(x => x[0] === "occupancy" && OCC_EST ? [x[0], T("Загрузка коек (расч.)"), x[2]] : x);
// The views change by themselves every 3 seconds; a view the person picks stays for a minute, then the changing goes on.
const MAP_AUTO = { every: 3, pinSec: 60, tick: 0, pinnedUntil: 0, draw: null, timer: null };
const mapCaption = () => { const left = Math.ceil((MAP_AUTO.pinnedUntil - Date.now()) / 1000);
  return left > 0 ? T("Выбранный вид закреплён: ещё {n} с, потом виды снова меняются сами. Нажмите на регион, чтобы открыть его.", { n: left }) : T("Виды меняются сами каждые {n} с; выберите вид, и он останется на минуту. Нажмите на регион, чтобы открыть его.", { n: MAP_AUTO.every }); };
function mapAutoStart() {
  if (MAP_AUTO.timer) return;
  MAP_AUTO.timer = setInterval(() => {
    const box = $("#map"); if (!box || !MAP_AUTO.draw || document.hidden) return;      // another page, or the tab is in the background
    const cap = $("#map-cap"); if (cap) cap.textContent = mapCaption();
    if (MAP_AUTO.pinnedUntil - Date.now() > 0 || RM || box.matches(":hover")) { MAP_AUTO.tick = 0; return; }   // pinned, reduced motion, or the pointer is on the map: nothing changes under it
    if (++MAP_AUTO.tick >= MAP_AUTO.every) {
      MAP_AUTO.tick = 0;
      const ms = mapMetrics(), i = ms.findIndex(x => x[0] === MAPM); MAPM = ms[(i + 1) % ms.length][0]; MAP_AUTO.draw();
    }
  }, 1000);
}
const mapShort = n => LANG === "uz" ? uzShort(n) : n.replace("Республика ", "").replace("Каракалпакстан", "Каракалп.").replace(" область", "").replace("город ", "г. ");
function mapValue(r, m) { return m === "not_reported" ? Math.max((r.facilities || 0) - (r.reported || 0), 0) : r.values[m]; }
// state of a region: occupancy by the thresholds of the settings; the other figures have no norm, so by the share of the leading region
function mapStates(rows, m, th) {
  const vals = rows.map(r => mapValue(r, m)), max = Math.max(0, ...vals.map(v => v || 0));
  return rows.map((r, i) => {
    const v = vals[i];
    if (v == null || (r.reported === 0 && m !== "not_reported")) return { r, v, st: "none", k: 0 };
    if (m === "occupancy") return { r, v, st: v >= th.critical ? "critical" : v >= th.elevated ? "warning" : "normal", k: clamp(v / 100, 0, 1) };
    const k = max ? v / max : 0;
    const st = v <= 0 ? "normal" : m === "extreme" ? "critical" : k >= 0.75 ? "critical" : k >= 0.4 ? "warning" : "normal";
    return { r, v, st, k };
  });
}
// where the labels of the small regions stand: id -> {ax: x of the vertical leader, ty: baseline of the label, end: the text ends at the leader (else it starts there)}.
// Some labels stand above the valley, some below it, always near the dot. The leaders are vertical and the labels form a staircase, so no leader crosses another leader or a label:
// above, the farther right the higher, the text ending at its leader; below, the farther right the lower, the text ending at its leader too, except the ids in `right`
// (the leftmost one, whose text starts at the leader and goes into the free place on its right).
function uzCallouts(M, below, above, right = [], y0 = 476, yUp = 262, step = 27, gap = 26) {
  const out = {}, cx = id => M.r[id].c[0], cy = id => M.r[id].c[1];
  let prev = -1e9;
  below.slice().sort((a, b) => (cx(a) - cy(a) * 0.1) - (cx(b) - cy(b) * 0.1)).forEach((id, i) => {    // of two dots one above the other the lower goes first: the leader of the upper one must not pass through its dot
    prev = Math.max(cx(id), prev + gap); out[id] = { ax: Math.round(prev), ty: y0 + i * step, end: !right.includes(id) };
  });
  prev = -1e9;
  above.slice().sort((a, b) => cx(a) - cx(b)).forEach((id, i) => { prev = Math.max(cx(id), prev + gap); out[id] = { ax: Math.round(prev), ty: yUp - i * step, end: true }; });
  return out;
}
function uzMap(rows, m, th, sel) {
  const M = window.UZMAP; if (!M) return "";
  const S = mapStates(rows, m, th), unit = MAP_METRICS.find(x => x[0] === m)[2], fmt = v => v == null ? "—" : (m === "occupancy" ? Math.round(v) : Math.round(v)).toLocaleString(LOCALE) + unit;
  const by = Object.fromEntries(S.map(s => [s.r.id, s])), ids = Object.keys(M.r);
  const order = ids.slice().sort((a, b) => (id => id == 14 ? 1 : 0)(a) - (id => id == 14 ? 1 : 0)(b));   // the city of Tashkent lies inside the region: draw it last
  const dur = s => (s.st === "critical" ? 1.9 - 1.1 * s.k : 3.2).toFixed(2);     // the higher the figure, the faster the pulse
  // small regions of the Fergana valley and Tashkent: the label stands next to the map on a leader line (see uzCallouts)
  const CALL = uzCallouts(M, [10, 12, 2], [14, 11, 7], [10]);
  const g = id => {
    const s = by[id] || { r: { id, name: "—", reported: 0, facilities: 0, values: {} }, v: null, st: "off", k: 0 }, p = M.r[id], [cx, cy] = p.c, alive = s.st === "critical" || s.st === "warning", city = +id === 14, co = CALL[id];
    const lab = !co
      ? `<text class="lb" x="${cx}" y="${cy - 11}" text-anchor="middle"><tspan class="ln1">${esc(mapShort(s.r.name))}</tspan><tspan class="ln2" x="${cx}" dy="15">${fmt(s.v)}</tspan></text>`
      : `<polyline class="lead" points="${cx},${cy} ${co.ax},${cy} ${co.ax},${co.ty - 4}"/><text class="lb call" x="${co.end ? co.ax - 7 : co.ax + 7}" y="${co.ty}" text-anchor="${co.end ? "end" : "start"}"><tspan class="ln1">${esc(mapShort(s.r.name))} </tspan><tspan class="ln2">${fmt(s.v)}</tspan></text>`;
    return `<g class="rg st-${s.st}${String(sel) === String(id) ? " sel" : ""}" data-rid="${id}" tabindex="0" role="button" aria-label="${esc(rname(s.r.name))}: ${fmt(s.v)}" style="--dur:${dur(s)}s">
      <path class="fl" d="${p.d}"/>${alive ? `<path class="gl" d="${p.d}"/>` : ""}<path class="ln" d="${p.d}"/>
      ${alive ? `<circle class="ring" cx="${cx}" cy="${cy}" r="${city ? 7 : 16}"/><circle class="ring r2" cx="${cx}" cy="${cy}" r="${city ? 7 : 16}"/>` : ""}
      <circle class="dot" cx="${cx}" cy="${cy}" r="${co ? 4 : 5.5}"/>${lab}</g>`;
  };
  const shadows = `<g class="shs">${ids.map(id => `<path d="${M.r[id].d}"/>`).join("")}</g>`;
  return `<svg class="uzmap" viewBox="0 0 ${M.w} ${M.h}" role="group" aria-label="${T("Карта Узбекистана по регионам")}">${shadows}${order.map(g).join("")}</svg>`;
}
// the card: metric chips, the map, the side list of the regions that need attention
function mapCard() { return `<div class="card mapcard"><div class="row"><h2>${T("Карта регионов")}</h2><span class="muted sm right" id="map-cap" data-keep></span></div><div class="chips" id="map-m" data-keep></div>
  <div class="mapwrap"><div class="mapbox"><div id="map" data-keep></div><div class="maptip" id="map-tip" data-keep hidden></div></div><div class="mapside" id="map-side" data-keep></div></div><div class="legend-dots" id="map-leg" data-keep></div></div>`; }
function bindMap(rows, th, onPick, silent) {
  const box = $("#map"); if (!box) return;
  if (NO_OCC && MAPM === "occupancy") MAPM = "visits";
  const draw = () => {
    H($("#map-m"), true).innerHTML = mapMetrics().map(([k, l]) => `<button class="chip${k === MAPM ? " on" : ""}" data-m="${k}">${l}</button>`).join("");
    H(box, true).innerHTML = uzMap(rows, MAPM, th, F.region_id);          // patched: the map is not redrawn, only the regions that changed
    const S = mapStates(rows, MAPM, th), unit = MAP_METRICS.find(x => x[0] === MAPM)[2], hot = S.filter(s => s.st === "critical" || s.st === "warning").sort((a, b) => b.k - a.k);
    H($("#map-side"), true).innerHTML = `<h3>${T("Требуют внимания")}</h3>` + (hot.length ? hot.slice(0, 6).map(s => `<button class="mrow st-${s.st}" data-rid="${s.r.id}"><i></i><span>${esc(mapShort(s.r.name))}</span><b>${Math.round(s.v).toLocaleString(LOCALE)}${unit}</b></button>`).join("") : `<p class="muted sm">${T("Нет регионов с повышенными значениями.")}</p>`);
    H($("#map-leg"), true).innerHTML = MAPM === "occupancy"
      ? `<span><i style="background:var(--ok)"></i>${T("норма до {n}%", { n: th.elevated })}</span><span><i style="background:var(--warn)"></i>${T("повышенная до {n}%", { n: th.critical })}</span><span><i style="background:var(--bad)"></i>${T("критическая от {n}% — пульсирует", { n: th.critical })}</span><span><i style="background:var(--mut)"></i>${T("нет данных")}</span>`
      : `<span><i style="background:var(--ok)"></i>${T("меньше 40% от лидера")}</span><span><i style="background:var(--warn)"></i>${T("40–75% от лидера")}</span><span><i style="background:var(--bad)"></i>${MAPM === "extreme" ? T("от 75% лидера и любой случай — пульсирует") : T("от 75% лидера — пульсирует")}</span><span class="muted">${T("у этого показателя нет нормы, цвет считается относительно лидера")}</span>`;
    $("#map-cap").textContent = mapCaption();
  };
  const tip = $("#map-tip"), find = e => e.target.closest && e.target.closest(".rg");
  const by = () => Object.fromEntries(mapStates(rows, MAPM, th).map(s => [s.r.id, s]));
  box.onpointermove = e => {
    const el = find(e); if (!el) { tip.hidden = true; return; }
    if (el.parentNode.lastChild !== el) el.parentNode.appendChild(el);   // lift the hovered region above its neighbours
    const s = by()[el.dataset.rid], r = s.r, b = box.getBoundingClientRect(), unit = MAP_METRICS.find(x => x[0] === MAPM)[2];
    tip.innerHTML = `<b>${esc(rname(r.name))}</b><span>${MAP_METRICS.find(x => x[0] === MAPM)[1]}: <b>${s.v == null ? "—" : Math.round(s.v).toLocaleString(LOCALE) + unit}</b></span><span>${T("Сдали отчёт: {a} из {b}", { a: r.reported, b: r.facilities })}</span><span>${T("Обращения {v} · тяжёлые {s} · койки {o}", { v: num(r.values.visits), s: num(r.values.severe), o: r.values.occupancy == null ? "—" : r.values.occupancy + "%" })}</span>`;
    tip.hidden = false; tip.style.left = Math.min(e.clientX - b.left + 14, b.width - 230) + "px"; tip.style.top = Math.max(e.clientY - b.top - 10, 0) + "px";
  };
  box.onpointerleave = () => { tip.hidden = true; };
  box.onclick = e => { const el = find(e); if (el) onPick(el.dataset.rid); };
  box.onkeydown = e => { if ((e.key === "Enter" || e.key === " ") && find(e)) { e.preventDefault(); onPick(find(e).dataset.rid); } };
  $("#map-m").onclick = e => { const b = e.target.closest("[data-m]"); if (b) { MAPM = b.dataset.m; MAP_AUTO.pinnedUntil = Date.now() + MAP_AUTO.pinSec * 1000; MAP_AUTO.tick = 0; draw(); } };
  $("#map-side").onclick = e => { const b = e.target.closest("[data-rid]"); if (b) onPick(b.dataset.rid); };
  MAP_AUTO.draw = draw; mapAutoStart();
  draw();
}
