#!/usr/bin/env python3
"""Dados separados por pessoa: quem é a pessoa da requisição e onde ficam os dados dela.

Cada pessoa que entra por convite (Cloudflare Access) tem uma pasta própria, db/people/<id>/ (a mesma do banco pessoal dela, heimdall_banco), com um banco por serviço (learn.db...), e a
sua pasta de material (knowledge/) fora da pasta do dono, para a busca nos documentos do dono nunca enxergar os arquivos dela. O dono mantém
os caminhos de sempre (sem migração). O <id> sai do e-mail (hash), então o e-mail não aparece em nome de pasta.

Este módulo é o ponto único de escolha: os serviços não montam caminho de dados por conta própria; pedem a `raiz()`.
A pessoa da requisição fica numa variável de contexto (`definir`); tarefas em segundo plano a levam junto com `vincular`.
Desligar: HEIMDALL_PESSOAS=0 (todo mundo usa os dados do dono, como antes). Usa só a biblioteca padrão do Python.
"""
import contextvars
import hashlib
import os
import re
from pathlib import Path

import heimdall_pastas

DONO = "dono"
ID_RE = re.compile(r"^p[0-9a-f]{12}$")
_atual = contextvars.ContextVar("heimdall_pessoa", default=DONO)


class ErroPessoa(Exception):
    """Identificação de pessoa inválida."""


def ativo() -> bool:
    return os.environ.get("HEIMDALL_PESSOAS", "1") != "0"


def id_da(email: str) -> str:
    """Identificador estável da pessoa a partir do e-mail (sem maiúsculas nem espaços). Nunca devolve "dono"."""
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        raise ErroPessoa("e-mail inválido")
    return "p" + hashlib.sha256(("heimdall-pessoa-v1\0" + e).encode("utf-8")).hexdigest()[:12]


def valido(pessoa: str) -> bool:
    return pessoa == DONO or bool(ID_RE.match(pessoa or ""))


def atual() -> str:
    """Pessoa da requisição em curso (o dono, se nada foi definido: terminal, testes e tarefas do próprio Mac)."""
    p = _atual.get()
    return p if valido(p) else DONO


class definir:
    """Com `with definir(pessoa):` tudo dentro do bloco, nesta thread, trabalha com os dados dessa pessoa."""

    def __init__(self, pessoa: str):
        if not valido(pessoa or DONO):
            raise ErroPessoa("pessoa inválida")
        self.pessoa = pessoa or DONO

    def __enter__(self):
        self._t = _atual.set(self.pessoa)
        return self.pessoa

    def __exit__(self, *exc):
        _atual.reset(self._t)
        return False


def vincular(funcao):
    """Devolve uma função que roda `funcao` com a pessoa de agora, mesmo em outra thread (tarefas em segundo plano)."""
    pessoa = atual()

    def rodar(*a, **k):
        with definir(pessoa):
            return funcao(*a, **k)
    return rodar


def e_dono(pessoa: str = "") -> bool:
    return (pessoa or atual()) == DONO or not ativo()


def raiz(base_db: Path, pessoa: str = "") -> Path:
    """Pasta de dados da pessoa. Dono (ou recurso desligado): a pasta de sempre. Convidado: <base_db>/people/<id>/ (permissão só do dono do Mac).
    A antiga <base_db>/pessoas/ é juntada a people/ por heimdall_pastas.people, sem apagar nada."""
    p = pessoa or atual()
    if e_dono(p):
        return base_db
    if not valido(p):
        raise ErroPessoa("pessoa inválida")
    pasta = heimdall_pastas.people(Path(base_db)) / p
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(pasta.parent, 0o700)
        os.chmod(pasta, 0o700)
    except OSError:
        pass
    return pasta


def existentes(base_db: Path) -> list:
    """O dono e as pessoas que já têm pasta, para tarefas que percorrem todo mundo (a agenda do Learn)."""
    saida = [DONO]
    if ativo():
        d = heimdall_pastas.people(Path(base_db)) if (Path(base_db) / "pessoas").exists() or (Path(base_db) / "people").exists() else None
        if d and d.is_dir():
            saida += sorted(x.name for x in d.iterdir() if x.is_dir() and ID_RE.match(x.name) and not x.is_symlink())
    return saida
