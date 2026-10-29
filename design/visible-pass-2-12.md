# Visible passes: weewx-skyfield 2.12

A design for what celestial changes when weewx-skyfield 2.12 redefines
a visible satellite pass.  Written 2026-10-26, before anything is
built, and revised the same day after its review.  It ships in 9.8,
with the dial label placement (`dial-label-placement.md`), and raises
the installer's skyfield floor from 2.7 to 2.12.

## What skyfield changes

From skyfield's design (its Consumers section) and its staged tree:

- **A pass is visible** when, at the same instant, the satellite is
  sunlit, the sun is below -6 degrees and the satellite is at least 10
  degrees up, for at least 60 seconds.  `next_pass.visible` and
  `next_visible_pass` share that one definition.  Today's rule lists
  passes nobody can see: Terra on 2026-10-26, "peaks 90°", is lit
  against a dark sky for 40 seconds and never above 2.4 degrees.
- **Ten new attributes** on both tags describe the window, the stretch
  that qualifies: `visible_start`, `visible_peak`, `visible_end`, each
  with `_altitude` and `_azimuth`, and `visible_duration`.  They are
  empty when the pass is not visible.  `rise`, `set`, `max_altitude`,
  the three azimuths and `duration` keep their geometric, horizon to
  horizon meaning.
- **`next_visible_pass` rolls at `visible_end`**, not at set.
  `next_pass` still rolls at set.
- **Skyfield's satellites panel** keeps its strings and fills them from
  the window: the line is the window's start date and time and
  `_sat_when(start, end)`, so "overhead now" means the window is open;
  the sub-line's appears, peaks and disappears are the window's start,
  peak and end, and its minutes the window's length, rounded by
  Python's `round` (half to even).
- **The pass chart** is drawn at the visible peak, so its featured dot
  is always sunlit (`data-sunlit="1"`), with the window drawn solid
  over the dashed arc.  `data-rise` and `data-set` stay the geometric
  rise and set.
- **The chart's caption key changes.**  Celestial shares it.

## How loopdata delivers the fields

Three facts about loopdata decide most of what follows, each measured
against skyfield's staged tree with loopdata's own
`AlmanacFieldEvaluator.insert_fields`:

- **A group is a chain prefix across the report's whole merged
  declaration** (loopdata.py ~4446), not a group of celestial's
  declaration.  It expires at its latest time leaf and is recomputed in
  the same call, so the packet whose stamp reaches `visible_end`
  already carries the next pass.  The page's clock is that packet's
  stamp, so on a report whose declaration names no later leaf of
  `next_visible_pass`, no packet ever pairs a closed window with that
  window's fields.
