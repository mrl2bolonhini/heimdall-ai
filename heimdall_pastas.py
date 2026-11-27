#!/usr/bin/env python3
"""Nomes das pastas de dados do StudioLibre e a migração dos nomes antigos para os novos (padrão: nome em inglês, igual ao do serviço).

Padrão: pasta com nome em inglês e de uma palavra só. Nomes antigos que migram sozinhos: dados_financas para finance, banco para db, cerebro para brain
e, dentro do finance, entrada para inbox e entrada_planilhas para sheets (qdrant_storage para qdrant é feito pelo start_heimdall.sh, por causa do Docker).
Pasta de dados do Finance: era dados_financas/, agora é finance/. Na primeira vez que qualquer serviço pede a pasta, se só a antiga existir,
ela é renomeada (os dados não são copiados nem apagados: o mesmo diretório muda de nome). Se não der para renomear, continua valendo a antiga.
STUDIO_FINANCE_DIR no .env, quando existe, manda mais que tudo isto.
Subpastas: db/copias para db/copies, db/caixa_recebidos para db/mailbox, db/avisos_mac para db/alerts, db/pessoas para db/people;
finance/inbox/importados para imported e revisar para review; os documentos de saúde saíram de db/documentos para a pasta própria health/
(entrada para inbox, arquivados para archive, revisar para review).
"""
import os
import sys
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


def finance_imported(inbox: Path) -> Path:
    """Arquivos do Finance já importados, dentro de finance/inbox. Era importados/."""
    return migrar(Path(inbox), "importados", "imported")


def finance_review(inbox: Path) -> Path:
    """Arquivos do Finance que pedem conferência, dentro de finance/inbox. Era revisar/."""
    return migrar(Path(inbox), "revisar", "review")


def db_copies(raiz: Path = AQUI) -> Path:
    """Cópia diária do banco (7 últimas). Era db/copias/."""
    return migrar(db(raiz), "copias", "copies")


def db_mailbox(raiz: Path = AQUI) -> Path:
    """Cópia local do que veio da caixa na nuvem. Era db/caixa_recebidos/."""
    return migrar(db(raiz), "caixa_recebidos", "mailbox")


def db_alerts(raiz: Path = AQUI) -> Path:
    """Avisos para o app do Mac. Era db/avisos_mac/."""
    return migrar(db(raiz), "avisos_mac", "alerts")


def _juntar(origem: Path, destino: Path) -> None:
    """Move para `destino` o que está em `origem` e ainda não existe lá, item por item. Nunca sobrescreve nem apaga:
    o que existir nos dois lugares fica em `origem`; a pasta só sai se ficar vazia."""
    destino.mkdir(parents=True, exist_ok=True)
    # Os arquivos auxiliares do SQLite (-wal, -shm, -journal) vão antes do banco: assim, quando o banco aparece no lugar novo,
    # as transações dele já estão lá. O que existir nos dois lugares fica na pasta antiga e é anotado no log, para conferência.
    auxiliar = lambda p: p.name.endswith(("-wal", "-shm", "-journal"))  # noqa: E731
    for item in sorted(origem.iterdir(), key=lambda p: (not auxiliar(p), p.name)):
        alvo = destino / item.name
        try:
            if item.is_symlink():
                continue
            if not alvo.exists():
                os.rename(item, alvo)
            elif item.is_dir() and alvo.is_dir():
                _juntar(item, alvo)
            else:
                sys.stderr.write(f"heimdall_pastas: {item} não foi movido porque {alvo} já existe; os dois foram mantidos\n")
        except OSError as ex:
            sys.stderr.write(f"heimdall_pastas: não consegui mover {item}: {ex}\n")
    try:
        origem.rmdir()   # só funciona se estiver vazia
    except OSError:
        pass


def people(base_db: Path) -> Path:
    """Pasta dos dados de cada pessoa, dentro da pasta de dados do dono: <base_db>/people/. Era <base_db>/pessoas/.
    Se só a antiga existir, é renomeada (a permissão 0700 vai junto). Se as duas existirem (o Learn gravava em pessoas/ e o banco em people/),
    o conteúdo da antiga é juntado ao da nova, pessoa por pessoa, sem sobrescrever nem apagar nada."""
    base_db = Path(base_db)
    n = migrar(base_db, "pessoas", "people")
    a = base_db / "pessoas"
    if n != a and a.is_dir() and not a.is_symlink():
        _juntar(a, n)
    try:
        os.chmod(n, 0o700) if n.is_dir() else None
    except OSError:
        pass
    return n


def db_people(raiz: Path = AQUI) -> Path:
    """Banco de cada pessoa (permissão 0700 preservada: é o mesmo diretório). Era db/pessoas/."""
    return people(db(raiz))


def health(raiz: Path = AQUI, db_dir: Path = None) -> Path:
    """Pasta própria da Saúde para soltar exames, receitas e encaminhamentos (inbox), com archive e review.
    Os documentos ficavam em db/documentos/: se só ela existir, é movida para health/ (mesmo diretório, nada é copiado nem apagado)."""
    raiz = Path(raiz)
    novo = raiz / "health"
    antigo = (Path(db_dir) if db_dir else db(raiz)) / "documentos"
    if antigo.exists() and not novo.exists():
        try:
            os.rename(antigo, novo)
        except OSError:
            return antigo
    return novo


def health_inbox(base: Path) -> Path:
    return migrar(Path(base), "entrada", "inbox")


def health_archive(base: Path) -> Path:
    return migrar(Path(base), "arquivados", "archive")


def health_review(base: Path) -> Path:
    return migrar(Path(base), "revisar", "review")
