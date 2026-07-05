"""
celestial.py

Copyright (C)2022-2025 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Celestial is a WeeWX service that generates Celestial observations
that are inserted into the loop packet.

With WeeWX 5.2 or later, Celestial also registers a Skyfield based
almanac (SkyfieldAlmanacType), so that report tags such as
$almanac.sunrise are computed with Skyfield rather than WeeWX's
built-in PyEphem/weeutil almanac.
"""

import logging
import math
import os
import re
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
import skyfield.magnitudelib
import skyfield.timelib
import weeutil.Moon
import weeutil.weeutil
import weewx
import weewx.almanac
import weewx.units

from weeutil.weeutil import to_bool
from weeutil.weeutil import to_int
from weewx.engine import StdEngine
from weewx.engine import StdService
from weewx.units import ValueHelper
from weewx.units import ValueTuple

# get a logger object
log = logging.getLogger(__name__)

CELESTIAL_VERSION = '3.0'

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
    'nextNewMoon'              : 'group_time',
    'nextFullMoon'             : 'group_time',
    'moonrise'                 : 'group_time',
    'moonTransit'              : 'group_time',
    'moonset'                  : 'group_time',
}

# Loop field names used before 3.0, mapped to their replacements.
# DEPRECATED: In 3.0, every loop packet carries each value under BOTH names,
# so existing [LoopData] fields lists and skins keep working.  The old names
# will be REMOVED in 4.0; switch skins and weewx.conf to the new names.
# (Note that daySunshineDur/yesterdaySunshineDur were renamed to
# daylightDur/yesterdayDaylightDur because they measure the time the sun is
# above the horizon, not "sunshine duration" in the meteorological sense of
# measured bright sunshine.)
DEPRECATED_FIELD_MAP: Dict[str, str] = {
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

# Set up celestial observation types (both the new and, until 4.0, the
# deprecated names).
for _obs_name, _obs_group in OBS_GROUPS.items():
    weewx.units.obs_group_dict[_obs_name] = _obs_group
for _old_name, _new_name in DEPRECATED_FIELD_MAP.items():
    weewx.units.obs_group_dict[_old_name] = OBS_GROUPS[_new_name]

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
        replace_builtin_almanac = to_bool(celestial_config_dict.get('replace_builtin_almanac', True))
        stars = to_bool(celestial_config_dict.get('stars', True))

        user_root, moon_phases, altitude_m, latitude, longitude = Sky.get_weewx_config_info(config_dict)
        if latitude is None or longitude is None:
            log.error("Could not determine station's latitude and longitude.")
            return
        if altitude_m is None:
            log.error("Could not determine station's altitude.")
            return

        log.info("update_rate_secs       : %d" % update_rate_secs)
        log.info("replace_builtin_almanac: %r" % replace_builtin_almanac)
        log.info("stars                  : %r" % stars)
        log.info("user_root              : %s" % user_root)
        log.info("moon_phases            : %r" % moon_phases)
        log.info("altitude_m             : %f" % altitude_m)
        log.info("latitude               : %f" % latitude)
        log.info("longitude              : %f" % longitude)

        self.sky = Sky(update_rate_secs, user_root, moon_phases, altitude_m, latitude, longitude, load_stars=stars)
        if self.sky.is_valid():
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop)
            if replace_builtin_almanac:
                if register_almanac(self.sky):
                    log.info('Skyfield almanac registered; reports will use Skyfield for almanac computations.')

    def new_loop(self, event):
        try:
            pkt: Dict[str, Any] = event.packet
            assert event.event_type == weewx.NEW_LOOP_PACKET
            log.debug(pkt)
            self.sky.insert_fields(pkt)
        except Exception as e:
            log.error('new_loop: %s.' % e)

