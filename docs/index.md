---
title: Home
layout: default
nav_order: 1
permalink: /
description: A live celestial page for WeeWX — countdown central, the Geocentric panel with comets, the live sky dome with real-time satellite tracking, and the Next Visible Pass chart — updating on every loop packet via weewx-loopdata almanac fields.
---

# weewx-celestial — Watch the sky move

**Watch the sky move** — a live celestial page for WeeWX, updating on
every loop packet.

[View on GitHub](https://github.com/chaunceygardiner/weewx-celestial){: .btn .btn-primary }
[Download weewx-celestial.zip](https://github.com/chaunceygardiner/weewx-celestial/releases/latest/download/weewx-celestial.zip){: .btn }
[Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues){: .btn }

This manual documents weewx-celestial **8.1.1**, the current release.

## Start here

- **[Installation](installation.md)** — install it, wire weewx-loopdata's
  output to where the page looks, and verify the feed.  Coming from an
  earlier version instead?  [Upgrading](upgrading.md).
- **[Reading the page](reading-the-page.md)** — what every mark, color
  and phrase on the page means.  Start here once it is running.
- **[Configuration](configuration.md)** — the report's options, and how
  the page degrades across almanac tiers.
- **[Satellites and comets](satellites-and-comets.md)** — watch more than
  the installer's defaults, in one command each.
- **[Troubleshooting](troubleshooting.md)** — symptom first: the badge's
  error states, missing panels, missing chips, a page that will not go
  live.

## What it is

weewx-celestial adds one page to your WeeWX site: **the sky over your
station as it stands this second**.  Where the sun, moon and eight planets
are — the compass bearing of each, how far away it is, whether it is up or
below the horizon.  Which stars and constellations are overhead.  Which
satellites are crossing right now, and when the next one will be bright
enough to walk outside and see.  Where each comet you follow has got to.
And how long you have until sunset, until astronomical darkness, until the
next meteor shower's peak.

Not a calculator you go to with a question, and not an almanac table: a
page you leave open, on which everything moves.

It is the bundled `Celestial` skin: a row of countdown chips over three
panels — the Geocentric dial, the live sky dome, and the Next Visible Pass
chart.  Here it is entire, in the bundled sample report (Palo Alto, a July
evening at 9:12 PM — the first-quarter moon high in the southwest trailing
its wake, Mercury and Mars in the west, the freshly set sun dashed below the
horizon, Proxima Centauri alone at the rim, and every odometer ticking):

![The Celestial page](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialSampleReport.png)

Panel by panel:

**Countdown central** (new in 8.1) — ticking countdown chips at the
top of the page: the soonest visible satellite pass ("ISS · appears in
00:41:12", then "overhead now", rolling to the next pass as this one
ends), sunset or sunrise — whichever comes next — the next meteor
shower's peak with the moon's illumination at the peak, and
astronomical darkness (begins and ends, whichever is next).  Windowed
guests join within ~30 days of their
event: the next equinox or solstice — named by the season it begins —
Earth's perihelion or aphelion,
the next supermoon, the next eclipse visible from your station,
and each configured comet's perihelion.  A day or more out a countdown
reads days-hours-minutes with the event's date beside it; inside the
final day it becomes a ticking `hh:mm:ss` clock.  Every chip is
client-side
arithmetic on an event instant weewx-loopdata computes once and caches
until it passes.

The row riding through a sunset, live (1-second frames at about 15×
speed): the sunset chip counts `hh:mm:ss` down through zero, then rolls
itself to the next sunrise — loopdata expires the event and the page
follows, no reload:

![The countdown row rolling through a sunset](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialCountdown-sunset-roll.gif)

**The Geocentric** — Earth at the center, every body (sun, moon, the
eight planets, Proxima Centauri) placed by compass bearing and log
distance, the moon at its true phase, bodies below the horizon dimmed and
dashed, and an hour-long motion trail behind every dot.  Beside the dial,
a roster gives each body an odometer distance readout that ticks between
loop refreshes at the body's true radial rate (Mercury can recede ~28 km
every second while Saturn approaches at the same pace), plus the raw
astronomical-unit value and the current altitude.  With weewx-skyfield
2.1, every configured comet joins the dial and roster (8.1): a diamond
placed like a planet, its tail fanning anti-sunward from the sun's own
dial point, solid when naked-eye bright, hollow when fainter — and
honestly absent when the Minor Planet Center has dropped the comet's
elements.

Both installer-default comets on the live dial — Halley's diamond low in
the eastern sky, its three-ray tail fanning away from the sun's own dial
point, Hale-Bopp dimmed below the southern horizon — with their live
roster rows below the planets':

![The Geocentric dial with both comet diamonds and their tails](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialDial-Comets.png)

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
along the drawn arc — flipping it between the solid sunlit dot and the
hollow in-shadow ring as the satellite crosses the shadow line, in step
with the dome's marker (8.1).  When no configured satellite has a visible pass
coming, the chart hides and the roster's honest rows say why.

The same July 24 pass on this panel — the chart features it, so the
sweep dot rides the dashed arc from the 21:54 rise to the 22:05 set
while the visible-pass roster counts down beside it:

![The Next Visible Pass panel during the ISS pass](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialPassPanel-ISS-zenith.gif)

And the live flip itself, captured August 10: NOAA-21 rises sunlit into
the pre-dawn sky and drops into Earth's shadow at 48°, the sweep dot
snapping from solid to the in-shadow ring mid-ride, in step with the
dome's marker (the July 24 capture above predates the fix; its dot
stays solid to the set):

![The Next Visible Pass panel during a NOAA-21 pass, the sweep dot flipping to the in-shadow ring mid-ride](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialPassPanel-NOAA21-shadow-entry.gif)

Everything on the page moves.  The dial and roster update from
`loop-data.txt` on every loop record (for the Vantage driver, every 2
seconds), and between refreshes the page derives each body's rate of
motion from consecutive packets and advances the readouts every second —
re-anchoring to truth on the next packet, and freezing rather than
inventing data if the feed goes stale.

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
  [upgrading](upgrading.md#upgrading-from-5x-or-earlier)), and the
  `--add-satellite`/`--remove-satellite` and
  `--add-comet`/`--remove-comet` utilities that make (or unmake) every
  weewx.conf edit a satellite or comet takes in one command (see
  [Adding and removing satellites](satellites-and-comets.md#adding-and-removing-satellites)
  and [comets](satellites-and-comets.md#adding-and-removing-comets)).

The rosters first-paint at report time from `$almanac` and then go live
from loop data, so what you see depends on the almanac WeeWX has — with
weewx-skyfield 2.1 everything, and less at each tier below it, down to
the built-in almanac, which serves none of the positions the Celestial page runs
on.  The full table is under
[the almanac tiers](configuration.md#the-almanac-tiers), and the
machinery behind the motion is in
[How the page stays live](how-it-stays-live.md).

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
  required for the sky dome's satellites and the Next Visible Pass
  chart; 2.1 or later for the comets, the meteor showers and the full
  countdown row), or PyEphem
