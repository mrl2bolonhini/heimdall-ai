"""Heimdall Design: o padrão de interface igual em todos os sites do Heimdall.

Regra de ouro (feita para leitor de tela e teclado):
  - LINK leva a outro lugar para LER: menu, "Voltar", o nome de um item em lista ou tabela, "Leia mais", links dentro de texto.
  - BOTÃO faz uma AÇÃO ou COMANDO, mesmo quando o resultado é abrir outra página: baixar, atualizar, continuar, confirmar,
    alterar, classificar, importar, trocar visão ou período, paginar, "Ver todos...", "Ver resultado".

Um botão de comando que só consulta (GET) é um formulário com um botão, o que funciona sem JavaScript e é lido como botão.
Botões repetidos numa lista levam nome acessível com o item ("Alterar categoria de Mercado"), para o leitor de tela distinguir.
A paginação é do heimdall_paginacao.py (botões), igual no News, Notas e Finance.
"""
import html

# ---------------------------------------------------------------------------------------------------------------------
# 1. CORES (fonte única). Claro e escuro seguem o sistema (prefers-color-scheme). Todo texto precisa de contraste mínimo
#    de 4,5:1 sobre o fundo e sobre a superfície; as linhas de borda de campos e tabelas, 3:1 (tests/design/teste_design.py confere).
#    Nunca use cor sozinha para dizer algo: sempre junto com texto ("Erro: ...").
# ---------------------------------------------------------------------------------------------------------------------
CORES_CLARO = {"fundo": "#f3f6fc", "superficie": "#ffffff", "texto": "#0c1530", "suave": "#46557a", "linha": "#7a87a6",
               "acento": "#0a58ad", "erro": "#a30000", "ok": "#0a6b2d", "ouro": "#ffc107", "sclera": "#ffffff", "pupila": "#0c1530"}
CORES_ESCURO = {"fundo": "#080d1f", "superficie": "#111a38", "texto": "#e9effc", "suave": "#a6b4d6", "linha": "#6877a0",
                "acento": "#86c5ff", "erro": "#ff9b9b", "ok": "#8be0a4", "ouro": "#ffc107", "sclera": "#e9effc", "pupila": "#080d1f"}
PAPEL_DAS_CORES = {
    "fundo": "fundo da página", "superficie": "caixas, campos, tabelas e blocos de código", "texto": "texto principal",
    "suave": "texto secundário (notas, legendas)", "linha": "bordas de campos e tabelas", "acento": "links, foco e item escolhido",
    "erro": "mensagens de erro", "ok": "mensagens de sucesso", "ouro": "marcação do item atual e detalhe da marca",
    "sclera": "olho da marca", "pupila": "olho da marca"}
# pares (texto, fundo, mínimo) que o teste confere nos dois temas
PARES_DE_CONTRASTE = [("texto", "fundo", 4.5), ("texto", "superficie", 4.5), ("suave", "fundo", 4.5), ("suave", "superficie", 4.5),
                      ("acento", "fundo", 4.5), ("acento", "superficie", 4.5), ("erro", "fundo", 4.5), ("erro", "superficie", 4.5),
                      ("ok", "fundo", 4.5), ("ok", "superficie", 4.5), ("linha", "fundo", 3.0), ("linha", "superficie", 3.0)]

# 2. TIPOGRAFIA e medidas
FONTE_TEXTO = "system-ui,sans-serif"
FONTE_TITULO = '"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif'
FONTE_CODIGO = "ui-monospace,Menlo,monospace"
TAMANHO_BASE_PX = 18
ALTURA_MINIMA_ALVO = "2.75rem"  # alvo de toque/clique confortável (cerca de 44 px)


def _tokens(c: dict) -> str:
    return ";".join(f"--{k}:{v}" for k, v in c.items())


