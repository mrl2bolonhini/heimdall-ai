#!/usr/bin/env python3
"""Leitor de boletos do Heimdall Finance: linha digitável (47 dígitos de boleto bancário ou 48 de conta de consumo/tributo) -> valor, vencimento e banco.

O Heimdall nunca paga nada: ele só lê o código, confere os dígitos verificadores e guarda o boleto como conta a pagar no banco local.
Nada aqui usa internet; o banco SQLite fica só no Mac.
"""
import json
import re
from datetime import date, datetime, timedelta

import financas_nucleo as fn

ERRO = fn.ErroFinance
BASE_ANTIGA = date(1997, 10, 7)   # fator de vencimento 0
BASE_NOVA = date(2025, 2, 22)     # o fator voltou a 1000 nesta data
BANCOS = {"001": "Banco do Brasil", "033": "Santander", "041": "Banrisul", "070": "BRB", "077": "Inter", "104": "Caixa", "136": "Unicred",
          "212": "Banco Original", "218": "BS2", "237": "Bradesco", "260": "Nubank", "290": "PagBank", "318": "BMG", "323": "Mercado Pago",
          "336": "C6 Bank", "341": "Itaú", "380": "PicPay", "389": "Mercantil", "422": "Safra", "748": "Sicredi", "756": "Sicoob", "655": "Votorantim"}
SEGMENTOS = {"1": "prefeitura", "2": "saneamento", "3": "energia elétrica e gás", "4": "telecomunicações", "5": "órgão governamental",
             "6": "carnê", "7": "multa de trânsito", "9": "uso exclusivo do banco"}


def _mod10(digitos: str) -> int:
    soma, peso = 0, 2
    for c in reversed(digitos):
        p = int(c) * peso
        soma += p // 10 + p % 10
        peso = 1 if peso == 2 else 2
    return (10 - soma % 10) % 10


def _mod11_banco(digitos: str) -> int:
    soma, peso = 0, 2
    for c in reversed(digitos):
        soma += int(c) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - soma % 11
    return 1 if dv in (0, 10, 11) else dv


def _mod11_convenio(digitos: str) -> int:
    soma, peso = 0, 2
    for c in reversed(digitos):
        soma += int(c) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return 0 if resto in (0, 1) else 11 - resto


def _vencimento(fator: int, hoje: date):
    """O fator reiniciou em 22/02/2025. Entre as duas leituras possíveis, vale a mais próxima de hoje."""
    if fator == 0:
        return None
    candidatas = [BASE_ANTIGA + timedelta(days=fator)]
    if fator >= 1000:
        candidatas.append(BASE_NOVA + timedelta(days=fator - 1000))
    return min(candidatas, key=lambda d: abs((d - hoje).days))


