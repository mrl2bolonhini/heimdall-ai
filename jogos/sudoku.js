// Sudoku por comandos, feito para leitor de tela. Linhas e colunas de 1 a 9, quadrantes de 1 a 9 (da esquerda para a direita, de cima para baixo).
// Você coloca um número com "colocar 5 em 3 4" (valor, linha, coluna). Todo tabuleiro tem uma única solução.
// Níveis: fácil (o jogo avisa na hora se o número não é o certo, dicas à vontade), normal (3 dicas, e o comando verificar aponta os erros) e difícil (sem dicas; verificar só acusa números repetidos).
(function (raiz) {
  "use strict";
  var NIVEIS = { facil: { nome: "fácil", dados: 40, dicas: 99 }, normal: { nome: "normal", dados: 32, dicas: 3 }, dificil: { nome: "difícil", dados: 26, dicas: 0 } };
  var PAL = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"];

  function sorteioPadrao(n) { return Math.floor(Math.random() * n); }
  function embaralhar(a, rnd) { a = a.slice(); for (var i = a.length - 1; i > 0; i--) { var j = rnd(i + 1), t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function lin(i) { return Math.floor(i / 9); }
  function col(i) { return i % 9; }
  function quad(i) { return Math.floor(lin(i) / 3) * 3 + Math.floor(col(i) / 3); }
  function candidatos(g, i) {
    var usados = {}, k;
    for (k = 0; k < 81; k++) if (g[k] && k !== i && (lin(k) === lin(i) || col(k) === col(i) || quad(k) === quad(i))) usados[g[k]] = true;
    var c = []; for (k = 1; k <= 9; k++) if (!usados[k]) c.push(k); return c;
  }
  // Conta soluções até o limite (para garantir solução única).
  function contar(g, limite) {
    var melhor = -1, mc = null, i, c;
    for (i = 0; i < 81; i++) if (!g[i]) { c = candidatos(g, i); if (!c.length) return 0; if (mc === null || c.length < mc.length) { mc = c; melhor = i; if (c.length === 1) break; } }
    if (melhor < 0) return 1;
    var total = 0;
    for (i = 0; i < mc.length; i++) { g[melhor] = mc[i]; total += contar(g, limite - total); if (total >= limite) break; }
    g[melhor] = 0; return total;
  }
  function completar(g, rnd) {
    var melhor = -1, mc = null, i, c;
    for (i = 0; i < 81; i++) if (!g[i]) { c = candidatos(g, i); if (!c.length) return false; if (mc === null || c.length < mc.length) { mc = c; melhor = i; } }
    if (melhor < 0) return true;
    mc = embaralhar(mc, rnd);
    for (i = 0; i < mc.length; i++) { g[melhor] = mc[i]; if (completar(g, rnd)) return true; }
    g[melhor] = 0; return false;
  }
  function gerar(nivel, rnd) {
    rnd = rnd || sorteioPadrao;
    var sol = new Array(81).fill(0); completar(sol, rnd);
    var puz = sol.slice(), alvo = NIVEIS[nivel].dados, restam = 81;
    embaralhar(Array.from({ length: 81 }, function (_, i) { return i; }), rnd).forEach(function (i) {
      if (restam <= alvo) return;
      var v = puz[i]; puz[i] = 0;
      if (contar(puz.slice(), 2) !== 1) puz[i] = v; else restam--;
    });
    return { puzzle: puz, solucao: sol };
  }
  function novo(nivel, rnd) {
    nivel = NIVEIS[nivel] ? nivel : "normal";
    var g = gerar(nivel, rnd);
    return { nivel: nivel, cfg: NIVEIS[nivel], dado: g.puzzle, atual: g.puzzle.slice(), solucao: g.solucao, pilha: [], dicasUsadas: 0, fim: null, jogadas: 0 };
  }

  // ---------- leitura ----------
  function falar(v) { return v ? String(v) : "vazia"; }
  function lerLinha(e, n) { if (n < 1 || n > 9) return "Linha inválida. Use de 1 a 9."; var o = []; for (var c = 0; c < 9; c++) o.push(falar(e.atual[(n - 1) * 9 + c])); return "Linha " + n + ", da coluna 1 à 9: " + o.join(", ") + "."; }
  function lerColuna(e, n) { if (n < 1 || n > 9) return "Coluna inválida. Use de 1 a 9."; var o = []; for (var r = 0; r < 9; r++) o.push(falar(e.atual[r * 9 + n - 1])); return "Coluna " + n + ", da linha 1 à 9: " + o.join(", ") + "."; }
  function lerQuadrante(e, n) {
    if (n < 1 || n > 9) return "Quadrante inválido. Use de 1 a 9.";
    var r0 = Math.floor((n - 1) / 3) * 3, c0 = ((n - 1) % 3) * 3, linhas = [];
    for (var r = 0; r < 3; r++) { var o = []; for (var c = 0; c < 3; c++) o.push(falar(e.atual[(r0 + r) * 9 + c0 + c])); linhas.push("linha " + (r0 + r + 1) + ": " + o.join(", ")); }
    return "Quadrante " + n + " (linhas " + (r0 + 1) + " a " + (r0 + 3) + ", colunas " + (c0 + 1) + " a " + (c0 + 3) + "): " + linhas.join("; ") + ".";
  }
  function faltam(lista, e, nome, n) {
    var tem = {}; lista.forEach(function (i) { if (e.atual[i]) tem[e.atual[i]] = true; });
    var f = []; for (var d = 1; d <= 9; d++) if (!tem[d]) f.push(d);
    return nome + " " + n + ": " + (f.length ? "faltam " + f.join(", ") : "está completa") + ".";
  }
  function indices(tipo, n) { var o = [], i; for (i = 0; i < 81; i++) if ((tipo === "linha" ? lin(i) : tipo === "coluna" ? col(i) : quad(i)) === n - 1) o.push(i); return o; }
  function lerCasa(e, l, c) {
    var i = (l - 1) * 9 + c - 1, v = e.atual[i], pre = "Linha " + l + ", coluna " + c + " (quadrante " + (quad(i) + 1) + "): ";
    if (e.dado[i]) return pre + e.dado[i] + ", número do enunciado.";
    if (v) return pre + v + ", colocado por você.";
    var cand = candidatos(e.atual, i); return pre + "vazia. Podem entrar: " + (cand.length ? cand.join(", ") : "nenhum número (há um erro em algum lugar)") + ".";
  }
  function tabuleiro(e) { var o = []; for (var r = 1; r <= 9; r++) o.push(lerLinha(e, r)); return o.join(" "); }
  function resumo(e) {
    var vazias = e.atual.filter(function (x) { return !x; }).length;
    return "Faltam " + vazias + " casas. Jogadas: " + e.jogadas + ". Dicas usadas: " + e.dicasUsadas + ".";
  }
  function vazias(e, tipo, n) {
    var l = indices(tipo, n).filter(function (i) { return !e.atual[i]; }).map(function (i) { return "linha " + (lin(i) + 1) + " coluna " + (col(i) + 1); });
    return l.length ? "Casas vazias no " + tipo + " " + n + ": " + l.join("; ") + "." : "Não há casas vazias no " + tipo + " " + n + ".";
  }

  // ---------- jogadas ----------
  function conflito(e, i, v) {
    var k; for (k = 0; k < 81; k++) if (k !== i && e.atual[k] === v) {
      if (lin(k) === lin(i)) return "já existe um " + v + " na linha " + (lin(i) + 1) + " (coluna " + (col(k) + 1) + ")";
      if (col(k) === col(i)) return "já existe um " + v + " na coluna " + (col(i) + 1) + " (linha " + (lin(k) + 1) + ")";
      if (quad(k) === quad(i)) return "já existe um " + v + " no quadrante " + (quad(i) + 1) + " (linha " + (lin(k) + 1) + ", coluna " + (col(k) + 1) + ")";
    }
    return "";
  }
  function completo(e) { return e.atual.every(function (x, i) { return x === e.solucao[i]; }); }
  function checarFim(e, msg) {
    if (completo(e)) { e.fim = "vitoria"; return { msg: msg + " Sudoku completo! Você terminou em " + e.jogadas + " jogadas, com " + e.dicasUsadas + (e.dicasUsadas === 1 ? " dica." : " dicas."), fim: true }; }
    return { msg: msg };
  }
  function colocar(e, v, l, c) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo.", erro: true };
    if (v < 1 || v > 9 || l < 1 || l > 9 || c < 1 || c > 9) return { msg: "Use números de 1 a 9 para o valor, a linha e a coluna. Exemplo: colocar 5 em 3 4.", erro: true };
    var i = (l - 1) * 9 + c - 1;
    if (e.dado[i]) return { msg: "A casa linha " + l + ", coluna " + c + " é do enunciado (" + e.dado[i] + ") e não pode mudar.", erro: true };
    var cf = conflito(e, i, v); if (cf) return { msg: "Não dá: " + cf + ".", erro: true };
    if (e.cfg === NIVEIS.facil && e.solucao[i] !== v) return { msg: "O " + v + " não cabe nessa casa: a solução é outra. (No nível fácil o jogo avisa na hora.)", erro: true };
    e.pilha.push({ i: i, antes: e.atual[i] }); e.atual[i] = v; e.jogadas++;
    return checarFim(e, "Colocado " + v + " na linha " + l + ", coluna " + c + ".");
  }
  function apagar(e, l, c) {
    if (e.fim) return { msg: "A partida terminou.", erro: true };
    var i = (l - 1) * 9 + c - 1;
    if (l < 1 || l > 9 || c < 1 || c > 9) return { msg: "Use linha e coluna de 1 a 9.", erro: true };
    if (e.dado[i]) return { msg: "Essa casa é do enunciado e não pode ser apagada.", erro: true };
    if (!e.atual[i]) return { msg: "Essa casa já está vazia.", erro: true };
    e.pilha.push({ i: i, antes: e.atual[i] }); var v = e.atual[i]; e.atual[i] = 0; e.jogadas++;
    return { msg: "Apagado o " + v + " da linha " + l + ", coluna " + c + "." };
  }
  function desfazer(e) {
    if (e.fim) return { msg: "A partida terminou.", erro: true };
    var u = e.pilha.pop(); if (!u) return { msg: "Não há jogada para desfazer.", erro: true };
    e.atual[u.i] = u.antes; return { msg: "Desfeito: linha " + (lin(u.i) + 1) + ", coluna " + (col(u.i) + 1) + " voltou a ficar " + (u.antes ? "com " + u.antes : "vazia") + "." };
  }
  function dica(e) {
    if (e.fim) return { msg: "A partida terminou.", erro: true };
    if (e.dicasUsadas >= e.cfg.dicas) return { msg: e.cfg.dicas === 0 ? "No nível difícil não há dicas." : "As " + e.cfg.dicas + " dicas do nível normal acabaram.", erro: true };
    // prefere a casa com menos candidatos; se houver número errado colocado, avisa
    var erro = -1, i, melhor = -1, mc = 10;
    for (i = 0; i < 81; i++) if (e.atual[i] && e.atual[i] !== e.solucao[i]) { erro = i; break; }
    if (erro >= 0) { e.dicasUsadas++; return { msg: "Dica: o número da linha " + (lin(erro) + 1) + ", coluna " + (col(erro) + 1) + " está errado. Apague-o." }; }
    for (i = 0; i < 81; i++) if (!e.atual[i]) { var n = candidatos(e.atual, i).length; if (n < mc) { mc = n; melhor = i; } }
    e.dicasUsadas++; e.pilha.push({ i: melhor, antes: 0 }); e.atual[melhor] = e.solucao[melhor]; e.jogadas++;
    return checarFim(e, "Dica: na linha " + (lin(melhor) + 1) + ", coluna " + (col(melhor) + 1) + " vai o " + e.solucao[melhor] + ", e eu já coloquei.");
  }
  function verificar(e) {
    var erros = [], i;
    for (i = 0; i < 81; i++) if (e.atual[i] && !e.dado[i] && e.atual[i] !== e.solucao[i]) erros.push(i);
    if (e.cfg === NIVEIS.dificil) return { msg: "Nível difícil: o jogo não confere números certos e errados. Os números repetidos em linha, coluna ou quadrante já são recusados na hora." };
    if (!erros.length) return { msg: "Tudo o que você colocou está certo até agora." };
    return { msg: "Há " + erros.length + (erros.length === 1 ? " número errado: " : " números errados: ") + erros.map(function (k) { return "linha " + (lin(k) + 1) + ", coluna " + (col(k) + 1); }).join("; ") + "." };
  }
  function ajuda() {
    return "Colocar: colocar 5 em 3 4 (valor, linha, coluna). Apagar: apagar 3 4. Ler: linha 3, coluna 4, quadrante 5, casa 3 4 (diz o que pode entrar), tabuleiro. " +
      "Faltam: faltam linha 3, faltam coluna 4, faltam quadrante 5. Casas vazias: vazias linha 3. Outros: verificar, dica, desfazer, resumo, desistir. Linhas e colunas vão de 1 a 9; os quadrantes, de 1 a 9, da esquerda para a direita e de cima para baixo.";
  }
  function nums(t) { return (t.match(/\d+/g) || []).map(Number); }
  function comando(e, texto) {
    var t = String(texto).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim().replace(/\s+/g, " "), p = t.split(" "), v = p[0], n = nums(t);
    if (!t) return { msg: "Digite um comando, por exemplo colocar 5 em 3 4, ou ajuda.", erro: true };
    if (v === "ajuda" || v === "?") return { msg: ajuda() };
    if (v === "colocar" || v === "por" || v === "poe" || v === "ponha" || (/^\d$/.test(v) && /\bem\b|\bna\b|\blinha\b/.test(t))) {
      if (n.length !== 3) return { msg: "Para colocar, diga valor, linha e coluna. Exemplo: colocar 5 em 3 4.", erro: true };
      return colocar(e, n[0], n[1], n[2]);
    }
    if (v === "apagar" || v === "limpar" || v === "tirar") return n.length === 2 ? apagar(e, n[0], n[1]) : { msg: "Para apagar, diga linha e coluna. Exemplo: apagar 3 4.", erro: true };
    if (v === "desfazer") return desfazer(e);
    if (v === "dica") return dica(e);
    if (v === "verificar" || v === "conferir") return verificar(e);
    if (v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "tabuleiro" || v === "tudo") return { msg: tabuleiro(e) };
    if (v === "desistir") { if (e.fim) return { msg: "A partida terminou.", erro: true }; e.fim = "desistencia"; return { msg: "Você desistiu. A solução, linha por linha: " + tabuleiro({ atual: e.solucao }) }; }
    var tipo = { linha: "linha", coluna: "coluna", quadrante: "quadrante" };
    if ((v === "faltam" || v === "falta") && tipo[p[1]] && n.length === 1) { if (n[0] < 1 || n[0] > 9) return { msg: "Use um número de 1 a 9.", erro: true }; return { msg: faltam(indices(p[1], n[0]), e, p[1].charAt(0).toUpperCase() + p[1].slice(1), n[0]) }; }
    if (v === "vazias" && tipo[p[1]] && n.length === 1) { if (n[0] < 1 || n[0] > 9) return { msg: "Use um número de 1 a 9.", erro: true }; return { msg: vazias(e, p[1], n[0]) }; }
    if (v === "linha" && n.length === 1) return { msg: lerLinha(e, n[0]) };
    if (v === "coluna" && n.length === 1) return { msg: lerColuna(e, n[0]) };
    if (v === "quadrante" && n.length === 1) return { msg: lerQuadrante(e, n[0]) };
    if ((v === "casa" || v === "ver") && n.length === 2) { if (n[0] < 1 || n[0] > 9 || n[1] < 1 || n[1] > 9) return { msg: "Use linha e coluna de 1 a 9.", erro: true }; return { msg: lerCasa(e, n[0], n[1]) }; }
    return { msg: "Não entendi \"" + texto + "\". Digite ajuda para ver os comandos.", erro: true };
  }
  function desenho(e) {
    var l = [], r, c;
    for (r = 0; r < 9; r++) { var s = ""; for (c = 0; c < 9; c++) { s += (e.atual[r * 9 + c] || ".") + (c % 3 === 2 && c < 8 ? " | " : " "); } l.push(s); if (r % 3 === 2 && r < 8) l.push("------+-------+------"); }
    return l.join("\n");
  }

  var api = { NIVEIS: NIVEIS, gerar: gerar, novo: novo, contar: contar, candidatos: candidatos, comando: comando, colocar: colocar, apagar: apagar, desfazer: desfazer, dica: dica, verificar: verificar, lerLinha: lerLinha, lerColuna: lerColuna, lerQuadrante: lerQuadrante, lerCasa: lerCasa, desenho: desenho, lin: lin, col: col, quad: quad };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = null;
  function D(m, f) { if (H.som) H.som.dizer("sudoku", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var selNivel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { return H.el("option", { value: k, texto: NIVEIS[k].nome.charAt(0).toUpperCase() + NIVEIS[k].nome.slice(1) + ": " + NIVEIS[k].dados + " números dados" }); }));
  selNivel.value = "normal";
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (colocar 5 em 3 4, linha 3, casa 3 4, ajuda...)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var historia = H.el("ol", { id: "historico", "aria-label": "Histórico da partida" });
  var visual = H.el("pre", { id: "visual", "aria-hidden": "true" });
  [H.el("label", { "for": "nivel", texto: "Nível (vale ao começar um novo jogo)" }), selNivel, novoBtn, form, historia, visual].forEach(function (x) { jogo.appendChild(x); });
  function escrever(m) { historia.insertBefore(H.el("li", { texto: m }), historia.firstChild); D(m); }
  function atualizar() { visual.textContent = desenho(e); }
  function comecar() {
    e = novo(selNivel.value); historia.textContent = ""; campo.disabled = false; atualizar();
    escrever("Novo sudoku, nível " + e.cfg.nome + ", com " + e.dado.filter(Boolean).length + " números dados. Digite tabuleiro para ouvir tudo, linha 1 para ouvir uma linha, ou ajuda. Para jogar: colocar 5 em 3 4.");
    campo.focus();
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var t = campo.value; campo.value = ""; var r = comando(e, t); atualizar(); escrever("> " + t + " — " + r.msg);
    if (e.fim) { campo.disabled = true; novoBtn.focus(); } else campo.focus();
  });
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
