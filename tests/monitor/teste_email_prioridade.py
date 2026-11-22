#!/usr/bin/env python3
"""Testa o rebaixamento de e-mails oficiais de serviços sem interesse (Serasa, SPC...) na triagem e no agendamento."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
from pathlib import Path
sys.path.insert(0, str(RAIZ))
import heimdall_email_oficial as eo  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:400])


def item(classe="oficial", servico="Serasa/SPC", dominio="serasa.com.br", urg="alta", mid="m1"):
    return {"classe": classe, "servico": servico, "dominio": dominio, "de": f"avisos@{dominio}", "assunto": "Seu boleto está disponível", "urg": urg, "mid": mid,
            "prazo": "", "motivo": "", "data": "2026-11-18"}


criados = []
eo.post_json = lambda url, dado, cab=None, timeout=0: criados.append(dado)
eo.criar_triagem({}, [item(), item(mid="m2", servico="Receita Federal", dominio="gov.br"), item(classe="suspeito", mid="m3")])
titulos = [c["titulo"] for c in criados]
confere("Serasa oficial urgente não vira triagem", not any("Serasa" in t and t.startswith("E-mail oficial") for t in titulos), titulos)
confere("Receita Federal urgente continua crítica", [c for c in criados if c["titulo"].startswith("E-mail oficial") and "Receita" in c["titulo"] and c["nivel"] == "critico"], criados)
confere("golpe imitando Serasa continua alertando", any(t.startswith("Possível golpe por e-mail") for t in titulos), titulos)
confere("a lista é configurável no .env", not eo.baixa_prioridade({"HEIMDALL_EMAIL_BAIXA_PRIORIDADE": "outra"}, item()) and eo.baixa_prioridade({"HEIMDALL_EMAIL_BAIXA_PRIORIDADE": "receita"}, item(servico="Receita Federal", dominio="gov.br")))
confere("lista vazia no .env não rebaixa ninguém", not eo.baixa_prioridade({"HEIMDALL_EMAIL_BAIXA_PRIORIDADE": " "}, item()))
confere("não rebaixa o que não é oficial", not eo.baixa_prioridade({}, item(classe="suspeito")))
confere("agendar não cria evento nem lembrete para Serasa", eo.agendar({}, item(), {"urgencia": "alta", "prazo_iso": "2026-12-01"}, __import__("datetime").datetime(2026, 11, 18, 10, 0)) == "")

# diagnóstico: mostra também o motivo e a autenticação, sem enviar nada
from email.message import EmailMessage  # noqa: E402
m = EmailMessage()
m["From"] = "Serasa <avisos@serasaconsumidor-exemplo.com>"
m["Subject"] = "Pagamento confirmado Serasa"
m["Date"] = "Wed, 18 Nov 2026 12:00:00 -0300"
m["Message-ID"] = "<d1@x>"
m["Authentication-Results"] = "mx.google.com; dkim=pass; spf=pass; dmarc=pass header.from=serasaconsumidor-exemplo.com"
linhas = []
rc = eo.diagnosticar({}, buscar=lambda cfg, extras: [("INBOX", m)], saida=linhas.append)
texto = "\n".join(linhas)
confere("diagnóstico retorna 0 e mostra domínio e motivo", rc == 0 and "serasaconsumidor-exemplo.com" in texto and "Por quê" in texto and "DMARC pass" in texto, texto)
linhas = []
eo.diagnosticar({}, buscar=lambda cfg, extras: [], saida=linhas.append)
confere("diagnóstico sem e-mails avisa", "Nenhum e-mail recente" in "\n".join(linhas), linhas)

# o modelo local não pode chamar de golpe um e-mail que o Gmail autenticou
import json as _json  # noqa: E402
fala = {"resumo": "E-mail falso que informa pagamento quitado com a Vivo, golpe de phishing.", "urgencia": "alta", "prazo": "", "prazo_iso": "", "acao": "NÃO clique em nenhum link e ignore o e-mail."}
eo.post_json = lambda url, dado, cab=None, timeout=0: {"choices": [{"message": {"content": _json.dumps(fala)}}]}
r = eo.resumir({"LITELLM_MASTER_KEY": "x"}, m, {"assunto": "Confirmação de pagamento!"})
confere("palpite de golpe do modelo é descartado e a urgência cai", r and "golpe" not in r["acao"].lower() and "phishing" not in r["resumo"].lower() and r["urgencia"] == "baixa", r)
fala = {"resumo": "Pagamento de R$ 50 confirmado.", "urgencia": "media", "prazo": "", "prazo_iso": "", "acao": "Guarde o comprovante."}
r = eo.resumir({"LITELLM_MASTER_KEY": "x"}, m, {"assunto": "Confirmação de pagamento!"})
confere("resumo normal passa intacto", r and r["resumo"].startswith("Pagamento") and r["urgencia"] == "media", r)
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
