// Teste de fumaça da interface dos jogos com um DOM de mentira: carrega cada jogo, aciona campos e botões e confere o que é anunciado.
const assert = require("assert"), path = require("path");
let falhas = 0, ok = 0;
const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { falhas++; console.log("FALHOU " + n + "\n     " + String(e.stack || e).split("\n").slice(0, 3).join(" | ")); } };

class El {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.style = {}; this._t = ""; this.value = ""; this.disabled = false; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "id") reg[v] = this; }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(c) { this.children.push(c); return c; }
  insertBefore(n) { this.children.unshift(n); return n; }
  get firstChild() { return this.children[0] || null; }
  set textContent(v) { this._t = String(v); this.children = []; }
  get textContent() { return this._t + this.children.map(c => c.textContent).join(" "); }
  addEventListener(tp, f) { (this.listeners[tp] = this.listeners[tp] || []).push(f); }
  fire(tp, ev) { (this.listeners[tp] || []).forEach(f => f(Object.assign({ preventDefault() {}, target: this }, ev || {}))); }
  focus() { document.activeElement = this; }
  all(tag) { return this.children.reduce((a, c) => a.concat(c.tag === tag ? [c] : [], c.all(tag)), []); }
}
let reg = {};
const doc = { activeElement: { tagName: "BODY" }, body: {}, createElement: (t) => new El(t), getElementById: (i) => reg[i] || null, listeners: {}, addEventListener(tp, f) { (this.listeners[tp] = this.listeners[tp] || []).push(f); } };
global.document = doc; global.window = global; global.setTimeout = (f) => f();
function carregar(nome, historia) {
  reg = {}; doc.listeners = {};
  const jogo = new El("div"); jogo.setAttribute("id", "jogo"); const an = new El("div"); an.setAttribute("id", "anuncio");
  if (historia) jogo.setAttribute("data-historia", historia);
  (historia ? ["base.js", nome + ".js", "motor.js"] : ["base.js", nome + ".js"]).forEach(f => { const p = path.join(__dirname, "jogos", f); delete require.cache[require.resolve(p)]; require(p); });
  return { jogo, an, id: (i) => reg[i] };
}
const botaoPorTexto = (jogo, txt) => jogo.all("button").filter(b => b.textContent === txt)[0];

