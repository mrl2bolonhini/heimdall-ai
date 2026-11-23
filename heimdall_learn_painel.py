#!/usr/bin/env python3
"""Heimdall Learn: dados das abas Exercícios e Progresso, só leitura.

Exercícios: todos os exercícios das lições, com a resposta do aluno e o resultado. O gabarito só aparece depois que a lição foi concluída.
Progresso: por pasta, lições, média de acertos, estudos, cards lidos; dias seguidos de estudo e acertos por tipo de exercício.
Usa só a biblioteca padrão do Python.
"""
import json
from datetime import date, datetime, timedelta

import heimdall_learn_dados as dados


def _resultado(correto) -> str:
    if correto is None:
        return "aguardando correção"
    return "certo" if correto >= 1 else ("parcial" if correto > 0 else "errado")


def exercicios(pasta: str = "", so_erros: bool = False, limite: int = 60) -> list:
    """Exercícios das lições, da lição mais recente para a mais antiga. Cada item traz o resultado e, só em lição concluída, o gabarito."""
    con = dados.conectar()
    if pasta:
        n = dados.normalizar_caminho(pasta)   # a pasta e tudo o que há dentro dela (um tema inclui as subpastas)
        lics = con.execute("SELECT id, pasta, numero, titulo, estado, exercicios FROM licoes WHERE (pasta = ? OR pasta LIKE ?) AND estado != 'gerando' ORDER BY id DESC", (n, n + "/%")).fetchall()
    else:
        lics = con.execute("SELECT id, pasta, numero, titulo, estado, exercicios FROM licoes WHERE estado != 'gerando' ORDER BY id DESC").fetchall()
    saida = []
    for lic in lics:
        try:
            exs = json.loads(lic["exercicios"] or "[]")
        except ValueError:
            continue
        resp = {r["ex_idx"]: r for r in con.execute("SELECT ex_idx, resposta, via, correto, correcao FROM respostas WHERE licao_id = ?", (lic["id"],)).fetchall()}
        for i, ex in enumerate(exs):
            r = resp.get(i)
            res = _resultado(r["correto"]) if r else "sem resposta"
            if so_erros and res not in ("errado", "parcial"):
                continue
            item = {"licao_id": lic["id"], "licao": lic["numero"], "titulo": lic["titulo"], "pasta": lic["pasta"], "numero": i + 1, "tipo": ex.get("tipo", ""),
                    "enunciado": ex.get("enunciado", ""), "resposta": r["resposta"] if r else "", "via": r["via"] if r else "", "resultado": res,
                    "correcao": r["correcao"] if r else "", "gabarito": ""}
            if lic["estado"] == "concluida":
                if ex.get("tipo") == "alternativas":
                    ops = ex.get("opcoes") or []
                    k = ex.get("correta")
                    item["gabarito"] = ops[k] if isinstance(k, int) and 0 <= k < len(ops) else ""
                else:
                    item["gabarito"] = ex.get("gabarito", "")
            saida.append(item)
            if len(saida) >= limite:
                return saida
    return saida


def sequencia_de_dias(datas: list, hoje: date = None) -> tuple:
    """(dias seguidos até hoje ou ontem, total de dias com estudo). Dias vêm como texto AAAA-MM-DD ou AAAA-MM-DD hh:mm:ss."""
    hoje = hoje or datetime.now().date()
    dias = set()
    for d in datas:
        try:
            dias.add(datetime.strptime(str(d)[:10], "%Y-%m-%d").date())
        except ValueError:
            continue
    if not dias:
        return 0, 0
    atual = hoje if hoje in dias else hoje - timedelta(days=1)
    n = 0
    while atual in dias:
        n += 1
        atual -= timedelta(days=1)
    return n, len(dias)


def progresso(tema: str = "") -> dict:
    """Números do aluno: por pasta e no geral. Com `tema`, só as pastas dele (e das subpastas) e os exercícios dele."""
    con = dados.conectar()
    pastas = []
    for p in con.execute("SELECT caminho, nome, categoria FROM pastas ORDER BY caminho").fetchall():
        c = p["caminho"]
        if tema and not (c == tema or c.startswith(tema + "/")):
            continue
        lic = con.execute("SELECT COUNT(*) c, SUM(CASE WHEN estado='concluida' THEN 1 ELSE 0 END) f, AVG(CASE WHEN estado='concluida' THEN nota END) m FROM licoes WHERE pasta = ?", (c,)).fetchone()
        est = con.execute("SELECT COUNT(*) c, SUM(CASE WHEN estado='corrigido' THEN 1 ELSE 0 END) f FROM estudos WHERE pasta = ?", (c,)).fetchone()
        crd = con.execute("SELECT COUNT(*) c, SUM(lido) l FROM cards WHERE pasta = ?", (c,)).fetchone()
        if not (lic["c"] or est["c"] or crd["c"]):
            continue
        pastas.append({"caminho": c, "nome": p["nome"], "categoria": p["categoria"], "licoes": lic["c"] or 0, "concluidas": lic["f"] or 0, "media": lic["m"],
                       "estudos": est["c"] or 0, "estudos_corrigidos": est["f"] or 0, "cards": crd["c"] or 0, "cards_lidos": crd["l"] or 0})
    datas = [r[0] for r in con.execute("SELECT criado FROM respostas UNION ALL SELECT criado FROM estudos WHERE resposta != '' UNION ALL SELECT criado FROM cards WHERE lido = 1")]
    seguidos, total_dias = sequencia_de_dias(datas)
    por_tipo = {}
    for ex in exercicios(tema, False, 100000):
        if ex["resultado"] in ("certo", "parcial", "errado"):
            t = por_tipo.setdefault(ex["tipo"] or "outro", {"total": 0, "pontos": 0.0})
            t["total"] += 1
            t["pontos"] += 1.0 if ex["resultado"] == "certo" else (0.5 if ex["resultado"] == "parcial" else 0.0)
    return {"pastas": pastas, "seguidos": seguidos, "dias_com_estudo": total_dias,
            "por_tipo": {k: {"total": v["total"], "acerto": v["pontos"] / v["total"]} for k, v in por_tipo.items()}}


