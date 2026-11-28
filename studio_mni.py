#!/usr/bin/env python3
"""MNI (Modelo Nacional de Interoperabilidade, webservice dos tribunais) na área Cidadania do Studio Miner: andamentos com a credencial do próprio advogado.

Alguns tribunais liberam o webservice MNI para advogados, com o CPF e a senha do sistema do tribunal (consultarProcesso). É o modo cliente local: roda só neste computador,
a credencial fica no cofre cifrado da pessoa e nunca aparece em tela, alerta ou registro; as consultas vão direto ao tribunal (endereço https de domínio .jus.br que a pessoa
informa, o do WSDL do tribunal). Para cada processo acompanhado cujo tribunal tenha endereço MNI cadastrado, o Miner lê as movimentações e avisa as novas, com o que
significam. Se o tribunal recusar a credencial, o Miner pára de tentar aquele tribunal até a pessoa salvar a credencial de novo, para não bloquear a conta do advogado.
Não serve para o gov.br e não usa certificado digital (o acesso por certificado fica para quando o tribunal exigir).
"""
import html
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

import studio_cidadania as cid
import studio_datajud as datajud
import studio_djen as djen
import studio_miner_dados as dados

CHAVE, ROTULO, INTERVALO = "mni", "Webservice dos tribunais (MNI)", timedelta(hours=20)
MAX_TRIBUNAIS = 12
MAX_NOVOS_NO_ALERTA = 5
NS = "http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
NS_TIPOS = "http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2"
_SEM_PERMISSAO = re.compile(r"sigilo|segredo de justica|sem permissao|nao tem acesso ao processo|nivel de acesso", re.I)
_AUTENTICACAO = re.compile(r"senha|autentic|credencial|login|usuario|cpf|acesso negado|nao autorizado", re.I)


def configurado(c: dict) -> bool:
    return bool(c.get("tribunais")) and cid.tem_segredo("mni_cpf") and cid.tem_segredo("mni_senha") and bool(djen.configuracao()["processos"])


def salvar(campos: dict) -> str:
    c = cid.cfg(CHAVE)
    tribs = []
    for linha in cid.lista(campos.get("tribunais", ""), minimo=12, maximo_item=300, maximo=MAX_TRIBUNAIS, o_que="tribunais"):
        alias, _, url = linha.partition("=")
        alias = alias.strip().lower().replace("_", "-")
        if not re.fullmatch(r"[a-z0-9-]{3,12}", alias) or not url.strip():
            raise dados.ErroMiner(f"Use o formato sigla=endereço, por exemplo tjsp=https://exemplo.jus.br/mni: {linha[:30]}.")
        tribs.append({"alias": alias, "endpoint": cid.validar_url(url.strip(), ("jus.br",))})
    c["tribunais"] = tribs
    cpf = re.sub(r"\D", "", campos.get("mni_cpf", ""))
    senha = campos.get("mni_senha", "")
    novos = {}
    if cpf:
        if len(cpf) not in (11, 14):
            raise dados.ErroMiner("Informe o CPF (11 dígitos) ou o CNPJ (14 dígitos) do cadastro no tribunal.")
        novos["mni_cpf"] = cpf
    if senha:
        novos["mni_senha"] = senha
    if novos:
        cid.guardar_segredos(novos)
        for t in c.get("tribunais", []):   # credencial nova: libera os tribunais que estavam em pausa
            djen._gravar(**{"mni_pausa_" + t["alias"]: ""})
    cid.salvar_cfg(CHAVE, c)
    return "MNI salvo."


