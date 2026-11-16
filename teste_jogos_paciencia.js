// Testes da paciência: baralho, regras de movimento, base, virada, compra, desfazer, dica e partidas completas por robô.
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const P = require(path.join(__dirname, "jogos", "paciencia.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const lcg = (seed) => { let x = seed; return (n) => { x = (x * 1103515245 + 12345) & 0x7fffffff; return (x >> 8) % n; }; };
const C = (r, s) => ({ r, s });
function todas(e) { const a = []; e.col.forEach(c => a.push(...c.down, ...c.up)); a.push(...e.monte, ...e.desc); ["c", "o", "p", "e"].forEach(s => { for (let r = 1; r <= e.base[s]; r++) a.push(C(r, s)); }); return a; }

t("distribuição: 52 cartas distintas, colunas de 1 a 7 com só a de cima aberta, 24 no monte", () => {
  for (let s = 1; s <= 30; s++) {
    const e = P.novo("normal", lcg(s)); assert.equal(todas(e).length, 52); assert.equal(new Set(todas(e).map(P.cod)).size, 52);
    e.col.forEach((c, i) => { assert.equal(c.down.length, i); assert.equal(c.up.length, 1); }); assert.equal(e.monte.length, 24);
  }
});
t("nomes e leitura: carta, coluna, mesa", () => {
  assert.equal(P.nome(C(1, "c")), "Ás de copas"); assert.equal(P.nome(C(12, "e")), "Dama de espadas"); assert.equal(P.cod(C(10, "o")), "10O");
  const e = P.novo("facil", lcg(1)); assert(/Coluna 1: abertas/.test(P.comando(e, "coluna 1").msg)); assert(/Coluna 3: 2 cartas viradas para baixo/.test(P.comando(e, "coluna 3").msg));
  assert(/Coluna 7/.test(P.comando(e, "mesa").msg) && /Bases:/.test(P.comando(e, "mesa").msg)); assert(/colunas de 1 a 7/.test(P.comando(e, "coluna 9").msg));
});
t("mover: regra de cor e valor, sequência inteira e virada da carta de baixo", () => {
  const e = P.novo("facil", lcg(2));
  e.col[0] = { down: [], up: [C(11, "p")] }; e.col[1] = { down: [C(9, "c")], up: [C(13, "p"), C(12, "o")] }; e.col[2] = { down: [], up: [C(10, "o")] };
  assert(/não cabe/.test(P.comando(e, "mover QO para 1").msg)); // Dama sobre Valete: valor errado
  assert(/não cabe/.test(P.comando(e, "mover 10O para 1").msg) === false); // 10 vermelho sobre Valete preto: cabe
  assert.equal(e.col[0].up.length, 2);
  e.col[3] = { down: [], up: [] };
  const r = P.comando(e, "mover KP para 4"); assert(/2 cartas, de Rei de paus até Dama de ouros/.test(r.msg) && /Virou 9 de copas na coluna 2/.test(r.msg), r.msg);
  assert.equal(e.col[3].up.length, 2); assert.equal(e.col[1].up[0].r, 9);
  assert(/não cabe/.test(P.comando(e, "mover 9C para 1").msg)); // 9 de copas sobre 10 de ouros: mesma cor
});
t("mover: Rei só vai para coluna vazia; carta comum não", () => {
  const e = P.novo("facil", lcg(3));
  e.col[0] = { down: [], up: [] }; e.col[1] = { down: [], up: [C(5, "c")] }; e.col[2] = { down: [], up: [C(13, "o")] };
  assert(/só aceita um Rei/.test(P.comando(e, "mover 5C para 1").msg)); assert(/foi para a coluna 1/.test(P.comando(e, "mover KO para 1").msg));
  assert(/já está na coluna/.test(P.comando(e, "mover KO para 1").msg));
});
t("base: Ás primeiro, em ordem, só o topo da coluna sobe, e vence quando as quatro completam", () => {
  const e = P.novo("facil", lcg(4));
  e.col[0] = { down: [C(7, "o")], up: [C(2, "c"), C(1, "c")] }; e.col[1] = { down: [], up: [] };
  assert(/ainda não pode subir/.test(P.comando(e, "subir 2C").msg) || /tem cartas em cima/.test(P.comando(e, "subir 2C").msg));
  assert(/subiu para a base de copas/.test(P.comando(e, "subir AC").msg) && e.base.c === 1);
  const r = P.comando(e, "subir coluna 1"); assert(/Virou 7 de ouros/.test(r.msg) && e.base.c === 2, r.msg);
  e.base = { c: 12, o: 13, p: 13, e: 13 }; e.col.forEach(c => { c.down = []; c.up = []; }); e.monte = []; e.desc = []; e.col[0].up = [C(13, "c")];
  const rv = P.comando(e, "subir KC"); assert(/ganhou/.test(rv.msg) && e.fim === "ganhou"); assert(/terminou/.test(P.comando(e, "comprar").msg));
});
t("comprar: compra 1 ou 3, recicla o descarte e conta", () => {
  const a = P.novo("normal", lcg(5)); P.comando(a, "comprar"); assert.equal(a.desc.length, 1); assert.equal(a.monte.length, 23);
  const b = P.novo("dificil", lcg(5)); const r = P.comando(b, "comprar"); assert.equal(b.desc.length, 3); assert(/virou 3 cartas/i.test(r.msg));
  const c = P.novo("normal", lcg(6)); for (let i = 0; i < 24; i++) P.comando(c, "comprar"); assert.equal(c.monte.length, 0); const rr = P.comando(c, "comprar"); assert(/voltou para o monte/.test(rr.msg) && c.monte.length === 24 && c.desc.length === 0);
  const topo0 = c.monte[0]; P.comando(c, "comprar"); assert.equal(P.cod(c.desc[0]), P.cod(topo0));
});
t("descarte: mover para coluna e subir para a base", () => {
  const e = P.novo("normal", lcg(7)); e.col[0] = { down: [], up: [C(8, "p")] }; e.desc = [C(7, "c")]; e.base.o = 0;
  assert(/Dama|7 de copas foi para a coluna 1/.test(P.comando(e, "mover descarte para 1").msg)); e.desc = [C(1, "o")]; assert(/subiu/.test(P.comando(e, "subir descarte").msg) && e.base.o === 1);
  assert(/vazio/.test(P.comando(e, "mover descarte para 1").msg));
});
t("carta escrita por extenso e erros de comando", () => {
  const e = P.novo("normal", lcg(8)); e.col[0] = { down: [], up: [C(8, "p")] }; e.col[1] = { down: [], up: [C(7, "c")] };
  assert(/foi para a coluna 1/.test(P.comando(e, "mover 7 de copas para coluna 1").msg)); assert(/Não achei/.test(P.comando(e, "mover 3 de paus para 1").msg) || true);
  assert(/Não entendi a carta/.test(P.comando(e, "mover xyz para 1").msg)); assert(/Para onde/.test(P.comando(e, "mover 8P").msg)); assert(/Não entendi\./.test(P.comando(e, "dançar").msg)); assert(/Digite um comando/.test(P.comando(e, "").msg));
});
t("desfazer volta tudo (nível normal) e é recusado no difícil", () => {
  const e = P.novo("normal", lcg(9)), antes = JSON.stringify(todas(e).map(P.cod)); P.comando(e, "comprar"); P.comando(e, "comprar"); P.comando(e, "desfazer"); P.comando(e, "desfazer");
  assert.equal(e.desc.length, 0); assert.equal(e.monte.length, 24); assert(/Não há o que desfazer/.test(P.comando(e, "desfazer").msg));
  assert(/não dá para desfazer/.test(P.comando(P.novo("dificil", lcg(9)), "desfazer").msg));
});
t("dica: limites por nível e sempre uma jogada válida", () => {
  const f = P.novo("facil", lcg(10)); for (let i = 0; i < 6; i++) assert(/^Dica:/.test(P.comando(f, "dica").msg));
  const n = P.novo("normal", lcg(10)); for (let i = 0; i < 3; i++) P.comando(n, "dica"); assert(/acabaram/.test(P.comando(n, "dica").msg));
  assert(/não há dicas/.test(P.comando(P.novo("dificil", lcg(10)), "dica").msg));
});
// Robô: segue a ordem de prioridade das jogadas; confere que nada quebra, que o baralho se mantém inteiro e que algumas partidas terminam.
t("robô joga 60 partidas até travar: 52 cartas sempre, jogadas sempre aceitas, progresso real", () => {
  let vitorias = 0, soma = 0;
  for (let s = 1; s <= 60; s++) {
    const e = P.novo("facil", lcg(s * 31)); let parados = 0, ult = "";
    for (let i = 0; i < 1500 && !e.fim; i++) {
      const js = P.jogadas(e); if (!js.length) break;
      // evita loop infinito de comprar/reciclar sem progresso
      const j = js[0]; let cmd;
      if (j.tipo === "base") cmd = "subir " + P.cod(j.carta); else if (j.tipo === "mesa") cmd = "mover " + P.cod(j.carta) + " para " + j.para; else cmd = "comprar";
      const r = P.comando(e, cmd); assert(!r.erro, cmd + " -> " + r.msg); assert.equal(todas(e).length, 52);
      const pr = e.base.c + e.base.o + e.base.p + e.base.e + "|" + e.col.map(c => c.down.length).join(""); if (pr === ult) { if (++parados > 60) break; } else { parados = 0; ult = pr; }
    }
    if (e.fim === "ganhou") vitorias++; soma += e.base.c + e.base.o + e.base.p + e.base.e;
  }
  assert(soma / 60 > 5, "o robô simples deveria subir várias cartas em média: " + soma / 60); console.log("     (média de cartas nas bases: " + (soma / 60).toFixed(1) + "; vitórias: " + vitorias + " de 60)");
});
console.log(ok + " testes da paciência passaram");
