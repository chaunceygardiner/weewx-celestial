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
from typing import Any, Dict, Optional, Tuple

import skyfield
import skyfield.almanac
import skyfield.api
import skyfield.framelib
import weeutil.Moon
import weewx

from weeutil.weeutil import to_bool
from weeutil.weeutil import to_int
from weewx.engine import StdService

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '2.0'

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
    def __init__(self, engine, config_dict):
        super(Celestial, self).__init__(engine, config_dict)
        log.info("Service version is %s." % CELESTIAL_VERSION)
        log.info("Skyfield version is %d.%d." % (skyfield.VERSION[0], skyfield.VERSION[1]))

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

        # Compose report directory
        weewx_root: str              = str(config_dict.get('WEEWX_ROOT'))
        celestial_report_config_dict = config_dict['StdReport'].get('CelestialReport', {})
        self.html_root : str         = celestial_report_config_dict.get('HTML_ROOT')
        if not self.html_root.startswith('/'):
            self.html_root = "%s/%s" % (weewx_root, self.html_root)

        self.moon_phases = weeutil.Moon.moon_phases
        if 'Defaults' in config_dict['StdReport']:
            if 'Almanac' in config_dict['StdReport']['Defaults']:
                if 'moon_phases' in config_dict['StdReport']['Defaults']['Almanac']:
                    self.moon_phases = config_dict['StdReport']['Defaults']['Almanac']['moon_phases']

        # observer usually needs latitude and longitude
        altitude_vt = engine.stn_info.altitude_vt
        altitude_vt = weewx.units.StdUnitConverters[weewx.METRIC].convert(altitude_vt)
        self.altitude = altitude_vt[0]
        self.latitude = engine.stn_info.latitude_f
        self.longitude = engine.stn_info.longitude_f
        if self.latitude is None or self.longitude is None:
            log.error("Could not determine station's latitude and longitude.")
            return
        if self.altitude is None:
            log.error("Could not determine station's altitude.")
            return

        # Need to delay some Skyfield initialization until the CopyGenerator copies the de421.bsp file.
        # The file will be loaded on the first loop packet.
        self.first_time = True

        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop)

    def perform_skyfield_init(self) -> bool:

        # Load the JPL ephemeris DE421 (covers 1900-2050).
        try:
            self.planets = skyfield.api.load_file('%s/de421.bsp' % self.html_root)
        except:
            log.info('Could not load de421.bsp file.')
            return False
            
        self.sun = self.planets['sun']
        self.moon = self.planets['moon']
        self.earth  = self.planets['earth']
        self.mercury  = self.planets['mercury']
        self.venus  = self.planets['venus']
        self.mars  = self.planets['mars']
        self.jupiter  = self.planets['jupiter barycenter']
        self.saturn  = self.planets['saturn barycenter']
        self.uranus  = self.planets['uranus barycenter']
        self.neptune  = self.planets['neptune barycenter']
        self.pluto  = self.planets['pluto barycenter']

        self.bluffton = skyfield.api.wgs84.latlon(self.latitude, self.longitude, elevation_m=self.altitude)
        self.observer = self.earth + self.bluffton

        return True

    @staticmethod
    def distance_from_earth(ts_pkt_datetime: datetime, earth, orb):
        position = earth.at(ts_pkt_datetime).observe(orb)
        _, _, distance = position.radec()
        return distance.au

    def get_moon_phase(self, ts, pkt_datetime: datetime) -> Tuple[float, float]:
        t = ts.from_datetime(pkt_datetime)

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

    def get_next_fullmoon_and_newmoon(self, ts, day_start: datetime) -> Tuple[datetime, datetime]:
        ts_day_start = ts.from_datetime(day_start)
        ts_plus_sixty_days = ts.from_datetime(day_start + timedelta(days=60))
        times, phases = skyfield.almanac.find_discrete(ts_day_start, ts_plus_sixty_days, skyfield.almanac.moon_phases(self.planets))

        fullmoon = None
        newmoon = None
        for phase, time in zip(phases, times):
            match phase:
                case 0:
                    newmoon = time.utc_datetime().timestamp()
                case 2:
                    fullmoon = time.utc_datetime().timestamp()
            if fullmoon is not None and newmoon is not None:
                break
        return fullmoon, newmoon

    def get_next_equinox_and_solstice(self, ts, day_start: datetime) -> Tuple[datetime, datetime]:
        ts_day_start = ts.from_datetime(day_start)
        ts_plus_one_year = ts.from_datetime(day_start + timedelta(days=366))
        times, types = skyfield.almanac.find_discrete(ts_day_start, ts_plus_one_year, skyfield.almanac.seasons(self.planets))

        equinox = None
        solstice = None
        for typ, time in zip(types, times):
            match typ:
                case 0:
                    equinox = time.utc_datetime().timestamp()
                case 1:
                    solstice = time.utc_datetime().timestamp()
                case 2:
                    equinox = time.utc_datetime().timestamp()
                case 3:
                    solstice = time.utc_datetime().timestamp()
            if equinox is not None and solstice is not None:
                break
        return equinox, solstice

    def get_az_alt_ra_dec(self, ts, orb, pkt_datetime: datetime, tempC: float, pressureMbar: float) -> Tuple[float, float, float, float]:

        astronomic = self.observer.at(ts.from_datetime(pkt_datetime)).observe(orb)
        apparent = astronomic.apparent()

        # Altitude and azimuth in the sky of a specific geographic location
        alt, az, _ = apparent.altaz(temperature_C=tempC, pressure_mbar=pressureMbar)
        ra, dec, _ = apparent.radec()

        return az.degrees, alt.degrees, ra._degrees, dec.degrees

    def get_rise_set_transit(self, ts, orb, day_start: datetime) -> Tuple[Optional[datetime.timestamp], Optional[datetime.timestamp], datetime.timestamp]:
        rise = None
        set = None
        transit = None

        ts_day_start = ts.from_datetime(day_start)
        ts_day_end = ts.from_datetime(day_start + timedelta(days=1))

        # rise/set
        rise_times, rise_crosses_horizons = skyfield.almanac.find_risings(self.observer, orb, ts_day_start, ts_day_end)
        set_times, set_crosses_horizons = skyfield.almanac.find_settings(self.observer, orb, ts_day_start, ts_day_end)
        if  rise_crosses_horizons[0]:
            rise = rise_times[0].utc_datetime().timestamp()
        if  set_crosses_horizons[0]:
            set = set_times[0].utc_datetime().timestamp()

        #transit
        transit_times = skyfield.almanac.find_transits(self.observer, orb, ts_day_start, ts_day_end)
        transit = transit_times[0].utc_datetime().timestamp()

        return rise, set, transit

    def get_sunrise_sunset_transit_daylight(self, ts, day_start: datetime) -> Tuple[Optional[datetime.timestamp], Optional[datetime.timestamp], datetime.timestamp, float]:
        sunrise = None
        sunset = None
        transit = None

        ts_day_start = ts.from_datetime(day_start)
        ts_day_end = ts.from_datetime(day_start + timedelta(days=1))

        # Sunrise/Sunset/SunTransit/daySunshineDur
        sunrise_times, sunrise_crosses_horizons = skyfield.almanac.find_risings(self.observer, self.sun, ts_day_start, ts_day_end)
        sunset_times, sunset_crosses_horizons = skyfield.almanac.find_settings(self.observer, self.sun, ts_day_start, ts_day_end)
        if  sunrise_crosses_horizons[0]:
            sunrise = sunrise_times[0].utc_datetime().timestamp()
        if  sunset_crosses_horizons[0]:
            sunset = sunset_times[0].utc_datetime().timestamp()
        if  sunrise_crosses_horizons[0] and sunset_crosses_horizons[0]:
            daylight = sunset - sunrise
        elif not sunrise_crosses_horizons[0] and not sunset_crosses_horizons[0]:
            # The sun neither rose nor set.
            alt, _, _ = self.observer.at(sunrise_times[0]).observe(self.sun).apparent().altaz()
            if alt.degrees > -0.833333:
                # 24 hours of daylight
                daylight = 86400
            else:
                # 24 hours of darkness
                daylight = 0
        elif sunrise_crosses_horizons[0] and not sunset_crosses_horizons[0]:
            # The sun rose, but never set.
            daylight = ts_day_end.timestamp() - sunrise
        else:
            # The never rose, but it did set.
            daylight = sunset - ts_day_start.timestamp()

        transit_times = skyfield.almanac.find_transits(self.observer, self.sun, ts_day_start, ts_day_end)
        transit = transit_times[0].utc_datetime().timestamp()

        return sunrise, sunset, transit, daylight

    def insert_fields(self, pkt: Dict[str, Any]) -> None:
        pkt_time: int = to_int(pkt['dateTime'])
        pkt_datetime  = datetime.fromtimestamp(pkt_time, timezone.utc)

        # Create a skyfield timescale with pkt_datetime.
        ts = skyfield.api.load.timescale()
        ts_pkt_time = ts.from_datetime(pkt_datetime)

        metric_pkt = weewx.units.StdUnitConverters[weewx.METRIC].convertDict(pkt)
        if 'outTemp' in metric_pkt:
            tempC = metric_pkt['outTemp']
        if 'barometer' in metric_pkt:
            pressureMbar = metric_pkt['barometer']

        sun_az, sun_alt, sun_ra, sun_dec= self.get_az_alt_ra_dec(ts, self.sun, pkt_datetime, tempC, pressureMbar)
        pkt['SunAzimuth'] = sun_az
        pkt['SunAltitude'] = sun_alt
        pkt['SunRightAscension'] = sun_ra
        pkt['SunDeclination'] = sun_dec

        moon_az, moon_alt, moon_ra, moon_dec= self.get_az_alt_ra_dec(ts, self.moon, pkt_datetime, tempC, pressureMbar)
        pkt['MoonAzimuth'] = moon_az
        pkt['MoonAltitude'] = moon_alt
        pkt['MoonRightAscension'] = moon_ra
        pkt['MoonDeclination'] = moon_dec

        moon_phase_degrees, percent_illumination = self.get_moon_phase(ts, pkt_datetime)
        pkt['MoonFullness'] = percent_illumination
        index = self.get_moon_phase_index(moon_phase_degrees)
        pkt['MoonPhase'] = self.moon_phases[index]

        # Convert astrological units to kilometers or miles
        if pkt['usUnits'] == weewx.METRIC:
            multiplier = 1.496e+8
        else:
            multiplier = 9.296e+7 

        pkt['EarthSunDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.sun) * multiplier
        pkt['EarthMoonDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.moon) * multiplier

        pkt['EarthMercuryDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.mercury) * multiplier
        pkt['EarthVenusDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.venus) * multiplier
        pkt['EarthMarsDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.mars) * multiplier
        pkt['EarthJupiterDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.jupiter) * multiplier
        pkt['EarthSaturnDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.saturn) * multiplier
        pkt['EarthUranusDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.uranus) * multiplier
        pkt['EarthNeptuneDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.neptune) * multiplier
        pkt['EarthPlutoDistance'] = Celestial.distance_from_earth(ts_pkt_time, self.earth, self.pluto) * multiplier

        # Sun/Moon rise/set/transit, etc. are always reported for the curent day (i.e., the event may have already passed.
        # We also don't want Equinox/Solstice/NewMoon/FullMoon to disappear as soon as it is hit (keep it around for the day)
        # As such, use the beginning of day for the observer, and recompute.
        pkt_now = datetime.fromtimestamp(pkt_time)
        local_day_start = datetime.strptime(pkt_now.strftime('%Y-%m-%d'), '%Y-%m-%d')
        day_start  = datetime.fromtimestamp(local_day_start.timestamp(), timezone.utc)

        sunrise, sunset, transit, daylight = self.get_sunrise_sunset_transit_daylight(ts, day_start)
        if sunrise is not None:
            pkt['Sunrise'] = sunrise
        if  sunset is not None:
            pkt['Sunset'] = sunset
        pkt['daySunshineDur'] = daylight
        pkt['SunTransit'] = transit

        # Moonrise/Moonset/MoonTransit
        moonrise, moonset, moontransit = self.get_rise_set_transit(ts, self.moon, day_start)
        if moonrise is not None:
            pkt['Moonrise'] = moonrise
        if moonset is not None:
            pkt['Moonset'] = moonset
        pkt['MoonTransit'] = moontransit

        next_equinox, next_solstice = self.get_next_equinox_and_solstice(ts, day_start)
        pkt['NextEquinox']  = next_equinox
        pkt['NextSolstice'] = next_solstice


        fullmoon, newmoon = self.get_next_fullmoon_and_newmoon(ts, day_start)
        if fullmoon is not None:
            pkt['NextFullMoon']  = fullmoon
        if newmoon is not None:
            pkt['NextNewMoon'] = newmoon

        f = skyfield.almanac.dark_twilight_day(self.planets, self.bluffton)
        times, events = skyfield.almanac.find_discrete(ts.from_datetime(day_start), ts.from_datetime(day_start + timedelta(days=1)), f)
        astronomical_encountered = False
        nautical_encountered = False
        civil_encountered = False
        for event, time in zip(events, times):
            match event:
                case 0:
                    pkt['AstronomicalTwilightEnd'] = time.utc_datetime().timestamp()
                case 1:
                    if not astronomical_encountered:
                        pkt['AstronomicalTwilightStart'] = time.utc_datetime().timestamp()
                        astronomical_encountered = True
                    else:
                        pkt['NauticalTwilightEnd'] = time.utc_datetime().timestamp()
                case 2:
                    if not nautical_encountered:
                        pkt['NauticalTwilightStart'] = time.utc_datetime().timestamp()
                        nautical_encountered = True
                    else:
                        pkt['CivilTwilightEnd'] = time.utc_datetime().timestamp()
                case 3:
                    if not civil_encountered:
                        pkt['CivilTwilightStart'] = time.utc_datetime().timestamp()
                        civil_encountered = True

        # We need yesterday's sunshine duration
        yesterday_start = day_start - timedelta(days=1)
        _, _, _, yesterday_daylight = self.get_sunrise_sunset_transit_daylight(ts, yesterday_start)
        pkt['yesterdaySunshineDur'] = yesterday_daylight

        # Tomorrow sunrise, sunset, daytime
        tomorrow_start = day_start + timedelta(days=1)
        tomorrow_sunrise, tomorrow_sunset, _, _ = self.get_sunrise_sunset_transit_daylight(ts, tomorrow_start)
        if tomorrow_sunrise is not None:
            pkt['tomorrowSunrise'] = tomorrow_sunrise
        if  tomorrow_sunset is not None:
            pkt['tomorrowSunset'] = tomorrow_sunset

    def new_loop(self, event):
        if self.first_time:
            if self.perform_skyfield_init():
                self.first_time = False
            else:
                return
        pkt: Dict[str, Any] = event.packet
        assert event.event_type == weewx.NEW_LOOP_PACKET
        log.debug(pkt)
        self.insert_fields(pkt)
