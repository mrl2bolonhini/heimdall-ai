// Forca em português. Digite uma letra ou arrisque a palavra inteira.
(function (raiz) {
  "use strict";
  var PALAVRAS = [
    ["animal", "elefante"], ["animal", "girafa"], ["animal", "tartaruga"], ["animal", "borboleta"], ["animal", "cachorro"], ["animal", "papagaio"], ["animal", "golfinho"], ["animal", "jacare"],
    ["animal", "morcego"], ["animal", "formiga"], ["fruta", "abacaxi"], ["fruta", "melancia"], ["fruta", "morango"], ["fruta", "laranja"], ["fruta", "goiaba"], ["fruta", "maracuja"],
    ["comida", "feijoada"], ["comida", "brigadeiro"], ["comida", "pamonha"], ["comida", "macarrao"], ["comida", "coxinha"], ["comida", "tapioca"], ["lugar", "biblioteca"], ["lugar", "aeroporto"],
    ["lugar", "montanha"], ["lugar", "cachoeira"], ["lugar", "farmacia"], ["lugar", "universidade"], ["objeto", "guarda-chuva"], ["objeto", "computador"], ["objeto", "travesseiro"],
    ["objeto", "telefone"], ["objeto", "liquidificador"], ["objeto", "caderno"], ["profissão", "advogado"], ["profissão", "engenheiro"], ["profissão", "professora"], ["profissão", "carpinteiro"],
    ["profissão", "bombeiro"], ["tecnologia", "algoritmo"], ["tecnologia", "servidor"], ["tecnologia", "criptografia"], ["tecnologia", "navegador"], ["tecnologia", "programador"],
    ["natureza", "arco-iris"], ["natureza", "tempestade"], ["natureza", "vulcao"], ["natureza", "floresta"], ["natureza", "oceano"], ["esporte", "natacao"], ["esporte", "basquete"], ["esporte", "maratona"]
  ];
  var ERROS_MAX = 7;

  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
  function novoEstado(palavra, categoria) {
    return { palavra: palavra, alvo: norm(palavra), categoria: categoria || "", certas: [], erradas: [], fim: null };
  }
  function tudoAcertado(e) {
    return e.alvo.split("").every(function (c) { return !/[a-z]/.test(c) || e.certas.indexOf(c) >= 0; });
  }
  // Devolve {msg} e atualiza o estado. Uma letra vira tentativa de letra; mais de uma, palpite da palavra.
  function tentar(e, entrada) {
    var t = norm(entrada).trim();
    if (e.fim) return { msg: "O jogo acabou. Comece uma nova rodada." };
    if (!t) return { msg: "Digite uma letra ou a palavra inteira." };
    if (t.length > 1) {
      if (t === e.alvo) { e.certas = e.alvo.split("").filter(function (c) { return /[a-z]/.test(c); }); e.fim = "ganhou"; return { msg: "Acertou a palavra: " + e.palavra + ". Você ganhou!" }; }
      e.erradas.push(t); e.fim = e.erradas.length >= ERROS_MAX ? "perdeu" : null;
      return { msg: "A palavra não é " + t + ". " + (e.fim ? "Você perdeu. A palavra era " + e.palavra + "." : "Restam " + (ERROS_MAX - e.erradas.length) + " erros.") };
    }
    if (!/[a-z]/.test(t)) return { msg: "Use uma letra de A a Z." };
    if (e.certas.indexOf(t) >= 0 || e.erradas.indexOf(t) >= 0) return { msg: "Você já tentou a letra " + t + "." };
    if (e.alvo.indexOf(t) >= 0) {
      e.certas.push(t);
      var n = e.alvo.split(t).length - 1;
      if (tudoAcertado(e)) { e.fim = "ganhou"; return { msg: "A letra " + t + " aparece " + n + (n > 1 ? " vezes" : " vez") + ". A palavra é " + e.palavra + ". Você ganhou!" }; }
      return { msg: "A letra " + t + " aparece " + n + (n > 1 ? " vezes" : " vez") + "." };
    }
    e.erradas.push(t);
    if (e.erradas.length >= ERROS_MAX) { e.fim = "perdeu"; return { msg: "A letra " + t + " não existe. Você perdeu. A palavra era " + e.palavra + "." }; }
    return { msg: "A letra " + t + " não existe. Restam " + (ERROS_MAX - e.erradas.length) + " erros." };
  }
  function exibir(e) {
    var partes = e.palavra.split("").map(function (orig, i) {
      var c = e.alvo[i];
      if (!/[a-z]/.test(c)) return orig;
      return (e.certas.indexOf(c) >= 0 || e.fim === "perdeu") ? orig : "_";
    });
    return partes.join(" ");
  }
  function sorteia() { var p = PALAVRAS[Math.floor(Math.random() * PALAVRAS.length)]; return novoEstado(p[1], p[0]); }

  var api = { novoEstado: novoEstado, tentar: tentar, exibir: exibir, tudoAcertado: tudoAcertado, sorteia: sorteia, ERROS_MAX: ERROS_MAX, PALAVRAS: PALAVRAS };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, estado = sorteia(), jogo = document.getElementById("jogo");
  var palavra = H.el("p", { id: "palavra", "aria-live": "off" }), info = H.el("p", { id: "info" }), usadas = H.el("p", { id: "usadas" });
  var campo = H.el("input", { id: "tentativa", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false", maxlength: "30" });
  var rotulo = H.el("label", { "for": "tentativa", texto: "Uma letra, ou a palavra inteira" });
  var botao = H.el("button", { type: "submit", texto: "Tentar" });
  var novo = H.el("button", { type: "button", texto: "Nova rodada" });
  var form = H.el("form", {}, [rotulo, campo, botao]);
  jogo.appendChild(palavra); jogo.appendChild(info); jogo.appendChild(usadas); jogo.appendChild(form); jogo.appendChild(novo);

  function atualizar() {
    palavra.textContent = "Palavra: " + exibir(estado);
    info.textContent = "Categoria: " + estado.categoria + ". Erros: " + estado.erradas.length + " de " + ERROS_MAX + ".";
    usadas.textContent = "Letras certas: " + (estado.certas.join(", ") || "nenhuma") + ". Erradas: " + (estado.erradas.join(", ") || "nenhuma") + ".";
    var fim = !!estado.fim;
    campo.disabled = fim; botao.disabled = fim;
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var r = tentar(estado, campo.value);
    campo.value = "";
    atualizar();
    H.anunciar(r.msg + " " + palavra.textContent);
    if (estado.fim) novo.focus(); else campo.focus();
  });
  novo.addEventListener("click", function () {
    estado = sorteia(); atualizar(); campo.focus();
    H.anunciar("Nova rodada. Categoria " + estado.categoria + ". A palavra tem " + estado.alvo.replace(/[^a-z]/g, "").length + " letras. " + palavra.textContent);
  });
  atualizar();
  H.anunciar("Categoria " + estado.categoria + ". A palavra tem " + estado.alvo.replace(/[^a-z]/g, "").length + " letras.");
})(typeof window !== "undefined" ? window : globalThis);
