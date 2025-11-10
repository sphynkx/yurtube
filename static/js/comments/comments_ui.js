// Comments UI wiring: composer + list refresh + relocate between placeholders
(function(){
  // Build comment tree one, thir block moves between placeholders
  const rootEl = document.getElementById('comments-root');
  if (!rootEl) return;

  const videoId    = rootEl.dataset.videoId || '';
  const currentUid = rootEl.dataset.currentUid || '';
  const maxLen     = parseInt(rootEl.dataset.maxLen || '1000', 10);

  // forwarding for likes
  window.CommentsTreeVideoId = videoId;

  // find placeholders
  const mountWidePH   = document.querySelector('#comments-mount-wide .comments-placeholder');
  const mountNarrowPH = document.querySelector('#comments-mount-narrow .comments-placeholder');

  function isNarrow(){ return window.matchMedia('(max-width:1100px)').matches; }
  function moveBlock(){
    if (!mountWidePH || !mountNarrowPH) return;
    if (isNarrow()){
      if (mountNarrowPH.contains(rootEl)) return;
      mountNarrowPH.innerHTML = ''; // clean placeholder
      mountNarrowPH.appendChild(rootEl);
    } else {
      if (mountWidePH.contains(rootEl)) return;
      mountWidePH.innerHTML = ''; // clean placeholder
      mountWidePH.appendChild(rootEl);
    }
  }
  moveBlock();
  window.addEventListener('resize', moveBlock);

  const listEl   = document.getElementById('comments-list');
  const ta       = document.getElementById('comment-textarea');
  const actions  = document.getElementById('composer-actions');
  const btnCancel= document.getElementById('comment-cancel');
  const btnPost  = document.getElementById('comment-post');

  function showActions(){ if (actions) actions.hidden = false; }
  function hideActions(){ if (actions) actions.hidden = true; }
  function resetComposer(){
    if (ta) ta.value = '';
    hideActions();
    if (btnPost) btnPost.disabled = true;
  }
  function validate(){
    const v = (ta?.value || '').trim();
    const ok = v.length > 0 && v.length <= maxLen;
    if (btnPost) btnPost.disabled = !ok;
  }

  ta?.addEventListener('focus', showActions);
  ta?.addEventListener('input', validate);
  btnCancel?.addEventListener('click', resetComposer);

  btnPost?.addEventListener('click', async () => {
    const text = (ta?.value || '').trim();
    if (!text || text.length > maxLen) return;
    try {
      await CommentsAPI.create({ video_id: videoId, text });
      resetComposer();
      await load();
    } catch (e) {
      console.warn('create failed', e);
    }
  });

  async function load(){
    try {
      const data = await CommentsAPI.list(videoId, false);
      CommentsTree.renderTree(
        listEl,
        { roots: data.roots || [], children_map: data.children_map || {}, comments: data.comments || {} },
        data.texts || {},
        3,
        { currentUid }
      );
    } catch (e){
      listEl.innerHTML = '<div class="comments-empty">No comments..</div>';
    }
  }

  load();
})();