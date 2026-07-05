"""
test_almanac.py

Copyright (C)2022-2025 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Tests for the Skyfield report almanac (SkyfieldAlmanacType/SkyfieldAlmanacBinder).

Run with the WeeWX virtual environment's Python, from the root of this repo:
    /home/weewx/weewx-venv/bin/python -m pytest tests

The expected values below were computed with Skyfield 1.54 and JPL's de421
ephemeris for Palo Alto, CA on 2025-06-21 (summer solstice weekend), and were
sanity checked against PyEphem and published almanac data.  They serve as
regression values.
"""

import contextlib
import os
import sys
import time

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TEST_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, 'bin', 'user'))

# The expected values (and WeeWX's notion of "today's" rise/set) depend on
# the local timezone, so pin it.
os.environ['TZ'] = 'America/Los_Angeles'
time.tzset()

import weeutil.Moon
import weeutil.weeutil
import weewx
import weewx.almanac
import weewx.units

import celestial

LATITUDE    = 37.4419
LONGITUDE   = -122.143
ALTITUDE_M  = 9.0
TIME_TS     = 1750532400      # 2025-06-21 12:00:00 PDT

# Tolerances
TIME_TOL    = 5.0             # seconds, for event regression values
ANGLE_TOL   = 0.05            # degrees
EPHEM_TOL   = 120.0           # seconds, when comparing against PyEphem

# The named stars come from celestial_stars.dat, a small excerpt of the
# Hipparcos catalog that ships with the extension.
CATALOG_PRESENT = os.path.exists(os.path.join(REPO_ROOT, 'bin', 'user', celestial.STAR_FILE))
needs_catalog = pytest.mark.skipif(not CATALOG_PRESENT, reason='%s not present' % celestial.STAR_FILE)


@pytest.fixture(scope='session')
def sky():
    s = celestial.Sky(0, os.path.join(REPO_ROOT, 'bin', 'user'),
                      weeutil.Moon.moon_phases, ALTITUDE_M, LATITUDE, LONGITUDE,
                      load_stars=CATALOG_PRESENT)
    assert s.is_valid()
    return s


@contextlib.contextmanager
def saved_almanacs():
    """Save and restore the global weewx.almanac.almanacs list."""
    saved = list(weewx.almanac.almanacs)
    try:
        yield
    finally:
        weewx.almanac.almanacs[:] = saved


def pyephem_observer(start_of_day: bool = False):
    """A PyEphem observer at the test station, at TIME_TS (or the local
    midnight starting its day).  Skips the calling test when PyEphem is
    not installed."""
    ephem = pytest.importorskip('ephem')
    observer = ephem.Observer()
    observer.lat = str(LATITUDE)
    observer.lon = str(LONGITUDE)
    observer.elevation = ALTITUDE_M
    date_ts = weeutil.weeutil.startOfDay(TIME_TS) if start_of_day else TIME_TS
    observer.date = weewx.almanac.timestamp_to_djd(date_ts)
    return observer


@pytest.fixture()
def almanac(sky):
    with saved_almanacs():
        assert celestial.register_almanac(sky)
        yield weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                    formatter=weewx.units.get_default_formatter())


@pytest.fixture()
def skyfield_only_almanac(sky):
    """An Almanac as it would behave on a system without PyEphem: the
    Skyfield almanac is the only registered almanac, and celestial's
    PyEphem fallback sees no ephem module."""
    saved_ephem = getattr(weewx.almanac, 'ephem', None)
    with saved_almanacs():
        assert celestial.register_almanac(sky)
        weewx.almanac.almanacs[:] = [a for a in weewx.almanac.almanacs
                                     if type(a).__name__ == 'SkyfieldAlmanacType']
        if saved_ephem is not None:
            del weewx.almanac.ephem
        try:
            yield weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
        finally:
            if saved_ephem is not None:
                weewx.almanac.ephem = saved_ephem


class StubEngine:
    """Just enough of a WeeWX engine for the Celestial service to start."""
    def __init__(self):
        self.bound = []

    def bind(self, event, callback):
        self.bound.append(event)


def make_config(**celestial_options):
    config = {
        'WEEWX_ROOT': REPO_ROOT,
        'USER_ROOT': 'bin/user',
        'Celestial': {'enable': 'true'},
        'Station': {
            'latitude': str(LATITUDE),
            'longitude': str(LONGITUDE),
            'altitude': [str(ALTITUDE_M), 'meter'],
        },
    }
    config['Celestial'].update(celestial_options)
    return config


class TestService:
    def test_service_registers_almanac(self):
        with saved_almanacs():
            engine = StubEngine()
            celestial.Celestial(engine, make_config())
            assert weewx.NEW_LOOP_PACKET in engine.bound
            assert type(weewx.almanac.almanacs[0]).__name__ == 'SkyfieldAlmanacType'

    def test_service_replace_builtin_almanac_disabled(self):
        with saved_almanacs():
            engine = StubEngine()
            celestial.Celestial(engine, make_config(replace_builtin_almanac='false'))
            # Loop packets are still bound, but no almanac is registered.
            assert weewx.NEW_LOOP_PACKET in engine.bound
            assert all(type(a).__name__ != 'SkyfieldAlmanacType' for a in weewx.almanac.almanacs)

    def test_service_disabled(self):
        with saved_almanacs():
            engine = StubEngine()
            celestial.Celestial(engine, make_config(enable='false'))
            assert engine.bound == []
            assert all(type(a).__name__ != 'SkyfieldAlmanacType' for a in weewx.almanac.almanacs)

    @needs_catalog
    def test_service_stars_default_on(self):
        with saved_almanacs():
            engine = StubEngine()
            service = celestial.Celestial(engine, make_config())
            assert len(service.sky.stars) == len(set(celestial.NAMED_STARS))

    def test_service_stars_disabled(self):
        with saved_almanacs():
            engine = StubEngine()
            service = celestial.Celestial(engine, make_config(stars='false'))
            assert service.sky.stars == {}


class TestRegistration:
    def test_skyfield_registered_first(self, sky):
        with saved_almanacs():
            assert celestial.register_almanac(sky)
            assert type(weewx.almanac.almanacs[0]).__name__ == 'SkyfieldAlmanacType'
            # Registering again must not create a duplicate.
            assert celestial.register_almanac(sky)
            names = [type(a).__name__ for a in weewx.almanac.almanacs]
            assert names.count('SkyfieldAlmanacType') == 1
            assert names[0] == 'SkyfieldAlmanacType'

    def test_has_extras(self, almanac):
        assert almanac.hasExtras


