#!/usr/bin/env python3
"""Núcleo do Heimdall Finance: banco SQLite local, leitura de extratos OFX e CSV, categorias por regras e relatórios.

Nada aqui usa internet: os extratos entram por arquivo e o banco fica só no seu Mac (pasta dados_financas, fora do git).
Valores são guardados em centavos (inteiros); gasto é negativo, entrada é positiva.
"""
import csv
import hashlib
import io
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

SEM_CATEGORIA = "Sem categoria"
# nome, tipo: gasto, renda ou neutra (neutra fica fora de receitas e despesas: pagamento de fatura, investimentos, entre contas)
CATEGORIAS_PADRAO = [
    ("Mercado", "gasto"), ("Restaurantes", "gasto"), ("Transporte", "gasto"), ("Moradia e contas", "gasto"), ("Saúde", "gasto"),
    ("Assinaturas", "gasto"), ("Educação", "gasto"), ("Lazer e viagens", "gasto"), ("Compras", "gasto"), ("Impostos e tarifas", "gasto"),
    ("Transferências", "gasto"), ("Saques", "gasto"), ("Outros gastos", "gasto"), ("Parcelamento de fatura", "gasto"),
    ("Salário", "renda"), ("Outras receitas", "renda"),
    ("Pagamento de fatura", "neutra"), ("Fatura de terceiros", "neutra"), ("Investimentos", "neutra"), ("Entre minhas contas", "neutra"),
    (SEM_CATEGORIA, "gasto"),
]
# palavra ou trecho (já sem acento e em minúsculas) -> categoria
REGRAS_PADRAO = [
    ("supermercado", "Mercado"), ("mercado ", "Mercado"), ("atacadao", "Mercado"), ("carrefour", "Mercado"), ("pao de acucar", "Mercado"),
    ("assai", "Mercado"), ("hortifruti", "Mercado"), ("sacolao", "Mercado"), ("dia supermercados", "Mercado"),
    ("restaurante", "Restaurantes"), ("lanchonete", "Restaurantes"), ("padaria", "Restaurantes"), ("ifood", "Restaurantes"), ("rappi", "Restaurantes"),
    ("mcdonald", "Restaurantes"), ("burger", "Restaurantes"), ("pizz", "Restaurantes"), ("cafeteria", "Restaurantes"), ("starbucks", "Restaurantes"),
    ("uber", "Transporte"), ("cabify", "Transporte"), ("99app", "Transporte"), ("99 pop", "Transporte"), ("posto ", "Transporte"), ("ipiranga", "Transporte"),
    ("combustivel", "Transporte"), ("estacionamento", "Transporte"), ("sem parar", "Transporte"), ("conectcar", "Transporte"), ("bilhete unico", "Transporte"),
    ("aluguel", "Moradia e contas"), ("condominio", "Moradia e contas"), ("iptu", "Moradia e contas"), ("enel", "Moradia e contas"),
    ("sabesp", "Moradia e contas"), ("comgas", "Moradia e contas"), ("energia eletrica", "Moradia e contas"), ("vivo", "Moradia e contas"),
    ("claro", "Moradia e contas"), ("tim ", "Moradia e contas"), ("internet", "Moradia e contas"),
    ("farmacia", "Saúde"), ("drogaria", "Saúde"), ("drogasil", "Saúde"), ("droga raia", "Saúde"), ("pague menos", "Saúde"), ("unimed", "Saúde"),
    ("amil", "Saúde"), ("hospital", "Saúde"), ("clinica", "Saúde"), ("laboratorio", "Saúde"), ("fleury", "Saúde"),
    ("netflix", "Assinaturas"), ("spotify", "Assinaturas"), ("amazon prime", "Assinaturas"), ("disney", "Assinaturas"), ("youtube", "Assinaturas"),
    ("icloud", "Assinaturas"), ("apple.com/bill", "Assinaturas"), ("google one", "Assinaturas"), ("globoplay", "Assinaturas"), ("deezer", "Assinaturas"),
    ("openai", "Assinaturas"), ("anthropic", "Assinaturas"), ("claude.ai", "Assinaturas"),
    ("faculdade", "Educação"), ("escola", "Educação"), ("udemy", "Educação"), ("alura", "Educação"), ("coursera", "Educação"), ("curso", "Educação"),
    ("cinema", "Lazer e viagens"), ("ingresso", "Lazer e viagens"), ("steam", "Lazer e viagens"), ("playstation", "Lazer e viagens"),
    ("airbnb", "Lazer e viagens"), ("booking", "Lazer e viagens"), ("decolar", "Lazer e viagens"), ("hotel", "Lazer e viagens"),
    ("mercado livre", "Compras"), ("mercadolivre", "Compras"), ("magalu", "Compras"), ("americanas", "Compras"), ("shopee", "Compras"),
    ("shein", "Compras"), ("aliexpress", "Compras"), ("amazon", "Compras"), ("renner", "Compras"),
    ("iof", "Impostos e tarifas"), ("tarifa", "Impostos e tarifas"), ("anuidade", "Impostos e tarifas"), ("juros", "Impostos e tarifas"),
    ("multa", "Impostos e tarifas"), ("darf", "Impostos e tarifas"), ("imposto", "Impostos e tarifas"),
    ("saque", "Saques"), ("pagamento da fatura de", "Parcelamento de fatura"),
    ("salario", "Salário"), ("folha de pagamento", "Salário"), ("proventos", "Salário"), ("pro labore", "Salário"),
    ("pagamento de fatura", "Pagamento de fatura"), ("pagamento fatura", "Pagamento de fatura"), ("pgto fatura", "Pagamento de fatura"),
    ("pag fatura", "Pagamento de fatura"), ("fatura cartao", "Pagamento de fatura"),
    ("pagamento recebido", "Pagamento de fatura"), ("pagamento em ", "Pagamento de fatura"), ("pagamento efetuado", "Pagamento de fatura"), ("fatura itau", "Pagamento de fatura"), ("fatura nubank", "Pagamento de fatura"), ("fatura mercado", "Pagamento de fatura"), ("rend pago aplic", "Investimentos"),
    ("aplicacao", "Investimentos"), ("resgate", "Investimentos"), ("tesouro direto", "Investimentos"), ("cdb", "Investimentos"),
    ("xp investimentos", "Investimentos"), ("rico investimentos", "Investimentos"), ("corretora", "Investimentos"),
    ("transferencia", "Transferências"), ("pix", "Transferências"), ("ted ", "Transferências"),
]
_PREFIXOS_IGNORADOS = {"compra", "debito", "credito", "pix", "transferencia", "transf", "pagamento", "pag", "pgto", "cartao", "em", "de", "no", "na", "a", "o",
                       "recebido", "enviado", "enviada", "recebida", "via", "ted", "doc", "para", "por", "com", "do", "da", "dos", "das"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS transacoes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, conta TEXT NOT NULL, data TEXT NOT NULL, valor INTEGER NOT NULL,
  descricao TEXT NOT NULL, desc_norm TEXT NOT NULL, categoria TEXT NOT NULL DEFAULT 'Sem categoria',
  manual INTEGER NOT NULL DEFAULT 0, hash TEXT NOT NULL UNIQUE, importado_em TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_tr_data ON transacoes(data);
CREATE TABLE IF NOT EXISTS regras(
  id INTEGER PRIMARY KEY AUTOINCREMENT, padrao TEXT NOT NULL, categoria TEXT NOT NULL, origem TEXT NOT NULL, UNIQUE(padrao, origem));
CREATE TABLE IF NOT EXISTS categorias(nome TEXT PRIMARY KEY, tipo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orcamentos(categoria TEXT PRIMARY KEY, limite INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS previstos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, descricao TEXT NOT NULL, valor INTEGER NOT NULL, dia INTEGER NOT NULL, inicio TEXT NOT NULL, fim TEXT);
CREATE TABLE IF NOT EXISTS ignorados(chave TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS boletos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, linha TEXT UNIQUE NOT NULL, valor INTEGER, vencimento TEXT, banco TEXT, beneficiario TEXT, tipo TEXT, segmento TEXT,
  arquivo TEXT, situacao TEXT NOT NULL DEFAULT 'aberto', criado_em TEXT);
CREATE TABLE IF NOT EXISTS importacoes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, arquivo TEXT, conta TEXT, quando TEXT, formato TEXT, novas INTEGER, repetidas INTEGER);
"""


class ErroFinance(Exception):
    """Erro com mensagem própria para o usuário."""


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9./& ]+", " ", s)).strip()


def brl(centavos: int, sinal: bool = False) -> str:
    v = abs(int(centavos))
    texto = f"R$ {v // 100:,}".replace(",", ".") + f",{v % 100:02d}"
    if centavos < 0:
        return "-" + texto
    return ("+" + texto) if sinal and centavos > 0 else texto


def data_br(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


# --------------------------------------------------------------------------------------------
# Banco
# --------------------------------------------------------------------------------------------
def conectar(caminho) -> sqlite3.Connection:
    con = sqlite3.connect(str(caminho), check_same_thread=False, timeout=15)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    if "hash_arquivo" not in {r["name"] for r in con.execute("PRAGMA table_info(importacoes)")}:
        con.execute("ALTER TABLE importacoes ADD COLUMN hash_arquivo TEXT")
    if "importacao_id" not in {r["name"] for r in con.execute("PRAGMA table_info(transacoes)")}:
        con.execute("ALTER TABLE transacoes ADD COLUMN importacao_id INTEGER")
    # lançamentos importados antes desta coluna existir: liga cada um à importação de mesma conta e mesmo instante
    con.execute("UPDATE transacoes SET importacao_id = (SELECT MAX(i.id) FROM importacoes i WHERE i.conta = transacoes.conta AND i.quando = transacoes.importado_em) WHERE importacao_id IS NULL")
    for nome, tipo in CATEGORIAS_PADRAO:
        con.execute("INSERT OR IGNORE INTO categorias(nome, tipo) VALUES(?, ?)", (nome, tipo))
    for padrao, cat in REGRAS_PADRAO:
        con.execute("INSERT OR IGNORE INTO regras(padrao, categoria, origem) VALUES(?, ?, 'padrao')", (norm(padrao) if not padrao.endswith(" ") else norm(padrao) + " ", cat))
    con.commit()
    return con


def tipos(con) -> dict:
    return {r["nome"]: r["tipo"] for r in con.execute("SELECT nome, tipo FROM categorias")}


def categorizar(con, desc_norm: str, regras: list = None) -> str:
    """Primeiro as regras suas (a mais longa vence), depois as padrão."""
    if regras is None:
        regras = _regras(con)
    alvo = " " + desc_norm + " "
    for padrao, cat in regras:
        if " " + padrao in alvo:  # o trecho começa em início de palavra ("amil" não casa com "familia")
            return cat
    return SEM_CATEGORIA


def _regras(con) -> list:
    lin = con.execute("SELECT padrao, categoria, origem FROM regras").fetchall()
    return [(r["padrao"], r["categoria"]) for r in sorted(lin, key=lambda r: (r["origem"] != "usuario", -len(r["padrao"])))]


# --------------------------------------------------------------------------------------------
# Leitura de valores e datas
# --------------------------------------------------------------------------------------------
def parse_valor(texto) -> int:
    s = re.sub(r"[Rr]\$|\s", "", str(texto or ""))
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")")) or s.endswith("-")
    s = s.strip("()-+")
    if not s:
        raise ValueError("valor vazio")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) <= 2 or s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s and len(s.split(".")[-1]) == 3 and len(s.split(".")[0]) <= 3 and s.split(".")[0] != "0":
        s = s.replace(".", "")  # 1.234 = mil duzentos e trinta e quatro
    try:
        v = int((Decimal(s) * 100).to_integral_value())
    except InvalidOperation as ex:
        raise ValueError(f"valor inválido: {texto}") from ex
    return -v if neg else v


def parse_data(texto) -> str:
    s = str(texto or "").strip()[:19]
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    if re.fullmatch(r"\d{8}.*", s):
        return datetime.strptime(s[:8], "%Y%m%d").strftime("%Y-%m-%d")
    raise ValueError(f"data inválida: {texto}")


# --------------------------------------------------------------------------------------------
# Leitores de arquivo
# --------------------------------------------------------------------------------------------
def decodificar(dados: bytes) -> str:
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(cod)
        except UnicodeDecodeError:
            continue
    return dados.decode("utf-8", "replace")


def parse_ofx(texto: str) -> list:
    saida = []
    for bloco in re.split(r"<STMTTRN>", texto, flags=re.I)[1:]:
        bloco = re.split(r"</STMTTRN>|</BANKTRANLIST>|</CCSTMTTRNRS>", bloco, flags=re.I)[0]
        campos = {m.group(1).upper(): m.group(2).strip() for m in re.finditer(r"<(\w+)>([^<\r\n]*)", bloco)}
        if "DTPOSTED" not in campos or "TRNAMT" not in campos:
            continue
        partes = [campos.get("NAME", ""), campos.get("MEMO", "")]
        desc = " - ".join(dict.fromkeys(p for p in partes if p)) or "(sem descrição)"
        saida.append({"data": parse_data(campos["DTPOSTED"]), "valor": parse_valor(campos["TRNAMT"]),
                      "descricao": desc, "fitid": campos.get("FITID", "")})
    return saida


_COL = {
    "data": ("data", "date", "release_date", "dt", "data lancamento", "data do lancamento", "data da compra", "data movimento", "data transacao"),
    "desc": ("descricao", "historico", "lancamento", "title", "estabelecimento", "memo", "detalhes", "descricao do lancamento", "titulo", "name"),
    "valor": ("valor", "amount", "transaction_net_amount", "value", "valor r$", "valor rs", "quantia", "valor da transacao"),
    "debito": ("debito", "saida", "saidas", "valor debito"),
    "credito": ("credito", "entrada", "entradas", "valor credito"),
    "tipo": ("tipo", "tipo de lancamento", "d/c", "dc"),
    "id": ("identificador", "id", "codigo", "documento", "numero documento"),
}


def _acha(cabecalho: list, chave: str):
    nomes = [norm(c) for c in cabecalho]
    for cand in _COL[chave]:
        if cand in nomes:
            return nomes.index(cand)
    return None


def parse_csv(texto: str, inverter: bool = False) -> list:
    linhas = texto.splitlines()
    amostra = "\n".join(linhas[:40])
    delim = ";" if amostra.count(";") > amostra.count(",") else ("\t" if amostra.count("\t") > amostra.count(",") else ",")
    tabela = list(csv.reader(io.StringIO(texto), delimiter=delim))
    ini = None
    for i, lin in enumerate(tabela[:40]):
        if _acha(lin, "data") is not None and (_acha(lin, "valor") is not None or _acha(lin, "debito") is not None or _acha(lin, "credito") is not None):
            ini = i
            break
    if ini is None:
        raise ErroFinance("Não achei o cabeçalho do CSV. Ele precisa ter colunas de data e de valor (por exemplo: Data, Descrição, Valor).")
    cab = tabela[ini]
    ci = {k: _acha(cab, k) for k in _COL}
    saida = []
    for lin in tabela[ini + 1:]:
        if not any(c.strip() for c in lin):
            continue
        try:
            def pega(k):
                return lin[ci[k]].strip() if ci[k] is not None and ci[k] < len(lin) else ""
            data = parse_data(pega("data"))
            if ci["valor"] is not None and pega("valor"):
                v = parse_valor(pega("valor"))
            else:
                d, c = pega("debito"), pega("credito")
                v = (parse_valor(c) if c else 0) - (abs(parse_valor(d)) if d else 0)
            t = norm(pega("tipo"))
            if t and ci["valor"] is not None and v > 0 and t in ("d", "debito", "saida"):
                v = -v
            if inverter:
                v = -v
            saida.append({"data": data, "valor": v, "descricao": pega("desc") or "(sem descrição)", "fitid": pega("id")})
        except (ValueError, IndexError):
            continue  # linha de total, rodapé ou lixo
    if not saida:
        raise ErroFinance("O CSV tem cabeçalho, mas nenhuma linha com data e valor que eu consiga ler.")
    return saida


def ler_extrato(dados: bytes, inverter: bool = False) -> tuple:
    """(formato, lista de lançamentos)."""
    texto = decodificar(dados)
    if re.search(r"<OFX>|OFXHEADER", texto[:4000], flags=re.I):
        itens = parse_ofx(texto)
        if not itens:
            raise ErroFinance("O arquivo OFX não tem lançamentos que eu consiga ler.")
        return "OFX", itens
    return "CSV", parse_csv(texto, inverter)


# --------------------------------------------------------------------------------------------
# Importação
# --------------------------------------------------------------------------------------------
def importar(con, dados: bytes, arquivo: str, conta: str, inverter: bool = False, agora: str = None) -> dict:
    conta = (conta or "").strip()[:60]
    if not conta:
        raise ErroFinance("Diga a que conta ou cartão o extrato pertence (por exemplo: Itaú conta ou Nubank cartão).")
    formato, itens = ler_extrato(dados, inverter)
    return importar_itens(con, itens, formato, arquivo, conta, agora)


def arquivo_ja_importado(con, hash_arquivo: str) -> bool:
    """True se um arquivo com exatamente o mesmo conteúdo já foi importado."""
    return bool(hash_arquivo) and con.execute("SELECT 1 FROM importacoes WHERE hash_arquivo=? LIMIT 1", (hash_arquivo,)).fetchone() is not None


def apagar_importacao_vazia(con, importacao_id: int) -> None:
    """Remove do histórico uma importação que não trouxe nada novo (arquivo duplicado)."""
    con.execute("DELETE FROM importacoes WHERE id=? AND novas=0", (importacao_id,))
    con.commit()


def importar_itens(con, itens: list, formato: str, arquivo: str, conta: str, agora: str = None, hash_arquivo: str = "") -> dict:
    """Grava lançamentos já lidos (de OFX, CSV ou PDF), pulando os que já existem."""
    conta = (conta or "").strip()[:60]
    if not conta:
        raise ErroFinance("Diga a que conta ou cartão o extrato pertence (por exemplo: Itaú conta ou Nubank cartão).")
    agora = agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    regras = _regras(con)
    vistos = defaultdict(int)
    novas = repetidas = 0
    imp_id = con.execute("INSERT INTO importacoes(arquivo, conta, quando, formato, novas, repetidas, hash_arquivo) VALUES(?,?,?,?,0,0,?)", ((arquivo or "")[:120], conta, agora, formato, hash_arquivo or None)).lastrowid
    for it in itens:
        dn = norm(it["descricao"])
        if it.get("fitid"):
            chave = f"{conta}|fitid|{it['fitid']}|{it['data']}|{it['valor']}"
        else:
            base = f"{conta}|{it['data']}|{it['valor']}|{dn}"
            vistos[base] += 1  # dois lançamentos iguais no mesmo dia continuam sendo dois
            chave = f"{base}|{vistos[base]}"
        h = hashlib.sha1(chave.encode("utf-8")).hexdigest()
        cat = categorizar(con, dn, regras)
        if cat == SEM_CATEGORIA and it["valor"] > 0:
            # cartão de crédito não gera renda: crédito sem regra (pagamento, estorno de encargo) fica fora das receitas
            cat = "Pagamento de fatura" if "cartao" in norm(conta) else "Outras receitas"
        cur = con.execute("INSERT OR IGNORE INTO transacoes(conta, data, valor, descricao, desc_norm, categoria, hash, importado_em, importacao_id) VALUES(?,?,?,?,?,?,?,?,?)",
                          (conta, it["data"], it["valor"], it["descricao"][:200], dn[:200], cat, h, agora, imp_id))
        if cur.rowcount:
            novas += 1
        else:
            repetidas += 1
    con.execute("UPDATE importacoes SET novas=?, repetidas=? WHERE id=?", (novas, repetidas, imp_id))
    con.commit()
    return {"formato": formato, "lidas": len(itens), "novas": novas, "repetidas": repetidas, "importacao_id": imp_id}


# --------------------------------------------------------------------------------------------
# Categorias e regras
# --------------------------------------------------------------------------------------------
def padrao_da_descricao(desc_norm: str) -> str:
    """Trecho que identifica o estabelecimento: as duas primeiras palavras úteis (sem números nem palavras de transação)."""
    p = [w for w in desc_norm.split() if w not in _PREFIXOS_IGNORADOS and len(w) >= 3 and not re.fullmatch(r"[\d./&-]+", w)]
    return " ".join(p[:2])


def definir_categoria(con, tid: int, categoria: str, criar_regra: bool = True) -> int:
    """Muda a categoria de um lançamento. Com criar_regra, lançamentos parecidos (não mexidos por você) vão junto. Devolve quantos mudaram."""
    if categoria not in tipos(con):
        raise ErroFinance("Categoria desconhecida.")
    r = con.execute("SELECT desc_norm FROM transacoes WHERE id=?", (tid,)).fetchone()
    if not r:
        raise ErroFinance("Lançamento não encontrado.")
    con.execute("UPDATE transacoes SET categoria=?, manual=1 WHERE id=?", (categoria, tid))
    n = 1
    padrao = padrao_da_descricao(r["desc_norm"]) if criar_regra else ""
    if padrao:
        con.execute("INSERT INTO regras(padrao, categoria, origem) VALUES(?,?, 'usuario') ON CONFLICT(padrao, origem) DO UPDATE SET categoria=excluded.categoria", (padrao, categoria))
        cur = con.execute("UPDATE transacoes SET categoria=? WHERE manual=0 AND id<>? AND (' ' || desc_norm || ' ') LIKE ?", (categoria, tid, f"% {padrao}%"))
        n += cur.rowcount
    con.commit()
    return n


def adicionar_regra(con, padrao: str, categoria: str) -> int:
    p = norm(padrao)
    if len(p) < 3:
        raise ErroFinance("O trecho da regra precisa ter pelo menos 3 letras.")
    if categoria not in tipos(con):
        raise ErroFinance("Categoria desconhecida.")
    con.execute("INSERT INTO regras(padrao, categoria, origem) VALUES(?,?, 'usuario') ON CONFLICT(padrao, origem) DO UPDATE SET categoria=excluded.categoria", (p, categoria))
    cur = con.execute("UPDATE transacoes SET categoria=? WHERE manual=0 AND (' ' || desc_norm || ' ') LIKE ?", (categoria, f"% {p}%"))
    con.commit()
    return cur.rowcount


def apagar_regra(con, rid: int) -> bool:
    cur = con.execute("DELETE FROM regras WHERE id=? AND origem='usuario'", (rid,))
    con.commit()
    return bool(cur.rowcount)


def reaplicar_regras(con) -> int:
    """Passa as regras de novo nos lançamentos que você não categorizou à mão."""
    regras = _regras(con)
    n = 0
    for r in con.execute("SELECT id, desc_norm, valor, categoria FROM transacoes WHERE manual=0").fetchall():
        cat = categorizar(con, r["desc_norm"], regras)
        if cat == SEM_CATEGORIA and r["valor"] > 0:
            cat = "Outras receitas"
        if cat != r["categoria"]:
            con.execute("UPDATE transacoes SET categoria=? WHERE id=?", (cat, r["id"]))
            n += 1
    con.commit()
    return n


# --------------------------------------------------------------------------------------------
# Relatórios
# --------------------------------------------------------------------------------------------
def meses(con) -> list:
    return [r[0] for r in con.execute("SELECT DISTINCT substr(data,1,7) m FROM transacoes ORDER BY m DESC")]


def mes_anterior(mes: str) -> str:
    a, m = int(mes[:4]), int(mes[5:7])
    return f"{a - 1}-12" if m == 1 else f"{a}-{m - 1:02d}"


def nome_mes(mes: str) -> str:
    nomes = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return f"{nomes[int(mes[5:7]) - 1]} de {mes[:4]}"


FATURA_PAGA = "Pagamento de fatura"
TERCEIROS = "Fatura de terceiros"
SEM_FATURA = "Fatura paga sem fatura importada"
VISOES = {"competencia": "por compra (o gasto conta no dia da compra)", "caixa": "por saída de caixa (conta o que saiu das contas, inclusive o pagamento da fatura)"}


def faturas_pagas(con) -> list:
    """Pagamentos de fatura feitos a partir de contas (não de cartões), cada um com 'conferida': True quando há fatura importada que
    explica o pagamento (crédito de pagamento de mesmo valor em algum cartão, até 10 dias de diferença, ou total de uma fatura importada)."""
    creditos = [(r["valor"], r["data"]) for r in con.execute("SELECT valor, data FROM transacoes WHERE valor>0 AND categoria=? AND conta LIKE '%cart_o%'", (FATURA_PAGA,))]
    totais = set()
    for r in con.execute("""SELECT SUM(CASE WHEN valor<0 THEN -valor ELSE 0 END) g,
                                   SUM(CASE WHEN valor>0 AND categoria<>? THEN valor ELSE 0 END) c
                            FROM transacoes WHERE conta LIKE '%cart_o%' AND importacao_id IS NOT NULL GROUP BY importacao_id""", (FATURA_PAGA,)):
        totais.add(r["g"])
        totais.add(r["g"] - r["c"])
    out = []
    for p in con.execute("SELECT id, data, descricao, valor, conta, categoria FROM transacoes WHERE valor<0 AND categoria=? AND NOT (conta LIKE '%cart_o%') ORDER BY data, id", (FATURA_PAGA,)):
        v = -p["valor"]
        try:
            d = datetime.strptime(p["data"], "%Y-%m-%d").date()
        except ValueError:
            d = None
        ok = v in totais or any(cv == v and d is not None and abs((datetime.strptime(cd, "%Y-%m-%d").date() - d).days) <= 10 for cv, cd in creditos)
        out.append({**dict(p), "conferida": ok})
    return out


def sem_fatura(con) -> list:
    """Pagamentos de fatura para os quais não há fatura importada. Podem ser seus (contam como gasto na visão por compra)
    ou de outra pessoa (mude a categoria para 'Fatura de terceiros' e saem das somas)."""
    return [p for p in faturas_pagas(con) if not p["conferida"]]


def _gastos_por_categoria(con, mes: str, tp: dict, visao: str = "competencia", semf: list = None) -> dict:
    out = defaultdict(int)
    if visao == "caixa":
        for r in con.execute("SELECT categoria, SUM(-valor) t FROM transacoes WHERE substr(data,1,7)=? AND valor<0 AND NOT (conta LIKE '%cart_o%') GROUP BY categoria", (mes,)):
            if tp.get(r["categoria"], "gasto") != "neutra" or r["categoria"] == FATURA_PAGA:
                out[r["categoria"]] = r["t"]
        return out
    for r in con.execute("SELECT categoria, SUM(-valor) t FROM transacoes WHERE substr(data,1,7)=? AND valor<0 GROUP BY categoria", (mes,)):
        if tp.get(r["categoria"], "gasto") != "neutra":
            out[r["categoria"]] = r["t"]
    semf = sem_fatura(con) if semf is None else semf
    extra = sum(-p["valor"] for p in semf if p["data"][:7] == mes)
    if extra:
        out[SEM_FATURA] += extra
    return out


def _receitas(con, mes: str, tp: dict, visao: str = "competencia") -> int:
    filtro = " AND NOT (conta LIKE '%cart_o%')" if visao == "caixa" else ""
    return sum(r["valor"] for r in con.execute(f"SELECT categoria, valor FROM transacoes WHERE substr(data,1,7)=? AND valor>0{filtro}", (mes,)) if tp.get(r["categoria"], "renda") != "neutra")


def resumo_mes(con, mes: str, visao: str = "competencia") -> dict:
    visao = visao if visao in VISOES else "competencia"
    tp = tipos(con)
    semf = sem_fatura(con)
    gastos = _gastos_por_categoria(con, mes, tp, visao, semf)
    antes = _gastos_por_categoria(con, mes_anterior(mes), tp, visao, semf)
    despesas = sum(gastos.values())
    receitas = _receitas(con, mes, tp, visao)
    neutros = 0
    for r in con.execute("SELECT id, categoria, valor, conta FROM transacoes WHERE substr(data,1,7)=?", (mes,)):
        if tp.get(r["categoria"]) != "neutra":
            continue
        if visao == "caixa" and (r["categoria"] == FATURA_PAGA and r["valor"] < 0 and "cartao" not in norm(r["conta"]) or "cartao" in norm(r["conta"])):
            continue  # na visão de caixa o pagamento da fatura é gasto, e o cartão nem entra
        neutros += abs(r["valor"])
    if visao == "competencia":
        neutros -= sum(-p["valor"] for p in semf if p["data"][:7] == mes)  # já contados como gasto
    cats = []
    for c, t in sorted(gastos.items(), key=lambda x: -x[1]):
        a = antes.get(c, 0)
        cats.append({"categoria": c, "total": t, "pct": round(100 * t / despesas, 1) if despesas else 0.0, "anterior": a,
                     "variacao": (round(100 * (t - a) / a) if a else None)})
    ids_semf = {p["id"] for p in semf}
    maiores = []
    for r in con.execute("SELECT id, data, descricao, valor, categoria, conta FROM transacoes WHERE substr(data,1,7)=? AND valor<0 ORDER BY valor ASC LIMIT 80", (mes,)):
        neutra = tp.get(r["categoria"], "gasto") == "neutra"
        if visao == "caixa":
            conta_cartao = "cartao" in norm(r["conta"])
            ok = (not conta_cartao) and (not neutra or r["categoria"] == FATURA_PAGA)
        else:
            ok = (not neutra) or r["id"] in ids_semf
        if ok:
            maiores.append(dict(r))
    maiores = maiores[:10]
    n_sem = con.execute("SELECT COUNT(*) FROM transacoes WHERE substr(data,1,7)=? AND categoria=?", (mes, SEM_CATEGORIA)).fetchone()[0]
    return {"mes": mes, "receitas": receitas, "despesas": despesas, "saldo": receitas - despesas, "neutros": neutros,
            "categorias": cats, "maiores": maiores, "sem_categoria": n_sem, "despesas_anterior": sum(antes.values()),
            "visao": visao, "sem_fatura": [p for p in semf if p["data"][:7] == mes]}


def _chave_recorrente(desc_norm: str) -> str:
    """Parte fixa da descrição: sem números (datas, parcelas, códigos) e só as primeiras palavras."""
    s = re.sub(r"\d+", " ", desc_norm)
    s = re.sub(r"\b(parcela|parc|de|em|da|do)\b", " ", s)
    return " ".join([t for t in s.split() if len(t) >= 2][:4])


def _mediana(valores: list):
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) // 2


def _indice_mes(mes: str) -> int:
    return int(mes[:4]) * 12 + int(mes[5:7])


def recorrentes(con, hoje=None) -> dict:
    """Lançamentos que se repetem todo mês (aluguel, assinaturas, salário...), achados pelo histórico.
    Uma série vale se aparece uma vez por mês em pelo menos 3 meses (ou em 2 meses seguidos com valor igual), sem faltar mais que um mês no meio,
    com valor que varia até 25% e dia que varia até 7 dias. Devolve as séries e a situação de cada uma no mês de `hoje`."""
    hoje = hoje or date.today()
    if isinstance(hoje, str):
        hoje = date.fromisoformat(hoje)
    mes_ref = f"{hoje.year}-{hoje.month:02d}"
    tp = tipos(con)
    grupos = defaultdict(lambda: defaultdict(list))
    for r in con.execute("SELECT data, valor, descricao, desc_norm, categoria, conta FROM transacoes WHERE valor<>0 ORDER BY data"):
        if tp.get(r["categoria"]) == "neutra":
            continue
        chave = _chave_recorrente(r["desc_norm"])
        if len(chave) < 3:
            continue
        grupos[(chave, r["valor"] > 0)][r["data"][:7]].append(r)
    series = []
    for (chave, entrada), por_mes in grupos.items():
        unicos = sorted(m for m, l in por_mes.items() if len(l) == 1)
        if len(unicos) < 2 or len(unicos) < 0.7 * len(por_mes):
            continue
        idx = [_indice_mes(m) for m in unicos]
        span = idx[-1] - idx[0] + 1
        if len(unicos) < 0.6 * span or span - len(unicos) > 1 and len(unicos) < 3:
            continue
        linhas = [por_mes[m][0] for m in unicos]
        valores = [abs(x["valor"]) for x in linhas]
        dias = [int(x["data"][8:10]) for x in linhas]
        med = _mediana(valores)
        if len(unicos) == 2:
            if span != 2 or valores[0] != valores[1]:
                continue
        elif med == 0 or (max(valores) - min(valores)) > 0.25 * med:
            continue
        if max(dias) - min(dias) > 7:
            continue
        ult = linhas[-1]
        series.append({"chave": chave, "descricao": ult["descricao"], "categoria": ult["categoria"], "conta": ult["conta"], "entrada": entrada,
                       "valor": med if entrada else -med, "dia": _mediana(dias), "meses": unicos, "n": len(unicos), "ultimo": unicos[-1],
                       "fixo": len(set(valores)) == 1, "parcelada": bool(re.search(r"parcela|\d+ ?/ ?\d+", ult["desc_norm"]))})
    for s in series:
        distancia = _indice_mes(mes_ref) - _indice_mes(s["ultimo"])
        if mes_ref in s["meses"]:
            s["situacao"] = "chegou"
        elif distancia > 2:
            s["situacao"] = "encerrada"
        elif distancia <= 0:
            s["situacao"] = "chegou"
        elif hoje.day <= s["dia"] + 3 and distancia == 1:
            s["situacao"] = "por_vir"
        else:
            s["situacao"] = "atrasada"
    series.sort(key=lambda s: (s["entrada"], s["dia"], s["chave"]))
    ativas = [s for s in series if s["situacao"] != "encerrada"]
    return {"mes": mes_ref, "series": series,
            "gasto_mensal": -sum(s["valor"] for s in ativas if not s["entrada"]), "renda_mensal": sum(s["valor"] for s in ativas if s["entrada"])}


_PARCELA_TEXTO = re.compile(r"parc(?:ela)?\.?\s*(\d{1,2})\s*(?:/|de)\s*(\d{1,2})\b")
_PARCELA_FIM = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})$")


def _parcela_da_descricao(desc_norm: str, conta: str):
    """(parcela atual, total, descrição sem a parcela) ou None. Aceita 'parcela 3 de 10', 'parc 03/10' e, só em cartão, '... 03/10' no fim."""
    m = _PARCELA_TEXTO.search(desc_norm)
    if not m and "cartao" in norm(conta):
        m = _PARCELA_FIM.search(desc_norm.strip())
    if not m:
        return None
    a, t = int(m.group(1)), int(m.group(2))
    if not (2 <= t <= 60 and 1 <= a <= t):
        return None
    return a, t, (desc_norm[:m.start()] + " " + desc_norm[m.end():]).strip()


def _soma_meses(mes: str, k: int) -> str:
    i = _indice_mes(mes) - 1 + k
    return f"{i // 12}-{i % 12 + 1:02d}"


def parcelamentos(con, hoje=None) -> list:
    """Parcelamentos achados nos extratos e faturas (parcela X de Y): valor, quantas já saíram, quantas faltam e o mês de cada parcela que falta."""
    hoje = hoje or date.today()
    if isinstance(hoje, str):
        hoje = date.fromisoformat(hoje)
    mes_ref = f"{hoje.year}-{hoje.month:02d}"
    ign = {r["chave"] for r in con.execute("SELECT chave FROM ignorados")}
    grupos = {}
    for r in con.execute("SELECT data, valor, descricao, desc_norm, categoria, conta FROM transacoes WHERE valor<0 ORDER BY data"):
        p = _parcela_da_descricao(r["desc_norm"], r["conta"])
        if not p:
            continue
        a, t, base = p
        chave = f"parcela:{_chave_recorrente(base)}:{t}:{abs(r['valor'])}"
        if len(_chave_recorrente(base)) < 3:
            continue
        g = grupos.setdefault(chave, {"chave": chave, "base": _chave_recorrente(base), "descricao": re.sub(r"\s*parc\w*\.?\s*\d+\s*(?:/|de)\s*\d+", "", r["descricao"], flags=re.I).strip() or r["descricao"],
                                      "total": t, "valor": r["valor"], "conta": r["conta"], "categoria": r["categoria"], "maior": 0, "ultimo_mes": "", "dia": 1})
        if a >= g["maior"]:
            g["maior"], g["ultimo_mes"], g["dia"] = a, r["data"][:7], int(r["data"][8:10])
    saida = []
    for g in grupos.values():
        falta = g["total"] - g["maior"]
        g["faltam"] = falta
        g["ignorado"] = g["chave"] in ign
        g["proximas"] = [{"mes": _soma_meses(g["ultimo_mes"], k), "numero": g["maior"] + k} for k in range(1, falta + 1)
                         if _soma_meses(g["ultimo_mes"], k) >= mes_ref]
        saida.append(g)
    saida.sort(key=lambda g: (g["ignorado"], g["descricao"]))
    return saida


def adicionar_previsto(con, descricao: str, texto_valor: str, dia, inicio: str = "", fim: str = "", entrada: bool = False) -> int:
    descricao = (descricao or "").strip()
    if not descricao:
        raise ErroFinance("Diga o que é este pagamento.")
    try:
        v = abs(parse_valor(texto_valor))
    except (ValueError, TypeError):
        v = 0
    if v == 0:
        raise ErroFinance("Valor inválido. Digite em reais, por exemplo 1500,00.")
    try:
        dia = int(dia)
    except (TypeError, ValueError):
        raise ErroFinance("Dia do mês inválido: use de 1 a 31.")
    if not 1 <= dia <= 31:
        raise ErroFinance("Dia do mês inválido: use de 1 a 31.")
    inicio = (inicio or "").strip() or date.today().strftime("%Y-%m")
    fim = (fim or "").strip()
    for m in (inicio, fim):
        if m and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", m):
            raise ErroFinance("Mês inválido: use o formato AAAA-MM, por exemplo 2026-12.")
    if fim and fim < inicio:
        raise ErroFinance("O mês final não pode ser antes do inicial.")
    cur = con.execute("INSERT INTO previstos(descricao, valor, dia, inicio, fim) VALUES(?,?,?,?,?)", (descricao[:80], v if entrada else -v, dia, inicio, fim or None))
    con.commit()
    return cur.lastrowid


def remover_previsto(con, id_previsto: int) -> bool:
    cur = con.execute("DELETE FROM previstos WHERE id=?", (int(id_previsto),))
    con.commit()
    return cur.rowcount > 0


def ignorar_detectado(con, chave: str, ignorar: bool = True) -> None:
    if ignorar:
        con.execute("INSERT OR IGNORE INTO ignorados(chave) VALUES(?)", (chave,))
    else:
        con.execute("DELETE FROM ignorados WHERE chave=?", (chave,))
    con.commit()


def _dia_no_mes(mes: str, dia: int) -> str:
    import calendar
    ano, m = int(mes[:4]), int(mes[5:7])
    return f"{mes}-{min(dia, calendar.monthrange(ano, m)[1]):02d}"


def futuros(con, n_meses: int = 6, hoje=None) -> dict:
    """Pagamentos e entradas previstos nos próximos meses: parcelas que faltam, contas recorrentes detectadas, previstos digitados e boletos em aberto.
    Devolve {"meses": [{"mes", "itens": [...], "saidas", "entradas"}], ...}. Cada item tem origem (parcela, recorrente, manual, boleto), data, descricao e valor (negativo = saída)."""
    hoje = hoje or date.today()
    if isinstance(hoje, str):
        hoje = date.fromisoformat(hoje)
    mes_ref = f"{hoje.year}-{hoje.month:02d}"
    alvo = [_soma_meses(mes_ref, k) for k in range(n_meses)]
    ign = {r["chave"] for r in con.execute("SELECT chave FROM ignorados")}
    itens = {m: [] for m in alvo}
    parcs = parcelamentos(con, hoje)
    chaves_parcela = {p["base"] for p in parcs}
    for p in parcs:
        if p["ignorado"]:
            continue
        for q in p["proximas"]:
            if q["mes"] in itens:
                itens[q["mes"]].append({"origem": "parcela", "data": _dia_no_mes(q["mes"], p["dia"]), "descricao": f"{p['descricao']} (parcela {q['numero']} de {p['total']})",
                                        "valor": p["valor"], "chave": p["chave"], "categoria": p["categoria"]})
    for s in recorrentes(con, hoje)["series"]:
        chave = "recorrente:" + s["chave"]
        if s["situacao"] == "encerrada" or chave in ign or s["parcelada"] or s["chave"] in chaves_parcela:
            continue
        for m in alvo:
            if m == mes_ref and s["situacao"] == "chegou":
                continue
            itens[m].append({"origem": "recorrente", "data": _dia_no_mes(m, s["dia"]), "descricao": s["descricao"], "valor": s["valor"], "chave": chave, "categoria": s["categoria"]})
    for r in con.execute("SELECT * FROM previstos ORDER BY id"):
        for m in alvo:
            if m >= r["inicio"] and (not r["fim"] or m <= r["fim"]):
                itens[m].append({"origem": "manual", "data": _dia_no_mes(m, r["dia"]), "descricao": r["descricao"], "valor": r["valor"], "id": r["id"], "categoria": ""})
    for b in con.execute("SELECT * FROM boletos WHERE situacao='aberto' AND vencimento IS NOT NULL"):
        m = b["vencimento"][:7]
        m = mes_ref if m < mes_ref else m  # vencido entra no mês atual
        if m in itens:
            itens[m].append({"origem": "boleto", "data": b["vencimento"], "descricao": "Boleto: " + (b["beneficiario"] or b["banco"] or b["segmento"] or "sem identificação"),
                             "valor": -(b["valor"] or 0), "id": b["id"], "categoria": ""})
    meses_saida = []
    for m in alvo:
        lista = sorted(itens[m], key=lambda x: (x["data"], x["descricao"]))
        meses_saida.append({"mes": m, "itens": lista, "saidas": -sum(x["valor"] for x in lista if x["valor"] < 0), "entradas": sum(x["valor"] for x in lista if x["valor"] > 0)})
    return {"hoje": hoje.isoformat(), "meses": meses_saida}


PERTO_DO_LIMITE = 80  # % do limite a partir do qual o orçamento mostra aviso


def definir_orcamento(con, categoria: str, texto_valor: str) -> int:
    """Grava (ou troca) o limite mensal de uma categoria de gasto. Devolve o limite em centavos."""
    if tipos(con).get(categoria) != "gasto" or categoria == SEM_CATEGORIA:
        raise ErroFinance("Só dá para pôr limite em categoria de gasto.")
    try:
        v = parse_valor(texto_valor)
    except ValueError as ex:
        raise ErroFinance("Digite o limite em reais, por exemplo 800 ou 1.250,50.") from ex
    if v <= 0:
        raise ErroFinance("O limite precisa ser maior que zero.")
    con.execute("INSERT INTO orcamentos(categoria, limite) VALUES(?, ?) ON CONFLICT(categoria) DO UPDATE SET limite=excluded.limite", (categoria, v))
    con.commit()
    return v


def remover_orcamento(con, categoria: str) -> bool:
    n = con.execute("DELETE FROM orcamentos WHERE categoria=?", (categoria,)).rowcount
    con.commit()
    return n > 0


def orcamentos(con, mes: str, visao: str = "competencia") -> dict:
    """Limite, gasto e situação de cada categoria de gasto no mês. Situação: dentro, perto (80% ou mais do limite) ou estourado (passou do limite)."""
    visao = visao if visao in VISOES else "competencia"
    tp = tipos(con)
    gastos = _gastos_por_categoria(con, mes, tp, visao)
    lim = {r["categoria"]: r["limite"] for r in con.execute("SELECT categoria, limite FROM orcamentos")}
    linhas = []
    for cat, tipo in tp.items():
        if tipo != "gasto" or cat == SEM_CATEGORIA:
            continue
        g, limite = gastos.get(cat, 0), lim.get(cat)
        if limite is None:
            linhas.append({"categoria": cat, "limite": None, "gasto": g, "restante": None, "pct": None, "estado": None})
            continue
        pct = round(100 * g / limite)
        estado = "estourado" if g > limite else "perto" if 100 * g >= PERTO_DO_LIMITE * limite else "dentro"
        linhas.append({"categoria": cat, "limite": limite, "gasto": g, "restante": limite - g, "pct": pct, "estado": estado})
    linhas.sort(key=lambda x: (x["limite"] is None, -(x["pct"] or 0), -x["gasto"], x["categoria"]))
    com = [x for x in linhas if x["limite"] is not None]
    return {"mes": mes, "visao": visao, "linhas": linhas,
            "estourados": sum(1 for x in com if x["estado"] == "estourado"), "perto": sum(1 for x in com if x["estado"] == "perto"),
            "dentro": sum(1 for x in com if x["estado"] == "dentro"), "com_limite": len(com),
            "total_limite": sum(x["limite"] for x in com), "total_gasto": sum(x["gasto"] for x in com)}


def tendencias(con, quantos: int = 12, visao: str = "competencia") -> dict:
    visao = visao if visao in VISOES else "competencia"
    tp = tipos(con)
    ms = sorted(meses(con))[-quantos:]
    semf = sem_fatura(con)
    por_mes = {m: _gastos_por_categoria(con, m, tp, visao, semf) for m in ms}
    rec = {m: _receitas(con, m, tp, visao) for m in ms}
    tot_cat = defaultdict(int)
    for m in ms:
        for c, v in por_mes[m].items():
            tot_cat[c] += v
    principais = [c for c, _ in sorted(tot_cat.items(), key=lambda x: -x[1])]
    linhas = []
    for m in ms:
        d = sum(por_mes[m].values())
        linhas.append({"mes": m, "receitas": rec[m], "despesas": d, "saldo": rec[m] - d, "cats": por_mes[m]})
    alertas = []
    if len(ms) >= 2:
        atual = ms[-1]
        prev = ms[-4:-1] if len(ms) >= 4 else ms[:-1]
        for c in principais:
            media = sum(por_mes[p].get(c, 0) for p in prev) / len(prev)
            v = por_mes[atual].get(c, 0)
            if media > 0 and v > 1.3 * media and v - media >= 5000:
                alertas.append(f"{c} em {nome_mes(atual)}: {brl(v)}, {round(100 * (v - media) / media)}% acima da média dos {len(prev)} mês(es) anterior(es) ({brl(int(media))}).")
            elif media == 0 and v >= 20000:
                alertas.append(f"{c} em {nome_mes(atual)}: {brl(v)}, categoria que não tinha gasto nos meses anteriores.")
    media_desp = (sum(l["despesas"] for l in linhas) / len(linhas)) if linhas else 0
    return {"meses": ms, "linhas": linhas, "categorias": principais, "alertas": alertas, "media_despesas": int(media_desp), "visao": visao}


# Produto de cada lançamento, deduzido da categoria, do nome da conta e da descrição (a ordem importa: vale a primeira regra que serve).
PRODUTOS = {
    "entre_contas": "Entre minhas contas",
    "fatura": "Pagamento de fatura",
    "cartao": "Cartão (compras e créditos da fatura)",
    "pix": "Pix",
    "boleto": "Boleto",
    "transferencia": "Outras transferências (TED, DOC e semelhantes)",
    "outros": "Outros",
    "fatura_sem": "Faturas pagas sem fatura importada",
}
_PRODUTO_SQL = """(CASE
  WHEN categoria = 'Entre minhas contas' THEN 'entre_contas'
  WHEN categoria = 'Pagamento de fatura' THEN 'fatura'
  WHEN conta LIKE '%cart_o%' THEN 'cartao'
  WHEN desc_norm LIKE '%pix%' THEN 'pix'
  WHEN desc_norm LIKE '%boleto%' OR desc_norm LIKE '%pagto titulo%' OR desc_norm LIKE '%pagamento de titulo%' THEN 'boleto'
  WHEN desc_norm LIKE '%transf%' OR (' ' || desc_norm || ' ') LIKE '% ted %' OR (' ' || desc_norm || ' ') LIKE '% doc %' THEN 'transferencia'
  ELSE 'outros' END)"""


def _filtro(con, mes: str = "", cat: str = "", q: str = "", conta: str = "", produto: str = "") -> tuple:
    where, args = ["1=1"], []
    if re.fullmatch(r"\d{4}-\d{2}", mes or ""):
        where.append("substr(data,1,7)=?")
        args.append(mes)
    if cat:
        where.append("categoria=?")
        args.append(cat)
    if q:
        where.append("desc_norm LIKE ?")
        args.append("%" + norm(q) + "%")
    if conta:
        where.append("conta=?")
        args.append(conta)
    if produto == "fatura_sem":
        ids = [int(p["id"]) for p in sem_fatura(con)]
        where.append("id IN (" + ",".join(str(i) for i in ids) + ")" if ids else "1=0")
    elif produto in PRODUTOS:
        where.append(_PRODUTO_SQL + " = ?")
        args.append(produto)
    return " AND ".join(where), args


def listar(con, mes: str = "", cat: str = "", q: str = "", limite: int = 100, deslocar: int = 0, conta: str = "", produto: str = "") -> tuple:
    cond, args = _filtro(con, mes, cat, q, conta, produto)
    total = con.execute(f"SELECT COUNT(*) FROM transacoes WHERE {cond}", args).fetchone()[0]
    linhas = [dict(r) for r in con.execute(f"SELECT *, {_PRODUTO_SQL} AS produto FROM transacoes WHERE {cond} ORDER BY data DESC, id DESC LIMIT ? OFFSET ?", args + [limite, deslocar])]
    return total, linhas


def somas_listagem(con, mes: str = "", cat: str = "", q: str = "", conta: str = "", produto: str = "") -> dict:
    """Quantidade, entradas e saídas do que o filtro mostra (inclui tudo, também o que fica fora do Resumo por ser neutro)."""
    cond, args = _filtro(con, mes, cat, q, conta, produto)
    r = con.execute(f"SELECT COUNT(*) n, COALESCE(SUM(CASE WHEN valor>0 THEN valor END),0) ent, COALESCE(SUM(CASE WHEN valor<0 THEN -valor END),0) sai FROM transacoes WHERE {cond}", args).fetchone()
    return {"n": r["n"], "entradas": r["ent"], "saidas": r["sai"], "liquido": r["ent"] - r["sai"]}


def contas_e_produtos(con) -> tuple:
    """([(conta, quantidade)], [(chave do produto, quantidade)]) de tudo o que há no banco, para os filtros."""
    contas = [(r["conta"], r["n"]) for r in con.execute("SELECT conta, COUNT(*) n FROM transacoes GROUP BY conta ORDER BY conta")]
    cont = {r["p"]: r["n"] for r in con.execute(f"SELECT {_PRODUTO_SQL} p, COUNT(*) n FROM transacoes GROUP BY p")}
    cont["fatura_sem"] = len(sem_fatura(con))
    produtos = [(k, cont[k]) for k in PRODUTOS if cont.get(k)]
    return contas, produtos


def exportar_csv(con) -> str:
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";")
    w.writerow(["data", "conta", "descricao", "valor", "categoria"])
    for r in con.execute("SELECT data, conta, descricao, valor, categoria FROM transacoes ORDER BY data, id"):
        w.writerow([r["data"], r["conta"], r["descricao"], f"{r['valor'] / 100:.2f}".replace(".", ","), r["categoria"]])
    return saida.getvalue()
