#!/usr/bin/env python3
"""Configurações do Heimdall: ler, mudar e tirar valores do arquivo .env, e listar as opções que o código aceita mas o .env ainda não define.

Quem usa: a aba Configurações do Controls. O formato é o mesmo do guardar_no_env.sh: NOME='valor' (o start_heimdall.sh lê o arquivo com source),
permissão 600 e uma cópia de segurança em .env.bak antes de cada mudança. Comentários e linhas que não são variável ficam como estão.
Mudar um valor aqui só vale para os serviços que lerem o .env depois: reinicie o serviço (aba Serviços) ou o Heimdall (aba Manutenção).
"""
import os
import re
import shutil
import threading
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ARQUIVO = PROJECT_DIR / ".env"
NOME_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")
_trava = threading.Lock()


def _valor_limpo(bruto: str) -> str:
    v = bruto.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def ler() -> list:
    """Variáveis definidas no .env, na ordem do arquivo: [{nome, valor}]. Se o nome aparece mais de uma vez, vale a última (como no shell)."""
    try:
        linhas = ARQUIVO.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    achadas: dict = {}
    for linha in linhas:
        t = linha.strip()
        if t.startswith("export "):
            t = t[7:].strip()
        if not t or t.startswith("#") or "=" not in t:
            continue
        nome, valor = t.split("=", 1)
        nome = nome.strip()
        if NOME_OK.match(nome):
            achadas.pop(nome, None)  # a última define; mantém a posição da última
            achadas[nome] = _valor_limpo(valor)
    return [{"nome": n, "valor": v} for n, v in achadas.items()]


def _validar(nome: str, valor: str = "") -> str:
    """Devolve o motivo de recusar ou "" se está certo."""
    if not NOME_OK.match(nome or ""):
        return "o nome só pode ter letras, números e _ e não pode começar por número"
    if "\n" in valor or "\r" in valor:
        return "o valor não pode ter quebra de linha"
    if "'" in valor:
        return "o valor não pode ter aspa simples (o .env guarda os valores entre aspas simples)"
    return ""


def _gravar(linhas: list) -> None:
    ARQUIVO_TMP = ARQUIVO.with_name(".env.novo")
    old = os.umask(0o077)
    try:
        ARQUIVO_TMP.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        os.chmod(ARQUIVO_TMP, 0o600)
        os.replace(ARQUIVO_TMP, ARQUIVO)
    finally:
        os.umask(old)


def _copia() -> None:
    if ARQUIVO.exists():
        bak = ARQUIVO.with_name(".env.bak")
        old = os.umask(0o077)
        try:
            shutil.copyfile(ARQUIVO, bak)
            os.chmod(bak, 0o600)
        finally:
            os.umask(old)


def _linhas_atuais() -> list:
    try:
        return ARQUIVO.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _e_do_nome(linha: str, nome: str) -> bool:
    t = linha.strip()
    if t.startswith("export "):
        t = t[7:].strip()
    return t.split("=", 1)[0].strip() == nome and "=" in t and not t.startswith("#")


def salvar(nome: str, valor: str) -> str:
    """Põe NOME='valor' no .env (troca a linha que existe, sem repetir). Devolve "" se deu certo ou o motivo."""
    nome, valor = (nome or "").strip(), (valor or "").strip()
    motivo = _validar(nome, valor)
    if motivo:
        return motivo
    with _trava:
        linhas = _linhas_atuais()
        _copia()
        novas, posto = [], False
        for l in linhas:
            if _e_do_nome(l, nome):
                if not posto:
                    novas.append(f"{nome}='{valor}'")
                    posto = True
                continue  # some com repetições
            novas.append(l)
        if not posto:
            novas.append(f"{nome}='{valor}'")
        try:
            _gravar(novas)
        except OSError as ex:
            return f"não consegui gravar o .env ({type(ex).__name__})"
    return ""


def remover(nome: str) -> str:
    nome = (nome or "").strip()
    motivo = _validar(nome)
    if motivo:
        return motivo
    with _trava:
        linhas = _linhas_atuais()
        _copia()
        try:
            _gravar([l for l in linhas if not _e_do_nome(l, nome)])
        except OSError as ex:
            return f"não consegui gravar o .env ({type(ex).__name__})"
    return ""


# ----------------------------------------------------------------------------------------
# O que o código aceita
# ----------------------------------------------------------------------------------------
_PY = re.compile(r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Z][A-Z0-9_]+)["']\s*(?:,\s*([^)\n]*?))?\s*\)""")
_SH = re.compile(r"\$\{([A-Z][A-Z0-9_]+):?-([^}]*)\}")
_cache = {"quando": 0.0, "dados": {}}


def _padrao_legivel(bruto) -> str:
    if bruto is None:
        return ""
    t = str(bruto).strip()
    if "(" in t or "[" in t or "{" in t or t in ("None",):
        return ""
    return t.strip("'\"")


def opcoes_do_codigo() -> dict:
    """{NOME: valor padrão} das variáveis HEIMDALL_* que os scripts do Heimdall leem. Guardado por 60 s."""
    if time.time() - _cache["quando"] < 60 and _cache["dados"]:
        return _cache["dados"]
    achadas: dict = {}
    for f in sorted(PROJECT_DIR.glob("*")):
        if f.suffix not in (".py", ".sh", ".zsh") or f.name.startswith("teste_") or f.name == Path(__file__).name:
            continue
        try:
            texto = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for nome, padrao in _PY.findall(texto):
            if nome.startswith("HEIMDALL_") and (nome not in achadas or not achadas[nome]):
                achadas[nome] = _padrao_legivel(padrao)
        for nome, padrao in _SH.findall(texto):
            if nome.startswith("HEIMDALL_") and (nome not in achadas or not achadas[nome]):
                achadas[nome] = _padrao_legivel(padrao)
    _cache.update(quando=time.time(), dados=achadas)
    return achadas


def grupo(nome: str) -> str:
    """Agrupa pelo serviço: HEIMDALL_CLOUD_PORTA -> CLOUD. Sem prefixo reconhecido, vai para GERAL."""
    partes = nome.split("_")
    if nome.startswith("HEIMDALL_") and len(partes) > 2:
        return partes[1]
    return "GERAL"
