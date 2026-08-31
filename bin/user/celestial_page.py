"""
celestial_page.py

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

The Celestial page's panels as things another skin can embed: the
`$celestial` search list (`CelestialPanels`) and the generator that
writes the sky dome's staggered backdrop fragments and the pass-chart
fragment into a report's HTML_ROOT (`FragmentGenerator`).

A skin lists the search list in its [CheetahGenerator]
search_list_extensions and the generator in its [Generators]
generator_list, and gets `$celestial` (this module's `CelestialPage`)
and `$sky_page` (weewx-skyfield's SkyPage, or None when weewx-skyfield
is absent -- through the celestial_sky shim, which is what makes the
absence survivable).  The bundled Celestial skin is a consumer of this
module like any other.

The page's javascript is one static file, the skin's celestial.js, and
everything it needs per report -- the [Extras] options, the station's
latitude, the generation instant, the report's distance unit, language,
body names, compass cardinals, [Texts] strings, satellites, comets, name
and loop-data file -- is the config `$celestial.config_script($almanac)`
builds into the <script> block that starts it.  Through 8.5 the script
was a Cheetah include that baked those values into itself; the split is
what lets another skin run the same javascript unchanged.  The config's
keys are contract (additive only inside a major version), and a test
pins them.

The fragment set.  Each report cycle the generator writes up to ten
dome backdrops spaced max(60 s, interval/10) apart across the archive
interval -- `dome-svg.txt` and `dome-svg-1..9.txt` -- so the open
page's javascript can step the sky between cycles, plus the
`pass-chart.txt` fragment the Next Visible Pass panel refetches.  Each
dome fragment is wrapped in a div that self-describes (its own depicted
time, its slot, the spacing, the count, the archive interval, the plate
it is drawn on), so the fetch side adapts to any archive interval and
notices a theme flip.  Slots whose offset falls beyond the interval are
written EMPTY, and the page never asks for them.  The slot geometry is
`dome_slots`, and nothing else computes it: the page's own wrapper
(`dome_html`) reads the same function, so the two can never disagree
(they did, once each in two repos, when each carried its own copy of
the arithmetic).

A skin that wants more than one set -- two label scales for two screen
sizes, or a set on a plate other than the report's -- declares them in
its skin.conf:

    [CelestialFragments]
        [[desktop]]
            prefix = dome-svg-desk
            label_scale = 0.8
        [[smartphone]]
            prefix = dome-svg-sp
            label_scale = 2.2
            theme = dark

No section means the one default set, prefix dome-svg, scale 1.0, on
the report's theme.  Declaring ANY set replaces it: a skin that adds a
set for a second page and keeps the page's own dome declares that one
too (prefix = dome-svg).  One dome and one pass chart per PAGE -- the
panels' element ids are singular -- so two sets mean two pages.  The
page names the set it embeds --
`$celestial.dome_html($almanac, set='smartphone')` and
`$celestial.pass_html($almanac, set='smartphone')` -- and no set means
the set on the dome-svg prefix, which a skin declaring none has by
default; so the first paint, the ten fragments, the pass chart and the
file names the javascript refetches all come from one declaration and
cannot disagree.  A call naming a set the skin does not declare renders
nothing and logs the name, never the default: a page first-painting one
set and refetching another's files is the fault the declaration
exists to prevent.  The panel's markup names its own files (the dome's
swap target carries data-dome-prefix, the chart's data-pass-fragment),
so a page can embed a set without saying its name twice.  A set's
theme takes dark | light | auto exactly as the report option does
(auto: light while the sun is up at the page's instant) and chooses
the plate of the skyfield-drawn panels only; the page's own chrome
follows the theme class on its root element, and the javascript judges
a plate flip against the dome's own wrapper, so a set on a plate other
than the page's is not a flip.  A set's files are written into its
`directory` under the report's HTML_ROOT -- HTML_ROOT itself by
default -- and the page's javascript fetches them from there: the
page passes core's $filename (its own path under HTML_ROOT, a core
search-list tag on every WeeWX this extension supports) to
config_script, the config block carries the page's route up to
HTML_ROOT (`root`, '../' per directory level), and the script fetches
from root + the set's directory, which the panel's markup carries
(data-dome-dir, data-pass-dir).  So a page may sit anywhere under
HTML_ROOT and the skin may keep its assets anywhere: nothing is
inferred, the generator states where the page is.  A page that passes
no $filename fetches relative to itself, which is right when it sits
beside its set.

A page in another skin says which panels it embeds in its report's
weewx.conf stanza (celestial_panels), and the installer declares the
satellite and comet fields those panels read under that report.  The
search list asks the same question of the same weewx.conf
(report_groups on the generator's config_dict -- one reader for both
sides), and a panel whose fields are not declared carries a line
saying so before its root, because such a panel first-paints and then
never moves, and nothing else on the page would say why.

The palette is resolved against the PAGE's almanac, never a slot's
re-bound one: on theme = auto a slot minutes past sunrise would
otherwise render paper inside a page that is still night, and the
refetch would flip the dome mid-cycle.  The palette is a property of
the generation instant, exactly as the theme class on <html> is.

A fragment that fails to render is logged and its file left as it was
-- the old sky stays on disk for the page to keep -- never written
empty and never written with error text the javascript would inject
into the page.  Without a SkyPage at all every fragment is written
EMPTY, which is the page's signal to say so and point at weewx-skyfield.
"""

import datetime
import functools
import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import weewx
import weewx.almanac
import weewx.cheetahgenerator
import weewx.units
import weeutil.logger
from weewx.cheetahgenerator import SearchList
from weewx.reportengine import ReportGenerator
from weeutil.weeutil import to_bool

try:
    import user.celestial_sky as celestial_sky  # type: ignore[import-not-found]
except ImportError:
    import celestial_sky  # type: ignore[import-not-found, no-redef]
try:
    from user.celestial import (CELESTIAL_VERSION, PANELS_KEY,  # type: ignore[import-not-found]
                                PANEL_GROUPS, misplaced_panels_key, panels_as_written,
                                panels_value, pending_groups, report_groups)
except ImportError:
    from celestial import (CELESTIAL_VERSION, PANELS_KEY,  # type: ignore[import-not-found, no-redef]
                           PANEL_GROUPS, misplaced_panels_key, panels_as_written,
                           panels_value, pending_groups, report_groups)

log = logging.getLogger(__name__)

# The staggered set's geometry: an archive interval is covered by at most
# MAX_SLOTS backdrops, never closer than MIN_STEP_S apart; a report that
# cannot say its interval is treated as the five-minute default.
DEFAULT_INTERVAL_S = 300
MIN_STEP_S = 60
MAX_SLOTS = 10

DEFAULT_PREFIX = 'dome-svg'
# The grammar of a set's prefix (a file name the page's markup carries
# and the javascript fetches) and of each segment of its directory:
# letters, digits, - _ . -- never a slash, a quote or a leading dot.
_PLAIN_NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
_DIRECTORY_RE = re.compile(r'%s(/%s)*/?' % (_PLAIN_NAME_RE.pattern, _PLAIN_NAME_RE.pattern))
# The default set's pass fragment keeps the name every 8.x page fetches.
DEFAULT_PASS_NAME = 'pass-chart.txt'

# Kilometers and miles per IAU astronomical unit: the page's distances
# arrive as raw au (weewx-loopdata almanac fields) and convert to the
# report's distance unit in the browser.  windrun stands in for
# group_distance -- this extension registers no observation types -- so
# the report's windrun unit decides which.  A test ties these to the
# template's own copies.
PER_AU_KM = 1.4959787e8
PER_AU_MILE = 9.2955807e7

# The Geocentric roster's bodies, nearest tier first: moon and sun, the
# planets in orbital order, Proxima Centauri last (the configured comets
# join between Pluto and Proxima at render time).  celestial.js carries
# the same list as its GEO_BODIES; a test pins the two.
GEO_BODIES = ('moon', 'sun', 'mercury', 'venus', 'mars', 'jupiter', 'saturn',
              'uranus', 'neptune', 'pluto', 'proxima_centauri')

# The bodies whose display names the javascript composes with (dial
# labels and tooltips), from the report's [Almanac] section: the
# roster's, with Earth (the dial's center) for Proxima (whose label is
# the short [Texts] one).
LABEL_BODIES = GEO_BODIES[:-1] + ('earth',)

# The countdown row's windowed guests -- the season, apsis, supermoon,
# eclipse and comet-perihelion chips -- first-paint visible only this
# close to their event; celestial.js's CHIP_WINDOW_SEC is the same
# number and a test pins the two.
CHIP_WINDOW_S = 30 * 86400

# The install pointer the panels' hints link.
SKYFIELD_LINK = '<a href="https://github.com/chaunceygardiner/weewx-skyfield">weewx-skyfield</a>'

# The consumer contract's marker: every panel's root element carries
# data-celestial="<version>" -- the version that rendered it, so a page
# in another skin says which celestial its panels came from, and a
# consumer's own tests can find the roots without knowing the ids.  The
# roots: the countdown row, the Geocentric's .geo-body, the dome's
# #dome-wrap, the chart's #pass-wrap and each satellite roster.  A
# panel's install hint is a sibling BEFORE its root, never inside it,
# and a panel with nothing to render emits no root and no marker.
PANEL_MARK = 'data-celestial="%s"' % CELESTIAL_VERSION

# The one place a panel sends a reader to the manual: the dome's frozen
# star field, the one condition the page cannot fix by itself.
FROZEN_LINK = 'https://chaunceygardiner.github.io/weewx-celestial/troubleshooting.html#the-star-field-is-frozen'

# The [Texts] strings the javascript composes, keyed by their English --
# each looked up through _t and fed to celestial.js as its T table (see
# config_dict).  Keys are single-line literals: the test suite reads
# this tuple, with the template's $gettext literals, to enforce that
# lang/en.conf ships exactly the keys that render, in both directions.
# A key the javascript looks up must match its entry here character for
# character (non-ASCII spelled with \u escapes on the javascript side,
# which is how json.dumps escapes it).
LIVE_TEXTS = (
    # The roster's live cells and the badge.
    'alt {alt}°',
    'below horizon',
    '{dist} au',
    'receding',
    'approaching',
    'LIVE',
    '{age}s ago',
    'NO DATA (HTTP {status}) — check loop_data_file',
    'BAD DATA — check loop_data_file',
    'OFFLINE',
    'CLICK-ME',
    '{ly} ly',
    'Proxima',
    # The satellite rows' live strings -- countdown, pass description and
    # the honest empty states -- shared verbatim with weewx-skyfield's Sky
    # page (its translations are mined into this skin's lang files).
    'overhead now',
    'in {m} min',
    'in {h} h',
    'in {n} day',
    'in {n} days',
    'just set',
    'appears {rise} · peaks {alt}° {culm} · disappears {set} · {m} min',
    'no visible pass in the coming week',
    'no pass in the coming week',
    'visible',
    'not visible',
    'no usable orbital elements — see the weewxd log',
    # The countdown chips' live strings.  The eclipse vocabulary and the
    # perihelion label are shared verbatim with weewx-skyfield's Sky page;
    # sunset/sunrise/darkness/supermoon/appears in and the day-count
    # wrapper are celestial's own wording.
    'sunset',
    'sunrise',
    'darkness begins',
    'darkness ends',
    'spring begins',
    'summer begins',
    'autumn begins',
    'winter begins',
    'Earth perihelion',
    'Earth aphelion',
    'supermoon',
    'appears in',
    '{d}d {h}h {m}m',
    'lunar eclipse',
    'solar eclipse',
    'penumbral',
    'partial',
    'total',
    'annular',
    '{name} perihelion',
    # The comet dial tooltip's magnitude suffix (the rest of the tooltip
    # reuses the roster keys above).
    'mag {mag}',
    # The dome's own health line: shown when the backdrop refetches stop
    # landing and the star field is no longer advancing.  The reason is
    # the last refetch's outcome, so the line names the fault rather than
    # just the symptom.  {file} is filled in with the fragment that
    # actually failed -- usually a numbered slot -- so the placeholder
    # must survive translation intact.
    'Star field frozen — this sky is from {time} ({why})',
    'no newer backdrop has arrived',
    '{file} returns HTTP {status}',
    '{file} is not a sky fragment',
    '{file} is empty',
    'no response for {file}',
    "{file} is stamped ahead of the station's clock",
)


