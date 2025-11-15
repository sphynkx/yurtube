(function(){
  var root = document.getElementById('video-reactions');
  if(!root) return;

  var videoId = root.getAttribute('data-video-id') || '';
  if(!videoId) return;

  var likeBtn = root.querySelector('.btn-v-like');
  var dislikeBtn = root.querySelector('.btn-v-dislike');
  var likeCountEl = root.querySelector('.like-count');
  var dislikeCountEl = root.querySelector('.dislike-count');

  var my = 0;

  function setActive(){
    if (likeBtn) likeBtn.classList.toggle('active', my === 1);
    if (dislikeBtn) dislikeBtn.classList.toggle('active', my === -1);
  }

  async function loadState(){
    try{
      var r = await fetch('/videos/react/state?video_id='+encodeURIComponent(videoId), {credentials:'same-origin'});
      if(!r.ok) return;
      var d = await r.json();
      if(!d || !d.ok) return;
      likeCountEl && (likeCountEl.textContent = String(d.likes||0));
      dislikeCountEl && (dislikeCountEl.textContent = String(d.dislikes||0));
      my = d.my_reaction||0;
      setActive();
    }catch(e){}
  }

  async function send(reaction){
    try{
      var r = await fetch('/videos/react', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        credentials:'same-origin',
        body: JSON.stringify({ video_id: videoId, reaction: reaction })
      });
      if(r.status === 401){
        // not logged in; optionally show prompt
        return;
      }
      if(!r.ok) return;
      var d = await r.json();
      if(!d || !d.ok) return;
      likeCountEl && (likeCountEl.textContent = String(d.likes||0));
      dislikeCountEl && (dislikeCountEl.textContent = String(d.dislikes||0));
      my = d.my_reaction||0;
      setActive();
    }catch(e){}
  }

  if (likeBtn){
    likeBtn.addEventListener('click', function(e){
      e.preventDefault();
      var target = (my === 1) ? 0 : 1;
      send(target);
    });
  }
  if (dislikeBtn){
    dislikeBtn.addEventListener('click', function(e){
      e.preventDefault();
      var target = (my === -1) ? 0 : -1;
      send(target);
    });
  }

  loadState();
})();