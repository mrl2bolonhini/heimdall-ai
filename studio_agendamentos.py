#!/usr/bin/env python3
"""Agendamentos públicos escassos na área Cidadania do Studio Miner (passaporte, consulado, INSS, Poupatempo e Detran, Receita, visto dos Estados Unidos).

Não existe API nem lista pública de vagas desses serviços: tudo exige login ou captcha, e o site de vistos dos Estados Unidos proíbe automação. O Miner não tenta
burlar nada. Ele ajuda de quatro formas legítimas:
1. Lembrete assistido: nos dias que a pessoa escolher, avisa que é hora de tentar o agendamento, com o caminho oficial, orientação de atendimento prioritário e
   canais sem agenda. A pessoa faz o agendamento.
2. Notícias oficiais de mutirão: lê, respeitando o robots.txt, as páginas oficiais que a pessoa marcar e avisa quando citam mutirão, plantão ou abertura de agenda.
3. E-mail de liberação: se a pessoa informa o remetente do serviço (por exemplo o consulado), o monitor de e-mail (somente leitura) avisa na hora quando chega um
   e-mail dele sobre vaga ou agendamento.
4. Orientação: atendimento prioritário (Lei 10.048/2000: idosos, gestantes, lactantes, pessoas com deficiência e pessoas com criança de colo) e canais sem agenda.
"""
import html
import re
import sys
from datetime import date, timedelta

import studio_cidadania as cid
import studio_diarios as diarios
import studio_feriados as feriados
import studio_miner_dados as dados

CHAVE, ROTULO, INTERVALO = "agendamentos", "Agendamentos", timedelta(hours=20)
# chave -> (nome, endereço oficial, orientação específica)
SERVICOS = {
    "pf": ("Passaporte (Polícia Federal)", "https://www.gov.br/pf", "O pedido e o agendamento são feitos no site da Polícia Federal; a taxa é paga antes. Se a agenda estiver cheia, confira outros postos de atendimento."),
    "inss": ("INSS", "https://meu.inss.gov.br", "Agende pelo Meu INSS ou pela central 135. Muitos serviços não precisam de agendamento: peça pelo Meu INSS e acompanhe o andamento."),
    "poupatempo": ("Poupatempo e Detran", "https://www.poupatempo.sp.gov.br", "Agende pelo site do Poupatempo; as vagas variam por posto e muitas vezes reabrem com cancelamentos."),
    "receita": ("Receita Federal", "https://www.gov.br/receitafederal", "Muitos atendimentos da Receita são digitais, pelo e-CAC, sem agendamento; confira antes de agendar presencial."),
    "consulado": ("Consulado ou embaixada", "", "Use o site do próprio consulado; as vagas costumam abrir em horários e dias fixos e reabrem com cancelamentos."),
    "visto_eua": ("Visto dos Estados Unidos", "https://travel.state.gov", "O site de agendamento proíbe automação: o Miner só lembra, e o agendamento é feito por você. Reabertura de vagas por cancelamento é comum."),
    "outro": ("Outro serviço", "", "Confira o site oficial do serviço."),
}
PRIORIDADE = ("Confira se você tem direito a atendimento prioritário (idosos, gestantes, lactantes, pessoas com deficiência e pessoas com criança de colo, Lei 10.048/2000) "
              "e se o serviço tem canal sem agenda (telefone, atendimento digital ou balcão).")
FREQUENCIAS = {"dias_uteis": "Todo dia útil", "diaria": "Todo dia", "semanal": "Toda segunda-feira"}
PALAVRAS_MUTIRAO = ["mutirão", "plantão", "novas vagas", "abertura de agenda", "vagas liberadas"]
PALAVRAS_EMAIL = ["vaga", "agendamento", "disponível", "liberad", "horário"]
MAX_LEMBRETES = 15
MAX_REMETENTES = 8


def configurado(c: dict) -> bool:
    return bool(c.get("lembretes") or c.get("paginas") or c.get("sites"))


