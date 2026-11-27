#!/usr/bin/env python3
"""Studio Games (games.studiolibre.io): jogos leves, feitos para leitor de tela, que rodam no navegador.

Cada jogo é HTML comum (botões, campos e listas) mais um arquivo JavaScript da pasta games/; o que acontece na partida
é dito em voz alta por uma região aria-live. Nada é gravado: o servidor só entrega as páginas.
Jogos: forca, senha (Mastermind), jogo da velha, número secreto, 2048, cinco letras, sudoku, xadrez, batalha naval, campo minado, caça-níqueis e aventuras de texto
(O Farol Apagado, A Mansão dos Relógios, O Templo Submerso, Estação Orion; as três últimas com níveis de dificuldade).

Segurança (pode ficar acessível de fora, então tem as mesmas camadas dos outros painéis):
  1. Escuta só em 127.0.0.1. O acesso de fora vem do túnel Cloudflare.
  2. Entrada com a senha e o código de 6 dígitos do Studio Lab (python3 studio_acesso.py --tudo).
  3. Limite de tentativas por endereço e global, sessão em cookie HttpOnly e SameSite=Strict.
  4. Só atende os nomes de site permitidos (STUDIO_JOGOS_HOSTS) e manda cabeçalhos de segurança.
  5. Só os arquivos .js do catálogo são entregues, e a política de conteúdo só deixa rodar script do próprio site.
  6. Sem senha e sem código configurados, o servidor não sobe.

Variáveis opcionais no .env: STUDIO_JOGOS_PORT (8014), STUDIO_JOGOS_HOST (127.0.0.1),
STUDIO_JOGOS_HOSTS (games.studiolibre.io,localhost,127.0.0.1) e STUDIO_JOGOS_EXTRAS: outros jogos que você hospeda
(só os que tenham versão em português ou permitam tradução), no formato "Nome|http://localhost:8015|descrição;Outro|https://exemplo.test|descrição".
"""
import unicodedata
import html
import os
import re
import secrets
import sys
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent
JOGOS_DIR = PROJECT_DIR / "games"


def carregar_env() -> None:
    """Do .env lê só as variáveis deste servidor (as outras chaves não entram neste processo)."""
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
        if not chave.startswith("STUDIO_JOGOS_"):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

import studio_design as design  # noqa: E402  (padrão de interface: link lê, botão age)
import studio_lab as nuvem  # noqa: E402  (login, senha, código de 6 dígitos e sessões: o mesmo do painel Lab)

HOST = os.environ.get("STUDIO_JOGOS_HOST", "127.0.0.1")
try:
    PORT = max(1, int(os.environ.get("STUDIO_JOGOS_PORT", "8014")))
except ValueError:
    PORT = 8014
HOSTS_OK = {h.strip().lower() for h in os.environ.get("STUDIO_JOGOS_HOSTS", "games.studiolibre.io,localhost,127.0.0.1").split(",") if h.strip()}
HOSTS_OK |= __import__("studio_links").hosts_padrao("games")   # domínio novo e antigo valem juntos durante a transição
COOKIE = nuvem.COOKIE
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731

NIVEIS_TXT = ["Níveis: fácil (dicas à vontade e sem limite de passos), normal (3 dicas e limite de passos folgado) e difícil (sem dicas, limite apertado e enigmas a mais). Troque o nível e use Recomeçar.",
              "Digite salvar para guardar a partida neste navegador e carregar para continuar depois. Digite objetivo, mapa, dica ou tempo quando precisar."]
