// Testes da roleta: cores, pagamentos, comandos de aposta, saldo, repetir, níveis e retorno de longo prazo (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const R = require(path.join(__dirname, "jogos", "roleta.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const mb = (a) => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const lcg = (seed) => { let x = seed; return (n) => { x = (x * 1103515245 + 12345) & 0x7fffffff; return (x >> 8) % n; }; };

t("cores: 18 vermelhos, 18 pretos, zero verde", () => {
  let v = 0, p = 0; for (let n = 1; n <= 36; n++) R.cor(n) === "vermelho" ? v++ : p++; assert.equal(v, 18); assert.equal(p, 18); assert.equal(R.cor(0), "verde"); assert.equal(R.cor(R.DUPLO), "verde");
  assert.equal(R.cor(1), "vermelho"); assert.equal(R.cor(2), "preto"); assert.equal(R.cor(36), "vermelho"); assert.equal(R.cor(17), "preto");
});
t("cada tipo de aposta cobre o número certo de casas (e zero nunca ganha fora do número)", () => {
  const cont = (a) => { let c = 0; for (let n = 0; n <= 36; n++) if (R.ganhou(a, n)) c++; return c; };
  assert.equal(cont({ tipo: "numero", alvo: 17 }), 1); assert.equal(cont({ tipo: "cor", alvo: "vermelho" }), 18); assert.equal(cont({ tipo: "par", alvo: "par" }), 18); assert.equal(cont({ tipo: "par", alvo: "impar" }), 18);
  assert.equal(cont({ tipo: "alto", alvo: "alto" }), 18); assert.equal(cont({ tipo: "alto", alvo: "baixo" }), 18); [1, 2, 3].forEach(k => { assert.equal(cont({ tipo: "duzia", alvo: k }), 12); assert.equal(cont({ tipo: "coluna", alvo: k }), 12); });
  assert(!R.ganhou({ tipo: "cor", alvo: "vermelho" }, 0) && !R.ganhou({ tipo: "par", alvo: "par" }, 0) && !R.ganhou({ tipo: "alto", alvo: "baixo" }, 0)); assert(R.ganhou({ tipo: "numero", alvo: 0 }, 0));
  assert(R.ganhou({ tipo: "coluna", alvo: 1 }, 1) && R.ganhou({ tipo: "coluna", alvo: 3 }, 36) && R.ganhou({ tipo: "coluna", alvo: 2 }, 35));
});
t("pagamentos: número 36x, dúzia 3x, vermelho 2x, com o saldo certo", () => {
  let e = R.novo("facil", lcg(1)); R.comando(e, "apostar 10 no 17"); assert.equal(e.saldo, 90); let r = R.girar(e, 17); assert.equal(e.saldo, 90 + 360); assert(/ganhou em número 17, recebe 360/.test(r.msg));
  e = R.novo("facil", lcg(1)); R.comando(e, "apostar 10 duzia 2"); R.comando(e, "apostar 5 vermelho"); r = R.girar(e, 14); assert.equal(e.saldo, 85 + 30 + 10); assert(/Você lucrou 25/.test(r.msg), r.msg);
  e = R.novo("facil", lcg(1)); R.comando(e, "apostar 10 preto"); r = R.girar(e, 0); assert.equal(e.saldo, 90); assert(/verde/.test(r.msg) && /perdeu 10/.test(r.msg));
  e = R.novo("facil", lcg(1)); R.comando(e, "apostar 4 zero"); R.girar(e, 0); assert.equal(e.saldo, 96 + 144);
});
t("comandos de aposta: formas aceitas e erros sem gastar nada", () => {
  const e = R.novo("facil", lcg(2));
  ["apostar 5 vermelho", "apostar 5 preto", "apostar 2 par", "apostar 2 impar", "apostar 1 alto", "apostar 1 baixo", "apostar 3 duzia 1", "apostar 3 coluna 2", "apostar 1 no 17", "apostar 1 numero 36", "apostar 1 zero", "5 vermelho"].forEach(c => assert(!R.comando(e, c).erro, c));
  const s = e.saldo; ["apostar", "apostar 5", "apostar x vermelho", "apostar 5 azul", "apostar 5 duzia 4", "apostar 5 coluna", "apostar 5 37", "apostar 1000 vermelho", "apostar 5 duplo zero"].forEach(c => assert(R.comando(e, c).erro, c)); assert.equal(e.saldo, s);
  assert(/somada/.test(R.comando(e, "apostar 1 zero").msg) && /Aposte em quê/.test(R.comando(e, "apostar 5 no").msg));
});
t("apostar de novo na mesma coisa soma; limpar devolve; repetir refaz; girar sem aposta é erro", () => {
  const e = R.novo("facil", lcg(3)); assert(R.comando(e, "girar").erro); R.comando(e, "apostar 5 vermelho"); R.comando(e, "apostar 5 vermelho"); assert.equal(e.apostas.length, 1); assert.equal(e.apostas[0].valor, 10); assert.equal(e.saldo, 90);
  assert(/10 créditos devolvidos/.test(R.comando(e, "limpar").msg)); assert.equal(e.saldo, 100); assert(R.comando(e, "repetir").erro);
  R.comando(e, "apostar 5 vermelho"); R.comando(e, "apostar 5 no 1"); R.girar(e, 2); assert.equal(e.apostas.length, 0); const r = R.comando(e, "repetir"); assert(/repetidas/.test(r.msg) && e.apostas.length === 2); assert(R.comando(e, "repetir").erro);
});
t("duplo zero só na difícil", () => {
  const e = R.novo("dificil", lcg(4)); assert(e.duplo); assert(!R.comando(e, "apostar 5 duplo zero").erro); assert(!R.comando(e, "apostar 5 00").erro); R.girar(e, R.DUPLO); assert(/duplo zero, verde/.test(R.comando(e, "historico").msg) || /duplo zero/.test(R.comando(e, "historico").msg));
  assert(!R.novo("normal", lcg(4)).duplo);
});
t("fim de jogo quando o saldo chega a zero; leituras sem efeito", () => {
  const e = R.novo("normal", lcg(5)); R.comando(e, "apostar 60 vermelho"); const r = R.girar(e, 0); assert(e.fim && /Fim de jogo/.test(r.msg)); assert(R.comando(e, "apostar 1 vermelho").erro);
  const f = R.novo("facil", lcg(6)); ["tabela", "saldo", "resumo", "apostas", "historico", "ajuda"].forEach(c => assert(R.comando(f, c).msg.length > 5)); assert.equal(f.saldo, 100); assert(/Não entendi/.test(R.comando(f, "xyz").msg)); assert(/ainda não girou/.test(R.comando(f, "historico").msg));
});
t("longo prazo: retorno de ~97,3% (europeia) e ~94,7% (americana)", () => {
  [["facil", 0.973], ["dificil", 0.947]].forEach(([nv, esperado]) => {
    let ap = 0, dev = 0; const mr = mb(12345), e = R.novo(nv, (n) => Math.floor(mr() * n));
    for (let i = 0; i < 200000; i++) {
      e.saldo = 1000; const tipos = ["cor vermelho", "numero 7", "duzia 1", "par"], x = tipos[i % 4];
      R.comando(e, x === "numero 7" ? "apostar 1 no 7" : x === "cor vermelho" ? "apostar 1 vermelho" : x === "duzia 1" ? "apostar 1 duzia 1" : "apostar 1 par"); const antes = e.saldo; const r = R.girar(e); ap += 1; dev += e.saldo - antes;
    }
    const rtp = dev / ap; console.log("     (" + nv + ": retorno medido " + (rtp * 100).toFixed(1) + "%)"); assert(Math.abs(rtp - esperado) < 0.015, nv + " " + rtp);
  });
});
console.log(ok + " testes da roleta passaram");
