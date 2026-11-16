// Caça-níqueis: um painel de três dígitos de 0 a 9 e um botão Girar, como nos painéis de aparelhos de som antigos.
// Três iguais (trinca) e uma sequência (123, 321, 901, 109...) dão os prêmios grandes; um par (dois números iguais) dá um prêmio pequeno e frequente; o resto perde a aposta.
// Créditos de mentira, sem dinheiro de verdade. Em média o jogador recebe de volta cerca de 99% do que aposta, e cerca de 30% das rodadas pagam alguma coisa.
(function (raiz) {
  "use strict";
  var INICIO = 30;
  var APOSTAS = [1, 2, 5];
  var PREMIOS = { trinca: 25, sequencia: 10, par: 2 };   // vezes a aposta devolvidas (a aposta já saiu do saldo)
  var PALAVRAS = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"];

  function classificar(d) {
    if (d[0] === d[1] && d[1] === d[2]) return "trinca";
    var sobe = d[1] === (d[0] + 1) % 10 && d[2] === (d[1] + 1) % 10;
    var desce = d[1] === (d[0] + 9) % 10 && d[2] === (d[1] + 9) % 10;
    if (sobe || desce) return "sequencia";
    return d[0] === d[1] || d[1] === d[2] || d[0] === d[2] ? "par" : "nada";
  }
  function sortear(rnd) {
    var r = rnd || function (n) {
      if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
      return Math.floor(Math.random() * n);
    };
    return [r(10), r(10), r(10)];
  }
  function novo() { return { creditos: INICIO, rodadas: 0, maximo: INICIO, trincas: 0, sequencias: 0, pares: 0, fim: false }; }
  function falarDigitos(d) { return d.map(function (x) { return PALAVRAS[x]; }).join(", "); }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }

  // Uma rodada: desconta a aposta, confere o resultado e paga o prêmio. `digitos` existe só para os testes.
  function girar(e, aposta, digitos, rnd) {
    if (e.fim) return { erro: "As fichas acabaram. Comece uma nova partida." };
    if (APOSTAS.indexOf(aposta) < 0) return { erro: "Aposta inválida. Use 1, 2 ou 5 créditos." };
    if (aposta > e.creditos) return { erro: "Você tem só " + plural(e.creditos, "crédito", "créditos") + ". Escolha uma aposta menor." };
    var d = digitos || sortear(rnd), tipo = classificar(d), premio = (PREMIOS[tipo] || 0) * aposta;
    e.creditos += premio - aposta; e.rodadas++;
    if (tipo === "trinca") e.trincas++;
    if (tipo === "sequencia") e.sequencias++;
    if (tipo === "par") e.pares++;
    if (e.creditos > e.maximo) e.maximo = e.creditos;
    if (e.creditos < 1) e.fim = true;
    var msg = "Saiu: " + falarDigitos(d) + ". ";
    if (tipo === "trinca") msg += "Trinca! Três iguais. Prêmio de " + plural(premio, "crédito", "créditos") + " para uma aposta de " + aposta + ".";
    else if (tipo === "sequencia") msg += "Sequência! Prêmio de " + plural(premio, "crédito", "créditos") + " para uma aposta de " + aposta + ".";
    else if (tipo === "par") msg += "Par! Dois números iguais. Prêmio de " + plural(premio, "crédito", "créditos") + " para uma aposta de " + aposta + ".";
    else msg += "Nada desta vez. Você perdeu a aposta de " + plural(aposta, "crédito", "créditos") + ".";
    msg += " Saldo: " + plural(e.creditos, "crédito", "créditos") + ".";
    if (e.fim) msg += " Acabaram os créditos. Foram " + plural(e.rodadas, "rodada", "rodadas") + ", e o maior saldo foi " + e.maximo + ".";
    return { digitos: d, tipo: tipo, premio: premio, msg: msg };
  }
  function tabela() {
    return "Prêmios: três números iguais, como 4 4 4, pagam " + PREMIOS.trinca + " vezes a aposta. Sequência de três números, subindo ou descendo, como 1 2 3, 3 2 1, 9 0 1 ou 1 0 9, paga " +
      PREMIOS.sequencia + " vezes a aposta. Dois números iguais, como 4 4 7 ou 3 8 3, é um par e paga " + PREMIOS.par + " vezes a aposta. Qualquer outra combinação perde a aposta. Você começa com " + INICIO + " créditos e pode apostar 1, 2 ou 5 por rodada.";
  }
  function resumo(e) {
    return "Saldo: " + plural(e.creditos, "crédito", "créditos") + ". Rodadas: " + e.rodadas + ". Trincas: " + e.trincas + ". Sequências: " + e.sequencias + ". Pares: " + e.pares + ". Maior saldo: " + e.maximo + ".";
  }

  var api = { INICIO: INICIO, APOSTAS: APOSTAS, PREMIOS: PREMIOS, classificar: classificar, sortear: sortear, novo: novo, girar: girar, tabela: tabela, resumo: resumo, falarDigitos: falarDigitos };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo();
  var painel = H.el("p", { id: "painel", "aria-hidden": "true", texto: "[ - | - | - ]" });
  var sel = H.el("select", { id: "aposta" }, APOSTAS.map(function (a) { return H.el("option", { value: String(a), texto: a + (a === 1 ? " crédito" : " créditos") }); }));
  var girarBtn = H.el("button", { type: "button", id: "girar", texto: "Girar" });
  var saldo = H.el("p", { id: "saldo" });
  var ler = H.el("button", { type: "button", texto: "Ler o saldo" });
  var premios = H.el("button", { type: "button", texto: "Ver os prêmios" });
  var novoBtn = H.el("button", { type: "button", texto: "Nova partida" });
  [painel, H.som ? H.som.botao() : H.el("span"), H.el("label", { "for": "aposta", texto: "Aposta por rodada" }), sel, girarBtn, saldo, ler, premios, novoBtn].forEach(function (x) { jogo.appendChild(x); });
  function atualizar() { saldo.textContent = "Saldo: " + e.creditos + " créditos."; girarBtn.disabled = e.fim; }
  girarBtn.addEventListener("click", function () {
    var r = girar(e, Number(sel.value));
    if (r.erro) { H.anunciar(r.erro); return; }
    painel.textContent = "[ " + r.digitos.join(" | ") + " ]";
    atualizar();
    if (H.som) H.som.anunciar(["rolos", r.tipo === "trinca" ? "grande" : r.premio > 0 ? "ganhou" : "perdeu"], r.msg); else H.anunciar(r.msg);
    if (e.fim) novoBtn.focus();
  });
  ler.addEventListener("click", function () { H.anunciar(resumo(e)); });
  premios.addEventListener("click", function () { H.anunciar(tabela()); });
  novoBtn.addEventListener("click", function () { e = novo(); painel.textContent = "[ - | - | - ]"; atualizar(); H.anunciar("Nova partida com " + INICIO + " créditos. " + tabela()); girarBtn.focus(); });
  atualizar();
  H.anunciar("Caça-níqueis. Você tem " + INICIO + " créditos. Escolha a aposta e use o botão Girar. " + tabela());
})(typeof window !== "undefined" ? window : globalThis);
