# Drop-in panels

A design for making every panel of the Celestial page usable in another
skin the way weewx-skyfield's `$sky_page` panels are: a search list, a
stylesheet, a script, and nothing copied.  Written 2026-08-29, before
anything is built; the decisions it needed were taken the same day and
are recorded at the end.

## The problem

weewx-skyfield's manual says "three things to arrange" and a panel is one
Cheetah call.  Celestial's manual says there is no supported way to reuse
its panels at all, and the one consumer that tried -- weewx-liveseasons --
shows what that costs:

| liveseasons file | lines | what it forked from celestial |
|---|---|---|
| `celestial_today_updater.inc` | 1,239 | Geocentric dial, roster, comets, countdown row |
| `celestial_stars_updater.inc` | 1,349 | dome slot walk, satellite marks, stale line |
| `celestial_satellites_updater.inc` | 661 | pass chart |
| `dome-svg*.txt.tmpl`, `dome-svg-frag.inc`, `pass-chart*.txt.tmpl` | 24 files | two fragment sets (desktop and smartphone label scales) |

The three updaters were forked whole from celestial 8.0 and hand-patched
since (their provenance markers still name 4.0, 7.0 and 8.0).  Only
430-460 lines of each still match celestial verbatim.  The divergence is
not design: the stars fork's slot-0 fallback carries an after-the-fact
justification where celestial clamps to `count - 1`; the countdown is a
different function (`fmtCountdown(ts, nowTs)` against `fmtDHMS(sec)`), so
the 8.1-8.3.5 chip rulings were re-derived rather than carried; and
8.3.4, 8.3.5 and 8.4 each became a separate liveseasons release with
its own review rounds.  It was too hard to keep them in sync, so they
drifted.  Every celestial fix is paid for twice and the two are no longer
the same program.

A third skin copying the page inherits all of that and none of the tests.

## Why it is possible now

Two things landed this month that were preconditions:

- **celestial 8.5 / weewx-loopdata 7.0.**  Each report declares its own
  fields and reads its own entry in `loop-data.txt`.  Before 8.5 a
  second skin reading celestial's fields worked only by riding the one
  global fields line; now a consumer report can declare exactly the
  groups a panel needs and get its own entry, in its own language.  That
  is the data leg of a drop-in, and it exists.
