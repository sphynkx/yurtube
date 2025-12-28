export const FALLBACK_SRC = '/static/img/fallback_video_notfound.gif';

export function installFallbackGuards(video, sourceEl, onDebug) {
  let applied = false;
  let watchdog = null;

  function applyFallback(reason) {
    if (applied) return;
    applied = true;
    onDebug && onDebug('fallback: applying', reason);
    try {
      if (sourceEl) sourceEl.setAttribute('src', FALLBACK_SRC);
      else video.src = FALLBACK_SRC;
      video.load();
    } catch {}
  }

  function clearWatchdog() { if (watchdog) { clearTimeout(watchdog); watchdog = null; } }

  video.addEventListener('loadstart', function () {
    clearWatchdog();
    watchdog = setTimeout(function () {
      if (!applied && video.readyState < 1) applyFallback('watchdog-timeout');
    }, 4000);
  });

  ['loadeddata', 'canplay', 'canplaythrough', 'play', 'playing'].forEach(function (ev) {
    video.addEventListener(ev, clearWatchdog);
  });

  video.addEventListener('error', function () {
    if (!applied) applyFallback('error-event');
  });

  setTimeout(function () {
    const src = sourceEl ? (sourceEl.getAttribute('src') || '') : (video.currentSrc || video.src || '');
    if (!applied && !src) applyFallback('empty-src');
  }, 0);
}