# id, título, arquivo, resumo, como jogar (uma frase por item)
CATALOGO = [
    ("forca", "Forca", "forca.js", "Descubra a palavra letra por letra, com 7 erros permitidos.",
     ["Digite uma letra e confirme com Enter, ou arrisque a palavra inteira.", "Acentos não importam: digite c para ç.", "A cada tentativa a página diz o que aconteceu e como está a palavra."]),
    ("senha", "Senha", "senha.js", "Mastermind: descubra uma senha de 4 dígitos em até 10 tentativas.",
     ["A senha tem 4 dígitos, cada um de 1 a 6, e pode repetir.", "Para cada palpite você ouve quantos dígitos estão no lugar certo e quantos são certos no lugar errado."]),
    ("velha", "Jogo da velha", "velha.js", "Contra o computador, nos níveis fácil e difícil.",
     ["Você é o X e joga primeiro; cada casa é um botão com o nome da linha e da coluna.", "No nível difícil o computador não perde: o melhor que você consegue é empatar."]),
    ("numero", "Número secreto", "numero.js", "Descubra o número de 1 a 100 com as dicas maior e menor.",
     ["Digite um palpite; a resposta diz se o número é maior ou menor e o intervalo que sobrou."]),
    ("2048", "2048", "g2048.js", "Junte peças iguais até chegar ao 2048, ouvindo cada jogada.",
     ["Mova com os botões ou com as setas do teclado; o jogo descreve o que se moveu e onde surgiu uma peça nova.", "O botão Ler o tabuleiro diz as quatro linhas."]),
    ("aventura", "O Farol Apagado", "aventura.js", "Aventura de texto: acenda a lâmpada do farol da ilha.",
     ["Digite comandos como olhar, ir norte, pegar lanterna, usar chave, inventário e ajuda.", "Dica: explore a casa do guarda antes de ir ao farol."]),
]
CATALOGO += [
    ("cincoletras", "Cinco letras", "cincoletras.js", "Descubra a palavra secreta de 5 letras, estilo Wordle, em português.",
     ["Digite uma palavra de 5 letras e confirme com Enter; acentos não importam. Qualquer combinação de 5 letras vale como palpite.",
      "Depois de cada palpite você ouve, letra por letra, se ela está no lugar certo, em outro lugar ou não tem.",
      "Comandos: tentativas, pistas (o que já se sabe), letras (as não testadas), dica e desistir. Níveis: fácil (8 tentativas e dicas), normal (6 e uma dica) e difícil (6, sem dicas, e você precisa reaproveitar as letras descobertas)."]),
    ("sudoku", "Sudoku", "sudoku.js", "Sudoku por comandos, com três níveis e solução sempre única.",
     ["Linhas e colunas vão de 1 a 9; os quadrantes também, da esquerda para a direita e de cima para baixo. Para jogar: colocar 5 em 3 4 (valor, linha, coluna).",
      "Para ler: linha 3, coluna 4, quadrante 5, casa 3 4 (diz o que pode entrar), tabuleiro, faltam linha 3, vazias coluna 4 e resumo. Também há apagar 3 4, desfazer, verificar, dica e desistir.",
      "Níveis: fácil (40 números dados, o jogo avisa na hora se o número não é o certo, dicas à vontade), normal (32, 3 dicas, e verificar aponta os erros) e difícil (26, sem dicas). Números repetidos em linha, coluna ou quadrante são sempre recusados."]),
    ("xadrez", "Xadrez", "xadrez.js", "Xadrez completo contra o computador, em três níveis, jogado por texto.",
     ["Escreva o lance: e4, Cf3, Cxe5, O-O (roque), e8=D (promoção) ou de casa para casa, como e2 e4. As letras das peças são R rei, D dama, T torre, B bispo e C cavalo.",
      "Para consultar o tabuleiro: tabuleiro, linha 4, coluna e, casa e4, peças, lances, histórico, material, último, dica, desfazer e desistir. Digite ajuda para ver tudo.",
      "Cada lance seu e a resposta do computador são lidos em voz alta, com a notação e uma frase falada."]),
    ("naval", "Batalha naval", "naval.js", "Afunde a frota do computador antes que ele afunde a sua, em três níveis.",
     ["O tabuleiro tem colunas de A a J e linhas de 1 a 10. Para atirar, diga a casa: B7, ou tiro b7. As duas frotas (porta-aviões, encouraçado, cruzador, submarino e destróier) são sorteadas.",
      "Para consultar: frota (onde estão os seus navios), tiros, inimigo (tiros do computador), restantes (navios inimigos), linha 3, coluna c, resumo, último e dica.",
      "Níveis: fácil (o computador atira ao acaso), normal (caça em volta dos acertos) e difícil (calcula onde os navios restantes mais cabem)."]),
    ("sonar", "Sonar", "sonar.js", "Caça-submarinos: mande pings de sonar, cruze as direções do eco e lance cargas de profundidade.",
     ["Você comanda um navio num mar quadriculado e anda com norte, sul, leste e oeste (leste 3 anda até três casas).",
      "O comando ping manda o sonar: o eco diz a que distância e em que direção está o submarino mais próximo, só de modo aproximado. Pingando de lugares diferentes você cruza as pistas e descobre onde ele está.",
      "O comando lançar solta uma carga de profundidade na casa onde você está, e só acerta se o submarino estiver exatamente ali. Os pings e as cargas são limitados; no nível difícil os submarinos se movem.",
      "No som, o eco demora mais quando o alvo está longe, vem do lado dele e é mais agudo quando ele está ao norte. Atalhos: setas movem, P pinga e L lança."]),
    ("labirinto", "Labirinto", "labirinto.js", "Ache a saída de um labirinto sorteado, ouvindo as passagens de cada lugar e usando o farol quando se perder.",
     ["Você começa no canto de cima à esquerda e a saída fica no canto de baixo à direita. Ande com norte, sul, leste e oeste (leste 3 anda até três casas; correr leste segue pelo corredor até uma bifurcação).",
      "O jogo descreve as passagens: no fácil a cada passo, no normal só em cruzamentos, curvas e becos, e no difícil só quando você pedir com olhar.",
      "O farol diz a direção e a distância em linha reta até a saída (os corredores dão voltas), e a dica diz o primeiro passo do caminho mais curto. Os dois são limitados nos níveis normal e difícil.",
      "No som, passos ao andar, uma batida grave na parede e o farol ecoando do lado da saída. Atalhos: as setas andam."]),
    ("minas", "Campo minado", "minas.js", "Abra as casas sem pisar numa mina, com três tamanhos de campo.",
     ["O campo é uma tabela de botões; cada botão diz a linha, a coluna e o que há nele. Abra com Enter ou use o campo de comando.",
      "Comandos: abrir 3 4, marcar 3 4, ler 3 4, linha 3, coluna 4, tudo e resumo. A primeira jogada nunca é uma mina.",
      "Um número diz quantas minas há nas oito casas ao redor."]),
    ("cacaniqueis", "Caça-níqueis", "cacaniqueis.js", "Um painel de três dígitos e um botão Girar: trinca, sequência ou par dão prêmio; o resto perde a aposta.",
     ["Você começa com créditos virtuais (sem dinheiro de verdade) e escolhe apostar 1, 2 ou 5 por rodada.",
      "Três dígitos iguais pagam muito; uma sequência, como 1 2 3 ou 9 0 1, paga menos; dois iguais (um par) pagam um prêmio pequeno e comum; qualquer outra coisa perde a aposta. Cerca de três em cada dez rodadas pagam algo.",
      "O botão Ver os prêmios lê a tabela, e Ler o saldo diz como você está."]),
    ("relogios", "A Mansão dos Relógios", "hist_relogios.js", "Aventura de mistério: descubra o que houve com o relojoeiro Heitor.",
     ["Digite comandos como olhar, ir norte, pegar ITEM, usar ITEM em ALGO, falar com ALGUÉM, digitar CÓDIGO no cofre e ajuda.", *NIVEIS_TXT]),
    ("templo", "O Templo Submerso", "hist_templo.js", "Aventura de exploração: recupere o Amuleto do Sol antes que a maré suba.",
     ["Digite comandos como olhar, ir norte, pegar ITEM, usar ITEM em ALGO, digitar RESPOSTA no guardião e ajuda.", *NIVEIS_TXT]),
    ("orion", "Estação Orion", "hist_orion.js", "Ficção científica: religue a energia e peça socorro antes que o oxigênio acabe.",
     ["Digite comandos como olhar, ir norte, pegar ITEM, usar ITEM em ALGO, falar com ZEL, digitar CÓDIGO e ajuda.", *NIVEIS_TXT]),
    ("gramado", "Gramado", "gramado.js", "Campo minado por movimento: conduza um cortador de grama e evite os formigueiros, guiado pelo sensor.",
     ["Você está no canto do gramado e anda com norte, sul, leste e oeste (leste 3 anda até três casas).",
      "Cada casa cortada diz quantos formigueiros há nas casas ao redor, inclusive nas diagonais; a caminhada de vários passos para quando há aviso.",
      "Pise num formigueiro e perde (no nível fácil o sensor apita e protege você). marcar DIREÇÃO põe bandeira, sensor lê as quatro direções, mapa lê tudo e dica ajuda nos níveis fácil e normal."]),
    ("escolhas", "A Travessia das Três Provas", "escolhas.js", "Aventura de escolhas numeradas com três problemas de lógica: o rio, as portas e os guardas.",
     ["Você lê a cena e responde com o número da escolha, por exemplo 1.",
      "Três provas de lógica: levar uma raposa, uma galinha e o milho para o outro lado do rio; achar a porta certa quando só uma frase é verdadeira; descobrir qual guarda diz a verdade.",
      "Fácil: o jogo avisa antes de um erro, sem perder nada, e há dicas à vontade. Normal: 3 vidas e 3 dicas. Difícil: 1 vida e sem dicas. repetir lê a cena de novo."]),
    ("blackjack", "Blackjack", "blackjack.js", "Vinte e um contra a banca, com créditos virtuais: pedir, parar, dobrar e dividir.",
     ["Chegue mais perto de 21 que a banca, sem passar. Ás vale 11 ou 1; Valete, Dama e Rei valem 10. Blackjack (Ás e carta de 10 nas duas primeiras) paga 3 para 2.",
      "Você aposta créditos virtuais (um número par de 2 a 50), e o jogo lê as suas cartas e a carta aberta da banca. A banca compra até 17 e para em qualquer 17.",
      "Comandos: apostar N (ou repetir), pedir, parar, dobrar, dividir, mao, banca, saldo, tabela, dica. A dica segue a estratégia básica do blackjack."]),
    ("roleta", "Roleta", "roleta.js", "Roleta com créditos virtuais: aposte em cor, número, dúzia e mais, e mande girar.",
     ["Você faz uma ou mais apostas e manda girar; o jogo lê onde a bola parou e o que cada aposta rendeu.",
      "Apostas: vermelho, preto, par, ímpar, alto, baixo, dúzia 1 a 3, coluna 1 a 3 ou um número de 0 a 36, por exemplo apostar 5 vermelho ou apostar 2 no 17.",
      "Número paga 35 para 1, dúzia e coluna 2 para 1, o resto 1 para 1. Fácil e normal: roleta europeia (um zero). Difícil: americana, com zero e duplo zero.",
      "Comandos: apostar, girar, apostas, limpar, repetir, tabela, histórico, saldo."]),
    ("bacara", "Bacará", "bacara.js", "Bacará com créditos virtuais: aposte no jogador, na banca ou no empate; o jogo dá as cartas e lê tudo.",
     ["Você escolhe o lado (jogador, banca ou empate) e o valor; o jogo dá as cartas, aplica as regras da terceira carta e lê cada passo.",
      "Valores: Ás vale 1, de 2 a 9 valem o número, 10 e figuras valem 0, e a mão vale a soma, ficando só o último dígito. Vence quem chega mais perto de 9.",
      "Jogador e banca pagam 1 para 1 (se a banca vencer com três cartas somando 7, a aposta só é devolvida). Empate paga 8 para 1, e nele as apostas nos outros lados são devolvidas.",
      "Comandos: apostar 10 banca, repetir, tabela, histórico, saldo, dica."]),
    ("caribenho", "Poker caribenho", "caribenho.js", "Poker contra a banca, com créditos virtuais: aposte o ante, veja as suas cinco cartas e decida entre aumentar e desistir.",
     ["Você aposta o ante e recebe cinco cartas abertas; a banca recebe cinco e mostra só uma. Depois você decide: desistir (perde o ante) ou aumentar (paga mais duas vezes o ante).",
      "A banca só joga com Ás e Rei ou melhor. Se não jogar, o ante paga 1 para 1 e o aumento volta. Se jogar, vence a melhor mão: o ante paga 1 para 1 e o aumento paga pela sua mão (par 1 para 1, dois pares 2, trinca 3, sequência 4, flush 5, full house 7, quadra 20, straight flush 50, royal flush 100).",
      "Comandos: apostar N (ante de 1 a 25) ou repetir, aumentar, desistir, mao, banca, saldo, tabela, dica. A dica simula as mãos possíveis da banca e diz se vale a pena aumentar."]),
    ("poker", "Poker Texas hold'em", "poker.js", "Poker um contra um contra o computador, com fichas virtuais: cartas, mesa e apostas lidas em voz alta.",
     ["Cada um começa com o mesmo número de fichas. Em cada mão você recebe duas cartas só suas, e a mesa recebe cinco (flop de três, turn e river), com uma rodada de apostas em cada etapa. Vale a melhor mão de cinco cartas entre as sete.",
      "Comandos: continuar (dá as cartas), pagar, passar, apostar N (o total que você terá apostado na rodada, também serve para aumentar), tudo, desistir, mao, fichas, tabela, dica.",
      "As cegas começam em 5 e 10 e dobram a cada 6 mãos; a partida termina quando alguém fica sem fichas. O computador decide pela chance de ganhar e pelo preço de pagar: no fácil ele paga muito e aposta pouco, no difícil aposta com força e às vezes blefa."]),
    ("arqueiro", "Arqueiro de áudio", "arqueiro.js", "Jogo de som em estéreo: ouça onde o pássaro pia, mova a mira e atire. Use fones de ouvido.",
     ["Pássaros cruzam o céu, da esquerda para a direita ou ao contrário, e piam a cada passo no lado onde estão. Você move a mira com as setas (cada passo faz um ping no lado da mira) e atira com a barra de espaço.",
      "Quando o ping da mira e o pio soam no mesmo ponto do estéreo, atire. Também há botões e comandos: esquerda, direita, atirar, posição, pontos, ajuda.",
      "São 10 alvos. Fácil: devagar, com tolerância de um passo e duas flechas. Normal: ritmo médio e mira exata. Difícil: rápido, com corvos de som grave que não se deve atingir. Sem áudio no navegador, o jogo diz em texto onde o alvo está.",
      "Aperte Testar o som antes de começar: você deve ouvir um som só no fone esquerdo, um no meio e um só no direito."]),
    ("vilarejo", "Vilarejo Sitiado", "vilarejo.js", "Tiro e exploração em um vilarejo tomado por bandidos: ouça onde os inimigos estão, mire, atire e abra caminho até a prefeitura. Visual de arcade para quem enxerga.",
     ["Você anda com W (norte), D (leste), S (sul) e A (oeste) e olha para onde andou por último. As setas movem a mira, que começa no centro e volta ao centro quando você anda (Q também centraliza). A barra de espaço atira, o Shift direito recarrega e as teclas 1 a 4 escolhem revólver, espingarda, faca e mão livre.",
      "X pega o item do chão, abre a porta à frente e sobe ou desce a escada. C usa um kit médico. E diz o estado (vida, arma, chaves e onde você está), L diz onde você está, com o caminho até a prefeitura e as referências por perto, O descreve o que há à frente e H repete a ajuda. Munição e kits estão espalhados pelo vilarejo: explore, porque ela não sobra.",
      "O som mostra onde estão os inimigos: o lado no estéreo, o volume e o brilho dão a distância; o rosnado e o latido são de cães (mire para baixo), o guincho é de rato, o resmungo e os passos pesados são de bandidos. Tiros, gemidos de quem é atingido, portas, chaves e passos (que mudam com o piso) também são sons de verdade. Perto do riacho ouve-se a água, do lado em que ele está. Quando a mira passa sobre um inimigo, soa um sinal agudo. Faca e mão livre só acertam quem está colado à sua frente; a espingarda pega vários, mas só de perto.",
      "O vilarejo tem um riacho com ponte, plantação, casa, igreja, hospital, delegacia de dois andares e prefeitura. Há portas trancadas e chaves escondidas, e o chefe dos bandidos espera na prefeitura. Níveis: fácil (mais vida, inimigos mais fracos), normal e difícil (pouca vida, inimigos rápidos e certeiros).",
      "As mensagens saem uma de cada vez, na ordem, e o aviso urgente (dano, queda de inimigo, fim) passa na frente. Ajuste o ritmo da narração e o volume dos efeitos antes de começar. Use fones de ouvido e aperte Testar o som antes de começar. Se o leitor de tela abaixa o volume dos sons enquanto fala, desative esse recurso no VoiceOver (opção de reduzir o áudio durante a fala). Para quem enxerga, o jogo desenha a cena em primeira pessoa, com mini-mapa e painel de vida e munição, em estilo arcade dos anos 80."]),
    ("paciencia", "Paciência", "paciencia.js", "Paciência (Klondike) falada: mova as cartas por comando e ouça a mesa lida coluna por coluna.",
     ["Sete colunas, um monte e quatro bases (uma por naipe). O objetivo é levar as 52 cartas para as bases, de Ás a Rei.",
      "Cartas: valor A, 2 a 10, J, Q ou K e naipe C copas, O ouros, P paus ou E espadas, como 7C ou QE (também vale 7 de copas).",
      "Comandos: comprar; mover 7C para 4 (leva as cartas abertas em cima dela junto); mover descarte para 3; subir 7C, subir descarte ou subir coluna 2; mesa, coluna N, descarte, bases; dica; desfazer.",
      "Fácil: compra 1, dicas à vontade. Normal: compra 1, 3 dicas. Difícil: compra 3 cartas por vez, sem dicas e sem desfazer."]),
    ("caverna", "A Caverna dos Ecos", "hist_caverna.js", "Aventura guiada pelo som: ache a saída de uma caverna escura ouvindo o vento, a água e os ecos.",
     ["Digite comandos como escutar, olhar, ir norte, pegar ITEM, usar ITEM em ALGO e ajuda. O comando escutar diz o que você ouve onde está, e o som mostra o caminho; onde diz onde você está.", *NIVEIS_TXT]),
]
# Categorias: (id, título, descrição, jogos). A página inicial lista as categorias e cada uma tem a sua página com os jogos.
CATEGORIAS = [
    # Nomes de uma palavra, em ordem alfabética. Cinco categorias ocupam as 5 posições de abas; com os jogos extras de terceiros passam de 5 itens e o menu Mais
    # (quinta posição) guarda as duas últimas (Studio Design: nunca mais de 5 posições).
    ("acao", "Ação", "Jogos de reflexo e movimento. O som ajuda a jogar: melhor com fones de ouvido.", ["arqueiro", "labirinto", "vilarejo"]),
    ("aventuras", "Aventuras", "Histórias em que você digita comandos e explora.", ["aventura", "relogios", "templo", "orion", "caverna", "escolhas"]),
    ("cassino", "Cassino", "Jogos de azar e de cartas, só com créditos virtuais.", ["poker", "blackjack", "bacara", "caribenho", "cacaniqueis", "roleta"]),
    ("estrategia", "Estratégia", "Jogos de tabuleiro, contra o computador.", ["xadrez", "naval", "sonar", "velha", "minas", "gramado"]),
    ("logica", "Lógica", "Palavras, números, códigos e quebra-cabeças de raciocínio, inclusive a paciência.",
     ["forca", "cincoletras", "senha", "numero", "sudoku", "2048", "paciencia"]),
]
def _chave(t: str) -> str:
    """Chave de ordem alfabética: sem acentos, sem maiúsculas e sem o artigo inicial (A, O, As, Os)."""
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"^(a|o|as|os) ", "", t)


