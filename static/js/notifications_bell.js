(function(){
  var wrap = document.getElementById('notif-bell-wrap');
  if(!wrap) return;
  var btn = document.getElementById('notif-bell-btn');
  var panel = document.getElementById('notif-panel');
  var badge = document.getElementById('notif-bell-badge');
  var listEl = document.getElementById('notif-list');
  var markAllBtn = document.getElementById('notif-mark-all');

  var open = false;
  var pollMs = 60000;
  var inflight = false;
  var timer = 0;
  var paused = false;

  function fmtTime(iso){
    try{
      var d = new Date(iso);
      return d.toLocaleString(undefined,{hour12:false});
    }catch(e){ return iso||''; }
  }
  function escapeHtml(s){
    return String(s||'').replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]||c; });
  }
  function videoLink(p){
    var vid = p && p.video_id ? String(p.video_id) : '';
    var title = p && (p.video_title || p.title) ? String(p.video_title || p.title) : vid;
    if(!vid) return escapeHtml(title||'');
    var href = '/watch?v=' + encodeURIComponent(vid);
    return '<a href="'+href+'">'+escapeHtml(title||vid)+'</a>';
  }

  function render(items){
    listEl.innerHTML = '';
    if(!items || !items.length){
      listEl.innerHTML = '<div class="notif-empty">No notifications</div>';
      return;
    }
    items.forEach(function(n){
      var div = document.createElement('div');
      div.className = 'notif-item' + (n.read_at ? '' : ' unread');
      var t = n.type;
      var p = n.payload || {};
      var line = '';
      if(t === 'comment_created'){
        line = 'New comment on your video (' + videoLink(p) + '): ' + escapeHtml(p.text_preview||'');
      } else if(t === 'comment_reply'){
        line = 'Reply to your comment (' + videoLink(p) + '): ' + escapeHtml(p.text_preview||'');
      } else if(t === 'comment_liked_batch'){
        line = 'Your comment got ' + (p.like_count||0) + ' like(s) on ' + videoLink(p) + '.';
      } else if(t === 'video_published'){
        line = 'New video: ' + videoLink(p);
      } else {
        line = escapeHtml(t);
      }
      div.innerHTML = '<div>'+line+'</div><small>'+fmtTime(n.created_at)+'</small>';
      listEl.appendChild(div);
    });
  }

  async function fetchUnread(){
    if (paused || open || document.hidden || !navigator.onLine) return;
    try{
      var r = await fetch('/notifications/unread-count', {credentials:'same-origin'});
      if(!r.ok) return;
      var d = await r.json();
      if(!d || !d.ok) return;
      var c = d.unread||0;
      badge.textContent = c;
      badge.style.display = c>0 ? 'inline-flex' : 'none';
    }catch(e){}
  }
  async function fetchList(){
    if(inflight) return;
    inflight = true;
    try{
      var r = await fetch('/notifications/list?limit=50&offset=0', {credentials:'same-origin'});
      if(!r.ok) return;
      var d = await r.json();
      if(!d || !d.ok) return;
      render(d.notifications||[]);
      badge.textContent = d.unread||0;
      badge.style.display = (d.unread||0)>0 ? 'inline-flex' : 'none';
    }catch(e){}
    inflight = false;
  }
  async function markAll(){
    try{
      var r = await fetch('/notifications/mark-all-read', {
        method:'POST',
        credentials:'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if(!r.ok) return;
      var d = await r.json();
      if(!d || !d.ok) return;
      badge.textContent = '0';
      badge.style.display = 'none';
      fetchList();
    }catch(e){}
  }

  function schedule(){
    if (timer) clearTimeout(timer);
    timer = window.setTimeout(async function(){
      timer = 0;
      await fetchUnread();
      schedule();
    }, pollMs);
  }
  function toggle(){
    open = !open;
    panel.style.display = open ? 'block' : 'none';
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if(open){ fetchList(); } else { fetchUnread(); }
  }

  document.addEventListener('click', function(e){
    if(!open) return;
    if(e.target.closest('#notif-bell-wrap')) return;
    panel.style.display = 'none';
    btn.setAttribute('aria-expanded','false');
    open = false;
  });
  btn.addEventListener('click', function(e){ e.preventDefault(); toggle(); });
  markAllBtn.addEventListener('click', function(e){ e.preventDefault(); markAll(); });

  document.addEventListener('visibilitychange', function(){
    if(document.hidden){ paused = true; } else { paused = false; fetchUnread(); }
  });
  window.addEventListener('offline', function(){ paused = true; });
  window.addEventListener('online', function(){ paused = false; fetchUnread(); });

  fetchUnread();
  schedule();
})();