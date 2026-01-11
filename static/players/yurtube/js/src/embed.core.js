import { fmtTime, parseJSONAttr, throttle, copyText } from './util.js';
import { installFallbackGuards } from './fallback.js';

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

export function initEmbed() {
  const PLAYER_NAME = detectPlayerName();
  const PLAYER_BASE = '/static/players/' + PLAYER_NAME;
  const hosts = document.querySelectorAll('.player-host[data-player="' + PLAYER_NAME + '"]');
  if (hosts.length === 0) return;

  fetch(PLAYER_BASE + '/templates/player.html', { credentials: 'same-origin' })
    .then(r => r.text())
    .then(function (html) { for (let i = 0; i < hosts.length; i++) mountOne(hosts[i], html, PLAYER_BASE); })
    .catch(function () {});
}

function mountOne(host, tpl, PLAYER_BASE) {
  host.innerHTML = tpl;

  const root = host.querySelector('.yrp-container');
  const wrap = root.querySelector('.yrp-video-wrap');
  const video = root.querySelector('.yrp-video');
  const controls = root.querySelector('.yrp-controls');
  const source = video.querySelector('source');
  const ap = root.querySelector('.yrp-autoplay');
  if (ap) ap.style.display = 'none';

  const opts = parseJSONAttr(host, 'data-options', {});
  const DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);
  function d() { if (!DEBUG) return; try { console.debug.apply(console, ['[YRP-EMBED]'].concat([].slice.call(arguments))); } catch (_) {} }

  root.classList.add('yrp-embed');
  root.setAttribute('tabindex', '0');

  const videoSrc = host.getAttribute('data-video-src') || '';
  const poster = host.getAttribute('data-poster-url') || '';
  const vid = host.getAttribute('data-video-id') || '';
  const subs = parseJSONAttr(host, 'data-subtitles', []);
  const spritesVtt = host.getAttribute('data-sprites-vtt') || '';
  const captionVtt = host.getAttribute('data-caption-vtt') || '';
  const captionLang = host.getAttribute('data-caption-lang') || '';

  if (source) source.setAttribute('src', videoSrc);
  if (poster) video.setAttribute('poster', poster);
  if (opts && opts.autoplay) video.setAttribute('autoplay', '');
  if (opts && opts.muted) video.setAttribute('muted', '');
  if (opts && opts.loop) video.setAttribute('loop', '');
  if (vid) root.setAttribute('data-video-id', vid);
  if (spritesVtt) root.setAttribute('data-sprites-vtt', spritesVtt);
  video.setAttribute('playsinline', '');

  if (Array.isArray(subs)) {
    subs.forEach(function (t) {
      if (!t || !t.src) return;
      const tr = document.createElement('track');
      // embed uses subtitles kind (ok)
      tr.setAttribute('kind', 'subtitles');
      if (t.srclang) tr.setAttribute('srclang', String(t.srclang));
      if (t.label) tr.setAttribute('label', String(t.label));
      tr.setAttribute('src', String(t.src));
      if (t.default) tr.setAttribute('default', '');
      video.appendChild(tr);
    });
  }

  const ccBtn = root.querySelector('.yrp-subtitles');
  if (captionVtt) {
    try {
      const ctr = document.createElement('track');
      ctr.setAttribute('kind', 'subtitles');
      ctr.setAttribute('src', captionVtt);
      ctr.setAttribute('srclang', captionLang || 'auto');
      ctr.setAttribute('label', captionLang || 'Original');
      ctr.setAttribute('default', '');
      video.appendChild(ctr);
    } catch (e) {
      d('caption track append failed', e);
    }
  }

  try { video.load(); d('video.load() called', { src: videoSrc }); } catch (e) { d('video.load() error', e); }
  installFallbackGuards(video, source, d);

  const iconBase = PLAYER_BASE + '/img/buttons';
  root.style.setProperty('--icon-play',    'url("' + iconBase + '/play.svg")');
  root.style.setProperty('--icon-pause',   'url("' + iconBase + '/pause.svg")');
  root.style.setProperty('--icon-prev',    'url("' + iconBase + '/prev.svg")');
  root.style.setProperty('--icon-next',    'url("' + iconBase + '/next.svg")');
  root.style.setProperty('--icon-vol',     'url("' + iconBase + '/volume.svg")');
  root.style.setProperty('--icon-mute',    'url("' + iconBase + '/mute.svg")');
  root.style.setProperty('--icon-cc',      'url("' + iconBase + '/cc.svg")');
  root.style.setProperty('--icon-mini',    'url("' + iconBase + '/mini.svg")');
  root.style.setProperty('--icon-settings','url("' + iconBase + '/settings.svg")');
  root.style.setProperty('--icon-theater', 'url("' + iconBase + '/theater.svg")');
  root.style.setProperty('--icon-full',    'url("' + iconBase + '/full.svg")');
  root.classList.add('yrp-icons-ready');

  const centerLogo = root.querySelector('.yrp-center-logo');
  if (centerLogo) centerLogo.setAttribute('src', PLAYER_BASE + '/img/logo.png');

  wireEmbed(root, wrap, video, controls, spritesVtt, DEBUG, ccBtn);
}

