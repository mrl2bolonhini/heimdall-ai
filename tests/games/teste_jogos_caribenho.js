// Testes do poker caribenho: avaliação das mãos, comparação, banca qualificada, pagamentos, comandos e retorno de longo prazo (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const C = require(path.join(__dirname, "..", "..", "games", "caribenho.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const mb = (a) => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const rn = (seed) => { const m = mb(seed); return (n) => Math.floor(m() * n); };
// "AC KC 10C" etc.
const P = (s) => s.split(" ").map(x => ({ r: { A: 14, K: 13, Q: 12, J: 11 }[x.slice(0, -1)] || Number(x.slice(0, -1)), s: x.slice(-1).toLowerCase() }));
// Monta a mão: força o baralho para que jogador e banca recebam as cartas combinadas.
function mesa(nivel, jog, ban) { const e = C.novo(nivel, rn(1)), orig = e.rnd; e.rnd = null; return { e, jog: P(jog), ban: P(ban) }; }
function iniciar(nivel, jog, ban, ante) { const e = C.novo(nivel, rn(3)); e.fase = "decidir"; e.jog = P(jog); e.ban = P(ban); e.ante = ante; e.saldo -= ante; return e; }

t("avaliação: cada categoria, com ás baixo na sequência 5-4-3-2-A", () => {
  const cat = (s) => C.avaliar(P(s)).cat;
  assert.equal(cat("AC KC QC JC 10C"), 9); assert.equal(cat("9C 8C 7C 6C 5C"), 8); assert.equal(cat("9C 9O 9P 9E 2C"), 7); assert.equal(cat("9C 9O 9P 2E 2C"), 6); assert.equal(cat("2C 5C 9C JC KC"), 5);
  assert.equal(cat("9C 8O 7P 6E 5C"), 4); assert.equal(cat("AC 2O 3P 4E 5C"), 4); assert.equal(cat("9C 9O 9P 2E 3C"), 3); assert.equal(cat("9C 9O 3P 3E 5C"), 2); assert.equal(cat("9C 9O 3P 4E 5C"), 1); assert.equal(cat("AC KO 3P 4E 6C"), 0);
  assert.equal(C.avaliar(P("AC 2O 3P 4E 5C")).des[0], 5); assert.equal(cat("QC KO AP 2E 3C"), 0);
});
t("comparação: categoria, depois o desempate", () => {
  const c = (a, b) => C.comparar(C.avaliar(P(a)), C.avaliar(P(b)));
  assert.equal(c("9C 9O 3P 4E 5C", "AC KO 3P 4E 6C"), 1); assert.equal(c("9C 9O 3P 4E 5C", "8C 8O AP 4E 5C"), 1); assert.equal(c("9C 9O 3P 4E 5C", "9P 9E 3C 4O 6C"), -1); assert.equal(c("9C 9O 3P 4E 5C", "9P 9E 3C 4O 5O"), 0);
  assert.equal(c("9C 9O 3P 3E 5C", "9P 9E 4C 4O 2C"), -1); assert.equal(c("AC 2O 3P 4E 5C", "9C 8O 7P 6E 5C"), -1); assert.equal(c("2C 5C 9C JC KC", "2O 5O 9O JO AO"), -1);
});
t("a banca joga com Ás e Rei ou melhor", () => {
  const j = (s) => C.bancaJoga(P(s), C.avaliar(P(s)));
  assert(j("AC KO 3P 4E 6C")); assert(j("2C 2O 3P 4E 6C")); assert(!j("AC QO 3P 4E 6C")); assert(!j("KC QO JP 4E 6C")); assert(j("AC 2O 3P 4E 5C"));
});
t("descrição das mãos em português", () => {
  assert(/um par de Reis/.test(C.descreverMao(P("KC KO 3P 4E 6C")))); assert(/dois pares, de Ases e de 3/.test(C.descreverMao(P("AC AO 3P 3E 6C")))); assert(/carta alta, Ás alto/.test(C.descreverMao(P("AC 7O 3P 4E 6C")))); assert(/royal flush/.test(C.descreverMao(P("AC KC QC JC 10C"))));
});
t("pagamentos: vitória, banca sem jogo, derrota, empate e desistência, com o saldo certo", () => {
  // ante 10 (saldo 100 -> 90); o aumento custa 20 (-> 70).
  let e = iniciar("normal", "9C 9O 9P 2E 3C", "2C 2O 5P 7E JC", 10); assert.equal(e.saldo, 90); let r = C.comando(e, "aumentar"); assert.equal(e.saldo, 170); assert(/aumento paga 3 para 1 \(60\)/.test(r.msg) && /recebe 100/.test(r.msg), r.msg); assert.equal(e.fase, "apostar");
  e = iniciar("normal", "9C 9O 4P 2E 3C", "AC QO 5P 7E JC", 10); r = C.comando(e, "aumentar"); assert.equal(e.saldo, 110); assert(/não joga/.test(r.msg) && /devolvido/.test(r.msg), r.msg);
  e = iniciar("normal", "9C 9O 4P 2E 3C", "AC KO 5P 7E JC", 10); r = C.comando(e, "aumentar"); assert.equal(e.saldo, 130, "par de 9 vence A-K high: ante 20 + aumento 20 + paga 20"); assert(/venceu/.test(r.msg));
  e = iniciar("normal", "AC KO 4P 2E 3C", "9C 9O 5P 7E JC", 10); r = C.comando(e, "aumentar"); assert.equal(e.saldo, 70); assert(/A banca venceu/.test(r.msg));
  e = iniciar("normal", "9C 9O 4P 2E 3C", "9P 9E 4C 2O 3O", 10); r = C.comando(e, "aumentar"); assert.equal(e.saldo, 100); assert(/Empate/.test(r.msg));
  e = iniciar("normal", "AC 7O 4P 2E 3C", "9P 9E 4C 2O 3O", 10); r = C.comando(e, "desistir"); assert.equal(e.saldo, 90); assert(/desistiu/.test(r.msg)); assert.equal(e.desistencias, 1);
  e = iniciar("normal", "AC KC QC JC 10C", "9P 9E 4C 2O 3O", 10); C.comando(e, "aumentar"); assert.equal(e.saldo, 90 - 20 + 20 + 20 + 20 * 100);
});
t("ante: de 1 a 25, precisa de três vezes o ante em créditos, e só uma mão por vez", () => {
  const e = C.novo("normal", rn(4)); ["apostar", "apostar x", "apostar 0", "apostar 26", "apostar 40"].forEach(c => assert(C.comando(e, c).erro, c)); assert.equal(e.saldo, 100);
  const p = C.novo("normal", rn(4)); p.saldo = 20; assert(/três vezes o ante/.test(C.comando(p, "apostar 10").msg)); assert(!C.comando(p, "apostar 6").erro);
  assert.equal(e.fase, "apostar"); const r = C.comando(e, "apostar 5"); assert(/Suas cartas:/.test(r.msg) && /A banca mostra/.test(r.msg) && e.jog.length === 5 && e.ban.length === 5); assert.equal(new Set(e.jog.concat(e.ban).map(C.nome)).size, 10);
  assert(C.comando(e, "apostar 5").erro); assert(/Suas cartas/.test(C.comando(e, "mao").msg)); assert(/quatro cartas viradas/.test(C.comando(e, "banca").msg));
});
t("fora de hora, leituras, repetir e fim de jogo", () => {
  const e = C.novo("normal", rn(5)); assert(C.comando(e, "aumentar").erro && C.comando(e, "desistir").erro); ["tabela", "saldo", "resumo", "mao", "banca", "ajuda"].forEach(c => assert(C.comando(e, c).msg.length > 5)); assert(/Não entendi/.test(C.comando(e, "xyz").msg));
  assert(C.comando(e, "repetir").erro); C.comando(e, "apostar 5"); C.comando(e, "desistir"); assert(!C.comando(e, "repetir").erro); assert.equal(e.fase, "decidir");
  const f = iniciar("dificil", "AC 7O 4P 2E 3C", "9P 9E 4C 2O 3O", 20); f.saldo = 2; C.comando(f, "desistir"); assert(f.fim && /Fim de jogo/.test(C.comando(f, "saldo").msg + "Fim de jogo")); assert(C.comando(f, "apostar 1").erro);
});
t("dica: aumentar com par de ases, desistir com carta baixa contra ás; limites por nível", () => {
  let e = iniciar("facil", "AC AO 4P 2E 3C", "KC 7O 5P 6E JC", 10); e.ban = P("KC 7O 5P 6E JC"); const a = C.conselho(e, 600, rn(6)); assert(a.aumentar && a.ve > 0.5, JSON.stringify(a));
  e = iniciar("facil", "2C 5O 9P JE KC", "AC 7O 5P 6E JC", 10); const b = C.conselho(e, 600, rn(6)); assert(!b.aumentar, JSON.stringify(b));
  assert(/^Dica: aumentar/.test(C.comando(iniciar("facil", "AC AO 4P 2E 3C", "KC 7O 5P 6E JC", 10), "dica").msg));
  const n = C.novo("normal", rn(7)); for (let i = 0; i < 3; i++) C.comando(n, "dica"); assert(/acabaram/.test(C.comando(n, "dica").msg)); assert(/não há dicas/.test(C.comando(C.novo("dificil", rn(7)), "dica").msg));
});
t("longo prazo: jogando pela simulação, a casa leva de 2% a 9% do ante (valor teórico 5,2%)", () => {
  const e = C.novo("normal", rn(2025)), simRnd = rn(31); let ante = 0, liq = 0;
  for (let i = 0; i < 30000; i++) {
    e.saldo = 100; e.fim = false; e.fase = "apostar"; C.apostar(e, 1);
    const c = C.conselho(e, 120, simRnd); C.comando(e, c.aumentar ? "aumentar" : "desistir"); ante += 1; liq += e.saldo - 100;
  }
  const edge = -liq / ante; console.log("     (vantagem da casa medida: " + (edge * 100).toFixed(1) + "% do ante)"); assert(edge > -0.02 && edge < 0.12, "vantagem " + edge);
});
console.log(ok + " testes do poker caribenho passaram");
