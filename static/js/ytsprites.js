(function () {
  const startForm = document.getElementById("ytsprites-start-form");
  const retryForm = document.getElementById("ytms-retry-form");

  const startStatusEl = document.getElementById("ytsprites-start-status");
  const retryStatusEl = document.getElementById("ytms-retry-status");

  function setText(el, v) { if (el) el.textContent = v; }
  function clearAll() {
    setText(startStatusEl, "");
    setText(retryStatusEl, "");
  }

  window.addEventListener("pageshow", clearAll);
  document.addEventListener("DOMContentLoaded", function () {
    clearAll();
    // extra: clear again next tick (some browsers restore text after DOMContentLoaded)
    setTimeout(clearAll, 0);
  });

  function stateLabel(state) {
    switch (Number(state)) {
      case 1: return "submitted";
      case 2: return "queued";
      case 3: return "processing";
      case 4: return "done";
      case 5: return "failed";
      case 6: return "canceled";
      default: return "unknown";
    }
  }

  async function pollProgress(videoId, statusEl, btn) {
    const started = Date.now();
    const maxMs = 60 * 60 * 1000;

    while (true) {
      if ((Date.now() - started) > maxMs) {
        setText(statusEl, "Still running (timeout).");
        if (btn) btn.removeAttribute("disabled");
        return;
      }

      try {
        const url = "/internal/ytsprites/thumbnails/progress?video_id=" + encodeURIComponent(videoId);
        const r = await fetch(url, { credentials: "same-origin" });
        const j = await r.json();

        if (!j || !j.ok || !j.active) {
          // show nothing until server actually started tracking a job
          setText(statusEl, "");
        } else {
          const st = stateLabel(j.state);
          const pct = (typeof j.percent === "number" && j.percent >= 0)
            ? Math.min(100, Math.max(0, Math.round(j.percent)))
            : null;
          const msg = (j.message || "").trim();
          const pctTxt = (pct !== null) ? (" " + pct + "%") : "";
          const msgTxt = msg ? (" — " + msg) : "";
          setText(statusEl, st + pctTxt + msgTxt);

          if (st === "done") {
            setText(statusEl, "done. reloading…");
            // reload more reliably
            window.location.href = window.location.href;
            return;
          }
          if (st === "failed" || st === "canceled") {
            if (btn) btn.removeAttribute("disabled");
            return;
          }
        }
      } catch (e) {
        // ignore
      }

      await new Promise(res => setTimeout(res, 800));
    }
  }

  function fireRequestAndTrack(formEl, statusEl) {
    const videoId = (formEl.getAttribute("data-video-id") || "").trim();
    const btn = formEl.querySelector("button[type=submit]");

    if (btn) btn.setAttribute("disabled", "disabled");
    setText(statusEl, "starting…");

    const fd = new FormData(formEl);

    // fire request but do not await it (it may take long)
    fetch(formEl.action, { method: "POST", body: fd, credentials: "same-origin" })
      .then(async (resp) => {
        if (!resp.ok) {
          let msg = "error";
          try {
            const ct = resp.headers.get("content-type") || "";
            if (ct.includes("application/json")) {
              const j = await resp.json();
              msg = j && (j.error || j.message) ? (j.error || j.message) : msg;
            } else {
              msg = await resp.text();
            }
          } catch (_) {}
          setText(statusEl, "error: " + String(msg || "").slice(0, 160));
          if (btn) btn.removeAttribute("disabled");
        }
      })
      .catch(() => {
        setText(statusEl, "network error");
        if (btn) btn.removeAttribute("disabled");
      });

    // start polling progress endpoint immediately
    if (videoId) {
      pollProgress(videoId, statusEl, btn);
    } else {
      if (btn) btn.removeAttribute("disabled");
    }
  }

  if (startForm) {
    startForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      fireRequestAndTrack(startForm, startStatusEl);
    });
  }

  if (retryForm) {
    retryForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      fireRequestAndTrack(retryForm, retryStatusEl);
    });
  }
})();