def _panel_guard(fallback: Any = '', label: Optional[str] = None) -> Callable:
    """Wrap a $celestial render method so a failure costs only its own
    panel: the error is logged with its traceback (the frame is what
    identifies the bug) and the panel renders as `fallback`.  Without
    this one raising tag takes out the whole page for that report cycle
    -- and a page that does not generate is the worse failure (7.2's
    lesson).  `label` names what failed in the log where the method's
    own name would mislead (a skyfield drawing made on the page's
    behalf).  The fragment renders are deliberately NOT guarded: the
    generator keeps the old file when one raises."""
    def decorate(method: Callable) -> Callable:
        @functools.wraps(method)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return method(self, *args, **kwargs)
            except Exception as e:
                log.error('%s failed (%s: %s); rendering that panel blank.',
                          label or 'celestial.' + method.__name__, type(e).__name__, e)
                weeutil.logger.log_traceback(log.error, '****  ')
                return fallback
        return wrapper
    return decorate


def _esc(s: Any) -> str:
    """Markup-escaped text for a value the panels do not own: a body's,
    satellite's or comet's display name (the report's [Almanac] section,
    or skyfield's label), a compass ordinal, a shower's name -- anything
    a report or a lang file controls that lands in the panels' markup.
    Quotes too, as weewx-skyfield's own escape does, since such text can
    land in an attribute.  [Texts] strings are never escaped: they carry
    markup of their own by design, and celestial.js paints them the same
    way."""
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def station_time_zone() -> str:
    """The station's IANA time zone, auto-detected on the machine the
    report is generated on: /etc/localtime is a symlink into the zoneinfo
    tree on Debian-family systems; /etc/timezone is the fallback.  Empty
    when neither yields a zone the tree carries (the javascript then falls
    back to the viewer's browser time zone)."""
    tz = ''
    try:
        tz = os.readlink('/etc/localtime').split('zoneinfo/')[-1]
    except Exception:
        pass
    if not tz:
        # Bare, like the include's #except: an undecodable byte in the
        # file is a ValueError, not an OSError, and a probe that raises
        # would cost the page its whole script block, where browser-local
        # is the fallback the page was designed with.
        try:
            with open('/etc/timezone') as fd:
                tz = fd.read().strip()
        except Exception:
            pass
    if tz and not os.path.exists('/usr/share/zoneinfo/' + tz):
        tz = ''
    return tz


def _number(value: Any, default: Any) -> Any:
    """An [Extras] number as the javascript should see it: an int when
    the option is written as one (refresh_rate = 2), a float otherwise,
    the default when the option is absent or not a number."""
    if value is None:
        return default
    try:
        return int(str(value))
    except ValueError:
        pass
    try:
        return float(str(value))
    except ValueError:
        return default


def almanac_texts(alm: Any) -> Dict[str, Any]:
    """The report's [Almanac] section -- the body names -- read out of
    the almanac's __dict__ and never as `alm.texts`: WeeWX only grew the
    attribute in 5.3 and this extension's floor is 5.2, where the plain
    lookup does NOT fail cleanly.  Almanac.__getattr__ walks the
    registered almanacs and PyEphem's catch-all hands back an
    AlmanacBinder for a "heavenly body" named texts, so the access
    succeeds, returns something truthy (a getattr() default can never
    fire) and the page dies one step later on .get.  __dict__ is the
    only lookup that tells the truth; on 5.2 it is empty and the bodies
    get their title-cased English tags."""
    texts = alm.__dict__.get('texts', {})
    return texts if isinstance(texts, dict) else {}


def distance_unit(alm: Any) -> Tuple[float, str]:
    """(per_au, label) for the report's distance unit: the number of the
    report's units in one astronomical unit and the unit's label, from
    the almanac's converter and formatter -- the report's own.  windrun
    stands in for group_distance (this extension registers no
    observation types), so 'km' or 'mile' is the report's windrun unit."""
    unit = alm.converter.getTargetUnit('windrun')[0]
    return (PER_AU_KM if unit == 'km' else PER_AU_MILE,
            str(alm.formatter.get_label_string(unit)))


