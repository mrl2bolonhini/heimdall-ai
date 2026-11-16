// Teste de fumaça da interface dos jogos com um DOM de mentira: carrega cada jogo, aciona campos e botões e confere o que é anunciado.
const assert = require("assert"), path = require("path");
let falhas = 0, ok = 0;
const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { falhas++; console.log("FALHOU " + n + "\n     " + String(e.stack || e).split("\n").slice(0, 3).join(" | ")); } };

class El {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.style = {}; this._t = ""; this.value = ""; this.disabled = false; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "id") reg[v] = this; }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(c) { this.children.push(c); return c; }
  insertBefore(n) { this.children.unshift(n); return n; }
  get firstChild() { return this.children[0] || null; }
  set textContent(v) { this._t = String(v); this.children = []; }
  get textContent() { return this._t + this.children.map(c => c.textContent).join(" "); }
  addEventListener(tp, f) { (this.listeners[tp] = this.listeners[tp] || []).push(f); }
  fire(tp, ev) { (this.listeners[tp] || []).forEach(f => f(Object.assign({ preventDefault() {}, target: this }, ev || {}))); }
  focus() { document.activeElement = this; }
  all(tag) { return this.children.reduce((a, c) => a.concat(c.tag === tag ? [c] : [], c.all(tag)), []); }
}
let reg = {};
const doc = { activeElement: { tagName: "BODY" }, body: {}, createElement: (t) => new El(t), getElementById: (i) => reg[i] || null, listeners: {}, addEventListener(tp, f) { (this.listeners[tp] = this.listeners[tp] || []).push(f); } };
global.document = doc; global.window = global; global.setTimeout = (f) => f();
function carregar(nome, historia) {
  reg = {}; doc.listeners = {};
  const jogo = new El("div"); jogo.setAttribute("id", "jogo"); const an = new El("div"); an.setAttribute("id", "anuncio");
  if (historia) jogo.setAttribute("data-historia", historia);
  (historia ? ["base.js", "som.js", nome + ".js", "motor.js"] : ["base.js", "som.js", nome + ".js"]).forEach(f => { const p = path.join(__dirname, "jogos", f); delete require.cache[require.resolve(p)]; require(p); });
  return { jogo, an, id: (i) => reg[i] };
}
const botaoPorTexto = (jogo, txt) => jogo.all("button").filter(b => b.textContent === txt)[0];

