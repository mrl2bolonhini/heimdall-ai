// História "A Mansão dos Relógios": mistério numa casa antiga. Dados para o motor.js.
(function (raiz) {
  "use strict";
  var base = ["ir norte", "ir leste", "examinar sofá", "ir norte", "pegar fósforos", "falar com Eleonora", "ir sul", "ir oeste", "usar chave de bronze na porta", "ir oeste", "pegar vela", "examinar estante", "usar fósforos",
    "ir leste", "ir leste", "ir norte", "descer", "pegar engrenagem", "subir", "ir sul", "ir oeste"];
  var normal = base.concat(["ir norte", "ir leste", "digitar 1147 no cofre", "ir oeste", "ir sul", "examinar relógio", "usar engrenagem no relógio", "usar chave dourada no relógio", "descer", "ler diário"]);
  var dificil = base.concat(["ir norte", "ir oeste", "pegar lupa", "pegar óleo", "ir leste", "ir sul", "examinar relógio", "ir norte", "ir leste", "digitar 1147 no cofre", "ir oeste", "ir sul",
    "usar engrenagem no relógio", "usar chave dourada no relógio", "descer", "ler diário"]);

  var h = {
    id: "relogios", titulo: "A Mansão dos Relógios",
    resumo: "Mistério numa mansão cheia de relógios: descubra o que houve com o relojoeiro Heitor.",
    intro: "É uma noite de tempestade. Você chega à Mansão Albuquerque, onde o relojoeiro Heitor desapareceu há uma semana. A governanta deixou o portão aberto e a casa inteira tiquetaqueia, menos o grande relógio do hall, parado desde o dia em que ele sumiu.",
    objetivo: "descobrir o que aconteceu com Heitor, encontrando o diário dele na sala secreta escondida na mansão.",
    inicio: "portao",
    salas: {
      portao: { nome: "Portão da mansão", desc: "Sob a chuva, o portão de ferro está aberto. Ao norte, uma porta dupla leva ao hall da mansão.", saidas: { norte: "hall" } },
      hall: { nome: "Hall dos relógios", desc: "Um salão alto, com dezenas de relógios nas paredes. No centro, um enorme relógio de pêndulo está parado. Há uma porta fechada ao norte, uma sala a leste, a biblioteca a oeste e o portão ao sul.",
        saidas: { sul: "portao", leste: "sala", oeste: "biblioteca",
          norte: { para: "corredor", requer: { flags: ["corredor_aberto"] }, msg: "A porta do corredor, ao norte, está trancada com uma fechadura de bronze." },
          descer: { para: "secreta", oculta: true, requer: { flags: ["passagem"] } } },
        extras: [{ se: { flags: ["corredor_aberto"] }, msg: "A porta do corredor, ao norte, está aberta." }, { se: { flags: ["passagem"] }, msg: "O grande relógio se abriu como uma porta, e uma escada desce por trás dele." }],
        cenario: {
          relogio_grande: { nome: "relógio de pêndulo", apelidos: ["relogio", "pendulo", "relógio grande", "grande relogio"],
            exame: [
              { se: { nivel: ["dificil"], semItem: ["lupa"] }, msg: "O relógio de pêndulo está parado, mas o mostrador está tão sujo de poeira e fuligem que não dá para ler os minutos. Falta algo que ajude a enxergar de perto." },
              { se: { flags: ["engrenagem_ok"] }, msg: "O relógio já tem a engrenagem no lugar. Os ponteiros continuam parados às onze e quarenta e sete, e na lateral há um buraco de chave em forma de ponteiro." },
              { msg: "O relógio de pêndulo está parado às onze e quarenta e sete. Dá para ver que falta uma engrenagem no mecanismo, e há um buraco de chave em forma de ponteiro na lateral.", poe: ["sabe_hora"] }] },
          porta: { nome: "porta do corredor", apelidos: ["porta", "fechadura", "porta de bronze"], desc: "Uma porta de madeira escura, ao norte, com uma fechadura de bronze." }
        } },
      sala: { nome: "Sala de estar", desc: "Poltronas cobertas por lençóis e um sofá de veludo gasto. A lareira está fria. O hall fica a oeste e a cozinha ao norte.", saidas: { oeste: "hall", norte: "cozinha" },
        cenario: { sofa: { nome: "sofá", apelidos: ["sofa", "almofada", "almofadas"],
          exame: [{ se: { semFlags: ["achou_chave"] }, msg: "Entre as almofadas do sofá você sente algo duro: uma chave de bronze.", poe: ["achou_chave"], ganha: ["chave_bronze"] }, { msg: "Um sofá de veludo gasto. Você já revirou as almofadas." }] } } },
      cozinha: { nome: "Cozinha", desc: "Panelas penduradas e uma mesa de madeira com marcas de faca. Há uma escada estreita descendo para a adega. A sala fica ao sul.", saidas: { sul: "sala", descer: "adega" }, itens: ["fosforos"],
        npcs: [{ id: "eleonora", nome: "Eleonora", apelidos: ["governanta", "dona eleonora"], desc: "A governanta, de cabelos grisalhos e olhar cansado, mexe numa xícara de chá.",
          falas: [
            { se: { semFlags: ["falou_eleonora"], nivel: ["facil", "normal"] }, msg: "O patrão passava os dias entre relógios. O grande do hall parou na noite em que ele sumiu, e ele só confiava em números de relógio para guardar o que importava. Procure no quarto dele, depois do corredor.", poe: ["falou_eleonora"] },
            { se: { semFlags: ["falou_eleonora"], nivel: ["dificil"] }, msg: "O patrão só confiava em números de relógio. Mais do que isso, eu não sei.", poe: ["falou_eleonora"] },
            { msg: "Já lhe contei o que sei, meu jovem. Procure com paciência: nesta casa, tudo tem um mecanismo." }] }] },
      adega: { nome: "Adega", desc: "Uma adega de pedra, fria e úmida, com prateleiras de garrafas empoeiradas. A escada sobe para a cozinha.", saidas: { subir: "cozinha" }, itens: ["engrenagem"],
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro como breu, e você ouve pingos de água. Só a escada, que sobe para a cozinha, é conhecida." },
      biblioteca: { nome: "Biblioteca", desc: "Estantes até o teto, cheias de livros de relojoaria. Sobre a mesa há um candelabro. O hall fica a leste.", saidas: { leste: "hall" }, itens: ["vela"],
        cenario: { estante: { nome: "estante", apelidos: ["livros", "livro", "estantes", "mesa"],
          exame: [{ msg: "Entre os livros de mecânica, um está aberto na mesa. Uma nota do relojoeiro diz: o pêndulo só volta a andar com a engrenagem do meu pai, guardada na adega.", poe: ["sabe_engrenagem"] }] } } },
      corredor: { nome: "Corredor", desc: "Um corredor estreito, com papel de parede descascado. O hall fica ao sul, o quarto do relojoeiro a leste e a oficina a oeste.", saidas: { sul: "hall", leste: "quarto", oeste: "oficina" } },
      oficina: { nome: "Oficina", desc: "A oficina do relojoeiro, com ferramentas minúsculas penduradas em fileiras. O corredor fica a leste.", saidas: { leste: "corredor" }, itens: ["lupa", "oleo"],
        cenario: { bancada: { nome: "bancada", apelidos: ["mesa", "ferramentas"], desc: "Uma bancada de trabalho coberta de molas, parafusos e pequenas engrenagens." } } },
      quarto: { nome: "Quarto do relojoeiro", desc: "Uma cama de ferro bem arrumada e um painel de madeira na parede. O corredor fica a oeste.", saidas: { oeste: "corredor" },
        cenario: { cofre: { nome: "cofre", apelidos: ["painel", "teclado", "cofre da parede"],
          exame: [{ se: { flags: ["cofre_aberto"] }, msg: "O cofre está aberto e vazio." }, { msg: "Atrás do painel há um cofre embutido, com um teclado de quatro dígitos. Para tentar um código, escreva: digitar NÚMEROS no cofre." }] } } },
      secreta: { nome: "Sala secreta", desc: "Uma sala pequena e redonda, cheia de desenhos de relógios. Sobre uma mesa repousa um caderno de capa de couro. A escada sobe para o hall.", saidas: { subir: "hall" }, itens: ["diario"] }
    },
    itens: {
      chave_bronze: { nome: "chave de bronze", apelidos: ["chave"], desc: "Uma chave pequena de bronze, com a marca de uma fechadura de porta." },
      fosforos: { nome: "fósforos", apelidos: ["fosforo", "caixa de fosforos"], desc: "Uma caixa de fósforos, ainda secos." },
      vela: { nome: "vela", apelidos: ["candelabro"], desc: "Uma vela grossa de cera, ainda inteira." },
      engrenagem: { nome: "engrenagem", apelidos: ["roda dentada"], desc: "Uma engrenagem de latão, pesada e antiga, do tamanho de um prato pequeno." },
      lupa: { nome: "lupa", apelidos: ["lente"], desc: "Uma lupa de relojoeiro, com aro de metal." , so: ["dificil"] },
      oleo: { nome: "óleo", apelidos: ["oleo fino", "lata de oleo"], desc: "Um frasquinho de óleo fino, de lubrificar mecanismos.", so: ["dificil"] },
      chave_dourada: { nome: "chave dourada", apelidos: ["chave de ponteiro", "ponteiro"], desc: "Uma chave dourada em forma de ponteiro de relógio." },
      diario: { nome: "diário do relojoeiro", apelidos: ["diario", "caderno", "livro de couro"], desc: "Um caderno de capa de couro, com a letra miúda de Heitor." }
    },
    usos: [
      { item: "chave_bronze", alvo: "porta", sala: "hall", se: { semFlags: ["corredor_aberto"] }, falha: "A porta já está aberta.", msg: "A chave de bronze gira com um estalo, e a porta do corredor se abre.", poe: ["corredor_aberto"] },
      { item: "fosforos", se: { flags: ["luz"] }, msg: "A vela já está acesa." },
      { item: "fosforos", se: { tem: ["vela"] }, falha: "Você precisa de uma vela para ter luz.", msg: "Você risca um fósforo e acende a vela. Agora você carrega uma luz.", poe: ["luz"] },
      { item: "vela", se: { flags: ["luz"] }, msg: "A vela já está acesa." },
      { item: "vela", se: { tem: ["fosforos"] }, falha: "Você precisa de fósforos para acender a vela.", msg: "Você acende a vela com um fósforo. Agora você carrega uma luz.", poe: ["luz"] },
      { item: "engrenagem", alvo: "relogio_grande", so: ["dificil"], se: { tem: ["oleo"], semFlags: ["engrenagem_ok"] }, falha: "Você encaixa a engrenagem, mas ela está enferrujada e trava. Falta algo para lubrificar o mecanismo.",
        msg: "Você passa o óleo nos dentes da engrenagem e a encaixa no mecanismo. Ela gira macia, mas o relógio ainda está parado: parece faltar uma chave.", poe: ["engrenagem_ok"], consome: ["engrenagem", "oleo"] },
      { item: "engrenagem", alvo: "relogio_grande", nao: ["dificil"], se: { semFlags: ["engrenagem_ok"] }, falha: "A engrenagem já está no lugar.",
        msg: "Você encaixa a engrenagem no mecanismo, e ela gira. O relógio ainda está parado: parece faltar uma chave.", poe: ["engrenagem_ok"], consome: ["engrenagem"] },
      { item: "chave_dourada", alvo: "relogio_grande", se: { flags: ["engrenagem_ok"] }, falha: "A chave não gira: o mecanismo do relógio está incompleto.",
        msg: "A chave dourada gira, o pêndulo começa a balançar e o relógio se abre como uma porta. Uma escada desce por trás dele.", poe: ["passagem"] },
      { codigo: "1147", alvo: "cofre", sala: "quarto", se: { semFlags: ["cofre_aberto"] }, falha: "O cofre já está aberto.", errado: "O teclado apita: código errado.",
        msg: "O cofre faz um clique e a porta se abre. Dentro há uma chave dourada, em forma de ponteiro de relógio.", poe: ["cofre_aberto"], ganha: ["chave_dourada"] },
      { verbo: "ler", alvo: "diario", msg: "Você lê o diário. Heitor descobriu que um sócio queria roubar seus relógios e fingiu o próprio desaparecimento, escondendo-se aqui até a polícia chegar. A última página diz: se alguém ler isto, o relógio do hall foi parado de propósito, só quem entende de tempo chegaria até aqui. Mistério resolvido: Heitor está vivo e a salvo.", fim: "vitoria" }
    ],
    dicas: [
      { se: { flags: ["passagem"] }, msg: "Desça a escada atrás do relógio e leia o diário." },
      { se: { flags: ["engrenagem_ok"], tem: ["chave_dourada"] }, msg: "Use a chave dourada no relógio de pêndulo do hall." },
      { se: { flags: ["engrenagem_ok"] }, msg: "Falta a chave dourada: ela está no cofre do quarto, e o código é a hora em que o relógio parou." },
      { se: { tem: ["engrenagem"], sala: "hall" }, msg: "Use a engrenagem no relógio de pêndulo." },
      { se: { tem: ["engrenagem"] }, msg: "Leve a engrenagem ao relógio de pêndulo, no hall." },
      { se: { flags: ["luz"] }, msg: "Com a vela acesa, desça à adega pela cozinha e pegue a engrenagem." },
      { se: { tem: ["vela", "fosforos"] }, msg: "Use os fósforos para acender a vela. Assim a adega fica iluminada." },
      { se: { flags: ["corredor_aberto"] }, msg: "Para o relógio você precisa de uma engrenagem: a biblioteca e a adega são o caminho. A vela da biblioteca e os fósforos da cozinha dão a luz." },
      { se: { tem: ["chave_bronze"] }, msg: "Use a chave de bronze na porta do corredor, no hall." },
      { msg: "Explore a sala de estar, a cozinha e a biblioteca. Examine os móveis, como o sofá." }
    ],
    solucao: { facil: normal, normal: normal, dificil: dificil }
  };
  var H = raiz.Heimdall || (raiz.Heimdall = {}); H.historias = H.historias || {}; H.historias.relogios = h;
  if (typeof module !== "undefined") module.exports = h;
})(typeof window !== "undefined" ? window : globalThis);
