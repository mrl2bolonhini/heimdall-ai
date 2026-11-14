// Heimdall Saúde Caixa: Worker da Cloudflare que fica na frente do webhook de saúde do n8n
// (flows.heimdall-ai.tech/webhook/heimdall-saude), o endereço que o Health Auto Export já usa. Nada muda no app.
//
//   Mac no ar        -> repassa o envio ao n8n do jeito que veio e devolve a resposta dele.
//   Mac fora do ar   -> guarda o envio no KV (7 dias, até 200 envios) e responde 202 ao app, que o considera entregue.
//   Cron, 5 em 5 min -> reenvia ao n8n o que ficou guardado e apaga cada item que o n8n aceitou.
//
// Ligações: FILA (KV). Opcional: TOKEN_SAUDE (segredo): se existir, só guarda envios cujo cabeçalho
// X-Heimdall-Saude (ou Authorization) for igual a ele, para ninguém encher a fila com lixo.
const ORIGEM = "https://flows.heimdall-ai.tech/webhook/heimdall-saude";
const MAX_ITENS = 200, MAX_BYTES = 8 * 1024 * 1024, TTL = 7 * 24 * 3600, POR_RODADA = 20;
const CABECALHOS = ["content-type", "x-heimdall-saude", "authorization"];

function origemFora(status) { return status >= 500; }

async function enviarAoN8n(headers, corpo) {
  const h = new Headers(headers);
  h.set("X-Heimdall-Reenvio", "1");
  return fetch(ORIGEM, { method: "POST", headers: h, body: corpo, signal: AbortSignal.timeout(20000) });
}

function tokenConfere(req, env) {
  if (!env.TOKEN_SAUDE) return true;
  const t = (req.headers.get("x-heimdall-saude") || req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim();
  return t.length > 0 && t === env.TOKEN_SAUDE;
}

async function guardar(env, req, corpo) {
  const lista = await env.FILA.list({ prefix: "fila:", limit: MAX_ITENS + 1 });
  if (lista.keys.length >= MAX_ITENS) return false;
  const h = {};
  for (const n of CABECALHOS) if (req.headers.get(n)) h[n] = req.headers.get(n);
  const chave = `fila:${Date.now().toString().padStart(14, "0")}:${crypto.randomUUID().slice(0, 8)}`;
  await env.FILA.put(chave, JSON.stringify({ h, b: corpo }), { expirationTtl: TTL });
  return true;
}

async function esvaziar(env) {
  const lista = await env.FILA.list({ prefix: "fila:", limit: POR_RODADA });
  let enviados = 0;
  for (const k of lista.keys) {
    const bruto = await env.FILA.get(k.name);
    if (!bruto) continue;
    let item;
    try { item = JSON.parse(bruto); } catch { await env.FILA.delete(k.name); continue; }
    try {
      const r = await enviarAoN8n(item.h, item.b);
      if (origemFora(r.status)) break; // o Mac continua fora: tenta de novo na próxima rodada
      await env.FILA.delete(k.name);
      enviados++;
    } catch { break; }
  }
  return enviados;
}

export default {
  async fetch(req, env) {
    if (req.method !== "POST" || req.headers.get("x-heimdall-reenvio")) return fetch(req); // reenvios e outros métodos passam direto
    let corpo = null;
    const tam = Number(req.headers.get("content-length") || 0);
    const clone = req.clone();
    try {
      const r = await fetch(req);
      if (!origemFora(r.status)) return r;
    } catch { /* origem fora: guarda abaixo */ }
    if (tam > MAX_BYTES || !tokenConfere(req, env)) return new Response("origem fora do ar", { status: 503 });
    corpo = await clone.text();
    if (corpo.length > MAX_BYTES) return new Response("origem fora do ar", { status: 503 });
    const ok = await guardar(env, req, corpo);
    return ok
      ? new Response(JSON.stringify({ enfileirado: true }), { status: 202, headers: { "Content-Type": "application/json" } })
      : new Response("fila cheia", { status: 503 });
  },
  async scheduled(evento, env, ctx) { ctx.waitUntil(esvaziar(env)); },
};
export { esvaziar, guardar };
