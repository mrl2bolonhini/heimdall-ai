#!/usr/bin/env python3
"""Dados do Studio Miner: as pendências de cada área da vida e as decisões do usuário (aceitar, adiar, ignorar).

Fonte: a tabela `triagem` do banco de cada pessoa (studio_banco), onde `studio_alertas.publicar` registra cada alerta uma única vez, com a fonte de origem
(email, justica, diarios, privacidade). O Miner só lê essas linhas e muda o estado delas por decisão do usuário; nada vira lembrete ou evento sem o aceite
(regra de studio_agenda.py). Áreas e abas: guides/miner_plano.txt.

Estados da linha: avisado e pendente (aguardam decisão), concluida (aceito) e descartada (ignorado); `adiado_ate` esconde o item até a data.
Usa só a biblioteca padrão do Python.
"""
import re
from datetime import date, datetime, timedelta, timezone

import studio_agenda as agenda
import studio_banco as banco

# slug da área (e da rota) -> (nome na aba, fontes de alerta que alimentam a área)
AREAS = {
    "identidade": ("Identidade", ["privacidade"]),
    "cidadania": ("Cidadania", ["justica", "diarios"]),
    "patrimonio": ("Patrimônio", []),
    "carreira": ("Carreira", []),
    "rotina": ("Rotina", ["email"]),
}
FONTE_ROTULO = {"privacidade": "Privacidade", "justica": "Justiça", "diarios": "Diário Oficial", "email": "E-mail oficial"}
FONTE_AREA = {f: a for a, (_, fontes) in AREAS.items() for f in fontes}
NIVEL_ROTULO = {"critico": "crítico", "alto": "alto", "medio": "médio"}
AREA_INICIAL_PADRAO = "identidade"
ENCERRADOS = ("concluida", "descartada")
# fonte -> título do lembrete ou evento: só a ação, sem dados do conteúdo (regra do studio_agenda.py)
ACAO_AGENDA = {"email": "Conferir comunicado oficial", "justica": "Conferir publicação oficial", "diarios": "Conferir publicação oficial"}
_PRAZO = re.compile(r"Prazo:\s*(\d{2})/(\d{2})/(\d{4})")
_BOLETO = re.compile(r"\bboletos?\b", re.IGNORECASE)


class ErroMiner(ValueError):
    """Pedido inválido ou ação que não pôde ser feita."""


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _con(somente_leitura: bool = False):
    if not banco.caminho().exists():
        banco.iniciar()
    con = banco.conectar(somente_leitura=False)
    con.execute("CREATE TABLE IF NOT EXISTS miner_config (chave TEXT PRIMARY KEY, valor TEXT NOT NULL DEFAULT '')")
    return con


def _fontes(area: str) -> list:
    if area not in AREAS:
        raise ErroMiner("Área desconhecida.")
    return AREAS[area][1]


def _consulta(fontes: list, so_pendentes: bool, limite: int) -> list:
    if not fontes:
        return []
    marcas = ",".join("?" for _ in fontes)
    sql = f"SELECT id, criado, fonte, nivel, titulo, resumo, estado, adiado_ate, decidido_em FROM triagem WHERE fonte IN ({marcas})"
    args = list(fontes)
    if so_pendentes:
        sql += " AND estado NOT IN ('concluida','descartada') AND (adiado_ate = '' OR adiado_ate <= ?)"
        args.append(_agora())
    sql += " ORDER BY CASE nivel WHEN 'critico' THEN 0 WHEN 'alto' THEN 1 ELSE 2 END, criado DESC LIMIT ?" if so_pendentes else " ORDER BY criado DESC LIMIT ?"
    args.append(int(limite))
    with banco._trava:
        con = _con()
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()


def pendentes(area: str, limite: int = 100) -> list:
    """Itens da área que aguardam decisão, do mais grave ao mais leve e, dentro do nível, do mais novo ao mais antigo."""
    return _consulta(_fontes(area), True, limite)


def historico(fontes: list, limite: int = 100) -> list:
    """Todos os itens das fontes, inclusive os já decididos, do mais novo ao mais antigo."""
    return _consulta(list(fontes), False, limite)


def total_pendentes(area: str) -> int:
    return len(pendentes(area, 500))


def obter(id_: str) -> dict:
    with banco._trava:
        con = _con()
        try:
            r = con.execute("SELECT id, criado, fonte, nivel, titulo, resumo, estado, adiado_ate, decidido_em FROM triagem WHERE id = ?", (str(id_),)).fetchone()
        finally:
            con.close()
    if not r or r["fonte"] not in FONTE_AREA:
        raise ErroMiner("Não encontrei este item.")
    return dict(r)


def situacao(it: dict) -> str:
    if it["estado"] == "concluida":
        return "Aceito"
    if it["estado"] == "descartada":
        return "Ignorado"
    if it["adiado_ate"] and it["adiado_ate"] > _agora():
        return "Adiado até " + data_local(it["adiado_ate"], so_data=True)
    return "Pendente"