class TestSunAndMoonEvents:
    def test_sunrise_sunset(self, almanac):
        assert almanac.sunrise.raw == pytest.approx(1750510081.9, abs=TIME_TOL)
        assert almanac.sunset.raw == pytest.approx(1750563177.8, abs=TIME_TOL)
        assert almanac.sun.rise.raw == almanac.sunrise.raw
        assert almanac.sun.set.raw == almanac.sunset.raw

    def test_sun_transit(self, almanac):
        assert almanac.sun.transit.raw == pytest.approx(1750536630.2, abs=TIME_TOL)

    def test_moon_rise_transit_set(self, almanac):
        assert almanac.moon.rise.raw == pytest.approx(1750497776.3, abs=TIME_TOL)
        assert almanac.moon.transit.raw == pytest.approx(1750523341.1, abs=TIME_TOL)
        assert almanac.moon.set.raw == pytest.approx(1750549654.3, abs=TIME_TOL)

    def test_twilight_horizons(self, almanac):
        civil = almanac(horizon=-6).sun(use_center=1).rise.raw
        nautical = almanac(horizon=-12).sun(use_center=1).rise.raw
        astronomical = almanac(horizon=-18).sun(use_center=1).rise.raw
        assert civil == pytest.approx(1750508213.5, abs=TIME_TOL)
        assert nautical == pytest.approx(1750505876.7, abs=TIME_TOL)
        assert astronomical == pytest.approx(1750503235.7, abs=TIME_TOL)
        # Dawn stages must be in order and before sunrise.
        assert astronomical < nautical < civil < almanac.sunrise.raw
        # The horizon override must not stick to the almanac.
        assert almanac.sun.rise.raw == pytest.approx(1750510081.9, abs=TIME_TOL)

    def test_next_and_previous_events(self, almanac):
        assert almanac.next_full_moon.raw == pytest.approx(1752179807.6, abs=TIME_TOL)
        assert almanac.next_new_moon.raw == pytest.approx(1750847497.1, abs=TIME_TOL)
        assert almanac.next_equinox.raw == pytest.approx(1758565160.5, abs=TIME_TOL)
        assert almanac.next_solstice.raw == pytest.approx(1766329385.1, abs=TIME_TOL)
        assert almanac.previous_solstice.raw == pytest.approx(1750473735.7, abs=TIME_TOL)
        # Sanity: previous < now < next.
        assert almanac.previous_full_moon.raw < TIME_TS < almanac.next_full_moon.raw
        assert almanac.previous_equinox.raw < TIME_TS < almanac.next_equinox.raw
        assert almanac.next_vernal_equinox.raw > almanac.next_autumnal_equinox.raw
        assert almanac.previous_winter_solstice.raw < TIME_TS

    def test_next_previous_risings(self, almanac):
        assert almanac.sun.previous_rising.raw == pytest.approx(1750510081.9, abs=TIME_TOL)
        assert almanac.sun.next_rising.raw == pytest.approx(1750596496.5, abs=TIME_TOL)
        assert almanac.sun.previous_rising.raw < TIME_TS < almanac.sun.next_rising.raw
        assert almanac.sun.previous_setting.raw < TIME_TS < almanac.sun.next_setting.raw

    def test_transits(self, almanac):
        assert almanac.sun.next_antitransit.raw == pytest.approx(1750579836.8, abs=TIME_TOL)
        assert almanac.sun.previous_transit.raw < TIME_TS < almanac.sun.next_transit.raw
        assert almanac.sun.previous_antitransit.raw < TIME_TS < almanac.sun.next_antitransit.raw


class TestPositions:
    def test_sun_position(self, almanac):
        assert almanac.sun.az == pytest.approx(127.847, abs=ANGLE_TOL)
        assert almanac.sun.alt == pytest.approx(69.409, abs=ANGLE_TOL)
        assert almanac.sun.ra == pytest.approx(90.707, abs=ANGLE_TOL)
        assert almanac.sun.dec == pytest.approx(23.436, abs=ANGLE_TOL)

    def test_moon_position(self, almanac):
        assert almanac.moon.az == pytest.approx(249.300, abs=ANGLE_TOL)
        assert almanac.moon.alt == pytest.approx(52.462, abs=ANGLE_TOL)

    def test_value_helper_angles(self, almanac):
        # These are ValueHelpers; .raw applies the default converter, which
        # renders angles in degrees.
        assert almanac.sun.azimuth.raw == pytest.approx(almanac.sun.az, abs=ANGLE_TOL)
        assert almanac.sun.altitude.raw == pytest.approx(almanac.sun.alt, abs=ANGLE_TOL)
        assert almanac.sun.topo_dec.raw == pytest.approx(almanac.sun.dec, abs=ANGLE_TOL)
        assert almanac.sun.topo_ra.raw == pytest.approx(almanac.sun.ra, abs=ANGLE_TOL)
        # And they can be formatted (as done in the Seasons skin).
        assert str(almanac.sun.azimuth.format("%.1f"))
        assert str(almanac.moon.altitude.format("%.1f"))

    def test_sidereal(self, almanac):
        assert almanac.sidereal_time == pytest.approx(73.083, abs=ANGLE_TOL)
        assert 0.0 <= almanac.sidereal_time < 360.0
        assert almanac.sidereal_angle.raw == pytest.approx(almanac.sidereal_time, abs=ANGLE_TOL)

    def test_distances(self, almanac):
        assert almanac.sun.earth_distance == pytest.approx(1.01625, abs=0.001)
        assert almanac.mars.earth_distance == pytest.approx(1.85875, abs=0.001)
        assert almanac.mars.sun_distance == pytest.approx(1.64, abs=0.05)


class TestMoonPhase:
    def test_moon_phase(self, almanac):
        assert almanac.moon_phase == weeutil.Moon.moon_phases[7]  # waning crescent
        assert almanac.moon_index == 7
        assert isinstance(almanac.moon_index, int)

    def test_moon_fullness(self, almanac):
        assert almanac.moon_fullness == 18
        assert isinstance(almanac.moon_fullness, int)
        # The more precise binder value:
        assert almanac.moon.moon_fullness == pytest.approx(18.18, abs=0.1)


class TestVisible:
    def test_sun_visible(self, almanac):
        assert almanac.sun.visible.raw == pytest.approx(almanac.sunset.raw - almanac.sunrise.raw, abs=1.0)
        assert str(almanac.sun.visible.long_form())

    def test_sun_visible_change(self, almanac):
        # Within a day of the solstice, the day length changes just a few seconds.
        assert abs(almanac.sun.visible_change().raw) < 60.0

    def test_sun_visible_change_across_dst(self, almanac):
        # 2026-03-09 00:30 PDT: within the first hour after midnight on the
        # day after the spring-forward transition.  A flat time_ts - 86400
        # is 2026-03-07 23:30 PST -- the wrong calendar day -- so
        # visible_change must anchor its day arithmetic at local noon.
        just_after_midnight = time.mktime((2026, 3, 9, 0, 30, 0, 0, 0, -1))
        today = almanac(almanac_time=just_after_midnight)
        yesterday = almanac(almanac_time=time.mktime((2026, 3, 8, 12, 0, 0, 0, 0, -1)))
        expected = today.sun.visible.raw - yesterday.sun.visible.raw
        assert today.sun.visible_change().raw == pytest.approx(expected, abs=1.0)

    def test_polar_day(self, almanac):
        polar = almanac(lat=70.0, lon=25.0, altitude=0.0)
        assert polar.sun.rise.raw is None
        assert polar.sun.set.raw is None
        assert polar.sun.visible.raw == 86400

    def test_polar_night(self, sky):
        with saved_almanacs():
            celestial.register_almanac(sky)
            # 2024-12-21 12:00:00 PST, above the arctic circle
            polar = weewx.almanac.Almanac(1734811200, 70.0, 25.0, altitude=0.0,
                                          formatter=weewx.units.get_default_formatter())
            assert polar.sun.visible.raw == 0
            assert polar.sun.rise.raw is None


class TestPlanets:
    def test_planet_rise_set(self, almanac):
        for planet in ('mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto'):
            binder = getattr(almanac, planet)
            assert binder.rise.raw is not None
            assert binder.set.raw is not None
            assert binder.transit.raw is not None
            assert -90.0 <= binder.alt <= 90.0
            assert 0.0 <= binder.az < 360.0


class TestFallback:
    def test_star_without_catalog_falls_back_to_pyephem(self):
        pytest.importorskip('ephem')
        # Without the Hipparcos catalog, stars fall through to PyEphem.
        starless_sky = celestial.Sky(0, os.path.join(REPO_ROOT, 'bin', 'user'),
                                     weeutil.Moon.moon_phases, ALTITUDE_M, LATITUDE, LONGITUDE)
        with saved_almanacs():
            assert celestial.register_almanac(starless_sky)
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            assert alm.rigel.rise.raw is not None

    def test_unknown_binder_attribute_falls_back(self, almanac):
        pytest.importorskip('ephem')
        # The moon's subsolar latitude is not computed by the Skyfield
        # almanac; PyEphem handles it.
        assert almanac.moon.subsolar_lat is not None

    def test_nonsense_body(self, almanac):
        pytest.importorskip('ephem')
        with pytest.raises(AttributeError):
            almanac.bar.rise

    def test_nonsense_attribute(self, almanac):
        with pytest.raises(AttributeError):
            almanac.sun.foo


