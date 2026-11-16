#!/usr/bin/env python3
"""Testa financas_arquivos.py: leitura de PDF, detecção do banco, inspeção anônima, conferência de total e pasta vigiada.
Usa banco e pastas temporários; nada toca a internet. Os textos de fatura e extrato são inventados."""
import io
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import financas_arquivos as fa  # noqa: E402
import financas_nucleo as fn  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:400])


def pdf_de(texto: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for ln in texto.splitlines():
        c.drawString(40, y, ln)
        y -= 14
    c.save()
    return buf.getvalue()


FATURA = """Fatura do cartão Nubank
Vencimento 10/12/2026   Fechamento 03/12/2026
Limite disponível R$ 4.000,00
03 NOV   Supermercado Exemplo   R$ 120,50
05 NOV   Padaria Esquina   R$ 30,00
12 NOV   Estorno compra   -R$ 20,00
28 NOV   Pagamento em 25 NOV   -R$ 50,00
Total da fatura R$ 80,50
"""
CONTA = """Extrato Itaú conta corrente 2026
02/11/2026   SALDO ANTERIOR   1.000,00
03/11/2026   PIX RECEBIDO FULANO   500,00   1.500,00
04/11/2026   COMPRA MERCADO EXEMPLO   -120,50   1.379,50
Total de entradas 500,00
"""

# ---- máscara anônima
m = fa.mascarar_linha("12/11/2026  MARIA APARECIDA SILVA  Valor R$ 1.234,56  conta 12345-6")
confere("máscara troca números por 9 e nomes por x", "MARIA" not in m and "SILVA" not in m and "1" not in m.replace("9", "") and "XXXXX" in m, m)
confere("máscara mantém rótulos do vocabulário", "Valor" in m and "conta" in m and "R" in m, m)
confere("máscara mantém a forma de datas e valores", "99/99/9999" in m and "9.999,99" in m, m)
confere("máscara não deixa passar o nome de uma loja nem um número", "Exemplo" not in fa.mascarar_linha("Supermercado Exemplo 45,90") and "45" not in fa.mascarar_linha("Supermercado Exemplo 45,90"))
confere("a máscara agrupa linhas iguais", "repete 3 vezes" in fa.mascarar("\n".join(["01/01 Loja a 1,00"] * 3)))

# ---- detecção
confere("detecta Nubank cartão", fa.detectar(FATURA, "fatura.pdf") == ("Nubank", "cartão"), fa.detectar(FATURA, "fatura.pdf"))
confere("detecta Itaú conta", fa.detectar(CONTA, "x.pdf") == ("Itaú", "conta"), fa.detectar(CONTA, "x.pdf"))
confere("detecta pelo nome do arquivo", fa.detectar("", "extrato_mercadopago_nov.csv") == ("Mercado Pago", "conta"), fa.detectar("", "extrato_mercadopago_nov.csv"))
confere("sem pistas, não chuta", fa.detectar("abc", "arquivo.csv") == ("", ""))
confere("CSV de cartão no formato date,category,title,amount é cartão", fa.detectar("date,category,title,amount\n2026-11-03,x,y,10.00", "nubank.csv") == ("Nubank", "cartão"))

# ---- leitor de texto
itens, info = fa.ler_pdf_texto(FATURA, "cartão")
confere("fatura: 4 lançamentos", len(itens) == 4, itens)
confere("fatura: compras negativas e crédito positivo", [i["valor"] for i in itens] == [-12050, -3000, 2000, 5000], [i["valor"] for i in itens])
confere("fatura: ano e dia certos nas datas 'dd MES'", itens[0]["data"] == "2026-11-03", itens[0])
confere("fatura: o total do documento confere", info["confere"] is True and info["gastos"] == 15050, info)
itens, info = fa.ler_pdf_texto(CONTA, "conta")
confere("conta: ignora saldo anterior e a coluna de saldo", [i["valor"] for i in itens] == [50000, -12050], itens)
confere("conta: descrição sem saldo", itens[0]["descricao"] == "PIX RECEBIDO FULANO", itens[0])
itens, info = fa.ler_pdf_texto(FATURA.replace("80,50", "99,99"), "cartão")
confere("total que não bate é sinalizado", info["confere"] is False, info)
itens, info = fa.ler_pdf_texto("03/11 Loja 10,00\n", "cartão")
confere("sem total no documento, a conferência fica indefinida", info["confere"] is None, info)
confere("data dd/mm sem ano usa o ano do documento", itens[0]["data"] == f"{__import__('datetime').date.today().year}-11-03", itens)
itens, _ = fa.ler_pdf_texto("Fatura 10/01/2027\n28/12 Loja 10,00\n", "cartão")
confere("compra de dezembro em fatura de janeiro fica no ano anterior", itens[0]["data"] == "2026-12-28", itens)
itens, _ = fa.ler_pdf_texto("Parcela 02/05 Loja 99,00\n03/11/2026 Loja parcela 02/05 50,00", "cartão")
confere("'02/05' dentro da descrição não vira data", len(itens) == 1 and itens[0]["valor"] == -5000, itens)

# ---- PDF de verdade
try:
    pdf = pdf_de(FATURA)
    texto = fa.texto_do_pdf(pdf)
    confere("extrai o texto de um PDF", "Supermercado Exemplo" in texto and "Total da fatura" in texto, texto[:200])
    a = fa.analisar(pdf, "fatura-nubank.pdf")
    confere("analisa PDF: banco, tipo, conta e conferência", (a["banco"], a["tipo"], a["conta"], a["confere"]) == ("Nubank", "cartão", "Nubank cartão", True), (a["banco"], a["tipo"], a["conta"], a["confere"]))
    ins = fa.inspecionar(pdf, "fatura.pdf")
    confere("a inspeção do PDF não vaza nome de loja nem valores", "Exemplo" not in ins and "120" not in ins and "Total da fatura" in ins, ins)
    confere("a inspeção do PDF mostra a estrutura", "99 XXX" in ins or "99 xxx" in ins or "99/99" in ins, ins[:300])
    pdf_ok = True
except Exception as ex:  # noqa: BLE001
    confere("PDF de teste", False, repr(ex))
    pdf_ok = False

# ---- importação
tmp = Path(tempfile.mkdtemp(prefix="finance_arq_"))
con = fn.conectar(tmp / "t.db")
if pdf_ok:
    r = fa.importar_arquivo(con, pdf, "fatura-nubank.pdf")
    confere("importa PDF que confere, na conta detectada", r["novas"] == 4 and r["conta"] == "Nubank cartão", r)
    r2 = fa.importar_arquivo(con, pdf, "fatura-nubank.pdf")
    confere("importar o PDF de novo não duplica", r2["novas"] == 0 and r2["repetidas"] == 4, r2)
    ruim = pdf_de(FATURA.replace("80,50", "99,99"))
    try:
        fa.importar_arquivo(con, ruim, "fatura-nubank.pdf", "Nubank cartão")
        confere("PDF que não confere é recusado", False)
    except fn.ErroFinance as ex:
        confere("PDF que não confere é recusado, com o motivo", "não conferiu" in str(ex), str(ex))
    r3 = fa.importar_arquivo(con, ruim, "fatura-nubank-2.pdf", "Nubank cartão", forcar=True)
    confere("com 'forçar' o PDF que não conferiu entra", r3["lidas"] == 4)
try:
    fa.importar_arquivo(con, b"date,valor\n", "qualquer.csv")
    confere("sem conta nem pistas pede a conta", False)
except fn.ErroFinance as ex:
    confere("sem conta nem pistas pede a conta ou acusa o cabeçalho", True)
csv_nu = "date,category,title,amount\n2026-11-03,compras,Padaria Esquina,30.00\n2026-11-04,compras,Estorno,-10.00\n".encode()
r = fa.importar_arquivo(con, csv_nu, "nubank-fatura.csv")
tot = con.execute("SELECT valor FROM transacoes WHERE conta='Nubank cartão' AND descricao='Padaria Esquina'").fetchone()
confere("CSV de cartão do Nubank inverte o sinal sozinho", tot and tot["valor"] == -3000, tot and tot["valor"])

# ---- pasta vigiada
base = tmp / "dados"
entrada = fa.preparar_pasta(base)
confere("cria entrada, importados e revisar", all((entrada / s).is_dir() for s in ("importados", "revisar")))
ofx = b"""OFXHEADER:100\r\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST><STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261105<TRNAMT>-45.90<FITID>A1<MEMO>Loja Teste</STMTTRN></BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""
(entrada / "extrato itau novembro.ofx").write_bytes(ofx)
(entrada / "misterio.csv").write_bytes(b"coluna1;coluna2\n1;2\n")
(entrada / ".oculto.csv").write_bytes(b"x")
(entrada / "nota.docx").write_bytes(b"x")
if pdf_ok:
    (entrada / "fatura-itau-ruim.pdf").write_bytes(ruim)
for f in entrada.iterdir():
    os.utime(f, (time.time() - 60, time.time() - 60))
res = fa.processar_entrada(con, base)
nomes = {r["arquivo"]: r for r in res}
confere("OFX com banco no nome entra na conta certa", nomes["extrato itau novembro.ofx"]["ok"] and nomes["extrato itau novembro.ofx"]["conta"] == "Itaú conta", nomes)
confere("o arquivo importado vai para importados/", (entrada / "importados" / "extrato itau novembro.ofx").is_file() and not (entrada / "extrato itau novembro.ofx").exists())
confere("CSV sem pistas vai para revisar com o motivo", (not nomes["misterio.csv"]["ok"]) and (entrada / "revisar" / "misterio.csv.motivo.txt").is_file(), nomes.get("misterio.csv"))
if pdf_ok:
    confere("PDF que não confere vai para revisar", not nomes["fatura-itau-ruim.pdf"]["ok"] and (entrada / "revisar" / "fatura-itau-ruim.pdf").is_file(), nomes.get("fatura-itau-ruim.pdf"))
confere("arquivo oculto e extensão desconhecida ficam quietos", ".oculto.csv" not in nomes and "nota.docx" not in nomes and (entrada / ".oculto.csv").exists())
confere("a lista de pendentes traz o motivo", any(n == "misterio.csv" and m for n, m in fa.pendentes(base)), fa.pendentes(base))
(entrada / "recente.ofx").write_bytes(ofx.replace(b"A1", b"A2"))
confere("arquivo recém-copiado espera a próxima rodada", fa.processar_entrada(con, base) == [] and (entrada / "recente.ofx").exists())

# ---- linha de comando
env = dict(os.environ, HEIMDALL_FINANCE_DIR=str(tmp / "cli"))
(tmp / "f.pdf").write_bytes(pdf) if pdf_ok else None
if pdf_ok:
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--inspecionar", str(tmp / "f.pdf")], capture_output=True, text=True, env=env, timeout=60)
    confere("--inspecionar imprime só a estrutura", p.returncode == 0 and "Estrutura anônima (PDF)" in p.stdout and "Exemplo" not in p.stdout, p.stdout[:300] + p.stderr[:200])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--prever", str(tmp / "f.pdf")], capture_output=True, text=True, env=env, timeout=60)
    confere("--prever mostra o resumo e não grava", p.returncode == 0 and "bate" in p.stdout and not (tmp / "cli" / "financas.db").exists(), p.stdout[:300] + p.stderr[:200])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--importar", str(tmp / "f.pdf")], capture_output=True, text=True, env=env, timeout=60)
    confere("--importar grava na conta detectada", p.returncode == 0 and "Nubank cartão" in p.stdout and "4 novos" in p.stdout, p.stdout[:300] + p.stderr[:200])
p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--pasta"], capture_output=True, text=True, env=env, timeout=60)
confere("--pasta mostra o caminho da entrada", p.returncode == 0 and "entrada" in p.stdout, p.stdout + p.stderr)
p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--inspecionar", str(tmp / "nao_existe.pdf")], capture_output=True, text=True, env=env, timeout=60)
confere("arquivo que não existe dá mensagem clara", p.returncode != 0 and "Não achei o arquivo" in p.stderr, p.stderr)

print()
print("FALHAS: " + str(falhas))
sys.exit(1 if falhas else 0)
