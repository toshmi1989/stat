// Records the film in one browser page. Needs: app on :8771 (demo data), static server on :8090 (this folder), playwright.
const { chromium } = require("playwright");
const path = require("path");
const APP = "http://localhost:8771", ST = "http://localhost:8090", OUT = process.env.OUT || "/tmp/vid/rec";
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: OUT, size: { width: 1280, height: 720 } } });
  await ctx.addInitScript({ path: path.join(__dirname, "overlay.js") });
  const p = await ctx.newPage(); p.on("pageerror", e => console.log("PAGEERR", e.message));
  const cap = async (t, s) => p.evaluate(([t, s]) => window.__cap && window.__cap(t, s), [t, s]);
  const hide = () => cap("", "");
  const move = async (sel, opt = {}) => { const el = p.locator(sel).first(); await el.scrollIntoViewIfNeeded().catch(() => {}); const r = await el.boundingBox(); if (!r) return; await p.mouse.move(r.x + r.width * (opt.fx ?? .5), r.y + r.height * (opt.fy ?? .5), { steps: 28 }); };
  const click = async (sel, opt) => { await move(sel, opt); await sleep(250); await p.mouse.down(); await p.mouse.up(); };
  const scroll = async y => { await p.evaluate(y => window.scrollTo({ top: y, behavior: "smooth" }), y); await sleep(1300); };
  const slide = async (kind, ms) => { await p.goto(`${ST}/slide.html?kind=${kind}`); await sleep(ms); };
  const chat = async (from, to) => { await p.goto(`${ST}/chat.html?from=${from}&to=${to || from}`); await p.waitForFunction(() => window.__done === true, null, { timeout: 180000 }); await sleep(500); };

  await slide("title", 5200);
  await slide("compare", 8200);
  for (const [f] of [["access"], ["submit"], ["fix"], ["download"], ["remind"]]) await chat(f);

  await slide("dash", 2600);
  // ---- login and the dashboard
  await p.goto(APP + "/login"); await sleep(600);
  await click("[name=login]"); await p.keyboard.type("admin", { delay: 70 }); await click("[name=password]"); await p.keyboard.type("secret123", { delay: 70 }); await sleep(300);
  await click("button.pri"); await p.waitForSelector(".kpi"); await sleep(2600);
  await cap("Вся республика на одном экране", "Карточки показателей, сдача отчётов, загрузка коек — за выбранный день");
  await move(".kpi:nth-child(3)"); await sleep(900); await move(".kpi:nth-child(7)", { fx: .2, fy: .3 }); await sleep(900); await move(".kpi:nth-child(11)", { fx: .8, fy: .7 }); await sleep(1200);
  await cap("Инфографика: что происходит прямо сейчас", "Кольцо — сколько учреждений сдали, спидометр — загрузка коек с зонами, баланс — поступили и выписаны");
  await scroll(330); await sleep(3200);
  await cap("Плитки регионов окрашены по загрузке коек", "Зелёный — норма, жёлтый — повышенная нагрузка, красный — критическая. Нажмите на плитку — откроется регион");
  await scroll(800); await sleep(1600); await move(".tile:nth-child(2)"); await sleep(1100); await move(".tile:nth-child(7)"); await sleep(1100);
  await cap("Регион — в один клик", "Фильтр применяется ко всей панели");
  await click(".tile:nth-child(1)"); await p.waitForTimeout(2200); await scroll(0); await sleep(2000);
  await cap("Сравнение регионов", "Включайте показатели и регионы кнопками — динамика строится сразу");
  await click("#f-reset"); await p.waitForTimeout(1800);
  await p.evaluate(() => document.querySelector("#dyn-m").scrollIntoView({ block: "center", behavior: "smooth" })); await sleep(1400);
  for (const r of [2, 3, 12]) { await click(`#dyn-r [data-r="${r}"]`); await sleep(1100); }
  await sleep(1600);

  // ---- forecast
  await cap("", ""); await p.goto(APP + "/#/forecast"); await p.waitForSelector("#fc h2"); await sleep(1500);
  await cap("Прогноз на 3 и 7 дней", "Показан метод и надёжность прогноза: низкая, средняя или высокая");
  await sleep(2800); await scroll(430); await sleep(2800);
  await cap("Прогноз загрузки коек и риск нехватки", "Система заранее подсказывает, где через 3 дня может не хватить мест"); await scroll(900); await sleep(3800);
  await cap("Предупреждения — приоритет: критические сверху", "Рост обращений, тяжёлые случаи, загрузка коек, учреждения без отчёта"); await scroll(1500); await sleep(3600);

  // ---- control
  await cap("", ""); await p.goto(APP + "/#/control"); await p.waitForSelector("#ct table"); await sleep(1200);
  await cap("Контроль сдачи: кто сдал, кто нет", "Статусы по цветам: отправлен, исправлен, возвращён, не отправлен, просрочен");
  await sleep(2600); await click('#c-f [data-v="not_sent"]'); await sleep(2800);

  // ---- reminder button
  await cap("", ""); await p.goto(APP + "/#/dashboard"); await p.waitForSelector(".cta"); await sleep(1800);
  await cap("Кто не сдал — видно сразу", "Одна кнопка — и все должники получают напоминание в Telegram");
  await sleep(2000); await click("#remind"); await p.waitForSelector("#rm-go"); await sleep(1800);
  await cap("Перед отправкой видно, кто получит сообщение", "А ещё — у каких учреждений нет ответственного"); await sleep(3600);
  await click("#rm-go"); await sleep(2800);
  await cap("Готово: напоминания отправлены", "Повторно одному человеку — не чаще раза в час"); await sleep(2600); await click(".modal .btn.pri"); await sleep(600);

  // ---- reports and history
  await cap("", ""); await p.goto(APP + "/#/reports"); await p.waitForSelector("#rl tr[data-id]"); await sleep(1200);
  await cap("Любую сводку можно открыть и проверить", "Исправления администратора — только с указанием причины"); await sleep(2200);
  await click("#rl tr[data-id]"); await p.waitForSelector(".modal"); await sleep(1500);
  await cap("История изменений хранится всегда", "Кто, когда и что исправил — стереть нельзя"); await sleep(3600);
  await click(".modal .btn.right"); await sleep(500);

  // ---- export
  await cap("", ""); await p.goto(APP + "/#/export"); await p.waitForSelector("[data-f]"); await sleep(1000);
  await cap("Выгрузка в Excel и PDF — в один клик", "Готовая форма для печати на A4 с полями для подписей"); await sleep(4200);
  await cap("", "");

  await slide("outro", 6200);
  await ctx.close(); await b.close();
  console.log("recorded");
})().catch(e => { console.error(e); process.exit(1); });
