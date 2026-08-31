---
title: Panels in your own skin
layout: default
nav_order: 11
description: Embedding the Celestial panels in any WeeWX skin — the countdown row, the Geocentric dial, the live sky dome and the Next Visible Pass chart, through the $celestial search list, a field declaration, three copied assets and the fragment generator.
---

# Panels in your own skin

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Every panel on the Celestial page is rendered by `$celestial` — a standard
WeeWX search-list extension, `user.celestial_page.CelestialPanels`,
installed along with this extension — and, as of **9.0**, can be dropped
into any skin's Cheetah template, live layer and all.  The bundled skin
is the first consumer: its `index.html.tmpl` is a header, some section
headings and a footer around the same calls this page documents, and it
uses nothing another skin cannot.

This is the same shape as
[weewx-skyfield's own panels guide](https://chaunceygardiner.github.io/weewx-skyfield/panels.html),
with one difference that decides most of what follows: **skyfield's
panels are pictures, and these are instruments.**  A `$sky_page` panel is
a string of markup, complete when the report ends.  A `$celestial` panel
is markup *plus* a live layer — a declaration of the loop-data fields it
reads, a script that repaints it on every packet, a stylesheet, and (for
the sky dome and the Next Visible Pass chart) a set of chart fragments
the page refetches as the sky turns.  So there are four things to
arrange rather than three, five if your skin is not in English.

{: .note }
Before 9.0 there was no supported way to do this, and the manual said so:
the page's javascript was a Cheetah include with every per-report value
baked into it, and the dome's fragments were a dozen templates.  A skin
that had forked that code replaces the fork with the steps below, and
inherits every fix since.

## What a skin arranges

### 1. The search list

In your skin's `skin.conf` (append to the list if your skin already sets
it):

```
[CheetahGenerator]
    search_list_extensions = user.celestial_page.CelestialPanels
```

That publishes `$celestial` — every panel call below — and `$sky_page`
beside it, so a skin embedding both these panels and weewx-skyfield's own
needs no second search list.

### 2. The fields the panels read

The panels first-paint from `$almanac` at report time and then go live
from `loop-data.txt`, which means the fields have to be **declared to
weewx-loopdata under your report's name** (weewx-loopdata 7.0 or later).
The declaration comes in two halves, exactly as it does for the bundled
skin.

