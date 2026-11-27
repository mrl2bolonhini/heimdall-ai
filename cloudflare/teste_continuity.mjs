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
const estadoDO = { contato: "", pausa: false, copia: "" };
const cont = { get: () => ({ registrarContato: async (i) => { estadoDO.contato = i; }, definirPausa: async (v) => { estadoDO.pausa = v; }, estadoNuvem: async () => ({ ...estadoDO }), fetch: async (req) => { chamadasContainer.push(req); return new Response("<html><body><h1>Finance</h1></body></html>", { headers: { "Content-Type": "text/html", "X-Heimdall-Copia": "2026-11-23T21:00:00+00:00" } }); } }), idFromName: (n) => n };
const env = (extra = {}) => ({ CONTINUIDADE: "1", ROTAS, CONTAINER: cont, ...extra });
const ctx = { waitUntil: (p) => { esperas.push(p); } };
const esperas = [];
const pedir = (url = "https://finance.x.tech/", init) => new Request(url, init);

let r = await W.default.fetch(pedir(), env(), ctx);
confere("com o Mac no ar só repassa ao Mac", (await r.text()) === "do mac" && chamadasContainer.length === 0);
r = await W.default.fetch(pedir("https://outro.tech/"), env({ ROTAS: "{}" }), ctx);
confere("site que não é do StudioLibre é repassado", (await r.text()) === "do mac");
r = await W.default.fetch(pedir(), env({ CONTINUIDADE: "0" }), ctx);
confere("interruptor desligado (CONTINUIDADE=0) nunca usa o contêiner", (await r.text()) === "do mac" && chamadasContainer.length === 0);
macStatus = 500;
r = await W.default.fetch(pedir(), env(), ctx);
confere("erro 500 do próprio site não troca para o contêiner", r.status === 500 && chamadasContainer.length === 0);

macStatus = 530;
r = await W.default.fetch(pedir(), env(), ctx);
let t = await r.text();
confere("túnel fora (530): atende pelo contêiner", chamadasContainer.length === 1 && t.includes("<h1>Finance</h1>"));
confere("a página leva o aviso de continuidade com a data da cópia", t.includes('role="status"') && t.includes("Modo de continuidade") && /20\/11\/2026|23\/11\/2026/.test(t) && t.includes("somente para leitura"), t);
confere("cabeçalho marca o modo e não vaza o da cópia", r.headers.get("X-Heimdall-Modo") === "continuidade" && !r.headers.get("X-Heimdall-Copia"));
const antes = chamadasMac;
r = await W.default.fetch(pedir(), env(), ctx);
confere("durante a pausa não sonda o Mac a cada requisição", chamadasMac === antes && chamadasContainer.length === 2);

r = await W.default.fetch(pedir("https://finance.x.tech/transacoes/nova", { method: "POST", body: "a=1" }), env(), ctx);
confere("envio (POST) em continuidade é recusado, somente leitura", r.status === 503 && (await r.text()).includes("somente para leitura") && chamadasContainer.length === 2);
r = await W.default.fetch(pedir("https://finance.x.tech/entrar", { method: "POST", body: "senha=x" }), env(), ctx);
confere("login (POST /entrar) continua permitido", chamadasContainer.length === 3 && r.status === 200);

// falha do contêiner
const quebrado = { CONTAINER: { idFromName: (n) => n, get: () => ({ fetch: async () => { throw new Error("O contêiner não respondeu a tempo."); } }) } };
r = await W.viaContainer(pedir(), env(quebrado), ctx);
t = await r.text();
confere("contêiner que não sobe mostra página de indisponibilidade em português", r.status === 503 && t.includes('lang="pt-BR"') && t.includes("indisponível") && t.includes("<h1>"));
confere("avisos escapam HTML", !W.aviso('<script>x</script>').includes("<script>"));

// --- páginas de fora do ar, painel e Access ---
macStatus = 200;
const FORA = JSON.stringify({ "chat.x.tech": "Chat" });
const envN = (extra = {}) => env({ FORA, PAINEL: "controls.x.tech", HEIMDALL_CFACCESS_AUD: "aud1", HEIMDALL_CFACCESS_EQUIPE: "equipe", ...extra });
W.reiniciarMemoria();
r = await W.default.fetch(pedir("https://chat.x.tech/"), envN(), ctx);
confere("chat com o Mac no ar é repassado", (await r.text()) === "do mac");
await Promise.all(esperas);
confere("o último contato com o Mac é registrado", estadoDO.contato !== "");
macLanca = true;
r = await W.default.fetch(pedir("https://chat.x.tech/"), envN(), ctx);
t = await r.text();
confere("chat fora do ar mostra página própria (503, pt-BR, h1, status)", r.status === 503 && t.includes('lang="pt-BR"') && t.includes("<h1>Chat indisponível") && t.includes('role="status"') && t.includes("Último contato"), t);
confere("a página lista os sites em leitura", t.includes("finance.x.tech") && chamadasContainer.length === 3);

