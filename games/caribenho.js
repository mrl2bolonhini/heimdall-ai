// Poker caribenho (Caribbean Stud) contra a banca, com créditos virtuais (nunca dinheiro de verdade).
// Você aposta o "ante" e recebe cinco cartas abertas; a banca recebe cinco, com só uma aberta. Você desiste (perde o ante) ou aumenta, pagando mais duas vezes o ante.
// A banca só joga se tiver Ás e Rei ou melhor. Se não tiver, o ante paga 1 para 1 e o aumento volta. Se tiver, vence a melhor mão: o ante paga 1 para 1 e o aumento paga conforme a mão.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", inicio: 100, dicas: 999 },
    normal: { nome: "normal", inicio: 100, dicas: 3 },
    dificil: { nome: "difícil", inicio: 60, dicas: 0 }
  };
  var ANTE_MAX = 25;
  var NAIPES = ["c", "o", "p", "e"], NOME_NAIPE = { c: "copas", o: "ouros", p: "paus", e: "espadas" };
  var NOME_VALOR = { 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "Valete", 12: "Dama", 13: "Rei", 14: "Ás" };
  var PLURAL_VALOR = { 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "Valetes", 12: "Damas", 13: "Reis", 14: "Ases" };
  var CATEGORIAS = ["carta alta", "par", "dois pares", "trinca", "sequência", "flush", "full house", "quadra", "straight flush", "royal flush"];
  var PAGA = [0, 1, 2, 3, 4, 5, 7, 20, 50, 100]; // aumento: vezes o valor do aumento, por categoria

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function nome(c) { return NOME_VALOR[c.r] + " de " + NOME_NAIPE[c.s]; }
  function baralhoNovo(rnd) {
    var b = [], i, j; NAIPES.forEach(function (s) { for (i = 2; i <= 14; i++) b.push({ r: i, s: s }); });
    for (i = b.length - 1; i > 0; i--) { j = rnd(i + 1); var t = b[i]; b[i] = b[j]; b[j] = t; }
    return b;
  }
  // Avalia cinco cartas: {cat, desempate:[...]} (comparar categoria e depois a lista).
  function avaliar(m) {
    var rs = m.map(function (c) { return c.r; }).sort(function (a, b) { return b - a; }), cont = {}, i;
    rs.forEach(function (r) { cont[r] = (cont[r] || 0) + 1; });
    var grupos = Object.keys(cont).map(function (r) { return { r: Number(r), n: cont[r] }; }).sort(function (a, b) { return b.n - a.n || b.r - a.r; });
    var flush = m.every(function (c) { return c.s === m[0].s; }), reta = false, alta = rs[0];
    if (grupos.length === 5) { if (rs[0] - rs[4] === 4) reta = true; else if (rs.join() === "14,5,4,3,2") { reta = true; alta = 5; } }
    var cat, des;
    if (reta && flush) { cat = alta === 14 ? 9 : 8; des = [alta]; }
    else if (grupos[0].n === 4) { cat = 7; des = [grupos[0].r, grupos[1].r]; }
    else if (grupos[0].n === 3 && grupos[1].n === 2) { cat = 6; des = [grupos[0].r, grupos[1].r]; }
    else if (flush) { cat = 5; des = rs; }
    else if (reta) { cat = 4; des = [alta]; }
    else if (grupos[0].n === 3) { cat = 3; des = grupos.map(function (g) { return g.r; }); }
    else if (grupos[0].n === 2 && grupos[1].n === 2) { cat = 2; des = grupos.map(function (g) { return g.r; }); }
    else if (grupos[0].n === 2) { cat = 1; des = grupos.map(function (g) { return g.r; }); }
    else { cat = 0; des = rs; }
    return { cat: cat, des: des };
  }
  function comparar(a, b) {
    if (a.cat !== b.cat) return a.cat > b.cat ? 1 : -1;
    for (var i = 0; i < a.des.length; i++) if (a.des[i] !== b.des[i]) return a.des[i] > b.des[i] ? 1 : -1;
    return 0;
  }
  function banca_joga(m, h) { // Ás e Rei ou melhor
    if (h.cat >= 1) return true;
    var rs = m.map(function (c) { return c.r; }); return rs.indexOf(14) >= 0 && rs.indexOf(13) >= 0;
  }
  function descreverMao(m) {
    var h = avaliar(m), d = h.des, c = h.cat;
    switch (c) {
      case 0: return "carta alta, " + NOME_VALOR[d[0]] + " alto";
      case 1: return "um par de " + PLURAL_VALOR[d[0]];
      case 2: return "dois pares, de " + PLURAL_VALOR[d[0]] + " e de " + PLURAL_VALOR[d[1]];
      case 3: return "uma trinca de " + PLURAL_VALOR[d[0]];
      case 4: return "uma sequência até " + NOME_VALOR[d[0]];
      case 5: return "um flush, cinco cartas do mesmo naipe, com " + NOME_VALOR[d[0]] + " alto";
      case 6: return "um full house, trinca de " + PLURAL_VALOR[d[0]] + " e par de " + PLURAL_VALOR[d[1]];
      case 7: return "uma quadra de " + PLURAL_VALOR[d[0]];
      case 8: return "um straight flush até " + NOME_VALOR[d[0]];
      default: return "um royal flush";
    }
  }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k];
    return { nivel: k, nome: n.nome, saldo: n.inicio, maximo: n.inicio, rnd: rnd || sorteio, fase: "apostar", ante: 0, jog: [], ban: [], baralho: [], ultima: 0, rodadas: 0, vitorias: 0, derrotas: 0, empates: 0, desistencias: 0, dicas: n.dicas, fim: false };
  }
  function apostar(e, ante) {
    if (e.fim) return { msg: "Os créditos acabaram. Comece um novo jogo.", erro: true };
    if (e.fase !== "apostar") return { msg: "Há uma mão em andamento. Diga aumentar ou desistir.", erro: true };
    if (!(ante >= 1) || ante % 1 || ante > ANTE_MAX) return { msg: "O ante é um número inteiro de 1 a " + ANTE_MAX + " créditos.", erro: true };
    if (ante * 3 > e.saldo) return { msg: "Para poder aumentar, você precisa de três vezes o ante: " + (ante * 3) + " créditos. Você tem " + e.saldo + ". Aposte menos.", erro: true };
    var b = baralhoNovo(e.rnd); e.jog = b.splice(0, 5); e.ban = b.splice(0, 5); e.baralho = b;
    e.ante = ante; e.saldo -= ante; e.fase = "decidir"; e.ultima = ante;
    var h = avaliar(e.jog);
    return { msg: "Ante de " + ante + ". Suas cartas: " + e.jog.map(nome).join(", ") + ". Você tem " + descreverMao(e.jog) + ". A banca mostra " + nome(e.ban[0]) + ". Diga aumentar, para pagar mais " + (ante * 2) + ", ou desistir, para perder o ante." };
  }
  function resolver(e, aumentou) {
    var raise = aumentou ? e.ante * 2 : 0, hj = avaliar(e.jog), hb = avaliar(e.ban), qual = banca_joga(e.ban, hb), msg, ret = 0, res;
    var abre = "A banca revela: " + e.ban.map(nome).join(", ") + ", com " + descreverMao(e.ban) + ". ";
    if (!aumentou) { e.desistencias++; e.derrotas++; res = "Você desistiu e perdeu o ante de " + e.ante + "."; msg = "Você desistiu. A banca não precisava mostrar a mão."; msg = msg + " " + res; }
    else if (!qual) { ret = e.ante * 2 + raise; e.vitorias++; res = "A banca não tem Ás e Rei nem um par, então não joga: o ante paga 1 para 1 (você recebe " + (e.ante * 2) + ") e o aumento de " + raise + " é devolvido."; msg = abre + res; }
    else {
      var c = comparar(hj, hb);
      if (c > 0) { var paga = raise * PAGA[hj.cat]; ret = e.ante * 2 + raise + paga; e.vitorias++; res = "Você venceu com " + descreverMao(e.jog) + ". O ante paga 1 para 1 (" + e.ante + ") e o aumento paga " + PAGA[hj.cat] + " para 1 (" + paga + "), então você recebe " + ret + " no total."; }
      else if (c === 0) { ret = e.ante + raise; e.empates++; res = "Empate: o ante e o aumento voltam."; }
      else { e.derrotas++; res = "A banca venceu. Você perdeu o ante de " + e.ante + " e o aumento de " + raise + "."; }
      msg = abre + res;
    }
    e.saldo -= raise; e.saldo += ret; e.rodadas++; e.fase = "apostar"; if (e.saldo > e.maximo) e.maximo = e.saldo;
    var fim = ""; if (e.saldo < 3) { e.fim = true; fim = " Os créditos não bastam para outro ante. Fim de jogo."; }
    return { msg: msg + " Saldo: " + plural(e.saldo, "crédito", "créditos") + "." + fim };
  }
  function aumentar(e) { if (e.fase !== "decidir") return { msg: "Não há mão em andamento. Aposte o ante com apostar N.", erro: true }; return resolver(e, true); }
  function desistir(e) { if (e.fase !== "decidir") return { msg: "Não há mão em andamento.", erro: true }; return resolver(e, false); }

  // Valor esperado (em créditos por ante) de aumentar, simulando as cartas que faltam à banca.
  function valorEsperado(e, sims, rnd) {
    var vistas = {}; e.jog.concat([e.ban[0]]).forEach(function (c) { vistas[c.r + c.s] = true; });
    var resto = []; NAIPES.forEach(function (s) { for (var r = 2; r <= 14; r++) if (!vistas[r + s]) resto.push({ r: r, s: s }); });
    var hj = avaliar(e.jog), tot = 0, k, i, j;
    for (k = 0; k < sims; k++) {
      var b = resto.slice(), mao = [e.ban[0]];
      for (i = 0; i < 4; i++) { j = rnd(b.length - i) + i; var t = b[i]; b[i] = b[j]; b[j] = t; mao.push(b[i]); }
      var hb = avaliar(mao), ganho;
      if (!banca_joga(mao, hb)) ganho = 1; // ante paga, aumento volta
      else { var c = comparar(hj, hb); ganho = c > 0 ? 1 + 2 * PAGA[hj.cat] : c === 0 ? 0 : -3; }
      tot += ganho;
    }
    return tot / sims;
  }
  function conselho(e, sims, rnd) { var v = valorEsperado(e, sims || 1500, rnd || e.rnd); return { aumentar: v > -1, ve: v }; }
  function dica(e) {
    if (e.fim) return { msg: "O jogo terminou." };
    if (e.dicas <= 0) return { msg: NIVEIS[e.nivel].dicas === 0 ? "No nível difícil não há dicas." : "As dicas acabaram." };
    var m;
    if (e.fase === "decidir") {
      var c = conselho(e); m = (c.aumentar ? "aumentar" : "desistir") + ". Simulando as mãos possíveis da banca, aumentar rende em média " + (c.ve >= 0 ? "um ganho de " : "uma perda de ") + Math.abs(c.ve).toFixed(2).replace(".", ",") + " ante, contra uma perda certa de 1 ante se você desistir.";
    } else m = "aposte um ante pequeno em relação ao saldo, pois você precisa ter três vezes o ante para poder aumentar. Como regra, a casa leva cerca de 5% do que se aposta, jogando bem.";
    if (NIVEIS[e.nivel].dicas < 100) e.dicas--;
    return { msg: "Dica: " + m + (NIVEIS[e.nivel].dicas < 100 ? " Dicas restantes: " + e.dicas + "." : "") };
  }
  function tabela() {
    return "Aumento paga, para cada crédito aumentado: um par 1 para 1, dois pares 2, trinca 3, sequência 4, flush 5, full house 7, quadra 20, straight flush 50 e royal flush 100. O ante sempre paga 1 para 1 quando você vence. A banca joga só com Ás e Rei ou melhor; se não jogar, o ante paga e o aumento volta. Empate devolve tudo. O aumento é sempre duas vezes o ante, e o ante vai de 1 a " + ANTE_MAX + ".";
  }
  function lerMao(e) {
    if (e.fase !== "decidir") return "Não há mão em andamento. Aposte o ante com apostar N. Saldo: " + e.saldo + ".";
    return "Suas cartas: " + e.jog.map(nome).join(", ") + ". Você tem " + descreverMao(e.jog) + ". A banca mostra " + nome(e.ban[0]) + ".";
  }
  function resumo(e) { return "Nível " + e.nome + ". Saldo: " + plural(e.saldo, "crédito", "créditos") + ", o maior foi " + e.maximo + ". Mãos: " + e.rodadas + " (vitórias " + e.vitorias + ", empates " + e.empates + ", derrotas " + e.derrotas + ", desistências " + e.desistencias + ")."; }
  function ajuda() { return "Comandos: apostar N, para o ante de 1 a " + ANTE_MAX + " (ou repetir); depois aumentar ou desistir; mao, banca, saldo, tabela, dica, resumo."; }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: apostar 5, ou ajuda." };
    if (v === "ajuda") return { msg: ajuda() };
    if (v === "tabela" || v === "regras" || v === "pagamentos") return { msg: tabela() };
    if (v === "saldo") return { msg: "Saldo: " + plural(e.saldo, "crédito", "créditos") + "." };
    if (v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "mao" || v === "cartas" || v === "ler") return { msg: lerMao(e) };
    if (v === "banca") return { msg: e.fase === "decidir" ? "A banca mostra " + nome(e.ban[0]) + " e tem quatro cartas viradas." : "Não há mão em andamento." };
    if (v === "dica") return dica(e);
    if (v === "aumentar" || v === "aumento" || v === "subir" || v === "pagar") return aumentar(e);
    if (v === "desistir" || v === "fugir" || v === "fold") return desistir(e);
    if (v === "repetir") return e.ultima ? apostar(e, Math.min(e.ultima, Math.floor(e.saldo / 3))) : { msg: "Ainda não há ante anterior.", erro: true };
    if (v === "apostar" || v === "ante" || v === "aposta" || /^\d+$/.test(v)) { var q = /^\d+$/.test(v) ? p : p.slice(1); return /^\d+$/.test(q[0] || "") ? apostar(e, Number(q[0])) : { msg: "Quanto? Exemplo: apostar 5.", erro: true }; }
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, PAGA: PAGA, novo: novo, avaliar: avaliar, comparar: comparar, bancaJoga: banca_joga, descreverMao: descreverMao, apostar: apostar, aumentar: aumentar, desistir: desistir, comando: comando, conselho: conselho, valorEsperado: valorEsperado, nome: nome };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + ": " + n.inicio + " créditos" + (k === "facil" ? ", dicas à vontade" : k === "normal" ? ", 3 dicas" : ", sem dicas") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (apostar 5, aumentar, desistir, mao, banca, saldo, tabela, dica, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var anteSel = H.el("select", { id: "ante" }, [1, 2, 5, 10, 25].map(function (n) { return H.el("option", { value: String(n), texto: n + (n === 1 ? " crédito" : " créditos") }); }));
  var anteBtn = H.el("button", { type: "button", texto: "Apostar o ante" });
  var botoes = H.el("div", { role: "group", "aria-label": "Jogadas" }, [["Aumentar", "aumentar"], ["Desistir", "desistir"], ["Ler a mão", "mao"], ["Ler a banca", "banca"], ["Repetir o ante", "repetir"], ["Ler o saldo", "saldo"], ["Tabela de pagamentos", "tabela"], ["Dica", "dica"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { falar(comando(e, x[1]).msg, x[1]); }); return b;
  }));
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, H.som ? H.som.botao() : H.el("span"), H.el("label", { "for": "ante", texto: "Valor do ante" }), anteSel, anteBtn, botoes, form].forEach(function (x) { jogo.appendChild(x); });
  function falar(m, cmd) { var c = H.som && H.som.cue(m, cmd); if (c) H.som.anunciar(c, m); else H.anunciar(m); campo.disabled = e.fim; }
  anteBtn.addEventListener("click", function () { falar(comando(e, "apostar " + anteSel.value).msg, "apostar " + anteSel.value); });
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var cmd = campo.value, r = comando(e, cmd); campo.value = ""; falar(r.msg, cmd); if (!e.fim) campo.focus(); });
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo jogo, nível " + e.nome + ", com " + e.saldo + " créditos virtuais. Aposte o ante, por exemplo apostar 5, e depois decida entre aumentar e desistir. O comando ajuda lista tudo."); }
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
