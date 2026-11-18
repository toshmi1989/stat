// «Ответственные (Telegram)» grouped by region. Run: BASE=http://localhost:8770 node tests/e2e/groups.js (a demo database with people)
const { chromium } = require("playwright");
(async () => { const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1300, height: 1000 } })).newPage(); const errs = []; let fails = 0;
  const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };
  p.on("pageerror", e => errs.push(e.message)); p.on("console", m => { if (m.type() === "error" && !/404/.test(m.text())) errs.push(m.text()); });
  await p.request.post((process.env.BASE || "http://localhost:8770") + "/login", { form: { login: "admin", password: "secret123" }, maxRedirects: 0 }).catch(() => {});
  await p.goto((process.env.BASE || "http://localhost:8770") + "/#/people"); await p.waitForSelector("#tgl .rgsum");
  console.log(await p.textContent("#tgl .rgsum"));
  const chips = await p.locator("#tgl .rgchips .chip").evaluateAll(es => es.map(e => e.textContent.trim().replace(/\s+/g, " ")));
  console.log(chips.join(" | "));
  const groups = await p.locator("#tgl details.rgrp").count(); ok(groups >= 5, "groups by region: " + groups);
  const sum = await p.locator("#tgl details.rgrp > summary .pill").evaluateAll(es => es.map(e => parseInt(e.textContent)));
  ok(sum.every(n => n > 0), "every group shows how many people: " + sum.join(","));
  // a person with facilities in two regions is listed in both
  const mad = await p.locator('#tgl tr[data-find*="мадина"]').count(); ok(mad >= 2, "a person with access in two regions appears in both groups (" + mad + ")");
  // chip opens its group
  const first = p.locator("#tgl .rgchips .chip:not([disabled])").first(); const id = await first.getAttribute("data-go"); await first.click();
  ok(await p.locator(`#tgl details[data-rg="${id}"]`).evaluate(d => d.open), "a region chip opens its group");
  // open state survives an action that reloads the list
  await p.click("#rg-open"); await p.locator("#tgl [data-tog]").first().click(); await p.waitForTimeout(800);
  ok(await p.locator("#tgl details.rgrp[open]").count() === groups, "the groups stay open after an action");
  await p.locator("#tgl [data-tog]").first().click(); await p.waitForTimeout(600);        // switch the person back
  // search
  await p.fill("#tg-q", "мадина"); ok(await p.locator('#tgl tr[data-find]:not([hidden])').count() === mad, "search shows only the person");
  await p.fill("#tg-q", ""); await p.click("#rg-close"); ok(await p.locator("#tgl details.rgrp[open]").count() === 0, "collapse all");
  await p.click("#rg-open"); await p.screenshot({ path: "/tmp/groups.png", fullPage: true });
  console.log("errors:", errs); await b.close(); process.exit(fails || errs.length ? 1 : 0); })();
