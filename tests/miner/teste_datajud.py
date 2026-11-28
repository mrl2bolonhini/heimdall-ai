#!/usr/bin/env python3
"""Testa os andamentos pelo DataJud: índice do tribunal pelo número, início do acompanhamento, andamento novo com significado, sem repetir, ausente, STF e chave recusada."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import tempfile
from datetime import date
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="datajud_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
import studio_banco as banco  # noqa: E402
import studio_datajud as dd  # noqa: E402
import studio_djen as dj  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:400]})"))
    if not ok:
        falhas += 1


def numero(seq, ano, j, tr, oooo):
    base = f"{seq:07d}{ano}{j}{tr:02d}{oooo:04d}"
    dv = 98 - (int(base[:7] + base[7:] + "00") % 97)
    return f"{base[:7]}{dv:02d}{base[7:]}"


TJSP, TRT2, TRF3, STF, TJDFT, TRE = numero(1, 2024, 8, 26, 100), numero(2, 2024, 5, 2, 1), numero(3, 2024, 4, 3, 6000), numero(4, 2024, 1, 0, 0), numero(5, 2024, 8, 7, 1), numero(6, 2024, 6, 26, 1)
confere("números de teste válidos", all(dj.numero_cnj_valido(n) for n in (TJSP, TRT2, TRF3, STF, TJDFT, TRE)))
confere("índices", [dd.indice(n) for n in (TJSP, TRT2, TRF3, STF, TJDFT, TRE)] == ["tjsp", "trt2", "trf3", "", "tjdft", "tre-sp"], [dd.indice(n) for n in (TJSP, TRT2, TRF3, STF, TJDFT, TRE)])
confere("superiores", dd.indice(numero(7, 2024, 3, 0, 1)) == "stj" and dd.indice(numero(8, 2024, 5, 0, 1)) == "tst")
confere("chave de fábrica e substituta", dd.chave() == dd.CHAVE_PADRAO and (os.environ.__setitem__("STUDIO_DATAJUD_CHAVE", "nova") or dd.chave() == "nova"))
del os.environ["STUDIO_DATAJUD_CHAVE"]


def resp(movs, orgao="2ª Vara Cível"):
    return {"hits": {"hits": [{"_source": {"numeroProcesso": "x", "tribunal": "TJSP", "grau": "G1", "classe": {"nome": "Procedimento Comum Cível"}, "orgaoJulgador": {"nome": orgao},
                                           "assuntos": [{"nome": "Indenização por Dano Moral"}], "movimentos": [{"nome": n, "dataHora": d} for n, d in movs]}}]}}


publicados = []
pub = lambda dado: publicados.append(dado) or {"novo": not any(p["id"] == dado["id"] for p in publicados[:-1])}   # noqa: E731
estado = {"r": resp([("Distribuição", "2024-03-01T10:00:00.000Z"), ("Petição", "2024-05-02T09:00:00.000Z")])}
chamadas = []


def falso(alias, num):
    chamadas.append((alias, num))
    return estado["r"]


dj.salvar("", "", "", TJSP)
r = dd.executar([TJSP], falso, lambda s: None, pub)
confere("primeira vez: acompanhamento iniciado sem andamento antigo", r["ok"] and [p["id"] for p in publicados] == [f"datajud-inicio:{TJSP}"] and chamadas == [("tjsp", TJSP)], (r, publicados))
ini = publicados[0]["resumo"]
confere("início traz classe, assunto, último andamento e o limite da fonte", "Procedimento Comum Cível" in ini and "Indenização" in ini and "Petição em 02/05/2024" in ini and "DJEN" in ini, ini)
r = dd.executar([TJSP], falso, lambda s: None, pub)
confere("sem andamento novo: nada", len(publicados) == 1, publicados)
estado["r"] = resp([("Distribuição", "2024-03-01T10:00:00.000Z"), ("Petição", "2024-05-02T09:00:00.000Z"), ("Audiência designada", "2024-06-10T14:30:00.000Z"), ("Conclusos para despacho", "2024-06-11T08:00:00.000Z")])
r = dd.executar([TJSP], falso, lambda s: None, pub)
a = publicados[-1]
confere("andamento novo: um aviso com os dois movimentos", a["id"].startswith(f"datajud:{TJSP}:") and "2 andamento(s) novo(s)" in a["resumo"] and "Audiência designada (10/06/2024)" in a["resumo"], a)
confere("com significado e o que fazer; fonte e título sem dados", "audiência" in a["resumo"].lower() and "O que fazer:" in a["resumo"] and a["fonte"] == "justica" and TJSP not in a["titulo"], a)
n = len(publicados)
dd.executar([TJSP], falso, lambda s: None, pub)
confere("não repete o aviso", len(publicados) == n)

publicados.clear()
dd.executar([STF], falso, lambda s: None, pub)
confere("STF: aviso indica o STF Push", len(publicados) == 1 and "STF Push" in publicados[0]["resumo"] and "DJEN" in publicados[0]["resumo"], publicados)
estado["r"] = {"hits": {"hits": []}}
publicados.clear()
dd.executar([TRT2], falso, lambda s: None, pub)
confere("não encontrado: aviso com alternativas", len(publicados) == 1 and "Push do tribunal" in publicados[0]["resumo"] and "sigiloso" in publicados[0]["resumo"], publicados)


def recusa(alias, num):
    raise dj.ErroDJEN("O DataJud recusou a chave de acesso. O CNJ pode ter trocado a chave pública.")


r = dd.executar([TRF3, TJDFT], recusa, lambda s: None, pub)
confere("chave recusada interrompe e explica", not r["ok"] and "chave" in r["erros"][0] and r["erros"] == ["O DataJud recusou a chave de acesso. O CNJ pode ter trocado a chave pública."], r)
pausas = []
dd.executar([TRT2, TRF3], lambda a, n: {"hits": {"hits": []}}, pausas.append, pub)
confere("uma pausa por consulta (limite de 120 por minuto)", len(pausas) == 2 and all(p >= 1 for p in pausas), pausas)
os.environ["STUDIO_MINER_DATAJUD"] = "0"
confere("interruptor desliga", dd.executar([TJSP], falso, lambda s: None, pub).get("desligado"))
del os.environ["STUDIO_MINER_DATAJUD"]

# integrado ao coletor do dia: DJEN sem itens + DataJud do processo configurado
dj.salvar("", "", "", TRT2)
publicados.clear()
estado["r"] = resp([("Petição", "2024-05-02T09:00:00.000Z")])
r = dj.executar(hoje=date(2026, 11, 27), requisitar=lambda p: {"count": 0, "items": []}, dormir=lambda s: None, publicar=pub, requisitar_datajud=lambda a, n: estado["r"])
confere("consulta do dia inclui os andamentos", r["ok"] and "Andamentos: 1 aviso(s) novo(s)." in r["mensagem"] and any(p["id"].startswith("datajud-inicio:") for p in publicados), (r, publicados))
# ---- leitura semanal da chave na wiki do CNJ ----
import io
import json
import urllib.error
from datetime import datetime, timedelta


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def wiki(chave_nova, robots="User-agent: *\nAllow: /\n"):
    def f(req, timeout=0):
        u = req.full_url
        if u.endswith("/robots.txt"):
            return Resp(robots.encode())
        if u == dd.PAGINA_CHAVE:
            return Resp(f"<html><body><p>Utilize o formato</p><pre>Authorization: APIKey {chave_nova}</pre></body></html>".encode())
        raise urllib.error.URLError("404")
    return f


os.environ.pop("STUDIO_DATAJUD_CHAVE", None)
confere("chave de fábrica é a vigente de 27/11/2026", dd.CHAVE_PADRAO.startswith("cDZHYzlZa0JadVREZDJCendQbXY6") and dd.chave() == dd.CHAVE_PADRAO)
NOVA = "ZZZZabcdefghijklmnopqrstuvwxyz0123456789=="
r = dd.atualizar_chave(wiki(NOVA), agora=datetime(2026, 12, 1, 8))
confere("lê a chave da wiki e guarda", r["ok"] and r["mudou"] and dd.chave() == NOVA, r)
confere("não relê dentro da semana", dd.atualizar_chave(wiki("OUTRA" * 8), agora=datetime(2026, 12, 5, 8))["mudou"] is False and dd.chave() == NOVA)
confere("relê depois da semana", dd.atualizar_chave(wiki("OUTRA" * 8), agora=datetime(2026, 12, 9, 8))["mudou"] and dd.chave() == "OUTRA" * 8)
confere("forçada não passa de uma leitura por hora", dd.atualizar_chave(wiki(NOVA), forcar=True, agora=datetime(2026, 12, 9, 8, 30))["mudou"] is False)
confere("forçada depois de uma hora lê", dd.atualizar_chave(wiki(NOVA), forcar=True, agora=datetime(2026, 12, 9, 10))["mudou"] and dd.chave() == NOVA)
os.environ["STUDIO_DATAJUD_CHAVE"] = "do-env"
confere("variável de ambiente vence a chave lida", dd.chave() == "do-env")
del os.environ["STUDIO_DATAJUD_CHAVE"]
bloq = dd.atualizar_chave(wiki("BLOQ" * 8, "User-agent: *\nDisallow: /\n"), forcar=True, agora=datetime(2027, 1, 1))
confere("respeita o robots.txt", not bloq["ok"] and dd.chave() == NOVA, bloq)


def sem_chave(req, timeout=0):
    if req.full_url.endswith("/robots.txt"):
        raise urllib.error.URLError("sem robots")
    return Resp(b"<html>sem a chave aqui</html>")


confere("página sem a chave não altera", not dd.atualizar_chave(sem_chave, forcar=True, agora=datetime(2027, 2, 1))["ok"] and dd.chave() == NOVA)


def fora(req, timeout=0):
    raise urllib.error.URLError("sem rede")


confere("sem rede não altera", not dd.atualizar_chave(fora, forcar=True, agora=datetime(2027, 3, 1))["ok"] and dd.chave() == NOVA)
confere("robots.txt ausente permite a leitura", dd._permitido(dd.PAGINA_CHAVE, sem_chave))

# chave recusada (401): relê a wiki, usa a nova e tenta uma vez
os.environ.pop("STUDIO_DATAJUD_CHAVE", None)
usadas = []


def api(req, timeout=0):
    usadas.append(req.get_header("Authorization"))
    if req.get_header("Authorization") == "APIKey " + dd.CHAVE_PADRAO:
        raise urllib.error.HTTPError(req.full_url, 401, "x", {}, None)
    return Resp(json.dumps({"hits": {"hits": []}}).encode())


arq = dd._arquivo_chave()
arq.unlink()
dd.atualizar_chave(wiki("NOVISSIMA" * 4), forcar=True, agora=datetime(2020, 1, 1))   # grava uma leitura antiga
arq.write_text(json.dumps({"chave": dd.CHAVE_PADRAO, "lida_em": "2020-01-01T00:00:00"}))
r = dd._requisitar("tjsp", TJSP, api, urlopen_wiki=wiki("NOVISSIMA" * 4))
confere("401 renova a chave e repete uma vez", len(usadas) == 2 and usadas[1] == "APIKey " + "NOVISSIMA" * 4 and r == {"hits": {"hits": []}}, usadas)

print("\nFALHAS:", falhas)
_sys.exit(1 if falhas else 0)
