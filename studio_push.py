#!/usr/bin/env python3
"""Push dos tribunais por e-mail: assistente de cadastro e leitura dos e-mails recebidos, na área Cidadania do Studio Miner.

Os sistemas Push dos tribunais (STF, STJ, TST, TRFs, TRTs e alguns tribunais de justiça) mandam por e-mail cada andamento dos processos cadastrados: é a fonte
de aviso mais confiável e, no STF, a única via automática. O cadastro é feito pela própria pessoa no site do tribunal; o Miner mostra, para cada processo
acompanhado, onde cadastrar, e depois lê (somente leitura, no mesmo Gmail que o monitor de e-mail oficial já lê) os e-mails desses sistemas e os transforma
em alertas com o que o andamento significa. Links dos e-mails nunca são seguidos nem repetidos.
O tribunal pelo número do processo vem dos campos J e TR do número único. Nada é enviado a terceiros: este módulo só interpreta texto.
"""
import re

import studio_datajud as datajud
import studio_djen as djen

# chave -> (nome do sistema, domínio do site do tribunal, observação)
SISTEMAS = {
    "stf": ("STF Push", "stf.jus.br", "É a única forma automática de acompanhar processo do STF."),
    "stj": ("STJ Push (Acompanhamento processual)", "stj.jus.br", ""),
    "tst": ("TST Push", "tst.jus.br", ""),
    "trf": ("Push do TRF", "jus.br", "Cada Tribunal Regional Federal tem o seu sistema; procure Push ou Acompanhamento por e-mail no site do TRF indicado."),
    "trt": ("PJe Push do TRT", "jus.br", "Cada Tribunal Regional do Trabalho tem o seu; procure PJe Push no site do TRT indicado."),
    "esaj": ("Acompanhamento por e-mail do e-SAJ", "tjsp.jus.br", "Não cobre processos que migraram para o eproc."),
    "tjrs": ("Push do TJRS", "tjrs.jus.br", ""),
    "tjrj": ("Push do TJRJ", "tjrj.jus.br", ""),
}
TJ_SISTEMA = {26: "esaj", 21: "tjrs", 19: "tjrj"}
_NUMERO = re.compile(r"\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b")
_SIGLA_DOMINIO = re.compile(r"(?:^|\.)((?:tj|trf|trt|tre|stj|stf|tst|tse|stm)[a-z0-9]*)\.jus\.br$|(?:^|\.)((?:stj|stf|tst|tse|stm))\.jus\.br$")


def sistema_do_processo(numero: str) -> dict:
    """Onde cadastrar o Push de um processo, pelo número único. {chave, nome, tribunal, site, observacao} ou {} se não há Push conhecido."""
    d = re.sub(r"\D", "", numero or "")
    if len(d) != 20:
        return {}
    j, tr = d[13], int(d[14:16])
    alias = datajud.indice(d).upper().replace("_", "-") or ("STF" if j == "1" else "")
    chave = ""
    if j == "1":
        chave = "stf"
    elif j == "3" and tr == 0:
        chave = "stj"
    elif j == "5":
        chave = "tst" if tr == 0 else "trt"
    elif j == "4" and 1 <= tr <= 6:
        chave = "trf"
    elif j == "8":
        chave = TJ_SISTEMA.get(tr, "")
    if not chave:
        return {}
    nome, site, obs = SISTEMAS[chave]
    site = {"trf": f"trf{tr}.jus.br", "trt": f"trt{tr}.jus.br"}.get(chave, site)
    return {"chave": chave, "nome": nome, "tribunal": alias or chave.upper(), "site": site, "observacao": obs}


def orientacoes(numeros: list, cadastrados: list) -> list:
    """Uma linha por processo: onde cadastrar o Push (ou que não há Push conhecido) e se já foi cadastrado."""
    saida = []
    for n in numeros:
        s = sistema_do_processo(n)
        ja = n in cadastrados
        if s:
            saida.append({"numero": n, "texto": f"{djen.mascara_cnj(n)}: {s['nome']} ({s['tribunal']}), no site {s['site']}. {s['observacao']}".strip(), "cadastrado": ja, "tem_push": True})
        else:
            saida.append({"numero": n, "texto": f"{djen.mascara_cnj(n)}: este tribunal não tem Push conhecido; o Miner acompanha pelo DJEN e pelo DataJud.", "cadastrado": False, "tem_push": False})
    return saida


def tribunal_do_remetente(de: str) -> str:
    m = re.search(r"@([a-z0-9.-]+)", (de or "").lower())
    dom = m.group(1) if m else ""
    m = _SIGLA_DOMINIO.search(dom)
    return (m.group(1) or m.group(2)).upper() if m else ""


def analisar(de: str, assunto: str, corpo: str):
    """Se o e-mail parece de um sistema Push de tribunal (remetente .jus.br e número de processo válido no texto), devolve os dados do andamento; senão None."""
    if not re.search(r"@[a-z0-9.-]*\.jus\.br\b", (de or "").lower()):
        return None
    texto = f"{assunto} {corpo}"
    numeros = []
    for m in _NUMERO.finditer(texto):
        n = djen.numero_cnj_valido(m.group(0))
        if n and n not in numeros:
            numeros.append(n)
    if not numeros:
        return None
    return {"numero": numeros[0], "outros": numeros[1:3], "tribunal": tribunal_do_remetente(de) or (datajud.indice(numeros[0]).upper() or "tribunal"),
            "assunto": re.sub(r"\s+", " ", assunto or "").strip()[:120], "trecho": re.sub(r"\s+", " ", corpo or "").strip()[:djen.TRECHO]}


def alerta(p: dict, mid: str) -> dict:
    significa, fazer, nivel = djen.classificar({"tipo": "", "documento": "", "classe": "", "texto": f"{p['assunto']} {p['trecho']}"})
    partes = [f"Andamento no processo {djen.mascara_cnj(p['numero'])} ({p['tribunal']}), avisado pelo sistema Push do tribunal.", significa,
              "Encontrado pelo e-mail do tribunal que você cadastrou, com remetente oficial confirmado." ]
    if p["outros"]:
        partes.append("O e-mail cita também outros processos: " + ", ".join(djen.mascara_cnj(n) for n in p["outros"]) + ".")
    partes.append("O Push avisa o andamento, mas o prazo oficial conta da intimação (DJEN ou Domicílio Judicial Eletrônico).")
    partes.append("O que fazer: " + fazer + " Abra o processo pelo site oficial digitando o endereço; não use links do e-mail.")
    if p["trecho"]:
        partes.append("Trecho: " + p["trecho"])
    return {"id": "push:" + mid.lower()[:200], "titulo": f"Andamento por e-mail do tribunal ({p['tribunal']})", "resumo": " ".join(partes)[:800], "nivel": nivel, "fonte": "justica"}
