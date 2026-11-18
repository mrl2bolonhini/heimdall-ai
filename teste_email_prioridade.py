#!/usr/bin/env python3
"""Testa o rebaixamento de e-mails oficiais de serviços sem interesse (Serasa, SPC...) na triagem e no agendamento."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
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
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
