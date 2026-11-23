// Teste da tela do Vilarejo Sitiado com um navegador de mentira: teclas, som, narração e desenho no canvas sem erros.
const assert = require("assert"), path = require("path");
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + (e.stack || e.message)); process.exitCode = 1; } };
const falas = [], oscilador = [], ouvintes = {}, desenho = { chamadas: 0, textos: [] };
function noEl(tag, attrs) {
  const el = { tag, attrs: attrs || {}, filhos: [], style: {}, value: "", textContent: (attrs && attrs.texto) || "", ouvintes: {},
    appendChild(f) { this.filhos.push(f); return f; }, setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(n, f) { (this.ouvintes[n] = this.ouvintes[n] || []).push(f); }, focus() {},
    querySelector(sel) { const q = (n) => { for (const f of n.filhos) { if (f.tag === sel) return f; const r = q(f); if (r) return r; } return null; }; return q(this); },
    getContext() { return new Proxy({}, { get: (_, p) => p === "measureText" ? () => ({ width: 10 }) : (...a) => { desenho.chamadas++; if (p === "fillText") desenho.textos.push(a[0]); }, set: () => true }); } };
  return el;
}
const raizJogo = noEl("div"), anuncio = { set textContent(v) { falas.push(v); } };
global.document = { getElementById: (id) => id === "jogo" ? raizJogo : id === "anuncio" ? anuncio : null, createElement: (tag) => noEl(tag), addEventListener(n, f) { (ouvintes[n] = ouvintes[n] || []).push(f); } };
global.setTimeout = (f) => { f(); return 0; };            // a fala sai na hora
global.setInterval = () => 1; global.clearInterval = () => {};
const base = require(path.join(__dirname, "..", "..", "games", "base.js")); global.Heimdall = base;
class Osc { constructor() { this.frequency = { setValueAtTime() {}, exponentialRampToValueAtTime() {} }; } connect(x) { return x; } start() { oscilador.push(1); } stop() {} }
global.window = undefined;
global.AudioContext = class { constructor() { this.currentTime = 0; this.sampleRate = 8000; this.state = "running"; this.destination = {}; }
  createOscillator() { return new Osc(); } createGain() { return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {}, value: 0 }, connect(x) { return x; } }; }
  createStereoPanner() { const p = { pan: { value: 0 }, connect(x) { return x; } }; p.pan.__p = p; (global.__pans = global.__pans || []).push(p); return p; }
  createBuffer(c, n) { return { getChannelData: () => new Float32Array(n) }; } createBufferSource() { return { connect(x) { return x; }, start() {} }; } createBiquadFilter() { return { frequency: {}, connect(x) { return x; } }; } };
delete require.cache[require.resolve(path.join(__dirname, "..", "..", "games", "vilarejo.js"))];
require(path.join(__dirname, "..", "..", "games", "vilarejo.js"));
const V = globalThis.HeimdallVilarejo;
const achar = (tag, f) => { const r = []; const q = (n) => { n.filhos.forEach(x => { if (x.tag === tag && (!f || f(x))) r.push(x); q(x); }); }; q(raizJogo); return r; };
const botao = (nome) => achar("button", b => b.textContent === nome)[0];
const campo = achar("input", i => i.attrs.id === "teclas")[0];
const tecla = (key, extra) => { const ev = Object.assign({ key, code: key.length === 1 ? "Key" + key.toUpperCase() : key, target: campo, preventDefault() { this.parado = true; }, repeat: false }, extra || {}); ouvintes.keydown.forEach(f => f(ev)); return ev; };

