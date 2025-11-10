// Helpers to render tree and collapse branches
const CommentsTree = (() => {
  function renderTree(container, payload, texts, inlineLimit) {
    container.innerHTML = '';
    const { roots, children_map, comments } = payload;

    function createCommentNode(cid) {
      const meta = comments[cid];
      const div = document.createElement('div');
      div.className = 'comment-item';
      if (!meta.visible) div.classList.add('comment-hidden');

      const body = document.createElement('div');
      body.className = 'comment-body';
      const title = document.createElement('div');
      title.className = 'comment-title';
      title.textContent = meta.author_name || 'User';

      const txt = document.createElement('div');
      txt.className = 'comment-text';
      const lid = meta.chunk_ref?.local_id;
      txt.textContent = lid && texts[lid] ? texts[lid] : '';

      const actions = document.createElement('div');
      actions.className = 'comment-actions';
      actions.innerHTML = `
        <button class="btn-like" data-cid="${cid}" data-delta="1" title="Like">👍 <span>${meta.likes||0}</span></button>
        <button class="btn-dislike" data-cid="${cid}" data-delta="-1" title="Dislike">👎 <span>${meta.dislikes||0}</span></button>
        <button class="btn-reply" data-cid="${cid}" title="Reply">↩</button>
      `;

      body.appendChild(title);
      body.appendChild(txt);
      body.appendChild(actions);

      div.appendChild(body);

      // children
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
      empty.textContent = 'No comments.';
      container.appendChild(empty);
    }
  }

  return { renderTree };
})();