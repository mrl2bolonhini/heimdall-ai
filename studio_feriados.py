#!/usr/bin/env python3
"""Calendário de dias úteis forenses em camadas, para a estimativa de prazos do Studio Miner (Cidadania).

Camadas, da mais certa para a mais local:
  1. nacional: feriados federais, carnaval, sexta-feira santa e Corpus Christi (calculados);
  2. recesso forense de 20/12 a 20/01 (art. 220 do CPC);
  3. estadual: feriados do estado do foro (UF lida do número do processo na Justiça Estadual, Eleitoral e Militar; nos demais ramos, a UF do município informado);
  4. municipal: feriados do município do foro (informado pela pessoa em Ajustes, por processo ou como padrão; o código do IBGE vem da API de localidades do IBGE);
  5. suspensões de prazo publicadas pelo tribunal, que a pessoa informa em Ajustes (portarias, instabilidade do sistema, ponto facultativo com suspensão).

Fonte dos feriados estaduais e municipais: conjunto de dados aberto joaopbini/feriados-brasil (licença MIT), um arquivo por ano e categoria, baixado
quando preciso e guardado em disco; sem rede, a estimativa avisa quais camadas ficaram de fora. A Recomendação CNJ 44/2020 pede que cada tribunal publique até
19/12 o calendário de feriados locais do ano seguinte; feriado local e suspensão de prazo precisam ser comprovados no ato do recurso (art. 1.003, § 6º, do CPC),
então o aviso sempre manda conferir o calendário do tribunal. Usa só a biblioteca padrão do Python.
Variáveis: STUDIO_FERIADOS (padrão 1; 0 usa só a camada nacional e o recesso), STUDIO_FERIADOS_URL (base dos arquivos de dados).
"""
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import studio_banco as banco

URL_DADOS = os.environ.get("STUDIO_FERIADOS_URL", "https://raw.githubusercontent.com/joaopbini/feriados-brasil/main/dados/feriados").rstrip("/")
URL_IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
UFS_ORDEM = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SE", "SP", "TO"]
# O código TR do número único segue a ordem alfabética das UFs na Justiça Estadual, Eleitoral e Militar (TJDFT é o 07, DF).
UFS_TR = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SE", "SP", "TO"]
UFS = set(UFS_ORDEM)
IDADE_MAXIMA = timedelta(days=30)   # os arquivos de dados são refeitos de tempos em tempos: depois de 30 dias, tenta baixar de novo (sem apagar o que já tem)
PAUSA_FALHA = timedelta(minutes=30)   # depois de uma falha de rede, não insiste na mesma fonte por este tempo
_FALHAS = {}


class ErroFeriados(Exception):
    pass


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower().strip()


# ---------- camada nacional ----------

def _pascoa(ano: int) -> date:
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def nacionais(ano: int) -> dict:
    """{data: nome} dos feriados nacionais e dos dias sem expediente forense em todo o país (a Consciência Negra é nacional desde 2024)."""
    fixos = {(1, 1): "Confraternização Universal", (4, 21): "Tiradentes", (5, 1): "Dia do Trabalho", (9, 7): "Independência", (10, 12): "Nossa Senhora Aparecida",
             (11, 2): "Finados", (11, 15): "Proclamação da República", (12, 25): "Natal"}
    if ano >= 2024:
        fixos[(11, 20)] = "Dia da Consciência Negra"
    f = {date(ano, m, d): n for (m, d), n in fixos.items()}
    p = _pascoa(ano)
    f.update({p - timedelta(days=48): "Carnaval", p - timedelta(days=47): "Carnaval", p - timedelta(days=2): "Sexta-feira Santa", p + timedelta(days=60): "Corpus Christi"})
    return f


def recesso(d: date) -> bool:
    return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 20)


# ---------- UF e município do foro ----------

def uf_do_processo(numero: str) -> str:
    """UF do foro pelo número único (J e TR), quando o ramo é estadual (8), eleitoral (6) ou militar estadual (9); vazio nos demais (federal e trabalhista cobrem vários estados)."""
    d = re.sub(r"\D", "", numero or "")
    if len(d) != 20:
        return ""
    j, tr = d[13], int(d[14:16])
    if j in ("8", "6") and 1 <= tr <= 27:
        return UFS_TR[tr - 1]
    if j == "9":
        return {13: "MG", 21: "RS", 26: "SP"}.get(tr, "")
    return ""


def partir_municipio(texto: str):
    """'São Paulo/SP' -> ('São Paulo', 'SP'). Levanta ErroFeriados se o formato não servir."""
    t = re.sub(r"\s+", " ", texto or "").strip()
    m = re.match(r"^(.{2,60}?)\s*[/,-]\s*([A-Za-z]{2})$", t)
    if not m or m.group(2).upper() not in UFS:
        raise ErroFeriados("Informe o município no formato Cidade/UF, por exemplo Campinas/SP.")
    return m.group(1).strip(), m.group(2).upper()


