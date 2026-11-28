#!/usr/bin/env python3
"""Legislação na área Cidadania do Studio Miner: projetos e normas por palavra-chave e tramitação de proposições acompanhadas.

Fontes públicas, sem chave: API de dados abertos da Câmara dos Deputados (v2), dados abertos do Senado Federal, LexML (normas de todas as esferas, busca SRU) e o
SAPL do Interlegis, a API pública de câmaras municipais e assembleias (a pessoa informa o endereço da casa, sempre em domínio .leg.br). Todos os dias o Miner procura,
para cada palavra-chave, as proposições e normas novas e avisa com o que o tipo de proposição significa; para as proposições que a pessoa acompanha (por exemplo
PL 1234/2024), avisa cada tramitação nova da Câmara. As consultas por palavra-chave filtram por data no próprio Miner, para a primeira rodada não despejar o histórico.
"""
import html
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import studio_cidadania as cid
import studio_miner_dados as dados

CHAVE, ROTULO, INTERVALO = "legislacao", "Legislação", timedelta(hours=20)
CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
LEXML = "https://www.lexml.gov.br/busca/SRU"
MAX_SAPL = 10
MAX_ACOMPANHADAS = 20
JANELA_INICIAL = 7
SOBREPOSICAO = 2
TIPOS = {
    "PL": "Projeto de lei: propõe lei nova ou muda uma existente; precisa ser aprovado pelas duas Casas e sancionado.",
    "PLP": "Projeto de lei complementar: trata de matéria que a Constituição reserva a lei complementar e exige maioria absoluta.",
    "PEC": "Proposta de emenda à Constituição: muda a Constituição e exige votação em dois turnos em cada Casa.",
    "MPV": "Medida provisória: vale desde a edição, mas perde a eficácia em 120 dias se o Congresso não a votar.",
    "PDL": "Projeto de decreto legislativo: matéria de competência exclusiva do Congresso, sem sanção.",
    "PLV": "Projeto de lei de conversão de medida provisória.",
    "PRC": "Projeto de resolução: regula assunto interno da Casa legislativa.",
    "REQ": "Requerimento: pedido feito por parlamentares à Casa ou a autoridades.",
    "PLN": "Projeto de lei do Congresso Nacional, em geral sobre orçamento.",
    "PLS": "Projeto de lei do Senado.",
}


def configurado(c: dict) -> bool:
    return bool(c.get("palavras") or c.get("acompanhar")) and bool(c.get("camara") or c.get("senado") or c.get("lexml") or c.get("sapl"))


def _proposicao(txt: str):
    m = re.match(r"^\s*([A-Za-z]{2,5})\s*(\d{1,6})\s*/\s*(\d{4})\s*$", txt or "")
    return (m.group(1).upper(), m.group(2), m.group(3)) if m else None


def salvar(campos: dict) -> str:
    c = cid.cfg(CHAVE)
    c["palavras"] = cid.lista(campos.get("palavras", ""))
    for k in ("camara", "senado", "lexml"):
        c[k] = campos.get(k) == "1"
    acomp = []
    for linha in cid.lista(campos.get("acompanhar", ""), minimo=4, maximo=MAX_ACOMPANHADAS, o_que="proposições"):
        p = _proposicao(linha)
        if not p:
            raise dados.ErroMiner(f"Proposição inválida: {linha[:30]}. Use o formato PL 1234/2024.")
        acomp.append(f"{p[0]} {p[1]}/{p[2]}")
    c["acompanhar"] = acomp
    sapl = []
    for u in cid.lista(campos.get("sapl", ""), minimo=10, maximo_item=150, maximo=MAX_SAPL, o_que="endereços de SAPL"):
        sapl.append(cid.validar_url(u, ("leg.br",)))
    c["sapl"] = sapl
    cid.salvar_cfg(CHAVE, c)
    return "Legislação salva."


# ---------- Câmara ----------

def camara_busca(palavra: str, ini: date, fim: date, c) -> list:
    q = urllib.parse.urlencode({"keywords": palavra, "dataApresentacaoInicio": ini.isoformat(), "dataApresentacaoFim": fim.isoformat(), "ordem": "DESC", "ordenarPor": "id", "itens": 50})
    r = cid.json_de(f"{CAMARA}/proposicoes?{q}", urlopen=c.urlopen, dormir=c.dormir, nome="A API da Câmara")
    return [d for d in (r.get("dados") or []) if isinstance(d, dict) and d.get("id")]


