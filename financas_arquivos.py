#!/usr/bin/env python3
"""Arquivos do Heimdall Finance: leitura de PDF, detecção do banco, inspeção anônima e pasta vigiada.

Tudo roda no seu Mac; nada daqui usa internet. Os extratos e faturas entram como OFX, CSV ou PDF.

PDF: o texto é extraído (pypdf, que já está no requirements.txt, ou o pdftotext do poppler) e lido por um leitor
genérico de linhas "data, descrição, valor". Como cada banco monta o PDF de um jeito, o leitor confere o resultado
com os totais que o próprio documento cita (por exemplo "Total da fatura"). Só o que confere é importado sozinho;
o resto vai para a pasta "revisar" ou pede confirmação sua.

Inspeção anônima (heimdall finance --inspect ARQUIVO): mostra só a estrutura do arquivo, com todas as letras trocadas
por x e todos os números por 9, menos um vocabulário de rótulos de extrato (data, valor, total, fatura...). Serve para
me mostrar o layout do seu banco sem que nenhum nome, valor ou número de conta saia do seu Mac.
"""
import hashlib
import io
import re
import shutil
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import financas_boletos as fb
import financas_nucleo as fn

ERRO = fn.ErroFinance
EXT_OK = {".ofx", ".csv", ".txt", ".pdf"}

# --------------------------------------------------------------------------------------------
# PDF -> texto
# --------------------------------------------------------------------------------------------
INSTALAR_PDF = "Não achei como ler PDF. Instale um destes: 'pip install pypdf' (no venv do Heimdall) ou 'brew install poppler'."


def texto_do_pdf(dados: bytes) -> str:
    """Texto do PDF, linha a linha, mantendo as colunas. Tenta pdftotext, depois pypdf."""
    ultimo = ""
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-layout", "-", "-"], input=dados, capture_output=True, timeout=60)
            txt = r.stdout.decode("utf-8", "replace")
            if txt.strip():
                return txt
            ultimo = "o PDF não tem texto (pode ser imagem escaneada)"
        except (OSError, subprocess.SubprocessError):
            ultimo = "o pdftotext falhou"
    try:
        import pypdf  # noqa: WPS433
    except ImportError:
        if exe:
            raise ERRO("Não consegui ler o PDF: " + (ultimo or "sem texto") + ".")
        raise ERRO(INSTALAR_PDF)
    try:
        leitor = pypdf.PdfReader(io.BytesIO(dados))
        if leitor.is_encrypted:
            try:
                leitor.decrypt("")
            except Exception:  # noqa: BLE001
                raise ERRO("O PDF tem senha. Abra-o, salve uma cópia sem senha e tente de novo.")
        paginas = []
        for p in leitor.pages:
            try:
                paginas.append(p.extract_text(extraction_mode="layout") or "")
            except TypeError:
                paginas.append(p.extract_text() or "")
        txt = "\n".join(paginas)
    except ERRO:
        raise
    except Exception as ex:  # noqa: BLE001
        raise ERRO(f"Não consegui ler o PDF ({type(ex).__name__}).")
    if not txt.strip():
        raise ERRO("O PDF não tem texto que eu consiga ler (pode ser imagem escaneada).")
    return txt


# --------------------------------------------------------------------------------------------
# Inspeção anônima
# --------------------------------------------------------------------------------------------
# Rótulos de extrato que continuam legíveis na inspeção. Nenhum é dado pessoal.
VOCABULARIO = set("""
parceladas parcelados parcelamento proximas próximas proxima próxima futuras futuros demais atuais previstos produtos servicos serviços
titular adicional cartoes cartões nacionais internacionais exterior outros rotativo financiamento refinanciamento taxa taxas mensal anual
cet encargo estornos creditos créditos debitos débitos pagamentos
data datas descricao descrição historico histórico lancamento lançamento lancamentos lançamentos valor valores saldo total subtotal
fatura faturas extrato conta cartao cartão credito crédito debito débito pagamento pagamentos compra compras parcela parcelas
parcelado vencimento fechamento limite disponivel disponível minimo mínimo encargos juros multa iof anuidade tarifa tarifas
pix ted doc transferencia transferência recebida recebido enviada enviado saque deposito depósito resumo periodo período
de da do das dos em no na a o e para por com ate até anterior atual proximo próximo melhor dia compra estorno cr dc
pontos moeda real reais brl rs saida saída entrada entradas saidas saídas movimentacao movimentação detalhes detalhe
nubank itau itaú mercado pago mercadopago uniclass personnalite visa mastercard elo
""".split())


def _mascarar_palavra(m) -> str:
    p = m.group(0)
    if p.lower() in VOCABULARIO:
        return p
    return "".join("X" if c.isupper() else "x" for c in p)


def mascarar_linha(linha: str) -> str:
    saida = re.sub(r"[^\W\d_]+", lambda m: "R" if m.group(0) == "R" and linha[m.end():m.end() + 1] == "$" else _mascarar_palavra(m), linha)  # palavras (letras, com acento); "R$" fica
    return re.sub(r"\d", "9", saida)


