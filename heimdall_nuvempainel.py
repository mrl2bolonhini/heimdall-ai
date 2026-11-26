#!/usr/bin/env python3
"""Dados da aba Nuvem do Studio Controls: continuidade (interruptor e última cópia), políticas de gasto da Cloudflare e o endereço da
página de controle na nuvem. Só lê; quem muda o interruptor é o Controls, pelo heimdall_config."""
import json
import urllib.error
import urllib.request

import heimdall_config as config
import heimdall_continuidade as continuidade

TETO_MENSAL = 15.0   # US$ por mês (CLAUDE.md)
PAINEL_NUVEM = "https://controls.heimdall-ai.tech/continuidade"
URL = "https://api.cloudflare.com/client/v4/accounts/{conta}/billing/spend-policies"
PRODUTOS = {"workers": "Workers", "durable_objects": "Durable Objects (contêiner)"}
ACOES = {"usage_block": "Bloqueio", "notification": "Aviso"}


def _env() -> dict:
    return {i["nome"]: i["valor"] for i in config.ler()}


def _abrir(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)


def politicas(env: dict = None, abrir=None) -> dict:
    """{ok, itens: [{produto, acao, limite, situacao}]} ou {ok: False, erro}. Usa CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID do .env."""
    e = _env() if env is None else env
    token, conta = e.get("CLOUDFLARE_API_TOKEN", "").strip(), e.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not conta:
        return {"ok": False, "erro": "Faltam CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID no .env."}
    req = urllib.request.Request(URL.format(conta=conta), headers={"Authorization": "Bearer " + token})
    try:
        with (abrir or _abrir)(req, 20) as r:
            dados = json.load(r)
    except urllib.error.HTTPError as ex:
        if ex.code == 403:
            return {"ok": False, "erro": "O token não tem a permissão Faturamento (leitura)."}
        return {"ok": False, "erro": f"A Cloudflare respondeu HTTP {ex.code}."}
    except (OSError, ValueError):
        return {"ok": False, "erro": "Não consegui falar com a Cloudflare agora."}
    itens = []
    for p in dados.get("result", []):
        if p.get("product_id") not in PRODUTOS:
            continue
        itens.append({"produto": PRODUTOS[p["product_id"]], "acao": ACOES.get(p.get("action"), str(p.get("action", ""))),
                      "limite": float(p.get("threshold_cents", 0)) / 100, "situacao": (p.get("current_state") or {}).get("status", "")})
    itens.sort(key=lambda i: (i["produto"], i["acao"], i["limite"]))
    return {"ok": True, "itens": itens}


def consumo(env: dict = None, abrir=None) -> dict:
    """Consumo faturável do mês corrente (API de uso da Cloudflare, beta): {ok, total, itens: [{servico, custo}], teto} ou {ok: False, erro}.
    Usa o token de leitura HEIMDALL_CF_LEITURA_TOKEN, ou o CLOUDFLARE_API_TOKEN se o de leitura não existir."""
    e = _env() if env is None else env
    token = (e.get("HEIMDALL_CF_LEITURA_TOKEN") or e.get("CLOUDFLARE_API_TOKEN") or "").strip()
    conta = e.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not conta:
        return {"ok": False, "erro": "Faltam o token e CLOUDFLARE_ACCOUNT_ID no .env."}
    req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{conta}/billing/usage/paygo", headers={"Authorization": "Bearer " + token})
    try:
        with (abrir or _abrir)(req, 20) as r:
            linhas = json.load(r).get("result") or []
    except urllib.error.HTTPError as ex:
        if ex.code == 403:
            return {"ok": False, "erro": "O token não tem a permissão Faturamento (leitura)."}
        return {"ok": False, "erro": f"A Cloudflare respondeu HTTP {ex.code} à consulta de consumo (a API ainda é beta e pode não estar liberada para a conta)."}
    except (OSError, ValueError):
        return {"ok": False, "erro": "Não consegui consultar o consumo agora."}
    por: dict = {}
    for l in linhas:
        por[l.get("ServiceName") or "Outros"] = por.get(l.get("ServiceName") or "Outros", 0.0) + float(l.get("BilledCost") or 0)
    itens = sorted(({"servico": k, "custo": v} for k, v in por.items()), key=lambda i: -i["custo"])
    return {"ok": True, "total": sum(por.values()), "itens": itens, "teto": TETO_MENSAL}


