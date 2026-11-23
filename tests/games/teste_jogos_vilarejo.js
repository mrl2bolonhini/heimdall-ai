// Testes da lógica do Vilarejo Sitiado: mapa, andar, portas e chaves, mira, armas, inimigos, escada e fim de partida (sem som e sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const V = require(path.join(__dirname, "..", "..", "games", "vilarejo.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const mb = (a) => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const rn = (seed) => { const m = mb(seed); return (n) => Math.floor(m() * n); };
const msgs = (evs) => evs.map(v => v.msg).join(" ");
const tipos = (evs) => evs.map(v => v.t);
function sem(e) { e.inimigos.forEach(m => { m.hp = 0; }); }                 // tira todos os inimigos
function poe(e, x, y, dir) { e.x = x; e.y = y; if (dir) e.dir = dir; e.mx = 0; e.my = 0; }
function inim(e, tipo, x, y, a = 0) { const m = { t: tipo, a, x, y, hp: V.TIPOS[tipo].hp, ativo: false, cool: 0, visto: false }; e.inimigos.push(m); return m; }

t("o mapa tem 16 linhas de 30 colunas nos dois andares e só símbolos conhecidos", () => {
  const e = V.novo("normal", rn(1));
  assert.equal(V.ANDAR0.length, 16);
  e.mapa.forEach(a => { assert.equal(a.length, 16); a.forEach(l => { assert.equal(l.length, 30); l.forEach(c => assert(".g,=_#T~DL^v".includes(c), "símbolo " + c)); }); });
});
t("tudo é alcançável na ordem certa: chave da delegacia, escada, espingarda, chave da prefeitura e o chefe", () => {
  const e = V.novo("normal", rn(1));
  function alcance(a, x, y, abertas) {
    const vis = new Set([a + "," + x + "," + y]), fila = [[a, x, y]];
    while (fila.length) { const [aa, xx, yy] = fila.shift(); [[0, -1], [1, 0], [0, 1], [-1, 0]].forEach(([dx, dy]) => { const nx = xx + dx, ny = yy + dy, k = aa + "," + nx + "," + ny, c = V.tile(e, aa, nx, ny);
      if (vis.has(k) || "#T~".includes(c)) return; if (c === "L" && !abertas.has(k)) return; vis.add(k); fila.push([aa, nx, ny]); }); const c = V.tile(e, aa, xx, yy); if (c === "^" && !vis.has("1," + xx + "," + yy)) { vis.add("1," + xx + "," + yy); fila.push([1, xx, yy]); } if (c === "v" && !vis.has("0," + xx + "," + yy)) { vis.add("0," + xx + "," + yy); fila.push([0, xx, yy]); } }
    return vis;
  }
  const item = n => V.ITENS0.find(i => i.nome === n), A = new Set();
  let r = alcance(0, 8, 8, A);
  assert(r.has("0," + item("chave da delegacia").x + ",5".replace(",5", "," + item("chave da delegacia").y)), "chave da delegacia alcançável de início");
  assert(!r.has("0,15,12"), "a delegacia está trancada no começo");
  A.add("0,16,10"); r = alcance(0, 8, 8, A);
  assert(r.has("1,14,11") && r.has("1,18,13"), "espingarda e chave da prefeitura acessíveis pela escada");
  assert(!r.has("0,26,12"), "a prefeitura ainda trancada");
  A.add("0,25,10"); r = alcance(0, 8, 8, A);
  assert(r.has("0,26,12"), "o chefe é alcançável");
  V.ITENS0.forEach(i => assert(r.has(i.a + "," + i.x + "," + i.y), "item inalcançável: " + i.nome));
  V.INIM0.forEach(m => { assert(r.has(m.a + "," + m.x + "," + m.y), "inimigo fora do mapa: " + m.t); assert(!"#T~".includes(V.tile(e, m.a, m.x, m.y))); });
  assert(V.INIM0.filter(m => m.t === "chefe").length === 1);
  assert(Object.keys(V.TRANCADAS).every(k => { const [a, x, y] = k.split(",").map(Number); return V.tile(e, a, x, y) === "L"; }));
});
t("começa no oeste da ponte, olhando para leste, com revólver 6 + 12, faca e mão livre", () => {
  const e = V.novo("normal", rn(1));
  assert.deepEqual([e.x, e.y, e.dir, e.andar], [8, 8, "leste", 0]); assert.equal(e.arma, "revolver"); assert.deepEqual(e.mun.revolver, { carga: 6, reserva: 12 });
  assert(e.armas.faca && e.armas.mao && !e.armas.espingarda); assert.equal(e.hp, 20); assert.equal(V.novo("facil").hp, 30); assert.equal(V.novo("dificil").hp, 14);
  assert.equal(e.area, "margem oeste do riacho");
});
t("W, D, S e A andam para norte, leste, sul e oeste, olham para lá e anunciam a área nova", () => {
  const e = V.novo("normal", rn(1)); sem(e);
  let r = V.comando(e, "w"); assert.deepEqual([e.x, e.y, e.dir], [8, 7, "norte"]); assert(!msgs(r));
  r = V.comando(e, "d"); assert.deepEqual([e.x, e.y, e.dir], [9, 7, "leste"]);
  r = V.comando(e, "d"); assert(/ponte do riacho/.test(msgs(r)), msgs(r)); r = V.comando(e, "d"); r = V.comando(e, "d"); assert(/rua do vilarejo/.test(msgs(r)), msgs(r));
  V.comando(e, "s"); assert.equal(e.dir, "sul"); V.comando(e, "a"); assert.equal(e.dir, "oeste");
});
t("o riacho, a parede e árvores bloqueiam, mas viram o personagem para lá", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 9, 6, "leste");
  let r = V.mover(e, "leste"); assert(/riacho/.test(msgs(r)) && e.x === 9, msgs(r));
  poe(e, 1, 1, "norte"); r = V.mover(e, "norte"); assert(/Árvores/.test(msgs(r)) && e.y === 1, msgs(r));
  poe(e, 13, 6, "norte"); r = V.mover(e, "norte"); assert(/Parede/.test(msgs(r)), msgs(r));
});
t("porta: fechada bloqueia; x abre; trancada exige a chave certa", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 16, 6, "norte");
  let r = V.mover(e, "norte"); assert(/Porta fechada/.test(msgs(r))); assert.equal(e.y, 6);
  r = V.usar(e); assert(/abriu a porta/.test(msgs(r))); r = V.mover(e, "norte"); assert.equal(e.y, 5);
  poe(e, 16, 9, "sul"); r = V.mover(e, "sul"); assert(/Porta trancada/.test(msgs(r))); r = V.usar(e); assert(/chave da delegacia/.test(msgs(r)) && !e.abertas["0,16,10"]);
  e.chaves.push("chave da prefeitura"); r = V.usar(e); assert(!e.abertas["0,16,10"], "chave errada não abre");
  e.chaves.push("chave da delegacia"); r = V.usar(e); assert(/destrancou/.test(msgs(r)) && e.abertas["0,16,10"]);
  r = V.mover(e, "sul"); assert.equal(e.y, 10);
});
t("itens: x pega a chave, os kits, a munição e a espingarda; x sem item usa o kit", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 5, 12, "norte");
  let r = V.usar(e); assert(/chave da delegacia/.test(msgs(r)) && e.chaves.includes("chave da delegacia"));
  poe(e, 3, 12); r = V.usar(e); assert.equal(e.mun.revolver.reserva, 24);
  poe(e, 3, 11); r = V.usar(e); assert.equal(e.kits, 1); r = V.usar(e); assert(/Vida cheia|vida está cheia/i.test(msgs(r)), msgs(r));
  e.hp = 5; r = V.usar(e); assert.equal(e.hp, 13); assert.equal(e.kits, 0); r = V.usar(e); assert(/Nada para pegar/.test(msgs(r)));
  e.andar = 1; poe(e, 14, 11); r = V.usar(e); assert(e.armas.espingarda && e.mun.espingarda.reserva === 4, msgs(r));
  poe(e, 14, 12); r = V.comando(e, "atirar"); // não explode sem arma equipada
  assert(V.escolher(e, 2).length === 1 && e.arma === "espingarda");
});
t("chegar a uma casa com item avisa e escada avisa", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 5, 11, "sul"); const r = V.mover(e, "sul"); assert(/Aqui há: 4 balas|chave da delegacia/.test(msgs(r)) || /Aqui há/.test(msgs(r)), msgs(r));
  poe(e, 16, 11, "sul"); e.abertas["0,16,10"] = true; const r2 = V.mover(e, "sul"); assert(/Escada para cima/.test(msgs(r2)), msgs(r2));
});
t("escada: sobe ao andar de cima e desce de volta, na mesma casa", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 16, 12, "sul");
  let r = V.usar(e); assert.equal(e.andar, 1); assert(/subiu/.test(msgs(r)) && /andar de cima/.test(msgs(r))); assert.equal(e.area, "andar de cima da delegacia");
  r = V.usar(e); assert.equal(e.andar, 0); assert(/desceu/.test(msgs(r)));
});
t("mira: começa no centro, as setas movem, tem limites e andar centraliza", () => {
  const e = V.novo("normal", rn(1)); sem(e); assert.deepEqual([e.mx, e.my], [0, 0]);
  V.mirar(e, -1, 0); V.mirar(e, 0, -1); assert.deepEqual([e.mx, e.my], [-1, -1]);
  for (let i = 0; i < 5; i++) V.mirar(e, -1, 0); assert.equal(e.mx, -3); assert(/limite/.test(msgs(V.mirar(e, -1, 0))));
  for (let i = 0; i < 5; i++) V.mirar(e, 0, 1); assert.equal(e.my, 2);
  V.mover(e, "leste"); assert.deepEqual([e.mx, e.my], [0, 0]); V.mirar(e, 1, 0); V.comando(e, "q"); assert.equal(e.mx, 0);
});
t("o que está à vista: cone de 45°, alcance de 7, sem parede no meio; a coluna da mira vem de lado/distância", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 14, 8, "leste");
  const a = inim(e, "bandido", 18, 8), b = inim(e, "bandido", 18, 6), c = inim(e, "bandido", 18, 4), d = inim(e, "bandido", 22, 8);
  const v = V.visiveis(e); assert.deepEqual(v.map(x => x.m), [a, b]); // c está fora do cone, d além do alcance
  assert.equal(v[0].col, 0); assert.equal(v[1].s, -2); assert.equal(v[1].col, -2);
  assert.equal(V.coluna(4, -4), -3); assert.equal(V.coluna(4, 2), 2); assert.equal(V.coluna(4, -2), -2, "simétrico"); assert.equal(V.coluna(1, 1), 3);
  poe(e, 14, 6, "norte"); assert.equal(V.visiveis(e).length, 0, "parede da igreja bloqueia a visão para o norte? (sem inimigo)");
  const f = inim(e, "bandido", 16, 3); e.andar = 0; poe(e, 16, 7, "norte"); assert.equal(V.visiveis(e).filter(x => x.m === f).length, 0, "porta fechada tapa a visão");
  e.abertas["0,16,5"] = true; assert.equal(V.visiveis(e).filter(x => x.m === f).length, 1, "porta aberta deixa ver");
});
t("revólver: só acerta com a mira na coluna e na linha do alvo; animal fica na linha de baixo", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 14, 8, "leste"); const rato = inim(e, "rato", 16, 8);
  let r = V.atirar(e); // mira no centro: o rato está na linha de baixo
  assert(tipos(r).includes("erro") && /Errou/.test(msgs(r)) && /mais abaixo/.test(msgs(r)), msgs(r)); assert.equal(e.mun.revolver.carga, 5); assert.equal(rato.hp, 2);
  V.mirar(e, 0, -1); r = V.atirar(e); assert(/caiu/.test(msgs(r)), msgs(r)); assert(rato.hp <= 0);
  const b = inim(e, "bandido", 18, 8); V.centralizar(e); r = V.atirar(e); assert.equal(b.hp, 2); assert(/Acertou o bandido/.test(msgs(r))); r = V.atirar(e); assert(b.hp <= 0 && /caiu/.test(msgs(r)));
  const c = inim(e, "bandido", 18, 6); V.centralizar(e); V.mirar(e, -1, 0); r = V.atirar(e); assert.equal(c.hp, 5, "coluna errada: " + e.mx); V.mirar(e, -1, 0); r = V.atirar(e); assert.equal(c.hp, 2, "coluna -2");
});
t("mirar sobre um inimigo avisa 'Mira sobre' e dá o evento de trava", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 14, 8, "leste"); inim(e, "bandido", 18, 7);
  let r = V.mirar(e, 1, 0); assert.equal(r[0].t, "mira"); r = V.mirar(e, -1, 0); assert.equal(r[0].t, "mira"); r = V.mirar(e, -1, 0); assert.equal(r[0].t, "trava"); assert(/Mira sobre o bandido, a 4 passos/.test(r[0].msg), r[0].msg);
});
t("revólver sem munição faz clique; recarregar leva tempo, usa a reserva e tem limites", () => {
  const e = V.novo("normal", rn(1)); sem(e); e.mun.revolver.carga = 0;
  assert(/Sem munição na arma/.test(msgs(V.atirar(e)))); let r = V.recarregar(e); assert(/Recarregando/.test(msgs(r)) && e.recarga === 2);
  assert(/Recarregando\. Espere/.test(msgs(V.atirar(e)))); V.tick(e); assert.equal(e.mun.revolver.carga, 0); r = V.tick(e); assert(/Recarregada: 6 na arma e 6 de reserva/.test(msgs(r)), msgs(r)); assert.equal(e.recarga, 0);
  assert(/já está carregada/.test(msgs(V.recarregar(e)))); e.mun.revolver = { carga: 2, reserva: 0 }; assert(/Sem munição de reserva/.test(msgs(V.recarregar(e))));
  V.escolher(e, 3); assert(/não recarrega/.test(msgs(V.recarregar(e))));
});
t("espingarda: cone de uma coluna e uma linha, só até 3 passos, atinge vários e dá mais dano de perto", () => {
  const e = V.novo("normal", rn(1)); sem(e); e.armas.espingarda = true; e.mun.espingarda = { carga: 2, reserva: 4 }; V.escolher(e, 2); poe(e, 14, 8, "leste");
  const a = inim(e, "bandido", 15, 8), b = inim(e, "bandido", 17, 9), longe = inim(e, "bandido", 19, 8);
  const r = V.atirar(e); assert.equal(a.hp, 0, "perto: 5 de dano mata o bandido (5)"); assert(b.hp < 5 && b.hp === 2, "a 3 passos na coluna vizinha leva 3: " + b.hp); assert.equal(longe.hp, 5); assert.equal(e.mun.espingarda.carga, 1);
  const e2 = V.novo("normal", rn(1)); sem(e2); e2.armas.espingarda = true; e2.mun.espingarda = { carga: 2, reserva: 0 }; V.escolher(e2, 2); poe(e2, 14, 8, "leste"); const c = inim(e2, "bandido", 17, 8); V.atirar(e2); assert.equal(c.hp, 2, "a 3 passos: 3 de dano");
  const d = inim(e2, "capanga", 19, 8); V.atirar(e2); assert.equal(d.hp, 7, "a 5 passos: nada");
});
t("faca e mão livre só acertam quem está colado à frente; mão dá 1, faca 3", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 14, 8, "leste"); V.escolher(e, 3); const m = inim(e, "cao", 16, 8);
  assert(/Golpeou o ar/.test(msgs(V.atirar(e)))); m.x = 15; assert(/Acertou o cão selvagem/.test(msgs(V.atirar(e))) && m.hp === 1);
  V.escolher(e, 4); V.atirar(e); assert(m.hp <= 0); assert.equal(e.mun.revolver.carga, 6, "corpo a corpo não gasta bala");
});
t("trocar de arma: 1 a 4; sem a espingarda avisa; número inválido orienta", () => {
  const e = V.novo("normal", rn(1)); assert(/ainda não tem a espingarda/.test(msgs(V.escolher(e, 2)))); assert(/Arma: faca/.test(msgs(V.escolher(e, 3)))); assert(/Escolha uma arma/.test(msgs(V.escolher(e, 7))));
  assert(/Arma: revólver, 6 na arma e 12 de reserva/.test(msgs(V.comando(e, "arma revolver"))));
});
t("inimigo acorda perto, anuncia, anda até você pelo caminho (não atravessa parede) e ataca", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 14, 8, "leste"); const c = inim(e, "cao", 19, 8);
  let r = V.tick(e); assert(c.ativo && /Você ouve o cão selvagem à frente, a 5 passos/.test(msgs(r)), msgs(r)); assert.equal(c.x, 18); assert(/À vista: cão selvagem/.test(msgs(r)));
  for (let i = 0; i < 3; i++) r = V.tick(e); assert.equal(c.x, 15);
  const hp = e.hp; r = V.tick(e); assert(e.hp < hp && /Você levou/.test(msgs(r)), msgs(r));
  const f = V.novo("normal", rn(1)); sem(f); poe(f, 16, 7, "norte"); const dentro = inim(f, "rato", 15, 4); V.tick(f); assert(dentro.ativo); const p0 = [dentro.x, dentro.y]; V.tick(f); V.tick(f); assert.deepEqual([dentro.x, dentro.y], p0, "porta fechada segura o rato");
  f.abertas["0,16,5"] = true; for (let i = 0; i < 4; i++) V.tick(f); assert(dentro.y > 4 || dentro.x > 15, "com a porta aberta ele vem");
});
t("bandido atira quando tem linha de visão, a cada 4 passos de tempo, e o dano segue o nível", () => {
  const e = V.novo("normal", rn(7)); sem(e); poe(e, 14, 8, "leste"); const b = inim(e, "bandido", 18, 8); b.ativo = true; e.t = 1; let tiros = 0, danos = 0;
  for (let i = 0; i < 16; i++) { const r = V.tick(e); tiros += tipos(r).filter(x => x === "tiro-inimigo").length; danos += tipos(r).filter(x => x === "dano").length; }
  assert(tiros >= 2 && tiros <= 4, "tiros " + tiros); assert(danos >= 1 && e.hp < 20);
  const f = V.novo("facil", rn(7)); sem(f); poe(f, 14, 8, "leste"); const b2 = inim(f, "bandido", 17, 8); b2.ativo = true; for (let i = 0; i < 30; i++) V.tick(f); assert(f.hp > 30 - 20);
});
t("som dos inimigos: lado e distância relativos a quem olha (esquerda negativa)", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 14, 8, "leste"); const b = inim(e, "bandido", 17, 6); b.ativo = true; e.t = 1;
  const r = V.tick(e).filter(x => x.t === "inimigo"); assert(r.length === 1 && r[0].s < 0 && r[0].f > 0, JSON.stringify(r));
  poe(e, 14, 8, "oeste"); e.t = 3; const r2 = V.tick(e).filter(x => x.t === "inimigo"); assert(r2[0].f < 0, "atrás");
});
t("vitória ao derrubar o chefe; derrota quando a vida zera; depois disso nada mais acontece", () => {
  const e = V.novo("normal", rn(1)); sem(e); poe(e, 24, 11, "leste"); const ch = inim(e, "chefe", 25, 11); const r = V.atirar(e.arma === "revolver" ? (V.escolher(e, 3), e) : e);
  ch.hp = 1; const r2 = V.atirar(e); assert.equal(e.fim, "venceu"); assert(/O chefe dos bandidos caiu\. O vilarejo está livre/.test(msgs(r2)), msgs(r2)); assert.deepEqual(V.tick(e), []); assert.deepEqual(V.mover(e, "norte"), []);
  const f = V.novo("dificil", rn(1)); sem(f); poe(f, 14, 8, "leste"); const c = inim(f, "cao", 15, 8); c.ativo = true; f.hp = 1; f.t = 1; let r3 = []; for (let i = 0; i < 4 && !f.fim; i++) r3 = r3.concat(V.tick(f));
  assert.equal(f.fim, "perdeu"); assert(/Você caiu/.test(msgs(r3)));
});
t("status, olhar e ajuda falam tudo que importa", () => {
  const e = V.novo("normal", rn(1)); poe(e, 14, 8, "leste"); e.area = V.areaDe(0, 14, 8);
  assert(/Vida 20 de 20\. Arma: revólver, 6 na arma e 12 de reserva\. Kits médicos: 0\. Chaves: nenhuma\. Térreo, rua do vilarejo, olhando para leste\. Inimigos vivos: 11\./.test(V.status(e)), V.status(e));
  const o = V.olhar(e); assert(/rua do vilarejo, olhando para leste/.test(o) && /passos livres/.test(o), o);
  inim(e, "bandido", 17, 8); assert(/bandido à frente, a 3 passos/.test(V.olhar(e)), V.olhar(e));
  assert(/W norte, D leste, S sul, A oeste/.test(V.ajuda()) && /Shift direito recarrega/.test(V.ajuda()) && /1 a 4/.test(V.ajuda()));
  ["status", "e", "r", "olhar", "o", "ajuda", "h"].forEach(c => assert.equal(V.comando(e, c)[0].t, "info"));
  assert(/Não entendi/.test(msgs(V.comando(e, "dançar"))));
  assert.equal(V.comando(e, "ir norte")[0] && true, true);
});
t("comandos de texto cobrem teclado: norte, atirar, recarregar, mira, arma 3, pegar", () => {
  const e = V.novo("normal", rn(1)); sem(e);
  V.comando(e, "norte"); assert.equal(e.y, 7); V.comando(e, "mira esquerda"); assert.equal(e.mx, -1); V.comando(e, "mira cima"); assert.equal(e.my, 1); V.comando(e, "mira centro"); assert.equal(e.mx, 0);
  V.comando(e, "atirar"); assert.equal(e.mun.revolver.carga, 5); V.comando(e, "recarregar"); assert.equal(e.recarga, 2); V.comando(e, "3"); assert.equal(e.arma, "faca"); assert(/Nada para pegar/.test(msgs(V.comando(e, "pegar"))));
});
t("os sons e a fala existem: todo evento tem tipo, texto e nível de narração", () => {
  const e = V.novo("normal", rn(3)); poe(e, 14, 8, "leste"); inim(e, "bandido", 17, 8);
  let todos = []; for (let i = 0; i < 30 && !e.fim; i++) { todos = todos.concat(V.tick(e)); if (i % 3 === 0) todos = todos.concat(V.atirar(e)); if (i % 5 === 0) todos = todos.concat(V.mirar(e, 1, 0)); }
  todos.forEach(v => { assert.equal(typeof v.t, "string"); assert.equal(typeof v.msg, "string"); assert([1, 2, 3].includes(v.n)); });
});
console.log(`\n${ok} testes`);
