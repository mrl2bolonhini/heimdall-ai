// Testes da batalha naval: frotas, tiros, leitura, comandos e a força de cada nível do computador (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const B = require(path.join(__dirname, "jogos", "naval.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const lcg = (seed) => { let x = seed; return (n) => { x = (x * 1103515245 + 12345) & 0x7fffffff; return (x >> 8) % n; }; };

t("frota: 5 navios nos tamanhos certos, dentro do tabuleiro, retos e sem sobreposição", () => {
  for (let s = 1; s <= 200; s++) {
    const f = B.frotaAleatoria(lcg(s)), usados = new Set();
    assert.deepEqual(f.navios.map(n => n.tam), [5, 4, 3, 3, 2]);
    f.navios.forEach(n => {
      assert.equal(n.cels.length, n.tam);
      n.cels.forEach(x => { assert(x >= 0 && x < 100); assert(!usados.has(x), "sobreposição"); usados.add(x); });
      const linhas = new Set(n.cels.map(x => Math.floor(x / 10))), cols = new Set(n.cels.map(x => x % 10));
      assert(n.horiz ? linhas.size === 1 && cols.size === n.tam : cols.size === 1 && linhas.size === n.tam, "navio torto");
    });
    assert.equal(usados.size, 17);
  }
});
t("casas: B7, tiro b7, 7b, j10, a1 e inválidas", () => {
  assert.equal(B.casa("B7"), 6 * 10 + 1); assert.equal(B.casa("tiro b7"), 61); assert.equal(B.casa("atirar em b 7"), 61); assert.equal(B.casa("7b"), 61);
  assert.equal(B.casa("j10"), 99); assert.equal(B.casa("a1"), 0);
  ["k1", "a11", "a0", "", "xyz", "b"].forEach(x => assert.equal(B.casa(x), -1, x));
  assert.equal(B.nome(0), "A1"); assert.equal(B.nome(99), "J10"); assert.equal(B.nome(61), "B7");
});
t("tiro: água, acerto, afunda e marca o navio todo como afundado", () => {
  const e = B.novo("normal", lcg(5)), nv = e.ele.navios[4];
  const agua = e.ele.grade.indexOf(-1); assert.equal(B.receber(e.ele, agua).tipo, "agua"); assert.equal(e.ele.tiros[agua], 1);
  assert.equal(B.receber(e.ele, nv.cels[0]).tipo, "acerto"); assert.equal(e.ele.tiros[nv.cels[0]], 2);
  const r = B.receber(e.ele, nv.cels[1]); assert.equal(r.tipo, "afundou"); assert(nv.afundado); assert(nv.cels.every(x => e.ele.tiros[x] === 3));
});
t("comando: tiro repetido e casa inválida não gastam a vez; tiro certo faz o computador responder", () => {
  const e = B.novo("normal", lcg(9));
  let r = B.comando(e, "zz"); assert(r.erro && /Não entendi/.test(r.msg)); assert.equal(e.turnos, 0);
  r = B.comando(e, "b7"); assert(!r.erro && /Você atirou em B7/.test(r.msg) && /O computador atirou em/.test(r.msg) && /Sua vez/.test(r.msg)); assert.equal(e.turnos, 1);
  r = B.comando(e, "tiro b7"); assert(r.erro && /já atirou em B7/.test(r.msg)); assert.equal(e.turnos, 1);
  assert.equal(e.eu.tiros.filter(Boolean).length, 1);
});
t("vitória: afundar toda a frota inimiga termina a partida", () => {
  const e = B.novo("facil", lcg(3)); let r;
  e.ele.navios.forEach(n => n.cels.forEach(x => { if (!e.fim) r = B.comando(e, B.nome(x)); }));
  assert.equal(e.fim, "vitoria"); assert(/Vitória/.test(r.msg)); assert(/terminou/.test(B.comando(e, "b1").msg));
});
t("leituras: frota, restantes, linha, coluna, tiros, inimigo, resumo, dica, ajuda", () => {
  const e = B.novo("normal", lcg(11)); const nv = e.ele.navios[0];
  assert(/Sua frota: porta-aviões, 5 casas, de [A-J]\d+ a [A-J]\d+, na (horizontal|vertical), intacto/.test(B.comando(e, "frota").msg));
  assert(/ainda ao mar: porta-aviões \(5\), encouraçado \(4\), cruzador \(3\), submarino \(3\) e destróier \(2\)\. Afundados: nenhum/.test(B.comando(e, "restantes").msg));
  assert(/Você ainda não atirou/.test(B.comando(e, "tiros").msg) && /computador ainda não atirou/.test(B.comando(e, "inimigo").msg));
  B.comando(e, "a1"); B.comando(e, "c1");
  assert(/Linha 1, seus tiros: A1 .*C1 /.test(B.comando(e, "linha 1").msg) && /Coluna A, seus tiros: A1 /.test(B.comando(e, "coluna a").msg) && /nenhum ainda/.test(B.comando(e, "linha 5").msg));
  assert(/Seus acertos:.*Suas águas:/.test(B.comando(e, "tiros").msg) && /Acertos do computador/.test(B.comando(e, "inimigo").msg));
  assert(/Você tem 5 navios e o inimigo tem 5/.test(B.comando(e, "resumo").msg) && /Sugestão: atire em [A-J]\d+\./.test(B.comando(e, "dica").msg) && /Colunas de A a J/.test(B.comando(e, "ajuda").msg));
  assert(/Linha inválida/.test(B.lerLinha(e, 11)) && /Coluna inválida/.test(B.lerColuna(e, "k")));
  assert(/Último|atirou/i.test(B.comando(e, "ultimo").msg));
});
t("desistir encerra com vitória do computador", () => {
  const e = B.novo("normal", lcg(2)); B.comando(e, "desistir"); assert.equal(e.fim, "derrota");
});
t("computador nunca repete casa e a partida sempre termina, nos três níveis", () => {
  ["facil", "normal", "dificil"].forEach(nv => { for (let s = 1; s <= 25; s++) {
    const e = B.novo(nv, lcg(s * 7)); let n = 0;
    while (!e.fim && n < 200) { const i = B.escolherTiro(e); assert.equal(e.eu.tiros[i], 0, "repetiu " + B.nome(i)); B.jogadaComputador(e); n++; }
    assert(e.fim === "derrota" && n <= 100, nv + " " + n);
  } });
});
t("força: média de tiros para afundar a frota é fácil > normal > difícil", () => {
  const media = (nv) => { let tot = 0, k = 60; for (let s = 1; s <= k; s++) { const e = B.novo(nv, lcg(s * 13 + 1)); let n = 0; while (!e.fim) { B.jogadaComputador(e); n++; } tot += n; } return tot / k; };
  const f = media("facil"), n = media("normal"), d = media("dificil");
  console.log("     médias: fácil " + f.toFixed(1) + ", normal " + n.toFixed(1) + ", difícil " + d.toFixed(1));
  assert(f > n + 5 && n > d + 3, [f, n, d].join(" "));
  assert(f > 80 && d < 55, "limites");
});
t("difícil: depois de um acerto, o próximo tiro é vizinho do acerto", () => {
  const e = B.novo("dificil", lcg(4)); const x = e.eu.navios[0].cels[1];
  e.eu.tiros[x] = 2; const i = B.escolherTiro(e); assert([x - 10, x + 10, x - 1, x + 1].includes(i), B.nome(i));
});
console.log(`${ok} testes da batalha naval passaram`);