# As categorias e, dentro delas, os jogos aparecem em ordem alfabética.
CATEGORIAS.sort(key=lambda c: _chave(c[1]))
GRUPOS = [(t, ids) for _, t, _, ids in CATEGORIAS]
POR_CATEGORIA = {c[0]: c for c in CATEGORIAS}
# Endereços antigos das categorias (juntadas em 25/11/2026), para quem guardou o link
for _antigo, _novo in (("audio", "acao"), ("cartas", "cassino"), ("palavras", "logica"), ("numeros", "logica"), ("tabuleiro", "estrategia")):
    POR_CATEGORIA[_antigo] = POR_CATEGORIA[_novo]
# Aventuras do motor: a página carrega a história e depois o motor (a ordem importa) e diz ao motor qual história abrir.
HISTORIAS = {"relogios", "templo", "orion", "caverna"}
POR_ID = {j[0]: j for j in CATALOGO}
for _c in CATEGORIAS:
    _c[3].sort(key=lambda i: _chave(POR_ID[i][1]))
# Arquivos de apoio que um jogo carrega antes do próprio script (o Vilarejo tem o motor de efeitos sonoros à parte).
APOIO = {"vilarejo": ["vilarejo_som.js"]}
ARQUIVOS_OK = {"base.js", "som.js", "motor.js"} | {j[2] for j in CATALOGO} | {a for l in APOIO.values() for a in l}


