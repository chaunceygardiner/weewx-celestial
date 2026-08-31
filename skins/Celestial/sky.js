/* Copyright 2026 by John A Kline.  See LICENSE for your rights.
   COPIED from weewx-skyfield skins/Skyfield/sky.js (v2.0) -- that repo
   is the source of truth; re-copy this file when upgrading, never fork.
   Here the .skytip rule lives at the end of celestial.css, and
   celestial.js hides an open chip on every fragment swap (a
   chip does not follow its mark, and this page's marks move).
   Tap tooltips for the Sky page's SVG panels.  Every mark already
   carries a native SVG <title> -- the browser shows it on hover, but
   touch has no hover, so a tap finds the mark and shows the same text
   in a floating chip (styled as .skytip in sky.css).  Mouse users keep
   the native tooltips; a click pins the chip too.  Self-contained: no
   libraries, nothing fetched. */
(function () {
  'use strict';

  /* How far (CSS px) a tap may miss a small mark and still count.
     Fingers are blunt; the dome's stars are 1-3px dots. */
  var RADIUS = 24;
  /* Marks bigger than this (either dimension) get no proximity grace:
     they are easy to hit directly, and a thin arc's bounding box would
     otherwise swallow taps on empty sky nearby. */
  var BIG = 80;

  var tip = null;
  function ensureTip() {
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'skytip';
      /* The text duplicates the <title> screen readers already announce. */
      tip.setAttribute('aria-hidden', 'true');
      document.body.appendChild(tip);
    }
    return tip;
  }
  function hideTip() { if (tip) { tip.style.display = 'none'; } }

  function childTitle(el) {
    for (var c = el.firstChild; c; c = c.nextSibling) {
      if (c.nodeName && c.nodeName.toLowerCase() === 'title') { return c; }
    }
    return null;
  }

  /* Distance from a point to a rect's edge; 0 inside. */
  function dist(x, y, r) {
    var dx = Math.max(r.left - x, 0, x - r.right);
    var dy = Math.max(r.top - y, 0, y - r.bottom);
    return Math.sqrt(dx * dx + dy * dy);
  }

  /* The mark the tap actually landed on: the innermost ancestor of the
     event target (up to the svg) owning a direct <title> child.  The
     browser's hit test honors the real geometry -- bars, strokes -- so
     no bounding-box guesswork is needed here. */
  function exactHit(target, svg) {
    for (var el = target; el; el = el.parentNode) {
      var t = childTitle(el);
      if (t) { return { rect: el.getBoundingClientRect(), text: t.textContent }; }
      if (el === svg) { break; }
    }
    return null;
  }

  /* The nearest small titled mark within RADIUS of the tap -- the
     finger-precision grace for tiny dots. */
  function nearHit(svg, x, y) {
    var titles = svg.getElementsByTagName('title');
    var best = null;
    var bestD = RADIUS + 1;
    var bestA = Infinity;
    for (var i = 0; i < titles.length; i++) {
      var el = titles[i].parentNode;
      if (!el || !el.getBoundingClientRect) { continue; }
      var r = el.getBoundingClientRect();
      if (r.right - r.left > BIG || r.bottom - r.top > BIG) { continue; }
      var d = dist(x, y, r);
      if (d > RADIUS) { continue; }
      var a = (r.right - r.left) * (r.bottom - r.top);
      /* Nearest wins; at equal distance (overlapping marks) the smaller
         mark does -- a star dot inside a body group's box, say. */
      if (d < bestD || (d === bestD && a < bestA)) {
        best = { rect: r, text: titles[i].textContent };
        bestD = d;
        bestA = a;
      }
    }
    return best;
  }

  function showTip(hit, x) {
    var t = ensureTip();
    t.textContent = hit.text;
    t.style.display = 'block';
    var r = hit.rect;
    /* Anchor above the mark, horizontally at the tap (clamped into the
       mark, so a wide bar's chip pops where the finger is), flipping
       below when there is no room, and staying inside the viewport. */
    var ax = Math.min(Math.max(x, r.left), r.right);
    var left = ax - t.offsetWidth / 2;
    left = Math.max(4, Math.min(left, window.innerWidth - t.offsetWidth - 4));
    var top = r.top - t.offsetHeight - 8;
    if (top < 4) { top = r.bottom + 8; }
    t.style.left = left + 'px';
    t.style.top = top + 'px';
  }

  document.addEventListener('click', function (e) {
    var el = e.target;
    var svg = el && el.closest ? el.closest('svg') : null;
    if (!svg) { hideTip(); return; }
    var hit = exactHit(el, svg) || nearHit(svg, e.clientX, e.clientY);
    if (hit) { showTip(hit, e.clientX); } else { hideTip(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { hideTip(); }
  });
  window.addEventListener('scroll', hideTip, { passive: true });
  window.addEventListener('resize', hideTip);
})();
