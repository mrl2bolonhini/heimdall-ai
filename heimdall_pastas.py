#!/usr/bin/env python3
"""Nomes das pastas de dados do Heimdall e a migração dos nomes antigos para os novos (padrão: nome em inglês, igual ao do serviço).

Padrão: pasta com nome em inglês e de uma palavra só. Nomes antigos que migram sozinhos: dados_financas para finance, banco para db, cerebro para brain
e, dentro do finance, entrada para inbox e entrada_planilhas para sheets (qdrant_storage para qdrant é feito pelo start_heimdall.sh, por causa do Docker).
Pasta de dados do Finance: era dados_financas/, agora é finance/. Na primeira vez que qualquer serviço pede a pasta, se só a antiga existir,
ela é renomeada (os dados não são copiados nem apagados: o mesmo diretório muda de nome). Se não der para renomear, continua valendo a antiga.
HEIMDALL_FINANCE_DIR no .env, quando existe, manda mais que tudo isto.
"""
import os
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def migrar(raiz: Path, antigo: str, novo: str) -> Path:
    """Devolve raiz/novo; se só raiz/antigo existir, renomeia antes. Nunca falha: na dúvida, devolve a pasta antiga."""
    a, n = Path(raiz) / antigo, Path(raiz) / novo
    if a.exists() and not n.exists():
        try:
            os.rename(a, n)
        except OSError:
            return a
    return n


def finance(raiz: Path = AQUI) -> Path:
    return migrar(raiz, "dados_financas", "finance")


def db(raiz: Path = AQUI) -> Path:
    """Banco pessoal (heimdall.db, caixa_recebidos, documentos...). Era banco/."""
    return migrar(raiz, "banco", "db")


def brain(raiz: Path = AQUI) -> Path:
    """Cofre do Second Brain (notas em Markdown e áudios). Era cerebro/."""
    return migrar(raiz, "cerebro", "brain")


def finance_inbox(base: Path) -> Path:
    """Pasta onde se soltam extratos e faturas, dentro da pasta de dados do Finance. Era entrada/."""
    return migrar(Path(base), "entrada", "inbox")


def finance_sheets(base: Path) -> Path:
    """Pasta onde se soltam planilhas, dentro da pasta de dados do Finance. Era entrada_planilhas/."""
    return migrar(Path(base), "entrada_planilhas", "sheets")
