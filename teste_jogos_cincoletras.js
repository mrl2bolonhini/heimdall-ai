// Testes do jogo Cinco letras (estilo Wordle em português), sem navegador.
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const W = require(path.join(__dirname, "jogos", "cincoletras.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const lcg = (seed) => { let x = seed; return (n) => { x = (x * 1103515245 + 12345) & 0x7fffffff; return (x >> 8) % n; }; };

t("lista: todas as palavras têm 5 letras sem acento, sem repetição, e há pelo menos 400", () => {
  assert(W.PALAVRAS.length >= 400, W.PALAVRAS.length);
  W.PALAVRAS.forEach(w => { assert.equal(W.plano(w).length, 5, w); assert(/^[a-z]{5}$/.test(W.plano(w)), w); });
  assert.equal(new Set(W.PALAVRAS.map(W.plano)).size, W.PALAVRAS.length, "repetidas");
});
t("avaliar: certas, lugar errado e letras repetidas contam só as que existem", () => {
  assert.deepEqual(W.avaliar("carro", "carro"), [2, 2, 2, 2, 2]);
  assert.deepEqual(W.avaliar("carro", "arroz"), [1, 1, 2, 1, 0]);
  assert.deepEqual(W.avaliar("festa", "fofos"), [2, 0, 0, 0, 1]);
  assert.deepEqual(W.avaliar("abade", "aaaaa"), [2, 0, 2, 0, 0]);
  assert.deepEqual(W.avaliar("sobre", "esses"), [1, 1, 0, 0, 0]);
});
t("acentos não importam: ação/coração e maiúsculas", () => {
  const e = W.novo("normal", null, "avião"); assert.equal(e.alvo, "aviao");
  const r = W.palpitar(e, "AVIÃO"); assert(e.fim === "vitoria" && /A palavra é AVIÃO, em 1 tentativa\./.test(r.msg), r.msg);
});
t("palpite inválido ou repetido não gasta tentativa", () => {
  const e = W.novo("normal", null, "carro");
  let r = W.palpitar(e, "casa"); assert(r.erro && /exatamente 5 letras/.test(r.msg));
  r = W.palpitar(e, "cabras"); assert(r.erro);
  W.palpitar(e, "arroz"); r = W.palpitar(e, "arroz"); assert(r.erro && /já tentou/.test(r.msg)); assert.equal(e.tentativas.length, 1);
});
t("leitura da tentativa e fim por falta de tentativas", () => {
  const e = W.novo("normal", null, "carro"); let r = W.comando(e, "arroz");
  assert(/Tentativa 1 de 6, ARROZ: A: em outro lugar, R: em outro lugar, R: lugar certo, O: em outro lugar, Z: não tem\. Restam 5 tentativas\./.test(r.msg), r.msg);
  ["festa", "viver", "norte", "livre"].forEach(p => W.comando(e, p));
  r = W.comando(e, "bolsa"); assert(e.fim === "derrota" && /A palavra era CARRO/.test(r.msg), r.msg);
  assert(W.comando(e, "mundo").erro);
});
t("níveis: fácil 8 tentativas, normal 6, difícil 6", () => {
  assert.equal(W.novo("facil").cfg.tent, 8); assert.equal(W.novo("normal").cfg.tent, 6); assert.equal(W.novo("dificil").cfg.tent, 6);
});
t("pistas, letras e tentativas", () => {
  const e = W.novo("normal", null, "carro"); assert(/Ainda não há pistas/.test(W.comando(e, "pistas").msg));
  W.comando(e, "arroz");
  const p = W.comando(e, "pistas").msg;
  assert(/Lugares conhecidos: traço, traço, R, traço, traço/.test(p) && /em outro lugar: A, O/.test(p) && /não têm: Z/.test(p), p);
  assert(/Letras ainda não testadas: B, C, D/.test(W.comando(e, "letras").msg) && !/Z/.test(W.comando(e, "letras").msg.replace("Letras ainda não testadas", "")));
  assert(/Tentativa 1, ARROZ:/.test(W.comando(e, "tentativas").msg));
});
t("dica: fácil ilimitada, normal uma vez, difícil nenhuma; revela letra verdadeira e entra nas pistas", () => {
  const f = W.novo("facil", lcg(1), "carro"); for (let i = 0; i < 5; i++) { const m = W.comando(f, "dica").msg; assert(/Dica: a letra da posição \d é [A-Z]\./.test(m) || /todas as letras/.test(m), m); }
  const n = W.novo("normal", lcg(2), "carro"), m1 = W.comando(n, "dica").msg; const pos = Number(m1.match(/posição (\d)/)[1]), letra = m1.match(/é ([A-Z])/)[1];
  assert.equal(letra.toLowerCase(), "carro"[pos - 1]); assert(/já foi usada/.test(W.comando(n, "dica").msg)); assert(/Lugares conhecidos/.test(W.comando(n, "pistas").msg));
  assert(/não há dicas/.test(W.comando(W.novo("dificil"), "dica").msg));
});
t("difícil: precisa manter letras certas no lugar e usar as que já existem", () => {
  const e = W.novo("dificil", null, "carro"); W.comando(e, "arroz");
  let r = W.comando(e, "festa"); assert(r.erro && /posição 3/.test(r.msg), r.msg);
  r = W.comando(e, "burro"); assert(r.erro && /precisa usar a letra A/.test(r.msg), r.msg);
  r = W.comando(e, "barro"); assert(!r.erro, r.msg);
});
t("sorteio fica dentro da lista e desistir revela a palavra", () => {
  for (let i = 0; i < 50; i++) assert(W.PALAVRAS.includes(W.novo("normal").palavra));
  const e = W.novo("normal", null, "farol"); assert(/A palavra era FAROL/.test(W.comando(e, "desistir").msg));
});
console.log(`${ok} testes do Cinco letras passaram`);
