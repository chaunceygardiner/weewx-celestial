---
title: Satellites and comets
layout: default
nav_order: 7
description: Adding and removing satellites and comets with the bundled --add-satellite/--add-comet utilities — the three weewx.conf edits each one takes, idempotent rewrites, tags and the shared namespace, and what removal deliberately leaves behind.
---

# Satellites and comets

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Satellites and comets are the two things on the Celestial page that you
choose.  Both
are computed by weewx-skyfield and both live in `weewx.conf`, and each
one takes the same **three separate edits**:

1. the `[Skyfield] [[Satellites]]` or `[[Comets]]` entry, which tells
   weewx-skyfield to track it,
2. its fields-line entries, which put it in the live feed — nineteen for
   a satellite, six for a comet (see the
   [Fields reference](fields-reference.md)),
3. a display name under `[StdReport] [[Defaults]] [[[Almanac]]]`, so
   every report *and* the loop feed call it the same thing.  (Display
   names reach the page on WeeWX 5.3 and later; on 5.2 the tag name
   itself is shown.)

The extension bundles a utility that makes all three in one command, one
object per run, so the three cannot drift apart.  The skin itself needs
no configuration: it enumerates whatever is configured.

## Adding and removing satellites

```
source /home/weewx/weewx-venv/bin/activate
cd /home/weewx/bin    # the directory CONTAINING the `user` package
                      # (~/weewx-data/bin on pip installs)
python -m user.celestial --add-satellite zenit23088=23088 --name 'Zenit-2 23088' --config /home/weewx/weewx.conf --output /tmp/weewx.conf.new
git diff --no-index --word-diff /home/weewx/weewx.conf /tmp/weewx.conf.new   # review, then move into place
```

On a Debian or Red Hat package install there is no venv to activate, and
WeeWX's own code lives in `/usr/share/weewx` — on the path only inside
`weectl` — so run from `/etc/weewx/bin` with a
`PYTHONPATH=/usr/share/weewx python3` prefix instead.  The same goes for
every `python -m user.celestial` command in this manual.

The tag (`zenit23088` — a lowercase identifier of your choosing, refused
if it shadows a body name the almanac already serves) becomes the
satellite's report tag and loop-field name; the number is its NORAD
catalog number ([search CelesTrak](https://celestrak.org/satcat/search.php)).
`--output` writes a copy and never touches the original; `--in-place`
edits `weewx.conf` directly after making a `.bak-celestial-<version>`
backup (root-owned configurations need `sudo` for either the move or
`--in-place`).  Restart weewxd afterwards — it fetches the new
satellite's orbital elements soon after start.

{: .note }
Review with a **word-diff**.  The fields line is one very long
comma-separated value, so a plain `diff` shows two unreadable lines and
tells you nothing about what changed.

Every edit is independently idempotent, so any starting state converges:
a satellite already configured per
[weewx-skyfield's manual](https://chaunceygardiner.github.io/weewx-skyfield/)
keeps its `[[Satellites]]` entry and gains the fields; re-running with a
different number or `--name` updates that piece in place (the rename
path); `--name` omitted leaves an existing name alone and merely prints
the line to add later.

Keep the list short — each satellite is a separate CelesTrak fetch every
three hours — and note that a satellite's orbital inclination bounds the
latitudes it can appear over, so a satellite configured for a station it
never crosses will honestly report no passes for ever
(weewx-skyfield's manual has the details).

`--remove-satellite zenit23088` is the exact inverse: it deletes the
`[[Satellites]]` entry, every `almanac.zenit23088.*` fields entry, and
the display name — each if present, so removing an absent satellite is a
no-op.  Two things it deliberately leaves: the cached element file
(`wxskyfield_sat_<norad>.tle`, beside the station database), and — when
you remove an installer default (`iss`, `tiangong`) — the knowledge that
a future weewx-skyfield upgrade re-adds the `[[Satellites]]` entry
(only; the fields line stays as you left it), so re-run the removal
afterwards.  The utility prints both reminders.

## Adding and removing comets

A comet is the same three edits — the `[Skyfield] [[Comets]]` entry (tag
= MPC designation), six fields-line entries, the display name — and
`--add-comet` makes them in one command, one comet per run:

```
python -m user.celestial --add-comet a3="C/2023 A3" --name 'Tsuchinshan-ATLAS' --config /home/weewx/weewx.conf --output /tmp/weewx.conf.new
```

The designation is the Minor Planet Center's — a numbered periodic (`1P`,
`220P`) or provisional (`C/2023 A3` — quote it, it has a space)
designation, fragment suffixes allowed (`C/1947 X1-B`).

All comets ride one shared MPC element file, fetched every two days, so
adding comets costs no extra downloads — but a comet the MPC has dropped
serves no values, and the page renders it
[absent](reading-the-page.md#the-geocentric) rather than inventing one.

Everything else works exactly like the satellite verbs: idempotent edits,
`--output`/`--in-place`, the `--remove-comet` inverse, and the same
installer-default warning (removing `halley` or `hale_bopp` wants
re-running after a weewx-skyfield upgrade re-adds the `[[Comets]]`
entry).

{: .important }
Satellites and comets share the `almanac.<tag>` namespace, so each family
refuses the other's tags — and both refuse body names.  You cannot have a
comet called `iss`.

## What they look like on the page

A configured satellite gets a live marker on the sky dome, a row in each
of the two satellite rosters, and a share of the pass countdown chip.  A
configured comet gets a diamond and tail on the Geocentric dial, a roster
row between Pluto and Proxima, and a windowed perihelion chip.  What each
mark's shape and brightness mean is in
[Reading the page](reading-the-page.md).

Configure several and they fly together: the dome draws every satellite
that is up, and each keeps its own pair of roster rows.  Three overhead
at once, on the morning of 18 August 2026 — the ISS climbing through the
zenith, Tiangong crossing to the north, and NOAA-21 skimming the western
horizon at four degrees.

![Three satellites overhead at once: the ISS through the zenith, Tiangong to the north, NOAA-21 low in the west](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialDome-triple-pass.gif)
