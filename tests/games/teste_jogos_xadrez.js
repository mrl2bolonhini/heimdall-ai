// Testes do xadrez: perft (contagem de lances), notação, fim de jogo e partidas contra a IA.
"use strict";
var X = require("../../games/xadrez.js"), n = 0, falhas = 0;
function ok(c, m) { n++; if (!c) { falhas++; console.log("FALHOU: " + m); } else console.log("ok: " + m); }
function perft(e, d) { if (d === 0) return 1; var t = 0; X.gerar(e).forEach(function (m) { t += perft(X.fazer(e, m), d - 1); }); return t; }

var ini = X.inicial();
ok(perft(ini, 1) === 20 && perft(ini, 2) === 400 && perft(ini, 3) === 8902, "perft posição inicial 20/400/8902");
var kiwi = X.desdeFEN("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1");
ok(perft(kiwi, 1) === 48 && perft(kiwi, 2) === 2039, "perft Kiwipete 48/2039 (roques, en passant, xeques)");
var p3 = X.desdeFEN("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1");
ok(perft(p3, 1) === 14 && perft(p3, 2) === 191 && perft(p3, 3) === 2812, "perft posição 3 14/191/2812");
var p4 = X.desdeFEN("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1");
ok(perft(p4, 1) === 6 && perft(p4, 2) === 264, "perft posição 4 6/264 (promoções)");

// notação
var g = X.novaPartida("facil", "w");
var r = X.lerLance(g.e, "e4"); ok(r.lance && X.nomeCasa(r.lance.para) === "e4", "lê e4");
r = X.lerLance(g.e, "Cf3"); ok(r.lance && X.san(g.e, r.lance) === "Cf3", "lê Cf3 (cavalo em português)");
r = X.lerLance(g.e, "e2 e4"); ok(r.lance && r.lance.duplo, "lê casa para casa");
r = X.lerLance(g.e, "e5"); ok(r.erro, "recusa lance ilegal");
// mate do pastor
var s = X.novaPartida("facil", "w");
["e4", "e5", "Bc4", "Cc6", "Dh5", "Cf6", "Dxf7"].forEach(function (t, i) { var l = X.lerLance(s.e, t); if (!l.lance) { ok(false, "lance " + t + ": " + l.erro); return; } X.aplicar(s, l.lance); });
ok(s.fim && s.fim.fim === "mate" && s.fim.vencedor === "w" && /#$/.test(s.lances[s.lances.length - 1]), "mate do pastor detectado, notação termina em #");
// afogamento e material
ok(X.situacao(X.desdeFEN("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")).fim === "afogamento", "afogamento");
ok(X.situacao(X.desdeFEN("8/8/4k3/8/8/3K4/8/8 w - - 0 1")).fim === "material", "rei contra rei: material insuficiente");
ok(X.situacao(X.desdeFEN("8/8/4k3/8/8/3K4/8/R7 w - - 100 80")).fim === "cinquenta", "regra dos cinquenta lances");
// roque e en passant e promoção
var rq = X.desdeFEN("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
ok(X.lerLance(rq, "O-O").lance.roque === "K" && X.lerLance(rq, "O-O-O").lance.roque === "Q", "roque pequeno e grande");
var ep = X.desdeFEN("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1");
ok(X.lerLance(ep, "exd6").lance.ep === true, "en passant");
var pr = X.desdeFEN("8/P6k/8/8/8/8/8/K7 w - - 0 1");
ok(X.lerLance(pr, "a8=D").lance.promo === "Q" && X.lerLance(pr, "a8=C").lance.promo === "N", "promoção a dama e a cavalo");
// ambiguidade
var am = X.desdeFEN("4k3/8/8/8/8/8/3N3N/4K3 w - - 0 1");
ok(X.lerLance(am, "Cf3").erro && /ambíguo/.test(X.lerLance(am, "Cf3").erro), "lance ambíguo pede desambiguação");
ok(X.lerLance(am, "Cdf3").lance, "desambiguação por coluna (Cdf3)");
// leitura
ok(/Linha 1/.test(X.lerLinha(ini, 1)) && /torre branca/.test(X.lerLinha(ini, 1)), "leitura de linha");
ok(/e1: rei branco/.test(X.lerCasa(ini, "e1")) && /vazia/.test(X.lerCasa(ini, "e4")), "leitura de casa");
ok(/Material igual/.test(X.material(ini)), "material");
// partida completa com IA dos dois lados (aleatória controlada), sem travar
function sorteio(seed) { var x = seed; return function (k) { x = (x * 1103515245 + 12345) & 0x7fffffff; return x % k; }; }
["facil", "medio"].forEach(function (nv) {
  var p = X.novaPartida(nv, "w"), rnd = sorteio(7), lances = 0;
  while (!p.fim && lances < 300) { var m = X.escolher(p.e, nv, rnd); if (!m) break; X.aplicar(p, m); lances++; }
  ok(lances > 0 && (p.fim || lances === 300), "IA " + nv + " joga contra si mesma sem erro (" + lances + " lances)");
});
// IA acha mate em 1 e não deixa a dama de graça
var m1 = X.desdeFEN("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1");
var mm = X.escolher(m1, "medio", function () { return 0; });
ok(X.san(m1, mm) === "Ta8#", "IA média acha mate em 1");
var cap = X.desdeFEN("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1");
ok(X.san(cap, X.escolher(cap, "dificil", function () { return 0; })).indexOf("x") > 0, "IA difícil captura a dama indefesa");
// jogar via texto e desfazer
var pj = X.novaPartida("facil", "w"), res = X.jogar(pj, "e4", sorteio(3));
ok(/Você jogou/.test(res.msg) && /O computador jogou/.test(res.msg) && pj.e.vez === "w", "jogar responde e devolve a vez");
ok(/Desfeito/.test(X.desfazer(pj)) && pj.lances.length === 0, "desfazer volta ao início");
ok(X.consulta(pj, "lances").indexOf("20 lances") === 0, "comando lances");
ok(X.consulta(pj, "e4") === null, "lance não é confundido com comando");

console.log("\n" + (n - falhas) + " de " + n + " verificações ok");
process.exit(falhas ? 1 : 0);
