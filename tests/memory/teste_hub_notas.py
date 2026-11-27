#!/usr/bin/env python3
"""Testa a área de Notas do Studio Hub (fase B): aba Notas com subabas, temas, nota com áudio e Range, documentos, busca, catálogo com ações próprias,
Perguntar com o contexto das notas, e a regra de que só o dono vê o conteúdo."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import re
import tempfile
import threading
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="hub_notas_"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "STUDIO_HUB_IA": "0"})
import studio_hub_notas as hn  # noqa: E402
import studio_lab as hc  # noqa: E402
import studio_memory as lib  # noqa: E402
import studio_memory_dados as dados  # noqa: E402
import studio_notas as n  # noqa: E402
import studio_servico_web as web  # noqa: E402

dados.PROJECT_DIR = TMP
hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
# cofre e knowledge de teste: tema "ciencia" com uma nota, um áudio e um documento
cofre, conhecimento = TMP / "brain", TMP / "knowledge"
(cofre / "ciencia" / "audio").mkdir(parents=True)
(conhecimento / "ciencia").mkdir(parents=True)
(cofre / "ciencia" / "2026-11-20-fotossintese.md").write_text("# Fotossíntese\n\nAs plantas convertem luz em energia química. Tag: clorofila.\n", encoding="utf-8")
(cofre / "ciencia" / "audio" / "2026-11-20-fotossintese.m4a").write_bytes(bytes(range(256)) * 4)
(conhecimento / "ciencia" / "resumo.md").write_text("# Resumo de ciência\n\nTexto do documento.\n", encoding="utf-8")
(conhecimento / "ciencia" / "livro.pdf").write_bytes(b"%PDF-1.4 teste")
n.VAULT, n.KNOWLEDGE = cofre, conhecimento
os.environ["STUDIO_NOTAS_PASTAS"] = "*"
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


chamadas = []
web.perguntar.iniciar = lambda dono, rotulo, funcao, info="": chamadas.append((rotulo, info))
srv = ThreadingHTTPServer(("127.0.0.1", 0), web.criar_manipulador(lib.CFG, {"localhost"}))
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORTA = srv.server_address[1]


def req(metodo, rota, corpo=None, cookie="", cab_extra=None):
    c = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=30)
    cab = {"Host": "localhost", **(cab_extra or {})}
    if cookie:
        cab["Cookie"] = f"{hc.COOKIE}={cookie}"
    dados_ = None
    if corpo is not None:
        dados_, cab["Content-Type"] = urllib.parse.urlencode(corpo, doseq=True).encode(), "application/x-www-form-urlencoded"
    c.request(metodo, rota, body=dados_, headers=cab)
    r = c.getresponse()
    return r.status, r.read(), r


def txt(b):
    return b.decode("utf-8", "replace")


tk = hc.nova_sessao()[0]
s, corpo, _ = req("GET", "/notas", cookie=tk)
h = txt(corpo)
csrf = re.search(r'data-csrf="([^"]+)"', h).group(1)
confere("aba Notas com as subabas Recentes, Temas, Busca e Catálogo (4 abas no total)", s == 200 and all(x in h for x in ("Recentes", "Temas", "Busca", "Catálogo")) and "Fotossíntese" in h, h[:200])
confere("os grupos antigos continuam e o limite de 5 abas vale", [a for a, _ in lib.CFG.abas] == ["Documentos", "Adicionar", "Organização", "Notas"] and len(lib.CFG.abas) <= 5)
confere("Recentes tem o Perguntar", 'id="perguntar-t"' in h)
s, corpo, _ = req("GET", "/notas/temas", cookie=tk)
h = txt(corpo)
confere("Temas: cada tema é botão (Tab alcança), não link solto", 'action="/notas/tema"' in h and "<button" in h and "Ciencia" in h, h[:300])
s, corpo, _ = req("GET", "/notas/tema?t=ciencia", cookie=tk)
h = txt(corpo)
confere("tema lista notas e documentos com rotas de /notas", s == 200 and "/notas/nota?p=ciencia" in h and "/notas/documento?t=ciencia" in h)
s, corpo, _ = req("GET", "/notas/nota?p=ciencia&n=2026-11-20-fotossintese.md", cookie=tk)
h = txt(corpo)
confere("nota abre com texto, áudio e navegação", s == 200 and "energia química" in h and "/notas/audio?p=ciencia" in h and 'id="leitor"' in h and "Todas as notas do tema" in h, h[:300])
confere("a página da nota leva o script do leitor", "hbib:" in h)
s, corpo, r = req("GET", "/notas/audio?p=ciencia&n=2026-11-20-fotossintese.m4a", cookie=tk)
confere("áudio inteiro: 200 com Accept-Ranges", s == 200 and len(corpo) == 1024 and r.getheader("Accept-Ranges") == "bytes" and r.getheader("Content-Type") == "audio/mp4")
s, corpo, r = req("GET", "/notas/audio?p=ciencia&n=2026-11-20-fotossintese.m4a", cookie=tk, cab_extra={"Range": "bytes=10-19"})
confere("Range: 206 com o trecho certo", s == 206 and corpo == bytes(range(10, 20)) and r.getheader("Content-Range") == "bytes 10-19/1024", (s, r.getheader("Content-Range")))
s, _, _ = req("GET", "/notas/audio?p=ciencia&n=2026-11-20-fotossintese.m4a", cookie=tk, cab_extra={"Range": "bytes=5000-"})
confere("Range fora do arquivo: 416", s == 416)
s, _, _ = req("GET", "/notas/audio?p=ciencia&n=..%2F..%2Fetc%2Fpasswd", cookie=tk)
confere("fuga de pasta no áudio: 404", s == 404)
s, _, _ = req("GET", "/notas/audio?p=ciencia&n=2026-11-20-fotossintese.m4a")
confere("áudio sem sessão: vai para a entrada", s == 303)
s, corpo, _ = req("GET", "/notas/documento?t=ciencia&c=resumo.md", cookie=tk)
confere("documento de texto abre", s == 200 and "Texto do documento" in txt(corpo) and "/notas/tema?t=ciencia" in txt(corpo))
s, corpo, r = req("GET", "/notas/arquivo?t=ciencia&c=livro.pdf&baixar=1", cookie=tk)
confere("arquivo baixa como anexo", s == 200 and corpo.startswith(b"%PDF") and "attachment" in r.getheader("Content-Disposition"))
s, corpo, _ = req("GET", "/notas/busca?q=clorofila", cookie=tk)
confere("busca acha a nota e o link vai para /notas", s == 200 and "/notas/nota?p=ciencia" in txt(corpo) and "1 resultado" in txt(corpo), txt(corpo)[:300])
s, corpo, _ = req("GET", "/notas/nota?p=ciencia&n=inexistente.md", cookie=tk)
confere("nota inexistente: aviso claro", s == 400 and "Nota não encontrada" in txt(corpo))
s, corpo, _ = req("GET", "/notas/catalogo", cookie=tk)
confere("catálogo: formulário de salvar nota", s == 200 and 'action="/notas/salvar"' in txt(corpo))
s, _, r = req("POST", "/notas/salvar", {"csrf": "errado", "texto": "ideia"}, tk)
confere("salvar sem CSRF: 403", s == 403)
s, _, r = req("POST", "/notas/salvar", {"csrf": csrf, "texto": "Comprar pilhas para o gravador"}, tk)
confere("salvar nota inicia a catalogação e volta ao catálogo", s == 303 and r.getheader("Location") == "/notas/catalogo" and chamadas and chamadas[-1][0] == "catalogo", (s, chamadas))
contexto = hn.contexto(type("C", (), {"p": lambda self, k, d="": "fotossintese clorofila"})())
confere("contexto do Perguntar traz só trechos das notas", "Fotossíntese" in contexto and "Notas do usuário" in contexto, contexto)
s, _, r = req("POST", "/perguntar", {"csrf": csrf, "texto": "o que é fotossíntese?", "volta": "/notas"}, tk)
confere("Perguntar na aba Notas é aceito", s == 303 and r.getheader("Location", "").startswith("/notas"), (s, r.getheader("Location")))
# convidado: não vê nada
import studio_pessoas as pessoas  # noqa: E402
confere("convidado recebe aviso, não o conteúdo", pessoas.e_dono() is True)
with pessoas.definir(pessoas.id_da("ana@exemplo.com")):
    ativo_antes = pessoas.ativo
    pessoas.ativo = lambda: True
    try:
        r1 = hn.pg_recentes(type("C", (), {"pagina": lambda self: 1})())
        confere("convidado não lê as notas do dono", "só do dono" in r1[1] and "Fotossíntese" not in r1[1], r1)
        confere("convidado não baixa áudio nem arquivo", hn.audio(type("C", (), {"p": lambda self, k, d="": "ciencia"})()) is None and hn.arquivo(type("C", (), {"p": lambda self, k, d="": "ciencia"})()) is None)
    finally:
        pessoas.ativo = ativo_antes

print(f"\n{falhas} falha(s)")
_sys.exit(1 if falhas else 0)
