#!/usr/bin/env python3
"""Licitações e sanções na área Cidadania do Studio Miner.

1. PNCP (Portal Nacional de Contratações Públicas, API pública sem chave): todos os dias o Miner lê as contratações publicadas desde a última rodada, nas
   modalidades que a pessoa escolher (e nas UFs, se quiser limitar), e avisa as que citam as palavras-chave dela no objeto, com órgão, valor estimado e o fim do
   prazo de propostas ("Prazo: dd/mm/aaaa": ao aceitar o item, vira evento).
2. Portal da Transparência (chave gratuita da própria pessoa, no cofre): confere, para os CNPJs que a pessoa lista (fornecedores, clientes, parceiros), se
   há sanção nova nos cadastros CEIS (empresas inidôneas e suspensas) e CNEP (Lei Anticorrupção). Só pessoas jurídicas: nada é consultado sobre pessoas físicas.
"""
import html
import re
import sys
import urllib.parse
from datetime import date, timedelta

import studio_cidadania as cid
import studio_miner_dados as dados

CHAVE, ROTULO, INTERVALO = "licitacoes", "Licitações e sanções", timedelta(hours=20)
PNCP = "https://pncp.gov.br/api/consulta/v1"
TRANSP = "https://api.portaldatransparencia.gov.br/api-de-dados"
MODALIDADES = {1: "Leilão eletrônico", 2: "Diálogo competitivo", 3: "Concurso", 4: "Concorrência eletrônica", 5: "Concorrência presencial", 6: "Pregão eletrônico",
               7: "Pregão presencial", 8: "Dispensa", 9: "Inexigibilidade", 10: "Manifestação de interesse", 11: "Pré-qualificação", 12: "Credenciamento", 13: "Leilão presencial"}
MODALIDADES_PADRAO = [1, 2, 3, 4, 6, 8, 12, 13]
MAX_PAGINAS = 10
TAMANHO = 50
MAX_CNPJ = 20
MAX_ALERTAS = 40


def configurado(c: dict) -> bool:
    return bool(c.get("palavras")) or (bool(c.get("cnpjs")) and cid.tem_segredo("transparencia_chave"))


def cnpj_valido(t: str) -> str:
    d = re.sub(r"\D", "", t or "")
    if len(d) != 14 or len(set(d)) == 1:
        return ""
    def dv(base, pesos):
        r = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return "0" if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(d[:12], p1)
    d2 = dv(d[:12] + d1, [6] + p1)
    return d if d[12:] == d1 + d2 else ""


def salvar(campos: dict) -> str:
    import studio_djen
    c = cid.cfg(CHAVE)
    c["palavras"] = cid.lista(campos.get("palavras", ""))
    mods = [int(m) for m in re.split(r"[,\s]+", campos.get("modalidades", "")) if m.isdigit() and int(m) in MODALIDADES]
    c["modalidades"] = sorted(set(mods)) or MODALIDADES_PADRAO
    ufs = [u.upper() for u in re.split(r"[,\s;]+", campos.get("ufs", "")) if u]
    if any(u not in studio_djen.UFS for u in ufs):
        raise dados.ErroMiner("Use siglas de UF com duas letras, separadas por vírgula.")
    c["ufs"] = sorted(set(ufs))
    cnpjs = []
    for t in cid.lista(campos.get("cnpjs", ""), minimo=14, maximo_item=18, maximo=MAX_CNPJ, o_que="CNPJs"):
        v = cnpj_valido(t)
        if not v:
            raise dados.ErroMiner(f"CNPJ inválido: {t[:20]}.")
        if v not in cnpjs:
            cnpjs.append(v)
    c["cnpjs"] = cnpjs
    chave = campos.get("transparencia_chave", "").strip()
    if chave:
        if not re.fullmatch(r"[A-Za-z0-9-]{16,64}", chave):
            raise dados.ErroMiner("A chave do Portal da Transparência deve ter de 16 a 64 letras, números ou hífens.")
        cid.guardar_segredos({"transparencia_chave": chave})
    cid.salvar_cfg(CHAVE, c)
    return "Licitações e sanções salvas."


