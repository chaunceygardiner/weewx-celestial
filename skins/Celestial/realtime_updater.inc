## Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
## See LICENSE.txt for your rights
## NOTE: Cheetah owns '#' and '$' in this file: no hex color literals (all
## colors come from classes in celestial.css, the SVG marks through the
## fill-*/stroke-* classes) and no javascript template literals.  Guard
## every loop-data key: a missing field must skip its own cell, never
## abort the whole update.  Non-ASCII glyphs in javascript strings use
## \u escapes so the generator's html_entities encoding cannot touch them.
#errorCatcher Echo
#encoding UTF-8
#import os
## Auto-detect the station's IANA timezone at report-generation time (the
## report is generated on the station machine): /etc/localtime is a symlink
## into the zoneinfo tree on Debian-family systems; /etc/timezone is the
## fallback.  Empty when neither yields a valid zone (the javascript then
## falls back to the viewer's browser timezone).
#set $auto_tz = ''
#try
#set $auto_tz = os.readlink('/etc/localtime').split('zoneinfo/')[-1]
#except
#pass
#end try
#if not $auto_tz
#try
#set $auto_tz = open('/etc/timezone').read().strip()
#except
#pass
#end try
#end if
#if $auto_tz and not os.path.exists('/usr/share/zoneinfo/' + $auto_tz)
#set $auto_tz = ''
#end if
<script>
  #if $Extras.has_key('page_update_pwd')
    page_update_pwd = '$Extras.page_update_pwd';
  #else
    page_update_pwd = 'foo';
  #end if
  #if $Extras.has_key('refresh_rate')
    refresh_rate = $Extras.refresh_rate;
  #else
    refresh_rate = 2;
  #end if
  #if $Extras.has_key('expiration_time')
    expiration_time = $Extras.expiration_time;
  #else
    expiration_time = 24;
  #end if
  ## Timezone for displayed times: the station's zone, auto-detected above.
  ## The time_zone Extras option overrides ('browser' forces the viewer's
  ## browser-local zone); empty falls back to browser-local too.
  #if $Extras.has_key('time_zone')
    time_zone = '$Extras.time_zone';
  #else
    time_zone = '$auto_tz';
  #end if
  if (time_zone === 'browser') {
    time_zone = '';
  }
  // An unknown zone name must not break every render: probe once and fall
  // back to the browser's local zone.
  try {
    new Date().toLocaleString("en-US", time_zone === '' ? {} : {timeZone: time_zone});
  } catch (e) {
    console.log('bad time_zone "' + time_zone + '", using browser-local');
    time_zone = '';
  }
  ## Station latitude decides the moon disc's lit side (hemisphere flip).
  STATION_LAT = $station.stn_info.latitude_f;
  ## Distances arrive as raw AU (weewx-loopdata almanac fields); convert to
  ## the report's distance units here.  windrun stands in for group_distance
  ## (this extension registers no observation types).
  #set $dist_label = str($unit.label.windrun)
  #if $unit.unit_type.windrun == 'km'
  #set $per_au = 1.4959787e8
  #else
  #set $per_au = 9.2955807e7
  #end if
  PER_AU = $per_au;
  DIST_LABEL = '$dist_label';
  function addLoadEvent(func) {
    var oldonload = window.onload;
    if (typeof window.onload != 'function') {
      window.onload = func;
    } else {
      window.onload = function() {
        if (oldonload) {
          oldonload();
        }
        func();
      }
    }
  }
  function getUrlParam(paramName) {
      var name, regexS, regex, results;
      name = paramName.replace(/(\[|\])/g, '\\$1');
      regexS = '[\\?&]' + name + '=([^&#]*)';
      regex = new RegExp(regexS);
      results = regex.exec(window.location.href);
      if (results === null) {
          return '';
      } else {
          return results[1];
      }
  }
  var pageTimedOut = false;
  function expirePage() {
    pageTimedOut = true;
  }
  function setUpExpiredClickListener() {
    var liveLabel = document.getElementById("live-label");
    if (liveLabel.innerHTML != "CLICK-ME") {
      liveLabel.innerHTML = "CLICK-ME";
      // set an onclick event on live-label to restart everything
      liveLabel.addEventListener("click", clickListener);
    }
  }
  function clickListener() {
    // disable the onClick event again
    var liveLabel = document.getElementById("live-label");
    liveLabel.removeEventListener('click', clickListener);
    liveLabel.innerHTML = "";
    // restart everything
    pageTimedOut = false;
    // restart the page timeout
    setPageExpirationTimer();
  }
  function setPageExpirationTimer() {
    if (getUrlParam('pageUpdate') !== page_update_pwd) {
      // expire in N hours
      setTimeout(expirePage, 1000 * 60 * 60 * expiration_time);
    }
  }
  setPageExpirationTimer();
  setInterval(updateCurrent, refresh_rate * 1000);
  setInterval(localTick, 1000);
  addLoadEvent(updateCurrent);

  // ---- formatting helpers -------------------------------------------------
  function tzOptions(opts) {
    if (time_zone !== '') {
      opts.timeZone = time_zone;
    }
    return opts;
  }
  function fmtHMS(ts) {
    return new Date(ts * 1000).toLocaleString("en-US",
      tzOptions({hour: '2-digit', minute: '2-digit', second: '2-digit'}));
  }
  function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function setHtml(id, html) {
    var el = document.getElementById(id);
    if (el && html !== undefined && html !== null) {
      el.innerHTML = html;
    }
  }
  function num(r, key) {
    // The guarded read: a missing or non-numeric field skips its own cell.
    return (typeof r[key] === 'number') ? r[key] : null;
  }

  // ---- the Geocentric -----------------------------------------------------
  // Bodies in roster order; the second element is the dial label.  Proxima
  // Centauri is served only by the weewx-skyfield almanac (with stars on);
  // its row and dot simply stay empty on any other almanac.
  var GEO_BODIES = [
    ['moon', 'Moon'], ['sun', 'Sun'],
    ['mercury', 'Mercury'], ['venus', 'Venus'], ['mars', 'Mars'],
    ['jupiter', 'Jupiter'], ['saturn', 'Saturn'], ['uranus', 'Uranus'],
    ['neptune', 'Neptune'], ['pluto', 'Pluto'],
    ['proxima_centauri', 'Proxima']
  ];
  var AU_PER_LY = 63241.077;          // au per light year, for Proxima's label
  // Dial geometry: azimuth is the compass bearing (plan view, east right);
  // radius is log10 of the distance in au, one ring per decade from
  // 0.01 au (inside the moon's orbit) to 100,000 au (Proxima at the rim).
  var CX = 330, CY = 330, R_IN = 56, R_OUT = 292;
  var LOG_MIN = -2.6, LOG_MAX = 5.45;
  var TRAIL_N = 24, TRAIL_SEC = 3600;  // the last hour, in 150 s segments
  var EXTRAP_MAX = 120;                // stop extrapolating stale data (s)
  function rOfAu(au) {
    var lg = Math.log(au) / Math.LN10;
    return R_IN + (lg - LOG_MIN) / (LOG_MAX - LOG_MIN) * (R_OUT - R_IN);
  }
  function dialXY(az, r) {
    var a = az * Math.PI / 180;
    return [CX + r * Math.sin(a), CY - r * Math.cos(a)];
  }
  var svgNS = 'http://www.w3.org/2000/svg';
  function svgEl(name, attrs, parent, text) {
    var e = document.createElementNS(svgNS, name);
    for (var k in attrs) {
      e.setAttribute(k, attrs[k]);
    }
    if (text) {
      e.textContent = text;
    }
    parent.appendChild(e);
    return e;
  }
  var dialMarks = null;   // per-body dial elements, built on first render
  function buildDial() {
    var dial = document.getElementById('dial');
    if (!dial) {
      return null;
    }
    // Distance rings, one per decade, labeled down the SSE radial (the
    // evening sky crowds the west and the label radial must not sit in
    // it; nothing guarantees a clear lane, but SSE collides least).
    var ringLabels = ['0.01 au', '0.1', '1 au', '10', '100',
                      '10\u00B3 au', '10\u2074', '10\u2075'];
    // fill='none' is structural, not color, so it rides as an attribute:
    // a stale cached stylesheet must never turn the rings into solid
    // discs that bury the dial.
    for (var lg = -2; lg <= 5; lg++) {
      var rr = R_IN + (lg - LOG_MIN) / (LOG_MAX - LOG_MIN) * (R_OUT - R_IN);
      svgEl('circle', {cx: CX, cy: CY, r: rr, 'class': 'geo-ring', fill: 'none',
                       'stroke-opacity': lg <= 1 ? 0.9 : 0.55}, dial);
      var rp = dialXY(157.5, rr);
      svgEl('text', {x: rp[0], y: rp[1] - 3, 'class': 'gridlab',
                     'text-anchor': 'middle'}, dial, ringLabels[lg + 2]);
    }
    svgEl('circle', {cx: CX, cy: CY, r: 296, 'class': 'geo-rim', fill: 'none'}, dial);
    for (var d = 0; d < 360; d += 45) {
      var p1 = dialXY(d, 290), p2 = dialXY(d, 296);
      svgEl('line', {x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1],
                     'class': d % 90 === 0 ? 'geo-tick geo-tick-major' : 'geo-tick'}, dial);
    }
    var cardinals = [[0, 'N'], [90, 'E'], [180, 'S'], [270, 'W']];
    for (var c = 0; c < cardinals.length; c++) {
      var pc = dialXY(cardinals[c][0], 310);
      svgEl('text', {x: pc[0], y: pc[1] + 4.5, 'class': 'cardinal',
                     'text-anchor': 'middle'}, dial, cardinals[c][1]);
    }
    svgEl('circle', {cx: CX, cy: CY, r: 9, 'class': 'fill-earth geo-earth'}, dial);
    svgEl('text', {x: CX, y: CY + 24, 'class': 'earthlab'}, dial, 'earth');
    var trailsG = svgEl('g', {}, dial);
    var marks = {};
    GEO_BODIES.forEach(function(pair) {
      var key = pair[0];
      var segs = [];
      for (var i = 0; i < TRAIL_N; i++) {
        segs.push(svgEl('line', {'class': 'trail stroke-' + key,
                                 display: 'none'}, trailsG));
      }
      var g = svgEl('g', {display: 'none'}, dial);
      var m = {label: pair[1], g: g, segs: segs,
               glow: null, dot: null, lit: null, rim: null};
      if (key === 'sun') {
        m.glow = svgEl('circle', {r: 13, 'class': 'sunglow fill-sun'}, g);
        m.dot = svgEl('circle', {r: 8, 'class': 'geodot fill-sun'}, g);
      } else if (key === 'moon') {
        // True-phase disc: dark disc, lit limb/terminator path, silver rim
        // (the rim keeps a new moon visible against the card).
        m.dot = svgEl('circle', {r: 8, 'class': 'moon-dark'}, g);
        m.lit = svgEl('path', {'class': 'moon-lit'}, g);
        m.rim = svgEl('circle', {r: 8, 'class': 'moon-rim', fill: 'none'}, g);
      } else {
        m.dot = svgEl('circle', {r: 6.5, 'class': 'geodot fill-' + key}, g);
      }
      m.lab = svgEl('text', {'class': 'bodylab'}, dial, pair[1]);
      marks[key] = m;
    });
    return marks;
  }
  // The moon disc's limb/terminator geometry (same construction as the
  // weewx-skyfield Sky page): frac is the illuminated fraction, and the
  // lit side faces the sun -- toward the east while waxing as seen from
  // the northern hemisphere, mirrored in the southern.
  function moonPath(cx, cy, R, frac, litLeft) {
    var rx = Math.abs(2 * frac - 1) * R;
    var limbSweep = litLeft ? 0 : 1;
    var termSweep = (frac >= 0.5) ? (litLeft ? 0 : 1) : (litLeft ? 1 : 0);
    return 'M ' + cx + ',' + (cy - R) +
           ' A ' + R + ',' + R + ' 0 0 ' + limbSweep + ' ' + cx + ',' + (cy + R) +
           ' A ' + rx + ',' + R + ' 0 0 ' + termSweep + ' ' + cx + ',' + (cy - R) + ' Z';
  }
  function placeBodyLabel(lab, az, r) {
    // Radially outward from Earth (inward for Proxima at the rim), the
    // anchor following the azimuth so the text leads away from the dot.
    var outward = (r <= 250);
    var rr = outward ? r + 17 : r - 17;
    var a = az * Math.PI / 180;
    var sx = Math.sin(a) * (outward ? 1 : -1);
    var anchor = 'middle';
    if (sx > 0.35) {
      anchor = 'start';
    } else if (sx < -0.35) {
      anchor = 'end';
    }
    lab.setAttribute('x', CX + rr * Math.sin(a));
    lab.setAttribute('y', CY - rr * Math.cos(a) + 4);
    lab.setAttribute('text-anchor', anchor);
  }

  // ---- loop-data history and derived motion -------------------------------
  // This script runs at global (window) scope, so its top-level names must
  // never collide with window's built-ins: `history` in particular is the
  // browser's read-only History object -- a `var history` here silently
  // fails to bind and every use of it throws or reads navigation state.
  var latest = null;      // last parsed loop-data object
  var latestTs = 0;       // its current.dateTime.raw (or receipt time)
  var packets = [];       // [{t, r}] oldest first, pruned to 10 minutes
  var HISTORY_SEC = 600;
  function pushHistory(t, r) {
    if (packets.length > 0 && t <= packets[packets.length - 1].t) {
      return;             // the same (or an older) packet again
    }
    packets.push({t: t, r: r});
    while (packets.length > 0 && t - packets[0].t > HISTORY_SEC) {
      packets.shift();
    }
  }
  function rateOf(key, wrap) {
    // Per-second rate of a numeric field over the retained history --
    // the oldest surviving packet against the newest, so short-window
    // jitter averages out.  null until two usable packets exist.
    if (packets.length < 2) {
      return null;
    }
    var a = packets[0], b = packets[packets.length - 1];
    var dt = b.t - a.t;
    var va = num(a.r, key), vb = num(b.r, key);
    if (dt < 1 || va === null || vb === null) {
      return null;
    }
    var dv = vb - va;
    if (wrap) {
      dv = ((dv + 540) % 360) - 180;   // azimuth crosses north
    }
    return dv / dt;
  }

  // ---- rendering ----------------------------------------------------------
  var prevOdometer = {};
  function setOdometer(id, text) {
    // Rewrite the km/miles readout, wrapping the changed digits in a span
    // the stylesheet flashes brass -- the odometer effect.
    var el = document.getElementById(id);
    if (!el || text === prevOdometer[id]) {
      return;
    }
    var prev = prevOdometer[id] || '';
    var i = 0, n = Math.min(text.length, prev.length);
    while (i < n && text.charAt(i) === prev.charAt(i)) {
      i++;
    }
    if (text.length !== prev.length) {
      i = 0;
    }
    el.innerHTML = text.slice(0, i) + '<span class="chg">' + text.slice(i) + '</span>';
    prevOdometer[id] = text;
  }
  function setRowBelow(key, below) {
    var row = document.getElementById('geo-row-' + key);
    if (row) {
      row.className = below ? 'row below' : 'row';
    }
  }
  function renderGeo(nowTs) {
    if (latest === null) {
      return;
    }
    if (dialMarks === null) {
      dialMarks = buildDial();
    }
    // Extrapolate at the derived rates between loop refreshes, re-anchoring
    // to truth on every packet; stale data stops advancing after
    // EXTRAP_MAX seconds so a dead feed cannot drift the page into fiction.
    var dt = Math.min(Math.max(nowTs - latestTs, 0), EXTRAP_MAX);
    // The moon's phase, for its dial disc: percent full plus waxing
    // (the next full moon precedes the next new moon).
    var moonFrac = num(latest, 'almanac.moon.phase');
    var nextFull = num(latest, 'almanac.next_full_moon.raw');
    var nextNew = num(latest, 'almanac.next_new_moon.raw');
    var waxing = (nextFull !== null && nextNew !== null) ? (nextFull < nextNew) : true;
    var litLeft = (STATION_LAT >= 0) ? !waxing : waxing;
    GEO_BODIES.forEach(function(pair) {
      var key = pair[0];
      var azKey = 'almanac.' + key + '.az';
      var altKey = 'almanac.' + key + '.alt';
      var distKey = 'almanac.' + key + '.earth_distance';
      var az = num(latest, azKey), alt = num(latest, altKey);
      var au = num(latest, distKey);
      var azRate = rateOf(azKey, true);
      var altRate = rateOf(altKey, false);
      var auRate = rateOf(distKey, false);
      var azNow = (az === null) ? null : (az + (azRate || 0) * dt + 360) % 360;
      var altNow = (alt === null) ? null : Math.max(-90, Math.min(90, alt + (altRate || 0) * dt));
      var auNow = (au === null) ? null : au + (auRate || 0) * dt;
      // The roster row: odometer, rate, au and altitude cells, each on its
      // own guard.
      if (auNow !== null) {
        setOdometer(distKey, numberWithCommas(Math.round(auNow * PER_AU)));
        setHtml('geo-au-' + key,
                (auNow >= 1000 ? auNow.toFixed(1) : auNow.toFixed(6)) + ' au');
      }
      if (auRate !== null) {
        var perSec = Math.abs(auRate) * PER_AU;
        setHtml('geo-rate-' + key,
                '<span class="arr">' + (auRate >= 0 ? '\u25B2' : '\u25BC') + '</span> ' +
                (auRate >= 0 ? 'receding' : 'approaching') + ' ' +
                perSec.toFixed(2) + DIST_LABEL + '/s');
      }
      if (altNow !== null) {
        setHtml('geo-alt-' + key,
                altNow < 0 ? 'below horizon' : 'alt ' + altNow.toFixed(1) + '&deg;');
        setRowBelow(key, altNow < 0);
      }
      // The dial: dot, phase, label and trail need the full position.
      var m = dialMarks === null ? null : dialMarks[key];
      if (!m) {
        return;
      }
      if (azNow === null || altNow === null || auNow === null) {
        m.g.setAttribute('display', 'none');
        m.lab.setAttribute('display', 'none');
        return;
      }
      m.g.removeAttribute('display');
      m.lab.removeAttribute('display');
      var below = altNow < 0;
      var r = rOfAu(auNow);
      var p = dialXY(azNow, r);
      m.dot.setAttribute('cx', p[0]);
      m.dot.setAttribute('cy', p[1]);
      if (key === 'moon') {
        if (moonFrac !== null && m.lit !== null) {
          m.lit.setAttribute('d', moonPath(p[0], p[1], 8, moonFrac / 100.0, litLeft));
        }
        m.rim.setAttribute('cx', p[0]);
        m.rim.setAttribute('cy', p[1]);
        m.g.setAttribute('class', below ? 'geomoon below' : 'geomoon');
      } else {
        var cls = 'geodot fill-' + key + (below ? ' below stroke-' + key : ' ring');
        m.dot.setAttribute('class', cls);
      }
      if (m.glow !== null) {
        m.glow.setAttribute('cx', p[0]);
        m.glow.setAttribute('cy', p[1]);
        m.glow.setAttribute('display', below ? 'none' : '');
      }
      m.lab.setAttribute('class', below ? 'bodylab dim' : 'bodylab');
      if (key === 'proxima_centauri') {
        m.lab.textContent = m.label + ' \u00B7 ' +
                            (auNow / AU_PER_LY).toFixed(2) + ' ly';
      }
      placeBodyLabel(m.lab, azNow, r);
      // The trail: the last hour of motion at the derived rates, drawn
      // backward from now (real observed positions replace nothing here --
      // the rates ARE observed, so the wake is the true recent path to
      // first order).  Hidden until motion can be derived.
      var haveRates = (azRate !== null && auRate !== null && altRate !== null);
      var step = TRAIL_SEC / TRAIL_N;
      for (var i = 0; i < TRAIL_N; i++) {
        var seg = m.segs[i];
        if (!haveRates) {
          seg.setAttribute('display', 'none');
          continue;
        }
        var backA = TRAIL_SEC - i * step;        // seconds before now
        var backB = backA - step;
        var azA = (azNow - azRate * backA + 720) % 360;
        var azB = (azNow - azRate * backB + 720) % 360;
        var rA = rOfAu(auNow - auRate * backA);
        var rB = rOfAu(auNow - auRate * backB);
        var altB = altNow - altRate * backB;
        var pA = dialXY(azA, rA), pB = dialXY(azB, rB);
        seg.removeAttribute('display');
        seg.setAttribute('x1', pA[0]);
        seg.setAttribute('y1', pA[1]);
        seg.setAttribute('x2', pB[0]);
        seg.setAttribute('y2', pB[1]);
        seg.setAttribute('stroke-opacity',
                         (i + 1) / TRAIL_N * (altB < 0 ? 0.28 : 0.6));
      }
    });
  }

  // ---- poll + local tick ---------------------------------------------------
  function localTick() {
    var nowTs = Date.now() / 1000;
    setHtml('live-clock', fmtHMS(nowTs));
    if (latest !== null) {
      renderGeo(nowTs);
    }
  }
  function updateCurrent() {
    if (pageTimedOut) {
        setUpExpiredClickListener();
        return false;
    }
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
      try {
        var result = JSON.parse(this.responseText);
        var nowTs = Date.now() / 1000;

        // Check the date
        // "dateTime": 1578965850,
        var lastTs = result["current.dateTime.raw"];
        if (typeof lastTs === 'number') {
          var age = Math.round(Math.abs(Date.now() - lastTs * 1000) / 1000);
          setHtml("live-label", age <= 6 ? "LIVE" : age + "s ago");
          // Display the time of the last update, in the page's timezone.
          setHtml("last-update", fmtHMS(lastTs));
        }

        latest = result;
        latestTs = (typeof lastTs === 'number') ? lastTs : nowTs;
        pushHistory(latestTs, result);
        renderGeo(nowTs);
      } catch (e) {
        console.log(e);
      }
    }
    xhttp.onerror = function() {
      try {
        // Status not OK (!= 200).
        var element = document.getElementById("live-label");
        element.innerHTML = "";
        console.log('status: ' + this.status);
      } catch (e) {
        console.log(e);
      }
    }
    try {
      xhttp.timeout = 1800;
      xhttp.open("GET", "$Extras.loop_data_file", true);
      xhttp.send();
    } catch (e) {
      console.log(e);
    }
  }
</script>
