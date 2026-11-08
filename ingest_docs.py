"""Indexa documentos na base de conhecimento (Qdrant) para a ferramenta rag_search.

Uso, na pasta do projeto, com o Qdrant e o Ollama no ar:
    ollama pull nomic-embed-text            # uma vez
    python ingest_docs.py                    # indexa a pasta knowledge/ ao lado do script
    python ingest_docs.py ~/Notas ~/Docs     # indexa outras pastas
    python ingest_docs.py --reset            # apaga a coleção e recria (troca de modelo de embedding)

Reindexar é seguro e incremental: arquivos que não mudaram são pulados (um registro em
data/ingest_manifest.json guarda o hash de cada um), e os que mudaram têm os trechos
antigos trocados pelos novos. Use --force para reindexar tudo e --prune para remover da
coleção os arquivos que saíram da pasta.
Temas: cada subpasta de primeiro nível vira o "tema" dos arquivos dentro dela (knowledge/aws/guia.pdf tem o tema "aws";
arquivos soltos em knowledge/ têm o tema "geral"). O rag_search aceita o parâmetro tema para buscar só naquele assunto.
Para dar tema a uma base já indexada basta rodar o script de novo: ele só atualiza a etiqueta, sem refazer os embeddings.
Arquivos ocultos (como .env), pastas ocultas e arquivos maiores que 50 MB (ajuste com --max-mb) são ignorados,
e padrões de segredo (chaves de API etc.) são mascarados antes de indexar.
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
import uuid
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import heimdall_tools as ht  # noqa: E402

TEXT_EXT = {".txt", ".md", ".rst", ".csv", ".json", ".yaml", ".yml", ".py", ".sql"}
DEFAULT_MAX_MB = 50


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Quebra por parágrafos, juntando até 'size' caracteres, com sobreposição."""
    paras = [p.strip() for p in text.replace("\r", "").split("\n\n") if p.strip()]
    pieces: list[str] = []
    for p in paras:
        while len(p) > size:  # parágrafo gigante: corta em fatias
            pieces.append(p[:size])
            p = p[size - overlap:]
        pieces.append(p)
    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) + 2 > size:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n\n" + p if overlap else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur.strip():
        chunks.append(cur)
    return chunks


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            print(f"  (pulado, instale 'pip install pypdf' para PDFs): {path.name}")
            return ""
        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="replace")


def _manifest_path() -> Path:
    return ht.DATA_DIR / "ingest_manifest.json"


