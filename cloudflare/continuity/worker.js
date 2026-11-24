// Heimdall Continuidade: Worker de entrada que mantém os sites no ar quando o Mac está fora (queda de energia, rede).
// Em condições normais só repassa a requisição ao Mac pelo túnel. Se o Mac não responde, liga o contêiner (Cloudflare Containers),
// que restaura a última cópia cifrada dos bancos e atende em modo SOMENTE LEITURA, com um aviso no topo de cada página.
// O contêiner dorme sozinho depois de um tempo sem uso, então só custa enquanto o Mac está fora.
//
// Ligações (bindings) e variáveis na Cloudflare (ver wrangler.jsonc):
//   CONTINUIDADE   variável: "1" liga o failover; "0" desliga (o Worker só repassa ao Mac): é o interruptor da fase.
//   ROTAS          variável JSON: nome do site -> porta dentro do contêiner.
//   CONTAINER      Durable Object com o contêiner (classe Continuidade).
//   Segredos repassados ao contêiner (wrangler secret put, lidos do .env por scripts/continuidade_nuvem.sh): ver SEGREDOS.
import { DurableObject } from "cloudflare:workers";

const FALHAS_DO_MAC = new Set([502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 530]);   // o que a Cloudflare devolve com o túnel fora
const ESPERA_MAC_MS = 4000;          // quanto esperar o Mac antes de considerar que caiu
const PAUSA_SONDA_MS = 30000;        // depois de uma queda, vai direto ao contêiner por 30 s antes de sondar o Mac de novo
const SEM_PROPAGAR = new Set(["/entrar", "/sair"]);   // únicos envios aceitos em modo somente leitura (login e logout; a sessão não grava no banco)
const SEGREDOS = ["HEIMDALL_CONTINUIDADE_SENHA", "HEIMDALL_R2_ENDPOINT", "HEIMDALL_R2_BUCKET", "HEIMDALL_R2_KEY_ID", "HEIMDALL_R2_SECRET",
  "HEIMDALL_CLOUD_SENHA_HASH", "HEIMDALL_CLOUD_TOTP_SEGREDO", "HEIMDALL_CLOUD_SESSAO_HORAS", "HEIMDALL_CFACCESS_AUD", "HEIMDALL_CFACCESS_EMAILS",
  "HEIMDALL_CFACCESS_EQUIPE", "HEIMDALL_CFACCESS_CONVIDADOS"];
const PORTA_SAUDE = 8080;

let foraAte = 0;   // por isolate: até quando pular a sonda ao Mac
let contatoGravadoEm = 0;   // por isolate: última vez que o contato com o Mac foi gravado (limita as gravações)
let pausaCache = { quando: 0, valor: false };   // por isolate: a pausa é lida do Durable Object no máximo a cada 30 s
export function reiniciarMemoria() { foraAte = 0; contatoGravadoEm = 0; pausaCache = { quando: 0, valor: false }; CERTS.quando = 0; CERTS.chaves = null; CONSUMO.quando = 0; CONSUMO.dados = null; AVISOS.quando = 0; AVISOS.dados = null; }   // para os testes
const GRAVAR_CONTATO_A_CADA_MS = 300000;
const CERTS = { quando: 0, chaves: null };
const CONSUMO = { quando: 0, dados: null };   // por isolate: o consumo do mês é consultado no máximo a cada 5 min
const AVISOS = { quando: 0, dados: null };
const TETO_MENSAL = 15;   // US$ por mês (regra do projeto)

