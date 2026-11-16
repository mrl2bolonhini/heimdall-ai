#!/usr/bin/env python3
"""Testa a entrada pelo Cloudflare Access (heimdall_cfaccess.py): assinatura RS256, claims, e-mail, cache e o fluxo HTTP do painel de jogos.
Sem internet: gera um par de chaves RSA só para o teste e responde os certificados no lugar do Cloudflare."""
import base64
import hashlib
import json
import os
import random
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
os.environ.update({"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(AQUI))
import heimdall_cfaccess as cfa  # noqa: E402
import heimdall_cloud as hc  # noqa: E402
import heimdall_jogos as hj  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


# --- RSA de teste (só biblioteca padrão) ---
rnd = random.Random(7)


def primo(bits):
    while True:
        p = rnd.getrandbits(bits) | (1 << (bits - 1)) | 1
        if all(p % q for q in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)) and all(
                _mr(p, rnd.randrange(2, p - 2)) for _ in range(12)):
            return p


def _mr(n, a):
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    x = pow(a, d, n)
    if x in (1, n - 1):
        return True
    for _ in range(r - 1):
        x = pow(x, 2, n)
        if x == n - 1:
            return True
    return False


def par():
    e = 65537
    while True:
        p, q = primo(512), primo(512)
        if p != q and (p - 1) % e and (q - 1) % e:
            n = p * q
            return n, e, pow(e, -1, (p - 1) * (q - 1))


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def assinar(n, d, texto: bytes) -> bytes:
    k = (n.bit_length() + 7) // 8
    t = cfa._PREFIXO_SHA256 + hashlib.sha256(texto).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


N, E, D = par()
N2, E2, D2 = par()  # outro par: assinatura de quem não é o Cloudflare
AGORA = 1_800_000_000.0
EQUIPE, AUD, EMAIL = "minha-equipe", "aud-do-aplicativo-123", "eu@exemplo.test"


def jwt(corpo=None, kid="k1", alg="RS256", chave=(N, D), cab_extra=None):
    cab = {"alg": alg, "kid": kid, "typ": "JWT", **(cab_extra or {})}
    base = {"iss": f"https://{EQUIPE}.cloudflareaccess.com", "aud": [AUD], "email": EMAIL, "exp": AGORA + 600, "nbf": AGORA - 10}
    base.update(corpo or {})
    parte = f"{b64(json.dumps(cab).encode())}.{b64(json.dumps(base).encode())}"
    return f"{parte}.{b64(assinar(chave[0], chave[1], parte.encode()))}"


chamadas = []


def falso_cloudflare(equipe):
    chamadas.append(equipe)
    return {"k1": (N, E)}


cfa._buscar_chaves = falso_cloudflare

# --- desligado ---
for k in ("HEIMDALL_CFACCESS_EQUIPE", "HEIMDALL_CFACCESS_AUD", "HEIMDALL_CFACCESS_EMAILS"):
    os.environ.pop(k, None)
confere("sem configuração fica desligado e recusa tudo", not cfa.ativo() and cfa.verificar_jwt(jwt(), AGORA) is None)
os.environ.update(HEIMDALL_CFACCESS_EQUIPE=EQUIPE + ".cloudflareaccess.com", HEIMDALL_CFACCESS_AUD=AUD)
confere("sem lista de e-mails continua desligado", not cfa.ativo())
os.environ["HEIMDALL_CFACCESS_EMAILS"] = f" {EMAIL.upper()} , outro@exemplo.test "
confere("com os três valores liga (equipe aceita com o sufixo; e-mail sem diferenciar maiúsculas)", cfa.ativo() and cfa.config()["equipe"] == EQUIPE)
os.environ["HEIMDALL_CFACCESS_EQUIPE"] = "evil.com/x"
confere("equipe em formato inválido não liga", not cfa.ativo())
os.environ["HEIMDALL_CFACCESS_EQUIPE"] = EQUIPE

# --- validação do token ---
confere("token válido devolve o e-mail", cfa.verificar_jwt(jwt(), AGORA) == EMAIL)
confere("aud como texto (não lista) também vale", cfa.verificar_jwt(jwt({"aud": AUD}), AGORA) == EMAIL)
confere("aud de outro aplicativo é recusado", cfa.verificar_jwt(jwt({"aud": ["outro"]}), AGORA) is None)
confere("iss de outra equipe é recusado", cfa.verificar_jwt(jwt({"iss": "https://outra.cloudflareaccess.com"}), AGORA) is None)
confere("token expirado é recusado", cfa.verificar_jwt(jwt({"exp": AGORA - 120}), AGORA) is None)
confere("pequena diferença de relógio é tolerada", cfa.verificar_jwt(jwt({"exp": AGORA - 10}), AGORA) == EMAIL)
confere("token que ainda não vale (nbf) é recusado", cfa.verificar_jwt(jwt({"nbf": AGORA + 3600}), AGORA) is None)
confere("e-mail fora da lista é recusado", cfa.verificar_jwt(jwt({"email": "intruso@exemplo.test"}), AGORA) is None)
confere("sem e-mail é recusado", cfa.verificar_jwt(jwt({"email": ""}), AGORA) is None)
confere("sem exp é recusado", cfa.verificar_jwt(jwt({"exp": None}), AGORA) is None)
confere("alg none é recusado", cfa.verificar_jwt(jwt(alg="none"), AGORA) is None)
confere("alg HS256 é recusado", cfa.verificar_jwt(jwt(alg="HS256"), AGORA) is None)
confere("assinado por outro par de chaves é recusado", cfa.verificar_jwt(jwt(chave=(N2, D2)), AGORA) is None)
t = jwt()
a, b, c = t.split(".")
adulterado = f"{a}.{b64(json.dumps({'iss': f'https://{EQUIPE}.cloudflareaccess.com', 'aud': [AUD], 'email': EMAIL, 'exp': AGORA + 99999}).encode())}.{c}"
confere("corpo adulterado com a assinatura antiga é recusado", cfa.verificar_jwt(adulterado, AGORA) is None)
confere("kid desconhecido é recusado", cfa.verificar_jwt(jwt(kid="zzz"), AGORA + 5000) is None)
for lixo in ("", "abc", "a.b", "a.b.c.d", "....", None, "e30.e30.e30"):
    confere(f"token malformado {lixo!r} é recusado sem erro", cfa.verificar_jwt(lixo, AGORA) is None)

# --- cache dos certificados ---
chamadas.clear()
cfa._cache.update(chaves={}, quando=0.0, tentou=0.0, equipe="")
for i in range(5):
    cfa.verificar_jwt(jwt(), AGORA + i)
confere("certificados são buscados uma vez e reaproveitados", len(chamadas) == 1, chamadas)
cfa.verificar_jwt(jwt(kid="novo"), AGORA + 10)
confere("kid novo dentro de 60 s não dispara nova busca (evita abuso)", len(chamadas) == 1, chamadas)
cfa.verificar_jwt(jwt(kid="novo"), AGORA + 100)
confere("kid novo depois de 60 s busca de novo (rotação de chaves)", len(chamadas) == 2, chamadas)

# --- fluxo HTTP no painel de jogos ---
hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
cfa._cache.update(chaves={}, quando=0.0, tentou=0.0, equipe="")
srv = ThreadingHTTPServer(("127.0.0.1", 0), hj.Jogos)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"


class Sem303(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


abre = urllib.request.build_opener(Sem303).open


def pedir(caminho, cab=None):
    req = urllib.request.Request(BASE + caminho, headers=cab or {})
    try:
        with abre(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8", "replace"), dict(ex.headers)


# o relógio real vale aqui: gera token com datas de agora
import time  # noqa: E402

AGORA = time.time()
st, corpo, _ = pedir("/entrar")
confere("sem token do Access, /entrar mostra o formulário de senha e código", st == 200 and 'name="senha"' in corpo, (st, corpo[:200]))
st, corpo, _ = pedir("/entrar", {cfa.CABECALHO: jwt()[:-6] + "AAAAAA"})
confere("token com assinatura ruim cai no formulário", st == 200 and 'name="senha"' in corpo, (st, corpo[:200]))
st, _, cab = pedir("/entrar", {cfa.CABECALHO: jwt()})
cookie = cab.get("Set-Cookie", "")
confere("token válido do Access abre a sessão sem senha nem código", st == 303 and cab.get("Location") == "/" and cookie.startswith(hc.COOKIE + "="), (st, cab))
confere("o cookie é HttpOnly e SameSite=Strict", "HttpOnly" in cookie and "SameSite=Strict" in cookie, cookie)
st, corpo, _ = pedir("/", {"Cookie": cookie.split(";")[0]})
confere("com esse cookie o painel abre", st == 200 and "<h1>Jogos</h1>" in corpo, (st, corpo[:200]))
st, _, cab = pedir("/", {cfa.CABECALHO: jwt()})
confere("o token sozinho, sem passar por /entrar, ainda manda para /entrar (que então abre a sessão)", st == 303 and cab.get("Location") == "/entrar", (st, cab))
st, _, cab = pedir("/entrar", {cfa.CABECALHO: jwt({"email": "intruso@exemplo.test"})})
confere("token de e-mail não permitido não abre sessão", st == 200 and "Set-Cookie" not in cab, (st, cab))
os.environ.pop("HEIMDALL_CFACCESS_AUD")
st, _, cab = pedir("/entrar", {cfa.CABECALHO: jwt()})
confere("desligando a configuração, o token deixa de valer", st == 200 and "Set-Cookie" not in cab, (st, cab))

# --- convidados e escopo por serviço ---
os.environ["HEIMDALL_CFACCESS_AUD"] = AUD + ",aud-do-app-games"
os.environ["HEIMDALL_CFACCESS_CONVIDADOS"] = "ana@exemplo.test=jogos;beto@exemplo.test=jogos+finance;ruim@exemplo.test=Jogos Ruim!;sem-igual"
cfg = cfa.config()
confere("convidados lidos do .env, com vários serviços e lixo ignorado", cfg["convidados"] == {"ana@exemplo.test": {"jogos"}, "beto@exemplo.test": {"jogos", "finance"}}, cfg["convidados"])
confere("duas AUDs separadas por vírgula", cfg["auds"] == {AUD, "aud-do-app-games"})
confere("token de outra AUD da lista também vale", cfa.verificar_jwt(jwt({"aud": ["aud-do-app-games"]}), time.time()) == EMAIL)
ana = jwt({"email": "ana@exemplo.test"})
confere("convidado entra no serviço liberado", cfa.verificar_jwt(ana, servico="jogos") == "ana@exemplo.test")
confere("convidado NÃO entra em outro serviço", cfa.verificar_jwt(ana, servico="cloud") is None and cfa.verificar_jwt(ana, servico="finance") is None and cfa.verificar_jwt(ana) is None)
confere("convidado com dois serviços entra nos dois", cfa.verificar_jwt(jwt({"email": "beto@exemplo.test"}), servico="finance") == "beto@exemplo.test")
confere("dono entra em qualquer serviço", all(cfa.verificar_jwt(jwt(), servico=s) == EMAIL for s in ("cloud", "notas", "news", "saude", "jogos", "finance")))
confere("papéis", cfa.papel(EMAIL, "cloud") == "dono" and cfa.papel("ana@exemplo.test", "jogos") == "convidado" and cfa.papel("ana@exemplo.test", "cloud") is None)

# sessões com escopo
tk_dono, _ = hc.nova_sessao()
tk_ana, s_ana = hc.nova_sessao("jogos")
confere("sessão de dono vale em todo serviço e sem serviço", all(hc.sessao_valida(tk_dono, s) for s in ("cloud", "jogos", "finance", None)))
confere("sessão de convidado vale só no serviço dela", s_ana is not None and hc.sessao_valida(tk_ana, "jogos") and not hc.sessao_valida(tk_ana, "cloud") and not hc.sessao_valida(tk_ana, "finance") and not hc.sessao_valida(tk_ana))
p = tk_ana.split(".")
trocado = ".".join([p[0], p[1], "finance~" + p[2].split("~", 1)[1], p[3]])
confere("trocar o escopo do token invalida a assinatura", hc.sessao_valida(trocado, "finance") is None)
confere("o escopo do token é lido do próprio token", hc._escopo_do_token(tk_ana) == "jogos" and hc._escopo_do_token(tk_dono) == "*")
try:
    hc.nova_sessao("Jogos; x")
    confere("escopo inválido é recusado", False)
except ValueError:
    confere("escopo inválido é recusado", True)

# HTTP: convidado no painel de jogos e dono no mesmo painel
os.environ["HEIMDALL_CFACCESS_AUD"] = AUD
cfa._cache.update(chaves={}, quando=0.0, tentou=0.0, equipe="")
st, _, cab = pedir("/entrar", {cfa.CABECALHO: jwt({"email": "ana@exemplo.test"})})
ck_ana = cab.get("Set-Cookie", "").split(";")[0]
confere("convidado liberado para jogos recebe sessão no painel de jogos", st == 303 and ck_ana.startswith(hc.COOKIE + "="), (st, cab))
st, corpo, _ = pedir("/", {"Cookie": ck_ana})
confere("e com ela abre os jogos", st == 200 and "<h1>Jogos</h1>" in corpo)
st, _, cab = pedir("/entrar", {cfa.CABECALHO: jwt({"email": "beto@exemplo.test"})})
confere("convidado de dois serviços também entra em jogos", st == 303 and cab.get("Set-Cookie"))
os.environ["HEIMDALL_CFACCESS_CONVIDADOS"] = "ana@exemplo.test=finance"
st, _, cab = pedir("/entrar", {cfa.CABECALHO: jwt({"email": "ana@exemplo.test"})})
confere("convidado liberado só para outro serviço não entra em jogos", st == 200 and "Set-Cookie" not in cab, (st, cab))
st, _, _ = pedir("/", {"Cookie": ck_ana})
confere("sessão antiga de convidado vale enquanto durar a sessão (derrubar: trocar a senha ou o código)", st == 200)
os.environ.pop("HEIMDALL_CFACCESS_CONVIDADOS")

# o login por senha e código segue intacto
confere("login errado continua sendo recusado", hc.confere_senha("errada", hc.SENHA_HASH) is False)

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
