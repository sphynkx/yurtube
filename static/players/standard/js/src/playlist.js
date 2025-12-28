import { load, save } from './storage.js';
import { applyIcon } from './icons.js';

export async function attachPlaylist({ root, video, DEBUG }) {
  const d = (...a) => { if (!DEBUG) return; try { console.debug('[STD-PL]', ...a); } catch {} };

  const url = new URL(window.location.href);
  const playlistId = url.searchParams.get('p');
  const currentVid = url.searchParams.get('v') || (root.getAttribute('data-video-id') || '');

  // Helpers: subtitles
  function subtitleTracks() {
    try {
      const tt = video.textTracks || [];
      return Array.prototype.filter.call(tt, (tr) => tr && (tr.kind === 'subtitles' || tr.kind === 'captions'));
    } catch { return []; }
  }
  function anySubtitleTracks() { return subtitleTracks().length > 0; }
  function isCcOn() {
    const subs = subtitleTracks();
    return subs.some((tr) => tr.mode === 'showing');
  }
  function applyCc(on) {
    const subs = subtitleTracks();
    if (!subs.length) return;
    if (on) {
      subs.forEach((tr, i) => { tr.mode = (i === 0) ? 'showing' : 'hidden'; });
    } else {
      subs.forEach((tr) => { tr.mode = 'hidden'; });
    }
  }

  if (!playlistId) {
    ['yrp-btn-prev', 'yrp-btn-next'].forEach((cls) => {
      const el = root.querySelector('.' + cls);
      if (el) el.style.display = 'none';
    });
  }

  function collectOrder() {
    const items = [];
    const right = document.querySelector('#upnext-block .rb-list');
    const under = document.querySelector('#panel-upnext .upnext-list');
    let anchors = [];
    if (right) anchors = right.querySelectorAll("a.rb-item[href*='/watch']");
    else if (under) anchors = under.querySelectorAll("a.rb-item[href*='/watch']");
    anchors.forEach((a) => {
      const href = a.getAttribute('href') || '';
      const m = href.match(/[?&]v=([^&]+)/);
      if (m && m[1]) items.push(decodeURIComponent(m[1]));
    });
    return items;
  }

  const order = playlistId ? collectOrder() : [];
  let curIndex = playlistId ? order.indexOf(currentVid) : -1;
  if (playlistId && curIndex < 0) curIndex = 0;

  const plKey = (s) => `pl:${playlistId}:${s}`;
  let orderMode = (playlistId ? (() => { const v = load(plKey('order'), 'direct'); return v === 'shuffle' ? 'shuffle' : 'direct'; })() : 'direct');
  let cycleOn  = (playlistId ? (() => { const v = load(plKey('cycle'), '0'); return v === true || v === '1'; })() : false);

  function pickRandomIndex(excludeIdx) {
    if (order.length <= 1) return excludeIdx;
    let tries = 0, rnd = excludeIdx;
    while (tries < 6 && rnd === excludeIdx) { rnd = Math.floor(Math.random() * order.length); tries++; }
    if (rnd === excludeIdx) rnd = (excludeIdx + 1) % order.length;
    return rnd;
  }
  function nextIndex() {
    if (!playlistId) return -1;
    if (orderMode === 'shuffle') return pickRandomIndex(curIndex);
    const ni = curIndex + 1;
    if (ni >= order.length) return cycleOn ? 0 : -1;
    return ni;
  }
  function prevIndex() {
    if (!playlistId) return -1;
    if (orderMode === 'shuffle') return pickRandomIndex(curIndex);
    const pi = curIndex - 1;
    if (pi < 0) return cycleOn ? (order.length - 1) : -1;
    return pi;
  }

  function gotoIndex(idx) {
    if (!playlistId) return;
    idx = Math.max(0, Math.min(order.length - 1, idx));
    const vidTarget = order[idx];
    if (!vidTarget) return;

    try {
      const m = load('resume', {});
      if (m && m[vidTarget]) { delete m[vidTarget]; save('resume', m); }
    } catch {}

    const nu = new URL(window.location.href);
    nu.searchParams.set('v', vidTarget);
    nu.searchParams.set('p', playlistId);
    window.location.href = nu.toString();
  }

  // Overlay controls - top left
  const bar = document.createElement('div');
  bar.className = 'yrp-ext-controls';
  Object.assign(bar.style, {
    position: 'absolute',
    left: '12px',
    top: '12px',
    display: 'flex',
    gap: '6px',
    alignItems: 'center',
    zIndex: '20',
    background: 'transparent',
    border: 'none',
    padding: '0',
    opacity: '0',
    transition: 'opacity 150ms ease',
    pointerEvents: 'auto'
  });

  function mkIconBtn(title) {
    const b = document.createElement('button');
    b.type = 'button';
    b.title = title || '';
    b.setAttribute('aria-label', title || '');
    Object.assign(b.style, {
      border: 'none',
      background: 'transparent',
      width: '28px',
      height: '28px',
      cursor: 'pointer',
      borderRadius: '14px',
      backgroundColor: 'var(--yrp-icon-color)',
      color: 'var(--yrp-icon-color)',
      textIndent: '-9999px',
      outline: 'none'
    });
    b.addEventListener('focus', () => { b.style.outline = '2px solid rgba(255,255,255,.6)'; b.style.outlineOffset = '2px'; });
    b.addEventListener('blur',  () => { b.style.outline = 'none'; });
    b.dataset.forceEmoji = '0';
    return b;
  }

  const btnPrev = mkIconBtn('Previous');
  const btnNext = mkIconBtn('Next');
  const btnShuffle = mkIconBtn('Shuffle');
  const btnCycle = mkIconBtn('Cycle playlist');
  const btnCC = mkIconBtn('Subtitles');

  try {
    const iconBase = `/static/players/${root.closest('.player-host')?.getAttribute('data-player') || 'standard'}/img/buttons`;
    [
      ['--icon-prev', 'prev.svg'],
      ['--icon-next', 'next.svg'],
      ['--icon-shuffle-on', 'shuffle-on.svg'],
      ['--icon-shuffle-off', 'shuffle-off.svg'],
      ['--icon-cycle-on', 'cycle-on.svg'],
      ['--icon-cycle-off', 'cycle-off.svg'],
      ['--icon-cc', 'cc.svg']
    ].forEach(([varName, file]) => {
      root.style.setProperty(varName, `url("${iconBase}/${file}")`);
    });
    root.style.setProperty('--yrp-icon-color', '#fff');
  } catch {}

  bar.appendChild(btnCC);
  const uiPrev = root.querySelector('.yrp-btn-prev');
  const uiNext = root.querySelector('.yrp-btn-next');
  if (playlistId) {
    if (!uiPrev) bar.appendChild(btnPrev);
    if (!uiNext) bar.appendChild(btnNext);
    bar.appendChild(btnShuffle);
    bar.appendChild(btnCycle);
  }

  async function refreshShuffleBtn() {
    if (!playlistId) return;
    btnShuffle.setAttribute('aria-pressed', orderMode === 'shuffle' ? 'true' : 'false');
    await applyIcon({ root, button: btnShuffle, varOn: '--icon-shuffle-on', varOff: '--icon-shuffle-off', isOn: orderMode === 'shuffle', fallbackEmoji: '🔀' });
    btnShuffle.style.opacity = (orderMode === 'shuffle') ? '1' : '0.7';
  }
  async function refreshCycleBtn() {
    if (!playlistId) return;
    btnCycle.setAttribute('aria-pressed', cycleOn ? 'true' : 'false');
    await applyIcon({ root, button: btnCycle, varOn: '--icon-cycle-on', varOff: '--icon-cycle-off', isOn: !!cycleOn, fallbackEmoji: '🔁' });
    btnCycle.style.opacity = cycleOn ? '1' : '0.7';
  }
  async function refreshPrevNext() {
    if (!playlistId) return;
    await applyIcon({ root, button: btnPrev, varOn: '--icon-prev', varOff: '--icon-prev', isOn: true, fallbackEmoji: '⏮' });
    await applyIcon({ root, button: btnNext, varOn: '--icon-next', varOff: '--icon-next', isOn: true, fallbackEmoji: '⏭' });
  }
  async function refreshCC() {
    const has = anySubtitleTracks();
    btnCC.disabled = !has;
    btnCC.style.opacity = has ? '1' : '0.4';
    await applyIcon({ root, button: btnCC, varOn: '--icon-cc', varOff: '--icon-cc', isOn: true, fallbackEmoji: 'CC' });
    if (!has) { btnCC.textContent = 'CC'; btnCC.style.textIndent = '0'; btnCC.style.backgroundColor = 'transparent'; }
  }

  btnPrev.addEventListener('click', function(){ const idx = prevIndex(); if (idx >= 0) gotoIndex(idx); });
  btnNext.addEventListener('click', function(){ const idx = nextIndex(); if (idx >= 0) gotoIndex(idx); });
  btnShuffle.addEventListener('click', function(){
    orderMode = (orderMode === 'shuffle') ? 'direct' : 'shuffle';
    if (playlistId) save(plKey('order'), orderMode);
    refreshShuffleBtn(); showBarTemp();
  });
  btnCycle.addEventListener('click', function(){
    cycleOn = !cycleOn;
    if (playlistId) save(plKey('cycle'), cycleOn ? '1' : '0');
    refreshCycleBtn(); showBarTemp();
  });
  btnCC.addEventListener('click', function(){
    if (!anySubtitleTracks()) return;
    const on = !isCcOn();
    applyCc(on);
    showBarTemp();
  });

  try {
    const wrap = root.querySelector('.yrp-video-wrap') || root;
    const pos = getComputedStyle(wrap).position;
    if (pos === 'static') wrap.style.position = 'relative';
    wrap.appendChild(bar);
  } catch { root.appendChild(bar); }

  await refreshPrevNext();
  await refreshShuffleBtn();
  await refreshCycleBtn();
  await refreshCC();

  let hideTimer = null;
  function showBar() {
    bar.style.opacity = '1';
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { bar.style.opacity = '0'; }, 1600);
  }
  function showBarTemp() { bar.style.opacity = '1'; if (hideTimer) clearTimeout(hideTimer); hideTimer = setTimeout(() => { bar.style.opacity = '0'; }, 1800); }

  ['mouseenter', 'mousemove', 'pointermove', 'touchstart'].forEach((ev) => {
    (root || document).addEventListener(ev, () => showBar(), { passive: true });
  });
  video.addEventListener('mouseleave', function(){ if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; } bar.style.opacity = '0'; });

  if (playlistId) {
    video.addEventListener('ended', function(){
      const idx = nextIndex();
      if (idx >= 0) gotoIndex(idx);
    });

    document.addEventListener('keydown', function(e){
      const tag = e.target && e.target.tagName ? e.target.tagName.toUpperCase() : '';
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
      const code = e.code || '';
      if (code === 'PageUp') { e.preventDefault(); const idx = prevIndex(); if (idx >= 0) gotoIndex(idx); }
      else if (code === 'PageDown') { e.preventDefault(); const idx2 = nextIndex(); if (idx2 >= 0) gotoIndex(idx2); }
    });
  }
}