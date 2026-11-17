#!/usr/bin/env python3
"""Lê o Gmail em busca de boletos e Pix copia e cola e os registra no Finance como contas a pagar.

Só lê (IMAP em modo somente leitura: nada é marcado como lido, movido ou apagado) e usa a mesma senha de aplicativo do monitor de e-mails oficiais
(HEIMDALL_EMAIL_USUARIO e HEIMDALL_EMAIL_SENHA_APP, no .env). O e-mail é dado não confiável: links nunca são abertos, só o texto e os PDFs anexados
são lidos, e só vale linha digitável com dígitos verificadores corretos. Boleto falso por e-mail é golpe comum, então o remetente é conferido pela
autenticação que o próprio Gmail registrou (DMARC/DKIM) e, se não passar, o boleto entra com um aviso. Nada é pago.

Uso: python3 financas_cli.py --ler-email        (uma verificação)
O painel do Finance repete a verificação a cada 15 minutos quando há senha de e-mail no .env (HEIMDALL_FINANCE_EMAIL=0 desliga).
"""
import email
import email.policy
import html
import imaplib
import json
import re
from pathlib import Path

import financas_arquivos as fa
import financas_boletos as fb
import financas_nucleo as fn
import heimdall_email_oficial as eo

AQUI = Path(__file__).resolve().parent
MAX_PDF = 8 * 1024 * 1024
DIAS = 7
LIMITE = 150  # mensagens mais recentes que passam no filtro, por rodada
MAX_DIAS = 365
# Termos que fazem o Gmail separar a mensagem. É só a primeira peneira: o que decide é achar linha digitável ou Pix com dígitos corretos no texto ou no PDF.
# Palavras genéricas (conta, cobrança, vencimento) só valem acompanhadas de um verbo ou termo de pagamento, para não trazer a caixa inteira.
TERMOS = ('filename:pdf OR boleto OR fatura OR mensalidade OR "linha digitavel" OR "codigo de barras" OR "pix copia e cola" OR "copia e cola" OR "chave pix" OR "qr code pix" '
          'OR "segunda via" OR "2a via" OR "2 via" OR "nota de cobranca" OR "aviso de cobranca" OR "aviso de vencimento" OR "data de vencimento" OR "vence em" OR "vence dia" '
          'OR "valor a pagar" OR "total a pagar" OR "pague ate" OR "para pagar" OR "pagamento pendente" OR "pagamento em aberto" '
          'OR (conta (vencimento OR pagar OR pagamento OR vence)) OR (cobranca (vencimento OR pagar OR pagamento OR vence)) OR (pix (pagar OR pagamento OR vencimento OR valor))')


def consulta(dias: int = DIAS) -> str:
    return "newer_than:%dd -from:uber.com -category:promotions -category:social (%s)" % (max(1, min(int(dias), MAX_DIAS)), TERMOS)
AVISO_ORIGEM = "Remetente não autenticado: pode ser boleto falso. Confira o nome do beneficiário e o valor no app do seu banco antes de pagar."


def credenciais(env_path: Path = None) -> dict:
    cfg = eo.ler_env(str(env_path or AQUI / ".env"))
    if not cfg.get("HEIMDALL_EMAIL_USUARIO") or not cfg.get("HEIMDALL_EMAIL_SENHA_APP"):
        return {}
    return {"HEIMDALL_EMAIL_USUARIO": cfg["HEIMDALL_EMAIL_USUARIO"], "HEIMDALL_EMAIL_SENHA_APP": cfg["HEIMDALL_EMAIL_SENHA_APP"]}


def buscar(cfg: dict, dias: int = DIAS) -> list:
    """Mensagens recentes da caixa de entrada que parecem trazer boleto ou Pix. Retorna objetos de e-mail."""
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=60)
    achadas = []
    try:
        imap.login(cfg["HEIMDALL_EMAIL_USUARIO"], cfg["HEIMDALL_EMAIL_SENHA_APP"].replace(" ", ""))
        if imap.select("INBOX", readonly=True)[0] != "OK":
            return []
        tipo, dados = imap.uid("SEARCH", None, "X-GM-RAW", '"%s"' % consulta(dias).replace('"', '\\"'))
        if tipo != "OK" or not dados or not dados[0]:
            return []
        for uid in dados[0].split()[-LIMITE:]:
            tipo, partes = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if tipo == "OK" and partes and isinstance(partes[0], tuple):
                achadas.append(email.message_from_bytes(partes[0][1], policy=email.policy.default))
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
    return achadas


def _texto_corpo(msg) -> str:
    saida = []
    for parte in msg.walk():
        if parte.get_content_maintype() != "text" or parte.get_filename():
            continue
        try:
            t = parte.get_content()
        except Exception:  # noqa: BLE001
            continue
        if parte.get_content_type() == "text/html":
            t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
            t = re.sub(r"(?i)<br\s*/?>|</p>|</td>|</tr>|</div>", "\n", t)
            t = html.unescape(re.sub(r"<[^>]+>", " ", t))
        saida.append(t)
    return "\n".join(saida)[:80000]


