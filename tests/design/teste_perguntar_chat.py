#!/usr/bin/env python3
"""Testa o Perguntar no estilo de chat (resposta sozinha, acima do campo) e as abas com uma dica só para o leitor de tela.

    python3 tests/design/teste_perguntar_chat.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import time

import studio_design as design
import studio_perguntar as perguntar

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


perguntar._respostas.clear()
perguntar.guardar_resposta("d", "Primeira?", {"texto": "Um.", "avisos": []})
perguntar.guardar_resposta("d", "Segunda?", {"texto": "Dois.", "avisos": []})
h = perguntar.bloco_html("d", "tok", "/")
confere("respostas em ordem de conversa, acima do campo", h.index("Um.") < h.index("Dois.") < h.index('id="pergunta"'), h)
confere("área de respostas e estado ligados ao script", 'id="perguntar-resp" data-volta="/"' in h and 'id="perguntar-estado" role="status" data-pensando="0"' in h)
confere("sem botão de atualizar quando nada está pensando", "Atualizar respostas" not in h)
confere("o formulário é do script e o campo não tem required (evita balão de validação)", "data-perguntar" in h and "data-pergunta" in h and "required" not in h)
confere("o campo é de várias linhas, e a dica ensina o atalho e o Enter", "<textarea" in h and "data-envia" in h and "Option Shift P" in h and "Shift Enter pula linha" in h)

perguntar._tarefas.clear()
perguntar._tarefas["x"] = {"id": "x", "dono": "d", "rotulo": "pergunta", "estado": "pensando", "resultado": None, "erro": "", "inicio": time.time(), "info": "q"}
h = perguntar.bloco_html("d", "tok", "/")
confere("pensando: estado marcado e botão só para quem está sem JavaScript", 'data-pensando="1"' in h and "<noscript>" in h and "Atualizar respostas" in h.split("<noscript>")[1])
perguntar._tarefas["x"].update(estado="erro", erro="falhou")
h = perguntar.bloco_html("d", "tok", "/")
confere("erro aparece como alerta dentro da área de respostas", 'role="alert"' in h and h.index('role="alert"') < h.index('id="perguntar-estado"'))
perguntar._tarefas.clear()

s = design.SCRIPT_PERGUNTAR
confere("o script confere a resposta sozinho e anuncia no estado, sem mexer no foco", "setInterval(conferir, 3000)" in s and "Resposta pronta." in s and ".focus()" in s)
confere("Option+Shift+P leva ao campo; Enter envia e Shift+Enter não", "'KeyP'" in s and "ev.key === 'Enter' && !ev.shiftKey" in s and "requestSubmit" in s and "data-envia" in s)
confere("as abas trocadas reiniciam o acompanhamento", "window.hdPerguntar" in design.SCRIPT_ABAS)
confere("design.script() leva o script do Perguntar", "perguntar-resp" in design.script())

a = design.abas([("/", "A"), ("/b", "B"), ("/c", "C")], "/b", "Seções")
confere("abas: sem descrição por aba nem dica oculta no conjunto, e sem aviso falado ao abrir", "atalho-aba" not in a and "aria-describedby" not in a and "aviso-abas" not in a, a)
print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
