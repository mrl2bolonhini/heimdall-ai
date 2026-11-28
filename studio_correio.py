#!/usr/bin/env python3
"""Correio: módulo compartilhado que lê, só para leitura, a caixa de e-mail de cada pessoa quando ela autoriza, como faria um cliente de e-mail (IMAP).

Serve a todos os serviços: cada serviço registra regras (quem envia, quais palavras) e recebe só as mensagens que casam com elas; a pessoa também cria as suas
rotinas em Ajustes. O módulo nunca marca como lido, move, apaga nem envia nada (SELECT somente leitura e BODY.PEEK), nunca guarda a caixa inteira (só remetente, assunto
e um trecho curto das mensagens que viraram aviso) e nunca segue links.
Acesso: usuário e senha de aplicativo (ou a senha do provedor, quando ele aceita IMAP), guardados no cofre cifrado da própria pessoa e nunca exibidos. Só IMAP com TLS
na porta 993, em servidor público. Provedores prontos: Gmail, Outlook, iCloud, Yahoo, UOL, Zoho e qualquer servidor IMAP informado.
Regras de serviços: `registrar(funcao)`, onde funcao() devolve uma lista de `Regra` para a pessoa atual. Fonte de aviso própria: "correio".
"""
import email
import email.header
import email.message
import email.policy
import html
import imaplib
import re
import ssl
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

import studio_cidadania as cid
import studio_miner_dados as dados

CHAVE, ROTULO, INTERVALO = "correio", "Correio", timedelta(hours=3)
PROVEDORES = {
    "gmail": ("Gmail", "imap.gmail.com"),
    "outlook": ("Outlook ou Hotmail", "outlook.office365.com"),
    "icloud": ("iCloud", "imap.mail.me.com"),
    "yahoo": ("Yahoo", "imap.mail.yahoo.com"),
    "uol": ("UOL", "imap.uol.com.br"),
    "zoho": ("Zoho", "imap.zoho.com"),
    "outro": ("Outro servidor IMAP", ""),
}
MAX_CONTAS, MAX_ROTINAS = 3, 20
LIMITE_CABECALHOS, LIMITE_CORPO, LIMITE_COMPLETA, JANELA_INICIAL_DIAS = 200, 200_000, 30_000_000, 3
_CAMPOS = "FROM SUBJECT DATE MESSAGE-ID AUTHENTICATION-RESULTS"


@dataclass
class Mensagem:
    conta: str
    pasta: str
    uid: str
    mid: str
    de: str
    assunto: str
    data: str
    auth: dict
    _baixar: Callable = None
    _corpo: str = None
    _completa: Callable = None

    @property
    def endereco(self) -> str:
        m = re.search(r"[\w.+-]+@[\w.-]+", self.de.lower())
        return m.group(0) if m else ""

    @property
    def dominio(self) -> str:
        return self.endereco.split("@")[-1]

    def completa(self):
        """A mensagem inteira (com anexos) como objeto de e-mail, com a autenticação do provedor já conferida. Só para regras que precisam dos anexos."""
        return self._completa() if self._completa else None

    @property
    def corpo(self) -> str:
        if self._corpo is None:
            self._corpo = self._baixar() if self._baixar else ""
        return self._corpo


@dataclass
class Regra:
    """servico: quem registra. cabecalho(msg): decide só com remetente e assunto se vale baixar o texto. tratar(msg): devolve o alerta (dict) ou None."""
    servico: str
    cabecalho: Callable
    tratar: Callable
    rotulo: str = ""


_REGISTRO: list = []


def registrar(funcao) -> None:
    if funcao not in _REGISTRO:
        _REGISTRO.append(funcao)


# ---------- configuração ----------

def contas() -> list:
    return list(cid.cfg(CHAVE).get("contas", []))


def configurado(c: dict) -> bool:
    return bool(c.get("contas")) and any(cid.tem_segredo("correio_senha_" + x["id"]) for x in c["contas"])


