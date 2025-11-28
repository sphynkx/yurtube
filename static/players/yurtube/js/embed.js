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
  function throttle(fn, ms) {
    var t = 0, pend = false;
    return function () {
      var now = Date.now();
      if (!t || now - t >= ms) { t = now; fn(); }
      else if (!pend) { pend = true; setTimeout(function () { pend = false; t = Date.now(); fn(); }, ms - (now - t)); }
    };
  }
  function copyText(s) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(s).catch(function(){});
    } else {
      var ta = document.createElement("textarea");
      ta.value = s;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(ta);
    }
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
    var controls = root.querySelector(".yrp-controls");
    var source = video.querySelector("source");
    var ap = root.querySelector(".yrp-autoplay"); if (ap) ap.style.display = "none";

    var opts = parseJSONAttr(host, "data-options", {});
    var DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);
    function d() { if (!DEBUG) return; try { console.debug.apply(console, ["[YRP-EMBED]"].concat([].slice.call(arguments))); } catch (_) {} }

    root.classList.add("yrp-embed");
    root.setAttribute("tabindex", "0");

    var videoSrc = host.getAttribute("data-video-src") || "";
    var poster = host.getAttribute("data-poster-url") || "";
    var vid = host.getAttribute("data-video-id") || "";
    var subs = parseJSONAttr(host, "data-subtitles", []);
    var spritesVtt = host.getAttribute("data-sprites-vtt") || "";
    // CAPTIONS START
    var captionVtt = host.getAttribute("data-caption-vtt") || "";
    var captionLang = host.getAttribute("data-caption-lang") || "";
    // CAPTIONS END

    if (source) source.setAttribute("src", videoSrc);
    if (poster) video.setAttribute("poster", poster);
    if (opts && opts.autoplay) video.setAttribute("autoplay", "");
    if (opts && opts.muted) video.setAttribute("muted", "");
    if (opts && opts.loop) video.setAttribute("loop", "");
    if (vid) root.setAttribute("data-video-id", vid);
    if (spritesVtt) root.setAttribute("data-sprites-vtt", spritesVtt);

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

    // CAPTIONS START
    var ccBtn = null;
    if (captionVtt) {
      try {
        var ctr = document.createElement("track");
        ctr.setAttribute("kind", "subtitles");
        ctr.setAttribute("src", captionVtt);
        ctr.setAttribute("srclang", captionLang || "auto");
        ctr.setAttribute("label", captionLang || "Original");
        ctr.setAttribute("default", "");
        video.appendChild(ctr);
        ccBtn = root.querySelector(".yrp-subtitles");
        if (ccBtn) ccBtn.disabled = false;
        var ensureShow = function(){
          try {
            if (!video.textTracks) return;
            for (var i=0;i<video.textTracks.length;i++){
              var tt = video.textTracks[i];
              if (tt.kind === "subtitles" || tt.kind === "captions") {
                tt.mode = "showing";
              }
            }
          } catch(_){}
        };
        setTimeout(ensureShow, 0);
        ctr.addEventListener("load", ensureShow);
        video.addEventListener("loadedmetadata", function once(){
          video.removeEventListener("loadedmetadata", once);
          ensureShow();
        });
      } catch(e){
        d("caption track append failed", e);
      }
    }
    // CAPTIONS END

    try { video.load(); d("video.load() called", { src: videoSrc }); } catch (e) { d("video.load() error", e); }
    installFallbackGuards(video, source, d);

    var iconBase = PLAYER_BASE + "/img/buttons";
    root.style.setProperty("--icon-play", 'url("' + iconBase + '/play.svg")');
    root.style.setProperty("--icon-pause", 'url("' + iconBase + '/pause.svg")');
    root.style.setProperty("--icon-prev", 'url("' + iconBase + '/prev.svg")');
    root.style.setProperty("--icon-next", 'url("' + iconBase + '/next.svg")');
    root.style.setProperty("--icon-vol", 'url("' + iconBase + '/volume.svg")');
    root.style.setProperty("--icon-mute", 'url("' + iconBase + '/mute.svg")');
    root.style.setProperty("--icon-cc", 'url("' + iconBase + '/cc.svg")');
    root.style.setProperty("--icon-mini", 'url("' + iconBase + '/mini.svg")');
    root.style.setProperty("--icon-settings", 'url("' + iconBase + '/settings.svg")');
    root.style.setProperty("--icon-theater", 'url("' + iconBase + '/theater.svg")');
    root.style.setProperty("--icon-full", 'url("' + iconBase + '/full.svg")');
    root.classList.add("yrp-icons-ready");

    var centerLogo = root.querySelector(".yrp-center-logo");
    if (centerLogo) centerLogo.setAttribute("src", PLAYER_BASE + "/img/logo.png");

    wireEmbed(root, wrap, video, controls, spritesVtt, DEBUG, ccBtn);
  }

  function wireEmbed(root, wrap, video, controls, spritesVttUrl, DEBUG, ccBtn) {
    function d() { if (!DEBUG) return; try { console.debug.apply(console, ["[YRP-EMBED]"].concat([].slice.call(arguments))); } catch (_) {} }

    var centerPlay = root.querySelector(".yrp-center-play");
    var btnPlay = root.querySelector(".yrp-play");
    var btnVol = root.querySelector(".yrp-vol-btn");
    var volWrap = root.querySelector(".yrp-volume");
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
    var btnFull = root.querySelector(".yrp-fullscreen");
    var btnPip = root.querySelector(".yrp-pip");
    var ctx = root.querySelector(".yrp-context");

    var seeking = false, duration = 0;
    var hideTimer = null;
    var userTouchedVolume = false;
    var autoMuteApplied = false;

    // SPRITES PREVIEW STATE
    var spriteCues = [];
    var spritesLoaded = false;
    var spritesLoadError = false;
    var spritePop = null;
    var spriteDurationApprox = 0;

    function parseTimestamp(ts){
      var m = String(ts||"").match(/^(\d{2}):(\d{2}):(\d{2}\.\d{3})$/);
      if(!m) return 0;
      var h = parseInt(m[1],10), mm = parseInt(m[2],10), ss = parseFloat(m[3]);
      return h*3600 + mm*60 + ss;
    }
    function buildAbsoluteSpriteUrl(rel){
      if(!rel) return "";
      if(/^https?:\/\//i.test(rel) || rel.startsWith("/")) return rel;
      try {
        var u = new URL(spritesVttUrl, window.location.origin);
        var baseDir = u.pathname.replace(/\/sprites\.vtt$/, "");
        return baseDir + "/" + rel.replace(/^\/+/,"");
      } catch(e){
        return rel;
      }
    }
    function ensureSpritePop(){
      if (spritePop) return spritePop;
      if (!progress) return null;
      spritePop = document.createElement("div");
      spritePop.className = "yrp-sprite-pop";
      spritePop.style.position = "absolute";
      spritePop.style.bottom = "calc(100% + 30px)";
      spritePop.style.left = "0";
      spritePop.style.display = "none";
      spritePop.style.width = "160px";
      spritePop.style.height = "90px";
      spritePop.style.border = "1px solid #333";
      spritePop.style.background = "#000";
      spritePop.style.overflow = "hidden";
      spritePop.style.zIndex = "5";
      if (getComputedStyle(progress).position === "static") progress.style.position = "relative";
      progress.appendChild(spritePop);
      return spritePop;
    }
    function loadSpritesVTT(){
      if (!spritesVttUrl || spritesLoaded || spritesLoadError) return;
      fetch(spritesVttUrl, { credentials: "same-origin" })
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
              var spriteRel = "", x=0,y=0,w=0,h=0;
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
              var absUrl = buildAbsoluteSpriteUrl(spriteRel);
              spriteCues.push({start:start,end:end,spriteUrl:absUrl,x:x,y:y,w:w,h:h});
              if(end > spriteDurationApprox) spriteDurationApprox = end;
              i++;
            }
          }
          spritesLoaded = true;
          d("embed sprites VTT loaded", {cues: spriteCues.length, durationApprox: spriteDurationApprox});
        })
        .catch(function(err){
          spritesLoadError = true;
          d("embed sprites VTT load failed", err);
        });
    }
    function showSpritePreview(clientX){
      if (!spritesVttUrl || !spriteCues.length || !rail) return;
      var rect = rail.getBoundingClientRect();
      var x = Math.max(0, Math.min(clientX - rect.left, rect.width));
      var frac = rect.width > 0 ? x / rect.width : 0;
      var t = (duration || spriteDurationApprox || 0) * frac;
      var cue = null;
      for (var i=0;i<spriteCues.length;i++){
        var c = spriteCues[i];
        if (t >= c.start && t < c.end) { cue = c; break; }
      }
      var pop = ensureSpritePop();
      if (!pop) return;
      if (!cue || !cue.spriteUrl || cue.w <= 0 || cue.h <= 0) {
        pop.style.display = "none";
        return;
      }
      while (pop.firstChild) pop.removeChild(pop.firstChild);
      var img = document.createElement("img");
      img.src = cue.spriteUrl;
      img.style.position = "absolute";
      img.style.left = (-cue.x) + "px";
      img.style.top = (-cue.y) + "px";
      pop.appendChild(img);

      pop.style.display = "block";
      var leftPx = Math.max(0, Math.min(rect.width - cue.w, x - cue.w/2));
      pop.style.left = leftPx + "px";
      pop.style.width = cue.w + "px";
      pop.style.height = cue.h + "px";
    }

    function showControls() {
      root.classList.remove("autohide");
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(function () { root.classList.add("autohide"); }, 1800);
    }
    function layoutFillViewport() {
      try {
        var H = window.innerHeight || document.documentElement.clientHeight || root.clientHeight || 0;
        if (H <= 0) return;
        wrap.style.height = H + "px";
        video.style.height = "100%";
        video.style.width = "100%";
        video.style.objectFit = "contain";
      } catch (_) {}
    }
    function updateTimes() {
      try { duration = isFinite(video.duration) ? video.duration : 0; } catch (e) { duration = 0; }
      if (tTot) tTot.textContent = fmtTime(duration);
      if (tCur) tCur.textContent = fmtTime(video.currentTime || 0);
    }
    function updateProgress() {
      var d = duration || 0, ct = video.currentTime || 0;
      var frac = d > 0 ? Math.max(0, Math.min(ct / d, 1)) : 0;
      if (played) played.style.width = (frac * 100).toFixed(3) + "%";
      if (handle) handle.style.left = (frac * 100).toFixed(3) + "%";
      var b = 0;
      if (video.buffered && video.buffered.length > 0) {
        try { b = video.buffered.end(video.buffered.length - 1); } catch (e) { b = 0; }
      }
      var bfrac = d > 0 ? Math.max(0, Math.min(b / d, 1)) : 0;
      if (buf) buf.style.width = (bfrac * 100).toFixed(3) + "%";
    }
    function refreshVolIcon() {
      var v = video.muted ? 0 : video.volume;
      var label = (video.muted || v === 0) ? "Mute" : "Vol";
      var b = root.querySelector(".yrp-vol-btn");
      if (b) {
        b.textContent = label;
        b.classList.toggle("icon-mute", (label === "Mute"));
        b.classList.toggle("icon-vol",  (label !== "Mute"));
      }
    }
    function setMutedToggle() { video.muted = !video.muted; refreshVolIcon(); }
    function playToggle() { if (video.paused) video.play().catch(function(){ }); else video.pause(); }
    function seekByClientX(xc) {
      var r = rail.getBoundingClientRect();
      var x = Math.max(0, Math.min(xc - r.left, r.width));
      var f = r.width > 0 ? x / r.width : 0;
      var t = (duration || 0) * f;
      video.currentTime = t;
    }
    function updateTooltip(xc) {
      var tt = tooltip; if (!tt) return;
      var r = rail.getBoundingClientRect();
      var x = Math.max(0, Math.min(xc - r.left, r.width));
      var f = r.width > 0 ? x / r.width : 0;
      var t = (duration || 0) * f;
      tt.textContent = fmtTime(t);
      tt.style.left = (f * 100).toFixed(3) + "%";
      tt.hidden = false;
    }
    function hideMenus() {
      if (menu) { menu.hidden = true; if (btnSettings) btnSettings.setAttribute("aria-expanded", "false"); }
      if (ctx) ctx.hidden = true;
      root.classList.remove("vol-open");
    }

    // volume persistence
    (function(){
      var vs = (function(){
        try { var x = localStorage.getItem("yrp:volume"); return x ? JSON.parse(x) : null; } catch(_){ return null; }
      })();
      if (vs && typeof vs.v === "number") video.volume = Math.max(0, Math.min(vs.v, 1));
      if (vs && typeof vs.m === "boolean") video.muted = !!vs.m;
      if (volSlider) volSlider.value = String(video.volume || 1);
      refreshVolIcon();

      video.addEventListener("volumechange", function(){
        if (autoMuteApplied && video.muted && !userTouchedVolume) return;
        try { localStorage.setItem("yrp:volume", JSON.stringify({ v: Math.max(0, Math.min(video.volume || 0, 1)), m: !!video.muted })); } catch(_){}
      });
      video.addEventListener("loadedmetadata", function once(){
        video.removeEventListener("loadedmetadata", once);
        if (userTouchedVolume) return;
        var vs2 = (function(){
          try { var x = localStorage.getItem("yrp:volume"); return x ? JSON.parse(x) : null; } catch(_){ return null; }
        })();
        if (vs2) {
          if (typeof vs2.v === "number") video.volume = Math.max(0, Math.min(vs2.v, 1));
          if (typeof vs2.m === "boolean") video.muted = !!vs2.m;
          if (volSlider) volSlider.value = String(video.volume || 1);
          refreshVolIcon();
        }
      });
    })();

    // speed persistence
    (function(){
      try {
        var sp = localStorage.getItem("yrp:speed");
        if (sp) {
          var v = parseFloat(sp);
          if (isFinite(v) && v > 0) video.playbackRate = v;
        }
      } catch(_) {}
      video.addEventListener("ratechange", function(){
        try { localStorage.setItem("yrp:speed", String(video.playbackRate)); } catch(_){}
      });
    })();

    // resume persistence
    (function(){
      var vid = root.getAttribute("data-video-id") || "";
      if (!vid) return;
      function loadMap(){ try{ var s=localStorage.getItem("yrp:resume"); return s? JSON.parse(s): {}; }catch(_){ return {}; } }
      function saveMap(m){ try{ localStorage.setItem("yrp:resume", JSON.stringify(m)); }catch(_){ } }
      var map = loadMap(), rec = map[vid], now = Date.now();
      function applyResume(t) {
        var d = isFinite(video.duration) ? video.duration : 0;
        if (d && t > 10 && t < d - 5) { try { video.currentTime = t; } catch(_){ } }
      }
      if (rec && typeof rec.t === "number" && (now - (rec.ts || 0)) < 180*24*3600*1000) {
        var setAt = Math.max(0, rec.t|0);
        if (isFinite(video.duration) && video.duration > 0) applyResume(setAt);
        else video.addEventListener("loadedmetadata", function once(){ video.removeEventListener("loadedmetadata", once); applyResume(setAt); });
      }
      var savePos = throttle(function(){
        var d = isFinite(video.duration) ? video.duration : 0;
        var cur = Math.max(0, Math.floor(video.currentTime || 0));
        var m = loadMap(); m[vid] = { t: cur, ts: Date.now(), d: d };
        var keys = Object.keys(m);
        if (keys.length > 200) {
          keys.sort(function(a,b){ return (m[a].ts||0) - (m[b].ts||0); });
          for (var i=0;i<keys.length-200;i++) delete m[keys[i]];
        }
        saveMap(m);
      }, 3000);
      video.addEventListener("timeupdate", function(){ if (!video.paused && !video.seeking) savePos(); });
      video.addEventListener("ended", function(){ var m = loadMap(); delete m[vid]; saveMap(m); });
    })();

    ["loadedmetadata","loadeddata","canplay","canplaythrough","play","playing","pause","stalled","suspend","waiting","error","abort","emptied"].forEach(function(ev){
      video.addEventListener(ev, function(){ d("event:", ev, { rs: video.readyState, paused: video.paused, muted: video.muted }); });
    });

    // autoplay (embed only if opt.autoplay === true)
    (function(){
      var host = root.closest(".player-host") || root;
      var opt = parseJSONAttr(host, "data-options", null);
      var WANT = !!(opt && Object.prototype.hasOwnProperty.call(opt, "autoplay") && opt.autoplay);
      d("autoplay check (embed)", { WANT: WANT, opt: opt });
      if (!WANT) return;
      function tryPlaySequence(reason) {
        d("tryPlaySequence", { reason: reason, muted: video.muted, rs: video.readyState });
        var p = null;
        try { p = video.play(); } catch (e) { d("play() threw sync", e); p = null; }
        if (p && typeof p.then === "function") {
          p.then(function(){ d("play() resolved"); }).catch(function(err){
            d("play() rejected", { name: err && err.name, msg: err && err.message });
            if (!video.muted) {
              video.muted = true;
              video.setAttribute("muted", "");
              try { video.play().catch(function(e2){ d("retry rejected", e2); }); } catch(e2){ d("retry threw sync", e2); }
            }
          });
        } else {
          setTimeout(function(){
            if (video.paused) {
              video.muted = true;
              video.setAttribute("muted", "");
              try { video.play().catch(function(e3){ d("no-promise fallback rejected", e3); }); } catch(e3){ d("no-promise fallback threw", e3); }
            }
          }, 0);
        }
      }
      var fired = false;
      function fireOnce(tag){ if (fired) return; fired = true; tryPlaySequence(tag); }
      if (video.readyState >= 1) fireOnce("readyState>=1");
      ["loadedmetadata","loadeddata","canplay","canplaythrough"].forEach(function(ev){
        var once = function(){ video.removeEventListener(ev, once); fireOnce(ev); };
        video.addEventListener(ev, once);
      });
      setTimeout(function(){ if (video.paused) tryPlaySequence("watchdog"); }, 1200);
    })();

    if (centerPlay) centerPlay.addEventListener("click", function(){ playToggle(); });
    if (btnPlay) btnPlay.addEventListener("click", function(){ playToggle(); });
    video.addEventListener("click", function(){ playToggle(); });

    if (btnVol) btnVol.addEventListener("click", function(e){
      e.preventDefault(); e.stopPropagation();
      userTouchedVolume = true;
      setMutedToggle();
      root.classList.add("vol-open");
      showControls();
      setTimeout(function(){ root.classList.remove("vol-open"); }, 800);
    });

    if (controls) {
      controls.addEventListener("click", function(e){
        var t = e.target; if (t && t.nodeType === 3 && t.parentNode) t = t.parentNode;
        if (t && t.classList && t.classList.contains("yrp-vol-btn")) {
          e.preventDefault(); e.stopPropagation();
          userTouchedVolume = true;
          setMutedToggle();
          root.classList.add("vol-open");
          showControls();
          setTimeout(function(){ root.classList.remove("vol-open"); }, 800);
        }
      }, true);
    }

    if (volSlider) {
      volSlider.addEventListener("input", function(){
        userTouchedVolume = true;
        var v = parseFloat(volSlider.value || "1"); if (!isFinite(v)) v = 1;
        v = Math.max(0, Math.min(v, 1));
        video.volume = v; if (v > 0) video.muted = false; refreshVolIcon();
        root.classList.add("vol-open"); showControls();
      });
    }
    if (volWrap) {
      volWrap.addEventListener("wheel", function(e){
        e.preventDefault();
        userTouchedVolume = true;
        var step = 0.05, v = video.muted ? 0 : video.volume;
        var nv = Math.max(0, Math.min(v + (e.deltaY < 0 ? step : -step), 1));
        video.volume = nv; if (nv > 0) video.muted = false;
        if (volSlider) volSlider.value = String(nv);
        refreshVolIcon(); root.classList.add("vol-open"); showControls();
      }, { passive: false });
    }

    if (progress && rail) {
      progress.addEventListener("mousedown", function (e) { seeking = true; seekByClientX(e.clientX); showControls(); });
      window.addEventListener("mousemove", function (e) { if (seeking) seekByClientX(e.clientX); });
      window.addEventListener("mouseup", function () { seeking = false; });
      progress.addEventListener("mousemove", function (e) {
        updateTooltip(e.clientX);
        if (spritesVttUrl && spritesLoaded && !spritesLoadError) {
          showSpritePreview(e.clientX);
        } else if (spritesVttUrl && !spritesLoaded && !spritesLoadError) {
          loadSpritesVTT();
        }
      });
      progress.addEventListener("mouseleave", function () {
        if (tooltip) tooltip.hidden = true;
        if (spritePop) spritePop.style.display = "none";
      });
    }

    if (btnSettings && menu) {
      btnSettings.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation();
        var isOpen = !menu.hidden;
        if (isOpen) {
          menu.hidden = true;
          btnSettings.setAttribute("aria-expanded", "false");
        } else {
          hideMenus();
          menu.hidden = false;
          btnSettings.setAttribute("aria-expanded", "true");
          root.classList.add("vol-open");
          showControls();
        }
      });
      menu.addEventListener("click", function (e) {
        var t = e.target;
        if (t && t.classList.contains("yrp-menu-item")) {
          var sp = parseFloat(t.getAttribute("data-speed") || "NaN");
          if (!isNaN(sp)) {
            video.playbackRate = sp;
            menu.hidden = true;
            btnSettings.setAttribute("aria-expanded", "false");
          }
        }
      });
      document.addEventListener("click", function (e) {
        if (!menu.hidden && !menu.contains(e.target) && e.target !== btnSettings) {
          menu.hidden = true;
          btnSettings.setAttribute("aria-expanded", "false");
        }
      });
      document.addEventListener("keydown", function (ev) {
        if (ev.code === "Escape" || (ev.key || "").toLowerCase() === "escape") {
          if (!menu.hidden) {
            menu.hidden = true;
            btnSettings.setAttribute("aria-expanded", "false");
          }
        }
      });
    }

    if (btnFull) {
      btnFull.addEventListener("click", function () {
        if (document.fullscreenElement) { document.exitFullscreen().catch(function(){}); }
        else { root.requestFullscreen && root.requestFullscreen().catch(function(){}); }
      });
    }
    if (btnPip) {
      btnPip.addEventListener("click", function(e){
        e.preventDefault(); e.stopPropagation();
        try {
          if (document.pictureInPictureEnabled && video.requestPictureInPicture && !video.disablePictureInPicture) {
            if (document.pictureInPictureElement === video) { document.exitPictureInPicture().catch(function(){}); }
            else {
              var need = video.paused, prev = video.muted, p = Promise.resolve();
              if (need) { video.muted = true; p = video.play().catch(function(){}); }
              p.then(function(){ return video.requestPictureInPicture(); })
               .catch(function(){})
               .then(function(){ if (need) { video.pause(); video.muted = prev; } });
            }
          }
        } catch(_){}
      });
    }

    root.addEventListener("contextmenu", function (e) {
      e.preventDefault();
      hideMenus();
      if (!ctx) return;
      var rw = root.getBoundingClientRect();
      ctx.style.left = (e.clientX - rw.left) + "px";
      ctx.style.top = (e.clientY - rw.top) + "px";
      ctx.hidden = false;
      root.classList.add("vol-open"); showControls();
    });
    if (ctx) {
      ctx.addEventListener("click", function (ev) {
        var act = ev.target && ev.target.getAttribute("data-action");
        var at = Math.floor(video.currentTime || 0);
        var vid = root.getAttribute("data-video-id") || "";
        if (act === "pip") {
          btnPip && btnPip.click();
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
          var iframe = "<iframe width=\"560\" height=\"315\" src=\"" + src + "\" frameborder=\"0\" allow=\"autoplay; encrypted-media; clipboard-write\" allowfullscreen></iframe>";
          copyText(iframe);
        }
        ctx.hidden = true;
      });
      document.addEventListener("click", function (e2) {
        if (!ctx.hidden && !ctx.contains(e2.target)) ctx.hidden = true;
      });
      document.addEventListener("keydown", function escClose(ev){
        if (ev.code === "Escape" || (ev.key||"").toLowerCase() === "escape") {
          if (!ctx.hidden) ctx.hidden = true;
        }
      });
    }

    function handleHotkey(e) {
      var t = e.target; var tag = t && t.tagName ? t.tagName.toUpperCase() : "";
      if (t && (t.isContentEditable || tag === "INPUT" || tag === "TEXTAREA")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var code = e.code, key = (e.key || "").toLowerCase();
      if (code === "Space" || code === "Enter" || code === "NumpadEnter" || code === "MediaPlayPause" || code === "KeyK" || key === "k") {
        e.preventDefault(); video.paused ? video.play().catch(function(){}) : video.pause(); return;
      }
      if (code === "ArrowLeft" || code === "KeyJ" || key === "j") {
        e.preventDefault(); video.currentTime = Math.max(0, (video.currentTime || 0) - 5); return;
      }
      if (code === "ArrowRight" || code === "KeyL" || key === "l") {
        e.preventDefault(); var dUR = isFinite(video.duration) ? video.duration : 1e9; video.currentTime = Math.min((video.currentTime || 0) + 5, dUR); return;
      }
      if (code === "KeyM" || key === "m") { e.preventDefault(); setMutedToggle(); return; }
      if (code === "KeyF" || key === "f") { e.preventDefault(); if (btnFull) btnFull.click(); return; }
      if (code === "KeyI" || key === "i") { e.preventDefault(); if (btnPip) btnPip.click(); return; }
      if (code === "Escape" || key === "escape") { hideMenus(); return; }
    }
    document.addEventListener("keydown", handleHotkey);

    ["mouseenter","mousemove","pointermove","touchstart"].forEach(function(ev){
      (controls || root).addEventListener(ev, function(){ try{ root.focus(); }catch(_){} showControls(); }, { passive: true });
    });
    root.addEventListener("mouseleave", function(){ setTimeout(function(){ root.classList.add("autohide"); }, 600); });

    function relayout(){ layoutFillViewport(); }
    function layoutFillViewport(){
      try {
        var H = window.innerHeight || document.documentElement.clientHeight || root.clientHeight || 0;
        if (H <= 0) return;
        wrap.style.height = H + "px";
        video.style.height = "100%";
        video.style.width = "100%";
        video.style.objectFit = "contain";
      } catch(_) {}
    }
    window.addEventListener("resize", relayout);
    setTimeout(relayout, 0);
    setTimeout(relayout, 100);

    video.addEventListener("loadedmetadata", function(){
      updateTimes();
      updateProgress();
      relayout();
      loadSpritesVTT();
    });
    video.addEventListener("timeupdate", function(){ updateTimes(); updateProgress(); });
    video.addEventListener("progress", function(){ updateProgress(); });

    // CAPTIONS START: switch by CC button
    if (ccBtn) {
      ccBtn.addEventListener("click", function(e){
        e.preventDefault(); e.stopPropagation();
        try {
          var tracks = video.textTracks;
          if (!tracks) return;
          var showing = false;
          for (var i=0;i<tracks.length;i++){
            var tt = tracks[i];
            if ((tt.kind === "subtitles" || tt.kind === "captions") && tt.mode === "showing") { showing = true; break; }
          }
          var target = showing ? "hidden" : "showing";
          for (var j=0;j<tracks.length;j++){
            var ttrack = tracks[j];
            if (ttrack.kind === "subtitles" || ttrack.kind === "captions") ttrack.mode = target;
          }
        } catch(_){}
        showControls();
      });
    }
    // CAPTIONS END
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