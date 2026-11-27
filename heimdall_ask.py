#!/usr/bin/env python3
"""Pergunta ao modelo pelo terminal: nuvem (gpt-oss-120b pelo gateway) se estiver ligada, senão o modelo local.

    python3 heimdall_ask.py "sua pergunta"            nuvem se STUDIO_NUVEM=1; se a nuvem falhar, cai para o modelo local
    python3 heimdall_ask.py --local "sua pergunta"    só o modelo local
    python3 heimdall_ask.py --cloud "sua pergunta"    só a nuvem (não cai para o local; avisa o erro)

Depois da resposta, uma linha diz qual modelo respondeu. Nada é guardado: a pergunta não entra em histórico.
"""
import sys

import heimdall_nuvem as nuvem
import heimdall_perguntar as perguntar

SISTEMA = "Você é o assistente do Heimdall. Responda em português, de forma direta e curta, sem inventar fatos nem números."


def perguntar_ao_modelo(pergunta: str, modo: str = "", nuvem_chat=None, local_chat=None) -> tuple:
    """(resposta, quem respondeu, aviso). modo: '' (nuvem se ligada, com volta ao local), 'local' ou 'cloud'."""
    nuvem_chat = nuvem_chat or (lambda s, u: nuvem.chat(s, u, max_tokens=700, forcar=(modo == "cloud")))
    local_chat = local_chat or (lambda s, u: perguntar.chamar_local(s, u, max_tokens=700, usar_nuvem=False))
    aviso = ""
    if modo != "local" and (nuvem.ativo() or modo == "cloud"):
        try:
            return nuvem_chat(SISTEMA, pergunta), "nuvem (" + nuvem.MODELO_PADRAO.split("/")[-1] + ")", ""
        except RuntimeError as ex:
            if modo == "cloud":
                raise
            aviso = f"A nuvem falhou ({ex}); usei o modelo local."
    return local_chat(SISTEMA, pergunta), "modelo local (" + perguntar.MODELO_PADRAO + ")", aviso


def main() -> None:
    args = sys.argv[1:]
    modo = ""
    while args and args[0] in ("--local", "--cloud"):
        modo = args.pop(0)[2:]
    pergunta = " ".join(args).strip()
    if not pergunta:
        sys.exit('Escreva a pergunta, por exemplo: studio ask "o que é um índice no banco de dados?"')
    try:
        resposta, quem, aviso = perguntar_ao_modelo(pergunta, modo)
    except RuntimeError as ex:
        sys.exit(f"A nuvem não respondeu ({ex}). Tente sem --cloud para usar o modelo local, ou rode studio cloudai.")
    except Exception as ex:  # noqa: BLE001  (modelo local desligado, LiteLLM fora do ar...)
        sys.exit(f"O modelo local não respondeu ({type(ex).__name__}). Confira com studio status.")
    if aviso:
        print(aviso)
    print(resposta)
    print(f"\n[Respondeu: {quem}]")


if __name__ == "__main__":
    main()
