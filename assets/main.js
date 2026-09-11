/* =========================================================
   Homepage behaviour
   - language toggle (en / zh), persisted
   - section scroll-spy for the sticky sidebar nav
   ========================================================= */
(function () {
  var body = document.body;

  /* ---------- language ---------- */
  var btn = document.getElementById('langBtn');

  function apply(lang) {
    body.classList.remove('lang-en', 'lang-zh');
    body.classList.add('lang-' + lang);
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    if (btn) btn.textContent = lang === 'zh' ? 'EN' : '中文';
    try { localStorage.setItem('homepage-lang', lang); } catch (e) {}
  }

  var saved = null;
  try { saved = localStorage.getItem('homepage-lang'); } catch (e) {}
  apply(saved === 'zh' ? 'zh' : 'en');

  if (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      apply(body.classList.contains('lang-en') ? 'zh' : 'en');
    });
  }

  /* ---------- scroll spy on the sidebar section nav ---------- */
  var nav = document.querySelector('.about-sidebar-nav');
  if (nav) {
    var links = Array.prototype.slice.call(nav.querySelectorAll('a[href^="#"]'));
    var targets = links
      .map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); })
      .filter(Boolean);

    var spy = function () {
      var pos = window.scrollY + 140;
      var current = null;
      targets.forEach(function (t) { if (t.offsetTop <= pos) current = t.id; });
      links.forEach(function (a) {
        var on = a.getAttribute('href') === '#' + current;
        a.style.color = on ? 'var(--teal)' : '';
        a.style.background = on ? 'rgba(15,118,110,.07)' : '';
      });
    };
    window.addEventListener('scroll', spy, { passive: true });
    window.addEventListener('resize', spy);
    spy();
  }

  /* ---------- research hub search filter ---------- */
  var search = document.getElementById('hubSearch');
  if (search) {
    var articles = Array.prototype.slice.call(
      document.querySelectorAll('#studies article')
    );
    search.addEventListener('input', function () {
      var q = search.value.trim().toLowerCase();
      articles.forEach(function (a) {
        a.hidden = q !== '' && a.textContent.toLowerCase().indexOf(q) === -1;
      });
    });
  }
})();
