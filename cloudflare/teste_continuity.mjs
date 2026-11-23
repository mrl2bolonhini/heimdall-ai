// Teste do Worker de continuidade (failover do Mac para o contêiner).  node cloudflare/teste_continuity.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "continuity-"));
const fonte = fs.readFileSync(new URL("./continuity/worker.js", import.meta.url), "utf8")
  .replace('import { DurableObject } from "cloudflare:workers";', "class DurableObject { constructor(ctx, env) { this.ctx = ctx; } }");
fs.writeFileSync(path.join(dir, "worker.mjs"), fonte);
const W = await import(path.join(dir, "worker.mjs"));
let falhas = 0;
const confere = (n, ok, d = "") => { console.log((ok ? "OK    " : "FALHA ") + n + (ok || !d ? "" : "  -> " + d)); if (!ok) falhas++; };

// HTMLRewriter mínimo para o teste: injeta o texto logo depois de <body ...>
globalThis.HTMLRewriter = class { on(_s, h) { this.h = h; return this; }
  transform(resp) { const h = this.h; return new Response(new ReadableStream({ async start(c) { const t = await resp.text(); let ins = ""; h.element({ prepend: (x) => { ins = x; } });
    c.enqueue(new TextEncoder().encode(t.replace(/(<body[^>]*>)/, "$1" + ins))); c.close(); } }), resp); } };

let macStatus = 200, macLanca = false, chamadasMac = 0;
globalThis.fetch = async (req) => { chamadasMac++; if (macLanca) throw new Error("sem rota"); return new Response("do mac", { status: macStatus }); };
const ROTAS = JSON.stringify({ "finance.x.tech": 8016 });
const chamadasContainer = [];
const cont = { get: () => ({ fetch: async (req) => { chamadasContainer.push(req); return new Response("<html><body><h1>Finance</h1></body></html>", { headers: { "Content-Type": "text/html", "X-Heimdall-Copia": "2026-11-23T21:00:00+00:00" } }); } }), idFromName: (n) => n };
const env = (extra = {}) => ({ CONTINUIDADE: "1", ROTAS, CONTAINER: cont, ...extra });
const pedir = (url = "https://finance.x.tech/", init) => new Request(url, init);

let r = await W.default.fetch(pedir(), env(), {});
confere("com o Mac no ar só repassa ao Mac", (await r.text()) === "do mac" && chamadasContainer.length === 0);
r = await W.default.fetch(pedir("https://outro.tech/"), env({ ROTAS: "{}" }), {});
confere("site que não é do Heimdall é repassado", (await r.text()) === "do mac");
r = await W.default.fetch(pedir(), env({ CONTINUIDADE: "0" }), {});
confere("interruptor desligado (CONTINUIDADE=0) nunca usa o contêiner", (await r.text()) === "do mac" && chamadasContainer.length === 0);
macStatus = 500;
r = await W.default.fetch(pedir(), env(), {});
confere("erro 500 do próprio site não troca para o contêiner", r.status === 500 && chamadasContainer.length === 0);

macStatus = 530;
r = await W.default.fetch(pedir(), env(), {});
let t = await r.text();
confere("túnel fora (530): atende pelo contêiner", chamadasContainer.length === 1 && t.includes("<h1>Finance</h1>"));
confere("a página leva o aviso de continuidade com a data da cópia", t.includes('role="status"') && t.includes("Modo de continuidade") && /20\/11\/2026|23\/11\/2026/.test(t) && t.includes("somente para leitura"), t);
confere("cabeçalho marca o modo e não vaza o da cópia", r.headers.get("X-Heimdall-Modo") === "continuidade" && !r.headers.get("X-Heimdall-Copia"));
const antes = chamadasMac;
r = await W.default.fetch(pedir(), env(), {});
confere("durante a pausa não sonda o Mac a cada requisição", chamadasMac === antes && chamadasContainer.length === 2);

r = await W.default.fetch(pedir("https://finance.x.tech/transacoes/nova", { method: "POST", body: "a=1" }), env(), {});
confere("envio (POST) em continuidade é recusado, somente leitura", r.status === 503 && (await r.text()).includes("somente para leitura") && chamadasContainer.length === 2);
r = await W.default.fetch(pedir("https://finance.x.tech/entrar", { method: "POST", body: "senha=x" }), env(), {});
confere("login (POST /entrar) continua permitido", chamadasContainer.length === 3 && r.status === 200);

// falha do contêiner
const quebrado = { CONTAINER: { idFromName: (n) => n, get: () => ({ fetch: async () => { throw new Error("O contêiner não respondeu a tempo."); } }) } };
r = await W.viaContainer(pedir(), env(quebrado), {});
t = await r.text();
confere("contêiner que não sobe mostra página de indisponibilidade em português", r.status === 503 && t.includes('lang="pt-BR"') && t.includes("indisponível") && t.includes("<h1>"));
confere("avisos escapam HTML", !W.aviso('<script>x</script>').includes("<script>"));
console.log(falhas ? `${falhas} falha(s)` : "Tudo certo.");
process.exit(falhas ? 1 : 0);
