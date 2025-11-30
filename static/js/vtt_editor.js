// WebVTT sync for the editor with "Follow player time" toggle.
// - Auto-scrolls to active cue and highlights it when follow=true.
// - User can scroll freely when follow=false (editor becomes leading).
// - Click on a cue time line jumps the player to its start.

(function () {
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var ta = document.getElementById("vtt-textarea");
    var wrap = document.getElementById("vtt-editor-wrap");
    var hi = document.getElementById("vtt-highlight");
    var playerWrap = document.getElementById("editor-player-wrap");
    var followChk = document.getElementById("vtt-follow-chk");
    if (!ta || !wrap || !hi || !playerWrap || !followChk) return;

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

    function firstVisibleLine() {
      return Math.floor((ta.scrollTop || 0) / lh);
    }

    function visibleLineCount() {
      return Math.max(1, Math.floor(ta.clientHeight / lh));
    }

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

    // Follow toggle: checked by default (controlled in template)
    function followEnabled() {
      return !!followChk.checked;
    }

    // Detect native <video> if present
    var nativeVideo = playerWrap.querySelector("video");

    function getCurrentTime() {
      if (nativeVideo && !isNaN(nativeVideo.currentTime)) return nativeVideo.currentTime || 0;
      try {
        if (window.player && typeof window.player.currentTime === "function") {
          return window.player.currentTime() || 0;
        }
      } catch (e) {}
      return 0;
    }

    function syncEditorToPlayer(force) {
      var t = getCurrentTime();
      var idx = nearestCueIndex(parsed.ranges, t);
      if (idx === -1) return;

      var r = parsed.ranges[idx];

      // Only auto-scroll when follow=true or force requested
      if (force || followEnabled()) {
        var first = firstVisibleLine();
        var last = first + visibleLineCount() - 1;
        if (r.lineStartIdx < first || r.lineStartIdx > last) {
          scrollToLine(r.lineStartIdx);
        }
      }
      updateHighlight(r.lineStartIdx, r.lineEndIdx);
      lastIdx = idx;
    }

    // Attach native events
    if (nativeVideo) {
      nativeVideo.addEventListener("timeupdate", function () { syncEditorToPlayer(false); });
      nativeVideo.addEventListener("seeked", function () { syncEditorToPlayer(true); });
      nativeVideo.addEventListener("loadeddata", function () { syncEditorToPlayer(true); });
      nativeVideo.addEventListener("play", function () { syncEditorToPlayer(true); });
      nativeVideo.addEventListener("pause", function () { syncEditorToPlayer(true); });
    }

    // Custom player events
    try {
      if (window.player && typeof window.player.on === "function") {
        window.player.on("timeupdate", function () { syncEditorToPlayer(false); });
        window.player.on("seeked", function () { syncEditorToPlayer(true); });
        window.player.on("loadeddata", function () { syncEditorToPlayer(true); });
        window.player.on("play", function () { syncEditorToPlayer(true); });
        window.player.on("pause", function () { syncEditorToPlayer(true); });
      }
    } catch (e) {}

    // Polling fallback
    var pollTimer = setInterval(function () { syncEditorToPlayer(false); }, 150);

    // User scroll: do not fight; highlight still updates on next sync
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
      syncEditorToPlayer(true);
    });

    // Click to jump player when clicking a time range line (editor leads)
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

        if (nativeVideo) {
          try { nativeVideo.currentTime = start; nativeVideo.pause(); } catch (e) {}
        }
        try {
          if (window.player && typeof window.player.currentTime === "function") {
            window.player.currentTime(start);
          }
        } catch (e) {}

        // Keep viewport around the clicked cue regardless of follow toggle
        var caretPos = caretPosForLine(text, lineIdx);
        try { ta.setSelectionRange(caretPos, caretPos); } catch (e) {}
        scrollToLine(lineIdx);
        syncEditorToPlayer(true);
      }
    });

    // Initial sync
    setTimeout(function () { syncEditorToPlayer(true); }, 250);

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