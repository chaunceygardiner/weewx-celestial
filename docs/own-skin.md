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
declare the almanac fields you want in your skin's `skin.conf`
(`[LoopData] [[fields]]`, weewx-loopdata 7.0 — see its
[Declaring fields](https://chaunceygardiner.github.io/weewx-loopdata/declaring-fields.html)),
give your HTML elements ids equal to the json keys, and poll
`loop-data.txt` from javascript, reading your report's own entry
(`(await response.json())[$json.dumps($REPORT_NAME)]`, with
`#import json` at the top of the template — `$REPORT_NAME` is a core
WeeWX tag, `$json` is not).
`skins/Celestial/realtime_updater.inc` is the reference
implementation — the dial, the rate derivation, the countdown chips and
the odometer are self-contained functions you can lift — and
`skins/Celestial/celestial.css` holds every color — both plates' worth
since 8.3, as a token set on `:root` and the overrides that a
`theme-light` class on the root element switches in.

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
  timestamp into a `data-ts` attribute at generation time.  A chip whose
  event the feed does not carry still counts down toward what the report
  knew, on the packets that do arrive; the feed re-anchors it when the
  event does arrive.  (Count on the packet's own timestamp, not the
  browser's clock — see
  [Whose time it is](how-it-stays-live.md#whose-time-it-is).)
- **Let precision follow the horizon.**  Days-hours-minutes with a date
  beside it while the event is far off, an `hh:mm:ss` clock inside the
  final day.  A seconds-resolution countdown to something eight days away
  is noise, and a date-only line is useless in the last hour.

### One clock, and it is the packet's

The loop packet's own timestamp is the page's time — the instant every
value in the packet was computed for — and before the first packet, the
instant the page was generated for, baked into the script.  Nothing that
reads that clock is on a timer: chips, rosters and verdicts render as
packets arrive, because between two packets there is nothing new to
paint.  The browser's clock is a stopwatch, never a calendar: it is
asked how long since the last packet (for the motion below) and how long
since the last fetch, and never what time it is.  A viewer whose clock
is wrong sees exactly what a viewer whose clock is right sees, and a
dead feed reads dead everywhere at once, with the badge naming it.  See
[Whose time it is](how-it-stays-live.md#whose-time-it-is).

### Rates from consecutive packets

Two loop packets give every numeric field a per-second rate (azimuth
wrap-aware); the page then advances the moving readouts — positions,
distances, the odometers — every second between refreshes and re-anchors
to truth on each packet.  Nothing that reads the clock (the chips, the
roster's "in {n} days") is on that timer; those render on the packet,
because the page's time is the packet's.  Extrapolation stops
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
network failure, `NO DATA (HTTP 404) — check loop_data_file` when the
web server is not serving the loop-data file where the page expects it,
and `BAD DATA — check loop_data_file` when what came back is not a
loop-data file at all, carries no entry for this report (an older
weewx-loopdata, or a report that declares nothing), or carries no
`current.dateTime.raw`.
A live page that silently shows stale numbers is worse than one that
admits it.

### Absent versus null

weewx-loopdata omits null-valued keys from `loop-data.txt`, which gives
you two distinguishable states for free: a field **not declared** (the
report-time first paint stands) versus one **present but empty** (no
pass to report, no elements, no comet).  The satellite rows,
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

## Five traps that cost real time

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

**`$almanac.texts` succeeds on WeeWX 5.2 and then kills the page.**  The
report's `[Almanac]` display names reach the almanac only from WeeWX 5.3
on.  You might expect 5.2 to raise a clean `AttributeError` you could
default around — it does not.  `Almanac.__getattr__` walks the registered
almanacs, and PyEphem's catch-all treats any unknown name as a heavenly
body, so it hands back a binder for a "body" called `texts`: the lookup
*succeeds*, returns something truthy, and dies one step later on `.get`,
during report generation, so the page never appears at all.  A
`getattr(almanac, 'texts', {})` default can therefore never fire.  Read
`$almanac.__dict__.get('texts', {})` instead — the only lookup that tells
the truth — and fall back to the capitalized tag name.  The same shape
lurks wherever an optional almanac attribute is probed: on the PyEphem
tier, test the *value*, never the success of the attribute access.

**A baked-in palette cannot have a browser toggle.**  If your page
embeds SVG whose colors are written into the markup — as this one does,
and as anything drawn server-side does — then a light/dark switch in the
browser can restyle your own chrome and nothing else, and any class you
add to the embedded markup is undone the moment the page refetches it.
The theme has to be resolved where the drawing happens: at generation
time, into a class on the root element, with every fragment template
rendered on the same palette as the page.  Miss one fragment and the
symptom is the worst kind — a panel that flips plate a minute after load,
on a timer, whenever that slot comes round.  (Resolve the palette from
the page's own instant, too: on a sun-following theme, a fragment
depicting a moment a few minutes later can otherwise disagree with the
page it lands in.)

**`Date.now()` as a calendar costs a release every time.**  It is the
obvious way to count a chip down or judge a pass over, and it is wrong
in three ways this skin paid for one release each: a viewer's skew reads
straight into every countdown (8.3.3 grew a freshness test and a latch
to police it); carrying the station's clock forward on the browser's
stopwatch matches no data on the page and steps back whenever a packet
arrives late (8.3.4); and either one leaves a dead feed looking half
alive.  Read the packet's stamp, and subtract `Date.now()` only from
another `Date.now()`.

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
