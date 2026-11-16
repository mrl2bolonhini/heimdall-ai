// Cinco letras: descubra a palavra secreta de 5 letras (estilo Wordle), em português. Acentos não importam na digitação.
// Cada tentativa é lida letra por letra: lugar certo, está na palavra mas em outro lugar, ou não tem. Níveis: fácil (8 tentativas e dicas), normal (6 e 1 dica) e difícil (6, sem dicas e você precisa reaproveitar o que já descobriu).
// A palavra secreta vem da lista abaixo; qualquer combinação de 5 letras vale como palpite (não há dicionário para conferir).
(function (raiz) {
  "use strict";
  var PALAVRAS = [
    "afeto", "agora", "ainda", "aluno", "amigo", "amora", "andar", "anexo", "antes", "apito", "areia", "arroz",
    "asilo", "aviso", "avião", "aroma", "atriz", "atual", "autor", "apoio", "ajuda", "alado", "ambos", "amplo",
    "aonde", "arara", "astro", "atrás", "aulas", "álbum", "baixo", "balde", "banco", "banho", "barco", "barro",
    "bater", "beijo", "beber", "bicho", "bispo", "bocal", "bolsa", "bonde", "braço", "brasa", "breve", "briga",
    "brisa", "burro", "busca", "bolos", "cabra", "cacau", "calma", "campo", "canal", "canto", "carga", "carro",
    "carta", "casal", "casas", "causa", "cedro", "cerca", "certo", "chave", "chefe", "chega", "chuva", "cinco",
    "circo", "civil", "claro", "clima", "cobra", "comer", "conto", "copos", "corpo", "couro", "creme", "crime",
    "curva", "curso", "cinza", "cheio", "ciúme", "cesta", "cesto", "coisa", "coral", "cores", "corda", "cravo",
    "dados", "dança", "datas", "dedos", "dente", "desde", "dever", "dizer", "doces", "dorme", "doido", "drama",
    "duplo", "durar", "exame", "exato", "enfim", "entre", "época", "ervas", "faixa", "falar", "falso", "farol",
    "farsa", "fazer", "feliz", "ferro", "festa", "fibra", "ficar", "filho", "final", "firme", "flora", "fluxo",
    "fogão", "folha", "fonte", "força", "forma", "forno", "forte", "fruta", "fugir", "fundo", "furar", "fumar",
    "fatos", "feira", "feixe", "galho", "ganho", "garfo", "gasto", "gente", "geral", "gesto", "globo", "golpe",
    "gordo", "graça", "grama", "grato", "grave", "grupo", "guiar", "gosto", "gripe", "hábil", "herói", "hotel",
    "horas", "humor", "ideal", "ideia", "igual", "imune", "ímpar", "irmão", "idoso", "índio", "jaula", "jeito",
    "jogar", "jogos", "jovem", "junto", "justo", "jarro", "lagoa", "lance", "lápis", "largo", "laudo", "leite",
    "lenço", "lento", "letra", "levar", "livre", "livro", "local", "longe", "lousa", "lugar", "lunar", "luzes",
    "lutar", "lindo", "linha", "limão", "lenha", "macio", "magia", "magro", "maior", "malha", "mamão", "manga",
    "manha", "mapas", "março", "massa", "matar", "medir", "mesmo", "metal", "meses", "mexer", "milho", "minha",
    "moeda", "molho", "monte", "morar", "morro", "motor", "mudar", "mundo", "muito", "museu", "nadar", "nariz",
    "natal", "nervo", "ninho", "noite", "norte", "nossa", "notas", "novos", "nuvem", "nunca", "nível", "nobre",
    "obras", "ontem", "ordem", "ouvir", "ótimo", "ombro", "opção", "outro", "órgão", "oásis", "padre", "pagar",
    "palco", "papel", "parar", "parte", "passo", "pasta", "pátio", "pausa", "peixe", "pedra", "pegar", "pente",
    "perna", "pesar", "piano", "pilha", "pista", "plano", "pobre", "poder", "podre", "poeta", "ponte", "porco",
    "porta", "posse", "pouco", "povos", "praia", "prato", "prazo", "preto", "prova", "pular", "punho", "pulso",
    "puxar", "prata", "preço", "pomba", "poção", "quase", "quero", "queda", "quilo", "rádio", "raiva", "ramos",
    "rampa", "rasgo", "razão", "reais", "regra", "reino", "resto", "rezar", "rimas", "risco", "ritmo", "rodas",
    "rolar", "roupa", "rosto", "rotas", "rubro", "ruído", "rumor", "rural", "rocha", "sabão", "sabor", "sábio",
    "saber", "safra", "saída", "salto", "samba", "santo", "sauna", "saúde", "selva", "senha", "sexta", "sinal",
    "sobre", "sogra", "solto", "sonho", "sorte", "subir", "suave", "sujar", "setor", "sítio", "sobra", "sócio",
    "sopro", "serra", "sacos", "tábua", "tarde", "tecla", "tempo", "tenda", "terra", "tigre", "tinta", "tirar",
    "tocar", "todos", "tomar", "torre", "touro", "traje", "trama", "trigo", "troca", "tropa", "trono", "turma",
    "tutor", "tosse", "traço", "trevo", "unhas", "união", "único", "usina", "vacas", "vagão", "valor", "vapor",
    "vasos", "vazio", "velho", "vento", "verbo", "verde", "verão", "vício", "vidro", "vigor", "vinho", "viver",
    "vivos", "volta", "votar", "vozes", "vulto", "visão", "vista", "zebra", "zerar", "zelar", "zumbi"
  ];
  var NIVEIS = { facil: { nome: "fácil", tent: 8, dicas: 99, rigido: false }, normal: { nome: "normal", tent: 6, dicas: 1, rigido: false }, dificil: { nome: "difícil", tent: 6, dicas: 0, rigido: true } };
  var LETRAS = "abcdefghijklmnopqrstuvwxyz";

  function plano(t) { return String(t).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, ""); }
  function sorteio(n) { return Math.floor(Math.random() * n); }
  function novo(nivel, rnd, palavra) {
    nivel = NIVEIS[nivel] ? nivel : "normal";
    var w = palavra || PALAVRAS[(rnd || sorteio)(PALAVRAS.length)];
    return { nivel: nivel, cfg: NIVEIS[nivel], palavra: w, alvo: plano(w), tentativas: [], dicasUsadas: 0, reveladas: {}, rnd: rnd, fim: null };
  }
  // 2 = lugar certo, 1 = na palavra, em outro lugar, 0 = não tem. Letras repetidas contam só quantas vezes existem na palavra.
  function avaliar(alvo, p) {
    var r = [0, 0, 0, 0, 0], resto = {}, i;
    for (i = 0; i < 5; i++) { if (p[i] === alvo[i]) r[i] = 2; else resto[alvo[i]] = (resto[alvo[i]] || 0) + 1; }
    for (i = 0; i < 5; i++) { if (r[i] === 0 && resto[p[i]] > 0) { r[i] = 1; resto[p[i]]--; } }
    return r;
  }
  var TXT = ["não tem", "em outro lugar", "lugar certo"];
  function lerResultado(p, r) { return p.split("").map(function (c, i) { return c.toUpperCase() + ": " + TXT[r[i]]; }).join(", "); }

  // O que já se sabe: letras no lugar, letras que existem, letras que não existem.
  function saber(e) {
    var lugar = ["", "", "", "", ""], existe = {}, nao = {}, i;
    Object.keys(e.reveladas || {}).forEach(function (k) { lugar[k] = e.reveladas[k]; existe[e.reveladas[k]] = true; });
    e.tentativas.forEach(function (t) {
      t.p.split("").forEach(function (c, i) { if (t.r[i] === 2) { lugar[i] = c; existe[c] = true; } else if (t.r[i] === 1) existe[c] = true; });
    });
    e.tentativas.forEach(function (t) { t.p.split("").forEach(function (c, i) { if (t.r[i] === 0 && !existe[c]) nao[c] = true; }); });
    return { lugar: lugar, existe: existe, nao: nao };
  }
  function pistas(e) {
    if (!e.tentativas.length && !Object.keys(e.reveladas).length) return "Ainda não há pistas. Dê um palpite de 5 letras.";
    var s = saber(e), padrao = s.lugar.map(function (c) { return c ? c.toUpperCase() : "traço"; }).join(", ");
    var fora = Object.keys(s.existe).filter(function (c) { return s.lugar.indexOf(c) < 0; }).sort().map(function (c) { return c.toUpperCase(); });
    var nao = Object.keys(s.nao).sort().map(function (c) { return c.toUpperCase(); });
    return "Lugares conhecidos: " + padrao + ". Letras que estão na palavra em outro lugar: " + (fora.length ? fora.join(", ") : "nenhuma") + ". Letras que não têm: " + (nao.length ? nao.join(", ") : "nenhuma") + ".";
  }
  function livres(e) {
    var s = saber(e), l = LETRAS.split("").filter(function (c) { return !s.nao[c] && !s.existe[c]; });
    return "Letras ainda não testadas: " + l.map(function (c) { return c.toUpperCase(); }).join(", ") + ".";
  }
  function lerTentativas(e) {
    if (!e.tentativas.length) return "Nenhuma tentativa ainda.";
    return e.tentativas.map(function (t, i) { return "Tentativa " + (i + 1) + ", " + t.p.toUpperCase() + ": " + lerResultado(t.p, t.r) + "."; }).join(" ");
  }
  // Modo difícil: o palpite precisa manter as letras certas no lugar e usar as letras que já se sabe que existem.
  function conferirRigido(e, p) {
    var s = saber(e), i, c;
    for (i = 0; i < 5; i++) if (s.lugar[i] && p[i] !== s.lugar[i]) return "No nível difícil a letra " + s.lugar[i].toUpperCase() + " precisa ficar na posição " + (i + 1) + ".";
    for (c in s.existe) if (p.indexOf(c) < 0) return "No nível difícil o palpite precisa usar a letra " + c.toUpperCase() + ", que já está na palavra.";
    return "";
  }
  function dica(e) {
    if (e.fim) return "A partida terminou.";
    if (e.dicasUsadas >= e.cfg.dicas) return e.cfg.dicas === 0 ? "No nível difícil não há dicas." : "A dica do nível normal já foi usada.";
    var s = saber(e), pos = [], i;
    for (i = 0; i < 5; i++) if (!s.lugar[i]) pos.push(i);
    if (!pos.length) return "Você já sabe todas as letras.";
    var k = pos[(e.rnd || sorteio)(pos.length)];
    e.dicasUsadas++;
    e.reveladas[k] = e.alvo[k];
    return "Dica: a letra da posição " + (k + 1) + " é " + e.alvo[k].toUpperCase() + ".";
  }
  function palpitar(e, texto) {
    if (e.fim) return { msg: "A partida terminou. Comece uma nova.", erro: true };
    var p = plano(texto);
    if (p.length !== 5) return { msg: "O palpite precisa ter exatamente 5 letras, e você digitou " + p.length + ". Acentos não importam.", erro: true };
    if (e.tentativas.some(function (t) { return t.p === p; })) return { msg: "Você já tentou " + p.toUpperCase() + ". Escolha outra palavra.", erro: true };
    if (e.cfg.rigido) { var avisoR = conferirRigido(e, p); if (avisoR) return { msg: avisoR, erro: true }; }
    var r = avaliar(e.alvo, p); e.tentativas.push({ p: p, r: r });
    var n = e.tentativas.length, msg = "Tentativa " + n + " de " + e.cfg.tent + ", " + p.toUpperCase() + ": " + lerResultado(p, r) + ".";
    if (p === e.alvo) { e.fim = "vitoria"; return { msg: msg + " Você acertou! A palavra é " + e.palavra.toUpperCase() + ", em " + n + (n === 1 ? " tentativa." : " tentativas."), fim: true }; }
    if (n >= e.cfg.tent) { e.fim = "derrota"; return { msg: msg + " Acabaram as tentativas. A palavra era " + e.palavra.toUpperCase() + ".", fim: true }; }
    return { msg: msg + " Restam " + (e.cfg.tent - n) + (e.cfg.tent - n === 1 ? " tentativa." : " tentativas.") };
  }
  function ajuda() {
    return "Digite uma palavra de 5 letras e confirme com Enter; acentos não importam. Depois de cada palpite você ouve, letra por letra, se ela está no lugar certo, em outro lugar ou não tem. Comandos: tentativas (repete tudo), pistas (o que já se sabe), letras (as não testadas), dica, desistir.";
  }
  function comando(e, texto) {
    var t = plano(texto), v = String(texto).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
    if (v === "ajuda" || v === "?") return { msg: ajuda() };
    if (v === "tentativas" || v === "historico") return { msg: lerTentativas(e) };
    if (v === "pistas" || v === "pista") return { msg: pistas(e) };
    if (v === "letras") return { msg: livres(e) };
    if (v === "dica") return { msg: dica(e) };
    if (v === "desistir") { if (e.fim) return { msg: "A partida terminou.", erro: true }; e.fim = "derrota"; return { msg: "Você desistiu. A palavra era " + e.palavra.toUpperCase() + ".", fim: true }; }
    if (!v) return { msg: "Digite um palpite de 5 letras, ou ajuda.", erro: true };
    return palpitar(e, texto);
  }

  var api = { PALAVRAS: PALAVRAS, NIVEIS: NIVEIS, plano: plano, novo: novo, avaliar: avaliar, palpitar: palpitar, comando: comando, pistas: pistas, lerTentativas: lerTentativas, dica: dica };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = null;
  var selNivel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { return H.el("option", { value: k, texto: NIVEIS[k].nome.charAt(0).toUpperCase() + NIVEIS[k].nome.slice(1) + ": " + NIVEIS[k].tent + " tentativas" }); }));
  selNivel.value = "normal";
  var novoBtn = H.el("button", { type: "button", texto: "Nova palavra" });
  var campo = H.el("input", { id: "palpite", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false", maxlength: "20" });
  var form = H.el("form", {}, [H.el("label", { "for": "palpite", texto: "Seu palpite de 5 letras, ou um comando (ajuda mostra tudo)" }), campo, H.el("button", { type: "submit", texto: "Tentar" })]);
  var historia = H.el("ol", { id: "historico", "aria-label": "Tentativas" });
  [H.el("label", { "for": "nivel", texto: "Nível (vale ao começar uma nova palavra)" }), selNivel, novoBtn, form, historia].forEach(function (x) { jogo.appendChild(x); });
  function escrever(m) { historia.insertBefore(H.el("li", { texto: m }), historia.firstChild); H.anunciar(m); }
  function comecar() {
    e = novo(selNivel.value); historia.textContent = ""; campo.disabled = false;
    escrever("Nova palavra de 5 letras, nível " + e.cfg.nome + ", com " + e.cfg.tent + " tentativas." + (e.cfg.rigido ? " Neste nível você precisa reaproveitar as letras já descobertas." : "") + " Digite seu primeiro palpite, ou ajuda.");
    campo.focus();
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var t = campo.value; campo.value = ""; var r = comando(e, t); escrever("> " + t + " — " + r.msg);
    if (e.fim) { campo.disabled = true; novoBtn.focus(); } else campo.focus();
  });
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
