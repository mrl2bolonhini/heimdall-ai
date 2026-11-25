#!/usr/bin/env python3
"""Cópia de segurança criptografada do banco pessoal do Heimdall.

O que faz: tira uma cópia consistente do banco (SQLite .backup), confere a integridade, comprime,
criptografa com AES-256-GCM (chave derivada da senha com scrypt) e grava em um ou mais destinos:
  - uma pasta (por exemplo no iCloud Drive: o Mac já sincroniza para fora dele);
  - um bucket do Cloudflare R2 (API compatível com S3, via boto3).
Mantém as 14 cópias mais recentes e a mais nova de cada um dos 6 últimos meses.
O banco de cada pessoa (db/people/<id>/heimdall.db) tem cópias próprias, na subpasta people/<id>/ de cada destino,
com a mesma senha e a mesma retenção, contadas separadamente das do dono.
Os demais bancos da mesma pasta (learn.db, avisos_saude.db...) também entram, cada um na subpasta com o nome dele
(learn/, avisos_saude/; para uma pessoa, people/<id>/learn/). As cópias locais (copies/) não entram.

Configuração (no .env, nunca no Git):
    HEIMDALL_BACKUP_SENHA   senha das cópias (gerada por:  python3 heimdall_backup.py preparar)
    HEIMDALL_BACKUP_DESTINO pasta de destino (opcional), ex.: ~/Library/Mobile Documents/com~apple~CloudDocs/Heimdall-backup
    HEIMDALL_R2_ENDPOINT    https://<id da conta>.r2.cloudflarestorage.com   (opcional, junto com as três abaixo)
    HEIMDALL_R2_BUCKET, HEIMDALL_R2_KEY_ID, HEIMDALL_R2_SECRET

Uso:
    python3 heimdall_backup.py preparar            gera a senha no .env (se ainda não existir)
    python3 heimdall_backup.py senha               mostra a senha, para guardar num gerenciador de senhas
    python3 heimdall_backup.py fazer               faz a cópia agora e envia aos destinos
    python3 heimdall_backup.py verificar           baixa a mais recente, decifra e confere a integridade
    python3 heimdall_backup.py listar              lista as cópias de cada destino
    python3 heimdall_backup.py restaurar ARQ SAÍDA decifra ARQ para o arquivo SAÍDA (não sobrescreve nada existente)

Sem a senha as cópias não podem ser lidas: guarde-a fora do Mac.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import zlib
from datetime import datetime
from pathlib import Path

import heimdall_banco as banco

PROJECT_DIR = Path(__file__).resolve().parent
MAGIA = b"HDBK1"
EXT = ".db.hdbk"
PADRAO_NOME = re.compile(r"^heimdall-(\d{4})-(\d{2})-(\d{2})T(\d{4})\.db\.hdbk$")
MANTER_RECENTES = 14
MANTER_MESES = 6
_trava = threading.Lock()


# ---------------------------------------------------------------- criptografia

def _chave(senha: str, sal: bytes) -> bytes:
    return hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=2 ** 15, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024)


def cifrar(dados: bytes, senha: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    sal, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    cab = MAGIA + sal + nonce
    return cab + AESGCM(_chave(senha, sal)).encrypt(nonce, zlib.compress(dados, 6), MAGIA)


def decifrar(blob: bytes, senha: str) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(MAGIA) or len(blob) < len(MAGIA) + 28:
        raise ValueError("não é uma cópia do Heimdall (cabeçalho inválido)")
    sal = blob[len(MAGIA):len(MAGIA) + 16]
    nonce = blob[len(MAGIA) + 16:len(MAGIA) + 28]
    try:
        return zlib.decompress(AESGCM(_chave(senha, sal)).decrypt(nonce, blob[len(MAGIA) + 28:], MAGIA))
    except InvalidTag:
        raise ValueError("senha errada ou arquivo corrompido") from None


# ---------------------------------------------------------------- retenção

def reter(nomes):
    """Dos nomes de cópias, devolve quais MANTER: as 14 mais recentes e a mais nova de cada um dos 6 últimos meses."""
    validos = sorted((n for n in nomes if PADRAO_NOME.match(n)), reverse=True)   # o nome ordena por data
    manter = set(validos[:MANTER_RECENTES])
    por_mes = {}
    for n in validos:
        por_mes.setdefault(n[9:16], n)                                            # 'AAAA-MM' -> a mais nova (primeira vista)
    for mes in sorted(por_mes, reverse=True)[:MANTER_MESES]:
        manter.add(por_mes[mes])
    return manter


# ---------------------------------------------------------------- destinos

class DestinoPasta:
    def __init__(self, pasta, sub=""):
        self.nome = f"pasta {pasta}"
        self.pasta = Path(pasta).expanduser() / sub if sub else Path(pasta).expanduser()

    def sub(self, caminho):
        d = DestinoPasta.__new__(DestinoPasta)
        d.nome, d.pasta = self.nome, self.pasta / caminho
        return d

    def da_pessoa(self, pessoa):
        return self.sub(f"people/{pessoa}")

    def enviar(self, nome, blob):
        self.pasta.mkdir(parents=True, exist_ok=True)
        tmp = self.pasta / (nome + ".parcial")
        tmp.write_bytes(blob)
        os.replace(tmp, self.pasta / nome)

    def listar(self):
        return sorted(p.name for p in self.pasta.glob("heimdall-*" + EXT)) if self.pasta.is_dir() else []

    def ler(self, nome):
        return (self.pasta / nome).read_bytes()

    def apagar(self, nome):
        (self.pasta / nome).unlink()


class DestinoR2:
    def __init__(self, cfg, cliente=None):
        self.nome = f"R2 {cfg['bucket']}"
        self.bucket = cfg["bucket"]
        self.prefixo = ""
        if cliente is None:
            import boto3
            cliente = boto3.client("s3", endpoint_url=cfg["endpoint"], aws_access_key_id=cfg["key_id"],
                                   aws_secret_access_key=cfg["secret"], region_name="auto")
        self.c = cliente

    def sub(self, caminho):
        d = DestinoR2.__new__(DestinoR2)
        d.nome, d.bucket, d.c, d.prefixo = self.nome, self.bucket, self.c, self.prefixo + caminho.strip("/") + "/"
        return d

    def da_pessoa(self, pessoa):
        return self.sub(f"people/{pessoa}")

    def enviar(self, nome, blob):
        self.c.put_object(Bucket=self.bucket, Key=self.prefixo + nome, Body=blob)

    def listar(self):
        nomes, token = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": self.prefixo + "heimdall-"}
            if token:
                kw["ContinuationToken"] = token
            r = self.c.list_objects_v2(**kw)
            nomes += [o["Key"][len(self.prefixo):] for o in r.get("Contents", []) if o["Key"].endswith(EXT)]
            if not r.get("IsTruncated"):
                return sorted(nomes)
            token = r.get("NextContinuationToken")

    def ler(self, nome):
        return self.c.get_object(Bucket=self.bucket, Key=self.prefixo + nome)["Body"].read()

    def apagar(self, nome):
        self.c.delete_object(Bucket=self.bucket, Key=self.prefixo + nome)


def _env(env=None):
    return os.environ if env is None else env


def destinos(env=None, cliente_r2=None):
    e = _env(env)
    lista = []
    if e.get("HEIMDALL_BACKUP_DESTINO", "").strip():
        lista.append(DestinoPasta(e["HEIMDALL_BACKUP_DESTINO"].strip()))
    r2 = {"endpoint": e.get("HEIMDALL_R2_ENDPOINT", "").strip(), "bucket": e.get("HEIMDALL_R2_BUCKET", "").strip(),
          "key_id": e.get("HEIMDALL_R2_KEY_ID", "").strip(), "secret": e.get("HEIMDALL_R2_SECRET", "").strip()}
    if all(r2.values()):
        lista.append(DestinoR2(r2, cliente_r2))
    return lista


# ---------------------------------------------------------------- operações

def _arquivo_estado():
    return banco.DB_DIR / "backup_estado.json"


def _grava_estado(estado):
    try:
        banco.DB_DIR.mkdir(parents=True, exist_ok=True)
        _arquivo_estado().write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def estado():
    try:
        return json.loads(_arquivo_estado().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ultimo_ok": None}


_NOME_BANCO = re.compile(r"^[a-z0-9_]{1,40}\.db$")


def outros_bancos(pasta: Path) -> list:
    """Bancos SQLite da pasta além do heimdall.db (learn.db, avisos_saude.db...), em ordem. Só nomes simples; nada de subpastas."""
    if not Path(pasta).is_dir():
        return []
    return sorted(p for p in Path(pasta).iterdir() if p.is_file() and not p.is_symlink() and _NOME_BANCO.match(p.name) and p.name != "heimdall.db")


def _copia_de_arquivo(arquivo: Path) -> bytes:
    """Cópia consistente e conferida de um banco SQLite qualquer, aberto só para leitura."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "copia.db"
        origem = sqlite3.connect(f"file:{arquivo}?mode=ro", uri=True, timeout=10)
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
            raise RuntimeError(f"{arquivo.name} falhou na conferência de integridade: {ok}")
        return tmp.read_bytes()


