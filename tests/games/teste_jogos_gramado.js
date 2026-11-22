// Testes do campo minado de gramado: geração, movimento, sensor, bandeiras, dicas e níveis (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const G = require(path.join(__dirname, "..", "..", "games", "gramado.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const lcg = (seed) => { let x = seed; return (n) => { x = (x * 1103515245 + 12345) & 0x7fffffff; return (x >> 8) % n; }; };
const DIRS = { norte: -1, sul: 1, leste: 1, oeste: -1 };
// Plano de jogo perfeito: percorre as casas seguras por largura, a partir da casa 0, usando só movimentos retos.
function resolver(e) {
  const seg = []; for (let i = 0; i < e.cel.length; i++) if (!e.cel[i].mina) seg.push(i);
  const vis = new Set([0]), pai = {}, fila = [0], ordem = [0];
  while (fila.length) { const j = fila.shift(); G.vizinhas(e, j, false).forEach(k => { if (!e.cel[k].mina && !vis.has(k)) { vis.add(k); pai[k] = j; fila.push(k); ordem.push(k); } }); }
  return { ordem, pai };
}
function dirDe(e, de, para) { const d = para - de; return d === 1 ? "leste" : d === -1 ? "oeste" : d === e.c ? "sul" : "norte"; }
function caminho(e, de, para) { // caminho pelas casas já cortadas ou a cortar, só seguras
  const pr = { [de]: null }, fila = [de];
  while (fila.length) { const j = fila.shift(); if (j === para) break; G.vizinhas(e, j, false).forEach(k => { if (!e.cel[k].mina && !(k in pr)) { pr[k] = j; fila.push(k); } }); }
  const out = []; for (let k = para; k !== de; k = pr[k]) out.unshift(k); return out;
}

