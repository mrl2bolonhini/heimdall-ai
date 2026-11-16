#!/usr/bin/env python3
"""Entrada pelo Cloudflare Access (Microsoft Entra ID), com aprovação por notificação no Microsoft Authenticator.

Como funciona: o Cloudflare Access fica na frente dos endereços públicos (cloud, notas, news, saúde, jogos...).
Quem chega é mandado ao login da Microsoft; o Authenticator no celular recebe a notificação e você aprova
digitando no celular o número mostrado na tela. Só então o Cloudflare deixa o pedido passar, com um documento
assinado (JWT) no cabeçalho Cf-Access-Jwt-Assertion. Os painéis conferem a assinatura aqui, sem biblioteca de fora,
e, estando tudo certo, abrem a sessão sem pedir senha nem código de 6 dígitos.

Fica DESLIGADO até você preencher três valores no .env:

    HEIMDALL_CFACCESS_EQUIPE   nome da equipe no Cloudflare Zero Trust (a parte antes de .cloudflareaccess.com)
    HEIMDALL_CFACCESS_AUD      "AUD tag" do aplicativo do Access (um texto comprido de letras e números)
    HEIMDALL_CFACCESS_EMAILS   e-mails aceitos, separados por vírgula (o do usuário que você criou na Microsoft)

Acesso pelo Tailscale ou por localhost não passa pelo Cloudflare: nesses, continua valendo senha e código de 6 dígitos.

    python3 heimdall_cfaccess.py --status      mostra a configuração e se os certificados do Cloudflare respondem
    python3 heimdall_cfaccess.py --verificar   confere um token colado (pedido sem aparecer na tela)
"""
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.request

CABECALHO = "Cf-Access-Jwt-Assertion"
TOLERANCIA = 30  # segundos de folga entre relógios
CACHE_SEG = 3600
RECARGA_MIN = 60  # só busca os certificados de novo, por chave desconhecida, a cada 60 s
_PREFIXO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")  # DigestInfo do SHA-256 (RFC 8017)

_lock = threading.Lock()
_cache = {"chaves": {}, "quando": 0.0, "tentou": 0.0, "equipe": ""}


def config() -> dict:
    """Lê do ambiente a cada chamada (o .env é carregado pelo subir.sh antes dos serviços)."""
    equipe = os.environ.get("HEIMDALL_CFACCESS_EQUIPE", "").strip().lower()
    if equipe.endswith(".cloudflareaccess.com"):
        equipe = equipe[: -len(".cloudflareaccess.com")]
    aud = os.environ.get("HEIMDALL_CFACCESS_AUD", "").strip()
    emails = {e.strip().lower() for e in os.environ.get("HEIMDALL_CFACCESS_EMAILS", "").split(",") if e.strip()}
    return {"equipe": equipe, "aud": aud, "emails": emails}


