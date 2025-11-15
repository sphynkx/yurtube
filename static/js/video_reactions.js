(function(){
  var root = document.getElementById('video-reactions');
  if(!root) return;

  var videoId = root.getAttribute('data-video-id') || '';
  if(!videoId) return;

  var likeBtn = root.querySelector('.btn-v-like');
  var dislikeBtn = root.querySelector('.btn-v-dislike');
  var likeCountEl = root.querySelector('.like-count');
  var dislikeCountEl = root.querySelector('.dislike-count');

  var my = 0;
  var lastLikes = null;
  var lastDislikes = null;
  var pollMs = 20000; // 20s polling
  var pollTimer = 0;

  function setActive(){
    if (likeBtn) likeBtn.classList.toggle('active', my === 1);
    if (dislikeBtn) dislikeBtn.classList.toggle('active', my === -1);
  }

  function updateMetaLikes(likeNum){
    var stats = document.querySelector('.watch-stats');
    if (!stats) return;
    var likesEl = stats.querySelector('.likes');

    if (likeNum > 0){
      if (!likesEl){
        var span = document.createElement('span');
        span.className = 'likes';
        span.textContent = String(likeNum) + ' likes';
        stats.appendChild(span);
      }else{
        likesEl.textContent = String(likeNum) + ' likes';
      }
    }else{
      if (likesEl) {
        likesEl.remove();
      }
    }
  }

  function applyCounts(d){
    if (likeCountEl) likeCountEl.textContent = String(d.likes||0);
    if (dislikeCountEl) dislikeCountEl.textContent = String(d.dislikes||0);
    updateMetaLikes(d.likes||0);
  }

  async function loadState(){
    try{
      var r = await fetch('/videos/react/state?video_id='+encodeURIComponent(videoId), {credentials:'same-origin'});
      if(!r.ok) return;
      var d = await r.json();
      if(!d || !d.ok) return;
      applyCounts(d);
      my = d.my_reaction||0;
      setActive();
      lastLikes = d.likes||0;
      lastDislikes = d.dislikes||0;
    }catch(e){}
  }

  async function send(reaction){
    try{
      var r = await fetch('/videos/react', {
        method: 'POST',
        headers: {
          'Content-Type':'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials:'same-origin',
        body: JSON.stringify({ video_id: videoId, reaction: reaction })
      });
      if(r.status === 401){ return; }
      if(!r.ok) return;
      var d = await r.json();
      if(!d || !d.ok) return;
      applyCounts(d);
      my = d.my_reaction||0;
      setActive();
      lastLikes = d.likes||0;
      lastDislikes = d.dislikes||0;
    }catch(e){}
  }

  if (likeBtn){
    likeBtn.addEventListener('click', function(e){
      e.preventDefault();
      var target = (my === 1) ? 0 : 1;
      send(target);
    });
  }
  if (dislikeBtn){
    dislikeBtn.addEventListener('click', function(e){
      e.preventDefault();
      var target = (my === -1) ? 0 : -1;
      send(target);
    });
  }

  // Periodic polling to reflect reactions made by other users
  async function poll(){
    if (document.hidden) return;
    try{
      var r = await fetch('/videos/react/state?video_id='+encodeURIComponent(videoId), {credentials:'same-origin'});
      if(!r.ok) return;
      var d = await r.json();
      if(!d || !d.ok) return;

      // Only update DOM if values changed
      var likesNow = d.likes||0;
      var dislikesNow = d.dislikes||0;
      if (lastLikes === null || lastDislikes === null || likesNow !== lastLikes || dislikesNow !== lastDislikes){
        applyCounts(d);
        lastLikes = likesNow;
        lastDislikes = dislikesNow;
      }
    }catch(e){}
  }

  function startPolling(){
    if (pollTimer) return;
    pollTimer = setInterval(poll, pollMs);
  }
  function stopPolling(){
    if (!pollTimer) return;
    clearInterval(pollTimer);
    pollTimer = 0;
  }

  document.addEventListener('visibilitychange', function(){
    if (document.hidden) stopPolling(); else startPolling();
  });

  // Embed handlers (present only if allow_embed and rendered in partial)
  (function(){
    var wrap = document.getElementById('embed-inline');
    if (!wrap) return;
    var trigger = wrap.querySelector('.embed-trigger');
    var panel   = document.getElementById('embed-flyout');
    var backdrop= document.getElementById('embed-backdrop');
    var btnCopy = wrap.querySelector('.btn-copy-embed');
    var btnClose= wrap.querySelector('.btn-close-embed');
    var textarea= wrap.querySelector('.embed-code');

    function openPanel(){
      if (!panel) return;
      panel.hidden = false;
      trigger && trigger.setAttribute('aria-expanded','true');
      if (backdrop) backdrop.hidden = false;
      try { textarea && textarea.focus(); textarea && textarea.select(); } catch(e){}
    }
    function closePanel(){
      if (!panel) return;
      panel.hidden = true;
      trigger && trigger.setAttribute('aria-expanded','false');
      if (backdrop) backdrop.hidden = true;
    }

    trigger && trigger.addEventListener('click', function(e){
      e.stopPropagation();
      if (panel.hidden) openPanel(); else closePanel();
    });
    btnClose && btnClose.addEventListener('click', function(){ closePanel(); });

    btnCopy && btnCopy.addEventListener('click', function(){
      try{
        textarea && textarea.select();
        document.execCommand('copy');
        textarea && textarea.blur();
      }catch(e){}
    });

    document.addEventListener('click', function(e){
      if (!panel || panel.hidden) return;
      if (wrap.contains(e.target)) return;
      closePanel();
    });
    document.addEventListener('keydown', function(e){
      if (e.key === 'Escape') closePanel();
    });
  })();

  loadState();
  startPolling();
})();