t("forca: sorteia, aceita letra e ganha/perde pela interface", () => {
  const j = carregar("forca"); assert(/Categoria/.test(j.an.textContent));
  const campo = j.id("tentativa"), form = j.jogo.all("form")[0];
  campo.value = "z"; form.fire("submit"); assert(/Palavra:/.test(j.id("palavra").textContent));
  assert(/Erros: \d de 7/.test(j.id("info").textContent));
  for (const c of "bcdfghjklmnpqrstvwxyz") { if (!campo.disabled) { campo.value = c; form.fire("submit"); } }
  botaoPorTexto(j.jogo, "Nova rodada").fire("click"); assert(!campo.disabled && /Nova rodada/.test(j.an.textContent));
});
t("senha: palpite inválido, válido e nova senha", () => {
  const j = carregar("senha"), campo = j.id("palpite"), form = j.jogo.all("form")[0];
  campo.value = "12"; form.fire("submit"); assert(/exatamente 4/.test(j.an.textContent));
  campo.value = "1234"; form.fire("submit"); assert(/dígito/.test(j.an.textContent) || /Acertou/.test(j.an.textContent)); assert.equal(j.id("historico").children.length, 1);
  for (let i = 0; i < 12 && !campo.disabled; i++) { campo.value = "1111"; form.fire("submit"); }
  assert(campo.disabled); botaoPorTexto(j.jogo, "Nova senha").fire("click"); assert(!campo.disabled && j.id("historico").children.length === 0);
});
t("numero: dicas e acerto", () => {
  const j = carregar("numero"), campo = j.id("palpite"), form = j.jogo.all("form")[0];
  campo.value = "abc"; form.fire("submit"); assert(/inteiro de 1 a 100/.test(j.an.textContent));
  let achou = false; for (let n = 1; n <= 100 && !achou; n++) { campo.value = String(n); form.fire("submit"); achou = /Acertou/.test(j.an.textContent); }
  assert(achou && campo.disabled);
});
t("velha: joga, computador responde e o nível troca", () => {
  const j = carregar("velha"), casas = j.jogo.all("button").filter(b => /linha/.test(b.getAttribute("aria-label") || ""));
  assert.equal(casas.length, 9); casas[0].fire("click");
  assert(/Você jogou em linha 1, coluna 1/.test(j.an.textContent) && /O computador jogou/.test(j.an.textContent));
  assert.equal(casas.filter(b => b.disabled).length, 2);
  j.id("nivel").fire("click"); assert(/fácil/.test(j.id("nivel").textContent) && casas.every(b => !b.disabled));
  for (let i = 0; i < 9; i++) casas.filter(b => !b.disabled).slice(0, 1).forEach(b => b.fire("click"));
  assert(/ganhou|velha|empate/i.test(j.an.textContent) || /Sua vez/.test(j.an.textContent));
});
t("2048: botões, setas, ler tabuleiro e nova partida", () => {
  const j = carregar("g2048"); assert(/Nova partida\. Linha 1/.test(j.an.textContent));
  let moveu = false; ["Esquerda", "Direita", "Cima", "Baixo"].forEach(n => { botaoPorTexto(j.jogo, n).fire("click"); moveu = moveu || /Moveu/.test(j.an.textContent); }); assert(moveu);
  botaoPorTexto(j.jogo, "Ler o tabuleiro").fire("click"); assert(/Linha 4:/.test(j.an.textContent));
  const antes = j.id("info") ? 0 : 0; doc.listeners.keydown.forEach(f => f({ key: "ArrowLeft", target: { tagName: "BODY" }, preventDefault() {} }));
  doc.listeners.keydown.forEach(f => f({ key: "ArrowLeft", target: { tagName: "INPUT" }, preventDefault() { throw new Error("não deveria agir em campo de texto"); } }));
  botaoPorTexto(j.jogo, "Nova partida").fire("click"); assert(/Nova partida/.test(j.an.textContent));
});
t("aventura: história, comando e recomeço", () => {
  const j = carregar("aventura"), campo = j.id("comando"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/O Farol Apagado/.test(hist.textContent));
  campo.value = "pegar fósforos"; form.fire("submit"); assert(/Você pegou: fósforos/.test(j.an.textContent) && hist.children.length === 2);
  assert(/^> pegar fósforos/.test(hist.children[0].textContent));
  botaoPorTexto(j.jogo, "Recomeçar").fire("click"); assert.equal(hist.children.length, 1);
});
t("caça-níqueis: gira, lê saldo, prêmios e nova partida", () => {
  const j = carregar("cacaniqueis"); assert(/Caça-níqueis/.test(j.an.textContent) && /30 créditos/.test(j.an.textContent));
  j.id("aposta").value = "1"; botaoPorTexto(j.jogo, "Girar").fire("click"); assert(/Saiu:/.test(j.an.textContent) && /Saldo:/.test(j.an.textContent));
  assert(/^\[ \d \| \d \| \d \]$/.test(j.id("painel").textContent) && j.id("painel").attrs["aria-hidden"] === "true");
  botaoPorTexto(j.jogo, "Ver os prêmios").fire("click"); assert(/trinca|iguais/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Ler o saldo").fire("click"); assert(/Rodadas: 1/.test(j.an.textContent));
  for (let i = 0; i < 200 && !j.id("girar").disabled; i++) botaoPorTexto(j.jogo, "Girar").fire("click");
  botaoPorTexto(j.jogo, "Nova partida").fire("click"); assert(/Nova partida com 30/.test(j.an.textContent) && !j.id("girar").disabled);
});
t("campo minado: grade de botões com rótulo, comando e novo jogo", () => {
  const j = carregar("minas"), grade = j.id("grade"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  const bs = grade.all("button"); assert(bs.length > 20 && /linha 1, coluna 1, fechada/.test(bs[0].getAttribute("aria-label")));
  bs[0].fire("click"); assert(/aberta|vazia|Você|casas/i.test(j.an.textContent));
  campo.value = "resumo"; form.fire("submit"); assert(/mina/i.test(j.an.textContent));
  campo.value = "marcar 5 5"; form.fire("submit"); assert(/marc/i.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Modo da grade: abrir").fire("click"); assert(/marcar/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("gramado: comandos, botões de direção, consultas e novo jogo", () => {
  const j = carregar("gramado"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  assert(/Novo jogo, nível fácil/.test(j.an.textContent));
  campo.value = "onde"; form.fire("submit"); assert(/linha 1, coluna 1/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Norte").fire("click"); assert(/Fim do gramado/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Sensor").fire("click"); assert(/norte: borda/.test(j.an.textContent));
  campo.value = "leste"; form.fire("submit"); assert(/Cortou|sensor apitou/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Ler o mapa").fire("click"); assert(/Linha 1\./.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("escolhas: botões numerados, comando, dica e novo jogo", () => {
  const j = carregar("escolhas"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  assert(/Novo jogo, nível fácil/.test(j.an.textContent) && /Escolhas:/.test(j.an.textContent) && j.id("escolhas").all("button").length === 3);
  campo.value = "1"; form.fire("submit"); assert(/Primeira prova/.test(j.an.textContent) && j.id("escolhas").all("button").length === 4);
  campo.value = "dica"; form.fire("submit"); assert(/^Dica:/.test(j.an.textContent));
  j.id("escolhas").all("button")[1].fire("click"); assert(/Você atravessa|Melhor não/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("paciência: comandos, atalhos, dica, desfazer e novo jogo", () => {
  const j = carregar("paciencia"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  assert(/Novo jogo, nível fácil/.test(j.an.textContent) && /Coluna 7/.test(j.an.textContent));
  campo.value = "comprar"; form.fire("submit"); assert(/Você virou/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Ler o descarte").fire("click"); assert(/Descarte:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Dica").fire("click"); assert(/^Dica:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Desfazer").fire("click"); assert(/Desfeito/.test(j.an.textContent));
  campo.value = "coluna 3"; form.fire("submit"); assert(/Coluna 3: 2 cartas viradas/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("blackjack: aposta por botão e comando, jogada, leitura, dica e novo jogo", () => {
  const j = carregar("blackjack"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  assert(/Novo jogo, nível fácil, com 100 créditos/.test(j.an.textContent));
  j.id("aposta").value = "10"; botaoPorTexto(j.jogo, "Apostar").fire("click"); assert(/Aposta de 10/.test(j.an.textContent));
  campo.value = "mao"; form.fire("submit"); assert(/Sua mão|Saldo|Mão 1/.test(j.an.textContent));
  campo.value = "saldo"; form.fire("submit"); assert(/Saldo:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Dica").fire("click"); assert(/^Dica:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("roleta: aposta por seleção, por número, girar, leitura e novo jogo", () => {
  const j = carregar("roleta"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  assert(/Novo jogo, nível fácil, com 100 créditos/.test(j.an.textContent));
  j.id("valor").value = "5"; j.id("tipo").value = "vermelho"; botaoPorTexto(j.jogo, "Apostar").fire("click"); assert(/Aposta de 5 em vermelho/.test(j.an.textContent));
  j.id("numero").value = "17"; botaoPorTexto(j.jogo, "Apostar neste número").fire("click"); assert(/número 17/.test(j.an.textContent));
  campo.value = "apostas"; form.fire("submit"); assert(/Apostas na mesa/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Girar").fire("click"); assert(/A bola parou no/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Histórico").fire("click"); assert(/Últimos números/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("bacará: aposta por botão e comando, leitura, dica e novo jogo", () => {
  const j = carregar("bacara"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  assert(/Novo jogo, nível fácil, com 100 créditos/.test(j.an.textContent));
  j.id("valor").value = "10"; botaoPorTexto(j.jogo, "Apostar na banca").fire("click"); assert(/Aposta de 10 na banca/.test(j.an.textContent) && /Jogador:/.test(j.an.textContent));
  campo.value = "historico"; form.fire("submit"); assert(/Últimas 1 rodadas/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Dica").fire("click"); assert(/^Dica:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Repetir a aposta").fire("click"); assert(/Aposta de 10/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("poker caribenho: ante, leitura, decisão, dica e novo jogo", () => {
  const j = carregar("caribenho"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  assert(/Novo jogo, nível fácil, com 100 créditos/.test(j.an.textContent));
  j.id("ante").value = "5"; botaoPorTexto(j.jogo, "Apostar o ante").fire("click"); assert(/Ante de 5/.test(j.an.textContent) && /Suas cartas:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Ler a banca").fire("click"); assert(/A banca mostra/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Dica").fire("click"); assert(/^Dica: (aumentar|desistir)/.test(j.an.textContent));
  campo.value = "desistir"; form.fire("submit"); assert(/desistiu/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("poker: continuar, leitura, decisão, dica, fichas e novo jogo", () => {
  const j = carregar("poker"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  assert(/Novo jogo, nível fácil: cada um começa com 300 fichas/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Continuar").fire("click"); assert(/Mão 1\./.test(j.an.textContent) && /Suas cartas:/.test(j.an.textContent) && /Sua vez/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Ler a mão e a mesa").fire("click"); assert(/Suas cartas:/.test(j.an.textContent) && /Pote:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Dica").fire("click"); assert(/^Dica:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Ler as fichas").fire("click"); assert(/Suas fichas:/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Desistir").fire("click"); assert(/desiste/.test(j.an.textContent) && /ganhou o pote/.test(j.an.textContent));
  campo.value = "tabela"; form.fire("submit"); assert(/royal flush/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível/.test(j.an.textContent));
});
t("arqueiro: teste de som, iniciar, controles em texto (sem áudio no navegador), parar", () => {
  const j = carregar("arqueiro");
  assert(/Arqueiro de áudio/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Testar o som").fire("click"); assert(/não oferece áudio estéreo/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Iniciar").fire("click"); assert(/Partida iniciada, nível fácil, 10 alvos/.test(j.an.textContent) && /vou dizer onde o alvo está/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Esquerda").fire("click"); assert(/Mira à esquerda/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Onde estou").fire("click"); assert(/Sua mira está 1 passo à esquerda do centro/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Atirar").fire("click"); assert(/Não há alvo/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Pontos").fire("click"); assert(/Pontos: 0/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Parar").fire("click"); assert(/Partida pausada/.test(j.an.textContent));
});
function audioFalso(log) {
  global.AudioContext = function () {
    this.currentTime = 0; this.state = "running"; this.destination = {}; this.sampleRate = 8000;
    this.createOscillator = () => ({ type: "", frequency: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, start() { log.push("tom"); }, stop() {} });
    this.createGain = () => ({ gain: { value: 0, setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} });
    this.createBuffer = (c, n) => ({ getChannelData: () => new Float32Array(n) });
    this.createBufferSource = () => ({ connect() {}, start() { log.push("ruido"); } });
    this.createBiquadFilter = () => ({ frequency: {}, connect() {} });
  };
}
t("sons de apoio: roleta tem o botão Sons, gira com som e fala só depois, e o botão desliga", () => {
  const log = [], esperas = []; audioFalso(log);
  const st = global.setTimeout; global.setTimeout = (f, ms) => { esperas.push(ms); f(); };
  const j = carregar("roleta"), campo = j.id("comando"), form = j.jogo.all("form")[0];
  const sons = botaoPorTexto(j.jogo, "Sons: ligados. Aperte para desligar"); assert(sons, "botão Sons");
  campo.value = "apostar 5 vermelho"; form.fire("submit"); assert(log.includes("tom"), "ficha ao apostar");
  log.length = 0; esperas.length = 0; campo.value = "girar"; form.fire("submit");
  assert(log.includes("tom"), "bola e resultado tocam"); assert(esperas.some(ms => ms >= 2000), "a fala espera os sons terminarem");
  assert(/A bola parou/.test(j.an.textContent));
  sons.fire("click"); assert(/desligados/.test(sons.textContent) && /Sons desligados/.test(j.an.textContent));
  log.length = 0; campo.value = "apostar 1 preto"; form.fire("submit"); assert.equal(log.length, 0, "desligado: sem som");
  sons.fire("click");  // religa, deixa o estado limpo
  delete global.AudioContext; global.setTimeout = st;
});
t("sons de apoio: o classificador escolhe sons só para jogadas, e nunca para consulta ou fala de erro", () => {
  const j = carregar("blackjack"), cue = global.Heimdall.som.cue;
  assert.deepEqual(cue("Aposta de 4. Suas cartas: 10 de espadas, Dama de ouros: 20.", "apostar 4"), ["ficha", "cartas"]);
  assert.deepEqual(cue("Você recebeu Valete de copas. Passou de 21 e estourou.", "pedir"), ["carta", "estourou"]);
  assert.equal(cue("Saldo: 96 créditos. Você ganhou muito.", "saldo"), null, "consulta não toca som");
  assert.equal(cue("Não há rodada em andamento.", "pedir"), "erro");
  assert.equal(cue("A bola parou no 17. Você lucrou 5.", "girar").pop(), "ganhou");
  assert.equal(cue("Empate. Aposta devolvida.", "parar").pop(), "empate");
});
t("sons de apoio: regras por jogo (acerto, erro, tiro, fusão, vitória) e botão Sons em todos", () => {
  const nomes = ["forca", "senha", "numero", "velha", "cincoletras", "sudoku", "naval", "xadrez", "minas", "gramado", "sonar", "aventura", "escolhas", "g2048"];
  nomes.forEach(n => { const j = carregar(n); assert(botaoPorTexto(j.jogo, "Sons: ligados. Aperte para desligar"), "botão Sons em " + n); });
  const c = global.Heimdall.som.cueJogo;
  assert.equal(c("forca", "A letra A aparece 2 vezes."), "acerto");
  assert.equal(c("forca", "A letra X não existe. Restam 4 erros."), "erro");
  assert.equal(c("numero", "O número é maior que 50. Ele está entre 51 e 100."), "sobe");
  assert.equal(c("numero", "O número é menor que 50."), "desce");
  assert.equal(c("naval", "B7: acertou e afundou um submarino."), "afundou");
  assert.equal(c("naval", "B7: acertou. Águas dele: C3: água."), "tiro");
  assert.equal(c("naval", "B7: água."), "agua");
  assert.equal(c("g2048", "Moveu para esquerda, somando 8 pontos. Surgiu 2."), "fusao");
  assert.equal(c("g2048", "Nada se moveu para cima."), "erro");
  assert.deepEqual(c("g2048", "Moveu para cima. Você chegou ao 2048! Pontos: 1."), ["mover", "grande"]);
  assert.deepEqual(c("velha", "Você jogou em 5. Você ganhou!"), ["toque", "grande"]);
  assert.equal(c("gramado", "Crash! O cortador caiu num formigueiro."), "explosao");
  assert.equal(c("gramado", "Você está na linha 1, coluna 2 de um gramado."), null, "consulta sem som");
  assert.equal(c("minas", "A casa da linha 1, coluna 1 já está aberta: vazia."), "erro");
  assert.equal(c("sudoku", "Não dá: o 5 já está na linha."), "erro");
  assert.equal(c("sudoku", "Colocado 5 na linha 1, coluna 1."), "toque");
  assert.equal(c("historia", "Não entendi. Digite ajuda."), "erro");
});
t("sonar: botões, teclas, ping com eco falado depois do som e carga", () => {
  const log = [], esperas = []; audioFalso(log);
  const st = global.setTimeout; global.setTimeout = (f, ms) => { esperas.push(ms); f(); };
  const j = carregar("sonar"); assert(/Novo jogo, nível fácil: mar de 8 por 8/.test(j.an.textContent));
  const tecla = (key, tagName) => doc.listeners.keydown.forEach(f => f({ key, target: { tagName: tagName || "BODY" }, preventDefault() {}, metaKey: false }));
  tecla("ArrowRight"); assert(/Você foi 1 casa ao leste/.test(j.an.textContent), "seta move o navio");
  esperas.length = 0; log.length = 0; botaoPorTexto(j.jogo, "Ping do sonar").fire("click");
  assert(/Eco: o submarino mais próximo/.test(j.an.textContent)); assert(esperas.some(ms => ms >= 300), "o eco fala só depois do som"); assert(log.includes("tom"), "tocou o eco");
  tecla("P"); assert(/Pings restantes: 18/.test(j.an.textContent), "a tecla P pinga");
  tecla("p", "INPUT"); assert(/Pings restantes: 18/.test(j.an.textContent), "P digitado em outro campo não pinga");
  botaoPorTexto(j.jogo, "Lançar carga").fire("click"); assert(/carga explodiu|Boom/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Placar").fire("click"); assert(/Cargas restantes: 5/.test(j.an.textContent));
  const campo = j.id("comando"), form = j.jogo.all("form")[0]; campo.value = "oeste 2"; form.fire("submit"); assert(/2 casas ao oeste/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(/Novo jogo, nível fácil/.test(j.an.textContent));
  delete global.AudioContext; global.setTimeout = st;
});
t("sons de apoio: caça-níqueis toca os rolos e o resultado", () => {
  const log = []; audioFalso(log);
  const j = carregar("cacaniqueis"); j.id("aposta").value = "1"; botaoPorTexto(j.jogo, "Girar").fire("click");
  assert(log.length > 3, "rolos e resultado"); assert(/Saiu:/.test(j.an.textContent));
  delete global.AudioContext;
});
t("arqueiro: teste de som toca os três sons em ordem e só depois fala a explicação", () => {
  const sons = []; let ultimaPan = null;
  global.AudioContext = function () {
    this.currentTime = 0; this.destination = {};
    this.createOscillator = () => ({ type: "", frequency: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, start() { sons.push({ pan: ultimaPan, falou: /ouviu três sons/.test(j.an.textContent) }); }, stop() {} });
    this.createGain = () => ({ gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} });
    this.createStereoPanner = () => { const o = { pan: { set value(v) { ultimaPan = v; } }, connect() {} }; return o; };
  };
  global.clearTimeout = () => {};
  const j = carregar("arqueiro");
  botaoPorTexto(j.jogo, "Testar o som").fire("click");
  delete global.AudioContext;
  assert.deepEqual(sons.map(x => x.pan), [-1, 0, 1], "esquerda, meio, direita, nessa ordem");
  assert(sons.every(x => !x.falou), "nenhuma explicação falada enquanto os sons tocam");
  assert(/Você ouviu três sons: o primeiro só no fone esquerdo/.test(j.an.textContent), "explicação falada depois do último som");
});
t("arqueiro: narração completa, curta ou nenhuma, com padrão por nível", () => {
  global.AudioContext = function () {
    this.currentTime = 0; this.state = "running"; this.destination = {};
    this.createOscillator = () => ({ type: "", frequency: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, start() {}, stop() {} });
    this.createGain = () => ({ gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} });
    this.createStereoPanner = () => ({ pan: { value: 0 }, connect() {} });
  };
  const j = carregar("arqueiro"), fala = j.id("fala"), nivel = j.id("nivel");
  assert.equal(fala.value, "completa", "fácil começa com narração completa");
  nivel.value = "normal"; (nivel.listeners.change || []).forEach(f => f()); assert.equal(fala.value, "curta");
  nivel.value = "dificil"; (nivel.listeners.change || []).forEach(f => f()); assert.equal(fala.value, "minima");
  const rodar = (modo) => { fala.value = modo; botaoPorTexto(j.jogo, "Iniciar").fire("click"); const ini = j.an.textContent; botaoPorTexto(j.jogo, "Atirar").fire("click"); const tiro = j.an.textContent; botaoPorTexto(j.jogo, "Parar").fire("click"); return { ini, tiro }; };
  const c = rodar("completa"); assert(/Partida iniciada/.test(c.ini) && /Não há alvo no céu agora/.test(c.tiro));
  const k = rodar("curta"); assert.equal(k.tiro, "Sem alvo."); assert(/alvos\.$/.test(k.ini) && k.ini.length < 40, "início curto");
  const n = rodar("minima"); assert.equal(n.ini, "Começou."); assert.equal(n.tiro, "Sem alvo.", "mínima: só o essencial");
  const campo = j.id("teclas"), rot = () => campo.attrs["aria-label"];
  fala.value = "minima"; (fala.listeners.change || []).forEach(f => f()); assert.equal(rot(), "Área de jogo.");
  fala.value = "curta"; (fala.listeners.change || []).forEach(f => f()); assert(/^Área de jogo\. Setas movem a mira, espaço atira\.$/.test(rot()));
  fala.value = "completa"; (fala.listeners.change || []).forEach(f => f()); assert(/Também dá para digitar comandos e apertar Enter/.test(rot()));
  delete global.AudioContext;
});
t("arqueiro: setas e espaço valem em qualquer lugar da página durante a partida, mas não em seletor, botão nem outro campo", () => {
  const j = carregar("arqueiro"), campo = j.id("teclas"), erro = () => { throw new Error("não deveria agir aqui"); };
  const tecla = (key, tagName, alvo) => doc.listeners.keydown.forEach(f => f({ key, target: alvo || { tagName }, preventDefault: tagName === "OK" ? () => {} : erro }));
  const ok = (key, tagName, alvo) => doc.listeners.keydown.forEach(f => f({ key, target: alvo || { tagName }, preventDefault() {} }));
  tecla("ArrowLeft", "BODY");  // partida parada e foco fora do campo: não age
  assert(!/Mira à esquerda/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Iniciar").fire("click");
  ok("ArrowLeft", "BODY"); assert(/Mira à esquerda/.test(j.an.textContent), "seta com a partida rodando, foco no corpo da página");
  ok("ArrowRight", "BUTTON"); ok("ArrowRight", "DIV");
  ok(" ", "BODY");
  tecla("ArrowLeft", "SELECT"); tecla("ArrowLeft", "INPUT"); tecla(" ", "BUTTON");  // seletor, outro campo e espaço em botão: ignorados
  ok("ArrowLeft", "INPUT", campo);  // no campo do jogo vale sempre
  botaoPorTexto(j.jogo, "Parar").fire("click");
  const antes = j.an.textContent; tecla("ArrowLeft", "BODY"); assert.equal(j.an.textContent, antes, "parada, fora do campo, não age");
});
t("xadrez: lance, resposta do computador, consulta, erro e nova partida", () => {
  const j = carregar("xadrez"), campo = j.id("lance"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/Nova partida, nível médio/.test(j.an.textContent));
  campo.value = "e4"; form.fire("submit"); assert(/Você jogou/.test(j.an.textContent) && /O computador jogou/.test(j.an.textContent));
  campo.value = "linha 1"; form.fire("submit"); assert(/Linha 1:/.test(j.an.textContent));
  campo.value = "e9"; form.fire("submit"); assert(/Não entendi|não é permitido/.test(j.an.textContent));
  campo.value = "desfazer"; form.fire("submit"); assert(/Desfeito/.test(j.an.textContent));
  assert(/pre/.test(j.id("visual").tag) && j.id("visual").attrs["aria-hidden"] === "true" && /a b c d e f g h/.test(j.id("visual").textContent));
  campo.value = "desistir"; form.fire("submit"); assert(campo.disabled);
  botaoPorTexto(j.jogo, "Nova partida").fire("click"); assert(!campo.disabled && hist.children.length === 1);
});
const store = {}; global.localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
["relogios", "templo", "orion", "caverna"].forEach(id => t(`aventura ${id}: níveis, comando, dica, salvar e carregar`, () => {
  const j = carregar("hist_" + id, id), campo = j.id("comando"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/Objetivo:/.test(hist.textContent) && /Nível normal/.test(hist.textContent));
  j.id("nivel").value = "dificil"; botaoPorTexto(j.jogo, "Recomeçar").fire("click"); assert(/Nível difícil: sem dicas/.test(hist.children[0].textContent));
  campo.value = "dica"; form.fire("submit"); assert(/não há dicas/.test(j.an.textContent));
  j.id("nivel").value = "facil"; botaoPorTexto(j.jogo, "Recomeçar").fire("click"); assert(/dicas à vontade/.test(hist.children[0].textContent));
  campo.value = "dica"; form.fire("submit"); assert(/Dica:/.test(j.an.textContent));
  campo.value = "ir norte"; form.fire("submit"); campo.value = "salvar"; form.fire("submit"); assert(/salva/.test(j.an.textContent));
  botaoPorTexto(j.jogo, "Recomeçar").fire("click"); botaoPorTexto(j.jogo, "Carregar").fire("click"); assert(/Partida carregada/.test(j.an.textContent));
  campo.value = "dançar"; form.fire("submit"); assert(/Não entendi/.test(j.an.textContent));
}));
t("batalha naval: frota, tiro, resposta do computador, erro e nova partida", () => {
  const j = carregar("naval"), campo = j.id("tiro"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/Nova batalha, nível normal/.test(hist.textContent));
  campo.value = "frota"; form.fire("submit"); assert(/Sua frota: porta-aviões/.test(j.an.textContent));
  campo.value = "b7"; form.fire("submit"); assert(/Você atirou em B7/.test(j.an.textContent) && /O computador atirou/.test(j.an.textContent));
  campo.value = "b7"; form.fire("submit"); assert(/já atirou em B7/.test(j.an.textContent));
  campo.value = "zz"; form.fire("submit"); assert(/Não entendi/.test(j.an.textContent));
  assert(j.id("visual").attrs["aria-hidden"] === "true" && /Seus tiros/.test(j.id("visual").textContent) && /Sua frota/.test(j.id("visual").textContent));
  campo.value = "desistir"; form.fire("submit"); assert(campo.disabled);
  botaoPorTexto(j.jogo, "Nova partida").fire("click"); assert(!campo.disabled && hist.children.length === 1);
});
t("cinco letras: palpite, erro, comandos e nova palavra", () => {
  const j = carregar("cincoletras"), campo = j.id("palpite"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/Nova palavra de 5 letras, nível normal/.test(hist.textContent));
  campo.value = "festa"; form.fire("submit"); assert(/Tentativa 1 de 6, FESTA: F: /.test(j.an.textContent));
  campo.value = "casa"; form.fire("submit"); assert(/exatamente 5 letras/.test(j.an.textContent));
  campo.value = "pistas"; form.fire("submit"); assert(/Lugares conhecidos/.test(j.an.textContent));
  campo.value = "desistir"; form.fire("submit"); assert(/A palavra era/.test(j.an.textContent) && campo.disabled);
  botaoPorTexto(j.jogo, "Nova palavra").fire("click"); assert(!campo.disabled && hist.children.length === 1);
});
t("sudoku: leitura, jogada, recusa e novo jogo", () => {
  const j = carregar("sudoku"), campo = j.id("comando"), form = j.jogo.all("form")[0], hist = j.id("historico");
  assert(/Novo sudoku, nível normal, com 32 números dados/.test(hist.textContent));
  campo.value = "linha 1"; form.fire("submit"); assert(/Linha 1, da coluna 1 à 9/.test(j.an.textContent));
  campo.value = "colocar 5 em 10 1"; form.fire("submit"); assert(/Use números de 1 a 9/.test(j.an.textContent));
  campo.value = "quadrante 5"; form.fire("submit"); assert(/Quadrante 5/.test(j.an.textContent));
  campo.value = "dica"; form.fire("submit"); assert(/Dica: na linha/.test(j.an.textContent));
  assert(j.id("visual").attrs["aria-hidden"] === "true" && /------\+-------\+------/.test(j.id("visual").textContent));
  campo.value = "desistir"; form.fire("submit"); assert(campo.disabled);
  botaoPorTexto(j.jogo, "Novo jogo").fire("click"); assert(!campo.disabled && hist.children.length === 1);
});
console.log(`${ok} testes de interface passaram`); process.exit(falhas ? 1 : 0);
