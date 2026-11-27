#!/usr/bin/env python3
"""Catálogo de tipos de estudo do Studio Learn: cada tipo traz a categoria que costuma combinar com ele, o que a IA faz, o que ela evita,
os formatos de exercício e as possibilidades futuras. É a fonte única: a tela de tipos, a criação de pastas e os prompts leem daqui.

Tipo cadastrado pelo usuário que não está aqui usa o perfil genérico: a IA estuda o material da pasta e, se faltar contexto, pergunta.
Usa só a biblioteca padrão do Python.
"""

# nome -> perfil. categoria: a sugerida (aleatorio ou sequencial). pede_idioma: o cadastro exige o idioma de estudo.
PERFIS = {
    "Idiomas": {
        "categoria": "sequencial", "pede_idioma": True,
        "resumo": "Aprender um idioma em ordem crescente, do básico ao avançado.",
        "faz": ["Lição em duas vozes: o trecho no idioma de estudo e a explicação em português.",
                "Vocabulário e gramática do nível atual, sem pular nível (A1 a C2).",
                "Exercícios de alternativas, completar a frase, tradução nos dois sentidos, ditado e leitura em voz alta."],
        "evita": ["Explicar em inglês ou no idioma de estudo o que é gramática: a explicação é sempre em português.",
                  "Misturar vocabulário de níveis acima do atual."],
        "regras": "Cada lição tem um trecho no idioma de estudo (curto, com tradução) e a explicação em português. Respeite o nível da pasta; "
                  "no modo aleatório, pergunte sobre o trecho sorteado pedindo tradução, uso da palavra ou da regra, e corrija com a forma certa.",
        "depois": "Pronúncia corrigida por voz (fase 4), revisão espaçada de vocabulário e cards diários com uma palavra e uma frase.",
    },
    "Programação": {
        "categoria": "sequencial", "pede_idioma": False,
        "resumo": "Aprender uma linguagem ou tecnologia de programação praticando.",
        "faz": ["Conceito curto, exemplo de código e exercício em seguida.",
                "Exercícios de prever o resultado, completar o código, achar o erro e escrever uma função pequena.",
                "Código lido de forma que o leitor de tela entenda: nome do símbolo por extenso quando importa (abre chaves, dois pontos)."],
        "evita": ["Exemplos longos: no máximo 15 linhas.", "Desenhar com caracteres ou tabelas."],
        "regras": "Mostre o código em bloco simples, explique linha a linha em texto corrido e peça um exercício que o aluno possa responder em texto. "
                  "No modo aleatório, pergunte o que o trecho de código faz ou por que foi escrito assim.",
        "depois": "Corrigir o código que o aluno digita, pequenos projetos em etapas e revisão dos erros mais comuns.",
    },
    "Exatas": {
        "categoria": "sequencial", "pede_idioma": False,
        "resumo": "Matemática, estatística, física, lógica: definições, método e problemas em ordem crescente.",
        "faz": ["Definição, passo a passo de um exemplo resolvido e problemas de dificuldade crescente.",
                "Fórmulas e contas ditas por extenso, para o leitor de tela e para o áudio (x ao quadrado mais dois, e não símbolos soltos).",
                "Correção que mostra onde a conta saiu do caminho."],
        "evita": ["Fórmula só em símbolo.", "Resposta numérica sem o raciocínio."],
        "regras": "Escreva as expressões por extenso e confira cada conta antes de afirmar o resultado. Se não tiver certeza da conta, diga que precisa ser conferida.",
        "depois": "Banco de problemas por nível e revisão dos tipos de erro do aluno.",
    },
    "Arquitetura e dados": {
        "categoria": "aleatorio", "pede_idioma": False,
        "resumo": "Arquitetura e engenharia de dados, serviços de nuvem (AWS), padrões e decisões de projeto.",
        "faz": ["Perguntas de cenário: dado um problema, qual serviço ou padrão e por quê.",
                "Comparação de alternativas com custo, escala, latência e manutenção.",
                "Sugestão de matérias vizinhas para ampliar a visão (modelagem, orquestração, governança, qualidade)."],
        "evita": ["Resposta sem trade-off.", "Afirmar preço ou limite de serviço sem estar no material."],
        "regras": "Prefira perguntas que pedem justificar uma escolha. Na correção, diga o que está certo, o que faltou e a decisão que um arquiteto tomaria com base no trecho.",
        "depois": "Simulados de certificação e um mapa do que já foi estudado e do que falta.",
    },
    "Filosofia": {
        "categoria": "aleatorio", "pede_idioma": False,
        "resumo": "Autores, conceitos, argumentos e objeções.",
        "faz": ["Perguntas sobre o argumento do trecho, as premissas e as objeções possíveis.",
                "Comparação entre autores e correntes.",
                "Sugestão do próximo autor ou conceito para ler."],
        "evita": ["Dar a opinião da IA como se fosse do autor.", "Resumir sem citar o trecho."],
        "regras": "Atribua cada ideia a quem a defende. Separe o que o texto diz do que é interpretação.",
        "depois": "Mapa de conceitos entre as pastas e linha do tempo dos autores.",
    },
    "Humanas": {
        "categoria": "aleatorio", "pede_idioma": False,
        "resumo": "História, sociologia, política, letras e outras ciências humanas.",
        "faz": ["Perguntas sobre causas, contexto, consequências e comparações.",
                "Datas e nomes só como estão no material.",
                "Sugestão de períodos, autores ou temas relacionados."],
        "evita": ["Inventar data, nome ou número.", "Tomar partido em tema político."],
        "regras": "Diferencie fato, interpretação e opinião. Quando o material tiver correntes diferentes, apresente as duas.",
        "depois": "Linhas do tempo e comparação entre fontes.",
    },
    "Direito": {
        "categoria": "aleatorio", "pede_idioma": False,
        "resumo": "Normas, doutrina e jurisprudência.",
        "faz": ["Perguntas de caso curto: fato, norma aplicável e conclusão.",
                "Citação exata do artigo, súmula ou julgado como aparece no material.",
                "Sugestão de temas conexos e de pontos que costumam cair em provas."],
        "evita": ["Citar artigo, número de processo ou súmula que não esteja no material.", "Dar parecer sobre caso real."],
        "regras": "É estudo, não parecer. Se a norma pode ter mudado, avise que é preciso conferir a redação vigente.",
        "depois": "Banco de questões por tema e fichamento de julgados.",
    },
    "Medicina": {
        "categoria": "aleatorio", "pede_idioma": False,
        "resumo": "Ciências médicas e da saúde, para estudo.",
        "faz": ["Perguntas de fisiopatologia, mecanismo, diagnóstico diferencial e conduta, sempre baseadas no trecho.",
                "Termos técnicos explicados em português simples.",
                "Casos clínicos curtos."],
        "evita": ["Dar conduta para o caso pessoal do aluno.", "Doses e valores que não estejam no material."],
        "regras": "É material de estudo, nunca orientação de saúde pessoal. Dose, valor de referência e protocolo só como estão no trecho, com aviso para conferir na fonte atual.",
        "depois": "Revisão espaçada de termos e simulados por especialidade.",
    },
    "Esoterismo": {
        "categoria": "aleatorio", "pede_idioma": False,
        "resumo": "Esoterismo, misticismo e simbologia, estudados como tradição e história.",
        "faz": ["Perguntas sobre símbolos, correspondências e a origem de cada ideia.",
                "Cada afirmação atribuída à tradição ou ao autor do trecho.",
                "Sugestão de textos e correntes relacionados."],
        "evita": ["Afirmar eficácia, previsão ou poder como fato.", "Misturar tradições sem avisar."],
        "regras": "Descreva o que a tradição ensina, dizendo qual é. Não afirme que funciona.",
        "depois": "Mapa de correspondências entre tradições.",
    },
    "Outro": {
        "categoria": "aleatorio", "pede_idioma": False,
        "resumo": "Qualquer assunto que não tem tipo próprio.",
        "faz": ["Perguntas sobre o trecho sorteado e correção com base nele."],
        "evita": ["Afirmar o que não está no material."],
        "regras": "Se o assunto da pasta não estiver claro, diga em uma frase o que entendeu e pergunte o que o aluno quer treinar.",
        "depois": "Perfil próprio, se o assunto se repetir.",
    },
}

