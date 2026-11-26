#!/usr/bin/env python3
"""Studio Finance: planilhas (xlsx e csv) de gastos, investimentos, empréstimos e outros assuntos, e as visões personalizadas delas.

Fluxo: o arquivo é lido (xlsx por zipfile, sem biblioteca externa), o Heimdall descobre o tipo e o papel de cada coluna (primeiro por palavras
do cabeçalho, depois pelo modelo de linguagem quando houver dúvida) e grava as linhas num conjunto. O layout aprendido fica gravado pela assinatura
dos cabeçalhos: o próximo arquivo com o mesmo layout (ou quase) entra sozinho no mesmo conjunto. Quando não dá para ter certeza, o Heimdall
guarda o arquivo e faz uma pergunta (dúvida) em vez de chutar. Gastos também alimentam as transações do Finance.
Visões são formas gravadas de mostrar um conjunto (colunas escolhidas e na ordem pedida, ordenação, filtro, agrupamento): como leem os
registros na hora de abrir, lançamentos novos aparecem nelas sem refazer nada.
"""
import csv
import heimdall_pastas
import hashlib
import io
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import financas_nucleo as fn

TIPOS_USUARIO = {"gastos": "Gastos", "investimentos": "Investimentos", "emprestimos": "Empréstimos", "outros": "Outros assuntos"}
# tipos que só a conexão com o Pluggy cria
TIPOS = dict(TIPOS_USUARIO, contas="Contas e cartões (Pluggy)", faturas="Faturas de cartão (Pluggy)", movimentos="Movimentações de investimentos (Pluggy)")
CATEGORIAS_CREDITO = {"veiculo": "Financiamento de veículo", "imovel": "Financiamento imobiliário", "consignado": "Consignado", "pessoal": "Empréstimo pessoal",
                      "outros": "Outros empréstimos e financiamentos"}
_PALAVRAS_CREDITO = [("consignado", ("consign",)),
                     ("veiculo", ("veicul", "automotor", "automovel", "carro", "moto ", "motocicleta", "caminhao")),
                     ("imovel", ("imobili", "habitac", "casa propria", "apartamento", "home equity", "sfh", "sfi", "terreno", "imovel")),
                     ("pessoal", ("pessoal", "cdc", "credito direto", "credito pessoal"))]
EXT_PLANILHA = {".xlsx", ".xlsm", ".csv", ".tsv", ".txt"}
MAX_BYTES = 12 * 1024 * 1024
MAX_LINHAS = 20000
MAX_COLUNAS = 60

# papel -> palavras do cabeçalho (já sem acento, minúsculas), da mais específica para a mais geral
PAPEIS = {
    "gastos": {"data": ["data", "dia", "data da compra", "data do lancamento"],
               "descricao": ["descricao", "historico", "estabelecimento", "lancamento", "detalhe", "nome", "local"],
               "valor": ["valor", "quantia", "montante", "valor (r$)"],
               "categoria": ["categoria", "classificacao"]},
    "investimentos": {"ativo": ["ativo", "produto", "ticker", "papel", "codigo", "titulo", "investimento", "fundo", "nome"],
                      "tipo_ativo": ["tipo", "classe", "categoria", "tipo de investimento"],
                      "instituicao": ["instituicao", "corretora", "banco"],
                      "quantidade": ["quantidade", "qtd", "cotas", "qtde"],
                      "preco": ["preco", "cotacao", "valor unitario", "preco medio", "pu"],
                      "valor": ["valor atual", "saldo atual", "valor liquido", "valor bruto", "posicao", "valor", "saldo", "total", "montante"],
                      "data": ["data", "data base", "posicao em", "referencia", "mes"],
                      "rentabilidade": ["rentabilidade", "rendimento", "retorno"]},
    "emprestimos": {"contrato": ["contrato", "emprestimo", "financiamento", "descricao", "nome", "divida"],
                    "credor": ["credor", "banco", "instituicao"],
                    "saldo": ["saldo devedor", "saldo atual", "valor devedor", "divida", "saldo"],
                    "parcela": ["valor da parcela", "valor parcela", "prestacao", "parcela", "mensalidade"],
                    "taxa": ["taxa de juros", "taxa", "juros", "cet"],
                    "vencimento": ["proximo vencimento", "vencimento", "proxima parcela", "data"],
                    "restantes": ["parcelas restantes", "restantes", "prazo restante", "prazo", "parcelas"]},
    "outros": {},
}
NOMES_PAPEIS = {
    "data": "a data", "descricao": "a descrição", "valor": "o valor", "categoria": "a categoria", "ativo": "o nome do ativo ou produto",
    "tipo_ativo": "o tipo ou a classe do ativo", "instituicao": "a instituição", "quantidade": "a quantidade", "preco": "o preço unitário",
    "rentabilidade": "a rentabilidade", "contrato": "o nome do contrato", "credor": "o credor", "saldo": "o saldo devedor",
    "parcela": "o valor da parcela", "taxa": "a taxa de juros", "vencimento": "o vencimento", "restantes": "as parcelas restantes",
}
# o que precisa existir para a planilha entrar: uma lista de alternativas, e basta uma completa
def categoria_credito(texto: str) -> str:
    """veiculo, imovel, consignado, pessoal ou outros, pelas palavras do tipo, do produto ou do nome do contrato (consignado vem antes de pessoal)."""
    t = " " + fn.norm(texto).replace("_", " ") + " "
    for cat, palavras in _PALAVRAS_CREDITO:
        if any(p in t for p in palavras):
            return cat
    return "outros"


OBRIGATORIOS = {"gastos": [["data", "descricao", "valor"]], "investimentos": [["ativo", "valor"], ["ativo", "quantidade", "preco"]],
                "emprestimos": [["saldo"], ["parcela"]], "outros": [[]]}
