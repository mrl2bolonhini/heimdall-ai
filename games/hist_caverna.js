// História "A Caverna dos Ecos": aventura guiada pelo som. No escuro, o comando escutar descreve o que se ouve. Dados para o motor.js.
(function (raiz) {
  "use strict";
  var normal = ["pegar lanterna", "ir norte", "ir leste", "examinar mochila", "usar pilhas", "ir oeste", "ir oeste", "ir leste", "ir norte", "usar apito", "ir leste", "ir norte", "usar corda na saliência", "subir"];
  var dificil = ["pegar lanterna", "ir norte", "ir leste", "examinar mochila", "examinar diário", "usar pilhas", "ir oeste", "ir oeste", "pegar gancho", "ir leste", "usar gancho na corda", "ir norte", "usar apito", "digitar 32 na parede", "ir leste", "ir norte", "usar corda de escalada na saliência", "subir"];

  var h = {
    id: "caverna", titulo: "A Caverna dos Ecos",
    resumo: "Aventura guiada pelo som: ache a saída de uma caverna escura ouvindo o vento, a água e os ecos.",
    intro: "Você caiu por uma fenda no chão de uma floresta e foi parar no fundo de uma caverna. Está tudo escuro, mas a caverna fala: pingos, vento e ecos. Use o comando escutar em cada lugar, ele diz o que você ouve e para onde ir.",
    objetivo: "encontrar o caminho de volta à superfície, guiado pelo som do vento, e escalar o poço até lá em cima.",
    inicio: "queda", inventario: ["apito"],
    salas: {
      queda: { nome: "Fundo da queda", desc: "Você está no fundo do buraco por onde caiu. Há uma lanterna caída no chão. Um corredor segue ao norte.", saidas: { norte: "tunel" }, itens: ["lanterna"],
        escuta: [{ msg: "Pingos de água ao norte e, muito acima, um sopro de vento frio que você não alcança daqui." }] },
      tunel: { nome: "Túnel dos pingos", desc: "Um túnel de pedra úmida, com cruzamento de caminhos. Ao sul fica o fundo da queda, a leste um clarão de brasas, a oeste pingos e ao norte um espaço grande e vazio.",
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro, mas você sente as paredes do túnel. Ao sul fica o fundo da queda, a leste há um clarão fraco de brasas, a oeste pingos e ao norte um espaço grande e vazio.",
        saidas: { sul: "queda", leste: "acampamento", oeste: "gotejante", norte: "salao" },
        escuta: [{ msg: "Pingos fortes a oeste, o estalo de brasas a leste e um eco profundo ao norte." }] },
      acampamento: { nome: "Acampamento abandonado", desc: "Um antigo acampamento de explorador, com brasas ainda mornas que dão uma luz fraca. Há uma mochila velha e um diário aberto numa pedra. O túnel fica a oeste.", saidas: { oeste: "tunel" },
        escuta: [{ msg: "O estalo manso das brasas. Nenhum outro som." }],
        cenario: {
          mochila: { nome: "mochila", apelidos: ["mochila velha", "bolsa"],
            exame: [{ se: { semFlags: ["viu_mochila"] }, msg: "Na mochila do explorador há pilhas novas e um rolo de corda.", poe: ["viu_mochila"], ganha: ["pilhas", "corda"] }, { msg: "A mochila está vazia." }] },
          diario: { nome: "diário", apelidos: ["diario", "caderno"],
            exame: [{ se: { nivel: ["dificil"] }, msg: "O diário do explorador diz: o salão do eco responde ao apito, mas a parede só abre com o ritmo certo: três batidas, uma pausa, duas batidas. O vento sai pelo poço, depois da galeria. Para escalar, é preciso prender a corda com um gancho." }, { msg: "O diário do explorador diz: o salão do eco guarda uma fenda, e o vento sai pelo poço, depois da galeria. Basta uma corda para escalar." }] } } },
      gotejante: { nome: "Gruta dos pingos", desc: "Uma gruta baixa, com gotas caindo de estalactites numa poça rasa. Num canto, pendurado numa rocha, há um gancho de ferro. O túnel fica a leste.", saidas: { leste: "tunel" }, itens: ["gancho"],
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro, e os pingos são fortes aqui, numa poça. O túnel fica a leste.",
        escuta: [{ msg: "Gotas pingando numa poça, num ritmo lento e regular." }] },
      salao: { nome: "Salão do eco", desc: "Um salão enorme, de teto muito alto. Tudo que você diz volta como eco. O túnel fica ao sul.",
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro, e pelo eco você percebe que o espaço é enorme. O túnel fica ao sul.",
        saidas: { sul: "tunel", leste: { para: "galeria", oculta: true, requer: { flags: ["fenda"] } } },
        extras: [{ se: { flags: ["fenda"] }, msg: "Uma fenda estreita se abriu na parede leste." }],
        aoEntrar: [{ so: ["dificil"], se: { semFlags: ["luz"] }, msg: "No escuro, você pisa em falso na beira de um buraco que o eco não avisou, e cai. Fim.", fim: "derrota" }],
        escuta: [{ se: { semFlags: ["fenda"] }, msg: "Seus passos voltam como eco. Do lado leste o eco volta diferente, mais curto, como se houvesse um vazio atrás da parede." }, { se: { flags: ["fenda"] }, msg: "Um sopro de vento vem da fenda a leste." }],
        cenario: { parede: { nome: "parede leste", apelidos: ["parede", "parede do leste"], desc: "Uma parede de pedra lisa, de onde o eco volta diferente." } } },
      galeria: { nome: "Galeria dos cristais", desc: "Uma galeria estreita, com cristais que brilham quando a luz bate neles. O vento frio sopra do norte. O salão fica a oeste.",
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro, mas o vento frio sopra do norte, firme. O salão fica a oeste.",
        saidas: { oeste: "salao", norte: "poco" }, escuta: [{ msg: "O vento sopra forte do norte, com um assobio agudo." }] },
      poco: { nome: "Poço do vento", desc: "Um poço vertical, onde o vento sobe com força. Lá no alto, muito longe, há um ponto de luz do dia. Uma saliência de pedra, a uns três metros de altura, serve para prender uma corda.",
        escuro: { flags: ["luz"] }, textoEscuro: "Está escuro, e o vento sobe com força por um poço vertical, com um ponto de luz muito lá em cima. Não dá para subir sem enxergar.",
        saidas: { sul: "galeria", subir: { para: "superficie", requer: { flags: ["corda_presa"] }, msg: "Sem uma corda presa à saliência, o poço é alto demais para escalar." } },
        extras: [{ se: { flags: ["corda_presa"] }, msg: "A corda está presa à saliência e desce até você." }],
        escuta: [{ msg: "O vento sobe pelo poço com um uivo longo, e lá no alto você escuta pássaros." }],
        cenario: { saliencia: { nome: "saliência", apelidos: ["saliencia", "pedra", "saliência de pedra"], desc: "Uma saliência firme de pedra, alta, onde dá para prender uma corda." } } },
      superficie: { nome: "Superfície", desc: "Ar fresco, sol e o canto dos pássaros.", saidas: {},
        aoEntrar: [{ msg: "Você sobe pela corda, vence a saliência e chega à luz do dia, na floresta. Você escapou da Caverna dos Ecos!", fim: "vitoria" }] }
    },
    itens: {
      apito: { nome: "apito", apelidos: [], desc: "Um apito de metal que você tinha no bolso. O som dele ecoa longe." },
      lanterna: { nome: "lanterna", apelidos: [], desc: "Uma lanterna, mas sem pilhas." },
      pilhas: { nome: "pilhas", apelidos: ["pilha"], desc: "Duas pilhas novas." },
      corda: { nome: "corda", apelidos: ["rolo de corda"], desc: "Um rolo de corda forte de escalada." },
      gancho: { nome: "gancho", apelidos: ["gancho de ferro"], desc: "Um gancho de ferro pesado, bom para prender numa corda.", so: ["dificil"] },
      corda_gancho: { nome: "corda de escalada", apelidos: ["escalada", "corda com o gancho"], desc: "Uma corda com um gancho de ferro amarrado na ponta." }
    },
    usos: [
      { item: "pilhas", se: { flags: ["luz"] }, msg: "A lanterna já está acesa." },
      { item: "pilhas", se: { tem: ["lanterna"] }, falha: "Você ainda não tem uma lanterna para pôr as pilhas.", msg: "Você coloca as pilhas na lanterna e a acende. Um feixe de luz mostra a caverna.", poe: ["luz"], consome: ["pilhas"] },
      { item: "lanterna", se: { flags: ["luz"] }, msg: "A lanterna já está acesa." },
      { item: "lanterna", se: { tem: ["pilhas"] }, falha: "A lanterna está sem pilhas.", msg: "Você coloca as pilhas na lanterna e a acende. Um feixe de luz mostra a caverna.", poe: ["luz"], consome: ["pilhas"] },
      { item: "apito", sala: "salao", so: ["facil", "normal"], se: { semFlags: ["fenda"] }, msg: "Você sopra o apito. O eco volta, e do lado leste ele volta mais cedo e mais fraco. Você apalpa a parede e uma pedra solta cede: uma fenda estreita se abre!", poe: ["fenda"] },
      { item: "apito", sala: "salao", so: ["dificil"], se: { semFlags: ["fenda"] }, msg: "Você sopra o apito. O eco volta, e do lado leste ele volta em um ritmo estranho: três batidas, uma pausa, duas batidas. A parede parece responder a um código.", poe: ["ouviu_ritmo"] },
      { item: "apito", msg: "Você sopra o apito. O som ecoa e vai embora, sem resposta." },
      { codigo: "32", alvo: "parede", sala: "salao", so: ["dificil"], se: { semFlags: ["fenda"] }, falha: "A fenda já está aberta.", errado: "Você bate na parede, e nada acontece.",
        msg: "Você bate três vezes, espera, e bate duas. Uma pedra solta cede e uma fenda estreita se abre na parede leste!", poe: ["fenda"] },
      { item: "gancho", alvo: "corda", so: ["dificil"], falha: "Você precisa da corda e do gancho juntos.", msg: "Você amarra o gancho de ferro na ponta da corda. Agora você tem uma corda de escalada.", ganha: ["corda_gancho"], consome: ["gancho", "corda"] },
      { item: "corda", alvo: "saliencia", sala: "poco", nao: ["dificil"], se: { semFlags: ["corda_presa"] }, falha: "A corda já está presa.", msg: "Você joga a corda e ela se enrosca na saliência. Dá para escalar!", poe: ["corda_presa"], consome: ["corda"] },
      { item: "corda", alvo: "saliencia", sala: "poco", so: ["dificil"], msg: "Sem peso na ponta, a corda cai de volta. Ela precisa de um gancho." },
      { item: "corda_gancho", alvo: "saliencia", sala: "poco", so: ["dificil"], se: { semFlags: ["corda_presa"] }, falha: "A corda já está presa.", msg: "Você joga a corda com o gancho, que se prende na saliência. Dá para escalar!", poe: ["corda_presa"], consome: ["corda_gancho"] }
    ],
    dicas: [
      { se: { flags: ["corda_presa"] }, msg: "Suba pelo poço." },
      { se: { flags: ["fenda"], tem: ["corda"] }, msg: "Siga a fenda a leste e o vento ao norte, até o poço, e use a corda na saliência." },
      { se: { flags: ["fenda"], tem: ["corda_gancho"] }, msg: "Siga a fenda a leste e o vento ao norte, até o poço, e use a corda de escalada na saliência." },
      { se: { flags: ["fenda"] }, msg: "Falta pegar a corda na mochila do acampamento, a leste do túnel. Siga o vento até o poço." },
      { se: { flags: ["luz"], sala: "salao" }, msg: "No salão do eco, o eco do lado leste é diferente. Use o apito." },
      { se: { flags: ["luz"] }, msg: "O vento vem do norte. Vá ao salão do eco, usando escutar para se guiar, e use o apito lá." },
      { se: { tem: ["lanterna"], semFlags: ["viu_mochila"] }, msg: "As pilhas estão na mochila do acampamento: o clarão de brasas a leste do túnel." },
      { msg: "Pegue a lanterna e siga para o norte. Em cada lugar, use escutar: o som mostra o caminho." }
    ],
    solucao: { facil: normal, normal: normal, dificil: dificil }
  };
  var H = raiz.Heimdall || (raiz.Heimdall = {}); H.historias = H.historias || {}; H.historias.caverna = h;
  if (typeof module !== "undefined") module.exports = h;
})(typeof window !== "undefined" ? window : globalThis);
