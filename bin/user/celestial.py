"""
celestial.py

Copyright (C)2020 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Celestial is a WeeWX service that generates Celestial observations
that are inserted into the loop packet.
"""

import logging
import math
import sys

from datetime import datetime
from typing import Any, Dict

import ephem
import weewx

from weeutil.weeutil import to_bool
from weeutil.weeutil import to_float
from weeutil.weeutil import to_int
from weewx.engine import StdService

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '0.1'

if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 7):
    raise weewx.UnsupportedFeature(
        "weewx-celestial requires Python 3.7 or later, found %s.%s" % (sys.version_info[0], sys.version_info[1]))

if weewx.__version__ < "4":
    raise weewx.UnsupportedFeature(
        "weewx-celestial requires WeeWX, found %s" % weewx.__version__)

# Set up celestial observation type.
weewx.units.obs_group_dict['EarthSunDistance']   = 'group_distance'
weewx.units.obs_group_dict['EarthMoonDistance']  = 'group_distance'
weewx.units.obs_group_dict['SunAzimuth']         = 'group_direction'
weewx.units.obs_group_dict['SunAltitude']        = 'group_direction'
weewx.units.obs_group_dict['SunRightAscension']  = 'group_direction'
weewx.units.obs_group_dict['SunDeclination']     = 'group_direction'
weewx.units.obs_group_dict['MoonAzimuth']        = 'group_direction'
weewx.units.obs_group_dict['MoonAltitude']       = 'group_direction'
weewx.units.obs_group_dict['MoonRightAscension'] = 'group_direction'
weewx.units.obs_group_dict['MoonDeclination']    = 'group_direction'

distance_types = [ 'EarthSunDistance', 'EarthMoonDistance' ]

distance_types = [ 'SunAzimuth', 'SunAltitude', 'SunRightAscension', 'SunDeclination',
                   'MoonAzimuth', 'MoonAltitude', 'MoonRightAscension', 'MoonDeclination' ]

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

        latitude = config_dict['Station'].get('latitude', None)
        longitude = config_dict['Station'].get('longitude', None)

        if latitude is None or longitude is None:
            log.error("Could not determine station's latitude and longitude.")
            return

        # convert lat/lon to floats
        self.latitude = to_float(latitude)
        self.longitude = to_float(longitude)

        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop)

    def insert_fields(self, pkt: Dict[str, Any]) -> None:
        pkt_time: int       = to_int(pkt['dateTime'])

        obs = ephem.Observer()
        obs.lat, obs.lon = math.radians(self.latitude), math.radians(self.longitude)
        obs.date = datetime.utcfromtimestamp(pkt_time)
        sun  = ephem.Sun()
        moon = ephem.Moon()
        sun.compute(obs)
        moon.compute(obs)

        pkt['SunAzimuth'] = math.degrees(sun.az)
        pkt['SunAltitude'] = math.degrees(sun.alt)
        pkt['SunRightAscension'] = math.degrees(sun.ra)
        pkt['SunDeclination'] = math.degrees(sun.dec)
        pkt['MoonAzimuth'] = math.degrees(moon.az)
        pkt['MoonAltitude'] = math.degrees(moon.alt)
        pkt['MoonRightAscension'] = math.degrees(moon.ra)
        pkt['MoonDeclination'] = math.degrees(moon.dec)

        if pkt['usUnits'] == weewx.METRIC:
            # Convert astrological units to kilometers
            pkt['EarthSunDistance'] = sun.earth_distance * 1.496e+8
            pkt['EarthMoonDistance'] = moon.earth_distance * 1.496e+8
        else:
            # Convert astrological units to miles
            pkt['EarthSunDistance'] = sun.earth_distance * 9.296e+7
            pkt['EarthMoonDistance'] = moon.earth_distance * 9.296e+7

    def new_loop(self, event):
        pkt: Dict[str, Any] = event.packet
        assert event.event_type == weewx.NEW_LOOP_PACKET
        log.debug(pkt)
        self.insert_fields(pkt)
