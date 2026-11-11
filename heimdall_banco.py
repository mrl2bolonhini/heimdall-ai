#!/usr/bin/env python3
"""Banco de dados pessoal do Heimdall (SQLite, só biblioteca padrão).

Guarda no Mac, fora do n8n e fora do Git, o histórico que hoje se perde ou fica preso nos fluxos:
saúde por dia, menções dos diários oficiais e análises do Second Brain. O agente (heimdall_agente.py)
expõe isto em /banco/*; o n8n grava, e o chat e os painéis futuros consultam.

Arquivo: HEIMDALL_DB_DIR/heimdall.db (padrão: ./banco/heimdall.db). Cópia diária em banco/copias (7 últimas).
Leitura livre só por SELECT (consulta_sql): conexão somente leitura + autorizador que recusa qualquer outra coisa.
"""
import json
import os
import re
import sqlite3
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DB_DIR = Path(os.environ.get("HEIMDALL_DB_DIR", str(PROJECT_DIR / "banco"))).expanduser()
DB_PATH = DB_DIR / "heimdall.db"
_trava = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS saude_diaria (
    dia TEXT NOT NULL,              -- AAAA-MM-DD
    metrica TEXT NOT NULL,          -- passos, fc_repouso, hrv, sono_total, x:<nome> ...
    valor REAL NOT NULL,
    unidade TEXT NOT NULL DEFAULT '',
    atualizado TEXT NOT NULL,
    PRIMARY KEY (dia, metrica)
);
CREATE INDEX IF NOT EXISTS ix_saude_metrica ON saude_diaria (metrica, dia);

