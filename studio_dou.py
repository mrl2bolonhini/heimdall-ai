#!/usr/bin/env python3
"""Diário Oficial da União por palavras-chave (INLABS, da Imprensa Nacional), na área Cidadania do Studio Miner.

O INLABS entrega, depois de um cadastro gratuito, o XML de cada edição do DOU (seções 1, 2 e 3 e edições extras). Cada pessoa cria o próprio cadastro no
site do INLABS e informa o login e a senha em Ajustes; ficam no cofre cifrado dela e só servem para baixar as edições. Todos os dias o Miner baixa as edições novas,
procura as palavras-chave da pessoa (e, se ela quiser, o nome completo e os processos que acompanha) e avisa cada publicação encontrada, com o tipo do ato,
o órgão, a seção e um trecho. O login do INLABS é instável: uma falha de entrada vira aviso de consulta incompleta, nunca perda de edição (a próxima rodada retoma).
"""
import html
import io
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

import studio_cidadania as cid
import studio_djen as djen
import studio_miner_dados as dados

CHAVE, ROTULO, INTERVALO = "dou", "Diário Oficial da União", timedelta(hours=20)
BASE = "https://inlabs.in.gov.br"
SECOES = {"DO1": "Seção 1", "DO2": "Seção 2", "DO3": "Seção 3", "DO1E": "Seção 1, edição extra", "DO2E": "Seção 2, edição extra", "DO3E": "Seção 3, edição extra"}
MAX_DIAS = 5
MAX_ZIP = 120_000_000
MAX_XML = 30_000_000
MAX_ALERTAS_POR_RODADA = 40
# (padrão no tipo do ato sem acento, o que significa)
ATOS = [
    (r"edital", "Convocação ou aviso público com regras e prazos (concurso, licitação, consulta pública, leilão)."),
    (r"portaria", "Ato administrativo que organiza serviço, nomeia, designa ou decide sobre pessoas e processos."),
    (r"decreto", "Ato do chefe do Executivo com força normativa ou de nomeação."),
    (r"resolucao|instrucao normativa", "Norma de órgão ou agência que regula uma atividade."),
    (r"extrato", "Resumo de contrato, convênio ou ato, publicado para valer perante terceiros."),
    (r"aviso", "Comunicado oficial, em geral com prazo para manifestação."),
    (r"despacho", "Decisão administrativa sobre um processo."),
    (r"retifica", "Correção de ato publicado antes: confira se muda prazo ou valor."),
]


def configurado(c: dict) -> bool:
    return bool(c.get("palavras") or c.get("usar_nome") or c.get("usar_processos")) and cid.tem_segredo("inlabs_email") and cid.tem_segredo("inlabs_senha")


def salvar(campos: dict) -> str:
    c = cid.cfg(CHAVE)
    c["palavras"] = cid.lista(campos.get("palavras", ""))
    c["usar_nome"] = campos.get("usar_nome") == "1"
    c["usar_processos"] = campos.get("usar_processos") == "1"
    secoes = [s for s in campos.get("secoes", "DO1,DO2,DO3").split(",") if s in SECOES]
    c["secoes"] = secoes or ["DO1", "DO2", "DO3"]
    email, senha = campos.get("inlabs_email", "").strip(), campos.get("inlabs_senha", "")
    if email and not re.match(r"^[^@\s]{1,64}@[^@\s]{1,120}$", email):
        raise dados.ErroMiner("Informe o e-mail do cadastro do INLABS.")
    novos = {}
    if email:
        novos["inlabs_email"] = email
    if senha:
        novos["inlabs_senha"] = senha
    if novos:
        cid.guardar_segredos(novos)
    cid.salvar_cfg(CHAVE, c)
    return "Diário Oficial da União salvo."


def termos(c: dict) -> list:
    t = list(c.get("palavras", []))
    base = djen.configuracao()
    if c.get("usar_nome") and base["nome"]:
        t.append(base["nome"])
    if c.get("usar_processos"):
        for n in base["processos"]:
            t.extend([djen.mascara_cnj(n), n])
    return t


def entrar(c, urlopen=None, dormir=None) -> str:
    """Cookie de sessão do INLABS."""
    corpo = urllib.parse.urlencode({"email": cid.segredo("inlabs_email"), "password": cid.segredo("inlabs_senha")}).encode()
    _, _, cab = cid.http(BASE + "/logar.php", {"Content-Type": "application/x-www-form-urlencoded"}, corpo, "POST", urlopen, nome="O INLABS", seguir=False, dormir=dormir)
    for ck in cab.get("_cookies", []):
        if ck.lower().startswith("inlabs_session_cookie="):
            return ck
    raise cid.ErroFonte("O INLABS não aceitou o login. Confira o e-mail e a senha do cadastro (o login do INLABS é instável: a próxima rodada tenta de novo).")


def baixar(dia: date, secao: str, cookie: str, urlopen=None, dormir=None):
    """Bytes do zip da edição, ou None se o INLABS não tem a edição daquele dia e seção."""
    d = dia.isoformat()
    url = f"{BASE}/index.php?p={d}&dl={d}-{secao}.zip"
    try:
        _, corpo, _ = cid.http(url, {"Cookie": cookie}, urlopen=urlopen, nome="O INLABS", limite=MAX_ZIP, timeout=120, dormir=dormir)
    except cid.ErroFonte as ex:
        if "erro 404" in str(ex):
            return None
        raise
    return corpo if corpo[:2] == b"PK" else None