function wireEmbed(root, wrap, video, controls, spritesVttUrl, DEBUG, ccBtn) {
  function d() { if (!DEBUG) return; try { console.debug.apply(console, ['[YRP-EMBED]'].concat([].slice.call(arguments))); } catch (_) {} }

  const centerPlay = root.querySelector('.yrp-center-play');
  const btnPlay = root.querySelector('.yrp-play');
  const btnVol = root.querySelector('.yrp-vol-btn');
  const volWrap = root.querySelector('.yrp-volume');
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
  const btnFull = root.querySelector('.yrp-fullscreen');
  const btnPip = root.querySelector('.yrp-pip');
  const ctx = root.querySelector('.yrp-context');

  let seeking = false, duration = 0;
  let hideTimer = null;
  let userTouchedVolume = false;
  let autoMuteApplied = false;

  // ---- submenu/menu state (Variant A like main player) ----
  let menuView = 'main'; // main | speed | langs | subs
  let menuMainHTML = '';
  let menuFixedMinHeight = 0;

  // ---- subtitles selection state ----
  let overlayActive = true;
  let activeTrackIndex = 0;

  const prefLang = (function(){ try { return String(localStorage.getItem('subtitle_lang') || ''); } catch (_) { return ''; } })();
  const prefSpeed = (function(){ try { return parseFloat(localStorage.getItem('playback_speed') || ''); } catch (_) { return NaN; } })();

  // --- English language display helpers ---
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
  function langDisplayNameEn(code, fallbackLabel) {
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

  // Captions overlay (draggable, pointer events)
  function createCaptionsOverlay(container) {
    const layer = document.createElement('div');
    layer.className = 'yrp-embed-captions-layer';
    Object.assign(layer.style, {
      position: 'absolute',
      left: '50%',
      top: '80%',
      transform: 'translate(-50%,-50%)',
      zIndex: '21',
      pointerEvents: 'auto',
      userSelect: 'none',
      touchAction: 'none'
    });
    const box = document.createElement('div');
    box.className = 'yrp-embed-captions-text';
    layer.appendChild(box);

    const cs = getComputedStyle(container);
    if (cs.position === 'static') container.style.position = 'relative';
    container.appendChild(layer);

    const drag = { active: false, sx: 0, sy: 0 };
    let leaveGuardTimer = null;

    function wrapRect() { return container.getBoundingClientRect(); }
    function endDrag(e) {
      if (!drag.active) return;
      drag.active = false;
      if (leaveGuardTimer) { clearTimeout(leaveGuardTimer); leaveGuardTimer = null; }
      if (e && e.preventDefault) try { e.preventDefault(); } catch {}
      if (e && e.stopPropagation) try { e.stopPropagation(); } catch {}
    }
    function onStart(e) {
      drag.active = true;
      drag.sx = e.clientX;
      drag.sy = e.clientY;
      try { layer.setPointerCapture && layer.setPointerCapture(e.pointerId); } catch {}
      if (leaveGuardTimer) { clearTimeout(leaveGuardTimer); leaveGuardTimer = null; }
      e.preventDefault(); e.stopPropagation();
    }
    function onMove(e) {
      if (!drag.active) return;
      const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
      const r = wrapRect(), ov = layer.getBoundingClientRect();
      let cx = (ov.left + ov.width / 2) + dx, cy = (ov.top + ov.height / 2) + dy;
      const halfW = ov.width / 2, halfH = ov.height / 2;
      cx = Math.min(Math.max(cx, r.left + halfW), r.right - halfW);
      cy = Math.min(Math.max(cy, r.top + halfH), r.bottom - halfH);
      const relX = (cx - r.left) / r.width * 100;
      const relY = (cy - r.top) / r.height * 100;
      layer.style.left = relX + '%';
      layer.style.top = relY + '%';
      layer.style.transform = 'translate(-50%,-50%)';
      drag.sx = e.clientX; drag.sy = e.clientY;
      e.preventDefault(); e.stopPropagation();
    }
    function onLeaveRegion() {
      if (leaveGuardTimer) { clearTimeout(leaveGuardTimer); }
      leaveGuardTimer = setTimeout(function () { endDrag(new Event('leaveguard')); }, 200);
    }

    layer.addEventListener('pointerdown', onStart);
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', endDrag);
    document.addEventListener('pointercancel', endDrag);
    document.addEventListener('mouseup', endDrag);
    document.addEventListener('touchend', endDrag);
    container.addEventListener('pointerleave', onLeaveRegion);
    layer.addEventListener('click', function (e) { e.stopPropagation(); });

    return { layer, box };
  }

  const overlay = createCaptionsOverlay(wrap);

  function subtitleTracks() {
    try {
      return video.textTracks ? Array.prototype.filter.call(video.textTracks, function (tr) {
        return tr.kind === 'subtitles' || tr.kind === 'captions';
      }) : [];
    } catch { return []; }
  }
  function anySubtitleTracks() { return subtitleTracks().length > 0; }
  function chooseActiveTrack() {
    const subs = subtitleTracks();
    if (subs.length === 0) return null;
    if (activeTrackIndex < 0 || activeTrackIndex >= subs.length) activeTrackIndex = 0;
    return subs[activeTrackIndex];
  }
  function applyTrackModes() {
    const subs = subtitleTracks();
    subs.forEach(function (tr, i) {
      tr.mode = (i === activeTrackIndex && overlayActive) ? 'hidden' : 'disabled';
    });
  }
  function currentCueText(track) {
    if (!track || !track.cues || track.cues.length === 0) return '';
    const t = video.currentTime || 0;
    for (let i = 0; i < track.cues.length; i++) {
      const c = track.cues[i];
      if (t >= c.startTime && t <= c.endTime) return (c.text || '').replace(/\r/g, '');
    }
    return '';
  }
  function updateOverlayText() {
    const tr = chooseActiveTrack();
    applyTrackModes();
    overlay.box.textContent = overlayActive ? currentCueText(tr) : '';
    overlay.layer.style.display = overlayActive ? '' : 'none';
  }

  function refreshSubtitlesBtnUI() {
    if (!ccBtn) return;
    const has = anySubtitleTracks();
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

  function trackInfoList() {
    const subs = subtitleTracks();
    return subs.map(function (tr, i) {
      // IMPORTANT: TextTrack.language is unreliable, prefer srclang fallback
      const code = String(tr.language || tr.srclang || '').toLowerCase();
      const rawLabel = String(tr.label || code || ('Lang ' + (i + 1)));
      const label = langDisplayNameEn(code, rawLabel);
      return { index: i, lang: code, label: label };
    });
  }
  function findTrackIndexByLang(code) {
    const c = String(code || '').toLowerCase();
    const list = trackInfoList();
    for (let i = 0; i < list.length; i++) {
      if (list[i].lang === c) return list[i].index;
      if (list[i].label.toLowerCase() === c) return list[i].index;
    }
    return -1;
  }
  function selectSubtitleLang(code) {
    const idx = findTrackIndexByLang(code);
    if (idx >= 0) {
      activeTrackIndex = idx;
      overlayActive = true;
      try { localStorage.setItem('subtitle_lang', String(code || '')); } catch (_){}
      applyTrackModes();
      updateOverlayText();
      refreshSubtitlesBtnUI();
    }
  }
  function setSubtitlesEnabled(flag) {
    overlayActive = !!flag;
    applyTrackModes();
    updateOverlayText();
    refreshSubtitlesBtnUI();
  }

  // Sprites preview
  const spriteCues = [];
  let spritesLoaded = false;
  let spritesLoadError = false;
  let spritePop = null;
  let spriteDurationApprox = 0;

  function parseTimestamp(ts) {
    const m = String(ts || '').match(/^(\d{2}):(\d{2}):(\d{2}\.\d{3})$/);
    if (!m) return 0;
    const h = parseInt(m[1], 10), mm = parseInt(m[2], 10), ss = parseFloat(m[3]);
    return h * 3600 + mm * 60 + ss;
  }
  function buildAbsoluteSpriteUrl(rel) {
    if (!rel) return '';
    if (/^https?:\/\//i.test(rel) || rel.startsWith('/')) return rel;
    try {
      const u = new URL(spritesVttUrl, window.location.origin);
      const baseDir = u.pathname.replace(/\/sprites\.vtt$/, '');
      return baseDir + '/' + rel.replace(/^\/+/, '');
    } catch { return rel; }
  }
  function ensureSpritePop() {
    if (spritePop) return spritePop;
    if (!progress) return null;
    spritePop = document.createElement('div');
    spritePop.className = 'yrp-sprite-pop';
    Object.assign(spritePop.style, {
      position: 'absolute',
      bottom: 'calc(100% + 30px)',
      left: '0',
      display: 'none',
      width: '160px',
      height: '90px',
      border: '1px solid #333',
      background: '#000',
      overflow: 'hidden',
      zIndex: '5'
    });
    if (getComputedStyle(progress).position === 'static') progress.style.position = 'relative';
    progress.appendChild(spritePop);
    return spritePop;
  }
  function loadSpritesVTT() {
    if (!spritesVttUrl || spritesLoaded || spritesLoadError) return;
    fetch(spritesVttUrl, { credentials: 'same-origin' })
      .then(r => r.text())
      .then(function (text) {
        const lines = text.split(/\r?\n/);
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;
          if (line.indexOf('-->') >= 0) {
            const parts = line.split('-->').map(s => s.trim());
            if (parts.length < 2) continue;
            const start = parseTimestamp(parts[0]);
            const end = parseTimestamp(parts[1]);
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
            }
            const absUrl = buildAbsoluteSpriteUrl(spriteRel);
            spriteCues.push({ start: start, end: end, spriteUrl: absUrl, x: x, y: y, w: w, h: h });
            if (end > spriteDurationApprox) spriteDurationApprox = end;
            i++;
          }
        }
        spritesLoaded = true;
        d('embed sprites VTT loaded', { cues: spriteCues.length, durationApprox: spriteDurationApprox });
      })
      .catch(function (err) {
        spritesLoadError = true;
        d('embed sprites VTT load failed', err);
      });
  }
  function showSpritePreview(clientX) {
    if (!spritesVttUrl || !spriteCues.length || !rail) return;
    const rect = rail.getBoundingClientRect();
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
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
    img.src = cue.spriteUrl;
    Object.assign(img.style, { position: 'absolute', left: (-cue.x) + 'px', top: (-cue.y) + 'px' });
    pop.appendChild(img);

    pop.style.display = 'block';
    const leftPx = Math.max(0, Math.min(rect.width - cue.w, x - cue.w / 2));
    pop.style.left = leftPx + 'px';
    pop.style.width = cue.w + 'px';
    pop.style.height = cue.h + 'px';
  }

  function showControls() {
    root.classList.remove('autohide');
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(function () { root.classList.add('autohide'); }, 1800);
  }
  function layoutFillViewport() {
    try {
      const H = window.innerHeight || document.documentElement.clientHeight || root.clientHeight || 0;
      if (H <= 0) return;
      wrap.style.height = H + 'px';
      video.style.height = '100%';
      video.style.width = '100%';
      video.style.objectFit = 'contain';
    } catch {}
  }
  function updateTimes() {
    try { duration = isFinite(video.duration) ? video.duration : 0; } catch { duration = 0; }
    if (tTot) tTot.textContent = fmtTime(duration);
    if (tCur) tCur.textContent = fmtTime(video.currentTime || 0);
  }
  function updateProgress() {
    const d0 = duration || 0, ct = video.currentTime || 0;
    const frac = d0 > 0 ? Math.max(0, Math.min(ct / d0, 1)) : 0;
    if (played) played.style.width = (frac * 100).toFixed(3) + '%';
    if (handle) handle.style.left = (frac * 100).toFixed(3) + '%';
    let b = 0;
    if (video.buffered && video.buffered.length > 0) { try { b = video.buffered.end(video.buffered.length - 1); } catch { b = 0; } }
    const bfrac = d0 > 0 ? Math.max(0, Math.min(b / d0, 1)) : 0;
    if (buf) buf.style.width = (bfrac * 100).toFixed(3) + '%';
  }
  function refreshVolIcon() {
    const v = video.muted ? 0 : video.volume;
    const label = (video.muted || v === 0) ? 'Mute' : 'Vol';
    const b = root.querySelector('.yrp-vol-btn');
    if (b) {
      b.textContent = label;
      b.classList.toggle('icon-mute', (label === 'Mute'));
      b.classList.toggle('icon-vol', (label !== 'Mute'));
    }
  }
  function setMutedToggle() { video.muted = !video.muted; refreshVolIcon(); }
  function playToggle() { if (video.paused) video.play().catch(function () { }); else video.pause(); }
  function seekByClientX(xc) {
    const r = rail.getBoundingClientRect();
    const x = Math.max(0, Math.min(xc - r.left, r.width));
    const f = r.width > 0 ? x / r.width : 0;
    const t = (duration || 0) * f;
    video.currentTime = t;
  }
  function updateTooltip(xc) {
    const tt = tooltip; if (!tt) return;
    const r = rail.getBoundingClientRect();
    const x = Math.max(0, Math.min(xc - r.left, r.width));
    const f = r.width > 0 ? x / r.width : 0;
    const t = (duration || 0) * f;
    tt.textContent = fmtTime(t);
    tt.style.left = (f * 100).toFixed(3) + '%';
    tt.hidden = false;
  }

  // ---- Menu helpers (Variant A) ----
  function ensureMenuMainSnapshot() {
    if (!menu) return;
    if (!menuMainHTML) menuMainHTML = menu.innerHTML || '';
  }
  function lockMenuHeightFromCurrent() {
    if (!menu) return;
    if (menuFixedMinHeight > 0) return;
    try {
      const r = menu.getBoundingClientRect();
      menuFixedMinHeight = Math.ceil(r.height || 0);
      if (menuFixedMinHeight > 0) menu.style.minHeight = menuFixedMinHeight + 'px';
    } catch {}
  }
  function resetMenuHeightLock() {
    if (!menu) return;
    menuFixedMinHeight = 0;
    menu.style.minHeight = '';
  }

  function ensureTransparentMenuButton(btn) {
    try {
      btn.style.background = 'transparent';
      btn.style.backgroundColor = 'transparent';
      btn.style.border = 'none';
      btn.style.boxShadow = 'none';
      btn.style.color = 'inherit';
      btn.style.textAlign = 'left';
      btn.style.width = '100%';
      btn.style.display = 'block';
    } catch {}
  }
  function styleBackButton(btn) {
    ensureTransparentMenuButton(btn);
    try {
      btn.style.background = 'rgba(255,255,255,0.12)';
      btn.style.backgroundColor = 'rgba(255,255,255,0.12)';
      btn.style.borderRadius = '4px';
      btn.style.fontWeight = '700';
      btn.style.marginBottom = '6px';
      btn.style.paddingLeft = '8px';
      btn.style.paddingRight = '8px';
    } catch {}
  }
  function withSubmenuChevron(btn) {
    try { btn.classList.add('has-submenu'); } catch {}
  }

  function normalizeQualitySectionTypography() {
    if (!menu) return;
    try {
      const secQ = menu.querySelector('.yrp-menu-section[data-section="quality"]');
      if (!secQ) return;

      const oldTitle = secQ.querySelector('.yrp-menu-title');
      if (oldTitle && oldTitle.parentNode) oldTitle.parentNode.removeChild(oldTitle);

      if (secQ.querySelector('.yrp-menu-item.quality-future')) return;

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'yrp-menu-item quality-future';
      btn.textContent = 'Quality (future)';
      btn.disabled = true;
      ensureTransparentMenuButton(btn);
      btn.style.opacity = '0.75';
      secQ.appendChild(btn);
    } catch {}
  }
  function removeFutureSubtitlesSection() {
    if (!menu) return;
    try {
      const sec = menu.querySelector('.yrp-menu-section[data-section="subtitles"]');
      if (sec && sec.parentNode) sec.parentNode.removeChild(sec);
    } catch {}
  }

  function insertMainEntry(label, action, extra = {}) {
    if (!menu) return null;
    const firstSection = menu.querySelector('.yrp-menu-section') || null;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'yrp-menu-item';
    btn.setAttribute('data-action', action);
    btn.textContent = label;

    ensureTransparentMenuButton(btn);

    if (extra.disabled === true) {
      btn.disabled = true;
      btn.style.opacity = '0.6';
    }
    if (extra.hasSubmenu === true) {
      withSubmenuChevron(btn);
    }

    if (firstSection && firstSection.parentNode === menu) menu.insertBefore(btn, firstSection);
    else menu.appendChild(btn);

    return btn;
  }

  function openMainMenuView() {
    if (!menu) return;
    ensureMenuMainSnapshot();
    menu.innerHTML = menuMainHTML;
    menuView = 'main';

    // remove old speed grid
    try {
      const secSpeed = menu.querySelector('.yrp-menu-section[data-section="speed"]');
      if (secSpeed && secSpeed.parentNode) secSpeed.parentNode.removeChild(secSpeed);
    } catch {}

    removeFutureSubtitlesSection();
    normalizeQualitySectionTypography();

    // add our top entries
    if (!menu.querySelector('.yrp-menu-item[data-action="open-speed"]')) {
      insertMainEntry('Speed', 'open-speed', { hasSubmenu: true });
    }
    if (!menu.querySelector('.yrp-menu-item[data-action="open-langs"]')) {
      insertMainEntry('Languages', 'open-langs', { hasSubmenu: true });
    }
    const hasSubs = anySubtitleTracks();
    if (!menu.querySelector('.yrp-menu-item[data-action="open-subs"]')) {
      const btn = insertMainEntry('Subtitles', 'open-subs', { hasSubmenu: true, disabled: !hasSubs });
      if (btn && !hasSubs) btn.title = 'No subtitles tracks';
    }
  }

  function buildScrollableListContainer() {
    const wrap = document.createElement('div');
    wrap.className = 'yrp-menu-scroll';
    Object.assign(wrap.style, {
      overflowY: 'auto',
      overflowX: 'hidden',
      maxHeight: 'calc(100% - 40px)',
      paddingRight: '2px'
    });
    return wrap;
  }

  function buildLangsMenuView() {
    if (!menu) return;
    menuView = 'langs';

    while (menu.firstChild) menu.removeChild(menu.firstChild);

    const back = document.createElement('button');
    back.type = 'button';
    back.className = 'yrp-menu-item';
    back.setAttribute('data-action', 'back');
    back.textContent = '← Back';
    styleBackButton(back);
    menu.appendChild(back);

    const sc = buildScrollableListContainer();
    menu.appendChild(sc);

    const list = trackInfoList();
    const cur = chooseActiveTrack();
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
      it.textContent = ti.label + suffix + (ti.lang === curLang ? ' ✓' : '');
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

  function speedOptions() { return [0.5, 0.75, 1, 1.25, 1.5, 2]; }
  function applySpeed(sp) {
    const s = parseFloat(String(sp));
    if (!isFinite(s) || s <= 0) return;
    video.playbackRate = s;
    try { localStorage.setItem('playback_speed', String(s)); } catch {}
  }
  function buildSpeedMenuView() {
    if (!menu) return;
    menuView = 'speed';

    while (menu.firstChild) menu.removeChild(menu.firstChild);

    const back = document.createElement('button');
    back.type = 'button';
    back.className = 'yrp-menu-item';
    back.setAttribute('data-action', 'back');
    back.textContent = '← Back';
    styleBackButton(back);
    menu.appendChild(back);

    const cur = isFinite(video.playbackRate) ? video.playbackRate : 1;
    speedOptions().forEach(function (s) {
      const it = document.createElement('button');
      it.type = 'button';
      it.className = 'yrp-menu-item';
      it.setAttribute('data-action', 'set-speed');
      it.setAttribute('data-speed', String(s));
      it.textContent = (s === 1 ? '1.0x' : (String(s) + 'x')) + (Math.abs(s - cur) < 0.001 ? ' ✓' : '');
      ensureTransparentMenuButton(it);
      menu.appendChild(it);
    });
  }

  function buildSubtitlesMenuView() {
    if (!menu) return;
    menuView = 'subs';

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

  function hideMenus() {
    if (menu) { menu.hidden = true; if (btnSettings) btnSettings.setAttribute('aria-expanded', 'false'); }
    if (ctx) ctx.hidden = true;
    root.classList.remove('vol-open');
    menuView = 'main';
    resetMenuHeightLock();
  }

  function refreshPlayBtn() {
    if (!btnPlay) return;
    const playing = !video.paused;
    btnPlay.classList.toggle('icon-play', !playing);
    btnPlay.classList.toggle('icon-pause', playing);
    btnPlay.setAttribute('aria-label', playing ? 'Pause (Space, K)' : 'Play (Space, K)');
    btnPlay.title = playing ? 'Pause (Space, K)' : 'Play (Space, K)';
    btnPlay.textContent = '';
  }

  // volume persistence (keep existing behavior)
  (function () {
    const vs = (function () { try { const x = localStorage.getItem('yrp:volume'); return x ? JSON.parse(x) : null; } catch { return null; } })();
    if (vs && typeof vs.v === 'number') video.volume = Math.max(0, Math.min(vs.v, 1));
    if (vs && typeof vs.m === 'boolean') video.muted = !!vs.m;
    if (volSlider) volSlider.value = String(video.volume || 1);
    refreshVolIcon();

    video.addEventListener('volumechange', function () {
      if (autoMuteApplied && video.muted && !userTouchedVolume) return;
      try { localStorage.setItem('yrp:volume', JSON.stringify({ v: Math.max(0, Math.min(video.volume || 0, 1)), m: !!video.muted })); } catch {}
    });
    video.addEventListener('loadedmetadata', function once() {
      video.removeEventListener('loadedmetadata', once);
      if (userTouchedVolume) return;
      const vs2 = (function () { try { const x = localStorage.getItem('yrp:volume'); return x ? JSON.parse(x) : null; } catch { return null; } })();
      if (vs2) {
        if (typeof vs2.v === 'number') video.volume = Math.max(0, Math.min(vs2.v, 1));
        if (typeof vs2.m === 'boolean') video.muted = !!vs2.m;
        if (volSlider) volSlider.value = String(video.volume || 1);
        refreshVolIcon();
      }
    });
  })();

  // speed persistence: keep old key yrp:speed but also support playback_speed
  (function () {
    // existing embed behavior key
    try {
      const sp = localStorage.getItem('yrp:speed');
      if (sp) {
        const v = parseFloat(sp);
        if (isFinite(v) && v > 0) video.playbackRate = v;
      }
    } catch {}
    // new unified key (prefer if present)
    if (isFinite(prefSpeed) && prefSpeed > 0) applySpeed(prefSpeed);

    video.addEventListener('ratechange', function () {
      try { localStorage.setItem('yrp:speed', String(video.playbackRate)); } catch {}
      try { localStorage.setItem('playback_speed', String(video.playbackRate)); } catch {}
    });
  })();

  // resume persistence (keep existing behavior)
  (function () {
    const vid = root.getAttribute('data-video-id') || '';
    if (!vid) return;
    function loadMap() { try { const s = localStorage.getItem('yrp:resume'); return s ? JSON.parse(s) : {}; } catch { return {}; } }
    function saveMap(m) { try { localStorage.setItem('yrp:resume', JSON.stringify(m)); } catch {} }
    const map = loadMap(), rec = map[vid], now = Date.now();
    function applyResume(t) {
      const d0 = isFinite(video.duration) ? video.duration : 0;
      if (d0 && t > 10 && t < d0 - 5) { try { video.currentTime = t; } catch {} }
    }
    if (rec && typeof rec.t === 'number' && (now - (rec.ts || 0)) < 180 * 24 * 3600 * 1000) {
      const setAt = Math.max(0, rec.t | 0);
      if (isFinite(video.duration) && video.duration > 0) applyResume(setAt);
      else video.addEventListener('loadedmetadata', function once() { video.removeEventListener('loadedmetadata', once); applyResume(setAt); });
    }
    const savePos = throttle(function () {
      const d0 = isFinite(video.duration) ? video.duration : 0;
      const cur = Math.max(0, Math.floor(video.currentTime || 0));
      const m = loadMap(); m[vid] = { t: cur, ts: Date.now(), d: d0 };
      const keys = Object.keys(m);
      if (keys.length > 200) {
        keys.sort(function (a, b) { return (m[a].ts || 0) - (m[b].ts || 0); });
        for (let i = 0; i < keys.length - 200; i++) delete m[keys[i]];
      }
      saveMap(m);
    }, 3000);
    video.addEventListener('timeupdate', function () { if (!video.paused && !video.seeking) savePos(); });
    video.addEventListener('ended', function () { const m = loadMap(); delete m[vid]; saveMap(m); });
  })();

  // autoplay (embed only if opt.autoplay === true) - keep existing behavior
  (function () {
    const host = root.closest('.player-host') || root;
    const opt = parseJSONAttr(host, 'data-options', null);
    const WANT = !!(opt && Object.prototype.hasOwnProperty.call(opt, 'autoplay') && opt.autoplay);
    d('autoplay check (embed)', { WANT: WANT, opt: opt });
    if (!WANT) return;
    function tryPlaySequence(reason) {
      d('tryPlaySequence', { reason: reason, muted: video.muted, rs: video.readyState });
      let p = null;
      try { p = video.play(); } catch (e) { d('play() threw sync', e); p = null; }
      if (p && typeof p.then === 'function') {
        p.then(function () { d('play() resolved'); }).catch(function (err) {
          d('play() rejected', { name: err && err.name, msg: err && err.message });
          if (!video.muted) {
            video.muted = true;
            video.setAttribute('muted', '');
            try { video.play().catch(function (e2) { d('retry rejected', e2); }); } catch (e2) { d('retry threw sync', e2); }
          }
        });
      } else {
        setTimeout(function () {
          if (video.paused) {
            video.muted = true;
            video.setAttribute('muted', '');
            try { video.play().catch(function (e3) { d('no-promise fallback rejected', e3); }); } catch (e3) { d('no-promise fallback threw', e3); }
          }
        }, 0);
      }
    }
    let fired = false;
    function fireOnce(tag) { if (fired) return; fired = true; tryPlaySequence(tag); }
    if (video.readyState >= 1) fireOnce('readyState>=1');
    ['loadedmetadata', 'loadeddata', 'canplay', 'canplaythrough'].forEach(function (ev) {
      const once = function () { video.removeEventListener(ev, once); fireOnce(ev); };
      video.addEventListener(ev, once);
    });
    setTimeout(function () { if (video.paused) tryPlaySequence('watchdog'); }, 1200);
  })();

  // bindings
  if (centerPlay) centerPlay.addEventListener('click', function () { playToggle(); });
  if (btnPlay) btnPlay.addEventListener('click', function () { playToggle(); });
  video.addEventListener('click', function () { playToggle(); });

  video.addEventListener('play', function () { root.classList.add('playing'); refreshPlayBtn(); });
  video.addEventListener('pause', function () { root.classList.remove('playing'); refreshPlayBtn(); });

  if (btnVol) btnVol.addEventListener('click', function (e) {
    e.preventDefault(); e.stopPropagation();
    userTouchedVolume = true;
    setMutedToggle();
    root.classList.add('vol-open');
    showControls();
    setTimeout(function () { root.classList.remove('vol-open'); }, 800);
  });

  if (controls) {
    controls.addEventListener('click', function (e) {
      let t = e.target; if (t && t.nodeType === 3 && t.parentNode) t = t.parentNode;
      if (t && t.classList && t.classList.contains('yrp-vol-btn')) {
        e.preventDefault(); e.stopPropagation();
        userTouchedVolume = true;
        setMutedToggle();
        root.classList.add('vol-open');
        showControls();
        setTimeout(function () { root.classList.remove('vol-open'); }, 800);
      }
    }, true);
  }

  if (volSlider) {
    volSlider.addEventListener('input', function () {
      userTouchedVolume = true;
      let v = parseFloat(volSlider.value || '1'); if (!isFinite(v)) v = 1;
      v = Math.max(0, Math.min(v, 1));
      video.volume = v; if (v > 0) video.muted = false; refreshVolIcon();
      root.classList.add('vol-open'); showControls();
    });
  }
  if (volWrap) {
    volWrap.addEventListener('wheel', function (e) {
      e.preventDefault();
      userTouchedVolume = true;
      const step = 0.05, v = video.muted ? 0 : video.volume;
      const nv = Math.max(0, Math.min(v + (e.deltaY < 0 ? step : -step), 1));
      video.volume = nv; if (nv > 0) video.muted = false;
      if (volSlider) volSlider.value = String(nv);
      refreshVolIcon(); root.classList.add('vol-open'); showControls();
    }, { passive: false });
  }

  if (progress && rail) {
    progress.addEventListener('mousedown', function (e) { seeking = true; seekByClientX(e.clientX); showControls(); });
    window.addEventListener('mousemove', function (e) { if (seeking) seekByClientX(e.clientX); });
    window.addEventListener('mouseup', function () { seeking = false; });
    progress.addEventListener('mousemove', function (e) {
      updateTooltip(e.clientX);
      if (spritesVttUrl && spritesLoaded && !spritesLoadError) {
        showSpritePreview(e.clientX);
      } else if (spritesVttUrl && !spritesLoaded && !spritesLoadError) {
        loadSpritesVTT();
      }
    });
    progress.addEventListener('mouseleave', function () {
      if (tooltip) tooltip.hidden = true;
      if (spritePop) spritePop.style.display = 'none';
    });
  }

  // Settings menu (Variant A)
  if (btnSettings && menu) {
    ensureMenuMainSnapshot();

    btnSettings.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      const isOpen = !menu.hidden;
      if (isOpen) {
        menu.hidden = true;
        btnSettings.setAttribute('aria-expanded', 'false');
        menuView = 'main';
        resetMenuHeightLock();
      } else {
        hideMenus();
        openMainMenuView();
        menu.hidden = false;
        btnSettings.setAttribute('aria-expanded', 'true');
        root.classList.add('vol-open');
        showControls();
        lockMenuHeightFromCurrent();
      }
    });

    menu.addEventListener('click', function (e) {
      const item = e.target && e.target.closest ? e.target.closest('.yrp-menu-item') : null;
      if (!item || !menu.contains(item)) return;

      const act = item.getAttribute('data-action') || '';
      const lang = item.getAttribute('data-lang') || '';

      if (menuView === 'main') {
        if (act === 'open-speed') {
          e.preventDefault(); e.stopPropagation();
          buildSpeedMenuView();
          lockMenuHeightFromCurrent();
          root.classList.add('vol-open'); showControls();
          return;
        }
        if (act === 'open-langs') {
          e.preventDefault(); e.stopPropagation();
          buildLangsMenuView();
          lockMenuHeightFromCurrent();
          root.classList.add('vol-open'); showControls();
          return;
        }
        if (act === 'open-subs') {
          e.preventDefault(); e.stopPropagation();
          if (!anySubtitleTracks()) return;
          buildSubtitlesMenuView();
          lockMenuHeightFromCurrent();
          root.classList.add('vol-open'); showControls();
          return;
        }
        return;
      }

      if (act === 'back') {
        e.preventDefault(); e.stopPropagation();
        openMainMenuView();
        lockMenuHeightFromCurrent();
        root.classList.add('vol-open'); showControls();
        return;
      }

      if (menuView === 'speed') {
        if (act === 'set-speed') {
          const sp = parseFloat(item.getAttribute('data-speed') || 'NaN');
          if (!isNaN(sp)) {
            e.preventDefault(); e.stopPropagation();
            applySpeed(sp);
            menu.hidden = true;
            btnSettings.setAttribute('aria-expanded', 'false');
            menuView = 'main';
            resetMenuHeightLock();
            return;
          }
        }
      }

      if (menuView === 'langs') {
        if (act === 'select-lang' && lang) {
          e.preventDefault(); e.stopPropagation();
          selectSubtitleLang(lang);
          menu.hidden = true;
          btnSettings.setAttribute('aria-expanded', 'false');
          menuView = 'main';
          resetMenuHeightLock();
          return;
        }
      }

      if (menuView === 'subs') {
        if (act === 'subs-on') {
          e.preventDefault(); e.stopPropagation();
          setSubtitlesEnabled(true);
          menu.hidden = true;
          btnSettings.setAttribute('aria-expanded', 'false');
          menuView = 'main';
          resetMenuHeightLock();
          return;
        }
        if (act === 'subs-off') {
          e.preventDefault(); e.stopPropagation();
          setSubtitlesEnabled(false);
          menu.hidden = true;
          btnSettings.setAttribute('aria-expanded', 'false');
          menuView = 'main';
          resetMenuHeightLock();
          return;
        }
      }
    });

    document.addEventListener('click', function (e) {
      if (!menu.hidden && !menu.contains(e.target) && e.target !== btnSettings) {
        menu.hidden = true;
        btnSettings.setAttribute('aria-expanded', 'false');
        menuView = 'main';
        resetMenuHeightLock();
      }
    });

    document.addEventListener('keydown', function (ev) {
      if (ev.code === 'Escape' || (ev.key || '').toLowerCase() === 'escape') {
        if (!menu.hidden) {
          menu.hidden = true;
          btnSettings.setAttribute('aria-expanded', 'false');
          menuView = 'main';
          resetMenuHeightLock();
        }
      }
    });
  }

  if (btnFull) {
    btnFull.addEventListener('click', function () {
      if (document.fullscreenElement) { document.exitFullscreen().catch(function () {}); }
      else { root.requestFullscreen && root.requestFullscreen().catch(function () {}); }
    });
  }
  if (btnPip) {
    btnPip.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      try {
        if (document.pictureInPictureEnabled && video.requestPictureInPicture && !video.disablePictureInPicture) {
          if (document.pictureInPictureElement === video) { document.exitPictureInPicture().catch(function () {}); }
          else {
            const need = video.paused, prev = video.muted;
            let p = Promise.resolve();
            if (need) { video.muted = true; p = video.play().catch(function () {}); }
            p.then(function () { return video.requestPictureInPicture(); })
              .catch(function () {})
              .then(function () { if (need) { video.pause(); video.muted = prev; } });
          }
        }
      } catch {}
    });
  }

  // context menu (keep existing)
  root.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    hideMenus();
    if (!ctx) return;
    const rw = root.getBoundingClientRect();
    ctx.style.left = (e.clientX - rw.left) + 'px';
    ctx.style.top = (e.clientY - rw.top) + 'px';
    ctx.hidden = false;
    root.classList.add('vol-open'); showControls();
  });
  if (ctx) {
    ctx.addEventListener('click', function (ev) {
      const act = ev.target && ev.target.getAttribute('data-action');
      const at = Math.floor(video.currentTime || 0);
      const vid = root.getAttribute('data-video-id') || '';
      if (act === 'pip') {
        btnPip && btnPip.click();
      } else if (act === 'copy-url') {
        const u = new URL(window.location.href);
        u.searchParams.delete('t');
        copyText(u.toString());
      } else if (act === 'copy-url-time') {
        const u2 = new URL(window.location.href);
        u2.searchParams.set('t', String(at));
        copyText(u2.toString());
      } else if (act === 'copy-embed') {
        const src = (window.location.origin || '') + '/embed?v=' + encodeURIComponent(vid || '');
        const iframe = '<iframe width="560" height="315" src="' + src + '" frameborder="0" allow="autoplay; encrypted-media; clipboard-write" allowfullscreen></iframe>';
        copyText(iframe);
      }
      ctx.hidden = true;
    });
    document.addEventListener('click', function (e2) {
      if (!ctx.hidden && !ctx.contains(e2.target)) ctx.hidden = true;
    });
    document.addEventListener('keydown', function escClose(ev) {
      if (ev.code === 'Escape' || (ev.key || '').toLowerCase() === 'escape') {
        if (!ctx.hidden) ctx.hidden = true;
      }
    });
  }

  function handleHotkey(e) {
    const t = e.target; const tag = t && t.tagName ? t.tagName.toUpperCase() : '';
    if (t && (t.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA')) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const code = e.code, key = (e.key || '').toLowerCase();
    if (code === 'Space' || code === 'Enter' || code === 'NumpadEnter' || code === 'MediaPlayPause' || code === 'KeyK' || key === 'k') {
      e.preventDefault(); video.paused ? video.play().catch(function () {}) : video.pause(); return;
    }
    if (code === 'ArrowLeft' || code === 'KeyJ' || key === 'j') {
      e.preventDefault(); video.currentTime = Math.max(0, (video.currentTime || 0) - 5); return;
    }
    if (code === 'ArrowRight' || code === 'KeyL' || key === 'l') {
      e.preventDefault(); const dUR = isFinite(video.duration) ? video.duration : 1e9; video.currentTime = Math.min((video.currentTime || 0) + 5, dUR); return;
    }
    if (code === 'KeyM' || key === 'm') { e.preventDefault(); setMutedToggle(); return; }
    if (code === 'KeyF' || key === 'f') { e.preventDefault(); if (btnFull) btnFull.click(); return; }
    if (code === 'KeyI' || key === 'i') { e.preventDefault(); if (btnPip) btnPip.click(); return; }
    if (code === 'Escape' || key === 'escape') { hideMenus(); return; }
  }
  document.addEventListener('keydown', handleHotkey);

  ['mouseenter', 'mousemove', 'pointermove', 'touchstart'].forEach(function (ev) {
    (controls || root).addEventListener(ev, function () { try { root.focus(); } catch {} showControls(); }, { passive: true });
  });
  root.addEventListener('mouseleave', function () { setTimeout(function () { root.classList.add('autohide'); }, 600); });

  function relayout() { layoutFillViewport(); }
  window.addEventListener('resize', relayout);
  setTimeout(relayout, 0);
  setTimeout(relayout, 100);

  function attachCue() {
    try {
      const tr = chooseActiveTrack();
      if (!tr) return;
      tr.addEventListener('cuechange', updateOverlayText);
      tr.addEventListener('load', updateOverlayText);
    } catch {}
  }

  video.addEventListener('loadedmetadata', function () {
    // restore preferred lang (if exists)
    if (prefLang) {
      const idx = findTrackIndexByLang(prefLang);
      if (idx >= 0) activeTrackIndex = idx;
    }
    // apply initial modes and ui
    applyTrackModes();
    updateOverlayText();
    refreshSubtitlesBtnUI();
    attachCue();

    updateTimes();
    updateProgress();
    relayout();
    loadSpritesVTT();
    refreshPlayBtn();

    // if menu already open, refresh current view
    if (menu && !menu.hidden) {
      if (menuView === 'main') openMainMenuView();
      else if (menuView === 'langs') buildLangsMenuView();
      else if (menuView === 'speed') buildSpeedMenuView();
      else if (menuView === 'subs') buildSubtitlesMenuView();
    }
  });

  video.addEventListener('timeupdate', function () { updateTimes(); updateProgress(); updateOverlayText(); });
  video.addEventListener('progress', function () { updateProgress(); });

  if (ccBtn) {
    ccBtn.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      if (!anySubtitleTracks()) return;
      overlayActive = !overlayActive;
      updateOverlayText();
      refreshSubtitlesBtnUI();
      showControls();
    });
  }
}