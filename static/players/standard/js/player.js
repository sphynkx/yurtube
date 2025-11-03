// ASCII ONLY
(function () {
  function parseJSONAttr(el, name, fallback) {
    var s = el.getAttribute(name);
    if (!s) return fallback;
    try { return JSON.parse(s); } catch (e) { return fallback; }
  }

  function mountOne(host, templateHTML) {
    host.innerHTML = templateHTML;
    var container = host.querySelector(".stdp-container");
    var video = container.querySelector(".stdp-video");
    var source = video.querySelector("source");

    var videoSrc = host.getAttribute("data-video-src") || "";
    var poster = host.getAttribute("data-poster-url") || "";
    var subs = parseJSONAttr(host, "data-subtitles", []);
    var opts = parseJSONAttr(host, "data-options", {});

    if (source) source.setAttribute("src", videoSrc);
    if (poster) video.setAttribute("poster", poster);
    if (opts && opts.autoplay) video.setAttribute("autoplay", "");
    if (opts && opts.muted) video.setAttribute("muted", "");
    if (opts && opts.loop) video.setAttribute("loop", "");
    if (typeof opts.start === "number" && opts.start > 0) {
      try { video.currentTime = opts.start; } catch (e) {}
    }
    if (Array.isArray(subs)) {
      subs.forEach(function(t) {
        if (!t || !t.src) return;
        var tr = document.createElement("track");
        tr.setAttribute("kind", "subtitles");
        if (t.srclang) tr.setAttribute("srclang", String(t.srclang));
        if (t.label) tr.setAttribute("label", String(t.label));
        tr.setAttribute("src", String(t.src));
        if (t.default) tr.setAttribute("default", "");
        video.appendChild(tr);
      });
    }
  }

  function initAll() {
    var hosts = document.querySelectorAll(".player-host[data-player='standard']");
    if (hosts.length === 0) return;

    fetch("/static/players/standard/templates/player.html", { credentials: "same-origin" })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        for (var i = 0; i < hosts.length; i++) {
          mountOne(hosts[i], html);
        }
      })
      .catch(function () { /* ignore */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();