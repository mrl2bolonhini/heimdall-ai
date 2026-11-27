#!/usr/bin/env python3
"""Testa a migração do nome antigo das pastas de dados (dados_financas para finance) e a organização do repositório."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import tempfile
from pathlib import Path

import studio_pastas as hp

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


d = Path(tempfile.mkdtemp())
(d / "dados_financas").mkdir()
(d / "dados_financas" / "financas.db").write_text("dados")
r = hp.finance(d)
confere("só a pasta antiga existe: renomeia para finance", r == d / "finance" and not (d / "dados_financas").exists())
confere("os dados vão junto (mesma pasta, só mudou o nome)", (d / "finance" / "financas.db").read_text() == "dados")
confere("chamar de novo não muda nada", hp.finance(d) == d / "finance" and (d / "finance" / "financas.db").exists())

d2 = Path(tempfile.mkdtemp())
confere("sem nenhuma pasta: devolve finance sem criar", hp.finance(d2) == d2 / "finance" and not (d2 / "finance").exists())

d3 = Path(tempfile.mkdtemp())
(d3 / "dados_financas").mkdir()
(d3 / "finance").mkdir()
(d3 / "finance" / "novo.txt").write_text("n")
(d3 / "dados_financas" / "velho.txt").write_text("v")
confere("as duas existem: não mexe em nenhuma", hp.finance(d3) == d3 / "finance" and (d3 / "dados_financas" / "velho.txt").exists() and (d3 / "finance" / "novo.txt").exists())

# demais pastas: db, brain e, dentro do Finance, inbox e sheets
d4 = Path(tempfile.mkdtemp())
for antigo in ("banco", "cerebro", "entrada", "entrada_planilhas"):
    (d4 / antigo).mkdir()
    (d4 / antigo / "arq.txt").write_text(antigo)
confere("banco vira db com os dados", hp.db(d4) == d4 / "db" and (d4 / "db" / "arq.txt").read_text() == "banco" and not (d4 / "banco").exists())
confere("cerebro vira brain com os dados", hp.brain(d4) == d4 / "brain" and (d4 / "brain" / "arq.txt").read_text() == "cerebro")
confere("entrada vira inbox", hp.finance_inbox(d4) == d4 / "inbox" and (d4 / "inbox" / "arq.txt").read_text() == "entrada")
confere("entrada_planilhas vira sheets", hp.finance_sheets(d4) == d4 / "sheets" and (d4 / "sheets" / "arq.txt").read_text() == "entrada_planilhas")
confere("db sem nenhuma pasta devolve db sem criar", hp.db(Path(tempfile.mkdtemp())).name == "db")

# subpastas do db, do Finance e a pasta própria da Saúde
import os, stat
d5 = Path(tempfile.mkdtemp())
(d5 / "db").mkdir()
for antigo in ("copias", "caixa_recebidos", "avisos_mac", "pessoas", "documentos"):
    (d5 / "db" / antigo).mkdir()
    (d5 / "db" / antigo / "arq.txt").write_text(antigo)
os.chmod(d5 / "db" / "pessoas", 0o700)
confere("copias vira copies", hp.db_copies(d5) == d5 / "db" / "copies" and (d5 / "db" / "copies" / "arq.txt").read_text() == "copias")
confere("caixa_recebidos vira mailbox", hp.db_mailbox(d5) == d5 / "db" / "mailbox" and (d5 / "db" / "mailbox" / "arq.txt").exists())
confere("avisos_mac vira alerts", hp.db_alerts(d5) == d5 / "db" / "alerts" and (d5 / "db" / "alerts" / "arq.txt").exists())
confere("pessoas vira people e mantém a permissão 0700", hp.db_people(d5) == d5 / "db" / "people" and stat.S_IMODE((d5 / "db" / "people").stat().st_mode) == 0o700)
for antigo, novo_ in (("entrada", "inbox"), ("arquivados", "archive"), ("revisar", "review")):
    (d5 / "db" / "documentos" / antigo).mkdir()
    (d5 / "db" / "documentos" / antigo / "doc.pdf").write_text(antigo)
h = hp.health(d5)
confere("db/documentos sai do db e vira health/ com os arquivos", h == d5 / "health" and not (d5 / "db" / "documentos").exists() and (h / "entrada" / "doc.pdf").exists())
confere("health: entrada vira inbox", hp.health_inbox(h) == h / "inbox" and (h / "inbox" / "doc.pdf").read_text() == "entrada")
confere("health: arquivados vira archive", hp.health_archive(h) == h / "archive" and (h / "archive" / "doc.pdf").exists())
confere("health: revisar vira review", hp.health_review(h) == h / "review" and (h / "review" / "doc.pdf").exists())
confere("health chamado de novo não muda nada", hp.health(d5) == h and (h / "inbox" / "doc.pdf").exists())
d6 = Path(tempfile.mkdtemp())
confere("health sem nenhuma pasta devolve health sem criar", hp.health(d6) == d6 / "health" and not (d6 / "health").exists())
d7 = Path(tempfile.mkdtemp())
(d7 / "inbox").mkdir()
for antigo in ("importados", "revisar"):
    (d7 / "inbox" / antigo).mkdir()
    (d7 / "inbox" / antigo / "x.csv").write_text(antigo)
confere("finance: importados vira imported", hp.finance_imported(d7 / "inbox") == d7 / "inbox" / "imported" and (d7 / "inbox" / "imported" / "x.csv").exists())
confere("finance: revisar vira review", hp.finance_review(d7 / "inbox") == d7 / "inbox" / "review" and (d7 / "inbox" / "review" / "x.csv").exists())
confere("health/ está no .gitignore", "/health/" in (RAIZ / ".gitignore").read_text().splitlines())

# pessoas/ e people/ ao mesmo tempo (o Learn gravava em pessoas/, o banco em people/): junta sem sobrescrever nem apagar
d6 = Path(tempfile.mkdtemp())
(d6 / "pessoas" / "pa" / "knowledge").mkdir(parents=True)
(d6 / "pessoas" / "pa" / "learn.db").write_text("learn-da-pa")
(d6 / "pessoas" / "pa" / "knowledge" / "m.md").write_text("material")
(d6 / "pessoas" / "pa" / "heimdall.db").write_text("versao-antiga")
(d6 / "pessoas" / "pb").mkdir()
(d6 / "pessoas" / "pb" / "learn.db").write_text("learn-da-pb")
(d6 / "people" / "pa").mkdir(parents=True)
(d6 / "people" / "pa" / "heimdall.db").write_text("versao-nova")
r = hp.people(d6)
confere("people: as duas pastas viram uma, em people/", r == d6 / "people" and (r / "pa" / "learn.db").read_text() == "learn-da-pa" and (r / "pb" / "learn.db").read_text() == "learn-da-pb" and (r / "pa" / "knowledge" / "m.md").exists())
confere("people: o que existe nos dois lugares não é sobrescrito nem apagado", (r / "pa" / "heimdall.db").read_text() == "versao-nova" and (d6 / "pessoas" / "pa" / "heimdall.db").read_text() == "versao-antiga")
confere("people: permissão 0700", stat.S_IMODE(r.stat().st_mode) == 0o700)
hp.people(d6)
confere("people: rodar de novo não muda nada", (d6 / "pessoas" / "pa" / "heimdall.db").exists() and (r / "pa" / "heimdall.db").read_text() == "versao-nova")
# organização do repositório
soltos = [p.name for p in RAIZ.iterdir() if p.is_file() and (p.name.startswith(("teste_", "test_")) or p.name.startswith("LEIAME_") or p.name.startswith("prompt_chat_"))]
confere("nenhum teste, guia LEIAME ou prompt solto na raiz", not soltos, ", ".join(soltos))
confere("nenhuma pasta com o nome antigo no repositório", not any((RAIZ / n).exists() for n in ("n8n_flows", "n8n_flows_avancados", "n8n_flows_monitor", "jogos", "app_mac")))
sys.exit(1 if falhas else 0)