def _id(provedor: str, usuario: str) -> str:
    return cid.hash_curto(provedor, usuario.lower())[:8]


def salvar(campos: dict) -> str:
    """Adiciona ou atualiza uma conta (campos provedor, usuario, senha, servidor) ou salva as rotinas (campo rotinas)."""
    c = cid.cfg(CHAVE)
    if "rotinas" in campos:
        c["rotinas"] = _ler_rotinas(campos.get("rotinas", ""))
        cid.salvar_cfg(CHAVE, c)
        return "Rotinas de e-mail salvas."
    prov = campos.get("provedor", "")
    if prov not in PROVEDORES:
        raise dados.ErroMiner("Escolha o provedor de e-mail.")
    usuario = (campos.get("usuario", "") or "").strip()
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,120}|[\w.+-]{2,80}", usuario):
        raise dados.ErroMiner("Informe o endereço de e-mail ou o usuário da conta.")
    servidor = PROVEDORES[prov][1]
    if prov == "outro":
        servidor = (campos.get("servidor", "") or "").strip().lower()
        cid.validar_url("https://" + servidor)   # só servidor público
    senha = (campos.get("senha", "") or "").replace(" ", "")
    ident = _id(prov, usuario)
    contas_ = [x for x in c.get("contas", []) if x["id"] != ident]
    if len(contas_) >= MAX_CONTAS:
        raise dados.ErroMiner(f"Conecte no máximo {MAX_CONTAS} contas de e-mail.")
    if not senha and not cid.tem_segredo("correio_senha_" + ident):
        raise dados.ErroMiner("Informe a senha de aplicativo da conta.")
    contas_.append({"id": ident, "provedor": prov, "usuario": usuario, "servidor": servidor})
    if senha:
        cid.guardar_segredos({"correio_senha_" + ident: senha})
    c["contas"] = contas_
    cid.salvar_cfg(CHAVE, c)
    return "Conta de e-mail conectada. A primeira leitura acontece na próxima rodada."


def remover(campos: dict) -> str:
    c = cid.cfg(CHAVE)
    ident = campos.get("id", "")
    antes = len(c.get("contas", []))
    c["contas"] = [x for x in c.get("contas", []) if x["id"] != ident]
    if len(c["contas"]) == antes:
        raise dados.ErroMiner("Conta não encontrada.")
    cid.guardar_segredos({"correio_senha_" + ident: ""})   # valor vazio apaga a senha do cofre
    cid.salvar_cfg(CHAVE, c)
    return "Conta removida e senha apagada."


def _ler_rotinas(texto: str) -> list:
    saida = []
    for linha in cid.lista(texto, minimo=3, maximo_item=160, maximo=MAX_ROTINAS, o_que="rotinas"):
        de, _, resto = linha.partition("|")
        palavra, _, rotulo = resto.partition("|")
        de, palavra, rotulo = de.strip().lower(), palavra.strip(), rotulo.strip()
        if not re.fullmatch(r"[\w.+-]*@?[\w.-]+\.[a-z]{2,}|[\w.+-]+@[\w.-]+", de) and de != "":
            raise dados.ErroMiner(f"Informe o remetente como endereço ou domínio, por exemplo cobranca@empresa.com.br ou empresa.com.br: {linha[:30]}.")
        if not de and not palavra:
            raise dados.ErroMiner(f"Cada rotina precisa de um remetente, de uma palavra ou dos dois: {linha[:30]}.")
        saida.append({"id": cid.hash_curto(de, palavra), "de": de, "palavra": palavra, "rotulo": cid.limpo(rotulo or palavra or de, 50)})
    return saida


# ---------- regras ----------

def _casa(de_regra: str, msg: Mensagem) -> bool:
    if not de_regra:
        return True
    return de_regra == msg.endereco or (("@" not in de_regra) and (msg.dominio == de_regra or msg.dominio.endswith("." + de_regra)))


