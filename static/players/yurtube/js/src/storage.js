const STORE = 'yrp:';

export function canLS() {
  try {
    localStorage.setItem('__t', '1');
    localStorage.removeItem('__t');
    return true;
  } catch {
    return false;
  }
}

export function load(key, def) {
  if (!canLS()) return def;
  try {
    const s = localStorage.getItem(STORE + key);
    return s ? JSON.parse(s) : def;
  } catch {
    return def;
  }
}

export function save(key, val) {
  if (!canLS()) return;
  try {
    localStorage.setItem(STORE + key, JSON.stringify(val));
  } catch {}
}