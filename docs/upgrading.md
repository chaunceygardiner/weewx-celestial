---
title: Upgrading
layout: default
nav_order: 3
description: Upgrading weewx-celestial to 9.0, within 8.x, or from 7.x, 6.x or 5.x and earlier — what each path needs, the files 9.0 leaves behind in the skin directory, the weewx-loopdata 7.0 declaration that 8.5 moves to, and the three 6.0 field changes with no 1:1 equivalent.
---

# Upgrading

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Find your current version below.  Every path ends the same way: the page
reads the entries listed in the [Fields reference](fields-reference.md),
and as of 8.5 it declares them to weewx-loopdata itself — the skin ships
the fixed ones, the installer writes the satellite and comet ones.

## Upgrading within 9.x

Install over the top and restart WeeWX.  Nothing in `weewx.conf` or the
skin changes, and no file has to be deleted.  Reload any page you have
open: the javascript is served with the version in its URL, so a browser
holding the previous release's copy takes the new one on the next load.

9.0.1 changes where the `LIVE` badge gets its number.  The age of the
record on show is now read from the clock of the machine that served it
— the `Date` header of the response that carried the record — rather
than worked out from the page's own two measures, which both read zero
in one real case: weewxd taking the report cycle and weewx-loopdata down
together, leaving a page that said `LIVE` over hour-old data to anyone
who opened it.  The age therefore counts publishing the file as well as
writing it, which costs well under a second; if your station and your
web server are different machines, both should keep NTP-grade time,
since skew between them lands in that number.

## Upgrading from 8.x to 9.0

Install over the top and restart WeeWX, as within 8.x.  Then delete the
sky dome's old fragment templates and the old javascript include from
the skin directory — 9.0 writes the same fragment files from a generator
instead, and its javascript is one static file (`celestial.js`) started
by a block the page generates; the install leaves the old files in
place, inert, because it only overlays files:

```
rm /home/weewx/skins/Celestial/dome-svg*.txt.tmpl \
   /home/weewx/skins/Celestial/dome-svg-frag.inc \
   /home/weewx/skins/Celestial/pass-chart.txt.tmpl \
   /home/weewx/skins/Celestial/realtime_updater.inc
```

(Your `SKIN_ROOT` may differ.)  Reload any browser page you left open
across the upgrade: the old page's script reads 9.0's pass-chart fragment
as junk and keeps whatever chart it had until a reload.  Nothing breaks
while the old files sit there; the reason to delete them is that a later
`weectl extension uninstall
celestial` removes only the files it installed and leaves a directory it
did not empty in place, so `skins/Celestial` would outlive the uninstall
holding nothing but them.  If you had edited one of those files, the
edit no longer applies — see the 9.0 entry in `changes.txt`.

Two more things to check, only if you ever pinned them.  A
`search_list_extensions` line under `[[CelestialReport]]
[[[CheetahGenerator]]]` in `weewx.conf` overrides the skin's, and the
skin's is now `user.celestial_page.CelestialPanels`.  An override still
naming `user.celestial_sky.CelestialSkyPage` leaves the page's
`$celestial` tag unbound: the page still generates (the shim still
ships), but the block that starts its javascript and every panel — the
countdown row, the Geocentric, the sky dome, the Next Visible Pass, the
footer's credit — are written by that tag, so the page comes out as its
header and empty section headings, on the dark plate whatever `theme`
says, and never goes live — its "updated" stamp stands and nothing
moves.  Name the new search list there too.  Likewise a `copy_once`
line under `[[[CopyGenerator]]]` overrides the skin's list wholesale,
and the skin's now includes `celestial.js`: an override listing only
`celestial.css, sky.js` never copies the script into `HTML_ROOT`, and
the page — static, with `celestial is not defined` in the browser
console and nothing in the WeeWX log — never goes live either.  Add
`celestial.js` to it, or drop the line.

Upgrade **weewx-skyfield to 2.3.5** while you are here, if you run it.
Neither release is required.  From **2.3.4** the panels beside the sky
dome — the two satellite rosters and the Next Visible Pass — can ask
whether there is a sky to draw without drawing one; 9.0 asks an older
weewx-skyfield the way it always has, by drawing the dome.  **2.3.5**
adds nothing this page uses, but it is a better install: it says what it
is downloading while it downloads, and it leaves alone any orbital
elements your station already has and that are still current, so an
upgrade over a running station usually makes no network request at all.

