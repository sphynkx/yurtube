(function () {
  function fmtTime(sec) {
    if (!isFinite(sec) || sec < 0) sec = 0;
    sec = Math.floor(sec);
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    function pad(x) { return (x < 10 ? "0" : "") + x; }
    return (h > 0 ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s));
  }
  function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }
  function parseJSONAttr(el, name, fallback) {
    var s = el.getAttribute(name);
    if (!s) return fallback;
    try { return JSON.parse(s); } catch (e) { return fallback; }
  }
  function copyText(s) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(s).catch(function(){});
    } else {
      var ta = document.createElement("textarea");
      ta.value = s;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(ta);
    }
  }
  function cssPxToNum(s) {
    var v = parseFloat(String(s || "").trim());
    return isFinite(v) ? v : 0;
  }
  function detectPlayerName() {
    // 1) ESM: import.meta.url
    try {
      var u = new URL(import.meta.url);
      var m = u.pathname.match(/\/static\/players\/([^\/]+)\//);
      if (m) return m[1];
    } catch (e) {}
    // 2) classic: currentScript
    try {
      var s = (document.currentScript && document.currentScript.src) || "";
      var m2 = s.match(/\/static\/players\/([^\/]+)\//);
      if (m2) return m2[1];
    } catch (e2) {}
    // 3) from DOM host
    try {
      var host = document.querySelector('.player-host[data-player]');
      if (host) {
        var pn = String(host.getAttribute('data-player') || '').trim();
        if (pn) return pn;
      }
    } catch (e3) {}
    // 4) fallback
    return "yurtube";
  }

  // storage helpers
  var STORE = "yrp:";
  function canLS(){ try { localStorage.setItem("__t","1"); localStorage.removeItem("__t"); return true; } catch(e){ return false; } }
  function load(key, def){ if (!canLS()) return def; try{ var s=localStorage.getItem(STORE+key); return s? JSON.parse(s): def; }catch(_){ return def; } }
  function save(key, val){ if (!canLS()) return; try{ localStorage.setItem(STORE+key, JSON.stringify(val)); }catch(_){} }
  function throttle(fn, ms){ var t=0, pend=false, last; return function(){ last=arguments; var now=Date.now(); if(!t || now-t>=ms){ t=now; fn.apply(null,last); } else if(!pend){ pend=true; setTimeout(function(){ pend=false; t=Date.now(); fn.apply(null,last); }, ms-(now-t)); } }; }

  function mountOne(host, templateHTML, PLAYER_BASE) {
    host.innerHTML = templateHTML;

    var root = host.querySelector(".yrp-container");
    var video = root.querySelector(".yrp-video");
    var source = video.querySelector("source");

    var videoSrc = host.getAttribute("data-video-src") || "";
    var poster = host.getAttribute("data-poster-url") || "";
    var vid = host.getAttribute("data-video-id") || "";
    var subs = parseJSONAttr(host, "data-subtitles", []);
    var opts = parseJSONAttr(host, "data-options", {});

    // debug flag
    var DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);
    function d(){ if(!DEBUG) return; try { console.debug.apply(console, ["[YRP]"].concat([].slice.call(arguments))); } catch(_){} }

    if (source) source.setAttribute("src", videoSrc);
    if (poster) video.setAttribute("poster", poster);
    if (opts && opts.autoplay) video.setAttribute("autoplay", "");
    if (opts && opts.muted) video.setAttribute("muted", "");
    if (opts && opts.loop) video.setAttribute("loop", "");
    if (vid) root.setAttribute("data-video-id", vid);

    // iOS inline
    video.setAttribute("playsinline", "");

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

    // ensure load starts
    try { video.load(); d("video.load() called", {src: videoSrc}); } catch(e){ d("video.load() error", e); }

    // icon urls -> CSS vars on root (for mask)
    var iconBase = PLAYER_BASE + "/img/buttons";
    root.style.setProperty("--icon-play",    'url("' + iconBase + '/play.svg")');
    root.style.setProperty("--icon-pause",   'url("' + iconBase + '/pause.svg")');
    root.style.setProperty("--icon-prev",    'url("' + iconBase + '/prev.svg")');
    root.style.setProperty("--icon-next",    'url("' + iconBase + '/next.svg")');
    root.style.setProperty("--icon-vol",     'url("' + iconBase + '/volume.svg")');
    root.style.setProperty("--icon-mute",    'url("' + iconBase + '/mute.svg")');
    root.style.setProperty("--icon-cc",      'url("' + iconBase + '/cc.svg")');
    root.style.setProperty("--icon-mini",    'url("' + iconBase + '/mini.svg")');
    root.style.setProperty("--icon-settings",'url("' + iconBase + '/settings.svg")');
    root.style.setProperty("--icon-theater", 'url("' + iconBase + '/theater.svg")');
    root.style.setProperty("--icon-full",    'url("' + iconBase + '/full.svg")');
    root.style.setProperty("--icon-autoplay-on",  'url("' + iconBase + '/autoplay-on.svg")');
    root.style.setProperty("--icon-autoplay-off", 'url("' + iconBase + '/autoplay-off.svg")');

    root.classList.add("yrp-icons-ready");

    // set center logo dynamically
    var centerLogo = root.querySelector(".yrp-center-logo");
    if (centerLogo) centerLogo.setAttribute("src", PLAYER_BASE + "/img/logo.png");

    var startAt = 0;
    if (opts && typeof opts.start === "number" && opts.start > 0) {
      startAt = Math.max(0, opts.start);
    }

    wire(root, startAt, DEBUG);
  }

  function wire(root, startAt, DEBUG) {
    function d(){ if(!DEBUG) return; try { console.debug.apply(console, ["[YRP]"].concat([].slice.call(arguments))); } catch(_){} }

    var video = root.querySelector(".yrp-video");
    var centerPlay = root.querySelector(".yrp-center-play");
    var btnPlay = root.querySelector(".yrp-play");
    var btnPrev = root.querySelector(".yrp-prev");
    var btnNext = root.querySelector(".yrp-next");
    var btnVol = root.querySelector(".yrp-vol-btn");
    var vol = root.querySelector(".yrp-volume");
    var volSlider = root.querySelector(".yrp-vol-slider");
    var tCur = root.querySelector(".yrp-time-current");
    var tTot = root.querySelector(".yrp-time-total");
    var progress = root.querySelector(".yrp-progress");
    var rail = root.querySelector(".yrp-progress-rail");
    var buf = root.querySelector(".yrp-progress-buffer");
    var played = root.querySelector(".yrp-progress-played");
    var handle = root.querySelector(".yrp-progress-handle");
    var tooltip = root.querySelector(".yrp-progress-tooltip");
    var btnSettings = root.querySelector(".yrp-settings");
    var menu = root.querySelector(".yrp-menu");
    var btnTheater = root.querySelector(".yrp-theater");
    var btnFull = root.querySelector(".yrp-fullscreen");
    var btnPip = root.querySelector(".yrp-pip");
    var leftGrp = root.querySelector(".yrp-left");
    var rightGrp = root.querySelector(".yrp-right");
    var btnAutoplay = root.querySelector(".yrp-autoplay");

    var hideTimer = null;
    var seeking = false;
    var duration = 0;

    var pipInSystem = false;
    var pipWasPlayingOrig = false;
    var pipWasMutedOrig = false;
    var pipUserState = null;

    var userTouchedVolume = false;
    var autoMuteApplied = false;

    var autoplayOn = !!load("autoplay", false);
    function refreshAutoplayBtn(){
      if (!btnAutoplay) return;
      btnAutoplay.setAttribute("aria-pressed", autoplayOn ? "true" : "false");
      btnAutoplay.title = autoplayOn ? "Autoplay on (A)" : "Autoplay off (A)";
      btnAutoplay.textContent = autoplayOn ? "Autoplay on" : "Autoplay off";
      var img = autoplayOn ? "var(--icon-autoplay-on)" : "var(--icon-autoplay-off)";
      try {
        btnAutoplay.style.webkitMaskImage = img;
        btnAutoplay.style.maskImage = img;
      } catch(_){}
    }

    function showControls() {
      root.classList.remove("autohide");
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(function () { root.classList.add("autohide"); }, 2000);
    }
    function updateTimes() {
      try { duration = isFinite(video.duration) ? video.duration : 0; } catch (e) { duration = 0; }
      if (tTot) tTot.textContent = fmtTime(duration);
      if (tCur) tCur.textContent = fmtTime(video.currentTime || 0);
    }
    function updateProgress() {
      var d = duration || 0;
      var ct = video.currentTime || 0;
      var frac = d > 0 ? clamp(ct / d, 0, 1) : 0;
      if (played) played.style.width = (frac * 100).toFixed(3) + "%";
      if (handle) handle.style.left = (frac * 100).toFixed(3) + "%";
      var b = 0;
      if (video.buffered && video.buffered.length > 0) {
        try { b = video.buffered.end(video.buffered.length - 1); } catch (e) { b = 0; }
      }
      var bfrac = d > 0 ? clamp(b / d, 0, 1) : 0;
      if (buf) buf.style.width = (bfrac * 100).toFixed(3) + "%";
    }
    function playToggle() { if (video.paused) video.play().catch(function(){}); else video.pause(); }
    function setMutedToggle() { video.muted = !video.muted; refreshVolIcon(); }
    function refreshVolIcon() {
      var v = video.muted ? 0 : video.volume;
      var label = (video.muted || v === 0) ? "Mute" : "Vol";
      if (btnVol) {
        btnVol.textContent = label;
        btnVol.classList.toggle("icon-mute", (label === "Mute"));
        btnVol.classList.toggle("icon-vol",  (label !== "Mute"));
      }
    }
    function refreshPlayIcon() {
      if (!btnPlay) return;
      if (video.paused) {
        btnPlay.textContent = "Play";
        btnPlay.classList.add("icon-play");
        btnPlay.classList.remove("icon-pause");
      } else {
        btnPlay.textContent = "Pause";
        btnPlay.classList.add("icon-pause");
        btnPlay.classList.remove("icon-play");
      }
    }
    function seekByClientX(clientX) {
      var rect = rail.getBoundingClientRect();
      var x = Math.max(0, Math.min(clientX - rect.left, rect.width));
      var frac = rect.width > 0 ? x / rect.width : 0;
      var target = (duration || 0) * frac;
      video.currentTime = target;
    }
    function updateTooltip(clientX) {
      var tt = tooltip; if (!tt) return;
      var rect = rail.getBoundingClientRect();
      var x = Math.max(0, Math.min(clientX - rect.left, rect.width));
      var frac = rect.width > 0 ? x / rect.width : 0;
      var t = (duration || 0) * frac;
      tt.textContent = fmtTime(t);
      tt.style.left = (frac * 100).toFixed(3) + "%";
      tt.hidden = false;
    }
    function hideMenus() {
      if (menu) { menu.hidden = true; if (btnSettings) btnSettings.setAttribute("aria-expanded", "false"); }
      var ctx = root.querySelector(".yrp-context");
      if (ctx) ctx.hidden = true;
      root.classList.remove("vol-open");
    }

    function measureControlsMinWidth() {
      var lw = leftGrp ? leftGrp.getBoundingClientRect().width : 0;
      var rw = rightGrp ? rightGrp.getBoundingClientRect().width : 0;
      var pad = 24;
      var minW = Math.ceil(lw + rw + pad);
      if (!isFinite(minW) || minW <= 0) minW = 480;
      return minW;
    }

    function adjustWidthByAspect() {
      if (root.classList.contains("yrp-theater")) return;

      var csVideo = getComputedStyle(video);
      var maxH = cssPxToNum(csVideo.getPropertyValue("max-height")) || video.clientHeight || 0;
      var vw = video.videoWidth || 16;
      var vh = video.videoHeight || 9;
      var aspect = vh > 0 ? (vw / vh) : (16 / 9);
      var targetH = Math.min(maxH || video.clientHeight || 0, window.innerHeight * 0.9);
      if (!targetH || !isFinite(targetH)) return;

      var targetW = Math.floor(targetH * aspect);
      var maxPage = Math.floor(window.innerWidth * 0.95);

      var controlsMin = measureControlsMinWidth();
      var finalW = Math.max(controlsMin, Math.min(targetW, maxPage));

      root.style.maxWidth = finalW + "px";
      root.style.minWidth = controlsMin + "px";
      root.style.width = "100%";
    }

    // PERSIST: volume/mute
    (function(){
      var vs = load("volume", null);
      if (vs && typeof vs.v === "number") video.volume = clamp(vs.v, 0, 1);
      if (vs && typeof vs.m === "boolean") video.muted = !!vs.m;
      if (volSlider) volSlider.value = String(video.volume || 1);
      refreshVolIcon();

      video.addEventListener("volumechange", function(){
        if (autoMuteApplied && video.muted && !userTouchedVolume) return;
        save("volume", { v: clamp(video.volume||0, 0, 1), m: !!video.muted });
      });

      video.addEventListener("loadedmetadata", function once(){
        video.removeEventListener("loadedmetadata", once);
        if (userTouchedVolume) return;
        if (vs) {
          if (typeof vs.v === "number") video.volume = clamp(vs.v, 0, 1);
          if (typeof vs.m === "boolean") video.muted = !!vs.m;
          if (volSlider) volSlider.value = String(video.volume || 1);
          refreshVolIcon();
        }
      });
    })();

    // PERSIST: speed
    (function(){
      var sp = load("speed", null);
      if (typeof sp === "number" && sp > 0) video.playbackRate = sp;
      video.addEventListener("ratechange", function(){ save("speed", video.playbackRate); });
    })();

    // PERSIST: theater
    (function(){
      if (!btnTheater) return;
      var th = !!load("theater", false);
      if (th) root.classList.add("yrp-theater");
      btnTheater.addEventListener("click", function () {
        root.classList.toggle("yrp-theater");
        save("theater", root.classList.contains("yrp-theater"));
        var inTheater = root.classList.contains("yrp-theater");
        if (inTheater) {
          root.style.maxWidth = "";
          root.style.minWidth = "";
          root.style.width = "";
        } else {
          adjustWidthByAspect();
        }
        showControls();
      });
    })();

    // PERSIST: resume
    (function(){
      var vid = root.getAttribute("data-video-id") || "";
      if (!vid) return;
      var map = load("resume", {});
      var rec = map[vid];
      var now = Date.now();
      function applyResume(t){
        var d = isFinite(video.duration) ? video.duration : 0;
        if (d && t > 10 && t < d - 5) {
          try { video.currentTime = t; } catch(_){}
        }
      }
      if (rec && typeof rec.t === "number" && (now - (rec.ts||0)) < 180*24*3600*1000) {
        var setAt = Math.max(0, rec.t|0);
        if (isFinite(video.duration) && video.duration > 0) applyResume(setAt);
        else video.addEventListener("loadedmetadata", function once(){ video.removeEventListener("loadedmetadata", once); applyResume(setAt); });
      }
      var savePos = throttle(function(){
        var d = isFinite(video.duration) ? video.duration : 0;
        var cur = Math.max(0, Math.floor(video.currentTime||0));
        var m = load("resume", {});
        m[vid] = { t: cur, ts: Date.now(), d: d };
        var keys = Object.keys(m);
        if (keys.length > 200) {
          keys.sort(function(a,b){ return (m[a].ts||0) - (m[b].ts||0); });
          for (var i=0;i<keys.length-200;i++) delete m[keys[i]];
        }
        save("resume", m);
      }, 3000);
      video.addEventListener("timeupdate", function(){ if (!video.paused && !video.seeking) savePos(); });
      video.addEventListener("ended", function(){ var m = load("resume", {}); delete m[vid]; save("resume", m); });
    })();

    // Debug events
    ["loadedmetadata","loadeddata","canplay","canplaythrough","play","playing","pause","stalled","suspend","waiting","error","abort","emptied"].forEach(function(ev){
      video.addEventListener(ev, function(){ d("event:", ev, {rs: video.readyState, paused: video.paused, muted: video.muted}); });
    });

    // Autoplay (opt.autoplay === true has priority; otherwise saved button)
    (function(){
      var host = root.closest(".player-host") || root;
      var opt = parseJSONAttr(host, "data-options", null);

      function wantAutoplay(){
        if (opt && opt.autoplay === true) return true;
        return !!autoplayOn;
      }

      var WANT = wantAutoplay();
      d("autoplay check", {WANT:WANT, opt:opt, saved:autoplayOn});
      if (!WANT) return;

      function tryPlaySequence(reason){
        d("tryPlaySequence", {reason:reason, muted: video.muted, rs: video.readyState});
        var p = null;
        try { p = video.play(); } catch(e){ d("play() threw sync", e); p = null; }
        if (p && typeof p.then === "function") {
          p.then(function(){ d("play() resolved"); }).catch(function(err){
            d("play() rejected", {name: err && err.name, msg: err && err.message});
            if (!video.muted) {
              autoMuteApplied = true;
              video.muted = true;
              video.setAttribute("muted", "");
              if (volSlider) volSlider.value = String(video.volume || 1);
              refreshVolIcon();
              d("retry play() with mute");
              try { video.play().catch(function(e2){ d("retry rejected", {name:e2 && e2.name, msg:e2 && e2.message}); }); } catch(e2){ d("retry threw sync", e2); }
            }
          });
        } else {
          setTimeout(function(){
            if (video.paused) {
              autoMuteApplied = true;
              video.muted = true;
              video.setAttribute("muted", "");
              d("no-promise fallback: play muted");
              try { video.play().catch(function(e3){ d("no-promise fallback rejected", e3); }); } catch(e3){ d("no-promise fallback threw", e3); }
            }
          }, 0);
        }
      }

      var fired = false;
      function fireOnce(tag){ if (fired) return; fired = true; tryPlaySequence(tag); }
      if (video.readyState >= 1) fireOnce("readyState>=1");
      ["loadedmetadata","loadeddata","canplay","canplaythrough"].forEach(function(ev){
        var once=function(){ video.removeEventListener(ev, once); fireOnce(ev); };
        video.addEventListener(ev, once);
      });

      setTimeout(function(){
        if (video.paused) {
          d("watchdog: still paused, force muted play");
          autoMuteApplied = true;
          video.muted = true;
          video.setAttribute("muted","");
          try { video.play().catch(function(e){ d("watchdog play rejected", e); }); } catch(e){ d("watchdog play threw", e); }
        }
      }, 1200);
    })();

    video.addEventListener("loadedmetadata", function () {
      if (startAt && startAt > 0) {
        try { video.currentTime = Math.min(startAt, Math.floor(video.duration || startAt)); } catch (e) {}
      }
      setTimeout(adjustWidthByAspect, 0);
      updateTimes();
      updateProgress();
      refreshPlayIcon();
      refreshVolIcon();
      refreshAutoplayBtn();
    });
    window.addEventListener("resize", function(){ adjustWidthByAspect(); });

    video.addEventListener("timeupdate", function(){ updateTimes(); updateProgress(); });
    video.addEventListener("progress", function(){ updateProgress(); });
    video.addEventListener("play", function(){
      d("PLAY fired");
      root.classList.add("playing");
      showControls();
      refreshPlayIcon();
      if (pipInSystem) pipUserState = true;
    });
    video.addEventListener("pause", function(){
      d("PAUSE fired");
      root.classList.remove("playing");
      showControls();
      refreshPlayIcon();
      if (pipInSystem) pipUserState = false;
    });

    function enterVideoPiP() {
      var pipWasPlayingOrig = !video.paused;
      var pipWasMutedOrig = !!video.muted;
      var pipUserState = null;

      var needTempPlay = video.paused;
      var prevMuted = video.muted;

      var startPlayPromise = Promise.resolve();
      if (needTempPlay) {
        video.muted = true;
        startPlayPromise = video.play().catch(function(){});
      }

      return startPlayPromise.then(function () {
        return video.requestPictureInPicture();
      }).catch(function(){ }).then(function(){
        if (needTempPlay) {
          video.pause();
          video.muted = prevMuted;
        }
      });
    }

    function toggleMini() {
      try {
        if (document.pictureInPictureEnabled && video.requestPictureInPicture && !video.disablePictureInPicture) {
          if (document.pictureInPictureElement === video) {
            document.exitPictureInPicture().catch(function(){});
          } else {
            enterVideoPiP();
          }
          return;
        }
      } catch (ex) {}
    }

    if ("mediaSession" in navigator) {
      try {
        navigator.mediaSession.setActionHandler("play", function(){ video.play().catch(function(){}); });
        navigator.mediaSession.setActionHandler("pause", function(){ video.pause(); });
        navigator.mediaSession.setActionHandler("seekbackward", function(){ video.currentTime = clamp((video.currentTime||0) - 5, 0, duration||0); });
        navigator.mediaSession.setActionHandler("seekforward", function(){ video.currentTime = clamp((video.currentTime||0) + 5, 0, duration||0); });
        navigator.mediaSession.setActionHandler("stop", function(){ video.pause(); });
      } catch (e) {}
    }

    video.addEventListener("click", function(){ playToggle(); });

    root.addEventListener("mousemove", showControls, { passive: true });
    root.addEventListener("pointermove", showControls, { passive: true });
    root.addEventListener("mouseleave", function () {
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(function () { root.classList.add("autohide"); }, 600);
    });

    if (centerPlay) centerPlay.addEventListener("click", playToggle);
    if (btnPlay) btnPlay.addEventListener("click", playToggle);
    if (btnPrev) btnPrev.addEventListener("click", function(){ root.dispatchEvent(new CustomEvent("yrp-prev",{bubbles:true})); });
    if (btnNext) btnNext.addEventListener("click", function(){ root.dispatchEvent(new CustomEvent("yrp-next",{bubbles:true})); });

    if (btnVol) {
      btnVol.addEventListener("click", function(e){
        e.preventDefault();
        e.stopPropagation();
        userTouchedVolume = true;
        autoMuteApplied = false;
        setMutedToggle();
        showControls();
        root.classList.add("vol-open");
        setTimeout(function(){ root.classList.remove("vol-open"); }, 1200);
      });
    }
    if (volSlider) {
      volSlider.addEventListener("input", function(){
        userTouchedVolume = true;
        autoMuteApplied = false;
        var v = parseFloat(volSlider.value || "1");
        if (!isFinite(v)) v = 1;
        v = clamp(v, 0, 1);
        video.volume = v;
        if (v > 0) video.muted = false;
        refreshVolIcon();
      });
    }
    function onWheelVolume(e) {
      e.preventDefault();
      userTouchedVolume = true;
      autoMuteApplied = false;
      var step = 0.05;
      var v = video.muted ? 0 : video.volume;
      var nv = clamp(v + (e.deltaY < 0 ? step : -step), 0, 1);
      video.volume = nv;
      if (nv > 0) video.muted = false;
      if (volSlider) volSlider.value = String(nv);
      refreshVolIcon();
      showControls();
    }
    if (vol) vol.addEventListener("wheel", onWheelVolume, { passive: false });
    if (volSlider) volSlider.addEventListener("wheel", onWheelVolume, { passive: false });
    refreshVolIcon();

    if (progress) {
      progress.addEventListener("mousedown", function (e) {
        seeking = true;
        hideMenus();
        seekByClientX(e.clientX);
      });
      window.addEventListener("mousemove", function (e) { if (seeking) seekByClientX(e.clientX); });
      window.addEventListener("mouseup", function () { seeking = false; });
      progress.addEventListener("mousemove", function (e) { updateTooltip(e.clientX); });
      progress.addEventListener("mouseleave", function () { if (tooltip) tooltip.hidden = true; });
    }

    if (btnSettings && menu) {
      btnSettings.addEventListener("click", function (e) {
        var open = menu.hidden === true ? false : true;
        if (open) {
          menu.hidden = true;
          btnSettings.setAttribute("aria-expanded", "false");
        } else {
          hideMenus();
          menu.hidden = false;
          btnSettings.setAttribute("aria-expanded", "true");
        }
        e.stopPropagation();
        root.classList.add("vol-open");
        showControls();
      });
      menu.addEventListener("click", function (e) {
        var target = e.target;
        if (target && target.classList.contains("yrp-menu-item")) {
          var sp = parseFloat(target.getAttribute("data-speed") || "NaN");
          if (!isNaN(sp)) {
            video.playbackRate = sp;
            menu.hidden = true;
            btnSettings.setAttribute("aria-expanded", "false");
          }
        }
      });
      document.addEventListener("click", function (e) {
        if (!menu.hidden && !menu.contains(e.target) && e.target !== btnSettings) menu.hidden = true;
      });
    }

    if (btnFull) {
      btnFull.addEventListener("click", function () {
        if (document.fullscreenElement) {
          document.exitFullscreen().catch(function (){});
        } else {
          root.requestFullscreen && root.requestFullscreen().catch(function (){});
        }
      });
    }

    if (btnPip) {
      btnPip.addEventListener("click", function(e){
        e.preventDefault();
        e.stopPropagation();
        toggleMini();
      });
    }

    if (btnAutoplay) {
      btnAutoplay.addEventListener("click", function(e){
        e.preventDefault();
        e.stopPropagation();
        autoplayOn = !autoplayOn;
        save("autoplay", autoplayOn);
        refreshAutoplayBtn();
      });
    }

    root.addEventListener("contextmenu", function (e) {
      e.preventDefault();
      hideMenus();
      var ctx = root.querySelector(".yrp-context");
      if (!ctx) return;
      var rw = root.getBoundingClientRect();
      ctx.style.left = (e.clientX - rw.left) + "px";
      ctx.style.top = (e.clientY - rw.top) + "px";
      ctx.hidden = false;

      ctx.onclick = function (ev) {
        var act = ev.target && ev.target.getAttribute("data-action");
        var at = Math.floor(video.currentTime || 0);
        var vid = root.getAttribute("data-video-id") || "";
        if (act === "pip") {
          toggleMini();
        } else if (act === "copy-url") {
          var u = new URL(window.location.href);
          u.searchParams.delete("t");
          copyText(u.toString());
        } else if (act === "copy-url-time") {
          var u2 = new URL(window.location.href);
          u2.searchParams.set("t", String(at));
          copyText(u2.toString());
        } else if (act === "copy-embed") {
          var src = (window.location.origin || "") + "/embed?v=" + encodeURIComponent(vid || "");
          var iframe = "<iframe width=\"560\" height=\"315\" src=\"" + src + "\" frameborder=\"0\" allow=\"autoplay; encrypted-media\" allowfullscreen></iframe>";
          copyText(iframe);
        }
        ctx.hidden = true;
      };
      document.addEventListener("click", function (e2) {
        var ctx = root.querySelector(".yrp-context");
        if (ctx && !ctx.hidden && !ctx.contains(e2.target)) ctx.hidden = true;
      }, { once: true });
      document.addEventListener("keydown", function escClose(ev){
        if (ev.code === "Escape" || (ev.key||"").toLowerCase() === "escape") {
          var c = root.querySelector(".yrp-context");
          if (c && !c.hidden) c.hidden = true;
          document.removeEventListener("keydown", escClose);
        }
      });
    });

    function handleHotkey(e) {
      var t = e.target;
      var tag = t && t.tagName ? t.tagName.toUpperCase() : "";
      var editable = t && (t.isContentEditable || tag === "INPUT" || tag === "TEXTAREA");
      if (editable) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      var code = e.code;
      var key = (e.key || "").toLowerCase();

      if (code === "Space" || code === "Enter" || code === "NumpadEnter" ||
          code === "MediaPlayPause" ||
          code === "KeyK" || key === "k") {
        playToggle(); e.preventDefault(); return;
      }
      if (code === "ArrowLeft" || key === "arrowleft" || code === "KeyJ" || key === "j") {
        video.currentTime = clamp((video.currentTime || 0) - 5, 0, duration || 0); e.preventDefault(); return;
      }
      if (code === "ArrowRight" || key === "arrowright" || code === "KeyL" || key === "l") {
        video.currentTime = clamp((video.currentTime || 0) + 5, 0, duration || 0); e.preventDefault(); return;
      }
      if (code === "KeyM" || key === "m") { setMutedToggle(); e.preventDefault(); return; }
      if (code === "KeyF" || key === "f") { btnFull && btnFull.click(); e.preventDefault(); return; }
      if (code === "KeyT" || key === "t") { btnTheater && btnTheater.click(); e.preventDefault(); return; }
      if (code === "KeyI" || key === "i") { toggleMini(); e.preventDefault(); return; }
      if (code === "KeyA" || key === "a") { e.preventDefault(); if (btnAutoplay) btnAutoplay.click(); return; }
      if (code === "Escape" || key === "escape") { hideMenus(); return; }
    }
    document.addEventListener("keydown", handleHotkey);

    setTimeout(adjustWidthByAspect, 200);
  }

  function initAll() {
    var PLAYER_NAME = detectPlayerName();
    var PLAYER_BASE = "/static/players/" + PLAYER_NAME;
    var hosts = document.querySelectorAll('.player-host[data-player="' + PLAYER_NAME + '"]');
    if (hosts.length === 0) return;

    fetch(PLAYER_BASE + "/templates/player.html", { credentials: "same-origin" })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        for (var i = 0; i < hosts.length; i++) {
          mountOne(hosts[i], html, PLAYER_BASE);
        }
      })
      .catch(function () { });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();