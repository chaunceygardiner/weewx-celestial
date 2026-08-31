/* Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
   Distributed under the terms of the GNU Public License (GPLv3)
   See LICENSE for your rights.

   The Celestial page's live layer: the Geocentric dial and roster, the
   countdown chips, the sky dome's backdrop walk and satellite marks, the
   Next Visible Pass sweep, the LIVE badge -- everything the page does
   after it is generated.  One static file, shipped by the CopyGenerator
   like sky.js and version-tagged in the page's URL for it.

   It publishes exactly ONE global, `celestial`, with ONE method,
   `celestial.start(config)`.  The config is everything a report bakes --
   its [Extras] options, the station's latitude, the generation instant,
   the report's distance unit, language, body names, compass cardinals,
   [Texts] strings, satellites, comets, name and loop-data file -- built by
   user.celestial_page's config_script (the celestial tag) into the
   <script> block that calls start().  Nothing else here is per-report;
   through 8.5 all of it was one Cheetah include, `realtime_updater.inc`,
   that baked those values into the script itself.

   The page loads this file with a plain <script src>, NOT deferred, and
   calls start() from the top of <body>: the loop poll is armed before the
   panels below have parsed, so a first packet can land while the page is
   still streaming in (see renderWanted and domeRefetchWanted, which
   handle exactly that).

   Every render function returns at once when its root element is absent
   (#dial, #dome-svg, #pass-chart, the chips, the rosters), so a page
   holding any subset of the panels runs this one script unchanged.

   No color literal lives here: every color is a class in celestial.css
   (the dial's marks through their per-body fill and stroke classes), and
   the stylesheet's tokens are what a consumer restyles.  Nor may this
   comment contain a star-slash, which would end it here.  ES5 throughout --
   no arrow functions, no const, no classList -- and the reasons are given
   where the code depends on it. */