def _textos_pdf(msg) -> list:
    saida = []
    for parte in msg.iter_attachments():
        nome = parte.get_filename() or ""
        if not (parte.get_content_type() == "application/pdf" or nome.lower().endswith(".pdf")):
            continue
        try:
            dados = parte.get_content()
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(dados, (bytes, bytearray)) or len(dados) > MAX_PDF:
            continue
        try:
            saida.append(fa.texto_do_pdf(bytes(dados)))
        except fn.ErroFinance:
            continue
        if len(saida) >= 5:
            break
    return saida


def motivo_descarte(msg, corpo: str, pdfs: list) -> str:
    """Por que um e-mail que passou na busca não rendeu boleto: ajuda a entender o que fazer."""
    n_pdf = sum(1 for p in msg.iter_attachments() if p.get_content_type() == "application/pdf" or (p.get_filename() or "").lower().endswith(".pdf"))
    todo = corpo + "\n" + "\n".join(pdfs)
    nums = fb.diagnosticar_numeros(todo)
    if nums:
        return "achei número parecido com boleto, mas os dígitos não conferem: " + nums[0]
    if "000201" in todo:
        return "achei um código parecido com Pix copia e cola, mas ele não confere (incompleto ou adulterado)"
    if n_pdf and not any(p.strip() for p in pdfs):
        return "tem PDF anexo, mas sem texto legível (provavelmente imagem escaneada) ou grande demais (acima de 8 MB)"
    links = False
    for parte in msg.walk():
        if parte.get_content_maintype() == "text":
            try:
                if re.search(r"https?://", parte.get_content()):
                    links = True
            except Exception:  # noqa: BLE001
                pass
    if links and re.search(r"boleto|fatura|pagar|pague|vencimento|vence|cobran[cç]a", corpo, re.I):
        return "fala de cobrança e só traz link (links nunca são abertos); abra o e-mail e copie a linha digitável para o Finance"
    return "não traz linha digitável nem Pix no texto, e não há PDF com boleto"


def processar(con, msgs: list, estado: dict, agora: str = None, diag: dict = None, ignorar_vistos: bool = False) -> list:
    """Registra os boletos e Pix achados. estado['ids'] guarda os e-mails já lidos. Devolve [{assunto, remetente, novos, repetidos, aviso}].
    Com diag (um dicionário), anota quantas mensagens vieram da busca e por que cada uma foi descartada. Com ignorar_vistos, relê também as já lidas."""
    vistos = estado.setdefault("ids", [])
    resultado = []
    if diag is not None:
        diag["total"] = len(msgs)
        diag.setdefault("descartes", [])
    for msg in msgs:
        mid = (msg.get("Message-ID") or "").strip()
        if mid and mid in vistos and not ignorar_vistos:
            if diag is not None:
                diag["descartes"].append((eo.dominio_do_remetente(eo.decodificar(msg.get("From"))) or "remetente desconhecido", eo.decodificar(msg.get("Subject"))[:80], "já lido em rodada anterior"))
            continue
        de = eo.decodificar(msg.get("From"))
        assunto = eo.decodificar(msg.get("Subject"))[:80]
        pdfs = _textos_pdf(msg)
        textos = [_texto_corpo(msg)] + pdfs
        todo = "\n".join(textos)
        achados = []
        for t in textos:
            for b in fb.achar_linhas(t):
                if all(b["linha"] != x["linha"] for x in achados):
                    achados.append(b)
        if mid:
            vistos.append(mid)
            del vistos[:-500]
        if not achados:
            if diag is not None:
                diag["descartes"].append((eo.dominio_do_remetente(de) or "remetente desconhecido", assunto, motivo_descarte(msg, textos[0], pdfs)))
            continue
        au = eo.autenticacao(msg)
        confiavel = au.get("dmarc") == "pass" or (au.get("dkim") == "pass" and au.get("spf") == "pass")
        dom = eo.dominio_do_remetente(de) or "remetente desconhecido"
        quem = fb.beneficiario_do_texto(todo)
        dono = fb.dono_do_texto(todo, fb.pessoas(con))
        novos = 0
        motivo = fb.sinal_pagamento(_texto_corpo(msg)) if confiavel else ""  # só confia na frase de pagamento se o remetente for autêntico
        for b in achados:
            novo = fb.registrar(con, b, quem or b.get("beneficiario", ""), f"e-mail de {dom}: {assunto}", agora, dono, "" if confiavel else AVISO_ORIGEM, motivo)[1]
            novos += 1 if novo else 0
        resultado.append({"assunto": assunto, "remetente": dom, "novos": novos, "repetidos": len(achados) - novos, "aviso": "" if confiavel else AVISO_ORIGEM, "motivo": motivo})
    return resultado


def executar(con, cfg: dict, estado_arq: Path, buscar_fn=buscar, dias: int = DIAS, diag: dict = None, ignorar_vistos: bool = False) -> list:
    try:
        estado = json.loads(Path(estado_arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        estado = {}
    r = processar(con, buscar_fn(cfg) if dias == DIAS else buscar_fn(cfg, dias), estado, None, diag, ignorar_vistos)
    try:
        Path(estado_arq).write_text(json.dumps(estado), encoding="utf-8")
        Path(estado_arq).chmod(0o600)
    except OSError:
        pass
    return r
