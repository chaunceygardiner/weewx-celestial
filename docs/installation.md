---
title: Installation
description: Installing weewx-celestial 8.x (with the satellite, comet and countdown fields for the live sky dome, the Next Visible Pass chart and countdown central), and upgrading from earlier versions with the bundled --migrate-loopdata-fields utility.
---

# Installation

[Home](index.md) ·
[Configuration](configuration.md) ·
[The Geocentric in your skin](own-skin.md) ·
[Translating (i18n)](i18n.md) ·
[GitHub project](https://github.com/chaunceygardiner/weewx-celestial)

---

## Fresh install

1. Install [weewx-loopdata](https://chaunceygardiner.github.io/weewx-loopdata/)
   6.9 or later and
   [weewx-skyfield](https://chaunceygardiner.github.io/weewx-skyfield/)
   2.1 or later, both per their instructions.  (weewx-skyfield's installer
   configures its default satellites — the ISS and Tiangong — and its
   default comets — Halley and Hale-Bopp — which is what the fields line
   below assumes.)

1. Download `weewx-celestial.zip` from the
   [release page](https://github.com/chaunceygardiner/weewx-celestial/releases),
   then:

   ```
   weectl extension install weewx-celestial.zip
   ```

1. Check the `fields` line of `[LoopData] [[Include]]` in `weewx.conf`
   — the install step above appended the entries the report reads
   (printing each one).  The line must stay a BARE comma-separated
   list (no brackets or quotes); the full set, for reference and hand
   editing:

   ```
   current.dateTime.raw, almanac.sun.az, almanac.sun.alt, almanac.sun.earth_distance, almanac.moon.az, almanac.moon.alt, almanac.moon.earth_distance, almanac.moon.phase, almanac.next_full_moon.unix_epoch.raw, almanac.next_new_moon.unix_epoch.raw, almanac.mercury.az, almanac.mercury.alt, almanac.mercury.earth_distance, almanac.venus.az, almanac.venus.alt, almanac.venus.earth_distance, almanac.mars.az, almanac.mars.alt, almanac.mars.earth_distance, almanac.jupiter.az, almanac.jupiter.alt, almanac.jupiter.earth_distance, almanac.saturn.az, almanac.saturn.alt, almanac.saturn.earth_distance, almanac.uranus.az, almanac.uranus.alt, almanac.uranus.earth_distance, almanac.neptune.az, almanac.neptune.alt, almanac.neptune.earth_distance, almanac.pluto.az, almanac.pluto.alt, almanac.pluto.earth_distance, almanac.proxima_centauri.az, almanac.proxima_centauri.alt, almanac.proxima_centauri.earth_distance, almanac.sun.next_setting.unix_epoch.raw, almanac.sun.next_rising.unix_epoch.raw, almanac(horizon=-18).sun.next_setting.unix_epoch.raw, almanac(horizon=-18).sun.next_rising.unix_epoch.raw, almanac.next_equinox.unix_epoch.raw, almanac.next_solstice.unix_epoch.raw, almanac.next_perihelion.unix_epoch.raw, almanac.next_aphelion.unix_epoch.raw, almanac.next_meteor_shower.peak.unix_epoch.raw, almanac.next_meteor_shower.label, almanac.next_supermoon.unix_epoch.raw, almanac.next_eclipse.unix_epoch.raw, almanac.next_eclipse_kind, almanac.iss.az, almanac.iss.alt, almanac.iss.sunlit, almanac.iss.label, almanac.iss.next_visible_pass.rise.unix_epoch.raw, almanac.iss.next_visible_pass.set.unix_epoch.raw, almanac.iss.next_visible_pass.max_altitude.degree_angle.raw, almanac.iss.next_visible_pass.duration.second.raw, almanac.iss.next_visible_pass.rise_azimuth.ordinal_compass, almanac.iss.next_visible_pass.culmination_azimuth.ordinal_compass, almanac.iss.next_visible_pass.set_azimuth.ordinal_compass, almanac.iss.next_pass.rise.unix_epoch.raw, almanac.iss.next_pass.set.unix_epoch.raw, almanac.iss.next_pass.max_altitude.degree_angle.raw, almanac.iss.next_pass.duration.second.raw, almanac.iss.next_pass.rise_azimuth.ordinal_compass, almanac.iss.next_pass.culmination_azimuth.ordinal_compass, almanac.iss.next_pass.set_azimuth.ordinal_compass, almanac.iss.next_pass.visible, almanac.tiangong.az, almanac.tiangong.alt, almanac.tiangong.sunlit, almanac.tiangong.label, almanac.tiangong.next_visible_pass.rise.unix_epoch.raw, almanac.tiangong.next_visible_pass.set.unix_epoch.raw, almanac.tiangong.next_visible_pass.max_altitude.degree_angle.raw, almanac.tiangong.next_visible_pass.duration.second.raw, almanac.tiangong.next_visible_pass.rise_azimuth.ordinal_compass, almanac.tiangong.next_visible_pass.culmination_azimuth.ordinal_compass, almanac.tiangong.next_visible_pass.set_azimuth.ordinal_compass, almanac.tiangong.next_pass.rise.unix_epoch.raw, almanac.tiangong.next_pass.set.unix_epoch.raw, almanac.tiangong.next_pass.max_altitude.degree_angle.raw, almanac.tiangong.next_pass.duration.second.raw, almanac.tiangong.next_pass.rise_azimuth.ordinal_compass, almanac.tiangong.next_pass.culmination_azimuth.ordinal_compass, almanac.tiangong.next_pass.set_azimuth.ordinal_compass, almanac.tiangong.next_pass.visible, almanac.halley.az, almanac.halley.alt, almanac.halley.earth_distance, almanac.halley.mag, almanac.halley.label, almanac.halley.perihelion.unix_epoch.raw, almanac.hale_bopp.az, almanac.hale_bopp.alt, almanac.hale_bopp.earth_distance, almanac.hale_bopp.mag, almanac.hale_bopp.label, almanac.hale_bopp.perihelion.unix_epoch.raw
   ```

   (As of 8.1 the installer does this step for you: `weectl extension
   install` appends any of these entries missing from the line —
   append-only, printing each one; existing entries are never renamed,
   removed or reordered — so the line above is the reference for hand
   editing and for older installs.  Entries already present need not be
   repeated; weewx-loopdata ignores duplicates.)

   The `almanac.iss.*` and `almanac.tiangong.*` entries are the
   satellite layer.  A satellite you add beyond the installer's two
   appears on the dome and in the rosters once it has a
   `[Skyfield] [[Satellites]]` entry and the same nineteen fields-line
   entries with its tag name; the skin picks the satellite set up
   automatically, only the fields line is per-satellite.  The bundled
   `--add-satellite` utility makes those edits — plus the display name —
   in one command; `--remove-satellite` is its inverse.  See
   [Adding and removing satellites](configuration.md#adding-and-removing-satellites).

   The `almanac.halley.*`/`almanac.hale_bopp.*` entries are the comet
   layer (six per comet, following `[Skyfield] [[Comets]]` the same
   way — `--add-comet`/`--remove-comet` make and unmake the edits, see
   [Adding and removing comets](configuration.md#adding-and-removing-comets)),
   and the sunset/sunrise, darkness, equinox/solstice,
   perihelion/aphelion, meteor shower,
   supermoon and eclipse entries feed the countdown row.

   By hand, the display name belongs in an `[Almanac]` entry where every
   report sees it:

   ```
   [StdReport]
       [[Defaults]]
           [[[Almanac]]]
               hst = Hubble
   ```

   (Live labels follow loopdata's *target report's* `[Almanac]` section,
   so `[[Defaults]]` is the reliable home — a name set only in one
   report's section does not reach the loop feed.)

1. Point weewx-loopdata's output where the page looks.  The skin fetches
   `loop_data_file` — default `../loop-data.txt`, the directory above
   this report, i.e. your web root — while weewx-loopdata's own defaults
   (`[LoopData]` `[[Formatting]] target_report = LoopDataReport`,
   `[[FileSpec]] loop_data_dir = .`) write `loop-data.txt` into the
   LoopData report's directory instead.  Make the two meet: with the
   default target report, set `loop_data_dir = ..` (`loop_data_dir` is
   relative to the target report's HTML_ROOT), or point this report's
   `loop_data_file` (see [Configuration](configuration.md)) at wherever
   your loopdata already writes.  A mismatch is easy to spot: the
   page's badge reads "NO DATA (HTTP 404) — check loop_data_file".

1. Restart WeeWX.  The report appears under `celestial/` of your web root.

## Upgrading from 7.x

Install right over the existing version, then restart WeeWX —

```
weectl extension install weewx-celestial.zip
```

One action lights up the new layers: append the missing entries above
to your `[LoopData] [[Include]] fields` line — the satellite entries
(8.0), and 8.1's countdown-chip fields and per-comet entries.  Running
`--migrate-loopdata-fields` appends them all for you: it follows your
`[Skyfield]` `[[Satellites]]` and `[[Comets]]`, so a customized set
gets entries for its own tags instead of the defaults, and it is
idempotent and never touches non-celestial entries.  Run weewx-skyfield
2.1 for the comets and the shower/supermoon chips (2.0 still serves the
satellites; the sunset, darkness and pass chips tick on either).
Without the entries the page simply hides those layers and chips;
everything else is drop-in and the rest of the fields line is
unchanged.  As of 8.1 the install itself appends the missing entries
(append-only, each one printed; restart weewxd so weewx-loopdata
reloads the line), so the migrator run is only needed when the line
carries pre-6.0 spellings — renames deserve review, and the installer
prints the exact migrator commands, tailored to your configuration,
instead of applying them.

Note that upgrading replaces the bundled skin (`skins/Celestial/`,
including its `lang/` files) — local additions and overrides survive
upgrades best as `[[[Almanac]]]`/`[[[Texts]]]` entries in the report's
section of `weewx.conf` (see [Translating](i18n.md)).

## Upgrading from 6.x

1. Uninstall the old version, then install the new one:

   ```
   weectl extension uninstall celestial
   weectl extension install weewx-celestial.zip
   ```

1. Restart WeeWX.  (The restart also refreshes the deployed
   `celestial.css` and `sky.js` — CopyGenerator re-copies `copy_once`
   files on every report first-run — and the page version-tags both
   URLs, so browsers refetch them too.)

Your existing `[LoopData] [[Include]] fields` line keeps working as is —
8.x reads a subset of the 6.0 field set plus the Proxima Centauri
entries and the satellite entries above.  Run the bundled
`--migrate-loopdata-fields` utility (next section) to append the
missing entries in one idempotent pass, or add them by hand.  The
remaining 6.0 entries (rise/sets, twilights, ra/dec, equinox/solstice,
`almanac.moon_phase`, `almanac.moon_index`, sun visible-time) are no
longer read by this skin; keep them if your own pages consume them, or
trim them to the list above.

If you still list `user.celestial.Celestial` under `data_services` in
`[Engine] [[Services]]` (a leftover from 2.x that 6.x tolerated with a
stub), **remove it now**: 7.0 deleted the stub, and a stale entry will
keep weewxd from starting.

## Upgrading from 5.x or earlier

6.0 removed this extension's loop fields (`current.sunrise`,
`current.earthMarsDistance`, `current.moonWaxing`, …); almanac fields
replace them.  The sequence matters — the migration utility ships with
this extension, so the new version must be installed before it can run:

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

1. Install [weewx-loopdata](https://chaunceygardiner.github.io/weewx-loopdata/)
   6.9+ and [weewx-skyfield](https://chaunceygardiner.github.io/weewx-skyfield/)
   2.1+ if you have not already, then install this version.

1. Run the bundled utility to rewrite your `[LoopData] [[Include]] fields`
   line — every celestial entry (including pre-3.0 PascalCase names)
   becomes its almanac equivalent, rendition suffixes are honored,
   non-celestial entries are never touched, and the fields the report
   needs are appended.  The satellite and comet entries follow your
   `[Skyfield]` `[[Satellites]]` and `[[Comets]]` — fields for exactly
   the sets you have configured, the installer defaults (iss and
   tiangong; halley and hale_bopp) only when there is no section to
   follow.  Raw times and durations
   arrive with pinned units
   (`almanac.sunrise.unix_epoch.raw`, `almanac.sun.visible.second.raw`),
   so they keep the old fields' fixed meanings — epoch seconds, seconds
   of daylight — no matter how loopdata's target report units are set:

   ```
   source /home/weewx/weewx-venv/bin/activate
   cd /home/weewx/bin    # the directory CONTAINING the `user` package
                         # (~/weewx-data/bin on pip installs)
   python -m user.celestial --migrate-loopdata-fields --config /home/weewx/weewx.conf --output /tmp/weewx.conf.migrated
   git diff --no-index --word-diff /home/weewx/weewx.conf /tmp/weewx.conf.migrated   # review, then move into place
   ```

   On a Debian or Red Hat package install there is no venv to activate,
   and WeeWX's own code lives in `/usr/share/weewx` — on the path only
   inside `weectl` — so prefix the command instead:

   ```
   cd /etc/weewx/bin
   PYTHONPATH=/usr/share/weewx python3 -m user.celestial --migrate-loopdata-fields --config /etc/weewx/weewx.conf --output /tmp/weewx.conf.migrated
   git diff --no-index --word-diff /etc/weewx/weewx.conf /tmp/weewx.conf.migrated   # review, then move into place
   ```

   (The commands `weectl extension install` prints are tailored to your
   machine and carry the prefix already.  `--in-place` edits weewx.conf
   directly after making a `.bak-celestial-<version>` backup;
   `--print-fields-value` just prints the migrated line for
   cut-and-paste.)

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
  `almanac.next_full_moon.unix_epoch.raw <
  almanac.next_new_moon.unix_epoch.raw` (the bundled skin shows the
  derivation).

The `[Celestial]` section of weewx.conf (`enable`, `update_rate_secs`,
`stars`) is obsolete and can be deleted.  The Skyfield and NumPy libraries
are no longer required by this extension (weewx-skyfield requires them,
and has its own ephemeris and star catalog).
