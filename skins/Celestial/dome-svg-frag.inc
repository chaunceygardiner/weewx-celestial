## Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
## Distributed under the terms of the GNU Public License (GPLv3)
##
## The shared body of the staggered dome fragments: dome-svg.txt.tmpl and
## dome-svg-<k>.txt.tmpl each set $frag_k and include this file.  Each
## report cycle renders up to ten backdrops, spaced max(60 s, interval/10)
## apart across the archive interval, so the open page's javascript can
## step the sky in quarter-degree (not 1.25-degree) increments; slots
## whose offset falls beyond the interval emit empty, and the javascript
## never asks for them.  The wrapper div self-describes (timestamp,
## slot, spacing, count) so the fetch side adapts to any archive
## interval without configuration.  data-dome-ts is the slot's OWN
## depicted time; data-dome-slot is what lets the javascript recover the
## cycle base (ts - slot*step) -- computing the next slot from a
## fragment's own time made the walk relative and the sky zigzag
## (0,2,1,3,2), caught in the NOAA-21 live capture.  The almanac is the report's own, re-bound to
## the slot's time through core WeeWX's $almanac(almanac_time=...) --
## the engine contract is untouched.
##
## Deliberately NO #errorCatcher, same as before the stagger: an
## unexpected failure must fail the template (weewxd logs it and the old
## fragment stays on disk), never write error text into the page.
#if $sky_page
## SECONDS, explicitly.  $current.interval.raw is delivered in whatever
## unit the report's group_interval asks for, so a station carrying
## `group_interval = hour` reports a five-minute interval as 0.0833 --
## int() takes that to 0, every slot's offset then fails the test below,
## and ALL TEN fragments render empty.  The page keeps its
## generation-time sky and the star field stands still for ever, with
## nothing in the log, because nothing failed.  `.second.raw` converts
## regardless of the setting.  Found by Jacques Terrettaz, issue #4.
#set $frag_interval = 300
#try
## round(), not int(): the unit conversion is floating point, so an
## hour-based interval comes back as 299.99988 and truncation would
## quietly cost the set a slot.
#set $frag_interval = int(round($current.interval.second.raw))
#except
#pass
#end try
#if not $frag_interval or $frag_interval <= 0
#set $frag_interval = 300
#end if
#set $frag_step = max(60, $frag_interval // 10)
#set $frag_count = min(10, max(1, $frag_interval // $frag_step))
#set $frag_offset = $frag_k * $frag_step
#if $frag_offset < $frag_interval
#set $frag_ts = int($almanac.time_ts) + $frag_offset
## The palette is resolved against the PAGE's almanac, never the slot's:
## on theme = auto a slot minutes past sunrise would otherwise render
## paper while the page around it is still night, and the refetch would
## flip the dome mid-cycle -- the palette must be a property of the
## generation instant, exactly as the theme class on <html> is.  Guarded
## (an unknown theme raises) so a typo costs the plate, not the fragment.
#set $palette = 'night'
#try
#set $palette = 'light' if str($sky_page.theme($almanac)) == 'light' else 'night'
#except
#pass
#end try
## data-dome-palette is the plate this backdrop is DRAWN on, and it is
## how an open page notices that theme = auto has flipped under it: the
## page's own plate was baked in when it was generated, but it goes on
## refetching fragments, and the cycle that crosses sunrise renders them
## on the other plate.  The javascript compares the two and reloads once
## on a mismatch.  This fragment is the sentinel for the pass chart too
## -- it refetches five times as often.
<div class="domefrag" data-dome-ts="$frag_ts" data-dome-slot="$frag_k" data-dome-step="$frag_step" data-dome-count="$frag_count" data-dome-palette="$palette">$sky_page.dome_svg($almanac(almanac_time=$frag_ts), palette=$palette)</div>#slurp
#end if
#end if
