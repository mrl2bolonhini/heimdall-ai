#!/usr/bin/env python3
"""Testes da cópia de segurança (heimdall_backup.py), sem rede: R2 simulado e banco temporário.
Uso: python3 tests/cloudflare/teste_backup.py"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hd_backup_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "banco")
os.environ["STUDIO_FINANCE_DIR"] = str(TMP / "finance")

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
env = {"STUDIO_BACKUP_SENHA": "s3nha", "STUDIO_BACKUP_DESTINO": str(pasta)}
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

# 6. bancos das pessoas: cópia própria em people/<id>/, separada da do dono e com a mesma retenção
with D.da_pessoa("convidada-1"):
    D.iniciar()
    c = D.conectar()
    c.execute("INSERT INTO triagem (id, criado, fonte, nivel, titulo, resumo, atualizado) VALUES ('p1','2026-11-11','justica','alto','Da convidada','r','2026-11-11')")
    c.commit()
    c.close()
(D.pasta_pessoas() / "Nome Invalido").mkdir(parents=True, exist_ok=True)   # pasta fora do padrão: ignorada
ok(B.pessoas() == ["convidada-1"], "acha só as pessoas com banco e nome válido")
s3p = FakeS3()
r = B.fazer(env2, cliente_r2=s3p, agora=base + timedelta(days=200))
ok(r["ok"] and r["pessoas"] and r["pessoas"][0]["pessoa"] == "convidada-1" and r["pessoas"][0]["ok"], "fazer inclui a cópia da pessoa")
chave = "people/convidada-1/" + r["nome"]
ok(chave in s3p.o and r["nome"] in s3p.o, "no R2, a cópia da pessoa fica em people/<id>/ e a do dono na raiz")
ok(b"Da convidada" not in s3p.o[chave], "a cópia da pessoa vai criptografada")
ok((pasta / "people" / "convidada-1" / r["nome"]).exists(), "na pasta, a cópia da pessoa fica em people/<id>/")
saida_p = TMP / "restaurado_pessoa.db"
B.restaurar(str(pasta / "people" / "convidada-1" / r["nome"]), str(saida_p), env)
titulos = [x[0] for x in sqlite3.connect(saida_p).execute("SELECT titulo FROM triagem")]
ok(titulos == ["Da convidada"], "a cópia da pessoa restaura só os dados dela")
titulos_dono = [x[0] for x in sqlite3.connect(TMP / "restaurado.db").execute("SELECT titulo FROM triagem")]
ok("Da convidada" not in titulos_dono, "a cópia do dono não traz os dados da pessoa")
v = B.verificar(env2, cliente_r2=s3p)
ok(any("people/convidada-1" in k for k in v) and all(x["ok"] for k, x in v.items() if "people/" in k), "verificar confere as cópias da pessoa")
l = B.listar(env2, cliente_r2=s3p)
ok(all(not n.startswith("people/") for k, ns in l.items() for n in ns), "listar devolve nomes sem o prefixo da pessoa")
for i in range(1, 30):
    B.fazer(env, agora=base + timedelta(days=200 + i))
ok(len(list((pasta / "people" / "convidada-1").glob("*" + B.EXT))) <= 20, "a retenção também poda as cópias da pessoa")
ok(len([n for n in B.listar(env)[next(iter(B.listar(env)))]]) <= 20, "a retenção do dono continua valendo")

# pessoa nova, ainda sem cópia: a verificação não acusa falha
with D.da_pessoa("convidada-2"):
    D.iniciar()
v = B.verificar(env)
nova = next(x for k, x in v.items() if "convidada-2" in k)
ok(nova["ok"] and "próxima cópia" in nova.get("aviso", ""), "pessoa sem cópia ainda não é falha na verificação")


class PessoaQuebrada(FakeS3):
    def put_object(self, Bucket, Key, Body):
        if Key.startswith("people/"):
            raise ConnectionError("sem rede")
        super().put_object(Bucket=Bucket, Key=Key, Body=Body)


antes = B.estado()["ultimo_ok"]
r = B.fazer(dict(env2, STUDIO_BACKUP_DESTINO=""), cliente_r2=PessoaQuebrada(), agora=base + timedelta(days=300))
ok(not r["ok"] and all(x["ok"] for x in r["destinos"]) and not all(p["ok"] for p in r["pessoas"]), "falha só na cópia de uma pessoa: resultado acusa a falha")
ok(B.estado()["ultimo_ok"] != antes and B.estado()["pessoas_ok"] is False, "a data do último sucesso segue a cópia do dono; a das pessoas fica registrada à parte")

# outros bancos da pasta (learn.db...): cópia própria na subpasta com o nome do banco, do dono e de cada pessoa
def _mini(caminho, valor):
    c = sqlite3.connect(caminho)
    c.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    c.execute("INSERT INTO t VALUES (?)", (valor,))
    c.commit()
    c.close()


_mini(D.DB_DIR / "learn.db", "estudo-do-dono")
_mini(D.pasta_pessoas() / "convidada-1" / "learn.db", "estudo-da-convidada")
(D.DB_DIR / "Estranho.DB").write_text("x")
ok([x.name for x in B.outros_bancos(D.DB_DIR)] == ["learn.db"], "outros bancos: só *.db de nome simples, sem o heimdall.db")
(TMP / "finance").mkdir(exist_ok=True)
_mini(TMP / "finance" / "financas.db", "saldo-do-dono")
ok([x.name for x in B.bancos_extras_do_dono()] == ["financas.db", "learn.db"], "bancos extras do dono: os da pasta db/ e os da pasta do Finance")
s3o = FakeS3()
r = B.fazer(env2, cliente_r2=s3o, agora=base + timedelta(days=400))
ok(r["ok"] and [x["banco"] for x in r["outros"]] == ["financas.db", "learn.db"] and r["pessoas"][0]["outros"][0]["banco"] == "learn.db", "fazer copia o learn.db do dono e o da pessoa")
ok(("learn/" + r["nome"]) in s3o.o and ("people/convidada-1/learn/" + r["nome"]) in s3o.o and r["nome"] in s3o.o, "no R2: learn/ e people/<id>/learn/, sem misturar com a cópia principal")
ok(b"estudo-do-dono" not in s3o.o["learn/" + r["nome"]], "o learn.db vai criptografado")
ok(("financas/" + r["nome"]) in s3o.o and b"saldo-do-dono" not in s3o.o["financas/" + r["nome"]], "o banco do Finance vai para financas/, criptografado")
ok((pasta / "learn" / r["nome"]).exists() and (pasta / "people" / "convidada-1" / "learn" / r["nome"]).exists(), "na pasta: learn/ e people/<id>/learn/")
saida_l = TMP / "restaurado_learn.db"
B.restaurar(str(pasta / "people" / "convidada-1" / "learn" / r["nome"]), str(saida_l), env)
ok([x[0] for x in sqlite3.connect(saida_l).execute("SELECT v FROM t")] == ["estudo-da-convidada"], "o learn.db da pessoa restaura só os dados dela")
v = B.verificar(env2, cliente_r2=s3o)
ok(all(x["ok"] for x in v.values()) and any(k.endswith(" / learn") for k in v) and any(k.endswith("people/convidada-1/learn") for k in v), "verificar confere os outros bancos")
ok(all(not n.startswith(("learn/", "people/")) for n in B.listar(env2, cliente_r2=s3o)[next(iter(B.listar(env2, cliente_r2=s3o)))]), "a lista principal não mistura os outros bancos")

# 7. configuração faltando
for cfg, trecho in (({}, "SENHA"), ({"STUDIO_BACKUP_SENHA": "x"}, "destino")):
    try:
        B.fazer(cfg)
        ok(False, "deveria recusar sem configuração")
    except RuntimeError as e:
        ok(trecho in str(e), f"recusa com mensagem clara ({trecho})")

print()
print("TUDO CERTO" if not falhas else f"{len(falhas)} FALHA(S)")
sys.exit(1 if falhas else 0)
