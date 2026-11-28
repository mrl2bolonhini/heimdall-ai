#!/usr/bin/env python3
"""Regras de serviços para o Correio (studio_correio): e-mail oficial e golpes (Miner, área Rotina) e documentos de saúde (Studio Health).

Cada regra decide primeiro só com remetente e assunto se vale baixar a mensagem. O Finance usa studio_correio.buscar_completas (boletos e Pix, com anexos).
"""
import re

import studio_cidadania as cid
import studio_email_oficial as eo

BAIXA_PRIORIDADE = [n.strip() for n in eo.BAIXA_PRIORIDADE_PADRAO.split(",") if n.strip()]
PALAVRAS_SAUDE = ["exame", "resultado", "laudo", "receita medica", "encaminhamento", "pedido medico", "atestado", "agendamento de consulta", "vacina"]


def _oficial_ou_imitacao(m) -> bool:
    return eo.dominio_oficial(m.dominio, []) or bool(eo.servico_citado(m.de) or eo.servico_citado(m.assunto))


def email_oficial(m):
    """Mesma classificação do monitor de e-mail oficial: golpe por imitação de serviço público, ou comunicado oficial autêntico com tom de urgência."""
    au = m.auth
    verificavel = bool(au.get("dmarc"))
    servico_assunto, servico_remet = eo.servico_citado(m.assunto), eo.servico_citado(m.de)
    servico = servico_remet or servico_assunto
    oficial_dom = eo.dominio_oficial(m.dominio, [])
    autentico = au.get("dmarc") == "pass" and eo.dominio_oficial(au.get("from") or m.dominio, [])
    susto = any(eo.sem_acento(p) in eo.sem_acento(m.assunto) for p in eo.SUSTO)
    if oficial_dom and not verificavel:
        return None   # o provedor da conta não informa a autenticação: não dá para afirmar nem golpe nem oficial
    if oficial_dom and autentico:
        alvo = " ".join([servico or "", m.dominio, m.de]).lower()
        if not susto or any(n.lower() in alvo for n in BAIXA_PRIORIDADE):
            return None
        return {"id": "email|" + m.mid.lower(), "titulo": "E-mail oficial (urgência alta): " + (servico or "serviço público"), "nivel": "alto", "fonte": "email",
                "resumo": (f"Assunto: {cid.limpo(m.assunto, 100)}. O que significa: comunicado de um serviço oficial, com remetente confirmado pelo provedor, que cita pendência, prazo ou cobrança. "
                           "O que fazer: abra o app ou o site oficial por conta própria, sem usar links do e-mail, e confira o que é pedido e até quando.")}
    if oficial_dom:
        motivo = f"o domínio parece oficial, mas o provedor não confirmou a autenticidade (DMARC: {au.get('dmarc') or 'ausente'})"
    elif servico_remet:
        motivo = f"o remetente usa o nome de {servico_remet}, mas o domínio ({m.dominio or 'desconhecido'}) não é oficial"
    elif servico and susto:
        motivo = f"cita {servico} com tom de urgência, mas o remetente ({m.dominio or 'desconhecido'}) não é de domínio oficial"
    else:
        return None
    return {"id": "email|" + m.mid.lower(), "titulo": "Possível golpe por e-mail: " + (servico or "serviço público"), "nivel": "alto", "fonte": "email",
            "resumo": (f"De: {cid.limpo(m.de, 80)}. Assunto: {cid.limpo(m.assunto, 100)}. O que significa: {motivo}; golpes assim costumam levar a uma página falsa que pede dados, senha ou pagamento. "
                       "O que fazer: não clique em links, não responda e não informe dados; se quiser conferir, abra o app ou o site oficial digitando o endereço por conta própria.")}


def saude(m):
    """Guarda os anexos (PDF ou imagem) de e-mails com documento de saúde em A revisar do Studio Health; nada é aceito sozinho e o aviso não traz o conteúdo."""
    msg = m.completa()
    if msg is None:
        return None
    import studio_exames
    guardados = 0
    for parte in msg.iter_attachments():
        tipo = parte.get_content_type()
        if tipo != "application/pdf" and not tipo.startswith("image/"):
            continue
        try:
            dados = parte.get_content()
            if not isinstance(dados, bytes):
                continue
            studio_exames.registrar(dados, parte.get_filename() or "documento", "e-mail")
            guardados += 1
        except Exception:  # noqa: BLE001 - duplicado, grande demais ou ilegível: segue com os demais
            continue
    if not guardados:
        return None
    return {"id": f"saude-email:{cid.hash_curto(m.mid)}", "titulo": "Documento de saúde recebido por e-mail", "nivel": "medio", "fonte": "saude",
            "resumo": f"{guardados} arquivo(s) de um e-mail que parece trazer documento de saúde foram guardados em A revisar, no Studio Health. Nada foi aceito: confira e decida lá."}


def regras(Regra) -> list:
    return [
        Regra("email", _oficial_ou_imitacao, email_oficial, "E-mail oficial"),
        Regra("saude", lambda m: any(p in cid.sem_acento(m.assunto) for p in PALAVRAS_SAUDE), saude, "Documentos de saúde"),
    ]