const html = (corpo, status = 200) => new Response(corpo, { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function paginaIndisponivel(motivo) {
  return html(`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Heimdall indisponível</title></head>`
    + `<body><main><h1>Heimdall indisponível no momento</h1><p role="status">O servidor principal está fora do ar e o modo de continuidade ainda não ficou pronto. ${esc(motivo)}</p>`
    + `<p>Tente novamente em alguns minutos.</p></main></body></html>`, 503);
}

export function paginaSomenteLeitura() {
  return html(`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Somente leitura - Heimdall</title></head>`
    + `<body><main><h1>Alteração indisponível</h1><p role="alert">O Heimdall está em modo de continuidade, somente para leitura. Esta ação ficará disponível quando o servidor principal voltar.</p>`
    + `<p><a href="/">Voltar ao início</a></p></main></body></html>`, 503);
}

export function aviso(copia) {
  let quando = "data indisponível";
  const d = new Date(copia);
  if (copia && !isNaN(d)) quando = d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" });
  return `<div class="aviso" role="status">Modo de continuidade: o Heimdall está atendendo pela nuvem enquanto o servidor principal está indisponível. `
    + `As páginas são somente para leitura e mostram os dados de ${esc(quando)}.</div>`;
}

const CSS = "body{font-family:-apple-system,system-ui,sans-serif;margin:0;background:#fff;color:#1a1a1a;line-height:1.5}main{max-width:44rem;margin:0 auto;padding:1.5rem}"
  + "a,button{color:#0b57d0;font:inherit}button{padding:.5rem 1rem;border:2px solid #0b57d0;background:#fff;border-radius:.4rem;cursor:pointer}"
  + "table{border-collapse:collapse}th,td{border:1px solid #888;padding:.3rem .6rem;text-align:left}caption{text-align:left;font-weight:bold}"
  + "a:focus-visible,button:focus-visible{outline:3px solid #b45309;outline-offset:2px}"
  + "@media(prefers-color-scheme:dark){body{background:#121212;color:#eee}a,button{color:#8ab4f8}button{background:#121212;border-color:#8ab4f8}}";

function pagina(titulo, corpo, status = 200) {
  return html(`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">`
    + `<title>${esc(titulo)}</title><style>${CSS}</style></head><body><main><h1>${esc(titulo)}</h1>${corpo}</main></body></html>`, status);
}

const quandoTexto = (iso) => {
  const d = new Date(iso);
  return iso && !isNaN(d) ? d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" }) : "";
};

// Página dos serviços que dependem do Mac (chat, lab, fluxos): informa a queda, o último contato e o que segue disponível em leitura.
export function paginaForaDoAr(nome, contato, leitura) {
  const q = quandoTexto(contato);
  const links = (leitura || []).map((h) => `<li><a href="https://${esc(h)}/">${esc(h)}</a></li>`).join("");
  return pagina(`${nome} indisponível no momento`,
    `<p role="status">O ${esc(nome)} depende do servidor principal, que está fora do ar${q ? `. Último contato: ${esc(q)}` : ""}. `
    + `Ele volta sozinho quando o servidor principal voltar.</p>`
    + (links ? `<h2>Disponível em modo somente leitura</h2><ul>${links}</ul>` : ""), 503);
}

function b64u(s) { s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "="; return Uint8Array.from(atob(s), (c) => c.charCodeAt(0)); }

// Confere o token de identidade do Cloudflare Access (cabeçalho Cf-Access-Jwt-Assertion): assinatura RS256, validade e AUD. Sem configuração, recusa.
export async function verificarAccess(request, env, buscar = fetch) {
  const jwt = request.headers.get("Cf-Access-Jwt-Assertion") || "";
  const auds = String(env.HEIMDALL_CFACCESS_AUD || "").split(",").map((a) => a.trim()).filter(Boolean);
  let equipe = String(env.HEIMDALL_CFACCESS_EQUIPE || "").trim().toLowerCase();   // o mesmo nome do resto do Heimdall: a parte antes de .cloudflareaccess.com
  if (!jwt || !auds.length || !/^[a-z0-9][a-z0-9-]{0,62}(\.cloudflareaccess\.com)?$/.test(equipe)) return false;
  if (!equipe.includes(".")) equipe += ".cloudflareaccess.com";
  const partes = jwt.split(".");
  if (partes.length !== 3) return false;
  try {
    const cab = JSON.parse(new TextDecoder().decode(b64u(partes[0])));
    const corpo = JSON.parse(new TextDecoder().decode(b64u(partes[1])));
    if (cab.alg !== "RS256") return false;
    if (Date.now() - CERTS.quando > 3600000 || !CERTS.chaves) {
      const r = await buscar(`https://${equipe}/cdn-cgi/access/certs`);
      CERTS.chaves = (await r.json()).keys || [];
      CERTS.quando = Date.now();
    }
    const jwk = CERTS.chaves.find((k) => k.kid === cab.kid);
    if (!jwk) return false;
    const chave = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", chave, b64u(partes[2]), new TextEncoder().encode(partes[0] + "." + partes[1]));
    if (!ok) return false;
    const aud = Array.isArray(corpo.aud) ? corpo.aud : [corpo.aud];
    return aud.some((a) => auds.includes(a)) && typeof corpo.exp === "number" && corpo.exp * 1000 > Date.now();
  } catch (e) { return false; }
}

// Consumo do mês corrente (API de uso faturável da Cloudflare, beta). Usa um token SÓ de leitura (Faturamento: leitura), guardado como segredo do Worker
// e nunca repassado ao contêiner. Se a API não estiver liberada para a conta ou o token faltar, devolve o motivo em vez de inventar valor.
export async function consumoMes(env, buscar = fetch) {
  const token = env.HEIMDALL_CF_LEITURA_TOKEN, conta = env.CLOUDFLARE_ACCOUNT_ID;
  if (!token || !conta) return { ok: false, erro: "Token de leitura de faturamento não configurado na nuvem." };
  if (CONSUMO.dados && Date.now() - CONSUMO.quando < 300000) return CONSUMO.dados;
  let dados;
  try {
    const r = await buscar(`https://api.cloudflare.com/client/v4/accounts/${conta}/billing/usage/paygo`, { headers: { Authorization: "Bearer " + token }, signal: AbortSignal.timeout(8000) });
    if (r.status === 403) dados = { ok: false, erro: "O token de leitura não tem a permissão Faturamento (leitura)." };
    else if (!r.ok) dados = { ok: false, erro: `A Cloudflare respondeu HTTP ${r.status} à consulta de consumo (a API ainda é beta e pode não estar liberada para a conta).` };
    else {
      const linhas = (await r.json()).result || [];
      const por = {};
      let total = 0;
      for (const l of linhas) { const c = Number(l.BilledCost) || 0; por[l.ServiceName || "Outros"] = (por[l.ServiceName || "Outros"] || 0) + c; total += c; }
      dados = { ok: true, total, itens: Object.entries(por).map(([servico, custo]) => ({ servico, custo })).sort((a, b) => b.custo - a.custo), teto: TETO_MENSAL };
    }
  } catch (e) { dados = { ok: false, erro: "Não consegui consultar o consumo agora." }; }
  CONSUMO.dados = dados; CONSUMO.quando = Date.now();
  return dados;
}

// Últimos avisos enviados pela Cloudflare à conta (histórico de notificações). Mesmo token de leitura (Conta, Notificações, Leitura).
export async function avisosCloudflare(env, buscar = fetch) {
  const token = env.HEIMDALL_CF_LEITURA_TOKEN, conta = env.CLOUDFLARE_ACCOUNT_ID;
  if (!token || !conta) return { ok: false, erro: "Token de leitura não configurado na nuvem." };
  if (AVISOS.dados && Date.now() - AVISOS.quando < 300000) return AVISOS.dados;
  let dados;
  try {
    const r = await buscar(`https://api.cloudflare.com/client/v4/accounts/${conta}/alerting/v3/history?per_page=15`, { headers: { Authorization: "Bearer " + token }, signal: AbortSignal.timeout(8000) });
    if (r.status === 403) dados = { ok: false, erro: "O token de leitura não tem a permissão Notificações (leitura)." };
    else if (!r.ok) dados = { ok: false, erro: `A Cloudflare respondeu HTTP ${r.status} à consulta de avisos.` };
    else {
      const itens = ((await r.json()).result || []).map((l) => ({ quando: l.sent || "", nome: l.name || l.alert_type || "Aviso", texto: String(l.alert_body || l.description || "").slice(0, 300) }))
        .sort((a, b) => (a.quando < b.quando ? 1 : -1)).slice(0, 15);
      dados = { ok: true, itens };
    }
  } catch (e) { dados = { ok: false, erro: "Não consegui consultar os avisos agora." }; }
  AVISOS.dados = dados; AVISOS.quando = Date.now();
  return dados;
}

export function blocoAvisos(a) {
  if (!a || !a.ok) return `<h2>Avisos da Cloudflare</h2><p role="status">${esc((a && a.erro) || "Avisos indisponíveis.")}</p>`;
  if (!a.itens.length) return `<h2>Avisos da Cloudflare</h2><p role="status">Nenhum aviso nos últimos dias.</p>`;
  const linhas = a.itens.map((i) => `<tr><th scope="row">${esc(quandoTexto(i.quando) || i.quando)}</th><td>${esc(i.nome)}</td><td>${esc(i.texto)}</td></tr>`).join("");
  return `<h2>Avisos da Cloudflare</h2><table><caption>Últimos avisos enviados pela Cloudflare à conta</caption><thead><tr><th scope="col">Data</th><th scope="col">Aviso</th><th scope="col">Mensagem</th></tr></thead><tbody>${linhas}</tbody></table>`;
}

const usd = (n) => "US$ " + Number(n).toFixed(2).replace(".", ",");

export function blocoConsumo(c) {
  if (!c || !c.ok) return `<h2>Consumo do mês</h2><p role="status">${esc((c && c.erro) || "Consumo indisponível.")}</p>`;
  const linhas = c.itens.map((i) => `<tr><th scope="row">${esc(i.servico)}</th><td>${usd(i.custo)}</td></tr>`).join("");
  return `<h2>Consumo do mês</h2><p role="status">Total no mês: <strong>${usd(c.total)}</strong> de um teto de ${usd(c.teto)}${c.total >= c.teto * 0.8 ? ". Atenção: perto do teto" : ""}.</p>`
    + (linhas ? `<table><caption>Consumo faturável do mês por serviço</caption><thead><tr><th scope="col">Serviço</th><th scope="col">Valor</th></tr></thead><tbody>${linhas}</tbody></table>` : "<p>Nenhum consumo faturável até agora.</p>");
}

export function paginaPainel(estado, macNoAr, consumo, avisos) {
  const pausada = !!estado.pausa;
  return pagina("Nuvem do Heimdall",
    `<p role="status">Servidor principal (Mac): <strong>${macNoAr ? "no ar" : "fora do ar"}</strong>. `
    + (estado.contato ? `Último contato: ${esc(quandoTexto(estado.contato))}. ` : "Nenhum contato registrado ainda. ")
    + (estado.copia ? `Última cópia de dados lida pela nuvem: ${esc(quandoTexto(estado.copia))}.` : "A nuvem ainda não leu nenhuma cópia nesta sessão.") + `</p>`
    + `<h2>Continuidade</h2><p>Situação: <strong>${pausada ? "pausada" : "ativa"}</strong>. `
    + (pausada ? "Com a continuidade pausada, os sites só são repassados ao Mac e a nuvem não assume." : "Se o Mac cair, os sites de dados passam a ser atendidos pela nuvem, somente para leitura.") + `</p>`
    + `<form method="post" action="/continuidade/pausa"><input type="hidden" name="pausar" value="${pausada ? "0" : "1"}">`
    + `<button type="submit">${pausada ? "Retomar a continuidade" : "Pausar a continuidade"}</button></form>`
    + blocoConsumo(consumo) + blocoAvisos(avisos));
}

const dono = (env) => env.CONTAINER.get(env.CONTAINER.idFromName("principal"));
async function estadoNuvem(env) {
  try { return await dono(env).estadoNuvem(); } catch (e) { return {}; }
}

async function pausada(env) {
  if (Date.now() - pausaCache.quando < 30000) return pausaCache.valor;
  const e = await estadoNuvem(env);
  pausaCache = { quando: Date.now(), valor: !!e.pausa };
  return pausaCache.valor;
}

async function painel(request, env, macNoAr) {
  if (!(await verificarAccess(request, env, env.BUSCAR || fetch))) return pagina("Acesso negado", `<p role="alert">Esta página exige login pelo Cloudflare Access.</p>`, 403);
  const url = new URL(request.url);
  if (request.method === "POST" && url.pathname === "/continuidade/pausa") {
    const origem = request.headers.get("Origin");
    if (request.headers.get("Sec-Fetch-Site") === "cross-site" || (origem && new URL(origem).hostname !== url.hostname))
      return pagina("Pedido recusado", `<p role="alert">Origem não aceita.</p>`, 403);
    const valor = (await request.formData()).get("pausar") === "1";
    await dono(env).definirPausa(valor);
    pausaCache = { quando: Date.now(), valor };
    return Response.redirect(url.origin + "/continuidade", 303);
  }
  const buscar = env.BUSCAR || fetch;
  return paginaPainel(await estadoNuvem(env), macNoAr, await consumoMes(env, buscar), await avisosCloudflare(env, buscar));
}

export async function viaContainer(original, env, ctx) {
  const url = new URL(original.url);
  const leitura = original.method === "GET" || original.method === "HEAD";
  if (!leitura && !SEM_PROPAGAR.has(url.pathname)) return paginaSomenteLeitura();
  const id = env.CONTAINER.idFromName("principal");
  let resp;
  try {
    resp = await env.CONTAINER.get(id).fetch(original);
  } catch (e) {
    return paginaIndisponivel(String(e.message || e).slice(0, 120));
  }
  const copia = resp.headers.get("X-Heimdall-Copia") || "";
  const tipo = resp.headers.get("Content-Type") || "";
  const saida = new Response(resp.body, resp);
  saida.headers.set("X-Heimdall-Modo", "continuidade");
  saida.headers.delete("X-Heimdall-Copia");
  if (!tipo.includes("text/html")) return saida;
  return new HTMLRewriter().on("body", { element(el) { el.prepend(aviso(copia), { html: true }); } }).transform(saida);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const host = url.hostname;
    const rotas = JSON.parse(env.ROTAS || "{}");
    const fora = JSON.parse(env.FORA || "{}");   // sites que dependem do Mac: nome do site -> nome para exibir
    const eDados = !!rotas[host], eFora = !!fora[host], ePainel = !!env.PAINEL && host === env.PAINEL;
    if (env.CONTINUIDADE !== "1" || !(eDados || eFora || ePainel)) return fetch(request);   // desligado ou site que não é do Heimdall: só repassa
    if (!ePainel && (await pausada(env))) return fetch(request);   // continuidade pausada pela página de controle
    const original = request.clone();   // o corpo só pode ser lido uma vez: guarda uma cópia para o contêiner
    if (ePainel && url.pathname.startsWith("/continuidade")) {   // caminho da nuvem: sempre atendido por aqui, com o Mac no ar ou não
      let noAr = false;
      try { noAr = !FALHAS_DO_MAC.has((await fetch(new Request(url.origin + "/", { method: "HEAD" }), { signal: AbortSignal.timeout(ESPERA_MAC_MS) })).status); } catch (e) { /* fora */ }
      return painel(original, env, noAr);
    }
    if (ePainel && request.method === "POST") return fetch(request);   // o resto é do Controls do Mac
    if (!ePainel || request.method === "GET" || request.method === "HEAD") {
      if (Date.now() >= foraAte) {
        try {
          const r = await fetch(request, { signal: AbortSignal.timeout(ESPERA_MAC_MS) });
          if (!FALHAS_DO_MAC.has(r.status)) {
            if (Date.now() - contatoGravadoEm > GRAVAR_CONTATO_A_CADA_MS) {   // registra o último contato com o Mac, sem esperar
              contatoGravadoEm = Date.now();
              ctx.waitUntil((async () => { try { await env.CONTAINER.get(env.CONTAINER.idFromName("principal")).registrarContato(new Date().toISOString()); } catch (e) { /* sem registro */ } })());
            }
            return r;
          }
        } catch (e) { /* sem resposta: o Mac está fora */ }
        foraAte = Date.now() + PAUSA_SONDA_MS;
      }
    }
    if (ePainel) return painel(original, env, false);
    if (eFora) return paginaForaDoAr(fora[host], (await estadoNuvem(env)).contato, Object.keys(rotas));
    return viaContainer(original, env, ctx);
  },
};

export class Continuidade extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.env = env;
    this.pronto = null;
    this.copia = "";
  }

  // Estado guardado no Durable Object (leve: não liga o contêiner): último contato com o Mac, pausa da continuidade e data da última cópia lida.
  async registrarContato(iso) { await this.ctx.storage.put("contato", iso); }
  async definirPausa(valor) { await this.ctx.storage.put("pausa", !!valor); }
  async estadoNuvem() {
    const m = await this.ctx.storage.get(["contato", "pausa", "copia"]);
    return { contato: m.get("contato") || "", pausa: !!m.get("pausa"), copia: m.get("copia") || "" };
  }

  segredos() {
    const e = {};
    for (const nome of SEGREDOS) if (this.env[nome]) e[nome] = this.env[nome];
    e.HEIMDALL_CONTINUIDADE_MODO = "1";
    return e;
  }

  iniciar() {
    if (this.pronto) return this.pronto;   // requisições simultâneas compartilham a mesma subida
    const c = this.ctx.container;
    this.pronto = (async () => {
      if (!c.running) {
        c.start({ enableInternet: true, env: this.segredos() });   // imagem, tipo de instância e máximo vêm do wrangler.jsonc (política default)
        this.ctx.waitUntil(c.monitor().catch(() => {}).finally(() => { this.pronto = null; }));
      }
      c.setInactivityTimeout(Number(this.env.DORMIR_APOS_MS || 600000));   // dorme depois de 10 min sem uso
      for (let i = 0; i < 200; i++) {   // até cerca de 60 s
        try {
          const r = await c.getTcpPort(PORTA_SAUDE).fetch("http://container/health", { signal: AbortSignal.timeout(1000) });
          if (r.ok) {
            this.copia = r.headers.get("X-Heimdall-Copia") || "";
            if (this.copia) await this.ctx.storage.put("copia", this.copia);
            return;
          }
        } catch (e) { /* ainda subindo */ }
        await new Promise((ok) => setTimeout(ok, 300));
      }
      throw new Error("O contêiner não respondeu a tempo.");
    })();
    this.pronto.catch(() => { this.pronto = null; });
    return this.pronto;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const porta = JSON.parse(this.env.ROTAS || "{}")[url.hostname];
    if (!porta) return new Response("Site desconhecido", { status: 404 });
    await this.iniciar();
    const resp = await this.ctx.container.getTcpPort(porta).fetch(request);
    const saida = new Response(resp.body, resp);
    saida.headers.set("X-Heimdall-Copia", this.copia);
    return saida;
  }
}