# Named stars available as report almanac tags (e.g., $almanac.rigel.rise)
# unless disabled (stars = false in [Celestial]).  Maps the tag name to the
# star's Hipparcos catalog number.  The names are the IAU Catalog of Star
# Names (the Working Group on Star Names' IAU-CSN list, 2022 edition; every
# entry with a Hipparcos number), plus PyEphem's star catalog names for
# backward compatibility (a few of which are legacy spellings of the same
# stars: albereo, alcaid, sirrah, etc.).  Multi-word names use underscores
# and diacritics are dropped, since a report tag must be an identifier
# ($almanac.barnards_star, $almanac.kaus_australis).  The stars themselves
# are read from celestial_stars.dat, an excerpt of the Hipparcos Catalogue
# (ESA SP-1200, 1997) that ships with this extension.  Any other Hipparcos
# star can be addressed by number: $almanac.hip_57939.
NAMED_STARS: Dict[str, int] = {
    'acamar'           : 13847,
    'achernar'         : 7588,
    'achird'           : 3821,
    'acrab'            : 78820,
    'acrux'            : 60718,
    'acubens'          : 44066,
    'adara'            : 33579,
    'adhafera'         : 50335,
    'adhara'           : 33579,
    'adhil'            : 6411,
    'agena'            : 68702,
    'ain'              : 20889,
    'ainalrami'        : 92761,
    'aladfar'          : 94481,
    'alasia'           : 90004,
    'albaldah'         : 94141,
    'albali'           : 102618,
    'albereo'          : 95947,
    'albireo'          : 95947,
    'alcaid'           : 67301,
    'alchiba'          : 59199,
    'alcor'            : 65477,
    'alcyone'          : 17702,
    'aldebaran'        : 21421,
    'alderamin'        : 105199,
    'aldhanab'         : 108085,
    'aldhibah'         : 83895,
    'aldulfin'         : 101421,
    'alfirk'           : 106032,
    'algedi'           : 100064,
    'algenib'          : 1067,
    'algieba'          : 50583,
    'algol'            : 14576,
    'algorab'          : 60965,
    'alhena'           : 31681,
    'alioth'           : 62956,
    'aljanah'          : 102488,
    'alkaid'           : 67301,
    'alkalurops'       : 75411,
    'alkaphrah'        : 44471,
    'alkarab'          : 115623,
    'alkes'            : 53740,
    'almaaz'           : 23416,
    'almach'           : 9640,
    'alnair'           : 109268,
    'alnasl'           : 88635,
    'alnilam'          : 26311,
    'alnitak'          : 26727,
    'alniyat'          : 80112,
    'alphard'          : 46390,
    'alphecca'         : 76267,
    'alpheratz'        : 677,
    'alpherg'          : 7097,
    'alrakis'          : 83608,
    'alrescha'         : 9487,
    'alruba'           : 86782,
    'alsafi'           : 96100,
    'alsciaukat'       : 41075,
    'alsephina'        : 42913,
    'alshain'          : 98036,
    'alshat'           : 100310,
    'altair'           : 97649,
    'altais'           : 94376,
    'alterf'           : 46750,
    'aludra'           : 35904,
    'alula_australis'  : 55203,
    'alula_borealis'   : 55219,
    'alya'             : 92946,
    'alzirr'           : 32362,
    'amadioha'         : 29550,
    'ancha'            : 110003,
    'angetenar'        : 13288,
    'aniara'           : 57820,
    'ankaa'            : 2081,
    'anser'            : 95771,
    'antares'          : 80763,
    'arcalis'          : 72845,
    'arcturus'         : 69673,
    'arkab_posterior'  : 95294,
    'arkab_prior'      : 95241,
    'arneb'            : 25985,
    'ascella'          : 93506,
    'asellus_australis': 42911,
    'asellus_borealis' : 42806,
    'ashlesha'         : 43109,
    'aspidiske'        : 45556,
    'asterope'         : 17579,
    'athebyne'         : 80331,
    'atik'             : 17448,
    'atlas'            : 17847,
    'atria'            : 82273,
    'avior'            : 41037,
    'axolotl'          : 118319,
    'ayeyarwady'       : 13993,
    'azelfafage'       : 107136,
    'azha'             : 13701,
    'azmidi'           : 38170,
    'baekdu'           : 73136,
    'barnards_star'    : 87937,
    'baten_kaitos'     : 8645,
    'beemim'           : 20535,
    'beid'             : 19587,
    'belel'            : 95124,
    'belenos'          : 6643,
    'bellatrix'        : 25336,
    'betelgeuse'       : 27989,
    'bharani'          : 13209,
    'bibha'            : 48711,
    'biham'            : 109427,
    'bosona'           : 107251,
    'botein'           : 14838,
    'brachium'         : 73714,
    'bubup'            : 26380,
    'buna'             : 12191,
    'bunda'            : 106786,
    'canopus'          : 30438,
    'capella'          : 24608,
    'caph'             : 746,
    'castor'           : 36850,
    'castula'          : 4422,
    'cebalrai'         : 86742,
    'ceibo'            : 37284,
    'celaeno'          : 17489,
    'cervantes'        : 86796,
    'chalawan'         : 53721,
    'chamukuy'         : 20894,
    'chara'            : 61317,
    'chechia'          : 99894,
    'chertan'          : 54879,
    'citadelle'        : 1547,
    'citala'           : 33719,
    'cocibolca'        : 3479,
    'copernicus'       : 43587,
    'cor_caroli'       : 63125,
    'cujam'            : 80463,
    'cursa'            : 23875,
    'dabih'            : 100345,
    'dalim'            : 14879,
    'deneb'            : 102098,
    'deneb_algedi'     : 107556,
    'denebola'         : 57632,
    'diadem'           : 64241,
    'dingolay'         : 54158,
    'diphda'           : 3419,
    'dofida'           : 66047,
    'dschubba'         : 78401,
    'dubhe'            : 54061,
    'dziban'           : 86614,
    'ebla'             : 114322,
    'edasich'          : 75458,
    'electra'          : 17499,
    'elgafar'          : 70755,
    'elkurud'          : 29034,
    'elnath'           : 25428,
    'eltanin'          : 87833,
    'emiw'             : 5529,
    'enif'             : 107315,
    'errai'            : 116727,
    'etamin'           : 87833,
    'fafnir'           : 90344,
    'fang'             : 78265,
    'fawaris'          : 97165,
    'felis'            : 48615,
    'felixvarela'      : 2247,
    'flegetonte'       : 57370,
    'fomalhaut'        : 113368,
    'formalhaut'       : 113368,
    'formosa'          : 56508,
    'fulu'             : 2920,
    'fumalsamakah'     : 113889,
    'funi'             : 61177,
    'furud'            : 30122,
    'fuyue'            : 87261,
    'gacrux'           : 61084,
    'gakyid'           : 42446,
    'giausar'          : 56211,
    'gienah'           : 59803,
    'gienah_corvi'     : 59803,
    'ginan'            : 60260,
    'gomeisa'          : 36188,
    'grumium'          : 87585,
    'gudja'            : 77450,
    'gumala'           : 94645,
    'guniibuu'         : 84405,
    'hadar'            : 68702,
    'haedus'           : 23767,
    'hamal'            : 9884,
    'hassaleh'         : 23015,
    'hatysa'           : 26241,
    'helvetios'        : 113357,
    'heze'             : 66249,
    'hoggar'           : 21109,
    'homam'            : 112029,
    'hunahpu'          : 55174,
    'hunor'            : 80076,
    'iklil'            : 78104,
    'illyrian'         : 47087,
    'imai'             : 59747,
    'inquill'          : 84787,
    'intan'            : 15578,
    'intercrus'        : 46471,
    'itonda'           : 108375,
    'izar'             : 72105,
    'jabbah'           : 79374,
    'jishui'           : 37265,
    'kaffaljidhma'     : 12706,
    'kalausi'          : 47202,
    'kamuy'            : 79219,
    'kang'             : 69427,
    'karaka'           : 76351,
    'kaus_australis'   : 90185,
    'kaus_borealis'    : 90496,
    'kaus_media'       : 89931,
    'kaveh'            : 92895,
    'keid'             : 19849,
    'khambalia'        : 69974,
    'kitalpha'         : 104987,
    'kochab'           : 72607,
    'koeia'            : 12961,
    'kornephoros'      : 80816,
    'kraz'             : 61359,
    'kurhah'           : 108917,
    'la_superba'       : 62223,
    'larawag'          : 82396,
    'lesath'           : 85696,
    'libertas'         : 97938,
    'liesma'           : 66192,
    'lilii_borea'      : 13061,
    'lionrock'         : 110813,
    'lucilinburhuc'    : 30860,
    'lusitania'        : 30905,
    'maasym'           : 85693,
    'macondo'          : 52521,
    'mago'             : 24003,
    'mahasim'          : 28380,
    'mahsati'          : 82651,
    'maia'             : 17573,
    'marfik'           : 80883,
    'markab'           : 113963,
    'markeb'           : 45941,
    'marsic'           : 79043,
    'matar'            : 112158,
    'mebsuta'          : 32246,
    'megrez'           : 59774,
    'meissa'           : 26207,
    'mekbuda'          : 34088,
    'meleph'           : 42556,
    'menkalinan'       : 28360,
    'menkar'           : 14135,
    'menkent'          : 68933,
    'menkib'           : 18614,
    'merak'            : 53910,
    'merga'            : 72487,
    'meridiana'        : 94114,
    'merope'           : 17608,
    'mesarthim'        : 8832,
    'miaplacidus'      : 45238,
    'mimosa'           : 62434,
    'minchir'          : 42402,
    'minelauva'        : 63090,
    'minkar'           : 59316,
    'mintaka'          : 25930,
    'mira'             : 10826,
    'mirach'           : 5447,
    'miram'            : 13268,
    'mirfak'           : 15863,
    'mirzam'           : 30324,
    'misam'            : 14668,
    'mizar'            : 65378,
    'monch'            : 72339,
    'mothallah'        : 8796,
    'mouhoun'          : 22491,
    'muliphein'        : 34045,
    'muphrid'          : 67927,
    'muscida'          : 41704,
    'musica'           : 103527,
    'nahn'             : 44946,
    'naos'             : 39429,
    'nashira'          : 106985,
    'nasti'            : 40687,
    'natasha'          : 48235,
    'nekkar'           : 73555,
    'nembus'           : 7607,
    'nenque'           : 5054,
    'nervia'           : 32916,
    'nganurganity'     : 33856,
    'nihal'            : 25606,
    'nikawiy'          : 74961,
    'nosaxa'           : 31895,
    'nunki'            : 92855,
    'nusakan'          : 75695,
    'nushagak'         : 13192,
    'ogma'             : 80838,
    'okab'             : 93747,
    'paikauhale'       : 81266,
    'peacock'          : 100751,
    'phact'            : 26634,
    'phecda'           : 58001,
    'pherkad'          : 75097,
    'phoenicia'        : 99711,
    'piautos'          : 40881,
    'pincoya'          : 88414,
    'pipirima'         : 82545,
    'pleione'          : 17851,
    'poerava'          : 116084,
    'polaris'          : 11767,
    'polaris_australis': 104382,
    'polis'            : 89341,
    'pollux'           : 37826,
    'porrima'          : 61941,
    'praecipua'        : 53229,
    'prima_hyadum'     : 20205,
    'procyon'          : 37279,
    'propus'           : 29655,
    'proxima_centauri' : 70890,
    'ran'              : 16537,
    'rana'             : 17378,
    'rapeto'           : 83547,
    'rasalas'          : 48455,
    'rasalgethi'       : 84345,
    'rasalhague'       : 86032,
    'rastaban'         : 85670,
    'regulus'          : 49669,
    'revati'           : 5737,
    'rigel'            : 24436,
    'rigil_kentaurus'  : 71683,
    'rosaliadecastro'  : 81022,
    'rotanev'          : 101769,
    'ruchbah'          : 6686,
    'rukbat'           : 95347,
    'sabik'            : 84012,
    'saclateni'        : 23453,
    'sadachbia'        : 110395,
    'sadalbari'        : 112748,
    'sadalmelik'       : 109074,
    'sadalsuud'        : 106278,
    'sadr'             : 100453,
    'sagarmatha'       : 56572,
    'saiph'            : 27366,
    'salm'             : 115250,
    'samaya'           : 106824,
    'sargas'           : 86228,
    'sarin'            : 84379,
    'sceptrum'         : 21594,
    'scheat'           : 113881,
    'schedar'          : 3179,
    'secunda_hyadum'   : 20455,
    'segin'            : 8886,
    'seginus'          : 71075,
    'sham'             : 96757,
    'shama'            : 55664,
    'sharjah'          : 79431,
    'shaula'           : 85927,
    'sheliak'          : 92420,
    'sheratan'         : 8903,
    'sika'             : 95262,
    'sirius'           : 32349,
    'sirrah'           : 677,
    'situla'           : 111710,
    'skat'             : 113136,
    'solaris'          : 104780,
    'spica'            : 65474,
    'stribor'          : 43674,
    'sualocin'         : 101958,
    'subra'            : 47508,
    'suhail'           : 44816,
    'sulafat'          : 93194,
    'syrma'            : 69701,
    'tabit'            : 22449,
    'taiyangshou'      : 57399,
    'taiyi'            : 63076,
    'talitha'          : 44127,
    'tania_australis'  : 50801,
    'tania_borealis'   : 50372,
    'tapecue'          : 38041,
    'tarazed'          : 97278,
    'tarf'             : 40526,
    'taygeta'          : 17531,
    'tegmine'          : 40167,
    'tejat'            : 30343,
    'terebellum'       : 98066,
    'theemin'          : 21393,
    'thuban'           : 68756,
    'tiaki'            : 112122,
    'tianguan'         : 26451,
    'tianyi'           : 62423,
    'timir'            : 80687,
    'titawin'          : 7513,
    'toliman'          : 71681,
    'tonatiuh'         : 58952,
    'torcular'         : 8198,
    'tupa'             : 60644,
    'tupi'             : 17096,
    'tureis'           : 39757,
    'ukdah'            : 47431,
    'uklun'            : 57291,
    'unukalhai'        : 77070,
    'uruk'             : 96078,
    'vega'             : 91262,
    'veritate'         : 116076,
    'vindemiatrix'     : 63608,
    'wasat'            : 35550,
    'wazn'             : 27628,
    'wezen'            : 34444,
    'wurren'           : 5348,
    'xamidimura'       : 82514,
    'xihe'             : 91852,
    'xuange'           : 69732,
    'yed_posterior'    : 79882,
    'yed_prior'        : 79593,
    'yildun'           : 85822,
    'zaniah'           : 60129,
    'zaurak'           : 18543,
    'zavijava'         : 57757,
    'zhang'            : 48356,
    'zibal'            : 15197,
    'zosma'            : 54872,
    'zubenelgenubi'    : 72622,
    'zubenelhakrabi'   : 76333,
    'zubeneschamali'   : 74785,
}

