// Labirinto: você anda por corredores até achar a saída. O jogo descreve as passagens de cada lugar; o som ajuda a se orientar
// (passos, batida na parede e um farol que ecoa do lado e na distância da saída). Cada labirinto é sorteado e tem um único caminho certo.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", l: 6, c: 6, fala: "tudo", farol: 999, dicas: 999 },
    normal: { nome: "normal", l: 9, c: 9, fala: "cruzamentos", farol: 8, dicas: 4 },
    dificil: { nome: "difícil", l: 12, c: 12, fala: "nada", farol: 3, dicas: 1 }
  };
  var DIR = { norte: [-1, 0], sul: [1, 0], leste: [0, 1], oeste: [0, -1] }, OPOSTO = { norte: "sul", sul: "norte", leste: "oeste", oeste: "leste" };
  var ABREV = { n: "norte", s: "sul", l: "leste", o: "oeste", cima: "norte", baixo: "sul", direita: "leste", esquerda: "oeste", este: "leste", frente: "norte", tras: "sul" };
  var LADOS = ["norte", "sul", "leste", "oeste"], OCTANTES = ["leste", "nordeste", "norte", "noroeste", "oeste", "sudoeste", "sul", "sudeste"];

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function idx(e, l, c) { return (l - 1) * e.c + (c - 1); }
  function lc(e, i) { return [Math.floor(i / e.c) + 1, (i % e.c) + 1]; }
  function vizinho(e, i, d) { var p = lc(e, i), l = p[0] + DIR[d][0], c = p[1] + DIR[d][1]; return l >= 1 && l <= e.l && c >= 1 && c <= e.c ? idx(e, l, c) : -1; }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k], r = rnd || sorteio, i;
    var e = { nivel: k, nome: n.nome, l: n.l, c: n.c, aberto: [], pos: 0, saida: n.l * n.c - 1, passos: 0, fim: null, farol: n.farol, dicas: n.dicas, rnd: r };
    for (i = 0; i < n.l * n.c; i++) e.aberto.push({ norte: false, sul: false, leste: false, oeste: false });
    // Labirinto perfeito por busca em profundidade: todas as casas se ligam e há um só caminho entre duas quaisquer.
    var vis = {}, pilha = [0]; vis[0] = true;
    while (pilha.length) {
      var a = pilha[pilha.length - 1], op = LADOS.filter(function (d) { var j = vizinho(e, a, d); return j >= 0 && !vis[j]; });
      if (!op.length) { pilha.pop(); continue; }
      var d = op[r(op.length)], j = vizinho(e, a, d); e.aberto[a][d] = true; e.aberto[j][OPOSTO[d]] = true; vis[j] = true; pilha.push(j);
    }
    return e;
  }
  function passagens(e, i) { return LADOS.filter(function (d) { return e.aberto[i][d]; }); }
  function lista(a) { return a.length <= 1 ? a.join("") : a.slice(0, -1).join(", ") + " e " + a[a.length - 1]; }
  // Menor caminho até a saída (busca em largura): devolve a primeira direção e o tamanho.
  function caminho(e, de) {
    var ant = {}, fila = [de], i; ant[de] = -1;
    while (fila.length) {
      var a = fila.shift(); if (a === e.saida) break;
      passagens(e, a).forEach(function (d) { var j = vizinho(e, a, d); if (!(j in ant)) { ant[j] = a; fila.push(j); } });
    }
    var n = 0, atual = e.saida, prox = e.saida; while (ant[atual] !== -1 && atual !== de) { prox = atual; atual = ant[atual]; n++; }
    var dir = LADOS.filter(function (d) { return vizinho(e, de, d) === prox; })[0];
    return { passos: n, dir: de === e.saida ? null : dir };
  }
  function olhar(e) {
    var ps = passagens(e, e.pos), p = lc(e, e.pos);
    if (e.pos === e.saida) return "Você está na saída!";
    if (ps.length === 1) return "Beco sem saída na linha " + p[0] + ", coluna " + p[1] + ". Só dá para voltar ao " + ps[0] + ".";
    return "Passagens: " + lista(ps) + ".";
  }
  function onde(e) {
    var p = lc(e, e.pos); return "Você está na linha " + p[0] + ", coluna " + p[1] + " de um labirinto de " + e.l + " por " + e.c + ". A saída fica no canto de baixo à direita. " + olhar(e);
  }
  // Descrição automática depois de um passo, conforme o nível: fácil sempre; normal só em cruzamentos, curvas e becos; difícil nunca.
  function auto(e, veio) {
    var f = NIVEIS[e.nivel].fala, ps = passagens(e, e.pos);
    if (f === "tudo") return " " + olhar(e);
    if (f === "cruzamentos") {
      var reto = ps.length === 2 && ps[0] === OPOSTO[ps[1]];
      return reto ? "" : " " + olhar(e);
    }
    return ps.length === 1 && e.pos !== e.saida ? " Beco sem saída." : "";
  }
  function andar(e, d, vezes) {
    if (e.fim) return { msg: "O jogo terminou. Comece um novo." };
    var n = Math.max(1, Math.min(vezes || 1, 40)), k = 0;
    while (k < n) {
      if (!e.aberto[e.pos][d]) break;
      e.pos = vizinho(e, e.pos, d); k++; e.passos++;
      if (e.pos === e.saida) break;
      if (k < n && passagens(e, e.pos).length !== 2) break; // numa bifurcação ou beco, a caminhada para
    }
    if (!k) return { msg: "Parede ao " + d + ". " + olhar(e), erro: true, batida: true };
    if (e.pos === e.saida) {
      e.fim = "ganhou"; var otimo = caminho(e, 0).passos;
      return { msg: "Você chegou à saída! Foram " + plural(e.passos, "passo", "passos") + "; o caminho mais curto tinha " + otimo + "." + (e.passos <= otimo + 2 ? " Excelente!" : e.passos <= otimo * 2 ? " Muito bom." : " Você explorou bastante, e isso também vale."), fim: "ganhou" };
    }
    return { msg: "Você foi " + plural(k, "casa", "casas") + " ao " + d + "." + auto(e, d), passos: k };
  }
  // Corre pelo corredor: segue em frente até uma bifurcação, um beco ou a saída.
  function correr(e, d) {
    if (e.fim) return { msg: "O jogo terminou. Comece um novo." };
    return andar(e, d, 40);
  }
  function direcao(dl, dc) { var ang = Math.atan2(-dl, dc) * 180 / Math.PI, i = Math.round(ang / 45); return OCTANTES[((i % 8) + 8) % 8]; }
  function farol(e) {
    if (e.fim) return { msg: "O jogo terminou." };
    if (e.farol <= 0) return { msg: "O farol está sem energia neste nível.", erro: true };
    if (e.farol < 100) e.farol--;
    var p = lc(e, e.pos), s = lc(e, e.saida), dl = s[0] - p[0], dc = s[1] - p[1], d = Math.sqrt(dl * dl + dc * dc), resto = e.farol < 100 ? " Usos do farol restantes: " + e.farol + "." : "";
    if (d === 0) return { msg: "Você está na saída." };
    return { msg: "Farol: a saída está a cerca de " + plural(Math.max(1, Math.round(d)), "casa", "casas") + " em linha reta, ao " + direcao(dl, dc) + ". Os corredores podem dar voltas." + resto, dl: dl, dc: dc, dist: d, alcance: Math.sqrt(e.l * e.l + e.c * e.c) };
  }
  function dica(e) {
    if (e.fim) return { msg: "O jogo terminou." };
    if (e.dicas <= 0) return { msg: NIVEIS[e.nivel].dicas === 0 ? "Neste nível não há dicas." : "As dicas acabaram.", erro: true };
    if (e.dicas < 100) e.dicas--;
    var c = caminho(e, e.pos), resto = e.dicas < 100 ? " Dicas restantes: " + e.dicas + "." : "";
    return { msg: "Dica: daqui, o caminho mais curto até a saída tem " + plural(c.passos, "passo", "passos") + ", e começa indo ao " + c.dir + "." + resto };
  }
  function resumo(e) {
    var s = "Nível " + e.nome + ", labirinto de " + e.l + " por " + e.c + ". Passos: " + e.passos + ". " + (e.farol < 100 ? "Farol: " + e.farol + ". " : "") + (e.dicas < 100 ? "Dicas: " + e.dicas + "." : "");
    if (e.fim === "ganhou") s += " Você chegou à saída."; return s.trim();
  }
  function ajuda() {
    return "Comandos: norte, sul, leste, oeste (ou n, s, l, o), e com um número anda várias casas, por exemplo leste 3; a caminhada para numa bifurcação. correr leste segue pelo corredor até uma bifurcação, um beco ou a saída. olhar diz as passagens do lugar onde você está. farol diz a direção e a distância em linha reta até a saída, mas os corredores dão voltas. dica diz o primeiro passo do caminho mais curto. onde diz a sua posição, resumo diz os passos e o que resta. Você começa no canto de cima à esquerda e a saída fica no canto de baixo à direita. No som: passos ao andar, uma batida grave na parede, e o farol ecoa do lado da saída, mais demorado quanto mais longe, e mais agudo quando ela está ao norte. Atalhos: setas andam.";
  }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: leste, olhar ou ajuda." };
    if (v === "ir" || v === "andar" || v === "mover") { p.shift(); v = p[0] || ""; }
    if (v === "correr" || v === "seguir") { var dc = ABREV[p[1]] || p[1]; return DIR[dc] ? correr(e, dc) : { msg: "Correr para onde? Exemplo: correr leste.", erro: true }; }
    var d = DIR[v] ? v : ABREV[v];
    if (d) return andar(e, d, Number((p[1] || "").replace(/\D/g, "")) || 1);
    if (v === "olhar" || v === "ver" || v === "passagens") return { msg: olhar(e) };
    if (v === "farol" || v === "saida") return farol(e);
    if (v === "dica") return dica(e);
    if (v === "onde" || v === "posicao") return { msg: onde(e) };
    if (v === "resumo" || v === "status" || v === "placar") return { msg: resumo(e) };
    if (v === "ajuda") return { msg: ajuda() };
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, novo: novo, andar: andar, correr: correr, olhar: olhar, farol: farol, dica: dica, caminho: caminho, passagens: passagens, comando: comando, resumo: resumo, onde: onde, direcao: direcao };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  function D(m, f) { if (H.som) H.som.dizer("labirinto", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + ": " + n.l + " por " + n.c + (k === "facil" ? ", descreve as passagens a cada passo" : k === "normal" ? ", descreve só cruzamentos e becos" : ", só diz o que você pedir") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (norte, sul, leste, oeste, leste 3, correr leste, olhar, farol, dica, onde, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  function btn(txt, cmd) { var b = H.el("button", { type: "button", texto: txt }); b.addEventListener("click", function () { agir(cmd); }); return b; }
  var mover4 = H.el("div", { role: "group", "aria-label": "Andar" }, [btn("Norte", "norte"), btn("Sul", "sul"), btn("Leste", "leste"), btn("Oeste", "oeste")]);
  var acoes = H.el("div", { role: "group", "aria-label": "Consultas" }, [btn("Olhar", "olhar"), btn("Farol", "farol"), btn("Dica", "dica"), btn("Onde estou", "onde"), btn("Resumo", "resumo"), btn("Ajuda", "ajuda")]);
  var novoBtn = H.el("button", { type: "button", texto: "Novo labirinto" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, form, mover4, acoes].forEach(function (x) { jogo.appendChild(x); });
  function agir(cmd) {
    var r = comando(e, cmd), som = H.som;
    if (r.dist !== undefined && som && som.eco) som.falarApos(som.eco(r.dc, -r.dl, r.dist, r.alcance), r.msg);
    else D(r.msg);
    campo.disabled = !!e.fim;
  }
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo labirinto, nível " + e.nome + ", de " + e.l + " por " + e.c + ". Você está no canto de cima à esquerda e a saída fica no canto de baixo à direita. " + olhar(e) + " Use as setas ou os botões para andar."); }
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var c = campo.value; campo.value = ""; agir(c); if (!e.fim) campo.focus(); });
  document.addEventListener("keydown", function (ev) {
    var t = ev.target && ev.target.tagName, noCampo = ev.target === campo;
    if (t === "SELECT" || t === "TEXTAREA" || (t === "INPUT" && !noCampo)) return;
    var cmd = { ArrowUp: "norte", ArrowDown: "sul", ArrowRight: "leste", ArrowLeft: "oeste" }[ev.key];
    if (cmd) { ev.preventDefault(); agir(cmd); }
  });
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
