// Testes do sudoku: geração com solução única, regras, comandos, níveis e leitura (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const S = require(path.join(__dirname, "..", "..", "games", "sudoku.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const lcg = (seed) => { let x = seed; return (n) => { x = (x * 1103515245 + 12345) & 0x7fffffff; return (x >> 8) % n; }; };
const valida = (g) => { for (let k = 0; k < 9; k++) for (const f of [i => S.lin(i), i => S.col(i), i => S.quad(i)]) { const s = new Set(); for (let i = 0; i < 81; i++) if (f(i) === k) s.add(g[i]); if (s.size !== 9 || s.has(0)) return false; } return true; };

t("geração: solução válida, enunciado bate com ela, solução única e número de dados por nível", () => {
  const alvo = { facil: 40, normal: 32, dificil: 26 };
  for (const nv of Object.keys(alvo)) for (let s = 1; s <= 6; s++) {
    const e = S.novo(nv, lcg(s * 31)); assert(valida(e.solucao), "solução inválida");
    e.dado.forEach((v, i) => { if (v) assert.equal(v, e.solucao[i]); });
    assert.equal(S.contar(e.dado.slice(), 2), 1, "não é única"); assert.equal(e.dado.filter(Boolean).length, alvo[nv], nv);
  }
});
t("geração é rápida (30 tabuleiros em menos de 5 s)", () => {
  const t0 = Date.now(); for (let s = 1; s <= 10; s++) ["facil", "normal", "dificil"].forEach(nv => S.novo(nv, lcg(s))); assert(Date.now() - t0 < 5000, (Date.now() - t0) + " ms");
});
const montar = (nv) => S.novo(nv, lcg(7));
const vazia = (e) => { const i = e.dado.findIndex(x => !x); return { i, l: S.lin(i) + 1, c: S.col(i) + 1, v: e.solucao[i] }; };
t("colocar certo, vitória preenchendo tudo e tabuleiro completo depois", () => {
  const e = montar("normal"); let r;
  for (let i = 0; i < 81; i++) if (!e.dado[i]) r = S.comando(e, `colocar ${e.solucao[i]} em ${S.lin(i) + 1} ${S.col(i) + 1}`);
  assert.equal(e.fim, "vitoria"); assert(/Sudoku completo!/.test(r.msg), r.msg); assert(S.comando(e, "linha 1").msg.startsWith("Linha 1"));
  assert(S.comando(e, "colocar 1 em 1 1").erro);
});
t("recusas: casa do enunciado, conflito de linha/coluna/quadrante, valores fora de 1 a 9, formato errado", () => {
  const e = montar("normal"), d = e.dado.findIndex(x => x), { i, l, c } = vazia(e);
  let r = S.comando(e, `colocar 5 em ${S.lin(d) + 1} ${S.col(d) + 1}`); assert(r.erro && /enunciado/.test(r.msg));
  // monta um conflito de linha: outro número da mesma linha que já existe
  const ja = e.atual.findIndex((v, k) => v && S.lin(k) === S.lin(i)); r = S.comando(e, `colocar ${e.atual[ja]} em ${l} ${c}`); assert(r.erro && /Não dá: já existe um/.test(r.msg), r.msg);
  assert(S.comando(e, "colocar 0 em 1 1").erro && S.comando(e, "colocar 5 em 10 1").erro && S.comando(e, "colocar 5 em 3").erro);
  assert.equal(e.jogadas, 0);
});
t("nível fácil recusa número legal mas errado; normal aceita e verificar aponta; difícil não confere", () => {
  const achaErrado = (e) => { for (let i = 0; i < 81; i++) if (!e.dado[i]) for (const v of S.candidatos(e.atual, i)) if (v !== e.solucao[i]) return { i, v }; return null; };
  let e = montar("facil"), x = achaErrado(e); assert(x, "sem errado legal");
  let r = S.comando(e, `colocar ${x.v} em ${S.lin(x.i) + 1} ${S.col(x.i) + 1}`); assert(r.erro && /a solução é outra/.test(r.msg));
  e = montar("normal"); x = achaErrado(e); r = S.comando(e, `colocar ${x.v} em ${S.lin(x.i) + 1} ${S.col(x.i) + 1}`); assert(!r.erro, r.msg);
  assert(/1 número errado: linha \d, coluna \d/.test(S.comando(e, "verificar").msg)); assert(/está errado\. Apague-o/.test(S.comando(e, "dica").msg));
  S.comando(e, `apagar ${S.lin(x.i) + 1} ${S.col(x.i) + 1}`); assert(/está certo/.test(S.comando(e, "verificar").msg));
  e = montar("dificil"); assert(/não confere/.test(S.comando(e, "verificar").msg));
});
t("apagar, desfazer e resumo", () => {
  const e = montar("normal"), { i, l, c, v } = vazia(e);
  assert(S.comando(e, "desfazer").erro && /Não há jogada/.test(S.comando(e, "desfazer").msg));
  S.comando(e, `colocar ${v} em ${l} ${c}`); assert.equal(e.atual[i], v);
  assert(/Desfeito/.test(S.comando(e, "desfazer").msg) && e.atual[i] === 0);
  S.comando(e, `colocar ${v} em ${l} ${c}`); assert(/Apagado/.test(S.comando(e, `apagar ${l} ${c}`).msg) && e.atual[i] === 0);
  assert(S.comando(e, `apagar ${l} ${c}`).erro); assert(/Faltam \d+ casas\. Jogadas: 3\./.test(S.comando(e, "resumo").msg), S.comando(e, "resumo").msg);
  const d = e.dado.findIndex(x => x); assert(S.comando(e, `apagar ${S.lin(d) + 1} ${S.col(d) + 1}`).erro);
});
t("dicas: fácil ilimitada, normal 3, difícil nenhuma; a dica coloca o número certo", () => {
  let e = montar("facil"); for (let k = 0; k < 6; k++) assert(/Dica: na linha/.test(S.comando(e, "dica").msg)); assert.equal(e.atual.filter((v, i) => v && !e.dado[i]).length, 6);
  e.atual.forEach((v, i) => { if (v) assert.equal(v, e.solucao[i]); });
  e = montar("normal"); for (let k = 0; k < 3; k++) assert(!S.comando(e, "dica").erro); assert(/acabaram/.test(S.comando(e, "dica").msg));
  assert(/não há dicas/.test(S.comando(montar("dificil"), "dica").msg));
});
t("leitura: linha, coluna, quadrante, casa, faltam, vazias, tabuleiro", () => {
  const e = montar("normal");
  const l1 = S.comando(e, "linha 1").msg; assert(/^Linha 1, da coluna 1 à 9: (\d|vazia)(, (\d|vazia)){8}\.$/.test(l1), l1);
  assert(/^Coluna 5, da linha 1 à 9:/.test(S.comando(e, "coluna 5").msg) && /^Quadrante 5 \(linhas 4 a 6, colunas 4 a 6\): linha 4: /.test(S.comando(e, "quadrante 5").msg));
  const { l, c } = vazia(e); assert(new RegExp(`^Linha ${l}, coluna ${c} \\(quadrante \\d\\): vazia\\. Podem entrar: [1-9](, [1-9])*\\.`).test(S.comando(e, `casa ${l} ${c}`).msg));
  const d = e.dado.findIndex(x => x); assert(/número do enunciado/.test(S.comando(e, `casa ${S.lin(d) + 1} ${S.col(d) + 1}`).msg));
  assert(/^Linha 1: faltam [\d, ]+\.$|^Linha 1: está completa\./.test(S.comando(e, "faltam linha 1").msg), S.comando(e, "faltam linha 1").msg);
  assert(/^Casas vazias no coluna 1:|^Não há casas vazias/.test(S.comando(e, "vazias coluna 1").msg));
  assert.equal(S.comando(e, "tabuleiro").msg.split("Linha ").length, 10);
  assert(S.comando(e, "linha 10").msg.includes("inválida") && S.comando(e, "xyz").erro && /Colocar: colocar/.test(S.comando(e, "ajuda").msg));
});
t("formas de escrever o comando: 'colocar 5 em 3 4', '5 na linha 3 coluna 4' e maiúsculas", () => {
  const e = montar("normal"), { l, c, v } = vazia(e);
  assert(!S.comando(e, `${v} na linha ${l} coluna ${c}`).erro); S.comando(e, `apagar ${l} ${c}`); assert(!S.comando(e, `COLOCAR ${v} EM ${l} ${c}`).erro);
});
t("desistir mostra a solução e encerra", () => {
  const e = montar("normal"); const r = S.comando(e, "desistir"); assert(/A solução, linha por linha: Linha 1/.test(r.msg)); assert.equal(e.fim, "desistencia");
});
console.log(`${ok} testes do sudoku passaram`);
