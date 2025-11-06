(function () {
  function parseJSONAttr(el, name, fallback) {
    var s = el.getAttribute(name);
    if (!s) return fallback;
    try { return JSON.parse(s); } catch (e) { return fallback; }
  }
  function detectPlayerName(){
    try{ var u=new URL(import.meta.url); var m=u.pathname.match(/\/static\/players\/([^\/]+)\//); if(m) return m[1]; }catch(e){}
    try{ var s=(document.currentScript&&document.currentScript.src)||""; var m2=s.match(/\/static\/players\/([^\/]+)\//); if(m2) return m2[1]; }catch(e2){}
    try{ var host=document.querySelector('.player-host[data-player]'); if(host){ var pn=String(host.getAttribute('data-player')||'').trim(); if(pn) return pn; } }catch(e3){}
    return "yurtube";
  }
  function tryPlay(video, onDebug) {
    var p=null;
    try { p = video.play(); } catch (e) { onDebug && onDebug("play threw", e); p=null; }
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
  // Fallback media
  var FALLBACK_SRC = "/static/img/fallback_video_notfound.webm";
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

  function mountOne(host, tpl, PLAYER_BASE){
    host.innerHTML = tpl;

    var root = host.querySelector(".yrp-container");
    var video = root.querySelector(".yrp-video");
    var source = video.querySelector("source");
    var centerBtn = root.querySelector(".yrp-center-play");
    var centerLogo = root.querySelector(".yrp-center-logo");

    var src = host.getAttribute("data-video-src") || "";
    var poster = host.getAttribute("data-poster-url") || "";
    var subs = parseJSONAttr(host,"data-subtitles",[]);
    var opts = parseJSONAttr(host,"data-options",{});

    var DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);
    function d(){ if(!DEBUG) return; try { console.debug.apply(console, ["[STD-EMBED]"].concat([].slice.call(arguments))); } catch(_){} }

    if (centerLogo) centerLogo.setAttribute("src", PLAYER_BASE + "/img/logo.png");

    if (source) source.setAttribute("src", src);
    if (poster) video.setAttribute("poster", poster);
    if (opts && opts.muted) video.setAttribute("muted", "");
    if (opts && opts.loop) video.setAttribute("loop", "");
    video.setAttribute("playsinline","");
    video.setAttribute("controls","");

    if (Array.isArray(subs)) {
      subs.forEach(function (t) {
        if (!t || !t.src) return;
        var tr = document.createElement("track");
        tr.setAttribute("kind","subtitles");
        if (t.srclang) tr.setAttribute("srclang", String(t.srclang));
        if (t.label) tr.setAttribute("label", String(t.label));
        tr.setAttribute("src", String(t.src));
        if (t.default) tr.setAttribute("default","");
        video.appendChild(tr);
      });
    }

    try { video.load(); d("video.load() called", { src: src }); } catch (e) { d("video.load() error", e); }

    // fallback handlers
    installFallbackGuards(video, source, d);

    function syncPlayingClass(){
      if (video.paused) root.classList.remove("playing");
      else root.classList.add("playing");
    }

    ["loadedmetadata","loadeddata","canplay","canplaythrough","play","pause","stalled","suspend","waiting","error","abort","emptied"].forEach(function(ev){
      video.addEventListener(ev, function(){ d("event", ev, { rs: video.readyState, paused: video.paused, muted: video.muted }); });
    });
    video.addEventListener("play", syncPlayingClass);
    video.addEventListener("pause", syncPlayingClass);

    var toggleLock=false;
    function safeToggle(){
      if (toggleLock) return;
      toggleLock = true;
      setTimeout(function(){ toggleLock=false; }, 180);
      if (video.paused) { tryPlay(video, d); } else { video.pause(); }
    }
    if (centerBtn) centerBtn.addEventListener("click", function(){ safeToggle(); });

    function onKey(e){
      var t=e.target; var tag=t && t.tagName ? t.tagName.toUpperCase() : "";
      if (t && (t.isContentEditable || tag==="INPUT" || tag==="TEXTAREA")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var k=(e.key||"").toLowerCase(), code=e.code||"";
      if (k==="j" || code==="ArrowLeft") {
        e.preventDefault(); video.currentTime = Math.max(0, (video.currentTime||0) - 5);
      } else if (k==="l" || code==="ArrowRight") {
        e.preventDefault(); var dUR = isFinite(video.duration) ? video.duration : 1e9; video.currentTime = Math.min((video.currentTime||0) + 5, dUR);
      } else if (k==="m") {
        e.preventDefault(); video.muted = !video.muted;
      } else if (k==="f") {
        e.preventDefault(); if (document.fullscreenElement) document.exitFullscreen().catch(function(){}); else root.requestFullscreen && root.requestFullscreen().catch(function(){});
      }
    }
    document.addEventListener("keydown", onKey);

    (function(){
      var want = !!(opts && opts.autoplay === true);
      d("autoplay check (embed)", { WANT: want, opt: opts });
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

    syncPlayingClass();
  }

  function initAll(){
    var PLAYER_NAME = detectPlayerName();
    var PLAYER_BASE = "/static/players/" + PLAYER_NAME;
    var hosts = document.querySelectorAll('.player-host[data-player="' + PLAYER_NAME + '"]');
    if (hosts.length===0) return;
    fetch(PLAYER_BASE + "/templates/player.html", { credentials: "same-origin" })
      .then(function(r){ return r.text(); })
      .then(function(html){ for (var i=0; i<hosts.length; i++) mountOne(hosts[i], html, PLAYER_BASE); })
      .catch(function(){});
  }

  if (document.readyState==="loading") document.addEventListener("DOMContentLoaded", initAll);
  else initAll();
})();