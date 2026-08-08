---
title: Configuration
description: The CelestialReport options in weewx.conf — loop_data_file, refresh_rate, expiration_time, time_zone — the sky dome and Next Visible Pass panels, the satellite set, and how the page degrades across almanac tiers.
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
  [Installation](installation.md#fresh-install)) to go live, and a
  display name is best set under `[StdReport] [[Defaults]]
  [[[Almanac]]]` so the loop feed sees it too.  The bundled
  [`--add-satellite` utility](#adding-and-removing-satellites) makes
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

## Adding and removing satellites

A satellite is three separate `weewx.conf` edits — the
`[Skyfield] [[Satellites]]` entry, nineteen fields-line entries, and
the display name — so the extension bundles a utility that makes them
in one command, one satellite per run:

```
source /home/weewx/weewx-venv/bin/activate
cd /home/weewx/bin    # the directory CONTAINING the `user` package
                      # (~/weewx-data/bin on pip installs)
python -m user.celestial --add-satellite zenit23088=23088 --name 'Zenit-2 23088' --config /home/weewx/weewx.conf --output /tmp/weewx.conf.new
git diff --no-index --word-diff /home/weewx/weewx.conf /tmp/weewx.conf.new   # review, then move into place
```

The tag (`zenit23088` — a lowercase identifier of your choosing, refused
if it shadows a body name the almanac already serves) becomes the
satellite's report tag and loop-field name; the number is its NORAD
catalog number ([search CelesTrak](https://celestrak.org/satcat/search.php)).
`--output` writes a copy and never touches the original; `--in-place`
edits `weewx.conf` directly after making a `.bak-celestial-<version>`
backup (root-owned configurations need `sudo` for either the move or
`--in-place`).  Restart weewxd afterwards — it fetches the new
satellite's orbital elements soon after start.

Every edit is independently idempotent, so any starting state
converges: a satellite already configured per
[weewx-skyfield's manual](https://chaunceygardiner.github.io/weewx-skyfield/)
keeps its `[[Satellites]]` entry and gains the fields; re-running with a
different number or `--name` updates that piece in place (the rename
path); `--name` omitted leaves an existing name alone and merely prints
the line to add later.  Keep the list short — each satellite is a
separate CelesTrak fetch every three hours, and note that a satellite's
orbital inclination bounds the latitudes it can appear over
(weewx-skyfield's manual has the details).

`--remove-satellite zenit23088` is the exact inverse: it deletes the
`[[Satellites]]` entry, every `almanac.zenit23088.*` fields entry, and
the display name — each if present, so removing an absent satellite is
a no-op.  Two things it deliberately leaves: the cached element file
(`wxskyfield_sat_<norad>.tle`, beside the station database), and — when
you remove an installer default (`iss`, `tiangong`) — the knowledge
that a future weewx-skyfield upgrade re-adds the `[[Satellites]]` entry
(only; the fields line stays as you left it), so re-run the removal
afterwards.  The utility prints both reminders.

## The almanac tiers

The rosters first-paint at report time from `$almanac` and then go live
from loop data.  What renders depends on the almanac WeeWX has:

| Almanac | The page |
|---|---|
| **weewx-skyfield 2.0** (satellites configured) | Everything — Proxima Centauri, the sky dome, the satellite layer and the Next Visible Pass chart; the footer carries the full Skyfield/DE421/Hipparcos credit |
| **weewx-skyfield** (earlier) | Everything but the satellites and their chart; the dome's sun/moon/planet marks step only at the backdrop step (the live-nudge hooks are 2.0's) |
| **PyEphem** | The Geocentric minus the Proxima Centauri row (PyEphem's star catalog lacks it); no dome or chart — the dome panel shows an install hint |
| **built-in** | The page generates, but the panels show install hints — the built-in almanac serves none of the positions or distances this page runs on |

The footer credit is generated truthfully for whichever almanac actually
serves the page.

## The fields line

The skin consumes exactly the 75 fields listed in
[Installation](installation.md#fresh-install) — az/alt/earth_distance per
body, the moon-phase fields, `current.dateTime.raw`, and nineteen
satellite entries per configured satellite (position, sunlit, label, and
the next-pass/next-visible-pass facts).  Two rules:

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