PALAVRAS_TIPO = {
    "investimentos": ["ativo", "ticker", "cotas", "quantidade", "qtd", "rentabilidade", "corretora", "aplicacao", "cdb", "tesouro", "acao", "acoes", "fii", "fundo",
                      "rendimento", "cotacao", "investimento", "investimentos", "lci", "lca", "dividendos", "proventos", "carteira", "posicao"],
    "emprestimos": ["saldo devedor", "prestacao", "parcela", "parcelas", "juros", "cet", "contrato", "financiamento", "emprestimo", "amortizacao", "credor",
                    "divida", "taxa", "consignado"],
}
_MESES = {"jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez", "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
          "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"}


class ErroPlanilha(fn.ErroFinance):
    """Planilha que não dá para ler."""


# --------------------------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------------------------
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_indice(ref: str) -> int:
    n = 0
    for c in re.match(r"[A-Z]+", ref.upper()).group(0):
        n = n * 26 + ord(c) - 64
    return n - 1


def _texto_si(si) -> str:
    return "".join(t.text or "" for t in si.iter(_NS + "t"))


def _eh_formato_data(cod: str) -> bool:
    limpo = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", cod.lower())
    return bool(re.search(r"[dy]", limpo) or re.search(r"m+\s*[/\-.]|[/\-.]\s*m+", limpo))


def _formatar_numero(v: str, percentual: bool = False) -> str:
    try:
        x = float(v)
    except ValueError:
        return v
    if percentual:
        x *= 100
    txt = format(round(x, 6), "f").rstrip("0").rstrip(".") or "0"
    return txt.replace(".", ",") + ("%" if percentual else "")


