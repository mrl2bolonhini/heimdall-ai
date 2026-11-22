// Roleta com créditos de mentira (nunca dinheiro de verdade). Você faz uma ou mais apostas e manda girar.
// Fácil e normal: roleta europeia (0 a 36). Difícil: roleta americana (0, 00 e 1 a 36), que é mais dura para o jogador.
// Pagamentos: número 35 para 1; dúzia e coluna 2 para 1; vermelho, preto, par, ímpar, alto e baixo 1 para 1. Zero (e 00) perdem as apostas de cor, paridade, alto/baixo, dúzia e coluna.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", inicio: 100, duplo: false },
    normal: { nome: "normal", inicio: 60, duplo: false },
    dificil: { nome: "difícil", inicio: 60, duplo: true }
  };
  var VERMELHOS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36];
  var MULT = { numero: 36, duzia: 3, coluna: 3, cor: 2, par: 2, alto: 2 }; // total devolvido por crédito apostado (aposta incluída)
  var DUPLO = 37; // índice do "00"

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function nomeNum(n) { return n === DUPLO ? "duplo zero" : String(n); }
  function cor(n) { return n === 0 || n === DUPLO ? "verde" : VERMELHOS.indexOf(n) >= 0 ? "vermelho" : "preto"; }
  function descNum(n) {
    if (n === 0 || n === DUPLO) return nomeNum(n) + ", verde";
    return n + ", " + cor(n) + ", " + (n % 2 ? "ímpar" : "par") + ", " + (n <= 18 ? "baixo" : "alto");
  }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k];
    return { nivel: k, nome: n.nome, duplo: n.duplo, saldo: n.inicio, inicio: n.inicio, maximo: n.inicio, apostas: [], anteriores: [], hist: [], rodadas: 0, fim: false, rnd: rnd || sorteio };
  }
  function nomeAposta(a) {
    return { numero: "número " + nomeNum(a.alvo), cor: a.alvo, par: a.alvo === "impar" ? "ímpar" : a.alvo, alto: a.alvo === "alto" ? "alto (19 a 36)" : "baixo (1 a 18)", duzia: "dúzia " + a.alvo + (a.alvo === 1 ? " (1 a 12)" : a.alvo === 2 ? " (13 a 24)" : " (25 a 36)"), coluna: "coluna " + a.alvo }[a.tipo];
  }
  function ganhou(a, n) {
    if (n === 0 || n === DUPLO) return a.tipo === "numero" && a.alvo === n;
    switch (a.tipo) {
      case "numero": return a.alvo === n;
      case "cor": return cor(n) === a.alvo;
      case "par": return (n % 2 === 0) === (a.alvo === "par");
      case "alto": return (n >= 19) === (a.alvo === "alto");
      case "duzia": return Math.ceil(n / 12) === a.alvo;
      case "coluna": return (n % 3 || 3) === a.alvo;
    }
    return false;
  }
  function totalApostado(e) { return e.apostas.reduce(function (s, a) { return s + a.valor; }, 0); }
  function listaApostas(e) {
    if (!e.apostas.length) return "Nenhuma aposta na mesa. Saldo: " + plural(e.saldo, "crédito", "créditos") + ".";
    return "Apostas na mesa: " + e.apostas.map(function (a) { return a.valor + " em " + nomeAposta(a); }).join("; ") + ". Total: " + totalApostado(e) + ". Saldo: " + plural(e.saldo, "crédito", "créditos") + ".";
  }
  function apostar(e, valor, tipo, alvo) {
    if (e.fim) return { msg: "Os créditos acabaram. Comece um novo jogo.", erro: true };
    if (!(valor >= 1) || valor % 1) return { msg: "O valor da aposta precisa ser um número inteiro de créditos, de 1 em diante.", erro: true };
    if (valor > e.saldo) return { msg: "Você tem só " + plural(e.saldo, "crédito", "créditos") + " livres.", erro: true };
    if (tipo === "numero" && !(alvo === 0 || (alvo >= 1 && alvo <= 36) || (alvo === DUPLO && e.duplo))) return { msg: "Esse número não existe nesta roleta. Há os números de 1 a 36, o zero" + (e.duplo ? " e o duplo zero" : "") + ".", erro: true };
    if ((tipo === "duzia" || tipo === "coluna") && !(alvo >= 1 && alvo <= 3)) return { msg: "A " + tipo + " vai de 1 a 3.", erro: true };
    var a = { tipo: tipo, alvo: alvo, valor: valor }, ex = e.apostas.filter(function (x) { return x.tipo === tipo && x.alvo === alvo; })[0];
    if (ex) ex.valor += valor; else e.apostas.push(a);
    e.saldo -= valor;
    return { msg: "Aposta de " + valor + " em " + nomeAposta(a) + (ex ? " (somada à anterior, agora " + ex.valor + ")" : "") + ". " + listaApostas(e) + " Para girar: girar." };
  }
  function limpar(e) {
    if (!e.apostas.length) return { msg: "Não há apostas para tirar." };
    var t = totalApostado(e); e.saldo += t; e.apostas = [];
    return { msg: "Apostas retiradas, " + plural(t, "crédito devolvido", "créditos devolvidos") + ". Saldo: " + e.saldo + "." };
  }
  function repetir(e) {
    if (!e.anteriores.length) return { msg: "Ainda não há apostas anteriores para repetir.", erro: true };
    if (e.apostas.length) return { msg: "Já há apostas na mesa. Gire, ou use limpar.", erro: true };
    var t = e.anteriores.reduce(function (s, a) { return s + a.valor; }, 0);
    if (t > e.saldo) return { msg: "As apostas anteriores somam " + t + " e você tem " + e.saldo + ".", erro: true };
    e.anteriores.forEach(function (a) { e.saldo -= a.valor; e.apostas.push({ tipo: a.tipo, alvo: a.alvo, valor: a.valor }); });
    return { msg: "Apostas repetidas. " + listaApostas(e) };
  }
  // `numero` existe só para os testes.
  function girar(e, numero) {
    if (e.fim) return { msg: "Os créditos acabaram. Comece um novo jogo.", erro: true };
    if (!e.apostas.length) return { msg: "Faça uma aposta antes de girar. Exemplo: apostar 5 vermelho.", erro: true };
    var n = numero !== undefined ? numero : e.rnd(e.duplo ? 38 : 37), paga = 0, partes = [];
    e.apostas.forEach(function (a) {
      if (ganhou(a, n)) { var r = a.valor * MULT[a.tipo]; paga += r; partes.push("ganhou em " + nomeAposta(a) + ", recebe " + r); }
      else partes.push("perdeu " + a.valor + " em " + nomeAposta(a));
    });
    var apostado = totalApostado(e);
    e.saldo += paga; e.rodadas++; e.hist.push(n); if (e.hist.length > 30) e.hist.shift(); e.anteriores = e.apostas; e.apostas = [];
    if (e.saldo > e.maximo) e.maximo = e.saldo;
    var res = paga > apostado ? "Você lucrou " + (paga - apostado) + "." : paga === apostado ? "Você ficou no zero a zero." : "Você perdeu " + (apostado - paga) + " nesta rodada.";
    var fim = ""; if (e.saldo < 1) { e.fim = true; fim = " Os créditos acabaram. Fim de jogo."; }
    return { msg: "A bola parou no " + descNum(n) + ". " + partes.join("; ") + ". " + res + " Saldo: " + plural(e.saldo, "crédito", "créditos") + "." + fim, numero: n, lucro: paga - apostado };
  }
  function tabela(e) {
    return "Pagamentos, por crédito apostado: número, 35 para 1; dúzia e coluna, 2 para 1; vermelho, preto, par, ímpar, alto e baixo, 1 para 1. Zero" + (e.duplo ? " e duplo zero são verdes e" : " é verde e") + " só pagam para quem apostou neles. Dúzias: 1 a 12, 13 a 24, 25 a 36. Colunas: a 1 tem 1, 4, 7 até 34; a 2 tem 2, 5, 8 até 35; a 3 tem 3, 6, 9 até 36. Alto é de 19 a 36 e baixo de 1 a 18. Chance de acertar: número " + (e.duplo ? "1 em 38" : "1 em 37") + ", dúzia ou coluna " + (e.duplo ? "12 em 38" : "12 em 37") + ", e cor, paridade ou alto/baixo " + (e.duplo ? "18 em 38" : "18 em 37") + ".";
  }
  function historico(e) {
    if (!e.hist.length) return "A roleta ainda não girou.";
    return "Últimos números, do mais recente ao mais antigo: " + e.hist.slice(-10).reverse().map(function (n) { return nomeNum(n) + " (" + cor(n) + ")"; }).join("; ") + ".";
  }
  function resumo(e) { return "Nível " + e.nome + (e.duplo ? ", roleta americana" : ", roleta europeia") + ". Saldo: " + plural(e.saldo, "crédito", "créditos") + ", o maior foi " + e.maximo + ". Rodadas: " + e.rodadas + "."; }
  function ajuda() {
    return "Comandos: apostar VALOR TIPO, com os tipos vermelho, preto, par, ímpar, alto, baixo, dúzia 1 a 3, coluna 1 a 3 ou um número (por exemplo: apostar 5 vermelho; apostar 2 no 17; apostar 10 dúzia 2; apostar 1 zero); girar; apostas; limpar; repetir; tabela; histórico; saldo; resumo.";
  }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: apostar 5 vermelho, ou ajuda." };
    if (v === "ajuda") return { msg: ajuda() };
    if (v === "tabela" || v === "regras" || v === "pagamentos") return { msg: tabela(e) };
    if (v === "saldo") return { msg: "Saldo: " + plural(e.saldo, "crédito", "créditos") + (e.apostas.length ? ", fora " + totalApostado(e) + " já apostados" : "") + "." };
    if (v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "apostas" || v === "mesa") return { msg: listaApostas(e) };
    if (v === "historico" || v === "ultimos") return { msg: historico(e) };
    if (v === "girar" || v === "gira" || v === "rodar") return girar(e);
    if (v === "limpar" || v === "retirar") return limpar(e);
    if (v === "repetir") return repetir(e);
    if (v === "apostar" || v === "aposta" || /^\d+$/.test(v)) {
      var q = (v === "apostar" || v === "aposta") ? p.slice(1) : p; if (!q.length || !/^\d+$/.test(q[0])) return { msg: "Quanto e em quê? Exemplo: apostar 5 vermelho.", erro: true };
      var valor = Number(q[0]), r = q.slice(1).filter(function (x) { return ["em", "no", "na", "numero", "n", "de", "a", "o"].indexOf(x) < 0; });
      if (!r.length) return { msg: "Aposte em quê? Exemplo: apostar " + valor + " vermelho.", erro: true };
      var w = r[0];
      if (w === "vermelho" || w === "preto") return apostar(e, valor, "cor", w);
      if (w === "par" || w === "impar") return apostar(e, valor, "par", w);
      if (w === "alto" || w === "baixo") return apostar(e, valor, "alto", w);
      if (w === "duzia" || w === "coluna") return /^\d$/.test(r[1] || "") ? apostar(e, valor, w, Number(r[1])) : { msg: "Qual " + w + "? Exemplo: apostar " + valor + " " + w + " 2.", erro: true };
      if (w === "zero") return apostar(e, valor, "numero", r[1] === "zero" ? DUPLO : 0);
      if (w === "duplo" || w === "00") return apostar(e, valor, "numero", DUPLO);
      if (/^\d+$/.test(w)) return apostar(e, valor, "numero", Number(w));
      return { msg: "Não entendi em que apostar. Digite ajuda.", erro: true };
    }
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, MULT: MULT, novo: novo, apostar: apostar, girar: girar, comando: comando, ganhou: ganhou, cor: cor, DUPLO: DUPLO, totalApostado: totalApostado };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  var SOM = H.som; // sons de apoio: ficha ao apostar, bola ao girar, e um som de resultado antes da fala
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + ": " + n.inicio + " créditos, roleta " + (n.duplo ? "americana (com duplo zero)" : "europeia") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (apostar 5 vermelho, apostar 2 no 17, girar, apostas, limpar, repetir, tabela, histórico, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var valorSel = H.el("select", { id: "valor" }, [1, 2, 5, 10, 20].map(function (n) { return H.el("option", { value: String(n), texto: n + (n === 1 ? " crédito" : " créditos") }); }));
  var tipoSel = H.el("select", { id: "tipo" }, [["vermelho", "Vermelho"], ["preto", "Preto"], ["par", "Par"], ["impar", "Ímpar"], ["alto", "Alto (19 a 36)"], ["baixo", "Baixo (1 a 18)"], ["duzia 1", "Primeira dúzia"], ["duzia 2", "Segunda dúzia"], ["duzia 3", "Terceira dúzia"], ["coluna 1", "Coluna 1"], ["coluna 2", "Coluna 2"], ["coluna 3", "Coluna 3"], ["zero", "Zero"]].map(function (x) { return H.el("option", { value: x[0], texto: x[1] }); }));
  var numCampo = H.el("input", { id: "numero", type: "number", min: "0", max: "36", inputmode: "numeric" });
  var apBtn = H.el("button", { type: "button", texto: "Apostar" });
  var numBtn = H.el("button", { type: "button", texto: "Apostar neste número" });
  var botoes = H.el("div", { role: "group", "aria-label": "Mesa" }, [["Girar", "girar"], ["Ler as apostas", "apostas"], ["Limpar as apostas", "limpar"], ["Repetir as apostas", "repetir"], ["Ler o saldo", "saldo"], ["Histórico", "historico"], ["Tabela de pagamentos", "tabela"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { falar(comando(e, x[1]), x[1]); }); return b;
  }));
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, SOM ? SOM.botao() : H.el("span"), H.el("label", { "for": "valor", texto: "Valor" }), valorSel, H.el("label", { "for": "tipo", texto: "Tipo de aposta" }), tipoSel, apBtn,
    H.el("label", { "for": "numero", texto: "Número para apostar, de 0 a 36" }), numCampo, numBtn, botoes, form].forEach(function (x) { jogo.appendChild(x); });
  function falar(r, cmd) {
    var cues = null;
    if (r.erro) cues = "erro";
    else if (r.numero !== undefined) cues = ["giro", r.lucro > 0 ? (r.lucro >= 10 ? "grande" : "ganhou") : r.lucro === 0 ? "empate" : "perdeu"];
    else if (/^apost/.test(cmd || "")) cues = "ficha";
    if (SOM && cues) SOM.anunciar(cues, r.msg); else H.anunciar(r.msg);
    campo.disabled = e.fim;
  }
  apBtn.addEventListener("click", function () { falar(comando(e, "apostar " + valorSel.value + " " + tipoSel.value), "apostar"); });
  numBtn.addEventListener("click", function () { falar(comando(e, "apostar " + valorSel.value + " " + (numCampo.value === "" ? "x" : numCampo.value)), "apostar"); });
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var cmd = campo.value, r = comando(e, cmd); campo.value = ""; falar(r, cmd); if (!e.fim) campo.focus(); });
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo jogo, nível " + e.nome + ", com " + e.saldo + " créditos de mentira, roleta " + (e.duplo ? "americana, com zero e duplo zero" : "europeia, de 0 a 36") + ". Faça suas apostas e depois gire. Exemplo: apostar 5 vermelho. O comando ajuda lista tudo."); }
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
