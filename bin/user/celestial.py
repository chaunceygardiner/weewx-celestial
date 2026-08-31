"""
celestial.py

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

weewx-celestial ships a live celestial report (the bundled Celestial skin):
a single Geocentric panel -- Earth at the center, every body placed by
compass bearing and log distance, with odometer distance readouts that tick
between loop refreshes -- whose values are weewx-loopdata 5.0 almanac
fields evaluated against the registered almanac (weewx-skyfield strongly
recommended).  This module holds the page's field set -- declared to
weewx-loopdata by the skin's skin.conf, and for the configured satellites
and comets by the installer -- and the command-line utilities that add and
remove satellites and comets.

Through 5.x this extension ran a StdService that computed celestial
observations with Skyfield and inserted them into every LOOP packet; 6.0
removed it (weewx-loopdata 5.0 evaluates almanac fields -- the report-tag
grammar with the $ removed -- directly against the registered almanac).
6.x also embedded weewx-skyfield's $sky_page SVG panels via the
CelestialSkyPage search-list shim; 7.0 removed the panels (they duplicate
weewx-skyfield's own Sky page), the shim, and the 6.x service stub.
"""

import logging
import os
import re
import sys

from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import weewx

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '9.0'

if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 9):
    raise weewx.UnsupportedFeature(
        "weewx-celestial requires Python 3.9 or later, found %s.%s" % (sys.version_info[0], sys.version_info[1]))


def parse_weewx_version(version: str) -> Optional[Tuple[int, int]]:
    """(major, minor) of a WeeWX version string, compared as integers (a
    plain string comparison would misjudge 5.10 against 5.2).  None -- the
    benefit of the doubt -- when the leading components are not plain
    integers (e.g., a dev build)."""
    parts = version.split('.')
    try:
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except ValueError:
        return None


# The install-time guard in install.py enforces the same minimum with a
# clear message; this one catches copied-in files and unsupported upgrades.
# WeeWX 5.2 is the first release with extensible almanacs, which both
# weewx-skyfield (the report tags) and weewx-loopdata's almanac fields (the
# live values) build on.
_weewx_version = parse_weewx_version(weewx.__version__)
if _weewx_version is not None and _weewx_version < (5, 2):
    raise weewx.UnsupportedFeature(
        "weewx-celestial requires WeeWX 5.2 or later, found %s" % weewx.__version__)


# ===============================================================================
# The page's loop-data field set.
#
# PAGE_FIELDS is the one source of truth for what the sample page reads.
# Its STATIC members -- everything that does not belong to a satellite or
# comet tag -- are declared to weewx-loopdata by skins/Celestial/skin.conf
# ([LoopData] [[fields]]; a test pins the two equal), and its iss and
# halley members double as the per-satellite and per-comet PATTERNS
# (satellite_fields/comet_fields), which declare_page_fields writes into
# weewx.conf under the report's stanza for the satellites and comets the
# station has configured -- a shipped skin.conf cannot know those.  The
# list exists SOLELY for the declaration and its tests and must never grow
# another consumer.
# ===============================================================================

_PLANETS: List[str] = ['mercury', 'venus', 'mars', 'jupiter',
                       'saturn', 'uranus', 'neptune', 'pluto']

# The fields the sample report reads.  Per body: az places the dial dot,
# alt decides above/below-horizon rendering, earth_distance (raw AU)
# drives the odometer; the moon adds its phase percent and the next
# full/new moon instants (waxing = full before new) for the phase disc --
# pinned to epoch seconds (.unix_epoch) because the page does date math
# on them, so a [Units] [[Groups]] group_time override on the report must
# not change their meaning.
# current.dateTime.raw is loopdata's own field, the live-age indicator
# and the extrapolation anchor.
PAGE_FIELDS: List[str] = [
    'current.dateTime.raw',
    'almanac.sun.az', 'almanac.sun.alt', 'almanac.sun.earth_distance',
    'almanac.moon.az', 'almanac.moon.alt', 'almanac.moon.earth_distance',
    'almanac.moon.phase',
    'almanac.next_full_moon.unix_epoch.raw', 'almanac.next_new_moon.unix_epoch.raw',
    'almanac.mercury.az', 'almanac.mercury.alt', 'almanac.mercury.earth_distance',
    'almanac.venus.az', 'almanac.venus.alt', 'almanac.venus.earth_distance',
    'almanac.mars.az', 'almanac.mars.alt', 'almanac.mars.earth_distance',
    'almanac.jupiter.az', 'almanac.jupiter.alt', 'almanac.jupiter.earth_distance',
    'almanac.saturn.az', 'almanac.saturn.alt', 'almanac.saturn.earth_distance',
    'almanac.uranus.az', 'almanac.uranus.alt', 'almanac.uranus.earth_distance',
    'almanac.neptune.az', 'almanac.neptune.alt', 'almanac.neptune.earth_distance',
    'almanac.pluto.az', 'almanac.pluto.alt', 'almanac.pluto.earth_distance',
    'almanac.proxima_centauri.az', 'almanac.proxima_centauri.alt',
    'almanac.proxima_centauri.earth_distance',
    # The countdown row (8.1): every chip is client-side arithmetic
    # against one of these event instants, pinned to epoch seconds per
    # the 7.5/7.6 doctrine.  The next_* pairs always lie ahead, so the
    # sunset/sunrise, darkness-begins/-ends and equinox/solstice chips
    # are client-side min()s; loopdata's event expiry rolls each the
    # moment it passes.  The
    # meteor shower, supermoon and eclipse chains need weewx-skyfield
    # 2.1 -- an almanac that cannot serve one omits it from
    # loop-data.txt (loopdata logs once per field) and the page hides
    # that chip.  The horizon=-18 spellings are byte-exact in the
    # page's javascript: loop-data.txt keys are these strings verbatim.
    'almanac.sun.next_setting.unix_epoch.raw',
    'almanac.sun.next_rising.unix_epoch.raw',
    'almanac(horizon=-18).sun.next_setting.unix_epoch.raw',
    'almanac(horizon=-18).sun.next_rising.unix_epoch.raw',
    'almanac.next_equinox.unix_epoch.raw',
    'almanac.next_solstice.unix_epoch.raw',
    'almanac.next_perihelion.unix_epoch.raw',
    'almanac.next_aphelion.unix_epoch.raw',
    'almanac.next_meteor_shower.peak.unix_epoch.raw',
    'almanac.next_meteor_shower.label',
    'almanac.next_supermoon.unix_epoch.raw',
    'almanac.next_eclipse.unix_epoch.raw',
    'almanac.next_eclipse_kind',
    # The satellite layer (8.0): weewx-skyfield 2.0's installer-default
    # satellites.  These iss/tiangong members double as the per-satellite
    # PATTERN: declare_page_fields substitutes the configured [Skyfield]
    # [[Satellites]] tags for them (via satellite_fields), falling back
    # to these defaults only when the configuration has no [[Satellites]]
    # section to follow.  An almanac that cannot serve one omits its keys from
    # loop-data.txt (loopdata logs once per field) and the page hides
    # that layer.  next_visible_pass feeds the Next Visible Pass panel's roster;
    # next_pass -- any pass, its visible bool the row's visible/not-
    # visible tag -- feeds the dome's.  Times, the duration and the peak
    # altitude use pinned-unit spellings -- the 7.5/7.6 doctrine: a
    # [Units] [[Groups]] override on the report must never change a
    # field's meaning.
    'almanac.iss.az', 'almanac.iss.alt', 'almanac.iss.sunlit',
    'almanac.iss.label',
    'almanac.iss.next_visible_pass.rise.unix_epoch.raw',
    'almanac.iss.next_visible_pass.set.unix_epoch.raw',
    'almanac.iss.next_visible_pass.max_altitude.degree_angle.raw',
    'almanac.iss.next_visible_pass.duration.second.raw',
    'almanac.iss.next_visible_pass.rise_azimuth.ordinal_compass',
    'almanac.iss.next_visible_pass.culmination_azimuth.ordinal_compass',
    'almanac.iss.next_visible_pass.set_azimuth.ordinal_compass',
    'almanac.iss.next_pass.rise.unix_epoch.raw',
    'almanac.iss.next_pass.set.unix_epoch.raw',
    'almanac.iss.next_pass.max_altitude.degree_angle.raw',
    'almanac.iss.next_pass.duration.second.raw',
    'almanac.iss.next_pass.rise_azimuth.ordinal_compass',
    'almanac.iss.next_pass.culmination_azimuth.ordinal_compass',
    'almanac.iss.next_pass.set_azimuth.ordinal_compass',
    'almanac.iss.next_pass.visible',
    'almanac.tiangong.az', 'almanac.tiangong.alt', 'almanac.tiangong.sunlit',
    'almanac.tiangong.label',
    'almanac.tiangong.next_visible_pass.rise.unix_epoch.raw',
    'almanac.tiangong.next_visible_pass.set.unix_epoch.raw',
    'almanac.tiangong.next_visible_pass.max_altitude.degree_angle.raw',
    'almanac.tiangong.next_visible_pass.duration.second.raw',
    'almanac.tiangong.next_visible_pass.rise_azimuth.ordinal_compass',
    'almanac.tiangong.next_visible_pass.culmination_azimuth.ordinal_compass',
    'almanac.tiangong.next_visible_pass.set_azimuth.ordinal_compass',
    'almanac.tiangong.next_pass.rise.unix_epoch.raw',
    'almanac.tiangong.next_pass.set.unix_epoch.raw',
    'almanac.tiangong.next_pass.max_altitude.degree_angle.raw',
    'almanac.tiangong.next_pass.duration.second.raw',
    'almanac.tiangong.next_pass.rise_azimuth.ordinal_compass',
    'almanac.tiangong.next_pass.culmination_azimuth.ordinal_compass',
    'almanac.tiangong.next_pass.set_azimuth.ordinal_compass',
    'almanac.tiangong.next_pass.visible',
    # The comet layer (8.1): weewx-skyfield 2.1's installer-default
    # comets.  The halley members double as the per-comet PATTERN
    # exactly as the iss members do for satellites: declare_page_fields
    # substitutes the configured [Skyfield] [[Comets]] tags for them
    # (via comet_fields), falling back to these defaults only when the
    # configuration has no [[Comets]] section to follow.  az/alt/
    # earth_distance place the dial's diamond like any planet; mag
    # picks solid (naked-eye, <= 6.0) vs hollow -- an MPC row without
    # g/k parameters serves no mag, which reads as hollow; perihelion
    # (pinned -- the chip does date math) feeds a windowed countdown
    # chip.  An elementless comet (MPC drops faded ones) serves null
    # across its surface and the page renders absence.
    'almanac.halley.az', 'almanac.halley.alt',
    'almanac.halley.earth_distance',
    'almanac.halley.mag', 'almanac.halley.label',
    'almanac.halley.perihelion.unix_epoch.raw',
    'almanac.hale_bopp.az', 'almanac.hale_bopp.alt',
    'almanac.hale_bopp.earth_distance',
    'almanac.hale_bopp.mag', 'almanac.hale_bopp.label',
    'almanac.hale_bopp.perihelion.unix_epoch.raw',
]

