(function(){
  var root = document.getElementById('addto-inline');
  if (!root) return;

  var trigger = root.querySelector('.addto-trigger');
  var flyout = document.getElementById('addto-flyout');
  var backdrop = document.getElementById('addto-backdrop');

  function openFlyout() {
    if (!flyout) return;
    flyout.hidden = false;
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
    if (backdrop) backdrop.hidden = false;
  }
  function closeFlyout() {
    if (!flyout) return;
    flyout.hidden = true;
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
    if (backdrop) backdrop.hidden = true;
  }

  if (trigger) {
    trigger.addEventListener('click', function(){
      if (flyout && flyout.hidden) openFlyout(); else closeFlyout();
    });
  }
  if (backdrop) backdrop.addEventListener('click', closeFlyout);
  document.addEventListener('keydown', function(ev){
    if (ev.key === 'Escape') closeFlyout();
  });

  // Placeholder: item clicks (route integration will come later)
  root.addEventListener('click', function(ev){
    var btn = ev.target.closest('.addto-item, .addto-new');
    if (!btn) return;

    var action = btn.getAttribute('data-action') || '';
    var playlistId = btn.getAttribute('data-playlist-id') || '';
    var videoContainer = document.getElementById('video-reactions');
    var videoId = videoContainer ? videoContainer.getAttribute('data-video-id') : '';

    // TODO: implement server calls:
    // - POST /playlists/add { video_id, playlist_id }
    // - POST /playlists/watch_later { video_id }
    // - POST /playlists/favorites { video_id }
    // - POST /playlists/create { name }
    // For now just close the menu.
    closeFlyout();
  });
})();