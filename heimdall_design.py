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
#    de 4,5:1 sobre o fundo e sobre a superfície; as linhas de borda de campos e tabelas, 3:1 (teste_design.py confere).
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
a{color:var(--acento)}a:focus,button:focus,input:focus,select:focus,textarea:focus{outline:3px solid var(--acento);outline-offset:2px}
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
.conta{display:flex;justify-content:flex-end;padding-top:.5rem}.conta form{margin:0}.conta button{margin:0}
ul.acoes{list-style:none;padding:0}ul.acoes li{margin:.6rem 0}ul.acoes button{margin:0 .8rem 0 0;min-width:11rem}
[role=tablist]{display:flex;flex-wrap:wrap;gap:.25rem;margin:.4rem 0 1rem;border-bottom:1px solid var(--linha)}
[role=tab]{display:inline-block;padding:.5rem 1rem;min-height:""" + ALTURA_MINIMA_ALVO + """;box-sizing:border-box;color:var(--texto);text-decoration:none;border:1px solid var(--linha);border-bottom:0;background:var(--superficie)}
[role=tab][aria-selected=true]{font-weight:700;border-bottom:3px solid var(--ouro);background:var(--fundo)}
.so-leitor{position:absolute;left:-999px;width:1px;height:1px;overflow:hidden}
ul.chaves{list-style:none;padding:0}ul.chaves li{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem 1rem;margin:.4rem 0;padding:.4rem .6rem;border:1px solid var(--linha)}
button[role=switch]{margin:0;min-width:11rem;text-align:left;border:3px solid var(--erro)}button[role=switch][aria-checked=true]{border-color:var(--ok)}
button[role=switch][aria-disabled=true]{opacity:.6;cursor:progress}
fieldset.opcao{border:1px solid var(--linha);margin:.6rem 0;padding:.5rem .9rem}fieldset.opcao legend{font-weight:700;padding:0 .3rem}
fieldset.opcao label{display:inline-block;font-weight:400;margin:.2rem 1.2rem .2rem 0}
""")


def botao(rota: str, rotulo: str, params: dict = None, nome_acessivel: str = "", atual: bool = False) -> str:
    """Ação de consulta como botão (formulário GET com campos ocultos). `atual` marca a opção escolhida num grupo (aria-current)."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    ocultos = "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in (params or {}).items() if v not in (None, ""))
    rot = f' aria-label="{e(nome_acessivel)}"' if nome_acessivel else ""
    marca = ' aria-current="true"' if atual else ""
    return f'<form class="acao" method="get" action="{e(rota)}">{ocultos}<button type="submit"{rot}{marca}>{e(rotulo)}</button></form>'


def botao_js(id_: str, rotulo: str) -> str:
    """Botão que age na própria página, sem navegar (o comportamento vem de um script com nonce que escuta o id). Nunca é link."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    return f'<button type="button" id="{e(id_)}">{e(rotulo)}</button>'


def abas(itens: list, atual: str, rotulo: str = "Seções", completas: tuple = ()) -> str:
    """Abas de navegação entre páginas (ARIA tablist). Cada aba é um link: ler/ir é link. As setas movem entre as abas e Option+Shift+número
    abre a aba pelo número (o script `SCRIPT_ABAS` faz isso). `itens` é [(rota, nome)]; `atual` é a rota aberta. O painel é o <div role=tabpanel>
    que `painel_da_aba` devolve em volta do conteúdo."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    abas_ = []
    for i, (rota, nome) in enumerate(itens, 1):
        sel = rota == atual
        abas_.append(f'<a role="tab" id="aba-{i}" href="{e(rota)}" aria-selected="{"true" if sel else "false"}" tabindex="{0 if sel else -1}" '
                     f'aria-controls="painel-aba" aria-keyshortcuts="Alt+Shift+{i}"{" data-completa" if rota in completas else ""}>{e(nome)}</a>')
    return f'<div role="tablist" aria-label="{e(rotulo)}">' + "".join(abas_) + '</div><p id="aviso-abas" class="so-leitor" role="status"></p>'


