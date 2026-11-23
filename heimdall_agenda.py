#!/usr/bin/env python3
"""Evento do Calendário ou lembrete do app Lembretes: a regra única do Heimdall.

Regra (vale para toda aplicação do Heimdall):
  - EVENTO (Calendário, calendário "Heimdall") é algo que acontece numa data e hora, ou que tem data fixa para olhar: consulta, retorno, prazo.
    Não tem "concluído": passa quando o dia passa.
  - LEMBRETE (app Lembretes, lista "Heimdall" ou "Heimdall: Triagem") é algo que você precisa fazer e marcar como feito: conferir, pagar, ligar.
    Fica pendente até você concluir, e o Heimdall volta a avisar enquanto estiver pendente.
Cada tipo de item que vai para a agenda é cadastrado em DESTINOS, com o destino escolhido. Quem criar um tipo novo acrescenta aqui (o teste
tests/agent/teste_agenda.py barra tipo fora desta tabela) e a tabela entra na página de documentação.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
AGENTE = os.environ.get("HEIMDALL_AGENTE_URL", "http://127.0.0.1:8003")
EVENTO, LEMBRETE = "evento", "lembrete"
ROTA = {EVENTO: "/calendario/evento", LEMBRETE: "/lembretes/criar"}
ROTA_DESFAZER = {EVENTO: "/calendario/desfazer", LEMBRETE: "/lembretes/desfazer"}

# tipo -> (destino, quando acontece, onde nasce)
DESTINOS = {
    "consulta": (EVENTO, "dia e hora da consulta médica, com local e médico", "heimdall health --labs: consulta lida de um documento ou cadastrada à mão"),
    "renovacao_receita": (EVENTO, "dia de dar entrada no pedido de renovação, alguns dias antes de a receita vencer", "heimdall health --labs: receita confirmada com validade"),
    "prazo_oficial": (EVENTO, "data-limite de um comunicado oficial (dia inteiro)", "heimdall_email_oficial.py: e-mail oficial confirmado"),
    "verificar_prazo": (LEMBRETE, "conferir o comunicado oficial, com hora, até você concluir", "heimdall_email_oficial.py"),
    "evento_nota": (EVENTO, "compromisso com data (e hora) achado numa nota escrita no Heimdall Notes", "heimdall_catalogo.py: nota catalogada pela IA local"),
    "lembrete_nota": (LEMBRETE, "algo a fazer, com data, achado numa nota escrita no Heimdall Notes", "heimdall_catalogo.py: nota catalogada pela IA local"),
    "triagem": (LEMBRETE, "item importante que pede decisão; você conclui, reclassifica ou adia", "heimdall_triagem.py (lista Heimdall: Triagem)"),
}

REGRA = ("Evento é o que acontece numa data e hora ou tem data fixa (consulta, prazo): vai para o Calendário. "
         "Lembrete é o que você precisa fazer e marcar como feito: vai para o app Lembretes.")


def destino(tipo: str) -> str:
    if tipo not in DESTINOS:
        raise KeyError(f"tipo de agenda desconhecido: {tipo}. Cadastre-o em DESTINOS de heimdall_agenda.py, escolhendo evento ou lembrete.")
    return DESTINOS[tipo][0]


def _token() -> str:
    t = os.environ.get("HEIMDALL_AGENTE_TOKEN", "")
    if t:
        return t
    try:
        for ln in (AQUI / ".env").read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("HEIMDALL_AGENTE_TOKEN="):
                v = ln.split("=", 1)[1].strip()
                return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v
    except OSError:
        pass
    return ""


def enviar(tipo: str, dado: dict, post=None) -> tuple:
    """Cria o evento ou o lembrete pelo agente do Mac. Devolve (ok, texto). Nunca levanta erro: falha de rede vira (False, motivo).
    `post` é para teste: função (url, corpo, cabecalho) -> dict."""
    rota = ROTA[destino(tipo)]
    corpo = json.dumps(dado).encode("utf-8")
    cab = {"Content-Type": "application/json", "X-Heimdall-Token": _token()}
    try:
        if post:
            r = post(AGENTE + rota, dado, cab)
        else:
            req = urllib.request.Request(AGENTE + rota, data=corpo, headers=cab, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                r = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return False, f"o agente recusou ({e.code})"
    except Exception as e:  # noqa: BLE001
        return False, f"não consegui falar com o agente do Mac ({type(e).__name__})"
    if not isinstance(r, dict) or not r.get("ok"):
        return False, "o agente não confirmou"
    return True, str(r.get("evento") or r.get("lembrete") or "ok")


def desfazer(tipo: str, dado: dict, post=None) -> tuple:
    """Apaga o evento ou lembrete que este mesmo tipo criou (mesmo título e data). Devolve (ok, texto)."""
    rota = ROTA_DESFAZER[destino(tipo)]
    cab = {"Content-Type": "application/json", "X-Heimdall-Token": _token()}
    try:
        if post:
            r = post(AGENTE + rota, dado, cab)
        else:
            req = urllib.request.Request(AGENTE + rota, data=json.dumps(dado).encode("utf-8"), headers=cab, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                r = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return False, f"não consegui falar com o agente do Mac ({type(e).__name__})"
    if not isinstance(r, dict) or not r.get("ok"):
        return False, "o agente não confirmou"
    return True, str(r.get("resultado") or "ok")