# weewx-skyfield's installer defaults: weectl's conditional merge re-adds
# a deleted default to [[Satellites]]/[[Comets]] on the next
# weewx-skyfield upgrade, so removing one earns a warning.  Also the
# fallback sets when the configuration has no section to follow.
_INSTALLER_DEFAULT_SATELLITES = ('iss', 'tiangong')
_INSTALLER_DEFAULT_COMETS = ('halley', 'hale_bopp')

# The report this extension's installer registers -- the [StdReport]
# section its per-configuration fields are declared under, whether or not
# the configuration has it yet -- and the skin it runs, by which every
# other report running the same page is found.
REPORT_NAME = 'CelestialReport'
SKIN_NAME = 'Celestial'

# The two groups declare_page_fields owns in a report's [[[LoopData]]]
# [[[[fields]]]] section.  They are REPLACED wholesale on every run, so a
# field of your own belongs in a group of your own, not in these.
SATELLITES_GROUP = 'satellites'
COMETS_GROUP = 'comets'

# The panels another skin can drop in ($celestial's countdown_html,
# geocentric_html, dome_html with dome_roster_html, pass_html with
# pass_roster_html) and the per-configuration groups each one reads
# live: the countdown's pass chip and perihelion chips, the dial's comet
# layer, the dome's satellite marks and any-pass roster, the chart's
# sweep and visible-pass roster.  A consumer report names the panels its
# page embeds in its own [StdReport] stanza (`celestial_panels =
# countdown, geocentric, dome, pass`) and declare_page_fields maintains
# exactly the groups those panels read under it, as it maintains both
# under a Celestial report -- the two group names are this extension's
# on every report carrying the key, replaced or removed wholesale on
# every run, so a group of the owner's own belongs under another name.
# The footer reads nothing live and is not a panel here.
PANELS_KEY = 'celestial_panels'
PANEL_GROUPS: Dict[str, Tuple[str, ...]] = {
    'countdown': (SATELLITES_GROUP, COMETS_GROUP),
    'geocentric': (COMETS_GROUP,),
    'dome': (SATELLITES_GROUP,),
    'pass': (SATELLITES_GROUP,),
}


def satellite_fields(tag: str) -> List[str]:
    """The nineteen fields the sample page reads per satellite: the
    almanac.iss.* members of PAGE_FIELDS with the tag substituted --
    derived, not copied, so the page's satellite consumption keeps one
    source of truth."""
    return [field.replace('almanac.iss.', 'almanac.%s.' % tag, 1)
            for field in PAGE_FIELDS
            if field.startswith('almanac.iss.')]


def comet_fields(tag: str) -> List[str]:
    """The six fields the sample page reads per comet: the almanac.halley.*
    members of PAGE_FIELDS with the tag substituted -- derived, not
    copied, so the page's comet consumption keeps one source of truth."""
    return [field.replace('almanac.halley.', 'almanac.%s.' % tag, 1)
            for field in PAGE_FIELDS
            if field.startswith('almanac.halley.')]


def static_page_fields() -> List[str]:
    """PAGE_FIELDS less the satellite and comet pattern entries: the
    fields that do not depend on the station's configuration, which the
    shipped skin.conf declares."""
    prefixes = tuple('almanac.%s.' % tag for tag in
                     _INSTALLER_DEFAULT_SATELLITES + _INSTALLER_DEFAULT_COMETS)
    return [field for field in PAGE_FIELDS if not field.startswith(prefixes)]


