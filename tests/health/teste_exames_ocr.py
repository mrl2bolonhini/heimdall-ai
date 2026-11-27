#!/usr/bin/env python3
"""Leitor de exames: ligaduras do PDF (ﬁ), leucograma e proteinograma com absoluto, metas por risco, urina, VHS, mU/L e texto de OCR com vírgula perdida.
Texto FICTÍCIO."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="heimdall-ocr-"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "banco"), "STUDIO_EXAMES_DIR": str(TMP / "health"), "STUDIO_EXAMES_LLM": "0"})
import studio_exames as ex  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


def por(r):
    return {x["chave"]: x for x in r}


TEXTO = """Laboratório Modelo
                                       RESULTADO                    INTERVALO DE REFERÊNCIA
 Eritrócitos                          5,12 10^6/µ L                   4,50 a 5,90 10^6/µ L
 Neutróﬁlos                           57,3 %                  4.779 /µL                           45,5 a 73,5 %         1.600 a 7.700 /µL
 Leucócitos                           100 %                   8.340 /µL                           100 %         4.500 a 11.000 /µL
 Hemossedimentação (VHS) 1ª                                          12 mm                          Inferior a 15 mm
 hora
 Insulina                                                           4,0 mU/L                        De 3,0 a 25,0 mU/L
 Proteínas Totais                     100 %                   6,8 g/dL                              100 %                 6,4 a 8,3 g/dL
 Albumina                             59,9 %                  4,07 g/dL                             55,8 a 66,1 %         4,01 - 4,78 g/dL
 Alfa1 Globulina                      5,1 %                   0,35 g/dL                             2,9 a 4,9 %           0,22 - 0,41 g/dL
 Glicose Média Estimada (GME)                                       113 mg/dL
 Meta lipídica de acordo com o risco cardiovascular estimado pelo médico solicitante
 LDL-C                        Baixo                                                                            <130                           <130
 Não-HDL-C                                          Baixo                                                                     <160                    <160
 Bibliograﬁa: Intervalos de Referência da Vitamina D- 25(OH)D. Posicionamento Oﬁcial da Sociedade Brasileira
 Urina Tipo I
 Leucócitos.                                                          8.000 /mL                                                                            Inferior a 10.000 /mL
 Liberado por: Fulano - CRBM-SP 1
"""
r, d = ex.ler_resultados_regra(TEXTO)
m = por(r)
confere("ligadura ﬁ: neutrófilos em % e absoluto", "neutrofilos" in m and "neutrofilos_abs" in m and m["neutrofilos_abs"]["unidade"] == "/µL", list(m))
confere("unidade '10^6/µ L' vira 10^6/µL", m["hemacias"]["unidade"] == "10^6/µL", m["hemacias"]["unidade"])
confere("leucócitos totais: só o absoluto", m["leucocitos"]["valor_texto"] == "8.340", m["leucocitos"])
confere("VHS 1ª hora: o 1 não é o resultado", m["vhs"]["valor_texto"] == "12" and m["vhs"]["unidade"] == "mm", m["vhs"])
confere("insulina em mU/L lida com unidade", m["insulina"]["unidade"] == "mU/L" and m["insulina"]["sinal"] == "dentro", m["insulina"])
confere("proteinograma: albumina em g/dL e fração com nome que tem número", m["albumina"]["unidade"] == "g/dL" and "alfa1_globulina" in m and "alfa1_globulina_absolutos" in m, list(m))
confere("glicose média estimada não vira glicemia", "glicose_media_estimada" in m and m["glicemia_jejum"]["valor_texto"] != "113" if "glicemia_jejum" in m else "glicose_media_estimada" in m)
confere("tabela de metas por risco não vira LDL nem não HDL", "ldl" not in m and "nao_hdl" not in m, list(m))
confere("bibliografia não vira vitamina D", "vitamina_d" not in m, list(m))
confere("urina não se mistura com o sangue", m["urina_leucocitos"]["valor_texto"] == "8.000" and m["leucocitos"]["valor_texto"] == "8.340", (m.get("urina_leucocitos"), m["leucocitos"]))

# ----- OCR: vírgula perdida e referência ilegível
OCR = """Laboratório Modelo
                                       RESULTADO                    INTERVALO DE REFERÊNCIA
 Proteínas Totais                     100 %                   6,8 g/dL                              100 %                 6,4 a 8,3 g/dL
 Gama Globulina 127% O 0,86g/dL |] 11,13 18,8% 0,72 a 1,27 g/dL |]
 Beta2 Globulina 47% O 0,32g/dL |] 3126,1% 0,22 a 0,45 g/dL |]
 Leucócitos                           100 %                   8.340 /µL                                  100 %         4.500 a 11.000 /µL
 Neutróﬁlos 57,3 % O 4.779 /yL 45,52 73,5% 1.600 a 7.700 /uL
 Pulso 12 mm Hg  ERAM
"""
x = ex.extrair(OCR, True)
mo = por(x["resultados"])
confere("OCR: percentual acima de 100 % é descartado", any("Gama" in dd["texto"] for dd in x["descartados"]), x["descartados"])
confere("OCR: 47 % não bate com 0,32 g/dL: sem sinal e com aviso", mo["beta2_globulina"]["sinal"] == "" and any("Beta2" in a and "4,7" in a for a in x["avisos"]), x["avisos"])
confere("OCR: o valor lido nunca é trocado", mo["beta2_globulina"]["valor_texto"] == "47")
confere("OCR: marcas '|]' e 'O' saem e o µ lido como 'y' volta", mo["neutrofilos_abs"]["unidade"] == "/µL" and mo["neutrofilos_abs"]["sinal"] == "dentro", mo["neutrofilos_abs"])
confere("OCR: faixa do percentual ilegível fica sem sinal", mo["neutrofilos"]["sinal"] == "", mo["neutrofilos"])
confere("sem OCR, o aviso de vírgula não aparece", not any("reconhecimento" in a and "Beta2" in a for a in ex.extrair(OCR, False)["avisos"]))

print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
sys_exit = 1 if falhas else 0
raise SystemExit(sys_exit)
