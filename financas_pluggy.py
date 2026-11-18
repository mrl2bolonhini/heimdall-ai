#!/usr/bin/env python3
"""Baixa sozinho as contas e transações dos seus bancos pelo Open Finance, usando o plano pessoal gratuito do Meu Pluggy, e importa no Finance.

Como funciona: você autoriza cada banco no site do Meu Pluggy; este módulo lê (somente leitura) as contas e as transações pela API do Pluggy e grava no banco
local do Finance, do mesmo jeito que um extrato importado. Os dados passam pelos servidores do Pluggy antes de chegar ao Mac: é uma exceção consciente à regra de
que dados de finanças não saem do Mac, aceita pelo usuário. Nada é movido: não há pagamento, transferência nem qualquer chamada que escreva no banco.

Chaves no .env (nunca coladas na conversa): HEIMDALL_PLUGGY_CLIENT_ID, HEIMDALL_PLUGGY_CLIENT_SECRET e HEIMDALL_PLUGGY_ITEMS (os ids dos bancos conectados,
separados por vírgula). `financas_cli.py --guardar-pluggy id|segredo|itens` grava cada uma lendo a área de transferência, sem imprimir o valor.

Uso: python3 financas_cli.py --sincronizar [--desde AAAA-MM-DD] [--listar] [--nomear N=NOME]
O painel do Finance repete a sincronização a cada 6 horas quando as três chaves existem (HEIMDALL_FINANCE_PLUGGY=0 desliga). O Meu Pluggy só atualiza a cada 24 h.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import financas_nucleo as fn

AQUI = Path(__file__).resolve().parent
BASE = "https://api.pluggy.ai"
MAX_RESPOSTA = 8 * 1024 * 1024
JANELA_INICIAL = 90   # dias buscados na primeira vez, se não houver extrato importado da mesma conta
SOBREPOSICAO = 7      # dias relidos a cada rodada; o id da transação evita duplicar
MAX_PAGINAS = 200
AVISO_DIAS = 30
PARCELADOS_DIAS = 400  # até onde olhar para achar parcelas que caem na fatura em aberto (o Pluggy entrega cerca de 12 meses)


class ErroPluggy(fn.ErroFinance):
    pass


# --------------------------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------------------------
def _ler_env(caminho: Path) -> dict:
    cfg = {}
    try:
        for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            cfg[k.strip()] = v.strip().strip("\"'")
    except OSError:
        pass
    return cfg


def credenciais(env_path: Path = None) -> dict:
    """{'id', 'segredo', 'itens': [...]} ou {} se faltar alguma das três chaves."""
    e = _ler_env(env_path or AQUI / ".env")
    itens = [x.strip() for x in e.get("HEIMDALL_PLUGGY_ITEMS", "").split(",") if x.strip()]
    if not e.get("HEIMDALL_PLUGGY_CLIENT_ID") or not e.get("HEIMDALL_PLUGGY_CLIENT_SECRET") or not itens:
        return {}
    return {"id": e["HEIMDALL_PLUGGY_CLIENT_ID"], "segredo": e["HEIMDALL_PLUGGY_CLIENT_SECRET"], "itens": itens}


CHAVES = {"id": "HEIMDALL_PLUGGY_CLIENT_ID", "segredo": "HEIMDALL_PLUGGY_CLIENT_SECRET", "itens": "HEIMDALL_PLUGGY_ITEMS"}
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def guardar_chave(qual: str, valor: str, env_path: Path = None) -> str:
    """Grava uma das chaves no .env (permissão 600), trocando a linha antiga. Devolve só uma descrição, nunca o valor."""
    if qual not in CHAVES:
        raise ErroPluggy("Escolha id, segredo ou itens.")
    valor = (valor or "").strip().strip("\"'")
    if qual == "itens" and "item=" in valor:
        # endereço da página Demo do Dashboard (…/applications/ID-DA-APLICAÇÃO/demo?item=ID-DO-ITEM): vale só o id do item
        achado = urllib.parse.parse_qs(urllib.parse.urlparse(valor).query).get("item") or []
        if not achado:
            raise ErroPluggy("Não achei o id do item no endereço copiado. Copie o endereço da página depois de abrir o item.")
        valor = achado[0]
    if "\n" in valor or "\r" in valor or " " in valor.replace(", ", ","):
        raise ErroPluggy("O que está na área de transferência não parece a chave: tem espaços ou várias linhas. Copie só o valor e tente de novo.")
    if qual == "itens":
        partes = [p.strip() for p in valor.split(",") if p.strip()]
        if not partes or not all(_UUID.match(p) for p in partes):
            raise ErroPluggy("Os ids dos bancos conectados são códigos no formato 8-4-4-4-12 (separados por vírgula, se forem vários). Copie de novo na página Demo, em Itens Conectados.")
        antigos = [x.strip() for x in _ler_env(Path(env_path or AQUI / ".env")).get("HEIMDALL_PLUGGY_ITEMS", "").split(",") if x.strip()]
        valor = ",".join(dict.fromkeys(antigos + partes))  # cada comando acrescenta os bancos novos; repetir o mesmo não duplica
    elif qual == "id" and not _UUID.match(valor):
        raise ErroPluggy("O Client ID é um código no formato 8-4-4-4-12. Copie de novo no Dashboard do Pluggy, em Aplicações.")
    elif qual == "segredo" and len(valor) < 16:
        raise ErroPluggy("O Client Secret parece curto demais. Ele só aparece uma vez na geração; se perdeu, gere outro no Dashboard.")
    caminho = Path(env_path or AQUI / ".env")
    linhas = []
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        pass
    nova = f"{CHAVES[qual]}={valor}"
    for i, l in enumerate(linhas):
        if l.strip().startswith(CHAVES[qual] + "="):
            linhas[i] = nova
            break
    else:
        linhas.append(nova)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    try:
        caminho.chmod(0o600)
    except OSError:
        pass
    if qual == "itens":
        return f"{CHAVES[qual]} gravada no .env: agora são {len(valor.split(','))} banco(s) conectado(s)."
    return f"{CHAVES[qual]} gravada no .env ({len(valor)} caracteres)."


# --------------------------------------------------------------------------------------------
# HTTP (só api.pluggy.ai, só https, sem redirecionamento)
# --------------------------------------------------------------------------------------------
class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401
        return None


def _http(metodo: str, caminho: str, params: dict = None, corpo: dict = None, chave: str = "") -> dict:
    """Uma chamada à API. Devolve o JSON. Levanta ErroPluggy com o código HTTP (nunca com o corpo, que pode ecoar dados)."""
    url = BASE + caminho + (("?" + urllib.parse.urlencode(params)) if params else "")
    cab = {"Accept": "application/json", "User-Agent": "heimdall-finance/1"}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        cab["Content-Type"] = "application/json"
    if chave:
        cab["X-API-KEY"] = chave
    req = urllib.request.Request(url, data=dados, headers=cab, method=metodo)
    opener = urllib.request.build_opener(_SemRedirecionar)
    try:
        with opener.open(req, timeout=30) as r:
            bruto = r.read(MAX_RESPOSTA + 1)
    except urllib.error.HTTPError as ex:
        raise ErroPluggy(f"O Pluggy respondeu com erro {ex.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ErroPluggy("Não consegui falar com o Pluggy (sem internet ou serviço fora do ar).") from None
    if len(bruto) > MAX_RESPOSTA:
        raise ErroPluggy("Resposta grande demais do Pluggy; ignorada.")
    try:
        return json.loads(bruto.decode("utf-8") or "{}")
    except ValueError:
        raise ErroPluggy("O Pluggy devolveu algo que não é JSON.") from None


def _com_tentativas(http, *args, **kw):
    for tentativa in range(3):
        try:
            return http(*args, **kw)
        except ErroPluggy as ex:
            transitorio = any(f"erro {c}" in str(ex) for c in (429, 500, 502, 503, 504)) or "Não consegui falar" in str(ex)
            if tentativa == 2 or not transitorio:
                raise
            time.sleep(2 * (tentativa + 1))


class Cliente:
    """Só chamadas de leitura (GET) e a de autenticação. A chave da API vale 2 horas e é reaproveitada."""

    def __init__(self, cfg: dict, http=_http):
        self.cfg, self.http, self._chave, self._ate = cfg, http, "", 0.0

    def chave(self) -> str:
        if not self._chave or time.time() > self._ate:
            try:
                r = _com_tentativas(self.http, "POST", "/auth", None, {"clientId": self.cfg["id"], "clientSecret": self.cfg["segredo"]})
            except ErroPluggy as ex:
                if "401" in str(ex) or "403" in str(ex):
                    raise ErroPluggy("O Pluggy recusou o Client ID e o Client Secret. Gere um segredo novo no Dashboard e grave de novo com --guardar-pluggy segredo.") from None
                raise
            if not r.get("apiKey"):
                raise ErroPluggy("O Pluggy não devolveu a chave de acesso.")
            self._chave, self._ate = r["apiKey"], time.time() + 100 * 60
        return self._chave

    def get(self, caminho: str, params: dict = None) -> dict:
        return _com_tentativas(self.http, "GET", caminho, params, None, self.chave())

    def contas(self, item_id: str) -> list:
        saida, pagina = [], 1
        while pagina <= 20:
            r = self.get("/accounts", {"itemId": item_id, "pageSize": 500, "page": pagina})
            saida += r.get("results") or []
            if pagina >= int(r.get("totalPages") or 1):
                break
            pagina += 1
        return saida

    def faturas(self, conta_id: str) -> list:
        """Faturas do cartão (fechadas e a vencer), se o banco informar; lista vazia quando a rota não está disponível."""
        try:
            return self.get("/bills", {"accountId": conta_id, "pageSize": 20}).get("results") or []
        except ErroPluggy:
            return []

    def item(self, item_id: str) -> dict:
        """Situação do item (consentimento). Em contas Meu Pluggy pode não estar disponível: devolve {} nesse caso."""
        try:
            return self.get(f"/items/{item_id}")
        except ErroPluggy:
            return {}

    def transacoes(self, conta_id: str, desde: date, ate: date) -> list:
        base = {"accountId": conta_id, "dateFrom": desde.isoformat(), "dateTo": ate.isoformat()}
        params, saida = dict(base), []
        for _ in range(MAX_PAGINAS):
            r = self.get("/v2/transactions", params)
            saida += r.get("results") or []
            prox = r.get("next")
            if not prox:
                break
            q = urllib.parse.urlparse(prox).query if "://" in prox else prox.lstrip("?&")
            params = {**base, **dict(urllib.parse.parse_qsl(q))}
        return saida


# --------------------------------------------------------------------------------------------
# Conversão para o formato do Finance
# --------------------------------------------------------------------------------------------
def _centavos(x) -> int:
    return int((Decimal(str(x)) * 100).quantize(Decimal("1")))


def para_itens(conta: dict, transacoes: list) -> list:
    """Transações do Pluggy -> itens do Finance (valor em centavos, negativo = saída).
    Conta corrente: o tipo (DEBIT/CREDIT) manda. Cartão de crédito: o valor segue a fatura, compra positiva e pagamento negativo, então o sinal é invertido.
    Em conta corrente, transação PENDING (agendada, bloqueada) fica de fora até ser liquidada; no cartão, a compra na fatura aberta entra."""
    cartao = (conta.get("type") or "").upper() == "CREDIT"
    itens = []
    for t in transacoes:
        if t.get("amount") is None or not t.get("date"):
            continue
        if not cartao and (t.get("status") or "POSTED").upper() == "PENDING":
            continue
        try:
            valor = _centavos(t["amount"])
        except Exception:  # noqa: BLE001
            continue
        if cartao:
            valor = -valor
        else:
            valor = -abs(valor) if (t.get("type") or "").upper() == "DEBIT" else abs(valor) if (t.get("type") or "").upper() == "CREDIT" else valor
        if valor == 0:
            continue
        desc = (t.get("description") or t.get("descriptionRaw") or "Sem descrição").strip()
        itens.append({"data": str(t["date"])[:10], "valor": valor, "descricao": desc, "fitid": str(t.get("id") or "")})
    return itens


def _saldo_centavos(conta: dict):
    try:
        return _centavos(conta["balance"]) if conta.get("balance") is not None else None
    except Exception:  # noqa: BLE001
        return None


def _dados_cartao(conta: dict) -> dict:
    """Dados do cartão que o banco informa (limite, disponível, fechamento, vencimento, mínimo); só o que veio, valores em centavos."""
    cd = conta.get("creditData") or {}
    saida = {}
    for chave, campo in (("limite", "creditLimit"), ("disponivel", "availableCreditLimit"), ("minimo", "minimumPayment")):
        try:
            if cd.get(campo) is not None:
                saida[chave] = _centavos(cd[campo])
        except Exception:  # noqa: BLE001
            pass
    for chave, campo in (("fecha", "balanceCloseDate"), ("vence", "balanceDueDate")):
        if cd.get(campo):
            saida[chave] = str(cd[campo])[:10]
    return saida


def _proxima_fatura(faturas: list, hoje: date) -> dict:
    """A fatura que vence hoje ou depois (a mais próxima); se não houver, a última vencida. Valores em centavos."""
    itens = []
    for f in faturas:
        try:
            venc = str(f.get("dueDate") or "")[:10]
            date.fromisoformat(venc)
            itens.append((venc, _centavos(f["totalAmount"])))
        except Exception:  # noqa: BLE001
            continue
    if not itens:
        return {}
    futuras = sorted(i for i in itens if i[0] >= hoje.isoformat())
    venc, valor = futuras[0] if futuras else sorted(itens)[-1]
    return {"fatura_vence": venc, "fatura_valor": valor, "fatura_aberta": bool(futuras)}


def parcelas_da_fatura_aberta(transacoes: list, faturas: list) -> list:
    """Parcelas de compras antigas que caem na fatura em aberto. O banco só lista uma parcela depois que ela entra numa fatura fechada (com a data da
    compra e o código da fatura); então a próxima parcela de cada compra, com o mesmo valor, cai na fatura em aberto quando a parcela atual
    pertence à última fatura fechada. Devolve [{"descricao", "valor" (centavos), "parcela", "total"}]."""
    ultima = None
    for f in faturas:
        venc = str(f.get("dueDate") or "")[:10]
        if venc and f.get("id") and (ultima is None or venc > ultima[0]):
            ultima = (venc, f["id"])
    if not ultima:
        return []
    existentes = set()
    for t in transacoes:
        m = t.get("creditCardMetadata") or {}
        if m.get("installmentNumber"):
            existentes.add((str(m.get("purchaseDate") or "")[:10], m.get("totalInstallments"), int(m["installmentNumber"]), abs(round(float(t.get("amount") or 0) * 100))))
    saida = []
    for t in transacoes:
        m = t.get("creditCardMetadata") or {}
        try:
            k, n = int(m.get("installmentNumber") or 0), int(m.get("totalInstallments") or 0)
        except (TypeError, ValueError):
            continue
        if not (1 <= k < n) or (m.get("billId") or t.get("billId")) != ultima[1] or t.get("amount") is None:
            continue
        valor = abs(_centavos(t["amount"]))
        chave = (str(m.get("purchaseDate") or "")[:10], m.get("totalInstallments"), k + 1)
        if any(e[:3] == chave and abs(e[3] - valor) <= max(5, valor // 50) for e in existentes):
            continue  # a próxima parcela já aparece na lista
        desc = re.sub(r"\s*\d{1,2}/\d{1,2}\s*$", "", str(t.get("description") or "")).strip()[:40]
        saida.append({"descricao": desc, "valor": valor, "parcela": k + 1, "total": n})
    return saida


def _final(conta: dict) -> str:
    n = re.sub(r"\D", "", str(conta.get("number") or ""))
    return n[-4:] if n else ""


MARCAS = (("nubank", "Nubank"), ("nu pagamentos", "Nubank"), ("itau", "Itaú"), ("mercado pago", "Mercado Pago"), ("mercadopago", "Mercado Pago"),
          ("bradesco", "Bradesco"), ("santander", "Santander"), ("inter", "Inter"), ("c6", "C6 Bank"), ("caixa", "Caixa"), ("banco do brasil", "Banco do Brasil"))
SUBTIPOS = {"CHECKING_ACCOUNT": "corrente", "SAVINGS_ACCOUNT": "poupança", "PAYMENT_ACCOUNT": "pagamentos"}


def _marca(rotulo: str) -> str:
    n = " " + fn.norm(rotulo) + " "
    for chave, nome in MARCAS:
        if f" {chave} " in n or (len(chave) > 3 and chave in n):
            return nome
    return ""


def _rotulo(conta: dict) -> str:
    r = (conta.get("marketingName") or conta.get("name") or "Conta")
    r = re.sub(r"\s*\([^)]*\)", "", r)
    r = re.sub(r"(?i)\bpluggy\b:?", "", r)
    return re.sub(r"\s+", " ", r).strip() or "Conta"


def _tipo_nome(conta: dict) -> str:
    if (conta.get("type") or "").upper() == "CREDIT":
        return "cartão de crédito"
    return "conta poupança" if (conta.get("subtype") or "").upper() == "SAVINGS_ACCOUNT" else "conta corrente"


def nome_padrao(con, conta: dict, usados: set = None, marca_item: str = "") -> str:
    """Nome da conta no Finance: 'Banco conta corrente', 'Banco conta poupança' ou 'Banco cartão de crédito'. Nunca devolve um nome já
    usado por outra conta nesta rodada (`usados`): nesse caso acrescenta o final ou um número. Dá para trocar com --nomear."""
    usados = usados if usados is not None else set()
    rotulo = _rotulo(conta)
    marca = _marca(rotulo) or marca_item or rotulo
    base = f"{marca} {_tipo_nome(conta)}"
    f = _final(conta)
    candidatos = [base] + ([f"{base} final {f}"] if f else [])
    for c in candidatos:
        if c[:60] not in usados:
            return c[:60]
    n = 2
    while f"{candidatos[-1]} {n}"[:60] in usados:
        n += 1
    return f"{candidatos[-1]} {n}"[:60]


def conta_existente(con, conta: dict, nome: str) -> str:
    """Conta já importada por extrato que parece ser a mesma (mesmo banco e tipo) mas tem outro nome; '' se não há."""
    cartao = (conta.get("type") or "").upper() == "CREDIT"
    rotulo = _rotulo(conta)
    marca = _marca(rotulo)
    palavras = [w for w in fn.norm(marca or rotulo).split() if len(w) >= 3 and w not in {"conta", "corrente", "cartao", "credito", "pagamentos", "banco", "digital", "poupanca"}]
    for (e,) in con.execute("SELECT DISTINCT conta FROM transacoes ORDER BY conta"):
        ne = fn.norm(e)
        if e != nome and ("cartao" in ne) == cartao and palavras and any(w in ne for w in palavras):
            return e
    return ""


def renomear_conta_finance(con, antigo: str, novo: str, estado: dict = None) -> int:
    """Troca o nome de uma conta já importada (histórico incluso). Devolve quantos lançamentos mudaram."""
    antigo, novo = (antigo or "").strip(), (novo or "").strip()[:60]
    if not antigo or not novo:
        raise ErroPluggy("Use --renomear-conta \"NOME ATUAL=NOME NOVO\".")
    if not con.execute("SELECT 1 FROM transacoes WHERE conta=? LIMIT 1", (antigo,)).fetchone():
        raise ErroPluggy(f"Não há lançamentos na conta \"{antigo}\".")
    if con.execute("SELECT 1 FROM transacoes WHERE conta=? LIMIT 1", (novo,)).fetchone():
        raise ErroPluggy(f"Já existe uma conta chamada \"{novo}\"; escolha outro nome.")
    n = con.execute("UPDATE transacoes SET conta=? WHERE conta=?", (novo, antigo)).rowcount
    con.execute("UPDATE importacoes SET conta=? WHERE conta=?", (novo, antigo))
    con.execute("INSERT OR IGNORE INTO renomeacoes(antigo, novo, quando) VALUES(?,?,?)", (antigo, novo, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    for g in (estado or {}).get("contas", {}).values():  # contas do Pluggy que usavam o nome antigo passam a usar o novo, sem recomeçar a contagem de datas
        if g.get("nome") == antigo:
            g["nome"] = novo
    return n


def resolver_nomes(con, estado: dict, contas: list, forcados: dict = None) -> dict:
    """Nome de cada conta (id -> nome): o forçado por --nomear, o já guardado, ou o padrão sem repetir nome dentro da mesma rodada."""
    forcados = forcados or {}
    guardados = estado.get("contas", {})
    saida = {}
    usados = set()
    marcas_item = {}  # cartão sem nome de banco (ex.: 'platinum') herda o banco da conta do mesmo item
    for c in contas:
        m = _marca(_rotulo(c))
        if m and c.get("itemId"):
            marcas_item[c["itemId"]] = m
    for c in contas:
        n = forcados.get(c["id"]) or guardados.get(c["id"], {}).get("nome")
        if n:
            saida[c["id"]] = n
            usados.add(n)
    for c in contas:
        if c["id"] not in saida:
            saida[c["id"]] = nome_padrao(con, c, usados, marcas_item.get(c.get("itemId") or "", ""))
            usados.add(saida[c["id"]])
    return saida


# --------------------------------------------------------------------------------------------
# Sincronização
# --------------------------------------------------------------------------------------------
def ler_estado(arq: Path) -> dict:
    try:
        return json.loads(Path(arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def gravar_estado(arq: Path, estado: dict) -> None:
    try:
        Path(arq).write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
        Path(arq).chmod(0o600)
    except OSError:
        pass


def _avisos_item(item: dict, hoje: date) -> list:
    saida = []
    erro = (item.get("error") or {}).get("code") if isinstance(item.get("error"), dict) else ""
    if item.get("status") == "LOGIN_ERROR" and "EXPIRED" in str(erro or item.get("statusDetail") or "").upper():
        saida.append("A autorização de um banco expirou: entre no Meu Pluggy e autorize de novo, senão as transações novas não chegam.")
    ate = (item.get("consentExpiresAt") or "")[:10]
    if ate:
        try:
            dias = (date.fromisoformat(ate) - hoje).days
        except ValueError:
            dias = None
        if dias is not None and dias <= AVISO_DIAS:
            saida.append(("A autorização de um banco expirou em " + fn.data_br(ate) + ".") if dias < 0
                         else f"A autorização de um banco expira em {fn.data_br(ate)} (daqui a {dias} dia(s)); renove no Meu Pluggy antes disso.")
    return saida


def coletar(cfg: dict, estado: dict, con_leitura, desde: date = None, hoje: date = None, cliente: Cliente = None, nomes: dict = None) -> dict:
    """Parte de rede: lê itens, contas e transações. Não grava nada. Devolve {'pacotes': [...], 'avisos': [...], 'contas': [...]}."""
    hoje = hoje or date.today()
    cli = cliente or Cliente(cfg)
    nomes = nomes or {}
    guardados = estado.setdefault("contas", {})
    pacotes, avisos, todas = [], [], []
    for item_id in cfg["itens"]:
        avisos += _avisos_item(cli.item(item_id), hoje)
        todas += cli.contas(item_id)
    nomes_finais = resolver_nomes(con_leitura, estado, todas, nomes)
    for c in todas:
        g = guardados.get(c["id"], {})
        nome = nomes_finais[c["id"]]
        if desde:
            ini = desde
        elif g.get("ultimo"):
            ini = date.fromisoformat(g["ultimo"]) - timedelta(days=SOBREPOSICAO)
        else:
            ult = con_leitura.execute("SELECT MAX(data) AS d FROM transacoes WHERE conta=?", (nome,)).fetchone()["d"]
            ini = date.fromisoformat(ult) + timedelta(days=1) if ult else hoje - timedelta(days=JANELA_INICIAL)
        ini = min(ini, hoje)
        recebidas = cli.transacoes(c["id"], ini, hoje)
        credito = _dados_cartao(c)
        if (c.get("type") or "").upper() == "CREDIT":
            faturas = cli.faturas(c["id"])
            credito.update(_proxima_fatura(faturas, hoje))
            if faturas:
                credito["parcelas_abertas"] = parcelas_da_fatura_aberta(cli.transacoes(c["id"], hoje - timedelta(days=PARCELADOS_DIAS), hoje), faturas)
        itens = para_itens(c, recebidas)
        pacotes.append({"id": c["id"], "nome": nome, "tipo": c.get("type"), "final": _final(c), "itens": itens, "desde": ini.isoformat(), "recebidas": len(recebidas), "saldo": _saldo_centavos(c), "credito": credito})
    return {"pacotes": pacotes, "avisos": avisos}


def gravar(con, coleta: dict, estado: dict, hoje: date = None, agora: str = None) -> dict:
    """Parte local: importa no banco do Finance e atualiza o estado."""
    hoje = hoje or date.today()
    resumo = []
    guardados = estado.setdefault("contas", {})
    for p in coleta["pacotes"]:
        r = fn.importar_itens(con, p["itens"], "pluggy", "Meu Pluggy", p["nome"], agora)
        resumo.append({"conta": p["nome"], "tipo": p["tipo"], "final": p["final"], "lidas": r["lidas"], "novas": r["novas"], "repetidas": r["repetidas"], "desde": p["desde"], "recebidas": p.get("recebidas", len(p["itens"]))})
        guardados[p["id"]] = {**{k: v for k, v in guardados.get(p["id"], {}).items() if k == "fechamento"}, "nome": p["nome"], "ultimo": hoje.isoformat(), "tipo": p["tipo"], "final": p["final"], "saldo": p.get("saldo"), "credito": p.get("credito")}
    estado["avisos"] = coleta["avisos"]
    estado["ultima"] = (agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    estado["resumo"] = resumo
    return {"contas": resumo, "avisos": coleta["avisos"]}


def padronizar_nomes(con, estado: dict, cfg: dict, cliente: Cliente = None) -> list:
    """Renomeia, com o histórico, as contas do Pluggy cujo nome guardado não segue o padrão (Banco conta corrente, Banco cartão de crédito...).
    Não pede digitar nomes. Devolve [(antigo, novo, lançamentos)] e avisos para o que não pôde trocar."""
    cli = cliente or Cliente(cfg)
    todas = []
    for item_id in cfg["itens"]:
        todas += cli.contas(item_id)
    padrao = resolver_nomes(con, {"contas": {}}, todas)
    feitos = []
    for c in todas:
        g = estado.get("contas", {}).get(c["id"])
        atual, novo = (g or {}).get("nome"), padrao[c["id"]]
        if not atual or atual == novo:
            continue
        if not con.execute("SELECT 1 FROM transacoes WHERE conta=? LIMIT 1", (atual,)).fetchone():
            g["nome"] = novo  # nada importado ainda: só passa a usar o nome novo
            feitos.append((atual, novo, 0, ""))
            continue
        try:
            feitos.append((atual, novo, renomear_conta_finance(con, atual, novo, estado), ""))
        except ErroPluggy as ex:
            feitos.append((atual, novo, 0, str(ex)))
    return feitos


def listar_contas(cfg: dict, estado: dict, con, cliente: Cliente = None) -> list:
    """Contas dos bancos conectados com o nome que cada uma terá no Finance."""
    cli = cliente or Cliente(cfg)
    todas = []
    for item_id in cfg["itens"]:
        todas += cli.contas(item_id)
    nomes = resolver_nomes(con, estado, todas)
    saida = []
    for c in todas:
        saldo = c.get("balance")
        existente = conta_existente(con, c, nomes[c["id"]])
        if existente in nomes.values():  # o nome é de outra conta da lista (ex.: Itaú conta corrente), não é um extrato à parte
            existente = ""
        saida.append({"id": c["id"], "tipo": "cartão de crédito" if (c.get("type") or "").upper() == "CREDIT" else "conta", "final": _final(c), "nome": nomes[c["id"]],
                      "rotulo": _rotulo(c), "existente": existente, "subtipo": SUBTIPOS.get((c.get("subtype") or "").upper(), (c.get("subtype") or "").lower()),
                      "saldo": saldo if isinstance(saldo, (int, float)) else None})
    return saida


def definir_nome(estado: dict, id_conta: str, nome: str) -> None:
    nome = (nome or "").strip()[:60]
    if not nome:
        raise ErroPluggy("Diga o nome da conta, por exemplo: Itaú conta.")
    estado.setdefault("contas", {}).setdefault(id_conta, {})["nome"] = nome
    estado["contas"][id_conta].pop("ultimo", None)  # recomeça a contagem de datas para o novo nome


def definir_fechamento(estado: dict, trecho: str, regra) -> str:
    """Guarda quando fecha a fatura de um cartão (achado por um pedaço do nome). `regra` é "27" (dia fixo do mês) ou "1:7"
    (vence no dia 1 e fecha 7 dias antes). Devolve o nome do cartão."""
    texto = str(regra).strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", texto)
    if m:
        cfg = {"vence": int(m.group(1)), "antes": int(m.group(2))}
        if not (1 <= cfg["vence"] <= 31 and 1 <= cfg["antes"] <= 20):
            raise ErroPluggy("Use VENCIMENTO:DIAS_ANTES com o dia do vencimento entre 1 e 31 e de 1 a 20 dias antes, por exemplo: itau=1:7")
    elif texto.isdigit() and 1 <= int(texto) <= 31:
        cfg = {"dia": int(texto)}
    else:
        raise ErroPluggy("Use um dia do mês (itau=27) ou o vencimento e quantos dias antes fecha (itau=1:7).")
    alvo = fn.norm(trecho)
    cartoes = [g for g in estado.get("contas", {}).values() if (g.get("tipo") or "").upper() == "CREDIT" and g.get("nome")]
    achados = [g for g in cartoes if alvo and alvo in fn.norm(g["nome"])]
    if len(achados) != 1:
        raise ErroPluggy("Cartões: " + "; ".join(g["nome"] for g in cartoes) + ". Escreva um pedaço do nome que combine com um só, por exemplo: itau=1:7")
    achados[0]["fechamento"] = cfg
    return achados[0]["nome"]


def diagnosticar_cartao(cfg: dict, estado: dict, trecho: str, hoje: date = None, dias: int = 75, cliente: Cliente = None) -> list:
    """Mostra como o Pluggy devolve as transações e as faturas de UM cartão (data, valor, situação, parcela, data da compra, fatura), para
    entender parcelados e a fatura em aberto. Só leitura; não mostra ids nem chaves."""
    hoje = hoje or date.today()
    alvo = fn.norm(trecho)
    achados = [(i, g) for i, g in estado.get("contas", {}).items() if (g.get("tipo") or "").upper() == "CREDIT" and alvo and alvo in fn.norm(g.get("nome") or "")]
    if len(achados) != 1:
        raise ErroPluggy("Cartões: " + "; ".join(g["nome"] for g in estado.get("contas", {}).values() if (g.get("tipo") or "").upper() == "CREDIT") + ". Escreva um pedaço do nome que combine com um só.")
    cid, g = achados[0]
    cli = cliente or Cliente(cfg)
    faturas = cli.faturas(cid)
    ids = {}
    saida = [f"Cartão {g['nome']}. Faturas informadas pelo banco: {len(faturas)}."]
    for f in sorted(faturas, key=lambda x: str(x.get("dueDate") or "")):
        ids[f.get("id")] = f"fatura {len(ids) + 1}"
        saida.append(f"{ids[f.get('id')]}: vence em {str(f.get('dueDate') or '')[:10]}, total {f.get('totalAmount')}, mínimo {f.get('minimumPaymentAmount')}.")
    trs = cli.transacoes(cid, hoje - timedelta(days=max(dias, PARCELADOS_DIAS)), hoje)
    saida.append(f"Transações dos últimos {max(dias, PARCELADOS_DIAS)} dias: {len(trs)}.")

    def linha(t, ordem):
        m = t.get("creditCardMetadata") or {}
        partes = [str(t.get("date") or "")[:10], f"valor {t.get('amount')}", f"situação {t.get('status')}", str(t.get("description") or "")[:40]]
        if m.get("installmentNumber"):
            partes.append(f"parcela {m.get('installmentNumber')}/{m.get('totalInstallments')}")
        if m.get("purchaseDate"):
            partes.append(f"compra em {str(m['purchaseDate'])[:10]}")
        bid = m.get("billId") or t.get("billId")
        partes.append(ids.get(bid, "fatura desconhecida") if bid else "sem fatura")
        return f"{ordem}. " + ", ".join(partes) + "."
    ordenadas = sorted(trs, key=lambda x: str(x.get("date") or ""), reverse=True)
    parceladas = [t for t in ordenadas if ((t.get("creditCardMetadata") or {}).get("installmentNumber") or 0) >= 1 or re.search(r"\d{2}/\d{2}\s*$", str(t.get("description") or ""))]
    saida.append(f"Parceladas ({len(parceladas)}), da mais recente para a mais antiga:")
    for n, t in enumerate(parceladas[:60], 1):
        saida.append(linha(t, n))
    saida.append("Últimas 12 transações em geral:")
    for n, t in enumerate(ordenadas[:12], 1):
        saida.append(linha(t, n))
    return saida


def simular(con, cfg: dict, estado_arq: Path, desde: date, hoje: date = None, cliente: Cliente = None) -> list:
    """Só olha até onde o Pluggy devolve histórico: lê as contas e devolve, por conta, quantos lançamentos vieram e o dia mais antigo e o mais recente. Não grava nada."""
    estado = ler_estado(estado_arq)
    coleta = coletar(cfg, estado, con, desde, hoje, cliente)
    saida = []
    for p in coleta["pacotes"]:
        datas = sorted(i["data"] for i in p["itens"])
        saida.append({"conta": p["nome"], "recebidas": p.get("recebidas", 0), "validas": len(p["itens"]), "primeira": datas[0] if datas else "", "ultima": datas[-1] if datas else ""})
    return saida


def refazer_pelo_pluggy(con, cfg: dict, estado_arq: Path, desde: date, pasta_backup: Path, aplicar: bool = False, hoje: date = None, cliente: Cliente = None) -> dict:
    """Apaga os lançamentos das contas conectadas ao Pluggy (inclusive os de extrato) e relê tudo pelo Pluggy desde `desde`.
    Antes copia o banco inteiro para `pasta_backup`. Sem `aplicar`, só conta o que seria apagado."""
    import sqlite3
    estado = ler_estado(estado_arq)
    nomes = sorted({g["nome"] for g in estado.get("contas", {}).values() if g.get("nome")})
    if not nomes:
        raise ErroPluggy("Ainda não há contas do Pluggy guardadas; rode antes: heimdall finance --sincronizar")
    marcas = ",".join("?" * len(nomes))
    resumo = [{"conta": r["conta"], "lancamentos": r["n"], "alterados": r["m"]} for r in con.execute(
        f"SELECT conta, COUNT(*) AS n, SUM(manual) AS m FROM transacoes WHERE conta IN ({marcas}) GROUP BY conta ORDER BY conta", nomes)]
    saida = {"contas": resumo, "backup": "", "sincronizado": None}
    if not aplicar:
        return saida
    pasta_backup.mkdir(parents=True, exist_ok=True)
    destino = pasta_backup / f"financas-antes-do-pluggy-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    bak = sqlite3.connect(str(destino))
    con.backup(bak)
    bak.close()
    try:
        destino.chmod(0o600)
    except OSError:
        pass
    saida["backup"] = str(destino)
    con.execute(f"DELETE FROM transacoes WHERE conta IN ({marcas})", nomes)
    con.execute(f"DELETE FROM importacoes WHERE conta IN ({marcas})", nomes)
    con.execute(f"DELETE FROM deduplicados WHERE conta IN ({marcas})", nomes)
    con.commit()
    for g in estado.get("contas", {}).values():
        g.pop("ultimo", None)
    gravar_estado(estado_arq, estado)
    saida["sincronizado"] = executar(con, cfg, estado_arq, desde, hoje, cliente)
    return saida


def executar(con, cfg: dict, estado_arq: Path, desde: date = None, hoje: date = None, cliente: Cliente = None) -> dict:
    estado = ler_estado(estado_arq)
    coleta = coletar(cfg, estado, con, desde, hoje, cliente)
    r = gravar(con, coleta, estado, hoje)
    gravar_estado(estado_arq, estado)
    return r


if __name__ == "__main__":
    sys.exit("Use: heimdall finance --sincronizar")
