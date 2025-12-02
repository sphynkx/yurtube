(function () {
  var GRACE_MS_AFTER_ACTIVE = 12000;
  var MIN_POLL_MS = 2500;
  var DEFAULT_POLL_MS = 6000;

  var last = {
    status: "idle",
    statusTs: 0,
    percent: -1,
    percentTs: 0
  };

  function mapStatusDisplay(s, hasVtt) {
    var label = "unknown";
    var color = "#555";
    switch (s) {
      case "start":
      case "wait":
        label = "queued";      color = "#0070cc"; break;
      case "process":
        label = "processing";  color = "#0070cc"; break;
      case "done":
        label = "done";        color = "#0a8a66"; break;
      case "fail":
        label = "error";       color = "#a00";    break;
      case "idle":
        label = "idle";        color = "#888";    break;
      default:
        label = hasVtt ? "done" : "unknown";
        color = hasVtt ? "#0a8a66" : "#a00";
        break;
    }
    return { label: label, color: color };
  }

  function normalizeRelVtt(relVtt, videoId) {
    try {
      if (!relVtt) return relVtt;
      relVtt = String(relVtt).replace(/^\/*/, "");
      var vid = String(videoId || "");
      if (vid) {
        var parts = relVtt.split("/");
        var idx = parts.indexOf(vid);
        if (idx >= 0) {
          var rest = parts.slice(idx + 1).join("/");
          if (rest) relVtt = rest;
        }
      }
      var capIdx = relVtt.indexOf("captions/");
      if (capIdx >= 0) relVtt = relVtt.slice(capIdx);
      return relVtt;
    } catch (_) {
      return relVtt;
    }
  }

  function fetchStatus(videoId) {
    var url = "/internal/ytcms/captions/status?video_id=" + encodeURIComponent(videoId);
    return fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .catch(function () { return null; });
  }

  function renderStatusText(el, s, hasVtt, percent) {
    var mapped = mapStatusDisplay(s, hasVtt);
    var pctStr = (s === "process" && typeof percent === "number" && percent >= 0)
      ? " (" + Math.min(100, Math.max(0, Math.round(percent))) + "%)"
      : "";
    el.textContent = "Captions: " + mapped.label + pctStr;
    el.style.color = mapped.color;
  }

  function findCaptionsSectionRoot() {
    var headers = document.querySelectorAll("h2");
    for (var i = 0; i < headers.length; i++) {
      var h = headers[i];
      var txt = (h.textContent || "").trim().toLowerCase();
      if (txt === "captions") {
        var sec = h.closest("section");
        if (sec) return sec;
        return h.parentElement || h;
      }
    }
    return null;
  }

  function ensureCaptionsList(section) {
    var list = section.querySelector("ul");
    if (!list) {
      list = document.createElement("ul");
      list.style.listStyle = "none";
      list.style.paddingLeft = "0";
      list.style.margin = "0 0 18px";
      var h2 = section.querySelector("h2");
      if (h2 && h2.nextSibling) {
        section.insertBefore(list, h2.nextSibling);
      } else {
        section.appendChild(list);
      }
    }
    return list;
  }

  function removeEmptyParagraph(section) {
    var ps = section.querySelectorAll("p");
    for (var i = 0; i < ps.length; i++) {
      var t = (ps[i].textContent || "").trim().toLowerCase();
      if (t === "no caption files found.") {
        try { ps[i].remove(); } catch (_) {}
      }
    }
  }

  function upsertCaptionEntry(list, videoId, relVtt) {
    var items = list.querySelectorAll("li");
    for (var i = 0; i < items.length; i++) {
      var codeEl = items[i].querySelector("code");
      var codeTxt = codeEl ? (codeEl.textContent || "").trim() : "";
      if (!codeTxt) continue;
      if (codeTxt === relVtt || codeTxt.indexOf(relVtt) >= 0 || relVtt.indexOf(codeTxt) >= 0) {
        var editHref = "/manage/video/" + encodeURIComponent(videoId) + "/vtt/edit?rel_vtt=" + encodeURIComponent(relVtt);
        var dlHref   = "/manage/video/" + encodeURIComponent(videoId) + "/vtt/download?rel_vtt=" + encodeURIComponent(relVtt);
        var edit = items[i].querySelector("a[href*='/vtt/edit']");
        var dl   = items[i].querySelector("a[href*='/vtt/download']");
        if (edit) edit.href = editHref; else {
          var e = document.createElement("a");
          e.href = editHref; e.style.marginLeft = "8px"; e.textContent = "Edit";
          items[i].appendChild(e);
        }
        if (dl) dl.href = dlHref; else {
          var d = document.createElement("a");
          d.href = dlHref; d.style.marginLeft = "8px"; d.textContent = "Download";
          items[i].appendChild(d);
        }
        if (codeEl) codeEl.textContent = relVtt;
        for (var k = items.length - 1; k >= 0; k--) {
          if (items[k] !== items[i]) {
            var ce = items[k].querySelector("code");
            var ct = ce ? (ce.textContent || "").trim() : "";
            if (ct === relVtt || ct.indexOf(relVtt) >= 0 || relVtt.indexOf(ct) >= 0) {
              try { items[k].remove(); } catch (_) {}
            }
          }
        }
        return;
      }
    }
    var li = document.createElement("li");
    li.style.marginBottom = "4px";
    var code = document.createElement("code");
    code.textContent = relVtt;
    var edit = document.createElement("a");
    edit.href = "/manage/video/" + encodeURIComponent(videoId) + "/vtt/edit?rel_vtt=" + encodeURIComponent(relVtt);
    edit.style.marginLeft = "8px";
    edit.textContent = "Edit";
    var dl = document.createElement("a");
    dl.href = "/manage/video/" + encodeURIComponent(videoId) + "/vtt/download?rel_vtt=" + encodeURIComponent(relVtt);
    dl.style.marginLeft = "8px";
    dl.textContent = "Download";
    li.appendChild(code);
    li.appendChild(edit);
    li.appendChild(dl);
    list.appendChild(li);
  }

  function ensureEmptyParagraphIfNeeded(section) {
    var list = section.querySelector("ul");
    var hasItems = !!(list && list.querySelector("li"));
    if (!hasItems) {
      var exists = false;
      var ps = section.querySelectorAll("p");
      for (var i = 0; i < ps.length; i++) {
        var t = (ps[i].textContent || "").trim().toLowerCase();
        if (t === "no caption files found.") { exists = true; break; }
      }
      if (!exists) {
        var emptyP = document.createElement("p");
        emptyP.style.margin = "6px 0 12px";
        emptyP.textContent = "No caption files found.";
        var h2 = section.querySelector("h2");
        if (h2 && h2.nextSibling) {
          section.insertBefore(emptyP, h2.nextSibling);
        } else {
          section.appendChild(emptyP);
        }
      }
      if (list) { try { list.remove(); } catch(_) {} }
    }
  }

  function updateCaptionsList(videoId, rawRelVtt) {
    try {
      var section = findCaptionsSectionRoot();
      if (!section) return;
      var relVtt = normalizeRelVtt(rawRelVtt, videoId);
      if (relVtt) {
        removeEmptyParagraph(section);
        var list = ensureCaptionsList(section);
        upsertCaptionEntry(list, videoId, relVtt);
      } else {
        ensureEmptyParagraphIfNeeded(section);
      }
    } catch (_) {}
  }

  // Add some gisteresis for  UI
  function stabilizeStatus(incomingStatus, incomingPercent) {
    var now = Date.now();
    if (typeof incomingPercent === "number" && incomingPercent > 0 && incomingPercent < 100) {
      last.percent = incomingPercent;
      last.percentTs = now;
    }
    if (incomingStatus && incomingStatus !== last.status) {
      last.status = incomingStatus;
      last.statusTs = now;
    }

    var s = incomingStatus || "idle";
    if (s === "idle") {
      if (last.percent > 0 && last.percent < 100 && (now - last.percentTs) <= GRACE_MS_AFTER_ACTIVE) {
        return "process";
      }
      if ((last.status === "process" || last.status === "wait") && (now - last.statusTs) <= GRACE_MS_AFTER_ACTIVE) {
        return "wait";
      }
    }
    return s;
  }

  function start(el, videoId, intervalMs) {
    if (!el || !videoId) return;

    function tick() {
      fetchStatus(videoId).then(function (d) {
        if (!d || !d.ok) {
          renderStatusText(el, "unknown", false, -1);
          return;
        }
        var sRaw = (d.status || "idle").toLowerCase();
        var pctRaw = (typeof d.percent === "number") ? d.percent : -1;
        var hasVtt = !!d.has_vtt;

        var s = stabilizeStatus(sRaw, pctRaw);

        renderStatusText(el, s, hasVtt, pctRaw);
        updateCaptionsList(videoId, hasVtt ? d.rel_vtt : null);
      });
    }

    tick();
    var ms = Math.max(MIN_POLL_MS, parseInt(intervalMs || DEFAULT_POLL_MS, 10));
    var timer = setInterval(tick, ms);
    window.addEventListener("beforeunload", function () { try { clearInterval(timer); } catch (_) {} });
  }

  // DirtyHack: set `processing (0%)` just button pressed
  function setImmediateProcessing(el) {
    if (!el) return;
    var now = Date.now();
    last.status = "process";
    last.statusTs = now;
    last.percent = 0;
    last.percentTs = now;
    renderStatusText(el, "process", false, 0);
  }

  window.CaptionsStatus = {
    init: function (opts) {
      opts = opts || {};
      start(opts.el || document.getElementById("captions-status"), opts.videoId, opts.intervalMs);
    },
    setImmediateProcessing: setImmediateProcessing
  };
})();