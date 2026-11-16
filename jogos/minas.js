// Campo minado para leitor de tela. Linhas e colunas são numeradas a partir de 1.
// Dois jeitos de jogar: comandos de texto ("abrir 3 4", "marcar 3 4", "ler 3", "tabuleiro") ou a grade de botões.
// A primeira casa aberta nunca é mina (e, se couber, nem as vizinhas), então a primeira jogada sempre abre uma área.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", l: 6, c: 6, m: 5 },
    medio: { nome: "médio", l: 9, c: 9, m: 10 },
    dificil: { nome: "difícil", l: 12, c: 12, m: 25 }
  };

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function novo(nivel) {
    var n = NIVEIS[nivel] || NIVEIS.facil, cel = [], i;
    for (i = 0; i < n.l * n.c; i++) cel.push({ mina: false, aberta: false, marcada: false, n: 0 });
    return { nivel: NIVEIS[nivel] ? nivel : "facil", nome: n.nome, l: n.l, c: n.c, m: n.m, cel: cel, iniciado: false, fim: null, abertas: 0, marcadas: 0 };
  }
  function idx(e, r, c) { return (r - 1) * e.c + (c - 1); }
  function dentro(e, r, c) { return r >= 1 && r <= e.l && c >= 1 && c <= e.c; }
  function vizinhas(e, i) {
    var r = Math.floor(i / e.c) + 1, c = (i % e.c) + 1, out = [], dr, dc;
    for (dr = -1; dr <= 1; dr++) for (dc = -1; dc <= 1; dc++) if ((dr || dc) && dentro(e, r + dr, c + dc)) out.push(idx(e, r + dr, c + dc));
    return out;
  }
  // Coloca as minas depois da primeira jogada. `rnd(n)` existe para os testes.
  function colocar(e, i0, rnd) {
    var r = rnd || sorteio, livres = [], i, proibidas = [i0].concat(vizinhas(e, i0));
    for (i = 0; i < e.cel.length; i++) if (proibidas.indexOf(i) < 0) livres.push(i);
    if (livres.length < e.m) { livres = []; for (i = 0; i < e.cel.length; i++) if (i !== i0) livres.push(i); }
    for (i = 0; i < e.m; i++) { var k = r(livres.length); e.cel[livres[k]].mina = true; livres.splice(k, 1); }
    for (i = 0; i < e.cel.length; i++) e.cel[i].n = vizinhas(e, i).filter(function (j) { return e.cel[j].mina; }).length;
    e.iniciado = true;
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function seguras(e) { return e.l * e.c - e.m - e.abertas; }
  function pos(r, c) { return "linha " + r + ", coluna " + c; }
  function minasAo(n) { return n === 0 ? "nenhuma mina ao redor" : plural(n, "mina", "minas") + " ao redor"; }

  function abrir(e, r, c, rnd) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    if (!dentro(e, r, c)) return { msg: "Essa casa não existe. O tabuleiro tem " + e.l + " linhas e " + e.c + " colunas." };
    var i = idx(e, r, c), cel = e.cel[i];
    if (cel.marcada) return { msg: "A casa da " + pos(r, c) + " está marcada com bandeira. Desmarque antes de abrir." };
    if (cel.aberta) return { msg: "A casa da " + pos(r, c) + " já está aberta: " + (cel.n ? minasAo(cel.n) : "vazia") + "." };
    if (!e.iniciado) colocar(e, i, rnd);
    if (cel.mina) {
      e.fim = "perdeu"; cel.aberta = true;
      return { msg: "Bum! Havia uma mina na " + pos(r, c) + ". Fim de jogo: você abriu " + plural(e.abertas, "casa segura", "casas seguras") + ".", fim: "perdeu", abertas: [i] };
    }
    var fila = [i], vistas = {}, abertasAgora = [];
    vistas[i] = true;
    while (fila.length) {
      var j = fila.shift(), cj = e.cel[j];
      if (cj.aberta || cj.marcada) continue;
      cj.aberta = true; e.abertas++; abertasAgora.push(j);
      if (cj.n === 0) vizinhas(e, j).forEach(function (k) { if (!vistas[k] && !e.cel[k].aberta && !e.cel[k].marcada) { vistas[k] = true; fila.push(k); } });
    }
    var msg;
    if (cel.n > 0) msg = pos(r, c).charAt(0).toUpperCase() + pos(r, c).slice(1) + ": " + minasAo(cel.n) + ".";
    else msg = pos(r, c).charAt(0).toUpperCase() + pos(r, c).slice(1) + ": " + minasAo(0) + ". Abriu uma área de " + plural(abertasAgora.length, "casa", "casas") + ".";
    if (seguras(e) === 0) {
      e.fim = "ganhou";
      return { msg: msg + " Você abriu todas as casas seguras. Ganhou!", fim: "ganhou", abertas: abertasAgora };
    }
    return { msg: msg + " Faltam " + plural(seguras(e), "casa segura", "casas seguras") + ".", abertas: abertasAgora };
  }
  function marcar(e, r, c) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    if (!dentro(e, r, c)) return { msg: "Essa casa não existe. O tabuleiro tem " + e.l + " linhas e " + e.c + " colunas." };
    var cel = e.cel[idx(e, r, c)];
    if (cel.aberta) return { msg: "A casa da " + pos(r, c) + " já está aberta e não pode ser marcada." };
    cel.marcada = !cel.marcada; e.marcadas += cel.marcada ? 1 : -1;
    return { msg: (cel.marcada ? "Marcou" : "Desmarcou") + " a " + pos(r, c) + ". Minas restantes pelas marcações: " + (e.m - e.marcadas) + "." };
  }

  // Como a casa é lida: fechada, marcada, vazia ou o número de minas ao redor.
  function simbolo(e, i) {
    var c = e.cel[i];
    if (e.fim && c.mina) return "mina";
    if (c.marcada) return "marcada";
    if (!c.aberta) return "fechada";
    return c.n === 0 ? "vazia" : String(c.n);
  }
  var PLURAL = { fechada: "fechadas", marcada: "marcadas", vazia: "vazias", mina: "minas" };
  function runs(tokens, rotulo) {
    var out = [], a = 0, k;
    for (k = 1; k <= tokens.length; k++) {
      if (k === tokens.length || tokens[k] !== tokens[a]) {
        var t = tokens[a];
        out.push(k - a === 1 ? rotulo + " " + (a + 1) + ": " + t : rotulo + "s " + (a + 1) + " a " + k + ": " + (PLURAL[t] || t));
        a = k;
      }
    }
    return out.join("; ");
  }
  function lerCasa(e, r, c) {
    if (!dentro(e, r, c)) return "Essa casa não existe. O tabuleiro tem " + e.l + " linhas e " + e.c + " colunas.";
    var s = simbolo(e, idx(e, r, c));
    return pos(r, c).charAt(0).toUpperCase() + pos(r, c).slice(1) + ": " + (/^\d$/.test(s) ? "aberta, " + minasAo(Number(s)) : s) + ".";
  }
  function lerLinha(e, r) {
    if (r < 1 || r > e.l) return "Essa linha não existe. Há " + e.l + " linhas.";
    var t = [], c; for (c = 1; c <= e.c; c++) t.push(simbolo(e, idx(e, r, c)));
    return "Linha " + r + ". " + runs(t, "coluna") + ".";
  }
  function lerColuna(e, c) {
    if (c < 1 || c > e.c) return "Essa coluna não existe. Há " + e.c + " colunas.";
    var t = [], r; for (r = 1; r <= e.l; r++) t.push(simbolo(e, idx(e, r, c)));
    return "Coluna " + c + ". " + runs(t, "linha") + ".";
  }
  function lerTudo(e) {
    var out = [], r; for (r = 1; r <= e.l; r++) out.push(lerLinha(e, r));
    return out.join(" ");
  }
  function resumo(e) {
    var s = "Nível " + e.nome + ", " + e.l + " por " + e.c + ", com " + e.m + " minas. Marcadas: " + e.marcadas + ". Minas restantes pelas marcações: " + (e.m - e.marcadas) + ". Casas seguras que faltam: " + seguras(e) + ".";
    if (e.fim === "ganhou") s += " Você ganhou.";
    if (e.fim === "perdeu") s += " Você perdeu.";
    return s;
  }
  function ajuda() {
    return "Comandos: abrir LINHA COLUNA (ou só os dois números); marcar LINHA COLUNA, para colocar ou tirar a bandeira; ler LINHA, ler coluna N ou ler LINHA COLUNA; tabuleiro, para ler tudo; resumo. Linhas e colunas começam em 1. O número de uma casa aberta diz quantas minas há nas oito casas ao redor.";
  }

  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  // Interpreta um comando de texto e devolve {msg, ...}.
  function comando(e, texto, rnd) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "", nums = (t.match(/\d+/g) || []).map(Number);
    if (!t) return { msg: "Digite um comando. Experimente: abrir 1 1, ou ajuda." };
    if (v === "ajuda" || v === "h") return { msg: ajuda() };
    if (v === "resumo" || v === "status" || v === "placar") return { msg: resumo(e) };
    if (v === "tabuleiro" || v === "tudo") return { msg: lerTudo(e) };
    if (v === "ler" || v === "l" || v === "linha" || v === "coluna") {
      var coluna = v === "coluna" || p[1] === "coluna";
      if (nums.length >= 2 && !coluna) return { msg: lerCasa(e, nums[0], nums[1]) };
      if (nums.length >= 1) return { msg: coluna ? lerColuna(e, nums[0]) : lerLinha(e, nums[0]) };
      return { msg: "Ler qual linha ou coluna? Exemplo: ler 3, ler coluna 2 ou ler 3 4." };
    }
    var acao = (v === "marcar" || v === "m" || v === "bandeira" || v === "flag") ? "marcar" : (v === "abrir" || v === "a" || v === "o" || /^\d+$/.test(v)) ? "abrir" : null;
    if (!acao) return { msg: "Não entendi. Digite ajuda para ver os comandos." };
    if (nums.length < 2) return { msg: "Informe a linha e a coluna, por exemplo: " + acao + " 3 4." };
    return acao === "abrir" ? abrir(e, nums[0], nums[1], rnd) : marcar(e, nums[0], nums[1]);
  }

  var api = { NIVEIS: NIVEIS, novo: novo, colocar: colocar, abrir: abrir, marcar: marcar, vizinhas: vizinhas, idx: idx, simbolo: simbolo, lerCasa: lerCasa, lerLinha: lerLinha, lerColuna: lerColuna,
    lerTudo: lerTudo, resumo: resumo, comando: comando, seguras: seguras };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil"), modo = "abrir", botoes = [];
  function D(m, f) { if (H.som) H.som.dizer("minas", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { return H.el("option", { value: k, texto: NIVEIS[k].nome.charAt(0).toUpperCase() + NIVEIS[k].nome.slice(1) + ": " + NIVEIS[k].l + " por " + NIVEIS[k].c + ", " + NIVEIS[k].m + " minas" }); }));
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  var modoBtn = H.el("button", { type: "button", id: "modo", texto: "Modo da grade: abrir" });
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (abrir 3 4, marcar 3 4, ler 3, tabuleiro, resumo, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var grade = H.el("table", { id: "grade", "aria-label": "Tabuleiro do campo minado" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, form, modoBtn, grade].forEach(function (x) { jogo.appendChild(x); });

  function rotulo(i) {
    var r = Math.floor(i / e.c) + 1, c = (i % e.c) + 1, s = simbolo(e, i);
    return "linha " + r + ", coluna " + c + ", " + (/^\d$/.test(s) ? "aberta, " + minasAo(Number(s)) : s);
  }
  function glifo(i) { var s = simbolo(e, i); return s === "fechada" ? "·" : s === "marcada" ? "⚑" : s === "vazia" ? " " : s === "mina" ? "*" : s; }
  function desenhar() {
    grade.textContent = ""; botoes = [];
    for (var r = 1; r <= e.l; r++) {
      var linha = H.el("tr", {});
      for (var c = 1; c <= e.c; c++) {
        (function (r2, c2) {
          var i = idx(e, r2, c2), b = H.el("button", { type: "button", "aria-label": rotulo(i), texto: glifo(i) });
          b.addEventListener("click", function () { jogar(modo, r2, c2); });
          b.addEventListener("contextmenu", function (ev) { ev.preventDefault(); jogar("marcar", r2, c2); });
          botoes[i] = b; linha.appendChild(H.el("td", {}, [b]));
        })(r, c);
      }
      grade.appendChild(linha);
    }
  }
  function atualizar() {
    botoes.forEach(function (b, i) { b.setAttribute("aria-label", rotulo(i)); b.textContent = glifo(i); });
  }
  function jogar(acao, r, c) {
    var res = acao === "abrir" ? abrir(e, r, c) : marcar(e, r, c);
    atualizar(); D(res.msg);
  }
  function comecar() {
    e = novo(nivelSel.value); modo = "abrir"; modoBtn.textContent = "Modo da grade: abrir"; desenhar();
    H.anunciar("Novo jogo, nível " + e.nome + ": " + e.l + " linhas por " + e.c + " colunas, com " + e.m + " minas. Todas as casas estão fechadas. Comece abrindo qualquer casa, por exemplo: abrir 1 1.");
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var r = comando(e, campo.value); campo.value = ""; atualizar(); D(r.msg); campo.focus();
  });
  modoBtn.addEventListener("click", function () { modo = modo === "abrir" ? "marcar" : "abrir"; modoBtn.textContent = "Modo da grade: " + modo; H.anunciar("Agora, tocar em uma casa da grade vai " + modo + " a casa."); });
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