# An excerpt of the Hipparcos Catalogue containing the stars in NAMED_STARS.
# It is installed alongside celestial.py (like the de421.bsp ephemeris), and
# its data lines are unmodified hip_main.dat records, so a full hip_main.dat
# works in its place.
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
# fields and the report almanac (earth, the observer, is loaded separately).
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

def find_discrete_events(f, t0, t1, code_sets: Tuple[Tuple[int, ...], ...],
                         previous: bool = False) -> List[Optional[float]]:
    """One skyfield find_discrete scan over [t0, t1]; for each set of event
    codes, the timestamp of the first (or last, if previous) matching event,
    or None.  Used by both the loop packet fields and the report almanac."""
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
    given its first rise/set of that day.  Handles the polar cases; used by
    both the loop packet fields and the report almanac's 'visible'.
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
        self.prev_reading    : Dict[str, Any] = { 'dateTime': 0 } # Set to epoch so it will be too old to use

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
        # earth (the observer) is not a target body and stays out of
        # self.orbs, whose keys drive the report almanac's body dispatch.
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
        # the Hipparcos catalog when stars are enabled.  hip_<number> entries
        # are added lazily by get_star_by_hip; misses are remembered so a bad
        # tag doesn't rescan the catalog on every report.
        self.stars: Dict[str, Tuple[Any, Optional[float]]] = {}
        self.load_stars: bool = load_stars
        self.hip_misses: set = set()
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

    def get_star_by_hip(self, hip: int) -> bool:
        """Load the star with the given Hipparcos number into self.stars
        under the name 'hip_<number>', serving $almanac.hip_57939 style tags
        for any star in the available catalog (the bundled excerpt, or all
        118,218 stars when a full hip_main.dat is installed).  Results,
        including misses, are cached.  Returns whether the star is available."""
        if not self.load_stars:
            return False
        name = 'hip_%d' % hip
        if name in self.stars:
            return True
        if hip in self.hip_misses:
            return False
        # Already loaded under one of its names?  Alias it; no catalog scan.
        for star_name, star_hip in NAMED_STARS.items():
            if star_hip == hip and star_name in self.stars:
                self.stars[name] = self.stars[star_name]
                return True
        try:
            by_hip = Sky.load_stars_by_hip(self.user_root, {hip})
        except OSError as e:
            # A missing/unreadable catalog must degrade to a per-tag miss,
            # never propagate into report generation.
            log.error('get_star_by_hip: could not read the star catalog: %s' % e)
            self.hip_misses.add(hip)
            return False
        if hip not in by_hip:
            self.hip_misses.add(hip)
            return False
        self.stars[name] = by_hip[hip]
        return True

    @staticmethod
    def load_named_stars(user_root: str) -> Dict[str, Tuple[Any, Optional[float]]]:
        """Load the stars in NAMED_STARS from the Hipparcos catalog."""
        by_hip = Sky.load_stars_by_hip(user_root, set(NAMED_STARS.values()))
        return {name: by_hip[hip] for name, hip in NAMED_STARS.items() if hip in by_hip}

    @staticmethod
    def load_stars_by_hip(user_root: str, wanted_hips: set) -> Dict[int, Tuple[Any, Optional[float]]]:
        """Load the requested Hipparcos numbers from the bundled excerpt
        (celestial_stars.dat).  A full hip_main.dat, if present, is preferred,
        since it serves every Hipparcos star, not just the named ones."""
        path = '%s/%s' % (user_root, 'hip_main.dat')
        if not os.path.exists(path):
            path = '%s/%s' % (user_root, STAR_FILE)

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
        # convention as the report almanac's topo_ra/topo_dec and PyEphem).
        ra, dec, _ = apparent.radec('date')

        return az.degrees, alt.degrees, ra._degrees, dec.degrees

    def rise_set_radius_degrees(self, t: skyfield.timelib.Time, body_name: str, orb,
                                observer=None) -> float:
        """The body's apparent angular radius for rise/set purposes,
        computed for the date -- sun and moon only (a planet's
        sub-arcsecond radius does not meaningfully move its rise time).
        Shared by the loop fields and the report almanac, so their
        rise/set horizons agree."""
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

    def insert_fields(self, pkt: Dict[str, Any]) -> None:
        pkt_time: int = to_int(pkt['dateTime'])
        pkt_datetime  = datetime.fromtimestamp(pkt_time, timezone.utc)

        # If prev_reading is more than update_rate_secs ago, just use the previous readings.
        if pkt_time - self.prev_reading['dateTime'] < self.update_rate_secs:
            for key in self.prev_reading:
                if key != 'dateTime':
                    pkt[key] = self.prev_reading[key]
            return

        # Create a skyfield time with pkt_datetime.
        ts = self.ts
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
            pkt['sunAzimuth'] = sun_az
            pkt['sunAltitude'] = sun_alt
            pkt['sunRightAscension'] = sun_ra
            pkt['sunDeclination'] = sun_dec
        except Exception as e:
            log.error('insert_fields: get_az_alt_ra_dec(%r, %r, %r, %r, %r): %s.' % (ts, self.sun, pkt_datetime, tempC, pressureMbar, e))

        try:
            moon_az, moon_alt, moon_ra, moon_dec= self.get_az_alt_ra_dec(ts, self.moon, pkt_datetime, tempC, pressureMbar)
            pkt['moonAzimuth'] = moon_az
            pkt['moonAltitude'] = moon_alt
            pkt['moonRightAscension'] = moon_ra
            pkt['moonDeclination'] = moon_dec
        except Exception as e:
            log.error('insert_fields: get_az_alt_ra_dec(moon): %s.' % e)

        try:
            moon_phase_degrees, percent_illumination = self.get_moon_phase(ts, pkt_datetime)
            pkt['moonFullness'] = percent_illumination
            index = self.get_moon_phase_index(moon_phase_degrees)
            pkt['moonPhase'] = self.moon_phases[index]
        except Exception as e:
            log.error('insert_fields: get_moon_phase: %s.' % e)

        # Convert astronomical units to miles (US) or kilometers (METRIC and METRICWX).
        if pkt['usUnits'] == weewx.US:
            multiplier = AU_MILES
        else:
            multiplier = AU_KM

        try:
            orb: str = 'sun'
            pkt['earthSunDistance'] = self.distance_au(ts_pkt_time, self.sun) * multiplier
            orb = 'moon'
            pkt['earthMoonDistance'] = self.distance_au(ts_pkt_time, self.moon) * multiplier

            orb = 'earth'
            pkt['earthMercuryDistance'] = self.distance_au(ts_pkt_time, self.mercury) * multiplier
            orb = 'venus'
            pkt['earthVenusDistance'] = self.distance_au(ts_pkt_time, self.venus) * multiplier
            orb = 'mars'
            pkt['earthMarsDistance'] = self.distance_au(ts_pkt_time, self.mars) * multiplier
            orb = 'jupiter'
            pkt['earthJupiterDistance'] = self.distance_au(ts_pkt_time, self.jupiter) * multiplier
            orb = 'saturn'
            pkt['earthSaturnDistance'] = self.distance_au(ts_pkt_time, self.saturn) * multiplier
            orb = 'uranus'
            pkt['earthUranusDistance'] = self.distance_au(ts_pkt_time, self.uranus) * multiplier
            orb = 'neptune'
            pkt['earthNeptuneDistance'] = self.distance_au(ts_pkt_time, self.neptune) * multiplier
            orb = 'pluto'
            pkt['earthPlutoDistance'] = self.distance_au(ts_pkt_time, self.pluto) * multiplier
        except Exception as e:
            log.error('insert_fields: distance_au(%r, %s): %s.' % (ts_pkt_time, orb, e))

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
                    log.error('insert_fields: distance_au(%r, proxima_centauri): %s.' % (ts_pkt_time, e))
            if self.proxima_light_years is not None:
                pkt['earthProximaCentauriDistance'] = self.proxima_light_years


        # Sun/Moon rise/set/transit, etc. are always reported for the curent day (i.e., the event may have already passed.
        # We also don't want Equinox/Solstice/NewMoon/FullMoon to disappear as soon as it is hit (keep it around for the day)
        # As such, use the beginning of day for the observer, and recompute.
        day_start = datetime.fromtimestamp(weeutil.weeutil.startOfDay(pkt_time), timezone.utc)

        try:
            sunrise, sunset, transit, daylight = self.get_sunrise_sunset_transit_daylight(ts, day_start)
            if sunrise is not None:
                pkt['sunrise'] = sunrise
            if  sunset is not None:
                pkt['sunset'] = sunset
            pkt['daylightDur'] = daylight
            pkt['sunTransit'] = transit
        except Exception as e:
            log.error('insert_fields: get_sunrise_sunset_transit_daylight(%r): %s.' % (day_start, e))

        # Moonrise/Moonset/MoonTransit
        try:
            moonrise, moonset, moontransit = self.get_rise_set_transit(ts, 'moon', self.moon, day_start)
            if moonrise is not None:
                pkt['moonrise'] = moonrise
            if moonset is not None:
                pkt['moonset'] = moonset
            pkt['moonTransit'] = moontransit
        except Exception as e:
            log.error('insert_fields: get_rise_set_transit(moon, %r): %s.' % (day_start, e))

        try:
            next_equinox, next_solstice = self.get_next_equinox_and_solstice(ts, day_start)
            pkt['nextEquinox']  = next_equinox
            pkt['nextSolstice'] = next_solstice
        except Exception as e:
            log.error('insert_fields: get_next_equinox_and_solstice(%r): %s.' % (day_start, e))


        try:
            fullmoon, newmoon = self.get_next_fullmoon_and_newmoon(ts, day_start)
            if fullmoon is not None:
                pkt['nextFullMoon']  = fullmoon
            if newmoon is not None:
                pkt['nextNewMoon'] = newmoon
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
                        pkt['astronomicalTwilightEnd'] = t.utc_datetime().timestamp()
                    case 1:
                        if not astronomical_encountered:
                            pkt['astronomicalTwilightStart'] = t.utc_datetime().timestamp()
                            astronomical_encountered = True
                        else:
                            pkt['nauticalTwilightEnd'] = t.utc_datetime().timestamp()
                    case 2:
                        if not nautical_encountered:
                            pkt['nauticalTwilightStart'] = t.utc_datetime().timestamp()
                            nautical_encountered = True
                        else:
                            pkt['civilTwilightEnd'] = t.utc_datetime().timestamp()
                    case 3:
                        if not civil_encountered:
                            pkt['civilTwilightStart'] = t.utc_datetime().timestamp()
                            civil_encountered = True
        except Exception as e:
            log.error('insert_fields: skyfield.almanac.find_discrete twilight(%r, %r): %s.' % (day_start, f, e))

        try:
            # We need yesterday's sunshine duration
            yesterday_start = day_start - timedelta(days=1)
            _, _, _, yesterday_daylight = self.get_sunrise_sunset_transit_daylight(ts, yesterday_start)
            pkt['yesterdayDaylightDur'] = yesterday_daylight
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

        # DEPRECATED: also emit each value under its pre-3.0 field name, so
        # that existing [LoopData] fields lists and skins keep working.  The
        # old names will be removed in 4.0.
        for old_name, new_name in DEPRECATED_FIELD_MAP.items():
            if new_name in pkt:
                pkt[old_name] = pkt[new_name]

        # Update prev_reading to current reading.
        if self.update_rate_secs != 0:
            self.prev_reading['dateTime'] = pkt['dateTime']
            for key in list(OBS_GROUPS) + list(DEPRECATED_FIELD_MAP):
                if key in pkt:
                    self.prev_reading[key] = pkt[key]

