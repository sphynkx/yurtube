/**
 * CommentsTree
 * - Reply / Edit / Delete / Like / Dislike
 * - Tombstone ("Removed") minimal node
 * - Mention linking: "@username: ..." -> <a href="/@username">@username</a>
 * - contenteditable reply editor with blue, deletable "@username: "
 * - Global state refreshed each render (no stale closures)
 */

const CommentsTree = (() => {

  const state = {
    activeReplyBox: null,
    replyParentCid: null,
    bound: false,
    comments: {},
    children_map: {},
    texts: {},
    avatars: {},
    currentUid: '',
    isModerator: false,   // get from /comments/list
    inlineLimit: 3,
    MAX_DEPTH: 5
  };

  function fmtTime(unix){
    if (!unix || isNaN(unix)) return '';
    const ts = (unix < 2_000_000_0000) ? (unix * 1000) : unix; // < ~2033 in seconds
    const d = new Date(ts);
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,'0');
    const da= String(d.getDate()).padStart(2,'0');
    const hh= String(d.getHours()).padStart(2,'0');
    const mm= String(d.getMinutes()).padStart(2,'0');
    return `${y}-${m}-${da} ${hh}:${mm}`;
  }

  function depthOf(cid){
    let d = 0, cur = cid;
    while (cur && state.comments[cur] && state.comments[cur].parent_id){
      d++;
      cur = state.comments[cur].parent_id;
      if (d > 50) break;
    }
    return d;
  }
  function clampParentForDepth(targetCid){
    let d = depthOf(targetCid);
    let cur = targetCid;
    while (d >= state.MAX_DEPTH - 1 && state.comments[cur] && state.comments[cur].parent_id){
      cur = state.comments[cur].parent_id;
      d = depthOf(cur);
    }
    return cur;
  }

  // contenteditable reply composer with blue @mention
  function buildReplyComposer(parentCid, parentMeta){
    const wrapper = document.createElement('div');
    wrapper.className = 'reply-composer';

    const ed = document.createElement('div');
    ed.className = 'reply-editor';
    ed.contentEditable = 'true';
    ed.spellcheck = true;
    const uname = parentMeta.author_name || parentMeta.author_uid || 'user';
    ed.innerHTML = `<span class="mention">@${uname}</span>: `; // deletable

    const bar = document.createElement('div');
    bar.className = 'reply-actions';

    const btnCancel = document.createElement('button');
    btnCancel.type = 'button';
    btnCancel.className = 'btn-secondary reply-cancel';
    btnCancel.textContent = 'Cancel';

    const btnSend = document.createElement('button');
    btnSend.type = 'button';
    btnSend.className = 'btn-primary reply-send';
    btnSend.textContent = 'Reply';
    btnSend.disabled = true;

    function currentText(){
      // innerText gives plain text like "@user: rest"
      return (ed.innerText || '').replace(/\u00A0/g,' ').trim();
    }
    ed.addEventListener('input', ()=>{ btnSend.disabled = currentText().length === 0; });

    btnCancel.addEventListener('click', ()=>{
      if (state.activeReplyBox){
        state.activeReplyBox.remove();
        state.activeReplyBox = null;
        state.replyParentCid = null;
      }
    });

    btnSend.addEventListener('click', async ()=>{
      const raw = currentText();
      if (!raw) return;
      btnSend.disabled = true;
      try{
        const finalParent = clampParentForDepth(parentCid);
        await CommentsAPI.create({
          video_id: window.CommentsTreeVideoId,
          text: raw,
          parent_id: finalParent
        });
        state.activeReplyBox = null;
        state.replyParentCid = null;
        window.CommentsReload && window.CommentsReload();
      }catch(e){
        console.warn('reply failed', e);
        btnSend.disabled = false;
      }
    });

    bar.appendChild(btnCancel);
    bar.appendChild(btnSend);
    wrapper.appendChild(ed);
    wrapper.appendChild(bar);
    setTimeout(()=>{ // place cursor at end
      ed.focus();
      const sel = window.getSelection();
      if (sel && sel.rangeCount){
        sel.collapse(ed, ed.childNodes.length);
      }
    }, 10);
    return wrapper;
  }

  // Render comment text; '@username: ' -> link; any inline @username -> link
  function renderText(originalTxt, visible){
    if (!visible){
      const d = document.createElement('div');
      d.className = 'comment-text';
      d.textContent = '[deleted]';
      return d;
    }
    const div = document.createElement('div');
    div.className = 'comment-text';

    const prefixMatch = originalTxt.match(/^\@([A-Za-z0-9_-]{1,64})\:\s*(.*)$/);
    if (prefixMatch){
      const uname = prefixMatch[1];
      const rest  = prefixMatch[2] || '';
      const a = document.createElement('a');
      a.className = 'mention';
      a.href = '/@' + uname;
      a.textContent = '@' + uname;
      div.appendChild(a);
      div.appendChild(document.createTextNode(': ' + rest));
      return div;
    }

    const parts = originalTxt.split(/(\@[A-Za-z0-9_-]{1,64})/g);
    parts.forEach(p=>{
      if (/^\@[A-Za-z0-9_-]{1,64}$/.test(p)){
        const uname = p.slice(1);
        const a = document.createElement('a');
        a.className = 'mention';
        a.href = '/@' + uname;
        a.textContent = p;
        div.appendChild(a);
      } else {
        div.appendChild(document.createTextNode(p));
      }
    });
    return div;
  }

  function node(cid){
    const meta = state.comments[cid];
    if (!meta) return document.createElement('div');

    if (meta.tombstone){
      const tomb = document.createElement('div');
      tomb.className = 'comment-item comment-tombstone';
      const body = document.createElement('div');
      body.className = 'comment-text comment-tombstone';
      body.textContent = 'Removed';
      tomb.appendChild(body);

      const kidsRaw = state.children_map[cid] || [];
      const kids = kidsRaw.filter(k => !!state.comments[k]);
      if (kids.length){
        const subtree = document.createElement('div');
        subtree.className = 'comment-children';
        const visibleKids = kids.slice(0, state.inlineLimit);
        const collapsed = kids.slice(state.inlineLimit);
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
        tomb.appendChild(subtree);
      }
      return tomb;
    }

    const div = document.createElement('div');
    div.className = 'comment-item';
    if (!meta.visible) div.classList.add('comment-hidden');

    const head = document.createElement('div');
    head.className = 'comment-head';

    const avatarImg = document.createElement('img');
    avatarImg.className = 'comment-avatar';
    avatarImg.src = state.avatars[meta.author_uid] || '/static/img/avatar_default.svg';
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

    const lid = meta.chunk_ref?.local_id;
    let originalTxt = (lid && state.texts[lid]) ? state.texts[lid] : '';
    if (!originalTxt && meta.cached_text) originalTxt = meta.cached_text;
    const bodyNode = renderText(originalTxt, meta.visible);

    const actions = document.createElement('div');
    actions.className = 'comment-actions';

    const interactive = meta.visible === true;

    if (interactive){
      const like = document.createElement('button');
      like.className = 'btn-like';
      like.dataset.cid = cid;
      like.dataset.vote = '1';
	  like.dataset.videoId = meta.video_id || window.CommentsTreeVideoId || '';
      // Heart + count
      like.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18">
          <path d="M9 21h9a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-5.31l.95-4.57.02-.23a1 1 0 0 0-.3-.7L12.17 3 6.59 8.59A2 2 0 0 0 6 10v9a2 2 0 0 0 2 2h1z"/>
        </svg><span class="count">${meta.likes||0}</span><span class="author-heart" data-cid="${cid}" style="display:none">❤</span>`;
      if ((meta.my_vote||0) === 1) like.classList.add('active');
      // Show heart if has flag
      const heartSpan = like.querySelector('.author-heart');
      if (heartSpan && meta.liked_by_author === true) {
        heartSpan.style.display = 'inline';
      }
      actions.appendChild(like);

      const dislike = document.createElement('button');
      dislike.className = 'btn-dislike';
      dislike.dataset.cid = cid;
      dislike.dataset.vote = '-1';
	  dislike.dataset.videoId = meta.video_id || window.CommentsTreeVideoId || '';
      dislike.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18">
          <path d="M15 3H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h5.31l-.95 4.57-.02.23a1 1 0 0 0 .3.7l1.49 1.5 5.58-5.59A2 2 0 0 0 18 14V5a2 2 0 0 0-2-2h-1z"/>
        </svg><span class="count">${meta.dislikes||0}</span>`;
      if ((meta.my_vote||0) === -1) dislike.classList.add('active');
      actions.appendChild(dislike);

      const replyBtn = document.createElement('button');
      replyBtn.className = 'btn-reply';
      replyBtn.dataset.cid = cid;
      replyBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16">
          <path d="M10 7V4l-6 6 6 6v-3h2c3.59 0 6.5 3.582 6.5 8v1h1v-1c0-5.514-3.582-10-8-10H10z"/>
        </svg>`;
      actions.appendChild(replyBtn);

      // Edit - for video's aithor only
      if (state.currentUid && meta.author_uid === state.currentUid){
        const editBtn = document.createElement('button');
        editBtn.className = 'btn-edit';
        editBtn.dataset.cid = cid;
        editBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16">
            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM21.41 6.34a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
          </svg>`;
        actions.appendChild(editBtn);
      }

      // Delete - for comment author and moderator (author of video)
      if ( (state.currentUid && meta.author_uid === state.currentUid) || state.isModerator ){
        const delBtn = document.createElement('button');
        delBtn.className = 'btn-delete';
        delBtn.dataset.cid = cid;
        delBtn.innerHTML  = `<svg viewBox="0 0 24 24" width="16" height="16">
            <path d="M6 7h12l-1 12H7L6 7zm5-5h2l1 1h5v2H5V3h5l1-1z"/>
          </svg>`;
        actions.appendChild(delBtn);
      }
    }

    div.appendChild(head);
    div.appendChild(bodyNode);
    div.appendChild(actions);

    const kidsRaw = state.children_map[cid] || [];
    const kids = kidsRaw.filter(k => !!state.comments[k]);
    if (kids.length){
      const subtree = document.createElement('div');
      subtree.className = 'comment-children';
      const visibleKids = kids.slice(0, state.inlineLimit);
      const collapsed = kids.slice(state.inlineLimit);
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

  function render(container, payload, texts, inlineLimit, opts){
    state.comments = payload.comments || {};
    state.children_map = payload.children_map || {};
    state.texts = texts || {};
    state.currentUid = (opts && opts.currentUid) || '';
    state.avatars = (opts && opts.avatars) || {};
    state.inlineLimit = inlineLimit || 3;
    state.isModerator = !!payload.moderator;   // read moderator flag from API

    container.innerHTML = '';
    const roots = payload.roots || [];
    roots.forEach(cid => container.appendChild(node(cid)));
    if (!roots.length){
      const empty = document.createElement('div');
      empty.className='comments-empty';
      empty.textContent='No comments..';
      container.appendChild(empty);
    }

    if (!state.bound){
      container.addEventListener('click', async (e) => {
        const replyBtn = e.target.closest('.btn-reply');
        if (replyBtn){
          const cid = replyBtn.dataset.cid;
          if (!cid) return;
          const meta = state.comments[cid];
          if (!meta || !meta.visible || meta.tombstone) return;
          const item = replyBtn.closest('.comment-item');
          if (!item) return;
          if (state.activeReplyBox){
            state.activeReplyBox.remove();
            state.activeReplyBox = null;
            state.replyParentCid = null;
          }
          const composer = buildReplyComposer(cid, meta);
          item.appendChild(composer);
          state.activeReplyBox = composer;
          state.replyParentCid = cid;
          return;
        }

        const editBtn = e.target.closest('.btn-edit');
        if (editBtn){
          const cid = editBtn.dataset.cid;
          const meta = state.comments[cid];
          if (!meta || !meta.visible || meta.tombstone) return;
          const item = editBtn.closest('.comment-item');
          if (!item) return;
          const existingBody = item.querySelector('.comment-text');
          if (!existingBody) return;
          if (item.querySelector('.edit-area')) return;

          const fallbackText = existingBody.textContent || '';
          const lid = meta?.chunk_ref?.local_id;
          let originalTxt = (lid && state.texts[lid]) ? state.texts[lid] : '';
          if (!originalTxt && fallbackText) originalTxt = fallbackText;
          const orig = originalTxt;

          existingBody.innerHTML = '';
          const ta = document.createElement('textarea');
          ta.className = 'edit-area';
          ta.value = orig;
          ta.rows = 3;
          ta.style.width = '100%';
          ta.maxLength = 1000;
          existingBody.appendChild(ta);

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
          existingBody.appendChild(bar);

          btnCancel.addEventListener('click', ()=>{
            const restored = renderText(orig, true);
            existingBody.replaceWith(restored);
          });

          btnSave.addEventListener('click', async () => {
            const newText = (ta.value || '').trim();
            if (!newText) return;
            btnSave.disabled = true;
            try{
              await CommentsAPI.update({ video_id: window.CommentsTreeVideoId, comment_id: cid, text: newText });
              const newNode = renderText(newText, true);
              existingBody.replaceWith(newNode);
              const headTime = item.querySelector('.comment-time');
              if (headTime && !/edited/.test(headTime.textContent)){
                headTime.textContent = headTime.textContent + ' (edited)';
              }
            }catch(err){
              console.warn('update failed', err);
              const restoreNode = renderText(orig, true);
              existingBody.replaceWith(restoreNode);
            }
          });
          return;
        }

        const delBtn = e.target.closest('.btn-delete');
        if (delBtn){
          const cid = delBtn.dataset.cid;
          const meta = state.comments[cid];
          if (!meta || !meta.visible || meta.tombstone) return;
          if (delBtn.dataset.deleting === '1') return;
          delBtn.dataset.deleting = '1';
          try{
            await CommentsAPI.remove({ video_id: window.CommentsTreeVideoId, comment_id: cid });
            window.CommentsReload && window.CommentsReload();
          }catch(err){
            console.warn('delete failed', err);
          }finally{
            delBtn.dataset.deleting = '0';
          }
          return;
        }

        const voteBtn = e.target.closest('.btn-like, .btn-dislike');
        if (voteBtn){
          const cid = voteBtn.dataset.cid;
          const meta = state.comments[cid];
          if (!meta || !meta.visible || meta.tombstone) {
            e.stopPropagation();
            e.preventDefault();
          }
        }
      });
      state.bound = true;
    }
  }

  return { renderTree: render };
})();