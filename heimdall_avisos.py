#!/usr/bin/env python3
"""Avisos de cada serviço sensível (Heimdall Health e Heimdall Finance): relatórios e análises que antes iam para o app Notas.

Agora ficam num banco local de cada serviço, só no Mac, e aparecem na aba Avisos do próprio serviço. O Notes (e o Notion, no futuro) nunca recebem
saúde nem finanças. O Bark continua avisando, mas só com texto genérico ("há um aviso novo"): `texto_bark` monta esse texto.
"""
import html
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SERVICOS = {"saude": "Heimdall Health", "financas": "Heimdall Finance"}
PASTAS_SENSIVEIS = {"Saúde": "saude", "Saude": "saude", "Heimdall Finanças": "financas", "Finanças": "financas", "Financas": "financas"}
_trava = threading.Lock()
MAX_TITULO, MAX_TEXTO, MAX_AVISOS = 200, 20000, 500


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Avisos:
    """Banco de avisos de um serviço. `caminho` é o arquivo .db (fica na pasta de dados do serviço, que não sai do Mac)."""

    def __init__(self, caminho):
        self.caminho = Path(caminho)

    def _con(self) -> sqlite3.Connection:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.caminho, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE IF NOT EXISTS avisos (id INTEGER PRIMARY KEY AUTOINCREMENT, criado TEXT NOT NULL, titulo TEXT NOT NULL, "
                    "texto TEXT NOT NULL DEFAULT '', lido INTEGER NOT NULL DEFAULT 0, origem TEXT)")
        if "origem" not in [r[1] for r in con.execute("PRAGMA table_info(avisos)")]:   # banco criado antes da migração das notas antigas
            con.execute("ALTER TABLE avisos ADD COLUMN origem TEXT")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_avisos_origem ON avisos (origem) WHERE origem IS NOT NULL")
        return con

    def gravar(self, titulo: str, texto: str, criado: str = "", origem: str = "") -> int:
        """Grava um aviso. Com `origem` (usada ao trazer notas antigas), gravar de novo a mesma origem não duplica: devolve o id que já existe."""
        titulo = re.sub(r"\s+", " ", str(titulo or "")).strip()[:MAX_TITULO]
        if not titulo:
            raise ValueError("falta o título")
        with _trava:
            con = self._con()
            try:
                if origem:
                    ja = con.execute("SELECT id FROM avisos WHERE origem = ?", (origem,)).fetchone()
                    if ja:
                        return ja[0]
                cur = con.execute("INSERT INTO avisos (criado, titulo, texto, origem) VALUES (?, ?, ?, ?)", (criado or _agora(), titulo, str(texto or "")[:MAX_TEXTO], origem or None))
                con.execute("DELETE FROM avisos WHERE id NOT IN (SELECT id FROM avisos ORDER BY id DESC LIMIT ?)", (MAX_AVISOS,))
                con.commit()
                return cur.lastrowid
            finally:
                con.close()

    def listar(self, limite: int = 100) -> list:
        if not self.caminho.exists():
            return []
        con = self._con()
        try:
            return [dict(r) for r in con.execute("SELECT * FROM avisos ORDER BY id DESC LIMIT ?", (int(limite),))]
        finally:
            con.close()

    def tem_origem(self, origem: str) -> bool:
        if not self.caminho.exists():
            return False
        con = self._con()
        try:
            return con.execute("SELECT 1 FROM avisos WHERE origem = ?", (origem,)).fetchone() is not None
        finally:
            con.close()

    def nao_lidos(self) -> int:
        if not self.caminho.exists():
            return 0
        con = self._con()
        try:
            return con.execute("SELECT COUNT(*) FROM avisos WHERE lido = 0").fetchone()[0]
        finally:
            con.close()

    def marcar(self, id_: int, lido: bool = True) -> bool:
        with _trava:
            con = self._con()
            try:
                n = con.execute("UPDATE avisos SET lido = ? WHERE id = ?", (1 if lido else 0, int(id_))).rowcount
                con.commit()
                return n > 0
            finally:
                con.close()

    def marcar_todos(self) -> int:
        with _trava:
            con = self._con()
            try:
                n = con.execute("UPDATE avisos SET lido = 1 WHERE lido = 0").rowcount
                con.commit()
                return n
            finally:
                con.close()


