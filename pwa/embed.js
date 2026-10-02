(function () {
  var script = document.currentScript;
  if (!script) return;
  var base = script.src.replace(/embed\.js(\?.*)?$/, "");
  var mode = script.getAttribute("data-mode") || "conversation";
  var lang = script.getAttribute("data-lang") || "es";
  var limit = script.getAttribute("data-limit") || "5";
  var theme = script.getAttribute("data-theme") || "rpc";
  var iframe = document.createElement("iframe");
  iframe.src = base + "widget.html?mode=" + encodeURIComponent(mode)
    + "&lang=" + encodeURIComponent(lang)
    + "&limit=" + encodeURIComponent(limit)
    + "&theme=" + encodeURIComponent(theme);
  iframe.loading = "lazy";
  iframe.title = "Radar RPC — Revista Panamericana de Comunicación";
  iframe.style.cssText = "width:100%;max-width:400px;height:560px;border:0;border-radius:12px;overflow:hidden;background:transparent;color-scheme:light dark;";
  script.parentNode.insertBefore(iframe, script.nextSibling);
})();
