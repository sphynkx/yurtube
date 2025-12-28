import { fmtTime, clamp, parseJSONAttr } from './util.js';
import { installFallbackGuards } from './fallback.js';
import { attachPlaylist } from './playlist.js';

function detectPlayerName() {
  try {
    const u = new URL(import.meta.url);
    const m = u.pathname.match(/\/static\/players\/([^\/]+)\//);
    if (m && m[1]) return m[1];
  } catch {}
  try {
    const s = (document.currentScript && document.currentScript.src) || '';
    const m2 = s.match(/\/static\/players\/([^\/]+)\//);
    if (m2 && m2[1]) return m2[1];
  } catch {}
  try {
    const host = document.querySelector('.player-host[data-player]');
    if (host) {
      const pn = String(host.getAttribute('data-player') || '').trim();
      if (pn) return pn;
    }
  } catch {}
  return 'standard';
}

function tryPlay(video, onDebug) {
  let p = null;
  try { p = video.play(); } catch (e) { onDebug && onDebug('play threw', e); p = null; }
  if (p && typeof p.then === 'function') {
    p.then(function(){ onDebug && onDebug('play resolved'); })
     .catch(function(err){
       onDebug && onDebug('play rejected', { name: err && err.name, msg: err && err.message });
       if (!video.muted) {
         video.muted = true;
         video.setAttribute('muted', '');
         try { video.play(); } catch {}
       }
     });
  } else {
    setTimeout(function(){
      if (video.paused) {
        video.muted = true;
        video.setAttribute('muted', '');
        try { video.play(); } catch {}
      }
    }, 0);
  }
}

export function initAll() {
  const PLAYER_NAME = detectPlayerName();
  const PLAYER_BASE = '/static/players/' + PLAYER_NAME;
  const hosts = document.querySelectorAll('.player-host[data-player="' + PLAYER_NAME + '"]');
  if (hosts.length === 0) return;

  fetch(PLAYER_BASE + '/templates/player.html', { credentials: 'same-origin' })
    .then(r => r.text())
    .then(function (html) {
      for (let i = 0; i < hosts.length; i++) mountOne(hosts[i], html, PLAYER_BASE);
    })
    .catch(function(){});
}

function mountOne(host, tpl, PLAYER_BASE) {
  host.innerHTML = tpl;

  const root = host.querySelector('.yrp-container');
  const wrap = root.querySelector('.yrp-video-wrap');
  const video = root.querySelector('.yrp-video');
  const source = video.querySelector('source');
  const centerBtn = root.querySelector('.yrp-center-play');
  const centerLogo = root.querySelector('.yrp-center-logo');

  const src = host.getAttribute('data-video-src') || '';
  const poster = host.getAttribute('data-poster-url') || '';
  const subs = parseJSONAttr(host, 'data-subtitles', []);
  const opts = parseJSONAttr(host, 'data-options', {});
  const spritesVtt = host.getAttribute('data-sprites-vtt') || '';
  const captionVtt = host.getAttribute('data-caption-vtt') || '';
  const captionLang = host.getAttribute('data-caption-lang') || '';

  const DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);
  function d(){ if (!DEBUG) return; try { console.debug.apply(console, ['[STD]'].concat([].slice.call(arguments))); } catch {} }

  if (centerLogo) centerLogo.setAttribute('src', PLAYER_BASE + '/img/logo.png');

  if (source) source.setAttribute('src', src);
  if (poster) video.setAttribute('poster', poster);
  if (opts && opts.muted) video.setAttribute('muted', '');
  if (opts && opts.loop) video.setAttribute('loop', '');
  video.setAttribute('playsinline', '');
  video.setAttribute('controls', '');

  if (Array.isArray(subs)) {
    subs.forEach(function (t) {
      if (!t || !t.src) return;
      const tr = document.createElement('track');
      tr.setAttribute('kind', 'subtitles');
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
      ctr.setAttribute('kind', 'subtitles');
      ctr.setAttribute('src', captionVtt);
      ctr.setAttribute('srclang', captionLang || 'auto');
      ctr.setAttribute('label', captionLang || 'Original');
      ctr.setAttribute('default', '');
      video.appendChild(ctr);
    } catch(e){ d('caption track append failed', e); }
  }

  function ensureTextTracksMode() {
    try {
      const tt = video.textTracks;
      if (!tt || tt.length === 0) return;
      const want = !!(opts && opts.subtitles === true);
      let anyShown = false;
      for (let i = 0; i < tt.length; i++) {
        const tr = tt[i];
        if (tr.kind === 'subtitles' || tr.kind === 'captions') {
          const show = want || (tr.language === (captionLang || tr.srclang));
          if (!anyShown && show) { tr.mode = 'showing'; anyShown = true; }
          else tr.mode = 'hidden';
        }
      }
      if (!anyShown) {
        for (let i = 0; i < tt.length; i++) {
          const tr = tt[i];
          if (tr.kind === 'subtitles' || tr.kind === 'captions') { tr.mode = 'showing'; break; }
        }
      }
    } catch {}
  }

  try { video.load(); d('video.load() called', { src }); } catch (e) { d('video.load() error', e); }
  installFallbackGuards(video, source, d);

  function syncPlayingClass() {
    if (video.paused) root.classList.remove('playing');
    else root.classList.add('playing');
  }

  ['loadedmetadata','loadeddata','canplay','canplaythrough','play','playing','pause','stalled','suspend','waiting','error','abort','emptied'].forEach(function(ev){
    video.addEventListener(ev, function(){ d('event', ev, { rs: video.readyState, paused: video.paused, muted: video.muted }); });
  });
  video.addEventListener('play', syncPlayingClass);
  video.addEventListener('pause', syncPlayingClass);

  video.addEventListener('loadedmetadata', function(){
    ensureTextTracksMode();
    try {
      const tt = video.textTracks;
      for (let i = 0; i < tt.length; i++) {
        const tr = tt[i];
        tr.addEventListener && tr.addEventListener('load', ensureTextTracksMode);
      }
    } catch {}
  });

  let toggleLock = false;
  function safeToggle() {
    if (toggleLock) return;
    toggleLock = true;
    setTimeout(function(){ toggleLock = false; }, 180);
    if (video.paused) { tryPlay(video, d); } else { video.pause(); }
  }
  if (centerBtn) centerBtn.addEventListener('click', function(){ safeToggle(); });

  function onKey(e) {
    const t = e.target; const tag = t && t.tagName ? t.tagName.toUpperCase() : '';
    if (t && (t.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA')) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = (e.key || '').toLowerCase(); const code = e.code || '';
    if (k === 'j' || code === 'ArrowLeft') {
      e.preventDefault();
      video.currentTime = Math.max(0, (video.currentTime || 0) - 5);
    } else if (k === 'l' || code === 'ArrowRight') {
      e.preventDefault();
      const dUR = isFinite(video.duration) ? video.duration : 1e9;
      video.currentTime = Math.min((video.currentTime || 0) + 5, dUR);
    } else if (k === 'm') {
      e.preventDefault(); video.muted = !video.muted;
    } else if (k === 'f') {
      e.preventDefault();
      if (document.fullscreenElement) document.exitFullscreen().catch(function(){});
      else root.requestFullscreen && root.requestFullscreen().catch(function(){});
    }
  }
  document.addEventListener('keydown', onKey);

  (function(){
    const want = !!(opts && opts.autoplay === true);
    d('autoplay check', { WANT: want, opt: opts });
    if (!want) return;
    function attempt(tag){ d('autoplay attempt', tag); tryPlay(video, d); }
    if (video.readyState >= 1) attempt('readyState>=1');
    const once = function(){ video.removeEventListener('canplay', once); attempt('canplay'); };
    video.addEventListener('canplay', once);
    setTimeout(function(){ if (video.paused) attempt('watchdog'); }, 1200);
  })();

  (function(){
    let start = 0;
    if (opts && typeof opts.start === 'number' && opts.start > 0) start = Math.max(0, opts.start);
    if (!start) return;
    const apply = function(){ try { video.currentTime = Math.min(start, Math.floor(video.duration || start)); } catch{} };
    if (isFinite(video.duration) && video.duration > 0) apply();
    else video.addEventListener('loadedmetadata', function once(){ video.removeEventListener('loadedmetadata', once); apply(); });
  })();

  // ===== Sprites in fullscreen (buggy!!) =====
  (function sprites(){
    const spriteCues = [];
    let spritesLoaded = false;
    let spritesLoadError = false;
    let spritePop = null;
    let spriteDurationApprox = 0;

    const FALLBACK_W = 160;
    const FALLBACK_H = 90;

    function parseTimestamp(ts){
      const m = String(ts || '').match(/^(\d{2}):(\d{2}):(\d{2}\.\d{3})$/);
      if(!m) return 0;
      const h = parseInt(m[1],10), mm = parseInt(m[2],10), ss = parseFloat(m[3]);
      return h*3600 + mm*60 + ss;
    }
    function buildAbsoluteSpriteUrl(vttUrl, rel){
      if(!rel) return '';
      if(/^https?:\/\//i.test(rel) || rel.startsWith('/')) return rel;
      try {
        const u = new URL(vttUrl, window.location.origin);
        const baseDir = u.pathname.replace(/\/sprites\.vtt$/, '');
        return baseDir + '/' + rel.replace(/^\/+/,'');
      } catch{ return rel; }
    }

    function hostEl() {
      return document.fullscreenElement || wrap || root;
    }

    function ensureSpritePop(){
      if (spritePop) return spritePop;
      spritePop = document.createElement('div');
      spritePop.className = 'std-sprite-pop';
      spritePop.style.pointerEvents = 'none';
      spritePop.style.display = 'none';
      spritePop.style.border = '1px solid #333';
      spritePop.style.background = '#000';
      spritePop.style.overflow = 'hidden';
      spritePop.style.boxShadow = '0 4px 12px rgba(0,0,0,.4)';
      spritePop.style.borderRadius = '4px';
      spritePop.style.zIndex = '9999';

      const host = hostEl();
      if (!document.fullscreenElement) {
        spritePop.style.position = 'absolute';
        const container = host;
        if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
        container.appendChild(spritePop);
      } else {
        spritePop.style.position = 'fixed';
        host.appendChild(spritePop);
      }
      return spritePop;
    }

    document.addEventListener('fullscreenchange', function(){
      if (!spritePop) return;
      const host = hostEl();
      try {
        host.appendChild(spritePop);
        spritePop.style.position = document.fullscreenElement ? 'fixed' : 'absolute';
      } catch {}
    });

    function loadSpritesVTT(){
      if (!spritesVtt || spritesLoaded || spritesLoadError) return;
      fetch(spritesVtt, { credentials: 'same-origin' })
        .then(r => r.text())
        .then(function(text){
          const lines = text.split(/\r?\n/);
          for (let i=0; i<lines.length; i++){
            const line = lines[i].trim();
            if(!line) continue;
            if(line.indexOf('-->') >= 0){
              const parts = line.split('-->').map(s => s.trim());
              if (parts.length < 2) continue;
              const start = parseTimestamp(parts[0]);
              const end = parseTimestamp(parts[1]);
              const ref = (lines[i+1]||'').trim();
              let spriteRel='', x=0,y=0,w=0,h=0;
              const hashIdx = ref.indexOf('#xywh=');
              if (hashIdx > 0) {
                spriteRel = ref.substring(0, hashIdx);
                const xywh = ref.substring(hashIdx+6).split(',');
                if (xywh.length === 4) {
                  x = parseInt(xywh[0],10);
                  y = parseInt(xywh[1],10);
                  w = parseInt(xywh[2],10);
                  h = parseInt(xywh[3],10);
                }
              }
              const absUrl = buildAbsoluteSpriteUrl(spritesVtt, spriteRel);
              spriteCues.push({start,end,spriteUrl:absUrl,x,y,w,h});
              if(end > spriteDurationApprox) spriteDurationApprox = end;
              i++;
            }
          }
          spritesLoaded = true;
          d('sprites VTT loaded (standard)', {cues: spriteCues.length, durationApprox: spriteDurationApprox});
        })
        .catch(function(err){
          spritesLoadError = true;
          d('sprites VTT load failed (standard)', err);
        });
    }

    function showSpritePreview(evt){
      if (!spritesVtt || !spriteCues.length) return;

      const rectVideo = video.getBoundingClientRect();
      const rectHost  = hostEl().getBoundingClientRect();

      const SHIFT_UP = Math.max(36, Math.min(140, Math.round(rectVideo.height * 0.12)));

      const clientX = evt.clientX;
      const xInside = Math.max(rectVideo.left, Math.min(clientX, rectVideo.right));
      let frac = (rectVideo.width > 0) ? (xInside - rectVideo.left) / rectVideo.width : 0;
      frac = Math.max(0, Math.min(1, frac));
      const tRef = (isFinite(video.duration) && video.duration > 0) ? video.duration : spriteDurationApprox;
      const t = tRef * frac;
      let cue = null;
      for (let i=0; i<spriteCues.length; i++){
        const c = spriteCues[i];
        if (t >= c.start && t < c.end) { cue = c; break; }
      }
      const pop = ensureSpritePop();
      if (!cue || !cue.spriteUrl) { pop.style.display = 'none'; return; }

      const cw = cue.w > 0 ? cue.w : FALLBACK_W;
      const ch = cue.h > 0 ? cue.h : FALLBACK_H;

      while (pop.firstChild) pop.removeChild(pop.firstChild);
      const img = document.createElement('img');
      img.src = cue.spriteUrl;
      img.style.position = 'absolute';
      img.style.left = (-cue.x) + 'px';
      img.style.top = (-cue.y) + 'px';
      img.style.pointerEvents = 'none';
      pop.appendChild(img);

      pop.style.display = 'block';
      pop.style.width = cw + 'px';
      pop.style.height = ch + 'px';

      const isFs = !!document.fullscreenElement;

      let offsetX = isFs
        ? clamp(xInside - cw/2, rectHost.left, rectHost.right - cw)
        : clamp(xInside - rectHost.left - cw/2, rectVideo.left - rectHost.left, rectVideo.right - rectHost.left - cw);

      const bottomLine = rectVideo.bottom - (isFs ? 0 : rectHost.top);
      let topPos = bottomLine - ch - SHIFT_UP;
      if (!isFs) topPos = Math.max(0, topPos);

      pop.style.left = offsetX + 'px';
      pop.style.top  = topPos + 'px';
    }

    if (spritesVtt) {
      video.addEventListener('loadedmetadata', function(){ loadSpritesVTT(); });
      setTimeout(function(){ if(!spritesLoaded && !spritesLoadError) loadSpritesVTT(); }, 2500);
      video.addEventListener('mousemove', function(e){ if (spritesLoaded) showSpritePreview(e); });
      video.addEventListener('mouseleave', function(){ if (spritePop) spritePop.style.display = 'none'; });
    }
  })();
  // ===== end sprites =====

  attachPlaylist({ root, video, DEBUG });
  syncPlayingClass();
}