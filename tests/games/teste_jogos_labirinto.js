// Lógica do Labirinto (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const L = require(path.join(__dirname, "..", "..", "games", "labirinto.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const todas = (e) => { const v = new Set([0]), f = [0]; while (f.length) { const a = f.shift(); L.passagens(e, a).forEach(d => { const [l, c] = [Math.floor(a / e.c) + 1, (a % e.c) + 1]; const dl = { norte: -1, sul: 1, leste: 0, oeste: 0 }[d], dc = { norte: 0, sul: 0, leste: 1, oeste: -1 }[d]; const j = (l + dl - 1) * e.c + (c + dc - 1); if (!v.has(j)) { v.add(j); f.push(j); } }); } return v.size; };

t("labirinto: todo labirinto é conexo, perfeito (n-1 passagens) e simétrico", () => {
  for (const n of ["facil", "normal", "dificil"]) for (let i = 0; i < 20; i++) {
    const e = L.novo(n), total = e.l * e.c; assert.equal(todas(e), total, "todas as casas alcançáveis");
    let arestas = 0; e.aberto.forEach(a => ["norte", "sul", "leste", "oeste"].forEach(d => { if (a[d]) arestas++; })); assert.equal(arestas / 2, total - 1, "perfeito: sem ciclos");
    for (let k = 0; k < total; k++) { const [l, c] = [Math.floor(k / e.c) + 1, (k % e.c) + 1]; if (e.aberto[k].leste) assert(e.aberto[k + 1].oeste); if (e.aberto[k].sul) assert(e.aberto[k + e.c].norte); if (l === 1) assert(!e.aberto[k].norte); if (c === 1) assert(!e.aberto[k].oeste); }
  }
});
t("labirinto: o caminho mais curto leva à saída e a dica aponta o primeiro passo certo", () => {
  const e = L.novo("facil"), c = L.caminho(e, 0); assert(c.passos >= e.l + e.c - 2);
  let n = 0; while (e.pos !== e.saida && n < 500) { const d = L.caminho(e, e.pos).dir; const r = L.andar(e, d, 1); assert(!r.erro, r.msg); n++; }
  assert.equal(e.pos, e.saida); assert.equal(e.passos, c.passos); assert.equal(e.fim, "ganhou");
});
t("labirinto: parede não move nem conta passo, e a descrição diz as passagens", () => {
  const e = L.novo("facil"), ps = L.passagens(e, 0), bloqueada = ["norte", "oeste"][0]; // no canto de cima não há mar ao norte nem ao oeste
  const r = L.andar(e, bloqueada, 1); assert(r.erro && r.batida && /^Parede ao norte/.test(r.msg)); assert.equal(e.pos, 0); assert.equal(e.passos, 0);
  assert(/Passagens: /.test(L.olhar(e)) || /Beco/.test(L.olhar(e))); assert(ps.length >= 1);
});
t("labirinto: andar vários passos para numa bifurcação e chegar à saída fecha o jogo", () => {
  const e = L.novo("facil"); e.aberto = e.aberto.map(() => ({ norte: false, sul: false, leste: false, oeste: false }));
  for (let c = 0; c < e.c - 1; c++) { e.aberto[c].leste = true; e.aberto[c + 1].oeste = true; } // corredor reto na linha 1
  e.saida = e.c - 1; const r = L.andar(e, "leste", 10); assert(/Você chegou à saída/.test(r.msg) && r.fim === "ganhou", r.msg); assert.equal(e.passos, e.c - 1);
  assert(/terminou/.test(L.andar(e, "oeste", 1).msg));
});
t("labirinto: níveis falam diferente (tudo, só cruzamentos, nada) a cada passo", () => {
  const monta = (nivel) => { const e = L.novo(nivel); e.aberto = e.aberto.map(() => ({ norte: false, sul: false, leste: false, oeste: false }));
    [[0, "leste", 1], [1, "leste", 2], [1, "sul", e.c + 1]].forEach(([a, d, b]) => { e.aberto[a][d] = true; e.aberto[b][{ leste: "oeste", sul: "norte" }[d]] = true; }); return e; };
  const f = monta("facil"); assert(/Passagens: /.test(L.andar(f, "leste", 1).msg), "fácil descreve sempre");
  const n = monta("normal"); assert(/Passagens: /.test(L.andar(n, "leste", 1).msg), "normal descreve a bifurcação"); // casa 1 tem leste, sul e oeste
  const d = monta("dificil"); assert(!/Passagens/.test(L.andar(d, "leste", 1).msg), "difícil não descreve");
});
t("labirinto: farol dá direção e distância em linha reta e é limitado nos níveis normal e difícil", () => {
  const e = L.novo("dificil"), r = L.farol(e); assert(/Farol: a saída está a cerca de/.test(r.msg) && /sudeste/.test(r.msg), r.msg); assert(r.dist > 0 && r.dl > 0 && r.dc > 0);
  L.farol(e); L.farol(e); const x = L.farol(e); assert(x.erro && /sem energia/.test(x.msg));
  const f = L.novo("facil"); for (let i = 0; i < 30; i++) assert(!L.farol(f).erro);
});
t("labirinto: dicas limitadas (difícil 1, normal 4) e ilimitadas no fácil", () => {
  const d = L.novo("dificil"); assert(/primeiro|começa indo ao/.test(L.dica(d).msg)); assert(L.dica(d).erro);
  const n = L.novo("normal"); for (let i = 0; i < 4; i++) assert(!L.dica(n).erro); assert(L.dica(n).erro);
  const f = L.novo("facil"); for (let i = 0; i < 20; i++) assert(!L.dica(f).erro);
});
t("labirinto: comandos em português, correr, atalhos e recusas", () => {
  const e = L.novo("facil");
  assert(/Parede ao norte/.test(L.comando(e, "n").msg)); assert(/Você está na linha 1, coluna 1/.test(L.comando(e, "onde").msg)); assert(/Passagens|Beco/.test(L.comando(e, "olhar").msg));
  assert(L.comando(e, "correr").erro); assert(/Comandos:/.test(L.comando(e, "ajuda").msg)); assert(/Não entendi/.test(L.comando(e, "xyz").msg)); assert(/Digite um comando/.test(L.comando(e, "").msg));
  const d = L.passagens(e, 0)[0]; assert(/Você foi/.test(L.comando(e, "correr " + d).msg));
  assert(/Passos: \d+/.test(L.comando(e, "resumo").msg));
});
console.log(ok + " testes do labirinto passaram");