def alerta_camara(p: dict, palavra: str) -> dict:
    tipo = str(p.get("siglaTipo", "")).upper()
    ident = f"{tipo} {p.get('numero', '')}/{p.get('ano', '')}".strip()
    return {"id": f"camara:{p['id']}", "titulo": f"Câmara dos Deputados: {ident}", "nivel": "medio", "fonte": "legislacao",
            "resumo": f"{ident} apresentado na Câmara dos Deputados. {TIPOS.get(tipo, 'Proposição legislativa.')} Encontrado pelo termo: {palavra}. Ementa: {cid.limpo(str(p.get('ementa', ''), 4000))[:400]} "
                      "O que fazer: leia a ementa e a tramitação no site da Câmara e decida se vale acompanhar (acrescente a proposição em Ajustes para receber cada tramitação)."}


def camara_id(prop: str, c):
    tipo, num, ano = _proposicao(prop)
    q = urllib.parse.urlencode({"siglaTipo": tipo, "numero": num, "ano": ano})
    r = cid.json_de(f"{CAMARA}/proposicoes?{q}", urlopen=c.urlopen, dormir=c.dormir, nome="A API da Câmara")
    d = [x for x in (r.get("dados") or []) if isinstance(x, dict) and x.get("id")]
    return d[0]["id"] if d else None


def camara_tramitacoes(idp, c) -> list:
    r = cid.json_de(f"{CAMARA}/proposicoes/{idp}/tramitacoes", urlopen=c.urlopen, dormir=c.dormir, nome="A API da Câmara")
    return [d for d in (r.get("dados") or []) if isinstance(d, dict)]


def alerta_tramitacao(prop: str, idp, t: dict) -> dict:
    desc = str(t.get("descricaoTramitacao") or t.get("despacho") or "Tramitação")
    return {"id": f"camara-tram:{idp}:{cid.hash_curto(t.get('dataHora'), desc, t.get('sequencia'))}", "titulo": f"Tramitação de {prop}: {desc[:60]}", "nivel": "medio", "fonte": "legislacao",
            "resumo": f"Nova tramitação de {prop} na Câmara: {desc}. Órgão: {t.get('siglaOrgao') or 'não informado'}. Situação: {t.get('descricaoSituacao') or 'não informada'}. "
                      f"Data: {str(t.get('dataHora', ''))[:10]}. Despacho: {cid.limpo(str(t.get('despacho') or ''), 4000)[:300]} O que fazer: abra a proposição no site da Câmara para ver o que mudou e o próximo passo."}


# ---------- Senado ----------

def _dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _dicts(v)


def _pega(d: dict, *chaves) -> str:
    for k in chaves:
        if d.get(k) not in (None, "", {}):
            return str(d[k])
    return ""


def senado_itens(resp) -> list:
    """Matérias de uma resposta do Senado, tolerando as variações de nome de campo e de aninhamento."""
    saida, vistos = [], set()
    for d in _dicts(resp):
        cod = _pega(d, "CodigoMateria", "Codigo")
        ement = _pega(d, "EmentaMateria", "Ementa")
        if cod and ement and cod not in vistos:
            vistos.add(cod)
            ident = _pega(d, "DescricaoIdentificacao") or " ".join(x for x in (_pega(d, "SiglaSubtipoMateria", "Sigla"), (_pega(d, "NumeroMateria", "Numero") + "/" + _pega(d, "AnoMateria", "Ano")).strip("/")) if x)
            saida.append({"codigo": cod, "ementa": ement, "ident": ident or "Matéria", "data": _pega(d, "DataApresentacao", "Data")[:10]})
    return saida


def senado_busca(palavra: str, ini: date, c) -> list:
    q = urllib.parse.urlencode({"palavraChave": palavra, "dataInicio": ini.strftime("%Y%m%d"), "dataFim": c.hoje.strftime("%Y%m%d")})
    r = cid.json_de(f"{SENADO}/materia/pesquisa/lista?{q}", urlopen=c.urlopen, dormir=c.dormir, nome="O Senado")
    return [m for m in senado_itens(r) if not m["data"] or m["data"].replace("/", "-")[:10] >= ini.isoformat() or _br_ge(m["data"], ini)]


