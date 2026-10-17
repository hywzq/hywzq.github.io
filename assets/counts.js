/* =========================================================
   Site-wide numbers, applied from one source of truth
   ---------------------------------------------------------
   Every count that appears in prose or in a metric tile is
   tagged in the HTML with data-fact="<key>". The values are
   counted from the content itself by tools/site_facts.py and
   written to assets/counts-data.js by tools/build_counts.py.

   The digits already hard-coded in the HTML are the fallback,
   so the page still reads correctly with JavaScript off.
   tools/check_site.py fails when that fallback has drifted
   from the content, and tools/build_counts.py is what rewrites
   both - so the two can never disagree.

   A fact with no value (or a key that nothing defines) is left
   alone rather than blanked: showing a stale number is better
   than showing nothing.
   ========================================================= */
(function () {
  var data = window.__SITE_COUNTS__;
  if (!data) return;

  var nodes = document.querySelectorAll('[data-fact]');
  for (var i = 0; i < nodes.length; i++) {
    var key = nodes[i].getAttribute('data-fact');
    if (!Object.prototype.hasOwnProperty.call(data, key)) continue;
    var value = data[key];
    if (value === null || value === undefined || value === '') continue;
    nodes[i].textContent = String(value);
  }
})();