#
# Skyfield report almanac.
#
# WeeWX 5.2 introduced extensible almanacs: weewx.almanac.almanacs is a
# prioritized list of AlmanacType objects and Almanac.__getattr__ tries
# each in turn until one does not raise weewx.UnknownType.  By registering
# SkyfieldAlmanacType at the head of that list, report tags such as
# $almanac.sunrise, $almanac.moon.transit and $almanac.next_full_moon are
# computed with Skyfield rather than the built-in PyEphem/weeutil almanac.
# Attributes Skyfield does not handle (e.g., stars) fall through to the
# built-in almanac.
#

# The eight seasonal events reported by skyfield.almanac.seasons are
# 0=vernal equinox, 1=summer solstice, 2=autumnal equinox, 3=winter solstice.
SEASON_EVENTS: Dict[str, Tuple[bool, Tuple[int, ...]]] = {
    'previous_equinox'         : (True,  (0, 2)),
    'next_equinox'             : (False, (0, 2)),
    'previous_solstice'        : (True,  (1, 3)),
    'next_solstice'            : (False, (1, 3)),
    'previous_vernal_equinox'  : (True,  (0,)),
    'next_vernal_equinox'      : (False, (0,)),
    'previous_summer_solstice' : (True,  (1,)),
    'next_summer_solstice'     : (False, (1,)),
    'previous_autumnal_equinox': (True,  (2,)),
    'next_autumnal_equinox'    : (False, (2,)),
    'previous_winter_solstice' : (True,  (3,)),
    'next_winter_solstice'     : (False, (3,)),
}

# skyfield.almanac.moon_phases events are
# 0=new moon, 1=first quarter, 2=full moon, 3=last quarter.
MOON_EVENTS: Dict[str, Tuple[bool, Tuple[int, ...]]] = {
    'previous_new_moon'          : (True,  (0,)),
    'next_new_moon'              : (False, (0,)),
    'previous_first_quarter_moon': (True,  (1,)),
    'next_first_quarter_moon'    : (False, (1,)),
    'previous_full_moon'         : (True,  (2,)),
    'next_full_moon'             : (False, (2,)),
    'previous_last_quarter_moon' : (True,  (3,)),
    'next_last_quarter_moon'     : (False, (3,)),
}

# Mean apparent semidiameters, used when a custom horizon is combined with
# use_center=False (i.e., the upper limb, not the center, crosses the horizon).
BODY_RADIUS_DEGREES: Dict[str, float] = {'sun': 16.0 / 60.0, 'moon': 15.5 / 60.0}

# Skyfield's standard refraction angle at the horizon.
STANDARD_REFRACTION_DEGREES = -34.0 / 60.0

# Equatorial radii in kilometers, used for angular size ($almanac.sun.size,
# $almanac.moon.radius_size, etc.).
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

# Tag form for addressing any Hipparcos star by number, e.g. $almanac.hip_57939.
HIP_TAG_RE = re.compile(r'hip_(\d+)$')