class TestPyEphemAgreement:
    """The Skyfield values should closely agree with PyEphem."""

    def test_sun_events_agree(self, almanac):
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer(start_of_day=True)
        sun = ephem.Sun()
        pyephem_rise = weewx.almanac.djd_to_timestamp(observer.next_rising(sun))
        pyephem_set = weewx.almanac.djd_to_timestamp(observer.next_setting(sun))
        assert almanac.sunrise.raw == pytest.approx(pyephem_rise, abs=EPHEM_TOL)
        assert almanac.sunset.raw == pytest.approx(pyephem_set, abs=EPHEM_TOL)


class TestConventions:
    """Behaviors where PyEphem and standard astronomical conventions differ,
    or where the two almanacs must interoperate (see 'Differences from
    PyEphem' in the README)."""

    def test_separation_tuple_form(self, almanac):
        """(longitude, latitude) tuples in radians -> radians, per the
        WeeWX 5.2 almanac API (Meeus 17.1)."""
        import math
        sep = almanac.separation((math.radians(10), math.radians(20)),
                                 (math.radians(30), math.radians(40)))
        assert sep == pytest.approx(0.45948598, abs=1e-6)

    def test_separation_body_form_defers_to_pyephem(self, almanac):
        """PyEphem Body arguments are not tuples; they must pass through to
        PyEphem rather than crash."""
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer()
        mars = ephem.Mars(observer)
        venus = ephem.Venus(observer)
        assert almanac.separation(mars, venus) == pytest.approx(
            float(ephem.separation(mars, venus)), abs=1e-9)

    def test_separation_binder_form(self, skyfield_only_almanac):
        """$almanac.separation($almanac.mars, $almanac.venus) works with this
        almanac's own binders, natively (no PyEphem involved).  Cross-checked
        against the tuple form fed with geocentric coordinates of date."""
        import math
        alm = skyfield_only_almanac
        sep = alm.separation(alm.mars, alm.venus)
        tuple_sep = alm.separation(
            (math.radians(alm.mars.g_ra), math.radians(alm.mars.g_dec)),
            (math.radians(alm.venus.g_ra), math.radians(alm.venus.g_dec)))
        assert sep == pytest.approx(tuple_sep, abs=1e-3)

    def test_separation_mixed_form(self, skyfield_only_almanac):
        """A binder mixed with a coordinate tuple works natively: the
        binder contributes its apparent geocentric coordinates of date."""
        import math
        alm = skyfield_only_almanac
        venus_tuple = (math.radians(alm.venus.g_ra), math.radians(alm.venus.g_dec))
        mixed = alm.separation(alm.mars, venus_tuple)
        assert mixed == pytest.approx(alm.separation(alm.mars, alm.venus), abs=1e-3)

    def test_separation_honors_each_binders_time(self, skyfield_only_almanac):
        """Each binder is observed at its own almanac's time: the moon moves
        ~12 degrees/day, so yesterday's moon is far from today's."""
        import math
        alm = skyfield_only_almanac
        yesterday = alm(almanac_time=TIME_TS - 86400)
        same_day = alm.separation(alm.sun, alm.moon)
        cross_day = alm.separation(alm.sun, yesterday.moon)
        assert abs(math.degrees(cross_day - same_day)) > 5.0

    def test_separation_body_form_without_pyephem(self, skyfield_only_almanac):
        """Without PyEphem, a non-tuple argument finds no almanac that can
        handle it: WeeWX raises ValueError (rather than a crash mid-formula)."""
        class NotATuple:
            pass
        with pytest.raises(ValueError):
            skyfield_only_almanac.separation(NotATuple(), NotATuple())

    def test_sun_hlong_is_earths_heliocentric_longitude(self, almanac):
        """Heliocentric coordinates of the sun itself are undefined; Earth's
        are reported, per the XEphem convention (and never 0.0)."""
        ephem = pytest.importorskip('ephem')
        import math
        observer = pyephem_observer()
        sun = ephem.Sun(observer)
        assert almanac.sun.hlong == pytest.approx(math.degrees(sun.hlong), abs=0.05)

    def test_moon_hlong_is_truly_heliocentric(self, almanac):
        """The moon's hlongitude is its true heliocentric longitude, within
        ~0.15 degrees of Earth's (the moon is close to Earth as seen from the
        sun) -- NOT PyEphem's geocentric redefinition, which differs wildly."""
        ephem = pytest.importorskip('ephem')
        import math
        observer = pyephem_observer()
        moon = ephem.Moon(observer)
        assert almanac.moon.hlong == pytest.approx(almanac.sun.hlong, abs=0.2)
        assert abs(almanac.moon.hlong - math.degrees(moon.hlong)) > 90.0

    def test_pressure_zero_gives_geometric_rise(self, almanac):
        """WeeWX's documented pressure=0 idiom turns refraction off for
        rise/set.  Verified against PyEphem with pressure=0 (both compute
        the geometric upper-limb crossing)."""
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer(start_of_day=True)
        observer.pressure = 0
        sun = ephem.Sun()
        pyephem_rise = weewx.almanac.djd_to_timestamp(observer.next_rising(sun))
        no_refraction = almanac(pressure=0)
        assert no_refraction.sun.rise.raw == pytest.approx(pyephem_rise, abs=EPHEM_TOL)

    def test_pressure_scales_refraction(self, almanac):
        # Less refraction -> the sun appears later: default (1010 mbar)
        # rises earliest, low pressure later, no refraction latest.
        default_rise = almanac.sun.rise.raw
        low_pressure_rise = almanac(pressure=800).sun.rise.raw
        geometric_rise = almanac(pressure=0).sun.rise.raw
        assert default_rise < low_pressure_rise < geometric_rise

    def test_circumpolar_agrees_with_rise_set(self, almanac):
        """At 66.2N on the June solstice the sun's lower culmination is a few
        tenths of a degree below the geometric horizon but above the refracted
        one: rise/set find no crossing, and circumpolar must say True (it is
        judged against the same effective horizon as rise/set)."""
        polar = weewx.almanac.Almanac(TIME_TS, 66.2, LONGITUDE, altitude=ALTITUDE_M,
                                      formatter=weewx.units.get_default_formatter())
        assert polar.sun.rise.raw is None
        assert polar.sun.set.raw is None
        assert polar.sun.circumpolar
        assert not polar.sun.neverup


class TestNativePhysicalEphemeris:
    """Moon libration/colongitude, Jupiter central meridian longitudes and
    Saturn ring tilt, computed natively (these were the last PyEphem
    fallbacks).  All return radians, like PyEphem's."""

    def test_libration_agrees_with_pyephem(self, almanac):
        import math
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer()
        moon = ephem.Moon(observer)
        # Optical libration; the neglected physical libration is < 0.04 deg.
        assert math.degrees(almanac.moon.libration_lat) == pytest.approx(
            math.degrees(moon.libration_lat), abs=0.1)
        assert math.degrees(almanac.moon.libration_long) == pytest.approx(
            math.degrees(moon.libration_long), abs=0.1)
        assert math.degrees(almanac.moon.colong) == pytest.approx(
            math.degrees(moon.colong), abs=0.25)

    def test_colong_definition(self, almanac):
        """Anchor colong to its definition rather than to PyEphem: the
        selenographic colongitude of the sun is ~90 degrees at full moon
        (within the +/-8 degree libration/geometry envelope), and PyEphem
        agrees closely there (both implementations are best-conditioned
        near syzygy)."""
        import math
        ephem = pytest.importorskip('ephem')
        full = almanac(almanac_time=almanac.next_full_moon.raw)
        colong = math.degrees(full.moon.colong)
        assert colong == pytest.approx(90.0, abs=9.0)
        observer = ephem.Observer()
        observer.date = weewx.almanac.timestamp_to_djd(almanac.next_full_moon.raw)
        moon = ephem.Moon(observer)
        assert colong == pytest.approx(math.degrees(moon.colong) % 360.0, abs=0.1)

    def test_libration_range(self, almanac):
        import math
        # Librations never exceed about 8 degrees.
        assert abs(math.degrees(almanac.moon.libration_lat)) < 8.0
        assert abs(math.degrees(almanac.moon.libration_long)) < 8.5

    def test_jupiter_cml(self, almanac):
        """Pinned against the rigorous IAU rotation model (pole + System
        I/II rates), cross-checked with PyEphem.  PyEphem's own values sit
        about 0.8 degrees from the IAU definition, hence the tolerance."""
        import math
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer()
        jupiter = ephem.Jupiter(observer)
        assert math.degrees(almanac.jupiter.cmlI) == pytest.approx(
            math.degrees(jupiter.cmlI), abs=1.2)
        assert math.degrees(almanac.jupiter.cmlII) == pytest.approx(
            math.degrees(jupiter.cmlII), abs=1.2)
        # Regression values (IAU rotation elements, 2025-06-21 12:00 PDT).
        assert math.degrees(almanac.jupiter.cmlI) == pytest.approx(162.19, abs=0.05)
        assert math.degrees(almanac.jupiter.cmlII) == pytest.approx(74.54, abs=0.05)

    def test_saturn_ring_tilt(self, almanac):
        import math
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer()
        saturn = ephem.Saturn(observer)
        assert math.degrees(almanac.saturn.earth_tilt) == pytest.approx(
            math.degrees(saturn.earth_tilt), abs=0.05)
        assert math.degrees(almanac.saturn.sun_tilt) == pytest.approx(
            math.degrees(saturn.sun_tilt), abs=0.05)


