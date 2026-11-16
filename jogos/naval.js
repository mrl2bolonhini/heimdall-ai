// Batalha naval contra o computador, feita para leitor de tela. Tabuleiro 10 por 10: colunas de A a J e linhas de 1 a 10.
// Você atira dizendo a casa (B7, ou "tiro b7"); o computador responde atirando na sua frota. As duas frotas são sorteadas.
// Níveis: fácil (o computador atira ao acaso), normal (caça em volta dos acertos) e difícil (calcula onde os navios restantes mais cabem).
(function (raiz) {
  "use strict";
  var COLS = "ABCDEFGHIJ", N = 10;
  var FROTA = [{ nome: "porta-aviões", tam: 5, art: "o" }, { nome: "encouraçado", tam: 4, art: "o" }, { nome: "cruzador", tam: 3, art: "o" }, { nome: "submarino", tam: 3, art: "o" }, { nome: "destróier", tam: 2, art: "o" }];
  var NIVEIS = { facil: "fácil", normal: "normal", dificil: "difícil" };
  // tiros: 0 sem tiro, 1 água, 2 acerto num navio ainda flutuando, 3 acerto num navio afundado

  function nome(i) { return COLS[i % N] + (Math.floor(i / N) + 1); }
  function casa(t) {
    var s = String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    s = s.replace(/^(tiro|atirar|atire|fogo|disparar|dispare|tiro em|atirar em|em)\s+/, "").replace(/^(tiro|atirar|fogo|em)\s+/, "");
    var m = s.match(/^([a-j]) ?(10|[1-9])$/) || s.match(/^(10|[1-9]) ?([a-j])$/);
    if (!m) return -1;
    var letra = /[a-j]/.test(m[1]) ? m[1] : m[2], num = /[a-j]/.test(m[1]) ? m[2] : m[1];
    return (Number(num) - 1) * N + COLS.toLowerCase().indexOf(letra);
  }
  function sorteioPadrao(n) { return Math.floor(Math.random() * n); }

  function frotaAleatoria(rnd) {
    var grade = [], navios = [], i;
    for (i = 0; i < N * N; i++) grade.push(-1);
    FROTA.forEach(function (f, k) {
      for (;;) {
        var horiz = rnd(2) === 0, r = rnd(horiz ? N : N - f.tam + 1), c = rnd(horiz ? N - f.tam + 1 : N), cels = [], livre = true, j;
        for (j = 0; j < f.tam; j++) { var x = horiz ? r * N + c + j : (r + j) * N + c; cels.push(x); if (grade[x] >= 0) livre = false; }
        if (!livre) continue;
        cels.forEach(function (x) { grade[x] = k; });
        navios.push({ nome: f.nome, tam: f.tam, cels: cels, horiz: horiz, afundado: false });
        break;
      }
    });
    return { grade: grade, navios: navios, tiros: new Array(N * N).fill(0) };
  }
  function novo(nivel, rnd) {
    rnd = rnd || sorteioPadrao;
    return { nivel: NIVEIS[nivel] ? nivel : "normal", eu: frotaAleatoria(rnd), ele: frotaAleatoria(rnd), fim: null, ultimo: "", turnos: 0, rnd: rnd };
  }

  // Tiro em um lado: devolve {tipo: "agua"|"acerto"|"afundou", navio}
  function receber(lado, i) {
    var k = lado.grade[i];
    if (k < 0) { lado.tiros[i] = 1; return { tipo: "agua" }; }
    var nv = lado.navios[k]; lado.tiros[i] = 2;
    if (nv.cels.every(function (x) { return lado.tiros[x] >= 2; })) { nv.afundado = true; nv.cels.forEach(function (x) { lado.tiros[x] = 3; }); return { tipo: "afundou", navio: nv }; }
    return { tipo: "acerto", navio: nv };
  }
  function venceu(lado) { return lado.navios.every(function (n) { return n.afundado; }); }
  function frase(i, r, quem) {
    var c = nome(i);
    if (r.tipo === "agua") return c + ": água.";
    if (r.tipo === "acerto") return c + ": acertou" + (quem === "ele" ? " um navio seu!" : "!");
    return c + ": acertou e afundou " + (quem === "ele" ? "o seu " : "o ") + r.navio.nome + " (" + r.navio.tam + " casas)!";
  }

  // ---------- computador ----------
  function vizinhas(i) {
    var r = Math.floor(i / N), c = i % N, o = [];
    if (r > 0) o.push(i - N); if (r < N - 1) o.push(i + N); if (c > 0) o.push(i - 1); if (c < N - 1) o.push(i + 1);
    return o;
  }
  function densidade(lado) {
    var d = new Array(N * N).fill(0);
    lado.navios.filter(function (n) { return !n.afundado; }).forEach(function (n) {
      for (var dir = 0; dir < 2; dir++) for (var r = 0; r < N; r++) for (var c = 0; c < N; c++) {
        if (dir === 0 ? c + n.tam > N : r + n.tam > N) continue;
        var cels = [], ok = true, acertos = 0;
        for (var j = 0; j < n.tam; j++) { var x = dir === 0 ? r * N + c + j : (r + j) * N + c; cels.push(x); if (lado.tiros[x] === 1 || lado.tiros[x] === 3) ok = false; if (lado.tiros[x] === 2) acertos++; }
        if (!ok) continue;
        var peso = acertos ? Math.pow(30, acertos) : 1;
        cels.forEach(function (x) { if (lado.tiros[x] === 0) d[x] += peso; });
      }
    });
    return d;
  }
  function escolherTiro(e) {
    var lado = e.eu, rnd = e.rnd, livres = [], i;
    for (i = 0; i < N * N; i++) if (lado.tiros[i] === 0) livres.push(i);
    if (e.nivel === "dificil") {
      var d = densidade(lado), max = Math.max.apply(null, livres.map(function (x) { return d[x]; })), melhores = livres.filter(function (x) { return d[x] === max; });
      return melhores[rnd(melhores.length)];
    }
    if (e.nivel === "normal") {
      var alvos = [];
      for (i = 0; i < N * N; i++) if (lado.tiros[i] === 2) vizinhas(i).forEach(function (v) { if (lado.tiros[v] === 0 && alvos.indexOf(v) < 0) alvos.push(v); });
      if (alvos.length) return alvos[rnd(alvos.length)];
      var par = livres.filter(function (x) { return (Math.floor(x / N) + (x % N)) % 2 === 0; });
      return (par.length ? par : livres)[rnd((par.length ? par : livres).length)];
    }
    return livres[rnd(livres.length)];
  }
  function jogadaComputador(e) {
    var i = escolherTiro(e), r = receber(e.eu, i);
    e.turnos++;
    var msg = "O computador atirou em " + frase(i, r, "ele");
    if (venceu(e.eu)) { e.fim = "derrota"; msg += " Toda a sua frota afundou. Você perdeu."; }
    return msg;
  }

  // ---------- leitura ----------
  function lista(a) { return a.length <= 1 ? a.join("") : a.slice(0, -1).join(", ") + " e " + a[a.length - 1]; }
  function estado(v) { return v === 1 ? "água" : v === 2 ? "acerto" : v === 3 ? "afundado" : "sem tiro"; }
  function lerLinha(e, n) {
    if (n < 1 || n > N) return "Linha inválida. Use de 1 a 10.";
    var p = [], c; for (c = 0; c < N; c++) { var v = e.ele.tiros[(n - 1) * N + c]; if (v) p.push(COLS[c] + n + " " + estado(v)); }
    return "Linha " + n + ", seus tiros: " + (p.length ? lista(p) + "; as outras casas estão sem tiro" : "nenhum ainda") + ".";
  }
  function lerColuna(e, l) {
    var c = COLS.indexOf(String(l).toUpperCase()); if (c < 0) return "Coluna inválida. Use de A a J.";
    var p = [], r; for (r = 0; r < N; r++) { var v = e.ele.tiros[r * N + c]; if (v) p.push(COLS[c] + (r + 1) + " " + estado(v)); }
    return "Coluna " + COLS[c] + ", seus tiros: " + (p.length ? lista(p) + "; as outras casas estão sem tiro" : "nenhum ainda") + ".";
  }
  function tirosDe(lado) {
    var ac = [], ag = [], i; for (i = 0; i < N * N; i++) { if (lado.tiros[i] >= 2) ac.push(nome(i)); else if (lado.tiros[i] === 1) ag.push(nome(i)); }
    return { ac: ac, ag: ag };
  }
  function lerTiros(e) {
    var t = tirosDe(e.ele);
    if (!t.ac.length && !t.ag.length) return "Você ainda não atirou.";
    return "Seus acertos: " + (t.ac.length ? lista(t.ac) : "nenhum") + ". Suas águas: " + (t.ag.length ? lista(t.ag) : "nenhuma") + ".";
  }
  function lerTirosInimigos(e) {
    var t = tirosDe(e.eu);
    if (!t.ac.length && !t.ag.length) return "O computador ainda não atirou.";
    return "Acertos do computador em você: " + (t.ac.length ? lista(t.ac) : "nenhum") + ". Águas dele: " + (t.ag.length ? lista(t.ag) : "nenhuma") + ".";
  }
  function lerFrota(e) {
    return "Sua frota: " + e.eu.navios.map(function (n) {
      var ord = n.cels.slice().sort(function (a, b) { return a - b; }), ac = n.cels.filter(function (x) { return e.eu.tiros[x] >= 2; }).length;
      return n.nome + ", " + n.tam + " casas, de " + nome(ord[0]) + " a " + nome(ord[ord.length - 1]) + ", " + (n.horiz ? "na horizontal" : "na vertical") + ", " + (n.afundado ? "afundado" : ac ? "atingido " + ac + (ac === 1 ? " vez" : " vezes") : "intacto");
    }).join("; ") + ".";
  }
  function lerRestantes(e) {
    var vivos = e.ele.navios.filter(function (n) { return !n.afundado; }), af = e.ele.navios.filter(function (n) { return n.afundado; });
    return "Navios do inimigo ainda ao mar: " + (vivos.length ? lista(vivos.map(function (n) { return n.nome + " (" + n.tam + ")"; })) : "nenhum") + ". Afundados: " + (af.length ? lista(af.map(function (n) { return n.nome; })) : "nenhum") + ".";
  }
  function dica(e) {
    var d = densidade(e.ele), livres = [], i;
    for (i = 0; i < N * N; i++) if (e.ele.tiros[i] === 0) livres.push(i);
    if (!livres.length) return "Não há mais casas livres.";
    var max = Math.max.apply(null, livres.map(function (x) { return d[x]; })), melhor = livres.filter(function (x) { return d[x] === max; })[0];
    return "Sugestão: atire em " + nome(melhor) + ".";
  }
  function resumo(e) {
    var meus = e.eu.navios.filter(function (n) { return !n.afundado; }).length, deles = e.ele.navios.filter(function (n) { return !n.afundado; }).length;
    return "Você tem " + meus + (meus === 1 ? " navio" : " navios") + " e o inimigo tem " + deles + ". Você atirou " + e.ele.tiros.filter(Boolean).length + " vezes.";
  }
  function ajuda() {
    return "Para atirar, diga a casa: B7, ou tiro b7. Colunas de A a J, linhas de 1 a 10. Para consultar: linha 3, coluna c, tiros, inimigo (tiros do computador), frota (a sua frota), restantes (navios inimigos), resumo, ultimo, dica, desistir.";
  }

  function comando(e, texto) {
    var t = String(texto).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim().replace(/\s+/g, " "), p = t.split(" "), v = p[0];
    if (!t) return { msg: "Digite uma casa para atirar, por exemplo B7, ou ajuda.", erro: true };
    if (v === "ajuda" || v === "?") return { msg: ajuda() };
    if (v === "linha" && /^\d+$/.test(p[1] || "")) return { msg: lerLinha(e, Number(p[1])) };
    if (v === "coluna" && /^[a-j]$/.test(p[1] || "")) return { msg: lerColuna(e, p[1]) };
    if (v === "tiros" || v === "meus") return { msg: lerTiros(e) };
    if (v === "inimigo" || v === "dele") return { msg: lerTirosInimigos(e) };
    if (v === "frota" || v === "navios") return { msg: lerFrota(e) };
    if (v === "restantes" || v === "restam") return { msg: lerRestantes(e) };
    if (v === "resumo" || v === "placar") return { msg: resumo(e) };
    if (v === "ultimo") return { msg: e.ultimo || "Ainda não houve tiros." };
    if (v === "dica") return { msg: e.fim ? "A partida terminou." : dica(e) };
    if (v === "desistir") { e.fim = "derrota"; return { msg: "Você desistiu. Vitória do computador." }; }
    var i = casa(t);
    if (i < 0) return { msg: "Não entendi \"" + texto + "\". Para atirar diga uma casa de A1 a J10. Digite ajuda para ver os comandos.", erro: true };
    if (e.fim) return { msg: "A partida terminou. Comece uma nova.", erro: true };
    if (e.ele.tiros[i]) return { msg: "Você já atirou em " + nome(i) + " (" + estado(e.ele.tiros[i]) + "). Escolha outra casa.", erro: true };
    var r = receber(e.ele, i), msg = "Você atirou em " + frase(i, r, "eu");
    if (venceu(e.ele)) { e.fim = "vitoria"; e.ultimo = msg; return { msg: msg + " Você afundou toda a frota inimiga. Vitória!", fim: true }; }
    msg += " " + jogadaComputador(e);
    if (!e.fim) msg += " Sua vez.";
    e.ultimo = msg;
    return { msg: msg, fim: !!e.fim };
  }
  function desenho(lado, mostrarNavios) {
    var l = ["   " + COLS.split("").join(" ")], r, c;
    for (r = 0; r < N; r++) {
      var s = (r + 1 < 10 ? " " : "") + (r + 1) + " ";
      for (c = 0; c < N; c++) { var i = r * N + c, v = lado.tiros[i]; s += (v === 1 ? "o" : v >= 2 ? "X" : mostrarNavios && lado.grade[i] >= 0 ? "#" : ".") + " "; }
      l.push(s);
    }
    return l.join("\n");
  }

  var api = { N: N, FROTA: FROTA, NIVEIS: NIVEIS, novo: novo, casa: casa, nome: nome, receber: receber, venceu: venceu, escolherTiro: escolherTiro, jogadaComputador: jogadaComputador, comando: comando,
    lerLinha: lerLinha, lerColuna: lerColuna, lerFrota: lerFrota, lerRestantes: lerRestantes, lerTiros: lerTiros, lerTirosInimigos: lerTirosInimigos, dica: dica, desenho: desenho, frotaAleatoria: frotaAleatoria, densidade: densidade };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = null;
  var selNivel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { return H.el("option", { value: k, texto: NIVEIS[k].charAt(0).toUpperCase() + NIVEIS[k].slice(1) }); }));
  selNivel.value = "normal";
  var novoBtn = H.el("button", { type: "button", texto: "Nova partida" });
  var campo = H.el("input", { id: "tiro", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "tiro", texto: "Sua casa de tiro, como B7, ou um comando (ajuda mostra tudo)" }), campo, H.el("button", { type: "submit", texto: "Atirar" })]);
  var historia = H.el("ol", { id: "historico", "aria-label": "Histórico da partida" });
  var visual = H.el("pre", { id: "visual", "aria-hidden": "true" });
  [H.el("label", { "for": "nivel", texto: "Nível do computador (vale ao começar uma nova partida)" }), selNivel, novoBtn, form, historia, visual].forEach(function (x) { jogo.appendChild(x); });
  function escrever(m) { historia.insertBefore(H.el("li", { texto: m }), historia.firstChild); H.anunciar(m); }
  function atualizar() { visual.textContent = "Seus tiros\n" + desenho(e.ele, false) + "\n\nSua frota\n" + desenho(e.eu, true); }
  function comecar() {
    e = novo(selNivel.value); historia.textContent = ""; campo.disabled = false; atualizar();
    escrever("Nova batalha, nível " + NIVEIS[e.nivel] + ". As duas frotas foram posicionadas: porta-aviões (5), encouraçado (4), cruzador (3), submarino (3) e destróier (2). Digite frota para ouvir onde estão os seus navios. Para atirar, diga uma casa, como B7.");
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
