"""
celestial.py

Copyright (C)2022-2023 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Celestial is a WeeWX service that generates Celestial observations
that are inserted into the loop packet.
"""

import logging
import math
import sys

from datetime import datetime
from datetime import timezone
from typing import Any, Dict

import ephem
import weeutil.Moon
import weewx

from weeutil.weeutil import to_bool
from weeutil.weeutil import to_int
from weewx.engine import StdService

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '1.0'

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

        self.moon_phases = weeutil.Moon.moon_phases
        if 'Defaults' in config_dict['StdReport']:
            if 'Almanac' in config_dict['StdReport']['Defaults']:
                if 'moon_phases' in config_dict['StdReport']['Defaults']['Almanac']:
                    self.moon_phases = config_dict['StdReport']['Defaults']['Almanac']['moon_phases']

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

        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop)

    def insert_fields(self, pkt: Dict[str, Any]) -> None:
        pkt_time: int = to_int(pkt['dateTime'])
        pkt_datetime  = datetime.fromtimestamp(pkt_time, timezone.utc)

        obs = ephem.Observer()
        obs.lat, obs.lon = math.radians(self.latitude), math.radians(self.longitude)
        obs.elevation = self.altitude
        metric_pkt = weewx.units.StdUnitConverters[weewx.METRIC].convertDict(pkt)
        if 'outTemp' in metric_pkt:
            obs.temp = metric_pkt['outTemp']
        if 'barometer' in metric_pkt:
            obs.pressure = metric_pkt['barometer']
        obs.date = pkt_datetime
        sun  = ephem.Sun()
        moon = ephem.Moon()
        mercury = ephem.Mercury()
        venus = ephem.Venus()
        mars = ephem.Mars()
        jupiter = ephem.Jupiter()
        saturn = ephem.Saturn()
        uranus = ephem.Uranus()
        neptune = ephem.Neptune()
        pluto = ephem.Pluto()

        sun.compute(obs)
        moon.compute(obs)
        mercury.compute(obs)
        venus.compute(obs)
        mars.compute(obs)
        jupiter.compute(obs)
        saturn.compute(obs)
        uranus.compute(obs)
        neptune.compute(obs)
        pluto.compute(obs)

        pkt['SunAzimuth'] = math.degrees(sun.az)
        pkt['SunAltitude'] = math.degrees(sun.alt)
        pkt['SunRightAscension'] = math.degrees(sun.ra)
        pkt['SunDeclination'] = math.degrees(sun.dec)
        pkt['MoonAzimuth'] = math.degrees(moon.az)
        pkt['MoonAltitude'] = math.degrees(moon.alt)
        pkt['MoonRightAscension'] = math.degrees(moon.ra)
        pkt['MoonDeclination'] = math.degrees(moon.dec)
        pkt['MoonFullness'] = 100.0 * moon.moon_phase
        index, _ = weeutil.Moon.moon_phase_ts(pkt_time)
        pkt['MoonPhase'] = self.moon_phases[index]

        # Convert astrological units to kilometers or miles
        if pkt['usUnits'] == weewx.METRIC:
            multiplier = 1.496e+8
        else:
            multiplier = 9.296e+7 
        pkt['EarthSunDistance'] = sun.earth_distance * multiplier
        pkt['EarthMoonDistance'] = moon.earth_distance * multiplier
        pkt['EarthMercuryDistance'] = mercury.earth_distance * multiplier
        pkt['EarthVenusDistance'] = venus.earth_distance * multiplier
        pkt['EarthMarsDistance'] = mars.earth_distance * multiplier
        pkt['EarthJupiterDistance'] = jupiter.earth_distance * multiplier
        pkt['EarthSaturnDistance'] = saturn.earth_distance * multiplier
        pkt['EarthUranusDistance'] = uranus.earth_distance * multiplier
        pkt['EarthNeptuneDistance'] = neptune.earth_distance * multiplier
        pkt['EarthPlutoDistance'] = pluto.earth_distance * multiplier

        # Sun/Moon rise/set/transit, etc. are always reported for the curent day (i.e., the event may have already passed.
        # We also don't want Equinox/Solstice/NewMoon/FullMoon to disappear as soon as it is hit (keep it around for the day)
        # As such, use the beginning of day for the observer, and recompute.
        pkt_now = datetime.fromtimestamp(pkt_time)
        local_day_start = datetime.strptime(pkt_now.strftime('%Y-%m-%d'), '%Y-%m-%d')
        day_start  = datetime.fromtimestamp(local_day_start.timestamp(), timezone.utc)
        obs.date = day_start

        pkt['NextEquinox']  = ephem.next_equinox( day_start).datetime().replace(tzinfo=timezone.utc).timestamp()
        pkt['NextSolstice'] = ephem.next_solstice(day_start).datetime().replace(tzinfo=timezone.utc).timestamp()

        pkt['NextNewMoon']  = ephem.next_new_moon( day_start).datetime().replace(tzinfo=timezone.utc).timestamp()
        pkt['NextFullMoon'] = ephem.next_full_moon(day_start).datetime().replace(tzinfo=timezone.utc).timestamp()

        try:
            pkt['Sunrise'] = obs.next_rising(sun).datetime().replace(tzinfo=timezone.utc).timestamp()
            pkt['SunTransit'] = obs.next_transit(sun).datetime().replace(tzinfo=timezone.utc).timestamp()
            pkt['Sunset'] = obs.next_setting(sun).datetime().replace(tzinfo=timezone.utc).timestamp()
            daylight = pkt['Sunset'] - pkt['Sunrise']
        except ephem.AlwaysUpError:
            daylight = 86400
        except ephem.NeverUpError:
            daylight = 0
        pkt['daySunshineDur'] = daylight
        try:
            pkt['Moonrise'] = obs.next_rising(moon).datetime().replace(tzinfo=timezone.utc).timestamp()
            pkt['MoonTransit'] = obs.next_transit(moon).datetime().replace(tzinfo=timezone.utc).timestamp()
            pkt['Moonset'] = obs.next_setting(moon).datetime().replace(tzinfo=timezone.utc).timestamp()
        except (ephem.AlwaysUpError, ephem.NeverUpError):
            pass
        # Now we need to mess with altitudes to compute twilight start/ends
        obs.horizon = '-18'
        pkt['AstronomicalTwilightStart'] = obs.next_rising(sun, use_center=True).datetime().replace(tzinfo=timezone.utc).timestamp()
        pkt['AstronomicalTwilightEnd'] = obs.next_setting(sun, use_center=True).datetime().replace(tzinfo=timezone.utc).timestamp()
        obs.horizon = '-12'
        pkt['NauticalTwilightStart'] = obs.next_rising(sun, use_center=True).datetime().replace(tzinfo=timezone.utc).timestamp()
        pkt['NauticalTwilightEnd'] = obs.next_setting(sun, use_center=True).datetime().replace(tzinfo=timezone.utc).timestamp()
        obs.horizon = '-6'
        pkt['CivilTwilightStart'] = obs.next_rising(sun, use_center=True).datetime().replace(tzinfo=timezone.utc).timestamp()
        pkt['CivilTwilightEnd'] = obs.next_setting(sun, use_center=True).datetime().replace(tzinfo=timezone.utc).timestamp()
        # Lastly, we need yesterday's sunshine duration
        obs.horizon = '0'
        yesterday_start  = datetime.fromtimestamp(local_day_start.timestamp() - 86400, timezone.utc)
        obs.date = yesterday_start
        try:
            yesterday_sunrise = obs.next_rising(sun).datetime().replace(tzinfo=timezone.utc).timestamp()
            yesterday_sunset = obs.next_setting(sun).datetime().replace(tzinfo=timezone.utc).timestamp()
            yesterday_daylight = yesterday_sunset - yesterday_sunrise
        except ephem.AlwaysUpError:
            yesterday_daylight = 86400
        except ephem.NeverUpError:
            yesterday_daylight = 0
        pkt['yesterdaySunshineDur'] = yesterday_daylight
        tomorrow_start  = datetime.fromtimestamp(local_day_start.timestamp() + 86400, timezone.utc)
        obs.date = tomorrow_start
        try:
            tomorrow_sunrise = obs.next_rising(sun).datetime().replace(tzinfo=timezone.utc).timestamp()
            tomorrow_sunset = obs.next_setting(sun).datetime().replace(tzinfo=timezone.utc).timestamp()
            tomorrow_daylight = tomorrow_sunset - tomorrow_sunrise
        except ephem.AlwaysUpError:
            tomorrow_daylight = 86400
        except ephem.NeverUpError:
            tomorrow_daylight = 0
        pkt['tomorrowSunrise'] = tomorrow_sunrise
        pkt['tomorrowSunset'] = tomorrow_sunset
        # Perhaps offer tomrrow daylight at some point.

    def new_loop(self, event):
        pkt: Dict[str, Any] = event.packet
        assert event.event_type == weewx.NEW_LOOP_PACKET
        log.debug(pkt)
        self.insert_fields(pkt)
