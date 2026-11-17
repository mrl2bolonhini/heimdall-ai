#!/usr/bin/env python3
"""Comandos de terminal do Heimdall Finance para arquivos (heimdall finance --inspect, --preview, --import, --inbox, --folder).

    python3 financas_cli.py --inspecionar ARQUIVO [--linhas N]   mostra só a estrutura (letras viram x, números viram 9) e copia para a área de transferência
    python3 financas_cli.py --explicar ARQUIVO [--linhas N]       mostra, linha por linha e de forma anônima, o que o leitor de PDF fez com cada linha
    python3 financas_cli.py --prever ARQUIVO                      mostra o que seria importado, sem gravar
    python3 financas_cli.py --importar ARQUIVO [--conta NOME] [--forcar]
    python3 financas_cli.py --entrada                             importa o que estiver na pasta de entrada
    python3 financas_cli.py --pasta [--abrir]                     mostra (e abre) a pasta de entrada

A pasta de entrada é dados_financas/entrada. Arquivos que importam vão para importados/; os que deixam dúvida vão para revisar/,
cada um com um .motivo.txt. Os dados ficam só neste Mac.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))


def _env_dir() -> str:
    """HEIMDALL_FINANCE_DIR do ambiente ou do .env (sem carregar o resto do .env)."""
    if os.environ.get("HEIMDALL_FINANCE_DIR"):
        return os.environ["HEIMDALL_FINANCE_DIR"]
    env = AQUI / ".env"
    try:
        for ln in env.read_text(encoding="utf-8").splitlines():
            if ln.startswith("HEIMDALL_FINANCE_DIR="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


import financas_arquivos as fa  # noqa: E402
import financas_nucleo as fn  # noqa: E402

DIR_DADOS = Path(_env_dir() or (AQUI / "dados_financas"))


def _banco():
    DIR_DADOS.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DIR_DADOS, 0o700)
    except OSError:
        pass
    return fn.conectar(DIR_DADOS / "financas.db")


def _ler(caminho: str) -> tuple:
    p = Path(caminho).expanduser()
    if not p.is_file():
        sys.exit(f"Não achei o arquivo: {caminho}")
    return p.read_bytes(), p.name


def _copiar(texto: str) -> bool:
    exe = shutil.which("pbcopy")
    if not exe:
        return False
    try:
        subprocess.run([exe], input=texto.encode("utf-8"), check=True, timeout=10)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Arquivos do Heimdall Finance")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inspecionar", metavar="ARQUIVO")
    g.add_argument("--explicar", metavar="ARQUIVO")
    g.add_argument("--prever", metavar="ARQUIVO")
    g.add_argument("--importar", metavar="ARQUIVO")
    g.add_argument("--entrada", action="store_true")
    g.add_argument("--pasta", action="store_true")
    g.add_argument("--reprocessar", action="store_true")
    ap.add_argument("--linhas", type=int, default=150)
    ap.add_argument("--conta", default="")
    ap.add_argument("--forcar", action="store_true")
    ap.add_argument("--abrir", action="store_true")
    a = ap.parse_args()
    try:
        if a.inspecionar:
            dados, nome = _ler(a.inspecionar)
            texto = fa.inspecionar(dados, nome, max(10, a.linhas))
            print(texto)
            if _copiar(texto):
                print("\nCopiado para a área de transferência. Cole na conversa com Command+V. Nenhuma letra ou número real foi mantido.")
        elif a.explicar:
            dados, nome = _ler(a.explicar)
            texto = fa.explicar(dados, nome, max(20, a.linhas if a.linhas != 150 else 400))
            print(texto)
            if _copiar(texto):
                print("\nCopiado para a área de transferência. Cole na conversa com Command+V. Nenhuma letra ou número real foi mantido.")
        elif a.prever:
            dados, nome = _ler(a.prever)
            an = fa.analisar(dados, nome)
            print(fa.resumo_texto(an))
            print("\nPrimeiros lançamentos lidos:")
            for it in an["itens"][:15]:
                print(f"{fn.data_br(it['data'])}  {fn.brl(it['valor'], True):>14}  {it['descricao'][:60]}")
            print("\nNada foi gravado. Para importar: heimdall finance --import ARQUIVO" + ("" if an["conta"] else " --account NOME"))
        elif a.importar:
            dados, nome = _ler(a.importar)
            con = _banco()
            r = fa.importar_arquivo(con, dados, nome, a.conta, a.forcar)
            fa.concluir_revisao(DIR_DADOS, Path(a.importar).expanduser())  # se veio de revisar/, vai para importados/ e o motivo some
            print(r["resumo"])
            print(f"\nImportado na conta '{r['conta']}': {r['novas']} novos, {r['repetidas']} já existentes.")
        elif a.entrada or a.reprocessar:
            if a.reprocessar:
                movidos = fa.devolver_para_entrada(DIR_DADOS)
                if not movidos:
                    print("Nada em revisar para tentar de novo.")
                for nome, ok, aviso in movidos:
                    print(f"Voltou para entrada: {nome}" if ok else f"Não movi {nome}: {aviso}")
            con = _banco()
            res = fa.processar_entrada(con, DIR_DADOS)
            if not res:
                print(f"Nada novo em {DIR_DADOS / 'entrada'}.")
            for r in res:
                if r.get("limpeza"):
                    print(f"Limpei {r['limpeza']} arquivo(s) de motivo de itens que já saíram de revisar.")
                elif r.get("duplicado"):
                    print(f"Duplicado: {r['arquivo']}: {r['motivo']}")
                elif r["ok"]:
                    print(f"Importado: {r['arquivo']} -> {r['conta']}: {r['novas']} novos, {r['repetidas']} já existentes.")
                else:
                    print(f"Para revisar: {r['arquivo']}: {r['motivo']}")
        else:
            pasta = fa.preparar_pasta(DIR_DADOS)
            fa._limpar_motivos(pasta / "revisar")
            print(f"Pasta de entrada: {pasta}")
            for nome, motivo in fa.pendentes(DIR_DADOS):
                print(f"Para revisar: {nome}: {motivo}")
            if a.abrir and shutil.which("open"):
                subprocess.run(["open", str(pasta)], check=False)
    except fn.ErroFinance as ex:
        sys.exit(str(ex))


if __name__ == "__main__":
    main()
