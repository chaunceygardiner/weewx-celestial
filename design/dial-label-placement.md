# Geocentric dial: label placement

A design for where the Geocentric dial writes each body's name.  Written
2026-10-26, before anything is built, and revised four times the same
day after independent reviews (eleven findings, then fourteen, ten and
eleven, all agreed).  After the third it gained leader lines (point 9)
and ring numbers that move around their ring (point 10).  After the
fourth, whose findings shared one cause (what a line or a text beside a
mark is read as), the leader lines were redesigned to the ownership rule
every other name keeps, and the dial's motion trails, which no earlier
measurement had drawn, became obstacles (point 12).  It ships in 9.8,
together with the changes weewx-skyfield 2.12's redefinition of a
visible pass requires.  A fifth review's findings were narrow, and were
folded into the build rather than into another round; the build and
its own measurements are at the end ("As built").

## The problem

On a phone the dial writes names beside the wrong bodies.  Reported on a
consuming skin at 390px, and reproduced on the bundled sample page the
same minute (9.7.2, 390x844, DPR 3, Chromium): "Moon" is written over
Uranus's dot, "Saturn" sits beside Neptune while "Neptune" sits nearer
Saturn, "Mars" sits beside Halley's diamond, and the Sun's, Mercury's
and Halley's names are dropped.

It is not only a phone problem.  Measured over many real skies (method
below), the desk frame misattributes names too:

| 9.7.2 | names | dropped | ambiguous | under 1.5x | over another mark | off the drawing | own tail through it |
|---|---|---|---|---|---|---|---|
| Palo Alto, narrow, 16-unit labels (bundled) | 2743 | 554 | 1541 | 1331 | 457 | 24 | 8 |
| Palo Alto, narrow, 12-unit labels | 2743 | 276 | 1637 | 1428 | 348 | 5 | 6 |
| Palo Alto, wide, 12-unit labels (bundled) | 2743 | 84 | 892 | 787 | 454 | 0 | 272 |
| Sydney, narrow, 16 | 780 | 157 | 438 | 364 | 132 | 8 | 2 |
| Sydney, wide, 12 | 780 | 27 | 233 | 206 | 121 | 0 | 80 |
| Proxima due east or west, narrow, 16 | 520 | 86 | 287 | 253 | 112 | 19 | 17 |
| Proxima due east or west, wide, 12 | 520 | 23 | 149 | 119 | 60 | 5 | 56 |
| Proxima on a diagonal, narrow, 20 | 520 | 129 | 256 | 232 | 122 | 35 | 26 |

"Names" counts every name whose mark is drawn, Earth's included, sky by
sky.  Distances run from a name's INK to a mark's disc: the box
`getBBox` returns is the font's whole cell, ascent to descent, and a
name above its mark would otherwise measure about 3.5 units farther
away than it looks.  The ink's width is `getBBox`'s; its height comes
from canvas `measureText` (`actualBoundingBoxAscent`/`Descent`) in the
same face, asked at ten times the type size because the canvas answers
in whole pixels.  "Ambiguous": another mark is less than twice as far from
the ink as the name's own mark is (a yardstick calibrated by eye on the
reported sky).  "Over another mark": the name's cell touches another
mark's disc.  "Off the drawing": the padded box (`LABEL_PAD`) leaves
the viewBox.  The Sun's disc is its glow whenever the glow is drawn.

With the one-hour motion trails a live page draws after its second
packet, 9.7.2 also runs another body's trail through 318 names on the
narrow frame and 429 on the wide; a trail is a 1.5-unit line in its
body's color, about as long as a name, and one ending inside a name or
a ring number reads as a line pointing at it.

Earth's name is fixed below Earth and checked by nothing.  On the
narrow frame it sits nearer the Moon than Earth (measured from the
cell) in 56 of the 211 Palo Alto skies.

## Why

`placeLabels` gives each name four candidate spots, all on the radial
line through its mark: `r ± labOff` and `r ± 1.9 × labOff`, outward
first unless the mark is beyond `labIn`.  The text anchor is `start` or
`end` by side and `middle` near vertical: within about 20 degrees of
vertical for the 1x spots and about 11 for the 1.9x spots, because the
code compares `sin(a) × 1.9` against 0.35.  So most of a label runs on
away from its spot.  The first spot whose padded box misses every box
already placed wins; if none does, the name is dropped.  Four things
follow:

1. **The spots are far from the mark.**  On the narrow frame the log
   scale gives 12.7 units per decade, so everything from 0.3 to 30 AU
   (Venus at its nearest to Neptune) lies between r=70 and r=96: a band
   of 26 units, most of it within one AU decade either side of the Sun's
   r=77.  `labOff` is 21, nearly the whole band, and the 1.9x spots are
   40 units out, past it.  Any body at a similar azimuth is then as
   close to the name as its own body is.  Today's Saturn/Neptune swap is
   exactly this: Saturn is placed first (it is nearer Earth) and takes
   its outward spot, which is beside Neptune; Neptune's outward spot
   then collides with "Saturn", so it takes its inward spot, beside
   Saturn.