def so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def _crc16(texto: str) -> str:
    crc = 0xFFFF
    for b in texto.encode("ascii", "ignore"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _tlv(texto: str) -> dict:
    campos, i = {}, 0
    while i + 4 <= len(texto):
        tam = texto[i + 2:i + 4]
        if not tam.isdigit() or i + 4 + int(tam) > len(texto):
            raise ERRO("O código Pix está cortado ou malformado. Copie o Pix copia e cola inteiro.")
        campos[texto[i:i + 2]] = texto[i + 4:i + 4 + int(tam)]
        i += 4 + int(tam)
    return campos


def interpretar_pix(texto: str) -> dict:
    """Pix copia e cola (BR Code): confere o CRC e lê valor, quem recebe e a cidade. Não tem vencimento próprio (Pix com vencimento vem por link do banco)."""
    cod = re.sub(r"[\r\n]+", "", (texto or "").strip())  # espaços dentro do nome do recebedor contam no CRC, então ficam
    if len(cod) < 30 or cod[-8:-4] != "6304" or _crc16(cod[:-4]) != cod[-4:].upper():
        raise ERRO("O código Pix não confere (o dígito de controle final está errado ou o código está cortado). Copie o Pix copia e cola inteiro.")
    c = _tlv(cod)
    valor = None
    if c.get("54"):
        try:
            valor = int(round(float(c["54"]) * 100)) or None
        except ValueError:
            valor = None
    url = ""
    for i in range(26, 52):
        if str(i) in c:
            try:
                sub = _tlv(c[str(i)])
            except ERRO:
                continue
            if sub.get("00", "").lower() == "br.gov.bcb.pix" and sub.get("25"):
                url = sub["25"].strip()
    return {"tipo": "pix", "linha": cod, "banco": "", "codigo_banco": "", "valor": valor, "vencimento": None, "segmento": "", "beneficiario": (c.get("59") or "").strip(),
            "cidade": (c.get("60") or "").strip(), "url": url}


def _url_segura(url: str):
    """(host, ip) se a URL do Pix dinâmico é https para um servidor público; senão levanta ErroFinance. Nunca segue para rede local, nem com porta, usuário ou IP direto."""
    import ipaddress
    import socket
    from urllib.parse import urlparse
    bruta = url if re.match(r"(?i)https?://", url) else "https://" + url
    p = urlparse(bruta)
    if p.scheme.lower() != "https" or not p.hostname or p.username or p.password or (p.port not in (None, 443)):
        raise ERRO("O endereço do Pix dinâmico não é um https comum; não vou abrir.")
    host = p.hostname.lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
        raise ERRO("O endereço do Pix dinâmico é um número de IP direto; não vou abrir.")
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as ex:
        raise ERRO("Não consegui resolver o endereço do Pix dinâmico.") from ex
    ips = {i[4][0] for i in infos}
    if not ips or any(not ipaddress.ip_address(x).is_global for x in ips):
        raise ERRO("O endereço do Pix dinâmico aponta para a rede local ou para um endereço não público; não vou abrir.")
    return host, sorted(ips)[0], (p.path or "/") + (("?" + p.query) if p.query else "")


def _baixar(host: str, ip: str, caminho: str, timeout: int = 8, maximo: int = 30000) -> bytes:
    """GET simples em https, conectando no IP já verificado, sem seguir redirecionamento, lendo no máximo `maximo` bytes. Não envia nenhum dado seu."""
    import socket
    import ssl
    ctx = ssl.create_default_context()
    with socket.create_connection((ip, 443), timeout=timeout) as s, ctx.wrap_socket(s, server_hostname=host) as t:
        t.settimeout(timeout)
        t.sendall(f"GET {caminho} HTTP/1.1\r\nHost: {host}\r\nAccept: application/json, application/jose, text/plain\r\nUser-Agent: Heimdall-Finance\r\nConnection: close\r\n\r\n".encode("ascii", "ignore"))
        dados = b""
        while len(dados) < maximo + 4000:
            parte = t.recv(8192)
            if not parte:
                break
            dados += parte
    cab, _, corpo = dados.partition(b"\r\n\r\n")
    if not cab.startswith(b"HTTP/1.1 200") and not cab.startswith(b"HTTP/1.0 200"):
        raise ERRO("O servidor do Pix dinâmico não devolveu os dados (resposta " + cab.split(b"\r\n")[0].decode("ascii", "ignore")[:40] + ").")
    if b"chunked" in cab.lower():
        raise ERRO("O servidor do Pix dinâmico respondeu num formato que não leio.")
    return corpo[:maximo]


def ler_payload_pix(corpo: bytes) -> dict:
    """Payload do Pix dinâmico: um JWS compacto (cabeçalho.payload.assinatura, em base64url) ou JSON direto. A assinatura NÃO é verificada."""
    import base64
    texto = corpo.decode("utf-8", "replace").strip()
    try:
        if texto.startswith("{"):
            return json.loads(texto)
        partes = texto.split(".")
        if len(partes) != 3:
            raise ValueError
        return json.loads(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4)))
    except (ValueError, TypeError) as ex:
        raise ERRO("Não entendi a resposta do servidor do Pix dinâmico.") from ex


