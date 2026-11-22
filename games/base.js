// Base comum dos jogos do Heimdall: anúncio para o leitor de tela (região aria-live), foco e utilidades.
(function (raiz) {
  "use strict";
  function anunciar(texto) {
    var el = typeof document !== "undefined" && document.getElementById("anuncio");
    if (!el) return;
    el.textContent = "";
    // o intervalo faz o leitor de tela ler de novo mesmo quando o texto se repete
    setTimeout(function () { el.textContent = texto; }, 60);
  }
  function el(tag, atributos, filhos) {
    var e = document.createElement(tag);
    Object.keys(atributos || {}).forEach(function (k) {
      if (k === "texto") e.textContent = atributos[k]; else e.setAttribute(k, atributos[k]);
    });
    (filhos || []).forEach(function (f) { e.appendChild(f); });
    return e;
  }
  function semAcento(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function sorteio(n) { return Math.floor(Math.random() * n); }
  raiz.Heimdall = { anunciar: anunciar, el: el, semAcento: semAcento, sorteio: sorteio };
  if (typeof module !== "undefined") module.exports = raiz.Heimdall;
})(typeof window !== "undefined" ? window : globalThis);
