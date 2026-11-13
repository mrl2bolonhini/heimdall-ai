#!/usr/bin/env python3
"""Teste do Heimdall Notas (heimdall_notas.py) com um cofre de mentira, sem rede e sem boto3.

    python3 teste_notas.py

Confere: Digest fora e o restante do cofre dentro, títulos com "Leia mais sobre", login (senha e código de 6 dígitos, sem reaproveitar o código), pastas privadas fora do ar, fuga de pasta,
leitura das notas (HTML escapado, tabela, lista, link perigoso), leitor de áudio, Range 206 (exigido pelo iPhone),
documentos, busca sem acento e saída com token CSRF.
"""
import http.client
import os
import re
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

RAIZ = Path(tempfile.mkdtemp(prefix="bib_teste_"))
COFRE, CONHEC = RAIZ / "cerebro", RAIZ / "knowledge"
SEGREDO = "JBSWY3DPEHPK3PXP"
SENHA = "senha-de-teste-123"


def escrever(caminho: Path, conteudo) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8"))


AUDIO = bytes(range(256)) * 4  # 1024 bytes
NOTA = """---
tags: [python, séries]
conceitos: ["laço for", "lista"]
---
# Aula 1: Introdução
Texto com **negrito**, *itálico* e `codigo`. <script>alert(1)</script>

## Itens
- primeiro
- segundo
1. um
2. dois

| Nome | Valor |
|------|-------|
| Ana  | 10    |

[bom](https://exemplo.com/a?x=1&y=2) e [ruim](javascript:alert(1)) e [[Outra nota]].
"""
escrever(CONHEC / "python" / "guia.pdf", b"%PDF-1.4 teste")
escrever(CONHEC / "python" / "resumo.md", "# Resumo rápido\nConteúdo do resumo sobre séries temporais.\n")
escrever(CONHEC / "python" / "sub" / "extra.txt", "texto simples <b>x</b>")
escrever(CONHEC / "python" / "perigo.html", "<script>alert(1)</script>")
escrever(COFRE / "python" / "aula-1.md", NOTA)
escrever(COFRE / "python" / "aula-2.md", "# Aula 2\nSegunda aula.\n")
escrever(COFRE / "python" / "audio" / "aula-1.m4a", AUDIO)
escrever(COFRE / "heimdall-digest" / "dia.md", "# Digest do dia\nResumo.\n")
escrever(COFRE / "heimdall-privacidade" / "segredo.md", "# Segredo\nsenha do banco\n")
escrever(COFRE / "saude" / "exame.md", "# Exame\nsegredo medico\n")
escrever(COFRE / "heimdall-cerebro" / "ideia.md", "# Ideia\nNota do Second Brain.\n")
escrever(COFRE / "python" / "titulo-longo.md", "# Um título bem comprido que não cabe inteiro na lista de notas\nTexto.\n")
escrever(COFRE / "python" / "estudo.md", "# Estudo 2026-11-12 20h: Média móvel simples\n\nTema: python. Livro: x.\n\n## Pergunta\n\nO que é?\n")
escrever(COFRE / "heimdall-cerebro" / "sb.md", "# Second Brain: Minha ideia\nTexto da ideia.\n")
escrever(COFRE / "heimdall-privacidade" / "monitor.md", "# Monitor de privacidade 2026-11-12\n\n**Nível de atenção: alto.** 2 achado(s) novo(s): 1 confirmado(s) e 1 provável(is).\n")
escrever(COFRE / "heimdall-privacidade" / "diarios.md", "# Diários oficiais - 2026-11-12\n\nTexto longo sobre menções.\n\n## DOU\n\n1. Publicação A\n2. Publicação B\n")
escrever(COFRE / "saude" / "dia.md", "# Saúde 2026-11-12\n\nSeu sono ficou abaixo da média dos últimos 30 dias, com menos sono profundo.\n")
escrever(COFRE / "python" / "resumo-aula.md", "# Resumo\n\nEsta aula apresenta os conceitos básicos de listas e laços em Python.\n")
os.utime(COFRE / "python" / "aula-1.md", (time.time() - 100, time.time() - 100))
escrever(RAIZ / "fora.md", "# Fora do cofre\n")