def mascarar(texto: str, max_linhas: int = 150) -> str:
    """Estrutura do texto sem dados: letras viram x, números viram 9. Linhas iguais seguidas são agrupadas."""
    brutas = [ln.rstrip() for ln in texto.splitlines()]
    linhas = []
    for ln in brutas:
        if not ln.strip():
            continue
        m = mascarar_linha(ln.expandtabs(4))
        # recuo: mantém só a quantidade aproximada de espaços, e cola sequências longas de espaços em colunas
        m = re.sub(r" {4,}", "    ", m)
        linhas.append(m)
    agrupadas = []
    for ln in linhas:
        if agrupadas and agrupadas[-1][0] == ln:
            agrupadas[-1][1] += 1
        else:
            agrupadas.append([ln, 1])
    saida = []
    for ln, n in agrupadas:
        saida.append(ln if n == 1 else f"{ln}   (repete {n} vezes)")
    if len(saida) > max_linhas:
        resto = len(saida) - max_linhas
        saida = saida[:max_linhas] + [f"... (mais {resto} linhas omitidas; use --lines N para ver mais)"]
    return "\n".join(saida)


def inspecionar(dados: bytes, nome: str, max_linhas: int = 150) -> str:
    """Texto anônimo da estrutura de um arquivo (PDF, CSV ou OFX)."""
    extensao = Path(nome).suffix.lower()
    if dados[:5] == b"%PDF-" or extensao == ".pdf":
        base = texto_do_pdf(dados)
        tipo = "PDF"
    else:
        base = fn.decodificar(dados)
        tipo = "OFX" if re.search(r"<OFX>|OFXHEADER", base[:4000], flags=re.I) else "CSV ou texto"
        if tipo == "OFX":
            # no OFX os rótulos são tags; mascara só o conteúdo depois de cada tag
            base = "\n".join(re.sub(r"(<\w+>)([^<]*)", lambda m: m.group(1) + mascarar_linha(m.group(2)), ln) for ln in base.splitlines())
            return f"Estrutura anônima ({tipo})\n" + mascarar_ofx_curto(base, max_linhas)
    return f"Estrutura anônima ({tipo})\n" + mascarar(base, max_linhas)


def mascarar_ofx_curto(texto: str, max_linhas: int) -> str:
    linhas = [ln for ln in texto.splitlines() if ln.strip()]
    ini = next((i for i, ln in enumerate(linhas) if re.search(r"<STMTTRN>", ln, re.I)), len(linhas))
    cab = linhas[:min(ini, 60)]
    um = linhas[ini:ini + 12]
    corpo = cab + (["--- um lançamento de exemplo ---"] + um if um else [])
    if len(linhas) > len(corpo):
        corpo.append(f"... ({len(linhas) - len(corpo)} linhas omitidas, com o mesmo formato)")
    return "\n".join(corpo[:max_linhas])


# --------------------------------------------------------------------------------------------
# Banco e tipo
# --------------------------------------------------------------------------------------------
BANCOS = (("Nubank", ("nubank", "nu pagamentos", "nu financeira")), ("Itaú", ("itau", "itaucard", "itau unibanco")),
          ("Mercado Pago", ("mercado pago", "mercadopago", "mercado livre", "mpago")))


def detectar(texto: str, nome: str = "") -> tuple:
    """(banco, tipo) com tipo 'conta' ou 'cartão'; vazio quando não dá para saber."""
    base = fn.norm(nome) + " " + fn.norm(texto[:6000])
    banco = ""
    pos_min = None
    for b, chaves in BANCOS:
        for c in chaves:
            i = base.find(c)
            if i >= 0 and (pos_min is None or i < pos_min):
                banco, pos_min = b, i
    bruto = texto[:6000].lower()
    forte_cartao = 3 * len(re.findall(r"<ccstmtrs>|<creditcardmsgsrsv1>", bruto))
    forte_conta = 3 * len(re.findall(r"<stmtrs>|<bankmsgsrsv1>", bruto))
    forte_cartao += len(re.findall(r"total (da|desta) fatura|limite total (de credito|do cartao)|limite disponivel|fechamento da (proxima )?fatura|vencimento da fatura|pagamento minimo|proximo fechamento|resumo da fatura|fatura anterior|total a pagar|\bcreditcard\b", base))
    forte_cartao += 3 if re.match(r"\s*date\s*,\s*category\s*,\s*title\s*,\s*amount", texto[:200], re.I) else 0
    forte_conta += len(re.findall(r"saldo do dia|saldo anterior|extrato conta|extrato de conta|extrato da conta|conta corrente|release_date|transaction_net_amount", base))
    fraco_conta = bool(re.search(r"\bextrato\b", base))
    fraco_cartao = bool(re.search(r"\bfatura\b", base))
    if forte_cartao > forte_conta:
        tipo = "cartão"
    elif forte_conta > forte_cartao:
        tipo = "conta"
    elif fraco_cartao and not fraco_conta:
        tipo = "cartão"
    elif fraco_conta:
        tipo = "conta"
    else:
        tipo = ""
    return banco, tipo


def nome_da_conta(banco: str, tipo: str) -> str:
    return f"{banco} {tipo}" if banco and tipo else ""


