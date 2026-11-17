// Auto-refresh: a report added from another process shows up on the open dashboard without a reload.
// Run: BASE=http://localhost:8770 PW=secret123 node tests/e2e/live.js (from the project root, with a demo database)
const { chromium } = require("playwright"); const { execFileSync } = require("child_process");
(async () => { const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage(); const errs = [];
  p.on("pageerror", e => errs.push(e.message));
  await p.goto((process.env.BASE || "http://localhost:8770") + "/login"); await p.fill("[name=login]","admin"); await p.fill("[name=password]",process.env.PW || "secret123"); await p.click("button.pri"); await p.waitForSelector(".kpi");
  await p.waitForTimeout(1500);
  const before = (await p.locator(".kpi .v").first().textContent()).replace(/\s+/g, " "); console.log("before:", before);
  await p.evaluate(() => { window.__marker = 1; }); await p.waitForTimeout(7000);
  // a report arrives from ANOTHER process (as from the bot)
  console.log(execFileSync("python3", ["tests/e2e/add_report.py"], { env: { ...process.env } }).toString().trim());
  await p.waitForFunction(() => /Данные обновлены/.test(document.getElementById("toast").textContent), null, { timeout: 15000 });
  await p.waitForTimeout(1200);
  const after = (await p.locator(".kpi .v").first().textContent()).replace(/\s+/g, " "); console.log("after:", after);
  console.log("page not reloaded:", await p.evaluate(() => window.__marker === 1), "changed:", before !== after, "errors:", errs);
  await b.close(); })();
