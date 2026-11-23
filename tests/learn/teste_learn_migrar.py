#!/usr/bin/env python3
"""Testa a migração dos estudos do Notes para o Learn: notas do cofre, áudios, tabela estudos, idempotência, nada apagado e a tela do estudo importado."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

TMP = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")
os.environ["HEIMDALL_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
os.environ["HEIMDALL_VAULT_DIR"] = str(TMP / "brain")
os.environ["HEIMDALL_AVISOS_MAC"] = "0"
(TMP / "knowledge").mkdir()

import heimdall_cloud as nuvem  # noqa: E402
import heimdall_learn as site  # noqa: E402
import heimdall_learn_dados as d  # noqa: E402
import heimdall_learn_estudo as es  # noqa: E402
import heimdall_learn_migrar as mg  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


# pastas do Learn (já existiam em knowledge/) e cofre
for nome in ("Arquitetura e Engenharia de Dados", "Esoterismo e Mistissismo"):
    (TMP / "knowledge" / nome).mkdir()
d.sincronizar()
B = TMP / "brain"
(B / "arquitetura-e-engenharia-de-dados" / "audio").mkdir(parents=True)
(B / "esoterismo-e-mistissismo").mkdir()
(B / "heimdall-privacidade").mkdir()
(B / "heimdall-privacidade" / "relatorio.md").write_text("# Relatório\n\nPergunta: nada disso é estudo.\n", encoding="utf-8")
NOVA = """# Arquitetura com cache e priorização

Estudo de 21/11/2026 às 06h. Tema: arquitetura-e-engenharia-de-dados. Livro: Fundamentos da arquitetura de software 2ª edição.

## Pergunta

Como a equipe mitigou o risco de sobrecarga?

## Resposta (confira só depois de tentar)

Criaram dois canais de mensagens e um cache.

## Leitura (trecho de Fundamentos da arquitetura de software 2ª edição)

A equipe usou filas assíncronas para priorizar pedidos.

## Para aprofundar (artigos)

1. Performance: decisão arquitetural | Alura - https://www.alura.com.br/x
2. Outro artigo - https://exemplo.com/y
"""
ANTIGA = """# Estudo 2026-11-09 12h: ETL versus ELT

Tema: arquitetura-e-engenharia-de-dados. Livro: Fundamentos de Engenharia de Dados.

## Pergunta

Qual a diferença entre ETL e ELT?

## Resposta (confira só depois de tentar)

No ETL se transforma antes de carregar; no ELT, depois.

## Leitura (trecho de Fundamentos de Engenharia de Dados)

