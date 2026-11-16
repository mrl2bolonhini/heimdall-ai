// Campo minado de gramado: você conduz um cortador de grama pelo gramado, andando para norte, sul, leste e oeste.
// Cada casa cortada diz quantos formigueiros há nas casas ao redor. Corte todo o gramado sem pisar em um formigueiro.
// Diferente do campo minado comum, aqui você tem uma posição: o jogo é por movimento, sem linha e coluna para digitar.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", l: 6, c: 6, m: 5, dicas: 999, aviso: true },
    normal: { nome: "normal", l: 8, c: 8, m: 10, dicas: 3, aviso: false },
    dificil: { nome: "difícil", l: 10, c: 10, m: 20, dicas: 0, aviso: false }
  };
  var DIR = { norte: [-1, 0], sul: [1, 0], leste: [0, 1], oeste: [0, -1] };
  var ABREV = { n: "norte", s: "sul", l: "leste", o: "oeste", cima: "norte", baixo: "sul", direita: "leste", esquerda: "oeste", frente: "norte", tras: "sul", este: "leste" };

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function idx(e, r, c) { return (r - 1) * e.c + (c - 1); }
  function dentro(e, r, c) { return r >= 1 && r <= e.l && c >= 1 && c <= e.c; }
  function vizinhas(e, i, diag) {
    var r = Math.floor(i / e.c) + 1, c = (i % e.c) + 1, out = [], dr, dc;
    for (dr = -1; dr <= 1; dr++) for (dc = -1; dc <= 1; dc++) if ((dr || dc) && (diag !== false || !dr || !dc) && dentro(e, r + dr, c + dc)) out.push(idx(e, r + dr, c + dc));
    return out;
  }
  // Todas as casas sem formigueiro precisam ser alcançáveis andando em linha reta (sem diagonais).
  function conexo(e) {
    var seg = [], i; for (i = 0; i < e.cel.length; i++) if (!e.cel[i].mina) seg.push(i);
    var vis = {}, fila = [seg[0]]; vis[seg[0]] = true;
    while (fila.length) { var j = fila.shift(); vizinhas(e, j, false).forEach(function (k) { if (!e.cel[k].mina && !vis[k]) { vis[k] = true; fila.push(k); } }); }
    return Object.keys(vis).length === seg.length;
  }
  function novo(nivel, rnd) {
    var r = rnd || sorteio, n = NIVEIS[nivel] || NIVEIS.facil, k = NIVEIS[nivel] ? nivel : "facil", e, i, t;
    for (t = 0; t < 300; t++) {
      e = { nivel: k, nome: n.nome, l: n.l, c: n.c, m: n.m, cel: [], pos: 0, fim: null, cortadas: 0, passos: 0, dicas: n.dicas, marcadas: 0 };
      for (i = 0; i < n.l * n.c; i++) e.cel.push({ mina: false, cortada: false, marcada: false, n: 0 });
      var livres = [], proib = [0].concat(vizinhas(e, 0));
      for (i = 0; i < e.cel.length; i++) if (proib.indexOf(i) < 0) livres.push(i);
      for (i = 0; i < n.m; i++) { var q = r(livres.length); e.cel[livres[q]].mina = true; livres.splice(q, 1); }
      if (conexo(e)) break;
    }
    for (i = 0; i < e.cel.length; i++) e.cel[i].n = vizinhas(e, i).filter(function (j) { return e.cel[j].mina; }).length;
    e.cel[0].cortada = true; e.cortadas = 1;
    return e;
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function faltam(e) { return e.l * e.c - e.m - e.cortadas; }
  function rc(e, i) { return [Math.floor(i / e.c) + 1, (i % e.c) + 1]; }
  function ao(n) { return n === 0 ? "nenhum formigueiro ao redor" : plural(n, "formigueiro", "formigueiros") + " ao redor"; }
  function onde(e) {
    var p = rc(e, e.pos);
    return "Você está na linha " + p[0] + ", coluna " + p[1] + " de um gramado de " + e.l + " por " + e.c + ", com " + ao(e.cel[e.pos].n) + ".";
  }
  function vizinhaDir(e, d) {
    var p = rc(e, e.pos), v = DIR[d]; var r = p[0] + v[0], c = p[1] + v[1];
    return dentro(e, r, c) ? idx(e, r, c) : -1;
  }
  function checarVitoria(e, msg) {
    if (faltam(e) === 0) { e.fim = "ganhou"; return { msg: msg + " Você cortou todo o gramado. Ganhou, em " + plural(e.passos, "passo", "passos") + "!", fim: "ganhou" }; }
    return { msg: msg + " Faltam " + plural(faltam(e), "casa", "casas") + " para cortar." };
  }
  // Um passo. Devolve {msg, parar} (parar = a caminhada de vários passos deve parar aqui).
  function passo(e, d) {
    var j = vizinhaDir(e, d), niv = NIVEIS[e.nivel];
    if (j < 0) return { msg: "Fim do gramado: não há casa ao " + d + ".", parar: true, erro: true };
    var c = e.cel[j];
    if (c.marcada) return { msg: "Há uma bandeira na casa ao " + d + ". Use marcar " + d + " para tirá-la, se quiser passar.", parar: true, erro: true };
    if (c.mina) {
      if (niv.aviso) { c.marcada = true; e.marcadas++; return { msg: "O sensor apitou: há um formigueiro na casa ao " + d + ". Eu o marquei com bandeira e você não se mexeu.", parar: true, erro: true }; }
      e.fim = "perdeu";
      return { msg: "Crash! O cortador caiu num formigueiro ao " + d + ". Fim de jogo: você cortou " + plural(e.cortadas, "casa", "casas") + " de " + (e.l * e.c - e.m) + ".", parar: true, fim: "perdeu" };
    }
    e.pos = j; e.passos++;
    if (c.cortada) return { msg: "Você voltou a uma casa já cortada, com " + ao(c.n) + ".", parar: false, nova: false };
    c.cortada = true; e.cortadas++;
    return { msg: "Cortou, com " + ao(c.n) + ".", parar: c.n > 0, nova: true };
  }
  function andar(e, d, vezes) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    var n = Math.max(1, Math.min(vezes || 1, 20)), partes = [], k, res = null;
    for (k = 0; k < n; k++) {
      res = passo(e, d); partes.push(res.msg);
      if (res.fim || res.parar || e.fim) break;
      if (k < n - 1) partes[partes.length - 1] = partes[partes.length - 1].replace(/ com .*$/, "").replace(/\.$/, "") + ".";
    }
    var msg = partes.join(" ");
    if (res && res.fim === "perdeu") return { msg: msg, fim: "perdeu" };
    if (res && res.erro) return { msg: msg, erro: true };
    if (e.fim) return { msg: msg };
    var comp = checarVitoria(e, msg); return comp;
  }
  function marcar(e, d) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    var j = vizinhaDir(e, d); if (j < 0) return { msg: "Não há casa ao " + d + "." };
    var c = e.cel[j]; if (c.cortada) return { msg: "A casa ao " + d + " já foi cortada." };
    c.marcada = !c.marcada; e.marcadas += c.marcada ? 1 : -1;
    return { msg: (c.marcada ? "Bandeira posta" : "Bandeira tirada") + " na casa ao " + d + ". Bandeiras no gramado: " + e.marcadas + " de " + e.m + " formigueiros." };
  }
  // Vê o que está ao redor de você (as quatro direções): cortada, fechada, bandeira ou borda.
  function sensor(e) {
    var out = [];
    ["norte", "sul", "leste", "oeste"].forEach(function (d) {
      var j = vizinhaDir(e, d); var s;
      if (j < 0) s = "borda"; else if (e.cel[j].marcada) s = "bandeira"; else if (e.cel[j].cortada) s = "já cortada, com " + ao(e.cel[j].n); else s = "ainda alta";
      out.push(d + ": " + s);
    });
    return onde(e) + " " + out.join("; ") + ".";
  }
  // Mapa por linhas: cada casa é a letra do estado. "você" marca onde está.
  function simb(e, i) {
    var c = e.cel[i];
    if (e.fim && c.mina) return "formigueiro";
    if (i === e.pos) return "você";
    if (c.marcada) return "bandeira";
    if (!c.cortada) return "alta";
    return c.n === 0 ? "vazia" : String(c.n);
  }
  function mapa(e) {
    var out = [], r, c;
    for (r = 1; r <= e.l; r++) {
      var t = []; for (c = 1; c <= e.c; c++) t.push(simb(e, idx(e, r, c)));
      var runs = [], a = 0, k;
      for (k = 1; k <= t.length; k++) if (k === t.length || t[k] !== t[a]) { runs.push(k - a === 1 ? "coluna " + (a + 1) + ": " + t[a] : "colunas " + (a + 1) + " a " + k + ": " + t[a]); a = k; }
      out.push("Linha " + r + ". " + runs.join("; ") + ".");
    }
    return out.join(" ");
  }
  // Dedução simples: acha casas certamente seguras ou certamente com formigueiro, usando só os números das casas cortadas.
  function deduzir(e) {
    var sabe = {}, mudou = true, i;
    while (mudou) {
      mudou = false;
      for (i = 0; i < e.cel.length; i++) {
        if (!e.cel[i].cortada) continue;
        var fech = vizinhas(e, i).filter(function (j) { return !e.cel[j].cortada; });
        var minas = fech.filter(function (j) { return sabe[j] === "mina"; }).length;
        var desc = fech.filter(function (j) { return sabe[j] === undefined; });
        if (!desc.length) continue;
        if (minas === e.cel[i].n) { desc.forEach(function (j) { sabe[j] = "segura"; }); mudou = true; }
        else if (minas + desc.length === e.cel[i].n) { desc.forEach(function (j) { sabe[j] = "mina"; }); mudou = true; }
      }
    }
    return sabe;
  }
  function dica(e) {
    if (e.fim) return { msg: "A partida terminou." };
    if (e.dicas <= 0) return { msg: NIVEIS[e.nivel].dicas === 0 ? "No nível difícil não há dicas." : "As dicas acabaram." };
    var sabe = deduzir(e), seg = [], min = [], i;
    for (i = 0; i < e.cel.length; i++) { if (sabe[i] === "segura" && !e.cel[i].cortada) seg.push(i); if (sabe[i] === "mina") min.push(i); }
    var qual = seg.length ? seg[0] : -1;
    if (NIVEIS[e.nivel].dicas < 100) e.dicas--;
    var resto = NIVEIS[e.nivel].dicas < 100 ? " Dicas restantes: " + e.dicas + "." : "";
    if (qual >= 0) { var p = rc(e, qual); return { msg: "Dica: a casa da linha " + p[0] + ", coluna " + p[1] + " é segura, pelos números já descobertos." + resto }; }
    if (min.length) { var q = rc(e, min[0]); return { msg: "Dica: há um formigueiro na linha " + q[0] + ", coluna " + q[1] + ". Evite essa casa." + resto }; }
    return { msg: "Dica: pelos números descobertos não dá para ter certeza de nada. Escolha uma casa com cuidado, perto das que têm menos formigueiros ao redor." + resto };
  }
  function resumo(e) {
    var s = "Nível " + e.nome + ", gramado de " + e.l + " por " + e.c + " com " + e.m + " formigueiros. Faltam " + plural(faltam(e), "casa", "casas") + " para cortar. Passos: " + e.passos + ". Bandeiras: " + e.marcadas + ".";
    if (e.fim === "ganhou") s += " Você ganhou."; if (e.fim === "perdeu") s += " Você perdeu.";
    return s;
  }
  function ajuda() {
    return "Comandos: norte, sul, leste, oeste (ou n, s, l, o), e com um número anda várias casas, por exemplo leste 3; a caminhada para quando uma casa tem formigueiro ao redor. marcar DIREÇÃO põe ou tira bandeira na casa ao lado; sensor, para ver as quatro direções; onde; mapa, para ler tudo; dica; resumo; ajuda.";
  }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: leste, ou ajuda." };
    if (v === "ir" || v === "andar" || v === "cortar" || v === "mover") { p.shift(); v = p[0] || ""; }
    var d = DIR[v] ? v : ABREV[v];
    if (d) { var nn = Number((p[1] || "").replace(/\D/g, "")) || 1; return andar(e, d, nn); }
    if (v === "marcar" || v === "bandeira" || v === "m") { var dm = ABREV[p[1]] || p[1]; return DIR[dm] ? marcar(e, dm) : { msg: "Marcar qual lado? Exemplo: marcar leste." }; }
    if (v === "sensor" || v === "ver" || v === "olhar") return { msg: sensor(e) };
    if (v === "onde" || v === "posicao") return { msg: onde(e) };
    if (v === "mapa" || v === "tudo" || v === "tabuleiro") return { msg: mapa(e) };
    if (v === "dica") return dica(e);
    if (v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "ajuda") return { msg: ajuda() };
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, novo: novo, andar: andar, marcar: marcar, sensor: sensor, mapa: mapa, dica: dica, deduzir: deduzir, resumo: resumo, comando: comando, faltam: faltam, vizinhas: vizinhas, conexo: conexo, onde: onde };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { return H.el("option", { value: k, texto: NIVEIS[k].nome.charAt(0).toUpperCase() + NIVEIS[k].nome.slice(1) + ": " + NIVEIS[k].l + " por " + NIVEIS[k].c + ", " + NIVEIS[k].m + " formigueiros" }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (norte, sul, leste, oeste, leste 3, marcar leste, sensor, mapa, dica, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var botoes = H.el("div", { role: "group", "aria-label": "Mover o cortador" }, ["norte", "sul", "leste", "oeste"].map(function (d) {
    var b = H.el("button", { type: "button", texto: d.charAt(0).toUpperCase() + d.slice(1) }); b.addEventListener("click", function () { falar(comando(e, d).msg); }); return b;
  }));
  var extras = H.el("div", { role: "group", "aria-label": "Consultas" }, [["Onde estou", "onde"], ["Sensor", "sensor"], ["Ler o mapa", "mapa"], ["Dica", "dica"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { falar(comando(e, x[1]).msg); }); return b;
  }));
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, form, botoes, extras].forEach(function (x) { jogo.appendChild(x); });
  function falar(m) { H.anunciar(m); campo.disabled = !!e.fim; }
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo jogo, nível " + e.nome + ": gramado de " + e.l + " por " + e.c + " com " + e.m + " formigueiros. Você está no canto da linha 1, coluna 1, que já está cortada. O gramado fica ao sul e a leste. Ande com leste, sul e os outros comandos; ajuda lista tudo."); }
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var r = comando(e, campo.value); campo.value = ""; falar(r.msg); if (!e.fim) campo.focus(); });
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
