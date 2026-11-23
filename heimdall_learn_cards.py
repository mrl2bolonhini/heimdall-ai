#!/usr/bin/env python3
"""Heimdall Learn, fase 5: cards (pílulas de conhecimento) e agenda de frequência.

Cada pasta pode ter, por dia, de 0 a 3 cards e de 0 a 1 lição (a lição só em pasta sequencial), a partir de um horário configurável.
Os cards saem espaçados de 4 em 4 horas depois do horário; a lição, no horário. O Learn confere a cada minuto o que falta fazer
(uma ação por pasta por vez), cria o card ou a lição e avisa: notificação nativa do Mac com o texto completo, e Bark no iPhone só com texto
genérico (o texto passa por servidor de terceiros). Falha do modelo: espera 30 minutos antes de tentar de novo.

Desligar: HEIMDALL_LEARN_AGENDA=0 (não gera nada sozinho) e HEIMDALL_LEARN_NOTIFICAR=0 (gera, mas não avisa).
Usa só a biblioteca padrão do Python.
"""
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import heimdall_learn_dados as dados
import heimdall_pessoas as pessoas
import heimdall_learn_estudo as estudo
import heimdall_learn_licoes as licoes
import heimdall_learn_tipos as tipos

PROMPT = Path(__file__).resolve().parent / "prompts" / "prompt_learn_card.txt"
MAX_CARDS_DIA, MAX_LICOES_DIA = 3, 1
ESPERA_FALHA = 30 * 60
_falhas: dict = {}


def _hhmm(h: str) -> str:
    h = (h or "").strip()
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", h)
    if not m:
        raise dados.ErroLearn("Horário inválido. Use hora e minuto, por exemplo 08:30.")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def obter_agenda(rel: str) -> dict:
    rel = dados.normalizar_caminho(rel)
    r = dados.conectar().execute("SELECT * FROM agenda WHERE pasta = ?", (rel,)).fetchone()
    return dict(r) if r else {"pasta": rel, "cards_dia": 0, "licao_dia": 0, "horario": "08:00", "ativo": 1}


def configurar(rel: str, cards_dia, licao_dia, horario: str) -> dict:
    pasta = dados.obter_pasta(rel)
    if not pasta:
        raise dados.ErroLearn("Pasta não encontrada.")
    try:
        c, li = int(cards_dia), int(licao_dia)
    except (TypeError, ValueError):
        raise dados.ErroLearn("Informe números para cards e lições por dia.")
    if not 0 <= c <= MAX_CARDS_DIA:
        raise dados.ErroLearn(f"No máximo {MAX_CARDS_DIA} cards por dia.")
    if not 0 <= li <= MAX_LICOES_DIA:
        raise dados.ErroLearn(f"No máximo {MAX_LICOES_DIA} lição por dia.")
    if li and pasta["categoria"] != "sequencial":
        raise dados.ErroLearn("Só pastas da categoria sequencial têm lição por dia.")
    h = _hhmm(horario)
    con = dados.conectar()
    with dados._trava:
        con.execute("INSERT OR REPLACE INTO agenda (pasta, cards_dia, licao_dia, horario, ativo) VALUES (?, ?, ?, ?, 1)", (pasta["caminho"], c, li, h))
        con.commit()
    return obter_agenda(pasta["caminho"])


