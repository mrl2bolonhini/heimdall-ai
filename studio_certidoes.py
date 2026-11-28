#!/usr/bin/env python3
"""Domicílio Judicial Eletrônico e certidões, na área Cidadania do Studio Miner.

1. Lembrete assistido do Domicílio Judicial Eletrônico (CNJ): quem se cadastra passa a receber as comunicações dos tribunais só por lá, e a entrada exige a
   conta gov.br da própria pessoa; por isso o Miner não consulta nada: avisa, nos dias úteis (ou toda segunda-feira), que é hora de conferir. Desligado até a
   pessoa ligar em Ajustes.
2. Calendário de certidões: a pessoa registra cada certidão com a data de emissão (a validade vem do tipo) ou com a validade informada, e o Miner avisa antes
   de vencer (30, 15, 7 e 3 dias, no dia e depois de vencida). O aviso traz "Prazo: dd/mm/aaaa"; ao aceitar, vira evento no Calendário.
Validades de referência: CNDT (TST) 180 dias, certidão negativa federal (Receita e PGFN) 180 dias, Certificado de Regularidade do FGTS 30 dias; as estaduais,
as municipais e as demais têm validade própria, que a pessoa informa. Confira sempre no documento emitido.
"""
import html
import re
import sys
from datetime import date, timedelta

import studio_cidadania as cid
import studio_feriados as feriados
import studio_miner_dados as dados

CHAVE, ROTULO, INTERVALO = "certidoes", "Domicílio e certidões", timedelta(hours=20)
MARCOS = (30, 15, 7, 3, 0)
MAX_CERTIDOES = 40
TIPOS = {
    "cndt": ("Certidão Negativa de Débitos Trabalhistas (CNDT)", 180, "no site do TST"),
    "federal": ("Certidão negativa de débitos federais", 180, "no site da Receita Federal ou da Procuradoria-Geral da Fazenda Nacional"),
    "fgts": ("Certificado de Regularidade do FGTS", 30, "no site da Caixa"),
    "estadual": ("Certidão negativa estadual", 0, "no site da Secretaria da Fazenda do estado"),
    "municipal": ("Certidão negativa municipal", 0, "no site da prefeitura"),
    "outra": ("Outra certidão", 0, "no órgão emissor"),
}
FREQUENCIAS = {"desligado": "Desligado", "diaria": "Todo dia útil", "semanal": "Toda segunda-feira"}


def _e(t) -> str:
    return html.escape(str(t), quote=True)


def configurado(c: dict) -> bool:
    return bool(c.get("certidoes")) or c.get("domicilio", "desligado") != "desligado"


def validade(item: dict):
    """Data de vencimento: a informada ou a emissão mais os dias do tipo."""
    v = cid.ler_data(item.get("validade", ""))
    if v:
        return v
    em, dias = cid.ler_data(item.get("emissao", "")), TIPOS.get(item.get("tipo"), ("", 0, ""))[1]
    return em + timedelta(days=dias) if em and dias else None


def salvar(campos: dict) -> str:
    c = cid.cfg(CHAVE)
    freq = campos.get("domicilio", c.get("domicilio", "desligado"))
    if freq not in FREQUENCIAS:
        raise dados.ErroMiner("Escolha uma frequência válida para o lembrete do Domicílio.")
    c["domicilio"] = freq
    if campos.get("tipo"):   # nova certidão
        tipo = campos["tipo"]
        if tipo not in TIPOS:
            raise dados.ErroMiner("Escolha o tipo da certidão.")
        emissao, val = campos.get("emissao", "").strip(), campos.get("validade", "").strip()
        if (emissao and not cid.ler_data(emissao)) or (val and not cid.ler_data(val)):
            raise dados.ErroMiner("Informe as datas no formato dd/mm/aaaa.")
        item = {"id": cid.hash_curto(tipo, emissao, val, campos.get("nome", ""), len(c.get("certidoes", []))), "tipo": tipo, "nome": re.sub(r"\s+", " ", campos.get("nome", "")).strip()[:60],
                "emissao": emissao, "validade": val}
        if not validade(item):
            raise dados.ErroMiner("Informe a data de emissão (a validade vem do tipo) ou a data de validade da certidão.")
        if len(c.get("certidoes", [])) >= MAX_CERTIDOES:
            raise dados.ErroMiner(f"Registre no máximo {MAX_CERTIDOES} certidões.")
        c.setdefault("certidoes", []).append(item)
        cid.salvar_cfg(CHAVE, c)
        return "Certidão registrada."
    cid.salvar_cfg(CHAVE, c)
    return "Lembrete do Domicílio atualizado."


def remover(campos: dict) -> str:
    c = cid.cfg(CHAVE)
    antes = len(c.get("certidoes", []))
    c["certidoes"] = [i for i in c.get("certidoes", []) if i["id"] != campos.get("id")]
    cid.salvar_cfg(CHAVE, c)
    return "Certidão removida." if len(c["certidoes"]) < antes else "Certidão não encontrada."


def _nivel(dias: int) -> str:
    return "critico" if dias <= 3 else "alto" if dias <= 7 else "medio"