def artigos(zip_bytes: bytes):
    """Itens {id, secao, tipo, orgao, data, ementa, texto, identifica} de todos os XML do zip."""
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return
    for nome in z.namelist():
        if not nome.lower().endswith(".xml"):
            continue
        info = z.getinfo(nome)
        if info.file_size > MAX_XML:
            continue
        bruto = z.read(nome)
        if b"<!ENTITY" in bruto or b"<!DOCTYPE" in bruto:   # entidades podem expandir sem limite: o INLABS não as usa
            continue
        try:
            raiz = ET.fromstring(bruto)
        except ET.ParseError:
            continue
        for a in raiz.iter("article"):
            corpo = a.find("body")
            f = lambda t: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", (corpo.findtext(t) or "") if corpo is not None else ""))).strip()   # noqa: E731
            yield {"id": a.get("idMateria") or a.get("id") or cid.hash_curto(nome, a.get("name")), "secao": a.get("pubName", ""), "tipo": a.get("artType", "") or a.get("name", ""),
                   "orgao": (a.get("artCategory") or "").split("/")[-1].strip() or (a.get("artCategory") or ""), "data": a.get("pubDate", ""), "pagina": a.get("numberPage", ""),
                   "identifica": f("Identifica"), "ementa": f("Ementa"), "texto": " ".join(x for x in (f("Titulo"), f("Ementa"), f("Texto")) if x)}


def significado(tipo: str, identifica: str) -> str:
    t = cid.sem_acento(f"{tipo} {identifica}")
    for padrao, sig in ATOS:
        if re.search(padrao, t):
            return sig
    return "Publicação oficial que cita um dos seus termos."


def alerta(it: dict, achados: list) -> dict:
    secao = SECOES.get(it["secao"], it["secao"] or "DOU")
    base = f"{it['tipo'] or 'Publicação'} no Diário Oficial da União ({secao}" + (f", {it['orgao']}" if it["orgao"] else "") + f"), de {it['data']}" + (f", página {it['pagina']}" if it["pagina"] else "") + "."
    partes = [base, significado(it["tipo"], it["identifica"]), "Encontrada pelo termo: " + ", ".join(achados[:3]) + ".",
              "O que fazer: leia a publicação no site oficial (in.gov.br) e confira se há prazo, convocação ou obrigação para você.",
              "Trecho: " + cid.trecho(it["texto"], achados[0], 120)]
    return {"id": f"dou:{it['id']}", "titulo": f"Diário Oficial da União: {achados[0][:40]}", "nivel": "alto" if re.search(r"edital|convoca|intima|cita", cid.sem_acento(it["tipo"] + " " + it["identifica"])) else "medio",
            "resumo": " ".join(partes)[:1800], "fonte": "diarios"}


def executar(c) -> dict:
    conf = cid.cfg(CHAVE)
    alvo = termos(conf)
    try:
        ultimo = date.fromisoformat(cid._ler("dou_dia"))
    except ValueError:
        ultimo = None
    inicio = max(ultimo + timedelta(days=1) if ultimo else c.hoje - timedelta(days=1), c.hoje - timedelta(days=MAX_DIAS))
    cookie = entrar(c, c.urlopen, c.dormir)
    novos, lidas, erros, avanco = 0, 0, [], None
    dia = inicio
    while dia <= c.hoje:
        for sec in conf.get("secoes", ["DO1", "DO2", "DO3"]):
            try:
                z = baixar(dia, sec, cookie, c.urlopen, c.dormir)
            except cid.ErroFonte as ex:
                erros.append(str(ex))
                break
            if not z:
                continue
            avanco = dia
            for it in artigos(z):
                lidas += 1
                ach = cid.achadas(it["texto"] + " " + it["identifica"], alvo)
                if ach and novos < MAX_ALERTAS_POR_RODADA:
                    novos += c.avisar(alerta(it, ach))
        if erros:
            break
        dia += timedelta(days=1)
    if not erros:
        cid._gravar(dou_dia=(avanco if avanco and avanco == c.hoje else c.hoje - timedelta(days=1)).isoformat())
    return {"novos": novos, "erros": erros, "resumo": f"{lidas} publicação(ões) lida(s)"}


def formulario(csrf: str) -> str:
    c = cid.cfg(CHAVE)
    e = lambda t: html.escape(str(t), quote=True)   # noqa: E731
    marca = lambda k: " checked" if c.get(k) else ""   # noqa: E731
    cofre = "O login e a senha estão guardados no cofre; deixe a senha em branco para mantê-la." if cid.tem_segredo("inlabs_senha") else "Crie o cadastro gratuito no INLABS, no site da Imprensa Nacional, e informe o login e a senha."
    est = cid.estado(sys.modules[__name__])
    return (f'<h2 id="h-dou">Diário Oficial da União</h2><form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}">'
            f'<p><label for="dpal">Termos a procurar (um por linha: nome de empresa, expressão, número de processo)</label><br><textarea id="dpal" name="palavras" rows="4" cols="40">{e(chr(10).join(c.get("palavras", [])))}</textarea></p>'
            f'<p><input id="dnome" type="checkbox" name="usar_nome" value="1"{marca("usar_nome")}> <label for="dnome">Procurar também o meu nome completo</label></p>'
            f'<p><input id="dproc" type="checkbox" name="usar_processos" value="1"{marca("usar_processos")}> <label for="dproc">Procurar também os números dos processos que acompanho</label></p>'
            f'<p><label for="dmail">E-mail do cadastro no INLABS</label><br><input id="dmail" name="inlabs_email" type="email" autocomplete="off" value="{e(cid.segredo("inlabs_email") if cid.tem_segredo("inlabs_email") else "")}"></p>'
            f'<p><label for="dsen">Senha do INLABS</label><br><input id="dsen" name="inlabs_senha" type="password" autocomplete="new-password"></p><p>{e(cofre)}</p>'
            '<button type="submit">Salvar Diário Oficial</button></form>' + (f'<p class="meta" role="status">{e(est)}</p>' if est else ""))
