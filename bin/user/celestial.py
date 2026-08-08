"""
celestial.py

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

weewx-celestial ships a live celestial report (the bundled Celestial skin):
a single Geocentric panel -- Earth at the center, every body placed by
compass bearing and log distance, with odometer distance readouts that tick
between loop refreshes -- whose values are weewx-loopdata 5.0 almanac
fields evaluated against the registered almanac (weewx-skyfield strongly
recommended).  This module provides the command-line utility that migrates
a pre-6.0 [LoopData] [[Include]] fields line to the almanac grammar.

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

from typing import Any, Dict, List, Optional, Tuple

import weewx

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '8.0'

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
# The --migrate-loopdata-fields machinery.
#
# 6.0 removed this extension's loop fields; their replacements are
# weewx-loopdata 5.0 almanac fields.  The maps below rewrite a user's
# [LoopData] [[Include]] fields line: pre-3.0 PascalCase names first collapse
# to their 4.0 camelCase names (_MIGRATION_FIELD_MAP, unchanged since 4.0),
# and every celestial camelCase entry is then rewritten to its almanac
# equivalent (_ALMANAC_FIELD_MAP).  These maps exist SOLELY for the
# command-line utility and must never grow another consumer.
# ===============================================================================

# Pre-3.0 loop field names mapped to their 4.0 replacements.
_MIGRATION_FIELD_MAP: Dict[str, str] = {
    'AstronomicalTwilightEnd'  : 'astronomicalTwilightEnd',
    'AstronomicalTwilightStart': 'astronomicalTwilightStart',
    'CivilTwilightEnd'         : 'civilTwilightEnd',
    'CivilTwilightStart'       : 'civilTwilightStart',
    'daySunshineDur'           : 'daylightDur',
    'EarthJupiterDistance'     : 'earthJupiterDistance',
    'EarthMarsDistance'        : 'earthMarsDistance',
    'EarthMercuryDistance'     : 'earthMercuryDistance',
    'EarthMoonDistance'        : 'earthMoonDistance',
    'EarthNeptuneDistance'     : 'earthNeptuneDistance',
    'EarthPlutoDistance'       : 'earthPlutoDistance',
    'EarthSaturnDistance'      : 'earthSaturnDistance',
    'EarthSunDistance'         : 'earthSunDistance',
    'EarthUranusDistance'      : 'earthUranusDistance',
    'EarthVenusDistance'       : 'earthVenusDistance',
    'MoonAltitude'             : 'moonAltitude',
    'MoonAzimuth'              : 'moonAzimuth',
    'MoonDeclination'          : 'moonDeclination',
    'MoonFullness'             : 'moonFullness',
    'MoonPhase'                : 'moonPhase',
    'MoonRightAscension'       : 'moonRightAscension',
    'Moonrise'                 : 'moonrise',
    'Moonset'                  : 'moonset',
    'MoonTransit'              : 'moonTransit',
    'NauticalTwilightEnd'      : 'nauticalTwilightEnd',
    'NauticalTwilightStart'    : 'nauticalTwilightStart',
    'NextEquinox'              : 'nextEquinox',
    'NextFullMoon'             : 'nextFullMoon',
    'NextNewMoon'              : 'nextNewMoon',
    'NextSolstice'             : 'nextSolstice',
    'SunAltitude'              : 'sunAltitude',
    'SunAzimuth'               : 'sunAzimuth',
    'SunDeclination'           : 'sunDeclination',
    'SunRightAscension'        : 'sunRightAscension',
    'Sunrise'                  : 'sunrise',
    'Sunset'                   : 'sunset',
    'SunTransit'               : 'sunTransit',
    'yesterdaySunshineDur'     : 'yesterdayDaylightDur',
}

def _body_angles(body: str) -> Dict[str, Tuple[str, str]]:
    """The four az/alt/ra/dec entries for one body: (raw, formatted) almanac
    equivalents.  The raw renditions are plain decimal degrees, exactly like
    the old .raw fields; the formatted renditions are the almanac's
    ValueHelper tags (formatting may differ slightly from the old fields)."""
    return {
        '%sAzimuth' % body       : ('almanac.%s.az' % body,  'almanac.%s.azimuth' % body),
        '%sAltitude' % body      : ('almanac.%s.alt' % body, 'almanac.%s.altitude' % body),
        '%sRightAscension' % body: ('almanac.%s.ra' % body,  'almanac.%s.topo_ra' % body),
        '%sDeclination' % body   : ('almanac.%s.dec' % body, 'almanac.%s.topo_dec' % body),
    }

_MIGRATION_PLANETS: List[str] = ['mercury', 'venus', 'mars', 'jupiter',
                                 'saturn', 'uranus', 'neptune', 'pluto']

# 4.0 celestial loop-field names mapped to their weewx-loopdata almanac
# equivalents, as (raw-rendition entry, formatted-rendition entry).  The raw
# renditions of times and durations carry a pinned unit segment
# (.unix_epoch, .second): the old loop fields always emitted epoch seconds
# and seconds regardless of report settings, and an unpinned almanac .raw
# follows the target report's converter -- under a report with [Units]
# [[Groups]] overrides (e.g. group_deltatime = hour) it would change
# meaning.  Unit segments evaluate on every loopdata >= 5.0.
_ALMANAC_FIELD_MAP: Dict[str, Tuple[str, str]] = {
    'sunrise'                  : ('almanac.sunrise.unix_epoch.raw', 'almanac.sunrise'),
    'sunset'                   : ('almanac.sunset.unix_epoch.raw', 'almanac.sunset'),
    'sunTransit'               : ('almanac.sun.transit.unix_epoch.raw', 'almanac.sun.transit'),
    'tomorrowSunrise'          : ('almanac(days=1).sunrise.unix_epoch.raw', 'almanac(days=1).sunrise'),
    'tomorrowSunset'           : ('almanac(days=1).sunset.unix_epoch.raw', 'almanac(days=1).sunset'),
    'daylightDur'              : ('almanac.sun.visible.second.raw', 'almanac.sun.visible'),
    'yesterdayDaylightDur'     : ('almanac(days=-1).sun.visible.second.raw', 'almanac(days=-1).sun.visible'),
    'astronomicalTwilightStart': ('almanac(horizon=-18).sun(use_center=1).rise.unix_epoch.raw',
                                  'almanac(horizon=-18).sun(use_center=1).rise'),
    'nauticalTwilightStart'    : ('almanac(horizon=-12).sun(use_center=1).rise.unix_epoch.raw',
                                  'almanac(horizon=-12).sun(use_center=1).rise'),
    'civilTwilightStart'       : ('almanac(horizon=-6).sun(use_center=1).rise.unix_epoch.raw',
                                  'almanac(horizon=-6).sun(use_center=1).rise'),
    'civilTwilightEnd'         : ('almanac(horizon=-6).sun(use_center=1).set.unix_epoch.raw',
                                  'almanac(horizon=-6).sun(use_center=1).set'),
    'nauticalTwilightEnd'      : ('almanac(horizon=-12).sun(use_center=1).set.unix_epoch.raw',
                                  'almanac(horizon=-12).sun(use_center=1).set'),
    'astronomicalTwilightEnd'  : ('almanac(horizon=-18).sun(use_center=1).set.unix_epoch.raw',
                                  'almanac(horizon=-18).sun(use_center=1).set'),
    'moonrise'                 : ('almanac.moon.rise.unix_epoch.raw', 'almanac.moon.rise'),
    'moonset'                  : ('almanac.moon.set.unix_epoch.raw', 'almanac.moon.set'),
    'moonTransit'              : ('almanac.moon.transit.unix_epoch.raw', 'almanac.moon.transit'),
    'nextEquinox'              : ('almanac.next_equinox.unix_epoch.raw', 'almanac.next_equinox'),
    'nextSolstice'             : ('almanac.next_solstice.unix_epoch.raw', 'almanac.next_solstice'),
    'nextFullMoon'             : ('almanac.next_full_moon.unix_epoch.raw', 'almanac.next_full_moon'),
    'nextNewMoon'              : ('almanac.next_new_moon.unix_epoch.raw', 'almanac.next_new_moon'),
    'moonPhase'                : ('almanac.moon_phase', 'almanac.moon_phase'),
    'moonPhaseIndex'           : ('almanac.moon_index', 'almanac.moon_index'),
    'moonFullness'             : ('almanac.moon.phase', 'almanac.moon.phase'),
    'earthSunDistance'         : ('almanac.sun.earth_distance', 'almanac.sun.earth_distance'),
    'earthMoonDistance'        : ('almanac.moon.earth_distance', 'almanac.moon.earth_distance'),
    'earthProximaCentauriDistance': ('almanac.proxima_centauri.earth_distance',
                                     'almanac.proxima_centauri.earth_distance'),
}
_ALMANAC_FIELD_MAP.update(_body_angles('sun'))
_ALMANAC_FIELD_MAP.update(_body_angles('moon'))
for _planet in _MIGRATION_PLANETS:
    _ALMANAC_FIELD_MAP.update(_body_angles(_planet))
    _cap = _planet.capitalize()
    _ALMANAC_FIELD_MAP['earth%sDistance' % _cap] = (
        'almanac.%s.earth_distance' % _planet, 'almanac.%s.earth_distance' % _planet)

# The fields the sample report (the 7.0 Geocentric panel) reads; the
# migrator appends the missing ones.  Per body: az places the dial dot,
# alt decides above/below-horizon rendering, earth_distance (raw AU)
# drives the odometer; the moon adds its phase percent and the next
# full/new moon instants (waxing = full before new) for the phase disc --
# pinned to epoch seconds (.unix_epoch) because the page does date math
# on them, so a [Units] [[Groups]] group_time override on loopdata's
# target report must not change their meaning.
# current.dateTime.raw is loopdata's own field, the live-age indicator
# and the extrapolation anchor.
_MIGRATION_NEW_FIELDS: List[str] = [
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
    # The satellite layer (8.0): weewx-skyfield 2.0's installer-default
    # satellites.  These iss/tiangong members double as the per-satellite
    # PATTERN: the migrator substitutes the configured [Skyfield]
    # [[Satellites]] tags for them (via satellite_fields), falling back
    # to these defaults only when the configuration has no [[Satellites]]
    # section to follow.  An almanac that cannot serve one omits its keys from
    # loop-data.txt (loopdata logs once per field) and the page hides
    # that layer.  next_visible_pass feeds the Next Visible Pass panel's roster;
    # next_pass -- any pass, its visible bool the row's visible/not-
    # visible tag -- feeds the dome's.  Times, the duration and the peak
    # altitude use pinned-unit spellings -- the 7.5/7.6 doctrine: a
    # [Units] [[Groups]] override on loopdata's target report must never
    # change a field's meaning.
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
]


# Entries this migrator itself appended unpinned through 7.5; a re-run
# upgrades them to the pinned spellings the sample page reads since 7.6.
_MIGRATION_UPGRADED_FIELDS: Dict[str, str] = {
    'almanac.next_full_moon.raw': 'almanac.next_full_moon.unix_epoch.raw',
    'almanac.next_new_moon.raw': 'almanac.next_new_moon.unix_epoch.raw',
}


def _migrate_one_field(field: str) -> Tuple[Optional[str], Optional[str]]:
    """One fields-line entry rewritten to its almanac equivalent.  Returns
    (new_entry, note): (field, None) for entries that are not celestial loop
    fields; (None, note) for moonWaxing, which has no almanac equivalent."""
    if field in _MIGRATION_UPGRADED_FIELDS:
        return _MIGRATION_UPGRADED_FIELDS[field], None
    parts = field.split('.')
    if len(parts) < 2 or parts[0] != 'current':
        return field, None
    name = _MIGRATION_FIELD_MAP.get(parts[1], parts[1])
    if name == 'moonWaxing':
        return None, ('%s dropped: derive waxing in the page instead -- the moon '
                      'is waxing when almanac.next_full_moon.unix_epoch.raw < '
                      'almanac.next_new_moon.unix_epoch.raw.' % field)
    if name not in _ALMANAC_FIELD_MAP:
        return field, None
    raw_entry, formatted_entry = _ALMANAC_FIELD_MAP[name]
    suffix = '.'.join(parts[2:])
    if suffix == 'raw':
        new_field = raw_entry
    elif suffix == '':
        new_field = formatted_entry
    elif suffix == 'formatted' and raw_entry != formatted_entry:
        new_field = formatted_entry + '.formatted'
    else:
        # ordinal_compass and the like: keep the data, best effort.
        new_field = formatted_entry
    return new_field, None


def migrate_loopdata_fields(fields: List[str],
                            satellites: Optional[List[str]] = None
                            ) -> Tuple[List[str], Dict[str, Any]]:
    """Rewrite a pre-6.0 [LoopData] [[Include]] fields list: rewrite every
    celestial loop-field entry (including pre-3.0 PascalCase names) to its
    weewx-loopdata almanac equivalent in place (preserving the list's
    order), drop moonWaxing (no equivalent; the sample report derives it)
    and the duplicates the rewrites create (keeping the first occurrence),
    and append the fields the current sample report needs.  The satellite
    entries follow satellites -- the configuration's [Skyfield]
    [[Satellites]] tags, in order; an empty list appends none.  None means
    there was no [[Satellites]] section to follow (weewx-skyfield absent
    or pre-2.0): the installer defaults are appended, provisioning for the
    [[Satellites]] weewx-skyfield 2.0's installer injects.  Entries that are not
    celestial loop fields are never touched -- a satellite entry already
    on the line stays regardless of satellites.  Returns (new_fields, report)
    where report maps 'renamed' to (old, new) pairs, 'dropped'/'added' to
    field names, and 'notes' to human-readable caveats."""
    result: List[str] = []
    seen: set = set()
    renamed: List[Tuple[str, str]] = []
    dropped: List[str] = []
    added: List[str] = []
    notes: List[str] = []
    any_distance = False
    any_fullness = False
    for field in fields:
        new_field, note = _migrate_one_field(field)
        if note is not None:
            notes.append(note)
        if new_field is None:
            dropped.append(field)
            continue
        if new_field != field:
            renamed.append((field, new_field))
            if 'earth_distance' in new_field:
                any_distance = True
            if new_field.startswith('almanac.moon.phase'):
                any_fullness = True
            field = new_field
        if field in seen:
            dropped.append(field)
            continue
        seen.add(field)
        result.append(field)
    sat_tags = (list(_INSTALLER_DEFAULT_SATELLITES) if satellites is None
                else list(satellites))
    default_prefixes = tuple('almanac.%s.' % tag
                             for tag in _INSTALLER_DEFAULT_SATELLITES)
    wanted = [f for f in _MIGRATION_NEW_FIELDS
              if not f.startswith(default_prefixes)]
    for tag in sat_tags:
        wanted.extend(satellite_fields(tag))
    for field in wanted:
        if field not in seen:
            seen.add(field)
            result.append(field)
            added.append(field)
    if any_distance:
        notes.append('Distances now arrive as raw astronomical units (the value '
                     'reports show), no longer miles/km; pages must convert '
                     '(the sample report shows how).  Proxima Centauri is '
                     'AU as well, no longer light years.')
    if any_fullness:
        notes.append('almanac.moon.phase is a raw percent (e.g. 33.6), no '
                     'longer a formatted string; pages format it themselves.')
    added_sat_tags = [tag for tag in sat_tags
                      if any(f.startswith('almanac.%s.' % tag) for f in added)]
    if added_sat_tags:
        entries = ', '.join('almanac.%s.*' % tag for tag in added_sat_tags)
        if satellites is None:
            notes.append('The satellite entries (%s) are weewx-skyfield '
                         "2.0's installer defaults, appended because the "
                         'configuration has no [Skyfield] [[Satellites]] to '
                         'follow; an almanac that cannot serve one omits it '
                         'from loop-data.txt (one weewxd log line per field) '
                         'and the sample page hides its satellite layer.'
                         % entries)
        else:
            notes.append('The satellite entries (%s) follow your [Skyfield] '
                         '[[Satellites]]; an almanac that cannot serve one '
                         'omits it from loop-data.txt (one weewxd log line '
                         'per field) and the sample page hides its satellite '
                         'layer.' % entries)
    elif satellites is not None and not sat_tags:
        notes.append('[Skyfield] [[Satellites]] is empty, so no satellite '
                     'fields were appended; --add-satellite configures a '
                     'satellite end to end when you want one.')
    return result, {'renamed': renamed, 'dropped': dropped, 'added': added,
                    'notes': notes}


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
    order -- the satellite set the migrator provisions fields for.  None
    when the configuration has no [[Satellites]] section to follow
    (weewx-skyfield absent or pre-2.0); a present-but-empty section is
    authoritative and returns [], so a deliberately emptied satellite set
    is never resurrected."""
    try:
        return list(config['Skyfield']['Satellites'].keys())
    except (KeyError, AttributeError):
        return None


