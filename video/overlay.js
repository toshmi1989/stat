// injected into the recorded pages: a fake cursor with click ripples and a caption bar
(() => {
  if (location.port !== "8771") return;
  const add = () => {
    const st = document.createElement("style");
    st.textContent = `#__cur{position:fixed;left:-50px;top:-50px;width:26px;height:26px;z-index:99999;pointer-events:none;transition:none;filter:drop-shadow(0 3px 4px rgba(0,0,0,.45))}
    .__rip{position:fixed;width:12px;height:12px;border-radius:50%;border:3px solid #3b6cf6;z-index:99998;pointer-events:none;transform:translate(-50%,-50%);animation:__r .6s ease-out forwards}
    @keyframes __r{to{width:70px;height:70px;opacity:0;border-width:1px}}
    #__cap{position:fixed;left:50%;bottom:26px;transform:translate(-50%,30px);opacity:0;z-index:99997;max-width:900px;padding:14px 26px;border-radius:18px;background:rgba(15,23,42,.92);color:#fff;font:600 20px/1.35 Inter,system-ui,sans-serif;text-align:center;box-shadow:0 14px 40px rgba(0,0,0,.4);transition:all .45s cubic-bezier(.2,.8,.2,1);pointer-events:none;backdrop-filter:blur(8px)}
    #__cap.on{opacity:1;transform:translate(-50%,0)}#__cap small{display:block;font-weight:400;font-size:16px;color:#c7d2e6;margin-top:3px}`;
    document.documentElement.appendChild(st);
    const cur = document.createElement("div"); cur.id = "__cur";
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l16 9-7 2-3 7z" fill="#fff" stroke="#111" stroke-width="1.5" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(cur);
    const cap = document.createElement("div"); cap.id = "__cap"; document.documentElement.appendChild(cap);
    addEventListener("mousemove", e => { cur.style.left = e.clientX - 3 + "px"; cur.style.top = e.clientY - 2 + "px"; }, true);
    addEventListener("mousedown", e => { const r = document.createElement("div"); r.className = "__rip"; r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px"; document.documentElement.appendChild(r); setTimeout(() => r.remove(), 700); }, true);
    window.__cap = (t, s) => { cap.innerHTML = t ? `${t}${s ? `<small>${s}</small>` : ""}` : ""; cap.classList.toggle("on", !!t); };
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", add); else add();
})();
