// Finds what is still not translated in Uzbek mode: texts that went through t()/ts() with no Uzbek entry (window.MISSING) and Cyrillic text on the page
// (names of regions, facilities and people from the database are data and are allowed; look at the rest).
// Usage: BASE=http://localhost:8201 PASS=secret node tools/uzcheck.js [route ...]     (needs playwright and a server with demo data: python -m app.cli demo)
const { chromium } = require("playwright");
const BASE = process.env.BASE || "http://localhost:8000", PASS = process.env.PASS || "testpass123";
const ROUTES = process.argv.slice(2).length ? process.argv.slice(2) : ["dashboard", "messages", "forecast", "reports", "people", "export", "territories", "broadcast", "settings", "control", "indicators", "audit"];
const CYR = /[А-Яа-яЁё]/;
(async () => {
  const b = await chromium.launch(), ctx = await b.newContext({ viewport: { width: 1500, height: 900 } });
  await ctx.addCookies([{ name: "lang", value: process.env.LANG_CHECK || "uz", url: BASE }]);
  const p = await ctx.newPage(); p.on("pageerror", e => console.log("PAGE ERROR", e.message));
  await p.goto(BASE + "/login"); await p.fill('input[name="login"]', "admin"); await p.fill('input[name="password"]', PASS); await p.keyboard.press("Enter"); await p.waitForTimeout(1500);
  const seen = new Set(), missing = new Set();
  for (const r of ROUTES) {
    await p.goto(BASE + "/#/" + r); await p.waitForTimeout(1500);
    const res = await p.evaluate(() => {
      const out = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (w.nextNode()) { const n = w.currentNode, s = n.textContent.trim(); if (s && /[А-Яа-яЁё]/.test(s) && !["SCRIPT", "STYLE"].includes(n.parentElement.tagName)) out.push(s.slice(0, 120)); }
      document.querySelectorAll("[placeholder],[title],[aria-label]").forEach(e => ["placeholder", "title", "aria-label"].forEach(a => { const v = e.getAttribute(a); if (v && /[А-Яа-яЁё]/.test(v)) out.push(a + ": " + v.slice(0, 120)); }));
      return { cyr: out, miss: [...window.MISSING] };
    });
    console.log(`--- #/${r}: ${res.cyr.length} Cyrillic texts on the page`);
    res.cyr.forEach(s => { if (!seen.has(s)) { seen.add(s); console.log("   ", s); } });
    res.miss.forEach(s => missing.add(s));
  }
  console.log(`=== not in the dictionary (went through t()/ts()): ${missing.size}`); [...missing].forEach(s => console.log("   ", s.slice(0, 160)));
  await b.close();
})();
