// Arqueiro de áudio: um jogo guiado pelo som, em estéreo. Pássaros cruzam o céu da esquerda para a direita (ou ao contrário) e piam a cada passo;
// o som vem do lado onde o pássaro está. Você move a mira com as setas (cada passo faz um "ping" no lado da mira) e atira com a barra de espaço.
// Quando a mira e o pássaro estão no mesmo lugar, o ping da mira e o pio soam no mesmo ponto do estéreo. Corvos (som grave, só no nível difícil) não devem ser atingidos.
// A lógica é independente do som: sem áudio no navegador, o jogo fala a posição em texto. Ninguém precisa ver nada.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", tick: 900, tol: 1, flechas: 2, corvos: 0, inverte: 0 },
    normal: { nome: "normal", tick: 600, tol: 0, flechas: 1, corvos: 0, inverte: 0 },
    dificil: { nome: "difícil", tick: 420, tol: 0, flechas: 1, corvos: 0.3, inverte: 0.1 }
  };
  var ALVOS = 10, POS_MIN = 1, POS_MAX = 9, CENTRO = 5;

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function lado(p) { return p < CENTRO ? "à esquerda" : p > CENTRO ? "à direita" : "no centro"; }
  function ondeTxt(p) { return p === CENTRO ? "no centro" : p < CENTRO ? plural(CENTRO - p, "passo", "passos") + " à esquerda do centro" : plural(p - CENTRO, "passo", "passos") + " à direita do centro"; }
  function pan(p) { return (p - CENTRO) / (CENTRO - POS_MIN); }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k];
    return { nivel: k, nome: n.nome, rnd: rnd || sorteio, mira: CENTRO, alvo: null, espera: 1, lancados: 0, acertos: 0, erros: 0, fugas: 0, pontos: 0, fim: false, flechas: 0 };
  }
  // Um passo de tempo: move o alvo, faz um novo aparecer ou termina. Devolve os eventos, para o som e a fala.
  function tick(e) {
    var ev = [], n = NIVEIS[e.nivel];
    if (e.fim) return ev;
    if (!e.alvo) {
      if (e.lancados >= ALVOS) { e.fim = true; ev.push({ tipo: "fim", msg: resultado(e) }); return ev; }
      if (e.espera > 0) { e.espera--; return ev; }
      var corvo = n.corvos > 0 && e.rnd(1000) / 1000 < n.corvos, dir = e.rnd(2) ? 1 : -1;
      e.alvo = { pos: dir > 0 ? POS_MIN : POS_MAX, dir: dir, tipo: corvo ? "corvo" : "passaro" }; e.lancados++; e.flechas = n.flechas;
      ev.push({ tipo: "novo", alvo: e.alvo.tipo, pos: e.alvo.pos, msg: (corvo ? "Um corvo, de som grave, entra pela " : "Um pássaro entra pela ") + (dir > 0 ? "esquerda" : "direita") + (corvo ? ". Não atire." : ".") + " Alvo " + e.lancados + " de " + ALVOS + "." });
      return ev;
    }
    var a = e.alvo;
    if (n.inverte && a.pos > POS_MIN + 1 && a.pos < POS_MAX - 1 && e.rnd(1000) / 1000 < n.inverte) a.dir = -a.dir;
    a.pos += a.dir;
    if (a.pos < POS_MIN || a.pos > POS_MAX) {
      var t = a.tipo; e.alvo = null; e.espera = 1;
      if (t === "passaro") { e.fugas++; ev.push({ tipo: "fugiu", msg: "O pássaro escapou." }); } else ev.push({ tipo: "fugiu", msg: "O corvo foi embora." });
      return ev;
    }
    ev.push({ tipo: "move", alvo: a.tipo, pos: a.pos });
    return ev;
  }
  function mover(e, d) {
    if (e.fim) return { msg: "A partida terminou." };
    var p = Math.max(POS_MIN, Math.min(POS_MAX, e.mira + d));
    if (p === e.mira) return { msg: "A mira já está no limite " + (d < 0 ? "da esquerda" : "da direita") + ".", pos: e.mira, limite: true };
    e.mira = p; return { msg: "", pos: p };
  }
  function atirar(e) {
    if (e.fim) return { msg: "A partida terminou." };
    if (!e.alvo) return { msg: "Não há alvo no céu agora.", tipo: "vazio", pos: e.mira };
    if (e.flechas <= 0) return { msg: "Você não tem mais flechas para este alvo.", tipo: "vazio", pos: e.mira };
    var n = NIVEIS[e.nivel], a = e.alvo; e.flechas--;
    if (Math.abs(e.mira - a.pos) <= n.tol) {
      e.alvo = null; e.espera = 1;
      if (a.tipo === "corvo") { e.pontos -= 2; e.erros++; return { msg: "Você atingiu um corvo. Menos 2 pontos.", tipo: "corvo", pos: a.pos }; }
      e.acertos++; e.pontos += 3; return { msg: "Acertou o pássaro! Mais 3 pontos.", tipo: "acerto", pos: a.pos };
    }
    e.erros++; if (a.tipo === "passaro") e.pontos -= 0;
    var dist = a.pos - e.mira;
    return { msg: "Errou: o alvo estava " + plural(Math.abs(dist), "passo", "passos") + " " + (dist < 0 ? "à esquerda" : "à direita") + " da mira." + (e.flechas > 0 ? " Você ainda tem uma flecha." : ""), tipo: "erro", pos: e.mira, dist: dist };
  }
  function resultado(e) {
    var nota = e.pontos >= 24 ? "Excelente!" : e.pontos >= 15 ? "Muito bom." : e.pontos >= 6 ? "Bom começo." : "Treine mais, e use a dica de posição.";
    return "Fim da partida. Pontos: " + e.pontos + ". Acertos: " + e.acertos + " de " + ALVOS + ". Fugas: " + e.fugas + ". Tiros errados: " + e.erros + ". " + nota;
  }
  function posicao(e) {
    var s = "Sua mira está " + ondeTxt(e.mira) + ".";
    if (e.alvo) s += " " + (e.alvo.tipo === "corvo" ? "O corvo" : "O pássaro") + " está " + ondeTxt(e.alvo.pos) + ", " + (e.alvo.dir > 0 ? "indo para a direita" : "indo para a esquerda") + (e.alvo.pos === e.mira ? ". Mira e alvo estão juntos: atire!" : "") + ".";
    else s += " Não há alvo no céu.";
    return s;
  }
  function resumo(e) { return "Nível " + e.nome + ". Alvo " + Math.min(e.lancados, ALVOS) + " de " + ALVOS + ". Pontos: " + e.pontos + ", acertos " + e.acertos + ", fugas " + e.fugas + ", tiros errados " + e.erros + "."; }
  function ajuda() {
    return "Controles: seta esquerda e seta direita movem a mira, e a barra de espaço atira. Também funcionam os botões e os comandos esquerda, direita, atirar, posicao, pontos e parar. O pássaro pia a cada passo no lado onde está, e a mira faz um ping no lado dela quando você a move: quando os dois soam no mesmo ponto, atire. Pássaro acertado dá 3 pontos; no nível difícil, corvos (som grave) tiram 2.";
  }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), v = t.split(" ")[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: esquerda, direita, atirar ou ajuda." };
    if (v === "esquerda" || v === "e") { var r = mover(e, -1); r.msg = r.msg || "Mira " + lado(e.mira) + "."; return r; }
    if (v === "direita" || v === "d") { var r2 = mover(e, 1); r2.msg = r2.msg || "Mira " + lado(e.mira) + "."; return r2; }
    if (v === "atirar" || v === "tiro" || v === "a" || v === "espaco") return atirar(e);
    if (v === "posicao" || v === "onde") return { msg: posicao(e) };
    if (v === "pontos" || v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "ajuda") return { msg: ajuda() };
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, ALVOS: ALVOS, novo: novo, tick: tick, mover: mover, atirar: atirar, comando: comando, posicao: posicao, resultado: resultado, pan: pan, resumo: resumo };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  // ---- Som (Web Audio). Sem áudio, o jogo avisa e fala as posições em texto. ----
  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil"), relogio = null, ctx = null, semAudio = false;
  function audio() {
    if (ctx || semAudio) { if (ctx && ctx.state === "suspended" && ctx.resume) { try { ctx.resume(); } catch (x) { /* segue */ } } return ctx; }
    try { var AC = raiz.AudioContext || raiz.webkitAudioContext; if (!AC) { semAudio = true; return null; } ctx = new AC(); if (ctx.state === "suspended" && ctx.resume) ctx.resume(); } catch (x) { semAudio = true; ctx = null; }
    return ctx;
  }
  function bip(freq, dur, p, tipo, vol, sweep) {
    var c = audio(); if (!c) return;
    try {
      var o = c.createOscillator(), g = c.createGain(), t0 = c.currentTime, pn = c.createStereoPanner ? c.createStereoPanner() : null;
      o.type = tipo || "sine"; o.frequency.setValueAtTime(freq, t0); if (sweep) o.frequency.exponentialRampToValueAtTime(sweep, t0 + dur);
      g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol || 0.25, t0 + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      o.connect(g); if (pn) { pn.pan.value = p; g.connect(pn); pn.connect(c.destination); } else g.connect(c.destination);
      o.start(t0); o.stop(t0 + dur + 0.02);
    } catch (x) { /* sem som */ }
  }
  function som(evs) {
    evs.forEach(function (v) {
      if (v.tipo === "novo" || v.tipo === "move") { if (v.alvo === "corvo") bip(260, 0.18, pan(v.pos), "sawtooth", 0.2); else { bip(880, 0.12, pan(v.pos), "sine", 0.28); } }
    });
  }
  var campoTeclas = H.el("input", { id: "teclas", type: "text", autocomplete: "off", spellcheck: "false", "aria-label": "Área de jogo: setas movem a mira e espaço atira. Também dá para digitar comandos e apertar Enter" });
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + (k === "facil" ? ": devagar e com tolerância de um passo" : k === "normal" ? ": ritmo médio, mira exata" : ": rápido, com corvos que não se deve atingir") }); }));
  var FALA_PADRAO = { facil: "completa", normal: "curta", dificil: "minima" };
  var falaSel = H.el("select", { id: "fala" }, [["completa", "Completa: descreve tudo"], ["curta", "Curta: frases enxutas"], ["minima", "Mínima: só o essencial, como acertou, errou e 1 de 10"]].map(function (o) { return H.el("option", { value: o[0], texto: o[1] }); }));
  var ROTULO_CAMPO = {
    completa: "Área de jogo: setas movem a mira e espaço atira. Também dá para digitar comandos e apertar Enter",
    curta: "Área de jogo. Setas movem a mira, espaço atira.",
    minima: "Área de jogo."
  };
  function ajustarRotulo() { campoTeclas.setAttribute("aria-label", ROTULO_CAMPO[falaSel.value] || ROTULO_CAMPO.completa); }
  falaSel.value = FALA_PADRAO.facil;
  nivelSel.addEventListener("change", function () { falaSel.value = FALA_PADRAO[nivelSel.value] || "completa"; ajustarRotulo(); });
  falaSel.addEventListener("change", ajustarRotulo);
  // Filtra a fala conforme a narração escolhida. v descreve o que aconteceu; sem v (dicas, posição, ajuda, pontos) a fala é sempre completa, pois foi pedida.
  function dizer(msg, v) {
    if (!msg) return;
    var m = falaSel.value;
    if (m === "completa" || !v || semAudio) { H.anunciar(msg); return; }
    var t = v.tipo, c = "";
    if (t === "fim") c = m === "curta" ? "Fim. " + e.pontos + " pontos, " + e.acertos + " acertos." : "Fim. " + e.pontos + " pontos.";
    else if (m === "curta") {
      if (t === "novo") c = (v.alvo === "corvo" ? "Corvo, não atire. " : "Pássaro, ") + (v.pos < CENTRO ? "esquerda." : "direita.");
      else if (t === "fugiu") c = /corvo/.test(msg) ? "Corvo passou." : "Escapou.";
      else if (t === "acerto") c = "Acertou! Mais 3.";
      else if (t === "corvo") c = "Corvo! Menos 2.";
      else if (t === "erro") c = "Errou, " + Math.abs(v.dist) + (v.dist < 0 ? " à esquerda." : " à direita.");
      else if (t === "vazio") c = /flechas/.test(msg) ? "Sem flechas." : "Sem alvo.";
      else if (t === "alinhado") c = "Alinhado.";
      else if (v.limite) c = "Limite.";
      else c = msg;
    } else {
      if (t === "novo") c = (v.alvo === "corvo" ? "Corvo, " : "") + e.lancados + " de " + ALVOS + ".";
      else if (t === "fugiu") c = "Escapou.";
      else if (t === "acerto") c = "Acertou.";
      else if (t === "corvo") c = "Corvo.";
      else if (t === "erro") c = "Errou.";
      else if (t === "vazio") c = "Sem alvo.";
    }
    if (c) H.anunciar(c);
  }
  var iniciarBtn = H.el("button", { type: "button", texto: "Iniciar" }), pararBtn = H.el("button", { type: "button", texto: "Parar" });
  var teclado = H.el("div", { role: "group", "aria-label": "Controles" }, [["Esquerda", "esquerda"], ["Direita", "direita"], ["Atirar", "atirar"], ["Onde estou", "posicao"], ["Pontos", "pontos"], ["Ajuda", "ajuda"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { acao(x[1]); }); return b;
  }));
  var testeSom = H.el("button", { type: "button", texto: "Testar o som" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, H.el("label", { "for": "fala", texto: "Narração" }), falaSel, iniciarBtn, pararBtn, testeSom, H.el("label", { "for": "teclas", texto: "Área de jogo (setas e espaço)" }), campoTeclas, teclado].forEach(function (x) { jogo.appendChild(x); });
  function parar() { if (relogio) { raiz.clearInterval(relogio); relogio = null; } }
  function acao(txt) {
    var r = comando(e, txt); audio();
    if (txt === "esquerda" || txt === "direita") { if (!r.limite) bip(1320, 0.07, pan(e.mira), "triangle", 0.2); else bip(220, 0.08, pan(e.mira), "square", 0.1); if (e.alvo && e.mira === e.alvo.pos && !r.limite) { r.msg = "Mira alinhada com o alvo."; r.tipo = "alinhado"; } else if (!r.limite && !semAudio) r.msg = ""; }
    if (txt === "atirar") { var t = r.tipo; if (t === "acerto") { bip(600, 0.12, pan(r.pos), "square", 0.25, 1200); setTimeout(function () { bip(900, 0.15, pan(r.pos), "sine", 0.25); }, 110); } else if (t === "erro" || t === "corvo") bip(180, 0.25, pan(r.pos), "sawtooth", 0.25, 90); else bip(500, 0.08, pan(r.pos), "square", 0.1, 300); }
    dizer(r.msg, r);
  }
  function passo() {
    var evs = tick(e); som(evs);
    evs.forEach(function (v) { dizer(v.msg, v); });
    if (semAudio && e.alvo) H.anunciar("Alvo " + lado(e.alvo.pos) + ".");
    if (e.fim) parar();
  }
  function iniciar() {
    parar(); e = novo(nivelSel.value); audio();
    if (falaSel.value !== "completa" && !semAudio) H.anunciar(falaSel.value === "curta" ? "Nível " + e.nome + ", " + ALVOS + " alvos." : "Começou."); else H.anunciar("Partida iniciada, nível " + e.nome + ", " + ALVOS + " alvos. " + (semAudio ? "Seu navegador não tem áudio estéreo, então vou dizer onde o alvo está. " : "Use fones de ouvido para o estéreo. ") + "A mira começa no centro. Setas movem a mira e espaço atira.");
    relogio = raiz.setInterval(passo, NIVEIS[e.nivel].tick); campoTeclas.focus();
  }
  iniciarBtn.addEventListener("click", iniciar);
  pararBtn.addEventListener("click", function () { parar(); H.anunciar("Partida pausada. " + resumo(e) + " Aperte Iniciar para recomeçar do zero."); });
  var temposTeste = [];
  testeSom.addEventListener("click", function () {
    var c = audio();
    if (!c) { H.anunciar("Seu navegador não oferece áudio estéreo. O jogo funciona em texto: ele diz onde o alvo está."); return; }
    temposTeste.forEach(function (t) { raiz.clearTimeout(t); }); temposTeste = [];
    // Os três sons tocam primeiro, com folga entre eles, e a explicação só é falada depois do último: assim o VoiceOver não atropela os sons.
    function tocar() {
      bip(880, 0.25, -1, "sine", 0.3);
      temposTeste.push(setTimeout(function () { bip(880, 0.25, 0, "sine", 0.3); }, 700));
      temposTeste.push(setTimeout(function () { bip(880, 0.25, 1, "sine", 0.3); }, 1400));
      temposTeste.push(setTimeout(function () { H.anunciar("Você ouviu três sons: o primeiro só no fone esquerdo, o segundo no meio e o terceiro só no fone direito. Se algum veio do lado errado, confira os fones."); }, 2100));
    }
    if (c.state === "suspended" && c.resume) {
      var feito = false, ir = function () { if (!feito) { feito = true; tocar(); } };
      try { var pr = c.resume(); if (pr && pr.then) pr.then(ir, ir); else ir(); } catch (x) { ir(); }
      temposTeste.push(setTimeout(ir, 500));
    } else tocar();
  });
  // Setas e espaço valem no campo do jogo e, com a partida rodando, em qualquer lugar da página (exceto no seletor de nível, nos campos de texto e no espaço sobre botões).
  document.addEventListener("keydown", function (ev) {
    var k = ev.key, t = ev.target && ev.target.tagName, noCampo = ev.target === campoTeclas;
    if (t === "SELECT" || t === "TEXTAREA" || (t === "INPUT" && !noCampo)) return;
    if (!noCampo && !relogio) return;
    if (k === "ArrowLeft") { ev.preventDefault(); acao("esquerda"); }
    else if (k === "ArrowRight") { ev.preventDefault(); acao("direita"); }
    else if ((k === " " || k === "Spacebar") && (noCampo || (t !== "BUTTON" && t !== "A"))) { ev.preventDefault(); acao("atirar"); }
  });
  campoTeclas.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") { ev.preventDefault(); var v = campoTeclas.value; campoTeclas.value = ""; if (v) acao(v); }
  });
  H.anunciar("Arqueiro de áudio. Use fones de ouvido. Aperte Testar o som para conferir o estéreo e depois Iniciar. Se preferir, o botão Ajuda explica os controles.");
})(typeof window !== "undefined" ? window : globalThis);
