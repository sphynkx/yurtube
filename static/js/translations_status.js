(function(){
  function $(sel, root){ return (root||document).querySelector(sel); }
  function $all(sel, root){ return (root||document).querySelectorAll(sel); }

  var root = $('.manage-comments-layout');
  if (!root) return;
  var videoId = root.getAttribute('data-video-id') || '';
  if (!videoId) return;

  var list = $('#langs-list');
  if (!list) return;

  var statusEl = $('#trans-status');

  function setStatusText(t){
    if (!statusEl) return;
    statusEl.textContent = t || '';
  }

  function updateUI(langs) {
    var items = $all('li[data-lang]', list);
    for (var i = 0; i < items.length; i++) {
      var li = items[i];
      var code = li.getAttribute('data-lang') || '';
      var has = langs.indexOf(code) >= 0;

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

  var known = {};
  function mergeLangs(langs) {
    if (!Array.isArray(langs)) return;
    var changed = false;
    for (var i = 0; i < langs.length; i++) {
      var c = String(langs[i] || '').trim();
      if (!c) continue;
      if (!known[c]) { known[c] = true; changed = true; }
    }
    if (changed) updateUI(Object.keys(known));
  }

  function pollProgress() {
    fetch('/internal/yttrans/translations/progress?video_id=' + encodeURIComponent(videoId), {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    }).then(function(r){
      if (!r.ok) throw new Error('progress_http_' + r.status);
      return r.json();
    }).then(function(j){
      if (!(j && j.ok)) throw new Error('bad_progress_payload');

      if (Array.isArray(j.langs)) mergeLangs(j.langs);

      var p = (typeof j.percent === 'number' && j.percent >= 0) ? (j.percent + '%') : '';
      var ec = (typeof j.entries_count === 'number') ? (' entries:' + j.entries_count) : '';
      var st = (j.state || '');
      var err = (j.result_error ? (' result_error=' + j.result_error) : '');
      setStatusText(st + (p ? ' ' + p : '') + ec + err);
    }).catch(function(e){
      setStatusText('progress error: ' + (e && e.message ? e.message : String(e || '')));
      // fallback to old behavior
      fetch('/internal/yttrans/translations/status?video_id=' + encodeURIComponent(videoId), {
        method: 'GET',
        headers: { 'Accept': 'application/json' }
      }).then(function(r){
        if (!r.ok) throw new Error('status_http_' + r.status);
        return r.json();
      }).then(function(j){
        if (j && j.ok && Array.isArray(j.langs)) mergeLangs(j.langs);
      }).catch(function(_){});
    });
  }

  setInterval(pollProgress, 2000);
  pollProgress();
})();