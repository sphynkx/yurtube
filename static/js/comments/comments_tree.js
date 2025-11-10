// Render comments tree with metadata and owner-only actions
const CommentsTree = (() => {

  function fmtTime(unix) {
    if (!unix || isNaN(unix)) return '';
    const d = new Date(unix * 1000);
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,'0');
    const da= String(d.getDate()).padStart(2,'0');
    const hh= String(d.getHours()).padStart(2,'0');
    const mm= String(d.getMinutes()).padStart(2,'0');
    return `${y}-${m}-${da} ${hh}:${mm}`;
  }

  function renderTree(container, payload, texts, inlineLimit, opts) {
    container.innerHTML = '';
    const { roots, children_map, comments } = payload;
    const currentUid = (opts && opts.currentUid) || '';

    function createCommentNode(cid) {
      const meta = comments[cid];
      const div  = document.createElement('div');
      div.className = 'comment-item';
      if (!meta.visible) div.classList.add('comment-hidden');

      const head = document.createElement('div');
      head.className = 'comment-head';
      const author = document.createElement('span');
      author.className = 'comment-author';
      author.textContent = meta.author_name || meta.author_uid || 'User';
      const time = document.createElement('span');
      time.className = 'comment-time';
      time.textContent = fmtTime(meta.created_at || 0) + (meta.edited ? ' (edited)' : '');
      head.appendChild(author);
      head.appendChild(time);

      const body = document.createElement('div');
      body.className = 'comment-text';
      const lid = meta.chunk_ref?.local_id;
      body.textContent = (lid && texts[lid]) ? texts[lid] : '';

      const actions = document.createElement('div');
      actions.className = 'comment-actions';
      actions.innerHTML = `
        <button class="btn-like" data-cid="${cid}" data-delta="1" title="Like">👍 <span>${meta.likes||0}</span></button>
        <button class="btn-dislike" data-cid="${cid}" data-delta="-1" title="Dislike">👎 <span>${meta.dislikes||0}</span></button>
      `;
      if (currentUid && String(meta.author_uid) === String(currentUid)) {
        const ownerTools = document.createElement('span');
        ownerTools.className = 'owner-tools';
        ownerTools.innerHTML = `
          <button class="btn-edit" data-cid="${cid}" title="Edit (TODO)">✎</button>
          <button class="btn-remove" data-cid="${cid}" title="Remove (TODO)">🗑</button>
        `;
        actions.appendChild(ownerTools);
      }

      div.appendChild(head);
      div.appendChild(body);
      div.appendChild(actions);

      const kids = children_map[cid] || [];
      if (kids.length) {
        const subtree = document.createElement('div');
        subtree.className = 'comment-children';
        const visible = kids.slice(0, inlineLimit);
        const collapsed = kids.slice(inlineLimit);
        visible.forEach(k => subtree.appendChild(createCommentNode(k)));
        if (collapsed.length) {
          const more = document.createElement('button');
          more.className = 'btn-more';
          more.textContent = `+ ${collapsed.length} more`;
          more.addEventListener('click', () => {
            collapsed.forEach(k => subtree.appendChild(createCommentNode(k)));
            more.remove();
          });
          subtree.appendChild(more);
        }
        div.appendChild(subtree);
      }
      return div;
    }

    roots.forEach(cid => container.appendChild(createCommentNode(cid)));
    if (!roots.length) {
      const empty = document.createElement('div');
      empty.className = 'comments-empty';
      empty.textContent = 'No comments..';
      container.appendChild(empty);
    }

    // Delegated like/dislike (w/o once)
    container.addEventListener('click', async (e) => {
      const btn = e.target.closest('.btn-like, .btn-dislike');
      if (!btn) return;
      const cid = btn.getAttribute('data-cid');
      if (!cid) return;
      const delta = parseInt(btn.getAttribute('data-delta') || '0', 10);
      const payload = window.CommentsTreeVideoId
        ? { video_id: window.CommentsTreeVideoId, comment_id: cid,
            delta_like: delta > 0 ? 1 : 0, delta_dislike: delta < 0 ? 1 : 0 }
        : null;
      if (!payload) return;
      // simple block for repeating increm.(MVP)
      if (btn.dataset.locked === '1') return;
      try {
        await CommentsAPI.like(payload);
        const span = btn.querySelector('span');
        if (span) span.textContent = String(parseInt(span.textContent || '0', 10) + 1);
        btn.dataset.locked = '1';
      } catch (err) {
        console.warn('like failed', err);
      }
    });
  }

  return { renderTree };
})();