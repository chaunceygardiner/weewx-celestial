---
title: In your own skin
layout: default
nav_order: 11
description: Building your own live celestial page on weewx-loopdata almanac fields — the Geocentric, the countdown chips and the roster patterns, with the bundled skin as the reference implementation, and why the dome and pass panels are not a copyable interface.
---

# In your own skin

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Everything the sample skin does is ordinary weewx-loopdata consumption:
list the almanac fields you want in `[LoopData] [[Include]] fields`, give
your HTML elements ids equal to the json keys, and poll `loop-data.txt`
from javascript.  `skins/Celestial/realtime_updater.inc` is the reference
implementation — the dial, the rate derivation, the countdown chips and
the odometer are self-contained functions you can lift — and
`skins/Celestial/celestial.css` holds every color.

{: .important }
What is safe to copy depends on what the copied code depends on.  The
Geocentric, the countdown chips and the roster patterns ride the
**public loopdata field grammar**: copy them and they keep working.  The
sky dome and the Next Visible Pass panel do not — see
[the boundary](#the-dome-and-the-pass-panel-are-not-an-interface) at the
end of this page.

## The parts worth lifting

### The Geocentric

A dial is nothing more than azimuth and distance drawn as polar
coordinates.  The version here places every body by compass bearing, with
`log10(earth_distance in au)` as the radius — one ring per decade — which
is what lets one picture hold both the moon and Proxima Centauri.  The
inputs are three fields per body (`az`, `alt`, `earth_distance`) and
nothing else; below-horizon styling is `alt < 0`.

### The countdown chips

The most liftable thing on the page, and the cheapest.  Each chip is
client-side arithmetic against one **event-tier field** — a unix
timestamp that weewx-loopdata computes once and caches until the event
passes.  Nothing recomputes an equinox on a two-second cadence.

Three details make them behave well, and all three are worth copying:

- **Let loopdata roll the event.**  When the instant passes, loopdata
  expires it and publishes the next one, so a sunset chip becomes the
  next sunrise with no page logic and no reload.  A chip that pairs two
  fields (sunset/sunrise, darkness begins/ends) is just a client-side
  `min()` of the two.
- **Bake a fallback target into the page.**  Render each event's
  timestamp into a `data-ts` attribute at generation time.  A page whose
  feed never arrives still counts down correctly toward what the report
  knew; the feed re-anchors it when it does arrive.
- **Let precision follow the horizon.**  Days-hours-minutes with a date
  beside it while the event is far off, a ticking `hh:mm:ss` inside the
  final day.  A seconds-resolution countdown to something eight days away
  is noise, and a date-only line is useless in the last hour.

### Rates from consecutive packets

Two loop packets give every numeric field a per-second rate (azimuth
wrap-aware); the page then advances its readouts every second between
refreshes and re-anchors to truth on each packet.  Extrapolation stops
after a stale-feed cutoff, so a dead feed freezes rather than drifting
into fiction.  Motion trails are drawn *backwards* from now at the
current rate — stateless, so nothing accumulates and a reload costs
nothing.

### Dual-source cells

Every value cell first-paints at report time from `$almanac` — each cell
individually guarded, so a less capable almanac leaves cells empty rather
than failing the page — and then goes live from loop data.  The page is
never blank while it waits for its first packet, and it never dies
because one tag is unavailable.

### A truthful badge

The badge reports the feed's actual state: packet age, `OFFLINE` on
network failure, and `NO DATA (HTTP 404) — check loop_data_file` when the
web server is not serving the loop-data file where the page expects it.
A live page that silently shows stale numbers is worse than one that
admits it.

### Absent versus null

weewx-loopdata omits null-valued keys from `loop-data.txt`, which gives
you two distinguishable states for free: a field **not on the fields
line** (the report-time first paint stands) versus one **present but
empty** (no pass to report, no elements, no comet).  The satellite rows,
the comet rows and the countdown chips all lean on this, and any page
that renders optional facts wants the same distinction.

### Tap tooltips

Native SVG `<title>` tooltips are hover-only — on a touch screen they are
simply dead.  `sky.js` (copied verbatim from weewx-skyfield) fixes that
with one document-level click listener: a tap on or near a mark shows the
same text as a floating chip, and because the listener binds to nothing
inside the SVG, marks swapped in by a fragment refetch need no
rebinding.  Marks your own javascript draws join for free: give the
mark's group a `<title>` child and keep its text current.  On a live
page, dismiss an open chip whenever a swap moves the sky under it — a
chip should be a transient answer, never a stale overlay.

## Two traps that cost real time

{: .important }
**Top-level `var` names in an include collide with `window`.**  A skin
include's script runs at global scope, so `var history`, `var name`,
`var location`, `var top`, `var status`, `var event` and friends do not
bind — the assignment silently fails against a read-only window property,
and the failure surfaces far away, as a throw inside your poll handler
that kills the whole page.  Prefix or rename anything that shadows a
window built-in.

**Cheetah owns `$` and `#`.**  In `.tmpl`/`.inc` files a bare `#` starts
a directive and `$` starts a placeholder, so no CSS hex literals and no
javascript template literals can appear in them.  With `#errorCatcher
Echo`, Cheetah also re-compiles each placeholder at render time and
rejects constructs that plain compilation accepts — guard cells with
directive-level `#if` blocks rather than conditional expressions inside
`$(...)`.

## The dome and the pass panel are not an interface

The sky dome and the Next Visible Pass chart are drawn by weewx-skyfield
and embedded here through a private, in-step integration: a guarded
search list, fragment files with their own wrapper protocol, and
per-mark hooks that this skin's javascript nudges.  Those internals
change between weewx-skyfield releases, deliberately and without notice,
because the two extensions are released together and tested against each
other.

There is therefore **no supported way to copy them into another skin**.
Code that copied them would break at the next weewx-skyfield release,
and the breakage would look like a bug in someone else's extension.

What is supported:

- **Run the bundled page as it is.**  It stands alone: link to it, or
  point its `HTML_ROOT` wherever you like in your site.
- **Use weewx-skyfield's own documented tags** for a report-time dome or
  sky chart in your own skin — see
  [its manual](https://chaunceygardiner.github.io/weewx-skyfield/).  That
  is a public interface, and it is the one to build on.

## Further reading

The full almanac-field grammar is documented in
[weewx-loopdata's manual](https://chaunceygardiner.github.io/weewx-loopdata/almanac-fields.html);
loopdata's own
[Build a live page](https://chaunceygardiner.github.io/weewx-loopdata/build-a-live-page.html)
covers the general pattern, and this manual's
[Fields reference](fields-reference.md) lists exactly what the Celestial
page reads.

## Live in the wild

[PaloAltoWeather.com's Celestial Today page](https://www.paloaltoweather.com/celestial.html)
carries a Geocentric Live panel built with the same technologies used
here ([weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield)
and [weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata)),
alongside pages of its own that read fields this skin does not.