def horarios_dos_cards(horario: str, n: int) -> list:
    """Horários dos n cards do dia: o primeiro no horário e os outros a cada 4 horas (apertados se não couberem até 23:59)."""
    h, m = map(int, horario.split(":"))
    ini = h * 60 + m
    passo = 240 if ini + 240 * max(0, n - 1) <= 23 * 60 + 59 else max(30, (23 * 60 + 59 - ini) // max(1, n - 1))
    return [f"{(ini + passo * k) // 60:02d}:{(ini + passo * k) % 60:02d}" for k in range(n)]


def _modelo(sistema: str, usuario: str, max_tokens: int = 400) -> str:
    import heimdall_perguntar as perguntar
    return perguntar.chamar_local(sistema, usuario, max_tokens=max_tokens)


def _sistema(pasta: dict) -> str:
    try:
        base = PROMPT.read_text(encoding="utf-8")
    except OSError:
        base = "Escreva um card curto em português com título na primeira linha. {regras}"
    return base.replace("{regras}", tipos.regras_para_prompt(pasta["tipo"], pasta["categoria"], pasta.get("idioma", "")))


def _trecho_para_card(pasta: dict, rng) -> tuple:
    """(documento, texto). Pasta sequencial: só do que já foi estudado (as lições criadas), para o card revisar e não adiantar."""
    if pasta["categoria"] == "sequencial":
        mat = licoes.material(pasta["caminho"])
        if not mat:
            raise dados.ErroLearn("Esta pasta ainda não tem material de texto.")
        feitas = licoes.resumo_progresso(pasta["caminho"])["criadas"]
        janela = mat[:max(licoes.TRECHOS_POR_LICAO, feitas * licoes.TRECHOS_POR_LICAO)]
        return rng.choice(janela)
    t = estudo.sortear(pasta["caminho"], rng)
    return t["documento"], t["trecho"]


def gerar_card(rel: str, modelo=None, rng=None, origem: str = "agenda") -> int:
    """Cria um card da pasta com o modelo. Levanta ErroLearn/RuntimeError se não der. Devolve o id."""
    pasta = dados.obter_pasta(rel)
    if not pasta:
        raise dados.ErroLearn("Pasta não encontrada.")
    doc, texto = _trecho_para_card(pasta, rng or random)
    bruto = (modelo or _modelo)(_sistema(pasta), f"TRECHO (de {doc}):\n{texto}\n\nEscreva o card.").strip()
    linhas = [x.strip() for x in bruto.splitlines()]
    titulo = re.sub(r"^[#*\s]+|[*\s]+$", "", linhas[0]) if linhas else ""
    corpo = " ".join(x for x in linhas[1:] if x)
    if not titulo or len(corpo) < 20:
        raise RuntimeError("o modelo não devolveu um card com título e texto")
    con = dados.conectar()
    with dados._trava:
        cur = con.execute("INSERT INTO cards (pasta, titulo, corpo, fonte, origem, dia, criado) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (pasta["caminho"], titulo[:100], corpo[:900], Path(doc).name, origem, dados._agora()[:10], dados._agora()))
        con.commit()
    return cur.lastrowid


def listar(nao_lidos: bool = False, limite: int = 50) -> list:
    q = "SELECT * FROM cards " + ("WHERE lido = 0 " if nao_lidos else "") + "ORDER BY id DESC LIMIT ?"
    return [dict(r) for r in dados.conectar().execute(q, (limite,)).fetchall()]


def marcar_lido(id_: int, lido: bool = True) -> None:
    con = dados.conectar()
    with dados._trava:
        con.execute("UPDATE cards SET lido = ? WHERE id = ?", (1 if lido else 0, int(id_)))
        con.commit()


def notificar_padrao(titulo: str, corpo: str, generico: str = "Há novidade no Learn.") -> None:
    """Mac: aviso nativo com o texto completo. iPhone: Bark só com texto genérico. Nunca levanta erro."""
    if os.environ.get("HEIMDALL_LEARN_NOTIFICAR", "1") == "0" or dados.ajuste("avisos", "1") == "0":
        return
    try:
        import heimdall_avisos_mac as mac
        mac.publicar({"title": titulo, "body": corpo, "group": "learn", "level": "active"})
    except Exception:  # noqa: BLE001
        pass
    try:
        import heimdall_triagem as tri
        tri.enviar_bark({"title": "Learn", "body": generico, "group": "learn"})
    except Exception:  # noqa: BLE001
        pass


def _tentar(chave: tuple, agora: float) -> bool:
    return agora - _falhas.get(chave, 0) >= ESPERA_FALHA


def executar_agenda(agora: datetime = None, modelo_card=None, modelo_licao=None, notificar=None, rng=None) -> list:
    """Faz o que a agenda pede neste momento (no máximo uma ação por pasta). Devolve a lista do que fez ou falhou, para log e teste."""
    if dados.ajuste("agenda", "1") == "0":
        return []   # pausada nos Ajustes do site (vale na hora, sem reiniciar)
    agora = agora or datetime.now()
    notificar = notificar or notificar_padrao
    rng = rng or random
    dia, hora = agora.strftime("%Y-%m-%d"), agora.strftime("%H:%M")
    feito = []
    con = dados.conectar()
    for ag in [dict(r) for r in con.execute("SELECT * FROM agenda WHERE ativo = 1").fetchall()]:
        rel = ag["pasta"]
        pasta = dados.obter_pasta(rel)
        if not pasta:
            continue
        try:
            if ag["licao_dia"] and pasta["categoria"] == "sequencial" and hora >= ag["horario"] and _tentar((rel, "licao"), time.time()):
                ja = con.execute("SELECT COUNT(*) FROM licoes WHERE pasta = ? AND origem = 'agenda' AND criado LIKE ?", (rel, dia + "%")).fetchone()[0]
                aberta = con.execute("SELECT 1 FROM licoes WHERE pasta = ? AND estado IN ('gerando','pronta','corrigindo','erro','erro_correcao')", (rel,)).fetchone()
                if ja < MAX_LICOES_DIA and not aberta:
                    try:
                        id_ = licoes.nova_licao(rel, "agenda")
                        licoes.gerar(id_, modelo_licao)
                        lic = licoes.obter(id_)
                        if lic["estado"] != "pronta":
                            raise RuntimeError(lic["erro"] or "lição não gerada")
                        notificar(f"Lição nova: {lic['titulo']}", f"{pasta['nome']}, lição {lic['numero']}. Abra o Learn para estudar.", "Há uma lição nova no Learn.")
                        feito.append(f"lição {rel}")
                        continue
                    except dados.ErroLearn:
                        pass   # material acabou: sem lição hoje
                    except Exception as ex:  # noqa: BLE001
                        _falhas[(rel, "licao")] = time.time()
                        feito.append(f"erro lição {rel}: {str(ex)[:80]}")
                        continue
            n = min(MAX_CARDS_DIA, ag["cards_dia"])
            if n:
                feitos = con.execute("SELECT COUNT(*) FROM cards WHERE pasta = ? AND origem = 'agenda' AND dia = ?", (rel, dia)).fetchone()[0]
                slots = horarios_dos_cards(ag["horario"], n)
                if feitos < n and hora >= slots[feitos] and _tentar((rel, "card"), time.time()):
                    try:
                        cid = gerar_card(rel, modelo_card, rng)
                        c = con.execute("SELECT titulo, corpo FROM cards WHERE id = ?", (cid,)).fetchone()
                        notificar(f"Card do Learn: {c['titulo']}", c["corpo"], "Há um card novo no Learn.")
                        feito.append(f"card {rel}")
                    except Exception as ex:  # noqa: BLE001
                        _falhas[(rel, "card")] = time.time()
                        feito.append(f"erro card {rel}: {str(ex)[:80]}")
        except Exception as ex:  # noqa: BLE001
            feito.append(f"erro {rel}: {str(ex)[:80]}")
    return feito


def iniciar_agenda(intervalo: int = 60):
    """Thread que confere a agenda a cada minuto. Desligada com HEIMDALL_LEARN_AGENDA=0. Devolve a thread ou None."""
    if os.environ.get("HEIMDALL_LEARN_AGENDA", "1") == "0":
        return None

    def laco():
        while True:
            for pessoa in pessoas.existentes(dados.pasta_dados_base()):
                try:
                    with pessoas.definir(pessoa):
                        # aviso no Mac e no iPhone é do dono; as outras pessoas recebem o conteúdo na aba Cards, sem aviso, até haver um canal próprio
                        for linha in executar_agenda(notificar=None if pessoa == pessoas.DONO else (lambda *a, **k: None)):
                            import sys
                            sys.stderr.write(f"{time.strftime('%H:%M:%S')} agenda ({pessoa}): {linha}\n")
                except Exception as ex:  # noqa: BLE001
                    import sys
                    sys.stderr.write(f"{time.strftime('%H:%M:%S')} agenda falhou ({pessoa}): {type(ex).__name__}: {str(ex)[:100]}\n")
            time.sleep(intervalo)

    t = threading.Thread(target=laco, daemon=True, name="learn-agenda")
    t.start()
    return t
