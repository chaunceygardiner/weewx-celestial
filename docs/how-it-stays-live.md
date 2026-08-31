---
title: How the page stays live
layout: default
nav_order: 5
description: The three cadences behind the Celestial page — the report cycle, the loop packet and the one-second motion tick — whose time the page keeps, how rates are derived and re-anchored, why a stale feed freezes, and what the browser does and does not compute.
---

# How the page stays live

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

You do not need this page to use the extension.  It is here for the
curious, and for anyone deciding how much to trust a number that is
moving.

## Three cadences

The page is driven by three different cadences, and almost every question
about its behavior is answered by knowing which one owns what.

| Cadence | Period | What it does |
|---|---|---|
| **The report cycle** | typically 5 minutes | WeeWX regenerates the page's HTML.  The first paint, the dome backdrops, the Next Visible Pass chart and the page's plate (dark or light) are all settled here. |
| **The loop packet** | seconds (2 with the Vantage driver) | weewx-loopdata writes `loop-data.txt`; the page fetches it every `refresh_rate` seconds, re-anchors every live value to truth, and moves the page's clock. |
| **The one-second tick** | 1 second | The browser advances what moves between packets — the dial's bodies, the dome's marks and satellites, the pass chart's dot — at loop-derived rates, plus housekeeping: the frozen-sky line and the wake-from-sleep check.  Nothing that reads the page's clock is repainted by it. |

## Whose time it is

The page keeps one clock, and it is the station's: the loop packet's own
timestamp, which is the instant every value in that packet was computed
for.  Before the first packet arrives it is the instant the page was
generated for.  Nothing in between — the page does not run the clock
forward on its own, so the time it shows always belongs to the data
beside it.  The header's "updated" stamp, the countdown chips, the
satellite rosters' "overhead now" and day counts, and the pass chart's
over/ahead verdict all read this clock, and they all render as packets
arrive, at loop cadence, because between two packets there is nothing
new to paint.

The browser's own clock is asked only how long something took — the
seconds since the last packet, for the motion between packets; the
seconds since the last fetch, for the throttles; whether a one-second
timer failed to fire for two minutes, which means the machine slept — and
never what time it is.  A viewer whose clock is half an hour wrong, in
either direction, sees exactly the page a viewer whose clock is right
sees.  The other side of the same coin: a station whose loop feed is not
working has no working live layer at all — the page stands as the report
drew it, or where the last packet left it, and the LIVE badge is where
that fault is reported.

One number does come from a third clock, and only that one: the age the
badge reports.  It is read from the `Date` header of the very response
that carried the loop record — the serving machine's own reading of the
time — against the record's own station timestamp, so neither operand is
the viewer's.  That is what lets the badge tell the truth in the one
case the page cannot work out for itself: weewxd takes the report cycle
and the loop feed down together, so the last packet written is newer
than the page that reads it, and the stale file is new to whichever
browser has just loaded that page.  Both of the page's own measures read
zero there; the header reads the real hour.  Where no `Date` can be read
— a page opened from `file:`, a cross-origin feed that does not expose
the header — the page falls back on what it can measure itself.  Header
and record are stamped by two machines, the web server and the weewx
station, so both are assumed to keep NTP-grade time; the skew between
them is charged against the badge's six-second `LIVE` threshold.

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

