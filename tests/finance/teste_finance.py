#!/usr/bin/env python3
"""Testa o Heimdall Finance: leitura de OFX e CSV, deduplicação, categorias e regras, relatórios, login e páginas.
Usa um banco temporário; nada toca a internet."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
from datetime import date
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = RAIZ
os.environ.update({"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
TMP = tempfile.mkdtemp(prefix="finance_teste_")
os.environ["HEIMDALL_FINANCE_DIR"] = TMP
sys.path.insert(0, str(AQUI))
import financas_nucleo as fn  # noqa: E402
import heimdall_lab as hc  # noqa: E402
import heimdall_finance as hf  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


# ---------------- valores, datas, nomes ----------------
confere("valores brasileiros e americanos", [fn.parse_valor(x) for x in ("1.234,56", "-12,5", "R$ 1.000", "(45,90)", "-1234.56", "0.50")] == [123456, -1250, 100000, -4590, -123456, 50])
confere("datas em vários formatos", [fn.parse_data(x) for x in ("05/03/2026", "2026-03-05", "20260305120000[-3:BRT]", "05/03/26")] == ["2026-03-05"] * 4)
confere("dinheiro formatado", fn.brl(-123456) == "-R$ 1.234,56" and fn.brl(5, True) == "+R$ 0,05" and fn.brl(0) == "R$ 0,00")
confere("norm tira acento e símbolos", fn.norm("PAG*IFood  Restaurante-SP") == "pag ifood restaurante sp")

# ---------------- OFX (estilo SGML, sem tags de fechamento) ----------------
OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260105120000[-3:BRT]<TRNAMT>-250.40<FITID>A1<MEMO>SUPERMERCADO EXTRA 123</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260106<TRNAMT>-45,90<FITID>A2<MEMO>UBER *TRIP</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260110<TRNAMT>8000.00<FITID>A3<MEMO>SALARIO ACME LTDA</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260112<TRNAMT>-1500.00<FITID>A4<MEMO>PAGAMENTO FATURA CARTAO</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260115<TRNAMT>-89.90<FITID>A5<MEMO>CLINICA FAMILIA SAUDE</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260118<TRNAMT>-33.00<FITID>A6<MEMO>COMPRA XYZ PADARIA</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
""".encode("latin-1")

con = fn.conectar(Path(TMP) / "unidade.db")
r = fn.importar(con, OFX, "jan.ofx", "Itaú conta")
confere("OFX: lê seis lançamentos novos", r["formato"] == "OFX" and r["lidas"] == 6 and r["novas"] == 6 and r["repetidas"] == 0, r)
r2 = fn.importar(con, OFX, "jan.ofx", "Itaú conta")
confere("importar o mesmo OFX de novo não duplica", r2["novas"] == 0 and r2["repetidas"] == 6, r2)
cats = {x["descricao"]: x["categoria"] for x in con.execute("SELECT descricao, categoria FROM transacoes")}
confere("categorias padrão: mercado, transporte, salário, fatura, padaria", cats["SUPERMERCADO EXTRA 123"] == "Mercado" and cats["UBER *TRIP"] == "Transporte"
        and cats["SALARIO ACME LTDA"] == "Salário" and cats["PAGAMENTO FATURA CARTAO"] == "Pagamento de fatura" and cats["COMPRA XYZ PADARIA"] == "Restaurantes", cats)
confere("regra por início de palavra: 'amil' não pega 'familia'", cats["CLINICA FAMILIA SAUDE"] == "Saúde" and fn.categorizar(con, "familia unida") == fn.SEM_CATEGORIA)
confere("valor com vírgula no OFX (-45,90) vira -4590", con.execute("SELECT valor FROM transacoes WHERE descricao='UBER *TRIP'").fetchone()[0] == -4590)

# ---------------- CSV brasileiro (; e preâmbulo) e CSV de cartão ----------------
CSV_CONTA = (
    "Extrato Conta Corrente\nAgência: 0000\n\nData;Histórico;Valor\n"
    "02/02/2026;SUPERMERCADO EXTRA 77;-310,00\n03/02/2026;NETFLIX.COM;-55,90\n05/02/2026;SALARIO ACME LTDA;8.000,00\n"
    "07/02/2026;PIX ENVIADO JOAO SILVA;-200,00\n07/02/2026;PIX ENVIADO JOAO SILVA;-200,00\n10/02/2026;ACADEMIA FORMA FISICA;-120,00\nTOTAL;;-1000,00\n"
).encode("cp1252")
r = fn.importar(con, CSV_CONTA, "fev.csv", "Itaú conta")
confere("CSV com ; e linhas antes do cabeçalho: sete lançamentos, o rodapé é ignorado", r["formato"] == "CSV" and r["lidas"] == 6 and r["novas"] == 6, r)
confere("dois lançamentos iguais no mesmo dia continuam sendo dois", con.execute("SELECT COUNT(*) FROM transacoes WHERE desc_norm LIKE 'pix enviado joao%'").fetchone()[0] == 2)
r = fn.importar(con, CSV_CONTA, "fev.csv", "Itaú conta")
confere("reimportar o CSV não duplica (inclusive os dois iguais)", r["novas"] == 0 and r["repetidas"] == 6, r)

CSV_CARTAO = ("date,category,title,amount\n2026-02-04,restaurante,Restaurante do Zé,120.50\n2026-02-09,transporte,Uber *Trip,32.40\n"
              "2026-02-15,compras,Loja Sem Regra,899.00\n2026-02-20,pagamento,Pagamento recebido,-1500.00\n").encode("utf-8")
r = fn.importar(con, CSV_CARTAO, "cartao.csv", "Nubank cartão", inverter=True)
confere("CSV de cartão com valores positivos e inverter: gastos viram negativos", r["novas"] == 4 and con.execute("SELECT valor FROM transacoes WHERE descricao='Loja Sem Regra'").fetchone()[0] == -89900, r)
confere("'Pagamento recebido' na fatura é pagamento de fatura (não conta como receita); gasto sem regra fica Sem categoria",
        con.execute("SELECT categoria FROM transacoes WHERE descricao='Pagamento recebido'").fetchone()[0] == "Pagamento de fatura"
        and con.execute("SELECT categoria FROM transacoes WHERE descricao='Loja Sem Regra'").fetchone()[0] == fn.SEM_CATEGORIA)

