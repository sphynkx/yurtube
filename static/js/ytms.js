(function(){
  const startForm = document.getElementById("ytms-start-form");
  const retryForm = document.getElementById("ytms-retry-form");
  const statusEl = document.getElementById("ytms-status");
  const retryStatusEl = document.getElementById("ytms-retry-status");
  const resultEl = document.getElementById("ytms-result");

  function setText(el, v){
    if(el) el.textContent = v;
  }

  function pollLocalStatus(videoId, targetEl){
    const url = "/internal/ytms/thumbnails/status?video_id=" + encodeURIComponent(videoId);
    async function tick(){
      try {
        const r = await fetch(url, { method: "GET", credentials: "same-origin" });
        const j = await r.json();
        console.log("[YTMS CLIENT] status:", j);
        if(j.ok && j.ready){
          setText(targetEl, "Ready. VTT: " + (j.vtt_path || ""));
          setTimeout(()=> location.reload(), 600);
          return;
        }
        setText(targetEl, "Status: waiting...");
        setTimeout(tick, 3000);
      } catch(e){
        console.error("[YTMS CLIENT] poll error:", e);
        setText(targetEl, "Poll error");
        setTimeout(tick, 5000);
      }
    }
    tick();
  }

  if(startForm){
    const videoId = startForm.dataset.videoId;
    startForm.addEventListener("submit", function(ev){
      ev.preventDefault();
      setText(statusEl, "Starting job...");
      const fd = new FormData(startForm);
      fetch(startForm.action, {
        method: "POST",
        body: fd,
        credentials: "same-origin"
      }).then(r => r.json())
      .then(data => {
        console.log("[YTMS CLIENT] process response:", data);
        const jobId = data.job_id || data.job || data.id;
        const ok = data.ok === true || !!jobId;
        if(!ok){
          setText(statusEl, "Error: " + (data.error || "unknown"));
          return;
        }
        setText(statusEl, "Job started...");
        pollLocalStatus(videoId, statusEl);
      })
      .catch(err => {
        console.error("[YTMS CLIENT] network/process error:", err);
        setText(statusEl, "Network error");
      });
    });
  }

  if(retryForm){
    const videoId = retryForm.dataset.videoId;
    retryForm.addEventListener("submit", function(ev){
      ev.preventDefault();
      setText(retryStatusEl, "Retry starting...");
      const fd = new FormData(retryForm);
      fetch(retryForm.action, {
        method: "POST",
        body: fd,
        credentials: "same-origin"
      }).then(r => r.json())
      .then(data => {
        console.log("[YTMS CLIENT] retry response:", data);
        const jobId = data.job && (data.job.job_id || data.job.id);
        const ok = data.ok === true || !!jobId;
        if(!ok){
          setText(retryStatusEl, "Retry error: " + (data.error || "unknown"));
          return;
        }
        setText(retryStatusEl, "Retry job started...");
        pollLocalStatus(videoId, retryStatusEl);
      })
      .catch(err => {
        console.error("[YTMS CLIENT] retry network error:", err);
        setText(retryStatusEl, "Network error");
      });
    });
  }
})();