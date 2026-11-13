#!/usr/bin/env python3
"""Senha e código de 6 dígitos de todos os serviços Heimdall com login (Cloud, Notas e News).

Os três usam o mesmo acesso, guardado no .env (a senha só como hash, nunca em texto). Aqui você troca o que precisar:

    python3 heimdall_acesso.py --tudo     nova senha e novo código de 6 dígitos
    python3 heimdall_acesso.py --senha    só troca a senha (o código de 6 dígitos continua o mesmo)
    python3 heimdall_acesso.py --codigo   só gera um novo código de 6 dígitos (perdeu o app, por exemplo)

Depois de trocar, reinicie para valer: ./subir.sh --reiniciar
A senha é digitada sem aparecer na tela. A chave do código aparece uma única vez, para você cadastrar no app Senhas.
"""
import argparse

import heimdall_cloud as nuvem


def main() -> None:
    ap = argparse.ArgumentParser(description="Senha e código de 6 dígitos dos serviços Heimdall (Cloud, Notas e News)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--tudo", action="store_true", help="nova senha e novo código de 6 dígitos")
    g.add_argument("--senha", action="store_true", help="só troca a senha")
    g.add_argument("--codigo", action="store_true", help="só gera um novo código de 6 dígitos")
    a = ap.parse_args()
    nuvem.definir_acesso("tudo" if a.tudo else "senha" if a.senha else "codigo")


if __name__ == "__main__":
    main()