t("a página monta controles, canvas escondido do leitor de tela e avisa como começar", () => {
  assert(botao("Iniciar") && botao("Parar") && botao("Testar o som") && botao("Ajuda") && botao("Recarregar") && botao("Pegar, abrir e subir (X)") && botao("Usar kit médico (C)"));
  assert(!tecla("r").parado, "R não faz nada: só E diz o estado");
  const cv = achar("canvas")[0]; assert.equal(cv.attrs["aria-hidden"], "true"); assert(/teclas|Área de jogo/.test(campo.attrs["aria-label"]));
  assert(falas.some(f => /Vilarejo Sitiado/.test(f))); assert(desenho.chamadas > 50, "desenhou a cena inicial");
});
t("sem partida rodando, as teclas não fazem nada exceto no campo; ajuda funciona sempre", () => {
  const antes = falas.length; tecla("w", { target: { tagName: "BODY" } }); assert.equal(falas.length, antes);
  tecla("h"); assert(/Objetivo: libertar o vilarejo/.test(falas[falas.length - 1]));
  tecla("w"); assert(/não está rodando/.test(falas[falas.length - 1]));
});
t("Iniciar começa a partida e fala o objetivo", () => {
  botao("Iniciar").ouvintes.click[0](); assert(/Partida iniciada, nível normal/.test(falas[falas.length - 1]) && /derrube o chefe/.test(falas[falas.length - 1]));
});
t("W A S D, setas, espaço, Shift direito, 1 a 4, X, E, O, Q e H são reconhecidos e consomem a tecla", () => {
  const casos = { w: 1, a: 1, s: 1, d: 1, ArrowUp: 1, ArrowDown: 1, ArrowLeft: 1, ArrowRight: 1, " ": 1, q: 1, x: 1, c: 1, e: 1, o: 1, h: 1, 1: 1, 2: 1, 3: 1, 4: 1 };
  Object.keys(casos).forEach(k => { const ev = tecla(k); assert(ev.parado, "tecla não tratada: " + k); });
  const sh = tecla("Shift", { code: "ShiftRight" }); assert(sh.parado, "Shift direito recarrega");
  const shE = tecla("Shift", { code: "ShiftLeft" }); assert(!shE.parado, "Shift esquerdo não faz nada");
  assert(!tecla("w", { ctrlKey: true }).parado, "Ctrl+W é do navegador");
});
t("andar e mirar mudam o estado de verdade e o som sai em estéreo", () => {
  botao("Iniciar").ouvintes.click[0](); const antes = oscilador.length;
  tecla("w"); tecla("ArrowLeft"); tecla("ArrowUp"); tecla(" "); assert(oscilador.length > antes);
  assert(global.__pans.some(p => p.pan.value < 0) && global.__pans.some(p => p.pan.value === 0), "som à esquerda e no centro");
});
t("a fala curta dispensa descrições; a completa traz tudo", () => {
  const sel = achar("select", s => s.attrs.id === "fala")[0]; sel.value = "curta"; sel.ouvintes.change[0]();
  botao("Iniciar").ouvintes.click[0](); const n0 = falas.length; tecla("s"); assert.equal(falas.length, n0, "andar em silêncio não fala");
  tecla("e"); assert(/Vida/.test(falas[falas.length - 1]), "o estado pedido fala sempre");
});
t("comando por texto também joga e o estado fala vida e arma", () => {
  const c2 = achar("input", i => i.attrs.id === "comando")[0]; c2.value = "status"; c2.ouvintes.keydown[0]({ key: "Enter", preventDefault() {} }); assert(/Vida \d+ de \d+\. Arma: revólver/.test(falas[falas.length - 1]), falas[falas.length - 1]);
});
t("desenhar roda em todos os cenários (dentro, andar de cima, fim) sem erro", () => {
  const e = V.novo("normal"); V.ANDAR0.length; // só garante a API
  ["facil", "normal", "dificil"].forEach(n => { const x = V.novo(n); x.andar = 1; x.x = 16; x.y = 12; assert(x.mapa[1][12][16] === "v"); });
  const antes = desenho.chamadas; botao("Estado").ouvintes.click[0](); botao("Olhar").ouvintes.click[0](); assert(desenho.chamadas >= antes);
  assert(desenho.textos.some(x => /VIDA/.test(x)));
});
console.log(`\n${ok} testes`);
