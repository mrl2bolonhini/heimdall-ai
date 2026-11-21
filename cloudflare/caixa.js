// Heimdall: caixa de correio na Cloudflare (Worker "heimdall-caixa").
// O celular de cada pessoa deixa itens (saúde, notas...) na ENTRADA; o Mac do dono busca, processa e apaga.
// O Mac deixa na SAÍDA o que o celular deve aplicar (lembretes e eventos); o celular busca e confirma, e o item some.
// Nada fica guardado além do trânsito: o R2 apaga sozinho o que sobrar depois de 7 dias (regra do bucket).
// Cada pessoa tem um token; só o hash dele fica no KV. Papéis: "dono" (o Mac) e "telefone" (uma pessoa, só a própria caixa).
// Bindings: CAIXA (R2), TOKENS (KV), CONTA_ID (variável de texto). Não é criptografia de ponta a ponta: a Cloudflare consegue ler o que está na caixa.

const TIPOS = new Set(["saude", "nota", "evento", "lembrete", "outro"]);
const MAX_CORPO = 5 * 1024 * 1024;
const COTA_BYTES_DIA = 50 * 1024 * 1024;
const COTA_DIA = 500;
const USUARIO = /^[a-z0-9-]{1,32}$/;
const ID = /^[0-9]{13}-[0-9a-f]{12}$/;

const resp = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
const erro = (status, msg) => resp({ erro: msg }, status);
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const sha256 = async (s) => hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
const aleatorio = (n) => hex(crypto.getRandomValues(new Uint8Array(n)));
const novoId = () => String(Date.now()).padStart(13, "0") + "-" + aleatorio(6);

async function autenticar(req, env) {
  const m = /^Bearer\s+([A-Za-z0-9_-]{20,200})$/.exec(req.headers.get("authorization") || "");
  if (!m) return null;
  const reg = await env.TOKENS.get("tok:" + (await sha256(m[1])));
  return reg ? JSON.parse(reg) : null;
}

async function criarToken(env, usuario, papel) {
  const token = "hc_" + aleatorio(24);
  const h = await sha256(token);
  await env.TOKENS.put("tok:" + h, JSON.stringify({ usuario, papel }));
  const lista = JSON.parse((await env.TOKENS.get("usr:" + usuario)) || "[]");
  lista.push(h);
  await env.TOKENS.put("usr:" + usuario, JSON.stringify(lista));
  return token;
}

async function revogar(env, usuario) {
  const lista = JSON.parse((await env.TOKENS.get("usr:" + usuario)) || "[]");
  for (const h of lista) await env.TOKENS.delete("tok:" + h);
  await env.TOKENS.delete("usr:" + usuario);
  return lista.length;
}

async function lerCorpo(req) {
  const declarado = Number(req.headers.get("content-length") || 0);
  if (declarado > MAX_CORPO) return { erro: 413 };
  const texto = await req.text();
  if (texto.length > MAX_CORPO) return { erro: 413 };
  try { return { json: JSON.parse(texto) }; } catch { return { erro: 400 }; }
}