def regras_da_pessoa() -> list:
    saida = []
    for fn in list(_REGISTRO) + [_regras_padrao]:
        try:
            saida.extend(fn() or [])
        except Exception as ex:  # noqa: BLE001 - uma regra com defeito não derruba as demais
            print("Correio: regra de serviço falhou:", type(ex).__name__, file=sys.stderr)
    return saida


def _regras_padrao() -> list:
    import studio_agendamentos
    import studio_push
    import studio_correio_regras
    regras = studio_correio_regras.regras(Regra)

    def push_cab(m):
        return m.endereco.endswith(".jus.br")

    def push_tratar(m):
        if m.auth.get("dmarc") != "pass":
            return None
        p = studio_push.analisar(m.de, m.assunto, m.corpo)
        return studio_push.alerta(p, m.mid) if p else None
    regras.append(Regra("justica", push_cab, push_tratar, "Push dos tribunais"))
    remetentes = cid.cfg("agendamentos").get("remetentes", [])
    if remetentes:
        regras.append(Regra("agendamentos", lambda m: any(_casa(r, m) for r in remetentes),
                            lambda m: studio_agendamentos.alerta_de_email(m.de, m.assunto, m.corpo, m.mid) if m.auth.get("dmarc") == "pass" else None, "Agendamentos"))
    for r in cid.cfg(CHAVE).get("rotinas", []):
        regras.append(Regra("correio", (lambda m, r=r: _casa(r["de"], m)), (lambda m, r=r: _rotina(m, r)), r["rotulo"]))
    return regras


def _rotina(m: Mensagem, r: dict):
    if r["palavra"] and not (cid.contem(m.assunto, r["palavra"]) or cid.contem(m.corpo, r["palavra"])):
        return None
    confirmado = m.auth.get("dmarc") == "pass"
    trecho = cid.trecho(m.corpo, r["palavra"], 120) if r["palavra"] else cid.limpo(m.corpo, 160)
    aviso = "" if confirmado else " O provedor não confirmou o remetente (SPF, DKIM e DMARC): trate como suspeito e não use links do e-mail."
    return {"id": f"correio:{r['id']}:{cid.hash_curto(m.mid, m.uid)}", "titulo": f"E-mail recebido: {r['rotulo']}", "nivel": "medio", "fonte": "correio",
            "resumo": (f"Chegou um e-mail de {cid.limpo(m.endereco or m.de, 80)} que casa com a sua rotina “{r['rotulo']}”. Assunto: {cid.limpo(m.assunto, 120)}. "
                       f"Trecho: {trecho} O que fazer: abra a mensagem no seu e-mail e confira o que é pedido; não use links recebidos sem conferir o endereço.{aviso}")[:1500]}


# ---------- leitura IMAP ----------

def conectar(conta: dict, senha: str):
    """Abre a conexão IMAP com TLS verificado. Substituível nos testes."""
    cid.validar_url("https://" + conta["servidor"])
    imap = imaplib.IMAP4_SSL(conta["servidor"], 993, ssl_context=ssl.create_default_context(), timeout=60)
    imap.login(conta["usuario"], senha)
    return imap


def _texto_cab(valor) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(str(valor or ""))))
    except Exception:  # noqa: BLE001
        return str(valor or "")


# trecho do identificador do servidor (antes do primeiro ";") que cada provedor usa no cabeçalho Authentication-Results que ele mesmo escreve
AUTHSERV = {"gmail": ("mx.google.com",), "outlook": ("protection.outlook.com", "outlook.com", "hotmail.com"), "icloud": ("icloud.com", "apple.com"),
            "yahoo": ("yahoo.com", "yahoo.", "mta"), "uol": ("uol.com.br",), "zoho": ("zoho.com", "zohomail")}


