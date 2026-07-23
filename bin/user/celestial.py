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
import sys

from typing import Any, Dict, List, Optional, Tuple

import weewx

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '7.0'

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

# 4.0 celestial loop-field names mapped to their weewx-loopdata 5.0 almanac
# equivalents, as (raw-rendition entry, formatted-rendition entry).
_ALMANAC_FIELD_MAP: Dict[str, Tuple[str, str]] = {
    'sunrise'                  : ('almanac.sunrise.raw', 'almanac.sunrise'),
    'sunset'                   : ('almanac.sunset.raw', 'almanac.sunset'),
    'sunTransit'               : ('almanac.sun.transit.raw', 'almanac.sun.transit'),
    'tomorrowSunrise'          : ('almanac(days=1).sunrise.raw', 'almanac(days=1).sunrise'),
    'tomorrowSunset'           : ('almanac(days=1).sunset.raw', 'almanac(days=1).sunset'),
    'daylightDur'              : ('almanac.sun.visible.raw', 'almanac.sun.visible'),
    'yesterdayDaylightDur'     : ('almanac(days=-1).sun.visible.raw', 'almanac(days=-1).sun.visible'),
    'astronomicalTwilightStart': ('almanac(horizon=-18).sun(use_center=1).rise.raw',
                                  'almanac(horizon=-18).sun(use_center=1).rise'),
    'nauticalTwilightStart'    : ('almanac(horizon=-12).sun(use_center=1).rise.raw',
                                  'almanac(horizon=-12).sun(use_center=1).rise'),
    'civilTwilightStart'       : ('almanac(horizon=-6).sun(use_center=1).rise.raw',
                                  'almanac(horizon=-6).sun(use_center=1).rise'),
    'civilTwilightEnd'         : ('almanac(horizon=-6).sun(use_center=1).set.raw',
                                  'almanac(horizon=-6).sun(use_center=1).set'),
    'nauticalTwilightEnd'      : ('almanac(horizon=-12).sun(use_center=1).set.raw',
                                  'almanac(horizon=-12).sun(use_center=1).set'),
    'astronomicalTwilightEnd'  : ('almanac(horizon=-18).sun(use_center=1).set.raw',
                                  'almanac(horizon=-18).sun(use_center=1).set'),
    'moonrise'                 : ('almanac.moon.rise.raw', 'almanac.moon.rise'),
    'moonset'                  : ('almanac.moon.set.raw', 'almanac.moon.set'),
    'moonTransit'              : ('almanac.moon.transit.raw', 'almanac.moon.transit'),
    'nextEquinox'              : ('almanac.next_equinox.raw', 'almanac.next_equinox'),
    'nextSolstice'             : ('almanac.next_solstice.raw', 'almanac.next_solstice'),
    'nextFullMoon'             : ('almanac.next_full_moon.raw', 'almanac.next_full_moon'),
    'nextNewMoon'              : ('almanac.next_new_moon.raw', 'almanac.next_new_moon'),
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
# full/new moon instants (waxing = full before new) for the phase disc.
# current.dateTime.raw is loopdata's own field, the live-age indicator
# and the extrapolation anchor.
_MIGRATION_NEW_FIELDS: List[str] = [
    'current.dateTime.raw',
    'almanac.sun.az', 'almanac.sun.alt', 'almanac.sun.earth_distance',
    'almanac.moon.az', 'almanac.moon.alt', 'almanac.moon.earth_distance',
    'almanac.moon.phase',
    'almanac.next_full_moon.raw', 'almanac.next_new_moon.raw',
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
]


def _migrate_one_field(field: str) -> Tuple[Optional[str], Optional[str]]:
    """One fields-line entry rewritten to its almanac equivalent.  Returns
    (new_entry, note): (field, None) for entries that are not celestial loop
    fields; (None, note) for moonWaxing, which has no almanac equivalent."""
    parts = field.split('.')
    if len(parts) < 2 or parts[0] != 'current':
        return field, None
    name = _MIGRATION_FIELD_MAP.get(parts[1], parts[1])
    if name == 'moonWaxing':
        return None, ('%s dropped: derive waxing in the page instead -- the moon '
                      'is waxing when almanac.next_full_moon.raw < '
                      'almanac.next_new_moon.raw.' % field)
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


def migrate_loopdata_fields(fields: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    """Rewrite a pre-6.0 [LoopData] [[Include]] fields list: rewrite every
    celestial loop-field entry (including pre-3.0 PascalCase names) to its
    weewx-loopdata almanac equivalent in place (preserving the list's
    order), drop moonWaxing (no equivalent; the sample report derives it)
    and the duplicates the rewrites create (keeping the first occurrence),
    and append the fields the current sample report needs.  Entries that are not
    celestial loop fields are never touched.  Returns (new_fields, report)
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
    for field in _MIGRATION_NEW_FIELDS:
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
    return result, {'renamed': renamed, 'dropped': dropped, 'added': added,
                    'notes': notes}


def migrate_loopdata_conf(config_path: str, output_path: str) -> Dict[str, Any]:
    """Rewrite config_path's [LoopData] [[Include]] fields entry
    (see migrate_loopdata_fields) and write the complete configuration to
    output_path atomically (temp file, fsync, rename -- a crash cannot
    leave a truncated file).  config_path itself is only written when
    output_path names the same file.  Returns the migration report."""
    import configobj
    import tempfile
    config = configobj.ConfigObj(config_path, file_error=True, encoding='utf-8')
    try:
        fields = config['LoopData']['Include']['fields']
    except KeyError:
        raise KeyError('%s has no [LoopData] [[Include]] fields entry' % config_path)
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(',') if f.strip()]
    new_fields, report = migrate_loopdata_fields(list(fields))
    config['LoopData']['Include']['fields'] = new_fields
    out_dir = os.path.dirname(os.path.abspath(output_path))
    fd, temp_path = tempfile.mkstemp(prefix='weewx.conf.migrate.', dir=out_dir)
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
       python -m user.celestial --migrate-loopdata-fields [--config=<weewx-config-file>] (--output=FILE | --in-place | --print-fields-value)"""

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', action='store_true',
                      help='Display version')
    parser.add_option('--config', dest='config_file', type=str, metavar="FILE",
                      help='weewx.conf file to migrate.  Default is /home/weewx/weewx.conf')
    parser.add_option('--migrate-loopdata-fields', dest='migrate', action='store_true',
                      help='Rewrite a pre-6.0 [LoopData] [[Include]] fields line: rewrite '
                           'every celestial loop field (including pre-3.0 PascalCase names) '
                           'to its weewx-loopdata almanac equivalent (keeping the line\'s '
                           'order), drop moonWaxing and the duplicates the rewrites create, '
                           'and append the fields the current sample report needs.  '
                           'Non-celestial fields are never touched.  Use with --config and '
                           'exactly one of --output, --in-place or --print-fields-value.')
    parser.add_option('--output', dest='output_file', type=str, metavar='FILE',
                      help='With --migrate-loopdata-fields: write the rewritten configuration '
                           'to FILE, leaving the --config file untouched (diff them, then move '
                           'FILE into place).')
    parser.add_option('--in-place', dest='in_place', action='store_true',
                      help='With --migrate-loopdata-fields: rewrite the --config file itself '
                           '(a .bak-celestial-7.0 backup is made first).')
    parser.add_option('--print-fields-value', dest='print_fields', action='store_true',
                      help='With --migrate-loopdata-fields: print the migrated fields value as '
                           'a bare comma-separated list, ready to paste into weewx.conf (do '
                           'NOT add brackets or quotes).')
    (options, args) = parser.parse_args()

    if options.version:
        log.info("Celestial version is %s." % CELESTIAL_VERSION)
        exit(0)

    if options.migrate:
        import shutil
        migrate_config = options.config_file if options.config_file else '/home/weewx/weewx.conf'
        if sum([bool(options.output_file), bool(options.in_place), bool(options.print_fields)]) != 1:
            log.error('Specify exactly one of --output FILE, --in-place or --print-fields-value.')
            exit(1)
        if options.print_fields:
            migrate_dict = get_configuration(migrate_config)
            fields = migrate_dict['LoopData']['Include']['fields']
            if isinstance(fields, str):
                fields = [f.strip() for f in fields.split(',') if f.strip()]
            new_fields, report = migrate_loopdata_fields(list(fields))
            print(', '.join(new_fields))
        else:
            if options.in_place:
                backup = migrate_config + '.bak-celestial-7.0'
                if os.path.exists(backup):
                    log.error('Backup %s already exists; move it aside first.' % backup)
                    exit(1)
                shutil.copy2(migrate_config, backup)
                log.info('Backed up %s to %s' % (migrate_config, backup))
                migrate_output = migrate_config
            else:
                migrate_output = options.output_file
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

    parser.print_help()
