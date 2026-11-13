#!/usr/bin/env python3
"""Senha e código de 6 dígitos de todos os serviços Heimdall com login (Cloud, Notas e News).

Os três usam o mesmo acesso, guardado no .env (a senha só como hash, nunca em texto). Aqui você troca o que precisar:

    python3 heimdall_acesso.py --tudo     nova senha e novo código de 6 dígitos
    python3 heimdall_acesso.py --senha    só troca a senha (o código de 6 dígitos continua o mesmo)
    python3 heimdall_acesso.py --codigo   só gera um novo código de 6 dígitos (perdeu o app, por exemplo)
    python3 heimdall_acesso.py --verificar confere, sem navegador, se a senha digitada e o código do app batem com o .env

Depois de trocar, reinicie para valer: ./subir.sh --reiniciar
A senha é digitada sem aparecer na tela. A chave do código aparece uma única vez, para você cadastrar no app Senhas.
"""
import argparse
import getpass
import re
import time

import heimdall_cloud as nuvem


def _ler_env() -> dict:
    """Lê direto do .env (e não do ambiente do terminal, que pode guardar valores antigos)."""
    out = {}
    try:
        linhas = (nuvem.PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for l in linhas:
        l = l.strip()
        if l.startswith("export "):
            l = l[7:]
        if l.startswith("HEIMDALL_CLOUD_") and "=" in l:
            k, v = l.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            out[k.strip()] = v
    return out


def verificar() -> None:
    env = _ler_env()
    h, seg = env.get("HEIMDALL_CLOUD_SENHA_HASH", ""), env.get("HEIMDALL_CLOUD_TOTP_SEGREDO", "")
    print("Senha gravada no .env:", "sim" if h.startswith("pbkdf2-sha256:") else "NÃO (ou em formato inválido): rode --tudo")
    print("Chave do código gravada no .env:", "sim" if seg else "NÃO: rode --codigo")
    if not h or not seg:
        return
    senha = getpass.getpass("Digite a senha como o Senhas a preenche (não aparece na tela): ")
    print("A senha digitada confere com a gravada:", "SIM" if nuvem.confere_senha(senha[:200], h) else "NÃO")
    if senha != senha.strip():
        print("Atenção: a senha digitada tem espaço no começo ou no fim.")
    chave = nuvem._chave_totp(seg)
    agora = time.time()
    atual = int(agora // 30)
    print("Código que o app Senhas deve mostrar agora:", nuvem._hotp(chave, atual), "(vale por mais %d segundos)" % (30 - int(agora % 30)))
    digitado = re.sub(r"\s", "", input("Digite o código que o app mostra neste momento (ou Enter para pular): "))
    if digitado:
        passo = nuvem.totp_contador(seg, digitado)
        if passo is None:
            print("O código do app NÃO confere: a chave cadastrada no Senhas não é a do .env (cadastre de novo com --codigo) ou o relógio do Mac está errado.")
        else:
            print("O código do app confere (diferença de %d passo(s) de 30 s em relação ao relógio do Mac)." % (passo - atual))
    print("Se tudo conferiu aqui e o site recusa, o serviço está com valores antigos: ./subir.sh --reiniciar e confira com ./subir.sh --log notas.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Senha e código de 6 dígitos dos serviços Heimdall (Cloud, Notas e News)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--tudo", action="store_true", help="nova senha e novo código de 6 dígitos")
    g.add_argument("--senha", action="store_true", help="só troca a senha")
    g.add_argument("--codigo", action="store_true", help="só gera um novo código de 6 dígitos")
    g.add_argument("--verificar", action="store_true", help="confere senha e código com o .env")
    a = ap.parse_args()
    if a.verificar:
        verificar()
        return
    nuvem.definir_acesso("tudo" if a.tudo else "senha" if a.senha else "codigo")


if __name__ == "__main__":
    main()