// Access: gera um par RSA e um JWKS falso
const par = await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
const jwk = { ...(await crypto.subtle.exportKey("jwk", par.publicKey)), kid: "k1" };
const b64 = (b) => Buffer.from(b).toString("base64url");
const jwt = async (corpo, chave = par.privateKey) => { const h = b64(JSON.stringify({ alg: "RS256", kid: "k1" })), c = b64(JSON.stringify(corpo));
  return `${h}.${c}.${b64(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", chave, new TextEncoder().encode(h + "." + c)))}`; };
const buscaCerts = async () => new Response(JSON.stringify({ keys: [jwk] }));
const futuro = Math.floor(Date.now() / 1000) + 600;
const comJwt = async (corpo, extra) => pedir("https://controls.x.tech/", { headers: { "Cf-Access-Jwt-Assertion": await jwt(corpo), ...(extra || {}) } });
const eA = envN({ BUSCAR: buscaCerts });
confere("Access: token válido passa", await W.verificarAccess(await comJwt({ aud: ["aud1"], exp: futuro }), eA, buscaCerts));
confere("Access: AUD errado é recusado", !(await W.verificarAccess(await comJwt({ aud: ["outro"], exp: futuro }), eA, buscaCerts)));
confere("Access: token vencido é recusado", !(await W.verificarAccess(await comJwt({ aud: ["aud1"], exp: 1 }), eA, buscaCerts)));
const outra = await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
const falso = pedir("https://controls.x.tech/", { headers: { "Cf-Access-Jwt-Assertion": await jwt({ aud: ["aud1"], exp: futuro }, outra.privateKey) } });
confere("Access: assinatura falsa é recusada", !(await W.verificarAccess(falso, eA, buscaCerts)));
confere("Access: nome de equipe com formato estranho é recusado (nada de endereço fora de cloudflareaccess.com)", !(await W.verificarAccess(await comJwt({ aud: ["aud1"], exp: futuro }), envN({ HEIMDALL_CFACCESS_EQUIPE: "evil.com/x" }), buscaCerts)));
confere("Access: sem cabeçalho ou sem configuração é recusado", !(await W.verificarAccess(pedir("https://controls.x.tech/"), eA, buscaCerts)) && !(await W.verificarAccess(await comJwt({ aud: ["aud1"], exp: futuro }), envN({ HEIMDALL_CFACCESS_AUD: "" }), buscaCerts)));

// painel
W.reiniciarMemoria(); macLanca = true;
r = await W.default.fetch(pedir("https://controls.x.tech/"), eA, ctx);
confere("painel sem login do Access: 403", r.status === 403);
r = await W.default.fetch(await comJwt({ aud: ["aud1"], exp: futuro }), eA, ctx);
t = await r.text();
confere("painel com Access mostra estado e botão de pausa", r.status === 200 && t.includes("fora do ar") && t.includes("Pausar a continuidade") && t.includes("<h1>Nuvem do StudioLibre"), t);
const post = async (extra) => pedir("https://controls.x.tech/continuidade/pausa", { method: "POST", body: new URLSearchParams({ pausar: "1" }), headers: { "Cf-Access-Jwt-Assertion": await jwt({ aud: ["aud1"], exp: futuro }), ...(extra || {}) } });
r = await W.default.fetch(await post({ Origin: "https://malicioso.tech" }), eA, ctx);
confere("pausa vinda de outra origem é recusada", r.status === 403 && estadoDO.pausa === false);
r = await W.default.fetch(await post({ Origin: "https://controls.x.tech" }), eA, ctx);
confere("pausa pelo painel grava e redireciona", r.status === 303 && estadoDO.pausa === true);
macLanca = false; macStatus = 200;
const antesC = chamadasContainer.length;
r = await W.default.fetch(pedir("https://finance.x.tech/"), envN(), ctx);
confere("com a pausa ligada só repassa ao Mac", (await r.text()) === "do mac" && chamadasContainer.length === antesC);
macLanca = true; W.reiniciarMemoria();
try { await W.default.fetch(pedir("https://finance.x.tech/"), envN(), ctx); } catch (e) { /* o repasse falha como falharia sem o Worker */ }
confere("com a pausa ligada e o Mac fora, não liga o contêiner", chamadasContainer.length === antesC);
macLanca = false; W.reiniciarMemoria();
r = await W.default.fetch(await (async () => pedir("https://controls.x.tech/continuidade", { headers: { "Cf-Access-Jwt-Assertion": await jwt({ aud: ["aud1"], exp: futuro }) } }))(), eA, ctx);
t = await r.text();
confere("/continuidade responde pela nuvem mesmo com o Mac no ar e mostra a pausa", r.status === 200 && t.includes("no ar") && t.includes("pausada") && t.includes("Retomar a continuidade"), t);
r = await W.default.fetch(pedir("https://controls.x.tech/continuidade"), eA, ctx);
confere("/continuidade sem Access: 403 mesmo com o Mac no ar", r.status === 403);
r = await W.default.fetch(pedir("https://controls.x.tech/outra", { method: "POST", body: "a=1" }), eA, ctx);
confere("POST do Controls do Mac passa direto ao Mac", (await r.text()) === "do mac");
// consumo do mês
W.reiniciarMemoria();
const respPaygo = (corpo, status = 200) => async (url, init) => { respPaygo.visto = { url, auth: init.headers.Authorization }; return new Response(JSON.stringify(corpo), { status }); };
let cm = await W.consumoMes({ HEIMDALL_CF_LEITURA_TOKEN: "tk", CLOUDFLARE_ACCOUNT_ID: "ct" }, respPaygo({ result: [
  { ServiceName: "Workers Standard", BilledCost: 5 }, { ServiceName: "Containers", BilledCost: 1.25 }, { ServiceName: "Containers", BilledCost: 0.5 }] }));
