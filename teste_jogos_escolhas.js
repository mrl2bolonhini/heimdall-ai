// Testes da aventura de escolhas com lógica: jogo perfeito, erros por nível, dica do rio e consultas (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const G = require(path.join(__dirname, "jogos", "escolhas.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const idx = (e, id) => G.escolhas(e).findIndex(o => o.id === id) + 1;
function jogarRio(e) { for (let i = 0; i < 20 && e.cena === "rio"; i++) { const id = G.proximoRio(e)[0]; assert(G.escolher(e, idx(e, id)).msg); } }
function perfeito(e) {
  G.escolher(e, idx(e, "barca")); assert.equal(e.cena, "rio"); jogarRio(e); assert.equal(e.cena, "portas");
  G.escolher(e, 2); assert.equal(e.cena, "guardas"); G.escolher(e, idx(e, "B")); assert.equal(e.sub, 1); return G.escolher(e, idx(e, "dir"));
}
t("jogo perfeito vence em todos os níveis, sem perder vida", () => {
  ["facil", "normal", "dificil"].forEach(nv => { const e = G.novo(nv), r = perfeito(e); assert.equal(e.fim, "vitoria", nv); assert.equal(e.erros, 0); assert(/ganhou/.test(r.msg)); assert(/terminou/.test(G.comando(e, "1").msg)); });
});
t("rio: a solução mínima tem 7 viagens e nunca deixa perigo", () => {
  const e = G.novo("normal"); G.escolher(e, 1); let n = 0;
  while (e.cena === "rio") { const id = G.proximoRio(e)[0]; G.escolher(e, idx(e, id)); n++; assert(n < 20); }
  assert.equal(n, 7); assert.equal(e.erros, 0);
});
t("rio: no fácil o jogo avisa do perigo e não castiga; no normal castiga e recomeça; no difícil perde", () => {
  let e = G.novo("facil"); G.escolher(e, 1); const r = G.escolher(e, idx(e, "sozinho")); assert(/Melhor não/.test(r.msg) && e.erros === 0 && e.passosRio === 0);
  e = G.novo("normal"); G.escolher(e, 1); const r2 = G.escolher(e, idx(e, "sozinho")); assert(/perdeu uma vida/.test(r2.msg) && e.vidas === 2 && e.passosRio === 0 && e.rio.barco === 0);
  e = G.novo("dificil"); G.escolher(e, 1); G.escolher(e, idx(e, "sozinho")); assert.equal(e.fim, "derrota");
});
t("nadar custa vida (normal), bilhete não custa", () => {
  const e = G.novo("normal"); assert(/Prefeita/.test(G.escolher(e, 3).msg) && e.vidas === 3); G.escolher(e, 2); assert.equal(e.vidas, 2); assert.equal(e.cena, "inicio");
});
t("portas: só a 2 passa; 1 e 3 explicam o erro", () => {
  const e = G.novo("normal"); G.escolher(e, 1); jogarRio(e);
  assert(/porta 1/.test(G.escolher(e, 1).msg) && e.cena === "portas" && e.vidas === 2);
  assert(/porta 3/.test(G.escolher(e, 3).msg) && e.vidas === 1); G.escolher(e, 2); assert.equal(e.cena, "guardas");
});
t("guardas: erros explicados, derrota quando acabam as vidas", () => {
  const e = G.novo("normal"); G.escolher(e, 1); jogarRio(e); G.escolher(e, 2);
  assert(/impossível/.test(G.escolher(e, idx(e, "A")).msg)); assert(/mentissem/.test(G.escolher(e, idx(e, "ambos")).msg)); assert.equal(e.vidas, 1);
  G.escolher(e, idx(e, "B")); assert(/sem saída/.test(G.escolher(e, idx(e, "esq")).msg)); assert.equal(e.fim, "derrota");
});
t("dica: ilimitada no fácil, 3 no normal, nenhuma no difícil; dica do rio é um passo válido", () => {
  const f = G.novo("facil"); for (let i = 0; i < 6; i++) assert(/^Dica:/.test(G.comando(f, "dica").msg));
  const n = G.novo("normal"); for (let i = 0; i < 3; i++) assert(/^Dica:/.test(G.comando(n, "dica").msg)); assert(/acabaram/.test(G.comando(n, "dica").msg));
  assert(/não há dicas/.test(G.comando(G.novo("dificil"), "dica").msg));
  const e = G.novo("facil"); G.escolher(e, 1); assert(/galinha/.test(G.comando(e, "dica").msg));
});
t("comandos: número fora da faixa, repetir, resumo, ajuda, escolha N e texto estranho", () => {
  const e = G.novo("normal");
  assert(/Escolha de 1 a 3/.test(G.comando(e, "9").msg)); assert(/Escolhas:/.test(G.comando(e, "repetir").msg)); assert(/Vidas: 3/.test(G.comando(e, "resumo").msg));
  assert(/Digite o número/.test(G.comando(e, "ajuda").msg)); assert(/Prefeita/.test(G.comando(e, "escolha 3").msg)); assert(/Não entendi/.test(G.comando(e, "xyz").msg)); assert(/Digite o número/.test(G.comando(e, "").msg));
  assert.equal(e.vidas, 3);
});
console.log(ok + " testes da aventura de escolhas passaram");