def migrate_loopdata_conf(config_path: str, output_path: str) -> Dict[str, Any]:
    """Rewrite config_path's [LoopData] [[Include]] fields entry
    (see migrate_loopdata_fields; the satellite entries follow the
    configuration's own [Skyfield] [[Satellites]]) and write the complete
    configuration to output_path atomically (see _write_conf_atomically).
    Returns the migration report."""
    import configobj
    config = configobj.ConfigObj(config_path, file_error=True, encoding='utf-8')
    try:
        fields = config['LoopData']['Include']['fields']
    except KeyError:
        raise KeyError('%s has no [LoopData] [[Include]] fields entry' % config_path)
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(',') if f.strip()]
    new_fields, report = migrate_loopdata_fields(list(fields),
                                                 _configured_satellites(config))
    config['LoopData']['Include']['fields'] = new_fields
    _write_conf_atomically(config, config_path, output_path)
    return report


# ===============================================================================
# The --add-satellite / --remove-satellite machinery.
#
# Adding a satellite by hand takes three separate weewx.conf edits -- the
# [Skyfield] [[Satellites]] entry, nineteen [LoopData] [[Include]] fields
# entries, and the display name under [StdReport] [[Defaults]]
# [[[Almanac]]].  These functions converge a configuration to the desired
# state: every edit is independently idempotent, so any mixed starting
# state (satellite already configured per weewx-skyfield's README, fields
# already appended by hand, ...) ends the same way, and re-running is the
# rename/repair path.
# ===============================================================================

