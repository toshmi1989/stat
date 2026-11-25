// Infographics and effects without libraries. Everything animated respects "reduced motion".
const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
let _uid = 0; const uid = p => p + (++_uid);

// numbers that count up
function countUp(root = document) {
  root.querySelectorAll("[data-count]").forEach(el => {
    const to = parseFloat(el.dataset.count), dec = +(el.dataset.dec || 0), suf = el.dataset.suf || "";
    const fmt = v => v.toLocaleString(LOCALE, { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suf;
    if (RM || !isFinite(to)) { el.textContent = fmt(to); return; }
    const t0 = performance.now(), dur = 900;
    const step = now => { const k = Math.min((now - t0) / dur, 1), e = 1 - Math.pow(1 - k, 3); el.textContent = fmt(to * e); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
}
// 3D tilt with a moving glare
function tilt(root = document) {
  if (RM || matchMedia("(hover: none)").matches) return;
  root.querySelectorAll(".tilt").forEach(el => {
    el.onmousemove = e => { const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      el.style.setProperty("--ry", ((x - .5) * 14).toFixed(1) + "deg"); el.style.setProperty("--rx", ((.5 - y) * 14).toFixed(1) + "deg");
      el.style.setProperty("--mx", (x * 100).toFixed(0) + "%"); el.style.setProperty("--my", (y * 100).toFixed(0) + "%"); };
    el.onmouseleave = () => { el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); };
  });
}
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// progress ring: part of whole
function ringChart(done, total, label) {
  const pct = total ? clamp(done / total * 100, 0, 100) : 0, r = 54, C = 2 * Math.PI * r, id = uid("rg");
  const col = pct >= 100 ? "var(--ok)" : pct >= 60 ? "var(--pri)" : "var(--warn)";
  return `<svg viewBox="0 0 140 140" class="viz-svg ring" role="img" aria-label="${esc(label)}"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".55"/><stop offset="1" stop-color="${col}"/></linearGradient></defs>
    <circle cx="70" cy="70" r="${r}" fill="none" stroke="var(--grey)" stroke-width="14"/>
    <circle class="ring-arc" cx="70" cy="70" r="${r}" fill="none" stroke="url(#${id})" stroke-width="14" stroke-linecap="round" transform="rotate(-90 70 70)" stroke-dasharray="${C.toFixed(1)}" style="--from:${C.toFixed(1)};--to:${(C * (1 - pct / 100)).toFixed(1)}" stroke-dashoffset="${(C * (1 - pct / 100)).toFixed(1)}"/>
    <text x="70" y="68" text-anchor="middle" class="ring-v">${Math.round(pct)}%</text><text x="70" y="88" text-anchor="middle" class="ring-s">${T("{a} из {b}", { a: done, b: total })}</text></svg>`;
}
// gauge with the threshold zones and a needle
function gaugeChart(pct, th) {
  const has = pct != null, v = has ? clamp(pct, 0, 100) : 0, R = 80, cx = 100, cy = 100;
  const pt = (p, r = R) => { const a = Math.PI * (1 - p / 100); return [cx + r * Math.cos(a), cy - r * Math.sin(a)]; };
  const arc = (a, b, col, w = 16) => { const [x1, y1] = pt(a), [x2, y2] = pt(b); return `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)} A${R} ${R} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}" fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="butt"/>`; };
  const state = !has ? "none" : v >= th.critical ? "critical" : v >= th.elevated ? "warning" : "normal";
  const col = { normal: "var(--ok)", warning: "var(--warn)", critical: "var(--bad)", none: "var(--mut)" }[state];
  return `<svg viewBox="0 0 200 128" class="viz-svg gauge" role="img" aria-label="${T("Загрузка коек {v}", { v: has ? Math.round(v) + '%' : T("нет данных") })}">
    <g opacity=".28">${arc(0, th.elevated, "var(--ok)")}${arc(th.elevated, th.critical, "var(--warn)")}${arc(th.critical, 100, "var(--bad)")}</g>
    ${has ? `<g class="gauge-fill" style="--pct:${v}">${arc(0, v, col, 16)}</g>` : ""}
    <g class="needle" style="--deg:${has ? (v / 100 * 180 - 90) : -90}deg"><line x1="100" y1="100" x2="100" y2="34" stroke="var(--ink)" stroke-width="3" stroke-linecap="round"/><circle cx="100" cy="100" r="7" fill="var(--ink)"/><circle cx="100" cy="100" r="3" fill="var(--card)"/></g>
    <text x="100" y="124" text-anchor="middle" class="gauge-v" fill="${col}">${has ? Math.round(v * 10) / 10 + "%" : "—"}</text>
    <text x="14" y="116" class="gauge-s">0</text><text x="186" y="116" text-anchor="end" class="gauge-s">100</text></svg>`;
}
// tiles of regions coloured by the load of beds; hover lifts a tile
function heatTiles(rows, th) {
  const short = n => LANG === "uz" ? uzShort(n) : n.replace("Республика ", "").replace("Каракалпакстан", "Каракалп.").replace(" область", "").replace("город ", "г. ");
  return `<div class="tiles">${rows.map((r, i) => {
    const o = r.values.occupancy, st = o == null ? "none" : o >= th.critical ? "critical" : o >= th.elevated ? "warning" : "normal";
    return `<button class="tile t-${st}" style="--i:${i}" data-rid="${r.id}" title="${esc(rname(r.name))}: ${o == null ? T("нет данных") : o + "%"}"><span class="tn">${esc(short(r.name))}</span><span class="tv">${o == null ? "—" : Math.round(o) + "%"}</span><span class="tb"><i style="width:${o == null ? 0 : clamp(o, 0, 100)}%"></i></span></button>`;
  }).join("")}</div>`;
}
// ranking with extruded (pseudo-3D) bars
function rankBars(rows, key, unit = "") {
  const list = rows.map(r => ({ id: r.id, name: r.name, v: r.values[key] || 0 })).sort((a, b) => b.v - a.v).slice(0, 8), max = Math.max(1, ...list.map(x => x.v));
  return `<div class="rank">${list.map((x, i) => `<button class="rk" style="--i:${i}" data-rid="${x.id}"><span class="rn">${esc(LANG === "uz" ? uzShort(x.name) : x.name.replace(" область", "").replace("Республика ", ""))}</span><span class="rb"><i style="--w:${(x.v / max * 100).toFixed(1)}%"></i></span><span class="rv">${x.v.toLocaleString(LOCALE)}${unit}</span></button>`).join("")}</div>`;
}
// admitted vs discharged: a balance bar
function flowCard(h, d) {
  const hh = h || 0, dd = d || 0, tot = hh + dd || 1, diff = hh - dd;
  return `<div class="flow"><div class="fl-row"><span class="fl-i up">▲</span><div><div class="fl-l">${T("Поступили")}</div><div class="fl-v" data-count="${hh}">${hh}</div></div></div>
    <div class="fl-row"><span class="fl-i down">▼</span><div><div class="fl-l">${T("Выписаны")}</div><div class="fl-v" data-count="${dd}">${dd}</div></div></div>
    <div class="fl-bar"><i class="a" style="--w:${(hh / tot * 100).toFixed(1)}%"></i><i class="b" style="--w:${(dd / tot * 100).toFixed(1)}%"></i></div>
    <div class="fl-s ${diff > 0 ? "bad" : "ok"}">${diff > 0 ? T("Нагрузка растёт: +{n}", { n: diff }) : diff < 0 ? T("Нагрузка снижается: {n}", { n: diff }) : T("Баланс нулевой")}</div></div>`;
}
