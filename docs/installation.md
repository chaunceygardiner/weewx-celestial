---
title: Installation
layout: default
nav_order: 2
description: Installing weewx-celestial 8.x — the extension, how the page declares the loop-data fields it reads, wiring weewx-loopdata's output to where the page looks, and verifying the live feed.
---

# Installation

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Upgrading from an earlier version instead?  See
[Upgrading](upgrading.md), which covers 8.x, 7.x, 6.x and 5.x-or-earlier
separately.

## Fresh install

1. Install [weewx-loopdata](https://chaunceygardiner.github.io/weewx-loopdata/)
   7.0 or later and
   [weewx-skyfield](https://chaunceygardiner.github.io/weewx-skyfield/)
   2.3.2 or later, both per their instructions, in that order.
   weewx-loopdata **must** come first: this extension's installer refuses
   to run beside an older weewx-loopdata, or none, because the page's
   live values reach it only through 7.0's per-report field declaration
   (below), and an older weewx-loopdata never reads one — the page would
   say `BAD DATA` for ever with nothing in any log to explain it.
   weewx-skyfield's installer configures its default satellites — the ISS
   and Tiangong — and its default comets — Halley and Hale-Bopp — which
   is what this extension's installer declares fields for when it finds
   no `[Skyfield]` sets of your own.

1. Download `weewx-celestial.zip` from the
   [release page](https://github.com/chaunceygardiner/weewx-celestial/releases),
   then:

   ```
   weectl extension install weewx-celestial.zip
   ```

1. There is no fields line to edit.  The page declares the loop-data
   fields it reads to weewx-loopdata itself: the fields that never
   change ship in the skin's own `skin.conf`, and the satellite and
   comet fields — which follow your `[Skyfield] [[Satellites]]` and
   `[[Comets]]` — are written by the install step above, under the
   report's own stanza in `weewx.conf`:

   ```
   Declared 38 satellite fields (iss, tiangong) under [StdReport] [[CelestialReport]] [[[LoopData]]] [[[[fields]]]] satellites.
   Declared 12 comet fields (halley, hale_bopp) under [StdReport] [[CelestialReport]] [[[LoopData]]] [[[[fields]]]] comets.
   ```

   Those two groups are the installer's, rebuilt on every install to
   track your sets (under every report running the Celestial skin, so a
   second one in another language needs nothing by hand); no fields
   line of yours is edited — in particular, an
   old `[LoopData] [[Include]] fields` line from an earlier
   weewx-loopdata is left exactly as it is (the install counts the
   entries on it this page now declares itself, which weewx-loopdata
   evaluates twice per packet until the line is trimmed or retired; see
   [Upgrading](upgrading.md#upgrading-within-8x)).

   The complete set, what each group feeds, and the declaration itself
   are in the [Fields reference](fields-reference.md).  To watch more
   satellites or comets than the installer's defaults, see
   [Adding and removing satellites](satellites-and-comets.md#adding-and-removing-satellites)
   and [comets](satellites-and-comets.md#adding-and-removing-comets) — one command
   makes every edit each one takes, the declaration included.

   A display name belongs in an `[Almanac]` entry where every report sees
   it:

   ```
   [StdReport]
       [[Defaults]]
           [[[Almanac]]]
               hst = Hubble
   ```

   `[Almanac]` display names reach the page on WeeWX 5.3 and later; on
   5.2 the tag name itself is shown.  See
   [Translations](i18n.md#how-it-works).

   (weewx-loopdata 7.0 renders this report's live values with this
   report's own `[Almanac]` names, so a name set in `[[CelestialReport]]`
   reaches the loop feed too; `[[Defaults]]` is simply where every
   report, weewx-skyfield's Sky page included, sees it at once.)

1. Check where the page will look for loop data — in most cases the
   installer has already settled it.  The page fetches `loop_data_file`,
   a URL relative to *this* report's directory, while weewx-loopdata
   writes `[[FileSpec]] loop_data_dir`, a path relative to its *target*
   report's directory.  Two different reports, so the installer works the
   answer out from your own `weewx.conf` and writes it:

   ```
   Set [StdReport] [[CelestialReport]] [[[Extras]]] loop_data_file =
   ../loopdata/loop-data.txt -- where weewx-loopdata writes
   ```

   It never rewrites a setting you already have; if yours disagrees with
   where loopdata writes, it says so and leaves the choice to you.  Two
   cases it cannot settle:

   - **weewx-loopdata isn't installed yet.**  There is nothing to read,
     so the shipped default stands — `../loopdata/loop-data.txt`, which
     is where a stock weewx-loopdata writes.  (You will not normally be
     here: the installer refuses to run without weewx-loopdata 7.0, so
     the only way to reach this case is a `[LoopData]` section removed
     by hand.)  Install loopdata, then either accept that or set the
     option by hand.
   - **The file lands outside your reports tree** — `/dev/shm`, say, or
     a directory of its own.  A filesystem path does not give a URL; only
     your web server's aliases do.  Set `loop_data_file` to the URL that
     serves it — see [Where the loop-data file should
     live](configuration.md#where-the-loop-data-file-should-live), which
     is also the arrangement to want if you run a report sync or a
     Raspberry Pi.

   {: .note }
   The default arrangement is fine and most stations keep it.  If you are
   comfortable editing your web server's configuration, [Where the
   loop-data file should
   live](configuration.md#where-the-loop-data-file-should-live) describes
   a tidier one — the file on a memory filesystem outside the web root,
   which keeps it out of your report sync and off an SD card.

   {: .important }
   This is the step that most often goes wrong, and the page tells you so
   plainly: the badge reads `NO DATA (HTTP 404) — check loop_data_file`.
   The file must be reachable through your **web server**, not merely
   present on disk — loopdata writing to `/dev/shm` with no alias serving
   it is the classic case.

1. Restart WeeWX.  The report appears under `celestial/` of your web root.

   It arrives on the night plate.  For the paper-atlas one, or for a page
   that follows the sun, see
   [Dark, light and auto](configuration.md#dark-light-and-auto).

## Verify it

Give WeeWX one report cycle, then check three things in order — each one
isolates a different half of the wiring.

**Is loopdata publishing the fields?**  The file carries each declaring
report's fields under the report's name, and this page's entry is
`CelestialReport`; the almanac keys should be in it:

```
python3 -c "import json; d=json.load(open('/home/weewx/public_html/loopdata/loop-data.txt'))['CelestialReport']; print(sorted(k for k in d if k.startswith('almanac')))"
```

(Use your own `loop_data_dir` path.)  A `KeyError: 'CelestialReport'`
means loopdata has not read the declaration — restart weewxd (it reads
every report's declaration at startup), and check that the report is
enabled.  Keys for the bodies but none for `iss`/`halley` means the
almanac cannot serve those layers; see
[the almanac tiers](configuration.md#the-almanac-tiers).

**Is the web server serving that file?**  Fetch it the way the page does:

```
curl -sI http://localhost/loopdata/loop-data.txt | head -1
```

(That is the default arrangement's URL.  Use whatever your own
`loop_data_file` resolves to — the installer printed it.)

Anything but `200` is the 404 case above — a path or alias problem, not
an astronomy one.

**Is the page live?**  Open `celestial/` in a browser.  Within a few
seconds the badge beside "updated" should read `LIVE`, and the roster's
distance odometers should be ticking.  Rates and motion trails need two
loop packets, so they appear one refresh cycle after load — a static
first few seconds is by design.

If any of that misbehaves, every symptom the page can show is catalogued
in [Reading the page](reading-the-page.md#the-header-and-the-badge-that-tells-the-truth).
