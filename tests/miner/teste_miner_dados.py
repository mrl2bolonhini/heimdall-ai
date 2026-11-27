#!/usr/bin/env python3
"""Testa os dados do Studio Miner: pendentes por área, aceite com evento ou lembrete, falha do agente, adiar, ignorar, boleto, golpe e área inicial."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="miner_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
import studio_banco as banco  # noqa: E402
import studio_miner_dados as d  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


def semear(id_, fonte, titulo, resumo="", nivel="medio"):
    banco.iniciar() if not banco.caminho().exists() else None
    with banco._trava:
        con = banco.conectar()
        con.execute("INSERT OR IGNORE INTO triagem (id, criado, fonte, nivel, titulo, resumo, estado, lembrete, atualizado) VALUES (?, '2026-11-20T12:00:00Z', ?, ?, ?, ?, 'avisado', 0, '2026-11-20T12:00:00Z')",
                    (id_, fonte, nivel, titulo, resumo))
        con.commit()
        con.close()


semear("a1", "email", "Comunicado do banco sobre boleto", "Prazo: " + (date.today() + timedelta(days=10)).strftime("%d/%m/%Y"), "alto")
semear("a2", "email", "Possível golpe: mensagem suspeita", "Não clique no link.")
semear("a3", "justica", "Publicação no tribunal", "Movimentação nova.")
semear("a4", "privacidade", "Menção ao nome", "Encontrada numa página pública.")
confere("áreas fixas, na ordem", list(d.AREAS) == ["identidade", "cidadania", "patrimonio", "carreira", "rotina"])
confere("pendentes de Rotina: só e-mail", {i["id"] for i in d.pendentes("rotina")} == {"a1", "a2"})
confere("pendentes de Cidadania e de Identidade", [i["id"] for i in d.pendentes("cidadania")] == ["a3"] and [i["id"] for i in d.pendentes("identidade")] == ["a4"])
confere("áreas sem fonte ficam vazias", d.pendentes("patrimonio") == [] and d.pendentes("carreira") == [])
confere("nível mais alto primeiro", d.pendentes("rotina")[0]["id"] == "a1")
try:
    d.pendentes("x"); desconhecida = False
except d.ErroMiner:
    desconhecida = True
confere("área desconhecida: erro", desconhecida)
confere("boleto identificado só onde o termo aparece", d.e_boleto(d.obter("a1")) and not d.e_boleto(d.obter("a3")))
confere("golpe não cria agenda; comunicado cria", not d.cria_agenda(d.obter("a2")) and d.cria_agenda(d.obter("a1")) and d.cria_agenda(d.obter("a3")))

envios = []
msg = d.aceitar("a1", lambda tipo, dado: (envios.append((tipo, dado)) or (True, "ok")))
confere("aceite com prazo cria evento por prazo_oficial", envios[0][0] == "prazo_oficial" and envios[0][1]["titulo"] == "Conferir comunicado oficial" and "evento" in msg, envios)
confere("título da agenda sem dados do conteúdo", "boleto" not in envios[0][1]["titulo"].lower())
confere("item aceito sai dos pendentes", "a1" not in {i["id"] for i in d.pendentes("rotina")})
envios.clear()
d.aceitar("a3", lambda tipo, dado: (envios.append((tipo, dado)) or (True, "ok")))
confere("aceite sem prazo cria lembrete pendencia_miner", envios[0][0] == "pendencia_miner" and "vencimento" in envios[0][1], envios)
semear("a5", "email", "Outro comunicado", "Sem prazo.")
try:
    d.aceitar("a5", lambda tipo, dado: (False, "agente fora"))
    falhou = False
except d.ErroMiner:
    falhou = True
confere("agente falha: erro e o item continua pendente", falhou and "a5" in {i["id"] for i in d.pendentes("rotina")})
envios.clear()
d.aceitar("a2", lambda tipo, dado: envios.append(1))
confere("aceitar golpe não chama a agenda", envios == [] and "a2" not in {i["id"] for i in d.pendentes("rotina")})
d.adiar("a4")
confere("adiado some dos pendentes", d.pendentes("identidade") == [])
d.ignorar("a5")
confere("ignorado some dos pendentes", "a5" not in {i["id"] for i in d.pendentes("rotina")})
confere("histórico mostra decididos", {"a1", "a2", "a5"} <= {i["id"] for i in d.historico(d.AREAS["rotina"][1])})
confere("área inicial padrão é Identidade", d.area_inicial() == "identidade")
d.definir_area_inicial("cidadania")
confere("área inicial gravada", d.area_inicial() == "cidadania")
try:
    d.definir_area_inicial("nada"); ruim = False
except d.ErroMiner:
    ruim = True
confere("área inicial inválida recusada", ruim)
try:
    d.obter("nao-existe"); inexistente = False
except d.ErroMiner:
    inexistente = True
confere("item inexistente: erro", inexistente)
for fn in (d.aceitar, d.adiar, d.ignorar):
    try:
        fn("a1"); repetido = False
    except d.ErroMiner:
        repetido = True
    confere(f"{fn.__name__} em item já decidido: recusado", repetido)
print(f"\n{falhas} falha(s)")
sys_exit = _sys.exit
sys_exit(1 if falhas else 0)
