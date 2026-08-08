---
title: weewx-celestial — Watch the sky move
description: A live celestial page for WeeWX — the Geocentric panel, the live sky dome with real-time satellite tracking, and the Next Visible Pass chart — updating on every loop packet via weewx-loopdata almanac fields.
---

# weewx-celestial

**Watch the sky move** — a live celestial page for WeeWX, updating on
every loop packet.

[Installation](installation.md) ·
[Configuration](configuration.md) ·
[The Geocentric in your skin](own-skin.md) ·
[Translating (i18n)](i18n.md) ·
[GitHub project](https://github.com/chaunceygardiner/weewx-celestial)

---

weewx-celestial ships a live celestial page (the bundled `Celestial` skin)
built from three panels:

**The Geocentric** — Earth at the center, every body (sun, moon, the
eight planets, Proxima Centauri) placed by compass bearing and log
distance, the moon at its true phase, bodies below the horizon dimmed and
dashed, and an hour-long motion trail behind every dot.  Beside the dial,
a roster gives each body an odometer distance readout that ticks between
loop refreshes at the body's true radial rate (Mercury can recede ~28 km
every second while Saturn approaches at the same pace), plus the raw
astronomical-unit value and the current altitude.

**The sky dome** (new in 8.0) — everything above the horizon right now:
weewx-skyfield's own dome chart, the full Hipparcos star field and
constellation figures included, embedded as a live instrument.  Each
report cycle renders a staggered set of backdrops a minute apart and the
open page steps to the one covering the current minute, while the
sun/moon/planet marks are nudged between steps at loop-derived rates.
With weewx-skyfield 2.0's satellites configured, the dome carries the one
thing up there that genuinely moves fast: the satellite marker crossing
in real time — drawn whenever the satellite is up, dimmed unless you
could actually see it (sunlit satellite, dark sky) — beside a roster of
each satellite's next pass of any kind, tagged visible or not.

The dome during the ISS's July 24 near-zenith visible pass (replayed
through the live page with the orbital elements Space-Track archived
that day; 2-second frames played at about 30× speed).  The full-brass
dot crosses the whole dome NW → SE, and near the end it snaps to a
hollow ring as the ISS enters Earth's shadow — how visible passes
really end:

![The sky dome during an ISS near-zenith pass](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialDome-ISS-zenith.gif)

**The Next Visible Pass** (new in 8.0) — the whole sky as it will stand at the
culmination of the soonest upcoming *visible* pass, the pass's arc dashed
across it under a dated head line, with the visible-pass roster beside
it.  During the pass itself the page sweeps the satellite's dot live
along the drawn arc.  When no configured satellite has a visible pass
coming, the chart hides and the roster's honest rows say why.

The same July 24 pass on this panel — the chart features it, so the
sweep dot rides the dashed arc from the 21:54 rise to the 22:05 set
while the visible-pass roster counts down beside it:

![The Next Visible Pass panel during the ISS pass](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialPassPanel-ISS-zenith.gif)

Everything on the page moves.  The dial and roster update from
`loop-data.txt` on every loop record (for the Vantage driver, every 2
seconds), and between refreshes the page derives each body's rate of
motion from consecutive packets and advances the readouts every second —
re-anchoring to truth on the next packet, and freezing rather than
inventing data if the feed goes stale.

The bundled sample report (Palo Alto, a July evening at 9:12 PM — the
first-quarter moon high in the southwest trailing its wake, Mercury and
Mars in the west, the freshly set sun dashed below the horizon, Proxima
Centauri alone at the rim, and every odometer ticking):

![The Celestial page](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialSampleReport.png)

## How it works

The live values are **weewx-loopdata almanac fields**: report almanac tags
(computed by the registered almanac, ideally
[weewx-skyfield](https://chaunceygardiner.github.io/weewx-skyfield/)'s)
that [weewx-loopdata](https://chaunceygardiner.github.io/weewx-loopdata/)
evaluates on every loop packet and publishes in `loop-data.txt`.  One
computation engine serves the report tags and the live page, so they
always agree.  This extension runs no service and computes nothing itself.

What installs:

- The `Celestial` skin (the sample report), registered as
  `CelestialReport`.
- The `--migrate-loopdata-fields` command-line utility (see
  [upgrading](installation.md#upgrading-from-5x-or-earlier)), and the
  `--add-satellite`/`--remove-satellite` utility that makes (or unmakes)
  every weewx.conf edit a satellite takes in one command (see
  [Adding and removing satellites](configuration.md#adding-and-removing-satellites)).

The rosters first-paint at report time from `$almanac` and then go live
from loop data.  What you see depends on the almanac WeeWX has: with
**weewx-skyfield 2.0** (satellites configured), everything — Proxima, the
dome, the Next Visible Pass chart and the live satellite layer.  With an earlier
**weewx-skyfield**, everything but the satellites and their chart.  With
**PyEphem** (no weewx-skyfield), the Geocentric minus the Proxima
Centauri row, and no dome or chart.  With only WeeWX's **built-in
almanac**, the page generates but the panels show install hints — the
built-in almanac serves none of the positions or distances this page runs
on, which is why weewx-skyfield is strongly recommended.

For the rest of the sky *atlas* — sun path, orrery, analemma, solar year,
lunation and rise/set timeline — see weewx-skyfield's own
[Sky page](https://chaunceygardiner.github.io/weewx-skyfield/sky-page.html).
The two remain complementary: weewx-skyfield is the atlas (its dome is a
report-time snapshot); weewx-celestial is the live instrument, and as of
8.0 its embedded dome is the live edition of the same chart.

## Requirements

- Python 3.9 or later
- WeeWX 5.2 or later
- [weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata)
  6.9 or later
- [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield)
  strongly recommended (required for Proxima Centauri; 2.0 or later
  required for the sky dome's satellites and the Next Visible Pass chart), or
  PyEphem

## License

weewx-celestial is Copyright © 2022–2026 John A Kline and is licensed
under the GNU Public License v3.
