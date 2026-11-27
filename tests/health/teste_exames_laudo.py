#!/usr/bin/env python3
"""Leitor de exames com um laudo FICTÍCIO no formato de colunas de laboratório grande: valor e referência na mesma linha, nome na linha de baixo,
leucograma com % e valor absoluto, blocos de histórico, tabelas de referência (jejum, risco, idade e sexo), notas, rodapés e repetições.
Nenhum dado real: nomes, datas e valores abaixo são inventados."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="heimdall-laudo-"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "banco"), "STUDIO_EXAMES_DIR": str(TMP / "health"), "STUDIO_EXAMES_LLM": "0"})
import studio_banco as banco  # noqa: E402
import studio_exames as ex  # noqa: E402

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


LAUDO = """
                                                  Atendimento ao cliente            Atendimento ao médico
                                                  Cidade Modelo 11 0000 0000

Fulano de Tal Modelo                                              CPF: 000.000.000-00                                       FAP: 000000000000
Gênero: Masculino                                                 DN: 10/03/1986 | 40 anos e 8 meses
Solicitante: Dr(a) Beltrano Exemplo                               RG: 000000000

 DATA COLETA/RECEBIMENTO: 20/11/2026 07:27

   Hemograma com Contagem de Plaquetas

   Série Vermelha                                                    RESULTADO                                        INTERVALO DE REFERÊNCIA

   Eritrócitos                                                 5,10 10^6/µL                                                               4,50 a 5,50 10^6/µL
   Hemoglobina                                                 15,0 g/dL                                                                      13,0 a 17,0 g/dL
                                                                                                                                              (Material:Sangue Total)

   Série Branca                                                      RESULTADO                                        INTERVALO DE REFERÊNCIA

   Leucócitos                                   100 %                  8.000 /µL                                          100 %               4.000 a 10.000 /µL
   Neutrófilos                                  50,0 %                 4.000 /µL                                          40,0 a 80,0 %       1.800 a 7.800 /µL
   Linfócitos                                   45,0 %                 3.600 /µL                                          20,0 a 40,0 %       1.000 a 3.000 /µL
   Contagem de Plaquetas                                       300.000 /µL                                                150.000 a 450.000 /µL
   VPM                                                         9,0 fL                                                    8,3 a 12,5 fL
   Fontes:
   Fulano, J., 2003. Hematologia clinica. 11th ed. Cidade: Editora Modelo.
   (Material:Sangue Total)

                                                                             R E S U LTA D O                             I N T E R VA L O D E R E F E R Ê N C I A

                                                                            100,0 ng/mL                                                               20,0 a 300,0 ng/mL
   Ferritina

   Material: Soro
   Método: Quimioluminescência

   Metabolismo do Ferro
   RESULTADO | INTERVALO DE REFERÊNCIA
   Ferro                                                       120 µg/dL                                                        33 a 193 µg/dL
   Capacidade de Fixação Latente do Ferro                      150 µg/dL                                                        125 a 345 µg/dL
   Capacidade Total de Fixação do Ferro                        270 µg/dL                                                        de 250 até 450 µg/dL
   Nota: Os valores de referência são padronizados para amostras colhidas até às
   11:00h devido às variações do ciclo circadiano. Resultado de 12 mg/dL não é este exame.

                                                                       R E S U LTA D O                         I N T E R VA L O D E R E F E R Ê N C I A

                                                                        490 pg/mL                                                              223 a 672 pg/mL
   Vitamina B-12, Dosagem
   Material: Soro

   RESULTADO | INTERVALO DE REFERÊNCIA
   Ureia                                                       25 mg/dL                                                         17 a 48 mg/dL
   Histórico Uréia

     Data                                     15/07/2021 07:14                                          20/11/2026 07:27
     Resultado                                30 mg/dL                                                  25 mg/dL
   Nota:
   Intervalo de referência da ureia verificado na população atendida pelo laboratório.
   RESULTADO | INTERVALO DE REFERÊNCIA
   *eGFR                                                       85 mL/min/1,73m²                                                 Superior a 90 mL/min/1,73m²

   RESULTADO | INTERVALO DE REFERÊNCIA
   25-Hidroxivitamina D (Vitamina D)                           22 ng/mL                                                         CONFIRA NA TABELA ABAIXO
   (Material:Soro)
   População saudável abaixo de 60 anos: Superior a 20 ng/mL
   População acima de 60 anos e grupos de risco*: 30 a 60 ng/mL
   Histórico 25-Hidroxivitamina D (Vitamina D)
     Data                                     15/07/2021 07:14        22/08/2024 07:56        20/11/2026 07:27
     Resultado                                12 ng/mL                13 ng/mL                22 ng/mL
   Nota:
   *Grupos de risco: gestantes, osteoporose e outros.

   Perfil Lipídico
   RESULTADO | INTERVALO DE REFERÊNCIA
   Triglicérides                                               160 mg/dL                                                        (Vide Intervalo de Referência Abaixo)
   (Material:Soro)
   Tabela de Referência - Triglicérides
   Com jejum: Inferior a 150 mg/dL
   Sem jejum: Inferior a 175 mg/dL
   Colesterol Total                                            170 mg/dL                                                        (Vide Intervalo de Referência Abaixo)
   Tabela de Referência - Colesterol Total
   Com jejum: Inferior a 190 mg/dL
   Sem jejum: Inferior a 190 mg/dL
   HDL - Colesterol                                            35 mg/dL                                                         (Vide Intervalo de Referência Abaixo)
   Tabela de Referência - HDL - Colesterol
   Com jejum: Superior a 40 mg/dL
   Sem jejum: Superior a 40 mg/dL
   Não HDL - Colesterol                                        135 mg/dL                                                        (Vide Intervalo de Referência Abaixo)
   Tabela de Referência - Não HDL - Colesterol
   Risco cardiovascular estimado e Meta de NÃO HDL a ser alcançada (com ou sem jejum):
   Extremo: Inferior a 70 mg/dL
   Muito Alto: Inferior a 80 mg/dL
   Alto: Inferior a 100 mg/dL
   Intermediário: Inferior a 130 mg/dL
   Baixo: Inferior a 145 mg/dL
   VLDL - Colesterol                                           24 mg/dL                                                         (Vide Intervalo de Referência Abaixo)
   Tabela de Referência - VLDL - Colesterol
   Não apresenta intervalo de referência definido.
   Notas:
   Resultados de triglicérides, em 3 coletas diferentes, superiores a 1.000 mg/dL em adultos, sugerem investigação.
   Quando os níveis de triglicérides estiverem acima de 440 mg/dL, sugere-se nova coleta.
   Os valores de Colesterol Total = 310 mg/dL em adultos podem ser indicativos de hipercolesterolemia.
   Referências:
   1. Autor A, Autor B. Comparação de métodos. JAMA. 2013;310(19):2061-8.

   RESULTADO | INTERVALO DE REFERÊNCIA
   Transaminase oxalacética - TGO                              25 U/L                                                           Inferior ou igual a 40 U/L
   (Aspartato amino transferase)
   (Material:Soro)
   RESULTADO | INTERVALO DE REFERÊNCIA
   Calcio Ionizado                                             1,20 mmol/L                                                      1,05 a 1,30 mmol/L
   RESULTADO | INTERVALO DE REFERÊNCIA
   Hormônio Tireoestimulante                                   2,50 µUI/mL                                                      0,40 a 4,30 µUI/mL
   Ultrassensível (TSH)
   (Material:Soro)
   RESULTADO | INTERVALO DE REFERÊNCIA
   Testosterona Total                                          600,00 ng/dL                                                     (Vide Intervalo de Referência Abaixo)
   Tabela de Referência - Testosterona Total
   Sexo Masculino:
   16 a 21 anos: 118,22 a 948,56 ng/dL
   22 a 49 anos: 164,94 a 753,38 ng/dL
   Superior ou igual a 50 anos: 86,49 a 788,22 ng/dL
   Sexo Feminino:
   16 a 21 anos: 17,55 a 50,41 ng/dL
   Pré Menopausa: 12,09 a 59,46 ng/dL
   Testosterona Livre e Biodisponível Calculadas
   RESULTADO | INTERVALO DE REFERÊNCIA
   Testosterona Total                                          600,00 ng/dL                                                     (Vide Intervalo de Referência Abaixo)
   Tabela de Referência - Testosterona Total
   Sexo Masculino:
   22 a 49 anos: 164,94 a 753,38 ng/dL
   Sexo Feminino:
   Pré Menopausa: 12,09 a 59,46 ng/dL
   SHBG (Globulina Transportadora de                           36,0 nmol/L                                                      10,0 a 57,0 nmol/L
   Hormônios Sexuais)
   Testosterona Livre Calculada                                12,00 ng/dL                                                      (Vide Intervalo de Referência Abaixo)
   Tabela de Referência - Testosterona Livre Calculada
   Abaixo de 17 anos: Sem valor de referência definido.
   17 a 40 anos: 3,40 a 24,60 ng/dL
   41 a 60 anos: 2,67 a 18,30 ng/dL
   Comentários:
   I. O cálculo fornece uma estimativa.
   * valor padrão de albumina = 4,3 g/dL (1).
   Observação: ng/dL x 10(dez) = pg/mL.

   Antígeno Prostático Específico Total
   R E S U LTA D O | I N T E R VA L O D E R E F E R Ê N C I A
                                                                                                                                            Inferior a 4,00 ng/mL
   PSA Total                                                         1,00 ng/mL
   (Material:Soro)
   Notas:
   Alguns autores sugerem um ponto de corte mais baixo de 2,5 ou 3,0 ng/mL, e outros recomendam outra faixa.
   Antígeno Prostático Específico Livre
   R E S U LTA D O | I N T E R VA L O D E R E F E R Ê N C I A
   PSA Livre                                                   0,20 ng/mL                                                       Vide Notas
   Notas:
   Não há intervalos de referência estabelecidos na literatura para PSA Livre.
   Local de Execução do(s) exame(s):
   - LAB MODELO - Avenida Exemplo, 434 CNES: 0000000 - Cidade, SP: Ureia, PSA Total, Ferritina, Prolactina, Magnésio, Vitamina B-12, Dosagem
