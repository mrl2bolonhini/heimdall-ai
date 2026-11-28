#!/usr/bin/env python3
"""Diários oficiais de municípios, estados e outros órgãos, na área Cidadania do Studio Miner (o da União está em studio_dou.py).

1. Querido Diário (Open Knowledge Brasil; cerca de 500 municípios, API pública): a pessoa lista os municípios (Cidade/UF); todos os dias o Miner procura as palavras-chave
   nas edições novas e avisa com o trecho. Como alguns raspadores do Querido Diário param de funcionar, o Miner confere a data da última edição de cada município e avisa
   quando passa de 15 dias sem edição nova, para a pessoa usar a reserva abaixo ou o site do município.
2. Páginas e PDFs de diários que o Querido Diário não cobre (diário do estado, de município fora da lista, de autarquia): a pessoa informa o endereço; o Miner lê a
   página ou o PDF do dia (PDF só com o leitor de PDF instalado), respeitando o robots.txt, e avisa os trechos com as palavras-chave. Nada é lido quando o robots.txt pede
   para não ler: o aviso diz isso.
"""
import html
import re
import sys
import urllib.parse
from datetime import date, timedelta

import studio_cidadania as cid
import studio_feriados as feriados
import studio_miner_dados as dados

CHAVE, ROTULO, INTERVALO = "diarios", "Diários de municípios e estados", timedelta(hours=20)
QD = "https://api.queridodiario.ok.org.br"
MAX_MUNICIPIOS = 10
MAX_PAGINAS = 10
DEFASAGEM_DIAS = 15
MAX_ALERTAS = 40


def configurado(c: dict) -> bool:
    return bool(c.get("palavras")) and bool(c.get("municipios") or c.get("paginas"))


def salvar(campos: dict, urlopen=None) -> str:
    c = cid.cfg(CHAVE)
    c["palavras"] = cid.lista(campos.get("palavras", ""))
    antigos = {m["nome"]: m["id"] for m in c.get("municipios", [])}
    munis = []
    for t in cid.lista(campos.get("municipios", ""), minimo=4, maximo=MAX_MUNICIPIOS, o_que="municípios"):
        try:
            cidade, uf = feriados.partir_municipio(t)
        except feriados.ErroFeriados as ex:
            raise dados.ErroMiner(str(ex))
        nome = f"{cidade}/{uf}"
        try:
            ident = antigos.get(nome) or feriados.codigo_ibge(cidade, uf, urlopen)
        except feriados.ErroFeriados as ex:
            raise dados.ErroMiner(f"Município {nome}: {ex}.")
        munis.append({"nome": nome, "id": str(ident)})
    c["municipios"] = munis
    paginas = []
    for t in cid.lista(campos.get("paginas", ""), minimo=12, maximo_item=300, maximo=MAX_PAGINAS, o_que="endereços de diários"):
        paginas.append(cid.validar_url(t))
    c["paginas"] = paginas
    cid.salvar_cfg(CHAVE, c)
    return "Diários salvos."


def _expr(palavras: list) -> str:
    return " | ".join('"' + p.replace('"', "") + '"' for p in palavras)


def edicoes(territorio: str, palavras: list, desde: date, c) -> list:
    q = urllib.parse.urlencode({"territory_ids": territorio, "querystring": _expr(palavras), "published_since": desde.isoformat(), "excerpt_size": 300, "number_of_excerpts": 3,
                                "size": 20, "sort_by": "descending_date"})
    r = cid.json_de(f"{QD}/gazettes?{q}", urlopen=c.urlopen, dormir=c.dormir, nome="O Querido Diário")
    return [g for g in (r.get("gazettes") or []) if isinstance(g, dict)]


def ultima_edicao(territorio: str, c):
    r = cid.json_de(f"{QD}/gazettes?{urllib.parse.urlencode({'territory_ids': territorio, 'size': 1, 'sort_by': 'descending_date'})}", urlopen=c.urlopen, dormir=c.dormir, nome="O Querido Diário")
    g = [x for x in (r.get("gazettes") or []) if isinstance(x, dict)]
    try:
        return date.fromisoformat(str(g[0].get("date", ""))[:10]) if g else None
    except ValueError:
        return None


def alerta_edicao(nome: str, g: dict, palavras: list) -> dict:
    trechos = [cid.limpo(x, 300) for x in (g.get("excerpts") or []) if x]
    ach = cid.achadas(" ".join(trechos), palavras) or palavras[:1]
    extra = " (edição extra)" if g.get("is_extra_edition") else ""
    return {"id": f"qd:{g.get('territory_id')}:{g.get('date')}:{g.get('edition') or ''}:{cid.hash_curto(g.get('url'))}", "titulo": f"Diário de {nome}: {ach[0][:40]}", "nivel": "medio", "fonte": "diarios",
            "resumo": f"Edição de {g.get('date')}{extra} do diário oficial de {nome} cita {', '.join(ach[:3])}. O que significa: publicação oficial do município, que pode conter nomeação, edital, "
                      f"convocação, decisão ou prazo. O que fazer: abra a edição no site oficial e leia o ato inteiro. Trecho: {(trechos[0] if trechos else '')[:300]}"}


