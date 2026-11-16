// Testes do blackjack: valores, rodadas com sapato combinado, pagamentos, dobrar, dividir, estratégia e balanço de longo prazo (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const B = require(path.join(__dirname, "jogos", "blackjack.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const lcg = (seed) => { let x = seed; return (n) => { x = (x * 1103515245 + 12345) & 0x7fffffff; return (x >> 8) % n; }; };
const K = (r, s = "c") => ({ r, s });
// Monta uma partida com o sapato combinado: ordem de saída = jogador1, jogador2, banca1, banca2 e depois as demais.
function mesa(nivel, cartas) { const e = B.novo(nivel, lcg(1)); e.sapato = cartas.concat(e.sapato.slice(0, 200)); return e; }

t("valor: ases valem 11 ou 1, figuras 10, blackjack só com duas cartas", () => {
  assert.deepEqual(B.valor([K(1), K(13)]), { total: 21, suave: true }); assert.equal(B.valor([K(1), K(1), K(9)]).total, 21); assert.equal(B.valor([K(1), K(1), K(10), K(10)]).total, 22);
  assert.equal(B.valor([K(10), K(6), K(5)]).total, 21); assert(B.ehBlackjack([K(1), K(12)])); assert(!B.ehBlackjack([K(5), K(6), K(10)]));
  assert.equal(B.valor([K(1), K(6)]).suave, true); assert.equal(B.valor([K(1), K(6), K(10)]).suave, false);
});
t("sapato: 4 baralhos no fácil, 6 nos outros; começa no saldo do nível", () => {
  assert.equal(B.novo("facil").sapato.length, 208); assert.equal(B.novo("normal").sapato.length, 312); assert.equal(B.novo("dificil").saldo, 60); assert.equal(B.novo("normal").saldo, 100);
});
t("aposta: só pares de 2 a 50, dentro do saldo; erros não gastam nada", () => {
  const e = B.novo("normal", lcg(2));
  ["apostar 3", "apostar 1", "apostar 52", "apostar 0", "apostar"].forEach(c => { const r = B.comando(e, c); assert(r.erro && e.saldo === 100, c); });
  const p = B.novo("dificil", lcg(2)); p.saldo = 10; assert(/só 10/.test(B.comando(p, "apostar 20").msg)); assert.equal(p.saldo, 10);
  assert(/Ainda não há aposta/.test(B.comando(B.novo("normal", lcg(2)), "repetir").msg));
});
t("vitória simples: 20 contra 18 paga o dobro", () => {
  const e = mesa("normal", [K(10), K(10), K(10), K(8)]); B.comando(e, "apostar 10"); assert.equal(e.saldo, 90);
  const r = B.comando(e, "parar"); assert(/você ganhou, você recebe 20/.test(r.msg), r.msg); assert.equal(e.saldo, 110); assert.equal(e.fase, "apostar"); assert.equal(e.vitorias, 1);
});
t("blackjack natural paga 3 para 2; blackjack dos dois empata; banca com blackjack vence", () => {
  let e = mesa("normal", [K(1), K(13), K(10), K(9)]); let r = B.comando(e, "apostar 10"); assert(/blackjack! Paga 3 para 2, você recebe 25/.test(r.msg), r.msg); assert.equal(e.saldo, 115); assert.equal(e.blackjacks, 1);
  e = mesa("normal", [K(1), K(13), K(1, "o"), K(12)]); r = B.comando(e, "apostar 10"); assert(/empate/.test(r.msg)); assert.equal(e.saldo, 100);
  e = mesa("normal", [K(10), K(9), K(1), K(13)]); r = B.comando(e, "apostar 10"); assert(/a banca tem blackjack/.test(r.msg)); assert.equal(e.saldo, 90); assert.equal(e.fase, "apostar");
});
t("estourar perde sem a banca jogar; banca compra até 17 e para no 17", () => {
  let e = mesa("normal", [K(10), K(6), K(10), K(7), K(9)]); B.comando(e, "apostar 10"); let r = B.comando(e, "pedir"); assert(/Estourou/.test(r.msg) && /perdeu/.test(r.msg)); assert.equal(e.saldo, 90); assert.equal(e.banca.length, 2);
  e = mesa("normal", [K(10), K(9), K(10), K(6), K(9)]); B.comando(e, "apostar 10"); r = B.comando(e, "parar"); assert.equal(e.banca.length, 3); assert(/estourou/.test(r.msg) && e.saldo === 110, r.msg);
  e = mesa("normal", [K(10), K(8), K(1), K(6), K(10)]); B.comando(e, "apostar 10"); B.comando(e, "parar"); assert.equal(e.banca.length, 2, "17 suave: a banca para"); 
});
t("empate devolve a aposta", () => {
  const e = mesa("normal", [K(10), K(8), K(10), K(8)]); B.comando(e, "apostar 10"); const r = B.comando(e, "parar"); assert(/empate/.test(r.msg)); assert.equal(e.saldo, 100); assert.equal(e.empates, 1);
});
t("dobrar: uma carta, aposta dobrada, só nas duas primeiras, e precisa de saldo", () => {
  let e = mesa("normal", [K(5), K(6), K(10), K(7), K(10)]); B.comando(e, "apostar 10"); const r = B.comando(e, "dobrar"); assert(/dobrada para 20/.test(r.msg) && /você ganhou, você recebe 40/.test(r.msg), r.msg); assert.equal(e.saldo, 120);
  e = mesa("normal", [K(2), K(3), K(10), K(7), K(2), K(9)]); B.comando(e, "apostar 10"); B.comando(e, "pedir"); assert(B.comando(e, "dobrar").erro);
  e = B.novo("normal", lcg(3)); e.saldo = 10; e.sapato = [K(5), K(6), K(10), K(7)].concat(e.sapato); B.comando(e, "apostar 10"); assert(B.comando(e, "dobrar").erro && /igualar/.test(B.comando(e, "dobrar").msg));
});
t("dividir: duas mãos, aposta em cada, cada uma jogada e paga separadamente; 21 depois de dividir não é blackjack", () => {
  const e = mesa("normal", [K(8), K(8, "o"), K(10), K(7), K(3), K(10), K(2), K(9), K(10, "p")]);
  B.comando(e, "apostar 10"); let r = B.comando(e, "dividir"); assert(/duas mãos/.test(r.msg) && e.maos.length === 2 && e.saldo === 80, r.msg); assert.equal(e.maos[0].cartas.length, 2);
  B.comando(e, "parar"); assert.equal(e.ativa, 1); assert.equal(e.maos[1].cartas.length, 2); r = B.comando(e, "parar"); assert(/Mão 1/.test(r.msg) && /Mão 2/.test(r.msg), r.msg); assert.equal(e.fase, "apostar");
  assert(B.comando(e, "dividir").erro);
  const f = mesa("normal", [K(1), K(1, "o"), K(10), K(7), K(13), K(10)]); B.comando(f, "apostar 10"); const rf = B.comando(f, "dividir"); assert(/ases, cada mão recebe só uma carta/.test(rf.msg), rf.msg);
  assert(!/blackjack!/.test(rf.msg), "21 depois de dividir ases não é blackjack natural"); assert.equal(f.fase, "apostar"); assert.equal(f.saldo, 100 - 20 + 20 + 20, "duas vitórias de 21 contra 17");
});
t("sapato embaralha de novo quando acaba, e a rodada continua jogável", () => {
  const e = B.novo("normal", lcg(4)); e.sapato = e.sapato.slice(0, 20); const r = B.comando(e, "apostar 2"); assert(/embaralhado/.test(r.msg)); assert(e.sapato.length > 250);
});
t("comandos de leitura não mudam o jogo; erros fora de hora; fim de jogo quando acaba o saldo", () => {
  const e = mesa("dificil", [K(10), K(7), K(10), K(9)]); const antes = e.saldo;
  ["mao", "banca", "saldo", "tabela", "resumo", "ajuda"].forEach(c => assert(B.comando(e, c).msg.length > 5)); assert.equal(e.saldo, antes);
  assert(B.comando(e, "pedir").erro); assert(B.comando(e, "parar").erro); assert(/Não entendi/.test(B.comando(e, "xyz").msg));
  e.saldo = 2; B.comando(e, "apostar 2"); B.comando(e, "pedir"); B.comando(e, "pedir"); B.comando(e, "pedir"); // chega a perder em algum momento
  for (let i = 0; i < 40 && !e.fim; i++) { if (e.fase === "apostar") { if (e.saldo >= 2) B.comando(e, "apostar 2"); } else B.comando(e, "pedir"); }
  assert(e.fim || e.saldo >= 2); if (e.fim) assert(/terminou|acabaram/.test(B.comando(e, "mao").msg + B.comando(e, "apostar 2").msg));
});
t("dica: limites por nível; estratégia: 16 contra 10 pede, 12 contra 6 para, 11 dobra, par de 8 divide, par de 10 para", () => {
  const f = B.novo("facil", lcg(5)); for (let i = 0; i < 8; i++) assert(/^Dica:/.test(B.comando(f, "dica").msg));
  const n = B.novo("normal", lcg(5)); for (let i = 0; i < 5; i++) B.comando(n, "dica"); assert(/acabaram/.test(B.comando(n, "dica").msg)); assert(/não há dicas/.test(B.comando(B.novo("dificil", lcg(5)), "dica").msg));
  const s = (a, b, up) => { const e = mesa("normal", [K(a), K(b), K(up, "o"), K(2, "p")]); B.comando(e, "apostar 2"); return B.sugestao(e); };
  assert.equal(s(10, 6, 10), "pedir"); assert.equal(s(10, 2, 6), "parar"); assert.equal(s(5, 6, 6), "dobrar"); assert.equal(s(8, 8, 10), "dividir"); assert.equal(s(10, 10, 6), "parar"); assert.equal(s(1, 7, 9), "pedir"); assert.equal(s(1, 7, 7), "parar");
  assert.equal(s(10, 7, 10), "parar"); assert.equal(s(1, 6, 5), "dobrar"); assert.equal(s(1, 6, 10), "pedir"); assert.equal(s(1, 8, 6), "parar"); assert.equal(s(1, 7, 5), "dobrar");
});
t("longo prazo: com a estratégia básica a banca leva pouco (retorno entre 96% e 101% em 60 mil rodadas)", () => {
  let apostado = 0, devolvido = 0; const rnd = lcg(99);
  const e = B.novo("normal", rnd);
  for (let i = 0; i < 60000; i++) {
    e.saldo = 1000; e.fim = false; const antes = e.saldo; let guarda = 0;
    B.apostar(e, 2); let gasto = 2;
    while (e.fase === "jogar" && guarda++ < 30) {
      const s = B.sugestao(e), sb = e.saldo, r = s === "dobrar" ? B.dobrar(e) : s === "dividir" ? B.dividir(e) : s === "pedir" ? B.pedir(e) : B.parar(e);
      assert(!r.erro, s + " " + r.msg);
    }
    // o gasto real é aposta inicial mais dobros e divisões: usa a diferença de saldo e as apostas das mãos
    const total = e.maos.reduce((a, m) => a + m.aposta, 0); apostado += total; devolvido += total + (e.saldo - antes);
  }
  const rtp = devolvido / apostado; console.log("     (retorno medido: " + (rtp * 100).toFixed(1) + "%)"); assert(rtp > 0.96 && rtp < 1.01, "retorno " + rtp);
});
console.log(ok + " testes do blackjack passaram");
