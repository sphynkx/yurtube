export function fmtTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  sec = Math.floor(sec);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (x) => (x < 10 ? '0' : '') + x;
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

export function clamp(v, min, max) {
  return v < min ? min : (v > max ? max : v);
}

export function cssPxToNum(s) {
  const v = parseFloat(String(s || '').trim());
  return isFinite(v) ? v : 0;
}

export function throttle(fn, ms) {
  let t = 0, pend = false, lastArgs = null, lastThis = null;
  return function (...args) {
    lastArgs = args; lastThis = this;
    const now = Date.now();
    if (!t || now - t >= ms) {
      t = now;
      fn.apply(lastThis, lastArgs);
    } else if (!pend) {
      pend = true;
      setTimeout(() => {
        pend = false;
        fn.apply(lastThis, lastArgs);
      }, ms - (now - t));
    }
  };
}

export function parseJSONAttr(el, name, fallback) {
  const s = el.getAttribute(name);
  if (!s) return fallback;
  try { return JSON.parse(s); } catch { return fallback; }
}

export function copyText(s) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(s).catch(() => {});
  } else {
    const ta = document.createElement('textarea');
    ta.value = s; ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch {}
    document.body.removeChild(ta);
  }
}