# --------------------------------------------------------------------------------------------
# Leitor genérico de PDF
# --------------------------------------------------------------------------------------------
_VALOR = r"-?\s?(?:R\$\s?)?-?\d{1,3}(?:\.\d{3})*,\d{2}(?!\s?%)\s?-?(?:\s?[CD]\b)?"  # porcentagem (9,99%) não é valor em reais
_RE_VALOR = re.compile(_VALOR)
_MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
_RE_DATA = re.compile(r"^\s*(?:(\d{2})/(\d{2})(?:/(\d{4}|\d{2}))?|(\d{1,2})\s+(?:de\s+)?(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*\.?(?:\s+(?:de\s+)?(\d{4}))?)\b", re.I)
_ENCARGO = re.compile(r"\b(juros|multa|iof|encargos?|tarifa|anuidade)\b")
_PARCELAMENTO_ANTERIOR = re.compile(r"\s*(d[eé]bito para (?:pagar|quitar|liquidar)|cr[eé]dito por parcelamento)\b", re.I)  # liquidação da fatura anterior parcelada (Mercado Pago)
_CREDITO_NO_NOME = re.compile(r"\s*(cr[eé]dito|estorno|reembolso|devolu[cç][aã]o|cashback)\b", re.I)
_IGNORAR = re.compile(r"\b(saldo|total|subtotal|limite|vencimento|fechamento|pagamento minimo|encargos|resumo|proxima fatura|valor da fatura)\b", re.I)


def _centavos(token: str) -> int:
    """Valor de um token como '-1.234,56', '1.234,56-', 'R$ 12,30' ou '12,30 D' (negativo)."""
    t = token.strip()
    neg = t.startswith("-") or t.endswith("-") or "-" in t.replace("R$", "")[:2] or bool(re.search(r"\bD$", t))
    n = re.sub(r"[^\d,]", "", t).replace(",", ".")
    v = int((float(n) * 100) + 0.5) if n else 0
    return -v if neg else v


def _anos_do_documento(texto: str) -> tuple:
    anos = [int(a) for a in re.findall(r"\b(20\d{2})\b", texto)]
    base = Counter(anos).most_common(1)[0][0] if anos else date.today().year
    datas = []
    for d, m, a in re.findall(r"\b(\d{2})/(\d{2})/(20\d{2})\b", texto):
        try:
            datas.append(date(int(a), int(m), int(d)))
        except ValueError:
            pass
    for d, mes, a in re.findall(r"\b(\d{1,2})\s+(?:de\s+)?(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*\.?\s+(?:de\s+)?(20\d{2})\b", texto, flags=re.I):
        try:
            datas.append(date(int(a), _MESES[mes.lower()], int(d)))
        except ValueError:
            pass
    return base, (max(datas) if datas else None)


def _data_da_linha(m, ano_base: int, ref) -> str:
    if m.group(1):
        dia, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
    else:
        dia, mes, ano = int(m.group(4)), _MESES[m.group(5).lower()[:3]], m.group(6)
    if ano:
        a = int(ano)
        a = a + 2000 if a < 100 else a
        return date(a, mes, dia).strftime("%Y-%m-%d")
    if not ref:
        return date(ano_base, mes, dia).strftime("%Y-%m-%d")
    # sem ano na linha: o ano que deixa a data mais perto do vencimento ou fechamento do documento, sem passar dele em mais de 31 dias
    candidatas = []
    for a in (ano_base - 1, ano_base, ano_base + 1):
        try:
            d = date(a, mes, dia)
        except ValueError:
            continue
        if d <= ref + timedelta(days=31):
            candidatas.append(d)
    if not candidatas:
        return date(ano_base, mes, dia).strftime("%Y-%m-%d")
    return max(candidatas).strftime("%Y-%m-%d")


# Em várias faturas as compras vêm em duas colunas lado a lado: "03/11 LOJA A 10,00    05/11 LOJA B 20,00".
# Um dd/mm no meio da linha só abre uma nova compra se vier depois de um vão de colunas (2+ espaços) e seguido de texto; "03/10 120,00" é parcela, não data.
_RE_INICIO_MEIO = re.compile(r"(?<=\s\s)\d{2}/\d{2}(?![\d/])(?=\s+(?!-?\d{1,3}(?:\.\d{3})*,\d{2}(?![\d,]))\S)")


def _segmentos(linha: str) -> list:
    """Trechos da linha que começam com uma data: [(texto_do_trecho, casamento_da_data)]."""
    inicios = []
    m0 = _RE_DATA.match(linha)
    if m0:
        inicios.append(m0.start())
    for m in _RE_INICIO_MEIO.finditer(linha):
        if not inicios or m.start() > inicios[0]:
            inicios.append(m.start())
    saida = []
    for k, ini in enumerate(inicios):
        fim = inicios[k + 1] if k + 1 < len(inicios) else len(linha)
        seg = linha[ini:fim].rstrip()
        m = _RE_DATA.match(seg)
        if m:
            saida.append((seg, m))
    return saida


