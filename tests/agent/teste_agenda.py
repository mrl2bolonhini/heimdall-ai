#!/usr/bin/env python3
"""Testa a regra evento x lembrete e o envio de consulta e renovação de receita ao Calendário, sem agente real."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ["STUDIO_DB_DIR"] = tempfile.mkdtemp()
os.environ["STUDIO_EXAMES_DIR"] = tempfile.mkdtemp()
os.environ["STUDIO_EXAMES_LLM"] = "0"
os.environ["STUDIO_AGENTE_URL"] = "http://127.0.0.1:9"  # nunca o agente real: o teste criaria eventos no Calendário
sys.path.insert(0, str(RAIZ))
import studio_agenda as ag  # noqa: E402
import studio_banco as banco  # noqa: E402
import studio_exames as ex  # noqa: E402

banco.iniciar()
falhas = 0


def pdf_com_texto(linhas: list) -> bytes:
    """PDF mínimo (Helvetica) com uma linha de texto por linha; serve para testar a leitura direta."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    cont = "BT /F1 10 Tf 40 800 Td 12 TL\n" + "\n".join(f"({esc(l)}) '" for l in linhas) + "\nET"
    cont_b = cont.encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(cont_b) + cont_b + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, pos = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        pos.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % p for p in pos)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def confere(nome, cond, extra=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"\n     {extra}"))
    falhas += 0 if cond else 1


# --- a regra
confere("consulta e renovação são eventos; triagem e verificar são lembretes",
        ag.destino("consulta") == "evento" and ag.destino("renovacao_receita") == "evento" and ag.destino("verificar_prazo") == "lembrete")
try:
    ag.destino("inventado")
    confere("tipo fora da tabela é barrado", False)
except KeyError:
    confere("tipo fora da tabela é barrado", True)
confere("todo destino é evento ou lembrete", all(d in ("evento", "lembrete") for d, _, _ in ag.DESTINOS.values()))
fonte = Path("studio_email_oficial.py").read_text(encoding="utf-8")
confere("e-mail oficial: prazo no Calendário e verificação no Lembretes, como na tabela",
        '"/calendario/evento", {"titulo": "Prazo: "' in fonte and '"/lembretes/criar", {"titulo": "Verificar: "' in fonte)

# --- consulta lida de um documento
hoje = date.today()
d1 = hoje + timedelta(days=20)
texto = f"""Clínica Coração Saudável
Confirmação de consulta
Paciente: Fulano de Tal
Consulta agendada para {d1.day:02d}/{d1.month:02d}/{d1.year} às 14h30
Dr. Carlos Souza CRM-SP 123456
Especialidade: cardiologia
Local: Rua das Flores, 100, sala 4
Chegar com 15 minutos de antecedência."""
r = ex.extrair(texto)
confere("documento de consulta é reconhecido", r["tipo"] == "consulta", r["tipo"])
c = (r["consultas"] or [{}])[0]
confere("data, hora, especialidade e local lidos do texto", c.get("dia") == d1.isoformat() and c.get("hora") == "14:30" and c.get("especialidade") and "Flores" in c.get("local", ""), c)

enviados = []


def falso_ok(url, dado, cab):
    enviados.append((url, dado))
    return {"ok": True, "evento": "criado"}


rr = ex.registrar(pdf_com_texto(texto.splitlines()), "consulta.pdf", "arquivo")
confere("registrada como pendente, nada no Calendário ainda", rr["tipo"] == "consulta" and not enviados, rr)
# o agente de verdade não existe aqui: o envio padrão falha, o item fica pendente e depois é refeito
sem_agente = ex.sincronizar_agenda(post=lambda *a: (_ for _ in ()).throw(ConnectionError("fora")))
confere("sem consultas confirmadas não há o que enviar", sem_agente["criados"] == 0 and sem_agente["pendentes"] == 0, sem_agente)

orig = ag.enviar
ag.enviar = lambda tipo, dado, post=None: orig(tipo, dado, falso_ok)
conf = ex.confirmar(rr["id"])
ag.enviar = orig
confere("ao confirmar, a consulta vai ao Calendário como evento com hora", conf["agenda"]["criados"] == 1 and enviados and enviados[0][0].endswith("/calendario/evento")
        and enviados[0][1]["hora"] == "14:30" and enviados[0][1]["data"] == d1.isoformat(), (conf, enviados))
