---
title: The Geocentric in your skin
description: Lifting the live Geocentric panel — or building your own live celestial page — from weewx-loopdata almanac fields, with the bundled skin as the reference implementation.
---

# The Geocentric in your skin

[Home](index.md) ·
[Installation](installation.md) ·
[Configuration](configuration.md) ·
[Translating (i18n)](i18n.md) ·
[GitHub project](https://github.com/chaunceygardiner/weewx-celestial)

---

Everything the sample skin does is ordinary weewx-loopdata consumption:
list the almanac fields you want in `[LoopData] [[Include]] fields`, give
your HTML elements ids equal to the json keys, and poll `loop-data.txt`
from javascript.  `skins/Celestial/realtime_updater.inc` is the reference
implementation — the dial, the rate derivation (two consecutive packets
give each body its motion; the one-second tick extrapolates between
refreshes) and the odometer are self-contained functions you can lift,
and `skins/Celestial/celestial.css` holds every color.

A few of the ideas worth stealing even if you build something quite
different:

- **Rates from consecutive packets.**  Two loop packets give every
  numeric field a per-second rate (azimuth wrap-aware); the page then
  advances its readouts every second between refreshes and re-anchors to
  truth on each packet.  Extrapolation stops after a stale-feed cutoff,
  so a dead feed freezes rather than drifts into fiction.
- **Dual-source cells.**  Every value cell first-paints at report time
  from `$almanac` (each cell individually guarded, so a less capable
  almanac leaves cells empty rather than failing the page) and then goes
  live from loop data — the page is never blank while it waits for its
  first packet.
- **A truthful badge.**  The LIVE badge reports the feed's actual state:
  packet age, `OFFLINE` on network failure, and
  `NO DATA (HTTP 404) — check loop_data_file` when the web server is not
  serving the loop-data file where the page expects it.

The full almanac-field grammar is documented in
[weewx-loopdata's manual](https://chaunceygardiner.github.io/weewx-loopdata/almanac-fields.html);
loopdata's own
[Build a live page](https://chaunceygardiner.github.io/weewx-loopdata/build-a-live-page.html)
covers the general pattern.

## The Geocentric Live on PaloAltoWeather.com

[PaloAltoWeather.com's Celestial Today page](https://www.paloaltoweather.com/celestial.html)
contains a Geocentric Live panel built with the same technologies as used
here ([weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield)
and [weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata)).

![PaloAltoWeather.com Celestial Today page](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/PAW_Celestial_Today.png)
