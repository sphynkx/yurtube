/**
 * Subtitles module - manages subtitle/caption tracks and UI
 */

/**
 * Get English display name for a language code using Intl.DisplayNames
 */
let _langNamesEn = null;
function _getLangNamesEn() {
  if (_langNamesEn) return _langNamesEn;
  try {
    if (typeof Intl !== 'undefined' && Intl.DisplayNames) {
      _langNamesEn = new Intl.DisplayNames(['en'], { type: 'language' });
    }
  } catch {}
  return _langNamesEn;
}

export function langDisplayNameEn(code, fallbackLabel) {
  const raw = String(code || '').trim();
  if (!raw) return String(fallbackLabel || '');
  if (raw.toLowerCase() === 'auto') return 'Auto';

  // for Intl.DisplayNames we pass primary language subtag only
  const base = raw.split('-', 1)[0].toLowerCase();
  try {
    const dn = _getLangNamesEn();
    if (dn && typeof dn.of === 'function') {
      const name = dn.of(base);
      if (name) return name.charAt(0).toUpperCase() + name.slice(1);
    }
  } catch {}
  return String(fallbackLabel || raw);
}

/**
 * Get all subtitle/caption tracks from a video element
 */
export function subtitleTracks(video) {
  try {
    return video.textTracks ? Array.prototype.filter.call(video.textTracks, function (tr) {
      return tr.kind === 'subtitles' || tr.kind === 'captions';
    }) : [];
  } catch {
    return [];
  }
}

/**
 * Check if video has any subtitle tracks
 */
export function anySubtitleTracks(video) {
  return subtitleTracks(video).length > 0;
}

/**
 * Get the currently active track based on activeTrackIndex
 */
export function chooseActiveTrack(video, activeTrackIndex) {
  const subs = subtitleTracks(video);
  if (subs.length === 0) return null;
  const idx = (activeTrackIndex < 0 || activeTrackIndex >= subs.length) ? 0 : activeTrackIndex;
  return subs[idx];
}

/**
 * Apply track modes - set active track to 'hidden', others to 'disabled'
 */
export function applyPageModes(video, activeTrackIndex, overlayActive) {
  const subs = subtitleTracks(video);
  subs.forEach(function (tr, i) {
    tr.mode = (i === activeTrackIndex && overlayActive) ? 'hidden' : 'disabled';
  });
}

/**
 * Get current cue text from active track at video's current time
 */
export function currentCueText(video, activeTrackIndex) {
  const tr = chooseActiveTrack(video, activeTrackIndex);
  if (!tr || !tr.cues) return '';
  const ct = video.currentTime || 0;
  for (let i = 0; i < tr.cues.length; i++) {
    const c = tr.cues[i];
    if (ct >= c.startTime && ct <= c.endTime) return (c.text || '').replace(/\r/g, '');
  }
  return '';
}

/**
 * Get list of track info with language and labels
 */
export function trackInfoList(video) {
  const subs = subtitleTracks(video);
  return subs.map(function (tr, i) {
    // IMPORTANT: use srclang fallback (most browsers don't populate TextTrack.language reliably)
    const code = String(tr.language || tr.srclang || '').toLowerCase();
    const rawLabel = String(tr.label || code || ('Lang ' + (i + 1)));
    const label = langDisplayNameEn(code, rawLabel);
    return { index: i, lang: code, label: label };
  });
}

/**
 * Find track index by language code
 */
export function findTrackIndexByLang(video, code) {
  const c = String(code || '').toLowerCase();
  const list = trackInfoList(video);
  for (var i = 0; i < list.length; i++) {
    if (list[i].lang === c) return list[i].index;
    if (list[i].label.toLowerCase() === c) return list[i].index;
  }
  return -1;
}

/**
 * Build the subtitles submenu view (On/Off options)
 */
