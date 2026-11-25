// Checks the Uzbek dictionaries of the messages of the server and translates a list of messages the way the page does (TS() in Uzbek mode).
// Usage:  node tools/uzpcheck.js                      validates window.UZ / window.UZP (every regular expression, every $n of the replacement, no Cyrillic left in the Uzbek)
//         echo '["Нет данных", "..."]' | node tools/uzpcheck.js --ts     prints the JSON list of the translations
const fs = require("fs"), path = require("path"), vm = require("vm");
const root = path.join(__dirname, "..", "app", "static");
const win = { document: { cookie: "lang=uz", documentElement: {}, addEventListener() {} }, location: {} };
win.window = win;
vm.createContext(win);
for (const f of ["i18n.js", ...fs.readdirSync(path.join(root, "i18n")).filter(x => x.endsWith(".js")).sort().map(x => "i18n/" + x)]) vm.runInContext(fs.readFileSync(path.join(root, f), "utf8"), win, { filename: f });
const CYR = /[А-Яа-яЁё]/;
if (process.argv.includes("--ts")) {
  const input = JSON.parse(fs.readFileSync(0, "utf8"));
  console.log(JSON.stringify(input.map(m => vm.runInContext("TS", win)(m))));
} else {
  let bad = 0;
  const err = m => { bad++; console.log("ERROR", m); };
  for (const [k, v] of Object.entries(win.UZ)) if (CYR.test(v)) err("Cyrillic in the Uzbek text of " + JSON.stringify(k));
  win.UZP.forEach((p, i) => {
    if (!Array.isArray(p) || Object.prototype.toString.call(p[0]) !== "[object RegExp]" || !["string", "function"].includes(typeof p[1])) return err("UZP[" + i + "] is not [RegExp, string or function]");
    if (p[0].global || p[0].sticky) err("UZP[" + i + "] " + p[0] + " has the flag g or y: test() would keep its position between calls");
    if (typeof p[1] === "function") return;      // a replacement function (for example one that turns a region name into its Uzbek form): nothing to check statically
    const groups = new RegExp(p[0].source + "|").exec("").length - 1;
    for (const m of p[1].matchAll(/\$(\d)/g)) if (+m[1] < 1 || +m[1] > groups) err("UZP[" + i + "] " + p[0] + ": $" + m[1] + " but the expression has " + groups + " group(s)");
    if (CYR.test(p[1])) err("UZP[" + i + "] Cyrillic in the Uzbek text " + JSON.stringify(p[1]));
  });
  console.log(`${Object.keys(win.UZ).length} texts in UZ, ${win.UZP.length} patterns in UZP, ${bad} error(s)`);
  process.exit(bad ? 1 : 0);
}