- **A report whose declaration names a later leaf** (`.set`, say, from
  another skin's group on the same report) keeps the group until that
  leaf passes.  The window is then closed but not rolled from
  `visible_end` until set: 03:18:49 to 03:21:17 for the fixture's pass
  A, 07:01:34 to 07:06:02 for the live ISS pass of 10-27.
- **A None value is left out of the feed**, not sent as null
  (loopdata.py ~4895).  A satellite with no visible pass carries no
  `visible_start` key at all; its three `.ordinal_compass` keys arrive
  as `'N/A'`.

## What celestial reads today

- **`PAGE_FIELDS`** (celestial.py:149-180), per satellite: the
  `next_visible_pass` group (rise, set, max altitude, duration, three
  azimuths) and the `next_pass` group (the same plus `visible`), 19
  fields with az, alt, sunlit and label.
- **The Next Visible Pass roster** (`_pass_lines`, celestial_page.py
  1931-1986, and `renderPassRow`, celestial.js 1792-1846): a dated line
  from `rise` and a sub-line from the geometric figures.
  `test_pass_lines_in_step_with_skyfield` pins the line to skyfield's
  `_sat_when`.
- **The dome's roster** (the same two functions on `next_pass`): any
  pass, tagged "visible" or "not visible" from the pass's bool.
- **The countdown chip** (`pass_chip`, celestial_page.py 1239-1264;
  celestial.js 3398-3453): the soonest `next_visible_pass` rise across
  the satellites.  It reads "appears in" before rise, "overhead now"
  until set, and "just set" for up to 60 seconds after.
- **The chart sweep's fallback** (celestial.js 3129-3138): for a chart
  without `data-rise`/`data-set`, the feed's `next_visible_pass` rise
  and set.
- **The caption** (`_pass_caption_text`, celestial_page.py 2174-2176),
  in nine lang files.
- **"Not declared" is read from an absent key** (`renderPassRow`'s and
  the chip's `hasKey` on `rise`), and a null value is taken as "no
  pass".  Production never sends that null: a satellite whose next pass
  disappears leaves the row as it was first painted, a countdown to a
  pass already over, until the page is reloaded.  The stricter 2.12 rule
  makes passless weeks commoner.

## The design

1. **Fields.**  Per satellite, the `next_visible_pass` group becomes
   the window, seven fields as now:
   - `visible_start.unix_epoch.raw` and `visible_end.unix_epoch.raw`;
   - `visible_peak_altitude.degree_angle.raw`;
   - `visible_duration.second.raw`;
   - `visible_start_azimuth`, `visible_peak_azimuth` and
     `visible_end_azimuth`, each `.ordinal_compass`.

   `rise` and `set` leave that group, so on celestial's own declaration
   it expires at `visible_end`.

   The `next_pass` group keeps its eight, and gains nothing: point 3
   reads the window from the `next_visible_pass` group instead.  (A first
   cut added `visible_start` and `visible_end` to it; they are empty on
   every pass that is not visible, most passes, and loopdata never
   caches a group with an empty leaf, so the whole group would have been
   recomputed every packet.  The second review found the tag needs
   neither.)

   Per satellite that is still 19 fields, and `PAGE_FIELDS` still 97;
   seven of them change.  The installer redeclares the satellite groups on
   every install (`declare_page_fields` replaces each group wholesale),
   so an upgrade needs no hand edit.
2. **The Next Visible Pass roster reads the window,** exactly as
   skyfield's satellites panel does:
   - the line is the window start's date and time, then
     `_sat_when(start, end)`;
   - the sub-line is "appears {start az} · peaks {peak alt}° {peak az}
     · disappears {end az} · {window minutes} m".

   The strings are unchanged, so no translation changes.  In Python
   and javascript alike, and both round half to even, as skyfield does:
   `visible_duration` is quantized to 10/128 s, so a window of exactly
   150 s happens, and javascript's `Math.round` would print "3 m"
   beside skyfield's "2 m".  One helper does it for the minutes and the
   peak altitude alike.
3. **The dome's roster stays the geometric pass,** since it is the
   table of whatever is overhead, and the dome draws any satellite
   above the horizon.  Its line and sub-line keep rise, culmination and
   set, so on one page the two rosters describe one pass two ways
   (settled below).  Its tag says "visible" when the pass is visible
   and either has not risen yet or is inside its window
   (`visible_start <= now < visible_end`), and "not visible" otherwise.
   The window is the `next_visible_pass` chain's: while this pass's
   window is to come or open, the next visible pass IS this pass, so its
   window lies inside this pass's rise and set; once it closes, that
   chain has rolled to a later pass (or to none), and a window outside
   this pass's rise and set means this one is past seeing.  So:
   - before rise, "in 3 m · visible" is true of the pass to come;
   - from rise to `visible_start` the satellite is in shadow, low or in
     daylight, and "overhead now · not visible" is what the sky shows;
   - inside the window, "overhead now · visible";
   - from `visible_end` to set, "not visible" again.

   Today the tag is the pass's bool alone, so it reads "visible" over a
   satellite nobody can see for minutes on either side of the window
   (fixture pass A: 6 minutes before, 2.5 after).  No new strings.
   Where the window chain is not declared (a declaration from before
   9.8 that the installer has not yet rewritten; see point 5), the tag
   falls back to the bool, as today.
4. **The countdown chip counts to the window:**
   - its candidates are the satellites whose window has not closed
     (`visible_end` absent or later than now), and it picks the
     soonest `visible_start` among them;
   - "appears in" until that start, then "overhead now" (skyfield's
     meaning) until `visible_end`;
   - with no candidate it hides.

   On celestial's own declaration the window's end and the roll are
   one packet, so at `visible_end` the chip goes straight to the next
   pass's "appears in".  On a report where another declaration keeps
   the group until set, the satellite whose window has closed stops
   being a candidate and the chip moves to the next satellite's pass;
   it never blanks because one satellite's window closed.  "Just set"
   goes from the chip: at `visible_end` the satellite has not set, it
   has entered shadow, sunk below 10 degrees or met the dawn.

   The generation bake moves the same way: `data-ts` becomes
   `visible_start` and `data-set` becomes `visible_end`, rounded UP to
   the second (the live path compares an integer packet stamp with the
   float, so a floored bake hid the static chip up to a second early).
   The static path itself is unchanged: "appears in", "overhead now",
   then hidden.

   In the visible roster, the closed-but-not-rolled state (reachable
   only on such a report) prints the window's date and time without a
   countdown, instead of `satWhen`'s "just set".  The dome's roster
   keeps "just set", which is true of a geometric pass.
5. **A declared chain with no times is no pass.**  loopdata leaves a
   None value out of the feed, but formats an empty compass point as
   `'N/A'` and sends it: a chain's three `.ordinal_compass` keys are in
   the feed whenever the chain is declared, pass or no pass (measured
   against loopdata's evaluator).  So when a chain's compass keys are
   present and its times are not, there is no pass: the row says "no
   visible pass in the coming week" (or the no-elements line when
   `sunlit` is absent too) and the chip passes the satellite over; the
   same for `next_pass` and "no pass in the coming week".  When the
   compass keys are absent the chain is not declared -- a weewx.conf
   still carrying 9.7.2's field list, until the installer rewrites it,
   which the page already reports as out of date -- and the row and the
   chip stand as they were, as through 9.7.2.  Each row asks for its own
   chain; nothing reads the satellite's `az` for this any more, since
   elements gone stale mid-session drop the `az` and the rows must then
   say so.  A row whose new pass lacks a figure blanks its sub-line
   rather than leave the last pass's figures under it.  (The first cut
   of this point read an absent time as no pass whenever the satellite
   was in the feed; the review showed that misreads a 9.7.2 field list
   as a week without passes.)
6. **The chart sweep** keeps sweeping the featured dot along the arc,
   rise to set, by the chart's own `data-rise`/`data-set`.  The
   dot's solid or hollow look keeps following the live sunlit flag, so
   it turns hollow as the satellite enters shadow.  The fallback for a
   chart without those attributes goes, and such a chart stands as
   drawn.  Every chart since skyfield 2.3.2 carries them, and the floor
   is now 2.12, so the fallback could only fire on a chart celestial
   itself never makes.  Once points 2 and 4 read the window, it is
   also the last reader of the `next_visible_pass` rise and set that
   point 1 removes.  The station's chart follows the same roll as the
   feed: the first report cycle after the window closes draws the next
   visible pass, and the page's refetch (every five minutes) brings it
   in, often before the satellite sets.  Until then the chart, the whole
   pass with its window drawn solid, keeps sweeping pass A while the
   roster already names pass B; today that gap opens at set.  The sweep
   past the window is true of the drawing.
7. **The caption** becomes skyfield's new key, copied verbatim with its
   eight translations from skyfield's lang files, and the old key
   leaves celestial's nine lang files and `docs/i18n-dictionary.md`.  A
   consuming skin reading `$celestial.pass_caption` gets the new text
   with no change of its own.
8. **The installer's floor** rises to skyfield 2.12, with the same
   refusal message shape as today's 2.7 check.
9. **Docstrings and comments** that say "at the culmination" or define
   visibility the old way change: `_pass_html`, `dome_roster_html`,
   `_pass_lines`, and the celestial.js comments at the sweep, the chip
   and its header comment at 3397 ("the -60 grace and the engine's roll
   interlock").  The field counts do not change.

## Tests

Every one runs the code.

- **Breakages, rewritten:**
  - The pass-head pins (test_celestial.py:1111, :2494) become the
    window's: pass A reads "Sun, Jun 22 · 3:17 AM → 3:18 AM · peak 17°".
  - :1124 `test_pass_row_day_count_is_calendar_days` pins "Jun 21, 3:59
    AM", the rise; the window opens at 04:03:54.
  - :2484 asserts "just set" in the visible roster, which point 4
    removes.
  - :11115 `test_pass_lines_in_step_with_skyfield` builds fake passes
    without `visible_*` attributes, and splits in two, since
    `_pass_lines` serves both rosters and only one reads the window.
  - :2248 `PASS_BASES` x `PASS_ATTRS` assumes one attribute set for both
    chains.
  - :12795 `test_satellite_fields_evaluate_in_loopdata` reads
    `next_visible_pass.rise` and pins its azimuths (:12829-12842).
  - The hand-built feeds carrying `next_visible_pass.rise/set` at
    :3045, :3222, :3304, :3529, :4103 and :5191; the sweep-fallback
    legs among them go with point 6.
  - `as_sunlit_at_generation` gains its mirror, a derived SHADOWED
    chart, so `test_pass_sweep_dot_flips_sunlit_in_a_real_browser`
    still drives both flips.
- **The mechanism point 1 exists for,** in act two of :12795, which
  already drives loopdata's real evaluator: the `next_visible_pass`
  group rolls at 03:18:49; `next_pass` stays pass A with `visible`
  true until 03:21:17, the window inside its rise and set while open; a
  non-visible `next_pass` carries every one of its fields, so loopdata
  can keep it.  Sabotage-checked by putting `set` back in the
  `next_visible_pass` group, which must fail it.
- **The feed builder matches loopdata** (`sat_feed_packets`,
  test_celestial.py:216-260): None-valued keys left out, the three
  compass keys `'N/A'` on a passless satellite, and each packet stamped
  with the instant its values were computed for, never the browser's
  wall clock.  The closed-but-not-rolled state is then built only on
  purpose, by a leg that declares a later leaf, as a report can.
- **`_pass_lines` in step with skyfield's `satellites_html`** at the
  boundary instants: before the window, inside it, and at its end;
  150 s and 270 s windows pin the half-even minutes on both sides.
- **The dome's tag:** a visible pass rendered at four instants (before
  rise, between rise and `visible_start`, inside the window, after
  `visible_end` but before set), in Python and in the browser.  The
  second and fourth read "not visible", sabotage-checked by restoring
  the bool-only rule.  A leg with `visible` true and no window keys
  reads "visible".
- **The chip:** a browser leg stepping a loopdata-shaped feed through
  `visible_start`, mid-window and `visible_end`: "appears in", then
  "overhead now", then the next pass's "appears in", never "just set".
  A second leg on a declaration that keeps the group until set, with
  two satellites: when the first one's window closes the chip names
  the second's pass, never blanks.  The generation bake gets the same
  instants in Python, and `data-set` is the end rounded up.
- **An absent window:** a satellite in the feed with no `visible_start`
  key reads "no visible pass in the coming week", where today it would
  keep its first paint; a satellite absent from the feed keeps it.
- **The fields:** `PAGE_FIELDS`, the declaration and the manual's
  printed lists move together; the existing pins catch any one moving
  alone.
- **The sweep:** a chart without `data-rise`/`data-set` stands as
  drawn, in place of the fallback's leg.
- **The caption:** the new key in all nine lang files, and the old key
  in none.  The existing shared-key test with skyfield then compares
  it.

## Docs and consumers

- docs/index.md:134 and reading-the-page.md:291 give the new
  definition.  reading-the-page.md:250 (the caption), :241 (the dome's
  tag) and :79 (the chip's "just set") change too.
- fields-reference.md prints the new groups (a test pins them); the
  counts stay 19 per satellite and 97 in all.
- upgrading.md: 9.8 needs skyfield 2.12, and the installer redeclares
  the fields.
- changes.md: the bullets, with skyfield 2.12 at the top as action
  required.
- **A consuming skin reads `next_visible_pass.rise` and `.set` through
  celestial's own `satellites` group** (its skin.conf names
  `celestial_panels = geocentric, dome, pass` and leaves the satellite
  fields to celestial): its pass chip, its first paint and a gate in
  its tests.  The first 9.8 install redeclares that group without
  them, so that skin switches to the window fields in the same
  rollout, and is told before this is built.  Putting rise and set
  back in a group of its own would keep
  the `next_visible_pass` group on the report until set, the state
  point 4 handles; it is told that too.

## Settled

Settled 2026-10-26 after the review:

- **The two rosters describe one pass two ways.**  The dome's roster
  is the geometric pass, rise to set, because it is the table of what
  is overhead; the Next Visible Pass roster is the window.  For the
  fixture's pass A the dome row reads "appears SSW · peaks 19° SE ·
  disappears ENE · 10 m" and the pass row "appears ESE · peaks 17° ESE
  · disappears E · 2 m".  Kept: each is true of what its table is
  about, and the dome's tag (point 3) says when the pass can be seen.
- **The consuming skin moves in the same rollout,** as above.

Points 3 to 6 follow from skyfield's own definitions, loopdata's
delivery and its handoff, and are taken as written: the dome's tag
comes from the window, the chip passes over a closed window rather
than saying something false, an absent window is no pass, and the
fallback goes because it cannot run.
