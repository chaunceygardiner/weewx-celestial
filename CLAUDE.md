# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A WeeWX extension with one job: a `StdService` that inserts celestial observations
(sunrise, twilight times, moon phase, earth-to-body distances, ...) into every LOOP
packet, for consumption by weewx-loopdata.  Everything is computed with Skyfield and
the bundled JPL DE421 ephemeris.

Report tags (`$almanac.sunrise`, `$almanac.rigel.mag`, ...) are NOT this extension's
job: versions 3.x embedded a Skyfield report almanac, and 4.0 removed it.  That engine
lives on in the independent weewx-skyfield extension (same author, sibling checkout at
`../weewx-skyfield`), which is now its sole home — engine fixes go there, and loop-field
fixes go here.  The two are designed to coexist with no configuration.

## Commands

Tests and development require the Python from a WeeWX virtual environment (WeeWX, Skyfield,
NumPy, pytest installed).  On this machine that venv is `/home/weewx/weewx-venv`.

```sh
# Full test suite (from the repo root; tests add bin/user to sys.path themselves)
/home/weewx/weewx-venv/bin/python -m pytest tests

# One test
/home/weewx/weewx-venv/bin/python -m pytest tests/test_celestial.py::TestStars::test_proxima_distance_in_packet

# Lint — BOTH must stay completely clean
pyflakes3 bin/user/celestial.py tests/test_celestial.py
mypy --ignore-missing-imports bin/user/celestial.py

# After editing the sample skin template, run the end-to-end render tests.
# Template.compile alone is NOT sufficient: with #errorCatcher Echo, Cheetah
# re-compiles each placeholder at render time and rejects constructs plain
# compilation accepts (e.g. `$(x if $cond else '')` loses its else-value and
# dies with SyntaxError only in production).  Guard cells with directive-level
# `#if ...#...#end if#`, never with conditional expressions inside $(...).
/home/weewx/weewx-venv/bin/python -m pytest tests/test_celestial.py::TestSampleSkinRenders

