// Teste da caixa de correio: papéis, isolamento entre pessoas, limites.  node cloudflare/teste_caixa.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "caixa-"));
fs.writeFileSync(path.join(dir, "caixa.mjs"), fs.readFileSync(new URL("./caixa.js", import.meta.url), "utf8"));
const { default: caixa } = await import(path.join(dir, "caixa.mjs"));
let falhas = 0;
const confere = (n, ok) => { console.log((ok ? "OK    " : "FALHA ") + n); if (!ok) falhas++; };

class KV { constructor() { this.m = new Map(); }
  async get(k) { return this.m.get(k) ?? null; } async put(k, v) { this.m.set(k, v); } async delete(k) { this.m.delete(k); } }
class R2 { constructor() { this.m = new Map(); }
  async put(k, v) { this.m.set(k, v); }
  async get(k) { return this.m.has(k) ? { text: async () => this.m.get(k) } : null; }
  async delete(k) { this.m.delete(k); }
  async list({ prefix, delimiter, limit = 1000 }) {
    const chaves = [...this.m.keys()].filter((k) => k.startsWith(prefix)).sort();
    if (delimiter) { const s = new Set(chaves.map((k) => prefix + k.slice(prefix.length).split(delimiter)[0] + delimiter)); return { objects: [], delimitedPrefixes: [...s] }; }
    return { objects: chaves.slice(0, limit).map((key) => ({ key })) };
  } }
const env = { CAIXA: new R2(), TOKENS: new KV(), CONTA_ID: "conta123" };
let cfOk = true;
globalThis.fetch = async (u, o) => new Response("{}", { status: cfOk && o.headers.authorization === "Bearer cf-bom" ? 200 : 403 });

const chamar = async (metodo, rota, { token, corpo, cf } = {}) => {
  const headers = {};
  if (token) headers.authorization = "Bearer " + token;
  if (cf) headers["x-cf-token"] = cf;
  const r = await caixa.fetch(new Request("https://x.dev" + rota, { method: metodo, headers, body: corpo === undefined ? undefined : (typeof corpo === "string" ? corpo : JSON.stringify(corpo)) }), env);
  return { status: r.status, json: await r.json() };
};

let r = await chamar("GET", "/v1/entrada");
confere("sem token: 401", r.status === 401);
r = await chamar("POST", "/v1/iniciar", { cf: "cf-ruim" });
confere("iniciar com token da Cloudflare inválido: 401", r.status === 401);
r = await chamar("POST", "/v1/iniciar");
confere("iniciar sem nada: 401", r.status === 401);
r = await chamar("POST", "/v1/iniciar", { cf: "cf-bom" });
const dono = r.json.token;
confere("iniciar com token válido entrega token de dono", r.status === 200 && /^hc_[0-9a-f]{48}$/.test(dono));
r = await chamar("POST", "/v1/iniciar", { cf: "cf-bom" });
const dono2 = r.json.token;
r = await chamar("GET", "/v1/entrada", { token: dono });
confere("novo iniciar invalida o token de dono anterior", r.status === 401);
r = await chamar("GET", "/v1/entrada", { token: dono2 });
confere("token novo do dono funciona", r.status === 200);

r = await chamar("POST", "/v1/tokens", { token: dono2, corpo: { usuario: "ana" } });
const ana = r.json.token;
r = await chamar("POST", "/v1/tokens", { token: dono2, corpo: { usuario: "bia" } });
const bia = r.json.token;
confere("dono cria tokens de pessoas", !!ana && !!bia);
r = await chamar("POST", "/v1/tokens", { token: dono2, corpo: { usuario: "dono" } });
confere("nome 'dono' é recusado", r.status === 400);
r = await chamar("POST", "/v1/tokens", { token: dono2, corpo: { usuario: "../x" } });
confere("nome com caracteres inválidos é recusado", r.status === 400);
r = await chamar("POST", "/v1/tokens", { token: ana, corpo: { usuario: "cris" } });
confere("telefone não cria tokens", r.status === 403);
const hashes = [...env.TOKENS.m.keys()].filter((k) => k.startsWith("tok:"));
confere("o KV guarda só hash, nunca o token", !JSON.stringify([...env.TOKENS.m.values()]).includes(ana) && hashes.every((k) => k.length === 68));

