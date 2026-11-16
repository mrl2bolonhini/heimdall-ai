// Motor das aventuras de texto do Heimdall. Uma história é só dados (salas, itens, regras); o motor cuida dos comandos em português,
// dos três graus de dificuldade (fácil, normal, difícil), das dicas, do limite de passos, de salvar e carregar e da leitura para leitor de tela.
// As histórias ficam em jogos/hist_*.js e se registram em Heimdall.historias. Também roda no Node (testes).
(function (raiz) {
  "use strict";
  var NIVEIS = { facil: "fácil", normal: "normal", dificil: "difícil" };
  var DICAS_NORMAL = 3;
  var FATOR_LIMITE = { normal: 3, dificil: 1.8 };   // vezes os passos da solução
  var DIRS = { n: "norte", s: "sul", l: "leste", o: "oeste", norte: "norte", sul: "sul", leste: "leste", oeste: "oeste", subir: "subir", sobe: "subir", descer: "descer", desce: "descer", cima: "subir", baixo: "descer", entrar: "entrar", sair: "sair", ne: "nordeste", no: "noroeste", se: "sudeste", so: "sudoeste" };
  var ACOES = { empurrar: 1, puxar: 1, girar: 1, ligar: 1, acender: 1, apertar: 1, abrir: 1, tocar: 1, escalar: 1, quebrar: 1, mexer: 1, beber: 1, comer: 1, cavar: 1, ler: 1, destrancar: 1, desligar: 1, apagar: 1, fechar: 1 };
  var JUNTAS = ["em", "com", "no", "na", "sobre", "contra", "nos", "nas"];
  var DARES = ["a", "para", "pra", "ao", "aos"];
  var ARTIGOS = /^(o|a|os|as|um|uma|do|da|dos|das|de|ao|para|pra|com|em|no|na) /;

  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim(); }
  function semArt(t) { t = norm(t); var antes; do { antes = t; t = t.replace(ARTIGOS, ""); } while (t !== antes); return t; }
  function lista(arr) { return arr.length <= 1 ? arr.join("") : arr.slice(0, -1).join(", ") + " e " + arr[arr.length - 1]; }
  function ativo(x, e) { return !(x && x.so && x.so.indexOf(e.nivel) < 0) && !(x && x.nao && x.nao.indexOf(e.nivel) >= 0); }

  // Condição: { flags:[...], semFlags:[...], tem:[...], semItem:[...], sala:"id", nivel:["dificil"] }
  function cond(e, c) {
    if (!c) return true;
    var i;
    for (i = 0; c.flags && i < c.flags.length; i++) if (!e.flags[c.flags[i]]) return false;
    for (i = 0; c.semFlags && i < c.semFlags.length; i++) if (e.flags[c.semFlags[i]]) return false;
    for (i = 0; c.tem && i < c.tem.length; i++) if (e.inv.indexOf(c.tem[i]) < 0) return false;
    for (i = 0; c.semItem && i < c.semItem.length; i++) if (e.inv.indexOf(c.semItem[i]) >= 0) return false;
    if (c.sala && e.sala !== c.sala) return false;
    if (c.nivel && c.nivel.indexOf(e.nivel) < 0) return false;
    return true;
  }

  function criar(h, nivel) {
    nivel = NIVEIS[nivel] ? nivel : "normal";
    var e = { historia: h.id, nivel: nivel, sala: h.inicio, inv: [], itensSala: {}, flags: {}, fim: null, passos: 0, dicas: 0, visitadas: {} };
    Object.keys(h.salas).forEach(function (k) { e.itensSala[k] = (h.salas[k].itens || []).filter(function (i) { return h.itens[i] && ativo(h.itens[i], e); }); });
    (h.inventario || []).forEach(function (i) { e.inv.push(i); });
    e.visitadas[h.inicio] = true;
    return e;
  }
  function limiteDe(h, nivel) {
    if (h.semLimite || !FATOR_LIMITE[nivel]) return 0;
    var base = h._passosSolucao && h._passosSolucao[nivel];
    if (!base) base = (h.solucao && (h.solucao[nivel] || h.solucao.normal) || []).length;
    return Math.ceil(base * FATOR_LIMITE[nivel]) + 4;
  }

  // ---------- efeitos ----------
  function aplicar(h, e, ef, msg) {
    var out = [msg], i;
    if (ef.poe) ef.poe.forEach(function (f) { e.flags[f] = true; });
    if (ef.tira) ef.tira.forEach(function (f) { delete e.flags[f]; });
    if (ef.consome) ef.consome.forEach(function (it) { var k = e.inv.indexOf(it); if (k >= 0) e.inv.splice(k, 1); });
    if (ef.ganha) ef.ganha.forEach(function (it) { if (e.inv.indexOf(it) < 0) { e.inv.push(it); out.push("Você pegou: " + h.itens[it].nome + "."); } });
    if (ef.solta) ef.solta.forEach(function (it) { if (e.itensSala[e.sala].indexOf(it) < 0) e.itensSala[e.sala].push(it); });
    if (ef.mover) { e.sala = ef.mover; e.visitadas[e.sala] = true; out.push(descrever(h, e)); out.push.apply(out, entrar(h, e)); }
    if (ef.fim && !e.fim) e.fim = ef.fim;
    return out.filter(Boolean).join(" ");
  }
  function entrar(h, e) {
    var s = h.salas[e.sala], out = [];
    (s.aoEntrar || []).some(function (r) {
      if (!ativo(r, e) || !cond(e, r.se)) return false;
      out.push(aplicar(h, e, r, r.msg || "")); return true;
    });
    return out;
  }

  // ---------- leitura da sala ----------
  function escuro(h, e) { var s = h.salas[e.sala]; return !!(s.escuro && !cond(e, s.escuro)); }
  function saidasVisiveis(h, e) {
    var s = h.salas[e.sala], out = [];
    Object.keys(s.saidas || {}).forEach(function (d) {
      var x = s.saidas[d]; if (typeof x === "string") { out.push(d); return; }
      if (!ativo(x, e)) return;
      if (x.oculta && !cond(e, x.requer)) return;
      out.push(d);
    });
    return out;
  }
  function descrever(h, e) {
    var s = h.salas[e.sala];
    if (escuro(h, e)) return s.nome + ". " + (s.textoEscuro || "Está escuro demais para ver qualquer coisa.") + " Saídas: " + saidasVisiveis(h, e).join(", ") + ".";
    var t = s.nome + ". " + s.desc;
    (s.extras || []).forEach(function (x) { if (ativo(x, e) && cond(e, x.se)) t += " " + x.msg; });
    var its = e.itensSala[e.sala].filter(function (i) { return !h.itens[i].escondido; });
    if (its.length) t += " Aqui há: " + lista(its.map(function (i) { return h.itens[i].nome; })) + ".";
    var np = (s.npcs || []).filter(function (n) { return ativo(n, e) && cond(e, n.se); });
    if (np.length) t += " Aqui está: " + lista(np.map(function (n) { return n.nome; })) + ".";
    return t + " Saídas: " + saidasVisiveis(h, e).join(", ") + ".";
  }

  // ---------- nomes ----------
  function escopo(h, e) {
    var s = h.salas[e.sala], l = [];
    e.inv.forEach(function (i) { l.push({ tipo: "item", id: i, nomes: [h.itens[i].nome].concat(h.itens[i].apelidos || []), mochila: true }); });
    if (!escuro(h, e)) {
      e.itensSala[e.sala].forEach(function (i) { l.push({ tipo: "item", id: i, nomes: [h.itens[i].nome].concat(h.itens[i].apelidos || []), mochila: false }); });
      Object.keys(s.cenario || {}).forEach(function (k) { var c = s.cenario[k]; if (ativo(c, e) && cond(e, c.se)) l.push({ tipo: "cenario", id: k, nomes: [c.nome].concat(c.apelidos || []) }); });
      (s.npcs || []).forEach(function (n) { if (ativo(n, e) && cond(e, n.se)) l.push({ tipo: "npc", id: n.id, nomes: [n.nome].concat(n.apelidos || []) }); });
    }
    return l;
  }
  function resolver(h, e, q) {
    q = semArt(q); if (!q) return null;
    var l = escopo(h, e), i, j, n;
    for (i = 0; i < l.length; i++) for (j = 0; j < l[i].nomes.length; j++) if (norm(l[i].nomes[j]) === q) return l[i];
    for (i = 0; i < l.length; i++) for (j = 0; j < l[i].nomes.length; j++) {
      n = norm(l[i].nomes[j]);
      if ((" " + q + " ").indexOf(" " + n + " ") >= 0 || (q.length >= 3 && (" " + n + " ").indexOf(" " + q + " ") >= 0)) return l[i];
    }
    return null;
  }
  function itemGlobal(h, q) {
    q = semArt(q); if (!q) return null;
    return Object.keys(h.itens).filter(function (k) { return [h.itens[k].nome].concat(h.itens[k].apelidos || []).some(function (n) { n = norm(n); return n === q || (" " + q + " ").indexOf(" " + n + " ") >= 0; }); })[0] || null;
  }
  function partir(t, seps) {
    var p = t.split(" "), i;
    for (i = 1; i < p.length - 0; i++) if (seps.indexOf(p[i]) >= 0 && i < p.length - 1) return [p.slice(0, i).join(" "), p.slice(i + 1).join(" ")];
    return [t, ""];
  }

  // ---------- regras de uso ----------
  function falhaPadrao(r) { return r.falha || "Isso não funciona agora."; }
  function tentar(h, e, filtro) {
    var falha = null, achou = false, i, r;
    for (i = 0; i < (h.usos || []).length; i++) {
      r = h.usos[i]; if (!ativo(r, e) || !filtro(r)) continue;
      if (r.sala && r.sala !== e.sala) continue;
      achou = true;
      if (cond(e, r.se)) return { msg: aplicar(h, e, r, r.msg || "Feito.") };
      if (falha === null) falha = falhaPadrao(r);
    }
    return achou ? { msg: falha } : null;
  }

  var CONSULTAS = { escutar: 1, ouvir: 1, onde: 1, olhar: 1, ver: 1, inventario: 1, i: 1, inv: 1, ajuda: 1, h: 1, dica: 1, pista: 1, mapa: 1, objetivo: 1, tempo: 1, examinar: 1, exame: 1, x: 1 };

  function ajuda(e) {
    return "Comandos: olhar; ir norte, sul, leste, oeste, subir, descer (ou n, s, l, o); pegar ITEM; largar ITEM; examinar ALGO; usar ITEM; usar ITEM em ALGO; dar ITEM a ALGUÉM; falar com ALGUÉM; digitar CÓDIGO em ALGO; " +
      "empurrar, puxar, girar, abrir, acender ALGO; escutar; onde; inventário; objetivo; mapa; dica; tempo; salvar; carregar; recomeçar.";
  }
  function dica(h, e) {
    if (e.nivel === "dificil") return "No nível difícil não há dicas.";
    if (e.nivel === "normal" && e.dicas >= DICAS_NORMAL) return "Suas " + DICAS_NORMAL + " dicas do nível normal acabaram.";
    var d = (h.dicas || []).filter(function (x) { return ativo(x, e) && cond(e, x.se); })[0];
    if (!d) return "Não tenho uma dica para este momento. Releia o objetivo e examine com calma o que há ao redor.";
    e.dicas++;
    return "Dica: " + d.msg + (e.nivel === "normal" ? " Restam " + (DICAS_NORMAL - e.dicas) + (DICAS_NORMAL - e.dicas === 1 ? " dica." : " dicas.") : "");
  }
  function tempo(h, e) {
    var l = limiteDe(h, e.nivel);
    return l ? "Você usou " + e.passos + " de " + l + " passos." : "Neste nível não há limite de passos. Você usou " + e.passos + ".";
  }

  function comando(h, e, texto) {
    var t = norm(texto), p = t.split(" "), v = p[0], resto = p.slice(1).join(" "), r, k, alvo, s = h.salas[e.sala];
    if (e.fim) return "A aventura terminou. Use Recomeçar para jogar de novo.";
    if (!t) return "Digite um comando. Experimente: olhar, ir norte, pegar ITEM, ajuda.";
    var conta = !CONSULTAS[v];
    var msg = interpretar(h, e, t, p, v, resto, s);
    if (conta && !e.fim && !msg.erro) {
      e.passos++;
      var l = limiteDe(h, e.nivel);
      if (l) {
        if (e.passos > l) { e.fim = "derrota"; return msg.texto + " " + (h.msgLimite || "O tempo acabou e você não conseguiu terminar a aventura.") + " Use Recomeçar para tentar de novo."; }
        var resta = l - e.passos;
        if (resta === 10 || resta === 3) return msg.texto + " Atenção: restam " + resta + " passos.";
      }
    }
    if (e.fim === "vitoria") return msg.texto + " Você terminou \"" + h.titulo + "\" no nível " + NIVEIS[e.nivel] + ", em " + e.passos + " passos.";
    if (e.fim === "derrota") return msg.texto + " Fim da aventura. Use Recomeçar para tentar de novo.";
    return msg.texto;
  }
  function ok(texto) { return { texto: texto }; }
  function erro(texto) { return { texto: texto, erro: true }; }

  function interpretar(h, e, t, p, v, resto, s) {
    var r, k, alvo, a, par;
    if (v === "ajuda" || v === "h" || v === "?") return ok(ajuda(e));
    if ((v === "olhar" || v === "ver") && !resto) return ok(descrever(h, e));
    if (v === "objetivo") return ok("Objetivo: " + h.objetivo);
    if (v === "onde") return ok("Você está em " + s.nome + ". Saídas: " + saidasVisiveis(h, e).join(", ") + ".");
    if (v === "escutar" || v === "ouvir") {
      var som = (s.escuta || []).filter(function (x) { return ativo(x, e) && cond(e, x.se); }).map(function (x) { return x.msg; });
      return ok(som.length ? "Você escuta: " + som.join(" ") : "Você só ouve o seu próprio silêncio e a sua respiração.");
    }
    if (v === "dica" || v === "pista") return ok(dica(h, e));
    if (v === "tempo") return ok(tempo(h, e));
    if (v === "mapa") {
      var vis = Object.keys(e.visitadas).map(function (k) { return h.salas[k].nome; });
      return ok("Você está em " + s.nome + ". Lugares visitados: " + lista(vis) + ". Saídas daqui: " + saidasVisiveis(h, e).join(", ") + ".");
    }
    if (v === "inventario" || v === "i" || v === "inv") return ok(e.inv.length ? "Você carrega: " + lista(e.inv.map(function (i) { return h.itens[i].nome; })) + "." : "Você não carrega nada.");

    // movimento
    var dir = null;
    if (v === "ir" || v === "va" || v === "andar" || v === "caminhar" || v === "seguir") dir = DIRS[resto.split(" ")[0]] || "";
    else if (DIRS[v] && p.length === 1) dir = DIRS[v];
    else if ((v === "subir" || v === "descer" || v === "entrar" || v === "sair") && p.length > 1) dir = DIRS[v];
    if (dir !== null) {
      if (!dir) return erro("Para onde? Use norte, sul, leste, oeste, subir ou descer.");
      var x = s.saidas && s.saidas[dir];
      if (x && typeof x !== "string" && !ativo(x, e)) x = null;
      if (!x) return erro("Não dá para ir para " + dir + " daqui.");
      if (typeof x !== "string") {
        if (x.oculta && !cond(e, x.requer)) return erro("Não dá para ir para " + dir + " daqui.");
        if (!cond(e, x.requer)) return erro(x.msg || "O caminho está bloqueado.");
        x = x.para;
      }
      e.sala = x; e.visitadas[x] = true;
      var partes = [descrever(h, e)].concat(entrar(h, e));
      return ok(partes.filter(Boolean).join(" "));
    }

    if (v === "pegar" || v === "pega" || v === "apanhar" || v === "levar") {
      if (!resto) return erro("Pegar o quê?");
      if (escuro(h, e)) return erro("Está escuro demais para achar qualquer coisa.");
      a = resolver(h, e, resto);
      if (!a) return erro(itemGlobal(h, resto) && e.inv.indexOf(itemGlobal(h, resto)) >= 0 ? "Você já está com isso." : "Não vejo isso aqui.");
      if (a.tipo !== "item") return erro("Isso não dá para carregar.");
      if (a.mochila) return erro("Você já está com isso.");
      var it = h.itens[a.id];
      if (it.fixo) return erro(it.msgFixo || "Isso está preso e não dá para levar.");
      e.itensSala[e.sala].splice(e.itensSala[e.sala].indexOf(a.id), 1); e.inv.push(a.id);
      return ok("Você pegou: " + it.nome + ".");
    }
    if (v === "largar" || v === "soltar") {
      a = resolver(h, e, resto);
      if (!a || !a.mochila) return erro("Você não tem isso.");
      e.inv.splice(e.inv.indexOf(a.id), 1); e.itensSala[e.sala].push(a.id);
      return ok("Você largou: " + h.itens[a.id].nome + ".");
    }
    if (v === "examinar" || v === "exame" || v === "x" || v === "olhar" || v === "ver") {
      if (!resto) return ok(descrever(h, e));
      a = resolver(h, e, resto);
      if (!a) return erro(escuro(h, e) ? "Está escuro demais para ver." : "Não vejo isso aqui.");
      var obj = a.tipo === "item" ? h.itens[a.id] : a.tipo === "cenario" ? s.cenario[a.id] : (s.npcs || []).filter(function (n) { return n.id === a.id; })[0];
      var ex = (obj.exame || []).filter(function (y) { return ativo(y, e) && cond(e, y.se); })[0];
      if (ex) return ok(aplicar(h, e, ex, ex.msg));
      return ok(obj.desc || "Nada de especial.");
    }
    if (v === "ler" && resto) {
      a = resolver(h, e, resto);
      if (a) { r = tentar(h, e, function (u) { return u.verbo === "ler" && u.alvo === a.id; }); if (r) return ok(r.msg); return comando_exame(h, e, s, a); }
    }
    if (v === "falar" || v === "conversar" || v === "perguntar") {
      a = resolver(h, e, resto.replace(/^(com|a|ao|para) /, ""));
      if (!a || a.tipo !== "npc") return erro("Não há ninguém com esse nome aqui.");
      var n = (s.npcs || []).filter(function (y) { return y.id === a.id; })[0];
      var fala = (n.falas || []).filter(function (y) { return ativo(y, e) && cond(e, y.se); })[0];
      return ok(fala ? aplicar(h, e, fala, n.nome + ": " + fala.msg) : n.nome + " não tem nada a dizer.");
    }
    if (v === "dar" || v === "entregar" || v === "mostrar") {
      par = partir(resto, DARES); a = resolver(h, e, par[0]); alvo = resolver(h, e, par[1]);
      if (!a || !a.mochila) return erro("Você não tem isso.");
      if (!alvo) return erro(par[1] ? "Não vejo essa pessoa aqui." : "Dar a quem? Escreva, por exemplo: dar chave ao guarda.");
      r = tentar(h, e, function (u) { return u.item === a.id && u.alvo === alvo.id; });
      return r ? ok(r.msg) : ok("Não parece adiantar.");
    }
    if (v === "usar" || v === "use" || v === "colocar" || v === "pôr" || v === "por") {
      if (!resto) return erro("Usar o quê?");
      par = partir(resto, JUNTAS); a = resolver(h, e, par[0]);
      if (!a) return erro(itemGlobal(h, par[0]) ? "Você não tem isso." : "Não vejo isso aqui.");
      if (a.tipo !== "item") {
        r = tentar(h, e, function (u) { return u.verbo === "usar" && u.alvo === a.id; });
        return r ? ok(r.msg) : erro("Não sei como usar isso. Tente um verbo como abrir, puxar ou empurrar.");
      }
      if (!a.mochila) return erro("Pegue isso primeiro.");
      alvo = par[1] ? resolver(h, e, par[1]) : null;
      if (par[1] && !alvo) return erro("Não vejo " + par[1] + " aqui.");
      if (alvo) r = tentar(h, e, function (u) { return u.item === a.id && u.alvo === alvo.id && !u.codigo && !u.verbo; });
      else {
        r = tentar(h, e, function (u) { return u.item === a.id && !u.alvo && !u.codigo && !u.verbo; });
        if (!r) {   // sem alvo dito: tenta o único alvo da sala que aceita esse item
          var aceitam = (h.usos || []).filter(function (u) { return ativo(u, e) && u.item === a.id && u.alvo && !u.codigo && !u.verbo && (!u.sala || u.sala === e.sala) && escopo(h, e).some(function (z) { return z.id === u.alvo; }); });
          var ids = {}; aceitam.forEach(function (u) { ids[u.alvo] = 1; });
          if (Object.keys(ids).length === 1) r = tentar(h, e, function (u) { return u.item === a.id && u.alvo === aceitam[0].alvo && !u.codigo && !u.verbo; });
          else if (Object.keys(ids).length > 1) return erro("Usar " + h.itens[a.id].nome + " em quê? Escreva: usar " + h.itens[a.id].nome + " em ALGO.");
        }
      }
      return r ? ok(r.msg) : erro("Você não vê como usar " + h.itens[a.id].nome + " assim.");
    }
    if (v === "digitar" || v === "escrever" || v === "dizer" || v === "discar") {
      par = partir(resto, JUNTAS); var cod = norm(par[0]).replace(/ /g, "");
      if (!cod) return erro("Digitar o quê? Exemplo: digitar 1234 no cofre.");
      alvo = par[1] ? resolver(h, e, par[1]) : null;
      var rs = (h.usos || []).filter(function (u) { return ativo(u, e) && u.codigo && (!u.sala || u.sala === e.sala) && (!alvo || u.alvo === alvo.id) && escopo(h, e).some(function (z) { return z.id === u.alvo; }); });
      if (!rs.length) return erro("Não há onde digitar isso aqui.");
      r = tentar(h, e, function (u) { return u.codigo && norm(u.codigo).replace(/ /g, "") === cod && rs.indexOf(u) >= 0; });
      return r ? ok(r.msg) : ok(rs[0].errado || "O código está errado.");
    }
    if (ACOES[v]) {
      if (!resto) return erro(v.charAt(0).toUpperCase() + v.slice(1) + " o quê?");
      a = resolver(h, e, resto);
      if (!a) return erro("Não vejo isso aqui.");
      r = tentar(h, e, function (u) { return u.verbo === v && u.alvo === a.id; });
      if (r) return ok(r.msg);
      if (v === "abrir" || v === "destrancar") {   // tenta com o que você carrega
        r = tentar(h, e, function (u) { return u.alvo === a.id && u.item && e.inv.indexOf(u.item) >= 0 && !u.codigo && !u.verbo; });
        if (r) return ok(r.msg);
      }
      return ok(v === "abrir" ? "Não abre assim. Talvez precise de uma chave ou de outro objeto." : "Não acontece nada.");
    }
    return erro("Não entendi. Digite ajuda para ver os comandos.");
  }
  function comando_exame(h, e, s, a) {
    var obj = a.tipo === "item" ? h.itens[a.id] : a.tipo === "cenario" ? s.cenario[a.id] : null;
    return ok(obj ? obj.desc || "Nada de especial." : "Nada para ler.");
  }

  // ---------- salvar / carregar ----------
  function exportar(e) { return JSON.stringify(e); }
  function importar(h, json) {
    try {
      var o = JSON.parse(json);
      if (!o || o.historia !== h.id || !h.salas[o.sala] || !Array.isArray(o.inv) || !NIVEIS[o.nivel]) return null;
      if (o.inv.some(function (i) { return !h.itens[i]; })) return null;
      return o;
    } catch (x) { return null; }
  }

  // ---------- validação dos dados de uma história ----------
  function validar(h) {
    var p = [], salas = h.salas || {}, itens = h.itens || {}, flags = {}, usados = {};
    function itemOk(i, onde) { if (!itens[i]) p.push(onde + ": item inexistente " + i); }
    function salaOk(s, onde) { if (!salas[s]) p.push(onde + ": sala inexistente " + s); }
    function efeito(ef, onde) {
      (ef.poe || []).forEach(function (f) { flags[f] = true; });
      (ef.ganha || []).forEach(function (i) { itemOk(i, onde); }); (ef.consome || []).forEach(function (i) { itemOk(i, onde); }); (ef.solta || []).forEach(function (i) { itemOk(i, onde); });
      if (ef.mover) salaOk(ef.mover, onde);
    }
    function condicao(c, onde) {
      if (!c) return;
      (c.flags || []).forEach(function (f) { usados[f] = onde; });
      (c.tem || []).forEach(function (i) { itemOk(i, onde); }); (c.semItem || []).forEach(function (i) { itemOk(i, onde); });
      if (c.sala) salaOk(c.sala, onde);
    }
    ["id", "titulo", "objetivo", "intro", "inicio"].forEach(function (k) { if (!h[k]) p.push("falta " + k); });
    salaOk(h.inicio, "inicio");
    Object.keys(salas).forEach(function (k) {
      var s = salas[k], on = "sala " + k;
      if (!s.nome || !s.desc) p.push(on + ": falta nome ou descrição");
      Object.keys(s.saidas || {}).forEach(function (d) { var x = s.saidas[d]; salaOk(typeof x === "string" ? x : x.para, on + " saída " + d); if (typeof x !== "string") condicao(x.requer, on); });
      (s.itens || []).forEach(function (i) { itemOk(i, on); });
      (s.aoEntrar || []).forEach(function (r) { condicao(r.se, on); efeito(r, on); });
      (s.extras || []).forEach(function (r) { condicao(r.se, on); });
      (s.escuta || []).forEach(function (r) { condicao(r.se, on); });
      condicao(s.escuro, on);
      Object.keys(s.cenario || {}).forEach(function (c) { (s.cenario[c].exame || []).forEach(function (r) { condicao(r.se, on + " cenário " + c); efeito(r, on + " cenário " + c); }); });
      (s.npcs || []).forEach(function (n) { (n.falas || []).forEach(function (r) { condicao(r.se, on + " npc " + n.id); efeito(r, on + " npc " + n.id); }); });
    });
    Object.keys(itens).forEach(function (i) { if (!itens[i].nome) p.push("item " + i + ": falta nome"); (itens[i].exame || []).forEach(function (r) { condicao(r.se, "item " + i); efeito(r, "item " + i); }); });
    (h.usos || []).forEach(function (u, n) { var on = "uso " + n; if (u.item) itemOk(u.item, on); condicao(u.se, on); efeito(u, on); if (u.sala) salaOk(u.sala, on); });
    (h.dicas || []).forEach(function (d, n) { condicao(d.se, "dica " + n); if (!d.msg) p.push("dica " + n + ": sem texto"); });
    Object.keys(usados).forEach(function (f) { if (!flags[f]) p.push("a marca " + f + " é exigida em " + usados[f] + " mas nunca é ativada"); });
    return p;
  }
  // Joga a solução da história e devolve {estado, msgs}. Serve de teste e define o limite de passos.
  function jogar(h, nivel, cmds) {
    var e = criar(h, nivel), msgs = [];
    cmds.forEach(function (c) { msgs.push(comando(h, e, c)); });
    return { e: e, msgs: msgs };
  }
  function preparar(h) {
    h._passosSolucao = {};
    Object.keys(NIVEIS).forEach(function (n) {
      var sol = h.solucao && (h.solucao[n] || h.solucao.normal); if (!sol) return;
      var sem = Object.assign({}, h, { semLimite: true }), e = criar(sem, n), c = 0;
      sol.forEach(function (x) { var t = norm(x).split(" ")[0]; if (!CONSULTAS[t]) c++; comando(sem, e, x); });
      h._passosSolucao[n] = c;
    });
    return h;
  }

  var api = { NIVEIS: NIVEIS, criar: criar, comando: comando, descrever: descrever, exportar: exportar, importar: importar, validar: validar, jogar: jogar, preparar: preparar, limiteDe: limiteDe, dica: dica, norm: norm };
  if (typeof module !== "undefined") module.exports = api;
  raiz.HeimdallMotor = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), id = jogo.getAttribute("data-historia"), hist = raiz.Heimdall.historias && raiz.Heimdall.historias[id], e = null, chave = "heimdall-aventura-" + id;
  function D(m, f) { if (H.som) H.som.dizer("historia", m, f); else H.anunciar(f === undefined ? m : f); }
  if (H.som) H.som.botao(jogo);
  if (!hist) { jogo.textContent = "Esta aventura não foi encontrada."; return; }
  preparar(hist);
  var selNivel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { return H.el("option", { value: k, texto: NIVEIS[k].charAt(0).toUpperCase() + NIVEIS[k].slice(1) }); }));
  selNivel.value = "normal";
  var saida = H.el("ol", { id: "historico", "aria-label": "Histórico da aventura" });
  var campo = H.el("input", { id: "comando", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "comando", texto: "O que você faz? (digite ajuda para ver os comandos)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var bReiniciar = H.el("button", { type: "button", texto: "Recomeçar" });
  var bSalvar = H.el("button", { type: "button", texto: "Salvar" });
  var bCarregar = H.el("button", { type: "button", texto: "Carregar" });
  [H.el("label", { "for": "nivel", texto: "Nível (vale ao recomeçar)" }), selNivel, form, bReiniciar, bSalvar, bCarregar, saida].forEach(function (x) { jogo.appendChild(x); });
  function escrever(m) { saida.insertBefore(H.el("li", { texto: m }), saida.firstChild); D(m); }
  function salvar() {
    try { localStorage.setItem(chave, exportar(e)); return "Partida salva neste navegador."; } catch (x) { return "Não consegui salvar neste navegador."; }
  }
  function carregar() {
    var j; try { j = localStorage.getItem(chave); } catch (x) { j = null; }
    var o = j && importar(hist, j); if (!o) return "Não há partida salva para esta aventura.";
    e = o; selNivel.value = e.nivel; campo.disabled = !!e.fim;
    return "Partida carregada, nível " + NIVEIS[e.nivel] + ". " + descrever(hist, e);
  }
  function comecar() {
    e = criar(hist, selNivel.value); saida.textContent = ""; campo.disabled = false;
    var l = limiteDe(hist, e.nivel);
    var regra = e.nivel === "facil" ? "Nível fácil: dicas à vontade e sem limite de passos." : e.nivel === "normal" ? "Nível normal: " + DICAS_NORMAL + " dicas" + (l ? " e limite de " + l + " passos." : ".") : "Nível difícil: sem dicas" + (l ? ", limite de " + l + " passos" : "") + " e enigmas a mais.";
    escrever(hist.titulo + ". " + hist.intro + " Objetivo: " + hist.objetivo + " " + regra + " " + descrever(hist, e));
    campo.focus();
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var c = campo.value; campo.value = ""; var n = norm(c), m;
    if (n === "salvar") m = salvar(); else if (n === "carregar") m = carregar(); else if (n === "recomecar") { comecar(); return; } else m = comando(hist, e, c);
    escrever("> " + c + " — " + m);
    if (e.fim) { campo.disabled = true; bReiniciar.focus(); } else campo.focus();
  });
  bReiniciar.addEventListener("click", comecar);
  bSalvar.addEventListener("click", function () { escrever(salvar()); });
  bCarregar.addEventListener("click", function () { escrever(carregar()); });
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