def autenticacao(msg, provedor: str = "gmail") -> dict:
    """Resultado de SPF, DKIM e DMARC escrito pelo próprio provedor do destinatário. Só vale o cabeçalho cujo identificador de servidor é do provedor da conta:
    cabeçalhos iguais vindos do remetente são ignorados. Provedor sem identificador conhecido (outro servidor) não confirma nada."""
    r = {"dmarc": "", "dkim": "", "spf": "", "from": ""}
    t = ""
    for h in msg.get_all("Authentication-Results", []):
        h = re.sub(r"\s+", " ", str(h)).strip()
        serv = h.split(";")[0].strip().lower()
        if any(x in serv for x in AUTHSERV.get(provedor, ())):
            t = h
            break
    if not t:
        return r
    for chave in ("dmarc", "dkim", "spf"):
        m = re.search(r"\b" + chave + r"=(\w+)", t)
        r[chave] = m.group(1).lower() if m else ""
    m = re.search(r"header\.from=([\w.-]+)", t)
    r["from"] = m.group(1).lower() if m else ""
    return r


def _corpo_texto(bruto: bytes) -> str:
    try:
        msg = email.message_from_bytes(bruto, policy=email.policy.default)
        parte = msg.get_body(preferencelist=("plain", "html"))
        t = parte.get_content() if parte is not None else ""
        if parte is not None and parte.get_content_type() == "text/html":
            t = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", t)))
    except Exception:  # noqa: BLE001
        t = ""
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+", "[link omitido]", t)).strip()[:2500]


def _pastas(imap) -> list:
    pastas = ["INBOX"]
    try:
        _, lista = imap.list()
        for linha in lista or []:
            l = linha.decode("utf-8", "replace") if isinstance(linha, bytes) else str(linha)
            if r"\Junk" in l:
                m = re.search(r'"([^"]+)"\s*$', l) or re.search(r"\s(\S+)\s*$", l)
                if m:
                    pastas.append(m.group(1))
    except Exception:  # noqa: BLE001
        pass
    return pastas


def _novas(imap, conta: dict, pasta: str):
    """UIDs ainda não vistos da pasta. Na primeira vez (ou se a pasta foi reconstruída), olha os últimos dias."""
    tipo, _ = imap.select('"%s"' % pasta, readonly=True)
    if tipo != "OK":
        return []
    chave = f"correio_{conta['id']}_{cid.hash_curto(pasta)[:6]}"
    validade = ""
    try:
        v = imap.response("UIDVALIDITY")[1]
        validade = (v[0].decode() if isinstance(v[0], bytes) else str(v[0])) if v and v[0] else ""
    except Exception:  # noqa: BLE001
        pass
    ultimo, vel = cid._ler(chave + "_uid"), cid._ler(chave + "_val")
    if ultimo.isdigit() and vel == validade:
        tipo, d = imap.uid("SEARCH", None, "UID", f"{int(ultimo) + 1}:*")
    else:
        desde = (date.today() - timedelta(days=JANELA_INICIAL_DIAS)).strftime("%d-%b-%Y")
        tipo, d = imap.uid("SEARCH", None, "SINCE", desde)
    uids = [u for u in (d[0].split() if tipo == "OK" and d and d[0] else []) if u.isdigit()]
    if ultimo.isdigit() and vel == validade:   # "n:*" sempre devolve o último existente, mesmo já visto
        uids = [u for u in uids if int(u) > int(ultimo)]
    return chave, validade, uids[-LIMITE_CABECALHOS:]


