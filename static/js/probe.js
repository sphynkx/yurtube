(function () {
  const SLICE_BYTES = 16 * 1024 * 1024; // 16MB
  const ENDPOINT = "/internal/ytconvert/probe";

  function el(id) {
    return document.getElementById(id);
  }

  function setText(id, text) {
    const e = el(id);
    if (e) e.textContent = text || "";
  }

  function clearNode(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function renderOptionsCheckboxes(list) {
    const body = el("ytconvert-options-body");
    if (!body) return;

    clearNode(body);

    if (!list || !list.length) {
      const d = document.createElement("div");
      d.style.fontSize = "12px";
      d.style.color = "#777";
      d.textContent = "No conversion options were detected.";
      body.appendChild(d);
      return;
    }

    const hint = document.createElement("div");
    hint.style.fontSize = "12px";
    hint.style.color = "#777";
    hint.style.marginBottom = "6px";
    hint.textContent = "These are just UI options for now (not applied yet).";
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

    setText("ytconvert-probe-status", "Probing...");
    setText("ytconvert-probe-source", "");

    const slice = file.slice(0, Math.min(file.size, SLICE_BYTES));
    const fd = new FormData();
    fd.append("file", slice, file.name || "slice.bin");

    try {
      const resp = await fetch(ENDPOINT, { method: "POST", body: fd });
      const ct = resp.headers.get("content-type") || "";
      const data = ct.includes("application/json") ? await resp.json() : null;

      if (!resp.ok) {
        const err = (data && data.error) ? data.error : `HTTP ${resp.status}`;
        setText("ytconvert-probe-status", `Probe failed: ${err}`);
        renderOptionsCheckboxes([]);
        return;
      }

      if (data && data.ok === false) {
        setText("ytconvert-probe-status", `Probe failed: ${data.error || "unknown"}`);
        renderOptionsCheckboxes([]);
        return;
      }

      setText("ytconvert-probe-status", "OK");

      const src = (data && data.source) || {};
      const w = src.width || 0;
      const h = src.height || 0;
      const dur = src.duration_sec;
      const durTxt = (typeof dur === "number" && isFinite(dur)) ? `, dur=${dur.toFixed(1)}s` : "";
      const codecTxt = `${src.vcodec || ""}${src.acodec ? "+" + src.acodec : ""}`;
      setText("ytconvert-probe-source", `Source: ${w}x${h}${durTxt}${codecTxt ? ", codecs=" + codecTxt : ""}`);

      renderOptionsCheckboxes((data && data.suggested_variants) || []);
    } catch (e) {
      setText("ytconvert-probe-status", "Probe failed: network error");
      renderOptionsCheckboxes([]);
    }
  }

  function bind() {
    const fileInput = document.querySelector('input[type="file"][name="file"]');
    if (!fileInput) return;

    fileInput.addEventListener("change", () => {
      const f = fileInput.files && fileInput.files[0];
      if (!f) {
        setText("ytconvert-probe-status", "");
        setText("ytconvert-probe-source", "");
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