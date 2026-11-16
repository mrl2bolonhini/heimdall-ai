// Jogo da velha contra o computador. Você é o X. No modo difícil o computador não perde.
(function (raiz) {
  "use strict";
  var LINHAS = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
  function vencedor(t) {
    for (var i = 0; i < LINHAS.length; i++) { var l = LINHAS[i]; if (t[l[0]] && t[l[0]] === t[l[1]] && t[l[0]] === t[l[2]]) return t[l[0]]; }
    return t.indexOf("") < 0 ? "empate" : null;
  }
  function minimax(t, vez, eu) {
    var v = vencedor(t);
    if (v === eu) return 10; if (v === "empate") return 0; if (v) return -10;
    var melhor = vez === eu ? -99 : 99;
    for (var i = 0; i < 9; i++) {
      if (t[i]) continue;
      t[i] = vez; var s = minimax(t, vez === "X" ? "O" : "X", eu); t[i] = "";
      // quanto antes ganhar (ou mais tarde perder), melhor
      s += s > 0 ? -t.filter(Boolean).length * 0.01 : s < 0 ? t.filter(Boolean).length * 0.01 : 0;
      melhor = vez === eu ? Math.max(melhor, s) : Math.min(melhor, s);
    }
    return melhor;
  }
  function jogadaDificil(t) {
    var melhor = -99, pos = -1;
    for (var i = 0; i < 9; i++) { if (t[i]) continue; t[i] = "O"; var s = minimax(t, "X", "O"); t[i] = ""; if (s > melhor) { melhor = s; pos = i; } }
    return pos;
  }
  function jogadaFacil(t, rnd) {
    var livres = []; for (var i = 0; i < 9; i++) if (!t[i]) livres.push(i);
    return livres[Math.floor((rnd ? rnd() : Math.random()) * livres.length)];
  }
  function nome(i) { return "linha " + (Math.floor(i / 3) + 1) + ", coluna " + (i % 3 + 1); }
  var api = { vencedor: vencedor, jogadaDificil: jogadaDificil, jogadaFacil: jogadaFacil, nome: nome };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), tab, dificil = true, botoes = [];
  function D(m, f) { if (H.som) H.som.dizer("velha", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var info = H.el("p", { id: "info" });
  var nivel = H.el("button", { type: "button", id: "nivel" });
  var novo = H.el("button", { type: "button", texto: "Nova partida" });
  var grade = H.el("div", { role: "group", "aria-label": "Tabuleiro, 3 linhas e 3 colunas" });
  for (var i = 0; i < 9; i++) {
    (function (k) {
      var b = H.el("button", { type: "button" });
      b.addEventListener("click", function () { jogar(k); });
      botoes.push(b); grade.appendChild(b);
    })(i);
  }
  [info, nivel, grade, novo].forEach(function (x) { jogo.appendChild(x); });
  grade.style.cssText = "display:grid;grid-template-columns:repeat(3,5rem);gap:.4rem;margin:1rem 0";
  function pintar() {
    botoes.forEach(function (b, k) {
      var v = tab[k];
      b.textContent = v || "·";
      b.setAttribute("aria-label", nome(k) + (v ? ", " + v : ", vazia"));
      b.disabled = !!v || !!vencedor(tab);
      b.style.cssText = "font-size:2rem;height:5rem";
    });
    nivel.textContent = "Nível: " + (dificil ? "difícil" : "fácil") + ". Mudar";
  }
  function fim(v) {
    return v === "X" ? "Você ganhou!" : v === "O" ? "O computador ganhou." : "Deu velha: empate.";
  }
  function jogar(k) {
    if (tab[k] || vencedor(tab)) return;
    tab[k] = "X"; var msg = "Você jogou em " + nome(k) + ".", v = vencedor(tab);
    if (!v) { var c = dificil ? jogadaDificil(tab) : jogadaFacil(tab); tab[c] = "O"; msg += " O computador jogou em " + nome(c) + "."; v = vencedor(tab); }
    pintar();
    if (v) { msg += " " + fim(v); novo.focus(); } else { var livre = botoes.filter(function (b) { return !b.disabled; })[0]; msg += " Sua vez."; if (document.activeElement === document.body) livre.focus(); }
    info.textContent = msg; D(msg, msg + " " + estado());
  }
  function estado() {
    var l = ["X", "O"].map(function (j) { return j + " em: " + (tab.map(function (v, k) { return v === j ? nome(k) : null; }).filter(Boolean).join("; ") || "nenhuma casa"); });
    return l.join(". ") + ".";
  }
  nivel.addEventListener("click", function () { dificil = !dificil; comecar(); });
  function comecar() { tab = ["","","","","","","","",""]; pintar(); info.textContent = "Você é o X. Escolha uma casa."; H.anunciar("Nova partida no nível " + (dificil ? "difícil" : "fácil") + ". Você é o X. Escolha uma casa."); }
  novo.addEventListener("click", function () { comecar(); botoes[0].focus(); });
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
