#!/usr/bin/env python3
"""Painel de saúde do Heimdall (health.heimdall-ai.tech): lê o banco pessoal e mostra, em texto e tabelas bons para
leitor de tela, as análises do heimdall_saude.py: como você está agora, tendências, sono, atividade, recuperação, coração,
ECG, treinos, sintomas/humor/medicamentos, o relatório da semana, o diário dos últimos dias e o estado dos dados
(para você ver se a exportação contínua do iPhone está chegando).

Somente leitura: o painel nunca grava nada no banco.

Segurança (os dados de saúde podem ficar acessíveis de fora, então tem as mesmas camadas dos outros painéis):
  1. Escuta só em 127.0.0.1. O acesso de fora vem do túnel Cloudflare.
  2. Entrada com a senha e o código de 6 dígitos do Heimdall Cloud (python3 heimdall_acesso.py --tudo).
  3. Limite de tentativas por endereço e global, sessão em cookie HttpOnly e SameSite=Strict.
  4. Só atende os nomes de site permitidos (HEIMDALL_SAUDE_PAINEL_HOSTS) e manda cabeçalhos de segurança.
  5. Sem senha e sem código configurados, o painel não sobe.
  6. Nada de rota de treino, forma de onda do ECG nem dados brutos: só números agregados e as análises.

Variáveis opcionais no .env: HEIMDALL_SAUDE_PAINEL_PORT (8013), HEIMDALL_SAUDE_PAINEL_HOST (127.0.0.1),
HEIMDALL_SAUDE_PAINEL_HOSTS (health.heimdall-ai.tech,localhost,127.0.0.1).
"""
import html
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Do .env lê só as variáveis deste painel e a pasta do banco (as outras chaves não entram neste processo)."""
    try:
        linhas = (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("export "):
            linha = linha[7:]
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip()
        if not (chave.startswith("HEIMDALL_SAUDE_PAINEL_") or chave == "HEIMDALL_DB_DIR"):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import heimdall_banco as banco  # noqa: E402
import heimdall_cloud as nuvem  # noqa: E402  (login, senha, código de 6 dígitos e sessões: o mesmo do painel Cloud)
import heimdall_saude as saude  # noqa: E402  (as análises)

HOST = os.environ.get("HEIMDALL_SAUDE_PAINEL_HOST", "127.0.0.1")
try:
    PORT = max(1, int(os.environ.get("HEIMDALL_SAUDE_PAINEL_PORT", "8013")))
except ValueError:
    PORT = 8013
HOSTS_OK = {h.strip().lower() for h in os.environ.get("HEIMDALL_SAUDE_PAINEL_HOSTS", "health.heimdall-ai.tech,localhost,127.0.0.1").split(",") if h.strip()}
COOKIE = "hsaude"
PERIODOS = (7, 14, 30, 90, 180, 365)
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731

CSS = nuvem.CSS + """
body{font-size:19px;line-height:1.7;max-width:50rem}
main h1{line-height:1.25;margin-top:1rem}h2{line-height:1.3;margin:1.6rem 0 .3rem;font-size:1.25em}
.rel p{margin:.35rem 0}.aviso{border:1px solid var(--linha);padding:.7rem;margin-top:1.5rem;color:var(--suave)}
.periodos ul{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:.4rem 1rem}
.atras{color:var(--erro);font-weight:700}
"""

SECOES = [("/", "Visão geral"), ("/hoje", "Hoje"), ("/semana", "Semana"), ("/sono", "Sono"), ("/atividade", "Atividade"), ("/recuperacao", "Recuperação"),
          ("/coracao", "Coração e ECG"), ("/treinos", "Treinos"), ("/eventos", "Sintomas, humor e medicamentos"), ("/diario", "Diário"), ("/dados", "Estado dos dados")]


# ----------------------------------------------------------------------------------------
# Texto das análises -> HTML
# ----------------------------------------------------------------------------------------
def texto_html(texto: str) -> str:
    """Parágrafos em branco separam blocos; uma primeira linha curta terminada em ':' vira subtítulo."""
    saida = []
    for bloco in re.split(r"\n\s*\n", (texto or "").strip()):
        linhas = [l.strip() for l in bloco.split("\n") if l.strip()]
        if not linhas:
            continue
        if len(linhas) > 1 and linhas[0].endswith(":") and len(linhas[0]) < 90:
            saida.append(f"<h2>{e(linhas[0][:-1])}</h2>")
            linhas = linhas[1:]
        saida.append("".join(f"<p>{e(l)}</p>" for l in linhas))
    return '<div class="rel">' + "".join(saida) + "</div>"


def secao(titulo: str, texto: str) -> str:
    return (f"<h2>{e(titulo)}</h2>" + texto_html(texto)) if texto and texto.strip() else ""


AVISO_HTML = f'<p class="aviso">{e(saude.AVISO)} O painel mostra números do seu histórico no app Saúde; ele não substitui consulta nem exame.</p>'


def seletor(rota: str, dias: int, padrao: int) -> str:
    itens = []
    for d in PERIODOS:
        if d == dias:
            itens.append(f'<li><strong aria-current="true">{d} dias (selecionado)</strong></li>')
        else:
            itens.append(f'<li><a href="{e(rota)}?dias={d}">{d} dias</a></li>')
    return f'<nav class="periodos" aria-label="Período"><ul>{"".join(itens)}</ul></nav>'


def dias_de(q: dict, padrao: int) -> int:
    try:
        d = int((q.get("dias") or [padrao])[0])
    except (ValueError, TypeError):
        return padrao
    return d if d in PERIODOS else padrao


# ----------------------------------------------------------------------------------------
# Páginas
# ----------------------------------------------------------------------------------------
def pg_inicio(q: dict) -> tuple:
    dias = dias_de(q, 90)
    corpo = secao("Hoje", saude.relatorio_hoje().replace("Hoje:\n", "", 1)) + (secao("Como você está agora", saude.relatorio_estado_atual().replace("Como você está agora:\n", "", 1))
             or "<p>Ainda não há dados suficientes para comparar os últimos 7 dias. Veja o estado dos dados.</p>")
    corpo += seletor("/", dias, 90) + secao(f"Tendências ({dias} dias)", saude.relatorio_tendencias(dias).split("\n", 1)[-1])
    corpo += AVISO_HTML
    return "Visão geral", corpo


def pg_hoje(q: dict) -> tuple:
    return "Hoje", texto_html(saude.relatorio_hoje().replace("Hoje:\n", "", 1)) + '<p><a href="/dados">Ver o estado dos dados</a></p>' + AVISO_HTML


def pg_semana(q: dict) -> tuple:
    r = saude.relatorio_semanal()
    return r["titulo"], texto_html(r["audio"].replace(saude.AVISO, "").strip()) + AVISO_HTML


def pg_relatorio(titulo: str, rota: str, funcao, padrao: int, q: dict, vazio: str) -> tuple:
    dias = dias_de(q, padrao)
    txt = funcao(dias)
    return titulo, seletor(rota, dias, padrao) + (texto_html(txt) if txt else f"<p>{e(vazio)}</p>") + AVISO_HTML


def pg_coracao(q: dict) -> tuple:
    dias = dias_de(q, 90)
    corpo = seletor("/coracao", dias, 90) + secao("Frequência cardíaca", saude.relatorio_fc(dias))
    corpo += secao("ECG", saude.relatorio_ecg(max(dias, 365)).replace(saude.AVISO, "").strip())
    return "Coração e ECG", corpo + AVISO_HTML


def pg_treinos(q: dict) -> tuple:
    dias = dias_de(q, 30)
    corpo = seletor("/treinos", dias, 30) + texto_html(saude.relatorio_treinos(dias))
    cruz = saude.relatorio_cruzado(dias)
    if cruz:
        corpo += secao("Treino e recuperação", cruz)
    corpo += ("<p>O Apple Watch só registra um treino quando você inicia um no app Treino ou aceita o aviso de início. "
              "A atividade do dia a dia, sem treino, está na página Atividade.</p>")
    return "Treinos", corpo + AVISO_HTML


def pg_diario(q: dict) -> tuple:
    dias = dias_de(q, 30)
    de = saude._dias_atras(dias)
    cols = [("sono_total", "Sono"), ("passos", "Passos"), ("x:apple_exercise_time", "Exercício (min)"), ("fc_repouso", "Pulso em repouso (bpm)"), ("hrv", "HRV (ms)"),
            ("resp", "Respiração (rpm)"), ("spo2", "Oxigênio (por cento)")]
    series = {m: saude._serie_bruta(m, de) for m, _ in cols}
    todos = sorted({d for s in series.values() for d in s}, reverse=True)
    cab = "<th scope=\"col\">Dia</th>" + "".join(f'<th scope="col">{e(n)}</th>' for _, n in cols)
    linhas = []
    for d in todos:
        cel = []
        for m, _ in cols:
            v = series[m].get(d)
            cel.append("<td>" + ("" if v is None else e(saude._dur(v) if m == "sono_total" else saude._num(v, 1 if m in ("resp", "spo2") else 0))) + "</td>")
        linhas.append(f'<tr><th scope="row">{e(saude._br(d))}</th>{"".join(cel)}</tr>')
    tabela = (f'<table><caption>Valores por dia, do mais recente para o mais antigo ({len(todos)} dias com dado)</caption><thead><tr>{cab}</tr></thead><tbody>'
              + "".join(linhas) + "</tbody></table>") if linhas else "<p>Sem dados neste período.</p>"
    return "Diário", seletor("/diario", dias, 30) + tabela + AVISO_HTML


_METRICAS_ESTADO = [("passos", "Passos"), ("sono_total", "Sono"), ("fc_repouso", "Pulso em repouso"), ("hrv", "HRV"), ("resp", "Respiração no sono"),
                    ("spo2", "Oxigênio no sangue"), ("x:apple_exercise_time", "Minutos de exercício"), ("energia", "Energia ativa"),
                    ("x:walking_heart_rate_average", "Frequência ao caminhar"), ("x:vo2_max", "VO2 máx")]


def pg_dados(q: dict) -> tuple:
    hoje = datetime.now().date()
    linhas = []
    for m, nome in _METRICAS_ESTADO:
        r = saude._ler("SELECT MAX(dia) AS u, COUNT(*) AS n, MIN(dia) AS p FROM saude_diaria WHERE metrica = ?", (m,))[0]
        linhas.append((nome, r["u"], r["n"], r["p"]))
    for nome, sql in (("Frequência cardíaca por hora", "SELECT MAX(dia) AS u, COUNT(*) AS n, MIN(dia) AS p FROM fc_hora"),
                      ("ECG", "SELECT MAX(dia) AS u, COUNT(*) AS n, MIN(dia) AS p FROM ecg"),
                      ("Treinos", "SELECT MAX(dia) AS u, COUNT(*) AS n, MIN(dia) AS p FROM treinos"),
                      ("Sintomas, humor, medicamentos e avisos", "SELECT MAX(dia) AS u, COUNT(*) AS n, MIN(dia) AS p FROM saude_eventos")):
        try:
            r = saude._ler(sql)[0]
            linhas.append((nome, r["u"], r["n"], r["p"]))
        except Exception:  # noqa: BLE001
            linhas.append((nome, None, 0, None))
    corpo_t, atrasados = [], []
    for nome, u, n, p in linhas:
        if u:
            atraso = (hoje - datetime.strptime(u, "%Y-%m-%d").date()).days
            situ = "em dia" if atraso <= 1 else f"{atraso} dias sem dado novo"
            if atraso > 2:
                atrasados.append(nome)
            corpo_t.append(f'<tr><th scope="row">{e(nome)}</th><td>{e(saude._br(u))}</td><td>{n}</td><td>{e(saude._br(p))}</td>'
                           f'<td{" class=atras" if atraso > 2 else ""}>{e(situ)}</td></tr>')
        else:
            corpo_t.append(f'<tr><th scope="row">{e(nome)}</th><td>sem dado</td><td>0</td><td></td><td>nunca chegou</td></tr>')
    ult = saude._ler("SELECT MAX(atualizado) AS a FROM saude_diaria")[0]["a"]
    intro = f"<p>Última gravação na tabela diária: {e(saude._br(ult[:10]) + ult[10:]) if ult else 'nenhuma'}.</p>"
    if atrasados:
        intro += f'<p class="atras" role="alert">Sem dado novo há mais de 2 dias em: {e(", ".join(atrasados))}. Se for a exportação contínua do iPhone, confira o Health Auto Export (iPhone desbloqueado, app aberto de vez em quando, automações ativas).</p>'
    else:
        intro += '<p class="ok">As métricas principais estão chegando em dia.</p>'
    tabela = ('<table><caption>Último dia com dado por tipo</caption><thead><tr><th scope="col">Tipo</th><th scope="col">Último dia</th><th scope="col">Dias ou registros</th>'
              '<th scope="col">Primeiro dia</th><th scope="col">Situação</th></tr></thead><tbody>' + "".join(corpo_t) + "</tbody></table>")
    return "Estado dos dados", intro + tabela


ROTAS = {
    "/": pg_inicio,
    "/hoje": pg_hoje,
    "/semana": pg_semana,
    "/sono": lambda q: pg_relatorio("Sono", "/sono", saude.relatorio_sono, 90, q, "Poucos dados de sono neste período."),
    "/atividade": lambda q: pg_relatorio("Atividade", "/atividade", saude.relatorio_atividade, 90, q, "Poucos dados de atividade neste período."),
    "/recuperacao": lambda q: pg_relatorio("Recuperação", "/recuperacao", lambda d: saude.relatorio_recuperacao(max(d, 30)), 180, q,
                                           "Poucos dados para a recuperação (precisa de pelo menos 20 dias de HRV e sono)."),
    "/coracao": pg_coracao,
    "/treinos": pg_treinos,
    "/eventos": lambda q: pg_relatorio("Sintomas, humor e medicamentos", "/eventos", saude.relatorio_eventos, 30, q, "Nenhum sintoma, humor ou medicamento registrado."),
    "/diario": pg_diario,
    "/dados": pg_dados,
}


def pagina(titulo: str, corpo: str, sess: dict = None, atual: str = "") -> bytes:
    nav = ""
    if sess:
        itens = "".join(f'<li><a href="{e(r)}"' + (' aria-current="page"' if r == atual else "") + f">{e(n)}</a></li>" for r, n in SECOES)
        nav = ('<nav aria-label="Principal"><ul>' + itens + '<li><form class="linha" method="post" action="/sair">'
               f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form></li></ul></nav>')
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall Saúde</title>{nuvem.ICONE}<style>{CSS}</style></head><body>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Heimdall Saúde", nav)}'
            f'<main id="principal"><h1>{e(titulo)}</h1>{corpo}</main></body></html>').encode("utf-8")


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo)


# ----------------------------------------------------------------------------------------
# Servidor
# ----------------------------------------------------------------------------------------
class Painel(BaseHTTPRequestHandler):
    server_version = "HeimdallSaude"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s %s\n" % (time.strftime("%H:%M:%S"), self.address_string(), (fmt % args).split("?")[0]))

    def _ip(self) -> str:
        return (self.headers.get("CF-Connecting-IP") or self.client_address[0]).strip()[:64]

    def _https(self) -> bool:
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https") or ("https" in self.headers.get("Cf-Visitor", ""))

    def _enviar(self, status: int, corpo: bytes, tipo: str = "text/html; charset=utf-8", extra: list = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src data:; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _ir(self, destino: str, extra: list = None) -> None:
        self._enviar(303, b"", extra=[("Location", destino)] + (extra or []))

    def _sessao(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            return None, None
        m = c.get(COOKIE)
        token = m.value if m else ""
        return token, nuvem.sessao_valida(token)

    def _cookie(self, token: str, apagar: bool = False) -> tuple:
        v = f"{COOKIE}={'' if apagar else token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if apagar else nuvem.SESSAO_SEG}"
        if self._https():
            v += "; Secure"
        return ("Set-Cookie", v)

    def do_GET(self):  # noqa: N802
        self._despachar("GET")

    def do_POST(self):  # noqa: N802
        self._despachar("POST")

    def do_HEAD(self):  # noqa: N802
        self._despachar("GET")

    def _despachar(self, metodo: str) -> None:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host not in HOSTS_OK:
            self._enviar(421, b"Host nao permitido", "text/plain; charset=utf-8")
            return
        url = urlparse(self.path)
        rota, q = url.path, parse_qs(url.query)
        if rota == "/saude":
            self._enviar(200, b"ok", "text/plain; charset=utf-8")
            return
        sess = None
        try:
            if rota == "/entrar":
                self._entrar(metodo)
                return
            token, sess = self._sessao()
            if not sess:
                self._ir("/entrar")
                return
            if metodo == "POST":
                if rota != "/sair":
                    self._enviar(405, pagina("Não permitido", "<p>Este painel é somente de leitura.</p>", sess))
                    return
                n = min(int(self.headers.get("Content-Length") or 0), 4096)
                campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}
                if not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
                    self._enviar(403, pagina("Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess))
                    return
                with nuvem._lock:
                    nuvem._sessoes.pop(token, None)
                self._ir("/entrar", [self._cookie("", apagar=True)])
                return
            funcao = ROTAS.get(rota)
            if not funcao:
                self._enviar(404, pagina("Não encontrei", '<p>Esta página não existe.</p><p><a href="/">Voltar à visão geral</a></p>', sess))
                return
            titulo, corpo = funcao(q)
            self._enviar(200, pagina(titulo, corpo, sess, rota))
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            self._enviar(500, pagina("Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p><p><a href="/">Voltar</a></p>', sess))

    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            self._enviar(200, pg_entrar())
            return
        ip = self._ip()
        if nuvem.login_bloqueado(ip):
            self._enviar(429, pg_entrar("Tentativas demais. Aguarde 15 minutos e tente de novo."), extra=[("Retry-After", "900")])
            return
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True).items()}
        senha_ok = nuvem.confere_senha(campos.get("senha", "")[:200], nuvem.SENHA_HASH)
        passo = nuvem.totp_contador(nuvem.TOTP_SEGREDO, campos.get("codigo", ""))
        if not (senha_ok and passo is not None and nuvem.usar_contador(passo)):
            nuvem.registrar_falha(ip)
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} login recusado de {ip}\n")
            self._enviar(401, pg_entrar("Senha ou código incorretos."))
            return
        token, _ = nuvem.nova_sessao()
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} login aceito de {ip}\n")
        self._ir("/", [self._cookie(token)])


def main() -> None:
    if not nuvem.SENHA_HASH or not nuvem.TOTP_SEGREDO:
        sys.exit("Sem senha e código configurados o painel de saúde não sobe. Rode: python3 heimdall_acesso.py --tudo")
    banco.iniciar()
    srv = ThreadingHTTPServer((HOST, PORT), Painel)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Saúde em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(HOSTS_OK))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