def _hms(rem: int) -> str:
    """hh:mm:ss of a remaining time in seconds, inside the final day."""
    return '%02d:%02d:%02d' % (rem % 86400 // 3600, rem % 3600 // 60, rem % 60)


def _hm(ts: float) -> str:
    """The station-local clock time of an instant, as the chips' detail
    cell and the javascript's fmtHM paint it."""
    return time.strftime('%H:%M', time.localtime(ts))


def _soonest(first: Any, second: Any) -> Tuple[Any, Optional[int]]:
    """The sooner of two next-event instants and which it was (0 or 1),
    null-aware: an instant the almanac cannot serve is None and loses;
    both None -> (None, None).  Ties go to the first, as the javascript's
    min()s break them."""
    if first is not None and (second is None or first <= second):
        return first, 0
    if second is not None:
        return second, 1
    return None, None


def body_name(texts: Dict[str, Any], body: str) -> str:
    """A body's display name: the report's [Almanac] entry, else the
    tag title-cased with its underscores as spaces -- weewx-skyfield's
    own fallback for an unnamed tag, so every panel agrees (what WeeWX
    5.2 shows, having no [Almanac] texts)."""
    return str(texts.get(body, body.replace('_', ' ').title()))


def dome_slots(interval_s: Any) -> Tuple[int, int, int]:
    """The staggered set's geometry for an archive interval given in
    SECONDS: (interval, step, count).

    round(), not int(): the interval usually arrives through a unit
    conversion, which is floating point, so an hour-based report hands
    over 299.99988 and truncation would quietly cost the set a slot.
    A missing, unparsable or non-positive interval is the default, so a
    report that cannot say its interval still gets a whole set rather
    than an empty one.

    Ceil, not floor, for the count: the emission gate is offset <
    interval, so a step that does not divide the interval emits one more
    fragment than floor division declares -- a 350 s interval writes six
    60 s slots and once called itself five; the sixth was rendered every
    cycle and could never be asked for (the walk clamps to count - 1),
    so the station paid for a whole dome nobody could see and the last
    50 s of every cycle showed the slot before it.  The MAX_SLOTS cap
    stays: a very long interval just leaves a tail uncovered."""
    try:
        interval = int(round(float(interval_s)))
    except (TypeError, ValueError):
        interval = 0
    if interval <= 0:
        interval = DEFAULT_INTERVAL_S
    step = max(MIN_STEP_S, interval // MAX_SLOTS)
    count = min(MAX_SLOTS, max(1, -(-interval // step)))
    return interval, step, count


class FragmentSet(NamedTuple):
    """One declared set of fragments: its [CelestialFragments] name ('' for
    the default set, which no set= names -- it is what no set= means),
    the file-name prefix, the dome's label scale, its theme (None: the
    report's own), the directory under the report's HTML_ROOT its
    files are written into ('' for HTML_ROOT itself), which the page's
    markup carries and the javascript fetches from, wherever the page
    itself sits, and which fragments it writes at all -- `both` (the
    default), `dome` (the ten backdrops) or `pass` (the chart).  A skin
    that puts the dome on one page and the chart on another, at
    different label scales, needs a set for each; without `kind` each of
    them would write the other's fragments every cycle for nobody to
    fetch."""
    name: str
    prefix: str
    label_scale: float
    theme: Optional[str]
    directory: str = ''
    kind: str = 'both'


DEFAULT_SET = FragmentSet('', DEFAULT_PREFIX, 1.0, None)


def fragment_names(fs: FragmentSet) -> Tuple[List[str], str]:
    """The file names a set's PREFIX spells: the ten dome slots in slot
    order and the pass-chart fragment -- bare names, what the page's
    markup carries (data-dome-prefix, data-pass-fragment) beside the
    set's directory (data-dome-dir, data-pass-dir), from which the
    javascript builds the URL it fetches.  A pure function of the
    prefix, which is what the page's markup wants: `kind` says which of
    these the set actually writes, and that is written_names."""
    domes = ['%s.txt' % fs.prefix] + ['%s-%d.txt' % (fs.prefix, k)
                                      for k in range(1, MAX_SLOTS)]
    pass_name = (DEFAULT_PASS_NAME if fs.prefix == DEFAULT_PREFIX
                 else '%s-pass.txt' % fs.prefix)
    return domes, pass_name


def written_names(fs: FragmentSet) -> Tuple[List[str], str]:
    """What a set actually WRITES: fragment_names filtered by `kind`,
    empty where the kind excludes them.  The one site that answers that
    question, read by both callers who need it -- the generator, which
    writes exactly this, and fragment_sets, which refuses two sets that
    would write the same file.

    Those two disagreed until 9.0's first real consumer hit it: the
    generator honored `kind` and the collision check did not, so it
    arbitrated over names nobody writes and refused a legal set of
    sets.  A dome-only set on the dome-svg prefix spells its pass
    fragment `pass-chart.txt` (the default prefix's legacy name), which
    collided with a pass-only set whose prefix was, reasonably,
    pass-chart -- and the report then wrote no fragments at all.  One
    function, two readers, so they cannot drift again."""
    domes, pass_name = fragment_names(fs)
    return (domes if fs.kind in ('both', 'dome') else [],
            pass_name if fs.kind in ('both', 'pass') else '')


def fragment_sets(skin_dict: Any) -> List[FragmentSet]:
    """The sets a skin declares in [CelestialFragments], or the one
    default set when it declares none.  Refuses -- ValueError naming the
    sets -- two sets that would write the same file (the file names are
    the prefix's, so one prefix per set, whatever the directories), a
    prefix that is not a plain file name, a directory that is not a
    plain relative path (segments of the same grammar joined by /: no
    leading slash, no `..`, so the files stay under HTML_ROOT), a
    label_scale that is not a positive number,
    a theme that is not dark, light or auto and a scalar outside any
    [[set]] subsection: a bad declaration must be one loud failure at
    the first cycle,
    not ten silently overwritten files, or a silently dark set, every
    cycle.  A declared set may take the default prefix at any scale or
    theme: the page follows the set it names (dome_html), and a page
    naming none follows whatever set holds that prefix."""
    section = None
    try:
        section = skin_dict.get('CelestialFragments')
    except AttributeError:
        pass
    if not isinstance(section, dict):
        return [DEFAULT_SET]
    sets: List[FragmentSet] = []
    scalars = [str(k) for k in section if not isinstance(section[k], dict)]
    if scalars:
        # The obvious way to tune the default set -- label_scale = 1.4
        # straight under the section -- and silently the old set for ever
        # without this.
        raise ValueError('[CelestialFragments] carries %s outside a [[set]] subsection; a set '
                         'is a [[name]] subsection with prefix, label_scale, theme and directory'
                         % ', '.join(scalars))
    for name in section:
        sub = section[name]
        prefix = str(sub.get('prefix', DEFAULT_PREFIX)).strip() or DEFAULT_PREFIX
        if not _PLAIN_NAME_RE.fullmatch(prefix):
            # The prefix is a file name and an attribute value the page's
            # javascript reads back: one loud refusal, not a path with a
            # slash in it or a quote that ends the attribute.
            raise ValueError('[CelestialFragments] [[%s]] prefix = %r is not a plain file name '
                             '(letters, digits, - _ .)' % (name, sub.get('prefix')))
        try:
            label_scale = float(sub.get('label_scale', 1.0))
        except (TypeError, ValueError):
            label_scale = 0.0
        if not label_scale > 0:
            # skyfield multiplies every label's size by it: zero or less
            # is a dome with no labels, silently.
            raise ValueError('[CelestialFragments] [[%s]] label_scale = %r is not a positive number'
                             % (name, sub.get('label_scale')))
        theme = sub.get('theme')
        theme = str(theme).strip().lower() or None if theme is not None else None
        if theme not in (None, 'dark', 'light', 'auto'):
            raise ValueError('[CelestialFragments] [[%s]] theme = %r is not dark, light or auto'
                             % (name, sub.get('theme')))
        # The directory is joined under HTML_ROOT and never leaves it
        # (a trailing slash is forgiven): one loud refusal, not files
        # written somewhere else.
        directory = str(sub.get('directory', '') or '').strip()
        if directory and not _DIRECTORY_RE.fullmatch(directory):
            raise ValueError('[CelestialFragments] [[%s]] directory = %r is not a plain relative '
                             'path under HTML_ROOT (segments of letters, digits, - _ . '
                             'joined by /)' % (name, sub.get('directory')))
        kind = str(sub.get('kind', 'both') or 'both').strip().lower()
        if kind not in ('both', 'dome', 'pass'):
            raise ValueError('[CelestialFragments] [[%s]] kind = %r is not both, dome or pass'
                             % (name, sub.get('kind')))
        sets.append(FragmentSet(str(name), prefix, label_scale, theme,
                                directory.rstrip('/'), kind))
    if not sets:
        return [DEFAULT_SET]
    # Compare the FILES, not the prefixes: dome-svg beside dome-svg-1, or
    # foo beside foo-pass, share a file with distinct prefixes.  The
    # names, not the paths: a page naming no set follows the set on the
    # dome-svg prefix, and two such sets in two directories would leave
    # it following whichever was declared first.
    owner: Dict[str, str] = {}
    prefixes: Dict[str, str] = {}
    for fs in sets:
        # TWO rules, separately, because they guard different things and
        # enforcing them as one refused a legal skin.
        #
        # (1) No two sets WRITE the same file -- the real hazard, one set
        #     silently clobbering another's output.  Judged on what each
        #     set writes (written_names), not on what its prefix spells:
        #     a dome-only set never writes the pass fragment its prefix
        #     names, and a pass-only set never writes the ten dome slots.
        domes, pass_name = written_names(fs)
        for filename in domes + ([pass_name] if pass_name else []):
            if filename in owner:
                raise ValueError('[CelestialFragments] [[%s]] and [[%s]] would both write %s; '
                                 'give one of them its own prefix'
                                 % (owner[filename], fs.name, filename))
            owner[filename] = fs.name
        # (2) One set per prefix.  Not about clobbering -- rule 1 has
        #     that -- but about resolution: a page that names no set gets
        #     the set on the dome-svg prefix, so a second set on a prefix
        #     would make dome_html($almanac) pick whichever came first.
        if fs.prefix in prefixes:
            raise ValueError('[CelestialFragments] [[%s]] and [[%s]] both use prefix = %s; '
                             'a page that names no set finds its set by prefix, so one '
                             'set per prefix' % (prefixes[fs.prefix], fs.name, fs.prefix))
        prefixes[fs.prefix] = fs.name
    return sets


def page_root(filename: Any) -> str:
    """A page's route up to HTML_ROOT from its own path under it (core's
    $filename, 'astro/index.html' -> '../'; 'index.html' -> ''): one
    '../' per directory level.  None, or anything without a path, is
    '': the page fetches relative to itself."""
    path = str(filename or '').replace('\\', '/').strip('/')
    return '../' * path.count('/')


class Resolved(NamedTuple):
    """What a dome- or pass-family panel call stands on: see
    CelestialPage._resolve."""
    fs: Optional[FragmentSet]
    hint: str
    line: str

    @property
    def refused(self) -> bool:
        """Whether the set (or the section) was refused: the hint is the
        line the page shows in the panel's place, and there is no other
        reason for one."""
        return bool(self.hint)


class CelestialPage:
    """What `$celestial` is in a template: the page's panels, rendered
    from the report's skin dict and an almanac passed in.

    `sky_page` is the weewx-skyfield SkyPage serving the report, or None
    when there is none -- ALWAYS the celestial_sky shim's answer, the one
    presence-detection site (CelestialPanels and FragmentGenerator each
    ask the shim and pass the answer in).  One SkyPage per CelestialPage:
    its per-page memo of body evaluations (the multi-day satellite pass
    search above all) is what keeps ten fragments and a pass chart to
    one search per cycle."""

    def __init__(self, skin_dict: Optional[Any], sky_page: Optional[Any],
                 interval_s: Any = None, config_dict: Optional[Any] = None) -> None:
        self.skin_dict: Any = skin_dict if skin_dict is not None else {}
        self.sky_page: Optional[Any] = sky_page
        # The station's weewx.conf (not to be confused with the config
        # BLOCK, config_dict(alm)), for the report's own stanza -- what
        # the installer declares the panels' fields from, and what the
        # panels therefore judge their declaration by (None: a page no
        # report owns, which asks nothing).
        self.station_config: Optional[Any] = config_dict
        # The archive interval in SECONDS (None: the default), which the
        # dome panel's wrapper describes its fragment set by; the search
        # list reads it from the record at the page's instant, exactly
        # as the generator does for the fragments themselves.
        self.interval_s: Any = interval_s
        self._warned_theme = False
        # The panels whose fields this page's report does not declare,
        # each with the line it carries (resolved once per instance, and
        # logged then, once per fault).
        self._undeclared: Optional[Dict[str, str]] = None
        texts = self.skin_dict.get('Texts', {})
        self._texts: Any = texts if isinstance(texts, dict) else {}
        # Renders shared by two calls at one instant (the pass chart by
        # pass_html and pass_panel_hidden, the satellite rows by both
        # rosters and the predicate, the dome by dome_html and the
        # can-draw gate the other panels stand behind), so the two cannot
        # disagree and the almanac is asked once.
        self._memo: Dict[Tuple[Any, ...], Any] = {}
        # The [CelestialFragments] sets, resolved once per instance (once
        # per page render), and the refusals already logged for it: a
        # bad section or an undeclared set is one line per cycle, not one
        # per panel.
        self._sets: Optional[List[FragmentSet]] = None
        self._sets_error: Optional[str] = None
        self._refused: List[str] = []

    # -- translation -------------------------------------------------------

    def _t(self, key: str, **values: Any) -> str:
        """The [Texts] translation for key -- gettext-style, exactly as
        the template's $gettext: the English string IS the key, a missing
        (or empty) entry falls back to it -- with {name} placeholders
        filled by the rule celestial.js's fmt fills them live: every
        occurrence of a known name replaced by the value's text, anything
        else left as written, nothing ever raised.  So a translation that
        misspells a placeholder paints it literally at generation and
        again on every packet, the same bytes both times, where a Python
        .format would raise at generation and leave a chip hidden that
        the first packet then pops in.  A test transliterates fmt and
        pins the two together.  NOT escaped for markup, because $gettext
        never was and the page's keys carry markup of their own
        ("solid&nbsp;=&nbsp;above the horizon").  Call sites pass the key
        as a single-line literal: the test suite reads them from this
        source file, with LIVE_TEXTS, to enforce that lang/en.conf ships
        exactly the keys that render."""
        s = self._texts.get(key) or key
        if not isinstance(s, str):
            s = key
        for name, value in values.items():
            s = s.replace('{%s}' % name, str(value))
        return s

    # -- the skyfield sets -------------------------------------------------

    def satellite_names(self) -> List[str]:
        """The station's [Skyfield] [[Satellites]] tags, through skyfield
        2.0's public satellite_names(); [] without a SkyPage or on an
        older skyfield that has no method and no satellites."""
        try:
            return [str(n) for n in self.sky_page.satellite_names()]  # type: ignore[union-attr]
        except Exception:
            return []

    def comet_names(self) -> List[str]:
        """The station's [Skyfield] [[Comets]] tags, through skyfield 2.1's
        public comet_names(); [] without a SkyPage or on an older
        skyfield."""
        try:
            return [str(n) for n in self.sky_page.comet_names()]  # type: ignore[union-attr]
        except Exception:
            return []

    # -- the countdown row and the Geocentric ------------------------------
    #
    # The two panels celestial draws itself, first-painted here from the
    # report's almanac and kept live by celestial.js from loop data.
    # Every almanac read that fills a cell or a chip is guarded on its
    # own, exactly as the template guarded it through 8.5: a lesser
    # almanac (PyEphem has no Proxima and none of the skyfield-only
    # events; the built-in almanac has no extras at all) leaves that cell
    # empty or that chip hidden -- and on WeeWX 5.2 the skyfield-only
    # tags fail with KeyError, not AttributeError, so nothing here
    # narrows the except.  The reads a whole panel stands on (the
    # instant, the distance unit, the [Almanac] names, the satellite and
    # comet sets) sit under _panel_guard alone: a failure there costs
    # the panel, logged with its traceback, and the javascript then
    # finds no root element for it and leaves it alone.

    def _dhms(self, rem: int) -> str:
        """A countdown's shape, mirroring the javascript's fmtDHMS
        exactly (the first paint IS what the script would render for
        the generation instant): days-hours-minutes a day or more out,
        the hh:mm:ss clock inside the final day."""
        if rem >= 86400:
            return self._t('{d}d {h}h {m}m', d=rem // 86400, h=rem % 86400 // 3600,
                           m=rem % 3600 // 60)
        return _hms(rem)

    def _date(self, ts: float) -> str:
        """An event's date, station-local, in the report's [Texts] date
        shape."""
        return time.strftime(self._t('%b %-d'), time.localtime(ts))

    def _date_hm(self, ts: float) -> str:
        """An event's date and clock time, station-local."""
        return self._date(ts) + ' ' + _hm(ts)

    @staticmethod
    def _chip(chip_id: str, k: str, v: str, d: str, data: str = '',
              hidden: bool = False, attrs: str = '') -> str:
        """One countdown chip: the label (k), the countdown (v) and the
        detail (d) cells the javascript repaints by id, the
        generation-baked target instant(s) in `data` (data-ts, and
        data-set for the pass chip) and the hidden attribute."""
        return ('<div class="cel-count" id="%s"%s%s%s>'
                '<span class="cel-k" id="%s-k">%s</span>'
                '<span class="cel-v" id="%s-v">%s</span>'
                '<span class="cel-d" id="%s-d">%s</span></div>'
                % (chip_id, attrs, data, ' hidden' if hidden else '',
                   chip_id, k, chip_id, v, chip_id, d))

    def _pair_chip(self, chip_id: str, first: Any, second: Any, k_first: str,
                   k_second: str, now: float) -> str:
        """An always-on chip counting to the sooner of two next-events
        (sunset/sunrise, darkness begins/ends): the chip first-paints the
        countdown itself with the event's clock time as the detail, and
        its target bakes so a feed without the keys still counts;
        neither instant known -> hidden.  The pair is the engine's
        next_* pair, which loopdata's event expiry rolls one at a time,
        so the live layer's min() flips the chip from one to the other
        by itself."""
        ts, which = _soonest(first, second)
        k = v = d = data = ''
        if ts is not None:
            k = k_first if which == 0 else k_second
            v = self._dhms(max(0, int(ts - now)))
            d = _hm(ts)
            data = ' data-ts="%d"' % int(ts)
        return self._chip(chip_id, k, v, d, data, hidden=not k)

    def _guest_chip(self, chip_id: str, ts: Any, now: float, k: str = '',
                    detail_prefix: str = '') -> str:
        """A windowed guest (the season and apsis chips, supermoon,
        eclipse, a comet's perihelion): its target and label bake at any
        distance -- the javascript unhides the chip from the baked
        target the moment the window opens and repaints only its
        countdown, so a label baked only inside the window would leave
        a nameless chip -- and it first-paints VISIBLE, counting down,
        dated, only inside CHIP_WINDOW_S of the event.  No chip on the
        row may pop in on the first loop packet.  The date detail is
        generation-painted and never rewritten live, so first paint and
        live never differ in dress; `detail_prefix` dresses it (the
        eclipse's type)."""
        v = d = data = ''
        hidden = True
        if ts is not None:
            data = ' data-ts="%d"' % int(ts)
            rem = int(ts - now)
            if 0 <= rem <= CHIP_WINDOW_S:
                hidden = False
                v = self._dhms(rem)
                d = self._date_hm(ts)
                if detail_prefix:
                    d = detail_prefix + ' &middot; ' + d
        return self._chip(chip_id, k, v, d, data, hidden)

    def _eclipse_type(self, alm: Any) -> str:
        """The next eclipse's translated type, '' when the almanac cannot
        say: decoration, because its own loopdata group can lag the
        rolled instant, so a missing type is omitted rather than
        trusted."""
        try:
            ecl_type = str(alm.next_eclipse_type)
        except Exception:
            return ''
        return {'penumbral': self._t('penumbral'), 'partial': self._t('partial'),
                'total': self._t('total'), 'annular': self._t('annular')
                }.get(ecl_type, ecl_type)

    def _season_key(self, ts: float, north: bool) -> str:
        """The season an equinox or solstice begins, hemisphere-aware,
        named by the event's month (March/September equinoxes,
        June/December solstices -- unambiguous across zone shifts); the
        javascript's seasonKey, which rolls the label live, is the same
        table."""
        mo = int(time.strftime('%m', time.localtime(ts)))
        if 2 <= mo <= 4:
            return self._t('spring begins') if north else self._t('autumn begins')
        if 5 <= mo <= 7:
            return self._t('summer begins') if north else self._t('winter begins')
        if 8 <= mo <= 10:
            return self._t('autumn begins') if north else self._t('spring begins')
        return self._t('winter begins') if north else self._t('summer begins')

    def _declaration_line(self, panel: str) -> str:
        """The line a panel carries BEFORE its root when this page's
        report does not declare the fields it reads -- '' when it does.
        The question is the installer's, asked of the same weewx.conf
        (report_groups on the station's config_dict): a report running
        the Celestial skin declares every panel; any other report names
        the panels its page embeds with celestial_panels in its stanza,
        and a panel is declared when every group it reads is among what
        the named panels read (`celestial_panels = countdown` declares
        both groups, so an embedded Geocentric is declared too).  A
        panel that is not first-paints and then never moves, with
        nothing on the page to say why -- so the panel says why, and the
        weewxd log says it once per FAULT per cycle (the panels it costs
        named in the one line).  An invalid key costs every panel the
        line, on our own skin too; so does a key sitting where WeeWX
        merges it into every report instead of on the stanza
        (misplaced_panels_key, the installer's one receipt for it, on a
        page whose report carries none of its own).  A panel whose
        fields are named but not yet WRITTEN -- the key added and weewxd
        restarted without re-running the installer, a satellite added
        to [Skyfield] by hand -- carries the out-of-date line: the
        writer's own dry run (pending_groups) says which groups it
        would change, so the panel says what to run.  Every line ends
        with restarting weewxd, because the page judges from the
        configuration weewxd loaded at startup.  A page with no station
        config is no report's, and asks nothing."""
        if self._undeclared is None:
            self._undeclared = {}
            if self.station_config is not None:
                report = str(self.skin_dict.get('REPORT_NAME', '?'))
                groups, refusal = report_groups(self.station_config, report)
                if refusal is None and groups is None:
                    refusal = misplaced_panels_key(self.station_config)
                if refusal is not None:
                    log.error('%s; every panel of the page says so.', refusal)
                    line = self._t("This page's report carries an invalid celestial_panels — see the weewxd log.")
                    self._undeclared = {p: line for p in PANEL_GROUPS}
                else:
                    owned = groups or ()
                    pending = pending_groups(self.station_config, report)
                    missing: List[str] = []
                    stale: List[str] = []
                    for p, reads in PANEL_GROUPS.items():
                        if not all(g in owned for g in reads):
                            missing.append(p)
                            self._undeclared[p] = self._t("This page's report does not name the {panel} panel in celestial_panels, so its live fields are not declared — name it, re-run weectl extension install and restart weewxd.", panel=p)
                        elif any(g in pending for g in reads):
                            stale.append(p)
                            self._undeclared[p] = self._t("This page's report's field declaration is out of date — re-run weectl extension install (or the --add-satellite/--add-comet utility) and restart weewxd.")
                    value = panels_value(self.station_config, report)
                    if missing:
                        log.error('[StdReport] [[%s]] %s (%s) leaves the %s panel(s) this page '
                                  'embeds undeclared -- no named panel reads their fields; name '
                                  'them, re-run weectl extension install and restart weewxd.',
                                  report, PANELS_KEY,
                                  'absent' if value is None else '= %s' % panels_as_written(value),
                                  ', '.join(missing))
                    if stale:
                        log.error('[StdReport] [[%s]] names the %s panel(s) this page embeds but '
                                  'their fields are not declared under it yet: re-run weectl '
                                  'extension install (or the --add-satellite/--add-comet '
                                  'utility) and restart weewxd.', report, ', '.join(stale))
        line = self._undeclared.get(panel, '')
        return '<p class="cel-skyhint">%s</p>\n' % line if line else ''

    def _behind_line(self, line: str, html: str) -> str:
        """A panel's markup behind its declaration line; nothing behind
        nothing (a panel that renders nothing carries no line)."""
        return line + html if html else html

    @_panel_guard()
    def countdown_html(self, alm: Any) -> str:
        """Countdown central: the row of countdown chips the javascript
        renders on every loop packet (the page's clock is the packet's
        own stamp, so the chips move at loop cadence), each pure client
        arithmetic against an event-tier loopdata field -- computed once
        by the engine, cached until the event, zero cost at that cadence.
        The chip family (.countdown/.count) is weewx-skyfield's, kept in
        step.

        A countdown's precision follows its horizon (fmtDHMS in
        celestial.js owns the shape; these first paints mirror it, and
        are exactly what it renders for the generation instant, which is
        the page's clock until the first packet): a day or more out it
        reads days-hours-minutes, inside the final day the hh:mm:ss
        clock.  Dual-source like the roster: the always-on chips
        first-paint the COUNTDOWN ITSELF -- the remaining time at
        generation -- with the event's clock time or date as the small
        detail (a countdown chip whose only number is a wall-clock time
        reads as remaining time and lies).  A lesser almanac first-paints
        a chip hidden and the javascript unhides it when the loop feed
        serves it.  The windowed guests are _guest_chip's story.

        Each chip's almanac reads are its own guarded step (`add`): a
        chip whose event the almanac cannot serve renders hidden and
        empty, and the row goes on.  The chips are built in display
        order."""
        now = alm.time_ts
        chips: List[str] = []

        def add(chip_id: str, build: Callable[[], str], k: str = '') -> None:
            """Append the chip `build` renders, or -- when a read it
            depends on raises -- the hidden empty chip, carrying `k` for
            the chips whose label bakes regardless (supermoon)."""
            try:
                chips.append(build())
            except Exception:
                chips.append(self._chip(chip_id, k, '', '', hidden=True))

        def pass_chip() -> str:
            # The soonest visible pass across the configured satellites
            # -- the same pick the live layer makes -- so all the row's
            # chips stand from the first byte; its rise and set instants
            # bake so a feed without the pass keys still has a target to
            # count from and roll into "overhead now".  A satellite whose
            # tags error is skipped, as in the rosters.
            best_rise = best_set = None
            best_label = ''
            for sn in self.satellite_names():
                try:
                    so = getattr(alm, sn)
                    sp = so.next_visible_pass
                    sr = sp.rise.raw
                    if sr is not None and (best_rise is None or sr < best_rise):
                        best_rise = sr
                        best_set = sp.set.raw
                        best_label = _esc(so.label)
                except Exception:
                    pass
            if best_rise is None:
                return self._chip('chip-pass', '', '', '', hidden=True)
            data = ' data-ts="%d"' % int(best_rise)
            if best_set is not None:
                data += ' data-set="%d"' % int(best_set)
            if best_set is not None and best_rise <= now < best_set:
                v, d = '', self._t('overhead now')
            else:
                v, d = self._dhms(max(0, int(best_rise - now))), self._t('appears in')
            return self._chip('chip-pass', best_label, v, d, data)

        def shower_chip() -> str:
            # The detail line is generation-time static: the peak's date
            # and the moon's illumination AT the peak (the almanac
            # time-traveled), the one fact that decides whether a shower
            # year is worth an alarm.  The javascript clears it if the
            # live label rolls to a different shower before the next
            # report cycle (data-shower-label).  The label stands once
            # read: a peak the almanac serves but a moon it cannot still
            # names the chip, with its countdown (8.5's order).
            label = v = note = data = ''
            try:
                peak = alm.next_meteor_shower.peak.raw
                if peak is not None:
                    label = _esc(alm.next_meteor_shower.label)
                    v = self._dhms(max(0, int(peak - now)))
                    data = ' data-ts="%d"' % int(peak)
                    pct = int(round(alm(almanac_time=int(peak)).moon.phase))
                    note = self._date(peak) + ' &middot; ' + self._t('moon {pct}%', pct=pct)
            except Exception:
                pass
            return self._chip('chip-shower', label, v, note, data, hidden=not label,
                              attrs=' data-shower-label="%s"' % label)

        def season_chip() -> str:
            # Equinox or solstice, whichever next, named by the season it
            # begins -- the one event whose count-to-zero is exact to the
            # second.
            ts, _which = _soonest(alm.next_equinox.raw, alm.next_solstice.raw)
            k = '' if ts is None else self._season_key(ts, float(alm.lat) >= 0)
            return self._guest_chip('chip-season', ts, now, k)

        def apsis_chip() -> str:
            # The season chip's twin: perihelion or aphelion, whichever
            # next -- early January and early July, minute-class extremum
            # instants (weewx-skyfield 2.1's next_perihelion/next_aphelion,
            # built on this page's ask).
            ts, which = _soonest(alm.next_perihelion.raw, alm.next_aphelion.raw)
            k = ('' if ts is None else
                 self._t('Earth perihelion') if which == 0 else self._t('Earth aphelion'))
            return self._guest_chip('chip-apsis', ts, now, k)

        def eclipse_chip() -> str:
            # The kind names the chip, the type dresses its detail.
            ts = alm.next_eclipse.raw
            kind = str(alm.next_eclipse_kind)
            if kind not in ('lunar', 'solar'):
                ts = None
            k = ('' if ts is None else
                 self._t('lunar eclipse') if kind == 'lunar' else self._t('solar eclipse'))
            return self._guest_chip('chip-eclipse', ts, now, k,
                                    detail_prefix=self._eclipse_type(alm))

        def comet_chip(comet: str) -> str:
            # A comet's perihelion: named through skyfield's label, the
            # roster row's source too.  (Through 8.5 the label baked only
            # while the chip showed, and a chip the script unhid from its
            # baked target was nameless until the feed served the key.)
            cp_obj = getattr(alm, comet)
            return self._guest_chip('chip-peri-' + comet, cp_obj.perihelion.raw, now,
                                    self._t('{name} perihelion', name=_esc(cp_obj.label)))

        add('chip-pass', pass_chip)
        # Sunset or sunrise, whichever next.
        add('chip-sun', lambda: self._pair_chip(
            'chip-sun', alm.sun.next_setting.raw, alm.sun.next_rising.raw,
            self._t('sunset'), self._t('sunrise'), now))
        chips.append(shower_chip())
        # Astronomical darkness, symmetric with the sun chip: darkness
        # begins at the -18 sunset, ends at the -18 sunrise -- stargazers
        # care about both ends of the window.  A high-latitude summer
        # where -18 never comes serves nulls and the chip stays hidden.
        add('chip-dark', lambda: self._pair_chip(
            'chip-dark', alm(horizon=-18).sun.next_setting.raw,
            alm(horizon=-18).sun.next_rising.raw,
            self._t('darkness begins'), self._t('darkness ends'), now))
        add('chip-season', season_chip)
        add('chip-apsis', apsis_chip)
        # The supermoon guest carries its label whatever the almanac says.
        add('chip-super', lambda: self._guest_chip(
            'chip-super', alm.next_supermoon.raw, now, self._t('supermoon')),
            k=self._t('supermoon'))
        add('chip-eclipse', eclipse_chip)
        # One perihelion chip per configured comet, the last of the
        # windowed guests.
        for comet in self.comet_names():
            add('chip-peri-' + comet, functools.partial(comet_chip, comet))

        return self._behind_line(self._declaration_line('countdown'),
                                 '<div class="cel-countdown cel-mono" id="countdown" %s>\n' % PANEL_MARK
                                 + ''.join('  %s\n' % chip for chip in chips)
                                 + '</div>')

    @staticmethod
    def _comet_label(alm: Any, comet: str, texts: Dict[str, Any]) -> str:
        """A comet's display name, markup-escaped: skyfield's own label
        for the tag -- the [Almanac] entry, else the tag title-cased with
        its underscores as spaces -- so the roster row and the perihelion
        chip (which reads the same label) never disagree.  A comet row
        exists only when skyfield serves the page, so this is safe on
        WeeWX 5.2; body_name, the same rule, covers a label that raises."""
        try:
            return _esc(getattr(alm, comet).label)
        except Exception:
            return _esc(body_name(texts, comet))

    @_panel_guard()
    def geocentric_html(self, alm: Any) -> str:
        """The Geocentric: the dial and the roster.  The dial is an empty
        SVG the javascript builds on the first loop packet (positions,
        trails and rates are javascript-only -- the rates and trails need
        two packets to derive motion).  The roster's distance, AU and
        altitude cells are dual-source: first-painted here from whatever
        capable report almanac is installed (weewx-skyfield for full
        fidelity including Proxima Centauri, or PyEphem), then kept live
        from loop data.  Each body's cells are one guarded read, so an
        almanac that cannot serve a body leaves its row empty; the reads
        the whole roster stands on (hasExtras, the distance unit, the
        [Almanac] names, the comet set) are under the panel guard alone.
        Without an extended almanac the panel carries an install hint
        and the roster first-paints empty for the javascript to fill, as
        always.

        Display names come from the report's [Almanac] section (the
        same source as $almanac.<body>.label), falling back to the
        title-cased tag; a comet's is skyfield's own label, the
        perihelion chip's source; Proxima Centauri uses the short [Texts]
        label so the row never overflows.  The value cells share their
        [Texts] keys with the javascript, so first paint and live
        updates always agree.  The configured comets join the roster
        between Pluto and Proxima -- the roster reads nearest-tier
        outward, and a comet at tens of au belongs among the planets,
        not past the stellar rim -- same row anatomy, the shared brass
        comet chip (comet tags are dynamic, so per-tag color classes
        cannot exist): the guarded cells leave an elementless comet's
        row honestly empty (MPC drops faded comets; absence, never the
        string "None").  Distance-cell ids are the loop keys verbatim
        (almanac.<body>.earth_distance); the derived cells use
        geo-rate/-au/-alt/-row-<body>."""
        extras = bool(alm.hasExtras)
        per_au, distance_label = distance_unit(alm)
        texts = almanac_texts(alm)
        comets = self.comet_names()
        out: List[str] = []
        if not extras:
            out.append('<p class="cel-skyhint">%s</p>' % self._t(
                "Install {skyfield} (strongly recommended, and required for Proxima Centauri) or PyEphem so the almanac can serve this panel's positions and distances.",
                skyfield=SKYFIELD_LINK))
        out.append('<div class="cel-geo-body" %s>' % PANEL_MARK)
        out.append('  <div>')
        out.append('    <svg id="dial" viewBox="0 0 660 660" role="img"')
        out.append('         aria-label="%s"></svg>' % self._t(
            'Geocentric chart: bodies placed by compass azimuth and log distance from Earth'))
        out.append('    <p class="cel-caption cel-dialcaption">%s · %s</p>' % (
            self._t("plan view — compass bearing, east to the right · rings step ×10 in distance · solid&nbsp;=&nbsp;above the horizon, dashed&nbsp;=&nbsp;below · trails show the last hour of motion"),
            self._t("Hover or tap any mark for its coordinates.")))
        out.append('  </div>')
        out.append('  <div class="cel-roster cel-mono">')
        for body in GEO_BODIES[:-1] + tuple(comets) + GEO_BODIES[-1:]:
            chip_cls = 'cel-chip-comet' if body in comets else 'cel-chip-' + body
            if body == 'proxima_centauri':
                display_name = self._t('Proxima')
            elif body in comets:
                display_name = self._comet_label(alm, body, texts)
            else:
                display_name = _esc(body_name(texts, body))
            dist_html = au_html = alt_html = below_cls = ''
            if extras:
                try:
                    body_obj = getattr(alm, body)
                    au_val = body_obj.earth_distance
                    alt_val = body_obj.alt
                    dist_html = '{:,.0f}'.format(au_val * per_au)
                    au_str = ('%.1f' % au_val) if au_val >= 1000 else ('%.6f' % au_val)
                    au_html = self._t('{dist} au', dist=au_str)
                    if alt_val < 0:
                        alt_html = self._t('below horizon')
                        below_cls = ' cel-below'
                    else:
                        alt_html = self._t('alt {alt}°', alt='%.1f' % alt_val)
                except Exception:
                    pass
            out.append('    <div class="cel-row%s" id="geo-row-%s">' % (below_cls, body))
            out.append('      <span class="cel-bname"><span class="cel-chip %s"></span>%s</span>'
                       % (chip_cls, display_name))
            out.append('      <span class="cel-odo"><span id="almanac.%s.earth_distance">%s</span>'
                       '<span class="cel-unit">%s</span></span>' % (body, dist_html, distance_label))
            out.append('      <span class="cel-rsub"><span id="geo-rate-%s"></span>'
                       '<span id="geo-au-%s">%s</span><span id="geo-alt-%s">%s</span></span>'
                       % (body, body, au_html, body, alt_html))
            out.append('    </div>')
        out.append('  </div>')
        out.append('</div>')
        return self._behind_line(self._declaration_line('geocentric'), '\n'.join(out))

    # -- the script ----------------------------------------------------------

    def config_dict(self, alm: Any, filename: Any = None) -> Dict[str, Any]:
        """What celestial.js is started with: every per-report value the
        8.5 include baked into the script, as one dict (config_script
        serializes it).  The keys are contract -- additive only inside a
        major version -- and a test pins them.  Everything comes from the
        report's skin dict and the almanac the page is rendered from:
        `alm.lat`, `alm.time_ts`, its formatter and converter (the
        report's own, which core WeeWX builds the almanac with) and its
        [Almanac] names (almanac_texts: read out of __dict__, never as
        `alm.texts`, which WeeWX 5.2 cannot serve cleanly) -- plus
        `filename`, core's $filename: the page's own path under
        HTML_ROOT ('astro/index.html'), from which `root` is the page's
        route up to HTML_ROOT ('../' per level), where every fragment
        set is written.  None (a page that passes nothing) is '' --
        fetch relative to the page."""
        extras = self.skin_dict.get('Extras', {})
        if not isinstance(extras, dict):
            extras = {}
        time_zone = extras.get('time_zone')
        texts = almanac_texts(alm)
        ords = alm.formatter.ordinate_names
        per_au, dist_label = distance_unit(alm)
        return {
            'version': CELESTIAL_VERSION,
            'page_update_pwd': str(extras.get('page_update_pwd', 'foo')),
            'refresh_rate': _number(extras.get('refresh_rate'), 2),
            'expiration_time': _number(extras.get('expiration_time'), 24),
            # The option overrides the station's detected zone ('browser'
            # forces the viewer's, resolved on the javascript side).
            'time_zone': station_time_zone() if time_zone is None else str(time_zone),
            'station_lat': float(alm.lat),
            'gen_ts': int(alm.time_ts),
            'per_au': per_au,
            'dist_label': dist_label,
            # The language only, as core's $lang serves it: 'en', not
            # 'en_AU.utf8'.
            'locale': str(self.skin_dict.get('lang', 'en')).split('_')[0],
            'body_labels': {b: body_name(texts, b) for b in LABEL_BODIES},
            'cardinals': [str(ords[i]) for i in (0, 4, 8, 12)],
            'texts': {key: self._t(key) for key in LIVE_TEXTS},
            'sat_names': self.satellite_names(),
            'comet_names': self.comet_names(),
            'report_name': str(self.skin_dict.get('REPORT_NAME', '')),
            # Absent, the javascript polls nothing and the badge says BAD
            # DATA, naming the option.
            'loop_data_file': str(extras.get('loop_data_file', '')),
            # The theme the page is generated on ('dark' or 'light'):
            # what the javascript compares each refetched fragment's
            # data-page-theme with to see the theme = auto flip -- from
            # the config, not the page's markup, so a consumer's chrome
            # owes the script nothing.
            'theme': self.theme(alm),
            # The page's route up to HTML_ROOT, where every fragment set
            # is written: the script fetches root + the set's directory
            # + the file name, so the page may sit anywhere under
            # HTML_ROOT.
            'root': page_root(filename),
        }

    @_panel_guard()
    def config_script(self, alm: Any, filename: Any = None) -> str:
        """The page-level <script> block: the config, through json.dumps
        (which backslash-u-escapes non-ASCII, so the report's html_entities
        encoding can never touch a label), and the celestial.start call.
        json.dumps leaves '/' alone, so '</' is escaped by hand: no string
        in the config -- a report name, a password -- can close the block
        early.  Guarded: a failure costs the live layer, never the page."""
        cfg = json.dumps(self.config_dict(alm, filename), sort_keys=True, indent=2)
        return '<script>\ncelestial.start(%s);\n</script>' % cfg.replace('</', '<\\/')

    # -- the sky page and the plate ----------------------------------------

    def theme(self, alm: Any, fs: FragmentSet = DEFAULT_SET) -> str:
        """The resolved theme, 'dark' or 'light', of the page or of a
        set -- the module's one resolution site, which the page's root
        class (theme_class), the dome and the pass chart and every
        fragment all read.  A set's dark or light is itself; a set's
        auto follows the sun at the page's instant; a set on the
        report's theme (the default set) is the report's option,
        resolved by weewx-skyfield: `auto` is skyfield's own sunrise
        logic, not a second copy of it.  No SkyPage to ask is dark, and
        so is a weewx-skyfield too old to have theme() -- quietly, since
        there is no way to know whether anyone asked for one.  An
        unusable report option is dark too, with a warning logged ONCE
        per instance -- so once per page render and once per generator
        cycle, never once per fragment -- because skyfield RAISES on an
        unknown theme by design and a typo would otherwise render the
        page dark for ever with nothing in the log.  (A set's own theme
        cannot be unusable: fragment_sets refuses one.)"""
        if fs.theme in ('dark', 'light'):
            return fs.theme
        sp = self.sky_page
        if sp is None or not hasattr(sp, 'theme'):
            return 'dark'
        if fs.theme == 'auto':
            try:
                return 'light' if sp.sun_is_up(alm) else 'dark'
            except Exception:
                return 'dark'
        try:
            return 'light' if str(sp.theme(alm)) == 'light' else 'dark'
        except Exception:
            if not self._warned_theme:
                self._warned_theme = True
                log.warning('The Celestial report has an unusable theme option; rendering '
                            'the dark plate.  Valid values are dark, light and auto.')
            return 'dark'

    def palette(self, alm: Any, fs: FragmentSet = DEFAULT_SET) -> str:
        """The skyfield palette name matching .theme: 'light' on the light
        theme, 'night' otherwise."""
        return 'light' if self.theme(alm, fs) == 'light' else 'night'

    def theme_class(self, alm: Any) -> str:
        """The class for the page's root element -- 'theme-dark' or
        'theme-light' -- which is what the stylesheet's plates hang on."""
        return 'theme-' + self.theme(alm)

    # -- the dome, the Next Visible Pass and their rosters ------------------
    #
    # The two panels weewx-skyfield draws, embedded per report cycle
    # through the guarded $sky_page (the real SkyPage when skyfield is
    # installed, else None -- and dome_svg's own guard returns '' when
    # the skyfield almanac is not actually registered, so one emptiness
    # test covers both), and the satellite rosters beside them.  The
    # dome is sky-chart orientation -- north top, EAST LEFT, agreeing
    # with skyfield's own Sky page and deliberately opposite the dial's
    # map-convention plan view; do not harmonize them.  celestial.js
    # refetches the fragments the FragmentGenerator writes each cycle
    # (the dome's staggered set, the pass chart) and nudges the dome's
    # sun/moon/planet marks at loop rates between refetches through
    # their data-body hooks (skyfield 2.0's consumer contract);
    # satellites are the genuinely live layer.

    def _set(self, name: str, method: str) -> Optional[FragmentSet]:
        """The declared fragment set a dome_html/pass_html call names:
        '' is the set on the default prefix, dome-svg -- the one default
        set when the skin declares none.  A set the skin does not declare
        is refused, the name in the log, never answered with the default:
        the page would first-paint one set and refetch another's files.
        A bad [CelestialFragments] section is refused the same way, with
        the generator's own message (it logs the same one per cycle)."""
        if self._sets is None and self._sets_error is None:
            try:
                self._sets = fragment_sets(self.skin_dict)
            except ValueError as e:
                self._sets_error = str(e)
        name = str(name or '').strip()
        if self._sets is None:
            if '' not in self._refused:
                self._refused.append('')
                log.error('%s; the dome and pass panels say so.', self._sets_error)
            return None
        for fs in self._sets:
            if (fs.name == name) if name else (fs.prefix == DEFAULT_PREFIX):
                return fs
        if name not in self._refused:
            self._refused.append(name)
            declared = ', '.join(fs.name for fs in self._sets)
            if name:
                log.error('celestial.%s names the fragment set %r, which [CelestialFragments] '
                          'does not declare (declared: %s); the panel says so.',
                          method, name, declared)
            else:
                log.error('celestial.%s names no fragment set and [CelestialFragments] declares '
                          'none on the %s prefix (declared: %s); name one with set=..., or '
                          'declare a set with prefix = %s for this page; the panel says so.',
                          method, DEFAULT_PREFIX, declared, DEFAULT_PREFIX)
        return None

    def _resolve(self, alm: Any, set: str, method: str, panel: str) -> 'Resolved':
        """What a panel call stands on (Resolved): the set when a SkyPage
        serves the page, the skin resolves the name and the sky can be
        drawn (_can_draw), else None; `refused` says the name (or the
        section) was the fault, and `hint` is then the line the page
        shows in the panel's place -- from EVERY panel that asks, so no
        answer depends on which panel asked first (a broken
        configuration says so wherever a panel stands); and `line`, the
        panel's declaration line (_declaration_line, '' when its fields
        are declared), which the dome and the chart carry before their
        root and pass_panel_hidden counts as something to show -- every
        state a pass-family method must know about lives here, so none
        can miss one.  A sky that cannot be drawn is reported first,
        whatever the set: the almanac is what the owner must fix before
        the section (the set's log line is still written).  Without a
        SkyPage or a drawable sky the hint is '' here: the dome's
        install hint is dome_html's own."""
        line = self._declaration_line(panel)
        if self.sky_page is None:
            return Resolved(None, '', line)
        fs = self._set(set, method)
        if not self._can_draw(alm, fs if fs is not None else DEFAULT_SET):
            return Resolved(None, '', line)
        if fs is not None and fs.kind not in ('both', panel):
            # The set is declared, but declared for the OTHER panel, so
            # the generator writes none of the fragments this one would
            # refetch: without this the panel first-paints from the
            # almanac and then 404s for ever, one console line and
            # nothing on the page to say why -- the silent-death shape
            # every other state here exists to prevent.  Refused as the
            # set fault it is, sharing the missing-or-invalid line (a
            # page cannot act on the difference: the answer is the same,
            # look at [CelestialFragments]), with the reason in the log.
            refusal = 'kind:%s:%s' % (fs.name, panel)
            if refusal not in self._refused:
                self._refused.append(refusal)
                log.error('celestial.%s names the fragment set %r, which is declared '
                          'kind = %s and writes no %s fragment; declare kind = both, or '
                          'name a set that writes one; the panel says so.',
                          method, fs.name, fs.kind, panel)
            fs = None
        if fs is None:
            return Resolved(None, '<p class="cel-skyhint">%s</p>' % self._t(
                "The page's fragment set is missing or invalid in [CelestialFragments] — see the weewxd log."), line)
        return Resolved(fs, '', line)

    def _dome_svg(self, alm: Any, fs: FragmentSet) -> str:
        """The set's dome at the page's instant, once: skyfield's dome_svg
        on the set's plate and scale, '' without a SkyPage or when the
        drawing fails (skyfield's own guard, or _draw_dome's)."""
        palette = self.palette(alm, fs)
        key = ('dome', id(alm), int(alm.time_ts), fs.name, palette)
        if key not in self._memo:
            self._memo[key] = self._draw_dome(alm, fs, palette)
        return self._memo[key]

    @_panel_guard(label='weewx-skyfield dome_svg')
    def _draw_dome(self, alm: Any, fs: FragmentSet, palette: str) -> str:
        """skyfield's dome for the page, '' when it raises (skyfield's own
        methods are guarded and return '' on failure, so a raise here is
        a SkyPage without that guard -- an older weewx-skyfield hitting
        its own WeeWX incompatibility -- and the dome then degrades to
        its install hint exactly as without one, logged with the
        traceback, as the template's bare #try around the same call did
        through 8.5 minus the log).  The fragments are NOT drawn through
        this: the generator keeps the old file when a render raises."""
        sp = self.sky_page
        if sp is None:
            return ''
        return str(sp.dome_svg(alm, palette=palette, label_scale=fs.label_scale))

    def _can_draw(self, alm: Any, fs: FragmentSet) -> bool:
        """Whether the sky can be drawn -- the gate the pass panel and both
        rosters stand behind, exactly as the template's `#if $dome_html`
        gated them through 8.5, so the three panels always agree (a page
        on the PyEphem or built-in tier with weewx-skyfield merely
        installed would otherwise carry an empty pass panel polled every
        five minutes for ever, and satellite rows under an install
        hint).  The answer is the SkyPage's own: weewx-skyfield 2.3.4's
        can_draw(), the test dome_svg stands on, taken the way $sky_page
        itself is taken -- the shim stays the one presence-detection
        site and nothing here probes the registered almanacs.  An older
        skyfield without it is asked the 8.5 way: the set's memoized
        dome, '' (its guard's answer to any failure) meaning no; a page
        that renders a roster or the pass panel without the dome then
        pays that draw once per set per instant -- and so does a page
        whose [CelestialFragments] section is broken, whose refusal line
        is worth the draw that puts the almanac's fault before the
        section's (accepted cost: the section is fixed once, the hint is
        read every cycle until then)."""
        sp = self.sky_page
        if sp is None:
            return False
        if hasattr(sp, 'can_draw'):
            return bool(sp.can_draw())
        return bool(self._dome_svg(alm, fs))

    def _dome_wrapper(self, alm: Any, ts: int, slot: Optional[int], step: int, count: int,
                      interval: int, palette: str, svg: str) -> str:
        """The self-describing wrapper around a dome SVG, the ONE shape
        celestial.js's domeFragMeta parses: the page's own wrapper
        (dome_html, no slot -- that dome is the cycle instant, slot 0 by
        construction) and every refetched fragment (dome_fragment, its
        slot) come from here, so the two cannot disagree about an
        attribute the way two copies of the slot arithmetic once did.
        data-page-theme is the REPORT's resolved theme, the plate the
        page's chrome wears: the javascript reloads the page once when a
        fragment arrives carrying the other one (the report regenerated
        across sunrise on theme = auto), whatever plate the fragment set
        itself is on."""
        attrs = 'data-dome-ts="%d"' % ts
        if slot is not None:
            attrs += ' data-dome-slot="%d"' % slot
        attrs += (' data-dome-step="%d" data-dome-count="%d" data-dome-interval="%d" '
                  'data-dome-palette="%s" data-page-theme="%s"'
                  % (step, count, interval, palette, self.theme(alm)))
        return '<div class="domefrag" %s>%s</div>' % (attrs, svg)

    def _pass_chart(self, alm: Any, fs: FragmentSet) -> str:
        """The set's pass-chart fragment at the page's instant, once
        (pass_html and pass_panel_hidden both read it): the wrapper
        pass_fragment writes, its chart empty when no configured
        satellite has a visible pass in its elements' validity window;
        '' without a SkyPage or when the drawing fails."""
        palette = self.palette(alm, fs)
        key = ('pass', id(alm), int(alm.time_ts), fs.name, palette)
        if key not in self._memo:
            self._memo[key] = self._draw_pass(alm, fs, palette)
        return self._memo[key]

    @_panel_guard(label='the pass-chart fragment (pass_fragment)')
    def _draw_pass(self, alm: Any, fs: FragmentSet, palette: str) -> str:
        """The pass-chart fragment for the page, '' when it raises -- the
        chart then degrades to its hidden area, logged with the traceback
        (see _draw_dome)."""
        return self.pass_fragment(alm, fs, palette)

    def _pass_lines(self, alm: Any, so: Any, p: Any, no_pass_key: str,
                    tag_visibility: bool) -> Tuple[str, str]:
        """One roster row's two lines from a pass chain (next_pass or
        next_visible_pass): the dated head line and the appears/peaks/
        disappears sub-line.  The head line is composed, never
        str(p.rise): the bare ValueHelper renders ephem_day (time-of-day
        only), and a next pass can be days out -- a dated line is the
        truthful first paint.  Same date + HM + countdown idiom as
        skyfield's satellite chips and this page's own live layer
        (fmtDayHM + satWhen), so the live replacement changes dress, not
        meaning.  Whole days is a CALENDAR-day difference, not elapsed
        seconds divided down: the count stands on the same line as the
        pass's own date, and a count reckoned any other way contradicts
        the date beside it twice a day -- rounding up calls a pass later
        this evening "in 1 day" (Jacques Terrettaz's report against
        weewx-skyfield's chips, the 2026-08-12 partial solar eclipse,
        issue #6), rounding down calls one just past midnight "today".
        Differencing the two local dates is DST-correct for free; the
        floor at 1 is the fall-back Sunday's belt and braces, where 24
        elapsed hours can land back on today.  The live layer's satWhen
        reckons identically.  Honest rows when there is no pass: the
        no-pass text with usable elements (sunlit is known), the
        weewxd-log row without -- read only then, as the template read
        it.  The any-pass table tags each row visible/not visible from
        the pass's own bool."""
        now = alm.time_ts
        rise = p.rise.raw
        if rise is None:
            if so.sunlit is not None:
                return self._t(no_pass_key), ''
            return self._t('no usable orbital elements — see the weewxd log'), ''
        sset = p.set.raw
        delta = rise - now
        if sset is not None and rise <= now < sset:
            when = self._t('overhead now')
        elif delta < 3600:
            when = self._t('in {m} min', m=max(1, int(delta // 60)))
        elif delta < 86400:
            when = self._t('in {h} h', h=int(round(delta / 3600)))
        else:
            days = max(1, (datetime.date.fromtimestamp(rise)
                           - datetime.date.fromtimestamp(now)).days)
            when = self._t('in {n} day', n=1) if days == 1 else self._t('in {n} days', n=days)
        line = self._date_hm(rise) + ' · ' + when
        sub = self._t('appears {rise} · peaks {alt}° {culm} · disappears {set} · {m} min',
                      rise=_esc(p.rise_azimuth.ordinal_compass()),
                      alt='%.0f' % p.max_altitude.raw,
                      culm=_esc(p.culmination_azimuth.ordinal_compass()),
                      set=_esc(p.set_azimuth.ordinal_compass()),
                      m='%d' % round(p.duration.raw / 60))
        if tag_visibility:
            if p.visible is True:
                sub += ' · ' + self._t('visible')
            elif p.visible is False:
                sub += ' · ' + self._t('not visible')
        return line, sub

    def _sat_rows(self, alm: Any) -> List[Tuple[str, str, str, str, str, str]]:
        """One row per CONFIGURED satellite -- [Skyfield] [[Satellites]],
        enumerated through skyfield 2.0's public satellite_names() (an
        older skyfield has no method and no satellites, so no rows) --
        as (tag, label, visible-pass line, its sub-line, any-pass line,
        its sub-line), once per instant for both rosters.  A satellite
        whose tags error is simply skipped, so a lesser almanac costs
        rows, never the panel.  Rows first-paint here and go live from
        loop data; the config block feeds the javascript the same list,
        so rows and live layer always agree.  The pass line, the honest
        no-pass and no-elements rows all reuse weewx-skyfield's Sky page
        wording, so the translations are shared verbatim; the any-pass
        strings are celestial's own."""
        key = ('rows', id(alm), int(alm.time_ts))
        if key not in self._memo:
            rows: List[Tuple[str, str, str, str, str, str]] = []
            for name in self.satellite_names():
                try:
                    so = getattr(alm, name)
                    label = _esc(so.label)
                    sat_line, sat_sub = self._pass_lines(
                        alm, so, so.next_visible_pass, 'no visible pass in the coming week', False)
                    any_line, any_sub = self._pass_lines(
                        alm, so, so.next_pass, 'no pass in the coming week', True)
                except Exception:
                    continue
                rows.append((name, label, sat_line, sat_sub, any_line, any_sub))
            self._memo[key] = rows
        return self._memo[key]

    def _roster(self, rows: List[Tuple[str, str, str, str, str, str]], heading: str,
                ids: str, line_at: int) -> str:
        """A satellite roster: the heading and one row per satellite,
        each row's cells carrying the ids the javascript repaints
        (sat-<ids>row/-line/-pass-<tag>); '' with no rows, so a station
        without satellites shows no empty table."""
        if not rows:
            return ''
        out = ['<div class="cel-roster cel-mono" %s>' % PANEL_MARK,
               '  <h3 class="cel-eyebrow">%s</h3>' % heading]
        for row in rows:
            name, label = row[0], row[1]
            out.append('  <div class="cel-row" id="sat-%srow-%s">' % (ids, name))
            out.append('    <span class="cel-bname"><span class="cel-chip cel-chip-sat"></span>%s</span>' % label)
            out.append('    <span class="cel-odo cel-satline" id="sat-%sline-%s">%s</span>'
                       % (ids, name, row[line_at]))
            out.append('    <span class="cel-rsub"><span id="sat-%spass-%s">%s</span></span>'
                       % (ids, name, row[line_at + 1]))
            out.append('  </div>')
        out.append('</div>')
        return '\n'.join(out)

    @_panel_guard()
    def dome_html(self, alm: Any, set: str = '') -> str:
        """The sky dome (see _dome_html), behind its declaration line --
        the dome carries the panel's line; its roster, a part of the
        same panel, never does, so a grid holding both shows it once."""
        r = self._resolve(alm, set, 'dome_html', 'dome')
        return self._behind_line(r.line, self._dome_html(alm, r))

    def _dome_html(self, alm: Any, r: 'Resolved') -> str:
        """The sky dome: weewx-skyfield's dome_svg for the named set (its
        plate and label scale) inside the wrapper the javascript swaps
        and reads, the caption, and the backdrop's health line.  The
        install hint instead when the almanac cannot draw the dome (no
        weewx-skyfield, or its almanac not registered) -- the panel's own
        degraded state, so a consumer gets it too.

        The inner #dome-svg is the javascript's swap target: a fragment
        refetch replaces exactly that element's contents, and the element
        itself names the files to refetch (data-dome-prefix, the set's).
        The wrapper self-describes like the staggered fragments the
        FragmentGenerator writes -- its instant, the step, the count, the
        archive interval (`interval_s`, read in SECONDS by the search
        list: .raw arrives in whatever unit the report's group_interval
        asks for, and a station carrying group_interval = hour once
        emptied every fragment that way, issue #4) and the plate it is
        drawn on -- so the javascript can pick the right slot from the
        very first refetch and judge a plate flip against the dome it
        holds: the wrapper carries the REPORT's theme (data-page-theme)
        beside the set's plate (data-dome-palette), and a flip is a
        fragment whose report theme is not the one the page was generated
        on (the config block's `theme`, the same theme(alm)) -- a set on
        a plate other than the page's is never one, and celestial.css
        styles a fragment's labels by the set's plate when it differs
        from the page's, so they wear the dome's plate.  The geometry is
        the generator's own
        dome_slots -- one function, so the page and its fragments cannot
        disagree about how many slots there are (they did, when each
        carried its own copy of the arithmetic).  The health line is
        written by the javascript (updateDomeStale) and hidden until the
        fragment refetches stop landing, at which point the dome freezes
        rather than flying live marks over a motionless star field and
        the line says so, naming the fault; ALWAYS hidden at first paint,
        since a page carries a backdrop of its own generation instant,
        which is by definition current.  Its link is the one place on
        the page that sends a reader to the manual."""
        fs, refused, hint = r.fs, r.refused, r.hint
        if refused:
            # A configuration fault the owner has to see: the log line is
            # written once per cycle, and this stands where the dome would.
            return hint
        install = '<p class="cel-skyhint">%s</p>' % self._t(
            'Install {skyfield} so the almanac can draw the live sky dome.',
            skyfield=SKYFIELD_LINK)
        if fs is None:
            return install
        svg = self._dome_svg(alm, fs)
        if not svg:
            # can_draw said yes and the drawing came back empty anyway (a
            # body tag raising inside skyfield's own guard, which logs
            # it): not an installation problem, and the rosters and pass
            # panel stand on can_draw's answer, so the line names the
            # right fault.  (An older skyfield without can_draw never
            # reaches here: the draw IS its answer.)
            return '<p class="cel-skyhint">%s</p>' % self._t(
                "The sky dome could not be drawn — see the weewxd log.")
        palette = self.palette(alm, fs)
        interval, step, count = dome_slots(self.interval_s)
        out = ['<div id="dome-wrap" %s>' % PANEL_MARK]
        out.append('  <div id="dome-svg" data-dome-prefix="%s" data-dome-dir="%s">%s</div>'
                   % (fs.prefix, fs.directory,
                      self._dome_wrapper(alm, int(alm.time_ts), None, step, count,
                                         interval, palette, svg)))
        out.append('  <p class="cel-caption cel-dialcaption">%s %s</p>' % (
            self._t("North at the top, east at the left — the sky-chart orientation, as if lying on your back looking up.  Altitude rings at 30° and 60°; the rim is the horizon."),
            self._t("Hover or tap any mark for its coordinates.")))
        out.append('  <p class="cel-stalehint" id="dome-stale" hidden><span id="dome-stale-msg"></span>'
                   ' · <a href="%s">%s</a></p>' % (FROZEN_LINK, self._t("what to check")))
        out.append('</div>')
        return '\n'.join(out)

    @_panel_guard()
    def dome_roster_html(self, alm: Any, set: str = '') -> str:
        """The dome's satellite roster: the next pass of ANY kind per
        configured satellite, each row tagged visible/not visible from
        next_pass.visible -- the dome draws any overhead satellite, dimmed
        when not visible, so this is its table.  '' without rows, and ''
        when the almanac cannot draw the sky (_can_draw): rows under an
        install hint would be rows only skyfield could have filled -- and
        '' beside a refused set, the dome it belongs to being refused."""
        r = self._resolve(alm, set, 'dome_roster_html', 'dome')
        if r.fs is None:
            return ''
        return self._roster(self._sat_rows(alm),
                            self._t("Satellites · the next pass overhead"), 'any-', 4)

    @_panel_guard()
    def pass_html(self, alm: Any, set: str = '') -> str:
        """The Next Visible Pass chart (see _pass_html), behind its
        declaration line -- the chart carries the panel's line; its
        roster never does."""
        r = self._resolve(alm, set, 'pass_html', 'pass')
        return self._behind_line(r.line, self._pass_html(alm, r))

    def _pass_html(self, alm: Any, r: 'Resolved') -> str:
        """The Next Visible Pass chart: skyfield 2.0's pass_chart_html --
        the whole sky as it will stand at the culmination of the soonest
        upcoming visible pass among the configured satellites, the
        pass's arc dashed across it under a dated head line (the dome
        stopped drawing the arc in 2.0: an undated future track on the
        now-sky crossed stars it will never cross) -- on the named set's
        plate and scale, with its caption.  The chart area is hidden
        when the chart is empty (no configured satellite has a visible
        pass in its elements' validity window): the javascript's
        fragment refetch, whose file #pass-chart names
        (data-pass-fragment), unhides it when a pass enters the window.
        During an in-progress pass the chart's epoch is within minutes
        of now, so the javascript sweeps the featured satellite's
        data-body marker along the drawn arc; the chart's sun, moon,
        planets and stars belong to the culmination instant and are
        never nudged.  '' when the almanac cannot draw the sky
        (_can_draw, the template's own gate through 8.5): a page on a
        lesser tier would otherwise poll an empty fragment for ever for a
        panel that cannot show.  The chart arrives wrapped (pass_fragment)
        naming its plate and the report's theme, exactly as the refetched
        fragment does, so celestial.css styles its labels by the set's
        plate and the javascript sees a theme flip on either fragment."""
        fs, refused, hint = r.fs, r.refused, r.hint
        if fs is None:
            return hint if refused else ''
        chart = self._pass_chart(alm, fs)
        _domes, pass_name = fragment_names(fs)
        out = ['<div id="pass-wrap" %s%s>' % (PANEL_MARK, '' if '<svg' in chart else ' hidden')]
        out.append('  <div id="pass-chart" data-pass-fragment="%s" data-pass-dir="%s">%s</div>'
                   % (pass_name, fs.directory, chart))
        out.append('  <p class="cel-caption cel-passcaption">%s</p>' % self._t(
            "The whole sky as it will stand at the pass's highest point, on the date above — the dashed arc is the satellite's path, its rise and set times at the ends.  Only stars bright enough for a twilight sky are drawn: a visible pass happens while your sky is half dark."))
        out.append('</div>')
        return '\n'.join(out)

    @_panel_guard()
    def pass_roster_html(self, alm: Any, set: str = '') -> str:
        """The Next Visible Pass panel's roster: the next VISIBLE pass per
        configured satellite, the chart's own story.  '' without rows, or
        when the almanac cannot draw the sky, or beside a refused set (as
        the dome's)."""
        r = self._resolve(alm, set, 'pass_roster_html', 'pass')
        if r.fs is None:
            return ''
        return self._roster(self._sat_rows(alm),
                            self._t("Satellites · the next visible pass"), '', 2)

    @_panel_guard(fallback=False)
    def pass_panel_hidden(self, alm: Any, set: str = '') -> bool:
        """Whether the Next Visible Pass panel has nothing to show at this
        instant -- no chart and no roster row -- which is when the
        bundled page first-paints the section around the panel hidden
        (an empty chart area beside an empty roster would leave a
        heading over nothing) -- False when the panel carries the
        refused-set line or its declaration line instead, whichever
        order the page asks in: a line is something to show.  The
        javascript unhides an element with
        id pass-sec when a pass enters the window, and hides it again
        when the chart empties and no roster stands, so a consumer
        wanting the same puts that id on its own wrapper.  Agrees with
        pass_html and pass_roster_html by construction: the same chart
        and rows."""
        r = self._resolve(alm, set, 'pass_panel_hidden', 'pass')
        if r.fs is None:
            # A refused set: the pass panel carries the line, which is
            # something to show -- in whatever order the page asks.  (No
            # sky at all renders nothing, whatever the declaration.)
            return not r.refused
        if r.line:
            return False
        return '<svg' not in self._pass_chart(alm, r.fs) and not self._sat_rows(alm)

    @_panel_guard()
    def footer_html(self, alm: Any) -> str:
        """The footer's credit, true for whatever almanac actually serves
        the page, probed by capability: Proxima Centauri needs a Skyfield
        almanac with a star catalog (the full credit); any other extended
        almanac gets the generic credit; the built-in almanac serves no
        live fields at all.  On top of the capability probe, an IDENTITY
        check -- the same class-name-plus-module match weewx-skyfield's
        own register_almanac uses -- decides whether the credit may name
        weewx-skyfield and link its project page: the independent
        weewx-skyfield-almanac extension also names its class
        SkyfieldAlmanacType and could pass the Proxima probe, and must
        not be credited as ours.  The name becomes a link only when the
        check proved it, substituted after translation, so it survives
        any language that keeps the proper noun verbatim.  The
        weewx-loopdata credit closes the line: the page is live through
        it."""
        wxsf = any(type(a).__name__ == 'SkyfieldAlmanacType'
                   and type(a).__module__.split('.')[-1] == 'wxskyfield'
                   for a in getattr(weewx.almanac, 'almanacs', []))
        credit = self._t("Calculated with WeeWX's built-in almanac")
        if alm.hasExtras:
            credit = self._t("Calculated with the station's extended almanac (weewx-skyfield or PyEphem)")
            try:
                # The read is the probe: it raises without a star catalog.
                alm.proxima_centauri.earth_distance
                if wxsf:
                    credit = self._t("Calculated with weewx-skyfield: Skyfield, JPL's DE421 ephemeris and the Hipparcos star catalog (Credit: ESA)")
                else:
                    credit = self._t("Calculated with Skyfield, JPL's DE421 ephemeris and the Hipparcos star catalog (Credit: ESA)")
            except Exception:
                pass
        if wxsf:
            credit = credit.replace('weewx-skyfield', SKYFIELD_LINK)
        return credit + ' &middot; ' + self._t("live via weewx-loopdata") + '.'

    # -- the fragment set --------------------------------------------------

    def dome_fragment(self, alm: Any, k: int, interval_s: Any = None,
                      fs: FragmentSet = DEFAULT_SET, palette: Optional[str] = None) -> str:
        """Slot k of a set's staggered dome backdrops: the self-describing
        wrapper around skyfield's dome_svg for the slot's own time (the
        report's almanac re-bound through core WeeWX's
        $almanac(almanac_time=...) -- the engine contract is untouched),
        or '' when the slot falls beyond the interval or there is no
        SkyPage.  `palette` is the set's, resolved once by the caller
        (the generator resolves each set's once per cycle); None resolves
        it here.  NOT guarded: a failure must reach the caller, which for
        the generator means the old file stays on disk, never an empty or
        error-carrying one."""
        sp = self.sky_page
        if sp is None:
            return ''
        interval, step, count = dome_slots(interval_s)
        offset = k * step
        if k < 0 or offset >= interval:
            return ''
        ts = int(alm.time_ts) + offset
        if palette is None:
            palette = self.palette(alm, fs)
        svg = sp.dome_svg(alm(almanac_time=ts), palette=palette, label_scale=fs.label_scale)
        return self._dome_wrapper(alm, ts, k, step, count, interval, palette, svg)

    def pass_fragment(self, alm: Any, fs: FragmentSet = DEFAULT_SET,
                      palette: Optional[str] = None) -> str:
        """The pass-chart fragment: skyfield's pass_chart_html on the
        set's plate in a self-describing wrapper -- an EMPTY wrapper when
        no configured satellite has a visible pass, which the javascript
        reads as the deliberate empty (it hides the panel on one, and
        keeps the chart it has on a failed fetch or junk); the wrapper is
        always written because it is what carries the report's theme to
        a page whose only fragment is this one.  '' with no SkyPage.
        NOT guarded, for the same reason as dome_fragment."""
        sp = self.sky_page
        if sp is None:
            return ''
        if palette is None:
            palette = self.palette(alm, fs)
        chart = str(sp.pass_chart_html(alm, palette=palette, label_scale=fs.label_scale))
        # Wrapped like a dome fragment: the set's plate, which celestial.css
        # styles the chart's labels by, and the report's theme, which the
        # javascript checks for a flip -- so a chart refetched across
        # sunrise never wears the other plate's labels, and a page with
        # no pass in window still sees the flip.
        return ('<div class="passfrag" data-pass-palette="%s" data-page-theme="%s">%s</div>'
                % (palette, self.theme(alm), chart.strip()))


class CelestialPanels(SearchList):
    """Exposes $celestial and $sky_page to a skin's templates."""

    def get_extension_list(self, timespan, db_lookup) -> List[Dict[str, Any]]:
        # $sky_page exactly as the celestial_sky shim serves it (and the
        # shim's version log fires here, since a skin listing this search
        # list need not list the shim as well).
        sky_page = sky_page_from_shim(self.generator)
        # The station's weewx.conf, for the report's own stanza (every
        # generator carries it; read with a default because nothing on
        # this path may raise -- a search list that raises kills the page).
        page = CelestialPage(self.generator.skin_dict, sky_page,
                             self._interval_seconds(timespan, db_lookup),
                             getattr(self.generator, 'config_dict', None))
        return [{'celestial': page, 'sky_page': sky_page}]

    def _interval_seconds(self, timespan: Any, db_lookup: Any) -> Optional[float]:
        """The archive interval at the page's instant, in seconds, read
        by the one reader the FragmentGenerator uses (interval_seconds:
        the engine's record when it is the instant's, else the archive's,
        else the engine's whatever its stamp); None -- the default
        geometry -- when nothing can say.  Nothing here may raise: a
        search list that fails costs the whole page, and an interval it
        cannot read costs the dome's wrapper its exact geometry at
        worst -- logged, since the fragments on disk then carry the true
        one."""
        archive = _archive_or_none(lambda: db_lookup() if db_lookup is not None else None)
        return interval_seconds(archive, getattr(timespan, 'stop', None),
                                getattr(self.generator, 'record', None))


def sky_page_from_shim(generator: Any) -> Optional[Any]:
    """$sky_page exactly as the celestial_sky shim serves it (the real
    SkyPage or None, with the shim's own log lines and its version log)
    for anything that carries a skin_dict the way a generator does."""
    return celestial_sky.CelestialSkyPage(generator).get_extension_list(None, None)[0]['sky_page']


def report_encoding(skin_dict: Any) -> str:
    """The report's `encoding` option: [CheetahGenerator] [[ToDate]],
    else [CheetahGenerator], else the skin's root, default html_entities
    -- the levels the CheetahGenerator accumulates for a page template
    listed directly under [[ToDate]], which is where the Celestial page
    is (an encoding set on the page's own template section is not seen
    here); stripped and lowercased, utf-8 spelled utf8 -- so
    HTML_ENTITIES in a user's stanza means to the fragments what it
    means to the page."""
    cg = skin_dict.get('CheetahGenerator', {})
    if not isinstance(cg, dict):
        cg = {}
    to_date = cg.get('ToDate', {})
    enc = to_date.get('encoding') if isinstance(to_date, dict) else None
    if enc is None:
        enc = cg.get('encoding')
    if enc is None:
        enc = skin_dict.get('encoding', 'html_entities')
    enc = str(enc).strip().lower()
    return 'utf8' if enc == 'utf-8' else enc


def encode_like_cheetah(text: str, encoding: str) -> bytes:
    """The bytes the CheetahGenerator writes for a report's `encoding`
    option (normalized by report_encoding), so a fragment reads the same
    whether a template or this module wrote it: html_entities (the
    default, and what the bundled skin uses) is ASCII with numeric
    character references."""
    if encoding == 'html_entities':
        return text.encode('ascii', 'xmlcharrefreplace')
    if encoding == 'strict_ascii':
        return text.encode('ascii', 'ignore')
    if encoding == 'normalized_ascii':
        import unicodedata
        return unicodedata.normalize('NFD', text).encode('ascii', 'ignore')
    return text.encode(encoding)


class FragmentGenerator(ReportGenerator):
    """Writes a report's dome and pass-chart fragments into its HTML_ROOT
    each cycle.  A skin lists it in [Generators] generator_list beside
    the CheetahGenerator; it needs nothing from the templates and the
    templates need nothing from it -- the page's wrapper and the
    fragments agree because both read dome_slots."""

    def run(self) -> None:
        t1 = time.time()
        skin_dict = self.skin_dict
        report = skin_dict.get('REPORT_NAME', '?')
        try:
            sets = fragment_sets(skin_dict)
        except ValueError as e:
            log.error('Report %s: %s; no fragments written.', report, e)
            return
        # No SkyPage (weewx-skyfield absent or broken -- the shim has
        # logged which): every fragment renders '' and is written EMPTY,
        # as the templates wrote it -- the page's "is empty" line then
        # points at skyfield, where a stale sky left on disk would point
        # it at the report's timing.
        page = CelestialPage(skin_dict, sky_page_from_shim(self))
        alm, interval_s = self.almanac_and_interval()
        html_root = os.path.join(self.config_dict['WEEWX_ROOT'], skin_dict['HTML_ROOT'])
        encoding = report_encoding(skin_dict)
        ngen = 0
        for fs in sets:
            # The set's files land in its directory under HTML_ROOT.  A
            # directory that cannot be made (a read-only root, a file
            # where the directory should be) costs this set its files,
            # named, and no other set its cycle -- the fault's scope,
            # as _write's is one file.
            dest = os.path.join(html_root, *fs.directory.split('/')) if fs.directory else html_root
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError as e:
                log.error('Report %s: fragment set %s not written (%s making %s: %s); the '
                          'previous files stay.', report, fs.name or 'default',
                          type(e).__name__, dest, e)
                continue
            # The plate, once per set: a property of the page's instant.
            palette = page.palette(alm, fs)
            # What this set writes, from the one function that decides
            # it -- the same one fragment_sets refuses collisions by, so
            # the check and the writer cannot disagree about which files
            # a set is responsible for.  `kind` is applied there: a
            # dome-only set comes back with no pass name, a pass-only one
            # with no dome names, and the loops below simply do nothing.
            dome_names, pass_name = written_names(fs)
            for k, name in enumerate(dome_names):
                if self._stopping():
                    return              # weewxd is shutting down; stop like the templates did
                ngen += self._write(dest, name, encoding, report,
                                    functools.partial(page.dome_fragment, alm, k, interval_s,
                                                      fs, palette))
            if self._stopping():
                return
            if pass_name:
                ngen += self._write(dest, pass_name, encoding, report,
                                    functools.partial(page.pass_fragment, alm, fs, palette))
        if to_bool(skin_dict.get('log_success', True)):
            log.info('Generated %d fragments for report %s in %.2f seconds',
                     ngen, report, time.time() - t1)

    def _stopping(self) -> bool:
        """Whether weewxd is shutting down.  WeeWX 5.2's ReportGenerator
        has no stop_event at all (its engine never passes one), so the
        attribute is read with a default: on 5.2 a cycle runs to its end,
        exactly as 5.2's own CheetahGenerator does."""
        ev = getattr(self, 'stop_event', None)
        return ev is not None and ev.is_set()

    @staticmethod
    def _write(html_root: str, name: str, encoding: str, report: str,
               render: Callable[[], str]) -> int:
        """Render and encode one fragment and write it through a
        temporary file and a rename, so a page's refetch never reads a
        half-written sky.  A render that raises -- or an encoding this
        Python has no codec for -- is logged with its traceback (the
        frame is what identifies a skyfield bug) and the file left as it
        was; so is a write that fails (a full tmpfs), with the temporary
        file removed."""
        try:
            data = encode_like_cheetah(render(), encoding)
        except Exception as e:
            log.error('Report %s: %s not written (%s: %s); the previous one stays.',
                      report, name, type(e).__name__, e)
            weeutil.logger.log_traceback(log.error, '****  ')
            return 0
        full = os.path.join(html_root, name)
        tmp = full + '.tmp'
        try:
            with open(tmp, 'wb') as fd:
                fd.write(data)
            os.rename(tmp, full)
        except OSError as e:
            log.error('Report %s: %s not written (%s: %s); the previous one stays.',
                      report, name, type(e).__name__, e)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return 0
        return 1

    def almanac_and_interval(self) -> Tuple[Any, Optional[float]]:
        """The report's almanac -- built by core WeeWX's own
        `cheetahgenerator.Almanac` search list on this generator, so it
        is the page's `$almanac` on every WeeWX version by construction
        (the search list wants a formatter and a converter on the
        generator, which the CheetahGenerator sets in its constructor and
        this one sets here), at the cycle's own instant -- and the archive
        interval of the record at
        the almanac's instant, in SECONDS (None when no record says),
        through the one reader the page's search list uses too
        (interval_seconds), so the wrapper on the page and the fragments
        on disk describe the same geometry."""
        self.formatter = weewx.units.Formatter.fromSkinDict(self.skin_dict)
        self.converter = weewx.units.Converter.fromSkinDict(self.skin_dict)
        # The instant: the engine passes no gen_ts, and core's Almanac
        # search list then takes lastGoodStamp() when IT runs -- for the
        # page's generator and this one separately, seconds apart, so a
        # record committing between the two would give the page one
        # instant (and, at a sunrise cycle on theme = auto, one plate)
        # and its fragments another.  The record the engine passed is the
        # one that started this cycle and, unless a record committed while
        # the page's generator was already running, the one it found as
        # lastGoodStamp -- so it is the instant here: the same record,
        # rather than a second reading of the clock.
        if not getattr(self, 'gen_ts', None) and self.record and self.record.get('dateTime'):
            self.gen_ts = self.record['dateTime']    # (untyped on the base class)
        alm = weewx.cheetahgenerator.Almanac(self).almanac
        return alm, self.interval_seconds(alm.time_ts)

    def interval_seconds(self, ts: Any) -> Optional[float]:
        archive = _archive_or_none(
            lambda: self.db_binder.get_manager(self.skin_dict.get('data_binding', 'wx_binding')))
        return interval_seconds(archive, ts, self.record)


def _archive_or_none(open_archive: Callable[[], Any]) -> Any:
    """The archive manager `open_archive` returns, or None with one
    warning when it raises (no database, an unknown binding, a locked
    file): the one policy both readers of the interval share -- the
    page's search list and the FragmentGenerator -- so the same fault
    reads the same in the log and costs the same, the default geometry
    and never the page or the cycle."""
    try:
        return open_archive()
    except Exception as e:
        log.warning("celestial: the archive is not readable for the dome's interval "
                    '(%s: %s); using the engine record or the default.',
                    type(e).__name__, e)
        return None


def interval_seconds(archive: Any, ts: Any, record: Any) -> Optional[float]:
    """The archive interval, in SECONDS, at `ts` -- the one reader the
    page's search list and the FragmentGenerator share, with one
    precedence: `record` (the one the engine passed) when it IS the
    record at `ts` (no query at all, the everyday cycle -- $current's own
    short cut); else the record within an hour of `ts` from `archive` (a
    database manager, None without one) -- core's Almanac idiom for the
    instant's record, wider than $current's exact match, so a report run
    between records first-paints the nearest record's geometry rather
    than the default; a read that raises (a locked database) is logged
    and falls through; else `record` whatever its stamp; else None when
    nothing says.  Converted explicitly: a record's interval is a
    minutes field, and the page once read it through the report's
    group_interval and got 0.0833 for five minutes (issue #4)."""
    rec: Optional[Dict[str, Any]] = None
    if record and ts and record.get('dateTime') == ts:
        rec = record
    elif archive is not None and ts:
        try:
            rec = archive.getRecord(ts, max_delta=3600)
        except Exception as e:
            log.warning("celestial: the archive record at %s could not be read for the dome's "
                        'interval (%s: %s); using the engine record or the default.',
                        ts, type(e).__name__, e)
    if rec is None:
        rec = record
    if rec is None or rec.get('interval') is None:
        return None
    try:
        return weewx.units.convert(weewx.units.as_value_tuple(rec, 'interval'), 'second')[0]
    except Exception as e:
        log.warning("celestial: the archive record's interval could not be converted "
                    '(%s: %s); using the default.', type(e).__name__, e)
        return None