def completar_pix(dados: dict, baixar=_baixar) -> dict:
    """Para Pix dinâmico (código com endereço, sem valor), consulta o servidor do banco do recebedor e completa valor, vencimento e quem recebe.
    Só roda a pedido seu (página, comando), nunca para código vindo de e-mail. A assinatura do banco não é verificada, então vira aviso. Se falhar, devolve os dados como estavam."""
    if dados.get("tipo") != "pix" or not dados.get("url"):
        return dados
    novo = dict(dados)
    try:
        host, ip, caminho = _url_segura(dados["url"])
        d = ler_payload_pix(baixar(host, ip, caminho))
    except ERRO as ex:
        novo["aviso"] = f"Pix dinâmico: não consegui consultar o valor ({ex}). Confira no app do seu banco."
        return novo
    except OSError as ex:
        novo["aviso"] = f"Pix dinâmico: o servidor não respondeu ({type(ex).__name__}). Confira no app do seu banco."
        return novo
    try:
        valor = d.get("valor", {}).get("original") or d.get("valor", {}).get("final")
        if valor:
            novo["valor"] = int(round(float(valor) * 100)) or None
    except (ValueError, TypeError, AttributeError):
        pass
    cal = d.get("calendario", {}) if isinstance(d.get("calendario"), dict) else {}
    venc = cal.get("dataDeVencimento") or cal.get("vencimento")
    if isinstance(venc, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", venc):
        novo["vencimento"] = venc
    rec = d.get("recebedor", {}) if isinstance(d.get("recebedor"), dict) else {}
    nome = rec.get("nomeFantasia") or rec.get("nome")
    if isinstance(nome, str) and nome.strip():
        novo["beneficiario"] = nome.strip()[:80]
    novo["aviso"] = "Valor, vencimento e recebedor lidos do servidor do banco do recebedor, sem verificar a assinatura. Confira no app do seu banco antes de pagar."
    return novo


def interpretar(texto: str, hoje: date = None) -> dict:
    """Lê uma linha digitável (ou um Pix copia e cola). Levanta ErroFinance se faltar dígito ou se algum dígito verificador não bater."""
    hoje = hoje or date.today()
    if (texto or "").strip().startswith("000201"):
        return interpretar_pix(texto)
    d = so_digitos(texto)
    if len(d) == 47:
        return _bancario(d, hoje)
    if len(d) == 48 and d[0] == "8":
        return _convenio(d, hoje)
    raise ERRO(f"A linha digitável tem {len(d)} dígitos; o boleto bancário tem 47 e a conta de consumo ou tributo tem 48 (começa com 8). Confira se copiou o código inteiro.")


def _bancario(d: str, hoje: date) -> dict:
    campos = [d[0:10], d[10:21], d[21:32]]
    for i, c in enumerate(campos, 1):
        if _mod10(c[:-1]) != int(c[-1]):
            raise ERRO(f"O dígito verificador do campo {i} da linha digitável não confere. Algum número foi digitado ou copiado errado.")
    barras = d[0:4] + d[32:47] + d[4:9] + d[10:20] + d[21:31]
    if _mod11_banco(barras[:4] + barras[5:]) != int(barras[4]) or barras[4] != d[32]:
        raise ERRO("O dígito verificador geral da linha digitável não confere. Algum número foi digitado ou copiado errado.")
    fator, valor = int(d[33:37]), int(d[37:47])
    venc = _vencimento(fator, hoje)
    return {"tipo": "bancário", "linha": d, "banco": BANCOS.get(d[0:3], f"banco {d[0:3]}"), "codigo_banco": d[0:3],
            "valor": valor or None, "vencimento": venc.isoformat() if venc else None, "segmento": ""}


def _convenio(d: str, hoje: date) -> dict:
    ident = d[2]
    if ident not in "6789":
        raise ERRO("O terceiro dígito de uma linha de 48 dígitos deveria ser 6, 7, 8 ou 9, e não é: o código parece errado.")
    calc = _mod10 if ident in "67" else _mod11_convenio
    blocos = [d[i:i + 12] for i in range(0, 48, 12)]
    for i, b in enumerate(blocos, 1):
        if calc(b[:-1]) != int(b[-1]):
            raise ERRO(f"O dígito verificador do bloco {i} da linha digitável não confere. Algum número foi digitado ou copiado errado.")
    barras = "".join(b[:-1] for b in blocos)
    if calc(barras[:3] + barras[4:]) != int(barras[3]):
        raise ERRO("O dígito verificador geral da linha digitável não confere. Algum número foi digitado ou copiado errado.")
    valor = int(barras[4:15]) if ident in "68" else None  # 7 e 9 são valor em outra referência (quantidade de moeda)
    venc = None
    livre = barras[19:]
    m = re.search(r"(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])", livre)
    if m and ident in "68":
        try:
            venc = date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            venc = None
    return {"tipo": "consumo ou tributo", "linha": d, "banco": "", "codigo_banco": "", "valor": valor or None, "vencimento": venc,
            "segmento": SEGMENTOS.get(d[1], "")}


def achar_linhas(texto: str, hoje: date = None) -> list:
    """Procura linhas digitáveis válidas num texto (por exemplo, o texto extraído de um PDF de boleto). Devolve interpretações, sem repetir."""
    achadas, vistas = [], set()
    for m in re.finditer(r"\d[\d.\s-]{40,70}\d", texto or ""):
        d = so_digitos(m.group(0))
        for tam in (47, 48):
            for ini in range(0, max(0, len(d) - tam) + 1):
                trecho = d[ini:ini + tam]
                if len(trecho) != tam or trecho in vistas:
                    continue
                try:
                    r = interpretar(trecho, hoje)
                except ERRO:
                    continue
                vistas.add(trecho)
                achadas.append(r)
    for palavra in re.findall(r"000201[^\r\n]{30,}", texto or ""):
        try:
            r = interpretar_pix(palavra.strip())
        except ERRO:
            continue
        if r["linha"] not in vistas:
            vistas.add(r["linha"])
            achadas.append(r)
    return achadas


def beneficiario_do_texto(texto: str) -> str:
    """Melhor esforço: o nome que vem depois de Beneficiário (ou Cedente). Vazio se não achar."""
    linhas = [l.strip() for l in (texto or "").splitlines()]
    for i, l in enumerate(linhas):
        if re.match(r"^(benefici[aá]rio|cedente)\b", l, re.I):
            resto = re.sub(r"^(benefici[aá]rio|cedente)\s*(final)?\s*[:\-]?\s*", "", l, flags=re.I)
            nome = resto if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", resto)) >= 3 else next((x for x in linhas[i + 1:i + 4] if x and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", x)) >= 3), "")
            nome = re.split(r"\s{2,}|\bCNPJ\b|\bCPF\b|\d{2}\.\d{3}\.\d{3}", nome)[0].strip(" -:")
            if nome:
                return nome[:80]
    return ""


