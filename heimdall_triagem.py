#!/usr/bin/env python3
"""Triagem obrigatória de avisos importantes (publicações do Diário da Justiça, alertas de saúde, e-mails suspeitos etc.).

Cada item importante vira um lembrete na lista "Heimdall: Triagem" do app Lembretes (iPhone e Mac). O Heimdall volta a
avisar pelo Bark enquanto o lembrete estiver pendente. Você age no próprio lembrete:
    concluir               = li e dispensei
    mudar a prioridade     = classificar a importância (alta, média ou baixa)
    mudar o horário        = adiar (o aviso espera até esse horário)

Regras de insistência (constantes abaixo):
    - Aviso a cada 2 horas, das 7h às 21h (fuso de São Paulo). À noite não toca.
    - Prioridade "baixa" no lembrete: o aviso passa a cada 8 horas.
    - Itens CRÍTICOS furam o modo silencioso (Bark nível "critical"). O primeiro aviso de um item crítico sai na hora,
      a qualquer hora; as repetições respeitam o horário das 7h às 21h.
    - Menções do Diário da Justiça viram críticas se ficarem 24 horas sem ação.
    - Se você baixar a prioridade de um item, ele deixa de ser tratado como crítico (você já o viu e decidiu).

Este módulo não fala com o macOS diretamente: quem chama (heimdall_agente.py) entrega a função que roda o AppleScript.
Assim as regras podem ser testadas em qualquer máquina (teste_triagem.py).
"""
import hashlib
import json
import os
import re
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import heimdall_banco as banco

try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # noqa: BLE001 - sem tzdata, usa o horário de Brasília sem verão
    FUSO = timezone(timedelta(hours=-3))

NOME_LISTA = "Heimdall: Triagem"
HORA_INICIO, HORA_FIM = 7, 21
INTERVALO = timedelta(hours=2)
INTERVALO_BAIXA = timedelta(hours=8)
ESCALA_JUSTICA = timedelta(hours=24)
ADIAR_MIN = 1800            # vencimento a mais de 30 min no futuro conta como adiamento
NIVEIS = ("critico", "alto", "medio")
PRIORIDADE_INICIAL = {"critico": 1, "alto": 5, "medio": 9}   # prioridade do app Lembretes: 1 alta, 5 média, 9 baixa
TEXTO_INICIAL = {"critico": "alta", "alto": "media", "medio": "baixa"}
INSTRUCAO = "Conclua este lembrete para dispensar, mude a prioridade para classificar a importância ou mude o horário para adiar."

AS_CRIAR = r'''
on run argv
    set tid to item 1 of argv
    set tit to item 2 of argv
    set corpo to item 3 of argv
    set prio to (item 4 of argv) as integer
    set nomeLista to item 5 of argv
    set marca to "[hd:" & tid & "]"
    tell application "Reminders"
        if not (exists list nomeLista) then make new list with properties {name:nomeLista}
        set l to list nomeLista
        if (count of (reminders of l whose body contains marca)) > 0 then return "ja_existe"
        set quando to (current date) + 60
        make new reminder at end of reminders of l with properties {name:tit, body:(corpo & return & return & marca), priority:prio, due date:quando, remind me date:quando}
        return "criado"
    end tell
end run
'''

