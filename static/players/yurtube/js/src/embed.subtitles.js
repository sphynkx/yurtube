/**
 * Subtitles/Captions functionality for embed player
 * Extracted from embed.core.js for better modularity
 */

/**
 * Get Intl.DisplayNames instance for English language names
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

/**
 * Get display name for language code in English
 */
export function langDisplayNameEn(code, fallbackLabel) {
  const raw = String(code || '').trim();
  if (!raw) return String(fallbackLabel || '');
  if (raw.toLowerCase() === 'auto') return 'Auto';
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
 * Get all subtitle/caption tracks from video element
 */
export function subtitleTracks(video) {
  try {
    return video.textTracks ? Array.prototype.filter.call(video.textTracks, function (tr) {
      return tr.kind === 'subtitles' || tr.kind === 'captions';
    }) : [];
  } catch { return []; }
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
export function applyTrackModes(video, activeTrackIndex, overlayActive) {
  const subs = subtitleTracks(video);
  subs.forEach(function (tr, i) {
    tr.mode = (i === activeTrackIndex && overlayActive) ? 'hidden' : 'disabled';
  });
}

/**
 * Get current cue text at video currentTime
 */
export function currentCueText(video, track) {
  if (!track || !track.cues || track.cues.length === 0) return '';
  const t = video.currentTime || 0;
  for (let i = 0; i < track.cues.length; i++) {
    const c = track.cues[i];
    if (t >= c.startTime && t <= c.endTime) return (c.text || '').replace(/\r/g, '');
  }
  return '';
}

/**
 * Get list of track info with language codes and labels
 */
export function trackInfoList(video) {
  const subs = subtitleTracks(video);
  return subs.map(function (tr, i) {
    // IMPORTANT: TextTrack.language is unreliable, prefer srclang fallback
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
  for (let i = 0; i < list.length; i++) {
    if (list[i].lang === c) return list[i].index;
    if (list[i].label.toLowerCase() === c) return list[i].index;
  }
  return -1;
}

/**
 * Build the subtitles on/off submenu view
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
    empty.textContent = 'No subtitles tracks';
    sc.appendChild(empty);
  }
}

/**
 * Refresh subtitle button UI based on track availability and state
 */
export function refreshSubtitlesBtnUI(ccBtn, video, overlayActive) {
  if (!ccBtn) return;
  const has = anySubtitleTracks(video);
  ccBtn.disabled = !has;
  ccBtn.style.visibility = has ? 'visible' : 'hidden';
  ccBtn.classList.toggle('no-tracks', !has);
  ccBtn.classList.toggle('has-tracks', has);
  ccBtn.classList.toggle('active', has && overlayActive);
  ccBtn.classList.toggle('disabled-track', has && !overlayActive);
  ccBtn.setAttribute('aria-pressed', overlayActive ? 'true' : 'false');
  ccBtn.title = overlayActive ? 'Subtitles: on' : 'Subtitles: off';
  ccBtn.setAttribute('aria-label', overlayActive ? 'Subtitles enabled' : 'Subtitles disabled');
}

/**
 * Update caption overlay text based on current track and time
 */
export function updateOverlayText(overlay, video, activeTrackIndex, overlayActive) {
  if (!overlay || !overlay.box) return;
  const tr = chooseActiveTrack(video, activeTrackIndex);
  applyTrackModes(video, activeTrackIndex, overlayActive);
  overlay.box.textContent = overlayActive ? currentCueText(video, tr) : '';
  overlay.layer.style.display = overlayActive ? '' : 'none';
}