def load_manifest() -> dict:
    try:
        return json.loads(_manifest_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_manifest(manifest: dict) -> None:
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def delete_source(base: str, source: str) -> None:
    requests.post(
        f"{base}/points/delete?wait=true",
        json={"filter": {"must": [{"key": "source", "match": {"value": source}}]}},
        timeout=60,
    ).raise_for_status()


def tema_slug(texto: str) -> str:
    """Nome do tema em minúsculas, sem acentos e com hífens (igual ao que o rag_search usa)."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "geral"


def tema_de(path: Path, root: Path) -> str:
    """Primeira subpasta abaixo da raiz; arquivos soltos usam 'geral' (ou o nome da raiz, se não for knowledge)."""
    if root.is_dir():
        rel = path.relative_to(root).parts
        if len(rel) > 1:
            return tema_slug(rel[0])
        return "geral" if root.name == "knowledge" else tema_slug(root.name)
    return "geral"


def find_files(roots: list[Path], max_bytes: int):
    for root in roots:
        if root.is_file():
            candidates = [root]
        else:
            candidates = sorted(p for p in root.rglob("*") if p.is_file())
        for p in candidates:
            rel_parts = p.relative_to(root).parts if root.is_dir() else (p.name,)
            if any(part.startswith(".") for part in rel_parts):
                continue
            if p.suffix.lower() not in TEXT_EXT | {".pdf"}:
                continue
            if p.stat().st_size > max_bytes:
                print(f"  (pulado, maior que {max_bytes // (1024 * 1024)} MB; use --max-mb): {p.name}")
                continue
            yield p, tema_de(p, root)


def set_tema(base: str, source: str, tema: str) -> None:
    requests.post(
        f"{base}/points/payload?wait=true",
        json={"payload": {"tema": tema}, "filter": {"must": [{"key": "source", "match": {"value": source}}]}},
        timeout=120,
    ).raise_for_status()


def ensure_tema_index(base: str) -> None:
    """Índice do campo tema (permite filtrar e listar os temas com rapidez). Pode repetir sem problema."""
    try:
        requests.put(f"{base}/index?wait=true", json={"field_name": "tema", "field_schema": "keyword"}, timeout=30)
    except requests.RequestException:
        pass


def ensure_collection(name: str, dim: int, reset: bool) -> bool:
    """Garante a coleção. Devolve True se ela acabou de ser criada (vazia)."""
    url = f"{ht.QDRANT_URL}/collections/{name}"
    if reset:
        requests.delete(url, timeout=30)
    r = requests.get(url, timeout=15)
    if r.status_code == 200:
        vectors = r.json()["result"]["config"]["params"]["vectors"]
        existing = vectors.get("size") if isinstance(vectors, dict) else None
        if existing and existing != dim:
            sys.exit(
                f"A coleção '{name}' usa vetores de {existing} dimensões, mas o modelo gera {dim}. "
                "Rode com --reset para recriar."
            )
        return False
    if r.status_code != 404:
        sys.exit(f"Erro do Qdrant ao consultar a coleção (status {r.status_code}): {r.text[:200]}")
    c = requests.put(url, json={"vectors": {"size": dim, "distance": "Cosine"}}, timeout=30)
    if c.status_code not in (200, 201):
        sys.exit(f"Não consegui criar a coleção (status {c.status_code}): {c.text[:200]}")
    print(f"Coleção '{name}' criada ({dim} dimensões).")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Indexa documentos no Qdrant para o rag_search")
    ap.add_argument("pastas", nargs="*", help="pastas ou arquivos (padrão: knowledge/)")
    ap.add_argument("--collection", default=ht.QDRANT_COLLECTION)
    ap.add_argument("--chunk", type=int, default=1000, help="tamanho do trecho em caracteres")
    ap.add_argument("--overlap", type=int, default=150)
    ap.add_argument("--max-mb", type=int, default=DEFAULT_MAX_MB, help="tamanho máximo de cada arquivo em MB (padrão 50)")
    ap.add_argument("--reset", action="store_true", help="apaga e recria a coleção")
    ap.add_argument("--force", action="store_true", help="reindexa tudo, mesmo o que não mudou")
    ap.add_argument("--prune", action="store_true", help="remove da coleção os arquivos que não estão mais nas pastas")
    args = ap.parse_args()
    ht.QDRANT_COLLECTION = args.collection

    roots = [Path(p).expanduser().resolve() for p in args.pastas] or [BASE_DIR / "knowledge"]
    for r in roots:
        if not r.exists():
            sys.exit(f"Não existe: {r}" + ("\nCrie a pasta e coloque seus documentos nela." if r.name == "knowledge" else ""))

    try:
        dim = len(ht._embed(["teste"])[0])
    except Exception as e:
        sys.exit(f"Erro ao gerar embeddings no Ollama: {e}")
    try:
        created = ensure_collection(args.collection, dim, args.reset)
    except requests.RequestException as e:
        sys.exit(f"Não consegui falar com o Qdrant ({ht.QDRANT_URL}): {e}")

    base = f"{ht.QDRANT_URL}/collections/{args.collection}"
    manifest = load_manifest()
    if created or args.reset or args.force:
        manifest[args.collection] = {}  # coleção nova/vazia: nada está indexado
    entries = manifest.setdefault(args.collection, {})
    ensure_tema_index(base)
    params = f"{args.chunk}/{args.overlap}/{ht.EMBED_MODEL}"

    files = chunks_total = unchanged = 0
    seen: set[str] = set()
    retemados = 0
    for path, tema in find_files(roots, args.max_mb * 1024 * 1024):
        source = str(path)
        seen.add(source)
        digest = file_sha256(path)
        old = entries.get(source)
        if old and old.get("sha256") == digest and old.get("params") == params:
            if old.get("tema") != tema:
                # Mesmo conteúdo, só falta (ou mudou) o tema: atualiza a etiqueta sem refazer os embeddings.
                if old.get("chunks"):
                    set_tema(base, source, tema)
                old["tema"] = tema
                save_manifest(manifest)
                retemados += 1
                print(f"  {path.name}: tema '{tema}'", flush=True)
            else:
                unchanged += 1
                print(f"  {path.name}: inalterado, pulado", flush=True)
            continue
        try:
            text = ht._redact(read_text(path))
        except Exception as e:
            print(f"  (erro ao ler {path.name}: {e})")
            continue
        chunks = chunk_text(text, args.chunk, args.overlap)
        if not chunks:
            print(f"  {path.name}: sem texto extraível (PDF escaneado/imagem?), ignorado")
        # Remove os trechos antigos deste arquivo antes de gravar os novos.
        delete_source(base, source)
        if not chunks:
            entries[source] = {"sha256": digest, "params": params, "chunks": 0, "tema": tema}
            save_manifest(manifest)
            continue
        print(f"  {path.name}: indexando {len(chunks)} trechos...", flush=True)
        for i in range(0, len(chunks), 16):
            batch = chunks[i:i + 16]
            vectors = ht._embed(batch)
            points = [
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}#{i + j}")),
                    "vector": vec,
                    "payload": {"source": source, "tema": tema, "chunk": i + j, "text": chunk},
                }
                for j, (chunk, vec) in enumerate(zip(batch, vectors))
            ]
            requests.put(f"{base}/points?wait=true", json={"points": points}, timeout=120).raise_for_status()
        files += 1
        chunks_total += len(chunks)
        entries[source] = {"sha256": digest, "params": params, "chunks": len(chunks), "tema": tema}
        save_manifest(manifest)  # grava a cada arquivo: se for interrompido, retoma de onde parou
        print(f"  {path.name}: {len(chunks)} trechos", flush=True)

    pruned = 0
    if args.prune:
        root_prefixes = tuple(str(r) for r in roots)
        for source in [x for x in entries if x.startswith(root_prefixes) and x not in seen]:
            delete_source(base, source)
            del entries[source]
            pruned += 1
            print(f"  removido da coleção (arquivo não existe mais): {Path(source).name}")
        save_manifest(manifest)

    print(
        f"\nPronto: {files} arquivo(s) indexado(s), {chunks_total} trecho(s), "
        f"{unchanged} inalterado(s)" + (f", {retemados} com tema atualizado" if retemados else "")
        + (f", {pruned} removido(s)" if args.prune else "")
        + f", na coleção '{args.collection}'."
    )


if __name__ == "__main__":
    main()
