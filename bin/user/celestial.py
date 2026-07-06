"""
celestial.py

Copyright (C)2022-2025 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Celestial is a WeeWX service that generates Celestial observations
that are inserted into the loop packet.

Report tags (e.g. $almanac.sunrise) are not served by this extension;
install the weewx-skyfield extension for a Skyfield-based report
almanac computed from the same definitions as these loop fields.
"""

import logging
import math
import os
import sys
import time

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy

import skyfield
import skyfield.almanac
import skyfield.api
import skyfield.framelib
import skyfield.timelib
import weeutil.Moon
import weeutil.weeutil
import weewx
import weewx.units

from weeutil.weeutil import to_bool
from weeutil.weeutil import to_int
from weewx.engine import StdEngine
from weewx.engine import StdService

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '4.0'

if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 9):
    raise weewx.UnsupportedFeature(
        "weewx-celestial requires Python 3.9 or later, found %s.%s" % (sys.version_info[0], sys.version_info[1]))

# Compare on the major version number (a plain string comparison would
# misjudge a hypothetical WeeWX 10).  A version string whose first component
# is not a plain integer (e.g., a dev build) is given the benefit of the doubt.
_weewx_major: Optional[int]
try:
    _weewx_major = int(weewx.__version__.split('.')[0])
except ValueError:
    _weewx_major = None
if _weewx_major is not None and _weewx_major < 4:
    raise weewx.UnsupportedFeature(
        "weewx-celestial requires WeeWX 4 or later, found %s" % weewx.__version__)

# The loop fields inserted by this extension (as of 3.0), and the unit group
# of each.
OBS_GROUPS: Dict[str, str] = {
    'earthSunDistance'         : 'group_distance',
    'earthMoonDistance'        : 'group_distance',
    'earthMercuryDistance'     : 'group_distance',
    'earthVenusDistance'       : 'group_distance',
    'earthMarsDistance'        : 'group_distance',
    'earthJupiterDistance'     : 'group_distance',
    'earthSaturnDistance'      : 'group_distance',
    'earthUranusDistance'      : 'group_distance',
    'earthNeptuneDistance'     : 'group_distance',
    'earthPlutoDistance'       : 'group_distance',
    # Light years in every unit system (group_data: no mile/km conversion).
    'earthProximaCentauriDistance': 'group_data',
    'sunAzimuth'               : 'group_direction',
    'sunAltitude'              : 'group_direction',
    'sunRightAscension'        : 'group_direction',
    'sunDeclination'           : 'group_direction',
    'sunrise'                  : 'group_time',
    'sunTransit'               : 'group_time',
    'sunset'                   : 'group_time',
    'daylightDur'              : 'group_deltatime',
    'yesterdayDaylightDur'     : 'group_deltatime',
    'tomorrowSunrise'          : 'group_time',
    'tomorrowSunset'           : 'group_time',
    'astronomicalTwilightStart': 'group_time',
    'nauticalTwilightStart'    : 'group_time',
    'civilTwilightStart'       : 'group_time',
    'civilTwilightEnd'         : 'group_time',
    'nauticalTwilightEnd'      : 'group_time',
    'astronomicalTwilightEnd'  : 'group_time',
    'nextEquinox'              : 'group_time',
    'nextSolstice'             : 'group_time',
    'moonAzimuth'              : 'group_direction',
    'moonAltitude'             : 'group_direction',
    'moonRightAscension'       : 'group_direction',
    'moonDeclination'          : 'group_direction',
    'moonFullness'             : 'group_percent',
    'moonPhase'                : 'group_data',
    # The index into the configured moon_phases list (0=new, 4=full,
    # 7=waning crescent), emitted so clients can name and draw the moon.
    'moonPhaseIndex'           : 'group_data',
    # 1 while the moon is waxing (elongation < 180), else 0.  Exact where
    # the index is not: index 0 spans the last ~1.5 days of waning crescent
    # as well as the first of waxing, which would draw the lit side of the
    # disc mirrored.
    'moonWaxing'               : 'group_data',
    'nextNewMoon'              : 'group_time',
    'nextFullMoon'             : 'group_time',
    'moonrise'                 : 'group_time',
    'moonTransit'              : 'group_time',
    'moonset'                  : 'group_time',
    'mercuryAzimuth'           : 'group_direction',
    'mercuryAltitude'          : 'group_direction',
    'venusAzimuth'             : 'group_direction',
    'venusAltitude'            : 'group_direction',
    'marsAzimuth'              : 'group_direction',
    'marsAltitude'             : 'group_direction',
    'jupiterAzimuth'           : 'group_direction',
    'jupiterAltitude'          : 'group_direction',
    'saturnAzimuth'            : 'group_direction',
    'saturnAltitude'           : 'group_direction',
    'uranusAzimuth'            : 'group_direction',
    'uranusAltitude'           : 'group_direction',
    'neptuneAzimuth'           : 'group_direction',
    'neptuneAltitude'          : 'group_direction',
    'plutoAzimuth'             : 'group_direction',
    'plutoAltitude'            : 'group_direction',
}

# Set up celestial observation types.  (The pre-3.0 PascalCase aliases were
# dual-emitted through 3.x and removed in 4.0, as announced in 3.0.)
for _obs_name, _obs_group in OBS_GROUPS.items():
    weewx.units.obs_group_dict[_obs_name] = _obs_group

class Celestial(StdService):
    def __init__(self, engine: StdEngine, config_dict: Dict[str, Any]):
        super(Celestial, self).__init__(engine, config_dict)
        log.info("Service version : %s" % CELESTIAL_VERSION)

        if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 7):
            raise Exception("Python 3.7 or later is required for the celestial plugin.")

        # Only continue if the plugin is enabled.
        celestial_config_dict = config_dict.get('Celestial', {})
        enable = to_bool(celestial_config_dict.get('enable'))
        if enable:
            log.info("Celestial status: enabled...continuing.")
        else:
            log.info("Celestial status: disabled...enable it in the Celestial section of weewx.conf.")
            return

        update_rate_secs = to_int(celestial_config_dict.get('update_rate_secs', 0))
        stars = to_bool(celestial_config_dict.get('stars', True))

        user_root, moon_phases, altitude_m, latitude, longitude = Sky.get_weewx_config_info(config_dict)
        if latitude is None or longitude is None:
            log.error("Could not determine station's latitude and longitude.")
            return
        if altitude_m is None:
            log.error("Could not determine station's altitude.")
            return

        log.info("update_rate_secs       : %d" % update_rate_secs)
        log.info("stars                  : %r" % stars)
        log.info("user_root              : %s" % user_root)
        log.info("moon_phases            : %r" % moon_phases)
        log.info("altitude_m             : %f" % altitude_m)
        log.info("latitude               : %f" % latitude)
        log.info("longitude              : %f" % longitude)

        self.sky = Sky(update_rate_secs, user_root, moon_phases, altitude_m, latitude, longitude, load_stars=stars)
        if self.sky.is_valid():
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop)

    def new_loop(self, event):
        try:
            pkt: Dict[str, Any] = event.packet
            assert event.event_type == weewx.NEW_LOOP_PACKET
            log.debug(pkt)
            self.sky.insert_fields(pkt)
        except Exception as e:
            log.error('new_loop: %s.' % e)