def data_local(iso: str, so_data: bool = False) -> str:
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return iso or ""
    return d.strftime("%d/%m/%Y" if so_data else "%d/%m/%Y %H:%M")


def e_boleto(it: dict) -> bool:
    """O termo "boleto" aparece no título ou no resumo: o Miner só identifica; quem cuida do boleto é o Studio Finance."""
    return bool(_BOLETO.search((it.get("titulo") or "") + " " + (it.get("resumo") or "")))


def e_golpe(it: dict) -> bool:
    return (it.get("titulo") or "").lower().startswith("possível golpe")


def cria_agenda(it: dict) -> bool:
    """O aceite deste item cria lembrete ou evento? Só comunicados e publicações oficiais; suspeita de golpe e menções na web, não."""
    return it["fonte"] in ACAO_AGENDA and not e_golpe(it)


def _prazo(it: dict):
    m = _PRAZO.search(it.get("resumo") or "")
    if not m:
        return None
    try:
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    hoje = date.today()
    return d if hoje <= d <= hoje + timedelta(days=730) else None


def _marcar(id_: str, estado: str, adiado_ate: str = "", lembrete: int = None) -> None:
    with banco._trava:
        con = _con()
        try:
            con.execute("UPDATE triagem SET estado = ?, adiado_ate = ?, decidido_em = ?, atualizado = ?" + (", lembrete = ?" if lembrete is not None else "") + " WHERE id = ?",
                        [estado, adiado_ate, _agora(), _agora()] + ([lembrete] if lembrete is not None else []) + [id_])
            con.commit()
        finally:
            con.close()


def _aberto(id_: str) -> dict:
    """O item precisa ainda aguardar decisão; um item já aceito ou ignorado não muda de novo (evita lembrete duplicado)."""
    it = obter(id_)
    if it["estado"] in ENCERRADOS:
        raise ErroMiner("Este item já foi decidido.")
    return it


def aceitar(id_: str, enviar=None) -> str:
    """Aceita o item. Onde o aceite cria agenda (cria_agenda), cria o evento (se o resumo traz um prazo) ou o lembrete pelo agente do Mac; se o agente falha,
    o item continua pendente. Devolve a frase para mostrar ao usuário."""
    it = _aberto(id_)
    enviar = enviar or agenda.enviar
    if not cria_agenda(it):
        _marcar(id_, "concluida")
        return "Item aceito."
    titulo = ACAO_AGENDA[it["fonte"]]
    notas = ""   # o conteúdo do comunicado não vai para o Calendário nem para o Lembretes (só a ação)
    prazo = _prazo(it)
    if prazo:
        ok, txt = enviar("prazo_oficial", {"titulo": titulo, "data": prazo.isoformat(), "notas": notas, "alerta_dias_antes": 1})
        quando = "evento no Calendário"
    else:
        ok, txt = enviar("pendencia_miner", {"titulo": titulo, "vencimento": (date.today() + timedelta(days=1)).isoformat(), "hora": 9, "notas": notas})
        quando = "lembrete no app Lembretes"
    if not ok:
        raise ErroMiner(f"O item continua pendente: não foi possível criar o {quando}. Tente novamente em instantes.")
    _marcar(id_, "concluida", lembrete=1)
    return f"Item aceito e {quando} criado."


def adiar(id_: str, dias: int = 1) -> str:
    _aberto(id_)
    ate = (datetime.now(timezone.utc) + timedelta(days=max(1, int(dias)))).strftime("%Y-%m-%dT%H:%M:%SZ")
    _marcar(id_, "pendente", adiado_ate=ate)
    return "Item adiado até " + data_local(ate, so_data=True) + "."


def ignorar(id_: str) -> str:
    _aberto(id_)
    _marcar(id_, "descartada")
    return "Item ignorado."


def area_inicial() -> str:
    with banco._trava:
        con = _con()
        try:
            r = con.execute("SELECT valor FROM miner_config WHERE chave = 'inicio'").fetchone()
        finally:
            con.close()
    return r["valor"] if r and r["valor"] in AREAS else AREA_INICIAL_PADRAO


def definir_area_inicial(area: str) -> None:
    if area not in AREAS:
        raise ErroMiner("Área desconhecida.")
    with banco._trava:
        con = _con()
        try:
            con.execute("INSERT INTO miner_config (chave, valor) VALUES ('inicio', ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (area,))
            con.commit()
        finally:
            con.close()


def finance_ativo() -> bool:
    """O Studio Finance está no catálogo e não foi desligado? Só então o Miner oferece o botão que leva a ele."""
    import studio_links as links
    import studio_servicos as servicos
    if not links.url_produto("finance", "/avisos"):
        return False
    return any(s["id"] == "finance" for s in servicos.catalogo()) and "finance" not in servicos.desligados()