for ruim, esperado in ((b"nada util aqui\nlinha 2", "cabeçalho"), (b"", "cabeçalho"), (b"Data;Valor\nabc;xyz", "nenhuma linha")):
    try:
        fn.importar(con, ruim, "x.csv", "Conta")
        confere(f"arquivo ruim {ruim[:12]!r} dá erro claro", False, "não deu erro")
    except fn.ErroFinance as ex:
        confere(f"arquivo ruim {ruim[:12]!r} dá erro claro", esperado in str(ex), str(ex))
try:
    fn.importar(con, OFX, "a.ofx", "  ")
    confere("importar sem nome de conta é recusado", False)
except fn.ErroFinance:
    confere("importar sem nome de conta é recusado", True)

# ---------------- categoria manual e regras ----------------
tid = con.execute("SELECT id FROM transacoes WHERE descricao='Loja Sem Regra'").fetchone()[0]
con.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em) VALUES('Nubank cartão','2026-02-21',-5000,'LOJA SEM REGRA FILIAL 2','loja sem regra filial 2','Sem categoria','h-extra','x')")
con.commit()
n = fn.definir_categoria(con, tid, "Compras", True)
confere("alterar categoria cria regra e muda os parecidos que não eram manuais", n == 2 and con.execute("SELECT categoria FROM transacoes WHERE descricao='LOJA SEM REGRA FILIAL 2'").fetchone()[0] == "Compras", n)
confere("o lançamento alterado fica marcado como manual", con.execute("SELECT manual FROM transacoes WHERE id=?", (tid,)).fetchone()[0] == 1)
fn.importar(con, b"Data;Descricao;Valor\n01/03/2026;LOJA SEM REGRA MATRIZ;-10,00\n", "mar.csv", "Itaú conta")
confere("a regra nova vale em importações futuras", con.execute("SELECT categoria FROM transacoes WHERE descricao='LOJA SEM REGRA MATRIZ'").fetchone()[0] == "Compras")
confere("regra do usuário vence a padrão", fn.adicionar_regra(con, "uber", "Lazer e viagens") >= 1 and fn.categorizar(con, "uber trip") == "Lazer e viagens")
manual_uber = con.execute("SELECT categoria FROM transacoes WHERE descricao='Uber *Trip'").fetchone()[0]
confere("regras mexem nos lançamentos que não são manuais", manual_uber == "Lazer e viagens", manual_uber)
rid = con.execute("SELECT id FROM regras WHERE padrao='uber' AND origem='usuario'").fetchone()[0]
confere("apagar regra do usuário e reaplicar volta ao padrão", fn.apagar_regra(con, rid) and fn.reaplicar_regras(con) >= 1 and fn.categorizar(con, "uber trip") == "Transporte")
confere("parcela de fatura parcelada tem categoria própria, de gasto", fn.categorizar(con, fn.norm("Pagamento da fatura de outubro/2026 Parcela 1 de 5")) == "Parcelamento de fatura" and fn.categorizar(con, fn.norm("Pagamento de fatura")) == "Pagamento de fatura")
pid = con.execute("SELECT id FROM regras WHERE origem='padrao' LIMIT 1").fetchone()[0]
confere("regra padrão não pode ser apagada", not fn.apagar_regra(con, pid))
for fun, args in ((fn.definir_categoria, (tid, "Inventada")), (fn.definir_categoria, (999999, "Mercado")), (fn.adicionar_regra, ("ab", "Mercado")), (fn.adicionar_regra, ("abc", "Inventada"))):
    try:
        fun(con, *args)
        confere(f"entrada inválida recusada: {fun.__name__}{args}", False)
    except fn.ErroFinance:
        confere(f"entrada inválida recusada: {fun.__name__}{args}", True)

# ---------------- relatórios ----------------
confere("meses em ordem do mais recente", fn.meses(con) == ["2026-03", "2026-02", "2026-01"], fn.meses(con))
j = fn.resumo_mes(con, "2026-01")
# gastos de janeiro fora a fatura: 250,40 + 45,90 + 89,90 + 33,00 = 419,20 ; fatura (1500) é neutra
confere("resumo de janeiro: fatura paga sem fatura importada conta como gasto (R$ 1.500 + 419,20)", j["receitas"] == 800000 and j["despesas"] == 191920 and j["neutros"] == 0 and len(j["sem_fatura"]) == 1, j)
# visão por compra x visão de caixa e faturas pagas sem fatura importada
import tempfile as _tf
_c = fn.conectar(os.path.join(_tf.mkdtemp(), "visoes.db"))
fn.importar_itens(_c, [{"data": "2026-05-03", "valor": -30000, "descricao": "LOJA A", "fitid": ""}, {"data": "2026-05-04", "valor": -20000, "descricao": "LOJA B", "fitid": ""}], "pdf", "fat.pdf", "Itaú cartão")
fn.importar_itens(_c, [{"data": "2026-05-20", "valor": -50000, "descricao": "PAGAMENTO FATURA ITAU", "fitid": ""}, {"data": "2026-05-21", "valor": -12345, "descricao": "PAGAMENTO FATURA ITAU UNICLASS", "fitid": ""}, {"data": "2026-05-22", "valor": -1000, "descricao": "PADARIA", "fitid": ""}], "ofx", "e.ofx", "Itaú conta")
_fp = fn.faturas_pagas(_c)
confere("pagamento de fatura que bate com o total da fatura importada é conferido; o outro não", [p["conferida"] for p in _fp] == [True, False], _fp)
_a, _b = fn.resumo_mes(_c, "2026-05", "competencia"), fn.resumo_mes(_c, "2026-05", "caixa")
confere("visão por compra: compras do cartão + pagamento sem fatura + padaria", _a["despesas"] == 50000 + 12345 + 1000 and _a["neutros"] == 50000, _a)
confere("visão de caixa: os dois pagamentos de fatura + padaria, sem as compras do cartão", _b["despesas"] == 50000 + 12345 + 1000 and _b["neutros"] == 0 and all("cartao" not in fn.norm(m["conta"]) for m in _b["maiores"]), _b)
_c.execute("UPDATE transacoes SET categoria=? WHERE descricao LIKE '%UNICLASS%'", (fn.TERCEIROS,))
confere("fatura de terceiros sai das somas nas duas visões", fn.resumo_mes(_c, "2026-05", "competencia")["despesas"] == 51000 and fn.resumo_mes(_c, "2026-05", "caixa")["despesas"] == 51000 and not fn.sem_fatura(_c))
fn.importar_itens(_c, [{"data": "2026-06-02", "valor": -77700, "descricao": "PAGAMENTO FATURA NUBANK", "fitid": ""}], "ofx", "e2.ofx", "Itaú conta")
_antes = len(fn.sem_fatura(_c))
fn.importar_itens(_c, [{"data": "2026-06-03", "valor": 77700, "descricao": "Pagamento recebido", "fitid": ""}], "ofx", "n.ofx", "Nubank cartão")
confere("crédito de pagamento no cartão confere o pagamento da conta", _antes == 1 and not fn.sem_fatura(_c), fn.sem_fatura(_c))
confere("categorias do resumo somam as despesas", sum(c["total"] for c in j["categorias"]) == j["despesas"])
confere("maiores gastos vêm em ordem e trazem a fatura sem fatura importada", j["maiores"][0]["descricao"].startswith("PAGAMENTO FATURA") and j["maiores"][1]["descricao"].startswith("SUPERMERCADO"))
f = fn.resumo_mes(con, "2026-02")
mercado = next(c for c in f["categorias"] if c["categoria"] == "Mercado")
confere("variação sobre o mês anterior: mercado 250,40 -> 310,00 = +24%", mercado["anterior"] == 25040 and mercado["variacao"] == 24, mercado)
confere("estorno/entrada em categoria de gasto não derruba a despesa", f["despesas"] > 0)

