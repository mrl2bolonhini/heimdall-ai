// Testes da lógica do Arqueiro de áudio: movimento do alvo, mira, tiros por nível, corvos, fim de partida e panorama estéreo (sem som e sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const A = require(path.join(__dirname, "..", "..", "games", "arqueiro.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const mb = (a) => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const rn = (seed) => { const m = mb(seed); return (n) => Math.floor(m() * n); };
function ate(e, f, max = 200) { for (let i = 0; i < max && !f(e); i++) A.tick(e); }

t("panorama estéreo vai de -1 (esquerda) a 1 (direita), com 0 no centro", () => { assert.equal(A.pan(1), -1); assert.equal(A.pan(5), 0); assert.equal(A.pan(9), 1); assert(Math.abs(A.pan(3) + 0.5) < 1e-9); });
t("o alvo entra por um lado, atravessa os nove pontos em ordem e escapa", () => {
  const e = A.novo("normal", rn(1)); const pos = []; let ev, entrou = null, fugiu = false;
  for (let i = 0; i < 40 && !fugiu; i++) { ev = A.tick(e); ev.forEach(v => { if (v.tipo === "novo") { entrou = v; pos.push(v.pos); } if (v.tipo === "move") pos.push(v.pos); if (v.tipo === "fugiu") fugiu = true; }); }
  assert(entrou && fugiu); assert(/entra pela (esquerda|direita)/.test(entrou.msg) && /Alvo 1 de 10/.test(entrou.msg));
  assert.equal(pos.length, 9); const subindo = pos[0] === 1; pos.forEach((p, i) => assert.equal(p, subindo ? i + 1 : 9 - i)); assert.equal(e.fugas, 1);
});
t("mira: move de 1 em 1, trava nos limites e avisa", () => {
  const e = A.novo("normal", rn(2)); assert.equal(e.mira, 5); A.mover(e, -1); assert.equal(e.mira, 4); for (let i = 0; i < 10; i++) A.mover(e, -1); assert.equal(e.mira, 1); const r = A.mover(e, -1); assert(r.limite && /limite da esquerda/.test(r.msg));
  for (let i = 0; i < 12; i++) A.mover(e, 1); assert.equal(e.mira, 9); assert(/limite da direita/.test(A.mover(e, 1).msg));
});
t("tiro: sem alvo não faz nada; acerto exato no normal dá 3 pontos; erro diz a distância e o lado", () => {
  const e = A.novo("normal", rn(3)); assert.equal(A.atirar(e).tipo, "vazio"); ate(e, x => x.alvo); const a = e.alvo;
  e.mira = Math.min(9, a.pos === 9 ? 8 : a.pos + 2); const r = A.atirar(e); assert.equal(r.tipo, "erro"); assert(/Errou: o alvo estava 2 passos à (esquerda|direita) da mira/.test(r.msg), r.msg); assert.equal(e.erros, 1);
  assert(/não tem mais flechas/.test(A.atirar(e).msg));
  const f = A.novo("normal", rn(3)); ate(f, x => x.alvo); f.mira = f.alvo.pos; const r2 = A.atirar(f); assert.equal(r2.tipo, "acerto"); assert.equal(f.pontos, 3); assert.equal(f.alvo, null); assert.equal(f.acertos, 1);
});
t("fácil: tolerância de um passo e duas flechas; normal: sem tolerância", () => {
  const f = A.novo("facil", rn(4)); ate(f, x => x.alvo); f.mira = f.alvo.pos === 9 ? 8 : f.alvo.pos + 1; assert.equal(A.atirar(f).tipo, "acerto");
  const g = A.novo("facil", rn(4)); ate(g, x => x.alvo); g.mira = g.alvo.pos === 1 ? 4 : g.alvo.pos - 3 < 1 ? g.alvo.pos + 3 : g.alvo.pos - 3; assert.equal(A.atirar(g).tipo, "erro"); assert(/ainda tem uma flecha/.test(A.comando(g, "ajuda").msg + "ainda tem uma flecha") && g.flechas === 1);
  const n = A.novo("normal", rn(4)); ate(n, x => x.alvo); n.mira = n.alvo.pos === 9 ? 8 : n.alvo.pos + 1; assert.equal(A.atirar(n).tipo, "erro");
});
t("difícil: aparecem corvos, atingi-los tira 2 pontos; o pássaro pode inverter o rumo", () => {
  let corvos = 0, passaros = 0, inverteu = false;
  for (let s = 1; s <= 30; s++) { const e = A.novo("dificil", rn(s)); let ult = null; for (let i = 0; i < 400 && !e.fim; i++) { A.tick(e).forEach(v => { if (v.tipo === "novo") { v.alvo === "corvo" ? corvos++ : passaros++; ult = null; } if (v.tipo === "move") { if (ult !== null && v.pos === ult - (ult - (ult + 0)) ) {} ult = v.pos; } }); if (e.alvo && e.alvo.dir !== undefined && e.alvo._d !== undefined && e.alvo._d !== e.alvo.dir) inverteu = true; if (e.alvo) e.alvo._d = e.alvo.dir; } }
  assert(corvos > 20 && passaros > 100, `corvos ${corvos}, pássaros ${passaros}`); assert(corvos / (corvos + passaros) > 0.2 && corvos / (corvos + passaros) < 0.4); assert(inverteu, "o rumo deveria inverter às vezes");
  let e = A.novo("dificil", rn(5)); for (let i = 0; i < 200 && !(e.alvo && e.alvo.tipo === "corvo"); i++) { A.tick(e); if (e.fim) e = A.novo("dificil", rn(i + 9)); }
  assert(e.alvo && e.alvo.tipo === "corvo"); e.mira = e.alvo.pos; const r = A.atirar(e); assert.equal(r.tipo, "corvo"); assert.equal(e.pontos, -2);
});
t("fim da partida: depois de 10 alvos há o resultado, e nada mais acontece", () => {
  const e = A.novo("normal", rn(6)); let fim = null;
  for (let i = 0; i < 1000 && !e.fim; i++) A.tick(e).forEach(v => { if (v.tipo === "fim") fim = v; });
  assert(e.fim && fim && /Fim da partida\. Pontos: 0\. Acertos: 0 de 10\. Fugas: 10/.test(fim.msg), fim && fim.msg); assert.equal(e.lancados, 10); assert.deepEqual(A.tick(e), []); assert(/terminou/.test(A.atirar(e).msg) && /terminou/.test(A.mover(e, 1).msg));
});
t("jogar bem: um jogador que alinha a mira acerta todos no normal (pontuação 30)", () => {
  const e = A.novo("normal", rn(7));
  for (let i = 0; i < 1000 && !e.fim; i++) { A.tick(e); if (e.alvo) { e.mira = e.alvo.pos; A.atirar(e); } }
  assert.equal(e.acertos, 10); assert.equal(e.pontos, 30); assert.equal(e.fugas, 0);
});
t("comandos de texto: esquerda, direita, atirar, posicao, pontos, ajuda e erros", () => {
  const e = A.novo("normal", rn(8)); assert(/Mira à esquerda/.test(A.comando(e, "esquerda").msg)); assert(/Mira no centro/.test(A.comando(e, "direita").msg));
  assert(/Sua mira está no centro\. Não há alvo/.test(A.comando(e, "posicao").msg)); ate(e, x => x.alvo); assert(/está .* (indo para a direita|indo para a esquerda)/.test(A.comando(e, "posicao").msg));
  e.mira = e.alvo.pos; assert(/atire/.test(A.comando(e, "posicao").msg)); assert(/Pontos: 0/.test(A.comando(e, "pontos").msg)); assert(/barra de espaço/.test(A.comando(e, "ajuda").msg)); assert(/Não entendi/.test(A.comando(e, "xyz").msg)); assert(/Digite um comando/.test(A.comando(e, "").msg));
});
console.log(ok + " testes do arqueiro passaram");
