#!/usr/bin/env python3
"""Base das fontes da área Cidadania do Studio Miner (além do DJEN e do DataJud): configuração por pessoa, HTTP educado, cofre de segredos, rodada diária.

Cada fonte é um módulo com CHAVE, ROTULO, INTERVALO, `configurado(cfg)`, `executar(c)` (c é um Contexto), `formulario(csrf)` e `salvar(campos)`.
A rodada percorre o dono e cada convidado (cada um com os próprios dados: recursos iguais para todos), respeita o intervalo de cada fonte, nunca deixa a
falha de uma fonte ou de uma pessoa interromper as outras e avisa quando uma fonte falha três vezes seguidas.

Cuidados: um intervalo mínimo entre chamadas ao mesmo servidor, User-Agent identificado, robots.txt respeitado nas páginas que não têm API, nada de captcha
nem de login de terceiros; segredos (login do INLABS, chave do Portal da Transparência, credencial do MNI) ficam cifrados por pessoa (AES-GCM, permissão 600)
e nunca aparecem em tela, alerta ou registro. Usa a biblioteca padrão e, só para o cofre, `cryptography`.
Variáveis: STUDIO_CIDADANIA (padrão 1; 0 desliga a rodada), STUDIO_CIDADANIA_<CHAVE> (0 desliga uma fonte).
"""
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import studio_banco as banco
import studio_djen as djen
import studio_miner_dados as dados
import studio_pessoas as pessoas

UA = "StudioLibre-Miner/1.0"
PAUSA_HOST_S = 1.0
ESPERA_TENTATIVA = timedelta(hours=2)
HORA_INICIAL = 6
MAX_PALAVRAS = 30
LIMITE_PADRAO = 5_000_000
_ULTIMO_ACESSO = {}
_ROBOTS = {}
_TRAVA_HOST = threading.Lock()


class ErroFonte(Exception):
    """Uma fonte falhou (rede, bloqueio, formato inesperado)."""


# ---------- configuração por pessoa ----------

def cfg(fonte: str) -> dict:
    try:
        r = json.loads(djen._ler("cfg_" + fonte) or "{}")
        return r if isinstance(r, dict) else {}
    except ValueError:
        return {}


def salvar_cfg(fonte: str, valores: dict) -> None:
    djen._gravar(**{"cfg_" + fonte: json.dumps(valores, ensure_ascii=False)})


def sem_acento(s: str) -> str:
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def lista(texto: str, minimo: int = 2, maximo_item: int = 80, maximo: int = MAX_PALAVRAS, o_que: str = "palavras-chave") -> list:
    """Linhas, vírgulas ou ponto e vírgula -> lista sem repetição (sem distinguir caixa nem acento). Levanta ErroMiner se passar do limite."""
    saida, vistos = [], set()
    for t in re.split(r"[\n;,]+", texto or ""):
        t = re.sub(r"\s+", " ", t).strip()
        if not t:
            continue
        if not (minimo <= len(t) <= maximo_item):
            raise dados.ErroMiner(f"Cada item de {o_que} deve ter de {minimo} a {maximo_item} caracteres: {t[:30]}.")
        if sem_acento(t) not in vistos:
            vistos.add(sem_acento(t))
            saida.append(t)
    if len(saida) > maximo:
        raise dados.ErroMiner(f"Use no máximo {maximo} itens de {o_que}.")
    return saida


def contem(texto: str, palavra: str) -> bool:
    """A palavra ou expressão aparece no texto, sem distinguir caixa nem acento e só como palavra inteira."""
    return re.search(r"(?<![a-z0-9])" + re.escape(sem_acento(palavra)) + r"(?![a-z0-9])", sem_acento(texto)) is not None


def achadas(texto: str, palavras: list) -> list:
    return [p for p in palavras if contem(texto, p)]