confere("consumo: soma por serviço, ordena e traz o teto", cm.ok && cm.total === 6.75 && cm.itens[0].servico === "Workers Standard" && cm.itens[1].custo === 1.75 && cm.teto === 15, JSON.stringify(cm));
confere("consumo: usa a conta e o token de leitura", respPaygo.visto.url.includes("/accounts/ct/billing/usage/paygo") && respPaygo.visto.auth === "Bearer tk");
let bl = W.blocoConsumo(cm);
confere("consumo: bloco com caption, scope, valores em reais-dólar e sem alerta abaixo de 80%", bl.includes("<caption>Consumo faturável") && bl.includes('scope="row">Containers') && bl.includes("US$ 6,75") && !bl.includes("perto do teto"), bl);
confere("consumo: perto do teto avisa", W.blocoConsumo({ ok: true, total: 13, itens: [], teto: 15 }).includes("perto do teto"));
W.reiniciarMemoria();
confere("consumo: sem token explica o que falta", (await W.consumoMes({}, respPaygo({}))).erro.includes("não configurado"));
W.reiniciarMemoria();
confere("consumo: 403 vira aviso de permissão", (await W.consumoMes({ HEIMDALL_CF_LEITURA_TOKEN: "tk", CLOUDFLARE_ACCOUNT_ID: "ct" }, respPaygo({}, 403))).erro.includes("Faturamento"));
W.reiniciarMemoria();
confere("consumo: API não liberada (404) explica sem inventar valor", (await W.consumoMes({ HEIMDALL_CF_LEITURA_TOKEN: "tk", CLOUDFLARE_ACCOUNT_ID: "ct" }, respPaygo({}, 404))).erro.includes("beta"));
W.reiniciarMemoria();
confere("o token de leitura não é repassado ao contêiner", !fonte.slice(fonte.indexOf("const SEGREDOS"), fonte.indexOf("const PORTA_SAUDE")).includes("LEITURA_TOKEN"));
// avisos da Cloudflare
W.reiniciarMemoria();
const respAv = (corpo, status = 200) => async (url, init) => { respAv.url = url; return new Response(JSON.stringify(corpo), { status }); };
const E2 = { HEIMDALL_CF_LEITURA_TOKEN: "tk", CLOUDFLARE_ACCOUNT_ID: "ct" };
let av = await W.avisosCloudflare(E2, respAv({ result: [
  { name: "Origem fora", alert_type: "health_check_status_notification", alert_body: "O Mac <b>caiu</b>", sent: "2026-11-23T21:00:00Z" },
  { alert_type: "universal_ssl_event_type", sent: "2026-11-23T22:00:00Z", description: "Certificado" }] }));
confere("avisos: lê o histórico, ordena do mais novo e usa o endereço certo", av.ok && av.itens[0].nome === "universal_ssl_event_type" && av.itens[1].nome === "Origem fora" && respAv.url.includes("/accounts/ct/alerting/v3/history"), JSON.stringify(av));
let ba = W.blocoAvisos(av);
confere("avisos: tabela com caption e scope, com HTML escapado", ba.includes("<caption>Últimos avisos") && ba.includes('scope="row">') && !ba.includes("<b>caiu") && ba.includes("&lt;b&gt;caiu"), ba);
confere("avisos: lista vazia e erro explicam sem inventar", W.blocoAvisos({ ok: true, itens: [] }).includes("Nenhum aviso") && W.blocoAvisos({ ok: false, erro: "x" }).includes("x"));
W.reiniciarMemoria();
confere("avisos: 403 vira aviso de permissão", (await W.avisosCloudflare(E2, respAv({}, 403))).erro.includes("Notificações"));
W.reiniciarMemoria();
confere("avisos: sem token explica o que falta", (await W.avisosCloudflare({}, respAv({}))).erro.includes("não configurado"));
console.log(falhas ? `${falhas} falha(s)` : "Tudo certo.");
process.exit(falhas ? 1 : 0);
