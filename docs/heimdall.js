/* Gerado por gerar_docs.py. Copiar comando e olho do início. */
(function () {
  var live = document.getElementById('aviso-copia');
  document.querySelectorAll('button.copy').forEach(function (b) {
    b.addEventListener('click', function () {
      var alvo = document.getElementById(b.getAttribute('data-alvo'));
      if (!alvo) return;
      var txt = alvo.textContent;
      var ok = function () { if (live) { live.textContent = ''; setTimeout(function () { live.textContent = 'Comando copiado.'; }, 50); } };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt).then(ok, function () { if (live) live.textContent = 'Não foi possível copiar. Selecione o texto do comando.'; });
      else { var r = document.createRange(); r.selectNodeContents(alvo); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); try { document.execCommand('copy'); ok(); } catch (e) {} }
    });
  });
  var svg = document.getElementById('bridge'), iris = document.getElementById('iris');
  if (!svg || !iris || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  iris.style.transition = 'transform .12s ease-out';
  window.addEventListener('pointermove', function (e) {
    var r = svg.getBoundingClientRect(), k = r.width / 800, cx = r.left + 400 * k, cy = r.top + 380 * k;
    var dx = e.clientX - cx, dy = e.clientY - cy, d = Math.sqrt(dx * dx + dy * dy) || 1, f = Math.min(1, d / (r.width * .5));
    iris.setAttribute('transform', 'translate(' + (dx / d * 52 * f).toFixed(1) + ' ' + (Math.min(0, dy / d) * 20 * f + (dy > 0 ? dy / d * 8 * f : 0)).toFixed(1) + ')');
  }, { passive: true });
})();