def alerta_defasagem(nome: str, ultima, hoje: date) -> dict:
    quando = f"a última edição que o Querido Diário tem é de {cid.data_br(ultima)}" if ultima else "o Querido Diário não tem edições deste município"
    return {"id": f"qd-defasado:{nome}:{hoje:%Y%m}", "titulo": f"Diário de {nome} sem edição nova no Querido Diário", "nivel": "medio", "fonte": "diarios",
            "resumo": f"Para {nome}, {quando}. O que significa: o coletor do município pode ter parado, e as buscas por palavra-chave podem estar deixando passar publicações. "
                      "O que fazer: confira o diário no site oficial do município e, se quiser, informe o endereço dele nos Ajustes para o Miner ler a página ou o PDF diretamente."}


def vigiar(paginas: list, palavras: list, c, fonte: str = "diarios", rotulo: str = "Página") -> tuple:
    """(novos, erros): lê cada página ou PDF e avisa os trechos com as palavras-chave (um aviso por trecho novo)."""
    novos, erros = 0, []
    for url in paginas:
        try:
            texto = cid.texto_da_pagina(url, c.urlopen, nome=f"{rotulo} {urllib.parse.urlsplit(url).netloc}")
        except cid.ErroFonte as ex:
            erros.append(str(ex))
            continue
        for p in cid.achadas(texto, palavras)[:5]:
            tr = cid.trecho(texto, p, 140)
            if novos >= MAX_ALERTAS:
                break
            host = urllib.parse.urlsplit(url).netloc
            novos += c.avisar({"id": f"pagina:{cid.hash_curto(url, p, tr)}", "titulo": f"{rotulo} {host}: {p[:40]}", "nivel": "medio", "fonte": fonte,
                               "resumo": f"A página {host} cita {p}. O que significa: o texto publicado menciona um termo que você acompanha; pode ser edital, convocação, nomeação ou aviso. "
                                         f"O que fazer: abra a página no site oficial e leia o ato inteiro. Trecho: {tr}"})
    return novos, erros


def executar(c) -> dict:
    conf = cid.cfg(CHAVE)
    palavras = conf.get("palavras", [])
    novos, erros = 0, []
    try:
        desde = date.fromisoformat(cid._ler("diarios_dia")) - timedelta(days=2)
    except ValueError:
        desde = c.hoje - timedelta(days=7)
    for m in conf.get("municipios", []):
        try:
            for g in edicoes(m["id"], palavras, desde, c):
                novos += c.avisar(alerta_edicao(m["nome"], g, palavras))
            ult = ultima_edicao(m["id"], c)
            if not ult or (c.hoje - ult).days > DEFASAGEM_DIAS:
                novos += c.avisar(alerta_defasagem(m["nome"], ult, c.hoje))
        except cid.ErroFonte as ex:
            erros.append(str(ex))
            break
    if conf.get("paginas"):
        n, e = vigiar(conf["paginas"], palavras, c)
        novos += n
        erros.extend(e)
    if not erros:
        cid._gravar(diarios_dia=c.hoje.isoformat())
    return {"novos": novos, "erros": erros, "resumo": f"{len(conf.get('municipios', []))} município(s), {len(conf.get('paginas', []))} página(s)"}


def formulario(csrf: str) -> str:
    c = cid.cfg(CHAVE)
    e = lambda t: html.escape(str(t), quote=True)   # noqa: E731
    est = cid.estado(sys.modules[__name__])
    return (f'<h2 id="h-diarios">Diários de municípios e estados</h2><form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}">'
            f'<p><label for="dpal2">Termos a procurar (um por linha)</label><br><textarea id="dpal2" name="palavras" rows="4" cols="40">{e(chr(10).join(c.get("palavras", [])))}</textarea></p>'
            f'<p><label for="dmun">Municípios no Querido Diário (Cidade/UF, um por linha, até {MAX_MUNICIPIOS})</label><br><textarea id="dmun" name="municipios" rows="3" cols="40">{e(chr(10).join(m["nome"] for m in c.get("municipios", [])))}</textarea></p>'
            f'<p><label for="dpag">Páginas ou PDFs de diários fora do Querido Diário (endereço https, um por linha, até {MAX_PAGINAS})</label><br><textarea id="dpag" name="paginas" rows="3" cols="40">{e(chr(10).join(c.get("paginas", [])))}</textarea></p>'
            '<button type="submit">Salvar diários</button></form>' + (f'<p class="meta" role="status">{e(est)}</p>' if est else ""))
