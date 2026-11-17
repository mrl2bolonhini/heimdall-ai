#!/usr/bin/env python3
"""Testa financas_email.py: boletos e Pix em e-mails (corpo e PDF anexo), autenticação do remetente, e-mails repetidos e ruído. Sem rede: as mensagens são montadas aqui."""
import io
from datetime import date
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import financas_boletos as fb  # noqa: E402
import financas_email as fe  # noqa: E402
import financas_nucleo as fn  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:500])


LB = "34191234546789012345767890123457616560000045090"
BONITA = f"{LB[0:5]}.{LB[5:10]} {LB[10:15]}.{LB[15:21]} {LB[21:26]}.{LB[26:32]} {LB[32]} {LB[33:]}"
PIX = "00020126400014br.gov.bcb.pix0118fulano@exemplo.com5204000053039865406123.455802BR5911MARIA SILVA6009SAO PAULO62070503***6304757B"


def msg(de, assunto, corpo, mid, auth="dmarc=pass dkim=pass spf=pass", pdf=None, html=False):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = de, "eu@exemplo.com", assunto, mid
    if auth is not None:
        m["Authentication-Results"] = f"mx.google.com; {auth}; header.from=exemplo.com"
    if html:
        m.set_content("veja o html")
        m.add_alternative(corpo, subtype="html")
    else:
        m.set_content(corpo)
    if pdf:
        m.add_attachment(pdf, maintype="application", subtype="pdf", filename="boleto.pdf")
    return m


def pdf_de(texto):
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


con = fn.conectar(Path(tempfile.mkdtemp()) / "e.db")
fb.adicionar_pessoa(con, "Maria Souza Lima")
estado = {}
msgs = [
    msg("Escola Alegria <cobranca@escola.com.br>", "Boleto de dezembro", f"Olá! Segue a linha digitável:\n{BONITA}\nObrigado", "<a1@x>"),
    msg("Golpista <x@falso.biz>", "Boleto urgente", f"Pague já: {BONITA[:-1]}1 ou use o Pix:\n{PIX}", "<a2@x>", auth="dmarc=fail dkim=none spf=fail"),
    msg("Loja <vendas@loja.com>", "Seu pedido foi enviado", "Rastreio 12345678901234567890123456789012345678901234567 e nada de boleto.", "<a3@x>"),
    msg("Newsletter <n@jornal.com>", "Boleto do jornal", "<p>Linha digitável:</p><p>" + BONITA.replace(" ", "<br>", 1) + "</p>", "<a4@x>", html=True),
]
res = fe.processar(con, msgs, estado, "2026-11-17 10:00:00")
lst = fb.listar(con)
confere("e-mail autenticado: boleto registrado com origem e sem aviso", any(b["linha"] == LB and b["aviso"] is None and (b["arquivo"] or "").startswith("e-mail de escola.com.br") for b in lst), [(b["linha"][:8], b["aviso"], b["arquivo"]) for b in lst])
confere("o mesmo boleto vindo de novo (HTML) não duplica", sum(1 for b in lst if b["linha"] == LB) == 1 and any(r["repetidos"] == 1 for r in res), res)
confere("linha com dígito trocado é ignorada, mas o Pix válido do mesmo e-mail entra", not any(b["linha"] == LB[:-1] + "1" for b in lst) and any(b["tipo"] == "pix" for b in lst), [b["linha"][:12] for b in lst])
pix = next(b for b in lst if b["tipo"] == "pix")
confere("remetente que não passa na autenticação entra com aviso de golpe", pix["aviso"] and "boleto falso" in pix["aviso"], pix["aviso"])
confere("e-mail sem boleto válido não registra nada", len(lst) == 2 and not any("loja.com" in (b["arquivo"] or "") for b in lst))
confere("e-mails lidos ficam no estado e não são lidos de novo", len(estado["ids"]) == 4 and fe.processar(con, msgs, estado) == [])

# PDF anexado, com pagador reconhecido
try:
    pdf = pdf_de(f"Beneficiário\nPADARIA DOIS IRMAOS LTDA\nPagador\nMARIA SOUZA LIMA\n{BONITA.replace(LB[-10:], '0000099990')}\n")
except Exception:  # noqa: BLE001
    pdf = None
if pdf:
    outra = "34191234546789012345767890123457616560000099990"
    try:
        fb.interpretar(outra)
        valido = True
    except fn.ErroFinance:
        valido = False
    corpo_pdf = f"Beneficiário\nPADARIA DOIS IRMAOS LTDA\nPagador\nMARIA SOUZA LIMA\n{BONITA}\n"
    pdf = pdf_de(corpo_pdf)
    con2 = fn.conectar(Path(tempfile.mkdtemp()) / "e2.db")
    fb.adicionar_pessoa(con2, "Maria Souza Lima")
    r2 = fe.processar(con2, [msg("Padaria <p@padaria.com>", "Boleto", "Segue em anexo.", "<b1@x>", pdf=pdf)], {})
    b = fb.listar(con2)
    confere("PDF anexado: registra, acha o beneficiário e a pessoa pelo Pagador", len(b) == 1 and b[0]["beneficiario"] == "PADARIA DOIS IRMAOS LTDA" and b[0]["dono"] == "Maria Souza Lima", [(x["beneficiario"], x["dono"]) for x in b])

