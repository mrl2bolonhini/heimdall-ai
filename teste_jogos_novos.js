// Lógica do caça-níqueis e do campo minado (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const J = (n) => require(path.join(__dirname, "jogos", n + ".js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };

const s = J("cacaniqueis");
t("caca-niqueis: trinca, sequências (subindo, descendo, com volta) e nada", () => {
  assert.equal(s.classificar([4, 4, 4]), "trinca"); assert.equal(s.classificar([0, 0, 0]), "trinca");
  [[1, 2, 3], [9, 0, 1], [8, 9, 0], [3, 2, 1], [1, 0, 9], [0, 9, 8]].forEach(d => assert.equal(s.classificar(d), "sequencia", d.join()));
  [[1, 3, 5], [1, 2, 4], [4, 4, 5], [1, 2, 1], [5, 3, 1], [7, 8, 7]].forEach(d => assert.equal(s.classificar(d), "nada", d.join()));
});
t("caca-niqueis: das 1000 combinações, 10 são trincas e 20 são sequências (sem sobreposição)", () => {
  let tr = 0, sq = 0; for (let a = 0; a < 10; a++) for (let b = 0; b < 10; b++) for (let c = 0; c < 10; c++) { const k = s.classificar([a, b, c]); if (k === "trinca") tr++; if (k === "sequencia") sq++; }
  assert.equal(tr, 10); assert.equal(sq, 20);
});
t("caca-niqueis: a aposta sai do saldo e o prêmio entra", () => {
  const e = s.novo(); assert.equal(e.creditos, 30);
  let r = s.girar(e, 1, [1, 3, 5]); assert.equal(e.creditos, 29); assert(/perdeu a aposta de 1 crédito/.test(r.msg), r.msg);
  r = s.girar(e, 2, [7, 7, 7]); assert.equal(e.creditos, 29 - 2 + 50); assert.equal(e.trincas, 1); assert(/Trinca/.test(r.msg));
  r = s.girar(e, 5, [2, 3, 4]); assert.equal(e.creditos, 77 - 5 + 50); assert.equal(e.sequencias, 1); assert.equal(e.maximo, 122);
});
t("caca-niqueis: fim por falta de créditos, aposta inválida e maior que o saldo", () => {
  const e = s.novo(); e.creditos = 1;
  assert(/Use 1, 2 ou 5/.test(s.girar(e, 3, [1, 3, 5]).erro)); assert(/só 1 crédito/.test(s.girar(e, 2, [1, 3, 5]).erro));
  const r = s.girar(e, 1, [1, 3, 5]); assert(e.fim && /Acabaram os créditos/.test(r.msg));
  assert(/acabaram/.test(s.girar(e, 1, [1, 3, 5]).erro));
});
t("caca-niqueis: dígitos falados em palavras e sorteio fica entre 0 e 9", () => {
  assert.equal(s.falarDigitos([0, 7, 9]), "zero, sete, nove");
  for (let i = 0; i < 300; i++) assert(s.sortear().every(x => x >= 0 && x <= 9 && Number.isInteger(x)));
});
t("caca-niqueis: retorno esperado fica abaixo de 100% (créditos de mentira, mas a casa ganha)", () => {
  const rtp = (10 * s.PREMIOS.trinca + 20 * s.PREMIOS.sequencia) / 1000; assert(rtp < 1 && rtp > 0.2, rtp);
});

