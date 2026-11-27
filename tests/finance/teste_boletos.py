#!/usr/bin/env python3
"""Testa financas_boletos.py: linha digitável bancária (47) e de convênio (48), dígitos verificadores, vencimento, PDF e banco local.
As linhas são montadas aqui com contas independentes do leitor e são inventadas."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import tempfile
from datetime import date
from pathlib import Path

AQUI = RAIZ
sys.path.insert(0, str(AQUI))
import financas_boletos as fb  # noqa: E402
import financas_nucleo as fn  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:400])


def dv10(s):
    t = 0
    for i, c in enumerate(reversed(s)):
        p = int(c) * (2 if i % 2 == 0 else 1)
        t += p - 9 if p > 9 else p
    return str((10 - t % 10) % 10)


def dv11(s, convenio=False):
    t = sum(int(c) * (2 + i % 8) for i, c in enumerate(reversed(s)))
    if convenio:
        r = t % 11
        return "0" if r in (0, 1) else str(11 - r)
    d = 11 - t % 11
    return "1" if d in (0, 10, 11) else str(d)


def linha_bancaria(banco, fator, valor, livre):
    sem = banco + "9" + f"{fator:04d}" + f"{valor:010d}" + livre
    dg = dv11(sem)
    c1 = banco + "9" + livre[:5]
    c2 = livre[5:15]
    c3 = livre[15:25]
    return c1 + dv10(c1) + c2 + dv10(c2) + c3 + dv10(c3) + dg + f"{fator:04d}" + f"{valor:010d}"


def linha_convenio(ident, segmento, valor11, livre):
    corpo = "8" + segmento + ident + valor11 + livre  # 43 dígitos sem o DV geral
    assert len(corpo) == 43, len(corpo)
    calc = (lambda s: dv10(s)) if ident in "67" else (lambda s: dv11(s, True))
    dg = calc(corpo)
    barras = corpo[:3] + dg + corpo[3:]
    return "".join(barras[i:i + 11] + calc(barras[i:i + 11]) for i in range(0, 44, 11))


# --- bancário -----------------------------------------------------------------------------
hoje = date(2026, 11, 17)
fator = 1000 + (date(2026, 11, 30) - date(2025, 2, 22)).days
L = linha_bancaria("341", fator, 123456, "1234567890123456789012345")
r = fb.interpretar(L, hoje)
confere("bancário: valor, vencimento e banco", r["valor"] == 123456 and r["vencimento"] == "2026-11-30" and r["banco"] == "Itaú", r)
bonita = f"{L[0:5]}.{L[5:10]} {L[10:15]}.{L[15:21]} {L[21:26]}.{L[26:32]} {L[32]} {L[33:]}"
confere("bancário: aceita pontos e espaços", fb.interpretar(bonita, hoje)["linha"] == L)
for pos, rotulo in ((3, "campo 1"), (14, "campo 2"), (25, "campo 3"), (40, "dígito geral/valor")):
    errada = L[:pos] + str((int(L[pos]) + 1) % 10) + L[pos + 1:]
    try:
        fb.interpretar(errada, hoje)
        confere(f"bancário: número trocado ({rotulo}) é recusado", False)
    except fn.ErroFinance:
        confere(f"bancário: número trocado ({rotulo}) é recusado", True)
try:
    fb.interpretar(L[:-1], hoje)
    confere("bancário: faltando dígito é recusado", False)
except fn.ErroFinance as ex:
    confere("bancário: faltando dígito é recusado com a contagem", "46 dígitos" in str(ex), ex)
antigo = linha_bancaria("001", 5000, 0, "0000000000000000000000001")
a = fb.interpretar(antigo, date(2011, 6, 1))
confere("bancário: fator antigo dá data de 2011 e valor zero vira em aberto", a["vencimento"] == (date(1997, 10, 7).fromordinal(date(1997, 10, 7).toordinal() + 5000)).isoformat() and a["valor"] is None, a)
sem = fb.interpretar(linha_bancaria("237", 0, 5000, "1111111111111111111111111"), hoje)
confere("bancário: fator zero é sem vencimento", sem["vencimento"] is None and sem["valor"] == 5000 and sem["banco"] == "Bradesco")

# --- convênio -----------------------------------------------------------------------------
C = linha_convenio("6", "3", "00000012345", "00000000" + "20261205" + "1234567" + "000000")
cr = fb.interpretar(C, hoje)
confere("convênio mod10: valor, segmento e vencimento no código", cr["valor"] == 12345 and cr["vencimento"] == "2026-12-05" and cr["segmento"] == "energia elétrica e gás" and cr["tipo"] == "consumo ou tributo", cr)
C8 = linha_convenio("8", "2", "00000009990", "11111111" + "2222222" + "3333333" + "4444444")
c8 = fb.interpretar(C8, hoje)
confere("convênio mod11: valor e segmento", c8["valor"] == 9990 and c8["segmento"] == "saneamento", c8)
try:
    fb.interpretar(C8[:20] + str((int(C8[20]) + 1) % 10) + C8[21:], hoje)
    confere("convênio: número trocado é recusado", False)
except fn.ErroFinance:
    confere("convênio: número trocado é recusado", True)

# --- Pix copia e cola ---------------------------------------------------------------------
def _t(i, v):
    return f"{i}{len(v):02d}{v}"


_corpo = _t("00", "01") + _t("26", _t("00", "br.gov.bcb.pix") + _t("01", "fulano@exemplo.com")) + _t("52", "0000") + _t("53", "986") + _t("54", "123.45") + _t("58", "BR") + _t("59", "MARIA SILVA") + _t("60", "SAO PAULO") + _t("62", _t("05", "***")) + "6304"
def _crc(s):
    c = 0xFFFF
    for b in s.encode():
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return f"{c:04X}"


PIX = _corpo + _crc(_corpo)
px = fb.interpretar(PIX, hoje)
confere("pix: valor, quem recebe e cidade", px["tipo"] == "pix" and px["valor"] == 12345 and px["beneficiario"] == "MARIA SILVA" and px["cidade"] == "SAO PAULO", px)
confere("pix: aceita quebra de linha no fim e acha dentro de texto", fb.interpretar(PIX + "\n", hoje)["linha"] == PIX and len(fb.achar_linhas("Pague:\n" + PIX + "\nobrigado", hoje)) == 1)
for ruim, rot in ((PIX[:-1] + ("0" if PIX[-1] != "0" else "1"), "CRC errado"), (PIX[:60], "cortado"), (PIX.replace("123.45", "123.46"), "valor adulterado")):
    try:
        fb.interpretar(ruim, hoje)
        confere(f"pix: {rot} é recusado", False)
    except fn.ErroFinance:
        confere(f"pix: {rot} é recusado", True)
_c = fn.conectar(Path(tempfile.mkdtemp()) / "pix.db")
_i, _n = fb.registrar(_c, px)
confere("pix: registra com o nome de quem recebe e lista como sem vencimento", _n and fb.listar(_c, hoje)[0]["beneficiario"] == "MARIA SILVA" and fb.listar(_c, hoje)[0]["estado"] == "sem vencimento")
confere("pix: frase em português simples", fb.frase(fb.listar(_c, hoje)[0]) == "MARIA SILVA: R$ 123,45, sem vencimento no código", fb.frase(fb.listar(_c, hoje)[0]))

# --- pessoas -------------------------------------------------------------------------------
_p = fn.conectar(Path(tempfile.mkdtemp()) / "pessoas.db")
fb.adicionar_pessoa(_p, "Maria Souza Lima")
fb.adicionar_pessoa(_p, "Ana Souza Lima")
for ruim in ("", "A", "123.456.789-09"):
    try:
        fb.adicionar_pessoa(_p, ruim)
        confere(f"pessoa inválida recusada: {ruim!r}", False)
    except fn.ErroFinance:
        confere(f"pessoa inválida recusada: {ruim!r}", True)
_txt = "Beneficiário\nESCOLA ALEGRIA\nPagador\nMARIA SOUZA LIMA   CPF xxx\nVencimento 10/12/2026\n"
confere("PDF: acha a pessoa pelo nome no campo Pagador", fb.dono_do_texto(_txt, fb.pessoas(_p)) == "Maria Souza Lima")
confere("PDF: dois nomes parecidos não geram palpite", fb.dono_do_texto("Pagador\nSOUZA LIMA", fb.pessoas(_p)) == "" and fb.dono_do_texto("sem pagador", fb.pessoas(_p)) == "")
_i, _ = fb.registrar(_p, r, "PADARIA", "", None, "Maria Souza Lima")
confere("boleto guarda a pessoa e a frase mostra de quem é", fb.listar(_p, hoje)[0]["dono"] == "Maria Souza Lima" and "(de Maria Souza Lima)" in fb.frase(fb.listar(_p, hoje)[0]))
try:
    fb.definir_dono(_p, _i, "Fulana Desconhecida")
    confere("mudar para pessoa não cadastrada é recusado", False)
except fn.ErroFinance:
    confere("mudar para pessoa não cadastrada é recusado", True)
fb.definir_dono(_p, _i, "Ana Souza Lima")
confere("mudar a pessoa do boleto", fb.listar(_p, hoje)[0]["dono"] == "Ana Souza Lima")
fb.remover_pessoa(_p, "Ana Souza Lima")
confere("remover pessoa deixa o boleto sem pessoa", fb.listar(_p, hoje)[0]["dono"] is None)

# --- Pix dinâmico (sem rede: o servidor é simulado) ----------------------------------------
import base64  # noqa: E402
import json  # noqa: E402

_corpo_d = _t("00", "01") + _t("01", "12") + _t("26", _t("00", "br.gov.bcb.pix") + _t("25", "pix.exemplo.com.br/qr/v2/abc123")) + _t("52", "0000") + _t("53", "986") + _t("58", "BR") + _t("59", "LOJA DO ZE") + _t("60", "SAO PAULO") + _t("62", _t("05", "***")) + "6304"
PIXD = _corpo_d + _crc(_corpo_d)
pd = fb.interpretar(PIXD, hoje)
confere("pix dinâmico: lê o endereço e não tem valor no código", pd["url"] == "pix.exemplo.com.br/qr/v2/abc123" and pd["valor"] is None and pd["beneficiario"] == "LOJA DO ZE", pd)
confere("pix estático não tem endereço e não consulta nada", fb.interpretar(PIX, hoje)["url"] == "" and fb.completar_pix(fb.interpretar(PIX, hoje)) == fb.interpretar(PIX, hoje))
for ruim in ("http://pix.exemplo.com.br/x", "https://127.0.0.1/x", "https://10.0.0.5/x", "https://user:senha@pix.exemplo.com.br/x", "https://pix.exemplo.com.br:8443/x", "localhost/x", "https://[::1]/x"):
    try:
        fb._url_segura(ruim)
        confere(f"pix dinâmico: endereço recusado {ruim}", False)
    except fn.ErroFinance:
        confere(f"pix dinâmico: endereço recusado {ruim}", True)
_payload = base64.urlsafe_b64encode(json.dumps({"calendario": {"dataDeVencimento": "2026-12-20"}, "valor": {"original": "89.90"}, "recebedor": {"nome": "LOJA DO ZE LTDA"}}).encode()).decode().rstrip("=")
_jws = "eyJhbGciOiJSUzI1NiJ9." + _payload + ".assinatura"
_orig = fb._url_segura
fb._url_segura = lambda u: ("pix.exemplo.com.br", "203.0.113.10", "/qr/v2/abc123")
pc = fb.completar_pix(pd, baixar=lambda h, i, c: _jws.encode())
confere("pix dinâmico: completa valor, vencimento e recebedor e avisa que a assinatura não foi verificada", pc["valor"] == 8990 and pc["vencimento"] == "2026-12-20" and pc["beneficiario"] == "LOJA DO ZE LTDA" and "sem verificar a assinatura" in pc["aviso"], pc)
pj = fb.completar_pix(pd, baixar=lambda h, i, c: json.dumps({"valor": {"original": "10.00"}}).encode())
confere("pix dinâmico: JSON direto também é aceito", pj["valor"] == 1000)
pe = fb.completar_pix(pd, baixar=lambda h, i, c: b"lixo")
confere("pix dinâmico: resposta que não entendo deixa os dados como estavam, com aviso", pe["valor"] is None and "Confira no app" in pe["aviso"], pe)


def _cai(h, i, c):
    raise OSError("sem rede")


confere("pix dinâmico: servidor fora do ar não derruba", "não respondeu" in fb.completar_pix(pd, baixar=_cai)["aviso"])
fb._url_segura = _orig
confere("pix dinâmico: sem rede, o endereço não resolve e o aviso explica", "Confira no app" in fb.completar_pix(pd, baixar=_cai).get("aviso", ""))
_cd = fn.conectar(Path(tempfile.mkdtemp()) / "pd.db")
fb.registrar(_cd, pc)
_l = fb.listar(_cd, hoje)[0]
confere("pix dinâmico registrado guarda valor, vencimento e o aviso", _l["valor"] == 8990 and _l["vencimento"] == "2026-12-20" and "sem verificar" in _l["aviso"], _l)
src = (AQUI / "financas_email.py").read_text(encoding="utf-8")
confere("e-mail nunca consulta Pix dinâmico", "completar_pix" not in src and "_baixar" not in src)

# --- achar no texto de um PDF -------------------------------------------------------------
texto = f"""Recibo do Pagador
Beneficiário
PADARIA DOIS IRMAOS LTDA   CNPJ 12.345.678/0001-90
Vencimento 30/11/2026   Valor do documento 1.234,56
{bonita}
Autenticação mecânica
Protocolo 12345678901234567890123456789012345678901234567890
"""
ach = fb.achar_linhas(texto, hoje)
confere("texto: acha uma linha válida e ignora números soltos", len(ach) == 1 and ach[0]["linha"] == L, ach)
confere("texto: acha o beneficiário", fb.beneficiario_do_texto(texto) == "PADARIA DOIS IRMAOS LTDA", fb.beneficiario_do_texto(texto))
confere("texto: sem boleto não acha nada", fb.achar_linhas("Fatura do cartão\nTotal 301,76\n", hoje) == [])

# --- banco local --------------------------------------------------------------------------
con = fn.conectar(Path(tempfile.mkdtemp()) / "b.db")
i1, novo1 = fb.registrar(con, r, "PADARIA", "a.pdf")
i2, novo2 = fb.registrar(con, r, "PADARIA", "a.pdf")
confere("registrar: a mesma linha não entra duas vezes", novo1 and not novo2 and i1 == i2)
fb.registrar(con, fb.interpretar(linha_bancaria("341", 1000 + (date(2026, 11, 10) - date(2025, 2, 22)).days, 5000, "9999999999999999999999999"), hoje), "ACADEMIA")
fb.registrar(con, c8, "")
lst = fb.listar(con, hoje)
confere("listar: vencido primeiro, depois a vencer, sem vencimento por último", [b["estado"] for b in lst] == ["vencido", "a vencer", "sem vencimento"], [(b["beneficiario"], b["estado"]) for b in lst])
confere("listar: dias até o vencimento", lst[1]["dias"] == 13 and lst[0]["dias"] == -7)
confere("frase em português simples", "PADARIA: R$ 1.234,56, vencimento 30/11/2026" == fb.frase(lst[1]), fb.frase(lst[1]))
fb.definir_situacao(con, i1, True)
confere("marcar como pago tira da lista aberta e volta com incluir_pagos", len(fb.listar(con, hoje)) == 2 and len(fb.listar(con, hoje, True)) == 3)
confere("remover apaga", fb.remover(con, i1) and len(fb.listar(con, hoje, True)) == 2)

# --- código de barras de 44 dígitos ---
def barras_banco(l):
    return l[0:4] + l[32:47] + l[4:9] + l[10:20] + l[21:31]


def barras_convenio(l):
    return "".join(l[i:i + 11] for i in range(0, 48, 12))


LBB = "34191234546789012345767890123457616560000045090"
confere("código de barras bancário de 44 dígitos vira a mesma linha digitável", fb.interpretar(barras_banco(LBB))["linha"] == LBB and fb.interpretar(" ".join(barras_banco(LBB)[i:i + 11] for i in range(0, 44, 11)))["valor"] == 45090)
try:
    fb.interpretar(barras_banco(LBB)[:-1] + ("0" if barras_banco(LBB)[-1] != "0" else "1"))
    confere("código de barras bancário adulterado levanta erro", False)
except fn.ErroFinance:
    confere("código de barras bancário adulterado levanta erro", True)
for l, nome in ((C, "convênio mod10"), (C8, "convênio mod11")):
    r44 = fb.interpretar(barras_convenio(l))
    confere(f"código de barras de 44 dígitos ({nome}) vira a mesma linha digitável", r44["linha"] == l and r44["valor"] == fb.interpretar(l)["valor"], r44)
confere("achar_linhas acha código de barras solto no texto e não duplica com a linha digitável do mesmo boleto", len(fb.achar_linhas(f"Código de barras: {barras_banco(LBB)}\nLinha: {LBB}")) == 1)
confere("chave de nota fiscal de 44 dígitos não vira boleto", fb.achar_linhas("Chave de acesso: 35260112345678000190550010000012341000012345") == [])

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
