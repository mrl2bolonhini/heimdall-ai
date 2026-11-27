#!/usr/bin/env python3
"""Testa os dados do Studio Memory: envio, duplicado, busca sem acento, revisão, etiquetas, lixeira, pasta de entrada e sugestão da IA."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")

import heimdall_memory_dados as L  # noqa: E402
import heimdall_banco as banco  # noqa: E402

L.PROJECT_DIR = TMP
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


def erro(fn, *a, **k):
    try:
        fn(*a, **k)
    except L.ErroMemory as ex:
        return str(ex)
    return ""


contrato = ("CONTRATO DE PRESTAÇÃO DE SERVIÇOS entre a CONTRATANTE Empresa Alfa e a CONTRATADA Beta. Cláusula primeira: objeto. "
            "Cláusula segunda: prazo. Foro de São Paulo. Assinado em 12/03/2026.").encode()
r = L.adicionar("contrato_alfa.txt", contrato, usar_ia=False)
confere("adiciona documento novo", r["novo"] and r["id"] == 1)
d = L.obter(r["id"])
confere("tipo por regras é Contrato", d["tipo"] == "Contrato", d.get("tipo"))
confere("etiqueta automática", d["etiquetas"] == ["Contrato"], d.get("etiquetas"))
confere("fica a revisar", d["revisado"] == 0)
confere("título vem do nome do arquivo", d["titulo"] == "contrato alfa", d["titulo"])
confere("arquivo guardado pelo hash", (L.pasta_arquivos() / d["sha256"][:2] / d["sha256"]).is_file())
r2 = L.adicionar("copia.txt", contrato, usar_ia=False)
confere("duplicado não entra de novo", not r2["novo"] and r2["id"] == 1)
confere("formato recusado", "Formato não aceito" in erro(L.adicionar, "x.exe", b"abc"))
confere("arquivo vazio recusado", "vazio" in erro(L.adicionar, "x.txt", b""))
confere("arquivo grande recusado", "MB" in erro(L.adicionar, "x.txt", b"a" * (L.LIMITE_BYTES + 1)))
L.adicionar("conta.txt", "Boleto. Beneficiário Luz S.A. Vencimento 10/12/2026. Linha digitável 1234. Nosso número 99.".encode(), usar_ia=False)
docs, total = L.listar(q="prestacao servicos")
confere("busca sem acento acha o contrato", total == 1 and docs[0]["id"] == 1, total)
docs, total = L.listar(q="PRESTAÇÃO")
confere("busca com acento e caixa", total == 1)
docs, total = L.listar(q="benefic")
confere("busca por prefixo", total == 1 and docs[0]["tipo"] == "Boleto", total)
confere("busca sem resultado", L.listar(q="inexistente")[1] == 0)
confere("busca com aspas e símbolos não quebra", L.listar(q='"a" OR (b*')[1] >= 0)
confere("filtro por tipo", L.listar(tipo="Boleto")[1] == 1)
confere("só a revisar", L.listar(so_revisar=True)[1] == 2)
L.atualizar(1, "Contrato Alfa", "Contrato", "2026-03-12", "Empresa Alfa", "cliente, 2026")
d = L.obter(1)
confere("revisão marca revisado", d["revisado"] == 1 and d["titulo"] == "Contrato Alfa" and d["data_doc"] == "2026-03-12")
confere("etiquetas revisadas", d["etiquetas"] == ["2026", "cliente"], d["etiquetas"])
confere("busca acha pelo emissor", L.listar(q="alfa")[1] == 1)
confere("busca acha pela etiqueta", L.listar(q="cliente")[1] == 1)
confere("filtro por etiqueta", L.listar(etiqueta="cliente")[1] == 1)
confere("data inválida recusada", "AAAA-MM-DD" in erro(L.atualizar, 1, "T1", "Outros", "12/03/2026", "", ""))
confere("tipo inválido recusado", "Tipo" in erro(L.atualizar, 1, "T1", "Xis", "", "", ""))
confere("título curto recusado", "título" in erro(L.atualizar, 1, "A", "Outros", "", "", ""))
confere("etiqueta inválida recusada", "etiquetas" in erro(L.validar_etiqueta, "<script>"))
nome, dados = L.arquivo(1)
confere("baixa o arquivo original", nome == "contrato_alfa.txt" and dados == contrato)
L.lixeira(1)
confere("lixeira some da lista", L.listar(q="alfa")[1] == 0 and L.listar(lixeira=True)[1] == 1)
L.lixeira(1, restaurar=True)
confere("restaura da lixeira", L.listar(q="alfa")[1] == 1)
(L.pasta_entrada()).mkdir(parents=True, exist_ok=True)
(L.pasta_entrada() / "novo.txt").write_bytes("Recibo. Recebi de Maria a quantia. Comprovante de pagamento do aluguel.".encode())
(L.pasta_entrada() / "repetido.txt").write_bytes(contrato)
(L.pasta_entrada() / "ruim.exe").write_bytes(b"x")
res = L.processar_entrada(usar_ia=False)
confere("pasta de entrada", res == {"novos": 1, "repetidos": 1, "recusados": 1}, res)
confere("entrada esvaziada", not any(p.is_file() for p in L.pasta_entrada().iterdir()))
ia = L.validar_sugestao_ia('texto {"titulo":"Contrato Alfa Beta","tipo":"Contrato","data":"2026-03-12","emissor":"Empresa Alfa","etiquetas":["serviços","<x>"]} fim', contrato.decode())
confere("IA válida", ia.get("tipo") == "Contrato" and ia.get("emissor") == "Empresa Alfa" and ia["etiquetas"] == ["serviços"], ia)
ia = L.validar_sugestao_ia('{"titulo":"Ok título","tipo":"Hack","data":"ontem","emissor":"Inventada SA","etiquetas":"x"}', contrato.decode())
confere("IA inválida é descartada campo a campo", "tipo" not in ia and "data_doc" not in ia and "emissor" not in ia and "etiquetas" not in ia, ia)
confere("IA sem JSON", L.validar_sugestao_ia("sem json", "x") == {})
confere("IA com texto curto não é chamada", L.sugerir_por_ia("curto") == {})
confere("contagens", dict(L.tipos_com_contagem())["Boleto"] == 1 and any(e["nome"] == "cliente" for e in L.etiquetas_com_contagem()))
confere("estado", L.estado()["documentos"] == 3)
with banco.da_pessoa("ana"):
    confere("acervo por pessoa isolado", L.estado()["documentos"] == 0 and "ana" in str(L.caminho()))
    L.adicionar("a.txt", b"Contrato clausula contratante foro de teste", usar_ia=False)
    confere("pasta de arquivos da pessoa", "ana" in str(L.pasta_arquivos()))
confere("dono não vê o da pessoa", L.estado()["documentos"] == 3)
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