def scripts_do_jogo(jid: str) -> list:
    base = ["base.js", "som.js"] + APOIO.get(jid, [])
    return base + [POR_ID[jid][2], "motor.js"] if jid in HISTORIAS else base + [POR_ID[jid][2]]


def extras() -> list:
    """Jogos extras, de terceiros, hospedados por você (STUDIO_JOGOS_EXTRAS): só endereços http e https."""
    saida = []
    for item in os.environ.get("STUDIO_JOGOS_EXTRAS", "").split(";"):
        p = [x.strip() for x in item.split("|")]
        if len(p) >= 2 and p[0] and re.match(r"^https?://[A-Za-z0-9.:/_~%?#=&-]+$", p[1]):
            saida.append((p[0], p[1], p[2] if len(p) > 2 else ""))
    return saida


CSS = nuvem.CSS + """
body{font-size:19px;line-height:1.7;max-width:50rem}
main h1{line-height:1.25;margin-top:1rem}h2{line-height:1.3;margin:1.6rem 0 .3rem;font-size:1.25em}h3{line-height:1.3;margin:1rem 0 .2rem;font-size:1.1em}
.lista-jogos{list-style:none;padding:0}.lista-jogos li{margin:.8rem 0}
#anuncio{border:1px solid var(--linha);padding:.7rem;margin:1rem 0;min-height:2.4rem}
#jogo input[type=text]{font-size:1.1em;padding:.5rem;margin:.3rem 0;max-width:22rem;width:100%}
#jogo button{margin:.3rem .3rem .3rem 0;padding:.6rem 1rem;font-size:1em}
#historico{padding-left:1.4rem}#quadro{list-style:none;padding:0}
"""


