// Map of Uzbekistan: regions pulse by the numbers the regions report. Outlines: uzmap.js (tools/build_map.py).
const MAP_METRICS = [["occupancy", "Загрузка коек", "%"], ["visits", "Обращения", ""], ["severe", "Тяжёлые", ""], ["extreme", "Крайне тяжёлые", ""], ["not_reported", "Не сдали отчёт", ""]];
let MAPM = "occupancy";
const mapShort = n => n.replace("Республика ", "").replace("Каракалпакстан", "Каракалп.").replace(" область", "").replace("город ", "г. ");
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
function uzMap(rows, m, th, sel) {
  const M = window.UZMAP; if (!M) return "";
  const S = mapStates(rows, m, th), unit = MAP_METRICS.find(x => x[0] === m)[2], fmt = v => v == null ? "—" : (m === "occupancy" ? Math.round(v) : Math.round(v)).toLocaleString("ru-RU") + unit;
  const by = Object.fromEntries(S.map(s => [s.r.id, s])), ids = Object.keys(M.r);
  const order = ids.slice().sort((a, b) => (id => id == 14 ? 1 : 0)(a) - (id => id == 14 ? 1 : 0)(b));   // the city of Tashkent lies inside the region: draw it last
  const dur = s => (s.st === "critical" ? 1.9 - 1.1 * s.k : 3.2).toFixed(2);     // the higher the figure, the faster the pulse
  const CALL = [10, 14, 11, 7, 12, 2], CX = 745, CY = 478;   // small regions of the Fergana valley and Tashkent: the label stands in a free corner of the map on a leader line
  const g = id => {
    const s = by[id] || { r: { id, name: "—", reported: 0, facilities: 0, values: {} }, v: null, st: "off", k: 0 }, p = M.r[id], [cx, cy] = p.c, alive = s.st === "critical" || s.st === "warning", city = +id === 14, ci = CALL.indexOf(+id);
    const ty = CY + ci * 27, lab = ci < 0
      ? `<text class="lb" x="${cx}" y="${cy - 11}" text-anchor="middle"><tspan class="ln1">${esc(mapShort(s.r.name))}</tspan><tspan class="ln2" x="${cx}" dy="15">${fmt(s.v)}</tspan></text>`
      : `<polyline class="lead" points="${cx},${cy} ${CX - 2},${ty - 5}"/><text class="lb call" x="${CX + 4}" y="${ty}"><tspan class="ln1">${esc(mapShort(s.r.name))} </tspan><tspan class="ln2">${fmt(s.v)}</tspan></text>`;
    return `<g class="rg st-${s.st}${String(sel) === String(id) ? " sel" : ""}" data-rid="${id}" tabindex="0" role="button" aria-label="${esc(s.r.name)}: ${fmt(s.v)}" style="--dur:${dur(s)}s">
      <path class="fl" d="${p.d}"/>${alive ? `<path class="gl" d="${p.d}"/>` : ""}<path class="ln" d="${p.d}"/>
      ${alive ? `<circle class="ring" cx="${cx}" cy="${cy}" r="${city ? 7 : 16}"/><circle class="ring r2" cx="${cx}" cy="${cy}" r="${city ? 7 : 16}"/>` : ""}
      <circle class="dot" cx="${cx}" cy="${cy}" r="${ci >= 0 ? 4 : 5.5}"/>${lab}</g>`;
  };
  const shadows = `<g class="shs">${ids.map(id => `<path d="${M.r[id].d}"/>`).join("")}</g>`;
  return `<svg class="uzmap" viewBox="0 0 ${M.w} ${M.h}" role="group" aria-label="Карта Узбекистана по регионам">${shadows}${order.map(g).join("")}</svg>`;
}
// the card: metric chips, the map, the side list of the regions that need attention
function mapCard() { return `<div class="card mapcard"><div class="row"><h2>Карта регионов</h2><span class="muted sm right" id="map-cap" data-keep></span></div><div class="chips" id="map-m" data-keep></div>
  <div class="mapwrap"><div class="mapbox"><div id="map" data-keep></div><div class="maptip" id="map-tip" data-keep hidden></div></div><div class="mapside" id="map-side" data-keep></div></div><div class="legend-dots" id="map-leg" data-keep></div></div>`; }
