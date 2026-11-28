#!/usr/bin/env python3
"""Testa as fontes da Cidadania (fases 3 a 10): base, segurança, cofre, certidões, Push, DOU, MNI, rodada por pessoa e rotas da tela."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import os
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="cidadania_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
os.environ["STUDIO_NUVEM_CHAVE"] = "chave-de-teste"
os.environ["STUDIO_FERIADOS"] = "0"
import studio_banco as banco  # noqa: E402
import studio_certidoes as cert  # noqa: E402
import studio_cidadania as cid  # noqa: E402
import studio_djen as dj  # noqa: E402
import studio_dou as dou  # noqa: E402
import studio_miner_dados as d  # noqa: E402
import studio_mni as mni  # noqa: E402
import studio_push as push  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:400]})"))
    if not ok:
        falhas += 1


def cnj(seq, ano, j, tr, origem):
    base = f"{seq:07d}{ano}{j}{tr:02d}{origem:04d}"
    return f"{seq:07d}{98 - (int(base[:7] + base[7:] + '00') % 97):02d}{base[7:]}"


class Resp(io.BytesIO):
    status = 200
    headers = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def servidor(corpo):
    def abrir(req, timeout=0):
        return Resp(corpo(req) if callable(corpo) else corpo)
    return abrir


avisos = []


def pub(dado):
    novo = dado["id"] not in {a["id"] for a in avisos}
    if novo:
        avisos.append(dado)
    return {"novo": novo}


def ctx(hoje=date(2026, 11, 28), **kw):
    return cid.Contexto(hoje=hoje, publicar=pub, dormir=lambda s: None, **kw)


# --- base e segurança
for url in ("http://exemplo.gov.br/x", "https://127.0.0.1/x", "https://localhost/x", "https://a@exemplo.gov.br/x", "https://exemplo.com/x"):
    try:
        cid.validar_url(url, ("gov.br",))
        confere("recusa " + url, False)
    except d.ErroMiner:
        confere("recusa " + url, True)
confere("aceita domínio oficial", cid.validar_url("https://www.in.gov.br/x/", ("gov.br",)) == "https://www.in.gov.br/x")
try:
    cid.http("https://127.0.0.1/", urlopen=None)
    confere("http bloqueia endereço local", False)
except cid.ErroFonte:
    confere("http bloqueia endereço local", True)

# --- cofre
cid.guardar_segredos({"mni_cpf": "12345678901", "mni_senha": "segredo-xyz"})
confere("cofre guarda e lê", cid.segredo("mni_senha") == "segredo-xyz")
confere("cofre cifrado em disco", b"segredo-xyz" not in (Path(banco.DB_DIR) / "miner_segredos.bin").read_bytes())
cid.guardar_segredos({"mni_senha": ""})
confere("cofre apaga valor vazio", not cid.tem_segredo("mni_senha"))

# --- certidões
hoje = date(2026, 11, 28)
cert.salvar({"tipo": "fgts", "emissao": "20/11/2026", "nome": "Empresa"})
cert.salvar({"tipo": "cndt", "validade": "01/11/2026", "nome": "Antiga"})
r = cert.executar(ctx())
confere("certidões: vencida e a vencer geram aviso", r["novos"] >= 2, avisos)
n = len(avisos)
cert.executar(ctx())
confere("certidões: aviso só uma vez por marco", len(avisos) == n)
confere("certidões: Prazo no resumo", any("Prazo:" in a["resumo"] for a in avisos if a["fonte"] == "certidoes"))
try:
    cert.salvar({"tipo": "fgts", "emissao": "31/02/2026"})
    confere("certidão com data inválida é recusada", False)
except d.ErroMiner:
    confere("certidão com data inválida é recusada", True)

# --- Push
num = cnj(1234, 2025, 8, 26, 100)
p = push.analisar("push@tjsp.jus.br", "Andamento", f"Processo {dj.mascara_cnj(num)} teve movimentação")
confere("push reconhece remetente oficial", bool(p) and p["numero"] == num, p)
confere("push ignora remetente comum", push.analisar("x@gmail.com", "Andamento", dj.mascara_cnj(num)) is None)
confere("push orienta tribunal conhecido", push.orientacoes([num], [])[0]["tem_push"])

# --- DOU
xml = ('<xml><article id="1" idMateria="77" pubName="DO3" artType="Edital" artCategory="Min/Orgao" pubDate="28/11/2026" numberPage="10">'
       '<body><Identifica>EDITAL 1</Identifica><Ementa>Convoca Fulano da Silva</Ementa><Texto>Fica convocado Fulano da Silva.</Texto></body></article></xml>')
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("a.xml", xml)
    z.writestr("mau.xml", '<!DOCTYPE x [<!ENTITY a "b">]><xml><article id="9"/></xml>')
itens = list(dou.artigos(buf.getvalue()))
confere("DOU lê o zip e ignora XML com ENTITY", len(itens) == 1 and itens[0]["id"] == "77", itens)
al = dou.alerta(itens[0], ["Fulano da Silva"])
confere("DOU alerta de edital é alto", al["nivel"] == "alto" and al["fonte"] == "diarios")

# --- MNI
resposta = ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><ns2:consultarProcessoResposta xmlns:ns2="x" sucesso="true" mensagem="">'
            '<processo><dadosBasicos classeProcessual="7"><orgaoJulgador nomeOrgao="1a Vara"/></dadosBasicos>'
            '<movimento dataHora="20261127101500"><movimentoLocal descricao="Juntada de petição"/></movimento>'
            '<movimento dataHora="20261120090000"><movimentoLocal descricao="Distribuído"/></movimento></processo></ns2:consultarProcessoResposta></soap:Body></soap:Envelope>')
rr = mni.interpretar(resposta.encode())
confere("MNI interpreta movimentos em ordem", rr["ok"] and rr["movimentos"][0]["nome"] == "Juntada de petição" and rr["orgao"] == "1a Vara", rr)
try:
    mni.interpretar(b'<!ENTITY x "y"><a/>')
    confere("MNI recusa ENTITY", False)
except cid.ErroFonte:
    confere("MNI recusa ENTITY", True)
dj.salvar("Fulano da Silva", "", "", dj.mascara_cnj(num))
try:
    mni.salvar({"tribunais": "tjsp=https://exemplo.com/mni", "mni_cpf": "12345678901", "mni_senha": "s3nha"})
    confere("MNI recusa domínio fora de jus.br", False)
except d.ErroMiner:
    confere("MNI recusa domínio fora de jus.br", True)
mni.salvar({"tribunais": "tjsp=https://mni.tjsp.jus.br/ws", "mni_cpf": "12345678901", "mni_senha": "s3nha"})
confere("MNI configurado", mni.configurado(cid.cfg("mni")))
chamadas = []


def tribunal(req):
    chamadas.append(req.data)
    return resposta.encode()


antes = len(avisos)
r1 = mni.executar(ctx(urlopen=servidor(tribunal)))
confere("MNI primeira consulta inicia acompanhamento", r1["novos"] == 1 and not r1["erros"], r1)
r2 = mni.executar(ctx(urlopen=servidor(tribunal)))
confere("MNI sem novidade não repete", r2["novos"] == 0)
confere("MNI não vaza a senha em aviso", all("s3nha" not in str(a) for a in avisos))
recusa = resposta.replace('sucesso="true" mensagem=""', 'sucesso="false" mensagem="Senha inválida"')
r3 = mni.executar(ctx(urlopen=servidor(recusa.encode())))
confere("MNI pausa o tribunal após recusa de credencial", any("recusou a credencial" in e for e in r3["erros"]), r3)
chamadas.clear()
mni.executar(ctx(urlopen=servidor(tribunal)))
confere("MNI não insiste enquanto em pausa", not chamadas)

# --- rodada por pessoa e falhas seguidas
class Falha:
    CHAVE, ROTULO, INTERVALO = "falha", "Fonte de teste", None

    @staticmethod
    def configurado(c):
        return True

    @staticmethod
    def executar(c):
        return {"novos": 0, "erros": ["fora do ar"]}


for i in range(3):
    cid.executar_fonte(Falha, ctx())
confere("três falhas seguidas geram aviso", any(a["id"].startswith("cid-falha:falha") for a in avisos))
os.environ["STUDIO_CIDADANIA"] = "0"
confere("interruptor desliga as fontes", not cid.ligada(cert))
os.environ["STUDIO_CIDADANIA"] = "1"
confere("todas as fontes importam", len(cid.fontes()) == 7)
confere("fontes registradas na área", all(m.CHAVE in d.AREAS["cidadania"][1] for m in cid.fontes() if m.CHAVE in ("certidoes", "legislacao", "licitacoes", "agendamentos")))

# --- legislação, licitações, diários e agendamentos: configuração, validação e rodada sem resposta
import studio_agendamentos as agd  # noqa: E402
import studio_diarios as dia  # noqa: E402
import studio_legislacao as leg  # noqa: E402
import studio_licitacoes as lic  # noqa: E402
vazio = servidor(b'{"dados": [], "data": [], "items": []}')
leg.salvar({"palavras": "licitação, proteção de dados", "camara": "1", "acompanhar": "PL 1234/2024"})
r = leg.executar(ctx(urlopen=vazio))
confere("legislação roda com resposta vazia", isinstance(r, dict) and r.get("novos", 0) == 0, r)
try:
    leg.salvar({"palavras": "lei", "sapl": "https://exemplo.com/sapl"})
    confere("SAPL só aceita leg.br", False)
except d.ErroMiner:
    confere("SAPL só aceita leg.br", True)
try:
    leg.salvar({"palavras": "lei", "acompanhar": "xyz"})
    confere("proposição inválida é recusada", False)
except d.ErroMiner:
    confere("proposição inválida é recusada", True)
try:
    lic.salvar({"palavras": "software", "cnpjs": "11111111111111"})
    confere("CNPJ inválido é recusado", False)
except d.ErroMiner:
    confere("CNPJ inválido é recusado", True)
lic.salvar({"palavras": "software", "ufs": "SP"})
r = lic.executar(ctx(urlopen=vazio))
confere("licitações rodam com resposta vazia", isinstance(r, dict) and r.get("novos", 0) == 0, r)
dia.salvar({"palavras": "convocação"})
agd.salvar({"servico": "pf", "frequencia": "dias_uteis", "nome": "Passaporte"})
r = agd.executar(ctx(urlopen=vazio))
confere("agendamentos geram o lembrete assistido", isinstance(r, dict), r)
try:
    agd.salvar({"remetentes": "xx yy"})
    confere("remetente inválido é recusado", False)
except d.ErroMiner:
    confere("remetente inválido é recusado", True)
confere("agendamentos informam domínios ao monitor de e-mail", isinstance(agd.dominios(), list))
for m in cid.fontes():
    confere("formulário de " + m.CHAVE, "csrf" in m.formulario("tok") and "tok" in m.formulario("tok"))

# --- cofre por pessoa, redirecionamento e mensagens do tribunal
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
cid.guardar_segredos({"inlabs_email": "dono@exemplo.com"})
with banco.da_pessoa("conv1"):
    confere("cofre de convidado não enxerga o do dono", not cid.tem_segredo("inlabs_email"))
    cid.guardar_segredos({"inlabs_email": "conv@exemplo.com"})
    confere("convidado guarda o próprio segredo", cid.segredo("inlabs_email") == "conv@exemplo.com")
confere("segredo do dono não foi sobrescrito", cid.segredo("inlabs_email") == "dono@exemplo.com")
h = cid._RedirecionarSeguro()
for novo in ("http://exemplo.gov.br/x", "https://127.0.0.1/x", "https://10.0.0.1/x", "https://exemplo.gov.br:8443/x"):
    try:
        h.redirect_request(urllib.request.Request("https://exemplo.gov.br/"), None, 302, "x", {}, novo)
        confere("redirecionamento recusado: " + novo, False)
    except urllib.error.URLError:
        confere("redirecionamento recusado: " + novo, True)
try:
    cid.validar_url("https://exemplo.gov.br:8443/x")
    confere("porta diferente de 443 é recusada", False)
except d.ErroMiner:
    confere("porta diferente de 443 é recusada", True)
cid.guardar_segredos({"mni_cpf": "12345678901", "mni_senha": "s3nha"})
for t in ("tjsp",):
    djen_marca = "mni_pausa_" + t
dj._gravar(**{djen_marca: ""})
msg = resposta.replace('sucesso="true" mensagem=""', 'sucesso="false" mensagem="Processo em segredo de justica, CPF 12345678901 senha s3nha"')
r4 = mni.executar(ctx(urlopen=servidor(msg.encode())))
confere("MNI sem permissão no processo não pausa o tribunal e não vaza segredo", not dj._ler(djen_marca) and all("12345678901" not in e and "s3nha" not in e for e in r4["erros"]), r4)

print("\nFALHAS:", falhas)
raise SystemExit(1 if falhas else 0)
