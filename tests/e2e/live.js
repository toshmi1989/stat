// Auto-refresh: a report added from another process shows up on the open dashboard without a reload.
// Run: BASE=http://localhost:8770 PW=secret123 node tests/e2e/live.js (from the project root, with a demo database)
const { chromium } = require("playwright"); const { execFileSync } = require("child_process");
(async () => { const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage(); const errs = [];
  p.on("pageerror", e => errs.push(e.message));
  await p.goto((process.env.BASE || "http://localhost:8770") + "/login"); await p.fill("[name=login]","admin"); await p.fill("[name=password]",process.env.PW || "secret123"); await p.click("button.pri"); await p.waitForSelector(".kpi");
  await p.waitForTimeout(1500);
  const before = (await p.locator(".kpi .v").first().textContent()).replace(/\s+/g, " "); console.log("before:", before);
  await p.evaluate(() => { window.__marker = 1;
    // mark elements of every part of the dashboard: if a refresh redrew the page they would be replaced and lose the mark
    window.__marked = { kpi: document.querySelector(".kpi"), svg: document.querySelector(".uzmap"), region: document.querySelector(".uzmap .rg"), tile: document.querySelector("#tiles .tile"), rank: document.querySelector("#rank .rk"), row: document.querySelector("#rt tr[data-id]"), gauge: document.querySelector(".sidecol svg"), filter: document.querySelector("#f-r") };
    Object.entries(window.__marked).forEach(([k, el]) => { if (el) el.__mark = k; });
    window.__anim = document.getAnimations().length; }); await p.waitForTimeout(7000);
  // a report arrives from ANOTHER process (as from the bot)
  console.log(execFileSync("python3", ["tests/e2e/add_report.py"], { env: { ...process.env } }).toString().trim());
  await p.waitForFunction(() => /Данные обновлены/.test(document.getElementById("toast").textContent), null, { timeout: 15000 });
  await p.waitForTimeout(1200);
  const after = (await p.locator(".kpi .v").first().textContent()).replace(/\s+/g, " "); console.log("after:", after);
  const kept = await p.evaluate(() => Object.fromEntries(Object.entries(window.__marked).map(([k, el]) => [k, !!el && document.contains(el) && el.__mark === k])));
  console.log("same elements still in the page (nothing redrawn):", JSON.stringify(kept));
  const redrawn = Object.entries(kept).filter(([, v]) => !v).map(([k]) => k);
  console.log(redrawn.length ? "FAIL redrawn: " + redrawn.join(", ") : "PASS no element was replaced");
  if (redrawn.length) process.exitCode = 1;
  console.log("page not reloaded:", await p.evaluate(() => window.__marker === 1), "changed:", before !== after, "errors:", errs);
  await b.close(); })();