def salvar(campos: dict) -> str:
    c = cid.cfg(CHAVE)
    serv = campos.get("servico", "")
    if serv:
        if serv not in SERVICOS or campos.get("frequencia", "dias_uteis") not in FREQUENCIAS:
            raise dados.ErroMiner("Escolha o serviço e a frequência do lembrete.")
        if len(c.get("lembretes", [])) >= MAX_LEMBRETES:
            raise dados.ErroMiner(f"Registre no máximo {MAX_LEMBRETES} lembretes.")
        c.setdefault("lembretes", []).append({"id": cid.hash_curto(serv, campos.get("nome", ""), len(c.get("lembretes", [])), campos.get("frequencia")), "servico": serv,
                                              "nome": cid.limpo(campos.get("nome", ""), 60), "frequencia": campos.get("frequencia", "dias_uteis")})
        cid.salvar_cfg(CHAVE, c)
        return "Lembrete de agendamento registrado."
    c["sites"] = [k for k in SERVICOS if SERVICOS[k][1] and (campos.get("sites_" + k) == "1" or k in campos.get("sites", "").split(","))]
    c["paginas"] = [cid.validar_url(u) for u in cid.lista(campos.get("paginas", ""), minimo=12, maximo_item=300, maximo=8, o_que="endereços de notícias")]
    c["remetentes"] = [r.lower() for r in cid.lista(campos.get("remetentes", ""), minimo=4, maximo_item=80, maximo=MAX_REMETENTES, o_que="remetentes")]
    if any(not re.fullmatch(r"[a-z0-9.@_-]+\.[a-z]{2,}|[a-z0-9._-]+@[a-z0-9.-]+", r) for r in c["remetentes"]):
        raise dados.ErroMiner("Informe o remetente como domínio (consulado.exemplo.gov) ou endereço de e-mail.")
    cid.salvar_cfg(CHAVE, c)
    return "Agendamentos salvos."


def remover(campos: dict) -> str:
    c = cid.cfg(CHAVE)
    c["lembretes"] = [i for i in c.get("lembretes", []) if i["id"] != campos.get("id")]
    cid.salvar_cfg(CHAVE, c)
    return "Lembrete removido."


def alerta_lembrete(item: dict, hoje: date) -> dict:
    nome, site, dica = SERVICOS[item["servico"]]
    rotulo = item.get("nome") or nome
    return {"id": f"agenda:{item['id']}:{hoje.isoformat()}", "titulo": f"Tentar o agendamento: {rotulo}"[:100], "nivel": "medio", "fonte": "agendamentos",
            "resumo": f"É hora de tentar o agendamento de {rotulo}. {dica} {PRIORIDADE} O que fazer: entre no site oficial digitando o endereço" + (f" ({site.replace('https://', '')})" if site else "") +
                      ", nunca por link recebido por mensagem, e tente uma vez; as vagas aparecem e somem com cancelamentos."}


def paginas_oficiais(c: dict) -> list:
    return [SERVICOS[k][1] for k in c.get("sites", []) if k in SERVICOS and SERVICOS[k][1]] + list(c.get("paginas", []))


def dominios() -> list:
    """Remetentes que o monitor de e-mail deve tratar como oficiais (a pessoa os informou)."""
    try:
        return [r for r in cid.cfg(CHAVE).get("remetentes", []) if "@" not in r]
    except Exception:  # noqa: BLE001
        return []


def alerta_de_email(de: str, assunto: str, corpo: str, mid: str):
    """Alerta crítico quando chega e-mail de um remetente informado pela pessoa e o texto fala de vaga ou agendamento; None nos demais casos."""
    try:
        c = cid.cfg(CHAVE)
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"[\w.+-]+@([\w.-]+)", (de or "").lower())
    endereco, dom = (m.group(0), m.group(1)) if m else ("", "")
    if not any(r == endereco or (r == dom or dom.endswith("." + r)) for r in c.get("remetentes", []) if "@" in r or "." in r):
        return None
    texto = f"{assunto} {corpo}"
    if not any(cid.sem_acento(p) in cid.sem_acento(texto) for p in PALAVRAS_EMAIL):
        return None
    return {"id": "agenda-email:" + mid.lower()[:200], "titulo": "E-mail de agendamento: possível vaga liberada", "nivel": "critico", "fonte": "agendamentos",
            "resumo": f"Chegou um e-mail de um remetente que você acompanha sobre agendamento. Assunto: {cid.limpo(assunto, 100)}. O que significa: vagas liberadas costumam durar poucas horas. "
                      "O que fazer: entre agora no site oficial digitando o endereço (não use links do e-mail) e confira se há vaga."}