- **8.3.4-8.4** settled the behaviour that was still moving: one clock
  (the loop packet's own timestamp), the dome slot walk's three guards,
  the stateless pass render.  The javascript has stopped churning, which
  is when it becomes worth freezing behind an interface.

## Why skyfield's model does not transfer as it stands

`$sky_page.dome_svg($almanac)` works because skyfield's panels are
report-time strings: colors inline, one call, done.  Celestial's panels
are live.  Each one is four things, and a string-returning method can
ship only the first:

1. **Markup** with a first paint from `$almanac` (guarded per cell, so a
   lesser almanac leaves cells empty rather than failing the page).
2. **A loop-field declaration** -- the groups loopdata must evaluate for
   the report that shows the panel.
3. **Javascript** that owns a set of DOM ids and moves them from the
   report's `loop-data.txt` entry.
4. **CSS** -- every color, both plates, and the SVG label classes kept in
   step with `sky.css`.

The dome adds a fifth: the **staggered fragment set** (`dome-svg.txt`,
`dome-svg-1..9.txt`) with the wrapper protocol
(`data-dome-ts/-slot/-step/-count/-interval/-palette`) that the page walks
to step the sky between cycles.  It is in scope; it is the part that
actually broke in two places (8.4 and liveseasons 8.4.6 fixed the same
slot-count arithmetic separately), so it is the part that most needs one
owner.

The contract therefore has to cover all five legs per panel, and the
consumer must be able to take a subset of panels.

## The design

### `$celestial`: a real search list

A new module, `bin/user/celestial_page.py`, exposing `$celestial` --
weewx-skyfield's pattern exactly: a `SearchList` whose object holds the
report's skin_dict and renders each panel from an almanac passed in.
Each render method wears a `_panel_guard`, so a failure costs its own
panel and is logged, never the page.

```
$celestial.config_script()              the page-level script block (see below)
$celestial.countdown_html($almanac)     the chip row
$celestial.geocentric_html($almanac)    dial + roster (comet rows included)
$celestial.dome_html($almanac, set='') the dome, its self-describing wrapper, the stale line
$celestial.dome_roster_html($almanac)   the any-pass satellite roster
$celestial.pass_html($almanac, set='')  the Next Visible Pass chart + its roster
$celestial.theme_class($almanac)        'theme-dark' or 'theme-light', for the consumer's root element
$celestial.footer_html($almanac)        the truthful credit
```

As built (step 4), the table above differs in three places.
`pass_html` is the chart and its caption alone and the visible-pass
roster is `pass_roster_html($almanac)`, its own call like the dome's
(decision 3 below, taken after the table was written).
`pass_panel_hidden($almanac, set='')` is a predicate: whether the pass
panel has nothing to show at this instant -- no chart, no roster row --
which is when the bundled page first-paints the section around the
panel `hidden` (celestial.js hides and unhides an element with id
`pass-sec` the same way; the id is optional for a consumer).  And
`theme_class` returns `'theme-dark'` or `'theme-light'`, the class the
stylesheet's plates hang on, never ''.  `footer_html` is the whole
credit line, the loopdata credit included.  The two grids that put a
chart beside its roster (`.domepanel`, `.passpanel`) are the bundled
page's chrome, like its sections.

The roster, chips, dome section and pass section move from
`index.html.tmpl` into Python.  That is the biggest single piece of work
(some 650 lines of guarded Cheetah), and it is the piece that makes the
panels callable at all: a `.inc` can only be `#include`d by a path
relative to the consumer's own skin directory, so shipped includes are
not drop-in.  Python is what skyfield does, and skyfield's `_panel_guard`
and `_t` give per-panel failure containment and gettext-style
translation for free.  The `#errorCatcher Echo` traps (no `$(a if b else
c)`, no hex literals, `*/` in comments) vanish with the templates.

The fragments the dome and pass panels refetch are not search-list
methods: they are written by a generator, below, from the same Python.

`celestial_sky.py`'s shim is unchanged: presence detection is its only
job and `$celestial` obtains the real `SkyPage` through the same
import.  A consumer names `user.celestial_page.CelestialPanels` in its
`search_list_extensions` and gets `$celestial` and `$sky_page` both.

As built (step 3): `countdown_html` returns the chip row from its
`#countdown` root, and `geocentric_html` the dial and roster from the
`.geo-body` root, preceded by the panel's install hint when no extended
almanac serves it -- the hint is the panel's own degraded state, so a
consumer gets it too, and it is a sibling BEFORE the root, outside it,
by design: the root is what the script finds, the hint is prose.  The `<section>` and its `<h2 class="eyebrow">`
stay in the template: they are chrome, exactly as skyfield's page keeps
its own section headings around each `$sky_page` call, and a consumer
chooses its own.  The panels' markup is nested from their own root, not
indented for the bundled page, so the rewrite gate below compares the
rendered page with leading whitespace normalized.  The
`data-celestial` version marker on the panel roots (the contract,
below) lands in step 5 with the consumer fixture that proves it, on all
the roots at once (as built: the countdown row, `.geo-body`,
`#dome-wrap`, `#pass-wrap` and each satellite roster -- six on the
bundled page; the footer is text and has none).  The template resolves `$celestial` once at the top
of `<body>` and tests it at each call (`#if $panels`), so a station
whose `weewx.conf` still overrides `search_list_extensions` with the
pre-9.0 shim gets a page without the panels rather than an echoed tag;
render-time failures are `_panel_guard`'s alone.

### `celestial.js`: one static, versioned script

`realtime_updater.inc` is Cheetah for one reason: it bakes values into
the script.  Everything it bakes is listed here, and it is all
configuration:

| baked today | source |
|---|---|
| `page_update_pwd`, `refresh_rate`, `expiration_time`, `time_zone` | `[Extras]` |
| `STATION_LAT` | `$station` |
| `GEN_TS` | `$almanac.time_ts` |
| `PER_AU`, `DIST_LABEL` | `$unit` (windrun stands in for group_distance) |
| `LOCALE` | `$lang` |
| `BODY_LABELS` | the report's `[Almanac]` texts |
| `CARDINALS` | the formatter's ordinates |
| `T` | 60-odd `$gettext` strings |
| `SAT_NAMES`, `COMET_NAMES` | `$sky_page` |
| `$REPORT_NAME`, `$Extras.loop_data_file` | the feed |

Everything after that -- the other 2,900 lines -- is static javascript.
So the split is:

- **`celestial.js`**, shipped by `CopyGenerator` like `sky.js`, wrapped in
  one function scope, publishing exactly one global, `celestial`, with
  one method, `celestial.start(config)`.  No top-level `var` can collide
  with `window` any more (the `var history` class of bug is closed by
  construction).  The file carries its version; `start` logs a mismatch
  against the config's version.
- **`$celestial.config_script()`** emits a `<script>` block that builds
  the config object from the table above -- through `json.dumps`, so
  html_entities encoding cannot touch a non-ASCII label -- and calls
  `celestial.start(...)`.  The consumer page carries `<script
  src="celestial.js?v=..." defer>` and one `$celestial.config_script()`
  call; the version-tagged URL stays, because browser caches were the
  real stale-script hazard.

  As built (step 2): `config_script($almanac)` -- it takes the almanac
  like every other panel method, since the generation instant, the
  station latitude, the [Almanac] names, the formatter and the
  converter all come from it.  And the tag is NOT deferred: `start()`
  arms the loop poll, and the parse-time paths the script keeps
  (`renderWanted`, `domeRefetchWanted`) exist precisely because a
  packet can land before the panels have parsed; deferred, `start()`
  would run only after parsing and those paths would never run, which
  is a behavior change the gate below forbids.  So the consumer writes
  `<script src="celestial.js?v=..."></script>` in `<head>` and the
  config call at the top of `<body>`, before the panels.  The config's
  keys (18 since step 4) are the contract and a test pins them both
  ways against the `config.<key>` reads in the file.  `GEO_BODIES` and
  the chip window stay literals in the file pinned to the Python by a
  source test (a step-3 review question, decided at step 4): they are
  not per-report values, and the config carries only those.

**Panel discovery by DOM presence.**  Each render function returns at
once when its root element is absent (`#countdown`, `#dial`, `#dome-svg`,
`#pass-chart`, the roster ids).  The dome and pass paths already do this
(`getElementById` guards at the top of `domeSvg`, `domeFragMeta`,
`refreshDome`, `passSvg`, `refreshPass`); the dial and the countdown do
not yet.  With every render guarded, a page holding any subset of
panels runs the one script with no per-panel wiring -- which is what
liveseasons' five tabs need and why they forked.

**Fragment names become config.**  Today the fragment names are
literals relative to the page URL (`dome-svg-3.txt`, `pass-chart.txt`).
The config carries the prefix of the fragment set the page embeds
(default `dome-svg`, so the sample skin's URLs do not change), taken
from the set the page named in its `dome_html` call -- liveseasons'
`dome-svg-sp` twin becomes a set name instead of a forked constant.

As built (step 4): NOT config.  The config block is emitted at the top
of `<body>`, before the `dome_html(set=...)` call it would have to
follow -- Cheetah renders top-down -- so either the consumer names the
set twice or the keys stay default (step 2's review found this; step 4
decided it).  Instead the panel's own markup names its files, from the
set it was rendered for: `data-dome-prefix` on `#dome-svg` (the swap
target, which a refetch never replaces) and `data-pass-fragment` on
`#pass-chart`.  celestial.js reads them at fetch time, and a page
without a dome or a chart fetches nothing for it.  The two config keys
(`dome_prefix`, `pass_fragment`) of steps 2-3 are gone; the config's
19 keys are the contract, `theme` and `root` among them -- the theme the page was
generated on, which the script compares each refetched fragment's
`data-page-theme` with, so a consumer's chrome owes the script no root
class.  The flip itself is judged the same way: every fragment
carries the REPORT's theme it was written on (`data-page-theme`, on
the dome's wrapper and on the pass chart's `.passfrag` wrapper alike,
an empty chart included), the script compares it with the config's
`theme`, and a fragment from the other one reloads the page once per
plate, and never again if the page comes back still disagreeing (a
stale copy).  The page and its fragments take the same record as their
instant: the fragment generator uses the cycle's own, which the page's
generator found as the last good stamp unless a record committed while
it was already running -- so short of that the two are never written
on different sides of sunrise, and that case costs one reload, not a
stuck plate.
The fragment set's own
plate (`data-dome-palette`, `data-pass-palette`) takes no part in
that: a set on a plate other than the page's is never a flip.  It is
what `celestial.css` scopes its plate tokens by -- on the fragment's
SVG, and only when the set's plate differs from the page's, so a
same-plate page inherits `:root` and a consumer's token override
reaches the charts -- because skyfield colors its charts inline but its
labels by class, and those classes would otherwise wear the page's
plate; the pass chart's head line is HTML on the page's surface and
keeps the page's.  A page names no set and the skin declares none on
the `dome-svg` prefix, or names one the skin does not declare: the dome's
place carries a line saying so and the log one line per cycle.

### The fields: still a declaration, now with a consumer hook

The static half of a panel's fields is a `[LoopData] [[fields]]` group in
the consumer's own `skin.conf`, pasted from the manual, exactly as the
Celestial skin ships its own.  The manual prints the groups **per
panel**, and the existing `TestManualInStepWithCode` test pins the print
to the skin.conf, so the paste cannot go stale.  This is the right home:
a skin's `skin.conf` deploys with the skin, so a consumer's field set is
a skin edit, nothing per machine.

The dynamic half -- the `satellites` and `comets` groups, which follow
the station's `[Skyfield]` sets and no shipped file can know -- needs a
way to reach a consumer report.  The proposal: the consumer's report
stanza in `weewx.conf` carries

```
[StdReport]
    [[MyReport]]
        skin = MySkin
        celestial_panels = dome, pass
```

and `celestial_reports()` returns every report that either runs the
Celestial skin or carries `celestial_panels` naming a panel that reads
satellite or comet fields.  `declare_page_fields`, the installer's
`configure` hook and the `--add-`/`--remove-satellite`/`-comet` verbs
then maintain that report's two groups exactly as they do a Celestial
report's -- one code path, nothing to keep in agreement.  A consumer
whose panels read no dynamic fields (countdown only, say) sets nothing.
As built (step 5): every panel reads a dynamic group -- the countdown
row's pass chip reads the satellites and its perihelion chips the
comets, the Geocentric's comet layer the comets, the dome and the pass
panel the satellites -- so the key names the panels the page embeds and
the report gets exactly the groups those panels read, never a group a
panel of its does not.  On any report carrying the key the two group
names are this extension's, replaced or removed wholesale on every run
(a group of the owner's own belongs under another name; a removal
because no named panel reads the group is reported as that).  A name
that is not a panel costs that report its declaration and nobody
else's -- the section is skipped and named, every run -- and the key is
refused under `[[Defaults]]`, which WeeWX merges into every report.
The page asks the same question at generation: `$celestial` asks
`report_groups` of the generator's `config_dict` -- the installer's
reader on the installer's file, never the merged skin dict, into which
WeeWX would fold a key from `skin.conf` or `[[Defaults]]` that the
installer never sees -- and a panel whose groups the named panels do
not cover carries a line before its root saying so, with a weewxd log
line, so the misdeclaration is visible where it bites.  The line rides
the dome and the chart, not their rosters (parts of the same panel),
and `pass_panel_hidden` counts it as something to show -- as does the
script's own hide rule for the section, the same rule applied live.
A panel named but not yet written carries a second line saying what
to run: the page asks the writer's own dry run (`pending_groups`),
never a second reading of what the report should carry.  A key naming
nothing is a consumer owning nothing (both groups removed, reported); a
section where the line belongs, and a key under `[[Defaults]]` or at
`[StdReport]`'s top level, are refused per report, in one function
(`report_groups`) both sides ask, so the installer's receipt and the
page's line say the same thing.  Every receipt is a sentence
`celestial.py` owns (`receipts`) that the installer and the verbs
print verbatim.

The key lives in `weewx.conf`, not the consumer's `skin.conf`, because
the installer and the CLI read `weewx.conf` and nothing else; resolving
another skin's `SKIN_ROOT` from `install.py` is a dependency this
extension should not take on.

### The fragments: a generator in the consumer's own report

The dome's staggered set belongs to the report whose page walks it: its
theme, its language, its `[Almanac]` names, its `HTML_ROOT`, and the
instant its page was generated for.  Today the CheetahGenerator writes
the set, one template per output file, and a template resolves relative
to the skin that lists it -- so a consumer skin cannot point at
Celestial's templates, and copying eleven files (liveseasons:
twenty-two) is what we are trying to end.  A first draft of this design
moved the set to a separate `CelestialDome` report.  That made every
`(theme, label_scale, lang)` combination a stanza of its own, whose
theme and language a user keeps in agreement with the page by hand,
with `theme = auto` in step only if every stanza said so -- and it
exempted the sample skin, which kept its own templates.  Rejected.