def painel_da_aba(itens: list, atual: str, conteudo: str) -> str:
    i = next((n for n, (r, _) in enumerate(itens, 1) if r == atual), 1)
    return f'<div role="tabpanel" id="painel-aba" aria-labelledby="aba-{i}">{conteudo}</div>'


# Setas Esquerda/Direita, Home e End movem o foco entre as abas; Enter ou Espaço abre a aba em foco; Option+Shift+1..9 abre pelo número.
# Abrir uma aba troca só o conteúdo do painel (sem recarregar a página, o foco fica na aba e o leitor de tela ouve "<nome> aberta").
# Abas marcadas com data-completa (as que têm script próprio, como o Terminal) carregam a página inteira, e só se vai delas ou para elas assim.
# Exige nonce de script na página.
SCRIPT_ABAS = r"""
(function(){
var lista = document.querySelector('[role=tablist]'); if (!lista) { return; }
var abas = Array.prototype.slice.call(lista.querySelectorAll('[role=tab]'));
var aviso = document.getElementById('aviso-abas');
function atual(){ return lista.querySelector('[aria-selected=true]'); }
function foco(i){ abas.forEach(function(a, k){ a.tabIndex = (k === i) ? 0 : -1; }); abas[i].focus(); }
function abrir(a, empurrar){
  var de = atual(); if (a === de) { return; }
  if (a.hasAttribute('data-completa') || (de && de.hasAttribute('data-completa'))) { location.href = a.href; return; }
  fetch(a.href, {credentials: 'same-origin', headers: {'X-Heimdall-Ajax': '1'}}).then(function(r){
    if (!r.ok || /\/entrar/.test(r.url)) { throw new Error('x'); } return r.text();
  }).then(function(t){
    var d = new DOMParser().parseFromString(t, 'text/html'), novo = d.getElementById('painel-aba'), velho = document.getElementById('painel-aba');
    if (!novo || !velho) { throw new Error('x'); }
    velho.innerHTML = novo.innerHTML; velho.setAttribute('aria-labelledby', a.id);
    abas.forEach(function(x){ var s = (x === a); x.setAttribute('aria-selected', s ? 'true' : 'false'); x.tabIndex = s ? 0 : -1; });
    document.title = d.title; if (empurrar) { history.pushState({}, '', a.href); }
    if (aviso) { aviso.textContent = ''; setTimeout(function(){ aviso.textContent = a.textContent + ' aberta'; }, 50); }
  }).catch(function(){ location.href = a.href; });
}
abas.forEach(function(a){ a.addEventListener('click', function(ev){
  if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) { return; } ev.preventDefault(); abrir(a, true);
}); });
window.addEventListener('popstate', function(){ location.reload(); });
lista.addEventListener('keydown', function(ev){
  var i = abas.indexOf(document.activeElement); if (i < 0 || ev.altKey || ev.ctrlKey || ev.metaKey) { return; }
  var k = ev.key;
  if (k === 'ArrowRight') { foco((i + 1) % abas.length); }
  else if (k === 'ArrowLeft') { foco((i - 1 + abas.length) % abas.length); }
  else if (k === 'Home') { foco(0); }
  else if (k === 'End') { foco(abas.length - 1); }
  else if (k === ' ') { abas[i].click(); }
  else { return; }
  ev.preventDefault();
});
document.addEventListener('keydown', function(ev){
  if (ev.isComposing || !ev.altKey || !ev.shiftKey || ev.ctrlKey || ev.metaKey) { return; }
  var m = /^Digit([1-9])$/.exec(ev.code); if (!m) { return; }
  var a = abas[parseInt(m[1], 10) - 1]; if (a) { ev.preventDefault(); a.click(); }
});
})();
"""
