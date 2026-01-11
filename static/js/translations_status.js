(function(){
  function $(sel, root){ return (root||document).querySelector(sel); }
  function $all(sel, root){ return (root||document).querySelectorAll(sel); }

  var root = $('.manage-comments-layout');
  if (!root) return;
  var videoId = root.getAttribute('data-video-id') || '';

  if (!videoId) return;

  var list = $('#langs-list');
  if (!list) return;

  function updateUI(langs) {
    var items = $all('li[data-lang]', list);
    for (var i = 0; i < items.length; i++) {
      var li = items[i];
      var code = li.getAttribute('data-lang') || '';
      var has = langs.indexOf(code) >= 0;

      // highlight blocks that have translation
      li.classList.toggle('lang-has-file', !!has);

      var edit = li.querySelector('.lang-edit');
      var dl = li.querySelector('.lang-dl');
      if (edit) {
        if (has) {
          edit.classList.remove('disabled');
          if (!edit.getAttribute('href') || edit.getAttribute('href') === '') {
            edit.setAttribute('href', '/manage/video/' + encodeURIComponent(videoId) +
              '/vtt/edit?rel_vtt=' + encodeURIComponent('captions/' + code + '.vtt'));
          }
        } else {
          edit.classList.add('disabled');
          edit.setAttribute('href', '');
        }
      }
      if (dl) {
        if (has) {
          dl.classList.remove('disabled');
          if (!dl.getAttribute('href') || dl.getAttribute('href') === '') {
            dl.setAttribute('href', '/manage/video/' + encodeURIComponent(videoId) +
              '/vtt/download?rel_vtt=' + encodeURIComponent('captions/' + code + '.vtt'));
          }
        } else {
          dl.classList.add('disabled');
          dl.setAttribute('href', '');
        }
      }
    }
  }

  function poll() {
    fetch('/internal/yttrans/translations/status?video_id=' + encodeURIComponent(videoId), {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    }).then(function(r){
      if (!r.ok) throw new Error('status_http_' + r.status);
      return r.json();
    }).then(function(j){
      if (j && j.ok && Array.isArray(j.langs)) {
        updateUI(j.langs);
      }
    }).catch(function(_){});
  }

  setInterval(poll, 2000);
  poll();
})();