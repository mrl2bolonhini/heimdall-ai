// A Travessia das Três Provas: aventura de escolhas numeradas, com três problemas de lógica.
// 1) travessia do rio (raposa, galinha e milho), 2) três portas com frases (só uma é verdadeira), 3) dois guardas (um só diz verdade, o outro só mente).
// Você responde digitando o número da escolha (ou apertando o botão). Cada cena lê o texto e as escolhas.
(function (raiz) {
  "use strict";
  var NIVEIS = {
    facil: { nome: "fácil", vidas: 99, dicas: 999, avisa: true },
    normal: { nome: "normal", vidas: 3, dicas: 3, avisa: false },
    dificil: { nome: "difícil", vidas: 1, dicas: 0, avisa: false }
  };
  var ITENS = ["raposa", "galinha", "milho"], ART = { raposa: "a raposa", galinha: "a galinha", milho: "o milho" };

  function novo(nivel) {
    var k = NIVEIS[nivel] ? nivel : "facil", n = NIVEIS[k];
    return { nivel: k, nome: n.nome, vidas: n.vidas, dicas: n.dicas, cena: "inicio", sub: 0, rio: rioNovo(), passosRio: 0, fim: null, erros: 0 };
  }
  function rioNovo() { return { lado: { raposa: 0, galinha: 0, milho: 0 }, barco: 0 }; }
  function nomeLado(l) { return l === 0 ? "esquerda" : "direita"; }
  // Quem fica sozinho na margem onde o barco não está: raposa come galinha, galinha come milho.
  function perigo(r) {
    var out = [], ficou = ITENS.filter(function (i) { return r.lado[i] !== r.barco; });
    if (ficou.indexOf("raposa") >= 0 && ficou.indexOf("galinha") >= 0) out.push("a raposa comeria a galinha");
    if (ficou.indexOf("galinha") >= 0 && ficou.indexOf("milho") >= 0) out.push("a galinha comeria o milho");
    return out;
  }
  function vidasTxt(e) { return e.nivel === "facil" ? "" : " Vidas: " + e.vidas + "."; }

  // Escolhas de cada cena: lista de {txt, f} onde f(e) devolve texto do que aconteceu.
  function escolhas(e) {
    if (e.fim) return [];
    if (e.cena === "inicio") return [
      { txt: "Pegar a barca do barqueiro", id: "barca" },
      { txt: "Tentar atravessar o rio a nado", id: "nado" },
      { txt: "Reler o bilhete da mensagem", id: "bilhete" }];
    if (e.cena === "rio") {
      var r = e.rio, o = [{ txt: "Atravessar para a margem " + nomeLado(1 - r.barco) + " sem levar nada", id: "sozinho" }];
      ITENS.forEach(function (i) { if (r.lado[i] === r.barco) o.push({ txt: "Atravessar para a margem " + nomeLado(1 - r.barco) + " levando " + ART[i], id: i }); });
      return o;
    }
    if (e.cena === "portas") return [1, 2, 3].map(function (n) { return { txt: "Abrir a porta " + n, id: String(n) }; });
    if (e.cena === "guardas" && e.sub === 0) return [
      { txt: "O guarda A diz a verdade e o B mente", id: "A" },
      { txt: "O guarda B diz a verdade e o A mente", id: "B" },
      { txt: "Os dois mentem", id: "ambos" }];
    if (e.cena === "guardas") return [{ txt: "Sair pela porta da esquerda", id: "esq" }, { txt: "Sair pela porta da direita", id: "dir" }];
    return [];
  }
  function descreverRio(e) {
    var r = e.rio, esq = [], dir = [];
    ITENS.forEach(function (i) { (r.lado[i] === 0 ? esq : dir).push(i); });
    function lista(a) { return a.length ? a.join(", ") : "ninguém"; }
    return "Na margem esquerda: " + lista(esq) + ". Na margem direita: " + lista(dir) + ". O barco está na margem " + nomeLado(r.barco) + " e leva você e, no máximo, um bicho ou o milho.";
  }
  function texto(e) {
    if (e.fim === "vitoria") return "Você passou pelas três provas e entregou a mensagem na cidade. Fim da aventura, você ganhou!";
    if (e.fim === "derrota") return "Suas vidas acabaram. Fim da aventura.";
    if (e.cena === "inicio") return "Você é um mensageiro com um bilhete urgente para a cidade do outro lado do rio. Para chegar lá, vai passar por três provas: o rio, as portas e os guardas. Você está na margem esquerda, ao lado de uma barca.";
    if (e.cena === "rio") return "Primeira prova: o rio. Você leva uma raposa, uma galinha e um saco de milho, e a barca só leva você e uma coisa de cada vez. Se você deixar a raposa sozinha com a galinha, ela a come; se deixar a galinha sozinha com o milho, ela o come. Leve tudo para a margem direita. " + descreverRio(e);
    if (e.cena === "portas") return "Segunda prova: três portas, e só uma esconde a saída. Cada porta tem uma frase, e só uma das três frases é verdadeira. Porta 1: A saída está nesta porta. Porta 2: A saída não está nesta porta. Porta 3: A saída não está na porta 1. Qual porta você abre?";
    if (e.cena === "guardas" && e.sub === 0) return "Terceira prova: dois guardas, A e B, na frente de duas saídas, esquerda e direita. Um deles sempre diz a verdade e o outro sempre mente, mas você não sabe qual é qual. O guarda A diz: Nós dois sempre mentimos. Quem diz a verdade?";
    if (e.cena === "guardas") return "Agora que você sabe em quem confiar, o guarda B diz: A saída certa é a porta da direita. Por qual porta você sai?";
    return "";
  }
  function listar(e) { var o = escolhas(e); return o.length ? " Escolhas: " + o.map(function (x, i) { return (i + 1) + ", " + x.txt + "."; }).join(" ") : ""; }
  function cena(e) { return texto(e) + listar(e) + vidasTxt(e); }

  function perder(e, msg) {
    if (e.nivel !== "facil") e.vidas--;
    e.erros++;
    if (e.vidas <= 0) { e.fim = "derrota"; return msg + " " + texto(e); }
    return msg + (e.nivel === "facil" ? " Tente de novo." : " Você perdeu uma vida, e ainda tem " + e.vidas + ".") + " " + listar(e).trim();
  }
  function escolher(e, n) {
    if (e.fim) return { msg: "A aventura terminou. Comece um novo jogo." };
    var o = escolhas(e);
    if (n < 1 || n > o.length) return { msg: "Escolha de 1 a " + o.length + "." + listar(e), erro: true };
    var id = o[n - 1].id;
    if (e.cena === "inicio") {
      if (id === "bilhete") return { msg: "O bilhete diz: Preciso desta mensagem aqui antes do amanhecer. Cuidado nas travessias. Assinado, a Prefeita." + listar(e) };
      if (id === "nado") return { msg: perder(e, "A corrente é forte demais. Você é arrastado e volta à margem, molhado e cansado.") };
      e.cena = "rio"; return { msg: "O barqueiro sorri e empurra a barca. " + cena(e) };
    }
    if (e.cena === "rio") {
      var r = e.rio, copia = { lado: { raposa: r.lado.raposa, galinha: r.lado.galinha, milho: r.lado.milho }, barco: r.barco };
      if (id !== "sozinho") copia.lado[id] = 1 - r.barco;
      copia.barco = 1 - r.barco;
      var pg = perigo(copia);
      if (pg.length) {
        if (NIVEIS[e.nivel].avisa) return { msg: "Melhor não: na margem " + nomeLado(r.barco) + " " + pg[0] + ". Escolha outra coisa." + listar(e), erro: true };
        e.rio = rioNovo(); e.passosRio = 0;
        return { msg: perder(e, "Você atravessa e, na margem " + nomeLado(r.barco) + ", " + pg[0] + ". A prova recomeça, com tudo de volta na margem esquerda.") + " " + descreverRio(e) };
      }
      e.rio = copia; e.passosRio++;
      if (ITENS.every(function (i) { return copia.lado[i] === 1; })) { e.cena = "portas"; return { msg: "Você atravessou com tudo, em " + e.passosRio + " viagens. Primeira prova vencida. " + cena(e) }; }
      return { msg: "Você atravessa. " + descreverRio(e) + listar(e) };
    }
    if (e.cena === "portas") {
      if (id === "2") { e.cena = "guardas"; e.sub = 0; return { msg: "Você abre a porta 2 e a saída está lá. Segunda prova vencida. " + cena(e) }; }
      var razao = id === "1" ? "Se a saída estivesse na porta 1, as frases das portas 1 e 2 seriam as duas verdadeiras." : "Se a saída estivesse na porta 3, as frases das portas 2 e 3 seriam as duas verdadeiras.";
      return { msg: perder(e, "A porta " + id + " dá num quarto vazio. " + razao) };
    }
    if (e.cena === "guardas" && e.sub === 0) {
      if (id === "B") { e.sub = 1; return { msg: "Isso: se A dissesse a verdade, a frase dele seria falsa, o que é impossível. Então A mente e B diz a verdade. " + cena(e) }; }
      return { msg: perder(e, id === "A" ? "Se A dissesse a verdade, a frase dele, que fala em dois mentirosos, seria falsa, e isso é impossível." : "Se os dois mentissem sempre, a frase de A seria verdadeira, e um mentiroso não diz a verdade.") };
    }
    if (id === "dir") { e.fim = "vitoria"; return { msg: "Você sai pela direita, pois B diz a verdade. " + texto(e), fim: "vitoria" }; }
    return { msg: perder(e, "A porta da esquerda leva a um corredor sem saída: B dizia a verdade e a saída certa era a da direita.") };
  }

  // Menor sequência de viagens a partir do estado do rio (busca em largura), para a dica e para os testes.
  function proximoRio(e) {
    function chave(r) { return r.barco + "" + ITENS.map(function (i) { return r.lado[i]; }).join(""); }
    var ini = e.rio, fila = [{ r: ini, p: [] }], vis = {}; vis[chave(ini)] = true;
    while (fila.length) {
      var a = fila.shift();
      if (ITENS.every(function (i) { return a.r.lado[i] === 1; })) return a.p;
      ["sozinho"].concat(ITENS).forEach(function (id) {
        if (id !== "sozinho" && a.r.lado[id] !== a.r.barco) return;
        var c = { lado: { raposa: a.r.lado.raposa, galinha: a.r.lado.galinha, milho: a.r.lado.milho }, barco: 1 - a.r.barco };
        if (id !== "sozinho") c.lado[id] = 1 - a.r.barco;
        if (perigo(c).length || vis[chave(c)]) return;
        vis[chave(c)] = true; fila.push({ r: c, p: a.p.concat([id]) });
      });
    }
    return [];
  }
  function dica(e) {
    if (e.fim) return { msg: "A aventura terminou." };
    if (e.dicas <= 0) return { msg: NIVEIS[e.nivel].dicas === 0 ? "No nível difícil não há dicas." : "As dicas acabaram." };
    if (NIVEIS[e.nivel].dicas < 100) e.dicas--;
    var resto = NIVEIS[e.nivel].dicas < 100 ? " Dicas restantes: " + e.dicas + "." : "", m;
    if (e.cena === "inicio") m = "Não há armadilha nesta etapa: pegue a barca. Nadar é arriscado.";
    else if (e.cena === "rio") {
      var p = proximoRio(e), id = p[0];
      m = id === "sozinho" ? "Atravesse sozinho: assim ninguém fica numa margem com um perigo." : "Leve " + ART[id] + " agora.";
      if (e.passosRio === 0) m += " O primeiro passo é levar a galinha: ela é quem causa problema com os dois outros, então não pode ficar sozinha com nenhum.";
    } else if (e.cena === "portas") m = "Suponha que a saída está numa porta e conte quantas frases ficam verdadeiras. Só serve a suposição em que exatamente uma frase é verdadeira.";
    else if (e.sub === 0) m = "Imagine que A diz a verdade: o que a frase dele, que fala dos dois, significaria? Dá certo?";
    else m = "B é o que diz a verdade. Faça o que ele diz.";
    return { msg: "Dica: " + m + resto };
  }
  function resumo(e) {
    var prova = e.cena === "inicio" ? "antes da primeira prova" : e.cena === "rio" ? "na primeira prova, o rio" : e.cena === "portas" ? "na segunda prova, as portas" : "na terceira prova, os guardas";
    return "Nível " + e.nome + ", " + (e.fim ? (e.fim === "vitoria" ? "vitória" : "derrota") : prova) + ". Erros: " + e.erros + "." + (e.nivel === "facil" ? "" : " Vidas: " + e.vidas + ".");
  }
  function ajuda() { return "Digite o número da escolha (por exemplo, 1). Outros comandos: repetir, para ler a cena e as escolhas de novo; dica; resumo; ajuda."; }
  function comando(e, txt) {
    var t = String(txt).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
    if (!t) return { msg: "Digite o número de uma escolha, ou ajuda." };
    if (/^\d+$/.test(t)) return escolher(e, Number(t));
    var m = t.match(/^(?:escolha|opcao|numero|n)\s*(\d+)$/); if (m) return escolher(e, Number(m[1]));
    if (t === "repetir" || t === "ler" || t === "cena" || t === "opcoes" || t === "escolhas") return { msg: cena(e) };
    if (t === "dica") return dica(e);
    if (t === "resumo" || t === "status" || t === "vidas") return { msg: resumo(e) };
    if (t === "ajuda") return { msg: ajuda() };
    return { msg: "Não entendi. Digite o número de uma escolha, ou ajuda." };
  }

  var api = { NIVEIS: NIVEIS, novo: novo, escolhas: escolhas, escolher: escolher, comando: comando, cena: cena, dica: dica, proximoRio: proximoRio, perigo: perigo, resumo: resumo };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), e = novo("facil");
  function D(m, f) { if (H.som) H.som.dizer("historia", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { return H.el("option", { value: k, texto: NIVEIS[k].nome.charAt(0).toUpperCase() + NIVEIS[k].nome.slice(1) + (k === "facil" ? ": sem perder vidas e com dicas" : k === "normal" ? ": 3 vidas e 3 dicas" : ": 1 vida e sem dicas") }); }));
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false", inputmode: "numeric" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "Número da escolha (ou repetir, dica, resumo, ajuda)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var lista = H.el("ol", { id: "escolhas", "aria-label": "Escolhas" });
  var novoBtn = H.el("button", { type: "button", texto: "Novo jogo" });
  [H.el("label", { "for": "nivel", texto: "Nível" }), nivelSel, novoBtn, form, lista].forEach(function (x) { jogo.appendChild(x); });
  function desenhar() {
    lista.textContent = "";
    escolhas(e).forEach(function (o, i) {
      var b = H.el("button", { type: "button", texto: o.txt }); b.addEventListener("click", function () { agir(String(i + 1)); });
      lista.appendChild(H.el("li", {}, [b]));
    });
    campo.disabled = !!e.fim;
  }
  function agir(t) { var r = comando(e, t); campo.value = ""; desenhar(); D(r.msg); if (!e.fim) campo.focus(); }
  form.addEventListener("submit", function (ev) { ev.preventDefault(); agir(campo.value); });
  novoBtn.addEventListener("click", comecar);
  function comecar() { e = novo(nivelSel.value); desenhar(); H.anunciar("Novo jogo, nível " + e.nome + ". " + cena(e)); }
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