Two things you may see on the page after the upgrade, both of them the
page reporting configuration rather than anything broken:

- **"This page's report's field declaration is out of date."**  9.0 asks
  the installer's own question at generation time: are the `satellites`
  and `comets` groups in `weewx.conf` what the installer would write for
  your `[Skyfield]` sets now?  A station whose sets were edited by hand
  — or re-filled by a weewx-skyfield upgrade after a
  `--remove-satellite` — has been carrying an undeclared satellite or
  comet with no live layer, silently, until now.  Re-run `weectl
  extension install` and restart weewxd; that is the whole fix.
- **A satellite, comet or body name that reads differently.**  Names the
  report controls are now escaped where they are dropped into markup, so
  one carrying an ampersand or an angle bracket reads as written instead
  of as markup.

And one thing 9.0 makes possible that no earlier version did: the panels
can be embedded in a skin of your own — see
[Panels in your own skin](own-skin.md).  Nothing about the bundled report
changes if you do not.

## Upgrading within 8.x

Upgrade weewx-loopdata to **7.0 or later first** — 8.5 requires it, and
this extension's installer refuses to run beside an older one — then
install over the top and restart WeeWX:

```
weectl extension install weewx-loopdata.zip
weectl extension install weewx-celestial.zip
```

There are no configuration changes you have to make between 8.x releases.
The install declares the satellite and comet fields for your `[Skyfield]`
sets under the report's stanza (printing what it wrote), and the restart
both makes weewx-loopdata read the declaration and refreshes the deployed
`celestial.css` and `sky.js`.