# ---------- dados em disco ----------

def pasta() -> Path:
    """Pasta global (não é por pessoa: os feriados são os mesmos para todos)."""
    p = Path(getattr(banco, "_RAIZ", banco.DB_DIR)) / "feriados"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _abrir(url: str, urlopen=None) -> str:
    if urlopen is None and datetime.now() - _FALHAS.get(url, datetime.min) < PAUSA_FALHA:
        raise ErroFeriados("fonte de feriados indisponível há pouco")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "StudioLibre-Miner/1.0"})
    try:
        with (urlopen or urllib.request.urlopen)(req, timeout=40) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as ex:
        _FALHAS[url] = datetime.now()
        raise ErroFeriados("sem acesso à fonte de feriados") from ex


def _lido(arq: Path):
    try:
        return json.loads(arq.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _recente(arq: Path) -> bool:
    try:
        return datetime.now() - datetime.fromtimestamp(arq.stat().st_mtime) < IDADE_MAXIMA
    except OSError:
        return False


def _data_br(s: str):
    try:
        return datetime.strptime(str(s)[:10], "%d/%m/%Y").date()
    except ValueError:
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _baixar_categoria(ano: int, categoria: str, urlopen=None) -> list:
    """Registros brutos de uma categoria e ano; tenta o ramo principal e o antigo (master)."""
    ultimo = None
    for url in (f"{URL_DADOS}/{categoria}/json/{ano}.json", URL_DADOS.replace("/main/", "/master/") + f"/{categoria}/json/{ano}.json"):
        try:
            dados = json.loads(_abrir(url, urlopen))
            if isinstance(dados, list):
                return dados
        except (ErroFeriados, ValueError) as ex:
            ultimo = ex
    raise ErroFeriados(str(ultimo or "fonte de feriados indisponível"))


def estaduais(ano: int, uf: str, urlopen=None) -> list:
    """[(data, nome)] dos feriados estaduais do ano. Levanta ErroFeriados se não houver dados nem em disco nem na rede."""
    arq = pasta() / f"estadual_{ano}.json"
    dados = _lido(arq) if _recente(arq) else None
    if dados is None:
        try:
            bruto = _baixar_categoria(ano, "estadual", urlopen)
            dados = [{"d": str(r.get("data", "")), "n": str(r.get("nome", "")), "u": str(r.get("uf", "")).upper()} for r in bruto if isinstance(r, dict)]
            arq.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
        except ErroFeriados:
            dados = _lido(arq)   # dado velho vale mais que nenhum
            if dados is None:
                raise
    return [(d, r["n"]) for r in dados if r["u"] == uf and (d := _data_br(r["d"])) and d.year == ano]


def municipais(ano: int, ibge: int, urlopen=None) -> list:
    arq = pasta() / f"municipal_{ano}.json"
    dados = _lido(arq) if _recente(arq) else None
    if dados is None:
        try:
            bruto = _baixar_categoria(ano, "municipal", urlopen)
            dados = {}
            for r in bruto:
                if isinstance(r, dict) and r.get("codigo_ibge"):
                    dados.setdefault(str(r["codigo_ibge"]), []).append([str(r.get("data", "")), str(r.get("nome", ""))])
            arq.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
        except ErroFeriados:
            dados = _lido(arq)
            if dados is None:
                raise
    return [(d, n) for ds, n in dados.get(str(ibge), []) if (d := _data_br(ds)) and d.year == ano]


def codigo_ibge(cidade: str, uf: str, urlopen=None) -> int:
    """Código do IBGE do município pelo nome e UF (API de localidades do IBGE, com cópia em disco)."""
    arq = pasta() / f"municipios_{uf}.json"
    lista = _lido(arq)
    if lista is None:
        try:
            bruto = json.loads(_abrir(URL_IBGE.format(uf=uf), urlopen))
            lista = [[int(m["id"]), str(m["nome"])] for m in bruto]
            arq.write_text(json.dumps(lista, ensure_ascii=False), "utf-8")
        except (ErroFeriados, ValueError, KeyError, TypeError) as ex:
            raise ErroFeriados("não foi possível consultar o código do município no IBGE") from ex
    alvo = _sem_acento(cidade)
    for cod, nome in lista:
        if _sem_acento(nome) == alvo:
            return cod
    raise ErroFeriados(f"o município {cidade}/{uf} não consta na lista do IBGE")


# ---------- suspensões informadas pela pessoa ----------

def ler_suspensoes(texto: str):
    """Linhas 'dd/mm/aaaa' ou 'dd/mm/aaaa a dd/mm/aaaa' seguidas de um motivo opcional -> [(inicio, fim, motivo)]. Levanta ErroFeriados na primeira linha inválida."""
    saida = []
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        m = re.match(r"^(\d{2}/\d{2}/\d{4})(?:\s*(?:a|até|ate|-)\s*(\d{2}/\d{2}/\d{4}))?\s*(.*)$", linha, re.I)
        ini = _data_br(m.group(1)) if m else None
        fim = _data_br(m.group(2)) if m and m.group(2) else ini
        if not (m and ini and fim and ini <= fim and (fim - ini).days <= 60):
            raise ErroFeriados(f"Suspensão inválida: {linha[:40]}. Use dd/mm/aaaa ou dd/mm/aaaa a dd/mm/aaaa, até 60 dias, com o motivo opcional.")
        saida.append((ini, fim, m.group(3).strip()[:60] or "suspensão de prazo"))
    return saida[:50]


# ---------- o calendário ----------

class Calendario:
    """Dias úteis do foro de um processo. Cada camada que não pôde ser carregada fica em `faltas`, para o aviso dizer a verdade."""

    def __init__(self, uf: str = "", cidade: str = "", ibge: int = 0, suspensoes=None, urlopen=None, rede: bool = True):
        self.uf, self.cidade, self.ibge = uf, cidade, ibge
        self.suspensoes = list(suspensoes or [])
        self.urlopen = urlopen
        self.rede = rede and os.environ.get("STUDIO_FERIADOS", "1") != "0"
        self.faltas = []
        self._anos = {}
        self._tentou = set()

    def _ano(self, ano: int) -> dict:
        if ano in self._anos:
            return self._anos[ano]
        mapa = {d: ("nacional", n) for d, n in nacionais(ano).items()}
        if self.rede and self.uf:
            try:
                for d, n in estaduais(ano, self.uf, self.urlopen):
                    mapa.setdefault(d, ("estadual", n))
            except ErroFeriados:
                self.faltas.append(f"feriados estaduais de {self.uf} em {ano}")
        if self.rede and self.ibge:
            try:
                for d, n in municipais(ano, self.ibge, self.urlopen):
                    mapa.setdefault(d, ("municipal", n))
            except ErroFeriados:
                self.faltas.append(f"feriados municipais de {self.cidade or self.ibge} em {ano}")
        for ini, fim, motivo in self.suspensoes:
            d = ini
            while d <= fim:
                if d.year == ano:
                    mapa.setdefault(d, ("suspensao", motivo))
                d += timedelta(days=1)
        self._anos[ano] = mapa
        return mapa

    def motivo(self, d: date):
        """(camada, nome) se o dia não é útil por feriado, suspensão ou recesso; None se é útil ou fim de semana comum."""
        if d.weekday() >= 5:
            return ("fim de semana", "")
        m = self._ano(d.year).get(d)
        if m:
            return m
        if recesso(d):
            return ("recesso", "Recesso forense (20/12 a 20/01)")
        return None

    def dia_util(self, d: date) -> bool:
        return self.motivo(d) is None

    def proximo_util(self, d: date) -> date:
        d += timedelta(days=1)
        while not self.dia_util(d):
            d += timedelta(days=1)
        return d

    def somar_uteis(self, d: date, n: int) -> date:
        for _ in range(n):
            d = self.proximo_util(d)
        return d

    def ajustar(self, d: date) -> date:
        while not self.dia_util(d):
            d += timedelta(days=1)
        return d

    def aplicados(self) -> str:
        """Frase para o aviso: o que foi considerado e o que ficou de fora."""
        camadas = ["feriados nacionais", "recesso forense de 20/12 a 20/01"]
        if self.uf and self.rede and not any("estaduais" in f for f in self.faltas):
            camadas.append(f"feriados estaduais de {self.uf}")
        if self.ibge and self.rede and not any("municipais" in f for f in self.faltas):
            camadas.append(f"feriados municipais de {self.cidade}")
        if self.suspensoes:
            camadas.append(f"{len(self.suspensoes)} suspensão(ões) de prazo informada(s)")
        txt = "Considerei " + ", ".join(camadas) + "."
        ausentes = []
        if not self.uf:
            ausentes.append("estaduais (a UF do foro não consta do número; informe o município do processo em Ajustes)" if not self.ibge else "estaduais")
        if not self.ibge:
            ausentes.append("municipais (o município do foro não foi informado)")
        if self.faltas:
            ausentes.append("os que não puderam ser carregados agora: " + "; ".join(sorted(set(self.faltas))))
        if ausentes:
            txt += " Não considerei: " + "; ".join(ausentes) + "."
        return txt


def nacional() -> Calendario:
    """Só a camada nacional e o recesso, sem rede."""
    return Calendario(rede=False)
