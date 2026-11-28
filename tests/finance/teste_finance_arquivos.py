#!/usr/bin/env python3
"""Testa financas_arquivos.py: leitura de PDF, detecção do banco, inspeção anônima, conferência de total e pasta vigiada.
Usa banco e pastas temporários; nada toca a internet. Os textos de fatura e extrato são inventados."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = RAIZ
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
    """PDF mínimo (Helvetica), uma linha de texto por linha, sem depender do reportlab (que pode faltar no venv)."""
    def esc(x):
        return x.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    cont = ("BT /F1 10 Tf 40 800 Td 14 TL\n" + "\n".join(f"({esc(l)}) '" for l in texto.splitlines()) + "\nET").encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(cont) + cont + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, pos = b"%PDF-1.4\n", []
    for k, o in enumerate(objs, 1):
        pos.append(len(out))
        out += b"%d 0 obj\n" % k + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % q for q in pos)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


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
confere("extrato: os saldos do dia conferem com os lançamentos", info["confere"] is True and info["saldos"]["pares"] == 2 and info["saldos"]["batem"] == 2, info)
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

# ---- fatura do Nubank em PDF: "dd MES", final do cartão "•••• 1234", menos tipográfico, encargos e vencimento em janeiro
NU_PDF = """Olá, Fulano.
Esta é a sua fatura de dezembro, no valor de
R$ 235,90
Data de vencimento: 10 JAN 2027
Limite total do cartão de crédito: R$ 10.000,00
RESUMO DA FATURA ATUAL
    Fatura anterior    R$ 100,00
    Pagamento recebido    −R$ 100,00
    Total de compras de todos os cartões, 12 DEZ a 12 JAN    R$ 220,00
    Outros lançamentos    R$ 15,90
    Total a pagar    R$ 235,90
    Pagamento mínimo para não entrar em atraso    R$ 30,00
TRANSAÇÕES DE 12 DEZ A 12 JAN
    Fulano de Tal    R$ 220,00
    28 DEZ    •••• 1234   Loja*Exemplo - Parcela 2/10    R$ 120,00
    05 JAN    •••• 1234   Padaria Teste    R$ 100,00
    Pagamentos e Financiamentos    -R$ 105,00
    20 DEZ    Pagamento em 20 DEZ    −R$ 100,00
    21 DEZ    Crédito de atraso    −R$ 5,00
    22 DEZ    Saldo em atraso    R$ 100,00
    23 DEZ    Multa de atraso    R$ 2,00
    23 DEZ    IOF de atraso    R$ 3,90
    23 DEZ    Juros de atraso    R$ 10,00