# --------------------------------------------------------------------------------------------
# Banco local
# --------------------------------------------------------------------------------------------
def pessoas(con) -> list:
    return [r["nome"] for r in con.execute("SELECT nome FROM pessoas ORDER BY nome")]


def adicionar_pessoa(con, nome: str) -> str:
    nome = " ".join((nome or "").split())[:60]
    if len(nome) < 2:
        raise ERRO("Digite o nome da pessoa (por exemplo, Maria Silva).")
    if re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", nome):
        raise ERRO("Digite só o nome. O Heimdall não guarda CPF.")
    con.execute("INSERT OR IGNORE INTO pessoas(nome) VALUES(?)", (nome,))
    con.commit()
    return nome


def remover_pessoa(con, nome: str) -> bool:
    cur = con.execute("DELETE FROM pessoas WHERE nome=?", (nome,))
    con.execute("UPDATE boletos SET dono=NULL WHERE dono=?", (nome,))
    con.commit()
    return cur.rowcount > 0


def definir_dono(con, id_boleto: int, nome: str) -> bool:
    nome = (nome or "").strip()
    if nome and nome not in pessoas(con):
        raise ERRO("Essa pessoa não está cadastrada. Adicione o nome primeiro.")
    cur = con.execute("UPDATE boletos SET dono=? WHERE id=?", (nome or None, int(id_boleto)))
    con.commit()
    return cur.rowcount > 0


def dono_do_texto(texto: str, nomes: list) -> str:
    """Se o PDF diz quem é o pagador (Pagador, Sacado) e o nome bate com uma pessoa cadastrada, devolve essa pessoa; senão, vazio."""
    base = fn.norm(texto)
    m = re.search(r"\b(pagador|sacado)\b", base)
    trecho = base[m.start():m.start() + 250] if m else ""
    achadas = []
    for n in nomes:
        toks = [t for t in fn.norm(n).split() if len(t) >= 2]
        if toks and all(t in trecho for t in (toks[0], toks[-1])):
            achadas.append(n)
    return achadas[0] if len(achadas) == 1 else ""