os.environ.update({"HEIMDALL_VAULT_DIR": str(COFRE), "HEIMDALL_KNOWLEDGE_DIR": str(CONHEC), "HEIMDALL_CLOUD_TOTP_SEGREDO": SEGREDO})
sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_cloud as hc  # noqa: E402

os.environ["HEIMDALL_CLOUD_SENHA_HASH"] = hc.hash_senha(SENHA, iteracoes=100_000)
hc.SENHA_HASH = os.environ["HEIMDALL_CLOUD_SENHA_HASH"]
hc.TOTP_SEGREDO = SEGREDO
import heimdall_notas as hb  # noqa: E402

srv = ThreadingHTTPServer(("127.0.0.1", 0), hb.Notas)
srv.daemon_threads = True
porta = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

ok_n, falhas = 0, []


def confere(nome: str, cond: bool, detalhe: str = "") -> None:
    global ok_n
    if cond:
        ok_n += 1
    else:
        falhas.append(f"{nome} {detalhe}")
        print("FALHOU:", nome, detalhe)


def req(metodo, caminho, corpo=None, cookie="", host="localhost", extra=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    cab = {"Host": host}
    if cookie:
        cab["Cookie"] = cookie
    if corpo is not None:
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    cab.update(extra or {})
    c.request(metodo, caminho, body=corpo, headers=cab)
    r = c.getresponse()
    dados = r.read()
    heads = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, heads, dados


def texto(b: bytes) -> str:
    return b.decode("utf-8", "replace")


def codigo(passo: int) -> str:
    return hc._hotp(hc._chave_totp(SEGREDO), passo)


agora = int(time.time() // 30)

# --- acesso ---
s, h, _ = req("GET", "/")
confere("sem login vai para /entrar", s == 303 and h["location"] == "/entrar")
s, _, _ = req("GET", "/", host="outro.exemplo")
confere("site não permitido: 421", s == 421)
s, _, c = req("GET", "/saude")
confere("saúde", s == 200 and c == b"ok")
s, h, c = req("GET", "/entrar")
confere("página de entrada", s == 200 and b'name="senha"' in c)
s, _, c = req("POST", "/entrar", urlencode({"senha": "errada", "codigo": codigo(agora)}))
confere("senha errada recusada", s == 401)
s, _, c = req("POST", "/entrar", urlencode({"senha": SENHA, "codigo": "000000"}))
confere("código errado recusado", s == 401)
s, h, c = req("POST", "/entrar", urlencode({"senha": SENHA, "codigo": codigo(agora)}))
confere("login correto", s == 303 and "hbib=" in h.get("set-cookie", "") and "HttpOnly" in h["set-cookie"] and "SameSite=Strict" in h["set-cookie"])
ck = h["set-cookie"].split(";")[0]
s, _, c = req("POST", "/entrar", urlencode({"senha": SENHA, "codigo": codigo(agora)}))
confere("código não pode ser reaproveitado", s == 401)
s, h, _ = req("POST", "/entrar", urlencode({"senha": SENHA, "codigo": codigo(agora + 1)}), host="localhost")
confere("segundo login com outro código", s == 303)

# --- início e privacidade ---
s, h, c = req("GET", "/", cookie=ck)
t = texto(c)
confere("início abre", s == 200 and "Últimas notas" in t and "Aula 1: Introdução" in t)
confere("tema python aparece", "Python" in t)
confere("Digest fica de fora", "Digest" not in t and "Resumo." not in t)
confere("privacidade, Second Brain e saúde aparecem", "Monitor de Privacidade" in t and "Second Brain" in t and "Saúde" in t and "Segredo" in t and "Exame" in t and "Ideia" in t)
confere("título é cabeçalho e vem seguido do Leia mais", '<h3>Aula 1: Introdução</h3><a href="/nota?p=python&amp;n=aula-1.md">Leia mais sobre Aula 1: Introdução</a>' in t)
confere("título de tamanho normal aparece inteiro no link, sem reticências", "Leia mais sobre Um título bem comprido que não cabe inteiro na lista de notas</a>" in t and "<h3>Um título bem comprido que não cabe inteiro na lista de notas</h3>" in t, t[t.find("Leia mais sobre Um"):][:120])
_longo = "Arquitetura de data lakes na AWS com Glue, Athena e Lake Formation: particionamento, formatos colunares, custo de consulta e governança de acesso por tabela"
_cor = hb.inicio_do_titulo(_longo)
confere("título muito longo só é cortado num espaço e com reticências", _cor.endswith("…") and len(_cor) <= 111 and _longo.startswith(_cor[:-1]) and _longo[len(_cor) - 1] in " ,;:", _cor)
confere("primeira frase de 120 caracteres não é cortada", not hb.primeira_frase("x " * 3 + "Esta é uma frase com palavras suficientes para passar de noventa caracteres e ainda assim caber folgadamente no limite novo.").endswith("…"), "")
confere("estudo: sem prefixo repetido", "<h3>Média móvel simples</h3>" in t and "Estudo 2026" not in t and "Leia mais sobre Média móvel simples</a>" in t)
confere("Second Brain: sem prefixo", "<h3>Minha ideia</h3>" in t and "Second Brain: Minha" not in t)
confere("monitor ganha sentido", "<h3>Monitor de privacidade de 12/11/2026: 2 achados, atenção alto</h3>" in t, t[t.find("Monitor de privacidade de"):][:100])
confere("diários ganham sentido", "<h3>Diários oficiais de 12/11/2026: 2 menções (DOU)</h3>" in t)
confere("saúde ganha sentido", "<h3>Saúde de 12/11/2026: Seu sono ficou abaixo da média dos últimos 30 dias, com menos sono profundo</h3>" in t)
confere("título vago 'Resumo' ganha sentido", "<h3>Resumo: Esta aula apresenta os conceitos básicos de listas e laços em Python</h3>" in t)
s2, _, c2 = req("GET", "/nota?p=python&n=estudo.md", cookie=ck)
t2 = texto(c2)
confere("página do estudo: título limpo e sem repetir no corpo", "<h1>Média móvel simples</h1>" in t2 and "Estudo 2026-11-12" not in t2)
confere("áudio indicado na lista", "com áudio" in t)
confere("cabeçalhos de segurança", "nosniff" in h["x-content-type-options"] and "frame-ancestors 'none'" in h["content-security-policy"])
confere("landmarks e pular", 'href="#principal"' in t and "<main" in t and 'aria-label="Principal"' in t and 'lang="pt-BR"' in t)
s, _, c = req("GET", "/nota?p=heimdall-privacidade&n=segredo.md", cookie=ck)
confere("nota de privacidade abre", s == 200 and b"senha do banco" in c)
s, _, c = req("GET", "/nota?p=saude&n=exame.md", cookie=ck)
confere("nota de saúde abre", s == 200)
s, _, c = req("GET", "/nota?p=heimdall-digest&n=dia.md", cookie=ck)
confere("Digest bloqueado", s == 404 and b"Digest do dia" not in c)
s, _, c = req("GET", "/busca?q=segredo", cookie=ck)
confere("busca acha privacidade e saúde, não o Digest", b"senha do banco" in c or b"Segredo" in c)
s, _, c = req("GET", "/busca?q=resumo.", cookie=ck)
confere("busca não acha o Digest", b"Digest do dia" not in c)
os.environ["HEIMDALL_NOTAS_EXCLUIR"] = "heimdall-digest,saude"
s, _, c = req("GET", "/nota?p=saude&n=exame.md", cookie=ck)
confere("EXCLUIR tira outras pastas", s == 404)
del os.environ["HEIMDALL_NOTAS_EXCLUIR"]
os.environ["HEIMDALL_NOTAS_PASTAS"] = "heimdall-cerebro"
s, _, c = req("GET", "/nota?p=saude&n=exame.md", cookie=ck)
confere("PASTAS com lista mostra só as listadas e os temas", s == 404 and req("GET", "/nota?p=heimdall-cerebro&n=ideia.md", cookie=ck)[0] == 200 and req("GET", "/nota?p=python&n=aula-1.md", cookie=ck)[0] == 200)
del os.environ["HEIMDALL_NOTAS_PASTAS"]

# --- notas ---
s, h, c = req("GET", "/nota?p=python&n=aula-1.md", cookie=ck)
t = texto(c)
confere("nota abre", s == 200 and "<title>Aula 1: Introdução - Heimdall Notas</title>" in t and "<h1>Aula 1: Introdução</h1>" in t)
confere("título não repete no corpo", t.count("Aula 1: Introdução") == 2)
confere("frontmatter vira linhas", "Tags:" in t and "séries" in t and "Conceitos:" in t and "name: " not in t)
confere("negrito, itálico, código", "<strong>negrito</strong>" in t and "<em>itálico</em>" in t and "<code>codigo</code>" in t)
confere("html escapado", "<script>alert(1)</script>" not in t.split("<article")[1] and "&lt;script&gt;" in t)
confere("lista e tabela", "<ul><li>primeiro</li><li>segundo</li></ul>" in t and "<ol><li>um</li>" in t and '<th scope="col">Nome</th>' in t and "<td>Ana</td>" in t)
confere("link https mantido", 'href="https://exemplo.com/a?x=1&amp;y=2"' in t)
confere("link perigoso sem href", "javascript:" in t and 'href="javascript' not in t)
confere("wikilink vira texto", "Outra nota" in t and "[[" not in t)
confere("leitor de áudio", '<audio id="leitor" controls' in t and "/audio?p=python&amp;n=aula-1.m4a" in t and "Voltar 15 segundos" in t and 'data-vel="1.5"' in t)
m = re.search(r"<script nonce=\"([^\"]+)\">", t)
confere("script com nonce combinando com a CSP", bool(m) and f"'nonce-{m.group(1)}'" in h["content-security-policy"])
confere("próxima/anterior nota", "Nota anterior" in t or "Próxima nota" in t)
s, h, c = req("GET", "/nota?p=python&n=aula-2.md", cookie=ck)
confere("nota sem áudio sem leitor nem script", s == 200 and b"<audio" not in c and b"<script" not in c and "script-src" not in h["content-security-policy"])
for ruim in ("../fora.md", "..%2Ffora.md", "/etc/passwd", "aula-1.md%00.png", ".hidden.md", "aula-1.pdf"):
    s, _, c = req("GET", f"/nota?p=python&n={ruim}", cookie=ck)
    confere(f"fuga de pasta bloqueada: {ruim}", s == 404)
s, _, _ = req("GET", "/nota?p=..&n=fora.md", cookie=ck)
confere("pasta inválida bloqueada", s == 404)

# --- áudio com Range ---
s, h, c = req("GET", "/audio?p=python&n=aula-1.m4a", cookie=ck)
confere("áudio inteiro", s == 200 and c == AUDIO and h["content-type"] == "audio/mp4" and h["accept-ranges"] == "bytes")
s, h, c = req("GET", "/audio?p=python&n=aula-1.m4a", cookie=ck, extra={"Range": "bytes=0-9"})
confere("Range 0-9 vira 206", s == 206 and c == AUDIO[:10] and h["content-range"] == "bytes 0-9/1024" and h["content-length"] == "10")
s, h, c = req("GET", "/audio?p=python&n=aula-1.m4a", cookie=ck, extra={"Range": "bytes=1000-"})
confere("Range aberto", s == 206 and c == AUDIO[1000:] and h["content-range"] == "bytes 1000-1023/1024")
s, h, c = req("GET", "/audio?p=python&n=aula-1.m4a", cookie=ck, extra={"Range": "bytes=-5"})
confere("Range de sufixo", s == 206 and c == AUDIO[-5:])
s, h, c = req("GET", "/audio?p=python&n=aula-1.m4a", cookie=ck, extra={"Range": "bytes=5000-6000"})
confere("Range fora do arquivo: 416", s == 416)
s, h, c = req("GET", "/audio?p=python&n=aula-1.m4a", extra={"Range": "bytes=0-9"})
confere("áudio exige login", s == 303)
s, h, c = req("HEAD", "/audio?p=python&n=aula-1.m4a", cookie=ck)
confere("HEAD sem corpo", s == 200 and c == b"" and h["content-length"] == "1024")
s, _, _ = req("GET", "/audio?p=python&n=../aula-1.md", cookie=ck)
confere("áudio só da pasta audio", s == 404)

# --- documentos ---
s, h, c = req("GET", "/tema?t=python", cookie=ck)
t = texto(c)
confere("tema lista notas e documentos", s == 200 and "Aula 2" in t and "guia.pdf" in t and "resumo.md" in t and "sub/extra.txt" in t and "perigo.html" not in t)
s, h, c = req("GET", "/doc?t=python&c=guia.pdf", cookie=ck)
confere("PDF vai para /arquivo", s == 303 and h["location"].startswith("/arquivo?"))
s, h, c = req("GET", "/arquivo?t=python&c=guia.pdf", cookie=ck)
confere("PDF abre na página", s == 200 and h["content-type"] == "application/pdf" and h["content-disposition"].startswith("inline"))
s, h, c = req("GET", "/arquivo?t=python&c=guia.pdf&baixar=1", cookie=ck)
confere("PDF baixa quando pedido", h["content-disposition"].startswith("attachment") and "sandbox" in h["content-security-policy"])
s, h, c = req("GET", "/doc?t=python&c=resumo.md", cookie=ck)
confere("documento Markdown renderizado", s == 200 and "Conteúdo do resumo" in texto(c))
s, h, c = req("GET", "/doc?t=python&c=sub/extra.txt", cookie=ck)
confere("texto simples escapado", s == 200 and "&lt;b&gt;x&lt;/b&gt;" in texto(c))
s, _, _ = req("GET", "/arquivo?t=python&c=perigo.html", cookie=ck)
confere("html de documento não é servido", s == 404)
for ruim in ("../../cerebro/saude/exame.md", "..%2Fguia.pdf", "sub/../guia.pdf", "/etc/passwd"):
    s, _, _ = req("GET", f"/arquivo?t=python&c={ruim}", cookie=ck)
    confere(f"fuga em documentos bloqueada: {ruim}", s == 404)

# --- busca ---
s, _, c = req("GET", "/busca?q=series", cookie=ck)
confere("busca sem acento acha 'séries'", "Resumo rápido" in texto(c) or "Aula 1" in texto(c))
s, _, c = req("GET", "/busca?q=SEGUNDA", cookie=ck)
confere("busca sem maiúsculas", "Aula 2" in texto(c))
s, _, c = req("GET", "/busca?q=%3Cscript%3E", cookie=ck)
confere("busca escapa a consulta", b"<script>" not in c)
s, _, c = req("GET", "/busca?q=a", cookie=ck)
confere("busca curta pede mais letras", "pelo menos duas letras" in texto(c))

# --- somente leitura e saída ---
s, _, c = req("POST", "/nota?p=python&n=aula-1.md", "x=1", cookie=ck)
confere("POST em página recusado", s == 405)
s, _, c = req("POST", "/sair", "csrf=errado", cookie=ck)
confere("sair sem CSRF recusado", s == 403)
csrf = re.search(r'name="csrf" value="([^"]+)"', texto(req("GET", "/", cookie=ck)[2])).group(1)
s, h, c = req("POST", "/sair", urlencode({"csrf": csrf}), cookie=ck)
confere("sair com CSRF", s == 303 and "Max-Age=0" in h["set-cookie"])
s, h, _ = req("GET", "/", cookie=ck)
confere("sessão encerrada", s == 303 and h["location"] == "/entrar")

# --- tentativas ---
for _ in range(hc.MAX_POR_IP):
    req("POST", "/entrar", urlencode({"senha": "x", "codigo": "123456"}))
s, h, _ = req("POST", "/entrar", urlencode({"senha": SENHA, "codigo": codigo(agora - 1)}))
confere("bloqueio depois de muitas falhas", s == 429 and h.get("retry-after") == "900")

srv.shutdown()
print(f"\n{ok_n} verificações passaram, {len(falhas)} falharam.")
sys.exit(1 if falhas else 0)
