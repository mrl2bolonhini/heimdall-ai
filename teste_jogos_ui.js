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
function carregar(nome) {
  reg = {}; doc.listeners = {};
  const jogo = new El("div"); jogo.setAttribute("id", "jogo"); const an = new El("div"); an.setAttribute("id", "anuncio");
  ["base.js", nome + ".js"].forEach(f => { const p = path.join(__dirname, "jogos", f); delete require.cache[require.resolve(p)]; require(p); });
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
console.log(`${ok} testes de interface passaram`); process.exit(falhas ? 1 : 0);
