// Media tools page helper: enqueue sprites generation and poll status.
(function () {
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  const form =
    document.getElementById("ytsprites-start-form") ||
    document.getElementById("ytms-retry-form");

  if (!form) return;

  const statusEl =
    document.getElementById("ytsprites-start-status") ||
    document.getElementById("ytms-retry-status");

  const resultEl = document.getElementById("ytms-result");

  const btn =
    document.getElementById("ytsprites-start") ||
    document.getElementById("ytms-retry") ||
    qs('button[type="submit"]', form);

  const videoId = form.getAttribute("data-video-id") || (qs('input[name="video_id"]', form)?.value || "");
  const action = form.getAttribute("action") || "/internal/ytsprites/thumbnails/retry";

  function setStatus(t, kind) {
    if (!statusEl) return;
    statusEl.textContent = t || "";
    statusEl.style.color = kind === "err" ? "#a00" : (kind === "ok" ? "#0a8a66" : "#555");
  }

  async function postForm() {
    const fd = new FormData(form);
    const r = await fetch(action, {
      method: "POST",
      credentials: "same-origin",
      body: fd,
    });
    const d = await r.json().catch(() => null);
    return { r, d };
  }

  async function fetchStatus() {
    const url = "/internal/ytsprites/thumbnails/status?video_id=" + encodeURIComponent(videoId);
    const r = await fetch(url, { credentials: "same-origin" });
    const d = await r.json().catch(() => null);
    if (!r.ok || !d || !d.ok) return null;
    return d;
  }

  function renderDone(st) {
    // Minimal UX: show VTT link if available and suggest reload for sprites list.
    if (!resultEl) return;
    resultEl.innerHTML = "";

    const box = document.createElement("div");
    box.style.padding = "10px";
    box.style.border = "1px solid #ddd";
    box.style.borderRadius = "6px";
    box.style.background = "#fafafa";

    const title = document.createElement("div");
    title.style.fontWeight = "600";
    title.textContent = "Sprites are ready";
    box.appendChild(title);

    if (st && st.vtt_path) {
      const line = document.createElement("div");
      line.style.marginTop = "6px";
      const a = document.createElement("a");
      a.href = st.vtt_path;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = "Open sprites.vtt";
      line.appendChild(a);
      box.appendChild(line);
    }

    const hint = document.createElement("div");
    hint.style.marginTop = "6px";
    hint.style.fontSize = "12px";
    hint.style.color = "#666";
    hint.textContent = "Reload the page to refresh the asset list.";
    box.appendChild(hint);

    const reloadBtn = document.createElement("button");
    reloadBtn.type = "button";
    reloadBtn.textContent = "Reload";
    reloadBtn.style.marginTop = "8px";
    reloadBtn.addEventListener("click", () => window.location.reload());
    box.appendChild(reloadBtn);

    resultEl.appendChild(box);
  }

  let timer = 0;
  let inflight = false;

  async function pollUntilReady(maxMs) {
    const started = Date.now();
    if (timer) clearInterval(timer);

    timer = setInterval(async () => {
      if (inflight) return;
      inflight = true;
      try {
        const st = await fetchStatus();
        if (!st) return;

        if (st.ready) {
          clearInterval(timer);
          timer = 0;
          setStatus("Done", "ok");
          if (btn) btn.disabled = false;
          renderDone(st);
          return;
        }

        const elapsed = Date.now() - started;
        if (elapsed > maxMs) {
          clearInterval(timer);
          timer = 0;
          setStatus("Still processing (check later)", "warn");
          if (btn) btn.disabled = false;
          return;
        }

        setStatus("Processing…", "warn");
      } finally {
        inflight = false;
      }
    }, 2000);
  }

  // On page load, if not ready -> start polling (nice UX)
  (async function init() {
    if (!videoId) return;
    const st = await fetchStatus();
    if (st && !st.ready) {
      setStatus("Processing…", "warn");
      pollUntilReady(10 * 60 * 1000); // 10 min
    }
  })();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!videoId) return;

    if (btn) btn.disabled = true;
    setStatus("Queued…", "warn");

    try {
      const { r, d } = await postForm();
      if (!r.ok || !d || !d.ok) {
        setStatus("Failed to enqueue", "err");
        if (btn) btn.disabled = false;
        return;
      }
      if (d.already_running) {
        setStatus("Already running…", "warn");
      } else {
        setStatus("Queued…", "warn");
      }
      pollUntilReady(10 * 60 * 1000);
    } catch (err) {
      console.warn(err);
      setStatus("Failed to enqueue", "err");
      if (btn) btn.disabled = false;
    }
  });
})();