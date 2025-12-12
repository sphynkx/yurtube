(function () {
  function fmtTime(sec) {
    if (!isFinite(sec) || sec < 0) sec = 0;
    sec = Math.floor(sec);
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;

    function pad(x) {
      return (x < 10 ? "0" : "") + x;
    }

    return (h > 0 ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s));
  }

  function clamp(v, min, max) {
    return v < min ? min : (v > max ? max : v);
  }

  function parseJSONAttr(el, name, fallback) {
    var s = el.getAttribute(name);
    if (!s) return fallback;
    try {
      return JSON.parse(s);
    } catch (_) {
      return fallback;
    }
  }

  function copyText(s) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(s).catch(function () {});
    } else {
      var ta = document.createElement("textarea");
      ta.value = s;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } catch (e) {}
      document.body.removeChild(ta);
    }
  }

  function cssPxToNum(s) {
    var v = parseFloat(String(s || "").trim());
    return isFinite(v) ? v : 0;
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

  var STORE = "yrp:";

  function canLS() {
    try {
      localStorage.setItem("__t", "1");
      localStorage.removeItem("__t");
      return true;
    } catch (e) {
      return false;
    }
  }

  function load(key, def) {
    if (!canLS()) return def;
    try {
      var s = localStorage.getItem(STORE + key);
      return s ? JSON.parse(s) : def;
    } catch (_) {
      return def;
    }
  }

  function save(key, val) {
    if (!canLS()) return;
    try {
      localStorage.setItem(STORE + key, JSON.stringify(val));
    } catch (_) {}
  }

  function throttle(fn, ms) {
    var t = 0, pend = false, lastArgs = null;
    return function () {
      lastArgs = arguments;
      var now = Date.now();
      if (!t || now - t >= ms) {
        t = now;
        fn.apply(null, lastArgs);
      } else if (!pend) {
        pend = true;
        setTimeout(function () {
          pend = false;
          fn.apply(null, lastArgs);
        }, ms - (now - t));
      }
    };
  }

  var FALLBACK_SRC = "/static/img/fallback_video_notfound.gif";

  function installFallbackGuards(video, sourceEl, onDebug) {
    var applied = false, watchdog = null;

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

    function clearWatchdog() {
      if (watchdog) {
        clearTimeout(watchdog);
        watchdog = null;
      }
    }

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

  function mountOne(host, tpl, BASE) {
    host.innerHTML = tpl;

    var root = host.querySelector(".yrp-container");
    var vw = root.querySelector(".yrp-video-wrap");
    var video = root.querySelector(".yrp-video");
    var source = video.querySelector("source");

    var videoSrc = host.getAttribute("data-video-src") || "";
    var poster = host.getAttribute("data-poster-url") || "";
    var vid = host.getAttribute("data-video-id") || "";
    var subs = parseJSONAttr(host, "data-subtitles", []);
    var opts = parseJSONAttr(host, "data-options", {});
    var spritesVtt = host.getAttribute("data-sprites-vtt") || "";
    var captionVtt = host.getAttribute("data-caption-vtt") || "";
    var captionLang = host.getAttribute("data-caption-lang") || "";

    var DEBUG = /\byrpdebug=1\b/i.test(location.search) || !!(opts && opts.debug);

    function d() {
      if (!DEBUG) return;
      try {
        console.debug.apply(console, ["[YRP]"].concat([].slice.call(arguments)));
      } catch (_) {}
    }

    if (source) source.setAttribute("src", videoSrc);
    if (poster) video.setAttribute("poster", poster);
    if (opts.autoplay) video.setAttribute("autoplay", "");
    if (opts.muted) video.setAttribute("muted", "");
    if (opts.loop) video.setAttribute("loop", "");
    if (vid) root.setAttribute("data-video-id", vid);
    if (spritesVtt) root.setAttribute("data-sprites-vtt", spritesVtt);
    video.setAttribute("playsinline", "");

    // Force native kind to "captions" for PiP stability
    if (Array.isArray(subs)) {
      subs.forEach(function (t) {
        if (!t || !t.src) return;
        var tr = document.createElement("track");
        tr.setAttribute("kind", "captions");
        if (t.srclang) tr.setAttribute("srclang", String(t.srclang));
        if (t.label) tr.setAttribute("label", String(t.label));
        tr.setAttribute("src", String(t.src));
        if (t.default) tr.setAttribute("default", "");
        video.appendChild(tr);
      });
    }

    if (captionVtt) {
      try {
        var ctr = document.createElement("track");
        ctr.setAttribute("kind", "captions");
        ctr.setAttribute("src", captionVtt);
        ctr.setAttribute("srclang", captionLang || "auto");
        ctr.setAttribute("label", captionLang || "Original");
        ctr.setAttribute("default", "");
        video.appendChild(ctr);
      } catch (e) {
        d("caption append failed", e);
      }
    }

    try {
      video.load();
      d("video.load()", { src: videoSrc });
    } catch (e) {
      d("video.load() error", e);
    }

    installFallbackGuards(video, source, d);

    var iconBase = BASE + "/img/buttons";
    [
      ["--icon-play", "play.svg"],
      ["--icon-pause", "pause.svg"],
      ["--icon-prev", "prev.svg"],
      ["--icon-next", "next.svg"],
      ["--icon-vol", "volume.svg"],
      ["--icon-mute", "mute.svg"],
      ["--icon-cc", "cc.svg"],
      ["--icon-mini", "mini.svg"],
      ["--icon-settings", "settings.svg"],
      ["--icon-theater", "theater.svg"],
      ["--icon-full", "full.svg"],
      ["--icon-autoplay-on", "autoplay-on.svg"],
      ["--icon-autoplay-off", "autoplay-off.svg"]
    ].forEach(function (p) {
      root.style.setProperty(p[0], 'url("' + iconBase + '/' + p[1] + '")');
    });

    root.classList.add("yrp-icons-ready");

    var centerLogo = root.querySelector(".yrp-center-logo");
    if (centerLogo) centerLogo.setAttribute("src", BASE + "/img/logo.png");

    // Custom captions overlay (draggable)
    var overlay = document.createElement("div");
    overlay.className = "yrp-captions-layer";
    Object.assign(overlay.style, {
      position: "absolute",
      left: "50%",
      top: "80%",
      transform: "translate(-50%,-50%)",
      zIndex: "21",
      pointerEvents: "auto",
      userSelect: "none",
      touchAction: "none"
    });

    var textBox = document.createElement("div");
    textBox.className = "yrp-captions-text";
    Object.assign(textBox.style, {
      display: "inline-block",
      background: "rgba(0,0,0,0.55)",
      color: "#fff",
      fontSize: "16px",
      lineHeight: "1.35",
      padding: "6px 10px",
      borderRadius: "6px",
      maxWidth: "80%",
      minWidth: "220px",
      boxShadow: "0 2px 6px rgba(0,0,0,0.35)",
      whiteSpace: "pre-wrap",
      wordBreak: "break-word"
    });
    overlay.appendChild(textBox);

    if (vw) {
      vw.style.position = "relative";
      vw.appendChild(overlay);
    }

    var dragState = {
      active: false,
      startX: 0,
      startY: 0,
      startLeftPct: 50,
      startTopPct: 80
    };

    var userMoved = false;

    function getVideoWrapRect() {
      return vw ? vw.getBoundingClientRect() : { width: 0, height: 0, left: 0, top: 0 };
    }

    function updateTextBoxMaxWidthByCenter(cx) {
      var r = getVideoWrapRect();
      var leftAvail = cx;
      var rightAvail = r.width - cx;
      var avail = Math.min(leftAvail, rightAvail) * 2;
      var pad = 12, minW = 220;
      textBox.style.maxWidth = Math.max(minW, Math.floor(avail - pad)) + "px";
    }

    function startDrag(e) {
      var t = e.touches ? e.touches[0] : e;
      var r = getVideoWrapRect();
      var ov = overlay.getBoundingClientRect();
      dragState.startLeftPct = ((ov.left + ov.width / 2) - r.left) / r.width * 100;
      dragState.startTopPct = ((ov.top + ov.height / 2) - r.top) / r.height * 100;
      dragState.active = true;
      dragState.startX = t.clientX;
      dragState.startY = t.clientY;
      e.preventDefault();
      e.stopPropagation();
    }

    function moveDrag(e) {
      if (!dragState.active) return;
      var t = e.touches ? e.touches[0] : e;
      var dx = t.clientX - dragState.startX;
      var dy = t.clientY - dragState.startY;
      var r = getVideoWrapRect();
      var newLeftPx = (dragState.startLeftPct / 100) * r.width + dx;
      var newTopPx = (dragState.startTopPct / 100) * r.height + dy;
      var ov = overlay.getBoundingClientRect();
      var halfW = ov.width / 2, halfH = ov.height / 2;
      newLeftPx = clamp(newLeftPx, halfW, r.width - halfW);
      newTopPx = clamp(newTopPx, halfH, r.height - halfH);
      overlay.style.left = (newLeftPx / r.width * 100) + "%";
      overlay.style.top = (newTopPx / r.height * 100) + "%";
      overlay.style.transform = "translate(-50%,-50%)";
      userMoved = true;
      updateTextBoxMaxWidthByCenter(newLeftPx);
      e.preventDefault();
      e.stopPropagation();
    }

    function endDrag(e) {
      if (dragState.active) {
        dragState.active = false;
        e.preventDefault();
        e.stopPropagation();
      }
    }

    overlay.addEventListener("mousedown", startDrag);
    overlay.addEventListener("touchstart", startDrag, { passive: false });
    document.addEventListener("mousemove", moveDrag);
    document.addEventListener("touchmove", moveDrag, { passive: false });
    document.addEventListener("mouseup", endDrag);
    document.addEventListener("touchend", endDrag);
    overlay.addEventListener("click", function (e) { e.stopPropagation(); });

    function adjustOverlayAuto() {
      if (userMoved) return;
      var controlsVisible = !root.classList.contains("autohide");
      overlay.style.top = controlsVisible ? "78%" : "82%";
      overlay.style.left = "50%";
      overlay.style.transform = "translate(-50%,-50%)";
      updateTextBoxMaxWidthByCenter(getVideoWrapRect().width / 2);
    }

    var startAt = 0;
    if (typeof opts.start === "number" && opts.start > 0) startAt = Math.max(0, opts.start);

    // Honor URL param `t` on watch page; take max between existing startAt and URL t
    try {
      var uWatch = new URL(window.location.href);
      var tParam = uWatch.searchParams.get("t");
      if (tParam != null) {
        var tNum = parseInt(String(tParam).trim(), 10);
        if (isFinite(tNum) && tNum > 0) startAt = Math.max(startAt, tNum);
      }
    } catch(_){}

    wire(root, startAt, DEBUG, {
      overlay: overlay,
      textBox: textBox,
      autoAdjust: adjustOverlayAuto
    }, startAt);
  }

  function wire(root, startAt, DEBUG, hooks, startFromUrl) {
    function d() {
      if (!DEBUG) return;
      try {
        console.debug.apply(console, ["[YRP]"].concat([].slice.call(arguments)));
      } catch (_) {}
    }

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
    var btnSubtitles = root.querySelector(".yrp-subtitles");

    var hideTimer = null, seeking = false, duration = 0;
    var userTouchedVolume = false, autoMuteApplied = false;
    var pipInSystem = false, pipWasPlayingOrig = false, pipWasMutedOrig = false, pipUserState = null;
    var autoplayOn = !!load("autoplay", false);
    var spritesVttUrl = root.getAttribute("data-sprites-vtt") || "";
    var spriteCues = [], spriteDurationApprox = 0, spritePop = null, spritesLoaded = false, spritesLoadError = false;

    var overlayActive = true;
    var activeTrackIndex = 0;

    function subtitleTracks() {
      try {
        return video.textTracks ? Array.prototype.filter.call(video.textTracks, function (tr) {
          return tr.kind === "subtitles" || tr.kind === "captions";
        }) : [];
      } catch (_) {
        return [];
      }
    }

    function anySubtitleTracks() { return subtitleTracks().length > 0; }

    function chooseActiveTrack() {
      var subs = subtitleTracks();
      if (subs.length === 0) return null;
      if (activeTrackIndex < 0 || activeTrackIndex >= subs.length) activeTrackIndex = 0;
      return subs[activeTrackIndex];
    }

    function logTracks(prefix) {
      var subs = subtitleTracks();
      var info = subs.map(function (tr, i) {
        return {
          i: i,
          mode: tr.mode,
          label: tr.label,
          srclang: tr.language || tr.srclang,
          cues: tr.cues ? tr.cues.length : 0,
          kind: tr.kind
        };
      });
      d(prefix, info);
    }

    function applyPageModes() {
      var subs = subtitleTracks();
      subs.forEach(function (tr, i) {
        tr.mode = (i === activeTrackIndex && overlayActive) ? "hidden" : "disabled";
      });
      logTracks("applyPageModes");
    }

    function applyPiPOriginalsDisabled() {
      var subs = subtitleTracks();
      subs.forEach(function (tr) { tr.mode = "disabled"; });
      logTracks("applyPiPOriginalsDisabled");
    }

    function currentCueText() {
      var tr = chooseActiveTrack();
      if (!tr || !tr.cues) return "";
      var ct = video.currentTime || 0;
      for (var i = 0; i < tr.cues.length; i++) {
        var c = tr.cues[i];
        if (ct >= c.startTime && ct <= c.endTime) return (c.text || "").replace(/\r/g, "");
      }
      return "";
    }

    function updateOverlayText() {
      if (!hooks || !hooks.textBox) return;
      hooks.textBox.textContent = overlayActive ? currentCueText() : "";
    }

    function refreshSubtitlesBtn() {
      if (!btnSubtitles) return;
      var has = anySubtitleTracks();
      btnSubtitles.disabled = !has;
      btnSubtitles.style.visibility = has ? "visible" : "hidden";
      btnSubtitles.classList.toggle("no-tracks", !has);
      btnSubtitles.classList.toggle("has-tracks", has);
      btnSubtitles.classList.toggle("active", has && overlayActive);
      btnSubtitles.classList.toggle("disabled-track", has && !overlayActive);
      btnSubtitles.setAttribute("aria-pressed", overlayActive ? "true" : "false");
    }

    // MIRROR TRACK FOR PiP
    var mirrorTrack = null; // TextTrack created by addTextTrack
    var mirrorLang = "";
    var mirrorLabel = ""; // for reuse

    function vttCtor() { return (window.VTTCue || window.TextTrackCue); }

    function buildMirrorFrom(sourceTrack, whenReady) {
      if (mirrorTrack) { whenReady && whenReady(); return; }
      if (!sourceTrack) { whenReady && whenReady(); return; }

      var tryBuild = function () {
        try {
          var cues = sourceTrack.cues;
          if (!cues || cues.length === 0) { whenReady && whenReady(); return; }

          mirrorLang = sourceTrack.language || sourceTrack.srclang || "";
          mirrorLabel = sourceTrack.label || "CC";
          mirrorTrack = video.addTextTrack("captions", mirrorLabel, mirrorLang);

          var Cue = vttCtor();
          for (var i = 0; i < cues.length; i++) {
            var c = cues[i];
            try {
              var nc = new Cue(c.startTime, c.endTime, c.text || "");
              mirrorTrack.addCue(nc);
            } catch (_) {}
          }
          whenReady && whenReady();
        } catch (_) {
          whenReady && whenReady();
        }
      };

      if (!sourceTrack.cues || sourceTrack.cues.length === 0) {
        var once = function () { sourceTrack.removeEventListener("cuechange", once); tryBuild(); };
        try { sourceTrack.addEventListener("cuechange", once); } catch (_) { tryBuild(); }
      } else {
        tryBuild();
      }
    }

    function setMirrorMode(mode) { if (mirrorTrack) { try { mirrorTrack.mode = mode; } catch (_) {} } }

    function parseTimestamp(ts) {
      var m = String(ts || "").match(/^(\d{2}):(\d{2}):(\d{2}\.\d{3})$/);
      if (!m) return 0;
      return parseInt(m[1], 10) * 3600 + parseInt(m[2], 10) * 60 + parseFloat(m[3]);
    }

    function buildAbsoluteSpriteUrl(rel) {
      if (!rel) return "";
      if (/^https?:\/\//i.test(rel) || rel.startsWith("/")) return rel;
      try {
        var u = new URL(spritesVttUrl, window.location.origin);
        var base = u.pathname.replace(/\/sprites\.vtt$/, "");
        return base + "/" + rel.replace(/^\/+/, "");
      } catch (e) {
        return rel;
      }
    }

    function ensureSpritePop() {
      if (spritePop) return spritePop;
      if (!progress) return null;
      spritePop = document.createElement("div");
      Object.assign(spritePop.style, {
        position: "absolute",
        display: "none",
        bottom: "calc(100% + 30px)",
        left: "0",
        width: "160px",
        height: "90px",
        border: "1px solid #333",
        background: "#000",
        overflow: "hidden",
        zIndex: "5"
      });
      spritePop.className = "yrp-sprite-pop";
      if (getComputedStyle(progress).position === "static") progress.style.position = "relative";
      progress.appendChild(spritePop);
      return spritePop;
    }

    function loadSpritesVTT() {
      if (!spritesVttUrl || spritesLoaded || spritesLoadError) return;
      fetch(spritesVttUrl, { credentials: "same-origin" })
        .then(r => r.text())
        .then(function (text) {
          var lines = text.split(/\r?\n/);
          for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (!line) continue;
            if (line.indexOf("-->") >= 0) {
              var parts = line.split("-->").map(function (s) { return s.trim(); });
              if (parts.length < 2) continue;
              var start = parseTimestamp(parts[0]), end = parseTimestamp(parts[1]);
              var ref = (lines[i + 1] || "").trim(), spriteRel = "", x = 0, y = 0, w = 0, h = 0;
              var hashIdx = ref.indexOf("#xywh=");
              if (hashIdx > 0) {
                spriteRel = ref.substring(0, hashIdx);
                var xywh = ref.substring(hashIdx + 6).split(",");
                if (xywh.length === 4) {
                  x = parseInt(xywh[0], 10);
                  y = parseInt(xywh[1], 10);
                  w = parseInt(xywh[2], 10);
                  h = parseInt(xywh[3], 10);
                }
              }
              var abs = buildAbsoluteSpriteUrl(spriteRel);
              spriteCues.push({ start: start, end: end, spriteUrl: abs, x: x, y: y, w: w, h: h });
              if (end > spriteDurationApprox) spriteDurationApprox = end;
              i++;
            }
          }
          spritesLoaded = true;
        })
        .catch(function () { spritesLoadError = true; });
    }

    function showSpritePreviewAtClientX(clientX) {
      if (!spritesVttUrl || !spriteCues.length || !rail) return;
      var rect = rail.getBoundingClientRect();
      var x = clamp(clientX - rect.left, 0, rect.width);
      var frac = rect.width > 0 ? x / rect.width : 0;
      var t = (duration || spriteDurationApprox || 0) * frac;
      var cue = null;
      for (var i = 0; i < spriteCues.length; i++) {
        var c = spriteCues[i];
        if (t >= c.start && t < c.end) { cue = c; break; }
      }
      var pop = ensureSpritePop();
      if (!pop) return;
      if (!cue || !cue.spriteUrl || cue.w <= 0 || cue.h <= 0) { pop.style.display = "none"; return; }
      while (pop.firstChild) pop.removeChild(pop.firstChild);
      var img = document.createElement("img");
      Object.assign(img.style, { position: "absolute", left: (-cue.x) + "px", top: (-cue.y) + "px" });
      img.src = cue.spriteUrl;
      pop.appendChild(img);
      pop.style.display = "block";
      var leftPx = clamp(x - cue.w / 2, 0, rect.width - cue.w);
      pop.style.left = leftPx + "px";
      pop.style.width = cue.w + "px";
      pop.style.height = cue.h + "px";
    }

    function refreshAutoplayBtn() {
      if (!btnAutoplay) return;
      var on = autoplayOn;
      btnAutoplay.setAttribute("aria-pressed", on ? "true" : "false");
      btnAutoplay.title = on ? "Autoplay on (A)" : "Autoplay off (A)";
      btnAutoplay.textContent = "";
      var iconVar = on ? "var(--icon-autoplay-on)" : "var(--icon-autoplay-off)";
      Object.assign(btnAutoplay.style, {
        backgroundColor: "#6cc9fa",
        webkitMaskImage: iconVar,
        maskImage: iconVar,
        webkitMaskRepeat: "no-repeat",
        maskRepeat: "no-repeat",
        webkitMaskPosition: "center",
        maskPosition: "center",
        webkitMaskSize: "20px 20px",
        maskSize: "20px 20px"
      });
    }

    function refreshPlayBtn() {
      if (!btnPlay) return;
      var playing = !video.paused;
      btnPlay.classList.toggle("icon-play", !playing);
      btnPlay.classList.toggle("icon-pause", playing);
      btnPlay.setAttribute("aria-label", playing ? "Pause (Space, K)" : "Play (Space, K)");
      btnPlay.title = playing ? "Pause (Space, K)" : "Play (Space, K)";
      btnPlay.textContent = "";
      var iconVar = playing ? "var(--icon-pause)" : "var(--icon-play)";
      Object.assign(btnPlay.style, {
        backgroundColor: "#6cc9fa",
        webkitMaskImage: iconVar,
        maskImage: iconVar,
        webkitMaskRepeat: "no-repeat",
        maskRepeat: "no-repeat",
        webkitMaskPosition: "center",
        maskPosition: "center",
        webkitMaskSize: "20px 20px",
        maskSize: "20px 20px"
      });
    }

    function scheduleAutoHide(ms) {
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(function () {
        root.classList.add("autohide");
        hooks && hooks.autoAdjust && hooks.autoAdjust();
      }, Math.max(0, ms || 1200));
    }

    function showControls() {
      root.classList.remove("autohide");
      hooks && hooks.autoAdjust && hooks.autoAdjust();
      scheduleAutoHide(2000);
    }

    function updateTimes() {
      try { duration = isFinite(video.duration) ? video.duration : 0; } catch (e) { duration = 0; }
      if (tTot) tTot.textContent = fmtTime(duration);
      if (tCur) tCur.textContent = fmtTime(video.currentTime || 0);
    }

    function updateProgress() {
      var d = duration || 0, ct = video.currentTime || 0, f = d > 0 ? clamp(ct / d, 0, 1) : 0;
      if (played) played.style.width = (f * 100).toFixed(3) + "%";
      if (handle) handle.style.left = (f * 100).toFixed(3) + "%";
      var b = 0;
      if (video.buffered && video.buffered.length > 0) { try { b = video.buffered.end(video.buffered.length - 1); } catch (e) { b = 0; } }
      var bf = d > 0 ? clamp(b / d, 0, 1) : 0;
      if (buf) buf.style.width = (bf * 100).toFixed(3) + "%";
    }

    function playToggle() {
      if (video.paused) video.play().catch(function () {});
      else video.pause();
    }

    function setMutedToggle() {
      video.muted = !video.muted;
      refreshVolIcon();
    }

    function refreshVolIcon() {
      var v = video.muted ? 0 : video.volume;
      var label = (video.muted || v === 0) ? "Mute" : "Vol";
      if (btnVol) {
        btnVol.textContent = label;
        btnVol.classList.toggle("icon-mute", label === "Mute");
        btnVol.classList.toggle("icon-vol", label !== "Mute");
      }
    }

    function seekByClientX(xClient) {
      if (!rail) return;
      var rect = rail.getBoundingClientRect();
      var x = clamp(xClient - rect.left, 0, rect.width);
      var f = rect.width > 0 ? x / rect.width : 0;
      video.currentTime = (duration || 0) * f;
    }

    function updateTooltip(xClient) {
      if (!tooltip || !rail) return;
      var rect = rail.getBoundingClientRect();
      var x = clamp(xClient - rect.left, 0, rect.width);
      var f = rect.width > 0 ? x / rect.width : 0;
      var t = (duration || 0) * f;
      tooltip.textContent = fmtTime(t);
      tooltip.style.left = (f * 100).toFixed(3) + "%";
      tooltip.hidden = false;
    }

    function hideMenus() {
      if (menu) {
        menu.hidden = true;
        btnSettings && btnSettings.setAttribute("aria-expanded", "false");
      }
      var ctx = root.querySelector(".yrp-context");
      if (ctx) ctx.hidden = true;
      root.classList.remove("vol-open");
    }

    function measureControlsMinWidth() {
      var lw = leftGrp ? leftGrp.getBoundingClientRect().width : 0;
      var rw = rightGrp ? rightGrp.getBoundingClientRect().width : 0;
      var pad = 24;
      var mw = Math.ceil(lw + rw + pad);
      return (!isFinite(mw) || mw <= 0) ? 480 : mw;
    }

    function adjustWidthByAspect() {
      if (root.classList.contains("yrp-theater")) return;
      var cs = getComputedStyle(video);
      var maxH = cssPxToNum(cs.getPropertyValue("max-height")) || video.clientHeight || 0;
      var vw = video.videoWidth || 16, vh = video.videoHeight || 9;
      var aspect = vh > 0 ? vw / vh : 16 / 9;
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

    (function volumeResume() {
      var vs = load("volume", null);
      if (vs && typeof vs.v === "number") video.volume = clamp(vs.v, 0, 1);
      if (vs && typeof vs.m === "boolean") video.muted = !!vs.m;
      if (volSlider) volSlider.value = String(video.volume || 1);
      refreshVolIcon();

      video.addEventListener("volumechange", function () {
        if (autoMuteApplied && video.muted && !userTouchedVolume) return;
        save("volume", { v: clamp(video.volume || 0, 0, 1), m: !!video.muted });
      });

      video.addEventListener("loadedmetadata", function once() {
        video.removeEventListener("loadedmetadata", once);
        if (userTouchedVolume) return;
        var vs2 = load("volume", null);
        if (vs2) {
          if (typeof vs2.v === "number") video.volume = clamp(vs2.v, 0, 1);
          if (typeof vs2.m === "boolean") video.muted = !!vs2.m;
          if (volSlider) volSlider.value = String(video.volume || 1);
          refreshVolIcon();
        }
      });
    })();

    (function speedResume() {
      var sp = load("speed", null);
      if (typeof sp === "number" && sp > 0) video.playbackRate = sp;
      video.addEventListener("ratechange", function () { save("speed", video.playbackRate); });
    })();

    (function theaterInit() {
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

    (function resumePosition() {
      var vid = root.getAttribute("data-video-id") || "";
      if (!vid) return;

      // Skip resume logic entirely when explicit start is requested via URL (`t`)
      if (startFromUrl > 0) {
        try {
          var s0 = load("resume", {});
          if (s0 && s0[vid]) {
            delete s0[vid];
            save("resume", s0);
          }
        } catch(_){}
        return;
      }

      var map = load("resume", {}), rec = map[vid], now = Date.now();

      function applyResume(t) {
        var d = isFinite(video.duration) ? video.duration : 0;
        if (d && t > 10 && t < d - 5) { try { video.currentTime = t; } catch (_) {} }
      }

      if (rec && typeof rec.t === "number" && (now - (rec.ts || 0)) < 180 * 24 * 3600 * 1000) {
        var setAt = Math.max(0, rec.t | 0);
        if (isFinite(video.duration) && video.duration > 0) applyResume(setAt);
        else video.addEventListener("loadedmetadata", function once() { video.removeEventListener("loadedmetadata", once); applyResume(setAt); });
      }

      var savePos = throttle(function () {
        var d = isFinite(video.duration) ? video.duration : 0;
        var cur = Math.max(0, Math.floor(video.currentTime || 0));
        var m = load("resume", {});
        m[vid] = { t: cur, ts: Date.now(), d: d };
        var keys = Object.keys(m);
        if (keys.length > 200) {
          keys.sort(function (a, b) { return (m[a].ts || 0) - (m[b].ts || 0); });
          for (var i = 0; i < keys.length - 200; i++) delete m[keys[i]];
        }
        save("resume", m);
      }, 3000);

      video.addEventListener("timeupdate", function () { if (!video.paused && !video.seeking) savePos(); });
      video.addEventListener("ended", function () { var m = load("resume", {}); delete m[vid]; save("resume", m); });
    })();

    ["loadedmetadata", "loadeddata", "canplay", "canplaythrough", "play", "playing", "pause", "stalled", "suspend", "waiting", "error", "abort", "emptied"].forEach(function (ev) {
      video.addEventListener(ev, function () { d("event:", ev, { rs: video.readyState, paused: video.paused, muted: video.muted }); });
    });

    (function autoplayInit() {
      var host = root.closest(".player-host") || root;
      var opt = parseJSONAttr(host, "data-options", null);

      function want() {
        if (opt && opt.autoplay === true) return true;
        return !!load("autoplay", false);
      }

      if (!want()) {
        setTimeout(function () { scheduleAutoHide(1000); }, 0);
        return;
      }

      function sequence() {
        var p = null;
        try { p = video.play(); } catch (e) { p = null; }
        if (p && typeof p.then === "function") {
          p.then(function () {}).catch(function () {
            if (!video.muted) {
              autoMuteApplied = true;
              video.muted = true;
              video.setAttribute("muted", "");
              try { video.play().catch(function () {}); } catch (_) {}
            }
          });
        } else {
          setTimeout(function () {
            if (video.paused) {
              autoMuteApplied = true;
              video.muted = true;
              video.setAttribute("muted", "");
              try { video.play().catch(function () {}); } catch (_) {}
            }
          }, 0);
        }
      }

      var fired = false;

      function fireOnce() { if (fired) return; fired = true; sequence(); }

      if (video.readyState >= 1) fireOnce();

      ["loadedmetadata", "loadeddata", "canplay", "canplaythrough"].forEach(function (ev) {
        var once = function () { video.removeEventListener(ev, once); fireOnce(); };
        video.addEventListener(ev, once);
      });

      setTimeout(function () {
        if (video.paused) {
          autoMuteApplied = true;
          video.muted = true;
          video.setAttribute("muted", "");
          try { video.play().catch(function () {}); } catch (_) {}
        }
      }, 1200);
    })();

    video.addEventListener("loadedmetadata", function () {
      if (startAt > 0) {
        try { video.currentTime = Math.min(startAt, Math.floor(video.duration || startAt)); } catch (e) {}
      }
      setTimeout(adjustWidthByAspect, 0);
      updateTimes();
      updateProgress();
      refreshVolIcon();
      refreshAutoplayBtn();
      refreshPlayBtn();

      chooseActiveTrack();
      applyPageModes();
      refreshSubtitlesBtn();
      scheduleAutoHide(1200);
      loadSpritesVTT();
      updateOverlayText();

      var r = root.querySelector(".yrp-video-wrap").getBoundingClientRect();
      var centerX = r.width / 2, tb = root.querySelector(".yrp-captions-text");
      if (tb) {
        var leftAvail = centerX, rightAvail = r.width - centerX, avail = Math.min(leftAvail, rightAvail) * 2;
        var pad = 12, minW = 220;
        tb.style.maxWidth = Math.max(minW, Math.floor(avail - pad)) + "px";
      }
      logTracks("after loadedmetadata");
    });

    function attachCueListeners() {
      try {
        subtitleTracks().forEach(function (tr) {
          tr.addEventListener("cuechange", updateOverlayText);
          tr.addEventListener("load", updateOverlayText);
        });
      } catch (_) {}
    }

    attachCueListeners();

    window.addEventListener("resize", adjustWidthByAspect);
    video.addEventListener("timeupdate", function () { updateTimes(); updateProgress(); updateOverlayText(); });
    video.addEventListener("progress", updateProgress);
    video.addEventListener("play", function () { root.classList.add("playing"); refreshPlayBtn(); showControls(); });
    video.addEventListener("pause", function () { root.classList.remove("playing"); refreshPlayBtn(); showControls(); });

    // PiP: use mirror track
    function enterPiPSequence() {
      var src = chooseActiveTrack();
      buildMirrorFrom(src, function () {
        applyPiPOriginalsDisabled();
        setMirrorMode(overlayActive ? "showing" : "hidden");
        if (hooks && hooks.overlay) hooks.overlay.style.display = "none";
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            video.requestPictureInPicture().catch(function (err) {
              d("PiP request error", err);
              setMirrorMode("disabled");
              applyPageModes();
              if (hooks && hooks.overlay) hooks.overlay.style.display = overlayActive ? "" : "none";
            });
          });
        });
      });
    }

    function exitPiPSequence() { document.exitPictureInPicture().catch(function () {}); }

    video.addEventListener("enterpictureinpicture", function () {
      pipInSystem = true;
      pipWasPlayingOrig = !video.paused;
      pipWasMutedOrig = !!video.muted;
      pipUserState = null;
      d("enter PiP event");
      logTracks("PiP entered modes (originals disabled), mirror=" + (mirrorTrack ? mirrorTrack.mode : "none"));
    });

    video.addEventListener("leavepictureinpicture", function () {
      pipInSystem = false;
      var shouldPlay = (pipUserState === null) ? pipWasPlayingOrig : !!pipUserState;
      if (shouldPlay) video.play().catch(function () {}); else video.pause();
      setMirrorMode("disabled");
      if (hooks && hooks.overlay) hooks.overlay.style.display = overlayActive ? "" : "none";
      applyPageModes();
      d("leave PiP event");
    });

    function toggleMini() {
      if (!document.pictureInPictureEnabled || !video.requestPictureInPicture || video.disablePictureInPicture) return;
      if (document.pictureInPictureElement === video) exitPiPSequence();
      else enterPiPSequence();
    }

    video.addEventListener("click", playToggle);
    centerPlay && centerPlay.addEventListener("click", playToggle);
    btnPlay && btnPlay.addEventListener("click", playToggle);
    btnPrev && btnPrev.addEventListener("click", function () { root.dispatchEvent(new CustomEvent("yrp-prev", { bubbles: true })); });
    btnNext && btnNext.addEventListener("click", function () { root.dispatchEvent(new CustomEvent("yrp-next", { bubbles: true })); });

    if (btnVol) {
      btnVol.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        userTouchedVolume = true;
        autoMuteApplied = false;
        setMutedToggle();
        showControls();
        root.classList.add("vol-open");
        setTimeout(function () { root.classList.remove("vol-open"); }, 1200);
      });
    }

    if (vol) {
      vol.addEventListener("wheel", function (e) {
        e.preventDefault();
        userTouchedVolume = true;
        autoMuteApplied = false;
        var step = 0.05, v = video.muted ? 0 : video.volume;
        var nv = clamp(v + (e.deltaY < 0 ? step : -step), 0, 1);
        video.volume = nv;
        if (nv > 0) video.muted = false;
        volSlider && (volSlider.value = String(nv));
        refreshVolIcon();
        showControls();
      }, { passive: false });
    }

    if (volSlider) {
      volSlider.addEventListener("input", function () {
        userTouchedVolume = true;
        autoMuteApplied = false;
        var v = parseFloat(volSlider.value || "1");
        if (!isFinite(v)) v = 1;
        v = clamp(v, 0, 1);
        video.volume = v;
        if (v > 0) video.muted = false;
        refreshVolIcon();
      });

      volSlider.addEventListener("wheel", function (e) {
        e.preventDefault();
        userTouchedVolume = true;
        autoMuteApplied = false;
        var step = 0.05, v = video.muted ? 0 : video.volume;
        var nv = clamp(v + (e.deltaY < 0 ? step : -step), 0, 1);
        video.volume = nv;
        if (nv > 0) video.muted = false;
        volSlider.value = String(nv);
        refreshVolIcon();
        showControls();
      }, { passive: false });
    }

    if (progress) {
      progress.addEventListener("mousedown", function (e) { seeking = true; hideMenus(); seekByClientX(e.clientX); });
      window.addEventListener("mousemove", function (e) { if (seeking) seekByClientX(e.clientX); });
      window.addEventListener("mouseup", function () { seeking = false; });
      progress.addEventListener("mousemove", function (e) {
        updateTooltip(e.clientX);
        if (spritesVttUrl && spritesLoaded && !spritesLoadError) showSpritePreviewAtClientX(e.clientX);
        else if (spritesVttUrl && !spritesLoaded && !spritesLoadError) loadSpritesVTT();
      });
      progress.addEventListener("mouseleave", function () { tooltip && (tooltip.hidden = true); spritePop && (spritePop.style.display = "none"); });
    }

    if (btnSettings && menu) {
      btnSettings.addEventListener("click", function (e) {
        var open = menu.hidden ? false : true;
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

    btnFull && btnFull.addEventListener("click", function () {
      if (document.fullscreenElement) document.exitFullscreen().catch(function () {});
      else root.requestFullscreen && root.requestFullscreen().catch(function () {});
    });

    btnPip && btnPip.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); toggleMini(); });

    btnAutoplay && btnAutoplay.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var next = !load("autoplay", false);
      save("autoplay", next);
      autoplayOn = next;
      refreshAutoplayBtn();
    });

    btnSubtitles && btnSubtitles.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (!anySubtitleTracks()) return;
      overlayActive = !overlayActive;
      if (pipInSystem) {
        setMirrorMode(overlayActive ? "showing" : "hidden");
        if (hooks && hooks.overlay) hooks.overlay.style.display = "none";
      } else {
        if (hooks && hooks.overlay) hooks.overlay.style.display = overlayActive ? "" : "none";
        applyPageModes();
      }
      refreshSubtitlesBtn();
      updateOverlayText();
      d("toggle subtitles overlayActive=" + overlayActive + ", mirror=" + (mirrorTrack ? mirrorTrack.mode : "none"));
    });

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
        if (act === "pip") toggleMini();
        else if (act === "copy-url") {
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
      };
      document.addEventListener("click", function (e2) {
        var ctx2 = root.querySelector(".yrp-context");
        if (ctx2 && !ctx2.hidden && !ctx2.contains(e2.target)) ctx2.hidden = true;
      }, { once: true });
      document.addEventListener("keydown", function esc(ev) {
        if ((ev.code === "Escape") || ((ev.key || "").toLowerCase() === "escape")) {
          var c = root.querySelector(".yrp-context");
          if (c && !c.hidden) c.hidden = true;
          document.removeEventListener("keydown", esc);
        }
      });
    });

    ["mousemove", "pointermove", "mouseenter", "touchstart"].forEach(function (evName) {
      root.addEventListener(evName, function () { try { root.focus(); } catch (_) {} showControls(); }, { passive: true });
      video && video.addEventListener(evName, showControls, { passive: true });
      centerPlay && centerPlay.addEventListener(evName, showControls, { passive: true });
    });

    function onDocMove(e) {
      var r = root.getBoundingClientRect();
      if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) showControls();
    }

    function updateFsHoverBinding() {
      try {
        if (document.fullscreenElement === root) {
          document.addEventListener("mousemove", onDocMove, { passive: true });
          document.addEventListener("pointermove", onDocMove, { passive: true });
        } else {
          document.removeEventListener("mousemove", onDocMove);
          document.removeEventListener("pointermove", onDocMove);
        }
      } catch (_) {}
    }

    document.addEventListener("fullscreenchange", updateFsHoverBinding);
    updateFsHoverBinding();

    function handleHotkey(e) {
      var t = e.target, tag = t && t.tagName ? t.tagName.toUpperCase() : "";
      if (t && (t.isContentEditable || tag === "INPUT" || tag === "TEXTAREA")) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var code = e.code, key = (e.key || "").toLowerCase();

      if (code === "Space" || code === "Enter" || code === "NumpadEnter" || code === "MediaPlayPause" || code === "KeyK" || key === "k") { playToggle(); e.preventDefault(); return; }
      if (code === "ArrowLeft" || key === "arrowleft" || code === "KeyJ" || key === "j") { video.currentTime = clamp((video.currentTime || 0) - 5, 0, duration || 0); e.preventDefault(); return; }
      if (code === "ArrowRight" || key === "arrowright" || code === "KeyL" || key === "l") { video.currentTime = clamp((video.currentTime || 0) + 5, 0, duration || 0); e.preventDefault(); return; }
      if (code === "KeyM" || key === "m") { setMutedToggle(); e.preventDefault(); return; }
      if (code === "KeyF" || key === "f") {
        if (document.fullscreenElement) document.exitFullscreen().catch(function () {});
        else root.requestFullscreen && root.requestFullscreen().catch(function () {});
        e.preventDefault(); return;
      }
      if (code === "KeyT" || key === "t") { btnTheater && btnTheater.click(); e.preventDefault(); return; }
      if (code === "KeyI" || key === "i") { toggleMini(); e.preventDefault(); return; }
      if (code === "KeyA" || key === "a") { btnAutoplay && btnAutoplay.click(); e.preventDefault(); return; }
      if (code === "KeyC" || key === "c") { btnSubtitles && !btnSubtitles.disabled && btnSubtitles.click(); e.preventDefault(); return; }
      if (code === "Escape" || key === "escape") { hideMenus(); return; }
    }

    document.addEventListener("keydown", handleHotkey);
    setTimeout(adjustWidthByAspect, 200);
  }

  function initAll() {
    var NAME = detectPlayerName();
    var BASE = "/static/players/" + NAME;
    var hosts = document.querySelectorAll('.player-host[data-player="' + NAME + '"]');
    if (!hosts.length) return;
    fetch(BASE + "/templates/player.html", { credentials: "same-origin" })
      .then(r => r.text())
      .then(function (html) { for (var i = 0; i < hosts.length; i++) mountOne(hosts[i], html, BASE); })
      .catch(function () {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initAll);
  else initAll();
})();