def avisos(env: dict = None, abrir=None, limite: int = 15) -> dict:
    """Últimos avisos enviados pela Cloudflare à conta (histórico de notificações: queda, certificado, erro). Token: Conta, Notificações, Leitura."""
    e = _env() if env is None else env
    token = (e.get("HEIMDALL_CF_LEITURA_TOKEN") or e.get("CLOUDFLARE_API_TOKEN") or "").strip()
    conta = e.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not token or not conta:
        return {"ok": False, "erro": "Faltam o token e CLOUDFLARE_ACCOUNT_ID no .env."}
    req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{conta}/alerting/v3/history?per_page={limite}", headers={"Authorization": "Bearer " + token})
    try:
        with (abrir or _abrir)(req, 20) as r:
            linhas = json.load(r).get("result") or []
    except urllib.error.HTTPError as ex:
        if ex.code == 403:
            return {"ok": False, "erro": "O token não tem a permissão Notificações (leitura)."}
        return {"ok": False, "erro": f"A Cloudflare respondeu HTTP {ex.code} à consulta de avisos."}
    except (OSError, ValueError):
        return {"ok": False, "erro": "Não consegui consultar os avisos agora."}
    itens = [{"quando": l.get("sent") or "", "nome": l.get("name") or l.get("alert_type") or "Aviso", "tipo": l.get("alert_type") or "",
              "texto": (l.get("alert_body") or l.get("description") or "")[:300]} for l in linhas]
    itens.sort(key=lambda i: i["quando"], reverse=True)
    return {"ok": True, "itens": itens[:limite]}


def estado(env: dict = None, abrir=None, cliente=None, com_nuvem: bool = True) -> dict:
    """Tudo o que a aba mostra. Cada parte falha sozinha, sem derrubar a página."""
    e = _env() if env is None else env
    saida = {"ligado": continuidade.ligado(e), "senha": bool(e.get("HEIMDALL_CONTINUIDADE_SENHA")), "painel": PAINEL_NUVEM, "teto": TETO_MENSAL}
    try:
        saida["copia"] = continuidade.status({**e, "HEIMDALL_CONTINUIDADE": "1"}, cliente) if saida["senha"] else {"ok": False, "erro": "A senha da continuidade ainda não foi criada (heimdall continuity --prepare)."}
    except Exception as ex:  # a nuvem pode estar fora; a página continua
        saida["copia"] = {"ok": False, "erro": f"Não consegui ler a cópia: {type(ex).__name__}."}
    saida["gastos"] = politicas(e, abrir) if com_nuvem else {"ok": False, "erro": "Consulta desligada."}
    saida["consumo"] = consumo(e, abrir) if com_nuvem else {"ok": False, "erro": "Consulta desligada."}
    saida["avisos"] = avisos(e, abrir) if com_nuvem else {"ok": False, "erro": "Consulta desligada."}
    return saida


def ligar(valor: bool) -> str:
    """Grava o interruptor da continuidade no .env. Devolve a mensagem de erro, ou '' se deu certo."""
    return config.salvar("HEIMDALL_CONTINUIDADE", "1" if valor else "0")


def enviar_agora() -> dict:
    """Envia a cópia cifrada dos bancos ao R2 agora, mesmo fora do horário automático."""
    try:
        return continuidade.enviar(env=_env())
    except Exception as ex:
        return {"ok": False, "erro": str(ex)[:160]}
