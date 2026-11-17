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

# ---- fatura com compras em duas colunas (layout comum de fatura de cartão)
DUAS = """Fatura do cartão Itaú
Vencimento:10/12/2026
DATA ESTABELECIMENTO VALOR EM R$   DATA ESTABELECIMENTO VALOR EM R$
03/11 PAGAMENTO EFETUADO -100,00   05/11 MERCADO EXEMPLO 50,00
ALIMENTACAO SAO PAULO              LAZER SAO PAULO
06/11 LOJA PARCELADA 03/10 120,00   08/11 PADARIA TESTE 30,50
Xx xx xx xx  09/11 FARMACIA TESTE 25,00
Total dos lançamentos atuais 225,50
"""
itens, info = fa.ler_pdf_texto(DUAS, "cartão")
confere("duas colunas: lê as cinco compras, uma por coluna", [i["descricao"] for i in itens] == ["PAGAMENTO EFETUADO", "MERCADO EXEMPLO", "LOJA PARCELADA 03/10", "PADARIA TESTE", "FARMACIA TESTE"], [i["descricao"] for i in itens])
confere("duas colunas: valores e sinais certos", [i["valor"] for i in itens] == [10000, -5000, -12000, -3050, -2500], [i["valor"] for i in itens])
confere("duas colunas: o total dos lançamentos confere", info["confere"] is True, info)
confere("parcela '03/10' antes do valor não abre uma compra nova", len(itens) == 5)

# ---- extrato do Itaú em PDF: data, lançamento, valor e saldo só nas linhas "SALDO DO DIA"
EXTRATO = """Itaú  agência: 1234   conta: 12345-6
saldo em conta    Limite da Conta utilizado    Limite da Conta disponível    Limite da Conta total *
extrato conta / lançamentos
período de visualização: 01/10/2026 até 31/10/2026    emitido em: 01/11/2026   10:00:00
data    lançamentos    valor (R$)    saldo (R$)
01/10/2026    SALDO DO DIA    1.000,00
02/10/2026    PIX TRANSF FULANO02/10    -100,00
02/10/2026    SISPAG EXEMPLO    300,00
02/10/2026    SALDO DO DIA    1.200,00
03/10/2026    FATURA ITAU UNICLASS 10/2026    -500,00
03/10/2026    IOF    -2,00
03/10/2026    SALDO DO DIA    698,00
"""
confere("extrato com 'fatura itau' na lista continua sendo conta", fa.detectar(EXTRATO, "extrato.pdf") == ("Itaú", "conta"), fa.detectar(EXTRATO, "extrato.pdf"))
itens, info = fa.ler_pdf_texto(EXTRATO, "conta")
confere("extrato: lê só os lançamentos, sem saldos", [i["valor"] for i in itens] == [-10000, 30000, -50000, -200], [i["valor"] for i in itens])
confere("extrato: os saldos do dia conferem com os lançamentos", info["confere"] is True and info["saldos"] == {"pares": 2, "batem": 2}, info)
itens, info = fa.ler_pdf_texto(EXTRATO.replace("-100,00", "-101,00"), "conta")
confere("extrato: um lançamento lido errado é pego pelo saldo", info["confere"] is False and info["saldos"]["batem"] == 1, info)
ORDEM_INVERSA = """03/10/2026    SALDO DO DIA    698,00
03/10/2026    IOF    -2,00
03/10/2026    FATURA ITAU UNICLASS 10/2026    -500,00
02/10/2026    SALDO DO DIA    1.200,00
02/10/2026    SISPAG EXEMPLO    300,00
02/10/2026    PIX TRANSF FULANO02/10    -100,00
01/10/2026    SALDO DO DIA    1.000,00
"""
itens, info = fa.ler_pdf_texto(ORDEM_INVERSA, "conta")
confere("extrato em ordem inversa também confere", info["confere"] is True, info)
FATURA_ITAU = """Itaú  Cartão 1234.XXXX.XXXX.5678
Resumo da fatura em R$
Total desta fatura 305,50    Limite total de crédito: R$ 20.000,00
Pagamento mínimo: R$ 50,00
"""
confere("fatura Itaú é cartão", fa.detectar(FATURA_ITAU, "fatura.pdf") == ("Itaú", "cartão"), fa.detectar(FATURA_ITAU, "fatura.pdf"))
con_x = fn.conectar(Path(tempfile.mkdtemp(prefix="finance_cat_")) / "c.db")
confere("'FATURA ITAU UNICLASS' é pagamento de fatura (fora das despesas)", fn.categorizar(con_x, fn.norm("FATURA ITAU UNICLASS 10/2026"), fn._regras(con_x)) == "Pagamento de fatura")

