---
title: weewx-celestial — Watch the sky move
description: A live celestial page for WeeWX — the Geocentric panel — every body placed by compass bearing and log distance, updating on every loop packet via weewx-loopdata almanac fields.
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
built around a single panel: **the Geocentric** — Earth at the center,
every body (sun, moon, the eight planets, Proxima Centauri) placed by
compass bearing and log distance, the moon at its true phase, bodies below
the horizon dimmed and dashed, and an hour-long motion trail behind every
dot.  Beside the dial, a roster gives each body an odometer distance
readout that ticks between loop refreshes at the body's true radial rate
(Mercury can recede ~28 km every second while Saturn approaches at the
same pace), plus the raw astronomical-unit value and the current altitude.

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
  [upgrading](installation.md#upgrading-from-5x-or-earlier)).

The roster first-paints at report time from `$almanac` and then goes live
from loop data.  What you see depends on the almanac WeeWX has: with
**weewx-skyfield** (stars on), everything, Proxima included.  With
**PyEphem** (no weewx-skyfield), everything except the Proxima Centauri
row.  With only WeeWX's **built-in almanac**, the page generates but the
panel stays empty and shows an install hint — the built-in almanac serves
none of the positions or distances this page runs on, which is why
weewx-skyfield is strongly recommended.

For sky *charts* — the sky dome, sun path, orrery, analemma, solar year,
lunation and rise/set timeline — see weewx-skyfield's own
[Sky page](https://chaunceygardiner.github.io/weewx-skyfield/sky-page.html):
as of 7.0 this skin no longer embeds them.  weewx-skyfield is the atlas;
weewx-celestial is the live instrument.

## Requirements

- Python 3.9 or later
- WeeWX 5.2 or later
- [weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata)
  5.0 or later
- [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield)
  strongly recommended (required for Proxima Centauri), or PyEphem

## License

weewx-celestial is Copyright © 2022–2026 John A Kline and is licensed
under the GNU Public License v3.