class TestPhysicalAttributes:
    """Magnitude, illuminated fraction, angular size, circumpolar status and
    parallactic angle, all computed natively with Skyfield."""

    def test_magnitudes_pinned(self, almanac):
        assert almanac.venus.mag == pytest.approx(-4.20, abs=0.05)
        assert almanac.mars.mag == pytest.approx(1.44, abs=0.05)
        assert almanac.sun.mag == pytest.approx(-26.70, abs=0.05)
        assert almanac.moon.mag == pytest.approx(-8.42, abs=0.1)
        assert almanac.pluto.mag == pytest.approx(14.42, abs=0.1)

    def test_magnitudes_agree_with_pyephem(self, almanac):
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer()
        for planet in ('mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune',
                       'sun', 'moon', 'pluto'):
            body = getattr(ephem, planet.title())()
            body.compute(observer)
            # PyEphem uses older magnitude models, so agreement is loose.
            assert getattr(almanac, planet).mag == pytest.approx(body.mag, abs=0.6), planet

    def test_phase(self, almanac):
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer()
        for planet in ('mercury', 'venus', 'mars', 'moon'):
            body = getattr(ephem, planet.title())()
            body.compute(observer)
            assert getattr(almanac, planet).phase == pytest.approx(body.phase, abs=0.1), planet
        # The sun is fully illuminated, by definition (and per PyEphem).
        assert almanac.sun.phase == 100.0

    def test_size_and_radius(self, almanac):
        ephem = pytest.importorskip('ephem')
        import math
        observer = pyephem_observer()
        for planet in ('sun', 'moon', 'venus', 'jupiter'):
            body = getattr(ephem, planet.title())()
            body.compute(observer)
            binder = getattr(almanac, planet)
            # size is the angular diameter in arcseconds.
            assert binder.size == pytest.approx(body.size, rel=0.02), planet
            # radius is the angular radius in decimal degrees (old-style name).
            assert binder.radius == pytest.approx(math.degrees(body.radius), rel=0.02), planet
            # radius_size is a ValueHelper; its raw value is converted to degrees.
            assert binder.radius_size.raw == pytest.approx(binder.radius, abs=1e-6), planet
        # size is self-consistent with radius.
        assert almanac.sun.size == pytest.approx(almanac.sun.radius * 2.0 * 3600.0, rel=1e-6)

    def test_parallactic_angle(self, almanac):
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer()
        for planet in ('venus', 'moon', 'mars'):
            body = getattr(ephem, planet.title())()
            body.compute(observer)
            assert getattr(almanac, planet).parallactic_angle() == pytest.approx(
                float(body.parallactic_angle()), abs=0.01), planet

    def test_circumpolar_neverup(self, almanac):
        # From 37N, the sun neither stays up nor stays down.
        assert not almanac.sun.circumpolar
        assert not almanac.sun.neverup

    def test_name(self, almanac):
        assert almanac.sun.name == 'Sun'
        assert almanac.mars.name == 'Mars'