WeeWX's extension point for "this report writes files" is the
**generator list**: `CheetahGenerator`, `ImageGenerator` and
`CopyGenerator` are all `weewx.reportengine.ReportGenerator` subclasses
that a skin names in `[Generators] generator_list`.  Celestial ships one
more, `user.celestial_page.FragmentGenerator`, and a consumer adds it
to its own skin's list:

```
[Generators]
    generator_list = weewx.cheetahgenerator.CheetahGenerator, user.celestial_page.FragmentGenerator, weewx.reportengine.CopyGenerator
```

It runs inside the consumer's report, with everything the report
engine hands a generator: the merged `skin_dict` (theme, lang,
`[Almanac]` texts, `[Texts]`, `HTML_ROOT`), `gen_ts`, `stn_info`, the
archive record and a `db_binder`.  From those it builds the report's
almanac exactly as the CheetahGenerator's own `Almanac` search list
does, resolves the palette once against that almanac at the page's own
generation instant -- so `theme = auto` agrees with the page by
construction, there being one option and one instant -- and writes the
ten dome fragments and the pass-chart fragment into `HTML_ROOT`, each
through a temporary file and a rename, so a page's refetch never reads a
half-written sky.  The archive interval comes from the record it is
given, in seconds explicitly (the `group_interval = hour` trap of issue
#4 stays fixed), and the slot geometry from **one Python function**,
`dome_slots(interval_s) -> (interval, step, count)`, which `dome_html`'s wrapper
reads too.  The arithmetic that was fixed twice lives once, and the two
wrappers cannot disagree because there is no second copy.

**The set is the unit of agreement.**  A skin that needs more than
one set -- liveseasons' desktop and smartphone label scales -- declares
them in its own `skin.conf`, beside `[CheetahGenerator]` and
`[CopyGenerator]`, the way `[ImageGenerator]` declares its plots:

```
[CelestialFragments]
    [[desktop]]
        label_scale = 0.8
        theme = dark
    [[smartphone]]
        prefix = dome-svg-sp
        label_scale = 2.2
        theme = dark
```

and the page names the set it embeds: `$celestial.dome_html($almanac,
set='smartphone')`, `$celestial.pass_html($almanac, set='smartphone')`.
The first paint, the ten fragments, the pass chart and the config's
prefix then all come from one declaration and cannot disagree.  Each
set carries:

- `prefix` -- the fragment file names (`<prefix>.txt`,
  `<prefix>-1..9.txt`, `<prefix>-pass.txt`); default `dome-svg`, whose
  pass fragment keeps today's name `pass-chart.txt`.
- `label_scale` -- passed through to skyfield's `dome_svg` and
  `pass_chart_html`; default 1.0.
- `theme` -- `dark | light | auto`, spelled exactly as the report option
  is; default the report's own `theme`.  `auto` resolves at the page's
  generation instant like everything else, so a set on `auto` flips
  when the page does and never in between.
- `directory` (step 5) -- where under the report's `HTML_ROOT` the
  set's files are written; default `HTML_ROOT` itself.  The page may
  sit anywhere under `HTML_ROOT`, and the skin may keep its assets
  anywhere: the page passes core's `$filename` -- its own path under
  `HTML_ROOT`, a core search-list tag on 5.2 and later -- to
  `config_script`, the config block carries the page's route up to
  `HTML_ROOT` (`root`, `../` per level), and the script fetches every
  fragment from `root + <directory>/` -- the panel's markup carries
  the directory (`data-dome-dir`, `data-pass-dir`) for that.  Nothing
  is inferred: the generator states where the page is.  (Step 5's
  review replaced three earlier designs in turn: fetching relative to
  the page, which required the page to sit beside its set; locating
  `HTML_ROOT` from the script's own URL, which a `js/` asset layout
  broke; and stripping the `copy_once` path from that URL, which read
  one of the four spellings `copy_once` accepts.  `$filename` was
  there all along.)  A page that passes no `$filename` fetches
  relative to itself, right when it sits beside its set.  A plain
  relative path only (no leading slash, no `..`);
  prefixes stay unique across sets whatever their directories, so a
  page naming no set has one set on the `dome-svg` prefix to follow.  A
  directory that cannot be made costs that set its files, named in the
  log, and no other set its cycle.

No section at all means one set, `dome-svg`, at scale 1.0 on the
report's theme -- which is what the sample skin wants, so its
`skin.conf` gains the generator and nothing else.  A page that names no
set gets that default.  There is no second report, no second stanza and
no `label_scale` on a report that has no page; the one thing a consumer
keeps in agreement is the set name in the call and the section, and a
call naming a set the section does not declare is refused at generation
time with the set's name in the log, not answered with the default.
As built (step 4): a call naming no set gets the set on the `dome-svg`
prefix -- the default set on a skin that declares none, or whichever
declared set holds that prefix, at that set's scale and theme -- and is
refused the same way when the skin declares sets but none on that
prefix.  So a declared set may take the default prefix at any scale or
theme (step 1 refused that until the page could follow a set).

A set's `theme` chooses the plate for the panels **skyfield draws** --
the dome and the pass chart, whose colors are inline in the SVG.  It
is what lets a light site carry a night dome, which is liveseasons
today (`palette='night'` written into a light page).  The panels
celestial draws -- the dial, the roster, the chips -- take their colors
from `celestial.css` tokens switched by the `theme-light` class on the
root element, so they follow the page, not a set.  A night dial beside
a light dome on one page is therefore possible only by scoping those
tokens on a wrapper, which is a stylesheet edit on the consumer's side
and not a contract point; the manual says so rather than implying
per-panel theming is uniform.

The sample skin uses the same generator.  Its eleven fragment templates
and `dome-svg-frag.inc` are deleted; the file names it writes are
unchanged, so `dome-svg.txt` stays where a page opened before the
upgrade is refetching it.  The design no longer exempts its own
reference implementation.

The cost is the almanac.  The CheetahGenerator builds it from `gen_ts`
(falling back to the archive's `lastGoodStamp`), the record's
temperature and pressure when one lies within an hour, the station's
altitude in meters, the skin's `[Almanac]` texts, and a formatter and
converter built from the skin_dict; the generator must build the same
one, and a test pins the two against each other for the same instant
(`time_ts`, the sun's azimuth, a body's translated label).  As built, the
generator does not re-implement that search list at all: it sets a
formatter and converter on itself and constructs core's
`weewx.cheetahgenerator.Almanac` directly, so whatever a WeeWX version
passes (5.2 has no `texts` keyword, measured on the 5.2.0 wheel; 5.3+
does) comes for free and the 5.2 floor holds by construction.  It is
also a new kind of component for this extension: report-time, inside
the report thread, so the README's "no service" line stands.

### The CSS

`celestial.css` is already shipped `copy_once` and already holds every
color for both plates.  A consumer copies it (or links to the Celestial
report's copy) and loads `sky.js` for tap tooltips, as skyfield's
`panels.md` already tells its consumers.  The theme is a class on the
consumer's root element, from `$celestial.theme_class($almanac)`.  The
SVG label classes stay byte-in-step with `sky.css`; the in-step test
stays.

A consumer restyles the panels celestial draws by redefining tokens.
Every color outside skyfield's SVG is a custom property on `:root` in
`celestial.css` -- the 22 of them, `--night`, `--vault`, `--ink`,
`--brass`, the per-body `--e-*` set -- and every rule reads them through
`var()`; the dial's marks reach their colors through `fill-*`/`stroke-*`
classes and no literal appears in markup or javascript.  So a consumer
stylesheet loaded after `celestial.css` redefines whatever it likes
(`:root { --night: #e3e3e3; --brass: #367ba3; }`) and the dial, roster,
chips, badge and stale line follow.  The token names are therefore
contract, additive-only like the DOM ids, so a consumer's overrides
survive an upgrade.  Skyfield's own marks are outside this: their colors
are the set's `theme`, above.

### The contract

- Every panel root carries `data-celestial="<version>"` (a panel's
  install hint is a sibling before its root, not inside it); the config and
  the script each carry the version.
- Inside a major version, additive only: DOM ids, config keys, the
  fragment wrapper's data-attributes, the field group names, the
  `[CelestialFragments]` set keys, the `celestial.css` token names and
  the public method signatures never change meaning or disappear.  A panel
  may gain marks, keys and classes; `changes.txt` names each, as
  skyfield's does.
- What is NOT contract: the internals of `celestial.js`, the shape of
  the SVG the dial builds, the roster's inner spans.  A consumer that
  reaches past the root ids is on its own, and the manual says so.
- The skyfield coupling (the `data-body` marks, the fragment palette, the
  label classes) is not removed.  It moves behind celestial's tests,
  where a consumer inherits it instead of copying it -- which is the
  whole point.

## What the consumer writes

Modeled on skyfield's "three things to arrange":

1. `search_list_extensions = user.celestial_page.CelestialPanels` in the
   skin's `skin.conf`.
2. The panel's `[LoopData] [[fields]]` groups, pasted from the manual,
   in the same `skin.conf`; `celestial_panels = ...` in the report's
   `weewx.conf` stanza if any panel reads satellites or comets.
3. `celestial.css` and `sky.js` copied in; `<script src="celestial.js"
   defer>` and `$celestial.config_script($almanac, $filename)` in the
   page (as built: not deferred, and `$filename` -- core's, the page's
   own path -- tells the script where the fragments are); the panel
   calls wherever the panels go.
4. For the dome and pass panels: `user.celestial_page.FragmentGenerator`
   in the skin's `generator_list`; a `[CelestialFragments]` section only
   if the skin wants more than one set, or a set on a theme other than
   the report's, with the page's `dome_html`/`pass_html` calls naming
   the set.

A page showing only the countdown row is steps 1-3 and one call.

## What the files look like

### Celestial's own `skin.conf`, after

Comments stripped.  Against today's file: the search list is the new
module, `celestial.js` joins `copy_once`, the eleven fragment entries
leave `[[ToDate]]`, and the generator joins the list.  The `[LoopData]`
groups are untouched.

```
lang = en
theme = dark

[Extras]
    version = 9.0
    loop_data_file = '../loopdata/loop-data.txt'
    refresh_rate = 2
    page_update_pwd = 'foobar'
    expiration_time = 24

[LoopData]
    [[fields]]
        clock = current.dateTime.raw
        sun = almanac.sun.az, almanac.sun.alt, almanac.sun.earth_distance
        ...                                  # the twenty groups of 8.5, unchanged
        eclipse = almanac.next_eclipse.unix_epoch.raw, almanac.next_eclipse_kind

[CheetahGenerator]
    encoding = html_entities
    search_list_extensions = user.celestial_page.CelestialPanels
    [[ToDate]]
        [[[index]]]
            template = index.html.tmpl

[CopyGenerator]
    copy_once = celestial.css, celestial.js, sky.js

[Generators]
    generator_list = weewx.cheetahgenerator.CheetahGenerator, user.celestial_page.FragmentGenerator, weewx.reportengine.CopyGenerator
```

No `[CelestialFragments]` section: the default set is `dome-svg` at
scale 1.0 on the report's theme, which is what this page has always
embedded, and `index.html.tmpl` calls `dome_html($almanac)` and
`pass_html($almanac)` with no set.  `user.celestial_sky.CelestialSkyPage`
leaves the list because `CelestialPanels` publishes `$sky_page` through
the same guarded import; the shim module stays shipped for any other
skin that names it.

### Celestial's `weewx.conf` stanza, after

Identical to 8.5's.  The installer's `CONFIG` string does not change: no
new option, no second report, and the `[[[LoopData]]] [[[[fields]]]]`
groups are written by `configure()` exactly as today.  That is the
claim the generator design was chosen for, and it is checkable by
diffing `install.py`.

```
[StdReport]
    [[CelestialReport]]
        #lang = en
        #theme = dark
        HTML_ROOT = celestial
        enable = true
        skin = Celestial
        [[[Extras]]]
            loop_data_file = ../loopdata/loop-data.txt
            #refresh_rate = 2
            #expiration_time = 24
            #time_zone = America/New_York
            page_update_pwd = foobar
        [[[LoopData]]]
            [[[[fields]]]]
                satellites = almanac.iss.az, almanac.iss.alt, ...     # written by configure()
                comets = almanac.halley.az, almanac.halley.alt, ...   # written by configure()
```

### A consumer, in liveseasons' shape

Its `weewx.conf` stanza gains one key, and the installer then keeps the
two dynamic groups under it as it does for `[[CelestialReport]]`:

```
[StdReport]
    [[LiveSeasonsReport]]
        HTML_ROOT = public_html
        skin = LiveSeasons
        celestial_panels = dome, pass
        [[[LoopData]]]
            [[[[fields]]]]
                satellites = almanac.iss.az, almanac.iss.alt, ...     # written by configure()
                comets = almanac.halley.az, almanac.halley.alt, ...   # written by configure()
```

Its `skin.conf` gains the search list, the generator, the stylesheet
and script in `copy_once`, the pasted groups for the panels it shows,
and -- because it wants two dome sizes on a night plate inside a light
site -- a two-set `[CelestialFragments]` section:

```
[LoopData]
    [[fields]]
        ...                                  # its own 22 groups, as today
        sun = almanac.sun.az, almanac.sun.alt, almanac.sun.earth_distance
        ...                                  # the groups the manual prints for the dome and pass panels

[CelestialFragments]
    [[desktop]]
        label_scale = 0.8
        theme = dark
    [[smartphone]]
        prefix = dome-svg-sp
        label_scale = 2.2
        theme = dark

[CheetahGenerator]
    search_list_extensions = user.nws.NWSForecastVariables, user.xtide.XTideVariables, user.celestial_page.CelestialPanels

[CopyGenerator]
    copy_once = ..., celestial.css, celestial.js, sky.js

[Generators]
    generator_list = weewx.cheetahgenerator.CheetahGenerator, user.celestial_page.FragmentGenerator, weewx.reportengine.CopyGenerator
```

and its Stars tab embeds `$celestial.dome_html($almanac,
set='desktop')` with the smartphone variant naming `'smartphone'`.  Its
twenty-two fragment templates and the `[[ToDate]]` entries that listed
them go.

## The sample skin becomes the first consumer

`skins/Celestial/index.html.tmpl` is rewritten to use nothing a consumer
cannot: the header and footer chrome stay Cheetah, every panel is a
`$celestial` call, the script is `celestial.js` plus the config block,
and the fragments come from the generator.  `realtime_updater.inc`, the
eleven fragment templates and `dome-svg-frag.inc` are deleted.

The gate for that rewrite is that the page does not change: the render
tests, the eighteen real-browser tests and the Nu validation all run
unmodified, and a one-off golden diff of the rendered HTML before and
after (leading whitespace normalized) catches anything the tests do
not pin.
The dome-slot, pass-sweep, freeze and stalled-feed browser tests are the
ones that matter most; they drive the exact code that moves.

## Liveseasons is the acceptance test

The design is done when liveseasons can delete its three updaters and
twenty-four fragment files and replace them with the four steps above
(a two-set `[CelestialFragments]` section for its two label scales), and its tabs
then behave like current celestial -- which is better than they behave
today, since every fix since 8.0 arrives at once.  Whatever liveseasons
loses in that swap it never chose to have.  That conversion is done
BEFORE celestial 9.0 is cut, against the unreleased 9.0 on the
dogfooding instances, and what it finds is fixed here first: shipping
the interface before its one real consumer has been built against it
would be shipping it untested (John, 2026-08-30, correcting this
paragraph's original "after celestial 9.0 ships").  Nothing in this
design needs a liveseasons-specific option, and none is proposed.

## Tests, new and moved

- `dome_slots` pinned across the thirteen intervals (ported from
  liveseasons' `test_the_count_declared_is_the_count_emitted`), replacing the two-place
  arithmetic test.
- `celestial.js` contains no Cheetah (`$`, `#` outside comments) and
  declares exactly one global.
- The config block's keys pinned as the contract; every `T` key still
  read out of the Python source and tied to `lang/en.conf` both ways
  (the regex moves from the `.inc` to the `.py`, the way skyfield's
  test reads `_t` calls).
- The generator's almanac pinned against the CheetahGenerator's for the
  same instant, and its ten dome fragments and pass-chart fragment
  pinned byte for byte against what the 8.5 templates wrote for that
  instant -- a golden captured once, before the templates go.
- The generator on a `skin_dict` with no `[CelestialFragments]` writes
  the one default set; with two sets, two prefixes; a set whose
  `prefix` collides with another's is refused at startup, not at the
  tenth write; a set on `theme = light` writes paper fragments beside a
  dark page, and `dome_html(set=...)` first-paints the same plate the
  set's fragments carry.
- `dome_html` naming an undeclared set (or none, on a skin declaring
  none on the `dome-svg` prefix, or a bad section) renders a line in the
  dome's place saying so and logs the name once per cycle; the pass
  panel and both rosters of that set render nothing.
- A minimal consumer skin fixture under `tests/`, using only the public
  surface, rendered and driven in the browser -- the one test that
  proves the contract from the outside.  Skyfield has no such test;
  this one should.
- Everything that exists stays, unmodified where the design has done its
  job.

## Sequencing

Six steps, roughly, each leaving the tests green:

1. `celestial_page.py` with `dome_slots`, `_panel_guard`, `_t`, the
   config block and `theme_class`; `FragmentGenerator`, its almanac
   pinned against the CheetahGenerator's and its output against the
   golden; the sample skin lists it and its twelve template files go.
2. The script split: `celestial.js` + `config_script()`; the sample page
   switches over; golden diff clean; browser tests green.  (As built,
   `realtime_updater.inc` goes here, not in step 4: the include was the
   script and nothing else.)
3. `countdown_html` and `geocentric_html`: the chip row and the roster
   move to Python; sample page switches; golden diff clean.  (As built:
   the section chrome stays in the template; see the `$celestial`
   section above.)
4. `dome_html`, `dome_roster_html`, `pass_html`; `realtime_updater.inc`
   deleted; `index.html.tmpl` is chrome plus calls.  (As built: plus
   `pass_roster_html`, `pass_panel_hidden`, `footer_html` and the
   template's switch to `theme_class`; the set keys decided as above;
   the label escaping both sides that step 3's review deferred here.
   The search list reads the archive interval for the dome's wrapper
   itself, as the generator does, so `dome_html` takes no `$current`.)
5. `celestial_panels`, `celestial_reports` widened, the installer and
   CLI verbs declaring for consumer reports; the consumer fixture and
   its browser test.  Also here: the fragments are written into
   `HTML_ROOT` itself and the page fetches them relative to its own
   URL, so a consumer page generated into a subdirectory
   (`template = astro/index.html.tmpl`) 404s every refetch with nothing
   logged.  Either a set gains a `directory`, or the contract states
   the page must sit at `HTML_ROOT`'s root; decide with the fixture.
   (As built: a set gains `directory`, decided with the fixture, whose
   page sits in `astro/` and whose browser test watches every fragment
   fetch reach `astro/` and come back 200 -- a contract that pinned the
   page to the root would have ruled out every multi-page skin with a
   sky section of its own.  The fixture is rendered through WeeWX's own
   `StdReportEngine`, not the harness's stubbed search list, so the
   search list, the generator and the copied assets are exercised as a
   station runs them.  The groups are per panel (above); the footer is
   not a panel for the key.)
6. Docs: `own-skin.md` becomes "Panels in your own skin" on skyfield's
   `panels.md` model (the boundary section is deleted, its replacement
   being the contract); `fields-reference.md` prints per panel;
   `configuration.md` gains `[CelestialFragments]` and `celestial_panels`;
   and three sentences step 5's reviews found wanting a home: `weectl
   extension uninstall` leaves a consumer's `satellites`/`comets`
   groups declared (weectl has no uninstall hook; empty the key and
   re-run a verb first, or delete them by hand after, as the
   twin-Celestial-report paragraph says); deleting the key likewise
   leaves the groups (absent means "not ours"); and two reports writing
   fragment sets into one `HTML_ROOT` must give them distinct prefixes;
   `changes.txt`; release notes; the README screenshot only if the look
   changed, which it must not have.

Then the liveseasons conversion from the manual (the acceptance test
above), then 9.0.  The version is a major because `realtime_updater.inc` and
the fragment templates go away, and a user who edited either has work
to do at upgrade; `upgrading.md` says what.

## Decisions

Taken 2026-08-29, working through the list above.  The alternatives are
kept so the reasons are not lost.

1. **Consumer field declaration: opt-in key plus paste.**  Static groups
   are pasted from the manual into the consumer's `skin.conf`;
   `celestial_panels = ...` in the consumer report's `weewx.conf` stanza
   has the installer and the `--add`/`--remove` verbs maintain its
   `satellites` and `comets` groups through the one existing code path.
   Rejected: paste only (a consumer with satellites re-pastes after every
   `--add-satellite`); the installer writing the static groups too (a
   consumer's field set on every machine's `weewx.conf`, which
   liveseasons 8.5 just moved away from).
2. **Fragments from `FragmentGenerator`** in the consumer's own
   `generator_list`, sets in its `skin.conf`; the sample skin uses it
   too.  Rejected: copied one-liner templates (eleven files per set,
   twenty-two for liveseasons); a separate fragments report (a stanza per
   theme, scale and language, kept in agreement by hand).
3. **Satellite rosters are separate methods** (`dome_roster_html`, and
   `pass_html`'s roster its own call), so a consumer places them
   independently.  Rejected: rosters inside `dome_html`/`pass_html` with
   a `roster=False` kwarg.
4. **`celestial.js` exposes `start(config)` and nothing else.**  A
   packet hook can be added later without breaking anything; it waits
   for a consumer to ask.
5. **Version 9.0.**  `realtime_updater.inc` and the fragment templates
   go away, and the consumer contract's additive-only clock starts here.

Nothing else in this document is open.  The next thing to do is step 1
of the sequencing above.