AS_LER = r'''
on limpar(t)
    set AppleScript's text item delimiters to {tab, return, linefeed}
    set ps to text items of t
    set AppleScript's text item delimiters to " "
    set t to ps as text
    set AppleScript's text item delimiters to ""
    return t
end limpar

on formatar(bs, ps, ds, cs, ns, feito, agora)
    set saida to ""
    repeat with i from 1 to (count of bs)
        set b to item i of bs
        if b is missing value then set b to ""
        set tid to ""
        set AppleScript's text item delimiters to "[hd:"
        set partes to text items of b
        if (count of partes) > 1 then
            set AppleScript's text item delimiters to "]"
            set tid to text item 1 of (item 2 of partes)
        end if
        set AppleScript's text item delimiters to ""
        if tid is not "" then
            set pr to item i of ps
            if pr is missing value then set pr to 0
            set vence to ""
            set dd to item i of ds
            if dd is not missing value then set vence to ((dd - agora) as integer) as text
            set feitoEm to ""
            set cc to item i of cs
            if cc is not missing value then set feitoEm to ((cc - agora) as integer) as text
            set nome to item i of ns
            if nome is missing value then set nome to ""
            set nome to my limpar(nome)
            set saida to saida & tid & tab & feito & tab & (pr as text) & tab & vence & tab & feitoEm & tab & nome & linefeed
        end if
    end repeat
    return saida
end formatar

on run argv
    set nomeLista to item 1 of argv
    set agora to current date
    set pBs to {}
    set pPs to {}
    set pDs to {}
    set pCs to {}
    set pNs to {}
    set fBs to {}
    set fPs to {}
    set fDs to {}
    set fCs to {}
    set fNs to {}
    tell application "Reminders"
        if not (exists list nomeLista) then return "lista:ausente"
        set l to list nomeLista
        if (count of (reminders of l whose completed is false)) > 0 then
            set pBs to body of (reminders of l whose completed is false)
            set pPs to priority of (reminders of l whose completed is false)
            set pDs to due date of (reminders of l whose completed is false)
            set pNs to name of (reminders of l whose completed is false)
            repeat (count of pBs) times
                set end of pCs to missing value
            end repeat
        end if
        if (count of (reminders of l whose completed is true)) > 0 then
            set fBs to body of (reminders of l whose completed is true)
            set fPs to priority of (reminders of l whose completed is true)
            set fDs to due date of (reminders of l whose completed is true)
            set fCs to completion date of (reminders of l whose completed is true)
            set fNs to name of (reminders of l whose completed is true)
        end if
    end tell
    return "lista:ok" & linefeed & my formatar(pBs, pPs, pDs, pCs, pNs, "0", agora) & my formatar(fBs, fPs, fDs, fCs, fNs, "1", agora)
end run
'''


# ----------------------------------------------------------------------------------------
# Auxiliares
# ----------------------------------------------------------------------------------------
def _texto(s, limite: int) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f]", " ", str(s or "")).strip()[:limite]


def gerar_id(origem: str) -> str:
    """Identificador estável a partir da origem (a mesma publicação nunca vira dois lembretes)."""
    base = unicodedata.normalize("NFD", str(origem).lower()).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:30].strip("-")
    return (base + "-" if base else "") + hashlib.sha1(str(origem).encode("utf-8")).hexdigest()[:10]


def texto_prioridade(p: int) -> str:
    if p <= 0:
        return "nenhuma"
    if p <= 4:
        return "alta"
    if p == 5:
        return "media"
    return "baixa"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _linhas() -> dict:
    banco.iniciar() if not banco.DB_PATH.exists() else None
    con = banco.conectar()
    try:
        return {r["id"]: dict(r) for r in con.execute("SELECT * FROM triagem")}
    finally:
        con.close()


def _atualizar(tid: str, **campos) -> None:
    campos["atualizado"] = _iso(_agora())
    sql = "UPDATE triagem SET " + ", ".join(k + " = ?" for k in campos) + " WHERE id = ?"
    with banco._trava:
        con = banco.conectar()
        try:
            con.execute(sql, [*campos.values(), tid])
            con.commit()
        finally:
            con.close()


# ----------------------------------------------------------------------------------------
# Criar
# ----------------------------------------------------------------------------------------
def _corpo(resumo: str) -> str:
    return (resumo + "\n\n" if resumo else "") + INSTRUCAO


def _criar_lembrete(osa, tid: str, row: dict) -> str:
    return osa(AS_CRIAR, tid, row["titulo"], _corpo(row.get("resumo", "")), str(PRIORIDADE_INICIAL[row["nivel"]]), NOME_LISTA)


def criar(dado: dict, osa) -> dict:
    """dado: {id (origem estável), titulo, resumo, nivel: critico|alto|medio, fonte}. osa(script, *args) roda o AppleScript.
    O item é registrado no banco ANTES de pedir o lembrete: se o app Lembretes não responder (por exemplo, permissão pendente no
    Mac), nada se perde; o ciclo tenta criar o lembrete de novo e o Bark continua avisando."""
    origem = _texto(dado.get("id"), 300)
    titulo = _texto(dado.get("titulo"), 150)
    if not origem or not titulo:
        raise ValueError("faltam id e título")
    nivel = str(dado.get("nivel", "alto")).strip().lower()
    if nivel not in NIVEIS:
        nivel = "alto"
    fonte = re.sub(r"[^a-z0-9_-]", "", str(dado.get("fonte", "")).lower())[:20]
    resumo = _texto(dado.get("resumo"), 900)
    tid = gerar_id(origem)
    agora = _iso(_agora())
    banco.iniciar() if not banco.DB_PATH.exists() else None
    with banco._trava:
        con = banco.conectar()
        try:
            con.execute("INSERT OR IGNORE INTO triagem (id, criado, fonte, nivel, titulo, resumo, estado, lembrete, atualizado) "
                        "VALUES (?, ?, ?, ?, ?, ?, 'pendente', 0, ?)", (tid, agora, fonte, nivel, titulo, resumo, agora))
            con.commit()
        finally:
            con.close()
    try:
        r = _criar_lembrete(osa, tid, {"titulo": titulo, "resumo": resumo, "nivel": nivel})
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("item registrado, mas o lembrete não pôde ser criado agora (o ciclo tenta de novo): " + str(e)[:200]) from e
    _atualizar(tid, lembrete=1)
    return {"ok": True, "id": tid, "lembrete": r}


