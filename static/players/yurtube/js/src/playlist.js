import { load, save } from './storage.js';
import { applyIcon } from './icons.js';

export function attachPlaylist({ root, video, btnPrev, btnNext, leftGrp, vol, DEBUG }) {
  const url = new URL(window.location.href);
  const playlistId = url.searchParams.get('p');
  const currentVid = url.searchParams.get('v') || (root.getAttribute('data-video-id') || '');

  if (!playlistId) {
    if (btnPrev) btnPrev.style.display = 'none';
    if (btnNext) btnNext.style.display = 'none';
    const oldSh = root.querySelector('.yrp-shuffle');
    const oldCy = root.querySelector('.yrp-cycle');
    if (oldSh) oldSh.style.display = 'none';
    if (oldCy) oldCy.style.display = 'none';
    return;
  } else {
    if (btnPrev) btnPrev.style.display = '';
    if (btnNext) btnNext.style.display = '';
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

  const order = collectOrder();
  if (!order || order.length === 0) return;
  let curIndex = order.indexOf(currentVid);
  if (curIndex < 0) curIndex = 0;

  const plKey = (s) => `pl:${playlistId}:${s}`;
  let orderMode = (() => { const v = load(plKey('order'), 'direct'); return v === 'shuffle' ? 'shuffle' : 'direct'; })();
  let cycleOn  = (() => { const v = load(plKey('cycle'), '0'); return v === true || v === '1'; })();

  function saveOrderMode(mode) {
    orderMode = (mode === 'shuffle') ? 'shuffle' : 'direct';
    save(plKey('order'), orderMode);
    refreshShuffleBtn();
  }
  function saveCycle(flag) {
    cycleOn = !!flag;
    save(plKey('cycle'), cycleOn ? '1' : '0');
    refreshCycleBtn();
  }

  function pickRandomIndex(excludeIdx) {
    if (order.length <= 1) return excludeIdx;
    let tries = 0, rnd = excludeIdx;
    while (tries < 6 && rnd === excludeIdx) { rnd = Math.floor(Math.random() * order.length); tries++; }
    if (rnd === excludeIdx) rnd = (excludeIdx + 1) % order.length;
    return rnd;
  }
  function nextIndex() {
    if (orderMode === 'shuffle') return pickRandomIndex(curIndex);
    const ni = curIndex + 1;
    if (ni >= order.length) return cycleOn ? 0 : -1;
    return ni;
  }
  function prevIndex() {
    if (orderMode === 'shuffle') return pickRandomIndex(curIndex);
    const pi = curIndex - 1;
    if (pi < 0) return cycleOn ? (order.length - 1) : -1;
    return pi;
  }
  function gotoIndex(idx) {
    idx = Math.max(0, Math.min(order.length - 1, idx));
    const vidTarget = order[idx];
    if (!vidTarget) return;

    // Flush resume timestamp for target video in playlist
    try {
      const m = load('resume', {});
      if (m && m[vidTarget]) { delete m[vidTarget]; save('resume', m); }
    } catch {}

    const nu = new URL(window.location.href);
    nu.searchParams.set('v', vidTarget);
    nu.searchParams.set('p', playlistId);
    window.location.href = nu.toString();
  }

  root.addEventListener('yrp-prev', () => { const i = prevIndex(); if (i >= 0) gotoIndex(i); });
  root.addEventListener('yrp-next', () => { const i = nextIndex(); if (i >= 0) gotoIndex(i); });

  // Build buttons
  let btnShuffle = root.querySelector('.yrp-shuffle');
  let btnCycle   = root.querySelector('.yrp-cycle');

  if (!btnShuffle) {
    btnShuffle = document.createElement('button');
    btnShuffle.type = 'button';
    btnShuffle.className = 'yrp-btn yrp-shuffle';
    btnShuffle.title = 'Shuffle playlist';
    btnShuffle.setAttribute('aria-label', 'Shuffle playlist');
    Object.assign(btnShuffle.style, {
      border: 'none',
      width: 'var(--yrp-icon-button-width)',
      height: '28px',
      cursor: 'pointer',
      padding: '0',
      marginLeft: '6px',
      marginRight: '2px'
    });
  }
  if (!btnCycle) {
    btnCycle = document.createElement('button');
    btnCycle.type = 'button';
    btnCycle.className = 'yrp-btn yrp-cycle';
    btnCycle.title = 'Cycle playlist';
    btnCycle.setAttribute('aria-label', 'Cycle playlist');
    Object.assign(btnCycle.style, {
      border: 'none',
      width: 'var(--yrp-icon-button-width)',
      height: '28px',
      cursor: 'pointer',
      padding: '0',
      marginRight: '8px'
    });
  }

  // Remove forced emoji mode (we rely on svg masks now; emojis still auto-fallback)
  btnShuffle.dataset.forceEmoji = '0';
  btnCycle.dataset.forceEmoji = '0';

  async function refreshShuffleBtn() {
    btnShuffle.setAttribute('aria-pressed', orderMode === 'shuffle' ? 'true' : 'false');
    await applyIcon({ root, button: btnShuffle, varOn: '--icon-shuffle-on', varOff: '--icon-shuffle-off', isOn: orderMode === 'shuffle', fallbackEmoji: '🔀' });
    btnShuffle.style.opacity = (orderMode === 'shuffle') ? '1' : '0.55';
    btnShuffle.style.display = '';
  }
  async function refreshCycleBtn() {
    btnCycle.setAttribute('aria-pressed', cycleOn ? 'true' : 'false');
    await applyIcon({ root, button: btnCycle, varOn: '--icon-cycle-on', varOff: '--icon-cycle-off', isOn: !!cycleOn, fallbackEmoji: '🔁' });
    btnCycle.style.opacity = cycleOn ? '1' : '0.55';
    btnCycle.style.display = '';
  }

  refreshShuffleBtn();
  refreshCycleBtn();

  btnShuffle.addEventListener('click', () => { saveOrderMode(orderMode === 'shuffle' ? 'direct' : 'shuffle'); });
  btnCycle.addEventListener('click', () => { saveCycle(!cycleOn); });

  // Insert into .yrp-left: after ">>" and before volume
  try {
    const container = leftGrp || (btnNext && btnNext.parentNode) || root;
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
  } catch {}

  video.addEventListener('ended', function () {
    const i = nextIndex();
    if (i >= 0) gotoIndex(i);
  });

  document.addEventListener('keydown', function (e) {
    const t = e.target, tag = t && t.tagName ? t.tagName.toUpperCase() : '';
    if (t && (t.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA')) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const code = e.code || '';
    if (code === 'PageUp')   { e.preventDefault(); const i = prevIndex(); if (i >= 0) gotoIndex(i); }
    else if (code === 'PageDown') { e.preventDefault(); const j = nextIndex(); if (j >= 0) gotoIndex(j); }
  });
}