@needs_catalog
class TestStars:
    """Named stars, computed natively from the Hipparcos catalog."""

    def test_all_named_stars_loaded(self, sky):
        assert len(sky.stars) == len(set(celestial.NAMED_STARS))
        for name in celestial.NAMED_STARS:
            assert name in sky.stars

    def test_star_positions_and_magnitudes_match_pyephem(self, almanac, sky):
        """Verify the name -> HIP mapping: every star's position and magnitude
        must agree with PyEphem's own catalog."""
        ephem = pytest.importorskip('ephem')
        import math
        observer = pyephem_observer()
        # Compare with refraction off (pressure=0): for a star sitting on the
        # horizon (e.g., Canopus from 37N), the two libraries' refraction
        # models differ by up to a degree, which would mask a mapping error.
        observer.pressure = 0
        no_refraction = almanac(pressure=0)
        compared = 0
        for name in sky.stars:
            pyephem_name = name.replace('_', ' ').title()
            try:
                star = ephem.star(pyephem_name)
            except KeyError:
                # An IAU name beyond PyEphem's catalog: nothing to compare.
                continue
            compared += 1
            star.compute(observer)
            binder = getattr(no_refraction, name)
            az1, alt1 = math.radians(binder.az), math.radians(binder.alt)
            az2, alt2 = float(star.az), float(star.alt)
            separation = math.degrees(math.acos(min(1.0,
                math.sin(alt1) * math.sin(alt2)
                + math.cos(alt1) * math.cos(alt2) * math.cos(az1 - az2))))
            assert separation < 0.1, '%s is %f degrees from PyEphem position' % (name, separation)
            assert binder.mag == pytest.approx(star.mag, abs=1.5), name
        # Every PyEphem-known name must actually have been compared.
        assert compared >= 100

    def test_star_rise_set_transit(self, almanac):
        assert almanac.rigel.rise.raw is not None
        assert almanac.rigel.set.raw is not None
        assert almanac.rigel.rise.raw < almanac.rigel.transit.raw < almanac.rigel.set.raw + 86400
        assert str(almanac.rigel.visible.long_form())

    def test_star_rise_agrees_with_pyephem(self, almanac):
        ephem = pytest.importorskip('ephem')
        observer = pyephem_observer(start_of_day=True)
        star = ephem.star('Rigel')
        pyephem_rise = weewx.almanac.djd_to_timestamp(observer.next_rising(star))
        assert almanac.rigel.rise.raw == pytest.approx(pyephem_rise, abs=EPHEM_TOL)

    def test_star_circumpolar(self, almanac):
        # From 37N, Polaris never sets and Acrux (Southern Cross) never rises.
        assert almanac.polaris.circumpolar
        assert not almanac.polaris.neverup
        assert almanac.acrux.neverup
        assert almanac.polaris.rise.raw is None
        assert almanac.acrux.rise.raw is None
        assert almanac.polaris.visible.raw == 86400
        assert almanac.acrux.visible.raw == 0

    def test_star_multiword_name(self, almanac):
        assert almanac.kaus_australis.name == 'Kaus Australis'
        assert almanac.kaus_australis.rise.raw is not None

    def test_iau_star_names(self, almanac, sky):
        """The name table is the IAU Catalog of Star Names (every entry with
        a Hipparcos number) plus PyEphem's names as aliases."""
        assert len(celestial.NAMED_STARS) >= 400
        # An IAU name PyEphem never had: Barnard's Star (HIP 87937), the
        # highest-proper-motion star in the sky.
        assert almanac.barnards_star.mag == pytest.approx(9.54, abs=0.1)
        assert 'Barnards Star' in almanac.barnards_star.name
        # PyEphem's legacy spellings still work, mapping to the same stars
        # as the IAU spellings.
        assert celestial.NAMED_STARS['alcaid'] == celestial.NAMED_STARS['alkaid']
        assert celestial.NAMED_STARS['albereo'] == celestial.NAMED_STARS['albireo']
        assert celestial.NAMED_STARS['sirrah'] == celestial.NAMED_STARS['alpheratz']
        # Alula Australis has no astrometric solution in hip_main.dat; its
        # position comes from the identification columns.
        assert sky.stars['alula_australis'][0].dec.degrees == pytest.approx(31.53, abs=0.01)

    def test_hip_number_tags(self, almanac, sky):
        """Any Hipparcos star in the available catalog can be addressed by
        number: $almanac.hip_57939.  Loaded lazily and cached; misses are
        cached too and fall through to the next almanac (AttributeError)."""
        # HIP 32349 is Sirius: the hip_ tag serves the same star as the name.
        assert almanac.hip_32349.mag == almanac.sirius.mag
        assert almanac.hip_32349.rise.raw == pytest.approx(almanac.sirius.rise.raw, abs=1.0)
        assert 'hip_32349' in sky.stars    # cached
        # A HIP number not in the bundled excerpt (Groombridge 1830, mag 6.4)
        # is a miss unless a full hip_main.dat is installed.
        full_catalog = os.path.exists(os.path.join(REPO_ROOT, 'bin', 'user', 'hip_main.dat'))
        if full_catalog:
            assert almanac.hip_57939.mag == pytest.approx(6.42, abs=0.1)
        else:
            with pytest.raises(AttributeError):
                almanac.hip_57939.mag
            assert 57939 in sky.hip_misses    # the miss is cached

    def test_hip_tag_leading_zeros(self, almanac):
        """Catalogs zero-pad HIP numbers ('HIP 032349'); the zero-padded tag
        must serve the same star as the canonical one."""
        assert almanac.hip_032349.mag == almanac.hip_32349.mag == almanac.sirius.mag

    def test_hip_tag_reuses_loaded_star(self, almanac, sky):
        """A hip_ tag for a star already loaded under a name is aliased
        without rescanning the catalog."""
        rigel_hip = celestial.NAMED_STARS['rigel']
        assert getattr(almanac, 'hip_%d' % rigel_hip).mag == almanac.rigel.mag
        assert sky.stars['hip_%d' % rigel_hip] is sky.stars['rigel']

    def test_missing_catalog_degrades_per_tag(self, tmp_path):
        """stars=true with an absent/unreadable catalog file must degrade to
        per-tag AttributeError, never leak OSError into report generation."""
        (tmp_path / 'celestial_de421.bsp').symlink_to(
            os.path.join(REPO_ROOT, 'bin', 'user', 'celestial_de421.bsp'))
        crippled = celestial.Sky(0, str(tmp_path), weeutil.Moon.moon_phases,
                                 ALTITUDE_M, LATITUDE, LONGITUDE, load_stars=True)
        assert crippled.is_valid()
        assert crippled.stars == {}
        assert not crippled.load_stars    # disabled by the failed load
        with saved_almanacs():
            assert celestial.register_almanac(crippled)
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            with pytest.raises(AttributeError):
                alm.hip_32349.mag

    def test_rigil_kentaurus_is_alpha_cen_a(self, almanac):
        """Rigil Kentaurus is the IAU name for Alpha Centauri A (HIP 71683,
        mag -0.01), not its close binary companion Alpha Cen B (HIP 71681,
        mag 1.35).  The pair is too close for the general 0.1-degree position
        audit to tell apart, so pin the identity here."""
        assert celestial.NAMED_STARS['rigil_kentaurus'] == 71683
        assert almanac.rigil_kentaurus.mag == pytest.approx(-0.01, abs=0.05)

    def test_malformed_record_skips_only_that_star(self, tmp_path):
        """One bad catalog record must disable only that star, not the
        whole catalog."""
        good = None
        with open(os.path.join(REPO_ROOT, 'bin', 'user', celestial.STAR_FILE)) as f:
            for line in f:
                if line.startswith('H|') and line.split('|')[1].strip() == '32349':
                    good = line
                    break
        assert good is not None
        vega_hip = celestial.NAMED_STARS['vega']
        truncated = 'H|%12d| |18 36 56.34|+38 47 01.3\n' % vega_hip
        bad_mag = good.split('|')
        bad_mag[1] = '%12d' % celestial.NAMED_STARS['rigel']
        bad_mag[5] = ' x.xx'
        (tmp_path / celestial.STAR_FILE).write_text(good + truncated + '|'.join(bad_mag))
        stars = celestial.Sky.load_named_stars(str(tmp_path))
        assert 'sirius' in stars
        assert 'vega' not in stars
        assert 'rigel' not in stars

    def test_star_unsupported_attributes(self, almanac):
        # A star has no phase (nor does PyEphem's).
        with pytest.raises(AttributeError):
            almanac.rigel.phase
        with pytest.raises(AttributeError):
            almanac.rigel.hlong

    def test_star_earth_distance(self, almanac):
        """Unlike PyEphem, earth_distance and sun_distance work for stars
        with a parallax (in AU, like the planets).  Hipparcos puts Rigel at
        ~773 light years; at that distance the two differ by at most 1 AU."""
        assert almanac.rigel.earth_distance / celestial.AU_PER_LIGHT_YEAR == pytest.approx(773.0, abs=5.0)
        assert abs(almanac.rigel.sun_distance - almanac.rigel.earth_distance) <= 1.0

    def test_proxima_centauri(self, almanac, sky):
        """The one star beyond PyEphem's catalog: the nearest star, at 4.22
        light years (Hipparcos parallax 772.33 mas), mag 11.01.  The loop
        packet reports the same distance, in light years."""
        assert celestial.NAMED_STARS['proxima_centauri'] == 70890
        assert almanac.proxima_centauri.mag == pytest.approx(11.01, abs=0.05)
        ly = almanac.proxima_centauri.earth_distance / celestial.AU_PER_LIGHT_YEAR
        assert ly == pytest.approx(4.223, abs=0.01)
        # From 37N, Proxima (dec -62.7) never rises.
        assert almanac.proxima_centauri.neverup
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        assert pkt['earthProximaCentauriDistance'] == pytest.approx(ly, abs=1e-6)