def envelope(cpf: str, senha: str, numero: str) -> bytes:
    return (f'<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="{NS}" xmlns:tip="{NS_TIPOS}">'
            f'<soapenv:Body><ser:consultarProcesso><tip:idConsultante>{escape(cpf)}</tip:idConsultante><tip:senhaConsultante>{escape(senha)}</tip:senhaConsultante>'
            f'<tip:numeroProcesso>{escape(numero)}</tip:numeroProcesso><tip:movimentos>true</tip:movimentos><tip:incluirCabecalho>true</tip:incluirCabecalho>'
            '<tip:incluirDocumentos>false</tip:incluirDocumentos></ser:consultarProcesso></soapenv:Body></soapenv:Envelope>').encode("utf-8")


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _quando(s: str):
    try:
        return datetime.strptime((s or "")[:14].ljust(14, "0"), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def interpretar(corpo: bytes) -> dict:
    """{ok, mensagem, classe, orgao, movimentos[{quando, nome}]} de uma resposta consultarProcesso, tolerando prefixos de namespace diferentes."""
    if b"<!ENTITY" in corpo or b"<!DOCTYPE" in corpo:
        raise cid.ErroFonte("O tribunal respondeu num formato não aceito.")
    try:
        raiz = ET.fromstring(corpo)
    except ET.ParseError:
        raise cid.ErroFonte("O tribunal respondeu num formato inesperado (não é XML).")
    r = {"ok": True, "mensagem": "", "classe": "", "orgao": "", "movimentos": []}
    for el in raiz.iter():
        n = _local(el.tag)
        if n == "consultarProcessoResposta":
            r["ok"] = str(el.get("sucesso", "true")).lower() == "true"
            r["mensagem"] = el.get("mensagem", "") or ""
        elif n == "faultstring" and el.text:
            r["ok"], r["mensagem"] = False, el.text
        elif n == "dadosBasicos":
            r["classe"] = r["classe"] or el.get("classeProcessual", "")
        elif n == "orgaoJulgador":
            r["orgao"] = r["orgao"] or el.get("nomeOrgao", "")
        elif n == "movimento":
            q = _quando(el.get("dataHora", ""))
            if not q:
                continue
            desc = ""
            for f in el.iter():
                fn = _local(f.tag)
                if fn == "movimentoLocal" and f.get("descricao"):
                    desc = f.get("descricao")
                    break
                if fn == "complemento" and f.text and not desc:
                    desc = f.text.strip()
                if fn == "movimentoNacional" and f.get("codigoNacional") and not desc:
                    desc = f"Movimento nacional {f.get('codigoNacional')}"
            r["movimentos"].append({"quando": q, "nome": cid.limpo(desc or "Movimento", 160)})
    r["movimentos"].sort(key=lambda m: m["quando"], reverse=True)
    return r


def consultar(endpoint: str, numero: str, c) -> dict:
    corpo = envelope(cid.segredo("mni_cpf"), cid.segredo("mni_senha"), numero)
    try:
        _, resp, _ = cid.http(endpoint, {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'}, corpo, "POST", c.urlopen, nome="O webservice do tribunal", pausa=2.0, dormir=c.dormir)
    except cid.ErroFonte as ex:
        raise cid.ErroFonte(str(ex))
    return interpretar(resp)


def alerta(numero: str, tribunal: str, r: dict, novos: list, inicio: bool) -> dict:
    significa, fazer, nivel = djen.classificar({"tipo": "", "documento": "", "classe": r["classe"], "texto": " ".join(m["nome"] for m in novos)})
    lista = "; ".join(f"{m['nome']} ({m['quando']:%d/%m/%Y})" for m in novos[:MAX_NOVOS_NO_ALERTA]) + ("…" if len(novos) > MAX_NOVOS_NO_ALERTA else "")
    onde = ", ".join(x for x in (tribunal.upper(), r["orgao"]) if x)
    if inicio:
        resumo = (f"Acompanhamento pelo webservice do tribunal iniciado no processo {djen.mascara_cnj(numero)} ({onde}). "
                  + (f"Último andamento: {novos[0]['nome']} em {novos[0]['quando']:%d/%m/%Y}. " if novos else "Ainda não há movimentações. ") + "A partir de agora, cada movimentação nova vira aviso.")
        return {"id": f"mni-inicio:{numero}", "titulo": f"Acompanhamento pelo tribunal iniciado ({tribunal.upper()})", "nivel": "medio", "fonte": "justica", "resumo": resumo}
    resumo = (f"{len(novos)} movimentação(ões) nova(s) no processo {djen.mascara_cnj(numero)} ({onde}), lida(s) direto do webservice do tribunal: {lista}. {significa} "
              f"O prazo oficial conta da intimação (DJEN ou Domicílio Judicial Eletrônico). O que fazer: {fazer}")
    return {"id": f"mni:{numero}:{novos[0]['quando']:%Y%m%d%H%M%S}", "titulo": f"Movimentação no processo ({tribunal.upper()})", "nivel": "medio" if nivel == "medio" else "alto", "fonte": "justica", "resumo": resumo[:1800]}


def executar(c) -> dict:
    conf = cid.cfg(CHAVE)
    por_alias = {t["alias"]: t["endpoint"] for t in conf.get("tribunais", [])}
    novos, erros, feitos = 0, [], 0
    for numero in djen.configuracao()["processos"]:
        alias = datajud.indice(numero)
        endpoint = por_alias.get(alias)
        if not endpoint:
            continue
        if djen._ler("mni_pausa_" + alias):
            erros.append(f"O tribunal {alias.upper()} recusou a credencial antes; salve a credencial de novo nos Ajustes para voltar a consultar.")
            continue
        try:
            r = consultar(endpoint, numero, c)
        except cid.ErroFonte as ex:
            erros.append(str(ex))
            continue
        if not r["ok"]:
            msg = cid.limpo(r["mensagem"], 120)
            for seg in (cid.segredo("mni_cpf"), cid.segredo("mni_senha")):
                if seg:
                    msg = msg.replace(seg, "***")
            if _AUTENTICACAO.search(cid.sem_acento(msg)) and not _SEM_PERMISSAO.search(cid.sem_acento(msg)):
                djen._gravar(**{"mni_pausa_" + alias: "1"})
                erros.append(f"O tribunal {alias.upper()} recusou a credencial ({msg}). O Miner pára de tentar para não bloquear a sua conta; confira a credencial e salve de novo.")
            else:
                erros.append(f"O tribunal {alias.upper()} recusou a consulta do processo {djen.mascara_cnj(numero)}: {msg or 'sem motivo informado'}.")
            continue
        feitos += 1
        marca = djen._ler("mni:" + numero)
        topo = r["movimentos"][0]["quando"] if r["movimentos"] else None
        if not marca:
            novos += c.avisar(alerta(numero, alias, r, r["movimentos"][:1], True))
        else:
            base = datetime.fromisoformat(marca)
            lista = [m for m in r["movimentos"] if m["quando"] > base]
            if lista:
                novos += c.avisar(alerta(numero, alias, r, lista, False))
        djen._gravar(**{"mni:" + numero: (topo or datetime(1970, 1, 1)).isoformat()})
    return {"novos": novos, "erros": erros, "parcial": feitos > 0, "resumo": f"{feitos} processo(s) consultado(s)"}


def formulario(csrf: str) -> str:
    c = cid.cfg(CHAVE)
    e = lambda t: html.escape(str(t), quote=True)   # noqa: E731
    cofre = "A credencial está no cofre deste computador; deixe a senha em branco para mantê-la." if cid.tem_segredo("mni_senha") else "Informe o CPF ou CNPJ e a senha do seu cadastro no sistema do tribunal."
    est = cid.estado(sys.modules[__name__])
    return (f'<h2 id="h-mni">Webservice dos tribunais (MNI)</h2><form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}">'
            f'<p><label for="mtrib">Tribunais com MNI liberado (sigla=endereço https do webservice, domínio jus.br, um por linha)</label><br><textarea id="mtrib" name="tribunais" rows="3" cols="40">{e(chr(10).join(t["alias"] + "=" + t["endpoint"] for t in c.get("tribunais", [])))}</textarea></p>'
            '<p><label for="mcpf">CPF ou CNPJ do cadastro no tribunal</label><br><input id="mcpf" name="mni_cpf" type="text" inputmode="numeric" autocomplete="off"></p>'
            f'<p><label for="msen">Senha do cadastro no tribunal</label><br><input id="msen" name="mni_senha" type="password" autocomplete="new-password"></p><p>{e(cofre)}</p>'
            '<button type="submit">Salvar MNI</button></form>' + (f'<p class="meta" role="status">{e(est)}</p>' if est else ""))
