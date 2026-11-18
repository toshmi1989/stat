// The map changes its view by itself every 3 s, a picked view stays a minute (virtual clock). Run: BASE=http://localhost:8770 PW=secret123 node tests/e2e/mapauto.js (a demo database)
const { chromium } = require("playwright");
(async () => { const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1400, height: 900 } }); const p = await ctx.newPage(); const errs = []; let fails = 0;
  const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) fails++; };
  p.on("pageerror", e => errs.push(e.message));
  await p.clock.install();
  await p.request.post((process.env.BASE || "http://localhost:8770") + "/login", { form: { login: "admin", password: "secret123" }, maxRedirects: 0 }).catch(() => {});
  await p.goto((process.env.BASE || "http://localhost:8770") + "/"); await p.waitForSelector(".uzmap"); await p.clock.runFor(500);
  const on = () => p.locator("#map-m .chip.on").textContent();
  const first = await on(); ok(first === "Загрузка коек", "starts with the bed load: " + first);
  await p.clock.runFor(3100); const second = await on(); ok(second !== first, "changes by itself after 3 seconds: " + second);
  await p.clock.runFor(3100); const third = await on(); ok(third !== second, "and again: " + third);
  const names = new Set([first, second, third]); for (let i = 0; i < 4; i++) { await p.clock.runFor(3100); names.add(await on()); }
  ok(names.size === 5, "goes through all five views: " + [...names].join(", "));
  // pick one: it stays a minute
  await p.click('#map-m [data-m="severe"]'); const picked = await on(); ok(picked === "Тяжёлые", "the picked view is shown");
  await p.mouse.move(5, 5);
  await p.clock.runFor(30000); ok(await on() === "Тяжёлые", "still the picked view after 30 s");
  ok(/закреплён: ещё \d+ с/.test(await p.textContent("#map-cap")), "the caption counts down: " + (await p.textContent("#map-cap")).slice(0, 50));
  await p.clock.runFor(29000); ok(await on() === "Тяжёлые", "still the picked view after 59 s");
  await p.clock.runFor(5000); await p.clock.runFor(3100); ok(await on() !== "Тяжёлые", "after the minute the views change again: " + await on());
  // the pointer on the map stops the changing
  const cur = await on(); const box = await p.locator("#map").boundingBox(); await p.mouse.move(box.x + box.width / 3, box.y + box.height / 3);
  await p.clock.runFor(9000); ok(await on() === cur, "the view does not change while the pointer is on the map");
  console.log("errors:", errs); await b.close(); process.exit(fails || errs.length ? 1 : 0); })();
