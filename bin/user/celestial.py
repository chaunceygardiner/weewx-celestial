"""
celestial.py

Copyright (C)2022-2025 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Celestial is a WeeWX service that generates Celestial observations
that are inserted into the loop packet.
"""

import logging
import sys

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy

import skyfield
import skyfield.almanac
import skyfield.api
import skyfield.framelib
import skyfield.timelib
import weeutil.Moon
import weewx

from weeutil.weeutil import to_bool
from weeutil.weeutil import to_int
from weewx.engine import StdEngine
from weewx.engine import StdService

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '2.2'

if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 9):
    raise weewx.UnsupportedFeature(
        "weewx-celestial requires Python 3.9 or later, found %s.%s" % (sys.version_info[0], sys.version_info[1]))

if weewx.__version__ < "4":
    raise weewx.UnsupportedFeature(
        "weewx-celestial requires WeeWX, found %s" % weewx.__version__)

# Set up celestial observation type.
weewx.units.obs_group_dict['EarthSunDistance']          = 'group_distance'
weewx.units.obs_group_dict['EarthMoonDistance']         = 'group_distance'
weewx.units.obs_group_dict['EarthMercuryDistance']      = 'group_distance'
weewx.units.obs_group_dict['EarthVenusDistance']        = 'group_distance'
weewx.units.obs_group_dict['EarthMarsDistance']         = 'group_distance'
weewx.units.obs_group_dict['EarthJupiterDistance']      = 'group_distance'
weewx.units.obs_group_dict['EarthSaturnDistance']       = 'group_distance'
weewx.units.obs_group_dict['EarthUranusDistance']       = 'group_distance'
weewx.units.obs_group_dict['EarthNeptuneDistance']      = 'group_distance'
weewx.units.obs_group_dict['EarthPlutoDistance']        = 'group_distance'
weewx.units.obs_group_dict['SunAzimuth']                = 'group_direction'
weewx.units.obs_group_dict['SunAltitude']               = 'group_direction'
weewx.units.obs_group_dict['SunRightAscension']         = 'group_direction'
weewx.units.obs_group_dict['SunDeclination']            = 'group_direction'
weewx.units.obs_group_dict['Sunrise']                   = 'group_time'
weewx.units.obs_group_dict['SunTransit']                = 'group_time'
weewx.units.obs_group_dict['Sunset']                    = 'group_time'
weewx.units.obs_group_dict['yesterdaySunshineDur']      = 'group_deltatime'
weewx.units.obs_group_dict['AstronomicalTwilightStart'] = 'group_time'
weewx.units.obs_group_dict['NauticalTwilightStart']     = 'group_time'
weewx.units.obs_group_dict['CivilTwilightStart']        = 'group_time'
weewx.units.obs_group_dict['CivilTwilightEnd']          = 'group_time'
weewx.units.obs_group_dict['NauticalTwilightEnd']       = 'group_time'
weewx.units.obs_group_dict['AstronomicalTwilightEnd']   = 'group_time'
weewx.units.obs_group_dict['NextEquinox']               = 'group_time'
weewx.units.obs_group_dict['NextSolstice']              = 'group_time'
weewx.units.obs_group_dict['MoonAzimuth']               = 'group_direction'
weewx.units.obs_group_dict['MoonAltitude']              = 'group_direction'
weewx.units.obs_group_dict['MoonRightAscension']        = 'group_direction'
weewx.units.obs_group_dict['MoonDeclination']           = 'group_direction'
weewx.units.obs_group_dict['MoonFullness']              = 'group_percent'
weewx.units.obs_group_dict['MoonPhase']                 = 'group_data'
weewx.units.obs_group_dict['NextNewMoon']               = 'group_time'
weewx.units.obs_group_dict['NextFullMoon']              = 'group_time'
weewx.units.obs_group_dict['Moonrise']                  = 'group_time'
weewx.units.obs_group_dict['MoonTransit']               = 'group_time'
weewx.units.obs_group_dict['Moonset']                   = 'group_time'

