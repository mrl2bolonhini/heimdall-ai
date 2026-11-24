// Testes do motor de sons do Vilarejo Sitiado: todos os sons existem, são finitos, altos e estáveis, e têm o timbre esperado (sem navegador).
const assert = require("assert"), path = require("path");
const S = require(path.join(__dirname, "..", "..", "games", "vilarejo_som.js"));
let ok = 0; const t = (n, f) => { try { f(); ok++; console.log("ok   " + n); } catch (e) { console.log("FALHOU " + n + "\n     " + e.message); process.exitCode = 1; } };
const SR = 22050;
const pico = (x) => x.reduce((m, v) => Math.max(m, Math.abs(v)), 0);
const zcr = (x) => { let n = 0; for (let i = 1; i < x.length; i++) if ((x[i - 1] < 0) !== (x[i] < 0)) n++; return n / (x.length / SR) / 2; };   // cruzamentos de zero por segundo, ~ frequência dominante em Hz
const trecho = (x, a, b) => x.slice(Math.round(a * SR), Math.round(b * SR));

t("todos os sons existem e são amostras finitas, com pico alto mas sem estourar", () => {
  assert(S.NOMES.length >= 35, "poucos sons: " + S.NOMES.length);
  S.NOMES.forEach(n => { const x = S.gerar(n, SR, 0, { piso: "rua" }); assert(x.length > 0 && x.length < SR * 8, n); for (let i = 0; i < x.length; i++) assert(Number.isFinite(x[i]), n + " tem valor inválido"); const p = pico(x); assert(p >= 0.45 && p <= 1.0, n + " pico " + p); });
});
t("a mesma variação sempre dá o mesmo som e variações diferentes diferem", () => {
  const a = S.gerar("resmungo", SR, 1, {}), b = S.gerar("resmungo", SR, 1, {}), c = S.gerar("resmungo", SR, 2, {});
  assert.equal(a.length, b.length); assert(a.every((v, i) => v === b[i])); assert(c.length !== a.length || c.some((v, i) => v !== a[i]));
  assert(S.gerar("passo", SR, 0, { piso: "madeira" }).some((v, i) => v !== S.gerar("passo", SR, 0, { piso: "grama" })[i]), "o piso muda o som");
});
t("tiros são fortes e começam com um estalo imediato; espingarda é mais longa e mais grave que o revólver", () => {
  const rev = S.gerar("revolver", SR, 0, {}), esp = S.gerar("espingarda", SR, 0, {}), pis = S.gerar("pistola", SR, 0, {});
  [rev, esp, pis].forEach(x => assert(pico(trecho(x, 0, 0.012)) > 0.5, "sem estalo inicial"));
  assert(esp.length > rev.length && rev.length > pis.length * 0.9);
  assert(S.rms(trecho(rev, 0, 0.3)) > 0.12, "revólver fraco: " + S.rms(trecho(rev, 0, 0.3))); assert(S.rms(trecho(esp, 0, 0.3)) > 0.12);
  assert(S.rms(trecho(esp, 0.05, 0.4)) > S.rms(trecho(rev, 0.05, 0.4)) * 0.9, "a espingarda dura mais");
  assert(pico(trecho(rev, 1.2, rev.length / SR)) < 0.25, "o eco some no fim");
});
t("timbres: rosnado e resmungo são graves, guincho de rato é agudo, latido fica no meio", () => {
  const g = zcr(S.gerar("rosnado", SR, 0, {})), r = zcr(S.gerar("resmungo", SR, 0, {})), rato = zcr(S.gerar("guincho", SR, 0, {})), l = zcr(S.gerar("latido", SR, 0, {}));
  assert(g < 1800, "rosnado " + g); assert(r < 1800, "resmungo " + r); assert(rato > 2400, "guincho " + rato); assert(l > 200 && l < rato, "latido " + l);
});
t("gemido de dor e de morte têm duração de voz e a morte termina com o corpo caindo", () => {
  const d = S.gerar("dor", SR, 0, {}), m = S.gerar("morte", SR, 0, {});
  assert(d.length / SR > 0.5 && d.length / SR < 1.1); assert(m.length / SR > 1.4);
  assert(pico(trecho(m, 1.0, 1.2)) > 0.3, "falta o som do corpo caindo");
  assert(S.gerar("morte", SR, 0, { tom: 0.8 }).length === m.length, "o tom mais grave não muda a duração");
});
t("o riacho é um laço sem emenda: o fim e o começo têm níveis parecidos", () => {
  const x = S.gerar("riacho", SR, 0, {}); const a = S.rms(x.slice(0, 200)), b = S.rms(x.slice(x.length - 200)); assert(Math.abs(Math.log((a + 1e-6) / (b + 1e-6))) < 1.2, a + " x " + b); assert(Math.abs(x[0] - x[x.length - 1]) < 0.5);
});
t("som desconhecido avisa", () => { assert.throws(() => S.gerar("nao-existe", SR, 0, {}), /desconhecido/); });
console.log(`\n${ok} testes`);
