---
title: Installation
description: Installing weewx-celestial 8.x (with the satellite fields for the live sky dome and Next Visible Pass chart), and upgrading from 7.x, 6.x, or 5.x and earlier with the bundled --migrate-loopdata-fields utility.
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
   2.0 or later, both per their instructions.  (weewx-skyfield's installer
   configures its default satellites — the ISS and Tiangong — which is
   what the fields line below assumes.)

1. Download `weewx-celestial.zip` from the
   [release page](https://github.com/chaunceygardiner/weewx-celestial/releases),
   then:

   ```
   weectl extension install weewx-celestial.zip
   ```

1. Add the fields the report reads to the `fields` line of
   `[LoopData] [[Include]]` in `weewx.conf`.  The line must stay a BARE
   comma-separated list (no brackets or quotes).  Append:

   ```
   current.dateTime.raw, almanac.sun.az, almanac.sun.alt, almanac.sun.earth_distance, almanac.moon.az, almanac.moon.alt, almanac.moon.earth_distance, almanac.moon.phase, almanac.next_full_moon.unix_epoch.raw, almanac.next_new_moon.unix_epoch.raw, almanac.mercury.az, almanac.mercury.alt, almanac.mercury.earth_distance, almanac.venus.az, almanac.venus.alt, almanac.venus.earth_distance, almanac.mars.az, almanac.mars.alt, almanac.mars.earth_distance, almanac.jupiter.az, almanac.jupiter.alt, almanac.jupiter.earth_distance, almanac.saturn.az, almanac.saturn.alt, almanac.saturn.earth_distance, almanac.uranus.az, almanac.uranus.alt, almanac.uranus.earth_distance, almanac.neptune.az, almanac.neptune.alt, almanac.neptune.earth_distance, almanac.pluto.az, almanac.pluto.alt, almanac.pluto.earth_distance, almanac.proxima_centauri.az, almanac.proxima_centauri.alt, almanac.proxima_centauri.earth_distance, almanac.iss.az, almanac.iss.alt, almanac.iss.sunlit, almanac.iss.label, almanac.iss.next_visible_pass.rise.unix_epoch.raw, almanac.iss.next_visible_pass.set.unix_epoch.raw, almanac.iss.next_visible_pass.max_altitude.degree_angle.raw, almanac.iss.next_visible_pass.duration.second.raw, almanac.iss.next_visible_pass.rise_azimuth.ordinal_compass, almanac.iss.next_visible_pass.culmination_azimuth.ordinal_compass, almanac.iss.next_visible_pass.set_azimuth.ordinal_compass, almanac.iss.next_pass.rise.unix_epoch.raw, almanac.iss.next_pass.set.unix_epoch.raw, almanac.iss.next_pass.max_altitude.degree_angle.raw, almanac.iss.next_pass.duration.second.raw, almanac.iss.next_pass.rise_azimuth.ordinal_compass, almanac.iss.next_pass.culmination_azimuth.ordinal_compass, almanac.iss.next_pass.set_azimuth.ordinal_compass, almanac.iss.next_pass.visible, almanac.tiangong.az, almanac.tiangong.alt, almanac.tiangong.sunlit, almanac.tiangong.label, almanac.tiangong.next_visible_pass.rise.unix_epoch.raw, almanac.tiangong.next_visible_pass.set.unix_epoch.raw, almanac.tiangong.next_visible_pass.max_altitude.degree_angle.raw, almanac.tiangong.next_visible_pass.duration.second.raw, almanac.tiangong.next_visible_pass.rise_azimuth.ordinal_compass, almanac.tiangong.next_visible_pass.culmination_azimuth.ordinal_compass, almanac.tiangong.next_visible_pass.set_azimuth.ordinal_compass, almanac.tiangong.next_pass.rise.unix_epoch.raw, almanac.tiangong.next_pass.set.unix_epoch.raw, almanac.tiangong.next_pass.max_altitude.degree_angle.raw, almanac.tiangong.next_pass.duration.second.raw, almanac.tiangong.next_pass.rise_azimuth.ordinal_compass, almanac.tiangong.next_pass.culmination_azimuth.ordinal_compass, almanac.tiangong.next_pass.set_azimuth.ordinal_compass, almanac.tiangong.next_pass.visible
   ```

   (Entries already present — e.g. `current.dateTime.raw` — need not be
   repeated; weewx-loopdata ignores duplicates.  The installer checks
   this line at install time and prints tailored
   `--migrate-loopdata-fields` commands when entries the page reads are
   missing — it never edits `[LoopData]` itself.)

   The `almanac.iss.*` and `almanac.tiangong.*` entries are the
   satellite layer.  A satellite you add beyond the installer's two
   appears on the dome and in the rosters once it has a
   `[Skyfield] [[Satellites]]` entry and the same nineteen fields-line
   entries with its tag name; the skin picks the satellite set up
   automatically, only the fields line is per-satellite.  The bundled
   `--add-satellite` utility makes those edits — plus the display name —
   in one command; `--remove-satellite` is its inverse.  See
   [Adding and removing satellites](configuration.md#adding-and-removing-satellites).

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

One action lights up the new satellite layer: append the
`almanac.iss.*` and `almanac.tiangong.*` entries above to your
`[LoopData] [[Include]] fields` line (running
`--migrate-loopdata-fields` appends them for you — it follows your
`[Skyfield]` `[[Satellites]]`, so a customized satellite set gets
entries for its own tags instead of these defaults, and it is
idempotent and never touches non-celestial entries), and run
weewx-skyfield 2.0 with its default `[[Satellites]]`.  Without them the page simply has no
satellites; everything else is drop-in and the rest of the fields line
is unchanged.  The install itself reminds you: when the fields line is
missing entries the page reads, the installer prints the exact migrator
commands, tailored to your configuration.

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
   2.0+ if you have not already, then install this version.

1. Run the bundled utility to rewrite your `[LoopData] [[Include]] fields`
   line — every celestial entry (including pre-3.0 PascalCase names)
   becomes its almanac equivalent, rendition suffixes are honored,
   non-celestial entries are never touched, and the fields the report
   needs are appended.  The satellite entries follow your `[Skyfield]`
   `[[Satellites]]` — fields for exactly the satellites you have
   configured, the installer defaults (iss, tiangong) only when there
   is no `[[Satellites]]` section to follow.  Raw times and durations
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

   (`--in-place` edits weewx.conf directly after making a
   `.bak-celestial-<version>` backup; `--print-fields-value` just prints
   the migrated line for cut-and-paste.)

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