class Celestial(StdService):
    def __init__(self, engine: StdEngine, config_dict: Dict[str, Any]):
        super(Celestial, self).__init__(engine, config_dict)
        log.info("Service version is %s." % CELESTIAL_VERSION)

        if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 7):
            raise Exception("Python 3.7 or later is required for the celestial plugin.")

        # Only continue if the plugin is enabled.
        celestial_config_dict = config_dict.get('Celestial', {})
        enable = to_bool(celestial_config_dict.get('enable'))
        if enable:
            log.info("Celestial is enabled...continuing.")
        else:
            log.info("Celestial is disabled. Enable it in the Celestial section of weewx.conf.")
            return

        user_root, moon_phases, altitude_m, latitude, longitude = Sky.get_weewx_config_info(config_dict)
        if latitude is None or longitude is None:
            log.error("Could not determine station's latitude and longitude.")
            return
        if altitude_m is None:
            log.error("Could not determine station's altitude.")
            return

        self.sky = Sky(user_root, moon_phases, altitude_m, latitude, longitude)
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

class Sky():
    def __init__(self, user_root: str, moon_phases: List[str], altitude_m: float, latitude: float, longitude: float):
        log.info("Skyfield version is %d.%d." % (skyfield.VERSION[0], skyfield.VERSION[1]))

        self.valid      : bool      = False
        self.user_root  : str       = user_root
        self.moon_phases: List[str] = moon_phases
        self.altitude_m : float     = altitude_m
        self.latitude   : float     = latitude
        self.longitude  : float     = longitude

        # Load the JPL ephemeris DE421 (covers 1900-2050).
        try:
            planets_file: str = '%s/de421.bsp' % user_root
            self.planets: skyfield.jpllib.SpiceKernel = skyfield.api.load_file(planets_file)
        except Exception as e:
            log.error('init: Could not load %s: %s.  Celestial will not run.' % (planets_file, e))
            return

        try:
            orb: str = 'sun'
            self.sun: skyfield.vectorlib.VectorSum = self.planets['sun']
            orb = 'moon'
            self.moon: skyfield.vectorlib.VectorSum = self.planets['moon']
            orb = 'earth'
            self.earth: skyfield.vectorlib.VectorSum  = self.planets['earth']
            orb = 'mercury'
            self.mercury: skyfield.vectorlib.VectorSum = self.planets['mercury']
            orb = 'venus'
            self.venus: skyfield.vectorlib.VectorSum = self.planets['venus']
            orb = 'mars'
            self.mars: skyfield.vectorlib.VectorSum = self.planets['mars']
            orb = 'jupiter'
            self.jupiter: skyfield.vectorlib.VectorSum = self.planets['jupiter barycenter']
            orb = 'saturn'
            self.saturn: skyfield.vectorlib.VectorSum = self.planets['saturn barycenter']
            orb = 'uranus'
            self.uranus: skyfield.vectorlib.VectorSum = self.planets['uranus barycenter']
            orb = 'neptune'
            self.neptune: skyfield.vectorlib.VectorSum = self.planets['neptune barycenter']
            orb = 'pluto'
            self.pluto: skyfield.vectorlib.VectorSum = self.planets['pluto barycenter']
        except Exception as e:
            log.error('init: Could not find %s in ephermis file %s: %s.  Celestial will not run.' % (orb, planets_file, e))
            return

        try:
            self.bluffton = skyfield.api.wgs84.latlon(self.latitude, self.longitude, elevation_m=self.altitude_m)
        except Exception as e:
            log.error('init: skyfield.api.wgs84.latlon(%f, %f, %f): %s.  Celestial will not run.' % (self.latitude, self.longitude, self.altitude_m, e))
            return
        try:
            self.observer = self.earth + self.bluffton
        except Exception as e:
            log.error('init: Could not set observer (earth: %r, bluffton: %r): %s.  Celestial will not run.' % (self.earth, self.blufftone, e))
            return

        self.valid = True

    @staticmethod
    def get_weewx_config_info(config_dict: Dict[str, Any]) -> Tuple[str, List[str], Optional[float], Optional[float], Optional[float]]:
        # Compose USER_ROOT directory (it's where Skyfield's planets file was installed.
        weewx_root: str = config_dict.get('WEEWX_ROOT')
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

    def distance_from_earth(self, ts_pkt_time: skyfield.timelib.Timescale, orb: skyfield.vectorlib.VectorSum):
        position = self.earth.at(ts_pkt_time).observe(orb)
        _, _, distance = position.radec()
        return distance.au

    def get_moon_phase(self, ts: skyfield.timelib.Timescale, pkt_datetime: datetime) -> Tuple[float, float]:
        t: skyfield.timelib.Timescale = ts.from_datetime(pkt_datetime)

        e = self.earth.at(t)
        s = e.observe(self.sun).apparent()
        m = e.observe(self.moon).apparent()

        _, slon, _ = s.frame_latlon(skyfield.framelib.ecliptic_frame)
        _, mlon, _ = m.frame_latlon(skyfield.framelib.ecliptic_frame)
        phase = (mlon.degrees - slon.degrees) % 360.0

        percent = 100.0 * m.fraction_illuminated(self.sun)

        return phase, percent

    def get_moon_phase_index(self, degrees: float) -> int:
        return int(round((degrees / 360) * 8))

    def get_next_fullmoon_and_newmoon(self, ts: skyfield.timelib.Timescale, day_start: datetime) -> Tuple[datetime, datetime]:
        ts_day_start = ts.from_datetime(day_start)
        ts_plus_sixty_days = ts.from_datetime(day_start + timedelta(days=60))
        times, phases = skyfield.almanac.find_discrete(ts_day_start, ts_plus_sixty_days, skyfield.almanac.moon_phases(self.planets))

        fullmoon = None
        newmoon = None
        for phase, t in zip(phases, times):
            match phase:
                case 0:
                    newmoon = t.utc_datetime().timestamp()
                case 2:
                    fullmoon = t.utc_datetime().timestamp()
            if fullmoon is not None and newmoon is not None:
                break
        return fullmoon, newmoon

    def get_next_equinox_and_solstice(self, ts: skyfield.timelib.Timescale, day_start: datetime) -> Tuple[datetime, datetime]:
        ts_day_start = ts.from_datetime(day_start)
        ts_plus_one_year = ts.from_datetime(day_start + timedelta(days=366))
        times, types = skyfield.almanac.find_discrete(ts_day_start, ts_plus_one_year, skyfield.almanac.seasons(self.planets))

        equinox = None
        solstice = None
        for typ, t in zip(types, times):
            match typ:
                case 0:
                    equinox = t.utc_datetime().timestamp()
                case 1:
                    solstice = t.utc_datetime().timestamp()
                case 2:
                    equinox = t.utc_datetime().timestamp()
                case 3:
                    solstice = t.utc_datetime().timestamp()
            if equinox is not None and solstice is not None:
                break
        return equinox, solstice

    def get_az_alt_ra_dec(self, ts: skyfield.timelib.Timescale, orb, pkt_datetime: datetime, tempC: Optional[float], pressureMbar: Optional[float]) -> Tuple[float, float, float, float]:

        astronomic = self.observer.at(ts.from_datetime(pkt_datetime)).observe(orb)
        apparent = astronomic.apparent()

        # Altitude and azimuth in the sky of a specific geographic location
        if tempC and pressureMbar:
            alt, az, _ = apparent.altaz(temperature_C=tempC, pressure_mbar=pressureMbar)
        elif tempC:
            alt, az, _ = apparent.altaz(temperature_C=tempC)
        elif pressureMbar:
            alt, az, _ = apparent.altaz(pressure_mbar=pressureMbar)
        else:
            alt, az, _ = apparent.altaz()
        ra, dec, _ = apparent.radec()

        return az.degrees, alt.degrees, ra._degrees, dec.degrees

    def get_rise_set_transit(self, ts: skyfield.timelib.Timescale, orb: skyfield.vectorlib.VectorSum, day_start: datetime) -> Tuple[Optional[datetime.timestamp], Optional[datetime.timestamp], datetime.timestamp]:
        rise = None
        set = None
        transit = None

        ts_day_start = ts.from_datetime(day_start)
        ts_day_end = ts.from_datetime(day_start + timedelta(days=2))  # Assume we'll see a rise and set in the next 2 days

        # rise/set
        rise_times, rise_crosses_horizons = skyfield.almanac.find_risings(self.observer, orb, ts_day_start, ts_day_end)
        set_times, set_crosses_horizons = skyfield.almanac.find_settings(self.observer, orb, ts_day_start, ts_day_end)
        if  len(rise_crosses_horizons) > 0 and rise_crosses_horizons[0]:
            rise = rise_times[0].utc_datetime().timestamp()
        if  len(set_crosses_horizons) > 0 and set_crosses_horizons[0]:
            set = set_times[0].utc_datetime().timestamp()

        #transit
        transit_times = skyfield.almanac.find_transits(self.observer, orb, ts_day_start, ts_day_end)
        if len(transit_times) > 0:
            transit = transit_times[0].utc_datetime().timestamp()

        return rise, set, transit

    def get_sunrise_sunset_transit_daylight(self, ts: skyfield.timelib.Timescale, day_start: datetime) -> Tuple[Optional[datetime.timestamp], Optional[datetime.timestamp], datetime.timestamp, float]:
        sunrise = None
        sunset = None
        transit = None

        ts_day_start = ts.from_datetime(day_start)
        ts_day_end = ts.from_datetime(day_start + timedelta(days=1))

        # Sunrise/Sunset/SunTransit/daySunshineDur
        sunrise_times, sunrise_crosses_horizons = skyfield.almanac.find_risings(self.observer, self.sun, ts_day_start, ts_day_end)
        sunset_times, sunset_crosses_horizons = skyfield.almanac.find_settings(self.observer, self.sun, ts_day_start, ts_day_end)
        if  len(sunrise_crosses_horizons) > 0 and sunrise_crosses_horizons[0]:
            sunrise = sunrise_times[0].utc_datetime().timestamp()
        if  len(sunrise_crosses_horizons) > 0 and sunset_crosses_horizons[0]:
            sunset = sunset_times[0].utc_datetime().timestamp()
        if  len(sunrise_crosses_horizons) > 0 and sunrise_crosses_horizons[0] and len(sunset_crosses_horizons) > 0 and sunset_crosses_horizons[0]:
            daylight = sunset - sunrise
        elif len(sunrise_crosses_horizons) > 0 and not sunrise_crosses_horizons[0] and len(sunset_crosses_horizons) > 0 and not sunset_crosses_horizons[0]:
            # The sun neither rose nor set.
            alt, _, _ = self.observer.at(sunrise_times[0]).observe(self.sun).apparent().altaz()
            if alt.degrees > -0.833333:
                # 24 hours of daylight
                daylight = 86400
            else:
                # 24 hours of darkness
                daylight = 0
        elif len(sunrise_crosses_horizons) > 0 and sunrise_crosses_horizons[0] and len(sunset_crosses_horizons) > 0 and not sunset_crosses_horizons[0]:
            # The sun rose, but never set.
            daylight = ts_day_end.timestamp() - sunrise
        else:
            # The never rose, but it did set.
            daylight = sunset - ts_day_start.timestamp()

        transit_times = skyfield.almanac.find_transits(self.observer, self.sun, ts_day_start, ts_day_end)
        if len(transit_times) > 0:
            transit = transit_times[0].utc_datetime().timestamp()

        return sunrise, sunset, transit, daylight

    def insert_fields(self, pkt: Dict[str, Any]) -> None:
        pkt_time: int = to_int(pkt['dateTime'])
        pkt_datetime  = datetime.fromtimestamp(pkt_time, timezone.utc)

        # Create a skyfield timescale with pkt_datetime.
        ts = skyfield.api.load.timescale()
        ts_pkt_time = ts.from_datetime(pkt_datetime)

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
            pkt['SunAzimuth'] = sun_az
            pkt['SunAltitude'] = sun_alt
            pkt['SunRightAscension'] = sun_ra
            pkt['SunDeclination'] = sun_dec
        except Exception as e:
            log.error('insert_fields: get_az_alt_ra_dec(%r, %r, %d, %r %r): %s.' % (ts, self.sun, pkt_datetime, tempC, pressureMbar, e))

        try:
            moon_az, moon_alt, moon_ra, moon_dec= self.get_az_alt_ra_dec(ts, self.moon, pkt_datetime, tempC, pressureMbar)
            pkt['MoonAzimuth'] = moon_az
            pkt['MoonAltitude'] = moon_alt
            pkt['MoonRightAscension'] = moon_ra
            pkt['MoonDeclination'] = moon_dec
        except Exception as e:
            log.error('insert_fields: get_az_alt_ra_dec(moon): %s.' % e)

        try:
            moon_phase_degrees, percent_illumination = self.get_moon_phase(ts, pkt_datetime)
            pkt['MoonFullness'] = percent_illumination
            index = self.get_moon_phase_index(moon_phase_degrees)
            pkt['MoonPhase'] = self.moon_phases[index]
        except Exception as e:
            log.error('insert_fields: get_moon_phase: %s.' % e)

        # Convert astrological units to kilometers or miles
        if pkt['usUnits'] == weewx.METRIC:
            multiplier = 1.496e+8
        else:
            multiplier = 9.296e+7

        try:
            orb: str = 'sun'
            pkt['EarthSunDistance'] = self.distance_from_earth(ts_pkt_time, self.sun) * multiplier
            orb = 'moon'
            pkt['EarthMoonDistance'] = self.distance_from_earth(ts_pkt_time, self.moon) * multiplier

            orb = 'earth'
            pkt['EarthMercuryDistance'] = self.distance_from_earth(ts_pkt_time, self.mercury) * multiplier
            orb = 'venus'
            pkt['EarthVenusDistance'] = self.distance_from_earth(ts_pkt_time, self.venus) * multiplier
            orb = 'mars'
            pkt['EarthMarsDistance'] = self.distance_from_earth(ts_pkt_time, self.mars) * multiplier
            orb = 'jupiter'
            pkt['EarthJupiterDistance'] = self.distance_from_earth(ts_pkt_time, self.jupiter) * multiplier
            orb = 'saturn'
            pkt['EarthSaturnDistance'] = self.distance_from_earth(ts_pkt_time, self.saturn) * multiplier
            orb = 'uranus'
            pkt['EarthUranusDistance'] = self.distance_from_earth(ts_pkt_time, self.uranus) * multiplier
            orb = 'neptune'
            pkt['EarthNeptuneDistance'] = self.distance_from_earth(ts_pkt_time, self.neptune) * multiplier
            orb = 'pluto'
            pkt['EarthPlutoDistance'] = self.distance_from_earth(ts_pkt_time, self.pluto) * multiplier
        except Exception as e:
            log.error('insert_fields: distance_from_earth(%r, %s): %s.' % (ts_pkt_time, orb, e))


        # Sun/Moon rise/set/transit, etc. are always reported for the curent day (i.e., the event may have already passed.
        # We also don't want Equinox/Solstice/NewMoon/FullMoon to disappear as soon as it is hit (keep it around for the day)
        # As such, use the beginning of day for the observer, and recompute.
        pkt_now = datetime.fromtimestamp(pkt_time)
        local_day_start = datetime.strptime(pkt_now.strftime('%Y-%m-%d'), '%Y-%m-%d')
        day_start  = datetime.fromtimestamp(local_day_start.timestamp(), timezone.utc)

        try:
            sunrise, sunset, transit, daylight = self.get_sunrise_sunset_transit_daylight(ts, day_start)
            if sunrise is not None:
                pkt['Sunrise'] = sunrise
            if  sunset is not None:
                pkt['Sunset'] = sunset
            pkt['daySunshineDur'] = daylight
            pkt['SunTransit'] = transit
        except Exception as e:
            log.error('insert_fields: get_sunrise_sunset_transit_daylight(%r): %s.' % (day_start, e))

        # Moonrise/Moonset/MoonTransit
        try:
            moonrise, moonset, moontransit = self.get_rise_set_transit(ts, self.moon, day_start)
            if moonrise is not None:
                pkt['Moonrise'] = moonrise
            if moonset is not None:
                pkt['Moonset'] = moonset
            pkt['MoonTransit'] = moontransit
        except Exception as e:
            log.error('insert_fields: get_rise_set_transit(moon, %r): %s.' % (day_start, e))

        try:
            next_equinox, next_solstice = self.get_next_equinox_and_solstice(ts, day_start)
            pkt['NextEquinox']  = next_equinox
            pkt['NextSolstice'] = next_solstice
        except Exception as e:
            log.error('insert_fields: get_next_equinox_and_solstice(%r): %s.' % (day_start, e))


        try:
            fullmoon, newmoon = self.get_next_fullmoon_and_newmoon(ts, day_start)
            if fullmoon is not None:
                pkt['NextFullMoon']  = fullmoon
            if newmoon is not None:
                pkt['NextNewMoon'] = newmoon
        except Exception as e:
            log.error('insert_fields: get_next_fullmoon_and_newmoon(%r): %s.' % (day_start, e))

        try:
            f = skyfield.almanac.dark_twilight_day(self.planets, self.bluffton)
            times, events = skyfield.almanac.find_discrete(ts.from_datetime(day_start), ts.from_datetime(day_start + timedelta(days=1)), f)
            astronomical_encountered = False
            nautical_encountered = False
            civil_encountered = False
            for event, t in zip(events, times):
                match event:
                    case 0:
                        pkt['AstronomicalTwilightEnd'] = t.utc_datetime().timestamp()
                    case 1:
                        if not astronomical_encountered:
                            pkt['AstronomicalTwilightStart'] = t.utc_datetime().timestamp()
                            astronomical_encountered = True
                        else:
                            pkt['NauticalTwilightEnd'] = t.utc_datetime().timestamp()
                    case 2:
                        if not nautical_encountered:
                            pkt['NauticalTwilightStart'] = t.utc_datetime().timestamp()
                            nautical_encountered = True
                        else:
                            pkt['CivilTwilightEnd'] = t.utc_datetime().timestamp()
                    case 3:
                        if not civil_encountered:
                            pkt['CivilTwilightStart'] = t.utc_datetime().timestamp()
                            civil_encountered = True
        except Exception as e:
            log.error('insert_fields: skyfield.almanac.find_discrete twilight(%r, %r): %s.' % (day_start, f, e))

        try:
            # We need yesterday's sunshine duration
            yesterday_start = day_start - timedelta(days=1)
            _, _, _, yesterday_daylight = self.get_sunrise_sunset_transit_daylight(ts, yesterday_start)
            pkt['yesterdaySunshineDur'] = yesterday_daylight
        except Exception as e:
            log.error('insert_fields: get_sunrise_sunset_transit_daylight(yesterday_start: %r): %s.' % (yesterday_start, e))

        try:
            # Tomorrow sunrise, sunset, daytime
            tomorrow_start = day_start + timedelta(days=1)
            tomorrow_sunrise, tomorrow_sunset, _, _ = self.get_sunrise_sunset_transit_daylight(ts, tomorrow_start)
            if tomorrow_sunrise is not None:
                pkt['tomorrowSunrise'] = tomorrow_sunrise
            if  tomorrow_sunset is not None:
                pkt['tomorrowSunset'] = tomorrow_sunset
        except Exception as e:
            log.error('insert_fields: get_sunrise_sunset_transit_daylight(tomorrow_start: %r): %s.' % (tomorrow_start, e))