function bindMap(rows, th, onPick, silent) {
  const box = $("#map"); if (!box) return;
  const draw = () => {
    H($("#map-m"), true).innerHTML = MAP_METRICS.map(([k, l]) => `<button class="chip${k === MAPM ? " on" : ""}" data-m="${k}">${l}</button>`).join("");
    H(box, true).innerHTML = uzMap(rows, MAPM, th, F.region_id);          // patched: the map is not redrawn, only the regions that changed
    const S = mapStates(rows, MAPM, th), unit = MAP_METRICS.find(x => x[0] === MAPM)[2], hot = S.filter(s => s.st === "critical" || s.st === "warning").sort((a, b) => b.k - a.k);
    H($("#map-side"), true).innerHTML = `<h3>Требуют внимания</h3>` + (hot.length ? hot.slice(0, 6).map(s => `<button class="mrow st-${s.st}" data-rid="${s.r.id}"><i></i><span>${esc(mapShort(s.r.name))}</span><b>${Math.round(s.v).toLocaleString("ru-RU")}${unit}</b></button>`).join("") : `<p class="muted sm">Нет регионов с повышенными значениями.</p>`);
    H($("#map-leg"), true).innerHTML = MAPM === "occupancy"
      ? `<span><i style="background:var(--ok)"></i>норма до ${th.elevated}%</span><span><i style="background:var(--warn)"></i>повышенная до ${th.critical}%</span><span><i style="background:var(--bad)"></i>критическая от ${th.critical}% — пульсирует</span><span><i style="background:var(--mut)"></i>нет данных</span>`
      : `<span><i style="background:var(--ok)"></i>меньше 40% от лидера</span><span><i style="background:var(--warn)"></i>40–75% от лидера</span><span><i style="background:var(--bad)"></i>от 75% лидера${MAPM === "extreme" ? " и любой случай" : ""} — пульсирует</span><span class="muted">у этого показателя нет нормы, цвет считается относительно лидера</span>`;
    $("#map-cap").textContent = "Чем выше значение, тем чаще пульсирует регион. Нажмите на регион, чтобы открыть его.";
  };
  const tip = $("#map-tip"), find = e => e.target.closest && e.target.closest(".rg");
  const by = () => Object.fromEntries(mapStates(rows, MAPM, th).map(s => [s.r.id, s]));
  box.onpointermove = e => {
    const el = find(e); if (!el) { tip.hidden = true; return; }
    if (el.parentNode.lastChild !== el) el.parentNode.appendChild(el);   // lift the hovered region above its neighbours
    const s = by()[el.dataset.rid], r = s.r, b = box.getBoundingClientRect(), unit = MAP_METRICS.find(x => x[0] === MAPM)[2];
    tip.innerHTML = `<b>${esc(r.name)}</b><span>${MAP_METRICS.find(x => x[0] === MAPM)[1]}: <b>${s.v == null ? "—" : Math.round(s.v).toLocaleString("ru-RU") + unit}</b></span><span>Сдали отчёт: ${r.reported} из ${r.facilities}</span><span>Обращения ${num(r.values.visits)} · тяжёлые ${num(r.values.severe)} · койки ${r.values.occupancy == null ? "—" : r.values.occupancy + "%"}</span>`;
    tip.hidden = false; tip.style.left = Math.min(e.clientX - b.left + 14, b.width - 230) + "px"; tip.style.top = Math.max(e.clientY - b.top - 10, 0) + "px";
  };
  box.onpointerleave = () => { tip.hidden = true; };
  box.onclick = e => { const el = find(e); if (el) onPick(el.dataset.rid); };
  box.onkeydown = e => { if ((e.key === "Enter" || e.key === " ") && find(e)) { e.preventDefault(); onPick(find(e).dataset.rid); } };
  $("#map-m").onclick = e => { const b = e.target.closest("[data-m]"); if (b) { MAPM = b.dataset.m; draw(); } };
  $("#map-side").onclick = e => { const b = e.target.closest("[data-rid]"); if (b) onPick(b.dataset.rid); };
  draw();
}
