#!/usr/bin/env python3
"""Memória clínica do Heimdall Health: perfil de saúde e sugestões de acompanhamento.

O perfil guarda o que o usuário informa (condições, cirurgias, alergias, convênio, médicos). As sugestões nascem dos documentos já confirmados
(receitas, encaminhamentos, atestados, laudos, pedidos de exame): retorno ao médico perto do fim do suprimento de um remédio, pergunta sobre
fisioterapia depois de um atestado com CID de joelho, pedidos de exame sem resultado. São SUGESTÕES para conversar com o médico, nunca diagnóstico
nem orientação sobre dose. Nada vai para o Lembretes sem o usuário aceitar.

Duas camadas: regras (sempre) e um modelo (nuvem, com o local de reserva) que revisa o texto das sugestões levando em conta o perfil (por exemplo,
o encaminhamento cita a UBS, mas com convênio a retirada de pontos pode ser feita na rede credenciada) e pode acrescentar até 3 sugestões, cada uma
com os documentos de que veio. O que o modelo devolve é conferido: documento tem que existir, e texto que fale de dose, suspensão ou diagnóstico é descartado.

Uso:
    python3 heimdall_clinico.py --sugestoes [--todas]     lista as sugestões abertas (ou todas)
    python3 heimdall_clinico.py --atualizar               procura sugestões novas nos documentos confirmados
    python3 heimdall_clinico.py --aceitar ID              vira lembrete (consulta ou exame) ou fica registrada (pergunta)
    python3 heimdall_clinico.py --recusar ID              não mostra mais
    python3 heimdall_clinico.py --adiar ID --dias 14      volta a aparecer depois
    python3 heimdall_clinico.py --responder ID --texto "..."   guarda a resposta a uma pergunta
    python3 heimdall_clinico.py --perfil                  mostra o perfil
    python3 heimdall_clinico.py --perfil-add TIPO --texto "..." [--desde AAAA-MM-DD]
    python3 heimdall_clinico.py --perfil-rm ID
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import heimdall_agenda as agenda  # noqa: E402
import heimdall_exames as ex  # noqa: E402

PERFIL_TIPOS = {"condicao": "condição ou doença", "cirurgia": "cirurgia ou procedimento", "alergia": "alergia", "convenio": "convênio ou plano",
                "medico": "médico ou serviço de confiança", "outro": "outra informação"}
TIPOS_SUGESTAO = ("consulta", "exame", "pergunta")
ANTECEDENCIA_RETORNO = 7          # dias antes do fim previsto do remédio
SEM_QUANTIDADE_DIAS = 30          # receita de controle especial vale 30 dias quando a quantidade não permite calcular


class ErroClinico(Exception):
    pass


def _norm(t: str) -> str:
    return ex._norm(t)


# --------------------------------------------------------------------------------------------
# Perfil
# --------------------------------------------------------------------------------------------
def perfil_listar() -> list:
    return ex._ler("SELECT * FROM perfil_clinico ORDER BY tipo, id")


def perfil_adicionar(tipo: str, texto: str, desde: str = "") -> dict:
    tipo = _norm(tipo).replace(" ", "_")
    if tipo not in PERFIL_TIPOS:
        raise ErroClinico("Tipo inválido. Use: " + ", ".join(PERFIL_TIPOS) + ".")
    texto = ex._limpo(texto, 200)
    if len(texto) < 2:
        raise ErroClinico("Escreva a informação (por exemplo: hipoglicemia, ou o nome do convênio).")
    if desde and not re.fullmatch(r"\d{4}(?:-\d{2}-\d{2})?", desde):
        raise ErroClinico("A data de início é AAAA ou AAAA-MM-DD.")
    ex._escrever(lambda con: con.execute("INSERT OR IGNORE INTO perfil_clinico (tipo, texto, desde, fonte, criado) VALUES (?,?,?,?,?)",
                                         (tipo, texto, desde, "usuario", ex._agora())))
    return {"tipo": tipo, "texto": texto, "desde": desde}


def perfil_remover(pid: int) -> dict:
    n = ex._escrever(lambda con: con.execute("DELETE FROM perfil_clinico WHERE id = ?", (int(pid),)).rowcount)
    if not n:
        raise ErroClinico(f"Não há item {pid} no perfil.")
    return {"removido": int(pid)}


def _ajuste(chave: str) -> str:
    r = ex._ler("SELECT valor FROM perfil_ajustes WHERE chave = ?", (chave,))
    return r[0]["valor"] if r else ""


def _definir_ajuste(chave: str, valor: str) -> None:
    ex._escrever(lambda con: con.execute("INSERT INTO perfil_ajustes (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (chave, valor)))


def perfil_pendente(hoje: date = None) -> bool:
    """True no primeiro acesso: o perfil está vazio, a pessoa nunca o concluiu e não o adiou. A tela de Perfil é oferecida logo na entrada."""
    hoje = hoje or date.today()
    if perfil_listar() or _ajuste("perfil_concluido"):
        return False
    return _ajuste("perfil_adiado") <= hoje.isoformat()


def perfil_concluir(hoje: date = None) -> dict:
    """A pessoa terminou de informar (ou não tem nada a informar): o convite deixa de aparecer. A aba Perfil continua disponível."""
    _definir_ajuste("perfil_concluido", (hoje or date.today()).isoformat())
    return {"concluido": True}


def perfil_adiar(dias: int = 7, hoje: date = None) -> dict:
    volta = ((hoje or date.today()) + timedelta(days=max(1, min(int(dias), 90)))).isoformat()
    _definir_ajuste("perfil_adiado", volta)
    return {"volta_em": volta}


def relatorio_perfil() -> str:
    rows = perfil_listar()
    if not rows:
        return ("O perfil de saúde está vazio. Registre o que quiser (nada é obrigatório): "
                "heimdall health --labs profile add condition|surgery|allergy|insurance|doctor|other TEXTO")
    linhas = ["Perfil de saúde:"]
    for r in rows:
        linhas.append(f"{r['id']}. {PERFIL_TIPOS.get(r['tipo'], r['tipo']).capitalize()}: {r['texto']}" + (f" (desde {r['desde']})" if r["desde"] else "") + ".")
    return "\n".join(linhas)


# --------------------------------------------------------------------------------------------
# Fatos e regras
# --------------------------------------------------------------------------------------------
CLASSES = (
    ("antidepressivo", ("escitalopram", "citalopram", "sertralina", "fluoxetina", "paroxetina", "fluvoxamina", "venlafaxina", "desvenlafaxina", "duloxetina",
                        "bupropiona", "mirtazapina", "amitriptilina", "nortriptilina", "clomipramina", "trazodona", "vortioxetina")),
    ("antipsicótico", ("quetiapina", "olanzapina", "risperidona", "aripiprazol", "haloperidol", "clozapina", "ziprasidona", "lurasidona", "amissulprida")),
    ("ansiolítico ou calmante", ("clonazepam", "alprazolam", "diazepam", "lorazepam", "bromazepam", "buspirona")),
    ("estabilizador de humor ou anticonvulsivante", ("litio", "lamotrigina", "valproato", "acido valproico", "carbamazepina", "oxcarbazepina", "topiramato")),
    ("para atenção e hiperatividade", ("metilfenidato", "lisdexanfetamina", "atomoxetina")),
    ("para dormir", ("zolpidem", "zopiclona", "melatonina")),
)

_BANIDO = re.compile(r"(?i)\b(dose|doses|aument\w*|reduz\w*|diminu\w*|suspend\w*|interromp\w*|pare\s+de|parar\s+de|deixe\s+de|diagn[oó]stic\w*|voc[eê]\s+tem\s+\w+ose|tratamento\s+correto)\b")


def classe_do_medicamento(nome: str):
    n = _norm(nome)
    for classe, nomes in CLASSES:
        for p in nomes:
            if re.search(r"(?<![a-z])" + p, n):
                return classe, p
    return None, None


def _por_dia(posologia: str) -> float:
    p = _norm(posologia)
    n = 1
    m = re.search(r"(\d+)\s*(?:cp|comprimid|capsul|caps\b)", p)
    if m:
        n = int(m.group(1))
    if re.search(r"12\s*(?:em|/)\s*12|2\s*x\b|2\s+vezes|duas\s+vezes", p):
        return n * 2
    if re.search(r"8\s*(?:em|/)\s*8|3\s*x\b|3\s+vezes|tres\s+vezes", p):
        return n * 3
    if re.search(r"6\s*(?:em|/)\s*6|4\s*x\b|4\s+vezes", p):
        return n * 4
    if "manha" in p and "noite" in p:
        return n * 2
    return n


def dias_de_suprimento(r: dict):
    """(dias, calculado): dias que a receita cobre, pela quantidade e pela posologia; (30, False) quando não dá para calcular."""
    q = r.get("quantidade") or ""
    m = re.search(r"(\d+)\s*(?:embalagens?|caixas?|frascos?)", q)
    u = re.search(r"\((\d+)\s*(?:un|comprimidos?|c[aá]psulas?)", q)
    if m and u:
        return max(1, int(int(m.group(1)) * int(u.group(1)) / _por_dia(r.get("posologia") or ""))), True
    return SEM_QUANTIDADE_DIAS, False


def _fatos(hoje: date) -> dict:
    return {
        "hoje": hoje.isoformat(),
        "receitas": ex._ler("SELECT * FROM receitas ORDER BY dia, id"),
        "encaminhamentos": ex._ler("SELECT * FROM encaminhamentos ORDER BY dia, id"),
        "atestados": ex._ler("SELECT * FROM atestados ORDER BY dia, id"),
        "laudos": ex._ler("SELECT id, documento_id, dia, modalidade, titulo FROM laudos ORDER BY dia, id"),
        "pedidos": ex._ler("SELECT * FROM pedidos_exame ORDER BY dia, id"),
        "consultas": ex._ler("SELECT * FROM consultas ORDER BY dia, id"),
        "resultados": ex._ler("SELECT chave, MAX(dia) AS dia FROM exames_resultados GROUP BY chave"),
        "perfil": perfil_listar(),
    }


def _limpo(t, tam: int = 600) -> str:
    """Texto de sugestão: letras, números e pontuação comum (com ? e !), sem símbolos nem quebras; o que vem do modelo passa por aqui também."""
    t = re.sub(r"[^\w\s().,;:%/+\-?!ºª°']", " ", str(t or ""), flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()[:tam]


def _cand(chave, tipo, titulo, motivo, quando="", base=(), compromisso="", acao=""):
    return {"chave": chave, "tipo": tipo, "titulo": _limpo(titulo, 160), "motivo": _limpo(motivo, 600), "quando": quando,
            "base": sorted({int(b) for b in base if b}), "origem": "regra", "compromisso": compromisso, "acao": acao}


def _regras(f: dict, hoje: date) -> list:
    cands = []
    br = ex._br
    # 1. remédio de acompanhamento médico: retorno e renovação antes de acabar
    grupos = {}
    for r in f["receitas"]:
        classe, p = classe_do_medicamento(r["medicamento"])
        if classe:
            grupos.setdefault((r["prescritor"], r["dia"]), []).append((r, classe, p))
    for (prescritor, dia), itens in grupos.items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia or ""):
            continue
        # só vale se nenhuma receita mais nova repete o mesmo medicamento
        abertos = [(r, c, p) for r, c, p in itens
                   if not any(o["dia"] > dia and classe_do_medicamento(o["medicamento"])[1] == p for o in f["receitas"])]
        if not abertos:
            continue
        calc = [(dias_de_suprimento(r), r, c, p) for r, c, p in abertos]
        (dias, calculado), r0, c0, p0 = min(calc, key=lambda x: x[0][0])
        fim = date.fromisoformat(dia) + timedelta(days=dias)
        quando = max(fim - timedelta(days=ANTECEDENCIA_RETORNO), hoje)
        lista = "; ".join(f"{r['medicamento']} {r['dose']} ({c})".replace("  ", " ") for r, c, _ in abertos)
        quem = prescritor.split("(")[0].strip().title() or "quem prescreveu"
        base_txt = (f"A receita de {br(dia)} ({lista}) cobre cerca de {dias} dia(s), pela quantidade e pela posologia, até {br(fim.isoformat())}."
                    if calculado else
                    f"A receita de {br(dia)} ({lista}) não informa a quantidade de forma que dê para calcular; considerei {dias} dias, até {br(fim.isoformat())}.")
        if fim <= hoje:
            base_txt += " Esse prazo já passou; se você já renovou, recuse esta sugestão."
        cands.append(_cand(f"retorno_receita|{prescritor}|{dia}", "consulta",
                           f"Marcar retorno com {quem} e pedir a renovação da receita", base_txt + " Conversar com o médico sobre a renovação e o acompanhamento.",
                           quando.isoformat(), [r["documento_id"] for r, _, _ in abertos]))
    # 2. joelho e ortopedia: atestado com CID de joelho, fisioterapia, retorno
    fisio = [e for e in f["encaminhamentos"] if e["especialidade"] == "Fisioterapia"]
    joelho_cid = [a for a in f["atestados"] if re.match(r"(?i)M23", a.get("cid") or "")]
    posop = [e for e in f["encaminhamentos"] if re.search(r"(?i)p[oó]s[\s\-]*op|cirurg|reconstru", e.get("motivo") or "")] \
        + [x for x in f["perfil"] if x["tipo"] == "cirurgia" and re.search(r"(?i)joelho|lca|menisc", x["texto"])]
    if joelho_cid and not fisio:
        a = joelho_cid[-1]
        cands.append(_cand(f"joelho_fisio|{a['documento_id']}", "pergunta", "Fisioterapia depois do atestado com CID de joelho",
                           f"O atestado de {br(a['dia'])} tem CID {a['cid']} (joelho) e ainda não há encaminhamento de fisioterapia registrado. "
                           "Você fez ou vai fazer algum procedimento no joelho? Se sim, vale perguntar ao médico sobre fisioterapia.",
                           hoje.isoformat(), [a["documento_id"]]))
    for e in fisio[-1:]:
        sessoes = re.search(r"(\d+)\s*sess", _norm(e["motivo"]))
        n = f" das {sessoes.group(1)} sessões" if sessoes else ""
        quando = max(date.fromisoformat(e["dia"]) + timedelta(days=30), hoje) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["dia"] or "") else hoje
        cands.append(_cand(f"fisio|{e['documento_id']}", "pergunta", "Como está a fisioterapia",
                           f"O último encaminhamento de fisioterapia é de {br(e['dia'])} ({e['motivo']}). Quantas{n} você já fez? "
                           "Se terminaram, vale perguntar ao médico se precisa de um novo encaminhamento.", quando.isoformat(), [e["documento_id"]]))
    if posop and (joelho_cid or fisio):
        ultimos = [x["dia"] for x in joelho_cid + fisio + f["laudos"] if x.get("dia")]
        ultimo = max(ultimos) if ultimos else ""
        futura = any(c["dia"] >= hoje.isoformat() and re.search(r"(?i)ortop", c.get("especialidade") or "") for c in f["consultas"])
        if ultimo and not futura and (hoje - date.fromisoformat(ultimo)).days > 60:
            cands.append(_cand("joelho_retorno|" + ultimo, "consulta", "Retorno com o ortopedista para avaliar a evolução do joelho",
                               f"Os documentos indicam pós-operatório do joelho e o último é de {br(ultimo)}, há mais de 60 dias, sem consulta de ortopedia marcada.",
                               hoje.isoformat(), [x["documento_id"] for x in joelho_cid + fisio][-3:]))
    # 3. pedido de exame sem resultado
    por_dia = {}
    for p in f["pedidos"]:
        por_dia.setdefault((p["documento_id"], p["dia"]), []).append(p)
    ult = {r["chave"]: r["dia"] for r in f["resultados"]}
    for (doc, dia), ps in por_dia.items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia or "") or (hoje - date.fromisoformat(dia)).days < 14:
            continue
        sem = []
        for p in ps:
            k = ex.achar_analito(p["exame"])
            if k and ult.get(k, "") < dia:
                sem.append(p["exame"])
        if sem:
            lista = ", ".join(sem[:8]) + (f" e mais {len(sem) - 8}" if len(sem) > 8 else "")
            cands.append(_cand(f"pedido_sem_resultado|{doc}", "pergunta", "Exames pedidos que ainda não têm resultado no Heimdall",
                               f"O pedido de {br(dia)} tem {len(ps)} exame(s); sem resultado enviado depois dessa data: {lista}. Se você já fez, solte os laudos em health/inbox; "
                               "se ainda não fez, este é o aviso para fazê-los.", hoje.isoformat(), [doc]))
    # 4. encaminhamento com data futura e local sugerido (UBS): o local pode ser outro
    convenio = [x["texto"] for x in f["perfil"] if x["tipo"] == "convenio"]
    for e in f["encaminhamentos"]:
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", e.get("motivo") or "")
        if not (m and re.search(r"(?i)retirada de pontos", e["especialidade"])):
            continue
        try:
            alvo = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if alvo < hoje:
            continue
        extra = (f" Você registrou o convênio {', '.join(convenio)}: pergunte se a rede credenciada atende esse procedimento." if convenio
                 else " Se você tem convênio, também pode ser feito em clínica ou hospital particular; registre o convênio no perfil para eu considerar isso.")
        cands.append(_cand(f"pontos|{e['documento_id']}", "consulta", f"Retirada de pontos em {br(alvo.isoformat())}",
                           f"O encaminhamento pede a retirada de pontos em {br(alvo.isoformat())} e cita a UBS, mas o local pode ser outro serviço." + extra,
                           max(alvo - timedelta(days=3), hoje).isoformat(), [e["documento_id"]],
                           compromisso=alvo.isoformat(), acao="retirada de pontos"))
    # 5. perfil vazio
    if not f["perfil"] and (f["receitas"] or f["atestados"] or f["encaminhamentos"] or f["laudos"]):
        cands.append(_cand("perfil|vazio", "pergunta", "Registrar o perfil de saúde",
                           "O perfil ainda está vazio. Condições e doenças que você já tem, cirurgias, alergias e o convênio ajudam o Heimdall a dar sugestões mais certas. "
                           "Nada é obrigatório: heimdall health --labs profile add TIPO TEXTO.", hoje.isoformat(), []))
    return cands


# --------------------------------------------------------------------------------------------
# Revisão pelo modelo (nuvem, com reserva local)
# --------------------------------------------------------------------------------------------
PROMPT_REVISAO = (ex._ANTI_INJECAO +
                  "Você revisa sugestões de acompanhamento de saúde para o próprio paciente, a partir de FATOS já confirmados por ele. "
                  "Regras: não dê diagnóstico, não fale de dose, não mande suspender, reduzir ou aumentar remédio; só sugira perguntar, marcar, levar ao médico ou conferir. "
                  "Para cada sugestão candidata, diga se mantém e, se quiser, reescreva título e motivo (curtos, em português) levando em conta detalhes sutis: o convênio do perfil, "
                  "o local citado num documento (por exemplo UBS) que pode ser outro serviço, datas que já passaram, coisas que parecem já feitas. "
                  "Você pode propor até 3 sugestões NOVAS, só com base nos fatos, cada uma com os ids dos documentos (campo documento_id dos fatos) de que veio.\n"
                  'Formato: {"revisadas": [{"chave": "...", "manter": true, "titulo": "...", "motivo": "..."}], '
                  '"novas": [{"tipo": "consulta|exame|pergunta", "titulo": "...", "motivo": "...", "base": [12]}]}\n\nFATOS E CANDIDATAS:\n')


def _fatos_para_modelo(f: dict, cands: list) -> str:
    def enxuto(rows, campos):
        return [{k: r.get(k) for k in campos if r.get(k) not in (None, "")} for r in rows]
    dados = {
        "hoje": f["hoje"],
        "perfil": enxuto(f["perfil"], ("tipo", "texto", "desde")),
        "receitas": enxuto(f["receitas"], ("documento_id", "dia", "medicamento", "dose", "posologia", "quantidade", "prescritor")),
        "encaminhamentos": enxuto(f["encaminhamentos"], ("documento_id", "dia", "especialidade", "motivo", "cid")),
        "atestados": enxuto(f["atestados"], ("documento_id", "dia", "inicio", "fim", "dias", "cid")),
        "laudos": enxuto(f["laudos"], ("documento_id", "dia", "titulo")),
        "pedidos_de_exame": enxuto(f["pedidos"], ("documento_id", "dia", "exame")),
        "consultas": enxuto(f["consultas"], ("dia", "especialidade", "medico")),
        "candidatas": [{k: c[k] for k in ("chave", "tipo", "titulo", "motivo", "quando")} for c in cands],
    }
    return json.dumps(dados, ensure_ascii=False)[:14000]


def _seguro(texto: str) -> bool:
    return not _BANIDO.search(texto or "")


def revisar_com_modelo(f: dict, cands: list) -> tuple:
    """(candidatas revisadas, avisos). Sem modelo, ou com resposta inválida, devolve as candidatas como estão."""
    if not ex.USAR_MODELO or not (cands or f["receitas"] or f["encaminhamentos"] or f["atestados"]):
        return cands, []
    r = ex._json_do_modelo(ex._modelo(PROMPT_REVISAO + _fatos_para_modelo(f, cands), 1500))
    if not isinstance(r, dict):
        return cands, []
    avisos, por_chave = [], {c["chave"]: c for c in cands}
    saida = list(cands)
    for it in (r.get("revisadas") or [])[:30]:
        if not isinstance(it, dict) or it.get("chave") not in por_chave:
            continue
        c = por_chave[it["chave"]]
        titulo, motivo = _limpo(it.get("titulo", ""), 160), _limpo(it.get("motivo", ""), 600)
        if titulo and _seguro(titulo):
            c["titulo"] = titulo
        if motivo and _seguro(motivo):
            c["motivo"] = motivo
            c["origem"] = "regra+modelo"
        if it.get("manter") is False:
            saida.remove(c)
            avisos.append(f"A revisão não manteve a sugestão '{c['titulo']}': {motivo or 'sem motivo informado'}.")
    docs = {x["documento_id"] for k in ("receitas", "encaminhamentos", "atestados", "laudos", "pedidos") for x in f[k]}
    for it in (r.get("novas") or [])[:3]:
        if not isinstance(it, dict) or it.get("tipo") not in TIPOS_SUGESTAO:
            continue
        titulo, motivo = _limpo(it.get("titulo", ""), 160), _limpo(it.get("motivo", ""), 600)
        base = [int(b) for b in (it.get("base") or []) if str(b).isdigit() and int(b) in docs]
        if not (titulo and motivo and base and _seguro(titulo) and _seguro(motivo)):
            continue
        chave = "modelo|" + re.sub(r"[^a-z0-9]+", "-", _norm(titulo))[:60]
        c = _cand(chave, it["tipo"], titulo, motivo, f["hoje"], base)
        c["origem"] = "modelo"
        saida.append(c)
    return saida, avisos


# --------------------------------------------------------------------------------------------
# Sugestões: gerar, listar, aceitar, recusar, adiar, responder
# --------------------------------------------------------------------------------------------
def atualizar(hoje: date = None, com_modelo: bool = True) -> dict:
    """Procura sugestões nos documentos confirmados e guarda as novas. Uma chave já vista (mesmo recusada) não volta. Devolve {novas, avisos}."""
    hoje = hoje or date.today()
    f = _fatos(hoje)
    cands = _regras(f, hoje)
    avisos = []
    if com_modelo:
        try:
            cands, avisos = revisar_com_modelo(f, cands)
        except Exception:  # noqa: BLE001 - a revisão é um extra: sem ela as regras valem
            pass
    existentes = {r["chave"] for r in ex._ler("SELECT chave FROM sugestoes_saude")}
    novas = [c for c in cands if c["chave"] not in existentes]
    agora = ex._agora()

    def grava(con):
        for c in cands:      # sugestão de regra ainda aberta acompanha os documentos novos (por exemplo, mais uma receita do mesmo dia)
            if c["chave"] in existentes and c["origem"] == "regra":
                con.execute("UPDATE sugestoes_saude SET titulo=?, motivo=?, quando=?, base=?, compromisso=?, acao=?, atualizado=? WHERE chave=? AND estado='aberta' AND origem='regra'",
                            (c["titulo"], c["motivo"], c["quando"], json.dumps(c["base"]), c.get("compromisso", ""), c.get("acao", ""), agora, c["chave"]))
        for c in novas:
            con.execute("INSERT OR IGNORE INTO sugestoes_saude (chave, tipo, titulo, motivo, quando, base, origem, estado, criado, atualizado, compromisso, acao) VALUES (?,?,?,?,?,?,?,'aberta',?,?,?,?)",
                        (c["chave"], c["tipo"], c["titulo"], c["motivo"], c["quando"], json.dumps(c["base"]), c["origem"], agora, agora, c.get("compromisso", ""), c.get("acao", "")))
        # a sugestão aberta que as regras não geram mais (receita renovada, pergunta já respondida por novos documentos) sai da lista
        vivas = {c["chave"] for c in cands}
        for r in con.execute("SELECT id, chave FROM sugestoes_saude WHERE estado = 'aberta' AND origem LIKE 'regra%'").fetchall():
            if r["chave"] not in vivas and not r["chave"].startswith("modelo|"):
                con.execute("UPDATE sugestoes_saude SET estado='recusada', resposta='Não se aplica mais (os documentos mudaram).', atualizado=? WHERE id=?", (agora, r["id"]))
    ex._escrever(grava)
    return {"novas": len(novas), "avisos": avisos}


def _reabrir_adiadas(hoje: date) -> None:
    ex._escrever(lambda con: con.execute("UPDATE sugestoes_saude SET estado='aberta', atualizado=? WHERE estado='adiada' AND quando != '' AND quando <= ?", (ex._agora(), hoje.isoformat())))


def listar(todas: bool = False, hoje: date = None) -> list:
    _reabrir_adiadas(hoje or date.today())
    if todas:
        return ex._ler("SELECT * FROM sugestoes_saude ORDER BY id DESC")
    return ex._ler("SELECT * FROM sugestoes_saude WHERE estado = 'aberta' ORDER BY quando, id")


def _sug(sid: int) -> dict:
    r = ex._ler("SELECT * FROM sugestoes_saude WHERE id = ?", (int(sid),))
    if not r:
        raise ErroClinico(f"Não há sugestão {sid}. Veja a lista: heimdall health --labs suggestions")
    return r[0]


def _linha(s: dict) -> str:
    quando = f" Para: {ex._br(s['quando'])}." if s["quando"] else ""
    if s.get("compromisso"):
        quando += f" Compromisso em {ex._br(s['compromisso'])}: ao aceitar, vira evento no Calendário."
    elif s["tipo"] in ("consulta", "exame"):
        quando += " Ao aceitar, vira lembrete; se você já marcou, informe a data e vira evento no Calendário."
    tag = " (proposta pela IA)" if s["origem"] == "modelo" else ""
    estado = "" if s["estado"] == "aberta" else f" [{s['estado']}]"
    return f"{s['id']}. {s['titulo']}{tag}{estado}. {s['motivo']}{quando}" + (f" Sua resposta: {s['resposta']}" if s["resposta"] and s["estado"] == "respondida" else "")


def relatorio_sugestoes(todas: bool = False) -> str:
    rows = listar(todas)
    if not rows:
        return "Nenhuma sugestão aberta. Para procurar de novo: heimdall health --labs suggestions refresh"
    cab = f"{len(rows)} sugestão(ões)" + ("" if todas else " aberta(s)") + ". São sugestões para conversar com o médico, não diagnóstico."
    ajuda = ("Para cada uma: heimdall health --labs suggestions accept ID (vira lembrete), dismiss ID (não mostrar mais), snooze ID DIAS, answer ID TEXTO (perguntas).")
    return "\n".join([cab] + [_linha(r) for r in rows] + ([ajuda] if not todas else []))


def _titulo_agenda(s: dict) -> str:
    """O título que vai à agenda (e à nuvem da Apple) diz só a ação; remédio, CID e motivo ficam no Heimdall."""
    if s.get("acao"):
        return "Heimdall Saúde: " + s["acao"]
    return "Heimdall Saúde: marcar consulta" if s["tipo"] == "consulta" else "Heimdall Saúde: fazer exame"


def destino_da_sugestao(s: dict, data: str = "", hoje: date = None) -> str:
    """Evento ou lembrete, conforme o caso: com data fixa (a do próprio documento ou a que o usuário informa, por exemplo da consulta já marcada) é evento
    no Calendário; sem data fixa é lembrete (algo a fazer, que se marca como feito). Pergunta não vai à agenda."""
    hoje = hoje or date.today()
    if s["tipo"] == "pergunta":
        return ""
    fixa = data or s.get("compromisso") or ""
    return "evento" if fixa and fixa >= hoje.isoformat() else "lembrete"


def aceitar(sid: int, post=None, hoje: date = None, data: str = "", hora: str = "") -> dict:
    """Aceita a sugestão. `data` (AAAA-MM-DD) e `hora` (HH:MM) opcionais: quem já marcou a consulta informa quando, e ela vira evento no Calendário."""
    s = _sug(sid)
    if s["estado"] not in ("aberta", "adiada"):
        raise ErroClinico(f"A sugestão {sid} está {s['estado']}.")
    hoje = hoje or date.today()
    agora = ex._agora()
    if s["tipo"] == "pergunta":
        ex._escrever(lambda con: con.execute("UPDATE sugestoes_saude SET estado='aceita', atualizado=? WHERE id=?", (agora, s["id"])))
        return {"id": s["id"], "lembrete": False, "evento": False, "texto": "Pergunta registrada como vista. Para guardar a resposta: heimdall health --labs suggestions answer ID TEXTO."}
    if data and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
        raise ErroClinico("A data é AAAA-MM-DD.")
    if data and data < hoje.isoformat():
        raise ErroClinico("A data informada já passou.")
    if hora and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", hora):
        raise ErroClinico("A hora é HH:MM, por exemplo 14:30.")
    dest = destino_da_sugestao(s, data, hoje)
    titulo = _titulo_agenda(s)
    notas = "Criado pelo Heimdall a partir de uma sugestão que você aceitou. Detalhes: heimdall health --labs suggestions."
    if dest == "evento":
        dia = data or s["compromisso"]
        dado = {"titulo": titulo, "data": dia, "duracao_min": 60, "alertas_min_antes": [60, 1440], "notas": notas}
        if hora:
            dado["hora"] = hora
        ok, msg = agenda.enviar("sugestao_saude_evento", dado, post)
        feito = f"Evento criado no Calendário para {ex._br(dia)}" + (f" às {hora}" if hora else " (dia inteiro)") + "."
    else:
        dia = s["quando"] if s["quando"] and s["quando"] >= hoje.isoformat() else hoje.isoformat()
        ok, msg = agenda.enviar("sugestao_saude", {"titulo": titulo, "vencimento": dia, "hora": 9, "notas": notas}, post)
        feito = f"Lembrete criado para {ex._br(dia)}."
    if ok:
        ex._escrever(lambda con: con.execute("UPDATE sugestoes_saude SET estado='aceita', atualizado=? WHERE id=?", (agora, s["id"])))
    return {"id": s["id"], "evento": ok and dest == "evento", "lembrete": ok and dest == "lembrete", "destino": dest, "dia": dia,
            "texto": feito if ok else f"Não criei o {dest} ({msg}). A sugestão continua aberta."}


def recusar(sid: int) -> dict:
    s = _sug(sid)
    ex._escrever(lambda con: con.execute("UPDATE sugestoes_saude SET estado='recusada', atualizado=? WHERE id=?", (ex._agora(), s["id"])))
    return {"id": s["id"], "estado": "recusada"}


def adiar(sid: int, dias: int = 14, hoje: date = None) -> dict:
    s = _sug(sid)
    if not 1 <= int(dias) <= 365:
        raise ErroClinico("Adie por 1 a 365 dias.")
    volta = ((hoje or date.today()) + timedelta(days=int(dias))).isoformat()
    ex._escrever(lambda con: con.execute("UPDATE sugestoes_saude SET estado='adiada', quando=?, atualizado=? WHERE id=?", (volta, ex._agora(), s["id"])))
    return {"id": s["id"], "volta_em": volta}


def responder(sid: int, texto: str) -> dict:
    s = _sug(sid)
    texto = _limpo(texto, 400)
    if not texto:
        raise ErroClinico("Escreva a resposta.")
    ex._escrever(lambda con: con.execute("UPDATE sugestoes_saude SET estado='respondida', resposta=?, atualizado=? WHERE id=?", (texto, ex._agora(), s["id"])))
    return {"id": s["id"], "estado": "respondida"}


def resumo_para_chat() -> str:
    return relatorio_perfil() + "\n\n" + relatorio_sugestoes()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sugestoes", action="store_true")
    ap.add_argument("--todas", action="store_true")
    ap.add_argument("--atualizar", action="store_true")
    ap.add_argument("--aceitar", type=int)
    ap.add_argument("--recusar", type=int)
    ap.add_argument("--adiar", type=int)
    ap.add_argument("--dias", type=int, default=14)
    ap.add_argument("--responder", type=int)
    ap.add_argument("--texto", default="")
    ap.add_argument("--perfil", action="store_true")
    ap.add_argument("--perfil-add", dest="perfil_add")
    ap.add_argument("--perfil-rm", dest="perfil_rm", type=int)
    ap.add_argument("--desde", default="")
    ap.add_argument("--data", default="", help="com --aceitar: AAAA-MM-DD da consulta ou compromisso já marcado (vira evento no Calendário)")
    ap.add_argument("--hora", default="", help="com --aceitar --data: HH:MM")
    ap.add_argument("--pessoa", default="", help="banco de outra pessoa (db/people/<nome>); sem ele vale o seu")
    ap.add_argument("--perfil-concluir", dest="perfil_concluir", action="store_true")
    a = ap.parse_args()
    import heimdall_banco as banco
    try:
        with banco.pessoa(a.pessoa):
            _executar(a)
    except (ErroClinico, ex.ErroExames, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _executar(a) -> None:
    if a.atualizar:
        r = atualizar()
        print(f"{r['novas']} sugestão(ões) nova(s).")
        for x in r["avisos"]:
            print("Atenção: " + x)
        print(relatorio_sugestoes())
    elif a.aceitar:
        print(aceitar(a.aceitar, data=a.data, hora=a.hora)["texto"])
    elif a.recusar:
        recusar(a.recusar)
        print("Sugestão recusada; ela não volta a aparecer.")
    elif a.adiar:
        print(f"Adiada; volta em {ex._br(adiar(a.adiar, a.dias)['volta_em'])}.")
    elif a.responder:
        responder(a.responder, a.texto)
        print("Resposta guardada.")
    elif a.perfil_add:
        r = perfil_adicionar(a.perfil_add, a.texto, a.desde)
        print(f"Registrado: {PERFIL_TIPOS[r['tipo']]}: {r['texto']}.")
    elif a.perfil_rm:
        perfil_remover(a.perfil_rm)
        print("Removido do perfil.")
    elif a.perfil_concluir:
        perfil_concluir()
        print("Perfil marcado como concluído.")
    elif a.perfil:
        print(relatorio_perfil())
    else:
        print(relatorio_sugestoes(a.todas))


if __name__ == "__main__":
    main()
