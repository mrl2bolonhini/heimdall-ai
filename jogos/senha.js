// Senha (Mastermind): descubra 4 dígitos de 1 a 6 (pode repetir) em até 10 tentativas.
(function (raiz) {
  "use strict";
  var TAM = 4, MAX = 10;
  function gerar(rnd) { var s = []; for (var i = 0; i < TAM; i++) s.push(1 + Math.floor((rnd ? rnd() : Math.random()) * 6)); return s; }
  // certos = dígito certo no lugar certo; trocados = dígito certo no lugar errado
  function avaliar(secreto, palpite) {
    var certos = 0, sobraS = {}, sobraP = {}, trocados = 0;
    for (var i = 0; i < TAM; i++) {
      if (secreto[i] === palpite[i]) certos++;
      else { sobraS[secreto[i]] = (sobraS[secreto[i]] || 0) + 1; sobraP[palpite[i]] = (sobraP[palpite[i]] || 0) + 1; }
    }
    Object.keys(sobraP).forEach(function (d) { trocados += Math.min(sobraP[d], sobraS[d] || 0); });
    return { certos: certos, trocados: trocados };
  }
  function ler(texto) {
    var t = String(texto).replace(/[^0-9]/g, "");
    if (t.length !== TAM || /[07-9]/.test(t)) return null;
    return t.split("").map(Number);
  }
  function frase(r) {
    if (r.certos === TAM) return "Acertou a senha!";
    return r.certos + (r.certos === 1 ? " dígito no lugar certo" : " dígitos no lugar certo") + " e " + r.trocados + (r.trocados === 1 ? " dígito certo no lugar errado." : " dígitos certos no lugar errado.");
  }
  var api = { gerar: gerar, avaliar: avaliar, ler: ler, frase: frase, TAM: TAM, MAX: MAX };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), secreto, historico;
  function D(m, f) { if (H.som) H.som.dizer("senha", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var info = H.el("p", { id: "info" }), lista = H.el("ol", { id: "historico", "aria-label": "Tentativas anteriores" });
  var campo = H.el("input", { id: "palpite", type: "text", inputmode: "numeric", autocomplete: "off", maxlength: "4" });
  var form = H.el("form", {}, [H.el("label", { "for": "palpite", texto: "Seu palpite: 4 dígitos, cada um de 1 a 6" }), campo, H.el("button", { type: "submit", texto: "Tentar" })]);
  var novo = H.el("button", { type: "button", texto: "Nova senha" });
  [info, form, lista, novo].forEach(function (x) { jogo.appendChild(x); });
  function comecar() {
    secreto = gerar(); historico = []; lista.textContent = ""; campo.disabled = false; campo.value = "";
    info.textContent = "Tentativa 1 de " + MAX + ".";
    H.anunciar("Nova senha de 4 dígitos, cada um de 1 a 6. Você tem " + MAX + " tentativas.");
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var p = ler(campo.value);
    if (!p) { D("Digite exatamente 4 dígitos, cada um de 1 a 6."); return; }
    var r = avaliar(secreto, p); historico.push(p);
    lista.appendChild(H.el("li", { texto: p.join(" ") + ": " + frase(r) }));
    campo.value = "";
    var msg = p.join(" ") + ": " + frase(r);
    if (r.certos === TAM) { campo.disabled = true; msg += " Você precisou de " + historico.length + " tentativas."; novo.focus(); }
    else if (historico.length >= MAX) { campo.disabled = true; msg += " Acabaram as tentativas. A senha era " + secreto.join(" ") + "."; novo.focus(); }
    else { info.textContent = "Tentativa " + (historico.length + 1) + " de " + MAX + "."; msg += " Tentativa " + (historico.length + 1) + " de " + MAX + "."; campo.focus(); }
    D(msg);
  });
  novo.addEventListener("click", function () { comecar(); campo.focus(); });
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