def do_servico(servico: str) -> "Avisos":
    """Os avisos de um serviço, no lugar certo: saúde fica ao lado do banco pessoal; finanças, na pasta de dados do Heimdall Finance (HEIMDALL_FINANCE_DIR)."""
    import os
    if servico == "saude":
        import heimdall_banco
        return Avisos(heimdall_banco.DB_DIR / "avisos_saude.db")
    if servico == "financas":
        return Avisos(Path(os.environ.get("HEIMDALL_FINANCE_DIR") or (Path(__file__).resolve().parent / "dados_financas")) / "avisos_financas.db")
    raise ValueError("serviço sem avisos: " + str(servico))


def texto_bark(servico: str, quantos: int = 1) -> dict:
    """Texto do Bark para um aviso novo: genérico, sem título, valor, nome ou número do conteúdo."""
    nome = SERVICOS.get(servico, "Heimdall")
    return {"title": f"{nome}: aviso novo" if quantos == 1 else f"{nome}: {quantos} avisos novos", "body": f"Abra a aba Avisos do {nome}.",
            "group": servico, "level": "active"}


def _data_br(iso: str) -> str:
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
        return d.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def _paragrafos(texto: str) -> str:
    """Markdown simples do aviso em parágrafos e listas de texto, sem interpretar HTML: o conteúdo vem de modelos e nunca é confiável."""
    saida, lista = [], []
    def fecha():
        if lista:
            saida.append("<ul>" + "".join(f"<li>{x}</li>" for x in lista) + "</ul>")
            lista.clear()
    for ln in str(texto).splitlines():
        t = ln.strip()
        if not t:
            fecha()
            continue
        t = html.escape(re.sub(r"^#+\s*", "", t) if t.startswith("#") else t, quote=True)
        if re.match(r"^[-*]\s+", ln.strip()):
            lista.append(re.sub(r"^[-*]\s+", "", t))
        else:
            fecha()
            saida.append(f"<p>{t}</p>")
    fecha()
    return "".join(saida)


def pagina(avisos: list, csrf: str, acao: str = "/avisos/lido", nome: str = "Avisos") -> str:
    """Corpo da aba Avisos: não lidos primeiro, cada um com o botão Marcar como lido (botão age) e um aviso para o leitor de tela."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    if not avisos:
        return '<p>Ainda não há avisos. Relatórios e análises novos aparecem aqui.</p>'
    ordem = sorted(avisos, key=lambda a: (a["lido"], -a["id"]))
    nao = sum(1 for a in avisos if not a["lido"])
    partes = [f'<p role="status">{nao} não lido(s) de {len(avisos)}.</p>']
    if nao:
        partes.append(f'<form method="post" action="{e(acao)}"><input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="id" value="todos">'
                      '<button type="submit">Marcar todos como lidos</button></form>')
    for a in ordem:
        i = f"aviso-{a['id']}"
        estado = "lido" if a["lido"] else "não lido"
        botao = "" if a["lido"] else (f'<form method="post" action="{e(acao)}"><input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="id" value="{a["id"]}">'
                                      f'<button type="submit" aria-label="Marcar como lido: {e(a["titulo"])}">Marcar como lido</button></form>')
        partes.append(f'<section aria-labelledby="{i}"><h2 id="{i}">{e(a["titulo"])} ({estado})</h2><p>{e(_data_br(a["criado"]))}</p>{_paragrafos(a["texto"])}{botao}</section>')
    return "".join(partes)
