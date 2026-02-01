(function () {
  function qs(id) { return document.getElementById(id); }

  const root = document.getElementById("edit-ytc");
  if (!root) return;

  const videoId = root.getAttribute("data-video-id") || "";
  const csrf = root.getAttribute("data-csrf") || "";

  const btnProbe = qs("ytc-probe-btn");
  const btnQueue = qs("ytc-queue-btn");
  const statusEl = qs("ytc-status");

  const optionsBox = qs("ytc-options");
  const optionsBody = qs("ytc-options-body");

  const jobLine = qs("ytc-job-line");
  const jobBar = qs("ytc-job-bar");

  const rendWrap = qs("ytc-renditions");
  const delBtn = qs("ytc-del-btn");

  function setStatus(t) { if (statusEl) statusEl.textContent = t || ""; }
  function clearNode(n) { while (n && n.firstChild) n.removeChild(n.firstChild); }

  // ---------- Renditions list (dynamic) ----------
  async function fetchRenditions() {
    try {
      const url = "/internal/ytconvert/renditions?video_id=" + encodeURIComponent(videoId);
      const r = await fetch(url, { credentials: "same-origin" });
      const d = await r.json().catch(() => null);
      if (!r.ok || !d || !d.ok) return null;
      return d.renditions || [];
    } catch {
      return null;
    }
  }

  function anyReadyChecked() {
    if (!rendWrap) return false;
    return rendWrap.querySelectorAll('input.ytc-del-item:checked').length > 0;
  }

  function updateDeleteBtnState() {
    if (!delBtn) return;
    delBtn.disabled = !anyReadyChecked();
  }

  function renderRenditions(list) {
    if (!rendWrap) return;
    clearNode(rendWrap);

    const renditions = Array.isArray(list) ? list : [];
    if (!renditions.length) {
      const sp = document.createElement("span");
      sp.id = "ytc-renditions-empty";
      sp.textContent = "none";
      rendWrap.appendChild(sp);
      updateDeleteBtnState();
      return;
    }

    const ul = document.createElement("ul");
    ul.id = "ytc-renditions-list";

    renditions.forEach((r) => {
      const preset = String(r.preset || "");
      const codec = String(r.codec || "");
      const status = String(r.status || "");
      const err = r.error_message ? String(r.error_message) : "";

      const li = document.createElement("li");

      // checkbox only for ready (as requested)
      if (status === "ready") {
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.className = "ytc-del-item";
        cb.value = "v|" + preset + "|" + codec;
        cb.style.marginRight = "8px";
        cb.addEventListener("change", updateDeleteBtnState);
        li.appendChild(cb);
      } else {
        // align text roughly
        const pad = document.createElement("span");
        pad.style.display = "inline-block";
        pad.style.width = "22px";
        li.appendChild(pad);
      }

      const txt = document.createElement("span");
      txt.textContent = preset + " " + codec + " — " + status + (err ? (" (" + err + ")") : "");
      li.appendChild(txt);

      ul.appendChild(li);
    });

    rendWrap.appendChild(ul);
    updateDeleteBtnState();
  }

  async function refreshRenditionsNow() {
    const list = await fetchRenditions();
    if (list !== null) renderRenditions(list);
  }

  async function deleteSelected() {
    if (!rendWrap) return;
    const checked = Array.from(rendWrap.querySelectorAll("input.ytc-del-item:checked"))
      .map((x) => x.value)
      .filter(Boolean);

    if (!checked.length) return;
    if (!confirm("Delete selected renditions?")) return;

    delBtn.disabled = true;

    // do normal POST navigation OR fetch; fetch is okay because endpoint redirects.
    // We'll use fetch and then refresh list to avoid full page reload.
    const fd = new FormData();
    fd.append("csrf_token", csrf);
    fd.append("video_id", videoId);
    checked.forEach((v) => fd.append("del_items", v));

    try {
      const r = await fetch("/manage/edit/ytconvert/delete", {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      // even if redirect happens, fetch follows; we just refresh the list
      await refreshRenditionsNow();
      setStatus("Deleted");
    } catch (e) {
      console.warn(e);
      setStatus("Delete failed");
      updateDeleteBtnState();
    }
  }

  if (delBtn) delBtn.addEventListener("click", deleteSelected);

  // ---------- Probe/Queue UI ----------
  function normalizeUiLabel(v) {
    if (!v) return "";
    const kind = String(v.kind || "").toLowerCase();
    if (kind === "video") return String(v.label || "").trim();
    if (kind === "audio") {
      const lb = String(v.label || "").trim().toLowerCase();
      if (lb === "mp3") return "mp3";
      if (lb === "ogg") return "ogg";
      return "";
    }
    return "";
  }

  function renderOptions(list) {
    clearNode(optionsBody);
    btnQueue.disabled = true;

    if (!list || !list.length) {
      optionsBox.style.display = "none";
      return;
    }

    const ui = list
      .map((v) => {
        const label = normalizeUiLabel(v);
        const vid = v && v.variant_id ? String(v.variant_id) : "";
        const kind = (v && v.kind ? String(v.kind) : "").toLowerCase();
        return { kind, label, variant_id: vid };
      })
      .filter((x) => x.variant_id && x.label && (x.kind === "video" || x.kind === "audio"));

    if (!ui.length) {
      optionsBox.style.display = "none";
      return;
    }

    optionsBox.style.display = "block";

    const hint = document.createElement("div");
    hint.style.fontSize = "12px";
    hint.style.color = "#777";
    hint.style.marginBottom = "6px";
    hint.textContent = "Choose renditions to generate. WEBM video will be added automatically on the backend.";
    optionsBody.appendChild(hint);

    const videoItems = ui.filter((x) => x.kind === "video");
    const audioItems = ui.filter((x) => x.kind === "audio");

    function renderGroup(title, items) {
      if (!items.length) return;
      const titleEl = document.createElement("div");
      titleEl.style.fontWeight = "600";
      titleEl.style.margin = "8px 0 4px";
      titleEl.textContent = title;
      optionsBody.appendChild(titleEl);

      const ul = document.createElement("ul");
      ul.style.margin = "0";
      ul.style.paddingLeft = "18px";

      items.forEach((v) => {
        const li = document.createElement("li");
        li.style.margin = "4px 0";

        const label = document.createElement("label");
        label.style.cursor = "pointer";

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = false;
        cb.value = v.variant_id;
        cb.className = "ytc-variant";

        cb.addEventListener("change", () => {
          const any = optionsBody.querySelectorAll("input.ytc-variant:checked").length > 0;
          btnQueue.disabled = !any;
        });

        const text = document.createElement("span");
        text.style.marginLeft = "6px";
        text.textContent = v.label;

        label.appendChild(cb);
        label.appendChild(text);
        li.appendChild(label);
        ul.appendChild(li);
      });

      optionsBody.appendChild(ul);
    }

    renderGroup("Video", videoItems);
    renderGroup("Audio", audioItems);
  }

  async function probe() {
    setStatus("Probing…");
    btnProbe.disabled = true;
    try {
      const url = "/internal/ytconvert/probe-video?video_id=" + encodeURIComponent(videoId);
      const r = await fetch(url, { credentials: "same-origin" });
      const d = await r.json().catch(() => null);
      if (!r.ok || !d || !d.ok) {
        setStatus("Probe failed");
        renderOptions([]);
        return;
      }
      renderOptions(d.suggested_variants || []);
      setStatus("Probe complete");
    } catch (e) {
      console.warn(e);
      setStatus("Probe failed");
      renderOptions([]);
    } finally {
      btnProbe.disabled = false;
    }
  }

  async function queueSelected() {
    const checked = Array.from(optionsBody.querySelectorAll("input.ytc-variant:checked"))
      .map((x) => x.value)
      .filter(Boolean);

    if (!checked.length) return;

    btnQueue.disabled = true;
    setStatus("Queueing…");

    try {
      const form = document.createElement("form");
      form.method = "POST";
      form.action = "/manage/edit/ytconvert/queue";

      function addHidden(name, value) {
        const i = document.createElement("input");
        i.type = "hidden";
        i.name = name;
        i.value = value;
        form.appendChild(i);
      }

      addHidden("csrf_token", csrf);
      addHidden("video_id", videoId);
      checked.forEach((v) => addHidden("ytconvert_variants", v));

      document.body.appendChild(form);
      form.submit();
    } catch (e) {
      console.warn(e);
      setStatus("Queue failed");
      btnQueue.disabled = false;
    }
  }

  async function pollJobOnce() {
    try {
      const url = "/internal/ytconvert/job-status?video_id=" + encodeURIComponent(videoId);
      const r = await fetch(url, { credentials: "same-origin" });
      const d = await r.json().catch(() => null);
      if (!r.ok || !d || !d.ok) return null;
      return d.job || null;
    } catch {
      return null;
    }
  }

  function renderJob(job) {
    if (!job) {
      jobLine.textContent = "—";
      jobBar.style.width = "0%";
      jobBar.style.background = "#2a7";
      return;
    }

    const st = String(job.state || "");
    const pct = Number(job.progress_percent || 0);
    const msg = String(job.message || "");
    jobLine.textContent = st + (msg ? (" — " + msg) : "");
    jobBar.style.width = Math.max(0, Math.min(100, pct)) + "%";
    jobBar.style.background = (st === "FAILED") ? "#c33" : "#2a7";
  }

  let pollTimer = null;
  async function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(async () => {
      const job = await pollJobOnce();
      renderJob(job);
      const st = job && String(job.state || "");
      if (st && (st === "DONE" || st === "FAILED" || st === "CANCELED")) {
        clearInterval(pollTimer);
        pollTimer = null;
        // NEW: refresh list right after completion
        await refreshRenditionsNow();
      }
    }, 2000);
  }

  btnProbe && btnProbe.addEventListener("click", probe);
  btnQueue && btnQueue.addEventListener("click", queueSelected);

  // initial status render + initial renditions refresh
  (async function init() {
    await refreshRenditionsNow();

    const job = await pollJobOnce();
    renderJob(job);
    if (job) startPolling();
  })();
})();