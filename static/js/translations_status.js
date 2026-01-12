(function(){
  function $(sel, root){ return (root||document).querySelector(sel); }
  function $all(sel, root){ return (root||document).querySelectorAll(sel); }

  function norm(code){ return String(code || '').trim().toLowerCase(); }
  function toSet(arr){
    var s = {};
    if (!Array.isArray(arr)) return s;
    for (var i=0; i<arr.length; i++){
      var c = norm(arr[i]);
      if (c) s[c] = true;
    }
    return s;
  }

  var root = $('.manage-comments-layout');
  if (!root) return;

  var videoId = root.getAttribute('data-video-id') || '';
  if (!videoId) return;

  var list = $('#langs-list');
  if (!list) return;

  var statusEl = $('#trans-status');
  function setStatusText(t){ if (statusEl) statusEl.textContent = t || ''; }

  function updateUI(readyLangs, writtenLangs) {
    var writtenSet = toSet(writtenLangs);
    var readySet = toSet(readyLangs);

    var items = $all('#langs-list li[data-lang]', list);

    // hard reset transient ready every tick
    for (var i=0; i<items.length; i++){
      items[i].classList.remove('lang-ready');
    }

    for (var j=0; j<items.length; j++){
      var li = items[j];
      var codeRaw = li.getAttribute('data-lang') || '';
      var code = norm(codeRaw);

      var isWritten = !!writtenSet[code];
      var isReadyOnly = !!readySet[code] && !isWritten;

      li.classList.toggle('lang-has-file', isWritten);
      if (isReadyOnly) li.classList.add('lang-ready');

      var edit = li.querySelector('.lang-edit');
      var dl = li.querySelector('.lang-dl');

      if (edit) {
        if (isWritten) {
          edit.classList.remove('disabled');
          edit.setAttribute(
            'href',
            '/manage/video/' + encodeURIComponent(videoId) +
              '/vtt/edit?rel_vtt=' + encodeURIComponent('captions/' + codeRaw + '.vtt')
          );
        } else {
          edit.classList.add('disabled');
          // IMPORTANT: remove href entirely so it's not a link
          edit.removeAttribute('href');
        }
      }

      if (dl) {
        if (isWritten) {
          dl.classList.remove('disabled');
          dl.setAttribute(
            'href',
            '/manage/video/' + encodeURIComponent(videoId) +
              '/vtt/download?rel_vtt=' + encodeURIComponent('captions/' + codeRaw + '.vtt')
          );
        } else {
          dl.classList.add('disabled');
          dl.removeAttribute('href');
        }
      }
    }
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

      var state = String(j.state || '').toLowerCase();
      var ready = Array.isArray(j.ready_langs) ? j.ready_langs : [];
      var written = Array.isArray(j.langs_written) ? j.langs_written : [];

      // show yellow only while job is active
      if (!(state === 'running' || state === 'queued')) {
        ready = [];
      }

      updateUI(ready, written);

      var p = (typeof j.percent === 'number' && j.percent >= 0) ? (j.percent + '%') : '';
      var totalN = (typeof j.total_langs === 'number' && j.total_langs > 0) ? j.total_langs : 0;
      var msg = String(j.message || '');

      var t = state || '';
      if (p) t += ' ' + p;
      t += ' ready ' + ready.length + (totalN ? '/' + totalN : '');
      if (msg) t += ' — ' + msg;
      setStatusText(t);
    }).catch(function(e){
      setStatusText('progress error: ' + (e && e.message ? e.message : String(e || '')));
    });
  }

  setInterval(pollProgress, 1000);
  pollProgress();
})();