# The stars used by the loop-field path, mapped to their Hipparcos catalog
# numbers.  Only Proxima Centauri is needed (for the
# earthProximaCentauriDistance loop field); the stars are read from
# celestial_stars.dat, an excerpt of the Hipparcos Catalogue (ESA SP-1200,
# 1997) that ships with this extension.  Report tags for named stars
# ($almanac.rigel.rise) are served by the weewx-skyfield extension.
LOOP_STARS: Dict[str, int] = {
    'proxima_centauri' : 70890,
}

# An excerpt of the Hipparcos Catalogue covering the IAU named stars
# (a superset of LOOP_STARS).  It is installed alongside celestial.py (like
# the de421.bsp ephemeris), and its data lines are unmodified hip_main.dat
# records, so a full hip_main.dat works in its place.
STAR_FILE = 'celestial_stars.dat'
# The Hipparcos catalog's positions are for epoch J1991.25.  This is that
# epoch as a TT Julian date, matching skyfield.data.hipparcos.load_dataframe.
HIPPARCOS_EPOCH_JD = 1721045.0 + 1991.25 * 365.25

# Astronomical units per light year (IAU 2015 definitions).
AU_PER_LIGHT_YEAR = 63241.077

# Miles and kilometers per astronomical unit (IAU 2012: 1 au = 149,597,870.7 km).
# The sample skin's index.html.tmpl hardcodes the same values (a template
# cannot import this module); a test ties the two together.
AU_MILES = 9.2955807e+7
AU_KM    = 1.4959787e+8

# Body name -> key in the DE421 ephemeris, for every body served by the loop
# fields (earth, the observer, is loaded separately).
EPHEMERIS_KEYS: Dict[str, str] = {
    'sun'    : 'sun',
    'moon'   : 'moon',
    'mercury': 'mercury',
    'venus'  : 'venus',
    'mars'   : 'mars',
    'jupiter': 'jupiter barycenter',
    'saturn' : 'saturn barycenter',
    'uranus' : 'uranus barycenter',
    'neptune': 'neptune barycenter',
    'pluto'  : 'pluto barycenter',
}

# The planets whose azimuth/altitude are emitted as loop fields
# (<name>Azimuth / <name>Altitude); sun and moon are handled individually.
LOOP_PLANETS: List[str] = ['mercury', 'venus', 'mars', 'jupiter',
                           'saturn', 'uranus', 'neptune', 'pluto']

# Pre-3.0 loop field names mapped to their replacements.  This map exists
# SOLELY for the --migrate-loopdata-fields command-line utility, which
# rewrites [LoopData] [[Include]] fields lines for users upgrading from 2.x
# or 3.x.  The old names were removed from the loop packet in 4.0 and this
# map must never grow another consumer (TestDeprecatedFieldsRemoved keeps
# the packet honest).
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

# The loop-data renditions the 4.0 sample report reads that pre-4.0 fields
# lines will not have; the migrator appends the missing ones.
_MIGRATION_NEW_FIELDS: List[str] = [
    'current.dateTime.raw',
    'current.earthProximaCentauriDistance.raw',
    'current.jupiterAltitude.raw', 'current.jupiterAzimuth.raw',
    'current.marsAltitude.raw', 'current.marsAzimuth.raw',
    'current.mercuryAltitude.raw', 'current.mercuryAzimuth.raw',
    'current.moonFullness.raw', 'current.moonPhaseIndex.raw',
    'current.moonTransit.raw', 'current.moonWaxing.raw',
    'current.neptuneAltitude.raw', 'current.neptuneAzimuth.raw',
    'current.nextEquinox.raw', 'current.nextFullMoon.raw',
    'current.nextNewMoon.raw', 'current.nextSolstice.raw',
    'current.plutoAltitude.raw', 'current.plutoAzimuth.raw',
    'current.saturnAltitude.raw', 'current.saturnAzimuth.raw',
    'current.uranusAltitude.raw', 'current.uranusAzimuth.raw',
    'current.venusAltitude.raw', 'current.venusAzimuth.raw',
]


