const ICON_CHECK_CACHE = Object.create(null);

function extractUrlFromCssVar(val) {
  const m = String(val).match(/url\(["']?([^"')]+)["']?\)/i);
  return m && m[1] ? m[1] : null;
}

async function assetExists(url) {
  if (!url) return false;
  if (ICON_CHECK_CACHE[url] !== undefined) return ICON_CHECK_CACHE[url];
  try {
    const r = await fetch(url, { method: 'GET', credentials: 'same-origin', cache: 'no-store' });
    ICON_CHECK_CACHE[url] = !!r.ok;
    return ICON_CHECK_CACHE[url];
  } catch {
    ICON_CHECK_CACHE[url] = false;
    return false;
  }
}

export async function applyIcon({ root, button, varOn, varOff, isOn, fallbackEmoji }) {
  // Force fallback (emoji) if requested
  if (button && button.dataset && button.dataset.forceEmoji === '1') {
    button.textContent = fallbackEmoji;
    button.style.webkitMaskImage = '';
    button.style.maskImage = '';
    button.style.backgroundColor = 'transparent';
    button.style.color = 'var(--yrp-icon-color)';
    button.style.textIndent = '0';
    button.dataset.maskApplied = '0';
    return;
  }

  const varName = isOn ? varOn : varOff;
  const cs = getComputedStyle(root);
  const val = cs.getPropertyValue(varName) || root.style.getPropertyValue(varName) || '';
  const url = extractUrlFromCssVar(val);

  if (!url) {
    button.style.webkitMaskImage = '';
    button.style.maskImage = '';
    button.textContent = fallbackEmoji;
    button.style.backgroundColor = 'transparent';
    button.style.color = 'var(--yrp-icon-color)';
    button.style.textIndent = '0';
    button.dataset.maskApplied = '0';
    return;
  }

  const ok = await assetExists(url);
  if (ok) {
    button.textContent = '';
    const iconVar = `var(${varName})`;
    button.style.webkitMaskImage = iconVar;
    button.style.maskImage = iconVar;
    button.style.backgroundColor = 'var(--yrp-icon-color)';
    button.style.color = '';
    button.style.textIndent = '-9999px';
    button.dataset.maskApplied = '1';
  } else {
    button.style.webkitMaskImage = '';
    button.style.maskImage = '';
    button.textContent = fallbackEmoji;
    button.style.backgroundColor = 'transparent';
    button.style.color = 'var(--yrp-icon-color)';
    button.style.textIndent = '0';
    button.dataset.maskApplied = '0';
  }
}