# o módulo nunca abre links
fonte = (AQUI / "financas_email.py").read_text(encoding="utf-8")
confere("o leitor de e-mail não abre links nem usa requisições web", "urllib" not in fonte and "requests" not in fonte and "http.client" not in fonte)
confere("o IMAP é aberto em modo somente leitura", 'imap.select("INBOX", readonly=True)' in fonte and "BODY.PEEK" in fonte)
confere("sem senha no .env, não há credenciais", fe.credenciais(Path(tempfile.mkdtemp()) / "nao-existe.env") == {})
d = Path(tempfile.mkdtemp())
(d / ".env").write_text("HEIMDALL_EMAIL_USUARIO=a@b.com\nHEIMDALL_EMAIL_SENHA_APP='abcd efgh'\nOUTRA=segredo\n", encoding="utf-8")
c = fe.credenciais(d / ".env")
confere("credenciais: só as duas chaves do e-mail, lidas do .env", set(c) == {"HEIMDALL_EMAIL_USUARIO", "HEIMDALL_EMAIL_SENHA_APP"} and c["HEIMDALL_EMAIL_SENHA_APP"] == "abcd efgh")
est = d / "estado.json"
r3 = fe.executar(fn.conectar(d / "x.db"), c, est, lambda cfg: [msgs[0]])
confere("executar guarda o estado em arquivo e devolve o resumo", r3 and est.exists() and "<a1@x>" in est.read_text(encoding="utf-8"))

# --- boletos já programados ou pagos ---
confere("sinal: débito automático no e-mail", "débito automático" in fb.sinal_pagamento("Sua fatura será debitada automaticamente na data de vencimento."), fb.sinal_pagamento("Sua fatura será debitada automaticamente"))
confere("sinal: cobrança no cartão", "cartão" in fb.sinal_pagamento("O valor foi cobrado no seu cartão de crédito final 1234."))
confere("sinal: já pago", "já foi feito" in fb.sinal_pagamento("Pagamento confirmado. Obrigado pelo pagamento!"))
confere("sinal: negação não conta (cadastre o débito automático)", fb.sinal_pagamento("Cadastre o débito automático e não esqueça de pagar o boleto.") == "")
confere("sinal: 'não tem débito automático' não conta", fb.sinal_pagamento("Você não tem débito automático cadastrado. Pague o boleto abaixo.") == "")
confere("sinal: e-mail comum sem frases não dispara", fb.sinal_pagamento("Segue o boleto de dezembro. Vencimento dia 10.") == "")
c2 = fn.conectar(Path(tempfile.mkdtemp()) / "p.db")
res2 = fe.processar(c2, [msg("Escola <c@escola.com.br>", "Mensalidade", f"Pagamento por débito automático em conta.\n{BONITA}", "<p1@x>")], {}, "2026-11-17 10:00:00")
l2 = fb.listar(c2, incluir_pagos=True)
confere("e-mail autêntico com débito automático: boleto entra como programado, fora das contas a pagar", len(l2) == 1 and l2[0]["estado"] == "programado" and "débito automático" in l2[0]["motivo"] and fb.listar(c2) == [], l2)
res3 = fe.processar(fn.conectar(Path(tempfile.mkdtemp()) / "q.db"), [msg("Golpe <x@falso.biz>", "Mensalidade", f"Pagamento por débito automático.\n{BONITA}", "<p2@x>", auth="dmarc=fail dkim=none spf=fail")], {}, "2026-11-17 10:00:00")
confere("remetente falso dizendo 'débito automático' não esconde o boleto", res3[0]["motivo"] == "")
bid = l2[0]["id"]
fb.definir_situacao(c2, bid, False)
fb.conciliar(c2)
confere("É para pagar mesmo: volta a aberto e não é mais mexido", fb.listar(c2)[0]["id"] == bid and fb.listar(c2)[0]["situacao"] == "aberto")
# histórico
c3 = fn.conectar(Path(tempfile.mkdtemp()) / "h.db")
fb.registrar(c3, fb.interpretar(LB), "Escola Alegria", "", "2026-11-17 10:00:00")
venc = fb.listar(c3, incluir_pagos=True)[0]["vencimento"]
fn.importar_itens(c3, [{"data": venc, "valor": -45090, "descricao": "PAGTO BOLETO ESCOLA ALEGRIA"}], "csv", "x.csv", "Itaú conta")
fb.conciliar(c3)
b3 = fb.listar(c3, incluir_pagos=True)[0]
confere("lançamento do mesmo valor no histórico marca o boleto como pago", b3["estado"] == "pago" and "histórico" in b3["motivo"], b3)
c4 = fn.conectar(Path(tempfile.mkdtemp()) / "r.db")
fb.registrar(c4, fb.interpretar(LB), "Escola Alegria", "", "2026-11-17 10:00:00")
v4 = fb.listar(c4, incluir_pagos=True)[0]["vencimento"]
y, m, _ = (int(x) for x in v4.split("-"))
itens = []
for k in (1, 2, 3):
    mm = m - k
    yy = y + (mm - 1) // 12
    mm = (mm - 1) % 12 + 1
    itens.append({"data": f"{yy}-{mm:02d}-10", "valor": -45000, "descricao": "ESCOLA ALEGRIA MENSALIDADE"})
fn.importar_itens(c4, itens, "csv", "y.csv", "Itaú conta")
fb.conciliar(c4, date.fromisoformat(v4))
b4 = fb.listar(c4, incluir_pagos=True)[0]
confere("conta recorrente de mesmo nome e valor parecido vira provável débito automático", b4["estado"] == "programado" and "Provável" in b4["motivo"], b4)

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
