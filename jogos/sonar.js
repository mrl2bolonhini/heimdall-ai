// Sonar: você comanda um navio caça-submarinos num mar quadriculado. Os submarinos estão escondidos. O sonar (ping) diz a que distância e em que
// direção está o submarino mais próximo, mas só de modo aproximado: para achar a posição certa é preciso pingar de lugares diferentes.
// Quando estiver sobre o submarino, lance uma carga de profundidade. O som ajuda: o eco demora mais quanto mais longe, vem do lado da direção e é mais agudo ao norte.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", l: 8, c: 8, subs: 1, pings: 20, cargas: 6, move: false },
    normal: { nome: "normal", l: 10, c: 10, subs: 2, pings: 20, cargas: 6, move: false },
    dificil: { nome: "difícil", l: 12, c: 12, subs: 3, pings: 25, cargas: 7, move: true }
  };
  var DIR = { norte: [-1, 0], sul: [1, 0], leste: [0, 1], oeste: [0, -1] };
  var ABREV = { n: "norte", s: "sul", l: "leste", o: "oeste", cima: "norte", baixo: "sul", direita: "leste", esquerda: "oeste", este: "leste" };
  var OCTANTES = ["leste", "nordeste", "norte", "noroeste", "oeste", "sudoeste", "sul", "sudeste"];

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k], r = rnd || sorteio;
    var e = { nivel: k, nome: n.nome, l: n.l, c: n.c, rnd: r, lin: Math.floor(n.l / 2) + 1, col: Math.floor(n.c / 2) + 1, subs: [], pings: n.pings, cargas: n.cargas,
      usouPings: 0, usouCargas: 0, afundados: 0, total: n.subs, fim: null, passos: 0 };
    while (e.subs.length < n.subs) {
      var s = { l: r(n.l) + 1, c: r(n.c) + 1 };
      if ((s.l === e.lin && s.c === e.col) || e.subs.some(function (x) { return x.l === s.l && x.c === s.c; })) continue;
      e.subs.push(s);
    }
    return e;
  }
  function direcao(dl, dc) { // dl cresce para o sul, dc cresce para o leste
    var ang = Math.atan2(-dl, dc) * 180 / Math.PI, i = Math.round(ang / 45); return OCTANTES[((i % 8) + 8) % 8];
  }
  function maisProximo(e) {
    var melhor = null;
    e.subs.forEach(function (s) {
      var dl = s.l - e.lin, dc = s.c - e.col, d = Math.sqrt(dl * dl + dc * dc);
      if (!melhor || d < melhor.d) melhor = { d: d, dl: dl, dc: dc };
    });
    return melhor;
  }
  function restam(e) { return plural(e.subs.length, "submarino", "submarinos"); }
  function onde(e) {
    return "Você está na linha " + e.lin + ", coluna " + e.col + " de um mar de " + e.l + " por " + e.c + ". Linha 1 é o norte e coluna 1 é o oeste.";
  }
  function mover(e, d, vezes) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    var v = DIR[d], n = Math.max(1, Math.min(vezes || 1, 20)), k = 0;
    while (k < n) {
      var l = e.lin + v[0], c = e.col + v[1];
      if (l < 1 || l > e.l || c < 1 || c > e.c) break;
      e.lin = l; e.col = c; k++; e.passos++;
    }
    if (!k) return { msg: "Fim do mapa: não há mar ao " + d + ".", erro: true };
    return { msg: "Você foi " + plural(k, "casa", "casas") + " ao " + d + (k < n ? ", até a borda" : "") + ". Agora na linha " + e.lin + ", coluna " + e.col + ".", passos: k };
  }
  function derivar(e) { // no nível difícil, os submarinos se mexem um pouco depois de cada ping
    e.subs.forEach(function (s) {
      var d = [[-1, 0], [1, 0], [0, 1], [0, -1], [0, 0]][e.rnd(5)], l = s.l + d[0], c = s.c + d[1];
      if (l >= 1 && l <= e.l && c >= 1 && c <= e.c) { s.l = l; s.c = c; }
    });
  }
  function ping(e) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    if (e.pings <= 0) return { msg: "O sonar está sem energia: acabaram os pings. Você ainda pode lançar cargas.", erro: true };
    e.pings--; e.usouPings++;
    var m = maisProximo(e), alcance = Math.sqrt(e.l * e.l + e.c * e.c), resto = " Pings restantes: " + e.pings + ".";
    if (NIVEIS[e.nivel].move) derivar(e);
    if (m.d === 0) return { msg: "Eco muito forte: há um submarino bem embaixo de você. Lance a carga!" + resto, dist: 0, dl: 0, dc: 0, alcance: alcance };
    var q = Math.max(1, Math.round(m.d));
    return { msg: "Eco: o submarino mais próximo está a cerca de " + plural(q, "casa", "casas") + ", ao " + direcao(m.dl, m.dc) + "." + resto, dist: m.d, dl: m.dl, dc: m.dc, alcance: alcance };
  }
  function lancar(e) {
    if (e.fim) return { msg: "A partida terminou. Comece um novo jogo." };
    if (e.cargas <= 0) return { msg: "Você não tem mais cargas.", erro: true };
    e.cargas--; e.usouCargas++;
    var i = -1; e.subs.forEach(function (s, j) { if (s.l === e.lin && s.c === e.col) i = j; });
    if (i >= 0) {
      e.subs.splice(i, 1); e.afundados++;
      if (!e.subs.length) { e.fim = "ganhou"; return { msg: "Boom! Você afundou um submarino. Você afundou toda a frota. Vitória! Foram " + plural(e.usouCargas, "carga", "cargas") + " e " + plural(e.usouPings, "ping", "pings") + ".", acerto: true, fim: "ganhou" }; }
      return { msg: "Boom! Você afundou um submarino. Restam " + restam(e) + ". Cargas restantes: " + e.cargas + ".", acerto: true };
    }
    if (e.cargas === 0) { e.fim = "perdeu"; return { msg: "A carga explodiu no fundo, sem acertar nada. Acabaram as cargas, e ainda restavam " + restam(e) + ". Fim de jogo.", fim: "perdeu" }; }
    return { msg: "A carga explodiu no fundo, sem acertar nada. Cargas restantes: " + e.cargas + ".", acerto: false };
  }
  function resumo(e) {
    var s = "Nível " + e.nome + ", mar de " + e.l + " por " + e.c + ". " + onde(e).split(".")[0] + ". Submarinos afundados: " + e.afundados + " de " + e.total + ". Pings restantes: " + e.pings + ". Cargas restantes: " + e.cargas + ".";
    if (e.fim === "ganhou") s += " Você ganhou."; if (e.fim === "perdeu") s += " Você perdeu.";
    return s;
  }
  function ajuda() {
    return "Comandos: norte, sul, leste, oeste (ou n, s, l, o), e com um número anda várias casas, por exemplo leste 3. ping manda o sonar, que diz a que distância e em que direção está o submarino mais próximo, só de modo aproximado. lançar solta uma carga de profundidade na casa onde você está, e só acerta se o submarino estiver exatamente ali. onde diz a sua posição, resumo diz o placar. Para achar um submarino, pingue de lugares diferentes e cruze as direções. No som, o eco demora mais quando o alvo está longe, vem do lado onde ele está e é mais agudo quando ele está ao norte. Atalhos de teclado: setas movem, a letra P pinga e a letra L lança.";
  }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: leste, ping, lançar ou ajuda." };
    if (v === "ir" || v === "andar" || v === "mover") { p.shift(); v = p[0] || ""; }
    var d = DIR[v] ? v : ABREV[v];
    if (d) return mover(e, d, Number((p[1] || "").replace(/\D/g, "")) || 1);
    if (v === "ping" || v === "sonar" || v === "p") return ping(e);
    if (v === "lancar" || v === "carga" || v === "bomba" || v === "l" || v === "soltar") return lancar(e);
    if (v === "onde" || v === "posicao") return { msg: onde(e) };
    if (v === "resumo" || v === "status" || v === "placar") return { msg: resumo(e) };
    if (v === "ajuda") return { msg: ajuda() };
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, novo: novo, mover: mover, ping: ping, lancar: lancar, comando: comando, direcao: direcao, resumo: resumo, onde: onde, maisProximo: maisProximo };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  function D(m, f) { if (H.som) H.som.dizer("sonar", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + ": mar de " + n.l + " por " + n.c + ", " + plural(n.subs, "submarino", "submarinos") + (n.move ? ", que se movem" : "") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (norte, sul, leste, oeste, leste 3, ping, lançar, onde, resumo, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  function btn(txt, cmd) { var b = H.el("button", { type: "button", texto: txt }); b.addEventListener("click", function () { agir(cmd); }); return b; }
  var mover4 = H.el("div", { role: "group", "aria-label": "Mover o navio" }, [btn("Norte", "norte"), btn("Sul", "sul"), btn("Leste", "leste"), btn("Oeste", "oeste")]);
  var acoes = H.el("div", { role: "group", "aria-label": "Ações" }, [btn("Ping do sonar", "ping"), btn("Lançar carga", "lancar"), btn("Onde estou", "onde"), btn("Placar", "resumo"), btn("Ajuda", "ajuda")]);
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, form, mover4, acoes].forEach(function (x) { jogo.appendChild(x); });
  function agir(cmd) {
    var r = comando(e, cmd), som = H.som;
    if (r.dist !== undefined && som && som.eco) { som.falarApos(som.eco(r.dc, -r.dl, r.dist, r.alcance), r.msg); }
    else if (r.acerto !== undefined && som) { som.anunciar(r.acerto ? ["tiro", "afundou"] : "agua", r.msg); }
    else D(r.msg);
    campo.disabled = !!e.fim;
  }
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo jogo, nível " + e.nome + ": mar de " + e.l + " por " + e.c + " com " + plural(e.total, "submarino escondido", "submarinos escondidos") + ". " + onde(e) + " Você tem " + e.pings + " pings e " + e.cargas + " cargas. Mande um ping para começar a procurar."); }
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var c = campo.value; campo.value = ""; agir(c); if (!e.fim) campo.focus(); });
  // Setas movem o navio; P pinga e L lança, com o foco fora de seletores e campos de texto (no campo de comando, as setas também valem).
  document.addEventListener("keydown", function (ev) {
    var t = ev.target && ev.target.tagName, noCampo = ev.target === campo;
    if (t === "SELECT" || t === "TEXTAREA" || (t === "INPUT" && !noCampo)) return;
    var cmd = { ArrowUp: "norte", ArrowDown: "sul", ArrowRight: "leste", ArrowLeft: "oeste" }[ev.key];
    if (!cmd && !noCampo && !ev.metaKey && !ev.ctrlKey && !ev.altKey) cmd = { p: "ping", P: "ping", l: "lancar", L: "lancar" }[ev.key];
    if (cmd) { ev.preventDefault(); agir(cmd); }
  });
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
