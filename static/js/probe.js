(function () {
  const SLICE_BYTES = 16 * 1024 * 1024; // 16MB
  const ENDPOINT = "/internal/ytconvert/probe";

  function el(id) {
    return document.getElementById(id);
  }

  function setText(id, text) {
    const e = el(id);
    if (e) e.textContent = text;
  }

  function renderVariants(list) {
    const box = el("ytconvert-suggestions");
    if (!box) return;

    box.innerHTML = "";
    if (!list || !list.length) {
      box.textContent = "No suggestions (could not determine).";
      return;
    }

    const ul = document.createElement("ul");
    ul.style.margin = "6px 0 0 18px";
    ul.style.padding = "0";

    list.forEach((v) => {
      const li = document.createElement("li");
      const parts = [];
      parts.push(`${v.kind}: ${v.label}`);
      if (v.container) parts.push(`container=${v.container}`);
      if (v.vcodec) parts.push(`v=${v.vcodec}`);
      if (v.acodec) parts.push(`a=${v.acodec}`);
      if (v.height) parts.push(`h=${v.height}`);
      if (v.audio_bitrate_kbps) parts.push(`abr=${v.audio_bitrate_kbps}k`);
      li.textContent = parts.join(", ");
      ul.appendChild(li);
    });

    box.appendChild(ul);
  }

  async function probeFile(file) {
    if (!file) return;

    setText("ytconvert-probe-status", "Probing...");
    const slice = file.slice(0, Math.min(file.size, SLICE_BYTES));

    const fd = new FormData();
    // keep original filename so ffprobe has a hint sometimes (optional)
    fd.append("file", slice, file.name || "slice.bin");

    try {
      const resp = await fetch(ENDPOINT, {
        method: "POST",
        body: fd,
      });

      const ct = resp.headers.get("content-type") || "";
      const data = ct.includes("application/json") ? await resp.json() : null;

      if (!resp.ok) {
        const err = (data && data.error) ? data.error : `HTTP ${resp.status}`;
        setText("ytconvert-probe-status", `Probe failed: ${err}`);
        renderVariants([]);
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

      renderVariants((data && data.suggested_variants) || []);
    } catch (e) {
      setText("ytconvert-probe-status", "Probe failed: network error");
      renderVariants([]);
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
        renderVariants([]);
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