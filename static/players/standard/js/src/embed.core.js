import { parseJSONAttr, clamp } from './util.js';
import { installFallbackGuards } from './fallback.js';

function detectPlayerName(){
  try{ const u=new URL(import.meta.url); const m=u.pathname.match(/\/static\/players\/([^\/]+)\//); if(m && m[1]) return m[1]; }catch{}
  try{ const s=(document.currentScript&&document.currentScript.src)||''; const m2=s.match(/\/static\/players\/([^\/]+)\//); if(m2 && m2[1]) return m2[1]; }catch{}
  try{ const host=document.querySelector('.player-host[data-player]'); if(host){ const pn=String(host.getAttribute('data-player')||'').trim(); if(pn) return pn; } }catch{}
  return 'standard';
}

function tryPlay(video, onDebug) {
  let p=null;
  try { p = video.play(); } catch (e) { onDebug && onDebug('play threw', e); p=null; }
  if (p && typeof p.then === 'function') {
    p.then(function(){ onDebug && onDebug('play resolved'); })
     .catch(function(err){
       onDebug && onDebug('play rejected', { name: err && err.name, msg: err && err.message });
       if (!video.muted) {
         video.muted = true;
         video.setAttribute('muted', '');
         try { video.play(); } catch{}
       }
     });
  } else {
    setTimeout(function(){
      if (video.paused) {
        video.muted = true;
        video.setAttribute('muted', '');
        try { video.play(); } catch{}
      }
    }, 0);
  }
}

// ===== NEW: quality/download overlay for standard embed =====
function attachMediaMenus({ root, host, video, DEBUG }) {
  const d = (...a) => { if (!DEBUG) return; try { console.debug('[STD-EMBED-MEDIA]', ...a); } catch {} };

  const sources = parseJSONAttr(host, 'data-sources', []);
  const permitDownload = String(host.getAttribute('data-permit-download') || '').trim() === '1';
  const downloadItems = parseJSONAttr(host, 'data-download-items', []);

  const wrap = root.querySelector('.yrp-video-wrap');
  const mount = root.querySelector('.std-ext-media[data-std-media="1"]');

  if (!wrap || !mount) return;

  const hasQuality = Array.isArray(sources) && sources.filter(s => s && s.src).length > 1;
  const hasDownload = !!permitDownload && Array.isArray(downloadItems) && downloadItems.length > 0;

  if (!hasQuality && !hasDownload) return;

  try {
    if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';
  } catch {}

  mount.innerHTML = '';
  Object.assign(mount.style, {
    position: 'absolute',
    right: '12px',
    top: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    zIndex: '30',
    pointerEvents: 'auto',
    alignItems: 'flex-end'
  });

  function mkRow(labelText) {
    const row = document.createElement('div');
    Object.assign(row.style, {
      display: 'flex',
      gap: '6px',
      alignItems: 'center',
      background: 'rgba(0,0,0,0.45)',
      border: '1px solid rgba(255,255,255,0.12)',
      padding: '6px 8px',
      borderRadius: '8px',
      color: '#fff',
      fontSize: '12px',
      lineHeight: '1',
      backdropFilter: 'blur(2px)'
    });

    const lab = document.createElement('div');
    lab.textContent = labelText;
    lab.style.opacity = '0.9';
    lab.style.whiteSpace = 'nowrap';
    row.appendChild(lab);

    return { row };
  }

  function mkSelect() {
    const sel = document.createElement('select');
    Object.assign(sel.style, {
      fontSize: '12px',
      padding: '3px 6px',
      borderRadius: '6px',
      border: '1px solid rgba(255,255,255,0.22)',
      background: 'rgba(0,0,0,0.55)',
      color: '#fff',
      outline: 'none'
    });
    return sel;
  }

  function currentSourceUrl() {
    try {
      const srcEl = video.querySelector('source');
      return (srcEl && (srcEl.getAttribute('src') || srcEl.src)) ? String(srcEl.getAttribute('src') || srcEl.src || '') : '';
    } catch { return ''; }
  }

  const videoIdForPref = root.getAttribute('data-video-id') || '';
  const qualityPrefKey = videoIdForPref ? ('yrp:quality:' + videoIdForPref) : 'yrp:quality';

  function switchSourceTo(newSrc) {
    if (!newSrc) return;

    const srcEl = video.querySelector('source');
    if (!srcEl) return;

    const cur = currentSourceUrl();
    if (cur && cur === newSrc) return;

    const wasPlaying = !video.paused;
    const t = Math.max(0, video.currentTime || 0);
    const rate = (isFinite(video.playbackRate) && video.playbackRate > 0) ? video.playbackRate : 1;
    const vol = isFinite(video.volume) ? video.volume : 1;
    const muted0 = !!video.muted;

    try { localStorage.setItem(qualityPrefKey, String(newSrc)); } catch {}

    try {
      srcEl.setAttribute('src', String(newSrc));
      try { srcEl.src = String(newSrc); } catch {}
      video.load();
    } catch (e) {
      d('switchSource load error', e);
      return;
    }

    const onMeta = function () {
      video.removeEventListener('loadedmetadata', onMeta);
      try { video.playbackRate = rate; } catch {}
      try { video.volume = vol; } catch {}
      try { video.muted = muted0; } catch {}

      try {
        const dur = isFinite(video.duration) ? video.duration : 0;
        if (dur > 0) {
          const target = Math.min(t, Math.max(0, dur - 0.25));
          video.currentTime = target;
        }
      } catch {}

      if (wasPlaying) {
        try { video.play().catch(function(){}); } catch {}
      }
    };
    video.addEventListener('loadedmetadata', onMeta);
  }

  if (hasQuality) {
    const { row } = mkRow('Quality');
    const sel = mkSelect();

    const list = sources.filter(s => s && s.src).map(s => ({
      label: String(s.label || s.preset || 'Quality'),
      src: String(s.src || '')
    }));

    list.forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s.src;
      opt.textContent = s.label;
      sel.appendChild(opt);
    });

    const pref = (function(){ try { return String(localStorage.getItem(qualityPrefKey) || ''); } catch { return ''; } })();
    const curSrc = currentSourceUrl();
    const initial = pref || curSrc || (list[0] && list[0].src) || '';
    if (initial) {
      sel.value = initial;
      if (pref && pref !== curSrc) setTimeout(() => switchSourceTo(pref), 0);
    }

    sel.addEventListener('change', function () {
      const v = String(sel.value || '');
      if (!v) return;
      switchSourceTo(v);
    });

    row.appendChild(sel);
    mount.appendChild(row);
  }

  if (hasDownload) {
    const { row } = mkRow('Download');
    const sel = mkSelect();

    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = 'Select…';
    sel.appendChild(ph);

    downloadItems.forEach((it) => {
      if (!it || !it.url) return;
      const opt = document.createElement('option');
      opt.value = String(it.url || '');
      opt.textContent = String(it.label || 'Download');
      sel.appendChild(opt);
    });

    sel.addEventListener('change', function () {
      const url = String(sel.value || '');
      if (!url) return;
      try { window.open(url, '_blank', 'noopener'); }
      catch { window.location.href = url; }
      sel.value = '';
    });

    row.appendChild(sel);
    mount.appendChild(row);
  }
}

export function initEmbed(){
  const PLAYER_NAME = detectPlayerName();
  const PLAYER_BASE = '/static/players/' + PLAYER_NAME;
  const hosts = document.querySelectorAll('.player-host[data-player="' + PLAYER_NAME + '"]');
  if (hosts.length===0) return;

  fetch(PLAYER_BASE + '/templates/player.html', { credentials: 'same-origin' })
    .then(r => r.text())
    .then(function(html){ for (let i=0; i<hosts.length; i++) mountOne(hosts[i], html, PLAYER_BASE); })
    .catch(function(){});
}

function mountOne(host, tpl, PLAYER_BASE){
  host.innerHTML = tpl;

  const root = host.querySelector('.yrp-container');
  const wrap = root.querySelector('.yrp-video-wrap');
  const video = root.querySelector('.yrp-video');
  const source = video.querySelector('source');
  const centerBtn = root.querySelector('.yrp-center-play');
  const centerLogo = root.querySelector('.yrp-center-logo');

  const src = host.getAttribute('data-video-src') || '';
  const poster = host.getAttribute('data-poster-url') || '';
  const subs = parseJSONAttr(host,'data-subtitles',[]);
  const opts = parseJSONAttr(host,'data-options',{});
  const spritesVtt = host.getAttribute('data-sprites-vtt') || '';
  const captionVtt = host.getAttribute('data-caption-vtt') || '';
  const captionLang = host.getAttribute('data-caption-lang') || '';

  const DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);
  function d(){ if(!DEBUG) return; try { console.debug.apply(console, ['[STD-EMBED]'].concat([].slice.call(arguments))); } catch{} }

  // --- English label helper for native track menu ---
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

  if (centerLogo) centerLogo.setAttribute('src', PLAYER_BASE + '/img/logo.png');

  if (source) source.setAttribute('src', src);
  if (poster) video.setAttribute('poster', poster);
  if (opts && opts.muted) video.setAttribute('muted', '');
  if (opts && opts.loop) video.setAttribute('loop', '');
  video.setAttribute('playsinline','');
  video.setAttribute('controls','');

  if (Array.isArray(subs)) {
    subs.forEach(function (t) {
      if (!t || !t.src) return;
      const tr = document.createElement('track');
      tr.setAttribute('kind','subtitles');
      if (t.srclang) tr.setAttribute('srclang', String(t.srclang));

      const code = String(t.srclang || '').toLowerCase();
      const rawLabel = String(t.label || code || 'Subtitles');
      tr.setAttribute('label', langDisplayNameEn(code, rawLabel) + (code ? ` (${code})` : ''));

      tr.setAttribute('src', String(t.src));
      if (t.default) tr.setAttribute('default','');
      video.appendChild(tr);
    });
  }
  if (captionVtt) {
    try {
      const ctr = document.createElement('track');
      ctr.setAttribute('kind', 'subtitles');
      ctr.setAttribute('src', captionVtt);
      ctr.setAttribute('srclang', captionLang || 'auto');

      const code2 = String(captionLang || 'auto').toLowerCase();
      const raw2 = String(captionLang || 'Original');
      ctr.setAttribute('label', langDisplayNameEn(code2, raw2) + (code2 ? ` (${code2})` : ''));

      ctr.setAttribute('default', '');
      video.appendChild(ctr);
    } catch(e){ d('caption track append failed', e); }
  }

  try { video.load(); d('video.load() called', { src }); } catch (e) { d('video.load() error', e); }
  installFallbackGuards(video, source, d);

  function syncPlayingClass(){
    if (video.paused) root.classList.remove('playing');
    else root.classList.add('playing');
  }

  ['loadedmetadata','loadeddata','canplay','canplaythrough','play','pause','stalled','suspend','waiting','error','abort','emptied'].forEach(function(ev){
    video.addEventListener(ev, function(){ d('event', ev, { rs: video.readyState, paused: video.paused, muted: video.muted }); });
  });
  video.addEventListener('play', syncPlayingClass);
  video.addEventListener('pause', syncPlayingClass);

  function layoutFillViewport(){
    try {
      const H = window.innerHeight || document.documentElement.clientHeight || root.clientHeight || 0;
      if (H <= 0) return;
      wrap.style.height = H + 'px';
      video.style.height = '100%';
      video.style.width = '100%';
      video.style.objectFit = 'contain';
    } catch{}
  }
  window.addEventListener('resize', layoutFillViewport);
  window.addEventListener('orientationchange', layoutFillViewport);
  layoutFillViewport();
  setTimeout(layoutFillViewport, 0);
  setTimeout(layoutFillViewport, 100);

  let toggleLock=false;
  function safeToggle(){
    if (toggleLock) return;
    toggleLock = true;
    setTimeout(function(){ toggleLock=false; }, 180);
    if (video.paused) { tryPlay(video, d); } else { video.pause(); }
  }
  if (centerBtn) centerBtn.addEventListener('click', function(){ safeToggle(); });

  // NEW: mount quality/download overlay
  attachMediaMenus({ root, host, video, DEBUG });

  syncPlayingClass();
}