8.5 is where the page stops reading weewx-loopdata's station-wide
`[LoopData] [[Include]] fields` line and reads its own entry of
`loop-data.txt` instead, which weewx-loopdata 7.0 writes under the
report's name from what the report declares.  Two things follow.  The
installer no longer appends anything to that line — it never writes it,
and an old one is left exactly as you have it.  That has a cost worth
knowing: 8.1–8.4's installers appended this page's ~100 fields to that
line, and weewx-loopdata 7.0 evaluates the line as a context of its own
beside the declaration, so every one of those entries is computed
**twice per loop packet** until the line is trimmed or weewx-loopdata
retires it (a later release of its own; it warns at startup while the
line stands).  The install tells you how many.  Trim this page's entries
from the line only if no other page of yours reads them —
[PaloAltoWeather.com](https://www.paloaltoweather.com/celestial.html)'s
do, for instance — or leave it for loopdata.  And the page's live values
now follow **this report's** units, formats and `[Almanac]` names rather
than loopdata's target report's: a display name in `[[CelestialReport]]`
reaches the feed, and a Celestial report in German gets German shower
names from the feed whatever language loopdata's sample report runs in.
See [Declaring fields](https://chaunceygardiner.github.io/weewx-loopdata/declaring-fields.html)
in weewx-loopdata's manual for the mechanism.

The `--migrate-loopdata-fields` utility is gone with the line it edited.
If you are coming from 5.x or earlier, see that section below: the
sequence is shorter than it was.

From 8.4 the install also settles `loop_data_file` — the URL the page
polls — for a station that has none, deriving it from where
weewx-loopdata is configured to write.  A value already in your
`weewx.conf` is never rewritten.  If yours disagrees with what the
installer worked out, it says so and leaves it alone:

```
Note: loop_data_file is ../loop-data.txt, but weewx-loopdata writes
where ../loopdata/loop-data.txt points ...
```

That is a report, not a change.  Your page kept working across the
upgrade if it was working before; the line is worth reading only if its
badge says `NO DATA (HTTP 404)`.

8.3.5 finishes what 8.3.4 began: the page's clock is now the loop
packet's own timestamp, and nothing else — not carried forward between
packets, and never the viewer's clock.  Three things look different.
The countdown chips and the satellite rosters advance on each loop
packet (every 2 s on most stations) instead of once a second; the
header's separate running clock is gone, leaving the "updated" stamp
beside the badge, now baked into the page at generation and in 24-hour
`HH:MM:SS` in every language (it read the browser's locale format
before, `03:11:22 PM` on an English page); and a page whose loop feed is not working
stands entirely still except for the badge naming the fault, where 8.3.4
kept its chips counting.  See
[Whose time it is](how-it-stays-live.md#whose-time-it-is).

The sky dome follows the same clock.  It can no longer be talked into
displaying a sky your station has not reached — which it could, briefly,
at the start of each report cycle — and it now fetches a backdrop only
when the sky is actually due to step, rather than once a minute
regardless.  Nothing to configure, and on most stations the only
difference you would notice is less traffic.  A dome that freezes and
posts a line against a station you believe is healthy has one new cause
worth checking: see
[The star field is frozen](troubleshooting.md#the-star-field-is-frozen).

8.3.4 is an internal simplification: the page now reads one clock, the
station's, for every instant it reasons about — pass rise and set times,
countdown targets, the header clock — instead of measuring some of them
against the viewer's own clock.  Once a page has its first loop packet —
normally a second or two after it loads — nothing looks different on a
machine whose clock is right.  A loop record carrying no `current.dateTime.raw`
is now ignored rather than timestamped from the browser; the declaration
this extension ships always carries it.

8.3.3 makes the Next Visible Pass chart's sweeping dot leave the chart
when the pass ends, instead of jumping back to mid-arc.  The fix reads
the pass's own rise and set from the chart, which **weewx-skyfield
2.3.2** writes there; on an older weewx-skyfield the chart carries no
times and the page keeps 8.3.2's window judgement — the dot returns
to its drawn place at set.  Upgrade both.

8.3 adds the light plate.  Nothing moves on your page: `theme` defaults
to `dark`, which is the page exactly as it was.  Set `theme = light` (or
`auto`) in `[[CelestialReport]]` — beside `lang`, not inside
`[[[Extras]]]` — to take it, and see
[Dark, light and auto](configuration.md#dark-light-and-auto).  The dome
and the Next Visible Pass chart follow the page onto the paper plate,
which needs **weewx-skyfield 1.15 or later** (2.2 for its own contrast
pass); without weewx-skyfield the page has no charts to match and stays
dark whatever the option says.

One note for 8.2: half of its contrast pass — the Geocentric dial's grid,
its below-horizon marks and trails, and the sky dome's star and
constellation names — lands with this install.  The other half lives
inside the dome and the Next Visible Pass chart, which draw their own
colors, and arrives only when **weewx-skyfield 2.2** is installed: their
altitude rings and meridian cross stay invisible until then, and the
dome's Mars stays a shade darker than the dial's.  Upgrade both.

## Upgrading from 7.x

Upgrade weewx-loopdata to 7.0 or later, install this version right over
the existing one, then restart WeeWX —

```
weectl extension install weewx-loopdata.zip
weectl extension install weewx-celestial.zip
```

Nothing lights up the new layers but the install itself: the page
declares every field it reads — the satellite layer (8.0), the countdown
chips and the comets (8.1) included — the fixed ones from the skin, the
satellite and comet ones written by the installer for your `[Skyfield]`
sets.  Your old fields line is neither needed nor touched.

Run weewx-skyfield 2.3.5 — 2.1 brought the comets and the
shower/supermoon chips, 2.3.2 the pass chart's own rise and set that
lets its dot leave the chart when the pass ends, and 2.3.4 the
`can_draw()` answer the panels beside the dome now stand on; 2.0 still
serves the satellites, and the sunset, darkness and pass chips count on
any of them.
An almanac that cannot serve a field omits it, and the page simply hides
that layer or chip.

{: .note }
Upgrading replaces the bundled skin (`skins/Celestial/`, including its
`lang/` files).  Local additions survive upgrades best as
`[[[Almanac]]]`/`[[[Texts]]]` entries in the report's section of
`weewx.conf` — see [Translations](i18n.md).

## Upgrading from 6.x

1. Upgrade weewx-loopdata to 7.0 or later — this extension's installer
   refuses to run beside an older one, so do it before the uninstall
   below leaves you without a page:

   ```
   weectl extension install weewx-loopdata.zip
   ```

1. Uninstall the old version, then install the new one:

   ```
   weectl extension uninstall celestial
   weectl extension install weewx-celestial.zip
   ```

   (The uninstall removes the report's whole `[[CelestialReport]]`
   stanza — `[[[Extras]]]` settings of your own, and any group of your
   own under `[[[LoopData]]]`, included.  Keep a copy to put back.)

1. Restart WeeWX.  (The restart also refreshes the deployed
   `celestial.css`, `celestial.js` and `sky.js` — CopyGenerator
   re-copies `copy_once` files on every report first-run — and the page
   version-tags all three URLs, so browsers refetch them too.)

Your existing fields line is no longer read by this page at all: 8.5
declares what it reads itself (see the
[Fields reference](fields-reference.md)), and the line is left as it is
for whatever pages of your own still read it, until weewx-loopdata
retires it.  While it stands, the entries on it that this page also
declares are evaluated twice per loop packet — the install counts them —
so trim this page's entries from it if nothing else reads them.

{: .important }
If you still list `user.celestial.Celestial` under `data_services` in
`[Engine] [[Services]]` — a leftover from 2.x that 6.x tolerated with a
stub — **remove it now**.  7.0 deleted the stub, and a stale entry will
keep weewxd from starting.

## Upgrading from 5.x or earlier

6.0 removed this extension's own loop fields (`current.sunrise`,
`current.earthMarsDistance`, `current.moonWaxing`, …); almanac fields
replace them, and as of 8.5 the page declares the ones it reads to
weewx-loopdata itself, so your old fields line needs no rewriting for
this page's sake (there was a `--migrate-loopdata-fields` utility for
that through 8.4; it is gone).  The sequence:

1. **Upgrade weewx-loopdata to 7.0 or later** (and install
   [weewx-skyfield](https://chaunceygardiner.github.io/weewx-skyfield/)
   2.3.5+ if you have not already).  This extension's installer refuses
   to run beside an older weewx-loopdata, so do it first — before the
   uninstall below leaves you without a page.

1. **Uninstall the old version** (required — see the 6.x note above about
   `data_services`):

   ```
   weectl extension uninstall celestial
   ```

   `weectl extension install` over an existing version only overlays
   files; it never reverses what the old version registered.
   Uninstalling first (while the old install record still exists) removes
   the old service registration and the bundled
   `celestial_de421.bsp`/`celestial_stars.dat` files.  If those linger,
   delete `user.celestial.Celestial` from `data_services` in
   `[Engine] [[Services]]` and remove the two orphaned `celestial_*` data
   files from `bin/user` by hand.

1. Install this version.  It declares every field
   the page reads, the satellite and comet ones for whatever
   `[Skyfield]` `[[Satellites]]` and `[[Comets]]` you have (the
   installer defaults — iss and tiangong; halley and hale_bopp — when
   there is no section to follow), and prints what it wrote.

1. Restart WeeWX.

Your old `[LoopData] [[Include]] fields` line still carries the 5.x
entries (`current.sunrise.raw`, `current.moonPhase`, …).  This page never
reads them, weewx-loopdata logs each one it cannot evaluate and moves on,
and it retires the whole line in a later release (any entry on it that
this page declares as well is evaluated twice per packet meanwhile; the
install counts those); a page of your own
that read them has been without them since 6.0 and wants the almanac
equivalents below.

### The almanac equivalents

If your own pages read the old fields, these are the almanac spellings
that replace them on a declaration of your own (see weewx-loopdata's
[Declaring fields](https://chaunceygardiner.github.io/weewx-loopdata/declaring-fields.html)).
Raw times and durations carry a **pinned unit** (`.unix_epoch`,
`.second`) so they keep the old fields' fixed meanings — epoch seconds,
seconds of daylight — whatever the report's `[Units]` say.  Pre-3.0
PascalCase names (`Sunrise`, `EarthMoonDistance`, `daySunshineDur`) map
the same way as their camelCase successors.

| Old field (`current.<name>`) | Raw (`.raw`) | Formatted |
|---|---|---|
| `sunrise`, `sunset` | `almanac.sunrise.unix_epoch.raw`, `almanac.sunset.unix_epoch.raw` | `almanac.sunrise`, `almanac.sunset` |
| `sunTransit` | `almanac.sun.transit.unix_epoch.raw` | `almanac.sun.transit` |
| `tomorrowSunrise`, `tomorrowSunset` | `almanac(days=1).sunrise.unix_epoch.raw`, `almanac(days=1).sunset.unix_epoch.raw` | `almanac(days=1).sunrise`, `almanac(days=1).sunset` |
| `daylightDur` (`daySunshineDur`) | `almanac.sun.visible.second.raw` | `almanac.sun.visible` |
| `yesterdayDaylightDur` | `almanac(days=-1).sun.visible.second.raw` | `almanac(days=-1).sun.visible` |
| `astronomicalTwilightStart` / `End` | `almanac(horizon=-18).sun(use_center=1).rise.unix_epoch.raw` / `.set.unix_epoch.raw` | `almanac(horizon=-18).sun(use_center=1).rise` / `.set` |
| `nauticalTwilightStart` / `End` | `almanac(horizon=-12).sun(use_center=1).rise.unix_epoch.raw` / `.set.unix_epoch.raw` | `almanac(horizon=-12).sun(use_center=1).rise` / `.set` |
| `civilTwilightStart` / `End` | `almanac(horizon=-6).sun(use_center=1).rise.unix_epoch.raw` / `.set.unix_epoch.raw` | `almanac(horizon=-6).sun(use_center=1).rise` / `.set` |
| `moonrise`, `moonset`, `moonTransit` | `almanac.moon.rise.unix_epoch.raw`, `almanac.moon.set.unix_epoch.raw`, `almanac.moon.transit.unix_epoch.raw` | `almanac.moon.rise`, `almanac.moon.set`, `almanac.moon.transit` |
| `nextEquinox`, `nextSolstice` | `almanac.next_equinox.unix_epoch.raw`, `almanac.next_solstice.unix_epoch.raw` | `almanac.next_equinox`, `almanac.next_solstice` |
| `nextFullMoon`, `nextNewMoon` | `almanac.next_full_moon.unix_epoch.raw`, `almanac.next_new_moon.unix_epoch.raw` | `almanac.next_full_moon`, `almanac.next_new_moon` |
| `moonPhase`, `moonPhaseIndex` | `almanac.moon_phase`, `almanac.moon_index` | (same) |
| `moonFullness` | `almanac.moon.phase` (a raw percent — see below) | (same) |
| `<body>Azimuth`, `<body>Altitude` | `almanac.<body>.az`, `almanac.<body>.alt` (plain degrees) | `almanac.<body>.azimuth`, `almanac.<body>.altitude` |
| `<body>RightAscension`, `<body>Declination` | `almanac.<body>.ra`, `almanac.<body>.dec` | `almanac.<body>.topo_ra`, `almanac.<body>.topo_dec` |
| `earth<Body>Distance` | `almanac.<body>.earth_distance` (raw AU — see below) | (same) |

`<body>` is `sun`, `moon`, `mercury`, `venus`, `mars`, `jupiter`,
`saturn`, `uranus`, `neptune` or `pluto` (`proxima_centauri` for the
distance).

### The three changes with no 1:1 equivalent

If your own pages read the old fields:

- **Distances arrive as raw astronomical units** (the value reports show),
  no longer miles/km — convert in the page (× 92,955,807 miles/AU or
  × 149,597,870 km/AU).  Proxima Centauri is AU as well, no longer light
  years (÷ 63,241.077 AU/ly).
- **`almanac.moon.phase`** (the `moonFullness` replacement) is a raw
  percent (e.g. `33.6`), no longer a formatted string.
- **`moonWaxing` is gone**: the moon is waxing exactly when
  `almanac.next_full_moon.unix_epoch.raw <
  almanac.next_new_moon.unix_epoch.raw` (the bundled skin shows the
  derivation).

The `[Celestial]` section of weewx.conf (`enable`, `update_rate_secs`,
`stars`) is obsolete and can be deleted.  The Skyfield and NumPy libraries
are no longer required by this extension (weewx-skyfield requires them,
and has its own ephemeris and star catalog).