r = await chamar("POST", "/v1/enviar", { token: ana, corpo: { tipo: "saude", dados: { passos: 1000 } } });
const idAna = r.json.id;
confere("telefone envia à própria caixa", r.status === 200 && /^[0-9]{13}-[0-9a-f]{12}$/.test(idAna));
await chamar("POST", "/v1/enviar", { token: bia, corpo: { tipo: "nota", dados: { t: "oi" } } });
r = await chamar("POST", "/v1/enviar", { token: ana, corpo: { tipo: "virus", dados: 1 } });
confere("tipo desconhecido é recusado", r.status === 400);
r = await chamar("POST", "/v1/enviar", { token: ana, corpo: "isto não é json" });
confere("JSON inválido é recusado", r.status === 400);
r = await chamar("POST", "/v1/enviar", { token: ana, corpo: { tipo: "nota", dados: "x".repeat(300 * 1024) } });
confere("corpo grande demais é recusado (413)", r.status === 413);
r = await chamar("POST", "/v1/enviar", { token: ana, corpo: { tipo: "nota", dados: "a", usuario: "bia" } });
const idIntruso = r.json.id;
confere("telefone não escolhe o destino: o campo usuario é ignorado", [...env.CAIXA.m.keys()].some((k) => k === `u/ana/entrada/${idIntruso}.json`) && ![...env.CAIXA.m.keys()].some((k) => k === `u/bia/entrada/${idIntruso}.json`));

r = await chamar("GET", "/v1/entrada", { token: ana });
confere("telefone não lê a entrada", r.status === 403);
r = await chamar("GET", "/v1/entrada", { token: dono2 });
confere("dono lê entradas de todos, com o nome da pessoa", r.status === 200 && r.json.itens.length === 3 && r.json.itens.some((i) => i.usuario === "bia" && i.tipo === "nota") && r.json.itens.some((i) => i.usuario === "ana" && i.dados.passos === 1000));
r = await chamar("GET", "/v1/entrada?usuario=bia", { token: dono2 });
confere("dono filtra por pessoa", r.json.itens.length === 1);
r = await chamar("DELETE", `/v1/entrada/ana/${idAna}`, { token: ana });
confere("telefone não apaga entrada", r.status === 403);
r = await chamar("DELETE", `/v1/entrada/ana/${idAna}`, { token: dono2 });
r = await chamar("GET", "/v1/entrada?usuario=ana", { token: dono2 });
confere("dono apaga o item depois de processar", r.json.itens.length === 1);

r = await chamar("POST", "/v1/saida", { token: ana, corpo: { usuario: "ana", tipo: "lembrete", dados: {} } });
confere("telefone não escreve na saída", r.status === 403);
r = await chamar("POST", "/v1/saida", { token: dono2, corpo: { usuario: "ana", tipo: "lembrete", dados: { titulo: "Tomar remédio" } } });
const idSaida = r.json.id;
r = await chamar("GET", "/v1/saida", { token: ana });
confere("telefone lê a própria saída", r.status === 200 && r.json.itens.length === 1 && r.json.itens[0].dados.titulo === "Tomar remédio");
r = await chamar("GET", "/v1/saida", { token: bia });
confere("telefone de outra pessoa não vê a saída alheia", r.json.itens.length === 0);
r = await chamar("GET", "/v1/saida?usuario=ana", { token: bia });
confere("telefone não escolhe outro usuário por parâmetro", r.json.itens.length === 0);
r = await chamar("DELETE", `/v1/saida/${idSaida}?usuario=ana`, { token: bia });
r = await chamar("GET", "/v1/saida", { token: ana });
confere("telefone alheio não apaga a saída de outra pessoa", r.json.itens.length === 1);
r = await chamar("DELETE", `/v1/saida/${idSaida}`, { token: ana });
r = await chamar("GET", "/v1/saida", { token: ana });
confere("telefone confirma e o item some", r.json.itens.length === 0);

r = await chamar("DELETE", "/v1/tokens/ana", { token: dono2 });
confere("dono revoga a pessoa", r.status === 200 && r.json.revogados === 1);
r = await chamar("GET", "/v1/saida", { token: ana });
confere("token revogado deixa de valer", r.status === 401);
r = await chamar("GET", "/v1/saida", { token: bia });
confere("revogar uma pessoa não afeta as outras", r.status === 200);

let ultimo;
for (let i = 0; i < 500; i++) ultimo = await chamar("POST", "/v1/enviar", { token: bia, corpo: { tipo: "outro", dados: i } });
r = await chamar("POST", "/v1/enviar", { token: bia, corpo: { tipo: "outro", dados: 0 } });
confere("limite diário de envios por pessoa (429)", r.status === 429);
r = await chamar("GET", "/v1/nada", { token: dono2 });
confere("rota desconhecida: 404", r.status === 404);

console.log(falhas ? `\n${falhas} falha(s)` : "\nTudo certo.");
process.exit(falhas ? 1 : 0);