async function listar(env, prefixo, limite = 50) {
  const l = await env.CAIXA.list({ prefix: prefixo, limit: limite });
  const itens = [];
  for (const o of l.objects) {
    const obj = await env.CAIXA.get(o.key);
    if (!obj) continue;
    const id = o.key.slice(o.key.lastIndexOf("/") + 1, -5);
    itens.push({ id, ...JSON.parse(await obj.text()) });
  }
  return itens;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const rota = url.pathname.replace(/\/+$/, "");
    const m = req.method;

    // Primeiro acesso ou troca do token do dono: quem prova ter acesso à conta da Cloudflare (com um token da própria conta) recebe um token novo.
    if (m === "POST" && rota === "/v1/iniciar") {
      const cf = req.headers.get("x-cf-token") || "";
      if (!cf) return erro(401, "não autorizado");
      let ok = false;
      try {
        const r = await fetch(`https://api.cloudflare.com/client/v4/accounts/${env.CONTA_ID}/ai-gateway/gateways`, { headers: { authorization: "Bearer " + cf, "user-agent": "heimdall-caixa/1.0" } });
        ok = r.status === 200;
      } catch { ok = false; }
      if (!ok) return erro(401, "não autorizado");
      await revogar(env, "dono");
      return resp({ token: await criarToken(env, "dono", "dono") });
    }

    const quem = await autenticar(req, env);
    if (!quem) return erro(401, "não autorizado");
    const dono = quem.papel === "dono";

    if (m === "POST" && rota === "/v1/tokens") {
      if (!dono) return erro(403, "só o dono");
      const c = await lerCorpo(req);
      if (c.erro) return erro(c.erro, "pedido inválido");
      const { usuario } = c.json || {};
      if (!USUARIO.test(usuario || "") || usuario === "dono") return erro(400, "nome de usuário inválido (a-z, 0-9 e hífen, até 32)");
      return resp({ usuario, token: await criarToken(env, usuario, "telefone") });
    }
    const rt = /^\/v1\/tokens\/([a-z0-9-]{1,32})$/.exec(rota);
    if (m === "DELETE" && rt) {
      if (!dono) return erro(403, "só o dono");
      if (rt[1] === "dono") return erro(400, "nome inválido");
      return resp({ revogados: await revogar(env, rt[1]) });
    }

    if (m === "POST" && rota === "/v1/enviar") {
      const c = await lerCorpo(req);
      if (c.erro) return erro(c.erro, c.erro === 413 ? "grande demais" : "JSON inválido");
      const { tipo, dados } = c.json || {};
      if (!TIPOS.has(tipo) || dados === undefined) return erro(400, "tipo ou dados inválidos");
      const usuario = dono ? (c.json.usuario || "dono") : quem.usuario;
      if (!USUARIO.test(usuario)) return erro(400, "usuário inválido");
      const chaveCota = `cota:${usuario}:${new Date().toISOString().slice(0, 10)}`;
      const [usados, bytes] = ((await env.TOKENS.get(chaveCota)) || "0:0").split(":").map(Number);
      const tamanho = JSON.stringify(c.json).length;
      if (usados >= COTA_DIA || bytes + tamanho > COTA_BYTES_DIA) return erro(429, "limite diário de envios");
      await env.TOKENS.put(chaveCota, `${usados + 1}:${bytes + tamanho}`, { expirationTtl: 172800 });
      const id = novoId();
      await env.CAIXA.put(`u/${usuario}/entrada/${id}.json`, JSON.stringify({ tipo, dados, recebido: new Date().toISOString() }));
      return resp({ id });
    }

    if (m === "GET" && rota === "/v1/entrada") {
      if (!dono) return erro(403, "só o dono");
      const us = url.searchParams.get("usuario");
      if (us && !USUARIO.test(us)) return erro(400, "usuário inválido");
      if (us) return resp({ itens: (await listar(env, `u/${us}/entrada/`)).map((i) => ({ usuario: us, ...i })) });
      const pastas = await env.CAIXA.list({ prefix: "u/", delimiter: "/" });
      const todos = [];
      for (const p of pastas.delimitedPrefixes || []) {
        const u = p.split("/")[1];
        for (const i of await listar(env, `u/${u}/entrada/`)) todos.push({ usuario: u, ...i });
      }
      return resp({ itens: todos });
    }
    const re = /^\/v1\/entrada\/([a-z0-9-]{1,32})\/([0-9]{13}-[0-9a-f]{12})$/.exec(rota);
    if (m === "DELETE" && re) {
      if (!dono) return erro(403, "só o dono");
      await env.CAIXA.delete(`u/${re[1]}/entrada/${re[2]}.json`);
      return resp({ apagado: true });
    }

    if (m === "POST" && rota === "/v1/saida") {
      if (!dono) return erro(403, "só o dono");
      const c = await lerCorpo(req);
      if (c.erro) return erro(c.erro, "pedido inválido");
      const { usuario, tipo, dados } = c.json || {};
      if (!USUARIO.test(usuario || "") || !TIPOS.has(tipo) || dados === undefined) return erro(400, "usuário, tipo ou dados inválidos");
      const id = novoId();
      await env.CAIXA.put(`u/${usuario}/saida/${id}.json`, JSON.stringify({ tipo, dados, criado: new Date().toISOString() }));
      return resp({ id });
    }
    if (m === "GET" && rota === "/v1/saida") {
      const us = dono ? url.searchParams.get("usuario") : quem.usuario;
      if (!us || !USUARIO.test(us)) return erro(400, "informe o usuário");
      return resp({ itens: await listar(env, `u/${us}/saida/`) });
    }
    const rs = /^\/v1\/saida\/([0-9]{13}-[0-9a-f]{12})$/.exec(rota);
    if (m === "DELETE" && rs) {
      const us = dono ? url.searchParams.get("usuario") : quem.usuario;
      if (!us || !USUARIO.test(us)) return erro(400, "informe o usuário");
      await env.CAIXA.delete(`u/${us}/saida/${rs[1]}.json`);
      return resp({ apagado: true });
    }

    return erro(404, "não encontrado");
  },
};
