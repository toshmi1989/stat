// Records explain.html to a video. Needs a static server on :8090 serving this folder.
const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: process.env.OUT || "/tmp/vid/rec4", size: { width: 1280, height: 720 } } });
  const p = await ctx.newPage();
  await p.goto("http://localhost:8090/explain.html");
  await p.waitForFunction(() => window.__done === true, null, { timeout: 240000 });
  await p.waitForTimeout(600); await ctx.close(); await b.close(); console.log("recorded");
})().catch(e => { console.error(e); process.exit(1); });
