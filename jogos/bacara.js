// Bacará (punto banco) com créditos de mentira (nunca dinheiro de verdade). Você aposta no jogador, na banca ou no empate;
// o jogo dá as cartas, aplica sozinho as regras da terceira carta e lê tudo. Valores: Ás vale 1, de 2 a 9 valem o número, 10, Valete, Dama e Rei valem 0; a mão vale a soma módulo 10.
// Pagamentos: jogador 1 para 1; banca 1 para 1, mas devolve a aposta (empate) quando a banca vence com três cartas somando 7; empate 8 para 1; no empate, as apostas no jogador e na banca são devolvidas.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", inicio: 100, dicas: 999 },
    normal: { nome: "normal", inicio: 100, dicas: 3 },
    dificil: { nome: "difícil", inicio: 60, dicas: 0 }
  };
  var APOSTA_MAX = 50;
  var NAIPES = ["c", "o", "p", "e"], NOME_NAIPE = { c: "copas", o: "ouros", p: "paus", e: "espadas" };
  var NOME_VALOR = [null, "Ás", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Valete", "Dama", "Rei"];
  var LADOS = { jogador: "jogador", banca: "banca", empate: "empate" };

  function sorteio(n) {
    if (typeof crypto !== "undefined" && crypto.getRandomValues) { var b = new Uint32Array(1); crypto.getRandomValues(b); return b[0] % n; }
    return Math.floor(Math.random() * n);
  }
  function plural(n, s, p) { return n + " " + (n === 1 ? s : p); }
  function nome(c) { return NOME_VALOR[c.r] + " de " + NOME_NAIPE[c.s]; }
  function vc(c) { return c.r >= 10 ? 0 : c.r; }
  function total(m) { return m.reduce(function (s, c) { return s + vc(c); }, 0) % 10; }
  function embaralhar(e) {
    var s = [], d, i, j, r = e.rnd;
    for (d = 0; d < 8; d++) NAIPES.forEach(function (x) { for (i = 1; i <= 13; i++) s.push({ r: i, s: x }); });
    for (i = s.length - 1; i > 0; i--) { j = r(i + 1); var t = s[i]; s[i] = s[j]; s[j] = t; }
    e.sapato = s;
  }
  function novo(nivel, rnd) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k];
    var e = { nivel: k, nome: n.nome, saldo: n.inicio, maximo: n.inicio, rnd: rnd || sorteio, sapato: [], ultima: null, hist: [], rodadas: 0, ganhas: 0, perdidas: 0, devolvidas: 0, dicas: n.dicas, fim: false };
    embaralhar(e); return e;
  }
  // A banca compra a terceira carta?  p3 é o valor da terceira carta do jogador, ou null se o jogador parou.
  function bancaCompra(tb, p3) {
    if (p3 === null) return tb <= 5;
    if (tb <= 2) return true;
    if (tb === 3) return p3 !== 8;
    if (tb === 4) return p3 >= 2 && p3 <= 7;
    if (tb === 5) return p3 >= 4 && p3 <= 7;
    if (tb === 6) return p3 === 6 || p3 === 7;
    return false;
  }
  function jogarRodada(e) {
    var s = e.sapato, J = [s.shift()], B = [s.shift()];
    J.push(s.shift()); B.push(s.shift());
    var passos = ["Jogador: " + J.map(nome).join(" e ") + ", total " + total(J) + ". Banca: " + B.map(nome).join(" e ") + ", total " + total(B) + "."], tj = total(J), tb = total(B), natural = tj >= 8 || tb >= 8;
    if (natural) passos.push("Há um natural, com " + (tj >= 8 && tb >= 8 ? "os dois" : tj >= 8 ? "o jogador" : "a banca") + " em 8 ou 9, então ninguém compra mais cartas.");
    else {
      var p3 = null;
      if (tj <= 5) { var c = s.shift(); J.push(c); p3 = vc(c); passos.push("O jogador compra " + nome(c) + " e fica com " + total(J) + "."); } else passos.push("O jogador para em " + tj + ".");
      if (bancaCompra(tb, p3)) { var d = s.shift(); B.push(d); passos.push("A banca compra " + nome(d) + " e fica com " + total(B) + "."); } else passos.push("A banca para em " + tb + ".");
    }
    var fj = total(J), fb = total(B), venc = fj > fb ? "jogador" : fb > fj ? "banca" : "empate";
    return { J: J, B: B, fj: fj, fb: fb, venc: venc, passos: passos, dragao: venc === "banca" && B.length === 3 && fb === 7 };
  }
  function apostar(e, valor, lado) {
    if (e.fim) return { msg: "Os créditos acabaram. Comece um novo jogo.", erro: true };
    if (!LADOS[lado]) return { msg: "Aposte no jogador, na banca ou no empate. Exemplo: apostar 10 banca.", erro: true };
    if (!(valor >= 1) || valor % 1 || valor > APOSTA_MAX) return { msg: "A aposta é um número inteiro de 1 a " + APOSTA_MAX + " créditos.", erro: true };
    if (valor > e.saldo) return { msg: "Você tem só " + plural(e.saldo, "crédito", "créditos") + ".", erro: true };
    var aviso = ""; if (e.sapato.length < 20) { embaralhar(e); aviso = "O sapato foi embaralhado de novo. "; }
    var r = jogarRodada(e), ret = 0, txt;
    if (lado === "empate") { if (r.venc === "empate") { ret = valor * 9; txt = "empate! Você ganhou, e a aposta paga 8 para 1: recebe " + ret; } else txt = "não deu empate, você perdeu " + valor; }
    else if (r.venc === "empate") { ret = valor; txt = "empate, a sua aposta " + (lado === "banca" ? "na " : "no ") + lado + " é devolvida"; }
    else if (r.venc === lado) { if (lado === "banca" && r.dragao) { ret = valor; txt = "a banca venceu com sete em três cartas, então a aposta só é devolvida"; } else { ret = valor * 2; txt = "o " + (lado === "banca" ? "lado da banca" : "jogador") + " venceu, você ganhou " + valor + " e recebe " + ret; } }
    else txt = "o " + (r.venc === "banca" ? "lado da banca" : "jogador") + " venceu, você perdeu " + valor;
    e.saldo += ret - valor; e.rodadas++; if (e.saldo > e.maximo) e.maximo = e.saldo;
    if (ret > valor) e.ganhas++; else if (ret === valor) e.devolvidas++; else e.perdidas++;
    e.hist.push(r.venc); if (e.hist.length > 40) e.hist.shift(); e.ultima = valor;
    var fim = ""; if (e.saldo < 1) { e.fim = true; fim = " Os créditos acabaram. Fim de jogo."; }
    return { msg: aviso + "Aposta de " + valor + (lado === "banca" ? " na " : " no ") + lado + ". " + r.passos.join(" ") + " Resultado: jogador " + r.fj + ", banca " + r.fb + ", " + (r.venc === "empate" ? "empate" : r.venc === "banca" ? "vence a banca" : "vence o jogador") + ". Para você: " + txt + ". Saldo: " + plural(e.saldo, "crédito", "créditos") + "." + fim, resultado: r.venc };
  }
  function tabela() {
    return "Pagamentos: jogador, 1 para 1; banca, 1 para 1 (se a banca vencer com três cartas somando 7, a aposta só é devolvida); empate, 8 para 1, e nesse caso as apostas no jogador e na banca são devolvidas. Valores das cartas: Ás vale 1, de 2 a 9 valem o número, 10, Valete, Dama e Rei valem 0, e a mão vale a soma, ficando só o último dígito. Natural é 8 ou 9 nas duas primeiras cartas. O jogador compra com 0 a 5; a banca segue uma tabela fixa, aplicada pelo jogo. Aposta de 1 a " + APOSTA_MAX + " créditos.";
  }
  function historico(e) {
    if (!e.hist.length) return "Ainda não houve rodadas.";
    var c = { jogador: 0, banca: 0, empate: 0 }; e.hist.forEach(function (x) { c[x]++; });
    return "Últimas " + e.hist.length + " rodadas: jogador " + c.jogador + ", banca " + c.banca + ", empate " + c.empate + ". As cinco mais recentes, da mais nova para a mais antiga: " + e.hist.slice(-5).reverse().join(", ") + ".";
  }
  function resumo(e) { return "Nível " + e.nome + ". Saldo: " + plural(e.saldo, "crédito", "créditos") + ", o maior foi " + e.maximo + ". Rodadas: " + e.rodadas + " (ganhas " + e.ganhas + ", devolvidas " + e.devolvidas + ", perdidas " + e.perdidas + ")."; }
  function dica(e) {
    if (e.fim) return { msg: "O jogo terminou." };
    if (e.dicas <= 0) return { msg: NIVEIS[e.nivel].dicas === 0 ? "No nível difícil não há dicas." : "As dicas acabaram." };
    if (NIVEIS[e.nivel].dicas < 100) e.dicas--;
    return { msg: "Dica: no bacará você não decide nada depois de apostar, só escolhe o lado. Pelas regras, a banca vence um pouco mais que o jogador, e esta versão só devolve a aposta quando a banca vence com sete em três cartas: perda média de cerca de 1% na banca e de 1,2% no jogador. O empate paga 8 para 1, mas dá cerca de 14% de vantagem à casa, então é a pior aposta." + (NIVEIS[e.nivel].dicas < 100 ? " Dicas restantes: " + e.dicas + "." : "") };
  }
  function ajuda() { return "Comandos: apostar VALOR LADO, com o lado jogador, banca ou empate (por exemplo, apostar 10 banca); repetir, para repetir a última aposta no mesmo lado; tabela; historico; saldo; dica; resumo."; }
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" ").filter(Boolean), v = p[0] || "";
    if (!t) return { msg: "Digite um comando. Experimente: apostar 10 banca, ou ajuda." };
    if (v === "ajuda") return { msg: ajuda() };
    if (v === "tabela" || v === "regras" || v === "pagamentos") return { msg: tabela() };
    if (v === "saldo") return { msg: "Saldo: " + plural(e.saldo, "crédito", "créditos") + "." };
    if (v === "resumo" || v === "status") return { msg: resumo(e) };
    if (v === "historico" || v === "placar") return { msg: historico(e) };
    if (v === "dica") return dica(e);
    if (v === "repetir") return e.ultimaAposta ? apostar(e, Math.min(e.ultimaAposta.valor, e.saldo), e.ultimaAposta.lado) : { msg: "Ainda não há aposta anterior.", erro: true };
    if (v === "apostar" || v === "aposta" || /^\d+$/.test(v)) {
      var q = v === "apostar" || v === "aposta" ? p.slice(1) : p; if (!q.length || !/^\d+$/.test(q[0])) return { msg: "Quanto e em quem? Exemplo: apostar 10 banca.", erro: true };
      var lado = q.slice(1).filter(function (x) { return ["no", "na", "em", "o", "a", "lado"].indexOf(x) < 0; })[0];
      lado = { player: "jogador", punto: "jogador", banker: "banca", tie: "empate", banqueiro: "banca", banco: "banca" }[lado] || lado;
      if (!lado) return { msg: "Em quem? Jogador, banca ou empate. Exemplo: apostar " + q[0] + " banca.", erro: true };
      var r = apostar(e, Number(q[0]), lado); if (!r.erro) e.ultimaAposta = { valor: Number(q[0]), lado: lado }; return r;
    }
    return { msg: "Não entendi. Digite ajuda para ver os comandos." };
  }

  var api = { NIVEIS: NIVEIS, novo: novo, apostar: apostar, comando: comando, total: total, bancaCompra: bancaCompra, nome: nome };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { var n = NIVEIS[k]; return H.el("option", { value: k, texto: n.nome.charAt(0).toUpperCase() + n.nome.slice(1) + ": " + n.inicio + " créditos" + (k === "facil" ? ", dicas à vontade" : k === "normal" ? ", 3 dicas" : ", sem dicas") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Comando (apostar 10 banca, repetir, tabela, historico, saldo, dica, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var valorSel = H.el("select", { id: "valor" }, [1, 2, 5, 10, 20, 50].map(function (n) { return H.el("option", { value: String(n), texto: n + (n === 1 ? " crédito" : " créditos") }); }));
  var lados = H.el("div", { role: "group", "aria-label": "Apostar" }, [["Apostar no jogador", "jogador"], ["Apostar na banca", "banca"], ["Apostar no empate", "empate"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { falar(comando(e, "apostar " + valorSel.value + " " + x[1]).msg, "apostar " + valorSel.value + " " + x[1]); }); return b;
  }));
  var extras = H.el("div", { role: "group", "aria-label": "Consultas" }, [["Repetir a aposta", "repetir"], ["Ler o saldo", "saldo"], ["Histórico", "historico"], ["Tabela de pagamentos", "tabela"], ["Dica", "dica"]].map(function (x) {
    var b = H.el("button", { type: "button", texto: x[0] }); b.addEventListener("click", function () { falar(comando(e, x[1]).msg, x[1]); }); return b;
  }));
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, H.som ? H.som.botao() : H.el("span"), H.el("label", { "for": "valor", texto: "Valor da aposta" }), valorSel, lados, extras, form].forEach(function (x) { jogo.appendChild(x); });
  function falar(m, cmd) { var c = H.som && H.som.cue(m, cmd); if (c) H.som.anunciar(c, m); else H.anunciar(m); campo.disabled = e.fim; }
  form.addEventListener("submit", function (ev) { ev.preventDefault(); var cmd = campo.value, r = comando(e, cmd); campo.value = ""; falar(r.msg, cmd); if (!e.fim) campo.focus(); });
  function comecar() { e = novo(nivelSel.value); campo.disabled = false; H.anunciar("Novo jogo, nível " + e.nome + ", com " + e.saldo + " créditos de mentira. Escolha o valor e o lado: jogador, banca ou empate. O jogo dá as cartas e lê tudo. Exemplo: apostar 10 banca."); }
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