t("forca: sorteia, aceita letra e ganha/perde pela interface", () => {
  const j = carregar("forca"); assert(/Categoria/.test(j.an.textContent));
  const campo = j.id("tentativa"), form = j.jogo.all("form")[0];
  campo.value = "z"; form.fire("submit"); assert(/Palavra:/.test(j.id("palavra").textContent));
  assert(/Erros: \d de 7/.test(j.id("info").textContent));
  for (const c of "bcdfghjklmnpqrstvwxyz") { if (!campo.disabled) { campo.value = c; form.fire("submit"); } }
  botaoPorTexto(j.jogo, "Nova rodada").fire("click"); assert(!campo.disabled && /Nova rodada/.test(j.an.textContent));
});
t("senha: palpite inválido, válido e nova senha", () => {
  const j = carregar("senha"), campo = j.id("palpite"), form = j.jogo.all("form")[0];
  campo.value = "12"; form.fire("submit"); assert(/exatamente 4/.test(j.an.textContent));
  campo.value = "1234"; form.fire("submit"); assert(/dígito/.test(j.an.textContent) || /Acertou/.test(j.an.textContent)); assert.equal(j.id("historico").children.length, 1);
  for (let i = 0; i < 12 && !campo.disabled; i++) { campo.value = "1111"; form.fire("submit"); }
  assert(campo.disabled); botaoPorTexto(j.jogo, "Nova senha").fire("click"); assert(!campo.disabled && j.id("historico").children.length === 0);
});
t("numero: dicas e acerto", () => {
  const j = carregar("numero"), campo = j.id("palpite"), form = j.jogo.all("form")[0];
  campo.value = "abc"; form.fire("submit"); assert(/inteiro de 1 a 100/.test(j.an.textContent));
  let achou = false; for (let n = 1; n <= 100 && !achou; n++) { campo.value = String(n); form.fire("submit"); achou = /Acertou/.test(j.an.textContent); }
  assert(achou && campo.disabled);
});
t("velha: joga, computador responde e o nível troca", () => {
  const j = carregar("velha"), casas = j.jogo.all("button").filter(b => /linha/.test(b.getAttribute("aria-label") || ""));
  assert.equal(casas.length, 9); casas[0].fire("click");
  assert(/Você jogou em linha 1, coluna 1/.test(j.an.textContent) && /O computador jogou/.test(j.an.textContent));
  assert.equal(casas.filter(b => b.disabled).length, 2);
  j.id("nivel").fire("click"); assert(/fácil/.test(j.id("nivel").textContent) && casas.every(b => !b.disabled));
  for (let i = 0; i < 9; i++) casas.filter(b => !b.disabled).slice(0, 1).forEach(b => b.fire("click"));
  assert(/ganhou|velha|empate/i.test(j.an.textContent) || /Sua vez/.test(j.an.textContent));
});
t("2048: botões, setas, ler tabuleiro e nova partida", () => {
  const j = carregar("g2048"); assert(/Nova partida\. Linha 1/.test(j.an.textContent));
  let moveu = false; ["Esquerda", "Direita", "Cima", "Baixo"].forEach(n => { botaoPorTexto(j.jogo, n).fire("click"); moveu = moveu || /Moveu/.test(j.an.textContent); }); assert(moveu);
  botaoPorTexto(j.jogo, "Ler o tabuleiro").fire("click"); assert(/Linha 4:/.test(j.an.textContent));
  const antes = j.id("info") ? 0 : 0; doc.listeners.keydown.forEach(f => f({ key: "ArrowLeft", target: { tagName: "BODY" }, preventDefault() {} }));
  doc.listeners.keydown.forEach(f => f({ key: "ArrowLeft", target: { tagName: "INPUT" }, preventDefault() { throw new Error("não deveria agir em campo de texto"); } }));
  botaoPorTexto(j.jogo, "Nova partida").fire("click"); assert(/Nova partida/.test(j.an.textContent));
});
t("aventura: história, comando e recomeço", () => {
  const j = carregar("aventura"), campo = j.id("comando"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/O Farol Apagado/.test(hist.textContent));
  campo.value = "pegar fósforos"; form.fire("submit"); assert(/Você pegou: fósforos/.test(j.an.textContent) && hist.children.length === 2);
  assert(/^> pegar fósforos/.test(hist.children[0].textContent));
  botaoPorTexto(j.jogo, "Recomeçar").fire("click"); assert.equal(hist.children.length, 1);
});
t("caça-níqueis: gira, lê saldo, prêmios e nova partida", () => {
  const j = carregar("cacaniqueis"); assert(/Caça-níqueis/.test(j.an.textContent) && /30 créditos/.test(j.an.textContent));
  j.id("aposta").value = "1"; botaoPorTexto(j.jogo, "Girar").fire("click"); assert(/Saiu:/.test(j.an.textContent) && /Saldo:/.test(j.an.textContent));
  assert(/^\[ \d \| \d \| \d \]$/.test(j.id("painel").textContent) && j.id("painel").attrs["aria-hidden"] === "true");
  botaoPorTexto(j.jogo, "Ver os prêmios").fire("click"); assert(/trinca|iguais/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Ler o saldo").fire("click"); assert(/Rodadas: 1/.test(j.an.textContent));
  for (let i = 0; i < 200 && !j.id("girar").disabled; i++) botaoPorTexto(j.jogo, "Girar").fire("click");
  botaoPorTexto(j.jogo, "Nova partida").fire("click"); assert(/Nova partida com 30/.test(j.an.textContent) && !j.id("girar").disabled);
});
t("campo minado: grade de botões com rótulo, comando e novo jogo", () => {
  const j = carregar("minas"), grade = j.id("grade"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  const bs = grade.all("button"); assert(bs.length > 20 && /linha 1, coluna 1, fechada/.test(bs[0].getAttribute("aria-label")));
  bs[0].fire("click"); assert(/aberta|vazia|Você|casas/i.test(j.an.textContent));
  campo.value = "resumo"; form.fire("submit"); assert(/mina/i.test(j.an.textContent));
  campo.value = "marcar 5 5"; form.fire("submit"); assert(/marc/i.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Modo da grade: abrir").fire("click"); assert(/marcar/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("xadrez: lance, resposta do computador, consulta, erro e nova partida", () => {
  const j = carregar("xadrez"), campo = j.id("lance"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/Nova partida, nível médio/.test(j.an.textContent));
  campo.value = "e4"; form.fire("submit"); assert(/Você jogou/.test(j.an.textContent) && /O computador jogou/.test(j.an.textContent));
  campo.value = "linha 1"; form.fire("submit"); assert(/Linha 1:/.test(j.an.textContent));
  campo.value = "e9"; form.fire("submit"); assert(/Não entendi|não é permitido/.test(j.an.textContent));
  campo.value = "desfazer"; form.fire("submit"); assert(/Desfeito/.test(j.an.textContent));
  assert(/pre/.test(j.id("visual").tag) && j.id("visual").attrs["aria-hidden"] === "true" && /a b c d e f g h/.test(j.id("visual").textContent));
  campo.value = "desistir"; form.fire("submit"); assert(campo.disabled);
  botaoPorTexto(j.jogo, "Nova partida").fire("click"); assert(!campo.disabled && hist.children.length === 1);
});
const store = {}; global.localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
["relogios", "templo", "orion"].forEach(id => t(`aventura ${id}: níveis, comando, dica, salvar e carregar`, () => {
  const j = carregar("hist_" + id, id), campo = j.id("comando"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/Objetivo:/.test(hist.textContent) && /Nível normal/.test(hist.textContent));
  j.id("nivel").value = "dificil"; botaoPorTexto(j.jogo, "Recomeçar").fire("click"); assert(/Nível difícil: sem dicas/.test(hist.children[0].textContent));
  campo.value = "dica"; form.fire("submit"); assert(/não há dicas/.test(j.an.textContent));
  j.id("nivel").value = "facil"; botaoPorTexto(j.jogo, "Recomeçar").fire("click"); assert(/dicas à vontade/.test(hist.children[0].textContent));
  campo.value = "dica"; form.fire("submit"); assert(/Dica:/.test(j.an.textContent));
  campo.value = "ir norte"; form.fire("submit"); campo.value = "salvar"; form.fire("submit"); assert(/salva/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Recomeçar").fire("click"); botaoPorTexto(j.jogo, "Carregar").fire("click"); assert(/Partida carregada/.test(j.an.textContent));
  campo.value = "dançar"; form.fire("submit"); assert(/Não entendi/.test(j.an.textContent));
}));
console.log(`${ok} testes de interface passaram`); process.exit(falhas ? 1 : 0);
