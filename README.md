# weewx-celestial
Open source plugin for WeeWX software.

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)

**This extension requires Python 3.9 or later, WeeWX 5.2 or later,
[weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata) 5.0 or
later, and (strongly recommended)
[weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield).**

## Description

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

For sky *charts* — the sky dome, sun path, orrery, analemma, solar year,
lunation and rise/set timeline — see weewx-skyfield's own Sky page: as of
7.0 this skin no longer embeds them.  weewx-skyfield is the atlas;
weewx-celestial is the live instrument.

The bundled sample report (Palo Alto, a July evening at 9:12 PM — the
first-quarter moon high in the southwest trailing its wake, Mercury and
Mars in the west, the freshly set sun dashed below the horizon, Proxima
Centauri alone at the rim, and every odometer ticking):
![Celestial Sample Report](CelestialSampleReport.png)

The live values are **weewx-loopdata almanac fields**: report almanac tags
(computed by the registered almanac, ideally weewx-skyfield's) that
weewx-loopdata evaluates on every loop packet and publishes in
`loop-data.txt`.  One computation engine serves the report tags and the
live page, so they always agree.  This extension runs no service and
computes nothing itself.

What installs:

- The `Celestial` skin (the sample report), registered as `CelestialReport`.
- The `--migrate-loopdata-fields` command-line utility (see upgrading).

The roster first-paints at report time from `$almanac` and then goes live
from loop data.  What you see depends on the almanac WeeWX has: with
**weewx-skyfield** (stars on), everything, Proxima included.  With
**PyEphem** (no weewx-skyfield), everything except the Proxima Centauri
row.  With only WeeWX's **built-in almanac**, the page generates but the
panel stays empty and shows an install hint — the built-in almanac serves
none of the positions or distances this page runs on, which is why
weewx-skyfield is strongly recommended.

# Installation Instructions

1. Install [weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata)
   5.0 or later and
   [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield),
   both per their instructions.

1. Download `weewx-celestial.zip` from the release page, then:

   ```
   weectl extension install weewx-celestial.zip
   ```

1. Add the fields the report reads to the `fields` line of
   `[LoopData] [[Include]]` in `weewx.conf`.  The line must stay a BARE
   comma-separated list (no brackets or quotes).  Append:

   ```
   current.dateTime.raw, almanac.sun.az, almanac.sun.alt, almanac.sun.earth_distance, almanac.moon.az, almanac.moon.alt, almanac.moon.earth_distance, almanac.moon.phase, almanac.next_full_moon.raw, almanac.next_new_moon.raw, almanac.mercury.az, almanac.mercury.alt, almanac.mercury.earth_distance, almanac.venus.az, almanac.venus.alt, almanac.venus.earth_distance, almanac.mars.az, almanac.mars.alt, almanac.mars.earth_distance, almanac.jupiter.az, almanac.jupiter.alt, almanac.jupiter.earth_distance, almanac.saturn.az, almanac.saturn.alt, almanac.saturn.earth_distance, almanac.uranus.az, almanac.uranus.alt, almanac.uranus.earth_distance, almanac.neptune.az, almanac.neptune.alt, almanac.neptune.earth_distance, almanac.pluto.az, almanac.pluto.alt, almanac.pluto.earth_distance, almanac.proxima_centauri.az, almanac.proxima_centauri.alt, almanac.proxima_centauri.earth_distance
   ```

   (Entries already present — e.g. `current.dateTime.raw` — need not be
   repeated; weewx-loopdata ignores duplicates.)

1. Restart WeeWX.  The report appears under `celestial/` of your web root.

# Upgrade Instructions (from 6.x)

1. Uninstall the old version, then install 7.0:

   ```
   weectl extension uninstall celestial
   weectl extension install weewx-celestial.zip
   ```

1. Restart WeeWX.  (The restart also refreshes the deployed
   `celestial.css` — CopyGenerator re-copies `copy_once` files on every
   report first-run — and the page version-tags the stylesheet URL, so
   browsers refetch it too.)

Your existing `[LoopData] [[Include]] fields` line keeps working as is —
7.0 reads a subset of the 6.0 field set plus three new entries, so add
`almanac.proxima_centauri.az, almanac.proxima_centauri.alt` (the
migration utility adds them too, but for a 6.0 line it is simpler by
hand).  The remaining 6.0 entries (rise/sets, twilights, ra/dec,
equinox/solstice, `almanac.moon_phase`, `almanac.moon_index`, sun
visible-time) are no longer read by this skin; keep them if your own
pages consume them, or trim them to the list above.

If you still list `user.celestial.Celestial` under `data_services` in
`[Engine] [[Services]]` (a leftover from 2.x that 6.x tolerated with a
stub), **remove it now**: 7.0 deletes the stub, and a stale entry will
keep weewxd from starting.

# Upgrade Instructions (from 5.x or earlier)

6.0 removed this extension's loop fields (`current.sunrise`,
`current.earthMarsDistance`, `current.moonWaxing`, …); almanac fields
replace them.  The sequence matters — the migration utility ships with
this extension, so 7.0 must be installed before it can run:

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