def _copias_dos_outros(dests, pasta: Path, nome: str, senha: str, rotulo: str = "") -> list:
    """Uma cópia cifrada por banco extra da pasta, na subpasta <nome do banco>/ de cada destino. Um banco com problema não impede os outros."""
    saida = []
    for arq in outros_bancos(pasta):
        sub = arq.stem
        try:
            blob = cifrar(_copia_de_arquivo(arq), senha)
            res = _enviar([d.sub(sub) for d in dests], nome, blob)
            saida.append({"banco": (rotulo + "/" if rotulo else "") + arq.name, "ok": all(r["ok"] for r in res), "destinos": res})
        except Exception as ex:  # noqa: BLE001
            saida.append({"banco": (rotulo + "/" if rotulo else "") + arq.name, "ok": False, "erro": str(ex)[:200]})
    return saida


def _copia_consistente() -> bytes:
    if not banco.caminho().exists():
        raise RuntimeError("o banco ainda não existe; nada para copiar")
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "copia.db"
        origem = banco.conectar()
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
            raise RuntimeError(f"o banco falhou na conferência de integridade: {ok}")
        return tmp.read_bytes()


def pessoas() -> list:
    """Identificadores das pessoas que já têm banco próprio (db/people/<id>/heimdall.db), em ordem."""
    raiz = banco.pasta_pessoas()
    if not raiz.is_dir():
        return []
    return sorted(p.name for p in raiz.iterdir() if banco.nome_de_pessoa_valido(p.name) and (p / "heimdall.db").is_file())