t("gerar: começo livre, quantidade de formigueiros certa e todas as casas seguras alcançáveis", () => {
  ["facil", "normal", "dificil"].forEach(nv => { for (let s = 1; s <= 60; s++) {
    const e = G.novo(nv, lcg(s)), N = G.NIVEIS[nv];
    assert.equal(e.cel.filter(c => c.mina).length, N.m); assert(!e.cel[0].mina && e.cel[0].cortada && e.cel[0].n === 0);
    assert(G.conexo(e), "casas seguras isoladas");
    e.cel.forEach((c, i) => assert.equal(c.n, G.vizinhas(e, i).filter(j => e.cel[j].mina).length));
  } });
});
t("andar: borda, voltar a casa cortada e número ao redor", () => {
  const e = G.novo("normal", lcg(3));
  assert(/Fim do gramado/.test(G.andar(e, "norte").msg) && /Fim do gramado/.test(G.andar(e, "oeste").msg));
  const r = G.comando(e, "leste"); assert(/Cortou/.test(r.msg) || /Crash/.test(r.msg));
  if (!e.fim) { assert(/voltou/.test(G.comando(e, "oeste").msg)); assert.equal(e.pos, 0); }
});
t("vencer: seguir o plano perfeito corta tudo e dá vitória, em todos os níveis", () => {
  ["facil", "normal", "dificil"].forEach(nv => { for (let s = 1; s <= 25; s++) {
    const e = G.novo(nv, lcg(s * 7)), { ordem } = resolver(e); let atual = 0, venceu = false;
    for (const alvo of ordem.slice(1)) { for (const k of caminho(e, atual, alvo)) { const rr = G.comando(e, dirDe(e, atual, k)); if (/Ganhou/.test(rr.msg)) venceu = true; atual = k; assert(!e.fim || e.fim === "ganhou", "perdeu no caminho seguro"); } }
    assert.equal(e.fim, "ganhou", nv + " seed " + s); assert(venceu);
  } });
});
t("formigueiro: no fácil o sensor avisa e marca; no normal e no difícil perde", () => {
  ["facil", "normal"].forEach(nv => {
    const e = G.novo(nv, lcg(11)); let bateu = false;
    for (let i = 0; i < e.cel.length && !bateu; i++) if (e.cel[i].mina) { // teletransporta ao lado de uma mina
      const viz = G.vizinhas(e, i, false).find(k => !e.cel[k].mina); e.pos = viz; e.cel[viz].cortada = true;
      const r = G.comando(e, dirDe(e, viz, i)); bateu = true;
      if (nv === "facil") { assert(/sensor apitou/.test(r.msg) && !e.fim && e.cel[i].marcada); assert(/bandeira/.test(G.comando(e, dirDe(e, viz, i)).msg)); }
      else { assert.equal(e.fim, "perdeu"); assert(/Crash/.test(r.msg)); assert(/terminou/.test(G.comando(e, "leste").msg)); }
    }
    assert(bateu);
  });
});
t("caminhada de vários passos para quando há aviso e respeita o limite", () => {
  const e = G.novo("facil", lcg(2)); e.cel.forEach(c => { c.mina = false; c.n = 0; }); e.m = 0; e.cel[5].mina = true; e.m = 1; e.cel.forEach((c, i) => c.n = G.vizinhas(e, i).filter(j => e.cel[j].mina).length);
  const r = G.comando(e, "leste 99"); assert(e.pos < 5 && /formigueiro/.test(r.msg)); const antes = e.pos; assert(antes > 0);
});
t("marcar: põe, tira, borda e casa já cortada", () => {
  const e = G.novo("normal", lcg(4));
  assert(/Bandeira posta/.test(G.comando(e, "marcar sul").msg) && e.marcadas === 1); assert(/bandeira/.test(G.comando(e, "sul").msg));
  assert(/Bandeira tirada/.test(G.comando(e, "marcar sul").msg) && e.marcadas === 0);
  assert(/Não há casa/.test(G.comando(e, "marcar norte").msg)); assert(/Marcar qual/.test(G.comando(e, "marcar").msg));
});
t("sensor, onde, mapa, resumo e ajuda são consultas que não mexem no jogo", () => {
  const e = G.novo("normal", lcg(8)), antes = JSON.stringify(e);
  assert(/linha 1, coluna 1/.test(G.comando(e, "onde").msg)); assert(/norte: borda/.test(G.comando(e, "sensor").msg));
  assert(/Linha 1\./.test(G.comando(e, "mapa").msg) && /você/.test(G.comando(e, "mapa").msg)); assert(/Faltam/.test(G.comando(e, "resumo").msg)); assert(/Comandos:/.test(G.comando(e, "ajuda").msg));
  assert.equal(JSON.stringify(e), antes); assert(/Não entendi/.test(G.comando(e, "dançar").msg)); assert(/Digite um comando/.test(G.comando(e, "").msg));
});
t("dica: sempre correta (nunca aponta casa segura que é mina) e respeita o limite do nível", () => {
  for (let s = 1; s <= 40; s++) {
    const e = G.novo("facil", lcg(s)), { ordem } = resolver(e);
    // abre metade do gramado seguro para haver o que deduzir
    ordem.slice(0, Math.ceil(ordem.length / 2)).forEach(i => { if (!e.cel[i].cortada) { e.cel[i].cortada = true; e.cortadas++; } });
    const sabe = G.deduzir(e); Object.keys(sabe).forEach(k => assert.equal(sabe[k] === "mina", e.cel[k].mina, "dedução errada"));
  }
  const n = G.novo("normal", lcg(1)); for (let i = 0; i < 3; i++) assert(/^Dica:/.test(G.comando(n, "dica").msg)); assert(/acabaram/.test(G.comando(n, "dica").msg));
  assert(/não há dicas/.test(G.comando(G.novo("dificil", lcg(1)), "dica").msg));
  const f = G.novo("facil", lcg(1)); for (let i = 0; i < 6; i++) assert(/^Dica:/.test(G.comando(f, "dica").msg));
});
t("comandos aceitam abreviações e 'ir'", () => {
  const e = G.novo("facil", lcg(6)); assert(/Cortou|voltou|Crash|sensor/.test(G.comando(e, "ir leste").msg)); assert(/Cortou|voltou|sensor|Crash|Fim/.test(G.comando(e, "s").msg));
});
console.log(ok + " testes do gramado passaram");