# Define a main entry point for basic testing.
# Invoke this as follows:
#
# Activate venv
# From root directory of this plugin project:
# PYTHONPATH=bin/user:/home/weewx/bin python -m celestial --version
# PYTHONPATH=bin/user:/home/weewx/bin python -m celestial --test --out-temp=65.1 --barometer=30.128
# PYTHONPATH=bin/user:/home/weewx/bin python -m celestial --test --out-temp=18.4 --barometer=1020.25 --metric


if __name__ == '__main__':

    import configobj
    import locale
    import optparse
    import time

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

    usage = """Usage: python -m user.vantagenext --help
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
    (options, args) = parser.parse_args()

    if options.version:
        log.info("Celestial version is %s." % CELESTIAL_VERSION)
        log.info("Skyfield version is %d.%d." % (skyfield.VERSION[0], skyfield.VERSION[1]))
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
        sky = Sky(user_root, moon_phases, altitude_m, latitude, longitude)
        if not sky.is_valid():
            log.error('Could not instantiate Sky object.')
            exit(0)

        timestamp: float = time.time()
        if options.timestamp:
            timestamp = options.timestamp

        pkt: Dict[str, Any] = {'dateTime': timestamp, 'usUnits': usUnits, 'outTemp': options.out_temp, 'barometer': options.barometer}
        sky.insert_fields(pkt)
        log.debug(pkt)

        # Check that all fields are present in the packet and have valid values.
        if not check_str_fields(pkt, [
            'MoonPhase']):
            log.info('Test failed.  See above.')
        elif not check_distance_fields(pkt, [
            'EarthJupiterDistance',
            'EarthMarsDistance',
            'EarthMercuryDistance',
            'EarthNeptuneDistance',
            'EarthMoonDistance',
            'EarthPlutoDistance',
            'EarthSaturnDistance',
            'EarthSunDistance',
            'EarthUranusDistance',
            'EarthVenusDistance']):
            log.info('Test failed.  See above.')
        elif not check_duration_fields(pkt, [
            'daySunshineDur',
            'yesterdaySunshineDur']):
            log.info('Test failed.  See above.')
        elif not check_fullness_fields(pkt, [
            'MoonFullness']):
            log.info('Test failed.  See above.')
        elif not check_degree_fields(pkt, [
            'MoonAltitude',
            'MoonAzimuth',
            'MoonDeclination',
            'MoonRightAscension',
            'SunAltitude',
            'SunAzimuth',
            'SunDeclination',
            'SunRightAscension']):
            log.info('Test failed.  See above.')
        elif not check_timestamp_fields(pkt, [
             'AstronomicalTwilightEnd',
            'AstronomicalTwilightStart',
            'CivilTwilightEnd',
            'CivilTwilightStart',
            'Moonrise',
            'Moonset',
            'MoonTransit',
            'NauticalTwilightEnd',
            'NauticalTwilightStart',
            'NextEquinox',
            'NextFullMoon',
            'NextNewMoon',
            'NextSolstice',
            'Sunrise',
            'Sunset',
            'SunTransit',
            'tomorrowSunrise',
            'tomorrowSunset']):
            log.info('Test failed.  See above.')
        else:
            log.info('All fields present and of the correct type.  The test passed.')
