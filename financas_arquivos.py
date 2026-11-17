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
import io
import re
import shutil
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

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
    forte_cartao += len(re.findall(r"total (da|desta) fatura|limite total de credito|limite disponivel|fechamento da fatura|vencimento da fatura|pagamento minimo|proximo fechamento|\bcreditcard\b", base))
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
_VALOR = r"-?\s?(?:R\$\s?)?-?\d{1,3}(?:\.\d{3})*,\d{2}\s?-?(?:\s?[CD]\b)?"
_RE_VALOR = re.compile(_VALOR)
_MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
_RE_DATA = re.compile(r"^\s*(?:(\d{2})/(\d{2})(?:/(\d{4}|\d{2}))?|(\d{1,2})\s+(?:de\s+)?(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*\.?(?:\s+(?:de\s+)?(\d{4}))?)\b", re.I)
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
    d = date(ano_base, mes, dia)
    if ref and d > ref + timedelta(days=31):
        d = date(ano_base - 1, mes, dia)
    return d.strftime("%Y-%m-%d")


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
    """Extrato de conta: entre duas linhas de saldo, a soma dos lançamentos tem de explicar a diferença dos saldos.
    Serve para extrato em ordem cronológica (saldo novo = saldo anterior + lançamentos) e na ordem inversa.
    Devolve (confere, pares, batem) ou None quando há menos de duas linhas de saldo."""
    saldos = [k for k, (tipo, _) in enumerate(eventos) if tipo == "s"]
    if len(saldos) < 2:
        return None
    asc = desc = pares = 0
    for a, b in zip(saldos, saldos[1:]):
        soma = sum(v for tipo, v in eventos[a + 1:b] if tipo == "t")
        va, vb = eventos[a][1], eventos[b][1]
        pares += 1
        asc += (vb == va + soma)
        desc += (va == vb + soma)
    batem = max(asc, desc)
    return batem == pares, pares, batem


def ler_pdf_texto(texto: str, tipo: str = "") -> tuple:
    """(itens, info). Cada item: data, valor (centavos; gasto negativo), descricao. info: tipo, soma, totais, confere."""
    ano_base, ref = _anos_do_documento(texto)
    cartao = tipo == "cartão"
    itens = []
    totais = []
    eventos = []  # ("t", valor) para cada lançamento e ("s", saldo) para cada linha de saldo, na ordem do documento
    for ln in texto.splitlines():
        linha = ln.strip()
        if not linha:
            continue
        if re.search(r"\btotal\b", linha, re.I):
            totais += [abs(_centavos(v.group(0))) for v in _RE_VALOR.finditer(linha)]
        for seg, m in _segmentos(linha):
            resto = seg[m.end():]
            if not cartao and re.match(r"\s*saldo\s+(do\s+dia|anterior|final|parcial)\b", resto, re.I):
                vsal = list(_RE_VALOR.finditer(resto))
                if vsal:
                    eventos.append(("s", _centavos(vsal[-1].group(0))))
                continue
            if _IGNORAR.search(resto):
                continue
            vs = list(_RE_VALOR.finditer(resto))
            if not vs:
                continue
            escolhido = vs[-1] if (cartao or len(vs) == 1) else vs[0]  # em extrato de conta o último valor costuma ser o saldo
            v = _centavos(escolhido.group(0))
            desc = re.sub(r"\s{2,}", " ", resto[:escolhido.start()]).strip(" -|.")
            if not desc:
                continue
            try:
                data = _data_da_linha(m, ano_base, ref)
            except ValueError:
                continue
            if cartao:
                v = -v  # na fatura a compra vem positiva e o crédito (estorno, pagamento) vem negativo
            itens.append({"data": data, "valor": v, "descricao": desc[:200], "fitid": ""})
            eventos.append(("t", v))
    soma = sum(i["valor"] for i in itens)
    gastos = sum(-i["valor"] for i in itens if i["valor"] < 0)
    liquido = abs(soma)
    confere = None
    saldos = _conferir_saldos(eventos)
    if saldos is not None:
        confere = saldos[0]
    elif totais and itens:
        confere = any(t in (liquido, gastos) for t in totais)
    return itens, {"tipo": tipo, "soma": soma, "gastos": gastos, "totais": sorted(set(totais))[:6], "confere": confere,
                   "saldos": None if saldos is None else {"pares": saldos[1], "batem": saldos[2]}}


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
            linhas.append("Conferência: o total do documento bate com a soma dos lançamentos.")
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
    r = _gravar(con, a, nome, conta, agora)
    r["conta"] = conta
    r["resumo"] = resumo_texto(a)
    return r


def _gravar(con, a: dict, nome: str, conta: str, agora: str = None) -> dict:
    return fn.importar_itens(con, a["itens"], a["formato"], nome, conta, agora)


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


def processar_entrada(con, base: Path, agora: str = None, max_bytes: int = 16 * 1024 * 1024) -> list:
    """Importa o que estiver na pasta entrada/. Sucesso vai para importados/, dúvida vai para revisar/ com um .motivo.txt."""
    agora = agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entrada = preparar_pasta(Path(base))
    resultados = []
    for arq in sorted(entrada.iterdir()):
        if not arq.is_file() or arq.name.startswith(".") or arq.suffix.lower() not in EXT_OK:
            continue
        try:
            if arq.stat().st_size > max_bytes:
                raise ERRO("Arquivo grande demais.")
            if datetime.now().timestamp() - arq.stat().st_mtime < 3:
                continue  # ainda sendo copiado
            dados = arq.read_bytes()
            r = importar_arquivo(con, dados, arq.name, agora=agora)
            _mover(arq, entrada / "importados", agora)
            resultados.append({"arquivo": arq.name, "ok": True, "conta": r["conta"], "novas": r["novas"], "repetidas": r["repetidas"], "lidas": r["lidas"]})
        except ERRO as ex:
            destino = _mover(arq, entrada / "revisar", agora)
            motivo = destino.with_name(destino.name + ".motivo.txt")
            motivo.write_text(f"{agora}\n{ex}\n", encoding="utf-8")
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
