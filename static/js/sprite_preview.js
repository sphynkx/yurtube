(function(){
  const area = document.getElementById("preview-area");
  if(!area) return;

  const vttUrl = area.dataset.vtt;
  if(!vttUrl) return;

  const pop = document.getElementById("preview-pop");
  if(!pop) return;

  let cues = [];
  let durationApprox = 0;

  function parseTimestamp(ts){
    const m = ts.match(/^(\d{2}):(\d{2}):(\d{2}\.\d{3})$/);
    if(!m) return 0;
    const h = parseInt(m[1],10);
    const mm = parseInt(m[2],10);
    const ss = parseFloat(m[3]);
    return h*3600 + mm*60 + ss;
  }

  function buildAbsolute(rel){
    if(!rel) return "";
    if(rel.startsWith("/") || /^https?:\/\//i.test(rel)) return rel;
    try {
      const u = new URL(vttUrl, window.location.origin);
      const baseDir = u.pathname.replace(/\/sprites\.vtt$/, "");
      return baseDir + "/" + rel.replace(/^\/+/,"");
    } catch(e){
      return rel;
    }
  }

  function loadVTT(){
    fetch(vttUrl, { credentials: "same-origin" })
      .then(r => r.text())
      .then(text => {
        const lines = text.split(/\r?\n/);
        for(let i=0;i<lines.length;i++){
          const line = lines[i].trim();
          if(!line) continue;
          if(line.includes("-->")){
            const parts = line.split("-->").map(s=>s.trim());
            if(parts.length < 2) continue;
            const start = parseTimestamp(parts[0]);
            const end = parseTimestamp(parts[1]);
            const ref = (lines[i+1]||"").trim();
            let spriteRel = "";
            let x=0,y=0,w=0,h=0;
            const hashIdx = ref.indexOf("#xywh=");
            if(hashIdx > 0){
              spriteRel = ref.substring(0, hashIdx);
              const xywh = ref.substring(hashIdx+6).split(",");
              if(xywh.length === 4){
                x = parseInt(xywh[0],10);
                y = parseInt(xywh[1],10);
                w = parseInt(xywh[2],10);
                h = parseInt(xywh[3],10);
              }
            }
            const absUrl = buildAbsolute(spriteRel);
            cues.push({start,end,spriteUrl: absUrl,x,y,w,h});
            if(end > durationApprox) durationApprox = end;
            i++;
          }
        }
        console.log("[sprite_preview] cues:", cues.length, "durationApprox:", durationApprox);
      })
      .catch(err => console.error("[sprite_preview] VTT load failed", err));
  }

  loadVTT();

  area.addEventListener("mousemove", function(ev){
    if(!cues.length) return;
    const rect = area.getBoundingClientRect();
    const rel = (ev.clientX - rect.left) / rect.width;
    const t = Math.max(0, Math.min(1, rel)) * durationApprox;
    const cue = cues.find(c => t >= c.start && t < c.end);
    if(!cue || !cue.spriteUrl || cue.w <= 0 || cue.h <= 0){
      pop.style.display = "none";
      return;
    }
    while(pop.firstChild) pop.removeChild(pop.firstChild);
    const img = document.createElement("img");
    img.src = cue.spriteUrl;
    img.style.position = "absolute";
    img.style.left = -cue.x + "px";
    img.style.top = -cue.y + "px";
    pop.appendChild(img);

    pop.style.display = "flex";
    const relX = ev.clientX - rect.left;
    const leftPx = Math.max(0, Math.min(rect.width - cue.w, relX - cue.w/2));
    pop.style.left = leftPx + "px";
    pop.style.width = cue.w + "px";
    pop.style.height = cue.h + "px";
  });

  area.addEventListener("mouseleave", function(){
    pop.style.display = "none";
  });
})();