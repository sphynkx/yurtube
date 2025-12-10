// WebVTT editor sync with "Follow player time" toggle.
// Rules:
// - When Follow is ON: editor auto-scrolls and highlights active cue; clicking a cue seeks the player.
// - When Follow is OFF: editor does NOT follow player; player time changes do NOT move editor; clicking in editor does NOT control player.

(function () {
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    function qs(id){ return document.getElementById(id); }

    var ta = qs("vtt-textarea");
    var wrap = qs("vtt-editor-wrap");
    var hi = qs("vtt-highlight");
    var playerWrap = qs("editor-player-wrap");
    var followChk = qs("vtt-follow-chk");

    if (!ta || !wrap || !hi || !playerWrap || !followChk) return;

    var followMode = !!followChk.checked;

    // line height detection
    var lh = parseFloat(getComputedStyle(ta).lineHeight || "0");
    if (!lh || isNaN(lh)) lh = 18;

    function parseTimeToSeconds(s) {
      try {
        var parts = String(s).trim().split(":");
        var h = 0, m = 0, sec = 0;
        if (parts.length === 3) {
          h = parseInt(parts[0], 10) || 0;
          m = parseInt(parts[1], 10) || 0;
          sec = parseFloat(parts[2]) || 0;
        } else if (parts.length === 2) {
          m = parseInt(parts[0], 10) || 0;
          sec = parseFloat(parts[1]) || 0;
        } else {
          sec = parseFloat(parts[0]) || 0;
        }
        return h * 3600 + m * 60 + sec;
      } catch (e) { return 0; }
    }

    function findCueRanges(text) {
      var lines = text.split(/\r?\n/);
      var ranges = [];
      for (var i = 0; i < lines.length; i++) {
        var L = lines[i];
        if (L.indexOf("-->") !== -1) {
          var seg = L.split("-->");
          var startStr = seg[0].trim().split(" ")[0];
          var endStr = seg[1].trim().split(" ")[0];
          var start = parseTimeToSeconds(startStr);
          var end = parseTimeToSeconds(endStr);
          var j = i + 1;
          while (j < lines.length && lines[j].trim() !== "") j++;
          ranges.push({ start: start, end: end, lineStartIdx: i, lineEndIdx: j - 1 });
        }
      }
      return { lines: lines, ranges: ranges };
    }

    function nearestCueIndex(ranges, t) {
      var best = -1, bestDist = 1e9;
      for (var k = 0; k < ranges.length; k++) {
        var r = ranges[k];
        var dist = 0;
        if (t < r.start) dist = r.start - t;
        else if (t > r.end) dist = t - r.end;
        else dist = 0;
        if (dist < bestDist) { bestDist = dist; best = k; }
      }
      return best;
    }

    function firstVisibleLine() { return Math.floor((ta.scrollTop || 0) / lh); }
    function visibleLineCount() { return Math.max(1, Math.floor(ta.clientHeight / lh)); }

    function caretPosForLine(text, lineIdx) {
      var pos = 0, count = 0;
      while (count < lineIdx && pos < text.length) {
        var p = text.indexOf("\n", pos);
        if (p === -1) break;
        pos = p + 1;
        count++;
      }
      return pos;
    }

    function scrollToLine(lineIdx) {
      var desiredTop = Math.max(0, Math.round(lineIdx * lh - lh));
      ta.scrollTop = desiredTop;
    }

    function updateHighlight(lineStart, lineEnd) {
      var first = firstVisibleLine();
      var topLine = Math.max(0, lineStart - first);
      var linesOnScreen = visibleLineCount();
      var bottomLine = Math.min(lineEnd - first, linesOnScreen - 1);

      var topPx = topLine * lh;
      var heightLines = Math.max(1, (bottomLine - topLine + 1));
      var hPx = heightLines * lh;

      hi.style.transform = "translateY(" + Math.round(topPx) + "px)";
      hi.style.height = Math.round(hPx) + "px";
      hi.style.opacity = "1";
    }

    var parsed = findCueRanges(ta.value);
    var lastIdx = -1;

    // Time sources
    var nativeVideo = playerWrap.querySelector("video");
    var bridgeLastTime = 0;
    var BRIDGE_TAG = "yrp-time";

    function getCurrentTime() {
      if (nativeVideo && !isNaN(nativeVideo.currentTime)) return nativeVideo.currentTime || 0;
      try {
        if (window.player && typeof window.player.currentTime === "function") {
          var ct = window.player.currentTime();
          if (typeof ct === "number") return ct || 0;
        }
      } catch (e) {}
      return bridgeLastTime || 0;
    }

    function syncEditorToPlayer(forceScroll) {
      // If follow is OFF and we didn't explicitly request to force scroll (user action), do nothing at all.
      if (!followMode && !forceScroll) return;

      var t = getCurrentTime();
      var idx = nearestCueIndex(parsed.ranges, t);
      if (idx === -1) return;

      var r = parsed.ranges[idx];

      // Only scroll when followMode is ON or explicitly forced (user clicked)
      if (forceScroll || followMode) {
        var first = firstVisibleLine();
        var last = first + visibleLineCount() - 1;
        if (r.lineStartIdx < first || r.lineStartIdx > last) {
          scrollToLine(r.lineStartIdx);
        }
      }
      updateHighlight(r.lineStartIdx, r.lineEndIdx);
      lastIdx = idx;
    }

    // Checkbox control — update internal flag
    followChk.addEventListener("change", function () {
      followMode = !!followChk.checked;
      // When turning OFF, leave current highlight but stop any automatic sync
      if (!followMode) return;
      // When turning ON, resync immediately
      syncEditorToPlayer(true);
    });

    // Native events — never force scroll; they will be ignored when followMode=false
    if (nativeVideo) {
      nativeVideo.addEventListener("timeupdate", function () { syncEditorToPlayer(false); });
      nativeVideo.addEventListener("seeked", function () { syncEditorToPlayer(false); });
      nativeVideo.addEventListener("loadeddata", function () { syncEditorToPlayer(false); });
      nativeVideo.addEventListener("play", function () { syncEditorToPlayer(false); });
      nativeVideo.addEventListener("pause", function () { syncEditorToPlayer(false); });
    }

    // Custom player events
    try {
      if (window.player && typeof window.player.on === "function") {
        window.player.on("timeupdate", function () { syncEditorToPlayer(false); });
        window.player.on("seeked", function () { syncEditorToPlayer(false); });
        window.player.on("loadeddata", function () { syncEditorToPlayer(false); });
        window.player.on("play", function () { syncEditorToPlayer(false); });
        window.player.on("pause", function () { syncEditorToPlayer(false); });
      }
    } catch (e) {}

    // PostMessage bridge
    window.addEventListener("message", function (ev) {
      try {
        var data = ev && ev.data;
        if (!data) return;
        if (typeof data === "string") {
          try { data = JSON.parse(data); } catch (_) {}
        }
        if (data && (data.type === BRIDGE_TAG || data.event === BRIDGE_TAG)) {
          var ct = data.currentTime;
          if (typeof ct === "number") {
            bridgeLastTime = ct;
            syncEditorToPlayer(false); // ignored when followMode=false
          }
        }
      } catch (e) {}
    });

    // Polling fallback — respect followMode; ignored when followMode=false
    var pollTimer = setInterval(function () { syncEditorToPlayer(false); }, 200);

    // User scroll: keep highlight consistent
    ta.addEventListener("scroll", function () {
      if (lastIdx >= 0 && parsed.ranges[lastIdx]) {
        var r = parsed.ranges[lastIdx];
        updateHighlight(r.lineStartIdx, r.lineEndIdx);
      }
    });

    window.addEventListener("resize", function () {
      lh = parseFloat(getComputedStyle(ta).lineHeight || "0") || lh;
      if (lastIdx >= 0 && parsed.ranges[lastIdx]) {
        var r = parsed.ranges[lastIdx];
        updateHighlight(r.lineStartIdx, r.lineEndIdx);
      }
    });

    // Re-parse on edit
    ta.addEventListener("input", function () {
      parsed = findCueRanges(ta.value);
      lastIdx = -1;
      // Do not force scroll on typing; if followMode=true, highlight will update in next tick
      syncEditorToPlayer(false);
    });

    // Click in editor — only control player when followMode=true
    ta.addEventListener("click", function () {
      var text = ta.value;
      var pos = ta.selectionStart || 0;
      var lineIdx = 0, i = 0;
      while (true) {
        var p = text.indexOf("\n", i);
        if (p === -1 || p >= pos) break;
        lineIdx++;
        i = p + 1;
      }
      var lines = parsed.lines;
      if (lines[lineIdx] && lines[lineIdx].indexOf("-->") !== -1) {
        var seg = lines[lineIdx].split("-->");
        var startStr = seg[0].trim().split(" ")[0];
        var start = parseTimeToSeconds(startStr);

        if (followMode) {
          if (nativeVideo) {
            try { nativeVideo.currentTime = start; nativeVideo.pause(); } catch (e) {}
          }
          try {
            if (window.player && typeof window.player.currentTime === "function") {
              window.player.currentTime(start);
            }
          } catch (e) {}
        }

        // Keep viewport around the clicked cue; force scroll only if followMode=true
        var caretPos = caretPosForLine(text, lineIdx);
        try { ta.setSelectionRange(caretPos, caretPos); } catch (e) {}
        if (followMode) {
          scrollToLine(lineIdx);
          syncEditorToPlayer(true);
        } else {
          // Just highlight clicked cue without moving player
          var r = parsed.ranges[lineIdx] || parsed.ranges[nearestCueIndex(parsed.ranges, start)];
          if (r) updateHighlight(r.lineStartIdx, r.lineEndIdx);
        }
      }
    });

    // Initial sync — if followMode=true, sync; else do nothing
    setTimeout(function () {
      if (followMode) syncEditorToPlayer(true);
    }, 250);

    // Cleanup
    window.addEventListener("beforeunload", function () {
      try { clearInterval(pollTimer); } catch (e) {}
      if (nativeVideo) {
        nativeVideo.removeEventListener("timeupdate", syncEditorToPlayer);
        nativeVideo.removeEventListener("seeked", syncEditorToPlayer);
        nativeVideo.removeEventListener("loadeddata", syncEditorToPlayer);
        nativeVideo.removeEventListener("play", syncEditorToPlayer);
        nativeVideo.removeEventListener("pause", syncEditorToPlayer);
      }
    });
  });
})();