def ler_conta(conta: dict, regras: list, c, conectar_=None) -> list:
    """Alertas das mensagens novas da conta que casam com alguma regra. Só lê; atualiza a marca de leitura por pasta."""
    try:
        imap = (conectar_ or conectar)(conta, cid.segredo("correio_senha_" + conta["id"]))
    except (imaplib.IMAP4.error, OSError, ssl.SSLError, dados.ErroMiner):
        raise cid.ErroFonte(f"Não foi possível entrar na conta {conta['usuario']}: confira o usuário, a senha de aplicativo e se o acesso IMAP está ativo no provedor.")
    achados = []
    try:
        for pasta in _pastas(imap):
            r = _novas(imap, conta, pasta)
            if not r:
                continue
            chave, validade, uids = r
            for uid in uids:
                uid = uid.decode() if isinstance(uid, bytes) else uid
                tipo, partes = imap.uid("FETCH", uid, f"(BODY.PEEK[HEADER.FIELDS ({_CAMPOS})])")
                if tipo != "OK" or not partes or not isinstance(partes[0], tuple):
                    continue
                cab = email.message_from_bytes(partes[0][1], policy=email.policy.default)
                m = Mensagem(conta["id"], pasta, uid, (str(cab.get("Message-ID", "")).strip() or f"{conta['id']}-{uid}"), _texto_cab(cab.get("From")),
                             _texto_cab(cab.get("Subject")), str(cab.get("Date", "")), autenticacao(cab, conta["provedor"]))
                m._baixar = lambda u=uid: _corpo_texto(_buscar_corpo(imap, u))
                m._completa = lambda u=uid, p=conta["provedor"]: _mensagem_completa(_buscar_corpo(imap, u, LIMITE_COMPLETA), p)
                for rg in regras:
                    try:
                        if rg.cabecalho(m):
                            a = rg.tratar(m)
                            if a:
                                achados.append(a)
                    except Exception as ex:  # noqa: BLE001
                        print("Correio: regra falhou:", type(ex).__name__, file=sys.stderr)
            if uids:
                cid._gravar(**{chave + "_uid": str(max(int(u) for u in uids)), chave + "_val": validade})
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass
    return achados


class MensagemVerificada(email.message.EmailMessage):
    """E-mail cuja autenticação foi conferida por este módulo (atributo, nunca cabeçalho: o remetente não consegue forjá-lo)."""
    auth_confiavel = None


def _mensagem_completa(bruto: bytes, provedor: str):
    msg = email.message_from_bytes(bruto, policy=email.policy.default, _class=MensagemVerificada)
    msg.auth_confiavel = autenticacao(msg, provedor)
    return msg


def _buscar_corpo(imap, uid: str, limite: int = None) -> bytes:
    tipo, partes = imap.uid("FETCH", uid, f"(BODY.PEEK[]<0.{limite or LIMITE_CORPO}>)")
    if tipo == "OK" and partes and isinstance(partes[0], tuple):
        return partes[0][1]
    return b""


def executar(c) -> dict:
    conf = cid.cfg(CHAVE)
    regras = regras_da_pessoa()
    novos, erros, lidas = 0, [], 0
    for conta in conf.get("contas", []):
        if not cid.tem_segredo("correio_senha_" + conta["id"]):
            continue
        try:
            for a in ler_conta(conta, regras, c, getattr(c, "conectar", None)):
                novos += c.avisar(a)
            lidas += 1
        except cid.ErroFonte as ex:
            erros.append(str(ex))
    return {"novos": novos, "erros": erros, "parcial": lidas > 0, "resumo": f"{lidas} conta(s) lida(s)"}


