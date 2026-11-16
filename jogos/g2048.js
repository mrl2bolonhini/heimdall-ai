// 2048 para leitor de tela: use os botões ou as setas do teclado. Cada jogada é descrita em voz alta.
(function (raiz) {
  "use strict";
  var N = 4;
  function vazio() { var t = []; for (var i = 0; i < N; i++) t.push([0, 0, 0, 0]); return t; }
  function copia(t) { return t.map(function (l) { return l.slice(); }); }
  function deslocaLinha(l) {
    var v = l.filter(Boolean), pontos = 0, r = [];
    for (var i = 0; i < v.length; i++) {
      if (v[i] === v[i + 1]) { r.push(v[i] * 2); pontos += v[i] * 2; i++; } else r.push(v[i]);
    }
    while (r.length < N) r.push(0);
    return { linha: r, pontos: pontos };
  }
  function girar(t) { var r = vazio(); for (var i = 0; i < N; i++) for (var j = 0; j < N; j++) r[j][N - 1 - i] = t[i][j]; return r; }
  // dir: esquerda, direita, cima, baixo
  function mover(t, dir) {
    var giros = { esquerda: 0, baixo: 1, direita: 2, cima: 3 }[dir], g = copia(t), k;
    for (k = 0; k < giros; k++) g = girar(g);
    var pontos = 0; g = g.map(function (l) { var r = deslocaLinha(l); pontos += r.pontos; return r.linha; });
    for (k = 0; k < (4 - giros) % 4; k++) g = girar(g);
    return { tab: g, pontos: pontos, moveu: JSON.stringify(g) !== JSON.stringify(t) };
  }
  function vazias(t) { var r = []; for (var i = 0; i < N; i++) for (var j = 0; j < N; j++) if (!t[i][j]) r.push([i, j]); return r; }
  function surgir(t, rnd) {
    var v = vazias(t); if (!v.length) return null;
    var p = v[Math.floor((rnd ? rnd() : Math.random()) * v.length)], valor = (rnd ? rnd() : Math.random()) < 0.9 ? 2 : 4;
    t[p[0]][p[1]] = valor; return { linha: p[0], coluna: p[1], valor: valor };
  }
  function acabou(t) {
    return ["esquerda", "direita", "cima", "baixo"].every(function (d) { return !mover(t, d).moveu; });
  }
  function maior(t) { return Math.max.apply(null, t.map(function (l) { return Math.max.apply(null, l); })); }
  function ler(t) {
    return t.map(function (l, i) { return "Linha " + (i + 1) + ": " + l.map(function (v) { return v || "vazio"; }).join(", "); }).join(". ") + ".";
  }
  var api = { mover: mover, surgir: surgir, acabou: acabou, maior: maior, ler: ler, vazio: vazio, vazias: vazias };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), tab, pontos, venceu;
  function D(m, f) { if (H.som) H.som.dizer("g2048", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var info = H.el("p", { id: "info" }), quadro = H.el("ul", { id: "quadro", "aria-label": "Tabuleiro" });
  var barra = H.el("div", { role: "group", "aria-label": "Mover as peças" });
  [["esquerda", "Esquerda"], ["direita", "Direita"], ["cima", "Cima"], ["baixo", "Baixo"]].forEach(function (d) {
    var b = H.el("button", { type: "button", texto: d[1] }); b.addEventListener("click", function () { jogada(d[0]); }); barra.appendChild(b);
  });
  var ler_b = H.el("button", { type: "button", texto: "Ler o tabuleiro" }), novo = H.el("button", { type: "button", texto: "Nova partida" });
  var dica = H.el("p", { texto: "Dica: com o foco fora de um campo de texto, as setas do teclado também movem as peças." });
  [info, barra, quadro, ler_b, novo, dica].forEach(function (x) { jogo.appendChild(x); });
  function pintar() {
    quadro.textContent = "";
    tab.forEach(function (l, i) { quadro.appendChild(H.el("li", { texto: "Linha " + (i + 1) + ": " + l.map(function (v) { return v || "vazio"; }).join(", ") })); });
    info.textContent = "Pontos: " + pontos + ". Maior peça: " + maior(tab) + ".";
  }
  function jogada(dir) {
    var r = mover(tab, dir);
    if (!r.moveu) { D("Nada se moveu para " + dir + "."); return; }
    tab = r.tab; pontos += r.pontos;
    var s = surgir(tab), msg = "Moveu para " + dir + (r.pontos ? ", somando " + r.pontos + " pontos" : "") + ". ";
    if (s) msg += "Surgiu " + s.valor + " na linha " + (s.linha + 1) + ", coluna " + (s.coluna + 1) + ". ";
    if (!venceu && maior(tab) >= 2048) { venceu = true; msg += "Você chegou ao 2048! Pode continuar jogando. "; }
    pintar();
    if (acabou(tab)) msg += "Não há mais jogadas. Fim de jogo com " + pontos + " pontos.";
    else msg += "Pontos: " + pontos + ".";
    D(msg);
  }
  function comecar() { tab = vazio(); pontos = 0; venceu = false; surgir(tab); surgir(tab); pintar(); H.anunciar("Nova partida. " + ler(tab)); }
  ler_b.addEventListener("click", function () { H.anunciar(ler(tab) + " Pontos: " + pontos + "."); });
  novo.addEventListener("click", comecar);
  document.addEventListener("keydown", function (ev) {
    var t = ev.target && ev.target.tagName; if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT") return;
    var d = { ArrowLeft: "esquerda", ArrowRight: "direita", ArrowUp: "cima", ArrowDown: "baixo" }[ev.key];
    if (d) { ev.preventDefault(); jogada(d); }
  });
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