def _conferir_saldos(eventos: list):
    """Extrato de conta: os saldos do dia têm de ser explicados pelos lançamentos. Tenta três jeitos de montar o documento:
    1. cronológico, ou saldo aberto no começo de cada dia: saldo novo = saldo anterior + lançamentos entre as duas linhas;
    2. do mais novo para o mais antigo, saldo no começo do dia: saldo anterior = saldo novo + lançamentos entre as duas linhas;
    3. do mais novo para o mais antigo, saldo no fim do dia: saldo da linha = saldo da linha seguinte + lançamentos do dia dela (antes dela).
    Devolve (confere, pares, batem, detalhe) ou None quando há menos de duas linhas de saldo."""
    saldos = [k for k, (tipo, _) in enumerate(eventos) if tipo == "s"]
    if len(saldos) < 2:
        return None
    antes = []  # soma dos lançamentos desde a linha de saldo anterior (ou o começo) até esta
    ini = 0
    for k in saldos:
        antes.append(sum(v for tipo, v in eventos[ini:k] if tipo == "t"))
        ini = k + 1
    o1 = o2 = o3 = 0
    dif = {1: [], 2: [], 3: []}
    for n, (a, b) in enumerate(zip(saldos, saldos[1:])):
        entre = antes[n + 1]
        va, vb = eventos[a][1], eventos[b][1]
        for modo, esperado in ((1, va + entre), (2, vb + entre), (3, vb + antes[n])):
            alvo = vb if modo == 1 else va
            if alvo == esperado:
                if modo == 1: o1 += 1
                elif modo == 2: o2 += 1
                else: o3 += 1
            else:
                nt = sum(1 for tipo, _ in eventos[(saldos[n - 1] + 1 if (modo == 3 and n > 0) else (0 if modo == 3 else a + 1)):(a if modo == 3 else b)] if tipo == "t")
                dif[modo].append((n + 1, alvo - esperado, nt))
    pares = len(saldos) - 1
    # Um lançamento impresso do outro lado de uma linha de saldo (quebra de página, ordem do leitor) deixa pares vizinhos
    # com diferenças que se anulam. Um trecho seguido de pares divergentes cuja soma é zero está explicado: os saldos das pontas fecham.
    restantes = {}
    explicadas = {}
    for modo in (1, 2, 3):
        pend, ok = list(dif[modo]), set()
        i = 0
        while i < len(pend):
            soma, j = 0, i
            while j < len(pend) and (j == i or pend[j][0] == pend[j - 1][0] + 1):
                soma += pend[j][1]
                if soma == 0:
                    ok.update(range(i, j + 1))
                    break
                j += 1
            i += 1
        restantes[modo] = [d for k, d in enumerate(pend) if k not in ok]
        explicadas[modo] = len(ok)
    bat = {m: pares - len(restantes[m]) for m in (1, 2, 3)}
    melhor = max((1, 2, 3), key=lambda m: bat[m])
    batem = bat[melhor]
    return batem == pares, pares, batem, {"cronologico": bat[1], "inverso_saldo_antes": bat[2], "inverso_saldo_depois": bat[3]}, restantes[melhor], explicadas[melhor]


def _reparar_espacos(linha: str) -> str:
    """Alguns leitores de PDF (pypdf) soltam espaços no meio de datas e valores: '99/9 9', '99/ 99', '99 ,99', '99, 99', '9.9 99,99'.
    Só junta quando o espaço é único e a forma resultante é de data ou de valor; colunas separadas por vários espaços não são tocadas."""
    linha = re.sub(r"(?<!\d)(\d{1,2}) ?/ ?(\d{1,2})(?!\d)", r"\1/\2", linha)       # 99 /99, 99/ 99
    linha = re.sub(r"(?<!\d)(\d{2}/\d) (\d)(?![\d/])", r"\1\2", linha)            # 99/9 9 (mês partido)
    linha = re.sub(r"(\d) ?, ?(\d)", r"\1,\2", linha)                              # 99 ,99 e 99, 99
    linha = re.sub(r"(,\d) (\d)(?!\d)", r"\1\2", linha)                            # 99,9 9 (centavos partidos)
    linha = re.sub(r"(\.\d{1,2}) (\d{1,3},\d{2})", r"\1\2", linha)                # 9.9 99,99 e 9.99 9,99 (milhar partido)
    linha = re.sub(r"(?<=\s{3})(-?\d{1,2}) (\d{1,2},\d{2})(?!\d)", r"\1\2", linha)   # 99 9,99 sozinho na coluna do valor
    return linha


