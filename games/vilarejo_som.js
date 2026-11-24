// Sons do Vilarejo Sitiado: efeitos sintetizados por modelos físicos simples, sem bipes e sem arquivos de áudio.
// Cada som é calculado em amostras (Float32Array) a partir de uma semente, então os testes rodam sem navegador e cada som tem variações.
// Armas: estampido com estalo, corpo, trovão grave e eco do vilarejo. Vozes: fonte glotal com formantes (vogais). Animais: rosnado com trilo,
// latido, guincho. Ambiente: passos por tipo de piso, portas, chaves, munição, impactos, ricochete.
// Se existirem gravações reais em games/sons/<nome>.wav no futuro, o jogo poderá usá-las no lugar destas; hoje tudo é gerado aqui.
(function (raiz) {
  "use strict";
  var PI2 = Math.PI * 2;

  function rng(semente) {
    var s = semente >>> 0;
    return function () { s = (s + 0x6D2B79F5) >>> 0; var t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function hash(txt) { var h = 2166136261, i; for (i = 0; i < txt.length; i++) { h ^= txt.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function zeros(sr, seg) { return new Float32Array(Math.max(1, Math.round(sr * seg))); }

  // Filtro biquad (receitas do Audio EQ Cookbook): passa-baixa, passa-alta e passa-faixa. O estado fica no objeto, então a frequência pode mudar no meio do som.
  function Bq(tipo, f, q, sr) { this.sr = sr; this.x1 = 0; this.x2 = 0; this.y1 = 0; this.y2 = 0; this.set(tipo, f, q); }
  Bq.prototype.set = function (tipo, f, q) {
    f = Math.max(20, Math.min(this.sr * 0.45, f)); q = q || 0.707;
    var w = PI2 * f / this.sr, c = Math.cos(w), s = Math.sin(w), al = s / (2 * q), b0, b1, b2;
    if (tipo === "lp") { b0 = (1 - c) / 2; b1 = 1 - c; b2 = b0; } else if (tipo === "hp") { b0 = (1 + c) / 2; b1 = -(1 + c); b2 = b0; } else { b0 = al; b1 = 0; b2 = -al; }
    var a0 = 1 + al;
    this.b0 = b0 / a0; this.b1 = b1 / a0; this.b2 = b2 / a0; this.a1 = -2 * c / a0; this.a2 = (1 - al) / a0;
  };
  Bq.prototype.p = function (x) {
    var y = this.b0 * x + this.b1 * this.x1 + this.b2 * this.x2 - this.a1 * this.y1 - this.a2 * this.y2;
    this.x2 = this.x1; this.x1 = x; this.y2 = this.y1; this.y1 = y; return y;
  };
  function filtrar(x, tipo, f, q, sr) { var b = new Bq(tipo, f, q, sr), o = new Float32Array(x.length), i; for (i = 0; i < x.length; i++) o[i] = b.p(x[i]); return o; }
  function somar(dest, src, ganho, atrasoSeg, sr) {
    var ini = Math.round((atrasoSeg || 0) * sr), i;
    for (i = 0; i < src.length && ini + i < dest.length; i++) dest[ini + i] += src[i] * ganho;
    return dest;
  }
  function normalizar(x, alvo) {
    var pico = 0, i; for (i = 0; i < x.length; i++) { var a = Math.abs(x[i]); if (a > pico) pico = a; }
    if (pico > 0) { var k = (alvo || 0.9) / pico; for (i = 0; i < x.length; i++) x[i] *= k; }
    return x;
  }
  function rms(x) { var s = 0, i; for (i = 0; i < x.length; i++) s += x[i] * x[i]; return Math.sqrt(s / Math.max(1, x.length)); }
  function saturar(x, k) { var d = Math.tanh(k), i; for (i = 0; i < x.length; i++) x[i] = Math.tanh(x[i] * k) / d; return x; }
  function curva(pts, t) {
    if (t <= pts[0][0]) return pts[0][1];
    for (var i = 1; i < pts.length; i++) if (t <= pts[i][0]) { var a = pts[i - 1], b = pts[i]; return a[1] + (b[1] - a[1]) * (t - a[0]) / Math.max(1e-9, b[0] - a[0]); }
    return pts[pts.length - 1][1];
  }
  // Eco e reverberação do vilarejo: combs com amortecimento (o brilho some na cauda, como ao ar livre) e ecos discretos de paredes.
  function reverbe(x, sr, rt60, umido, cauda, ecos) {
    var n = x.length + Math.round(sr * (cauda || 0)), y = new Float32Array(n), atrasos = [0.0297, 0.0371, 0.0411, 0.0437, 0.0521, 0.0613], cs = [], i, k;
    for (k = 0; k < atrasos.length; k++) cs.push({ b: new Float32Array(Math.round(atrasos[k] * sr)), i: 0, g: Math.pow(10, -3 * atrasos[k] / rt60), lp: 0 });
    for (i = 0; i < n; i++) {
      var s = i < x.length ? x[i] : 0, acc = 0;
      for (k = 0; k < cs.length; k++) { var c = cs[k], o = c.b[c.i]; c.lp = o * 0.62 + c.lp * 0.38; c.b[c.i] = s + c.lp * c.g; c.i = (c.i + 1) % c.b.length; acc += o; }
      y[i] = s + umido * acc * 0.38;
    }
    (ecos || []).forEach(function (e) { somar(y, filtrar(x, "lp", e[2] || 1800, 0.7, sr), e[1], e[0], sr); });
    return y;
  }
  function estalo(sr, freqs, tau, dur, r) {
    var n = zeros(sr, dur), i, t, k, v;
    for (i = 0; i < n.length; i++) {
      t = i / sr; v = (r() * 2 - 1) * Math.exp(-t / 0.0007) * 0.6;
      for (k = 0; k < freqs.length; k++) v += Math.sin(PI2 * freqs[k] * t) * Math.exp(-t / tau) / (k + 1);
      n[i] = v;
    }
    return n;
  }

  // ---------- armas ----------
  function tiro(sr, r, o) {
    var p = o.pitch || 1, curto = o.curto, n = zeros(sr, curto ? 1.1 : 1.6), cr = new Float32Array(n.length), co = new Float32Array(n.length), bo = new Float32Array(n.length), fase = 0, i, t, f, y = new Float32Array(n.length);
    for (i = 0; i < n.length; i++) {
      t = i / sr;
      cr[i] = (r() * 2 - 1) * Math.exp(-t / 0.0035);
      co[i] = (r() * 2 - 1) * Math.exp(-t / 0.03);
      f = (78 + 190 * Math.exp(-t / 0.03)) * p; fase += PI2 * f / sr;
      bo[i] = Math.sin(fase) * Math.exp(-t / (curto ? 0.04 : 0.065)) + 0.35 * Math.sin(fase * 2.02) * Math.exp(-t / 0.04);
    }
    cr = filtrar(cr, "hp", 1400, 0.7, sr); co = filtrar(co, "lp", 3500, 0.7, sr);
    for (i = 0; i < n.length; i++) y[i] = 1.4 * cr[i] + 1.3 * co[i] + 0.8 * bo[i];
    saturar(y, 2.3);
    return normalizar(filtrar(reverbe(y, sr, 0.9, 0.55, 0.35, [[0.11, 0.2, 1500], [0.29, 0.1, 1100]]), "hp", 60, 0.7, sr), 0.97);
  }
  function espingarda(sr, r) {
    var n = zeros(sr, 1.9), cr = new Float32Array(n.length), co = new Float32Array(n.length), bo = new Float32Array(n.length), tr = new Float32Array(n.length), fase = 0, i, t, f, y = new Float32Array(n.length);
    for (i = 0; i < n.length; i++) {
      t = i / sr;
      cr[i] = (r() * 2 - 1) * Math.exp(-t / 0.005);
      co[i] = (r() * 2 - 1) * Math.exp(-t / 0.065);
      tr[i] = (r() * 2 - 1) * Math.exp(-t / 0.22);
      f = 58 + 140 * Math.exp(-t / 0.05); fase += PI2 * f / sr;
      bo[i] = Math.sin(fase) * Math.exp(-t / 0.14) + 0.4 * Math.sin(fase * 1.98) * Math.exp(-t / 0.08);
    }
    cr = filtrar(cr, "hp", 900, 0.7, sr); co = filtrar(co, "lp", 2200, 0.7, sr); tr = filtrar(tr, "lp", 380, 0.8, sr);
    for (i = 0; i < n.length; i++) y[i] = 1.2 * cr[i] + 1.7 * co[i] + 1.0 * bo[i] + 0.7 * tr[i];
    saturar(y, 2.8);
    return normalizar(filtrar(reverbe(y, sr, 1.2, 0.6, 0.5, [[0.13, 0.25, 1300], [0.33, 0.14, 900], [0.52, 0.07, 700]]), "hp", 50, 0.7, sr), 0.99);
  }
  function cliqueSeco(sr, r) { var n = estalo(sr, [2900, 1700], 0.012, 0.09, r); somar(n, estalo(sr, [2300], 0.01, 0.05, r), 0.6, 0.035, sr); return normalizar(n, 0.7); }
  function recargaRevolver(sr, r) {
    var n = zeros(sr, 1.0), i;
    somar(n, estalo(sr, [2600, 1500], 0.02, 0.08, r), 0.9, 0.0, sr);
    for (i = 0; i < 4; i++) somar(n, estalo(sr, [3200 + r() * 1800, 5200], 0.025, 0.07, r), 0.55, 0.16 + i * 0.07 + r() * 0.03, sr);
    for (i = 0; i < 4; i++) somar(n, estalo(sr, [2600 + r() * 1400, 4100], 0.03, 0.08, r), 0.6, 0.55 + i * 0.1 + r() * 0.04, sr);
    return normalizar(n, 0.8);
  }
  function fechaRevolver(sr, r) {
    var n = zeros(sr, 0.5), i; somar(n, estalo(sr, [2000, 1200], 0.03, 0.1, r), 1, 0, sr);
    for (i = 0; i < 6; i++) somar(n, estalo(sr, [3600], 0.004, 0.03, r), 0.45, 0.08 + i * 0.035, sr);
    somar(n, estalo(sr, [1500, 900], 0.04, 0.12, r), 0.9, 0.3, sr);
    return normalizar(n, 0.8);
  }
  function recargaEspingarda(sr, r) {
    var n = zeros(sr, 1.0), k;
    for (k = 0; k < 2; k++) { somar(n, estalo(sr, [1300, 2100], 0.035, 0.12, r), 0.9, 0.12 + k * 0.4, sr); somar(n, estalo(sr, [200], 0.04, 0.1, r), 0.6, 0.12 + k * 0.4, sr); }
    return normalizar(n, 0.8);
  }
  function bombeia(sr, r) {
    var n = zeros(sr, 0.7);
    somar(n, estalo(sr, [900, 1500, 2300], 0.06, 0.2, r), 1, 0, sr); somar(n, estalo(sr, [150], 0.06, 0.15, r), 0.8, 0.005, sr);
    somar(n, estalo(sr, [1100, 1900, 2700], 0.07, 0.22, r), 1, 0.24, sr); somar(n, estalo(sr, [130], 0.07, 0.15, r), 0.9, 0.245, sr);
    return normalizar(n, 0.9);
  }
  function ricochete(sr, r) {
    var n = zeros(sr, 0.55), i, t, fase = 0, f, v;
    for (i = 0; i < n.length; i++) {
      t = i / sr; f = 700 + 3600 * Math.exp(-t / 0.09); fase += PI2 * f / sr;
      v = Math.sin(fase) * Math.exp(-t / 0.12) * 0.7 + (r() * 2 - 1) * Math.exp(-t / 0.02) * 0.5;
      n[i] = v * (1 + 0.15 * Math.sin(PI2 * 38 * t));
    }
    somar(n, estalo(sr, [3100, 4700], 0.05, 0.2, r), 0.35, 0.0, sr);
    return normalizar(reverbe(n, sr, 0.6, 0.3, 0.15), 0.85);
  }
  function faca(sr, r) {
    var n = zeros(sr, 0.3), b = new Bq("bp", 1000, 1.2, sr), i, t, e;
    for (i = 0; i < n.length; i++) { t = i / sr; b.set("bp", 900 + 3200 * Math.min(1, t / 0.14), 1.2); e = Math.sin(Math.PI * Math.min(1, t / 0.2)); n[i] = b.p(r() * 2 - 1) * e * (t < 0.2 ? 1 : 0); }
    return normalizar(n, 0.8);
  }
  function soco(sr, r) {
    var n = zeros(sr, 0.25), i, t, fase = 0;
    for (i = 0; i < n.length; i++) { t = i / sr; fase += PI2 * (95 - 40 * Math.min(1, t / 0.1)) / sr; n[i] = Math.sin(fase) * Math.exp(-t / 0.05) + (r() * 2 - 1) * Math.exp(-t / 0.012) * 0.4; }
    return normalizar(filtrar(n, "lp", 1500, 0.7, sr), 0.85);
  }
  function impacto(sr, r, o) {
    var p = o.pitch || 1, n = zeros(sr, 0.3), i, t, fase = 0, cr = new Float32Array(n.length);
    for (i = 0; i < n.length; i++) { t = i / sr; fase += PI2 * (120 - 50 * Math.min(1, t / 0.08)) * p / sr; cr[i] = (r() * 2 - 1) * Math.exp(-t / 0.03); n[i] = Math.sin(fase) * Math.exp(-t / 0.06); }
    cr = filtrar(cr, "lp", 1800, 0.7, sr);
    for (i = 0; i < n.length; i++) n[i] = n[i] * 1.1 + cr[i] * 0.9;
    return normalizar(n, 0.85);
  }

  // ---------- vozes: fonte glotal (pulsos de Rosenberg, derivados) filtrada por formantes de vogais ----------
  var VOGAIS = { a: [730, 1090, 2440], o: [570, 840, 2410], u: [300, 870, 2240], e: [530, 1840, 2480], i: [270, 2290, 3010] };
  function vogalEm(pts, t) {
    var i, a, b, k;
    if (t <= pts[0][0]) return VOGAIS[pts[0][1]];
    for (i = 1; i < pts.length; i++) if (t <= pts[i][0]) { a = pts[i - 1]; b = pts[i]; k = (t - a[0]) / Math.max(1e-9, b[0] - a[0]); var va = VOGAIS[a[1]], vb = VOGAIS[b[1]]; return [va[0] + (vb[0] - va[0]) * k, va[1] + (vb[1] - va[1]) * k, va[2] + (vb[2] - va[2]) * k]; }
    return VOGAIS[pts[pts.length - 1][1]];
  }
  function voz(sr, r, e) {
    var len = Math.max(1, Math.round(sr * e.dur)), vv = new Float32Array(len), nn = new Float32Array(len), esc = e.formantes || 1, tom = e.tom || 1;
    var f1 = new Bq("bp", 600, 7, sr), f2 = new Bq("bp", 1000, 9, sr), f3 = new Bq("bp", 2400, 11, sr), ar = new Bq("bp", e.arFreq || 1400, 0.9, sr);
    var fase = 0, gAnt = 0, jit = 0, ganho = 1, i, t, vf, f0, g, s, am, env;
    for (i = 0; i < len; i++) {
      t = i / sr;
      if (i % 96 === 0) { vf = vogalEm(e.vogais, t); f1.set("bp", vf[0] * esc, e.q || 7); f2.set("bp", vf[1] * esc, 9); f3.set("bp", vf[2] * esc, 11); }
      jit += (r() - 0.5) * 0.02 * (e.jitter || 0) - jit * 0.02;
      f0 = curva(e.f0, t) * tom * (1 + jit);
      fase += f0 / sr;
      if (fase >= 1) { fase -= 1; ganho = 1 + (r() - 0.5) * (e.shimmer || 0); }
      g = fase < 0.6 ? 0.5 * (1 - Math.cos(Math.PI * fase / 0.6)) : Math.cos(Math.PI / 2 * (fase - 0.6) / 0.4);
      s = (g - gAnt) * ganho * 40; gAnt = g;
      am = e.trilo ? 1 - e.trilo.prof * (0.5 + 0.5 * Math.sin(PI2 * e.trilo.hz * t)) : 1;
      env = curva(e.amp, t);
      s *= am * env;
      vv[i] = f1.p(s) + 0.6 * f2.p(s) + 0.18 * f3.p(s);
      nn[i] = ar.p(r() * 2 - 1) * env * (e.trilo ? am : 1);
    }
    var rv = rms(vv), rn = rms(nn), out = new Float32Array(len), k = rn > 0 ? (e.ar || 0) * rv / rn : 0;
    for (i = 0; i < len; i++) out[i] = vv[i] + nn[i] * k;
    out = filtrar(out, "lp", e.lp || 2600, 0.7, sr);
    if (e.saturar) saturar(out, e.saturar);
    return normalizar(out, e.pico || 0.8);
  }
  function dorHomem(sr, r, o) {
    var tom = o.tom || 1;
    return voz(sr, r, { dur: 0.75, f0: [[0, 165], [0.12, 185], [0.75, 80]], vogais: [[0, "a"], [0.22, "a"], [0.75, "o"]], amp: [[0, 0], [0.04, 1], [0.3, 0.9], [0.75, 0]], jitter: 0.7, shimmer: 0.3, ar: 0.35, tom: tom, saturar: 1.4, pico: 0.9 });
  }
  function morteHomem(sr, r, o) {
    var tom = o.tom || 1, v = voz(sr, r, { dur: 1.4, f0: [[0, 140], [0.3, 120], [1.1, 55], [1.4, 48]], vogais: [[0, "a"], [0.4, "o"], [1.4, "u"]], amp: [[0, 0], [0.03, 1], [0.6, 0.8], [1.4, 0]], jitter: 1.1, shimmer: 0.5, ar: 0.5, tom: tom, saturar: 1.3, pico: 0.85 }), n = zeros(sr, 1.9), i, t, fase = 0, queda = new Float32Array(n.length);
    for (i = 0; i < queda.length; i++) { t = i / sr; fase += PI2 * (75 - 30 * Math.min(1, t / 0.15)) / sr; queda[i] = Math.sin(fase) * Math.exp(-t / 0.07) + (r() * 2 - 1) * Math.exp(-t / 0.04) * 0.5; }
    somar(n, v, 1, 0, sr); somar(n, filtrar(queda, "lp", 900, 0.7, sr), 0.9, 1.0, sr);
    return normalizar(n, 0.9);
  }
  function resmungo(sr, r, o) {
    var tom = o.tom || 1, ns = 4 + Math.floor(r() * 3), n = zeros(sr, 1.6), t0 = 0, k, V = ["o", "u", "a", "e", "o"];
    for (k = 0; k < ns; k++) {
      var d = 0.13 + r() * 0.1, f = (100 + r() * 28) * tom, vg = V[Math.floor(r() * V.length)];
      var s = voz(sr, r, { dur: d, f0: [[0, f * 1.05], [d, f * 0.9]], vogais: [[0, vg], [d, vg]], amp: [[0, 0], [0.02, 1], [d * 0.7, 0.8], [d, 0]], jitter: 0.5, shimmer: 0.25, ar: 0.3, saturar: 1.2, pico: 0.8 });
      var cons = filtrar(estaloRuido(sr, 0.03, r), "bp", 700 + r() * 900, 1.5, sr);
      somar(n, cons, 0.5 * rms(s) / Math.max(1e-6, rms(cons)) * 0.4, t0 - 0.01 > 0 ? t0 - 0.01 : 0, sr); somar(n, s, 1, t0, sr);
      t0 += d + 0.06 + r() * 0.1;
    }
    return normalizar(filtrar(n, "lp", 3200, 0.7, sr), 0.6);
  }
  function estaloRuido(sr, dur, r) { var n = zeros(sr, dur), i; for (i = 0; i < n.length; i++) n[i] = (r() * 2 - 1) * Math.exp(-(i / sr) / (dur / 3)); return n; }
  function dorJogador(sr, r) {
    var v = voz(sr, r, { dur: 0.32, f0: [[0, 190], [0.3, 120]], vogais: [[0, "a"], [0.32, "o"]], amp: [[0, 0], [0.015, 1], [0.15, 0.8], [0.32, 0]], jitter: 0.4, shimmer: 0.3, ar: 0.4, saturar: 1.3, pico: 0.8 });
    var n = zeros(sr, 0.4), i, t, fase = 0, pe = new Float32Array(n.length);
    for (i = 0; i < pe.length; i++) { t = i / sr; fase += PI2 * (90 - 40 * Math.min(1, t / 0.1)) / sr; pe[i] = Math.sin(fase) * Math.exp(-t / 0.05) + (r() * 2 - 1) * Math.exp(-t / 0.03) * 0.4; }
    somar(n, filtrar(pe, "lp", 700, 0.7, sr), 0.9, 0, sr); somar(n, v, 0.8, 0.02, sr);
    return normalizar(n, 0.9);
  }

  // ---------- animais ----------
  function rosnado(sr, r) {
    return voz(sr, r, { dur: 1.2, f0: [[0, 78], [0.3, 92], [0.9, 74], [1.2, 60]], vogais: [[0, "o"], [0.6, "a"], [1.2, "o"]], amp: [[0, 0], [0.12, 1], [0.9, 0.9], [1.2, 0]], formantes: 0.85, jitter: 1.3, shimmer: 0.55, ar: 0.35, arFreq: 700, lp: 2200, trilo: { hz: 24 + r() * 6, prof: 0.55 }, q: 4, saturar: 1.6, pico: 0.9 });
  }
  function latido(sr, r) {
    var n = zeros(sr, 0.95), k, d = 0.2;
    for (k = 0; k < 2; k++) {
      var b = voz(sr, r, { dur: d, f0: [[0, 520], [0.06, 430], [d, 300]], vogais: [[0, "a"], [d, "o"]], amp: [[0, 0], [0.008, 1], [0.08, 0.8], [d, 0]], jitter: 0.5, shimmer: 0.4, ar: 0.6, saturar: 1.5, pico: 0.9 });
      somar(n, b, 1, k * 0.3, sr);
    }
    somar(n, rosnado(sr, r).subarray(0, Math.round(sr * 0.3)), 0.5, 0.62, sr);
    return normalizar(n, 0.9);
  }
  function ganido(sr, r) {
    return voz(sr, r, { dur: 0.5, f0: [[0, 420], [0.1, 900], [0.5, 480]], vogais: [[0, "i"], [0.25, "e"], [0.5, "i"]], amp: [[0, 0], [0.01, 1], [0.3, 0.8], [0.5, 0]], jitter: 0.3, ar: 0.2, pico: 0.8 });
  }
  function piar(sr, r, f1, f2, dur, k) {
    var n = zeros(sr, dur), i, t, fase = 0, f, v, h;
    for (i = 0; i < n.length; i++) {
      t = i / sr; f = f1 + (f2 - f1) * Math.sin(Math.PI * Math.min(1, t / dur)) * 0.9 + 130 * Math.sin(PI2 * 38 * t); fase += PI2 * f / sr;
      v = 0; for (h = 1; h <= 3; h++) v += Math.sin(fase * h) / (h * h);
      n[i] = v * Math.sin(Math.PI * Math.min(1, t / dur)) * (k || 1);
    }
    return n;
  }
  function guincho(sr, r) {
    var n = zeros(sr, 0.55);
    somar(n, piar(sr, r, 3300, 5200, 0.09), 1, 0, sr); somar(n, piar(sr, r, 3600, 5600, 0.08), 0.85, 0.15, sr);
    somar(n, filtrar(estaloRuido(sr, 0.08, r), "hp", 3500, 0.7, sr), 0.25, 0.3, sr); somar(n, piar(sr, r, 3000, 4800, 0.07), 0.6, 0.38, sr);
    return normalizar(n, 0.75);
  }
  function guinchoMorte(sr, r) {
    var n = zeros(sr, 0.5), i, t, fase = 0, f;
    for (i = 0; i < n.length; i++) { t = i / sr; f = 5600 - 3800 * Math.min(1, t / 0.45) + 160 * Math.sin(PI2 * 30 * t); fase += PI2 * f / sr; n[i] = (Math.sin(fase) + 0.4 * Math.sin(fase * 2)) * Math.exp(-t / 0.25) * (t < 0.01 ? t / 0.01 : 1); }
    return normalizar(n, 0.75);
  }
  function ataqueRato(sr, r) {
    var n = zeros(sr, 0.35), i, t, e;
    for (i = 0; i < n.length; i++) { t = i / sr; e = Math.sin(Math.PI * Math.min(1, t / 0.3)) * (0.5 + 0.5 * Math.sin(PI2 * 34 * t)); n[i] = (r() * 2 - 1) * e; }
    n = filtrar(n, "hp", 3800, 0.8, sr); somar(n, piar(sr, r, 3400, 5000, 0.07), 0.8, 0.2, sr);
    return normalizar(n, 0.75);
  }

  // ---------- ambiente ----------
  function passo(sr, r, o) {
    var piso = o.piso || "rua", n = zeros(sr, piso === "ponte" ? 0.35 : 0.22), i, t, fase = 0, p = 0.9 + r() * 0.25, cru = new Float32Array(n.length);
    for (i = 0; i < n.length; i++) { t = i / sr; cru[i] = r() * 2 - 1; }
    if (piso === "grama") { cru = filtrar(cru, "lp", 1700, 0.7, sr); for (i = 0; i < n.length; i++) { t = i / sr; n[i] = cru[i] * Math.exp(-t / 0.05) * 0.9; } }
    else if (piso === "terra") { cru = filtrar(cru, "lp", 850, 0.7, sr); for (i = 0; i < n.length; i++) { t = i / sr; n[i] = cru[i] * Math.exp(-t / 0.06); } }
    else if (piso === "madeira") {
      cru = filtrar(cru, "bp", 650 * p, 2, sr);
      for (i = 0; i < n.length; i++) { t = i / sr; fase += PI2 * 170 * p / sr; n[i] = cru[i] * Math.exp(-t / 0.03) * 0.8 + Math.sin(fase) * Math.exp(-t / 0.05) * 0.6; }
    } else if (piso === "ponte") {
      for (i = 0; i < n.length; i++) { t = i / sr; fase += PI2 * 210 * p / sr; n[i] = Math.sin(fase) * Math.exp(-t / 0.09) * 0.8 + Math.sin(fase * 2.4) * Math.exp(-t / 0.04) * 0.3 + cru[i] * Math.exp(-t / 0.012) * 0.3; }
      n = filtrar(n, "lp", 2500, 0.7, sr);
    } else {
      // cascalho: vários grãos curtos em sequência
      for (i = 0; i < 9; i++) somar(n, filtrar(estaloRuido(sr, 0.02, r), "bp", 2000 + r() * 2500, 1.2, sr), 0.5 + r() * 0.5, i * 0.008 + r() * 0.01, sr);
      for (i = 0; i < n.length; i++) { t = i / sr; fase += PI2 * 80 * p / sr; n[i] += Math.sin(fase) * Math.exp(-t / 0.035) * 0.6; }
    }
    if (piso !== "madeira" && piso !== "ponte" && piso !== "rua") { for (i = 0; i < n.length; i++) { t = i / sr; fase += PI2 * 75 * p / sr; n[i] += Math.sin(fase) * Math.exp(-t / 0.04) * 0.5; } }
    return normalizar(n, 0.5);
  }
  function abrePorta(sr, r) {
    var n = zeros(sr, 0.9), b = new Bq("bp", 900, 8, sr), i, t, fase = 0, f, e, s;
    somar(n, estalo(sr, [1800, 900], 0.015, 0.07, r), 0.8, 0, sr);
    for (i = 0; i < n.length; i++) {
      t = i / sr; if (t < 0.1) continue; var u = t - 0.1; f = 150 + 100 * Math.sin(Math.PI * Math.min(1, u / 0.7)) + 12 * Math.sin(PI2 * 17 * u); fase += PI2 * f / sr;
      e = Math.sin(Math.PI * Math.min(1, u / 0.7)); s = (fase % PI2) / PI2 * 2 - 1; b.set("bp", 700 + 800 * e, 8);
      n[i] += b.p(s * e * (1 + 0.5 * (r() - 0.5)));
    }
    somar(n, estalo(sr, [1000], 0.03, 0.1, r), 0.5, 0.82, sr);
    return normalizar(n, 0.7);
  }
  function portaTrancada(sr, r) {
    var n = zeros(sr, 0.6), k; for (k = 0; k < 3; k++) { somar(n, estalo(sr, [1500, 2300, 3100], 0.025, 0.1, r), 0.8, k * 0.12 + r() * 0.02, sr); somar(n, estalo(sr, [220], 0.04, 0.1, r), 0.5, k * 0.12, sr); }
    return normalizar(n, 0.75);
  }
  function destranca(sr, r) {
    var n = zeros(sr, 0.9), k;
    somar(n, estalo(sr, [4200, 5600], 0.03, 0.1, r), 0.6, 0.0, sr);
    for (k = 0; k < 5; k++) somar(n, estalo(sr, [3500], 0.006, 0.03, r), 0.5, 0.18 + k * 0.05, sr);
    somar(n, estalo(sr, [900, 1400, 230], 0.05, 0.15, r), 1, 0.5, sr);
    return normalizar(n, 0.85);
  }
  function pegaChave(sr, r) {
    var n = zeros(sr, 0.9), k; for (k = 0; k < 6; k++) somar(n, estalo(sr, [2100 + r() * 500, 3300 + r() * 600, 4400], 0.12, 0.3, r), 0.5, k * 0.055 + r() * 0.02, sr);
    return normalizar(n, 0.7);
  }
  function pegaMunicao(sr, r) {
    var n = zeros(sr, 0.8), k; for (k = 0; k < 7; k++) somar(n, estalo(sr, [3000 + r() * 2200, 5200 + r() * 800], 0.03, 0.08, r), 0.45 + r() * 0.3, k * 0.05 + r() * 0.03, sr);
    somar(n, estalo(sr, [400], 0.03, 0.08, r), 0.6, 0.0, sr);
    return normalizar(n, 0.75);
  }
  function pegaKit(sr, r) {
    var n = zeros(sr, 0.6), i, t, b = filtrar(estaloRuido(sr, 0.5, r), "bp", 3000, 0.9, sr);
    for (i = 0; i < n.length && i < b.length; i++) { t = i / sr; n[i] = b[i] * (0.5 + 0.5 * Math.sin(PI2 * 45 * t)) * Math.sin(Math.PI * Math.min(1, t / 0.4)); }
    somar(n, estalo(sr, [700, 300], 0.04, 0.1, r), 0.7, 0.4, sr);
    return normalizar(n, 0.7);
  }
  function pegaArma(sr, r) {
    var n = zeros(sr, 0.7); somar(n, estalo(sr, [1200, 600, 180], 0.07, 0.2, r), 1, 0, sr); somar(n, estalo(sr, [3000, 4500], 0.05, 0.1, r), 0.6, 0.18, sr);
    return normalizar(n, 0.85);
  }
  function cura(sr, r) {
    var n = zeros(sr, 1.0), rasga = filtrar(estaloRuido(sr, 0.35, r), "hp", 2200, 0.8, sr), i, t, ar = new Float32Array(n.length);
    for (i = 0; i < rasga.length; i++) rasga[i] *= 0.6 + 0.4 * Math.sin(PI2 * 40 * (i / sr));
    somar(n, rasga, 1, 0, sr);
    for (i = 0; i < ar.length; i++) { t = i / sr; ar[i] = (r() * 2 - 1) * Math.sin(Math.PI * Math.min(1, Math.max(0, (t - 0.35) / 0.55))); }
    somar(n, filtrar(ar, "bp", 900, 0.9, sr), 0.9, 0, sr);
    return normalizar(n, 0.7);
  }
  function escada(sr, r, o) {
    var n = zeros(sr, 0.95), k, sobe = o.sobe !== false;
    for (k = 0; k < 4; k++) somar(n, passo(sr, r, { piso: "madeira" }), sobe ? 1 : 0.8, 0.05 + k * (sobe ? 0.2 : 0.17), sr);
    return normalizar(n, 0.7);
  }
  function batida(sr, r) {
    var n = zeros(sr, 0.2), i, t, fase = 0;
    for (i = 0; i < n.length; i++) { t = i / sr; fase += PI2 * 85 / sr; n[i] = Math.sin(fase) * Math.exp(-t / 0.05) + (r() * 2 - 1) * Math.exp(-t / 0.01) * 0.3; }
    return normalizar(filtrar(n, "lp", 600, 0.7, sr), 0.6);
  }
  function sino(sr, r) {
    var n = zeros(sr, 5), P = [[0.5, 1.0, 3.5], [1, 0.9, 2.6], [1.19, 0.6, 2.0], [1.56, 0.35, 1.5], [2, 0.5, 1.4], [2.5, 0.25, 1.0], [3, 0.2, 0.8]], f0 = 196, i, t, k, v;
    for (i = 0; i < n.length; i++) { t = i / sr; v = 0; for (k = 0; k < P.length; k++) v += P[k][1] * Math.sin(PI2 * f0 * P[k][0] * t) * Math.exp(-t / P[k][2]); n[i] = v * Math.min(1, t / 0.004) + (r() * 2 - 1) * Math.exp(-t / 0.01) * 0.3; }
    return normalizar(reverbe(n, sr, 1.5, 0.3, 0.5), 0.8);
  }
  function coracao(sr, r) {
    var n = zeros(sr, 0.6), k, T = [0, 0.24], A = [1, 0.7];
    for (k = 0; k < 2; k++) { var b = new Float32Array(Math.round(sr * 0.14)), i, t, fase = 0; for (i = 0; i < b.length; i++) { t = i / sr; fase += PI2 * (62 - 14 * t / 0.14) / sr; b[i] = Math.sin(fase) * Math.exp(-t / 0.045); } somar(n, b, A[k], T[k], sr); }
    return normalizar(filtrar(n, "lp", 260, 0.7, sr), 0.8);
  }
  function derrota(sr, r) {
    var n = zeros(sr, 2.2), k, b;
    somar(n, coracao(sr, r), 0.9, 0.0, sr); somar(n, coracao(sr, r), 0.6, 0.9, sr);
    b = new Float32Array(Math.round(sr * 0.35)); for (k = 0; k < b.length; k++) { var t = k / sr; b[k] = Math.sin(PI2 * 55 * t) * Math.exp(-t / 0.08) + (r() * 2 - 1) * Math.exp(-t / 0.05) * 0.4; }
    somar(n, filtrar(b, "lp", 500, 0.7, sr), 1, 1.7, sr);
    return normalizar(n, 0.8);
  }
  // Riacho: um laço de 4 s com borbulhas aleatórias; o fim se mistura ao começo para não haver emenda audível.
  function riacho(sr, r) {
    var len = Math.round(sr * 4), f = Math.round(sr * 0.3), raw = new Float32Array(len), i, k, b, n;
    for (i = 0; i < len; i++) raw[i] = r() * 2 - 1;
    n = filtrar(filtrar(raw, "lp", 1400, 0.7, sr), "hp", 250, 0.7, sr);
    for (i = 0; i < len; i++) n[i] *= 0.55;
    for (k = 0; k < 90; k++) {
      var t0 = r() * 3.9, f0 = 500 + r() * 900, d = 0.03 + r() * 0.05, a = 0.15 + r() * 0.35, fase = 0;
      b = new Float32Array(Math.round(sr * d));
      for (i = 0; i < b.length; i++) { var t = i / sr; fase += PI2 * (f0 * (1 + 2 * t / d)) / sr; b[i] = Math.sin(fase) * Math.sin(Math.PI * t / d); }
      somar(n, b, a, t0, sr);
    }
    for (i = 0; i < f; i++) { var m = i / f; n[i] = n[i] * m + n[len - f + i] * (1 - m); }
    return normalizar(n.slice(0, len - f), 0.7);
  }

  var FAB = {
    revolver: function (sr, r, o) { return tiro(sr, r, o); },
    espingarda: function (sr, r) { return espingarda(sr, r); },
    pistola: function (sr, r) { return tiro(sr, r, { pitch: 1.35, curto: true }); },
    seco: cliqueSeco, recarga: recargaRevolver, recarregou: fechaRevolver, recargaEsp: recargaEspingarda, bombeia: bombeia,
    ricochete: ricochete, faca: faca, soco: soco, impacto: impacto,
    dor: dorHomem, morte: morteHomem, resmungo: resmungo, dorJogador: dorJogador,
    rosnado: rosnado, latido: latido, ganido: ganido, guincho: guincho, guinchoMorte: guinchoMorte, ataqueRato: ataqueRato,
    passo: passo, abrePorta: abrePorta, portaTrancada: portaTrancada, destranca: destranca, pegaChave: pegaChave, pegaMunicao: pegaMunicao, pegaKit: pegaKit, pegaArma: pegaArma,
    cura: cura, escada: escada, batida: batida, sino: sino, coracao: coracao, derrota: derrota, riacho: riacho
  };
  var NOMES = Object.keys(FAB);
  // Gera um som: nome, taxa de amostragem, número da variação e opções (piso, pitch, tom). Sempre devolve amostras finitas entre -1 e 1.
  function gerar(nome, sr, variante, opcoes) {
    var f = FAB[nome]; if (!f) throw new Error("som desconhecido: " + nome);
    var o = opcoes || {}, r = rng(hash(nome + (o.piso || "")) + (variante || 0) * 7919), x = f(sr, r, o), i;
    for (i = 0; i < x.length; i++) if (!isFinite(x[i])) x[i] = 0;
    return x;
  }
  var api = { NOMES: NOMES, gerar: gerar, rng: rng, rms: rms, filtrar: filtrar };
  raiz.HeimdallVilarejoSom = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
