const CommentsTree = (() => {
  function fmtTime(unix){
    if (!unix || isNaN(unix)) return '';
    const d = new Date(unix * 1000);
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,'0');
    const da= String(d.getDate()).padStart(2,'0');
    const hh= String(d.getHours()).padStart(2,'0');
    const mm= String(d.getMinutes()).padStart(2,'0');
    return `${y}-${m}-${da} ${hh}:${mm}`;
  }

  function renderTree(container, payload, texts, inlineLimit, opts){
    container.innerHTML = '';
    const { roots, children_map, comments } = payload;
    const currentUid = (opts && opts.currentUid) || '';

    function node(cid){
      const meta = comments[cid]; if (!meta) return document.createElement('div');
      const div = document.createElement('div'); div.className = 'comment-item';
      if (!meta.visible) div.classList.add('comment-hidden');

      const head = document.createElement('div'); head.className = 'comment-head';
      const author = document.createElement('span'); author.className = 'comment-author';
      author.textContent = meta.author_name || meta.author_uid || 'User';
      const time = document.createElement('span'); time.className = 'comment-time';
      time.textContent = fmtTime(meta.created_at || 0) + (meta.edited ? ' (edited)' : '');
      head.appendChild(author); head.appendChild(time);

      const body = document.createElement('div'); body.className = 'comment-text';
      const lid = meta.chunk_ref?.local_id; body.textContent = (lid && texts[lid]) ? texts[lid] : '';

      const actions = document.createElement('div'); actions.className = 'comment-actions';
      const like = document.createElement('button'); like.className = 'btn-like'; like.dataset.cid = cid; like.dataset.vote = '1';
      like.innerHTML = `👍 <span>${meta.likes||0}</span>`;
      const dislike = document.createElement('button'); dislike.className = 'btn-dislike'; dislike.dataset.cid = cid; dislike.dataset.vote = '-1';
      dislike.innerHTML = `👎 <span>${meta.dislikes||0}</span>`;
      if ((meta.my_vote||0) === 1) like.classList.add('active');
      if ((meta.my_vote||0) === -1) dislike.classList.add('active');
      actions.appendChild(like); actions.appendChild(dislike);

      div.appendChild(head); div.appendChild(body); div.appendChild(actions);

      const kids = children_map[cid] || [];
      if (kids.length){
        const subtree = document.createElement('div'); subtree.className = 'comment-children';
        const visible = kids.slice(0, inlineLimit); const collapsed = kids.slice(inlineLimit);
        visible.forEach(k => subtree.appendChild(node(k)));
        if (collapsed.length){
          const more = document.createElement('button'); more.className='btn-more'; more.textContent=`+ ${collapsed.length} more`;
          more.addEventListener('click', ()=>{ collapsed.forEach(k => subtree.appendChild(node(k))); more.remove(); });
          subtree.appendChild(more);
        }
        div.appendChild(subtree);
      }
      return div;
    }

    roots.forEach(cid => container.appendChild(node(cid)));
    if (!roots.length){
      const empty = document.createElement('div'); empty.className='comments-empty'; empty.textContent='No comments..'; container.appendChild(empty);
    }
  }

  return { renderTree };
})();