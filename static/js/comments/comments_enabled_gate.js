(function(){
  if (window.__comments_enabled_gate_once) return;
  window.__comments_enabled_gate_once = true;

  const root = document.getElementById('comments-root');
  if (!root) return;
  let banner = null;

  function ensureBanner(){
    if (banner) return banner;
    banner = document.createElement('div');
    banner.className = 'comments-disabled-banner';
    banner.textContent = 'Comments are disabled for this video.';
    banner.style.display = 'none';
    root.parentElement && root.parentElement.insertBefore(banner, root);
    return banner;
  }
  function apply(enabled){
    ensureBanner();
    if (enabled){
      root.style.display = '';
      banner.style.display = 'none';
    } else {
      root.style.display = 'none';
      banner.style.display = 'block';
    }
  }

  function onListPayload(data){
    if (!data || typeof data !== 'object') return;
    if (typeof data.comments_enabled === 'boolean'){
      apply(data.comments_enabled);
    }
  }

  // fetch
  (function wrapFetch(){
    if (!window.fetch) return;
    const rList = /\/comments\/list(?:\/|\?|$)/;
    const orig = window.fetch;
    window.fetch = async function(input, init){
      const url = (typeof input === 'string') ? input : (input && input.url) || '';
      const method = ((init && init.method) || 'GET').toUpperCase();
      const res = await orig(input, init);
      try{
        if (rList.test(url) && method === 'GET'){
          res.clone().json().then(onListPayload).catch(()=>{});
        }
      }catch(e){}
      return res;
    };
  })();

  // XHR
  (function wrapXHR(){
    if (!window.XMLHttpRequest) return;
    const rList = /\/comments\/list(?:\/|\?|$)/;
    const Orig = window.XMLHttpRequest;
    function X(){ const xhr = new Orig();
      xhr.__u=''; xhr.__m='GET';
      const oOpen=xhr.open; xhr.open=function(m,u){ xhr.__m=(m||'GET').toUpperCase(); xhr.__u=u||''; return oOpen.apply(xhr, arguments); };
      const oSend=xhr.send; xhr.send=function(b){
        xhr.addEventListener('load', function(){
          try{
            if (rList.test(xhr.__u) && xhr.__m==='GET'){
              let data=null; try{ data = xhr.responseType==='json' ? xhr.response : JSON.parse(xhr.responseText); }catch(_){}
              onListPayload(data);
            }
          }catch(e){}
        });
        return oSend.apply(xhr, arguments);
      };
      return xhr;
    }
    window.XMLHttpRequest = X;
  })();
})();