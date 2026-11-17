// Browser walk-through. Run: BASE=http://localhost:8770 node tests/e2e/flow.js  (needs playwright and a database with demo data)
const { chromium } = require("playwright");
const BASE = process.env.BASE || "http://localhost:8770", OUT = process.env.OUT || "/tmp/fluserve/shots";
let fails = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };
(async () => {
  const b = await chromium.launch(); const errs = [];
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } }); const p = await ctx.newPage();
  p.on("pageerror", e => errs.push(e.message)); p.on("console", m => { if (m.type() === "error" && !/401|403|404|422/.test(m.text())) errs.push(m.text()); });
  await p.goto(BASE + "/login"); await p.fill("[name=login]", "admin"); await p.fill("[name=password]", "wrong"); await p.click("button.pri");
  ok(/Неверный/.test(await p.textContent(".err")), "wrong password shows an error");
  await p.fill("[name=password]", process.env.PW || "secret123"); await p.click("button.pri"); await p.waitForSelector(".kpi");
  await p.waitForTimeout(1500);
  ok(await p.locator(".kpi").count() === 6, "6 KPI cards in one row");
  ok(await p.locator("#rt tr[data-id]").count() === 14, "14 regions in the table");
  ok(!/^\s*0\/3\s*$/.test(await p.locator("#rt tr[data-id] td").nth(1).textContent()), "table shows the same day as the cards (not empty)");
  ok(await p.locator(".uzmap .rg").count() === 14, "map of Uzbekistan: 14 regions drawn");
  ok(await p.locator(".topgrid .sidecol .vcard").count() === 2 && await p.locator(".viz").count() === 0, "bed gauge and flow card stand to the right of the map, the ring card is gone");
  ok(await p.locator(".uzmap .rg.st-critical .gl").count() > 0 && await p.locator(".uzmap .rg.st-critical .ring").count() > 0, "critical regions pulse (glow + ripple)");
  await p.click('#map-m [data-m="severe"]'); await p.waitForTimeout(300);
  ok(await p.locator("#map-m .chip.on").textContent() === "Тяжёлые" && await p.locator("#map-side .mrow").count() > 0, "map metric switch redraws the map and the attention list");
  await p.screenshot({ path: OUT + "/1-dashboard.png", fullPage: true });
  await p.click("#rt tr[data-id]"); await p.waitForTimeout(700);
  ok((await p.textContent("#rt")).includes("Центральный район"), "drill-down to districts");
  await p.click("#rt tr[data-id]"); await p.waitForTimeout(700);
  ok((await p.textContent("#rt")).includes("Больница"), "drill-down to facilities");
  await p.click("#up0"); await p.waitForTimeout(500);
  await p.click('#rt th[data-s="name"]'); await p.waitForTimeout(300);
  await p.fill("#rt-q", "Андиж"); await p.waitForTimeout(300);
  ok(await p.locator("#rt tr[data-id]").count() === 1, "search narrows the table");
  await p.selectOption("#f-r", { index: 2 }); await p.waitForTimeout(1500); ok(await p.locator(".kpi").count() === 6, "region filter keeps the dashboard");
  for (const [n, sel] of [["forecast", "#fc h2"], ["control", "#ct table"], ["reports", "#rl table"], ["people", "#rq"], ["export", "[data-f]"], ["territories", "#tt table"], ["indicators", ".card h2"], ["settings", "#s-save"], ["audit", "table"]]) {
    await p.goto(BASE + "/#/" + n); await p.waitForSelector(sel); await p.waitForTimeout(900); await p.screenshot({ path: `${OUT}/2-${n}.png`, fullPage: true }); ok(true, "page " + n);
  }
  await p.goto(BASE + "/#/reports"); await p.waitForSelector("#rl tr[data-id]"); await p.click("#rl tr[data-id]"); await p.waitForSelector(".modal #m-ed");
  await p.screenshot({ path: OUT + "/3-report.png" }); await p.click("#m-ed"); await p.waitForSelector("#e-save");
  await p.fill('[data-code="beds_occupied"]', "99999"); await p.fill("#e-reason", "тест"); await p.click("#e-save"); await p.waitForTimeout(700);
  ok(await p.locator(".modal").count() === 1, "invalid figures keep the form open");
  await p.click(".modal .btn.right"); await p.waitForTimeout(300);
  ok(await p.locator(".modal").count() === 0, "modal Cancel button works (CSP blocks inline handlers)");
  const [dl] = await Promise.all([p.waitForEvent("download"), p.evaluate(() => { location.href = "/api/export?fmt=xlsx&d1=2026-01-01&d2=2026-12-31"; })]).catch(() => [null]);
  ok(!!dl, "excel downloads");
  const m = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }); const q = await m.newPage();
  await q.goto(BASE + "/login"); await q.fill("[name=login]", "admin"); await q.fill("[name=password]", process.env.PW || "secret123"); await q.click("button.pri"); await q.waitForSelector(".kpi"); await q.waitForTimeout(1200);
  await q.screenshot({ path: OUT + "/4-phone.png" });
  ok(!(await q.evaluate(() => document.documentElement.scrollWidth > 392)), "no horizontal page scroll on the phone");
  await b.close();
  console.log(errs.length ? "JS ERRORS:\n" + errs.join("\n") : "no JS errors"); console.log(fails ? fails + " FAILED" : "ALL PASS"); process.exit(fails ? 1 : 0);
})();
