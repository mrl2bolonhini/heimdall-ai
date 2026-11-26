#!/usr/bin/env python3
"""Configurações do Heimdall: ler, mudar e tirar valores do arquivo .env, e listar as opções que o código aceita mas o .env ainda não define.

Quem usa: a aba Ajustes do Controls. O formato é o mesmo do scripts/guardar_no_env.sh: NOME='valor' (o start_heimdall.sh lê o arquivo com source),
permissão 600 e uma cópia de segurança em .env.bak antes de cada mudança. Comentários e linhas que não são variável ficam como estão.
Mudar um valor aqui só vale para os serviços que lerem o .env depois: reinicie o serviço (aba Serviços) ou o Heimdall (aba Manutenção).
"""
import os
import re
import shutil
import threading
import time
from pathlib import Path

import heimdall_envcompat as _envcompat

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
        nome = _envcompat.interno(nome.strip())
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
    return _envcompat.interno(t.split("=", 1)[0].strip()) == _envcompat.interno(nome) and "=" in t and not t.startswith("#")


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


# Nomes que mudaram: o Cloud virou Lab (23/11/2026). A senha, o código e a duração da sessão (HEIMDALL_CLOUD_SENHA_HASH, _TOTP_SEGREDO e _SESSAO_HORAS)
# servem a todos os sites e mantêm o nome.
RENOMEADAS = {f"HEIMDALL_CLOUD_{x}": f"HEIMDALL_LAB_{x}" for x in ("HOST", "PORT", "ENDPOINT", "REGIAO", "HOSTS", "MAX_MB")}


def renomear_antigas() -> list:
    """Troca no .env os nomes antigos pelos novos (sem perder valor: se o novo já existe, o antigo só sai). Faz cópia em .env.bak. Devolve os nomes trocados."""
    linhas = _linhas_atuais()
    if not linhas:
        return []
    trocadas, saida = [], []
    for ln in linhas:
        nome = next((a for a in RENOMEADAS if _e_do_nome(ln, a)), "")
        if not nome:
            saida.append(ln)
            continue
        trocadas.append(nome)
        if not any(_e_do_nome(x, RENOMEADAS[nome]) for x in linhas):
            saida.append(ln.replace(nome, RENOMEADAS[nome], 1))
    if trocadas:
        _copia()
        _gravar(saida)
    return trocadas


# ----------------------------------------------------------------------------------------
# O que o código aceita
# ----------------------------------------------------------------------------------------
_PY = re.compile(r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Z][A-Z0-9_]+)["']\s*(?:,\s*([^)\n]*?))?\s*\)""")
_SH = re.compile(r"\$\{([A-Z][A-Z0-9_]+):?-([^}]*)\}")
_PALAVRAS_SEGREDO = {"SENHA", "SECRET", "SEGREDO", "TOKEN", "KEY", "HASH", "PASSWORD"}


def e_segredo(nome: str) -> bool:
    """Segredo de verdade: alguma palavra do nome é senha, token, chave etc. HEIMDALL_WEBUI_SEM_SENHA é um liga/desliga, não um segredo."""
    partes = nome.upper().split("_")
    return any(p in _PALAVRAS_SEGREDO and (i == 0 or partes[i - 1] != "SEM") for i, p in enumerate(partes))


# Opções que não valem mais: não aparecem na lista de Ajustes (quem ainda as tem no .env pode apagá-las à mão ou deixar).
OBSOLETAS = {"HEIMDALL_WEBUI_SEM_SENHA"}
_SH_SIMPLES = re.compile(r"\$\{?(HEIMDALL_[A-Z0-9_]+)")
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
        if f.suffix in (".sh", ".zsh"):
            for nome in _SH_SIMPLES.findall(texto):  # lidas como $NOME ou ${NOME:+...}, sem padrão
                achadas.setdefault(nome, "")
    try:  # variáveis documentadas na ajuda também aparecem, mesmo se o código as lê de outro jeito
        import heimdall_config_ajuda as _aj
        for nome in _aj.DESCRICOES:
            if nome.startswith(("HEIMDALL_", "SUBIR_")):
                achadas.setdefault(nome, "")
    except ImportError:
        pass
    for n in OBSOLETAS:
        achadas.pop(n, None)
    _cache.update(quando=time.time(), dados=achadas)
    return achadas


def grupo(nome: str) -> str:
    """Agrupa pelo serviço: HEIMDALL_LAB_PORT -> LAB; LITELLM_MASTER_KEY -> LITELLM. Sem prefixo, vai para GERAL."""
    partes = nome.split("_")
    if nome.startswith("HEIMDALL_"):
        return partes[1] if len(partes) > 2 else "GERAL"
    return partes[0] or "GERAL"


def gravar_padroes() -> tuple:
    """Grava no .env as opções que o código define com valor padrão e o .env ainda não tem (nunca segredos). Devolve (gravadas, recusadas)."""
    atuais = {d["nome"] for d in ler()}
    feitas, falhas = [], []
    for n, v in sorted(opcoes_do_codigo().items()):
        if n in atuais or not v or e_segredo(n):
            continue
        (falhas if salvar(n, v) else feitas).append(n)
    return feitas, falhas


if __name__ == "__main__":
    import sys
    if "--gravar-padroes" in sys.argv:
        ok, ruins = gravar_padroes()
        print(f"{len(ok)} valores padrão gravados no .env (cópia anterior em .env.bak)." + (" Recusados: " + ", ".join(ruins) + "." if ruins else ""))
        for n in ok:
            print("  " + n)
    else:
        print("Use: python3 heimdall_config.py --gravar-padroes")