# Every category of tag the built-in PyEphem almanac supports, including
# direct PyEphem body attributes.  With PyEphem installed, all of these must
# evaluate: natively via Skyfield where possible, via the PyEphem fallback
# otherwise.
PYEPHEM_PARITY_EXPRESSIONS = [
    "almanac.moon_fullness", "almanac.moon.moon_fullness",
    "almanac.sunrise", "almanac.sunset", "almanac.moon_phase", "almanac.moon_index",
    "almanac.sun.rise", "almanac.sun.transit", "almanac.sun.set",
    "almanac.moon.rise", "almanac.moon.transit", "almanac.moon.set",
    "almanac.mars.rise", "almanac.mars.transit", "almanac.mars.set",
    "almanac.rigel.rise", "almanac.rigel.transit", "almanac.rigel.set",
    "almanac.sidereal_time", "almanac.sidereal_angle",
    "almanac.next_vernal_equinox", "almanac.next_autumnal_equinox",
    "almanac.next_summer_solstice", "almanac.previous_winter_solstice",
    "almanac.next_winter_solstice",
    "almanac.next_full_moon", "almanac.next_new_moon",
    "almanac.next_first_quarter_moon", "almanac.previous_last_quarter_moon",
    "almanac.sun.az", "almanac.sun.alt", "almanac.moon.az", "almanac.moon.alt",
    "almanac.sun.azimuth", "almanac.sun.altitude",
    "almanac.moon.azimuth", "almanac.moon.altitude",
    "almanac(horizon=-6).sun(use_center=1).rise",
    "almanac(pressure=0, horizon=-34.0/60.0).sun.previous_rising",
    "almanac.moon.next_setting", "almanac.sun.next_antitransit",
    "almanac.mars.sun_distance", "almanac.mars.earth_distance",
    "almanac.jupiter.cmlI", "almanac.jupiter.cmlII",
    "almanac.venus.mag", "almanac.venus.phase",
    "almanac.sun.size", "almanac.moon.radius_size",
    "almanac.moon.libration_lat", "almanac.moon.libration_long", "almanac.moon.colong",
    "almanac.saturn.earth_tilt",
    "almanac.mercury.elong", "almanac.mercury.elongation",
    "almanac.sun.hlong", "almanac.mars.hlongitude", "almanac.mars.hlatitude",
    "almanac.sun.a_ra", "almanac.sun.a_dec", "almanac.sun.g_ra", "almanac.sun.g_dec",
    "almanac.sun.astro_ra", "almanac.sun.geo_dec",
    "almanac.sun.topo_ra", "almanac.sun.topo_dec",
    "almanac.sun.name", "almanac.venus.circumpolar", "almanac.venus.neverup",
    "almanac.sun.parallactic_angle()",
    "almanac.polaris.az", "almanac.polaris.alt",
    "almanac.separation((almanac.venus.a_ra, almanac.venus.a_dec), (almanac.mars.a_ra, almanac.mars.a_dec))",
    "almanac.sun.visible", "almanac.sun.visible_change()", "almanac.moon.visible",
]

# These raise AttributeError on the built-in almanac too (PyEphem limitations);
# the Skyfield almanac must fail the same way rather than crash differently.
PYEPHEM_PARITY_ATTRIBUTE_ERRORS = [
    "almanac.venus.cmlI",
    "almanac.sun.foo",
    "almanac.moon.sublatitude",
    "almanac.moon.sublongitude",
    "almanac.io.rise",
]


class TestPyEphemParityAudit:
    """With PyEphem installed, everything the built-in almanac can do must
    still work with the Skyfield almanac registered."""

    @pytest.fixture(autouse=True)
    def _require_ephem(self):
        pytest.importorskip('ephem')

    @pytest.mark.parametrize('expression', PYEPHEM_PARITY_EXPRESSIONS)
    def test_expression_evaluates(self, almanac, expression):
        value = eval(expression)
        assert value is not None
        assert str(value) != ''

    @pytest.mark.parametrize('expression', PYEPHEM_PARITY_ATTRIBUTE_ERRORS)
    def test_expression_raises_attribute_error(self, almanac, expression):
        with pytest.raises(AttributeError):
            eval(expression)


# Everything that must work on a system with no PyEphem at all (a
# Skyfield-only installation).
SKYFIELD_ONLY_EXPRESSIONS = [
    "almanac.hasExtras",
    "almanac.moon_fullness", "almanac.moon.moon_fullness",
    "almanac.sunrise", "almanac.sunset", "almanac.moon_phase", "almanac.moon_index",
    "almanac.sun.rise", "almanac.sun.transit", "almanac.sun.set",
    "almanac.moon.rise", "almanac.moon.transit", "almanac.moon.set",
    "almanac.mars.rise", "almanac.mars.transit", "almanac.mars.set",
    "almanac.sidereal_time", "almanac.sidereal_angle",
    "almanac.next_vernal_equinox", "almanac.next_autumnal_equinox",
    "almanac.next_summer_solstice", "almanac.previous_winter_solstice",
    "almanac.next_winter_solstice", "almanac.next_equinox", "almanac.next_solstice",
    "almanac.next_full_moon", "almanac.next_new_moon",
    "almanac.next_first_quarter_moon", "almanac.previous_last_quarter_moon",
    "almanac.sun.az", "almanac.sun.alt", "almanac.moon.az", "almanac.moon.alt",
    "almanac.sun.azimuth", "almanac.sun.altitude",
    "almanac.moon.azimuth", "almanac.moon.altitude",
    "almanac.sun.topo_ra", "almanac.sun.topo_dec",
    "almanac.sun.astro_ra", "almanac.sun.geo_dec",
    "almanac(horizon=-6).sun(use_center=1).rise",
    "almanac(pressure=0, horizon=-34.0/60.0).sun.previous_rising",
    "almanac.moon.next_setting", "almanac.sun.next_antitransit",
    "almanac.mars.sun_distance", "almanac.mars.earth_distance",
    "almanac.moon.libration_lat", "almanac.moon.libration_long", "almanac.moon.colong",
    "almanac.jupiter.cmlI", "almanac.jupiter.cmlII",
    "almanac.saturn.earth_tilt", "almanac.saturn.sun_tilt",
    "almanac.separation(almanac.mars, almanac.venus)",
    "almanac.sun.phase",
    "almanac.mercury.mag", "almanac.venus.mag", "almanac.mars.mag",
    "almanac.jupiter.mag", "almanac.saturn.mag", "almanac.uranus.mag",
    "almanac.neptune.mag", "almanac.sun.mag", "almanac.moon.mag", "almanac.pluto.mag",
    "almanac.venus.phase", "almanac.mars.phase",
    "almanac.sun.size", "almanac.moon.size", "almanac.moon.radius", "almanac.moon.radius_size",
    "almanac.sun.circumpolar", "almanac.sun.neverup",
    "almanac.venus.parallactic_angle()", "almanac.sun.name",
    "almanac.mercury.elong", "almanac.mercury.elongation",
    "almanac.sun.hlong", "almanac.mars.hlongitude", "almanac.mars.hlatitude",
    "almanac.separation((0.1, 0.2), (0.3, 0.4))",
    "almanac.sun.visible", "almanac.sun.visible_change()", "almanac.moon.visible",
]

SKYFIELD_ONLY_STAR_EXPRESSIONS = [
    "almanac.rigel.rise", "almanac.rigel.set", "almanac.rigel.transit",
    "almanac.rigel.az", "almanac.rigel.alt", "almanac.rigel.mag",
    "almanac.polaris.circumpolar", "almanac.sirius.azimuth",
    "almanac.vega.next_rising", "almanac.rigel.visible",
    "almanac.rigel.earth_distance", "almanac.rigel.sun_distance",
    "almanac.proxima_centauri.earth_distance", "almanac.barnards_star.mag",
    "almanac.hip_32349.mag",
]


class TestSkyfieldOnlyAudit:
    """Everything a Skyfield-only installation (no PyEphem) must support."""

    def test_has_extras(self, skyfield_only_almanac):
        assert skyfield_only_almanac.hasExtras

    @pytest.mark.parametrize('expression', SKYFIELD_ONLY_EXPRESSIONS)
    def test_expression_evaluates(self, skyfield_only_almanac, expression):
        value = eval(expression, {'almanac': skyfield_only_almanac})
        assert value is not None
        assert str(value) != ''

    @needs_catalog
    @pytest.mark.parametrize('expression', SKYFIELD_ONLY_STAR_EXPRESSIONS)
    def test_star_expression_evaluates(self, skyfield_only_almanac, expression):
        value = eval(expression, {'almanac': skyfield_only_almanac})
        assert value is not None
        assert str(value) != ''

    def test_pyephem_only_attributes_raise(self, skyfield_only_almanac):
        # Without PyEphem, its exclusive attributes raise AttributeError
        # (a per-tag error in a report, not a crash).
        with pytest.raises(AttributeError):
            skyfield_only_almanac.moon.subsolar_lat

    def test_seasons_tags_without_pyephem(self, skyfield_only_almanac):
        """Every tag the Seasons skin uses must work without PyEphem."""
        for expression in [
                "almanac(horizon=-6).sun(use_center=1).rise",
                "almanac.moon.altitude", "almanac.moon.azimuth",
                "almanac.moon_fullness", "almanac.moon_phase",
                "almanac.moon.rise", "almanac.moon.set", "almanac.moon.transit",
                "almanac.moon.topo_dec", "almanac.moon.topo_ra",
                "almanac.next_equinox", "almanac.next_full_moon",
                "almanac.next_new_moon", "almanac.next_solstice",
                "almanac.sun.alt", "almanac.sun.altitude", "almanac.sun.azimuth",
                "almanac.sunrise", "almanac.sun.rise", "almanac.sunset", "almanac.sun.set",
                "almanac.sun.topo_dec", "almanac.sun.topo_ra", "almanac.sun.transit",
                "almanac.sun.visible_change()", "almanac.sun.visible.long_form()"]:
            value = eval(expression, {'almanac': skyfield_only_almanac})
            assert value is not None and str(value) != '', expression