# Attributes that make no sense for a star (they involve the sun-body
# geometry of a solar system body).  For these, a star goes straight to the
# PyEphem fallback, which raises AttributeError just as PyEphem's own star
# objects do.  earth_distance/sun_distance are not in this set: unlike
# PyEphem, they ARE supported for stars with a measured parallax (e.g.,
# $almanac.proxima_centauri.earth_distance).
STAR_UNSUPPORTED = {'phase', 'moon_fullness',
                    'hlong', 'hlat', 'hlongitude', 'hlatitude'}

# Base class for almanac extensions.  WeeWX versions earlier than 5.2 do not
# have weewx.almanac.AlmanacType, in which case register_almanac declines to
# register (and this base is never exercised).
_AlmanacTypeBase: Any = getattr(weewx.almanac, 'AlmanacType', object)

class SkyfieldAlmanacType(_AlmanacTypeBase):
    """Almanac extension that computes report almanac tags with Skyfield."""

    def __init__(self, sky: Sky):
        self.sky = sky
        self.ts = sky.ts
        # Cache of observers, keyed by (lat, lon, altitude).
        self._observers: Dict[Tuple[float, float, float], Tuple[Any, Any]] = {}

    @property
    def hasExtras(self) -> bool:
        return True

    def location(self, almanac_obj) -> Tuple[Any, Any]:
        """Return (geographic_position, observer) for the almanac's location."""
        key = (almanac_obj.lat, almanac_obj.lon, almanac_obj.altitude)
        if key not in self._observers:
            geographic = skyfield.api.wgs84.latlon(almanac_obj.lat, almanac_obj.lon, elevation_m=almanac_obj.altitude)
            self._observers[key] = (geographic, self.sky.earth + geographic)
        return self._observers[key]

    def skyfield_time(self, time_ts: float) -> skyfield.timelib.Time:
        return self.ts.from_datetime(datetime.fromtimestamp(time_ts, timezone.utc))

    def time_value(self, almanac_obj, time_ts: Optional[float], context: str) -> ValueHelper:
        return ValueHelper(ValueTuple(time_ts, 'unix_epoch', 'group_time'),
                           context=context,
                           formatter=almanac_obj.formatter,
                           converter=almanac_obj.converter)

    def direction_value(self, almanac_obj, degrees: float) -> ValueHelper:
        return ValueHelper(ValueTuple(degrees, 'degree_compass', 'group_direction'),
                           context='ephem_day',
                           formatter=almanac_obj.formatter,
                           converter=almanac_obj.converter)

    def find_event(self, almanac_obj, f, codes: Tuple[int, ...], previous: bool, window_days: int) -> ValueHelper:
        """Search for the next (or previous) discrete event of the given type(s)."""
        if previous:
            t0 = self.skyfield_time(almanac_obj.time_ts - window_days * 86400)
            t1 = self.skyfield_time(almanac_obj.time_ts)
        else:
            t0 = self.skyfield_time(almanac_obj.time_ts)
            t1 = self.skyfield_time(almanac_obj.time_ts + window_days * 86400)
        event_ts = find_discrete_events(f, t0, t1, (codes,), previous)[0]
        return self.time_value(almanac_obj, event_ts, 'ephem_year')

    def get_almanac_data(self, almanac_obj, attr: str):
        if attr.startswith('__'):
            raise weewx.UnknownType(attr)

        if attr == 'sunrise':
            return almanac_obj.sun.rise
        elif attr == 'sunset':
            return almanac_obj.sun.set
        elif attr in ('moon_phase', 'moon_index', 'moon_fullness'):
            pkt_datetime = datetime.fromtimestamp(almanac_obj.time_ts, timezone.utc)
            moon_phase_degrees, percent_illumination = self.sky.get_moon_phase(self.ts, pkt_datetime)
            if attr == 'moon_fullness':
                return int(percent_illumination + 0.5)
            index = self.sky.get_moon_phase_index(moon_phase_degrees)
            if attr == 'moon_index':
                return index
            return almanac_obj.moon_phases[index]
        elif attr in SEASON_EVENTS:
            previous, codes = SEASON_EVENTS[attr]
            return self.find_event(almanac_obj, skyfield.almanac.seasons(self.sky.planets), codes, previous, 370)
        elif attr in MOON_EVENTS:
            previous, codes = MOON_EVENTS[attr]
            return self.find_event(almanac_obj, skyfield.almanac.moon_phases(self.sky.planets), codes, previous, 32)
        elif attr in ('sidereal_time', 'sidereal_angle'):
            geographic, _ = self.location(almanac_obj)
            degrees = geographic.lst_hours_at(self.skyfield_time(almanac_obj.time_ts)) * 15.0
            if attr == 'sidereal_time':
                return degrees
            return self.direction_value(almanac_obj, degrees)
        elif attr in self.sky.orbs or attr in self.sky.stars:
            return SkyfieldAlmanacBinder(self, almanac_obj, attr)

        # Any Hipparcos star by number: $almanac.hip_57939 (works for every
        # star in the available catalog; install a full hip_main.dat in the
        # user directory to go beyond the bundled named-star excerpt).
        hip_match = HIP_TAG_RE.match(attr)
        if hip_match:
            hip = int(hip_match.group(1))
            if self.sky.get_star_by_hip(hip):
                canonical = 'hip_%d' % hip
                if attr != canonical:
                    # Catalogs zero-pad HIP numbers (e.g. hip_032349); alias
                    # the tag as written to the canonical entry.
                    self.sky.stars[attr] = self.sky.stars[canonical]
                return SkyfieldAlmanacBinder(self, almanac_obj, attr)

        # Not something Skyfield handles (e.g., a star when the Hipparcos
        # catalog is not enabled).  Let the next almanac in
        # weewx.almanac.almanacs (PyEphem or weeutil) take a crack at it.
        raise weewx.UnknownType(attr)

    def separation(self, body1, body2):
        """Angular separation, in radians.  Accepts (longitude, latitude)
        tuples in radians (same contract as weewx.almanac.AlmanacType.separation),
        this almanac's own body binders (e.g.,
        $almanac.separation($almanac.mars, $almanac.venus)), or a mix of the
        two.  Each binder is observed at its own almanac's time.  Anything
        else (e.g., PyEphem Body objects) is deferred to the next almanac
        rather than crashed on."""
        if isinstance(body1, SkyfieldAlmanacBinder) and isinstance(body2, SkyfieldAlmanacBinder):
            p1 = self.sky.earth.at(self.skyfield_time(body1.almanac.time_ts)).observe(body1.target_body())
            p2 = self.sky.earth.at(self.skyfield_time(body2.almanac.time_ts)).observe(body2.target_body())
            return p1.separation_from(p2).radians
        coords1 = SkyfieldAlmanacType.separation_coordinates(body1)
        coords2 = SkyfieldAlmanacType.separation_coordinates(body2)
        if coords1 is None or coords2 is None:
            raise weewx.UnknownType('separation')
        # Meeus 17.1, delegated to the WeeWX base class (only reachable on
        # WeeWX 5.2+, where the base class exists).
        return super().separation(coords1, coords2)

    @staticmethod
    def separation_coordinates(body):
        """A separation argument as (longitude, latitude) in radians: a
        tuple as given, or a binder's apparent geocentric coordinates of
        date (at the binder's own almanac time).  None if unrecognized."""
        if isinstance(body, SkyfieldAlmanacBinder):
            return (math.radians(body.compute_angle('g_ra')),
                    math.radians(body.compute_angle('g_dec')))
        if isinstance(body, (tuple, list)):
            return body
        return None