def ler_pdf_texto(texto: str, tipo: str = "", registro: list = None) -> tuple:
    """(itens, info). Cada item: data, valor (centavos; gasto negativo), descricao. info: tipo, soma, totais, confere."""
    texto = texto.replace("\u2212", "-")  # o sinal de menos tipográfico (−) que alguns bancos usam
    texto = re.sub(r"(?m)^(\s*)(\d{2})-(\d{2})-(\d{4})(?=\s)", r"\1\2/\3/\4", texto)  # 99-99-9999 no começo da linha (Mercado Pago) vira 99/99/9999
    ano_base, ref = _anos_do_documento(texto)
    cartao = tipo == "cartão"
    itens = []
    totais = []
    saldo_da_linha = {}  # posição do lançamento em eventos -> saldo mostrado na mesma linha (Mercado Pago: data, descrição, número, valor, saldo)
    eventos = []  # ("t", valor) para cada lançamento e ("s", saldo) para cada linha de saldo, na ordem do documento
    for ln in texto.splitlines():
        linha = _reparar_espacos(ln).strip()
        if not linha:
            continue
        marcas = []
        if re.search(r"\btotal\b", linha, re.I):
            totais += [abs(_centavos(v.group(0))) for v in _RE_VALOR.finditer(linha)]
            if registro is not None:
                acum_g = sum(-i["valor"] for i in itens if i["valor"] < 0)
                marcas.append(f"TOTAL {', '.join(fn.brl(abs(_centavos(v.group(0)))) for v in _RE_VALOR.finditer(linha))} depois de {len(itens)} lançamentos (acumulado: gastos {fn.brl(acum_g)}, líquido {fn.brl(sum(i['valor'] for i in itens))})")
        elif registro is not None and not re.search(r"\d", linha) and 3 <= len(linha) <= 70:
            marcas.append(f"TÍTULO depois de {len(itens)} lançamentos")
        segs = _segmentos(linha)
        if cartao and not segs:
            # IOF de compra internacional: cobrança real da fatura que vem sem data ("... IOF em R$ 7,47")
            miof = re.search(r"\biof\b\s+em\s+r\$\s*(" + _VALOR + r")\s*$", linha, re.I)
            if miof and itens:
                viof = _centavos(miof.group(1))
                if viof > 0:
                    itens.append({"data": itens[-1]["data"], "valor": -viof, "descricao": "IOF compra internacional", "fitid": ""})
                    eventos.append(("t", -viof))
                    marcas.append("LANÇAMENTO gasto (IOF sem data)")
        if not segs and registro is not None and (_RE_VALOR.search(linha) or re.search(r"\d{2}/\d{2}|\b\d{1,2}\s+(?:de\s+)?(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\b", linha, re.I)):
            marcas.append("SEM DATA NO INÍCIO")
        for seg, m in segs:
            resto = seg[m.end():]
            if not cartao and re.match(r"\s*saldo\s+(do\s+dia|anterior|final|parcial)\b", resto, re.I):
                vsal = list(_RE_VALOR.finditer(resto))
                if vsal:
                    eventos.append(("s", _centavos(vsal[-1].group(0))))
                    marcas.append("SALDO")
                continue
            ign = _IGNORAR.search(resto)
            if ign and not cartao and ign.group(0).lower() in ("limite", "encargos") and _ENCARGO.search(resto.lower()):
                ign = None  # "JUROS LIMITE DA CONTA" é lançamento de verdade e mexe no saldo
            if ign:
                marcas.append("IGNORADO (palavra: " + ign.group(0).lower() + ")")
                continue
            vs = list(_RE_VALOR.finditer(resto))
            if not vs:
                marcas.append("SEM VALOR")
                continue
            escolhido = vs[-1] if (cartao or len(vs) == 1) else vs[0]  # em extrato de conta o último valor costuma ser o saldo
            v = _centavos(escolhido.group(0))
            desc = re.sub(r"\s{2,}", " ", resto[:escolhido.start()]).strip(" -|.")
            desc = re.sub(r"^[•·*.]{2,}\s*\d{4}\s+", "", desc)  # "•••• 1234" é o final do cartão, não faz parte da descrição
            fid = ""
            mid = re.search(r"(?<!\d)\d{10,}(?!\d)", desc)  # número da operação do banco (Mercado Pago): serve de identificador, não de descrição
            if mid:
                fid = mid.group(0)
                desc = re.sub(r"\s{2,}", " ", desc.replace(fid, " ")).strip(" -|.")
            if not desc or not re.search(r"[A-Za-zÀ-ÿ]{2,}", _RE_VALOR.sub("", desc)):
                marcas.append("SEM DESCRIÇÃO")  # só valores (ex.: "Vence em 99/99, limite R$ x, saque R$ y") não é lançamento
                continue
            try:
                data = _data_da_linha(m, ano_base, ref)
            except ValueError:
                marcas.append("DATA INVÁLIDA")
                continue
            if cartao and _PARCELAMENTO_ANTERIOR.match(desc):
                marcas.append("IGNORADO (parcelamento da fatura anterior)")  # "Débito para quitar" + "Crédito por parcelamento" somam o total da fatura ANTERIOR, que já foi lançada
                continue
            if cartao:
                v = -v  # na fatura a compra vem positiva e o crédito (estorno, pagamento) vem negativo
                if v < 0 and _CREDITO_NO_NOME.match(desc):
                    v = -v  # há bancos (Mercado Pago) que mostram o crédito com valor positivo e a palavra no nome: "Crédito por parcelamento da fatura"
            itens.append({"data": data, "valor": v, "descricao": desc[:200], "fitid": fid})
            eventos.append(("t", v))
            if not cartao and len(vs) >= 2:
                saldo_da_linha[len(eventos) - 1] = _centavos(vs[-1].group(0))
            marcas.append("LANÇAMENTO " + ("crédito" if v > 0 else "gasto"))
        if registro is not None and marcas:
            registro.append((linha, marcas))
    def _somas(lista):
        s = sum(i["valor"] for i in lista)
        g = sum(-i["valor"] for i in lista if i["valor"] < 0)
        c = sum(-i["valor"] for i in lista if i["valor"] < 0 and not _ENCARGO.search(fn.norm(i["descricao"])))
        return s, g, c
    descartadas = 0
    if cartao and totais and itens:
        # Fatura com seção final de parcelas das próximas faturas: se todos os lançamentos não fecham com nenhum total,
        # procura o maior começo da lista (na ordem do documento) cuja soma bate com um total citado e descarta o resto.
        s0, g0, c0 = _somas(itens)
        if not any(t in (abs(s0), g0, c0) for t in totais):
            for k in range(len(itens) - 1, 2, -1):
                s, g, c = _somas(itens[:k])
                if any(t >= 5000 and t in (abs(s), g, c) for t in totais):
                    descartadas = len(itens) - k
                    itens = itens[:k]
                    break
    soma, gastos, compras = _somas(itens)
    liquido = abs(soma)
    confere = None
    saldos = _conferir_saldos(eventos)
    if saldos is None and len(saldo_da_linha) >= 3:
        # extrato com o saldo na mesma linha de cada lançamento: só vale se a sequência de saldos fechar
        ev2 = []
        for k, e in enumerate(eventos):
            ev2.append(e)
            if k in saldo_da_linha:
                ev2.append(("s", saldo_da_linha[k]))
        alt = _conferir_saldos(ev2)
        if alt is not None and alt[0]:
            saldos = alt
    if saldos is not None:
        confere = saldos[0]
    elif totais and itens:
        confere = any(t in (liquido, gastos, compras) for t in totais)
    return itens, {"tipo": tipo, "soma": soma, "gastos": gastos, "totais": sorted(set(totais))[:12], "confere": confere, "descartadas": descartadas,
                   "saldos": None if saldos is None else {"pares": saldos[1], "batem": saldos[2], "orientacoes": saldos[3], "divergencias": saldos[4], "explicadas": saldos[5]}}


