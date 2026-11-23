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
  "HEIMDALL_CFACCESS_EQUIPE", "HEIMDALL_CFACCESS_CONVIDADOS", "HEIMDALL_CFACCESS_TEAM"];
const PORTA_SAUDE = 8080;

let foraAte = 0;   // por isolate: até quando pular a sonda ao Mac

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
    const rotas = JSON.parse(env.ROTAS || "{}");
    if (env.CONTINUIDADE !== "1" || !rotas[url.hostname]) return fetch(request);   // desligado ou site que não é do Heimdall: só repassa
    const original = request.clone();   // o corpo só pode ser lido uma vez: guarda uma cópia para o contêiner
    if (Date.now() >= foraAte) {
      try {
        const r = await fetch(request, { signal: AbortSignal.timeout(ESPERA_MAC_MS) });
        if (!FALHAS_DO_MAC.has(r.status)) return r;
      } catch (e) { /* sem resposta: o Mac está fora */ }
      foraAte = Date.now() + PAUSA_SONDA_MS;
    }
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
          if (r.ok) { this.copia = r.headers.get("X-Heimdall-Copia") || ""; return; }
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