var celestial = (function () {
  // The version this file was shipped with; start() logs a mismatch
  // against the config's, which is the version of the Python that built
  // it.  A test keeps this literal in lockstep with the other version
  // sites.
  var CELESTIAL_JS_VERSION = '9.0';

  // ---- the report's configuration, set by start() -------------------------
  // These were the values realtime_updater.inc baked; they keep their
  // names so the code that reads them did not have to change.
  var page_update_pwd, refresh_rate, expiration_time, time_zone;
  var STATION_LAT;        // decides the moon disc's lit side (hemisphere flip)
  var GEN_TS;             // the instant the page was generated FOR, on the
                          // station's clock -- the same stamp the dome
                          // fragment carries as data-dome-ts, and the
                          // station clock's anchor before the first loop
                          // packet arrives (see serverNow)
  var PER_AU, DIST_LABEL; // distances arrive as raw au (weewx-loopdata
                          // almanac fields) and convert to the report's
                          // distance unit here
  var LOCALE;
  var BODY_LABELS;        // body names from the report's [Almanac] section
  var CARDINALS;          // the report formatter's compass ordinates, N E S W
  var T;                  // the [Texts] strings this script composes, keyed
                          // by their English
  var SAT_NAMES;          // the station's [Skyfield] [[Satellites]] tags
  var COMET_NAMES;        // ... and its [[Comets]] tags
  var REPORT_NAME;        // the report's own entry in loop_data_file
  var LOOP_DATA_FILE;
  var PAGE_THEME;         // the theme the page was generated on, 'dark' or
                          // 'light' -- what a refetched fragment's own
                          // report theme is compared with (pageThemeFlip)
  // (The fragment files the dome and the pass chart refetch are named
  // by the panels' own markup -- data-dome-prefix on #dome-svg,
  // data-pass-fragment on #pass-chart -- from the fragment set each
  // was rendered for, so a page embedding a set says its name once.)
  // Composed translations: look the English key up in T (falling back to
  // the key, so a missing or empty entry renders English) and fill the
  // {named} placeholders -- every occurrence, the value inserted
  // verbatim (split/join, not String.replace, whose replacement string
  // would interpret a '$' in a name).  celestial_page.py's _t fills the
  // first paint by the same rule, so the two paint the same bytes for
  // the same translation, misspelled placeholders included.  Javascript
  // key literals must spell non-ASCII with \u escapes to match
  // json.dumps' escaping of the generated object.
  function fmt(key, params) {
    var s = T[key] || key;
    for (var k in params) {
      s = s.split('{' + k + '}').join(String(params[k]));
    }
    return s;
  }
  // Markup-escaped text for what the feed or the report controls and
  // this script drops into innerHTML -- a satellite's, comet's or
  // shower's label, a compass ordinal -- the same rule the panels'
  // first paint applies (celestial_page's _esc).  [Texts] strings are
  // never escaped: they carry markup of their own by design.
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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
    // The badge is the page's chrome, not a panel, so a page in another
    // skin need not carry it -- and this is the one site that reaches it
    // directly rather than through the null-safe setHtml.  Unguarded, a
    // page without it threw here on every poll once the expiration timer
    // fired, for ever, and could never be clicked back to life.
    var liveLabel = document.getElementById("live-label");
    if (liveLabel === null) {
      return;
    }
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
    // 0 means NEVER expire, for a page whose host skin runs an expiry of
    // its own: two regimes on one page is worse than either, and a
    // consumer keeping its own badge has nowhere for CLICK-ME to appear
    // anyway.  (Before 9.0 this armed setTimeout(..., 0) and expired the
    // page instantly, so no station could have been relying on that.)
    if (expiration_time <= 0) {
      return;
    }
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
  // The poll interval is armed by start(), which the page's config block
  // calls at the top of <body>, so a first packet can land while the
  // rest of the page is still streaming in.  The renders that packet
  // triggers (updateCurrent)
  // are harmless on ids the parser has not reached -- setHtml is silent
  // -- but two of them, the countdown chips and the satellite rosters,
  // paint only on a NEW packet, never on the tick; on a dead feed that
  // re-serves its last file the gate never opens again, and the rosters
  // would wear the generated first paint for the life of the page while
  // the badge says the packet's time.  So a packet that lands during
  // parsing leaves this flag, and the load handler below re-runs the
  // five renders once, on `latest`, against the whole page.  Same idiom
  // as domeRefetchWanted for the backdrop.  A dead feed then keeps that
  // packet's paint, which is the doctrine.
  var renderWanted = false;
  function renderPacket(nowTs) {
    // The five paints a new packet calls for, in one place.  The packet
    // handler makes them; the load handler below re-makes them for a
    // packet that landed while the document was still parsing.  nowTs is
    // the BROWSER's clock -- renderDome measures the feed's age with it
    // against latestRecvTs, a stopwatch reading -- while the chips, the
    // rosters and the pass verdict take the station's from serverNow
    // themselves.
    renderCountdown();
    renderSatRosters();
    renderGeo();
    renderDome(nowTs);
    renderPass();
  }
  function renderOnLoad() {
    // Registered by start() after updateCurrent, so on a page whose
    // first packet came before load the handler chain renders it once
    // against the whole document.
    if (renderWanted && latest !== null) {
      renderWanted = false;
      try {
        renderPacket(Date.now() / 1000);
      } catch (e) {
        // addLoadEvent chains handlers by calling one after another with
        // no guard of its own, so a throw here would take every handler
        // registered AFTER this one with it -- including the backdrop's
        // deferred refetch, further down.  Every other render site is
        // wrapped; this one was not.
        console.log(e);
      }
    }
  }

  // ---- formatting helpers -------------------------------------------------
  function tzOptions(opts) {
    if (time_zone !== '') {
      opts.timeZone = time_zone;
    }
    return opts;
  }
  function fmtHMS(ts) {
    // The header's "updated" stamp: BYTE-IDENTICAL to the template's
    // first paint, which renders %H:%M:%S of the generation instant in
    // the station's zone, for the same reason as fmtHM below -- the
    // first packet must not reformat what the report painted.  (Under a
    // time_zone override the zone differs and so may the digits; the
    // shape is still the same.)  Through 8.3.4 this was
    // LOCALE-formatted (an English page read "03:11:22 PM"), which no
    // template can bake byte for byte across locales; 24-hour matches
    // the chip details beside it.
    return new Date(ts * 1000).toLocaleString('en-GB',
      tzOptions({hour: '2-digit', minute: '2-digit', second: '2-digit',
                 hour12: false}));
  }
  function fmtHM(ts) {
    // The countdown chips' event-time detail: BYTE-IDENTICAL to the
    // template's first paint, which renders %H:%M in the station's zone
    // -- the first live rewrite must not reformat what the report
    // painted (no seconds, no locale AM/PM: en-GB with hour12 off is
    // 24-hour HH:MM in every browser; under a time_zone override only
    // the zone, and so the digits, can differ).  The remaining-time
    // value above it is the hh:mm:ss-shaped number; the two must not
    // wear the same dress.
    return new Date(ts * 1000).toLocaleString('en-GB',
      tzOptions({hour: '2-digit', minute: '2-digit', hour12: false}));
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
  // How long without a NEW packet before the feed counts as dead, which
  // is a different question from how long a value may be extrapolated
  // and must not borrow its answer: a station whose loop packets are
  // minutes apart would then be declared dead between every pair of
  // them, and the dome would two-step -- marks tracking live, snapping
  // back to the backdrop's geometry with the satellite marker deleted,
  // then jumping forward on the next packet.  Derived from the poll
  // rate, which the manual tells users to match to weewx-loopdata's
  // write cadence, so twenty missed writes is the measure.  No
  // inference, no learning: a number from the configuration.
  var DEAD_FEED;                       // set by start(), from refresh_rate
  // There is deliberately NO threshold here for how old the page's clock
  // may be before the backdrop refetch stops trusting it to name a slot.
  // It is the obvious instrument and it is the wrong one, twice over: any
  // such threshold only bites when set BELOW the station's loop-write
  // interval, so on every driver slower than a couple of polls a healthy
  // page reads stale most of the time and refetches the whole sky to be
  // refused; and the fault it would guard grows WORSE as the clock gets
  // fresher, the overshoot being most of a cycle minus the clock's own
  // age.  There is no setting that is both cheap and safe.  See domeWant:
  // the slot is named from the station's clock against the archive
  // interval, which cannot name a sky the station has not reached, so
  // there is nothing left to distrust.
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
  var sunDialPt = null;   // the sun's dial point this render, the comet
                          // tails' anti-sunward anchor (null: no tail)
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
    // The grid is deliberately recessive: 2.05:1 inside 10 au, 1.74
    // outside, both short of the 3:1 a graphical object wants.  That is a
    // judgement, not an oversight.  The rings are not what carries the
    // scale -- the au label beside each one is at 5.78:1 and does not move
    // -- and a dial stops reading as a dial when its armature competes
    // with the dots.  Read as contrast ratio the lift over 8.1 looks
    // slight (1.20 -> 1.74); read as perceptual lightness, which is the
    // honest instrument this near black, it is 2.5x the step (dL* 7.4 ->
    // 18.9), because the ratio formula's flare term swamps everything at
    // this end.  Weight chosen by eye against the measured alternatives
    // (mockups/celestial-dial-contrast).
    for (var lg = -2; lg <= 5; lg++) {
      var rr = R_IN + (lg - LOG_MIN) / (LOG_MAX - LOG_MIN) * (R_OUT - R_IN);
      svgEl('circle', {cx: CX, cy: CY, r: rr, 'class': 'cel-geo-ring', fill: 'none',
                       'stroke-opacity': lg <= 1 ? 0.5 : 0.4}, dial);
      var rp = dialXY(157.5, rr);
      svgEl('text', {x: rp[0], y: rp[1] - 3, 'class': 'gridlab',
                     'text-anchor': 'middle'}, dial, ringLabels[lg + 2]);
    }
    svgEl('circle', {cx: CX, cy: CY, r: 296, 'class': 'cel-geo-rim', fill: 'none'}, dial);
    for (var d = 0; d < 360; d += 45) {
      var p1 = dialXY(d, 290), p2 = dialXY(d, 296);
      svgEl('line', {x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1],
                     'class': d % 90 === 0 ? 'cel-geo-tick cel-geo-tick-major' : 'cel-geo-tick'}, dial);
    }
    var cardinals = [[0, CARDINALS[0]], [90, CARDINALS[1]],
                     [180, CARDINALS[2]], [270, CARDINALS[3]]];
    for (var c = 0; c < cardinals.length; c++) {
      var pc = dialXY(cardinals[c][0], 310);
      svgEl('text', {x: pc[0], y: pc[1] + 4.5, 'class': 'cardinal',
                     'text-anchor': 'middle'}, dial, cardinals[c][1]);
    }
    svgEl('circle', {cx: CX, cy: CY, r: 9, 'class': 'cel-fill-earth cel-geo-earth'}, dial);
    svgEl('text', {x: CX, y: CY + 24, 'class': 'cel-earthlab'}, dial,
          BODY_LABELS['earth'] || 'Earth');
    var trailsG = svgEl('g', {}, dial);
    var marks = {};
    GEO_BODIES.forEach(function(key) {
      var segs = [];
      for (var i = 0; i < TRAIL_N; i++) {
        segs.push(svgEl('line', {'class': 'cel-trail cel-stroke-' + key,
                                 display: 'none'}, trailsG));
      }
      var g = svgEl('g', {display: 'none'}, dial);
      var m = {label: bodyLabel(key), g: g, segs: segs,
               glow: null, dot: null, lit: null, rim: null};
      // sky.js's document-level tap listener serves any mark owning a
      // <title> child; renderGeo keeps the text live.
      m.title = svgEl('title', {}, g, m.label);
      if (key === 'sun') {
        m.glow = svgEl('circle', {r: 13, 'class': 'cel-sunglow cel-fill-sun'}, g);
        m.dot = svgEl('circle', {r: 8, 'class': 'cel-geodot cel-fill-sun'}, g);
      } else if (key === 'moon') {
        // True-phase disc: dark disc, lit limb/terminator path, silver rim
        // (the rim keeps a new moon visible against the card).
        m.dot = svgEl('circle', {r: 8, 'class': 'cel-moon-dark'}, g);
        m.lit = svgEl('path', {'class': 'cel-moon-lit'}, g);
        m.rim = svgEl('circle', {r: 8, 'class': 'cel-moon-rim', fill: 'none'}, g);
      } else {
        m.dot = svgEl('circle', {r: 6.5, 'class': 'cel-geodot cel-fill-' + key}, g);
      }
      m.lab = svgEl('text', {'class': 'bodylab'}, dial, m.label);
      marks[key] = m;
    });
    // The comet marks: a diamond with an anti-sunward tail fan and the
    // planets' one-hour trail, one per configured comet.  Same mark
    // anatomy as the bodies (group + <title> child for sky.js taps,
    // label parented to the dial); the diamond is a <path> repositioned
    // by rewriting its d each render, the three tail rays carry
    // skyfield's fixed per-ray opacity and get their endpoints per
    // render (weewx-skyfield's _comet_tail geometry, ported).
    COMET_NAMES.forEach(function(key) {
      var segs = [];
      for (var i = 0; i < TRAIL_N; i++) {
        segs.push(svgEl('line', {'class': 'cel-trail cel-stroke-comet',
                                 display: 'none'}, trailsG));
      }
      var g = svgEl('g', {'class': 'cel-geocomet', display: 'none'}, dial);
      var m = {label: satLabel(key), g: g, segs: segs,
               glow: null, dot: null, lit: null, rim: null, rays: []};
      m.title = svgEl('title', {}, g, m.label);
      var rayOpacity = ['0.55', '0.9', '0.55'];
      for (var ri = 0; ri < 3; ri++) {
        m.rays.push(svgEl('line', {'class': 'comet-tail',
                                   'stroke-width': 1.2,
                                   'stroke-opacity': rayOpacity[ri],
                                   display: 'none'}, g));
      }
      m.dot = svgEl('path', {'class': 'cel-cometdot'}, g);
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
  function drawTrail(segs, azNow, auNow, altNow, azRate, auRate, altRate) {
    // The trail: the last hour of motion at the derived rates, drawn
    // backward from now (real observed positions replace nothing here --
    // the rates ARE observed, so the wake is the true recent path to
    // first order).  Hidden until motion can be derived.  On this dial
    // the angle is azimuth, so everything -- planets and comets alike --
    // sweeps at the sky's diurnal rate and earns the same wake.
    var haveRates = (azRate !== null && auRate !== null && altRate !== null);
    var step = TRAIL_SEC / TRAIL_N;
    for (var i = 0; i < TRAIL_N; i++) {
      var seg = segs[i];
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
      // The wake fades from a visible FLOOR, not from nothing: ramping
      // straight off zero put the oldest segments at 1.02:1, an hour of
      // trail no eye can find.  The newest segment carries the motion and
      // is the one that has to read (4.58:1 above the horizon).
      seg.setAttribute('stroke-opacity',
                       (0.2 + 0.8 * (i + 1) / TRAIL_N) * (altB < 0 ? 0.42 : 0.75));
    }
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
  // Through 8.5 this script ran at window scope, where a `var history`
  // silently failed to bind (the browser's read-only History object) and
  // every use of it threw or read navigation state; the function scope
  // this file now lives in closes that class of bug, and the ring keeps
  // the name it was given to survive it.
  var latest = null;      // last parsed loop-data object
  var latestTs = 0;       // its current.dateTime.raw; never the browser's time
  var latestRecvTs = 0;   // when THIS BROWSER received it (its own clock)
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
      row.className = below ? 'cel-row cel-below' : 'cel-row';
    }
  }
  function renderGeo() {
    if (latest === null) {
      return;
    }
    if (dialMarks === null) {
      dialMarks = buildDial();
    }
    // Extrapolate at the derived rates between loop refreshes, re-anchoring
    // to truth on every packet.  The interval is the stopwatch reading
    // since the packet arrived (packetAge -- never the browser's clock
    // minus the station's, which would extrapolate a skewed viewer's page
    // to the cap and hold it there); stale data stops advancing after
    // EXTRAP_MAX seconds so a dead feed cannot drift the page into fiction.
    var dt = packetAge();
    // The moon's phase, for its dial disc: percent full plus waxing
    // (the next full moon precedes the next new moon).
    var moonFrac = num(latest, 'almanac.moon.phase');
    // Pinned spellings since 7.6, which the skin's own declaration
    // uses; the bare .raw keys stay as fallbacks for a `moon` group of
    // your own in the report's stanza that overrides the skin's with
    // the unpinned spellings.
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
    sunDialPt = null;        // re-captured below when the sun has data
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
      if (key === 'sun') {
        sunDialPt = p;       // valid below the horizon too, like
      }                      // skyfield's own dome tail anchor
      m.dot.setAttribute('cx', p[0]);
      m.dot.setAttribute('cy', p[1]);
      if (key === 'moon') {
        if (moonFrac !== null && m.lit !== null) {
          m.lit.setAttribute('d', moonPath(p[0], p[1], 8, moonFrac / 100.0, litLeft));
        }
        m.rim.setAttribute('cx', p[0]);
        m.rim.setAttribute('cy', p[1]);
        m.g.setAttribute('class', below ? 'cel-geomoon cel-below' : 'cel-geomoon');
      } else {
        var cls = 'cel-geodot cel-fill-' + key + (below ? ' cel-below cel-stroke-' + key : ' cel-ring');
        m.dot.setAttribute('class', cls);
      }
      if (m.glow !== null) {
        m.glow.setAttribute('cx', p[0]);
        m.glow.setAttribute('cy', p[1]);
        m.glow.setAttribute('display', below ? 'none' : '');
      }
      m.lab.setAttribute('class', below ? 'bodylab cel-dim' : 'bodylab');
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
      drawTrail(m.segs, azNow, auNow, altNow, azRate, auRate, altRate);
    });
    renderComets(dt);
  }
  function renderComets(dt) {
    // The comets, drawn AFTER the bodies so sunDialPt is this render's:
    // the exact planet pipeline (guarded reads, ring-long rates, roster
    // cells, below-horizon dimming, the one-hour trail), with a diamond
    // marker in place of the dot -- solid when naked-eye bright
    // (mag <= 6), the hollow inversion when fainter or when magnitude
    // is honestly absent (an MPC row without g/k parameters) -- and a
    // three-ray tail fanning away from the sun's dial point.  A comet
    // whose fields read null across the surface (MPC dropped it) renders
    // ABSENCE: no diamond, no tail, no trail, empty roster cells.
    COMET_NAMES.forEach(function(key) {
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
      var m = dialMarks === null ? null : dialMarks[key];
      if (!m) {
        return;
      }
      m.label = satLabel(key);
      m.lab.textContent = m.label;
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
      m.dot.setAttribute('d',
          'M ' + p[0].toFixed(1) + ',' + (p[1] - 5).toFixed(1) +
          ' L ' + (p[0] + 5).toFixed(1) + ',' + p[1].toFixed(1) +
          ' L ' + p[0].toFixed(1) + ',' + (p[1] + 5).toFixed(1) +
          ' L ' + (p[0] - 5).toFixed(1) + ',' + p[1].toFixed(1) + ' Z');
      var mag = num(latest, 'almanac.' + key + '.mag');
      var bright = (mag !== null && mag <= 6.0);
      m.g.setAttribute('class', below ? 'cel-geocomet cel-below' : 'cel-geocomet');
      m.dot.setAttribute('class',
          'cel-cometdot' + (bright ? '' : ' cel-faint') + (below ? ' cel-below' : ''));
      // The tail: three rays fanning ANTI-SUNWARD -- away from the sun's
      // own dial point (the sun sits on this plan view like any body;
      // radially-outward is sun-centered orrery logic and wrong here).
      // Skipped when the sun is off the dial this render or degenerately
      // close, skyfield's own guard.
      var ux = null, uy = null;
      if (sunDialPt !== null) {
        var dx = p[0] - sunDialPt[0], dy = p[1] - sunDialPt[1];
        var dn = Math.sqrt(dx * dx + dy * dy);
        if (dn > 1.0) {
          ux = dx / dn;
          uy = dy / dn;
        }
      }
      var rayGeom = [[-0.18, 9.0], [0.0, 12.0], [0.18, 9.0]];
      for (var ri = 0; ri < 3; ri++) {
        var ray = m.rays[ri];
        if (ux === null) {
          ray.setAttribute('display', 'none');
          continue;
        }
        var ca = Math.cos(rayGeom[ri][0]), sa = Math.sin(rayGeom[ri][0]);
        var rx = ux * ca - uy * sa, ry = ux * sa + uy * ca;
        ray.removeAttribute('display');
        ray.setAttribute('x1', (p[0] + 6.0 * rx).toFixed(1));
        ray.setAttribute('y1', (p[1] + 6.0 * ry).toFixed(1));
        ray.setAttribute('x2', (p[0] + (6.0 + rayGeom[ri][1]) * rx).toFixed(1));
        ray.setAttribute('y2', (p[1] + (6.0 + rayGeom[ri][1]) * ry).toFixed(1));
      }
      m.lab.setAttribute('class', below ? 'bodylab cel-dim' : 'bodylab');
      var tip = m.label + ' \u00B7 ' +
          (below ? T['below horizon']
                 : fmt('alt {alt}\u00B0', {alt: altNow.toFixed(1)})) +
          ' \u00B7 ' +
          fmt('{dist} au',
              {dist: auNow >= 1000 ? auNow.toFixed(1) : auNow.toFixed(6)});
      if (mag !== null) {
        tip += ' \u00B7 ' + fmt('mag {mag}', {mag: mag.toFixed(1)});
      }
      m.title.textContent = tip;
      placeBodyLabel(m.lab, azNow, r);
      drawTrail(m.segs, azNow, auNow, altNow, azRate, auRate, altRate);
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
  // max(60 s, interval/10) spacing): the fetch asks for the slot
  // covering the station's time, so the sky steps a quarter degree
  // instead of lurching a full cycle's rotation at once.  The set
  // self-describes through the fragment wrapper's data-dome-ts/-slot/
  // -step/-count/-interval, so any archive interval works unconfigured.
  //
  // Which slot is wanted is a question about the STATION's clock and the
  // archive interval only (domeWant) -- never about the fragment the
  // page happens to be holding, whose cycle may already be the previous
  // one.  A fetch goes out only when the wanted slot is not the one on
  // the page, so a page in step spends no requests; the check runs on
  // every loop packet, since the packet is the only thing that moves the
  // clock, and DOME_REFRESH remains as the backstop for what no packet
  // reaches (a pre-stagger backdrop, a failed fetch to retry).  The
  // chart keeps the old cadence: it is a fixed future scene, not a
  // rotating sky.
  var DOME_REFRESH = 60;       // seconds between backdrop refetches
  var CHART_REFRESH = 300;     // seconds between pass-chart refetches
  var DOME_BODIES = ['sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter',
                     'saturn', 'uranus', 'neptune'];
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
    // the same drop-in idiom as the 7.6 moon keys.  Null before the
    // first packet, like everything else read from the feed.
    if (latest === null) {
      return null;
    }
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
    if (document.readyState === 'loading') {
      // The dome may be half-parsed: a first packet from the interval
      // poll can land while the document is still streaming (see
      // refreshDome).  Baselines read now would miss every body the
      // parser has not reached, and stand incomplete until a fragment
      // is next APPLIED -- up to a minute on a page inside slot 0's
      // minute, whose deferred refetch is refused as the same sky --
      // and a live satellite mark appended now lands under layers
      // parsed after it.  Nothing here touches a dome the parser is
      // still filling; the next tick, after parsing, does it all.
      // The pass chart's readPassBase has the same guard.
      return;
    }
    if (domeChecked && !domeAsking(nowTs) && domeStaleFor() !== null) {
      restoreDomeMarks(svg);
      // domeChecked, so the freeze and the line that explains it begin
      // together: acting on a suspicion the page has not yet tested
      // would leave a visibly stopped dome with nothing under it saying
      // why, for as long as the first refetch takes.
      //
      // The backdrop stopped advancing, so the whole dome layer freezes
      // -- bodies and satellites together.  Nudging live marks across a
      // star field that is no longer moving manufactures a sky that
      // never existed, and the error grows at 15 degrees an hour with no
      // bound; frozen, the marks and the stars around them stay in the
      // relation the almanac drew them in, honestly old.  It is the
      // doctrine EXTRAP_MAX applies one layer down -- a stale source
      // freezes rather than drifts -- and updateDomeStale says so under
      // the panel, naming the fault.  Nothing else on the page is
      // affected: the dial, the roster, the countdown chips and the pass
      // panel stand on the loop feed, not on the backdrop, and they go
      // on moving.  The first fragment that lands clears this by
      // itself.
      return;
    }
    if (latestRecvTs > 0 && nowTs - latestRecvTs > DEAD_FEED) {
      // Both sides of this comparison are the BROWSER's clock -- the
      // receipt stamp, not the packet's station timestamp.  Mixing them
      // reintroduced exactly what 8.3.1 removed: a viewer two minutes
      // ahead of the station would read every healthy packet as a dead
      // feed, for ever, with no line under the panel to say why.
      //
      // The other input dying is the same lie inverted, and the comment
      // in domeStaleFor used to get this wrong.  When the FEED stops,
      // latestTs stops with it, so the station clock this page judges by
      // stops too: the backdrop goes on arriving, m.ts runs past that
      // frozen clock, the difference goes negative and the dome can
      // never be called stale again.  Meanwhile the nudge loop below
      // keeps drawing bodies at their last known place plus EXTRAP_MAX
      // of extrapolation, on a star field that is still advancing --
      // a current sky wearing hour-old marks.  So the marks go back to
      // the backdrop's own geometry here too.  No second line under the
      // panel: the LIVE badge already owns the feed's fault, the same
      // reasoning that keeps the backdrop's fault off the badge.
      restoreDomeMarks(svg);
      return;
    }
    domeRestored = false;    // the live layer is running; a later freeze restores again
    if (domeBase === null) {
      readDomeBase();
    }
    var dt = packetAge();
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
        setShown(b.g, false);
        setShown(b.lab, false);
        return;
      }
      setShown(b.g, true);
      setShown(b.lab, true);
      var p = domeXY(azNow, altNow);
      var tr = 'translate(' + (p[0] - b.x).toFixed(1) + ' ' + (p[1] - b.y).toFixed(1) + ')';
      b.g.setAttribute('transform', tr);
      if (b.lab !== null) {
        b.lab.setAttribute('transform', tr);
      }
    });
    renderSats(svg);
  }
  // The live satellite layer: our own marker (dot + name), created
  // inside the current backdrop and rebuilt after every swap.  Feature
  // detection is key PRESENCE: a loop feed without the
  // satellite keys (older skyfield, no [[Satellites]], a station not
  // re-installed since its satellites changed) leaves the static dome
  // untouched; keys present but null mean
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
            dot: svgEl('circle', {r: 4, 'class': 'cel-satdot'}, g),
            lab: svgEl('text', {'class': 'satlab'}, g)};
  }
  function localDayNum(ts) {
    // The instant's DISPLAY-ZONE calendar date, as a day number to
    // difference.  Never new Date(...).getDate(): that reckons in the
    // BROWSER's zone, and this page renders in the station's.
    var parts = new Intl.DateTimeFormat('en-US',
      tzOptions({year: 'numeric', month: '2-digit', day: '2-digit'}))
      .formatToParts(new Date(ts * 1000));
    var v = {};
    for (var i = 0; i < parts.length; i++) {
      v[parts[i].type] = parts[i].value;
    }
    return Math.floor(Date.UTC(v.year, v.month - 1, v.day) / 86400000);
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
    // Whole days is a CALENDAR-day difference, not elapsed seconds
    // divided down: renderPassRow puts this count on the same line as
    // the pass's own date (fmtDayHM), and a count reckoned any other
    // way contradicts the date beside it twice a day -- rounding up
    // calls a pass later this evening 'in 1 day' (Jacques Terrettaz's
    // report against weewx-skyfield's chips, the 2026-08-12 partial
    // solar eclipse, issue #6), rounding down calls one just past
    // midnight 'today'.  Differencing the two local dates also costs
    // nothing to be DST-correct: the day a clock shifts is still one
    // day.  The floor at 1 is that Sunday's belt and braces -- 24
    // elapsed hours can land back on today's date, and this branch
    // has already ruled out anything under a day.
    var n = Math.max(1, localDayNum(riseTs) - localDayNum(nowTs));
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
      // Not declared at all: the report-time first paint
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
                  {rise: esc(riseOrd), alt: maxAlt.toFixed(0), culm: esc(culmOrd),
                   set: esc(setOrd), m: Math.round(dur / 60).toString()});
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
  function renderSatRosters() {
    // The two countdown rows per satellite, one per table (present only
    // when the report almanac served them; setHtml is a no-op
    // otherwise): the dome's next pass of ANY kind, visibility-tagged,
    // and the Next Pass panel's next visible pass.
    //
    // These live OUT here, called from the poll (they read the page's
    // clock, which moves only with a packet), because they are pure
    // loop-feed arithmetic and have nothing to do with the backdrop.
    // They used to sit inside renderSats, which the dome's
    // stale freeze skips -- so a station whose fragments stopped serving
    // got a frozen roster beside a countdown chip that kept counting,
    // the two contradicting each other about the same pass (8.3.2).  The
    // rule the page states everywhere else holds here too: only what
    // stands on the backdrop freezes with it.
    if (latest === null) {
      return;
    }
    // A pass's rise and set are the station's instants, so the now they
    // are measured against is the station's too (serverNow), never the
    // viewer's: satWhen's "overhead now" / "in {n} days" and the day
    // count that names the calendar day both read it.
    var nowTs = serverNow();
    SAT_NAMES.forEach(function(name) {
      if (!hasKey('almanac.' + name + '.az')) {
        return;              // not in the loop feed: first paint stands
      }
      var sunlit = latest['almanac.' + name + '.sunlit'];
      renderPassRow('almanac.' + name + '.next_pass',
                    'sat-any-line-' + name, 'sat-any-pass-' + name,
                    T['no pass in the coming week'], sunlit, nowTs, true);
      renderPassRow('almanac.' + name + '.next_visible_pass',
                    'sat-line-' + name, 'sat-pass-' + name,
                    T['no visible pass in the coming week'], sunlit, nowTs,
                    false);
    });
  }
  function restoreDomeMarks(svg) {
    // Put every mark back where the backdrop drew it, once, as the
    // freeze engages.  Freezing in place is not enough: the marks may
    // have been nudged first -- a page restored from cache takes its
    // first packet before the first refetch answers, and that one nudge
    // jumps a body from its generated position to its true one, which
    // against an hours-old star field can be most of the sky.  Frozen
    // there for ever, the dome would stand permanently in exactly the
    // state the freeze exists to prevent, with this function's own
    // comment promising the opposite.  Undoing the nudge is undoing a
    // translate, so removing the attribute restores the almanac's own
    // geometry; the live satellite marks are removed outright and the
    // generated ones come back out from under them.
    if (domeRestored) {
      return;
    }
    domeRestored = true;
    // Both attributes, on every mark, unconditionally.  The nudge does
    // two things: it moves a mark, and it HIDES one that has set since
    // the backdrop was drawn ("set since generation" above).  A hidden
    // body carries no transform, so a transform-only restore left it
    // hidden for ever -- a frozen plate showing a daytime sky with no
    // sun in it, which is the same lie as a mark in the wrong place.
    // Removing an attribute a mark never had is a no-op, and the
    // generated backdrop emits neither (checked: zero display
    // attributes in a rendered dome), so the wide selector costs
    // nothing and cannot hide what the almanac meant to draw.  Found by
    // the liveseasons port's review.
    // Array.prototype.forEach.call, not NodeList.forEach: this file is
    // ES5 throughout -- no arrow functions, no const, no classList --
    // and the block below deliberately supports engines too old for
    // XHR2's onloadend.  Those same engines have no NodeList.forEach, so
    // the tidier spelling would throw inside renderDome, which localTick
    // calls with no try/catch: every tick after the dome went stale
    // would abort there, for the life of the page (renderPass runs
    // ahead of it in the tick since 8.3.3, so it would survive; the
    // point stands).
    Array.prototype.forEach.call(
        svg.querySelectorAll('g.dome-body, text[data-body]'),
        function(e) {
          e.removeAttribute('transform');
          e.removeAttribute('display');
        });
    if (satMarks !== null) {
      SAT_NAMES.forEach(function(name) {
        var m = satMarks[name];
        if (m && m.g && m.g.parentNode !== null) {
          m.g.parentNode.removeChild(m.g);
        }
        // (the generated marks were un-hidden by the sweep above)
      });
      satMarks = null;
    }
  }
  function renderSats(svg) {
    if (satMarks === null) {
      satMarks = {};
    }
    var dt = packetAge();
    SAT_NAMES.forEach(function(name) {
      var azKey = 'almanac.' + name + '.az';
      var altKey = 'almanac.' + name + '.alt';
      if (!hasKey(azKey)) {
        return;              // not in the loop feed: static dome stands
      }
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
      // The marker's own read of the sunlit flag.  It used to ride along
      // with the roster rows' copy; those moved out to renderSatRosters
      // in 8.3.2 and this one has to stay here, where it is used.
      var shadowed = (latest['almanac.' + name + '.sunlit'] === false);
      var daylight = (sunAlt !== null && sunAlt >= -6);
      m.dot.setAttribute('class', 'cel-satdot' + (shadowed ? ' cel-shadow' : '')
                                           + (daylight ? ' cel-faint' : ''));
      m.lab.setAttribute('class',
                         (shadowed || daylight) ? 'satlab cel-faint' : 'satlab');
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
    // is what turns it back into a cycle base, and since 8.3.5 into the
    // record PHASE (see domeWant).  Computing the walk from ts directly
    // made the next slot RELATIVE to whichever slot was showing -- the
    // dome stepped 0,2,1,3,2, visibly zigzagging in the NOAA-21 live
    // capture.
    //
    // Falling back to 0 is the RIGHT answer for the case that fires on
    // every page load: the wrapper the page bakes around its own dome
    // carries no data-dome-slot, because that dome is the cycle instant
    // itself -- slot 0 by construction.  A refetched fragment always
    // carries one.  The out-of-range half of the test is the guess: a
    // hand-edited or truncated attribute costs a phase wrong by a
    // multiple of the step, which moves the wanted slot but cannot ask
    // for a sky ahead of the station (the base is floored to at or
    // before the clock either way), and the next fragment that parses
    // puts it right.
    var slot = parseInt(d.getAttribute('data-dome-slot'), 10);
    if (!isFinite(slot) || slot < 0 || slot >= count) {
      slot = 0;
    }
    // The archive interval, which is the report cycle's own length and
    // the quantum every cycle base is a multiple of.  NOT step*count:
    // a set counts the fragments it writes, which is a ceil, so on an
    // interval the step does not divide the product OVERSTATES the cycle
    // -- 350 s writes six 60 s slots, and 360 is past the boundary the
    // station puts at 350 -- and a page computing with it would still be
    // inside a cycle the station had left.  The product is the fallback
    // for a wrapper generated before 8.3.5 wrote this attribute, where
    // the count was floor-divided instead: exact for every interval that
    // divides, and short of the true interval rather than past it for
    // one that does not.
    var interval = parseFloat(d.getAttribute('data-dome-interval'));
    if (!isFinite(interval) || interval <= 0) {
      interval = step * count;
    }
    return {ts: ts, step: step, count: count, slot: slot, interval: interval};
  }
  function domeWant(m) {
    // The fragment the page SHOULD be showing: the slot covering the
    // station's own clock, in the cycle the station is in NOW.
    //
    // The base comes from that clock, not from the fragment on the page.
    // Deriving it from the fragment (ts - slot*step, through 8.3.4) was
    // the root of the whole family of faults this replaces: moments
    // after the station rolls to a new cycle the page is still holding
    // the previous one, so the base was a cycle stale, and the late slot
    // it named was answered out of the CURRENT cycle -- the filename
    // carries a slot number and no cycle identity, so the station cannot
    // tell which cycle was meant.  The page then displayed a sky most of
    // a cycle into the future, applied because it was newer, and held it
    // until the true time caught up.  8.3.4 fenced that off with a
    // clock-age threshold, which cost a whole-sky refetch most minutes
    // on any station whose loop writes were slower than the threshold,
    // and could flip-flop two fetches per packet on a slow link.
    //
    // The station's clock names the base, with nothing to remember: a
    // report cycle is generated for the last ARCHIVE RECORD (weewx's
    // report engine passes no gen_ts, so the generator falls back to
    // lastGoodStamp), and archive records land one interval apart.
    //
    // One interval apart, but not necessarily ON a multiple of it.
    // SOFTWARE record generation computes record times as
    // int(t/interval)*interval, which is an epoch multiple by
    // construction; a HARDWARE logger stamps them on its OWN boundaries,
    // by its own clock, so they can sit at a constant offset from that
    // grid -- a console in a half-hour UTC zone writing hourly records.
    // Assuming a zero phase would be worse than wrong on a station that
    // is not: the wanted slot would come out one too high, the reply
    // would be stamped ahead of the page's clock, the ceiling in the
    // response handler would refuse it, and the sky would step at half
    // rate or stand still.
    //
    // So the phase is read off the fragment on the page -- its own cycle
    // base is ts - slot*step -- while the CYCLE still comes from the
    // clock.  That distinction is the whole fix: the phase is a property
    // of the STATION's records, identical whether the fragment is
    // current or a cycle old, so taking it from a stale fragment is
    // safe, whereas taking the cycle from one is the fault this all
    // exists to prevent.  (An interval change or a console clock resync
    // moves the phase; the page carries the old one for one cycle, and
    // the ceiling still refuses anything ahead meanwhile.)
    //
    // What the phase does NOT correct -- because nothing here can -- is
    // a station whose records are stamped ahead of its own loop packets,
    // a console clock out of true against weewxd's system time.  A
    // remainder modulo the interval cannot see an offset of a whole
    // interval and cannot undo one of any size, and there is nothing to
    // undo it WITH: the page has one clock, the packet's own stamp, and
    // a fragment stamped past it is indistinguishable from the sky out
    // of the next cycle that the ceiling exists to refuse.  Such a
    // station freezes rather than draw a sky its own clock says has not
    // happened yet, and the line under the plate names that fault by its
    // own kind (domeStaleWhy) instead of accusing a station that is
    // generating backdrops perfectly.
    var phase = ((m.ts - m.slot * m.step) % m.interval + m.interval) % m.interval;
    var base = Math.floor((serverNow() - phase) / m.interval) * m.interval + phase;
    var k = Math.floor((serverNow() - base) / m.step);
    // A set covers its whole interval unless it runs out of fragments:
    // there are ten templates and no more, so an interval longer than
    // ten steps -- 605 s, whose ten 60 s slots reach 600 -- leaves a
    // tail no slot depicts, and a clock inside it names a k of 10
    // against a count of 10.  That tail is served by the last slot.
    // (Before 8.4 every non-dividing interval had one, because the
    // count was floor-divided while the set wrote the extra fragment
    // anyway: a 350 s station declared five 60 s slots, and the sixth it
    // had written was unaskable.)
    if (k < 0) {
      k = 0;
    } else if (k > m.count - 1) {
      k = m.count - 1;
    }
    // ts is at or behind serverNow() by construction -- which is what
    // makes a sky ahead of the station unaskable, and is relied on by
    // the ceiling in the response handler.
    return {k: k, ts: base + k * m.step};
  }
  // Where the fragments are: the generator writes a set into its
  // directory under the report's HTML_ROOT, and the config block
  // carries this page's route up to HTML_ROOT (root: '../' per
  // directory level, from core's filename tag, which the page passes to
  // config_script) -- so a page may sit anywhere under HTML_ROOT and
  // the skin may keep its assets anywhere; nothing here is inferred.
  // The panel's markup carries the set's directory (data-dome-dir,
  // data-pass-dir).  A page that passed no filename has root '' and
  // fetches relative to itself, right when it sits beside its set.
  var FRAGMENT_ROOT = '';
  function fragmentUrl(dir, name) {
    return FRAGMENT_ROOT + (dir ? dir + '/' : '') + name;
  }
  // A fragment fetch that came back wrong -- an HTTP error, or a body
  // that is not a fragment (a server's fallback page for an unknown
  // path) -- earns one console line per kind naming the URL asked, so
  // a set written where the page is not looking is a line in the
  // console, not a sky that quietly stops moving.
  var fragWarned = {};
  function warnFragmentOnce(kind, url, why) {
    if (fragWarned[kind]) {
      return;
    }
    fragWarned[kind] = true;
    console.warn('celestial: the ' + kind + ' fragment ' + url + ' ' + why);
  }
  var domePrefixWarned = false;
  function domeFragName(k) {
    // The set's files, named by the swap target the panel rendered
    // (data-dome-prefix).  No attribute, no name: the panel is
    // contracted to emit it, and a default here would refetch one
    // set's files under another set's first paint -- the fault the
    // attribute exists to end.  null means fetch nothing.
    var wrap = document.getElementById('dome-svg');
    var prefix = wrap === null ? null : wrap.getAttribute('data-dome-prefix');
    if (prefix === null || prefix === '') {
      if (wrap !== null && !domePrefixWarned) {
        domePrefixWarned = true;   // once, not once a minute
        console.warn('celestial: #dome-svg carries no data-dome-prefix; the dome is not refetched');
      }
      return null;
    }
    return k >= 1 ? prefix + '-' + k + '.txt' : prefix + '.txt';
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
  var lastDomeFetch = 0;         // when the last refetch went out
  var lastDomeWant = 0;          // the depicted time the last one asked for
  var domeStaleGrace = 0;        // hold the frozen line until this instant
  var domeRestored = false;      // has the freeze already undone the nudges
  var domeChecked = false;       // has any refetch attempt completed yet
  var domeFetchInFlight = false; // is one out on the wire right now
  // The theme this page was generated on (PAGE_THEME, from the config
  // block -- the report's own resolution, so the page's markup owes the
  // script nothing) compared with the report's theme each refetched
  // fragment carries (data-page-theme, on the dome's wrapper and the
  // pass chart's alike): on theme = auto the report cycle that crosses
  // sunrise regenerates the page on the other plate, and the open page
  // must follow it -- a paper page under night chrome, or the reverse
  // at sunset, would otherwise stand until somebody reloaded, which on
  // a dashboard left open is never.  So the page reloads itself, ONCE
  // per plate per fragment kind: the report has already regenerated,
  // and this is the report-cycle flip the manual promises.  Once only
  // -- if a cached page keeps disagreeing, one stale plate beats a
  // reload loop.  The fragment SET's own plate (data-dome-palette /
  // data-pass-palette) takes no part: a set on a plate other than the
  // page's is styled by its own attribute and is never a flip.  A
  // fragment without data-page-theme (a hand-made one) is simply
  // applied.
  function pageThemeFlip(text, kind) {
    var tm = /data-page-theme="([a-z]+)"/.exec(text);
    if (tm !== null && tm[1] !== PAGE_THEME) {
      if (!plateReloadTried(kind, tm[1])) {
        markPlateReload(kind, tm[1]);
        window.location.reload();
        return true;
      }
    } else if (tm !== null) {
      clearPlateReload(kind);  // in step -- so the next flip gets its own reload
    }
    return false;
  }
  // The reload guard has to OUTLIVE the reload -- an in-page flag is
  // reset by the very navigation it is meant to bound, so a page served
  // from cache would reload every DOME_REFRESH seconds for ever.
  // sessionStorage remembers which plate we already reloaded to reach;
  // if the page comes back still wearing the other one, that is a stale
  // cached page, not a flip, and one stale plate beats a reload loop.
  // The in-page flag is the fallback where storage throws (private
  // modes, file:// origins).  One guard PER FRAGMENT KIND ('dome',
  // 'pass'): two judges share the page, and a dome in step must not
  // clear the mark a stale pass chart set, or that chart would reload
  // the page on every one of its refetches until the next good cycle.
  // Once ever per plate per kind, and no expiry: a page that keeps
  // coming back on the other plate (a stale copy behind a proxy) wears
  // it, rather than reloading every few minutes for ever.  The page and
  // its fragments take the same record as their instant -- the fragment
  // generator uses the cycle's own, which the page's generator found
  // as the last good stamp unless a record committed while it ran --
  // so they agree short of that, and there is no race worth an expiry.
  var PLATE_KEY = 'celestial-plate-reload-';   // + the fragment kind
  var plateReloaded = {};
  function plateReloadTried(kind, want) {
    try {
      return window.sessionStorage.getItem(PLATE_KEY + kind) === want;
    } catch (e) {
      return plateReloaded[kind] === want;
    }
  }
  function markPlateReload(kind, want) {
    plateReloaded[kind] = want;
    try {
      window.sessionStorage.setItem(PLATE_KEY + kind, want);
    } catch (e) {
      // storage unavailable; the in-page flag bounds this page's life
    }
  }
  function clearPlateReload(kind) {
    delete plateReloaded[kind];
    try {
      window.sessionStorage.removeItem(PLATE_KEY + kind);
    } catch (e) {
      // nothing to clear
    }
  }
  var domeRefetchWanted = false; // asked for while the document was still parsing
  function refreshDome() {
    if (pageTimedOut) {
      return;
    }
    if (document.readyState === 'loading') {
      // The document is still streaming in.  A first packet can arrive
      // now -- the poll interval is armed at script eval, and the dome
      // is a couple of hundred kilobytes further down the page -- and
      // a fetch made now would be judged and applied against a dome
      // that is absent or, worse, half-parsed: the response handler
      // would find no wrapper and throw the fragment away (with
      // domeChecked set, so a cached page could then freeze and post
      // the frozen line against a healthy station until the next
      // interval), or find a wrapper the parser is still filling and
      // replace its children under it.  So remember that a refetch is
      // owed, and let the load handler below make it, once the whole
      // page has parsed.  The first packet is what gets here; on a very
      // slow link the interval can too, and so can the wake handler (a
      // background tab switched to while still streaming).
      domeRefetchWanted = true;
      return;
    }
    if (document.getElementById('dome-svg') === null) {
      return;              // no dome panel on this page: nothing to refetch
    }
    var meta = domeFragMeta();
    var want = meta === null ? null : domeWant(meta);
    if (want !== null && want.ts <= meta.ts) {
      // The sky on the page IS the one the station's clock asks for:
      // nothing is owed, so nothing is fetched.  This is the whole
      // bandwidth story -- a page in step with its station spends no
      // requests at all, on any driver, and the fetches that do go out
      // are one per slot the sky advances.  It is also what makes the
      // ceiling in the response handler safe: a page whose clock has
      // stopped (a dead feed, a sleep before the first packet back)
      // computes the slot it is already showing and never asks, so the
      // legitimately-ahead answer to a blind ask cannot arise.
      return;
    }
    if ((want === null || want.ts === lastDomeWant)
        && Date.now() / 1000 - lastDomeFetch < DOME_REFRESH) {
      // The same unmet want as last time: pace it.  A want that has
      // MOVED is always asked at once -- that is the packet-driven step
      // this design exists for -- but a want that has not can repeat for
      // a long time, and this check now runs on every packet rather than
      // once a minute.  A station LATE writing a cycle the page's clock
      // has already entered answers each ask with the previous cycle's
      // file, refused as older, leaving the want unmet: without this the
      // page would pull a whole sky every refresh_rate seconds until the
      // report landed.  A pre-stagger backdrop has no want to compare
      // and is paced the same way, which is the interval it always had.
      // Measured on the browser's stopwatch: it is an elapsed time, and
      // the station's clock is exactly what has stopped in some of these
      // cases.
      return;
    }
    if (domeFetchInFlight
        && Date.now() / 1000 - lastDomeFetch < 2 * DOME_REFRESH) {
      // One at a time: on resume the overdue interval callback and the
      // wake handler both come due, and the guard on lastDomeFetch only
      // covers the second of them.  The backward-step guard hides the
      // symptom; this removes it.
      //
      // Bounded, though.  The flag is cleared by onloadend and by the
      // onload/onerror/ontimeout trio -- all XHR2, and the timeout that
      // guarantees one of them fires is XHR2 as well.  On an engine
      // without any of it a hung connection would latch the flag and
      // stop the dome refetching forever, which is far worse than the
      // duplicate fetch this guard exists to prevent.  After two
      // refresh intervals we ask again regardless.
      return;
    }
    // A pre-stagger backdrop (no self-description) has no slot set to
    // walk: ask for slot 0 each interval, exactly as before the stagger.
    var fragName = domeFragName(want === null ? 0 : want.k);
    if (fragName === null) {
      return;              // the swap target names no set: nothing to fetch
    }
    var fragUrl = fragmentUrl(
      document.getElementById('dome-svg').getAttribute('data-dome-dir'), fragName);
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
      // Anything but a fresh SVG keeps the dome we already have: a failed
      // fetch (including a 404 from a pre-stagger server), an empty
      // fragment (no capable almanac this cycle, or a slot beyond the
      // interval), or junk.  Keeping it is right -- a blank dome helps
      // nobody -- but the outcome is remembered: if this goes on long
      // enough for the sky to be visibly wrong, domeStaleWhy turns it
      // into the reason under the panel.
      domeChecked = true;
      clearInFlight();
      if (this.status !== 200 && this.status !== 0) {
        warnFragmentOnce('dome', fragUrl, 'came back HTTP ' + this.status);
        domeFetchProblem = {kind: 'http', status: this.status, file: fragName};
        return;
      }
      if (!/\S/.test(this.responseText)) {
        // An empty fragment is its own answer, and it is worth naming.
        // Sometimes it is deliberate -- a slot whose offset falls beyond
        // the archive interval renders empty by design, which a page
        // holding an older cycle's count will ask for after the interval
        // is shortened.  Sometimes it means the station is writing
        // nothing at all: no capable almanac this cycle, or the
        // group_interval arithmetic that emptied every slot for Jacques
        // Terrettaz in issue #4.  The page cannot tell those apart, but
        // it can say which file came back empty, which is the fact that
        // sends a reader to the right place -- and it is emphatically
        // not "not a sky fragment", which reads as garbage.
        domeFetchProblem = {kind: 'empty', file: fragName};
        return;
      }
      if (this.responseText.indexOf('<svg') === -1) {
        warnFragmentOnce('dome', fragUrl, 'is not a sky fragment');
        domeFetchProblem = {kind: 'junk', file: fragName};
        return;
      }
      // A backdrop arrived and parses.  Whatever happens to it below --
      // applied, or refused as identical or backward -- the fetch side
      // is healthy, and a sky that goes stale from here is a station
      // that has stopped writing new fragments.
      domeFetchProblem = null;
      var wrap = document.getElementById('dome-svg');
      if (wrap === null) {
        return;
      }
      // The page's theme first (see pageThemeFlip): a fragment from a
      // report regenerated on the other plate reloads the page, once.
      if (pageThemeFlip(this.responseText, 'dome')) {
        return;
      }
      // The same slot of the same cycle (a late report re-serving what
      // we already show) is a no-op: swapping identical content would
      // only churn the baselines.
      var m = /data-dome-ts="([0-9.]+)"/.exec(this.responseText);
      var ident = fragName + '|' + (m === null ? '' : m[1]);
      if (ident === appliedDomeFrag) {
        // A repeat of the last APPLIED fragment.  For a stamped fragment
        // the same-or-older guard below would refuse it anyway (its
        // stamp is the dome's own); this remains for a fragment with no
        // data-dome-ts, or a page whose wrapper lost its meta, where the
        // guard has nothing to compare and the name alone must serve.
        return;
      }
      // Never step the sky backward, and never re-inject the sky already
      // showing: data-dome-ts is the instant a fragment depicts (cycle
      // base + slot * step, unique per slot of a cycle), so a fragment
      // stamped the same as the dome on the page IS that dome -- a
      // refetch inside slot 0's minute of a fresh page, or a late report
      // re-serving the slot we show -- and swapping it in would only
      // throw away the mark baselines, unhide the generated satellite
      // marks until the next tick and re-parse a whole sky for nothing.
      // Older is the late cycle answering the slot-0 ask with the
      // PREVIOUS cycle's file, whose sky the page already stepped past.
      // Either way keep what is showing; the walk asks again next
      // minute.  Judged against the DOM at this instant, on purpose:
      // 8.3.2 through 8.3.4 seeded the applied identity from
      // the dome in a load handler and compared against that memory
      // here, which held only while nothing could ask for a fragment
      // before the seed had run -- and the first-packet refetch below,
      // fired from an interval poll on a page still streaming its dome,
      // could.  A comparison that reads the page has no such ordering to
      // get right.
      // ...and never step it FORWARD past the station either.  The ask
      // names a slot number and the station answers it out of whatever
      // cycle it currently holds, so a cycle that rolls between the
      // page's clock and the reply comes back as that slot of the NEW
      // cycle -- a sky the station has not reached.  The wanted slot's
      // depicted time is at or behind serverNow() by construction
      // (domeWant), so anything past it was answered from a cycle the
      // page did not mean.  Keep what is showing; the next check asks
      // again with a base that has caught up, and the sky is a slot
      // behind for a minute instead of four minutes ahead for four.
      // Safe only because refreshDome does not ask on a stopped clock:
      // otherwise the correct answer to a page waking after hours --
      // the current cycle, far ahead of a clock that has not moved --
      // would be refused here and the dome would freeze awake.
      var cur = domeFragMeta();
      if (m !== null && parseFloat(m[1]) > serverNow()) {
        // Ahead of the station's own clock.  Recorded, and only this
        // half is: a roll caught mid-fetch lands here once and clears on
        // the next apply, long before the sky is stale enough for the
        // line to post, whereas a station whose records run ahead of its
        // loop packets lands here every single time and would otherwise
        // be accused of not generating backdrops at all.
        //
        // Judged without reference to the dome on the page, unlike the
        // backward half below: "ahead of this page's clock" is a
        // property of the reply alone, so it holds for the blind slot-0
        // ask a page with no readable meta makes as well.  On a healthy
        // station it cannot fire -- the cycle is generated for an
        // archive record, which is older than the packets the clock is
        // read from.
        domeFetchProblem = {kind: 'ahead', file: fragName};
        return;
      }
      if (cur !== null && m !== null && parseFloat(m[1]) <= cur.ts) {
        // Backward or identical: normal at a late cycle, resolves
        // itself, and says nothing about the station's health.
        return;
      }
      appliedDomeFrag = ident;
      wrap.innerHTML = this.responseText;
      hideSkytip();
      domeBase = null;       // baselines belong to the old backdrop
      satMarks = null;       // the live layer's elements were replaced too
      domeRestored = false;  // a fresh sky is live again until it is not
      var swapTs = Date.now() / 1000;
      updateDomeStale(swapTs);   // a fresh sky clears the frozen line at once
      if (latest !== null) {
        renderDome(swapTs);
      }
    };
    xhttp.onerror = function() {
      // A network-level failure: unreachable, blocked, offline.  Unlike
      // the HTTP case there is no status to show.
      domeChecked = true;
      clearInFlight();
      domeFetchProblem = {kind: 'net', file: fragName};
    };
    xhttp.ontimeout = xhttp.onerror;
    xhttp.onloadend = function() {
      domeFetchInFlight = false;
      // No re-ask here.  Through 8.3.4 this compared the slot the fetch
      // was for against the slot the clock named on completion, because
      // a fetch begun on a stale clock had asked for the wrong one --
      // and since the name depended on a freshness flag that flipped
      // twice per loop interval, not on the slot number alone, a station
      // whose fetches outlasted the threshold re-asked on every
      // completion: two whole skies per packet, for ever, from a
      // comment that said it could not loop.  There is no freshness flag
      // now, and every caller re-derives the wanted slot from the
      // station's clock before asking, so a slot boundary crossed during
      // a fetch is picked up by the next packet.
    };
    // ...and on each individual completion too.  onloadend is the one
    // XHR2-era handler in this block, and the timeout note below is
    // explicit about engines old enough to lack such things: without
    // this, a browser with no onloadend latches the flag on its first
    // fetch and never refetches the dome again.
    var clearInFlight = function() {
      domeFetchInFlight = false;
    };
    try {
      // A timeout is what makes ontimeout above mean anything: without
      // one, a server that accepts the connection and never answers
      // leaves the request hanging for ever -- no onload, no onerror, so
      // the reason stays whatever it last was (null, after any earlier
      // success) and the line blames the station for a network fault.
      // Generous next to the loop feed's 1800 ms: this is a whole sky,
      // not a small json file.
      // Cache-busted: the fragment is a static file and heuristic browser
      // caching would happily serve a stale sky.
      lastDomeFetch = Date.now() / 1000;
      lastDomeWant = want === null ? 0 : want.ts;
      xhttp.open('GET', fragUrl + '?ts=' + Date.now(), true);
      // AFTER open(): older engines throw InvalidStateError on a timeout
      // set against an unopened request, and this whole block is inside
      // a try whose catch would swallow it -- costing the refetch
      // entirely on exactly the browsers least able to spare it.
      //
      // Thirty seconds, because this is a whole sky: a rendered fragment
      // measures about 140 KB on a real station, and ten meant every
      // refetch over a slow mobile link timed out, recorded "no
      // response" against a perfectly healthy station, and never
      // recovered -- the timeout being far shorter than the interval
      // that would have retried it.  Still well inside one refresh
      // cycle, so a hung connection stays bounded.
      xhttp.timeout = 30000;
      // Raised only once the request is built and open: set any earlier
      // and a throw from domeFragName or the XHR constructor would leave
      // it stuck, and every later refetch -- interval and wake alike --
      // would return at the guard for the life of the page.
      domeFetchInFlight = true;
      xhttp.send();
    } catch (e) {
      // A request that cannot be issued at all -- a security or URL
      // error, a page opened off file:// -- is as much a fault as one
      // that comes back 404, and it must COUNT as having asked:
      // otherwise domeChecked stays false for the life of the page, the
      // freeze never engages and no line ever posts, which is silently
      // the behaviour this release replaced.
      domeFetchInFlight = false;
      domeChecked = true;
      domeFetchProblem = {kind: 'net', file: fragName};
      console.log(e);
    }
  }
  // And once when the first loop packet lands (updateCurrent), which is
  // the moment the page learns what time it is.  The HTML can be minutes
  // or hours older than the fragments beside it -- a page served from a
  // browser or CDN cache is the ordinary case, which is why the
  // fragments are cache-busted at all -- so waiting for the first
  // interval would freeze the dome and post the line for a whole minute
  // before the first refetch silently corrected it.  Not at load,
  // though, as 8.3.2 through 8.3.4 did: before a packet the clock is
  // GEN_TS, which always names slot 0 -- the very sky the page was
  // generated with -- so a load-time fetch bought a fresh page nothing,
  // and on a page opened mid-cycle it left the slot-0 backdrop up to
  // (count - 1) steps behind until the interval came round; and a fetch
  // still on the wire when the packet arrived would have blocked the
  // packet's own refetch through the in-flight guard.  A page with no
  // feed fetches NOTHING -- its clock never leaves GEN_TS, which names
  // the slot already showing, so the interval finds nothing owed every
  // time it comes round.  Deliberate: no feed, no live layer, and the
  // LIVE badge is where that is reported.  8.3.4's interval kept asking
  // for slot 0 and following the report cycles; this does not.
  // The grace below covers the moment between load
  // and that first refetch going out, as it does for a page waking up.
  // A refetch that returns the sky the page already shows -- slot 0
  // inside its own minute -- is a no-op by the same-or-older guard in
  // the response handler, which reads the dome on the page at the
  // moment of comparison; nothing is seeded at load, so nothing depends
  // on load order (start() is called from the TOP of <body>, the dome
  // hundreds of lines below, and a poll from the interval it armed can
  // answer before either has parsed -- in which case refreshDome
  // defers, and this handler makes the refetch it owes).
  function refetchDomeOnLoad() {
    if (domeRefetchWanted) {
      domeRefetchWanted = false;
      refreshDome();
    }
  }

  // A laptop closed and reopened, or a tab left in the background and
  // brought forward: the timers stopped with the machine, and on the way
  // back the loop feed catches up within its two seconds while the
  // backdrop would wait for the next minute boundary.  That is up to a
  // minute of live marks moving over an hour-old star field -- the very
  // thing this release is about -- so a page that becomes visible
  // refetches at once, rather than at the interval's convenience.  The
  // DOME_REFRESH guard keeps a much-flipped tab from fetching per
  // switch.  (The pass chart is left to its own five minutes: it is a
  // fixed future scene, and being minutes old tells no lie.)
  function domeWake() {
    // The dome is stale by definition on the way back from a sleep, and
    // the fetch that fixes it is already in flight: hold the frozen line
    // for a few seconds rather than flash an accusation at a station
    // doing nothing wrong.
    // The grace FIRST, and unconditionally: on a real resume the overdue
    // interval callback often runs before this does, taking the fetch
    // and setting lastDomeFetch -- so the guard below would return
    // without granting it, and the line would flash for that fetch's
    // whole round trip.  The grace is about the resume, not about who
    // happened to send the request.
    domeStaleGrace = Date.now() / 1000 + 5;
    if (Date.now() / 1000 - lastDomeFetch < DOME_REFRESH) {
      return;                    // a much-flipped tab must not fetch per switch
    }
    refreshDome();
  }

  // ---- a backdrop that stopped advancing -----------------------------------
  // Every one of refreshDome's failure paths keeps the sky it has and
  // says nothing, which is right for a minute or two and wrong for an
  // hour: the star field stands still while the live marks go on moving,
  // and the page draws a sky that never existed.  So the backdrop's age
  // is watched, the dome freezes when it goes stale (renderDome), and
  // this line under the panel says so -- with the REASON, because "the
  // sky stopped" leaves a reader nowhere to go.  The three faults that
  // land here are told apart by the last refetch's outcome: fragments
  // not served (an HTTP status), fragments served but unreadable or
  // empty, no answer at all -- and, when the fetch side is perfectly
  // healthy, a station that has stopped writing new ones.  That last
  // case is the one no status code would ever reveal.
  var domeFetchProblem = null;   // last refetch outcome; null = healthy
  var domeStaleShown = '';       // what the line currently says ('' = none)
  function domeStaleFor() {
    // How many seconds the backdrop is stale BY, or null when it is
    // current.  Its depicted time (data-dome-ts) is the honest measure:
    // that is the instant the marks are being drawn against.  The limit
    // is three report cycles, floored at ten minutes -- one skipped
    // cycle is routine, two is a hiccup, three means nothing is coming
    // -- where a cycle is the fragment set's own declared span, which is
    // the archive interval.  This skin does not support a report_timing
    // that makes its reports slower than that (the manual says so
    // plainly): a page cannot tell a throttled report apart from a stopped
    // one without inferring it, and every attempt to infer it mistook a
    // sleep, an outage, a cached page or a hand-run report for a cadence.
    // A pre-stagger backdrop (no
    // self-description) is exempt: there is nothing to judge it by, and
    // the walk already treats it as slot 0 for ever.
    var m = domeFragMeta();
    if (m === null) {
      return null;
    }
    // Judged by the STATION's clock, not the viewer's: the station
    // writes these fragments and its loop packets carry its own time, so
    // comparing the two takes the viewer's clock out of the question
    // entirely -- a kiosk with no NTP can be an hour out, and judging by
    // it would freeze a perfectly healthy sky and post a frozen line
    // over it.  Before the first packet serverNow is GEN_TS, the very
    // stamp the baked backdrop carries, so the judgement is undecidable
    // and answers "current" (8.3.4 let the browser's clock decide here,
    // the one place it still could); the first packet's refetch corrects
    // a stale-cached page, and the first packet judges.  A page that
    // never gets one is never corrected and never judged: with no packet
    // the clock stays at GEN_TS, which names the slot the page already
    // shows, so no fetch is owed and none goes out.  That is the
    // doctrine, not an oversight -- a station whose loop feed is not
    // working has no live layer at all, and the LIVE badge is where that
    // fault is reported (John, 2026-08-17).  When a
    // feed DIES its clock stops with it, so this stops firing -- which
    // is right for THIS test: a stopped clock cannot judge, and the
    // dead-feed case is handled where it belongs, in renderDome, which
    // puts the marks back rather than pinning them to a sky that goes
    // on turning underneath them.
    var over = (serverNow() - m.ts)
               - Math.max(600, 3 * m.interval);
    return over > 0 ? over : null;
  }
  function packetAge() {
    // How long the current packet has been in hand, by the stopwatch:
    // both readings are the BROWSER's own clock, so a viewer's skew
    // cancels exactly and never reaches the arithmetic.  Capped at
    // EXTRAP_MAX so a feed that dies freezes the page rather than
    // running it on into fiction.
    return Math.min(Math.max(Date.now() / 1000 - latestRecvTs, 0), EXTRAP_MAX);
  }
  function serverNow() {
    // THE clock of this page, and the station's: the last loop packet's
    // own timestamp -- the instant every value in that packet was
    // computed for -- and before the first packet the instant this page's
    // baked data is for (GEN_TS).  Nothing in between: a clock carried
    // forward by the browser's stopwatch (8.3.4) matched no data on the
    // page and stepped BACK by up to a poll whenever a packet arrived
    // later than the one before it, and the browser's own calendar
    // (8.3.3 and earlier) needed a freshness test and a latch to police
    // a fallback that could be wrong by hours.  So the page's time
    // advances at loop cadence and stops when the feed does -- a station
    // whose loop feed is not working has no working live layer, and the
    // LIVE badge is where that fault is reported (John, 2026-08-16).
    // The browser is asked only how long something took (packetAge and
    // the fetch throttles: a difference between two of its own readings,
    // immune to any skew), never what time it is.
    //
    // Consequently nothing that reads this clock is repainted by a timer
    // -- the countdown chips, the satellite rosters and the pass verdict
    // render as packets arrive (updateCurrent) -- because between two
    // packets it would paint the same value again, and it would reach a
    // new packet's value up to a second late.  Timers remain only for
    // extrapolated MOTION (renderGeo, renderDome, renderPass's sweep, on
    // packetAge) and for elapsed-time housekeeping (the tick-gap wake,
    // the dome-stale line, the fetch throttles).
    //
    // A page loaded onto a feed that died BEFORE the page was generated
    // gets a first packet OLDER than GEN_TS, and this clock steps back
    // to it: the chips, the stamp, the dial and the dome all repaint
    // from that stale packet.  Deliberate -- the packet is the station's
    // last word and the badge reads its age ("Ns ago") beside it; the
    // alternative, max(GEN_TS, latestTs), is a clock that matches no
    // packet, which is what this release removed.
    return latestTs === 0 ? GEN_TS : latestTs;
  }
  function domeStaleWhy() {
    var p = domeFetchProblem;
    // Every one through fmt (T[key] || key), never a bare T[...] lookup:
    // a key that drifts by one character from its Python source then
    // renders "(undefined)" instead of falling back to English, and the
    // tests -- which assert the English text a matching key also
    // produces -- would not see it.
    if (p === null) {
      return fmt('no newer backdrop has arrived', {});
    }
    // The FILE that failed, not the family's base name: the walk is
    // usually on a numbered slot, and an rsync that dropped those while
    // keeping dome-svg.txt would otherwise send a reader to the one file
    // being served perfectly.
    var file = p.file || 'dome-svg.txt';
    if (p.kind === 'http') {
      return fmt('{file} returns HTTP {status}', {file: file, status: p.status});
    }
    if (p.kind === 'net') {
      return fmt('no response for {file}', {file: file});
    }
    if (p.kind === 'empty') {
      return fmt('{file} is empty', {file: file});
    }
    if (p.kind === 'ahead') {
      // Not the station's fault: it answered, and the answer was for a
      // time this page's own clock has not reached.
      return fmt("{file} is stamped ahead of the station's clock",
                 {file: file});
    }
    return fmt('{file} is not a sky fragment', {file: file});
  }
  function fmtBackdropWhen(ts, refTs) {
    // The backdrop's own time, to the minute -- seconds would be noise
    // on a sky that has not moved for an hour.  The DATE comes along
    // once the backdrop is not from the reference clock's own day: a
    // report cycle stalled overnight would otherwise say "from 12:00"
    // of a day it never names.  Intl does the wording, so this costs no
    // translation.
    var d = new Date(ts * 1000);
    var opts = {hour: '2-digit', minute: '2-digit'};
    if (new Date(refTs * 1000).toLocaleDateString(LOCALE, tzOptions({}))
        !== d.toLocaleDateString(LOCALE, tzOptions({}))) {
      opts.month = 'short';
      opts.day = 'numeric';
    }
    return d.toLocaleString(LOCALE, tzOptions(opts));
  }
  function domeAsking(nowTs) {
    // "The page is still asking, so it is not yet answering."  A fetch
    // on the wire, or the few seconds' grace after a load or a wake,
    // holds back a verdict that has not been reached -- but never
    // retracts one already given, or a hung server would blink the
    // explanation off and on beneath a dome that never moves.
    //
    // The FREEZE consults this too, and must: gating only the line left
    // a page restored from cache standing visibly frozen with nothing
    // underneath it for as long as the grace ran, which is the silence
    // this release exists to end.  Freeze and explanation begin
    // together, or neither does.
    return (domeFetchInFlight || nowTs < domeStaleGrace)
           && domeStaleShown === '';
  }
  function updateDomeStale(nowTs) {
    if (pageTimedOut) {
      // A page past expiration_time has deliberately stopped fetching,
      // so it has no standing to say the station is not writing
      // backdrops -- the same accusation-without-asking the domeChecked
      // gate prevents, reached from the other end.  The badge already
      // says CLICK-ME, which is the honest account of this state.
      return;
    }
    // Runs on the one-second tick, but its verdict reads the page's
    // clock, which moves only with a loop packet -- so a page that has
    // never received one cannot call its backdrop stale (GEN_TS never
    // gets ahead of a backdrop's stamp), and a feed that dies freezes
    // this judgement with it.  In both the LIVE badge names the fault,
    // and it is the instrument that owns it.  The tick is for the fetch
    // outcomes and the wake grace, which do not depend on the clock, and
    // the line repaints only on a change.
    var el = document.getElementById('dome-stale');
    if (el === null) {
      return;                    // no dome on this page
    }
    var msg = '';
    // domeChecked, because the no-fault reason -- fetches fine, nothing
    // newer being written -- is a claim about the station that this page
    // cannot make before its first refetch has come back.  A page
    // restored from cache with an old backdrop would otherwise post it
    // within the first second, having asked nobody.  Bounded by the
    // fetch's own timeout, after which some outcome is recorded.
    //
    // The FREEZE consults the same two conditions (renderDome), so the
    // dome and the line explaining it begin together.  If you are here
    // to make them agree, they already do -- see domeAsking.
    // A request on the wire holds back a line that has not been shown
    // yet -- the wake grace is five seconds and a fetch may take ten, so
    // a slow sky over a slow link would otherwise flash the accusation
    // in the gap between them.  It does NOT retract a line already
    // standing: against a server that hangs for the full ten seconds
    // every minute, that would blink the explanation off and on beneath
    // a dome that never moves, which is worse than either state.  The
    // freeze has no such gate, and the two must agree.
    // Neither an in-flight fetch nor a wake grace retracts a line that
    // is already standing: on a dead station, a tab flip would otherwise
    // blank the explanation for five seconds under a dome that never
    // moves.  Both only hold back a line that has yet to appear.
    if (domeChecked && !domeAsking(nowTs) && domeStaleFor() !== null) {
      // The key's em dash is spelled with its \u escape, matching
      // json.dumps' escaping of the generated T object.
      msg = fmt('Star field frozen \u2014 this sky is from {time} ({why})',
                {time: fmtBackdropWhen(domeFragMeta().ts, serverNow()),
                 why: domeStaleWhy()});
    }
    if (msg === domeStaleShown) {
      return;                    // no churn: this line changes rarely
    }
    domeStaleShown = msg;
    setHtml('dome-stale-msg', msg);
    el.hidden = (msg === '');
  }

  // ---- the next-pass chart -------------------------------------------------
  // The chart is skyfield 2.0's pass_chart_html: the sky at the soonest
  // visible pass's culmination, the arc dashed across it, the featured
  // satellite's own dot at the arc's peak (a dome-body group -- the same
  // consumer contract as the dome's marks, under the chart's own SVG
  // ids).  During the pass itself the chart's epoch is within minutes of
  // now, so nudging that ONE dot from the live alt/az -- and flipping
  // its ring/solid look from the live sunlit flag -- is epoch-honest;
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
    // skyfield): nothing sweeps, the chart stands as drawn.  The
    // baseline also records the dot's generated look -- fill, stroke,
    // and the data-sunlit hook's verdict -- so the sweep can flip and
    // restore it (passDotLit below) -- and the pass's OWN window,
    // data-rise/data-set on the track (skyfield 2.3.2), null on an
    // older chart.
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
    var ds = g.getAttribute('data-sunlit');
    passBase = {tag: tag, g: g, c: c,
                lab: svg.querySelector('text[data-body="' + tag + '"]'),
                x: parseFloat(c.getAttribute('cx')),
                y: parseFloat(c.getAttribute('cy')),
                fill: c.getAttribute('fill'),
                stroke: c.getAttribute('stroke'),
                genLit: ds === null ? null : ds !== '0',
                // Freshly read from the chart, so it IS as the station
                // drew it: see passStandsAsDrawn, which restores that
                // state and must not rewrite it every tick to do so.
                asDrawn: true,
                rise: attrNum(track, 'data-rise'),
                set: attrNum(track, 'data-set')};
  }
  function attrNum(el, name) {
    // A numeric attribute, or null when absent or not a number.
    var v = parseFloat(el.getAttribute(name));
    return isFinite(v) ? v : null;
  }
  function setShown(el, shown) {
    // Show or hide one SVG element by its display attribute; null-safe.
    //
    // Written only when the state actually CHANGES.  setAttribute
    // records a mutation whether or not the value differs, and hiding is
    // what the steady states do: past a pass's set renderPass hides the
    // dot and its label on every tick and returns, so an unconditional
    // write costs two attribute mutations a second until the chart is
    // refetched.  Same class as the asDrawn latch, on the other branch
    // -- and the latch cannot cover this one, because a hidden mark is
    // deliberately NOT the drawn state.  removeAttribute needs no such
    // test: removing an attribute that is not there records nothing.
    if (el === null) {
      return;
    }
    if (shown) {
      el.removeAttribute('display');
    } else if (el.getAttribute('display') !== 'none') {
      el.setAttribute('display', 'none');
    }
  }
  function passMarkShown(b, shown) {
    // The dot and its name label move as one: a label left standing
    // alone is the ghost name renderSats guards against.  An open tap
    // chip on the mark is left to the next tap or fragment swap, as
    // every other panel's hidden marks leave theirs -- sky.js has one
    // chip for the whole page, and dismissing it here would take a chip
    // the viewer opened on Jupiter because Terra set.
    if (!shown) {
      // Hidden is not the drawn state, so the next restore must do its
      // work rather than trust the flag.
      b.asDrawn = false;
    }
    setShown(b.g, shown);
    setShown(b.lab, shown);
  }
  function passStandsAsDrawn(b) {
    // The chart is a prediction: the dot at its generated position, in
    // its generated look, shown.
    //
    // Restored ONCE, not on every tick.  renderPass runs every second,
    // and two of its branches end here -- the hours before a pass rises,
    // and an older chart's whole out-of-window stretch -- so without this
    // guard the same six attribute writes went out a second apart, for
    // hours, to a chart nothing had touched.  (8.3.4 removed exactly that
    // churn from the no-packet branch; these two kept it.)  The flag is
    // cleared by everything that departs from the drawn state, so a mark
    // that really has moved or hidden is always restored.
    if (b.asDrawn) {
      return;
    }
    b.asDrawn = true;
    b.g.removeAttribute('transform');
    passDotLit(b, b.genLit);
    if (b.lab !== null) {
      b.lab.removeAttribute('transform');
    }
    passMarkShown(b, true);
  }
  function passDotLit(b, lit) {
    // Solid vs hollow ring on the chart's dot.  The generator draws a
    // shadowed satellite as the exact fill/stroke inversion of a sunlit
    // one, so the two looks are the recorded generated pair and its
    // swap -- no color knowledge of skyfield's chart palette needed,
    // and no CSS coupling.  Without the data-sunlit hook (an older
    // chart) the dot stands as drawn.
    if (b.genLit === null || b.fill === null || b.stroke === null) {
      return;
    }
    if (lit === b.genLit) {
      b.c.setAttribute('fill', b.fill);
      b.c.setAttribute('stroke', b.stroke);
    } else {
      b.c.setAttribute('fill', b.stroke);
      b.c.setAttribute('stroke', b.fill);
    }
  }
  function renderPass() {
    if (passSvg() === null) {
      return;
    }
    if (passBase === null) {
      if (document.readyState === 'loading') {
        return;                // the chart may be half-parsed: no baseline yet
      }
      readPassBase();
    }
    var b = passBase;
    if (b.tag === null) {
      return;
    }
    if (latest === null) {
      // No packet, so no position to sweep to -- the dot's az and alt
      // come from the feed, and no clock however good supplies them --
      // and no verdict either: serverNow is GEN_TS, the instant the
      // chart was drawn for.  The chart therefore stands exactly as the
      // station drew it, untouched: the dot at the culmination, under the
      // pass it names.  A page opened mid-pass, or just after one, shows
      // that until the first packet lands -- normally refresh_rate
      // seconds later, but for as long as the feed stays down, since
      // nothing else here can set `latest`.  A station whose loop feed is
      // not working has no working pass panel either; John's ruling of
      // 2026-08-16, and what lets the verdict below be a plain
      // comparison of two station-written times with nothing remembered
      // and nothing to police.  (8.3.4 restored the drawn state here on
      // every tick -- six attribute writes a second on a chart nothing
      // had touched.)
      return;
    }
    // The window the chart is judged against is the chart's OWN --
    // data-rise/data-set on the track, skyfield 2.3.2 -- because the
    // feed's next_visible_pass rolls on to the FOLLOWING pass moments
    // after this one sets.  8.0 through 8.3.2 judged against the feed:
    // at the set instant the mark, having just ridden the arc to its
    // end, was put back at its generated position -- the culmination,
    // MID-ARC -- under a header still naming the finished pass, and
    // stayed there until the next refetch brought the next chart
    // (NOAA-21's Aug 15 capture, f0498 at 02:58:35 exactly).  With the
    // chart's own times there is nothing to remember: past the set the
    // pass this chart depicts is over, whether or not the page was
    // watching when it ended.  Both sides of the comparison are written
    // by the station -- the chart's times by the report, the instant by
    // serverNow -- so the verdict cannot flip with the viewer's clock
    // and has nothing to latch.  An older chart without the attributes
    // falls back to the feed's window and 8.3.2's behavior -- restoring
    // the drawn chart outside the window, the roll-back and all -- on
    // this same clock; no better and no worse.
    var now = serverNow();
    if (b.rise !== null && b.set !== null) {
      if (now >= b.set) {
        // Over.  Hide the mark and its label, exactly as the dome does
        // with a satellite that has set; the arc, the header and the
        // rest of the chart stand until the next refetch replaces them.
        passMarkShown(b, false);
        return;
      }
      if (now < b.rise) {
        passStandsAsDrawn(b);
        return;
      }
    } else {
      var rise = numOr('almanac.' + b.tag + '.next_visible_pass.rise.unix_epoch.raw',
                       'almanac.' + b.tag + '.next_visible_pass.rise.raw');
      var setTs = numOr('almanac.' + b.tag + '.next_visible_pass.set.unix_epoch.raw',
                        'almanac.' + b.tag + '.next_visible_pass.set.raw');
      if (rise === null || setTs === null || now < rise || now >= setTs) {
        passStandsAsDrawn(b);
        return;
      }
    }
    var az = num(latest, 'almanac.' + b.tag + '.az');
    var alt = num(latest, 'almanac.' + b.tag + '.alt');
    if (az === null || alt === null) {
      // Nothing to sweep from.  A dot never yet swept stands as drawn;
      // one already on the arc holds its last position rather than
      // snapping back to the culmination for a single null packet.
      if (!b.g.hasAttribute('transform')) {
        passStandsAsDrawn(b);
      }
      return;
    }
    var dt = packetAge();
    var azNow = (az + (recentRateOf('almanac.' + b.tag + '.az', true) || 0) * dt + 360) % 360;
    var altNow = alt + (recentRateOf('almanac.' + b.tag + '.alt', false) || 0) * dt;
    if (altNow <= 0) {
      // The in-progress window's first and last seconds can dip below
      // the rim: hide rather than pin, like the dome's marks.
      passMarkShown(b, false);
      return;
    }
    passMarkShown(b, true);
    // Mid-ride the ring/solid state is the satellite's LIVE state, the
    // dome's own toggle (renderSats above): 8.0 shipped the sweeping dot
    // wearing the culmination's sunlit state all pass, so the two panels
    // disagreed whenever the satellite crossed the shadow line mid-pass
    // (NOAA-21's Aug 8 shadow culmination wore the ring from rise while
    // the dome showed the live shadow entry).  Only when the feed
    // carries the key: a feed without it keeps the chart as drawn.
    var sl = latest['almanac.' + b.tag + '.sunlit'];
    if (sl !== undefined) {
      passDotLit(b, sl !== false);
    }
    var p = domeXY(azNow, altNow);
    var tr = 'translate(' + (p[0] - b.x).toFixed(1) + ' ' + (p[1] - b.y).toFixed(1) + ')';
    // Swept off the drawn position -- and the lit toggle just above may
    // have left the drawn look too.  Both are undone by the next
    // passStandsAsDrawn, which needs to know it has work to do.
    b.asDrawn = false;
    b.g.setAttribute('transform', tr);
    if (b.lab !== null) {
      b.lab.setAttribute('transform', tr);
    }
  }
  function refreshPass() {
    if (pageTimedOut) {
      return;
    }
    // The chart names its own fragment (data-pass-fragment, the set's
    // file); no chart on this page, nothing to refetch.
    var target = document.getElementById('pass-chart');
    var fragName = target === null ? null : target.getAttribute('data-pass-fragment');
    if (fragName === null || fragName === '') {
      return;
    }
    var fragUrl = fragmentUrl(target.getAttribute('data-pass-dir'), fragName);
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
      var wrap = document.getElementById('pass-chart');
      var chart = document.getElementById('pass-wrap');
      // The section around the panel (id pass-sec) is the page's own
      // chrome and optional: the bundled page hides it when the panel
      // has nothing to show at all.
      var sec = document.getElementById('pass-sec');
      if (this.status !== 200 && this.status !== 0) {
        warnFragmentOnce('pass', fragUrl, 'came back HTTP ' + this.status);
        return;              // a failed fetch keeps the chart we have
      }
      if (wrap === null || chart === null) {
        return;
      }
      // The page's theme first, as for the dome -- and before the
      // emptiness test, because the pass chart is refetched on pages
      // that carry no dome, and an EMPTY chart (no pass in window) still
      // arrives in its wrapper, carrying the theme: the flip must reach
      // such a page while it waits for a pass.
      if (pageThemeFlip(this.responseText, 'pass')) {
        return;
      }
      if (this.responseText.indexOf('<svg') === -1) {
        // A well-formed EMPTY fragment is meaningful -- no visible pass
        // among the configured satellites: bare (as the 8.x templates
        // wrote it) or an empty .passfrag wrapper (9.0).  The chart area
        // hides; the roster's honest rows keep the section up, which
        // hides only when it has no roster either.  Junk keeps the chart
        // we have.
        if (!/\S/.test(this.responseText) ||
            /^\s*<div class="passfrag"[^>]*>\s*<\/div>\s*$/.test(this.responseText)) {
          wrap.innerHTML = '';
          hideSkytip();
          chart.setAttribute('hidden', '');
          // ... unless the section holds something else to show: a
          // roster, or a line the page put there (a refused set, an
          // undeclared panel) -- the same rule pass_panel_hidden applies
          // at first paint.
          if (sec !== null && sec.querySelector('.cel-roster, .cel-skyhint') === null) {
            sec.setAttribute('hidden', '');
          }
          passBase = null;
        } else {
          warnFragmentOnce('pass', fragUrl, 'is not a pass-chart fragment');
        }
        return;
      }
      wrap.innerHTML = this.responseText;
      hideSkytip();
      chart.removeAttribute('hidden');
      if (sec !== null) {
        sec.removeAttribute('hidden');
      }
      passBase = null;       // baselines belong to the old chart
      // Synchronous, in this same task, so a chart whose pass is already
      // over is hidden before anything is painted -- once a packet is in
      // hand.  Without one the chart stands as the station drew it; the
      // dot has no position to move to until the feed gives it one.
      renderPass();
    };
    try {
      // Cache-busted, like the dome fragment.
      xhttp.open('GET', fragUrl + '?ts=' + Date.now(), true);
      // Timed out like the dome's fetch, and for the same reason: a
      // server that accepts the connection and never answers would
      // otherwise leave one request hanging every five minutes for the
      // life of the page.  The chart carries no health line of its own --
      // it is a fixed future scene, not a live sky -- so this buys
      // tidiness rather than a diagnosis.  Sized like the dome's, and
      // for the same payload reason.
      xhttp.timeout = 30000;
      xhttp.send();
    } catch (e) {
      console.log(e);
    }
  }

  // ---- countdown central ---------------------------------------------------
  // The chip row under the header: d hh:mm:ss countdowns rendered on
  // every loop packet, at loop cadence -- the page's clock moves only
  // with a packet (serverNow) -- each pure client arithmetic against an
  // event-tier loopdata field, computed once by the engine, cached
  // until the event, zero cost at this cadence.  Feature detection is
  // the roster's: an ABSENT key (not declared, or an almanac
  // that cannot serve it) leaves the chip's report-time first paint
  // alone; a key present but null is loopdata's honest "nothing ahead"
  // and hides the chip.  The windowed guests (supermoon, eclipse, a
  // comet's perihelion) show only within CHIP_WINDOW_SEC of the event
  // -- close enough to count meaningfully.
  var CHIP_WINDOW_SEC = 30 * 86400;
  function fmtDHMS(sec) {
    // The countdown's precision follows its horizon: a day or more out
    // it reads days-hours-minutes, moving by the minute (seconds --
    // and a seconds-bearing clock shape -- are noise at that range, and
    // the chip's detail carries the actual date); inside the final day
    // it becomes the hh:mm:ss clock, where seconds are the point.
    sec = Math.max(0, Math.floor(sec));
    var days = Math.floor(sec / 86400);
    var rem = sec - days * 86400;
    var hh = Math.floor(rem / 3600);
    var mm = Math.floor((rem - hh * 3600) / 60);
    if (days >= 1) {
      return fmt('{d}d {h}h {m}m', {d: days, h: hh, m: mm});
    }
    var ss = rem - hh * 3600 - mm * 60;
    return ('0' + hh).slice(-2) + ':' + ('0' + mm).slice(-2) + ':' +
           ('0' + ss).slice(-2);
  }
  function chipShow(id, show) {
    var el = document.getElementById(id);
    if (el === null) {
      return;
    }
    if (show) {
      el.removeAttribute('hidden');
    } else {
      el.setAttribute('hidden', '');
    }
  }
  function chipStaticTs(id) {
    // The generation-baked target instant (the chip's data-ts): a
    // countdown needs only a target and a clock, and the page's clock is
    // GEN_TS until the first packet moves it, so a chip whose key the
    // feed does not carry counts down from this target on every packet
    // -- the loop feed's job is re-anchoring and ROLLING the target when
    // the event passes; the counting needs no key of its own.
    var el = document.getElementById(id);
    if (el === null) {
      return null;
    }
    return attrNum(el, 'data-ts');
  }
  function seasonKey(ts) {
    // The season the instant begins, hemisphere-aware, named by the
    // event's month in the display zone (equinoxes fall in
    // March/September, solstices in June/December -- the month is
    // unambiguous even across zone shifts).
    var mo = parseInt(new Date(ts * 1000).toLocaleString('en-GB',
        tzOptions({month: 'numeric'})), 10);
    var north = STATION_LAT >= 0;
    if (mo >= 2 && mo <= 4) {
      return north ? 'spring begins' : 'autumn begins';
    }
    if (mo >= 5 && mo <= 7) {
      return north ? 'summer begins' : 'winter begins';
    }
    if (mo >= 8 && mo <= 10) {
      return north ? 'autumn begins' : 'spring begins';
    }
    return north ? 'winter begins' : 'summer begins';
  }
  function chipEvent(id, key, nowTs, windowed) {
    // The shared chip skeleton: read the pinned instant -- the live
    // feed's when it carries the key, else the generation-baked
    // data-ts -- decide visibility, paint the value.  Returns the
    // instant (null: hidden, or the first paint stands) so callers can
    // dress the k/d cells.  The -60 grace shows 00:00:00 between the
    // event and the roll that replaces the target; without the feed
    // KEY there is no roll, so a passed static target hides its chip
    // until the next report cycle regenerates the page.  (With no feed
    // at all this never runs -- renderCountdown paints on packets -- and
    // the baked first paint stands under the badge that says why.)
    var ts;
    if (hasKey(key)) {
      ts = num(latest, key);       // present but null: honest nothing
    } else {
      ts = chipStaticTs(id);
      if (ts === null) {
        return null;               // nothing to count: first paint stands
      }
    }
    var show = ts !== null && ts - nowTs > -60 &&
               (!windowed || (ts - nowTs >= 0 && ts - nowTs <= CHIP_WINDOW_SEC));
    chipShow(id, show);
    if (!show) {
      return null;
    }
    setHtml(id + '-v', fmtDHMS(ts - nowTs));
    return ts;
  }
  function renderCountdown() {
    // Runs on every loop packet (updateCurrent), which is when the page's
    // clock moves: the sun, shower and darkness chips count from their
    // generation-baked targets until the feed's event fields arrive to
    // re-anchor and roll them.  Before the first packet the template's
    // first paint stands, and it is exactly what this would render for
    // GEN_TS -- the same arithmetic on the same instant.  The pass chip
    // is feed-only (rolling is its whole story).
    //
    // Every target below -- the feed's instants and the generation-baked
    // data-ts alike -- is written by the STATION, so the instant they
    // are measured against is the station's too (serverNow), never the
    // viewer's clock.  8.1 through 8.3.3 subtracted Date.now() from
    // these, so a viewer whose clock was ninety seconds fast read every
    // countdown ninety seconds wrong and hid each chip before loopdata
    // had rolled its target, leaving a gap.  On one clock the -60 grace
    // and the engine's roll interlock as they were designed to.
    var nowTs = serverNow();
    var bestTag = null, bestRise = null, bestSet = null, anyPassKey = false;
    SAT_NAMES.forEach(function(sat) {
      var base = 'almanac.' + sat + '.next_visible_pass';
      if (!hasKey(base + '.rise.unix_epoch.raw') && !hasKey(base + '.rise.raw')) {
        return;
      }
      anyPassKey = true;
      var rise = numOr(base + '.rise.unix_epoch.raw', base + '.rise.raw');
      if (rise === null) {
        return;
      }
      if (bestRise === null || rise < bestRise) {
        bestTag = sat;
        bestRise = rise;
        bestSet = numOr(base + '.set.unix_epoch.raw', base + '.set.raw');
      }
    });
    if (anyPassKey) {
      var passShow = bestRise !== null &&
          (nowTs < bestRise || (bestSet !== null && nowTs < bestSet + 60));
      chipShow('chip-pass', passShow);
      if (passShow) {
        setHtml('chip-pass-k', esc(satLabel(bestTag)));
        if (nowTs < bestRise) {
          setHtml('chip-pass-d', T['appears in']);
          setHtml('chip-pass-v', fmtDHMS(bestRise - nowTs));
        } else if (bestSet !== null && nowTs < bestSet) {
          setHtml('chip-pass-d', T['overhead now']);
          setHtml('chip-pass-v', '');
        } else {
          setHtml('chip-pass-d', T['just set']);
          setHtml('chip-pass-v', '');
        }
      }
    } else {
      // No feed keys: count from the generation-baked rise/set pair
      // (the painted label stands).  Without the keys there is no roll,
      // so a completed pass hides its chip until the next report
      // cycle regenerates the page.
      var passStatic = chipStaticTs('chip-pass');
      if (passStatic !== null) {
        var passEl = document.getElementById('chip-pass');
        var passSetStatic = attrNum(passEl, 'data-set');
        if (nowTs < passStatic) {
          chipShow('chip-pass', true);
          setHtml('chip-pass-d', T['appears in']);
          setHtml('chip-pass-v', fmtDHMS(passStatic - nowTs));
        } else if (passSetStatic !== null && nowTs < passSetStatic) {
          chipShow('chip-pass', true);
          setHtml('chip-pass-d', T['overhead now']);
          setHtml('chip-pass-v', '');
        } else {
          chipShow('chip-pass', false);
        }
      }
    }
    // Sunset or sunrise, whichever next: a client-side min() -- the
    // next_* pair always lies ahead by definition, and loopdata's event
    // expiry rolls each the moment it passes, so the sunset chip
    // becomes the sunrise chip by itself.
    if (hasKey('almanac.sun.next_setting.unix_epoch.raw') ||
        hasKey('almanac.sun.next_rising.unix_epoch.raw')) {
      var sunSet = num(latest, 'almanac.sun.next_setting.unix_epoch.raw');
      var sunRise = num(latest, 'almanac.sun.next_rising.unix_epoch.raw');
      var sunTs = null, sunK = null;
      if (sunSet !== null && (sunRise === null || sunSet <= sunRise)) {
        sunTs = sunSet;
        sunK = T['sunset'];
      } else if (sunRise !== null) {
        sunTs = sunRise;
        sunK = T['sunrise'];
      }
      var sunShow = sunTs !== null && sunTs - nowTs > -60;
      chipShow('chip-sun', sunShow);
      if (sunShow) {
        setHtml('chip-sun-k', sunK);
        setHtml('chip-sun-v', fmtDHMS(sunTs - nowTs));
        setHtml('chip-sun-d', fmtHM(sunTs));
      }
    } else {
      // No feed keys: count from the generation-baked target (the k and
      // d cells stand as painted -- same event).
      var sunStatic = chipStaticTs('chip-sun');
      if (sunStatic !== null) {
        var sunStaticShow = sunStatic - nowTs > -60;
        chipShow('chip-sun', sunStaticShow);
        if (sunStaticShow) {
          setHtml('chip-sun-v', fmtDHMS(sunStatic - nowTs));
        }
      }
    }
    // The shower chip: there is always a next shower; the label rides
    // the same event group as the peak, so both roll together.  The
    // generation-time moon note (illumination at the peak) is cleared
    // if the live label has rolled past the shower it described.
    var showerTs = chipEvent('chip-shower',
        'almanac.next_meteor_shower.peak.unix_epoch.raw', nowTs, false);
    if (showerTs !== null) {
      var showerLab = strAt('almanac.next_meteor_shower.label');
      if (showerLab !== null) {
        setHtml('chip-shower-k', esc(showerLab));
        var showerChip = document.getElementById('chip-shower');
        if (showerChip !== null &&
            showerChip.getAttribute('data-shower-label') !== showerLab) {
          showerChip.setAttribute('data-shower-label', showerLab);
          setHtml('chip-shower-d', '');
        }
      }
    }
    // Astronomical darkness, symmetric with the sun chip: darkness
    // begins at the -18 sunset, ends at the -18 sunrise -- stargazers
    // care about both ends of the window.  A high-latitude summer
    // where -18 never comes serves nulls and hides the chip.  The
    // keys are the declaration's spellings verbatim.
    if (hasKey('almanac(horizon=-18).sun.next_setting.unix_epoch.raw') ||
        hasKey('almanac(horizon=-18).sun.next_rising.unix_epoch.raw')) {
      var darkSet = num(latest, 'almanac(horizon=-18).sun.next_setting.unix_epoch.raw');
      var darkRise = num(latest, 'almanac(horizon=-18).sun.next_rising.unix_epoch.raw');
      var darkTs = null, darkK = null;
      if (darkSet !== null && (darkRise === null || darkSet <= darkRise)) {
        darkTs = darkSet;
        darkK = T['darkness begins'];
      } else if (darkRise !== null) {
        darkTs = darkRise;
        darkK = T['darkness ends'];
      }
      var darkShow = darkTs !== null && darkTs - nowTs > -60;
      chipShow('chip-dark', darkShow);
      if (darkShow) {
        setHtml('chip-dark-k', darkK);
        setHtml('chip-dark-v', fmtDHMS(darkTs - nowTs));
        setHtml('chip-dark-d', fmtHM(darkTs));
      }
    } else {
      var darkStatic = chipStaticTs('chip-dark');
      if (darkStatic !== null) {
        var darkStaticShow = darkStatic - nowTs > -60;
        chipShow('chip-dark', darkStaticShow);
        if (darkStaticShow) {
          setHtml('chip-dark-v', fmtDHMS(darkStatic - nowTs));
        }
      }
    }
    // The season chip: equinox or solstice, whichever next, inside the
    // 30-day window -- the one event whose count-to-zero is exact to
    // the second, named by the season it begins.  The date detail is
    // generation-painted and never rewritten (the chip's k rides the
    // same translated keys both sides).
    if (hasKey('almanac.next_equinox.unix_epoch.raw') ||
        hasKey('almanac.next_solstice.unix_epoch.raw')) {
      var eqTs = num(latest, 'almanac.next_equinox.unix_epoch.raw');
      var solTs = num(latest, 'almanac.next_solstice.unix_epoch.raw');
      var seasonTs = null;
      if (eqTs !== null && (solTs === null || eqTs <= solTs)) {
        seasonTs = eqTs;
      } else if (solTs !== null) {
        seasonTs = solTs;
      }
      var seasonShow = seasonTs !== null && seasonTs - nowTs >= 0 &&
                       seasonTs - nowTs <= CHIP_WINDOW_SEC;
      chipShow('chip-season', seasonShow);
      if (seasonShow) {
        var sk = seasonKey(seasonTs);
        setHtml('chip-season-k', T[sk] || sk);
        setHtml('chip-season-v', fmtDHMS(seasonTs - nowTs));
      }
    } else {
      var seasonStatic = chipStaticTs('chip-season');
      if (seasonStatic !== null) {
        var seasonStaticShow = seasonStatic - nowTs >= 0 &&
                               seasonStatic - nowTs <= CHIP_WINDOW_SEC;
        chipShow('chip-season', seasonStaticShow);
        if (seasonStaticShow) {
          setHtml('chip-season-v', fmtDHMS(seasonStatic - nowTs));
        }
      }
    }
    // Earth's apsis chip, the season chip's twin: perihelion or
    // aphelion, whichever next, inside the 30-day window -- extremum
    // instants, minute-class by nature.  The date detail is
    // generation-painted and never rewritten.
    if (hasKey('almanac.next_perihelion.unix_epoch.raw') ||
        hasKey('almanac.next_aphelion.unix_epoch.raw')) {
      var periTs2 = num(latest, 'almanac.next_perihelion.unix_epoch.raw');
      var aphTs = num(latest, 'almanac.next_aphelion.unix_epoch.raw');
      var apsisTs = null, apsisK = null;
      if (periTs2 !== null && (aphTs === null || periTs2 <= aphTs)) {
        apsisTs = periTs2;
        apsisK = T['Earth perihelion'];
      } else if (aphTs !== null) {
        apsisTs = aphTs;
        apsisK = T['Earth aphelion'];
      }
      var apsisShow = apsisTs !== null && apsisTs - nowTs >= 0 &&
                      apsisTs - nowTs <= CHIP_WINDOW_SEC;
      chipShow('chip-apsis', apsisShow);
      if (apsisShow) {
        setHtml('chip-apsis-k', apsisK);
        setHtml('chip-apsis-v', fmtDHMS(apsisTs - nowTs));
      }
    } else {
      var apsisStatic = chipStaticTs('chip-apsis');
      if (apsisStatic !== null) {
        var apsisStaticShow = apsisStatic - nowTs >= 0 &&
                              apsisStatic - nowTs <= CHIP_WINDOW_SEC;
        chipShow('chip-apsis', apsisStaticShow);
        if (apsisStaticShow) {
          setHtml('chip-apsis-v', fmtDHMS(apsisStatic - nowTs));
        }
      }
    }
    // The remaining windowed guests.  Their date/type details are
    // generation-painted and never rewritten (first paint and live
    // must not differ in dress); the live layer decides visibility,
    // paints the value, and re-derives the label from the feed's own
    // strings -- the same translated text the generator painted.
    chipEvent('chip-super', 'almanac.next_supermoon.unix_epoch.raw',
              nowTs, true);
    var eclTs = chipEvent('chip-eclipse',
        'almanac.next_eclipse.unix_epoch.raw', nowTs, true);
    if (eclTs !== null && hasKey('almanac.next_eclipse.unix_epoch.raw')) {
      // Live path only: the kind names the chip; without one the chip
      // cannot say what it is counting to, so it hides.  (On the
      // static path the generation-painted label stands.)
      var eclKind = strAt('almanac.next_eclipse_kind');
      if (eclKind === 'lunar' || eclKind === 'solar') {
        setHtml('chip-eclipse-k',
                T[eclKind === 'lunar' ? 'lunar eclipse' : 'solar eclipse']);
      } else {
        chipShow('chip-eclipse', false);
      }
    }
    COMET_NAMES.forEach(function(cometTag) {
      var periKey = 'almanac.' + cometTag + '.perihelion.unix_epoch.raw';
      var periTs = chipEvent('chip-peri-' + cometTag, periKey, nowTs, true);
      if (periTs !== null && hasKey(periKey)) {
        setHtml('chip-peri-' + cometTag + '-k',
                fmt('{name} perihelion', {name: esc(satLabel(cometTag))}));
      }
    });
  }

  // ---- poll + local tick ---------------------------------------------------
  var lastTickTs = 0;
  function localTick() {
    var nowTs = Date.now() / 1000;
    // Two minutes, not five seconds: a hidden tab's timers are throttled
    // to roughly one a minute, so a tighter threshold reads ordinary
    // background running as a resume, on every single tick.  A real
    // sleep is minutes at least, and shorter suspends are caught by
    // visibilitychange and pageshow anyway.
    if (lastTickTs !== 0 && nowTs - lastTickTs > 120) {
      domeWake();                // the machine was not running; see above
    }
    lastTickTs = nowTs;
    // This tick is for MOTION and housekeeping only.  Nothing that reads
    // the page's clock is REPAINTED by it: the countdown chips, the
    // satellite rosters and the header's "updated" stamp render as
    // packets arrive (see serverNow), and 8.3.4's header clock is gone
    // -- read from the station it was that stamp shown twice.  (Two
    // things below do READ the clock every second -- the pass chart's
    // over/ahead verdict and the dome-stale judgement -- but between two
    // packets it does not move, so they paint nothing new.)
    //
    // The backdrop's health goes stale on its own schedule, whatever the
    // loop feed is doing; its inputs move with packets, fetch outcomes
    // and the wake grace, and it repaints only on a change.
    updateDomeStale(nowTs);
    // The pass chart's sweep, extrapolated between packets like the
    // dial's bodies and the dome's marks below (its verdict, on
    // serverNow, can only change with a packet; renderPass returns at
    // its latest === null guard until one lands, leaving the chart as
    // the station drew it).  Contained: a throw here must not take the
    // dial and the dome down with it every second (the silent-dead-dial
    // class; see restoreDomeMarks' note).
    try {
      renderPass();
    } catch (e) {
      console.log(e);
    }
    if (latest !== null) {
      renderGeo();
      renderDome(nowTs);
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
        // Since weewx-loopdata 7.0 the file carries each declaring
        // report's fields under the REPORT's name (the [StdReport]
        // section, not the skin: one skin can be listed under two
        // reports, in two languages), each rendered with that report's
        // own units, formats and [Almanac] names.  This page reads its
        // own entry and nothing else; everything below sees the flat
        // record it always saw.  A file without the key is a
        // weewx-loopdata older than 7.0 (the installer refuses to
        // install beside one), or this report not declaring its fields;
        // BAD DATA covers both -- the file is there, this page's data is
        // not.  The name arrives through the config like every other
        // string the report hands this script: a report name is any
        // [StdReport] section name, quotes and non-ASCII included.
        result = JSON.parse(this.responseText)[REPORT_NAME];
        if (result === undefined) {
          throw new Error('no ' + REPORT_NAME +
                          ' entry in loop_data_file (weewx-loopdata 7.0 or ' +
                          'later writes one per declaring report)');
        }
      } catch (e) {
        // A 200 with a non-JSON body, or JSON without this report's
        // entry: loop_data_file points at something, but not at
        // weewx-loopdata's output for this page.
        setHtml("live-label", T['BAD DATA \u2014 check loop_data_file']);
        console.log(e);
        return;
      }
      try {
        var nowTs = Date.now() / 1000;

        // Check the date
        // "dateTime": 1578965850,
        var lastTs = result["current.dateTime.raw"];
        if (typeof lastTs !== 'number') {
          // A record with no station timestamp is INVALID and is dropped
          // whole, exactly as if the fetch had never landed: the page's
          // clock, its rates and its every placement are anchored on this
          // field, and a record that cannot say when it was written
          // cannot serve any of them.  Nothing is stored -- not latest,
          // not latestTs, not latestRecvTs -- so the feed simply goes on
          // looking dead, which is what it is, and DEAD_FEED restores the
          // dome's marks on its own schedule.  8.3.3 and earlier stamped
          // these from the BROWSER's clock, which is the one clock this
          // page may not read; the skin's own declaration (its `clock`
          // group) always carries current.dateTime.raw, so a feed doing
          // this is misconfigured and the badge says so.  (John,
          // 2026-08-16.)
          setHtml("live-label", T['BAD DATA \u2014 check loop_data_file']);
          console.log('loop record has no current.dateTime.raw; ignored');
          return;
        }
        latest = result;
        var prevTs = latestTs;
        latestTs = lastTs;
        // Stamped by the browser, for the one question that must not
        // cross clocks: has the feed stopped arriving HERE?  latestTs is
        // the station's own time and belongs to the backdrop-age
        // judgement; comparing it against Date.now() would make an
        // ordinary two-minute clock skew look exactly like a dead feed.
        //
        // Only when the packet is NEW, though.  The commonest way a feed
        // dies is not a failed fetch: weewx-loopdata stops writing and
        // the web server goes on serving the last file, so every poll is
        // a 200 carrying the same stale json.  Stamping those would keep
        // this clock fresh for ever while the station's clock -- and with
        // it the backdrop-age judgement, which reads latestTs -- froze:
        // both restore paths dead at once, and the plate left showing a
        // current star field wearing hour-old bodies.  A repeat of the
        // same packet is not news.
        if (latestTs !== prevTs) {
          latestRecvTs = nowTs;
        }
        // The first packet needs no case of its own any more: every new
        // packet checks the backdrop below, and the first is simply the
        // one that moves the clock furthest -- from GEN_TS, which names
        // the slot the page was generated with, to the station's real
        // time.  A page served from a browser or CDN cache can be hours
        // stale, and that is the packet that repairs it.
        // How old the data on show is -- two terms, each measured on ONE
        // clock, never across the two.  How stale this record already was
        // when the page first found it: its own station time against the
        // page's generation instant, station against station.  Plus how
        // long since a fresh record arrived HERE: browser against
        // browser.  Through 8.3.3 this was Date.now() minus the packet's
        // station time, which posted a skewed viewer's offset as a
        // permanent "Ns ago" over a perfectly live feed.
        //
        // The first term is zero on any healthy feed, whose packets are
        // newer than the page that reads them, and the six-second LIVE
        // threshold absorbs a write that lags the archive instant.  It
        // earns its place on the dead feed a viewer has just loaded:
        // loopdata stopped an hour ago, the web server still serves the
        // last file, and the first fetch stamps latestRecvTs -- so the
        // second term alone reads zero and the badge would call hour-old
        // data LIVE, resetting on every reload.  Against GEN_TS it reads
        // the hour.
        var age = Math.round(Math.max(0, GEN_TS - latestTs)
                             + (nowTs - latestRecvTs));
        setHtml("live-label", age <= 6 ? T['LIVE'] : fmt('{age}s ago', {age: age}));
        // Display the time of the last update, in the page's timezone.
        setHtml("last-update", fmtHMS(lastTs));
        pushHistory(latestTs, result);
        // Everything that reads the page's clock renders here, on the
        // packet that moved it (see serverNow), and everything that
        // extrapolates re-anchors here.  Only when the packet is NEW:
        // the commonest dead feed is the last file served again on every
        // poll (see latestRecvTs above), and a repeat moves nothing, so
        // there is nothing to paint -- five renders of identical text
        // every refresh_rate for as long as it lasts.  The badge above
        // stays outside this gate because the age it reports goes on
        // growing; the stamp beside it is repainted with the same digits
        // on a repeat, one setHtml, not worth a second gate.  The tick
        // still drives the motion between packets and the dead-feed
        // restore.
        if (latestTs !== prevTs) {
          if (document.readyState === 'loading') {
            renderWanted = true;   // the page is still streaming; see the load handler
          }
          // The packet is the page's clock, so it is also the only thing
          // that can change which slot the backdrop should be showing:
          // check on every one of them.  Nearly all of these return at
          // refreshDome's want-gate without a request -- the cost is a
          // floor division -- and the one that does not is the instant
          // the sky is genuinely a slot behind, which is when it should
          // step.  The minute interval stays as the backstop for the
          // cases no packet reaches: a pre-stagger backdrop, and a fetch
          // that failed and must be retried.
          refreshDome();
          renderPacket(nowTs);
        }
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
      xhttp.open("GET", LOOP_DATA_FILE, true);
      // AFTER open(), for the reason the dome's fetch documents: an
      // engine that throws InvalidStateError on a timeout set against an
      // unopened request would throw here inside this try, the catch
      // would swallow it, and the poll would never send -- the page
      // would never go live at all, which is worse than any dome fault.
      xhttp.timeout = 1800;
      xhttp.send();
    } catch (e) {
      console.log(e);
    }
  }

  // ---- start ---------------------------------------------------------------
  var started = false;
  function start(config) {
    // Once only: a second call would arm every timer and listener twice.
    if (started) {
      console.log('celestial.start called twice; the second call is ignored');
      return;
    }
    started = true;
    if (config.version !== CELESTIAL_JS_VERSION) {
      // Logged, not refused: the config is what the report emitted, and
      // inside a major version it only gains keys.  There are no
      // defaults here -- the report's config_dict is the one place they
      // live -- so a config a report did not build is not supported.
      console.log('celestial.js ' + CELESTIAL_JS_VERSION +
                  ' started with a version ' + config.version + ' config');
    }
    page_update_pwd = config.page_update_pwd;
    refresh_rate = config.refresh_rate;
    expiration_time = config.expiration_time;
    // Timezone for displayed times: the station's zone, auto-detected by
    // the report; the time_zone Extras option overrides ('browser' forces
    // the viewer's browser-local zone), and empty falls back to
    // browser-local too.
    time_zone = config.time_zone;
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
    STATION_LAT = config.station_lat;
    GEN_TS = config.gen_ts;
    PER_AU = config.per_au;
    DIST_LABEL = config.dist_label;
    // The report's language drives toLocaleString (the satellite rosters'
    // pass times and the frozen-sky line's time; the header's "updated"
    // stamp and the chip details are 24-hour in every language, matching
    // the template's bake); an unknown tag must not break every render.
    LOCALE = config.locale;
    try {
      new Date().toLocaleString(LOCALE);
    } catch (e) {
      console.log('bad lang "' + LOCALE + '", using en-US');
      LOCALE = 'en-US';
    }
    // Everything this script composes is translated at generation time
    // and arrives here: body names from the report's [Almanac] section
    // (the same source as the almanac's .label tag), cardinals from the
    // report formatter's compass ordinates, and the badge/roster/chip
    // strings from [Texts].  All three ride through json.dumps, which
    // \u-escapes every non-ASCII character -- the report's html_entities
    // encoding can never touch them, and dial labels land via textContent
    // where entities would show literally.  Javascript key literals into
    // T must spell non-ASCII with the same \u escapes.
    BODY_LABELS = config.body_labels || {};
    CARDINALS = config.cardinals || [];
    T = config.texts || {};
    // The satellite set follows the station's [Skyfield] [[Satellites]]
    // and the comet set its [[Comets]], both enumerated by the report
    // through weewx-skyfield's public satellite_names()/comet_names();
    // the page builds its roster rows from the same lists, so rows and
    // live layer always agree.  Comets ride the DIAL, not the dome: the
    // dome fragments already carry their diamonds, redrawn every backdrop
    // refetch -- nothing to nudge at comet speed.
    SAT_NAMES = config.sat_names || [];
    COMET_NAMES = config.comet_names || [];
    REPORT_NAME = config.report_name;
    // A report with no loop_data_file hands over '': nothing is polled
    // (the empty URL is the page's own -- a whole page every
    // refresh_rate seconds for nothing) and the badge says BAD DATA --
    // check loop_data_file, naming the option, once the label has parsed.
    LOOP_DATA_FILE = config.loop_data_file;
    PAGE_THEME = config.theme;
    DEAD_FEED = Math.max(EXTRAP_MAX, 20 * refresh_rate);

    // The timers, load handlers and listeners, in one place and in this
    // order: the load handlers chain in registration order (addLoadEvent),
    // so the first packet's fetch precedes the deferred paints, which
    // precede the deferred backdrop refetch.
    setPageExpirationTimer();
    if (LOOP_DATA_FILE === '') {
      addLoadEvent(function() {
        setHtml('live-label', T['BAD DATA \u2014 check loop_data_file']);
      });
    } else {
      setInterval(updateCurrent, refresh_rate * 1000);
      addLoadEvent(updateCurrent);
    }
    setInterval(localTick, 1000);
    addLoadEvent(renderOnLoad);
    FRAGMENT_ROOT = config.root;
    setInterval(refreshDome, DOME_REFRESH * 1000);
    addLoadEvent(refetchDomeOnLoad);
    domeStaleGrace = Date.now() / 1000 + 5;
    document.addEventListener('visibilitychange', function() {
      if (!document.hidden) {
        domeWake();
      }
    });
    // Coming back to the front is not the only way a page resumes.  The
    // back button restores from the bfcache with no visibility change at
    // all, and an OS suspend with this tab already in front resumes
    // without one either -- both land on exactly the case the grace exists
    // for.  pageshow catches the first; the tick-gap check in localTick
    // catches the second, since a one-second timer that did not fire for
    // five seconds means the machine was not running.
    window.addEventListener('pageshow', function(e) {
      if (e.persisted) {
        domeWake();
      }
    });
    setInterval(refreshPass, CHART_REFRESH * 1000);
  }

  return {start: start};
})();
