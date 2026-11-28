#!/usr/bin/env python3
"""Andamentos de processos pelo DataJud (API pública do CNJ) para a área Cidadania do Studio Miner.

Para cada número de processo que a pessoa informou em Ajustes (subaba Cidadania), consulta o índice do tribunal que o número indica (campos J e TR do número
único) e avisa os andamentos novos, com o que o movimento significa e o que conferir. Complementa o DJEN (studio_djen.py), que traz o texto das intimações:
o DataJud traz capa e movimentações, com atraso de alguns dias, sem partes, sem processos sigilosos e sem o STF (para o STF, o aviso indica o STF Push).

Termos do CNJ (levantamento de 27/11/2026): limite de 120 consultas por minuto (aqui, uma por segundo), uso só para fins legais, sem coleta de dados pessoais
de terceiros e sem exploração comercial sem autorização escrita (uso pessoal por enquanto; revisar quando virar produto). A chave é pública e única para todos
os usuários, mas o CNJ pode trocá-la: STUDIO_DATAJUD_CHAVE (no .env) substitui a que vem de fábrica.
Variáveis: STUDIO_MINER_DATAJUD (padrão 1; 0 desliga), STUDIO_DATAJUD_CHAVE, STUDIO_DATAJUD_URL.
Usa só a biblioteca padrão do Python.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

import studio_djen as djen

BASE = os.environ.get("STUDIO_DATAJUD_URL", "https://api-publica.datajud.cnj.jus.br").rstrip("/")
CHAVE_PADRAO = "cDZHYzlZa0JadVREZDJCendFbXNpMDI="   # chave pública divulgada pelo CNJ; o CNJ pode trocá-la (veja STUDIO_DATAJUD_CHAVE)
PAUSA_S = 1.0
MAX_MOVIMENTOS_NO_ALERTA = 5

_UFS = ["ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms", "mg", "pa", "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc", "se", "sp", "to"]


def indice(numero: str) -> str:
    """Alias do índice do tribunal pelo número único (J = ramo, TR = tribunal). Texto vazio se o tribunal não tem índice público (STF) ou se o número não mapeia."""
    d = re.sub(r"\D", "", numero or "")
    if len(d) != 20:
        return ""
    j, tr = d[13], int(d[14:16])
    if j == "3":
        return "stj" if tr == 0 else ""
    if j == "4":
        return f"trf{tr}" if 1 <= tr <= 6 else ""
    if j == "5":
        return "tst" if tr == 0 else (f"trt{tr}" if 1 <= tr <= 24 else "")
    if j == "6":
        return "tse" if tr == 0 else (f"tre-{_UFS[tr - 1]}" if 1 <= tr <= 27 else "")
    if j == "7":
        return "stm" if tr == 0 else ""
    if j == "8":
        if tr == 7:
            return "tjdft"   # o tribunal do Distrito Federal usa a sigla com T
        return f"tj{_UFS[tr - 1]}" if 1 <= tr <= 27 else ""
    if j == "9":
        return {13: "tjmmg", 21: "tjmrs", 26: "tjmsp"}.get(tr, "")
    return ""   # J=1 é o STF, que não tem índice público


def chave() -> str:
    return os.environ.get("STUDIO_DATAJUD_CHAVE", "").strip() or CHAVE_PADRAO


def _requisitar(alias: str, numero: str, urlopen=None) -> dict:
    corpo = json.dumps({"query": {"match": {"numeroProcesso": numero}}, "size": 10}).encode()
    req = urllib.request.Request(f"{BASE}/api_publica_{alias.replace('-', '_')}/_search", data=corpo, method="POST",
                                 headers={"Authorization": "APIKey " + chave(), "Content-Type": "application/json", "User-Agent": "StudioLibre-Miner/1.0"})
    try:
        with (urlopen or urllib.request.urlopen)(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as ex:
        if ex.code in (401, 403):
            raise djen.ErroDJEN("O DataJud recusou a chave de acesso. O CNJ pode ter trocado a chave pública.")
        if ex.code == 429:
            raise djen.ErroDJEN("O DataJud limitou as consultas.")
        raise djen.ErroDJEN(f"O DataJud respondeu com erro {ex.code}.")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise djen.ErroDJEN("Não foi possível falar com o DataJud agora.")


def _data(s: str):
    try:
        return datetime.strptime(str(s)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d")
        except ValueError:
            return None


def resumir(resposta: dict) -> dict:
    """Junta os resultados do processo (um por grau ou juizado): classe, órgão, assuntos e todos os movimentos, do mais novo ao mais antigo."""
    hits = ((resposta or {}).get("hits") or {}).get("hits") or []
    movs, classe, orgao, assuntos, tribunal, grau = [], "", "", [], "", ""
    for h in hits:
        s = h.get("_source") or {}
        classe = classe or str((s.get("classe") or {}).get("nome") or "")
        orgao = orgao or str((s.get("orgaoJulgador") or {}).get("nome") or "")
        tribunal = tribunal or str(s.get("tribunal") or "")
        grau = grau or str(s.get("grau") or "")
        for a in s.get("assuntos") or []:
            nome = str((a or {}).get("nome") or "")
            if nome and nome not in assuntos:
                assuntos.append(nome)
        for m in s.get("movimentos") or []:
            dt = _data((m or {}).get("dataHora"))
            if dt:
                movs.append({"quando": dt, "nome": str((m or {}).get("nome") or "Movimento")})
    movs.sort(key=lambda m: m["quando"], reverse=True)
    return {"encontrado": bool(hits), "classe": classe, "orgao": orgao, "assuntos": assuntos[:3], "tribunal": tribunal, "grau": grau, "movimentos": movs}


def _marca(numero: str) -> str:
    return "dj:" + numero


def alerta_andamento(numero: str, r: dict, novos: list) -> dict:
    topo = novos[0]
    significa, fazer, nivel = djen.classificar({"tipo": "", "documento": "", "classe": "", "texto": " ".join(m["nome"] for m in novos)})
    lista = "; ".join(f"{m['nome']} ({m['quando']:%d/%m/%Y})" for m in novos[:MAX_MOVIMENTOS_NO_ALERTA]) + ("…" if len(novos) > MAX_MOVIMENTOS_NO_ALERTA else "")
    onde = ", ".join(x for x in (r["tribunal"], r["orgao"]) if x)
    partes = [f"{len(novos)} andamento(s) novo(s) no processo {djen.mascara_cnj(numero)}" + (f" ({onde})" if onde else "") + f": {lista}.",
              (f"Classe: {r['classe']}. " if r["classe"] else "") + (f"Assunto: {', '.join(r['assuntos'])}." if r["assuntos"] else ""),
              significa, "O DataJud mostra capa e andamentos, com alguns dias de atraso e sem o texto da decisão; o prazo oficial vem da intimação no DJEN.", "O que fazer: " + fazer]
    return {"id": f"datajud:{numero}:{topo['quando']:%Y%m%d%H%M%S}", "titulo": f"Andamento em processo da Justiça ({r['tribunal'] or 'tribunal'})",
            "resumo": " ".join(p for p in partes if p), "nivel": "medio" if nivel == "medio" else "alto", "fonte": "justica"}


def alerta_inicio(numero: str, r: dict) -> dict:
    ult = r["movimentos"][0] if r["movimentos"] else None
    onde = ", ".join(x for x in (r["tribunal"], r["orgao"]) if x)
    txt = (f"Processo {djen.mascara_cnj(numero)}" + (f" ({onde})" if onde else "") + " encontrado no DataJud, e o acompanhamento começou. "
           + (f"Classe: {r['classe']}. " if r["classe"] else "") + (f"Assunto: {', '.join(r['assuntos'])}. " if r["assuntos"] else "")
           + (f"Último andamento: {ult['nome']} em {ult['quando']:%d/%m/%Y}. " if ult else "Ainda não há andamentos registrados. ")
           + "A partir de agora o Miner avisa os andamentos novos. O DataJud tem alguns dias de atraso; o prazo oficial vem da intimação no DJEN.")
    return {"id": f"datajud-inicio:{numero}", "titulo": f"Acompanhamento iniciado ({r['tribunal'] or 'tribunal'})", "resumo": txt, "nivel": "medio", "fonte": "justica"}


def alerta_ausente(numero: str, motivo: str) -> dict:
    return {"id": f"datajud-ausente:{numero}", "titulo": "Processo não encontrado no DataJud", "nivel": "medio", "fonte": "justica",
            "resumo": f"O processo {djen.mascara_cnj(numero)} não pôde ser acompanhado pelo DataJud: {motivo} Por isso, confira as intimações no DJEN (o Miner continua consultando) e, para andamentos, cadastre o processo no sistema Push do tribunal e no Domicílio Judicial Eletrônico."}


def executar(numeros: list, requisitar=None, dormir=None, publicar=None) -> dict:
    """Consulta cada processo e publica o início do acompanhamento, os andamentos novos e a ausência. Devolve {ok, novos, erros}."""
    requisitar = requisitar or _requisitar
    dormir = dormir or time.sleep
    publicar = publicar or djen._publicar
    novos, erros = 0, []
    if os.environ.get("STUDIO_MINER_DATAJUD", "1") == "0":
        return {"ok": True, "novos": 0, "erros": [], "desligado": True}
    for numero in numeros:
        alias = indice(numero)
        if not alias:
            if numero[13] == "1":
                m = "o STF não tem índice público no DataJud. Use o STF Push, que envia as movimentações por e-mail."
            else:
                m = "o tribunal deste número não tem índice público."
            novos += 1 if publicar(alerta_ausente(numero, m)).get("novo") else 0
            continue
        try:
            r = resumir(requisitar(alias, numero))
        except djen.ErroDJEN as ex:
            erros.append(str(ex))
            if "chave" in str(ex) or "limitou" in str(ex):
                break
            continue
        finally:
            dormir(PAUSA_S)
        if not r["encontrado"]:
            novos += 1 if publicar(alerta_ausente(numero, "o DataJud não tem registro público dele (pode ser sigiloso, muito recente ou do STF).")).get("novo") else 0
            continue
        visto = djen._ler(_marca(numero))
        ultimo = r["movimentos"][0]["quando"] if r["movimentos"] else None
        if not visto:
            novos += 1 if publicar(alerta_inicio(numero, r)).get("novo") else 0
        else:
            base = _data(visto)
            lista = [m for m in r["movimentos"] if base is None or m["quando"] > base]
            if lista:
                novos += 1 if publicar(alerta_andamento(numero, r, lista)).get("novo") else 0
        if ultimo:
            _gravar_marca(numero, ultimo.strftime("%Y-%m-%d %H:%M:%S"))
        elif not visto:
            _gravar_marca(numero, "1970-01-01 00:00:00")
    return {"ok": not erros, "novos": novos, "erros": erros}


def _gravar_marca(numero: str, valor: str) -> None:
    """Grava a marca do último andamento visto (chave livre em miner_config)."""
    djen._garantir_banco()
    with djen.banco._trava:
        con = djen.dados._con()
        try:
            con.execute("INSERT INTO miner_config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (_marca(numero), valor))
            con.commit()
        finally:
            con.close()
