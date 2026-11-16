// Sons de apoio para os jogos: uma camada de acessibilidade, não o atrativo. Cada jogo avisa o que aconteceu (ficha, carta, giro, ganhou, perdeu)
// e este módulo toca um som curto. A fala só começa depois do som terminar, para o leitor de tela não atropelar os sons.
// O botão "Sons" liga e desliga tudo e a escolha fica gravada neste navegador. Sem áudio no navegador, nada muda: o jogo continua falado.
(function (raiz) {
  "use strict";
  var H = raiz.Heimdall; if (!H) return;
  var CHAVE = "heimdall_sons", desloc = 0, ctx = null, semAudio = false, ligado = true;
  try { if (raiz.localStorage && raiz.localStorage.getItem(CHAVE) === "0") ligado = false; } catch (x) { /* sem armazenamento */ }

  function audio() {
    if (ctx || semAudio) { if (ctx && ctx.state === "suspended" && ctx.resume) { try { ctx.resume(); } catch (x) { /* segue */ } } return ctx; }
    try { var AC = raiz.AudioContext || raiz.webkitAudioContext; if (!AC) { semAudio = true; return null; } ctx = new AC(); if (ctx.state === "suspended" && ctx.resume) ctx.resume(); } catch (x) { semAudio = true; ctx = null; }
    return ctx;
  }
  // Um tom: frequência, duração e atraso em segundos. Varredura opcional até outra frequência.
  function tom(c, freq, dur, atraso, tipo, vol, ate) {
    try {
      var t0 = c.currentTime + desloc + atraso, o = c.createOscillator(), g = c.createGain();
      o.type = tipo || "sine"; o.frequency.setValueAtTime(freq, t0); if (ate) o.frequency.exponentialRampToValueAtTime(ate, t0 + dur);
      g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol || 0.2, t0 + 0.008); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      o.connect(g); g.connect(c.destination); o.start(t0); o.stop(t0 + dur + 0.02);
    } catch (x) { /* sem som */ }
  }
  // Um estalo de ruído, como carta no feltro ou bola na madeira.
  function ruido(c, dur, atraso, vol, freq) {
    try {
      var n = Math.max(1, Math.floor(c.sampleRate * dur)), b = c.createBuffer(1, n, c.sampleRate), d = b.getChannelData(0), i;
      for (i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
      var s = c.createBufferSource(), f = c.createBiquadFilter(), g = c.createGain(), t0 = c.currentTime + desloc + atraso;
      s.buffer = b; f.type = "bandpass"; f.frequency.value = freq || 2500; g.gain.value = vol || 0.3;
      s.connect(f); f.connect(g); g.connect(c.destination); s.start(t0);
    } catch (x) { /* sem som */ }
  }
  // Cada som devolve a duração em milissegundos.
  var SONS = {
    ficha: function (c) { tom(c, 2200, 0.05, 0, "triangle", 0.18); tom(c, 2900, 0.06, 0.06, "triangle", 0.18); return 160; },
    carta: function (c) { ruido(c, 0.07, 0, 0.35, 3000); return 140; },
    cartas: function (c) { ruido(c, 0.07, 0, 0.35, 3000); ruido(c, 0.07, 0.15, 0.35, 2600); ruido(c, 0.07, 0.3, 0.35, 3400); return 450; },
    virar: function (c) { ruido(c, 0.06, 0, 0.3, 2200); tom(c, 700, 0.08, 0.05, "sine", 0.12, 1100); return 220; },
    giro: function (c) {
      // A bola da roleta: estalos que vão espaçando, e o último, grave, é a bola parando.
      var t = 0, gap = 0.05, i = 0;
      while (t < 2.0) { tom(c, 1500 + (i % 3) * 120, 0.025, t, "square", 0.08); t += gap; gap *= 1.16; i++; }
      tom(c, 320, 0.18, t, "triangle", 0.3); return Math.round((t + 0.25) * 1000);
    },
    rolos: function (c) {
      // Três rolos que vão parando, um depois do outro.
      var k; for (k = 0; k < 8; k++) ruido(c, 0.04, k * 0.06, 0.15, 1800);
      tom(c, 400, 0.07, 0.5, "square", 0.2); tom(c, 420, 0.07, 0.85, "square", 0.2); tom(c, 440, 0.09, 1.2, "square", 0.25); return 1400;
    },
    ganhou: function (c) { tom(c, 523, 0.12, 0, "triangle", 0.22); tom(c, 659, 0.12, 0.11, "triangle", 0.22); tom(c, 784, 0.2, 0.22, "triangle", 0.22); return 520; },
    grande: function (c) { tom(c, 523, 0.1, 0, "triangle", 0.22); tom(c, 659, 0.1, 0.1, "triangle", 0.22); tom(c, 784, 0.1, 0.2, "triangle", 0.22); tom(c, 1047, 0.35, 0.3, "triangle", 0.25); return 750; },
    perdeu: function (c) { tom(c, 330, 0.18, 0, "sawtooth", 0.12); tom(c, 247, 0.28, 0.17, "sawtooth", 0.12); return 520; },
    estourou: function (c) { tom(c, 400, 0.4, 0, "sawtooth", 0.14, 120); return 480; },
    empate: function (c) { tom(c, 440, 0.12, 0, "sine", 0.2); tom(c, 440, 0.12, 0.17, "sine", 0.2); return 400; },
    erro: function (c) { tom(c, 150, 0.12, 0, "square", 0.1); return 180; },
    ping: function (c) { tom(c, 1000, 0.1, 0, "sine", 0.2); return 160; },
    toque: function (c) { tom(c, 520, 0.05, 0, "triangle", 0.2); return 110; },
    acerto: function (c) { tom(c, 660, 0.07, 0, "sine", 0.2); tom(c, 990, 0.1, 0.07, "sine", 0.2); return 220; },
    sobe: function (c) { tom(c, 400, 0.16, 0, "sine", 0.18, 800); return 220; },
    desce: function (c) { tom(c, 800, 0.16, 0, "sine", 0.18, 400); return 220; },
    mover: function (c) { ruido(c, 0.09, 0, 0.18, 900); return 150; },
    fusao: function (c) { ruido(c, 0.07, 0, 0.18, 900); tom(c, 880, 0.08, 0.06, "triangle", 0.2); tom(c, 1320, 0.1, 0.13, "triangle", 0.2); return 300; },
    captura: function (c) { ruido(c, 0.06, 0, 0.3, 1200); tom(c, 200, 0.12, 0, "triangle", 0.25); return 200; },
    alerta: function (c) { tom(c, 880, 0.08, 0, "square", 0.12); tom(c, 880, 0.08, 0.14, "square", 0.12); return 300; },
    agua: function (c) { ruido(c, 0.25, 0, 0.2, 700); return 300; },
    tiro: function (c) { ruido(c, 0.18, 0, 0.35, 500); tom(c, 140, 0.2, 0, "triangle", 0.3, 60); return 300; },
    afundou: function (c) { ruido(c, 0.18, 0, 0.35, 500); tom(c, 160, 0.5, 0, "triangle", 0.3, 40); return 600; },
    explosao: function (c) { ruido(c, 0.4, 0, 0.5, 300); tom(c, 110, 0.5, 0, "sawtooth", 0.25, 35); return 600; },
    terra: function (c) { ruido(c, 0.05, 0, 0.2, 1500); return 100; },
    bandeira: function (c) { tom(c, 1200, 0.04, 0, "square", 0.1); tom(c, 900, 0.05, 0.05, "square", 0.1); return 140; },
    passo: function (c) { ruido(c, 0.05, 0, 0.22, 600); return 100; }
  };

  // Toca um som, ou vários em sequência, e devolve a duração total em milissegundos (0 se os sons estiverem desligados ou o navegador não tiver áudio).
  function tocar(nomes) {
    if (!ligado) return 0;
    var c = audio(); if (!c) return 0;
    var total = 0;
    (Array.isArray(nomes) ? nomes : [nomes]).forEach(function (n) {
      var f = SONS[n]; if (!f) return;
      desloc = total / 1000; total += f(c); desloc = 0;
    });
    return total;
  }
  // Escolhe os sons de uma jogada a partir do comando e da resposta falada. Comandos só de consulta não tocam nada.
  function sem(t) { return String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
  var CONSULTA = /^(ler|saldo|ajuda|mesa|apostas|historico|ultimos|tabela|regras|pagamentos|resumo|status|dica|fichas|placar|pontos|descarte|monte|base|colunas?|cartas?)$/;
  var VERBO_FICHA = /^(apostar|aposta|ante|pagar|aumentar|\d+)$/, VERBO_CARTA = /^(pedir|comprar|dobrar|dividir|dar|distribuir|continuar|proxima|nova|novo|mover|passar|virar|jogar|girar|rodada|parar|ficar|desistir|desfazer)$/;
  var RECUSA = /^(nao entendi|digite um comando|aposta invalida|voce tem so|nao ha |ha uma |ha um |nao e a sua vez|quanto|em quem|aposte (no|em|o)|a aposta (e|precisa)|o valor|os creditos acabaram\. comece|a partida terminou\. comece|o jogo terminou|essa carta|para onde|depois de dividir|para poder|o ante e|esse numero|a (duzia|coluna) vai|nao tem|nao pode|voce so pode|para dobrar|para dividir|nao e possivel)/;
  function cue(msg, cmd) {
    var m = sem(msg), v = sem(cmd).trim().split(/\s+/)[0] || "";
    if (CONSULTA.test(v)) return null;
    if (RECUSA.test(m)) return "erro";
    var lista = [];
    if (VERBO_FICHA.test(v)) lista.push("ficha"); else if (VERBO_CARTA.test(v)) lista.push(/^(continuar|nova|novo|dar|distribuir|rodada)$/.test(v) ? "cartas" : "carta");
    if (lista[0] === "ficha" && /suas cartas|sua mao|voce recebeu/.test(m)) lista.push("cartas");
    if (/estourou|passou de 21/.test(m)) lista.push("estourou");
    else if (/blackjack!|royal flush|straight flush|parabens|voce venceu|voce ganhou a partida/.test(m)) lista.push("grande");
    else if (/voce perdeu|perdeu a mao|a banca ganhou|a banca venceu|computador ganhou|desistiu|fim de jogo/.test(m)) lista.push("perdeu");
    else if (/empate|zero a zero|push/.test(m) && !/aposte|aposta no empate/.test(m)) lista.push("empate");
    else if (/voce ganhou|voce lucrou|voce venceu|lucrou|ganhou a mao|recebe/.test(m)) lista.push("ganhou");
    return lista.length ? lista : null;
  }
  // Regras por jogo: a partir do texto falado, escolhem o som. Só entram acontecimentos claros; descrições longas não tocam nada.
  var RECUSA_JOGO = /^(nao entendi|use uma letra|voce ja tentou|digite|casa invalida|jogada invalida|lance invalido|lance ilegal|nao e possivel|nao pode|nao posso|esta ocupada|ocupada|nao ha caminho|fora d[oa]|ja foi|ja atirou|essa casa|comando|nao conheco|nao sei|voce nao|nao tem como|invalido|nao existe|nao da)/;
  function desfecho(m) {
    if (/crash!|boom|pisou numa mina/.test(m)) return "explosao";
    if (/voce perdeu|a palavra era|acabaram as tentativas|toda a sua frota afundou|o computador ganhou|nao ha mais jogadas|fim de jogo|computador venceu|vitoria do computador/.test(m)) return "perdeu";
    if (/deu velha|empate/.test(m)) return "empate";
    if (/voce ganhou|ganhou!|vitoria!|acertou a senha|acertou a palavra|acertou! o numero|voce acertou|parabens|cortou todo o gramado|abriu todas as casas seguras|voce chegou ao 2048|xeque-mate! vitoria das brancas|sudoku completo/.test(m)) return "grande";
    return null;
  }
  var REGRAS = {
    forca: function (m) { return /aparece \d/.test(m) ? "acerto" : /nao existe|a palavra nao e/.test(m) ? "erro" : null; },
    senha: function (m) { var k = m.match(/(\d) digitos? no lugar certo/); return k ? (Number(k[1]) > 0 ? "acerto" : "toque") : null; },
    numero: function (m) { return /e maior que/.test(m) ? "sobe" : /e menor que/.test(m) ? "desce" : null; },
    cincoletras: function (m) { return /^tentativa \d/.test(m) ? "toque" : null; },
    velha: function (m) { return /voce jogou/.test(m) ? "toque" : null; },
    sudoku: function (m) { return /errado|errados/.test(m) ? "erro" : /^(colocado|apagado|colocou|apagou)/.test(m) ? "toque" : null; },
    xadrez: function (m) { return /xeque/.test(m) ? "alerta" : /captura|capturou|x[a-h]/.test(m) && /jogou|lance/.test(m) ? "captura" : /voce jogou|computador jogou|jogou/.test(m) ? "toque" : null; },
    naval: function (m) { var i = m.search(/acertou e afundou|: acertou|: agua|afundou/); if (i < 0) return null; var t = m.slice(i); return /^(: acertou e afundou|afundou)/.test(t) ? "afundou" : /^: acertou/.test(t) ? "tiro" : "agua"; },
    minas: function (m) { return /bandeira (colocada|marcada|posta)|marcou/.test(m) ? "bandeira" : /abriu|casa .* tem|zero minas|sem minas|aberta/.test(m) ? "terra" : null; },
    gramado: function (m) { return /sensor apitou/.test(m) ? "alerta" : /bandeira/.test(m) && /marc|pos/.test(m) ? "bandeira" : /^(cortou|andou|moveu|voce andou|voce cortou|chegou)/.test(m) ? "passo" : null; },
    g2048: function (m) { return /^moveu/.test(m) ? (/somando/.test(m) ? "fusao" : "mover") : /nada se moveu/.test(m) ? "erro" : null; },
    historia: function () { return null; }
  };
  function cueJogo(id, msg) {
    var m = sem(msg).replace(/^> .*? - /, "").replace(/^> .*? — /, "").trim();
    if (RECUSA.test(m) || RECUSA_JOGO.test(m) || /ja esta aberta|nao pode ser marcada|desmarque antes|o palpite precisa|nao esta na lista|palavra desconhecida|nao cabe nessa|nao pode mudar|use numeros de 1 a 9/.test(m)) return "erro";
    var d = desfecho(m), f = REGRAS[id], r = f ? f(m) : null;
    if (d) return r && r !== "erro" && d === "grande" ? [r, d] : d;
    return r;
  }
  // Fala com som: cue pelo jogo e pelo texto, e a fala (que pode ser outra, mais longa) vem depois.
  function dizer(id, msg, fala) {
    var c = cueJogo(id, msg), t = fala === undefined ? msg : fala;
    if (c) anunciar(c, t); else H.anunciar(t);
  }
  // Toca o som e só depois fala o texto.
  function anunciar(nomes, texto) {
    var d = nomes ? tocar(nomes) : 0;
    if (!d) { H.anunciar(texto); return; }
    raiz.setTimeout(function () { H.anunciar(texto); }, d + 120);
  }
  function botao(jogo) {
    var b = H.el("button", { type: "button", texto: "" });
    function rotulo() { b.textContent = ligado ? "Sons: ligados. Aperte para desligar" : "Sons: desligados. Aperte para ligar"; }
    b.addEventListener("click", function () {
      ligado = !ligado; rotulo();
      try { if (raiz.localStorage) raiz.localStorage.setItem(CHAVE, ligado ? "1" : "0"); } catch (x) { /* sem armazenamento */ }
      if (ligado) tocar("ping"); H.anunciar(ligado ? "Sons ligados." : "Sons desligados.");
    });
    rotulo(); if (jogo) jogo.appendChild(b); return b;
  }
  H.som = { cueJogo: cueJogo, dizer: dizer, cue: cue, tocar: tocar, anunciar: anunciar, botao: botao, ligado: function () { return ligado; } };
  if (typeof module !== "undefined") module.exports = H.som;
})(typeof window !== "undefined" ? window : globalThis);
