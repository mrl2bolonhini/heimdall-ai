#!/usr/bin/env python3
"""Testa o coletor do DJEN: configuração por usuário, número CNJ, prazo, significado do ato, deduplicação, homônimo, falhas e limite de consultas."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="djen_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
import studio_banco as banco  # noqa: E402
import studio_djen as dj  # noqa: E402
import studio_miner_dados as d  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:400]})"))
    if not ok:
        falhas += 1


def levanta(f, *a):
    try:
        f(*a)
    except d.ErroMiner as ex:
        return str(ex)
    return ""


NUM = "0000832-35.2018.4.01.3202"
confere("número CNJ válido", dj.numero_cnj_valido(NUM) == "00008323520184013202")
confere("número CNJ com dígito errado", dj.numero_cnj_valido("0000832-36.2018.4.01.3202") == "")
confere("máscara", dj.mascara_cnj("00008323520184013202") == NUM)

confere("sem configuração", not dj.configurado())
r = dj.executar(requisitar=lambda p: (_ for _ in ()).throw(AssertionError("não deve consultar")))
confere("sem configuração não consulta", not r["ok"] and "Informe" in r["mensagem"], r)
confere("nome sem sobrenome recusado", "nome completo" in levanta(dj.salvar, "Maria", "", "", ""))
confere("OAB sem UF recusada", "UF" in levanta(dj.salvar, "", "123456", "", ""))
confere("processo inválido recusado", "inválido" in levanta(dj.salvar, "", "", "", "123"))
confere("salva", dj.salvar("Fulano de Tal", "123456", "sp", NUM + "\n" + NUM) == "Configuração salva.")
c = dj.configuracao()
confere("configuração gravada", c["nome"] == "Fulano de Tal" and c["oab_numero"] == "123456" and c["oab_uf"] == "SP" and c["processos"] == ["00008323520184013202"], c)

# prazo: quinta 26/11/2026 disponibiliza; publica sexta 27; conta a partir de segunda 30
pub, ini, fim, n, ut = dj.prazo_do_ato(date(2026, 11, 26), "prazo de 5 (cinco) dias")
confere("publicação e início", pub == date(2026, 11, 27) and ini == date(2026, 11, 30), (pub, ini))
confere("5 dias úteis", fim == date(2026, 12, 4) and ut, fim)
confere("recesso suspende a contagem", dj.prazo_do_ato(date(2026, 11, 27), "no prazo de 15 dias")[2] == date(2027, 1, 21))
confere("dias corridos", dj.dias_de_prazo("prazo de 10 dias corridos") == (10, False))
confere("sem prazo", dj.dias_de_prazo("Publique-se.") is None)
confere("feriado nacional", not dj.dia_util(date(2026, 12, 25)) and not dj.dia_util(date(2026, 4, 3)))

hoje = date(2026, 11, 27)
bruto_oab = {"id": 1001, "data_disponibilizacao": "2026-11-26", "siglaTribunal": "TJSP", "nomeOrgao": "1ª Vara Cível", "tipoComunicacao": "Intimação", "tipoDocumento": "Despacho",
             "numero_processo": "00008323520184013202", "texto": "<p>Manifeste-se a parte no prazo de 15 (quinze) dias.</p>"}
bruto_nome = {"id": 1002, "data_disponibilizacao": "2026-11-27", "siglaTribunal": "TRT2", "numero_processo": "11111111111111111111", "tipoComunicacao": "Intimação", "texto": "Designada audiência."}
bruto_cit = {"id": 1003, "data_disponibilizacao": "2026-11-27", "siglaTribunal": "TJRJ", "numero_processo": "22222222222222222222", "tipoComunicacao": "Citação", "texto": "Cite-se o réu."}
chamadas = []


def falso(p):
    chamadas.append(dict(p))
    if "numeroOab" in p:
        return {"count": 1, "items": [bruto_oab]} if p["numeroOab"] == "123456" and p["pagina"] == 1 else {"count": 0, "items": []}
    if "nomeParte" in p:
        return {"count": 2, "items": [bruto_nome, bruto_oab]}
    return {"count": 1, "items": [bruto_oab]}


publicados = []


def pub_falso(dado):
    publicados.append(dado)
    return {"novo": True}


r = dj.executar(hoje=hoje, requisitar=falso, dormir=lambda s: None, publicar=pub_falso)
confere("consulta ok", r["ok"] and r["total"] == 2 and r["novas"] == 2, r)
confere("variantes de OAB consultadas", sum(1 for p in chamadas if "numeroOab" in p) == len(dj.SUFIXOS_OAB))
confere("nome e processo consultados", any("nomeParte" in p for p in chamadas) and any(p.get("numeroProcesso") == "00008323520184013202" for p in chamadas))
confere("janela inicial de 7 dias", chamadas[0]["dataDisponibilizacaoInicio"] == "2026-11-20", chamadas[0])
a = {x["id"]: x for x in publicados}
confere("id estável", set(a) == {"djen:1001", "djen:1002"}, set(a))
r1 = a["djen:1001"]["resumo"]
confere("motivo mais forte vence (processo)", "número de um processo que você acompanha" in r1, r1)
confere("tem significado, prazo e o que fazer", "Abre prazo" in r1 and "Prazo: 18/12/2026" in r1 and "O que fazer:" in r1, r1)
r2 = a["djen:1002"]["resumo"]
confere("homônimo avisado", "homônimos" in r2 and "audiência" in r2.lower(), r2)
confere("sem prazo em dias", "não traz prazo em dias" in r2 and "Prazo:" not in r2.replace("prazo", ""), r2)
confere("HTML removido do trecho", "<p>" not in r1)
confere("fonte e título sem dados", a["djen:1001"]["fonte"] == "justica" and "TJSP" in a["djen:1001"]["titulo"] and "0000832" not in a["djen:1001"]["titulo"])
confere("citação é crítica", dj.alerta(dj.normalizar(bruto_cit, "oab"), hoje)["nivel"] == "critico")
confere("prazo próximo é crítico", dj.alerta(dj.normalizar(dict(bruto_oab, id=9, texto="Prazo de 2 dias."), "oab"), hoje)["nivel"] == "critico")
confere("estado gravado", dj.configuracao()["ultimo"] == "2026-11-27" and "2 comunicações" in dj.configuracao()["estado"])

# segunda consulta: janela com sobreposição e sem repetir o aviso
chamadas.clear()
real = []
import studio_alertas as al  # noqa: E402
al.mac.publicar = lambda x: False
al.bark.enviar_bark = lambda x: False
r = dj.executar(hoje=date(2026, 11, 28), requisitar=falso, dormir=lambda s: None)
confere("janela com sobreposição", chamadas[0]["dataDisponibilizacaoInicio"] == "2026-11-24", chamadas[0])
r = dj.executar(hoje=date(2026, 11, 28), requisitar=falso, dormir=lambda s: None)
confere("sem repetir o aviso", r["total"] == 2 and r["novas"] == 0, r)
con = banco.conectar(somente_leitura=True)
n = con.execute("SELECT COUNT(*) FROM triagem WHERE id LIKE 'djen:%'").fetchone()[0]
con.close()
confere("alertas na triagem da Cidadania, uma vez", n == 2 and len(d.pendentes("cidadania")) == 2, n)

# falhas
def fora(p):
    raise dj.ErroDJEN("O DJEN recusou o acesso (ele só responde a acessos feitos do Brasil).")


pubs = []
for i in range(3):
    r = dj.executar(hoje=date(2026, 12, 1 + i), requisitar=fora, dormir=lambda s: None, publicar=lambda x: pubs.append(x) or {"novo": True})
confere("falha não avança a data", not r["ok"] and dj.configuracao()["ultimo"] == "2026-11-28", r)
confere("três falhas viram aviso com contexto", len(pubs) == 1 and "Domicílio Judicial" in pubs[0]["resumo"], pubs)
dormiu = []
estado = {"n": 0}


def limite(p):
    estado["n"] += 1
    if estado["n"] == 1:
        raise dj.ErroDJEN("limite")
    return {"count": 1, "items": [bruto_oab]}


confere("429 espera e tenta de novo", len(dj.buscar({"numeroProcesso": "x"}, limite, dormir=dormiu.append)) == 1 and 65 in dormiu)


def sempre429(p):
    raise dj.ErroDJEN("limite")


try:
    dj.buscar({"x": 1}, sempre429, dormir=lambda s: None)
    confere("429 repetido desiste", False)
except dj.ErroDJEN as ex:
    confere("429 repetido desiste", "limitou" in str(ex), ex)

# paginação
pags = []


def paginado(p):
    pags.append(p["pagina"])
    return {"count": 3, "items": [dict(bruto_oab, id=p["pagina"] * 10 + k) for k in range(2)][: (2 if p["pagina"] == 1 else 1)]}


confere("pagina até o total", len(dj.buscar({"x": 1}, paginado, dormir=lambda s: None)) == 3 and pags == [1, 2], pags)

# consulta diária devida
dj._gravar(djen_ultimo="2026-11-28", djen_tentativa="2026-11-28T07:00:00")
confere("devida: já rodou hoje", not dj.devida(datetime(2026, 11, 28, 9, 0)))
confere("devida: antes da hora", not dj.devida(datetime(2026, 11, 29, 6, 0)))
confere("devida: depois da hora", dj.devida(datetime(2026, 11, 29, 8, 0)))
dj._gravar(djen_tentativa="2026-11-29T07:30:00")
confere("devida: espera depois de tentar", not dj.devida(datetime(2026, 11, 29, 8, 0)) and dj.devida(datetime(2026, 11, 29, 9, 45)))
os.environ["STUDIO_MINER_DJEN"] = "0"
confere("interruptor desliga", not dj.devida(datetime(2026, 11, 29, 12, 0)) and not dj.executar()["ok"])
del os.environ["STUDIO_MINER_DJEN"]
confere("limpar configuração", dj.salvar("", "", "", "") .startswith("Configuração limpa") and not dj.configurado())

# todas as pessoas: cada uma com a própria configuração, o próprio banco e sem aviso no Mac do dono
import studio_pessoas as pe  # noqa: E402
ANA = "p" + "a" * 12
BETO = "p" + "b" * 12
dj.salvar("Dona da Casa", "", "", NUM)
dj._gravar(djen_ultimo="", djen_tentativa="")
os.environ["STUDIO_MINER_DJEN_HORA"] = "0"
for quem, nome, num in ((ANA, "Ana Convidada", ""), (BETO, "Beto Convidado", "")):
    with pe.definir(quem), banco.da_pessoa(quem):
        dj.salvar(nome, "", "", num)
con_dono = banco.conectar(somente_leitura=True)
con_dono.close()
avisos_mac = []
al.mac.publicar = lambda x: avisos_mac.append(x) or True
al.bark.enviar_bark = lambda x: avisos_mac.append(x) or True
chamadas2 = []


def falso2(p):
    chamadas2.append(dict(p))
    return {"count": 1, "items": [dict(bruto_nome, id=7000 + len(chamadas2))]}


feitos = dj.executar_todos(hoje=date.today(), requisitar=falso2, dormir=lambda s: None)
confere("percorre o dono e os convidados", set(feitos) == {"dono", ANA, BETO}, feitos)
confere("cada pessoa consulta o próprio nome", {p.get("nomeParte") for p in chamadas2 if "nomeParte" in p} == {"Dona da Casa", "Ana Convidada", "Beto Convidado"}, chamadas2)
with pe.definir(ANA), banco.da_pessoa(ANA):
    con = banco.conectar(somente_leitura=True)
    n_ana = con.execute("SELECT COUNT(*) FROM triagem WHERE id LIKE 'djen:%'").fetchone()[0]
    con.close()
confere("a triagem do convidado fica no banco dele", n_ana >= 1, n_ana)
con = banco.conectar(somente_leitura=True)
ids_dono = {r[0] for r in con.execute("SELECT id FROM triagem WHERE id LIKE 'djen:%'")}
con.close()
confere("o dono não vê os alertas dos convidados", not any(i in ids_dono for i in ("djen:7003", "djen:7004")), ids_dono)
confere("só o alerta do dono notifica o Mac", len(avisos_mac) >= 1 and all("Ana" not in str(x) and "Beto" not in str(x) for x in avisos_mac), avisos_mac)

print("\nFALHAS:", falhas)
_sys.exit(1 if falhas else 0)
