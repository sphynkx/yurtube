(function(){
  const startForm = document.getElementById("ytsprites-start-form");
  const retryForm = document.getElementById("ytms-retry-form");

  const startStatusEl = document.getElementById("ytsprites-start-status");
  const retryStatusEl = document.getElementById("ytms-retry-status");

  function setText(el, v){
    if(el) el.textContent = v;
  }

  async function postForm(formEl, statusEl){
    try {
      const fd = new FormData(formEl);
      setText(statusEl, "Starting...");
      const resp = await fetch(formEl.action, {
        method: "POST",
        body: fd,
        credentials: "same-origin"
      });
      if(resp.redirected || resp.ok){
        setText(statusEl, "Processing...");
        setTimeout(()=> { window.location.reload(); }, 600);
        return;
      }
      let msg = "Network error";
      try {
        const ct = resp.headers.get("content-type") || "";
        if (ct.includes("application/json")) {
          const j = await resp.json();
          msg = j && (j.error || j.message) ? ("Error: " + (j.error || j.message)) : msg;
        } else {
          const t = await resp.text();
          if (t && t.length) msg = "Error: " + t.substring(0, 160);
        }
      } catch(e){}
      setText(statusEl, msg);
    } catch (err) {
      console.error("[YTSPRITES CLIENT] network/process error:", err);
      setText(statusEl, "Network error");
    }
  }

  if(startForm){
    startForm.addEventListener("submit", function(ev){
      ev.preventDefault();
      postForm(startForm, startStatusEl);
    });
  }

  if(retryForm){
    retryForm.addEventListener("submit", function(ev){
      ev.preventDefault();
      postForm(retryForm, retryStatusEl);
    });
  }
})();