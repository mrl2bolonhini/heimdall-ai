#!/usr/bin/env python3
"""Leitor de documentos clínicos: atestado com CID, laudo de imagem, IA do leitor (nuvem com reserva local, texto reduzido, valores conferidos
no texto) e formatos TXT e DOCX. Documentos FICTÍCIOS."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="heimdall-tipos-"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "banco"), "STUDIO_EXAMES_DIR": str(TMP / "health"), "STUDIO_EXAMES_LLM": "0"})
import heimdall_banco as banco  # noqa: E402
import heimdall_exames as ex  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


def sql(q, *p):
    con = sqlite3.connect(banco.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(q, p)]
    finally:
        con.close()


ATESTADO = """CLINICA ORTOPEDICA MODELO
ATESTADO MEDICO
Atesto para os devidos fins que o(a) paciente FULANO DE TAL, CPF 000.000.000-00, esteve sob meus cuidados e necessita de
afastamento de suas atividades por 15 (quinze) dias, a partir de 10/11/2026, em razão de CID M23.2 - Transtornos internos dos joelhos.
Cidade Modelo, 10 de novembro de 2026
Dr. Carlos Souza CRM-SP 123456
"""
LAUDO = """CENTRO DE DIAGNOSTICO MODELO
RESSONÂNCIA MAGNÉTICA DO JOELHO DIREITO
Data do exame: 12/11/2026
Indicação clínica: dor e bloqueio articular.
Técnica: sequências multiplanares ponderadas em T1 e T2.
Achados: lesão do corno posterior do menisco medial.
Conclusão:
Rotura complexa do menisco medial.
Condropatia patelar grau II.
Dr. Ana Lima CRM-SP 654321
"""
SOLTO = """Declaração
O paciente deve ficar afastado do trabalho por dez dias por causa de problema no joelho, com CID F32.1 informado pelo médico.
Dr. Beltrano Exemplo CRM-SP 111222
Data: 03/11/2026
"""

# ----- classificação por regras
confere("atestado é reconhecido", ex.classificar(ATESTADO) == "atestado", ex.classificar(ATESTADO))
confere("laudo de imagem é reconhecido", ex.classificar(LAUDO) == "laudo", ex.classificar(LAUDO))
confere("um exame de laboratório não vira laudo", ex.classificar("Laboratório\nResultado\nMétodo: x\nMaterial: soro\nHemograma\nLaudo liberado", 5) == "exame")

# ----- atestado por regras
a = ex.ler_atestado_regra(ATESTADO, "2026-11-10")
confere("atestado: CID, dias, início e fim calculado", len(a) == 1 and a[0]["cid"] == "M23.2" and a[0]["dias"] == 15 and a[0]["inicio"] == "2026-11-10"
        and a[0]["fim"] == "2026-11-24", a)
confere("atestado: descrição do CID só se o documento a traz", a[0]["cid_texto"].startswith("Transtornos internos"), a[0]["cid_texto"])
confere("atestado: médico com CRM", "Carlos Souza" in a[0]["medico"] and "123456" in a[0]["medico"], a[0]["medico"])
duplo = ex.ler_atestado_regra("Atestado. Afastamento por 5 dias. CID: M23.2, M25.5", "2026-11-10")
confere("atestado com dois CIDs vira dois registros", [x["cid"] for x in duplo] == ["M23.2", "M25.5"], duplo)
periodo = ex.ler_atestado_regra("Atestado: afastamento no período de 01/11/2026 a 07/11/2026. CID M54", "2026-11-01")
confere("atestado com período: dias calculados", periodo[0]["dias"] == 7 and periodo[0]["fim"] == "2026-11-07", periodo)
confere("texto de CID parecido com palavra não é CID", ex.ler_atestado_regra("Atestado de comparecimento, afastamento de 1 dia, cidade X12Y", "2026-11-01")[0]["cid"] == "")

# ----- laudo por regras
l = ex.ler_laudo_regra(LAUDO)
confere("laudo: modalidade e título", l and l[0]["modalidade"] == "ressonância magnética" and "JOELHO DIREITO" in l[0]["titulo"].upper(), l)
confere("laudo: conclusão copiada até a assinatura", l[0]["conclusao"] == "Rotura complexa do menisco medial. Condropatia patelar grau II.", l[0]["conclusao"])
confere("laudo: médico", "Ana Lima" in l[0]["medico"])

# ----- do arquivo ao banco, com a conferência
ex.texto_do_arquivo = lambda dados, nome: ((ATESTADO if b"atestado" in dados else LAUDO), False)
r1 = ex.registrar(b"atestado ficticio", "atestado.pdf")
confere("registra atestado: tipo, data e itens", r1["tipo"] == "atestado" and r1["dia"] == "2026-11-10" and r1["itens"] == 0 or r1["tipo"] == "atestado", r1)
txt = ex.resumo_documento(r1["id"])
confere("resumo do atestado", "Afastamento de 15 dia(s)" in txt and "CID M23.2" in txt and "studio health --labs confirm" in txt, txt)
ex.confirmar(r1["id"])
confere("atestado guardado no banco", sql("SELECT cid, dias, inicio, fim FROM atestados")[0] == {"cid": "M23.2", "dias": 15, "inicio": "2026-11-10", "fim": "2026-11-24"})
confere("relatório de atestados", "CID M23.2" in ex.relatorio_atestados())
r2 = ex.registrar(b"laudo ficticio", "laudo.pdf")
confere("registra laudo", r2["tipo"] == "laudo" and r2["dia"] == "2026-11-12", r2)
ex.confirmar(r2["id"])
confere("laudo guardado e listado", sql("SELECT modalidade, conclusao FROM laudos")[0]["modalidade"] == "ressonância magnética" and "menisco medial" in ex.relatorio_laudos())
confere("banco: tabelas novas fora da gravação por HTTP", all(t not in banco.TABELAS for t in ("atestados", "laudos")))
confere("banco: resumo conhece as tabelas novas", banco.resumo()["atestados"]["linhas"] == 1 and banco.resumo()["laudos"]["linhas"] == 1)

# ----- IA: sempre conferida no texto
ex.USAR_MODELO = True
respostas = []
ex._modelo = lambda prompt, max_tokens=1400: respostas.pop(0) if respostas else ""
respostas.append(json.dumps({"dias": "30", "cid": "M99", "inicio": "01/01/2020"}))
ia = ex.ler_atestado_modelo(SOLTO, "2026-11-03")
confere("IA inventa dias, CID e data: nada passa", ia == [], ia)
respostas.append(json.dumps({"dias": "10", "cid": "F32.1", "inicio": "03/11/2026"}))
ia = ex.ler_atestado_modelo(SOLTO, "2026-11-03")
confere("IA: o CID escrito no texto passa; dias por extenso ('dez') não são aceitos como número", ia and ia[0]["cid"] == "F32.1" and ia[0]["dias"] is None, ia)
respostas.append(json.dumps({"titulo": "RM", "conclusao": "Rotura total do ligamento cruzado."}))
r, av = ex.extrair_laudos("Clínica X\nRessonância magnética do joelho\nEdema.\nDr. Zé CRM-SP 1")
confere("IA: conclusão que não está no laudo é ignorada, com aviso", r and r[0]["conclusao"] == "" and any("não está escrita" in x for x in av), (r, av))
respostas.append(json.dumps({"titulo": "RM joelho", "conclusao": "Edema ósseo discreto."}))
r, av = ex.extrair_laudos("Clínica X\nRessonância magnética do joelho\nResumo do exame: Edema ósseo discreto.\nDr. Zé CRM-SP 1")
confere("IA: conclusão escrita no laudo, com outro cabeçalho, passa", r and r[0]["conclusao"] == "Edema ósseo discreto.", (r, av))
respostas.append(json.dumps({"tipo": "atestado"}))
confere("IA classifica um documento sem pistas para as regras", ex.classificar_ia("Texto qualquer de documento.") == "atestado")
respostas.append("lixo")
confere("IA devolvendo lixo vira 'outro'", ex.classificar_ia("Texto qualquer de documento.") == "outro")
respostas.append(json.dumps({"tipo": "atestado"}))
respostas.append(json.dumps({"dias": "10", "cid": "F32.1"}))
x = ex.extrair("Declaração sem as palavras de sempre. Fica afastado por 10 dias. F32.1 no joelho.", False)
confere("extrair: tipo indicado pela IA vem com aviso", x["tipo"] == "atestado" and any("indicado pelo modelo" in a for a in x["avisos"]), x["avisos"])
ex.USAR_MODELO = False

# ----- quando chamar a IA para exames
LAB_LIMPO = "\n".join(["Laboratório X", "RESULTADO | INTERVALO DE REFERÊNCIA"] + [f"Hemoglobina   {14 + i/10:.1f} g/dL   13,0 a 17,0 g/dL" for i in range(1)]
                      + ["Hematócrito   45,0 %   40,0 a 50,0 %", "VCM   91,0 fL   83,0 a 101,0 fL"])
r_l, d_l = ex.ler_resultados_regra(LAB_LIMPO)
confere("exame limpo: não precisa da IA", ex.ia_ajuda(LAB_LIMPO, r_l, d_l, False) is False)
confere("texto de OCR: chama a IA", ex.ia_ajuda(LAB_LIMPO, r_l, d_l, True) is True)
confere("quase nada lido: chama a IA", ex.ia_ajuda("Algo", [], [], False) is True)
ESTRANHO = LAB_LIMPO + "\n" + "\n".join(f"Dosagem exótica {i}: {i}0 mg/dL" for i in range(1, 6)) + "\n" + "\n".join(f"Marcador {i} - {i}5 U/L" for i in range(1, 4))
r_e, d_e = ex.ler_resultados_regra(ESTRANHO)
sobras = {}
ex._registros_do_laudo(ESTRANHO, sobras)
confere("formato que as regras não entendem: sobras viram motivo para chamar a IA", ex.ia_ajuda(ESTRANHO, r_e, d_e, False) == (sobras.get("sobras", 0) >= 3), (sobras, len(r_e)))

# ----- nuvem com reserva local, texto reduzido
class Abridor:
    def __init__(self, resp):
        self.resp = resp

    def open(self, req, timeout=0):
        class R:
            def __init__(s, b):
                s.b = b

            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s, n=-1):
                return s.b
        return R(json.dumps({"choices": [{"message": {"content": self.resp}}]}).encode())


ex.USAR_MODELO = True
modelo_real = ex.__dict__.get("_modelo_original")
import importlib  # noqa: E402
importlib.reload(ex)
ex.USAR_MODELO = True
ex._abridor_local = Abridor('{"origem": "local"}')
vistos = []
ex.nuvem.ativo = lambda *a, **k: True
ex.nuvem.chat = lambda sistema, usuario, **k: (vistos.append(usuario) or '<think>x</think>{"origem": "nuvem"}')
r = ex._modelo("Paciente: Fulano de Tal\nCPF 000.000.000-00 RG 123456789 fone (11) 99999-8888 a@b.com\nHemoglobina 14,4 g/dL")
confere("nuvem ligada: usa a nuvem e tira o raciocínio da resposta", json.loads(r) == {"origem": "nuvem"}, r)
confere("nuvem: o texto vai sem CPF, RG, telefone, e-mail e nome do paciente", vistos and not any(x in vistos[0] for x in ("000.000.000-00", "123456789", "99999-8888", "a@b.com", "Fulano")) and "14,4" in vistos[0], vistos)


def cai(*a, **k):
    raise RuntimeError("sem rede")


ex.nuvem.chat = cai
confere("nuvem falha: cai para o modelo local", json.loads(ex._modelo("x")) == {"origem": "local"})
os.environ["STUDIO_EXAMES_NUVEM"] = "0"
ex.nuvem.chat = lambda *a, **k: '{"origem": "nuvem"}'
confere("STUDIO_EXAMES_NUVEM=0: nunca usa a nuvem", json.loads(ex._modelo("x")) == {"origem": "local"})
del os.environ["STUDIO_EXAMES_NUVEM"]
ex.nuvem.ativo = lambda *a, **k: False
confere("nuvem desligada: usa o modelo local", json.loads(ex._modelo("x")) == {"origem": "local"})
ex.USAR_MODELO = False
confere("IA desligada (STUDIO_EXAMES_LLM=0): sem modelo nenhum", ex._modelo("x") == "")

# ----- formatos TXT e DOCX
LAB = "Laboratório Modelo\nRESULTADO | INTERVALO DE REFERÊNCIA\nHemoglobina   14,4 g/dL   13,0 a 17,0 g/dL\nHematócrito   45,0 %   40,0 a 50,0 %\nVCM   91,0 fL   83,0 a 101,0 fL\nData da coleta: 10/11/2026\n"


def docx_com(linhas):
    corpo = "".join(f"<w:p><w:r><w:t>{l}</w:t></w:r></w:p>" for l in linhas)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{corpo}</w:body></w:document>'
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", xml)
        z.writestr("[Content_Types].xml", "<Types/>")
    return b.getvalue()


t, ocr = ex.texto_do_arquivo(LAB.encode("utf-8"), "laudo.txt")
confere("TXT: lido direto", "Hemoglobina" in t and ocr is False)
t, ocr = ex.texto_do_arquivo(LAB.encode("latin-1"), "laudo.txt")
confere("TXT em latin-1 também", "Hematócrito" in t)
t, ocr = ex.texto_do_arquivo(docx_com(LAB.splitlines()), "laudo.docx")
confere("DOCX: parágrafos viram linhas", "Hemoglobina   14,4" in t and ocr is False and len(ex.ler_resultados_regra(t)[0]) == 3, t)
try:
    ex.texto_do_arquivo(b"PK\x03\x04lixo", "x.docx")
    erro = False
except ex.ErroExames:
    erro = True
confere("DOCX corrompido: erro claro", erro)
try:
    ex.texto_do_arquivo(b"x", "x.exe")
    erro = False
except ex.ErroExames as e:
    erro = "TXT" in str(e) and "DOCX" in str(e)
confere("formato desconhecido: a mensagem lista os aceitos", erro)
confere("iPhone: reconhece WEBP, TIFF e DOCX pelo conteúdo", all(ex.receber(d, n)["arquivo"] for d, n in ((b"RIFF\x00\x00\x00\x00WEBPxxxx", "a"), (b"II*\x00xxxxxxxx", "b"), (docx_com(["Texto de teste longo aqui"]), "c"))))

# ----- documentos digitais (Memed): receita, encaminhamento em texto livre, atestado com CID sozinho, pedido de exame, laudo sem conclusão
RECEITA = """                    DRA ANA EXEMPLO
                    CRM: 11111 SP
