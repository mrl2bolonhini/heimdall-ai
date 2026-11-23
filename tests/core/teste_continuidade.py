#!/usr/bin/env python3
"""Testa a cópia de continuidade: envio só do que mudou, cifra no Mac, restauração conferida, interruptor e caminhos seguros (R2 simulado)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import heimdall_continuidade as hc  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:400])


class S3Falso:
    def __init__(self):
        self.o, self.puts = {}, 0

    def put_object(self, Bucket, Key, Body):
        self.o[Key] = bytes(Body)
        self.puts += 1

    def get_object(self, Bucket, Key):
        if Key not in self.o:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.o[Key])}


def banco(p, linhas):
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    for l in linhas:
        con.execute("INSERT INTO t VALUES (?)", (l,))
    con.commit()
    con.close()


ENV = {"HEIMDALL_CONTINUIDADE": "1", "HEIMDALL_CONTINUIDADE_SENHA": "senha-de-teste", "HEIMDALL_R2_ENDPOINT": "https://x", "HEIMDALL_R2_BUCKET": "b",
       "HEIMDALL_R2_KEY_ID": "k", "HEIMDALL_R2_SECRET": "s"}
raiz = Path(tempfile.mkdtemp())
banco(raiz / "db" / "heimdall.db", ["segredo-de-saude-123"])
banco(raiz / "finance" / "financas.db", ["saldo-9999"])
(raiz / "db" / "leia.txt").write_text("fora")
confere("arquivos da cópia: só bancos e configurações de avisos", hc.arquivos(raiz) == ["db/heimdall.db", "finance/financas.db"], hc.arquivos(raiz))

r = hc.enviar(raiz, dict(ENV, HEIMDALL_CONTINUIDADE="0"), S3Falso())
confere("interruptor desligado não envia nada", r.get("desligado") is True)
s3 = S3Falso()
r = hc.enviar(raiz, ENV, s3)
confere("primeiro envio manda os dois bancos e o manifesto", sorted(r["enviados"]) == ["db/heimdall.db", "finance/financas.db"] and s3.puts == 3, (r, s3.puts))
confere("nada vai em texto claro para o R2", not any(b"segredo-de-saude-123" in v or b"saldo-9999" in v or b"SQLite format" in v for v in s3.o.values()))
puts = s3.puts
r = hc.enviar(raiz, ENV, s3)
confere("sem mudança não reenvia nada", r["enviados"] == [] and s3.puts == puts and len(r["iguais"]) == 2, (r, s3.puts))
banco(raiz / "finance" / "financas.db", ["novo-lancamento"])
r = hc.enviar(raiz, ENV, s3)
confere("só o banco que mudou é reenviado", r["enviados"] == ["finance/financas.db"], r)

destino = Path(tempfile.mkdtemp())
rr = hc.restaurar(destino, ENV, s3)
con = sqlite3.connect(destino / "finance" / "financas.db")
linhas = [x[0] for x in con.execute("SELECT v FROM t ORDER BY rowid")]
con.close()
confere("restauração devolve os dados do Mac", rr["ok"] and linhas == ["saldo-9999", "novo-lancamento"] and (destino / "db" / "heimdall.db").exists(), (rr, linhas))
confere("a cópia restaurada passa na integridade", sqlite3.connect(destino / "db" / "heimdall.db").execute("PRAGMA integrity_check").fetchone()[0] == "ok")

try:
    hc.restaurar(Path(tempfile.mkdtemp()), dict(ENV, HEIMDALL_CONTINUIDADE_SENHA="outra"), s3)
    confere("senha errada não restaura", False)
except Exception:  # noqa: BLE001
    confere("senha errada não restaura", True)
chave = hc._chave_objeto("db/heimdall.db")
s3.o[chave] = s3.o[hc._chave_objeto("finance/financas.db")]   # objeto trocado: a soma não confere
destino2 = Path(tempfile.mkdtemp())
try:
    hc.restaurar(destino2, ENV, s3)
    confere("cópia adulterada é recusada e não grava nada", False)
except Exception:  # noqa: BLE001
    confere("cópia adulterada é recusada e não grava nada", not any(destino2.rglob("*.db")))
try:
    hc.restaurar(Path(tempfile.mkdtemp()), ENV, S3Falso())
    confere("sem cópia no R2 dá erro claro", False)
except RuntimeError as ex:
    confere("sem cópia no R2 dá erro claro", "não há cópia" in str(ex))
st = hc.status(ENV, s3)
confere("status mostra a data e os arquivos", st["ok"] and st["quando"] and "finance/financas.db" in st["arquivos"], st)
try:
    hc.enviar(raiz, dict(ENV, HEIMDALL_CONTINUIDADE_SENHA=""), s3)
    confere("sem senha o envio falha", False)
except RuntimeError:
    confere("sem senha o envio falha", True)

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