1. Install [weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata)
   5.0+ and [weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield)
   if you have not already, then install 7.0.

1. Run the bundled utility to rewrite your `[LoopData] [[Include]] fields`
   line — every celestial entry (including pre-3.0 PascalCase names)
   becomes its almanac equivalent, rendition suffixes are honored,
   non-celestial entries are never touched, and the fields the report
   needs are appended:

   ```
   source /home/weewx/weewx-venv/bin/activate
   cd /home/weewx/bin    # the directory CONTAINING the `user` package
                         # (~/weewx-data/bin on pip installs)
   python -m user.celestial --migrate-loopdata-fields --config /home/weewx/weewx.conf --output /tmp/weewx.conf.migrated
   diff /home/weewx/weewx.conf /tmp/weewx.conf.migrated   # review, then move into place
   ```

   (`--in-place` edits weewx.conf directly after making a
   `.bak-celestial-7.0` backup; `--print-fields-value` just prints the
   migrated line for cut-and-paste.)

1. Restart WeeWX.

If your own pages read the old fields, note the three changes with no
1:1 equivalent:

- **Distances arrive as raw astronomical units** (the value reports show),
  no longer miles/km — convert in the page (× 92,955,807 miles/AU or
  × 149,597,870 km/AU).  Proxima Centauri is AU as well, no longer light
  years (÷ 63,241.077 AU/ly).
- **`almanac.moon.phase`** (the `moonFullness` replacement) is a raw
  percent (e.g. `33.6`), no longer a formatted string.
- **`moonWaxing` is gone**: the moon is waxing exactly when
  `almanac.next_full_moon.raw < almanac.next_new_moon.raw` (the bundled
  skin shows the derivation).

The `[Celestial]` section of weewx.conf (`enable`, `update_rate_secs`,
`stars`) is obsolete and can be deleted.  The Skyfield and NumPy libraries
are no longer required by this extension (weewx-skyfield requires them,
and has its own ephemeris and star catalog).

## Entries in `CelestialReport` section of `weewx.conf`:

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
  are relative to this report's HTML_ROOT.
- `refresh_rate`: seconds between loop-data polls (match weewx-loopdata's
  write cadence: 2 for the Vantage driver).
- `expiration_time`: hours the page keeps polling before requiring a click
  (`?pageUpdate=<page_update_pwd>` in the URL disables expiration).
- The skin's `time_zone` Extras option (see `skin.conf`) controls the
  timezone of displayed times; by default the station's zone is
  auto-detected at report time.

## Adding the Geocentric (or your own live panel) to your own skin

Everything the sample skin does is ordinary weewx-loopdata consumption:
list the almanac fields you want in `[LoopData] [[Include]] fields`, give
your HTML elements ids equal to the json keys, and poll `loop-data.txt`
from javascript.  `skins/Celestial/realtime_updater.inc` is the reference
implementation — the dial, the rate derivation (two consecutive packets
give each body its motion; the one-second tick extrapolates between
refreshes) and the odometer are self-contained functions you can lift,
and `skins/Celestial/celestial.css` holds every color.  The full
almanac-field grammar (any report almanac tag with the `$` removed, plus
the `almanac(days=±N)` tomorrow/yesterday extension) is documented in
[weewx-loopdata's README](https://github.com/chaunceygardiner/weewx-loopdata#almanac-fields).

## The Geocentric Live on PaloAltoWeather.com

[PaloAltoWeather.com's Celestial Today page](https://www.paloaltoweather.com/celestial.html)
contains a Geocentric Live panel built with the same technologies as used here
([weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield) and
[weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata)).

![PaloAltoWeather.com Celestial Today page](PAW_Celestial_Today.png)

## Testing

### Automated tests

```
cd ~/software/weewx-celestial     # your checkout
/home/weewx/weewx-venv/bin/python -m pytest tests
```

The suite renders the bundled skin end to end through Cheetah's
errorCatcher with the weewx-skyfield, PyEphem and built-in almanacs
(skipping the weewx-skyfield tier when that extension is not importable),
ties the javascript's loop-data keys to the migrator's field set, lints
the javascript's top-level names against hazardous window globals, and
cross-checks every entry the migration utility can produce against the
weewx-loopdata almanac-field parser (when a weewx-loopdata checkout is
available).  When a Playwright environment is available it also loads the
served page in headless Chromium with an advancing loop-data feed and
asserts the live machinery comes up — no page errors, dial dots drawn,
rates derived, trails visible.

### Command line check

To sanity check an installed configuration, confirm the `almanac.*` keys
appear in `loop-data.txt` after a restart:

```
python3 -c "import json; d=json.load(open('/home/weewx/gauge-data/loop-data.txt')); print(sorted(k for k in d if k.startswith('almanac')))"
```

## Why require Python 3.9 or later?

weewx-celestial is tested on Python 3.9 and later.  WeeWX 5.2 — this
extension's minimum, the first release with extensible almanacs — runs on
older Pythons, but the test matrix here does not.

## Licensing

weewx-celestial is licensed under the GNU Public License v3.
