#!/usr/bin/env python3
"""Heimdall Learn, parte de dados: banco próprio (db/learn.db) e pastas de estudo dentro de knowledge/.

Fase 1 do Learn (guides/learn_especificacao.txt): pastas e subpastas criadas pela plataforma, cada uma com CATEGORIA (aleatório ou sequencial)
e TIPO (aberto: idiomas, programação, filosofia, medicina, exatas, humanas ou qualquer outro que o usuário cadastrar), importação de documentos
e catalogação das pastas que já existiam em knowledge/. Lições, exercícios, cards e agenda entram nas próximas fases.

Tudo fica no Mac. O banco é separado do banco pessoal (db/heimdall.db). Nenhuma função aqui apaga arquivo ou pasta do usuário.
Usa só a biblioteca padrão do Python.
"""
import hashlib
import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

import heimdall_pastas
import heimdall_learn_tipos as tipos_perfis

PROJECT_DIR = Path(__file__).resolve().parent


def pasta_dados() -> Path:
    return Path(os.environ.get("HEIMDALL_DB_DIR", str(heimdall_pastas.db(PROJECT_DIR)))).expanduser()


def pasta_knowledge() -> Path:
    return Path(os.environ.get("HEIMDALL_KNOWLEDGE_DIR", str(PROJECT_DIR / "knowledge"))).expanduser()


def caminho_banco() -> Path:
    return pasta_dados() / "learn.db"


CATEGORIAS = {
    "aleatorio": ("Aleatório", "Perguntas e respostas sobre trechos sorteados do material, com a transcrição do trecho, áudio e sugestão de matérias."),
    "sequencial": ("Sequencial", "Lições em ordem crescente, criadas a partir do material, com exercícios (idiomas, programação)."),
}
TIPOS_INICIAIS = list(tipos_perfis.PERFIS)   # o catálogo com as regras de cada tipo fica em heimdall_learn_tipos.py
EXT_DOC = {".pdf", ".md", ".markdown", ".txt", ".docx", ".epub", ".m4a", ".mp3"}
PROFUNDIDADE_MAX = 5
NOME_ARQ_RE = re.compile(r"^[^\W_][\w .,()+-]{0,118}\.[A-Za-z0-9]{1,8}$")
_trava = threading.RLock()
_prontos = set()   # bancos cujo esquema e tipos iniciais ja foram conferidos neste processo


class ErroLearn(Exception):
    """Pedido inválido: a mensagem é em português e pode ser mostrada ao usuário."""


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def max_bytes() -> int:
    try:
        return max(1, int(os.environ.get("HEIMDALL_LEARN_MAX_MB", "50"))) * 1024 * 1024
    except ValueError:
        return 50 * 1024 * 1024


