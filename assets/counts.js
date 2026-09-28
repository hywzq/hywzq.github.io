/* =========================================================
   Publication counts, derived from the list itself
   ---------------------------------------------------------
   The numbers in the hero sentence and the metric cards were
   maintained by hand, which is exactly the kind of thing that
   silently goes stale: a paper is added, the list is right,
   and the headline number is not.

   They are now counted from the publication groups on this
   page. The values already hard-coded in the HTML act as the
   fallback, so the page still reads correctly if this script
   or JS is missing. tools/check_site.py reports when that
   fallback has drifted.
   ========================================================= */
(function () {
  /* The four publication groups, in page order. "Papers by Year" is a
     <details> block with its own <ul>, and is deliberately not one of them. */
  var GROUPS = [
    'first-and-corresponding-author',
    'under-review-and-submitted',
    'climate-dynamics-earth-system-modelling-and-paleoclimate',
    'ecology'
  ];

  /* A paper counts as in progress when its status note says so. Matched on the
     note text rather than on a class, because the same note element is also
     used for "In Chinese" and "Highly Cited Paper", which are not statuses.
     Extend this pattern if a new in-progress value is ever introduced. */
  var IN_PROGRESS = /under review|submitted|in revising/i;

  /* The group heading and its list are not always adjacent - the first group
     has legend paragraphs in between - so walk forward to the next <ul>. */
  function listAfter(id) {
    var heading = document.getElementById(id);
    if (!heading) return null;
    var node = heading.nextElementSibling;
    while (node && node.tagName !== 'UL') node = node.nextElementSibling;
    return node;
  }

  function entries(ul) {
    var out = [];
    if (!ul) return out;
    for (var i = 0; i < ul.children.length; i++) {
      if (ul.children[i].tagName === 'LI') out.push(ul.children[i]);
    }
    return out;
  }

  var lists = [];
  var found = 0;
  for (var g = 0; g < GROUPS.length; g++) {
    var ul = listAfter(GROUPS[g]);
    lists.push(ul);
    if (ul) found++;
  }

  /* Only touch the page if all four groups are present. On any other page -
     or if the markup is restructured - writing a half-counted number would be
     worse than leaving the fallback alone. */
  if (found !== GROUPS.length) return;

  var firstAuthor = entries(lists[0]).length;
  var total = 0;
  var inProgress = 0;

  for (var l = 0; l < lists.length; l++) {
    var items = entries(lists[l]);
    total += items.length;
    for (var k = 0; k < items.length; k++) {
      var note = items[k].querySelector('.pub-note');
      if (note && IN_PROGRESS.test(note.textContent)) inProgress++;
    }
  }

  var values = {
    'first-author': firstAuthor,
    'total': total,
    'in-progress': inProgress
  };

  Object.keys(values).forEach(function (key) {
    var nodes = document.querySelectorAll('[data-pub-count="' + key + '"]');
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = String(values[key]);
    }
  });
})();
