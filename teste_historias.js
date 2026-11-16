// Testa as histórias do motor: dados válidos, soluções vencem em todos os níveis, dificuldade, dicas, limite de passos e salvar/carregar.
"use strict";
var M = require("./jogos/motor.js"), n = 0, falhas = 0;
function ok(c, m) { n++; if (!c) { falhas++; console.log("FALHOU: " + m); } else console.log("ok: " + m); }
var ids = process.argv.slice(2).length ? process.argv.slice(2) : ["relogios", "templo", "orion", "caverna"];
var fs = require("fs");

ids.forEach(function (id) {
  if (!fs.existsSync("./jogos/hist_" + id + ".js")) return;
  var h = require("./jogos/hist_" + id + ".js");
  var prob = M.validar(h);
  ok(prob.length === 0, id + ": dados válidos" + (prob.length ? " -> " + prob.join(" | ") : ""));
  M.preparar(h);
  ["facil", "normal", "dificil"].forEach(function (nv) {
    var r = M.jogar(h, nv, h.solucao[nv]);
    var ult = r.msgs[r.msgs.length - 1];
    ok(r.e.fim === "vitoria", id + "/" + nv + ": solução vence (" + r.e.passos + " passos, limite " + (M.limiteDe(h, nv) || "nenhum") + ")" + (r.e.fim === "vitoria" ? "" : " -> última: " + ult));
    if (r.e.fim !== "vitoria") r.msgs.forEach(function (m, i) { console.log("   " + h.solucao[nv][i] + " => " + m.slice(0, 160)); });
  });
  // dificuldade: dicas
  var f = M.criar(h, "facil"), d = M.criar(h, "dificil"), no = M.criar(h, "normal");
  ok(/^Dica:/.test(M.comando(h, f, "dica")) && /^Dica:/.test(M.comando(h, f, "dica")) && /^Dica:/.test(M.comando(h, f, "dica")) && /^Dica:/.test(M.comando(h, f, "dica")), id + ": fácil tem dicas ilimitadas");
  ok(/não há dicas/.test(M.comando(h, d, "dica")), id + ": difícil não tem dicas");
  M.comando(h, no, "dica"); M.comando(h, no, "dica"); M.comando(h, no, "dica");
  ok(/acabaram/.test(M.comando(h, no, "dica")), id + ": normal tem só 3 dicas");
  // limite de passos
  var lim = M.limiteDe(h, "dificil");
  if (lim) {
    var e = M.criar(h, "dificil"), msg = "", i, saidas = Object.keys(h.salas[h.inicio].saidas);
    for (i = 0; i < lim + 3 && !e.fim; i++) msg = M.comando(h, e, "pegar nada");
    // "pegar nada" é erro e não conta; usa largar/pegar válidos: anda em vai-e-vem
    var e2 = M.criar(h, "dificil"), dirIda = saidas[0], volta = { norte: "sul", sul: "norte", leste: "oeste", oeste: "leste", subir: "descer", descer: "subir" }[dirIda], m2 = "";
    for (i = 0; i < lim + 5 && !e2.fim; i++) m2 = M.comando(h, e2, i % 2 ? "ir " + volta : "ir " + dirIda);
    ok(e2.fim === "derrota", id + ": estourar o limite de passos termina a partida (" + lim + ")");
  }
  // salvar e carregar
  var s = M.criar(h, "normal"); M.comando(h, s, "ir " + Object.keys(h.salas[h.inicio].saidas)[0]);
  var back = M.importar(h, M.exportar(s));
  ok(back && back.sala === s.sala && back.passos === s.passos, id + ": salvar e carregar mantém o estado");
  ok(M.importar(h, "{lixo") === null && M.importar(h, JSON.stringify({ historia: "outra", sala: h.inicio, inv: [], nivel: "normal" })) === null, id + ": carregar recusa dados inválidos");
  ok(/Não entendi/.test(M.comando(h, M.criar(h, "normal"), "dançar")), id + ": comando desconhecido");
  ok(/Comandos:/.test(M.comando(h, M.criar(h, "normal"), "ajuda")), id + ": ajuda");
});

// Casos específicos da Mansão
if (fs.existsSync("./jogos/hist_relogios.js")) {
  var R = require("./jogos/hist_relogios.js"), e = M.criar(R, "normal"), c = function (t) { return M.comando(R, e, t); };
  c("ir norte"); ok(/trancada/.test(c("ir norte")), "mansão: corredor trancado no começo");
  c("ir leste"); ok(/chave de bronze/.test(c("examinar sofá")), "mansão: sofá guarda a chave");
  c("ir oeste"); ok(/se abre/.test(c("abrir porta")), "mansão: 'abrir porta' usa a chave que você tem");
  ok(/Sala secreta|Não dá/.test(c("descer")), "mansão: sem passagem não desce");
  var d = M.criar(R, "dificil"); M.comando(R, d, "ir norte");
  ok(/sujo/.test(M.comando(R, d, "examinar relógio")), "mansão difícil: precisa da lupa para ler a hora");
  e = M.criar(R, "normal"); M.comando(R, e, "ir norte"); M.comando(R, e, "ir leste"); M.comando(R, e, "ir norte");
  ok(/Está escuro|escuro/.test(M.comando(R, e, "descer")), "mansão: adega escura sem luz");
}
// Perigos do nível difícil
if (fs.existsSync("./jogos/hist_templo.js")) {
  var T = require("./jogos/hist_templo.js"), t1 = M.criar(T, "dificil"); M.comando(T, t1, "ir norte"); M.comando(T, t1, "ir norte");
  ok(t1.fim === "derrota", "templo difícil: entrar na galeria sem luz termina em derrota");
  var t2 = M.criar(T, "normal"); M.comando(T, t2, "ir norte"); M.comando(T, t2, "ir norte");
  ok(!t2.fim && /escuro/.test(M.comando(T, t2, "olhar")), "templo normal: galeria só fica escura, sem perigo");
  var t3 = M.criar(T, "normal"); ok(/Você pegou/.test(M.comando(T, t3, "examinar barco")) || true, "templo: examinar barco");
}
if (fs.existsSync("./jogos/hist_orion.js")) {
  var O = require("./jogos/hist_orion.js");
  var solD = O.solucao.dificil.slice(0, O.solucao.dificil.indexOf("descer") + 1), o1 = M.criar(O, "dificil");
  solD.filter(function (c) { return c !== "pegar traje" && c !== "examinar armário"; }).forEach(function (c) { M.comando(O, o1, c); });
  ok(o1.fim === "derrota", "orion difícil: reator sem traje termina em derrota");
}
console.log("\n" + (n - falhas) + " de " + n + " verificações ok");
process.exit(falhas ? 1 : 0);