def contratacoes(modalidade: int, ini: date, fim: date, uf: str, c) -> list:
    saida = []
    for pagina in range(1, MAX_PAGINAS + 1):
        q = {"dataInicial": ini.strftime("%Y%m%d"), "dataFinal": fim.strftime("%Y%m%d"), "codigoModalidadeContratacao": modalidade, "pagina": pagina, "tamanhoPagina": TAMANHO}
        if uf:
            q["uf"] = uf
        r = cid.json_de(f"{PNCP}/contratacoes/publicacao?{urllib.parse.urlencode(q)}", urlopen=c.urlopen, dormir=c.dormir, nome="O PNCP")
        lote = [d for d in (r.get("data") or []) if isinstance(d, dict)]
        saida.extend(lote)
        if len(lote) < TAMANHO or pagina >= int(r.get("totalPaginas") or 1):
            break
    return saida


def _dia(s) -> date:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def alerta_pncp(d: dict, palavra: str) -> dict:
    org = (d.get("orgaoEntidade") or {}).get("razaoSocial") or "órgão não informado"
    uf = (d.get("unidadeOrgao") or {}).get("ufSigla") or ""
    fim = _dia(d.get("dataEncerramentoProposta"))
    valor = d.get("valorTotalEstimado")
    partes = [f"{d.get('modalidadeNome') or 'Contratação'} publicada no PNCP por {org}{' (' + uf + ')' if uf else ''}: {cid.limpo(d.get('objetoCompra'), 300)}",
              f"Encontrada pelo termo: {palavra}.",
              (f"Valor estimado: R$ {float(valor):,.2f}.".replace(",", "X").replace(".", ",").replace("X", ".") if isinstance(valor, (int, float)) and valor else "Valor estimado não informado."),
              "O que significa: o órgão abriu a disputa e a participação tem prazo; propostas fora do prazo não entram. O que fazer: abra o edital no portal do PNCP e confira requisitos, documentos e o fim do prazo."]
    if fim:
        partes.append(f"Prazo: {cid.data_br(fim)}")
    return {"id": f"pncp:{d.get('numeroControlePNCP')}", "titulo": f"Licitação: {cid.limpo(d.get('objetoCompra'), 60)}", "nivel": "alto" if fim and 0 <= (fim - date.today()).days <= 5 else "medio",
            "resumo": " ".join(partes)[:1800], "fonte": "licitacoes"}


def sancoes(cnpj: str, c) -> list:
    cab = {"chave-api-dados": cid.segredo("transparencia_chave")}
    achados = []
    for cadastro in ("ceis", "cnep"):
        r = cid.json_de(f"{TRANSP}/{cadastro}?{urllib.parse.urlencode({'codigoSancionado': cnpj, 'pagina': 1})}", cab, urlopen=c.urlopen, dormir=c.dormir, nome="O Portal da Transparência", pausa=1.2)
        for d in (r if isinstance(r, list) else []):
            if isinstance(d, dict) and d.get("id"):
                achados.append((cadastro.upper(), d))
    return achados


def alerta_sancao(cad: str, d: dict, cnpj: str) -> dict:
    s = d.get("sancionado") or {}
    tipo = (d.get("tipoSancao") or {}).get("descricaoResumida") or "sanção"
    org = (d.get("orgaoSancionador") or {}).get("nome") or "órgão não informado"
    quem = s.get("nome") or cnpj
    return {"id": f"sancao:{cad}:{d['id']}", "titulo": f"Sanção no {cad}: {str(quem)[:50]}", "nivel": "alto", "fonte": "licitacoes",
            "resumo": f"O CNPJ {cnpj} ({quem}) tem registro no {cad} do Portal da Transparência: {tipo}, aplicada por {org}, com início em {str(d.get('dataInicioSancao') or 'data não informada')[:10]} "
                      f"e fim em {str(d.get('dataFimSancao') or 'data não informada')[:10]}. O que significa: empresa sancionada pode ficar impedida de contratar com o poder público ou ter outras restrições. "
                      "O que fazer: confira o registro no portal e, se você contrata ou contratou essa empresa, avalie o risco com seu jurídico."}


