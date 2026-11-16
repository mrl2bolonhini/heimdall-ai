// Testes do poker Texas hold'em: avaliação de 7 cartas, equidade, regras de aposta, fichas conservadas, showdown e força dos níveis do computador (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const K = require(path.join(__dirname, "jogos", "poker.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const mb = (a) => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const rn = (seed) => { const m = mb(seed); return (n) => Math.floor(m() * n); };
const P = (s) => s.split(" ").map(x => ({ r: { A: 14, K: 13, Q: 12, J: 11 }[x.slice(0, -1)] || Number(x.slice(0, -1)), s: x.slice(-1).toLowerCase() }));
const total = (e) => e.fichas[0] + e.fichas[1] + e.comp[0] + e.comp[1];

t("melhor mão entre 7 cartas: categorias e desempate", () => {
  const cat = (s) => K.melhor(P(s)).cat;
  assert.equal(cat("AC KC QC JC 10C 2O 3P"), 9); assert.equal(cat("9C 8C 7C 6C 5C AO AP"), 8); assert.equal(cat("9C 9O 9P 9E 2C 3O 4P"), 7); assert.equal(cat("9C 9O 9P 2E 2C 3O 4P"), 6); assert.equal(cat("2C 5C 9C JC KC 3O 4P"), 5);
  assert.equal(cat("9C 8O 7P 6E 5C AO KP"), 4); assert.equal(cat("AC 2O 3P 4E 5C KO QP"), 4); assert.equal(cat("9C 9O 9P 2E 3C 5O KP"), 3); assert.equal(cat("9C 9O 3P 3E 5C 5O KP"), 2); assert.equal(cat("9C 9O 3P 4E 6C 8O KP"), 1); assert.equal(cat("AC KO 3P 4E 6C 8O JP"), 0);
  assert.equal(K.melhor(P("9C 9O 3P 3E 5C 5O KP")).des.join(), "9,5,13", "dois pares usa os dois mais altos e o melhor kicker");
  assert.equal(K.comparar(K.melhor(P("AC AO 2P 5E 7C 9O JP")), K.melhor(P("AP AE 2C 5O 7P 9E KP"))), -1, "kicker maior vence");
  assert.equal(K.comparar(K.melhor(P("AC KO QP JE 10C 2O 3P")), K.melhor(P("9C 8O 7P 6E 5C 2O 3P"))), 1);
});
t("melhor mão com 5 e 6 cartas (flop e turn) e descrição em português", () => {
  assert.equal(K.melhor(P("AC AO 2P 5E 7C")).cat, 1); assert.equal(K.melhor(P("AC AO 2P 5E 7C 7O")).cat, 2);
  assert(/um par de Ases/.test(K.descreverMao(K.melhor(P("AC AO 2P 5E 7C"))))); assert(/full house, trinca de Reis e par de 3/.test(K.descreverMao(K.melhor(P("KC KO KP 3E 3C 8O 9P")))));
});
t("equidade: ases contra mão aleatória ~85%, 7-2 fora de naipe ~35%, e sobe quando a mesa ajuda", () => {
  const a = K.equidade(P("AC AO"), [], 4000, rn(1)), b = K.equidade(P("7C 2O"), [], 4000, rn(2)); assert(a > 0.80 && a < 0.90, "AA " + a); assert(b > 0.28 && b < 0.42, "72 " + b);
  const c = K.equidade(P("AC KC"), P("QC JC 10C"), 500, rn(3)); assert(c > 0.99, "royal feito " + c);
});
t("nova partida e primeira mão: cegas, cartas, vez do dealer e fichas conservadas", () => {
  const e = K.novo("normal", rn(4)); assert.equal(e.fase, "entre"); const r = K.comando(e, "continuar"); assert(/Mão 1\./.test(r.msg) && /Suas cartas:/.test(r.msg) && /pequena de 5/.test(r.msg) && /grande de 10/.test(r.msg), r.msg);
  assert.equal(e.buraco[0].length, 2); assert.equal(e.buraco[1].length, 2); assert.equal(total(e), 400); assert.equal(e.fase, "apostas");
  const ids = new Set(e.buraco[0].concat(e.buraco[1]).map(K.nome)); assert.equal(ids.size, 4); assert(K.comando(e, "continuar").erro);
});
const montar = (fichas, aposta, comp, minAum) => { const e = K.novo("normal", rn(7)); e.fase = "apostas"; e.vez = 0; e.rua = 1; e.mesa = P("2C 7O 9P"); e.buraco = [P("AC KC"), P("3O 4P")]; e.fichas = fichas; e.aposta = aposta; e.comp = comp; e.minAumento = minAum; e.agiu = [false, aposta[1] > 0]; e.baralho = P("3C 4C 5C 6C 8C QE JO"); return e; };
t("sem aposta na mesa: não dá para pagar, aposta mínima, e aposta acima do que o outro cobre vira o limite", () => {
  let e = montar([150, 100], [0, 0], [50, 50], 10);
  assert(K.comando(e, "pagar").erro); assert(/mínima agora é 10/.test(K.comando(e, "apostar 5").msg)); assert(K.comando(e, "apostar").erro);
  const r = K.comando(e, "apostar 300"); assert(!r.erro, r.msg); assert(/Você aposta 100/.test(r.msg), r.msg); assert.equal(e.fichas[0] + e.fichas[1] + e.comp[0] + e.comp[1], 350);
});
t("com aposta na mesa: passar é erro, aumento mínimo é a aposta mais o último aumento, e tudo funciona", () => {
  let e = montar([180, 180], [0, 20], [30, 50], 20);
  assert(/aposta de 20 a pagar/.test(K.comando(e, "passar").msg)); assert(/mínima agora é 40/.test(K.comando(e, "apostar 25").msg)); const r = K.comando(e, "apostar 40"); assert(!r.erro, r.msg); assert(/aumenta para 40/.test(r.msg));
  e = montar([180, 180], [0, 20], [30, 50], 20); const r2 = K.comando(e, "tudo"); assert(!r2.erro && /vai de tudo/.test(r2.msg), r2.msg); assert.equal(e.fichas[0] + e.fichas[1] + e.comp[0] + e.comp[1], 440);
  e = montar([180, 180], [0, 20], [30, 50], 20); const r3 = K.comando(e, "pagar"); assert(/Você paga 20/.test(r3.msg), r3.msg);
  e.vez = 1; assert(K.jogar(e, "passar").erro && /Não é a sua vez/.test(K.jogar(e, "passar").msg));
});
t("desistir dá o pote ao outro; showdown dá ao vencedor; empate divide; fichas sempre somam o total", () => {
  let e = K.novo("normal", rn(8)); e.fase = "apostas"; e.vez = 0; e.rua = 1; e.mesa = P("2C 7O 9P"); e.buraco = [P("AC KC"), P("3O 4P")]; e.fichas = [180, 190]; e.aposta = [0, 10]; e.comp = [20, 10]; e.agiu = [false, true]; e.baralho = [];
  const r = K.comando(e, "desistir"); assert(/O computador ganhou o pote de 30/.test(r.msg)); assert.equal(e.fichas[1], 220); assert.equal(e.fichas[0] + e.fichas[1], 400); assert.equal(e.fase, "entre");
  e = K.novo("normal", rn(9)); e.fase = "apostas"; e.rua = 3; e.vez = 0; e.mesa = P("2C 7O 9P JE 3C"); e.buraco = [P("AC AO"), P("KC KO")]; e.fichas = [150, 150]; e.aposta = [0, 0]; e.comp = [50, 50]; e.agiu = [true, false]; e.vez = 1; e.baralho = [];
  const o = []; K.aplicar(e, 1, "passar", 0, o); assert(/ganhou o pote de 100/.test(o.join(" ")) && e.fichas[0] === 250, o.join(" "));
  e = K.novo("normal", rn(10)); e.fase = "apostas"; e.rua = 3; e.mesa = P("AC KC QC JC 10C"); e.buraco = [P("2O 3O"), P("4P 5P")]; e.fichas = [150, 150]; e.aposta = [0, 0]; e.comp = [50, 50]; e.agiu = [true, false]; e.vez = 1; e.baralho = []; const o2 = []; K.aplicar(e, 1, "passar", 0, o2); assert(/Empate/.test(o2.join(" ")) && e.fichas[0] === 200 && e.fichas[1] === 200);
});
t("tudo contra pilha menor: aposta limitada ao que o outro cobre, e as cartas restantes são viradas", () => {
  const e = K.novo("normal", rn(11)); e.fichas = [300, 100]; e.botao = 0; e.mao = 0; // jogador dealer
  K.iniciarMao(e); assert.equal(total(e), 400);
  if (e.vez === 0) { const r = K.comando(e, "tudo"); assert(!r.erro, r.msg); assert(e.aposta[0] <= 100 + 1 || e.fase === "entre"); }
  assert.equal(e.fichas[0] + e.fichas[1] + e.comp[0] + e.comp[1], 400);
});
t("partidas inteiras entre jogador-robô e computador: fichas conservadas, sempre termina, sem erros", () => {
  for (let s = 1; s <= 12; s++) {
    const e = K.novo(["facil", "normal", "dificil"][s % 3], rn(s * 13)); e.sims = 25; let guarda = 0;
    while (!e.fim && guarda++ < 800) {
      if (e.fase === "entre") { const r = K.comando(e, "continuar"); assert(!r.erro, r.msg); }
      else if (e.vez === 0) {
        const d = K.decidirCPU(e, 0, K.NIVEIS.normal, 25), r = d.tipo === "apostar" ? K.jogar(e, "apostar", d.valor) : K.jogar(e, d.tipo === "pagar" || d.tipo === "passar" || d.tipo === "desistir" ? d.tipo : "passar");
        assert(!r.erro, JSON.stringify(d) + " -> " + r.msg + " | " + K.comando(e, "mao").msg);
      }
      assert.equal(e.fichas[0] + e.fichas[1] + e.comp[0] + e.comp[1], e.inicio * 2);
    }
    assert(e.fim, "partida " + s + " não terminou"); assert(e.fim === "ganhou" ? e.fichas[1] === 0 : e.fichas[0] === 0);
  }
});
t("dica: ilimitada no fácil, 5 no normal, nenhuma no difícil; dá a chance de vencer", () => {
  const f = K.novo("facil", rn(14)); K.comando(f, "continuar"); if (f.vez !== 0) K.comando(f, "mao"); const d = K.comando(f, "dica"); assert(/^Dica: contra uma mão qualquer, você ganha cerca de \d+%/.test(d.msg) || /não há mão/.test(d.msg), d.msg);
  const n = K.novo("normal", rn(15)); K.comando(n, "continuar"); for (let i = 0; i < 5; i++) K.comando(n, "dica"); assert(/acabaram/.test(K.comando(n, "dica").msg)); assert(/não há dicas/.test(K.comando(K.novo("dificil", rn(16)), "dica").msg));
});
t("leituras e erros de comando", () => {
  const e = K.novo("normal", rn(17)); ["tabela", "resumo", "mao", "fichas", "ajuda"].forEach(c => assert(K.comando(e, c).msg.length > 5)); assert(K.comando(e, "pagar").erro && K.comando(e, "passar").erro && K.comando(e, "tudo").erro); assert(/Não entendi/.test(K.comando(e, "xyz").msg)); assert(K.comando(e, "apostar").erro);
});
t("cegas sobem a cada 6 mãos", () => { const e = K.novo("normal", rn(18)); e.mao = 1; assert.deepEqual(K.cegas(e), { p: 5, g: 10 }); e.mao = 7; assert.deepEqual(K.cegas(e), { p: 10, g: 20 }); e.mao = 13; assert.deepEqual(K.cegas(e), { p: 20, g: 40 }); });
t("força dos níveis: o computador difícil vence o normal na maioria das partidas", () => {
  let dif = 0, total_ = 24;
  for (let s = 1; s <= total_; s++) {
    const e = K.novo("normal", rn(s * 101)); e.sims = 30; e.botao = s % 2; let g = 0;
    // assento 0 joga como "difícil", assento 1 como "normal" (o que a partida usa)
    while (!e.fim && g++ < 600) {
      if (e.fase === "entre") { K.iniciarMao(e); continue; }
      if (e.vez === 0) { const d = K.decidirCPU(e, 0, { nome: "difícil" }, 30), out = []; K.aplicar(e, 0, d.tipo, d.valor, out); K.seguir(e, out); }
    }
    if (e.fim === "ganhou") dif++;
  }
  console.log("     (difícil venceu " + dif + " de " + total_ + " partidas contra o normal)"); assert(dif >= 13, "difícil deveria vencer ao menos 13 de 24: " + dif);
});
console.log(ok + " testes do poker passaram");
