#!/usr/bin/env python3
"""Studio Learn: traz para o Learn os estudos que antes viviam no Notes.

Fontes (só leitura; nada é apagado nem movido, as cópias originais continuam onde estão):
  1. As notas de estudo do cofre (brain/<tema>/*.md, com o áudio em brain/<tema>/audio/*.m4a) que o fluxo das 6h, 13h e 20h gravava.
  2. A tabela estudos do banco principal (db/heimdall.db), para o que não tiver nota.
Destino: a tabela estudos do Learn (estado importado), na pasta do Learn cujo nome, sem acento e com hífens, é o tema da nota. Tema sem pasta
no Learn é só avisado. Pode rodar de novo: o que já foi importado (campo chave) é pulado.

    python3 heimdall_learn_migrar.py            mostra o que faria
    python3 heimdall_learn_migrar.py --aplicar  importa
Usa só a biblioteca padrão do Python.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path

import heimdall_learn_dados as dados
import heimdall_learn_voz as voz
import heimdall_pastas

PROJECT_DIR = Path(__file__).resolve().parent
CABECALHO = re.compile(r"^Estudo de (\d{2})/(\d{2})/(\d{4}) às (\d{1,2})h\.(?: Tema: ([^.\n]*)\.)?(?: Livro: (.*))?$", re.M)
CABECALHO_ANTIGO = re.compile(r"^# Estudo (\d{4}-\d{2}-\d{2}) (\d{1,2})h: (.*)$", re.M)
TEMA_LIVRO = re.compile(r"^Tema: ([^.\n]*)\.(?: Livro: (.*))?$", re.M)


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()).strip()


def _do_env(chave: str) -> str:
    """Valor de uma variável: do ambiente ou, no terminal (que não carrega o .env), da linha do .env do projeto. Só lê as chaves pedidas."""
    if os.environ.get(chave):
        return os.environ[chave]
    try:
        for linha in (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            linha = linha[7:] if linha.startswith("export ") else linha
            if linha.startswith(chave + "="):
                return linha.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def pasta_cofre() -> Path:
    v = _do_env("HEIMDALL_VAULT_DIR")
    return Path(v).expanduser() if v else heimdall_pastas.brain(PROJECT_DIR)


def _secao(md: str, inicio: str) -> str:
    m = re.search(r"^## " + re.escape(inicio) + r"[^\n]*\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1).strip() if m else ""


def ler_nota(p: Path) -> dict:
    """Uma nota de estudo do cofre como dicionário, ou {} se não tiver o formato (precisa de Pergunta e Resposta)."""
    try:
        md = p.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    except OSError:
        return {}
    pergunta, resposta = _secao(md, "Pergunta"), _secao(md, "Resposta")
    sem_pergunta = False
    if not pergunta or not resposta:
        # nota dos primeiros dias, em que o modelo não devolveu a pergunta: o trecho lido continua valendo, a pergunta se gera de novo no Learn
        if not _secao(md, "Leitura") or not md.lstrip().startswith("#"):
            return {}
        pergunta = resposta = ""
        sem_pergunta = True
    titulo = (re.search(r"^# (.+)$", md, re.M) or [None, p.stem])[1].strip()
    dia = hora = tema = livro = ""
    m = CABECALHO.search(md)
    if m:
        dia, hora, tema, livro = f"{m[3]}-{m[2]}-{m[1]}", m[4].zfill(2), (m[5] or "").strip(), (m[6] or "").strip().rstrip(".")
    else:
        a = CABECALHO_ANTIGO.search(md)
        if a:
            dia, hora = a[1], a[2].zfill(2)
            titulo = a[3].strip() or titulo
        t = TEMA_LIVRO.search(md)
        if t:
            tema, livro = t[1].strip(), (t[2] or "").strip().rstrip(".")
    artigos = [x.strip() for x in _secao(md, "Para aprofundar").splitlines() if x.strip()]
    artigos = [re.sub(r"^\d+\.\s*", "", x) for x in artigos]
    return {"arquivo": p, "titulo": titulo, "dia": dia, "hora": hora, "tema": tema or p.parent.name, "livro": livro, "pergunta": pergunta, "sem_pergunta": sem_pergunta,
            "resposta": resposta, "leitura": _secao(md, "Leitura"), "artigos": artigos}


def pasta_do_tema(tema: str):
    """Pasta de nível de topo do Learn cujo nome no disco, normalizado, é o tema. None se não houver."""
    alvo = dados.slug(tema)
    for p in dados.listar_pastas(""):
        if dados.slug(p["caminho"]) == alvo:
            return p["caminho"]
    return None


def _chave(tipo: str, ident: str) -> str:
    return hashlib.sha1(f"{tipo}:{ident}".encode("utf-8")).hexdigest()[:16]


def notas_do_cofre(cofre: Path = None) -> tuple:
    """(itens, avisos): as notas de estudo dos temas que têm pasta no Learn, e os temas do cofre que ficam de fora."""
    cofre = cofre or pasta_cofre()
    itens, avisos = [], []
    if not cofre.is_dir():
        return itens, [f"Cofre não encontrado: {cofre}"]
    for d in sorted(cofre.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.is_symlink():
            continue
        pasta = pasta_do_tema(d.name)
        if not pasta:
            sem = sum(1 for p in d.glob("*.md") if ler_nota(p))
            if sem:
                avisos.append(f"o tema {d.name} do cofre tem {sem} nota(s) de estudo, mas não há uma pasta {d.name} no Learn; não serão importadas (crie a pasta e rode de novo)")
            continue
        for p in sorted(d.glob("*.md")):
            n = ler_nota(p)
            if not n:
                avisos.append(f"{d.name}/{p.name}: sem pergunta e resposta, não é uma nota de estudo; fica onde está")
                continue
            n["pasta"] = pasta
            n["chave"] = _chave("nota", f"{d.name}/{p.name}")
            a = d / "audio" / (p.stem + ".m4a")
            n["audio"] = a if a.is_file() and not a.is_symlink() else None
            itens.append(n)
    return itens, avisos


def linhas_do_banco(arq: Path = None) -> list:
    """Linhas da tabela estudos do banco principal, só leitura. Lista vazia se não existir."""
    arq = arq or (dados.pasta_dados_base() / "heimdall.db")
    if not Path(arq).is_file():
        return []
    try:
        con = sqlite3.connect(f"file:{arq}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute("SELECT id, dia, hora, tema, livro, conceito, pergunta, resposta, artigos, atualizado FROM estudos ORDER BY id")]
    except sqlite3.Error:
        return []


def _artigos_do_banco(txt: str) -> list:
    try:
        return [f"{a.get('titulo', '').strip()} - {a.get('url', '').strip()}".strip(" -") for a in json.loads(txt or "[]") if isinstance(a, dict)]
    except ValueError:
        return []


def planejar(cofre: Path = None, banco: Path = None) -> dict:
    """O que seria importado: notas do cofre e linhas do banco sem nota correspondente (mesmo tema, dia, hora e conceito)."""
    notas, avisos = notas_do_cofre(cofre)
    vistos = {(_norm(n["tema"]), n["dia"], n["hora"], _norm(n["titulo"])) for n in notas}
    so_banco, sem_pasta = [], set()
    for r in linhas_do_banco(banco):
        pasta = pasta_do_tema(r["tema"] or "")
        if not pasta:
            sem_pasta.add(r["tema"] or "(sem tema)")
            continue
        if (_norm(r["tema"]), r["dia"], str(r["hora"]).zfill(2), _norm(r["conceito"])) in vistos:
            continue
        so_banco.append({"pasta": pasta, "titulo": (r["conceito"] or "Estudo").strip(), "dia": r["dia"], "hora": str(r["hora"]).zfill(2), "tema": r["tema"], "livro": r["livro"] or "",
                         "pergunta": r["pergunta"] or "", "resposta": r["resposta"] or "", "leitura": "", "artigos": _artigos_do_banco(r["artigos"]), "audio": None,
                         "chave": _chave("banco", str(r["id"]))})
    for t in sorted(sem_pasta):
        avisos.append(f"tema {t} do banco não tem pasta no Learn; não foi importado")
    return {"notas": notas, "banco": [x for x in so_banco if x["pergunta"]], "avisos": avisos}


def _inserir(con, n: dict, origem: str) -> int:
    criado = f"{n['dia'] or '2026-01-01'} {n['hora'] or '00'}:00:00"
    sem = n.get("sem_pergunta")
    texto_resp = "" if sem else "Resposta esperada (do estudo original):\n" + n["resposta"]
    estado, erro = ("erro", "Esta nota antiga não tinha pergunta. Use Tentar de novo para gerar uma pergunta sobre o trecho.") if sem else ("importado", "")
    cur = con.execute(
        "INSERT INTO estudos (pasta, documento, trecho_idx, trecho, pergunta, resposta, correcao, sugestoes, audio, estado, erro, criado, titulo, origem, chave) "
        "VALUES (?, ?, 0, ?, ?, '', ?, ?, '', ?, ?, ?, ?, ?, ?)",
        (n["pasta"], n["livro"] or "(sem livro)", n["leitura"], n["pergunta"], texto_resp, "\n".join(n["artigos"]), estado, erro, criado, n["titulo"], origem, n["chave"]))
    return cur.lastrowid


def migrar(aplicar: bool = False, cofre: Path = None, banco: Path = None) -> dict:
    """Importa (ou só conta, se aplicar=False). Idempotente. Devolve os números e os avisos."""
    plano = planejar(cofre, banco)
    r = {"notas": 0, "banco": 0, "audios": 0, "ja_importados": 0, "avisos": list(plano["avisos"]), "aplicado": aplicar, "por_pasta": {}}
    con = dados.conectar()
    with dados._trava:
        for origem, itens in (("nota", plano["notas"]), ("banco", plano["banco"])):
            for n in itens:
                if con.execute("SELECT 1 FROM estudos WHERE chave = ?", (n["chave"],)).fetchone():
                    r["ja_importados"] += 1
                    continue
                r["notas" if origem == "nota" else "banco"] += 1
                r["por_pasta"][n["pasta"]] = r["por_pasta"].get(n["pasta"], 0) + 1
                if not aplicar:
                    continue
                id_ = _inserir(con, n, origem)
                if n.get("audio"):
                    destino = voz.pasta_audio() / f"estudo-{id_}.m4a"
                    if not destino.exists():
                        shutil.copy2(n["audio"], destino)
                        os.chmod(destino, 0o600)
                        con.execute("UPDATE estudos SET audio = ? WHERE id = ?", (destino.name, id_))
                        r["audios"] += 1
        if aplicar:
            con.commit()
    return r


def texto_resumo(r: dict) -> str:
    verbo = "Importados" if r["aplicado"] else "Seriam importados"
    linhas = [f"{verbo}: {r['notas']} nota(s) do cofre e {r['banco']} estudo(s) só do banco" + (f", com {r['audios']} áudio(s)" if r["aplicado"] else "") + ".",
              f"Já estavam no Learn: {r['ja_importados']}."]
    linhas += [f"  {pasta}: {n}" for pasta, n in sorted(r["por_pasta"].items())]
    linhas += [f"Aviso: {a}" for a in r["avisos"][:20]]
    if not r["aplicado"]:
        linhas.append("Nada foi gravado. Para importar: heimdall learn --migrate --apply")
    else:
        linhas.append("Nada foi apagado: as notas e os áudios originais continuam no cofre (brain/).")
    return "\n".join(linhas)


def main() -> None:
    aplicar = "--aplicar" in sys.argv[1:]
    print(texto_resumo(migrar(aplicar)))


if __name__ == "__main__":
    main()