The report also bakes each event's target timestamp into the page, so a
chip whose event the feed does not carry — a lesser almanac, a group
of your own that overrode it — still counts down toward the instant the
page knew about at generation time, on the packets that do arrive.  With no feed at all
the chips stand at their generation values, like everything else on the
page: the clock they count on is the packet's (see
[Whose time it is](#whose-time-it-is)).

## The two fetched fragments

The dome and the Next Visible Pass chart are drawn by weewx-skyfield at
report time — written into the report's own directory by a generator this
extension adds to the report, `user.celestial_page.FragmentGenerator`,
which is the name to grep for in the weewxd log if they stop arriving —
but the open page keeps them current by refetching small fragments:

- **Dome backdrops.**  Each report cycle renders a staggered set of them,
  spaced `max(60 s, interval/10)` across the archive interval, and the
  page steps to the one covering the current minute by the station's
  clock, which the packets carry — so the sky advances about a quarter
  of a degree at a time instead of lurching a whole cycle at once.
  Which one that is follows from the station's clock and the archive
  interval alone: report cycles are generated for an archive record, so
  every cycle begins on an interval boundary and the page can work out
  the current one without needing to have kept up.  After a sleep, or a
  spell in a background tab, the page therefore steps straight to the
  right backdrop as soon as the loop feed catches up — the packet is
  what tells it the time, so the packet is what moves the sky.  The
  fragments describe their own timestamp, spacing, count and archive
  interval, so any archive interval works with no configuration, and if
  report cycles stall the page keeps the freshest backdrop it has rather
  than accepting one the station has not reached.
  Between steps, the sun, moon and planet marks are nudged at
  loop-derived rates.

  Keeping the freshest backdrop is right for a minute or two and wrong
  for an hour, so from 8.3.1 the page watches the backdrop's age.  Once it
  is three report cycles behind — measured against the station's own
  clock, which the loop packets carry, not the viewer's — the dome
  **freezes
  whole**, marks and satellites with it, and a line under the panel says
  so and names the fault, and the fragment it names is the one that
  actually failed: an HTTP status if that fragment is not being served,
  "not a sky fragment" if what comes back is unreadable, "no response" if
  nothing answers, and — the case no status code could reveal — "no newer
  backdrop has arrived" when the fetches succeed but no newer sky is
  being written — and "is empty" when the file is there with nothing in
  it, which is sometimes by design (a slot beyond the archive interval)
  and sometimes the station writing no backdrop at all.  Naming the file
  is what tells those two apart.  Nothing else on the page is affected:
  the dial, both satellite rosters and the countdown chips stand on the
  loop feed, not on the backdrop, and go on rolling.  See
  [The star field is frozen](troubleshooting.md#the-star-field-is-frozen).
- **The pass chart**, refetched every five minutes, which is how a
  completed pass's chart rolls over to the next pass, and how the panel
  reappears when a pass enters the window.  The moving dot does not wait
  for that: the chart states its pass's own rise and set (weewx-skyfield
  2.3.2), and past the set the dot leaves the chart, so the gap before
  the next chart shows the finished arc without a satellite on it, rather
  than a mark parked somewhere it no longer is.

Satellites are the exception to all of this: their markers move at loop
rates, continuously, because they are the one class of thing overhead
that genuinely moves fast.

Both fragments arrive as SVG with their colors already inside them, which
is why the page's plate — dark or light — is settled when the report is
generated rather than in the browser (see
[Dark, light and auto](configuration.md#dark-light-and-auto)).  Each
fragment carries the theme the report was on when it wrote it, resolved
from the report's own generation instant, so a page never finds its own
plate switched under it by a refetch.

On `theme = auto` a report cycle eventually crosses sunrise, and an open
page cannot restyle itself — its plate was baked in when it was
generated.  So each fragment declares the theme the report was on when it
wrote it, and a page that finds a fragment from the other one reloads —
once per flip, and never again if it comes back still disagreeing, which
would mean a cached copy rather than a flip.  (A fragment set declared
on a plate of its own is drawn on that plate whatever the page's, and is
never mistaken for a flip.)  The change reaches a page left open overnight
within a minute of the report cycle that makes it, rather than waiting
for someone to press reload.

## What the browser does not do

No astronomy, and no theme switching.  The javascript does arithmetic —
differences, rates, linear extrapolation, countdown subtraction — and
draws.  Every astronomical quantity on the page was computed by the
almanac in weewxd, and the page does not follow your operating system's
dark-mode setting: it wears the plate its report was generated with.
That is a deliberate division: it keeps the page cheap on a phone, and it
guarantees that what moves in the browser cannot disagree with what the
report says.

## What it costs

One `loop-data.txt` fetch per `refresh_rate` seconds (a small json file),
one pass-chart fragment per five minutes, and one dome fragment each time
the sky steps a slot — which is once a minute on a five-minute archive
interval, and never more often than that.  The page works out which slot
its station's clock calls for and fetches only when that is not the one
it already has, so a page that is in step with its station asks for
nothing at all; a page whose station has stopped writing asks for nothing
either, because its clock has stopped with it.  The one-second tick is
arithmetic on values already in memory.  Nothing on the page polls
weewxd, and nothing recomputes an ephemeris.

To keep an unattended page from polling forever, it stops after
`expiration_time` hours and shows `CLICK-ME`; a click resumes it.  See
[Configuration](configuration.md).
