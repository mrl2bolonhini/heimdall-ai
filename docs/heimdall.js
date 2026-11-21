/* Gerado por gerar_docs.py (docs_tema.py). Tema, copiar comando e olho do início. */
(function () {
  var live = document.getElementById('aviso');
  var avisar = function (t) { if (live) { live.textContent = ''; setTimeout(function () { live.textContent = t; }, 50); } };
  var raiz = document.documentElement, btn = document.getElementById('tema');
  var escuro = function () { var t = raiz.getAttribute('data-theme'); return t ? t === 'dark' : !!(window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches); };
  var rotulo = function () { if (btn) { btn.textContent = escuro() ? 'Tema claro' : 'Tema escuro'; } };
  rotulo();
  if (btn) btn.addEventListener('click', function () {
    var novo = escuro() ? 'light' : 'dark';
    raiz.setAttribute('data-theme', novo);
    try { localStorage.setItem('tema', novo); } catch (e) {}
    rotulo(); avisar(novo === 'dark' ? 'Tema escuro ativado.' : 'Tema claro ativado.');
  });
  document.querySelectorAll('button.copy').forEach(function (b) {
    b.addEventListener('click', function () {
      var alvo = document.getElementById(b.getAttribute('data-alvo'));
      if (!alvo) return;
      var ok = function () { avisar('Comando copiado.'); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(alvo.textContent).then(ok, function () { avisar('Não foi possível copiar. Selecione o texto do comando.'); });
      else { var r = document.createRange(); r.selectNodeContents(alvo); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); try { document.execCommand('copy'); ok(); } catch (e) {} }
    });
  });
  var cs = document.getElementById('conta-site');
  if (cs && window.fetch) {
    var base = cs.getAttribute('data-url');
    var el = function (tag, texto, filho) { var x = document.createElement(tag); if (texto) x.textContent = texto; if (filho) x.appendChild(filho); return x; };
    fetch(base + 'quem.json', { credentials: 'include', redirect: 'manual', headers: { 'Accept': 'application/json' } }).then(function (r) {
      if (r.type === 'opaqueredirect' || !r.ok) return null;
      return r.json();
    }).then(function (d) {
      if (!d || !d.logado) return;
      var det = document.createElement('details'), sum = el('summary', 'Conta: ' + d.nome), cx = document.createElement('div'), ul = document.createElement('ul');
      cx.className = 'caixa';
      cx.appendChild(el('p', 'Conectado como ' + d.nome + (d.email && d.email !== d.nome ? ' (' + d.email + ')' : '') + '.'));
      cx.appendChild(el('p', 'Serviços do Heimdall'));
      (d.servicos || []).forEach(function (s) {
        if (!/^https:\/\//.test(s.url || '')) return;
        var a = el('a', s.nome); a.href = s.url; ul.appendChild(el('li', '', a));
      });
      ul.setAttribute('aria-label', 'Serviços do Heimdall');
      cx.appendChild(ul);
      var sai = el('a', 'Sair do Heimdall'); sai.href = base + 'cdn-cgi/access/logout';
      cx.appendChild(el('p', '', sai));
      det.appendChild(sum); det.appendChild(cx);
      det.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && det.open) { det.open = false; sum.focus(); } });
      cs.textContent = ''; cs.appendChild(det);
      avisar('Você está conectado como ' + d.nome + '. O menu Conta lista os seus serviços.');
    }).catch(function () {});
  }
  var svg = document.getElementById('bridge'), iris = document.getElementById('iris');
  if (!svg || !iris || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  iris.style.transition = 'transform .12s ease-out';
  window.addEventListener('pointermove', function (e) {
    var r = svg.getBoundingClientRect(), k = r.width / 100, cx = r.left + 50 * k, cy = r.top + (46 + 4) * k;
    var dx = e.clientX - cx, dy = e.clientY - cy, d = Math.sqrt(dx * dx + dy * dy) || 1, f = Math.min(1, d / (r.width * .5));
    var x = dx / d * 6.5 * f, y = (dy < 0 ? dy / d * 2.4 : dy / d * 1) * f;
    iris.setAttribute('transform', 'translate(' + x.toFixed(2) + ' ' + y.toFixed(2) + ')');
  }, { passive: true });
})();
