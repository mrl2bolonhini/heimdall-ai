#!/usr/bin/env python3
"""Teste da Ajuda e suporte do StudioLibre (heimdall_ajuda.py e as rotas do Account): perguntas frequentes de todos os serviços, formulário com protocolo, limite por hora,
validação, envio pelo Cloudflare Email Sending (simulado, sem rede), CSRF e origem, páginas de política com aviso de minuta, e os links do rodapé de todos os serviços."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import json
import re
import tempfile
import threading
import urllib.parse
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

import heimdall_account as a
import heimdall_ajuda as aj
import heimdall_cfaccess as cfa
import heimdall_conta as c
import heimdall_design as design
import heimdall_integracoes as integ
import heimdall_usuarios as u

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {extra}"))
    falhas += 0 if ok else 1


# ---- ambiente isolado ----
tmp = _Path(tempfile.mkdtemp())
aj.PASTA = tmp / "suporte"
aj._env_arquivo = lambda chave: ""
for k in ("STUDIO_SUPORTE_EMAIL", "STUDIO_SUPORTE_DE", "STUDIO_SUPORTE_PARA", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "STUDIO_POLITICA_APROVADA"):
    aj.os.environ.pop(k, None)

# ---- conteúdo ----
chaves = [k for k in aj.SERVICOS if k != "geral"]
confere("há perguntas frequentes gerais e de todos os serviços com página própria", aj.FAQ.get("geral") and all(aj.FAQ.get(k) for k in ("account", "controls", "finance", "saude", "news", "learn", "jogos", "lab", "chat")))
confere("cada pergunta tem resposta e nada de gíria ou tom pessoal nas respostas", all(q.strip() and r.strip() and not re.search(r"\b(cara|mano|beleza|tá|né|pra)\b", r.lower()) for itens in aj.FAQ.values() for q, r in itens))
titulo, corpo = aj.pagina_ajuda("tok", "finance")
confere("ajuda: um só h1, FAQ do serviço antes do geral e formulário no fim", corpo.count("<h1>") == 1 and corpo.index("Perguntas frequentes: Finance") < corpo.index("Perguntas frequentes: Geral") < corpo.index("Falar com o suporte"))
confere("ajuda: campos com label e botão de envio", all(f'for="{i}"' in corpo for i in ("s-servico", "s-assunto", "s-msg")) and 'type="submit"' in corpo and 'name="csrf" value="tok"' in corpo)
confere("ajuda: serviço desconhecido volta ao geral, sem erro", "Perguntas frequentes: Geral" in aj.pagina_ajuda("tok", "<script>")[1] and "<script>" not in aj.pagina_ajuda("tok", "<script>")[1])
confere("termos de uso e de privacidade: um só h1, índice, aviso de minuta e, sem dados no .env, o marcador do responsável", all(x[1].count("<h1>") == 1 and "Minuta em revisão" in x[1] and 'aria-label="Conteúdo desta página"' in x[1] and "Em vigor desde 24 de novembro de 2026" in x[1] for x in (aj.pagina_termos_de_uso(), aj.pagina_privacidade())) and "[NOME E DOCUMENTO DO RESPONSÁVEL" in aj.pagina_termos_de_uso()[1])
aj.os.environ.update({"STUDIO_RESPONSAVEL": "Fulano de Tal, CPF/MF nº 000.000.000-00", "STUDIO_FORO": "Campinas"})
confere("com os dados no .env: o responsável e o foro aparecem nos dois documentos, e o encarregado padrão é o suporte", "Fulano de Tal, CPF/MF nº 000.000.000-00" in aj.pagina_termos_de_uso()[1] and "foro de Campinas" in aj.pagina_termos_de_uso()[1] and "Fulano de Tal" in aj.pagina_privacidade()[1] and "suporte@studiolibre.io" in aj.pagina_privacidade()[1])
confere("nenhum documento deixa marcador entre colchetes quando os dados estão definidos", "[" not in aj.texto_documento("termos") and "[" not in aj.texto_documento("privacidade"))
confere("texto puro: título, vigência, índice e seções numeradas", aj.texto_documento("termos").startswith("TERMOS DE USO DO HEIMDALL") and "Conteúdo" in aj.texto_documento("termos") and "13. Lei aplicável e foro" in aj.texto_documento("termos") and "POLÍTICA DE PRIVACIDADE" in aj.texto_documento("privacidade"))
for k in ("STUDIO_RESPONSAVEL", "STUDIO_FORO"):
    aj.os.environ.pop(k, None)
confere("privacidade: cita os operadores reais (Cloudflare, Microsoft, Pluggy, Apple, Bark, Notion) e os direitos da LGPD", all(x in aj.pagina_privacidade()[1] for x in ("Cloudflare", "Microsoft", "Pluggy", "Apple", "Bark", "Notion", "art. 18")))
aj.os.environ["STUDIO_POLITICA_APROVADA"] = "1"
confere("STUDIO_POLITICA_APROVADA=1 tira o aviso de minuta", "Minuta em revisão" not in aj.pagina_privacidade()[1])
aj.os.environ.pop("STUDIO_POLITICA_APROVADA")

# ---- validação e registro ----
P = {"email": "ana@x.com", "nome": "Ana"}
def erro_de(*args):
    try:
        aj.validar(*args)
    except aj.ErroSuporte as e:
        return str(e)
    return ""
confere("validação: assunto, serviço e tamanho da mensagem", "assunto" in erro_de("x", "finance", "uma mensagem longa") and "serviço" in erro_de("duvida", "x", "uma mensagem longa") and "pelo menos" in erro_de("duvida", "finance", "curta") and "no máximo" in erro_de("duvida", "finance", "a" * 4001))
confere("limpeza: tira caracteres de controle e espaços repetidos", aj._limpar("a\x00b   c\r\nd") == "ab c\nd")
agora = datetime(2026, 11, 24, 12, 0, 0)
r = aj.registrar(P, "duvida", "finance", "Como conecto minha conta?", agora)
confere("registro: protocolo no formato HMD-AAAAMMDD-XXXXXX, estado recebida e arquivo com permissão 600", re.fullmatch(r"HMD-20261124-[0-9A-F]{6}", r["protocolo"]) and r["estado"] == "recebida" and ((aj.PASTA / "mensagens.jsonl").stat().st_mode & 0o777) == 0o600)
for i in range(aj.LIMITE_POR_HORA - 1):
    aj.registrar(P, "duvida", "finance", f"mensagem número {i} para o limite", agora + timedelta(minutes=i))
try:
    aj.registrar(P, "duvida", "finance", "mensagem acima do limite", agora + timedelta(minutes=10))
    limite = False
except aj.ErroSuporte as e:
    limite = "última hora" in str(e)
confere("limite de mensagens por hora por pessoa", limite)
outra = aj.registrar({"email": "bia@x.com"}, "outro", "geral", "mensagem de outra pessoa", agora + timedelta(minutes=10))
confere("o limite é por pessoa, e passada 1 hora a pessoa volta a enviar", outra["email"] == "bia@x.com" and aj.registrar(P, "duvida", "finance", "uma hora depois do primeiro", agora + timedelta(minutes=70)))

# ---- envio por e-mail (simulado) ----
confere("sem configuração, o envio por e-mail fica desligado e a mensagem continua gravada", not aj.envio_configurado() and aj.enviar_email(r) is False)
aj.os.environ.update({"STUDIO_SUPORTE_EMAIL": "1", "STUDIO_SUPORTE_DE": "no-reply@studiolibre.io", "CLOUDFLARE_API_TOKEN": "tk", "CLOUDFLARE_ACCOUNT_ID": "acc"})
chamadas = []


class Resp:
    def __init__(self, ok): self.ok = ok
    def __enter__(self): return self
    def __exit__(self, *x): return False
    def read(self): return json.dumps({"success": self.ok, "result": {"message_id": "m"}}).encode()


def falso(req, timeout):
    chamadas.append((req.full_url, req.get_method(), req.headers, json.loads(req.data)))
    return Resp(True)


aj._post = falso
r2 = aj.registrar({"email": "caio@x.com", "nome": "Caio"}, "problema", "saude", "O painel de saúde não carrega.", agora)
confere("envio: POST no endereço do Email Sending, com o token e o protocolo no assunto", aj.envio_configurado() and aj.enviar_email(r2) is True and chamadas[0][0] == "https://api.cloudflare.com/client/v4/accounts/acc/email/sending/send"
        and chamadas[0][1] == "POST" and chamadas[0][2].get("Authorization") == "Bearer tk" and r2["protocolo"] in chamadas[0][3]["subject"] and chamadas[0][3]["to"] == "suporte@studiolibre.io")
confere("envio: o texto leva quem escreveu, o serviço e a mensagem", "caio@x.com" in chamadas[0][3]["text"] and "Health" in chamadas[0][3]["text"] and "O painel de saúde não carrega." in chamadas[0][3]["text"])
confere("envio aceito: o estado do registro vira enviada", [x for x in aj._ler_registros() if x["protocolo"] == r2["protocolo"]][0]["estado"] == "enviada")


def quebra(req, timeout):
    raise OSError("sem rede")


aj._post = quebra
r3 = aj.registrar({"email": "dora@x.com"}, "duvida", "geral", "Teste com falha de envio.", agora)
confere("falha na Cloudflare: não levanta erro e o estado vira gravada_sem_envio", aj.enviar_email(r3) is False and [x for x in aj._ler_registros() if x["protocolo"] == r3["protocolo"]][0]["estado"] == "gravada_sem_envio")
confere("confirmação: com e sem envio, sempre traz o protocolo; sem envio indica o e-mail de suporte", r3["protocolo"] in aj.mensagem_de_confirmacao(r3, False) and "suporte@studiolibre.io" in aj.mensagem_de_confirmacao(r3, False) and "enviada ao suporte" in aj.mensagem_de_confirmacao(r3, True))
for k in ("STUDIO_SUPORTE_EMAIL", "STUDIO_SUPORTE_DE", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
    aj.os.environ.pop(k, None)

# ---- rotas do Account ----
cfa.email_validado = lambda jwt: {"tokdono": "dono@x.com", "tokana": "ana@x.com"}.get(jwt)
cfa.config = lambda: {"equipe": "eq", "auds": {"a"}, "donos": {"dono@x.com"}, "convidados": {}}
u.situacao = lambda: {"donos": ["dono@x.com"], "convidados": {"ana@x.com": ["jogos", "news"]}}
c._buscar_identidade = lambda eq, jwt: {"name": {"tokdono": "Murillo", "tokana": "Ana Souza"}[jwt]}
srv = ThreadingHTTPServer(("127.0.0.1", 0), a.Account)
threading.Thread(target=srv.serve_forever, daemon=True).start()
porta = srv.server_address[1]
HOST = "account.studiolibre.io"


def pedir(caminho, jwt=None, origem=None, metodo="GET", corpo=None, host=HOST):
    h = {"Host": host}
    if corpo is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded"
    if jwt:
        h[cfa.CABECALHO] = jwt
    if origem:
        h["Origin"] = origem
    k = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    k.request(metodo, caminho, body=corpo, headers=h)
    r = k.getresponse()
    b = r.read().decode("utf-8", "replace")
    k.close()
    return r.status, b


for caminho in ("/ajuda", "/termos-de-uso", "/politica-de-privacidade"):
    s, b = pedir(caminho)
    confere(f"{caminho} sem Access: 403", s == 403)
    s, b = pedir(caminho, jwt="tokana")
    confere(f"{caminho} para convidado: 200, lang pt-BR, um só h1, pular para o conteúdo e sem script", s == 200 and 'lang="pt-BR"' in b and b.count("<h1>") == 1 and 'class="pular"' in b and "<script" not in b)
s, b = pedir("/ajuda?servico=finance", jwt="tokdono")
confere("/ajuda?servico=finance abre com as perguntas do Finance primeiro", s == 200 and "Ajuda e suporte do Finance" in b and b.index("Perguntas frequentes: Finance") < b.index("Perguntas frequentes: Geral"))
confere("o menu do Account tem o link Ajuda e suporte", 'href="/ajuda"' in b)

tok = integ.csrf({"email": "ana@x.com"})
corpo = urllib.parse.urlencode({"csrf": tok, "servico": "news", "assunto": "duvida", "mensagem": "Como assino o feed no iPhone?"})
origem = "https://" + HOST
s, b = pedir("/suporte", jwt="tokana", origem=origem, metodo="POST", corpo=corpo)
m = re.search(r"protocolo é (HMD-\d{8}-[0-9A-F]{6})", b)
confere("POST /suporte: 200, protocolo na confirmação (role=status) e a mensagem gravada com o e-mail de quem entrou", s == 200 and m and 'role="status"' in b and any(x["protocolo"] == m.group(1) and x["email"] == "ana@x.com" and x["servico"] == "news" for x in aj._ler_registros()), b[:300])
s, b = pedir("/suporte", jwt="tokana", origem=origem, metodo="POST", corpo=corpo.replace(tok, "errado"))
confere("POST /suporte com csrf errado: 403", s == 403)
s, b = pedir("/suporte", jwt="tokana", origem="https://outro.exemplo", metodo="POST", corpo=corpo)
confere("POST /suporte com origem de outro site: 403", s == 403)
s, b = pedir("/suporte", origem=origem, metodo="POST", corpo=corpo)
confere("POST /suporte sem Access: 403", s == 403)
s, b = pedir("/suporte", jwt="tokana", origem=origem, metodo="POST", corpo=urllib.parse.urlencode({"csrf": tok, "servico": "news", "assunto": "duvida", "mensagem": "curta"}))
confere("POST /suporte com mensagem curta: 400, role=alert e o texto digitado volta no campo", s == 400 and 'role="alert"' in b and ">curta</textarea>" in b)
s, b = pedir("/suporte", jwt="tokana", origem=origem, metodo="POST", corpo="x" * 20000)
confere("POST /suporte grande demais: 413", s == 413)
s, b = pedir("/suporte", jwt="tokana", origem=origem, metodo="POST", corpo=urllib.parse.urlencode({"csrf": tok, "servico": "news", "assunto": "duvida", "mensagem": "<script>alert(1)</script> teste"}))
confere("mensagem com HTML é gravada como texto (sem executar) e a confirmação não a repete", s == 200 and "<script>alert" not in b)

# ---- resposta de suporte@ (CLI e Account) ----
for k, v in (("STUDIO_SUPORTE_EMAIL", "1"), ("STUDIO_SUPORTE_DE", "suporte@studiolibre.io"), ("CLOUDFLARE_API_TOKEN", "tk"), ("CLOUDFLARE_ACCOUNT_ID", "acc")):
    aj.os.environ[k] = v
chamadas.clear()
aj._post = falso
rr = aj.registrar({"email": "eva@x.com", "nome": "Eva"}, "duvida", "finance", "Como conecto o banco?", agora)
aj.enviar_email(rr)
confere("mensagem do formulário leva o e-mail de quem escreveu como reply_to", chamadas[-1][3].get("reply_to") == "eva@x.com")
ok, msg = aj.responder(rr["protocolo"], "Olá Eva, abra Finance e use Conectar banco.")
env = chamadas[-1][3]
confere("responder: envia de suporte@ para quem escreveu, com Re: e protocolo no assunto e reply_to do suporte", ok and env["to"] == "eva@x.com" and env["from"] == "suporte@studiolibre.io" and env["subject"].startswith("Re: [" + rr["protocolo"] + "]") and env["reply_to"] == "suporte@studiolibre.io" and "Conectar banco" in env["text"])
reg_r = [x for x in aj._ler_registros() if x["protocolo"] == rr["protocolo"]][0]
confere("responder: o registro vira respondida e guarda o texto", reg_r["estado"] == "respondida" and reg_r["respostas"][0]["texto"].startswith("Olá Eva"))
confere("responder sem protocolo exige endereço válido", aj.responder("", "texto", "")[0] is False and aj.responder("", "texto", "fulano@x.com")[0] is True and chamadas[-1][3]["to"] == "fulano@x.com")
confere("responder com texto vazio é recusado", aj.responder(rr["protocolo"], " ")[0] is False)
n_antes = len(chamadas)


def recusa_reply(req, timeout):
    import urllib.error as ue
    d = json.loads(req.data)
    chamadas.append((req.full_url, req.get_method(), req.headers, d))
    if "reply_to" in d:
        raise ue.HTTPError(req.full_url, 400, "x", {}, __import__("io").BytesIO(b'{"success":false}'))
    return Resp(True)


aj._post = recusa_reply
rs = aj.registrar({"email": "gil@x.com"}, "duvida", "geral", "Mensagem com reply_to recusado.", agora)
confere("se a Cloudflare recusar o reply_to, o envio tenta de novo sem ele", aj.enviar_email(rs) is True and "reply_to" not in chamadas[-1][3] and len(chamadas) == n_antes + 2)
aj._post = falso

dono_tok = cfa.CABECALHO
s, b = pedir("/suporte/mensagens", jwt="tokana")
confere("GET /suporte/mensagens por convidado: 404, como se a página não existisse", s == 404)
s, b = pedir("/suporte/mensagens", jwt="tokdono")
confere("GET /suporte/mensagens pelo dono: 200, lista com protocolo, e-mail, formulário de resposta e texto escapado", s == 200 and rr["protocolo"] in b and "eva@x.com" in b and 'action="/suporte/responder"' in b and "<script>alert" not in b and "<h1>" in b)
s, b = pedir("/ajuda", jwt="tokdono")
confere("Ajuda do dono traz o link para as mensagens; a do convidado não", s == 200 and "/suporte/mensagens" in b and "/suporte/mensagens" not in pedir("/ajuda", jwt="tokana")[1])
tok_d = re.search(r'name="csrf" value="([^"]+)"', pedir("/suporte/mensagens", jwt="tokdono")[1]).group(1)
origem_d = "https://" + HOST
corpo_r = urllib.parse.urlencode({"csrf": tok_d, "protocolo": rs["protocolo"], "texto": "Resposta pelo Account."})
chamadas.clear()
s, b = pedir("/suporte/responder", jwt="tokdono", origem=origem_d, metodo="POST", corpo=corpo_r)
confere("POST /suporte/responder pelo dono: 200, aviso role=status e envio para quem escreveu", s == 200 and 'role="status"' in b and chamadas and chamadas[-1][3]["to"] == "gil@x.com", b[:200])
s, b = pedir("/suporte/responder", jwt="tokana", origem=origem_d, metodo="POST", corpo=corpo_r)
confere("POST /suporte/responder por convidado: 404, sem enviar nada", s == 404)
s, b = pedir("/suporte/responder", jwt="tokdono", origem=origem_d, metodo="POST", corpo=corpo_r.replace(tok_d, "errado"))
confere("POST /suporte/responder com csrf errado: 403", s == 403)
s, b = pedir("/suporte/responder", jwt="tokdono", origem="https://outro.exemplo", metodo="POST", corpo=corpo_r)
confere("POST /suporte/responder com origem de outro site: 403", s == 403)
for k in ("STUDIO_SUPORTE_EMAIL", "STUDIO_SUPORTE_DE", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
    aj.os.environ.pop(k, None)

# ---- rodapé de todos os serviços ----
r = design.rodape(servico="finance")
confere("rodapé: Ajuda e suporte (com o serviço), Termos de Uso e Privacidade, antes do Voltar para o topo", "/ajuda?servico=finance" in r and "/termos-de-uso" in r and "/politica-de-privacidade" in r and r.index("Privacidade") < r.index("Voltar para o topo") and 'aria-label="Ajuda e informações"' in r)
fontes = {"controls": "heimdall_controls.py", "finance": "heimdall_finance.py", "saude": "heimdall_painel_saude.py", "memory": "heimdall_servico_web.py", "news": "heimdall_news.py",
          "learn": "heimdall_learn.py", "jogos": "heimdall_jogos.py", "lab": "heimdall_lab.py", "account": "heimdall_account.py"}
confere("todos os serviços com página própria passam a chave do serviço ao rodapé", all(f'design.rodape(' in (RAIZ / f).read_text(encoding="utf-8") and (f'"{k}"' in (RAIZ / f).read_text(encoding="utf-8")) for k, f in fontes.items()))
confere("as chaves do rodapé existem na ajuda", all(k in aj.SERVICOS for k in fontes))

import re as _re
_t, _c = aj.pagina_ajuda("tok")
confere("Atalhos e dispositivos na Ajuda: iPhone e Android, sem tabela de comandos de terminal", all(x in _c for x in ("iPhone e Android", "Atalhos e dispositivos")) and "Comandos do Health" not in _c)
_corpo_faq = " ".join(t + " " + r for v in aj.FAQ.values() for t, r in v)
confere("a Ajuda do produto não traz comandos do dono (terminal, .env, python3, porta, studio)", not _re.search(r"\bstudio [a-z]+ --|python3 |\.env|\bheimdall [a-z]+|localhost|docker |brew |pip ", _c + " " + _corpo_faq), "")
confere("atalhos de teclado: tabela com caption e scope, com a forma do macOS e a do Windows e Linux em cada linha",
        'id="atalhos"' in _c and "<caption>Atalhos de teclado por sistema" in _c and 'Windows e Linux</th>' in _c and len(aj.ATALHOS) >= 10 and all(a and m and w for a, m, w in aj.ATALHOS))
confere("atalhos: a forma do Windows e Linux é a do macOS com Option por Alt e Control por Ctrl (nada mais muda)",
        all(m.replace("Option", "Alt").replace("Control", "Ctrl") == w for _a2, m, w in aj.ATALHOS), [w for _a2, m, w in aj.ATALHOS if m.replace("Option", "Alt").replace("Control", "Ctrl") != w])
confere("atalhos: o menu Mais tem um só atalho (5), sem o 0 antigo", sum("menu Mais" in a for a, _m, _w in aj.ATALHOS) == 1 and "Option+Shift+0" not in _c and "Alt+Shift+0" not in _c)
print("\nFALHAS:", falhas)
raise SystemExit(1 if falhas else 0)
