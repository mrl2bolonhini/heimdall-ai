// História "Estação Orion": ficção científica numa estação espacial sem energia. Dados para o motor.js.
(function (raiz) {
  "use strict";
  var comum1 = ["pegar lanterna", "usar lanterna", "ir norte", "ir leste", "examinar geladeira", "ir leste", "pegar bateria", "ir oeste", "ir oeste", "usar cartão azul na porta", "ir norte", "examinar terminal", "ir sul", "ir oeste"];
  var normal = comum1.concat(["digitar 7316 no armário", "ir leste", "usar cartão vermelho na escotilha", "descer", "usar bateria no painel", "puxar alavanca", "subir", "ir leste", "falar com ZEL", "ir oeste", "ir norte", "ir leste", "usar chip no rádio"]);
  var dificil = ["pegar lanterna", "usar lanterna", "examinar armário", "pegar traje", "ir norte", "ir leste", "examinar geladeira", "ir leste", "pegar bateria", "examinar diário", "ir oeste", "ir oeste", "usar cartão azul na porta", "ir norte", "examinar terminal", "ir sul", "ir oeste"]
    .concat(["digitar 7316 no armário", "ir leste", "usar cartão vermelho na escotilha", "descer", "usar bateria no painel", "puxar alavanca", "subir", "ir leste", "falar com ZEL", "ir oeste", "ir norte", "ir leste", "usar chip no rádio", "digitar 4021 no rádio"]);

  var h = {
    id: "orion", titulo: "Estação Orion",
    resumo: "Ficção científica: religue a energia da estação Orion e peça socorro antes que o oxigênio acabe.",
    intro: "Você acorda na câmara de acoplamento da Estação Orion, sozinho e com a cabeça doendo. Uma falha apagou as luzes e cortou a energia. O ar está acabando, e o rádio de emergência está mudo.",
    objetivo: "religar a energia no reator e enviar um pedido de socorro pelo rádio da sala de comunicações.",
    inicio: "eclusa",
    msgLimite: "O oxigênio da estação acabou antes de você conseguir pedir socorro.",
    salas: {
      eclusa: { nome: "Câmara de acoplamento", desc: "Uma câmara pequena, de paredes metálicas, com um armário de trajes. Uma lanterna de emergência está presa à parede. Um corredor segue ao norte.", saidas: { norte: "corredor" }, itens: ["lanterna"],
        cenario: { armario_trajes: { nome: "armário de trajes", apelidos: ["armario de trajes", "trajes", "armario"],
          exame: [
            { se: { nivel: ["dificil"], semFlags: ["viu_traje"] }, msg: "No armário há um traje de proteção contra radiação. Você o veste por cima da roupa.", poe: ["viu_traje"], ganha: ["traje"] },
            { se: { nivel: ["dificil"] }, msg: "O armário está vazio agora." },
            { msg: "Trajes espaciais velhos, gastos demais para serem úteis." }] } } },
      corredor: { nome: "Corredor central", desc: "Um corredor longo, de paredes de metal. A câmara de acoplamento fica ao sul, o refeitório a leste, o laboratório a oeste, uma porta de controle ao norte e uma escotilha no chão, que desce para o reator.",
        escuro: { flags: ["luz"] }, textoEscuro: "O corredor está no breu. Sem luz, só dá para seguir às cegas pelas saídas conhecidas.",
        saidas: { sul: "eclusa", leste: "refeitorio", oeste: "laboratorio",
          norte: { para: "controle", requer: { flags: ["porta_azul"] }, msg: "A porta de controle, ao norte, está trancada e pede um cartão azul." },
          descer: { para: "reator", requer: { flags: ["porta_vermelha"] }, msg: "A escotilha do reator está trancada e pede um cartão vermelho." } },
        extras: [{ se: { flags: ["porta_azul"] }, msg: "A porta de controle está destravada." }],
        cenario: {
          porta: { nome: "porta de controle", apelidos: ["porta", "porta azul"], desc: "Uma porta de metal com uma luz azul apagada, que pede um cartão azul." },
          escotilha: { nome: "escotilha", apelidos: ["escotilha do reator", "escotilha vermelha"], desc: "Uma escotilha no chão, marcada com um símbolo de radiação, que pede um cartão vermelho." } } },
      refeitorio: { nome: "Refeitório", desc: "Mesas fixas ao chão, uma geladeira e uma grande janela com estrelas. Um robô de serviço está parado num canto. O corredor fica a oeste e os alojamentos a leste.", saidas: { oeste: "corredor", leste: "alojamentos" },
        escuro: { flags: ["luz"] }, textoEscuro: "O refeitório está escuro. O corredor fica a oeste e os alojamentos a leste.",
        npcs: [{ id: "zel", nome: "ZEL", apelidos: ["robo", "robô", "robo de servico"], desc: "ZEL é um robô de serviço baixo e redondo, com um único olho azul fraco.",
          falas: [
            { se: { flags: ["energia"], semFlags: ["zel_deu"], nivel: ["facil", "normal"] }, msg: "Energia restaurada! Obrigado, tripulante. O chip de comunicação do rádio ficou guardado na minha memória. Pegue: ele reativa o rádio da sala de comunicações.", poe: ["zel_deu"], ganha: ["chip"] },
            { se: { flags: ["energia"], semFlags: ["zel_deu"], nivel: ["dificil"] }, msg: "Energia restaurada. Pegue o chip do rádio. A frequência de emergência é quatro zero dois um. Guarde esse número.", poe: ["zel_deu"], ganha: ["chip"] },
            { se: { flags: ["zel_deu"] }, msg: "Boa sorte com o rádio, tripulante." },
            { se: { nivel: ["facil", "normal"] }, msg: "Bateria fraca... Sem energia na estação não posso ajudar. O reator fica embaixo do corredor, e as chaves de acesso estão espalhadas pelos módulos." },
            { msg: "Bateria fraca... sem energia, não posso ajudar." }] }],
        cenario: { geladeira: { nome: "geladeira", apelidos: ["refrigerador"],
          exame: [{ se: { semFlags: ["achou_azul"] }, msg: "Preso à porta da geladeira com um ímã, há um cartão azul de acesso.", poe: ["achou_azul"], ganha: ["cartao_azul"] }, { msg: "Uma geladeira vazia e sem energia." }] } } },
      alojamentos: { nome: "Alojamentos", desc: "Beliches pequenos e uma bagunça de cobertores flutuando devagar. Uma bateria de reserva está presa a uma prateleira. O refeitório fica a oeste.", saidas: { oeste: "refeitorio" }, itens: ["bateria"],
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro demais. O refeitório fica a oeste.",
        cenario: { diario: { nome: "diário de bordo", apelidos: ["diario", "diario de bordo", "caderno"],
          exame: [{ se: { nivel: ["dificil"] }, msg: "No diário de bordo, o engenheiro escreveu: o final do código do armário do laboratório é um, seis." }, { msg: "O diário de bordo só tem anotações de rotina." }] } } },
      laboratorio: { nome: "Laboratório", desc: "Bancadas com instrumentos apagados. Um armário de aço, com teclado numérico, ocupa uma parede. O corredor fica a leste.", saidas: { leste: "corredor" },
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro demais. O corredor fica a leste.",
        cenario: { armario: { nome: "armário", apelidos: ["armario", "armario de aco", "armario de aço", "teclado"],
          exame: [{ se: { flags: ["armario_aberto"] }, msg: "O armário está aberto e vazio." }, { msg: "Um armário de aço, com teclado numérico de quatro dígitos. Para tentar um código, escreva: digitar NÚMEROS no armário." }] } } },
      controle: { nome: "Sala de controle", desc: "Telas apagadas cobrem as paredes. Um terminal de emergência ainda funciona com bateria própria. O corredor fica ao sul e a sala de comunicações a leste.", saidas: { sul: "corredor", leste: "comunicacoes" },
        cenario: { terminal: { nome: "terminal", apelidos: ["terminal de emergencia", "computador", "tela"],
          exame: [
            { se: { nivel: ["dificil"] }, msg: "O terminal de emergência mostra um registro apagado em parte: código do armário do laboratório, sete, três, e o resto foi corrompido. Para religar a estação, é preciso ativar a alavanca do reator com a bateria no painel.", poe: ["sabe_codigo"] },
            { msg: "O terminal de emergência mostra: código do armário do laboratório, sete, três, um, seis. Para religar a estação, ative a alavanca do reator, depois de instalar uma bateria no painel.", poe: ["sabe_codigo"] }] } } },
      comunicacoes: { nome: "Sala de comunicações", desc: "Uma sala pequena, com um grande rádio de emergência numa bancada. Há um encaixe vazio para um chip. A sala de controle fica a oeste.", saidas: { oeste: "controle" },
        cenario: { radio: { nome: "rádio", apelidos: ["radio", "rádio de emergência", "radio de emergencia"],
          exame: [{ se: { flags: ["sos"] }, msg: "O rádio transmite seu pedido de socorro." }, { se: { flags: ["chip_ok"] }, msg: "O rádio está pronto, e o visor pede a frequência de emergência. Para digitar, escreva: digitar NÚMEROS no rádio." }, { se: { flags: ["energia"] }, msg: "O rádio está ligado, com um encaixe vazio para um chip." }, { msg: "O rádio está apagado, sem energia." }] } } },
      reator: { nome: "Sala do reator", desc: "Um reator cilíndrico zumbe baixinho, com um painel de bateria e uma grande alavanca. A escotilha, acima, leva de volta ao corredor.", saidas: { subir: "corredor" },
        extras: [{ se: { flags: ["energia"] }, msg: "O reator ruge, de novo em funcionamento." }],
        aoEntrar: [{ so: ["dificil"], se: { semItem: ["traje"] }, msg: "Sem traje de proteção, a radiação do reator derruba você em segundos.", fim: "derrota" }],
        cenario: {
          painel: { nome: "painel", apelidos: ["painel de bateria", "encaixe"], exame: [{ se: { flags: ["painel_ok"] }, msg: "A bateria está no painel, e o reator está pronto para ser ativado." }, { msg: "Um painel com um encaixe de bateria vazio." }] },
          alavanca: { nome: "alavanca", apelidos: ["alavanca grande"], desc: "Uma alavanca grande, que religa o reator." } } }
    },
    itens: {
      lanterna: { nome: "lanterna", apelidos: ["lanterna de emergencia"], desc: "Uma lanterna de emergência potente." },
      cartao_azul: { nome: "cartão azul", apelidos: ["cartao azul", "cartao", "cartão"], desc: "Um cartão de acesso azul, nível um." },
      cartao_vermelho: { nome: "cartão vermelho", apelidos: ["cartao vermelho", "cartao", "cartão"], desc: "Um cartão de acesso vermelho, de nível técnico." },
      bateria: { nome: "bateria", apelidos: ["bateria de reserva"], desc: "Uma bateria de reserva, pesada, ainda carregada." },
      chip: { nome: "chip", apelidos: ["chip de comunicacao", "chip de comunicação"], desc: "Um chip de comunicação do rádio de emergência." },
      traje: { nome: "traje de proteção", apelidos: ["traje", "traje de protecao"], desc: "Um traje de proteção contra radiação.", so: ["dificil"] }
    },
    usos: [
      { item: "lanterna", se: { flags: ["luz"] }, msg: "A lanterna já está ligada." },
      { item: "lanterna", msg: "Você liga a lanterna. Um feixe branco rasga a escuridão da estação.", poe: ["luz"] },
      { item: "cartao_azul", alvo: "porta", sala: "corredor", se: { semFlags: ["porta_azul"] }, falha: "A porta já está destravada.", msg: "O cartão azul apita, a luz da porta fica verde e a porta de controle se abre.", poe: ["porta_azul"] },
      { item: "cartao_vermelho", alvo: "escotilha", sala: "corredor", se: { semFlags: ["porta_vermelha"] }, falha: "A escotilha já está destravada.", msg: "O cartão vermelho apita e a escotilha do reator se destrava com um sibilo.", poe: ["porta_vermelha"] },
      { codigo: "7316", alvo: "armario", sala: "laboratorio", se: { semFlags: ["armario_aberto"] }, falha: "O armário já está aberto.", errado: "O teclado apita: código errado.",
        msg: "O armário se destrava. Dentro há um cartão vermelho de acesso técnico.", poe: ["armario_aberto"], ganha: ["cartao_vermelho"] },
      { item: "bateria", alvo: "painel", sala: "reator", se: { semFlags: ["painel_ok"] }, falha: "A bateria já está no painel.", msg: "Você encaixa a bateria no painel. Uma luz verde acende, e o reator espera pela alavanca.", poe: ["painel_ok"], consome: ["bateria"] },
      { verbo: "puxar", alvo: "alavanca", se: { flags: ["painel_ok"], semFlags: ["energia"] }, falha: "A alavanca está dura e não se mexe. Falta energia para o reator partir: instale uma bateria no painel.",
        msg: "Você puxa a alavanca com as duas mãos. O reator ruge, as luzes da estação voltam e os sistemas despertam. A energia está de volta!", poe: ["energia"] },
      { item: "chip", alvo: "radio", sala: "comunicacoes", so: ["facil", "normal"], se: { flags: ["energia"] }, falha: "O rádio está sem energia.", msg: "Você encaixa o chip no rádio. O visor acende, o sinal de emergência parte para o espaço e uma nave responde: estamos a caminho! Você está salvo.", fim: "vitoria" },
      { item: "chip", alvo: "radio", sala: "comunicacoes", so: ["dificil"], se: { flags: ["energia"] }, falha: "O rádio está sem energia.", msg: "Você encaixa o chip no rádio. O visor acende e pede a frequência de emergência.", poe: ["chip_ok"] },
      { codigo: "4021", alvo: "radio", sala: "comunicacoes", so: ["dificil"], se: { flags: ["chip_ok"] }, falha: "O rádio ainda não tem o chip.", errado: "O rádio chia: frequência inválida.",
        msg: "O rádio sintoniza a frequência de emergência. O sinal de socorro parte para o espaço e uma nave responde: estamos a caminho! Você está salvo.", poe: ["sos"], fim: "vitoria" }
    ],
    dicas: [
      { se: { flags: ["energia"], tem: ["chip"] }, msg: "Vá à sala de comunicações, a leste da sala de controle, e use o chip no rádio." },
      { se: { flags: ["energia"] }, msg: "Fale com ZEL, o robô do refeitório: agora que há energia, ele tem algo para você." },
      { se: { flags: ["painel_ok"] }, msg: "Puxe a alavanca do reator." },
      { se: { tem: ["cartao_vermelho"] }, msg: "Use o cartão vermelho na escotilha do corredor, desça ao reator e instale a bateria no painel." },
      { se: { flags: ["sabe_codigo"] }, msg: "Digite o código do terminal no armário do laboratório, a oeste do corredor." },
      { se: { flags: ["porta_azul"] }, msg: "Examine o terminal na sala de controle: ele mostra o código do armário do laboratório." },
      { se: { tem: ["cartao_azul"] }, msg: "Use o cartão azul na porta de controle, ao norte do corredor." },
      { se: { flags: ["luz"] }, msg: "Procure no refeitório: a geladeira guarda um cartão azul. E nos alojamentos há uma bateria." },
      { msg: "Pegue a lanterna e use-a. Sem luz, a estação é um labirinto." }
    ],
    solucao: { facil: normal, normal: normal, dificil: dificil }
  };
  var H = raiz.Heimdall || (raiz.Heimdall = {}); H.historias = H.historias || {}; H.historias.orion = h;
  if (typeof module !== "undefined") module.exports = h;
})(typeof window !== "undefined" ? window : globalThis);