# --------------------------------------------------------------------------------------------
# Banco
# --------------------------------------------------------------------------------------------
def conectar() -> sqlite3.Connection:
    arq = caminho_banco()
    arq.parent.mkdir(parents=True, exist_ok=True)
    novo = not arq.exists()
    con = sqlite3.connect(str(arq), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    if str(arq) in _prontos and not novo:
        return con
    con.executescript("""
        CREATE TABLE IF NOT EXISTS tipos (nome TEXT PRIMARY KEY, criado TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pastas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caminho TEXT NOT NULL UNIQUE,      -- relativo a knowledge/, com barras (ex.: idiomas/ingles)
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL CHECK (categoria IN ('aleatorio', 'sequencial')),
            tipo TEXT NOT NULL,
            idioma TEXT NOT NULL DEFAULT '',
            origem TEXT NOT NULL DEFAULT 'learn',   -- learn (criada aqui) ou existente (já estava em knowledge/)
            criado TEXT NOT NULL,
            atualizado TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pasta TEXT NOT NULL,               -- caminho da pasta
            arquivo TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            importado TEXT NOT NULL,
            UNIQUE (pasta, arquivo)
        );
        CREATE TABLE IF NOT EXISTS estudos (          -- modo aleatório: um sorteio, uma pergunta, uma resposta, uma correção
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pasta TEXT NOT NULL,
            documento TEXT NOT NULL,
            trecho_idx INTEGER NOT NULL,
            trecho TEXT NOT NULL,
            pergunta TEXT NOT NULL DEFAULT '',
            resposta TEXT NOT NULL DEFAULT '',
            correcao TEXT NOT NULL DEFAULT '',
            sugestoes TEXT NOT NULL DEFAULT '',
            audio TEXT NOT NULL DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'sorteado',
            erro TEXT NOT NULL DEFAULT '',
            criado TEXT NOT NULL
        );
    """)
    for t in TIPOS_INICIAIS:
        con.execute("INSERT OR IGNORE INTO tipos (nome, criado) VALUES (?, ?)", (t, _agora()))
    con.commit()
    if novo:
        try:
            os.chmod(arq, 0o600)
        except OSError:
            pass
    _prontos.add(str(arq))
    return con


# --------------------------------------------------------------------------------------------
# Nomes e caminhos
# --------------------------------------------------------------------------------------------
def slug(texto: str) -> str:
    """Nome de pasta no disco: minúsculas, sem acento, hífen no lugar de espaço. Vazio se não sobrar nada."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60]


def normalizar_caminho(rel: str) -> str:
    """Caminho relativo seguro (sem .., sem barra inicial, sem pasta oculta). Levanta ErroLearn se for suspeito."""
    rel = (rel or "").strip().replace("\\", "/").strip("/")
    if not rel:
        return ""
    partes = rel.split("/")
    for p in partes:
        if p in ("", ".", "..") or p.startswith(".") or "\0" in p or len(p) > 80:
            raise ErroLearn("Caminho de pasta inválido.")
    if len(partes) > PROFUNDIDADE_MAX:
        raise ErroLearn(f"No máximo {PROFUNDIDADE_MAX} níveis de subpastas.")
    return "/".join(partes)


def pasta_no_disco(rel: str) -> Path:
    """Pasta real dentro de knowledge/. Nunca sai de knowledge/ (nem por link simbólico)."""
    base = pasta_knowledge().resolve()
    alvo = (base / normalizar_caminho(rel)).resolve()
    if alvo != base and base not in alvo.parents:
        raise ErroLearn("Caminho de pasta inválido.")
    return alvo


def nome_bonito(rel: str) -> str:
    return rel.split("/")[-1].replace("-", " ").replace("_", " ").strip().capitalize()


# --------------------------------------------------------------------------------------------
# Tipos
# --------------------------------------------------------------------------------------------
def listar_tipos(con=None) -> list:
    c = con or conectar()
    return [r["nome"] for r in c.execute("SELECT nome FROM tipos ORDER BY nome COLLATE NOCASE")]


def _tipo_valido(nome: str) -> str:
    t = " ".join((nome or "").split())
    if not (2 <= len(t) <= 40) or not re.match(r"^[\w .,&()+/-]+$", t):
        raise ErroLearn("O tipo precisa ter de 2 a 40 letras, números ou espaços.")
    return t


def criar_tipo(nome: str) -> str:
    t = _tipo_valido(nome)
    with _trava:
        con = conectar()
        existe = next((x for x in listar_tipos(con) if x.lower() == t.lower()), None)
        if existe:
            return existe
        con.execute("INSERT INTO tipos (nome, criado) VALUES (?, ?)", (t, _agora()))
        con.commit()
    return t


def _eh_idiomas(tipo: str) -> bool:
    return tipos_perfis.pede_idioma(tipo)


# --------------------------------------------------------------------------------------------
# Pastas
# --------------------------------------------------------------------------------------------
def _linha_para_dict(r) -> dict:
    d = dict(r)
    d["categoria_nome"] = CATEGORIAS.get(d["categoria"], (d["categoria"], ""))[0]
    return d


def obter_pasta(rel: str):
    rel = normalizar_caminho(rel)
    r = conectar().execute("SELECT * FROM pastas WHERE caminho = ?", (rel,)).fetchone()
    return _linha_para_dict(r) if r else None


def listar_pastas(pai: str = "") -> list:
    """Subpastas diretas de `pai` ('' = nível de cima), só as que existem no disco."""
    pai = normalizar_caminho(pai)
    prefixo = pai + "/" if pai else ""
    saida = []
    for r in conectar().execute("SELECT * FROM pastas ORDER BY nome COLLATE NOCASE").fetchall():
        c = r["caminho"]
        if not c.startswith(prefixo) or "/" in c[len(prefixo):]:
            continue
        try:
            if not pasta_no_disco(c).is_dir():
                continue
        except ErroLearn:
            continue
        d = _linha_para_dict(r)
        d["documentos"] = len(listar_documentos(c))
        d["subpastas"] = len(listar_pastas(c)) if c.count("/") + 1 < PROFUNDIDADE_MAX else 0
        saida.append(d)
    return saida


def criar_pasta(nome: str, categoria: str = "", tipo: str = "", idioma: str = "", pai: str = "") -> dict:
    """Cria a pasta no disco e a cadastra. Subpasta herda categoria, tipo e idioma da pasta de cima, se não vierem."""
    nome = " ".join((nome or "").split())
    if not (2 <= len(nome) <= 60):
        raise ErroLearn("O nome da pasta precisa ter de 2 a 60 caracteres.")
    nome_disco = slug(nome)
    if not nome_disco:
        raise ErroLearn("O nome da pasta precisa ter letras ou números.")
    pai = normalizar_caminho(pai)
    with _trava:
        pai_reg = None
        if pai:
            pai_reg = obter_pasta(pai)
            if not pai_reg or not pasta_no_disco(pai).is_dir():
                raise ErroLearn("A pasta de cima não existe.")
        tipo = tipo.strip() or (pai_reg["tipo"] if pai_reg else "")
        if not tipo:
            raise ErroLearn("Escolha ou cadastre o tipo da pasta (por exemplo, idiomas ou programação).")
        # categoria: a escolhida; senão a da pasta de cima (se o tipo não mudou); senão a que o catálogo sugere para o tipo
        if not categoria and pai_reg and pai_reg["tipo"].lower() == tipo.lower():
            categoria = pai_reg["categoria"]
        categoria = categoria or tipos_perfis.categoria_sugerida(tipo)
        if categoria not in CATEGORIAS:
            raise ErroLearn("Escolha a categoria: aleatório ou sequencial.")
        tipo = criar_tipo(tipo)
        idioma = " ".join((idioma or (pai_reg["idioma"] if pai_reg else "")).split())[:40]
        if _eh_idiomas(tipo) and not idioma:
            raise ErroLearn("Para o tipo idiomas, informe o idioma de estudo (por exemplo, inglês).")
        rel = (pai + "/" if pai else "") + nome_disco
        rel = normalizar_caminho(rel)
        if obter_pasta(rel) or pasta_no_disco(rel).exists():
            raise ErroLearn("Já existe uma pasta com esse nome aí.")
        pasta_no_disco(rel).mkdir(parents=True, exist_ok=False, mode=0o700)
        con = conectar()
        con.execute("INSERT INTO pastas (caminho, nome, categoria, tipo, idioma, origem, criado, atualizado) VALUES (?, ?, ?, ?, ?, 'learn', ?, ?)",
                    (rel, nome, categoria, tipo, idioma, _agora(), _agora()))
        con.commit()
    return obter_pasta(rel)


def atualizar_pasta(rel: str, categoria: str, tipo: str, idioma: str = "", nome: str = "") -> dict:
    """Muda categoria, tipo, idioma (e o nome mostrado) de uma pasta. O nome no disco não muda."""
    rel = normalizar_caminho(rel)
    with _trava:
        atual = obter_pasta(rel)
        if not atual:
            raise ErroLearn("Pasta não encontrada.")
        if categoria not in CATEGORIAS:
            raise ErroLearn("Escolha a categoria: aleatório ou sequencial.")
        tipo = criar_tipo(tipo)
        idioma = " ".join((idioma or "").split())[:40]
        if _eh_idiomas(tipo) and not idioma:
            raise ErroLearn("Para o tipo idiomas, informe o idioma de estudo (por exemplo, inglês).")
        nome = " ".join((nome or atual["nome"]).split())
        if not (2 <= len(nome) <= 60):
            raise ErroLearn("O nome da pasta precisa ter de 2 a 60 caracteres.")
        con = conectar()
        con.execute("UPDATE pastas SET nome = ?, categoria = ?, tipo = ?, idioma = ?, atualizado = ? WHERE caminho = ?",
                    (nome, categoria, tipo, idioma, _agora(), rel))
        con.commit()
    return obter_pasta(rel)


def sincronizar() -> int:
    """Cadastra as pastas que já existiam em knowledge/ (os temas de estudo) e ainda não estão no banco: categoria aleatório (o que fazem hoje),
    tipo Outro (ou o da pasta de cima, nas subpastas). Devolve quantas foram cadastradas. Não mexe em nada no disco."""
    base = pasta_knowledge()
    if not base.is_dir():
        return 0
    novas = 0
    with _trava:
        con = conectar()
        achadas = []
        for dirpath, dirnames, _ in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and not Path(dirpath, d).is_symlink())
            for d in dirnames:
                rel = Path(dirpath, d).relative_to(base).as_posix()
                if rel.count("/") + 1 <= PROFUNDIDADE_MAX:
                    achadas.append(rel)
        for rel in sorted(achadas, key=lambda r: (r.count("/"), r)):
            if con.execute("SELECT 1 FROM pastas WHERE caminho = ?", (rel,)).fetchone():
                continue
            pai = rel.rsplit("/", 1)[0] if "/" in rel else ""
            r_pai = con.execute("SELECT * FROM pastas WHERE caminho = ?", (pai,)).fetchone() if pai else None
            con.execute("INSERT INTO pastas (caminho, nome, categoria, tipo, idioma, origem, criado, atualizado) VALUES (?, ?, ?, ?, ?, 'existente', ?, ?)",
                        (rel, nome_bonito(rel), r_pai["categoria"] if r_pai else "aleatorio", r_pai["tipo"] if r_pai else "Outro",
                         r_pai["idioma"] if r_pai else "", _agora(), _agora()))
            novas += 1
        con.commit()
    return novas


# --------------------------------------------------------------------------------------------
# Documentos
# --------------------------------------------------------------------------------------------
def listar_documentos(rel: str) -> list:
    pasta = pasta_no_disco(rel)
    if not pasta.is_dir():
        return []
    saida = []
    for p in sorted(pasta.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in EXT_DOC and not p.is_symlink():
            st = p.stat()
            saida.append({"nome": p.name, "bytes": st.st_size, "alterado": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y")})
    return saida


def nome_de_arquivo_seguro(nome: str) -> str:
    base = (nome or "").replace("\\", "/").split("/")[-1].strip()
    if not NOME_ARQ_RE.match(base) or Path(base).suffix.lower() not in EXT_DOC:
        raise ErroLearn("Arquivo não aceito. Use PDF, Markdown, texto, Word, EPUB, M4A ou MP3, com nome simples.")
    return base


def importar_documento(rel: str, nome_arquivo: str, dados: bytes) -> dict:
    """Grava o arquivo na pasta (permissão só do dono). Nunca sobrescreve: se o nome já existe, acrescenta um número."""
    rel = normalizar_caminho(rel)
    if not rel or not obter_pasta(rel):
        raise ErroLearn("Escolha uma pasta do Learn para receber o arquivo.")
    nome = nome_de_arquivo_seguro(nome_arquivo)
    if not dados:
        raise ErroLearn("O arquivo está vazio.")
    if len(dados) > max_bytes():
        raise ErroLearn(f"Arquivo maior que o limite de {max_bytes() // (1024 * 1024)} MB.")
    pasta = pasta_no_disco(rel)
    if not pasta.is_dir():
        raise ErroLearn("A pasta não existe no disco.")
    with _trava:
        destino = pasta / nome
        n = 1
        while destino.exists():
            n += 1
            destino = pasta / f"{Path(nome).stem}-{n}{Path(nome).suffix}"
        fd = os.open(str(destino), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
        con = conectar()
        con.execute("INSERT OR REPLACE INTO documentos (pasta, arquivo, bytes, sha256, importado) VALUES (?, ?, ?, ?, ?)",
                    (rel, destino.name, len(dados), hashlib.sha256(dados).hexdigest(), _agora()))
        con.commit()
    return {"arquivo": destino.name, "bytes": len(dados), "pasta": rel}


def resumo() -> dict:
    con = conectar()
    return {"pastas": con.execute("SELECT COUNT(*) FROM pastas").fetchone()[0],
            "documentos": con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0],
            "tipos": con.execute("SELECT COUNT(*) FROM tipos").fetchone()[0]}


def arvore_plana() -> list:
    """Todas as pastas que existem no disco, em ordem de caminho (para escolher uma pasta num formulário)."""
    saida = []
    for r in conectar().execute("SELECT * FROM pastas ORDER BY caminho COLLATE NOCASE").fetchall():
        try:
            if pasta_no_disco(r["caminho"]).is_dir():
                saida.append(_linha_para_dict(r))
        except ErroLearn:
            continue
    return saida


if __name__ == "__main__":
    import sys
    if "--sincronizar" in sys.argv:
        print(f"Pastas novas cadastradas: {sincronizar()}. {resumo()}")
    else:
        print(resumo())
