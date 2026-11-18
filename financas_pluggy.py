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
AVISO_DIAS = 30       # avisa quando o consentimento de um banco vence em até tantos dias


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


def renomear_conta_finance(con, antigo: str, novo: str) -> int:
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
    con.commit()
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
        itens = para_itens(c, cli.transacoes(c["id"], ini, hoje))
        pacotes.append({"id": c["id"], "nome": nome, "tipo": c.get("type"), "final": _final(c), "itens": itens, "desde": ini.isoformat()})
    return {"pacotes": pacotes, "avisos": avisos}


def gravar(con, coleta: dict, estado: dict, hoje: date = None, agora: str = None) -> dict:
    """Parte local: importa no banco do Finance e atualiza o estado."""
    hoje = hoje or date.today()
    resumo = []
    guardados = estado.setdefault("contas", {})
    for p in coleta["pacotes"]:
        r = fn.importar_itens(con, p["itens"], "pluggy", "Meu Pluggy", p["nome"], agora)
        resumo.append({"conta": p["nome"], "tipo": p["tipo"], "final": p["final"], "lidas": r["lidas"], "novas": r["novas"], "repetidas": r["repetidas"], "desde": p["desde"]})
        guardados[p["id"]] = {"nome": p["nome"], "ultimo": hoje.isoformat(), "tipo": p["tipo"], "final": p["final"]}
    estado["avisos"] = coleta["avisos"]
    estado["ultima"] = (agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    estado["resumo"] = resumo
    return {"contas": resumo, "avisos": coleta["avisos"]}


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
        saida.append({"id": c["id"], "tipo": "cartão de crédito" if (c.get("type") or "").upper() == "CREDIT" else "conta", "final": _final(c), "nome": nomes[c["id"]],
                      "rotulo": _rotulo(c), "existente": conta_existente(con, c, nomes[c["id"]]), "subtipo": SUBTIPOS.get((c.get("subtype") or "").upper(), (c.get("subtype") or "").lower()),
                      "saldo": saldo if isinstance(saldo, (int, float)) else None})
    return saida


def definir_nome(estado: dict, id_conta: str, nome: str) -> None:
    nome = (nome or "").strip()[:60]
    if not nome:
        raise ErroPluggy("Diga o nome da conta, por exemplo: Itaú conta.")
    estado.setdefault("contas", {}).setdefault(id_conta, {})["nome"] = nome
    estado["contas"][id_conta].pop("ultimo", None)  # recomeça a contagem de datas para o novo nome


def executar(con, cfg: dict, estado_arq: Path, desde: date = None, hoje: date = None, cliente: Cliente = None) -> dict:
    estado = ler_estado(estado_arq)
    coleta = coletar(cfg, estado, con, desde, hoje, cliente)
    r = gravar(con, coleta, estado, hoje)
    gravar_estado(estado_arq, estado)
    return r


if __name__ == "__main__":
    sys.exit("Use: heimdall finance --sincronizar")
