const CommentsAPI = (() => {
  async function list(videoId, includeHidden=false) {
    const url = `/comments/list?video_id=${encodeURIComponent(videoId)}&include_hidden=${includeHidden?'true':'false'}`;
    const r = await fetch(url, { credentials: 'same-origin' });
    if (!r.ok) throw new Error('Failed to load comments');
    return r.json();
  }

  async function create({ video_id, text, parent_id=null, reply_to_user_uid=null }) {
    const r = await fetch('/comments/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ video_id, text, parent_id, reply_to_user_uid })
    });
    if (!r.ok) throw new Error('Failed to create comment');
    return r.json();
  }

  async function vote({ video_id, comment_id, vote }) {
    const r = await fetch('/comments/vote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ video_id, comment_id, vote })
    });
    if (!r.ok) throw new Error('Failed to vote');
    return r.json();
  }

  async function update({ video_id, comment_id, text }) {
    const r = await fetch('/comments/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ video_id, comment_id, text })
    });
    if (!r.ok) throw new Error('Failed to update');
    return r.json();
  }

  async function remove({ video_id, comment_id }) {
    const r = await fetch('/comments/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ video_id, comment_id })
    });
    if (!r.ok) throw new Error('Failed to delete');
    return r.json();
  }

  return { list, create, vote, update, remove };
})();