# ----------------------------------------------------------------------------------------
# Ler o estado dos lembretes
# ----------------------------------------------------------------------------------------
def _inteiro(s: str):
    s = str(s).strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def ler_lembretes(osa):
    """Devolve (lista_existe, {id: {feito, prioridade, vence_em, feito_em, nome}}); tempos em segundos relativos a agora."""
    saida = osa(AS_LER, NOME_LISTA)
    linhas = saida.splitlines()
    if not linhas or linhas[0].strip() != "lista:ok":
        return False, {}
    itens = {}
    for linha in linhas[1:]:
        p = linha.split("\t")
        if len(p) < 6 or not p[0].strip():
            continue
        itens[p[0].strip()] = {"feito": p[1].strip() in ("1", "true"), "prioridade": _inteiro(p[2]) or 0, "vence_em": _inteiro(p[3]),
                               "feito_em": _inteiro(p[4]), "nome": "\t".join(p[5:])}
    return True, itens


# ----------------------------------------------------------------------------------------
# Decidir quando avisar
# ----------------------------------------------------------------------------------------
def e_critico(row: dict, prioridade: str, agora: datetime) -> bool:
    if prioridade == "baixa":
        return False
    if row["nivel"] == "critico":
        return True
    return row["fonte"] == "justica" and agora - _dt(row["criado"]) >= ESCALA_JUSTICA


def deve_avisar(row: dict, prioridade: str, agora: datetime) -> tuple:
    """(avisar, critico). O primeiro aviso de um item crítico sai a qualquer hora; os demais, só das 7h às 21h."""
    critico = e_critico(row, prioridade, agora)
    dentro = HORA_INICIO <= agora.astimezone(FUSO).hour < HORA_FIM
    if not row.get("ultimo_aviso"):
        return (critico or dentro), critico
    intervalo = INTERVALO_BAIXA if prioridade == "baixa" else INTERVALO
    return (dentro and agora - _dt(row["ultimo_aviso"]) >= intervalo), critico


def montar_aviso(row: dict, critico: bool, pendentes: int, sem_lembrete: bool = False) -> dict:
    corpo = (row.get("resumo") or "")[:350]
    if sem_lembrete:
        corpo = (corpo + "\n" if corpo else "") + ("O lembrete ainda não foi criado no app Lembretes (autorização pendente no Mac); "
                                                  "o aviso continua até isso ser resolvido.")
    else:
        corpo = (corpo + "\n" if corpo else "") + "Abra o app Lembretes, lista " + NOME_LISTA + ". " + INSTRUCAO
    p = {"title": (("CRÍTICO: " if critico else "Triagem: ") + row["titulo"])[:100], "body": corpo[:900], "group": "triagem",
         "level": "critical" if critico else "timeSensitive", "badge": pendentes}
    if critico:
        p["volume"] = 7
    return p


def chave_bark() -> str:
    v = os.environ.get("HEIMDALL_BARK_KEY", "").strip()
    if not v:
        try:
            for linha in (Path(__file__).resolve().parent / ".env").read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*(?:export\s+)?HEIMDALL_BARK_KEY\s*=\s*(.*)$", linha)
                if m:
                    v = m.group(1).strip().strip("'\"")
        except OSError:
            pass
    return re.sub(r"^https?://[^/]+/([^/?]+).*", r"\1", v)


