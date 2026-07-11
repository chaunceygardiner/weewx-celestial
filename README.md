# weewx-celestial
Open source plugin for WeeWX software.

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)

**This extension requires Python 3.9 or later, WeeWX 5.2 or later, and the Skyfield and NumPy libraries.**


## Description

Celestial is a WeeWX service that inserts celestial observations into loop packets.
The information is then available via
[weewx-loopdata plugin](https://github.com/chaunceygardiner/weewx-loopdata), as `current.<celestial-obs>`

As of version 2.0, weewx-celestial uses [Skyfield](https://rhodesmill.org/skyfield/) for *much* more accurate
information than [PyEphem](https://rhodesmill.org/pyephem/index.html), which is currently used by WeeWX.

The bundled sample report (Palo Alto, a July evening at 9:12 PM — first-quarter moon in the
west, the brass now-line in the dusk gradient, and the seven weewx-skyfield sky charts):
![Celestial Sample Report](CelestialSampleReport.png)

As of version 4.0, the sample report is a live "night-palette" page: a true-phase moon disc, a
day strip showing the twilight bands with rise/set ticks and a pulsing "now" line that moves in
real time, countdown chips for the next full/new moon and equinox/solstice, planets-now chips
(up/down, altitude, compass direction, distance, one identity color per body), and the full data
cards — all updated by javascript from the loop-data.txt file on every loop record (for the
Vantage driver, that happens every 2 seconds).  The data cells are additionally computed at
report generation time when a capable almanac is available (weewx-skyfield, or WeeWX's built-in
PyEphem almanac) so the page first-paints populated; without an extended almanac the page still
generates and the javascript fills everything in.  The new visual components require the 4.0
loop fields in the `[LoopData]` fields list; without them the page works and those components
simply stay empty.  **You do not need to edit the fields list by hand** — a bundled utility
updates it in one command (see the Upgrade Instructions below).

As of version 5.0, the sample report also carries sky charts drawn at report generation
time when the [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) extension is
installed: the sky dome, the rise-and-set timeline, the orrery and the analemma (see "Install
weewx-skyfield too" below).  Without weewx-skyfield, each of those panels shows a short install
hint and the rest of the page is unaffected.  Version 5.1 adds three more: the sun's path for
today, the solar year, and the lunar month.  These need weewx-skyfield 1.7 or later — with an
older weewx-skyfield the three new panels show a short upgrade hint while the original four
keep drawing.

As of version 4.0, each observation is recomputed only as often as it can change: positions,
distances and the moon's phase on every loop record (about 20 ms on a Raspberry Pi 5); rise/set,
twilight and daylight times once per local day; and the next equinox/solstice/full/new moon only
when one passes.  Every loop record still carries every field.  (Versions 2.3 through 3.x instead
recomputed everything on a ten-second cycle, because a full recompute was too expensive to run
per record.)

As of version 4.2 the bundled JPL DE421 ephemeris is read fully into memory at startup (about
16 MB), so upgrading this extension over a running WeeWX cannot disturb — or crash — the running
service; the new files take effect on the restart that follows the install.

Versions 3.x of weewx-celestial also replaced WeeWX's built-in almanac for report generation.
As of version 4.0 it no longer does: that job now belongs to the independent
[weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) extension (same author),
whose almanac engine grew out of this extension's.

### Install weewx-skyfield too (recommended, not required)

Installing [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) (same author)
alongside this extension is recommended.  The two are designed to run side by side and need no
configuration to coexist.  It completes the picture in two ways:

- **The sample report's seven sky-chart panels are drawn by weewx-skyfield**: a sky dome of
  everything above the horizon now (sun, true-phase moon, planets, and the brightest named
  stars sized by magnitude), a midnight-to-midnight rise-and-set timeline for the sun, moon
  and planets over the twilight bands, an orrery (solar-system plan view), the analemma,
  the sun's altitude-and-azimuth path for today (moon path dashed alongside), the solar
  year (sunrise, sunset and solar noon for every week of the year), and the lunar month
  (the current lunation as a strip of phase discs).  The last three need weewx-skyfield
  1.7 or later.
- **Report tags computed with Skyfield** — weewx-celestial does not touch report generation;
  report tags such as `$almanac.sunrise` are served by whatever almanac WeeWX has.
  weewx-skyfield serves them from the same definitions as these loop fields, plus much more
  (planet magnitudes and angular sizes, named-star tags such as `$almanac.rigel.rise`, any
  Hipparcos star via `$almanac.hip_57939`, heliocentric coordinates, librations, and so on).

Without weewx-skyfield, everything still works, minus the above: each sky-chart panel shows a
short install hint in its place, and reports fall back to WeeWX's built-in PyEphem/weeutil
almanac.  The bundled sample report generates either way: cells a capable almanac can fill are
rendered at report generation time, and javascript fills and updates every cell live from loop
data regardless.

The information available in loop records is based on WeeWX's Seasons Report (Copyright Tom Keffer
and Matthew Wall).  More fields are provided than in the Seasons report, including start/end times
for astronomical and nautical twilight.  Also, distances from earth to the other planets (and Pluto);
as well as the current distance to the moon and sun.

The following observations are available in the LOOP packet (names as of version 3.0):

- `astronomicalTwilightEnd`
- `astronomicalTwilightStart`
- `civilTwilightEnd`
- `civilTwilightStart`
- `daylightDur`
- `earthJupiterDistance`
- `earthMarsDistance`
- `earthMercuryDistance`
- `earthNeptuneDistance`
- `earthMoonDistance`
- `earthPlutoDistance`
- `earthProximaCentauriDistance` (light years in every unit system; needs the star catalog, i.e., `stars = true`)
- `earthSaturnDistance`
- `earthSunDistance`
- `earthUranusDistance`
- `earthVenusDistance`
- `jupiterAltitude`
- `jupiterAzimuth`
- `marsAltitude`
- `marsAzimuth`
- `mercuryAltitude`
- `mercuryAzimuth`
- `moonAltitude`
- `moonAzimuth`
- `moonDeclination`
- `moonFullness`
- `moonPhase`
- `moonPhaseIndex` (index into the moon-phases list: 0 = new .. 4 = full .. 7 = waning crescent)
- `moonRightAscension`
- `moonrise`
- `moonset`
- `moonTransit`
- `moonWaxing` (1 while the moon is waxing, else 0)
- `nauticalTwilightEnd`
- `nauticalTwilightStart`
- `neptuneAltitude`
- `neptuneAzimuth`
- `nextEquinox`
- `nextFullMoon`
- `nextNewMoon`
- `nextSolstice`
- `plutoAltitude`
- `plutoAzimuth`
- `saturnAltitude`
- `saturnAzimuth`
- `sunAltitude`
- `sunAzimuth`
- `sunDeclination`
- `sunRightAscension`
- `sunrise`
- `sunset`
- `sunTransit`
- `tomorrowSunrise`
- `tomorrowSunset`
- `uranusAltitude`
- `uranusAzimuth`
- `venusAltitude`
- `venusAzimuth`
- `yesterdayDaylightDur`

## Adding the live celestial panels to your own skin

The sample report's live components are deliberately framework-free: one Cheetah include
produces a single `<script>` block, and each component finds its place in your page by element
id.  You can lift exactly the pieces you want into any WeeWX skin — this is how the
[paloaltoweather.com celestial pages](https://www.paloaltoweather.com/celestial.html) are built
(see "See it in action" below).

1. **Serve the loop fields.**  Install
   [weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata) and add the celestial
   fields to the `[LoopData] [[Include]] [[[fields]]]` line in `weewx.conf` (the full line is in
   the Installation Instructions below).  weewx-loopdata then rewrites `loop-data.txt` on every
   loop record — that file is the page's only data source.

1. **Include the updater.**  Copy `skins/Celestial/realtime_updater.inc` into your skin's
   directory and add `#include "realtime_updater.inc"` inside your template's `<body>` (your
   report must use WeeWX's CheetahGenerator; every stock skin does).  Configure it through your
   report's `[[[Extras]]]`:

   ```
   [[[Extras]]]
       loop_data_file = ../loop-data.txt   # path to loop-data.txt, relative to this report
       refresh_rate = 2                    # seconds between polls; match loopdata's write cadence
       expiration_time = 24                # hours before the page stops polling
       #time_zone = America/New_York       # optional; defaults to the station's zone.
                                           # 'browser' = the viewer's timezone.
   ```

1. **Data cells: give an element the loop-data key as its id.**  The updater writes into
   whatever elements exist and silently skips the rest, so use only the cells you want:

   ```html
   Sunrise: <span id="current.sunrise.raw"></span>
   Sun altitude: <span id="current.sunAltitude.raw"></span>
   Distance to Mars: <span id="current.earthMarsDistance"></span>
   Next full moon: <span id="current.nextFullMoon"></span>
   ```

   `.raw` time ids render as `HH:MM:SS AM/PM` in the display timezone; `.raw` angle ids as one
   decimal with a degree sign; distance ids gain thousands separators; `current.nextFullMoon`
   and its like render as full date+times.  The authoritative map of which ids exist and how
   each renders is the short, readable `renderDataCells` function at the bottom of
   `realtime_updater.inc`.

1. **The visual components mount on fixed ids.**  Each renders itself into (or under) a
   specific element, and a component whose element is absent simply does not run:

   ```html
   <div id="moon-disc"></div>     <!-- the true-phase moon disc -->
   <div id="day-strip"></div>     <!-- twilight bands, rise/set ticks, moving now-line -->
   <div class="count" id="count-fullmoon"><span class="k">full moon</span><span class="v mono"></span><span class="d"></span></div>
   <div class="chip" id="planet-mars"><span class="dot dot-mars"></span><div><div class="chipname">Mars</div><div class="chipline mono"></div><div class="chipsub mono"></div></div></div>
   ```

   The countdown chips exist for `count-fullmoon`, `count-newmoon`, `count-equinox` and
   `count-solstice`; the planet chips for `planet-mercury` through `planet-pluto`.  Copy the
   markup from `skins/Celestial/index.html.tmpl` and the classes these components use from
   `skins/Celestial/celestial.css` (`moon-*`, `band-*`, `tick-*`, `nowline`, `gridlab`,
   `nowlab`, the `.count` and `.chip` families) — restyle them there freely.  Keep color
   literals in the CSS, not the template: Cheetah owns `#`, and a hex color in a template is a
   parsing accident waiting to happen.

1. **First paint (optional).**  Cells are empty until the first poll (at most `refresh_rate`
   seconds).  The sample report also renders report-time values into the same cells with
   `$almanac` tags so the page arrives populated; see any data cell in
   `skins/Celestial/index.html.tmpl` for the pattern.

1. **Missing fields are harmless.**  Every read in the updater is guarded: a field you left out
   of the `[LoopData]` fields line leaves its own cell alone and never breaks the rest of the
   page.

### Deprecated loop field names

The loop fields were renamed in version 3.0 to follow WeeWX's lowerCamelCase convention for
observation names (e.g., `outTemp`, `windSpeed`).  In addition, `daySunshineDur` and
`yesterdaySunshineDur` were renamed to `daylightDur` and `yesterdayDaylightDur`, because they
measure the time the sun is above the horizon (daylight), not "sunshine duration" in the
meteorological sense of measured bright sunshine.

In 3.x releases, every value was written to the loop packet under both its new name and its
old (pre-3.0) name.  **As of version 4.0, the old names are no longer emitted** — your
`weewx.conf` and any custom skins must use the new names.  **There is no need to edit
`weewx.conf` by hand**: the bundled `--migrate-loopdata-fields` utility renames every
deprecated field in your `[LoopData]` fields line automatically (see the Upgrade Instructions
below).  The table that follows is the reference for updating custom skins and javascript,
which the utility cannot see:

| Deprecated (removed in 4.0) | Use instead |
|---|---|
| `AstronomicalTwilightEnd` / `AstronomicalTwilightStart` | `astronomicalTwilightEnd` / `astronomicalTwilightStart` |
| `CivilTwilightEnd` / `CivilTwilightStart` | `civilTwilightEnd` / `civilTwilightStart` |
| `daySunshineDur` | `daylightDur` |
| `EarthJupiterDistance` … `EarthVenusDistance` (all ten) | `earthJupiterDistance` … `earthVenusDistance` |
| `MoonAltitude`, `MoonAzimuth`, `MoonDeclination` | `moonAltitude`, `moonAzimuth`, `moonDeclination` |
| `MoonFullness`, `MoonPhase`, `MoonRightAscension` | `moonFullness`, `moonPhase`, `moonRightAscension` |
| `Moonrise`, `Moonset`, `MoonTransit` | `moonrise`, `moonset`, `moonTransit` |
| `NauticalTwilightEnd` / `NauticalTwilightStart` | `nauticalTwilightEnd` / `nauticalTwilightStart` |
| `NextEquinox`, `NextFullMoon`, `NextNewMoon`, `NextSolstice` | `nextEquinox`, `nextFullMoon`, `nextNewMoon`, `nextSolstice` |
| `SunAltitude`, `SunAzimuth`, `SunDeclination`, `SunRightAscension` | `sunAltitude`, `sunAzimuth`, `sunDeclination`, `sunRightAscension` |
| `Sunrise`, `Sunset`, `SunTransit` | `sunrise`, `sunset`, `sunTransit` |
| `yesterdaySunshineDur` | `yesterdayDaylightDur` |

(`tomorrowSunrise` and `tomorrowSunset` were already lowerCamelCase and are unchanged.)

# Upgrade Instructions

1. **As of version 5.0, weewx-celestial requires WeeWX 5.2 or later** (WeeWX 4 was supported
   through version 4.2).  On an older WeeWX, stay with
   [weewx-celestial 4.2](https://github.com/chaunceygardiner/weewx-celestial/releases) — or,
   better, upgrade WeeWX.  The installer refuses to install 5.0 on an unsupported WeeWX.

1. As of version 5.1, the sample report includes three more sky-chart panels — the sun's
   path for today, the solar year, and the lunar month — which need
   [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) 1.7 or later.  With
   an older weewx-skyfield those three panels show a short upgrade hint (the original four
   keep drawing); without weewx-skyfield all seven show install hints.  No `[LoopData]`
   fields changes are needed for this release; there is nothing to migrate.

1. As of version 5.0, the sample report includes four sky-chart panels — the sky dome, the
   rise-and-set timeline, the orrery and the analemma — drawn by the
   [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) extension.  Installing
   weewx-skyfield is recommended but not strictly necessary: without it, each of those panels
   shows a short install hint, report-time cell values fall back to WeeWX's built-in PyEphem
   almanac, and everything else works exactly as before.  No `[LoopData]` fields changes are
   needed for this release; there is nothing to migrate.

1. If you are upgrading from a previous version to 1.x, and you are using the sample skin, you'll need to add the following
   two fields to the `fields` line in `weewx.conf`:
   `current.tomorrowSunrise.raw, current.tomorrowSunset.raw`

1. If you are upgrading from a 1.x version, you'll need to install skyfield.  See the install instructions above for how to install skyfield.

1. If you are upgrading from 2.0 to a later version, you'll need to add the following fields in the `fields` line in `weewx.conf`:
   `current.MoonTransit`
   `current.Moonrise`
   `current.Moonset`

1. As of version 4.0, fields are cached by how often they can change (see the Description above), which makes per-record updates cheap:
   `update_rate_secs` now throttles only the continuously varying fields (positions, distances, moon phase) and the installed default is
   `0` (update on every loop record).  If your weewx.conf still has `update_rate_secs = 10` from an earlier release, it keeps working;
   change it to `0` for live updates on every loop record.

1. As of version 4.0, weewx-celestial no longer replaces the almanac used in report generation (versions 3.x did).  If your reports rely
   on Skyfield-computed `$almanac` tags (including named-star tags such as `$almanac.rigel.rise`), install the
   [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) extension.  The `replace_builtin_almanac` option is gone; a
   leftover setting in the `[Celestial]` section of `weewx.conf` is ignored harmlessly.

1. As of version 4.0, the deprecated pre-3.0 loop field names are no longer emitted (see "Deprecated loop field names" above), and there
   are new loop fields — `moonPhaseIndex`, `moonWaxing` and azimuth/altitude for all eight planets — feeding the redesigned live sample
   report (moon disc, countdown chips, day strip, planets-now chips).  **A bundled utility updates your `[LoopData] [[Include]]
   [[[fields]]]` line for both changes at once**: it renames the deprecated celestial fields in place (keeping their rendition suffixes
   and the line's order), drops the duplicates the renames create, appends the fields the new sample report reads, and never touches
   non-celestial fields.  Run it after installing 4.0:

   `PYTHONPATH=/home/weewx/bin python -m user.celestial --migrate-loopdata-fields --config /home/weewx/weewx.conf --output /home/weewx/weewx.conf.migrated`

   Compare the two files (`diff /home/weewx/weewx.conf /home/weewx/weewx.conf.migrated`), then move the migrated file into place and
   restart WeeWX.  Alternatives: `--in-place` rewrites `weewx.conf` directly (a `.bak-celestial-4.0` backup is made first), and
   `--print-fields-value` just prints the migrated value as a bare comma-separated list for manual pasting (do not add brackets or
   quotes).  The utility is safe to re-run; a second pass changes nothing.

   One caveat: `daySunshineDur`/`yesterdaySunshineDur` are renamed to `daylightDur`/`yesterdayDaylightDur`.  If another extension
   (e.g., weewx-sunduration) provides a *real* `daySunshineDur` on your system, restore those entries by hand — the utility calls
   this out in its summary when it happens.

   Also update any custom skins or JavaScript that read the old names from loop-data.txt (the bundled Celestial sample skin already
   uses the new names as of 3.0).  Without the new fields the page still works and the new visual components simply stay empty.  Displayed times now use the station's timezone, auto-detected at report
   generation time (previously the javascript hardcoded America/Los_Angeles); a new `time_zone` Extras option can override (an IANA
   name, or `browser` for the viewer's browser-local timezone).  The `refresh_rate` Extras option (seconds between loop-data polls) is
   now honored; it existed before but was ignored.

1. As of version 3.0, the bundled JPL ephemeris is named `celestial_de421.bsp` (formerly `de421.bsp`).  `weectl` does not remove
   files dropped from an extension's file list when upgrading, so after upgrading from 2.x, delete the orphaned 17 MB file:
   `sudo rm <weewx-root>/bin/user/de421.bsp`

1. As of version 3.0, there is a new loop field `earthProximaCentauriDistance`, reported in light years in every unit system
   (at 4.22 light years, miles and kilometers are unreadable).  It is only emitted when the star catalog is enabled
   (`stars = true`, the default).  To use it (the bundled Celestial sample skin displays it), add
   `current.earthProximaCentauriDistance.raw` to the `[LoopData] [[Include]] [[[fields]]]` line in `weewx.conf`.

1. As of version 3.0, the right ascension/declination loop fields (`sunRightAscension`, `sunDeclination`, `moonRightAscension`,
   `moonDeclination`, and their deprecated equivalents) are expressed in coordinates of date rather than J2000 (in 2025, right
   ascensions shift by roughly 0.4&deg; as a result).  Apparent coordinates of date are the accepted convention for observed
   positions (they are what the Astronomical Almanac publishes); this also matches PyEphem and the report almanac's
   `topo_ra`/`topo_dec`.


# Installation Instructions

weewx-celestial requires WeeWX 5.2 or later.  (WeeWX 4 was supported through version 4.2;
on WeeWX 4, stay with [weewx-celestial 4.2](https://github.com/chaunceygardiner/weewx-celestial/releases).)

1. If pip install,
   Activate the virtual environment (actual syntax varies by type of WeeWX install):
   `/home/weewx/weewx-venv/bin/activate`
   Install the prerequisite skyfield package.
   `pip install skyfield`

1. If package install:
   Install the prerequisite skyfield package.  On debian, that can be accomplished with:
   `sudo apt install python3-skyfield` 

1. Install the latest release of weewx-loopdata at

   [weewx-loopdata GitHub repository](https://github.com/chaunceygardiner/weewx-loopdata).

1. Recommended (not required): install the
   [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) extension, 1.7 or
   later.  It draws the sample report's seven sky-chart panels (sky dome, rise-and-set
   timeline, orrery, analemma, sun path, solar year, lunar month) and serves
   Skyfield-computed report tags.  Without it, those panels show a short install hint,
   report-time values fall back to WeeWX's built-in PyEphem almanac, and everything else
   works.

1. Download the latest release, weewx-celestial.zip, from

   [weewx-celestial GitHub Repository](https://github.com/chaunceygardiner/weewx-celestial).

1. Install the celestial extension.

   `weectl extension install weewx-celestial.zip`

1. Add the following fields to the `[LoopData][[Include]][[[fields]]]` line in `weewx.conf`.  (They are used by the sample report.)

   `current.astronomicalTwilightEnd.raw, current.astronomicalTwilightStart.raw, current.civilTwilightEnd.raw, current.civilTwilightStart.raw, current.dateTime.raw, current.daylightDur.raw, current.earthJupiterDistance, current.earthMarsDistance, current.earthMercuryDistance, current.earthMoonDistance, current.earthNeptuneDistance, current.earthPlutoDistance, current.earthProximaCentauriDistance.raw, current.earthSaturnDistance, current.earthSunDistance, current.earthUranusDistance, current.earthVenusDistance, current.jupiterAltitude.raw, current.jupiterAzimuth.raw, current.marsAltitude.raw, current.marsAzimuth.raw, current.mercuryAltitude.raw, current.mercuryAzimuth.raw, current.moonAltitude.raw, current.moonAzimuth.raw, current.moonDeclination.raw, current.moonFullness, current.moonFullness.raw, current.moonPhase, current.moonPhaseIndex.raw, current.moonRightAscension.raw, current.moonTransit, current.moonTransit.raw, current.moonWaxing.raw, current.moonrise, current.moonrise.raw, current.moonset, current.moonset.raw, current.nauticalTwilightEnd.raw, current.nauticalTwilightStart.raw, current.neptuneAltitude.raw, current.neptuneAzimuth.raw, current.nextEquinox, current.nextEquinox.raw, current.nextFullMoon, current.nextFullMoon.raw, current.nextNewMoon, current.nextNewMoon.raw, current.nextSolstice, current.nextSolstice.raw, current.plutoAltitude.raw, current.plutoAzimuth.raw, current.saturnAltitude.raw, current.saturnAzimuth.raw, current.sunAltitude.raw, current.sunAzimuth.raw, current.sunDeclination.raw, current.sunRightAscension.raw, current.sunTransit.raw, current.sunrise.raw, current.sunset.raw, current.tomorrowSunrise.raw, current.tomorrowSunset.raw, current.uranusAltitude.raw, current.uranusAzimuth.raw, current.venusAltitude.raw, current.venusAzimuth.raw, current.yesterdayDaylightDur.raw`

1. Restart WeeWX.

1. After a reporting cycle runs, navigate to `<weewx-url>/celestial/ in your browser
   to see the default celestial sample report. (Reports typically run every 5 minutes.)

## Entries in `Celestial` section of `weewx.conf`:

```
[Celestial]
    enable = true
    update_rate_secs = 0
    stars = true
```

 * `enable`          : When true, the celestial observations are added to every loop record.
 * `update_rate_secs`: number of seconds that have to pass before the continuously varying fields
                       (positions, distances, moon phase) are recalculated; `0` (the default)
                       recalculates them on every loop record.  The daily and next-event fields
                       have their own natural lifetimes and are unaffected by this setting.
 * `stars`           : When true (the default), the `earthProximaCentauriDistance` loop field is emitted,
                       computed from the bundled Hipparcos catalog excerpt (`celestial_stars.dat`).

## Entries in `CelestialReport` section of `weewx.conf`:

```
    [[CelestialReport]]
        HTML_ROOT = public_html/celestial
        enable = true
        skin = Celestial
        [[[Extras]]]
            loop_data_file = ../loop-data.txt
            refresh_rate = 2
            expiration_time = 24
            page_update_pwd = foobar
```

 * HTML_ROOT        : The HTML output directory in which to write the report.
 * `enable`         : When true, the report is generated.
 * `skin`           : Must be `Celestial`
 * `loop_data_file` : The path of the loop-data.txt file (written by the loopdata extension).
                      If a relative path is specified, it is relative to the
                     `target_report` directory.
 * `refresh_rate`   : Seconds between loop-data polls.  Match weewx-loopdata's write cadence
                      (2 seconds for the Vantage driver).
 * `time_zone`      : Timezone for every time shown on the page (rise/set cells, day strip,
                      clock).  By default the station's timezone is auto-detected at report
                      generation time, so remote viewers of a public page see station time —
                      no setting needed.  Set only to override: an IANA name (e.g.,
                      `America/New_York`) forces that zone; `browser` forces the viewer's
                      browser-local timezone.
 * `expiration_time`: The number of hours before expiring the autoupdate of the report.
 * `page_update_pwd`: The password to specify in the URL such that the page never expires.
                      That is, `<machine>/weewx/celestial/?pageUpdate=foobar`

## See it in action at PaloAltoWeather.com

The celestial pages at
[www.paloaltoweather.com](https://www.paloaltoweather.com/celestial.html) are a custom skin
built exactly as described in "Adding the live celestial panels to your own skin" above:
weewx-celestial loop fields for the live values, plus report tags and sky panels from the
[weewx-skyfield extension](https://github.com/chaunceygardiner/weewx-skyfield).

![Celestial Today Page](PAW_Celestial_Today.png)
![Celestial Sun Page](PAW_Celestial_Sun.png)
![Celestial Moon Page](PAW_Celestial_Moon.png)
![Celestial Planets Page](PAW_Celestial_Planets.png)
![Celestial Stars Page](PAW_Celestial_Stars.png)

## Testing

### Automated tests

A pytest test suite lives in the `tests` directory.  It exercises the loop fields and their
Sky engine (rise/set/transit and twilight times, equinoxes/solstices, moon phases, positions,
distances and their units, polar day/night edge cases, the sample skin's end-to-end render,
and pinned regression values for Palo Alto on 2025-06-21).  When the
[weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) extension is available
(installed on the machine, or checked out as a sibling repository), the loop fields are also
cross-checked against its report almanac: the two extensions compute from the same definitions,
so their values must agree.  Run the suite from the root of this repository with the Python
from your WeeWX virtual environment (WeeWX, Skyfield and pytest must be installed in that
environment):

```
/home/weewx/weewx-venv/bin/python -m pytest tests
```

The star tests use the bundled Hipparcos catalog excerpt (`bin/user/celestial_stars.dat`),
which is part of this repository, so no additional downloads are needed.

### Command line check

Celestial can be run from the command line to verify the readings.  Below are examples.  Use --help for all of the options.
`PYTHON_PATH` needs to point to the user directory for weewx.  That is, it needs to point to where extensions are located.

1. `/home/weewx/weewx-venv/bin/activate`
2. `PYTHONPATH=/home/weewx/bin python -m user.celestial --test --out-temp=65.1 --barometer=30.128` (for inputs in US units)
   `PYTHONPATH=/home/weewx/bin python -m user.celestial --test --out-temp=18.4 --barometer=1020.25 --metric` (for temp and barometer in Metric units)

Example output from above test execution:
```
Skyfield version: 1.54.
                moonPhase:                      Waning gibbous
     earthJupiterDistance:                 580,002,076.2 miles
        earthMarsDistance:                 194,417,412.8 miles
     earthMercuryDistance:                  53,857,884.8 miles
     earthNeptuneDistance:               2,760,433,627.2 miles
        earthMoonDistance:                     241,090.0 miles
       earthPlutoDistance:               3,216,323,226.6 miles
      earthSaturnDistance:                 875,208,906.9 miles
         earthSunDistance:                  94,502,823.0 miles
      earthUranusDistance:               1,880,091,466.7 miles
       earthVenusDistance:                  93,494,330.4 miles
              daylightDur: 14 hours, 39 minutes and 13 seconds
     yesterdayDaylightDur: 14 hours, 39 minutes and 57 seconds
             moonFullness:                            70% full
             moonAltitude:                              -37.2°
              moonAzimuth:                              300.5°
          moonDeclination:                               -2.7°
       moonRightAscension:                              350.1°
              sunAltitude:                               66.3°
               sunAzimuth:                              237.8°
           sunDeclination:                               22.7°
        sunRightAscension:                              105.1°
  astronomicalTwilightEnd:           July 05, 2026 at 10:24 PM
astronomicalTwilightStart:           July 05, 2026 at 04:01 AM
         civilTwilightEnd:           July 05, 2026 at 09:03 PM
       civilTwilightStart:           July 05, 2026 at 05:22 AM
                 moonrise:           July 05, 2026 at 11:51 PM
                  moonset:           July 05, 2026 at 11:20 AM
              moonTransit:           July 05, 2026 at 05:19 AM
      nauticalTwilightEnd:           July 05, 2026 at 09:41 PM
    nauticalTwilightStart:           July 05, 2026 at 04:44 AM
              nextEquinox:      September 22, 2026 at 05:05 PM
             nextFullMoon:           July 29, 2026 at 07:35 AM
              nextNewMoon:           July 14, 2026 at 02:43 AM
             nextSolstice:       December 21, 2026 at 12:50 PM
                  sunrise:           July 05, 2026 at 05:53 AM
                   sunset:           July 05, 2026 at 08:32 PM
               sunTransit:           July 05, 2026 at 01:13 PM
          tomorrowSunrise:           July 06, 2026 at 05:53 AM
           tomorrowSunset:           July 06, 2026 at 08:32 PM
All fields present and of the correct type.  The test passed.
```


## Why require Python 3.9 or later?

Celestial code uses timezone aware date features which do not work with Python 2, nor in
versions of Python 3 earlier than 3.9.


## Licensing

weewx-celestial is licensed under the GNU Public License v3.

The bundled star catalog excerpt (`celestial_stars.dat`) contains data from the Hipparcos and
Tycho Catalogues, which ESA distributes under the
[CC BY-NC 3.0 IGO](https://creativecommons.org/licenses/by-nc/3.0/igo/) licence.  Credit: ESA.