def luminancia(hexa: str) -> float:
    r, g, b = (int(hexa.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# 3. CSS compartilhado (todos os sites usam este bloco; um site só acrescenta o que é só dele, sem trocar cores nem tamanhos)
CSS = (f":root{{color-scheme:light dark;{_tokens(CORES_CLARO)}}}\n"
       f"@media (prefers-color-scheme:dark){{:root{{{_tokens(CORES_ESCURO)}}}}}\n"
       + """body{background:var(--fundo);color:var(--texto);font:18px/1.5 system-ui,sans-serif;margin:0;padding:0 1rem 3rem;max-width:60rem;margin-inline:auto}
a{color:var(--acento)}a:focus,button:focus,input:focus,select:focus,textarea:focus,summary:focus,[role=tab]:focus,[role=tabpanel]:focus{outline:3px solid var(--acento);outline-offset:2px}
.pular{position:absolute;left:-999px}.pular:focus{left:0;background:var(--fundo);padding:.5rem}
header{margin-bottom:1rem}header::after{content:"";display:block;height:3px;background:linear-gradient(90deg,#bfe3fb 0 16.66%,#93d2fa 0 33.33%,#42a5f5 0 50%,#26c6da 0 66.66%,#1e88e5 0 83.33%,#ffc107 0)}
.marca{display:flex;align-items:center;gap:.7rem;margin:.6rem 0 .2rem}.marca svg{width:3.4rem;height:auto;flex:none}.marca strong{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;font-size:1.3em}
nav ul{list-style:none;display:flex;gap:1.25rem;flex-wrap:wrap;padding:0}nav a[aria-current=page]{font-weight:700;border-bottom:3px solid var(--ouro)}
table{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}th,td{border:1px solid var(--linha);padding:.4rem .6rem;text-align:left;vertical-align:top}
caption{text-align:left;font-weight:700;padding:.25rem 0}label{display:block;font-weight:700;margin-top:.8rem}
input[type=text],input[type=password],input[type=file],select,textarea{width:100%;box-sizing:border-box;font:inherit;padding:.4rem;background:var(--superficie);color:var(--texto);border:1px solid var(--linha)}
textarea{min-height:9rem;font-family:ui-monospace,Menlo,monospace}button{font:inherit;padding:.45rem .9rem;margin-top:.8rem;cursor:pointer}
pre{white-space:pre-wrap;word-break:break-word;border:1px solid var(--linha);background:var(--superficie);padding:.7rem;overflow:auto}
.ok{color:var(--ok);font-weight:700}.erro{color:var(--erro);font-weight:700}form.linha{display:inline}form.linha button{margin:0}
.nota{color:var(--suave)}
.terminal{height:60vh;min-height:16rem;font-size:1em;line-height:1.4;white-space:pre-wrap;overflow-wrap:anywhere}.terminal.historico{height:16rem}
.linha-acoes{display:flex;flex-wrap:wrap;gap:.2rem 1rem;align-items:flex-end}.linha-acoes form{margin:0}
form.acao{display:inline;margin:0}
.ant-prox form.acao{margin:0}
details.conta{max-width:22rem;margin:.5rem 0 0 auto;padding:.3rem .6rem;border:1px solid var(--linha);background:var(--superficie)}details.conta summary{cursor:pointer;font-weight:700}details.conta p{margin:.4rem 0}details.conta form{margin:.4rem 0}details.conta ul{margin:.4rem 0;padding-left:1.2rem}
details.grupo{border:1px solid var(--linha);margin:.5rem 0;padding:.3rem .8rem}details.grupo summary{cursor:pointer;font-weight:700;min-height:2.75rem}
ul.acoes{list-style:none;padding:0}ul.acoes li{margin:.6rem 0}ul.acoes button{margin:0 .8rem 0 0;min-width:11rem}
[role=tablist]{display:flex;flex-wrap:wrap;gap:.25rem;margin:.4rem 0 1rem;border-bottom:1px solid var(--linha)}
.abas-bloco{display:grid;grid-template-columns:repeat(5,1fr)}.abas-bloco>[role=tablist]{grid-area:1/1/2/-1;margin-bottom:.4rem}
.abas-bloco>details.mais{grid-area:1/5;align-self:end;margin:0 0 .4rem;position:relative;z-index:2}.abas-bloco>details.mais summary{display:block;width:100%;text-align:center}
.abas-bloco>details.mais ul{position:absolute;top:100%;right:0;min-width:100%;margin:0}
[role=tablist] [role=tab]{flex:1 1 auto;text-align:center}[role=tablist].l3 [role=tab]{flex-basis:calc(33.333% - .25rem)}[role=tablist].l4 [role=tab]{flex-basis:calc(25% - .25rem)}[role=tablist].l5 [role=tab]{flex-basis:calc(20% - .25rem)}
[role=tablist].com-mais [role=tab]{flex-grow:0}
@media (max-width:36rem){.abas-bloco{display:block}.abas-bloco>details.mais ul{position:static}[role=tablist] [role=tab],[role=tablist].com-mais [role=tab]{flex:1 1 calc(50% - .25rem)}}
[role=tab]{display:inline-block;padding:.5rem 1rem;min-height:""" + ALTURA_MINIMA_ALVO + """;box-sizing:border-box;color:var(--texto);text-decoration:none;border:1px solid var(--linha);border-bottom:0;background:var(--superficie)}
details.mais{display:inline-block;position:relative;margin:.4rem 0 .6rem}details.mais summary{cursor:pointer;display:inline-block;padding:.5rem 1rem;min-height:""" + ALTURA_MINIMA_ALVO + """;box-sizing:border-box;border:1px solid var(--linha);background:var(--superficie);color:var(--texto)}
details.mais ul{list-style:none;margin:.3rem 0 0;padding:.4rem .8rem;border:1px solid var(--linha);background:var(--superficie)}details.mais li{margin:.2rem 0}details.mais a{display:inline-block;padding:.3rem 0;min-height:""" + ALTURA_MINIMA_ALVO + """}
[role=tab][aria-selected=true]{font-weight:700;border-bottom:3px solid var(--ouro);background:var(--fundo)}
[role=tablist].subabas{border-bottom:0;margin:.2rem 0 1rem}.subabas [role=tab]{border:1px solid var(--linha);border-radius:.4rem;background:transparent;font-size:.95em}.subabas [role=tab][aria-selected=true]{font-weight:700;border:2px solid var(--ouro);background:var(--superficie)}
[hidden]{display:none !important}
.campo-segredo{display:inline-flex;gap:.4rem;align-items:center}.rodape{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--linha)}.rodape form{margin:0 0 1rem}
.so-leitor{position:absolute;left:-999px;width:1px;height:1px;overflow:hidden}
ul.chaves{list-style:none;padding:0}ul.chaves li{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem 1rem;margin:.4rem 0;padding:.4rem .6rem;border:1px solid var(--linha)}
button[role=switch]{margin:0;min-width:11rem;text-align:left;border:3px solid var(--erro)}button[role=switch][aria-checked=true]{border-color:var(--ok)}
button[role=switch][aria-disabled=true]{opacity:.6;cursor:progress}
fieldset.opcao{border:1px solid var(--linha);margin:.6rem 0;padding:.5rem .9rem}fieldset.opcao legend{font-weight:700;padding:0 .3rem}
fieldset.opcao label{display:inline-block;font-weight:400;margin:.2rem 1.2rem .2rem 0}.topo-conta{display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:flex-start;gap:.5rem;margin:.5rem 0 0}.topo-conta details.conta{margin:0}.topo-conta form.acao{margin:0}.acoes-topo{display:flex;flex-wrap:wrap;gap:.5rem;margin:.5rem 0}.tipo-op{margin:.6rem 0}.tipo-op p{margin:.1rem 0 0 1.8rem}
""")


def botao(rota: str, rotulo: str, params: dict = None, nome_acessivel: str = "", atual: bool = False) -> str:
    """Ação de consulta como botão (formulário GET com campos ocultos). `atual` marca a opção escolhida num grupo (aria-current)."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    ocultos = "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in (params or {}).items() if v not in (None, ""))
    rot = f' aria-label="{e(nome_acessivel)}"' if nome_acessivel else ""
    marca = ' aria-current="true"' if atual else ""
    return f'<form class="acao" method="get" action="{e(rota)}">{ocultos}<button type="submit"{rot}{marca}>{e(rotulo)}</button></form>'


def botao_post(rota: str, rotulo: str, csrf: str, params: dict = None, nome_acessivel: str = "") -> str:
    """Ação que muda algo (gera token, liga, apaga) como botão: formulário POST com o token csrf em campo oculto. Nunca é link nem GET."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    ocultos = f'<input type="hidden" name="csrf" value="{e(csrf)}">' + "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in (params or {}).items() if v not in (None, ""))
    rot = f' aria-label="{e(nome_acessivel)}"' if nome_acessivel else ""
    return f'<form class="acao" method="post" action="{e(rota)}">{ocultos}<button type="submit"{rot}>{e(rotulo)}</button></form>'


def botao_js(id_: str, rotulo: str) -> str:
    """Botão que age na própria página, sem navegar (o comportamento vem de um script com nonce que escuta o id). Nunca é link."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    return f'<button type="button" id="{e(id_)}">{e(rotulo)}</button>'


MAX_ABAS = 9   # Option+Shift+1 a 9 abrem as 9 primeiras abas; as demais ficam no menu Mais (Option+Shift+0)


def por_linha(n: int) -> int:
    """Abas por linha: até 5 cabem numa linha; de 6 a 9 as duas linhas ficam equilibradas (6 = 3+3, 7 = 4+3, 8 = 4+4, 9 = 5+4); com mais de 9 são 5 + 4 e o menu Mais
    ocupa o quinto lugar da segunda linha."""
    return n if n <= 5 else (5 if n > MAX_ABAS else (n + 1) // 2)


def abas(itens: list, atual: str, rotulo: str = "Seções", completas: tuple = ()) -> str:
    """Abas de navegação entre páginas (ARIA tablist). Cada aba é um link: ler/ir é link. As setas movem entre as abas e Option+Shift+número
    abre a aba pelo número (o script `SCRIPT_ABAS` faz isso). `itens` é [(rota, nome)]; `atual` é a rota aberta. O painel é o <div role=tabpanel>
    que `painel_da_aba` devolve em volta do conteúdo.
    Com mais de 9 itens, as 9 primeiras são abas e as outras vão para o menu Mais (um <details>, que funciona sem JavaScript), aberto por
    Option+Shift+0; os itens do Mais são links comuns (abrem a página inteira)."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    abas_, extras = [], []
    for i, (rota, nome) in enumerate(itens, 1):
        sel = rota == atual
        if i > MAX_ABAS:
            extras.append(f'<li><a id="aba-{i}" href="{e(rota)}"{" aria-current=\"page\"" if sel else ""}>{e(nome)}</a></li>')
            continue
        abas_.append(f'<a role="tab" id="aba-{i}" href="{e(rota)}" aria-selected="{"true" if sel else "false"}" tabindex="{0 if sel else -1}" '
                     f'aria-controls="painel-aba"{" data-completa" if rota in completas else ""}>{e(nome)}</a>')
    n_abas = min(len(itens), MAX_ABAS)
    dicas = f'<span id="atalho-abas" hidden>Atalho: Option Shift 1 a {n_abas}</span>' if n_abas > 1 else (f'<span id="atalho-abas" hidden>Atalho: Option Shift 1</span>' if n_abas else "")
    if abas_ and not any('aria-selected="true"' in a for a in abas_):   # a aba aberta está no Mais: a primeira continua alcançável pelo Tab
        abas_[0] = abas_[0].replace('tabindex="-1"', 'tabindex="0"', 1)
    mais = ""
    if extras:
        atual_extra = next((n for r, n in itens[MAX_ABAS:] if r == atual), "")
        titulo = f"Mais, aba aberta: {atual_extra}" if atual_extra else "Mais"
        mais = (f'<details class="mais" id="mais"{" data-atual" if atual_extra else ""}><summary>{e(titulo)}</summary>'
                f'<ul aria-label="Outras abas">{"".join(extras)}</ul></details><span id="atalho-mais" hidden>Atalho: Option Shift 0</span>')
    classe = f"l{por_linha(len(itens))}" + (" com-mais" if extras else "")
    return (f'<div class="abas-bloco"><div role="tablist" class="{classe}" aria-label="{e(rotulo)}"{' aria-describedby="atalho-abas"' if dicas else ""}>' + "".join(abas_)
            + f'</div>{mais}{dicas}<p id="aviso-abas" class="so-leitor" role="status"></p></div>')


def painel_da_aba(itens: list, atual: str, conteudo: str, foco: bool = True) -> str:
    """O painel da aba aberta. `foco`: parada do Tab (tabindex=0); fica False quando o painel começa com subabas, que já são a primeira parada dentro dele."""
    i = next((n for n, (r, _) in enumerate(itens, 1) if r == atual), 1)
    # tabindex=0: o Tab que sai da aba cai no painel (padrão ARIA das abas). Sem isso, em navegador que pula links no Tab (Safari por padrão)
    # a aba era a última parada e o foco voltava ao menu Conta.
    return f'<div role="tabpanel" id="painel-aba" aria-labelledby="aba-{i}"{" tabindex=\"0\"" if foco else ""}>{conteudo}</div>'


def subabas(itens: list, atual: str, rotulo: str = "Subseções", completas: tuple = ()) -> str:
    """Subabas: um segundo nível de abas dentro do painel de uma aba (ex.: Extratos > Transações, Pagamentos futuros, Boletos). Mesmo padrão das abas
    (links com role=tab, uma parada do Tab, setas, Home e End), com data-nivel=2; Option+Shift+seta direita ou esquerda passa para a próxima ou a anterior.
    As subabas trocam só o painel interno (`painel_da_subaba`); a aba de cima continua onde está. `itens` é [(rota, nome)]."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    tabs = []
    for i, (rota, nome) in enumerate(itens, 1):
        sel = rota == atual
        tabs.append(f'<a role="tab" id="subaba-{i}" href="{e(rota)}" aria-selected="{"true" if sel else "false"}" tabindex="{0 if sel else -1}" '
                    f'aria-controls="painel-subaba"{" data-completa" if rota in completas else ""}>{e(nome)}</a>')
    if tabs and not any('aria-selected="true"' in t for t in tabs):
        tabs[0] = tabs[0].replace('tabindex="-1"', 'tabindex="0"', 1)
    return (f'<div role="tablist" class="subabas l{por_linha(len(itens))}" data-nivel="2" aria-label="{e(rotulo)}" aria-describedby="atalho-subabas">' + "".join(tabs)
            + '</div><span id="atalho-subabas" hidden>Atalho: Option Shift seta para a direita ou para a esquerda</span>')


def painel_da_subaba(itens: list, atual: str, conteudo: str) -> str:
    i = next((n for n, (r, _) in enumerate(itens, 1) if r == atual), 1)
    return f'<div role="tabpanel" id="painel-subaba" aria-labelledby="subaba-{i}" tabindex="0">{conteudo}</div>'


def com_subabas(itens: list, atual: str, conteudo: str, rotulo: str = "Subseções", completas: tuple = ()) -> str:
    """As subabas e o painel interno com o conteúdo, para ir dentro de `com_abas(..., foco=False)`."""
    return subabas(itens, atual, rotulo, completas) + painel_da_subaba(itens, atual, conteudo)


# Setas Esquerda/Direita, Home e End movem o foco entre as abas; Enter ou Espaço abre a aba em foco; Option+Shift+1..9 abre pelo número.
# Abrir uma aba troca só o conteúdo do painel (sem recarregar a página, o foco fica na aba e o leitor de tela ouve "<nome> aberta").
# Abas marcadas com data-completa (as que têm script próprio, como o Terminal) carregam a página inteira, e só se vai delas ou para elas assim.
# Exige nonce de script na página.
_BASE_AJUDA = []


def base_ajuda() -> str:
    """Endereço do Heimdall Account, onde ficam a ajuda, o suporte e as políticas que o rodapé de todo serviço liga."""
    if not _BASE_AJUDA:
        try:
            import heimdall_usuarios as _u
            _BASE_AJUDA.append("https://" + _u.host_publico("account"))
        except Exception:  # noqa: BLE001
            _BASE_AJUDA.append("https://account.heimdall-ai.tech")
    return _BASE_AJUDA[0]


def rodape(extra: str = "", servico: str = "") -> str:
    """Fim de toda página: `extra` (botões de ação, se houver), os links de Ajuda e suporte, Termos de Uso e Privacidade, e o link para o topo, para o leitor de tela
    não ficar num final abrupto. `servico` é a chave do serviço (finance, saude, notas...): a Ajuda abre já nas perguntas dele.
    O link do topo leva tabindex=0 para ser parada do Tab também onde o navegador pula links (Safari por padrão): é o fim do percurso por Tab."""
    b = base_ajuda()
    q = f"?servico={servico}" if servico else ""
    links = (f'<nav aria-label="Ajuda e informações"><ul><li><a href="{b}/ajuda{q}">Ajuda e suporte</a></li>'
             f'<li><a href="{b}/termos-de-uso">Termos de Uso</a></li><li><a href="{b}/privacidade">Privacidade</a></li></ul></nav>')
    return f'<footer class="rodape">{extra}{links}<p><a href="#topo" tabindex="0">Voltar para o topo</a></p></footer>'


def topo() -> str:
    """Âncora do "Voltar para o topo" do rodapé: o foco vai para o começo da página e o leitor de tela lê onde está."""
    return '<div id="topo" tabindex="-1" role="group" aria-label="Início da página"></div>'


def nav_abas(itens: list, atual: str, rotulo: str = "Seções", completas: tuple = ()) -> str:
    """Navegação principal de um serviço: as abas do Heimdall Design (no lugar de menu lateral ou lista de links)."""
    return '<nav aria-label="Principal">' + abas(itens, atual, rotulo, completas) + "</nav>"


def com_abas(itens: list, atual: str, conteudo: str, foco: bool = True) -> str:
    """Conteúdo da página dentro do painel da aba aberta (o que o SCRIPT_ABAS troca ao mudar de aba). Com subabas, passe foco=False."""
    return painel_da_aba(itens, atual, conteudo, foco)


def script(extra: str = "") -> str:
    """<script> com as abas (setas, Home, End e Option+Shift+número) e `extra`, com um nonce novo. Use `csp()` ao enviar a página."""
    import secrets
    return f'<script nonce="{secrets.token_urlsafe(16)}">{SCRIPT_ABAS}{SCRIPT_DETALHES}{SCRIPT_PERGUNTAR}{extra}</script>'


def csp(base: str, corpo: bytes, conectar: bool = True) -> str:
    """Política de segurança do serviço (`base`, sem script) e, se a página traz o <script nonce=...> do `script()`, a permissão só para esse nonce."""
    import re
    m = re.search(rb'<script nonce="([A-Za-z0-9_-]+)"', corpo or b"")
    if not m:
        return base
    nonce = m.group(1).decode()
    if "script-src " in base:
        base = base.replace("script-src ", f"script-src 'nonce-{nonce}' ", 1)
    else:
        base = f"script-src 'nonce-{nonce}'; " + base
    if conectar:   # trocar de aba busca a página (fetch); com uma aba só (Games) não há troca, e o connect-src fica como está
        if "connect-src " in base:
            base = re.sub(r"connect-src [^;]*", "connect-src 'self'", base, count=1)
        else:
            base = "connect-src 'self'; " + base
    return base


def aba_da_rota(rota: str, itens: list, aliases: dict = None) -> str:
    """Rota da aba que cobre `rota`: a própria, o alias (ex.: /transacao/5 -> /transacoes) ou a mais longa que for prefixo."""
    rota = rota.split("?")[0]
    if rota in {r for r, _ in itens}:
        return rota
    for pref, alvo in (aliases or {}).items():
        if rota.startswith(pref):
            return alvo
    cand = [r for r, _ in itens if r != "/" and rota.startswith(r + "/")]
    return max(cand, key=len) if cand else ""


# Mostrar/ocultar valor secreto: o botão ao lado do campo troca type=password por text. Delegado no documento.
SCRIPT_SEGREDO = r"""
document.addEventListener('click', function (ev) {
  var b = ev.target.closest ? ev.target.closest('button[data-mostrar]') : null;
  if (!b) return;
  var campo = document.getElementById(b.getAttribute('data-mostrar'));
  if (!campo) return;
  var ver = campo.type === 'password';
  campo.type = ver ? 'text' : 'password';
  b.setAttribute('aria-pressed', ver ? 'true' : 'false');
  b.textContent = ver ? 'Ocultar' : 'Mostrar';
});
"""

SCRIPT_DETALHES = r"""
document.addEventListener('keydown', function (ev) {
  if (ev.key !== 'Escape' || ev.defaultPrevented) return;
  var det = ev.target && ev.target.closest ? ev.target.closest('details[open]') : null;
  if (!det) return;
  det.removeAttribute('open');
  var sum = det.querySelector('summary');
  if (sum) sum.focus();
  ev.preventDefault();
});
"""
"""Esc fecha o <details> (grupo ou menu) em que o foco está e devolve o foco ao resumo."""

SCRIPT_PERGUNTAR = r"""
(function(){
var temporizador = null, tentativas = 0, pensando = false;
function el(id){ return document.getElementById(id); }
function aplicar(texto){
  var d = new DOMParser().parseFromString(texto, 'text/html');
  var novo = d.getElementById('perguntar-resp'), n_estado = d.getElementById('perguntar-estado');
  var resp = el('perguntar-resp'), estado = el('perguntar-estado');
  if (!novo || !n_estado || !resp || !estado) { return null; }
  if (resp.innerHTML !== novo.innerHTML) { resp.innerHTML = novo.innerHTML; }
  var agora = n_estado.getAttribute('data-pensando') === '1';
  if (agora) {
    if (!pensando || !estado.textContent) { estado.textContent = n_estado.textContent; }
  } else if (pensando) {
    var ult = novo.querySelectorAll('article'); ult = ult.length ? ult[ult.length - 1] : null;
    estado.textContent = ult ? 'Resposta pronta. ' + ult.textContent.replace(/\s+/g, ' ').trim() : '';
  }
  estado.setAttribute('data-pensando', agora ? '1' : '0');
  pensando = agora;
  return agora;
}
function conferir(){
  var resp = el('perguntar-resp'); if (!resp) { parar(); return; }
  tentativas += 1; if (tentativas > 400) { parar(); return; }
  fetch(resp.getAttribute('data-volta') || location.pathname, {credentials: 'same-origin', headers: {'X-Heimdall-Ajax': '1'}})
    .then(function(r){ if (!r.ok || /\/entrar/.test(r.url)) { throw new Error('x'); } return r.text(); })
    .then(function(t){ if (aplicar(t) === false) { parar(); } })
    .catch(function(){ parar(); });
}
function parar(){ if (temporizador) { clearInterval(temporizador); temporizador = null; } }
function acompanhar(){ if (temporizador) { return; } tentativas = 0; temporizador = setInterval(conferir, 3000); }
window.hdPerguntar = function(){
  var estado = el('perguntar-estado'); parar();
  pensando = !!estado && estado.getAttribute('data-pensando') === '1';
  if (pensando) { acompanhar(); }
};
document.addEventListener('submit', function(ev){
  var f = ev.target;
  if (!f || !f.hasAttribute || !f.hasAttribute('data-perguntar') || !window.fetch || !window.URLSearchParams) { return; }
  if (ev.submitter && ev.submitter.hasAttribute('formaction')) { return; }
  var campo = f.querySelector('[data-pergunta]'), estado = el('perguntar-estado');
  if (!campo || !estado) { return; }
  ev.preventDefault();
  if (!campo.value.trim()) { estado.textContent = 'Escreva a pergunta antes de enviar.'; campo.focus(); return; }
  var dados = new URLSearchParams(new FormData(f));
  estado.textContent = 'Pergunta enviada. O modelo está pensando; a resposta aparece aqui sozinha.';
  fetch(f.action, {method: 'POST', credentials: 'same-origin', headers: {'X-Heimdall-Ajax': '1', 'Content-Type': 'application/x-www-form-urlencoded'}, body: dados.toString()})
    .then(function(r){ if (!r.ok || /\/entrar/.test(r.url)) { throw new Error('x'); } return r.text(); })
    .then(function(t){ campo.value = ''; pensando = true; estado.setAttribute('data-pensando', '1'); aplicar(t); acompanhar(); })
    .catch(function(){ f.submit(); });
});
document.addEventListener('keydown', function(ev){
  if (ev.isComposing) { return; }
  if (ev.altKey && ev.shiftKey && !ev.ctrlKey && !ev.metaKey && ev.code === 'KeyP') {   // Option+Shift+P leva ao campo da pergunta
    var c = document.querySelector('[data-pergunta]');
    if (c) { ev.preventDefault(); c.scrollIntoView({block: 'center'}); c.focus(); }
    return;
  }
  if (ev.key === 'Enter' && !ev.shiftKey && !ev.altKey && !ev.ctrlKey && !ev.metaKey && ev.target && ev.target.hasAttribute && ev.target.hasAttribute('data-envia')) {
    ev.preventDefault();   // Enter envia; Shift+Enter pula linha
    var f = ev.target.form;
    if (f) { if (f.requestSubmit) { f.requestSubmit(); } else { f.submit(); } }
  }
});
window.hdPerguntar();
})();
"""

SCRIPT_ABAS = r"""
(function(){
var ALVO = {'1': 'painel-aba', '2': 'painel-subaba'};
var aviso = document.getElementById('aviso-abas');
function nivel(lista){ return lista.getAttribute('data-nivel') || '1'; }
function listaDe(el){ return el && el.closest ? el.closest('[role=tablist]') : null; }
function abasDe(lista){ return Array.prototype.slice.call(lista.querySelectorAll('[role=tab]')); }
function atual(lista){ return lista.querySelector('[aria-selected=true]'); }
function foco(lista, i){ var as = abasDe(lista); as.forEach(function(a, k){ a.tabIndex = (k === i) ? 0 : -1; }); as[i].focus(); }
function principal(){ return document.querySelector('[role=tablist]:not([data-nivel])'); }
function abrir(a, empurrar){
  var lista = listaDe(a), de = lista && atual(lista); if (!lista || a === de) { return; }
  if (!de || a.hasAttribute('data-completa') || de.hasAttribute('data-completa')) { location.href = a.href; return; }
  var id = ALVO[nivel(lista)];
  fetch(a.href, {credentials: 'same-origin', headers: {'X-Heimdall-Ajax': '1'}}).then(function(r){
    if (!r.ok || /\/entrar/.test(r.url)) { throw new Error('x'); } return r.text();
  }).then(function(t){
    var d = new DOMParser().parseFromString(t, 'text/html'), novo = d.getElementById(id), velho = document.getElementById(id);
    if (!novo || !velho) { throw new Error('x'); }
    velho.innerHTML = novo.innerHTML;
    ['aria-labelledby', 'tabindex'].forEach(function(k){ if (novo.hasAttribute(k)) { velho.setAttribute(k, novo.getAttribute(k)); } else { velho.removeAttribute(k); } });
    abasDe(lista).forEach(function(x){ var s = (x === a); x.setAttribute('aria-selected', s ? 'true' : 'false'); x.tabIndex = s ? 0 : -1; });
    if (window.hdPerguntar) { window.hdPerguntar(); }
    document.title = d.title; if (empurrar) { history.pushState({}, '', a.href); }
    if (aviso) { aviso.textContent = ''; setTimeout(function(){ aviso.textContent = a.textContent + ' aberta'; }, 50); }
  }).catch(function(){ location.href = a.href; });
}
document.addEventListener('click', function(ev){
  var a = ev.target && ev.target.closest ? ev.target.closest('a[role=tab]') : null; if (!a) { return; }
  if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) { return; } ev.preventDefault(); abrir(a, true);
});
window.addEventListener('popstate', function(){ location.reload(); });
document.addEventListener('keydown', function(ev){
  var lista = listaDe(ev.target); if (!lista || ev.altKey || ev.ctrlKey || ev.metaKey) { return; }
  var as = abasDe(lista), i = as.indexOf(ev.target); if (i < 0) { return; }
  var k = ev.key;
  if (k === 'ArrowRight') { foco(lista, (i + 1) % as.length); }
  else if (k === 'ArrowLeft') { foco(lista, (i - 1 + as.length) % as.length); }
  else if (k === 'Home') { foco(lista, 0); }
  else if (k === 'End') { foco(lista, as.length - 1); }
  else if (k === ' ') { as[i].click(); }
  else { return; }
  ev.preventDefault();
});
document.addEventListener('keydown', function(ev){
  if (ev.isComposing || !ev.altKey || !ev.shiftKey || ev.ctrlKey || ev.metaKey) { return; }
  if (ev.code === 'ArrowRight' || ev.code === 'ArrowLeft') {   // subabas: próxima ou anterior (fora de campos de texto, onde Option+Shift+seta seleciona texto)
    var alvo = ev.target, tag = alvo && alvo.tagName; if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (alvo && alvo.isContentEditable)) { return; }
    var sub = document.querySelector('[role=tablist][data-nivel="2"]'); if (!sub) { return; }
    var as = abasDe(sub), i = as.indexOf(atual(sub)); if (i < 0) { i = 0; }
    ev.preventDefault(); as[(i + (ev.code === 'ArrowRight' ? 1 : as.length - 1)) % as.length].click(); return;
  }
  if (ev.code === 'Digit0') {   // menu Mais: abre e põe o foco no primeiro item; de novo, fecha
    var mais = document.getElementById('mais'); if (!mais) { return; }
    ev.preventDefault();
    if (mais.open) { mais.open = false; mais.querySelector('summary').focus(); return; }
    mais.open = true; var l = mais.querySelector('a'); if (l) { l.focus(); }
    return;
  }
  var m = /^Digit([1-9])$/.exec(ev.code); if (!m) { return; }
  var top = principal(); if (!top) { return; }
  var a = abasDe(top)[parseInt(m[1], 10) - 1]; if (a) { ev.preventDefault(); a.click(); }
});
})();
"""