export function buildSubtitlesMenuView(menu, overlayActive, styleBackButton, ensureTransparentMenuButton) {
  if (!menu) return;

  while (menu.firstChild) menu.removeChild(menu.firstChild);

  const back = document.createElement('button');
  back.type = 'button';
  back.className = 'yrp-menu-item';
  back.setAttribute('data-action', 'back');
  back.textContent = '← Back';
  styleBackButton(back);
  menu.appendChild(back);

  const onBtn = document.createElement('button');
  onBtn.type = 'button';
  onBtn.className = 'yrp-menu-item';
  onBtn.setAttribute('data-action', 'subs-on');
  onBtn.textContent = 'On' + (overlayActive ? ' ✓' : '');
  ensureTransparentMenuButton(onBtn);
  menu.appendChild(onBtn);

  const offBtn = document.createElement('button');
  offBtn.type = 'button';
  offBtn.className = 'yrp-menu-item';
  offBtn.setAttribute('data-action', 'subs-off');
  offBtn.textContent = 'Off' + (!overlayActive ? ' ✓' : '');
  ensureTransparentMenuButton(offBtn);
  menu.appendChild(offBtn);
}

/**
 * Build the languages submenu view
 */
export function buildLangsMenuView(menu, video, activeTrackIndex, styleBackButton, ensureTransparentMenuButton, buildScrollableListContainer) {
  if (!menu) return;

  while (menu.firstChild) menu.removeChild(menu.firstChild);

  const back = document.createElement('button');
  back.type = 'button';
  back.className = 'yrp-menu-item';
  back.setAttribute('data-action', 'back');
  back.textContent = '← Back';
  styleBackButton(back);
  menu.appendChild(back);

  const sc = buildScrollableListContainer(back, menu);
  menu.appendChild(sc);

  const list = trackInfoList(video);
  const cur = chooseActiveTrack(video, activeTrackIndex);
  const curLang = (cur && (cur.language || cur.srclang)) ? String(cur.language || cur.srclang).toLowerCase() : '';

  const sorted = list.slice().sort(function (a, b) {
    const aa = (a.lang || '').toLowerCase();
    const bb = (b.lang || '').toLowerCase();
    if (aa === 'auto' && bb !== 'auto') return -1;
    if (bb === 'auto' && aa !== 'auto') return 1;
    return (a.label || '').localeCompare(b.label || '');
  });

  sorted.forEach(function (ti) {
    const it = document.createElement('button');
    it.type = 'button';
    it.className = 'yrp-menu-item';
    it.setAttribute('data-action', 'select-lang');
    it.setAttribute('data-lang', ti.lang || '');

    const suffix = ti.lang ? ` (${ti.lang})` : '';
    // Check if this is the current language - compare both by index and by language code
    const isCurrentLang = (ti.index === activeTrackIndex) || (ti.lang && curLang && ti.lang === curLang);
    it.textContent = ti.label + suffix + (isCurrentLang ? ' ✓' : '');

    ensureTransparentMenuButton(it);
    sc.appendChild(it);
  });

  if (!sorted.length) {
    const empty = document.createElement('div');
    empty.className = 'yrp-menu-title';
    empty.style.marginTop = '6px';
    empty.style.fontSize = '12px';
    empty.style.opacity = '0.8';
    empty.textContent = 'No subtitle tracks';
    sc.appendChild(empty);
  }
}

/**
 * Refresh the subtitles button state
 */
export function refreshSubtitlesBtn(btnSubtitles, video, overlayActive) {
  if (!btnSubtitles) return;
  const has = anySubtitleTracks(video);
  btnSubtitles.disabled = !has;
  btnSubtitles.style.visibility = has ? 'visible' : 'hidden';
  btnSubtitles.classList.toggle('no-tracks', !has);
  btnSubtitles.classList.toggle('has-tracks', has);
  btnSubtitles.classList.toggle('active', has && overlayActive);
  btnSubtitles.classList.toggle('disabled-track', has && !overlayActive);
  btnSubtitles.setAttribute('aria-pressed', overlayActive ? 'true' : 'false');
}

/**
 * Update overlay text with current cue
 */
export function updateOverlayText(hooks, video, activeTrackIndex, overlayActive) {
  if (!hooks || !hooks.textBox) return;
  hooks.textBox.textContent = overlayActive ? currentCueText(video, activeTrackIndex) : '';
}

/**
 * Log track information for debugging
 */
export function logTracks(video, d, prefix) {
  const subs = subtitleTracks(video);
  const info = subs.map(function (tr, i) {
    return {
      i: i,
      mode: tr.mode,
      label: tr.label,
      srclang: tr.language || tr.srclang,
      cues: tr.cues ? tr.cues.length : 0,
      kind: tr.kind
    };
  });
  d(prefix, info);
}