# A tag becomes a report tag, a loop-field segment and a config key, so it
# must be a plain lowercase identifier.
_SATELLITE_TAG_RE = re.compile(r'[a-z][a-z0-9_]*$')

# Body names the almanac already serves; a satellite tag shadowing one
# would collide in every report tag and loop field.  sat_<number> is
# likewise refused: it is weewx-skyfield's alternate spelling for a
# satellite already listed under its own tag.
_RESERVED_SATELLITE_TAGS = frozenset(
    ['sun', 'moon', 'earth', 'proxima_centauri'] + _MIGRATION_PLANETS)

# weewx-skyfield's installer defaults: weectl's conditional merge re-adds
# a deleted default to [[Satellites]] on the next weewx-skyfield upgrade
# (only there -- no installer touches the fields line), so removing one
# earns a warning.  Also the migrator's fallback satellite set when the
# configuration has no [[Satellites]] section to follow.
_INSTALLER_DEFAULT_SATELLITES = ('iss', 'tiangong')

# Matches a fields entry belonging to a satellite tag, almanac arguments
# allowed: almanac.<tag>.* and almanac(...).<tag>.*.
def _satellite_entry_re(tag: str) -> 're.Pattern[str]':
    return re.compile(r'almanac(\([^)]*\))?\.%s\.' % re.escape(tag))


