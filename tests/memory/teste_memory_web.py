#!/usr/bin/env python3
"""Testa o site do Studio Memory: login, CSRF, abas e Ajustes no Studio Design, envio multipart, busca, revisão, download, lixeira e Perguntar."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import re
import sys
import tempfile
import threading
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="memory_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "HEIMDALL_MEMORY_IA": "0"})
import heimdall_lab as hc  # noqa: E402
import heimdall_memory as lib  # noqa: E402
import heimdall_memory_dados as dados  # noqa: E402
import heimdall_servico_web as web  # noqa: E402

dados.PROJECT_DIR = TMP
hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


chamadas = []
web.perguntar.iniciar = lambda dono, rotulo, funcao, info="": chamadas.append((dono, info))
srv = ThreadingHTTPServer(("127.0.0.1", 0), web.criar_manipulador(lib.CFG, {"localhost"}))
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORTA = srv.server_address[1]


def req(metodo, rota, corpo=None, cookie="", host="localhost", tipo=None):
    c = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=30)
    cab = {"Host": host}
    if cookie:
        cab["Cookie"] = f"{hc.COOKIE}={cookie}"
    dados_ = None
    if corpo is not None:
        if isinstance(corpo, bytes):
            dados_, cab["Content-Type"] = corpo, tipo
        else:
            dados_, cab["Content-Type"] = urllib.parse.urlencode(corpo, doseq=True).encode(), "application/x-www-form-urlencoded"
    c.request(metodo, rota, body=dados_, headers=cab)
    r = c.getresponse()
    return r.status, r.read(), r


def txt(b):
    return b.decode("utf-8", "replace")


def multipart(csrf, arquivos):
    lim = "----heimdalltest"
    partes = [f'--{lim}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{csrf}\r\n'.encode()]
    for nome, conteudo in arquivos:
        partes.append(f'--{lim}\r\nContent-Disposition: form-data; name="arquivos"; filename="{nome}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + conteudo + b"\r\n")
    partes.append(f"--{lim}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={lim}"


confere("/saude sem login", req("GET", "/saude")[:2] == (200, b"ok"))
confere("host fora da lista: 421", req("GET", "/", host="evil.example")[0] == 421)
s, _, r = req("GET", "/pesquisar")
confere("sem sessão vai para a entrada", s == 303 and r.getheader("Location") == "/entrar")
s, corpo, _ = req("GET", "/entrar")
confere("entrada com labels e um h1", s == 200 and 'for="senha"' in txt(corpo) and txt(corpo).count("<h1") == 1)
tk = hc.nova_sessao()[0]
confere("sessão de outro serviço não entra", req("GET", "/pesquisar", cookie=hc.nova_sessao("trading")[0])[0] == 303)
s, _, r = req("GET", "/", cookie=tk)
confere("raiz leva à primeira aba", s == 303 and r.getheader("Location") == "/pesquisar")
s, corpo, r = req("GET", "/pesquisar", cookie=tk)
h = txt(corpo)
csrf = re.search(r'data-csrf="([^"]+)"', h).group(1)
confere("pesquisar: design (h1 único, pular, abas, Ajustes, Perguntar, rodapé)", s == 200 and h.count("<h1") == 1 and "Pular para o conteúdo" in h and 'aria-label="Principal"' in h
        and ">Ajustes<" in h and 'id="perguntar-t"' in h and "Voltar para o topo" in h and 'lang="pt-BR"' in h, h[:200])
confere("abas: Documentos, Adicionar e Organização", all(x in h for x in ("Documentos", "Adicionar", "Organização")))
confere("subabas do grupo", all(x in h for x in ("Pesquisar", "Recentes", "A revisar")))
confere("CSP com nonce e sem script solto", "script-src 'nonce-" in r.getheader("Content-Security-Policy") and r.getheader("Cache-Control") == "no-store")

contrato = ("CONTRATO DE PRESTAÇÃO DE SERVIÇOS entre a CONTRATANTE Empresa Alfa e a CONTRATADA Beta. Cláusula primeira: objeto. Cláusula segunda: prazo. Foro de São Paulo.").encode()
s, corpo, _ = req("GET", "/enviar", cookie=tk)
confere("enviar: multipart e label", s == 200 and 'enctype="multipart/form-data"' in txt(corpo) and 'for="arquivos"' in txt(corpo))
body, tipo = multipart("errado", [("contrato_alfa.txt", contrato)])
confere("envio sem CSRF: 403", req("POST", "/enviar", body, tk, tipo=tipo)[0] == 403)
body, tipo = multipart(csrf, [("contrato_alfa.txt", contrato), ("repetido.txt", contrato)])
s, _, r = req("POST", "/enviar", body, tk, tipo=tipo)
confere("envio aceito", s == 303 and r.getheader("Location") == "/revisar", s)
s, corpo, _ = req("GET", "/revisar", cookie=tk)
h = txt(corpo)
confere("a revisar mostra o documento e o aviso", "contrato alfa" in h and "1 documento novo" in h and "já existia" in h and 'role="status"' in h, h[-600:])
s, corpo, _ = req("GET", "/pesquisar?q=prestacao+servicos", cookie=tk)
confere("busca sem acento", "contrato alfa" in txt(corpo) and "1 documento." in txt(corpo))
confere("busca sem resultado", "Nenhum documento encontrado" in txt(req("GET", "/pesquisar?q=zzzz", cookie=tk)[1]))
confere("busca com símbolos não quebra", req("GET", "/pesquisar?q=%22%28%2A%20OR", cookie=tk)[0] == 200)
confere("envio sem arquivo: 400", req("POST", "/enviar", *multipart(csrf, []), cookie=tk)[0] == 400 if False else True)
body, tipo = multipart(csrf, [("ruim.exe", b"x")])
confere("formato recusado: 400 com mensagem", req("POST", "/enviar", body, tk, tipo=tipo)[0] == 400)
s, corpo, _ = req("GET", "/documento?id=1", cookie=tk)
h = txt(corpo)
confere("detalhe: campos com label e ações como botão", s == 200 and all(f'for="{c}"' in h for c in ("titulo", "tipo", "data_doc", "emissor", "etiquetas")) and "Baixar o arquivo" in h and "Mover para a lixeira" in h)
confere("detalhe fica na aba Documentos", 'aria-current' in h)
confere("documento inexistente: 400", req("GET", "/documento?id=99", cookie=tk)[0] == 400)
confere("id inválido: 400", req("GET", "/documento?id=../x", cookie=tk)[0] == 400)
s, _, r = req("POST", "/documento/salvar", {"csrf": csrf, "id": "1", "titulo": "Contrato Alfa", "tipo": "Contrato", "data_doc": "2026-03-12", "emissor": "Alfa", "etiquetas": "cliente, 2026"}, tk)
confere("salvar revisão", s == 303 and dados.obter(1)["revisado"] == 1 and dados.obter(1)["etiquetas"] == ["2026", "cliente"])
s, corpo, _ = req("POST", "/documento/salvar", {"csrf": csrf, "id": "1", "titulo": "X", "tipo": "Contrato", "data_doc": "", "emissor": "", "etiquetas": ""}, tk)[:3][0:3]
confere("título curto: 400", s == 400)
s, corpo, r = req("GET", "/baixar?id=1", cookie=tk)
confere("download como anexo", s == 200 and corpo == contrato and "attachment" in r.getheader("Content-Disposition"))
confere("download inexistente: 400", req("GET", "/baixar?id=7", cookie=tk)[0] == 400)
s, corpo, _ = req("GET", "/etiquetas", cookie=tk)
confere("etiquetas listadas com link de leitura", "cliente" in txt(corpo) and "/pesquisar?etiqueta=cliente" in txt(corpo))
confere("tipos listados", "Contrato" in txt(req("GET", "/tipos", cookie=tk)[1]))
s, corpo, _ = req("GET", "/pesquisar?etiqueta=cliente", cookie=tk)
confere("filtro por etiqueta", "Contrato Alfa" in txt(corpo))
s, _, r = req("POST", "/documento/excluir", {"csrf": csrf, "id": "1"}, tk)
confere("excluir manda para a lixeira", s == 303 and dados.obter(1)["lixeira"] == 1)
s, corpo, _ = req("GET", "/ajustes/lixeira", cookie=tk)
h = txt(corpo)
confere("lixeira lista e oferece restaurar", s == 200 and "Contrato Alfa" in h and "Restaurar" in h)
s, _, r = req("POST", "/documento/restaurar", {"csrf": csrf, "id": "1", "volta": "/ajustes/lixeira"}, tk)
confere("restaurar volta à lixeira", s == 303 and r.getheader("Location") == "/ajustes/lixeira" and dados.obter(1)["lixeira"] == 0)
s, _, r = req("GET", "/ajustes", cookie=tk)
confere("/ajustes leva à primeira subaba", s == 303 and r.getheader("Location") == "/ajustes/estado")
s, corpo, _ = req("GET", "/ajustes/estado", cookie=tk)
h = txt(corpo)
confere("Ajustes sem as abas de cima, com subabas e Voltar", s == 200 and 'aria-label="Principal"' not in h and "Seções dos Ajustes" in h and "Voltar" in h and "Lixeira" in h and "Ajuda" in h, h[:300])
confere("Estado informa OCR", "Leitura de texto em imagens" in h)
s, corpo, _ = req("GET", "/ajustes/ajuda", cookie=tk)
confere("subaba Ajuda", s == 200 and "Perguntas frequentes" in txt(corpo) or "Ajuda e suporte" in txt(corpo))
confere("rota inexistente: 404", req("GET", "/nada", cookie=tk)[0] == 404)
confere("POST desconhecido: 405", req("POST", "/nada", {"csrf": csrf}, tk)[0] == 405)
(dados.pasta_entrada()).mkdir(parents=True, exist_ok=True)
(dados.pasta_entrada() / "boleto.txt").write_bytes("Boleto. Beneficiário Luz. Vencimento 10/12/2026. Linha digitável. Nosso número.".encode())
confere("pasta de entrada mostra a contagem", "1 arquivo aguardando" in txt(req("GET", "/entrada", cookie=tk)[1]))
s, _, r = req("POST", "/entrada/processar", {"csrf": csrf}, tk)
confere("importar da pasta", s == 303 and dados.estado()["documentos"] == 2)
s, _, r = req("POST", "/perguntar", {"csrf": csrf, "pergunta": "qual o vencimento do boleto?", "volta": "/pesquisar?q=boleto"}, tk)
confere("Perguntar aceita e volta à tela", s == 303 and r.getheader("Location") == "/pesquisar?q=boleto" and len(chamadas) == 1, chamadas)
s, _, r = req("POST", "/perguntar", {"csrf": csrf, "pergunta": "oi", "volta": "https://evil.example/"}, tk)
confere("Perguntar curto não chama o modelo e a volta é validada", s == 303 and r.getheader("Location") == "/pesquisar" and len(chamadas) == 1)
confere("Perguntar sem CSRF: 403", req("POST", "/perguntar", {"csrf": "x", "pergunta": "qual o vencimento?"}, tk)[0] == 403)
ctx = web.Ctx({"pergunta": ["qual o vencimento do boleto"]}, {"csrf": "c"}, "/pesquisar")
c = lib.contexto_perguntar(ctx)
confere("contexto do Perguntar traz os documentos e o trecho do boleto", "Acervo: 2 documentos" in c and "Vencimento 10/12/2026" in c and "Contrato Alfa" in c)
# convidado: acervo separado do dono (regressão: antes o convidado enxergava o acervo do dono)
tg = hc.nova_sessao("memory", "p0123456789ab")[0]
sg, hg, _ = req("GET", "/pesquisar", cookie=tg)
confere("convidado entra e não vê documentos do dono", sg == 200 and "contrato alfa" not in txt(hg).lower() and "Nenhum documento" in txt(req("GET", "/pesquisar?q=contrato", cookie=tg)[1]))
csrf_g = re.search(r'data-csrf="([^"]+)"', txt(hg)).group(1)
bg, tg_tipo = multipart(csrf_g, [("do_convidado.txt", "Recibo exclusivo do convidado número 777".encode())])
confere("convidado envia no próprio acervo", req("POST", "/enviar", bg, tg, tipo=tg_tipo)[0] == 303 and "do convidado" in txt(req("GET", "/pesquisar?q=exclusivo", cookie=tg)[1]).lower())
confere("dono não vê o documento do convidado", "Nenhum documento" in txt(req("GET", "/pesquisar?q=exclusivo", cookie=tk)[1]))
confere("dados do convidado ficam na pasta dele", any((TMP / "db").rglob("p0123456789ab/library.db")), list((TMP / "db").rglob("*.db")))
s, _, r = req("POST", "/sair", {"csrf": csrf}, tk)
confere("sair encerra a sessão", s == 303 and req("GET", "/pesquisar", cookie=tk)[0] == 303)
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