2. **Marks are not obstacles.**  Only labels are (the cardinals and
   Earth's name seed the pass), so a name can be written across another
   body's dot, or across its trail.
3. **Nothing checks ownership.**  Nothing asks whether a spot is nearer
   its own mark than any other.
4. **Nothing checks the frame.**  The far spots can put a name partly
   outside the viewBox: 24 times in the Palo Alto skies on the narrow
   frame, 5 on the wide frame when Proxima is due east or west.

The wide frame has the same rule.  Its scale gives 29.3 units per
decade against a `labOff` of 17 (the narrow frame: 12.7 against 21), so
the same band is 3.4 offsets wide instead of 1.2.  The fault shows less
often, but it is there.

## The design

Everything outside the placement step stays as 9.6.1 built it: every
box measured in one read pass before any write, names shown before they
are measured, no "is the drawing visible" guard, and a re-measure on
`document.fonts.ready` and on a resize inside one frame.

1. **Names are measured to their ink.**  In the same read pass, each
   name's ink height is taken with canvas `measureText` in the face the
   stylesheet resolves for it now (`getComputedStyle`: style, small
   caps, weight, size, family, and `letterSpacing` where the canvas
   has it); its width stays `getBBox`'s.  The canvas is asked at ten
   times the type size and the answer divided by ten, because its ink
   metrics come back in whole pixels: at the narrow frame's 16 units
   that rounding alone understated the ink by up to 0.67.
   - **Properties that move or grow the drawn glyphs without moving the
     canvas's font box are read directly,** and any of them set sends
     the name to the cell: `baseline-shift` other than `baseline`,
     `dominant-baseline` other than `auto` or `alphabetic`,
     `alignment-baseline` other than `auto` or `baseline`, a
     `font-variation-settings` or `font-feature-settings` other than
     `normal`, a `writing-mode` other than `horizontal-tb`.  A small
     baseline shift slipped under the comparison below in Chromium and
     understated the ink by up to the whole 3-unit gap; variation axes
     and feature settings can change glyph heights with the advance and
     the font box unchanged.
   - **Paint that reaches past the glyphs sends the name to the cell,
     padded** by that reach: a stroke by half its width, times the miter
     limit at a miter join (the SVG bound); a `text-shadow` or a
     `drop-shadow` filter by its larger offset plus its blur; a `blur`
     filter by three times its radius; any other filter that cannot be
     read by 0.25 em; an underline or overline by 0.15 em (an overline
     measured 0.08 em past the cell, which no other measure contains).
     `getBBox` leaves all of these out.  A skin that halos its names
     with `stroke-linejoin: round` costs half the width.
   - **Otherwise the canvas answer is taken only when the canvas is
     drawing the SVG's face.**  Two checks, each against what `getBBox`
     answered for the same element: the canvas's advance must agree
     with the width to 1 unit plus 10%, and the canvas's font box (its
     `fontBoundingBoxAscent` and `Descent`) must sit where the cell
     sits, each edge to 0.15 em.  Anything else answers the cell, which
     contains the ink.  The canvas follows only what the font shorthand
     carries, so a stylesheet's `text-transform`, `font-size-adjust`,
     `font-stretch` or letter spacing the canvas cannot take changes
     the advance and is refused.  Both checks need their tolerance
     because `getBBox` lays text out at the device's rounded size: for
     faces the canvas does follow, its width wandered up to 7.9% from
     the canvas's advance, and its cell edges up to 0.11 em from the
     font box (13.33 and 4.44 units on a phone for 16-unit Georgia,
     whose font box is 14.6 and 3.6).
   - **The canvas's font is set once per face per pass:** the names
     are grouped by face (font string and letter spacing) before any is
     measured, and each group's face is assigned through a sentinel: a
     fixed font first, so a font string the canvas refuses leaves the
     sentinel behind, which the code detects, never another face.  A
     refused face answers the cell for its names.  Nothing is
     remembered between passes.
   - Where the canvas cannot answer at all, the cell stands, as the
     estimate stands for `getBBox` today.  Spots and the ownership test
     use the ink; label-to-label collisions and the frame use the
     padded cell, as now.
2. **Candidates touch the mark.**  Eight spots around the mark (right,
   left, above, below and the four diagonals), the ink's near edge
   `GAP` = 3 units from the mark's edge.  Right and left center the ink
   vertically on the mark.  The spots are tried in order of how nearly
   each points away from Earth (dot product with the outward radial),
   so a name still goes outward when it can.