def ler_xlsx(dados: bytes) -> list:
    """[(nome_da_aba, linhas)] com cada linha como lista de textos. Datas viram AAAA-MM-DD e números usam vírgula decimal."""
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile as ex:
        raise ErroPlanilha("Este arquivo não parece uma planilha .xlsx válida.") from ex
    if sum(i.file_size for i in z.infolist()) > 60 * 1024 * 1024:
        raise ErroPlanilha("A planilha descompactada é grande demais.")
    try:
        livro = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        compartilhadas = []
        if "xl/sharedStrings.xml" in z.namelist():
            compartilhadas = [_texto_si(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(_NS + "si")]
        datas, pct = set(), set()
        if "xl/styles.xml" in z.namelist():
            est = ET.fromstring(z.read("xl/styles.xml"))
            codigos = {int(n.get("numFmtId")): n.get("formatCode", "") for n in est.iter(_NS + "numFmt")}
            xfs = est.find(_NS + "cellXfs")
            for i, xf in enumerate(xfs if xfs is not None else []):
                nid = int(xf.get("numFmtId", "0"))
                if nid in (9, 10):
                    pct.add(i)
                elif 14 <= nid <= 22 or 45 <= nid <= 47 or (nid in codigos and _eh_formato_data(codigos[nid])):
                    datas.add(i)
        abas = []
        for s in livro.iter(_NS + "sheet"):
            alvo = rels.get(s.get(_NS_REL + "id"), "")
            caminho = alvo.lstrip("/") if alvo.startswith("/") else "xl/" + alvo
            if caminho not in z.namelist():
                continue
            linhas = []
            raiz = ET.fromstring(z.read(caminho))
            for r in raiz.iter(_NS + "row"):
                lin = []
                for c in r.iter(_NS + "c"):
                    pos = _col_indice(c.get("r", "A1"))
                    if pos >= MAX_COLUNAS:
                        continue
                    lin.extend([""] * (pos + 1 - len(lin)))
                    t, estilo = c.get("t", "n"), int(c.get("s", "0") or 0)
                    v = c.find(_NS + "v")
                    bruto = (v.text or "") if v is not None else ""
                    if t == "s":
                        txt = compartilhadas[int(bruto)] if bruto.isdigit() and int(bruto) < len(compartilhadas) else ""
                    elif t == "inlineStr":
                        txt = _texto_si(c)
                    elif t in ("str", "e", "b"):
                        txt = bruto
                    elif bruto and estilo in datas:
                        try:
                            txt = (datetime(1899, 12, 30) + timedelta(days=int(float(bruto)))).strftime("%Y-%m-%d")
                        except (ValueError, OverflowError):
                            txt = bruto
                    elif bruto:
                        txt = _formatar_numero(bruto, estilo in pct)
                    else:
                        txt = ""
                    lin[pos] = txt.strip()
                linhas.append(lin)
                if len(linhas) > MAX_LINHAS + 50:
                    break
            abas.append((s.get("name", "Planilha"), linhas))
        return abas
    except (KeyError, ET.ParseError, ValueError) as ex:
        raise ErroPlanilha("Não consegui ler a estrutura desta planilha .xlsx.") from ex


def ler_csv(dados: bytes) -> list:
    texto = fn.decodificar(dados)
    amostra = "\n".join(texto.splitlines()[:40])
    delim = ";" if amostra.count(";") > amostra.count(",") else ("\t" if amostra.count("\t") > amostra.count(",") else ",")
    return [("Planilha", [lin[:MAX_COLUNAS] for lin in csv.reader(io.StringIO(texto), delimiter=delim)][:MAX_LINHAS + 50])]


def ler_planilha(dados: bytes, nome: str) -> list:
    if len(dados) > MAX_BYTES:
        raise ErroPlanilha("Arquivo grande demais.")
    if dados[:2] == b"PK":
        return ler_xlsx(dados)
    if Path(nome).suffix.lower() in (".xlsx", ".xlsm"):
        raise ErroPlanilha("Este arquivo não parece uma planilha .xlsx válida.")
    return ler_csv(dados)


def achar_tabela(linhas: list):
    """(cabeçalhos, linhas de dados): o cabeçalho é a primeira linha com pelo menos duas células de texto seguida de linhas com conteúdo."""
    def numerico(t):
        try:
            fn.parse_valor(t)
            return True
        except ValueError:
            return False
    for i, lin in enumerate(linhas[:30]):
        cel = [c for c in lin if c.strip()]
        if len(cel) < 2 or sum(1 for c in cel if numerico(c) or re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}", c)) > len(cel) / 2:
            continue
        resto = [r for r in linhas[i + 1:i + 4] if sum(1 for c in r if c.strip()) >= 2]
        if not resto:
            continue
        cab = [c.strip() for c in lin]
        while cab and not cab[-1]:
            cab.pop()
        dados = []
        for r in linhas[i + 1:]:
            r = (list(r) + [""] * len(cab))[:len(cab)]
            if not any(c.strip() for c in r):
                continue
            primeiro = next((norm_ for norm_ in (fn.norm(c) for c in r) if norm_), "")
            if primeiro.startswith("total") or primeiro.startswith("subtotal"):
                continue  # linha de total no pé da planilha
            dados.append([c.strip() for c in r])
        return cab, dados
    raise ErroPlanilha("Não achei o cabeçalho (a linha com os nomes das colunas) nesta planilha.")


def chaves_das_colunas(cab: list) -> list:
    """Chave estável de cada coluna: o cabeçalho sem acento, em minúsculas, com sublinhado; repetidas ganham número."""
    saida, vistas = [], {}
    for i, c in enumerate(cab):
        k = re.sub(r"[^a-z0-9]+", "_", fn.norm(c)).strip("_") or f"coluna_{i + 1}"
        vistas[k] = vistas.get(k, 0) + 1
        saida.append(k if vistas[k] == 1 else f"{k}_{vistas[k]}")
    return saida


def assinatura(chaves: list) -> str:
    return hashlib.sha1("|".join(sorted(chaves)).encode("utf-8")).hexdigest()[:20]


# --------------------------------------------------------------------------------------------
# Interpretação
# --------------------------------------------------------------------------------------------
def nome_do_arquivo(arquivo: str, aba: str = "", varias: bool = False) -> str:
    stem = Path(arquivo or "Planilha").stem
    toks = [t for t in re.split(r"[\s_\-.]+", stem) if t and not t.isdigit() and fn.norm(t) not in _MESES]
    nome = " ".join(toks).strip() or "Planilha"
    nome = nome[0].upper() + nome[1:]
    if varias and aba and fn.norm(aba) not in ("planilha", "plan1", "sheet1", "planilha1"):
        nome = f"{nome} {aba}"
    return nome[:60]


def _papeis_por_palavras(tipo: str, cab_por_chave: dict) -> dict:
    usados, achados = set(), {}
    norm_ = {k: fn.norm(v) for k, v in cab_por_chave.items()}
    for papel, palavras in PAPEIS.get(tipo, {}).items():
        for passo in ("exato", "contem"):
            achou = None
            for kw in palavras:
                for k, n in norm_.items():
                    if k in usados:
                        continue
                    if (passo == "exato" and n == kw) or (passo == "contem" and len(kw) >= 4 and kw in n):
                        achou = k
                        break
                if achou:
                    break
            if achou:
                achados[papel] = achou
                usados.add(achou)
                break
    return achados


def faltam(tipo: str, papeis: dict) -> list:
    """Papéis que ainda faltam para a menor alternativa obrigatória do tipo."""
    alternativas = OBRIGATORIOS.get(tipo, [[]])
    melhor = None
    for alt in alternativas:
        f = [p for p in alt if p not in papeis]
        if not f:
            return []
        if melhor is None or len(f) < len(melhor):
            melhor = f
    return melhor or []


def _pontuar(arquivo: str, cab: list, papeis_gastos: dict) -> dict:
    texto = " ".join(fn.norm(c) for c in cab) + " " + fn.norm(Path(arquivo or "").stem)
    pontos = {}
    for tipo, palavras in PALAVRAS_TIPO.items():
        pontos[tipo] = sum(1 for p in palavras if re.search(r"(?<![a-z])" + re.escape(p) + r"(?![a-z])", texto))
    achados = len({"data", "descricao", "valor"} & set(papeis_gastos))
    pontos["gastos"] = 2 if achados == 3 else (1 if achados == 2 else 0)
    if re.search(r"extrato|fatura|gastos|despesas|lancamentos", fn.norm(Path(arquivo or "").stem)):
        pontos["gastos"] += 1
    return pontos


_PROMPT = ("Você interpreta planilhas financeiras pessoais brasileiras. Responda SOMENTE um objeto JSON, sem texto fora dele: "
           '{"tipo":"gastos|investimentos|emprestimos|outros","nome":"nome curto do conjunto","papeis":{"papel":"cabeçalho exato da coluna"},"duvida":"o que não ficou claro, ou vazio"}. '
           "Papéis por tipo: gastos (data, descricao, valor, categoria); investimentos (ativo, tipo_ativo, instituicao, quantidade, preco, valor, data, rentabilidade); "
           "emprestimos (contrato, credor, saldo, parcela, taxa, vencimento, restantes); outros (nenhum). Use só cabeçalhos que existem. Omita o papel se não houver coluna para ele. "
           "Não invente dados e não responda sobre o conteúdo das linhas além disso.")


def _modelo_padrao(sistema: str, usuario: str) -> str:
    import heimdall_perguntar as perguntar
    # só o cabeçalho e as 5 primeiras linhas vão ao modelo; HEIMDALL_FINANCE_PLANILHAS_NUVEM=0 mantém tudo no modelo local do Mac
    return perguntar.chamar_local(sistema, usuario, max_tokens=500, timeout=120, usar_nuvem=os.environ.get("HEIMDALL_FINANCE_PLANILHAS_NUVEM", "1") != "0")


def _pedir_ao_modelo(modelo, arquivo, cab, linhas) -> dict:
    exemplo = "\n".join(" | ".join(c[:40] for c in l) for l in linhas[:5])
    usuario = f"Arquivo: {arquivo}\nCabeçalhos: {' | '.join(cab)}\nPrimeiras linhas:\n{exemplo}"
    try:
        resp = (modelo or _modelo_padrao)(_PROMPT, usuario)
        m = re.search(r"\{.*\}", resp or "", re.S)
        d = json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001  (modelo fora do ar ou resposta torta: segue só com o código)
        return {}
    if not isinstance(d, dict) or d.get("tipo") not in TIPOS_USUARIO:
        return {}
    return d


def interpretar(arquivo: str, cab: list, chaves: list, linhas: list, tipo: str = "", modelo=None, usar_modelo: bool = True) -> dict:
    """{tipo, papeis{papel: chave}, nome, origem, faltam[...]}. `tipo` forçado pelo usuário pula a classificação."""
    por_chave = dict(zip(chaves, cab))
    origem = "usuario" if tipo in TIPOS_USUARIO else "palavras"
    if tipo not in TIPOS_USUARIO:
        pontos = _pontuar(arquivo, cab, _papeis_por_palavras("gastos", por_chave))
        ordem = sorted(pontos.items(), key=lambda kv: -kv[1])
        if ordem[0][1] >= 2 and ordem[0][1] > ordem[1][1]:
            tipo = ordem[0][0]
        else:
            tipo = ""
    papeis, nome = ({}, "")
    if tipo:
        papeis = _papeis_por_palavras(tipo, por_chave)
    if (not tipo or faltam(tipo, papeis)) and usar_modelo:
        d = _pedir_ao_modelo(modelo, arquivo, cab, linhas)
        if d and (not tipo or d["tipo"] == tipo):
            tipo = d["tipo"]
            origem = "modelo" if origem != "usuario" else origem
            nome = str(d.get("nome") or "")[:60]
            por_nome = {c: k for k, c in por_chave.items()}
            pm = {}
            for papel, c in (d.get("papeis") or {}).items():
                if papel in PAPEIS.get(tipo, {}) and c in por_nome:
                    pm[papel] = por_nome[c]
            for papel, k in pm.items():
                papeis.setdefault(papel, k)
            if faltam(tipo, papeis):  # o modelo pode ter acertado o tipo; completa o que faltar pelas palavras
                for papel, k in _papeis_por_palavras(tipo, por_chave).items():
                    if k not in papeis.values():
                        papeis.setdefault(papel, k)
    return {"tipo": tipo, "papeis": papeis, "nome": nome, "origem": origem, "faltam": faltam(tipo, papeis) if tipo else ["tipo"]}


# --------------------------------------------------------------------------------------------
# Conjuntos e registros
# --------------------------------------------------------------------------------------------
def _json(txt, padrao):
    try:
        return json.loads(txt) if txt else padrao
    except ValueError:
        return padrao


def conjuntos(con) -> list:
    return list(con.execute("SELECT c.*, (SELECT COUNT(*) FROM registros r WHERE r.conjunto_id=c.id) AS n, "
                            "(SELECT MAX(importado_em) FROM registros r WHERE r.conjunto_id=c.id) AS ultimo FROM conjuntos c ORDER BY c.tipo, c.nome"))


def conjunto(con, cid: int):
    return con.execute("SELECT * FROM conjuntos WHERE id=?", (cid,)).fetchone()


def colunas_do_conjunto(c) -> list:
    return [(k, n) for k, n in _json(c["colunas"], [])]


def _achar_ou_criar_conjunto(con, nome: str, tipo: str, colunas: list, papeis: dict, agora: str) -> int:
    nome = nome or "Planilha"
    row = con.execute("SELECT * FROM conjuntos WHERE nome=?", (nome,)).fetchone()
    if row and row["tipo"] != tipo:
        nome = f"{nome} ({TIPOS[tipo].lower()})"
        row = con.execute("SELECT * FROM conjuntos WHERE nome=?", (nome,)).fetchone()
    if not row:
        cur = con.execute("INSERT INTO conjuntos(nome, tipo, colunas, papeis, criado) VALUES(?,?,?,?,?)",
                          (nome, tipo, json.dumps(colunas, ensure_ascii=False), json.dumps(papeis), agora))
        return cur.lastrowid
    antigas = colunas_do_conjunto(row)
    chaves = {k for k, _ in antigas}
    novas = [(k, n) for k, n in colunas if k not in chaves]
    pap = _json(row["papeis"], {})
    for p, k in papeis.items():
        pap.setdefault(p, k)
    if novas or pap != _json(row["papeis"], {}):
        con.execute("UPDATE conjuntos SET colunas=?, papeis=? WHERE id=?", (json.dumps(antigas + novas, ensure_ascii=False), json.dumps(pap), row["id"]))
    return row["id"]


def _modelo_parecido(con, chaves: list):
    """Layout salvo com a mesma assinatura ou quase (70% das colunas em comum) cujos papéis ainda existem aqui."""
    atuais = set(chaves)
    exato = con.execute("SELECT * FROM modelos WHERE assinatura=?", (assinatura(chaves),)).fetchone()
    if exato:
        return exato
    melhor, nota = None, 0.0
    for m in con.execute("SELECT * FROM modelos"):
        c = conjunto(con, m["conjunto_id"])
        if not c:
            continue
        antigas = {k for k, _ in colunas_do_conjunto(c)}
        papeis = _json(m["papeis"], {})
        if not papeis or not set(papeis.values()) <= atuais:
            continue
        jac = len(atuais & antigas) / max(1, len(atuais | antigas))
        if jac >= 0.7 and jac > nota:
            melhor, nota = m, jac
    return melhor


def _hash_registro(cid: int, valores: dict, n: int) -> str:
    return hashlib.sha1((f"{cid}|{n}|" + json.dumps(valores, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()


def _gravar_registros(con, cid: int, chaves: list, linhas: list, arquivo: str, agora: str) -> tuple:
    novas = repetidas = 0
    vistos = {}
    for lin in linhas:
        valores = {k: v for k, v in zip(chaves, lin)}
        base = json.dumps(valores, sort_keys=True, ensure_ascii=False)
        vistos[base] = vistos.get(base, 0) + 1  # duas linhas idênticas no mesmo arquivo continuam sendo duas
        cur = con.execute("INSERT OR IGNORE INTO registros(conjunto_id, hash, dados, arquivo, importado_em) VALUES(?,?,?,?,?)",
                          (cid, _hash_registro(cid, valores, vistos[base]), base, (arquivo or "")[:120], agora))
        if cur.rowcount:
            novas += 1
        else:
            repetidas += 1
    return novas, repetidas


def _itens_de_gastos(chaves, linhas, papeis, inverter: bool) -> tuple:
    itens, ruins = [], 0
    ix = {k: i for i, k in enumerate(chaves)}
    for lin in linhas:
        try:
            data = fn.parse_data(lin[ix[papeis["data"]]])
            valor = fn.parse_valor(lin[ix[papeis["valor"]]])
        except (ValueError, KeyError, IndexError):
            ruins += 1
            continue
        if inverter:
            valor = -valor
        desc = lin[ix[papeis["descricao"]]] if papeis.get("descricao") in ix else ""
        itens.append({"data": data, "valor": valor, "descricao": desc or "Sem descrição"})
    return itens, ruins


# --------------------------------------------------------------------------------------------
# Dúvidas
# --------------------------------------------------------------------------------------------
def _pasta_pendentes(pasta: Path) -> Path:
    p = Path(pasta) / "planilhas_pendentes"
    p.mkdir(parents=True, exist_ok=True)
    try:
        p.chmod(0o700)
    except OSError:
        pass
    return p


def _criar_duvida(con, pasta: Path, dados: bytes, arquivo: str, aba: str, interp: dict, cab: list, chaves: list, agora: str) -> int:
    h = hashlib.sha256(dados).hexdigest()
    campos = []
    if not interp["tipo"]:
        campos.append({"chave": "tipo", "rotulo": "Que tipo de planilha é esta?", "opcoes": [[k, v] for k, v in TIPOS_USUARIO.items()]})
    for papel in (interp["faltam"] if interp["tipo"] else []):
        campos.append({"chave": f"papel:{papel}", "rotulo": f"Qual coluna tem {NOMES_PAPEIS.get(papel, papel)}?", "opcoes": [[k, c or k] for k, c in zip(chaves, cab)]})
    arq = _pasta_pendentes(pasta) / f"{h}.dat"
    if not arq.exists():
        arq.write_bytes(dados)
        try:
            arq.chmod(0o600)
        except OSError:
            pass
    pergunta = (f"Não tive certeza de como ler a aba {aba} do arquivo {arquivo}. " if aba else f"Não tive certeza de como ler o arquivo {arquivo}. ") + \
               "Responda abaixo e eu guardo o jeito de ler para os próximos arquivos com as mesmas colunas."
    con.execute("DELETE FROM duvidas WHERE hash_arquivo=? AND aba=?", (h, aba))
    cur = con.execute("INSERT INTO duvidas(arquivo, aba, hash_arquivo, pergunta, campos, criado) VALUES(?,?,?,?,?,?)",
                      ((arquivo or "")[:120], aba, h, pergunta, json.dumps(campos, ensure_ascii=False), agora))
    con.commit()
    return cur.lastrowid


def duvidas(con) -> list:
    return [dict(d, campos=_json(d["campos"], [])) for d in con.execute("SELECT * FROM duvidas ORDER BY id")]


def descartar_duvida(con, pasta: Path, did: int) -> None:
    d = con.execute("SELECT * FROM duvidas WHERE id=?", (did,)).fetchone()
    if not d:
        return
    con.execute("DELETE FROM duvidas WHERE id=?", (did,))
    if not con.execute("SELECT 1 FROM duvidas WHERE hash_arquivo=?", (d["hash_arquivo"],)).fetchone():
        try:
            (_pasta_pendentes(pasta) / f"{d['hash_arquivo']}.dat").unlink()
        except OSError:
            pass
    con.commit()


def responder_duvida(con, pasta: Path, did: int, respostas: dict, agora: str = None, modelo=None) -> list:
    d = con.execute("SELECT * FROM duvidas WHERE id=?", (did,)).fetchone()
    if not d:
        raise fn.ErroFinance("Essa dúvida já foi resolvida.")
    arq = _pasta_pendentes(pasta) / f"{d['hash_arquivo']}.dat"
    try:
        dados = arq.read_bytes()
    except OSError as ex:
        raise fn.ErroFinance("Perdi o arquivo desta dúvida. Envie a planilha de novo.") from ex
    con.execute("DELETE FROM duvidas WHERE id=?", (did,))
    con.commit()
    res = processar(con, dados, d["arquivo"], pasta, agora=agora, modelo=modelo, respostas=respostas, so_aba=d["aba"])
    if not con.execute("SELECT 1 FROM duvidas WHERE hash_arquivo=?", (d["hash_arquivo"],)).fetchone():
        try:
            arq.unlink()
        except OSError:
            pass
    return res


# --------------------------------------------------------------------------------------------
# Importação
# --------------------------------------------------------------------------------------------
def processar(con, dados: bytes, arquivo: str, pasta: Path, agora: str = None, modelo=None, tipo: str = "", nome: str = "",
              inverter: bool = False, respostas: dict = None, so_aba: str = None, usar_modelo: bool = True) -> list:
    """Importa cada aba de uma planilha. Devolve um resultado por aba: ok com conjunto/novas/repetidas, ou duvida com o id da pergunta."""
    agora = agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    respostas = respostas or {}
    abas = ler_planilha(dados, arquivo)
    resultados = []
    for aba, linhas_brutas in abas:
        if so_aba is not None and aba != so_aba and not (so_aba == "" and len(abas) == 1):
            continue
        try:
            cab, linhas = achar_tabela(linhas_brutas)
        except ErroPlanilha as ex:
            if len(abas) == 1:
                raise
            resultados.append({"aba": aba, "ok": False, "motivo": str(ex)})
            continue
        if not linhas:
            resultados.append({"aba": aba, "ok": False, "motivo": "Sem linhas de dados."})
            continue
        chaves = chaves_das_colunas(cab)
        guardado = None if (tipo or respostas) else _modelo_parecido(con, chaves)
        if guardado:
            c = conjunto(con, guardado["conjunto_id"])
            interp = {"tipo": guardado["tipo"], "papeis": _json(guardado["papeis"], {}), "nome": c["nome"], "origem": "aprendido", "faltam": []}
        else:
            forcado = respostas.get("tipo") or tipo
            interp = interpretar(arquivo, cab, chaves, linhas, forcado, modelo, usar_modelo)
            for chave, valor in respostas.items():
                if chave.startswith("papel:") and valor in chaves:
                    interp["papeis"][chave[6:]] = valor
            if interp["tipo"]:
                interp["faltam"] = faltam(interp["tipo"], interp["papeis"])
        if not interp["tipo"] or interp["faltam"]:
            did = _criar_duvida(con, pasta, dados, arquivo, aba if len(abas) > 1 else "", interp, cab, chaves, agora)
            resultados.append({"aba": aba, "ok": False, "duvida": did, "motivo": "Preciso de uma resposta sua para ler esta planilha."})
            continue
        nome_final = (nome or respostas.get("nome") or interp["nome"] or nome_do_arquivo(arquivo, aba, len(abas) > 1)).strip()[:60]
        colunas = list(zip(chaves, cab))
        cid = _achar_ou_criar_conjunto(con, nome_final, interp["tipo"], [[k, c or k] for k, c in colunas], interp["papeis"], agora)
        novas, repetidas = _gravar_registros(con, cid, chaves, linhas, arquivo, agora)
        con.execute("INSERT OR REPLACE INTO modelos(assinatura, conjunto_id, tipo, papeis, criado) VALUES(?,?,?,?,?)",
                    (assinatura(chaves), cid, interp["tipo"], json.dumps(interp["papeis"]), agora))
        extra = {}
        if interp["tipo"] == "gastos":
            itens, ruins = _itens_de_gastos(chaves, linhas, interp["papeis"], inverter)
            if itens:
                r = fn.importar_itens(con, itens, "planilha", arquivo, nome_final, agora)
                extra = {"transacoes_novas": r["novas"], "transacoes_repetidas": r["repetidas"], "linhas_ruins": ruins}
            else:
                extra = {"linhas_ruins": ruins}
        con.commit()
        resultados.append({"aba": aba, "ok": True, "conjunto": nome_final, "conjunto_id": cid, "tipo": interp["tipo"], "origem": interp["origem"],
                           "lidas": len(linhas), "novas": novas, "repetidas": repetidas, **extra})
    if not resultados:
        raise ErroPlanilha("Não achei nenhuma aba com dados.")
    return resultados


def importar_arquivo(con, dados: bytes, arquivo: str, pasta: Path, **kw) -> list:
    """Como `processar`, mas ignora arquivo já importado (mesmo conteúdo) e registra o que foi lido."""
    h = hashlib.sha256(dados).hexdigest()
    if con.execute("SELECT 1 FROM planilhas_arquivos WHERE hash=?", (h,)).fetchone():
        return [{"aba": "", "ok": True, "duplicado": True, "motivo": "Já importei uma planilha com este mesmo conteúdo."}]
    res = processar(con, dados, arquivo, pasta, **kw)
    if all(r.get("ok") for r in res):
        con.execute("INSERT OR IGNORE INTO planilhas_arquivos(hash, nome, quando) VALUES(?,?,?)",
                    (h, (arquivo or "")[:120], kw.get("agora") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
    return res


def pasta_de_entrada(base: Path) -> Path:
    p = heimdall_pastas.finance_sheets(base)
    for pasta in (p, heimdall_pastas.finance_imported(p)):
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            pasta.chmod(0o700)
        except OSError:
            pass
    return p


def processar_pasta(con, base: Path, agora: str = None, modelo=None) -> list:
    """Importa o que foi solto em sheets/. Sucesso vai para imported/; dúvida vira pergunta na página Planilhas e o arquivo sai da pasta."""
    entrada = pasta_de_entrada(base)
    saida = []
    for arq in sorted(entrada.iterdir()):
        if not arq.is_file() or arq.name.startswith(".") or arq.suffix.lower() not in EXT_PLANILHA:
            continue
        try:
            if datetime.now().timestamp() - arq.stat().st_mtime < 3:
                continue  # ainda sendo copiado
            dados = arq.read_bytes()
            res = importar_arquivo(con, dados, arq.name, base, agora=agora, modelo=modelo)
            if any(r.get("duplicado") for r in res):
                arq.unlink()
            else:
                destino = heimdall_pastas.finance_imported(entrada) / arq.name
                if destino.exists():
                    destino = heimdall_pastas.finance_imported(entrada) / f"{datetime.now():%Y%m%d-%H%M%S}-{arq.name}"
                arq.replace(destino)
            saida.append({"arquivo": arq.name, "resultados": res})
        except fn.ErroFinance as ex:
            saida.append({"arquivo": arq.name, "ok": False, "motivo": str(ex)})
        except OSError as ex:
            saida.append({"arquivo": arq.name, "ok": False, "motivo": f"Não consegui ler o arquivo ({type(ex).__name__})."})
    return saida


# --------------------------------------------------------------------------------------------
# Registros e valores
# --------------------------------------------------------------------------------------------
def registros(con, cid: int) -> list:
    return [(r["id"], _json(r["dados"], {})) for r in con.execute("SELECT id, dados FROM registros WHERE conjunto_id=? ORDER BY id", (cid,))]


def _chave_ordem(v: str):
    try:
        return (1, fn.parse_data(v), 0)
    except ValueError:
        pass
    try:
        return (0, "", fn.parse_valor(v))
    except ValueError:
        return (2, fn.norm(v), 0)


def _valor_centavos(v: str):
    try:
        return fn.parse_valor(v)
    except ValueError:
        return None


# --------------------------------------------------------------------------------------------
# Visões
# --------------------------------------------------------------------------------------------
def config_padrao(c) -> dict:
    return {"colunas": [k for k, _ in colunas_do_conjunto(c)], "ordem": "", "dir": "asc", "filtro_col": "", "filtro_valor": "", "agrupar": "", "somar": ""}


def visoes(con, cid: int = None) -> list:
    q = "SELECT v.*, c.nome AS conjunto_nome FROM visoes v JOIN conjuntos c ON c.id=v.conjunto_id" + (" WHERE v.conjunto_id=?" if cid else "") + " ORDER BY c.nome, v.nome"
    return [dict(v, cfg=_json(v["config"], {})) for v in con.execute(q, (cid,) if cid else ())]


def visao(con, vid: int):
    v = con.execute("SELECT * FROM visoes WHERE id=?", (vid,)).fetchone()
    return dict(v, cfg=_json(v["config"], {})) if v else None


def criar_visao(con, cid: int, nome: str, agora: str = None, copiar_de: int = None) -> int:
    c = conjunto(con, cid)
    nome = (nome or "").strip()[:60]
    if not c or not nome:
        raise fn.ErroFinance("Dê um nome para a visão.")
    if con.execute("SELECT 1 FROM visoes WHERE conjunto_id=? AND nome=?", (cid, nome)).fetchone():
        raise fn.ErroFinance("Já existe uma visão com esse nome neste conjunto.")
    cfg = config_padrao(c)
    if copiar_de:
        o = visao(con, copiar_de)
        if o and o["conjunto_id"] == cid:
            cfg = dict(o["cfg"])
    cur = con.execute("INSERT INTO visoes(conjunto_id, nome, config, criado) VALUES(?,?,?,?)",
                      (cid, nome, json.dumps(cfg, ensure_ascii=False), agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    return cur.lastrowid


def _salvar_cfg(con, vid: int, cfg: dict) -> None:
    con.execute("UPDATE visoes SET config=? WHERE id=?", (json.dumps(cfg, ensure_ascii=False), vid))
    con.commit()


def _validas(con, v) -> set:
    return {k for k, _ in colunas_do_conjunto(conjunto(con, v["conjunto_id"]))}


def mover_coluna(con, vid: int, chave: str, delta: int) -> None:
    v = visao(con, vid)
    cols = v["cfg"].get("colunas", [])
    if chave not in cols:
        raise fn.ErroFinance("Essa coluna não está na visão.")
    i = cols.index(chave)
    j = max(0, min(len(cols) - 1, i + delta))
    cols.insert(j, cols.pop(i))
    v["cfg"]["colunas"] = cols
    _salvar_cfg(con, vid, v["cfg"])


def tirar_coluna(con, vid: int, chave: str) -> None:
    v = visao(con, vid)
    cols = v["cfg"].get("colunas", [])
    if len(cols) <= 1:
        raise fn.ErroFinance("A visão precisa ter pelo menos uma coluna.")
    v["cfg"]["colunas"] = [c for c in cols if c != chave]
    _salvar_cfg(con, vid, v["cfg"])


def por_coluna(con, vid: int, chave: str) -> None:
    v = visao(con, vid)
    if chave not in _validas(con, v):
        raise fn.ErroFinance("Coluna desconhecida.")
    if chave not in v["cfg"]["colunas"]:
        v["cfg"]["colunas"].append(chave)
        _salvar_cfg(con, vid, v["cfg"])


def definir_regras(con, vid: int, ordem: str = "", direcao: str = "asc", filtro_col: str = "", filtro_valor: str = "", agrupar: str = "", somar: str = "") -> None:
    v = visao(con, vid)
    ok = _validas(con, v)
    for x in (ordem, filtro_col, agrupar, somar):
        if x and x not in ok:
            raise fn.ErroFinance("Coluna desconhecida.")
    v["cfg"].update({"ordem": ordem, "dir": "desc" if direcao == "desc" else "asc", "filtro_col": filtro_col, "filtro_valor": (filtro_valor or "").strip()[:80],
                     "agrupar": agrupar, "somar": somar})
    _salvar_cfg(con, vid, v["cfg"])


def renomear_visao(con, vid: int, nome: str) -> None:
    nome = (nome or "").strip()[:60]
    v = visao(con, vid)
    if not nome:
        raise fn.ErroFinance("Dê um nome para a visão.")
    if con.execute("SELECT 1 FROM visoes WHERE conjunto_id=? AND nome=? AND id<>?", (v["conjunto_id"], nome, vid)).fetchone():
        raise fn.ErroFinance("Já existe uma visão com esse nome neste conjunto.")
    con.execute("UPDATE visoes SET nome=? WHERE id=?", (nome, vid))
    con.commit()


def apagar_visao(con, vid: int) -> None:
    con.execute("DELETE FROM visoes WHERE id=?", (vid,))
    con.commit()


def aplicar_visao(con, cid: int, cfg: dict = None) -> dict:
    """Linhas da visão, calculadas na hora a partir dos registros: {colunas[(chave, nome)], linhas[[texto]], total, filtradas, grupos}."""
    c = conjunto(con, cid)
    nomes = dict(colunas_do_conjunto(c))
    cfg = cfg or config_padrao(c)
    cols = [k for k in cfg.get("colunas", []) if k in nomes] or list(nomes)
    regs = [d for _, d in registros(con, cid)]
    total = len(regs)
    fc, fv = cfg.get("filtro_col", ""), fn.norm(cfg.get("filtro_valor", ""))
    if fc in nomes and fv:
        regs = [d for d in regs if fv in fn.norm(d.get(fc, ""))]
    o = cfg.get("ordem", "")
    if o in nomes:
        regs.sort(key=lambda d: _chave_ordem(d.get(o, "")), reverse=cfg.get("dir") == "desc")
    saida = {"colunas": [(k, nomes[k]) for k in cols], "linhas": [[d.get(k, "") for k in cols] for d in regs], "total": total, "filtradas": len(regs), "grupos": None}
    g, s = cfg.get("agrupar", ""), cfg.get("somar", "")
    if g in nomes:
        acum = {}
        for d in regs:
            chave = d.get(g, "") or "(vazio)"
            item = acum.setdefault(chave, {"n": 0, "soma": 0, "tem": False})
            item["n"] += 1
            if s in nomes:
                val = _valor_centavos(d.get(s, ""))
                if val is not None:
                    item["soma"] += val
                    item["tem"] = True
        grupos = [(k, x["n"], x["soma"] if x["tem"] else None) for k, x in acum.items()]
        grupos.sort(key=lambda t: (-(t[2] or 0), t[0]) if s in nomes else (-t[1], t[0]))
        saida["grupos"] = {"coluna": nomes[g], "soma": nomes.get(s, ""), "linhas": grupos}
    return saida


# --------------------------------------------------------------------------------------------
# Resumos de investimentos e empréstimos
# --------------------------------------------------------------------------------------------
def _so_lote_atual(regs: list, coluna_lote: str) -> list:
    """Conexões como a do Pluggy gravam uma foto por dia: vale só a mais recente (o que sumiu da conexão deixa de aparecer)."""
    if not coluna_lote:
        return regs
    ultimo = max((d.get(coluna_lote, "") for _, d in regs), default="")
    return [(rid, d) for rid, d in regs if d.get(coluna_lote, "") == ultimo]


def _mais_recente(regs: list, papel_data: str, chave_item: str) -> list:
    """Uma linha por item (ativo ou contrato): a mais recente pela coluna de data, ou a última importada."""
    por_item = {}
    for rid, d in regs:
        item = fn.norm(d.get(chave_item, "")) if chave_item else str(rid)
        quando = ""
        if papel_data:
            try:
                quando = fn.parse_data(d.get(papel_data, ""))
            except ValueError:
                quando = ""
        atual = por_item.get(item)
        if atual is None or (quando, rid) >= (atual[0], atual[1]):
            por_item[item] = (quando, rid, d)
    return [(q, d) for q, _, d in por_item.values()]


def linhas_atuais(con, nome_conjunto: str) -> list:
    """Linhas (dicts por chave) da foto mais recente de um conjunto de conexão, ou todas se o conjunto não tem foto. Lista vazia se o conjunto não existe."""
    c = con.execute("SELECT * FROM conjuntos WHERE nome=?", (nome_conjunto,)).fetchone()
    if not c:
        return []
    return [d for _, d in _so_lote_atual(registros(con, c["id"]), _json(c["papeis"], {}).get("lote", ""))]


def resumo_investimentos(con) -> dict:
    itens, total, sem_valor = [], 0, 0
    for c in con.execute("SELECT * FROM conjuntos WHERE tipo='investimentos' ORDER BY nome"):
        p = _json(c["papeis"], {})
        regs = _so_lote_atual(registros(con, c["id"]), p.get("lote", ""))
        for quando, d in _mais_recente(regs, p.get("data", ""), p.get("id") or p.get("ativo", "")):
            v = _valor_centavos(d.get(p.get("valor", ""), "")) if p.get("valor") else None
            if v is None and p.get("quantidade") and p.get("preco"):
                try:
                    q = fn.parse_valor(d.get(p["quantidade"], "")) / 100
                    pr = fn.parse_valor(d.get(p["preco"], ""))
                    v = int(round(q * pr))
                except ValueError:
                    v = None
            if v is None:
                sem_valor += 1
            else:
                total += v
            itens.append({"conjunto": c["nome"], "ativo": d.get(p.get("ativo", ""), ""), "tipo": d.get(p.get("tipo_ativo", ""), "") or "Sem tipo",
                          "instituicao": d.get(p.get("instituicao", ""), ""), "valor": v, "data": quando, "rentabilidade": d.get(p.get("rentabilidade", ""), "")})
    por_tipo = {}
    for i in itens:
        if i["valor"] is not None:
            por_tipo[i["tipo"]] = por_tipo.get(i["tipo"], 0) + i["valor"]
    return {"itens": sorted(itens, key=lambda i: -(i["valor"] or 0)), "total": total, "por_tipo": sorted(por_tipo.items(), key=lambda kv: -kv[1]), "sem_valor": sem_valor}


_CHAVES_TIPO = ("tipo", "modalidade", "produto", "type", "productname", "finalidade")


def resumo_emprestimos(con, categoria: str = "") -> dict:
    """Dívidas das planilhas e do Pluggy, cada uma numa categoria (veículo, imóvel, consignado, pessoal, outros). `categoria` filtra."""
    itens, sem_valor = [], 0
    for c in con.execute("SELECT * FROM conjuntos WHERE tipo='emprestimos' ORDER BY nome"):
        p = _json(c["papeis"], {})
        regs = _so_lote_atual(registros(con, c["id"]), p.get("lote", ""))
        for quando, d in _mais_recente(regs, p.get("coletado", ""), p.get("id") or p.get("contrato", "")):
            s = _valor_centavos(d.get(p.get("saldo", ""), "")) if p.get("saldo") else None
            pa = _valor_centavos(d.get(p.get("parcela", ""), "")) if p.get("parcela") else None
            texto = " ".join([c["nome"], d.get(p.get("contrato", ""), ""), d.get(p.get("credor", ""), "")] +
                             [v for k, v in d.items() if any(x in k for x in _CHAVES_TIPO)])
            cat = categoria_credito(texto)
            if categoria and cat != categoria:
                continue
            if s is None and pa is None:
                sem_valor += 1
            itens.append({"conjunto": c["nome"], "conjunto_id": c["id"], "categoria": cat, "contrato": d.get(p.get("contrato", ""), "") or c["nome"],
                          "credor": d.get(p.get("credor", ""), ""), "saldo": s, "parcela": pa, "taxa": d.get(p.get("taxa", ""), ""),
                          "vencimento": d.get(p.get("vencimento", ""), ""), "restantes": d.get(p.get("restantes", ""), ""),
                          "pagas": d.get("installments_paidinstallments", ""), "contratacao": d.get("contractdate", ""),
                          "contratado": _valor_centavos(d.get("contractamount", "")) if d.get("contractamount") else None})
    return {"itens": sorted(itens, key=lambda i: -(i["saldo"] or 0)), "saldo": sum(i["saldo"] or 0 for i in itens),
            "parcelas": sum(i["parcela"] or 0 for i in itens), "sem_valor": sem_valor}


def categorias_de_credito(con) -> list:
    """[(categoria, quantidade)] das categorias que existem nos dados, na ordem de CATEGORIAS_CREDITO."""
    cont = {}
    for i in resumo_emprestimos(con)["itens"]:
        cont[i["categoria"]] = cont.get(i["categoria"], 0) + 1
    return [(k, cont[k]) for k in CATEGORIAS_CREDITO if k in cont]