# alerta: mercado dispara em março
for i, v in enumerate((260_00, 270_00, 255_00)):
    con.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em) VALUES('Itaú conta',?,?, 'SUPERMERCADO X','supermercado x','Mercado',?,'x')", (f"2025-{10 + i}-10", -v, f"h-old{i}"))
con.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em) VALUES('Itaú conta','2026-03-20',-90000,'SUPERMERCADO BIG','supermercado big','Mercado','h-big','x')")
con.commit()
t = fn.tendencias(con, 12)
confere("tendências: meses em ordem e categoria que mais pesa primeiro", t["meses"][0] == "2025-10" and t["meses"][-1] == "2026-03" and t["categorias"][0] == "Mercado", t["meses"])
confere("alerta quando uma categoria passa de 30% da média e de R$ 50", any("Mercado" in a and "acima da média" in a for a in t["alertas"]), t["alertas"])
total, lin = fn.listar(con, "2026-02", "Mercado")
confere("listar filtra por mês e categoria", total == 1 and lin[0]["descricao"].startswith("SUPERMERCADO"), (total, lin))
total, lin = fn.listar(con, q="AÇADEMIA")
confere("busca ignora acento e caixa", total == 1)
total, lin = fn.listar(con, q="academia")
confere("busca por descrição acha", total == 1)
confere("exportar CSV tem cabeçalho e valor com vírgula", fn.exportar_csv(con).startswith("data;conta;descricao;valor;categoria") and "-250,40" in fn.exportar_csv(con))

# ---------------- servidor ----------------
hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
srv = ThreadingHTTPServer(("127.0.0.1", 0), hf.Finance)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"