def satellite_fields(tag: str) -> List[str]:
    """The nineteen [LoopData] [[Include]] fields entries the sample page
    reads per satellite: the almanac.iss.* members of _MIGRATION_NEW_FIELDS
    with the tag substituted -- derived, not copied, so the page's
    satellite consumption keeps one source of truth."""
    return [field.replace('almanac.iss.', 'almanac.%s.' % tag, 1)
            for field in _MIGRATION_NEW_FIELDS
            if field.startswith('almanac.iss.')]


def _validate_satellite_tag(tag: str, adding: bool) -> None:
    if not _SATELLITE_TAG_RE.match(tag):
        raise ValueError("Satellite tag '%s' must be a lowercase identifier: "
                         "a letter, then letters, digits or underscores "
                         "(e.g. zenit23088)." % tag)
    if not adding:
        return
    if tag in _RESERVED_SATELLITE_TAGS:
        raise ValueError("Satellite tag '%s' is a body name the almanac "
                         "already serves; choose another tag." % tag)
    if re.match(r'sat_[0-9]+$', tag):
        raise ValueError("Satellite tag '%s' is weewx-skyfield's alternate "
                         "spelling for a listed satellite; choose a plain "
                         "tag (e.g. zenit23088)." % tag)


def _loopdata_fields(config: Any) -> Optional[List[str]]:
    """The [LoopData] [[Include]] fields entry as a list, or None when the
    configuration has none."""
    try:
        fields = config['LoopData']['Include']['fields']
    except KeyError:
        return None
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(',') if f.strip()]
    return list(fields)