def explicar(dados: bytes, nome: str, max_linhas: int = 400, valores: bool = False) -> str:
    """Diagnóstico anônimo do leitor de PDF: cada linha com data ou valor, mascarada, com o que o leitor fez com ela."""
    texto = texto_do_pdf(dados)
    banco, tipo = detectar(texto, nome)
    registro = []
    itens, info = ler_pdf_texto(texto, tipo, registro)
    cont = Counter(m.split(" (")[0] for _, marcas in registro for m in marcas)
    leitor = "pdftotext" if shutil.which("pdftotext") else "pypdf"
    saida = [f"Diagnóstico anônimo do leitor (letras viram x, números viram 9)", f"leitor de texto: {leitor}; banco: {banco or '?'}; tipo: {tipo or '?'}; lançamentos lidos: {len(itens)}"]
    saida.append("contagem: " + "; ".join(f"{k} {v}" for k, v in sorted(cont.items())))
    sal = info.get("saldos")
    if sal:
        o = sal["orientacoes"]
        saida.append(f"saldos: {sal['pares']} pares; cronológico {o['cronologico']}; inverso com saldo no começo do dia {o['inverso_saldo_antes']}; inverso com saldo no fim do dia {o['inverso_saldo_depois']}")
        if sal.get("explicadas"):
            saida.append(f"  {sal['explicadas']} par(es) divergente(s) se anulam entre vizinhos (lançamento impresso do outro lado da linha de saldo): aceitos")
        for n, d, nt in (sal.get("divergencias") or [])[:20]:
            saida.append(f"  par de saldos {n} não bate: diferença R$ {fn.brl(d)}, {nt} lançamento(s) no dia")
    saida.append("totais citados no documento (R$): " + (", ".join(fn.brl(x) for x in info["totais"]) or "nenhum") + f"; gastos lidos {fn.brl(info['gastos'])}; soma {fn.brl(info['soma'])}")
    saida.append("---")
    for linha, marcas in registro[:max_linhas]:
        extra = ""
        if valores and any(m.startswith("LANÇAMENTO") for m in marcas):  # só os valores em reais das linhas lidas como lançamento, nunca o texto
            extra = "  => valores: " + " ; ".join(v.group(0).strip() for v in _RE_VALOR.finditer(linha))
        saida.append(" | ".join(marcas) + " :: " + re.sub(r" {3,}", "   ", mascarar_linha(linha))[:160] + extra)
    if len(registro) > max_linhas:
        saida.append(f"... (mais {len(registro) - max_linhas} linhas; use --lines N)")
    return "\n".join(saida)


def ler_pdf(dados: bytes, nome: str = "") -> tuple:
    """(itens, info) de um PDF. info também traz banco, tipo e conta sugerida."""
    texto = texto_do_pdf(dados)
    banco, tipo = detectar(texto, nome)
    itens, info = ler_pdf_texto(texto, tipo)
    if not itens:
        raise ERRO("Li o PDF, mas não achei linhas com data e valor. Rode 'heimdall finance --inspect ARQUIVO' e me mostre a estrutura.")
    info.update({"banco": banco, "conta_sugerida": nome_da_conta(banco, tipo)})
    return itens, info


# --------------------------------------------------------------------------------------------
# Qualquer arquivo
# --------------------------------------------------------------------------------------------
def e_pdf(dados: bytes, nome: str = "") -> bool:
    return dados[:5] == b"%PDF-" or Path(nome).suffix.lower() == ".pdf"


def analisar(dados: bytes, nome: str, inverter: bool = None) -> dict:
    """Lê OFX, CSV ou PDF sem gravar nada. Devolve formato, itens, banco, tipo, conta sugerida e a conferência."""
    if e_pdf(dados, nome):
        itens, info = ler_pdf(dados, nome)
        return {"formato": "PDF", "itens": itens, "banco": info["banco"], "tipo": info["tipo"], "conta": info["conta_sugerida"], "confere": info["confere"], "info": info}
    texto = fn.decodificar(dados)
    banco, tipo = detectar(texto, nome)
    inv = (tipo == "cartão" and re.match(r"\s*date\s*,\s*category\s*,\s*title\s*,\s*amount", texto[:200], re.I) is not None) if inverter is None else inverter
    formato, itens = fn.ler_extrato(dados, inv)
    # em OFX de cartão o sinal já vem certo; em CSV de cartão com valores positivos, o usuário ou o cabeçalho conhecido inverte
    return {"formato": formato, "itens": itens, "banco": banco, "tipo": tipo, "conta": nome_da_conta(banco, tipo), "confere": True, "info": {}}