"""
itens, info = fa.ler_pdf_texto(NU_PDF, "cartão")
confere("Nubank PDF: lê compras, pagamentos e encargos, sem o saldo em atraso", [i["valor"] for i in itens] == [-12000, -10000, 10000, 500, -200, -390, -1000], [i["valor"] for i in itens])
confere("Nubank PDF: descrição sem o final do cartão", itens[0]["descricao"] == "Loja*Exemplo - Parcela 2/10", itens[0])
confere("Nubank PDF: compra de dezembro numa fatura de janeiro fica em 2026", itens[0]["data"] == "2026-12-28" and itens[1]["data"] == "2027-01-05", [i["data"] for i in itens[:2]])
confere("Nubank PDF: o 'Total de compras' confere mesmo com encargos na fatura", info["confere"] is True, info)
confere("Nubank PDF: detectado como cartão do Nubank", fa.detectar(NU_PDF + "\nO Nubank é uma instituição", "fatura.pdf") == ("Nubank", "cartão"), fa.detectar(NU_PDF + "\nO Nubank é uma instituição", "fatura.pdf"))
con_np = fn.conectar(Path(tempfile.mkdtemp(prefix="finance_np_")) / "n.db")
r = fn.importar_itens(con_np, itens, "PDF", "fatura.pdf", "Nubank cartão")
cats = {x["descricao"]: x["categoria"] for x in con_np.execute("SELECT descricao, categoria FROM transacoes")}
confere("Nubank PDF: pagamento e crédito de atraso não viram receita", cats["Pagamento em 20 DEZ"] == "Pagamento de fatura" and cats["Crédito de atraso"] == "Pagamento de fatura", cats)
confere("Nubank PDF: multa, IOF e juros são tarifas", cats["Multa de atraso"] == "Impostos e tarifas" and cats["IOF de atraso"] == "Impostos e tarifas", cats)

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

# ---- extrato de conta com "JUROS LIMITE DA CONTA" (lançamento real, não cabeçalho)
_txt = "Itaú extrato conta\nperíodo de visualização: 01/10/2026 até 03/10/2026\n03/10/2026   JUROS LIMITE DA CONTA   -10,00\n03/10/2026   SALDO DO DIA   -60,00\n02/10/2026   PIX ENVIADO FULANO   -50,00\n02/10/2026   SALDO DO DIA   -50,00\n01/10/2026   SALDO DO DIA   0,00\n"
_it, _inf = fa.ler_pdf_texto(_txt, "conta")
confere("juros do limite da conta entra e o saldo confere", len(_it) == 2 and _inf["confere"] is True, _inf)
_deslocado = ("Itaú extrato conta\nperíodo de visualização: 01/10/2026 até 04/10/2026\n04/10/2026   PIX A   -10,00\n04/10/2026   SALDO DO DIA   -110,00\n"
              "03/10/2026   PIX C   -47,00\n03/10/2026   SALDO DO DIA   -100,00\n03/10/2026   PIX B   -53,00\n02/10/2026   SALDO DO DIA   0,00\n01/10/2026   SALDO DO DIA   0,00\n")
_it3, _inf3 = fa.ler_pdf_texto(_deslocado, "conta")
confere("lançamento do outro lado da linha de saldo (diferenças que se anulam) é aceito", _inf3["confere"] is True and _inf3["saldos"]["explicadas"] == 2, _inf3["saldos"])
_it2, _inf2 = fa.ler_pdf_texto(_txt.replace("-60,00", "-99,00"), "conta")
confere("saldo que não bate aparece nas divergências", _inf2["confere"] is False and _inf2["saldos"]["divergencias"], _inf2["saldos"])
# ---- fatura do Mercado Pago em parcelamento (crédito com valor positivo e linha de cabeçalho só com valores)
_mp = """Mercado Pago Cartão
Total a pagar   Vence em   Limite total   Saque total
15/12/2026   R$ 10.000,00   R$ 50,00
Resumo da fatura
Total da fatura de novembro   R$ 521,09
Total   R$ 301,76
Vencimento: 15/12/2026
Movimentações na fatura
05/12   Débito para pagar sua fatura   R$ 101,94
05/12   Crédito por parcelamento da fatura   R$ 419,15
05/12   Pagamento da fatura de outubro/2026   Parcela 1 de 5   R$ 98,73
06/12   Juros de mora   R$ 1,05
06/12   Multa por atraso   R$ 4,65
06/12   Juros do rotativo   R$ 18,66
06/12   IOF do rotativo   R$ 2,25
07/12   LOJA*EXEMPLO   Parcela 02 de 10   R$ 176,42
Total   R$ 176,42
"""
_itm, _infm = fa.ler_pdf_texto(_mp, "cartão")
confere("Mercado Pago: cabeçalho só com valores e a liquidação da fatura anterior não são lançamentos", len(_itm) == 6 and not any(("10.000" in i["descricao"] or "Débito para" in i["descricao"] or "parcelamento da fatura" in i["descricao"]) for i in _itm), [i["descricao"] for i in _itm])
confere("Mercado Pago: a soma confere com o total da fatura", _infm["confere"] is True and _infm["soma"] == -30176, _infm)
_it_cr, _ = fa.ler_pdf_texto("Nubank\nVencimento: 10/12/2026\n05/12   Crédito de teste   R$ 10,00\n06/12   Loja   R$ 30,00\nTotal da fatura   R$ 20,00\n", "cartão")
confere("cartão: lançamento que começa com Crédito, com valor positivo, é crédito", any(i["valor"] > 0 for i in _it_cr) and sum(i["valor"] for i in _it_cr) == -2000, _it_cr)

# ---- extrato de conta do Mercado Pago (data com traços, número da operação e saldo na mesma linha)
_mpc = """EXTRATO DE CONTA
Mercado Pago
Entradas: R$ 150,00
Saldo inicial: R$ 100,00   Saldo final: R$ 204,10
Saídas: R$ 45,90
DETALHE DOS MOVIMENTOS
03-11-2026   Rendimentos   1234567890123   R$ 4,00   R$ 104,00
04-11-2026   Transferência Pix enviada Fulano   1234567890124   R$ -45,90   R$ 58,10
05-11-2026   Transferência Pix recebida Beltrano   1234567890125   R$ 146,00   R$ 204,10
Mercado Pago Instituição de Pagamento
"""
_itc, _infc = fa.ler_pdf_texto(_mpc, "conta")
confere("Mercado Pago conta: lê data com traços, valor e identificador da operação", len(_itc) == 3 and _itc[1]["valor"] == -4590 and _itc[1]["fitid"] == "1234567890124" and "1234567890124" not in _itc[1]["descricao"] and _itc[0]["data"] == "2026-11-03", _itc)
confere("Mercado Pago conta: a sequência de saldos confere", _infc["confere"] is True, _infc["saldos"])
_itc2, _infc2 = fa.ler_pdf_texto(_mpc.replace("R$ -45,90", "R$ -44,90"), "conta")
confere("Mercado Pago conta: valor que não fecha com os saldos barra a importação", _infc2["confere"] is not True, _infc2)

# ---- pasta vigiada
con.execute("UPDATE importacoes SET hash_arquivo=NULL")  # o "forçar" acima já gravou o mesmo PDF; aqui começa do zero
con.commit()
base = tmp / "dados"
entrada = fa.preparar_pasta(base)
confere("cria entrada, importados e revisar", all((entrada / s).is_dir() for s in ("imported", "review")))
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
confere("o arquivo importado vai para imported/", (entrada / "imported" / "extrato itau novembro.ofx").is_file() and not (entrada / "extrato itau novembro.ofx").exists())
confere("CSV sem pistas vai para revisar com o motivo", (not nomes["misterio.csv"]["ok"]) and (entrada / "review" / "misterio.csv.motivo.txt").is_file(), nomes.get("misterio.csv"))
if pdf_ok:
    confere("PDF que não confere vai para revisar", not nomes["fatura-itau-ruim.pdf"]["ok"] and (entrada / "review" / "fatura-itau-ruim.pdf").is_file(), nomes.get("fatura-itau-ruim.pdf"))
confere("arquivo oculto e extensão desconhecida ficam quietos", ".oculto.csv" not in nomes and "nota.docx" not in nomes and (entrada / ".oculto.csv").exists())
confere("a lista de pendentes traz o motivo", any(n == "misterio.csv" and m for n, m in fa.pendentes(base)), fa.pendentes(base))
# duplicados e limpeza de motivos
(entrada / "copia do extrato.ofx").write_bytes(ofx)
(entrada / "misterio.csv").write_bytes(b"coluna1;coluna2\n1;2\n")
os.utime(entrada / "copia do extrato.ofx", (time.time() - 60,) * 2)
os.utime(entrada / "misterio.csv", (time.time() - 60,) * 2)
res2 = fa.processar_entrada(con, base)
n2 = {r["arquivo"]: r for r in res2}
confere("cópia idêntica de arquivo já importado não é importada e é apagada", n2["copia do extrato.ofx"].get("duplicado") and not (entrada / "copia do extrato.ofx").exists(), n2)
confere("cópia de arquivo que já espera revisão é apagada e o original fica", n2["misterio.csv"].get("duplicado") and not (entrada / "misterio.csv").exists() and (entrada / "review" / "misterio.csv").is_file(), n2)
(entrada / "review" / "misterio.csv").unlink()
fa.processar_entrada(con, base)
confere("motivo órfão em review/ é apagado", not (entrada / "review" / "misterio.csv.motivo.txt").exists())
ofx2 = ofx.replace(b"OFXHEADER:100", b"OFXHEADER:100 ")
(entrada / "itau mesmo conteudo outro byte.ofx").write_bytes(ofx2)
os.utime(entrada / "itau mesmo conteudo outro byte.ofx", (time.time() - 60,) * 2)
n3 = {r["arquivo"]: r for r in fa.processar_entrada(con, base)}
confere("arquivo com bytes diferentes mas só lançamentos repetidos não importa e é apagado", n3["itau mesmo conteudo outro byte.ofx"].get("duplicado") and not (entrada / "itau mesmo conteudo outro byte.ofx").exists(), n3)
confere("duplicado não deixa registro vazio no histórico", con.execute("SELECT COUNT(*) FROM importacoes WHERE novas=0 AND arquivo LIKE 'itau mesmo%'").fetchone()[0] == 0)
(entrada / "review" / "x.csv").write_bytes(b"a")
(entrada / "review" / "x.csv.motivo.txt").write_text("m")
fa.concluir_revisao(base, entrada / "review" / "x.csv")
confere("revisado: arquivo vai para imported/ e o motivo some", (entrada / "imported" / "x.csv").is_file() and not (entrada / "review" / "x.csv.motivo.txt").exists())
(entrada / "review" / "volta.csv").write_bytes(b"x;y\n1;2\n")
(entrada / "review" / "volta.csv.motivo.txt").write_text("m")
(entrada / "volta.csv").write_bytes(b"outro")
mv = fa.devolver_para_entrada(base)
confere("retry não sobrescreve arquivo de mesmo nome na entrada", [m[:2] for m in mv if m[0] == "volta.csv"] == [("volta.csv", False)] and (entrada / "review" / "volta.csv").exists() and (entrada / "review" / "volta.csv.motivo.txt").exists(), mv)
(entrada / "volta.csv").unlink()
mv = fa.devolver_para_entrada(base)
confere("retry devolve para a entrada e some com o motivo", ("volta.csv", True, "") in mv and (entrada / "volta.csv").exists() and not (entrada / "review" / "volta.csv.motivo.txt").exists(), mv)
(entrada / "volta.csv").unlink()
if (entrada / "fatura-itau-ruim.pdf").exists():
    (entrada / "fatura-itau-ruim.pdf").rename(entrada / "review" / "fatura-itau-ruim.pdf")
(entrada / "recente.ofx").write_bytes(ofx.replace(b"A1", b"A2"))
confere("arquivo recém-copiado espera a próxima rodada", fa.processar_entrada(con, base) == [] and (entrada / "recente.ofx").exists())

# ---- linha de comando
env = dict(os.environ, STUDIO_FINANCE_DIR=str(tmp / "cli"))
(tmp / "f.pdf").write_bytes(pdf) if pdf_ok else None
if pdf_ok:
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--inspecionar", str(tmp / "f.pdf")], capture_output=True, text=True, env=env, timeout=60)
    confere("--inspecionar imprime só a estrutura", p.returncode == 0 and "Estrutura anônima (PDF)" in p.stdout and "Exemplo" not in p.stdout, p.stdout[:300] + p.stderr[:200])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--explicar", str(tmp / "f.pdf")], capture_output=True, text=True, env=env, timeout=60)
    confere("--explicar mostra a classificação anônima", p.returncode == 0 and "Diagnóstico anônimo" in p.stdout and "LANÇAMENTO" in p.stdout, p.stdout[:300] + p.stderr[:200])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--prever", str(tmp / "f.pdf")], capture_output=True, text=True, env=env, timeout=60)
    confere("--prever mostra o resumo e não grava", p.returncode == 0 and "bate" in p.stdout and not (tmp / "cli" / "financas.db").exists(), p.stdout[:300] + p.stderr[:200])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--importar", str(tmp / "f.pdf")], capture_output=True, text=True, env=env, timeout=60)
    confere("--importar grava na conta detectada", p.returncode == 0 and "Nubank cartão" in p.stdout and "4 novos" in p.stdout, p.stdout[:300] + p.stderr[:200])
p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--pasta"], capture_output=True, text=True, env=env, timeout=60)
confere("--pasta mostra o caminho da entrada", p.returncode == 0 and "entrada" in p.stdout, p.stdout + p.stderr)
p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--inspecionar", str(tmp / "nao_existe.pdf")], capture_output=True, text=True, env=env, timeout=60)
confere("arquivo que não existe dá mensagem clara", p.returncode != 0 and "Não achei o arquivo" in p.stderr, p.stderr)

# espaços soltos no meio de datas e valores (pypdf)
import financas_arquivos as _fa
quebrado = """Fatura do cartão Itaú
Vencimento: 20/11/2026   Total desta fatura   305,50
05/1 1   MERCADO EXEMPLO   50 ,00   06/ 11   PADARIA TESTE   30, 50
08 /11   LOJA GRANDE   2 25,00
Limite total de crédito   R$ 20.0 00,00
"""
_it, _inf = _fa.ler_pdf_texto(quebrado, "cartão")
confere("espaços soltos em datas e valores são reparados", len(_it) == 3 and abs(_inf["gastos"] - 30550) == 0 and _inf["confere"] is True, (_it, _inf))
confere("parcela 03/10 e colunas não são coladas", _fa._reparar_espacos("03/10 120,00") == "03/10 120,00" and _fa._reparar_espacos("x   99,99   99/99") == "x   99,99   99/99")

# fatura com seção final de parcelas das próximas faturas
prox = """Fatura do cartão Itaú
Vencimento: 20/11/2026   Fechamento: 10/11/2026
Total dos lançamentos atuais   R$ 305,50
05/10   MERCADO EXEMPLO   50,00
06/10   PADARIA TESTE   55,50
07/10   LOJA GRANDE   200,00
Total dos lançamentos no cartão   305,50
Compras parceladas - próximas faturas
08/09   MOVEIS TESTE 03/10   120,00
09/09   CELULAR TESTE 04/12   90,00
Total para próximas faturas   210,00
"""
_it2, _inf2 = _fa.ler_pdf_texto(prox, "cartão")
confere("seção de próximas faturas é descartada quando o total só bate sem ela", len(_it2) == 3 and _inf2["confere"] is True and _inf2["descartadas"] == 2, (_it2, _inf2))

# porcentagem ao lado de compra não vira valor; IOF internacional sem data entra
pct = """Fatura do cartão Itaú
Vencimento: 20/11/2026   Fechamento: 10/11/2026
05/10   MERCADO EXEMPLO   50,00   Juros do rotativo   9,99%
06/10   COMPRA EXTERIOR   100,00
Total de IOF em R$   3,50
Total dos lançamentos atuais   R$ 153,50
Compras parceladas - próximas faturas
08/09   MOVEIS TESTE 03/10   120,00
Total para próximas faturas   120,00
"""
_it3, _inf3 = _fa.ler_pdf_texto(pct, "cartão")
confere("porcentagem não é valor e IOF sem data entra na soma", [i["valor"] for i in _it3[:3]] == [-5000, -10000, -350] and _inf3["confere"] is True and _inf3["descartadas"] == 1, (_it3, _inf3))

# ---- boleto em PDF solto na pasta de entrada vira conta a pagar
if pdf_ok:
    import financas_boletos as _fb
    _bol = "Recibo do Pagador\nBeneficiário\nPADARIA DOIS IRMAOS LTDA   CNPJ 12.345.678/0001-90\nValor do documento 450,90\n34191.23454 67890.123457 67890.123457 6 16560000045090\n"
    _base = tmp / "boleto"
    _ent = fa.preparar_pasta(_base)
    (_ent / "boleto padaria.pdf").write_bytes(pdf_de(_bol))
    os.utime(_ent / "boleto padaria.pdf", (time.time() - 60, time.time() - 60))
    _con = fn.conectar(tmp / "boleto.db")
    _res = fa.processar_entrada(_con, _base)
    confere("PDF de boleto na pasta vira conta a pagar e vai para importados", len(_res) == 1 and _res[0].get("boleto") and _res[0]["novas"] == 1 and (_ent / "imported" / "boleto padaria.pdf").exists(), _res)
    _l = _fb.listar(_con)
    confere("boleto da pasta guarda valor e beneficiário", len(_l) == 1 and _l[0]["valor"] == 45090 and _l[0]["beneficiario"] == "PADARIA DOIS IRMAOS LTDA", _l)
    confere("boleto não cria lançamento no extrato", _con.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 0)
    _fb.adicionar_pessoa(_con, "Maria Souza Lima")
    _outra = "34191234546789012345767890123457616560000099990"
    try:
        _ob = _fb.interpretar(_outra)
    except fn.ErroFinance:
        _ob = None
    _env = dict(os.environ, STUDIO_FINANCE_DIR=str(tmp / "clib"))
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--boleto", "34191234546789012345767890123457616560000045090"], capture_output=True, text=True, env=_env, timeout=60)
    confere("--boleto com a linha registra e avisa que não paga", p.returncode == 0 and "Registrado" in p.stdout and "R$ 450,90" in p.stdout and "não paga nada" in p.stdout, p.stdout[:300] + p.stderr[:200])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--boleto", "34191234546789012345767890123457616560000045090"], capture_output=True, text=True, env=_env, timeout=60)
    confere("--boleto repetido não duplica", "Já estava registrado" in p.stdout, p.stdout[:300])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--boleto", "34191234546789012345767890123457616560000045091"], capture_output=True, text=True, env=_env, timeout=60)
    confere("--boleto com número errado recusa", p.returncode != 0 and "não confere" in (p.stdout + p.stderr), p.stdout[:200] + p.stderr[:300])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--boletos"], capture_output=True, text=True, env=_env, timeout=60)
    confere("--boletos lista", p.returncode == 0 and "R$ 450,90" in p.stdout, p.stdout[:300])
    pix_cli = "00020126400014br.gov.bcb.pix0118fulano@exemplo.com5204000053039865406123.455802BR5911MARIA SILVA6009SAO PAULO62070503***6304757B"
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--boleto", pix_cli, "--pessoa", "Ana Souza"], capture_output=True, text=True, env=_env, timeout=60)
    confere("--boleto com --pessoa cadastra a pessoa e mostra de quem é", p.returncode == 0 and "(de Ana Souza)" in p.stdout and "R$ 123,45" in p.stdout, p.stdout[:300] + p.stderr[:200])
    p = subprocess.run([sys.executable, str(AQUI / "financas_cli.py"), "--boletos"], capture_output=True, text=True, env=_env, timeout=60)
    confere("--boletos mostra o total por pessoa", "Total em aberto por pessoa" in p.stdout and "Ana Souza R$ 123,45" in p.stdout, p.stdout[:400])

print()
print("FALHAS: " + str(falhas))
sys.exit(1 if falhas else 0)