# Install into a WeeWX instance, then restart weewx.  Deploying requires
# root (WeeWX runs as root on these machines).  Claude: you cannot run
# this (sudo needs a password you don't have); print the command and have
# the human run it in their own terminal.
sudo -- bash -c ". /home/weewx/weewx-venv/bin/activate; weectl extension install /path/to/weewx-celestial -y"
```

## Architecture

Everything lives in `bin/user/celestial.py`, in two layers:

- **`Celestial(StdService)`** — reads `[Celestial]` config, binds `NEW_LOOP_PACKET`.
- **`Sky`** — the Skyfield engine: loads the timescale, the ephemeris
  (`celestial_de421.bsp`) and the star catalog, and owns the loop-field computation
  (`insert_fields`).  Its `__init__` NEVER raises: every failure logs and leaves
  `valid=False`, and the service then simply does nothing.  `EPHEMERIS_KEYS` is the
  single source of truth for the bodies served.

**Caching: each field class has its own lifetime** (`insert_fields` is three sections):
continuous fields (`get_continuous_fields`, ~20 ms) run every packet, throttled only by
`update_rate_secs` (default 0 = every loop record); day-scoped fields (`get_day_fields`,
~150 ms) recompute when the packet's local day changes — compared for EQUALITY, so
backfilled packets get their own day, never a newer cache; next-event fields
(`get_event_fields`, ~110 ms of months-long scans) recompute when the local day advances
past a cached event (events are deliberately kept for the rest of their day after they
occur).  `TestFieldCaching` pins all of this, including that a cached packet equals a
cold-computed one.  Don't collapse these lifetimes back into one blanket cache — the
~270 ms full recompute per cycle is why 2.3 had to introduce a 10-second throttle.

**Correctness policy: accepted definitions (USNO/IAU/Meeus), verified against
weewx-skyfield.**  The loop fields and weewx-skyfield's report tags compute from the same
definitions (rise/set with standard refraction plus the date's apparent radius, geometric
custom horizons for twilight, coordinates of date for RA/Dec), and
`TestLoopPacketConsistency` cross-checks the two whenever weewx-skyfield is importable.
`TestLoopPacketPinned` pins regression values (captured from 3.1) that run even without it.
When a definition changes on either side, both repos and both test classes must move together.

**Loop fields** are registered in `OBS_GROUPS` (name → unit group).  The pre-3.0
PascalCase names were dual-emitted through 3.x and removed in 4.0
(`TestDeprecatedFieldsRemoved` keeps them from coming back).  The old→new mapping
survives only as `_MIGRATION_FIELD_MAP`, which exists solely for the
`--migrate-loopdata-fields` CLI utility (rewrites users' `[LoopData]` fields lines;
safe-by-default `--output`, plus `--in-place` and `--print-fields-value`) and must never
grow another consumer.  Distances are unit-converted
(miles/km) except `earthProximaCentauriDistance`, which is light years in every unit
system (`group_data`, so nothing "converts" it).

**Stars**: the loop path needs exactly one star — Proxima Centauri (`LOOP_STARS`), for
`earthProximaCentauriDistance`.  `celestial_stars.dat` is an excerpt of unmodified
`hip_main.dat` records (it still covers the full IAU named-star set, so it doubles as a
stand-in full catalog); a user-installed `hip_main.dat` (gitignored) stands in when the
excerpt is missing.  A malformed catalog record must only disable that one star; an
unreadable catalog must only disable star support, never the engine.

**Sample skin** (`skins/Celestial/`): a live "night-palette" page.  Every report-time data
cell is guarded by `$almanac.hasExtras` (and `#try` where a tag needs WeeWX 5.2 or the
Skyfield almanac), so the page renders first-paint values from whatever capable almanac is
installed (weewx-skyfield or built-in PyEphem) and still generates, with empty
javascript-filled cells, without one.  The live components (moon disc, countdown chips, day
strip, planet chips) are javascript-only, driven by loop data at `refresh_rate` plus a 1 s
local tick; every loop-data read is guarded so a missing key skips its own cell, never the
batch.  Data-cell element ids must match loop-data keys exactly; the live components use
non-key ids (`moon-disc`, `count-*`, `planet-*`).  ALL colors live in `celestial.css`
(shipped via CopyGenerator copy_once): Cheetah owns `#` and `$`, so hex color literals and
JS template literals must never appear in the .tmpl/.inc files — a test enforces the hex
rule, and the display timezone is auto-detected from the station machine
(/etc/localtime → IANA name) with the `time_zone` Extras option as override ('browser' =
viewer-local).

**Installed file naming**: files this extension installs into `bin/user` are prefixed
`celestial_` (`celestial_de421.bsp`, `celestial_stars.dat`) so no other extension can claim
them — and remove them on its uninstall.  Skyfield does not care about the ephemeris
filename.  `hip_main.dat` deliberately keeps its canonical name: it is user-supplied, not
installed.

## Tests

`tests/test_celestial.py` pins TZ to America/Los_Angeles and uses fixed regression values
for Palo Alto on 2025-06-21 (`TIME_TS`).  Key fixtures/helpers: `sky` (session-scoped
engine), `wxskyfield_sky`/`wxskyfield_almanac` (the weewx-skyfield oracle — found via
`WXSKYFIELD_DIRS`: the installed copy or the sibling checkout; tests using it skip when
neither exists), `saved_almanacs()`, `StubEngine`/`make_config()`.  The oracle dirs also
contain a `celestial.py`, so `load_wxskyfield()` APPENDS to sys.path — never insert(0).
`TestLoopPacketPinned` must keep passing with no wxskyfield anywhere.

## Releasing

Version lives in two places: `install.py` (`version=`) and `CELESTIAL_VERSION` in
celestial.py.  Every user-visible change gets a bullet in changes.txt under the release
heading — action-required items (renames, config changes) go at the TOP of the entry.
New loop fields must also be added to: the README field list, the README upgrade notes
(the `[LoopData] [[Include]] [[[fields]]]` line users must edit), and the sample skin
(template cell + javascript updater).
