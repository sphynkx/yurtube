/**
* Comments Author Heart
* - draw hearts according to the rule:
* liked_by_author === true OR (we know videoAuthorUid AND votes[videoAuthorUid] === 1)
* - get videoAuthorUid from:
* 1) root.dataset.videoAuthorUid (if the template returns it),
* 2) the response /comments/list (video_author_uid|author_uid|...),
* 3) if absent, we get it from comments where liked_by_author=true: from votes, we look for the uid starting with 1.
* - On click (POST /comments/vote):
* a) if resp.liked_by_author is present → switch immediately only for the current cid,
* b) otherwise, if we know videoAuthorUid and actor (resp.user_id|user_uid) == videoAuthorUid → switch immediately,
* c) otherwise (author unknown) → quick debounce/refresh /comments/list (we'll pull in liked_by_author and display it immediately).
* - Each .btn-like contains exactly one .author-heart; we only control style.display.
* - Force the heart color to be red (with !important).
*
* Debug: window.__COMMENTS_DEBUG_HEART = true|false (default true)
*/
(function(){
  if (window.__comments_author_heart_once) return;
  window.__comments_author_heart_once = true;

  const DEBUG = (typeof window !== 'undefined' && typeof window.__COMMENTS_DEBUG_HEART !== 'undefined')
    ? !!window.__COMMENTS_DEBUG_HEART
    : true;
  const dbg = (...a) => { if (DEBUG) console.log('[comments-heart]', ...a); };

  const root = document.getElementById('comments-root');
  const listEl = document.getElementById('comments-list');
  if (!root || !listEl){ dbg('missing root/listEl'); return; }

  const STATE = {
    videoId: root.dataset.videoId || '',
    vAuthor: root.dataset.videoAuthorUid || '',
    hearts: {},                 // cid -> boolean
    fetchWrapped: false,
    xhrWrapped: false,
    initialDone: false,
    initialInflight: false,
    refreshTimer: 0
  };
  if (!STATE.videoId){ dbg('no videoId'); return; }

  (function injectStyle(){
    if (document.getElementById('comments-author-heart-style')) return;
    const css = `
      .btn-like .author-heart {
        color: #e0245e !important;
        font-size: 12px;
        line-height: 1;
        position: relative;
        top: -1px;
        margin-left: 2px;
        user-select: none;
      }
    `;
    const style = document.createElement('style');
    style.id = 'comments-author-heart-style';
    style.type = 'text/css';
    style.appendChild(document.createTextNode(css));
    document.head.appendChild(style);
  })();

  // Normalize: 1 .author-heart on button
  function normalizeHeart(btn){
    if (!btn) return null;
    const hearts = btn.querySelectorAll('.author-heart');
    if (hearts.length > 1){
      for (let i=1;i<hearts.length;i++) hearts[i].remove();
    }
    let heart = btn.querySelector('.author-heart');
    if (!heart){
      heart = document.createElement('span');
      heart.className = 'author-heart';
      heart.textContent = '❤';
      heart.style.display = 'none';
      btn.appendChild(heart);
      dbg('created heart node');
    }
    return heart;
  }
  function setHeart(btn, on){
    const heart = normalizeHeart(btn);
    if (!heart) return;
    heart.style.display = on ? 'inline' : 'none';
  }
  function applyHearts(){
    const ids = Object.keys(STATE.hearts || {});
    dbg('applyHearts', { count: ids.length, vAuthor: STATE.vAuthor });
    for (const cid of ids){
      const btn = listEl.querySelector(`.btn-like[data-cid="${cid}"]`);
      if (!btn) continue;
      setHeart(btn, !!STATE.hearts[cid]);
    }
  }

  // Get author video
  function updateAuthorFromList(data){
    const va = (data && (data.video_author_uid || data.author_uid || data.video_author_uid_channel || data.video_author_uid_user)) || '';
    if (va && va !== STATE.vAuthor){
      STATE.vAuthor = va;
      root.dataset.videoAuthorUid = va;
      dbg('videoAuthorUid set', va);
    }
  }
  // If videoAuthorUid absent - try to display it by liked_by_author=true
  function deduceAuthorFromLiked(data){
    if (STATE.vAuthor || !data || !data.comments) return;
    const counts = {}; // uid -> score
    for (const [cid, meta] of Object.entries(data.comments)){
      if (!meta || meta.liked_by_author !== true) continue;
      const votes = meta.votes || {};
      for (const [uid, val] of Object.entries(votes)){
        if (Number(val) === 1){
          counts[uid] = (counts[uid] || 0) + 1;
        }
      }
    }
    let best = '', bestCount = 0;
    for (const [uid, cnt] of Object.entries(counts)){
      if (cnt > bestCount){ best = uid; bestCount = cnt; }
    }
    if (best){
      STATE.vAuthor = best;
      root.dataset.videoAuthorUid = best;
      dbg('videoAuthorUid deduced from liked_by_author', { uid: best, count: bestCount });
    }
  }

  // Recount hearts from list
  function computeFromList(data){
    const out = {};
    if (!data || !data.comments) return out;
    const vAuthor = STATE.vAuthor;
    for (const [cid, meta] of Object.entries(data.comments)){
      const likedMeta = !!(meta && meta.liked_by_author === true);
      const votes = (meta && meta.votes) || {};
      const byAuthor = vAuthor ? Number(votes[vAuthor] || 0) === 1 : false;
      out[cid] = likedMeta || byAuthor;
      if (DEBUG) dbg('compute', { cid, likedMeta, byAuthor, vAuthor, final: out[cid] });
    }
    return out;
  }

  function onList(data, src){
    try{
      dbg('list', { src, roots: (data.roots||[]).length, comments: data.comments ? Object.keys(data.comments).length : 0 });
      updateAuthorFromList(data);
      // if no author - try to get ti from liked_by_author
      if (!STATE.vAuthor) deduceAuthorFromLiked(data);

      // Nrmalize buttons and apply state
      listEl.querySelectorAll('.btn-like').forEach(normalizeHeart);
      STATE.hearts = computeFromList(data);
      applyHearts();

      STATE.initialDone = true;
    }catch(e){
      console.warn('[comments-heart] onList failed', e);
    }
  }

  function onVote(req, resp){
    try{
      const cid = req && (req.comment_id || req.cid);
      const btn = cid ? listEl.querySelector(`.btn-like[data-cid="${cid}"]`) : null;
      const actor = (resp && (resp.user_id || resp.user_uid)) || '';
      const myVote = resp && resp.my_vote;

      // 1) If backend send liked_by_author
      if (btn && typeof resp?.liked_by_author === 'boolean'){
        dbg('vote liked_by_author', { cid, val: resp.liked_by_author });
        setHeart(btn, resp.liked_by_author === true);
        STATE.hearts[cid] = (resp.liked_by_author === true);
        return;
      }

      // 2) If author is known and it is actor also
      if (btn && STATE.vAuthor && actor && typeof myVote === 'number' && actor === STATE.vAuthor){
        const on = (myVote === 1);
        setHeart(btn, on);
        STATE.hearts[cid] = on;
        return;
      }

      // 3) Else - refresh of list to get liked_by_author refresh again
      scheduleRefresh('vote-fallback');
    }catch(e){
      console.warn('[comments-heart] onVote failed', e);
    }
  }

  function scheduleRefresh(reason){
    if (STATE.refreshTimer) clearTimeout(STATE.refreshTimer);
    STATE.refreshTimer = setTimeout(async () => {
      STATE.refreshTimer = 0;
      try{
        const url = `/comments/list?video_id=${encodeURIComponent(STATE.videoId)}&include_hidden=false&_=${Date.now()}`;
        dbg('refresh list', { url, reason });
        const r = await fetch(url, { method: 'GET', credentials: 'same-origin' });
        const data = await r.json();
        onList(data, 'refresh');
      }catch(e){
        console.warn('[comments-heart] refresh failed', e);
      }
    }, 120);
  }

  // Get list on start
  async function initialFetchOnce(){
    if (STATE.initialDone || STATE.initialInflight) return;
    STATE.initialInflight = true;
    try{
      const url = `/comments/list?video_id=${encodeURIComponent(STATE.videoId)}&include_hidden=false&_=${Date.now()}`;
      dbg('initial list fetch', { url });
      const r = await fetch(url, { method: 'GET', credentials: 'same-origin' });
      const data = await r.json();
      onList(data, 'initial');
    }catch(e){
      console.warn('[comments-heart] initial fetch failed', e);
    }finally{
      STATE.initialInflight = false;
    }
  }

  // Catch the fetch
  (function wrapFetch(){
    if (STATE.fetchWrapped) return;
    if (!window.fetch) return;
    const rList = /\/comments\/list(?:\/|\?|$)/;
    const rVote = /\/comments\/vote(?:\/|\?|$)/;
    const orig = window.fetch;
    window.fetch = async function(input, init){
      const url = (typeof input === 'string') ? input : (input && input.url) || '';
      const method = ((init && init.method) || 'GET').toUpperCase();
      const res = await orig(input, init);
      try{
        let reqBody = null;
        if (init && init.body){
          const b = init.body;
          if (typeof b === 'string' && b.trim().startsWith('{')){ try{ reqBody = JSON.parse(b); }catch(_){ } }
          else if (typeof URLSearchParams !== 'undefined' && b instanceof URLSearchParams){ const o={}; for (const [k,v] of b) o[k]=v; reqBody=o; }
          else if (typeof FormData !== 'undefined' && b instanceof FormData){ const o={}; b.forEach((v,k)=>o[k]=v); reqBody=o; }
        }
        if (rList.test(url) && method === 'GET'){
          res.clone().json().then(d => onList(d, 'fetch')).catch(()=>{});
        } else if (rVote.test(url) && method === 'POST'){
          res.clone().json().then(d => onVote(reqBody, d)).catch(()=>{});
        }
      }catch(e){}
      return res;
    };
    STATE.fetchWrapped = true;
    dbg('wrapped fetch');
  })();

  // Catch XHR
  (function wrapXHR(){
    if (STATE.xhrWrapped) return;
    if (!window.XMLHttpRequest) return;
    const rList = /\/comments\/list(?:\/|\?|$)/;
    const rVote = /\/comments\/vote(?:\/|\?|$)/;
    const Orig = window.XMLHttpRequest;
    function X(){
      const xhr = new Orig();
      xhr.__h = { m:'GET', u:'', b:null };
      const oOpen = xhr.open;
      xhr.open = function(m,u){ xhr.__h.m=(m||'GET').toUpperCase(); xhr.__h.u=u||''; return oOpen.apply(xhr, arguments); };
      const oSend = xhr.send;
      xhr.send = function(b){
        xhr.__h.b = b || null;
        xhr.addEventListener('load', function(){
          try{
            const url = xhr.__h.u, m = xhr.__h.m;
            let data=null; try{ data = xhr.responseType==='json' ? xhr.response : JSON.parse(xhr.responseText); }catch(_){}
            let req=null; try{
              const rb = xhr.__h.b;
              if (typeof rb==='string' && rb.trim().startsWith('{')) req=JSON.parse(rb);
              else if (rb instanceof FormData){ const o={}; rb.forEach((v,k)=>o[k]=v); req=o; }
            }catch(_){}
            if (!data) return;
            if (rList.test(url) && m==='GET'){ onList(data, 'xhr'); }
            else if (rVote.test(url) && m==='POST'){ onVote(req, data); }
          }catch(_){}
        });
        return oSend.apply(xhr, arguments);
      };
      return xhr;
    }
    window.XMLHttpRequest = X;
    STATE.xhrWrapped = true;
    dbg('wrapped xhr');
  })();

  // Normalize buttons and start fetch
  listEl.querySelectorAll('.btn-like').forEach(normalizeHeart);
  setTimeout(initialFetchOnce, 50);

  // On DOM mutation stay single knob and reapply curr. params
  const mo = new MutationObserver(() => {
    listEl.querySelectorAll('.btn-like').forEach(normalizeHeart);
    applyHearts();
  });
  mo.observe(listEl, { childList: true, subtree: true });

  dbg('addon ready');
})();