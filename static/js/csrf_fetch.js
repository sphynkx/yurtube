(function(){
  if (window.__csrfPatched) return;
  window.__csrfPatched = true;

  function getCookie(name){
    var m = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()\\[\\]\\\\/+^])/g, '\\\\$1') + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : '';
  }

  // Patch fetch
  var origFetch = window.fetch;
  if (origFetch){
    window.fetch = function(input, init){
      init = init || {};
      init.headers = init.headers || {};
      var hdrs = init.headers instanceof Headers ? init.headers : new Headers(init.headers);
      if (!hdrs.has('X-Requested-With')) hdrs.set('X-Requested-With', 'XMLHttpRequest');
      var t = getCookie('yt_csrf');
      if (t && !hdrs.has('X-CSRF-Token')) hdrs.set('X-CSRF-Token', t);
      init.headers = hdrs;
      if (!init.credentials) init.credentials = 'same-origin';
      return origFetch(input, init);
    };
  }

  // Patch XHR
  if (window.XMLHttpRequest){
    var OrigXHR = window.XMLHttpRequest;
    var p = OrigXHR && OrigXHR.prototype;
    if (p){
      var origOpen = p.open;
      var origSend = p.send;
      p.open = function(method, url){
        this.__csrf_method = (method||'').toUpperCase();
        this.__csrf_url = url || '';
        return origOpen.apply(this, arguments);
      };
      p.send = function(body){
        try{
          this.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
          var t = getCookie('yt_csrf');
          if (t) this.setRequestHeader('X-CSRF-Token', t);
        }catch(e){}
        return origSend.apply(this, arguments);
      };
    }
  }
})();