def add_satellite(config: Any, tag: str, norad: str,
                  name: Optional[str] = None) -> Dict[str, Any]:
    """Converge config (a ConfigObj) to carry satellite tag = norad: the
    [Skyfield] [[Satellites]] entry (added, or updated when the number
    differs -- the invocation is authoritative), the nineteen fields
    entries appended to [LoopData] [[Include]] fields (entries already
    present are left in place), and, when name is given, the display name
    under [StdReport] [[Defaults]] [[[Almanac]]] (an existing name is
    never deleted by omitting --name).  Raises ValueError for an invalid
    or reserved tag, a non-numeric catalog number, or a configuration
    with no [LoopData] [[Include]] fields entry.  Returns a report dict:
    'satellites_entry'/'name_entry' statuses, 'previous_norad',
    'fields_added' and human-readable 'hints'."""
    _validate_satellite_tag(tag, adding=True)
    if not norad.isdigit():
        raise ValueError("NORAD catalog number '%s' must be all digits "
                         "(e.g. zenit23088=23088)." % norad)
    fields = _loopdata_fields(config)
    if fields is None:
        raise ValueError('The configuration has no [LoopData] [[Include]] '
                         'fields entry.  Install weewx-loopdata and run '
                         '--migrate-loopdata-fields first; --add-satellite '
                         'only appends to an existing fields line.')
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
    present = set(fields)
    fields_added = [f for f in satellite_fields(tag) if f not in present]
    if fields_added:
        config['LoopData']['Include']['fields'] = fields + fields_added
    if 'StdReport' not in config:
        config['StdReport'] = {}
    defaults = config['StdReport'].get('Defaults', {})
    existing_name = defaults.get('Almanac', {}).get(tag)
    if name is None:
        name_entry = 'not given'
        if existing_name is None:
            hints.append("Until a report names it, %s renders its tag "
                         "title-cased ('%s').  Re-run with --name, or add "
                         "under [StdReport] [[Defaults]] [[[Almanac]]]: "
                         "%s = <display name>."
                         % (tag, tag.title(), tag))
    elif existing_name == name:
        name_entry = 'unchanged'
    else:
        if 'Defaults' not in config['StdReport']:
            config['StdReport']['Defaults'] = {}
        if 'Almanac' not in config['StdReport']['Defaults']:
            config['StdReport']['Defaults']['Almanac'] = {}
        config['StdReport']['Defaults']['Almanac'][tag] = name
        name_entry = 'added' if existing_name is None else 'updated'
    hints.append('Each [[Satellites]] entry is a separate CelesTrak fetch '
                 'every three hours -- keep the list short.')
    hints.append("Restart weewxd: it fetches the new satellite's orbital "
                 'elements on its worker thread soon after start, and the '
                 'satellite appears on the Celestial page from the next '
                 'report cycle.')
    return {'satellites_entry': satellites_entry,
            'previous_norad': previous_norad,
            'fields_added': fields_added,
            'name_entry': name_entry,
            'hints': hints}


