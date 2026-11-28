#!/usr/bin/env python3
"""Coletor do DJEN (Diário de Justiça Eletrônico Nacional, Comunica PJe, do CNJ) para a área Cidadania do Studio Miner.

O usuário informa nos Ajustes do Miner o próprio nome, a OAB (número e UF, opcional) e os números dos processos que acompanha. Todos os dias o coletor
consulta a API aberta do DJEN (sem chave) por OAB, por nome da parte e por número de processo, e publica cada comunicação nova como alerta da fonte
"justica" (studio_alertas.publicar), com o que o ato significa, como foi encontrado, o início e a estimativa do prazo e o que conferir.
Nada vira lembrete ou evento sem o aceite do usuário (studio_agenda.py).

Limites e cuidados (levantamento de 27/11/2026, guides/miner_plano.txt):
  - a API só responde a acessos do Brasil (o coletor roda no Mac) e limita as consultas por IP: um IP, intervalo entre chamadas, uma espera em caso de 429;
  - a busca por nome traz homônimos: o aviso diz que foi achado pelo nome e pede a conferência; só o número do processo confirma;
  - o texto da comunicação traz dados de terceiros: o alerta guarda só um trecho curto;
  - o prazo é estimativa (dias úteis, feriados nacionais, recesso de 20/12 a 20/01), nunca substitui a conferência no processo.
Variáveis: STUDIO_MINER_DJEN (padrão 1; 0 desliga), STUDIO_MINER_DJEN_HORA (hora local da consulta diária, padrão 7), STUDIO_MINER_DJEN_URL (endereço da API).
Usa só a biblioteca padrão do Python.
"""
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import studio_banco as banco
import studio_feriados as feriados
import studio_miner_dados as dados
import studio_pessoas as pessoas

URL = os.environ.get("STUDIO_MINER_DJEN_URL", "https://comunicaapi.pje.jus.br/api/v1/comunicacao")
SUFIXOS_OAB = ("", "A", "B", "N", "S", "E", "O")   # a API compara o texto exato: sem as variantes, parte das publicações some
UFS = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}
MAX_PROCESSOS = 50
MAX_PAGINAS = 20
POR_PAGINA = 100
JANELA_INICIAL_DIAS = 7
SOBREPOSICAO_DIAS = 3
PAUSA_S = 1.5
TRECHO = 350
ESPERA_TENTATIVA = timedelta(hours=2)   # depois de uma consulta (com ou sem falha), a consulta diária só repete depois deste intervalo


class ErroDJEN(Exception):
    """A consulta ao DJEN falhou (fora do Brasil, limite de consultas, instabilidade)."""


# ---------- configuração do usuário ----------

def _garantir_banco() -> None:
    if not banco.caminho().exists():   # fora do trinco: iniciar() também o usa
        banco.iniciar()


def _ler(chave: str, padrao: str = "") -> str:
    _garantir_banco()
    with banco._trava:
        con = dados._con()
        try:
            r = con.execute("SELECT valor FROM miner_config WHERE chave = ?", (chave,)).fetchone()
        finally:
            con.close()
    return r["valor"] if r else padrao


