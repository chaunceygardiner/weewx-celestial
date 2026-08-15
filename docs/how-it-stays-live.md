---
title: How the page stays live
layout: default
nav_order: 5
description: The three clocks behind the Celestial page — the report cycle, the loop packet and the one-second tick — how rates are derived and re-anchored, why a stale feed freezes, and what the browser does and does not compute.
---

# How the page stays live

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

You do not need this page to use the extension.  It is here for the
curious, and for anyone deciding how much to trust a number that is
moving.

## Three clocks

The page is driven by three different clocks, and almost every question
about its behavior is answered by knowing which one owns what.

| Clock | Period | What it does |
|---|---|---|
| **The report cycle** | typically 5 minutes | WeeWX regenerates the page's HTML.  The first paint, the dome backdrops, the Next Visible Pass chart and the page's plate (dark or light) are all settled here. |
| **The loop packet** | seconds (2 with the Vantage driver) | weewx-loopdata writes `loop-data.txt`; the page fetches it every `refresh_rate` seconds and re-anchors every live value to truth. |
| **The one-second tick** | 1 second | The browser advances the readouts between packets, and ticks the countdown chips. |

## First paint, then live

Every value cell is filled twice.  At report time it is rendered from
`$almanac` — the ordinary WeeWX tag — so the page is never blank while it
waits for a packet.  Each of those cells is guarded individually, which is
why a less capable almanac leaves a cell empty instead of failing the
whole page.  Then the first loop packet arrives and the javascript takes
over the same cells by id.

The two agree because they are the same computation: the report tag and
the loop field are both evaluated by the almanac WeeWX has registered.
This extension computes nothing of its own — it has no service at all.

## How motion is derived

The page keeps a ring of the last ten minutes of loop packets.  For each
key, comparing the oldest and newest gives a per-second rate — azimuth
wrap-aware, so a body crossing north does not appear to sprint backwards.
The one-second tick then extrapolates position and distance at that rate,
and every arriving packet re-anchors the value to what the almanac
actually says.

Three consequences worth knowing:

- **Rates and trails need two packets.**  For the first `refresh_rate`
  seconds after a page load the marks stand still and no trails are
  drawn.  That is by design, not a fault.
- **Motion trails are drawn backwards from now** at the current rate,
  covering the last hour in 24 segments.  They are stateless — the page
  does not accumulate a history, it reconstructs one.
- **Extrapolation stops after 120 seconds.**  If the feed dies, the page
  freezes rather than drifting into fiction, and the badge tells you how
  old the data is.  A frozen page is an honest page.

## Why the countdown chips roll themselves

The chips are the cheapest thing on the page: pure client arithmetic
against an event instant — a unix timestamp — that weewx-loopdata
computed once and caches until the event passes.  Nothing recomputes an
equinox every two seconds.

When an event passes, loopdata expires it and publishes the next one, and
the chip follows on its next packet.  That is why a sunset chip counts to
zero and then becomes the next sunrise with no reload, and why a pass
chip rolls to the next pass the moment the current one ends.

Chips also tick with no feed at all: the report bakes each event's target
timestamp into the page, so a page open on a dead feed still counts down
correctly toward the instants it knew about at generation time.

## The two fetched fragments

The dome and the Next Visible Pass chart are drawn by weewx-skyfield at
report time, but the open page keeps them current by refetching small
fragments:

- **Dome backdrops.**  Each report cycle renders a staggered set of them,
  spaced `max(60 s, interval/10)` across the archive interval, and the
  page steps to the one covering the current minute — so the sky advances
  about a quarter of a degree at a time instead of lurching a whole cycle
  at once.  The fragments describe their own timestamp, spacing and
  count, so any archive interval works with no configuration, and if
  report cycles stall the page keeps the freshest backdrop it has.
  Between steps, the sun, moon and planet marks are nudged at
  loop-derived rates.

  Keeping the freshest backdrop is right for a minute or two and wrong
  for an hour, so from 8.3.1 the page watches the backdrop's age.  Once it
  is three report cycles behind — measured against the station's own
  clock, which the loop packets carry, not the viewer's — the dome
  **freezes whole**, marks and satellites with it, and a line under the
  panel says so and names the fault: an HTTP status if the fragment is
  not being served, "not a sky fragment" if what comes back is empty or
  unreadable, "no response" if nothing answers, and — the case no status
  code could reveal — "no newer backdrop is being generated" when the
  fetches succeed but the station has stopped writing new ones.  Nothing
  else on the page is affected: the dial, the roster and the countdown
  chips stand on the loop feed, not on the backdrop.  See
  [The star field is frozen](troubleshooting.md#the-star-field-is-frozen).
- **The pass chart**, refetched every five minutes, which is how a
  completed pass's chart rolls over to the next pass, and how the panel
  reappears when a pass enters the window.

Satellites are the exception to all of this: their markers move at loop
rates, continuously, because they are the one class of thing overhead
that genuinely moves fast.

Both fragments arrive as SVG with their colors already inside them, which
is why the page's plate — dark or light — is settled when the report is
generated rather than in the browser (see
[Dark, light and auto](configuration.md#dark-light-and-auto)).  Each
fragment is rendered on the palette the page around it was rendered with,
resolved from the report's own generation instant, so a refetch can never
land a night dome in a light page.

On `theme = auto` a report cycle eventually crosses sunrise, and an open
page cannot restyle itself — its plate was baked in when it was
generated.  So each backdrop declares which plate it was drawn on, and a
page that finds itself wearing the other one reloads — once per flip, and
never again if it comes back still disagreeing, which would mean a cached
copy rather than a flip.  The change reaches a page left open overnight
within a minute of the report cycle that makes it, rather than waiting
for someone to press reload.

## What the browser does not do

No astronomy, and no theme switching.  The javascript does arithmetic —
differences, rates, linear extrapolation, countdown subtraction — and
draws.  Every astronomical quantity on the page was computed by the
almanac in weewxd, and the page does not follow your operating system's
dark-mode setting: it wears the plate its report was generated with.
That is a deliberate division: it keeps the page cheap on a phone, and it
guarantees that what ticks in the browser cannot disagree with what the
report says.

## What it costs

One `loop-data.txt` fetch per `refresh_rate` seconds (a small json file),
one dome fragment per minute, one pass-chart fragment per five minutes.
The one-second tick is arithmetic on values already in memory.  Nothing
on the page polls weewxd, and nothing recomputes an ephemeris.

To keep an unattended page from polling forever, it stops after
`expiration_time` hours and shows `CLICK-ME`; a click resumes it.  See
[Configuration](configuration.md).