def _enviar(dests, nome, blob):
    res = []
    for d in dests:
        try:
            d.enviar(nome, blob)
            if d.ler(nome) != blob:   # confere o que foi gravado
                raise RuntimeError("o arquivo gravado não confere com o enviado")
            manter = reter(d.listar())
            for velho in d.listar():
                if velho not in manter:
                    d.apagar(velho)
            res.append({"destino": d.nome, "ok": True})
        except Exception as ex:  # noqa: BLE001 - um destino com problema não pode impedir os outros
            res.append({"destino": d.nome, "ok": False, "erro": str(ex)[:200]})
    return res


def _copias_das_pessoas(dests, nome, senha):
    """Uma cópia cifrada por pessoa, na subpasta people/<id>/ de cada destino. Um banco com problema não impede os outros."""
    saida = []
    for p in pessoas():
        try:
            with banco.da_pessoa(p):
                blob = cifrar(_copia_consistente(), senha)
            res = _enviar([d.da_pessoa(p) for d in dests], nome, blob)
            extras = _copias_dos_outros([d.da_pessoa(p) for d in dests], banco.pasta_pessoas() / p, nome, senha)
            saida.append({"pessoa": p, "ok": all(r["ok"] for r in res) and all(x["ok"] for x in extras), "destinos": res, "outros": extras})
        except Exception as ex:  # noqa: BLE001
            saida.append({"pessoa": p, "ok": False, "erro": str(ex)[:200]})
    return saida