def _gravar(**campos) -> None:
    _garantir_banco()
    with banco._trava:
        con = dados._con()
        try:
            for k, v in campos.items():
                con.execute("INSERT INTO miner_config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (k, str(v)))
            con.commit()
        finally:
            con.close()


def numero_cnj_valido(numero: str) -> str:
    """Devolve o número único com 20 dígitos se o dígito verificador confere (módulo 97 da Resolução CNJ 65/2008); senão, texto vazio."""
    d = re.sub(r"\D", "", numero or "")
    if len(d) != 20:
        return ""
    n, dv, resto = d[:7], d[7:9], d[9:]
    return d if 98 - (int(n + resto + "00") % 97) == int(dv) else ""


def mascara_cnj(d: str) -> str:
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"


def configuracao() -> dict:
    procs = [p for p in _ler("processos").split(",") if p]
    try:
        por_proc = json.loads(_ler("proc_municipios") or "{}")
    except ValueError:
        por_proc = {}
    return {"nome": _ler("nome"), "oab_numero": _ler("oab_numero"), "oab_uf": _ler("oab_uf"), "processos": procs,
            "municipio": _ler("municipio"), "proc_municipios": por_proc if isinstance(por_proc, dict) else {}, "suspensoes": _ler("suspensoes"),
            "ultimo": _ler("djen_ultimo"), "estado": _ler("djen_estado")}


def configurado() -> bool:
    c = configuracao()
    return bool(c["nome"] or c["oab_numero"] or c["processos"])


def salvar(nome: str, oab_numero: str, oab_uf: str, processos_texto: str, municipio: str = None, suspensoes: str = None) -> str:
    """Valida e grava a configuração. Levanta dados.ErroMiner com a mensagem para o usuário."""
    nome = re.sub(r"\s+", " ", nome or "").strip()
    if nome and (len(nome) < 5 or len(nome) > 100 or len(nome.split()) < 2):
        raise dados.ErroMiner("Informe o nome completo, com nome e sobrenome, ou deixe o campo em branco.")
    num = re.sub(r"\D", "", oab_numero or "")
    uf = (oab_uf or "").strip().upper()
    if num and not (1 <= len(num) <= 7):
        raise dados.ErroMiner("O número da OAB deve ter só dígitos, até sete.")
    if num and uf not in UFS:
        raise dados.ErroMiner("Informe a UF da OAB com duas letras, por exemplo SP.")
    if not num:
        uf = ""
    validos, invalidos, por_proc = [], [], {}
    for linha in re.split(r"[\n;,]+", processos_texto or ""):
        linha = linha.strip()
        if not linha:
            continue
        numero_txt, _, local = linha.partition("@")
        d = numero_cnj_valido(numero_txt)
        if not d:
            invalidos.append(linha[:30])
            continue
        if local.strip():
            try:
                cidade, uf_c = feriados.partir_municipio(local)
            except feriados.ErroFeriados as ex:
                raise dados.ErroMiner(f"Município do processo {mascara_cnj(d)}: {ex}")
            por_proc[d] = f"{cidade}/{uf_c}"
        if d not in validos:
            validos.append(d)
    if invalidos:
        raise dados.ErroMiner("Número de processo inválido: " + "; ".join(invalidos[:3]) + ". Use o número único de 20 dígitos, com ou sem pontuação.")
    if len(validos) > MAX_PROCESSOS:
        raise dados.ErroMiner(f"Acompanhe no máximo {MAX_PROCESSOS} processos.")
    campos = {}
    if municipio is not None:
        municipio = (municipio or "").strip()
        if municipio:
            try:
                cidade, uf_c = feriados.partir_municipio(municipio)
            except feriados.ErroFeriados as ex:
                raise dados.ErroMiner(str(ex))
            municipio = f"{cidade}/{uf_c}"
        campos["municipio"] = municipio
    if suspensoes is not None:
        try:
            feriados.ler_suspensoes(suspensoes)
        except feriados.ErroFeriados as ex:
            raise dados.ErroMiner(str(ex))
        campos["suspensoes"] = "\n".join(l.strip() for l in suspensoes.splitlines() if l.strip())
    _gravar(nome=nome, oab_numero=num, oab_uf=uf, processos=",".join(validos), proc_municipios=json.dumps(por_proc, ensure_ascii=False), **campos)
    if not (nome or num or validos):
        return "Configuração limpa. Nenhuma consulta será feita."
    return "Configuração salva."


# ---------- prazo ----------

def dia_util(d: date, cal=None) -> bool:
    return (cal or feriados.nacional()).dia_util(d)


def proximo_util(d: date, cal=None) -> date:
    return (cal or feriados.nacional()).proximo_util(d)


def somar_uteis(d: date, n: int, cal=None) -> date:
    return (cal or feriados.nacional()).somar_uteis(d, n)


_NUM = {"um": 1, "dois": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "quinze": 15, "vinte": 20, "trinta": 30}


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def dias_de_prazo(texto: str):
    """(dias, uteis) do primeiro prazo citado no texto, ou None. Padrão: dias úteis (CPC e CLT), salvo menção a dias corridos."""
    t = _sem_acento(texto)
    for m in re.finditer(r"prazo[^.;]{0,80}?\b(\d{1,3}|" + "|".join(_NUM) + r")\b[^.;]{0,25}?dias?\b([^.;]{0,20})", t):
        v = m.group(1)
        n = int(v) if v.isdigit() else _NUM.get(v)
        if n and 1 <= n <= 90:
            return n, "corrido" not in m.group(2)
    return None


def prazo_do_ato(disponibilizacao: date, texto: str, cal=None):
    """(publicacao, inicio, fim, dias, uteis): a publicação vale no primeiro dia útil depois da disponibilização e a contagem começa no dia útil seguinte."""
    cal = cal or feriados.nacional()
    pub = cal.proximo_util(disponibilizacao)
    inicio = cal.proximo_util(pub)
    p = dias_de_prazo(texto)
    if not p:
        return pub, inicio, None, None, True
    n, uteis = p
    fim = cal.somar_uteis(pub, n) if uteis else cal.ajustar(inicio + timedelta(days=n - 1))
    return pub, inicio, fim, n, uteis


def calendario_do(numero: str, cfg: dict, urlopen=None, rede: bool = True, cache: dict = None):
    """Calendário do foro de um processo: UF pelo número (ou pelo município informado), município do processo ou o padrão e as suspensões informadas."""
    por_proc = cfg.get("proc_municipios") or {}
    local = por_proc.get(numero) or cfg.get("municipio") or ""
    uf = feriados.uf_do_processo(numero)
    chave = f"{local}|{uf}"
    if cache is not None and chave in cache:
        return cache[chave]
    cidade, uf_m, ibge = "", "", 0
    erro = ""
    if local:
        try:
            cidade, uf_m = feriados.partir_municipio(local)
            if not uf or uf == uf_m:   # num processo estadual de outra UF, o município informado não vale
                ibge = feriados.codigo_ibge(cidade, uf_m, urlopen) if rede else 0
        except feriados.ErroFeriados as ex:
            erro = f"município {local}: {ex}"
    try:
        susp = [(a, b, m) for a, b, m in feriados.ler_suspensoes(cfg.get("suspensoes", ""))]
    except feriados.ErroFeriados:
        susp = []
    cal = feriados.Calendario(uf=uf or uf_m, cidade=cidade, ibge=ibge, suspensoes=susp, urlopen=urlopen, rede=rede)
    if erro:
        cal.faltas.append(erro)
    if cache is not None:
        cache[chave] = cal
    return cal


# ---------- significado do ato ----------

# (padrão no texto sem acento, o que significa, o que conferir, nível)
ATOS = [
    (r"\bcitacao\b|\bcite-se\b|\bcitado\b", "Chamamento para integrar o processo e apresentar defesa.", "Abra o processo hoje e confira o prazo de resposta.", "critico"),
    (r"mandado|penhora|bloqueio|sisbajud|bacenjud|constricao|arresto|sequestro", "Ordem de constrição de bens ou valores.", "Confira o valor, a conta e o prazo para impugnar.", "critico"),
    (r"tutela|liminar|antecipacao", "Decisão provisória sobre pedido urgente.", "Leia o dispositivo e veja o prazo de cumprimento ou de recurso.", "alto"),
    (r"audiencia|pericia|designad", "Marca ou altera audiência ou perícia.", "Anote a data e a hora, confirme a intimação das testemunhas e a presença.", "alto"),
    (r"sentenca|julgo (procedente|improcedente|parcialmente)|julgo extint|homologo", "Decisão que encerra a fase do processo na instância.", "Confira o dispositivo (quem ganhou o quê) e os prazos de embargos e de recurso.", "alto"),
    (r"acordao|embargos|recurso|apelacao|agravo", "Decisão ou andamento de recurso.", "Confira o resultado e o prazo para novo recurso ou cumprimento.", "alto"),
    (r"manifeste-se|manifestacao|intime-se|intimacao para|prazo de|prazo para|emende|emenda|apresente|junte|comprove", "Abre prazo para a parte se manifestar ou cumprir uma ordem.", "Leia o que foi pedido e a contagem do prazo.", "alto"),
    (r"despacho|ato ordinatorio|vista", "Ordem de andamento, em geral sem decisão sobre o mérito.", "Leia se há tarefa ou prazo para a parte.", "medio"),
    (r"decisao interlocutoria|decido|indefiro|defiro", "Decisão sobre um ponto do processo, sem encerrá-lo.", "Confira o resultado e se cabe recurso (agravo).", "alto"),
]
ATO_GENERICO = ("Comunicação do tribunal sobre o processo.", "Leia o texto completo no processo para saber se há prazo.", "medio")
MOTIVO = {
    "oab": "Encontrada pela sua OAB: o processo tem você como advogado.",
    "processo": "Encontrada pelo número de um processo que você acompanha.",
    "nome": "Encontrada pelo seu nome como parte: confira o número do processo, porque homônimos aparecem na busca por nome.",
}


def classificar(item: dict) -> tuple:
    t = _sem_acento(" ".join([item.get("tipo", ""), item.get("documento", ""), item.get("classe", ""), item.get("texto", "")[:1500]]))
    for padrao, sig, fazer, nivel in ATOS:
        if re.search(padrao, t):
            return sig, fazer, nivel
    return ATO_GENERICO


# ---------- consulta e normalização ----------

def _data(s: str):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s or "") or None
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _limpo(t) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(t or ""))).strip()


