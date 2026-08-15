---
title: Installation
layout: default
nav_order: 2
description: Installing weewx-celestial 8.x — the extension, the loop-data fields it reads, wiring weewx-loopdata's output to where the page looks, and verifying the live feed.
---

# Installation

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Upgrading from an earlier version instead?  See
[Upgrading](upgrading.md), which covers 8.x, 7.x, 6.x and 5.x-or-earlier
separately.

## Fresh install

1. Install [weewx-loopdata](https://chaunceygardiner.github.io/weewx-loopdata/)
   6.9 or later and
   [weewx-skyfield](https://chaunceygardiner.github.io/weewx-skyfield/)
   2.1 or later, both per their instructions.  (weewx-skyfield's installer
   configures its default satellites — the ISS and Tiangong — and its
   default comets — Halley and Hale-Bopp — which is what the fields line
   below assumes.)

1. Download `weewx-celestial.zip` from the
   [release page](https://github.com/chaunceygardiner/weewx-celestial/releases),
   then:

   ```
   weectl extension install weewx-celestial.zip
   ```

1. Check the `fields` line of `[LoopData] [[Include]]` in `weewx.conf`.
   The install step above appended the entries the report reads, printing
   each one — append-only, so existing entries are never renamed, removed
   or reordered.  The line must stay a **bare comma-separated list** (no
   brackets, no quotes).

   The complete set, what each group feeds, and the line itself for hand
   editing are in the [Fields reference](fields-reference.md).  To watch
   more satellites or comets than the installer's defaults, see
   [Adding and removing satellites](satellites-and-comets.md#adding-and-removing-satellites)
   and [comets](satellites-and-comets.md#adding-and-removing-comets) — one command
   makes every edit each one takes.

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
   your loopdata already writes.

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

**Is loopdata publishing the fields?**  The almanac keys should be in the
file itself:

```
python3 -c "import json; d=json.load(open('/home/weewx/gauge-data/loop-data.txt')); print(sorted(k for k in d if k.startswith('almanac')))"
```

(Use your own `loop_data_dir` path.)  An empty list means the fields line
never reached loopdata — restart weewxd so it reloads the line.  Keys for
the bodies but none for `iss`/`halley` means the almanac cannot serve
those layers; see [the almanac tiers](configuration.md#the-almanac-tiers).

**Is the web server serving that file?**  Fetch it the way the page does:

```
curl -sI http://localhost/loop-data.txt | head -1
```

Anything but `200` is the 404 case above — a path or alias problem, not
an astronomy one.

**Is the page live?**  Open `celestial/` in a browser.  Within a few
seconds the badge beside "updated" should read `LIVE`, and the roster's
distance odometers should be ticking.  Rates and motion trails need two
loop packets, so they appear one refresh cycle after load — a static
first few seconds is by design.

If any of that misbehaves, every symptom the page can show is catalogued
in [Reading the page](reading-the-page.md#the-header-and-the-badge-that-tells-the-truth).
