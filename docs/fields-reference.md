---
title: Fields reference
layout: default
nav_order: 8
description: Every weewx-loopdata field the Celestial page reads — the body positions, the moon-phase pair, the thirteen countdown-chip event fields, the nineteen-entry satellite pattern and the six-entry comet pattern — and how the page declares them, in the skin and in weewx.conf.
---

# Fields reference

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

This is the canonical list of what the page reads.  Everything else in
the manual links here rather than repeating it.

A field is a WeeWX report almanac tag written **with the `$` removed**:
`$almanac.mars.az` in a template is `almanac.mars.az` in a declaration.
weewx-loopdata (7.0 or later) evaluates each one on every loop packet —
with whatever almanac WeeWX has registered — and publishes it in
`loop-data.txt` under this report's name, rendered with this report's
own units, formats and `[Almanac]` names, where the page's javascript
reads it by that exact key.  The full grammar is in
[weewx-loopdata's manual](https://chaunceygardiner.github.io/weewx-loopdata/almanac-fields.html).

## How the page declares them

The page declares what it reads in two places, and you do not normally
type any of it:

- **The fields that never change** — the clock, the eleven bodies, the
  countdown events — ship in the skin's own `skin.conf`, as a
  `[LoopData] [[fields]]` section of named groups (the names are the
  handles the merge below works by; ConfigObj has no line continuation
  for lists).  It is printed in full [below](#the-shipped-declaration).
- **The satellite and comet fields** follow your `[Skyfield]
  [[Satellites]]` and `[[Comets]]`, which no shipped file can know, so
  `weectl extension install` writes them into `weewx.conf` as two more
  groups under the report's own stanza — `satellites` and `comets` in
  `[StdReport] [[CelestialReport]] [[[LoopData]]] [[[[fields]]]]` —
  rebuilt on every install, and by
  [`--add-satellite`](satellites-and-comets.md#adding-and-removing-satellites)
  and `--add-comet` on every edit, so they always track your sets.  Both
  write the two groups under *every* report running the Celestial skin,
  so a second report of your own — the page in another language, say —
  needs nothing declared by hand, and under every report of another skin
  that names the panels it embeds — `celestial_panels`, which that skin
  declares in its own `skin.conf` (9.0; see
  [Panels in your own skin](own-skin.md#2-the-fields-the-panels-read)) —
  which gets exactly the groups those panels read.  Also printed
  [below](#the-installers-stanza), for the defaults.

weewx-loopdata reads the two merged, group by group: a group named in
`weewx.conf` replaces the skin's group of that name, a new name adds one.
So **a field of your own goes in a group of your own** in the `weewx.conf`
stanza — never in the skin file, which the next upgrade overwrites, and
never in the `satellites`/`comets` groups, which the next install
rebuilds.  (An *uninstall* removes the report's whole stanza, your groups
with it, as it does `[[[Extras]]]`; keep a copy if you uninstall.)  A group line is a bare comma-separated list; every entry the
page uses takes at most one argument precisely so that no entry ever
contains a comma and needs quoting.

{: .note }
The older `[LoopData] [[Include]] fields` line in `weewx.conf` is not
this page's business any more.  Since 8.5 the installer never writes it,
and only reads it to count: the entries on it that this page now declares
itself — the ~100 that 8.1–8.4's installers appended — are evaluated
**twice per loop packet** by weewx-loopdata 7.0 while the line stands,
and the install says how many.  weewx-loopdata warns about the line at startup and
retires it in a later release of its own; trim this page's entries from
it sooner if no other page of yours reads them.  Do not add this page's
fields to it.

## What the page reads

The skin consumes exactly 100 entries with the installer's default two
satellites and two comets.  They fall into six kinds.

### The clock (1 entry)

`current.dateTime.raw` — the packet's timestamp, and the page's clock:
the "updated" stamp, every countdown chip, the rosters' "overhead now"
and the pass chart's verdict are all reckoned against it, rates are
derived from consecutive stamps, and a record without it is dropped
whole (see [Whose time it is](how-it-stays-live.md#whose-time-it-is)).

### Body positions (33 entries)

Three entries — `az`, `alt`, `earth_distance` — for each of the eleven
bodies on the Geocentric dial:

```
almanac.<body>.az, almanac.<body>.alt, almanac.<body>.earth_distance
```

for `sun`, `moon`, `mercury`, `venus`, `mars`, `jupiter`, `saturn`,
`uranus`, `neptune`, `pluto` and `proxima_centauri`.

Distances arrive as **raw astronomical units**; the page converts them
for display.  `proxima_centauri` needs weewx-skyfield — PyEphem's star
catalog does not carry it, and that row simply renders empty.

### The moon's phase (3 entries)

```
almanac.moon.phase, almanac.next_full_moon.unix_epoch.raw, almanac.next_new_moon.unix_epoch.raw
```

`almanac.moon.phase` is a raw percent (`33.6`), not a formatted string.
The two instants are what tell the page whether the moon is waxing: it is
waxing exactly when the next full moon comes before the next new moon.

### The countdown chips (13 entries)

| Chip | Fields |
|---|---|
| Sunset / sunrise | `almanac.sun.next_setting.unix_epoch.raw`, `almanac.sun.next_rising.unix_epoch.raw` |
| Astronomical darkness | `almanac(horizon=-18).sun.next_setting.unix_epoch.raw`, `almanac(horizon=-18).sun.next_rising.unix_epoch.raw` |
| Season begins | `almanac.next_equinox.unix_epoch.raw`, `almanac.next_solstice.unix_epoch.raw` |
| Earth perihelion / aphelion | `almanac.next_perihelion.unix_epoch.raw`, `almanac.next_aphelion.unix_epoch.raw` |
| Meteor shower peak | `almanac.next_meteor_shower.peak.unix_epoch.raw`, `almanac.next_meteor_shower.label` |
| Supermoon | `almanac.next_supermoon.unix_epoch.raw` |
| Eclipse | `almanac.next_eclipse.unix_epoch.raw`, `almanac.next_eclipse_kind` |

{: .note }
The two `almanac(horizon=-18)` entries must be spelled exactly as shown —
the javascript looks them up by that literal key.  There is no loop field
for the eclipse *type* (total, partial, annular, penumbral): the page
renders it at generation time from the report tag, deliberately, because
its own field can lag the rolled instant.

The satellite-pass chip needs no fields of its own — it reads the
satellite entries below.

### Satellites (19 entries each)

Per configured satellite, with the satellite's tag in place of `iss`:

```
almanac.iss.az, almanac.iss.alt, almanac.iss.sunlit, almanac.iss.label,
almanac.iss.next_visible_pass.rise.unix_epoch.raw,
almanac.iss.next_visible_pass.set.unix_epoch.raw,
almanac.iss.next_visible_pass.max_altitude.degree_angle.raw,
almanac.iss.next_visible_pass.duration.second.raw,
almanac.iss.next_visible_pass.rise_azimuth.ordinal_compass,
almanac.iss.next_visible_pass.culmination_azimuth.ordinal_compass,
almanac.iss.next_visible_pass.set_azimuth.ordinal_compass,
almanac.iss.next_pass.rise.unix_epoch.raw,
almanac.iss.next_pass.set.unix_epoch.raw,
almanac.iss.next_pass.max_altitude.degree_angle.raw,
almanac.iss.next_pass.duration.second.raw,
almanac.iss.next_pass.rise_azimuth.ordinal_compass,
almanac.iss.next_pass.culmination_azimuth.ordinal_compass,
almanac.iss.next_pass.set_azimuth.ordinal_compass,
almanac.iss.next_pass.visible
```

`az`/`alt`/`sunlit` drive the live marker on the dome; the
`next_visible_pass` seven feed the Next Visible Pass roster and the pass
chip; the `next_pass` eight feed the "next pass overhead" roster,
`visible` being what tags each row.  The skin discovers your satellite
*set* automatically from `[Skyfield] [[Satellites]]` — only the
declaration is per-satellite, which the installer and
[`--add-satellite`](satellites-and-comets.md#adding-and-removing-satellites)
both handle.

### Comets (6 entries each)

Per configured comet, with the comet's tag in place of `halley`:

```
almanac.halley.az, almanac.halley.alt, almanac.halley.earth_distance,
almanac.halley.mag, almanac.halley.label,
almanac.halley.perihelion.unix_epoch.raw
```

`mag` is what decides whether the diamond draws solid or hollow;
`perihelion` feeds that comet's windowed countdown chip.

## Which groups each panel reads

The bundled page shows every panel, so it declares everything above.  A
skin embedding a subset — see
[Panels in your own skin](own-skin.md) — can paste a subset, and the two
installer-written groups follow the panels its report names in
`celestial_panels`:

| Panel | Groups pasted from the skin's declaration | Written by the installer |
|---|---|---|
| The countdown row | `clock`, `sunset`, `darkness`, `season`, `perihelion`, `meteor_shower`, `supermoon`, `eclipse` | `satellites` (the pass chip), `comets` (the perihelion chips) |
| The Geocentric | `clock`, the eleven body groups (`sun` … `proxima_centauri`) | `comets` |
| The sky dome | `clock`, the eleven body groups — the marks it nudges between backdrops are the sun, the moon and the planets | `satellites` |
| The Next Visible Pass | `clock` | `satellites` |

`clock` is not optional anywhere: `current.dateTime.raw` is the page's
whole notion of time, and a record without it is dropped.  Pasting all
the static groups whatever you show is the simple choice — an unread
group costs one evaluation per packet and nothing else — but a group a
panel does read has to be there, or that panel first-paints and never
moves.

## What a missing field does

Nothing breaks.  weewx-loopdata omits a field it cannot compute from
`loop-data.txt` (logging one line per field at startup), and the page
distinguishes two cases deliberately:

- **A field not declared** — the report-time first paint stands, and
  that cell simply never goes live.
- **A field declared but null** — the page treats it as honestly empty:
  the chip hides, or the roster row says why.

So the satellite and comet entries are safe to declare before you run an
almanac that can serve them: the layer stays hidden until it can.

## The shipped declaration

`skins/Celestial/skin.conf`'s `[LoopData]` section, as shipped — the
fifty fields that do not depend on your configuration:

```
[LoopData]
    [[fields]]
        # The packet's timestamp: the page's clock, the LIVE badge's age
        # and the extrapolation anchor.
        clock = current.dateTime.raw
        # The Geocentric dial and its roster: azimuth places the mark,
        # altitude decides above/below the horizon, earth_distance (raw
        # astronomical units) drives the odometer.  The moon adds its
        # phase percent and the next full/new moon instants (waxing =
        # full before new) for the phase disc.
        sun = almanac.sun.az, almanac.sun.alt, almanac.sun.earth_distance
        moon = almanac.moon.az, almanac.moon.alt, almanac.moon.earth_distance, almanac.moon.phase, almanac.next_full_moon.unix_epoch.raw, almanac.next_new_moon.unix_epoch.raw
        mercury = almanac.mercury.az, almanac.mercury.alt, almanac.mercury.earth_distance
        venus = almanac.venus.az, almanac.venus.alt, almanac.venus.earth_distance
        mars = almanac.mars.az, almanac.mars.alt, almanac.mars.earth_distance
        jupiter = almanac.jupiter.az, almanac.jupiter.alt, almanac.jupiter.earth_distance
        saturn = almanac.saturn.az, almanac.saturn.alt, almanac.saturn.earth_distance
        uranus = almanac.uranus.az, almanac.uranus.alt, almanac.uranus.earth_distance
        neptune = almanac.neptune.az, almanac.neptune.alt, almanac.neptune.earth_distance
        pluto = almanac.pluto.az, almanac.pluto.alt, almanac.pluto.earth_distance
        proxima_centauri = almanac.proxima_centauri.az, almanac.proxima_centauri.alt, almanac.proxima_centauri.earth_distance
        # The countdown row: each chip is client-side arithmetic against
        # one of these event instants, pinned to epoch seconds
        # (.unix_epoch) because the page does date math on them.  The
        # two almanac(horizon=-18) spellings must stay exactly as written:
        # the javascript looks them up by that literal key.
        sunset = almanac.sun.next_setting.unix_epoch.raw, almanac.sun.next_rising.unix_epoch.raw
        darkness = almanac(horizon=-18).sun.next_setting.unix_epoch.raw, almanac(horizon=-18).sun.next_rising.unix_epoch.raw
        season = almanac.next_equinox.unix_epoch.raw, almanac.next_solstice.unix_epoch.raw
        perihelion = almanac.next_perihelion.unix_epoch.raw, almanac.next_aphelion.unix_epoch.raw
        meteor_shower = almanac.next_meteor_shower.peak.unix_epoch.raw, almanac.next_meteor_shower.label
        supermoon = almanac.next_supermoon.unix_epoch.raw
        eclipse = almanac.next_eclipse.unix_epoch.raw, almanac.next_eclipse_kind
```

## The installer's stanza

What `weectl extension install` writes under the report's stanza for the
installer's defaults — the ISS and Tiangong, Halley and Hale-Bopp.  Your
own sets produce the same pattern with your tags; a group of your own
sits beside these two:

```
[StdReport]
    [[CelestialReport]]
        [[[LoopData]]]
            [[[[fields]]]]
                satellites = almanac.iss.az, almanac.iss.alt, almanac.iss.sunlit, almanac.iss.label, almanac.iss.next_visible_pass.rise.unix_epoch.raw, almanac.iss.next_visible_pass.set.unix_epoch.raw, almanac.iss.next_visible_pass.max_altitude.degree_angle.raw, almanac.iss.next_visible_pass.duration.second.raw, almanac.iss.next_visible_pass.rise_azimuth.ordinal_compass, almanac.iss.next_visible_pass.culmination_azimuth.ordinal_compass, almanac.iss.next_visible_pass.set_azimuth.ordinal_compass, almanac.iss.next_pass.rise.unix_epoch.raw, almanac.iss.next_pass.set.unix_epoch.raw, almanac.iss.next_pass.max_altitude.degree_angle.raw, almanac.iss.next_pass.duration.second.raw, almanac.iss.next_pass.rise_azimuth.ordinal_compass, almanac.iss.next_pass.culmination_azimuth.ordinal_compass, almanac.iss.next_pass.set_azimuth.ordinal_compass, almanac.iss.next_pass.visible, almanac.tiangong.az, almanac.tiangong.alt, almanac.tiangong.sunlit, almanac.tiangong.label, almanac.tiangong.next_visible_pass.rise.unix_epoch.raw, almanac.tiangong.next_visible_pass.set.unix_epoch.raw, almanac.tiangong.next_visible_pass.max_altitude.degree_angle.raw, almanac.tiangong.next_visible_pass.duration.second.raw, almanac.tiangong.next_visible_pass.rise_azimuth.ordinal_compass, almanac.tiangong.next_visible_pass.culmination_azimuth.ordinal_compass, almanac.tiangong.next_visible_pass.set_azimuth.ordinal_compass, almanac.tiangong.next_pass.rise.unix_epoch.raw, almanac.tiangong.next_pass.set.unix_epoch.raw, almanac.tiangong.next_pass.max_altitude.degree_angle.raw, almanac.tiangong.next_pass.duration.second.raw, almanac.tiangong.next_pass.rise_azimuth.ordinal_compass, almanac.tiangong.next_pass.culmination_azimuth.ordinal_compass, almanac.tiangong.next_pass.set_azimuth.ordinal_compass, almanac.tiangong.next_pass.visible
                comets = almanac.halley.az, almanac.halley.alt, almanac.halley.earth_distance, almanac.halley.mag, almanac.halley.label, almanac.halley.perihelion.unix_epoch.raw, almanac.hale_bopp.az, almanac.hale_bopp.alt, almanac.hale_bopp.earth_distance, almanac.hale_bopp.mag, almanac.hale_bopp.label, almanac.hale_bopp.perihelion.unix_epoch.raw
```