def executar(c) -> dict:
    conf = cid.cfg(CHAVE)
    novos, erros = 0, []
    cal = feriados.nacional()
    for it in conf.get("lembretes", []):
        f = it.get("frequencia", "dias_uteis")
        if (f == "diaria") or (f == "dias_uteis" and cal.dia_util(c.hoje)) or (f == "semanal" and c.hoje.weekday() == 0):
            novos += c.avisar(alerta_lembrete(it, c.hoje))
    paginas = paginas_oficiais(conf)
    if paginas:
        n, e = diarios.vigiar(paginas, PALAVRAS_MUTIRAO, c, fonte="agendamentos", rotulo="Notícia")
        novos += n
        erros.extend(e)
    return {"novos": novos, "erros": erros, "resumo": f"{len(conf.get('lembretes', []))} lembrete(s), {len(paginas)} página(s) oficial(is)"}


def formulario(csrf: str) -> str:
    c = cid.cfg(CHAVE)
    e = lambda t: html.escape(str(t), quote=True)   # noqa: E731
    serv = "".join(f'<option value="{k}">{e(v[0])}</option>' for k, v in SERVICOS.items())
    freq = "".join(f'<option value="{k}">{e(v)}</option>' for k, v in FREQUENCIAS.items())
    sites = "".join(f'<p><input id="ag-{k}" type="checkbox" name="sites_{k}" value="1"{" checked" if k in c.get("sites", []) else ""}> <label for="ag-{k}">Ler as páginas oficiais de {e(v[0])}</label></p>'
                    for k, v in SERVICOS.items() if v[1])
    saida = [f'<h2 id="h-agend">Agendamentos</h2><form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}"><h3>Novo lembrete de agendamento</h3>'
             f'<p><label for="as">Serviço</label><br><select id="as" name="servico">{serv}</select></p>'
             '<p><label for="an">Identificação (opcional)</label><br><input id="an" name="nome" type="text" maxlength="60"></p>'
             f'<p><label for="af">Frequência</label><br><select id="af" name="frequencia">{freq}</select></p><button type="submit">Registrar lembrete</button></form>']
    if c.get("lembretes"):
        li = "".join(f'<li>{e(i.get("nome") or SERVICOS[i["servico"]][0])}: {e(FREQUENCIAS.get(i["frequencia"], ""))}. '
                     f'<form class="acao" method="post" action="/ajustes/fontes/{CHAVE}/remover"><input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="id" value="{e(i["id"])}">'
                     f'<button type="submit" aria-label="Remover lembrete de {e(i.get("nome") or SERVICOS[i["servico"]][0])}">Remover</button></form></li>' for i in c["lembretes"])
        saida.append(f"<h3>Lembretes registrados</h3><ol>{li}</ol>")
    saida.append(f'<form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}"><h3>Notícias oficiais e e-mail de liberação</h3>{sites}'
                 f'<p><label for="apag">Outras páginas oficiais de notícias (endereço https, um por linha)</label><br><textarea id="apag" name="paginas" rows="2" cols="40">{e(chr(10).join(c.get("paginas", [])))}</textarea></p>'
                 f'<p><label for="arem">Remetentes de e-mail de liberação de vagas (domínio ou endereço, um por linha)</label><br><textarea id="arem" name="remetentes" rows="2" cols="40">{e(chr(10).join(c.get("remetentes", [])))}</textarea></p>'
                 '<button type="submit">Salvar notícias e e-mail</button></form>')
    est = cid.estado(sys.modules[__name__])
    if est:
        saida.append(f'<p class="meta" role="status">{e(est)}</p>')
    return "".join(saida)
