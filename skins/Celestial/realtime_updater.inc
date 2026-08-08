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
  // The report's language drives toLocaleString (clock and last-update
  // formats); an unknown tag must not break every render.
  LOCALE = '$lang';
  try {
    new Date().toLocaleString(LOCALE);
  } catch (e) {
    console.log('bad lang "' + LOCALE + '", using en-US');
    LOCALE = 'en-US';
  }
  ## Everything this script composes is translated at generation time and
  ## fed here: body names from the report's [Almanac] section (the same
  ## source as $almanac.<body>.label -- any almanac tier has .texts),
  ## cardinals from the report formatter's compass ordinates, and the
  ## badge/roster strings from [Texts] via $gettext (each key spelled out
  ## literally so the tests can tie the include to lang/en.conf).  All
  ## three ride through json.dumps, which \u-escapes every non-ASCII
  ## character -- html_entities encoding can never touch them, and dial
  ## labels land via textContent where entities would show literally.
  #import json
  #set $names = {}
  #for $b in ('moon', 'sun', 'mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto', 'earth')
  #silent $names.update({$b: str($almanac.texts.get($b, $b.capitalize()))})
  #end for
  BODY_LABELS = $json.dumps($names);
  #set $ords = $almanac.formatter.ordinate_names
  CARDINALS = $json.dumps([str($ords[0]), str($ords[4]), str($ords[8]), str($ords[12])]);
  #set $t = {}
  #silent $t.update({'alt {alt}°': $gettext('alt {alt}°')})
  #silent $t.update({'below horizon': $gettext('below horizon')})
  #silent $t.update({'{dist} au': $gettext('{dist} au')})
  #silent $t.update({'receding': $gettext('receding')})
  #silent $t.update({'approaching': $gettext('approaching')})
  #silent $t.update({'LIVE': $gettext('LIVE')})
  #silent $t.update({'{age}s ago': $gettext('{age}s ago')})
  #silent $t.update({'NO DATA (HTTP {status}) — check loop_data_file': $gettext('NO DATA (HTTP {status}) — check loop_data_file')})
  #silent $t.update({'BAD DATA — check loop_data_file': $gettext('BAD DATA — check loop_data_file')})
  #silent $t.update({'OFFLINE': $gettext('OFFLINE')})
  #silent $t.update({'CLICK-ME': $gettext('CLICK-ME')})
  #silent $t.update({'{ly} ly': $gettext('{ly} ly')})
  #silent $t.update({'Proxima': $gettext('Proxima')})
  ## The satellite rows' live strings -- countdown, pass description and
  ## the honest empty states -- shared verbatim with weewx-skyfield's Sky
  ## page (its translations are mined into this skin's lang files).
  #silent $t.update({'overhead now': $gettext('overhead now')})
  #silent $t.update({'in {m} min': $gettext('in {m} min')})
  #silent $t.update({'in {h} h': $gettext('in {h} h')})
  #silent $t.update({'in {n} day': $gettext('in {n} day')})
  #silent $t.update({'in {n} days': $gettext('in {n} days')})
  #silent $t.update({'just set': $gettext('just set')})
  #silent $t.update({'appears {rise} · peaks {alt}° {culm} · disappears {set} · {m} min': $gettext('appears {rise} · peaks {alt}° {culm} · disappears {set} · {m} min')})
  #silent $t.update({'no visible pass in the coming week': $gettext('no visible pass in the coming week')})
  #silent $t.update({'no pass in the coming week': $gettext('no pass in the coming week')})
  #silent $t.update({'visible': $gettext('visible')})
  #silent $t.update({'not visible': $gettext('not visible')})
  #silent $t.update({'no usable orbital elements — see the weewxd log': $gettext('no usable orbital elements — see the weewxd log')})
  T = $json.dumps($t);
  // Composed translations: look the English key up in T (falling back to
  // the key, so a missing entry renders English) and fill the {named}
  // placeholders.  Javascript key literals must spell non-ASCII with \u
  // escapes to match json.dumps' escaping of the generated object.
  function fmt(key, params) {
    var s = T[key] || key;
    for (var k in params) {
      s = s.replace('{' + k + '}', params[k]);
    }
    return s;
  }
  function bodyLabel(key) {
    if (key === 'proxima_centauri') {
      return T['Proxima'] || 'Proxima';
    }
    return BODY_LABELS[key] || key;
  }
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
    if (liveLabel.innerHTML != T['CLICK-ME']) {
      liveLabel.innerHTML = T['CLICK-ME'];
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
      // Expire in N hours, clamped to the browser's int32 timer-delay
      // ceiling (~24.8 days): past 2147483647 ms the delay overflows
      // and the timer fires early -- an expiration_time over ~596
      // hours would otherwise expire the page at once instead of
      // effectively never.
      setTimeout(expirePage,
                 Math.min(1000 * 60 * 60 * expiration_time, 2147483647));
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
    return new Date(ts * 1000).toLocaleString(LOCALE,
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
  // Bodies in roster order; display names come from BODY_LABELS/T via
  // bodyLabel.  Proxima Centauri is served only by the weewx-skyfield
  // almanac (with stars on); its row and dot simply stay empty on any
  // other almanac.
  var GEO_BODIES = [
    'moon', 'sun', 'mercury', 'venus', 'mars', 'jupiter',
    'saturn', 'uranus', 'neptune', 'pluto', 'proxima_centauri'
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
    var au = function(d) { return fmt('{dist} au', {dist: d}); };
    var ringLabels = [au('0.01'), '0.1', au('1'), '10', '100',
                      au('10\u00B3'), '10\u2074', '10\u2075'];
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
    var cardinals = [[0, CARDINALS[0]], [90, CARDINALS[1]],
                     [180, CARDINALS[2]], [270, CARDINALS[3]]];
    for (var c = 0; c < cardinals.length; c++) {
      var pc = dialXY(cardinals[c][0], 310);
      svgEl('text', {x: pc[0], y: pc[1] + 4.5, 'class': 'cardinal',
                     'text-anchor': 'middle'}, dial, cardinals[c][1]);
    }
    svgEl('circle', {cx: CX, cy: CY, r: 9, 'class': 'fill-earth geo-earth'}, dial);
    svgEl('text', {x: CX, y: CY + 24, 'class': 'earthlab'}, dial,
          BODY_LABELS['earth'] || 'Earth');
    var trailsG = svgEl('g', {}, dial);
    var marks = {};
    GEO_BODIES.forEach(function(key) {
      var segs = [];
      for (var i = 0; i < TRAIL_N; i++) {
        segs.push(svgEl('line', {'class': 'trail stroke-' + key,
                                 display: 'none'}, trailsG));
      }
      var g = svgEl('g', {display: 'none'}, dial);
      var m = {label: bodyLabel(key), g: g, segs: segs,
               glow: null, dot: null, lit: null, rim: null};
      // sky.js's document-level tap listener serves any mark owning a
      // <title> child; renderGeo keeps the text live.
      m.title = svgEl('title', {}, g, m.label);
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
      m.lab = svgEl('text', {'class': 'bodylab'}, dial, m.label);
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
  function rateBetween(a, b, key, wrap) {
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
  function rateOf(key, wrap) {
    // Per-second rate of a numeric field over the retained history --
    // the oldest surviving packet against the newest, so short-window
    // jitter averages out.  null until two usable packets exist.
    if (packets.length < 2) {
      return null;
    }
    return rateBetween(packets[0], packets[packets.length - 1], key, wrap);
  }
  function recentRateOf(key, wrap) {
    // Per-second rate over the two NEWEST packets, for the satellites:
    // a LEO pass curves through its whole ~10 minutes, so the ring-long
    // average -- right for the planets' steady drift -- lags the turn,
    // and every packet then snaps the mark back a few pixels (a visible
    // bounce, worst on the name label).  Two SGP4-computed points 2 s
    // apart track the curve and carry no jitter worth averaging.
    if (packets.length < 2) {
      return null;
    }
    return rateBetween(packets[packets.length - 2], packets[packets.length - 1],
                       key, wrap);
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
    // Pinned spellings since 7.6; the pre-7.6 unpinned keys remain as
    // fallbacks so a fields line migrated earlier keeps working unchanged.
    var nextFull = num(latest, 'almanac.next_full_moon.unix_epoch.raw');
    if (nextFull === null) {
      nextFull = num(latest, 'almanac.next_full_moon.raw');
    }
    var nextNew = num(latest, 'almanac.next_new_moon.unix_epoch.raw');
    if (nextNew === null) {
      nextNew = num(latest, 'almanac.next_new_moon.raw');
    }
    var waxing = (nextFull !== null && nextNew !== null) ? (nextFull < nextNew) : true;
    var litLeft = (STATION_LAT >= 0) ? !waxing : waxing;
    GEO_BODIES.forEach(function(key) {
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
                fmt('{dist} au',
                    {dist: auNow >= 1000 ? auNow.toFixed(1) : auNow.toFixed(6)}));
      }
      if (auRate !== null) {
        var perSec = Math.abs(auRate) * PER_AU;
        setHtml('geo-rate-' + key,
                '<span class="arr">' + (auRate >= 0 ? '\u25B2' : '\u25BC') + '</span> ' +
                T[auRate >= 0 ? 'receding' : 'approaching'] + ' ' +
                perSec.toFixed(2) + DIST_LABEL + '/s');
      }
      if (altNow !== null) {
        setHtml('geo-alt-' + key,
                altNow < 0 ? T['below horizon']
                           : fmt('alt {alt}\u00B0', {alt: altNow.toFixed(1)}));
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
      m.title.textContent = m.label + ' \u00B7 ' +
          (below ? T['below horizon']
                 : fmt('alt {alt}\u00B0', {alt: altNow.toFixed(1)})) +
          ' \u00B7 ' +
          fmt('{dist} au',
              {dist: auNow >= 1000 ? auNow.toFixed(1) : auNow.toFixed(6)});
      if (key === 'proxima_centauri') {
        m.lab.textContent = m.label + ' \u00B7 ' +
                            fmt('{ly} ly', {ly: (auNow / AU_PER_LY).toFixed(2)});
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

  // ---- the sky dome -------------------------------------------------------
  // The backdrop is weewx-skyfield's dome_svg, embedded at generation time
  // and refetched (dome-svg.txt, rewritten each report cycle) so an
  // open page never drifts more than DOME_REFRESH behind the sky.  Between
  // refetches the sun/moon/planet marks are nudged at the loop-derived
  // rates through their data-body hooks (skyfield 2.0's consumer
  // contract; an older dome simply has no hooks and nothing moves).  The
  // satellites are the genuinely live layer: their marks are this
  // script's own, repositioned every tick, with the static generation-time
  // marker hidden whenever the loop feed carries the satellite.
  // The backdrop refetch walks the staggered fragment set (dome-svg.txt
  // plus dome-svg-1..9.txt, written together each report cycle at
  // max(60 s, interval/10) spacing): each minute the fetch asks for the
  // slot covering the current time, so the sky steps a quarter degree
  // instead of lurching a full cycle's rotation at once.  The set
  // self-describes through the fragment wrapper's data-dome-ts/-slot/
  // -step/-count -- ts is the fragment's OWN depicted time, so the walk
  // must de-relativize it through the slot number (base = ts -
  // slot*step) before computing the next slot -- so any archive
  // interval works unconfigured; when the slots
  // run out before a late report cycle lands, the fetch falls back to
  // slot 0 and the page degrades to the pre-stagger behavior.  The
  // chart keeps the old cadence: it is a fixed future scene, not a
  // rotating sky.
  var DOME_REFRESH = 60;       // seconds between backdrop refetches
  var CHART_REFRESH = 300;     // seconds between pass-chart refetches
  var DOME_BODIES = ['sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter',
                     'saturn', 'uranus', 'neptune'];
  ## The satellite set follows the station's [Skyfield] [[Satellites]],
  ## enumerated through skyfield 2.0's public satellite_names() (guarded:
  ## an older skyfield has no method and no satellites).  The template
  ## builds the roster rows from the same list, so rows and live layer
  ## always agree; the loopdata fields line stays per-satellite manual
  ## (the README shows the pattern).
  #set $sat_names = []
  #if $sky_page
  #try
  #for $n in $sky_page.satellite_names()
  #silent $sat_names.append(str($n))
  #end for
  #except
  #pass
  #end try
  #end if
  SAT_NAMES = $json.dumps($sat_names);
  // dome_svg's fixed geometry (viewBox 0 0 680 706): sky-chart
  // orientation, north up, EAST LEFT -- hence minus sine.  Mirrors
  // wxskyfield_sky._dome_xy; deliberately opposite the dial's east-right.
  var DOME_CX = 340, DOME_CY = 348, DOME_R = 296;
  function domeXY(az, alt) {
    var rr = DOME_R * (90 - alt) / 90;
    var a = az * Math.PI / 180;
    return [DOME_CX - rr * Math.sin(a), DOME_CY - rr * Math.cos(a)];
  }
  function domeSvg() {
    var wrap = document.getElementById('dome-svg');
    return wrap === null ? null : wrap.querySelector('svg');
  }
  function hasKey(key) {
    return latest !== null && Object.prototype.hasOwnProperty.call(latest, key);
  }
  function numOr(primary, fallback) {
    // The pinned-unit spelling first, the bare .raw as the fallback --
    // the same drop-in idiom as the 7.6 moon keys.
    var v = num(latest, primary);
    return v !== null ? v : num(latest, fallback);
  }
  function strAt(key) {
    return (latest !== null && typeof latest[key] === 'string') ? latest[key] : null;
  }
  // Per-body baselines: each mark's generated position, read once per
  // fetched backdrop from its circle's cx/cy; the nudge is a translate of
  // (live position - generated position) applied to the mark group and
  // its label.
  var domeBase = null;
  function readDomeBase() {
    domeBase = {};
    var svg = domeSvg();
    if (svg === null) {
      return;
    }
    DOME_BODIES.forEach(function(key) {
      var g = svg.querySelector('g.dome-body[data-body="' + key + '"]');
      if (g === null) {
        return;              // below the horizon at generation time
      }
      var c = g.querySelector('circle');
      if (c === null || !c.hasAttribute('cx')) {
        return;
      }
      domeBase[key] = {g: g,
                       lab: svg.querySelector('text[data-body="' + key + '"]'),
                       x: parseFloat(c.getAttribute('cx')),
                       y: parseFloat(c.getAttribute('cy'))};
    });
  }
  function renderDome(nowTs) {
    var svg = domeSvg();
    if (svg === null || latest === null) {
      return;
    }
    if (domeBase === null) {
      readDomeBase();
    }
    var dt = Math.min(Math.max(nowTs - latestTs, 0), EXTRAP_MAX);
    DOME_BODIES.forEach(function(key) {
      var b = domeBase[key];
      if (!b) {
        return;              // no mark to nudge; the next refetch draws it
      }
      var az = num(latest, 'almanac.' + key + '.az');
      var alt = num(latest, 'almanac.' + key + '.alt');
      if (az === null || alt === null) {
        return;              // no live data: the mark stands as generated
      }
      var azNow = (az + (rateOf('almanac.' + key + '.az', true) || 0) * dt + 360) % 360;
      var altNow = alt + (rateOf('almanac.' + key + '.alt', false) || 0) * dt;
      if (altNow <= 0) {
        // Set since generation: hide rather than pin to the rim.
        b.g.setAttribute('display', 'none');
        if (b.lab !== null) {
          b.lab.setAttribute('display', 'none');
        }
        return;
      }
      b.g.removeAttribute('display');
      var p = domeXY(azNow, altNow);
      var tr = 'translate(' + (p[0] - b.x).toFixed(1) + ' ' + (p[1] - b.y).toFixed(1) + ')';
      b.g.setAttribute('transform', tr);
      if (b.lab !== null) {
        b.lab.removeAttribute('display');
        b.lab.setAttribute('transform', tr);
      }
    });
    renderSats(nowTs, svg);
  }
  // The live satellite layer: our own marker (dot + name), created
  // inside the current backdrop and rebuilt after every swap.  Feature
  // detection is key PRESENCE: a loop feed without the
  // satellite keys (older skyfield, no [[Satellites]], unmigrated fields
  // line) leaves the static dome untouched; keys present but null mean
  // unusable elements -- configured, but nothing to draw.
  var satMarks = null;
  // NOTE (2026-08-06, tried and rejected -- do not re-add without a
  // better idea): easing the marker toward each packet's anchor
  // (first-order glide, TAU 0.8 and 1.6 both shot and compared) to
  // kill the small extrapolate-then-correct zigzag at culmination.
  // John judged the cure worse than the disease on the pass chart:
  // the lag pulls the dot visibly off the drawn arc -- a sustained
  // error against a truth reference, where the zigzag is fast noise
  // centered on it.  The zigzag is accepted: per-packet anchors are
  // true positions, and at live speed it is sub-perceptual.
  function satLabel(name) {
    var lab = strAt('almanac.' + name + '.label');
    return lab !== null ? lab : name.charAt(0).toUpperCase() + name.slice(1);
  }
  function buildSatMark(svg) {
    var g = svgEl('g', {display: 'none'}, svg);
    return {g: g,
            dot: svgEl('circle', {r: 4, 'class': 'satdot'}, g),
            lab: svgEl('text', {'class': 'satlab'}, g)};
  }
  function satWhen(riseTs, setTs, nowTs) {
    if (setTs !== null && riseTs <= nowTs && nowTs < setTs) {
      return T['overhead now'];
    }
    var delta = riseTs - nowTs;
    if (delta < 0) {
      // The pass ended but the feed has not rolled the next_pass fields
      // forward yet (a one-packet window): past tense, never a countdown.
      return T['just set'];
    }
    if (delta < 3600) {
      return fmt('in {m} min', {m: Math.max(1, Math.floor(delta / 60))});
    }
    if (delta < 86400) {
      return fmt('in {h} h', {h: Math.round(delta / 3600)});
    }
    var n = Math.ceil(delta / 86400);
    return n === 1 ? fmt('in {n} day', {n: 1}) : fmt('in {n} days', {n: n});
  }
  function fmtDayHM(ts) {
    return new Date(ts * 1000).toLocaleString(LOCALE,
      tzOptions({month: 'short', day: 'numeric',
                 hour: '2-digit', minute: '2-digit'}));
  }
  function renderPassRow(base, lineId, passId, noPassMsg, sunlit, nowTs, tagVisibility) {
    // One roster row from a pass chain (base runs through .next_pass or
    // .next_visible_pass): the dated countdown line, then the
    // appears/peaks/disappears sub-line -- tagged visible/not visible
    // from the pass's own bool when the caller asks (the any-pass
    // table).  Honest rows when there is no pass: noPassMsg with usable
    // elements, the weewxd-log row without.  setHtml is a no-op when
    // the report almanac never served the row.
    if (!hasKey(base + '.rise.unix_epoch.raw') && !hasKey(base + '.rise.raw')) {
      // Not in the fields line at all: the report-time first paint
      // stands.  A key PRESENT with a null value is different -- that
      // is loopdata's honest "no pass", handled below.
      return;
    }
    var rise = numOr(base + '.rise.unix_epoch.raw', base + '.rise.raw');
    var setTs = numOr(base + '.set.unix_epoch.raw', base + '.set.raw');
    if (rise === null) {
      if (sunlit !== null && sunlit !== undefined) {
        setHtml(lineId, noPassMsg);
      } else {
        setHtml(lineId, T['no usable orbital elements \u2014 see the weewxd log']);
      }
      setHtml(passId, '');
      return;
    }
    setHtml(lineId, fmtDayHM(rise) + ' \u00B7 ' + satWhen(rise, setTs, nowTs));
    var maxAlt = numOr(base + '.max_altitude.degree_angle.raw',
                       base + '.max_altitude.raw');
    var dur = numOr(base + '.duration.second.raw', base + '.duration.raw');
    var riseOrd = strAt(base + '.rise_azimuth.ordinal_compass');
    var culmOrd = strAt(base + '.culmination_azimuth.ordinal_compass');
    var setOrd = strAt(base + '.set_azimuth.ordinal_compass');
    if (maxAlt === null || dur === null || riseOrd === null ||
        culmOrd === null || setOrd === null) {
      return;
    }
    var sub = fmt('appears {rise} \u00B7 peaks {alt}\u00B0 {culm} \u00B7 disappears {set} \u00B7 {m} min',
                  {rise: riseOrd, alt: maxAlt.toFixed(0), culm: culmOrd,
                   set: setOrd, m: Math.round(dur / 60).toString()});
    if (tagVisibility) {
      var vis = latest[base + '.visible'];
      if (vis === true) {
        sub += ' \u00B7 ' + T['visible'];
      } else if (vis === false) {
        sub += ' \u00B7 ' + T['not visible'];
      }
    }
    setHtml(passId, sub);
  }
  function renderSats(nowTs, svg) {
    if (satMarks === null) {
      satMarks = {};
    }
    var dt = Math.min(Math.max(nowTs - latestTs, 0), EXTRAP_MAX);
    SAT_NAMES.forEach(function(name) {
      var azKey = 'almanac.' + name + '.az';
      var altKey = 'almanac.' + name + '.alt';
      if (!hasKey(azKey)) {
        return;              // not in the loop feed: static dome stands
      }
      // The two countdown rows, one per table (present only when the
      // report almanac served them; setHtml is a no-op otherwise): the
      // dome's next pass of ANY kind, visibility-tagged, and the Next
      // Pass panel's next visible pass.
      var sunlit = latest['almanac.' + name + '.sunlit'];
      renderPassRow('almanac.' + name + '.next_pass',
                    'sat-any-line-' + name, 'sat-any-pass-' + name,
                    T['no pass in the coming week'], sunlit, nowTs, true);
      renderPassRow('almanac.' + name + '.next_visible_pass',
                    'sat-line-' + name, 'sat-pass-' + name,
                    T['no visible pass in the coming week'], sunlit, nowTs,
                    false);
      // The marker.  Wrap-aware azimuth extrapolation keeps a zenith pass
      // smooth; EXTRAP_MAX freezes a stale feed, which is exactly right
      // for a vanished satellite.
      var az = num(latest, azKey), alt = num(latest, altKey);
      var azNow = (az === null) ? null
                                : (az + (recentRateOf(azKey, true) || 0) * dt + 360) % 360;
      var altNow = (alt === null) ? null : alt + (recentRateOf(altKey, false) || 0) * dt;
      var m = satMarks[name];
      var overhead = (azNow !== null && altNow !== null && altNow > 0);
      if (overhead && m === undefined) {
        m = satMarks[name] = buildSatMark(svg);
      }
      // The static generation-time marker is superseded whenever the loop
      // feed carries this satellite -- dot AND name label, since our own
      // marker draws the name at the live position and a kept static
      // label would be a ghost name with no dot.
      var stat = svg.querySelector('g.dome-body[data-body="' + name + '"]');
      if (stat !== null) {
        stat.setAttribute('display', 'none');
      }
      var statLab = svg.querySelector('text[data-body="' + name + '"]');
      if (statLab !== null) {
        statLab.setAttribute('display', 'none');
      }
      if (m === undefined) {
        return;
      }
      if (!overhead) {
        m.g.setAttribute('display', 'none');
        return;
      }
      m.g.removeAttribute('display');
      var p = domeXY(azNow, altNow);
      m.dot.setAttribute('cx', p[0].toFixed(1));
      m.dot.setAttribute('cy', p[1].toFixed(1));
      // Two orthogonal signals, composing.  Ring vs solid is the
      // satellite's own state: inside Earth's shadow the dot inverts to
      // a hollow ring (the static dome's convention).  Faint vs full is
      // the sky's state: sun at -6 or above (the visible-pass
      // definition) dims the dot.  The name label dims on either cause
      // -- it is about findability by eye.  Overhead-but-dimmed is
      // still drawn: the dome shows what is up, like its daytime moon
      // and stars.
      var sunAlt = num(latest, 'almanac.sun.alt');
      var shadowed = (sunlit === false);
      var daylight = (sunAlt !== null && sunAlt >= -6);
      m.dot.setAttribute('class', 'satdot' + (shadowed ? ' shadow' : '')
                                           + (daylight ? ' faint' : ''));
      m.lab.setAttribute('class',
                         (shadowed || daylight) ? 'satlab faint' : 'satlab');
      m.lab.textContent = satLabel(name);
      m.lab.setAttribute('x', (p[0] + 8).toFixed(1));
      m.lab.setAttribute('y', (p[1] - 6).toFixed(1));
    });
  }
  function domeFragMeta() {
    // The current backdrop's self-description, from the fragment
    // wrapper's data attributes.  null on a pre-stagger backdrop (an
    // upgrade race) or a hand-stripped wrapper: the fetch then sticks to
    // slot 0, which is the pre-stagger behavior exactly.
    var wrap = document.getElementById('dome-svg');
    var d = wrap === null ? null : wrap.querySelector('div[data-dome-ts]');
    if (d === null) {
      return null;
    }
    var ts = parseFloat(d.getAttribute('data-dome-ts'));
    var step = parseFloat(d.getAttribute('data-dome-step'));
    var count = parseInt(d.getAttribute('data-dome-count'), 10);
    if (!isFinite(ts) || !isFinite(step) || step <= 0 || !(count >= 1)) {
      return null;
    }
    // ts is the displayed fragment's OWN depicted time; the slot number
    // recovers the cycle base.  Computing the walk from ts directly made
    // the next slot RELATIVE to whichever slot was showing -- the dome
    // stepped 0,2,1,3,2, visibly zigzagging in the NOAA-21 live capture.
    var slot = parseInt(d.getAttribute('data-dome-slot'), 10);
    if (!isFinite(slot) || slot < 0 || slot >= count) {
      slot = 0;
    }
    return {ts: ts, step: step, count: count, slot: slot};
  }
  function domeFragName() {
    var m = domeFragMeta();
    if (m !== null) {
      var base = m.ts - m.slot * m.step;
      var k = Math.floor((Date.now() / 1000 - base) / m.step);
      if (k >= 1 && k < m.count) {
        return 'dome-svg-' + k + '.txt';
      }
      // k < 1: still inside slot 0's minute.  k >= count: the next
      // report cycle is due (or late) -- ask for slot 0 and let its
      // timestamp tell us which cycle actually answered.
    }
    return 'dome-svg.txt';
  }
  function hideSkytip() {
    // sky.js's tap chip does not follow its mark, so a fragment swap
    // would leave an open chip floating over a sky that has moved on:
    // dismiss it whenever the dome or the pass chart is replaced.  This
    // mirrors sky.js's own hideTip -- hide the div, never remove it
    // (sky.js holds it in a closure and would go on writing into a
    // detached node).  A no-op when sky.js has not created a chip yet.
    var tip = document.querySelector('.skytip');
    if (tip !== null) {
      tip.style.display = 'none';
    }
  }
  var appliedDomeFrag = null;
  function refreshDome() {
    if (pageTimedOut) {
      return;
    }
    var fragName = domeFragName();
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
      // Anything but a fresh SVG keeps the dome we already have: a failed
      // fetch (including a 404 from a pre-stagger server), an empty
      // fragment (no capable almanac this cycle, or a slot beyond the
      // interval), or junk.
      if ((this.status !== 200 && this.status !== 0) ||
          this.responseText.indexOf('<svg') === -1) {
        return;
      }
      var wrap = document.getElementById('dome-svg');
      if (wrap === null) {
        return;
      }
      // The same slot of the same cycle (a late report re-serving what
      // we already show) is a no-op: swapping identical content would
      // only churn the baselines.
      var m = /data-dome-ts="([0-9.]+)"/.exec(this.responseText);
      var ident = fragName + '|' + (m === null ? '' : m[1]);
      if (ident === appliedDomeFrag) {
        return;
      }
      // Never step the sky backward: a late report cycle answers the
      // slot-0 ask with the PREVIOUS cycle's file, whose sky the page
      // already stepped past.  Keep the newer backdrop; the walk asks
      // again next minute.
      var cur = domeFragMeta();
      if (cur !== null && m !== null && parseFloat(m[1]) < cur.ts) {
        return;
      }
      appliedDomeFrag = ident;
      wrap.innerHTML = this.responseText;
      hideSkytip();
      domeBase = null;       // baselines belong to the old backdrop
      satMarks = null;       // the live layer's elements were replaced too
      if (latest !== null) {
        renderDome(Date.now() / 1000);
      }
    };
    try {
      // Cache-busted: the fragment is a static file and heuristic browser
      // caching would happily serve a stale sky.
      xhttp.open('GET', fragName + '?ts=' + Date.now(), true);
      xhttp.send();
    } catch (e) {
      console.log(e);
    }
  }
  setInterval(refreshDome, DOME_REFRESH * 1000);

  // ---- the next-pass chart -------------------------------------------------
  // The chart is skyfield 2.0's pass_chart_html: the sky at the soonest
  // visible pass's culmination, the arc dashed across it, the featured
  // satellite's own dot at the arc's peak (a dome-body group -- the same
  // consumer contract as the dome's marks, under the chart's own SVG
  // ids).  During the pass itself the chart's epoch is within minutes of
  // now, so nudging that ONE dot from the live alt/az is epoch-honest;
  // the chart's sun, moon, planets and stars belong to the culmination
  // instant and are never touched.  The fragment refetch (pass-chart.txt,
  // rewritten each report cycle) swaps in the next chart once a pass
  // completes; a deliberately EMPTY fragment means no visible pass in the
  // elements' validity window and hides the panel.
  var passBase = null;
  function passSvg() {
    var wrap = document.getElementById('pass-chart');
    return wrap === null ? null : wrap.querySelector('svg');
  }
  function readPassBase() {
    // The featured satellite is named by the arc's own data-body; its
    // baseline is the dot's generated position, exactly the dome-mark
    // pattern.  tag stays null when the chart lacks the hooks (an older
    // skyfield): nothing sweeps, the chart stands as drawn.
    passBase = {tag: null};
    var svg = passSvg();
    if (svg === null) {
      return;
    }
    var track = svg.querySelector('g.dome-track');
    if (track === null) {
      return;
    }
    var tag = track.getAttribute('data-body');
    var g = svg.querySelector('g.dome-body[data-body="' + tag + '"]');
    var c = g === null ? null : g.querySelector('circle');
    if (c === null || !c.hasAttribute('cx')) {
      return;
    }
    passBase = {tag: tag, g: g,
                lab: svg.querySelector('text[data-body="' + tag + '"]'),
                x: parseFloat(c.getAttribute('cx')),
                y: parseFloat(c.getAttribute('cy'))};
  }
  function renderPass(nowTs) {
    if (passSvg() === null || latest === null) {
      return;
    }
    if (passBase === null) {
      readPassBase();
    }
    var b = passBase;
    if (b.tag === null) {
      return;
    }
    var rise = numOr('almanac.' + b.tag + '.next_visible_pass.rise.unix_epoch.raw',
                     'almanac.' + b.tag + '.next_visible_pass.rise.raw');
    var setTs = numOr('almanac.' + b.tag + '.next_visible_pass.set.unix_epoch.raw',
                      'almanac.' + b.tag + '.next_visible_pass.set.raw');
    if (rise === null || setTs === null || nowTs < rise || nowTs >= setTs) {
      // Not in the pass: the chart is a prediction and stands as drawn
      // (after the pass the next refetch brings the next chart).
      b.g.removeAttribute('transform');
      b.g.removeAttribute('display');
      if (b.lab !== null) {
        b.lab.removeAttribute('transform');
      }
      return;
    }
    var az = num(latest, 'almanac.' + b.tag + '.az');
    var alt = num(latest, 'almanac.' + b.tag + '.alt');
    if (az === null || alt === null) {
      return;
    }
    var dt = Math.min(Math.max(nowTs - latestTs, 0), EXTRAP_MAX);
    var azNow = (az + (recentRateOf('almanac.' + b.tag + '.az', true) || 0) * dt + 360) % 360;
    var altNow = alt + (recentRateOf('almanac.' + b.tag + '.alt', false) || 0) * dt;
    if (altNow <= 0) {
      // The in-progress window's first and last seconds can dip below
      // the rim: hide rather than pin, like the dome's marks.
      b.g.setAttribute('display', 'none');
      return;
    }
    b.g.removeAttribute('display');
    var p = domeXY(azNow, altNow);
    var tr = 'translate(' + (p[0] - b.x).toFixed(1) + ' ' + (p[1] - b.y).toFixed(1) + ')';
    b.g.setAttribute('transform', tr);
    if (b.lab !== null) {
      b.lab.setAttribute('transform', tr);
    }
  }
  function refreshPass() {
    if (pageTimedOut) {
      return;
    }
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
      var wrap = document.getElementById('pass-chart');
      var sec = document.getElementById('pass-sec');
      var chart = document.getElementById('pass-wrap');
      if (wrap === null || sec === null || chart === null ||
          (this.status !== 200 && this.status !== 0)) {
        return;              // a failed fetch keeps the chart we have
      }
      if (this.responseText.indexOf('<svg') === -1) {
        // A well-formed EMPTY fragment is meaningful -- no visible pass
        // among the configured satellites.  The chart area hides; the
        // roster's honest rows keep the section up, which hides only
        // when it has no roster either.  Junk keeps the chart we have.
        if (!/\S/.test(this.responseText)) {
          wrap.innerHTML = '';
          hideSkytip();
          chart.setAttribute('hidden', '');
          if (sec.querySelector('.roster') === null) {
            sec.setAttribute('hidden', '');
          }
          passBase = null;
        }
        return;
      }
      wrap.innerHTML = this.responseText;
      hideSkytip();
      chart.removeAttribute('hidden');
      sec.removeAttribute('hidden');
      passBase = null;       // baselines belong to the old chart
      if (latest !== null) {
        renderPass(Date.now() / 1000);
      }
    };
    try {
      // Cache-busted, like the dome fragment.
      xhttp.open('GET', 'pass-chart.txt?ts=' + Date.now(), true);
      xhttp.send();
    } catch (e) {
      console.log(e);
    }
  }
  setInterval(refreshPass, CHART_REFRESH * 1000);

  // ---- poll + local tick ---------------------------------------------------
  function localTick() {
    var nowTs = Date.now() / 1000;
    setHtml('live-clock', fmtHMS(nowTs));
    if (latest !== null) {
      renderGeo(nowTs);
      renderDome(nowTs);
      renderPass(nowTs);
    }
  }
  function updateCurrent() {
    if (pageTimedOut) {
        setUpExpiredClickListener();
        return false;
    }
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
      // A response arrived, but only HTTP 200 carries the file (status 0
      // covers a page opened from file:).  Anything else is almost always
      // loop_data_file not resolving to where weewx-loopdata writes -- the
      // classic being a 404 page because the file lives outside HTML_ROOT
      // (say /dev/shm) with nothing on the web server serving it.  Say so
      // in the badge: the old behavior (a console error only a debugging
      // user ever finds) left the page silently dead.
      if (this.status !== 200 && this.status !== 0) {
        setHtml("live-label",
                fmt('NO DATA (HTTP {status}) \u2014 check loop_data_file',
                    {status: this.status}));
        return;
      }
      var result;
      try {
        result = JSON.parse(this.responseText);
      } catch (e) {
        // A 200 with a non-JSON body: loop_data_file points at something,
        // but not at weewx-loopdata's output.
        setHtml("live-label", T['BAD DATA \u2014 check loop_data_file']);
        console.log(e);
        return;
      }
      try {
        var nowTs = Date.now() / 1000;

        // Check the date
        // "dateTime": 1578965850,
        var lastTs = result["current.dateTime.raw"];
        if (typeof lastTs === 'number') {
          var age = Math.round(Math.abs(Date.now() - lastTs * 1000) / 1000);
          setHtml("live-label", age <= 6 ? T['LIVE'] : fmt('{age}s ago', {age: age}));
          // Display the time of the last update, in the page's timezone.
          setHtml("last-update", fmtHMS(lastTs));
        }

        latest = result;
        latestTs = (typeof lastTs === 'number') ? lastTs : nowTs;
        pushHistory(latestTs, result);
        renderGeo(nowTs);
        renderDome(nowTs);
        renderPass(nowTs);
      } catch (e) {
        console.log(e);
      }
    }
    xhttp.onerror = function() {
      // A network-level failure (server unreachable, request blocked):
      // unlike the HTTP case there is no status to show.  A later
      // successful poll rewrites the badge to LIVE.
      setHtml("live-label", T['OFFLINE']);
    }
    xhttp.ontimeout = xhttp.onerror;
    try {
      xhttp.timeout = 1800;
      xhttp.open("GET", "$Extras.loop_data_file", true);
      xhttp.send();
    } catch (e) {
      console.log(e);
    }
  }
</script>
