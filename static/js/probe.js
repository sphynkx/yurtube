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
    if (!btn) {
      console.error("[ERROR]: Upload button not found!");
      return;
    }
    btn.disabled = !enabled;
  }

  function setUploadStatus(text) {
    const statusEl = el("upload-status");
    if (!statusEl) {
      console.warn("[WARN]: Upload status element not found!");
      return;
    }
    statusEl.textContent = text || "";
  }

  function showOptions(show) {
    const optionsBox = el("ytconvert-options");
    if (!optionsBox) {
      console.error("[ERROR]: Options block not found!");
      return;
    }
    optionsBox.style.display = show ? "block" : "none";
  }

  function renderOptionsCheckboxes(list) {
    console.log("[DEBUG]: Rendering options checkboxes, list provided:", list);

    const optionsBody = el("ytconvert-options-body");
    if (!optionsBody) {
      console.error("[ERROR]: Options body element not found!");
      return;
    }

    clearNode(optionsBody);

    if (!list || !list.length) {
      console.log("[DEBUG]: No formats received, hiding options block.");
      showOptions(false);
      return;
    }

    console.log("[DEBUG]: Showing options block with formats.");
    showOptions(true);

    const hint = document.createElement("div");
    hint.style.fontSize = "12px";
    hint.style.color = "#777";
    hint.style.marginBottom = "6px";
    hint.textContent = "Select formats to generate after upload (UI only for now).";
    optionsBody.appendChild(hint);

    const ul = document.createElement("ul");
    ul.style.margin = "0";
    ul.style.paddingLeft = "18px";

    list.forEach((v, idx) => {
      const li = document.createElement("li");
      li.style.margin = "4px 0";

      const label = document.createElement("label");
      label.style.cursor = "pointer";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = false;

      const vid = (v && v.variant_id) ? String(v.variant_id) : "";
      cb.name = "ytconvert_variants";
      cb.value = vid || `variant-${idx}`;

      const text = document.createElement("span");
      text.style.marginLeft = "6px";

      const parts = [];
      parts.push(v.label || "Variant");
      if (v.container) parts.push(v.container);
      if (v.vcodec) parts.push(`v:${v.vcodec}`);
      if (v.acodec) parts.push(`a:${v.acodec}`);
      if (v.audio_bitrate_kbps) parts.push(`${v.audio_bitrate_kbps}k`);
      text.textContent = parts.join(" / ");

      label.appendChild(cb);
      label.appendChild(text);

      li.appendChild(label);
      ul.appendChild(li);
    });

    optionsBody.appendChild(ul);
  }

  async function probeFile(file) {
    if (!file) return;

    console.log("[DEBUG]: Starting file probe for:", file.name);

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

      console.log("[DEBUG]: Probe Response: ", data);

      setUploadEnabled(true);
      setUploadStatus("");

      if (!resp.ok || (data && data.ok === false)) {
        console.error("[ERROR]: Probe failed: ", data.error);
        renderOptionsCheckboxes([]);
        return;
      }

      renderOptionsCheckboxes(data.suggested_variants || []);
    } catch (e) {
      console.error("[ERROR]: Network error during probe:", e);

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