class SkyfieldAlmanacBinder:
    """Binds the observer properties held in Almanac with a heavenly body."""

    # Attributes that are returned as ValueHelpers.  Maps attribute name to
    # (computation, ValueTuple flavor), where flavor 'direction' means degrees in
    # degree_compass, and 'angle' means radians in group_angle.
    VALUE_HELPER_ANGLES: Dict[str, Tuple[str, str]] = {
        'azimuth'   : ('az',    'direction'),
        'altitude'  : ('alt',   'angle'),
        'topo_ra'   : ('ra',    'direction'),
        'topo_dec'  : ('dec',   'angle'),
        'astro_ra'  : ('a_ra',  'direction'),
        'astro_dec' : ('a_dec', 'angle'),
        'geo_ra'    : ('g_ra',  'direction'),
        'geo_dec'   : ('g_dec', 'angle'),
        'hlongitude': ('hlong', 'direction'),
        'hlatitude' : ('hlat',  'angle'),
        'elongation': ('elong', 'angle'),
    }

    # Attributes that are returned as plain floats in decimal degrees.
    FLOAT_ANGLES = ('az', 'alt', 'ra', 'dec', 'a_ra', 'a_dec', 'g_ra', 'g_dec', 'hlong', 'hlat', 'elong')

    def __init__(self, almanac_type: SkyfieldAlmanacType, almanac, heavenly_body: str):
        self.almanac_type = almanac_type
        self.almanac = almanac
        self.heavenly_body = heavenly_body
        self.is_star = heavenly_body not in almanac_type.sky.orbs
        self.use_center = False

    def __call__(self, use_center: bool = False):
        self.use_center = use_center
        return self

    def __str__(self):
        # A binder cannot be printed itself.  It always needs an attribute.
        raise AttributeError(self.heavenly_body)

    def target_body(self) -> Any:
        """The skyfield object observed: a planet vector or a Star."""
        sky = self.almanac_type.sky
        if self.is_star:
            return sky.stars[self.heavenly_body][0]
        return sky.orbs[self.heavenly_body]

    def start_of_day_ts(self) -> float:
        """Local midnight of the day containing the almanac's time."""
        return weeutil.weeutil.startOfDay(self.almanac.time_ts)

    def refraction_degrees(self) -> float:
        """Atmospheric refraction at the horizon (negative degrees) for the
        almanac's pressure/temperature, scaled from the standard 34' so that
        WeeWX's defaults (1010 mbar, 15C) give exactly the standard value.
        pressure=0, WeeWX's documented no-refraction idiom, gives 0."""
        return (STANDARD_REFRACTION_DEGREES * (self.almanac.pressure / 1010.0)
                * (288.0 / (273.0 + self.almanac.temperature)))

    def apparent_radius_degrees(self) -> float:
        """The body's apparent angular radius for rise/set purposes: the
        same Sky computation the loop fields use, evaluated at the start of
        the almanac's day (as the loop does), so the two paths' rise/set
        horizons are identical."""
        _, observer = self.almanac_type.location(self.almanac)
        t = self.almanac_type.skyfield_time(self.start_of_day_ts())
        return self.almanac_type.sky.rise_set_radius_degrees(
            t, self.heavenly_body, self.target_body(), observer=observer)

    def horizon_degrees(self) -> float:
        """The effective horizon for rise/set (and for the all-day up/down
        judgments of visible and circumpolar/neverup, which must use the
        same value).  The default horizon includes refraction, scaled by
        the almanac's pressure/temperature (standard 34 arcminutes at
        standard conditions; pressure=0 turns it off), and the date's
        apparent body radius unless use_center is set.  One formula for
        all conditions: rise/set times vary continuously with pressure.
        A custom horizon is geometric (no refraction), per the USNO
        twilight definitions."""
        if self.almanac.horizon == 0.0:
            refraction = self.refraction_degrees()
            if self.use_center:
                return refraction
            return refraction - self.apparent_radius_degrees()
        h: float = self.almanac.horizon
        if not self.use_center:
            h -= self.apparent_radius_degrees()
        return h

    def find_rise_set(self, rise: bool, start_ts: float, end_ts: float, previous: bool = False) -> Optional[float]:
        _, observer = self.almanac_type.location(self.almanac)
        orb = self.target_body()
        t0 = self.almanac_type.skyfield_time(start_ts)
        t1 = self.almanac_type.skyfield_time(end_ts)
        finder = skyfield.almanac.find_risings if rise else skyfield.almanac.find_settings
        times, crosses = finder(observer, orb, t0, t1, horizon_degrees=self.horizon_degrees())
        stamps = [t.utc_datetime().timestamp() for t, crossed in zip(times, crosses) if crossed]
        if not stamps:
            return None
        return stamps[-1] if previous else stamps[0]

    def find_transit(self, antitransit: bool, start_ts: float, end_ts: float, previous: bool = False) -> Optional[float]:
        geographic, _ = self.almanac_type.location(self.almanac)
        orb = self.target_body()
        t0 = self.almanac_type.skyfield_time(start_ts)
        t1 = self.almanac_type.skyfield_time(end_ts)
        f = skyfield.almanac.meridian_transits(self.almanac_type.sky.planets, orb, geographic)
        times, events = skyfield.almanac.find_discrete(t0, t1, f)
        # meridian_transits reports 1 for an upper (meridian) transit and 0 for
        # a lower (antimeridian) transit.
        wanted = 0 if antitransit else 1
        stamps = [t.utc_datetime().timestamp() for t, event in zip(times, events) if event == wanted]
        if not stamps:
            return None
        return stamps[-1] if previous else stamps[0]

    @property
    def visible(self) -> ValueHelper:
        """How long the body is above the horizon on the almanac's day."""
        sod_ts = self.start_of_day_ts()
        eod_ts = sod_ts + 86400
        rise = self.find_rise_set(True, sod_ts, eod_ts)
        set_ = self.find_rise_set(False, sod_ts, eod_ts)

        def up_all_day() -> bool:
            _, observer = self.almanac_type.location(self.almanac)
            orb = self.target_body()
            alt, _, _ = observer.at(self.almanac_type.skyfield_time(sod_ts)).observe(orb).apparent().altaz()
            return alt.degrees > self.horizon_degrees()

        visible = daylight_seconds(rise, set_, sod_ts, eod_ts, up_all_day)
        return ValueHelper(ValueTuple(visible, 'second', 'group_deltatime'),
                           context='day',
                           formatter=self.almanac.formatter,
                           converter=self.almanac.converter)

    def visible_change(self, days_ago: int = 1) -> ValueHelper:
        """Change in visibility of the heavenly body compared to 'days_ago'."""
        today_visible = self.visible
        # Anchor at local noon minus whole days: subtracting a flat 86400
        # from the almanac's time can land on the wrong calendar day across
        # a DST transition (e.g., 00:30 PDT on the spring-forward day minus
        # 86400 is 23:30 PST two calendar days back).
        then_almanac = self.almanac(
            almanac_time=self.start_of_day_ts() + 43200 - days_ago * 86400)
        then_visible = getattr(then_almanac, self.heavenly_body).visible
        diff_vt = today_visible.value_t - then_visible.value_t
        return ValueHelper(diff_vt,
                           context='hour',
                           formatter=self.almanac.formatter,
                           converter=self.almanac.converter)

    def compute_angle(self, attr: str) -> float:
        """Compute the requested angle.  Returned in decimal degrees."""
        sky = self.almanac_type.sky
        orb = self.target_body()
        t = self.almanac_type.skyfield_time(self.almanac.time_ts)
        if attr in ('az', 'alt'):
            _, observer = self.almanac_type.location(self.almanac)
            apparent = observer.at(t).observe(orb).apparent()
            alt, az, _ = apparent.altaz(temperature_C=self.almanac.temperature,
                                        pressure_mbar=self.almanac.pressure)
            return az.degrees if attr == 'az' else alt.degrees
        elif attr in ('ra', 'dec'):
            # Apparent topocentric right ascension/declination of date.
            _, observer = self.almanac_type.location(self.almanac)
            ra, dec, _ = observer.at(t).observe(orb).apparent().radec('date')
            return ra._degrees if attr == 'ra' else dec.degrees
        elif attr in ('a_ra', 'a_dec'):
            # Astrometric geocentric right ascension/declination (J2000).
            ra, dec, _ = sky.earth.at(t).observe(orb).radec()
            return ra._degrees if attr == 'a_ra' else dec.degrees
        elif attr in ('g_ra', 'g_dec'):
            # Apparent geocentric right ascension/declination of date.
            ra, dec, _ = sky.earth.at(t).observe(orb).apparent().radec('date')
            return ra._degrees if attr == 'g_ra' else dec.degrees
        elif attr in ('hlong', 'hlat'):
            # Heliocentric ecliptic longitude/latitude.  For the sun itself
            # these are undefined (it sits at the origin); report Earth's
            # heliocentric coordinates instead, per the XEphem convention.
            # For the moon this is its true heliocentric longitude, where
            # PyEphem reports the moon's GEOcentric ecliptic longitude.
            target = sky.earth if self.heavenly_body == 'sun' else orb
            lat, lon, _ = sky.sun.at(t).observe(target).frame_latlon(skyfield.framelib.ecliptic_frame)
            return lon.degrees if attr == 'hlong' else lat.degrees
        else:
            # elong: elongation (angular separation from the sun).
            e = sky.earth.at(t)
            return e.observe(orb).separation_from(e.observe(sky.sun)).degrees

    def magnitude(self) -> float:
        """Apparent visual magnitude of the body."""
        sky = self.almanac_type.sky
        name = self.heavenly_body
        if self.is_star:
            mag = sky.stars[name][1]
            if mag is None:
                raise AttributeError('mag')
            return mag
        t = self.almanac_type.skyfield_time(self.almanac.time_ts)
        if name == 'sun':
            # The sun's apparent magnitude is -26.74 at one astronomical unit.
            return -26.74 + 5.0 * math.log10(sky.distance_au(t, sky.sun))
        elif name == 'moon':
            # Allen's approximation, plus a correction for the moon's
            # topocentric distance (385000 km is the mean).
            _, observer = self.almanac_type.location(self.almanac)
            apparent = observer.at(t).observe(sky.moon).apparent()
            phase_angle = abs(apparent.phase_angle(sky.sun).degrees)
            return (-12.73 + 0.026 * phase_angle + 4e-9 * phase_angle ** 4
                    + 5.0 * math.log10(apparent.distance().km / 385000.0))
        elif name == 'pluto':
            # Meeus, Astronomical Algorithms: m = -1.00 + 5 log10(r * delta).
            return -1.0 + 5.0 * math.log10(sky.distance_au(t, sky.pluto, origin=sky.sun)
                                           * sky.distance_au(t, sky.pluto))
        else:
            return float(skyfield.magnitudelib.planetary_magnitude(
                sky.earth.at(t).observe(sky.orbs[name])))

    def angular_radius_radians(self) -> float:
        """Apparent (topocentric) angular radius of the body, in radians."""
        if self.is_star:
            return 0.0
        _, observer = self.almanac_type.location(self.almanac)
        t = self.almanac_type.skyfield_time(self.almanac.time_ts)
        distance_km = observer.at(t).observe(self.target_body()).apparent().distance().km
        return math.asin(BODY_RADIUS_KM[self.heavenly_body] / distance_km)

    def circumpolar_neverup(self) -> Tuple[bool, bool]:
        """Whether the body stays above (circumpolar), or below (neverup),
        the horizon, judged from its current declination.  Uses the same
        effective horizon as find_rise_set (refraction and body radius
        included), so these can never contradict rise/set."""
        dec_degrees = self.compute_angle('dec')
        latitude = self.almanac.lat
        upper_culmination_alt = 90.0 - abs(latitude - dec_degrees)
        lower_culmination_alt = abs(latitude + dec_degrees) - 90.0
        threshold = self.horizon_degrees()
        return (lower_culmination_alt > threshold,
                upper_culmination_alt < threshold)

    def parallactic_angle(self) -> float:
        """Parallactic angle of the body in radians (a method, like PyEphem's,
        so that both $almanac.venus.parallactic_angle and an explicit call
        work in a template)."""
        _, observer = self.almanac_type.location(self.almanac)
        t = self.almanac_type.skyfield_time(self.almanac.time_ts)
        ha, dec, _ = observer.at(t).observe(self.target_body()).apparent().hadec()
        latitude = math.radians(self.almanac.lat)
        return math.atan2(math.sin(ha.radians),
                          math.tan(latitude) * math.cos(dec.radians)
                          - math.sin(dec.radians) * math.cos(ha.radians))

    def moon_libration(self, attr: str) -> float:
        """Geocentric optical libration of the moon (libration_lat,
        libration_long) and selenographic colongitude of the sun (colong),
        in radians like PyEphem's, per Meeus, Astronomical Algorithms,
        chapter 53.  The physical libration (at most 0.04 degrees) is
        neglected."""
        sky = self.almanac_type.sky
        t = self.almanac_type.skyfield_time(self.almanac.time_ts)
        T = (t.tt - 2451545.0) / 36525.0
        # Mean elements of the lunar orbit (Meeus ch. 47), in degrees:
        # F, the moon's argument of latitude, and omega, the longitude of
        # the ascending node.  I is the inclination of the mean lunar
        # equator to the ecliptic.
        F = 93.2720950 + 483202.0175233 * T - 0.0036539 * T ** 2 - T ** 3 / 3526000.0 + T ** 4 / 863310000.0
        omega = 125.0445479 - 1934.1362891 * T + 0.0020754 * T ** 2 + T ** 3 / 467441.0 - T ** 4 / 60616000.0
        inc = math.radians(1.54242)

        moon_lat, moon_lon, moon_dist = sky.earth.at(t).observe(sky.moon).apparent().frame_latlon(
            skyfield.framelib.ecliptic_frame)
        if attr == 'colong':
            # The colongitude derives from the selenographic position of
            # the sun: the same formulas, fed the sun's coordinates as seen
            # from the moon (Meeus 53.5).
            sun_lat, sun_lon, sun_dist = sky.earth.at(t).observe(sky.sun).apparent().frame_latlon(
                skyfield.framelib.ecliptic_frame)
            ratio = moon_dist.au / sun_dist.au
            lam = (sun_lon.degrees + 180.0
                   + math.degrees(ratio) * math.cos(moon_lat.radians)
                   * math.sin(math.radians(sun_lon.degrees - moon_lon.degrees)))
            beta = math.radians(ratio * moon_lat.degrees)
        else:
            lam = moon_lon.degrees
            beta = moon_lat.radians
        W = math.radians(lam - omega)
        if attr == 'libration_lat':
            return math.asin(-math.sin(W) * math.cos(beta) * math.sin(inc)
                             - math.sin(beta) * math.cos(inc))
        A = math.atan2(math.sin(W) * math.cos(beta) * math.cos(inc)
                       - math.sin(beta) * math.sin(inc),
                       math.cos(W) * math.cos(beta))
        l = math.degrees(A) - F
        if attr == 'libration_long':
            # Librations stay within +/-8 degrees; normalize to [-180, 180).
            return math.radians((l + 180.0) % 360.0 - 180.0)
        # Selenographic colongitude of the sun (the morning terminator).
        return math.radians((90.0 - l) % 360.0)

    def jupiter_cml(self, attr: str) -> float:
        """Central meridian longitude of Jupiter in System I (equatorial
        belts) or System II (temperate belts), in radians like PyEphem's.
        Computed rigorously: the sub-Earth longitude from the light-time
        corrected geometry and the IAU rotation elements (pole per the IAU
        Working Group on Cartographic Coordinates; System I/II rotation
        rates per the Explanatory Supplement).  Note: PyEphem's values
        differ from the IAU definition by about 0.8 degrees."""
        sky = self.almanac_type.sky
        t = self.almanac_type.skyfield_time(self.almanac.time_ts)
        astrometric = sky.earth.at(t).observe(sky.jupiter)
        p = astrometric.position.au                # earth -> jupiter, ICRF
        d = (t.tdb - 2451545.0) - astrometric.light_time    # time at Jupiter
        T = d / 36525.0
        a0 = math.radians(268.056595 - 0.006499 * T)        # pole RA
        d0 = math.radians(64.495303 + 0.002413 * T)         # pole dec
        if attr == 'cmlI':
            W = 67.1 + 877.900 * d
        else:
            W = 43.3 + 870.270 * d
        z = numpy.array([math.cos(d0) * math.cos(a0),
                         math.cos(d0) * math.sin(a0),
                         math.sin(d0)])
        node = numpy.cross([0.0, 0.0, 1.0], z)     # ascending node of the equator
        node /= numpy.linalg.norm(node)
        y = numpy.cross(z, node)
        s = -p / numpy.linalg.norm(p)              # jupiter -> earth direction
        theta = math.degrees(math.atan2(numpy.dot(s, y), numpy.dot(s, node)))
        return math.radians((W - theta) % 360.0)

    def saturn_ring_tilt(self, attr: str) -> float:
        """Saturnicentric latitude of the Earth (earth_tilt) or of the Sun
        (sun_tilt) referred to the ring plane, in radians like PyEphem's
        (southern tilts negative), per Meeus, Astronomical Algorithms,
        chapter 45."""
        sky = self.almanac_type.sky
        t = self.almanac_type.skyfield_time(self.almanac.time_ts)
        T = (t.tt - 2451545.0) / 36525.0
        # Inclination and node of the ring plane, ecliptic of date.
        i = math.radians(28.075216 - 0.012998 * T + 0.000004 * T ** 2)
        node = 169.508470 + 1.394681 * T + 0.000412 * T ** 2
        if attr == 'earth_tilt':
            lat, lon, _ = sky.earth.at(t).observe(sky.saturn).apparent().frame_latlon(
                skyfield.framelib.ecliptic_frame)
        else:
            lat, lon, _ = sky.sun.at(t).observe(sky.saturn).frame_latlon(
                skyfield.framelib.ecliptic_frame)
        return math.asin(math.sin(i) * math.cos(lat.radians) * math.sin(math.radians(lon.degrees - node))
                         - math.cos(i) * math.sin(lat.radians))

    def pyephem_fallback(self, attr: str):
        """Delegate an attribute Skyfield does not compute to the built-in
        PyEphem almanac, if PyEphem is installed."""
        if getattr(weewx.almanac, 'ephem', None) is not None:
            binder = weewx.almanac.AlmanacBinder(self.almanac, self.heavenly_body)
            binder.use_center = self.use_center
            return getattr(binder, attr)
        raise AttributeError("'%s' object has no attribute '%s'" % (self.heavenly_body.capitalize(), attr))

    def __getattr__(self, attr: str):
        """Get the requested observation, such as when the body will rise."""
        # Don't try any attributes that start with a double underscore, or any
        # of these special names: they are used by the Python language:
        if attr.startswith('__') or attr in ['mro', 'im_func', 'func_code']:
            raise AttributeError(attr)

        # For a star, attributes involving sun-body geometry make no sense.
        # PyEphem's own star objects raise AttributeError for these, and the
        # fallback reproduces that behavior.
        if self.is_star and attr in STAR_UNSUPPORTED:
            return self.pyephem_fallback(attr)

        if attr in ('rise', 'set', 'transit'):
            # These verbs refer to the time the event occurs anytime in the
            # day, which is not necessarily the *next* one.  Look forward from
            # local midnight (two days, in case the event does not occur today).
            sod_ts = self.start_of_day_ts()
            if attr == 'transit':
                event_ts = self.find_transit(False, sod_ts, sod_ts + 2 * 86400)
            else:
                event_ts = self.find_rise_set(attr == 'rise', sod_ts, sod_ts + 2 * 86400)
            return self.almanac_type.time_value(self.almanac, event_ts, 'ephem_day')
        elif attr in ('next_rising', 'next_setting', 'previous_rising', 'previous_setting',
                      'next_transit', 'previous_transit', 'next_antitransit', 'previous_antitransit'):
            # These are relative to the time of the almanac.
            time_ts = self.almanac.time_ts
            previous = attr.startswith('previous_')
            if previous:
                start_ts, end_ts = time_ts - 2 * 86400, time_ts
            else:
                start_ts, end_ts = time_ts, time_ts + 2 * 86400
            if attr.endswith('transit'):
                event_ts = self.find_transit(attr.endswith('antitransit'), start_ts, end_ts, previous)
            else:
                event_ts = self.find_rise_set(attr.endswith('rising'), start_ts, end_ts, previous)
            return self.almanac_type.time_value(self.almanac, event_ts, 'ephem_day')
        elif attr in SkyfieldAlmanacBinder.VALUE_HELPER_ANGLES:
            key, flavor = SkyfieldAlmanacBinder.VALUE_HELPER_ANGLES[attr]
            degrees = self.compute_angle(key)
            if flavor == 'direction':
                return self.almanac_type.direction_value(self.almanac, degrees)
            return ValueHelper(ValueTuple(math.radians(degrees), 'radian', 'group_angle'),
                               context='ephem_day',
                               formatter=self.almanac.formatter,
                               converter=self.almanac.converter)
        elif attr in SkyfieldAlmanacBinder.FLOAT_ANGLES:
            return self.compute_angle(attr)
        elif attr == 'moon_fullness' and self.heavenly_body == 'moon':
            # Same computation as 'phase' (percent illuminated).
            return self.phase
        elif attr in ('earth_distance', 'sun_distance'):
            # Supported for planets, and for stars with a measured parallax
            # (a zero parallax puts the star on skyfield's gigaparsec sphere,
            # i.e., its distance is unknown).
            sky = self.almanac_type.sky
            if self.is_star and not sky.stars[self.heavenly_body][0].parallax_mas:
                return self.pyephem_fallback(attr)
            t = self.almanac_type.skyfield_time(self.almanac.time_ts)
            origin = sky.sun if attr == 'sun_distance' else None
            return sky.distance_au(t, self.target_body(), origin=origin)
        elif attr == 'mag':
            return self.magnitude()
        elif attr == 'phase':
            # Percent of the body's surface illuminated by the sun.  The sun
            # illuminates itself: 100, as PyEphem also reports (asking
            # skyfield for the sun's fraction_illuminated by the sun would
            # yield a meaningless ~50).
            if self.heavenly_body == 'sun':
                return 100.0
            sky = self.almanac_type.sky
            t = self.almanac_type.skyfield_time(self.almanac.time_ts)
            return 100.0 * sky.earth.at(t).observe(sky.orbs[self.heavenly_body]).apparent().fraction_illuminated(sky.sun)
        elif attr == 'size':
            # Apparent angular diameter in arcseconds.
            return math.degrees(2.0 * self.angular_radius_radians()) * 3600.0
        elif attr == 'radius':
            # Apparent angular radius in decimal degrees (the old-style name).
            return math.degrees(self.angular_radius_radians())
        elif attr == 'radius_size':
            # Apparent angular radius as a ValueHelper.
            return ValueHelper(ValueTuple(self.angular_radius_radians(), 'radian', 'group_angle'),
                               context='ephem_day',
                               formatter=self.almanac.formatter,
                               converter=self.almanac.converter)
        elif attr in ('circumpolar', 'neverup'):
            circumpolar, neverup = self.circumpolar_neverup()
            return circumpolar if attr == 'circumpolar' else neverup
        elif attr in ('libration_lat', 'libration_long', 'colong') and self.heavenly_body == 'moon':
            return self.moon_libration(attr)
        elif attr in ('cmlI', 'cmlII') and self.heavenly_body == 'jupiter':
            return self.jupiter_cml(attr)
        elif attr in ('earth_tilt', 'sun_tilt') and self.heavenly_body == 'saturn':
            return self.saturn_ring_tilt(attr)
        elif attr == 'name':
            return self.heavenly_body.replace('_', ' ').title()

        # Something Skyfield does not compute (e.g., the moon's libration or
        # Jupiter's central meridian longitudes).  Fall back to the built-in
        # PyEphem almanac if PyEphem is installed.
        return self.pyephem_fallback(attr)


