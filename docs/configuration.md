---
title: Configuration
description: The CelestialReport options in weewx.conf — loop_data_file, refresh_rate, expiration_time, time_zone — and how the page degrades across almanac tiers.
---

# Configuration

[Home](index.md) ·
[Installation](installation.md) ·
[The Geocentric in your skin](own-skin.md) ·
[Translating (i18n)](i18n.md) ·
[GitHub project](https://github.com/chaunceygardiner/weewx-celestial)

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
- `expiration_time`: hours the page keeps polling before requiring a click
  (`?pageUpdate=<page_update_pwd>` in the URL disables expiration).  Note
  the password is visible to anyone reading the page source.
- `time_zone` (skin.conf `[Extras]`, commented out by default): the
  timezone of displayed times.  By default the *station's* zone is
  auto-detected at report time, so remote viewers see station time.  Set
  an IANA name (`America/New_York`) to force a zone, or `browser` for the
  viewer's local zone.
- `lang`: the page's language — see [Translating (i18n)](i18n.md).
- `title` / `meta_title` (Extras): override the page heading and the HTML
  `<title>`.

## The almanac tiers

The roster first-paints at report time from `$almanac` and then goes live
from loop data.  What renders depends on the almanac WeeWX has:

| Almanac | The page |
|---|---|
| **weewx-skyfield** (stars on) | Everything, Proxima Centauri included; the footer carries the full Skyfield/DE421/Hipparcos credit |
| **PyEphem** | Everything except the Proxima Centauri row (PyEphem's star catalog lacks it) |
| **built-in** | The page generates, but the panel stays empty with an install hint — the built-in almanac serves none of the positions or distances this page runs on |

The footer credit is generated truthfully for whichever almanac actually
serves the page.

## The fields line

The skin consumes exactly the 37 fields listed in
[Installation](installation.md#fresh-install) — az/alt/earth_distance per
body, the moon-phase fields, and `current.dateTime.raw`.  Two rules:

- `[LoopData] [[Include]] fields` must stay a **bare comma-separated
  list** — no brackets, no quotes.  (Almanac entries are single-argument
  precisely so they never contain a comma.)
- Extra fields are harmless: weewx-loopdata publishes whatever you list,
  and the page reads only its own keys.  If your own pages consume other
  fields (as, for example,
  [PaloAltoWeather.com](https://www.paloaltoweather.com/celestial.html)'s
  do), keep them on the line.

The full almanac-field grammar (any report almanac tag with the `$`
removed, plus the `almanac(days=±N)` tomorrow/yesterday extension) is
documented in
[weewx-loopdata's manual](https://chaunceygardiner.github.io/weewx-loopdata/almanac-fields.html).