GENERICO = {
    "categoria": "aleatorio", "pede_idioma": False,
    "resumo": "Tipo criado por você: a IA usa o material da pasta e, se faltar contexto, pergunta.",
    "faz": ["Perguntas sobre o trecho sorteado e correção com base nele."],
    "evita": ["Afirmar o que não está no material."],
    "regras": "Se o assunto não estiver claro, diga em uma frase o que entendeu e pergunte o que o aluno quer treinar.",
    "depois": "",
}


def _chave(nome: str) -> str:
    return " ".join((nome or "").split()).lower()


def perfil(tipo: str) -> dict:
    """Perfil do tipo (sem diferenciar maiúsculas); o genérico se não houver."""
    for k, v in PERFIS.items():
        if _chave(k) == _chave(tipo):
            return v
    return GENERICO


def categoria_sugerida(tipo: str) -> str:
    return perfil(tipo)["categoria"]


def pede_idioma(tipo: str) -> bool:
    return bool(perfil(tipo)["pede_idioma"])


def regras_para_prompt(tipo: str, categoria: str, idioma: str = "") -> str:
    p = perfil(tipo)
    partes = [f"Tipo de estudo: {tipo or 'sem tipo'}. Categoria: {categoria}.", p["regras"]]
    if p["evita"]:
        partes.append("Evite: " + " ".join(p["evita"]))
    if idioma:
        partes.append(f"Idioma de estudo: {idioma}.")
    return " ".join(partes)