# Frases de e-mail que dizem que o boleto não precisa ser pago à mão. Cada uma precisa vir sem negação por perto (não tem, cadastre, adira...).
_SINAIS_PAGAMENTO = [
    ("débito automático", re.compile(r"d[eé]bito autom[aá]tico|debitad[oa] automaticamente|ser[aá] debitad[oa]|d[eé]bito em conta|pagamento autom[aá]tico|d[eé]bito agendado", re.I)),
    ("cartão", re.compile(r"(cobrad[oa]|lan[cç]ad[oa]|debitad[oa]) (no|em) (seu )?cart[aã]o|pagamento (via|no|com|pelo) cart[aã]o|cart[aã]o de cr[eé]dito (final|terminado)", re.I)),
    ("já pago", re.compile(r"j[aá] (foi |est[aá] )?pag[oa]|pagamento (foi )?(confirmado|realizado|identificado|recebido)|obrigad[oa] pelo pagamento|n[aã]o [eé] necess[aá]rio pagar|n[aã]o precisa pagar|comprovante de pagamento|recibo de pagamento", re.I)),
]
_NEGACAO = re.compile(r"\b(n[aã]o|sem|cadastre|cadastrar|ades[aã]o|adira|aderir|ative|ativar|contrate|caso|se voc[eê]|quem n[aã]o|evite|programe|programar|saiba como|como)\b", re.I)


def sinal_pagamento(texto: str) -> str:
    """Se o texto do e-mail diz que o pagamento já está programado ou feito, devolve o motivo em português; senão, vazio. Frases com negação por perto não contam."""
    base = re.sub(r"\s+", " ", texto or "")
    for nome, rx in _SINAIS_PAGAMENTO:
        for m in rx.finditer(base):
            antes = base[max(0, m.start() - 45):m.start()]
            depois = base[m.end():m.end() + 25]
            if _NEGACAO.search(antes) or re.match(r"\s*(n[aã]o|ainda n[aã]o)\b", depois, re.I):
                continue
            return {"débito automático": "O e-mail diz que o pagamento será por débito automático", "cartão": "O e-mail diz que a cobrança é feita no cartão",
                    "já pago": "O e-mail diz que o pagamento já foi feito ou não é preciso pagar"}[nome]
    return ""


def _tokens(texto: str) -> set:
    return {t for t in fn.norm(texto).split() if len(t) >= 4 and t not in {"ltda", "boleto", "pagamento", "banco", "conta", "pagto", "debito", "automatico", "cartao"}}


def conciliar(con, hoje: date = None) -> int:
    """Bate os boletos em aberto com o histórico do Finance. Devolve quantos mudaram.
    1. Lançamento de saída com o mesmo valor, perto do vencimento e com nome parecido (ou palavra de boleto na descrição): o boleto está pago.
    2. Conta recorrente de mesmo nome e valor parecido: provável débito automático (ou cobrança no cartão, se a série é de cartão).
    O que você mexeu à mão (marcar como pago, É para pagar mesmo) nunca é alterado."""
    hoje = hoje or date.today()
    mudou = 0
    series = None
    for b in con.execute("SELECT * FROM boletos WHERE situacao='aberto' AND manual=0 AND valor IS NOT NULL"):
        toks = _tokens(b["beneficiario"] or "")
        venc = date.fromisoformat(b["vencimento"]) if b["vencimento"] else None
        ini = ((venc or hoje) - timedelta(days=10)).isoformat()
        fim = ((venc or hoje) + timedelta(days=10)).isoformat()
        achado = None
        for t in con.execute("SELECT data, valor, descricao, desc_norm, conta FROM transacoes WHERE valor=? AND data>=? AND data<=? ORDER BY data", (-b["valor"], ini, fim)):
            if (toks and toks & _tokens(t["descricao"])) or re.search(r"\b(boleto|pagto|pag|deb aut|debito aut)\b", t["desc_norm"]):
                achado = t
                break
        if achado:
            con.execute("UPDATE boletos SET situacao='pago', motivo=? WHERE id=?", (f"Pago: lançamento de {fn.data_br(achado['data'])} de {fn.brl(b['valor'])} em {achado['conta']} no histórico do Finance", b["id"]))
            mudou += 1
            continue
        if toks:
            if series is None:
                series = fn.recorrentes(con, hoje)["series"]
            for s in series:
                if s["entrada"] or s["situacao"] == "encerrada" or not (toks & _tokens(s["descricao"])):
                    continue
                if abs(abs(s["valor"]) - b["valor"]) <= 0.15 * b["valor"]:
                    onde = "cobrança no cartão" if "cartao" in fn.norm(s["conta"]) else "débito automático"
                    con.execute("UPDATE boletos SET situacao='programado', motivo=? WHERE id=?",
                                (f"Provável {onde}: {s['descricao'][:40]} já sai da conta todo mês, perto de {fn.brl(abs(s['valor']))}", b["id"]))
                    mudou += 1
                    break
    con.commit()
    return mudou