3. **Earth's name is placed by the same pass,** with the same eight
   spots, below first (at the center there is no outward radial).  It
   leaves `dialFixedLabels`, which keeps the cardinals.  `earthDy` stays
   as the build-time position and is no longer where the name ends up.
   - **The placer owns every name's anchor.**  It writes `text-anchor`
     as an inline style on every name it places, because a stylesheet
     rule outranks the attribute: `.cel-earthlab` in celestial.css says
     `text-anchor:middle`, and so does at least one consuming skin's own
     copy of that rule.  The celestial.css declaration is then dead and
     is deleted; own-skin.md says a skin's `text-anchor` on the dial's
     names has no effect.
   - **Earth's mark gains a `<title>`,** its translated name, as every
     other mark has, so a dropped Earth name still answers a tap.  None
     dropped in any measured sky, but nothing guarantees it.
4. **The ownership test.**  A spot is accepted only if, for every other
   drawn mark (Earth's disc included):
   - its disc is at least `own + TOUCH` from the name's ink, and
   - its disc is at least `own + MIN` from the name's near end (the
     point of the ink nearest its own mark's center),
   where `own` is the name's real distance to its own mark: `GAP` for a
   touching spot, `GAP` plus the leader's length for a leadered one
   (point 9).  `TOUCH` = 3, `MIN` = 6.  The first clause stops a name
   running into another dot anywhere along its length; the second stops
   another dot crowding the place where the name attaches.  A mark's
   disc is its dot (`dotR`, `moonR`, `cometR`); the Sun's is its glow
   (`glowR`) while the glow is drawn, `sunR` below the horizon.
   (`.cel-sunglow` is blurred 6px, so the glow visibly reaches a little
   past `glowR`.)  Mark positions come from the values `renderGeo` and
   `renderComets` just computed, carried on the queued entry, never
   from a DOM read.  One consequence to know: when a mark's disc
   touches another's (Mercury inside the Sun's glow is the common
   case), no spot is nearer its own mark than the other, and its name
   is dropped.  That is the rule saying the name would be ambiguous
   anywhere.
5. **Labels and the frame.**  A spot's padded box must miss every label
   already placed and stay inside the viewBox.
6. **The order.**  The Moon's name, then Earth's, then the other
   bodies most crowded first (more marks within 30 units of the mark,
   on both frames), ties nearest Earth first; then the comets the same
   way.  The Moon goes before Earth because Earth's name is what
   crowds it out: the Moon sits 29 units from Earth on the narrow
   frame, and in each of the third prototype's 13 Moon drops (Earth
   first), three to five of its eight spots collided with Earth's name,
   the only label placed by then near the center, and other marks'
   discs refused the rest.  Earth's name, with eight spots around the
   center of the dial, has not dropped in any measured sky going
   second.  The order runs name by name, every spot of one name before
   the next name: an earlier name's leadered spot can take a later
   name's touching spot.  Placing every name's touching spot first and
   leaders after (two passes) dropped more names on the fourth review's
   measure (292 against 254 phone drops on the fifth prototype), so the
   order stands.
7. **Names keep their spot.**  A name's previous spot is tried first
   within its tier (point 9).  The state is one map, body key to spot,
   owned by the dial: `buildDial` clears it (a frame flip is a
   different drawing), and a dropped name's entry is deleted.  It
   reorders candidates and never changes what is accepted.  Earth's
   name is not in the map: its mark never moves, so remembering would
   only keep the name wherever the Moon last pushed it, long after the
   Moon has gone; it takes its first free spot, below when there is
   room.  One consequence to accept knowingly: a page left open places
   other names differently from a fresh load of the same sky (measured
   below), each placement passing every rule.
8. **A name's own tail and own trail.**  A comet's tail rays, and the
   name's own motion trail (point 12), are its tail.  Spots whose padded
   box its tail crosses are tried after every other spot, across all
   tiers: a leadered spot clear of the tail is tried before a touching
   spot through it.  "Crosses" is an exact segment-against-box test.  The candidates are built tier by tier (point 9),
   each tier ordered by point 7, and then sorted by this rule with a
   stable sort, so inside each half the tier order and the remembered
   spot stand.  A tail cannot make a name read as another body's; it is
   legibility, not ownership, so such a spot is a last resort, not
   refused.
9. **Leader lines.**  When none of a name's eight touching spots
   passes, six of the eight directions are tried 8 and then 16 units
   farther out, each joined to its mark by a line: not right and left,
   whose level line runs into the name's first or last letter and reads
   as a dash ("Saturn–").  The line runs from 1 unit outside the mark's
   disc to 1.5 units short of the name's near end.
   - **The ownership test is point 4's, from the real distance:** every
     other mark must be at least `TOUCH` farther from the ink than the
     name's own mark is, and `MIN` farther from the near end.  A line
     does not make a name its body's if another mark is nearer it.
   - **The line** keeps `GAP` + `TOUCH` (6) from every other disc, so
     it cannot start inside a pair of overlapping marks, and `TOUCH`
     from every other line and every other body's stroke (point 12).
     Past its first 6 units it also keeps `TOUCH` from its OWN trail
     and tail, so it never runs along either (the fifth review found
     lines laid along their own trail and down their own comet tail,
     where only the line's far end had been tested, and the tail rule
     then preferred such spots).
     It crosses no label, and later names and ring numbers do not cross
     it.
   - **It looks like no trail:** a dotted line (round caps, a dot every
     2.8 units, 1.4 wide) in `--muted`, where a trail is solid, in its
     body's color, fading.  A celestial.css rule on both plates that
     TestContrast scores as a must-see mark.
   - Earth's name takes no leader (it has never been refused at all
     eight spots).  Each body's and comet's name gets one hidden
     `<line class="cel-leader">` in `buildDial`.  It is shown, moved
     and hidden with its name, and forgotten with the rest on a
     rebuild.
