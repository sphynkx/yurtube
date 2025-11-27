// Disable "Generate captions" button after pressing.
// Use sessionStorage to mark pending and regular request to /internal/ytcms/captions/status.
//Buggy - redirect breaks disabling.

(function () {
  var PENDING_PREFIX = 'captions_pending_';

  function getVideoId() {
    var main = document.querySelector('main.mc-main');
    if (main && main.dataset && main.dataset.videoId) return main.dataset.videoId;
    var hidden = document.querySelector('input[name="video_id"]');
    if (hidden && hidden.value) return hidden.value;
    try {
      var m = location.pathname.match(/\/manage\/video\/([^/]+)\/media/);
      if (m && m[1]) return m[1];
    } catch (e) {}
    return null;
  }

  function markPending(videoId) {
    try {
      sessionStorage.setItem(PENDING_PREFIX + videoId, String(Date.now()));
    } catch (e) {}
  }

  function clearPending(videoId) {
    try {
      sessionStorage.removeItem(PENDING_PREFIX + videoId);
    } catch (e) {}
  }

  function isPending(videoId) {
    try {
      return !!sessionStorage.getItem(PENDING_PREFIX + videoId);
    } catch (e) {
      return false;
    }
  }

  function disableCaptionsButtonUI() {
    var btn = document.getElementById('btn-generate-captions');
    if (!btn) {
      var forms = document.querySelectorAll('section form');
      for (var i = 0; i < forms.length; i++) {
        if (/\/captions\/(process|retry)$/.test(forms[i].getAttribute('action') || '')) {
          btn = forms[i].querySelector('button[type="submit"]');
          if (btn) break;
        }
      }
    }
    if (btn) {
      try {
        btn.disabled = true;
        btn.classList.add('disabled');
        if (!btn.dataset.originalText) {
          btn.dataset.originalText = btn.textContent;
        }
        btn.textContent = 'Queued...';
      } catch (e) {}
    }
  }

  function enableCaptionsButtonUI() {
    var btn = document.getElementById('btn-generate-captions');
    if (btn) {
      try {
        btn.disabled = false;
        btn.classList.remove('disabled');
        btn.textContent = btn.dataset.originalText || 'Generate captions';
      } catch (e) {}
    }
  }

  async function fetchStatus(videoId) {
    try {
      var url = '/internal/ytcms/captions/status?video_id=' + encodeURIComponent(videoId);
      var resp = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
      if (!resp.ok) return null;
      return await resp.json();
    } catch (e) {
      return null;
    }
  }

  function startPolling(videoId) {
    disableCaptionsButtonUI();
    var timer = setInterval(function () {
      fetchStatus(videoId).then(function (data) {
        if (!data) return;
        if (data.ok && data.ready) {
          clearInterval(timer);
          clearPending(videoId);
          enableCaptionsButtonUI();
        } else {
          disableCaptionsButtonUI();
        }
      });
    }, 3000);
  }

  function attachFormHandlers() {
    var forms = document.querySelectorAll('form');
    forms.forEach(function (form) {
      var action = (form.getAttribute('action') || '');
      if (/\/captions\/process$/.test(action) || /\/captions\/retry$/.test(action)) {
        form.addEventListener('submit', function () {
          var videoId = getVideoId();
          if (!videoId) return true;
          markPending(videoId);
          disableCaptionsButtonUI();
          return true;
        });
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var videoId = getVideoId();
    attachFormHandlers();
    if (!videoId) return;

    // If pending marked enable polling and keep it disabled
    if (isPending(videoId)) {
      startPolling(videoId);
      return;
    }

    // else check status. If not ready -  keep disabled and run polling
    fetchStatus(videoId).then(function (data) {
      if (data && data.ok && !data.ready) {
        markPending(videoId);
        startPolling(videoId);
      }
    });
  });
})();