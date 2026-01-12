import { fmtTime, clamp, cssPxToNum, throttle, parseJSONAttr, copyText } from './util.js';
import { load, save } from './storage.js';
import { installFallbackGuards } from './fallback.js';
import { attachPlaylist } from './playlist.js';
import {
  subtitleTracks,
  anySubtitleTracks,
  chooseActiveTrack,
  applyPageModes,
  currentCueText,
  trackInfoList,
  findTrackIndexByLang,
  buildSubtitlesMenuView,
  buildLangsMenuView,
  refreshSubtitlesBtn,
  updateOverlayText,
  logTracks
} from './player.subtitles.js';
import {
  ensureTransparentMenuButton,
  styleBackButton,
  withSubmenuChevron,
  buildScrollableListContainer,
  normalizeQualitySectionTypography,
  removeFutureSubtitlesSection,
  insertMainEntry,
  speedOptions,
  buildSpeedMenuView,
  applySpeed,
  MenuManager
} from './player.menu.js';

function detectPlayerName() {
  try {
    const u = new URL(import.meta.url);
    const m = u.pathname.match(/\/static\/players\/([^\/]+)\//);
    if (m) return m[1];
  } catch {}
  try {
    const s = (document.currentScript && document.currentScript.src) || '';
    const m2 = s.match(/\/static\/players\/([^\/]+)\//);
    if (m2) return m2[1];
  } catch {}
  try {
    const host = document.querySelector('.player-host[data-player]');
    if (host) {
      const pn = String(host.getAttribute('data-player') || '').trim();
      if (pn) return pn;
    }
  } catch {}
  return 'yurtube';
}

export function initAll() {
  const NAME = detectPlayerName();
  const BASE = `/static/players/${NAME}`;
  const hosts = document.querySelectorAll(`.player-host[data-player="${NAME}"]`);
  if (!hosts.length) return;

  fetch(BASE + '/templates/player.html', { credentials: 'same-origin' })
    .then(r => r.text())
    .then(function (html) {
      for (let i = 0; i < hosts.length; i++) mountOne(hosts[i], html, BASE);
    })
    .catch(function () {});
}

function fmtDebug(debug, ...args) {
  if (!debug) return;
  try { console.debug('[YRP]', ...args); } catch {}
}

function mountOne(host, tpl, BASE) {
  host.innerHTML = tpl;

  const root = host.querySelector('.yrp-container');
  const vw = root.querySelector('.yrp-video-wrap');
  const video = root.querySelector('.yrp-video');
  const source = video.querySelector('source');

  const videoSrc = host.getAttribute('data-video-src') || '';
  const poster = host.getAttribute('data-poster-url') || '';
  const vid = host.getAttribute('data-video-id') || '';
  const subs = parseJSONAttr(host, 'data-subtitles', []);
  const opts = parseJSONAttr(host, 'data-options', {});
  const spritesVtt = host.getAttribute('data-sprites-vtt') || '';
  const captionVtt = host.getAttribute('data-caption-vtt') || '';
  const captionLang = host.getAttribute('data-caption-lang') || '';
  const DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);

  const d = (...a) => fmtDebug(DEBUG, ...a);

  if (source) source.setAttribute('src', videoSrc);
  if (poster) video.setAttribute('poster', poster);
  if (opts.autoplay) video.setAttribute('autoplay', '');
  if (opts.muted) video.setAttribute('muted', '');
  if (opts.loop) video.setAttribute('loop', '');
  if (vid) root.setAttribute('data-video-id', vid);
  if (spritesVtt) root.setAttribute('data-sprites-vtt', spritesVtt);
  video.setAttribute('playsinline', '');

  if (Array.isArray(subs)) {
    subs.forEach(function (t) {
      if (!t || !t.src) return;
      const tr = document.createElement('track');
      tr.setAttribute('kind', 'captions');
      if (t.srclang) tr.setAttribute('srclang', String(t.srclang));
      if (t.label) tr.setAttribute('label', String(t.label));
      tr.setAttribute('src', String(t.src));
      if (t.default) tr.setAttribute('default', '');
      video.appendChild(tr);
    });
  }

  if (captionVtt) {
    try {
      const ctr = document.createElement('track');
      ctr.setAttribute('kind', 'captions');
      ctr.setAttribute('src', captionVtt);
      ctr.setAttribute('srclang', captionLang || 'auto');
      ctr.setAttribute('label', captionLang || 'Original');
      ctr.setAttribute('default', '');
      video.appendChild(ctr);
    } catch (e) {
      d('caption append failed', e);
    }
  }

  try {
    video.load();
    d('video.load()', { src: videoSrc });
  } catch (e) {
    d('video.load() error', e);
  }

  installFallbackGuards(video, source, d);

  const iconBase = BASE + '/img/buttons';
  [
    ['--icon-play', 'play.svg'],
    ['--icon-pause', 'pause.svg'],
    ['--icon-prev', 'prev.svg'],
    ['--icon-next', 'next.svg'],
    ['--icon-vol', 'volume.svg'],
    ['--icon-mute', 'mute.svg'],
    ['--icon-cc', 'cc.svg'],
    ['--icon-mini', 'mini.svg'],
    ['--icon-settings', 'settings.svg'],
    ['--icon-theater', 'theater.svg'],
    ['--icon-full', 'full.svg'],
    ['--icon-autoplay-on', 'autoplay-on.svg'],
    ['--icon-autoplay-off', 'autoplay-off.svg'],
    ['--icon-shuffle-on', 'shuffle-on.svg'],
    ['--icon-shuffle-off', 'shuffle-off.svg'],
    ['--icon-cycle-on', 'cycle-on.svg'],
    ['--icon-cycle-off', 'cycle-off.svg']
  ].forEach(([varName, file]) => {
    root.style.setProperty(varName, `url("${iconBase}/${file}")`);
  });

  root.classList.add('yrp-icons-ready');

  const centerLogo = root.querySelector('.yrp-center-logo');
  if (centerLogo) centerLogo.setAttribute('src', BASE + '/img/logo.png');

  const overlay = document.createElement('div');
  overlay.className = 'yrp-captions-layer';
  Object.assign(overlay.style, {
    position: 'absolute',
    left: '50%',
    top: '80%',
    transform: 'translate(-50%,-50%)',
    zIndex: '21',
    pointerEvents: 'auto',
    userSelect: 'none',
    touchAction: 'none'
  });

  const textBox = document.createElement('div');
  textBox.className = 'yrp-captions-text';
  Object.assign(textBox.style, {
    display: 'inline-block',
    background: 'rgba(0,0,0,0.55)',
    color: '#fff',
    fontSize: '16px',
    lineHeight: '1.35',
    padding: '6px 10px',
    borderRadius: '6px',
    maxWidth: '80%',
    minWidth: '220px',
    boxShadow: '0 2px 6px rgba(0,0,0,0.35)',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word'
  });
  overlay.appendChild(textBox);

  if (vw) {
    vw.style.position = 'relative';
    vw.appendChild(overlay);
  }

  const dragState = { active: false, startX: 0, startY: 0, startLeftPct: 50, startTopPct: 80 };
  let userMoved = false;

  function getVideoWrapRect() {
    return vw ? vw.getBoundingClientRect() : { width: 0, height: 0, left: 0, top: 0 };
  }
  function updateTextBoxMaxWidthByCenter(cx) {
    const r = getVideoWrapRect();
    const avail = Math.min(cx, r.width - cx) * 2;
    const pad = 12, minW = 220;
    textBox.style.maxWidth = Math.max(minW, Math.floor(avail - pad)) + 'px';
  }
  function startDrag(e) {
    const t = e.touches ? e.touches[0] : e;
    const r = getVideoWrapRect();
    const ov = overlay.getBoundingClientRect();
    dragState.startLeftPct = ((ov.left + ov.width / 2) - r.left) / r.width * 100;
    dragState.startTopPct = ((ov.top + ov.height / 2) - r.top) / r.height * 100;
    dragState.active = true;
    dragState.startX = t.clientX;
    dragState.startY = t.clientY;
    e.preventDefault(); e.stopPropagation();
  }
  function moveDrag(e) {
    if (!dragState.active) return;
    const t = e.touches ? e.touches[0] : e;
    const dx = t.clientX - dragState.startX;
    const dy = t.clientY - dragState.startY;
    const r = getVideoWrapRect();
    let newLeftPx = (dragState.startLeftPct / 100) * r.width + dx;
    let newTopPx = (dragState.startTopPct / 100) * r.height + dy;
    const ov = overlay.getBoundingClientRect();
    const halfW = ov.width / 2, halfH = ov.height / 2;
    newLeftPx = clamp(newLeftPx, halfW, r.width - halfW);
    newTopPx = clamp(newTopPx, halfH, r.height - halfH);
    overlay.style.left = (newLeftPx / r.width * 100) + '%';
    overlay.style.top = (newTopPx / r.height * 100) + '%';
    overlay.style.transform = 'translate(-50%,-50%)';
    userMoved = true;
    updateTextBoxMaxWidthByCenter(newLeftPx);
    e.preventDefault(); e.stopPropagation();
  }
  function endDrag(e) {
    if (dragState.active) {
      dragState.active = false;
      e.preventDefault(); e.stopPropagation();
    }
  }

  overlay.addEventListener('mousedown', startDrag);
  overlay.addEventListener('touchstart', startDrag, { passive: false });
  document.addEventListener('mousemove', moveDrag);
  document.addEventListener('touchmove', moveDrag, { passive: false });
  document.addEventListener('mouseup', endDrag);
  document.addEventListener('touchend', endDrag);
  overlay.addEventListener('click', function (e) { e.stopPropagation(); });

  function adjustOverlayAuto() {
    if (userMoved) return;
    const controlsVisible = !root.classList.contains('autohide');
    overlay.style.top = controlsVisible ? '78%' : '82%';
    overlay.style.left = '50%';
    overlay.style.transform = 'translate(-50%,-50%)';
    updateTextBoxMaxWidthByCenter(getVideoWrapRect().width / 2);
  }

  let startAt = 0;
  if (typeof opts.start === 'number' && opts.start > 0) startAt = Math.max(0, opts.start);
  try {
    const uWatch = new URL(window.location.href);
    const tParam = uWatch.searchParams.get('t');
    if (tParam != null) {
      const tNum = parseInt(String(tParam).trim(), 10);
      if (isFinite(tNum) && tNum > 0) startAt = Math.max(startAt, tNum);
    }
  } catch {}

  wire(root, startAt, DEBUG, { overlay, textBox, autoAdjust: adjustOverlayAuto }, startAt, BASE);
}

export function wire(root, startAt, DEBUG, hooks, startFromUrl, BASE) {
  const d = (...a) => fmtDebug(DEBUG, ...a);

  const video = root.querySelector('.yrp-video');
  const centerPlay = root.querySelector('.yrp-center-play');
  const btnPlay = root.querySelector('.yrp-play');
  const btnPrev = root.querySelector('.yrp-prev');
  const btnNext = root.querySelector('.yrp-next');
  const btnVol = root.querySelector('.yrp-vol-btn');
  const vol = root.querySelector('.yrp-volume');
  const volSlider = root.querySelector('.yrp-vol-slider');
  const tCur = root.querySelector('.yrp-time-current');
  const tTot = root.querySelector('.yrp-time-total');
  const progress = root.querySelector('.yrp-progress');
  const rail = root.querySelector('.yrp-progress-rail');
  const buf = root.querySelector('.yrp-progress-buffer');
  const played = root.querySelector('.yrp-progress-played');
  const handle = root.querySelector('.yrp-progress-handle');
  const tooltip = root.querySelector('.yrp-progress-tooltip');
  const btnSettings = root.querySelector('.yrp-settings');
  const menu = root.querySelector('.yrp-menu');
  const btnTheater = root.querySelector('.yrp-theater');
  const btnFull = root.querySelector('.yrp-fullscreen');
  const btnPip = root.querySelector('.yrp-pip');
  const leftGrp = root.querySelector('.yrp-left');
  const rightGrp = root.querySelector('.yrp-right');
  const btnAutoplay = root.querySelector('.yrp-autoplay');
  const btnSubtitles = root.querySelector('.yrp-subtitles');

  let hideTimer = null, seeking = false, duration = 0;
  let userTouchedVolume = false, autoMuteApplied = false;
  let pipInSystem = false, pipWasPlayingOrig = false, pipWasMutedOrig = false, pipUserState = null;
  let autoplayOn = !!load('autoplay', false);
  const spritesVttUrl = root.getAttribute('data-sprites-vtt') || '';
  let spriteCues = [], spriteDurationApprox = 0, spritePop = null, spritesLoaded = false, spritesLoadError = false;

  let overlayActive = true;
  let activeTrackIndex = 0;

  let prefLang = (function(){ try { return String(localStorage.getItem('subtitle_lang') || ''); } catch (_) { return ''; } })();
  let prefSpeed = (function(){ try { return parseFloat(localStorage.getItem('playback_speed') || ''); } catch (_) { return NaN; } })();

  // Menu manager
  const menuManager = new MenuManager(menu);
  let menuBound = false;


  function selectSubtitleLang(code) {
    const idx = findTrackIndexByLang(video, code);
    if (idx >= 0) {
      activeTrackIndex = idx;
      overlayActive = true;
      applyPageModes(video, activeTrackIndex, overlayActive);
      updateOverlayText(hooks, video, activeTrackIndex, overlayActive);
      try { localStorage.setItem('subtitle_lang', String(code || '')); } catch (_){}
      refreshSubtitlesBtn(btnSubtitles, video, overlayActive);
    }
  }

  function setSubtitlesEnabled(flag) {
    overlayActive = !!flag;
    applyPageModes(video, activeTrackIndex, overlayActive);
    updateOverlayText(hooks, video, activeTrackIndex, overlayActive);
    refreshSubtitlesBtn(btnSubtitles, video, overlayActive);
  }

  function openMainMenuView() {
    menuManager.openMainView({
      injectSpeed: injectSpeedEntryIntoMain,
      injectLanguages: injectLanguagesEntryIntoMain,
      injectSubtitles: injectSubtitlesEntryIntoMain
    });
  }

  function injectLanguagesEntryIntoMain() {
    if (!menu) return;
    if (menu.querySelector('.yrp-menu-item[data-action="open-langs"]')) return;
    insertMainEntry(menu, 'Languages', 'open-langs', { hasSubmenu: true }, ensureTransparentMenuButton, withSubmenuChevron);
  }

  function injectSpeedEntryIntoMain() {
    if (!menu) return;
    if (menu.querySelector('.yrp-menu-item[data-action="open-speed"]')) return;
    insertMainEntry(menu, 'Speed', 'open-speed', { hasSubmenu: true }, ensureTransparentMenuButton, withSubmenuChevron);
  }

  function injectSubtitlesEntryIntoMain() {
    if (!menu) return;
    if (menu.querySelector('.yrp-menu-item[data-action="open-subs"]')) return;

    const has = anySubtitleTracks(video);
    const btn = insertMainEntry(menu, 'Subtitles', 'open-subs', { hasSubmenu: true, disabled: !has }, ensureTransparentMenuButton, withSubmenuChevron);
    if (btn && !has) btn.title = 'No subtitle tracks';
  }

  function wrappedBuildLangsMenuView() {
    buildLangsMenuView(menu, video, activeTrackIndex, styleBackButton, ensureTransparentMenuButton, buildScrollableListContainer);
    menuManager.setView('langs');
    menuManager.constrainToPlayerHeight(2/3); // Limit to 2/3 of player height
  }

  function wrappedBuildSpeedMenuView() {
    buildSpeedMenuView(menu, video, styleBackButton, ensureTransparentMenuButton);
    menuManager.setView('speed');
    menuManager.constrainToPlayerHeight(2/3); // Limit to 2/3 of player height
  }

  function wrappedBuildSubtitlesMenuView() {
    buildSubtitlesMenuView(menu, overlayActive, styleBackButton, ensureTransparentMenuButton);
    menuManager.setView('subs');
    menuManager.constrainToPlayerHeight(2/3); // Limit to 2/3 of player height
  }

  function applyIcon(button, varOn, varOff, isOn, fallbackEmoji) {
    const varName = isOn ? varOn : varOff;
    const cs = getComputedStyle(root);
    const val = cs.getPropertyValue(varName) || root.style.getPropertyValue(varName) || '';
    const m = String(val).match(/url\(["']?([^"')]+)["']?\)/i);
    const url = m && m[1] ? m[1] : null;
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
    button.textContent = '';
    const iconVar = `var(${varName})`;
    button.style.webkitMaskImage = iconVar;
    button.style.maskImage = iconVar;
    button.style.backgroundColor = 'var(--yrp-icon-color)';
    button.style.color = '';
    button.style.textIndent = '-9999px';
    button.dataset.maskApplied = '1';
  }

  function ensureSpritePop() {
    if (spritePop) return spritePop;
    if (!progress) return null;
    spritePop = document.createElement('div');
    Object.assign(spritePop.style, {
      position: 'absolute',
      display: 'none',
      bottom: 'calc(100% + 30px)',
      left: '0',
      width: '160px',
      height: '90px',
      border: '1px solid #333',
      background: '#000',
      overflow: 'hidden',
      zIndex: '5'
    });
    spritePop.className = 'yrp-sprite-pop';
    if (getComputedStyle(progress).position === 'static') progress.style.position = 'relative';
    progress.appendChild(spritePop);
    return spritePop;
  }
  function parseTimestamp(ts) {
    const m = String(ts || '').match(/^(\d{2}):(\d{2}):(\d{2}\.\d{3})$/);
    if (!m) return 0;
    return parseInt(m[1], 10) * 3600 + parseInt(m[2], 10) * 60 + parseFloat(m[3]);
  }
  function buildAbsoluteSpriteUrl(rel) {
    if (!rel) return '';
    try {
      const vttAbs = new URL(spritesVttUrl, window.location.href);
      return new URL(rel, vttAbs).href;
    } catch { return rel; }
  }
  function loadSpritesVTT() {
    if (!spritesVttUrl || spritesLoaded || spritesLoadError) return;
    let vttUrlAbs = '';
    try { vttUrlAbs = new URL(spritesVttUrl, window.location.href).href; } catch { vttUrlAbs = spritesVttUrl; }
    fetch(vttUrlAbs, { credentials: 'same-origin' })
      .then(r => r.text())
      .then(function (text) {
        const lines = text.split(/\r?\n/);
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;
          if (line.indexOf('-->') >= 0) {
            const parts = line.split('-->').map(s => s.trim());
            if (parts.length < 2) continue;
            const start = parseTimestamp(parts[0]), end = parseTimestamp(parts[1]);
            const ref = (lines[i + 1] || '').trim();
            let spriteRel = '', x = 0, y = 0, w = 0, h = 0;
            const hashIdx = ref.indexOf('#xywh=');
            if (hashIdx > 0) {
              spriteRel = ref.substring(0, hashIdx);
              const xywh = ref.substring(hashIdx + 6).split(',');
              if (xywh.length === 4) {
                x = parseInt(xywh[0], 10);
                y = parseInt(xywh[1], 10);
                w = parseInt(xywh[2], 10);
                h = parseInt(xywh[3], 10);
              }
            } else {
              spriteRel = ref || '';
            }
            const abs = buildAbsoluteSpriteUrl(spriteRel);
            spriteCues.push({ start, end, spriteUrl: abs, x, y, w, h });
            if (end > spriteDurationApprox) spriteDurationApprox = end;
            i++;
          }
        }
        spritesLoaded = true;
      })
      .catch(function () { spritesLoadError = true; });
  }
  function showSpritePreviewAtClientX(clientX) {
    if (!spritesVttUrl || !spriteCues.length || !rail) return;
    const rect = rail.getBoundingClientRect();
    const x = clamp(clientX - rect.left, 0, rect.width);
    const frac = rect.width > 0 ? x / rect.width : 0;
    const t = (duration || spriteDurationApprox || 0) * frac;
    let cue = null;
    for (let i = 0; i < spriteCues.length; i++) {
      const c = spriteCues[i];
      if (t >= c.start && t < c.end) { cue = c; break; }
    }
    const pop = ensureSpritePop();
    if (!pop) return;
    if (!cue || !cue.spriteUrl || cue.w <= 0 || cue.h <= 0) { pop.style.display = 'none'; return; }
    while (pop.firstChild) pop.removeChild(pop.firstChild);
    const img = document.createElement('img');
    Object.assign(img.style, { position: 'absolute', left: (-cue.x) + 'px', top: (-cue.y) + 'px' });
    img.src = cue.spriteUrl;
    pop.appendChild(img);
    pop.style.display = 'block';
    const leftPx = clamp(x - cue.w / 2, 0, rect.width - cue.w);
    pop.style.left = leftPx + 'px';
    pop.style.width = cue.w + 'px';
    pop.style.height = cue.h + 'px';
  }

  function refreshAutoplayBtn() {
    if (!btnAutoplay) return;
    const on = autoplayOn;
    btnAutoplay.setAttribute('aria-pressed', on ? 'true' : 'false');
    btnAutoplay.title = on ? 'Autoplay on (A)' : 'Autoplay off (A)';
    btnAutoplay.textContent = '';
    const iconVar = on ? 'var(--icon-autoplay-on)' : 'var(--icon-autoplay-off)';
    Object.assign(btnAutoplay.style, {
      backgroundColor: 'currentColor',
      webkitMaskImage: iconVar,
      maskImage: iconVar,
      webkitMaskRepeat: 'no-repeat',
      maskRepeat: 'no-repeat',
      webkitMaskPosition: 'center',
      maskPosition: 'center',
      webkitMaskSize: '20px 20px',
      maskSize: '20px 20px',
      opacity: on ? '1' : '0.6'
    });
  }
  function refreshPlayBtn() {
    if (!btnPlay) return;
    const playing = !video.paused;
    btnPlay.classList.toggle('icon-play', !playing);
    btnPlay.classList.toggle('icon-pause', playing);
    btnPlay.setAttribute('aria-label', playing ? 'Pause (Space, K)' : 'Play (Space, K)');
    btnPlay.title = playing ? 'Pause (Space, K)' : 'Play (Space, K)';
    btnPlay.textContent = '';
    const iconVar = playing ? 'var(--icon-pause)' : 'var(--icon-play)';
    Object.assign(btnPlay.style, {
      backgroundColor: 'currentColor',
      webkitMaskImage: iconVar,
      maskImage: iconVar,
      webkitMaskRepeat: 'no-repeat',
      maskRepeat: 'no-repeat',
      webkitMaskPosition: 'center',
      maskPosition: 'center',
      webkitMaskSize: '20px 20px',
      maskSize: '20px 20px'
    });
  }
  function scheduleAutoHide(ms) {
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(function () {
      root.classList.add('autohide');
      hooks && hooks.autoAdjust && hooks.autoAdjust();
    }, Math.max(0, ms || 1200));
  }
  function showControls() {
    root.classList.remove('autohide');
    hooks && hooks.autoAdjust && hooks.autoAdjust();
    scheduleAutoHide(2000);
  }
  function updateTimes() {
    try { duration = isFinite(video.duration) ? video.duration : 0; } catch { duration = 0; }
    if (tTot) tTot.textContent = fmtTime(duration);
    if (tCur) tCur.textContent = fmtTime(video.currentTime || 0);
  }
  function updateProgress() {
    const d = duration || 0, ct = video.currentTime || 0, f = d > 0 ? clamp(ct / d, 0, 1) : 0;
    if (played) played.style.width = (f * 100).toFixed(3) + '%';
    if (handle) handle.style.left = (f * 100).toFixed(3) + '%';
    let b = 0;
    if (video.buffered && video.buffered.length > 0) { try { b = video.buffered.end(video.buffered.length - 1); } catch { b = 0; } }
    const bf = d > 0 ? clamp(b / d, 0, 1) : 0;
    if (buf) buf.style.width = (bf * 100).toFixed(3) + '%';
  }

  function playToggle() { if (video.paused) video.play().catch(() => {}); else video.pause(); }
  function setMutedToggle() { video.muted = !video.muted; refreshVolIcon(); }
  function refreshVolIcon() {
    const v = video.muted ? 0 : video.volume;
    const label = (video.muted || v === 0) ? 'Mute' : 'Vol';
    if (btnVol) {
      btnVol.textContent = label;
      btnVol.classList.toggle('icon-mute', label === 'Mute');
      btnVol.classList.toggle('icon-vol', label !== 'Mute');
    }
  }
  function seekByClientX(xClient) {
    if (!rail) return;
    const rect = rail.getBoundingClientRect();
    const x = clamp(xClient - rect.left, 0, rect.width);
    const f = rect.width > 0 ? x / rect.width : 0;
    video.currentTime = (duration || 0) * f;
  }
  function updateTooltip(xClient) {
    if (!tooltip || !rail) return;
    const rect = rail.getBoundingClientRect();
    const x = clamp(xClient - rect.left, 0, rect.width);
    const f = rect.width > 0 ? x / rect.width : 0;
    const t = (duration || 0) * f;
    tooltip.textContent = fmtTime(t);
    tooltip.style.left = (f * 100).toFixed(3) + '%';
    tooltip.hidden = false;
  }

  (function resumePosition() {
    const vid = root.getAttribute('data-video-id') || '';
    if (!vid) return;

    if (startFromUrl > 0) {
      try {
        const s0 = load('resume', {});
        if (s0 && s0[vid]) { delete s0[vid]; save('resume', s0); }
      } catch {}
      return;
    }

    const map = load('resume', {}), rec = map[vid], now = Date.now();
    function applyResume(t) {
      const d = isFinite(video.duration) ? video.duration : 0;
      if (d && t > 10 && t < d - 5) { try { video.currentTime = t; } catch {} }
    }
    if (rec && typeof rec.t === 'number' && (now - (rec.ts || 0)) < 180 * 24 * 3600 * 1000) {
      const setAt = Math.max(0, rec.t | 0);
      if (isFinite(video.duration) && video.duration > 0) applyResume(setAt);
      else video.addEventListener('loadedmetadata', function once() { video.removeEventListener('loadedmetadata', once); applyResume(setAt); });
    }

    const savePos = throttle(function () {
      const d = isFinite(video.duration) ? video.duration : 0;
      const cur = Math.max(0, Math.floor(video.currentTime || 0));
      const m = load('resume', {});
      m[vid] = { t: cur, ts: Date.now(), d };
      const keys = Object.keys(m);
      if (keys.length > 200) {
        keys.sort((a, b) => (m[a].ts || 0) - (m[b].ts || 0));
        for (let i = 0; i < keys.length - 200; i++) delete m[keys[i]];
      }
      save('resume', m);
    }, 3000);

    video.addEventListener('timeupdate', function () { if (!video.paused && !video.seeking) savePos(); });
    video.addEventListener('ended', function () { const m = load('resume', {}); delete m[vid]; save('resume', m); });
  })();

  (function theaterInit() {
    function applyTheater(flag) {
      root.classList.toggle('yrp-theater', flag);
      try {
        if (typeof window.setTheater === 'function') {
          window.setTheater(flag);
        } else {
          const layout = root.closest('.watch-layout') || document.querySelector('.watch-layout');
          if (layout) {
            layout.classList.toggle('theater-mode', flag);
            if (typeof window.relocateUpNext === 'function') window.relocateUpNext();
          }
        }
      } catch {}
      if (flag) {
        root.style.maxWidth = '';
        root.style.minWidth = '';
        root.style.width = '';
      } else {
        adjustWidthByAspect();
      }
    }
    const thSaved = !!load('theater', false);
    if (thSaved) applyTheater(true);
    if (btnTheater) {
      btnTheater.addEventListener('click', function () {
        const next = !root.classList.contains('yrp-theater');
        applyTheater(next);
        save('theater', next);
        showControls();
      });
    }
  })();

  video.addEventListener('loadedmetadata', function () {
    if (startAt > 0) {
      try { video.currentTime = Math.min(startAt, Math.floor(video.duration || startAt)); } catch {}
    }
    setTimeout(adjustWidthByAspect, 0);
    updateTimes();
    updateProgress();
    refreshVolIcon();
    refreshAutoplayBtn();
    refreshPlayBtn();
    refreshSubtitlesBtn(btnSubtitles, video, overlayActive);

    if (prefLang) {
      const idxPref = findTrackIndexByLang(video, prefLang);
      if (idxPref >= 0) activeTrackIndex = idxPref;
    }
    if (isFinite(prefSpeed) && prefSpeed > 0) {
      applySpeed(prefSpeed);
    }

    chooseActiveTrack(video, activeTrackIndex);
    applyPageModes(video, activeTrackIndex, overlayActive);
    refreshSubtitlesBtn(btnSubtitles, video, overlayActive);
    scheduleAutoHide(1200);

    loadSpritesVTT();
    updateOverlayText(hooks, video, activeTrackIndex, overlayActive);

    const r = root.querySelector('.yrp-video-wrap').getBoundingClientRect();
    const centerX = r.width / 2, tb = root.querySelector('.yrp-captions-text');
    if (tb) {
      const avail = Math.min(centerX, r.width - centerX) * 2;
      const pad = 12, minW = 220;
      tb.style.maxWidth = Math.max(minW, Math.floor(avail - pad)) + 'px';
    }
    logTracks(video, d, 'after loadedmetadata');

    if (menu && !menu.hidden) {
      const currentView = menuManager.getView();
      if (currentView === 'main') openMainMenuView();
      else if (currentView === 'langs') wrappedBuildLangsMenuView();
      else if (currentView === 'speed') wrappedBuildSpeedMenuView();
      else if (currentView === 'subs') wrappedBuildSubtitlesMenuView();
    }
  });

  function wrappedLogTracks(prefix) {
    logTracks(video, d, prefix);
  }

  function adjustWidthByAspect() {
    if (root.classList.contains('yrp-theater')) return;
    const cs = getComputedStyle(video);
    const maxH = cssPxToNum(cs.getPropertyValue('max-height')) || video.clientHeight || 0;
    const vw0 = video.videoWidth || 16, vh0 = video.videoHeight || 9;
    const aspect = vh0 > 0 ? vw0 / vh0 : 16 / 9;
    const targetH = Math.min(maxH || video.clientHeight || 0, window.innerHeight * 0.9);
    if (!targetH || !isFinite(targetH)) return;
    const targetW = Math.floor(targetH * aspect);
    const maxPage = Math.floor(window.innerWidth * 0.95);
    const controlsMin = measureControlsMinWidth();
    const finalW = Math.max(controlsMin, Math.min(targetW, maxPage));
    root.style.maxWidth = finalW + 'px';
    root.style.minWidth = controlsMin + 'px';
    root.style.width = '100%';
  }
  function measureControlsMinWidth() {
    const lw = leftGrp ? leftGrp.getBoundingClientRect().width : 0;
    const rw = rightGrp ? rightGrp.getBoundingClientRect().width : 0;
    const pad = 24;
    const mw = Math.ceil(lw + rw + pad);
    return (!isFinite(mw) || mw <= 0) ? 480 : mw;
  }

  (function autoplayInit() {
    const host = root.closest('.player-host') || root;
    const opt = parseJSONAttr(host, 'data-options', null);
    function want() { if (opt && opt.autoplay === true) return true; return !!load('autoplay', false); }
    if (!want()) { setTimeout(function () { scheduleAutoHide(1000); }, 0); return; }

    function sequence() {
      let p = null;
      try { p = video.play(); } catch { p = null; }
      if (p && typeof p.then === 'function') {
        p.then(function () {}).catch(function () {
          if (!video.muted) {
            autoMuteApplied = true;
            video.muted = true;
            video.setAttribute('muted', '');
            try { video.play().catch(function () {}); } catch {}
          }
        });
      } else {
        setTimeout(function () {
          if (video.paused) {
            autoMuteApplied = true;
            video.muted = true;
            video.setAttribute('muted', '');
            try { video.play().catch(function () {}); } catch {}
          }
        }, 0);
      }
    }

    let fired = false;
    function fireOnce() { if (fired) return; fired = true; sequence(); }
    if (video.readyState >= 1) fireOnce();
    ['loadedmetadata', 'loadeddata', 'canplay', 'canplaythrough'].forEach(function (ev) {
      const once = function () { video.removeEventListener(ev, once); fireOnce(); };
      video.addEventListener(ev, once);
    });
    setTimeout(function () {
      if (video.paused) {
        autoMuteApplied = true;
        video.muted = true;
        video.setAttribute('muted', '');
        try { video.play().catch(function () {}); } catch {}
      }
    }, 1200);
  })();

  window.addEventListener('resize', adjustWidthByAspect);
  video.addEventListener('timeupdate', function () { updateTimes(); updateProgress(); updateOverlayText(hooks, video, activeTrackIndex, overlayActive); });
  video.addEventListener('progress', updateProgress);
  video.addEventListener('play', function () { root.classList.add('playing'); refreshPlayBtn(); showControls(); });
  video.addEventListener('pause', function () { root.classList.remove('playing'); refreshPlayBtn(); showControls(); });

  function toggleMini() {
    if (!document.pictureInPictureEnabled || !video.requestPictureInPicture || video.disablePictureInPicture) return;
    if (document.pictureInPictureElement === video) document.exitPictureInPicture().catch(function () {});
    else video.requestPictureInPicture().catch(function () {});
  }

  video.addEventListener('click', playToggle);
  centerPlay && centerPlay.addEventListener('click', playToggle);
  btnPlay && btnPlay.addEventListener('click', playToggle);
  btnPrev && btnPrev.addEventListener('click', function () { root.dispatchEvent(new CustomEvent('yrp-prev', { bubbles: true })); });
  btnNext && btnNext.addEventListener('click', function () { root.dispatchEvent(new CustomEvent('yrp-next', { bubbles: true })); });

  (function playlistSupport(){
    var url = new URL(window.location.href);
    var playlistId = url.searchParams.get("p");
    var currentVid = url.searchParams.get("v") || (root.getAttribute("data-video-id") || "");

    if (!playlistId) {
      if (btnPrev) btnPrev.style.display = "none";
      if (btnNext) btnNext.style.display = "none";
      var oldSh = root.querySelector(".yrp-shuffle");
      var oldCy = root.querySelector(".yrp-cycle");
      if (oldSh) oldSh.style.display = "none";
      if (oldCy) oldCy.style.display = "none";
      return;
    } else {
      if (btnPrev) btnPrev.style.display = "";
      if (btnNext) btnNext.style.display = "";
    }

    function collectOrder(){
      var items = [];
      var right = document.querySelector("#upnext-block .rb-list");
      var under = document.querySelector("#panel-upnext .upnext-list");
      var anchors = [];
      if (right) anchors = right.querySelectorAll("a.rb-item[href*='/watch']");
      else if (under) anchors = under.querySelectorAll("a.rb-item[href*='/watch']");
      anchors.forEach(function(a){
        var href = a.getAttribute("href") || "";
        var m = href.match(/[?&]v=([^&]+)/);
        if (m && m[1]) items.push(decodeURIComponent(m[1]));
      });
      return items;
    }

    var order = collectOrder();
    if (!order || order.length === 0) return;
    var curIndex = order.indexOf(currentVid);
    if (curIndex < 0) curIndex = 0;

    function plKey(s){ return "pl:" + playlistId + ":" + s; }
    var orderMode = (function(){ var v = load(plKey("order"), "direct"); return v === "shuffle" ? "shuffle" : "direct"; })();
    var cycleOn  = (function(){ var v = load(plKey("cycle"), "0"); return v === true || v === "1"; })();

    function saveOrderMode(mode){
      orderMode = (mode === "shuffle") ? "shuffle" : "direct";
      save(plKey("order"), orderMode);
      refreshShuffleBtn();
    }
    function saveCycle(flag){
      cycleOn = !!flag;
      save(plKey("cycle"), cycleOn ? "1" : "0");
      refreshCycleBtn();
    }

    function pickRandomIndex(excludeIdx){
      if (order.length <= 1) return excludeIdx;
      var tries = 0, rnd = excludeIdx;
      while (tries < 6 && rnd === excludeIdx) { rnd = Math.floor(Math.random() * order.length); tries++; }
      if (rnd === excludeIdx) rnd = (excludeIdx + 1) % order.length;
      return rnd;
    }
    function nextIndex(){
      if (orderMode === "shuffle") return pickRandomIndex(curIndex);
      var ni = curIndex + 1;
      if (ni >= order.length) return cycleOn ? 0 : -1;
      return ni;
    }
    function prevIndex(){
      if (orderMode === "shuffle") return pickRandomIndex(curIndex);
      var pi = curIndex - 1;
      if (pi < 0) return cycleOn ? (order.length - 1) : -1;
      return pi;
    }
    function gotoIndex(idx){
      idx = Math.max(0, Math.min(order.length - 1, idx));
      var vidTarget = order[idx];
      if (!vidTarget) return;

      try {
        var m = load("resume", {});
        if (m && m[vidTarget]) { delete m[vidTarget]; save("resume", m); }
      } catch(_){}

      var nu = new URL(window.location.href);
      nu.searchParams.set("v", vidTarget);
      nu.searchParams.set("p", playlistId);
      window.location.href = nu.toString();
    }

    root.addEventListener("yrp-prev", function(){ var i = prevIndex(); if (i >= 0) gotoIndex(i); });
    root.addEventListener("yrp-next", function(){ var i = nextIndex(); if (i >= 0) gotoIndex(i); });

    var btnShuffle = root.querySelector(".yrp-shuffle");
    var btnCycle   = root.querySelector(".yrp-cycle");

    if (!btnShuffle) {
      btnShuffle = document.createElement("button");
      btnShuffle.type = "button";
      btnShuffle.className = "yrp-btn yrp-shuffle";
      btnShuffle.title = "Shuffle playlist";
      btnShuffle.setAttribute("aria-label", "Shuffle playlist");
      Object.assign(btnShuffle.style, {
        border: "none",
        width: "var(--yrp-icon-button-width)",
        height: "28px",
        cursor: "pointer",
        padding: "0",
        marginLeft: "6px",
        marginRight: "2px"
      });
    }
    if (!btnCycle) {
      btnCycle = document.createElement("button");
      btnCycle.type = "button";
      btnCycle.className = "yrp-btn yrp-cycle";
      btnCycle.title = "Cycle playlist";
      btnCycle.setAttribute("aria-label", "Cycle playlist");
      Object.assign(btnCycle.style, {
        border: "none",
        width: "var(--yrp-icon-button-width)",
        height: "28px",
        cursor: "pointer",
        padding: "0",
        marginRight: "8px"
      });
    }

    btnShuffle.dataset.forceEmoji = "0";
    btnCycle.dataset.forceEmoji = "0";

    function refreshShuffleBtn(){
      btnShuffle.setAttribute("aria-pressed", orderMode === "shuffle" ? "true" : "false");
      applyIcon(btnShuffle, "--icon-shuffle-on", "--icon-shuffle-off", orderMode === "shuffle", "🔀");
      btnShuffle.style.opacity = (orderMode === "shuffle") ? "1" : "0.55";
      btnShuffle.style.display = "";
    }
    function refreshCycleBtn(){
      btnCycle.setAttribute("aria-pressed", cycleOn ? "true" : "false");
      applyIcon(btnCycle, "--icon-cycle-on", "--icon-cycle-off", !!cycleOn, "🔁");
      btnCycle.style.opacity = "1";
      btnCycle.style.display = "";
    }

    refreshShuffleBtn();
    refreshCycleBtn();

    btnShuffle.addEventListener("click", function(){
      saveOrderMode(orderMode === "shuffle" ? "direct" : "shuffle");
    });
    btnCycle.addEventListener("click", function(){
      saveCycle(!cycleOn);
    });

    try {
      var container = leftGrp || (btnNext && btnNext.parentNode) || root;
      if (vol && container) {
        container.insertBefore(btnShuffle, vol);
        container.insertBefore(btnCycle, vol);
      } else if (btnNext && container) {
        container.insertBefore(btnShuffle, btnNext.nextSibling);
        container.insertBefore(btnCycle, btnShuffle.nextSibling);
      } else {
        container.appendChild(btnShuffle);
        container.appendChild(btnCycle);
      }
    } catch(_){}

    video.addEventListener("ended", function(){
      var i = nextIndex();
      if (i >= 0) gotoIndex(i);
    });

    document.addEventListener("keydown", function(e){
      var t = e.target, tag = t && t.tagName ? t.tagName.toUpperCase() : "";
      if (t && (t.isContentEditable || tag === "INPUT" || tag === "TEXTAREA")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var code = e.code || "";
      if (code === "PageUp")   { e.preventDefault(); var i = prevIndex(); if (i >= 0) gotoIndex(i); }
      else if (code === "PageDown") { e.preventDefault(); var j = nextIndex(); if (j >= 0) gotoIndex(j); }
    });
  })();

  if (btnVol) {
    btnVol.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      userTouchedVolume = true;
      autoMuteApplied = false;
      setMutedToggle();
      showControls();
      root.classList.add('vol-open');
      setTimeout(function () { root.classList.remove('vol-open'); }, 1200);
    });
  }

  if (vol) {
    vol.addEventListener('wheel', function (e) {
      e.preventDefault();
      userTouchedVolume = true;
      autoMuteApplied = false;
      const step = 0.05, v = video.muted ? 0 : video.volume;
      const nv = clamp(v + (e.deltaY < 0 ? step : -step), 0, 1);
      video.volume = nv;
      if (nv > 0) video.muted = false;
      volSlider && (volSlider.value = String(nv));
      refreshVolIcon();
      showControls();
    }, { passive: false });
  }

  if (volSlider) {
    volSlider.addEventListener('input', function () {
      userTouchedVolume = true;
      autoMuteApplied = false;
      let v = parseFloat(volSlider.value || '1');
      if (!isFinite(v)) v = 1;
      v = clamp(v, 0, 1);
      video.volume = v;
      if (v > 0) video.muted = false;
      refreshVolIcon();
    });

    volSlider.addEventListener('wheel', function (e) {
      e.preventDefault();
      userTouchedVolume = true;
      autoMuteApplied = false;
      const step = 0.05, v = video.muted ? 0 : video.volume;
      const nv = clamp(v + (e.deltaY < 0 ? step : -step), 0, 1);
      video.volume = nv;
      if (nv > 0) video.muted = false;
      volSlider.value = String(nv);
      refreshVolIcon();
      showControls();
    }, { passive: false });
  }

  if (progress) {
    progress.addEventListener('mousedown', function (e) { seeking = true; hideMenus(); seekByClientX(e.clientX); });
    window.addEventListener('mousemove', function (e) { if (seeking) seekByClientX(e.clientX); });
    window.addEventListener('mouseup', function () { seeking = false; });
    progress.addEventListener('mousemove', function (e) {
      updateTooltip(e.clientX);
      if (spritesVttUrl && spritesLoaded && !spritesLoadError) showSpritePreviewAtClientX(e.clientX);
      else if (spritesVttUrl && !spritesLoaded && !spritesLoadError) loadSpritesVTT();
    });
    progress.addEventListener('mouseleave', function () { tooltip && (tooltip.hidden = true); spritePop && (spritePop.style.display = 'none'); });
  }

  function hideMenus() {
    if (menu) {
      menu.hidden = true;
      btnSettings && btnSettings.setAttribute('aria-expanded', 'false');
    }
    const ctx = root.querySelector('.yrp-context');
    if (ctx) ctx.hidden = true;
    root.classList.remove('vol-open');

    menuManager.setView('main');
    menuManager.resetHeightLock();
  }

  if (btnSettings && menu) {
    menuManager.ensureMainSnapshot();

    if (!menuBound) {
      menuBound = true;

      btnSettings.addEventListener('click', function (e) {
        const open = menu.hidden ? false : true;
        if (open) {
          menu.hidden = true;
          btnSettings.setAttribute('aria-expanded', 'false');
          menuManager.setView('main');
          menuManager.resetHeightLock();
        } else {
          hideMenus();
          openMainMenuView();
          menu.hidden = false;
          btnSettings.setAttribute('aria-expanded', 'true');
          menuManager.lockHeightFromCurrent();
        }
        e.stopPropagation();
        root.classList.add('vol-open');
        showControls();
      });

      menu.addEventListener('click', function (e) {
        const item = e.target && e.target.closest ? e.target.closest('.yrp-menu-item') : null;
        if (!item || !menu.contains(item)) return;

        const act = item.getAttribute('data-action') || '';
        const lang = item.getAttribute('data-lang') || '';
        const currentView = menuManager.getView();

        if (currentView === 'main') {
          if (act === 'open-langs') {
            e.preventDefault(); e.stopPropagation();
            wrappedBuildLangsMenuView();
            menuManager.lockHeightFromCurrent();
            root.classList.add('vol-open'); showControls();
            return;
          }
          if (act === 'open-speed') {
            e.preventDefault(); e.stopPropagation();
            wrappedBuildSpeedMenuView();
            menuManager.lockHeightFromCurrent();
            root.classList.add('vol-open'); showControls();
            return;
          }
          if (act === 'open-subs') {
            e.preventDefault(); e.stopPropagation();
            if (!anySubtitleTracks(video)) return;
            wrappedBuildSubtitlesMenuView();
            menuManager.lockHeightFromCurrent();
            root.classList.add('vol-open'); showControls();
            return;
          }
          return;
        }

        if (act === 'back') {
          e.preventDefault(); e.stopPropagation();
          openMainMenuView();
          menuManager.lockHeightFromCurrent();
          root.classList.add('vol-open'); showControls();
          return;
        }

        if (currentView === 'langs') {
          if (act === 'select-lang' && lang) {
            e.preventDefault(); e.stopPropagation();
            selectSubtitleLang(lang);
            menu.hidden = true;
            btnSettings.setAttribute('aria-expanded', 'false');
            menuManager.setView('main');
            menuManager.resetHeightLock();
            return;
          }
        }

        if (currentView === 'speed') {
          if (act === 'set-speed') {
            const sp2 = parseFloat(item.getAttribute('data-speed') || 'NaN');
            if (!isNaN(sp2)) {
              e.preventDefault(); e.stopPropagation();
              applySpeed(video, sp2);
              menu.hidden = true;
              btnSettings.setAttribute('aria-expanded', 'false');
              menuManager.setView('main');
              menuManager.resetHeightLock();
              return;
            }
          }
        }

        if (currentView === 'subs') {
          if (act === 'subs-on') {
            e.preventDefault(); e.stopPropagation();
            setSubtitlesEnabled(true);
            menu.hidden = true;
            btnSettings.setAttribute('aria-expanded', 'false');
            menuManager.setView('main');
            menuManager.resetHeightLock();
            return;
          }
          if (act === 'subs-off') {
            e.preventDefault(); e.stopPropagation();
            setSubtitlesEnabled(false);
            menu.hidden = true;
            btnSettings.setAttribute('aria-expanded', 'false');
            menuManager.setView('main');
            menuManager.resetHeightLock();
            return;
          }
        }
      });

      document.addEventListener('click', function (e) {
        if (!menu.hidden && !menu.contains(e.target) && e.target !== btnSettings) {
          menu.hidden = true;
          btnSettings.setAttribute('aria-expanded', 'false');
          menuManager.setView('main');
          menuManager.resetHeightLock();
        }
      });
    }
  }

  btnFull && btnFull.addEventListener('click', function () {
    if (document.fullscreenElement) document.exitFullscreen().catch(function () {});
    else root.requestFullscreen && root.requestFullscreen().catch(function () {});
  });

  btnPip && btnPip.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); toggleMini(); });

  btnAutoplay && btnAutoplay.addEventListener('click', function (e) {
    e.preventDefault();
    e.stopPropagation();
    const next = !load('autoplay', false);
    save('autoplay', next);
    autoplayOn = next;
    refreshAutoplayBtn();
  });

  btnSubtitles && btnSubtitles.addEventListener('click', function (e) {
    e.preventDefault();
    e.stopPropagation();
    if (!anySubtitleTracks(video)) return;
    overlayActive = !overlayActive;
    applyPageModes(video, activeTrackIndex, overlayActive);
    updateOverlayText(hooks, video, activeTrackIndex, overlayActive);
    refreshSubtitlesBtn(btnSubtitles, video, overlayActive);
  });

  root.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    hideMenus();
    const ctx = root.querySelector('.yrp-context');
    if (!ctx) return;
    const rw = root.getBoundingClientRect();
    ctx.style.left = (e.clientX - rw.left) + 'px';
    ctx.style.top = (e.clientY - rw.top) + 'px';
    ctx.hidden = false;
    ctx.onclick = function (ev) {
      const act = ev.target && ev.target.getAttribute('data-action');
      const at = Math.floor(video.currentTime || 0);
      const vid = root.getAttribute('data-video-id') || '';
      if (act === 'pip') toggleMini();
      else if (act === 'copy-url') {
        const u = new URL(window.location.href);
        u.searchParams.delete('t');
        copyText(u.toString());
      } else if (act === 'copy-url-time') {
        const u2 = new URL(window.location.href);
        u2.searchParams.set('t', String(at));
        copyText(u2.toString());
      } else if (act === 'copy-embed') {
        const src = (window.location.origin || '') + '/embed?v=' + encodeURIComponent(vid || '');
        const iframe = `<iframe width="560" height="315" src="${src}" frameborder="0" allow="autoplay; encrypted-media; clipboard-write" allowfullscreen></iframe>`;
        copyText(iframe);
      }
      ctx.hidden = true;
    };
    document.addEventListener('click', function (e2) {
      const ctx2 = root.querySelector('.yrp-context');
      if (ctx2 && !ctx2.hidden && !ctx2.contains(e2.target)) ctx2.hidden = true;
    }, { once: true });
    document.addEventListener('keydown', function esc(ev) {
      if ((ev.code === 'Escape') || ((ev.key || '').toLowerCase() === 'escape')) {
        const c = root.querySelector('.yrp-context');
        if (c && !c.hidden) c.hidden = true;
        document.removeEventListener('keydown', esc);
      }
    });
  });

  function onDocMove(e) {
    const r = root.getBoundingClientRect();
    if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) showControls();
  }
  document.addEventListener('mousemove', onDocMove, { passive: true });
  document.addEventListener('pointermove', onDocMove, { passive: true });

  ['mousemove', 'pointermove', 'mouseenter', 'mouseover', 'touchstart'].forEach(function (evName) {
    root.addEventListener(evName, function () { try { root.focus(); } catch {} showControls(); }, { passive: true });
    video && video.addEventListener(evName, showControls, { passive: true });
    centerPlay && centerPlay.addEventListener(evName, showControls, { passive: true });
  });

  function updateFsHoverBinding() {
    try {
      if (document.fullscreenElement === root) {
        document.addEventListener('mousemove', onDocMove, { passive: true });
        document.addEventListener('pointermove', onDocMove, { passive: true });
      } else {
      }
    } catch {}
  }

  document.addEventListener('fullscreenchange', updateFsHoverBinding);
  updateFsHoverBinding();

  function handleHotkey(e) {
    const t = e.target, tag = t && t.tagName ? t.tagName.toUpperCase() : '';
    if (t && (t.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA')) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const code = e.code, key = (e.key || '').toLowerCase();

    if (code === 'Space' || code === 'Enter' || code === 'NumpadEnter' || code === 'MediaPlayPause' || code === 'KeyK' || key === 'k') { playToggle(); e.preventDefault(); return; }
    if (code === 'ArrowLeft' || key === 'arrowleft' || code === 'KeyJ' || key === 'j') { video.currentTime = clamp((video.currentTime || 0) - 5, 0, duration || 0); e.preventDefault(); return; }
    if (code === 'ArrowRight' || key === 'arrowright' || code === 'KeyL' || key === 'l') { video.currentTime = clamp((video.currentTime || 0) + 5, 0, duration || 0); e.preventDefault(); return; }
    if (code === 'KeyM' || key === 'm') { setMutedToggle(); e.preventDefault(); return; }
    if (code === 'KeyF' || key === 'f') {
      if (document.fullscreenElement) document.exitFullscreen().catch(function () {});
      else root.requestFullscreen && root.requestFullscreen().catch(function () {});
      e.preventDefault(); return;
    }
    if (code === 'KeyT' || key === 't') { btnTheater && btnTheater.click(); e.preventDefault(); return; }
    if (code === 'KeyI' || key === 'i') { toggleMini(); e.preventDefault(); return; }
    if (code === 'KeyA' || key === 'a') { btnAutoplay && btnAutoplay.click(); e.preventDefault(); return; }
    if (code === 'KeyC' || key === 'c') { btnSubtitles && !btnSubtitles.disabled && btnSubtitles.click(); e.preventDefault(); return; }
    if (code === 'Escape' || key === 'escape') { hideMenus(); return; }
  }

  document.addEventListener('keydown', handleHotkey);
  setTimeout(adjustWidthByAspect, 200);
}