def resumo_texto(a: dict) -> str:
    itens = a["itens"]
    n = len(itens)
    if not n:
        return "Nenhum lançamento lido."
    datas = sorted(i["data"] for i in itens)
    gastos = sum(-i["valor"] for i in itens if i["valor"] < 0)
    entradas = sum(i["valor"] for i in itens if i["valor"] > 0)
    linhas = [f"Formato {a['formato']}; banco {a['banco'] or 'não identificado'}; tipo {a['tipo'] or 'não identificado'}.",
              f"{n} lançamentos, de {fn.data_br(datas[0])} a {fn.data_br(datas[-1])}.",
              f"Gastos {fn.brl(gastos)}; entradas {fn.brl(entradas)}."]
    if a["formato"] == "PDF":
        tot = a["info"].get("totais") or []
        sal = a["info"].get("saldos")
        if sal and a["confere"] is True:
            linhas.append(f"Conferência: os {sal['pares']} saldos do dia batem com a soma dos lançamentos entre eles.")
        elif sal:
            linhas.append(f"Conferência: NÃO bateu. Dos {sal['pares']} saldos do dia, só {sal['batem']} fecham com os lançamentos. Confira antes de importar.")
        elif a["confere"] is True:
            linhas.append("Conferência: o total do documento bate com a soma dos lançamentos." + (f" Ignorei {a['info']['descartadas']} lançamentos do fim do documento (parcelas das próximas faturas), que não fazem parte desta fatura." if a["info"].get("descartadas") else ""))
        elif a["confere"] is False:
            linhas.append("Conferência: NÃO bateu. Totais citados no documento: " + ", ".join(fn.brl(t) for t in tot) + ". Confira antes de importar.")
        else:
            linhas.append("Conferência: o documento não cita um total que eu consiga comparar.")
    return "\n".join(linhas)


def importar_arquivo(con, dados: bytes, nome: str, conta: str = "", forcar: bool = False, inverter: bool = None, agora: str = None) -> dict:
    """Importa um arquivo. PDF só entra se a conferência bater ou se forcar for verdadeiro."""
    a = analisar(dados, nome, inverter)
    conta = (conta or a["conta"]).strip()
    if not conta:
        raise ERRO("Não consegui descobrir de que banco e tipo é o arquivo. Diga o nome da conta ou do cartão (por exemplo: Itaú conta, Nubank cartão).")
    if a["formato"] == "PDF" and a["confere"] is not True and not forcar:
        raise ERRO("O PDF foi lido, mas o total não conferiu com os lançamentos. " + resumo_texto(a).replace("\n", " ") +
                   " Para importar mesmo assim, confirme que revisou.")
    r = _gravar(con, a, nome, conta, agora, hashlib.sha256(dados).hexdigest())
    try:
        fb.conciliar(con)  # lançamentos novos podem mostrar que um boleto em aberto já foi pago
    except Exception:  # noqa: BLE001
        pass
    r["conta"] = conta
    r["resumo"] = resumo_texto(a)
    return r


def _gravar(con, a: dict, nome: str, conta: str, agora: str = None, hash_arquivo: str = "") -> dict:
    return fn.importar_itens(con, a["itens"], a["formato"], nome, conta, agora, hash_arquivo)


# --------------------------------------------------------------------------------------------
# Pasta vigiada
# --------------------------------------------------------------------------------------------
def preparar_pasta(base: Path) -> Path:
    entrada = base / "entrada"
    for sub in ("", "importados", "revisar"):
        (entrada / sub).mkdir(parents=True, exist_ok=True)
    return entrada


def _mover(origem: Path, destino_dir: Path, agora: str) -> Path:
    destino = destino_dir / origem.name
    if destino.exists():
        destino = destino_dir / f"{origem.stem}-{agora.replace(':', '').replace(' ', '_').replace('-', '')}{origem.suffix}"
    shutil.move(str(origem), str(destino))
    try:
        destino.chmod(0o600)
    except OSError:
        pass
    return destino


def _motivo_de(arq: Path) -> Path:
    return arq.with_name(arq.name + ".motivo.txt")


def _limpar_motivos(revisar: Path) -> int:
    """Apaga os .motivo.txt cujo arquivo já saiu de revisar/ (foi revisado, importado ou apagado)."""
    n = 0
    if not revisar.is_dir():
        return 0
    for m in sorted(revisar.glob("*.motivo.txt")):
        if not (revisar / m.name[: -len(".motivo.txt")]).exists():
            try:
                m.unlink()
                n += 1
            except OSError:
                pass
    return n


def _ja_em_revisar(revisar: Path, h: str, ignorar: Path) -> bool:
    """True se já há em revisar/ um arquivo com exatamente o mesmo conteúdo."""
    for outro in revisar.iterdir():
        if outro.is_file() and outro != ignorar and not outro.name.endswith(".motivo.txt") and not outro.name.startswith("."):
            try:
                if hashlib.sha256(outro.read_bytes()).hexdigest() == h:
                    return True
            except OSError:
                pass
    return False


def concluir_revisao(base: Path, arquivo: Path, agora: str = None) -> None:
    """Chamado quando um arquivo de revisar/ foi de fato revisado e importado: vai para importados/ e o motivo é apagado."""
    agora = agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entrada = preparar_pasta(Path(base))
    arquivo = Path(arquivo)
    if arquivo.is_file() and arquivo.parent.resolve() == (entrada / "revisar").resolve():
        _mover(arquivo, entrada / "importados", agora)
    _limpar_motivos(entrada / "revisar")


def devolver_para_entrada(base: Path) -> list:
    """Move os arquivos de revisar/ de volta para entrada/ (sem os .motivo.txt) para serem lidos de novo. Devolve [(nome, movido, aviso)]."""
    entrada = preparar_pasta(Path(base))
    revisar = entrada / "revisar"
    saida = []
    for arq in sorted(revisar.iterdir()):
        if not arq.is_file() or arq.name.startswith(".") or arq.name.endswith(".motivo.txt"):
            continue
        destino = entrada / arq.name
        if destino.exists():
            saida.append((arq.name, False, "já existe um arquivo com esse nome em entrada; deixei em revisar"))
            continue
        arq.rename(destino)
        saida.append((arq.name, True, ""))
    _limpar_motivos(revisar)
    return saida


