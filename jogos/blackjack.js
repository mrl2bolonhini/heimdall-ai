// Blackjack (vinte e um) contra a banca, com créditos de mentira (nunca dinheiro de verdade).
// Regras: vence quem chega mais perto de 21 sem passar. Ás vale 11 ou 1; Valete, Dama e Rei valem 10. Blackjack (Ás com carta de 10 nas duas primeiras cartas) paga 3 para 2.
// A banca compra até 17 e para em qualquer 17. Dá para pedir, parar, dobrar (só nas duas primeiras cartas) e dividir um par (uma vez). Não há seguro nem rendição.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", inicio: 100, dicas: 999, baralhos: 4 },
    normal: { nome: "normal", inicio: 100, dicas: 5, baralhos: 6 },
    dificil: { nome: "difícil", inicio: 60, dicas: 0, baralhos: 6 }
  };
  var APOSTA_MIN = 2, APOSTA_MAX = 50;
  var NAIPES = ["c", "o", "p", "e"], NOME_NAIPE = { c: "copas", o: "ouros", p: "paus", e: "espadas" };
  var NOME_VALOR = [null, "Ás", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Valete", "Dama", "Rei"];

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function nome(c) { return NOME_VALOR[c.r] + " de " + NOME_NAIPE[c.s]; }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function embaralhar(e) {
    var r = e.rnd, n = NIVEIS[e.nivel].baralhos, s = [], i, j, d;
    for (d = 0; d < n; d++) NAIPES.forEach(function (x) { for (i = 1; i <= 13; i++) s.push({ r: i, s: x }); });
    for (i = s.length - 1; i > 0; i--) { j = r(i + 1); var t = s[i]; s[i] = s[j]; s[j] = t; }
    e.sapato = s;
  }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k];
    var e = { nivel: k, nome: n.nome, saldo: n.inicio, maximo: n.inicio, rnd: rnd || sorteio, sapato: [], fase: "apostar", maos: [], ativa: 0, banca: [], ultima: 0, rodadas: 0, vitorias: 0, derrotas: 0, empates: 0, blackjacks: 0, dicas: n.dicas, fim: false, dobrou: false };
    embaralhar(e); return e;
  }
  function pegar(e) { return e.sapato.shift(); }
  function valorCarta(c) { return c.r === 1 ? 11 : c.r >= 10 ? 10 : c.r; }
  function valor(cartas) {
    var t = 0, ases = 0; cartas.forEach(function (c) { t += valorCarta(c); if (c.r === 1) ases++; });
    while (t > 21 && ases > 0) { t -= 10; ases--; }
    return { total: t, suave: ases > 0 };
  }
  function ehBlackjack(cartas) { return cartas.length === 2 && valor(cartas).total === 21; }
  function lerMaoTxt(cartas) { var v = valor(cartas); return cartas.map(nome).join(", ") + ": " + v.total + (v.suave && v.total < 21 ? " (com o Ás valendo 11)" : ""); }

  function banca1(e) { return "A banca mostra " + nome(e.banca[0]) + " e tem uma carta virada."; }
  function lerMao(e) {
    if (e.fase === "apostar") return "Nenhuma rodada em andamento. Saldo: " + plural(e.saldo, "crédito", "créditos") + ". Aposte com apostar N.";
    return e.maos.map(function (m, i) { return (e.maos.length > 1 ? "Mão " + (i + 1) + (i === e.ativa && e.fase === "jogar" ? " (a ativa)" : "") + ", aposta " + m.aposta + ": " : "Sua mão, aposta " + m.aposta + ": ") + lerMaoTxt(m.cartas) + (m.fechada ? (valor(m.cartas).total > 21 ? ", estourou" : ", fechada") : ""); }).join(". ") + ". " + banca1(e);
  }
  function resumo(e) {
    return "Nível " + e.nome + ". Saldo: " + plural(e.saldo, "crédito", "créditos") + ", o maior foi " + e.maximo + ". Rodadas: " + e.rodadas + " (vitórias " + e.vitorias + ", empates " + e.empates + ", derrotas " + e.derrotas + ", blackjacks " + e.blackjacks + "). No sapato restam " + e.sapato.length + " cartas.";
  }
  function tabela() {
    return "Pagamentos: vitória paga o dobro da aposta (você recebe a aposta mais um tanto igual); blackjack natural paga 3 para 2; empate devolve a aposta; derrota perde a aposta. A banca compra até 17 e para em qualquer 17. Aposta de " + APOSTA_MIN + " a " + APOSTA_MAX + " créditos, sempre um número par.";
  }

  function apostar(e, n) {
    if (e.fim) return { msg: "Os créditos acabaram. Comece um novo jogo." };
    if (e.fase !== "apostar") return { msg: "Há uma rodada em andamento. Termine com pedir ou parar.", erro: true };
    if (!(n >= APOSTA_MIN) || n > APOSTA_MAX || n % 2) return { msg: "A aposta precisa ser um número par de " + APOSTA_MIN + " a " + APOSTA_MAX + " créditos.", erro: true };
    if (n > e.saldo) return { msg: "Você tem só " + plural(e.saldo, "crédito", "créditos") + ". Aposte menos.", erro: true };
    var aviso = "";
    if (e.sapato.length < 30) { embaralhar(e); aviso = "O sapato foi embaralhado de novo. "; }
    e.saldo -= n; e.ultima = n; e.dobrou = false;
    e.maos = [{ cartas: [pegar(e)], aposta: n, fechada: false, dividida: false }]; e.banca = [];
    e.maos[0].cartas.push(pegar(e)); // jogador recebe duas
    e.banca.push(pegar(e)); e.banca.push(pegar(e));
    e.ativa = 0; e.fase = "jogar";
    var m = e.maos[0], msg = aviso + "Aposta de " + n + ". Suas cartas: " + lerMaoTxt(m.cartas) + ". " + banca1(e);
    var bjJ = ehBlackjack(m.cartas), bjB = ehBlackjack(e.banca);
    if (bjJ || bjB) return { msg: msg + " " + liquidar(e, true).msg };
    return { msg: msg + " Você pode pedir, parar" + (podeDobrar(e) ? ", dobrar" : "") + (podeDividir(e) ? " ou dividir" : "") + "." };
  }
  function podeDobrar(e) { var m = e.maos[e.ativa]; return e.fase === "jogar" && m && m.cartas.length === 2 && e.saldo >= m.aposta && !m.fechada && !m.ases; }
  function podeDividir(e) {
    var m = e.maos[e.ativa];
    return e.fase === "jogar" && m && e.maos.length === 1 && m.cartas.length === 2 && valorCarta(m.cartas[0]) === valorCarta(m.cartas[1]) && e.saldo >= m.aposta && !m.fechada;
  }
  // Passa para a próxima mão aberta; se não houver, a banca joga e a rodada é paga.
  function avancar(e, prefixo) {
    var i; for (i = 0; i < e.maos.length; i++) if (!e.maos[i].fechada) break;
    if (i >= e.maos.length) return { msg: prefixo + " " + liquidar(e, false).msg };
    e.ativa = i; var m = e.maos[i], extra = "";
    if (m.cartas.length === 1) { m.cartas.push(pegar(e)); extra = " Mão " + (i + 1) + " recebeu " + nome(m.cartas[1]) + ": " + lerMaoTxt(m.cartas) + "."; if (valor(m.cartas).total === 21) { m.fechada = true; return avancar(e, prefixo + extra + " Vinte e um, a mão fecha sozinha."); } }
    return { msg: prefixo + extra + (e.maos.length > 1 ? " Agora é a mão " + (i + 1) + ": " + lerMaoTxt(m.cartas) + "." : "") };
  }
  function pedir(e) {
    if (e.fase !== "jogar") return { msg: "Não há rodada em andamento. Aposte com apostar N.", erro: true };
    var m = e.maos[e.ativa]; if (m.ases) return { msg: "Depois de dividir ases, cada mão recebe só uma carta.", erro: true };
    var c = pegar(e); m.cartas.push(c); var v = valor(m.cartas), pre = "Você recebeu " + nome(c) + ". " + lerMaoTxt(m.cartas) + ".";
    if (v.total > 21) { m.fechada = true; return avancar(e, pre + " Estourou!"); }
    if (v.total === 21) { m.fechada = true; return avancar(e, pre + " Vinte e um, a mão fecha sozinha."); }
    return { msg: pre };
  }
  function parar(e) {
    if (e.fase !== "jogar") return { msg: "Não há rodada em andamento. Aposte com apostar N.", erro: true };
    e.maos[e.ativa].fechada = true; return avancar(e, "Você parou em " + valor(e.maos[e.ativa].cartas).total + ".");
  }
  function dobrar(e) {
    if (!podeDobrar(e)) return { msg: e.fase !== "jogar" ? "Não há rodada em andamento." : "Só dá para dobrar nas duas primeiras cartas e com créditos para igualar a aposta.", erro: true };
    var m = e.maos[e.ativa]; e.saldo -= m.aposta; m.aposta *= 2; m.dobrou = true; e.dobrou = true;
    var c = pegar(e); m.cartas.push(c); m.fechada = true; var v = valor(m.cartas);
    return avancar(e, "Aposta dobrada para " + m.aposta + ". Você recebeu " + nome(c) + ". " + lerMaoTxt(m.cartas) + "." + (v.total > 21 ? " Estourou!" : ""));
  }
  function dividir(e) {
    if (!podeDividir(e)) return { msg: e.fase !== "jogar" ? "Não há rodada em andamento." : "Só dá para dividir duas cartas do mesmo valor, uma vez, e com créditos para uma segunda aposta igual.", erro: true };
    var m = e.maos[0], b = m.cartas.pop(), ases = m.cartas[0].r === 1;
    e.saldo -= m.aposta; m.dividida = true; m.cartas = [m.cartas[0]];
    var m2 = { cartas: [b], aposta: m.aposta, fechada: false, dividida: true }; e.maos.push(m2);
    var msg = "Você dividiu o par em duas mãos, cada uma com aposta de " + m.aposta + ".";
    if (ases) { m.ases = m2.ases = true; m.cartas.push(pegar(e)); m2.cartas.push(pegar(e)); m.fechada = m2.fechada = true; msg += " Com ases, cada mão recebe só uma carta. Mão 1: " + lerMaoTxt(m.cartas) + ". Mão 2: " + lerMaoTxt(m2.cartas) + "."; return avancar(e, msg); }
    m.cartas.push(pegar(e)); e.ativa = 0;
    var v = valor(m.cartas); msg += " Mão 1 recebeu " + nome(m.cartas[1]) + ": " + lerMaoTxt(m.cartas) + ".";
    if (v.total === 21) { m.fechada = true; return avancar(e, msg + " Vinte e um, a mão fecha sozinha."); }
    return { msg: msg };
  }
  // A banca joga (se preciso) e todas as mãos são pagas.
  function liquidar(e, natural) {
    var vivas = e.maos.some(function (m) { return valor(m.cartas).total <= 21; }), partes = [], pagar = 0, b;
    var bjB = ehBlackjack(e.banca) && !e.maos[0].dividida;
    if (vivas && !natural) { while (valor(e.banca).total < 17) e.banca.push(pegar(e)); }
    b = valor(e.banca).total;
    var intro = "A banca mostra a carta virada: " + lerMaoTxt(e.banca) + (b > 21 ? ", estourou." : ".");
    e.maos.forEach(function (m, i) {
      var v = valor(m.cartas).total, bj = ehBlackjack(m.cartas) && !m.dividida, rot = e.maos.length > 1 ? "Mão " + (i + 1) + ": " : "", ganho = 0, txt;
      if (bj && bjB) { ganho = m.aposta; txt = "blackjack dos dois, empate"; e.empates++; }
      else if (bj) { ganho = m.aposta * 2.5; txt = "blackjack! Paga 3 para 2"; e.vitorias++; e.blackjacks++; }
      else if (bjB) { txt = "a banca tem blackjack, você perdeu"; e.derrotas++; }
      else if (v > 21) { txt = "você estourou e perdeu"; e.derrotas++; }
      else if (b > 21 || v > b) { ganho = m.aposta * 2; txt = "você ganhou"; e.vitorias++; }
      else if (v === b) { ganho = m.aposta; txt = "empate, a aposta volta"; e.empates++; }
      else { txt = "a banca vence com " + b + " contra " + v; e.derrotas++; }
      pagar += ganho; partes.push(rot + txt + (ganho > m.aposta ? ", você recebe " + ganho : ganho === m.aposta ? "" : ", você perde " + m.aposta) + ".");
    });
    e.saldo += pagar; e.rodadas++; e.fase = "apostar"; if (e.saldo > e.maximo) e.maximo = e.saldo;
    var fim = "";
    if (e.saldo < APOSTA_MIN) { e.fim = true; fim = " Os créditos acabaram. Fim de jogo."; }
    return { msg: intro + " " + partes.join(" ") + " Saldo: " + plural(e.saldo, "crédito", "créditos") + "." + fim };
  }

  // Estratégia básica simplificada, para a dica.
  function sugestao(e) {
    var m = e.maos[e.ativa], v = valor(m.cartas), up = valorCarta(e.banca[0]), pd = podeDobrar(e), ps = podeDividir(e), c0 = valorCarta(m.cartas[0]);
    function dobra(ou) { return pd ? "dobrar" : ou; }
    if (ps) {
      if (m.cartas[0].r === 1 || c0 === 8) return "dividir";
      if (c0 === 9 && up !== 7 && up < 10) return "dividir";
      if (c0 === 7 && up <= 7) return "dividir";
      if (c0 === 6 && up <= 6) return "dividir";
      if ((c0 === 2 || c0 === 3) && up <= 7) return "dividir";
    }
    if (v.suave && !m.ases) {
      var o = v.total - 11; // segunda carta, de 2 a 9
      if (o <= 3) return up === 5 || up === 6 ? dobra("pedir") : "pedir";
      if (o <= 5) return up >= 4 && up <= 6 ? dobra("pedir") : "pedir";
      if (o === 6) return up >= 3 && up <= 6 ? dobra("pedir") : "pedir";
      if (o === 7) return up >= 3 && up <= 6 ? dobra("parar") : up === 2 || up === 7 || up === 8 ? "parar" : "pedir";
      return "parar";
    }
    var t = v.total;
    if (t >= 17) return "parar";
    if (t >= 13) return up <= 6 ? "parar" : "pedir";
    if (t === 12) return up >= 4 && up <= 6 ? "parar" : "pedir";
    if (t === 11) return up === 11 ? "pedir" : dobra("pedir");
    if (t === 10) return up <= 9 ? dobra("pedir") : "pedir";
    if (t === 9) return up >= 3 && up <= 6 ? dobra("pedir") : "pedir";
    return "pedir";
  }
  function dica(e) {
    if (e.dicas <= 0) return { msg: NIVEIS[e.nivel].dicas === 0 ? "No nível difícil não há dicas." : "As dicas acabaram." };
    var t;
    if (e.fim) return { msg: "O jogo terminou." };
    if (e.fase === "apostar") t = "Aposte uma parte pequena do saldo, de 2 a " + Math.max(2, Math.min(APOSTA_MAX, Math.floor(e.saldo / 10) * 2 || 2)) + " créditos, para aguentar uma sequência ruim.";
    else { var s = sugestao(e); t = "a jogada mais segura, pela estratégia básica, é " + s + "."; }
    if (NIVEIS[e.nivel].dicas < 100) e.dicas--;
    return { msg: "Dica: " + (e.fase === "apostar" ? t : t.charAt(0).toUpperCase() + t.slice(1)) + (NIVEIS[e.nivel].dicas < 100 ? " Dicas restantes: " + e.dicas + "." : "") };
  }
  function ajuda() {
    return "Comandos: apostar N (um número par de 2 a 50) ou repetir, para apostar o mesmo valor; pedir, parar, dobrar, dividir; mao, para ler suas cartas; banca; saldo; tabela, para ver os pagamentos; dica; resumo.";
  }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: apostar 2, ou ajuda." };
    if (v === "ajuda") return { msg: ajuda() };
    if (v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "saldo") return { msg: "Saldo: " + plural(e.saldo, "crédito", "créditos") + "." };
    if (v === "tabela" || v === "regras" || v === "pagamentos") return { msg: tabela() };
    if (v === "mao" || v === "cartas" || v === "ler") return { msg: lerMao(e) };
    if (v === "banca") return { msg: e.fase === "jogar" ? banca1(e) : "Não há rodada em andamento." };
    if (v === "dica") return dica(e);
    if (v === "pedir" || v === "p" || v === "carta" || v === "hit") return pedir(e);
    if (v === "parar" || v === "stand" || v === "fico") return parar(e);
    if (v === "dobrar" || v === "dobro") return dobrar(e);
    if (v === "dividir" || v === "split") return dividir(e);
    if (v === "repetir") return e.ultima ? apostar(e, Math.min(e.ultima, e.saldo - (e.saldo % 2))) : { msg: "Ainda não há aposta anterior. Use apostar N.", erro: true };
    if (v === "apostar" || v === "aposta" || /^\d+$/.test(v)) { var n = Number((t.match(/\d+/) || [""])[0]); return n ? apostar(e, n) : { msg: "Quanto? Exemplo: apostar 10.", erro: true }; }
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, novo: novo, valor: valor, apostar: apostar, pedir: pedir, parar: parar, dobrar: dobrar, dividir: dividir, comando: comando, sugestao: sugestao, nome: nome, podeDobrar: podeDobrar, podeDividir: podeDividir, ehBlackjack: ehBlackjack };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + ": " + n.inicio + " créditos" + (k === "facil" ? ", dicas à vontade" : k === "normal" ? ", 5 dicas" : ", sem dicas") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (apostar 10, pedir, parar, dobrar, dividir, mao, banca, saldo, tabela, dica, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var atalhos = H.el("div", { role: "group", "aria-label": "Jogadas" }, [["Pedir", "pedir"], ["Parar", "parar"], ["Dobrar", "dobrar"], ["Dividir", "dividir"], ["Ler a mão", "mao"], ["Ler o saldo", "saldo"], ["Dica", "dica"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { falar(comando(e, x[1]).msg, x[1]); }); return b;
  }));
  var apostaSel = H.el("select", { id: "aposta" }, [2, 4, 10, 20, 50].map(function (n) { return H.el("option", { value: String(n), texto: n + " créditos" }); }));
  var apostarBtn = H.el("button", { type: "button", texto: "Apostar" });
  var repetirBtn = H.el("button", { type: "button", texto: "Repetir a aposta" });
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, H.som ? H.som.botao() : H.el("span"), H.el("label", { "for": "aposta", texto: "Valor da aposta" }), apostaSel, apostarBtn, repetirBtn, form, atalhos].forEach(function (x) { jogo.appendChild(x); });
  function falar(m, cmd) { var c = H.som && H.som.cue(m, cmd); if (c) H.som.anunciar(c, m); else H.anunciar(m); campo.disabled = e.fim; }
  apostarBtn.addEventListener("click", function () { falar(comando(e, "apostar " + apostaSel.value).msg, "apostar " + apostaSel.value); });
  repetirBtn.addEventListener("click", function () { falar(comando(e, "repetir").msg, "repetir"); });
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var cmd = campo.value, r = comando(e, cmd); campo.value = ""; falar(r.msg, cmd); if (!e.fim) campo.focus(); });
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo jogo, nível " + e.nome + ", com " + e.saldo + " créditos de mentira. Escolha o valor e aperte Apostar, ou digite apostar 10. Dica: o comando ajuda lista tudo."); }
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