def enviar_bark(payload: dict) -> bool:
    chave = chave_bark()
    if not chave:
        return False
    req = urllib.request.Request("https://api.day.app/push", data=json.dumps({"device_key": chave, **payload}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return 200 <= r.status < 300
    except Exception:  # noqa: BLE001
        return False


# ----------------------------------------------------------------------------------------
# Ciclo (roda a cada 15 minutos, chamado pelo n8n)
# ----------------------------------------------------------------------------------------
def ciclo(osa, enviar=enviar_bark, agora: datetime = None) -> dict:
    agora = agora or _agora()
    res = {"pendentes": 0, "concluidas": 0, "descartadas": 0, "adiadas": 0, "classificadas": 0, "lembretes_criados": 0,
           "avisados": [], "falhas_aviso": 0, "lista_existe": True, "erro_lembretes": ""}
    try:
        lista_existe, lembretes = ler_lembretes(osa)
    except Exception as e:  # noqa: BLE001 - app Lembretes sem resposta (por exemplo, permissão pendente no Mac)
        lista_existe, lembretes = True, {}
        res["erro_lembretes"] = str(e)[:200]
    res["lista_existe"] = lista_existe
    sem_acesso = bool(res["erro_lembretes"])
    linhas = _linhas()
    # 1. cria os lembretes que ainda faltam (itens registrados quando o app Lembretes não respondia)
    if not sem_acesso:
        criou = False
        for tid, row in linhas.items():
            if row["estado"] == "pendente" and not row["lembrete"]:
                try:
                    _criar_lembrete(osa, tid, row)
                except Exception as e:  # noqa: BLE001
                    res["erro_lembretes"] = str(e)[:200]
                    sem_acesso = True
                    break
                _atualizar(tid, lembrete=1)
                row["lembrete"] = 1
                res["lembretes_criados"] += 1
                criou = True
        if criou and not sem_acesso:
            try:
                lista_existe, lembretes = ler_lembretes(osa)
                res["lista_existe"] = lista_existe
            except Exception as e:  # noqa: BLE001
                res["erro_lembretes"] = str(e)[:200]
                sem_acesso = True
    # 2. lê as suas decisões e decide quem recebe aviso
    a_avisar = []
    for tid, row in linhas.items():
        if row["estado"] != "pendente":
            continue
        lem = lembretes.get(tid)
        if lem is None:
            if row["lembrete"] and lista_existe and not sem_acesso:
                if agora - _dt(row["criado"]) > timedelta(minutes=10):
                    _atualizar(tid, estado="descartada", prioridade_usuario="apagada", decidido_em=_iso(agora))
                    res["descartadas"] += 1
                continue
            # sem lembrete (ainda não criado, ou o app não responde): continua pendente e o Bark segue avisando pelas regras
            res["pendentes"] += 1
            if row["adiado_ate"] and _dt(row["adiado_ate"]) > agora:
                continue
            avisar, critico = deve_avisar(row, row["prioridade_usuario"], agora)
            if avisar:
                a_avisar.append((tid, row, critico, True))
            continue
        txt = texto_prioridade(lem["prioridade"])
        if lem["feito"]:
            quando = agora + timedelta(seconds=lem["feito_em"]) if lem["feito_em"] is not None else agora
            _atualizar(tid, estado="concluida", prioridade_usuario=txt, decidido_em=_iso(quando))
            res["concluidas"] += 1
            continue
        if txt != TEXTO_INICIAL[row["nivel"]] and txt != row["prioridade_usuario"]:
            _atualizar(tid, prioridade_usuario=txt)
            row["prioridade_usuario"] = txt
            res["classificadas"] += 1
        res["pendentes"] += 1
        vence = lem["vence_em"]
        if vence is not None and vence > ADIAR_MIN:
            ate = _iso(agora + timedelta(seconds=vence))
            if not row["adiado_ate"] or abs((_dt(ate) - _dt(row["adiado_ate"])).total_seconds()) > 300:
                _atualizar(tid, adiado_ate=ate)
                res["adiadas"] += 1
            continue
        if row["adiado_ate"]:
            _atualizar(tid, adiado_ate="")
        avisar, critico = deve_avisar(row, txt if txt != "nenhuma" else row["prioridade_usuario"], agora)
        if avisar:
            a_avisar.append((tid, row, critico, False))
    for tid, row, critico, sem_lembrete in a_avisar:
        if enviar(montar_aviso(row, critico, res["pendentes"], sem_lembrete)):
            _atualizar(tid, avisos=int(row["avisos"] or 0) + 1, ultimo_aviso=_iso(agora))
            res["avisados"].append({"id": tid, "titulo": row["titulo"], "critico": critico})
        else:
            res["falhas_aviso"] += 1
    return res


def estado(limite: int = 50) -> dict:
    con = banco.conectar(somente_leitura=True) if banco.DB_PATH.exists() else None
    if con is None:
        return {"pendentes": [], "total": 0}
    try:
        linhas = [dict(r) for r in con.execute("SELECT id, criado, fonte, nivel, titulo, estado, prioridade_usuario, adiado_ate, avisos, ultimo_aviso "
                                               "FROM triagem WHERE estado = 'pendente' ORDER BY criado LIMIT ?", (int(limite),))]
        total = con.execute("SELECT COUNT(*) FROM triagem").fetchone()[0]
    finally:
        con.close()
    return {"pendentes": linhas, "total": total}
