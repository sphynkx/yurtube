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
    const avatars = (opts && opts.avatars) || {};

    function node(cid){
      const meta = comments[cid];
      if (!meta) return document.createElement('div');

      const div = document.createElement('div');
      div.className = 'comment-item';
      if (!meta.visible) div.classList.add('comment-hidden');

      const head = document.createElement('div');
      head.className = 'comment-head';

      const avatarImg = document.createElement('img');
      avatarImg.className = 'comment-avatar';
      avatarImg.src = avatars[meta.author_uid] || '/static/img/avatar_default.svg';
      avatarImg.alt = '';
      head.appendChild(avatarImg);

      const authorWrap = document.createElement('span');
      authorWrap.className = 'comment-author';
      if (meta.author_name) {
        const link = document.createElement('a');
        link.href = '/@' + meta.author_name;
        link.textContent = meta.author_name;
        authorWrap.appendChild(link);
      } else {
        authorWrap.textContent = meta.author_uid || 'User';
      }
      head.appendChild(authorWrap);

      const time = document.createElement('span');
      time.className = 'comment-time';
      time.textContent = fmtTime(meta.created_at || 0) + (meta.edited ? ' (edited)' : '');
      head.appendChild(time);

      const body = document.createElement('div');
      body.className = 'comment-text';
      const lid = meta.chunk_ref?.local_id;
      const originalTxt = (lid && texts[lid]) ? texts[lid] : '';
      body.textContent = meta.visible ? originalTxt : '[deleted]';

      const actions = document.createElement('div');
      actions.className = 'comment-actions';

      const like = document.createElement('button');
      like.className = 'btn-like';
      like.dataset.cid = cid;
      like.dataset.vote = '1';
      like.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M9 21h9a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-5.31l.95-4.57.02-.23a1 1 0 0 0-.3-.7L12.17 3 6.59 8.59A2 2 0 0 0 6 10v9a2 2 0 0 0 2 2h1z"/></svg><span>${meta.likes||0}</span>`;
      if ((meta.my_vote||0) === 1) like.classList.add('active');

      const dislike = document.createElement('button');
      dislike.className = 'btn-dislike';
      dislike.dataset.cid = cid;
      dislike.dataset.vote = '-1';
      dislike.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M15 3H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h5.31l-.95 4.57-.02.23a1 1 0 0 0 .3.7l1.49 1.5 5.58-5.59A2 2 0 0 0 18 14V5a2 2 0 0 0-2-2h-1z"/></svg><span>${meta.dislikes||0}</span>`;
      if ((meta.my_vote||0) === -1) dislike.classList.add('active');

      actions.appendChild(like);
      actions.appendChild(dislike);

      if (currentUid && meta.author_uid === currentUid && meta.visible){
        const editBtn = document.createElement('button');
        editBtn.className = 'btn-edit';
        editBtn.dataset.cid = cid;
        editBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM21.41 6.34a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>`;
        actions.appendChild(editBtn);

        const delBtn = document.createElement('button');
        delBtn.className = 'btn-delete';
        delBtn.dataset.cid = cid;
        delBtn.innerHTML  = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M6 7h12l-1 12H7L6 7zm5-5h2l1 1h5v2H5V3h5l1-1z"/></svg>`;
        actions.appendChild(delBtn);
      }

      div.appendChild(head);
      div.appendChild(body);
      div.appendChild(actions);

      const kids = children_map[cid] || [];
      if (kids.length){
        const subtree = document.createElement('div');
        subtree.className = 'comment-children';
        const visibleKids = kids.slice(0, inlineLimit);
        const collapsed = kids.slice(inlineLimit);
        visibleKids.forEach(k => subtree.appendChild(node(k)));
        if (collapsed.length){
          const more = document.createElement('button');
            more.className='btn-more';
            more.textContent=`+ ${collapsed.length} more`;
            more.addEventListener('click', ()=>{
              collapsed.forEach(k => subtree.appendChild(node(k)));
              more.remove();
            });
          subtree.appendChild(more);
        }
        div.appendChild(subtree);
      }
      return div;
    }

    roots.forEach(cid => container.appendChild(node(cid)));
    if (!roots.length){
      const empty = document.createElement('div');
      empty.className='comments-empty';
      empty.textContent='No comments..';
      container.appendChild(empty);
    }

    if (!container.dataset.editsBound){
      container.addEventListener('click', async (e) => {
        const editBtn = e.target.closest('.btn-edit');
        const delBtn  = e.target.closest('.btn-delete');

        if (editBtn){
          const cid = editBtn.dataset.cid;
          const item = editBtn.closest('.comment-item');
          if (!item) return;
          const body = item.querySelector('.comment-text');
          if (!body) return;
          if (item.querySelector('.edit-area')) return;

          const orig = body.textContent;
          const lid = comments[cid]?.chunk_ref?.local_id;
          const txtRaw = comments[cid]?.visible ? ((lid && texts[lid]) || '') : '';
          body.innerHTML = '';

          const ta = document.createElement('textarea');
          ta.className = 'edit-area';
          ta.value = txtRaw;
          ta.rows = 3;
          ta.style.width = '100%';
          ta.maxLength = 1000;
          body.appendChild(ta);

          const bar = document.createElement('div');
          bar.style.marginTop = '6px';
          bar.style.display = 'flex';
          bar.style.gap = '8px';

          const btnSave = document.createElement('button');
          btnSave.textContent = 'Save';
          btnSave.className = 'btn-edit-save';

          const btnCancel = document.createElement('button');
          btnCancel.textContent = 'Cancel';
          btnCancel.className = 'btn-edit-cancel';

          bar.appendChild(btnSave);
          bar.appendChild(btnCancel);
          body.appendChild(bar);

          btnCancel.addEventListener('click', ()=>{ body.textContent = orig; });

          btnSave.addEventListener('click', async () => {
            const newText = (ta.value || '').trim();
            if (!newText) return;
            try{
              await CommentsAPI.update({ video_id: window.CommentsTreeVideoId, comment_id: cid, text: newText });
              body.textContent = newText;
              const headTime = item.querySelector('.comment-time');
              if (headTime && !/edited/.test(headTime.textContent)){
                headTime.textContent = headTime.textContent + ' (edited)';
              }
            }catch(err){
              console.warn('update failed', err);
              body.textContent = orig;
            }
          });
          return;
        }

        if (delBtn){
          const cid = delBtn.dataset.cid;
          if (!cid) return;
          try{
            await CommentsAPI.remove({ video_id: window.CommentsTreeVideoId, comment_id: cid });
            const item = delBtn.closest('.comment-item');
            if (item){
              item.classList.add('comment-hidden');
              const body = item.querySelector('.comment-text');
              if (body) body.textContent = '[deleted]';
              const ed = item.querySelector('.btn-edit');
              if (ed) ed.remove();
              delBtn.remove();
            }
          }catch(err){
            console.warn('delete failed', err);
          }
          return;
        }
      });
      container.dataset.editsBound = '1';
    }
  }

  return { renderTree };
})();