def nav_jogos() -> list:
    """Abas do Games: uma por categoria (em ordem alfabética) e, se há jogos extras de terceiros, o item Extras, que fica no menu Mais. No máximo 5 posições: 5 categorias, ou 4 abas e o menu Mais (quando há Outros jogos)."""
    itens = [(f"/categoria/{cid}", t) for cid, t, _, _ in CATEGORIAS]
    return itens + ([("/extras", "Extras")] if extras() else [])


def aba_do_jogo(jid: str) -> str:
    """Rota da aba (a categoria) a que o jogo pertence."""
    return next((f"/categoria/{c[0]}" for c in CATEGORIAS if jid in c[3]), nav_jogos()[0][0])


def pagina(titulo: str, corpo: str, sess: dict = None, extra_head: str = "", scripts_: list = None, atual: str = "") -> bytes:
    nav = sair = scripts = ""
    conteudo = f"<h1>{e(titulo)}</h1>{corpo}"
    if sess:
        itens = nav_jogos()
        atual = atual or itens[0][0]
        # Numa página de jogo, trocar de aba carrega a página inteira (o jogo tem script e teclas próprias que não podem ficar para trás).
        completas = tuple(r for r, _ in itens) if scripts_ else ()
        nav = design.nav_abas(itens, atual, "Categorias de jogos do Studio Games", completas)
        sair = (f'<form class="linha" method="post" action="/sair"><input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form>')
        conteudo = design.com_abas(itens, atual, conteudo)
        scripts = design.script()
    js = "".join(f'<script src="/js/{e(s)}" defer></script>' for s in (scripts_ or []))
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow">{extra_head}<title>{e(titulo)} - Studio Games</title>{nuvem.ICONE}<style>{CSS}</style></head><body>'
            f'{design.topo()}<a class="pular" href="#principal">Pular para o conteúdo</a>{nuvem.cabecalho("Studio Games", nav, sair_html=sair)}'
            f'<main id="principal">{conteudo}</main>{design.rodape(servico="jogos")}{scripts}{js}</body></html>').encode("utf-8")


