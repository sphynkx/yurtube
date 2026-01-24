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
    const s = el("upload-status");
    if (!s) return;
    s.textContent = text || "";
  }

  function showOptions(show) {
    const box = el("ytconvert-options");
    if (!box) return;
    box.style.display = show ? "block" : "none";
  }

  function renderOptionsCheckboxes(list) {
    const body = el("ytconvert-options-body");
    if (!body) return;

    clearNode(body);

    if (!list || !list.length) {
      // Nothing to show => keep box hidden
      showOptions(false);
      return;
    }

    showOptions(true);

    const hint = document.createElement("div");
    hint.style.fontSize = "12px";
    hint.style.color = "#777";
    hint.style.marginBottom = "6px";
    hint.textContent = "Select formats to generate after upload (UI only for now).";
    body.appendChild(hint);

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

      // For later: send selected variants with the upload form (backend will ignore for now)
      const valParts = [];
      if (v.kind) valParts.push(v.kind);
      if (v.height) valParts.push(String(v.height));
      if (v.container) valParts.push(v.container);
      const value = valParts.join(":") || String(idx);

      cb.name = "ytconvert_variants";
      cb.value = value;

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

    body.appendChild(ul);
  }

  async function probeFile(file) {
    if (!file) return;

    // user must wait for probe => disable upload until probe finishes
    setUploadEnabled(false);
    showOptions(false);
    setUploadStatus("Probing...");

    const slice = file.slice(0, Math.min(file.size, SLICE_BYTES));
    const fd = new FormData();
    fd.append("file", slice, file.name || "slice.bin");

    try {
      const resp = await fetch(ENDPOINT, { method: "POST", body: fd });
      const ct = resp.headers.get("content-type") || "";
      const data = ct.includes("application/json") ? await resp.json() : null;

      // Regardless of probe result, allow upload after probe finishes
      setUploadEnabled(true);
      setUploadStatus("");

      if (!resp.ok || (data && data.ok === false)) {
        renderOptionsCheckboxes([]);
        return;
      }

      renderOptionsCheckboxes((data && data.suggested_variants) || []);
    } catch (e) {
      // Network error: allow upload, just no options
      setUploadEnabled(true);
      setUploadStatus("");
      renderOptionsCheckboxes([]);
    }
  }

  function bind() {
    const fileInput = document.querySelector('input[type="file"][name="file"]');
    if (!fileInput) return;

    // initial state: no file => upload disabled
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