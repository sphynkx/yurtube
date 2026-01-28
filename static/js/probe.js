(function () {
  const SLICE_BYTES = 16 * 1024 * 1024; // 16MB
  const ENDPOINT = "/internal/ytconvert/probe";

  function el(id) {
    return document.getElementById(id);
  }

  function clearNode(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function setUploadEnabled(enabled) {
    const btn = el("upload-submit");
    if (!btn) return;
    btn.disabled = !enabled;
  }

  function setUploadStatus(text) {
    const statusEl = el("upload-status");
    if (!statusEl) return;
    statusEl.textContent = text || "";
  }

  function showOptions(show) {
    const optionsBox = el("ytconvert-options");
    if (!optionsBox) return;
    optionsBox.style.display = show ? "block" : "none";
  }

  function normalizeUiLabel(v) {
    if (!v) return "";
    const kind = (v.kind || "").toLowerCase();
    if (kind === "video") {
      // only resolution, e.g. "144p"
      return String(v.label || "").trim();
    }
    if (kind === "audio") {
      // only mp3/ogg
      const lb = String(v.label || "").trim().toLowerCase();
      if (lb === "mp3") return "mp3";
      if (lb === "ogg") return "ogg";
      return "";
    }
    return "";
  }

  function renderOptionsCheckboxes(list) {
    const optionsBody = el("ytconvert-options-body");
    if (!optionsBody) return;

    clearNode(optionsBody);

    if (!list || !list.length) {
      showOptions(false);
      return;
    }

    // Filter to safe UI items: video with label, audio mp3/ogg
    const ui = list
      .map((v) => {
        const label = normalizeUiLabel(v);
        const vid = v && v.variant_id ? String(v.variant_id) : "";
        const kind = (v && v.kind ? String(v.kind) : "").toLowerCase();
        return { kind, label, variant_id: vid };
      })
      .filter((x) => x.variant_id && x.label && (x.kind === "video" || x.kind === "audio"));

    if (!ui.length) {
      showOptions(false);
      return;
    }

    showOptions(true);

    const hint = document.createElement("div");
    hint.style.fontSize = "12px";
    hint.style.color = "#777";
    hint.style.marginBottom = "6px";
    hint.textContent = "Choose renditions to generate after upload.";
    optionsBody.appendChild(hint);

    // Optional grouping: Video then Audio
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

      items.forEach((v, idx) => {
        const li = document.createElement("li");
        li.style.margin = "4px 0";

        const label = document.createElement("label");
        label.style.cursor = "pointer";

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = false;
        cb.name = "ytconvert_variants";
        cb.value = v.variant_id;

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

  async function probeFile(file) {
    if (!file) return;

    setUploadEnabled(false);
    setUploadStatus("Probing...");
    showOptions(false);

    const slice = file.slice(0, Math.min(file.size, SLICE_BYTES));
    const fd = new FormData();
    fd.append("file", slice, file.name || "slice.bin");

    try {
      const resp = await fetch(ENDPOINT, { method: "POST", body: fd });
      const ct = resp.headers.get("content-type") || "";
      const data = ct.includes("application/json") ? await resp.json() : null;

      setUploadEnabled(true);
      setUploadStatus("");

      if (!resp.ok || (data && data.ok === false)) {
        renderOptionsCheckboxes([]);
        return;
      }

      renderOptionsCheckboxes(data.suggested_variants || []);
    } catch (e) {
      setUploadEnabled(true);
      setUploadStatus("");
      showOptions(false);
    }
  }

  function bind() {
    const fileInput = document.querySelector('input[type="file"][name="file"]');
    if (!fileInput) return;

    setUploadEnabled(false);
    showOptions(false);
    setUploadStatus("");

    fileInput.addEventListener("change", () => {
      const f = fileInput.files && fileInput.files[0];
      if (!f) {
        setUploadEnabled(false);
        showOptions(false);
        setUploadStatus("");
        renderOptionsCheckboxes([]);
        return;
      }
      probeFile(f);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();