// Small SVG charts without libraries: line (with optional dashed forecast) and grouped bars.
const COLORS = ["#1f6feb", "#d64545", "#1a9d5c", "#d9922b", "#8957e5", "#0e8a96"];
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
// short name of a region for tiles, chips and map labels (the Uzbek one; the Russian shortenings stay where they were)
const uzShort = n => rname(n).replace(" viloyati", "").replace(" Respublikasi", "").replace(" shahri", " sh.");
function niceMax(v) { if (v <= 0) return 1; const p = 10 ** Math.floor(Math.log10(v)); const m = v / p; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p; }
function frame(W, H, ml, mt, mr, mb, max, labels) {
  let s = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" preserveAspectRatio="none">`;
  for (let i = 0; i <= 4; i++) { const y = mt + (H - mt - mb) * (1 - i / 4); s += `<line x1="${ml}" x2="${W - mr}" y1="${y}" y2="${y}" stroke="currentColor" opacity=".12"/><text x="${ml - 4}" y="${y + 4}" text-anchor="end">${+(max * i / 4).toFixed(1)}</text>`; }
  const step = Math.ceil(labels.length / 8);
  labels.forEach((l, i) => { if (i % step === 0) s += `<text x="${ml + (W - ml - mr) * (labels.length > 1 ? i / (labels.length - 1) : .5)}" y="${H - 6}" text-anchor="middle">${esc(l.slice(5))}</text>`; });
  return s;
}
// series: [{name, points:[n|null], dashed?, color?, band?:[[low,high]...]}]
function lineChart(labels, series) {
  const W = 800, H = 260, ml = 40, mt = 10, mr = 10, mb = 24;
  const all = series.flatMap(s => s.points.concat((s.band || []).map(b => b && b[1]))).filter(v => v != null);
  const max = niceMax(Math.max(0, ...all)), n = labels.length, gid = "lg" + Math.random().toString(36).slice(2, 7);
  const X = i => ml + (W - ml - mr) * (n > 1 ? i / (n - 1) : .5), Y = v => mt + (H - mt - mb) * (1 - v / max);
  let s = frame(W, H, ml, mt, mr, mb, max, labels);
  s += "<defs>" + series.map((sr, k) => { const col = sr.color || COLORS[k % COLORS.length]; return `<linearGradient id="${gid}${k}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".32"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient>`; }).join("") + "</defs>";
  series.forEach((sr, k) => {
    const col = sr.color || COLORS[k % COLORS.length];
    if (sr.band) { const up = [], lo = []; sr.band.forEach((b, i) => { if (b) { up.push(`${X(i)},${Y(b[1])}`); lo.unshift(`${X(i)},${Y(b[0])}`); } }); if (up.length) s += `<polygon points="${up.concat(lo).join(" ")}" fill="${col}" opacity=".12"/>`; }
    let d = "", pen = false, first = null, last = null;
    sr.points.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; if (first === null) first = i; last = i; });
    if (first !== null && !sr.dashed && series.length <= 3) s += `<path class="area" d="${d}L${X(last).toFixed(1)},${H - mb}L${X(first).toFixed(1)},${H - mb}Z" fill="url(#${gid}${k})" stroke="none"/>`;
    s += `<path class="draw" pathLength="1" d="${d}" fill="none" stroke="${col}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" ${sr.dashed ? 'stroke-dasharray="5 4"' : ""}/>`;
    if (n <= 40) sr.points.forEach((v, i) => { if (v != null) s += `<circle class="dot" cx="${X(i)}" cy="${Y(v)}" r="3" fill="var(--card)" stroke="${col}" stroke-width="2"><title>${esc(sr.name)} ${esc(labels[i])}: ${v}</title></circle>`; });
  });
  return s + "</svg>" + legend(series);
}
// groups: labels; series: [{name, values:[n]}]; each bar is extruded (front, top and side faces)
function barChart(labels, series) {
  const W = 800, H = 260, ml = 40, mt = 14, mr = 14, mb = 24;
  const max = niceMax(Math.max(0, ...series.flatMap(s => s.values.filter(v => v != null))));
  const n = labels.length, gw = (W - ml - mr) / Math.max(n, 1), bw = Math.max(3, gw * .7 / series.length), dx = Math.min(5, bw * .35), dy = dx * .7;
  let s = frame(W, H, ml, mt, mr, mb, max, labels);
  series.forEach((sr, k) => sr.values.forEach((v, i) => {
    if (v == null) return;
    const h = (H - mt - mb) * v / max, x = ml + gw * i + gw * .15 + bw * k, y = H - mb - h, col = sr.color || COLORS[k % COLORS.length];
    s += `<g class="bar3" style="--d:${(i * 25)}ms"><title>${esc(sr.name)} ${esc(labels[i])}: ${v}</title><rect x="${x}" y="${y}" width="${bw}" height="${h}" fill="${col}"/>
      <polygon points="${x + bw},${y} ${x + bw + dx},${y - dy} ${x + bw + dx},${H - mb - dy} ${x + bw},${H - mb}" fill="${col}"/><polygon points="${x + bw},${y} ${x + bw + dx},${y - dy} ${x + bw + dx},${H - mb - dy} ${x + bw},${H - mb}" fill="#000" opacity=".28"/>
      <polygon points="${x},${y} ${x + dx},${y - dy} ${x + bw + dx},${y - dy} ${x + bw},${y}" fill="#fff" opacity=".42"/></g>`;
  }));
  return s + "</svg>" + legend(series);
}
function legend(series) { return `<div class="legend">${series.map((s, k) => `<span><i style="background:${s.color || COLORS[k % COLORS.length]}"></i>${esc(s.name)}</span>`).join("")}</div>`; }
