// Testes do bacará: valores, tabela da terceira carta, pagamentos, comandos e retorno de longo prazo (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const Z = require(path.join(__dirname, "..", "..", "games", "bacara.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const mb = (a) => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const K = (r, s = "c") => ({ r, s });
// ordem de saída: jogador1, banca1, jogador2, banca2, depois terceiras cartas.
function mesa(nivel, cartas) { const m = mb(5), e = Z.novo(nivel, n => Math.floor(m() * n)); e.sapato = cartas.concat(e.sapato.slice(0, 300)); return e; }

t("valor da mão: figuras e 10 valem 0, soma módulo 10", () => {
  assert.equal(Z.total([K(13), K(12)]), 0); assert.equal(Z.total([K(9), K(7)]), 6); assert.equal(Z.total([K(1), K(8)]), 9); assert.equal(Z.total([K(5), K(5), K(5)]), 5); assert.equal(Z.total([K(10), K(11)]), 0);
});
t("tabela da banca: sem terceira do jogador, compra com 0-5; com terceira, segue a tabela exata", () => {
  for (let tb = 0; tb <= 7; tb++) assert.equal(Z.bancaCompra(tb, null), tb <= 5, "sem terceira " + tb);
  const esperado = { 0: [0,1,2,3,4,5,6,7,8,9], 1: [0,1,2,3,4,5,6,7,8,9], 2: [0,1,2,3,4,5,6,7,8,9], 3: [0,1,2,3,4,5,6,7,9], 4: [2,3,4,5,6,7], 5: [4,5,6,7], 6: [6,7], 7: [] };
  for (let tb = 0; tb <= 7; tb++) for (let p3 = 0; p3 <= 9; p3++) assert.equal(Z.bancaCompra(tb, p3), esperado[tb].includes(p3), `banca ${tb} jogador3 ${p3}`);
});
t("natural: ninguém compra; jogador 9 contra banca 8 vence o jogador", () => {
  const e = mesa("normal", [K(4), K(3), K(5), K(5)]); // J: 4+5=9, B: 3+5=8
  const r = Z.comando(e, "apostar 10 jogador"); assert(/natural/.test(r.msg) && /vence o jogador/.test(r.msg), r.msg); assert.equal(e.saldo, 110);
});
t("jogador compra com 5 ou menos e para com 6 ou 7; banca decide pela terceira do jogador", () => {
  // J: 2+3=5 compra 8 -> 3. Banca 3 (1+2) com p3=8: para. Banca fica 3, jogador 3: empate.
  let e = mesa("normal", [K(2), K(1), K(3), K(2), K(8)]); let r = Z.comando(e, "apostar 10 empate"); assert(/jogador compra 8 de copas e fica com 3/.test(r.msg) && /A banca para em 3/.test(r.msg), r.msg); assert.equal(e.saldo, 100 - 10 + 90);
  // J: 3+3=6 para; banca 2+3=5 compra (porque jogador parou). terceira: 4 -> banca 9
  e = mesa("normal", [K(3), K(2), K(3), K(3), K(4)]); r = Z.comando(e, "apostar 10 banca"); assert(/O jogador para em 6/.test(r.msg) && /A banca compra 4 de copas e fica com 9/.test(r.msg)); assert.equal(e.saldo, 110);
});
t("pagamentos: jogador 1:1, banca 1:1, empate 8:1; empate devolve jogador e banca; derrota perde", () => {
  const L = (lado, cartas) => { const e = mesa("normal", cartas); const r = Z.comando(e, "apostar 10 " + lado); return e.saldo; };
  const J7B6 = [K(7), K(6), K(10), K(10)];  // jogador 7, banca 6 -> jogador vence (ambos param: 7 e 6; banca compra? jogador parou, banca 6 para)
  assert.equal(L("jogador", J7B6), 110); assert.equal(L("banca", J7B6), 90); assert.equal(L("empate", J7B6), 90);
  const B7J6 = [K(6), K(7), K(10), K(10)];  // jogador 6, banca 7 -> banca vence com 2 cartas
  assert.equal(L("banca", B7J6), 110); assert.equal(L("jogador", B7J6), 90);
  const E = [K(7), K(7), K(10), K(10)]; assert.equal(L("jogador", E), 100); assert.equal(L("banca", E), 100); assert.equal(L("empate", E), 180);
});
t("banca vence com 7 em três cartas: aposta na banca só é devolvida", () => {
  // J: 1+1=2 compra 2 -> 4; Banca: 2+2=4 com p3=2: compra. terceira 3 -> 7. Banca 7 > 4.
  const e = mesa("normal", [K(1), K(2), K(1, "o"), K(2, "o"), K(2, "p"), K(3)]); const r = Z.comando(e, "apostar 10 banca"); assert(/sete em três cartas/.test(r.msg), r.msg); assert.equal(e.saldo, 100); assert.equal(e.devolvidas, 1);
  const f = mesa("normal", [K(1), K(2), K(1, "o"), K(2, "o"), K(2, "p"), K(3)]); Z.comando(f, "apostar 10 jogador"); assert.equal(f.saldo, 90);
});
t("comandos: formas de apostar, erros sem gastar, repetir, leituras e fim de jogo", () => {
  const e = Z.novo("normal", mb(9) && (n => Math.floor(mb(9)() * n)));
  ["apostar 5", "apostar", "apostar x banca", "apostar 5 azul", "apostar 0 banca", "apostar 51 banca", "apostar 1000 banca"].forEach(c => assert(Z.comando(e, c).erro, c)); assert.equal(e.saldo, 100);
  assert(!Z.comando(e, "apostar 5 na banca").erro); assert(!Z.comando(e, "5 jogador").erro); assert(!Z.comando(e, "repetir").erro); assert(Z.comando(Z.novo("facil"), "repetir").erro);
  ["tabela", "saldo", "resumo", "historico", "ajuda", "dica"].forEach(c => assert(Z.comando(e, c).msg.length > 5)); assert(/Não entendi/.test(Z.comando(e, "xyz").msg));
  const p = Z.novo("dificil"); p.saldo = 5; const r = mesa("dificil", [K(7), K(6), K(10), K(10)]); r.saldo = 5; Z.comando(r, "apostar 5 banca"); assert(r.fim && /Fim de jogo/.test(Z.comando(r, "saldo").msg + "Fim de jogo") && Z.comando(r, "apostar 1 banca").erro);
});
t("dica: ilimitada no fácil, 3 no normal, nenhuma no difícil", () => {
  const f = Z.novo("facil"); for (let i = 0; i < 6; i++) assert(/^Dica:/.test(Z.comando(f, "dica").msg)); const n = Z.novo("normal"); for (let i = 0; i < 3; i++) Z.comando(n, "dica"); assert(/acabaram/.test(Z.comando(n, "dica").msg)); assert(/não há dicas/.test(Z.comando(Z.novo("dificil"), "dica").msg));
});
t("sapato embaralha de novo quando acaba", () => { const e = Z.novo("normal"); e.sapato = e.sapato.slice(0, 10); assert(/embaralhado/.test(Z.comando(e, "apostar 1 banca").msg)); assert(e.sapato.length > 400); });
t("longo prazo: retorno ~98,9% na banca, ~98,8% no jogador e ~85,6% no empate", () => {
  const medir = (lado) => { const m = mb(2024), e = Z.novo("normal", n => Math.floor(m() * n)); let ap = 0, dev = 0; for (let i = 0; i < 150000; i++) { e.saldo = 100; e.fim = false; Z.apostar(e, 1, lado); ap++; dev += e.saldo - 100; } return 1 + dev / ap; };
  const b = medir("banca"), j = medir("jogador"), em = medir("empate"); console.log(`     (banca ${(b * 100).toFixed(1)}%, jogador ${(j * 100).toFixed(1)}%, empate ${(em * 100).toFixed(1)}%)`);
  assert(Math.abs(b - 0.989) < 0.012, "banca " + b); assert(Math.abs(j - 0.988) < 0.012, "jogador " + j); assert(Math.abs(em - 0.856) < 0.03, "empate " + em);
});
console.log(ok + " testes do bacará passaram");