class TestSampleSkinRenders:
    """Render the bundled sample skin end to end, through Cheetah's
    errorCatcher, exactly as weewx does.  Template.compile alone is NOT
    enough: with #errorCatcher Echo, Cheetah re-compiles each placeholder's
    source at render time, and that path rejects constructs plain
    compilation accepts (e.g. a conditional expression inside $(...) loses
    its else-value and dies with SyntaxError only at render time)."""

    @staticmethod
    def render(almanac_obj):
        from Cheetah.Template import Template

        class Obj:
            def __init__(self, **kw):
                self.__dict__.update(kw)

        class Extras(dict):
            def has_key(self, key):
                return key in self

        skin_dir = os.path.join(REPO_ROOT, 'skins', 'Celestial')
        source = open(os.path.join(skin_dir, 'index.html.tmpl')).read()
        # Inline the include so its directives and placeholders are also
        # exercised through the errorCatcher render path.
        include = open(os.path.join(skin_dir, 'realtime_updater.inc')).read()
        assert '#include "realtime_updater.inc"' in source
        source = source.replace('#include "realtime_updater.inc"', include)
        template = Template(source, searchList=[{
            'almanac': almanac_obj,
            'current': Obj(dateTime=Obj(raw=TIME_TS)),
            'unit': Obj(label=Obj(earthMoonDistance=' miles'),
                        unit_type=Obj(earthMoonDistance='mile')),
            'station': Obj(location='Test Station'),
            'Extras': Extras(loop_data_file='/gauge-data/loop-data.txt',
                             expiration_time=86400, refresh_rate=2),
        }])
        return str(template)

    def cell(self, html, cell_id):
        import re
        match = re.search(r'id="%s"[^>]*>([^<]*)<' % re.escape(cell_id), html)
        assert match is not None, cell_id
        return match.group(1)

    def test_renders_with_skyfield_almanac(self, almanac):
        html = self.render(almanac)
        assert ':' in self.cell(html, 'current.sunrise.raw')            # a time
        assert '&deg;' in self.cell(html, 'current.moonAzimuth.raw')    # an angle
        assert 'miles' in self.cell(html, 'current.earthPlutoDistance')
        assert 'light years' in self.cell(html, 'current.earthProximaCentauriDistance.raw')
        assert 'than yesterday' in html                                 # daylight computed
        # The inlined realtime_updater.inc rendered too.
        assert 'function lookup(' in html
        assert '/gauge-data/loop-data.txt' in html

    def test_template_constants_match_celestial(self):
        """The template hardcodes unit constants (it cannot import
        celestial.py); they must equal the module's."""
        import re
        source = open(os.path.join(REPO_ROOT, 'skins', 'Celestial', 'index.html.tmpl')).read()
        per_au = {float(m) for m in re.findall(r'\$per_au = ([0-9.e+]+)', source)}
        assert per_au == {celestial.AU_MILES, celestial.AU_KM}
        light_year = re.search(r'earth_distance / ([0-9.]+)', source)
        assert float(light_year.group(1)) == celestial.AU_PER_LIGHT_YEAR

    def test_renders_without_extended_almanac(self, sky):
        """With only the weeutil almanac (no PyEphem, no Skyfield), the page
        must still generate, with empty javascript-filled cells as in 2.x."""
        with saved_almanacs():
            weewx.almanac.almanacs[:] = [weewx.almanac.WeeutilAlmanacType()]
            plain = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                          formatter=weewx.units.get_default_formatter())
            assert not plain.hasExtras
            html = self.render(plain)
        assert self.cell(html, 'current.sunrise.raw') == ''
        assert self.cell(html, 'current.earthProximaCentauriDistance.raw') == ''
        assert 'Proxima Centauri' in html


class TestSeasonsSkinTags:
    """Every almanac tag used by WeeWX's Seasons skin must evaluate."""

    def test_all_tags_evaluate(self, almanac):
        sun_none = 'none'
        tags = [
            lambda: almanac.hasExtras,
            lambda: str(almanac(horizon=-6).sun(use_center=1).rise),
            lambda: str(almanac(horizon=-6).sun(use_center=1).set),
            lambda: str(almanac.moon.altitude.format("%.1f")),
            lambda: str(almanac.moon.azimuth.format("%.1f")),
            lambda: almanac.moon_fullness,
            lambda: almanac.moon_phase,
            lambda: str(almanac.moon.rise),
            lambda: str(almanac.moon.set),
            lambda: str(almanac.moon.topo_dec.format("%.1f")),
            lambda: str(almanac.moon.topo_ra.format("%.1f")),
            lambda: str(almanac.moon.transit),
            lambda: str(almanac.next_equinox),
            lambda: almanac.next_equinox.raw,
            lambda: str(almanac.next_full_moon),
            lambda: almanac.next_full_moon.raw,
            lambda: str(almanac.next_new_moon),
            lambda: almanac.next_new_moon.raw,
            lambda: str(almanac.next_solstice),
            lambda: almanac.next_solstice.raw,
            lambda: almanac.sun.alt,
            lambda: str(almanac.sun.altitude),
            lambda: str(almanac.sun.azimuth.format("%.1f")),
            lambda: str(almanac.sunrise),
            lambda: str(almanac.sun.rise.format(None_string=sun_none)),
            lambda: almanac.sun.rise.raw,
            lambda: str(almanac.sunset),
            lambda: str(almanac.sun.set.format(None_string=sun_none)),
            lambda: almanac.sun.set.raw,
            lambda: str(almanac.sun.topo_dec.format("%.1f")),
            lambda: str(almanac.sun.topo_ra.format("%.1f")),
            lambda: str(almanac.sun.transit),
            lambda: str(almanac.sun.visible_change()),
            lambda: str(almanac.sun.visible.long_form()),
        ]
        for i, tag in enumerate(tags):
            value = tag()
            assert value is not None and value != '', 'tag %d evaluated to %r' % (i, value)


class TestDistanceUnits:
    """Distances must be km for both METRIC and METRICWX, miles for US."""

    MOON_KM = (356000.0, 407000.0)     # perigee..apogee
    MOON_MILES = (221000.0, 253000.0)

    def insert(self, sky, us_units):
        pkt = {'dateTime': TIME_TS, 'usUnits': us_units}
        sky.insert_fields(pkt)
        return pkt

    def test_us_distances_in_miles(self, sky):
        pkt = self.insert(sky, weewx.US)
        assert self.MOON_MILES[0] < pkt['earthMoonDistance'] < self.MOON_MILES[1]

    def test_metric_distances_in_km(self, sky):
        pkt = self.insert(sky, weewx.METRIC)
        assert self.MOON_KM[0] < pkt['earthMoonDistance'] < self.MOON_KM[1]

    def test_metricwx_distances_in_km(self, sky):
        # Regression: METRICWX packets used to get miles.
        pkt = self.insert(sky, weewx.METRICWX)
        assert self.MOON_KM[0] < pkt['earthMoonDistance'] < self.MOON_KM[1]


