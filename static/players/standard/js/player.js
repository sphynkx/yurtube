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
      if (m && m[1]) return m[1];
    } catch (e) {}
    try {
      var s = (document.currentScript && document.currentScript.src) || "";
      var m2 = s.match(/\/static\/players\/([^\/]+)\//);
      if (m2 && m2[1]) return m2[1];
    } catch (e2) {}
    try {
      var host = document.querySelector('.player-host[data-player]');
      if (host) {
        var pn = String(host.getAttribute('data-player') || '').trim();
        if (pn) return pn;
      }
    } catch (e3) {}
    return "standard";
  }

  function tryPlay(video, onDebug) {
    var p = null;
    try { p = video.play(); } catch (e) { onDebug && onDebug("play threw", e); p = null; }
    if (p && typeof p.then === "function") {
      p.then(function(){ onDebug && onDebug("play resolved"); })
       .catch(function(err){
         onDebug && onDebug("play rejected", { name: err && err.name, msg: err && err.message });
         if (!video.muted) {
           video.muted = true;
           video.setAttribute("muted", "");
           try { video.play(); } catch(_){}
         }
       });
    } else {
      setTimeout(function(){
        if (video.paused) {
          video.muted = true;
          video.setAttribute("muted", "");
          try { video.play(); } catch(_){}
        }
      }, 0);
    }
  }

  var FALLBACK_SRC = "/static/img/fallback_video_notfound.gif";
  function installFallbackGuards(video, sourceEl, onDebug) {
    var applied = false;
    var watchdog = null;
    function applyFallback(reason){
      if (applied) return;
      applied = true;
      onDebug && onDebug("fallback: applying", reason);
      try {
        if (sourceEl) sourceEl.setAttribute("src", FALLBACK_SRC);
        else video.src = FALLBACK_SRC;
        video.load();
      } catch(e) {}
    }
    function clearWatchdog(){ if (watchdog) { clearTimeout(watchdog); watchdog = null; } }
    video.addEventListener("loadstart", function(){
      clearWatchdog();
      watchdog = setTimeout(function(){
        if (!applied && video.readyState < 1) applyFallback("watchdog-timeout");
      }, 4000);
    });
    ["loadeddata","canplay","canplaythrough","play","playing"].forEach(function(ev){
      video.addEventListener(ev, clearWatchdog);
    });
    video.addEventListener("error", function(){
      if (!applied) applyFallback("error-event");
    });
    setTimeout(function(){
      var src = sourceEl ? (sourceEl.getAttribute("src")||"") : (video.currentSrc||video.src||"");
      if (!applied && !src) applyFallback("empty-src");
    }, 0);
  }

  // --- Sprites (VTT) helpers ---
  function parseTimestamp(ts){
    var m = String(ts||"").match(/^(\d{2}):(\d{2}):(\d{2}\.\d{3})$/);
    if(!m) return 0;
    var h = parseInt(m[1],10), mm = parseInt(m[2],10), ss = parseFloat(m[3]);
    return h*3600 + mm*60 + ss;
  }

  function buildAbsoluteSpriteUrl(vttUrl, rel){
    if(!rel) return "";
    if(/^https?:\/\//i.test(rel) || rel.startsWith("/")) return rel;
    try {
      var u = new URL(vttUrl, window.location.origin);
      var baseDir = u.pathname.replace(/\/sprites\.vtt$/, "");
      return baseDir + "/" + rel.replace(/^\/+/,"");
    } catch(e){
      return rel;
    }
  }

  function mountOne(host, tpl, PLAYER_BASE) {
    host.innerHTML = tpl;

    var root = host.querySelector(".yrp-container");
    var video = root.querySelector(".yrp-video");
    var source = video.querySelector("source");
    var centerBtn = root.querySelector(".yrp-center-play");
    var centerLogo = root.querySelector(".yrp-center-logo");

    var src = host.getAttribute("data-video-src") || "";
    var poster = host.getAttribute("data-poster-url") || "";
    var subs = parseJSONAttr(host, "data-subtitles", []);
    var opts = parseJSONAttr(host, "data-options", {});
    var spritesVtt = host.getAttribute("data-sprites-vtt") || "";

    var DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);
    function d(){ if (!DEBUG) return; try { console.debug.apply(console, ["[STD]"].concat([].slice.call(arguments))); } catch(_){} }

    if (centerLogo) centerLogo.setAttribute("src", PLAYER_BASE + "/img/logo.png");

    if (source) source.setAttribute("src", src);
    if (poster) video.setAttribute("poster", poster);
    if (opts && opts.muted) video.setAttribute("muted", "");
    if (opts && opts.loop) video.setAttribute("loop", "");
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

    try { video.load(); d("video.load() called", { src: src }); } catch (e) { d("video.load() error", e); }

    installFallbackGuards(video, source, d);

    function syncPlayingClass() {
      if (video.paused) root.classList.remove("playing");
      else root.classList.add("playing");
    }

    ["loadedmetadata","loadeddata","canplay","canplaythrough","play","playing","pause","stalled","suspend","waiting","error","abort","emptied"].forEach(function(ev){
      video.addEventListener(ev, function(){ d("event", ev, { rs: video.readyState, paused: video.paused, muted: video.muted }); });
    });
    video.addEventListener("play", syncPlayingClass);
    video.addEventListener("pause", syncPlayingClass);

    var toggleLock = false;
    function safeToggle() {
      if (toggleLock) return;
      toggleLock = true;
      setTimeout(function(){ toggleLock = false; }, 180);
      if (video.paused) { tryPlay(video, d); } else { video.pause(); }
    }

    if (centerBtn) {
      centerBtn.addEventListener("click", function(){ safeToggle(); });
    }

    function onKey(e){
      var t = e.target; var tag = t && t.tagName ? t.tagName.toUpperCase() : "";
      if (t && (t.isContentEditable || tag === "INPUT" || tag === "TEXTAREA")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var k = (e.key || "").toLowerCase();
      var code = e.code || "";
      if (k === "j" || code === "ArrowLeft") {
        e.preventDefault();
        video.currentTime = Math.max(0, (video.currentTime || 0) - 5);
      } else if (k === "l" || code === "ArrowRight") {
        e.preventDefault();
        var dUR = isFinite(video.duration) ? video.duration : 1e9;
        video.currentTime = Math.min((video.currentTime || 0) + 5, dUR);
      } else if (k === "m") {
        e.preventDefault(); video.muted = !video.muted;
      } else if (k === "f") {
        e.preventDefault();
        if (document.fullscreenElement) document.exitFullscreen().catch(function(){});
        else root.requestFullscreen && root.requestFullscreen().catch(function(){});
      }
    }
    document.addEventListener("keydown", onKey);

    (function(){
      var want = !!(opts && opts.autoplay === true);
      d("autoplay check", { WANT: want, opt: opts });
      if (!want) return;
      function attempt(tag){ d("autoplay attempt", tag); tryPlay(video, d); }
      if (video.readyState >= 1) attempt("readyState>=1");
      var once = function(){ video.removeEventListener("canplay", once); attempt("canplay"); };
      video.addEventListener("canplay", once);
      setTimeout(function(){ if (video.paused) attempt("watchdog"); }, 1200);
    })();

    (function(){
      var start = 0;
      if (opts && typeof opts.start === "number" && opts.start > 0) start = Math.max(0, opts.start);
      if (!start) return;
      var apply = function(){ try { video.currentTime = Math.min(start, Math.floor(video.duration || start)); } catch(_){} };
      if (isFinite(video.duration) && video.duration > 0) apply();
      else video.addEventListener("loadedmetadata", function once(){ video.removeEventListener("loadedmetadata", once); apply(); });
    })();

    // --- Sprites preview integration ---
    var spriteCues = [];
    var spritesLoaded = false;
    var spritesLoadError = false;
    var spritePop = null;
    var spriteDurationApprox = 0;

    // SPRITES POSITION UPDATED constants
    var CONTROL_ZONE_PX = 85;      // height of bottom edge (under controls)
    var OFFSET_ABOVE    = 12;      // padding above bottom edge of video
    var FALLBACK_W = 160;
    var FALLBACK_H = 90;

    function ensureSpritePop(){
      if (spritePop) return spritePop;
      spritePop = document.createElement("div");
      spritePop.className = "std-sprite-pop";
      spritePop.style.position = "absolute";
      spritePop.style.pointerEvents = "none";
      spritePop.style.display = "none";
      spritePop.style.zIndex = "15";
      spritePop.style.border = "1px solid #333";
      spritePop.style.background = "#000";
      spritePop.style.overflow = "hidden";
      spritePop.style.boxShadow = "0 4px 12px rgba(0,0,0,.4)";
      spritePop.style.borderRadius = "4px";
      var container = root;
      if (getComputedStyle(container).position === "static") {
        container.style.position = "relative";
      }
      container.appendChild(spritePop);
      return spritePop;
    }

    function loadSpritesVTT(){
      if (!spritesVtt || spritesLoaded || spritesLoadError) return;
      fetch(spritesVtt, { credentials: "same-origin" })
        .then(function(r){ return r.text(); })
        .then(function(text){
          var lines = text.split(/\r?\n/);
          for (var i=0;i<lines.length;i++){
            var line = lines[i].trim();
            if(!line) continue;
            if(line.indexOf("-->") >= 0){
              var parts = line.split("-->").map(function(s){ return s.trim(); });
              if (parts.length < 2) continue;
              var start = parseTimestamp(parts[0]);
              var end = parseTimestamp(parts[1]);
              var ref = (lines[i+1]||"").trim();
              var spriteRel="", x=0,y=0,w=0,h=0;
              var hashIdx = ref.indexOf("#xywh=");
              if (hashIdx > 0) {
                spriteRel = ref.substring(0, hashIdx);
                var xywh = ref.substring(hashIdx+6).split(",");
                if (xywh.length === 4) {
                  x = parseInt(xywh[0],10);
                  y = parseInt(xywh[1],10);
                  w = parseInt(xywh[2],10);
                  h = parseInt(xywh[3],10);
                }
              }
              var absUrl = buildAbsoluteSpriteUrl(spritesVtt, spriteRel);
              spriteCues.push({start:start,end:end,spriteUrl:absUrl,x:x,y:y,w:w,h:h});
              if(end > spriteDurationApprox) spriteDurationApprox = end;
              i++;
            }
          }
          spritesLoaded = true;
          d("sprites VTT loaded (standard)", {cues: spriteCues.length, durationApprox: spriteDurationApprox});
        })
        .catch(function(err){
          spritesLoadError = true;
          d("sprites VTT load failed (standard)", err);
        });
    }

    function showSpritePreview(evt){
      if (!spritesVtt || !spriteCues.length) return;
      var rectVideo = video.getBoundingClientRect();
      var rectRoot = root.getBoundingClientRect();

      // Show sprites only if cursor in bottom zone
      if (evt.clientY < rectVideo.bottom - CONTROL_ZONE_PX) {
        if (spritePop) spritePop.style.display = "none";
        return;
      }

      var pop = ensureSpritePop();
      var clientX = evt.clientX;
      var xInside = Math.max(rectVideo.left, Math.min(clientX, rectVideo.right));
      var frac = (rectVideo.width > 0) ? (xInside - rectVideo.left) / rectVideo.width : 0;
      frac = Math.max(0, Math.min(1, frac));
      var tRef = (isFinite(video.duration) && video.duration > 0) ? video.duration : spriteDurationApprox;
      var t = tRef * frac;
      var cue = null;
      for (var i=0;i<spriteCues.length;i++){
        var c = spriteCues[i];
        if (t >= c.start && t < c.end) { cue = c; break; }
      }
      if (!cue || !cue.spriteUrl) {
        pop.style.display = "none";
        return;
      }
      var cw = cue.w > 0 ? cue.w : FALLBACK_W;
      var ch = cue.h > 0 ? cue.h : FALLBACK_H;

      while (pop.firstChild) pop.removeChild(pop.firstChild);
      var img = document.createElement("img");
      img.src = cue.spriteUrl;
      img.style.position = "absolute";
      img.style.left = (-cue.x) + "px";
      img.style.top = (-cue.y) + "px";
      pop.appendChild(img);

      pop.style.display = "block";
      pop.style.width = cw + "px";
      pop.style.height = ch + "px";

      var offsetX = xInside - rectRoot.left - cw/2;
      offsetX = Math.max(rectVideo.left - rectRoot.left, Math.min(offsetX, rectVideo.right - rectRoot.left - cw));

      var bottomLine = rectVideo.bottom - rectRoot.top;
      var topPos = bottomLine - ch - OFFSET_ABOVE - (CONTROL_ZONE_PX * 0.35);

      if (topPos < 0) topPos = 0;
      pop.style.left = offsetX + "px";
      pop.style.top  = topPos + "px";
    }

    if (spritesVtt) {
      video.addEventListener("loadedmetadata", function(){
        loadSpritesVTT();
      });
      setTimeout(function(){ if(!spritesLoaded && !spritesLoadError) loadSpritesVTT(); }, 2500);

      video.addEventListener("mousemove", function(e){
        if (spritesLoaded) showSpritePreview(e);
      });
      video.addEventListener("mouseleave", function(){
        if (spritePop) spritePop.style.display = "none";
      });
    }

    syncPlayingClass();
  }

  function initAll() {
    var PLAYER_NAME = detectPlayerName();
    window.__YRP_STD_NAME = PLAYER_NAME;
    var PLAYER_BASE = "/static/players/" + PLAYER_NAME;
    var hosts = document.querySelectorAll('.player-host[data-player="' + PLAYER_NAME + '"]');
    if (hosts.length === 0) return;

    fetch(PLAYER_BASE + "/templates/player.html", { credentials: "same-origin" })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        for (var i = 0; i < hosts.length; i++) mountOne(hosts[i], html, PLAYER_BASE);
      })
      .catch(function(){});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initAll);
  else initAll();
})();