def _lista_categoria(c: tuple) -> str:
    _, _, desc, ids = c
    lista = '<ul class="lista-jogos">' + "".join(
        f'<li><h2><a href="/jogo/{e(i)}">{e(POR_ID[i][1])}</a></h2><p>{e(POR_ID[i][3])}</p></li>' for i in ids) + "</ul>"
    return f"<p>{e(desc)} {len(ids)} {'jogo' if len(ids) == 1 else 'jogos'}.</p>{lista}"


def pg_inicio() -> tuple:
    """A página inicial é a primeira categoria (a primeira aba), com a apresentação do site antes da lista."""
    c = CATEGORIAS[0]
    intro = ("<p>Jogos leves para jogar no navegador, feitos para leitor de tela: tudo é botão, campo de texto ou lista, e cada jogada é lida em voz alta. "
             "Nada é guardado no servidor. Cada aba é uma categoria de jogos.</p>")
    return c[1], intro + _lista_categoria(c), []


def pg_categoria(cid: str):
    c = POR_CATEGORIA.get(cid)
    if not c:
        return None
    return c[1], _lista_categoria(c), []


def pg_outros():
    ex = extras()
    if not ex:
        return None
    lista = '<ul class="lista-jogos">' + "".join(f'<li><a href="{e(u)}">{e(n)}</a>' + (f": {e(d)}" if d else "") + "</li>" for n, u, d in ex) + "</ul>"
    return "Extras", f"<p>Jogos de terceiros, hospedados por você, fora do Studio Games.</p>{lista}", []


