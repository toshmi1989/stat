// The «Охват» page: regions, districts, facilities, who is connected, reports sent. Run: BASE=http://localhost:8770 node tests/e2e/coverage.js (a demo database)
const { chromium } = require("playwright");
(async () => { const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1300, height: 900 } })).newPage(); const errs = []; let fails = 0;
  const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };
  p.on("pageerror", e => errs.push(e.message)); p.on("console", m => { if (m.type() === "error" && !/404/.test(m.text())) errs.push(m.text()); });
  await p.request.post((process.env.BASE || "http://localhost:8770") + "/login", { form: { login: "admin", password: "secret123" }, maxRedirects: 0 }).catch(() => {});
  await p.goto((process.env.BASE || "http://localhost:8770") + "/"); await p.waitForSelector('#tabs a[data-t="coverage"]'); await p.click('#tabs a[data-t="coverage"]'); await p.waitForSelector("tr.cvr");
  ok(await p.locator("tr.cvr").count() === 14, "14 regions in the table");
  ok(await p.locator(".cvk .kpi").count() === 5, "five totals");
  console.log((await p.locator(".cvk").innerText()).replace(/\s+/g, " "));
  await p.click('tr.cvr[data-rg="3"]'); ok(!(await p.locator('tr.cvd[data-d="3"]').isHidden()), "a region row opens its districts and facilities");
  ok(/Алишер Каримов/.test(await p.textContent('tr.cvd[data-d="3"]')) && /@alisher_k/.test(await p.textContent('tr.cvd[data-d="3"]')), "the whole-region person is shown with @username");
  await p.click("#cv-all"); await p.waitForTimeout(400); ok(await p.locator("tr.cvd:not([hidden])").count() === 14, "expand all");
  await p.click('#cv-p [data-n="29"]'); await p.waitForTimeout(500); ok(await p.locator("#cv-p .chip.on").textContent() === "30 дней", "the period presets work");
  const [dl] = await Promise.all([p.waitForEvent("download"), p.click('a:has-text("Скачать Excel")')]); ok(/coverage_.*\.xlsx/.test(dl.suggestedFilename()), "Excel download: " + dl.suggestedFilename());
  await p.screenshot({ path: "/tmp/coverage.png", fullPage: true });
  console.log("errors:", errs); await b.close(); process.exit(fails || errs.length ? 1 : 0); })();
