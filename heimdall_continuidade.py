#!/usr/bin/env python3
"""Continuidade do StudioLibre na nuvem: cópia cifrada dos bancos para o R2 (no Mac) e restauração deles no contêiner (na nuvem).

No Mac (STUDIO_CONTINUIDADE=1 no .env liga; =0 desliga e não envia nada):
    python3 heimdall_continuidade.py preparar    gera a senha das cópias de continuidade no .env (se ainda não existir)
    python3 heimdall_continuidade.py enviar      envia ao R2 só os bancos que mudaram, cifrados com AES-256-GCM
    python3 heimdall_continuidade.py status      mostra a data da última cópia no R2
No contêiner (a imagem chama sozinha na subida):
    python3 heimdall_continuidade.py restaurar [PASTA]   baixa e decifra a última cópia para PASTA (padrão: a pasta do projeto)

Como funciona: cada banco SQLite (db/*.db, db/people/*/*.db, finance/*.db) vira uma cópia consistente (SQLite .backup, com conferência de integridade),
é cifrado no próprio Mac (a senha HEIMDALL_CONTINUIDADE_SENHA nunca vai ao R2) e gravado em continuidade/. Um manifesto cifrado lista os
arquivos, o tamanho e a soma de conferência de cada um. Na restauração toda soma é conferida antes de gravar; nada que já exista é apagado.
A nuvem só lê esta cópia: o Mac continua sendo a fonte (as alterações feitas na nuvem durante uma queda entram na fase do diário de alterações).
Variáveis: HEIMDALL_R2_ENDPOINT, HEIMDALL_R2_BUCKET, HEIMDALL_R2_KEY_ID, HEIMDALL_R2_SECRET (as mesmas do backup) e HEIMDALL_CONTINUIDADE_SENHA.
"""
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import heimdall_backup as backup

PROJECT_DIR = Path(__file__).resolve().parent
PADROES = ("db/*.db", "db/people/*/*.db", "finance/*.db", "db/avisos_config_*.json", "finance/avisos_config_*.json")
PREFIXO = "continuidade/"
MANIFESTO = PREFIXO + "manifesto.hdcn"


def ligado(env=None) -> bool:
    e = os.environ if env is None else env
    return str(e.get("STUDIO_CONTINUIDADE", "0")).strip() in ("1", "true", "sim")


def modo_continuidade(env=None) -> bool:
    """True dentro do contêiner de continuidade: os serviços só leem a cópia e não rodam coletores nem vigias que gravariam no banco restaurado."""
    e = os.environ if env is None else env
    return str(e.get("HEIMDALL_CONTINUIDADE_MODO", "0")).strip() == "1"


def arquivos(raiz: Path = PROJECT_DIR) -> list:
    """Caminhos relativos (com /) dos arquivos que entram na cópia."""
    achados = set()
    for padrao in PADROES:
        for p in Path(raiz).glob(padrao):
            if p.is_file():
                achados.add(p.relative_to(raiz).as_posix())
    return sorted(achados)


def _conteudo(raiz: Path, rel: str) -> bytes:
    """Conteúdo do arquivo; banco SQLite sai como cópia consistente e conferida, o resto é lido como está."""
    p = Path(raiz) / rel
    if p.suffix != ".db":
        return p.read_bytes()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "copia.db"
        origem = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            dest = sqlite3.connect(tmp)
            try:
                origem.backup(dest)
                ok = dest.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                dest.close()
        finally:
            origem.close()
        if ok != "ok":
            raise RuntimeError(f"{rel} falhou na conferência de integridade: {ok}")
        return tmp.read_bytes()


def _chave_objeto(rel: str) -> str:
    return PREFIXO + rel.replace("/", "__") + ".hdcn"


