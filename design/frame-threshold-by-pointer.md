# Which drawing shows: a phone rule for phones, a desk rule for desks

Status: BUILT for 9.10, after an independent review of this design; its
findings are folded into the sections below.

## The problem

Every chart is drawn twice, a desk drawing (680 units across, 660 for
the dial) and a phone drawing (360), and the page shows one of them by
the width the chart is drawn at.  The switch comes from
`frame_threshold(label_scale)`, the width at which the desk drawing's
smallest label, 10 units times the set's scale, reaches 11px:

    threshold = 11 x 680 / (10 x scale)     # 623.3px at the default 1.2

11px is a phone rule.  A phone's screen is small and held close, and
that is where smaller text stops reading comfortably.  It says nothing
about a desk, where the screen is farther away and the question is
whether a drawing is near the size it was laid out for.  These charts
are laid out for 10px labels at scale 1.0 and their own size
(weewx-skyfield's stated design), so on a desk the phone rule hands a
reader the phone drawing earlier than legibility asks: a desk window
whose chart column is 567-623px wide gets the 360-unit phone drawing,
when the desk drawing would read at 10.0-11.0px.

## Why the obvious fix is wrong

Lowering 11 to 10 is not the fix.  The switch is decided by the
drawing's WIDTH, and a width does not say whether a phone is showing it:
a phone in landscape gives a column of 600-800px.  At 10px, a phone in
landscape with a 600px column would get the desk drawing at 10.6px,
under the phone rule.  The floor has to follow the device, not the
width.

## The rule

- On a device whose primary pointer is coarse (phones, tablets), the
  floor stays 11px.
- On a device whose primary pointer is fine (a mouse or a trackpad), the
  floor is 10px, the size the charts are laid out for.

The signal is the CSS media feature `(pointer: fine)`, and only a fine
primary pointer takes the desk rule: coarse, none (a television, a
kiosk, a keyboard) and a browser with no `matchMedia` keep the phone
rule, the larger type being the safe answer for a device nothing here
can identify.  The primary pointer is the best of the three signals by
reasoning, not measurement: `any-pointer` would file a touchscreen
laptop as a phone, and `hover` has had vendor misreports.  Chromium's
emulation drives `pointer` and `hover` from one touch flag, so it cannot
tell them apart and proves nothing about real devices.

With a 10px desk floor:

    desk threshold = 10 x 680 / (10 x scale)   # 566.7px at 1.2, 850 at 0.8, 503.7 at 1.35

## The mechanism

1. **celestial_page.py.**  `frame_threshold(label_scale, floor_px=11)`;
   a second constant `DESK_LABEL_FLOOR_PX = 10.0` beside
   `LABEL_FLOOR_PX`.  The fragments are UNCHANGED: `_frames_attr` still
   writes the one phone-rule width, `data-frame-at`, as every release
   since 9.6 has.
2. **celestial.js.**  One predicate, `deskRule()` (a fine primary
   pointer), decides for the charts and the dial alike, and one number,
   `DESK_RATIO = 10 / 11` (the two floors; a test pins it to the Python
   constants), turns a phone width into a desk width.  `fitFrames`
   multiplies each fragment's `data-frame-at` by it where `deskRule()`
   holds; the dial multiplies its `NARROW_BELOW` (623.3) the same way,
   to 566.6 (its smallest label is 12 units in a 660-unit frame: 10.3px
   there).  Because both apply one ratio to the width they already
   have, nothing on a page can take one rule while its neighbor takes
   the other, whatever release wrote the fragments.  Two earlier builds
   carried the desk width as a second attribute and then had to decide,
   per page, whether the fragments were new enough to have it -- first
   by probing the page (two timing holes), then by parsing the station's
   version string -- and both were replaced by this.  The dial's frame
   check is one function, `dialFrameCheck()`, called by its resize
   observer and by the pointer listener.
3. **celestial.css.**  The `@container (max-width: 623.29px)` default
   stays, and a desk rule follows it: `@media (pointer: fine) {
   @container (min-width: 566.7px) { ...wide... } }`, scoped to
   fragments whose `data-frame-at` is the default's `623.3` (any other
   set's desk width is elsewhere, and an unscoped rule would paint a 0.8
   set's desk drawing at 7px labels first), with the
   `data-frame-fit` rules
   outranking both.  Without it a desk window in the band would paint
   the phone drawing first and swap to the desk one at load (the script
   first fits frames from the load event), a jump of 200px or more for
   everything below.  The cost is a third pinned Nu checker error, for
   the second `@container`.
4. **A listener for a pointer change.**  The primary pointer can change
   with the window unmoved (a two-in-one losing its keyboard), and then
   no resize observer fires.  A `matchMedia('(pointer: fine)')` change
   listener re-runs `fitFrames()` and `dialFrameCheck()`; the query
   object it listens on is held for that alone.

## What changes for a reader

Only fine-pointer devices, and only in the band between the two widths.
On the bundled page that band is a desk window about 653-709px wide
(the stacked layout leaves about 86px around the column, measured at
640px: column 554).  Above it nothing changes; below it nothing changes;
a phone or tablet changes nothing anywhere.  A consuming skin's set
moves in proportion to its scale (1.35: 554 -> 504).

## What does not change

- The phone rule and every phone or tablet.
- The fragment files and the slot walk: a 9.10 page reads 9.9's
  fragments and a 9.9 celestial.js reads 9.10's, since they are the
  same bytes.
- A skin that re-copies only one of celestial.js and celestial.css is
  not supported; the release entry says both move together.

The label layers DO change on a desk: a set's `narrow_media` layer is
reachable wherever the desk drawing shows, which is now lower on a desk
(567px at the default scale, not 623px).

## Tests

- Python: `frame_threshold` at both floors for 0.8, 1.2, 1.35, 1.4; every
  two-drawing fragment carries `data-frame-at` and nothing new; a lone
  frame carries none.  The script's `DESK_RATIO` is pinned to the two
  Python floors, and the stylesheet's desk width to `frame_threshold`
  at the desk floor.
- Browser (`test_a_desk_keeps_its_desk_drawing_longer_than_a_phone_
  in_a_real_browser`), on the bundled page, whose stacked layout gives
  the dome, the pass chart and the dial one column: a pixel or two
  either side of each threshold (565/568 on a fine pointer, 622/625 on
  a coarse one, `has_touch=True` in Chromium), reading which drawing is
  DISPLAYED rather than the verdict attribute, the dial agreeing with
  the charts, and every label shown clearing the device's floor.  Then
  the stylesheet alone on both devices, and a pointer change with the
  window unmoved.  Each mechanism is sabotage-checked.  Cost: about 6 s
  net on a Pi (a browser launch and six page loads; the page render it
  shares with two other tests is made once per process).

## Docs

configuration.md, own-skin.md and how-it-stays-live.md state the
thresholds (623px at 1.2); each gains the desk number and the pointer
rule.  own-skin.md now tells a consuming skin to key chrome that should
change with the drawings to the wrapper's `data-frame-fit`, since the
width differs by device and by set; a `@container` query at the
stylesheet's widths is the no-javascript fallback.

## Release

A behavior change a reader can see: 9.10.  Re-copying celestial.js is
needed for an embedding skin to get it; without it, nothing changes.

## Settled

1. The desk floor is 10px, the size the charts are laid out for.
2. The signal is a fine primary pointer; anything else keeps the phone
   rule.

## Measured before building

A desk browser at fourteen window widths from 700 to 1920px, on the
bundled page and an embedding skin's pages, found real layouts in the
band: the embedding skin's pass chart (scale 1.35) at 534-547px in
1000-1024px windows, its Geocentric dial at 572px in an 1100px window,
and the bundled page's three charts at 614px in a 700px window.  Each
showed the phone drawing where the desk drawing would read at
10.4-10.9px.
