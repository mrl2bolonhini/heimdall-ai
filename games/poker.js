// Poker Texas hold'em, você contra o computador (um contra um), com fichas virtuais (nunca dinheiro de verdade).
// Cada um começa com o mesmo número de fichas. As cegas sobem a cada 6 mãos, e a partida acaba quando alguém fica sem fichas.
// Em cada mão: duas cartas só suas, cinco cartas na mesa (flop de três, turn e river) e quatro rodadas de apostas. Vence a melhor mão de cinco cartas entre as sete.
// O computador decide pela chance de ganhar (simulada) e pelo preço de pagar; o nível muda o quanto ele aposta, paga e blefa.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", fichas: 300, dicas: 999, sims: 120 },
    normal: { nome: "normal", fichas: 200, dicas: 5, sims: 250 },
    dificil: { nome: "difícil", fichas: 200, dicas: 0, sims: 400 }
  };
  var MAOS_POR_NIVEL_DE_CEGA = 6;
  var NAIPES = ["c", "o", "p", "e"], NOME_NAIPE = { c: "copas", o: "ouros", p: "paus", e: "espadas" };
  var NOME_VALOR = { 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "Valete", 12: "Dama", 13: "Rei", 14: "Ás" };
  var PLURAL_VALOR = { 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10", 11: "Valetes", 12: "Damas", 13: "Reis", 14: "Ases" };
  var COMBOS = []; (function () { for (var a = 0; a < 7; a++) for (var b = a + 1; b < 7; b++) { var c = []; for (var i = 0; i < 7; i++) if (i !== a && i !== b) c.push(i); COMBOS.push(c); } })();

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function nome(c) { return NOME_VALOR[c.r] + " de " + NOME_NAIPE[c.s]; }
  function lista(cs) { return cs.map(nome).join(", "); }
  function baralhoNovo(rnd) {
    var b = [], i, j; NAIPES.forEach(function (s) { for (i = 2; i <= 14; i++) b.push({ r: i, s: s }); });
    for (i = b.length - 1; i > 0; i--) { j = rnd(i + 1); var t = b[i]; b[i] = b[j]; b[j] = t; }
    return b;
  }
  // Cinco cartas: {cat, des}. Categorias: 0 carta alta, 1 par, 2 dois pares, 3 trinca, 4 sequência, 5 flush, 6 full house, 7 quadra, 8 straight flush, 9 royal flush.
  function avaliar5(m) {
    var rs = m.map(function (c) { return c.r; }).sort(function (a, b) { return b - a; }), cont = {};
    rs.forEach(function (r) { cont[r] = (cont[r] || 0) + 1; });
    var g = Object.keys(cont).map(function (r) { return { r: Number(r), n: cont[r] }; }).sort(function (a, b) { return b.n - a.n || b.r - a.r; });
    var flush = m.every(function (c) { return c.s === m[0].s; }), reta = false, alta = rs[0];
    if (g.length === 5) { if (rs[0] - rs[4] === 4) reta = true; else if (rs.join() === "14,5,4,3,2") { reta = true; alta = 5; } }
    var d = g.map(function (x) { return x.r; });
    if (reta && flush) return { cat: alta === 14 ? 9 : 8, des: [alta] };
    if (g[0].n === 4) return { cat: 7, des: d };
    if (g[0].n === 3 && g[1].n === 2) return { cat: 6, des: d };
    if (flush) return { cat: 5, des: rs };
    if (reta) return { cat: 4, des: [alta] };
    if (g[0].n === 3) return { cat: 3, des: d };
    if (g[0].n === 2 && g[1].n === 2) return { cat: 2, des: d };
    if (g[0].n === 2) return { cat: 1, des: d };
    return { cat: 0, des: rs };
  }
  function comparar(a, b) {
    if (a.cat !== b.cat) return a.cat > b.cat ? 1 : -1;
    for (var i = 0; i < a.des.length; i++) if (a.des[i] !== b.des[i]) return a.des[i] > b.des[i] ? 1 : -1;
    return 0;
  }
  // Melhor mão de cinco entre cinco a sete cartas.
  function melhor(cs) {
    if (cs.length === 5) { var h = avaliar5(cs); h.cartas = cs; return h; }
    var best = null, i, k;
    if (cs.length === 7) { for (k = 0; k < COMBOS.length; k++) { var m = COMBOS[k].map(function (j) { return cs[j]; }), h2 = avaliar5(m); if (!best || comparar(h2, best) > 0) { best = h2; best.cartas = m; } } return best; }
    var n = cs.length; // 6 cartas: tira uma
    for (i = 0; i < n; i++) { var m2 = cs.filter(function (_, j) { return j !== i; }), h3 = avaliar5(m2); if (!best || comparar(h3, best) > 0) { best = h3; best.cartas = m2; } }
    return best;
  }
  function descreverMao(h) {
    var d = h.des;
    switch (h.cat) {
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
  // Chance de vencer contra uma mão aleatória (empate vale meia vitória), completando a mesa ao acaso.
  function equidade(buraco, mesa, sims, rnd) {
    var vistas = {}; buraco.concat(mesa).forEach(function (c) { vistas[c.r + c.s] = true; });
    var resto = []; NAIPES.forEach(function (s) { for (var r = 2; r <= 14; r++) if (!vistas[r + s]) resto.push({ r: r, s: s }); });
    var falta = 5 - mesa.length, tot = 0, k, i, j;
    for (k = 0; k < sims; k++) {
      var n = falta + 2;
      for (i = 0; i < n; i++) { j = rnd(resto.length - i) + i; var t = resto[i]; resto[i] = resto[j]; resto[j] = t; }
      var board = mesa.concat(resto.slice(0, falta)), opp = resto.slice(falta, falta + 2);
      var c = comparar(melhor(buraco.concat(board)), melhor(opp.concat(board)));
      tot += c > 0 ? 1 : c === 0 ? 0.5 : 0;
    }
    return tot / sims;
  }

  function cegas(e) { var i = Math.floor((e.mao - 1) / MAOS_POR_NIVEL_DE_CEGA); return { p: 5 * Math.pow(2, i), g: 10 * Math.pow(2, i) }; }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k], r = rnd || sorteio;
    return { nivel: k, nome: n.nome, rnd: r, sims: n.sims, fichas: [n.fichas, n.fichas], inicio: n.fichas, botao: r(2), mao: 0, fase: "entre", rua: 0, baralho: [], buraco: [[], []], mesa: [], aposta: [0, 0], comp: [0, 0], vez: 0, agiu: [false, false], minAumento: 10, aumentos: 0, dicas: n.dicas, fim: null, maosGanhas: 0, maosPerdidas: 0, ultimo: "" };
  }
  var QUEM = ["você", "o computador"];
  function maxAp(e) { return Math.max(e.aposta[0], e.aposta[1]); }
  function pote(e) { return e.comp[0] + e.comp[1]; }
  function limite(e, q) { return Math.min(e.fichas[q] + e.aposta[q], e.fichas[1 - q] + e.aposta[1 - q]); }
  function postar(e, q, v) { v = Math.min(v, e.fichas[q]); e.fichas[q] -= v; e.aposta[q] += v; e.comp[q] += v; return v; }

  function iniciarMao(e) {
    var out = [];
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    if (e.fase !== "entre") return { msg: "Há uma mão em andamento.", erro: true };
    e.mao++; if (e.mao > 1) e.botao = 1 - e.botao;
    var cg = cegas(e), ef = Math.min(e.fichas[0], e.fichas[1]);
    e.baralho = baralhoNovo(e.rnd); e.buraco = [e.baralho.splice(0, 2), e.baralho.splice(0, 2)]; e.mesa = []; e.rua = 0; e.aposta = [0, 0]; e.comp = [0, 0]; e.agiu = [false, false]; e.minAumento = cg.g; e.aumentos = 0;
    var sb = e.botao, bb = 1 - e.botao;
    postar(e, sb, Math.min(cg.p, ef)); postar(e, bb, Math.min(cg.g, ef));
    e.fase = "apostas"; e.vez = sb;
    if (e.mao > 1 && (e.mao - 1) % MAOS_POR_NIVEL_DE_CEGA === 0) out.push("As cegas subiram para " + cg.p + " e " + cg.g + ".");
    out.push("Mão " + e.mao + ". " + (e.botao === 0 ? "Você é o dealer e paga a cega pequena de " + cg.p + "; o computador paga a grande de " + cg.g + "." : "O computador é o dealer e paga a cega pequena de " + cg.p + "; você paga a grande de " + cg.g + ".") + " Suas cartas: " + lista(e.buraco[0]) + ".");
    if (e.fichas[0] === 0 || e.fichas[1] === 0) { out.push("Alguém está com todas as fichas na mesa."); correrAteOFim(e, out); return { msg: out.join(" ") }; }
    seguir(e, out);
    return { msg: out.join(" ") };
  }
  function pedidoDaVez(e) {
    var dif = maxAp(e) - e.aposta[0], pot = pote(e), ef = limite(e, 0) - e.aposta[0];
    return "Sua vez. Pote: " + pot + ". Suas fichas: " + e.fichas[0] + ". " + (dif > 0 ? "Para pagar: " + Math.min(dif, e.fichas[0]) + ". Você pode pagar, aumentar (apostar N, com N a partir de " + Math.min(maxAp(e) + e.minAumento, limite(e, 0)) + "), tudo ou desistir." : "Você pode passar ou apostar (apostar N, de " + Math.min(e.minAumento, limite(e, 0)) + " a " + limite(e, 0) + "), ou tudo.");
  }
  // Deixa o computador jogar enquanto for a vez dele; depois pede a sua jogada.
  function seguir(e, out) {
    var guarda = 0;
    while (e.fase === "apostas" && e.vez === 1 && guarda++ < 20) {
      var d = decidirCPU(e, 1, NIVEIS[e.nivel], e.sims);
      aplicar(e, 1, d.tipo, d.valor, out);
    }
    if (e.fase === "apostas" && e.vez === 0) out.push(pedidoDaVez(e));
  }
  function aplicar(e, q, tipo, valor, out) {
    var dif = maxAp(e) - e.aposta[q], quem = q === 1 ? "O computador" : "Você", antes = maxAp(e), cap = limite(e, q);
    if (tipo === "desistir") { out.push(quem + (q === 1 ? " desiste." : " desiste.")); fimMaoPorDesistencia(e, q, out); return; }
    if (tipo === "passar") out.push(quem + " passa.");
    else if (tipo === "pagar") { var p = postar(e, q, dif); out.push(quem + " paga " + p + (e.fichas[q] === 0 ? ", com todas as fichas." : ".")); }
    else {
      var X = Math.min(valor, cap);
      if (X <= antes) { var p2 = postar(e, q, dif); out.push(quem + " paga " + p2 + (e.fichas[q] === 0 ? ", com todas as fichas." : ".")); tipo = "pagar"; }
      else {
        postar(e, q, X - e.aposta[q]); var tam = X - antes; if (tam >= e.minAumento) e.minAumento = tam; e.aumentos++;
        e.agiu = [false, false];
        out.push(quem + (e.fichas[q] === 0 ? " vai de tudo, " + X + " nesta rodada." : antes === 0 ? " aposta " + X + "." : " aumenta para " + X + "."));
      }
    }
    e.agiu[q] = true;
    var completa = e.agiu[0] && e.agiu[1] && e.aposta[0] === e.aposta[1];
    if (completa) {
      if (e.fichas[0] === 0 || e.fichas[1] === 0) correrAteOFim(e, out);
      else if (e.rua === 3) mostrar(e, out);
      else proximaRua(e, out);
    } else e.vez = 1 - q;
  }
  function proximaRua(e, out) {
    e.rua++; e.aposta = [0, 0]; e.agiu = [false, false]; e.minAumento = cegas(e).g; e.aumentos = 0;
    if (e.rua === 1) { e.mesa = e.mesa.concat(e.baralho.splice(0, 3)); out.push("Flop: " + lista(e.mesa) + "."); }
    else { var c = e.baralho.shift(); e.mesa.push(c); out.push((e.rua === 2 ? "Turn: " : "River: ") + nome(c) + ". Mesa: " + lista(e.mesa) + "."); }
    out.push("Você tem " + descreverMao(melhor(e.buraco[0].concat(e.mesa))) + ".");
    e.vez = 1 - e.botao;
  }
  function correrAteOFim(e, out) {
    while (e.mesa.length < 5) {
      if (e.mesa.length === 0) e.mesa = e.mesa.concat(e.baralho.splice(0, 3)); else e.mesa.push(e.baralho.shift());
    }
    out.push("As fichas estão todas na mesa, então as cartas da mesa são viradas: " + lista(e.mesa) + ".");
    mostrar(e, out);
  }
  function mostrar(e, out) {
    var h0 = melhor(e.buraco[0].concat(e.mesa)), h1 = melhor(e.buraco[1].concat(e.mesa)), c = comparar(h0, h1), pot = pote(e), msg;
    out.push("Showdown. Você: " + lista(e.buraco[0]) + ", com " + descreverMao(h0) + ". O computador: " + lista(e.buraco[1]) + ", com " + descreverMao(h1) + ".");
    if (c > 0) { e.fichas[0] += pot; e.maosGanhas++; msg = "Você ganhou o pote de " + pot + "."; }
    else if (c < 0) { e.fichas[1] += pot; e.maosPerdidas++; msg = "O computador ganhou o pote de " + pot + "."; }
    else { e.fichas[0] += e.comp[0]; e.fichas[1] += e.comp[1]; msg = "Empate: o pote é dividido."; }
    out.push(msg); fecharMao(e, out);
  }
  function fimMaoPorDesistencia(e, q, out) {
    var v = 1 - q, pot = pote(e); e.fichas[v] += pot; if (v === 0) e.maosGanhas++; else e.maosPerdidas++;
    out.push((v === 0 ? "Você ganhou" : "O computador ganhou") + " o pote de " + pot + "."); fecharMao(e, out);
  }
  function fecharMao(e, out) {
    e.fase = "entre"; e.aposta = [0, 0]; e.comp = [0, 0];
    if (e.fichas[0] === 0) { e.fim = "perdeu"; out.push("Você ficou sem fichas. Fim de jogo: o computador venceu a partida."); }
    else if (e.fichas[1] === 0) { e.fim = "ganhou"; out.push("O computador ficou sem fichas. Você venceu a partida!"); }
    else out.push("Suas fichas: " + e.fichas[0] + ", do computador: " + e.fichas[1] + ". Diga continuar para a próxima mão.");
  }

  // Decisão do computador. `nv` é o nível ({nome}); `sims` o número de simulações.
  function decidirCPU(e, q, nv, sims) {
    var dif = maxAp(e) - e.aposta[q], pot = pote(e), cap = limite(e, q), eq = equidade(e.buraco[q], e.mesa, sims, e.rnd), r = e.rnd(1000) / 1000, nome = nv.nome;
    function aumentarPara(frac) {
      var alvo = maxAp(e) + Math.max(e.minAumento, Math.round(pot * frac) + dif);
      alvo = Math.min(alvo, cap); if (alvo >= cap * 0.7) alvo = cap;
      return alvo;
    }
    var podeAumentar = cap > maxAp(e) && e.aumentos < 4;
    if (dif > 0) {
      var need = dif / (pot + dif);
      if (nome === "fácil") { if (podeAumentar && eq > 0.85) return { tipo: "apostar", valor: aumentarPara(0.5) }; return eq > need * 0.7 ? { tipo: "pagar" } : { tipo: "desistir" }; }
      if (nome === "normal") { if (podeAumentar && eq > 0.72) return { tipo: "apostar", valor: aumentarPara(0.7) }; return eq > need + 0.02 ? { tipo: "pagar" } : { tipo: "desistir" }; }
      if (podeAumentar && (eq > 0.66 || (eq > 0.42 && r < 0.07))) return { tipo: "apostar", valor: aumentarPara(eq > 0.8 ? 1 : 0.75) };
      return eq > need + 0.03 ? { tipo: "pagar" } : { tipo: "desistir" };
    }
    if (nome === "fácil") return podeAumentar && eq > 0.75 ? { tipo: "apostar", valor: aumentarPara(0.4) } : { tipo: "passar" };
    if (nome === "normal") return podeAumentar && eq > 0.58 ? { tipo: "apostar", valor: aumentarPara(0.6) } : { tipo: "passar" };
    return podeAumentar && (eq > 0.55 || (eq < 0.48 && r < 0.14)) ? { tipo: "apostar", valor: aumentarPara(eq > 0.8 ? 1 : 0.65) } : { tipo: "passar" };
  }

  // Comandos do jogador
  function jogar(e, tipo, valor) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo.", erro: true };
    if (e.fase === "entre") return { msg: "Não há mão em andamento. Diga continuar para dar as cartas.", erro: true };
    if (e.vez !== 0) return { msg: "Não é a sua vez.", erro: true };
    var dif = maxAp(e) - e.aposta[0], cap = limite(e, 0);
    if (tipo === "passar" && dif > 0) return { msg: "Há uma aposta de " + dif + " a pagar. Diga pagar, aumentar ou desistir.", erro: true };
    if (tipo === "pagar" && dif === 0) return { msg: "Não há nada a pagar. Diga passar ou apostar N.", erro: true };
    if (tipo === "tudo") { tipo = "apostar"; valor = cap; }
    if (tipo === "apostar") {
      if (!(valor >= 1) || valor % 1) return { msg: "Quanto? Exemplo: apostar 40.", erro: true };
      if (cap <= maxAp(e)) return { msg: "Você só pode pagar ou desistir: o computador não tem fichas para cobrir mais.", erro: true };
      var min = Math.min(maxAp(e) + e.minAumento, cap), X = Math.min(valor, cap);
      if (valor > cap) X = cap;
      if (X < min) return { msg: "A aposta mínima agora é " + min + " no total desta rodada" + (maxAp(e) ? " (" + e.minAumento + " acima da maior aposta de " + maxAp(e) + ")" : "") + ". Você tem " + (e.fichas[0] + e.aposta[0]) + ".", erro: true };
      valor = X;
    }
    var out = []; aplicar(e, 0, tipo, valor, out); seguir(e, out);
    return { msg: out.join(" ") };
  }
  function lerMao(e) {
    if (e.fase === "entre") return "Não há mão em andamento. Suas fichas: " + e.fichas[0] + ", do computador: " + e.fichas[1] + "." + (e.fim ? "" : " Diga continuar.");
    var dif = maxAp(e) - e.aposta[0];
    return "Suas cartas: " + lista(e.buraco[0]) + ". Mesa: " + (e.mesa.length ? lista(e.mesa) + ". Você tem " + descreverMao(melhor(e.buraco[0].concat(e.mesa))) : "ainda sem cartas") + ". Pote: " + pote(e) + ". Suas fichas: " + e.fichas[0] + ", do computador: " + e.fichas[1] + ". Apostas nesta rodada: você " + e.aposta[0] + ", computador " + e.aposta[1] + (dif > 0 ? ". Para pagar: " + Math.min(dif, e.fichas[0]) : "") + ".";
  }
  function dica(e) {
    if (e.fim) return { msg: "O jogo terminou." };
    if (e.dicas <= 0) return { msg: NIVEIS[e.nivel].dicas === 0 ? "No nível difícil não há dicas." : "As dicas acabaram." };
    if (e.fase !== "apostas") return { msg: "Dica: não há mão em andamento. Diga continuar." };
    if (NIVEIS[e.nivel].dicas < 100) e.dicas--;
    var eq = equidade(e.buraco[0], e.mesa, 1200, e.rnd), dif = maxAp(e) - e.aposta[0], pot = pote(e), pc = Math.round(eq * 100), s;
    if (dif > 0) { var need = dif / (pot + dif); s = "pagar custa " + Math.min(dif, e.fichas[0]) + " para um pote de " + pot + ", então você precisa ganhar mais de " + Math.round(need * 100) + "% das vezes. " + (eq > 0.72 ? "Sua mão é forte: aumentar é bom." : eq > need + 0.02 ? "Vale pagar." : "Melhor desistir."); }
    else s = eq > 0.6 ? "sua mão é boa, vale apostar, algo como metade do pote." : "sua mão é fraca ou média, passar é seguro.";
    return { msg: "Dica: contra uma mão qualquer, você ganha cerca de " + pc + "% das vezes (isso não leva em conta as apostas dele). " + s + (NIVEIS[e.nivel].dicas < 100 ? " Dicas restantes: " + e.dicas + "." : "") };
  }
  function tabela() { return "Das mais fortes às mais fracas: royal flush, straight flush, quadra, full house, flush (cinco do mesmo naipe), sequência, trinca, dois pares, um par e carta alta. Vale a melhor mão de cinco cartas entre as suas duas e as cinco da mesa. O Ás vale mais que o Rei, mas também pode ser o 1 na sequência Ás, 2, 3, 4, 5."; }
  function resumo(e) { var cg = cegas(e); return "Nível " + e.nome + ". Mão " + e.mao + ", cegas " + cg.p + " e " + cg.g + ". Suas fichas: " + e.fichas[0] + ", do computador: " + e.fichas[1] + ". Mãos ganhas: " + e.maosGanhas + ", perdidas: " + e.maosPerdidas + "."; }
  function ajuda() { return "Comandos: continuar, para dar as cartas de uma mão; pagar; passar; apostar N, que é o total que você terá apostado nesta rodada (também serve para aumentar); tudo; desistir; mao, para ler cartas, mesa e pote; fichas; tabela, para ver a ordem das mãos; dica; resumo."; }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: continuar, ou ajuda." };
    if (v === "ajuda") return { msg: ajuda() };
    if (v === "tabela" || v === "ranking") return { msg: tabela() };
    if (v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "mao" || v === "mesa" || v === "cartas" || v === "pote" || v === "ler") return { msg: lerMao(e) };
    if (v === "fichas" || v === "saldo") return { msg: "Suas fichas: " + e.fichas[0] + ", do computador: " + e.fichas[1] + (e.fase === "apostas" ? ". Pote: " + pote(e) : "") + "." };
    if (v === "dica") return dica(e);
    if (v === "continuar" || v === "proxima" || v === "dar" || v === "iniciar" || v === "comecar") return iniciarMao(e);
    if (v === "pagar" || v === "call" || v === "cobrir") return jogar(e, "pagar");
    if (v === "passar" || v === "check") return jogar(e, "passar");
    if (v === "desistir" || v === "fold" || v === "largar") return jogar(e, "desistir");
    if (v === "tudo" || v === "allin") return jogar(e, "tudo");
    if (v === "apostar" || v === "aposta" || v === "aumentar" || v === "raise" || v === "subir") { var n = Number((p.slice(1).join(" ").match(/\d+/) || [""])[0]); return n ? jogar(e, "apostar", n) : { msg: "Quanto? Exemplo: apostar 40.", erro: true }; }
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, novo: novo, avaliar5: avaliar5, melhor: melhor, comparar: comparar, equidade: equidade, descreverMao: descreverMao, iniciarMao: iniciarMao, jogar: jogar, comando: comando, decidirCPU: decidirCPU, aplicar: aplicar, seguir: seguir, cegas: cegas, pote: pote, nome: nome };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + ": " + n.fichas + " fichas" + (k === "facil" ? ", adversário fácil, dicas à vontade" : k === "normal" ? ", adversário médio, 5 dicas" : ", adversário forte, sem dicas") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (continuar, pagar, passar, apostar 40, tudo, desistir, mao, fichas, tabela, dica, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var valorCampo = H.el("input", { id: "valor", type: "number", min: "1", inputmode: "numeric" });
  var apBtn = H.el("button", { type: "button", texto: "Apostar este valor" });
  var botoes = H.el("div", { role: "group", "aria-label": "Jogadas" }, [["Continuar", "continuar"], ["Pagar", "pagar"], ["Passar", "passar"], ["Desistir", "desistir"], ["Tudo", "tudo"], ["Ler a mão e a mesa", "mao"], ["Ler as fichas", "fichas"], ["Tabela das mãos", "tabela"], ["Dica", "dica"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { falar(comando(e, x[1]).msg, x[1]); }); return b;
  }));
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, H.som ? H.som.botao() : H.el("span"), botoes, H.el("label", { "for": "valor", texto: "Valor total da aposta nesta rodada" }), valorCampo, apBtn, form].forEach(function (x) { jogo.appendChild(x); });
  function falar(m, cmd) { var c = H.som && H.som.cue(m, cmd); if (c) H.som.anunciar(c, m); else H.anunciar(m); campo.disabled = !!e.fim; }
  apBtn.addEventListener("click", function () { falar(comando(e, "apostar " + (valorCampo.value || "x")).msg, "apostar " + (valorCampo.value || "x")); });
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var cmd = campo.value, r = comando(e, cmd); campo.value = ""; falar(r.msg, cmd); if (!e.fim) campo.focus(); });
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo jogo, nível " + e.nome + ": cada um começa com " + e.fichas[0] + " fichas virtuais, um contra um contra o computador. As cegas começam em 5 e 10 e dobram a cada 6 mãos. Diga continuar para dar as cartas. O comando ajuda lista tudo."); }
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