def _tentar_boleto(con, arq: Path, dados: bytes, agora: str):
    """PDF que não é extrato nem fatura mas traz uma linha digitável válida é um boleto: vira conta a pagar. Nada é pago."""
    try:
        texto = texto_do_pdf(dados)
    except ERRO:
        return None
    achadas = fb.achar_linhas(texto)
    if not achadas:
        return None
    quem = fb.beneficiario_do_texto(texto)
    novos = 0
    for b in achadas:
        novos += 1 if fb.registrar(con, b, quem, arq.name, agora, fb.dono_do_texto(texto, fb.pessoas(con)))[1] else 0
    return {"arquivo": arq.name, "ok": True, "boleto": True, "conta": "", "novas": novos, "repetidas": len(achadas) - novos, "lidas": len(achadas),
            "motivo": " | ".join(fb.frase({**b, "beneficiario": quem or b.get("beneficiario", "")}) for b in achadas)}


def processar_entrada(con, base: Path, agora: str = None, max_bytes: int = 16 * 1024 * 1024) -> list:
    """Importa o que estiver na pasta entrada/. Sucesso vai para importados/; dúvida vai para revisar/ com um .motivo.txt.
    Arquivo duplicado (mesmo conteúdo já importado, ou nada novo nos lançamentos) não é importado e é apagado.
    Os .motivo.txt de arquivos que já saíram de revisar/ são apagados."""
    agora = agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entrada = preparar_pasta(Path(base))
    revisar = entrada / "revisar"
    resultados = []
    limpos = _limpar_motivos(revisar)
    if limpos:
        resultados.append({"arquivo": f"{limpos} motivo(s) antigo(s)", "ok": True, "limpeza": limpos, "conta": "", "novas": 0, "repetidas": 0, "lidas": 0})
    for arq in sorted(entrada.iterdir()):
        if not arq.is_file() or arq.name.startswith(".") or arq.suffix.lower() not in EXT_OK:
            continue
        try:
            if arq.stat().st_size > max_bytes:
                raise ERRO("Arquivo grande demais.")
            if datetime.now().timestamp() - arq.stat().st_mtime < 3:
                continue  # ainda sendo copiado
            dados = arq.read_bytes()
            h = hashlib.sha256(dados).hexdigest()
            if fn.arquivo_ja_importado(con, h):
                arq.unlink()
                _limpar_motivos(revisar)
                resultados.append({"arquivo": arq.name, "ok": True, "duplicado": True, "conta": "", "novas": 0, "repetidas": 0, "lidas": 0,
                                   "motivo": "Já importado antes (conteúdo idêntico): apaguei esta cópia."})
                continue
            if _ja_em_revisar(revisar, h, arq):
                arq.unlink()
                resultados.append({"arquivo": arq.name, "ok": True, "duplicado": True, "conta": "", "novas": 0, "repetidas": 0, "lidas": 0,
                                   "motivo": "Mesmo conteúdo de um arquivo que já espera revisão: apaguei esta cópia."})
                continue
            r = importar_arquivo(con, dados, arq.name, agora=agora)
            if r["lidas"] > 0 and r["novas"] == 0:
                fn.apagar_importacao_vazia(con, r["importacao_id"])
                arq.unlink()
                _limpar_motivos(revisar)
                resultados.append({"arquivo": arq.name, "ok": True, "duplicado": True, "conta": r["conta"], "novas": 0, "repetidas": r["repetidas"], "lidas": r["lidas"],
                                   "motivo": "Todos os lançamentos já estavam importados: não importei de novo e apaguei esta cópia."})
                continue
            _mover(arq, entrada / "importados", agora)
            _limpar_motivos(revisar)
            resultados.append({"arquivo": arq.name, "ok": True, "conta": r["conta"], "novas": r["novas"], "repetidas": r["repetidas"], "lidas": r["lidas"]})
        except ERRO as ex:
            boleto = _tentar_boleto(con, arq, dados, agora) if arq.suffix.lower() == ".pdf" else None
            if boleto:
                _mover(arq, entrada / "importados", agora)
                _limpar_motivos(revisar)
                resultados.append(boleto)
                continue
            destino = _mover(arq, revisar, agora)
            _motivo_de(destino).write_text(f"{agora}\n{ex}\n", encoding="utf-8")
            resultados.append({"arquivo": arq.name, "ok": False, "motivo": str(ex)})
        except OSError as ex:
            resultados.append({"arquivo": arq.name, "ok": False, "motivo": f"Não consegui ler o arquivo ({type(ex).__name__})."})
    return resultados


def pendentes(base: Path) -> list:
    """(arquivo, motivo) dos arquivos em revisar/."""
    pasta = Path(base) / "entrada" / "revisar"
    if not pasta.is_dir():
        return []
    saida = []
    for arq in sorted(pasta.iterdir()):
        if arq.is_file() and not arq.name.endswith(".motivo.txt") and not arq.name.startswith("."):
            m = arq.with_name(arq.name + ".motivo.txt")
            motivo = ""
            if m.is_file():
                partes = m.read_text(encoding="utf-8", errors="replace").splitlines()
                motivo = " ".join(partes[1:]).strip()
            saida.append((arq.name, motivo))
    return saida
