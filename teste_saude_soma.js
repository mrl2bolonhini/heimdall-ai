// Testa o fluxo 15-saude (nó "Guardar dados"): o total do dia de métricas somadas soma as horas já recebidas, em vez de ser trocado pelo do último envio.
// Uso: node teste_saude_soma.js
const assert = require('assert');
const d = require('./n8n_flows_avancados/15-saude.json');
const code = d.nodes.find(n => n.name === 'Guardar dados').parameters.jsCode.replace(/__SAUDE_TOKEN__/g, 'tk');
const sd = {};
function envia(pts, nome = 'step_count', un = 'count') {
  const it = { json: { headers: { 'x-heimdall-saude': 'tk' }, body: { data: { metrics: [{ name: nome, units: un, data: pts }] } } } };
  return new Function('$getWorkflowStaticData', '$input', '$', code)(() => sd, { first: () => it }, () => ({}))[0].json;
}
const total = (r, m) => r.registros.find(x => x.metrica === m).valor;
const D = '2026-11-14';
envia([{ date: D + ' 08:00:00 -0300', qty: 500 }]);
assert.strictEqual(total(envia([{ date: D + ' 09:00:00 -0300', qty: 700 }]), 'passos'), 1200, 'horas diferentes somam');
assert.strictEqual(total(envia([{ date: D + ' 09:00:00 -0300', qty: 700 }, { date: D + ' 10:00:00 -0300', qty: 300 }]), 'passos'), 1500, 'reenviar uma hora não duplica');
assert.strictEqual(total(envia([{ date: D + ' 00:00:00 -0300', qty: 8000 }]), 'passos'), 8000, 'exportação diária completa prevalece sobre horas parciais');
assert.strictEqual(total(envia([{ date: D + ' 14:00:00 -0300', qty: 200 }]), 'passos'), 8000, 'um envio parcial depois não derruba o total');
assert.strictEqual(total(envia([{ date: D + ' 07:00:00 -0300', qty: 120 }], 'basal_energy_burned', 'kJ'), 'x:basal_energy_burned'), 120, 'energia em repouso soma e segue em kJ até o banco converter');
console.log('ok   fluxo de saúde: total do dia soma as horas recebidas');
