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

    // Compute minimal width needed for controls (left + right)
    function measureControlsMinWidth() {
      var lw = leftGrp ? leftGrp.getBoundingClientRect().width : 0;
      var rw = rightGrp ? rightGrp.getBoundingClientRect().width : 0;
      var pad = 24; // small gap
      var minW = Math.ceil(lw + rw + pad);
      if (!isFinite(minW) || minW <= 0) minW = 480;
      return minW;
    }

    // Constrain width by aspect and minimal controls width
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
    video.addEventListener("play", function(){ root.classList.add("playing"); showControls(); });
    video.addEventListener("pause", function(){ root.classList.remove("playing"); showControls(); });

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

    // Volume: hover shows slider (CSS). Click toggles mute/unmute.
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
          // Clear inline widths to let CSS stretch
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
      video.addEventListener("enterpictureinpicture", function(){ root.classList.add("pip"); });
      video.addEventListener("leavepictureinpicture", function(){ root.classList.remove("pip"); });
      btnPip.addEventListener("click", function(e){
        e.preventDefault();
        e.stopPropagation();
        try {
          if ("pictureInPictureEnabled" in document && video.requestPictureInPicture && !video.disablePictureInPicture) {
            if (document.pictureInPictureElement === video) {
              document.exitPictureInPicture().catch(function(){});
            } else {
              video.requestPictureInPicture().catch(function(){});
            }
          } else {
            // Fallback: pop-out embed window
            var vid = root.getAttribute("data-video-id") || "";
            var url = (window.location.origin || "") + "/embed?v=" + encodeURIComponent(vid) + "&autoplay=1&muted=1";
            var w = Math.round(Math.min(640, window.innerWidth * 0.6));
            var h = Math.round(w * 9 / 16);
            var left = Math.max(0, Math.floor((window.screen.width - w) / 2));
            var top = Math.max(0, Math.floor((window.screen.height - h) / 2));
            var feat = "popup=yes,resizable=yes,scrollbars=no,menubar=no,toolbar=no,location=no,status=no"
                     + ",width=" + w + ",height=" + h + ",left=" + left + ",top=" + top;
            window.open(url, "yurtube-popout-" + vid, feat);
          }
        } catch (ex) {}
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
          if (document.pictureInPictureEnabled && video.requestPictureInPicture) {
            video.requestPictureInPicture().catch(function(){});
          }
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
        if (!ctx.hidden && !ctx.contains(e2.target)) ctx.hidden = true;
      }, { once: true });
    });

    // Keyboard shortcuts (minimal)
    root.addEventListener("keydown", function (e) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
      var k = e.key.toLowerCase();
      if (k === " " || k === "k") { if (video.paused) video.play().catch(function(){}); else video.pause(); e.preventDefault(); }
      else if (k === "arrowleft" || k === "j") { video.currentTime = clamp((video.currentTime || 0) - 5, 0, duration || 0); }
      else if (k === "arrowright" || k === "l") { video.currentTime = clamp((video.currentTime || 0) + 5, 0, duration || 0); }
      else if (k === "m") { setMutedToggle(); }
      else if (k === "f") { btnFull && btnFull.click(); }
      else if (k === "t") { btnTheater && btnTheater.click(); }
      showControls();
    });

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