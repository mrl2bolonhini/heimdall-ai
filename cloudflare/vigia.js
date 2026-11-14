// Heimdall Vigia: Worker da Cloudflare que roda de 5 em 5 minutos (cron) e confere, de fora de casa,
// se os endereços públicos do Heimdall respondem. Avisa por e-mail só quando algo cai ou volta.
// Quando o Mac dorme ou perde a rede, o túnel cai e a Cloudflare responde 5xx (530/502): é isso que ele detecta.
//
// Ligações (bindings) na Cloudflare:
//   ESTADO       KV   guarda o último estado de cada endereço (para avisar só nas mudanças)
//   EMAIL        send_email   envia o aviso (Email Routing precisa estar ligado e o destino verificado)
//   ALERTA_PARA  texto: o e-mail que recebe o aviso (não fica no GitHub)
//   ALERTA_DE    texto: remetente no seu domínio, por exemplo vigia@heimdall-ai.tech
import { EmailMessage } from "cloudflare:email";

const ALVOS = [
  ["Chat", "https://chat.heimdall-ai.tech/health"],
  ["Automações", "https://flows.heimdall-ai.tech/healthz"],
  ["Cloud", "https://cloud.heimdall-ai.tech/saude"],
  ["Notas", "https://notes.heimdall-ai.tech/saude"],
  ["News", "https://news.heimdall-ai.tech/saude"],
  ["Saúde", "https://health.heimdall-ai.tech/saude"],
];
const FALHAS_PARA_AVISAR = 2; // duas conferências seguidas (10 min) para não avisar por um soluço

async function conferir(url) {
  try {
    const r = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(10000), headers: { "User-Agent": "heimdall-vigia" } });
    return r.status < 500 ? { ok: true, detalhe: String(r.status) } : { ok: false, detalhe: "HTTP " + r.status };
  } catch (e) {
    return { ok: false, detalhe: "sem resposta" };
  }
}

function mime(de, para, assunto, texto) {
  const id = crypto.randomUUID() + "@heimdall-ai.tech";
  const b64 = btoa(unescape(encodeURIComponent(assunto)));
  return `From: Heimdall Vigia <${de}>\r\nTo: ${para}\r\nSubject: =?UTF-8?B?${b64}?=\r\nMessage-ID: <${id}>\r\nDate: ${new Date().toUTCString()}\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n${btoa(unescape(encodeURIComponent(texto))).replace(/.{1,76}/g, "$&\r\n")}`;
}

async function avisar(env, assunto, texto) {
  const de = env.ALERTA_DE, para = env.ALERTA_PARA;
  if (!de || !para || !env.EMAIL) return;
  await env.EMAIL.send(new EmailMessage(de, para, mime(de, para, assunto, texto)));
}

async function rodar(env) {
  const antes = JSON.parse((await env.ESTADO.get("estado")) || "{}");
  const agora = {};
  const caiu = [], voltou = [];
  const resultados = await Promise.all(ALVOS.map(async ([nome, url]) => [nome, await conferir(url)]));
  for (const [nome, r] of resultados) {
    const a = antes[nome] || { falhas: 0, fora: false };
    if (r.ok) {
      if (a.fora) voltou.push(nome);
      agora[nome] = { falhas: 0, fora: false, detalhe: r.detalhe };
    } else {
      const falhas = a.falhas + 1;
      const fora = a.fora || falhas >= FALHAS_PARA_AVISAR;
      if (fora && !a.fora) caiu.push(`${nome} (${r.detalhe})`);
      agora[nome] = { falhas, fora, detalhe: r.detalhe };
    }
  }
  await env.ESTADO.put("estado", JSON.stringify(agora));
  await env.ESTADO.put("ultima", new Date().toISOString());
  if (caiu.length) await avisar(env, "Heimdall: fora do ar", "Não responderam: " + caiu.join(", ") + ".\nSe forem todos, o Mac provavelmente está dormindo, sem rede ou com o túnel parado.\nNo Mac: ./subir.sh --status");
  if (voltou.length) await avisar(env, "Heimdall: voltou", "Voltaram a responder: " + voltou.join(", ") + ".");
  return agora;
}

export default {
  async scheduled(evento, env, ctx) { ctx.waitUntil(rodar(env)); },
  // Abrir o endereço do Worker mostra só o último estado (sem dados sensíveis); ?avisar=teste não existe de propósito.
  async fetch(req, env) {
    const estado = JSON.parse((await env.ESTADO.get("estado")) || "{}");
    const linhas = Object.entries(estado).map(([n, e]) => `${n}: ${e.fora ? "FORA" : "ok"} (${e.detalhe})`);
    return new Response(`Heimdall Vigia\nÚltima conferência: ${(await env.ESTADO.get("ultima")) || "nunca"}\n${linhas.join("\n")}\n`, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
  },
};