confere("por padrão o evento traz especialidade, médico e local",
        "cardio" in enviados[0][1]["titulo"].lower() and "Carlos" in enviados[0][1]["titulo"] and "Flores" in enviados[0][1]["local"], enviados[0][1])
ag.enviar = lambda tipo, dado, post=None: orig(tipo, dado, falso_ok)
de_novo = ex.sincronizar_agenda()
confere("rodar de novo não duplica", de_novo["criados"] == 0 and de_novo["ja_feitos"] == 1 and len(enviados) == 1, de_novo)

# --- agente fora do ar: fica pendente e é refeito
ag.enviar = orig
r2 = ex.consulta_nova((hoje + timedelta(days=5)).isoformat(), "09:00", "Ana", "dermatologia", "")
confere("agente fora do ar: a consulta fica pendente, sem erro", r2["pendentes"] == 1 and r2["criados"] == 0, r2)
ag.enviar = lambda tipo, dado, post=None: orig(tipo, dado, falso_ok)
r3 = ex.sincronizar_agenda()
confere("depois de o agente voltar, o pendente é criado", r3["criados"] == 1, r3)

# --- renovação de receita
validade = hoje + timedelta(days=30)
banco.iniciar()
ex._escrever(lambda con: con.execute("INSERT INTO receitas (documento_id, dia, medicamento, dose, posologia, validade) VALUES (99, ?, 'Medicamento X', '10 mg', '1 por dia', ?)",
                                    (hoje.isoformat(), validade.isoformat())))
enviados.clear()
r4 = ex.sincronizar_agenda()
renov = [e for e in enviados if "renovação" in e[1]["titulo"]]
confere("receita com validade futura gera evento de renovação antes do vencimento",
        r4["criados"] == 1 and renov and renov[0][1]["data"] == (validade - timedelta(days=ex.RENOVACAO_DIAS)).isoformat() and "Medicamento X" in renov[0][1]["titulo"], (r4, enviados))
ex._escrever(lambda con: con.execute("INSERT INTO receitas (documento_id, dia, medicamento, dose, posologia, validade) VALUES (98, ?, 'Vencida', '', '', ?)",
                                    (hoje.isoformat(), (hoje - timedelta(days=3)).isoformat())))
enviados.clear()
r5 = ex.sincronizar_agenda()
confere("receita já vencida não gera evento", r5["criados"] == 0 and not enviados, r5)
confere("consulta passada não gera evento", all(e[1]["data"] >= hoje.isoformat() for e in enviados))
ag.enviar = orig

# --- modo genérico, para quem não quer detalhes na nuvem
ex.DETALHES_NA_AGENDA = False
gen = ex._eventos_pendentes(hoje)
confere("com STUDIO_AGENDA_DETALHES=0 o título é genérico e sem local",
        all("cardio" not in i["dado"]["titulo"].lower() and "Medicamento" not in i["dado"]["titulo"] and not i["dado"].get("local") for i in gen) and gen)
ex.DETALHES_NA_AGENDA = True

# --- validação do agente (sem rodar AppleScript)
import studio_agente as agente  # noqa: E402
agente.osascript = lambda script, *a, **k: "criado:" + "|".join(a)
agente._lock = __import__("threading").Lock()
v = agente.criar_evento({"titulo": "Consulta médica", "data": d1.isoformat(), "hora": "14:30", "duracao_min": 45, "alertas_min_antes": [60, 1440]})
confere("agente: evento com hora usa o script de horário", v["ok"] and "14|30|45" in v["evento"] and "3600,86400" in v["evento"], v)
v2 = agente.criar_evento({"titulo": "Prazo", "data": d1.isoformat()})
confere("agente: sem hora continua dia inteiro", v2["ok"] and "|14|30|" not in v2["evento"], v2)
try:
    agente.criar_evento({"titulo": "x", "data": d1.isoformat(), "hora": "25:99"})
    confere("agente: hora inválida é recusada", False)
except ValueError:
    confere("agente: hora inválida é recusada", True)

print("\nTUDO OK" if not falhas else f"\n{falhas} falha(s)")
sys.exit(1 if falhas else 0)
