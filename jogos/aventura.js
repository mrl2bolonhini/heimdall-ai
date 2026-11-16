// "O Farol Apagado": aventura de texto. Escreva comandos como "ir norte", "olhar", "pegar lanterna", "usar chave", "inventário" ou "ajuda".
(function (raiz) {
  "use strict";
  var SALAS = {
    praia: { nome: "Praia", itens: ["fosforos"], saidas: { norte: "trilha" },
      desc: "Você está numa praia de pedras escuras, com o mar bravo à sua direita. Há uma trilha subindo ao norte." },
    trilha: { nome: "Trilha", itens: [], saidas: { sul: "praia", norte: "pe_do_farol", leste: "casa" },
      desc: "Uma trilha de terra entre arbustos. Ao sul fica a praia, ao norte o pé do farol e a leste uma casinha de madeira." },
    casa: { nome: "Casa do guarda", itens: ["lanterna", "oleo"], saidas: { oeste: "trilha", descer: "porao" },
      desc: "A casa do antigo guarda do farol, empoeirada. Há um alçapão aberto no chão que desce para o porão. A saída é a oeste." },
    porao: { nome: "Porão", itens: ["chave"], saidas: { subir: "casa" }, escuro: true,
      desc: "Um porão úmido, com caixotes velhos. Uma escada sobe para a casa." },
    pe_do_farol: { nome: "Pé do farol", itens: [], saidas: { sul: "trilha" },
      desc: "O farol se ergue à sua frente, alto e branco. A porta de ferro, ao norte, " },
    escada: { nome: "Escada em caracol", itens: [], saidas: { descer: "pe_do_farol", subir: "lampada" },
      desc: "Uma escada em caracol sobe pelo interior do farol. Descendo você volta à porta; subindo chega à sala da lâmpada." },
    lampada: { nome: "Sala da lâmpada", itens: [], saidas: { descer: "escada" },
      desc: "No alto do farol, a grande lâmpada está apagada. Ela precisa de óleo e de uma chama. A escada desce." }
  };
  var ITENS = {
    fosforos: { nome: "fósforos", desc: "Uma caixa de fósforos, ainda secos." },
    lanterna: { nome: "lanterna", desc: "Uma lanterna a pilha. Funciona." },
    oleo: { nome: "óleo", desc: "Uma lata de óleo para lamparina." },
    chave: { nome: "chave", desc: "Uma chave grande de ferro, de porta de farol." }
  };
  var DIRS = { n: "norte", s: "sul", l: "leste", o: "oeste", norte: "norte", sul: "sul", leste: "leste", oeste: "oeste", subir: "subir", sobe: "subir", descer: "descer", desce: "descer", cima: "subir", baixo: "descer" };

  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function novo() {
    var salas = {}; Object.keys(SALAS).forEach(function (k) { salas[k] = SALAS[k].itens.slice(); });
    return { sala: "praia", inv: [], itensSala: salas, porta: false, oleo: false, fim: false, passos: 0 };
  }
  function saidasDe(e) {
    var s = Object.keys(SALAS[e.sala].saidas);
    if (e.sala === "pe_do_farol" && e.porta) s.push("norte");
    return s;
  }
  function descrever(e) {
    var s = SALAS[e.sala], t = s.nome + ". " + s.desc;
    if (e.sala === "pe_do_farol") t += e.porta ? "está aberta, e a escada sobe lá dentro." : "está trancada com uma fechadura grande.";
    if (s.escuro && e.inv.indexOf("lanterna") < 0) return s.nome + ". Está escuro demais para ver qualquer coisa. Uma escada sobe para a casa.";
    var it = e.itensSala[e.sala];
    if (it.length) t += " Aqui há: " + it.map(function (i) { return ITENS[i].nome; }).join(", ") + ".";
    t += " Saídas: " + saidasDe(e).join(", ") + ".";
    return t;
  }
  function acha(nome) { var n = norm(nome); return Object.keys(ITENS).filter(function (k) { return norm(ITENS[k].nome) === n || k === n || (n === "fosforo" && k === "fosforos"); })[0] || null; }
  // O "farol" é o cenário da porta: "usar chave" funciona no pé do farol.
  function comando(e, texto) {
    var t = norm(texto), p = t.split(" "), v = p[0], resto = p.slice(1).join(" ").replace(/^(o|a|os|as|para|pra|a|ao) /, "");
    if (e.fim) return "O jogo acabou. Recarregue a partida para jogar de novo.";
    if (!t) return "Digite um comando. Experimente: olhar, ir norte, pegar lanterna, ajuda.";
    e.passos++;
    if (v === "ajuda" || v === "ajudar" || v === "h") return "Comandos: olhar; ir norte, sul, leste, oeste, subir ou descer (ou só n, s, l, o); pegar ITEM; largar ITEM; examinar ITEM; usar ITEM; inventário. Objetivo: acender a lâmpada do farol.";
    if (v === "olhar" || v === "ver") return descrever(e);
    if (v === "inventario" || v === "i" || v === "inv") return e.inv.length ? "Você carrega: " + e.inv.map(function (i) { return ITENS[i].nome; }).join(", ") + "." : "Você não carrega nada.";
    var dir = null;
    if (v === "ir" || v === "va" || v === "andar" || v === "caminhar") dir = DIRS[resto.split(" ")[0]];
    else if (DIRS[v] && p.length === 1) dir = DIRS[v];
    if (dir !== null && (v === "ir" || v === "va" || v === "andar" || v === "caminhar" || DIRS[v])) {
      if (!dir) return "Para onde? Use norte, sul, leste, oeste, subir ou descer.";
      var ss = SALAS[e.sala];
      if (e.sala === "pe_do_farol" && dir === "norte") {
        if (!e.porta) return "A porta de ferro está trancada.";
        e.sala = "escada"; return descrever(e);
      }
      var destino = ss.saidas[dir];
      if (!destino) return "Não dá para ir para " + dir + " daqui.";
      e.sala = destino; return descrever(e);
    }
    if (v === "pegar" || v === "pega" || v === "apanhar") {
      var k = acha(resto); if (!k) return "Pegar o quê?";
      if (SALAS[e.sala].escuro && e.inv.indexOf("lanterna") < 0) return "Está escuro demais para achar qualquer coisa.";
      var i = e.itensSala[e.sala].indexOf(k); if (i < 0) return "Não há " + ITENS[k].nome + " aqui.";
      e.itensSala[e.sala].splice(i, 1); e.inv.push(k); return "Você pegou: " + ITENS[k].nome + ".";
    }
    if (v === "largar" || v === "soltar") {
      var k2 = acha(resto); if (!k2 || e.inv.indexOf(k2) < 0) return "Você não tem isso.";
      e.inv.splice(e.inv.indexOf(k2), 1); e.itensSala[e.sala].push(k2); return "Você largou: " + ITENS[k2].nome + ".";
    }
    if (v === "examinar" || v === "exame" || v === "x") {
      var k3 = acha(resto); if (!k3) return "Examinar o quê?";
      if (e.inv.indexOf(k3) < 0 && e.itensSala[e.sala].indexOf(k3) < 0) return "Você não vê isso aqui.";
      return ITENS[k3].desc;
    }
    if (v === "usar" || v === "use") {
      var k4 = acha(resto); if (!k4) return "Usar o quê?";
      if (e.inv.indexOf(k4) < 0) return "Você não tem isso.";
      if (k4 === "chave") {
        if (e.sala !== "pe_do_farol") return "Não há nada para abrir aqui.";
        if (e.porta) return "A porta já está aberta.";
        e.porta = true; return "A chave gira com um rangido e a porta de ferro se abre. Ao norte, a escada sobe.";
      }
      if (k4 === "oleo") {
        if (e.sala !== "lampada") return "Esse óleo serve para a lâmpada do farol.";
        e.oleo = true; e.inv.splice(e.inv.indexOf("oleo"), 1); return "Você enche o reservatório da lâmpada com óleo. Agora falta uma chama.";
      }
      if (k4 === "fosforos") {
        if (e.sala !== "lampada") return "Acender fósforos aqui não adianta. A chama é para a lâmpada.";
        if (!e.oleo) return "Você risca um fósforo, mas a lâmpada está sem óleo e não pega.";
        e.fim = true; return "A chama sobe pelo pavio e a grande lâmpada se acende! O feixe de luz varre o mar escuro. Você acendeu o farol, e ganhou o jogo em " + e.passos + " comandos.";
      }
      if (k4 === "lanterna") return e.sala === "porao" ? "A lanterna já ilumina o porão." : "A lanterna ilumina um pouco, mas não é preciso aqui.";
    }
    return "Não entendi. Digite ajuda para ver os comandos.";
  }
  var api = { novo: novo, comando: comando, descrever: descrever };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo();
  function D(m, f) { if (H.som) H.som.dizer("historia", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var saida = H.el("ol", { id: "historico", "aria-label": "Histórico da aventura" });
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "O que você faz? (digite ajuda para ver os comandos)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var reiniciar = H.el("button", { type: "button", texto: "Recomeçar" });
  [form, saida, reiniciar].forEach(function (x) { jogo.appendChild(x); });
  function escrever(msg, voz) { saida.insertBefore(H.el("li", { texto: msg }), saida.firstChild); if (voz !== false) D(msg); }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var c = campo.value; campo.value = "";
    escrever("> " + c + " — " + comando(e, c));
    if (e.fim) { campo.disabled = true; reiniciar.focus(); } else campo.focus();
  });
  reiniciar.addEventListener("click", function () { e = novo(); campo.disabled = false; saida.textContent = ""; escrever("O Farol Apagado. " + descrever(e)); campo.focus(); });
  escrever("O Farol Apagado. Há anos o farol da ilha está sem luz. " + descrever(e));
})(typeof window !== "undefined" ? window : globalThis);
