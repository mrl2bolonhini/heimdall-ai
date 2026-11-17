#!/usr/bin/env python3
"""Testa o Heimdall Finance: leitura de OFX e CSV, deduplicação, categorias e regras, relatórios, login e páginas.
Usa um banco temporário; nada toca a internet."""
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
os.environ.update({"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
TMP = tempfile.mkdtemp(prefix="finance_teste_")
os.environ["HEIMDALL_FINANCE_DIR"] = TMP
sys.path.insert(0, str(AQUI))
import financas_nucleo as fn  # noqa: E402
import heimdall_cloud as hc  # noqa: E402
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
st, corpo, cab = pedir("/", ck)
confere("início sem dados convida a importar", st == 200 and "Importar extrato" in corpo and "Ainda não há lançamentos" in corpo, (st, corpo[:300]))
csp = cab.get("Content-Security-Policy", "")
confere("política de conteúdo: nada de script", "default-src 'none'" in csp and "script-src" not in csp and "<script" not in corpo, csp)
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

st, corpo, _ = pedir("/?mes=2026-01", ck)
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
