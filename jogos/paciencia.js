// Paciência (Klondike) falada. Você move cartas por comandos de texto e ouve o resultado; a mesa é lida por coluna.
// Cartas: valor (A, 2 a 10, J, Q, K) e naipe (C copas, O ouros, P paus, E espadas). Exemplos: 7C, 10O, QE, AP. Também vale "7 de copas".
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", compra: 1, dicas: 999, desfaz: true },
    normal: { nome: "normal", compra: 1, dicas: 3, desfaz: true },
    dificil: { nome: "difícil", compra: 3, dicas: 0, desfaz: false }
  };
  var NAIPES = ["c", "o", "p", "e"], NOME_NAIPE = { c: "copas", o: "ouros", p: "paus", e: "espadas" }, VERMELHO = { c: true, o: true, p: false, e: false };
  var NOME_VALOR = [null, "Ás", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Valete", "Dama", "Rei"], LETRA_VALOR = [null, "a", "2", "3", "4", "5", "6", "7", "8", "9", "10", "j", "q", "k"];

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function nome(c) { return NOME_VALOR[c.r] + " de " + NOME_NAIPE[c.s]; }
  function cod(c) { return LETRA_VALOR[c.r].toUpperCase() + c.s.toUpperCase(); }
  function novo(nivel, rnd) {
    var r = rnd || sorteio, k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k], baralho = [], i, j;
    NAIPES.forEach(function (s) { for (i = 1; i <= 13; i++) baralho.push({ r: i, s: s }); });
    for (i = baralho.length - 1; i > 0; i--) { j = r(i + 1); var t = baralho[i]; baralho[i] = baralho[j]; baralho[j] = t; }
    var col = [];
    for (i = 1; i <= 7; i++) { var cartas = baralho.splice(0, i); col.push({ down: cartas.slice(0, i - 1), up: [cartas[i - 1]] }); }
    return { nivel: k, nome: n.nome, compra: n.compra, dicas: n.dicas, col: col, monte: baralho, desc: [], base: { c: 0, o: 0, p: 0, e: 0 }, movs: 0, fim: null, hist: [], recicladas: 0 };
  }
  function topoCol(e, i) { var u = e.col[i].up; return u.length ? u[u.length - 1] : null; }
  function virar(e, i) { var c = e.col[i]; if (!c.up.length && c.down.length) { var x = c.down.pop(); c.up.push(x); return x; } return null; }
  function cabe(c, dest) { // pode colocar a carta c sobre a coluna dest?
    var t = dest.up.length ? dest.up[dest.up.length - 1] : null;
    if (!t) return c.r === 13 && !dest.down.length;
    return t.r === c.r + 1 && VERMELHO[t.s] !== VERMELHO[c.s];
  }
  function vencer(e) { return NAIPES.every(function (s) { return e.base[s] === 13; }); }
  function guardar(e) { var h = e.hist; e.hist = []; var s = JSON.stringify(e); e.hist = h; h.push(s); if (h.length > 300) h.shift(); }

  // Acha onde está a carta: descarte (só o topo), coluna (aberta) ou base (só o topo).
  function achar(e, c) {
    var t = e.desc.length ? e.desc[e.desc.length - 1] : null;
    if (t && t.r === c.r && t.s === c.s) return { onde: "descarte" };
    for (var i = 0; i < 7; i++) { var u = e.col[i].up; for (var k = 0; k < u.length; k++) if (u[k].r === c.r && u[k].s === c.s) return { onde: "coluna", i: i, k: k }; }
    if (e.base[c.s] === c.r) return { onde: "base" };
    return null;
  }
  function paraBase(e, orig) { // orig: {onde, i}
    var c = orig.onde === "descarte" ? e.desc[e.desc.length - 1] : topoCol(e, orig.i);
    if (!c) return { msg: "Não há carta aí.", erro: true };
    if (e.base[c.s] !== c.r - 1) return { msg: "O " + nome(c) + " ainda não pode subir para a base: a base de " + NOME_NAIPE[c.s] + " " + (e.base[c.s] ? "está no " + NOME_VALOR[e.base[c.s]] : "está vazia e pede o Ás") + "." , erro: true };
    guardar(e);
    if (orig.onde === "descarte") e.desc.pop(); else e.col[orig.i].up.pop();
    e.base[c.s]++; e.movs++;
    var extra = orig.onde === "coluna" ? virar(e, orig.i) : null, msg = nome(c) + " subiu para a base de " + NOME_NAIPE[c.s] + "." + (extra ? " Virou " + nome(extra) + " na coluna " + (orig.i + 1) + "." : "");
    if (vencer(e)) { e.fim = "ganhou"; msg += " As quatro bases estão completas. Você ganhou, em " + e.movs + " jogadas!"; }
    return { msg: msg };
  }
  function paraColuna(e, c, ach, dest) {
    if (dest < 0 || dest > 6) return { msg: "A mesa tem as colunas de 1 a 7.", erro: true };
    var alvo = e.col[dest];
    if (ach.onde === "coluna" && ach.i === dest) return { msg: "Essa carta já está na coluna " + (dest + 1) + ".", erro: true };
    if (!cabe(c, alvo)) {
      var t = alvo.up.length ? alvo.up[alvo.up.length - 1] : null;
      return { msg: t ? "O " + nome(c) + " não cabe sobre o " + nome(t) + ": é preciso uma carta de valor imediatamente menor e de cor diferente." : "A coluna " + (dest + 1) + " está vazia e só aceita um Rei.", erro: true };
    }
    guardar(e);
    var mov, extra = null;
    if (ach.onde === "descarte") mov = [e.desc.pop()];
    else if (ach.onde === "base") { e.base[c.s]--; mov = [c]; }
    else { mov = e.col[ach.i].up.splice(ach.k); extra = virar(e, ach.i); }
    mov.forEach(function (x) { alvo.up.push(x); }); e.movs++;
    return { msg: (mov.length > 1 ? mov.length + " cartas, de " + nome(mov[0]) + " até " + nome(mov[mov.length - 1]) + ", foram para a coluna " + (dest + 1) + "." : nome(c) + " foi para a coluna " + (dest + 1) + ".") + (extra ? " Virou " + nome(extra) + " na coluna " + (ach.i + 1) + "." : "") };
  }
  function comprar(e) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    if (!e.monte.length) {
      if (!e.desc.length) return { msg: "O monte e o descarte estão vazios.", erro: true };
      guardar(e); e.monte = e.desc.reverse(); e.desc = []; e.recicladas++; e.movs++;
      return { msg: "O monte acabou, então o descarte voltou para o monte, " + e.monte.length + " cartas. Compre de novo." };
    }
    guardar(e);
    var n = Math.min(e.compra, e.monte.length), v = [];
    for (var i = 0; i < n; i++) { var c = e.monte.shift(); e.desc.push(c); v.push(c); }
    e.movs++;
    return { msg: (n > 1 ? "Você virou " + n + " cartas; a de cima do descarte é " : "Você virou ") + nome(v[v.length - 1]) + ". No monte restam " + e.monte.length + "." };
  }

  // Leitura
  function lerCol(e, i) {
    var c = e.col[i], b = c.down.length;
    if (!c.up.length && !b) return "Coluna " + (i + 1) + ": vazia.";
    return "Coluna " + (i + 1) + ": " + (b ? b + (b === 1 ? " carta virada para baixo; " : " cartas viradas para baixo; ") : "") + "abertas, da primeira à última: " + c.up.map(nome).join(", ") + ". A do topo é " + nome(c.up[c.up.length - 1]) + ".";
  }
  function lerDesc(e) { return e.desc.length ? "Descarte: " + nome(e.desc[e.desc.length - 1]) + " em cima, com " + e.desc.length + (e.desc.length === 1 ? " carta" : " cartas") + ". Monte: " + e.monte.length + "." : "O descarte está vazio. Monte: " + e.monte.length + "."; }
  function lerBases(e) { return "Bases: " + NAIPES.map(function (s) { return NOME_NAIPE[s] + " " + (e.base[s] ? "até o " + NOME_VALOR[e.base[s]] : "vazia"); }).join("; ") + "."; }
  function lerMesa(e) { var o = []; for (var i = 0; i < 7; i++) o.push(lerCol(e, i)); return o.join(" ") + " " + lerDesc(e) + " " + lerBases(e); }
  function resumo(e) { var n = e.base.c + e.base.o + e.base.p + e.base.e; return "Nível " + e.nome + " (compra " + e.compra + "). " + n + " de 52 cartas nas bases. Jogadas: " + e.movs + ". Monte: " + e.monte.length + ", descarte: " + e.desc.length + "." + (e.fim ? " Você ganhou." : ""); }

  // Jogadas possíveis, para dicas e testes.
  function jogadas(e) {
    var out = [], i, k, j, c;
    function baseOk(c) { return e.base[c.s] === c.r - 1; }
    var d = e.desc.length ? e.desc[e.desc.length - 1] : null;
    if (d && baseOk(d)) out.push({ tipo: "base", carta: d, de: "descarte", prio: 1 });
    for (i = 0; i < 7; i++) { c = topoCol(e, i); if (c && baseOk(c)) out.push({ tipo: "base", carta: c, de: "coluna " + (i + 1), prio: e.col[i].up.length === 1 && e.col[i].down.length ? 0 : 1 }); }
    for (i = 0; i < 7; i++) for (k = 0; k < e.col[i].up.length; k++) {
      c = e.col[i].up[k];
      for (j = 0; j < 7; j++) {
        if (j === i || !cabe(c, e.col[j])) continue;
        // só vale a pena mover quando vira uma carta fechada, esvazia uma coluna ou libera uma carta que sobe para a base
        var revela = k === 0 && e.col[i].down.length > 0, libera = k > 0 && baseOk(e.col[i].up[k - 1]), esvazia = k === 0 && !e.col[i].down.length && c.r !== 13;
        if (!revela && !libera && !esvazia) continue;
        out.push({ tipo: "mesa", carta: c, de: "coluna " + (i + 1), para: j + 1, prio: revela ? 0 : libera ? 1 : 4 });
      }
    }
    if (d) for (j = 0; j < 7; j++) if (cabe(d, e.col[j])) out.push({ tipo: "mesa", carta: d, de: "descarte", para: j + 1, prio: 2 });
    if (e.monte.length) out.push({ tipo: "comprar", prio: 5 }); else if (e.desc.length) out.push({ tipo: "reciclar", prio: 6 });
    return out.sort(function (a, b) { return a.prio - b.prio; });
  }
  function dica(e) {
    if (e.fim) return { msg: "A partida terminou." };
    if (e.dicas <= 0) return { msg: NIVEIS[e.nivel].dicas === 0 ? "No nível difícil não há dicas." : "As dicas acabaram." };
    var js = jogadas(e), m = js[0];
    if (NIVEIS[e.nivel].dicas < 100) e.dicas--;
    var resto = NIVEIS[e.nivel].dicas < 100 ? " Dicas restantes: " + e.dicas + "." : "";
    if (!m) return { msg: "Dica: não vejo mais jogadas. A partida parece travada; você pode desfazer ou começar outra." + resto };
    var t = m.tipo === "base" ? "Suba o " + nome(m.carta) + " (" + m.de + ") para a base: comando subir " + cod(m.carta) + "." : m.tipo === "mesa" ? "Mova " + nome(m.carta) + " (" + m.de + ") para a coluna " + m.para + ": comando mover " + cod(m.carta) + " para " + m.para + "." : m.tipo === "comprar" ? "Não há jogada melhor: compre uma carta do monte." : "Recicle o descarte: comando comprar.";
    return { msg: "Dica: " + t + resto };
  }
  function desfazer(e) {
    if (!NIVEIS[e.nivel].desfaz) return { msg: "No nível difícil não dá para desfazer.", erro: true };
    if (!e.hist.length) return { msg: "Não há o que desfazer.", erro: true };
    var h = e.hist, s = JSON.parse(h.pop()), dicas = e.dicas; Object.keys(e).forEach(function (k) { delete e[k]; }); Object.keys(s).forEach(function (k) { e[k] = s[k]; });
    e.hist = h; e.dicas = dicas;
    return { msg: "Desfeito. " + resumo(e) };
  }
  function ajuda() {
    return "Comandos: comprar; mover CARTA para COLUNA (por exemplo, mover 7C para 4, que leva também as cartas abertas sobre ela); mover descarte para COLUNA; subir CARTA, subir descarte ou subir coluna N, para mandar à base; mesa, para ler tudo; coluna N; descarte; bases; dica; desfazer; resumo. Cartas: valor A, 2 a 10, J, Q ou K e o naipe C copas, O ouros, P paus ou E espadas, como QE ou 10O. Também vale escrever 7 de copas.";
  }

  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  var NAIPE_PAL = { copas: "c", ouros: "o", paus: "p", espadas: "e" }, VAL_PAL = { as: 1, ases: 1, valete: 11, dama: 12, rainha: 12, rei: 13 };
  // Lê uma carta no início de uma lista de palavras; devolve {c, usadas}.
  function lerCarta(p) {
    var a = p[0] || "", m = a.match(/^(10|[2-9]|a|j|q|k)([cope])$/);
    if (m) return { c: { r: LETRA_VALOR.indexOf(m[1]), s: m[2] }, usadas: 1 };
    var v = /^(10|[2-9])$/.test(a) ? Number(a) : VAL_PAL[a] || (a === "a" ? 1 : a === "j" ? 11 : a === "q" ? 12 : a === "k" ? 13 : 0), k = 1;
    if (!v) return null;
    if (p[k] === "de") k++;
    var s = NAIPE_PAL[p[k]] || (/^[cope]$/.test(p[k] || "") ? p[k] : null);
    return s ? { c: { r: v, s: s }, usadas: k + 1 } : null;
  }
  function origem(e, p) { // devolve {orig, carta, usadas} ou {msg}
    var a = p[0];
    if (a === "descarte" || a === "d") { if (!e.desc.length) return { msg: "O descarte está vazio." }; return { orig: { onde: "descarte" }, carta: e.desc[e.desc.length - 1], usadas: 1 }; }
    if (a === "coluna" || a === "c" && /^\d$/.test(p[1] || "")) { var n = Number(p[1]); if (!(n >= 1 && n <= 7)) return { msg: "A mesa tem as colunas de 1 a 7." }; var t = topoCol(e, n - 1); if (!t) return { msg: "A coluna " + n + " está vazia." }; return { orig: { onde: "coluna", i: n - 1, k: e.col[n - 1].up.length - 1 }, carta: t, usadas: 2 }; }
    var lc = lerCarta(p); if (!lc) return { msg: "Não entendi a carta. Exemplos: 7C, QE, 10O ou 7 de copas." };
    var ach = achar(e, lc.c); if (!ach) return { msg: "Não achei o " + nome(lc.c) + " aberto na mesa, no topo do descarte ou no topo de uma base." };
    return { orig: ach, carta: lc.c, usadas: lc.usadas };
  }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: mesa, comprar ou ajuda." };
    if (v === "ajuda") return { msg: ajuda() };
    if (v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "mesa" || v === "tudo" || v === "ler") return { msg: lerMesa(e) };
    if (v === "descarte" && p.length === 1) return { msg: lerDesc(e) };
    if ((v === "coluna" || v === "col") && p.length === 2) { var n = Number(p[1]); return n >= 1 && n <= 7 ? { msg: lerCol(e, n - 1) } : { msg: "A mesa tem as colunas de 1 a 7." }; }
    if (v === "bases" || v === "base" && p.length === 1) return { msg: lerBases(e) };
    if (v === "dica") return dica(e);
    if (v === "desfazer" || v === "voltar") return desfazer(e);
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    if (v === "comprar" || v === "compra" || v === "monte" || v === "virar") return comprar(e);
    if (v === "subir" || v === "base") {
      var o = origem(e, p.slice(1)); if (o.msg) return { msg: o.msg, erro: true };
      if (o.orig.onde === "base") return { msg: "Essa carta já está na base.", erro: true };
      if (o.orig.onde === "coluna" && o.orig.k !== e.col[o.orig.i].up.length - 1) return { msg: "O " + nome(o.carta) + " tem cartas em cima. Só a carta do topo da coluna pode subir.", erro: true };
      return paraBase(e, o.orig);
    }
    if (v === "mover" || v === "m" || v === "passar" || v === "levar" || v === "ir") {
      var s = origem(e, p.slice(1)); if (s.msg) return { msg: s.msg, erro: true };
      var resto = p.slice(1 + s.usadas); if (resto[0] === "para" || resto[0] === "pra" || resto[0] === "na" || resto[0] === "a") resto.shift(); if (resto[0] === "coluna") resto.shift();
      if (resto[0] === "base") { if (s.orig.onde === "base") return { msg: "Essa carta já está na base.", erro: true }; if (s.orig.onde === "coluna" && s.orig.k !== e.col[s.orig.i].up.length - 1) return { msg: "O " + nome(s.carta) + " tem cartas em cima. Só a carta do topo da coluna pode subir.", erro: true }; return paraBase(e, s.orig); }
      var d = Number(resto[0]); if (!(d >= 1 && d <= 7)) return { msg: "Para onde? Diga a coluna de 1 a 7 ou base. Exemplo: mover " + cod(s.carta) + " para 3.", erro: true };
      return paraColuna(e, s.carta, s.orig, d - 1);
    }
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, novo: novo, comando: comando, jogadas: jogadas, dica: dica, comprar: comprar, nome: nome, cod: cod, lerMesa: lerMesa, vencer: vencer, achar: achar, cabe: cabe };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + ": compra " + n.compra + (k === "facil" ? ", dicas à vontade" : k === "normal" ? ", 3 dicas" : ", sem dicas e sem desfazer") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (comprar, mover 7C para 4, subir descarte, mesa, dica, desfazer, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var atalhos = H.el("div", { role: "group", "aria-label": "Atalhos" }, [["Comprar", "comprar"], ["Ler a mesa", "mesa"], ["Ler o descarte", "descarte"], ["Ler as bases", "bases"], ["Dica", "dica"], ["Desfazer", "desfazer"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { falar(comando(e, x[1]).msg); }); return b;
  }));
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, form, atalhos].forEach(function (x) { jogo.appendChild(x); });
  function falar(m) { H.anunciar(m); campo.disabled = !!e.fim; }
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var r = comando(e, campo.value); campo.value = ""; falar(r.msg); if (!e.fim) campo.focus(); });
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo jogo, nível " + e.nome + ", compra " + e.compra + ". Sete colunas, com 1 a 7 cartas cada; só a de cima de cada coluna está aberta. " + lerMesa(e)); }
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