# --- Perguntar: contexto do tema para o modelo ---------------------------------------------------------
def _corta(t, n: int) -> str:
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def contexto_do_tema(tema: str = "", limite: int = 14000) -> str:
    """Texto que o campo Perguntar do Learn entrega ao modelo: números de progresso e o que o aluno fez no tema (ou em todos, se tema vazio).
    Só leitura. Entram os trechos que o aluno estudou (o do estudo e o da lição, para poder perguntar sobre o texto), nunca o livro inteiro. O gabarito de lição em aberto não entra (exercicios() já o esconde)."""
    con = dados.conectar()
    sob = lambda campo: (f"({campo} = ? OR {campo} LIKE ?)", (tema, tema + "/%")) if tema else ("1 = 1", ())  # noqa: E731
    pr = progresso(tema)
    partes = [f"TEMA: {dados.nome_bonito(tema) if tema else 'todos os temas'}.",
              f"Dias seguidos de estudo: {pr['seguidos']}; dias com estudo no total: {pr['dias_com_estudo']}."]
    for p in pr["pastas"]:
        media = f"{round(p['media'] * 100)}%" if p["media"] is not None else "sem nota"
        partes.append(f"Pasta {p['caminho']} ({p['categoria']}): lições concluídas {p['concluidas']} de {p['licoes']}, média {media}; estudos corrigidos {p['estudos_corrigidos']} de {p['estudos']}; cards lidos {p['cards_lidos']} de {p['cards']}.")
    for k, v in sorted(pr["por_tipo"].items()):
        partes.append(f"Acerto em exercícios do tipo {k}: {round(v['acerto'] * 100)}% em {v['total']}.")
    w, a = sob("pasta")
    est = con.execute(f"SELECT pasta, titulo, documento, trecho, pergunta, resposta, correcao, estado, criado FROM estudos WHERE {w} ORDER BY id DESC LIMIT 8", a).fetchall()
    if est:
        partes.append("ESTUDOS RECENTES:")
        for x in est:
            partes.append(f"- {x['criado'][:10]} {x['pasta']} ({x['titulo'] or x['documento']}) [{x['estado']}] pergunta: {_corta(x['pergunta'], 220)}"
                          + (f" | resposta do aluno: {_corta(x['resposta'], 250)}" if x["resposta"] else "") + (f" | correção: {_corta(x['correcao'], 300)}" if x["correcao"] else "")
                          + (f"\n  trecho estudado: {_corta(x['trecho'], 1200)}" if x["trecho"] else ""))
    lic = con.execute(f"SELECT pasta, numero, titulo, explicacao, trecho_estudo, estado, nota, criado FROM licoes WHERE {w} ORDER BY id DESC LIMIT 6", a).fetchall()
    if lic:
        partes.append("LIÇÕES RECENTES:")
        for x in lic:
            partes.append(f"- {x['criado'][:10]} {x['pasta']} lição {x['numero']} {x['titulo']} [{x['estado']}]" + (f", nota {round(x['nota'] * 100)}%" if x["nota"] is not None else "")
                          + (f"\n  explicação: {_corta(x['explicacao'], 600)}" if x["explicacao"] else "") + (f"\n  trecho de estudo: {_corta(x['trecho_estudo'], 1200)}" if x["trecho_estudo"] else ""))
    erros = exercicios(tema, True, 15)
    if erros:
        partes.append("EXERCÍCIOS ERRADOS OU PARCIAIS:")
        for x in erros:
            partes.append(f"- {x['pasta']} lição {x['licao']}: {_corta(x['enunciado'], 200)} | resposta: {_corta(x['resposta'], 150)} | {x['resultado']}"
                          + (f" | esperado: {_corta(x['gabarito'], 150)}" if x["gabarito"] else ""))
    w2, a2 = sob("pasta")
    crd = con.execute(f"SELECT pasta, titulo, corpo, lido FROM cards WHERE {w2} ORDER BY id DESC LIMIT 8", a2).fetchall()
    if crd:
        partes.append("CARDS RECENTES:")
        partes += [f"- {x['pasta']}: {x['titulo']}: {_corta(x['corpo'], 200)}" + ("" if x["lido"] else " (não lido)") for x in crd]
    return "\n".join(partes)[:limite]


def resumo_dos_temas() -> list:
    """Um item por tema (pasta de nível de cima): documentos de consulta (da pasta e das subpastas), estudos e lições."""
    con = dados.conectar()
    saida = []
    for t in dados.listar_pastas(""):
        c = t["caminho"]
        docs = sum(len(dados.listar_documentos(x["caminho"])) for x in dados.arvore_plana() if x["caminho"] == c or x["caminho"].startswith(c + "/"))
        est = con.execute("SELECT COUNT(*) FROM estudos WHERE pasta = ? OR pasta LIKE ?", (c, c + "/%")).fetchone()[0]
        lic = con.execute("SELECT COUNT(*) FROM licoes WHERE pasta = ? OR pasta LIKE ?", (c, c + "/%")).fetchone()[0]
        saida.append({"caminho": c, "nome": t["nome"], "categoria": t["categoria_nome"], "tipo": t.get("tipo") or "", "documentos": docs, "estudos": est, "licoes": lic})
    return saida
