(function () {
  function parseJSONAttr(el, name, fallback) {
    var s = el.getAttribute(name);
    if (!s) return fallback;
    try { return JSON.parse(s); } catch (e) { return fallback; }
  }
  function detectPlayerName() {
    try {
      var u = new URL(import.meta.url);
      var m = u.pathname.match(/\/static\/players\/([^\/]+)\//);
      if (m) return m[1];
    } catch (e) {}
    try {
      var s = (document.currentScript && document.currentScript.src) || "";
      var m2 = s.match(/\/static\/players\/([^\/]+)\//);
      if (m2) return m2[1];
    } catch (e2) {}
    try {
      var host = document.querySelector('.player-host[data-player]');
      if (host) {
        var pn = String(host.getAttribute('data-player') || '').trim();
        if (pn) return pn;
      }
    } catch (e3) {}
    return "yurtube";
  }

  var FALLBACK_SRC = "/static/img/fallback_video_notfound.gif";
  function installFallbackGuards(video, sourceEl, onDebug) {
    var applied = false;
    var watchdog = null;
    function applyFallback(reason) {
      if (applied) return;
      applied = true;
      onDebug && onDebug("fallback: applying", reason);
      try {
        if (sourceEl) sourceEl.setAttribute("src", FALLBACK_SRC);
        else video.src = FALLBACK_SRC;
        video.load();
      } catch (e) {}
    }
    function clearWatchdog() { if (watchdog) { clearTimeout(watchdog); watchdog = null; } }
    video.addEventListener("loadstart", function () {
      clearWatchdog();
      watchdog = setTimeout(function () {
        if (!applied && video.readyState < 1) applyFallback("watchdog-timeout");
      }, 4000);
    });
    ["loadeddata", "canplay", "canplaythrough", "play", "playing"].forEach(function (ev) {
      video.addEventListener(ev, clearWatchdog);
    });
    video.addEventListener("error", function () {
      if (!applied) applyFallback("error-event");
    });
    setTimeout(function () {
      var src = sourceEl ? (sourceEl.getAttribute("src") || "") : (video.currentSrc || video.src || "");
      if (!applied && !src) applyFallback("empty-src");
    }, 0);
  }

  function mountOne(host, tpl, PLAYER_BASE) {
    host.innerHTML = tpl;

    var root = host.querySelector(".yrp-container");
    var wrap = root.querySelector(".yrp-video-wrap");
    var video = root.querySelector(".yrp-video");
    var source = video.querySelector("source");

    var src = host.getAttribute("data-video-src") || "";
    var poster = host.getAttribute("data-poster-url") || "";
    var vid = host.getAttribute("data-video-id") || "";
    var subs = parseJSONAttr(host, "data-subtitles", []);
    var opts = parseJSONAttr(host, "data-options", {});
    var spritesVtt = host.getAttribute("data-sprites-vtt") || "";
    // CAPTIONS
    var captionVtt = host.getAttribute("data-caption-vtt") || "";
    var captionLang = host.getAttribute("data-caption-lang") || "";

    var DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);
    function d() { if (!DEBUG) return; try { console.debug.apply(console, ["[YRP-EMBED]"].concat([].slice.call(arguments))); } catch (_) { } }

    root.classList.add("yrp-embed");
    root.setAttribute("tabindex", "0");

    if (source) source.setAttribute("src", src);
    if (poster) video.setAttribute("poster", poster);
    if (opts && opts.autoplay) video.setAttribute("autoplay", "");
    if (opts && opts.muted) video.setAttribute("muted", "");
    if (opts && opts.loop) video.setAttribute("loop", "");
    if (vid) root.setAttribute("data-video-id", vid);

    video.setAttribute("playsinline", "");
    video.setAttribute("controls", "");

    if (Array.isArray(subs)) {
      subs.forEach(function (t) {
        if (!t || !t.src) return;
        var tr = document.createElement("track");
        tr.setAttribute("kind", "subtitles");
        if (t.srclang) tr.setAttribute("srclang", String(t.srclang));
        if (t.label) tr.setAttribute("label", String(t.label));
        tr.setAttribute("src", String(t.src));
        if (t.default) tr.setAttribute("default", "");
        video.appendChild(tr);
      });
    }

    // CAPTIONS append if provided
    if (captionVtt) {
      try {
        var ctr = document.createElement("track");
        ctr.setAttribute("kind", "subtitles");
        ctr.setAttribute("src", captionVtt);
        ctr.setAttribute("srclang", captionLang || "auto");
        ctr.setAttribute("label", captionLang || "Original");
        ctr.setAttribute("default", "");
        video.appendChild(ctr);
        d("caption track appended", { captionVtt: captionVtt, captionLang: captionLang });
      } catch (e) {
        d("caption track append failed", e);
      }
    }

    try { video.load(); d("video.load() called", { src: src }); } catch (e) { d("video.load() error", e); }
    installFallbackGuards(video, source, d);

    // Simple layout sizing for embed
    function layoutFillViewport() {
      try {
        var H = window.innerHeight || document.documentElement.clientHeight || root.clientHeight || 0;
        if (H <= 0) return;
        wrap.style.height = H + "px";
        video.style.height = "100%";
        video.style.width = "100%";
        video.style.objectFit = "contain";
      } catch (_) { }
    }
    window.addEventListener("resize", layoutFillViewport);
    window.addEventListener("orientationchange", layoutFillViewport);
    layoutFillViewport();
    setTimeout(layoutFillViewport, 0);
    setTimeout(layoutFillViewport, 100);

    var toggleLock = false;
    function safeToggle() {
      if (toggleLock) return;
      toggleLock = true;
      setTimeout(function () { toggleLock = false; }, 180);
      if (video.paused) {
        var p = null;
        try { p = video.play(); } catch (e) { p = null; }
        if (p && p.then) p.catch(function(){});
      } else {
        video.pause();
      }
    }

    var centerBtn = root.querySelector(".yrp-center-play");
    if (centerBtn) centerBtn.addEventListener("click", safeToggle);
    video.addEventListener("click", safeToggle);

    // Hotkeys (minimal)
    function onKey(e) {
      var t = e.target; var tag = t && t.tagName ? t.tagName.toUpperCase() : "";
      if (t && (t.isContentEditable || tag === "INPUT" || tag === "TEXTAREA")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var k = (e.key || "").toLowerCase(), code = e.code || "";
      if (k === " " || k === "k" || code === "KeyK" || code === "Space" || code === "Enter") {
        safeToggle(); e.preventDefault(); return;
      }
      if (k === "j" || code === "ArrowLeft") {
        video.currentTime = Math.max(0, (video.currentTime || 0) - 5); e.preventDefault(); return;
      }
      if (k === "l" || code === "ArrowRight") {
        var dUR = isFinite(video.duration) ? video.duration : 1e9;
        video.currentTime = Math.min((video.currentTime || 0) + 5, dUR); e.preventDefault(); return;
      }
      if (k === "m" || code === "KeyM") { video.muted = !video.muted; e.preventDefault(); return; }
      if (k === "f" || code === "KeyF") {
        if (document.fullscreenElement) document.exitFullscreen().catch(function(){});
        else root.requestFullscreen && root.requestFullscreen().catch(function(){});
        e.preventDefault(); return;
      }
    }
    document.addEventListener("keydown", onKey);

    // Autoplay (embed conditions)
    (function(){
      var WANT = !!(opts && opts.autoplay === true);
      if (!WANT) return;
      function attempt(tag){
        var p=null;
        try { p = video.play(); } catch(e){ p = null; }
        if (p && p.then) {
          p.catch(function(err){
            if (!video.muted) {
              video.muted = true;
              video.setAttribute("muted","");
              try { video.play().catch(function(){}) } catch(_){}
            }
          });
        } else {
          setTimeout(function(){
            if (video.paused) {
              video.muted = true;
              video.setAttribute("muted","");
              try { video.play().catch(function(){}) } catch(_){}
            }
          }, 0);
        }
      }
      var fired=false;
      function fireOnce(tag){ if(fired) return; fired=true; attempt(tag); }
      if (video.readyState >= 1) fireOnce("readyState>=1");
      ["loadedmetadata","loadeddata","canplay","canplaythrough"].forEach(function(ev){
        var once=function(){ video.removeEventListener(ev, once); fireOnce(ev); };
        video.addEventListener(ev, once);
      });
      setTimeout(function(){ if (video.paused) attempt("watchdog"); }, 1200);
    })();
  }

  function initAll() {
    var PLAYER_NAME = detectPlayerName();
    var PLAYER_BASE = "/static/players/" + PLAYER_NAME;
    var hosts = document.querySelectorAll('.player-host[data-player="' + PLAYER_NAME + '"]');
    if (hosts.length === 0) return;
    fetch(PLAYER_BASE + "/templates/player.html", { credentials: "same-origin" })
      .then(function (r) { return r.text(); })
      .then(function (html) { for (var i = 0; i < hosts.length; i++) mountOne(hosts[i], html, PLAYER_BASE); })
      .catch(function () { });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initAll);
  else initAll();
})();