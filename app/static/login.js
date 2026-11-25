// The language switch of the login page. A failed login is the answer of a POST, and a reload would send the form again: set the cookie and open the page with GET.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("#lang [data-l]").forEach(b => {
    b.onclick = () => { if (b.dataset.l !== LANG) { document.cookie = "lang=" + b.dataset.l + "; path=/; max-age=31536000; samesite=lax"; location.href = "/login"; } };
  });
});