def normalizar(bruto: dict, motivo: str):
    """Item da API -> dicionário padronizado, ou None se faltar o essencial. Aceita as grafias de campo que a API já usou."""
    g = lambda *ks: next((bruto.get(k) for k in ks if bruto.get(k) not in (None, "")), "")   # noqa: E731
    numero = re.sub(r"\D", "", str(g("numero_processo", "numeroProcesso")))
    disp = _data(str(g("data_disponibilizacao", "dataDisponibilizacao", "datadisponibilizacao")))
    ident = str(g("id", "hash"))
    if not (numero and disp and ident):
        return None
    return {"id": ident, "numero": numero, "disponibilizacao": disp, "tribunal": str(g("siglaTribunal", "siglatribunal")), "orgao": _limpo(g("nomeOrgao", "nomeorgao")),
            "tipo": _limpo(g("tipoComunicacao", "tipocomunicacao")), "documento": _limpo(g("tipoDocumento", "tipodocumento")), "classe": _limpo(g("nomeClasse", "nomeclasse")),
            "texto": _limpo(g("texto")), "motivo": motivo}


def _requisitar(params: dict, urlopen=None) -> dict:
    url = URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "StudioLibre-Miner/1.0"})
    try:
        with (urlopen or urllib.request.urlopen)(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as ex:
        if ex.code == 403:
            raise ErroDJEN("O DJEN recusou o acesso (ele só responde a acessos feitos do Brasil).")
        if ex.code == 429:
            raise ErroDJEN("limite")
        raise ErroDJEN(f"O DJEN respondeu com erro {ex.code}.")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ErroDJEN("Não foi possível falar com o DJEN agora.")


def buscar(params: dict, requisitar=None, dormir=None) -> list:
    """Todas as páginas de uma consulta. Em 429, espera um minuto uma vez; depois disso, desiste da consulta."""
    requisitar = requisitar or _requisitar
    dormir = dormir or time.sleep
    itens, pagina = [], 1
    while pagina <= MAX_PAGINAS:
        p = dict(params, pagina=pagina, itensPorPagina=POR_PAGINA)
        try:
            r = requisitar(p)
        except ErroDJEN as ex:
            if str(ex) != "limite":
                raise
            dormir(65)
            try:
                r = requisitar(p)
            except ErroDJEN as ex2:
                raise ErroDJEN("O DJEN limitou as consultas. A próxima tentativa será na consulta seguinte." if str(ex2) == "limite" else str(ex2))
        lote = (r or {}).get("items") or []
        itens.extend(lote)
        total = int((r or {}).get("count") or 0)
        if not lote or (total and len(itens) >= total):
            break
        pagina += 1
        dormir(PAUSA_S)
    return itens


def consultas(cfg: dict, inicio: date, fim: date) -> list:
    """(motivo, parâmetros) de cada consulta: OAB com as variantes de sufixo, nome da parte e cada processo."""
    base = {"dataDisponibilizacaoInicio": inicio.isoformat(), "dataDisponibilizacaoFim": fim.isoformat()}
    lista = []
    if cfg["oab_numero"] and cfg["oab_uf"]:
        for suf in SUFIXOS_OAB:
            num = cfg["oab_numero"] + (("-" + suf) if suf else "")
            lista.append(("oab", dict(base, numeroOab=num, ufOab=cfg["oab_uf"])))
    if cfg["nome"]:
        lista.append(("nome", dict(base, nomeParte=cfg["nome"])))
    for p in cfg["processos"]:
        lista.append(("processo", dict(base, numeroProcesso=p)))
    return lista


FORCA = {"processo": 3, "oab": 2, "nome": 1}


def coletar(cfg: dict, inicio: date, fim: date, requisitar=None, dormir=None) -> tuple:
    """Executa as consultas e junta as comunicações repetidas (o motivo mais forte vence). Devolve (itens, erros)."""
    dormir = dormir or time.sleep
    achados, erros = {}, []
    for motivo, params in consultas(cfg, inicio, fim):
        try:
            for bruto in buscar(params, requisitar, dormir):
                it = normalizar(bruto, motivo)
                if it and (it["id"] not in achados or FORCA[motivo] > FORCA[achados[it["id"]]["motivo"]]):
                    achados[it["id"]] = it
        except ErroDJEN as ex:
            erros.append(str(ex))
            if "acesso" in str(ex) or "limitou" in str(ex):
                break
        dormir(PAUSA_S)
    return sorted(achados.values(), key=lambda x: (x["disponibilizacao"], x["id"])), erros


# ---------- alerta com contexto ----------

def alerta(it: dict, hoje: date = None, cal=None) -> dict:
    """Monta o alerta (id, título, resumo com contexto, nível, fonte) de uma comunicação."""
    hoje = hoje or date.today()
    significa, fazer, nivel = classificar(it)
    cal = cal or feriados.nacional()
    pub, inicio, fim, dias, uteis = prazo_do_ato(it["disponibilizacao"], it["texto"], cal)
    onde = ", ".join(x for x in (it["tribunal"], it["orgao"]) if x)
    tipo = it["tipo"] or it["documento"] or "Comunicação"
    partes = [f"{tipo} no processo {mascara_cnj(it['numero']) if len(it['numero']) == 20 else it['numero']}" + (f" ({onde})" if onde else "") + f", disponibilizada em {it['disponibilizacao']:%d/%m/%Y}.",
              significa, MOTIVO[it["motivo"]],
              f"A publicação vale em {pub:%d/%m/%Y} e a contagem de prazo começa em {inicio:%d/%m/%Y}."]
    if fim:
        partes.append(f"O texto cita prazo de {dias} dias {'úteis' if uteis else 'corridos'}: termina em torno de {fim:%d/%m/%Y}. {cal.aplicados()} Feriado local e suspensão de prazo precisam ser comprovados no ato do recurso (art. 1.003, § 6º, do CPC): confira no calendário publicado no site do tribunal (Recomendação CNJ 44/2020) e no processo.")
        if fim <= hoje + timedelta(days=5):
            nivel = "critico"
        partes.append(f"Prazo: {fim:%d/%m/%Y}")
    else:
        partes.append("O texto não traz prazo em dias; confira no processo se há prazo a cumprir.")
    partes.append("O que fazer: " + fazer)
    if it["texto"]:
        partes.append("Trecho: " + it["texto"][:TRECHO] + ("…" if len(it["texto"]) > TRECHO else ""))
    return {"id": "djen:" + it["id"], "titulo": f"{tipo} em processo da Justiça ({it['tribunal'] or 'tribunal'})",
            "resumo": " ".join(partes), "nivel": nivel, "fonte": "justica"}


def _publicar(dado: dict) -> dict:
    import studio_alertas as alertas
    return alertas.publicar(dado)


def executar(hoje: date = None, requisitar=None, dormir=None, publicar=None, requisitar_datajud=None, urlopen_feriados=None, sem_rede: bool = False) -> dict:
    """Consulta o DJEN para a pessoa atual e publica as comunicações novas. Devolve {ok, novas, total, erros, mensagem}."""
    hoje = hoje or date.today()
    publicar = publicar or _publicar
    if os.environ.get("STUDIO_MINER_DJEN", "1") == "0":
        return {"ok": False, "novas": 0, "total": 0, "erros": [], "mensagem": "A consulta ao DJEN está desligada."}
    cfg = configuracao()
    if not (cfg["nome"] or cfg["oab_numero"] or cfg["processos"]):
        return {"ok": False, "novas": 0, "total": 0, "erros": [], "mensagem": "Informe nome, OAB ou processos nos Ajustes para consultar o DJEN."}
    ultimo = _data(cfg["ultimo"])
    inicio = (ultimo - timedelta(days=SOBREPOSICAO_DIAS)) if ultimo else hoje - timedelta(days=JANELA_INICIAL_DIAS)
    _gravar(djen_tentativa=datetime.now().isoformat(timespec="seconds"))
    itens, erros = coletar(cfg, inicio, hoje, requisitar, dormir)
    novas = 0
    cache = {}
    for it in itens:
        r = publicar(alerta(it, hoje, calendario_do(it["numero"], cfg, urlopen_feriados, rede=not sem_rede, cache=cache)))
        novas += 1 if r.get("novo") else 0
    falhou = bool(erros) and not itens
    if not erros:
        _gravar(djen_ultimo=hoje.isoformat(), djen_estado=f"{datetime.now():%d/%m/%Y %H:%M}: {len(itens)} comunicações, {novas} novas.", djen_falhas="0")
        msg = f"Consulta concluída: {len(itens)} comunicações, {novas} novas."
    else:
        falhas = int(_ler("djen_falhas", "0") or 0) + 1
        _gravar(djen_estado=f"{datetime.now():%d/%m/%Y %H:%M}: consulta incompleta. {erros[0]}", djen_falhas=str(falhas))
        msg = "Consulta incompleta. " + erros[0]
        if falhas >= 3:
            publicar({"id": f"djen-falha:{hoje.isoformat()}", "titulo": "Consulta ao DJEN indisponível", "nivel": "alto", "fonte": "justica",
                      "resumo": f"A consulta ao DJEN falhou {falhas} vezes seguidas: {erros[0]} Enquanto isso, intimações novas podem não aparecer aqui. Confira o Domicílio Judicial Eletrônico e os e-mails dos sistemas Push dos tribunais."})
    if cfg["processos"]:   # andamentos dos processos acompanhados (DataJud); uma falha dele não conta como falha do DJEN
        import studio_datajud
        rd = studio_datajud.executar(cfg["processos"], requisitar_datajud, dormir, publicar)
        if not rd.get("desligado"):
            msg += f" Andamentos: {rd['novos']} aviso(s) novo(s)." + (" " + rd["erros"][0] if rd["erros"] else "")
            novas += rd["novos"]
    return {"ok": not erros, "novas": novas, "total": len(itens), "erros": erros, "mensagem": msg, "falhou": falhou}


def executar_todos(**kw) -> dict:
    """A consulta diária vale para todas as pessoas, não só para o dono: percorre quem já tem pasta e roda a consulta devida de cada uma, com os dados dela."""
    feitos = {}
    for quem in pessoas.existentes(banco.DB_DIR):
        try:
            with pessoas.definir(quem), banco.da_pessoa(quem):
                if devida():
                    feitos[quem] = executar(**kw)
        except Exception as ex:  # a falha de uma pessoa não impede a das outras
            feitos[quem] = {"ok": False, "mensagem": type(ex).__name__}
    return feitos


def hora_da_consulta() -> int:
    try:
        return min(23, max(0, int(os.environ.get("STUDIO_MINER_DJEN_HORA", "7"))))
    except ValueError:
        return 7


def devida(agora: datetime = None) -> bool:
    """A consulta diária já passou da hora e ainda não rodou hoje?"""
    agora = agora or datetime.now()
    if os.environ.get("STUDIO_MINER_DJEN", "1") == "0" or not configurado():
        return False
    if agora.hour < hora_da_consulta() or _ler("djen_ultimo") == agora.date().isoformat():
        return False
    try:
        return agora - datetime.fromisoformat(_ler("djen_tentativa")) >= ESPERA_TENTATIVA
    except ValueError:
        return True