def migrate_loopdata_fields(fields: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    """Rewrite a [LoopData] [[Include]] fields list for 4.0: rename
    deprecated pre-3.0 celestial obstypes in place (preserving each entry's
    rendition suffix and the list's order), drop the duplicates those
    renames create (keeping the first occurrence), and append the 4.0
    sample-report fields that are missing.  Entries that are not deprecated
    celestial names are never touched.  Returns (new_fields, report) where
    report maps 'renamed' to (old, new) pairs and 'dropped'/'added' to
    field names."""
    result: List[str] = []
    seen: set = set()
    renamed: List[Tuple[str, str]] = []
    dropped: List[str] = []
    added: List[str] = []
    for field in fields:
        parts = field.split('.')
        if len(parts) >= 2 and parts[0] == 'current' and parts[1] in _MIGRATION_FIELD_MAP:
            new_field = '.'.join([parts[0], _MIGRATION_FIELD_MAP[parts[1]]] + parts[2:])
            renamed.append((field, new_field))
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
    return result, {'renamed': renamed, 'dropped': dropped, 'added': added}


def migrate_loopdata_conf(config_path: str, output_path: str) -> Dict[str, Any]:
    """Rewrite config_path's [LoopData] [[Include]] fields entry for 4.0
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

def find_discrete_events(f, t0, t1, code_sets: Tuple[Tuple[int, ...], ...],
                         previous: bool = False) -> List[Optional[float]]:
    """One skyfield find_discrete scan over [t0, t1]; for each set of event
    codes, the timestamp of the first (or last, if previous) matching event,
    or None."""
    times, events = skyfield.almanac.find_discrete(t0, t1, f)
    results: List[Optional[float]] = []
    for codes in code_sets:
        stamps = [t.utc_datetime().timestamp() for t, event in zip(times, events) if event in codes]
        results.append((stamps[-1] if previous else stamps[0]) if stamps else None)
    return results


def daylight_seconds(rise: Optional[float], set_: Optional[float],
                     sod_ts: float, eod_ts: float,
                     up_all_day: Callable[[], bool]) -> float:
    """How long a body is above the horizon on the day [sod_ts, eod_ts),
    given its first rise/set of that day.  Handles the polar cases.
    up_all_day is only consulted when the body never crossed the horizon."""
    if rise is not None and set_ is not None:
        if set_ >= rise:
            return set_ - rise
        # The body was up at the start of the day: it set first, then rose
        # again (e.g., the sun in polar regions, or the moon).
        return (set_ - sod_ts) + (eod_ts - rise)
    if rise is not None:
        # The body rose, but never set.
        return eod_ts - rise
    if set_ is not None:
        # The body set, but never rose.
        return set_ - sod_ts
    # The body neither rose nor set.  Since it never crossed the horizon, it
    # was either up all day or down all day.
    return 86400 if up_all_day() else 0


# Mean apparent semidiameters for rise/set purposes -- sun and moon only (a
# planet's sub-arcsecond radius does not meaningfully move its rise time).
# Membership decides which bodies get a radius; the actual value is computed
# for the date from BODY_RADIUS_KM (see Sky.rise_set_radius_degrees).
BODY_RADIUS_DEGREES: Dict[str, float] = {'sun': 16.0 / 60.0, 'moon': 15.5 / 60.0}

# Skyfield's standard refraction angle at the horizon.
STANDARD_REFRACTION_DEGREES = -34.0 / 60.0

# Equatorial radii in kilometers, used to compute the date's apparent angular
# radius when searching for rise and set.
BODY_RADIUS_KM: Dict[str, float] = {
    'sun'    : 695700.0,
    'moon'   : 1738.1,
    'mercury': 2440.5,
    'venus'  : 6051.8,
    'mars'   : 3396.2,
    'jupiter': 71492.0,
    'saturn' : 60268.0,
    'uranus' : 25559.0,
    'neptune': 24764.0,
    'pluto'  : 1188.3,
}


class Sky():
    def __init__(self, update_rate_secs, user_root: str, moon_phases: List[str], altitude_m: float, latitude: float, longitude: float, load_stars: bool = False):
        log.info("Skyfield version: %d.%d." % (skyfield.VERSION[0], skyfield.VERSION[1]))

        self.valid           : bool           = False
        self.update_rate_secs: int            = update_rate_secs
        self.user_root       : str            = user_root
        self.moon_phases     : List[str]      = moon_phases
        self.altitude_m      : float          = altitude_m
        self.latitude        : float          = latitude
        self.longitude       : float          = longitude
        # Caches, one per field class (see insert_fields): continuous
        # fields (throttled by update_rate_secs), day-scoped fields (valid
        # for one local day) and next-event fields (valid until an event
        # passes).
        self.prev_reading    : Dict[str, Any] = { 'dateTime': 0 } # Set to epoch so it will be too old to use
        self.day_cache       : Dict[str, Any] = {}
        self.day_cache_day   : Optional[float] = None
        self.event_cache     : Dict[str, float] = {}
        self.event_cache_day : Optional[float] = None

        # find_risings/find_settings arrived in Skyfield 1.47; on anything
        # older every rise/set computation would fail, so decline up front
        # (e.g., Debian 12 packages Skyfield 1.45).
        if tuple(skyfield.VERSION[:2]) < (1, 47):
            log.error('init: weewx-celestial requires Skyfield 1.47 or later, found %d.%d.'
                      '  Celestial will not run.'
                      % (skyfield.VERSION[0], skyfield.VERSION[1]))
            return

        # The timescale is built once and reused; building it parses
        # skyfield's leap second and delta-T tables.
        try:
            self.ts: skyfield.timelib.Timescale = skyfield.api.load.timescale()
        except Exception as e:
            log.error('init: Could not build the skyfield timescale: %s.  Celestial will not run.' % e)
            return

        # Load the JPL ephemeris DE421 (covers 1900-2050).  The file is
        # prefixed 'celestial_' so that no other extension can claim (and,
        # on its uninstall, remove) it; skyfield itself does not care about
        # the name.
        try:
            planets_file: str = '%s/celestial_de421.bsp' % user_root
            self.planets: skyfield.jpllib.SpiceKernel = skyfield.api.load_file(planets_file)
        except Exception as e:
            log.error('init: Could not load %s: %s.  Celestial will not run.' % (planets_file, e))
            return

        # Look up the bodies in the ephemeris.  EPHEMERIS_KEYS is the single
        # source of truth for which bodies are served and their DE421 keys;
        # earth (the observer) is not a target body and stays out of self.orbs.
        try:
            orb: str = 'earth'
            self.earth: skyfield.vectorlib.VectorSum = self.planets['earth']
            self.orbs: Dict[str, Any] = {}
            for orb, key in EPHEMERIS_KEYS.items():
                self.orbs[orb] = self.planets[key]
        except Exception as e:
            log.error('init: Could not find %s in ephermis file %s: %s.  Celestial will not run.' % (orb, planets_file, e))
            return

        # The same bodies as attributes, used by the loop packet code.
        self.sun    : skyfield.vectorlib.VectorSum = self.orbs['sun']
        self.moon   : skyfield.vectorlib.VectorSum = self.orbs['moon']
        self.mercury: skyfield.vectorlib.VectorSum = self.orbs['mercury']
        self.venus  : skyfield.vectorlib.VectorSum = self.orbs['venus']
        self.mars   : skyfield.vectorlib.VectorSum = self.orbs['mars']
        self.jupiter: skyfield.vectorlib.VectorSum = self.orbs['jupiter']
        self.saturn : skyfield.vectorlib.VectorSum = self.orbs['saturn']
        self.uranus : skyfield.vectorlib.VectorSum = self.orbs['uranus']
        self.neptune: skyfield.vectorlib.VectorSum = self.orbs['neptune']
        self.pluto  : skyfield.vectorlib.VectorSum = self.orbs['pluto']

        # A map of star name to (skyfield.api.Star, magnitude), populated from
        # the Hipparcos catalog when stars are enabled.
        self.stars: Dict[str, Tuple[Any, Optional[float]]] = {}
        self.load_stars: bool = load_stars
        self.proxima_light_years: Optional[float] = None
        if load_stars:
            try:
                self.stars = Sky.load_named_stars(user_root)
                log.info('Loaded %d named stars from the Hipparcos catalog.' % len(self.stars))
            except Exception as e:
                log.error('init: Could not load the Hipparcos star catalog: %s.  Star support disabled.' % e)
                self.load_stars = False

        try:
            self.bluffton = skyfield.api.wgs84.latlon(self.latitude, self.longitude, elevation_m=self.altitude_m)
        except Exception as e:
            log.error('init: skyfield.api.wgs84.latlon(%f, %f, %f): %s.  Celestial will not run.' % (self.latitude, self.longitude, self.altitude_m, e))
            return
        try:
            self.observer = self.earth + self.bluffton
        except Exception as e:
            log.error('init: Could not set observer (earth: %r, bluffton: %r): %s.  Celestial will not run.' % (self.earth, self.bluffton, e))
            return

        self.valid = True

    @staticmethod
    def load_named_stars(user_root: str) -> Dict[str, Tuple[Any, Optional[float]]]:
        """Load the stars in LOOP_STARS from the Hipparcos catalog."""
        by_hip = Sky.load_stars_by_hip(user_root, set(LOOP_STARS.values()))
        return {name: by_hip[hip] for name, hip in LOOP_STARS.items() if hip in by_hip}

    @staticmethod
    def load_stars_by_hip(user_root: str, wanted_hips: set) -> Dict[int, Tuple[Any, Optional[float]]]:
        """Load the requested Hipparcos numbers from the star catalog.  The
        bundled excerpt covers the stars in LOOP_STARS (with records
        identical to the full catalog's), so it is read even when a full
        hip_main.dat is installed; a user-installed hip_main.dat stands in
        when the excerpt is missing."""
        path = '%s/%s' % (user_root, STAR_FILE)
        if not os.path.exists(path):
            path = '%s/%s' % (user_root, 'hip_main.dat')

        def parse_float(field: str) -> float:
            field = field.strip()
            return float(field) if field else 0.0

        by_hip: Dict[int, Tuple[Any, Optional[float]]] = {}
        with open(path) as f:
            for line in f:
                fields = line.split('|')
                try:
                    hip = int(fields[1])
                except (ValueError, IndexError):
                    continue
                if hip not in wanted_hips:
                    continue
                # A malformed record disables only this star, not the catalog.
                try:
                    if fields[8].strip() and fields[9].strip():
                        ra_degrees = float(fields[8])
                        dec_degrees = float(fields[9])
                    else:
                        # A few Hipparcos entries (e.g., HIP 55203, Alula
                        # Australis, a close binary) have no astrometric
                        # solution; fall back to the identification columns
                        # (right ascension h m s, declination sign-d m s).
                        h, m, s = fields[3].split()
                        ra_degrees = (int(h) + int(m) / 60.0 + float(s) / 3600.0) * 15.0
                        d, dm, ds = fields[4].split()
                        sign = -1.0 if d.startswith('-') else 1.0
                        dec_degrees = sign * (abs(int(d)) + int(dm) / 60.0 + float(ds) / 3600.0)
                    star = skyfield.api.Star(
                        ra_hours=ra_degrees / 15.0,
                        dec_degrees=dec_degrees,
                        ra_mas_per_year=parse_float(fields[12]),
                        dec_mas_per_year=parse_float(fields[13]),
                        parallax_mas=parse_float(fields[11]),
                        epoch=HIPPARCOS_EPOCH_JD)
                    magnitude = float(fields[5]) if fields[5].strip() else None
                except (ValueError, IndexError):
                    continue
                by_hip[hip] = (star, magnitude)
                if len(by_hip) == len(wanted_hips):
                    break
        return by_hip

    @staticmethod
    def get_weewx_config_info(config_dict: Dict[str, Any]) -> Tuple[str, List[str], Optional[float], Optional[float], Optional[float]]:
        # Compose USER_ROOT directory (it's where Skyfield's planets file was installed.
        weewx_root: str = config_dict.get('WEEWX_ROOT', '')
        user_root : str = config_dict.get('USER_ROOT', 'bin/user')
        if not user_root.startswith('/'):
            user_root = "%s/%s" % (weewx_root, user_root)

        moon_phases = Sky.get_moon_phases(config_dict)

        stn_info = weewx.station.StationInfo(None, **config_dict['Station'])

        altitude_m = None
        latitude   = None
        longitude  = None

        # observer usually needs latitude and longitude
        altitude_vt = stn_info.altitude_vt
        altitude_vt = weewx.units.StdUnitConverters[weewx.METRIC].convert(altitude_vt)
        altitude_m = altitude_vt[0]
        latitude = stn_info.latitude_f
        longitude = stn_info.longitude_f
        if latitude is None or longitude is None:
            log.error("Could not determine station's latitude and longitude.")
        if altitude_m is None:
            log.error("Could not determine station's altitude.")
        return user_root, moon_phases, altitude_m, latitude, longitude

    @staticmethod
    def get_moon_phases(config_dict: Dict[str, Any]) -> List[str]:
        moon_phases: List[str] = weeutil.Moon.moon_phases
        if 'StdReport' in config_dict:
            if 'Defaults' in config_dict['StdReport']:
                if 'Almanac' in config_dict['StdReport']['Defaults']:
                    if 'moon_phases' in config_dict['StdReport']['Defaults']['Almanac']:
                        moon_phases = config_dict['StdReport']['Defaults']['Almanac']['moon_phases']
        return moon_phases

    def is_valid(self) -> bool:
        return self.valid

    def distance_au(self, t: skyfield.timelib.Time, orb: skyfield.vectorlib.VectorSum,
                    origin: Optional[skyfield.vectorlib.VectorSum] = None) -> float:
        """Distance from origin (default: earth) to orb, in astronomical units."""
        position = (origin if origin is not None else self.earth).at(t).observe(orb)
        _, _, distance = position.radec()
        return distance.au

    def get_moon_phase(self, ts: skyfield.timelib.Timescale, pkt_datetime: datetime) -> Tuple[float, float]:
        t: skyfield.timelib.Time = ts.from_datetime(pkt_datetime)

        e = self.earth.at(t)
        s = e.observe(self.sun).apparent()
        m = e.observe(self.moon).apparent()

        _, slon, _ = s.frame_latlon(skyfield.framelib.ecliptic_frame)
        _, mlon, _ = m.frame_latlon(skyfield.framelib.ecliptic_frame)
        phase = (mlon.degrees - slon.degrees) % 360.0

        percent = 100.0 * m.fraction_illuminated(self.sun)

        return phase, percent

    def get_moon_phase_index(self, degrees: float) -> int:
        index: int = int(round((degrees / 360) * 8))
        if index == 8:
            index = 0
        return index

    def get_next_fullmoon_and_newmoon(self, ts: skyfield.timelib.Timescale, day_start: datetime) -> Tuple[Optional[float], Optional[float]]:
        # moon_phases events: 0=new moon, 2=full moon.
        fullmoon, newmoon = find_discrete_events(
            skyfield.almanac.moon_phases(self.planets),
            ts.from_datetime(day_start),
            ts.from_datetime(day_start + timedelta(days=60)),
            ((2,), (0,)))
        return fullmoon, newmoon

    def get_next_equinox_and_solstice(self, ts: skyfield.timelib.Timescale, day_start: datetime) -> Tuple[Optional[float], Optional[float]]:
        # seasons events: 0/2 are the equinoxes, 1/3 the solstices.
        equinox, solstice = find_discrete_events(
            skyfield.almanac.seasons(self.planets),
            ts.from_datetime(day_start),
            ts.from_datetime(day_start + timedelta(days=366)),
            ((0, 2), (1, 3)))
        return equinox, solstice

    def get_az_alt_ra_dec(self, ts: skyfield.timelib.Timescale, orb, pkt_datetime: datetime, tempC: Optional[float], pressureMbar: Optional[float]) -> Tuple[float, float, float, float]:

        astronomic = self.observer.at(ts.from_datetime(pkt_datetime)).observe(orb)
        apparent = astronomic.apparent()

        # Altitude and azimuth in the sky of a specific geographic location.
        # Compare against None: 0.0 degC is a perfectly good temperature.
        if tempC is not None and pressureMbar is not None:
            alt, az, _ = apparent.altaz(temperature_C=tempC, pressure_mbar=pressureMbar)
        elif tempC is not None:
            alt, az, _ = apparent.altaz(temperature_C=tempC)
        elif pressureMbar is not None:
            alt, az, _ = apparent.altaz(pressure_mbar=pressureMbar)
        else:
            alt, az, _ = apparent.altaz()
        # Right ascension/declination in coordinates of date (the same
        # convention as weewx-skyfield's ra/dec report tags and PyEphem).
        ra, dec, _ = apparent.radec('date')

        return az.degrees, alt.degrees, ra._degrees, dec.degrees

    def rise_set_radius_degrees(self, t: skyfield.timelib.Time, body_name: str, orb,
                                observer=None) -> float:
        """The body's apparent angular radius for rise/set purposes,
        computed for the date -- sun and moon only (a planet's
        sub-arcsecond radius does not meaningfully move its rise time).
        The same definition weewx-skyfield uses, so the loop fields and
        its report tags agree."""
        if body_name not in BODY_RADIUS_DEGREES:
            return 0.0
        if observer is None:
            observer = self.observer
        distance_km = observer.at(t).observe(orb).apparent().distance().km
        return math.degrees(math.asin(BODY_RADIUS_KM[body_name] / distance_km))

    def rise_set_horizon_degrees(self, t: skyfield.timelib.Time, body_name: str, orb) -> float:
        """The effective rise/set horizon at standard atmospheric
        conditions: standard refraction plus the date's apparent radius."""
        return STANDARD_REFRACTION_DEGREES - self.rise_set_radius_degrees(t, body_name, orb)

    def get_rise_set_transit(self, ts: skyfield.timelib.Timescale, body_name: str, orb: skyfield.vectorlib.VectorSum, day_start: datetime) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        rise: Optional[float] = None
        set_ts: Optional[float] = None
        transit: Optional[float] = None

        ts_day_start = ts.from_datetime(day_start)
        ts_day_end = ts.from_datetime(day_start + timedelta(days=2))  # Assume we'll see a rise and set in the next 2 days

        # rise/set
        horizon = self.rise_set_horizon_degrees(ts_day_start, body_name, orb)
        rise_times, rise_crosses_horizons = skyfield.almanac.find_risings(self.observer, orb, ts_day_start, ts_day_end, horizon_degrees=horizon)
        set_times, set_crosses_horizons = skyfield.almanac.find_settings(self.observer, orb, ts_day_start, ts_day_end, horizon_degrees=horizon)
        if  len(rise_crosses_horizons) > 0 and rise_crosses_horizons[0]:
            rise = rise_times[0].utc_datetime().timestamp()
        if  len(set_crosses_horizons) > 0 and set_crosses_horizons[0]:
            set_ts = set_times[0].utc_datetime().timestamp()

        #transit
        transit_times = skyfield.almanac.find_transits(self.observer, orb, ts_day_start, ts_day_end)
        if len(transit_times) > 0:
            transit = transit_times[0].utc_datetime().timestamp()

        return rise, set_ts, transit

    def get_sunrise_sunset_transit_daylight(self, ts: skyfield.timelib.Timescale, day_start: datetime) -> Tuple[Optional[float], Optional[float], Optional[float], float]:
        sunrise: Optional[float] = None
        sunset: Optional[float] = None
        transit: Optional[float] = None

        ts_day_start = ts.from_datetime(day_start)
        day_end = day_start + timedelta(days=1)
        ts_day_end = ts.from_datetime(day_end)

        # Sunrise/Sunset/SunTransit/daySunshineDur
        horizon = self.rise_set_horizon_degrees(ts_day_start, 'sun', self.sun)
        sunrise_times, sunrise_crosses_horizons = skyfield.almanac.find_risings(self.observer, self.sun, ts_day_start, ts_day_end, horizon_degrees=horizon)
        sunset_times, sunset_crosses_horizons = skyfield.almanac.find_settings(self.observer, self.sun, ts_day_start, ts_day_end, horizon_degrees=horizon)
        if  len(sunrise_crosses_horizons) > 0 and sunrise_crosses_horizons[0]:
            sunrise = sunrise_times[0].utc_datetime().timestamp()
        if  len(sunset_crosses_horizons) > 0 and sunset_crosses_horizons[0]:
            sunset = sunset_times[0].utc_datetime().timestamp()

        def sun_up_all_day() -> bool:
            alt, _, _ = self.observer.at(ts_day_start).observe(self.sun).apparent().altaz()
            return alt.degrees > horizon

        daylight = daylight_seconds(sunrise, sunset, day_start.timestamp(),
                                    day_end.timestamp(), sun_up_all_day)

        transit_times = skyfield.almanac.find_transits(self.observer, self.sun, ts_day_start, ts_day_end)
        if len(transit_times) > 0:
            transit = transit_times[0].utc_datetime().timestamp()

        return sunrise, sunset, transit, daylight

    def get_continuous_fields(self, pkt: Dict[str, Any], ts_pkt_time: skyfield.timelib.Time,
                              pkt_datetime: datetime) -> Dict[str, Any]:
        """The fields that vary continuously: positions, distances and the
        moon's phase.  Cheap (roughly 20 ms on a Raspberry Pi 5); recomputed
        every packet unless throttled by update_rate_secs."""
        fields: Dict[str, Any] = {}
        ts = self.ts

        if not 'outTemp' in pkt:
            log.debug("Missing 'outTemp' in loop packet won't be used in calculations.")

        if not 'barometer' in pkt:
            log.debug("Missing 'barometer' in loop packet won't be used in calculations")

        metric_pkt = weewx.units.StdUnitConverters[weewx.METRIC].convertDict(pkt)
        tempC: Optional[float] = None
        pressureMbar: Optional[float] = None
        if 'outTemp' in metric_pkt:
            tempC = metric_pkt['outTemp']
        if 'barometer' in metric_pkt:
            pressureMbar = metric_pkt['barometer']

        try:
            sun_az, sun_alt, sun_ra, sun_dec= self.get_az_alt_ra_dec(ts, self.sun, pkt_datetime, tempC, pressureMbar)
            fields['sunAzimuth'] = sun_az
            fields['sunAltitude'] = sun_alt
            fields['sunRightAscension'] = sun_ra
            fields['sunDeclination'] = sun_dec
        except Exception as e:
            log.error('get_continuous_fields: get_az_alt_ra_dec(%r, %r, %r, %r, %r): %s.' % (ts, self.sun, pkt_datetime, tempC, pressureMbar, e))

        try:
            moon_az, moon_alt, moon_ra, moon_dec= self.get_az_alt_ra_dec(ts, self.moon, pkt_datetime, tempC, pressureMbar)
            fields['moonAzimuth'] = moon_az
            fields['moonAltitude'] = moon_alt
            fields['moonRightAscension'] = moon_ra
            fields['moonDeclination'] = moon_dec
        except Exception as e:
            log.error('get_continuous_fields: get_az_alt_ra_dec(moon): %s.' % e)

        try:
            moon_phase_degrees, percent_illumination = self.get_moon_phase(ts, pkt_datetime)
            fields['moonFullness'] = percent_illumination
            index = self.get_moon_phase_index(moon_phase_degrees)
            fields['moonPhase'] = self.moon_phases[index]
            fields['moonPhaseIndex'] = index
            fields['moonWaxing'] = 1 if moon_phase_degrees < 180.0 else 0
        except Exception as e:
            log.error('get_continuous_fields: get_moon_phase: %s.' % e)

        for planet in LOOP_PLANETS:
            try:
                az, alt, _, _ = self.get_az_alt_ra_dec(ts, self.orbs[planet], pkt_datetime, tempC, pressureMbar)
                fields[planet + 'Azimuth'] = az
                fields[planet + 'Altitude'] = alt
            except Exception as e:
                log.error('get_continuous_fields: get_az_alt_ra_dec(%s): %s.' % (planet, e))

        # Convert astronomical units to miles (US) or kilometers (METRIC and METRICWX).
        if pkt['usUnits'] == weewx.US:
            multiplier = AU_MILES
        else:
            multiplier = AU_KM

        try:
            orb: str = 'sun'
            fields['earthSunDistance'] = self.distance_au(ts_pkt_time, self.sun) * multiplier
            orb = 'moon'
            fields['earthMoonDistance'] = self.distance_au(ts_pkt_time, self.moon) * multiplier

            orb = 'mercury'
            fields['earthMercuryDistance'] = self.distance_au(ts_pkt_time, self.mercury) * multiplier
            orb = 'venus'
            fields['earthVenusDistance'] = self.distance_au(ts_pkt_time, self.venus) * multiplier
            orb = 'mars'
            fields['earthMarsDistance'] = self.distance_au(ts_pkt_time, self.mars) * multiplier
            orb = 'jupiter'
            fields['earthJupiterDistance'] = self.distance_au(ts_pkt_time, self.jupiter) * multiplier
            orb = 'saturn'
            fields['earthSaturnDistance'] = self.distance_au(ts_pkt_time, self.saturn) * multiplier
            orb = 'uranus'
            fields['earthUranusDistance'] = self.distance_au(ts_pkt_time, self.uranus) * multiplier
            orb = 'neptune'
            fields['earthNeptuneDistance'] = self.distance_au(ts_pkt_time, self.neptune) * multiplier
            orb = 'pluto'
            fields['earthPlutoDistance'] = self.distance_au(ts_pkt_time, self.pluto) * multiplier
        except Exception as e:
            log.error('get_continuous_fields: distance_au(%r, %s): %s.' % (ts_pkt_time, orb, e))

        # Distance to Proxima Centauri, the nearest star (needs the star
        # catalog).  Reported in light years in every unit system: miles/km
        # are unreadable at this scale, and at honest precision (the
        # Hipparcos parallax is good to ~0.3%) the value is constant -- so
        # it is computed once, not on the loop hot path.
        if 'proxima_centauri' in self.stars:
            if self.proxima_light_years is None:
                try:
                    self.proxima_light_years = (
                        self.distance_au(ts_pkt_time, self.stars['proxima_centauri'][0]) / AU_PER_LIGHT_YEAR)
                except Exception as e:
                    log.error('get_continuous_fields: distance_au(%r, proxima_centauri): %s.' % (ts_pkt_time, e))
            if self.proxima_light_years is not None:
                fields['earthProximaCentauriDistance'] = self.proxima_light_years

        return fields

    def get_day_fields(self, day_start: datetime) -> Tuple[Dict[str, Any], bool]:
        """The fields that are constant for a local day: rise/set/transit
        times, twilights and daylight durations.  The expensive searches
        (roughly 150 ms on a Raspberry Pi 5) run only when the packet's
        local day changes.  Returns (fields, ok): ok is False when any
        section raised, so the caller can retry on the next packet instead
        of serving a poisoned cache for the rest of the day (a field that
        is legitimately absent -- e.g., no moonrise today -- is not a
        failure)."""
        fields: Dict[str, Any] = {}
        ok = True
        ts = self.ts

        try:
            sunrise, sunset, transit, daylight = self.get_sunrise_sunset_transit_daylight(ts, day_start)
            if sunrise is not None:
                fields['sunrise'] = sunrise
            if  sunset is not None:
                fields['sunset'] = sunset
            fields['daylightDur'] = daylight
            fields['sunTransit'] = transit
        except Exception as e:
            log.error('get_day_fields: get_sunrise_sunset_transit_daylight(%r): %s.' % (day_start, e))
            ok = False

        # Moonrise/Moonset/MoonTransit
        try:
            moonrise, moonset, moontransit = self.get_rise_set_transit(ts, 'moon', self.moon, day_start)
            if moonrise is not None:
                fields['moonrise'] = moonrise
            if moonset is not None:
                fields['moonset'] = moonset
            fields['moonTransit'] = moontransit
        except Exception as e:
            log.error('get_day_fields: get_rise_set_transit(moon, %r): %s.' % (day_start, e))
            ok = False

        try:
            f = skyfield.almanac.dark_twilight_day(self.planets, self.bluffton)
            times, events = skyfield.almanac.find_discrete(ts.from_datetime(day_start), ts.from_datetime(day_start + timedelta(days=1)), f)
            astronomical_encountered = False
            nautical_encountered = False
            civil_encountered = False
            for event, t in zip(events, times):
                match event:
                    case 0:
                        fields['astronomicalTwilightEnd'] = t.utc_datetime().timestamp()
                    case 1:
                        if not astronomical_encountered:
                            fields['astronomicalTwilightStart'] = t.utc_datetime().timestamp()
                            astronomical_encountered = True
                        else:
                            fields['nauticalTwilightEnd'] = t.utc_datetime().timestamp()
                    case 2:
                        if not nautical_encountered:
                            fields['nauticalTwilightStart'] = t.utc_datetime().timestamp()
                            nautical_encountered = True
                        else:
                            fields['civilTwilightEnd'] = t.utc_datetime().timestamp()
                    case 3:
                        if not civil_encountered:
                            fields['civilTwilightStart'] = t.utc_datetime().timestamp()
                            civil_encountered = True
        except Exception as e:
            log.error('get_day_fields: skyfield.almanac.find_discrete twilight(%r, %r): %s.' % (day_start, f, e))
            ok = False

        try:
            # We need yesterday's daylight duration
            yesterday_start = day_start - timedelta(days=1)
            _, _, _, yesterday_daylight = self.get_sunrise_sunset_transit_daylight(ts, yesterday_start)
            fields['yesterdayDaylightDur'] = yesterday_daylight
        except Exception as e:
            log.error('get_day_fields: get_sunrise_sunset_transit_daylight(yesterday_start: %r): %s.' % (yesterday_start, e))
            ok = False

        try:
            # Tomorrow sunrise, sunset
            tomorrow_start = day_start + timedelta(days=1)
            tomorrow_sunrise, tomorrow_sunset, _, _ = self.get_sunrise_sunset_transit_daylight(ts, tomorrow_start)
            if tomorrow_sunrise is not None:
                fields['tomorrowSunrise'] = tomorrow_sunrise
            if  tomorrow_sunset is not None:
                fields['tomorrowSunset'] = tomorrow_sunset
        except Exception as e:
            log.error('get_day_fields: get_sunrise_sunset_transit_daylight(tomorrow_start: %r): %s.' % (tomorrow_start, e))
            ok = False

        return fields, ok

    def get_event_fields(self, day_start: datetime) -> Tuple[Dict[str, float], bool]:
        """The next-event fields: equinox/solstice and full/new moon.  The
        searches sweep months of ephemeris (roughly 110 ms on a Raspberry
        Pi 5) for values that change a handful of times a year, so they run
        only when the local day advances past a cached event.  Each event is
        computed from the start of the day, so it is deliberately kept for
        the rest of its day after it occurs.  Returns (fields, ok); ok is
        False when a search raised, so the caller retries next packet."""
        fields: Dict[str, float] = {}
        ok = True
        ts = self.ts

        try:
            next_equinox, next_solstice = self.get_next_equinox_and_solstice(ts, day_start)
            if next_equinox is not None:
                fields['nextEquinox']  = next_equinox
            if next_solstice is not None:
                fields['nextSolstice'] = next_solstice
        except Exception as e:
            log.error('get_event_fields: get_next_equinox_and_solstice(%r): %s.' % (day_start, e))
            ok = False

        try:
            fullmoon, newmoon = self.get_next_fullmoon_and_newmoon(ts, day_start)
            if fullmoon is not None:
                fields['nextFullMoon']  = fullmoon
            if newmoon is not None:
                fields['nextNewMoon'] = newmoon
        except Exception as e:
            log.error('get_event_fields: get_next_fullmoon_and_newmoon(%r): %s.' % (day_start, e))
            ok = False

        return fields, ok

    def insert_fields(self, pkt: Dict[str, Any]) -> None:
        """Insert the celestial fields, each computed no more often than it
        can change: continuous fields every packet (or update_rate_secs),
        day-scoped fields once per local day, next-event fields when an
        event passes.  Every packet still carries every field."""
        pkt_time: int = to_int(pkt['dateTime'])
        pkt_datetime  = datetime.fromtimestamp(pkt_time, timezone.utc)
        ts_pkt_time = self.ts.from_datetime(pkt_datetime)

        # Continuously varying fields, throttled by update_rate_secs.  The
        # cache serves only packets moving forward within the window and
        # carrying the same unit system (distances are stored converted):
        # an out-of-order packet or a units change recomputes.
        delta = pkt_time - self.prev_reading['dateTime']
        if (self.update_rate_secs != 0 and 0 <= delta < self.update_rate_secs
                and pkt['usUnits'] == self.prev_reading.get('usUnits')):
            continuous = {key: value for key, value in self.prev_reading.items()
                          if key not in ('dateTime', 'usUnits')}
        else:
            continuous = self.get_continuous_fields(pkt, ts_pkt_time, pkt_datetime)
            if self.update_rate_secs != 0:
                # Merge, don't replace: a field whose computation failed
                # this round keeps its last good value for the throttled
                # packets that follow (the 3.x behavior).
                self.prev_reading.update(continuous)
                self.prev_reading['dateTime'] = pkt_time
                self.prev_reading['usUnits'] = pkt['usUnits']
        pkt.update(continuous)

        # Sun/moon rise/set/transit etc. are always reported for the current
        # day (i.e., the event may have already passed), so they are computed
        # from the beginning of the packet's local day.
        day_start = datetime.fromtimestamp(weeutil.weeutil.startOfDay(pkt_time), timezone.utc)
        day_start_ts = day_start.timestamp()

        # Day-scoped fields: recomputed only when the packet's local day
        # changes.  Compared for equality, not staleness, so a backfilled or
        # out-of-order packet is answered for its own day rather than from a
        # newer cache.
        if self.day_cache_day != day_start_ts:
            self.day_cache, day_ok = self.get_day_fields(day_start)
            # A failed section must not poison the cache for the rest of
            # the day: leave the cache unstamped so the next packet retries
            # (before 4.0, every packet recomputed and transient errors
            # self-healed in one loop cycle).
            self.day_cache_day = day_start_ts if day_ok else None
        pkt.update(self.day_cache)

        # Event fields: the cache stays valid until the local day advances
        # past a cached event.  A backward day (backfilled packet) also
        # recomputes, as does a failed search (the cache is left unstamped
        # so the next packet retries); the incomplete-cache check on day
        # advance covers a search that legitimately found nothing.
        if (self.event_cache_day is None
                or day_start_ts < self.event_cache_day
                or (day_start_ts > self.event_cache_day
                    and (len(self.event_cache) < 4
                         or min(self.event_cache.values()) < day_start_ts))):
            self.event_cache, event_ok = self.get_event_fields(day_start)
            self.event_cache_day = day_start_ts if event_ok else None
        pkt.update(self.event_cache)

if __name__ == '__main__':

    import configobj
    import locale
    import optparse

    import weeutil.logger

    class UnexpectedSensorRecord(Exception):
        pass

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

    def check_timestamp_fields(pkt: Dict[str, Any], fields: List[str]) -> bool:
        success: bool = True
        for field in fields:
            if field not in pkt:
                log.info('Packet missing %s' % field)
                success = False
            elif type(pkt[field]) is not float and type(pkt[field]) is not numpy.float64:
                log.info('Packet[%s] is not a float: %r(%s)' % (field, pkt[field], type(pkt[field])))
                success = False
            else:
                log.info('%25s: %35s' % (field, datetime.fromtimestamp(pkt[field]).strftime("%B %d, %Y at %I:%M %p")))
        return success

    def check_duration_fields(pkt: Dict[str, Any], fields: List[str]) -> bool:
        success: bool = True
        for field in fields:
            if field not in pkt:
                log.info('Packet missing %s' % field)
                success = False
            elif type(pkt[field]) is not float and type(pkt[field]) is not numpy.float64:
                log.info('Packet[%s] is not a float: %r(%s)' % (field, pkt[field], type(pkt[field])))
                success = False
            else:
                hours: int = int(pkt[field] / 3600)
                remainder: float = pkt[field] - 3600 * hours
                minutes: int = int (remainder / 60)
                remainder -= minutes * 60
                seconds = int(remainder)
                log.info('%25s: %2d hours, %2d minutes and %2d seconds' % (field, hours, minutes, seconds))
        return success

    def check_fullness_fields(pkt: Dict[str, Any], fields: List[str]) -> bool:
        success: bool = True
        for field in fields:
            if field not in pkt:
                log.info('Packet missing %s' % field)
                success = False
            elif type(pkt[field]) is not float and type(pkt[field]) is not numpy.float64:
                log.info('Packet[%s] is not a float: %r(%s)' % (field, pkt[field], type(pkt[field])))
                success = False
            else:
                log.info('%25s: %29.0f%% full' % (field, pkt[field]))
        return success

    def check_degree_fields(pkt: Dict[str, Any], fields: List[str]) -> bool:
        success: bool = True
        for field in fields:
            if field not in pkt:
                log.info('Packet missing %s' % field)
                success = False
            elif type(pkt[field]) is not float and type(pkt[field]) is not numpy.float64:
                log.info('Packet[%s] is not a float: %r(%s)' % (field, pkt[field], type(pkt[field])))
                success = False
            else:
                log.info('%25s: %34.1f\u00b0' % (field, pkt[field]))
        return success

    def check_distance_fields(pkt: Dict[str, Any], fields: List[str]) -> bool:
        success: bool = True
        for field in fields:
            if field not in pkt:
                log.info('Packet missing %s' % field)
                success = False
            elif type(pkt[field]) is not float and type(pkt[field]) is not numpy.float64:
                log.info('Packet[%s] is not a float: %r(%s)' % (field, pkt[field], type(pkt[field])))
                success = False
            else:
                label: str = 'miles'
                if pkt['usUnits'] == weewx.METRIC:
                    label = 'km'
                fmt_dist = locale.format_string('%.1f', pkt[field], grouping=True)
                log.info('%25s: %29s %s' % (field, fmt_dist, label))
        return success

    def check_phase_index_field(pkt: Dict[str, Any]) -> bool:
        """moonPhaseIndex must be an int in 0..7 (the moon_phases index);
        moonWaxing must be 0 or 1."""
        if 'moonPhaseIndex' not in pkt:
            log.info('Packet missing moonPhaseIndex')
            return False
        value = pkt['moonPhaseIndex']
        if type(value) is not int or not 0 <= value <= 7:
            log.info('Packet[moonPhaseIndex] is not an int in 0..7: %r' % value)
            return False
        log.info('%25s: %35d' % ('moonPhaseIndex', value))
        if pkt.get('moonWaxing') not in (0, 1):
            log.info('Packet[moonWaxing] is not 0 or 1: %r' % pkt.get('moonWaxing'))
            return False
        log.info('%25s: %35d' % ('moonWaxing', pkt['moonWaxing']))
        return True

    def check_str_fields(pkt: Dict[str, Any], fields: List[str]) -> bool:
        success: bool = True
        for field in fields:
            if field not in pkt:
                log.info('Packet missing %s' % field)
                success = False
            elif type(pkt[field]) is not str:
                log.info('Packet[%s] is not a str: %r(%s)' % (field, pkt[field], type(pkt[field])))
                success = False
            else:
                log.info('%25s: %35s' % (field, pkt[field]))
        return success

    weeutil.logger.setup('celestial', {})
    logging.getLogger().addHandler(logging.StreamHandler())

    usage = """Usage: python -m user.celestial --help
       python -m user.celestial --version
       python -m user.celestial --test --out-temp=<outside-temperature> --barometer=<barometer> [--metric] [--config=<weewx-config-file>] [--timestamp=<epoch-time>]"""

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', action='store_true',
                      help='Display version')
    parser.add_option('--test', dest='test', action='store_true',
                      help='Test celestial functions.  Mandatory: --Optional: --config, --timestamp')
    parser.add_option('--out-temp', dest='out_temp', type=float,
                      help='temperature to use in some celestial calculations.  Specify in Fahrenheit. If --metric, specify in Celsius.')
    parser.add_option('--barometer', dest='barometer', type=float,
                      help='barometer to use in some celestial calculations.  Specify in inHg.  If --metric, specify in mbar.')
    parser.add_option("--metric", action="store_true", dest="metric",
                      help='Specify if out-temp is expressed in Celsius and barometer is expressed in mbar.  Default fahrenheit and inches of mercury, respectively.')
    parser.add_option('--config', dest='config_file', type=str, metavar="FILE",
                      help='weewx.conf file from which to retrieve moon_phases, altitude, latitude and longitude.  Default is /home/weewx/weewx.conf')
    parser.add_option('--timestamp', dest='timestamp', type=float,
                      help='timestamp for which to request celestial information.  Default is the current time.')
    parser.add_option('--migrate-loopdata-fields', dest='migrate', action='store_true',
                      help='Rewrite the [LoopData] [[Include]] fields line for 4.0: rename '
                           'deprecated pre-3.0 celestial fields (keeping their rendition '
                           'suffixes and the line\'s order), drop the duplicates the renames '
                           'create, and append the fields the 4.0 sample report needs.  '
                           'Non-celestial fields are never touched.  Use with --config and '
                           'exactly one of --output, --in-place or --print-fields-value.')
    parser.add_option('--output', dest='output_file', type=str, metavar='FILE',
                      help='With --migrate-loopdata-fields: write the rewritten configuration '
                           'to FILE, leaving the --config file untouched (diff them, then move '
                           'FILE into place).')
    parser.add_option('--in-place', dest='in_place', action='store_true',
                      help='With --migrate-loopdata-fields: rewrite the --config file itself '
                           '(a .bak-celestial-4.0 backup is made first).')
    parser.add_option('--print-fields-value', dest='print_fields', action='store_true',
                      help='With --migrate-loopdata-fields: print the migrated fields value as '
                           'a bare comma-separated list, ready to paste into weewx.conf (do '
                           'NOT add brackets or quotes).')
    (options, args) = parser.parse_args()

    if options.version:
        log.info("Celestial version is %s." % CELESTIAL_VERSION)
        log.info("Skyfield version is %d.%d." % (skyfield.VERSION[0], skyfield.VERSION[1]))
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
                backup = migrate_config + '.bak-celestial-4.0'
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
            log.info('dropped duplicate  %s' % name)
        for name in report['added']:
            log.info('added  %s' % name)
        log.info('%d renamed, %d duplicates dropped, %d added.'
                 % (len(report['renamed']), len(report['dropped']), len(report['added'])))
        if any(old.split('.')[1] in ('daySunshineDur', 'yesterdaySunshineDur')
               for old, _ in report['renamed']):
            log.info('NOTE: daySunshineDur/yesterdaySunshineDur were renamed to')
            log.info('      daylightDur/yesterdayDaylightDur.  If another extension')
            log.info('      (e.g., weewx-sunduration) provides a real daySunshineDur on')
            log.info('      this system, restore those entries by hand.')
        exit(0)

    if options.test:
        locale.setlocale(locale.LC_ALL, locale.getlocale())
        if not options.out_temp:
            log.error('--out-temp must be specified.')
            exit(0)

        if not options.barometer:
            log.error('--barometer must be specified.')
            exit(0)

        usUnits = weewx.US
        if options.metric:
            usUnits = weewx.METRIC

        config_file: str = '/home/weewx/weewx.conf'
        if options.config_file:
            config_file = options.config_file
        config_dict: Dict[str, Any] = get_configuration(config_file)

        user_root, moon_phases, altitude_m, latitude, longitude = Sky.get_weewx_config_info(config_dict)
        if altitude_m is None or latitude is None or longitude is None:
            log.error("Could not determine station's altitude, latitude and longitude.")
            exit(1)
        sky = Sky(0, user_root, moon_phases, altitude_m, latitude, longitude)
        if not sky.is_valid():
            log.error('Could not instantiate Sky object.')
            exit(1)

        timestamp: float = time.time()
        if options.timestamp:
            timestamp = options.timestamp

        pkt: Dict[str, Any] = {'dateTime': timestamp, 'usUnits': usUnits, 'outTemp': options.out_temp, 'barometer': options.barometer}
        sky.insert_fields(pkt)
        log.debug(pkt)

        # Check that all fields are present in the packet and have valid values.
        if not check_str_fields(pkt, [
            'moonPhase']):
            log.info('Test failed.  See above.')
        elif not check_distance_fields(pkt, [
            'earthJupiterDistance',
            'earthMarsDistance',
            'earthMercuryDistance',
            'earthNeptuneDistance',
            'earthMoonDistance',
            'earthPlutoDistance',
            'earthSaturnDistance',
            'earthSunDistance',
            'earthUranusDistance',
            'earthVenusDistance']):
            log.info('Test failed.  See above.')
        elif not check_duration_fields(pkt, [
            'daylightDur',
            'yesterdayDaylightDur']):
            log.info('Test failed.  See above.')
        elif not check_fullness_fields(pkt, [
            'moonFullness']):
            log.info('Test failed.  See above.')
        elif not check_degree_fields(pkt, [
            'moonAltitude',
            'moonAzimuth',
            'moonDeclination',
            'moonRightAscension',
            'sunAltitude',
            'sunAzimuth',
            'sunDeclination',
            'sunRightAscension']
            + [planet + suffix for planet in LOOP_PLANETS
               for suffix in ('Azimuth', 'Altitude')]):
            log.info('Test failed.  See above.')
        elif not check_phase_index_field(pkt):
            log.info('Test failed.  See above.')
        elif not check_timestamp_fields(pkt, [
            'astronomicalTwilightEnd',
            'astronomicalTwilightStart',
            'civilTwilightEnd',
            'civilTwilightStart',
            'moonrise',
            'moonset',
            'moonTransit',
            'nauticalTwilightEnd',
            'nauticalTwilightStart',
            'nextEquinox',
            'nextFullMoon',
            'nextNewMoon',
            'nextSolstice',
            'sunrise',
            'sunset',
            'sunTransit',
            'tomorrowSunrise',
            'tomorrowSunset']):
            log.info('Test failed.  See above.')
        else:
            log.info('All fields present and of the correct type.  The test passed.')