const m = J("minas");
const semRnd = (n) => 0;
t("minas: primeira jogada nunca é mina e abre uma área", () => {
  for (let k = 0; k < 200; k++) { const e = m.novo("medio"); const r = m.abrir(e, 5, 5); assert(!e.fim, "perdeu na primeira"); assert(e.abertas >= 1); assert(e.cel.filter(c => c.mina).length === 10); }
});
t("minas: contagem de vizinhas confere com as minas", () => {
  const e = m.novo("medio"); m.abrir(e, 1, 1);
  e.cel.forEach((c, i) => assert.equal(c.n, m.vizinhas(e, i).filter(j => e.cel[j].mina).length));
});
t("minas: abrir mina perde e mostra a mina", () => {
  const e = m.novo("facil"); m.colocar(e, m.idx(e, 3, 3), semRnd); const mina = e.cel.findIndex(c => c.mina);
  const r = m.abrir(e, Math.floor(mina / e.c) + 1, (mina % e.c) + 1); assert.equal(e.fim, "perdeu"); assert(/Bum/.test(r.msg));
  assert(/mina/.test(m.lerCasa(e, Math.floor(mina / e.c) + 1, (mina % e.c) + 1)));
  assert(/terminou/.test(m.abrir(e, 1, 1).msg));
});
t("minas: ganhar abrindo todas as casas seguras", () => {
  const e = m.novo("facil"); m.abrir(e, 3, 3);
  for (let i = 0; i < e.cel.length && !e.fim; i++) if (!e.cel[i].mina && !e.cel[i].aberta) m.abrir(e, Math.floor(i / e.c) + 1, (i % e.c) + 1);
  assert.equal(e.fim, "ganhou"); assert.equal(m.seguras(e), 0);
});
t("minas: marcar, desmarcar, não abre casa marcada nem marca casa aberta", () => {
  const e = m.novo("facil"); m.abrir(e, 3, 3);
  const fechada = e.cel.findIndex(c => !c.aberta); const r = Math.floor(fechada / e.c) + 1, c = (fechada % e.c) + 1;
  assert(/Marcou/.test(m.marcar(e, r, c).msg) && e.marcadas === 1); assert(/marcada com bandeira/.test(m.abrir(e, r, c).msg));
  assert(/Desmarcou/.test(m.marcar(e, r, c).msg) && e.marcadas === 0);
  const aberta = e.cel.findIndex(x => x.aberta); assert(/já está aberta/.test(m.marcar(e, Math.floor(aberta / e.c) + 1, (aberta % e.c) + 1).msg));
});
t("minas: leitura de linha agrupa casas iguais", () => {
  const e = m.novo("facil"); assert.equal(m.lerLinha(e, 1), "Linha 1. colunas 1 a 6: fechadas."); assert.equal(m.lerColuna(e, 2), "Coluna 2. linhas 1 a 6: fechadas.");
  assert(/não existe/.test(m.lerLinha(e, 9))); assert(/não existe/.test(m.lerCasa(e, 0, 1)));
});
t("minas: comandos de texto, inclusive números soltos e coordenadas inválidas", () => {
  const e = m.novo("facil");
  assert(/Faltam|abriu|Linha 3/i.test(m.comando(e, "abrir 3 3").msg)); assert(e.iniciado);
  assert(/já está aberta/.test(m.comando(e, "3 3").msg));
  assert(/Marcou/.test(m.comando(e, "marcar 1 1").msg) || /já está aberta/.test(m.comando(e, "marcar 1 1").msg));
  assert(/Linha 3\./.test(m.comando(e, "ler 3").msg)); assert(/Coluna 2\./.test(m.comando(e, "ler coluna 2").msg));
  assert(/Linha 3, coluna 3:/.test(m.comando(e, "ler 3 3").msg)); assert(/Nível fácil/.test(m.comando(e, "resumo").msg));
  assert(/não existe/.test(m.comando(e, "abrir 9 9").msg)); assert(/Informe a linha e a coluna/.test(m.comando(e, "abrir 3").msg));
  assert(/Não entendi/.test(m.comando(e, "dançar").msg)); assert(/Comandos:/.test(m.comando(e, "ajuda").msg));
});
t("minas: nível difícil tem 144 casas e 25 minas", () => { const e = m.novo("dificil"); assert.equal(e.cel.length, 144); m.abrir(e, 6, 6); assert.equal(e.cel.filter(c => c.mina).length, 25); });
console.log(ok + " testes dos jogos novos passaram");
