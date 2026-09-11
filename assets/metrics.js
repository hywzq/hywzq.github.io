/* =========================================================
   Live Google Scholar metrics
   ---------------------------------------------------------
   Reads window.__SCHOLAR_METRICS__ (written by
   tools/refresh_metrics.py into assets/metrics-data.js) and
   writes the values into every element carrying data-metric.

   The numbers already hard-coded in the HTML act as the
   fallback, so the page still reads correctly if this script
   or the data file is missing.
   ========================================================= */
(function () {
  var data = window.__SCHOLAR_METRICS__;
  if (!data || !data.scholar) return;

  var s = data.scholar;

  /* Scholar labels the second column "Since <year>"; build both languages from it. */
  var yearMatch = /(\d{4})/.exec(s.sinceLabel || '');
  var sinceYear = yearMatch ? yearMatch[1] : null;

  var values = {
    citations: s.citations,
    citationsSince: s.citationsSince,
    hIndex: s.hIndex,
    hIndexSince: s.hIndexSince,
    i10Index: s.i10Index,
    i10IndexSince: s.i10IndexSince,
    sinceLabelEn: s.sinceLabel || (sinceYear ? 'Since ' + sinceYear : null),
    sinceLabelZh: sinceYear ? sinceYear + ' 年以来' : null,
    works: data.works
  };

  function setAll(selector, text) {
    var nodes = document.querySelectorAll(selector);
    for (var i = 0; i < nodes.length; i++) nodes[i].textContent = text;
  }

  function fmt(value) {
    if (typeof value === 'number') {
      return value.toLocaleString('en-US');
    }
    return value == null ? '' : String(value);
  }

  Object.keys(values).forEach(function (key) {
    var value = values[key];
    if (value === null || value === undefined) return;
    setAll('[data-metric="' + key + '"]', fmt(value));
  });

  /* ---------- "last updated" in relative time ---------- */
  var when = data.updated ? new Date(data.updated) : null;
  var valid = when && !isNaN(when.getTime());

  function relative(lang) {
    if (!valid) return data.updatedDisplay || '';
    var mins = Math.round((Date.now() - when.getTime()) / 60000);
    if (mins < 2) return lang === 'zh' ? '刚刚' : 'just now';
    if (mins < 60) return lang === 'zh' ? mins + ' 分钟前' : mins + ' minutes ago';
    var hrs = Math.round(mins / 60);
    if (hrs < 24) return lang === 'zh' ? hrs + ' 小时前' : (hrs === 1 ? '1 hour ago' : hrs + ' hours ago');
    var days = Math.round(hrs / 24);
    if (days < 31) return lang === 'zh' ? days + ' 天前' : (days === 1 ? 'yesterday' : days + ' days ago');
    return data.updatedDisplay || '';
  }

  setAll('[data-updated="en"]', ' ' + relative('en'));
  setAll('[data-updated="zh"]', relative('zh'));

  /* absolute date as a tooltip, and mark the block as live */
  var blocks = document.querySelectorAll('.scholar-meta');
  for (var i = 0; i < blocks.length; i++) {
    blocks[i].setAttribute('data-synced', 'true');
    blocks[i].setAttribute('title', 'Google Scholar · ' + (data.updatedDisplay || ''));
  }

  /* If the refresh job has stopped running, say so instead of quietly showing
     numbers that may be months out of date. */
  var STALE_DAYS = 7;
  if (valid && (Date.now() - when.getTime()) / 86400000 > STALE_DAYS) {
    for (var j = 0; j < blocks.length; j++) {
      blocks[j].setAttribute('data-stale', 'true');
      blocks[j].setAttribute(
        'title',
        (document.body.classList.contains('lang-zh') ? '数据可能已过期 · 上次同步 ' : 'Data may be stale · last synced ') +
          (data.updatedDisplay || '')
      );
    }
  }
})();
