---
title: Configuration
layout: default
nav_order: 6
description: The CelestialReport options in weewx.conf — loop_data_file, refresh_rate, expiration_time, time_zone, theme — the dark and light plates, the sky dome and Next Visible Pass panels, the satellite and comet sets, the countdown row, how the page degrades across almanac tiers, and the two settings that embed the panels in another skin.
---

# Configuration

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Installing registers the report; its options live in `weewx.conf`.  This
is what a **fresh** install writes — see [what an existing station
sees](#upgrading-an-existing-station) below, which is different:

```
[StdReport]
    [[CelestialReport]]
        #lang = en
        #theme = dark
        HTML_ROOT = celestial
        enable = true
        skin = Celestial
        [[[LoopData]]]
            [[[[fields]]]]
                satellites = almanac.iss.az, almanac.iss.alt, ...
                comets = almanac.halley.az, almanac.halley.alt, ...
        [[[Extras]]]
            loop_data_file = ../loopdata/loop-data.txt
            #refresh_rate = 2
            #expiration_time = 24
            #time_zone = America/New_York
            page_update_pwd = foobar
```

An option that merely selects a default is written **commented out**, with
the default shown.  Nothing is lost: with the line commented, the value
in force is the one in `skins/Celestial/skin.conf`, which every upgrade
replaces — so if a later release picks a better default, your station
follows it.  Uncomment one to pin your station to a value of your own.
`loop_data_file` and `page_update_pwd` are live because neither is a
default: the first is derived for your station at install, the second is a
placeholder you are meant to replace.

- `loop_data_file`: where the javascript fetches loop data; relative paths
  are relative to this report's HTML_ROOT.  You should not have to set
  this: the installer reads your `[LoopData]` settings, works out where
  weewx-loopdata actually writes, and puts that here — the value above is
  what a stock weewx-loopdata gives you, its own report's directory.  An
  existing setting is never rewritten, only flagged when it disagrees.
  The file must be reachable through your **web server** — if
  weewx-loopdata writes outside the web root (say `/dev/shm`) with no
  alias serving it, the installer cannot know the URL that reaches it and
  says so, and the page's badge will tell you the same:
  `NO DATA (HTTP 404) — check loop_data_file`.
- `refresh_rate`: seconds between loop-data polls (match weewx-loopdata's
  write cadence: 2 for the Vantage driver).  Ships commented out.  The countdown chips and the
  satellite rosters advance with each packet a poll brings, since the
  page's clock is the packet's own.
- `expiration_time`: hours the page keeps polling before requiring a click.
  Ships commented out.
  An unattended browser therefore stops polling overnight instead of for
  ever; the badge reads `CLICK-ME` and a click resumes it.  `0` means
  never expire, which is for a page in another skin that runs an expiry
  of its own — see
  [Panels in your own skin](own-skin.md#two-ids-where-your-live-layer-and-this-one-meet).
- `page_update_pwd`: appending `?pageUpdate=<page_update_pwd>` to the URL
  disables expiration for that view.  The password is visible to anyone
  reading the page source, so treat it as a convenience, not a secret.
- `time_zone`: the timezone of displayed times.  By default the
  *station's* zone is auto-detected at report time, so remote viewers see
  station time.  Set an IANA name (`America/New_York`) to force a zone,
  or `browser` for the viewer's local zone.  It ships commented out
  above — and unlike the others, the line there is an **example, not a
  default**: this option's default is having no value at all, which is
  what makes the zone auto-detect.  Uncomment and edit it to override.
- `lang`: the page's language — see [Translations](i18n.md).
- `theme`: the page's plate — `dark` (the default), `light`, or `auto`.
  See [Dark, light and auto](#dark-light-and-auto) below.
- `title` / `meta_title` (Extras): override the page heading and the HTML
  `<title>`.
- `[[[LoopData]]] [[[[fields]]]]`: the satellite and comet fields the
  page reads, declared to weewx-loopdata — written by the installer for
  your `[Skyfield]` sets, rebuilt on every install, not for editing.  See
  [the declared fields](#the-declared-fields) below.

## Upgrading an existing station

Nothing you have set is rewritten: WeeWX fills in only what is absent from
`weewx.conf`.  So your stanza will not come to look like the one above —
a station installed before this release keeps `refresh_rate` and
`expiration_time` live and has no `lang`, `theme` or `time_zone` lines,
which is fine; copy from above if you want them.

## Where the loop-data file should live

Where the file lands is weewx-loopdata's decision — its `loop_data_dir`,
relative to its sample report — and this page simply follows: whatever
`loop_data_file` you set has to be the URL that reaches it.  The
installer works that out for you whenever both sit inside your reports
tree, which is the arrangement weewx-loopdata ships with and where most
stations leave it.

If you are comfortable editing your web server's configuration, there is
a tidier place for the file — a memory filesystem outside the web root,
which keeps it out of your report sync and off an SD card.  That is
weewx-loopdata's ground, and its manual has the recipe: [Where the
loop-data file should
live](https://chaunceygardiner.github.io/weewx-loopdata/configuration.html#where-the-loop-data-file-should-live).

Two things to know on this side if you take it.  `loop_data_file` becomes
an absolute URL — the one your alias serves — because the file no longer
shares a tree with the page:

```
[StdReport]
    [[CelestialReport]]
        [[[Extras]]]
            loop_data_file = /loop-data/loop-data.txt
```

And the installer cannot work that one out: a path on disk does not say
what URL reaches it, and only your web server knows about the alias.  It
reports what it found and leaves your setting alone.

## Report timing is not supported

**Do not set `report_timing` on this report.**  This page is live: its
dome backdrops are written by the report cycle and stepped through by the
open page as its station's clock advances, and the whole design assumes
those two run at the same rate.  A report throttled to run less often than the archive interval
leaves the page holding a sky older than it is willing to draw marks
over, so the dome freezes and says so — permanently, and correctly: from
the browser, a deliberately slow report and a station that has stopped
writing backdrops look exactly alike.

If report generation is costing more than you want to spend — this skin
renders a dome backdrop for each slot that fits inside the archive
interval, five of them at WeeWX's default five minutes and up to ten on a
longer one, which is the expensive part — lengthen the **archive
interval** instead.  The page follows that on its
own: the fragment set is spaced across it, and the staleness limit is
derived from it.

## Dark, light and auto

The page ships as the night plate it has always been.  `theme` switches
it.  Add it to the `[[CelestialReport]]` stanza above, beside
`skin = Celestial` — at the report level, *not* inside `[[[Extras]]]`,
exactly where `lang` goes:

    theme = light

- **`dark`** — the night page.  The default; upgrading changes nothing.
- **`light`** — the paper-atlas page.
- **`auto`** — light while the sun is up at generation time, dark otherwise.
  The report regenerates each archive cycle, so the flip follows
  sunrise and sunset to within one interval.

![The Celestial page on the light plate](https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/CelestialSampleReport-light.png)

**The whole page follows it.**  The sky dome and the Next Visible Pass
chart are weewx-skyfield's drawings, and on a light page they are
rendered on that extension's matching paper palette — never left as a
night rectangle inside a light page.  The page above is the same page as
the [dark one on the home page](index.md), one option apart.  Everything
the page draws itself (the Geocentric dial, the roster, the countdown
chips) is on the same paper, with the three pale bodies — the sun, the
moon and Venus — taking a darker edge in their own color so they still
read against it.

The option is spelled and valued exactly as weewx-skyfield's own Sky page
spells it, so the two pages configure alike; weewx-skyfield reads it
straight out of this report's configuration.  Without that extension the
page has no charts to match and stays dark.

**It is resolved when the report is generated, not in the browser.**  The
dome and the pass chart arrive as SVG with their colors already inside
them, and the page refetches them as it runs — so there is nothing for a
browser-side toggle to switch, and the page does not follow your
operating system's dark-mode setting.  A theme change takes effect on the
next report cycle.

## The sky dome, the satellites and the Next Visible Pass panel

The dome and the Next Visible Pass chart are drawn by weewx-skyfield (2.0 or
later) and embedded through a guarded search list, so a lesser almanac
costs panels, never the page.  There is nothing to configure in this
skin for them; what they show follows weewx-skyfield's own
configuration:

- **The satellite set** is `[Skyfield] [[Satellites]]` in `weewx.conf`
  (weewx-skyfield's installer defaults to the ISS and Tiangong).  The
  skin enumerates whatever is configured; each satellite needs its
  nineteen declared fields (see
  [Fields reference](fields-reference.md#satellites-19-entries-each)) to go live,
  which the installer writes for the set it finds, and a display name is
  best set under `[StdReport] [[Defaults]] [[[Almanac]]]` so every
  report calls it the same thing.  The bundled
  [`--add-satellite` utility](satellites-and-comets.md#adding-and-removing-satellites) makes
  all three edits in one command.
- **The backdrop steps once a minute.**  Each report cycle renders a
  staggered set of dome backdrops (`dome-svg.txt`,
  `dome-svg-1..9.txt`), spaced `max(60 s, interval/10)` across the
  archive interval, and the open page fetches the one covering the
  current minute — and only when that is not the backdrop it already
  has, so a page in step with its station fetches nothing.  The
  fragments describe their own spacing, so any
  archive interval works unconfigured; if report cycles stall, the page
  keeps the freshest backdrop it has — and once it is three cycles
  behind, freezes the dome and says so rather than flying live marks
  over a motionless star field (see
  [The star field is frozen](troubleshooting.md#the-star-field-is-frozen)).
  The Next Visible Pass chart refetches
  every five minutes and rolls over to the next pass by itself.
- **The satellite marker is honest about visibility**: drawn whenever
  the satellite is up, full brightness only when you could actually see
  it (sunlit satellite against a dark sky), dimmed otherwise.
- **The comet set** (8.1, weewx-skyfield 2.1) is `[Skyfield]
  [[Comets]]` (installer defaults: Halley and Hale-Bopp).  Each
  configured comet gets a diamond on the Geocentric dial — placed like
  a planet, its tail fanning anti-sunward, solid when naked-eye bright
  — a roster row, and a windowed perihelion countdown chip; each needs
  its six declared fields to go live, which the installer writes for
  the set it finds.  The bundled
  [`--add-comet` utility](satellites-and-comets.md#adding-and-removing-comets) makes the three
  edits in one command.  The dome and the pass chart draw their own
  comet diamonds and meteor shower radiants inside weewx-skyfield's
  fragments — nothing to configure here.

## The countdown row

The chip row at the top of the page has no options of its own: the
always-on chips (the soonest visible pass, sunset/sunrise, the meteor
shower peak, and astronomical darkness — begins at the −18° sunset,
ends at the −18° sunrise, whichever is next) follow the declaration,
and the windowed guests (the next equinox or solstice — named by the
season it begins — Earth's perihelion or aphelion, the next supermoon,
the next eclipse visible from
the station, each configured comet's perihelion) appear only within
~30 days of their event — close enough for a countdown to mean
something.  A day or more out a countdown reads days-hours-minutes
with the event's date beside it; inside the final day it becomes an
`hh:mm:ss` clock, counting on every loop packet.  Every chip is client-side arithmetic on an
event instant
weewx-loopdata computes once and caches until it passes; a chip whose
field the almanac cannot serve simply stays hidden.  (weewx-skyfield's
own Sky page shows a perihelion as a dated chip up to a year out; the
30-day window here is deliberate.)

## Adding and removing satellites and comets

Each satellite or comet takes three separate `weewx.conf` edits — its
`[Skyfield]` entry, its declared fields, and its display name — and
the extension bundles `--add-satellite`/`--add-comet` to make all three
in one command (with `--remove-satellite`/`--remove-comet` as exact
inverses).  That is its own page:
[Satellites and comets](satellites-and-comets.md).

## The almanac tiers

The rosters first-paint at report time from `$almanac` and then go live
from loop data.  What renders depends on the almanac WeeWX has:

| Almanac | The page |
|---|---|
| **weewx-skyfield 2.3.4** (satellites and comets configured) | Everything — Proxima Centauri, the sky dome, the satellite layer, the Next Visible Pass chart, the comet diamonds and the full countdown row; the footer carries the full Skyfield/DE421/Hipparcos credit |
| **weewx-skyfield 2.3.2** or 2.3.3 | The same page.  2.3.4 adds one thing this skin uses: a way to ask whether the sky can be drawn at all without drawing it, so the panels beside the dome — the two rosters and the Next Visible Pass — settle their state without a dome render.  On an older weewx-skyfield the page asks the way it always has, by drawing the dome |
| **weewx-skyfield 2.1** | Everything but the pass chart's dot leaving the chart when the pass ends — the chart states its own rise and set only from 2.3.2, so the page falls back to the loop feed's window and the dot returns to its drawn place at set |
| **weewx-skyfield 2.0** | Everything but the comets and the shower/supermoon chips (the sunset, darkness and pass chips still count) |
| **weewx-skyfield** (earlier) | Everything but the satellites and their chart; the dome's sun/moon/planet marks step only at the backdrop step (the live-nudge hooks are 2.0's) |
| **PyEphem** | The Geocentric minus the Proxima Centauri row (PyEphem's star catalog lacks it), the sunset and darkness chips; no dome or chart — the dome panel shows an install hint |
| **built-in** | The page generates, but the panels show install hints — the built-in almanac serves none of the positions or distances the Celestial page runs on |

2.2 adds nothing to that top row — no new fields, no new marks — but the
dome and the Next Visible Pass chart carry their colors inside the SVG
this skin embeds, so upgrading to it is what makes their altitude rings and
meridian cross visible.  It is also where the dome's Mars comes up to meet
the dial's: celestial 8.2 lifts its own Mars dot, and until 2.2 is
installed the embedded dome still draws the darker one.  The half of that
pass which lives in this skin's own stylesheet (the star and constellation
names) ships in celestial 8.2 and applies at any weewx-skyfield version.

The plate follows the same shape.  `theme` is read by weewx-skyfield, and
the light plate is the paper its charts are drawn on, so **1.15 or later**
is what makes the option do anything: below that — and on the PyEphem and
built-in tiers, where there are no charts at all — the page stays dark
whatever the option says, quietly, since there is no way to tell an old
installation from one that never asked.

The footer credit is generated truthfully for whichever almanac actually
serves the page.

## The declared fields

The page declares the loop-data fields it reads to weewx-loopdata (7.0
or later), which evaluates them on every loop packet and writes them
into `loop-data.txt` under the report's name — `CelestialReport` — in
this report's own units, formats and `[Almanac]` names.  The declaration
is in two places, and neither wants editing:

- the fields that never change, in the skin's own `skin.conf`
  (`[LoopData] [[fields]]`), and
- the satellite and comet fields, which follow your `[Skyfield]` sets, in
  the `satellites` and `comets` groups of the report's stanza above —
  written by the installer and by `--add-satellite`/`--add-comet`, and
  rebuilt whenever either runs.

A field of your own — for a page of your own reading this report's entry,
say — goes in a **group of your own** in that stanza; weewx-loopdata
merges the groups by name, so the skin's and the installer's are left
alone.  The stanza is the report's, though: `weectl extension uninstall
celestial` removes it whole, your groups with it, exactly as it removes
`[[[Extras]]]` — so keep a copy of any group of your own if you uninstall
(the 6.x upgrade path does).  It removes only `[[CelestialReport]]`: a
second report of your own running the Celestial skin keeps its
`satellites` and `comets` groups after an uninstall, and weewx-loopdata
goes on evaluating those fields every loop packet for a page that is no
longer there — delete that report's `[[[LoopData]]]` section by hand.
(A report of *another* skin embedding the panels is different: uninstall
that skin and its groups are taken away by the next install or utility
run, because the skin's `skin.conf` — where its `celestial_panels` lives
— has gone with it.  See
[Panels in another skin](#panels-in-another-skin) below.)  The older `[LoopData] [[Include]] fields` line is not this page's
business: since 8.5 the installer never writes it — it only reads it to
count the entries this page now declares itself, which weewx-loopdata
evaluates twice per packet while the line stands — and weewx-loopdata
retires it in a later release.  If your own pages still read it (as, for example,
[PaloAltoWeather.com](https://www.paloaltoweather.com/celestial.html)'s
do), that is between them and weewx-loopdata's
[Declaring fields](https://chaunceygardiner.github.io/weewx-loopdata/declaring-fields.html)
page.

Every entry the skin reads, grouped by what it feeds, plus both halves of
the declaration as shipped, is in the
[Fields reference](fields-reference.md).

## Panels in another skin

Since 9.0 the page's panels can be embedded in a skin of your own — the
countdown row, the Geocentric, the sky dome and the Next Visible Pass
chart, live layer and all.  The whole recipe is
[Panels in your own skin](own-skin.md); two pieces of it are
configuration and belong here.

**`celestial_panels`** names the panels a page embeds — any of
`countdown`, `geocentric`, `dome` and `pass` — and **belongs in the
consuming skin's own `skin.conf`**, at the top level:

```
celestial_panels = dome, pass
```

That is where a well-behaved skin puts it: which panels a page embeds is
a property of its templates, the same on every station, so declaring it
with the skin means installing that skin needs no edit to `weewx.conf`
on any machine.  Every report running that skin inherits it, which is
what a second report — a metric twin, say — wants.

A report's own stanza still overrides it, in the order WeeWX merges in,
for a station that needs one report to differ:

```
[StdReport]
    [[MyReport]]
        HTML_ROOT = public_html/mysite
        skin = MySkin
        celestial_panels = dome
```

Set in both places, the run logs which file answered, and warns when the
two disagree — the stanza wins, and a stale one is easy to forget.

`weectl extension install` and the `--add-satellite`/`--add-comet`
utilities then maintain that report's `satellites` and `comets` groups
exactly as they maintain the Celestial report's, and give it only the
groups its named panels read: satellites for the dome and the Next
Visible Pass, comets for the Geocentric, both for the countdown row.  Do
re-run the installer after adding the key, and restart weewxd so
weewx-loopdata reads the declaration.

Three things about it are worth knowing before you write it.  On any
report carrying the key, the two group names are this extension's, so a
declared field of your own belongs under a name of your own.  The key
belongs on a report and nowhere else: under `[[Defaults]]`, or at
`[StdReport]`'s top level, WeeWX would merge it into every report, so
both are refused — named once, as the station's own misconfiguration, in
the installer's output and on the page of any other skin's report that
carries no key of its own.  And a name that is not a panel
costs that report its declaration and nobody else's, every run.  A page
whose panels are not declared, or whose declaration is out of date, says
so where the panel renders and in the weewxd log.

**`[CelestialFragments]`** goes in the consumer *skin*'s `skin.conf`, and
declares the dome backdrop sets the report writes — one subsection per
set.  It is needed only for the sky dome and the Next Visible Pass chart,
and only when the default single set is not what the skin wants: two
label scales for two screen sizes, a night dome inside a light site, or
the files kept in a subdirectory:

```
[CelestialFragments]
    [[astro]]
        directory = astro
    [[smartphone]]
        prefix = dome-svg-sp
        label_scale = 2.2
        directory = astro
```

| Key | What it does |
|---|---|
| `prefix` | The set's file names: `<prefix>.txt`, `<prefix>-1..9.txt`, `<prefix>-pass.txt`.  Default `dome-svg`, whose pass fragment keeps the name `pass-chart.txt`.  One set per prefix, whatever their directories; two sets that would *write* the same file are refused separately, judged by what `kind` says each writes |
| `label_scale` | The chart labels' scale, passed to weewx-skyfield; default 1.0 |
| `theme` | `dark`, `light` or `auto`, spelled exactly as the report option is; default the report's own |
| `directory` | Where under the report's `HTML_ROOT` the set is written; default `HTML_ROOT` itself.  A plain relative path — nothing that could leave `HTML_ROOT` |
| `kind` | Which fragments the set is for — `dome`, `pass` or `both` (the default).  A skin showing the dome on one page and the chart on another, at different label scales, declares a set for each; without this each would write the other's files every cycle for a page that never fetches them |

The page names the set it embeds in the call
(`$celestial.dome_html($almanac, set='astro')`), so scale, plate, file
names and directory all follow from the one declaration.  The bundled
Celestial skin declares no section at all: one set, `dome-svg`, at scale
1.0 on the report's own plate, in `HTML_ROOT`.