def fazer(env=None, cliente_r2=None, agora=None):
    """Faz a cópia do banco do dono e do banco de cada pessoa e envia a todos os destinos.
    Devolve {ok, nome, destinos:[{destino, ok, erro?}], pessoas:[{pessoa, ok, ...}]}; ok só se TUDO deu certo."""
    e = _env(env)
    senha = e.get("HEIMDALL_BACKUP_SENHA", "")
    if not senha:
        raise RuntimeError("falta HEIMDALL_BACKUP_SENHA no .env (rode: python3 heimdall_backup.py preparar)")
    dests = destinos(e, cliente_r2)
    if not dests:
        raise RuntimeError("nenhum destino configurado (HEIMDALL_BACKUP_DESTINO ou as variáveis HEIMDALL_R2_*)")
    with _trava:
        agora = agora or datetime.now()
        nome = f"heimdall-{agora:%Y-%m-%dT%H%M}{EXT}"
        blob = cifrar(_copia_consistente(), senha)
        res = _enviar(dests, nome, blob)
        outros = _copias_dos_outros(dests, banco.DB_DIR, nome, senha)
        das_pessoas = _copias_das_pessoas(dests, nome, senha)
        saida = {"ok": all(r["ok"] for r in res) and all(x["ok"] for x in outros) and all(p["ok"] for p in das_pessoas), "nome": nome, "bytes": len(blob),
                 "destinos": res, "outros": outros, "pessoas": das_pessoas, "quando": agora.isoformat(timespec="seconds")}
        est = estado()
        est.update({"ultima_tentativa": saida})
        if all(r["ok"] for r in res) and all(x["ok"] for x in outros):   # a data do último sucesso segue os bancos do dono; os das pessoas têm resultado próprio
            est["ultimo_ok"] = saida["quando"]
        est["pessoas_ok"] = all(p["ok"] for p in das_pessoas)
        _grava_estado(est)
        return saida


def listar(env=None, cliente_r2=None):
    """Cópias do dono por destino; as de cada pessoa aparecem como "<destino> / people/<id>"."""
    saida = {}
    for d in destinos(env, cliente_r2):
        saida[d.nome] = d.listar()
        for arq in outros_bancos(banco.DB_DIR):
            saida[f"{d.nome} / {arq.stem}"] = d.sub(arq.stem).listar()
        for p in pessoas():
            saida[f"{d.nome} / people/{p}"] = d.da_pessoa(p).listar()
            for arq in outros_bancos(banco.pasta_pessoas() / p):
                saida[f"{d.nome} / people/{p}/{arq.stem}"] = d.da_pessoa(p).sub(arq.stem).listar()
    return saida


