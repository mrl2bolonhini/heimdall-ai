#!/usr/bin/env python3
"""Testes da cópia de segurança (heimdall_backup.py), sem rede: R2 simulado e banco temporário.
Uso: python3 teste_backup.py"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hd_backup_"))
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "banco")

import heimdall_backup as B  # noqa: E402
import heimdall_banco as D  # noqa: E402

falhas = []


def ok(cond, msg):
    print(("ok   " if cond else "FALHA ") + msg)
    if not cond:
        falhas.append(msg)


class FakeS3:
    def __init__(self):
        self.o = {}

    def put_object(self, Bucket, Key, Body):
        self.o[Key] = Body

    def get_object(self, Bucket, Key):
        import io
        return {"Body": io.BytesIO(self.o[Key])}

    def list_objects_v2(self, Bucket, Prefix="", ContinuationToken=None):
        ks = sorted(k for k in self.o if k.startswith(Prefix))
        if ContinuationToken is None and len(ks) > 3:       # força paginação
            return {"Contents": [{"Key": k} for k in ks[:3]], "IsTruncated": True, "NextContinuationToken": "x"}
        return {"Contents": [{"Key": k} for k in (ks[3:] if ContinuationToken else ks)], "IsTruncated": False}

    def delete_object(self, Bucket, Key):
        self.o.pop(Key, None)


# 1. criptografia
blob = B.cifrar(b"dados secretos " * 100, "senha-boa")
ok(b"secretos" not in blob, "o conteúdo não aparece em claro")
ok(B.decifrar(blob, "senha-boa") == b"dados secretos " * 100, "decifra com a senha certa")
try:
    B.decifrar(blob, "errada")
    ok(False, "senha errada deveria falhar")
except ValueError as e:
    ok("senha errada" in str(e), "senha errada é recusada com mensagem clara")
adulterado = bytearray(blob)
adulterado[-5] ^= 1
try:
    B.decifrar(bytes(adulterado), "senha-boa")
    ok(False, "arquivo adulterado deveria falhar")
except ValueError:
    ok(True, "arquivo adulterado é recusado")
try:
    B.decifrar(b"lixo", "x")
    ok(False, "cabeçalho inválido deveria falhar")
except ValueError:
    ok(True, "arquivo que não é cópia é recusado")

# 2. retenção
base = datetime(2026, 11, 11, 3, 30)
nomes = [f"heimdall-{base - timedelta(days=i):%Y-%m-%dT%H%M}{B.EXT}" for i in range(200)]
manter = B.reter(nomes + ["qualquer-coisa.txt"])
ok(all(n in manter for n in sorted(nomes, reverse=True)[:14]), "mantém as 14 mais recentes")
meses = {n[9:16] for n in manter}
ok(len(meses) >= 6, f"cobre ao menos 6 meses ({len(meses)})")
ok(len(manter) <= 14 + 6, f"não guarda além do necessário ({len(manter)})")
ok("qualquer-coisa.txt" not in manter, "ignora arquivos que não são cópias")

# 3. banco real + fazer/verificar/restaurar
D.iniciar()
con = D.conectar()
con.execute("INSERT INTO triagem (id, criado, fonte, nivel, titulo, resumo, atualizado) VALUES ('t1','2026-11-11','justica','alto','Teste','r','2026-11-11')")
con.commit()
con.close()
pasta = TMP / "icloud"
env = {"HEIMDALL_BACKUP_SENHA": "s3nha", "HEIMDALL_BACKUP_DESTINO": str(pasta)}
r = B.fazer(env, agora=base)
ok(r["ok"] and (pasta / r["nome"]).exists(), "cópia gravada na pasta")
ok(not list(pasta.glob("*.parcial")), "sem arquivo parcial sobrando")
v = B.verificar(env)
d = next(iter(v.values()))
ok(d["ok"] and d["linhas_por_tabela"].get("triagem") == 1, "verificação decifra e acha a linha da triagem")
saida = TMP / "restaurado.db"
B.restaurar(str(pasta / r["nome"]), str(saida), env)
ok(sqlite3.connect(saida).execute("SELECT titulo FROM triagem").fetchone()[0] == "Teste", "restaurar devolve o banco")
try:
    B.restaurar(str(pasta / r["nome"]), str(saida), env)
    ok(False, "não deveria sobrescrever")
except RuntimeError:
    ok(True, "restaurar não sobrescreve arquivo existente")
ok(B.estado()["ultimo_ok"] is not None, "estado registra o último sucesso")

# 4. rotação numa pasta com muitas cópias
for i in range(1, 40):
    B.fazer(env, agora=base + timedelta(days=i))
ok(len(B.listar(env)[next(iter(B.listar(env)))]) <= 20, "a pasta é podada pela retenção")

# 5. R2 simulado + pasta; falha de um destino não impede o outro
s3 = FakeS3()
env2 = dict(env, HEIMDALL_R2_ENDPOINT="https://x", HEIMDALL_R2_BUCKET="b", HEIMDALL_R2_KEY_ID="k", HEIMDALL_R2_SECRET="s")
r = B.fazer(env2, cliente_r2=s3, agora=base + timedelta(days=100))
ok(r["ok"] and r["nome"] in s3.o and len(r["destinos"]) == 2, "envia ao R2 e à pasta")
ok(b"Teste" not in s3.o[r["nome"]], "o que vai ao R2 está criptografado")
v = B.verificar(env2, cliente_r2=s3)
ok(all(x["ok"] for x in v.values()) and len(v) == 2, "verifica os dois destinos")


class QuebradoS3(FakeS3):
    def put_object(self, **kw):
        raise ConnectionError("sem rede")


r = B.fazer(env2, cliente_r2=QuebradoS3(), agora=base + timedelta(days=101))
res = {x["destino"].split()[0]: x for x in r["destinos"]}
ok(not r["ok"] and res["R2"]["ok"] is False and res["pasta"]["ok"] is True, "R2 fora do ar: a pasta continua sendo gravada e o resultado acusa falha")
ok(B.estado()["ultima_tentativa"]["ok"] is False and B.estado()["ultimo_ok"], "estado guarda a falha sem apagar o último sucesso")

# 6. configuração faltando
for cfg, trecho in (({}, "SENHA"), ({"HEIMDALL_BACKUP_SENHA": "x"}, "destino")):
    try:
        B.fazer(cfg)
        ok(False, "deveria recusar sem configuração")
    except RuntimeError as e:
        ok(trecho in str(e), f"recusa com mensagem clara ({trecho})")

print()
print("TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S)")
sys.exit(1 if falhas else 0)