def register_almanac(sky: Sky) -> bool:
    """Register the Skyfield almanac at the head of WeeWX's almanac list, so
    that reports use Skyfield.  Requires WeeWX 5.2 or later."""
    if not hasattr(weewx.almanac, 'almanacs') or not hasattr(weewx.almanac, 'AlmanacType'):
        log.info('This version of WeeWX (%s) does not support almanac extensions'
                 ' (WeeWX 5.2 or later is required).  Reports will not use Skyfield.' % weewx.__version__)
        return False
    # Remove any previously registered instance (e.g., after an engine restart),
    # then insert at the head of the list so Skyfield takes priority.  Match on
    # module as well as class name: the independent weewx-skyfield-almanac
    # extension also names its class SkyfieldAlmanacType and must not be removed.
    weewx.almanac.almanacs[:] = [a for a in weewx.almanac.almanacs
                                 if not (type(a).__name__ == 'SkyfieldAlmanacType'
                                         and type(a).__module__ == __name__)]
    weewx.almanac.almanacs.insert(0, SkyfieldAlmanacType(sky))
    return True


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

    def check_deprecated_aliases(pkt: Dict[str, Any]) -> bool:
        """Every deprecated (pre-3.0) field name must be present and hold the
        same value as its replacement."""
        success: bool = True
        for old_name, new_name in DEPRECATED_FIELD_MAP.items():
            if new_name in pkt and (old_name not in pkt or pkt[old_name] != pkt[new_name]):
                log.info('Deprecated alias %s does not match %s.' % (old_name, new_name))
                success = False
        if success:
            log.info('All %d deprecated field aliases match their replacements.' % len(DEPRECATED_FIELD_MAP))
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
            'sunRightAscension']):
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
        elif not check_deprecated_aliases(pkt):
            log.info('Test failed.  See above.')
        else:
            log.info('All fields present and of the correct type.  The test passed.')