Nome: FULANO DE TAL
CPF: 000.000.000-00      Data e hora: 16/11/2026 - 16:51:58 (GMT-3)

1. Marcax 100mg, Comprimido revestido (30un) Fabricante                         2 embalagens
    Hemifumarato de substanciax 100mg

    TOMAR 1 CP A NOITE.

                   MEMED - Acesso à sua receita digital via QR Code
                   Assinado digitalmente por ANA EXEMPLO - CRM 11111 SP
            RECEITA DE CONTROLE ESPECIAL
  PRESCRIÇÃO
  Nome do medicamento ou substância: Marcax 100mg
  Concentração: Hemifumarato de substanciax 100mg
  Quantidade: 2 embalagens (30un)
  Posologia: TOMAR 1 CP A NOITE.
"""
x = ex.extrair(RECEITA, False)
confere("receita digital: um só item, com marca, princípio ativo, quantidade e posologia (sem repetir a segunda via)",
        len(x["receitas"]) == 1 and x["receitas"][0]["medicamento"] == "Marcax (hemifumarato de substanciax)" and x["receitas"][0]["quantidade"] == "2 embalagens (30un)"
        and x["receitas"][0]["posologia"] == "TOMAR 1 CP A NOITE." and x["tipo"] == "receita", x["receitas"])
confere("receita digital: prescritor com UF depois do número", x["emissor"] == "ANA EXEMPLO (CRM-SP 11111)", x["emissor"])

ENC = """Nome: FULANO DE TAL
CPF: Não há CPF cadastrado       Data e hora: 13/07/2026 - 12:34:11 (GMT-3)