class TestDeprecatedFieldAliases:
    """In 3.0, every loop value is emitted under both its new (lowerCamelCase)
    name and its deprecated pre-3.0 name.  The old names go away in 4.0."""

    def test_all_new_names_present(self, sky):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        for name in celestial.OBS_GROUPS:
            if name == 'earthProximaCentauriDistance' and not sky.stars:
                continue    # needs the star catalog
            assert name in pkt, 'missing new-name field %s' % name

    def test_deprecated_names_match_new_names(self, sky):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        assert len(celestial.DEPRECATED_FIELD_MAP) == 38
        for old_name, new_name in celestial.DEPRECATED_FIELD_MAP.items():
            assert old_name in pkt, 'missing deprecated field %s' % old_name
            assert pkt[old_name] == pkt[new_name], '%s != %s' % (old_name, new_name)

    def test_deprecated_names_survive_caching(self):
        # With update_rate_secs > 0, cached (prev_reading) packets must also
        # carry both names.
        sky = celestial.Sky(300, os.path.join(REPO_ROOT, 'bin', 'user'),
                            weeutil.Moon.moon_phases, ALTITUDE_M, LATITUDE, LONGITUDE)
        pkt1 = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt1)
        # A second packet within update_rate_secs is served from the cache.
        pkt2 = {'dateTime': TIME_TS + 2, 'usUnits': weewx.US}
        sky.insert_fields(pkt2)
        assert pkt2['sunrise'] == pkt1['sunrise']
        assert pkt2['Sunrise'] == pkt1['sunrise']
        assert pkt2['daylightDur'] == pkt1['daylightDur']
        assert pkt2['daySunshineDur'] == pkt1['daylightDur']

    def test_obs_groups_registered_for_both_names(self):
        for name, group in celestial.OBS_GROUPS.items():
            assert weewx.units.obs_group_dict.get(name) == group
        for old_name, new_name in celestial.DEPRECATED_FIELD_MAP.items():
            assert weewx.units.obs_group_dict.get(old_name) == celestial.OBS_GROUPS[new_name]


class TestPolarDaylight:
    """Edge cases of daySunshineDur around the polar day/night transitions.
    Uses latitude 70N at longitude -120 (which roughly matches the pinned
    America/Los_Angeles timezone, so local midnight is near solar midnight)."""

    @pytest.fixture(scope='class')
    @staticmethod
    def polar_sky():
        s = celestial.Sky(0, os.path.join(REPO_ROOT, 'bin', 'user'),
                          weeutil.Moon.moon_phases, 0.0, 70.0, -120.0)
        assert s.is_valid()
        return s

    @staticmethod
    def day_start(y, m, d):
        from datetime import datetime, timezone
        return datetime.fromtimestamp(datetime(y, m, d).timestamp(), timezone.utc)

    def test_polar_day(self, polar_sky):
        _, _, _, daylight = polar_sky.get_sunrise_sunset_transit_daylight(
            polar_sky.ts, self.day_start(2025, 6, 21))
        assert daylight == 86400

    def test_polar_night(self, polar_sky):
        _, _, _, daylight = polar_sky.get_sunrise_sunset_transit_daylight(
            polar_sky.ts, self.day_start(2024, 12, 21))
        assert daylight == 0

    def test_sun_rose_but_never_set(self, polar_sky):
        # First day of polar day: the sun rises and stays up.  This used to
        # crash with AttributeError (skyfield Time has no timestamp()).
        sunrise, sunset, _, daylight = polar_sky.get_sunrise_sunset_transit_daylight(
            polar_sky.ts, self.day_start(2025, 5, 13))
        assert sunrise is not None
        assert sunset is None
        assert daylight == pytest.approx(79279, abs=120)

    def test_sun_up_at_midnight(self):
        # At 70N, 25E viewed in the Pacific timezone, the local day starts
        # with the sun up; it sets, then rises again.  The old formula
        # (set - rise) produced a negative daylight here.
        sky = celestial.Sky(0, os.path.join(REPO_ROOT, 'bin', 'user'),
                            weeutil.Moon.moon_phases, 0.0, 70.0, 25.0)
        sunrise, sunset, _, daylight = sky.get_sunrise_sunset_transit_daylight(
            sky.ts, self.day_start(2025, 5, 15))
        assert sunrise is not None and sunset is not None
        assert sunset < sunrise
        assert daylight == pytest.approx(86400 - 2506, abs=120)
        assert 0 <= daylight <= 86400


class TestLoopPacketConsistency:
    """The report almanac and the loop packet fields must agree."""

    def test_zero_celsius_is_a_measurement(self, sky):
        """outTemp of exactly 0.0 degC must be used for refraction, not
        treated as missing: the sun's refracted altitude at sunrise must
        vary monotonically as the temperature passes through zero."""
        from datetime import datetime, timezone
        sunrise_dt = datetime.fromtimestamp(1750510082, timezone.utc)
        alts = [sky.get_az_alt_ra_dec(sky.ts, sky.sun, sunrise_dt, tempC, 1013.0)[1]
                for tempC in (-0.5, 0.0, 0.5)]
        assert alts[0] > alts[1] > alts[2]    # colder air refracts more

    def test_sunrise_matches_loop_packet(self, sky, almanac):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US, 'outTemp': 65.0, 'barometer': 30.0}
        sky.insert_fields(pkt)
        assert pkt['sunrise'] == pytest.approx(almanac.sunrise.raw, abs=1.0)
        assert pkt['sunset'] == pytest.approx(almanac.sunset.raw, abs=1.0)
        assert pkt['moonrise'] == pytest.approx(almanac.moon.rise.raw, abs=1.0)
        assert pkt['sunTransit'] == pytest.approx(almanac.sun.transit.raw, abs=1.0)
        assert pkt['nextFullMoon'] == pytest.approx(almanac.next_full_moon.raw, abs=1.0)
        assert pkt['nextEquinox'] == pytest.approx(almanac.next_equinox.raw, abs=1.0)
        assert pkt['moonPhase'] == almanac.moon_phase

    def test_twilight_and_daylight_match_loop_packet(self, sky, almanac):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        assert pkt['civilTwilightStart'] == pytest.approx(
            almanac(horizon=-6).sun(use_center=1).rise.raw, abs=1.0)
        assert pkt['nauticalTwilightEnd'] == pytest.approx(
            almanac(horizon=-12).sun(use_center=1).set.raw, abs=1.0)
        assert pkt['astronomicalTwilightStart'] == pytest.approx(
            almanac(horizon=-18).sun(use_center=1).rise.raw, abs=1.0)
        assert pkt['daylightDur'] == pytest.approx(almanac.sun.visible.raw, abs=1.0)
        assert pkt['yesterdayDaylightDur'] == pytest.approx(
            almanac(almanac_time=TIME_TS - 86400).sun.visible.raw, abs=1.0)
        assert pkt['tomorrowSunrise'] == pytest.approx(
            almanac(almanac_time=TIME_TS + 86400).sunrise.raw, abs=1.0)

    def test_ra_dec_match_loop_packet(self, sky, almanac):
        # The loop packet's RA/Dec are in coordinates of date, matching the
        # almanac's topo_ra/topo_dec.
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        assert pkt['sunRightAscension'] == pytest.approx(almanac.sun.topo_ra.raw, abs=1e-3)
        assert pkt['sunDeclination'] == pytest.approx(almanac.sun.topo_dec.raw, abs=1e-3)
        assert pkt['moonRightAscension'] == pytest.approx(almanac.moon.topo_ra.raw, abs=1e-3)
        assert pkt['moonDeclination'] == pytest.approx(almanac.moon.topo_dec.raw, abs=1e-3)

    def test_distances_match_loop_packet(self, sky, almanac):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.METRIC}
        sky.insert_fields(pkt)
        km_per_au = celestial.AU_KM
        assert pkt['earthSunDistance'] == pytest.approx(almanac.sun.earth_distance * km_per_au, rel=1e-9)
        assert pkt['earthMoonDistance'] == pytest.approx(almanac.moon.earth_distance * km_per_au, rel=1e-9)
        assert pkt['earthPlutoDistance'] == pytest.approx(almanac.pluto.earth_distance * km_per_au, rel=1e-9)