def trecho(texto: str, palavra: str, raio: int = 140) -> str:
    """Pedaço do texto em volta da primeira ocorrência (o alerta guarda só isso: o texto inteiro pode ter dados de terceiros)."""
    t = re.sub(r"\s+", " ", texto or "")
    m = re.search(r"(?<![a-z0-9])" + re.escape(sem_acento(palavra)) + r"(?![a-z0-9])", sem_acento(t))
    if not m:
        return t[: 2 * raio]
    i = m.start()
    return ("…" if i > raio else "") + t[max(0, i - raio): i + len(palavra) + raio].strip() + ("…" if i + len(palavra) + raio < len(t) else "")


def limpo(t, n: int = 400) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip()[:n]


def data_br(d: date) -> str:
    return f"{d:%d/%m/%Y}"


def ler_data(s: str):
    try:
        return datetime.strptime((s or "").strip()[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def hash_curto(*partes) -> str:
    return hashlib.sha1("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:16]


# ---------- HTTP educado ----------

def _host_publico(host: str) -> bool:
    """Falso se o nome aponta para endereço local, privado ou reservado (a pessoa informa endereços; o servidor não pode ser levado a consultar a rede interna)."""
    if re.fullmatch(r"[0-9.:\[\]]+", host or "") or "." not in (host or "") or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        return all(ipaddress.ip_address(i[4][0]).is_global for i in socket.getaddrinfo(host, None))
    except socket.gaierror:
        return True   # sem resolução agora (rede fora do ar): a consulta falha sozinha


def validar_url(url: str, sufixos: tuple = None) -> str:
    """Endereço https de servidor público, opcionalmente só de certos domínios. Levanta ErroMiner."""
    p = urllib.parse.urlsplit((url or "").strip())
    host = (p.hostname or "").lower()
    if p.scheme != "https" or not host or "@" in p.netloc or p.port not in (None, 443) or not _host_publico(host):
        raise dados.ErroMiner("Informe um endereço https de um site público, como https://exemplo.gov.br/pagina.")
    if sufixos and not any(host == s or host.endswith("." + s) for s in sufixos):
        raise dados.ErroMiner("O endereço deve ser de um dos domínios aceitos para esta fonte: " + ", ".join(sufixos) + ".")
    return p.geturl().rstrip("/")


def _pausa(host: str, pausa: float, dormir=None) -> None:
    with _TRAVA_HOST:
        agora = time.monotonic()
        alvo = max(agora, _ULTIMO_ACESSO.get(host, 0) + pausa)
        _ULTIMO_ACESSO[host] = alvo
    if alvo > agora:
        (dormir or time.sleep)(alvo - agora)


_TRAVA_COFRE = threading.Lock()


class _RedirecionarSeguro(urllib.request.HTTPRedirectHandler):
    """Segue redirecionamentos só para https de servidores públicos, revalidando a cada salto."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = urllib.parse.urlsplit(newurl)
        if p.scheme != "https" or (p.port not in (None, 443)) or not _host_publico(p.hostname or ""):
            raise urllib.error.URLError("redirecionamento para endereço não permitido")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _cabecalhos(h) -> dict:
    saida = {k: v for k, v in (h.items() if h else [])}
    if h is not None and hasattr(h, "get_all"):
        saida["_cookies"] = [c.split(";")[0] for c in (h.get_all("Set-Cookie") or [])]
    return saida


def http(url: str, cab: dict = None, corpo: bytes = None, metodo: str = None, urlopen=None, pausa: float = PAUSA_HOST_S, limite: int = LIMITE_PADRAO,
         timeout: int = 40, dormir=None, nome: str = "A fonte", seguir: bool = True) -> tuple:
    """(status, bytes, cabeçalhos). Só https (http só para o teste). Com seguir=False, um redirecionamento volta como resposta (para ler o cookie do login).
    Levanta ErroFonte com mensagem para o usuário."""
    partes = urllib.parse.urlsplit(url)
    if partes.scheme != "https" and not (urlopen and partes.scheme == "http"):
        raise ErroFonte(f"{nome} precisa de um endereço https.")
    if urlopen is None:
        if not _host_publico(partes.hostname or ""):
            raise ErroFonte(f"{nome} aponta para um endereço não público e foi bloqueada.")
        _pausa(partes.netloc, pausa, dormir)
    req = urllib.request.Request(url, data=corpo, method=metodo, headers={"User-Agent": UA, "Accept": "*/*", **(cab or {})})
    abrir = urlopen or urllib.request.build_opener(_RedirecionarSeguro if seguir else _SemRedirecionar).open
    try:
        with abrir(req, timeout=timeout) as r:
            return getattr(r, "status", 200), r.read(limite), _cabecalhos(getattr(r, "headers", None))
    except urllib.error.HTTPError as ex:
        if 300 <= ex.code < 400 and not seguir:
            return ex.code, b"", _cabecalhos(ex.headers)
        if ex.code == 429:
            raise ErroFonte(f"{nome} limitou as consultas. A próxima tentativa será na rodada seguinte.")
        if ex.code in (401, 403):
            raise ErroFonte(f"{nome} recusou o acesso (confira o login ou a chave, ou o bloqueio fora do Brasil).")
        raise ErroFonte(f"{nome} respondeu com erro {ex.code}.")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ErroFonte(f"Não foi possível falar com {nome} agora.")


def json_de(url: str, cab: dict = None, **kw):
    _, corpo, _ = http(url, {"Accept": "application/json", **(cab or {})}, **kw)
    try:
        return json.loads(corpo.decode("utf-8", "replace") or "{}")
    except ValueError:
        raise ErroFonte(f"{kw.get('nome', 'A fonte')} respondeu num formato inesperado.")


def robots_permite(url: str, urlopen=None) -> bool:
    """robots.txt do servidor (guardado por 6 horas). Sem robots.txt legível, a leitura é permitida."""
    partes = urllib.parse.urlsplit(url)
    base = f"{partes.scheme}://{partes.netloc}"
    agora = time.time()
    rp, quando = _ROBOTS.get(base, (None, 0))
    if rp is None or agora - quando > 6 * 3600:
        rp = urllib.robotparser.RobotFileParser()
        try:
            _, corpo, _ = http(base + "/robots.txt", urlopen=urlopen, limite=200_000, timeout=20, pausa=0.2)
            rp.parse(corpo.decode("utf-8", "replace").splitlines())
        except ErroFonte:
            rp.parse(["User-agent: *", "Allow: /"])
        _ROBOTS[base] = (rp, agora)
    return rp.can_fetch("StudioLibre-Miner", url)


def texto_da_pagina(url: str, urlopen=None, nome: str = "A página") -> str:
    """Texto de uma página HTML, feed XML ou PDF (PDF só com pdftotext instalado), respeitando o robots.txt."""
    if not robots_permite(url, urlopen):
        raise ErroFonte(f"{nome} não permite a leitura automática (robots.txt).")
    _, corpo, cab = http(url, urlopen=urlopen, nome=nome, limite=8_000_000)
    tipo = str({k.lower(): v for k, v in cab.items()}.get("content-type", "")).lower()
    if corpo[:5] == b"%PDF-" or "pdf" in tipo:
        exe = shutil.which("pdftotext")
        if not exe:
            raise ErroFonte(f"{nome} é um PDF e não pôde ser lido agora.")
        try:
            r = subprocess.run([exe, "-layout", "-", "-"], input=corpo, capture_output=True, timeout=60, check=True)
        except (subprocess.SubprocessError, OSError):
            raise ErroFonte(f"Não foi possível ler o PDF de {nome}.")
        return r.stdout.decode("utf-8", "replace")
    t = corpo.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t.replace("&nbsp;", " ").replace("&amp;", "&")).strip()


# ---------- cofre de segredos por pessoa ----------

def _aead():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise dados.ErroMiner("Não foi possível guardar o login agora. Tente novamente mais tarde.") from None
    segredo = os.environ.get("STUDIO_NUVEM_CHAVE") or os.environ.get("STUDIO_PAPERLESS_SECRET", "")
    if not segredo:
        raise dados.ErroMiner("Não foi possível guardar o login agora. Tente novamente mais tarde.")
    return AESGCM(hashlib.sha256(b"studio-miner-cofre-v1\0" + segredo.encode()).digest())


def _arq_cofre() -> Path:
    return Path(banco.pasta_em_uso()) / "miner_segredos.bin"


def _cofre() -> dict:
    f = _arq_cofre()
    if not f.is_file():
        return {}
    try:
        b = f.read_bytes()
        return json.loads(_aead().decrypt(b[:12], b[12:], b"miner"))
    except dados.ErroMiner:
        raise
    except Exception:  # noqa: BLE001
        raise dados.ErroMiner("Não foi possível ler o cofre desta pessoa. Informe os dados de novo.") from None


def segredo(nome: str) -> str:
    return str(_cofre().get(nome, ""))


def guardar_segredos(novos: dict) -> None:
    """Grava os pares informados (valor vazio apaga). Cifrado, permissão 600."""
    with _TRAVA_COFRE:
        _guardar(novos)


def _guardar(novos: dict) -> None:
    atual = _cofre()
    for k, v in novos.items():
        if v:
            atual[k] = v
        else:
            atual.pop(k, None)
    f = _arq_cofre()
    f.parent.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_bytes(12)
    tmp = f.with_suffix(".tmp")
    tmp.write_bytes(nonce + _aead().encrypt(nonce, json.dumps(atual).encode(), b"miner"))
    os.chmod(tmp, 0o600)
    tmp.replace(f)


def tem_segredo(nome: str) -> bool:
    try:
        return bool(segredo(nome))
    except dados.ErroMiner:
        return False


# ---------- rodada ----------

@dataclass
class Contexto:
    hoje: date = field(default_factory=date.today)
    publicar: object = None
    urlopen: object = None
    dormir: object = None
    forcar: bool = False

    def avisar(self, dado: dict) -> bool:
        r = (self.publicar or djen._publicar)(dado)
        return bool(r.get("novo"))


def fontes() -> list:
    import studio_agendamentos
    import studio_certidoes
    import studio_diarios
    import studio_dou
    import studio_legislacao
    import studio_licitacoes
    import studio_mni
    return [studio_certidoes, studio_dou, studio_legislacao, studio_licitacoes, studio_diarios, studio_agendamentos, studio_mni]


def ligada(mod) -> bool:
    return os.environ.get("STUDIO_CIDADANIA", "1") != "0" and os.environ.get("STUDIO_CIDADANIA_" + mod.CHAVE.upper(), "1") != "0"


def _ler(chave, padrao=""):
    return djen._ler("cid_" + chave, padrao)


def _gravar(**kw):
    djen._gravar(**{"cid_" + k: v for k, v in kw.items()})


def devida(mod, agora: datetime = None) -> bool:
    agora = agora or datetime.now()
    if not ligada(mod) or not mod.configurado(cfg(mod.CHAVE)) or agora.hour < HORA_INICIAL:
        return False
    try:
        if agora - datetime.fromisoformat(_ler(mod.CHAVE + "_tentativa")) < ESPERA_TENTATIVA:
            return False
    except ValueError:
        pass
    try:
        return agora - datetime.fromisoformat(_ler(mod.CHAVE + "_ultimo")) >= mod.INTERVALO - timedelta(hours=1)
    except ValueError:
        return True


def executar_fonte(mod, contexto: Contexto = None) -> dict:
    """Roda uma fonte para a pessoa atual, guarda o estado e avisa quando ela falha três vezes seguidas."""
    c = contexto or Contexto()
    if not ligada(mod):
        return {"ok": False, "novos": 0, "mensagem": f"A fonte {mod.ROTULO} está desligada."}
    if not mod.configurado(cfg(mod.CHAVE)):
        return {"ok": False, "novos": 0, "mensagem": f"Configure {mod.ROTULO} nos Ajustes para consultar."}
    _gravar(**{mod.CHAVE + "_tentativa": datetime.now().isoformat(timespec="seconds")})
    try:
        r = mod.executar(c)
    except (ErroFonte, dados.ErroMiner) as ex:
        r = {"ok": False, "novos": 0, "erros": [str(ex)]}
    except Exception as ex:  # noqa: BLE001 - uma fonte com defeito não derruba as outras
        print("Miner: falha inesperada em", mod.CHAVE, type(ex).__name__)
        r = {"ok": False, "novos": 0, "erros": [f"{mod.ROTULO} falhou de forma inesperada."]}
    erros = r.get("erros") or []
    r.setdefault("novos", 0)
    quando = f"{datetime.now():%d/%m/%Y %H:%M}"
    if erros and r.get("parcial"):   # parte da consulta funcionou: a próxima rodada segue o intervalo normal
        _gravar(**{mod.CHAVE + "_ultimo": datetime.now().isoformat(timespec="seconds")})
    if not erros:
        _gravar(**{mod.CHAVE + "_ultimo": datetime.now().isoformat(timespec="seconds"), mod.CHAVE + "_falhas": "0",
                   mod.CHAVE + "_estado": f"{quando}: {r.get('resumo') or 'consulta concluída'}; {r['novos']} aviso(s) novo(s)."})
        r["mensagem"] = f"{mod.ROTULO}: consulta concluída, {r['novos']} aviso(s) novo(s)."
    else:
        falhas = int(_ler(mod.CHAVE + "_falhas", "0") or 0) + 1
        _gravar(**{mod.CHAVE + "_falhas": str(falhas), mod.CHAVE + "_estado": f"{quando}: consulta incompleta. {erros[0]}"})
        r["mensagem"] = f"{mod.ROTULO}: consulta incompleta. {erros[0]}"
        if falhas >= 3:
            c.avisar({"id": f"cid-falha:{mod.CHAVE}:{c.hoje.isoformat()}", "titulo": f"Consulta indisponível: {mod.ROTULO}", "nivel": "alto", "fonte": "justica",
                      "resumo": f"A consulta de {mod.ROTULO} falhou {falhas} vezes seguidas: {erros[0]} Enquanto isso, avisos novos desta fonte podem não aparecer aqui; confira o site oficial."})
    r["ok"] = not erros
    return r


def estado(mod) -> str:
    return _ler(mod.CHAVE + "_estado")


def executar_todos(**kw) -> dict:
    """A rodada vale para todas as pessoas: percorre o dono e cada convidado e roda as fontes devidas de cada um, com os dados dele."""
    feitos = {}
    for quem in pessoas.existentes(banco.DB_DIR):
        try:
            with pessoas.definir(quem), banco.da_pessoa(quem):
                for mod in fontes():
                    if devida(mod):
                        feitos[(quem, mod.CHAVE)] = executar_fonte(mod, Contexto(**kw))
        except Exception as ex:  # a falha de uma pessoa não impede a das outras
            feitos[(quem, "erro")] = {"ok": False, "mensagem": type(ex).__name__}
    return feitos


def executar_todos_da_pessoa(**kw) -> str:
    """Roda agora todas as fontes ligadas da pessoa atual (botão "Consultar fontes agora"); devolve uma frase de resultado."""
    ok = falhas = 0
    for mod in fontes():
        if not ligada(mod) or not mod.configurado(cfg(mod.CHAVE)):
            continue
        r = executar_fonte(mod, Contexto(**kw))
        if r.get("ok", True):
            ok += 1
        else:
            falhas += 1
    return f"Consulta concluída: {ok} fonte(s) consultada(s)" + (f", {falhas} com falha (veja o estado de cada uma)." if falhas else ".")
