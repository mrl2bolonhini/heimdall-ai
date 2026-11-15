// Número secreto: descubra um número de 1 a 100 com as dicas "maior" e "menor".
(function (raiz) {
  "use strict";
  function dica(secreto, palpite) {
    if (palpite === secreto) return "certo";
    return palpite < secreto ? "maior" : "menor";
  }
  function ler(texto) { var t = String(texto).trim(); if (!/^\d{1,3}$/.test(t)) return null; var n = Number(t); return n >= 1 && n <= 100 ? n : null; }
  var api = { dica: dica, ler: ler };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;
  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), secreto, tentativas, min, max;
  var info = H.el("p", { id: "info" });
  var campo = H.el("input", { id: "palpite", type: "text", inputmode: "numeric", autocomplete: "off", maxlength: "3" });
  var form = H.el("form", {}, [H.el("label", { "for": "palpite", texto: "Seu palpite, de 1 a 100" }), campo, H.el("button", { type: "submit", texto: "Tentar" })]);
  var novo = H.el("button", { type: "button", texto: "Nova rodada" });
  [info, form, novo].forEach(function (x) { jogo.appendChild(x); });
  function comecar() {
    secreto = 1 + H.sorteio(100); tentativas = 0; min = 1; max = 100; campo.disabled = false; campo.value = "";
    info.textContent = "Pensei em um número entre 1 e 100.";
    H.anunciar("Pensei em um número entre 1 e 100. Qual é o seu palpite?");
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var n = ler(campo.value); campo.value = "";
    if (n === null) { H.anunciar("Digite um número inteiro de 1 a 100."); return; }
    tentativas++;
    var d = dica(secreto, n), msg;
    if (d === "certo") { msg = "Acertou! O número era " + secreto + ", em " + tentativas + (tentativas === 1 ? " tentativa." : " tentativas."); campo.disabled = true; novo.focus(); }
    else {
      if (d === "maior") min = Math.max(min, n + 1); else max = Math.min(max, n - 1);
      msg = "O número é " + d + " que " + n + ". Ele está entre " + min + " e " + max + ". Tentativa " + tentativas + ".";
      campo.focus();
    }
    info.textContent = msg; H.anunciar(msg);
  });
  novo.addEventListener("click", function () { comecar(); campo.focus(); });
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