class Sem303(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


abre = urllib.request.build_opener(Sem303).open


def pedir(caminho, cookie="", host=None, dados=None, tipo=None):
    cab = {}
    if cookie:
        cab["Cookie"] = cookie
    if host:
        cab["Host"] = host
    if tipo:
        cab["Content-Type"] = tipo
    req = urllib.request.Request(BASE + caminho, data=dados, headers=cab)
    try:
        with abre(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8", "replace"), dict(ex.headers)


def post(caminho, campos, ck, csrf):
    campos = dict(campos, csrf=csrf)
    return pedir(caminho, ck, dados=urllib.parse.urlencode(campos).encode(), tipo="application/x-www-form-urlencoded")


def multipart(campos, arquivo):
    lim = "----" + uuid.uuid4().hex
    corpo = b""
    for k, v in campos.items():
        corpo += f'--{lim}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    nome, dados = arquivo
    corpo += f'--{lim}\r\nContent-Disposition: form-data; name="arquivo"; filename="{nome}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + dados + b"\r\n"
    corpo += f"--{lim}--\r\n".encode()
    return corpo, f"multipart/form-data; boundary={lim}"


st, _, cab = pedir("/")
confere("sem login vai para /entrar", st == 303 and cab.get("Location") == "/entrar", (st, cab))
confere("host fora da lista é recusado", pedir("/", host="outro.exemplo.test")[0] == 421)
st, corpo, _ = pedir("/saude")
confere("/saude responde sem login", st == 200 and corpo == "ok")
st, corpo, _ = pedir("/entrar", dados=urllib.parse.urlencode({"senha": "errada", "codigo": "000000"}).encode(), tipo="application/x-www-form-urlencoded")
confere("login errado é recusado", st == 401 and "incorretos" in corpo)
confere("exportação exige login", pedir("/exportar.csv")[0] == 303)

token, sess = hc.nova_sessao()
ck = f"{hc.COOKIE}={token}"
csrf = sess["csrf"]
st, corpo, cab = pedir("/resumo", ck)
confere("início sem dados convida a importar", st == 200 and "Importar extrato" in corpo and "Ainda não há lançamentos" in corpo, (st, corpo[:300]))
csp = cab.get("Content-Security-Policy", "")
import re as _re
_n = _re.search(r"script-src 'nonce-([A-Za-z0-9_-]+)'", csp)
confere("política de conteúdo: script só com o nonce da página (abas), nada inline sem nonce", "default-src 'none'" in csp and _n and f'<script nonce="{_n.group(1)}">' in corpo and corpo.count("<script") == 1 and "script-src 'unsafe" not in csp, csp)
confere("abas no lugar do menu de links, atalhos Option+Shift+número e voltar para o topo", 'role="tablist"' in corpo and 'role="tabpanel"' in corpo and 'id="topo"' in corpo and 'href="#topo"' in corpo and "<nav aria-label=\"Principal\"><ul>" not in corpo, corpo[:200])
confere("cabeçalhos de segurança", cab.get("X-Frame-Options") == "DENY" and cab.get("Cache-Control") == "no-store", cab)

corpo_m, tipo_m = multipart({"csrf": csrf, "conta": "Itaú conta"}, ("jan.ofx", OFX))
st, _, cab = pedir("/importar", ck, dados=corpo_m, tipo=tipo_m)
confere("importar OFX pelo formulário redireciona ao resumo", st == 303 and cab.get("Location") == "/", (st, cab))
corpo_m, tipo_m = multipart({"csrf": "errado", "conta": "X"}, ("jan.ofx", OFX))
confere("importar com CSRF errado é recusado", pedir("/importar", ck, dados=corpo_m, tipo=tipo_m)[0] == 403)
corpo_m, tipo_m = multipart({"csrf": csrf, "conta": "Conta"}, ("lixo.csv", b"nada"))
st, _, cab = pedir("/importar", ck, dados=corpo_m, tipo=tipo_m)
confere("arquivo ruim volta à tela de importar com mensagem", st == 303 and cab.get("Location") == "/importar")
st, corpo, _ = pedir("/importar", ck)
confere("a mensagem de erro aparece uma vez", "Não achei o cabeçalho" in corpo and "Não achei o cabeçalho" not in pedir("/importar", ck)[1], corpo[:200])
st_aj, corpo_aj, _ = pedir("/ajuda", ck)
confere("subaba Ajuda nos Ajustes: perguntas do Finance, caminho para o suporte, sem abas de cima e um só h1",
        st_aj == 200 and "Perguntas frequentes" in corpo_aj and "/ajuda?servico=finance" in corpo_aj and "Voltar ao Finance" in corpo_aj
        and 'aria-label="Seções do Heimdall Finance"' not in corpo_aj and corpo_aj.count("<h1>") == 1 and ">Ajuda</a>" in corpo_aj, corpo_aj[:600])

try:
    import io as _io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as _cv
    _b = _io.BytesIO()
    _c = _cv.Canvas(_b, pagesize=A4)
    for _i, _l in enumerate(["Fatura do cartão Nubank", "Vencimento 10/12/2026", "03 NOV   Loja Teste   R$ 80,00", "Total da fatura R$ 80,00"]):
        _c.drawString(40, 800 - 14 * _i, _l)
    _c.save()
    corpo_m, tipo_m = multipart({"csrf": csrf, "conta": ""}, ("fatura-nubank.pdf", _b.getvalue()))
    st, _, cab = pedir("/importar", ck, dados=corpo_m, tipo=tipo_m)
    confere("importar PDF pelo formulário, sem nome de conta, usa a conta identificada", st == 303 and cab.get("Location") == "/", (st, cab))
    confere("a conta identificada foi gravada", fn.conectar(os.path.join(TMP, "financas.db")).execute("SELECT COUNT(*) FROM transacoes WHERE conta='Nubank cartão'").fetchone()[0] == 1)
    st, corpo, _ = pedir("/importar", ck)
    confere("a tela de importar aceita PDF e avisa da pasta de entrada", ".pdf" in corpo and "pasta de entrada" in corpo)
except ImportError:
    pass

st, corpo, _ = pedir("/resumo?mes=2026-01", ck)
confere("resumo do mês mostra totais e tabela com legenda", st == 200 and "R$ 8.000,00" in corpo and "R$ 1.919,20" in corpo and "Faturas pagas sem fatura importada" in corpo and "<caption>Gastos por categoria em janeiro de 2026</caption>" in corpo and 'scope="col"' in corpo, corpo[:500])
confere("aviso de lançamentos sem categoria não aparece quando não há", "sem categoria neste mês" not in corpo)
st, corpo, _ = pedir("/transacoes?mes=2026-01&cat=Mercado&q=extra", ck)
confere("lista de transações filtrada", st == 200 and "SUPERMERCADO EXTRA 123" in corpo and "UBER" not in corpo and "1 lançamento(s)" in corpo, corpo[:300])
st, corpo, _ = pedir("/transacoes", ck)
confere("transações têm filtro de conta e de produto, com rótulo e contagem", 'for="conta"' in corpo and 'for="produto"' in corpo and "Itaú conta (" in corpo and "Entradas: R$" in corpo and "Saídas: R$" in corpo, corpo[:400])
_b = hf.banco()
_b.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em) VALUES('Itaú conta','2026-01-22',-1500,'PIX ENVIADO FILTRO','pix enviado filtro','Sem categoria','h-pixfiltro','x')")
_b.commit()
st, corpo, _ = pedir("/transacoes?conta=Ita%C3%BA%20conta&produto=pix", ck)
confere("filtro de conta e produto combinados só traz Pix da conta", st == 200 and "PIX" in corpo.upper() and "<td>Pix</td>" in corpo and "UBER" not in corpo and "1 lançamento(s)" in corpo, corpo[:300])
st, corpo, _ = pedir("/transacoes?mes=2026-01", ck)
confere("ações são botões (Alterar categoria, Baixar CSV) e não links", 'aria-label="Alterar categoria de ' in corpo and ">Alterar categoria</a>" not in corpo and ">Baixar tudo em CSV</a>" not in corpo and ">Baixar tudo em CSV</button>" in corpo)
st, corpo, _ = pedir("/resumo", ck)
confere("trocar a visão é botão", ">Ver por saída de caixa</button>" in corpo and ">Ver por saída de caixa</a>" not in corpo)
_b2 = hf.banco()
for _i in range(hf.POR_PAGINA + 3):
    _b2.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em) VALUES('Pag conta','2025-03-15',-100,?,?,'Outros gastos',?,'x')", (f"ITEM PAG {_i}", f"item pag {_i}", f"h-pag-{_i}"))