def remove_satellite(config: Any, tag: str) -> Dict[str, Any]:
    """Converge config (a ConfigObj) to carry no satellite tag: deletes
    the [Skyfield] [[Satellites]] entry, every fields entry reading the
    satellite (almanac.<tag>.* in any spelling, almanac arguments
    included), and the [StdReport] [[Defaults]] [[[Almanac]]] display
    name.  Each piece is removed if present -- removing an
    already-absent satellite is a no-op, not an error.  Returns a report
    dict: 'satellites_entry'/'name_entry' statuses, the removed entry's
    'norad', 'fields_removed' and human-readable 'hints'."""
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
    entry_re = _satellite_entry_re(tag)
    fields = _loopdata_fields(config)
    fields_removed: List[str] = []
    if fields is not None:
        kept = [f for f in fields if not entry_re.match(f)]
        fields_removed = [f for f in fields if entry_re.match(f)]
        if fields_removed:
            config['LoopData']['Include']['fields'] = kept
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
                     'to [[Satellites]] (only -- the fields line stays as '
                     'you left it).  Re-run --remove-satellite %s '
                     'afterwards.' % (tag, tag))
    hints.append('Restart weewxd to pick up the change.')
    return {'satellites_entry': satellites_entry,
            'norad': norad,
            'fields_removed': fields_removed,
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

    weeutil.logger.setup('celestial', {})
    logging.getLogger().addHandler(logging.StreamHandler())

    usage = """Usage: python -m user.celestial --help
       python -m user.celestial --version
       python -m user.celestial --migrate-loopdata-fields [--config=<weewx-config-file>] (--output=FILE | --in-place | --print-fields-value)
       python -m user.celestial --add-satellite TAG=NORAD [--name=NAME] [--config=<weewx-config-file>] (--output=FILE | --in-place)
       python -m user.celestial --remove-satellite TAG [--config=<weewx-config-file>] (--output=FILE | --in-place)"""

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', action='store_true',
                      help='Display version')
    parser.add_option('--config', dest='config_file', type=str, metavar="FILE",
                      help='weewx.conf file to work on.  Default is /home/weewx/weewx.conf')
    parser.add_option('--migrate-loopdata-fields', dest='migrate', action='store_true',
                      help='Rewrite a pre-6.0 [LoopData] [[Include]] fields line: rewrite '
                           'every celestial loop field (including pre-3.0 PascalCase names) '
                           'to its weewx-loopdata almanac equivalent (keeping the line\'s '
                           'order), drop moonWaxing and the duplicates the rewrites create, '
                           'and append the fields the current sample report needs.  The '
                           'satellite entries follow the configuration\'s [Skyfield] '
                           '[[Satellites]] (weewx-skyfield\'s installer defaults when there '
                           'is no [[Satellites]] section to follow).  '
                           'Non-celestial fields are never touched.  Use with --config and '
                           'exactly one of --output, --in-place or --print-fields-value.')
    parser.add_option('--add-satellite', dest='add_satellite', type=str, metavar='TAG=NORAD',
                      help='Add an earth satellite to the configuration, one per run: writes '
                           'TAG = NORAD under [Skyfield] [[Satellites]], appends the nineteen '
                           '[LoopData] [[Include]] fields entries the sample page reads, and '
                           '(with --name) writes the display name under [StdReport] '
                           '[[Defaults]] [[[Almanac]]].  Every edit is idempotent: pieces '
                           'already present are kept, and re-running with the same TAG '
                           'updates the number or name in place.  Use with --config and '
                           'exactly one of --output or --in-place.')
    parser.add_option('--name', dest='satellite_name', type=str, metavar='NAME',
                      help='With --add-satellite: the display name reports show for the '
                           'satellite.  Without it the satellite renders its tag title-cased '
                           'until a report names it.')
    parser.add_option('--remove-satellite', dest='remove_satellite', type=str, metavar='TAG',
                      help='Remove an earth satellite from the configuration: deletes TAG '
                           'from [Skyfield] [[Satellites]], every almanac.TAG.* entry from '
                           'the [LoopData] [[Include]] fields line, and TAG\'s [StdReport] '
                           '[[Defaults]] [[[Almanac]]] display name -- each if present.  Use '
                           'with --config and exactly one of --output or --in-place.')
    parser.add_option('--output', dest='output_file', type=str, metavar='FILE',
                      help='Write the rewritten configuration to FILE, leaving the --config '
                           'file untouched (diff them, then move FILE into place).')
    parser.add_option('--in-place', dest='in_place', action='store_true',
                      help='Rewrite the --config file itself '
                           '(a .bak-celestial-%s backup is made first).' % CELESTIAL_VERSION)
    parser.add_option('--print-fields-value', dest='print_fields', action='store_true',
                      help='With --migrate-loopdata-fields: print the migrated fields value as '
                           'a bare comma-separated list, ready to paste into weewx.conf (do '
                           'NOT add brackets or quotes).')
    (options, args) = parser.parse_args()

    if options.version:
        log.info("Celestial version is %s." % CELESTIAL_VERSION)
        exit(0)

    if sum([bool(options.migrate), bool(options.add_satellite),
            bool(options.remove_satellite)]) > 1:
        log.error('Specify only one of --migrate-loopdata-fields, '
                  '--add-satellite or --remove-satellite.')
        exit(1)
    if options.satellite_name and not options.add_satellite:
        log.error('--name only applies with --add-satellite.')
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

    if options.migrate:
        migrate_config = options.config_file if options.config_file else '/home/weewx/weewx.conf'
        if sum([bool(options.output_file), bool(options.in_place), bool(options.print_fields)]) != 1:
            log.error('Specify exactly one of --output FILE, --in-place or --print-fields-value.')
            exit(1)
        if options.print_fields:
            migrate_dict = get_configuration(migrate_config)
            fields = migrate_dict['LoopData']['Include']['fields']
            if isinstance(fields, str):
                fields = [f.strip() for f in fields.split(',') if f.strip()]
            new_fields, report = migrate_loopdata_fields(
                list(fields), _configured_satellites(migrate_dict))
            print(', '.join(new_fields))
        else:
            migrate_output = resolve_output(migrate_config)
            report = migrate_loopdata_conf(migrate_config, migrate_output)
            log.info('Wrote %s' % migrate_output)
        for old_name, new_name in report['renamed']:
            log.info('renamed  %s -> %s' % (old_name, new_name))
        for name in report['dropped']:
            log.info('dropped  %s' % name)
        for name in report['added']:
            log.info('added  %s' % name)
        log.info('%d renamed, %d dropped, %d added.'
                 % (len(report['renamed']), len(report['dropped']), len(report['added'])))
        for note in report['notes']:
            log.info('NOTE: %s' % note)
        exit(0)

    if options.add_satellite or options.remove_satellite:
        sat_config = options.config_file if options.config_file else '/home/weewx/weewx.conf'
        if sum([bool(options.output_file), bool(options.in_place)]) != 1 or options.print_fields:
            log.error('Specify exactly one of --output FILE or --in-place.')
            exit(1)
        config = get_configuration(sat_config)
        try:
            if options.add_satellite:
                sat_tag, sep, sat_norad = options.add_satellite.partition('=')
                sat_tag = sat_tag.strip()
                sat_norad = sat_norad.strip()
                if not sep or not sat_tag or not sat_norad:
                    raise ValueError('--add-satellite takes TAG=NORAD '
                                     '(e.g. --add-satellite zenit23088=23088).')
                report = add_satellite(config, sat_tag, sat_norad,
                                       options.satellite_name)
            else:
                sat_tag = options.remove_satellite.strip()
                report = remove_satellite(config, sat_tag)
        except ValueError as e:
            log.error(str(e))
            exit(1)
        sat_output = resolve_output(sat_config)
        _write_conf_atomically(config, sat_config, sat_output)
        log.info('Wrote %s' % sat_output)
        if options.add_satellite:
            if report['satellites_entry'] == 'added':
                log.info('added  [Skyfield] [[Satellites]] %s = %s' % (sat_tag, sat_norad))
            elif report['satellites_entry'] == 'updated':
                log.info('updated  [Skyfield] [[Satellites]] %s = %s (was %s)'
                         % (sat_tag, sat_norad, report['previous_norad']))
            else:
                log.info('kept  [Skyfield] [[Satellites]] %s = %s (already present)'
                         % (sat_tag, sat_norad))
            for name in report['fields_added']:
                log.info('added  %s' % name)
            if not report['fields_added']:
                log.info('fields line already complete for %s' % sat_tag)
            if report['name_entry'] in ('added', 'updated'):
                log.info('%s  [StdReport] [[Defaults]] [[[Almanac]]] %s = %s'
                         % (report['name_entry'], sat_tag, options.satellite_name))
            elif report['name_entry'] == 'unchanged':
                log.info('kept  [StdReport] [[Defaults]] [[[Almanac]]] %s (already named)'
                         % sat_tag)
        else:
            if report['satellites_entry'] == 'removed':
                log.info('removed  [Skyfield] [[Satellites]] %s = %s' % (sat_tag, report['norad']))
            else:
                log.info('no [Skyfield] [[Satellites]] entry for %s' % sat_tag)
            for name in report['fields_removed']:
                log.info('removed  %s' % name)
            if report['name_entry'] == 'removed':
                log.info('removed  [StdReport] [[Defaults]] [[[Almanac]]] %s' % sat_tag)
        for note in report['hints']:
            log.info('NOTE: %s' % note)
        exit(0)

    parser.print_help()
