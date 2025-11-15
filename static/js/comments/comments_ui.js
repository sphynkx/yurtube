(function(){
  if (window.__comments_ui_once) return;
  window.__comments_ui_once = true;

  const root = document.getElementById('comments-root');
  if (!root) return;

  const rootHome = root.parentElement;

  function isNarrow(){ return window.matchMedia('(max-width:1100px)').matches; }
  function getNarrowTarget(){
    return document.getElementById('comments-mount-narrow')
        || document.getElementById('panel-comments')
        || null;
  }
  function moveToNarrow(){
    const target = getNarrowTarget();
    if (target && !target.contains(root)) target.appendChild(root);
  }
  function moveToWide(){
    if (rootHome && root.parentElement !== rootHome) rootHome.appendChild(root);
  }
  function relocate(){
    if (isNarrow()) moveToNarrow(); else moveToWide();
  }

  // Move on start or on resize
  relocate();
  window.addEventListener('resize', relocate);

  // Move by click on Comments tab
  const tabBtn = document.getElementById('tab-comments');
  tabBtn?.addEventListener('click', () => { moveToNarrow(); });

  const videoId    = root.dataset.videoId || '';
  const currentUid = root.dataset.currentUid || '';
  const maxLen     = parseInt(root.dataset.maxLen || '1000', 10);
  window.CommentsTreeVideoId = videoId;

  const listEl    = document.getElementById('comments-list');
  const ta        = document.getElementById('comment-textarea');
  const actions   = document.getElementById('composer-actions');
  const btnCancel = document.getElementById('comment-cancel');
  const btnPost   = document.getElementById('comment-post');
  const countEl   = document.getElementById('comments-count');

  let isPosting = false;

  function showActions(){ if (actions) actions.hidden = false; }
  function hideActions(){ if (actions) actions.hidden = true; }
  function validate(){
    const v=(ta?.value||'').trim();
    const ok = v.length>0 && v.length<=maxLen && !isPosting;
    if (btnPost) btnPost.disabled = !ok;
  }
  function resetComposer(){
    if (ta) ta.value = '';
    hideActions();
    isPosting = false;
    if (btnPost) btnPost.disabled = true;
  }

  ta?.addEventListener('focus', showActions);
  ta?.addEventListener('input', validate);
  btnCancel?.addEventListener('click', resetComposer);

  btnPost?.addEventListener('click', async () => {
    if (isPosting) return;
    const text = (ta?.value||'').trim();
    if (!text || text.length>maxLen) return;
    isPosting = true; validate();
    try{
      await CommentsAPI.create({ video_id: videoId, text });
      resetComposer();
      await load();
    }catch(e){
      console.warn('create failed', e);
      isPosting = false; validate();
    }
  });

  if (!listEl.dataset.voteBound){
    listEl.addEventListener('click', async (e) => {
      const like = e.target.closest('.btn-like');
      const dislike = e.target.closest('.btn-dislike');
      const btn = like || dislike; if (!btn) return;
      const cid = btn.dataset.cid; if (!cid) return;
      const isLike = !!like;
      const otherSel = isLike ? '.btn-dislike' : '.btn-like';
      const other = btn.parentElement.querySelector(`${otherSel}[data-cid="${cid}"]`);
      const wasActive = btn.classList.contains('active');
      const want = wasActive ? 0 : (isLike ? 1 : -1);
      try{
        const res = await CommentsAPI.vote({ video_id: videoId, comment_id: cid, vote: want });
        if (!res || !res.ok) return;
        const likeBtn = isLike ? btn : other;
        const dislikeBtn = isLike ? other : btn;
        if (likeBtn){
          const s = likeBtn.querySelector('.count'); if (s) s.textContent = String(res.likes);
          likeBtn.classList.toggle('active', res.my_vote === 1);
        }
        if (dislikeBtn){
          const s = dislikeBtn.querySelector('.count'); if (s) s.textContent = String(res.dislikes);
          dislikeBtn.classList.toggle('active', res.my_vote === -1);
        }
      }catch(err){ console.warn('vote failed', err); }
    });
    listEl.dataset.voteBound = '1';
  }

  async function load(){
    try{
      const data = await CommentsAPI.list(videoId, false);

      // video author uid + moderator flag
      const vAuthor = data.video_author_uid || data.author_uid || '';
      if (vAuthor){
        root.dataset.videoAuthorUid = vAuthor;
      }
      // Flag from BE
      let moderatorFlag = !!data.moderator;
      // Fallback: if no data and curr user is author
      if (!moderatorFlag && vAuthor && currentUid && vAuthor === currentUid){
        moderatorFlag = true;
      }

      // Send all fields and moderator also (need for Del button)
      CommentsTree.renderTree(
        listEl,
        {
          roots: data.roots || [],
          children_map: data.children_map || {},
          comments: data.comments || {},
          moderator: moderatorFlag,
          video_author_uid: vAuthor
        },
        data.texts || {},
        3,
        { currentUid, avatars: data.avatars || {} }
      );

      // Refresh counter
      if (countEl){
        const all = data.comments || {};
        const visibleCount = Object.values(all).filter(m => m && m.visible).length;
        if (visibleCount > 0){
          countEl.hidden = false;
          countEl.textContent = `${visibleCount} comment${visibleCount===1?'':'s'}`;
        } else {
          countEl.hidden = true;
          countEl.textContent = '';
        }
      }
    }catch(e){
      listEl.innerHTML = '<div class="comments-empty">No comments..</div>';
      if (countEl){ countEl.hidden = true; countEl.textContent = ''; }
    }
  }

  // export global reload
  window.CommentsReload = load;

  load();
})();
