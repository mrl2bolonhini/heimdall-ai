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
from datetime import date
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


import financas_arquivos as fa
import financas_boletos as fb  # noqa: E402
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


def _colar() -> str:
    exe = shutil.which("pbpaste")
    if not exe:
        sys.exit("Não achei o pbpaste (só existe no Mac). Rode este comando no Mac.")
    try:
        return subprocess.run([exe], capture_output=True, timeout=10, check=True).stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError):
        sys.exit("Não consegui ler a área de transferência.")


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
    g.add_argument("--boleto", metavar="LINHA_OU_PDF")
    g.add_argument("--boletos", action="store_true")
    g.add_argument("--ler-email", dest="ler_email", action="store_true")
    g.add_argument("--sincronizar", action="store_true")
    g.add_argument("--deduplicar", action="store_true")
    g.add_argument("--padronizar-nomes", dest="padronizar_nomes", action="store_true")
    g.add_argument("--renomear-conta", dest="renomear_conta", action="append")
    g.add_argument("--guardar-pluggy", dest="guardar_pluggy", choices=["id", "segredo", "itens"])
    ap.add_argument("--valores", action="store_true")
    ap.add_argument("--linhas", type=int, default=150)
    ap.add_argument("--conta", default="")
    ap.add_argument("--pessoa", default="")
    ap.add_argument("--dias", type=int, default=None)
    ap.add_argument("--desde", default="")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--nomear", action="append", default=[])
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
            texto = fa.explicar(dados, nome, max(20, a.linhas if a.linhas != 150 else 400), a.valores)
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
        elif a.boleto:
            con = _banco()
            p = Path(a.boleto).expanduser()
            beneficiario, arquivo = "", ""
            if p.is_file():
                texto = fa.texto_do_pdf(p.read_bytes()) if p.suffix.lower() == ".pdf" else p.read_text(encoding="utf-8", errors="replace")
                achadas = fb.achar_linhas(texto)
                if not achadas:
                    sys.exit("Não achei uma linha digitável válida nesse arquivo. Se o código estiver impresso, rode de novo passando só os números entre aspas.")
                beneficiario, arquivo = fb.beneficiario_do_texto(texto), p.name
            else:
                achadas = [fb.completar_pix(fb.interpretar(a.boleto))]
            for b in achadas:
                dono = a.pessoa or (fb.dono_do_texto(texto, fb.pessoas(con)) if p.is_file() else "")
                if a.pessoa and a.pessoa not in fb.pessoas(con):
                    fb.adicionar_pessoa(con, a.pessoa)
                idb, novo = fb.registrar(con, b, beneficiario, arquivo, None, dono)
                print(("Registrado" if novo else "Já estava registrado") + f" (número {idb}): " + fb.frase({**b, "beneficiario": beneficiario or b.get("beneficiario", ""), "dono": dono}))
            print("\nO Heimdall não paga nada: só guarda a conta a pagar. Veja em heimdall finance, página Boletos, ou com heimdall finance --bills.")
        elif a.guardar_pluggy:
            import financas_pluggy as fpl
            print(fpl.guardar_chave(a.guardar_pluggy, _colar()))
            if a.guardar_pluggy == "segredo" and shutil.which("pbcopy"):
                subprocess.run(["pbcopy"], input=b"", timeout=10)
                print("A área de transferência foi esvaziada, para o segredo não ficar copiado.")
        elif a.deduplicar:
            con = _banco()
            achados = fn.repetidos_entre_fontes(con, aplicar=a.forcar)
            for conta, n in sorted(achados.items()):
                print(f"{conta}: {n} lançamento(s) do Pluggy repetem lançamentos de extrato (mesmo dia e valor).")
            if not achados:
                print("Nenhum lançamento do Pluggy repete extrato ou fatura.")
            elif a.forcar:
                print(f"Apaguei {sum(achados.values())} lançamento(s) do Pluggy repetidos; os de extrato ficam. Rode de novo para conferir.")
            else:
                print("Nada foi apagado. Para apagar os do Pluggy repetidos, rode: heimdall finance --dedupe --force")
        elif a.padronizar_nomes:
            import financas_pluggy as fpl
            cfg = fpl.credenciais()
            if not cfg:
                sys.exit("Faltam chaves do Pluggy no .env.")
            con = _banco()
            arq = DIR_DADOS / "pluggy_estado.json"
            estado = fpl.ler_estado(arq)
            feitos = fpl.padronizar_nomes(con, estado, cfg)
            fpl.gravar_estado(arq, estado)
            for antigo, novo, n, erro in feitos:
                print(f"Não renomeei \"{antigo}\": {erro}" if erro else f"\"{antigo}\" passou a se chamar \"{novo}\" ({n} lançamentos).")
            if not feitos:
                print("Todos os nomes já seguem o padrão.")
        elif a.renomear_conta:
            import financas_pluggy as fpl
            con = _banco()
            arq = DIR_DADOS / "pluggy_estado.json"
            estado = fpl.ler_estado(arq)
            aspas = "\"'\u201c\u201d\u2018\u2019 "
            for par in a.renomear_conta:
                antigo, _, novo = par.partition("=")
                antigo, novo = antigo.strip(aspas), novo.strip(aspas)
                try:
                    n = fpl.renomear_conta_finance(con, antigo, novo, estado)
                except fpl.ErroPluggy as ex:
                    print(f"Não renomeei \"{antigo}\": {ex}")
                    continue
                print(f"A conta \"{antigo}\" passou a se chamar \"{novo[:60]}\" no Finance ({n} lançamentos).")
            fpl.gravar_estado(arq, estado)
        elif a.sincronizar:
            import financas_pluggy as fpl
            cfg = fpl.credenciais()
            if not cfg:
                sys.exit("Faltam chaves do Pluggy no .env. Guarde as três, copiando cada uma antes: heimdall finance --guardar-pluggy id; depois segredo; depois itens.")
            con = _banco()
            arq = DIR_DADOS / "pluggy_estado.json"
            estado = fpl.ler_estado(arq)
            if a.listar or a.nomear:
                contas = fpl.listar_contas(cfg, estado, con)
                for par in a.nomear:
                    n, _, nome = par.partition("=")
                    if not n.strip().isdigit() or not 1 <= int(n) <= len(contas):
                        sys.exit(f"Use --nomear NÚMERO=NOME, com o número da lista (1 a {len(contas)}). Exemplo: --nomear 2=\"Itaú conta\"")
                    fpl.definir_nome(estado, contas[int(n) - 1]["id"], nome)
                    contas[int(n) - 1]["nome"] = nome.strip()[:60]
                    print(f"Conta {n} passa a se chamar {nome.strip()[:60]} no Finance.")
                fpl.gravar_estado(arq, estado)
                for i, c in enumerate(contas, 1):
                    print(f"{i}. {c['tipo']} {c['rotulo']}" + (f", {c['subtipo']}" if c.get("subtipo") else "") + (f", final {c['final']}" if c["final"] else "") + (f", saldo {c['saldo']:.2f}".replace(".", ",") if c.get("saldo") is not None else "") + f". No Finance: {c['nome']}." + (f" Atenção: já existe no Finance a conta \"{c['existente']}\" (de extrato); para manter o histórico, rode antes: heimdall finance --renomear-conta \"{c['existente']}={c['nome']}\"." if c.get("existente") else ""))
                print("\nPara trocar o nome: heimdall finance --sincronizar --nomear 2=\"Itaú conta\" (use o nome de uma conta já importada por extrato para não duplicar).")
            else:
                desde = None
                if a.desde:
                    try:
                        desde = date.fromisoformat(a.desde)
                    except ValueError:
                        sys.exit("Use a data no formato AAAA-MM-DD, por exemplo 2026-01-01.")
                r = fpl.executar(con, cfg, arq, desde)
                for c in r["contas"]:
                    print(f"{c['conta']}: {c['novas']} nova(s), {c['repetidas']} repetida(s), a partir de {fn.data_br(c['desde'])} (o Pluggy devolveu {c.get('recebidas', 0)}).")
                if not r["contas"]:
                    print("Nenhuma conta encontrada nos bancos conectados.")
                for av in r["avisos"]:
                    print(f"ATENÇÃO: {av}")
                print("\nSó li as contas e transações (nada foi movido nem pago). O Meu Pluggy atualiza a cada 24 horas.")
        elif a.ler_email:
            import financas_email as femail
            cfg = femail.credenciais()
            if not cfg:
                sys.exit("Não achei a senha de aplicativo do Gmail no .env (HEIMDALL_EMAIL_USUARIO e HEIMDALL_EMAIL_SENHA_APP). Instale o monitor de e-mails oficiais primeiro: heimdall privacy --email.")
            dias = max(1, min(a.dias or femail.DIAS, femail.MAX_DIAS))
            diag = {}
            res = femail.executar(_banco(), cfg, DIR_DADOS / "email_estado.json", dias=dias, diag=diag, ignorar_vistos=True)
            print(f"A busca no Gmail (só Caixa de entrada, últimos {dias} dias) trouxe {diag.get('total', 0)} mensagem(ns) com termos de cobrança"
                  + (f"; o limite é de {femail.LIMITE} por rodada, então pode haver mais antigas" if diag.get("total", 0) >= femail.LIMITE else "") + ".")
            if not res:
                print("Nenhum boleto ou Pix com dígitos corretos nelas.")
            grupos = {}
            for dom, assunto, motivo in diag.get("descartes", []):
                grupos.setdefault((dom, motivo), []).append(assunto)
            for (dom, motivo), assuntos in sorted(grupos.items(), key=lambda kv: -len(kv[1])):
                exemplo = "; ".join(dict.fromkeys(assuntos[:3]))
                print(f"Descartado: {len(assuntos)} e-mail(s) de {dom} (por exemplo: {exemplo}): {motivo}.")
            for r in res:
                print(f"E-mail de {r['remetente']} ({r['assunto']}): {r['novos']} novo(s), {r['repetidos']} já registrado(s)." + (f" ATENÇÃO: {r['aviso']}" if r["aviso"] else "") + (f" Já programado: {r['motivo']}." if r.get("motivo") else ""))
            print("\nSó li os e-mails (nada foi marcado, movido ou apagado) e nada foi pago.")
        elif a.boletos:
            con = _banco()
            lista = fb.listar(con)
            if not lista:
                print("Nenhum boleto em aberto.")
            prog = [b for b in fb.listar(con, incluir_pagos=True) if b["estado"] == "programado"]
            if prog:
                print(f"{len(prog)} boleto(s) já programado(s) em débito automático ou cartão ficaram de fora:")
                for b in prog:
                    print(f"  {fb.frase(b)}. {b['motivo']}")
            for b in lista:
                dias = b["dias"] or 0
                quando = {"vencido": f"vencido há {-dias} dia(s)", "vence hoje": "vence hoje", "a vencer": f"vence em {dias} dia(s)"}.get(b["estado"], "sem vencimento")
                print(f"{b['id']}. {fb.frase(b)} ({quando})")
            tot = {}
            for b in lista:
                tot[b["dono"] or "sem pessoa"] = tot.get(b["dono"] or "sem pessoa", 0) + (b["valor"] or 0)
            if len(tot) > 1 or (tot and "sem pessoa" not in tot):
                print("\nTotal em aberto por pessoa: " + "; ".join(f"{k} {fn.brl(v)}" for k, v in sorted(tot.items())) + ".")
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
                elif r.get("boleto"):
                    print(f"Boleto: {r['arquivo']}: {r['novas']} novo(s) registrado(s) como conta a pagar. {r['motivo']}")
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