# ---- fatura do Nubank em OFX (cartão: compra negativa, pagamento recebido positivo)
NU_OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
<OFX>
<SIGNONMSGSRSV1><SONRS><FI>
<ORG>NU PAGAMENTOS S.A.</ORG>
<FID>260</FID>
</FI></SONRS></SIGNONMSGSRSV1>
<CREDITCARDMSGSRSV1>
<CCSTMTTRNRS>
<CCSTMTRS>
<CURDEF>BRL</CURDEF>
<CCACCTFROM>
<ACCTID>abc1d234-e5f6-7890-1abc-de23fg456hi7</ACCTID>
</CCACCTFROM>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>CREDIT</TRNTYPE>
<DTPOSTED>20261005000000[-3:GMT]</DTPOSTED>
<TRNAMT>350.00</TRNAMT>
<FITID>6abc12d3-4567-89e0-12ab-c3d45efgh678</FITID>
<MEMO>Pagamento recebido</MEMO>
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20261006000000[-3:GMT]</DTPOSTED>
<TRNAMT>-120.50</TRNAMT>
<FITID>6abcde12-3a4b-5c6d-7a8b-9cde012fgh34</FITID>
<MEMO>Padaria Exemplo</MEMO>
</STMTTRN>
</BANKTRANLIST>
</CCSTMTRS>
</CCSTMTTRNRS>
</CREDITCARDMSGSRSV1>
</OFX>
""".encode()
a = fa.analisar(NU_OFX, "Nubank_2026-11-01.ofx")
confere("OFX de fatura do Nubank: banco, tipo e conta identificados", (a["banco"], a["tipo"], a["conta"]) == ("Nubank", "cartão", "Nubank cartão"), (a["banco"], a["tipo"], a["conta"]))
confere("OFX de fatura do Nubank: o sinal do arquivo é respeitado (compra negativa, pagamento positivo)", [i["valor"] for i in a["itens"]] == [35000, -12050], [i["valor"] for i in a["itens"]])
ins = fa.inspecionar(NU_OFX, "x.ofx")
confere("inspeção de OFX mantém as tags de fechamento e mascara o conteúdo", "</CODE>" in ins or "</TRNAMT>" in ins or "<MEMO>Xxxxxxxxx xxxxxxxx</MEMO>" in ins, ins[-400:])
confere("inspeção de OFX não vaza nome de loja, identificador nem valor", "Padaria" not in ins and "abc1d234" not in ins and "120" not in ins and "350" not in ins, ins)
con_nu = fn.conectar(Path(tempfile.mkdtemp(prefix="finance_nu_")) / "n.db")
r = fa.importar_arquivo(con_nu, NU_OFX, "Nubank_2026-11-01.ofx")
confere("importa o OFX do Nubank na conta detectada", r["novas"] == 2 and r["conta"] == "Nubank cartão", r)
cat = con_nu.execute("SELECT categoria FROM transacoes WHERE descricao='Pagamento recebido'").fetchone()
confere("'Pagamento recebido' na fatura não vira receita", cat and cat["categoria"] == "Pagamento de fatura", cat and cat["categoria"])
r2 = fa.importar_arquivo(con_nu, NU_OFX, "Nubank_2026-11-01.ofx")
confere("importar o mesmo OFX de novo não duplica", r2["novas"] == 0 and r2["repetidas"] == 2, r2)

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