def _br_ge(s: str, ini: date) -> bool:
    d = cid.ler_data(s)
    return bool(d and d >= ini)


def alerta_senado(m: dict, palavra: str) -> dict:
    return {"id": f"senado:{m['codigo']}", "titulo": f"Senado Federal: {m['ident'][:60]}", "nivel": "medio", "fonte": "legislacao",
            "resumo": f"{m['ident']} no Senado Federal. Encontrado pelo termo: {palavra}. Ementa: {cid.limpo(m['ementa'], 400)} O que fazer: leia a matéria e a tramitação no site do Senado e decida se vale acompanhar."}


# ---------- LexML ----------

def lexml_busca(palavra: str, ini: date, c) -> list:
    q = urllib.parse.urlencode({"operation": "searchRetrieve", "version": "1.1", "query": f'"{palavra}"', "startRecord": 1, "maximumRecords": 20})
    _, corpo, _ = cid.http(f"{LEXML}?{q}", urlopen=c.urlopen, dormir=c.dormir, nome="O LexML")
    if b"<!ENTITY" in corpo or b"<!DOCTYPE" in corpo:
        return []
    try:
        raiz = ET.fromstring(corpo)
    except ET.ParseError:
        raise cid.ErroFonte("O LexML respondeu num formato inesperado.")
    saida = []
    for rec in raiz.iter():
        if rec.tag.split("}")[-1] != "record":
            continue
        campos = {}
        for el in rec.iter():
            nome = el.tag.split("}")[-1]
            if el.text and el.text.strip() and nome not in campos:
                campos[nome] = el.text.strip()
        data = campos.get("date", "")[:10]
        if data and data < ini.isoformat():
            continue
        ident = campos.get("urn") or campos.get("identifier") or campos.get("title", "")
        if ident:
            saida.append({"id": cid.hash_curto(ident), "titulo": campos.get("title", "Norma"), "resumo": campos.get("description") or campos.get("abstract") or "", "data": data})
    return saida


def alerta_lexml(n: dict, palavra: str) -> dict:
    return {"id": f"lexml:{n['id']}", "titulo": f"Norma publicada: {n['titulo'][:70]}", "nivel": "medio", "fonte": "legislacao",
            "resumo": f"{n['titulo']}" + (f", de {n['data']}" if n["data"] else "") + f". Encontrada pelo termo: {palavra}. " + (f"Ementa: {cid.limpo(n['resumo'], 400)} " if n["resumo"] else "") +
                      "O que fazer: leia a norma completa no LexML ou no diário oficial de origem e confira a data de vigência."}


# ---------- SAPL ----------

def sapl_busca(base: str, palavras: list, ini: date, c) -> list:
    achados = []
    for pagina in (1, 2, 3):
        r = cid.json_de(f"{base}/api/materia/materialegislativa/?{urllib.parse.urlencode({'page': pagina, 'o': '-data_apresentacao'})}", urlopen=c.urlopen, dormir=c.dormir, nome="O SAPL")
        itens = [d for d in (r.get("results") or []) if isinstance(d, dict)]
        for d in itens:
            if str(d.get("data_apresentacao", ""))[:10] < ini.isoformat():
                continue
            ach = cid.achadas(f"{d.get('ementa', '')} {d.get('__str__', '')}", palavras)
            if ach:
                achados.append((d, ach[0]))
        if not itens or str(itens[-1].get("data_apresentacao", ""))[:10] < ini.isoformat():
            break
    return achados


def alerta_sapl(base: str, d: dict, palavra: str) -> dict:
    host = re.sub(r"^https://", "", base)
    return {"id": f"sapl:{host}:{d.get('id')}", "titulo": f"{host}: {str(d.get('__str__', 'Matéria'))[:60]}", "nivel": "medio", "fonte": "legislacao",
            "resumo": f"{d.get('__str__', 'Matéria legislativa')} apresentada em {str(d.get('data_apresentacao', ''))[:10]} na casa {host}. Encontrada pelo termo: {palavra}. "
                      f"Ementa: {cid.limpo(str(d.get('ementa', ''), 4000))[:400]} O que fazer: abra a matéria no portal da casa e acompanhe a tramitação."}


# ---------- rodada ----------

