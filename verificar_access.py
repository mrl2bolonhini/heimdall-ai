#!/usr/bin/env python3
"""Confere se um endereço público está protegido pelo Cloudflare Access (sem entrar nele).

Uso: python3 verificar_access.py https://chat.studiolibre.io
Saída 0 = protegido (o Access manda a pessoa entrar antes), 1 = aberto (responde sem passar pelo Access: NÃO ligue o login pelo cabeçalho),
2 = sem resposta (o endereço está fora do ar ou sem internet; o login por cabeçalho fica seguro, porque ninguém de fora chega ao serviço).
"""
import sys
import urllib.error
import urllib.request


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def verificar(url: str, tempo: int = 8) -> tuple:
    """Devolve (código, frase)."""
    ab = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SemRedirecionar())
    req = urllib.request.Request(url, headers={"User-Agent": "heimdall-verificar-access"})
    try:
        r = ab.open(req, timeout=tempo)
        return 1, f"{url} respondeu {r.status} sem pedir entrada: o Access não está na frente."
    except urllib.error.HTTPError as ex:
        local = (ex.headers.get("Location") or "").lower()
        if "cloudflareaccess.com" in local or "/cdn-cgi/access/" in local:
            return 0, f"{url} manda entrar pelo Cloudflare Access ({ex.code})."
        if ex.code in (401, 403) and "cloudflare" in (ex.headers.get("Server") or "").lower():
            return 0, f"{url} recusa quem não entrou pelo Cloudflare ({ex.code})."
        if 300 <= ex.code < 400:
            return 1, f"{url} redireciona ({ex.code}) para {local or 'outro lugar'}, que não é o Access."
        return 1, f"{url} respondeu {ex.code} e não é do Access."
    except (urllib.error.URLError, OSError, ValueError) as ex:
        return 2, f"{url} não respondeu ({type(ex).__name__})."


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(64)
    cod, frase = verificar(sys.argv[1])
    print(frase)
    sys.exit(cod)