"""

res, desc = ex.ler_resultados_regra(LAUDO)
por = {r["chave"]: r for r in res}
chaves = [r["chave"] for r in res]

# ----- o que tem de entrar, e só isso
esperadas = ["hemacias", "hemoglobina", "leucocitos", "neutrofilos", "neutrofilos_abs", "linfocitos", "linfocitos_abs", "plaquetas", "vpm", "ferritina",
             "ferro_serico", "clf", "ctlf", "vitamina_b12", "ureia", "tfg", "vitamina_d", "triglicerideos", "colesterol_total", "hdl", "nao_hdl", "vldl",
             "tgo", "calcio_ionico", "tsh", "testosterona_total", "shbg", "testosterona_livre", "psa_total", "psa_livre"]
confere("lê exatamente os exames do laudo", sorted(chaves) == sorted(esperadas), (set(chaves) ^ set(esperadas)))
confere("nada é descartado", desc == [], desc)
confere("nenhuma linha de nota, tabela ou rodapé vira exame", all(r["catalogado"] for r in res), [r["chave"] for r in res if not r["catalogado"]])
confere("testosterona total repetida no laudo entra uma vez só", chaves.count("testosterona_total") == 1)

# ----- unidades, nomes na linha de baixo, nomes que contêm 'idade'
confere("unidade 10^6/µL", por["hemacias"]["unidade"] == "10^6/µL" and por["hemacias"]["valor"] == 5.1 and por["hemacias"]["sinal"] == "dentro", por["hemacias"])
confere("nome na linha de baixo: ferritina", por["ferritina"]["valor"] == 100 and por["ferritina"]["unidade"] == "ng/mL" and por["ferritina"]["sinal"] == "dentro")
confere("nome na linha de baixo: vitamina B12", por["vitamina_b12"]["valor"] == 490 and por["vitamina_b12"]["unidade"] == "pg/mL")
confere("'Capacidade ... do ferro' não é barrada por conter 'idade'", por["clf"]["valor"] == 150 and por["ctlf"]["valor"] == 270)
confere("referência 'de 250 até 450'", por["ctlf"]["ref_min"] == 250 and por["ctlf"]["ref_max"] == 450 and por["ctlf"]["sinal"] == "dentro")
confere("cálcio ionizado não é cálcio total", por["calcio_ionico"]["valor"] == 1.2 and por["calcio_ionico"]["sinal"] == "dentro")
confere("nome com 25- no começo", por["vitamina_d"]["valor"] == 22)
confere("nome em duas linhas: SHBG", por["shbg"]["valor"] == 36 and por["shbg"]["sinal"] == "dentro")
confere("'Inferior ou igual a 40'", por["tgo"]["ref_max"] == 40 and por["tgo"]["sinal"] == "dentro")
confere("eGFR 85 abaixo de 'Superior a 90'", por["tfg"]["ref_min"] == 90 and por["tfg"]["sinal"] == "abaixo")

# ----- referência na linha de cima (PSA) e sem faixa
confere("PSA total: referência vem na linha de cima", por["psa_total"]["ref_max"] == 4 and por["psa_total"]["sinal"] == "dentro", por["psa_total"])
confere("PSA livre: 'Vide Notas' não vira faixa nem sinal", por["psa_livre"]["sinal"] == "" and por["psa_livre"]["ref_min"] is None and por["psa_livre"]["ref_max"] is None)

# ----- leucograma: percentual e absoluto separados
confere("leucócitos totais em /µL (a coluna de 100 % não é o resultado)", por["leucocitos"]["valor"] == 8000 and por["leucocitos"]["unidade"] == "/µL")
confere("neutrófilos em % e absoluto", por["neutrofilos"]["valor"] == 50 and por["neutrofilos"]["unidade"] == "%" and por["neutrofilos_abs"]["valor"] == 4000
        and por["neutrofilos_abs"]["unidade"] == "/µL" and por["neutrofilos"]["sinal"] == "dentro" and por["neutrofilos_abs"]["sinal"] == "dentro")
confere("linfócitos acima nas duas colunas", por["linfocitos"]["sinal"] == "acima" and por["linfocitos_abs"]["sinal"] == "acima"
        and por["linfocitos"]["ref_max"] == 40 and por["linfocitos_abs"]["ref_max"] == 3000)

# ----- tabelas de referência
confere("triglicerídeos: com e sem jejum diferentes, sinal só quando as duas concordam",
        por["triglicerideos"]["valor"] == 160 and por["triglicerideos"]["sinal"] == "" and "com jejum" in por["triglicerideos"]["ref_texto"]
        and "sem jejum" in por["triglicerideos"]["ref_texto"], por["triglicerideos"])
confere("colesterol total: faixas iguais viram uma só", por["colesterol_total"]["ref_max"] == 190 and por["colesterol_total"]["sinal"] == "dentro", por["colesterol_total"])
confere("HDL 35 abaixo de 'Superior a 40'", por["hdl"]["ref_min"] == 40 and por["hdl"]["sinal"] == "abaixo", por["hdl"])
confere("não HDL: meta por risco, sem sinal", por["nao_hdl"]["sinal"] == "" and "risco" in por["nao_hdl"]["ref_texto"].lower() and "130" in por["nao_hdl"]["ref_texto"]
        and "extremo" in por["nao_hdl"]["ref_texto"], por["nao_hdl"])
confere("VLDL sem intervalo definido: sem sinal", por["vldl"]["sinal"] == "" and por["vldl"]["ref_min"] is None)
confere("vitamina D: população saudável <60 anos, com ressalva dos grupos de risco",
        por["vitamina_d"]["ref_min"] == 20 and por["vitamina_d"]["sinal"] == "dentro" and "grupos de risco" in por["vitamina_d"]["ref_texto"], por["vitamina_d"])
confere("testosterona total: faixa de homem de 22 a 49 anos (idade vem do cabeçalho)", por["testosterona_total"]["ref_min"] == 164.94
        and por["testosterona_total"]["ref_max"] == 753.38 and por["testosterona_total"]["sinal"] == "dentro", por["testosterona_total"])
confere("testosterona livre: faixa de 17 a 40 anos", por["testosterona_livre"]["ref_min"] == 3.4 and por["testosterona_livre"]["ref_max"] == 24.6, por["testosterona_livre"])

# ----- histórico
confere("histórico da ureia: só o valor antigo, o atual não se repete", [(h["dia"], h["valor"]) for h in por["ureia"].get("historico", [])] == [("2021-07-15", 30.0)], por["ureia"].get("historico"))
confere("histórico da vitamina D: dois valores antigos com data", [(h["dia"], h["valor"]) for h in por["vitamina_d"].get("historico", [])] == [("2021-07-15", 12.0), ("2024-08-22", 13.0)])

# ----- sexo e idade mudam a faixa escolhida
fem = LAUDO.replace("Gênero: Masculino", "Gênero: Feminino")
rf = {r["chave"]: r for r in ex.ler_resultados_regra(fem)[0]}
confere("sexo feminino: não usa a faixa masculina", rf["testosterona_total"]["ref_min"] != 164.94, rf["testosterona_total"])
velho = LAUDO.replace("DN: 10/03/1986", "DN: 10/03/1960")
rv = {r["chave"]: r for r in ex.ler_resultados_regra(velho)[0]}
confere("idade de 66 anos: faixa de 50 anos ou mais e grupos de risco da vitamina D", rv["testosterona_total"]["ref_min"] == 86.49 and "30 a 60" in rv["vitamina_d"]["ref_texto"], (rv["testosterona_total"], rv["vitamina_d"]))
sem_cab = "\n".join(l for l in LAUDO.splitlines() if "Gênero" not in l and "DN:" not in l)
rs = {r["chave"]: r for r in ex.ler_resultados_regra(sem_cab)[0]}
confere("sem sexo e idade no laudo: não chuta a faixa", rs["testosterona_total"]["sinal"] == "" and rs["testosterona_total"]["ref_min"] is None, rs["testosterona_total"])

# ----- do arquivo ao banco: o histórico entra com a data própria e sem repetir dia
ex.texto_do_arquivo = lambda dados, nome: (LAUDO, False)
r1 = ex.registrar(b"%PDF-1.4 laudo ficticio", "laudo.pdf")
confere("registra como exame com a data da coleta", r1["tipo"] == "exame" and r1["dia"] == "2026-11-20" and r1["itens"] == len(esperadas), r1)
txt = ex.resumo_documento(r1["id"])
confere("resumo mostra os valores anteriores do laudo", "valores anteriores no laudo" in txt and "15/07/2021 30" in txt)
ex.confirmar(r1["id"])
ur = sql("SELECT dia, valor, fonte FROM exames_resultados WHERE chave = 'ureia' ORDER BY dia")
confere("ureia: valor antigo guardado com fonte 'historico' e o atual normal", [(x["dia"], x["valor"], x["fonte"]) for x in ur] == [("2021-07-15", 30.0, "historico"), ("2026-11-20", 25.0, "regra")], ur)
vd = sql("SELECT dia FROM exames_resultados WHERE chave = 'vitamina_d' ORDER BY dia")
confere("vitamina D: três datas", [x["dia"] for x in vd] == ["2021-07-15", "2024-08-22", "2026-11-20"], vd)
rel = ex.relatorio_exame("ureia")
confere("relatório do exame mostra o histórico em ordem", rel.index("15/07/2021") < rel.index("20/11/2026"), rel)
# Um segundo laudo do mesmo dia antigo não duplica o dia que já veio do histórico
LAUDO2 = (LAUDO.replace("20/11/2026", "21/11/2026").replace("Ureia                                                       25 mg/dL", "Ureia                                                       26 mg/dL")
          .replace("30 mg/dL                                                  25 mg/dL", "30 mg/dL                                                  26 mg/dL"))
ex.texto_do_arquivo = lambda dados, nome: (LAUDO2, False)
r2 = ex.registrar(b"%PDF-1.4 laudo ficticio 2", "laudo2.pdf")
ex.confirmar(r2["id"])
ur2 = sql("SELECT dia FROM exames_resultados WHERE chave = 'ureia' ORDER BY dia")
confere("histórico repetido em outro laudo não duplica o dia", [x["dia"] for x in ur2] == ["2021-07-15", "2026-11-20", "2026-11-21"], ur2)

# Laudo antigo, com menos exames, enviado depois do novo: substitui o valor que só veio do histórico, sem duplicar o dia
ANTIGO = """
Gênero: Masculino                                                 DN: 10/03/1986 | 35 anos
 DATA COLETA/RECEBIMENTO: 15/07/2021 07:14
   RESULTADO | INTERVALO DE REFERÊNCIA
   Ureia                                                       30 mg/dL                                                         17 a 48 mg/dL
   Glicose                                                     86 mg/dL                                                         70 a 99 mg/dL
"""
ex.texto_do_arquivo = lambda dados, nome: (ANTIGO, False)
r3 = ex.registrar(b"%PDF-1.4 laudo antigo", "antigo.pdf")
ex.confirmar(r3["id"])
u3 = sql("SELECT dia, fonte, ref_texto, sinal FROM exames_resultados WHERE chave = 'ureia' AND dia = '2021-07-15'")
confere("laudo antigo: o dia do histórico não fica duplicado e ganha referência e sinal", len(u3) == 1 and u3[0]["fonte"] == "regra" and u3[0]["sinal"] == "dentro", u3)
g3 = sql("SELECT dia, fonte FROM exames_resultados WHERE chave = 'glicemia_jejum' ORDER BY dia")
confere("laudo antigo: exame que o laudo novo não trazia entra normalmente", [x["dia"] for x in g3] == ["2021-07-15"], g3)
t3 = sql("SELECT COUNT(*) n FROM exames_resultados WHERE chave = 'tsh'")[0]["n"]
confere("laudo antigo com menos exames não apaga nem altera o que ele não traz", t3 == 2 and sql("SELECT COUNT(*) n FROM exames_resultados WHERE chave = 'vitamina_d'")[0]["n"] == 4)

print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)