def ativo() -> bool:
    """Só liga com os três valores e com a equipe em formato válido (vai para um endereço de internet)."""
    c = config()
    return bool(c["equipe"] and c["aud"] and c["emails"] and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", c["equipe"]))


def _b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _buscar_chaves(equipe: str) -> dict:
    url = f"https://{equipe}.cloudflareaccess.com/cdn-cgi/access/certs"
    req = urllib.request.Request(url, headers={"User-Agent": "heimdall-cfaccess/1"})
    with urllib.request.urlopen(req, timeout=6) as r:
        dados = json.loads(r.read(200_000).decode("utf-8", "replace"))
    chaves = {}
    for k in dados.get("keys", []):
        if k.get("kty") == "RSA" and k.get("kid") and k.get("n") and k.get("e"):
            chaves[k["kid"]] = (int.from_bytes(_b64(k["n"]), "big"), int.from_bytes(_b64(k["e"]), "big"))
    return chaves


def _chave(kid: str, equipe: str, agora: float, buscar=None):
    """Chave pública do certificado com este kid. Cache de 1 hora; kid novo força uma busca (no máximo a cada 60 s)."""
    buscar = buscar or _buscar_chaves
    with _lock:
        if _cache["equipe"] != equipe:
            _cache.update(chaves={}, quando=0.0, tentou=0.0, equipe=equipe)
        velho = agora - _cache["quando"] > CACHE_SEG
        if (velho or kid not in _cache["chaves"]) and agora - _cache["tentou"] >= RECARGA_MIN:
            _cache["tentou"] = agora
            try:
                _cache["chaves"] = buscar(equipe)
                _cache["quando"] = agora
            except Exception as ex:  # noqa: BLE001
                sys.stderr.write(f"{time.strftime('%H:%M:%S')} cfaccess: não consegui buscar os certificados: {type(ex).__name__}\n")
        return _cache["chaves"].get(kid)


def _assinatura_confere(n: int, e: int, assinada: bytes, assinatura: bytes) -> bool:
    """RSASSA-PKCS1-v1_5 com SHA-256 (RS256), só com a biblioteca padrão."""
    k = (n.bit_length() + 7) // 8
    if len(assinatura) != k or k < 64:
        return False
    s = int.from_bytes(assinatura, "big")
    if s >= n:
        return False
    em = pow(s, e, n).to_bytes(k, "big")
    t = _PREFIXO_SHA256 + hashlib.sha256(assinada).digest()
    esperado = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return hmac.compare_digest(em, esperado)


def verificar_jwt(token: str, agora: float = None, buscar=None):
    """E-mail do usuário se o token do Access é legítimo e é de quem pode entrar; senão None."""
    if not ativo():
        return None
    c = config()
    agora = time.time() if agora is None else agora
    try:
        cab_b64, corpo_b64, ass_b64 = (token or "").strip().split(".")
        cab, corpo = json.loads(_b64(cab_b64)), json.loads(_b64(corpo_b64))
        if cab.get("alg") != "RS256" or not isinstance(cab.get("kid"), str):
            return None
        chave = _chave(cab["kid"], c["equipe"], agora, buscar)
        if not chave or not _assinatura_confere(chave[0], chave[1], f"{cab_b64}.{corpo_b64}".encode("ascii"), _b64(ass_b64)):
            return None
        if corpo.get("iss") != f"https://{c['equipe']}.cloudflareaccess.com":
            return None
        aud = corpo.get("aud")
        if c["aud"] not in (aud if isinstance(aud, list) else [aud]):
            return None
        exp = corpo.get("exp")
        if not isinstance(exp, (int, float)) or agora > exp + TOLERANCIA:
            return None
        nbf = corpo.get("nbf")
        if isinstance(nbf, (int, float)) and agora < nbf - TOLERANCIA:
            return None
        email = str(corpo.get("email", "")).strip().lower()
        return email if email in c["emails"] else None
    except Exception:  # noqa: BLE001 (token malformado: recusa)
        return None


def email_do_pedido(cabecalhos) -> str:
    """cabecalhos: o self.headers do servidor HTTP (ou qualquer objeto com .get)."""
    return verificar_jwt(cabecalhos.get(CABECALHO, "")) if ativo() else None


def _status() -> None:
    c = config()
    print("Equipe:", c["equipe"] or "(vazio)")
    print("AUD tag:", ("preenchida (%d caracteres)" % len(c["aud"])) if c["aud"] else "(vazio)")
    print("E-mails aceitos:", len(c["emails"]))
    print("Entrada pelo Cloudflare Access:", "LIGADA" if ativo() else "desligada (faltam valores no .env)")
    if not ativo():
        return
    try:
        chaves = _buscar_chaves(c["equipe"])
        print("Certificados do Cloudflare:", "ok, %d chave(s)" % len(chaves) if chaves else "resposta sem chaves")
    except Exception as ex:  # noqa: BLE001
        print("Certificados do Cloudflare: falhou (%s). Confira o nome da equipe e a internet." % type(ex).__name__)


def _verificar() -> None:
    if not ativo():
        print("Desligado: preencha HEIMDALL_CFACCESS_EQUIPE, _AUD e _EMAILS no .env.")
        return
    token = getpass.getpass("Cole o token (cookie CF_Authorization), sem aparecer na tela: ")
    email = verificar_jwt(token)
    print("Token válido para:", email if email else "NENHUM (inválido, expirado, de outro aplicativo ou de e-mail não permitido)")


if __name__ == "__main__":
    if "--verificar" in sys.argv:
        _verificar()
    else:
        _status()
