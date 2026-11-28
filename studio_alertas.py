#!/usr/bin/env python3
"""Alertas do monitor (saúde, e-mail oficial, diários, privacidade, segurança): aviso, nunca lembrete.

Decisão do usuário em 26/11/2026: a triagem de avisos (lista "Heimdall: Triagem" do app Lembretes) deixou de existir; lembrete e evento só nascem
nas situações de studio_agenda.py e depois do aceite. Cada alerta agora:
  1. registra-se uma vez por origem estável (a mesma id não repete o aviso);
  2. alertas de saúde ficam na aba Avisos do Studio Health, com o texto completo; o Bark leva só texto genérico e o link do produto;
  3. o Mac recebe o aviso completo (notificação nativa); os demais alertas (ainda sem produto próprio) vão só ao Mac e ao Bark genérico, sem link.
Entrada: {id (origem estável), titulo, resumo, nivel: critico|alto|medio, fonte}. Interruptor: STUDIO_ALERTAS=0 desliga todos os avisos daqui.
"""
import os
import re
from datetime import datetime, timezone

import studio_avisos as avisos
import studio_avisos_mac as mac
import studio_banco as banco
import studio_bark as bark
import studio_links as links
import studio_pessoas as pessoas

NIVEIS = {"critico": "timeSensitive", "alto": "active", "medio": "passive"}
FONTE_PRODUTO = {"saude": "saude"}   # fonte do alerta -> chave do produto em studio_avisos.SERVICOS
# Fonte do alerta -> tela do Studio Miner que a recebe (usada enquanto STUDIO_MINER não for 0)
MINER_CAMINHO = {"email": "/rotina", "justica": "/cidadania", "diarios": "/cidadania", "legislacao": "/cidadania", "licitacoes": "/cidadania", "certidoes": "/cidadania", "agendamentos": "/cidadania", "privacidade": "/identidade"}


def _caminho_miner(fonte):
    if os.environ.get("STUDIO_MINER", "1") != "1":
        return None
    return MINER_CAMINHO.get(fonte)


def _texto(s, limite: int) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:limite]


def _registrar(origem: str, dado: dict) -> bool:
    """True se a origem é nova (primeira vez que o alerta aparece)."""
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not banco.DB_PATH.exists():
        banco.iniciar()
    with banco._trava:
        con = banco.conectar()
        try:
            cur = con.execute("INSERT OR IGNORE INTO triagem (id, criado, fonte, nivel, titulo, resumo, estado, lembrete, atualizado) "
                              "VALUES (?, ?, ?, ?, ?, ?, 'avisado', 0, ?)",
                              (origem, agora, dado["fonte"], dado["nivel"], dado["titulo"], dado["resumo"], agora))
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()


def publicar(dado: dict) -> dict:
    """Publica o alerta. Devolve {ok, id, novo, mac, bark, aba}. Levanta ValueError se faltar id ou título."""
    origem = _texto(dado.get("id"), 300)
    titulo = _texto(dado.get("titulo"), 150)
    if not origem or not titulo:
        raise ValueError("faltam id e título")
    nivel = str(dado.get("nivel", "alto")).strip().lower()
    nivel = nivel if nivel in NIVEIS else "alto"
    fonte = re.sub(r"[^a-z0-9_-]", "", str(dado.get("fonte", "")).lower())[:20]
    resumo = _texto(dado.get("resumo"), 2000)
    r = {"ok": True, "id": origem, "novo": False, "mac": False, "bark": False, "aba": False}
    if os.environ.get("STUDIO_ALERTAS", os.environ.get("STUDIO_ALERTAS", "1")) == "0":
        return {**r, "desativado": True}
    if not _registrar(origem, {"fonte": fonte, "nivel": nivel, "titulo": titulo, "resumo": resumo}):
        return r
    r["novo"] = True
    if not pessoas.e_dono():   # o alerta de um convidado fica só na triagem dele: nunca aparece no Mac nem no Bark do dono
        return {**r, "convidado": True}
    produto = FONTE_PRODUTO.get(fonte)
    if produto in avisos.SERVICOS:
        try:
            avisos.do_servico(produto).gravar(titulo, resumo or titulo)
            r["aba"] = True
        except (ValueError, OSError):
            pass
    completo = {"title": titulo, "body": resumo, "group": fonte or "alertas", "level": NIVEIS[nivel]}
    miner = None if produto else _caminho_miner(fonte)
    if produto:
        completo = links.com_link(completo, produto)
    elif miner:
        completo = links.com_link(completo, "miner", miner)
    r["mac"] = mac.publicar(completo)
    if produto and r["aba"] and avisos.bark_ligado(produto):
        r["bark"] = bark.enviar_bark(avisos.texto_bark(produto))
    elif not produto:
        generico = {"title": "StudioLibre: alerta novo", "body": "Há um alerta novo. Abra o aplicativo do Mac.", "group": fonte or "alertas", "level": NIVEIS[nivel]}
        r["bark"] = bark.enviar_bark(links.com_link(generico, "miner", miner) if miner else generico)
    return r


def estado(limite: int = 50) -> dict:
    """Últimos alertas registrados (consulta somente leitura)."""
    if not banco.DB_PATH.exists():
        return {"alertas": [], "total": 0}
    con = banco.conectar(somente_leitura=True)
    try:
        linhas = [dict(x) for x in con.execute("SELECT id, criado, fonte, nivel, titulo FROM triagem ORDER BY criado DESC LIMIT ?", (int(limite),))]
        total = con.execute("SELECT COUNT(*) FROM triagem").fetchone()[0]
    finally:
        con.close()
    return {"alertas": linhas, "total": total}
