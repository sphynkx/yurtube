(function () {
  function fmtTime(sec){ if(!isFinite(sec)||sec<0) sec=0; sec=Math.floor(sec); var h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60), s=sec%60; function pad(x){return(x<10?"0":"")+x;} return (h>0? h+":"+pad(m)+":"+pad(s): m+":"+pad(s)); }
  function parseJSONAttr(el,name,fallback){ var s=el.getAttribute(name); if(!s) return fallback; try { return JSON.parse(s); } catch(e){ return fallback; } }
  function elClosest(node, selector, stopAt){ var n=node; while(n && n!==stopAt){ if(n.nodeType===1 && typeof n.matches==="function" && n.matches(selector)) return n; n=n.parentElement||n.parentNode; } return null; }
  function detectPlayerName(){ try{ var u=new URL(import.meta.url); var m=u.pathname.match(/\/static\/players\/([^\/]+)\//); return m? m[1]:"yurtube"; }catch(e){ return "yurtube"; } }

  function mountOne(host, tpl, PLAYER_BASE){
    host.innerHTML = tpl;

    var root = host.querySelector(".yrp-container");
    var wrap = root.querySelector(".yrp-video-wrap");
    var video = root.querySelector(".yrp-video");
    var controls = root.querySelector(".yrp-controls");
    var source = video.querySelector("source");

    root.classList.add("yrp-embed");
    root.setAttribute("tabindex","0");

    var videoSrc = host.getAttribute("data-video-src")||"";
    var poster = host.getAttribute("data-poster-url")||"";
    var vid = host.getAttribute("data-video-id")||"";
    var subs = parseJSONAttr(host,"data-subtitles",[]);
    var opts = parseJSONAttr(host,"data-options",{});

    if(source) source.setAttribute("src", videoSrc);
    if(poster) video.setAttribute("poster", poster);
    if(opts&&opts.autoplay) video.setAttribute("autoplay","");
    if(opts&&opts.muted) video.setAttribute("muted","");
    if(opts&&opts.loop) video.setAttribute("loop","");
    if(vid) root.setAttribute("data-video-id", vid);

    if(Array.isArray(subs)){
      subs.forEach(function(t){
        if(!t||!t.src) return;
        var tr=document.createElement("track");
        tr.setAttribute("kind","subtitles");
        if(t.srclang) tr.setAttribute("srclang", String(t.srclang));
        if(t.label) tr.setAttribute("label", String(t.label));
        tr.setAttribute("src", String(t.src));
        if(t.default) tr.setAttribute("default","");
        video.appendChild(tr);
      });
    }

    // icon urls -> CSS vars on root (for mask)
    var iconBase = PLAYER_BASE + "/img/buttons";
    root.style.setProperty("--icon-play",    'url("' + iconBase + '/play.svg")');
    root.style.setProperty("--icon-pause",   'url("' + iconBase + '/pause.svg")');
    root.style.setProperty("--icon-prev",    'url("' + iconBase + '/prev.svg")');
    root.style.setProperty("--icon-next",    'url("' + iconBase + '/next.svg")');
    root.style.setProperty("--icon-vol",     'url("' + iconBase + '/volume.svg")');
    root.style.setProperty("--icon-mute",    'url("' + iconBase + '/mute.svg")');
    root.style.setProperty("--icon-cc",      'url("' + iconBase + '/cc.svg")');
    root.style.setProperty("--icon-mini",    'url("' + iconBase + '/mini.svg")');
    root.style.setProperty("--icon-settings",'url("' + iconBase + '/settings.svg")');
    root.style.setProperty("--icon-theater", 'url("' + iconBase + '/theater.svg")');
    root.style.setProperty("--icon-full",    'url("' + iconBase + '/full.svg")');
    root.classList.add("yrp-icons-ready");

    wireEmbed(root, wrap, video, controls);
  }

  function wireEmbed(root, wrap, video, controls){
    var centerPlay = root.querySelector(".yrp-center-play");
    var btnPlay = root.querySelector(".yrp-play");
    var btnVol  = root.querySelector(".yrp-vol-btn");
    var volWrap = root.querySelector(".yrp-volume");
    var volSlider = root.querySelector(".yrp-vol-slider");
    var tCur = root.querySelector(".yrp-time-current");
    var tTot = root.querySelector(".yrp-time-total");
    var progress = root.querySelector(".yrp-progress");
    var rail = root.querySelector(".yrp-progress-rail");
    var buf = root.querySelector(".yrp-progress-buffer");
    var played = root.querySelector(".yrp-progress-played");
    var handle = root.querySelector(".yrp-progress-handle");
    var tooltip = root.querySelector(".yrp-progress-tooltip");
    var btnSettings = root.querySelector(".yrp-settings");
    var menu = root.querySelector(".yrp-menu");
    var btnFull = root.querySelector(".yrp-fullscreen");
    var btnPip = root.querySelector(".yrp-pip");
    var ctx = root.querySelector(".yrp-context");

    var seeking=false, duration=0, hideTimer=null;
    var volClickLock=false;

    function showControls(){
      root.classList.remove("autohide");
      if(hideTimer) clearTimeout(hideTimer);
      hideTimer=setTimeout(function(){ root.classList.add("autohide"); }, 1800);
    }
    function layoutFillViewport(){
      try {
        var H = window.innerHeight || document.documentElement.clientHeight || root.clientHeight || 0;
        if(H <= 0) return;
        wrap.style.height = H + "px";
        video.style.height = "100%";
        video.style.width = "100%";
        video.style.objectFit = "contain";
      } catch(_){}
    }
    function updateTimes(){ try{ duration=isFinite(video.duration)?video.duration:0; }catch(e){ duration=0; } if(tTot) tTot.textContent=fmtTime(duration); if(tCur) tCur.textContent=fmtTime(video.currentTime||0); }
    function updateProgress(){
      var d=duration||0, ct=video.currentTime||0, frac=d>0?Math.max(0,Math.min(ct/d,1)):0;
      if(played) played.style.width=(frac*100).toFixed(3)+"%";
      if(handle) handle.style.left=(frac*100).toFixed(3)+"%";
      var b=0; if(video.buffered&&video.buffered.length>0){ try{ b=video.buffered.end(video.buffered.length-1);}catch(e){b=0;} }
      var bfrac=d>0?Math.max(0,Math.min(b/d,1)):0; if(buf) buf.style.width=(bfrac*100).toFixed(3)+"%";
    }
    function refreshVolIcon(){
      var v = video.muted ? 0 : video.volume;
      var label = (video.muted || v === 0) ? "Mute" : "Vol";
      if (btnVol) {
        btnVol.textContent = label;
        btnVol.classList.toggle("icon-mute", (label === "Mute"));
        btnVol.classList.toggle("icon-vol",  (label !== "Mute"));
      }
    }
    function refreshPlayIcon(){
      if (!btnPlay) return;
      if (video.paused) {
        btnPlay.textContent = "Play";
        btnPlay.classList.add("icon-play");
        btnPlay.classList.remove("icon-pause");
      } else {
        btnPlay.textContent = "Pause";
        btnPlay.classList.add("icon-pause");
        btnPlay.classList.remove("icon-play");
      }
    }
    function setMutedToggle(){ video.muted=!video.muted; refreshVolIcon(); }
    function playToggle(){ if(video.paused) video.play().catch(function(){}); else video.pause(); }
    function seekByClientX(xc){ var r=rail.getBoundingClientRect(); var x=Math.max(0, Math.min(xc - r.left, r.width)); var f=r.width>0? x/r.width: 0; var t=(duration||0)*f; video.currentTime=t; }
    function updateTooltip(xc){ var tt=tooltip; if(!tt) return; var r=rail.getBoundingClientRect(); var x=Math.max(0, Math.min(xc-r.left, r.width)); var f=r.width>0? x/r.width:0; var t=(duration||0)*f; tt.textContent=fmtTime(t); tt.style.left=(f*100).toFixed(3)+"%"; tt.hidden=false; }

    function volToggleOnce(e){
      if(e){ e.preventDefault(); e.stopPropagation(); }
      if(volClickLock) return;
      volClickLock = true;
      setTimeout(function(){ volClickLock=false; }, 220);
      setMutedToggle();
      root.classList.add("vol-open");
      showControls();
      setTimeout(function(){ root.classList.remove("vol-open"); }, 800);
    }

    refreshVolIcon();

    video.addEventListener("loadedmetadata", function(){ updateTimes(); updateProgress(); layoutFillViewport(); showControls(); refreshPlayIcon(); });
    video.addEventListener("timeupdate", function(){ updateTimes(); updateProgress(); });
    video.addEventListener("progress", function(){ updateProgress(); });
    video.addEventListener("play", function(){ root.classList.add("playing"); showControls(); refreshPlayIcon(); });
    video.addEventListener("pause", function(){ root.classList.remove("playing"); showControls(); refreshPlayIcon(); });

    video.addEventListener("click", function(){ playToggle(); });
    if(centerPlay) centerPlay.addEventListener("click", playToggle);
    if(btnPlay) btnPlay.addEventListener("click", playToggle);

    if(btnVol) btnVol.addEventListener("click", volToggleOnce);
    if(controls){
      controls.addEventListener("click", function(e){
        var t=e.target; if(t&&t.nodeType===3&&t.parentNode) t=t.parentNode;
        if(elClosest(t, ".yrp-vol-btn", controls)) volToggleOnce(e);
      }, true);
    }
    document.addEventListener("click", function(e){
      try{
        var btn = root.querySelector(".yrp-vol-btn"); if(!btn) return;
        var r = btn.getBoundingClientRect();
        var x = e.clientX, y = e.clientY;
        if(x>=r.left && x<=r.right && y>=r.top && y<=r.bottom){
          volToggleOnce(e);
        }
      }catch(_){}
    }, true);

    if(volSlider){
      volSlider.addEventListener("input", function(){
        var v=parseFloat(volSlider.value||"1"); if(!isFinite(v)) v=1;
        v=Math.max(0,Math.min(v,1)); video.volume=v; if(v>0) video.muted=false; refreshVolIcon();
        root.classList.add("vol-open"); showControls();
      });
    }
    if(volWrap){
      volWrap.addEventListener("wheel", function(e){
        e.preventDefault();
        var step=0.05, v=video.muted?0:video.volume;
        var nv=Math.max(0,Math.min(v+(e.deltaY<0?step:-step),1));
        video.volume=nv; if(nv>0) video.muted=false;
        if(volSlider) volSlider.value=String(nv);
        refreshVolIcon(); root.classList.add("vol-open"); showControls();
      }, {passive:false});
    }

    if(progress){
      progress.addEventListener("mousedown", function (e) { var seeking=true; seekByClientX(e.clientX); showControls(); });
      window.addEventListener("mousemove", function (e) { /* noop: seeking handled above */ });
      window.addEventListener("mouseup", function () { /* noop */ });
      progress.addEventListener("mousemove", function (e) { updateTooltip(e.clientX); });
      progress.addEventListener("mouseleave", function () { if(tooltip) tooltip.hidden=true; });
    }

    // Settings toggle: class-based, not hidden property
    if (btnSettings && menu) {
      // ensure template "hidden" attr does not block
      menu.removeAttribute("hidden");
      btnSettings.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation();
        var open = menu.classList.contains("open");
        if (open) {
          menu.classList.remove("open");
          btnSettings.setAttribute("aria-expanded", "false");
        } else {
          menu.classList.add("open");
          btnSettings.setAttribute("aria-expanded", "true");
          root.classList.add("vol-open");
          showControls();
        }
      });
      menu.addEventListener("click", function (e) {
        var t=e.target; if(t && t.classList.contains("yrp-menu-item")){
          var sp=parseFloat(t.getAttribute("data-speed")||"NaN");
          if(!isNaN(sp)){ video.playbackRate=sp; menu.classList.remove("open"); btnSettings.setAttribute("aria-expanded","false"); }
        }
      });
      document.addEventListener("click", function (e) {
        if (menu.classList.contains("open") && !menu.contains(e.target) && e.target !== btnSettings) {
          menu.classList.remove("open");
          btnSettings.setAttribute("aria-expanded", "false");
        }
      });
    }

    if(btnFull){
      btnFull.addEventListener("click", function () {
        if(document.fullscreenElement){ document.exitFullscreen().catch(function(){}); }
        else { root.requestFullscreen && root.requestFullscreen().catch(function(){}); }
      });
    }
    if(btnPip){
      btnPip.addEventListener("click", function(e){
        e.preventDefault(); e.stopPropagation();
        try{
          if(document.pictureInPictureEnabled && video.requestPictureInPicture && !video.disablePictureInPicture){
            if(document.pictureInPictureElement===video){ document.exitPictureInPicture().catch(function(){}); }
            else {
              var need=video.paused, prev=video.muted, p=Promise.resolve();
              if(need){ video.muted=true; p=video.play().catch(function(){}); }
              p.then(function(){ return video.requestPictureInPicture(); })
               .catch(function(){})
               .then(function(){ if(need){ video.pause(); video.muted=prev; } });
            }
          }
        }catch(_){}
      });
    }

    root.addEventListener("contextmenu", function (e) {
      e.preventDefault();
      if(!ctx) return;
      var rw = root.getBoundingClientRect();
      ctx.style.left = (e.clientX - rw.left) + "px";
      ctx.style.top = (e.clientY - rw.top) + "px";
      ctx.hidden = false;
      root.classList.add("vol-open"); showControls();
    });
    if(ctx){
      ctx.addEventListener("click", function(ev){
        var t = ev.target; if(!t) return;
        var act = t.getAttribute("data-action");
        var at = Math.floor(video.currentTime || 0);
        var u = new URL(window.location.href);
        if(act==="pip"){
          btnPip && btnPip.click();
        } else if(act==="copy-url"){
          u.searchParams.delete("t");
          try{ navigator.clipboard && navigator.clipboard.writeText && navigator.clipboard.writeText(u.toString()); }catch(_){}
        } else if(act==="copy-url-time"){
          u.searchParams.set("t", String(at));
          try{ navigator.clipboard && navigator.clipboard.writeText && navigator.clipboard.writeText(u.toString()); }catch(_){}
        }
        ctx.hidden = true;
      });
    }
    document.addEventListener("click", function (e2) {
      if (ctx && !ctx.hidden && !ctx.contains(e2.target)) ctx.hidden = true;
    });

    function handleHotkey(e){
      var t=e.target; var tag=t && t.tagName ? t.tagName.toUpperCase():"";
      var editable=t && (t.isContentEditable || tag==="INPUT" || tag==="TEXTAREA"); if(editable) return;
      if(e.ctrlKey||e.metaKey||e.altKey) return;
      var code=e.code, key=(e.key||"").toLowerCase();

      if(code==="Space"||code==="Enter"||code==="NumpadEnter"||code==="MediaPlayPause"||code==="KeyK"||key==="k"){ e.preventDefault(); video.paused?video.play().catch(function(){}):video.pause(); return; }
      if(code==="ArrowLeft"||code==="KeyJ"||key==="j"){ e.preventDefault(); video.currentTime=Math.max(0,(video.currentTime||0)-5); return; }
      if(code==="ArrowRight"||code==="KeyL"||key==="l"){ e.preventDefault(); video.currentTime=Math.min((video.currentTime||0)+5, duration||1e9); return; }
      if(code==="KeyM"||key==="m"){ e.preventDefault(); setMutedToggle(); return; }
      if(code==="KeyF"||key==="f"){ e.preventDefault(); btnFull && btnFull.click(); return; }
      if(code==="KeyI"||key==="i"){ e.preventDefault(); btnPip && btnPip.click(); return; }
      if(code==="Escape"||key==="escape"){
        if(ctx && !ctx.hidden) ctx.hidden = true;
        if(btnSettings && menu && menu.classList.contains("open")) { menu.classList.remove("open"); btnSettings.setAttribute("aria-expanded","false"); }
        return;
      }
    }
    document.addEventListener("keydown", handleHotkey);

    ["mouseenter","mousemove","pointermove","touchstart"].forEach(function(ev){
      (controls||root).addEventListener(ev, function(){ try{ root.focus(); }catch(_){} showControls(); }, {passive:true});
    });
    root.addEventListener("mouseleave", function(){ setTimeout(function(){ root.classList.add("autohide"); }, 600); });

    function relayout(){ layoutFillViewport(); }
    window.addEventListener("resize", relayout);
    setTimeout(relayout, 0);
    setTimeout(relayout, 100);
  }

  function initAll(){
    var PLAYER_NAME = detectPlayerName();
    var PLAYER_BASE = "/static/players/" + PLAYER_NAME;
    var hosts=document.querySelectorAll('.player-host[data-player="'+PLAYER_NAME+'"]');
    if(hosts.length===0) return;
    fetch(PLAYER_BASE + "/templates/player.html",{credentials:"same-origin"})
      .then(function(r){return r.text();})
      .then(function(html){ for(var i=0;i<hosts.length;i++) mountOne(hosts[i], html, PLAYER_BASE); })
      .catch(function(){});
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded", initAll);
  else initAll();
})();