def executar(c) -> dict:
    conf = cid.cfg(CHAVE)
    try:
        ultimo = date.fromisoformat(cid._ler("leg_dia"))
    except ValueError:
        ultimo = None
    ini = (ultimo - timedelta(days=SOBREPOSICAO)) if ultimo else c.hoje - timedelta(days=JANELA_INICIAL)
    novos, erros, palavras = 0, [], conf.get("palavras", [])

    def tentar(f):
        nonlocal novos
        try:
            novos += f() or 0
        except cid.ErroFonte as ex:
            erros.append(str(ex))

    if conf.get("camara"):
        for p in palavras:
            tentar(lambda p=p: sum(c.avisar(alerta_camara(d, p)) for d in camara_busca(p, ini, c.hoje, c)))
        for prop in conf.get("acompanhar", []):
            def _acomp(prop=prop):
                idp = camara_id(prop, c)
                if not idp:
                    return 0
                chave = "leg_tram_" + str(idp)
                visto = cid._ler(chave)
                tram = camara_tramitacoes(idp, c)
                if not visto:   # primeira vez: guarda o ponto de partida sem avisar o histórico
                    cid._gravar(**{chave: str(len(tram))})
                    return c.avisar({"id": f"camara-inicio:{idp}", "titulo": f"Acompanhamento iniciado: {prop}", "nivel": "medio", "fonte": "legislacao",
                                     "resumo": f"O Miner passou a acompanhar {prop} na Câmara: {len(tram)} tramitação(ões) até agora. A partir daqui, cada tramitação nova vira aviso."})
                n = sum(c.avisar(alerta_tramitacao(prop, idp, t)) for t in tram[int(visto or 0):])
                cid._gravar(**{chave: str(len(tram))})
                return n
            tentar(_acomp)
    if conf.get("senado"):
        for p in palavras:
            tentar(lambda p=p: sum(c.avisar(alerta_senado(m, p)) for m in senado_busca(p, ini, c)))
    if conf.get("lexml"):
        for p in palavras:
            tentar(lambda p=p: sum(c.avisar(alerta_lexml(n, p)) for n in lexml_busca(p, ini, c)))
    for base in conf.get("sapl", []):
        tentar(lambda base=base: sum(c.avisar(alerta_sapl(base, d, p)) for d, p in sapl_busca(base, palavras, ini, c)))
    if not erros:
        cid._gravar(leg_dia=c.hoje.isoformat())
    return {"novos": novos, "erros": erros, "resumo": f"{len(palavras)} termo(s), {len(conf.get('acompanhar', []))} proposição(ões) acompanhada(s)"}


def formulario(csrf: str) -> str:
    c = cid.cfg(CHAVE)
    e = lambda t: html.escape(str(t), quote=True)   # noqa: E731
    marca = lambda k: " checked" if c.get(k) else ""   # noqa: E731
    est = cid.estado(sys.modules[__name__])
    return (f'<h2 id="h-leg">Legislação</h2><form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}">'
            f'<p><label for="lpal">Termos a procurar em projetos e normas (um por linha)</label><br><textarea id="lpal" name="palavras" rows="4" cols="40">{e(chr(10).join(c.get("palavras", [])))}</textarea></p>'
            f'<p><label for="lac">Proposições da Câmara que você acompanha (por exemplo PL 1234/2024, uma por linha)</label><br><textarea id="lac" name="acompanhar" rows="3" cols="40">{e(chr(10).join(c.get("acompanhar", [])))}</textarea></p>'
            f'<p><input id="lcam" type="checkbox" name="camara" value="1"{marca("camara")}> <label for="lcam">Câmara dos Deputados</label></p>'
            f'<p><input id="lsen" type="checkbox" name="senado" value="1"{marca("senado")}> <label for="lsen">Senado Federal</label></p>'
            f'<p><input id="llex" type="checkbox" name="lexml" value="1"{marca("lexml")}> <label for="llex">LexML (normas de todas as esferas)</label></p>'
            f'<p><label for="lsapl">Câmaras municipais e assembleias com SAPL (endereço https do portal, domínio leg.br, um por linha)</label><br><textarea id="lsapl" name="sapl" rows="3" cols="40">{e(chr(10).join(c.get("sapl", [])))}</textarea></p>'
            '<button type="submit">Salvar legislação</button></form>' + (f'<p class="meta" role="status">{e(est)}</p>' if est else ""))
