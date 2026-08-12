---
title: Configuration
layout: default
nav_order: 6
description: The CelestialReport options in weewx.conf — loop_data_file, refresh_rate, expiration_time, time_zone — the sky dome and Next Visible Pass panels, the satellite and comet sets, the countdown row, and how the page degrades across almanac tiers.
---

# Configuration

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Installing registers the report; its options live in `weewx.conf`:

```
[StdReport]
    [[CelestialReport]]
        HTML_ROOT = celestial
        enable = true
        skin = Celestial
        [[[Extras]]]
            loop_data_file = ../loop-data.txt
            refresh_rate = 2
            expiration_time = 24
            page_update_pwd = foobar
```

- `loop_data_file`: where the javascript fetches loop data; relative paths
  are relative to this report's HTML_ROOT.  The file must be reachable
  through your **web server** — if weewx-loopdata writes outside the web
  root (say `/dev/shm`) with no alias serving it, the page's badge will
  tell you: `NO DATA (HTTP 404) — check loop_data_file`.
- `refresh_rate`: seconds between loop-data polls (match weewx-loopdata's
  write cadence: 2 for the Vantage driver).
- `expiration_time`: hours the page keeps polling before requiring a click.
  An unattended browser therefore stops polling overnight instead of for
  ever; the badge reads `CLICK-ME` and a click resumes it.
- `page_update_pwd`: appending `?pageUpdate=<page_update_pwd>` to the URL
  disables expiration for that view.  The password is visible to anyone
  reading the page source, so treat it as a convenience, not a secret.
- `time_zone`: the timezone of displayed times.  By default the
  *station's* zone is auto-detected at report time, so remote viewers see
  station time.  Set an IANA name (`America/New_York`) to force a zone,
  or `browser` for the viewer's local zone.  It ships commented out in
  `skin.conf`; set it in `weewx.conf` beside the options above rather
  than uncommenting it there, because an upgrade overwrites the skin.
- `lang`: the page's language — see [Translations](i18n.md).
- `title` / `meta_title` (Extras): override the page heading and the HTML
  `<title>`.

## The sky dome, the satellites and the Next Visible Pass panel

The dome and the Next Visible Pass chart are drawn by weewx-skyfield (2.0 or
later) and embedded through a guarded search list, so a lesser almanac
costs panels, never the page.  There is nothing to configure in this
skin for them; what they show follows weewx-skyfield's own
configuration:

- **The satellite set** is `[Skyfield] [[Satellites]]` in `weewx.conf`
  (weewx-skyfield's installer defaults to the ISS and Tiangong).  The
  skin enumerates whatever is configured; each satellite needs its
  nineteen fields-line entries (see
  [Fields reference](fields-reference.md#satellites-19-entries-each)) to go live, and a
  display name is best set under `[StdReport] [[Defaults]]
  [[[Almanac]]]` so the loop feed sees it too.  The bundled
  [`--add-satellite` utility](satellites-and-comets.md#adding-and-removing-satellites) makes
  all three edits in one command.
- **The backdrop steps once a minute.**  Each report cycle renders a
  staggered set of dome backdrops (`dome-svg.txt`,
  `dome-svg-1..9.txt`), spaced `max(60 s, interval/10)` across the
  archive interval, and the open page fetches the one covering the
  current minute.  The fragments describe their own spacing, so any
  archive interval works unconfigured; if report cycles stall, the page
  keeps the freshest backdrop it has.  The Next Visible Pass chart refetches
  every five minutes and rolls over to the next pass by itself.
- **The satellite marker is honest about visibility**: drawn whenever
  the satellite is up, full brightness only when you could actually see
  it (sunlit satellite against a dark sky), dimmed otherwise.
- **The comet set** (8.1, weewx-skyfield 2.1) is `[Skyfield]
  [[Comets]]` (installer defaults: Halley and Hale-Bopp).  Each
  configured comet gets a diamond on the Geocentric dial — placed like
  a planet, its tail fanning anti-sunward, solid when naked-eye bright
  — a roster row, and a windowed perihelion countdown chip; each needs
  its six fields-line entries to go live.  The bundled
  [`--add-comet` utility](satellites-and-comets.md#adding-and-removing-comets) makes the three
  edits in one command.  The dome and the pass chart draw their own
  comet diamonds and meteor shower radiants inside weewx-skyfield's
  fragments — nothing to configure here.

## The countdown row

The chip row at the top of the page has no options of its own: the
always-on chips (the soonest visible pass, sunset/sunrise, the meteor
shower peak, and astronomical darkness — begins at the −18° sunset,
ends at the −18° sunrise, whichever is next) follow the fields line,
and the windowed guests (the next equinox or solstice — named by the
season it begins — Earth's perihelion or aphelion, the next supermoon,
the next eclipse visible from
the station, each configured comet's perihelion) appear only within
~30 days of their event — close enough for a ticking countdown to mean
something.  A day or more out a countdown reads days-hours-minutes
with the event's date beside it; inside the final day it becomes a
ticking `hh:mm:ss` clock.  Every chip is client-side arithmetic on an
event instant
weewx-loopdata computes once and caches until it passes; a chip whose
field the almanac cannot serve simply stays hidden.  (weewx-skyfield's
own Sky page shows a perihelion as a dated chip up to a year out; the
30-day window here is deliberate.)

## Adding and removing satellites and comets

Each satellite or comet takes three separate `weewx.conf` edits — its
`[Skyfield]` entry, its fields-line entries, and its display name — and
the extension bundles `--add-satellite`/`--add-comet` to make all three
in one command (with `--remove-satellite`/`--remove-comet` as exact
inverses).  That is its own page:
[Satellites and comets](satellites-and-comets.md).

## The almanac tiers

The rosters first-paint at report time from `$almanac` and then go live
from loop data.  What renders depends on the almanac WeeWX has:

| Almanac | The page |
|---|---|
| **weewx-skyfield 2.1** (satellites and comets configured) | Everything — Proxima Centauri, the sky dome, the satellite layer, the Next Visible Pass chart, the comet diamonds and the full countdown row; the footer carries the full Skyfield/DE421/Hipparcos credit |
| **weewx-skyfield 2.0** | Everything but the comets and the shower/supermoon chips (the sunset, darkness and pass chips still tick) |
| **weewx-skyfield** (earlier) | Everything but the satellites and their chart; the dome's sun/moon/planet marks step only at the backdrop step (the live-nudge hooks are 2.0's) |
| **PyEphem** | The Geocentric minus the Proxima Centauri row (PyEphem's star catalog lacks it), the sunset and darkness chips; no dome or chart — the dome panel shows an install hint |
| **built-in** | The page generates, but the panels show install hints — the built-in almanac serves none of the positions or distances the Celestial page runs on |

The footer credit is generated truthfully for whichever almanac actually
serves the page.

## The fields line

Nothing about the fields line is configured in this skin — it belongs to
weewx-loopdata — but two rules govern it, and breaking either is a
common cause of a page that will not go live:

- `[LoopData] [[Include]] fields` must stay a **bare comma-separated
  list** — no brackets, no quotes.  (Almanac entries are single-argument
  precisely so they never contain a comma.)
- Extra fields are harmless: weewx-loopdata publishes whatever you list,
  and the page reads only its own keys.  If your own pages consume other
  fields (as, for example,
  [PaloAltoWeather.com](https://www.paloaltoweather.com/celestial.html)'s
  do), keep them on the line — and never trim it to the Celestial page's set
  without checking those pages first.

Every entry the skin reads, grouped by what it feeds, plus the complete
line for hand editing, is in the
[Fields reference](fields-reference.md).