def rota_canonica(rota: str) -> str:
    """A rota atual de uma rota antiga: /categoria/<antigo> vai para a categoria que a absorveu e /outros para /extras. As demais não mudam.
    Regra do projeto: rota nova é a canônica e a antiga redireciona (301) para ela."""
    if rota == "/outros":
        return "/extras"
    m = re.fullmatch(r"/categoria/([a-z0-9]+)", rota)
    if m and m.group(1) in POR_CATEGORIA and POR_CATEGORIA[m.group(1)][0] != m.group(1):
        return f"/categoria/{POR_CATEGORIA[m.group(1)][0]}"
    return rota


def pg_jogo(jid: str):
    j = POR_ID.get(jid)
    if not j:
        return None
    como = "".join(f"<li>{e(t)}</li>" for t in j[4])
    dado = f' data-historia="{e(jid)}"' if jid in HISTORIAS else ""
    cat = next(c for c in CATEGORIAS if jid in c[3])
    corpo = (f'<p>{e(j[3])}</p><h2>Como jogar</h2><ol>{como}</ol><h2>Jogo</h2>'
             '<noscript><p class="erro">Este jogo precisa de JavaScript ligado no navegador.</p></noscript>'
             f'<div id="jogo"{dado}></div><div id="anuncio" role="status" aria-live="polite" aria-atomic="true"></div>'
             f'<p><a href="/categoria/{e(cat[0])}">Voltar para {e(cat[1])}</a></p>')
    return j[1], corpo, scripts_do_jogo(jid)


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo)


