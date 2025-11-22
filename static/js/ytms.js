(function(){
  const form = document.getElementById("ytms-start-form");
  const statusEl = document.getElementById("ytms-status");
  const resultEl = document.getElementById("ytms-result");

  function setText(el, v){
    if(el) el.textContent = v;
  }

  if(!form) return;
  const videoId = form.dataset.videoId;

  form.addEventListener("submit", function(ev){
    ev.preventDefault();
    setText(statusEl, "Starting job...");
    const fd = new FormData(form);
    fetch(form.action, {
      method: "POST",
      body: fd,
      credentials: "same-origin"
    }).then(r => r.json())
    .then(data => {
      console.log("[YTMS CLIENT] process response:", data);
      const jobId = data.job_id || data.job || data.id;
      const looksLikeSuccess = data.ok === true || !!jobId;

      if(!looksLikeSuccess){
        setText(statusEl, "Error: " + (data.error || "unknown"));
        return;
      }
      setText(statusEl, "Job started...");
      pollLocalStatus(videoId);
    })
    .catch(err => {
      console.error("[YTMS CLIENT] network/process error:", err);
      setText(statusEl, "Network error");
    });
  });

  function pollLocalStatus(videoId){
    const url = "/internal/ytms/thumbnails/status?video_id=" + encodeURIComponent(videoId);
    async function tick(){
      try {
        const r = await fetch(url, { method: "GET", credentials: "same-origin" });
        const j = await r.json();
        console.log("[YTMS CLIENT] status:", j);
        if(j.ok && j.ready){
          setText(statusEl, "Ready. VTT: " + (j.vtt_path || ""));
          setTimeout(()=> location.reload(), 600);
          return;
        }
        setText(statusEl, "Status: waiting...");
        setTimeout(tick, 3000);
      } catch(e){
        console.error("[YTMS CLIENT] poll error:", e);
        setText(statusEl, "Poll error");
        setTimeout(tick, 5000);
      }
    }
    tick();
  }
})();