"""Compatibilidade de nomes de variáveis (renomeação para StudioLibre, fase 3b).

O prefixo novo é STUDIO_; o código interno ainda lê HEIMDALL_ (nome antigo, mantido durante a transição). Quem escreve STUDIO_X no .env
tem o mesmo efeito de HEIMDALL_X, e HEIMDALL_X continua valendo. Os leitores do .env chamam `interno(nome)` para trocar STUDIO_ por HEIMDALL_.
Nomes que o Worker e o GitHub também conhecem (HEIMDALL_CFACCESS_*, HEIMDALL_R2_* etc.) só trocam na fase 4, e aceitam os dois prefixos do mesmo jeito.
No shell o mesmo efeito vem de scripts/studio_env.sh.
"""
NOVO = "STUDIO_"
ANTIGO = "HEIMDALL_"


def interno(nome: str) -> str:
    """STUDIO_X vira HEIMDALL_X (o nome que o código lê); qualquer outro nome volta igual."""
    if nome.startswith(NOVO):
        return ANTIGO + nome[len(NOVO):]
    return nome