CSP_PAGINA = "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; form-action 'self'; base-uri 'none'; connect-src 'none'; frame-ancestors 'none'"


class Jogos(nuvem.ManipuladorBase):
    server_version = "StudioJogos"
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
        self.send_header("Content-Security-Policy", design.csp(CSP_PAGINA, corpo, conectar=b'<script src="/js/' not in corpo))
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

    def _ir_permanente(self, destino: str) -> None:
        self._enviar(301, b"", extra=[("Location", destino)])

    def _sessao(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            return None, None
        m = c.get(COOKIE)
        token = m.value if m else ""
        return token, nuvem.sessao_valida(token, "jogos")

    def _cookie(self, token: str, apagar: bool = False) -> tuple:
        return nuvem.cabecalho_cookie(token, self.headers.get("Host", ""), self._https(), apagar)

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
        rota = urlparse(self.path).path
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
                    self._enviar(405, pagina("Não permitido", "<p>Este servidor só entrega os jogos.</p>", sess))
                    return
                n = min(int(self.headers.get("Content-Length") or 0), 4096)
                campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}
                if not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
                    self._enviar(403, pagina("Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess))
                    return
                nuvem.encerrar_sessao(token)
                self._ir("/entrar", [self._cookie("", apagar=True)])
                return
            if rota.startswith("/js/"):
                nome = rota[4:]
                if nome not in ARQUIVOS_OK or not (JOGOS_DIR / nome).is_file():
                    self._enviar(404, b"nao encontrado", "text/plain; charset=utf-8")
                    return
                self._enviar(200, (JOGOS_DIR / nome).read_bytes(), "application/javascript; charset=utf-8")
                return
            if rota == "/":
                titulo, corpo, scripts = pg_inicio()
                self._enviar(200, pagina(titulo, corpo, sess, scripts_=scripts, atual=nav_jogos()[0][0]))
                return
            canonica = rota_canonica(rota)
            if canonica != rota:   # rota antiga: redireciona de forma permanente para a atual, para o endereço sempre estar em dia
                self._ir_permanente(canonica)
                return
            if rota == "/extras":
                ro = pg_outros()
                if not ro:
                    self._enviar(404, pagina("Não encontrei", '<p>Não há jogos extras configurados.</p>' + design.botao("/", "Ver as categorias"), sess))
                    return
                self._enviar(200, pagina(ro[0], ro[1], sess, scripts_=ro[2], atual="/extras"))
                return
            mc = re.fullmatch(r"/categoria/([a-z0-9]+)", rota)
            if mc:
                rc = pg_categoria(mc.group(1))
                if not rc:
                    self._enviar(404, pagina("Não encontrei", '<p>Esta categoria não existe.</p>' + design.botao("/", "Ver as categorias"), sess))
                    return
                self._enviar(200, pagina(rc[0], rc[1], sess, scripts_=rc[2], atual=f"/categoria/{POR_CATEGORIA[mc.group(1)][0]}"))
                return
            m = re.fullmatch(r"/jogo/([a-z0-9]+)", rota)
            r = pg_jogo(m.group(1)) if m else None
            if not r:
                self._enviar(404, pagina("Não encontrei", '<p>Este jogo não existe.</p>' + design.botao("/", "Ver todos os jogos"), sess))
                return
            self._enviar(200, pagina(r[0], r[1], sess, scripts_=r[2], atual=aba_do_jogo(m.group(1))))
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            self._enviar(500, pagina("Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p><p><a href="/">Voltar</a></p>', sess))

    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            via_access = nuvem.entrada_por_access(self.headers, "jogos")  # aprovado no Cloudflare Access (Microsoft Authenticator), se ligado
            if via_access:
                self._enviar(200, nuvem.pagina_continuar(), extra=[self._cookie(via_access)])
                return
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
        sys.exit("Sem senha e código configurados o servidor de jogos não sobe. Rode: python3 studio_acesso.py --tudo")
    srv = ThreadingHTTPServer((HOST, PORT), Jogos)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Studio Games em http://{HOST}:{PORT} (sites permitidos: {', '.join(sorted(HOSTS_OK))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
