// Vilarejo Sitiado: tiro e exploração guiados pelo som, com visual de arcade dos anos 80 para quem enxerga.
// Bandidos tomaram o vilarejo. Você anda pelos quatro pontos cardeais (W norte, D leste, S sul, A oeste), olha na direção do último passo e mira
// com as setas (a mira começa no centro e volta ao centro quando você anda). O som mostra onde cada inimigo está (estéreo) e se a mira está sobre ele.
// A lógica abaixo não depende de som nem de tela: tudo o que acontece vira texto, para o leitor de tela, e os testes rodam sem navegador.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", hp: 30, mult: 0.6, tick: 800, acerto: 0.35 },
    normal: { nome: "normal", hp: 20, mult: 1, tick: 650, acerto: 0.5 },
    dificil: { nome: "difícil", hp: 14, mult: 1.3, tick: 520, acerto: 0.6 }
  };
  var LARG = 30, ALT = 16, ALCANCE = 7, KIT = 8;
  var DIRS = { norte: [0, -1], leste: [1, 0], sul: [0, 1], oeste: [-1, 0] };
  var ARMAS = {
    revolver: { nome: "revólver", tecla: 1, dano: 3, cap: 6, municao: true },
    espingarda: { nome: "espingarda", tecla: 2, dano: 5, cap: 2, municao: true },
    faca: { nome: "faca", tecla: 3, dano: 3, melee: true },
    mao: { nome: "mão livre", tecla: 4, dano: 1, melee: true }
  };
  var POR_TECLA = { 1: "revolver", 2: "espingarda", 3: "faca", 4: "mao" };
  // vel: o inimigo age a cada vel passos de tempo. linha: -1 é baixo (animais), 0 é na altura do peito. dist: o atirador para a essa distância.
  var TIPOS = {
    rato: { nome: "rato", art: "um", hp: 2, dano: 1, vel: 1, linha: -1, alerta: 5 },
    cao: { nome: "cão selvagem", art: "um", hp: 4, dano: 2, vel: 1, linha: -1, alerta: 5 },
    bandido: { nome: "bandido", art: "um", hp: 5, dano: 2, vel: 2, linha: 0, alerta: 7, atira: true, dist: 3 },
    capanga: { nome: "capanga", art: "um", hp: 7, dano: 2, vel: 2, linha: 0, alerta: 7, atira: true, dist: 3 },
    chefe: { nome: "chefe dos bandidos", art: "o", hp: 12, dano: 3, vel: 2, linha: 0, alerta: 8, atira: true, dist: 2, chefe: true }
  };
  // Mapa do térreo. # parede, T árvore, ~ riacho, = ponte, . rua, g grama, , plantação, _ chão de dentro, D porta, L porta trancada, ^ escada para cima, v para baixo.
  var ANDAR0 = [
    "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTT",
    "T,,,,,,,,,~~g#######gg#######T",
    "T,,,,,,,,,~~g#_____#gg#_____#T",
    "T,,,,,,,,,~~g#_____#gg#_____#T",
    "T,,,,,,,,,~~g#_____#gg#_____#T",
    "T,,,,,,,,,~~g###D###gg###D###T",
    "Tggggggggg~~.................T",
    "Tggggggggg==.................T",
    "T.........==.................T",
    "Tggggggggg~~.................T",
    "Tg##D##ggg~~g###L###gg###L###T",
    "Tg#___#ggg~~g#_____#gg#_____#T",
    "Tg#___#ggg~~g#__^__#gg#_____#T",
    "Tg#####ggg~~g#_____#gg#_____#T",
    "Tggggggggg~~g#######gg#######T",
    "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTT"
  ];
  var TRANCADAS = { "0,16,10": "chave da delegacia", "0,25,10": "chave da prefeitura" };
  var ITENS0 = [
    { a: 0, x: 5, y: 12, tipo: "chave", nome: "chave da delegacia" },
    { a: 0, x: 3, y: 11, tipo: "kit", nome: "kit médico" },
    { a: 0, x: 3, y: 12, tipo: "municao", arma: "revolver", qtd: 12, nome: "12 balas de revólver" },
    { a: 0, x: 16, y: 2, tipo: "kit", nome: "kit médico" },
    { a: 0, x: 14, y: 3, tipo: "municao", arma: "revolver", qtd: 6, nome: "6 balas de revólver" },
    { a: 0, x: 23, y: 2, tipo: "kit", nome: "kit médico" },
    { a: 0, x: 27, y: 4, tipo: "kit", nome: "kit médico" },
    { a: 0, x: 25, y: 2, tipo: "municao", arma: "espingarda", qtd: 4, nome: "4 cartuchos de espingarda" },
    { a: 0, x: 18, y: 13, tipo: "municao", arma: "revolver", qtd: 6, nome: "6 balas de revólver" },
    { a: 1, x: 14, y: 11, tipo: "arma", arma: "espingarda", qtd: 4, nome: "espingarda, com 4 cartuchos" },
    { a: 1, x: 18, y: 11, tipo: "municao", arma: "espingarda", qtd: 4, nome: "4 cartuchos de espingarda" },
    { a: 1, x: 18, y: 13, tipo: "chave", nome: "chave da prefeitura" },
    { a: 0, x: 23, y: 13, tipo: "kit", nome: "kit médico" }
  ];
  var INIM0 = [
    { t: "rato", a: 0, x: 5, y: 11 }, { t: "cao", a: 0, x: 3, y: 2 },
    { t: "bandido", a: 0, x: 16, y: 7 }, { t: "bandido", a: 0, x: 22, y: 8 }, { t: "cao", a: 0, x: 20, y: 8 },
    { t: "rato", a: 0, x: 15, y: 4 }, { t: "bandido", a: 0, x: 24, y: 3 },
    { t: "bandido", a: 0, x: 15, y: 12 }, { t: "bandido", a: 1, x: 15, y: 12 },
    { t: "capanga", a: 0, x: 24, y: 12 }, { t: "chefe", a: 0, x: 26, y: 12 }
  ];
  var INICIO = { a: 0, x: 8, y: 8, dir: "leste" };

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function ev(t, msg, n, extra) { var o = { t: t, msg: msg || "", n: n || 1 }; if (extra) Object.keys(extra).forEach(function (k) { o[k] = extra[k]; }); return o; }
  function andares() {
    var a0 = ANDAR0.map(function (r) { return r.split(""); }), a1 = [], x, y;
    for (y = 0; y < ALT; y++) { var l = []; for (x = 0; x < LARG; x++) l.push("#"); a1.push(l); }
    for (y = 11; y <= 13; y++) for (x = 14; x <= 18; x++) a1[y][x] = "_";
    a1[12][16] = "v";
    return [a0, a1];
  }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "normal", n = NIVEIS[k];
    var e = {
      nivel: k, nome: n.nome, rnd: rnd || sorteio, mapa: andares(), andar: INICIO.a, x: INICIO.x, y: INICIO.y, dir: INICIO.dir, mx: 0, my: 0,
      hp: n.hp, hpMax: n.hp, arma: "revolver", armas: { revolver: true, faca: true, mao: true, espingarda: false },
      mun: { revolver: { carga: 6, reserva: 12 }, espingarda: { carga: 0, reserva: 0 } }, kits: 0, chaves: [], abertas: {}, recarga: 0, recargaArma: "",
      itens: ITENS0.map(function (i) { return Object.assign({}, i); }), inimigos: [], t: 0, passos: 0, mortos: 0, tiros: 0, acertos: 0, fim: null, area: ""
    };
    INIM0.forEach(function (s) { var tp = TIPOS[s.t]; e.inimigos.push({ t: s.t, a: s.a, x: s.x, y: s.y, hp: tp.hp, ativo: false, cool: 0, visto: false }); });
    e.area = areaDe(e.andar, e.x, e.y);
    return e;
  }
  function tile(e, a, x, y) { return x < 0 || y < 0 || x >= LARG || y >= ALT ? "#" : e.mapa[a][y][x]; }
  function ch(a, x, y) { return a + "," + x + "," + y; }
  function aberta(e, a, x, y) { return !!e.abertas[ch(a, x, y)]; }
  function passavel(e, a, x, y) {
    var c = tile(e, a, x, y);
    if (c === "#" || c === "T" || c === "~") return false;
    if (c === "D" || c === "L") return aberta(e, a, x, y);
    return true;
  }
  function transparente(e, a, x, y) {
    var c = tile(e, a, x, y);
    if (c === "#" || c === "T") return false;
    if (c === "D" || c === "L") return aberta(e, a, x, y);
    return true;
  }
  function inimigoEm(e, a, x, y) {
    for (var i = 0; i < e.inimigos.length; i++) { var m = e.inimigos[i]; if (m.hp > 0 && m.a === a && m.x === x && m.y === y) return m; }
    return null;
  }
  function areaDe(a, x, y) {
    if (a === 1) return "andar de cima da delegacia";
    if (x >= 13 && x <= 19 && y >= 1 && y <= 5) return "igreja";
    if (x >= 22 && x <= 28 && y >= 1 && y <= 5) return "hospital";
    if (x >= 13 && x <= 19 && y >= 10 && y <= 14) return "delegacia";
    if (x >= 22 && x <= 28 && y >= 10 && y <= 14) return "prefeitura";
    if (x >= 2 && x <= 6 && y >= 10 && y <= 13) return "casa do fazendeiro";
    if (x >= 10 && x <= 11) return "ponte do riacho";
    if (x <= 9 && y <= 4) return "plantação";
    if (x <= 9) return "margem oeste do riacho";
    return "rua do vilarejo";
  }
  // Posição de um ponto em relação a quem olha: f é quanto à frente (negativo, atrás) e s quanto à direita (negativo, à esquerda).
  function relativo(e, x, y) {
    var d = DIRS[e.dir], dx = x - e.x, dy = y - e.y;
    return { f: dx * d[0] + dy * d[1], s: dx * -d[1] + dy * d[0] };
  }
  function coluna(f, s) { var c = Math.min(3, Math.round(Math.abs(s) / f * 3)); return s < 0 ? -c : c; }
  function clara(e, a, x0, y0, x1, y1) {
    var n = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)), i;
    for (i = 1; i < n; i++) if (!transparente(e, a, Math.round(x0 + (x1 - x0) * i / n), Math.round(y0 + (y1 - y0) * i / n))) return false;
    return true;
  }
  // O que está à vista na direção em que você olha: cone de 45 graus para cada lado, até 7 passos, sem paredes ou portas fechadas no meio.
  function visiveis(e) {
    var r = [];
    e.inimigos.forEach(function (m) {
      if (m.hp <= 0 || m.a !== e.andar) return;
      var p = relativo(e, m.x, m.y);
      if (p.f < 1 || p.f > ALCANCE || Math.abs(p.s) > p.f || !clara(e, e.andar, e.x, e.y, m.x, m.y)) return;
      r.push({ m: m, f: p.f, s: p.s, col: coluna(p.f, p.s), linha: TIPOS[m.t].linha });
    });
    return r.sort(function (a, b) { return a.f - b.f; });
  }
  function ladoTxt(f, s) {
    if (f < 0 && Math.abs(s) <= -f) return "atrás de você";
    if (f >= 1 && Math.abs(s) * 3 <= f) return "à frente";
    return s < 0 ? "à esquerda" : "à direita";
  }
  function distTxt(f, s) { var d = Math.max(Math.abs(f), Math.abs(s)); return plural(d, "passo", "passos"); }
  function nomeInim(m, caixa) { var t = TIPOS[m.t]; return (caixa ? "O " : "o ") + t.nome; }
  function dica(e, v) {
    var dc = v.col - e.mx, dl = v.linha - e.my, p = [];
    if (dc) p.push(plural(Math.abs(dc), "coluna", "colunas") + (dc < 0 ? " à esquerda" : " à direita"));
    if (dl) p.push((dl > 0 ? "mais acima" : "mais abaixo") + (Math.abs(dl) > 1 ? " ainda" : ""));
    return p.length ? "O " + TIPOS[v.m.t].nome + " está " + p.join(" e ") + " da mira." : "";
  }

  // ---- ações do jogador ----
  function chegada(e, evs) {
    var a = areaDe(e.andar, e.x, e.y);
    if (a !== e.area) { e.area = a; evs.push(ev("area", "Você entrou na " + a + ".", 1, { c: a.charAt(0).toUpperCase() + a.slice(1) + "." })); }
    var aqui = e.itens.filter(function (i) { return i.a === e.andar && i.x === e.x && i.y === e.y; });
    if (aqui.length) evs.push(ev("item", "Aqui há: " + aqui.map(function (i) { return i.nome; }).join(", ") + ". Aperte x para pegar.", 1, { c: "Item: " + aqui[0].nome + "." }));
    var c = tile(e, e.andar, e.x, e.y);
    if (c === "^") evs.push(ev("escada", "Escada para cima. Aperte x para subir.", 1, { c: "Escada para cima." }));
    if (c === "v") evs.push(ev("escada", "Escada para baixo. Aperte x para descer.", 1, { c: "Escada para baixo." }));
  }
  function mover(e, d) {
    var evs = [];
    if (e.fim) return evs;
    var v = DIRS[d], nx = e.x + v[0], ny = e.y + v[1], c = tile(e, e.andar, nx, ny), m = inimigoEm(e, e.andar, nx, ny);
    e.dir = d;
    if (m) { evs.push(ev("bloqueio", nomeInim(m, true) + " bloqueia o caminho, à frente.", 1, { c: "Bloqueado." })); return evs; }
    if (!passavel(e, e.andar, nx, ny)) {
      var msg = c === "D" ? "Porta fechada à frente (" + d + "). Aperte x para abrir." : c === "L" ? "Porta trancada à frente (" + d + "). Aperte x para tentar abrir." : c === "~" ? "O riacho, fundo demais, bloqueia o caminho a " + d + ". Procure a ponte." : c === "T" ? "Árvores fechadas a " + d + "." : "Parede a " + d + ".";
      evs.push(ev("bloqueio", msg, 1, { c: c === "D" || c === "L" ? "Porta." : "Bloqueado." })); return evs;
    }
    e.x = nx; e.y = ny; e.mx = 0; e.my = 0; e.passos++;
    evs.push(ev("passo", "", 3));
    chegada(e, evs);
    return evs;
  }
  function mirar(e, dx, dy) {
    if (e.fim) return [];
    var x = Math.max(-3, Math.min(3, e.mx + dx)), y = Math.max(-2, Math.min(2, e.my + dy));
    if (x === e.mx && y === e.my) return [ev("mira-limite", "A mira já está no limite.", 2, { c: "Limite." })];
    e.mx = x; e.my = y;
    var v = visiveis(e), trava = v.filter(function (a) { return a.col === e.mx && a.linha === e.my; })[0];
    return [ev(trava ? "trava" : "mira", trava ? "Mira sobre " + nomeInim(trava.m) + ", a " + distTxt(trava.f, trava.s) + "." : "", trava ? 1 : 3, { mx: e.mx, my: e.my, c: trava ? "Alinhado." : "" })];
  }
  function centralizar(e) { e.mx = 0; e.my = 0; return [ev("mira", "Mira no centro.", 2, { mx: 0, my: 0, c: "Centro." })]; }
  function acordar(e, raio) {
    e.inimigos.forEach(function (m) { if (m.hp > 0 && m.a === e.andar && !m.ativo && Math.max(Math.abs(m.x - e.x), Math.abs(m.y - e.y)) <= raio) m.ativo = true; });
  }
  function dano(e, m, d, evs) {
    m.hp -= d;
    if (m.hp > 0) return false;
    e.mortos++;
    evs.push(ev("morte", nomeInim(m, true) + " caiu.", 1, { c: "Caiu." }));
    if (TIPOS[m.t].chefe) { e.fim = "venceu"; evs.push(ev("fim", resultado(e), 1)); }
    return true;
  }
  function atirar(e) {
    var evs = [], a = ARMAS[e.arma];
    if (e.fim) return evs;
    if (a.melee) {
      var d = DIRS[e.dir], m = inimigoEm(e, e.andar, e.x + d[0], e.y + d[1]);
      evs.push(ev("golpe", "", 3, { arma: e.arma }));
      if (!m) { evs.push(ev("erro", "Golpeou o ar.", 2, { c: "Ar." })); return evs; }
      e.tiros++; e.acertos++; m.ativo = true;
      var morto = dano(e, m, a.dano, evs);
      if (!morto) evs.push(ev("acerto", "Acertou " + nomeInim(m) + ".", 2, { c: "Acertou." }));
      return evs;
    }
    if (e.recarga > 0) { evs.push(ev("seco", "Recarregando. Espere.", 1, { c: "Recarregando." })); return evs; }
    var mu = e.mun[e.arma];
    if (mu.carga <= 0) { evs.push(ev("seco", "Sem munição na arma. Shift direito recarrega" + (mu.reserva ? "." : ", mas não há reserva."), 1, { c: "Sem munição." })); return evs; }
    mu.carga--; e.tiros++; acordar(e, 10);
    evs.push(ev("tiro", "", 3, { arma: e.arma }));
    var vis = visiveis(e), alvos = [];
    if (e.arma === "revolver") { var t = vis.filter(function (v) { return v.col === e.mx && v.linha === e.my; })[0]; if (t) alvos.push(t); }
    else alvos = vis.filter(function (v) { return v.f <= 3 && Math.abs(v.col - e.mx) <= 1 && Math.abs(v.linha - e.my) <= 1; });
    if (!alvos.length) {
      var prox = vis[0];
      evs.push(ev("erro", "Errou." + (prox ? " " + dica(e, prox) : " Não há ninguém à vista."), 1, { c: "Errou." }));
    } else {
      alvos.forEach(function (v) {
        var dm = e.arma === "espingarda" ? (v.f <= 2 ? 5 : 3) : a.dano; e.acertos++;
        var morto = dano(e, v.m, dm, evs);
        if (!morto) evs.push(ev("acerto", "Acertou " + nomeInim(v.m) + ".", 1, { c: "Acertou." }));
      });
    }
    if (mu.carga === 0 && !e.fim) evs.push(ev("vazia", mu.reserva ? "Arma vazia. Recarregue com Shift direito." : "Arma vazia e sem reserva.", 2, { c: "Vazia." }));
    return evs;
  }
  function recarregar(e) {
    if (e.fim) return [];
    var a = ARMAS[e.arma];
    if (!a.municao) return [ev("erro", "A " + a.nome + " não recarrega.", 2)];
    if (e.recarga > 0) return [ev("seco", "Já está recarregando.", 2)];
    var mu = e.mun[e.arma];
    if (mu.carga >= a.cap) return [ev("erro", "A " + a.nome + " já está carregada.", 2, { c: "Cheia." })];
    if (mu.reserva <= 0) return [ev("erro", "Sem munição de reserva para a " + a.nome + ".", 1, { c: "Sem reserva." })];
    e.recarga = e.arma === "espingarda" ? 3 : 2; e.recargaArma = e.arma;
    return [ev("recarga", "Recarregando.", 2, { c: "Recarregando." })];
  }
  function escolher(e, n) {
    var id = POR_TECLA[n];
    if (!id) return [ev("erro", "Escolha uma arma de 1 a 4: 1 revólver, 2 espingarda, 3 faca, 4 mão livre.", 1)];
    if (!e.armas[id]) return [ev("erro", "Você ainda não tem a " + ARMAS[id].nome + ".", 1, { c: "Não tem." })];
    if (e.arma === id) return [ev("arma", "Já está com a " + ARMAS[id].nome + ".", 2)];
    e.arma = id; e.recarga = 0;
    var mu = e.mun[id];
    return [ev("arma", "Arma: " + ARMAS[id].nome + (ARMAS[id].municao ? ", " + mu.carga + " na arma e " + mu.reserva + " de reserva." : "."), 1, { c: ARMAS[id].nome + "." })];
  }
  function usar(e) {
    var evs = [];
    if (e.fim) return evs;
    var aqui = e.itens.filter(function (i) { return i.a === e.andar && i.x === e.x && i.y === e.y; });
    if (aqui.length) {
      aqui.forEach(function (i) {
        e.itens.splice(e.itens.indexOf(i), 1);
        if (i.tipo === "chave") { e.chaves.push(i.nome); evs.push(ev("pegou", "Pegou a " + i.nome + ".", 1, { c: "Pegou." })); }
        else if (i.tipo === "kit") { e.kits++; evs.push(ev("pegou", "Pegou um kit médico. Você tem " + e.kits + ". Aperte x onde não houver nada para pegar para usar.", 1, { c: "Kit." })); }
        else if (i.tipo === "municao") { e.mun[i.arma].reserva += i.qtd; evs.push(ev("pegou", "Pegou " + i.nome + ". Reserva: " + e.mun[i.arma].reserva + ".", 1, { c: "Munição." })); }
        else if (i.tipo === "arma") { e.armas[i.arma] = true; e.mun[i.arma].reserva += i.qtd; evs.push(ev("pegou", "Pegou a " + ARMAS[i.arma].nome + " com " + i.qtd + " cartuchos. Aperte 2 para empunhar.", 1, { c: "Espingarda." })); }
      });
      return evs;
    }
    var d = DIRS[e.dir], fx = e.x + d[0], fy = e.y + d[1], c = tile(e, e.andar, fx, fy);
    if ((c === "D" || c === "L") && !aberta(e, e.andar, fx, fy)) {
      if (c === "L") {
        var nec = TRANCADAS[ch(e.andar, fx, fy)];
        if (e.chaves.indexOf(nec) < 0) { evs.push(ev("bloqueio", "A porta está trancada. Você precisa da " + nec + ".", 1, { c: "Trancada." })); return evs; }
        e.abertas[ch(e.andar, fx, fy)] = true; evs.push(ev("porta", "Você destrancou a porta com a " + nec + " e a abriu.", 1, { c: "Aberta." })); acordar(e, 6); return evs;
      }
      e.abertas[ch(e.andar, fx, fy)] = true; evs.push(ev("porta", "Você abriu a porta.", 1, { c: "Aberta." })); return evs;
    }
    var aq = tile(e, e.andar, e.x, e.y);
    if (aq === "^" || aq === "v") {
      e.andar = aq === "^" ? 1 : 0; e.mx = 0; e.my = 0;
      evs.push(ev("escada", aq === "^" ? "Você subiu ao andar de cima da delegacia." : "Você desceu ao térreo da delegacia.", 1, { c: aq === "^" ? "Subiu." : "Desceu." }));
      e.area = ""; chegada(e, evs); return evs;
    }
    if (e.kits > 0) {
      if (e.hp >= e.hpMax) return [ev("erro", "Sua vida está cheia: " + e.hp + ".", 2, { c: "Vida cheia." })];
      e.kits--; e.hp = Math.min(e.hpMax, e.hp + KIT);
      return [ev("cura", "Usou um kit médico. Vida " + e.hp + " de " + e.hpMax + ". Restam " + e.kits + " kits.", 1, { c: "Vida " + e.hp + "." })];
    }
    return [ev("erro", "Nada para pegar ou usar aqui.", 2, { c: "Nada." })];
  }
  function olhar(e) {
    var d = DIRS[e.dir], n = 0, x = e.x + d[0], y = e.y + d[1];
    while (n < 12 && passavel(e, e.andar, x, y)) { n++; x += d[0]; y += d[1]; }
    var c = tile(e, e.andar, x, y), fim = c === "D" ? "uma porta fechada" : c === "L" ? "uma porta trancada" : c === "~" ? "o riacho" : c === "T" ? "árvores" : c === "#" ? "uma parede" : "mais caminho";
    var s = "Você está na " + e.area + ", olhando para " + e.dir + ". À frente há " + (n ? plural(n, "passo livre", "passos livres") + " e depois " + fim : fim + " logo adiante") + ".";
    var v = visiveis(e);
    if (v.length) s += " À vista: " + v.map(function (a) { return TIPOS[a.m.t].nome + " " + ladoTxt(a.f, a.s) + ", a " + distTxt(a.f, a.s); }).join("; ") + ".";
    else s += " Ninguém à vista.";
    var perto = e.itens.filter(function (i) { if (i.a !== e.andar) return false; var p = relativo(e, i.x, i.y); return Math.max(Math.abs(p.f), Math.abs(p.s)) <= 3; });
    if (perto.length) s += " Por perto: " + perto.map(function (i) { var p = relativo(e, i.x, i.y); return p.f === 0 && p.s === 0 ? i.nome + " aqui" : i.nome + " " + ladoTxt(p.f, p.s) + ", a " + distTxt(p.f, p.s); }).join("; ") + ".";
    return s;
  }
  function vivos(e) { return e.inimigos.filter(function (m) { return m.hp > 0; }).length; }
  function status(e) {
    var a = ARMAS[e.arma], mu = e.mun[e.arma];
    return "Vida " + e.hp + " de " + e.hpMax + ". Arma: " + a.nome + (a.municao ? ", " + mu.carga + " na arma e " + mu.reserva + " de reserva" : "") + ". Kits médicos: " + e.kits + ". Chaves: " + (e.chaves.length ? e.chaves.join(", ") : "nenhuma") +
      ". " + (e.andar === 1 ? "Andar de cima" : "Térreo") + ", " + e.area + ", olhando para " + e.dir + ". Inimigos vivos: " + vivos(e) + ".";
  }
  function resultado(e) {
    return e.fim === "venceu" ? "O chefe dos bandidos caiu. O vilarejo está livre! Inimigos derrubados: " + e.mortos + ". Vida final: " + e.hp + " de " + e.hpMax + ". Tiros: " + e.tiros + ", acertos: " + e.acertos + "."
      : "Você caiu. O vilarejo continua sitiado. Inimigos derrubados: " + e.mortos + ".";
  }
  function ajuda() {
    return "Objetivo: libertar o vilarejo derrubando o chefe dos bandidos, na prefeitura. Andar: W norte, D leste, S sul, A oeste. Você olha para onde andou por último. Setas mudam a mira, que começa no centro e volta ao centro quando você anda; Q centraliza. " +
      "Barra de espaço atira. Shift direito recarrega. Teclas 1 a 4 escolhem revólver, espingarda, faca e mão livre. X ou C pega o item do chão, abre a porta à frente, sobe ou desce a escada e, se não houver nada disso, usa um kit médico. E ou R diz o estado, O descreve o que está à frente, H repete esta ajuda. " +
      "O som mostra onde estão os inimigos: o lado no estéreo, o volume é a distância e o tom grave é de animal, que fica abaixo da mira (seta para baixo). Quando a mira passa sobre um inimigo, soa um sinal agudo. Faca e mão livre só acertam quem está colado à sua frente. A espingarda pega vários, mas só de perto.";
  }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), v = t.split(" ")[0] || "", r = t.split(" ")[1] || "";
    var ND = { n: "norte", norte: "norte", w: "norte", cima: "norte", s: "sul", sul: "sul", baixo: "sul", l: "leste", leste: "leste", d: "leste", direita: "leste", oeste: "oeste", a: "oeste", esquerda: "oeste" };
    if (!t) return [ev("erro", "Digite um comando. Experimente: norte, atirar, recarregar, status ou ajuda.", 1)];
    if (ND[v] && v !== "baixo" && v !== "cima" && v !== "direita" && v !== "esquerda") return mover(e, ND[v]);
    if (v === "andar" || v === "ir") { if (ND[r]) return mover(e, ND[r]); return [ev("erro", "Ande para norte, sul, leste ou oeste.", 1)]; }
    if (v === "mira" || v === "mirar") {
      var M = { cima: [0, 1], acima: [0, 1], baixo: [0, -1], abaixo: [0, -1], esquerda: [-1, 0], direita: [1, 0], centro: [0, 0] };
      if (r === "centro") return centralizar(e);
      return M[r] ? mirar(e, M[r][0], M[r][1]) : [ev("erro", "Mire para cima, baixo, esquerda, direita ou centro.", 1)];
    }
    if (v === "centralizar" || v === "q") return centralizar(e);
    if (v === "atirar" || v === "tiro" || v === "espaco" || v === "fogo") return atirar(e);
    if (v === "recarregar" || v === "recarrega") return recarregar(e);
    if (v === "arma") { var n = Number(r); if (!n) { var porNome = { revolver: 1, espingarda: 2, faca: 3, mao: 4 }; n = porNome[r] || 0; } return escolher(e, n); }
    if (/^[1-4]$/.test(v)) return escolher(e, Number(v));
    if (v === "revolver" || v === "espingarda" || v === "faca" || v === "mao") return escolher(e, ARMAS[v].tecla);
    if (v === "pegar" || v === "usar" || v === "x" || v === "c" || v === "abrir" || v === "subir" || v === "descer" || v === "curar") return usar(e);
    if (v === "status" || v === "estado" || v === "e" || v === "r" || v === "vida") return [ev("info", status(e), 1)];
    if (v === "olhar" || v === "o") return [ev("info", olhar(e), 1)];
    if (v === "ajuda" || v === "h") return [ev("info", ajuda(), 1)];
    return [ev("erro", "Não entendi. Digite ajuda para ver os comandos.", 1)];
  }

  // ---- o tempo passa: inimigos acordam, andam, atacam e atiram ----
  function distancias(e) {
    var dist = {}, fila = [[e.x, e.y]], k = ch(e.andar, e.x, e.y), i;
    dist[k] = 0;
    for (i = 0; i < fila.length; i++) {
      var p = fila[i], d0 = dist[ch(e.andar, p[0], p[1])];
      Object.keys(DIRS).forEach(function (n) {
        var x = p[0] + DIRS[n][0], y = p[1] + DIRS[n][1], kk = ch(e.andar, x, y);
        if (kk in dist || !passavel(e, e.andar, x, y)) return;
        dist[kk] = d0 + 1; fila.push([x, y]);
      });
    }
    return dist;
  }
  function danoAoJogador(e, base, evs, de) {
    var d = Math.max(1, Math.round(base * NIVEIS[e.nivel].mult));
    e.hp -= d;
    var p = relativo(e, de.x, de.y);
    evs.push(ev("dano", "Você levou " + d + " de dano, " + ladoTxt(p.f, p.s) + ". Vida " + Math.max(0, e.hp) + " de " + e.hpMax + ".", 1, { c: "Dano " + d + ". Vida " + Math.max(0, e.hp) + ".", s: p.s, f: p.f }));
    if (e.hp <= 0) { e.hp = 0; e.fim = "perdeu"; evs.push(ev("fim", resultado(e), 1)); }
  }
  function tick(e) {
    var evs = [];
    if (e.fim) return evs;
    e.t++;
    if (e.recarga > 0) {
      e.recarga--;
      if (e.recarga === 0) {
        var a = ARMAS[e.recargaArma], mu = e.mun[e.recargaArma], n = Math.min(a.cap - mu.carga, mu.reserva);
        mu.carga += n; mu.reserva -= n;
        evs.push(ev("recarregou", "Recarregada: " + mu.carga + " na arma e " + mu.reserva + " de reserva.", 1, { c: mu.carga + " e " + mu.reserva + "." }));
      }
    }
    var dist = distancias(e), sons = [];
    e.inimigos.forEach(function (m) {
      if (m.hp <= 0 || m.a !== e.andar || e.fim) return;
      var tp = TIPOS[m.t], cheb = Math.max(Math.abs(m.x - e.x), Math.abs(m.y - e.y));
      if (!m.ativo) {
        if (cheb > tp.alerta) return;
        m.ativo = true;
        var p0 = relativo(e, m.x, m.y);
        evs.push(ev("alerta", "Você ouve " + nomeInim(m) + " " + ladoTxt(p0.f, p0.s) + ", a " + distTxt(p0.f, p0.s) + ".", 1, { c: TIPOS[m.t].nome.charAt(0).toUpperCase() + TIPOS[m.t].nome.slice(1) + " " + ladoTxt(p0.f, p0.s) + "." }));
      }
      if (m.cool > 0) m.cool--;
      if (e.t % tp.vel !== 0) return;
      var dk = dist[ch(m.a, m.x, m.y)], manh = Math.abs(m.x - e.x) + Math.abs(m.y - e.y), agiu = false;
      if (tp.atira && cheb <= 6 && m.cool <= 0 && clara(e, e.andar, m.x, m.y, e.x, e.y)) {
        m.cool = 4; agiu = true;
        var pr = relativo(e, m.x, m.y);
        evs.push(ev("tiro-inimigo", "", 3, { f: pr.f, s: pr.s }));
        if (e.rnd(1000) / 1000 < NIVEIS[e.nivel].acerto) danoAoJogador(e, tp.dano, evs, m);
        else evs.push(ev("erro-inimigo", "Um tiro passou perto, " + ladoTxt(pr.f, pr.s) + ".", 2, { c: "Passou perto." }));
      } else if (!tp.atira && manh === 1 && m.cool <= 0) {
        m.cool = 2; agiu = true;
        var pm = relativo(e, m.x, m.y);
        evs.push(ev("ataque", "", 3, { tipo: m.t, f: pm.f, s: pm.s }));
        danoAoJogador(e, tp.dano, evs, m);
      }
      if (e.fim) return;
      if (!agiu || (tp.atira && manh > (tp.dist || 1))) {
        if (dk !== undefined && manh > (tp.atira ? tp.dist : 1)) {
          var melhor = null, bd = dk;
          Object.keys(DIRS).forEach(function (nm) {
            var x = m.x + DIRS[nm][0], y = m.y + DIRS[nm][1], d1 = dist[ch(m.a, x, y)];
            if (d1 === undefined || d1 >= bd || (x === e.x && y === e.y) || inimigoEm(e, m.a, x, y)) return;
            bd = d1; melhor = [x, y];
          });
          if (melhor) { m.x = melhor[0]; m.y = melhor[1]; agiu = true; }
        }
      }
      if (agiu) { var ps = relativo(e, m.x, m.y), dd = Math.sqrt(ps.f * ps.f + ps.s * ps.s); if (dd <= 9) sons.push({ tipo: m.t, f: ps.f, s: ps.s, d: dd }); }
    });
    sons.sort(function (a, b) { return a.d - b.d; }).slice(0, 3).forEach(function (s) { evs.push(ev("inimigo", "", 3, s)); });
    // Quem entrou na linha de visão agora é anunciado uma vez.
    var vis = visiveis(e), novos = [];
    e.inimigos.forEach(function (m) { if (m.hp > 0 && !vis.some(function (v) { return v.m === m; })) m.visto = false; });
    vis.forEach(function (v) {
      if (v.m.visto) return; v.m.visto = true;
      novos.push(TIPOS[v.m.t].nome + " " + ladoTxt(v.f, v.s) + ", a " + distTxt(v.f, v.s));
    });
    if (novos.length && !e.fim) evs.push(ev("vista", "À vista: " + novos.join("; ") + ".", 1, { c: novos[0].split(",")[0] + "." }));
    return evs;
  }

  var api = {
    NIVEIS: NIVEIS, ARMAS: ARMAS, TIPOS: TIPOS, LARG: LARG, ALT: ALT, ALCANCE: ALCANCE, ANDAR0: ANDAR0, ITENS0: ITENS0, INIM0: INIM0, INICIO: INICIO, TRANCADAS: TRANCADAS,
    novo: novo, tile: tile, passavel: passavel, transparente: transparente, visiveis: visiveis, relativo: relativo, coluna: coluna, mover: mover, mirar: mirar, centralizar: centralizar,
    atirar: atirar, recarregar: recarregar, escolher: escolher, usar: usar, olhar: olhar, status: status, ajuda: ajuda, comando: comando, aberta: aberta, tick: tick, areaDe: areaDe, resultado: resultado, vivos: vivos, inimigoEm: inimigoEm
  };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;
  // ================= Tela e som (só no navegador) =================
  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("normal"), relogio = null, ctx = null, semAudio = false, rodando = false, flash = 0;
  var W = 480, VH = 240, HT = 300, N = 120;
  // Paleta de arcade, só para o desenho do jogo (a página em volta segue o Heimdall Design).
  var P = { ceu: ["#05051a", "#0a0a33", "#14144d", "#20206b"], chao: ["#0b2a12", "#0f3a18"], parede: [200, 70, 40], arvore: [30, 150, 50], porta: [210, 150, 40], trancada: [220, 40, 80], neon: "#39ff14", ciano: "#00e5ff", rosa: "#ff2d95", amarelo: "#ffe600", branco: "#ffffff" };

  function audio() {
    if (ctx || semAudio) { if (ctx && ctx.state === "suspended" && ctx.resume) { try { ctx.resume(); } catch (x) { /* segue */ } } return ctx; }
    try { var AC = raiz.AudioContext || raiz.webkitAudioContext; if (!AC) { semAudio = true; return null; } ctx = new AC(); if (ctx.state === "suspended" && ctx.resume) ctx.resume(); } catch (x) { semAudio = true; ctx = null; }
    return ctx;
  }
  function pan(p, c) { var pn = c.createStereoPanner ? c.createStereoPanner() : null; if (pn) pn.pan.value = Math.max(-1, Math.min(1, p)); return pn; }
  // Um tom com posição no estéreo (p de -1 a 1), volume e varredura de frequência.
  function bip(freq, dur, p, tipo, vol, ate, atraso) {
    var c = audio(); if (!c) return;
    try {
      var t0 = c.currentTime + (atraso || 0), o = c.createOscillator(), g = c.createGain(), pn = pan(p || 0, c);
      o.type = tipo || "sine"; o.frequency.setValueAtTime(freq, t0); if (ate) o.frequency.exponentialRampToValueAtTime(ate, t0 + dur);
      g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(Math.max(0.0002, vol || 0.2), t0 + 0.008); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      o.connect(g); if (pn) { g.connect(pn); pn.connect(c.destination); } else g.connect(c.destination);
      o.start(t0); o.stop(t0 + dur + 0.02);
    } catch (x) { /* sem som */ }
  }
  function ruido(dur, p, vol, freq, atraso) {
    var c = audio(); if (!c) return;
    try {
      var n = Math.max(1, Math.floor(c.sampleRate * dur)), b = c.createBuffer(1, n, c.sampleRate), d = b.getChannelData(0), i;
      for (i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
      var s = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain(), pn = pan(p || 0, c), t0 = c.currentTime + (atraso || 0);
      s.buffer = b; f.type = "bandpass"; f.frequency.value = freq || 1500; g.gain.value = vol || 0.3;
      s.connect(f); f.connect(g); if (pn) { g.connect(pn); pn.connect(c.destination); } else g.connect(c.destination); s.start(t0);
    } catch (x) { /* sem som */ }
  }
  // Som de um inimigo: o lado vem de s/distância, o volume cai com a distância, atrás de você soa mais grave e baixo; animais grunhem em tom grave, pessoas pisam.
  function somInimigo(v) {
    var d = Math.max(1, v.d), p = v.s / d, vol = Math.max(0.03, 0.34 - d * 0.034), atras = v.f < 0, k = v.tipo;
    if (atras) vol *= 0.75;
    if (k === "rato") { bip(atras ? 600 : 900, 0.07, p, "triangle", vol * 0.8); bip(atras ? 520 : 760, 0.06, p, "triangle", vol * 0.7, 0, 0.09); }
    else if (k === "cao") { bip(atras ? 110 : 150, 0.22, p, "sawtooth", vol, atras ? 80 : 100); ruido(0.1, p, vol * 0.5, 400); }
    else { ruido(0.06, p, vol, atras ? 300 : 600); bip(atras ? 90 : 120, 0.08, p, "square", vol * 0.7); }
  }
  var SOM = {
    passo: function () { ruido(0.04, 0, 0.08, 500); },
    mira: function (v) { bip(700 + (v.my || 0) * 140, 0.06, (v.mx || 0) / 3, "triangle", 0.16); },
    trava: function (v) { bip(700 + (v.my || 0) * 140, 0.05, (v.mx || 0) / 3, "triangle", 0.16); bip(1760, 0.14, (v.mx || 0) / 3, "square", 0.2, 0, 0.06); },
    "mira-limite": function () { bip(220, 0.08, 0, "square", 0.1); },
    tiro: function (v) {
      if (v.arma === "espingarda") { ruido(0.28, 0, 0.7, 600); bip(110, 0.3, 0, "sawtooth", 0.35, 40); }
      else { ruido(0.12, 0, 0.5, 1800); bip(420, 0.14, 0, "square", 0.25, 90); }
    },
    golpe: function (v) { if (v.arma === "faca") ruido(0.12, 0, 0.3, 4000); else bip(140, 0.1, 0, "sine", 0.3, 70); },
    seco: function () { bip(1200, 0.03, 0, "square", 0.15); },
    recarga: function () { ruido(0.05, 0, 0.3, 2500); bip(500, 0.05, 0, "square", 0.12, 0, 0.18); },
    recarregou: function () { bip(800, 0.06, 0, "square", 0.18); bip(1200, 0.08, 0, "square", 0.18, 0, 0.08); },
    acerto: function () { bip(300, 0.1, 0, "square", 0.25, 80); },
    morte: function () { bip(500, 0.35, 0, "sawtooth", 0.25, 60); },
    erro: function () { bip(160, 0.1, 0, "square", 0.1); },
    "tiro-inimigo": function (v) { var d = Math.max(1, Math.sqrt(v.f * v.f + v.s * v.s)); ruido(0.1, v.s / d, Math.max(0.06, 0.5 - d * 0.05), 1400); bip(300, 0.12, v.s / d, "square", Math.max(0.05, 0.3 - d * 0.03), 80); },
    "erro-inimigo": function () { },
    ataque: function (v) { var d = Math.max(1, Math.sqrt(v.f * v.f + v.s * v.s)); bip(v.tipo === "rato" ? 1000 : 200, 0.08, v.s / d, "sawtooth", 0.25, v.tipo === "rato" ? 700 : 120); },
    inimigo: somInimigo,
    dano: function (v) { bip(110, 0.28, (v.s || 0) / Math.max(1, Math.abs(v.s || 0) + Math.abs(v.f || 0)), "sawtooth", 0.4, 55); flash = 3; },
    alerta: function () { bip(440, 0.08, 0, "triangle", 0.15); },
    vista: function () { bip(600, 0.06, 0, "triangle", 0.12); },
    pegou: function () { bip(660, 0.07, 0, "sine", 0.2); bip(990, 0.1, 0, "sine", 0.2, 0, 0.07); },
    cura: function () { bip(520, 0.1, 0, "sine", 0.2, 900); },
    porta: function () { ruido(0.2, 0, 0.35, 700); bip(180, 0.18, 0, "triangle", 0.2, 120); },
    escada: function () { bip(400, 0.16, 0, "sine", 0.18, 800); },
    bloqueio: function () { bip(150, 0.1, 0, "square", 0.12); },
    fim: function () { if (e.fim === "venceu") { bip(523, 0.12, 0, "triangle", 0.22); bip(659, 0.12, 0, "triangle", 0.22, 0, 0.12); bip(784, 0.3, 0, "triangle", 0.22, 0, 0.24); } else { bip(330, 0.2, 0, "sawtooth", 0.14); bip(220, 0.4, 0, "sawtooth", 0.14, 0, 0.2); } }
  };
  var narr = "completa";
  function falar(evs) {
    var partes = [];
    evs.forEach(function (v) {
      if (!v.msg || (v.n === 3)) return;
      if (narr === "curta") { if (v.c) partes.push(v.c); else if (v.n === 1) partes.push(v.msg); }
      else partes.push(v.msg);
    });
    if (partes.length) H.anunciar(partes.join(" "));
  }
  function processar(evs) {
    evs.forEach(function (v) { var f = SOM[v.t]; if (f && !semAudio) f(v); });
    falar(evs);
    if (e.fim) parar();
    desenhar();
  }

  // ---- desenho: raios na grade, sprites e mini-mapa ----
  function cor(c, f) { return "rgb(" + Math.round(c[0] * f) + "," + Math.round(c[1] * f) + "," + Math.round(c[2] * f) + ")"; }
  function sprite(g, k, x, base, tam, lado) {
    var t = TIPOS[k];
    if (k === "rato") { g.fillStyle = "#b0b0b0"; g.fillRect(x - tam * 0.3, base - tam * 0.18, tam * 0.6, tam * 0.18); g.fillStyle = P.rosa; g.fillRect(x + tam * 0.18, base - tam * 0.15, tam * 0.08, tam * 0.06); g.fillRect(x - tam * 0.42, base - tam * 0.08, tam * 0.14, tam * 0.03); }
    else if (k === "cao") { g.fillStyle = "#a0602a"; g.fillRect(x - tam * 0.35, base - tam * 0.34, tam * 0.7, tam * 0.24); g.fillRect(x + tam * 0.22, base - tam * 0.46, tam * 0.2, tam * 0.2); g.fillStyle = "#702f10"; g.fillRect(x - tam * 0.3, base - tam * 0.1, tam * 0.1, tam * 0.1); g.fillRect(x + tam * 0.2, base - tam * 0.1, tam * 0.1, tam * 0.1); g.fillStyle = P.amarelo; g.fillRect(x + tam * 0.34, base - tam * 0.42, tam * 0.05, tam * 0.05); }
    else {
      var corpo = k === "chefe" ? "#7a1fa2" : k === "capanga" ? "#c0392b" : "#d35400", w = (k === "chefe" ? 0.5 : 0.4) * tam;
      g.fillStyle = corpo; g.fillRect(x - w / 2, base - tam * 0.62, w, tam * 0.42);
      g.fillStyle = "#222"; g.fillRect(x - w / 2, base - tam * 0.2, w * 0.4, tam * 0.2); g.fillRect(x + w * 0.1, base - tam * 0.2, w * 0.4, tam * 0.2);
      g.fillStyle = "#e8b88a"; g.fillRect(x - w * 0.25, base - tam * 0.84, w * 0.5, tam * 0.22);
      g.fillStyle = "#111"; g.fillRect(x - w * 0.3, base - tam * 0.88, w * 0.6, tam * 0.08);
      g.fillStyle = P.branco; g.fillRect(x + w / 2, base - tam * 0.55, tam * 0.22, tam * 0.07);
    }
  }
  function desenhar() {
    var cv = jogo && jogo.querySelector("canvas"); if (!cv || !cv.getContext) return;
    var g = cv.getContext("2d"); if (!g) return;
    var d = DIRS[e.dir], fx = d[0], fy = d[1], rx = -fy, ry = fx, px = e.x + 0.5, py = e.y + 0.5, cw = W / N, zb = [], i, k;
    g.fillStyle = "#000"; g.fillRect(0, 0, W, HT);
    for (k = 0; k < 4; k++) { g.fillStyle = P.ceu[k]; g.fillRect(0, k * VH / 8, W, VH / 8 + 1); }
    for (k = 0; k < 8; k++) { g.fillStyle = P.chao[k % 2]; g.fillRect(0, VH / 2 + k * VH / 16, W, VH / 16 + 1); }
    for (i = 0; i < N; i++) {
      var cx = (i + 0.5) / N * 2 - 1, dx = fx + rx * cx, dy = fy + ry * cx, mx = e.x, my = e.y, ddx = Math.abs(1 / (dx || 1e-9)), ddy = Math.abs(1 / (dy || 1e-9));
      var sx = dx < 0 ? -1 : 1, sy = dy < 0 ? -1 : 1, sdx = (dx < 0 ? px - mx : mx + 1 - px) * ddx, sdy = (dy < 0 ? py - my : my + 1 - py) * ddy, lado = 0, dist = 99, hit = "", n = 0;
      while (n++ < 40) {
        if (sdx < sdy) { sdx += ddx; mx += sx; lado = 0; } else { sdy += ddy; my += sy; lado = 1; }
        if (!transparente(e, e.andar, mx, my)) { hit = tile(e, e.andar, mx, my); dist = (lado === 0 ? sdx - ddx : sdy - ddy); break; }
      }
      zb.push(dist);
      if (!hit) continue;
      var h = Math.min(VH, VH / Math.max(0.2, dist)), y0 = (VH - h) / 2, sh = Math.max(0.2, 1 - dist / 11) * (lado ? 0.72 : 1);
      var base = hit === "T" ? P.arvore : hit === "D" ? P.porta : hit === "L" ? P.trancada : P.parede;
      g.fillStyle = cor(base, sh); g.fillRect(i * cw, y0, cw + 1, h);
      if (hit === "#" && ((mx + my) % 2 === 0)) { g.fillStyle = cor([0, 0, 0], 1); g.globalAlpha = 0.12; g.fillRect(i * cw, y0, cw + 1, h); g.globalAlpha = 1; }
    }
    // inimigos e itens como sprites, do mais longe para o mais perto, escondidos atrás de paredes mais próximas
    var lista = [];
    e.inimigos.forEach(function (m) { if (m.hp > 0 && m.a === e.andar) lista.push({ tipo: "i", m: m, x: m.x, y: m.y }); });
    e.itens.forEach(function (it) { if (it.a === e.andar) lista.push({ tipo: "t", it: it, x: it.x, y: it.y }); });
    lista.forEach(function (o) { var p = relativo(e, o.x, o.y); o.f = p.f; o.s = p.s; });
    lista.filter(function (o) { return o.f >= 0.6 && Math.abs(o.s) <= o.f * 1.15; }).sort(function (a, b) { return b.f - a.f; }).forEach(function (o) {
      var col = Math.max(0, Math.min(N - 1, Math.floor((o.s / o.f * 0.5 + 0.5) * N)));
      if (zb[col] < o.f - 0.3) return;
      var xs = (o.s / o.f * 0.5 + 0.5) * W, tam = Math.min(VH * 0.9, VH / o.f * 0.7), baseY = VH / 2 + VH / (2 * o.f) * 0.55;
      if (o.tipo === "i") sprite(g, o.m.t, xs, baseY, tam);
      else { g.fillStyle = o.it.tipo === "chave" ? P.amarelo : o.it.tipo === "kit" ? P.rosa : P.ciano; g.fillRect(xs - tam * 0.1, baseY - tam * 0.22, tam * 0.2, tam * 0.2); }
    });
    // mira
    var ax = (e.mx / 3 * 0.5 + 0.5) * W, ay = VH / 2 - e.my * VH * 0.12, trava = visiveis(e).some(function (v) { return v.col === e.mx && v.linha === e.my; });
    g.strokeStyle = trava ? P.rosa : P.neon; g.lineWidth = 2; g.beginPath(); g.moveTo(ax - 14, ay); g.lineTo(ax - 4, ay); g.moveTo(ax + 4, ay); g.lineTo(ax + 14, ay); g.moveTo(ax, ay - 14); g.lineTo(ax, ay - 4); g.moveTo(ax, ay + 4); g.lineTo(ax, ay + 14); g.stroke();
    if (flash > 0) { g.fillStyle = "rgba(255,0,60,0.3)"; g.fillRect(0, 0, W, VH); flash--; }
    // mini-mapa
    var ox = W - LARG * 3 - 6, oy = 6;
    g.fillStyle = "rgba(0,0,0,0.6)"; g.fillRect(ox - 2, oy - 2, LARG * 3 + 4, ALT * 3 + 4);
    var yy, xx;
    for (yy = 0; yy < ALT; yy++) for (xx = 0; xx < LARG; xx++) {
      var c = tile(e, e.andar, xx, yy); if (c === "#" && e.andar === 1) continue;
      g.fillStyle = c === "#" ? "#a04030" : c === "T" ? "#1e7a32" : c === "~" ? "#2060d0" : c === "=" ? "#c09040" : c === "D" || c === "L" ? (aberta(e, e.andar, xx, yy) ? "#555" : "#ffb020") : c === "^" || c === "v" ? "#fff" : c === "," ? "#406020" : "#303030";
      g.fillRect(ox + xx * 3, oy + yy * 3, 3, 3);
    }
    e.inimigos.forEach(function (m) { if (m.hp > 0 && m.a === e.andar) { g.fillStyle = P.rosa; g.fillRect(ox + m.x * 3, oy + m.y * 3, 3, 3); } });
    g.fillStyle = P.neon; g.fillRect(ox + e.x * 3 - 1, oy + e.y * 3 - 1, 5, 5); g.fillStyle = P.amarelo; g.fillRect(ox + (e.x + fx) * 3, oy + (e.y + fy) * 3, 3, 3);
    // painel
    g.fillStyle = "#101020"; g.fillRect(0, VH, W, HT - VH);
    g.font = "bold 16px monospace"; g.textBaseline = "top";
    g.fillStyle = P.neon; g.fillText("VIDA", 10, VH + 8); g.fillStyle = "#333"; g.fillRect(64, VH + 9, 150, 14); g.fillStyle = e.hp <= e.hpMax * 0.3 ? P.rosa : P.neon; g.fillRect(64, VH + 9, 150 * e.hp / e.hpMax, 14);
    var a = ARMAS[e.arma], mu = e.mun[e.arma];
    g.fillStyle = P.ciano; g.fillText(a.nome.toUpperCase(), 10, VH + 32); g.fillStyle = P.amarelo; g.fillText(a.municao ? mu.carga + " / " + mu.reserva : "SEM MUNICAO", 230, VH + 32);
    g.fillStyle = P.branco; g.fillText("KITS " + e.kits + "  CHAVES " + e.chaves.length + "  INIMIGOS " + vivos(e), 10, VH + 56);
    g.fillStyle = P.rosa; g.fillText(e.area.toUpperCase(), 230, VH + 8);
    if (e.fim) { g.fillStyle = "rgba(0,0,0,0.7)"; g.fillRect(0, VH / 2 - 30, W, 60); g.fillStyle = e.fim === "venceu" ? P.neon : P.rosa; g.font = "bold 28px monospace"; g.textAlign = "center"; g.fillText(e.fim === "venceu" ? "VITORIA!" : "FIM DE JOGO", W / 2, VH / 2 - 14); g.textAlign = "left"; }
  }

  // ---- controles ----
  var campoTeclas = H.el("input", { id: "teclas", type: "text", autocomplete: "off", spellcheck: "false", "aria-label": "Área de jogo. W A S D andam, setas mudam a mira, espaço atira, Shift direito recarrega, 1 a 4 escolhem a arma, X pega e usa, E diz o estado, O descreve, H ajuda. Também dá para digitar comandos e apertar Enter" });
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + (k === "facil" ? ": mais vida e inimigos mais fracos" : k === "normal" ? ": equilibrado" : ": pouca vida, inimigos rápidos e certeiros") }); }));
  nivelSel.value = "normal";
  var falaSel = H.el("select", { id: "fala" }, [["completa", "Completa: descreve tudo"], ["curta", "Curta: só o essencial"]].map(function (o) { return H.el("option", { value: o[0], texto: o[1] }); }));
  falaSel.addEventListener("change", function () { narr = falaSel.value; });
  var iniciarBtn = H.el("button", { type: "button", texto: "Iniciar" }), pararBtn = H.el("button", { type: "button", texto: "Parar" }), testeSom = H.el("button", { type: "button", texto: "Testar o som" });
  var comandoCampo = H.el("input", { id: "comando", type: "text", autocomplete: "off", spellcheck: "false", "aria-label": "Comando por texto, como atirar, norte ou status, e Enter" });
  var cv = H.el("canvas", { width: String(W), height: String(HT), "aria-hidden": "true" });
  cv.style.maxWidth = "100%"; cv.style.height = "auto"; cv.style.imageRendering = "pixelated"; cv.style.background = "#000"; cv.style.display = "block";
  var teclado = H.el("div", { role: "group", "aria-label": "Controles" }, [["Norte", "norte"], ["Oeste", "oeste"], ["Leste", "leste"], ["Sul", "sul"], ["Atirar", "atirar"], ["Recarregar", "recarregar"], ["Pegar ou usar", "usar"], ["Estado", "status"], ["Olhar", "olhar"], ["Ajuda", "ajuda"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { acao(x[1]); }); return b;
  }));
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, H.el("label", { "for": "fala", texto: "Narração" }), falaSel, iniciarBtn, pararBtn, testeSom, H.el("label", { "for": "teclas", texto: "Área de jogo (teclado)" }), campoTeclas, cv, teclado, H.el("label", { "for": "comando", texto: "Comando por texto" }), comandoCampo].forEach(function (x) { jogo.appendChild(x); });
  function parar() { rodando = false; if (relogio) { raiz.clearInterval(relogio); relogio = null; } }
  function acao(txt) {
    if (!rodando && !/^(status|olhar|ajuda)$/.test(txt)) { H.anunciar("A partida não está rodando. Aperte Iniciar."); return; }
    audio(); processar(comando(e, txt));
  }
  function passo() { processar(tick(e)); }
  function iniciar() {
    parar(); e = novo(nivelSel.value); narr = falaSel.value; audio(); rodando = true; desenhar();
    H.anunciar("Partida iniciada, nível " + e.nome + ". " + (semAudio ? "Seu navegador não tem áudio estéreo, então vou descrever o que aparece. " : "Use fones de ouvido. ") + "Você está na margem oeste do riacho, olhando para leste, com um revólver de 6 balas. Bandidos tomaram o vilarejo: ache a ponte e derrube o chefe, na prefeitura. Aperte H para a ajuda.");
    relogio = raiz.setInterval(passo, NIVEIS[e.nivel].tick); campoTeclas.focus();
  }
  iniciarBtn.addEventListener("click", iniciar);
  pararBtn.addEventListener("click", function () { parar(); H.anunciar("Partida pausada. " + status(e) + " Aperte Iniciar para recomeçar do zero."); });
  var temposTeste = [];
  testeSom.addEventListener("click", function () {
    var c = audio();
    if (!c) { H.anunciar("Seu navegador não oferece áudio estéreo. O jogo descreve o que acontece em texto."); return; }
    temposTeste.forEach(function (t) { raiz.clearTimeout(t); }); temposTeste = [];
    function tocar() {
      somInimigo({ tipo: "bandido", f: 3, s: -3, d: 4 });
      temposTeste.push(setTimeout(function () { somInimigo({ tipo: "cao", f: 3, s: 0, d: 3 }); }, 900));
      temposTeste.push(setTimeout(function () { somInimigo({ tipo: "rato", f: 3, s: 3, d: 4 }); }, 1800));
      temposTeste.push(setTimeout(function () { SOM.tiro({ arma: "revolver" }); }, 2700));
      temposTeste.push(setTimeout(function () { H.anunciar("Você ouviu passos de bandido só no fone esquerdo, o grunhido grave de um cão no meio, o guincho agudo de um rato só no direito e um tiro de revólver. Se algo veio do lado errado, confira os fones."); }, 3500));
    }
    if (c.state === "suspended" && c.resume) {
      var feito = false, ir = function () { if (!feito) { feito = true; tocar(); } };
      try { var pr = c.resume(); if (pr && pr.then) pr.then(ir, ir); else ir(); } catch (x) { ir(); }
      temposTeste.push(setTimeout(ir, 500));
    } else tocar();
  });
  var TECLAS = { w: "norte", a: "oeste", s: "sul", d: "leste", ArrowUp: "mira cima", ArrowDown: "mira baixo", ArrowLeft: "mira esquerda", ArrowRight: "mira direita", " ": "atirar", q: "centralizar", x: "usar", c: "usar", e: "status", r: "status", o: "olhar", h: "ajuda", "1": "arma 1", "2": "arma 2", "3": "arma 3", "4": "arma 4" };
  function tecla(ev) {
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return null;
    if (ev.key === "Shift" && ev.code === "ShiftRight") return "recarregar";
    var k = ev.key.length === 1 ? ev.key.toLowerCase() : ev.key;
    if (ev.shiftKey && /^[0-9]$/.test(k)) return null;
    return TECLAS[k] || null;
  }
  // As teclas do jogo valem na área de jogo e, com a partida rodando, em qualquer lugar da página (menos em seletores, no campo de comando e no espaço sobre botões).
  document.addEventListener("keydown", function (ev) {
    var t = ev.target && ev.target.tagName, noCampo = ev.target === campoTeclas;
    if (t === "SELECT" || t === "TEXTAREA" || (t === "INPUT" && !noCampo)) return;
    if (!noCampo && !rodando) return;
    var a = tecla(ev); if (!a) return;
    if (a === "atirar" && !noCampo && (t === "BUTTON" || t === "A")) return;
    ev.preventDefault(); if (!ev.repeat || /^(norte|sul|leste|oeste|mira)/.test(a)) acao(a === "mira cima" ? "mira cima" : a);
  });
  campoTeclas.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); var v = campoTeclas.value; campoTeclas.value = ""; if (v) acao(v); } });
  comandoCampo.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); var v = comandoCampo.value; comandoCampo.value = ""; if (v) acao(v); } });
  desenhar();
  H.anunciar("Vilarejo Sitiado. Use fones de ouvido. Aperte Testar o som para conferir o estéreo e depois Iniciar. O botão Ajuda explica os controles.");
  raiz.HeimdallVilarejo = api;
})(typeof window !== "undefined" ? window : globalThis);
