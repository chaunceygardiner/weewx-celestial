# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A WeeWX extension with two jobs, both computed with Skyfield and the bundled JPL DE421
ephemeris:

1. **Loop fields** — a `StdService` that inserts celestial observations (sunrise, twilight
   times, moon phase, earth-to-body distances, ...) into every LOOP packet, for consumption
   by weewx-loopdata.
2. **Report almanac** — on WeeWX 5.2+, a `weewx.almanac.AlmanacType` registered at the head
   of `weewx.almanac.almanacs`, so report tags (`$almanac.sunrise`,
   `$almanac(horizon=-6).sun(use_center=1).rise`, `$almanac.rigel.mag`, ...) use Skyfield
   instead of WeeWX's built-in PyEphem/weeutil almanac.

## Commands

Tests and development require the Python from a WeeWX virtual environment (WeeWX, Skyfield,
NumPy, pytest installed; PyEphem enables the parity audits).  On this machine that venv is
`/home/weewx/weewx-venv`.

```sh
# Full test suite (from the repo root; tests add bin/user to sys.path themselves)
/home/weewx/weewx-venv/bin/python -m pytest tests

# One test
/home/weewx/weewx-venv/bin/python -m pytest tests/test_almanac.py::TestStars::test_hip_number_tags

# Lint — BOTH must stay completely clean
pyflakes3 bin/user/celestial.py tests/test_almanac.py
mypy --ignore-missing-imports bin/user/celestial.py

# After editing the sample skin template, run the end-to-end render tests.
# Template.compile alone is NOT sufficient: with #errorCatcher Echo, Cheetah
# re-compiles each placeholder at render time and rejects constructs plain
# compilation accepts (e.g. `$(x if $cond else '')` loses its else-value and
# dies with SyntaxError only in production).  Guard cells with directive-level
# `#if ...#...#end if#`, never with conditional expressions inside $(...).
/home/weewx/weewx-venv/bin/python -m pytest tests/test_almanac.py::TestSampleSkinRenders

# Install into a WeeWX instance, then restart weewx.  Deploying requires
# root (WeeWX runs as root on these machines).  Claude: you cannot run
# this (sudo needs a password you don't have); print the command and have
# the human run it in their own terminal.
sudo -- bash -c ". /home/weewx/weewx-venv/bin/activate; weectl extension install /path/to/weewx-celestial -y"
```

## Architecture

Everything lives in `bin/user/celestial.py`, in three layers:

- **`Celestial(StdService)`** — reads `[Celestial]` config, binds `NEW_LOOP_PACKET`, and
  calls `register_almanac()` (which declines gracefully before WeeWX 5.2, and dedups by
  class name *and* module — the independent weewx-skyfield-almanac extension uses the same
  class name and must not be removed).
- **`Sky`** — the Skyfield engine shared by both paths: loads the timescale, the ephemeris
  (`celestial_de421.bsp`), and the star catalog; owns the loop-field computation
  (`insert_fields`).  Its `__init__` NEVER raises: every failure logs and leaves
  `valid=False`, and the service then simply does nothing.  `EPHEMERIS_KEYS` is the single
  source of truth for the bodies served (earth stays out of `Sky.orbs`, whose keys drive
  almanac body dispatch).
- **`SkyfieldAlmanacType` / `SkyfieldAlmanacBinder`** — the report almanac.  Attributes the
  binder does not compute fall through to the built-in PyEphem almanac when installed
  (`pyephem_fallback`); by design the only remaining fallbacks are named stars when the
  catalog is disabled and direct PyEphem attributes we do not compute (e.g.
  `moon.subsolar_lat`).

**The cardinal rule: one computation, two consumers.**  Most quantities are needed by both
the loop path and the report path.  Shared helpers exist precisely so the two cannot drift:
`daylight_seconds()` (the polar-safe four-branch daylight algorithm), `find_discrete_events()`
(moon phases, equinoxes/solstices), `Sky.distance_au()`, `direction_value()`.  When adding a
quantity to one path, put the computation where the other path can reach it.

**Correctness policy: accepted definitions over PyEphem compatibility.**  PyEphem is
deprecated and measurably wrong in places (its Jupiter CMLs are ~0.8° off the IAU
definition; it applies refraction to custom horizons where USNO twilight is geometric).
Prefer the USNO/IAU/Meeus answer, document every deviation in the README section
"Differences from PyEphem", and give it a changes.txt bullet.  Return conventions:
`FLOAT_ANGLES` attributes are decimal degrees; PyEphem-shaped attributes (`libration_*`,
`colong`, `cmlI/II`, `earth_tilt`, `separation`, `parallactic_angle`) are radians floats,
matching PyEphem's numeric scale.

**Loop fields** are registered in `OBS_GROUPS` (name → unit group).
`DEPRECATED_FIELD_MAP` dual-emits the pre-3.0 PascalCase names; the old names are removed
in 4.0.  Distances are unit-converted (miles/km) except `earthProximaCentauriDistance`,
which is light years in every unit system (`group_data`, so nothing "converts" it).

**Stars**: `NAMED_STARS` maps tag names to Hipparcos numbers — the IAU Catalog of Star
Names (IAU-CSN, every entry with an HIP number) plus PyEphem's names as legacy aliases.
`celestial_stars.dat` is an excerpt of unmodified `hip_main.dat` records covering exactly
those HIPs; a user-installed full `hip_main.dat` (gitignored) is preferred when present and
enables `$almanac.hip_<number>` tags for any Hipparcos star (loaded lazily, misses cached).
A malformed catalog record must only disable that one star.

**Sample skin** (`skins/Celestial/`): every report-time value is guarded by
`$almanac.hasExtras` (and `#try` where a tag needs WeeWX 5.2) so the page still generates
with empty, javascript-filled cells on configurations without a capable almanac.  The
javascript reads loop-data keys through `lookup()`, which falls back to the pre-3.0 field
names so an un-migrated `[LoopData]` fields list keeps the page updating.  Element ids must
match loop-data keys exactly.

**Installed file naming**: files this extension installs into `bin/user` are prefixed
`celestial_` (`celestial_de421.bsp`, `celestial_stars.dat`) so no other extension can claim
them — and remove them on its uninstall.  Skyfield does not care about the ephemeris
filename.  `hip_main.dat` deliberately keeps its canonical name: it is user-supplied, not
installed.

## Tests

`tests/test_almanac.py` pins TZ to America/Los_Angeles and uses fixed regression values for
Palo Alto on 2025-06-21 (`TIME_TS`).  Key fixtures/helpers: `sky` (session-scoped engine),
`almanac` (registers the Skyfield almanac, restores the global list), `skyfield_only_almanac`
(simulates a system without PyEphem), `saved_almanacs()`, `pyephem_observer()`.  Two
permanent audits matter when adding features: `TestPyEphemParityAudit` (with PyEphem,
everything the built-in almanac could do must still evaluate) and `TestSkyfieldOnlyAudit`
(without PyEphem, every supported tag must evaluate — add new native tags to
`SKYFIELD_ONLY_EXPRESSIONS`).  PyEphem-dependent tests skip via `pytest.importorskip`.

## Releasing

Version lives in two places: `install.py` (`version=`) and `CELESTIAL_VERSION` in
celestial.py.  Every user-visible change gets a bullet in changes.txt under the release
heading — action-required items (renames, config changes) go at the TOP of the entry.
New loop fields must also be added to: the README field list, the README upgrade notes
(the `[LoopData] [[Include]] [[[fields]]]` line users must edit), and the sample skin
(template cell + javascript updater).
