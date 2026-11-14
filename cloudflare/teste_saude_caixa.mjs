// Teste da caixa de entrada com KV e fetch de mentira:  node cloudflare/teste_saude_caixa.mjs
import caixa, { esvaziar } from "./saude_caixa.js";
let falhas = 0;
const confere = (n, ok) => { console.log((ok ? "OK    " : "FALHA ") + n); if (!ok) falhas++; };
class KV { constructor() { this.m = new Map(); }
  async get(k) { return this.m.get(k) ?? null; } async put(k, v) { this.m.set(k, v); } async delete(k) { this.m.delete(k); }
  async list({ prefix, limit }) { return { keys: [...this.m.keys()].filter(k => k.startsWith(prefix)).sort().slice(0, limit).map(name => ({ name })) }; } }
let origem = "fora"; const vistos = [];
globalThis.fetch = async (a, b) => {
  const req = a instanceof Request ? a : new Request(a, b);
  const corpo = await req.clone().text();
  vistos.push({ reenvio: req.headers.get("x-heimdall-reenvio"), corpo });
  if (origem === "fora") throw new Error("sem rota");
  if (origem === "530") return new Response("", { status: 530 });
  return new Response("ok", { status: 200 });
};
const env = { FILA: new KV() };
const post = (corpo, h = {}) => new Request("https://flows.heimdall-ai.tech/webhook/heimdall-saude", { method: "POST", body: corpo, headers: { "content-type": "application/json", "x-heimdall-saude": "segredo-longo-123", ...h } });
let r = await caixa.fetch(post('{"a":1}'), env);
confere("origem fora: responde 202 e guarda", r.status === 202 && env.FILA.m.size === 1);
origem = "530"; r = await caixa.fetch(post('{"a":2}'), env);
confere("origem com 530: também guarda", r.status === 202 && env.FILA.m.size === 2);
await esvaziar(env);
confere("com a origem ainda fora, nada é apagado", env.FILA.m.size === 2);
origem = "ok"; r = await caixa.fetch(post('{"a":3}'), env);
confere("origem no ar: repassa sem guardar", r.status === 200 && env.FILA.m.size === 2);
const n = await esvaziar(env);
confere("origem volta: reenvia tudo e esvazia a fila", n === 2 && env.FILA.m.size === 0);
confere("reenvios levam o cabeçalho de reenvio", vistos.filter(v => v.reenvio === "1").length >= 2);
origem = "fora"; env.TOKEN_SAUDE = "outro-segredo";
r = await caixa.fetch(post('{"a":4}'), env);
confere("com TOKEN_SAUDE, token errado não entra na fila", r.status === 503 && env.FILA.m.size === 0);
r = await caixa.fetch(post('{"a":5}', { "x-heimdall-saude": "outro-segredo" }), env);
confere("com TOKEN_SAUDE, token certo entra", r.status === 202 && env.FILA.m.size === 1);
delete env.TOKEN_SAUDE; env.FILA.m.clear();
for (let i = 0; i < 200; i++) await env.FILA.put("fila:" + String(i).padStart(14, "0") + ":x", "{}");
r = await caixa.fetch(post('{"a":6}'), env);
confere("fila cheia (200) recusa com 503", r.status === 503);
env.FILA.m.clear(); await caixa.fetch(post("x".repeat(9 * 1024 * 1024)), env);
confere("corpo grande demais não é guardado", env.FILA.m.size === 0);
console.log(falhas ? falhas + " falha(s)" : "Tudo certo.");
process.exit(falhas ? 1 : 0);