def _soma(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def cliente_r2(env=None, cliente=None):
    """(cliente S3, bucket) do R2, ou (None, "") se faltar configuração."""
    e = os.environ if env is None else env
    cfg = {k: e.get(v, "").strip() for k, v in (("endpoint", "HEIMDALL_R2_ENDPOINT"), ("bucket", "HEIMDALL_R2_BUCKET"),
                                                ("key_id", "HEIMDALL_R2_KEY_ID"), ("secret", "HEIMDALL_R2_SECRET"))}
    if not all(cfg.values()):
        return None, ""
    if cliente is None:
        import boto3
        cliente = boto3.client("s3", endpoint_url=cfg["endpoint"], aws_access_key_id=cfg["key_id"], aws_secret_access_key=cfg["secret"], region_name="auto")
    return cliente, cfg["bucket"]


def _ler_manifesto(c, bucket: str, senha: str) -> dict:
    try:
        blob = c.get_object(Bucket=bucket, Key=MANIFESTO)["Body"].read()
    except Exception:  # noqa: BLE001  (ainda não existe)
        return {}
    return json.loads(backup.decifrar(blob, senha).decode("utf-8"))


def enviar(raiz: Path = PROJECT_DIR, env=None, cliente=None, agora=None) -> dict:
    """Envia ao R2 os bancos que mudaram desde a última cópia. Devolve {ok, enviados, iguais, quando} ou {ok, desligado}."""
    e = os.environ if env is None else env
    if not ligado(e):
        return {"ok": True, "desligado": True, "aviso": "STUDIO_CONTINUIDADE está desligado; nada foi enviado."}
    senha = e.get("HEIMDALL_CONTINUIDADE_SENHA", "")
    if not senha:
        raise RuntimeError("falta HEIMDALL_CONTINUIDADE_SENHA no .env (rode: python3 heimdall_continuidade.py preparar)")
    c, bucket = cliente_r2(e, cliente)
    if c is None:
        raise RuntimeError("faltam as variáveis HEIMDALL_R2_* no .env")
    antes = _ler_manifesto(c, bucket, senha).get("arquivos", {})
    novos, enviados, iguais = {}, [], []
    for rel in arquivos(raiz):
        dados = _conteudo(raiz, rel)
        soma = _soma(dados)
        novos[rel] = {"bytes": len(dados), "sha256": soma}
        if antes.get(rel, {}).get("sha256") == soma:
            iguais.append(rel)
            continue
        c.put_object(Bucket=bucket, Key=_chave_objeto(rel), Body=backup.cifrar(dados, senha))
        enviados.append(rel)
    quando = (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    if enviados or novos.keys() != antes.keys():
        manifesto = {"quando": quando, "arquivos": novos}
        c.put_object(Bucket=bucket, Key=MANIFESTO, Body=backup.cifrar(json.dumps(manifesto).encode("utf-8"), senha))
    else:
        quando = _ler_manifesto(c, bucket, senha).get("quando", quando)
    return {"ok": True, "enviados": enviados, "iguais": iguais, "quando": quando}


def restaurar(destino: Path = PROJECT_DIR, env=None, cliente=None) -> dict:
    """Baixa, decifra e confere a última cópia, e grava em `destino`. Só grava depois de conferir tudo. Devolve {ok, quando, arquivos}."""
    e = os.environ if env is None else env
    senha = e.get("HEIMDALL_CONTINUIDADE_SENHA", "")
    if not senha:
        raise RuntimeError("falta HEIMDALL_CONTINUIDADE_SENHA")
    c, bucket = cliente_r2(e, cliente)
    if c is None:
        raise RuntimeError("faltam as variáveis HEIMDALL_R2_*")
    manifesto = _ler_manifesto(c, bucket, senha)
    if not manifesto.get("arquivos"):
        raise RuntimeError("não há cópia de continuidade no R2")
    lidos = {}
    for rel, info in manifesto["arquivos"].items():
        dados = backup.decifrar(c.get_object(Bucket=bucket, Key=_chave_objeto(rel))["Body"].read(), senha)
        if len(dados) != info["bytes"] or _soma(dados) != info["sha256"]:
            raise RuntimeError(f"{rel}: a cópia não confere com o manifesto")
        lidos[rel] = dados
    destino = Path(destino)
    for rel, dados in lidos.items():
        alvo = (destino / rel).resolve()
        if destino.resolve() not in alvo.parents:   # nunca grava fora da pasta de destino
            raise RuntimeError(f"caminho inválido na cópia: {rel}")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        tmp = alvo.with_name(alvo.name + ".parcial")
        tmp.write_bytes(dados)
        os.replace(tmp, alvo)
    return {"ok": True, "quando": manifesto.get("quando", ""), "arquivos": sorted(lidos)}


def status(env=None, cliente=None) -> dict:
    e = os.environ if env is None else env
    c, bucket = cliente_r2(e, cliente)
    if c is None or not e.get("HEIMDALL_CONTINUIDADE_SENHA"):
        return {"ok": False, "erro": "configuração incompleta (HEIMDALL_R2_* e HEIMDALL_CONTINUIDADE_SENHA)"}
    m = _ler_manifesto(c, bucket, e["HEIMDALL_CONTINUIDADE_SENHA"])
    return {"ok": bool(m), "quando": m.get("quando", ""), "arquivos": sorted(m.get("arquivos", {}))}


INTERVALO_PADRAO_MIN = 60


def _env_atual() -> dict:
    """O ambiente do processo com o que está no .env agora (o agente fica dias no ar: ligar ou desligar pelo Controls vale sem reiniciar)."""
    e = dict(os.environ)
    try:
        import heimdall_config
        e.update({i["nome"]: i["valor"] for i in heimdall_config.ler()})
    except Exception:  # noqa: BLE001
        pass
    return e


def intervalo_s(env=None) -> int:
    """Segundos entre dois envios automáticos: HEIMDALL_CONTINUIDADE_INTERVALO_MIN (padrão 60; mínimo 5; máximo 1440)."""
    e = _env_atual() if env is None else env
    try:
        m = int(str(e.get("HEIMDALL_CONTINUIDADE_INTERVALO_MIN", INTERVALO_PADRAO_MIN)).strip())
    except ValueError:
        m = INTERVALO_PADRAO_MIN
    return max(5, min(1440, m)) * 60


def uma_rodada(raiz: Path = PROJECT_DIR, env=None, cliente=None):
    """Um envio automático. None quando não cabe (desligado, ou dentro do contêiner de continuidade); senão o resultado de enviar(). Nunca levanta erro."""
    e = _env_atual() if env is None else env
    if modo_continuidade(e) or not ligado(e):
        return None
    try:
        return enviar(raiz, e, cliente)
    except Exception as ex:  # noqa: BLE001 - o envio automático nunca derruba o agente
        return {"ok": False, "erro": str(ex)[:160]}


def vigiar(dormir=time.sleep, rodadas=None) -> None:
    """Laço do agente do Mac: envia à nuvem só os bancos que mudaram, a cada HEIMDALL_CONTINUIDADE_INTERVALO_MIN minutos, enquanto STUDIO_CONTINUIDADE=1."""
    feitas = 0
    while rodadas is None or feitas < rodadas:
        r = uma_rodada()
        if r is not None and (not r.get("ok") or r.get("enviados")):
            msg = f"erro: {r.get('erro', '?')}" if not r.get("ok") else f"enviados: {', '.join(r['enviados'])}"
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} continuidade: {msg}\n")
        feitas += 1
        dormir(intervalo_s())


def _preparar() -> int:
    backup._carregar_env()
    if os.environ.get("HEIMDALL_CONTINUIDADE_SENHA"):
        print("A senha das cópias de continuidade já existe no .env.")
        return 0
    import heimdall_config
    motivo = heimdall_config.salvar("HEIMDALL_CONTINUIDADE_SENHA", secrets.token_urlsafe(32))
    if motivo:
        print("Não consegui gravar no .env:", motivo)
        return 1
    print("Senha criada no .env (HEIMDALL_CONTINUIDADE_SENHA). Guarde também fora do Mac: sem ela a cópia não pode ser lida.")
    return 0


def main(argv) -> int:
    backup._carregar_env()
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "preparar":
            return _preparar()
        if cmd == "enviar":
            r = enviar()
        elif cmd == "status":
            r = status()
        elif cmd == "restaurar":
            r = restaurar(Path(argv[2]) if len(argv) > 2 else PROJECT_DIR)
        else:
            print(__doc__)
            return 2
    except Exception as ex:  # noqa: BLE001
        print(f"Erro: {ex}")
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
