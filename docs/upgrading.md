---
title: Upgrading
layout: default
nav_order: 3
description: Upgrading weewx-celestial within 8.x, or from 7.x, 6.x or 5.x and earlier — what each path needs, the bundled --migrate-loopdata-fields utility, and the three 6.0 field changes with no 1:1 equivalent.
---

# Upgrading

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Find your current version below.  Every path ends the same way: the page
reads the entries listed in the [Fields reference](fields-reference.md),
and as of 8.1 the installer appends the missing ones for you.

## Upgrading within 8.x

Install over the top and restart WeeWX — that is the whole procedure:

```
weectl extension install weewx-celestial.zip
```

There are no configuration changes between 8.x releases.  The install
appends any fields-line entries a newer version reads (append-only,
printing each one), and the restart both reloads that line in
weewx-loopdata and refreshes the deployed `celestial.css` and `sky.js`.

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
is now ignored rather than timestamped from the browser; the fields line
this extension prescribes always carries it.

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

Install right over the existing version, then restart WeeWX —

```
weectl extension install weewx-celestial.zip
```

One action lights up the new layers: your `[LoopData] [[Include]] fields`
line needs the satellite entries (8.0) and 8.1's countdown-chip and
per-comet entries.  As of 8.1 the install itself appends them —
append-only, each one printed — so restart weewxd afterwards to make
weewx-loopdata reload the line, and that is the whole upgrade.

Run weewx-skyfield 2.3.2 — 2.1 brought the comets and the
shower/supermoon chips, 2.3.2 the pass chart's own rise and set that
lets its dot leave the chart when the pass ends; 2.0 still serves the
satellites, and the sunset, darkness and pass chips count on any of them.
Without the entries the page simply hides those layers and chips.  Everything else is drop-in, and the rest of the fields line
is untouched.

The `--migrate-loopdata-fields` utility remains available and appends the
same entries: it follows your `[Skyfield]` `[[Satellites]]` and
`[[Comets]]`, so a customized set gets entries for its own tags instead
of the defaults, and it is idempotent and never touches non-celestial
entries.  It is only *needed* when the line still carries pre-6.0
spellings — renames deserve review, so the installer prints the exact
migrator commands, tailored to your machine, instead of applying them.

{: .note }
Upgrading replaces the bundled skin (`skins/Celestial/`, including its
`lang/` files).  Local additions survive upgrades best as
`[[[Almanac]]]`/`[[[Texts]]]` entries in the report's section of
`weewx.conf` — see [Translations](i18n.md).

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

Your existing fields line keeps working as is: 8.x reads a subset of the
6.0 field set, plus the Proxima Centauri, satellite, comet and countdown
entries in the [Fields reference](fields-reference.md).  The installer
appends those; `--migrate-loopdata-fields` does the same in one
idempotent pass if you would rather run it by hand.

The remaining 6.0 entries (rise/sets, twilights, ra/dec,
equinox/solstice, `almanac.moon_phase`, `almanac.moon_index`, sun
visible-time) are no longer read by this skin.  Keep them if your own
pages consume them, or trim them.

{: .important }
If you still list `user.celestial.Celestial` under `data_services` in
`[Engine] [[Services]]` — a leftover from 2.x that 6.x tolerated with a
stub — **remove it now**.  7.0 deleted the stub, and a stale entry will
keep weewxd from starting.

## Upgrading from 5.x or earlier

6.0 removed this extension's own loop fields (`current.sunrise`,
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
   2.3.2+ if you have not already, then install this version.

1. Run the bundled utility to rewrite your `[LoopData] [[Include]] fields`
   line — every celestial entry (including pre-3.0 PascalCase names)
   becomes its almanac equivalent, rendition suffixes are honored,
   non-celestial entries are never touched, and the fields the report
   needs are appended.  The satellite and comet entries follow your
   `[Skyfield]` `[[Satellites]]` and `[[Comets]]` — fields for exactly
   the sets you have configured, the installer defaults (iss and
   tiangong; halley and hale_bopp) only when there is no section to
   follow.  Raw times and durations arrive with pinned units
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

   Review with a **word-diff**: the fields line is one long
   comma-separated value, so a plain `diff` shows only two unreadable
   lines.

   (The commands `weectl extension install` prints are tailored to your
   machine and carry the prefix already.  `--in-place` edits weewx.conf
   directly after making a `.bak-celestial-<version>` backup;
   `--print-fields-value` just prints the migrated line for
   cut-and-paste.)

1. Restart WeeWX.

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
