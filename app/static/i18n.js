// Interface language: Uzbek (Latin, the default) or Russian. The Russian text is the key: t("Сохранить") gives "Saqlash" in Uzbek and the same
// Russian text in Russian (or when the Uzbek one is missing). Dictionaries live in i18n/uz-*.js and add themselves to window.UZ.
// Parameters: t("Получат {n} человек", { n: 5 }); a value is inserted as it is, so pass escaped text or HTML the way the template did before.
// Messages of the server (errors) come in Russian: ts() looks them up in UZ and then in UZP, patterns [RegExp, "Uzbek with $1"].
window.UZ = window.UZ || {};
window.UZP = window.UZP || [];
window.LANG = (document.cookie.match(/(?:^|; )lang=(ru|uz)/) || [])[1] || "uz";
window.LOCALE = LANG === "uz" ? "uz-Latn-UZ" : "ru-RU";
window.MISSING = window.MISSING || new Set();
function t(ru, p) {
  let s = ru;
  if (LANG === "uz") { const u = UZ[ru]; if (u !== undefined) s = u; else if (/[А-Яа-яЁё]/.test(ru)) MISSING.add(ru); }
  return p ? s.replace(/\{(\w+)\}/g, (m, k) => p[k] !== undefined && p[k] !== null ? p[k] : m) : s;
}
function ts(msg) {     // a message from the server
  if (LANG !== "uz" || !msg) return msg;
  if (UZ[msg] !== undefined) return UZ[msg];
  for (const [re, to] of UZP) if (re.test(msg)) return msg.replace(re, to);
  if (/[А-Яа-яЁё]/.test(msg)) MISSING.add(msg);
  return msg;
}
function setLang(l) { document.cookie = "lang=" + l + "; path=/; max-age=31536000; samesite=lax"; location.reload(); }
document.documentElement.lang = LANG;
// static texts of a page: <span data-i18n>Русский текст</span> (the text is the key); the language switch (#lang buttons) and the title
document.addEventListener("DOMContentLoaded", () => {
  document.title = t(document.title);
  document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.textContent.trim()); });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => { el.placeholder = t(el.placeholder); });
  document.querySelectorAll("#lang [data-l]").forEach(b => { b.classList.toggle("on", b.dataset.l === LANG); b.onclick = () => { if (b.dataset.l !== LANG) setLang(b.dataset.l); }; });
});
