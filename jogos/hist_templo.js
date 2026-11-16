// História "O Templo Submerso": exploração de um templo numa gruta de maré. Dados para o motor.js.
(function (raiz) {
  "use strict";
  var ini = ["examinar barco", "pegar pederneira", "usar pederneira", "ir norte", "ir norte", "ir leste", "pegar espelho", "ir oeste"];
  var fim = ["ir oeste", "usar corda no pilar", "descer", "pegar chave de jade", "subir", "ir leste", "ir norte", "ir norte", "digitar sol no guardião", "usar chave de jade na caixa", "ir sul", "ir sul", "ir sul", "ir sul"];
  var normal = ini.concat(["usar espelho na fresta"], fim);
  var dificil = ["examinar barco", "pegar pederneira", "pegar trapo", "usar pederneira", "ir norte", "ir norte", "ir leste", "pegar espelho", "usar trapo no espelho", "ir oeste", "usar espelho na fresta"]
    .concat(["ir oeste", "usar corda no pilar", "descer", "pegar chave de jade", "subir", "ir leste", "ir norte", "ir norte", "digitar mapa no guardião", "usar chave de jade na caixa", "ir sul", "ir sul", "ir sul", "ir sul"]);

  var h = {
    id: "templo", titulo: "O Templo Submerso",
    resumo: "Explore um templo escondido numa gruta de maré e traga o amuleto antes que a água suba.",
    intro: "Você é arqueóloga ou arqueólogo e, na maré baixa, descobriu a entrada de um templo antigo escondido numa gruta. A maré vai subir em poucas horas: tudo precisa ser feito com pressa.",
    objetivo: "recuperar o Amuleto do Sol, no altar do templo, e voltar à praia antes que a maré suba.",
    inicio: "praia",
    msgLimite: "A maré subiu depressa demais e inundou o templo antes de você conseguir sair.",
    salas: {
      praia: { nome: "Praia da enseada", desc: "Uma praia estreita de pedras escuras. Um barco velho jaz virado de cabeça para baixo na areia, perto de uma pederneira. Ao norte, a boca de uma gruta.", saidas: { norte: "gruta" }, itens: ["pederneira"],
        cenario: { barco: { nome: "barco", apelidos: ["barco velho", "casco"],
          exame: [
            { se: { semFlags: ["viu_barco"], nivel: ["dificil"] }, msg: "Debaixo do barco você encontra uma tocha, um rolo de corda e um trapo velho.", poe: ["viu_barco"], ganha: ["tocha", "corda", "trapo"] },
            { se: { semFlags: ["viu_barco"] }, msg: "Debaixo do barco você encontra uma tocha e um rolo de corda.", poe: ["viu_barco"], ganha: ["tocha", "corda"] },
            { msg: "Só sobrou o casco apodrecido." }] } },
        aoEntrar: [{ se: { tem: ["amuleto"] }, msg: "Você sai da gruta com o Amuleto do Sol brilhando na mão, e a água já lambe os seus pés. A maré encobre a entrada do templo logo depois. Você conseguiu!", fim: "vitoria" }] },
      gruta: { nome: "Boca da gruta", desc: "Uma entrada ampla na rocha, que engole a luz do dia. A praia fica ao sul, e ao norte um corredor segue para o escuro.", saidas: { sul: "praia", norte: "galeria" } },
      galeria: { nome: "Galeria das colunas", desc: "Colunas de pedra esculpidas sustentam um teto alto. Uma fresta no teto deixa cair um fio de luz do sol. Uma grande porta de pedra, com um sol esculpido, fecha o caminho ao norte. Há uma câmara a leste, uma sala a oeste e a saída ao sul.",
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro, mas você sente colunas por perto e um fio de luz distante no teto.",
        saidas: { sul: "gruta", leste: "camara", oeste: "poco_sala", norte: { para: "ponte", requer: { flags: ["porta_aberta"] }, msg: "A grande porta de pedra, com um sol esculpido, está fechada." } },
        extras: [{ se: { flags: ["porta_aberta"] }, msg: "A porta de pedra do norte está aberta." }],
        aoEntrar: [{ so: ["dificil"], se: { semFlags: ["luz"] }, msg: "No escuro, você tropeça numa coluna caída e bate a cabeça. O mundo gira e apaga.", fim: "derrota" }],
        cenario: {
          fresta: { nome: "fresta", apelidos: ["fresta no teto", "feixe", "raio de sol", "luz do sol"], desc: "Uma fresta no teto, por onde cai um fio fino de luz do sol bem em frente à porta de pedra." },
          porta: { nome: "porta de pedra", apelidos: ["porta", "sol esculpido", "simbolo"], desc: "Uma porta de pedra com um grande sol esculpido, que parece esperar por luz." } } },
      camara: { nome: "Câmara dos espelhos", desc: "Uma câmara pequena, com paredes de pedra lisa. Num nicho há um espelho de bronze. A galeria fica a oeste.", saidas: { oeste: "galeria" }, itens: ["espelho"],
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro demais para ver. A galeria fica a oeste." },
      poco_sala: { nome: "Sala do poço", desc: "Uma sala redonda com um poço escuro no centro e um pilar de pedra perto da borda. A galeria fica a leste.",
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro, e você ouve água lá embaixo. A galeria fica a leste.",
        saidas: { leste: "galeria", descer: { para: "cripta", requer: { flags: ["corda_presa"] }, msg: "O poço é fundo demais para descer sem uma corda bem presa." } },
        extras: [{ se: { flags: ["corda_presa"] }, msg: "Uma corda está amarrada ao pilar e desce pelo poço." }],
        cenario: { pilar: { nome: "pilar", apelidos: ["pilar de pedra", "poco", "poço"], desc: "Um pilar de pedra grosso, perfeito para amarrar uma corda." } } },
      cripta: { nome: "Cripta alagada", desc: "Uma cripta com água até os tornozelos. Sobre um sarcófago há uma chave de jade. A corda sobe de volta ao poço.", saidas: { subir: "poco_sala" }, itens: ["chave_jade"],
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro, e a água fria bate nos seus tornozelos. A corda sobe pelo poço." },
      ponte: { nome: "Ponte de pedra", desc: "Uma ponte estreita sobre um abismo cheio de água escura. A galeria fica ao sul e o altar ao norte.", saidas: { sul: "galeria", norte: "altar" } },
      altar: { nome: "Altar do sol", desc: "Uma sala circular, com o teto aberto para o céu. No centro, um altar com uma caixa de jade. Uma estátua de guardião, com olhos de pedra, vigia o altar. A ponte fica ao sul.", saidas: { sul: "ponte" },
        cenario: {
          guardiao: { nome: "guardião", apelidos: ["estatua", "guardiao", "estátua"],
            exame: [
              { se: { flags: ["guardiao_ok"] }, msg: "O guardião inclinou a cabeça de pedra e deixou o caminho livre." },
              { se: { nivel: ["dificil"] }, msg: "A estátua fala com voz de pedra: tenho cidades sem casas, rios sem água e florestas sem árvores. Quem sou? Para responder, escreva: digitar RESPOSTA no guardião." },
              { msg: "A estátua fala com voz de pedra: nasço no leste e morro no oeste, aqueço o mundo e não tenho pés. Quem sou? Para responder, escreva: digitar RESPOSTA no guardião." }] },
          caixa: { nome: "caixa de jade", apelidos: ["caixa", "altar"],
            exame: [{ se: { flags: ["caixa_aberta"] }, msg: "A caixa está aberta e vazia." }, { se: { flags: ["guardiao_ok"] }, msg: "A caixa de jade tem uma fechadura em forma de folha." }, { msg: "Uma caixa de jade, guardada pela estátua. Você não ousa tocá-la." }] } } }
    },
    itens: {
      pederneira: { nome: "pederneira", apelidos: ["pedra de fogo", "isqueiro"], desc: "Uma pederneira com um pedaço de aço, para fazer faíscas." },
      tocha: { nome: "tocha", apelidos: [], desc: "Uma tocha de madeira com trapos embebidos em piche." },
      corda: { nome: "corda", apelidos: ["rolo de corda"], desc: "Um rolo de corda grossa, ainda firme." },
      trapo: { nome: "trapo", apelidos: ["pano"], desc: "Um trapo velho, mas seco.", so: ["dificil"] },
      espelho: { nome: "espelho", apelidos: ["espelho de bronze"], desc: "Um espelho redondo de bronze polido.",
        exame: [{ se: { nivel: ["dificil"], semFlags: ["espelho_limpo"] }, msg: "O espelho de bronze está coberto de limo, e não reflete nada. Precisa ser limpo." }, { msg: "Um espelho redondo de bronze polido, que reflete bem a luz." }] },
      chave_jade: { nome: "chave de jade", apelidos: ["chave"], desc: "Uma chave de jade em forma de folha." },
      amuleto: { nome: "Amuleto do Sol", apelidos: ["amuleto"], desc: "Um disco de ouro com o rosto do sol, que brilha sozinho." }
    },
    usos: [
      { item: "pederneira", se: { flags: ["luz"] }, msg: "A tocha já está acesa." },
      { item: "pederneira", se: { tem: ["tocha"] }, falha: "Você precisa de uma tocha para acender.", msg: "Faíscas pulam da pederneira e a tocha pega fogo. Agora você tem luz.", poe: ["luz"] },
      { item: "tocha", se: { flags: ["luz"] }, msg: "A tocha já está acesa." },
      { item: "tocha", se: { tem: ["pederneira"] }, falha: "Falta algo para acender a tocha.", msg: "Faíscas pulam da pederneira e a tocha pega fogo. Agora você tem luz.", poe: ["luz"] },
      { item: "trapo", alvo: "espelho", se: { semFlags: ["espelho_limpo"] }, falha: "O espelho já está limpo.", msg: "Você esfrega o limo com o trapo, e o bronze brilha como novo.", poe: ["espelho_limpo"] },
      { item: "espelho", alvo: "fresta", so: ["dificil"], se: { flags: ["espelho_limpo"], semFlags: ["porta_aberta"] }, falha: "O espelho está sujo demais e não reflete nada. Limpe-o primeiro.",
        msg: "Você inclina o espelho limpo, o feixe de sol bate no sol esculpido da porta, e as pedras rangem: a porta se abre.", poe: ["porta_aberta"] },
      { item: "espelho", alvo: "fresta", nao: ["dificil"], se: { semFlags: ["porta_aberta"] }, falha: "A porta já está aberta.",
        msg: "Você inclina o espelho no fio de luz, o feixe bate no sol esculpido da porta, e as pedras rangem: a porta se abre.", poe: ["porta_aberta"] },
      { item: "corda", alvo: "pilar", se: { semFlags: ["corda_presa"] }, falha: "A corda já está amarrada.", msg: "Você amarra a corda ao pilar com um nó firme e joga a ponta no poço. Dá para descer.", poe: ["corda_presa"], consome: ["corda"] },
      { codigo: "sol", alvo: "guardiao", so: ["facil", "normal"], se: { semFlags: ["guardiao_ok"] }, falha: "O guardião já foi vencido.", errado: "A estátua balança a cabeça de pedra: resposta errada.",
        msg: "A estátua inclina a cabeça de pedra: o sol, é claro. Os olhos dela se apagam, e o caminho até a caixa está livre.", poe: ["guardiao_ok"] },
      { codigo: "mapa", alvo: "guardiao", so: ["dificil"], se: { semFlags: ["guardiao_ok"] }, falha: "O guardião já foi vencido.", errado: "A estátua balança a cabeça de pedra: resposta errada.",
        msg: "A estátua inclina a cabeça de pedra: um mapa, é claro. Os olhos dela se apagam, e o caminho até a caixa está livre.", poe: ["guardiao_ok"] },
      { item: "chave_jade", alvo: "caixa", se: { flags: ["guardiao_ok"], semFlags: ["caixa_aberta"] }, falha: "A estátua do guardião ainda vigia a caixa, e você não ousa tocá-la.",
        msg: "A chave de jade gira. A caixa se abre e o amuleto brilha lá dentro. O chão do templo treme: é hora de sair.", poe: ["caixa_aberta", "tremor"], ganha: ["amuleto"] }
    ],
    dicas: [
      { se: { tem: ["amuleto"] }, msg: "Volte pelo caminho que veio, até a praia, antes que a maré suba." },
      { se: { flags: ["guardiao_ok"], tem: ["chave_jade"] }, msg: "Use a chave de jade na caixa do altar." },
      { se: { flags: ["porta_aberta"], tem: ["chave_jade"] }, msg: "Vá ao altar, ao norte da ponte, e responda ao enigma do guardião." },
      { se: { flags: ["corda_presa"] }, msg: "Desça o poço e pegue a chave de jade na cripta." },
      { se: { flags: ["porta_aberta"] }, msg: "Atravesse a ponte. Para a caixa do altar você vai precisar de uma chave de jade, no fundo do poço, a oeste da galeria." },
      { se: { tem: ["espelho"], flags: ["luz"] }, msg: "Na galeria, use o espelho na fresta do teto, para refletir a luz no sol da porta." },
      { se: { flags: ["luz"] }, msg: "Com a tocha acesa, explore a galeria: o espelho está na câmara ao leste." },
      { msg: "Examine o barco na praia e acenda a tocha com a pederneira antes de entrar na gruta." }
    ],
    solucao: { facil: normal, normal: normal, dificil: dificil }
  };
  var H = raiz.Heimdall || (raiz.Heimdall = {}); H.historias = H.historias || {}; H.historias.templo = h;
  if (typeof module !== "undefined") module.exports = h;
})(typeof window !== "undefined" ? window : globalThis);