def registrar(con, dados: dict, beneficiario: str = "", arquivo: str = "", agora: str = None, dono: str = "", aviso: str = "", motivo: str = "") -> tuple:
    """Guarda o boleto como conta a pagar. Devolve (id, novo). A mesma linha digitável não entra duas vezes.
    Com motivo (o e-mail diz que é débito automático, cartão ou já pago), entra como programado, fora da lista de contas a pagar."""
    agora = agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ja = con.execute("SELECT id FROM boletos WHERE linha=?", (dados["linha"],)).fetchone()
    if ja:
        return ja["id"], False
    cur = con.execute("INSERT INTO boletos(linha, valor, vencimento, banco, beneficiario, tipo, segmento, arquivo, situacao, criado_em, dono, aviso, motivo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (dados["linha"], dados["valor"], dados["vencimento"], dados["banco"], (beneficiario or dados.get("beneficiario") or "").strip(), dados["tipo"], dados["segmento"], arquivo, "programado" if motivo else "aberto", agora, (dono or "").strip() or None, aviso or dados.get("aviso") or None, motivo or None))
    con.commit()
    conciliar(con)
    return cur.lastrowid, True


def listar(con, hoje: date = None, incluir_pagos: bool = False) -> list:
    """Boletos com a situação em palavras: vencido, vence hoje, vence em N dias, sem vencimento, pago."""
    hoje = hoje or date.today()
    saida = []
    for r in con.execute("SELECT * FROM boletos ORDER BY CASE WHEN vencimento IS NULL THEN 1 ELSE 0 END, vencimento, id"):
        b = dict(r)
        b["dias"] = None
        if b["situacao"] == "pago":
            b["estado"] = "pago"
        elif b["situacao"] == "programado":
            b["estado"] = "programado"
        elif not b["vencimento"]:
            b["estado"] = "sem vencimento"
        else:
            dias = (date.fromisoformat(b["vencimento"]) - hoje).days
            b["dias"] = dias
            b["estado"] = "vencido" if dias < 0 else "vence hoje" if dias == 0 else "a vencer"
        if b["estado"] not in ("pago", "programado") or incluir_pagos:
            saida.append(b)
    return saida


def definir_situacao(con, id_boleto: int, pago: bool) -> bool:
    """Marcar como pago ou reabrir é decisão sua: o boleto fica travado e o Heimdall não muda mais a situação dele sozinho."""
    cur = con.execute("UPDATE boletos SET situacao=?, motivo=NULL, manual=1 WHERE id=?", ("pago" if pago else "aberto", int(id_boleto)))
    con.commit()
    return cur.rowcount > 0


def remover(con, id_boleto: int) -> bool:
    cur = con.execute("DELETE FROM boletos WHERE id=?", (int(id_boleto),))
    con.commit()
    return cur.rowcount > 0


def frase(b: dict) -> str:
    """Uma linha em português simples para o terminal."""
    quem = b.get("beneficiario") or b.get("banco") or b.get("segmento") or "sem identificação"
    if b.get("dono"):
        quem += f" (de {b['dono']})"
    valor = fn.brl(b["valor"]) if b.get("valor") else "valor em aberto (o pagador define)"
    venc = ("vencimento " + fn.data_br(b["vencimento"])) if b.get("vencimento") else "sem vencimento no código"
    return f"{quem}: {valor}, {venc}"
