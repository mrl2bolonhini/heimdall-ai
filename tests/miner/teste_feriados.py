#!/usr/bin/env python3
"""Testa o calendário forense em camadas: nacional, recesso, estadual, municipal, suspensões informadas, falta de rede e o aviso de prazo."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import json
import os
import tempfile
import urllib.error
from datetime import date, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="feriados_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
os.environ.pop("STUDIO_FERIADOS", None)
import studio_banco as banco  # noqa: E402
import studio_djen as dj  # noqa: E402
import studio_feriados as fe  # noqa: E402
import studio_miner_dados as d  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:400]})"))
    if not ok:
        falhas += 1


def cnj(seq, ano, j, tr, origem):
    base = f"{seq:07d}{ano}{j}{tr:02d}{origem:04d}"
    return f"{seq:07d}{98 - (int(base[:7] + base[7:] + '00') % 97):02d}{base[7:]}"


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


CHAMADAS = []


def rede_ok(req, timeout=0):
    url = req.full_url
    CHAMADAS.append(url)
    if "/estadual/json/2026.json" in url:
        return Resp(json.dumps([{"data": "09/07/2026", "nome": "Revolução Constitucionalista", "tipo": "ESTADUAL", "uf": "SP", "codigo_ibge": None},
                                {"data": "02/07/2026", "nome": "Independência da Bahia", "tipo": "ESTADUAL", "uf": "BA", "codigo_ibge": None}]).encode())
    if "/municipal/json/2026.json" in url:
        return Resp(json.dumps([{"data": "14/07/2026", "nome": "Aniversário (teste)", "tipo": "MUNICIPAL", "uf": "SP", "codigo_ibge": 3509502},
                                {"data": "15/07/2026", "nome": "Outro município", "tipo": "MUNICIPAL", "uf": "SP", "codigo_ibge": 3550308}]).encode())
    if "localidades/estados/SP/municipios" in url:
        return Resp(json.dumps([{"id": 3509502, "nome": "Campinas"}, {"id": 3550308, "nome": "São Paulo"}]).encode())
    raise urllib.error.URLError("404")


def sem_rede(req, timeout=0):
    raise urllib.error.URLError("sem rede")


# nacional e recesso
n24, n23 = fe.nacionais(2024), fe.nacionais(2023)
confere("Consciência Negra é nacional desde 2024", date(2024, 11, 20) in n24 and date(2023, 11, 20) not in n23)
confere("carnaval, sexta santa e Corpus Christi", date(2026, 2, 17) in fe.nacionais(2026) and date(2026, 4, 3) in fe.nacionais(2026) and date(2026, 6, 4) in fe.nacionais(2026))
confere("recesso", fe.recesso(date(2026, 12, 20)) and fe.recesso(date(2027, 1, 20)) and not fe.recesso(date(2027, 1, 21)))

# UF do foro
confere("UF pelo número: TJSP", fe.uf_do_processo(cnj(1, 2025, 8, 26, 100)) == "SP")
confere("UF pelo número: TJDFT", fe.uf_do_processo(cnj(1, 2025, 8, 7, 1)) == "DF")
confere("UF pelo número: TRT não tem UF única", fe.uf_do_processo(cnj(1, 2025, 5, 2, 1)) == "")
confere("UF pelo número: TJMMG", fe.uf_do_processo(cnj(1, 2025, 9, 13, 1)) == "MG")

# município
confere("município com acento", fe.partir_municipio("São Paulo/SP") == ("São Paulo", "SP"))
try:
    fe.partir_municipio("Campinas")
    confere("município sem UF recusado", False)
except fe.ErroFeriados:
    confere("município sem UF recusado", True)
confere("código IBGE sem acento", fe.codigo_ibge("sao paulo", "SP", rede_ok) == 3550308)
try:
    fe.codigo_ibge("Inexistente", "SP", rede_ok)
    confere("município fora da lista", False)
except fe.ErroFeriados:
    confere("município fora da lista", True)

# suspensões
s = fe.ler_suspensoes("20/04/2026 portaria 12\n05/05/2026 a 07/05/2026 instabilidade do sistema")
confere("suspensões lidas", len(s) == 2 and s[1][0] == date(2026, 5, 5) and s[1][1] == date(2026, 5, 7) and s[1][2].startswith("instab"), s)
for ruim in ("amanhã", "10/05/2026 a 01/05/2026", "01/01/2026 a 01/06/2026"):
    try:
        fe.ler_suspensoes(ruim)
        confere("suspensão inválida recusada: " + ruim, False)
    except fe.ErroFeriados:
        confere("suspensão inválida recusada: " + ruim, True)

# camadas
cal = fe.Calendario(uf="SP", cidade="Campinas", ibge=3509502, suspensoes=s, urlopen=rede_ok)
confere("estadual SP vale", cal.motivo(date(2026, 7, 9)) == ("estadual", "Revolução Constitucionalista"))
confere("estadual de outra UF não vale", cal.dia_util(date(2026, 7, 2)))
confere("municipal do município vale", cal.motivo(date(2026, 7, 14))[0] == "municipal")
confere("municipal de outro município não vale", cal.dia_util(date(2026, 7, 15)))
confere("suspensão informada vale", cal.motivo(date(2026, 5, 6))[0] == "suspensao" and cal.motivo(date(2026, 4, 20))[0] == "suspensao")
confere("nacional continua valendo", cal.motivo(date(2026, 9, 7))[0] == "nacional")
confere("aplicados cita todas as camadas", all(t in cal.aplicados() for t in ("nacionais", "estaduais de SP", "municipais de Campinas", "suspensão")), cal.aplicados())
antes = len(CHAMADAS)
cal.motivo(date(2026, 7, 20))
confere("não baixa de novo no mesmo ano", len(CHAMADAS) == antes)
cal2 = fe.Calendario(uf="SP", cidade="Campinas", ibge=3509502, urlopen=rede_ok)
cal2.motivo(date(2026, 7, 9))
confere("segunda instância usa o disco", len([u for u in CHAMADAS if "estadual" in u]) == 1, CHAMADAS)

# prazo com e sem as camadas locais
disp = date(2026, 7, 6)   # segunda
base = dj.prazo_do_ato(disp, "no prazo de 5 dias")
local = dj.prazo_do_ato(disp, "no prazo de 5 dias", fe.Calendario(uf="SP", cidade="Campinas", ibge=3509502, urlopen=rede_ok))
confere("feriados estadual e municipal adiam o fim do prazo", local[2] == base[2] + timedelta(days=2), (base, local))

# sem rede: usa o que tem e diz o que faltou
os.environ["STUDIO_DB_DIR"] = str(TMP / "db2")
banco.DB_DIR = Path(os.environ["STUDIO_DB_DIR"])
banco._RAIZ = banco.DB_DIR
fe._FALHAS.clear()
off = fe.Calendario(uf="RJ", cidade="Niterói", ibge=3303302, urlopen=sem_rede)
off.motivo(date(2026, 7, 9))
txt = off.aplicados()
confere("sem rede: diz o que não considerou", "Não considerei" in txt and "estaduais de RJ" in txt and "municipais de Niterói" in txt, txt)
sem_local = fe.Calendario(rede=False).aplicados()
confere("sem município: pede para informar", "município do foro não foi informado" in sem_local, sem_local)

# alerta com o aviso do CPC e do calendário do tribunal
it = dj.normalizar({"id": 1, "numero_processo": cnj(1, 2025, 8, 26, 100), "data_disponibilizacao": "2026-07-06", "siglaTribunal": "TJSP", "tipoComunicacao": "Intimação", "texto": "Manifeste-se no prazo de 5 dias."}, "oab")
a = dj.alerta(it, date(2026, 7, 6), fe.Calendario(uf="SP", cidade="Campinas", ibge=3509502, urlopen=rede_ok))
confere("alerta cita calendários e prova do feriado local", "1.003" in a["resumo"] and "Recomendação CNJ 44/2020" in a["resumo"] and "municipais de Campinas" in a["resumo"], a["resumo"])

# configuração: município padrão, por processo e suspensões
os.environ["STUDIO_DB_DIR"] = str(TMP / "db3")
banco.DB_DIR = Path(os.environ["STUDIO_DB_DIR"])
banco._RAIZ = banco.DB_DIR
banco.iniciar()
p1, p2 = cnj(1, 2025, 8, 26, 100), cnj(2, 2025, 5, 15, 200)
dj.salvar("", "", "", f"{p1}\n{p2} @ Campinas/SP", "São Paulo/SP", "20/04/2026 portaria")
c = dj.configuracao()
confere("município padrão salvo", c["municipio"] == "São Paulo/SP")
confere("município por processo salvo", c["proc_municipios"] == {p2: "Campinas/SP"}, c["proc_municipios"])
confere("suspensões salvas", c["suspensoes"] == "20/04/2026 portaria")
cache = {}
c1 = dj.calendario_do(p1, c, rede_ok, True, cache)
c2 = dj.calendario_do(p2, c, rede_ok, True, cache)
confere("processo estadual usa UF do número e município padrão", c1.uf == "SP" and c1.ibge == 3550308 and len(c1.suspensoes) == 1)
confere("processo trabalhista usa UF e município informados", c2.uf == "SP" and c2.ibge == 3509502)
for ruim in ("Campinas", "Campinas/XX"):
    try:
        dj.salvar("", "", "", p1, ruim, "")
        confere("município inválido recusado: " + ruim, False)
    except d.ErroMiner:
        confere("município inválido recusado: " + ruim, True)
try:
    dj.salvar("", "", "", p1, "", "ontem")
    confere("suspensão inválida recusada ao salvar", False)
except d.ErroMiner:
    confere("suspensão inválida recusada ao salvar", True)
confere("configuração anterior preservada após erro", dj.configuracao()["municipio"] == "São Paulo/SP")
dj.salvar("", "", "", p1)   # sem os campos novos, nada muda neles
confere("campos omitidos não são apagados", dj.configuracao()["municipio"] == "São Paulo/SP")

# interruptor
os.environ["STUDIO_FERIADOS"] = "0"
confere("interruptor usa só a camada nacional", fe.Calendario(uf="SP", ibge=3509502, urlopen=rede_ok).rede is False)

print("\nFALHAS:", falhas)
_sys.exit(1 if falhas else 0)