def executar(c) -> dict:
    conf = cid.cfg(CHAVE)
    novos, erros, lidas = 0, [], 0
    if conf.get("palavras"):
        try:
            ultimo = date.fromisoformat(cid._ler("lic_dia"))
        except ValueError:
            ultimo = None
        ini = (ultimo - timedelta(days=1)) if ultimo else c.hoje - timedelta(days=2)
        for m in conf.get("modalidades", MODALIDADES_PADRAO):
            for uf in conf.get("ufs") or [""]:
                try:
                    for d in contratacoes(m, ini, c.hoje, uf, c):
                        lidas += 1
                        ach = cid.achadas(str(d.get("objetoCompra", "")), conf["palavras"])
                        if ach and d.get("numeroControlePNCP") and novos < MAX_ALERTAS:
                            novos += c.avisar(alerta_pncp(d, ach[0]))
                except cid.ErroFonte as ex:
                    erros.append(str(ex))
                    break
            if erros:
                break
        if not erros:
            cid._gravar(lic_dia=c.hoje.isoformat())
    if conf.get("cnpjs") and cid.tem_segredo("transparencia_chave"):
        for cnpj in conf["cnpjs"]:
            try:
                for cad, d in sancoes(cnpj, c):
                    novos += c.avisar(alerta_sancao(cad, d, cnpj))
            except cid.ErroFonte as ex:
                erros.append(str(ex))
                break
    return {"novos": novos, "erros": erros, "resumo": f"{lidas} contratação(ões) lida(s)"}


def formulario(csrf: str) -> str:
    c = cid.cfg(CHAVE)
    e = lambda t: html.escape(str(t), quote=True)   # noqa: E731
    mods = c.get("modalidades", MODALIDADES_PADRAO)
    lista_mod = "; ".join(f"{k} {v}" for k, v in MODALIDADES.items())
    cofre = "A chave está no cofre; deixe em branco para mantê-la." if cid.tem_segredo("transparencia_chave") else "Peça a chave gratuita no Portal da Transparência (acesso com gov.br) e informe aqui."
    est = cid.estado(sys.modules[__name__])
    return (f'<h2 id="h-lic">Licitações e sanções</h2><form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}">'
            f'<p><label for="lpal2">Termos a procurar no objeto das licitações (um por linha)</label><br><textarea id="lpal2" name="palavras" rows="4" cols="40">{e(chr(10).join(c.get("palavras", [])))}</textarea></p>'
            f'<p><label for="lmod">Modalidades (códigos separados por vírgula: {e(lista_mod)})</label><br><input id="lmod" name="modalidades" type="text" value="{e(", ".join(str(m) for m in mods))}"></p>'
            f'<p><label for="luf">UFs (opcional, separadas por vírgula; em branco, todo o Brasil)</label><br><input id="luf" name="ufs" type="text" value="{e(", ".join(c.get("ufs", [])))}"></p>'
            f'<p><label for="lcnpj">CNPJs a conferir no CEIS e no CNEP (um por linha, só pessoas jurídicas)</label><br><textarea id="lcnpj" name="cnpjs" rows="3" cols="40">{e(chr(10).join(c.get("cnpjs", [])))}</textarea></p>'
            f'<p><label for="lchave">Chave do Portal da Transparência</label><br><input id="lchave" name="transparencia_chave" type="password" autocomplete="new-password"></p><p>{e(cofre)}</p>'
            '<button type="submit">Salvar licitações e sanções</button></form>' + (f'<p class="meta" role="status">{e(est)}</p>' if est else ""))
