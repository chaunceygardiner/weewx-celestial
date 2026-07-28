---
title: Installation
description: Installing weewx-celestial 7.x, and upgrading from 6.x or from 5.x and earlier with the bundled --migrate-loopdata-fields utility.
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
   5.0 or later and
   [weewx-skyfield](https://chaunceygardiner.github.io/weewx-skyfield/),
   both per their instructions.

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
   current.dateTime.raw, almanac.sun.az, almanac.sun.alt, almanac.sun.earth_distance, almanac.moon.az, almanac.moon.alt, almanac.moon.earth_distance, almanac.moon.phase, almanac.next_full_moon.raw, almanac.next_new_moon.raw, almanac.mercury.az, almanac.mercury.alt, almanac.mercury.earth_distance, almanac.venus.az, almanac.venus.alt, almanac.venus.earth_distance, almanac.mars.az, almanac.mars.alt, almanac.mars.earth_distance, almanac.jupiter.az, almanac.jupiter.alt, almanac.jupiter.earth_distance, almanac.saturn.az, almanac.saturn.alt, almanac.saturn.earth_distance, almanac.uranus.az, almanac.uranus.alt, almanac.uranus.earth_distance, almanac.neptune.az, almanac.neptune.alt, almanac.neptune.earth_distance, almanac.pluto.az, almanac.pluto.alt, almanac.pluto.earth_distance, almanac.proxima_centauri.az, almanac.proxima_centauri.alt, almanac.proxima_centauri.earth_distance
   ```

   (Entries already present — e.g. `current.dateTime.raw` — need not be
   repeated; weewx-loopdata ignores duplicates.)

1. Restart WeeWX.  The report appears under `celestial/` of your web root.

## Upgrading from 7.x

Drop-in: uninstall, install, restart —

```
weectl extension uninstall celestial
weectl extension install weewx-celestial.zip
```

No `weewx.conf` changes; the fields line is unchanged.  Note that
upgrading replaces the bundled skin (`skins/Celestial/`, including its
`lang/` files) — local additions and overrides survive upgrades best as
`[[[Almanac]]]`/`[[[Texts]]]` entries in the report's section of
`weewx.conf` (see [Translating](i18n.md)).

## Upgrading from 6.x

1. Uninstall the old version, then install the new one:

   ```
   weectl extension uninstall celestial
   weectl extension install weewx-celestial.zip
   ```

1. Restart WeeWX.  (The restart also refreshes the deployed
   `celestial.css` — CopyGenerator re-copies `copy_once` files on every
   report first-run — and the page version-tags the stylesheet URL, so
   browsers refetch it too.)

Your existing `[LoopData] [[Include]] fields` line keeps working as is —
7.x reads a subset of the 6.0 field set plus three new entries, so add
`almanac.proxima_centauri.az, almanac.proxima_centauri.alt` (the
migration utility adds them too, but for a 6.0 line it is simpler by
hand).  The remaining 6.0 entries (rise/sets, twilights, ra/dec,
equinox/solstice, `almanac.moon_phase`, `almanac.moon_index`, sun
visible-time) are no longer read by this skin; keep them if your own
pages consume them, or trim them to the list above.

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
   5.0+ and [weewx-skyfield](https://chaunceygardiner.github.io/weewx-skyfield/)
   if you have not already, then install this version.

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