def alerta_certidao(item: dict, fim: date, dias: int, marco: int = 0) -> dict:
    nome, _, onde = TIPOS[item["tipo"]]
    rotulo = item.get("nome") or nome
    if dias < 0:
        return {"id": f"certidao:{item['id']}:vencida", "titulo": f"Certidão vencida: {rotulo}", "nivel": "critico", "fonte": "certidoes",
                "resumo": f"{rotulo} venceu em {cid.data_br(fim)}. O que significa: o documento deixou de provar a regularidade e pode barrar contrato, licitação, financiamento ou transação. O que fazer: emita uma nova {onde}."}
    quando = "vence hoje" if dias == 0 else f"vence em {dias} dia(s)"
    return {"id": f"certidao:{item['id']}:{marco}", "titulo": f"Certidão {quando}: {rotulo}", "nivel": _nivel(dias), "fonte": "certidoes",
            "resumo": f"{rotulo} {quando}, em {cid.data_br(fim)}. O que significa: depois dessa data o documento não vale mais para provar a regularidade. O que fazer: emita uma nova {onde}, e atualize o registro aqui. Prazo: {cid.data_br(fim)}"}


def alerta_domicilio(hoje: date) -> dict:
    return {"id": f"domicilio:{hoje.isoformat()}", "titulo": "Conferir o Domicílio Judicial Eletrônico", "nivel": "medio", "fonte": "justica",
            "resumo": "Quem se cadastra no Domicílio Judicial Eletrônico, do CNJ, passa a receber por lá as citações e as intimações dos tribunais, e o prazo corre mesmo que ninguém abra a comunicação. "
                      "O que fazer: entre com a sua conta gov.br digitando o endereço do Domicílio Judicial Eletrônico no navegador (nunca por link recebido por mensagem) e confira se há comunicações novas."}


def executar(c) -> dict:
    conf = cid.cfg(CHAVE)
    novos = 0
    cal = feriados.nacional()
    freq = conf.get("domicilio", "desligado")
    if (freq == "diaria" and cal.dia_util(c.hoje)) or (freq == "semanal" and c.hoje.weekday() == 0 and cal.dia_util(c.hoje)):
        novos += c.avisar(alerta_domicilio(c.hoje))
    for it in conf.get("certidoes", []):
        fim = validade(it)
        if not fim:
            continue
        dias = (fim - c.hoje).days
        if dias < 0:
            novos += c.avisar(alerta_certidao(it, fim, dias))
        elif dias <= max(MARCOS):
            marco = min(m for m in MARCOS if dias <= m)   # o menor marco já alcançado: cada marco avisa uma vez
            novos += c.avisar(alerta_certidao(it, fim, dias, marco))
    return {"novos": novos, "resumo": f"{len(conf.get('certidoes', []))} certidão(ões)"}


def formulario(csrf: str) -> str:
    c = cid.cfg(CHAVE)
    freq = c.get("domicilio", "desligado")
    op = "".join(f'<option value="{k}"{" selected" if k == freq else ""}>{_e(v)}</option>' for k, v in FREQUENCIAS.items())
    tipos = "".join(f'<option value="{k}">{_e(v[0])}</option>' for k, v in TIPOS.items())
    saida = ['<h2 id="h-cert">Domicílio Judicial Eletrônico e certidões</h2>',
             f'<form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{_e(csrf)}">'
             f'<p><label for="dom">Lembrete para conferir o Domicílio Judicial Eletrônico</label><br><select id="dom" name="domicilio">{op}</select></p>'
             '<button type="submit">Salvar lembrete</button></form>',
             f'<form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{_e(csrf)}"><h3>Registrar certidão</h3>'
             f'<p><label for="ctipo">Tipo</label><br><select id="ctipo" name="tipo">{tipos}</select></p>'
             '<p><label for="cnome">Identificação (opcional, por exemplo o estado ou a cidade)</label><br><input id="cnome" name="nome" type="text" maxlength="60"></p>'
             '<p><label for="cem">Data de emissão (dd/mm/aaaa)</label><br><input id="cem" name="emissao" type="text" inputmode="numeric" maxlength="10"></p>'
             '<p><label for="cval">Data de validade (dd/mm/aaaa, obrigatória nas estaduais, municipais e outras)</label><br><input id="cval" name="validade" type="text" inputmode="numeric" maxlength="10"></p>'
             '<button type="submit">Registrar certidão</button></form>']
    itens = c.get("certidoes", [])
    if itens:
        li = []
        for it in itens:
            fim = validade(it)
            nome = it.get("nome") or TIPOS[it["tipo"]][0]
            li.append(f'<li>{_e(nome)}: vence em {cid.data_br(fim) if fim else "data não informada"}. '
                      f'<form class="acao" method="post" action="/ajustes/fontes/{CHAVE}/remover"><input type="hidden" name="csrf" value="{_e(csrf)}"><input type="hidden" name="id" value="{_e(it["id"])}">'
                      f'<button type="submit" aria-label="Remover {_e(nome)}">Remover</button></form></li>')
        saida.append("<h3>Certidões registradas</h3><ol>" + "".join(li) + "</ol>")
    est = cid.estado(sys.modules[__name__])
    if est:
        saida.append(f'<p class="meta" role="status">{_e(est)}</p>')
    return "".join(saida)