**The fields that never change** — the clock, the eleven bodies, the
countdown events — you paste into your own `skin.conf`, from
[the shipped declaration](fields-reference.md#the-shipped-declaration):

```
[LoopData]
    [[fields]]
        clock = current.dateTime.raw
        ...
```

They are a skin's own business: `skin.conf` deploys with the skin, so
this is one edit, not one per machine.  Paste the whole thing unless you
are showing a subset of the panels — the
[per-panel groups](fields-reference.md#which-groups-each-panel-reads)
say what each one actually reads.  A group of your own goes under a name
of your own; weewx-loopdata merges by group name.

{: .note }
If your own suite holds your declaration to exactly what your pages read
— a test that fails on a declared field nothing consumes, which is a good
test to have — it will fail the moment you paste these groups, because
the fields they carry are read by this extension's markup rather than
yours.  Exempt the pasted groups by name and check them against the
per-panel table instead; that is the table's second use.

Such a test breaks a second way if it finds its fields by scanning
script literals: `celestial.js` carries fallback key spellings beside
the keys it reads — `almanac.next_full_moon.raw` sitting next to
`almanac.next_full_moon.unix_epoch.raw` — and those are not fields to
declare.  Exempt the vendored scripts from that scan.

**The satellite and comet fields** follow the station's `[Skyfield]
[[Satellites]]` and `[[Comets]]`, which no shipped file can know, so
this extension's installer writes them — for your report too, once you
say which panels your page embeds.  **Say it in your own `skin.conf`**,
at the top level, beside `[LoopData]`:

```
celestial_panels = countdown, geocentric, dome, pass
```

That is a fact about your templates: the same on every station, changing
only when you change which panels you embed.  Declaring it with the skin
means it deploys with the skin, and nobody installing your skin has to
edit `weewx.conf` on any machine.

Then `weectl extension install`, `--add-satellite`/`--add-comet` and
their inverses maintain that report's `satellites` and `comets` groups
exactly as they maintain the Celestial report's — one writer, so the two
cannot disagree — and only the groups your named panels actually read.

**Have your own installer do it, so one install is enough.**  Those two
groups are per-station, so something has to write them into `weewx.conf`
after your skin lands.  End your installer's `configure(engine)` with:

```python
    try:
        import user.celestial
        user.celestial.declare_page_fields(engine.config_dict,
                                           pending=self['config'])
    except ImportError:
        print('weewx-celestial is not installed; install it and re-run '
              'this installer to declare the panels\' fields.')
    return True
```

`pending` is your own config stanza, and it is not optional: `weectl`
runs `configure()` *before* it injects that stanza, so on a fresh install
your report does not exist yet and there would be nothing to declare
under.  Passing it lets the groups be written under a report that is
about to exist; `weectl`'s own merge fills the rest in around them.

Install order does not matter.  If weewx-celestial is already installed,
your install writes the groups.  If it is installed afterwards, its own
installer walks every report and picks yours up.  If it is never
installed, your installer says so and finishes, and your pages carry the
panels' install hint.

**A per-report override, when you need one.**  A report's own stanza
still beats the skin — the order WeeWX merges in — so a station can
differ for one report without editing a skin it may not own:

```
[StdReport]
    [[MyReport]]
        skin = MySkin
        celestial_panels = dome, pass
```

Two reports running one skin — a metric twin, say — both inherit the
skin's key, and either can override in its own stanza.  If you set the
key in both places, the run says so in the log, and warns when the two
disagree: the stanza wins, and a stale one is easy to forget.

{: .important }
On any report carrying `celestial_panels`, the group names `satellites`
and `comets` belong to this extension: they are rebuilt or removed
wholesale on every run.  Put a satellite field of your own under another
name.  The key belongs on the report — never under `[[Defaults]]` or at
`[StdReport]`'s top level, which WeeWX merges into every report, and
which is refused as the misconfiguration it is.  A page whose panels are
not declared says so where it renders; see
[What a panel says instead of drawing](#what-a-panel-says-instead-of-drawing).

A page embedding only the countdown row and the Geocentric still needs
the key (both read comets, the countdown reads satellites too); a page
embedding neither satellites nor comets needs no key at all.

### 3. The assets, and the config block

Three files, copied from `skins/Celestial/` into your skin and deployed
by your own `[CopyGenerator]`:

```
[CopyGenerator]
    copy_once = celestial.css, celestial.js, sky.js
```

- **`celestial.css`** is the **panel** stylesheet: every color the panels
  use, both plates' worth, as a token set you can restyle — see
  [Restyling the panels](#restyling-the-panels).
- **`celestial.js`** is the live layer: one static file publishing one
  global, `celestial`, with one method, `celestial.start(config)`.
- **`sky.js`** is weewx-skyfield's tap-tooltip helper, copied verbatim;
  without it the SVG tooltips are hover-only and dead on a touch screen.

{: .important }
**Do not load `celestial-page.css`.**  The bundled skin ships a second
stylesheet, and it is the Celestial *report's* own page — the `body`,
the `header`, the `h1`, the card a `<section>` draws, the `footer`, the
document's `color-scheme`.  Those rules name bare elements, so loading
them in a page of your own repaints your whole site: your titlebar, your
footer and every unrelated section on the page.  `celestial.css` carries
nothing that reaches past the panels, which is the whole point of there
being two files.

Two practical notes on copying, both from the first skin to do it.  You
may already ship files of these names — a `celestial.css` of your own is
not unlikely if you built celestial-style panels before 9.0 — so **copy
them under whatever names you like** (`css/celestial-panels.css`, say);
nothing in the panels depends on the file name, and following the step
above literally would clobber your own file.  And if your skin already
carries weewx-skyfield's `sky.js`, keep the copy you have and load it
once; it is the same file.

In the page's `<head>`:

```
    <link rel="stylesheet" href="celestial.css">
    <script src="celestial.js"></script>
    <script src="sky.js" defer></script>
```

`celestial.js` is deliberately **not** deferred.  It arms the loop poll
when it runs, and a packet can land while the panels below are still
parsing; deferred, the paths that handle exactly that case would never
run.

Then, as the first thing in `<body>`, the config block:

```
    $celestial.config_script($almanac, $filename)
```

That is the whole per-report half of the live layer — the `[Extras]`
options, the station's latitude, the generation instant, the report's
distance unit, language, body names, compass cardinals, `[Texts]`
strings, satellites, comets, report name and loop-data file — emitted as
one object, ending in the `celestial.start(...)` call.  The script itself
is static and knows nothing about your report.  One key in it is worth
knowing by name: `gen_ts` is the instant the page was generated for, the
page's clock until the first loop packet arrives — if your own code or
tests reach for a generation instant, that is where it now lives.

`$filename` is core WeeWX's own tag: the page's path under `HTML_ROOT`.
Passing it is what lets the page **sit anywhere** — in a subdirectory,
beside a dozen other pages — because the block turns it into the route
back up to `HTML_ROOT`, where the chart fragments are written.  A page
that passes nothing fetches relative to itself, which is right only when
it sits at `HTML_ROOT`'s root.

Your report also needs `[[[Extras]]] loop_data_file` — the URL, relative
to *your* report's `HTML_ROOT`, at which the web server serves
weewx-loopdata's output.  `refresh_rate`, `expiration_time`,
`page_update_pwd` and `time_zone` work as they do for the bundled page
(see [Configuration](configuration.md)), and the page's plate comes from
the report's `theme` option.

### 4. The fragments — only for the dome and the pass chart

The sky dome and the Next Visible Pass chart are weewx-skyfield
drawings, and an open page keeps them current by refetching them: a
staggered set of dome backdrops the page steps through as the sky turns,
and the pass chart every five minutes.  Those files are written by a
generator that runs inside your own report, so they carry your report's
theme, language, `[Almanac]` names and generation instant:

```
[Generators]
    generator_list = weewx.cheetahgenerator.CheetahGenerator, user.celestial_page.FragmentGenerator, weewx.reportengine.CopyGenerator
```

With no more than that, the report writes one set — `dome-svg.txt`,
`dome-svg-1..9.txt` and `pass-chart.txt` — into `HTML_ROOT`, at label
scale 1.0, on the report's own plate, and `$celestial.dome_html($almanac)`
embeds it.  A skin that wants more than one set — two label scales for
two screen sizes, a night dome inside a light site, or simply a tidier
directory — declares them:

```
[CelestialFragments]
    [[astro]]
        directory = astro
    [[smartphone]]
        prefix = dome-svg-sp
        label_scale = 2.2
        directory = astro
```

| Key | What it does |
|---|---|
| `prefix` | The set's file names: `<prefix>.txt`, `<prefix>-1..9.txt`, `<prefix>-pass.txt`.  Default `dome-svg`, whose pass fragment keeps the name `pass-chart.txt`.  One set per prefix, whatever their directories — a page that names no set finds its set by prefix.  Two sets are refused separately for *writing* the same file, which follows `kind`: a dome-only set never claims the pass fragment its prefix spells, nor a pass-only set the ten dome slots |
| `label_scale` | Passed to weewx-skyfield's chart labels; default 1.0 |
| `theme` | `dark`, `light` or `auto`, spelled exactly as the report option is; default the report's own.  A set on a plate of its own is drawn on that plate and keeps its own label colors — that is how a night dome sits inside a light page |
| `directory` | Where under `HTML_ROOT` the set is written; default `HTML_ROOT` itself.  A plain relative path — no leading slash, nothing that could leave `HTML_ROOT` |
| `kind` | Which fragments the set is for: `dome` (the ten backdrops), `pass` (the chart) or `both`, the default.  A skin with the dome on one page and the chart on another, at different label scales, wants a set for each — and without this each writes the other's files every cycle for a page that never asks.  A call for the panel a set does not write is **refused**, with the line below and the reason in the log, rather than pointed at a file nothing will ever write |

The page then names the set it embeds, and gets that set's scale, plate
and file names in one:

```
    $celestial.dome_html($almanac, set='astro')
    $celestial.pass_html($almanac, set='astro')
```

A skin with two label scales chooses its set per page rather than naming
one literally, and `set=` takes a Cheetah variable — **unquoted**, since
Cheetah does not interpolate inside a quoted string.  `set='$dome_set'`
passes the literal text `$dome_set`; what that case wants is:

```
    #set $dome_set = 'stars_sp' if $smartphone else 'stars'
    $celestial.dome_html($almanac, set=$dome_set)
```

A call naming no set gets the set on the `dome-svg` prefix — the default
set on a skin that declares none, or whichever declared set holds that
prefix.  A call naming a set the skin does not declare is **refused**,
with a line in the dome's place and the set's name in the weewxd log; it
is never quietly answered with the default.

{: .note }
Declaring any set replaces the default, so a skin that adds one for a
second page and still wants the plain one declares that one too, with
`prefix = dome-svg`.  Two reports writing sets into one `HTML_ROOT` must
give them distinct prefixes — the files are named by prefix alone, and
whichever report ran last would otherwise own them.

### 5. If your skin is not in English

The panels translate through **your** report's `[Texts]`, not the
Celestial skin's: `$celestial` reads the skin dict it is given.  Copy the
`[Texts]` section of `skins/Celestial/lang/<code>.conf` into your own
skin's lang file for each language you ship — the strings are reproduced
in [the translation dictionary](i18n-dictionary.md) — or set the entries
in `weewx.conf`, under the report or `[[Defaults]]`, where they survive
upgrades.  Anything you leave out falls back to its English key, one
string at a time; nothing breaks.  Body, satellite and comet names come
from the report's `[Almanac]` section as usual, and so need nothing
copied.  See [Translations](i18n.md).

## The calls

Every one takes the report's `$almanac` and returns markup, guarded: a
panel that fails to render is logged with its traceback and left out,
and the rest of the page and the rest of the live layer carry on.

| Call | What it renders |
|---|---|
| `$celestial.countdown_html($almanac)` | The countdown row — the chips, first-painted and then counting on every loop packet |
| `$celestial.geocentric_html($almanac)` | The Geocentric: the dial (the javascript builds it on the first packet) and the roster beside it |
| `$celestial.dome_html($almanac, set='')` | The sky dome: the fragment set's current backdrop in its self-describing wrapper, its caption and its frozen-sky line |
| `$celestial.dome_roster_html($almanac, set='')` | The "next pass overhead" roster — every configured satellite's next pass of any kind |
| `$celestial.pass_html($almanac, set='')` | The Next Visible Pass chart, hidden when no pass is in the window |
| `$celestial.pass_roster_html($almanac, set='')` | The visible-pass roster beside it |
| `$celestial.pass_panel_hidden($almanac, set='')` | True when the pass panel has nothing at all to show, so your own section chrome can hide with it; the javascript unhides `#pass-sec` by that id when a pass enters the window |
| `$celestial.footer_html($almanac)` | The credit line, true for whichever almanac actually served the page |
| `$celestial.theme_class($almanac)` | `theme-dark` or `theme-light` — the report's `theme` resolved at generation, `auto` included.  Put it on your root element, or on the container holding the panels: both plates are keyed on the class, so a dark panel box inside a light site is a matter of putting `theme-dark` on that box |
| `$celestial.config_script($almanac, $filename)` | The config block and the `celestial.start` call |

The rosters are separate calls so you can place them where you like; the
bundled page puts each beside its chart in a two-column grid, which is
its own chrome, not the panel's.

{: .note }
One dome and one pass chart per page.  Both are addressed by id
(`#dome-svg`, `#pass-chart`) and refetched by the script, so a second
copy of either on one page would not refresh.  The countdown row, the
Geocentric and the rosters have no such limit.

## A page, entire

This is the whole of a working consumer page — the one the test suite
generates through WeeWX's own report engine and then drives in a real
browser.  It sits in `astro/` under its report's `HTML_ROOT`, which is
why its assets are one level up and its fragment set declares
`directory = astro`:

```
#errorCatcher Echo
#encoding UTF-8
<!DOCTYPE html>
<html lang="en" class="$celestial.theme_class($almanac)">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>$station.location</title>
    <link rel="stylesheet" href="../celestial.css">
    <script src="../celestial.js"></script>
    <script src="../sky.js" defer></script>
  </head>
  <body>
    $celestial.config_script($almanac, $filename)
    <div class="cel-page">
      <header>
        <h1>$station.location &middot; the live sky</h1>
        <div class="cel-sub cel-mono">updated <span id="last-update"></span> <span id="live-label"></span></div>
      </header>
      $celestial.countdown_html($almanac)
      <section>
        <h2 class="cel-eyebrow">Geocentric</h2>
        $celestial.geocentric_html($almanac)
      </section>
      <section>
        <h2 class="cel-eyebrow">Sky dome</h2>
        <div class="cel-domepanel">
          $celestial.dome_html($almanac, set='astro')
          $celestial.dome_roster_html($almanac, set='astro')
        </div>
      </section>
      #set $pass_html = $celestial.pass_html($almanac, set='astro')
      #if $pass_html
      #set $pass_sec_attr = ' hidden' if $celestial.pass_panel_hidden($almanac, set='astro') else ''
      <section id="pass-sec"$pass_sec_attr>
        <h2 class="cel-eyebrow">Next visible pass</h2>
        <div class="cel-passpanel">
          $pass_html
          $celestial.pass_roster_html($almanac, set='astro')
        </div>
      </section>
      #end if
      <footer>$celestial.footer_html($almanac)</footer>
    </div>
  </body>
</html>
```

The complete skin — that template, its `skin.conf` and the pasted field
groups — is in the repository at `tests/fixtures/consumer-skin/`, and it
is not a sketch: the suite runs a real report engine over it, asserts the
page and its fragments land where they should, and then loads it in
headless Chromium with a loop feed running to watch every fragment fetch
reach `astro/` and come back 200.

### Two ids where your live layer and this one meet

The panels are self-contained, but two elements describe the **feed**
rather than any one panel, and the script writes them if it finds them:

- **`#last-update`** — the page's clock: the timestamp of the last loop
  packet, painted as `HH:MM:SS`.
- **`#live-label`** — the badge, where the feed's faults are reported:
  `LIVE`, an age in seconds, `NO DATA (HTTP 404)`, `BAD DATA`, `OFFLINE`,
  `CLICK-ME`.

**If your skin has no live layer of its own, give the page both.**  They
are the only honest account of a dead feed, and without them a stalled
page looks merely quiet.  The bundled skin puts both in its header.

**If your skin already has a live layer — and any skin big enough to want
these panels probably does — leave them out.**  This is the opposite
advice, and it is the important half: those two ids are exactly where
your live layer and this one collide.  Both would write the same
elements, on their own polls, in their own dress.  The first consumer to
try it found its own clock painting `11:50:00 AM` and this script
painting `11:50:00`, twice every two seconds, in the most prominent cell
of the panel header — a visible flicker on every page.  Give your own
elements **ids of your own** — reusing these two is what causes the
collision, and a skin that has had a `#live-label` of its own for years
is exactly the skin that will reuse them without thinking.  Rename yours
(`paw-live-label`, say) and the script skips these silently: every write
goes through a null-safe path, there is no console noise, and no panel
is affected.

{: .important }
**A host with its own expiry wants `expiration_time = 0`.**  The script
runs an expiry of its own — after `expiration_time` hours it stops
polling and offers `CLICK-ME` in `#live-label` — and if you have left
that element out, it stops polling with nowhere to say so, while your own
badge goes on reporting a feed the panels are no longer reading.  Setting
`expiration_time = 0` in the report's `[[[Extras]]]` disarms it entirely,
leaving the policy to your own machinery.  Two expiry regimes on one page
is worse than either.

`#pass-sec` is optional in a third way: give your pass section that id
and the script hides and unhides it as passes come and go; leave it off
and the section stands, with the chart hiding itself inside it.

### The script never reads `celestial_panels`

Panel presence is inferred from the DOM alone.  A page with no countdown
chips, or with the dome but not the pass chart, is silent on every packet
— the renders find no element and return.  `celestial_panels` drives the
*field declaration* and the render-time message about it, and nothing in
the browser reads it.  So a page may embed any subset of the panels
without configuring the script.

## Restyling the panels

Everything the panels draw themselves — the dial, the rosters, the chips,
the badge, the frozen-sky line — takes its colors from custom properties
declared on `:root` in `celestial.css`, and every rule reads them through
`var()`.  No color is written into markup or javascript.

One rule in that stylesheet is not a color and is worth knowing about:
the panels' spacing was laid out under `box-sizing: border-box`, so the
sheet sets it — scoped to the panels' own subtree
(`[data-celestial], [data-celestial] *`), never to your page.  A site on
the browser default gets the panels laid out as designed and keeps its
own box model everywhere else.

Every class the panels wear is prefixed `cel-` (`cel-row`, `cel-roster`,
`cel-caption`), so nothing here can collide with a class of your own,
however deeply your own rules are scoped.  The exceptions are the classes
weewx-skyfield writes inside its own fragments, which keep its names.  So a stylesheet
of your own, loaded after `celestial.css`, restyles the lot:

```css
:root { --night: #e3e3e3; --ink: #1c1c1c; --brass: #367ba3; }
```

The token names are part of the contract, so overrides survive an
upgrade.  They come in four families: the page surfaces (`--night`,
`--vault`, `--ink`, `--muted`, `--brass`, `--line`, `--halo`), the chart
furniture (`--grid`, and `--skylab`/`--conlab` for the sky charts'
labels), the per-body identity colors (`--c-sun`, `--c-moon`, `--c-mars`,
… `--c-proxima`), and the darker edges the three pale bodies take on
paper (`--e-sun`, `--e-moon`, `--e-venus`, `--e-earth`).  Read the top of
`celestial.css` for the current set and what each is for.

{: .important }
**On the light plate, write the override on `.theme-light`.**  The light
plate's tokens are declared there, and a class outranks a plain `:root`
rule however late it is loaded — so a `:root { --brass: … }` override
reaches the dark page and is silently lost on the light one.  Write both:

```css
:root { --brass: #367ba3; }
.theme-light { --brass: #1d5c80; }
```

{: .important }
**Declare the tokens above the panels, not below them.**  An override on
`:root`, or on a container that holds the panels, does what you expect.
Declaring the whole token set on an element *between* `:root` and the
panels — a `body.night-page`, say — also works, and silently pins you to
today's palette: your copies shadow this extension's inside its own
panels, so a value changed in a later release (weewx-skyfield retuned
Mars once already) reaches the charts and not the dial, putting two
shades of one thing on one page.  If you do keep a copy of the values,
pin it with a test against `celestial.css` rather than trusting it to
stay true.

The marks weewx-skyfield draws — the dome's stars and planets, the pass
chart's arc — are the exception: their colors are written inline in the
SVG, chosen by the fragment set's `theme`.  A token cannot move them.

Their *labels* are a middle case worth knowing.  Those carry skyfield's
own class names (`starlab`, `conlab`, `gridlab`, `cardinal`, `bodylab`),
deliberately, so the two extensions' charts read as one family — which
means a rule of your own naming those classes styles the dome's labels
too, and beats the token route on specificity.  That is fine and often
intended; just know which of the two is in force before concluding the
tokens have failed to reach the charts.  Label *sizes* are the one thing
your rules cannot take over: skyfield writes those inline on every label,
which is what makes `label_scale` work.
That is also why a fragment set on a plate other than the page's keeps
its own label colors rather than inheriting the page's.

## What a panel says instead of drawing

A panel that cannot draw says why, where it would have drawn, rather than
vanishing — and says the same thing in the weewxd log, once per fault per
report cycle.  You will meet these while wiring a page up:

| The panel says | What it means |
|---|---|
| *Install weewx-skyfield …* | The registered almanac cannot serve that panel — the ordinary tier behavior, not a wiring fault (see [the almanac tiers](configuration.md#the-almanac-tiers)) |
| *The sky dome could not be drawn — see the weewxd log* | The almanac is registered but the drawing came back empty; the log says why |
| *This page's report does not name the … panel in `celestial_panels`* | Step 2's key is missing that panel, so its live fields are not declared.  Name it, re-run the installer, restart weewxd |
| *This page's report carries an invalid `celestial_panels`* | The key names something that is not a panel, or sits where WeeWX would merge it into every report.  The log names it |
| *This page's report's field declaration is out of date* | The panels are named but the groups in `weewx.conf` are not what the installer would write now — a satellite added to `[Skyfield]` by hand, say.  Re-run the installer or the `--add-` verb, and restart weewxd |
| *The page's fragment set is missing or invalid in `[CelestialFragments]`* | The `set=` name is not declared, or the skin declares sets but none on the `dome-svg` prefix and the call named none |

A page that first-paints and then never moves, with nothing to say why,
is the failure these lines exist to prevent: the declaration ones are
rendered by asking the installer's own question of the same `weewx.conf`
at generation time.

The browser console carries the rest, once per kind: a fragment fetch
that came back with an HTTP error or with something that is not a
fragment, naming the URL asked, and — at load — a dome whose swap target
carries no set name, which is never refetched at all.  That is where to
look when the panel renders and then the sky never steps.

## The contract

Every panel's root element carries `data-celestial="<version>"` — the
version of this extension that rendered it.  Inside a major version the
surface is **additive only**: the DOM ids, the config keys, the fragment
wrapper's data-attributes, the field group names, the
`[CelestialFragments]` keys, the `celestial.css` token names and the
public call signatures above never change meaning or disappear.  A panel
may gain marks, keys and classes; `changes.txt` names each one.

What is **not** contract: the internals of `celestial.js`, the shape of
the SVG the dial builds, and the roster's inner spans.  A page that
reaches past the documented ids and tokens is on its own.

The coupling to weewx-skyfield — the dome's per-mark hooks, the chart
palettes, the label classes — has not gone away.  It has moved behind
this extension's own tests, where you inherit it instead of copying it,
which is the whole point of this page.  Run the two extensions in step,
as their release notes ask, and it is not your problem.

## Housekeeping

- **Uninstalling your skin takes its groups with it, on the next run.**
  `weectl` has no uninstall hook, so your installer cannot clean up after
  itself: removing your skin deletes its `skin.conf`, taking the key, and
  would leave the two groups behind for weewx-loopdata to evaluate every
  packet for panels that no longer exist.  So a report that names no
  panels, carries those groups, and whose skin's `skin.conf` is **gone**
  has them removed by the next `weectl extension install` or
  `--add-`/`--remove-` verb, which reports the removal.  A `skin.conf`
  that merely cannot be read — no permission, a mount that is not up, a
  syntax error — is left alone and logged: a skin that is gone is a
  statement, one that cannot be read is a question.
- **Deleting the key from a `skin.conf` that still exists leaves the
  groups.**  No key means "not this extension's report", so nothing is
  removed.  To ask for their removal without removing the skin, empty
  the key — `celestial_panels =`, a report that embeds nothing — and
  re-run the installer or a verb.
- **`weectl extension uninstall celestial` does not clean up after a
  consumer.**  It removes its own report's stanza and leaves yours
  alone, groups included.
- **Your skin's own upgrade path.**  The copied assets are yours once
  copied, under whatever names you gave them: re-copy them from
  `skins/Celestial/` after upgrading this extension, exactly as you would
  weewx-skyfield's `sky.js`.  The version-tag trick the bundled page uses
  (`celestial.css?v=…`) is worth copying too — a browser holding a stale
  script against a fresh config block is a confusing few minutes.

  Know what forgetting looks like, because it does not look like an
  error: the panels render (the markup is new) but arrive unstyled, and
  the dial never draws, because an old stylesheet and an old script are
  looking for class names the new markup no longer uses.  Nothing fails
  and nothing is logged.  The script does announce a version-mismatched
  config in the browser console, which catches its half on a real
  upgrade; the stylesheet carries no version and cannot.  If a page
  looks like plain text with a blank dial after you upgrade, this is
  why.  Note also that `copy_once` will not overwrite a file that is
  already there — copying is yours to do.

## If you are building a live page of your own instead

Nothing above stops you writing your own page against the same data —
the panels are one way to spend weewx-loopdata's almanac fields, not the
only one.  The full grammar is in
[weewx-loopdata's manual](https://chaunceygardiner.github.io/weewx-loopdata/almanac-fields.html),
its own
[Build a live page](https://chaunceygardiner.github.io/weewx-loopdata/build-a-live-page.html)
covers the general pattern, and this manual's
[Fields reference](fields-reference.md) lists exactly what these panels
read.  Five things this skin learned the hard way, each of which applies
to any live page:

- **One clock, and it is the packet's.**  The loop packet's own
  timestamp is the page's time; the browser's clock is a stopwatch, asked
  only how long something took, never what time it is.  A viewer whose
  clock is wrong then sees exactly what a viewer whose clock is right
  sees, and a dead feed reads dead everywhere at once.  See
  [Whose time it is](how-it-stays-live.md#whose-time-it-is).
- **Absent and null are two different states.**  weewx-loopdata omits
  null-valued keys, so a field *not declared* (the report-time first paint
  stands) is distinguishable from one *present but empty* (no pass to
  report, no elements, no comet).  Every honest "nothing to show" on this
  page leans on that.
- **First-paint every cell from `$almanac`, guarded individually.**  The
  page is then never blank while it waits for a packet, and a less
  capable almanac costs a cell rather than the report.
- **`$almanac.texts` succeeds on WeeWX 5.2 and then kills the page.**
  The report's `[Almanac]` names reach the almanac only from 5.3.  You
  might expect 5.2 to raise a clean `AttributeError` you could default
  around — it does not: `Almanac.__getattr__` walks the registered
  almanacs and PyEphem's catch-all treats any unknown name as a heavenly
  body, so the lookup *succeeds*, returns something truthy, and dies one
  step later during report generation, so the page never appears at all.
  Read `$almanac.__dict__.get('texts', {})` instead.  The same shape
  lurks wherever an optional almanac attribute is probed: test the
  *value*, never the success of the attribute access.
- **A baked-in palette cannot have a browser toggle.**  Server-drawn SVG
  arrives with its colors inside it, and any class you add to it is undone
  the moment the page refetches it.  Resolve the theme where the drawing
  happens — at generation time, into a class on the root element, with
  every refetched fragment on the same palette as the page.

## Live in the wild

[PaloAltoWeather.com's Celestial Today page](https://www.paloaltoweather.com/celestial.html)
carries a Geocentric Live panel built with the same technologies used
here ([weewx-skyfield](https://github.com/chaunceygardiner/weewx-skyfield)
and [weewx-loopdata](https://github.com/chaunceygardiner/weewx-loopdata)),
alongside pages of its own that read fields this skin does not.
