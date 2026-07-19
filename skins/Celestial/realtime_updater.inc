## Copyright (C)2022-2025 by John A Kline (john@johnkline.com)
## See LICENSE.txt for your rights
## NOTE: Cheetah owns '#' and '$' in this file: no hex color literals (all
## colors come from classes in celestial.css) and no javascript template
## literals.  Guard every loop-data key: a missing field must skip its own
## cell, never abort the whole update.
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
  ## (this extension no longer registers distance observation types).
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
  function fmtHM(ts) {
    return new Date(ts * 1000).toLocaleString("en-US",
      tzOptions({hour: '2-digit', minute: '2-digit'}));
  }
  function fmtHour(ts) {
    return new Date(ts * 1000).toLocaleString("en-US",
      tzOptions({hour: 'numeric'}));
  }
  function fmtDateShort(ts) {
    return new Date(ts * 1000).toLocaleDateString("en-US",
      tzOptions({month: 'short', day: 'numeric'}));
  }
  function fmtDateTime(ts) {
    // Matches the template's server-side %m/%d/%Y %I:%M:%S %p format.
    return new Date(ts * 1000).toLocaleString("en-US",
      tzOptions({month: '2-digit', day: '2-digit', year: 'numeric',
                 hour: '2-digit', minute: '2-digit', second: '2-digit'})).replace(',', '');
  }
  function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function compass16(az) {
    var PTS = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
               'S','SSW','SW','WSW','W','WNW','NW','NNW'];
    return PTS[Math.round(az / 22.5) % 16];
  }
  function daylightString(yesterday_daylight_secs, today_daylight_secs) {
    // 	9 hours, 35 minutes, 56 seconds
    //  0 minutes, 2 seconds less than yesterday
    var hours = Math.floor(today_daylight_secs / 3600);
    var minutes = Math.floor((today_daylight_secs % 3600) / 60);
    var seconds = Math.round(today_daylight_secs % 60);
    delta = Math.abs(Math.round(yesterday_daylight_secs - today_daylight_secs));
    var deltaMinutes = Math.floor((delta % 3600) / 60);
    var deltaSeconds = delta % 60;
    var moreLess = "same"
    if (today_daylight_secs < yesterday_daylight_secs) {
      moreLess = "less";
    } else if (today_daylight_secs > yesterday_daylight_secs) {
      moreLess = "more";
    }
    return hours + ' hours, ' + minutes + ' minutes, ' + seconds + " seconds<br>" + deltaMinutes + " minutes, " + deltaSeconds + " seconds " + moreLess + " than yesterday";
  }

  // ---- per-field setters: a missing key skips its cell, never throws -----
  function setHtml(id, html) {
    var el = document.getElementById(id);
    if (el && html !== undefined && html !== null) {
      el.innerHTML = html;
    }
  }
  function setTime(r, key) {
    if (typeof r[key] === 'number') {
      setHtml(key, fmtHMS(r[key]));
    }
  }
  function setDeg(r, key) {
    if (typeof r[key] === 'number') {
      setHtml(key, r[key].toFixed(1) + "&deg;");
    }
  }
  function setStr(r, key) {
    if (r[key] !== undefined) {
      setHtml(key, r[key]);
    }
  }
  function setDist(r, key) {
    // Distances arrive as raw AU; format to match the template's
    // "{:,.1f}" + label first paint.
    if (typeof r[key] === 'number') {
      setHtml(key, numberWithCommas((r[key] * PER_AU).toFixed(1)) + DIST_LABEL);
    }
  }
  function setFullTime(r, key) {
    // Format date+time cells from the raw epoch so they honor time_zone;
    // fall back to loop-data's pre-formatted (station-timezone) string
    // when the .raw rendition is not in the user's fields list.
    if (typeof r[key + '.raw'] === 'number') {
      setHtml(key, fmtDateTime(r[key + '.raw']));
    } else if (r[key] !== undefined) {
      setHtml(key, r[key]);
    }
  }

  // ---- timezone day math (DST-correct) ------------------------------------
  // Offset of the display timezone from UTC at ts, in milliseconds.
  function tzOffsetMs(ts) {
    var d = new Date(ts * 1000);
    if (time_zone === '') {
      return -d.getTimezoneOffset() * 60000;
    }
    var parts = new Intl.DateTimeFormat('en-US', {timeZone: time_zone, hour12: false,
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit'}).formatToParts(d);
    var v = {};
    parts.forEach(function(p) { v[p.type] = p.value; });
    return Date.UTC(v.year, v.month - 1, v.day, v.hour % 24, v.minute, v.second) - d.getTime();
  }
  // Start of the display-timezone day containing ts (seconds).
  function midnightTs(ts) {
    var guess = Math.floor((ts * 1000 + tzOffsetMs(ts)) / 86400000) * 86400000;
    // Refine with the offset in effect just before that midnight, so DST
    // days (23/25 hours) land on the true wall-clock midnight.
    return (guess - tzOffsetMs((guess - 43200000) / 1000)) / 1000;
  }

  // ---- live components -----------------------------------------------------
  var latest = null;      // last parsed loop-data object

  // True-phase moon disc (geometry ported from the weewx-skyfield Sky page).
  function renderMoonDisc(r) {
    var el = document.getElementById('moon-disc');
    var fullness = r["almanac.moon.phase"];
    var index = r["almanac.moon_index"];
    if (!el || typeof fullness !== 'number' || typeof index !== 'number') {
      return;   // fields not in the loop-data list: leave the container empty
    }
    var frac = fullness / 100.0;
    // Waxing iff the next full moon precedes the next new moon (exact);
    // the phase index is a coarse fallback (index 0 also covers the last
    // ~1.5 days of waning crescent, which would draw the lit side mirrored).
    var nextFull = r["almanac.next_full_moon.raw"], nextNew = r["almanac.next_new_moon.raw"];
    var waxing = (typeof nextFull === 'number' && typeof nextNew === 'number')
        ? (nextFull < nextNew) : (index <= 3);
    var litLeft = (STATION_LAT >= 0) ? !waxing : waxing;
    var c = 38, R = 34;
    var rx = Math.abs(2 * frac - 1) * R;
    var limbSweep = litLeft ? 0 : 1;
    var termSweep = (frac >= 0.5) ? (litLeft ? 0 : 1) : (litLeft ? 1 : 0);
    var path = 'M ' + c + ',' + (c - R) +
               ' A ' + R + ',' + R + ' 0 0 ' + limbSweep + ' ' + c + ',' + (c + R) +
               ' A ' + rx + ',' + R + ' 0 0 ' + termSweep + ' ' + c + ',' + (c - R) + ' Z';
    document.getElementById('moon-disc').innerHTML =
      '<svg viewBox="0 0 76 76" role="img" aria-label="Moon phase">' +
      '<circle class="moon-dark" cx="' + c + '" cy="' + c + '" r="' + R + '"/>' +
      '<path class="moon-lit" d="' + path + '"/>' +
      '<circle class="moon-ring" cx="' + c + '" cy="' + c + '" r="' + R + '"/>' +
      '</svg>';
  }

  // Countdown chips: next full/new moon, equinox, solstice.
  function renderCountdowns(r, nowTs) {
    var chips = [['count-fullmoon', 'almanac.next_full_moon.raw'],
                 ['count-newmoon', 'almanac.next_new_moon.raw'],
                 ['count-equinox', 'almanac.next_equinox.raw'],
                 ['count-solstice', 'almanac.next_solstice.raw']];
    chips.forEach(function(chip) {
      var el = document.getElementById(chip[0]);
      var ts = r[chip[1]];
      if (!el || typeof ts !== 'number') {
        return;
      }
      // Count calendar days in the display timezone, not 86400-second
      // buckets: an event later tonight is 'today', not 'in 1 day'.
      var n = Math.max(0, Math.round((midnightTs(ts) - midnightTs(nowTs)) / 86400));
      var when = (n === 0) ? 'today' : (n === 1 ? 'in 1 day' : 'in ' + n + ' days');
      el.querySelector('.v').innerHTML = fmtDateShort(ts);
      el.querySelector('.d').innerHTML = when;
    });
  }

  // The day strip: twilight bands, rise/set ticks and the moving now-line.
  var STRIP_X0 = 8, STRIP_X1 = 992, STRIP_W = 1000, STRIP_H = 96;
  var stripSod = 0, stripEod = 1;
  function stripX(ts) {
    var t = Math.min(Math.max(ts, stripSod), stripEod);
    return STRIP_X0 + (STRIP_X1 - STRIP_X0) * (t - stripSod) / (stripEod - stripSod);
  }
  function renderDayStrip(r, nowTs) {
    var el = document.getElementById('day-strip');
    if (!el) {
      return;
    }
    stripSod = midnightTs(nowTs);
    stripEod = midnightTs(stripSod + 26 * 3600 + 1);
    var bandTop = 18, bandBot = 66;
    // Sky-state transitions across the day; each edge carries the band it
    // transitions TO and the band it transitions FROM.  Missing edges
    // (polar day/night, sun up at midnight) drop out, and the band before
    // the first surviving edge is that edge's FROM state -- so a day that
    // starts with the sun up starts with the day band, not night.
    var edges = [[r["almanac(horizon=-18).sun(use_center=1).rise.raw"], 'band-astro', 'band-night'],
                 [r["almanac(horizon=-12).sun(use_center=1).rise.raw"], 'band-naut', 'band-astro'],
                 [r["almanac(horizon=-6).sun(use_center=1).rise.raw"], 'band-civil', 'band-naut'],
                 [r["almanac.sunrise.raw"], 'band-day', 'band-civil'],
                 [r["almanac.sunset.raw"], 'band-civil', 'band-day'],
                 [r["almanac(horizon=-6).sun(use_center=1).set.raw"], 'band-naut', 'band-civil'],
                 [r["almanac(horizon=-12).sun(use_center=1).set.raw"], 'band-astro', 'band-naut'],
                 [r["almanac(horizon=-18).sun(use_center=1).set.raw"], 'band-night', 'band-astro']]
      .filter(function(e) { return typeof e[0] === 'number'; })
      .sort(function(a, b) { return a[0] - b[0]; });
    var firstBand;
    if (edges.length > 0) {
      firstBand = edges[0][2];
    } else {
      // No transitions at all today: polar day or polar night.
      var daylight = r["almanac.sun.visible.raw"];
      firstBand = (typeof daylight === 'number' && daylight >= 43200) ? 'band-day' : 'band-night';
    }
    edges.unshift([stripSod, firstBand, firstBand]);
    var svg = '<svg viewBox="0 0 ' + STRIP_W + ' ' + STRIP_H + '" preserveAspectRatio="none" role="img" aria-label="Light and dark today">';
    var i;
    for (i = 0; i < edges.length; i++) {
      var x0 = stripX(edges[i][0]);
      var x1 = (i + 1 < edges.length) ? stripX(edges[i + 1][0]) : STRIP_X1;
      svg += '<rect class="' + edges[i][1] + '" x="' + x0 + '" y="' + bandTop +
             '" width="' + Math.max(0, x1 - x0) + '" height="' + (bandBot - bandTop) + '"/>';
    }
    // Hour gridlines and labels every three hours.
    var t;
    for (t = stripSod; t <= stripEod + 1; t += 3 * 3600) {
      var gx = stripX(t);
      // Anchor the edge labels inward so midnight's text is not clipped.
      var anchor = (t === stripSod) ? 'start' : (t + 3 * 3600 > stripEod + 1 ? 'end' : 'middle');
      svg += '<line class="gridline" x1="' + gx + '" y1="' + bandBot + '" x2="' + gx + '" y2="' + (bandBot + 5) + '"/>';
      svg += '<text class="mono gridlab" x="' + gx + '" y="' + (bandBot + 18) + '" text-anchor="' + anchor + '">' + fmtHour(t) + '</text>';
    }
    // Sun and moon ticks (each may be absent today).
    var ticks = [['almanac.sunrise.raw', 'tick-sun'],
                 ['almanac.sun.transit.raw', 'tick-sun'],
                 ['almanac.sunset.raw', 'tick-sun'],
                 ['almanac.moon.rise.raw', 'tick-moon'],
                 ['almanac.moon.set.raw', 'tick-moon']];
    ticks.forEach(function(tick) {
      var ts2 = r[tick[0]];
      if (typeof ts2 === 'number' && ts2 >= stripSod && ts2 <= stripEod) {
        var tx = stripX(ts2);
        svg += '<line class="' + tick[1] + '" x1="' + tx + '" y1="' + (bandTop - 4) + '" x2="' + tx + '" y2="' + (bandBot + 4) + '"/>';
      }
    });
    // The now-line; localTick() repositions it between polls.
    var nx = stripX(nowTs);
    svg += '<line class="nowline nowpulse" id="strip-now" x1="' + nx + '" y1="10" x2="' + nx + '" y2="' + (bandBot + 6) + '"/>';
    svg += '<text class="mono nowlab" id="strip-now-label" x="' + nx + '" y="8" text-anchor="middle">now ' + fmtHM(nowTs) + '</text>';
    svg += '</svg>';
    el.innerHTML = svg;
  }
  function moveNowLine(nowTs) {
    var line = document.getElementById('strip-now');
    var label = document.getElementById('strip-now-label');
    if (!line || !label) {
      return;
    }
    var nx = stripX(nowTs);
    line.setAttribute('x1', nx);
    line.setAttribute('x2', nx);
    label.setAttribute('x', nx);
    label.textContent = 'now ' + fmtHM(nowTs);
  }

  // Planets-now chips: up/down, altitude, compass direction, distance.
  var PLANETS = ['mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto'];
  function renderPlanets(r) {
    PLANETS.forEach(function(planet) {
      var chip = document.getElementById('planet-' + planet);
      if (!chip) {
        return;
      }
      var alt = r['almanac.' + planet + '.alt'];
      var az = r['almanac.' + planet + '.az'];
      var dist = r['almanac.' + planet + '.earth_distance'];
      if (typeof alt === 'number' && typeof az === 'number') {
        var line;
        if (alt >= 0) {
          line = 'up &middot; ' + alt.toFixed(0) + "&deg; &middot; " + compass16(az);
        } else {
          line = 'down &middot; ' + compass16(az);
        }
        chip.querySelector('.chipline').innerHTML = line;
      }
      if (typeof dist === 'number') {
        chip.querySelector('.chipsub').innerHTML =
            numberWithCommas(Math.round(dist * PER_AU)) + DIST_LABEL;
      }
    });
  }

  // The 41 data cells (dual-source: first-painted by the report almanac,
  // kept live from loop data here).
  function renderDataCells(r) {
    setTime(r, "almanac.sunrise.raw");
    setTime(r, "almanac.sun.transit.raw");
    setTime(r, "almanac.sunset.raw");
    setTime(r, "almanac(days=1).sunrise.raw");
    setTime(r, "almanac(days=1).sunset.raw");
    setTime(r, "almanac(horizon=-18).sun(use_center=1).rise.raw");
    setTime(r, "almanac(horizon=-12).sun(use_center=1).rise.raw");
    setTime(r, "almanac(horizon=-6).sun(use_center=1).rise.raw");
    setTime(r, "almanac(horizon=-6).sun(use_center=1).set.raw");
    setTime(r, "almanac(horizon=-12).sun(use_center=1).set.raw");
    setTime(r, "almanac(horizon=-18).sun(use_center=1).set.raw");
    if (typeof r["almanac(days=-1).sun.visible.raw"] === 'number' &&
        typeof r["almanac.sun.visible.raw"] === 'number') {
      setHtml("daylight", daylightString(r["almanac(days=-1).sun.visible.raw"],
                                         r["almanac.sun.visible.raw"]));
    }
    setDeg(r, "almanac.sun.az");
    setDeg(r, "almanac.sun.alt");
    setDeg(r, "almanac.sun.ra");
    setDeg(r, "almanac.sun.dec");
    setFullTime(r, "almanac.next_equinox");
    setFullTime(r, "almanac.next_solstice");
    setFullTime(r, "almanac.moon.rise");
    setFullTime(r, "almanac.moon.transit");
    setFullTime(r, "almanac.moon.set");
    setDeg(r, "almanac.moon.az");
    setDeg(r, "almanac.moon.alt");
    setDeg(r, "almanac.moon.ra");
    setDeg(r, "almanac.moon.dec");
    setStr(r, "almanac.moon_phase");
    if (typeof r["almanac.moon.phase"] === 'number') {
      setHtml("almanac.moon.phase", Math.round(r["almanac.moon.phase"]) + "% full");
    }
    setFullTime(r, "almanac.next_new_moon");
    setFullTime(r, "almanac.next_full_moon");
    setDist(r, "almanac.moon.earth_distance");
    setDist(r, "almanac.sun.earth_distance");
    setDist(r, "almanac.mercury.earth_distance");
    setDist(r, "almanac.venus.earth_distance");
    setDist(r, "almanac.mars.earth_distance");
    setDist(r, "almanac.jupiter.earth_distance");
    setDist(r, "almanac.saturn.earth_distance");
    setDist(r, "almanac.uranus.earth_distance");
    setDist(r, "almanac.neptune.earth_distance");
    setDist(r, "almanac.pluto.earth_distance");
    // Raw AU converted to light years; present when weewx-skyfield's star
    // catalog is enabled and the field is in the [LoopData] fields list.
    var proximaAU = r["almanac.proxima_centauri.earth_distance"];
    if (typeof proximaAU === 'number') {
      setHtml("almanac.proxima_centauri.earth_distance",
              (proximaAU / 63241.077).toFixed(2) + " light years");
    }
  }

  // ---- poll + local tick ---------------------------------------------------
  function localTick() {
    var nowTs = Date.now() / 1000;
    setHtml('live-clock', fmtHMS(nowTs));
    if (latest !== null) {
      moveNowLine(nowTs);
      renderCountdowns(latest, nowTs);
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
        renderDataCells(result);
        renderMoonDisc(result);
        renderCountdowns(result, nowTs);
        renderDayStrip(result, nowTs);
        renderPlanets(result);
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
