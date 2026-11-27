#!/usr/bin/env python3
"""Lembretes e Calendário pelo EventKit (a interface de agenda do próprio macOS), SEM abrir os apps Lembretes e Calendário.

O AppleScript obriga o macOS a abrir o app (que aparece na tela e no Command+Tab). O EventKit lê e grava os mesmos dados sem abrir app nenhum.
O agente (studio_agente.osascript) tenta primeiro este módulo para os scripts registrados em registrar(); se o EventKit não estiver
disponível (pacote não instalado, permissão negada, erro), cai no AppleScript de antes, então nada deixa de funcionar.

Dependência: pip install pyobjc-framework-EventKit (no venv do StudioLibre). Permissão: na primeira vez o macOS pergunta se o programa pode
acessar Lembretes e Calendário. Desligar: STUDIO_EVENTKIT=0 no .env. Conferir: venv/bin/python studio_eventkit.py --status
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from datetime import datetime

ATIVO = os.environ.get("STUDIO_EVENTKIT", "1").strip() != "0"
try:  # pyobjc só existe no macOS
    import EventKit as EK  # type: ignore
    import Foundation as NS  # type: ignore
    PACOTE = True
except Exception:  # noqa: BLE001
    EK = NS = None
    PACOTE = False

ESPERA_PERMISSAO_S = 30
REPETIR_APOS_FALHA_S = 600     # depois de uma falha de permissão, usa o AppleScript por 10 min antes de tentar de novo


class EKIndisponivel(Exception):
    """O EventKit não pode ser usado agora (pacote, permissão ou sessão sem tela): usar o AppleScript."""


def _log(msg: str) -> None:
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} EventKit: {msg}\n")


# ----------------------------------------------------------------------------------------
# Acesso e loja de eventos
# ----------------------------------------------------------------------------------------
_loja_unica = None
_liberado: dict[int, bool] = {}
_lock = threading.RLock()


def _loja():
    global _loja_unica
    if _loja_unica is None:
        _loja_unica = EK.EKEventStore.alloc().init()
    return _loja_unica


def _tipo(nome: str) -> int:
    return EK.EKEntityTypeEvent if nome == "evento" else EK.EKEntityTypeReminder


def estado_permissao(nome: str) -> str:
    """'liberado', 'negado', 'restrito', 'nao-pedido' ou 'so-escrita'."""
    if not PACOTE:
        return "pacote-ausente"
    st = int(EK.EKEventStore.authorizationStatusForEntityType_(_tipo(nome)))
    return {0: "nao-pedido", 1: "restrito", 2: "negado", 3: "liberado", 4: "so-escrita"}.get(st, f"desconhecido({st})")


def garantir_acesso(nome: str) -> None:
    """Levanta EKIndisponivel se a permissão não existe. Na primeira vez pede ao macOS (o aviso aparece na tela)."""
    if not PACOTE:
        raise EKIndisponivel("pacote pyobjc-framework-EventKit não instalado")
    ent = _tipo(nome)
    with _lock:
        if _liberado.get(ent):
            return
        est = estado_permissao(nome)
        if est == "liberado":
            _liberado[ent] = True
            return
        if est in ("negado", "restrito"):
            raise EKIndisponivel(f"permissão de {'Calendário' if nome == 'evento' else 'Lembretes'} {est} (Ajustes do Sistema, Privacidade e Segurança)")
        feito, res = threading.Event(), {}

        def resposta(concedido, erro):
            res["ok"] = bool(concedido)
            res["erro"] = str(erro) if erro else ""
            feito.set()

        loja = _loja()
        pedir = getattr(loja, "requestFullAccessToEventsWithCompletion_" if nome == "evento" else "requestFullAccessToRemindersWithCompletion_", None)
        if pedir:
            pedir(resposta)
        else:  # macOS anterior ao 14
            loja.requestAccessToEntityType_completion_(ent, resposta)
        if not feito.wait(ESPERA_PERMISSAO_S):
            raise EKIndisponivel("o macOS não respondeu ao pedido de permissão (sessão sem tela, como SSH?)")
        if not res.get("ok"):
            raise EKIndisponivel("permissão não concedida" + (f" ({res['erro'][:80]})" if res.get("erro") else ""))
        _liberado[ent] = True


# ----------------------------------------------------------------------------------------
# Auxiliares
# ----------------------------------------------------------------------------------------
def _ts_local(y: int, m: int, d: int, hh: int = 0, mi: int = 0) -> float:
    return datetime(int(y), int(m), int(d), int(hh), int(mi)).timestamp()


def _nsdate(ts: float):
    return NS.NSDate.dateWithTimeIntervalSince1970_(ts)


def _salvou(res, o_que: str) -> None:
    ok, erro = res if isinstance(res, tuple) else (res, None)
    if not ok:
        raise RuntimeError(f"não consegui salvar {o_que}: {erro}")


def _achar_calendario(nome_lista: str, tipo: str, criar: bool):
    """Calendário de eventos ou lista de lembretes pelo nome. Cria na mesma conta do padrão se pedido. Devolve (calendario, criado)."""
    garantir_acesso(tipo)
    loja = _loja()
    for c in loja.calendarsForEntityType_(_tipo(tipo)) or []:
        if str(c.title()) == nome_lista and c.allowsContentModifications():
            return c, False
    if not criar:
        return None, False
    padrao = loja.defaultCalendarForNewEvents() if tipo == "evento" else loja.defaultCalendarForNewReminders()
    if padrao is None or padrao.source() is None:
        raise EKIndisponivel("não há conta padrão para criar o " + ("calendário" if tipo == "evento" else "a lista"))
    cal = EK.EKCalendar.calendarForEntityType_eventStore_(_tipo(tipo), loja)
    cal.setTitle_(nome_lista)
    cal.setSource_(padrao.source())
    _salvou(loja.saveCalendar_commit_error_(cal, True, None), "o calendário" if tipo == "evento" else "a lista")
    return cal, True


def _lembretes_da_lista(cal) -> list:
    loja = _loja()
    feito, saida = threading.Event(), []

    def resposta(rs):
        saida.extend(list(rs or []))
        feito.set()

    loja.fetchRemindersMatchingPredicate_completion_(loja.predicateForRemindersInCalendars_([cal]), resposta)
    if not feito.wait(ESPERA_PERMISSAO_S):
        raise EKIndisponivel("a busca de lembretes não respondeu")
    return saida


def _evento_igual(cal, titulo: str, inicio_ts: float) -> bool:
    loja = _loja()
    pred = loja.predicateForEventsWithStartDate_endDate_calendars_(_nsdate(inicio_ts - 1), _nsdate(inicio_ts + 86400), [cal])
    for e in loja.eventsMatchingPredicate_(pred) or []:
        if str(e.title()) == titulo and abs(float(e.startDate().timeIntervalSince1970()) - inicio_ts) < 1:
            return True
    return False


def _salvar_evento(ev) -> None:
    _salvou(_loja().saveEvent_span_commit_error_(ev, EK.EKSpanThisEvent, True, None), "o evento")


def _data_componentes(ts: float):
    cal = NS.NSCalendar.currentCalendar()
    flags = NS.NSCalendarUnitYear | NS.NSCalendarUnitMonth | NS.NSCalendarUnitDay | NS.NSCalendarUnitHour | NS.NSCalendarUnitMinute | NS.NSCalendarUnitSecond
    return cal.components_fromDate_(flags, _nsdate(ts))


def _criar_lembrete_ek(cal, titulo: str, notas: str, quando_ts: float, prioridade: int = 0) -> None:
    r = EK.EKReminder.reminderWithEventStore_(_loja())
    r.setTitle_(titulo)
    r.setNotes_(notas)
    r.setCalendar_(cal)
    r.setPriority_(int(prioridade))
    r.setDueDateComponents_(_data_componentes(quando_ts))
    r.addAlarm_(EK.EKAlarm.alarmWithAbsoluteDate_(_nsdate(quando_ts)))
    _salvou(_loja().saveReminder_commit_error_(r, True, None), "o lembrete")


# ----------------------------------------------------------------------------------------
# Calendário
# ----------------------------------------------------------------------------------------
def evento_dia_inteiro(tit, y, m, dd, notas, antes, nome_cal) -> str:
    cal, _ = _achar_calendario(nome_cal, "evento", True)
    ini = _ts_local(y, m, dd)
    if _evento_igual(cal, tit, ini):
        return "ja_existe"
    ev = EK.EKEvent.eventWithEventStore_(_loja())
    ev.setTitle_(tit)
    ev.setCalendar_(cal)
    ev.setAllDay_(True)
    ev.setStartDate_(_nsdate(ini))
    ev.setEndDate_(_nsdate(ini + 86399))
    ev.setNotes_(notas)
    antes = int(antes)
    if antes > 0:   # igual ao AppleScript: às 9h, `antes` dias antes
        ev.addAlarm_(EK.EKAlarm.alarmWithRelativeOffset_(float((-1440 * antes + 540) * 60)))
    _salvar_evento(ev)
    return "criado"


def evento_com_hora(tit, y, m, dd, hh, mi, dur, notas, lugar, alarmes, nome_cal) -> str:
    cal, _ = _achar_calendario(nome_cal, "evento", True)
    ini = _ts_local(y, m, dd, hh, mi)
    if _evento_igual(cal, tit, ini):
        return "ja_existe"
    ev = EK.EKEvent.eventWithEventStore_(_loja())
    ev.setTitle_(tit)
    ev.setCalendar_(cal)
    ev.setStartDate_(_nsdate(ini))
    ev.setEndDate_(_nsdate(ini + int(dur) * 60))
    ev.setNotes_(notas)
    if lugar:
        ev.setLocation_(lugar)
    for a in [x for x in str(alarmes).split(",") if x.strip()]:   # os alertas chegam em segundos antes do início
        ev.addAlarm_(EK.EKAlarm.alarmWithRelativeOffset_(float(-int(a))))
    _salvar_evento(ev)
    return "criado"


def preparar_calendario(nome_cal) -> str:
    _, criado = _achar_calendario(nome_cal, "evento", True)
    return "calendário criado" if criado else "calendário já existe"


# ----------------------------------------------------------------------------------------
# Lembretes
# ----------------------------------------------------------------------------------------
def lembrete_simples(tit, y, m, dd, h, notas, nome_lista) -> str:
    cal, _ = _achar_calendario(nome_lista, "lembrete", True)
    for r in _lembretes_da_lista(cal):
        if str(r.title() or "") == tit and not r.isCompleted():
            return "ja_existe"
    _criar_lembrete_ek(cal, tit, notas, _ts_local(y, m, dd, h))
    return "criado"


def preparar_lista(nome_lista) -> str:
    _, criado = _achar_calendario(nome_lista, "lembrete", True)
    return "lista criada" if criado else "lista já existe"


# ----------------------------------------------------------------------------------------
# Registro: qual AppleScript é resolvido por qual função
# ----------------------------------------------------------------------------------------
_registro: dict[str, object] = {}
_falha_ate = 0.0
_avisou = [False]


def registrar(script: str, funcao) -> None:
    _registro[script] = funcao


def tentar(script: str, args) -> tuple[bool, str | None]:
    """(True, resultado) se o EventKit resolveu; (False, None) se o chamador deve usar o AppleScript."""
    global _falha_ate
    if not ATIVO or script not in _registro or time.time() < _falha_ate:
        return False, None
    try:
        with _lock:
            return True, str(_registro[script](*args))
    except EKIndisponivel as e:
        _falha_ate = time.time() + REPETIR_APOS_FALHA_S
        if not _avisou[0]:
            _avisou[0] = True
            _log(f"indisponível ({e}); usando o AppleScript, que abre os apps. Veja: venv/bin/python studio_eventkit.py --status")
        return False, None
    except Exception as e:  # noqa: BLE001 - qualquer erro cai no AppleScript, que já funcionava
        _log(f"erro ({type(e).__name__}: {str(e)[:160]}); usando o AppleScript desta vez")
        return False, None


def verificar_na_partida() -> None:
    """Pede as permissões já na partida do agente (o aviso do macOS aparece uma vez) e registra o resultado no log."""
    if not ATIVO:
        _log("desligado (STUDIO_EVENTKIT=0)")
        return
    if not PACOTE:
        _log("pacote pyobjc-framework-EventKit não instalado; Lembretes e Calendário seguem pelo AppleScript (abrem os apps). "
             "Instale com: venv/bin/pip install pyobjc-framework-EventKit")
        return
    for nome, rotulo in (("lembrete", "Lembretes"), ("evento", "Calendário")):
        try:
            garantir_acesso(nome)
            _log(f"{rotulo}: liberado")
        except EKIndisponivel as e:
            _log(f"{rotulo}: {e}")


if __name__ == "__main__":
    if "--status" in sys.argv:
        print("Pacote pyobjc-framework-EventKit:", "instalado" if PACOTE else "NÃO instalado")
        if PACOTE:
            for nome, rotulo in (("lembrete", "Lembretes"), ("evento", "Calendário")):
                print(f"{rotulo}: {estado_permissao(nome)}")
            print("Pedindo as permissões que faltam (o macOS pode mostrar um aviso na tela)...")
            ATIVO = True
            verificar_na_partida()
            for nome, rotulo in (("lembrete", "Lembretes"), ("evento", "Calendário")):
                print(f"{rotulo} agora: {estado_permissao(nome)}")
    else:
        print("Uso: venv/bin/python studio_eventkit.py --status")
