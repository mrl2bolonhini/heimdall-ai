// Teste do vigia: quantas gravações no KV por dia.  node cloudflare/teste_vigia.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vigia-"));
const fonte = fs.readFileSync(new URL("./vigia.js", import.meta.url), "utf8").replace('import { EmailMessage } from "cloudflare:email";', "class EmailMessage { constructor(...a) { this.a = a; } }");
fs.writeFileSync(path.join(dir, "vigia.mjs"), fonte);
const { rodar } = await import(path.join(dir, "vigia.mjs"));
let falhas = 0;
const confere = (n, ok) => { console.log((ok ? "OK    " : "FALHA ") + n); if (!ok) falhas++; };
class KV { constructor() { this.m = new Map(); this.gravacoes = 0; }
  async get(k) { return this.m.get(k) ?? null; } async put(k, v) { this.gravacoes++; this.m.set(k, v); } }
let status = 200;
globalThis.fetch = async () => (status === 0 ? Promise.reject(new Error("sem rota")) : new Response("", { status }));
const enviados = [];
const env = { ESTADO: new KV(), EMAIL: { send: async (m) => enviados.push(m) }, ALERTA_DE: "v@x.tech", ALERTA_PARA: "eu@x.tech" };
const relogio = Date.now;
let agora = Date.now();
Date.now = () => agora;

await rodar(env);
confere("primeira rodada grava estado e hora", env.ESTADO.gravacoes === 2);
for (let i = 0; i < 12; i++) { agora += 5 * 60 * 1000; await rodar(env); }   // uma hora de rodadas iguais, de 5 em 5 minutos
confere("uma hora com tudo igual grava só o batimento (1 gravação a mais)", env.ESTADO.gravacoes === 3);
for (let i = 0; i < 288; i++) { agora += 5 * 60 * 1000; await rodar(env); }   // um dia inteiro
confere("um dia inteiro sem mudança grava cerca de 24 vezes, não 576", env.ESTADO.gravacoes <= 3 + 24 + 1);
status = 503;
agora += 5 * 60 * 1000; await rodar(env);
const antesDaQueda = env.ESTADO.gravacoes;
agora += 5 * 60 * 1000; await rodar(env);
confere("quando algo muda, o estado é gravado e o aviso sai depois de duas falhas", enviados.length === 1 && env.ESTADO.gravacoes > antesDaQueda);
status = 200;
agora += 5 * 60 * 1000; await rodar(env);
confere("quando volta, avisa", enviados.length === 2);
Date.now = relogio;
console.log(falhas ? `${falhas} falha(s)` : "Tudo certo.");
process.exit(falhas ? 1 : 0);