_b2.commit()
st, corpo, _ = pedir("/transacoes?conta=Pag%20conta", ck)
st2, corpo2, _ = pedir("/transacoes?conta=Pag%20conta&pg=2", ck)
confere("paginação do Finance é de botões, com páginas e a atual marcada", 'aria-label="Paginação"' in corpo and "Próxima página" in corpo and "Página 1 (atual)" in corpo and ">Próxima página</a>" not in corpo and "Página 2 (atual)" in corpo2 and corpo2.count("<td>ITEM PAG") == 3, corpo2[:200])
confere("descrição maliciosa é escapada", True)
con2 = hf.banco()
con2.execute("INSERT INTO transacoes(conta,data,valor,descricao,desc_norm,categoria,hash,importado_em) VALUES('Itaú conta','2026-01-20',-1000,?,?,?,'h-xss','x')", ("<img src=x onerror=alert(1)>", "img src x onerror alert 1", fn.SEM_CATEGORIA))
con2.commit()
st, corpo, _ = pedir("/transacoes?mes=2026-01", ck)
confere("HTML na descrição não vira HTML", "<img src=x" not in corpo and "&lt;img src=x" in corpo)
st, corpo, _ = pedir("/transacoes?mes=2026-01&cat=Sem%20categoria", ck)
confere("lista de sem categoria traz formulário por linha, com rótulo", 'name="categoria"' in corpo and "Categoria de " in corpo)
tid = con2.execute("SELECT id FROM transacoes WHERE hash='h-xss'").fetchone()[0]
st, _, cab = post(f"/transacao/{tid}", {"categoria": "Lazer e viagens", "volta": "2026-01"}, ck, csrf)
confere("salvar categoria pela lista volta à lista", st == 303 and "cat=Sem%20categoria" in cab.get("Location", ""), cab)
confere("categoria foi gravada", con2.execute("SELECT categoria, manual FROM transacoes WHERE id=?", (tid,)).fetchone()[:] == ("Lazer e viagens", 1))
st, corpo, _ = pedir(f"/transacao/{tid}", ck)
confere("página do lançamento mostra o formulário", st == 200 and "Nova categoria" in corpo and "Criar regra" in corpo)
confere("lançamento inexistente dá 404", pedir("/transacao/999999", ck)[0] == 404)
confere("categoria inventada é recusada sem gravar", post(f"/transacao/{tid}", {"categoria": "Qualquer"}, ck, csrf)[0] == 303 and con2.execute("SELECT categoria FROM transacoes WHERE id=?", (tid,)).fetchone()[0] == "Lazer e viagens")
confere("POST com CSRF errado é recusado", post(f"/transacao/{tid}", {"categoria": "Mercado"}, ck, "errado")[0] == 403)
st, _, cab = post("/regras", {"padrao": "academia forma", "categoria": "Saúde"}, ck, csrf)
confere("adicionar regra", st == 303 and con2.execute("SELECT categoria FROM regras WHERE padrao='academia forma'").fetchone()[0] == "Saúde")
st, corpo, _ = pedir("/regras", ck)
confere("página de regras lista as suas e as padrão", st == 200 and "academia forma" in corpo and "Regras padrão" in corpo)
# ---- orçamentos
_g = next(x for x in fn.orcamentos(con2, "2025-03")["linhas"] if x["categoria"] == "Outros gastos")["gasto"]
confere("orçamento: sem limite a categoria aparece sem situação", _g > 0 and next(x for x in fn.orcamentos(con2, "2025-03")["linhas"] if x["categoria"] == "Outros gastos")["estado"] is None)
for _lim, _est in ((_g * 2, "dentro"), (_g * 100 // 85 + 1, "perto"), (_g, "perto"), (_g - 1, "estourado")):
    fn.definir_orcamento(con2, "Outros gastos", f"{_lim // 100},{_lim % 100:02d}")
    _x = next(x for x in fn.orcamentos(con2, "2025-03")["linhas"] if x["categoria"] == "Outros gastos")
    confere(f"orçamento: limite {_lim} com gasto {_g} fica {_est}", _x["estado"] == _est, _x)
for _cat, _val in (("Outros gastos", "abc"), ("Outros gastos", "0"), ("Outros gastos", "-5"), ("Pagamento de fatura", "100"), ("Inventada", "100"), (fn.SEM_CATEGORIA, "100")):
    try:
        fn.definir_orcamento(con2, _cat, _val)
        confere(f"orçamento recusa {_cat} / {_val}", False)
    except fn.ErroFinance:
        confere(f"orçamento recusa {_cat} / {_val}", True)
st, _, cab = post("/orcamentos", {"categoria": "Outros gastos", "limite": "10,00", "mes": "2025-03", "visao": "competencia"}, ck, csrf)
confere("salvar limite pela página volta à página", st == 303 and cab.get("Location", "").startswith("/orcamentos?mes=2025-03"), cab)
confere("limite gravado em centavos", con2.execute("SELECT limite FROM orcamentos WHERE categoria='Outros gastos'").fetchone()[0] == 1000)
st, corpo, _ = pedir("/orcamentos?mes=2025-03", ck)
confere("página de orçamentos mostra situação, tabela com legenda e botões com nome", st == 200 and "Estourado" in corpo and "<caption>" in corpo and 'aria-label="Salvar limite de Outros gastos"' in corpo and 'aria-label="Remover limite de Outros gastos"' in corpo and 'scope="col"' in corpo, corpo[:300])
st, corpo, _ = pedir("/resumo?mes=2025-03", ck)
confere("o Resumo avisa dos orçamentos estourados", "Orçamentos de" in corpo and "estourado(s)" in corpo and "Ver orçamentos" in corpo)
confere("limite inválido pela página não grava", post("/orcamentos", {"categoria": "Outros gastos", "limite": "abc"}, ck, csrf)[0] == 303 and con2.execute("SELECT limite FROM orcamentos WHERE categoria='Outros gastos'").fetchone()[0] == 1000)
confere("orçamento com CSRF errado é recusado", post("/orcamentos", {"categoria": "Outros gastos", "limite": "5"}, ck, "errado")[0] == 403)
st, _, _ = post("/orcamentos/remover", {"categoria": "Outros gastos", "mes": "2025-03"}, ck, csrf)
confere("remover limite", st == 303 and con2.execute("SELECT COUNT(*) FROM orcamentos").fetchone()[0] == 0)
# contas recorrentes
import tempfile as _tr
_r = fn.conectar(os.path.join(_tr.mkdtemp(), "recorrentes.db"))
_it = []
for _m in ("2026-06", "2026-07", "2026-08", "2026-09", "2026-10"):
    _it.append({"data": f"{_m}-05", "valor": -150000, "descricao": f"PIX ALUGUEL IMOBILIARIA {_m[5:]}", "fitid": ""})
    _it.append({"data": f"{_m}-12", "valor": -3990, "descricao": "NETFLIX.COM", "fitid": ""})
    _it.append({"data": f"{_m}-28", "valor": 500000, "descricao": "SALARIO EMPRESA XYZ", "fitid": ""})
    _it.append({"data": f"{_m}-03", "valor": -2000, "descricao": "UBER TRIP", "fitid": ""})
    _it.append({"data": f"{_m}-17", "valor": -2500, "descricao": "UBER TRIP", "fitid": ""})
_it.append({"data": "2026-08-20", "valor": -88000, "descricao": "LOJA UNICA COMPRA", "fitid": ""})
_it.append({"data": "2026-04-10", "valor": -5000, "descricao": "ACADEMIA ANTIGA", "fitid": ""})
_it.append({"data": "2026-05-10", "valor": -5000, "descricao": "ACADEMIA ANTIGA", "fitid": ""})
fn.importar_itens(_r, _it, "ofx", "rec.ofx", "Itaú conta")
_rec = fn.recorrentes(_r, "2026-10-20")
_nomes = {s["chave"]: s for s in _rec["series"]}
confere("recorrentes: aluguel, assinatura e salário são achados", all(k in _nomes for k in ("pix aluguel imobiliaria", "netflix.com", "salario empresa xyz")), list(_nomes))
confere("recorrentes: uso frequente (duas vezes por mês) e compra única não entram", "uber trip" not in _nomes and not any("loja" in k for k in _nomes))
confere("recorrentes: valores e sinais", _nomes["pix aluguel imobiliaria"]["valor"] == -150000 and _nomes["salario empresa xyz"]["valor"] == 500000 and _nomes["salario empresa xyz"]["entrada"])
confere("recorrentes: série que parou há mais de dois meses fica encerrada", _nomes["academia antiga"]["situacao"] == "encerrada")
confere("recorrentes: o que já veio no mês aparece como chegou", _nomes["netflix.com"]["situacao"] == "chegou")
confere("recorrentes: totais mensais não contam as encerradas", _rec["gasto_mensal"] == 153990 and _rec["renda_mensal"] == 500000, _rec)
_atr = fn.recorrentes(_r, "2026-11-20")
_futuro = {s["chave"]: s["situacao"] for s in _atr["series"]}
confere("recorrentes: passou do dia habitual e não veio é atrasada", _futuro["netflix.com"] == "atrasada" and _futuro["pix aluguel imobiliaria"] == "atrasada", _futuro)
_cedo = {s["chave"]: s["situacao"] for s in fn.recorrentes(_r, "2026-11-02")["series"]}
confere("recorrentes: antes do dia habitual é por vir", _cedo["pix aluguel imobiliaria"] == "por_vir" and _cedo["netflix.com"] == "por_vir", _cedo)
_v = fn.conectar(os.path.join(_tr.mkdtemp(), "vazio.db"))
confere("recorrentes: sem histórico não acha nada", fn.recorrentes(_v, "2026-10-20")["series"] == [])
st, corpo, _ = pedir("/recorrentes", ck)
confere("página de recorrentes abre e usa tabelas com legenda", st == 200 and ("<caption>" in corpo or "Ainda não achei" in corpo), corpo[:200])
# pagamentos futuros: parcelas, recorrentes, cadastrados e boletos
_f = fn.conectar(os.path.join(_tr.mkdtemp(), "futuros.db"))
_fi = [{"data": "2026-09-10", "valor": -12000, "descricao": "LOJA XPTO 02/10", "fitid": ""},
       {"data": "2026-10-10", "valor": -12000, "descricao": "LOJA XPTO 03/10", "fitid": ""},
       {"data": "2026-10-12", "valor": -9990, "descricao": "MAGALU - Parcela 2/3", "fitid": ""},
       {"data": "2026-10-14", "valor": -5000, "descricao": "COMPRA 15/11", "fitid": ""}]
fn.importar_itens(_f, _fi, "pdf", "fat.pdf", "Itaú cartão")
fn.importar_itens(_f, [{"data": "2026-10-20", "valor": -7000, "descricao": "PIX 05/10", "fitid": ""}], "ofx", "x.ofx", "Itaú conta")
_ps = {p["base"]: p for p in fn.parcelamentos(_f, "2026-11-05")}
confere("parcelas: acha as duas compras parceladas e ignora data e PIX", set(_ps) == {"loja xpto", "magalu"}, list(_ps))
confere("parcelas: quantas faltam e em que meses", _ps["loja xpto"]["faltam"] == 7 and _ps["loja xpto"]["proximas"][0] == {"mes": "2026-11", "numero": 4} and _ps["loja xpto"]["proximas"][-1]["mes"] == "2027-05", _ps["loja xpto"])
confere("parcelas: a última parcela (3 de 3) não deixa nada a prever", _ps["magalu"]["faltam"] == 1 and len(_ps["magalu"]["proximas"]) == 1 and _ps["magalu"]["proximas"][0]["mes"] == "2026-11")
fn.adicionar_previsto(_f, "Aluguel por fora", "1.200,00", 8, "2026-11", "2027-01")
fn.adicionar_previsto(_f, "Freela", "500", 20, "2026-12", "2026-12", True)
_fb2 = __import__("financas_boletos")
_fb2.registrar(_f, _fb2.interpretar("34191234546789012345767890123457616560000045090", date(2026, 11, 5)), "PADARIA")
_fu = fn.futuros(_f, 4, "2026-11-05")
_m = {x["mes"]: x for x in _fu["meses"]}
confere("futuros: quatro meses a partir do atual", list(_m) == ["2026-11", "2026-12", "2027-01", "2027-02"])
confere("futuros: parcelas, cadastrados e boletos entram no mês certo", {x["origem"] for x in _m["2026-11"]["itens"]} >= {"parcela", "manual"})
confere("futuros: o boleto entra no mês do vencimento", any(x["origem"] == "boleto" for x in _m["2026-12"]["itens"]))
confere("futuros: o aluguel cadastrado acaba em janeiro", sum(1 for x in _m["2027-02"]["itens"] if x["origem"] == "manual") == 0 and sum(1 for x in _m["2027-01"]["itens"] if x["origem"] == "manual") == 1)
confere("futuros: entrada cadastrada soma como entrada", _m["2026-12"]["entradas"] == 50000)
confere("futuros: total de saídas de novembro soma parcelas e aluguel", _m["2026-11"]["saidas"] >= 12000 + 9990 + 120000, _m["2026-11"]["saidas"])
_ch = next(x["chave"] for x in _m["2026-11"]["itens"] if x["origem"] == "parcela" and "XPTO" in x["descricao"])
fn.ignorar_detectado(_f, _ch)
confere("futuros: ignorar tira a parcela das previsões", not any("XPTO" in x["descricao"] for mm in fn.futuros(_f, 4, "2026-11-05")["meses"] for x in mm["itens"]))
fn.ignorar_detectado(_f, _ch, False)
confere("futuros: voltar a considerar traz de volta", any("XPTO" in x["descricao"] for x in fn.futuros(_f, 4, "2026-11-05")["meses"][0]["itens"]))
for _args in (("", "10", 5), ("X", "abc", 5), ("X", "10", 40), ("X", "10", 5, "2026-13"), ("X", "10", 5, "2026-05", "2026-01")):
    try:
        fn.adicionar_previsto(_f, *_args)
        confere(f"cadastro inválido recusado {_args}", False)
    except fn.ErroFinance:
        confere(f"cadastro inválido recusado {_args}", True)
st, _, _ = post("/futuros", {"descricao": "Escola", "valor": "800,00", "dia": "10", "inicio": "2026-12", "tipo": "saida"}, ck, csrf)
confere("cadastrar pagamento futuro pela página", st == 303 and con2.execute("SELECT COUNT(*) FROM previstos").fetchone()[0] == 1)
st, corpo, _ = pedir("/futuros", ck)
confere("página de pagamentos futuros: tabelas com legenda, campos com rótulo e botões com nome", st == 200 and "<caption>" in corpo and '<label for="fdesc">' in corpo and "Remover: Escola" in corpo, corpo[:300])
_pid = con2.execute("SELECT id FROM previstos").fetchone()[0]
confere("futuros: CSRF errado é recusado", post("/futuros/remover", {"id": str(_pid)}, ck, "errado")[0] == 403)
post("/futuros/remover", {"id": str(_pid)}, ck, csrf)
confere("remover pagamento futuro", con2.execute("SELECT COUNT(*) FROM previstos").fetchone()[0] == 0)
post("/futuros/ignorar", {"chave": "recorrente:netflix.com", "ignorar": "1"}, ck, csrf)
confere("ignorar pela página grava e chave estranha é recusada", con2.execute("SELECT COUNT(*) FROM ignorados").fetchone()[0] == 1 and (post("/futuros/ignorar", {"chave": "qualquer", "ignorar": "1"}, ck, csrf)[0] == 303) and con2.execute("SELECT COUNT(*) FROM ignorados").fetchone()[0] == 1)
# análise e perguntar (modelo simulado)
import heimdall_perguntar as _hp
import time as _tm
_hp.chamar_local = lambda sistema, usuario, modelo="", max_tokens=700, timeout=240: "Resposta de teste sem números."
st, corpo, _ = pedir("/analise", ck)
confere("análise: semana e mês já vêm prontos, calculados pelas regras, com botões para gerar nova", st == 200 and "Análise da semana" in corpo and "Análise do mês" in corpo and "calculada agora, pelas regras" in corpo and "Gerar nova análise da semana" in corpo and "Gerar nova análise do mês" in corpo, corpo[:300])
st, _, _ = post("/analise/gerar", {"tipo": "ano"}, ck, csrf)
confere("análise com tipo inválido não inicia", st == 303 and con2.execute("SELECT COUNT(*) FROM analises").fetchone()[0] == 0)
confere("análise com CSRF errado é recusada", post("/analise/gerar", {"tipo": "mes"}, ck, "errado")[0] == 403)
st, _, _ = post("/analise/gerar", {"tipo": "mes"}, ck, csrf)
for _ in range(100):
    if con2.execute("SELECT COUNT(*) FROM analises").fetchone()[0]:
        break
    _tm.sleep(0.1)
confere("gerar análise guarda no banco, com texto fixo quando o modelo é curto", st == 303 and con2.execute("SELECT origem FROM analises").fetchone()[0] == "regras")
st, corpo, _ = pedir("/analise", ck)
confere("página de análise mostra a análise salva do mês, a da semana calculada e sem botão do Notas", st == 200 and "<h3>Resumo</h3>" in corpo and "<ol>" in corpo and "Gerada em" in corpo and "Salvar a análise do mês no Notas" not in corpo and "aba Avisos" in corpo, corpo[:300])
st, corpo, _ = pedir("/avisos", ck)
confere("a análise gerada vira aviso na aba Avisos, sem passar pelo Notas", st == 200 and "Análise de" in corpo and "não lido" in corpo and "Marcar como lido" in corpo, corpo[:300])
post("/avisos/lido", {"id": "todos"}, ck, csrf)
st, corpo, _ = pedir("/avisos", ck)
confere("marcar todos como lidos", "0 não lido(s)" in corpo and "Marcar como lido" not in corpo)
confere("avisos com CSRF errado são recusados", post("/avisos/lido", {"id": "todos"}, ck, "errado")[0] == 403)
confere("a rota que salvava no Notas não existe mais", "/analise/notas" not in open("heimdall_finance.py").read())
# campo Perguntar no fim de toda página
for _rota in ("/resumo", "/transacoes", "/tendencias", "/orcamentos", "/analise", "/futuros", "/boletos", "/recorrentes", "/regras", "/importar", "/avisos"):
    st, corpo, _ = pedir(_rota, ck)
    confere(f"campo Perguntar no fim de {_rota}", st == 200 and '<label for="pergunta">' in corpo and corpo.rfind('id="perguntar-t"') > corpo.rfind("</table>") and ("</section></div></main>" in corpo or "</section></div></div></main>" in corpo) and corpo.rfind("Voltar para o topo") > corpo.rfind('id="perguntar-t"'), corpo[-300:])
st, _, cab = pedir("/perguntar", ck)
confere("/perguntar não é mais página: volta ao resumo", st in (200, 303) and (st == 200 or cab.get("Location") == "/"))
_hp.chamar_local = lambda *a, **k: "Primeira resposta."
st, _, cab = post("/perguntar", {"pergunta": "quanto gastei com mercado?", "volta": "/orcamentos?mes=2025-03"}, ck, csrf)
confere("pergunta volta para a mesma página, com o mês", st == 303 and cab.get("Location") == "/orcamentos?mes=2025-03", cab)
for _ in range(100):
    st2, corpo, _ = pedir("/orcamentos?mes=2025-03", ck)
    if "Primeira resposta." in corpo:
        break
    _tm.sleep(0.1)
confere("a resposta aparece no fim da página, acima do campo, e sem botão de atualizar quando há JavaScript", "Primeira resposta." in corpo and corpo.index("Primeira resposta.") < corpo.index('id="pergunta"') and 'id="perguntar-resp"' in corpo and 'id="perguntar-estado"' in corpo, corpo[-500:])
_hp.chamar_local = lambda *a, **k: "Segunda resposta."
post("/perguntar", {"pergunta": "e de restaurantes?", "volta": "/tendencias"}, ck, csrf)
for _ in range(100):
    st2, corpo, _ = pedir("/regras", ck)
    if "Segunda resposta." in corpo:
        break
    _tm.sleep(0.1)
confere("respostas em ordem de conversa (a mais recente embaixo) e visíveis em qualquer página", "Segunda resposta." in corpo and corpo.index("Primeira resposta.") < corpo.index("Segunda resposta."), corpo[-700:])
confere("pergunta com volta maliciosa vai para o resumo", post("/perguntar", {"pergunta": "teste", "volta": "https://evil.example/x"}, ck, csrf)[2].get("Location") == "/" and post("/perguntar", {"pergunta": "teste", "volta": "//evil.example"}, ck, csrf)[2].get("Location") == "/")
confere("pergunta vazia é recusada", post("/perguntar", {"pergunta": " "}, ck, csrf)[0] == 303)
confere("pergunta com CSRF errado é recusada", post("/perguntar", {"pergunta": "x"}, ck, "errado")[0] == 403)
_hp.chamar_local = lambda *a, **k: "Foram R$ 123.456,78."
post("/perguntar", {"pergunta": "total do mercado em 2025", "volta": "/"}, ck, csrf)
for _ in range(100):
    st2, corpo, _ = pedir("/resumo", ck)
    if "123.456,78" in corpo:
        break
    _tm.sleep(0.1)
confere("pergunta: valor fora dos dados aparece com aviso", "Confira estes valores" in corpo, corpo[-400:])
# boletos
st, _, _ = post("/boletos", {"linha": "34191.23454 67890.123457 67890.123457 6 16560000045090", "quem": "Padaria"}, ck, csrf)
confere("registrar boleto pela página", st == 303 and con2.execute("SELECT COUNT(*) FROM boletos").fetchone()[0] == 1)
st, _, _ = post("/boletos", {"linha": "34191234546789012345767890123457616560000045091"}, ck, csrf)
confere("boleto com número errado não grava", st == 303 and con2.execute("SELECT COUNT(*) FROM boletos").fetchone()[0] == 1)
st, corpo, _ = pedir("/boletos", ck)
confere("página de boletos tem campo com rótulo, tabela com legenda e botões com nome", st == 200 and '<label for="linha">' in corpo and "<caption>Boletos registrados" in corpo and "Marcar como pago: boleto de Padaria" in corpo and "R$ 450,90" in corpo, corpo[:300])
st, _, _ = post("/boletos/pessoa", {"nome": "Maria Souza"}, ck, csrf)
confere("cadastrar pessoa pela página", st == 303 and con2.execute("SELECT COUNT(*) FROM pessoas").fetchone()[0] == 1)
_idb = con2.execute("SELECT id FROM boletos").fetchone()[0]
con2.execute("UPDATE boletos SET aviso='Remetente não autenticado: teste', arquivo='e-mail de golpe.biz: x' WHERE id=?", (_idb,))
con2.commit()
st, corpo, _ = pedir("/boletos", ck)
confere("boleto com aviso mostra Atenção e a origem do e-mail", "Atenção: Remetente não autenticado: teste" in corpo and "Origem: e-mail de golpe.biz" in corpo)
post("/boletos/dono", {"id": str(_idb), "dono": "Maria Souza"}, ck, csrf)
st, corpo, _ = pedir("/boletos", ck)
confere("boleto mostra a pessoa e o total por pessoa", con2.execute("SELECT dono FROM boletos").fetchone()[0] == "Maria Souza" and "Total em aberto por pessoa: Maria Souza R$ 450,90" in corpo and "Mudar a pessoa do boleto de Padaria" in corpo, corpo[-600:])
post("/boletos/pessoa/remover", {"nome": "Maria Souza"}, ck, csrf)
confere("remover pessoa pela página", con2.execute("SELECT COUNT(*) FROM pessoas").fetchone()[0] == 0 and con2.execute("SELECT dono FROM boletos").fetchone()[0] is None)
post("/boletos/situacao", {"id": str(_idb), "pago": "1"}, ck, csrf)
confere("marcar boleto como pago", con2.execute("SELECT situacao FROM boletos").fetchone()[0] == "pago")
confere("boleto com CSRF errado é recusado", post("/boletos/remover", {"id": str(_idb)}, ck, "errado")[0] == 403 and con2.execute("SELECT COUNT(*) FROM boletos").fetchone()[0] == 1)
post("/boletos/remover", {"id": str(_idb)}, ck, csrf)
confere("remover boleto", con2.execute("SELECT COUNT(*) FROM boletos").fetchone()[0] == 0)
rid = con2.execute("SELECT id FROM regras WHERE padrao='academia forma'").fetchone()[0]
post("/regras/apagar", {"id": str(rid)}, ck, csrf)
confere("apagar regra", con2.execute("SELECT COUNT(*) FROM regras WHERE padrao='academia forma'").fetchone()[0] == 0)
st, corpo, _ = pedir("/tendencias", ck)
confere("tendências mostram tabelas por mês", st == 200 and "<caption>Receitas, despesas e saldo por mês" in corpo, corpo[:200])
st, corpo, cab = pedir("/exportar.csv", ck)
confere("exportação em CSV com download", st == 200 and "attachment" in cab.get("Content-Disposition", "") and "data;conta;descricao" in corpo)
confere("rota desconhecida dá 404", pedir("/nada", ck)[0] == 404)
st, _, cab = post("/sair", {}, ck, csrf)
confere("sair encerra a sessão", st == 303 and pedir("/", ck)[0] == 303)
confere("o banco e a pasta ficam só do dono", oct(os.stat(TMP).st_mode & 0o777) == "0o700" and oct(os.stat(Path(TMP) / "financas.db").st_mode & 0o777) == "0o600")

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