def formulario(csrf: str) -> str:
    c = cid.cfg(CHAVE)
    e = lambda t: html.escape(str(t), quote=True)   # noqa: E731
    itens = "".join(f'<li>{e(PROVEDORES[x["provedor"]][0])}: {e(x["usuario"])}. <form class="acao" method="post" action="/ajustes/fontes/{CHAVE}/remover"><input type="hidden" name="csrf" value="{e(csrf)}">'
                    f'<input type="hidden" name="id" value="{e(x["id"])}"><button type="submit" aria-label="Remover a conta {e(x["usuario"])} e apagar a senha">Remover conta</button></form></li>' for x in c.get("contas", []))
    opcoes = "".join(f'<option value="{k}">{e(v[0])}</option>' for k, v in PROVEDORES.items())
    est = cid.estado(sys.modules[__name__])
    return ('<h2 id="h-correio">Correio</h2><p>Conecte o seu e-mail para o Miner vigiar mensagens e criar rotinas. A leitura é só de consulta: nada é marcado como lido, movido, apagado nem enviado, e só viram aviso as mensagens que casam com uma rotina. '
            'Use uma senha de aplicativo, que você pode revogar no provedor a qualquer momento.</p>'
            + (f"<ol>{itens}</ol>" if itens else "")
            + f'<form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}">'
            f'<p><label for="cprov">Provedor</label><br><select id="cprov" name="provedor">{opcoes}</select></p>'
            '<p><label for="cserv">Servidor IMAP (só para Outro servidor IMAP)</label><br><input id="cserv" name="servidor" type="text" autocomplete="off"></p>'
            '<p><label for="cusu">Endereço de e-mail ou usuário</label><br><input id="cusu" name="usuario" type="text" autocomplete="off"></p>'
            '<p><label for="csen">Senha de aplicativo</label><br><input id="csen" name="senha" type="password" autocomplete="new-password"></p>'
            '<button type="submit">Conectar conta</button></form>'
            f'<form method="post" action="/ajustes/fontes/{CHAVE}"><input type="hidden" name="csrf" value="{e(csrf)}">'
            '<p><label for="crot">Rotinas de e-mail (uma por linha: remetente ou domínio | palavra no assunto ou no texto | nome da rotina; a palavra e o nome são opcionais)</label><br>'
            f'<textarea id="crot" name="rotinas" rows="4" cols="40">{e(chr(10).join(r["de"] + " | " + r["palavra"] + " | " + r["rotulo"] for r in c.get("rotinas", [])))}</textarea></p>'
            '<button type="submit">Salvar rotinas</button></form>' + (f'<p class="meta" role="status">{e(est)}</p>' if est else ""))


def buscar_completas(termos: list, dias: int = 7, limite: int = 150, conectar_=None) -> list:
    """Mensagens recentes da caixa de entrada de todas as contas da pessoa que citam algum dos termos (busca do próprio servidor, só leitura), como objetos de e-mail com a
    autenticação conferida (MensagemVerificada). Para serviços que leem anexos, como o Finance. Falha de uma conta não impede as demais."""
    achadas = []
    ascii_ = [re.sub(r"[^\w ]", "", cid.sem_acento(t)) for t in termos]
    ascii_ = [t for t in ascii_ if t]
    if not ascii_:
        return []
    criterio = ""
    for t in reversed(ascii_):
        criterio = f'TEXT "{t}"' if not criterio else f'OR TEXT "{t}" {criterio}'
    desde = (date.today() - timedelta(days=max(1, min(int(dias), 365)))).strftime("%d-%b-%Y")
    for conta in contas():
        if not cid.tem_segredo("correio_senha_" + conta["id"]):
            continue
        try:
            imap = (conectar_ or conectar)(conta, cid.segredo("correio_senha_" + conta["id"]))
        except (imaplib.IMAP4.error, OSError, ssl.SSLError, dados.ErroMiner):
            continue
        try:
            if imap.select("INBOX", readonly=True)[0] != "OK":
                continue
            tipo, d = imap.uid("SEARCH", None, f"SINCE {desde} {criterio}")
            if tipo != "OK" or not d or not d[0]:
                continue
            for uid in d[0].split()[-limite:]:
                uid = uid.decode() if isinstance(uid, bytes) else uid
                bruto = _buscar_corpo(imap, uid, LIMITE_COMPLETA)
                if bruto:
                    achadas.append(_mensagem_completa(bruto, conta["provedor"]))
        except (imaplib.IMAP4.error, OSError):
            continue
        finally:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
    return achadas