Encaminhamento

10 SESSÕES DE FISIOTERAPIA

HD = PÓS OP. DE RECONSTRUÇÃO DO LCA DE JOELHO D .

M23

   MEMED - Acesso à sua receita digital via QR Code
   Assinado digitalmente por BELTRANO EXEMPLO - CRM 22222 SP
"""
x = ex.extrair(ENC, False)
e = x["encaminhamentos"][0] if x["encaminhamentos"] else {}
confere("encaminhamento em texto livre: especialidade, motivo e CID", x["tipo"] == "encaminhamento" and e.get("especialidade") == "Fisioterapia" and e.get("cid") == "M23"
        and "10 SESSÕES" in e.get("motivo", "") and "hipótese diagnóstica" in e.get("motivo", ""), x["encaminhamentos"])
confere("encaminhamento: o médico vem da assinatura digital", x["emissor"] == "BELTRANO EXEMPLO (CRM-SP 22222)", x["emissor"])
x = ex.extrair("Encaminhamento\n\nUBS\n\nSOLICITO RETIRADA DE PONTOS DO PACIENTE EM QUESTÃO, NO DIA 17/07/2026\n\nGRATO\n\nMEMED - x\n", False)
confere("encaminhamento: retirada de pontos na UBS, sem 'GRATO'", x["encaminhamentos"] and x["encaminhamentos"][0]["especialidade"] == "Retirada de pontos (UBS)" and "GRATO" not in x["encaminhamentos"][0]["motivo"], x["encaminhamentos"])

ATEST2 = """Data e hora: 13/07/2026 - 12:35:29 (GMT-3)

