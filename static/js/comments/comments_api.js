// Simple API client for comments
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
    if (!r.ok) {
      const err = await r.json().catch(()=>({}));
      throw new Error(err?.detail?.error || 'Failed to create comment');
    }
    return r.json();
  }

  async function like({ video_id, comment_id, delta_like=0, delta_dislike=0 }) {
    const r = await fetch('/comments/like', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ video_id, comment_id, delta_like, delta_dislike })
    });
    if (!r.ok) throw new Error('Failed to like');
    return r.json();
  }

  return { list, create, like };
})();