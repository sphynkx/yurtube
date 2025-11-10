// Wire up UI events
(function(){
  const root = document.getElementById('comments-root');
  if (!root) return;

  const videoId = root.dataset.videoId || '';
  const listEl = document.getElementById('comments-list');
  const btnSend = document.getElementById('comment-send');
  const btnRefresh = document.getElementById('comment-refresh');
  const ta = document.getElementById('comment-text');
  const INLINE_LIMIT = 3;

  async function load() {
    try {
      const data = await CommentsAPI.list(videoId, false);
      CommentsTree.renderTree(listEl, {
        roots: data.roots || [],
        children_map: data.children_map || {},
        comments: data.comments || {}
      }, data.texts || {}, INLINE_LIMIT);
    } catch (e) {
      listEl.innerHTML = '<div class="comments-empty">No comments.</div>';
    }
  }

  // Simple delegation for like/dislike
  listEl.addEventListener('click', async (e) => {
    const btn = e.target.closest('.btn-like, .btn-dislike, .btn-reply');
    if (!btn) return;
    const cid = btn.getAttribute('data-cid');
    if (!cid) return;

    if (btn.classList.contains('btn-reply')) {
      // Prepend reply hint
      const authorTitle = btn.closest('.comment-item')?.querySelector('.comment-title')?.textContent || '';
      if (ta) {
        const prefix = `For @${authorTitle}: `;
        if (!ta.value.startsWith(prefix)) {
          ta.value = prefix + ta.value;
        }
        ta.focus();
      }
      return;
    }

    const delta = parseInt(btn.getAttribute('data-delta') || '0', 10);
    const payload = {
      video_id: videoId,
      comment_id: cid,
      delta_like: delta > 0 ? 1 : 0,
      delta_dislike: delta < 0 ? 1 : 0
    };
    try {
      await CommentsAPI.like(payload);
      // Optimistic update UI
      const span = btn.querySelector('span');
      if (span) span.textContent = String(parseInt(span.textContent || '0',10) + 1);
    } catch (e) {
      console.warn('like failed', e);
    }
  });

  btnSend?.addEventListener('click', async () => {
    const text = (ta?.value || '').trim();
    if (!text) return;
    if (text.length > 1000) return;

    try {
      await CommentsAPI.create({ video_id: videoId, text });
      ta.value = '';
      await load();
    } catch (e) {
      console.warn('create failed', e);
    }
  });

  btnRefresh?.addEventListener('click', load);

  load();
})();