Atestado

ATESTADO MÉDICO

O PACIENTE EM QUESTÃO, DEVE FICAR AFASTADO DO TRABALHO, DE 08/07/2026 A
21/07/2026.

M23

ATT.
   Assinado digitalmente por BELTRANO EXEMPLO - CRM 22222 SP
"""
x = ex.extrair(ATEST2, False)
a = x["atestados"][0] if x["atestados"] else {}
confere("atestado digital: período em duas linhas, CID sozinho na linha e dias calculados", x["tipo"] == "atestado" and a.get("cid") == "M23" and a.get("inicio") == "2026-07-08"
        and a.get("fim") == "2026-07-21" and a.get("dias") == 14, x["atestados"])

PEDIDO = """DRA ANA EXEMPLO
CRM: 11111 SP
Pedido de Exame

Hemograma completo                                              TUSS: 40304361

Ferritina                                                       TUSS: 40316270

Hemograma completo                                              TUSS: 40304361
"""
x = ex.extrair(PEDIDO, False)
confere("pedido de exame: lista sem repetir, com TUSS, e não é resultado", x["tipo"] == "pedido" and [p["exame"] for p in x["pedidos"]] == ["Hemograma completo", "Ferritina"]
        and x["pedidos"][0]["tuss"] == "40304361" and not x["resultados"], x["pedidos"])
r = ex.registrar(PEDIDO.replace("Pedido de Exame", "Pedido de Exame\nData: 17/08/2026").encode("utf-8"), "pedido.txt")
confere("pedido: registra como pedido, resume e confirma na tabela própria", r["tipo"] == "pedido" and "Hemograma completo (TUSS 40304361)" in ex.resumo_documento(r["id"]), r)
ex.confirmar(r["id"])
confere("pedido: guardado e listado", len(ex._ler("SELECT * FROM pedidos_exame")) == 2 and "Ferritina" in ex.relatorio_pedidos())

LAUDO2 = """Protocolo:   000000000000          Data: 18/4/2026
Nome:        FULANO DE TAL         Unidade: CENTRO MODELO

                RESSONÂNCIA MAGNÉTICA DO JOELHO DIREITO

Indicação clínica: dor.
Técnica: Realizadas sequências FSE.

Análise:
Condropatia patelar com irregularidades superficiais.
Meniscos sem evidências de lesões.

                                DR. ALFREDO EXEMPLO
                                CRM-11111

                      Este laudo foi assinado eletronicamente
"""
x = ex.extrair(LAUDO2, False)
l = x["laudos"][0] if x["laudos"] else {}
confere("laudo sem conclusão: guarda a análise inteira e avisa", l.get("conclusao") == "" and "Meniscos sem evidências de lesões." in l.get("achados", "") and "DR." not in l.get("achados", "")
        and any("não traz conclusão" in a for a in x["avisos"]), (l, x["avisos"]))
confere("laudo: médico pela linha 'DR.', sem o CRM colado ao nome", l.get("medico") == "ALFREDO EXEMPLO (CRM 11111)", l.get("medico"))
confere("'drenagem' não vira o Dr.", ex.achar_prescritor("Demais vias de drenagem dos seios pérvias. (CRM 131103)") == "(CRM 131103)", ex.achar_prescritor("Demais vias de drenagem dos seios pérvias. (CRM 131103)"))

print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)