def _write_conf_atomically(config: Any, config_path: str, output_path: str) -> None:
    """Write config (a ConfigObj) to output_path atomically (temp file,
    fsync, rename -- a crash cannot leave a truncated file), preserving
    config_path's mode.  config_path itself is only written when
    output_path names the same file."""
    import tempfile
    out_dir = os.path.dirname(os.path.abspath(output_path))
    fd, temp_path = tempfile.mkstemp(prefix='weewx.conf.celestial.', dir=out_dir)
    try:
        with os.fdopen(fd, 'wb') as f:
            config.write(f)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp_path, os.stat(config_path).st_mode & 0o777)
        os.replace(temp_path, output_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _configured_satellites(config: Any) -> Optional[List[str]]:
    """The [Skyfield] [[Satellites]] tags as a list, in configuration
    order -- the satellite set the page's fields are declared for.  None
    when the configuration has no [[Satellites]] section to follow
    (weewx-skyfield absent or pre-2.0); a present-but-empty section is
    authoritative and returns [], so a deliberately emptied satellite set
    is never resurrected."""
    try:
        return list(config['Skyfield']['Satellites'].keys())
    except (KeyError, AttributeError):
        return None


def _configured_comets(config: Any) -> Optional[List[str]]:
    """The [Skyfield] [[Comets]] tags as a list, in configuration order --
    the comet set the page's fields are declared for.  None when the
    configuration has no [[Comets]] section to follow (weewx-skyfield
    absent or pre-2.1); a present-but-empty section is authoritative and
    returns [], so a deliberately emptied comet set is never
    resurrected."""
    try:
        return list(config['Skyfield']['Comets'].keys())
    except (KeyError, AttributeError):
        return None


# ===============================================================================
# Declaring the per-configuration fields.
#
# weewx-loopdata 7.0 reads the fields a report needs from the report's
# merged configuration: the skin's skin.conf ([LoopData] [[fields]], a
# section of named groups), then the report's own stanza in weewx.conf
# ([StdReport] [[<report>]] [[[LoopData]]] [[[[fields]]]]), group by
# group -- a group named in weewx.conf replaces the skin's group of that
# name and leaves the others alone.  The shipped skin.conf declares the
# static fields; the satellite and comet fields follow the station's
# [Skyfield] [[Satellites]] and [[Comets]], which no shipped file can
# know, so they are written into weewx.conf as two groups of the report's
# own, by the installer on every install and by the satellite and comet
# verbs on every edit.  The skin's own skin.conf is never written.
# ===============================================================================

class Declarations(NamedTuple):
    """What declare_page_fields declares, report by report: `groups`,
    the reports declared under, in configuration order, each with the
    groups this extension owns there; `refused`, the reports nothing
    is declared under and why -- a celestial_panels naming something
    that is not a panel, or a section where the line belongs -- each
    fault costing exactly that report, never another; and `misplaced`,
    the one station-level fault: a key sitting where WeeWX merges it
    into every report (misplaced_panels_key), reported once."""
    groups: Dict[str, Tuple[str, ...]]
    refused: Dict[str, str]
    misplaced: Optional[str]


def _report_section(config: Any, report: str) -> Any:
    """A report's [StdReport] section, or None."""
    try:
        return config['StdReport'][report]
    except (KeyError, TypeError):
        return None


def celestial_skin_report(config: Any, report: str, ensure_default: bool = False) -> bool:
    """Whether a report is the Celestial skin's own -- its page reads
    every panel and declares the whole static set.  Its skin says so;
    and with ensure_default -- the INSTALLER's case, and only its --
    [[CelestialReport]] is ours before it has a skin, or exists at all:
    weectl's conditional merge is about to fill in that report's skin
    and HTML_ROOT around the groups.  Nothing else may claim it: a
    [[CelestialReport]] holding only a [[[LoopData]]] section has no
    skin, and reportengine dies on it (KeyError 'skin') every archive
    cycle.  Even then the skin decides: a [[CelestialReport]] already
    there under ANOTHER skin (the name reused after an uninstall, or
    repurposed) is somebody else's report, and declaring this page's
    fields under it would have weewx-loopdata evaluate fifty almanac
    fields per packet for a page that is not there."""
    section = _report_section(config, report)
    if not isinstance(section, dict) or section.get('skin') is None:
        return ensure_default and report == REPORT_NAME
    return str(section['skin']) == SKIN_NAME


def skin_conf_path(config: Any, report: str) -> Optional[str]:
    """Where a report's skin.conf is, or None when the report names no
    skin.  Resolved the way WeeWX resolves it and deliberately from the
    GLOBAL [StdReport] SKIN_ROOT: WeeWX ignores a SKIN_ROOT set on an
    individual report (weewx.reportengine builds the path from
    config_dict['StdReport']['SKIN_ROOT'] and that report's skin), so
    honouring a per-report one here would have this extension reading a
    different file than WeeWX does, and the two would disagree in
    silence about where a report's options come from."""
    section = _report_section(config, report)
    if not isinstance(section, dict):
        return None
    skin = str(section.get('skin', '') or '').strip()
    if not skin:
        return None
    try:
        std = config['StdReport']
        root = str(config.get('WEEWX_ROOT', '') or '')
        skin_root = str(std.get('SKIN_ROOT', 'skins') or 'skins')
    except (KeyError, TypeError):
        return None
    if not root:
        # weewxd and weectl put WEEWX_ROOT into the config they hand us,
        # but the --add-/--remove- verbs read weewx.conf straight off disk
        # with ConfigObj, where it is simply not a key -- and a relative
        # SKIN_ROOT would then resolve against the caller's working
        # directory and quietly find no skin.conf at all.  The file's own
        # location is what weecfg derives the root from, so use it.
        filename = getattr(config, 'filename', None)
        if filename:
            root = os.path.dirname(os.path.abspath(str(filename)))
    return os.path.join(root, skin_root, skin, 'skin.conf')


def skin_conf_panels(config: Any, report: str) -> Tuple[Any, str]:
    """A report's `celestial_panels` as its SKIN declares it, and the
    state of that skin.conf: (value, 'found' | 'nokey' | 'absent' |
    'unreadable').  The value is None unless the state is 'found'.

    Which panels a page embeds is a property of the skin's templates --
    identical on every station, changing only when the skin changes --
    so it belongs in a file that deploys with the skin.  Reading it here
    is what spares every consumer a hand edit of weewx.conf per station.

    The state matters as much as the value: 'absent' (ENOENT) is a
    statement that the skin is gone, while 'unreadable' -- no permission,
    a mount that is not up, a half-written file, a syntax error -- is a
    question nobody can answer, and the caller must not treat the two
    alike."""
    path = skin_conf_path(config, report)
    if path is None:
        return None, 'absent'
    if not os.path.exists(path):
        # A missing skin.conf says the skin is gone -- but only if we are
        # looking in the right place.  A SKIN_ROOT that does not exist
        # (mistyped, or a config read from somewhere the skins are not)
        # makes EVERY report's skin look uninstalled, and would prune
        # every consumer's groups at once from one typo.  That is a
        # question, not a statement, and the rule is not to act on a
        # question: no skin tree, no answer.
        if not os.path.isdir(os.path.dirname(os.path.dirname(path))):
            return None, 'unreadable'
        return None, 'absent'
    import configobj
    try:
        skin_dict = configobj.ConfigObj(path, encoding='utf-8', file_error=True)
    except (OSError, UnicodeDecodeError, configobj.ConfigObjError):
        # The conditions the ruling calls UNKNOWN: no permission, a mount
        # that is not up, EIO, a half-written file, a syntax error.  NOT
        # a bare except: anything else here is a fault in this code, and
        # disguising it as 'unreadable' would have it quietly mean "leave
        # the groups alone for ever" -- which is how a missing import for
        # configobj first passed as a well-behaved unreadable file.
        return None, 'unreadable'
    if PANELS_KEY in skin_dict:
        return skin_dict[PANELS_KEY], 'found'
    return None, 'nokey'


def panels_source(config: Any, report: str) -> Optional[str]:
    """Which file answered for a report's celestial_panels: 'stanza',
    'skin', or None when neither carries one.  For the log lines: when
    the two disagree it will be because someone forgot an override
    existed, and a message that does not say which file it read sends
    them to the one that already looks right."""
    section = _report_section(config, report)
    if isinstance(section, dict) and PANELS_KEY in section:
        return 'stanza'
    return 'skin' if skin_conf_panels(config, report)[1] == 'found' else None


def panels_value(config: Any, report: str) -> Any:
    """A report's `celestial_panels` as written, or None when neither its
    stanza nor its skin declares one.  The ONE reader of the key, for the
    installer, the verbs and the page alike -- both sides ask through
    here, so a key in a place one of them cannot see is impossible.

    Two places, and the report's own stanza wins, which is the order
    WeeWX itself merges in (skin.conf, then [[Defaults]], then the
    report's stanza) -- so a station keeps a per-report override in the
    file it already looks in, without editing a skin it may not own."""
    section = _report_section(config, report)
    if isinstance(section, dict) and PANELS_KEY in section:
        return section[PANELS_KEY]
    return skin_conf_panels(config, report)[0]


def misplaced_panels_key(config: Any) -> Optional[str]:
    """The station's one misplaced `celestial_panels`, as a message
    saying where it sits and where it belongs, or None: under
    [[Defaults]], at [StdReport]'s top level, or as a [[celestial_panels]]
    SECTION there -- the places WeeWX merges into every report's skin
    dict (so a key there would have the fields evaluated under every
    enabled report, which is why the installer declares from the stanza
    alone).  A station-level fault, asked once by the installer and
    once by each page whose report carries no key of its own."""
    try:
        std_report = config['StdReport']
    except (KeyError, TypeError):
        return None
    if not isinstance(std_report, dict):
        return None
    belongs = ('belongs on each report whose page embeds the panels, as a line of its own '
               'stanza (%s = %s); WeeWX merges %%s into every report, so the fields would be '
               'evaluated under every one of them' % (PANELS_KEY, ', '.join(PANEL_GROUPS)))
    defaults = std_report.get('Defaults')
    if isinstance(defaults, dict) and PANELS_KEY in defaults:
        return '[StdReport] [[Defaults]] carries %s, which %s' % (PANELS_KEY, belongs % '[[Defaults]]')
    if PANELS_KEY in std_report:
        if isinstance(std_report[PANELS_KEY], dict):
            return ('[StdReport] carries a [[%s]] section, which %s'
                    % (PANELS_KEY, belongs % "the top level's sections"))
        return ('[StdReport] carries %s at its top level, which %s'
                % (PANELS_KEY, belongs % "the top level's scalars"))
    return None


def _panel_names(value: Any) -> List[str]:
    """A `celestial_panels` value as the names it carries.  ConfigObj
    hands back a list for `dome, pass` and a bare string for `dome`,
    which is what _group_fields reads -- but a FIELD may not be split on
    its commas (loopdata reads one field per entry) and a panel name
    never contains one, so a value that reaches here as a single string
    with commas in it -- the key written as `"dome, pass"`, quoted by
    hand or by any tool that writes it as one string -- is those two
    names, not one impossible name.  Splitting keeps the refusal
    honest: it can only ever name something its reader can find in the
    line."""
    names: List[str] = []
    for entry in _group_fields(value):
        names.extend(part.strip() for part in entry.split(',') if part.strip())
    return names


def panels_as_written(value: Any) -> str:
    """A `celestial_panels` value in the spelling its stanza carries
    ('dome, pass'), whatever shape ConfigObj handed it back -- so the
    installer's receipts and the page's log line say the key the way
    its owner wrote it, and never a Python list's repr.  One formatter,
    as the receipts are one formatter."""
    return ', '.join(_panel_names(value))


def parse_panels(value: Any, where: str) -> List[str]:
    """A `celestial_panels` value as ConfigObj hands it back -- a list for
    `dome, pass`, a bare string for `dome`, a single string carrying the
    commas itself when the line was quoted (_panel_names), '' or [] for
    a key naming nothing -- as the panel names, in order, lower-cased
    and de-duplicated; [] for none.  A name that is not a panel, or a
    [[[celestial_panels]]] SECTION where the line belongs, is a
    ValueError naming `where` (the stanza) and what a line looks like:
    a misspelled panel would otherwise declare nothing, silently, for a
    page that then reads BAD DATA."""
    if isinstance(value, dict):
        raise ValueError('%s %s is a section; the key is a line: %s = %s'
                         % (where, PANELS_KEY, PANELS_KEY, ', '.join(PANEL_GROUPS)))
    panels: List[str] = []
    for entry in _panel_names(value):
        name = entry.lower()
        if name not in PANEL_GROUPS:
            raise ValueError('%s %s names %r, which is not a panel; the panels are %s'
                             % (where, PANELS_KEY, entry, ', '.join(PANEL_GROUPS)))
        if name not in panels:
            panels.append(name)
    return panels


def report_groups(config: Any, report: str,
                  ensure_default: bool = False) -> Tuple[Optional[Tuple[str, ...]], Optional[str]]:
    """The groups declare_page_fields owns under a report, and why not:
    (groups, refusal).  Both groups for a Celestial report
    (celestial_skin_report) -- a valid celestial_panels on it changes
    nothing, its page reads every panel.  For any other report the key
    decides: absent, the report is not ours (None); present, the report
    is ours and owns the union of what the named panels read, in the
    declaration's own order (satellites, then comets), whatever order
    the panels were named in -- () for a key naming nothing, which
    then has both groups removed, as the owner asked.  A key naming
    something that is not a panel, or a section where the line belongs,
    is ((), the message): nothing is declared under that report -- and
    nothing removed -- and the message names it.  A key sitting where
    WeeWX merges it into every report is not this report's fault but
    the station's (misplaced_panels_key), asked separately."""
    value = panels_value(config, report)
    where = '[StdReport] [[%s]]' % report
    try:
        panels = parse_panels(value, where)
    except ValueError as e:
        return (), str(e)
    if celestial_skin_report(config, report, ensure_default):
        return (SATELLITES_GROUP, COMETS_GROUP), None
    if value is None:
        return None, None
    wanted = {g for panel in panels for g in PANEL_GROUPS[panel]}
    return tuple(g for g in (SATELLITES_GROUP, COMETS_GROUP) if g in wanted), None


def celestial_reports(config: Any, ensure_default: bool = False) -> Declarations:
    """The [StdReport] sections the page's per-configuration fields are
    declared under, with the groups each owns, in configuration order:
    every report running the Celestial skin (one skin can be listed
    under two reports -- two languages, say -- and weewx-loopdata serves
    each under its own name, so each needs its own declaration) and
    every report of another skin whose stanza names the panels its page
    embeds (celestial_panels).  With ensure_default -- the installer's
    case -- [[CelestialReport]] leads the list whether or not the
    configuration has it yet (celestial_skin_report says when).
    [[Defaults]] is never a report, nor is a section named after the
    key: WeeWX merges the one into every report's skin dict and the
    other is the key written as a section.  A key in either place, or
    at [StdReport]'s top level, is the station's one misplacement
    (misplaced_panels_key), reported once (Declarations.misplaced); a
    report whose own key is invalid is refused by name
    (Declarations.refused)."""
    groups: Dict[str, Tuple[str, ...]] = {}
    refused: Dict[str, str] = {}
    try:
        std_report = config['StdReport']
    except (KeyError, TypeError):
        std_report = {}

    def admit(name: str) -> None:
        owned, why = report_groups(config, name, ensure_default)
        if why is not None:
            refused[name] = why
        elif owned is not None:
            groups[name] = owned

    if ensure_default:
        admit(REPORT_NAME)
    for name in std_report:
        section = std_report[name]
        if (name in groups or name in refused or name in ('Defaults', PANELS_KEY)
                or not isinstance(section, dict)):
            continue
        admit(name)
    return Declarations(groups, refused, misplaced_panels_key(config))


def _fields_groups(config: Any, report: str) -> Any:
    """A report's [[[LoopData]]] [[[[fields]]]] section of groups, or {}
    when it has none.  A [[[LoopData]]] that is not a section, or a
    flat `fields =` line where the section of groups belongs -- the
    shape weewx-loopdata 7.0 itself refuses -- is a ValueError naming
    the report."""
    try:
        section = config['StdReport'][report]
    except KeyError:
        return {}
    loopdata = section.get('LoopData') if isinstance(section, dict) else None
    if loopdata is None:
        return {}
    groups = loopdata.get('fields') if isinstance(loopdata, dict) else None
    if not isinstance(loopdata, dict) or (groups is not None
                                          and not isinstance(groups, dict)):
        raise ValueError(
            '[StdReport] [[%s]] [[[LoopData]]] %s; weewx-loopdata 7.0 '
            'declares fields as named groups in a [[[[fields]]]] section '
            '(fields = a, b becomes, say, mine = a, b under [[[[fields]]]]).  '
            'Move it into a group of your own and re-run.'
            % (report, 'is not a section' if not isinstance(loopdata, dict)
               else 'carries a flat fields = line'))
    return groups if groups is not None else {}


def _group_fields(value: Any) -> List[str]:
    """A [[[[fields]]]] group's value as a list of fields, read the way
    weewx-loopdata reads it: ConfigObj hands back a list for a
    comma-separated value and a bare str for a single one (one field,
    never split); None, or a subsection where a line belongs, is no
    fields."""
    if value is None or isinstance(value, dict):
        return []
    if isinstance(value, str):
        value = [value]
    return [str(entry).strip() for entry in value if str(entry).strip()]


def _with_pending_reports(config: Any, pending: Any) -> Any:
    """`config` with any [StdReport] sections of `pending` that it does
    not yet have, so a report about to be injected is visible to the
    walk.  Only the report's own keys are borrowed -- enough to know it
    exists, which skin it runs and what it already declares -- and the
    caller's config is the one written to, so the groups land where
    weectl's merge will keep them."""
    try:
        reports = pending['StdReport']
    except (KeyError, TypeError):
        return config
    std = config.setdefault('StdReport', {})
    for name in reports:
        section = reports[name]
        if isinstance(section, dict) and name not in std:
            std[name] = {k: section[k] for k in section
                         if not isinstance(section[k], dict)}
    return config


def declare_page_fields(config: Any, apply: bool = True,
                        ensure_default: bool = False,
                        pending: Any = None) -> Dict[str, Any]:
    """Converge every declaring report's [[[LoopData]]] [[[[fields]]]]
    satellites and comets groups (see celestial_reports; ensure_default
    is the installer's, adding REPORT_NAME before it exists) to the
    fields the page reads for the configured [Skyfield] [[Satellites]]
    and [[Comets]] tags: satellite_fields/comet_fields per tag, in
    configuration order, the installer defaults only when there is no
    section to follow.  Each group is replaced wholesale -- re-running is
    the repair path -- and a group whose set is empty is removed; a
    group already right is left untouched, and no section is created
    for nothing.  Other groups in the section are never touched.  With
    apply=False the changes are computed and reported but not written.
    A consumer report (one naming panels with celestial_panels) gets
    only the groups its panels read; a group no panel of its reads (the
    panels renamed, or a group of the owner's own under one of the two
    reserved names) is removed like an emptied set, and reported as
    such.  A section whose celestial_panels is invalid is skipped, not
    written and not emptied, and reported (Declarations.refused): the
    fault costs that section's declaration and nobody else's.  Raises
    ValueError for a report whose [[[LoopData]]] carries a flat
    `fields =` line where the [[[[fields]]]] section of groups belongs
    (the shape weewx-loopdata 7.0 itself refuses to start on), or is not
    a section at all, naming the report -- every report is checked
    before any is written, so a bad one leaves the others untouched.
    Returns a report dict: 'satellites'/'comets' (the tag lists),
    'satellites_defaulted'/'comets_defaulted' (True when the installer
    defaults stood in for a missing section), 'reports' (the sections
    declared under), 'groups' (per report, the groups owned there),
    'refused' (per skipped report, why), 'misplaced' (the station's
    one misplaced key, or None), 'unread' (per report, the groups
    removed because no panel of its reads them, each with the key's
    value as written), 'applied' (whether anything was written -- the
    receipts' tense) and 'changes', mapping each report whose groups
    changed to {group: (old_fields, new_fields)}."""
    if pending is not None:
        # A consumer's installer calls this from its own configure(engine),
        # and weectl runs configure() BEFORE it injects the installer's
        # config stanza (weecfg/extension.py: _install_files 197,
        # configure 228, _inject_config 232).  So on a FRESH install the
        # consumer's report does not exist yet, and without this the walk
        # below would find no report using that skin and correctly write
        # nothing -- leaving a station needing a second run, which is the
        # whole defect this parameter exists to remove.  It works on an
        # upgrade, where the stanza is already there, which is why it
        # would pass every test that did not install from scratch.
        #
        # The caller hands over the stanza it is about to have injected;
        # the report name and its skin come from that, and the groups are
        # written under it.  weectl's own conditional merge then fills in
        # skin, HTML_ROOT and the rest AROUND them, because it only fills
        # what is absent.  This is the mechanism ensure_default already
        # uses for [[CelestialReport]], which does not exist yet either
        # when celestial's own configure() runs.
        config = _with_pending_reports(config, pending)
    sat_tags = _configured_satellites(config)
    comet_tags = _configured_comets(config)
    wanted = {
        SATELLITES_GROUP: [f for tag in (_INSTALLER_DEFAULT_SATELLITES
                                         if sat_tags is None else sat_tags)
                           for f in satellite_fields(tag)],
        COMETS_GROUP: [f for tag in (_INSTALLER_DEFAULT_COMETS
                                     if comet_tags is None else comet_tags)
                       for f in comet_fields(tag)],
    }
    declarations = celestial_reports(config, ensure_default)
    reports = list(declarations.groups)
    # Tear-down.  weectl has no uninstall hook, so a consumer skin cannot
    # clean up after itself: uninstalling it deletes its skin.conf --
    # taking the key with it -- and prunes only what its own installer
    # config declared, leaving these two groups behind for weewx-loopdata
    # to evaluate every packet for panels that no longer exist.  A report
    # that is not ours, carries one of our groups, and whose skin.conf is
    # ABSENT is such a report, and its groups go.
    #
    # Absent, never merely unreadable.  Absence is a statement someone
    # made; no permission, a mount that is not up, a half-written file or
    # a syntax error is a question nobody can answer, and pruning on a
    # question would let a permission bit look like an uninstall.  Those
    # keep their groups and say so in the log, which is the status quo
    # and costs nothing but a stale declaration.
    # Which file answered, for every report that carries the key in both
    # places.  The stanza wins, so a stale one silently overrides a skin
    # that has since changed which panels it embeds -- and the panel's
    # own message then sends the reader to the skin.conf, which already
    # names the panel correctly.  Said once per run, per report.
    for name in declarations.groups:
        section = _report_section(config, name)
        if not isinstance(section, dict) or PANELS_KEY not in section:
            continue
        skin_value, state = skin_conf_panels(config, name)
        if state != 'found':
            continue
        stanza_written = panels_as_written(section[PANELS_KEY])
        skin_written = panels_as_written(skin_value)
        if stanza_written == skin_written:
            log.info('[StdReport] [[%s]] and its skin both set %s (%s); the report wins.  '
                     'Delete the one in weewx.conf and the skin alone decides.',
                     name, PANELS_KEY, stanza_written)
        else:
            log.warning('[StdReport] [[%s]] sets %s = %s and its skin sets %s; the REPORT wins, '
                        'so the skin is being overridden.  Delete the one in weewx.conf unless '
                        'the override is deliberate.',
                        name, PANELS_KEY, stanza_written, skin_written)

    orphaned: List[str] = []
    try:
        std_report = config['StdReport']
    except (KeyError, TypeError):
        std_report = {}
    for name in std_report:
        if name in declarations.groups or name in declarations.refused:
            continue                      # already ours, or refused by name
        if name in ('Defaults', PANELS_KEY) or not isinstance(_report_section(config, name), dict):
            continue
        if panels_value(config, name) is not None:
            continue                      # names panels: ours, handled above
        if not any(g in _fields_groups(config, name)
                   for g in (SATELLITES_GROUP, COMETS_GROUP)):
            continue                      # nothing of ours to take away
        state = skin_conf_panels(config, name)[1]
        if state == 'absent':
            orphaned.append(name)
            reports.append(name)
            declarations.groups[name] = ()
        elif state == 'unreadable':
            log.info("[StdReport] [[%s]] carries this extension's groups and names no panels, "
                     "but its skin.conf could not be read; leaving them alone.  A skin that is "
                     "gone has its groups taken away; one that cannot be read is a question, "
                     "not an answer.", name)
    # Every report's shape checked before any report is written: a
    # ValueError from the second report must not leave the first one
    # half-declared in a configuration the caller then saves.
    declared_groups = {report: _fields_groups(config, report) for report in reports}
    changes: Dict[str, Dict[str, Tuple[List[str], List[str]]]] = {}
    unread: Dict[str, Dict[str, str]] = {}
    for report in reports:
        groups = declared_groups[report]
        for group, fields in wanted.items():
            new = fields if group in declarations.groups[report] else []
            old = _group_fields(groups.get(group))
            if old == new:
                continue
            if not new and group not in declarations.groups[report]:
                # Removed because no panel of this report reads it -- the
                # reason the writers must name, whatever the configured
                # set holds.
                unread.setdefault(report, {})[group] = panels_as_written(
                    panels_value(config, report))
            changes.setdefault(report, {})[group] = (old, list(new))
            if not apply:
                continue
            if new:
                section = config.setdefault('StdReport', {}).setdefault(report, {})
                section.setdefault('LoopData', {}).setdefault('fields', {})[group] = list(new)
            elif group in groups:
                del groups[group]
    return {'satellites': list(_INSTALLER_DEFAULT_SATELLITES) if sat_tags is None
            else list(sat_tags),
            'comets': list(_INSTALLER_DEFAULT_COMETS) if comet_tags is None
            else list(comet_tags),
            'satellites_defaulted': sat_tags is None,
            'comets_defaulted': comet_tags is None,
            'reports': reports,
            'groups': dict(declarations.groups),
            'refused': dict(declarations.refused),
            'misplaced': declarations.misplaced,
            'unread': unread,
            'applied': apply,
            'changes': changes}


def pending_groups(config: Any, report: str) -> Tuple[str, ...]:
    """The groups the installer's next run would change under a report
    -- what its page asks to learn whether its declaration is out of
    date (a key added and weewxd restarted without a re-run; a
    satellite added by hand to [Skyfield]): the writer's own dry run,
    so there is no second reading of what a report should carry.  ()
    when nothing is pending, or when the dry run refuses the station
    outright (a flat fields line, which loopdata itself will not start
    on -- not a fault a page can name)."""
    try:
        return tuple(declare_page_fields(config, apply=False)['changes'].get(report, {}))
    except ValueError:
        return ()


def receipts(report: Dict[str, Any]) -> List[str]:
    """What declare_page_fields did that its writers -- the installer and
    the four verbs -- must say in the same words: the station's
    misplaced key, if any; each report skipped for a fault of its own;
    and each group removed because no panel of its report reads it --
    in the tense of what happened ('was removed', or 'would be removed'
    on a dry run).  One voice, printed verbatim by both, AFTER the
    lines that say what was written."""
    lines = []
    if report['misplaced']:
        lines.append('Nothing declared for it: %s.' % report['misplaced'])
    lines.extend('Nothing declared: %s.' % why for why in report['refused'].values())
    removed = 'was removed' if report['applied'] else 'would be removed'
    for name, removed_groups in report['unread'].items():
        for group_name, value in removed_groups.items():
            lines.append('No panel of [StdReport] [[%s]] reads %s fields (%s = %s), so its '
                         '%s group %s.'
                         % (name, group_name[:-1], PANELS_KEY, value, group_name, removed))
    return lines


# The legacy [LoopData] [[Include]] fields line -- weewx-loopdata's
# station-wide list, deprecated in 7.0 and removed by a later loopdata --
# is READ here and never written (John's ruling, 2026-08-25).  Read for
# one purpose: to say what it still costs.  loopdata 7.0 evaluates the
# line as a context of its own beside every declaring report's, so an
# entry on it that this page now declares is computed twice per loop
# packet (loopdata deliberately defers de-duplicating: "measure first",
# once every extension declares), and an almanac.<tag>.* entry left
# behind by --remove-satellite/--remove-comet has no [[Satellites]]/
# [[Comets]] entry to serve it and earns a loopdata warning at startup.

def legacy_fields_line(config: Any) -> List[str]:
    """The [LoopData] [[Include]] fields line as a list of entries; []
    when there is none.  Read the way loopdata reads it (a single value
    is one entry)."""
    try:
        value = config['LoopData']['Include']['fields']
    except (KeyError, AttributeError, TypeError):
        return []
    return _group_fields(value)


def legacy_entries_declared(config: Any, satellites: List[str],
                            comets: List[str],
                            reports: Optional[List[str]] = None) -> List[str]:
    """The legacy line's entries that this page now declares itself --
    the static set plus the fields for the given satellite and comet
    tags -- and that weewx-loopdata therefore evaluates TWICE per
    packet: once for the line's own context, once for this report's
    declaration.

    Except where it does not.  loopdata renders the line through its
    [[Formatting]] target_report, so where that report is one of the
    reports declaring these very fields (reports; the page's own report
    unless told otherwise) the two renderings are the same values from
    the same report dict, and loopdata renders them once for both.
    Those entries cost nothing, so they are not counted -- which on
    such a station leaves nothing to count, and nothing to say.

    The target must be ENABLED for that, though, and loopdata's two
    halves differ there: it builds its declaring contexts from the
    enabled reports, and renders the legacy line through target_report
    whatever its enable says.  A disabled target declares nothing, so
    there is nothing for the line to share with, and its entries are
    evaluated a second time after all.  A consumer report (9.0, one
    naming its panels with celestial_panels) in `reports` counts as
    sharing too: loopdata shares a legacy entry with any declaring
    report whose rendering matches, and a consumer declares the
    satellite and comet groups here and, with the manual's paste, the
    static set in its skin.conf -- one without the paste shares less
    than this assumes, which errs toward silence, the accepted
    direction.

    This test is a deliberate APPROXIMATION of loopdata's, and errs one
    way only.  loopdata also requires the two contexts to agree on their
    windrose band edges, and those can differ -- the legacy context
    takes the deprecated station-wide [LoopData] windrose_bands, the
    report its own -- so a station setting both, differently, and
    pointing target_report at this page shares nothing and does pay for
    the entries twice, silently.  Resolving that here would tie this
    installer to loopdata's band resolution, which is deprecated and
    dies with the line this note is about; and the error is SILENCE
    where a note could have been printed, never a note that is untrue.

    (target_report is deprecated with the line and dies with it, so it
    is read here and never named to the user.)"""
    from weeutil.weeutil import to_bool
    if reports is None:
        reports = [REPORT_NAME]
    try:
        target = config['LoopData'].get('Formatting', {}).get(
            'target_report', 'LoopDataReport')
    except (KeyError, AttributeError, TypeError):
        target = 'LoopDataReport'
    try:
        section = config['StdReport'][target]
        enabled = to_bool(section.get('enable', True))
    except (KeyError, AttributeError, TypeError, ValueError):
        # No section (the report this install is about to create), or an
        # enable nobody can parse: loopdata's own default is that a
        # report runs.
        enabled = True
    if target in reports and enabled:
        return []
    declared = set(static_page_fields())
    for tag in satellites:
        declared.update(satellite_fields(tag))
    for tag in comets:
        declared.update(comet_fields(tag))
    return [f for f in legacy_fields_line(config) if f in declared]


def legacy_entries_for_tag(config: Any, tag: str) -> List[str]:
    """The legacy line's entries reading satellite or comet tag, in any
    almanac spelling (almanac.<tag>.* and almanac(...).<tag>.*)."""
    entry_re = re.compile(r'almanac(\([^)]*\))?\.%s\.' % re.escape(tag))
    return [f for f in legacy_fields_line(config) if entry_re.match(f)]


# ===============================================================================
# The --add-satellite / --remove-satellite / --add-comet / --remove-comet
# machinery.
#
# Adding a satellite or a comet by hand takes three separate weewx.conf
# edits -- the [Skyfield] [[Satellites]] (or [[Comets]]) entry, the
# report's declared fields (nineteen per satellite, six per comet, in
# the satellites/comets group of [StdReport] [[CelestialReport]]
# [[[LoopData]]] [[[[fields]]]]), and the display name under [StdReport]
# [[Defaults]] [[[Almanac]]].  These functions converge a configuration
# to the desired state: every edit is independently idempotent, so any
# mixed starting state (satellite already configured per weewx-skyfield's
# README, fields already declared by the installer, ...) ends the same
# way, and re-running is the rename/repair path.
# ===============================================================================

# A tag becomes a report tag, a loop-field segment and a config key, so it
# must be a plain lowercase identifier.
_TAG_RE = re.compile(r'[a-z][a-z0-9_]*$')

# Body names the almanac already serves; a satellite or comet tag
# shadowing one would collide in every report tag and loop field.
# sat_<number> is likewise refused on the satellite side: it is
# weewx-skyfield's alternate spelling for a satellite already listed
# under its own tag.  Satellites and comets share the almanac.<tag>
# namespace, so each family also refuses the other family's configured
# tags and installer defaults (checked in add_satellite/add_comet, where
# the configuration is in hand).
_RESERVED_TAGS = frozenset(
    ['sun', 'moon', 'earth', 'proxima_centauri'] + _PLANETS)

# An MPC comet designation: numbered periodic (1P, 220P) or provisional
# (C/2023 A3, C/1995 O1), an optional fragment suffix on either
# (C/1947 X1-B).  Letters, digits, slash, space and hyphen only -- never
# a comma, so the [[Comets]] value cannot break the config grammar.
_COMET_DESIGNATION_RE = re.compile(
    r'(\d{1,4}[PDCXAI]|[PCDXAI]/\d{4} [A-Z]{1,2}\d*)(-[A-Z0-9]+)?$')


def _validate_satellite_tag(tag: str, adding: bool) -> None:
    if not _TAG_RE.match(tag):
        raise ValueError("Satellite tag '%s' must be a lowercase identifier: "
                         "a letter, then letters, digits or underscores "
                         "(e.g. zenit23088)." % tag)
    if not adding:
        return
    if tag in _RESERVED_TAGS:
        raise ValueError("Satellite tag '%s' is a body name the almanac "
                         "already serves; choose another tag." % tag)
    if re.match(r'sat_[0-9]+$', tag):
        raise ValueError("Satellite tag '%s' is weewx-skyfield's alternate "
                         "spelling for a listed satellite; choose a plain "
                         "tag (e.g. zenit23088)." % tag)


def _validate_comet_tag(tag: str, adding: bool) -> None:
    if not _TAG_RE.match(tag):
        raise ValueError("Comet tag '%s' must be a lowercase identifier: "
                         "a letter, then letters, digits or underscores "
                         "(e.g. halley)." % tag)
    if adding and tag in _RESERVED_TAGS:
        raise ValueError("Comet tag '%s' is a body name the almanac "
                         "already serves; choose another tag." % tag)


def _other_family_tags(config: Any, section: str,
                       defaults: Tuple[str, ...]) -> set:
    """The tags the OTHER family owns: its [Skyfield] section's keys plus
    its installer defaults (which its installer will re-add on the next
    upgrade, so they are taken even when currently absent)."""
    tags = set(defaults)
    try:
        tags.update(config['Skyfield'][section].keys())
    except (KeyError, AttributeError):
        pass
    return tags


def _group_diff(declared: Dict[str, Any], group: str,
                reports: Optional[List[str]] = None) -> Tuple[List[str], List[str]]:
    """(added, removed) for one group, unioned over the given reports
    (default: every report declared under), in order.  A verb's receipt
    unions over the reports that OWN its group: a consumer's removal of
    a group it does not own is the unread receipt's story, and would
    otherwise be printed as the owning report's."""
    added: List[str] = []
    removed: List[str] = []
    for report in declared['reports'] if reports is None else reports:
        old, new = declared['changes'].get(report, {}).get(group, ([], []))
        added.extend(f for f in new if f not in old and f not in added)
        removed.extend(f for f in old if f not in new and f not in removed)
    return added, removed


def _tags_in(entries: List[str]) -> List[str]:
    """The satellite or comet tags the entries belong to, in order, each
    once: an entry is almanac.<tag>.<member> (almanac arguments allowed
    on the head, as ever)."""
    tags: List[str] = []
    for entry in entries:
        m = re.match(r'almanac(?:\([^)]*\))?\.([a-z][a-z0-9_]*)\.', entry)
        if m is not None and m.group(1) not in tags:
            tags.append(m.group(1))
    return tags


def _declare_for_verb(config: Any, group: str,
                      hints: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """The declaration step the four verbs share: declare_page_fields
    over every declaring report (never adding REPORT_NAME -- that is
    the installer's), then (added, removed, reports): the entries the
    named group gained and lost, unioned over those reports in order,
    and the reports that OWN this verb's group -- what "under ..." and
    "already declared" are true of; a consumer report owning only the
    other family's group is not among them.  With no report owning this
    verb's group and none refused, there is no report to declare for,
    and the hint says so -- beside the station's misplaced-key receipt,
    if any (both are true there); never beside a refused report's,
    which already says there is a report and what is wrong with it.

    One declaration covers BOTH families -- there is one writer, so the
    verbs and the installer cannot disagree about what a station's
    [Skyfield] sets need -- so a run may well change the group this verb
    is not about: a station with no [[Comets]] section gets
    weewx-skyfield's default comets declared by --add-satellite, exactly
    as the next install would declare them.  Unannounced that would be
    four edits where the manual promises three, so the hint says it."""
    declared = declare_page_fields(config)
    owning = [r for r in declared['reports'] if group in declared['groups'][r]]
    added, removed = _group_diff(declared, group, owning)
    other = COMETS_GROUP if group == SATELLITES_GROUP else SATELLITES_GROUP
    other_added, other_removed = _group_diff(
        declared, other, [r for r in declared['reports'] if other in declared['groups'][r]])
    for entries, verb in ((other_added, 'declared'), (other_removed, 'undeclared')):
        if not entries:
            continue
        # The tags come from the ENTRIES, never from the family's current
        # tag list: on a run that UNdeclares (the other family's set
        # emptied since the last one) that list is empty, and the note
        # would count twelve fields belonging to "none".
        note = ('One declaration covers both families, so %d %s fields '
                '(%s) were %s as well.'
                % (len(entries), other[:-1], ', '.join(_tags_in(entries)),
                   verb))
        if verb == 'declared' and declared['%s_defaulted' % other]:
            note += (" They are weewx-skyfield's installer defaults: this "
                     'configuration has no [Skyfield] [[%s]] to follow.  '
                     '--%s-%s configures your own; an almanac that cannot '
                     'serve one omits it from loop-data.txt (one weewxd log '
                     'line per field) and the page hides that layer.'
                     % (other.capitalize(), 'add', other[:-1]))
        hints.append(note)
    hints.extend(receipts(declared))
    if not owning and not declared['refused']:
        hints.append('No report runs the Celestial skin or names a panel reading %s '
                     'fields with celestial_panels yet, so none were declared; '
                     'weewx-celestial\'s installer declares them when it is installed.'
                     % group[:-1])
    return added, removed, owning


def _stranded_legacy_hint(config: Any, tag: str, hints: List[str]) -> None:
    """The removal verbs' reminder about the legacy line, which they
    never edit: entries for the tag left on it have nothing to serve
    them once its [Skyfield] entry is gone."""
    stranded = legacy_entries_for_tag(config, tag)
    if stranded:
        hints.append('%d entries for %s remain on the legacy [LoopData] '
                     '[[Include]] fields line, which this utility never '
                     'edits; weewx-loopdata will warn about them at startup '
                     'until the line is trimmed or retired.'
                     % (len(stranded), tag))


def _set_display_name(config: Any, tag: str, name: Optional[str],
                      hints: List[str]) -> str:
    """The [StdReport] [[Defaults]] [[[Almanac]]] display name edit the
    add verbs share: never deleted by omitting the name, updated in
    place when it differs.  Returns the entry's status."""
    if 'StdReport' not in config:
        config['StdReport'] = {}
    defaults = config['StdReport'].get('Defaults', {})
    existing_name = defaults.get('Almanac', {}).get(tag)
    if name is None:
        if existing_name is None:
            # weewx-skyfield's own fallback label: the tag title-cased
            # with its underscores as spaces, which is what every panel
            # of the page shows for an unnamed tag.
            hints.append("Until a report names it, %s renders its tag "
                         "title-cased ('%s').  Re-run with --name, or add "
                         "under [StdReport] [[Defaults]] [[[Almanac]]]: "
                         "%s = <display name>."
                         % (tag, tag.replace('_', ' ').title(), tag))
        return 'not given'
    if existing_name == name:
        return 'unchanged'
    if 'Defaults' not in config['StdReport']:
        config['StdReport']['Defaults'] = {}
    if 'Almanac' not in config['StdReport']['Defaults']:
        config['StdReport']['Defaults']['Almanac'] = {}
    config['StdReport']['Defaults']['Almanac'][tag] = name
    return 'added' if existing_name is None else 'updated'


def add_satellite(config: Any, tag: str, norad: str,
                  name: Optional[str] = None) -> Dict[str, Any]:
    """Converge config (a ConfigObj) to carry satellite tag = norad: the
    [Skyfield] [[Satellites]] entry (added, or updated when the number
    differs -- the invocation is authoritative), the declared satellite
    fields (every Celestial report's satellites group rebuilt for the
    configured set, see declare_page_fields), and, when name is given, the display
    name under [StdReport] [[Defaults]] [[[Almanac]]] (an existing name
    is never deleted by omitting --name).  Raises ValueError for an
    invalid or reserved tag or a non-numeric catalog number.  Returns a
    report dict: 'satellites_entry'/'name_entry' statuses,
    'previous_norad', 'fields_added'/'fields_removed' (the entries the
    declaration gained and lost -- a rebuild can drop a stale one, and a
    verb that writes or deletes must say so), 'reports' and
    human-readable 'hints'."""
    _validate_satellite_tag(tag, adding=True)
    if not norad.isdigit():
        raise ValueError("NORAD catalog number '%s' must be all digits "
                         "(e.g. zenit23088=23088)." % norad)
    if tag in _other_family_tags(config, 'Comets', _INSTALLER_DEFAULT_COMETS):
        raise ValueError("Satellite tag '%s' is a comet tag (configured "
                         "under [Skyfield] [[Comets]], or a weewx-skyfield "
                         "installer default); satellites and comets share "
                         "the almanac.<tag> namespace, so choose another "
                         "tag." % tag)
    hints: List[str] = []
    if 'Skyfield' not in config:
        config['Skyfield'] = {}
    if 'Satellites' not in config['Skyfield']:
        config['Skyfield']['Satellites'] = {}
    satellites = config['Skyfield']['Satellites']
    previous = satellites.get(tag)
    previous_norad: Optional[str] = None
    if previous is None:
        satellites[tag] = norad
        satellites_entry = 'added'
    elif str(previous) == norad:
        satellites_entry = 'unchanged'
    else:
        previous_norad = str(previous)
        satellites[tag] = norad
        satellites_entry = 'updated'
    fields_added, fields_removed, reports = _declare_for_verb(
        config, SATELLITES_GROUP, hints)
    name_entry = _set_display_name(config, tag, name, hints)
    hints.append('Each [[Satellites]] entry is a separate CelesTrak fetch '
                 'every three hours -- keep the list short.')
    hints.append("Restart weewxd: it fetches the new satellite's orbital "
                 'elements on its worker thread soon after start, '
                 'weewx-loopdata reads the declared fields, and the '
                 'satellite appears on the Celestial page from the next '
                 'report cycle.')
    return {'satellites_entry': satellites_entry,
            'previous_norad': previous_norad,
            'fields_added': fields_added,
            'fields_removed': fields_removed,
            'reports': reports,
            'name_entry': name_entry,
            'hints': hints}


def remove_satellite(config: Any, tag: str) -> Dict[str, Any]:
    """Converge config (a ConfigObj) to carry no satellite tag: deletes
    the [Skyfield] [[Satellites]] entry, the satellite's declared fields
    (every Celestial report's satellites group rebuilt for the
    remaining set), and
    the [StdReport] [[Defaults]] [[[Almanac]]] display name.  Each piece
    is removed if present -- removing an already-absent satellite is a
    no-op, not an error.  Returns a report dict: 'satellites_entry'/
    'name_entry' statuses, the removed entry's 'norad',
    'fields_added'/'fields_removed' (both directions: the rebuild can
    write as well as delete, and either must be reported), 'reports' and
    human-readable 'hints'."""
    _validate_satellite_tag(tag, adding=False)
    hints: List[str] = []
    norad: Optional[str] = None
    satellites_entry = 'absent'
    try:
        satellites = config['Skyfield']['Satellites']
    except KeyError:
        satellites = {}
    if tag in satellites:
        norad = str(satellites.pop(tag))
        satellites_entry = 'removed'
    fields_added, fields_removed, reports = _declare_for_verb(
        config, SATELLITES_GROUP, hints)
    name_entry = 'absent'
    try:
        almanac_names = config['StdReport']['Defaults']['Almanac']
    except KeyError:
        almanac_names = {}
    if tag in almanac_names:
        del almanac_names[tag]
        name_entry = 'removed'
    if norad is not None:
        hints.append('The cached element file wxskyfield_sat_%s.tle (in the '
                     'wxskyfield directory beside the station database) is '
                     'not removed; delete it yourself if you want it gone.'
                     % norad)
    if tag in _INSTALLER_DEFAULT_SATELLITES:
        hints.append('%s is a weewx-skyfield installer default: the next '
                     'weectl extension install of weewx-skyfield re-adds it '
                     'to [[Satellites]], and the next install of '
                     'weewx-celestial declares its fields again.  Re-run '
                     '--remove-satellite %s afterwards.' % (tag, tag))
    _stranded_legacy_hint(config, tag, hints)
    hints.append('Restart weewxd to pick up the change.')
    return {'satellites_entry': satellites_entry,
            'norad': norad,
            'fields_added': fields_added,
            'fields_removed': fields_removed,
            'reports': reports,
            'name_entry': name_entry,
            'hints': hints}


def add_satellite_conf(config_path: str, output_path: str, tag: str,
                       norad: str, name: Optional[str] = None) -> Dict[str, Any]:
    """add_satellite against the configuration at config_path, written to
    output_path atomically (see _write_conf_atomically).  Returns the
    report."""
    import configobj
    config = configobj.ConfigObj(config_path, file_error=True, encoding='utf-8')
    report = add_satellite(config, tag, norad, name)
    _write_conf_atomically(config, config_path, output_path)
    return report


def remove_satellite_conf(config_path: str, output_path: str,
                          tag: str) -> Dict[str, Any]:
    """remove_satellite against the configuration at config_path, written
    to output_path atomically (see _write_conf_atomically).  Returns the
    report."""
    import configobj
    config = configobj.ConfigObj(config_path, file_error=True, encoding='utf-8')
    report = remove_satellite(config, tag)
    _write_conf_atomically(config, config_path, output_path)
    return report


def add_comet(config: Any, tag: str, designation: str,
              name: Optional[str] = None) -> Dict[str, Any]:
    """Converge config (a ConfigObj) to carry comet tag = designation: the
    [Skyfield] [[Comets]] entry (added, or updated when the designation
    differs -- the invocation is authoritative), the declared comet
    fields (every Celestial report's comets group rebuilt for the
    configured set, see declare_page_fields), and, when name is given, the display name
    under [StdReport] [[Defaults]] [[[Almanac]]] (an existing name is
    never deleted by omitting --name).  Raises ValueError for an invalid
    or reserved tag or a malformed MPC designation.  Returns a report
    dict: 'comets_entry'/'name_entry' statuses, 'previous_designation',
    'fields_added'/'fields_removed' (the entries the declaration gained
    and lost), 'reports' and human-readable 'hints'."""
    _validate_comet_tag(tag, adding=True)
    if not _COMET_DESIGNATION_RE.match(designation):
        raise ValueError("MPC designation '%s' must be a numbered periodic "
                         "designation (1P, 220P) or a provisional one "
                         "(C/2023 A3), fragment suffixes allowed "
                         "(C/1947 X1-B).  Quote designations with a space: "
                         '--add-comet a3="C/2023 A3".' % designation)
    if tag in _other_family_tags(config, 'Satellites',
                                 _INSTALLER_DEFAULT_SATELLITES):
        raise ValueError("Comet tag '%s' is a satellite tag (configured "
                         "under [Skyfield] [[Satellites]], or a "
                         "weewx-skyfield installer default); satellites "
                         "and comets share the almanac.<tag> namespace, so "
                         "choose another tag." % tag)
    hints: List[str] = []
    if 'Skyfield' not in config:
        config['Skyfield'] = {}
    if 'Comets' not in config['Skyfield']:
        config['Skyfield']['Comets'] = {}
    comets = config['Skyfield']['Comets']
    previous = comets.get(tag)
    previous_designation: Optional[str] = None
    if previous is None:
        comets[tag] = designation
        comets_entry = 'added'
    elif str(previous) == designation:
        comets_entry = 'unchanged'
    else:
        previous_designation = str(previous)
        comets[tag] = designation
        comets_entry = 'updated'
    fields_added, fields_removed, reports = _declare_for_verb(
        config, COMETS_GROUP, hints)
    name_entry = _set_display_name(config, tag, name, hints)
    hints.append('All comets share one Minor Planet Center element file, '
                 'fetched every two days -- adding a comet costs no extra '
                 'downloads, but a comet the MPC has dropped serves no '
                 'values and the page renders it absent.')
    hints.append("Restart weewxd: it reads the comet's orbital elements "
                 'from the shared MPC file (fetching it first if missing '
                 'or stale), weewx-loopdata reads the declared fields, and '
                 'the comet appears on the Celestial page from the next '
                 'report cycle.')
    return {'comets_entry': comets_entry,
            'previous_designation': previous_designation,
            'fields_added': fields_added,
            'fields_removed': fields_removed,
            'reports': reports,
            'name_entry': name_entry,
            'hints': hints}


def remove_comet(config: Any, tag: str) -> Dict[str, Any]:
    """Converge config (a ConfigObj) to carry no comet tag: deletes the
    [Skyfield] [[Comets]] entry, the comet's declared fields (every
    Celestial report's comets group rebuilt for the remaining set), and the
    [StdReport] [[Defaults]] [[[Almanac]]] display name.  Each piece is
    removed if present -- removing an already-absent comet is a no-op,
    not an error.  Returns a report dict: 'comets_entry'/'name_entry'
    statuses, the removed entry's 'designation',
    'fields_added'/'fields_removed' (both directions), 'reports' and
    human-readable 'hints'."""
    _validate_comet_tag(tag, adding=False)
    hints: List[str] = []
    designation: Optional[str] = None
    comets_entry = 'absent'
    try:
        comets = config['Skyfield']['Comets']
    except KeyError:
        comets = {}
    if tag in comets:
        designation = str(comets.pop(tag))
        comets_entry = 'removed'
    fields_added, fields_removed, reports = _declare_for_verb(
        config, COMETS_GROUP, hints)
    name_entry = 'absent'
    try:
        almanac_names = config['StdReport']['Defaults']['Almanac']
    except KeyError:
        almanac_names = {}
    if tag in almanac_names:
        del almanac_names[tag]
        name_entry = 'removed'
    if tag in _INSTALLER_DEFAULT_COMETS:
        hints.append('%s is a weewx-skyfield installer default: the next '
                     'weectl extension install of weewx-skyfield re-adds it '
                     'to [[Comets]], and the next install of weewx-celestial '
                     'declares its fields again.  Re-run --remove-comet %s '
                     'afterwards.' % (tag, tag))
    _stranded_legacy_hint(config, tag, hints)
    hints.append('Restart weewxd to pick up the change.')
    return {'comets_entry': comets_entry,
            'designation': designation,
            'fields_added': fields_added,
            'fields_removed': fields_removed,
            'reports': reports,
            'name_entry': name_entry,
            'hints': hints}


def add_comet_conf(config_path: str, output_path: str, tag: str,
                   designation: str,
                   name: Optional[str] = None) -> Dict[str, Any]:
    """add_comet against the configuration at config_path, written to
    output_path atomically (see _write_conf_atomically).  Returns the
    report."""
    import configobj
    config = configobj.ConfigObj(config_path, file_error=True, encoding='utf-8')
    report = add_comet(config, tag, designation, name)
    _write_conf_atomically(config, config_path, output_path)
    return report


def remove_comet_conf(config_path: str, output_path: str,
                      tag: str) -> Dict[str, Any]:
    """remove_comet against the configuration at config_path, written to
    output_path atomically (see _write_conf_atomically).  Returns the
    report."""
    import configobj
    config = configobj.ConfigObj(config_path, file_error=True, encoding='utf-8')
    report = remove_comet(config, tag)
    _write_conf_atomically(config, config_path, output_path)
    return report


if __name__ == '__main__':

    import configobj
    import optparse

    import weeutil.logger

    class CantOpenConfigFile(Exception):
        pass

    class CantParseConfigFile(Exception):
        pass

    def get_configuration(config_file):
        try:
            config_dict = configobj.ConfigObj(config_file, file_error=True, encoding='utf-8')
        except IOError:
            raise CantOpenConfigFile("Unable to open configuration file %s" % config_file)
        except configobj.ConfigObjError:
            raise CantParseConfigFile("Error parsing configuration file %s", config_file)

        return config_dict

    def _log_declaration(report, edit_tag, adding):
        """What the declaration did, in BOTH directions.  Every verb
        rebuilds its family's group from the configured set, so a remove
        can write (a set the rebuild re-derives) and an add can delete (a
        stale entry the rebuild drops) -- reporting only the direction
        the verb is named for leaves the other silent, which is how a
        --remove-satellite came to declare two satellites without saying
        so.

        The nothing-changed line belongs to the ADD verbs alone: "fields
        already declared for x" answers "did my add take?", and on a
        removal it would answer a question nobody asked with the
        opposite of the truth -- a no-op --remove-satellite zenit99
        printed it directly under 'no [Skyfield] [[Satellites]] entry
        for zenit99'."""
        for name in report['fields_added']:
            log.info('declared  %s' % name)
        for name in report['fields_removed']:
            log.info('undeclared  %s' % name)
        if report['fields_added'] or report['fields_removed']:
            log.info('under %s' % ', '.join('[StdReport] [[%s]] [[[LoopData]]] '
                                            '[[[[fields]]]]' % r
                                            for r in report['reports']))
        elif adding and report['reports']:
            log.info('fields already declared for %s' % edit_tag)

    weeutil.logger.setup('celestial', {})
    logging.getLogger().addHandler(logging.StreamHandler())

    usage = """Usage: python -m user.celestial --help
       python -m user.celestial --version
       python -m user.celestial --add-satellite TAG=NORAD [--name=NAME] [--config=<weewx-config-file>] (--output=FILE | --in-place)
       python -m user.celestial --remove-satellite TAG [--config=<weewx-config-file>] (--output=FILE | --in-place)
       python -m user.celestial --add-comet TAG=DESIGNATION [--name=NAME] [--config=<weewx-config-file>] (--output=FILE | --in-place)
       python -m user.celestial --remove-comet TAG [--config=<weewx-config-file>] (--output=FILE | --in-place)"""

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', action='store_true',
                      help='Display version')
    parser.add_option('--config', dest='config_file', type=str, metavar="FILE",
                      help='weewx.conf file to work on.  Default is /home/weewx/weewx.conf')
    parser.add_option('--add-satellite', dest='add_satellite', type=str, metavar='TAG=NORAD',
                      help='Add an earth satellite to the configuration, one per run: writes '
                           'TAG = NORAD under [Skyfield] [[Satellites]], declares the nineteen '
                           'fields the sample page reads per satellite (the satellites group '
                           'of [StdReport] [[CelestialReport]] [[[LoopData]]] [[[[fields]]]], '
                           'and of every report whose celestial_panels reads satellites, '
                           'rebuilt for the configured set), and (with --name) writes the '
                           'display name under [StdReport] [[Defaults]] [[[Almanac]]].  Every '
                           'edit is idempotent: pieces already present are kept, and '
                           're-running with the same TAG updates the number or name in place.  '
                           'Use with --config and exactly one of --output or --in-place.')
    parser.add_option('--name', dest='display_name', type=str, metavar='NAME',
                      help='With --add-satellite or --add-comet: the display name reports '
                           'show for it.  Without it the tag renders title-cased until a '
                           'report names it.')
    parser.add_option('--remove-satellite', dest='remove_satellite', type=str, metavar='TAG',
                      help='Remove an earth satellite from the configuration: deletes TAG '
                           'from [Skyfield] [[Satellites]], its declared fields (the '
                           'satellites group is rebuilt for the remaining set), and TAG\'s '
                           '[StdReport] [[Defaults]] [[[Almanac]]] display name -- each if '
                           'present.  Use with --config and exactly one of --output or '
                           '--in-place.')
    parser.add_option('--add-comet', dest='add_comet', type=str, metavar='TAG=DESIGNATION',
                      help='Add a comet to the configuration, one per run: writes '
                           'TAG = DESIGNATION (an MPC designation, e.g. 1P or "C/2023 A3" '
                           '-- quote one with a space) under [Skyfield] [[Comets]], declares '
                           'the six fields the sample page reads per comet (the comets group '
                           'of [StdReport] [[CelestialReport]] [[[LoopData]]] [[[[fields]]]], '
                           'and of every report whose celestial_panels reads comets, '
                           'rebuilt for the configured set), and (with --name) writes the '
                           'display name under [StdReport] [[Defaults]] [[[Almanac]]].  Every edit is '
                           'idempotent: pieces already present are kept, and re-running '
                           'with the same TAG updates the designation or name in place.  '
                           'Use with --config and exactly one of --output or --in-place.')
    parser.add_option('--remove-comet', dest='remove_comet', type=str, metavar='TAG',
                      help='Remove a comet from the configuration: deletes TAG from '
                           '[Skyfield] [[Comets]], its declared fields (the comets group is '
                           'rebuilt for the remaining set), and TAG\'s [StdReport] '
                           '[[Defaults]] [[[Almanac]]] display name -- each if present.  Use '
                           'with --config and exactly one of --output or --in-place.')
    parser.add_option('--output', dest='output_file', type=str, metavar='FILE',
                      help='Write the rewritten configuration to FILE, leaving the --config '
                           'file untouched (diff them, then move FILE into place).')
    parser.add_option('--in-place', dest='in_place', action='store_true',
                      help='Rewrite the --config file itself '
                           '(a .bak-celestial-%s backup is made first).' % CELESTIAL_VERSION)
    (options, args) = parser.parse_args()

    if options.version:
        log.info("Celestial version is %s." % CELESTIAL_VERSION)
        exit(0)

    if sum([bool(options.add_satellite), bool(options.remove_satellite),
            bool(options.add_comet), bool(options.remove_comet)]) > 1:
        log.error('Specify only one of --add-satellite, --remove-satellite, '
                  '--add-comet or --remove-comet.')
        exit(1)
    if options.display_name and not (options.add_satellite or options.add_comet):
        log.error('--name only applies with --add-satellite or --add-comet.')
        exit(1)

    def resolve_output(config_path):
        """The output path for a config rewrite, honoring --in-place (the
        versioned backup is made here, so callers validate first)."""
        import shutil
        if options.in_place:
            backup = config_path + '.bak-celestial-' + CELESTIAL_VERSION
            if os.path.exists(backup):
                log.error('Backup %s already exists; move it aside first.' % backup)
                exit(1)
            shutil.copy2(config_path, backup)
            log.info('Backed up %s to %s' % (config_path, backup))
            return config_path
        return options.output_file

    if (options.add_satellite or options.remove_satellite
            or options.add_comet or options.remove_comet):
        edit_config = options.config_file if options.config_file else '/home/weewx/weewx.conf'
        if sum([bool(options.output_file), bool(options.in_place)]) != 1:
            log.error('Specify exactly one of --output FILE or --in-place.')
            exit(1)
        config = get_configuration(edit_config)
        try:
            if options.add_satellite:
                edit_tag, sep, edit_value = options.add_satellite.partition('=')
                edit_tag = edit_tag.strip()
                edit_value = edit_value.strip()
                if not sep or not edit_tag or not edit_value:
                    raise ValueError('--add-satellite takes TAG=NORAD '
                                     '(e.g. --add-satellite zenit23088=23088).')
                report = add_satellite(config, edit_tag, edit_value,
                                       options.display_name)
            elif options.remove_satellite:
                edit_tag = options.remove_satellite.strip()
                report = remove_satellite(config, edit_tag)
            elif options.add_comet:
                edit_tag, sep, edit_value = options.add_comet.partition('=')
                edit_tag = edit_tag.strip()
                edit_value = edit_value.strip()
                if not sep or not edit_tag or not edit_value:
                    raise ValueError('--add-comet takes TAG=DESIGNATION '
                                     '(e.g. --add-comet halley=1P, or '
                                     '--add-comet a3="C/2023 A3" -- quote a '
                                     'designation with a space).')
                report = add_comet(config, edit_tag, edit_value,
                                   options.display_name)
            else:
                edit_tag = options.remove_comet.strip()
                report = remove_comet(config, edit_tag)
        except ValueError as e:
            log.error(str(e))
            exit(1)
        edit_output = resolve_output(edit_config)
        _write_conf_atomically(config, edit_config, edit_output)
        log.info('Wrote %s' % edit_output)
        if options.add_satellite or options.add_comet:
            section = '[[Satellites]]' if options.add_satellite else '[[Comets]]'
            entry = report['satellites_entry' if options.add_satellite
                           else 'comets_entry']
            previous = report['previous_norad' if options.add_satellite
                              else 'previous_designation']
            if entry == 'added':
                log.info('added  [Skyfield] %s %s = %s' % (section, edit_tag, edit_value))
            elif entry == 'updated':
                log.info('updated  [Skyfield] %s %s = %s (was %s)'
                         % (section, edit_tag, edit_value, previous))
            else:
                log.info('kept  [Skyfield] %s %s = %s (already present)'
                         % (section, edit_tag, edit_value))
            _log_declaration(report, edit_tag, True)
            if report['name_entry'] in ('added', 'updated'):
                log.info('%s  [StdReport] [[Defaults]] [[[Almanac]]] %s = %s'
                         % (report['name_entry'], edit_tag, options.display_name))
            elif report['name_entry'] == 'unchanged':
                log.info('kept  [StdReport] [[Defaults]] [[[Almanac]]] %s (already named)'
                         % edit_tag)
        else:
            section = '[[Satellites]]' if options.remove_satellite else '[[Comets]]'
            entry = report['satellites_entry' if options.remove_satellite
                           else 'comets_entry']
            removed_value = report['norad' if options.remove_satellite
                                   else 'designation']
            if entry == 'removed':
                log.info('removed  [Skyfield] %s %s = %s'
                         % (section, edit_tag, removed_value))
            else:
                log.info('no [Skyfield] %s entry for %s' % (section, edit_tag))
            _log_declaration(report, edit_tag, False)
            if report['name_entry'] == 'removed':
                log.info('removed  [StdReport] [[Defaults]] [[[Almanac]]] %s' % edit_tag)
        for note in report['hints']:
            log.info('NOTE: %s' % note)
        exit(0)

    parser.print_help()
