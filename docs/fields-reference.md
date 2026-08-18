---
title: Fields reference
layout: default
nav_order: 8
description: Every weewx-loopdata field the Celestial page reads — the body positions, the moon-phase pair, the thirteen countdown-chip event fields, the nineteen-entry satellite pattern and the six-entry comet pattern — with the complete fields line for copy-and-paste.
---

# Fields reference

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

This is the canonical list of what the page reads.  Everything else in
the manual links here rather than repeating it.

A field is a WeeWX report almanac tag written **with the `$` removed**:
`$almanac.mars.az` in a template is `almanac.mars.az` on the fields line.
weewx-loopdata evaluates each one on every loop packet — with whatever
almanac WeeWX has registered — and publishes it in `loop-data.txt`, where
the page's javascript reads it by that exact name.  The full grammar is
in
[weewx-loopdata's manual](https://chaunceygardiner.github.io/weewx-loopdata/almanac-fields.html).

Two rules govern the line itself:

{: .important }
`[LoopData] [[Include]] fields` must stay a **bare comma-separated list**
— no brackets, no quotes.  Every almanac entry the page uses takes at
most one argument precisely so that no entry ever contains a comma.

**Extra fields are harmless.**  weewx-loopdata publishes whatever you
list and the page reads only its own keys, so a line shared with other
pages of your own is fine — and must not be trimmed to this list without
checking what those pages consume.

As of 8.1 you do not normally type any of this: `weectl extension
install` appends the entries missing from your line, append-only,
printing each one.  This page is the reference for hand editing, for
older installs, and for understanding what a layer costs.

## What the page reads

The skin consumes exactly 100 entries with the installer's default two
satellites and two comets.  They fall into five groups.

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
*set* automatically from `[Skyfield] [[Satellites]]` — only the fields
line is per-satellite, which is what
[`--add-satellite`](satellites-and-comets.md#adding-and-removing-satellites)
exists to handle.

### Comets (6 entries each)

Per configured comet, with the comet's tag in place of `halley`:

```
almanac.halley.az, almanac.halley.alt, almanac.halley.earth_distance,
almanac.halley.mag, almanac.halley.label,
almanac.halley.perihelion.unix_epoch.raw
```

`mag` is what decides whether the diamond draws solid or hollow;
`perihelion` feeds that comet's windowed countdown chip.

## What a missing field does

Nothing breaks.  weewx-loopdata omits a field it cannot compute from
`loop-data.txt` (logging one line per field at startup), and the page
distinguishes two cases deliberately:

- **A field absent from the line** — the report-time first paint stands,
  and that cell simply never goes live.
- **A field present but null** — the page treats it as honestly empty:
  the chip hides, or the roster row says why.

So the satellite and comet entries are safe to add before you run an
almanac that can serve them: the layer stays hidden until it can.

## The complete line

The installer's defaults — the ISS and Tiangong, Halley and Hale-Bopp —
as one line, for hand editing:

```
current.dateTime.raw, almanac.sun.az, almanac.sun.alt, almanac.sun.earth_distance, almanac.moon.az, almanac.moon.alt, almanac.moon.earth_distance, almanac.moon.phase, almanac.next_full_moon.unix_epoch.raw, almanac.next_new_moon.unix_epoch.raw, almanac.mercury.az, almanac.mercury.alt, almanac.mercury.earth_distance, almanac.venus.az, almanac.venus.alt, almanac.venus.earth_distance, almanac.mars.az, almanac.mars.alt, almanac.mars.earth_distance, almanac.jupiter.az, almanac.jupiter.alt, almanac.jupiter.earth_distance, almanac.saturn.az, almanac.saturn.alt, almanac.saturn.earth_distance, almanac.uranus.az, almanac.uranus.alt, almanac.uranus.earth_distance, almanac.neptune.az, almanac.neptune.alt, almanac.neptune.earth_distance, almanac.pluto.az, almanac.pluto.alt, almanac.pluto.earth_distance, almanac.proxima_centauri.az, almanac.proxima_centauri.alt, almanac.proxima_centauri.earth_distance, almanac.sun.next_setting.unix_epoch.raw, almanac.sun.next_rising.unix_epoch.raw, almanac(horizon=-18).sun.next_setting.unix_epoch.raw, almanac(horizon=-18).sun.next_rising.unix_epoch.raw, almanac.next_equinox.unix_epoch.raw, almanac.next_solstice.unix_epoch.raw, almanac.next_perihelion.unix_epoch.raw, almanac.next_aphelion.unix_epoch.raw, almanac.next_meteor_shower.peak.unix_epoch.raw, almanac.next_meteor_shower.label, almanac.next_supermoon.unix_epoch.raw, almanac.next_eclipse.unix_epoch.raw, almanac.next_eclipse_kind, almanac.iss.az, almanac.iss.alt, almanac.iss.sunlit, almanac.iss.label, almanac.iss.next_visible_pass.rise.unix_epoch.raw, almanac.iss.next_visible_pass.set.unix_epoch.raw, almanac.iss.next_visible_pass.max_altitude.degree_angle.raw, almanac.iss.next_visible_pass.duration.second.raw, almanac.iss.next_visible_pass.rise_azimuth.ordinal_compass, almanac.iss.next_visible_pass.culmination_azimuth.ordinal_compass, almanac.iss.next_visible_pass.set_azimuth.ordinal_compass, almanac.iss.next_pass.rise.unix_epoch.raw, almanac.iss.next_pass.set.unix_epoch.raw, almanac.iss.next_pass.max_altitude.degree_angle.raw, almanac.iss.next_pass.duration.second.raw, almanac.iss.next_pass.rise_azimuth.ordinal_compass, almanac.iss.next_pass.culmination_azimuth.ordinal_compass, almanac.iss.next_pass.set_azimuth.ordinal_compass, almanac.iss.next_pass.visible, almanac.tiangong.az, almanac.tiangong.alt, almanac.tiangong.sunlit, almanac.tiangong.label, almanac.tiangong.next_visible_pass.rise.unix_epoch.raw, almanac.tiangong.next_visible_pass.set.unix_epoch.raw, almanac.tiangong.next_visible_pass.max_altitude.degree_angle.raw, almanac.tiangong.next_visible_pass.duration.second.raw, almanac.tiangong.next_visible_pass.rise_azimuth.ordinal_compass, almanac.tiangong.next_visible_pass.culmination_azimuth.ordinal_compass, almanac.tiangong.next_visible_pass.set_azimuth.ordinal_compass, almanac.tiangong.next_pass.rise.unix_epoch.raw, almanac.tiangong.next_pass.set.unix_epoch.raw, almanac.tiangong.next_pass.max_altitude.degree_angle.raw, almanac.tiangong.next_pass.duration.second.raw, almanac.tiangong.next_pass.rise_azimuth.ordinal_compass, almanac.tiangong.next_pass.culmination_azimuth.ordinal_compass, almanac.tiangong.next_pass.set_azimuth.ordinal_compass, almanac.tiangong.next_pass.visible, almanac.halley.az, almanac.halley.alt, almanac.halley.earth_distance, almanac.halley.mag, almanac.halley.label, almanac.halley.perihelion.unix_epoch.raw, almanac.hale_bopp.az, almanac.hale_bopp.alt, almanac.hale_bopp.earth_distance, almanac.hale_bopp.mag, almanac.hale_bopp.label, almanac.hale_bopp.perihelion.unix_epoch.raw
```

Entries already on your line need not be repeated; weewx-loopdata
ignores duplicates.