O texto compara ETL e ELT.
"""
(B / "arquitetura-e-engenharia-de-dados" / "arquitetura-com-cache.md").write_text(NOVA, encoding="utf-8")
(B / "arquitetura-e-engenharia-de-dados" / "estudo-2026-11-09-12h-etl.md").write_text(ANTIGA + "\x00lixo", encoding="utf-8")
(B / "arquitetura-e-engenharia-de-dados" / "estudo-2026-11-09-20h-sem-pergunta.md").write_text("# Estudo 2026-11-09 20h: Framework AWS\n\nTema: arquitetura-e-engenharia-de-dados. Livro: Framework AWS.\n\n## Pergunta e resposta\n\n(O modelo não devolveu uma pergunta utilizável desta vez; a leitura abaixo continua valendo.)\n\n## Leitura (trecho de Framework AWS)\n\nTRECHO-SEM-PERGUNTA sobre malha de dados.\n", encoding="utf-8")
(B / "arquitetura-e-engenharia-de-dados" / "indice.md").write_text("# Índice\n\nSó um índice, sem pergunta.\n", encoding="utf-8")
(B / "arquitetura-e-engenharia-de-dados" / "audio" / "arquitetura-com-cache.m4a").write_bytes(b"AUDIO-FALSO")
(B / "esoterismo-e-mistissismo" / "alma.md").write_text(NOVA.replace("arquitetura-e-engenharia-de-dados", "esoterismo-e-mistissismo").replace("Arquitetura com cache e priorização", "A alma"), encoding="utf-8")
# banco principal: uma linha que tem nota (não duplica), uma só do banco, uma de tema sem pasta
bp = TMP / "db" / "heimdall.db"
bp.parent.mkdir(exist_ok=True)
c = sqlite3.connect(bp)
c.execute("CREATE TABLE estudos (id TEXT PRIMARY KEY, dia TEXT, hora TEXT, tema TEXT, livro TEXT, conceito TEXT, pergunta TEXT, resposta TEXT, artigos TEXT, atualizado TEXT)")
c.execute("INSERT INTO estudos VALUES ('1','2026-11-21','06','arquitetura-e-engenharia-de-dados','Fundamentos da arquitetura','Arquitetura com cache e priorização','P1','R1','[]','x')")
c.execute("INSERT INTO estudos VALUES ('2','2026-11-11','06','esoterismo-e-mistissismo','A Vós Confio','Controle da ira e perdão','Qual é o ensinamento sobre a cólera?','A cólera leva ao arrependimento.',?, 'x')",
          (json.dumps([{"titulo": "Esoterismo e Psicoesfera", "url": "https://e.com/p"}]),))
c.execute("INSERT INTO estudos VALUES ('3','2026-11-12','13','geral','L','Algo','P3','R3','[]','x')")
c.commit()
c.close()
antes = {p: p.read_bytes() for p in B.rglob("*") if p.is_file()}

# leitura das notas
n = mg.ler_nota(B / "arquitetura-e-engenharia-de-dados" / "arquitetura-com-cache.md")
confere("nota nova: título, dia, hora, tema, livro, pergunta, resposta, leitura e artigos", n["titulo"] == "Arquitetura com cache e priorização" and n["dia"] == "2026-11-21" and n["hora"] == "06"
        and n["livro"].startswith("Fundamentos da arquitetura") and n["pergunta"].startswith("Como a equipe") and n["resposta"].startswith("Criaram") and "filas" in n["leitura"] and len(n["artigos"]) == 2 and n["artigos"][0].startswith("Performance"), n)
n2 = mg.ler_nota(B / "arquitetura-e-engenharia-de-dados" / "estudo-2026-11-09-12h-etl.md")
confere("nota no formato antigo: dia e hora vêm do título, e caractere nulo é ignorado", n2["dia"] == "2026-11-09" and n2["hora"] == "12" and n2["titulo"] == "ETL versus ELT" and n2["livro"] == "Fundamentos de Engenharia de Dados" and "\x00" not in n2["leitura"] and n2["livro"].endswith("Dados"), n2)
ns = mg.ler_nota(B / "arquitetura-e-engenharia-de-dados" / "estudo-2026-11-09-20h-sem-pergunta.md")
confere("nota dos primeiros dias, sem pergunta mas com leitura, é lida como sem_pergunta", ns.get("sem_pergunta") is True and "TRECHO-SEM-PERGUNTA" in ns["leitura"] and ns["dia"] == "2026-11-09" and ns["hora"] == "20", ns)
confere("arquivo sem pergunta e resposta não é nota de estudo", mg.ler_nota(B / "arquitetura-e-engenharia-de-dados" / "indice.md") == {})

# simulação não grava
r = mg.migrar(False)
confere("sem --apply só conta e não grava nada", r["notas"] == 4 and r["banco"] == 1 and not r["aplicado"] and d.conectar().execute("SELECT COUNT(*) FROM estudos").fetchone()[0] == 0, r)
confere("avisos: índice fica de fora e tema geral não tem pasta", any("indice.md" in a for a in r["avisos"]) and any("geral" in a for a in r["avisos"]), r["avisos"])
confere("pasta de privacidade não é tratada como estudo", not any("privacidade" in a or "relatorio" in a for a in r["avisos"]))

# importa
r = mg.migrar(True)
con = d.conectar()
linhas = [dict(x) for x in con.execute("SELECT * FROM estudos ORDER BY id")]
confere("importou 4 notas (uma sem pergunta) e 1 linha só do banco, com 1 áudio", r["notas"] == 4 and r["banco"] == 1 and r["audios"] == 1 and len(linhas) == 5, r)
sp = d.conectar().execute("SELECT estado, pergunta, trecho, erro FROM estudos WHERE trecho LIKE '%TRECHO-SEM-PERGUNTA%'").fetchone()
confere("a nota sem pergunta entra em erro com o trecho, pronta para Tentar de novo", sp and sp["estado"] == "erro" and sp["pergunta"] == "" and "Tentar de novo" in sp["erro"], dict(sp) if sp else None)
nova = next(x for x in linhas if x["titulo"] == "Arquitetura com cache e priorização")
confere("estudo importado: pasta certa, estado, origem, data, pergunta, leitura e artigos", nova["pasta"] == "Arquitetura e Engenharia de Dados" and nova["estado"] == "importado" and nova["origem"] == "nota" and nova["criado"] == "2026-11-21 06:00:00"
        and nova["pergunta"].startswith("Como a equipe") and "filas" in nova["trecho"] and "Alura" in nova["sugestoes"] and nova["correcao"].startswith("Resposta esperada"), nova)
confere("a linha do banco que já tinha nota não duplicou", sum(1 for x in linhas if x["titulo"] == "Arquitetura com cache e priorização") == 1 and not any(x["pergunta"] == "P1" for x in linhas))
so_banco = next(x for x in linhas if x["origem"] == "banco")
confere("estudo só do banco entra na pasta do tema, com artigos", so_banco["pasta"] == "Esoterismo e Mistissismo" and so_banco["titulo"] == "Controle da ira e perdão" and "https://e.com/p" in so_banco["sugestoes"] and so_banco["trecho"] == "")
confere("tema sem pasta no Learn não foi importado", not any(x["pergunta"] == "P3" for x in linhas))
aud = d.pasta_dados() / "audio" / f"estudo-{nova['id']}.m4a"
confere("áudio copiado com o nome do estudo e permissão 600", aud.is_file() and aud.read_bytes() == b"AUDIO-FALSO" and oct(aud.stat().st_mode & 0o777) == "0o600" and nova["audio"] == aud.name)
confere("nada foi apagado nem alterado no cofre", all(p.exists() and p.read_bytes() == v for p, v in antes.items()))
confere("o banco principal não foi alterado", sqlite3.connect(bp).execute("SELECT COUNT(*) FROM estudos").fetchone()[0] == 3)

# idempotência
r2 = mg.migrar(True)
confere("rodar de novo não duplica", r2["notas"] == 0 and r2["banco"] == 0 and r2["ja_importados"] == 5 and con.execute("SELECT COUNT(*) FROM estudos").fetchone()[0] == 5, r2)
confere("resumo em texto", "Já estavam no Learn: 5" in mg.texto_resumo(r2) and "Nada foi apagado" in mg.texto_resumo(r2))

# schema antigo: banco do Learn sem as colunas novas ganha as colunas
arq = TMP / "velho" / "learn.db"
arq.parent.mkdir()
v = sqlite3.connect(arq)
v.execute("CREATE TABLE estudos (id INTEGER PRIMARY KEY AUTOINCREMENT, pasta TEXT NOT NULL, documento TEXT NOT NULL, trecho_idx INTEGER NOT NULL, trecho TEXT NOT NULL, pergunta TEXT NOT NULL DEFAULT '', resposta TEXT NOT NULL DEFAULT '', correcao TEXT NOT NULL DEFAULT '', sugestoes TEXT NOT NULL DEFAULT '', audio TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'sorteado', erro TEXT NOT NULL DEFAULT '', criado TEXT NOT NULL)")
v.commit()
v.close()
os.environ["HEIMDALL_DB_DIR"] = str(arq.parent)
cols = {x[1] for x in d.conectar().execute("PRAGMA table_info(estudos)")}
confere("banco do Learn já existente ganha as colunas novas sem perder nada", {"titulo", "origem", "chave"} <= cols)
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")

# tela
srv = ThreadingHTTPServer(("127.0.0.1", 0), site.Learn)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
token, _ = nuvem.nova_sessao("*")


def req(metodo, caminho, corpo=None, cab=None):
    cx = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Host": "localhost", "Cookie": f"{nuvem.COOKIE}={token}"}
    h.update(cab or {})
    cx.request(metodo, caminho, body=corpo, headers=h)
    rr = cx.getresponse()
    return rr.status, rr.read().decode("utf-8", "replace"), rr


st, pag, _ = req("GET", f"/estudo?id={nova['id']}")
confere("tela do estudo importado: título, pergunta, resposta escondida em details, leitura, áudio e artigos",
        st == 200 and "Arquitetura com cache e priorização" in pag and "<details><summary>Resposta esperada" in pag and "Criaram dois canais" in pag and "filas assíncronas" in pag
        and f'src="/audio?id={nova["id"]}"' in pag and "Alura" in pag and 'for="resposta"' in pag, re.sub(r"<[^>]+>", " ", pag)[:400])
st, aud_resp, _ = req("GET", f"/audio?id={nova['id']}")
confere("o áudio importado toca", st == 200 and aud_resp == "AUDIO-FALSO")
_, pasta, _ = req("GET", "/estudos?t=" + "Arquitetura%20e%20Engenharia%20de%20Dados")
confere("a aba Estudos do tema lista o estudo importado", "importado" in pasta.lower() or "Como a equipe" in pasta)

# responder um estudo importado usa a correção normal
es._modelo = lambda sistema, usuario, max_tokens=900: "Parcial. Faltou citar o cache.\nSUGESTÕES: filas; cache"
_, pag, _ = req("GET", "/ajustes")
csrf = re.search(r'name="csrf" value="([^"]+)"', pag).group(1)
st, _, r = req("POST", "/responder", urlencode({"csrf": csrf, "id": nova["id"], "resposta": "Dois canais de mensagens."}), {"Content-Type": "application/x-www-form-urlencoded"})
for _ in range(60):
    if es.obter(nova["id"])["estado"] == "corrigido":
        break
    time.sleep(0.1)
confere("responder um estudo importado dispara a correção", st == 303 and es.obter(nova["id"])["estado"] == "corrigido" and "Parcial" in es.obter(nova["id"])["correcao"], es.obter(nova["id"]))

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
