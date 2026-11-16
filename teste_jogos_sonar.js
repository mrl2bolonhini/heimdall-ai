// Lógica do Sonar (sem navegador).
const assert = require("assert"), path = require("path");
global.Heimdall = {};
const S = require(path.join(__dirname, "jogos", "sonar.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const com = (subs, nivel) => { const e = S.novo(nivel || "facil"); e.subs = subs.map(([l, c]) => ({ l, c })); e.total = subs.length; return e; };

t("sonar: direções em oito sentidos (linha cresce para o sul, coluna para o leste)", () => {
  assert.equal(S.direcao(-3, 0), "norte"); assert.equal(S.direcao(3, 0), "sul"); assert.equal(S.direcao(0, 4), "leste"); assert.equal(S.direcao(0, -4), "oeste");
  assert.equal(S.direcao(-2, 2), "nordeste"); assert.equal(S.direcao(-2, -2), "noroeste"); assert.equal(S.direcao(2, 2), "sudeste"); assert.equal(S.direcao(2, -2), "sudoeste");
});
t("sonar: o navio começa no centro e os submarinos nunca começam sobre ele nem empilhados", () => {
  for (const n of ["facil", "normal", "dificil"]) for (let i = 0; i < 50; i++) {
    const e = S.novo(n), c = new Set(e.subs.map(s => s.l + "," + s.c));
    assert.equal(e.subs.length, S.NIVEIS[n].subs); assert.equal(c.size, e.subs.length); assert(!c.has(e.lin + "," + e.col));
    e.subs.forEach(s => { assert(s.l >= 1 && s.l <= e.l && s.c >= 1 && s.c <= e.c); });
  }
});
t("sonar: o ping diz a distância e a direção do submarino mais próximo e gasta um ping", () => {
  const e = com([[1, 5], [8, 8]]); // navio em 5,5: o primeiro está 4 casas ao norte
  const r = S.ping(e); assert(/cerca de 4 casas, ao norte/.test(r.msg), r.msg); assert.equal(e.pings, S.NIVEIS.facil.pings - 1);
  assert.equal(r.dist, 4); assert.equal(r.dl, -4); assert.equal(r.dc, 0);
  const o = com([[5, 5]]); assert(/bem embaixo de você/.test(S.ping(o).msg));
});
t("sonar: mover respeita a borda e anda várias casas", () => {
  const e = com([[1, 1]]); assert.equal(S.mover(e, "leste", 2).passos, 2); assert.equal(e.col, 7);
  const r = S.mover(e, "leste", 10); assert.equal(e.col, 8); assert(/até a borda/.test(r.msg));
  const b = S.mover(e, "leste", 1); assert(b.erro && /Fim do mapa/.test(b.msg));
});
t("sonar: a carga só acerta na casa exata; acertar tudo vence", () => {
  const e = com([[5, 6], [5, 5]]);
  let r = S.lancar(e); assert(r.acerto === true && /Restam 1 submarino/.test(r.msg), r.msg); assert.equal(e.subs.length, 1);
  S.mover(e, "leste"); r = S.lancar(e); assert.equal(r.fim, "ganhou"); assert(/Vitória/.test(r.msg)); assert.equal(e.fim, "ganhou");
  assert(/terminou/.test(S.lancar(e).msg));
});
t("sonar: errar a carga gasta uma, e a última carga errada perde o jogo", () => {
  const e = com([[1, 1]]); for (let i = 0; i < S.NIVEIS.facil.cargas - 1; i++) assert.equal(S.lancar(e).acerto, false);
  const r = S.lancar(e); assert.equal(r.fim, "perdeu"); assert(/Fim de jogo/.test(r.msg)); assert.equal(e.cargas, 0);
});
t("sonar: sem pings o sonar cala, mas dá para lançar", () => {
  const e = com([[1, 1]]); e.pings = 0; const r = S.ping(e); assert(r.erro && /sem energia/.test(r.msg));
});
t("sonar: no difícil os submarinos se movem depois do ping, sem sair do mar", () => {
  const e = S.novo("dificil"); const antes = JSON.stringify(e.subs); let mudou = false;
  for (let i = 0; i < 20; i++) { S.ping(e); e.subs.forEach(s => { assert(s.l >= 1 && s.l <= e.l && s.c >= 1 && s.c <= e.c); }); if (JSON.stringify(e.subs) !== antes) mudou = true; }
  assert(mudou, "algum submarino deve ter se mexido");
  const f = S.novo("facil"), a = JSON.stringify(f.subs); S.ping(f); S.ping(f); assert.equal(JSON.stringify(f.subs), a, "no fácil ficam parados");
});
t("sonar: comandos em português, com atalhos, e recusas", () => {
  const e = com([[1, 1]]);
  assert(/Você foi 1 casa ao norte/.test(S.comando(e, "n").msg)); assert(/Você foi 3 casas ao leste/.test(S.comando(e, "ir leste 3").msg));
  assert(/Eco/.test(S.comando(e, "sonar").msg)); assert(/Você está na linha/.test(S.comando(e, "onde").msg)); assert(/Submarinos afundados: 0 de 1/.test(S.comando(e, "resumo").msg));
  assert(/Comandos:/.test(S.comando(e, "ajuda").msg)); assert(/Não entendi/.test(S.comando(e, "xyz").msg)); assert(/Digite um comando/.test(S.comando(e, "").msg));
});
console.log(ok + " testes do sonar passaram");
