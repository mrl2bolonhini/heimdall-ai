// Xadrez contra o computador, feito para leitor de tela. Todas as regras: roque, en passant, promoção, xeque, mate, afogamento,
// repetição, regra dos 50 lances e material insuficiente. Você digita o lance (e4, Cf3, Cxe5, O-O, e7e8=D, ou de casa para casa: e2 e4).
// Letras das peças em português: R rei, D dama, T torre, B bispo, C cavalo; o peão não tem letra.
(function (raiz) {
  "use strict";
  var COLS = "abcdefgh";
  var NOME = { P: "peão", N: "cavalo", B: "bispo", R: "torre", Q: "dama", K: "rei" };
  var NOME_PL = { P: "peões", N: "cavalos", B: "bispos", R: "torres", Q: "damas", K: "reis" };
  var LETRA_PT = { N: "C", B: "B", R: "T", Q: "D", K: "R", P: "" };
  var PT_LETRA = { C: "N", B: "B", T: "R", D: "Q", R: "K" };
  var VALOR = { P: 100, N: 320, B: 330, R: 500, Q: 900, K: 0 };

  function nomeCasa(i) { return COLS[i & 7] + (8 - (i >> 3)); }
  function casa(s) { return /^[a-h][1-8]$/.test(s) ? (8 - Number(s[1])) * 8 + COLS.indexOf(s[0]) : -1; }
  function cor(p) { return p === p.toUpperCase() ? "w" : "b"; }
  function tipo(p) { return p.toUpperCase(); }

  // ---------- estado ----------
  function desdeFEN(fen) {
    var f = fen.trim().split(/\s+/), tab = [], r, i, ch;
    f[0].split("/").forEach(function (linha) { for (i = 0; i < linha.length; i++) { ch = linha[i]; if (/\d/.test(ch)) for (r = 0; r < Number(ch); r++) tab.push(""); else tab.push(ch); } });
    var e = { tab: tab, vez: f[1] === "b" ? "b" : "w", roque: { K: /K/.test(f[2] || ""), Q: /Q/.test(f[2] || ""), k: /k/.test(f[2] || ""), q: /q/.test(f[2] || "") },
      ep: !f[3] || f[3] === "-" ? -1 : casa(f[3]), meio: Number(f[4] || 0), num: Number(f[5] || 1), hist: [] };
    e.hist.push(chave(e));
    return e;
  }
  function inicial() { return desdeFEN("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"); }
  function chave(e) { return e.tab.map(function (p) { return p || "."; }).join("") + e.vez + (e.roque.K ? "K" : "") + (e.roque.Q ? "Q" : "") + (e.roque.k ? "k" : "") + (e.roque.q ? "q" : "") + e.ep; }
  function copiar(e) { return { tab: e.tab.slice(), vez: e.vez, roque: { K: e.roque.K, Q: e.roque.Q, k: e.roque.k, q: e.roque.q }, ep: e.ep, meio: e.meio, num: e.num, hist: e.hist }; }

  // ---------- ataques ----------
  var DN = [[-2, -1], [-2, 1], [-1, -2], [-1, 2], [1, -2], [1, 2], [2, -1], [2, 1]];
  var DK = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];
  var DB = [[-1, -1], [-1, 1], [1, -1], [1, 1]], DR = [[-1, 0], [1, 0], [0, -1], [0, 1]];

  function atacada(tab, i, por) {
    var r = i >> 3, c = i & 7, k, rr, cc, p, d, passo;
    var dir = por === "w" ? 1 : -1, peao = por === "w" ? "P" : "p";
    for (k = -1; k <= 1; k += 2) { rr = r + dir; cc = c + k; if (rr >= 0 && rr < 8 && cc >= 0 && cc < 8 && tab[rr * 8 + cc] === peao) return true; }
    var cav = por === "w" ? "N" : "n", rei = por === "w" ? "K" : "k";
    for (k = 0; k < 8; k++) {
      rr = r + DN[k][0]; cc = c + DN[k][1]; if (rr >= 0 && rr < 8 && cc >= 0 && cc < 8 && tab[rr * 8 + cc] === cav) return true;
      rr = r + DK[k][0]; cc = c + DK[k][1]; if (rr >= 0 && rr < 8 && cc >= 0 && cc < 8 && tab[rr * 8 + cc] === rei) return true;
    }
    for (d = 0; d < 8; d++) {   // 0-3: diagonais (bispo/dama); 4-7: retas (torre/dama)
      var dv = d < 4 ? DB[d] : DR[d - 4];
      rr = r + dv[0]; cc = c + dv[1];
      while (rr >= 0 && rr < 8 && cc >= 0 && cc < 8) {
        p = tab[rr * 8 + cc];
        if (p) { if (cor(p) === por && (tipo(p) === "Q" || tipo(p) === (d < 4 ? "B" : "R"))) return true; break; }
        rr += dv[0]; cc += dv[1];
      }
    }
    return false;
  }
  function achaRei(tab, v) { var rei = v === "w" ? "K" : "k"; for (var i = 0; i < 64; i++) if (tab[i] === rei) return i; return -1; }
  function emXeque(e, v) { v = v || e.vez; var r = achaRei(e.tab, v); return r >= 0 && atacada(e.tab, r, v === "w" ? "b" : "w"); }

  // ---------- geração de lances ----------
  function pseudo(e) {
    var tab = e.tab, v = e.vez, out = [], i, p, t, r, c, k, rr, cc, j, dv, d;
    function add(de, para, extra) {
      var m = { de: de, para: para, peca: tab[de], cap: tab[para] || null };
      if (extra) for (var x in extra) m[x] = extra[x];
      out.push(m);
    }
    function promos(de, para, cap) { ["Q", "R", "B", "N"].forEach(function (pr) { add(de, para, { promo: v === "w" ? pr : pr.toLowerCase() }); }); }
    for (i = 0; i < 64; i++) {
      p = tab[i]; if (!p || cor(p) !== v) continue;
      t = tipo(p); r = i >> 3; c = i & 7;
      if (t === "P") {
        var dir = v === "w" ? -1 : 1, ini = v === "w" ? 6 : 1, ult = v === "w" ? 0 : 7;
        rr = r + dir;
        if (rr >= 0 && rr < 8 && !tab[rr * 8 + c]) {
          if (rr === ult) promos(i, rr * 8 + c); else add(i, rr * 8 + c);
          if (r === ini && !tab[(rr + dir) * 8 + c]) add(i, (rr + dir) * 8 + c, { duplo: true });
        }
        for (k = -1; k <= 1; k += 2) {
          cc = c + k; if (cc < 0 || cc > 7 || rr < 0 || rr > 7) continue;
          j = rr * 8 + cc;
          if (tab[j] && cor(tab[j]) !== v) { if (rr === ult) promos(i, j); else add(i, j); }
          else if (j === e.ep) add(i, j, { ep: true, cap: v === "w" ? "p" : "P" });
        }
      } else if (t === "N" || t === "K") {
        var ds = t === "N" ? DN : DK;
        for (k = 0; k < 8; k++) { rr = r + ds[k][0]; cc = c + ds[k][1]; if (rr < 0 || rr > 7 || cc < 0 || cc > 7) continue; j = rr * 8 + cc; if (!tab[j] || cor(tab[j]) !== v) add(i, j); }
      } else {
        for (d = 0; d < 8; d++) {
          if (t === "B" && d >= 4) continue; if (t === "R" && d < 4) continue;
          dv = d < 4 ? DB[d] : DR[d - 4]; rr = r + dv[0]; cc = c + dv[1];
          while (rr >= 0 && rr < 8 && cc >= 0 && cc < 8) {
            j = rr * 8 + cc;
            if (!tab[j]) add(i, j); else { if (cor(tab[j]) !== v) add(i, j); break; }
            rr += dv[0]; cc += dv[1];
          }
        }
      }
    }
    // roques
    var rei0 = v === "w" ? 60 : 4, rt = v === "w" ? "R" : "r", rk = v === "w" ? "K" : "k", inim = v === "w" ? "b" : "w";
    if (tab[rei0] === rk && !atacada(tab, rei0, inim)) {
      if (e.roque[v === "w" ? "K" : "k"] && tab[rei0 + 3] === rt && !tab[rei0 + 1] && !tab[rei0 + 2] && !atacada(tab, rei0 + 1, inim) && !atacada(tab, rei0 + 2, inim)) add(rei0, rei0 + 2, { roque: "K" });
      if (e.roque[v === "w" ? "Q" : "q"] && tab[rei0 - 4] === rt && !tab[rei0 - 1] && !tab[rei0 - 2] && !tab[rei0 - 3] && !atacada(tab, rei0 - 1, inim) && !atacada(tab, rei0 - 2, inim)) add(rei0, rei0 - 2, { roque: "Q" });
    }
    return out;
  }
  function fazer(e, m) {
    var n = copiar(e), tab = n.tab, v = e.vez, p = tab[m.de];
    tab[m.de] = ""; tab[m.para] = m.promo || p;
    if (m.ep) tab[m.para + (v === "w" ? 8 : -8)] = "";
    if (m.roque === "K") { tab[m.para - 1] = tab[m.para + 1]; tab[m.para + 1] = ""; }
    if (m.roque === "Q") { tab[m.para + 1] = tab[m.para - 2]; tab[m.para - 2] = ""; }
    if (p === "K") { n.roque.K = false; n.roque.Q = false; } else if (p === "k") { n.roque.k = false; n.roque.q = false; }
    if (m.de === 63 || m.para === 63) n.roque.K = false; if (m.de === 56 || m.para === 56) n.roque.Q = false;
    if (m.de === 7 || m.para === 7) n.roque.k = false; if (m.de === 0 || m.para === 0) n.roque.q = false;
    n.ep = m.duplo ? (m.de + m.para) / 2 : -1;
    n.meio = (tipo(p) === "P" || m.cap) ? 0 : e.meio + 1;
    if (v === "b") n.num = e.num + 1;
    n.vez = v === "w" ? "b" : "w";
    n.hist = e.hist.concat([chave(n)]);
    return n;
  }
  function gerar(e) {
    return pseudo(e).filter(function (m) { var n = fazer(e, m); return !emXeque(n, e.vez); });
  }

  // ---------- fim de jogo ----------
  function materialInsuficiente(tab) {
    var ps = tab.filter(function (p) { return p && tipo(p) !== "K"; });
    if (!ps.length) return true;
    if (ps.length === 1 && (tipo(ps[0]) === "B" || tipo(ps[0]) === "N")) return true;
    if (ps.length === 2 && ps.every(function (p) { return tipo(p) === "B"; })) {
      var cores = []; tab.forEach(function (p, i) { if (p && tipo(p) === "B") cores.push(((i >> 3) + (i & 7)) % 2); });
      return cores[0] === cores[1];
    }
    return false;
  }
  function situacao(e, legais) {
    legais = legais || gerar(e);
    if (!legais.length) return emXeque(e) ? { fim: "mate", vencedor: e.vez === "w" ? "b" : "w" } : { fim: "afogamento" };
    if (materialInsuficiente(e.tab)) return { fim: "material" };
    if (e.meio >= 100) return { fim: "cinquenta" };
    var k = e.hist[e.hist.length - 1], rep = e.hist.filter(function (x) { return x === k; }).length;
    if (rep >= 3) return { fim: "repeticao" };
    return { fim: null, xeque: emXeque(e) };
  }

  // ---------- notação ----------
  function san(e, m, legais) {
    legais = legais || gerar(e);
    var base, t = tipo(m.peca);
    if (m.roque) base = m.roque === "K" ? "O-O" : "O-O-O";
    else if (t === "P") base = (m.cap ? COLS[m.de & 7] + "x" : "") + nomeCasa(m.para) + (m.promo ? "=" + LETRA_PT[tipo(m.promo)] : "");
    else {
      var outros = legais.filter(function (o) { return !(o.de === m.de && o.para === m.para && o.promo === m.promo) && !o.roque && o.peca === m.peca && o.para === m.para; }), d = "";
      if (outros.length) {
        var mesmaCol = outros.some(function (o) { return (o.de & 7) === (m.de & 7); }), mesmaLin = outros.some(function (o) { return (o.de >> 3) === (m.de >> 3); });
        d = !mesmaCol ? COLS[m.de & 7] : !mesmaLin ? String(8 - (m.de >> 3)) : nomeCasa(m.de);
      }
      base = LETRA_PT[t] + d + (m.cap ? "x" : "") + nomeCasa(m.para);
    }
    var depois = fazer(e, m);
    if (emXeque(depois)) base += gerar(depois).length ? "+" : "#";
    return base;
  }
  function falar(e, m) {
    var t = tipo(m.peca), nome = NOME[t].charAt(0).toUpperCase() + NOME[t].slice(1);
    if (m.roque) return m.roque === "K" ? "roque pequeno, com o rei de " + nomeCasa(m.de) + " para " + nomeCasa(m.para) : "roque grande, com o rei de " + nomeCasa(m.de) + " para " + nomeCasa(m.para);
    var s = nome + " de " + nomeCasa(m.de) + (m.cap ? " captura " + NOME[tipo(m.cap)] + " em " + nomeCasa(m.ep ? m.para : m.para) : " para " + nomeCasa(m.para));
    if (m.ep) s += ", en passant";
    if (m.promo) s += ", e promove a " + NOME[tipo(m.promo)];
    return s;
  }

  // Lê o que a pessoa digitou. Devolve {lance} ou {erro}.
  function norm(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").trim(); }
  function lerLance(e, texto, legais) {
    legais = legais || gerar(e);
    var t = norm(texto).replace(/\s+/g, " ");
    if (!t) return { erro: "Digite um lance. Exemplos: e4, Cf3, Cxe5, O-O, ou de casa para casa: e2 e4." };
    var tl = t.toLowerCase();
    if (/^(0-0-0|o-o-o|roque grande)$/i.test(t)) return achar(legais.filter(function (m) { return m.roque === "Q"; }), "o roque grande");
    if (/^(0-0|o-o|roque pequeno|roque)$/i.test(t)) return achar(legais.filter(function (m) { return m.roque === "K"; }), "o roque pequeno");
    // de casa para casa: "e2e4", "e2 e4", "e2-e4", "e2 para e4"
    var cc = tl.replace(/\s*(para|a|-|x)\s*/g, " ").replace(/\s+/g, " ").match(/^([a-h][1-8]) ?([a-h][1-8]) ?([qrbndtc])?$/);
    if (cc) {
      var de = casa(cc[1]), para = casa(cc[2]), pr = cc[3] ? (PT_LETRA[cc[3].toUpperCase()] || cc[3].toUpperCase()) : "Q";
      var c = legais.filter(function (m) { return m.de === de && m.para === para; });
      if (!c.length) return { erro: "O lance " + cc[1] + " para " + cc[2] + " não é permitido agora." + (e.tab[de] && cor(e.tab[de]) === e.vez ? "" : " Não há peça sua em " + cc[1] + ".") };
      var com = c.filter(function (m) { return !m.promo || tipo(m.promo) === pr; });
      return { lance: com[0] || c[0] };
    }
    // notação com letra da peça em português
    var m = t.replace(/[+#!?]/g, "").match(/^([RDTBC])?([a-h])?([1-8])?x?([a-h][1-8])(?:=?([DTBC]))?$/);
    if (!m) return { erro: "Não entendi o lance \"" + texto + "\". Use e4, Cf3, Cxe5, O-O ou e2 e4. Digite ajuda para ver tudo." };
    var peca = m[1] ? PT_LETRA[m[1]] : "P", dest = casa(m[4]), prom = m[5] ? PT_LETRA[m[5]] : null;
    if (!m[1] && m[2] && !m[3] && !/x/.test(t) && m[2] + "" !== "") { /* coluna de origem do peão sem captura: ignora */ }
    var cands = legais.filter(function (x) {
      if (x.roque || tipo(x.peca) !== peca || x.para !== dest) return false;
      if (m[2] && COLS[x.de & 7] !== m[2]) return false;
      if (m[3] && String(8 - (x.de >> 3)) !== m[3]) return false;
      return true;
    });
    if (cands.length > 1 && peca === "P" && cands.every(function (x) { return x.promo; })) {
      var q = prom || "Q"; cands = cands.filter(function (x) { return tipo(x.promo) === q; });
    }
    if (!cands.length) return { erro: "O lance " + texto + " não é permitido agora. Digite lances para ver os que você pode fazer." };
    if (cands.length > 1) return { erro: "O lance " + texto + " é ambíguo: " + cands.map(function (x) { return NOME[tipo(x.peca)] + " de " + nomeCasa(x.de); }).join(" ou ") + ". Escreva a coluna ou a linha de origem, por exemplo " + (LETRA_PT[peca] || "") + COLS[cands[0].de & 7] + nomeCasa(dest) + "." };
    return { lance: cands[0] };
    function achar(l, nome) { return l.length ? { lance: l[0] } : { erro: "Não dá para fazer " + nome + " agora." }; }
  }

  // ---------- leitura do tabuleiro ----------
  function corNome(v) { return v === "w" ? "brancas" : "pretas"; }
  function pecaFalada(p) { return NOME[tipo(p)] + (cor(p) === "w" ? " branco" : " preto") .replace("branco", { P: "branco", N: "branco", B: "branco", R: "branca", Q: "branca", K: "branco" }[tipo(p)]).replace("preto", { P: "preto", N: "preto", B: "preto", R: "preta", Q: "preta", K: "preto" }[tipo(p)]); }
  function lista(arr) { return arr.length <= 1 ? arr.join("") : arr.slice(0, -1).join(", ") + " e " + arr[arr.length - 1]; }
  function lerPecas(e, v) {
    var grupos = {}, out = [];
    e.tab.forEach(function (p, i) { if (p && cor(p) === v) (grupos[tipo(p)] = grupos[tipo(p)] || []).push(nomeCasa(i)); });
    ["K", "Q", "R", "B", "N", "P"].forEach(function (t) { var g = grupos[t]; if (g) out.push((g.length > 1 ? NOME_PL[t] : NOME[t]) + " em " + lista(g.sort())); });
    return "Peças " + (v === "w" ? "brancas" : "pretas") + ": " + out.join("; ") + ".";
  }
  function lerLinha(e, n) {
    if (n < 1 || n > 8) return "Linha inválida. Use de 1 a 8.";
    var r = 8 - n, partes = [], c, ini = -1;
    function fecha(fim) { if (ini >= 0) { partes.push(fim === ini ? COLS[ini] + n + " vazia" : "de " + COLS[ini] + n + " a " + COLS[fim] + n + " vazias"); ini = -1; } }
    for (c = 0; c < 8; c++) { var p = e.tab[r * 8 + c]; if (!p) { if (ini < 0) ini = c; } else { fecha(c - 1); partes.push(COLS[c] + n + " " + pecaFalada(p)); } }
    fecha(7);
    return "Linha " + n + ": " + partes.join(", ") + ".";
  }
  function lerColuna(e, letra) {
    var c = COLS.indexOf(letra); if (c < 0) return "Coluna inválida. Use de a até h.";
    var partes = [], r, ini = -1;
    function fecha(fim) { if (ini >= 0) { partes.push(fim === ini ? letra + (8 - ini) + " vazia" : "de " + letra + (8 - ini) + " a " + letra + (8 - fim) + " vazias"); ini = -1; } }
    for (r = 0; r < 8; r++) { var p = e.tab[r * 8 + c]; if (!p) { if (ini < 0) ini = r; } else { fecha(r - 1); partes.push(letra + (8 - r) + " " + pecaFalada(p)); } }
    fecha(7);
    return "Coluna " + letra + ": " + partes.join(", ") + ".";
  }
  function lerCasa(e, s) {
    var i = casa(s); if (i < 0) return "Casa inválida. Use uma letra de a até h e um número de 1 a 8, como e4.";
    var p = e.tab[i]; return s + ": " + (p ? pecaFalada(p) : "vazia") + ".";
  }
  function material(e) {
    var s = { w: 0, b: 0 }; e.tab.forEach(function (p) { if (p) s[cor(p)] += VALOR[tipo(p)]; });
    var d = Math.round((s.w - s.b) / 100);
    return d === 0 ? "Material igual." : (d > 0 ? "As brancas" : "As pretas") + " estão com " + Math.abs(d) + (Math.abs(d) === 1 ? " ponto" : " pontos") + " de material a mais.";
  }
  function desenho(e) {
    var linhas = [], r, c; for (r = 0; r < 8; r++) { var l = (8 - r) + " "; for (c = 0; c < 8; c++) l += (e.tab[r * 8 + c] || ((r + c) % 2 ? "." : "-")) + " "; linhas.push(l); }
    return linhas.join("\n") + "\n  a b c d e f g h";
  }

  // ---------- inteligência do computador ----------
  var CENTRO = [0, 1, 2, 3, 3, 2, 1, 0];
  function posBonus(p, i) {
    var t = tipo(p), r = i >> 3, c = i & 7, lin = cor(p) === "w" ? 7 - r : r, cen = CENTRO[r] + CENTRO[c];
    if (t === "P") return lin * 6 + (cen >= 4 ? 8 : 0) - (lin === 1 && (c === 3 || c === 4) ? 0 : 0);
    if (t === "N") return cen * 8 - (lin === 0 ? 12 : 0);
    if (t === "B") return cen * 4 - (lin === 0 ? 8 : 0);
    if (t === "R") return lin === 6 ? 15 : 0;
    if (t === "Q") return cen * 2;
    return lin === 0 ? 10 : -cen * 3;   // rei: fica atrás
  }
  function avaliar(e) {   // do ponto de vista de quem joga
    var s = 0; for (var i = 0; i < 64; i++) { var p = e.tab[i]; if (!p) continue; var v = VALOR[tipo(p)] + posBonus(p, i); s += cor(p) === "w" ? v : -v; }
    return e.vez === "w" ? s : -s;
  }
  function ordenar(ms) {
    return ms.sort(function (a, b) { return (b.cap ? VALOR[tipo(b.cap)] * 10 - VALOR[tipo(b.peca)] : 0) + (b.promo ? 800 : 0) - ((a.cap ? VALOR[tipo(a.cap)] * 10 - VALOR[tipo(a.peca)] : 0) + (a.promo ? 800 : 0)); });
  }
  var MATE = 100000;
  function quiesce(e, alfa, beta, prof) {
    var base = avaliar(e); if (prof <= 0) return base;
    if (base >= beta) return base; if (base > alfa) alfa = base;
    var ms = ordenar(gerar(e).filter(function (m) { return m.cap || m.promo; }));
    for (var i = 0; i < ms.length; i++) { var s = -quiesce(fazer(e, ms[i]), -beta, -alfa, prof - 1); if (s >= beta) return s; if (s > alfa) alfa = s; }
    return alfa;
  }
  function buscar(e, prof, alfa, beta, q) {
    var ms = gerar(e);
    if (!ms.length) return emXeque(e) ? -MATE - prof : 0;
    if (prof <= 0) return q ? quiesce(e, alfa, beta, q) : avaliar(e);
    ordenar(ms);
    for (var i = 0; i < ms.length; i++) { var s = -buscar(fazer(e, ms[i]), prof - 1, -beta, -alfa, q); if (s >= beta) return s; if (s > alfa) alfa = s; }
    return alfa;
  }
  var NIVEIS = { facil: { nome: "fácil", prof: 1, margem: 140, q: 0 }, medio: { nome: "médio", prof: 2, margem: 40, q: 2 }, dificil: { nome: "difícil", prof: 3, margem: 8, q: 3 } };
  function escolher(e, nivel, rnd) {
    var cfg = NIVEIS[nivel] || NIVEIS.medio, ms = gerar(e); if (!ms.length) return null;
    var pontuados = ms.map(function (m) { return { m: m, s: -buscar(fazer(e, m), cfg.prof - 1, -MATE * 2, MATE * 2, cfg.q) }; });
    var melhor = Math.max.apply(null, pontuados.map(function (x) { return x.s; }));
    var bons = pontuados.filter(function (x) { return x.s >= melhor - cfg.margem; });
    var r = rnd || function (n) { return Math.floor(Math.random() * n); };
    return bons[r(bons.length)].m;
  }

  // ---------- partida ----------
  function novaPartida(nivel, corJogador) {
    return { e: inicial(), nivel: NIVEIS[nivel] ? nivel : "medio", eu: corJogador === "b" ? "b" : "w", pilha: [], lances: [], fim: null };
  }
  function fraseFim(e, s) {
    if (s.fim === "mate") return "Xeque-mate! Vitória das " + corNome(s.vencedor) + ".";
    if (s.fim === "afogamento") return "Empate por afogamento: quem joga não tem lance legal e o rei não está em xeque.";
    if (s.fim === "material") return "Empate por material insuficiente: nenhum lado consegue dar mate.";
    if (s.fim === "cinquenta") return "Empate pela regra dos cinquenta lances, sem captura nem movimento de peão.";
    if (s.fim === "repeticao") return "Empate por repetição: a mesma posição apareceu três vezes.";
    return "";
  }
  function aplicar(g, m) {
    var legais = gerar(g.e), notacao = san(g.e, m, legais), falado = falar(g.e, m);
    g.pilha.push(g.e); g.e = fazer(g.e, m); g.lances.push(notacao);
    var s = situacao(g.e); g.fim = s.fim ? s : null;
    return { san: notacao, falado: falado, xeque: !!s.xeque, situacao: s };
  }
  // O jogador joga um lance (texto); o computador responde. Devolve a mensagem falada.
  function jogar(g, texto, rnd) {
    if (g.fim) return { msg: "A partida terminou. Comece uma nova." };
    if (g.e.vez !== g.eu) return { msg: "Não é a sua vez." };
    var r = lerLance(g.e, texto); if (r.erro) return { msg: r.erro, erro: true };
    var a = aplicar(g, r.lance), msg = "Você jogou " + a.falado + " (" + a.san + ").";
    if (g.fim) return { msg: msg + " " + fraseFim(g.e, g.fim), fim: true };
    if (a.xeque) msg += " Xeque no computador.";
    return { msg: msg + " " + responder(g, rnd) };
  }
  function responder(g, rnd) {
    var m = escolher(g.e, g.nivel, rnd); if (!m) return "";
    var a = aplicar(g, m), msg = "O computador jogou " + a.falado + " (" + a.san + ").";
    if (g.fim) return msg + " " + fraseFim(g.e, g.fim);
    if (a.xeque) msg += " Seu rei está em xeque!";
    return msg + " Sua vez.";
  }
  function desfazer(g) {
    if (!g.pilha.length) return "Ainda não há lance para desfazer.";
    var n = (g.pilha.length >= 2 && g.e.vez === g.eu) ? 2 : 1;
    while (n-- > 0 && g.pilha.length) { g.e = g.pilha.pop(); g.lances.pop(); }
    g.fim = null;
    if (g.e.vez !== g.eu) { return "Desfiz o último lance, mas ainda não é a sua vez." }
    return "Desfeito. Sua vez.";
  }
  function historico(g) {
    if (!g.lances.length) return "Nenhum lance ainda.";
    var out = [], i; for (i = 0; i < g.lances.length; i += 2) out.push((i / 2 + 1) + ". " + g.lances[i] + (g.lances[i + 1] ? " " + g.lances[i + 1] : ""));
    return out.join("; ") + ".";
  }
  function lancesLegais(g) {
    var l = gerar(g.e); return l.length + " lances: " + l.map(function (m) { return san(g.e, m, l); }).sort().join(", ") + ".";
  }
  function ajuda() {
    return "Digite o lance de um destes jeitos: e4 (peão), Cf3 (cavalo), Cxe5 (captura), exd5 (peão captura), O-O (roque pequeno), O-O-O (roque grande), e8=D (promove a dama), ou de casa para casa: e2 e4. " +
      "As letras das peças são R rei, D dama, T torre, B bispo, C cavalo. Para consultar: tabuleiro, pecas, linha 4, coluna e, casa e4, lances, historico, material, ultimo, dica, desfazer, desistir.";
  }
  function dica(g) {
    var m = escolher(g.e, "dificil", function () { return 0; }); return m ? "Sugestão: " + falar(g.e, m) + " (" + san(g.e, m) + ")." : "Não há lances.";
  }
  // Comandos de consulta; devolve null se o texto não for um comando (aí é um lance).
  function consulta(g, texto) {
    var t = norm(texto).toLowerCase().replace(/\s+/g, " "), p = t.split(" "), v = p[0];
    if (v === "ajuda" || v === "?") return ajuda();
    if (v === "tabuleiro") return lerPecas(g.e, "w") + " " + lerPecas(g.e, "b") + " Vez das " + corNome(g.e.vez) + ".";
    if (v === "pecas") return p[1] && /^(p|pret)/.test(p[1]) ? lerPecas(g.e, "b") : p[1] && /^(b|bran)/.test(p[1]) ? lerPecas(g.e, "w") : lerPecas(g.e, "w") + " " + lerPecas(g.e, "b");
    if (v === "linha" && /^[1-8]$/.test(p[1] || "")) return lerLinha(g.e, Number(p[1]));
    if (v === "coluna" && /^[a-h]$/.test(p[1] || "")) return lerColuna(g.e, p[1]);
    if (v === "casa" && p[1]) return lerCasa(g.e, p[1]);
    if (v === "lances" || v === "movimentos") return lancesLegais(g);
    if (v === "historico") return historico(g);
    if (v === "material") return material(g.e);
    if (v === "ultimo") return g.lances.length ? "Último lance: " + g.lances[g.lances.length - 1] + "." : "Nenhum lance ainda.";
    if (v === "dica") return g.fim ? "A partida terminou." : dica(g);
    if (v === "desfazer") return desfazer(g);
    if (v === "desistir") { g.fim = { fim: "desistencia" }; return "Você desistiu. Vitória do computador."; }
    return null;
  }

  var api = { inicial: inicial, desdeFEN: desdeFEN, gerar: gerar, fazer: fazer, emXeque: emXeque, situacao: situacao, san: san, falar: falar, lerLance: lerLance, nomeCasa: nomeCasa, casa: casa,
    escolher: escolher, novaPartida: novaPartida, jogar: jogar, responder: responder, consulta: consulta, desfazer: desfazer, historico: historico, lerPecas: lerPecas, lerLinha: lerLinha,
    lerColuna: lerColuna, lerCasa: lerCasa, material: material, desenho: desenho, ajuda: ajuda, NIVEIS: NIVEIS, fraseFim: fraseFim, aplicar: aplicar, pecaFalada: pecaFalada };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;

  var H = raiz.Heimdall, jogo = document.getElementById("jogo"), g = null;
  var nivelSel = H.el("select", { id: "nivel" }, Object.keys(NIVEIS).map(function (k) { return H.el("option", { value: k, texto: NIVEIS[k].nome.charAt(0).toUpperCase() + NIVEIS[k].nome.slice(1) }); }));
  var corSel = H.el("select", { id: "cor" }, [H.el("option", { value: "w", texto: "Brancas (você começa)" }), H.el("option", { value: "b", texto: "Pretas (o computador começa)" })]);
  var novoBtn = H.el("button", { type: "button", texto: "Nova partida" });
  var campo = H.el("input", { id: "lance", type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
  var form = H.el("form", {}, [H.el("label", { "for": "lance", texto: "Seu lance ou comando (ajuda mostra tudo)" }), campo, H.el("button", { type: "submit", texto: "Enviar" })]);
  var historia = H.el("ol", { id: "historico", "aria-label": "Histórico da partida" });
  var visual = H.el("pre", { id: "visual", "aria-hidden": "true" });
  [H.el("label", { "for": "nivel", texto: "Nível do computador" }), nivelSel, H.el("label", { "for": "cor", texto: "Sua cor" }), corSel, novoBtn, form, historia, visual].forEach(function (x) { jogo.appendChild(x); });
  function escrever(msg) { historia.insertBefore(H.el("li", { texto: msg }), historia.firstChild); H.anunciar(msg); }
  function atualizar() { visual.textContent = desenho(g.e); }
  function comecar() {
    g = novaPartida(nivelSel.value, corSel.value); historia.textContent = ""; campo.disabled = false;
    var msg = "Nova partida, nível " + NIVEIS[g.nivel].nome + ", você joga de " + (g.eu === "w" ? "brancas" : "pretas") + ". ";
    if (g.eu === "b") msg += responder(g); else msg += "Sua vez. Digite um lance, por exemplo e4, ou ajuda.";
    atualizar(); escrever(msg); campo.focus();
  }
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var t = campo.value; campo.value = "";
    var c = consulta(g, t), msg = c;
    if (c === null) { var r = jogar(g, t); msg = r.msg; }
    atualizar(); escrever("> " + t + " — " + msg);
    if (g.fim) { campo.disabled = true; novoBtn.focus(); } else campo.focus();
  });
  novoBtn.addEventListener("click", comecar);
  comecar();
})(typeof window !== "undefined" ? window : globalThis);
