// Regression: moving quickly between sections with a region chosen must never leave «Панель» without its cards (a late answer of the previous section used to draw over it).
// Run: BASE=http://localhost:8770 node tests/e2e/race.js  (a demo database; about a minute)
const { chromium } = require("playwright");
(async () => { const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1300, height: 900 } })).newPage(); const errs = []; let bad = 0, n = 0;
  p.on("pageerror", e => errs.push((e.stack || e.message).split("\n").slice(0, 2).join(" @ ").replace(/http:\/\/localhost:8787\/static\//g, "")));
  await p.request.post((process.env.BASE || "http://localhost:8770") + "/login", { form: { login: "admin", password: "secret123" }, maxRedirects: 0 }).catch(() => {});
  await p.goto((process.env.BASE || "http://localhost:8770") + "/"); await p.waitForSelector(".kpi");
  await p.route("**/api/**", async r => { await new Promise(res => setTimeout(res, Math.random() * 500)); r.continue(); });
  await p.selectOption("#f-r", { index: 3 }); await p.waitForTimeout(1500);      // a region is chosen: the filter bar needs the network (districts) on every page
  const tabs = ["forecast", "settings", "reports", "people", "export", "territories", "dashboard"];
  for (let i = 0; i < 8; i++) {
    const hops = 1 + Math.floor(Math.random() * 3);
    for (let h = 0; h < hops; h++) { await p.click(`#tabs a[data-t="${tabs[Math.floor(Math.random() * 6)]}"]`); await p.waitForTimeout(Math.random() * 150); }
    await p.click('#tabs a[data-t="dashboard"]'); await p.waitForTimeout(Math.random() * 300); if (Math.random() < .4) await p.click('#tabs a[data-t="dashboard"]');
    await p.waitForTimeout(3500); n++;
    const info = await p.evaluate(() => { const ks = [...document.querySelectorAll(".kpi")]; return { n: ks.length, vis: ks.filter(k => { const r = k.getBoundingClientRect(), s = getComputedStyle(k); return r.height > 20 && +s.opacity > .9; }).length, map: !!document.querySelector(".uzmap .rg"), tiles: document.querySelectorAll("#tiles .tile").length, gauge: !!document.querySelector(".sidecol svg"), rt: document.querySelectorAll("#rt tr[data-id]").length, tab: document.querySelector("#tabs a.on")?.dataset.t, h: document.querySelector("main")?.innerText.slice(0, 40).replace(/\n/g, " ") }; });
    if (info.n !== 6 || info.vis !== 6 || !info.map || !info.gauge || info.tab !== "dashboard") { bad++; console.log(`run ${i}:`, JSON.stringify(info)); }
  }
  console.log(`broken ${bad} of ${n}; page errors: ${errs.length}`, [...new Set(errs)].slice(0, 4)); await b.close(); process.exit(bad || errs.length ? 1 : 0); })();