def _verificar_destino(d, senha, nova_ok=False):
    """`nova_ok`: banco de pessoa ainda sem nenhuma cópia (criado depois da última cópia diária) não é falha; entra na próxima cópia."""
    nomes = d.listar()
    if not nomes:
        if nova_ok:
            return {"ok": True, "aviso": "ainda sem cópia; entra na próxima cópia diária"}
        return {"ok": False, "erro": "nenhuma cópia encontrada"}
    try:
        dados = decifrar(d.ler(nomes[-1]), senha)
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "v.db"
            p.write_bytes(dados)
            con = sqlite3.connect(p)
            try:
                integ = con.execute("PRAGMA integrity_check").fetchone()[0]
                tabelas = {r[0]: con.execute(f'SELECT COUNT(*) FROM "{r[0]}"').fetchone()[0]
                           for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            finally:
                con.close()
        return {"ok": integ == "ok", "copia": nomes[-1], "integridade": integ, "linhas_por_tabela": tabelas}
    except Exception as ex:  # noqa: BLE001
        return {"ok": False, "copia": nomes[-1], "erro": str(ex)[:200]}


def verificar(env=None, cliente_r2=None):
    """Baixa a cópia mais recente de cada destino (a do dono e a de cada pessoa), decifra e confere a integridade e as tabelas."""
    e = _env(env)
    senha = e.get("HEIMDALL_BACKUP_SENHA", "")
    if not senha:
        raise RuntimeError("falta HEIMDALL_BACKUP_SENHA no .env")
    saida = {}
    for d in destinos(e, cliente_r2):
        saida[d.nome] = _verificar_destino(d, senha)
        for arq in outros_bancos(banco.DB_DIR):   # banco extra criado depois da última cópia diária entra na próxima: não é falha
            saida[f"{d.nome} / {arq.stem}"] = _verificar_destino(d.sub(arq.stem), senha, nova_ok=True)
        for p in pessoas():
            saida[f"{d.nome} / people/{p}"] = _verificar_destino(d.da_pessoa(p), senha, nova_ok=True)
            for arq in outros_bancos(banco.pasta_pessoas() / p):
                saida[f"{d.nome} / people/{p}/{arq.stem}"] = _verificar_destino(d.da_pessoa(p).sub(arq.stem), senha, nova_ok=True)
    return saida


def restaurar(arquivo, saida, env=None):
    senha = _env(env).get("HEIMDALL_BACKUP_SENHA", "")
    if not senha:
        raise RuntimeError("falta HEIMDALL_BACKUP_SENHA no .env")
    saida = Path(saida).expanduser()
    if saida.exists():
        raise RuntimeError(f"{saida} já existe; escolha outro nome (por segurança, nada é sobrescrito)")
    saida.write_bytes(decifrar(Path(arquivo).expanduser().read_bytes(), senha))
    return str(saida)


# ---------------------------------------------------------------- linha de comando

def _preparar():
    env = PROJECT_DIR / ".env"
    texto = env.read_text(encoding="utf-8") if env.exists() else ""
    if "HEIMDALL_BACKUP_SENHA=" in texto:
        print("A senha das cópias já existe no .env. Para ouvi-la: python3 heimdall_backup.py senha")
        return
    senha = secrets.token_urlsafe(24)
    with env.open("a", encoding="utf-8") as f:
        f.write(("" if texto.endswith("\n") or not texto else "\n") + f"HEIMDALL_BACKUP_SENHA='{senha}'\n")
    print("Senha das cópias gerada e gravada no .env.")
    print("Guarde-a também fora do Mac (gerenciador de senhas): sem ela as cópias não abrem. Para ouvi-la: python3 heimdall_backup.py senha")


def _carregar_env():
    f = PROJECT_DIR / ".env"
    if not f.exists():
        return
    for linha in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", linha)
        if m and m.group(1) not in os.environ:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            os.environ[m.group(1)] = v


def main(argv):
    _carregar_env()
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "preparar":
            return _preparar() or 0
        if cmd == "senha":
            print(os.environ.get("HEIMDALL_BACKUP_SENHA", "(ainda não existe; rode: python3 heimdall_backup.py preparar)"))
            return 0
        if cmd == "fazer":
            r = fazer()
        elif cmd == "listar":
            r = listar()
        elif cmd == "verificar":
            r = verificar()
        elif cmd == "restaurar" and len(argv) == 4:
            r = {"restaurado_em": restaurar(argv[2], argv[3])}
        else:
            print(__doc__)
            return 2
    except Exception as ex:  # noqa: BLE001
        print("ERRO:", ex)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=1))
    ok = r.get("ok", True) if isinstance(r, dict) else True
    if cmd == "verificar":
        ok = all(v.get("ok") for v in r.values()) if r else False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
