#!/usr/bin/env python3
"""Testa a cópia de continuidade: envio só do que mudou, cifra no Mac, restauração conferida, interruptor e caminhos seguros (R2 simulado)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import studio_continuidade as hc  # noqa: E402

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


ENV = {"STUDIO_CONTINUIDADE": "1", "HEIMDALL_CONTINUIDADE_SENHA": "senha-de-teste", "HEIMDALL_R2_ENDPOINT": "https://x", "HEIMDALL_R2_BUCKET": "b",
       "HEIMDALL_R2_KEY_ID": "k", "HEIMDALL_R2_SECRET": "s"}
raiz = Path(tempfile.mkdtemp())
banco(raiz / "db" / "heimdall.db", ["segredo-de-saude-123"])
banco(raiz / "finance" / "financas.db", ["saldo-9999"])
(raiz / "db" / "leia.txt").write_text("fora")
confere("arquivos da cópia: só bancos e configurações de avisos", hc.arquivos(raiz) == ["db/heimdall.db", "finance/financas.db"], hc.arquivos(raiz))
raiz_p = Path(tempfile.mkdtemp())
banco(raiz_p / "db" / "heimdall.db", ["dono"])
banco(raiz_p / "db" / "people" / "convidada-1" / "heimdall.db", ["dado-da-convidada"])
banco(raiz_p / "db" / "people" / "convidada-1" / "copies" / "heimdall-2026-11-25.db", ["copia-local"])
confere("o banco de cada pessoa entra na cópia; as cópias locais dela, não",
        hc.arquivos(raiz_p) == ["db/heimdall.db", "db/people/convidada-1/heimdall.db"], hc.arquivos(raiz_p))

r = hc.enviar(raiz, dict(ENV, STUDIO_CONTINUIDADE="0"), S3Falso())
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

# envio automático (agente do Mac)
s3a = S3Falso()
confere("envio automático desligado não faz nada", hc.uma_rodada(raiz, dict(ENV, STUDIO_CONTINUIDADE="0"), s3a) is None and s3a.puts == 0)
confere("dentro do contêiner de continuidade não envia", hc.uma_rodada(raiz, dict(ENV, HEIMDALL_CONTINUIDADE_MODO="1"), s3a) is None and s3a.puts == 0)
ra = hc.uma_rodada(raiz, ENV, s3a)
confere("envio automático manda o que mudou", ra["ok"] and sorted(ra["enviados"]) == ["db/heimdall.db", "finance/financas.db"], ra)
confere("envio automático seguinte não reenvia o que não mudou", hc.uma_rodada(raiz, ENV, s3a)["enviados"] == [])
confere("falha no envio automático vira resultado, não exceção", hc.uma_rodada(raiz, dict(ENV, HEIMDALL_CONTINUIDADE_SENHA=""), s3a)["ok"] is False)
confere("intervalo: padrão 60 min, mínimo 5, máximo 1440, valor ruim volta ao padrão", hc.intervalo_s({}) == 3600 and hc.intervalo_s({"HEIMDALL_CONTINUIDADE_INTERVALO_MIN": "1"}) == 300
        and hc.intervalo_s({"HEIMDALL_CONTINUIDADE_INTERVALO_MIN": "99999"}) == 86400 and hc.intervalo_s({"HEIMDALL_CONTINUIDADE_INTERVALO_MIN": "x"}) == 3600)
_dormiu = []
_real = hc.uma_rodada
hc.uma_rodada = lambda *a, **k: None   # o laço do teste nunca envia nada de verdade
hc.vigiar(dormir=_dormiu.append, rodadas=2)
hc.uma_rodada = _real
confere("o laço dorme o intervalo entre as rodadas e termina quando pedido", len(_dormiu) == 2 and all(d >= 300 for d in _dormiu), _dormiu)

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