10. **Ring numbers** are placed last, each on its own ring, at the
    first of eight azimuths whose spot passes.  The order is 157.5
    (today's spot), then 202.5, 112.5 and 247.5, then the upper four,
    67.5, 292.5, 22.5 and 337.5.  A spot passes when:
    - its padded box misses every label and line placed and stays in
      the frame, as now;
    - its cell keeps `GAP` + `TOUCH` (6) from every mark's disc and from
      every trail, the clearance a name keeps from marks not its own,
      so a ring number can never read as a body's distance;
    - its cell keeps 12 from every name's ink and every cardinal: a
      number in the same muted color as a below-horizon name, on the
      same text line a word-space away, read as one phrase ("0.01 au
      Moon").  6 would be no rule at all: two padded boxes already
      keep 6 apart.
    - its cell keeps `TOUCH` from every leader line.

    Each ring number's azimuth is remembered like a name's spot, so it
    does not hop between redraws.
11. **A name that fits nowhere is dropped**, as now: `display="none"`,
    and the mark keeps its `<title>`, which the tap tooltip shows.
12. **Strokes are obstacles.**  A stroke is anything drawn from a
    mark: its motion trail and a comet's tail rays.  `drawTrail` keeps
    each trail's drawn segments on the trail (a list of endpoints,
    rewritten every render), and the comet render its rays, and the
    placement pass reads them there.  A name keeps 6 units (`GAP` +
    `TOUCH`) from every other body's strokes, measured from its ink, the
    distance a mark keeps from a name at `GAP`; a line and a ring number
    keep theirs (points 9 and 10).  A trail is drawn only
    once two packets give rates, about a refresh interval after load.
    Until then the pass places against the trail the sky's rotation
    will draw: for each mark, the diurnal azimuth rate at its azimuth
    `A` and altitude `h`, `w (sin(lat) - cos(lat) cos(A) tan(h))` with
    `w` one sidereal turn, its distance held, swept back one hour on the
    same segments `drawTrail` uses (none above 89 degrees, where the
    rate has no bound).  The predicted trail is never drawn; it only
    keeps names off the place the trail is about to occupy, so the
    names do not rearrange when it appears.

`labelCandidates`, `newPlacer` and the frames' `labOff`, `labIn` and
`labDy` go.  `fixedBox` stays for the cardinals; `labPx` stays (the
estimate's fallback size).  Comments that say Earth's name never moves
change: `dialFixedLabels`'s, `fixedBox`'s, and the narrow frame's note
that the inner ring is sized to clear "the Earth label below the
center".  So does the comment in
`test_the_frame_follows_the_drawings_own_width_in_a_real_browser`
headed "WHAT THE ORDER GUARANTEES", which promises that the Moon's and
the Sun's names cannot be crowded out; under this design either can be
(see the Tests section).  The page's "Rates and trails need two
packets" is unchanged: nothing is drawn sooner.

## Measured

The method: a scratch harness loads the bundled sample page with a
given `celestial.js`, blocks the loop-data poll, and for each sky hands
the page two packets ten minutes apart, each sky's second position
computed by weewx-skyfield 600 s earlier, so the page derives real
rates and draws its trails as a live page does; then it rebuilds the
dial, at 390x844 (DPR 3, narrow) and 1280x900 (wide).  Palo Alto: 211
skies, every 3.5 days plus 75 minutes (so the hour walks) from
2025-01-01, plus the reported instant 2026-10-26 09:45 PDT.  Sydney: 60
skies the same way.  Neither puts a name at the frame's edge, because
Proxima, the body at the rim, stays between azimuth 145 and 215 from
both; so a third set takes 40 of the Palo Alto skies and sets Proxima's
azimuth to 88 or 272, and a fourth sets it to 45, 135, 225 or 315 and
is run on the narrow frame at 20-unit type, where the rim bites on the
narrow frame too; a station south of about -63 degrees really sees
Proxima at all of those azimuths.  All computed by weewx-skyfield with
the default comets (Halley and Hale-Bopp, from its archived MPC rows).
Saturn and Neptune are near conjunction through that span (azimuths 3.9
degrees apart at the median, 20 at most), so their pair is
over-represented compared with a typical decade.  Every earlier
measurement in this document's history was taken without trails; none
of the figures below is.

The prototype (the sixth; `make_proto.py` in the harness) implements
points 1-12.  Against 9.7.2:

| | dropped | names on a leader | ambiguous / under 1.5x | over another / off the drawing | own tail or trail through it | another trail through it |
|---|---|---|---|---|---|---|
| Palo Alto, narrow, 16 | 543 (554) | 228 | 0 / 0 (1541 / 1331) | 0 / 0 | 16 + 14 (8 + 3) | 0 (318) |
| Palo Alto, narrow, 12 | 426 (276) | 150 | 1 / 0 (1637 / 1428) | 0 / 0 | 9 + 6 | 0 |
| Palo Alto, wide, 12 | 132 (84) | 99 | 0 / 0 (892 / 787) | 0 / 0 | 0 + 13 (272 + 16) | 0 (429) |
| Sydney, narrow, 16 | 147 (157) | 62 | 0 / 0 (438 / 364) | 0 / 0 | 3 + 4 | 0 |
| Sydney, wide, 12 | 44 (27) | 17 | 0 / 0 (233 / 206) | 0 / 0 | 0 + 4 | 0 |
| Proxima east/west, narrow, 16 | 111 (86) | 63 | 0 / 0 (287 / 253) | 0 / 0 | 1 + 2 | 0 |
| Proxima east/west, wide, 12 | 30 (23) | 13 | 0 / 0 (149 / 119) | 0 / 0 | 0 + 2 | 0 |
| Proxima on a diagonal, narrow, 20 | 147 (129) | 74 | 0 / 0 (256 / 232) | 0 / 0 | 2 + 8 | 0 |
| Swedish names, narrow / wide | 597 / 140 (583 / 100) | 230 / 113 | 1 / 0 | 0 / 0 | | 0 |
| 20- / 16-unit labels, narrow / wide | 722 / 157 (734 / 149) | 286 / 136 | 0 / 0 | 0 / 0 | | 0 |

9.7.2's figure is in parentheses; there are 2743 names in each Palo
Alto row, 780 in each Sydney row and 520 in each of the others.  The
ambiguity columns judge a touching name by distance from its ink; for
a leadered name the harness checks the rule itself: no leadered name in
any run sits nearer another mark than its own (the fifth prototype,
whose lines said whose a name was whatever the distances: 135 narrow
and 31 wide).  A leadered name is held to `own + TOUCH`, not to twice
its own distance: 142 of the 228 on a phone have another mark less
than twice as far from their ink as their own (53 under 1.5x, the
least 1.16), and 42 of 99 on a desk.  For these the line, not the
distance alone, shows whose the name is; the renders bear it out.  The same prototype without leader lines drops 622 and
165 in the first and third rows.  Before the second packet, with the
predicted trails standing in, it drops 544 and 133.

**Which names drop.**  Palo Alto, per body, narrow / wide, prototype
(9.7.2): Earth 0 / 0 (0 / 0), Moon 2 / 0 (0 / 0), Sun 60 / 12 (24 / 7),
Mercury 150 / 56 (58 / 10), Venus 77 / 22 (33 / 12), Mars 52 / 10 (41 /
18), Jupiter 39 / 5 (52 / 2), Saturn 92 / 25 (47 / 4), Uranus 2 / 0 (37 /
0), Neptune 50 / 1 (113 / 28), Proxima 0 / 0 (2 / 0), Halley 6 / 0 (61 /
2), Hale-Bopp 13 / 1 (86 / 1).  The drops have moved from the outer
bodies, which 9.7.2 crowded off, to the bodies about the Sun, which it
named wherever a spot was free, often beside another body.  Mercury
dropping 150 times on a phone is the ownership rule (point 4): with
trails ignored it still drops 138 times; in most of them its disc
touches the Sun's glow, and no spot is then nearer Mercury than the
glow.

**Trails.**  The clearance a name keeps from other bodies' trails,
narrow / wide drops and trails through names: 6 units (this design)
543 / 132 and 0 / 0; trails held to the whole ownership rule as marks
609 / 163 and 0 / 0; 3 units 528 / 118 and 5 / 0 (39 / 28 within 3);
ignored 490 / 91 and 159 / 258.  Placed against no trail before the
second packet, a page rearranged 565 of 2743 narrow names and 530 wide
the moment trails appeared; placing against the predicted trail, 11
and 5.

**Ring numbers.**  Shown out of 211, prototype (9.7.2).  Narrow: "0.01
au" 148 (0), "1 au" 198 (20), "100" 201 (27), "10⁴" 211 (78).  Wide:
all eight in every sky (9.7.2 between 147 and 199 each, 1465 in all).
Within 10 units of a name of the same muted color, cell to cell: 7
narrow and 0 wide (measured as the rule is written, cell to the name's
ink, none: the least 11.88)
(9.7.2 9 and 21; without the 12-unit name clearance, 74 and 79, the
clearance costing 19 narrow numbers and none wide).  No trail runs
through a ring number (9.7.2: 8 and 45).

**The frame check is load-bearing only at the rim.**  With it removed,
the diagonal skies put 40 names off the narrow drawing; with it, none.
The Palo Alto and Sydney skies never reach the frame.

**The ink.**  On the bundled page the guard takes the canvas for every
name in both engines at 12-, 16- and 20-unit type (measured on the
fourth and fifth prototypes; the comparison is unchanged).  Against
screenshots of 15 names x 3 sizes, the phone frame at DPR 3 and the
desk frame at DPR 2 and 1, in both engines (`ink_probe.py`):

- Refused everywhere, every name to the cell, by the direct reads:
  every `baseline-shift` probed (1, 2 and 3 units up, 1 and 2 down,
  0.12 em, -0.08 em), `dominant-baseline: ideographic` and `central`, a 3-unit
  stroke (miter and round), `font-variation-settings`,
  `font-feature-settings`; and by the comparison: `text-transform:
  uppercase` and `font-size-adjust`.  Firefox also refuses
  `font-variant-position: super`; Chromium takes it and draws it as
  plain text.  A stroked name's padded cell contains its drawn ink.
- Taken: the bundled two, an oblique, a bold condensed, a quoted
  family, `dominant-baseline: alphabetic`, `petite-caps` (it then
  overstates), and `all-small-caps` sometimes.  Where taken, the canvas
  understates the drawn ink by at most 0.04 (Chromium) and 0.52
  (Firefox) on a phone, 0.61 and 1.03 at DPR 2, and 1.76 and 1.30 at
  DPR 1, where hinting snaps the drawn letters to whole device pixels.
  The 3-unit gap holds all of it.
- (Through the fourth review the probe's quoted-family case wrote its
  quotes inside a double-quoted style attribute, which ended the
  attribute: it measured the default face.  The figures above are
  from the corrected probe.)

**The order** (second prototype, TOUCH 3, MIN 9): nearest first drops
859 / 173, most crowded first 822 / 159.  Ranking by importance (Sun
and Moon, then the bright planets, then the rest), measured on the
first prototype, did not keep the Sun's name.  The Moon before Earth
(fourth prototype) against Earth before the Moon (third): 539 / 104
against 544 / 105 dropped, the Moon's 2 against 13.

**Tails.**  Names crossed by their own comet's tail, narrow / wide: 16
/ 0 (9.7.2 8 / 272; with the tail rule inside each tier rather than
across them, 83 / 40).  By their own trail: 14 / 13 (with the trail
not counted as a tail, 156 / 205).

**Names keeping their spot.**  Each sky is drawn, then drawn again with
every azimuth 0.25 degrees on (about a minute of sky) without a
rebuild; a name that changes side, or appears or disappears, counts.
Names changed, narrow / wide: 9.7.2 19 / 5, this prototype 25 / 13.

**An open page against a reload.**  Every seventh Palo Alto sky (31)
turned 0.25 degrees at a time without a rebuild, then compared with a
fresh build of the same turned sky.  Narrow, 8 hours: 64 of 321 placed
names in a different spot; drops 82 against 86.  Wide, 2 hours: 94 of
390; drops 13 against 13.  Earth's name is somewhere other than below
Earth in 4 of the 31 narrow pages, open and fresh alike.

**Speed.**  `placeLabels` with trails on the page, every seventh sky,
20 passes each, two runs, on a Raspberry Pi at load average 11 to 14,
the prototype's refusal log off.  Median (90th percentile), in ms:
this prototype 2.3 (7.3) narrow and 2.6 (8.3) wide, the same before the
second packet; 9.7.2 0.6 (1.6) and 0.8 (3.7).  The dial redraws once a
second.  The leader tiers and the trail checks are the difference;
each trail check first tests the trail's bounding box.

## What the reader sees

The renders (9.7.2 and this prototype, nine Palo Alto skies and two
Sydney skies, both frames, with trails, plus the prototype without
leaders and two other trail and ring settings) were all inspected.

- Every name is drawn against its own mark, or at the end of a short
  dotted line to it, nearer its own mark than any other, Earth's
  included, on both frames.  No trail runs through or ends at a name or
  a ring number.
- On a phone about one name in five is not drawn (543 of 2743), as
  today (554); on a desk one in twenty (132, against 84).  What is not
  drawn has changed: 9.7.2 drops the outer bodies and names the bodies
  about the Sun beside whatever is there, and seven in ten of the names
  it draws on a phone sit where another body is less than twice as far
  as their own (1541 of 2189).  This drops the bodies about the Sun when
  they crowd it: on a phone Mercury is named in 61 of 211 skies, the Sun
  in 151, Venus in 134.  A missing name is honest; a wrong one is not.
  Every body stays in the roster beside the dial, and a tap on a mark
  names it.
- About one name in twelve on a phone (228 of 2743), and one in
  twenty-eight on a desk, hangs off a dotted line.
- The Moon is named in 209 of 211 phone skies, and Earth's name sits
  against Earth, below it when there is room, moving when the Moon
  crowds it.
- The ring numbers show far more often ("0.01 au" on a phone in 148
  skies of 211, against never), and not always on the same spoke.
- A page settles once: the names placed on the first packet stay when
  the trails appear (11 of 2743 move).
- The bundled page's dial stills change and are owed a reshoot.

## Tests

The fault depends on the sky, so a test of one sky proves little.  A
fixture of skies, kept as JSON in `tests/fixtures/` so the test needs
no skyfield and carrying exactly the comets the test page configures:
about 24 of the most crowded Palo Alto skies, each with its second
position ten minutes earlier so the page draws trails, and for the
frame, skies with Proxima due east or west for the wide frame and on
the diagonals at 20-unit type for the narrow.  It is driven through the
real script in one browser session, both frames, the dial REBUILT for
every sky (the remembered spots would otherwise carry from one sky to
the next and the results would depend on fixture order), first with
one packet and then with the second.  Mark radii and trail segments are
read from the drawn elements, as the harness does, never from the
code's own constants.  For every placed name, measured from its ink:

- a touching name sits within `GAP` of its own mark, to 1 unit either
  way; a leadered name at `GAP` plus its tier, to the same 1 unit;
- every other mark passes both clauses of the ownership test from the
  name's real distance, to the same 1 unit;
- every other body's drawn trail keeps 6 from the ink, to the same 1
  unit;
- its padded box hits no other label and stays inside the viewBox.

For every line shown: it starts 1 unit outside its own mark's disc and
ends 1.5 short of its own name's near end, on a spot not level with the
mark; it keeps 6 from every other disc, 3 from every other line and
every other body's stroke, and, past its first 6 units, 3 from its own;
no label crosses it.  The fixture carries each set's latitude, which the
predicted trail needs.  For every ring number shown: 6 from
every disc and trail, 12 from every name and cardinal, 3 from every
line.

The test reads a name's horizontal extent from its anchor and its
`getBBox` width, as the placer does, not from `getBBox`'s own x:
Chromium's box can start up to 1.1 units before the anchor where the
drawn ink reaches at most 0.41 past it.  The 1 unit, stated in the test
with its reason, then covers how far the test's reading can differ from
the placer's.  Those checks read the ink through the same canvas the
placer uses, so they cannot see a canvas that is wrong; how far the
canvas is from the drawn ink was measured against screenshots (above).
Legs that check the guard without trusting the canvas's answer:

- on the bundled page the canvas answer is taken for every name
  (recorded by a wrapped measuring call), so a guard that refuses
  everything fails, and each taken answer lies inside its cell to 0.15
  em;
- a stylesheet the canvas cannot follow, one run each: `text-transform:
  uppercase`, `baseline-shift: 1px`, `stroke-width: 3px` (miter): every
  name falls back to the cell, the stroked ones padded by 6 units each
  side (half the 3-unit width times the default miter limit of 4), and
  every placed name, measured from its padded cell, still passes the
  ownership test;
- a canvas that refuses the face (its font setter wrapped to ignore the
  assignment): every name of that face falls back to the cell.

And per frame, at least a stated number of names are placed (a placer
that drops everything fails).  Legs for the parts the above cannot see,
each asserting the mechanism:

- the order: the Moon's name and then Earth's are placed before any
  other (recorded by a wrapped placement call);
- the canvas font is assigned twice per face per pass (the sentinel,
  then the face), in any measurement order (a wrapped context counting
  assignments, with the queue reversed);
- tails and trails last: on skies where a comet's tail or a name's own
  trail crosses a spot, a name placed on such a spot had no other spot
  passing, in any tier;
- remembered spots: a name whose previous spot still passes is still
  there after a quarter-degree turn, `buildDial` empties the map, and
  Earth's name is never in it (after the Moon has passed, Earth's name
  is back below);
- leader lines: on a sky where a name is refused at all eight touching
  spots, it is placed with a line; no name placed touching shows a
  line, and a dropped name's line is hidden;
- predicted trails: a sky placed on one packet keeps every name where
  it was when the second packet brings the trails, to a stated small
  number of names over the fixture; and with prediction removed that
  number is exceeded (the sabotage);
- ring numbers: one whose first spot is taken moves to the next azimuth
  that passes, and its azimuth holds across a quarter-degree turn;
- the Sun's glow: a name refused only by the glow's radius;
- Earth's mark carries a `<title>`.

Each part is sabotage-checked: remove it, and its leg must fail.  The
9.6.1 legs in
`test_label_boxes_follow_a_size_the_stylesheet_changes_in_a_real_browser`
must pass unchanged.
`test_the_frame_follows_the_drawings_own_width_in_a_real_browser`
asserts that the cardinals, Earth's, the Moon's and the Sun's names are
shown on both frames for its sky.  On this prototype its sky drops four
phone names (Mercury, Jupiter, Saturn, Neptune) and keeps the Moon's
and the Sun's; but its "WHAT THE ORDER GUARANTEES" comment says the
Moon's and the Sun's names "cannot be crowded out", which is no longer
true: the order guarantees only the cardinals, which the pass does not
place, and every other name is placed only where it reads as its own
body's.  The comment is rewritten to say so, and the assertion stays as
what it now is, a pin of what that test's sky shows, not a guarantee.
The added cost is measured and reported.

## Docs and consumers

own-skin.md says the dial "drops one it cannot fit rather than stacking
it"; that is now only half the rule, and it gains the other half: a
name is also dropped when it cannot sit where it reads as its own
body's, beside its mark or at the end of a short line to it, clear of
the other bodies and their trails.  reading-the-page.md, where a reader
looks to learn why a dot has no name, says the same (and why Mercury so
often goes unnamed), explains the dotted line, and says a ring number
may sit at any of eight places around its ring.  The `DIAL_WIDE`
comment, the comments listed after point 12, and changes.md change with
it.  A consuming skin holds its own `copy_once` copy of `celestial.js`,
so re-copying it goes at the top of the release entry as action
required, as in 9.6.1.  A skin's own label sizes need nothing: the
boxes and the ink are measured, as now.  own-skin.md gains four things:
a skin's `text-anchor` on the dial's names has no effect (the placer
writes every name's anchor, point 3); the dotted line beside a crowded
name is `.cel-leader`, restyled like any other mark, and a restyle
should keep it unlike a trail; a stylesheet that gives the names
`text-transform`, `font-size-adjust`, `font-stretch`, a baseline shift,
variation axes or feature settings costs the ink measure: the names are
then measured by their cell, still placed correctly, a little farther
from their marks; and a stroke (a halo) is allowed for, by half its
width, or more at a miter join, so a halo wants `stroke-linejoin:
round`.  celestial.css loses `.cel-earthlab`'s `text-anchor:middle`,
which nothing would read any more, and gains `.cel-leader` on both
plates.

## Settled

Every question this design has raised is settled, 2026-10-26:

1. Points 1-11 as the fix, measuring names to their ink with the
   guarded canvas, `GAP` 3, `TOUCH` 3, `MIN` 6, the order (the Moon,
   then Earth, then most crowded first), comet tails tried last, ring
   numbers at the first of eight places around their ring, and leader
   lines, with the costs measured at the time: the redraw time, ring
   numbers off their usual spoke, Mercury dropped more often than
   today.
2. After the fourth review: leader lines held to the ownership rule
   from their real distance, never level, dotted, clear of other discs,
   lines and trails (point 9); the dial's trails drawn in every
   measurement and treated as obstacles; ring numbers clear of names;
   the guard reading the glyph-moving properties directly and padding a
   stroke (point 1); the tail rule across tiers, with a name's own trail
   counted as its tail (point 8); the order kept name by name (point
   6).
3. After the fourth review's measurements: other bodies' trails kept 6
   units from names (against held to the whole ownership rule, or
   ignored); leader lines kept, under the strict rule (543 / 132 drops
   against 622 / 165 without); the predicted trail from the first
   packet (point 12); ring numbers 12 units from names.

## As built

Built 2026-10-26 into `skins/Celestial/celestial.js` (`placeAll` and
its helpers), with the fifth review's findings folded in: a line's own
strokes (point 9), comet tails as strokes (point 12), the paint-reach
reads (point 1) and the exact tail test (point 8).  The build fixed one
more thing its own test found: a padded name's diagonal spots added
the pad along the diagonal, where a padded box's corner moves by it on
each axis, so a haloed name could sit on its mark.  Measured as the
prototype was (`run_built.sh` in the harness, `results/built/`), the
build against 9.7.2:

- Palo Alto, narrow: 554 dropped (554), 173 on a line; wide: 137 (84),
  87 on a line.  Sydney: 147 (157) and 44 (27).  Proxima east or west:
  114 (86) and 30 (23); on a diagonal at 20 units, 148 (129).  12-unit
  names on a phone: 430 (276).
- No name nearer another mark than its own, touching or leadered, in
  any run; no stroke through a name; no ring number within 6 of a disc
  or stroke.
- Own comet tail through a name 37 narrow / 7 wide, own trail 26 / 12:
  the lines that ran down a tail or along a trail are gone, so those
  names take a touching spot through their own tail, which point 8
  allows as a last resort.
- Per body, narrow / wide: Mercury 151 / 56, the Sun 60 / 12, Venus 80 /
  23, Saturn 93 / 26, Neptune 51 / 1, Hale-Bopp 17 / 3, the Moon 2 / 0,
  Earth 0 / 0.
- Names moving when trails appear: 13 / 5 (Sydney, at its own latitude,
  5 / 3).  A quarter-degree turn: 25 / 11.  An open page against a
  reload: 62 of 321 narrow names elsewhere after 8 hours, 93 of 389
  wide after 2.
- Firefox, every seventh sky: 83 / 16 dropped against Chromium's 80 /
  17 on the same skies.
- Ring numbers: "0.01 au" 149, "1 au" 198, "100" 201, "10⁴" 211 of 211 on
  a phone; every one in every sky on a desk.

