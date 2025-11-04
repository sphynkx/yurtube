(function () {
  // Helpers
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

  // Mount a single host
  function mountOne(host, templateHTML) {
    host.innerHTML = templateHTML;

    var root = host.querySelector(".yrp-container");
    var video = root.querySelector(".yrp-video");
    var source = video.querySelector("source");

    var videoSrc = host.getAttribute("data-video-src") || "";
    var poster = host.getAttribute("data-poster-url") || "";
    var vid = host.getAttribute("data-video-id") || "";
    var subs = parseJSONAttr(host, "data-subtitles", []);
    var opts = parseJSONAttr(host, "data-options", {});

    if (source) source.setAttribute("src", videoSrc);
    if (poster) video.setAttribute("poster", poster);
    if (opts && opts.autoplay) video.setAttribute("autoplay", "");
    if (opts && opts.muted) video.setAttribute("muted", "");
    if (opts && opts.loop) video.setAttribute("loop", "");
    if (vid) root.setAttribute("data-video-id", vid);

    if (Array.isArray(subs)) {
      subs.forEach(function(t) {
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

    var startAt = 0;
    if (opts && typeof opts.start === "number" && opts.start > 0) startAt = Math.max(0, opts.start);

    wire(root, startAt);
  }

  // Wire behavior for a single player
  function wire(root, startAt) {
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

    var hideTimer = null;
    var seeking = false;
    var duration = 0;

    // PiP state bookkeeping
    var pipInSystem = false;
    var pipWasPlayingOrig = false;
    var pipWasMutedOrig = false;
    var pipUserState = null; // last play/pause inside PiP (true=playing, false=paused, null=unknown)

    // Pop-out fallback window (kept but does not affect main playback state)
    var popWin = null;
    var popWinTimer = null;

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
      if (btnVol) btnVol.textContent = label;
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

    // Enter standard Video PiP preserving paused/mute state (no forced play)
    function enterVideoPiP() {
      pipWasPlayingOrig = !video.paused;
      pipWasMutedOrig = !!video.muted;
      pipUserState = null;

      var needTempPlay = video.paused;
      var prevMuted = video.muted;

      var startPlayPromise = Promise.resolve();
      if (needTempPlay) {
        video.muted = true;
        startPlayPromise = video.play().catch(function(){});
      }

      return startPlayPromise.then(function () {
        return video.requestPictureInPicture();
      }).catch(function(){ /* ignore */ }).then(function(){
        if (needTempPlay) {
          video.pause();
          video.muted = prevMuted;
        }
      });
    }

    // Toggle mini: prefer Video PiP, else pop-out; never touch playing/paused on toggle
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
        // Fallback: pop-out embed window (keeps main playback state intact)
        if (popWin && !popWin.closed) { try { popWin.close(); } catch(e) {} return; }
        var vid = root.getAttribute("data-video-id") || "";
        var url = (window.location.origin || "") + "/embed?v=" + encodeURIComponent(vid) + "&autoplay=1&muted=1";
        var w = Math.round(Math.min(640, window.innerWidth * 0.6));
        var h = Math.round(w * 9 / 16);
        var left = Math.max(0, Math.floor((window.screen.width - w) / 2));
        var top = Math.max(0, Math.floor((window.screen.height - h) / 2));
        var feat = "popup=yes,resizable=yes,scrollbars=no,menubar=no,toolbar=no,location=no,status=no"
                 + ",width=" + w + ",height=" + h + ",left=" + left + ",top=" + top;
        popWin = window.open(url, "yurtube-popout-" + vid, feat);
        if (popWinTimer) clearInterval(popWinTimer);
        popWinTimer = setInterval(function(){
          if (!popWin || popWin.closed) {
            clearInterval(popWinTimer); popWinTimer = null;
            setTimeout(function(){ adjustWidthByAspect(); }, 0);
          }
        }, 1000);
      } catch (ex) {}
    }

    // Metadata and initial layout
    video.addEventListener("loadedmetadata", function () {
      if (startAt && startAt > 0) {
        try { video.currentTime = Math.min(startAt, Math.floor(video.duration || startAt)); } catch (e) {}
      }
      setTimeout(adjustWidthByAspect, 0);
      updateTimes();
      updateProgress();
    });
    window.addEventListener("resize", function(){ adjustWidthByAspect(); });

    // Playback state
    video.addEventListener("timeupdate", function(){ updateTimes(); updateProgress(); });
    video.addEventListener("progress", function(){ updateProgress(); });
    video.addEventListener("play", function(){
      root.classList.add("playing");
      showControls();
      if (pipInSystem) pipUserState = true;
    });
    video.addEventListener("pause", function(){
      root.classList.remove("playing");
      showControls();
      if (pipInSystem) pipUserState = false;
    });

    // System PiP enter/leave
    video.addEventListener("enterpictureinpicture", function(){
      pipInSystem = true;
      root.classList.add("pip");
      if (!pipWasPlayingOrig && !video.paused) {
        video.pause();
        video.muted = pipWasMutedOrig;
        pipUserState = false;
      }
    });
    video.addEventListener("leavepictureinpicture", function(){
      pipInSystem = false;
      root.classList.remove("pip");
      if (pipUserState === true) {
        video.play().catch(function(){});
      } else if (pipUserState === false) {
        video.pause();
      } else {
        if (pipWasPlayingOrig) video.play().catch(function(){});
        else video.pause();
      }
      video.muted = pipWasMutedOrig;
      pipUserState = null;
    });

    // Media Session: hw-buttons
    if ("mediaSession" in navigator) {
      try {
        navigator.mediaSession.setActionHandler("play", function(){ video.play().catch(function(){}); });
        navigator.mediaSession.setActionHandler("pause", function(){ video.pause(); });
        navigator.mediaSession.setActionHandler("seekbackward", function(){ video.currentTime = clamp((video.currentTime||0) - 5, 0, duration||0); });
        navigator.mediaSession.setActionHandler("seekforward", function(){ video.currentTime = clamp((video.currentTime||0) + 5, 0, duration||0); });
        navigator.mediaSession.setActionHandler("stop", function(){ video.pause(); });
      } catch (e) {}
    }

    // Click to toggle play
    video.addEventListener("click", function(){ playToggle(); });

    // Auto-hide controls
    root.addEventListener("mousemove", showControls, { passive: true });
    root.addEventListener("pointermove", showControls, { passive: true });
    root.addEventListener("mouseleave", function () {
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(function () { root.classList.add("autohide"); }, 600);
    });

    // Buttons
    if (centerPlay) centerPlay.addEventListener("click", playToggle);
    if (btnPlay) btnPlay.addEventListener("click", playToggle);
    if (btnPrev) btnPrev.addEventListener("click", function(){ root.dispatchEvent(new CustomEvent("yrp-prev",{bubbles:true})); });
    if (btnNext) btnNext.addEventListener("click", function(){ root.dispatchEvent(new CustomEvent("yrp-next",{bubbles:true})); });

    // Volume: hover shows slider (CSS). Click => mute/unmute. Wheel => volume up/down.
    if (btnVol) {
      btnVol.addEventListener("click", function(e){
        e.preventDefault();
        e.stopPropagation();
        setMutedToggle();
        showControls();
        root.classList.add("vol-open");
        setTimeout(function(){ root.classList.remove("vol-open"); }, 1200);
      });
    }
    if (volSlider) {
      volSlider.addEventListener("input", function(){
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

    // Seeking on progress rail
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

    // Settings menu
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
      });
      menu.addEventListener("click", function (e) {
        var target = e.target;
        if (target && target.classList.contains("yrp-menu-item")) {
          var sp = parseFloat(target.getAttribute("data-speed") || "NaN");
          if (!isNaN(sp)) {
            video.playbackRate = sp;
            hideMenus();
          }
        }
      });
      document.addEventListener("click", function (e) {
        if (!menu.hidden && !menu.contains(e.target) && e.target !== btnSettings) hideMenus();
      });
    }

    // Theater toggle: expand inside page column
    if (btnTheater) {
      btnTheater.addEventListener("click", function () {
        root.classList.toggle("yrp-theater");
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
    }

    // Fullscreen
    if (btnFull) {
      btnFull.addEventListener("click", function () {
        if (document.fullscreenElement) {
          document.exitFullscreen().catch(function (){});
        } else {
          root.requestFullscreen && root.requestFullscreen().catch(function (){});
        }
      });
    }

    // Mini (PiP) button
    if (btnPip) {
      btnPip.addEventListener("click", function(e){
        e.preventDefault();
        e.stopPropagation();
        toggleMini();
      });
    }

    // Context menu (right click)
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
          var src = window.location.origin + "/embed?v=" + encodeURIComponent(vid || "");
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

    // Keyboard shortcuts (global; layout-agnostic via e.code)
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
          code === "KeyK" || key === "k" || key === "к") {
        playToggle(); e.preventDefault(); return;
      }
      if (code === "ArrowLeft" || key === "arrowleft" || code === "KeyJ" || key === "j" || key === "л") {
        video.currentTime = clamp((video.currentTime || 0) - 5, 0, duration || 0); e.preventDefault(); return;
      }
      if (code === "ArrowRight" || key === "arrowright" || code === "KeyL" || key === "l" || key === "д") {
        video.currentTime = clamp((video.currentTime || 0) + 5, 0, duration || 0); e.preventDefault(); return;
      }
      if (code === "KeyM" || key === "m" || key === "ь") { setMutedToggle(); e.preventDefault(); return; }
      if (code === "KeyF" || key === "f" || key === "а") { btnFull && btnFull.click(); e.preventDefault(); return; }
      if (code === "KeyT" || key === "t" || key === "е") { btnTheater && btnTheater.click(); e.preventDefault(); return; }
      if (code === "KeyI" || key === "i" || key === "ш") { toggleMini(); e.preventDefault(); return; }
      if (code === "Escape" || key === "escape") { hideMenus(); return; }
    }
    document.addEventListener("keydown", handleHotkey);

    // Final pass after layout settles
    setTimeout(adjustWidthByAspect, 200);
  }

  // Init all hosts on the page
  function initAll() {
    var hosts = document.querySelectorAll(".player-host[data-player='yurtube']");
    if (hosts.length === 0) return;

    fetch("/static/players/yurtube/templates/player.html", { credentials: "same-origin" })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        for (var i = 0; i < hosts.length; i++) {
          mountOne(hosts[i], html);
        }
      })
      .catch(function () { /* ignore */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();