CREATE TABLE IF NOT EXISTS saude_resumos (
    dia TEXT PRIMARY KEY,
    titulo TEXT NOT NULL DEFAULT '',
    texto TEXT NOT NULL,
    atualizado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS diarios (
    id TEXT PRIMARY KEY,            -- fonte|id-ou-url, em minúsculas
    fonte TEXT NOT NULL,            -- municipal, federal, estadual, justica
    data TEXT NOT NULL DEFAULT '',
    titulo TEXT NOT NULL DEFAULT '',
    nome TEXT NOT NULL DEFAULT '',  -- o termo pesquisado
    trecho TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    visto_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_diarios_data ON diarios (data);

CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,            -- Message-ID
    data TEXT NOT NULL DEFAULT '',
    remetente TEXT NOT NULL DEFAULT '',
    dominio TEXT NOT NULL DEFAULT '',
    assunto TEXT NOT NULL DEFAULT '',
    classe TEXT NOT NULL DEFAULT '',        -- oficial, suspeito, nao_oficial
    servico TEXT NOT NULL DEFAULT '',
    motivo TEXT NOT NULL DEFAULT '',
    urgencia TEXT NOT NULL DEFAULT '',
    prazo TEXT NOT NULL DEFAULT '',
    visto_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_emails_classe ON emails (classe, visto_em);

CREATE TABLE IF NOT EXISTS estudos (
    id TEXT PRIMARY KEY,
    dia TEXT NOT NULL,
    hora TEXT NOT NULL DEFAULT '',
    tema TEXT NOT NULL DEFAULT '',
    livro TEXT NOT NULL DEFAULT '',
    conceito TEXT NOT NULL DEFAULT '',
    pergunta TEXT NOT NULL DEFAULT '',
    resposta TEXT NOT NULL DEFAULT '',
    artigos TEXT NOT NULL DEFAULT '[]',     -- JSON: [{titulo, url}]
    atualizado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_estudos_tema ON estudos (tema, dia);

CREATE TABLE IF NOT EXISTS privacidade (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL DEFAULT '',
    host TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    titulo TEXT NOT NULL DEFAULT '',
    tipo TEXT NOT NULL DEFAULT '',
    classe TEXT NOT NULL DEFAULT '',        -- confirmado, provavel
    risco TEXT NOT NULL DEFAULT '',         -- nenhum, baixo, medio, alto
    resumo TEXT NOT NULL DEFAULT '',
    dados TEXT NOT NULL DEFAULT '[]',       -- JSON: dados pessoais visíveis
    acao TEXT NOT NULL DEFAULT '',
    visto_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_privacidade_data ON privacidade (data);

CREATE TABLE IF NOT EXISTS avisos (
    id TEXT PRIMARY KEY,
    quando TEXT NOT NULL,
    slot TEXT NOT NULL DEFAULT '',          -- manha1, manha2, manha3, direto...
    titulo TEXT NOT NULL DEFAULT '',
    linha TEXT NOT NULL DEFAULT '',
    urgente INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_avisos_quando ON avisos (quando);

CREATE TABLE IF NOT EXISTS triagem (
    id TEXT PRIMARY KEY,            -- resumo legível + hash do identificador de origem
    criado TEXT NOT NULL,           -- AAAA-MM-DDTHH:MM:SSZ (UTC)
    fonte TEXT NOT NULL DEFAULT '', -- justica, saude, email, privacidade, diarios
    nivel TEXT NOT NULL DEFAULT 'alto',     -- critico, alto, medio (como o Heimdall classificou)
    titulo TEXT NOT NULL DEFAULT '',
    resumo TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'pendente',        -- pendente, concluida, descartada
    prioridade_usuario TEXT NOT NULL DEFAULT '',    -- alta, media, baixa, nenhuma, apagada: como você deixou o lembrete
    decidido_em TEXT NOT NULL DEFAULT '',
    adiado_ate TEXT NOT NULL DEFAULT '',
    avisos INTEGER NOT NULL DEFAULT 0,
    ultimo_aviso TEXT NOT NULL DEFAULT '',
    atualizado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_triagem_estado ON triagem (estado, criado);

CREATE TABLE IF NOT EXISTS analises (
    nota_id TEXT PRIMARY KEY,       -- id da nota no app Notas
    titulo TEXT NOT NULL,
    pasta TEXT NOT NULL DEFAULT '',
    resumo TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',        -- JSON
    conceitos TEXT NOT NULL DEFAULT '[]',   -- JSON
    entidades TEXT NOT NULL DEFAULT '[]',   -- JSON
    conexoes TEXT NOT NULL DEFAULT '[]',    -- JSON: [{titulo, tipo, motivo}]
    lacunas TEXT NOT NULL DEFAULT '[]',     -- JSON
    perguntas TEXT NOT NULL DEFAULT '[]',   -- JSON
    atualizado TEXT NOT NULL
);
"""

# tabela -> (colunas graváveis, chave primária). Nada fora desta lista é aceito.
TABELAS = {
    "saude_diaria": (["dia", "metrica", "valor", "unidade"], ["dia", "metrica"]),
    "saude_resumos": (["dia", "titulo", "texto"], ["dia"]),
    "diarios": (["id", "fonte", "data", "titulo", "nome", "trecho", "url"], ["id"]),
    "emails": (["id", "data", "remetente", "dominio", "assunto", "classe", "servico", "motivo", "urgencia", "prazo"], ["id"]),
    "estudos": (["id", "dia", "hora", "tema", "livro", "conceito", "pergunta", "resposta", "artigos"], ["id"]),
    "privacidade": (["id", "data", "host", "url", "titulo", "tipo", "classe", "risco", "resumo", "dados", "acao"], ["id"]),
    "avisos": (["id", "quando", "slot", "titulo", "linha", "urgente"], ["id"]),
    "analises": (["nota_id", "titulo", "pasta", "resumo", "tags", "conceitos", "entidades", "conexoes", "lacunas", "perguntas"], ["nota_id"]),
}
_JSON_COLS = {"tags", "conceitos", "entidades", "conexoes", "lacunas", "perguntas", "artigos", "dados"}
# coluna de data de gravação de cada tabela (None = a tabela já traz a sua). visto_em guarda a 1ª vez; atualizado, a última.
_CARIMBO = {"saude_diaria": "atualizado", "saude_resumos": "atualizado", "analises": "atualizado", "estudos": "atualizado",
            "diarios": "visto_em", "emails": "visto_em", "privacidade": "visto_em", "avisos": None}
_TEXTO_MAX = 8000
_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def conectar(somente_leitura: bool = False) -> sqlite3.Connection:
    if somente_leitura:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    else:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(DB_PATH, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
    return con


def iniciar() -> None:
    """Cria o arquivo e as tabelas se faltarem; faz a cópia diária."""
    with _trava:
        con = conectar()
        try:
            con.executescript(ESQUEMA)
            con.commit()
        finally:
            con.close()
    _copia_diaria()


def _copia_diaria() -> None:
    destino = DB_DIR / "copias"
    try:
        destino.mkdir(parents=True, exist_ok=True)
        hoje = destino / f"heimdall-{datetime.now():%Y-%m-%d}.db"
        if hoje.exists():
            return
        origem = conectar()
        try:
            copia = sqlite3.connect(hoje)
            try:
                origem.backup(copia)
            finally:
                copia.close()
        finally:
            origem.close()
        antigas = sorted(destino.glob("heimdall-*.db"))[:-7]
        for a in antigas:
            a.unlink()
    except Exception:  # noqa: BLE001 - a cópia nunca pode derrubar o agente
        pass


def _limpa(col: str, v):
    if col in _JSON_COLS:
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                v = [v]
        return json.dumps(v if v is not None else [], ensure_ascii=False)[:_TEXTO_MAX]
    if col == "valor":
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            raise ValueError("valor inválido")
        return f
    s = "" if v is None else str(v)
    if col == "dia" and not _DATA_RE.match(s):
        raise ValueError(f"dia inválido: {s[:20]}")
    return s[:_TEXTO_MAX]


def gravar(tabela: str, registros: list) -> dict:
    """Insere ou atualiza (pela chave primária). Devolve quantos entraram e quantos foram recusados."""
    if tabela not in TABELAS:
        raise ValueError(f"tabela desconhecida: {tabela[:40]}")
    if not isinstance(registros, list):
        raise ValueError("registros deve ser uma lista")
    cols, chave = TABELAS[tabela]
    carimbo = _CARIMBO[tabela]
    todas = cols + ([carimbo] if carimbo else [])
    atualiza = [c for c in todas if c not in chave and c != "visto_em"]
    sql = (f"INSERT INTO {tabela} ({', '.join(todas)}) VALUES ({', '.join('?' * len(todas))}) "
           f"ON CONFLICT ({', '.join(chave)}) DO " + (f"UPDATE SET {', '.join(c + '=excluded.' + c for c in atualiza)}" if atualiza else "NOTHING"))
    linhas, recusados = [], 0
    for r in registros[:5000]:
        try:
            if not isinstance(r, dict) or any(r.get(k) in (None, "") for k in chave):
                raise ValueError("falta a chave")
            vals = [_limpa(c, r.get(c, "")) if c != "valor" else _limpa(c, r["valor"]) for c in cols]
            linhas.append(vals + ([_agora()] if carimbo else []))
        except (ValueError, TypeError, KeyError):
            recusados += 1
    if not linhas:
        return {"gravados": 0, "recusados": recusados}
    with _trava:
        con = conectar()
        try:
            con.executemany(sql, linhas)
            con.commit()
        finally:
            con.close()
    return {"gravados": len(linhas), "recusados": recusados}


def _autorizador(acao, a1, a2, banco, gatilho):
    permitidas = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE)
    return sqlite3.SQLITE_OK if acao in permitidas else sqlite3.SQLITE_DENY


def sem_acento(texto) -> str:
    """Minúsculas e sem acento; também disponível dentro do SQL como sem_acento(coluna)."""
    return unicodedata.normalize("NFKD", "" if texto is None else str(texto).lower()).encode("ascii", "ignore").decode()


def consulta_sql(sql: str, limite: int = 200, params: tuple = ()) -> dict:
    """Roda um único SELECT em conexão somente leitura. Qualquer outra coisa é recusada."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", sql) or ";" in sql:
        raise PermissionError("só é permitido um único SELECT")
    limite = max(1, min(int(limite), 1000))
    if not DB_PATH.exists():
        iniciar()
    con = conectar(somente_leitura=True)
    try:
        con.create_function("sem_acento", 1, sem_acento, deterministic=True)
        con.set_authorizer(_autorizador)
        # interrompe consultas lentas (ex.: produto cartesiano)
        t0 = time.time()
        con.set_progress_handler(lambda: 1 if time.time() - t0 > 5 else 0, 10000)
        cur = con.execute(sql, tuple(params))
        linhas = cur.fetchmany(limite + 1)
        colunas = [d[0] for d in cur.description or []]
        cortado = len(linhas) > limite
        return {"colunas": colunas, "linhas": [list(r) for r in linhas[:limite]], "cortado": cortado}
    except sqlite3.DatabaseError as e:
        raise ValueError("consulta recusada ou inválida: " + str(e)[:160]) from e
    finally:
        con.close()


def resumo() -> dict:
    """Contagens e período de cada tabela (para conferir se o banco está recebendo dados)."""
    if not DB_PATH.exists():
        iniciar()
    con = conectar(somente_leitura=True)
    try:
        saida = {}
        saida["saude_diaria"] = dict(zip(("linhas", "dias", "de", "ate", "metricas"), con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT dia), MIN(dia), MAX(dia), COUNT(DISTINCT metrica) FROM saude_diaria").fetchone()))
        saida["saude_resumos"] = dict(zip(("linhas", "de", "ate"), con.execute("SELECT COUNT(*), MIN(dia), MAX(dia) FROM saude_resumos").fetchone()))
        saida["diarios"] = dict(zip(("linhas", "de", "ate"), con.execute("SELECT COUNT(*), MIN(data), MAX(data) FROM diarios").fetchone()))
        saida["emails"] = dict(zip(("linhas", "ate"), con.execute("SELECT COUNT(*), MAX(visto_em) FROM emails").fetchone()))
        saida["estudos"] = dict(zip(("linhas", "de", "ate"), con.execute("SELECT COUNT(*), MIN(dia), MAX(dia) FROM estudos").fetchone()))
        saida["privacidade"] = dict(zip(("linhas", "de", "ate"), con.execute("SELECT COUNT(*), MIN(data), MAX(data) FROM privacidade").fetchone()))
        saida["avisos"] = dict(zip(("linhas", "de", "ate"), con.execute("SELECT COUNT(*), MIN(quando), MAX(quando) FROM avisos").fetchone()))
        saida["triagem"] = dict(zip(("linhas", "pendentes", "ate"), con.execute(
            "SELECT COUNT(*), COALESCE(SUM(estado = 'pendente'), 0), MAX(criado) FROM triagem").fetchone()))
        saida["analises"] = dict(zip(("linhas", "ate"), con.execute("SELECT COUNT(*), MAX(atualizado) FROM analises").fetchone()))
        return saida
    finally:
        con.close()


def tabelas_para_modelo() -> str:
    """Descrição curta do esquema, usada nas ferramentas do chat."""
    return (
        "saude_diaria(dia, metrica, valor, unidade): um valor por métrica por dia. Métricas: passos, energia, fc_repouso, hrv, resp, spo2, "
        "glicose, glicose_min, sono_total, sono_profundo, sono_rem, sono_cama e x:<nome> (qualquer outra métrica do Apple Saúde). "
        "Sono em minutos.\n"
        "saude_resumos(dia, titulo, texto): o resumo de saúde escrito de cada dia.\n"
        "diarios(id, fonte, data, titulo, nome, trecho, url, visto_em): menções ao seu nome nos diários oficiais; fonte: municipal, federal, estadual, justica.\n"
        "emails(id, data, remetente, dominio, assunto, classe, servico, motivo, urgencia, prazo, visto_em): e-mails de serviços públicos vistos pelo vigia (sem o corpo); "
        "classe: oficial, suspeito (possível golpe) ou nao_oficial.\n"
        "estudos(id, dia, hora, tema, livro, conceito, pergunta, resposta, artigos, atualizado): cada estudo dos livros (6h, 13h e 20h); artigos é JSON.\n"
        "privacidade(id, data, host, url, titulo, tipo, classe, risco, resumo, dados, acao, visto_em): achados do monitor de privacidade; risco: nenhum, baixo, medio, alto.\n"
        "avisos(id, quando, slot, titulo, linha, urgente): cada aviso de rotina que passou pelo resumo agrupado.\n"
        "analises(nota_id, titulo, pasta, resumo, tags, conceitos, entidades, conexoes, lacunas, perguntas, atualizado): análise do Second Brain de cada nota; "
        "as colunas de lista são JSON.\n"
        "Dentro do SQL, sem_acento(coluna) devolve o texto em minúsculas e sem acento (use em buscas: WHERE sem_acento(titulo) LIKE '%coracao%')."
    )


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Banco pessoal do Heimdall")
    ap.add_argument("--sql", help="roda um SELECT e mostra o resultado em texto")
    a = ap.parse_args()
    iniciar()
    if a.sql:
        try:
            r = consulta_sql(a.sql)
        except (PermissionError, ValueError) as e:
            print("Erro:", e)
            sys.exit(1)
        print(" | ".join(r["colunas"]))
        for linha in r["linhas"]:
            print(" | ".join("" if v is None else str(v) for v in linha))
        if r["cortado"]:
            print("(resultado cortado)")
    else:
        print(json.dumps(resumo(), ensure_ascii=False, indent=2))
