"""
test_celestial.py

Copyright (C)2022-2025 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Tests for the Celestial loop-field service and its Sky engine.

Run with the WeeWX virtual environment's Python, from the root of this repo:
    /home/weewx/weewx-venv/bin/python -m pytest tests

The expected values below were computed with Skyfield 1.54 and JPL's de421
ephemeris for Palo Alto, CA on 2025-06-21 (summer solstice weekend), and were
sanity checked against PyEphem and published almanac data.  They serve as
regression values.  In addition, when the independent weewx-skyfield
extension is available, the loop fields are cross-checked against its report
almanac (the two extensions share the same definitions, so their values must
agree).
"""

import contextlib
import os
import shutil
import sys
import time

import pytest

import skyfield.api

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TEST_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, 'bin', 'user'))

# The expected values (and WeeWX's notion of "today's" rise/set) depend on
# the local timezone, so pin it.
os.environ['TZ'] = 'America/Los_Angeles'
time.tzset()

import weeutil.Moon
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

# The stars come from celestial_stars.dat, a small excerpt of the Hipparcos
# catalog that ships with the extension.
CATALOG_PRESENT = os.path.exists(os.path.join(REPO_ROOT, 'bin', 'user', celestial.STAR_FILE))
needs_catalog = pytest.mark.skipif(not CATALOG_PRESENT, reason='%s not present' % celestial.STAR_FILE)

# Where the independent weewx-skyfield extension may be found: the installed
# copy on this machine, or a sibling checkout of its repo.
WXSKYFIELD_DIRS = [
    '/home/weewx/weewx-data/bin/user',
    os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield', 'bin', 'user'),
]


def load_wxskyfield():
    """Import the weewx-skyfield extension (the report-almanac oracle for
    the loop-field cross-checks) and return (module, its user_root), or
    skip the calling test."""
    for d in WXSKYFIELD_DIRS:
        if os.path.exists(os.path.join(d, 'wxskyfield.py')):
            if d not in sys.path:
                # Append, NOT insert(0): these directories also hold a
                # celestial.py, which must not shadow the one under test.
                sys.path.append(d)
            import wxskyfield
            return wxskyfield, d
    pytest.skip('the weewx-skyfield extension is not available')


def load_wxskyfield_sky():
    """Import weewx-skyfield's sky-page module (the $sky_page SVG panels the
    sample skin embeds), or skip the calling test."""
    for d in WXSKYFIELD_DIRS:
        if os.path.exists(os.path.join(d, 'wxskyfield_sky.py')):
            if d not in sys.path:
                sys.path.append(d)     # append, NOT insert(0); see above
            import wxskyfield_sky
            return wxskyfield_sky
    pytest.skip('the weewx-skyfield sky page is not available')


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


@pytest.fixture(scope='session')
def wxskyfield_sky():
    mod, user_root = load_wxskyfield()
    s = mod.Sky(user_root, load_stars=True)
    assert s.is_valid()
    return s


@pytest.fixture()
def wxskyfield_almanac(wxskyfield_sky):
    """An Almanac served by the weewx-skyfield extension's almanac."""
    mod, _ = load_wxskyfield()
    with saved_almanacs():
        assert mod.register_almanac(wxskyfield_sky)
        yield weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                    formatter=weewx.units.get_default_formatter())


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
    def test_service_binds_loop(self):
        engine = StubEngine()
        celestial.Celestial(engine, make_config())
        assert weewx.NEW_LOOP_PACKET in engine.bound

    def test_service_disabled(self):
        engine = StubEngine()
        celestial.Celestial(engine, make_config(enable='false'))
        assert engine.bound == []

    @needs_catalog
    def test_service_stars_default_on(self):
        engine = StubEngine()
        service = celestial.Celestial(engine, make_config())
        assert set(service.sky.stars) == set(celestial.LOOP_STARS)

    def test_service_stars_disabled(self):
        engine = StubEngine()
        service = celestial.Celestial(engine, make_config(stars='false'))
        assert service.sky.stars == {}


class TestEngineGuards:
    """Skyfield and WeeWX version guards."""

    def test_old_skyfield_declines(self, monkeypatch):
        """Skyfield earlier than 1.47 lacks find_risings/find_settings; the
        engine must decline up front, not fail on every rise/set
        computation."""
        monkeypatch.setattr(celestial.skyfield, 'VERSION', (1, 45))
        s = celestial.Sky(0, os.path.join(REPO_ROOT, 'bin', 'user'),
                          weeutil.Moon.moon_phases, ALTITUDE_M, LATITUDE, LONGITUDE,
                          load_stars=False)
        assert not s.is_valid()

    def test_weewx_version_parse(self):
        """The 5.2 minimum is compared on integer (major, minor): 5.10 must
        beat 5.2, dev builds get the benefit of the doubt (None)."""
        assert celestial.parse_weewx_version('5.2.0') == (5, 2)
        assert celestial.parse_weewx_version('5.10.1') == (5, 10)
        assert celestial.parse_weewx_version('4.10.2') == (4, 10)
        assert celestial.parse_weewx_version('10.0') == (10, 0)
        assert celestial.parse_weewx_version('5') == (5, 0)
        assert celestial.parse_weewx_version('dev') is None
        assert celestial.parse_weewx_version('5.2.0') >= (5, 2)
        assert celestial.parse_weewx_version('5.10.1') >= (5, 2)
        assert celestial.parse_weewx_version('4.10.2') < (5, 2)
        assert celestial.parse_weewx_version('5.1.0') < (5, 2)

    def test_old_weewx_refused_at_import(self):
        """As of 5.0 the module refuses to load on WeeWX older than 5.2
        (the install-time guard in install.py is the friendly front door;
        this catches copied-in files)."""
        import importlib
        saved = weewx.__version__
        try:
            weewx.__version__ = '4.10.2'
            with pytest.raises(weewx.UnsupportedFeature):
                importlib.reload(celestial)
        finally:
            weewx.__version__ = saved
            importlib.reload(celestial)


class TestStars:
    """The star catalog, which feeds the earthProximaCentauriDistance loop
    field.  (Named-star report tags are the weewx-skyfield extension's job.)"""

    @needs_catalog
    def test_loop_stars_loaded(self, sky):
        assert set(sky.stars) == set(celestial.LOOP_STARS)
        _, magnitude = sky.stars['proxima_centauri']
        assert magnitude == pytest.approx(11.01, abs=0.05)

    @needs_catalog
    def test_proxima_distance_in_packet(self, sky):
        """The nearest star, at 4.22 light years (Hipparcos parallax
        772.33 mas).  Light years in every unit system (group_data, no
        mile/km conversion), and constant at honest precision, so cached
        across packets."""
        assert celestial.LOOP_STARS['proxima_centauri'] == 70890
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        assert pkt['earthProximaCentauriDistance'] == pytest.approx(4.223, abs=0.01)
        metric_pkt = {'dateTime': TIME_TS, 'usUnits': weewx.METRIC}
        sky.insert_fields(metric_pkt)
        assert metric_pkt['earthProximaCentauriDistance'] == pkt['earthProximaCentauriDistance']

    def test_missing_catalog_degrades(self, tmp_path):
        """stars=true with an absent catalog file must disable star support,
        not invalidate the engine or break loop packets."""
        (tmp_path / 'celestial_de421.bsp').symlink_to(
            os.path.join(REPO_ROOT, 'bin', 'user', 'celestial_de421.bsp'))
        crippled = celestial.Sky(0, str(tmp_path), weeutil.Moon.moon_phases,
                                 ALTITUDE_M, LATITUDE, LONGITUDE, load_stars=True)
        assert crippled.is_valid()
        assert crippled.stars == {}
        assert not crippled.load_stars    # disabled by the failed load
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        crippled.insert_fields(pkt)
        assert 'earthProximaCentauriDistance' not in pkt
        assert 'sunrise' in pkt

    def test_corrupt_catalog_degrades(self, tmp_path):
        """An unreadable catalog -- not text at all (a corrupt or
        still-compressed download raises UnicodeDecodeError) -- must
        disable star support, never invalidate the engine."""
        (tmp_path / 'celestial_de421.bsp').symlink_to(
            os.path.join(REPO_ROOT, 'bin', 'user', 'celestial_de421.bsp'))
        (tmp_path / celestial.STAR_FILE).write_bytes(b'\x1f\x8b\x08\x00\xff\xfe garbage \xff')
        s = celestial.Sky(0, str(tmp_path), weeutil.Moon.moon_phases,
                          ALTITUDE_M, LATITUDE, LONGITUDE, load_stars=True)
        assert s.is_valid()
        assert s.stars == {}
        assert not s.load_stars

    @needs_catalog
    def test_stars_load_from_excerpt_not_full_catalog(self, tmp_path):
        """Stars load from the bundled excerpt even when a full hip_main.dat
        is installed: the excerpt's records are identical, and scanning
        118,218 catalog records at every startup buys nothing."""
        (tmp_path / celestial.STAR_FILE).symlink_to(
            os.path.join(REPO_ROOT, 'bin', 'user', celestial.STAR_FILE))
        # An empty stand-in full catalog: were it preferred, nothing would load.
        (tmp_path / 'hip_main.dat').write_text('')
        stars = celestial.Sky.load_named_stars(str(tmp_path))
        assert set(stars) == set(celestial.LOOP_STARS)

    @needs_catalog
    def test_full_catalog_stands_in_when_excerpt_missing(self, tmp_path):
        import shutil
        shutil.copy(os.path.join(REPO_ROOT, 'bin', 'user', celestial.STAR_FILE),
                    tmp_path / 'hip_main.dat')
        stars = celestial.Sky.load_named_stars(str(tmp_path))
        assert 'proxima_centauri' in stars

    @needs_catalog
    def test_malformed_record_skips_only_that_star(self, tmp_path):
        """One bad catalog record must disable only that star, not the
        whole catalog."""
        sirius_hip = 32349
        proxima_hip = celestial.LOOP_STARS['proxima_centauri']
        good = None
        with open(os.path.join(REPO_ROOT, 'bin', 'user', celestial.STAR_FILE)) as f:
            for line in f:
                if line.startswith('H|') and line.split('|')[1].strip() == str(sirius_hip):
                    good = line
                    break
        assert good is not None
        # A truncated record for proxima: no astrometric or identification
        # columns to fall back on.
        truncated = 'H|%12d|\n' % proxima_hip
        (tmp_path / celestial.STAR_FILE).write_text(good + truncated)
        by_hip = celestial.Sky.load_stars_by_hip(str(tmp_path), {sirius_hip, proxima_hip})
        assert sirius_hip in by_hip
        assert proxima_hip not in by_hip


class TestSampleSkinRenders:
    """Render the bundled sample skin end to end, through Cheetah's
    errorCatcher, exactly as weewx does.  Template.compile alone is NOT
    enough: with #errorCatcher Echo, Cheetah re-compiles each placeholder's
    source at render time, and that path rejects constructs plain
    compilation accepts (e.g. a conditional expression inside $(...) loses
    its else-value and dies with SyntaxError only at render time)."""

    @staticmethod
    def render(almanac_obj, with_time_zone=True, sky_page=None):
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
        extras = Extras(loop_data_file='/gauge-data/loop-data.txt',
                        expiration_time=86400, refresh_rate=2)
        if with_time_zone:
            extras['time_zone'] = 'America/Los_Angeles'
        template = Template(source, searchList=[{
            'almanac': almanac_obj,
            'sky_page': sky_page,
            'current': Obj(dateTime=Obj(raw=TIME_TS)),
            'unit': Obj(label=Obj(earthMoonDistance=' miles'),
                        unit_type=Obj(earthMoonDistance='mile')),
            'station': Obj(location='Test Station',
                           stn_info=Obj(latitude_f=LATITUDE, longitude_f=LONGITUDE)),
            'Extras': extras,
        }])
        return str(template)

    def cell(self, html, cell_id):
        import re
        match = re.search(r'id="%s"[^>]*>([^<]*)<' % re.escape(cell_id), html)
        assert match is not None, cell_id
        return match.group(1)

    def test_renders_with_skyfield_almanac(self, wxskyfield_almanac):
        html = self.render(wxskyfield_almanac)
        assert ':' in self.cell(html, 'current.sunrise.raw')            # a time
        assert '&deg;' in self.cell(html, 'current.moonAzimuth.raw')    # an angle
        assert 'miles' in self.cell(html, 'current.earthPlutoDistance')
        assert 'light years' in self.cell(html, 'current.earthProximaCentauriDistance.raw')
        assert 'than yesterday' in html                                 # daylight computed
        # The inlined realtime_updater.inc rendered too.
        assert 'function setHtml(' in html
        assert '/gauge-data/loop-data.txt' in html
        # The live-page structure rendered.
        assert 'celestial.css' in html
        assert 'id="moon-disc"' in html
        assert 'id="day-strip"' in html
        assert 'id="planet-mercury"' in html and 'id="planet-pluto"' in html
        assert 'id="count-equinox"' in html
        # The javascript consumes the new loop fields (planet keys are built
        # dynamically) and the station latitude.
        assert "'Azimuth.raw'" in html and "'Altitude.raw'" in html
        assert 'current.moonPhaseIndex.raw' in html
        assert '37.44' in html
        # No sky_page was passed, so all seven sky-chart panels show hints.
        assert html.count('class="skyhint"') == 7

    def test_renders_sky_panels_with_wxskyfield(self, wxskyfield_almanac):
        """With weewx-skyfield present, $sky_page draws all seven SVG
        panels (this is what CelestialSkyPage delegates to in production)."""
        sky_mod = load_wxskyfield_sky()
        html = self.render(wxskyfield_almanac, sky_page=sky_mod.SkyPage())
        assert 'aria-label="Rise and set timeline"' in html
        assert 'aria-label="Sky dome chart"' in html
        assert 'aria-label="Solar system plan view"' in html
        assert 'aria-label="Analemma"' in html
        assert 'aria-label="Sun path today"' in html
        assert 'aria-label="Day length through the year"' in html
        assert 'aria-label="The lunar month"' in html
        assert 'skyhint' not in html

    def test_old_wxskyfield_shows_upgrade_hints(self, wxskyfield_almanac):
        """A pre-1.7 weewx-skyfield lacks the sun path, solar year and
        lunar month panels: those three cells must degrade to upgrade
        hints while the original four panels keep drawing."""
        sky_mod = load_wxskyfield_sky()
        real = sky_mod.SkyPage()

        class Old16SkyPage:
            """Only the four panel methods weewx-skyfield 1.6 had."""
            dome_svg = staticmethod(real.dome_svg)
            ribbons_svg = staticmethod(real.ribbons_svg)
            orrery_svg = staticmethod(real.orrery_svg)
            analemma_svg = staticmethod(real.analemma_svg)

        html = self.render(wxskyfield_almanac, sky_page=Old16SkyPage())
        assert 'aria-label="Rise and set timeline"' in html
        assert 'aria-label="Sky dome chart"' in html
        assert 'aria-label="Solar system plan view"' in html
        assert 'aria-label="Analemma"' in html
        assert 'aria-label="Sun path today"' not in html
        assert 'aria-label="Day length through the year"' not in html
        assert 'aria-label="The lunar month"' not in html
        assert html.count('class="skyhint"') == 3
        assert html.count('Upgrade <a') == 3
        assert 'Install <a' not in html

    def test_no_hex_colors_in_cheetah_files(self):
        """Cheetah owns '#': hex color literals in the template or the
        javascript include would be eaten as directives/comments.  All
        colors must come from classes in celestial.css."""
        import re
        skin_dir = os.path.join(REPO_ROOT, 'skins', 'Celestial')
        for name in ('index.html.tmpl', 'realtime_updater.inc'):
            source = open(os.path.join(skin_dir, name)).read()
            assert not re.search(r'#[0-9A-Fa-f]{6}\b', source), name

    def test_template_constants_match_celestial(self):
        """The template hardcodes unit constants (it cannot import
        celestial.py); they must equal the module's."""
        import re
        source = open(os.path.join(REPO_ROOT, 'skins', 'Celestial', 'index.html.tmpl')).read()
        per_au = {float(m) for m in re.findall(r'\$per_au = ([0-9.e+]+)', source)}
        assert per_au == {celestial.AU_MILES, celestial.AU_KM}
        light_year = re.search(r'earth_distance / ([0-9.]+)', source)
        assert float(light_year.group(1)) == celestial.AU_PER_LIGHT_YEAR

    def test_renders_without_extended_almanac(self):
        """With only the weeutil almanac (no PyEphem, no Skyfield), the page
        must still generate, with empty javascript-filled cells as in 2.x."""
        with saved_almanacs():
            weewx.almanac.almanacs[:] = [weewx.almanac.WeeutilAlmanacType()]
            plain = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                          formatter=weewx.units.get_default_formatter())
            assert not plain.hasExtras
            # Render without a time_zone Extras key: the template must
            # auto-detect the station machine's zone (same logic as the
            # include: /etc/localtime symlink, /etc/timezone fallback).
            html = self.render(plain, with_time_zone=False)
        assert self.cell(html, 'current.sunrise.raw') == ''
        assert self.cell(html, 'current.earthProximaCentauriDistance.raw') == ''
        assert 'Proxima Centauri' in html
        # Without weewx-skyfield the sky-chart panels invite installing it.
        assert html.count('class="skyhint"') == 7
        assert 'https://github.com/chaunceygardiner/weewx-skyfield' in html
        assert 'aria-label="Sky dome chart"' not in html
        auto_tz = ''
        try:
            auto_tz = os.readlink('/etc/localtime').split('zoneinfo/')[-1]
        except OSError:
            try:
                auto_tz = open('/etc/timezone').read().strip()
            except OSError:
                pass
        assert "time_zone = '%s'" % auto_tz in html


class TestCelestialSkyPage:
    """The search-list shim behind the skin's $sky_page: the real
    weewx-skyfield sky page when that extension is importable, None
    (install hints) when it is not -- never a failed report."""

    @staticmethod
    def _block_wxskyfield_sky(monkeypatch):
        # A None entry in sys.modules makes the import raise ImportError,
        # even if an earlier test appended the oracle checkout to sys.path.
        monkeypatch.setitem(sys.modules, 'user.wxskyfield_sky', None)
        monkeypatch.setitem(sys.modules, 'wxskyfield_sky', None)

    def test_absent_serves_none(self, monkeypatch):
        self._block_wxskyfield_sky(monkeypatch)
        page = celestial.CelestialSkyPage(StubEngine())
        assert page.get_extension_list(None, None) == [{'sky_page': None}]

    def test_present_delegates(self, monkeypatch):
        import types

        class FakeSkyfieldSky:
            def __init__(self, generator):
                self.generator = generator

            def get_extension_list(self, timespan, db_lookup):
                return [{'sky_page': 'the-sky-page'}]

        fake = types.ModuleType('wxskyfield_sky')
        fake.SkyfieldSky = FakeSkyfieldSky
        monkeypatch.setitem(sys.modules, 'user.wxskyfield_sky', None)
        monkeypatch.setitem(sys.modules, 'wxskyfield_sky', fake)
        page = celestial.CelestialSkyPage(StubEngine())
        assert page.get_extension_list(None, None) == [{'sky_page': 'the-sky-page'}]

    def test_broken_delegate_degrades_to_none(self, monkeypatch):
        import types

        class ExplodingSkyfieldSky:
            def __init__(self, generator):
                raise RuntimeError('boom')

        fake = types.ModuleType('wxskyfield_sky')
        fake.SkyfieldSky = ExplodingSkyfieldSky
        monkeypatch.setitem(sys.modules, 'user.wxskyfield_sky', None)
        monkeypatch.setitem(sys.modules, 'wxskyfield_sky', fake)
        page = celestial.CelestialSkyPage(StubEngine())
        assert page.get_extension_list(None, None) == [{'sky_page': None}]


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


class TestDeprecatedFieldsRemoved:
    """The pre-3.0 PascalCase aliases were dual-emitted through 3.x and are
    gone in 4.0, as announced in the 3.0 release notes."""

    OLD_NAMES = ['Sunrise', 'Sunset', 'SunTransit', 'Moonrise', 'Moonset',
                 'MoonAzimuth', 'MoonPhase', 'NextEquinox', 'NextFullMoon',
                 'EarthSunDistance', 'EarthMoonDistance', 'EarthPlutoDistance',
                 'CivilTwilightStart', 'AstronomicalTwilightEnd',
                 'daySunshineDur', 'yesterdaySunshineDur']

    def test_all_new_names_present(self, sky):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        for name in celestial.OBS_GROUPS:
            if name == 'earthProximaCentauriDistance' and not sky.stars:
                continue    # needs the star catalog
            assert name in pkt, 'missing new-name field %s' % name

    def test_old_names_absent_from_packet(self, sky):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        for old_name in self.OLD_NAMES:
            assert old_name not in pkt, 'deprecated field %s still emitted' % old_name

    def test_old_names_not_registered_as_obs_types(self):
        # obs_group_dict is process-global, but nothing else in this test
        # process registers the PascalCase names, so their absence shows
        # celestial no longer does.  (daySunshineDur is excluded: WeeWX
        # core registers that name itself, for actual sunshine duration.)
        for old_name in self.OLD_NAMES:
            if old_name in ('daySunshineDur', 'yesterdaySunshineDur'):
                continue
            assert old_name not in weewx.units.obs_group_dict

    def test_cached_packets_use_new_names_only(self):
        # With update_rate_secs > 0, cached (prev_reading) packets must
        # carry the new names, and only those.
        sky = celestial.Sky(300, os.path.join(REPO_ROOT, 'bin', 'user'),
                            weeutil.Moon.moon_phases, ALTITUDE_M, LATITUDE, LONGITUDE)
        pkt1 = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt1)
        # A second packet within update_rate_secs is served from the cache.
        pkt2 = {'dateTime': TIME_TS + 2, 'usUnits': weewx.US}
        sky.insert_fields(pkt2)
        assert pkt2['sunrise'] == pkt1['sunrise']
        assert pkt2['daylightDur'] == pkt1['daylightDur']
        assert 'Sunrise' not in pkt2
        assert 'daySunshineDur' not in pkt2


class TestMigrateLoopdataFields:
    """The --migrate-loopdata-fields utility: renames deprecated pre-3.0
    celestial fields in place, drops the duplicates the renames create,
    appends the 4.0 sample-report fields, and touches nothing else."""

    def test_2x_list_with_only_old_names(self):
        fields = ['current.outTemp', 'current.Sunrise.raw', 'current.EarthMoonDistance',
                  'current.daySunshineDur.raw', 'day.rain.sum']
        new, report = celestial.migrate_loopdata_fields(fields)
        # Renames happen in place, order preserved, suffixes kept.
        assert new[:5] == ['current.outTemp', 'current.sunrise.raw',
                           'current.earthMoonDistance', 'current.daylightDur.raw',
                           'day.rain.sum']
        assert ('current.Sunrise.raw', 'current.sunrise.raw') in report['renamed']
        assert ('current.daySunshineDur.raw', 'current.daylightDur.raw') in report['renamed']
        assert report['dropped'] == []
        # The 4.0 sample-report fields are appended.
        assert 'current.moonWaxing.raw' in new
        assert 'current.marsAzimuth.raw' in new
        assert 'current.moonWaxing.raw' in report['added']

    def test_3x_list_with_both_names_dedups(self):
        fields = ['current.Sunrise.raw', 'current.sunrise.raw', 'current.moonPhase']
        new, report = celestial.migrate_loopdata_fields(fields)
        assert new.count('current.sunrise.raw') == 1
        assert report['dropped'] == ['current.sunrise.raw']

    def test_non_celestial_entries_untouched(self):
        # current.Data.raw / current.UV are not celestial names despite the
        # capital letter; unit.label entries have no obstype to rename.
        fields = ['current.Data.raw', 'current.UV', 'unit.label.outTemp',
                  'trend.barometer.desc']
        new, report = celestial.migrate_loopdata_fields(fields)
        assert new[:4] == fields
        assert report['renamed'] == []

    def test_idempotent(self):
        fields = ['current.Sunrise.raw', 'current.outTemp']
        once, _ = celestial.migrate_loopdata_fields(fields)
        twice, report = celestial.migrate_loopdata_fields(once)
        assert twice == once
        assert report['renamed'] == [] and report['dropped'] == [] and report['added'] == []

    def test_new_fields_all_present_in_obs_groups(self):
        # Every appended current.<obstype>[.raw] must name a real loop field
        # (or dateTime, which WeeWX itself provides).
        for field in celestial._MIGRATION_NEW_FIELDS:
            obstype = field.split('.')[1]
            assert obstype == 'dateTime' or obstype in celestial.OBS_GROUPS, field

    def test_conf_rewrite(self, tmp_path):
        conf = tmp_path / 'weewx.conf'
        conf.write_text(
            '# a comment\n'
            '[Station]\n'
            '    location = Test Station\n'
            '[LoopData]\n'
            '    [[Include]]\n'
            '        fields = current.Sunrise.raw, current.outTemp, current.sunset.raw\n'
        )
        out = tmp_path / 'weewx.conf.migrated'
        report = celestial.migrate_loopdata_conf(str(conf), str(out))
        assert ('current.Sunrise.raw', 'current.sunrise.raw') in report['renamed']
        import configobj
        migrated = configobj.ConfigObj(str(out))
        fields = migrated['LoopData']['Include']['fields']
        assert 'current.sunrise.raw' in fields
        assert 'current.Sunrise.raw' not in fields
        assert 'current.outTemp' in fields          # non-celestial preserved
        assert 'current.moonWaxing.raw' in fields   # 4.0 fields appended
        # The rest of the configuration survives the round trip.
        assert migrated['Station']['location'] == 'Test Station'
        # The original file is untouched.
        assert 'current.Sunrise.raw' in conf.read_text()


class TestPolarDaylight:
    """Edge cases of daylightDur around the polar day/night transitions.
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


class TestFieldCaching:
    """insert_fields computes each field class no more often than it can
    change: continuous fields every packet (or update_rate_secs), day-scoped
    fields once per local day, next-event fields when an event passes.
    These tests pin the correctness of the cached paths."""

    @staticmethod
    def fresh_sky(update_rate_secs=0):
        return celestial.Sky(update_rate_secs, os.path.join(REPO_ROOT, 'bin', 'user'),
                             weeutil.Moon.moon_phases, ALTITUDE_M, LATITUDE, LONGITUDE)

    @staticmethod
    def insert(sky, ts):
        pkt = {'dateTime': ts, 'usUnits': weewx.US, 'outTemp': 65.0, 'barometer': 30.0}
        sky.insert_fields(pkt)
        return pkt

    def test_same_day_reuses_day_fields_recomputes_positions(self):
        sky = self.fresh_sky()
        pkt1 = self.insert(sky, TIME_TS)
        pkt2 = self.insert(sky, TIME_TS + 3600)
        assert pkt2['sunrise'] == pkt1['sunrise']
        assert pkt2['nextNewMoon'] == pkt1['nextNewMoon']
        assert pkt2['sunAzimuth'] != pkt1['sunAzimuth']    # continuous: recomputed
        assert pkt2['marsAzimuth'] != pkt1['marsAzimuth']  # planets are continuous too

    def test_cached_day_fields_match_fresh_compute(self):
        cached = self.fresh_sky()
        fresh = self.fresh_sky()
        self.insert(cached, TIME_TS)
        pkt_cached = self.insert(cached, TIME_TS + 7200)   # day/event fields from cache
        pkt_fresh = self.insert(fresh, TIME_TS + 7200)     # everything computed cold
        for name in ('sunrise', 'sunset', 'sunTransit', 'moonrise', 'daylightDur',
                     'civilTwilightStart', 'astronomicalTwilightEnd',
                     'tomorrowSunrise', 'nextFullMoon', 'nextEquinox'):
            assert pkt_cached[name] == pkt_fresh[name], name

    def test_day_rollover_refreshes_day_fields(self):
        sky = self.fresh_sky()
        pkt1 = self.insert(sky, TIME_TS)
        pkt2 = self.insert(sky, TIME_TS + 86400)
        assert pkt2['sunrise'] == pytest.approx(pkt1['sunrise'] + 86400, abs=120)
        # No event passed, so the event cache is still served.
        assert pkt2['nextEquinox'] == pkt1['nextEquinox']
        assert pkt2['nextNewMoon'] == pkt1['nextNewMoon']

    def test_event_kept_for_rest_of_its_day(self):
        sky = self.fresh_sky()
        pkt1 = self.insert(sky, TIME_TS)
        new_moon = pkt1['nextNewMoon']
        # An hour after the new moon (same local day): still reported, per
        # the keep-it-around-for-the-day convention.
        pkt2 = self.insert(sky, new_moon + 3600)
        assert pkt2['nextNewMoon'] == new_moon

    def test_event_advances_the_next_day(self):
        sky = self.fresh_sky()
        pkt1 = self.insert(sky, TIME_TS)
        pkt2 = self.insert(sky, pkt1['nextNewMoon'] + 86400)
        assert pkt2['nextNewMoon'] > pkt1['nextNewMoon']
        assert pkt2['nextNewMoon'] > pkt2['dateTime']
        # The full moon had not passed; the rescan finds the same one.
        assert pkt2['nextFullMoon'] == pytest.approx(pkt1['nextFullMoon'], abs=TIME_TOL)

    def test_backfilled_packet_gets_its_own_day(self):
        sky = self.fresh_sky()
        pkt1 = self.insert(sky, TIME_TS)
        self.insert(sky, TIME_TS + 86400 * 10)
        pkt3 = self.insert(sky, TIME_TS)    # out-of-order: answered for its own day
        assert pkt3['sunrise'] == pkt1['sunrise']
        assert pkt3['nextNewMoon'] == pkt1['nextNewMoon']

    def test_update_rate_secs_throttles_only_continuous(self):
        sky = self.fresh_sky(update_rate_secs=300)
        pkt1 = self.insert(sky, TIME_TS)
        pkt2 = self.insert(sky, TIME_TS + 2)
        assert pkt2['sunAzimuth'] == pkt1['sunAzimuth']    # inside the window: cached
        assert pkt2['marsAzimuth'] == pkt1['marsAzimuth']
        assert pkt2['sunrise'] == pkt1['sunrise']          # day cache, always present
        pkt3 = self.insert(sky, TIME_TS + 400)
        assert pkt3['sunAzimuth'] != pkt1['sunAzimuth']    # window expired: recomputed

    def test_throttle_rejects_backfilled_packets(self):
        # A packet whose time moved backward (out-of-order, NTP step) must
        # be recomputed for its own time, not served positions from a newer
        # packet via the negative-delta window.
        sky = self.fresh_sky(update_rate_secs=300)
        pkt1 = self.insert(sky, TIME_TS)
        pkt2 = self.insert(sky, TIME_TS - 7200)
        assert pkt2['sunAzimuth'] != pkt1['sunAzimuth']

    def test_throttle_rejects_unit_system_change(self):
        # A cached distance is stored converted; a packet with a different
        # unit system inside the window must recompute, not serve miles as km.
        sky = self.fresh_sky(update_rate_secs=300)
        self.insert(sky, TIME_TS)                          # US: miles cached
        pkt = {'dateTime': TIME_TS + 2, 'usUnits': weewx.METRIC,
               'outTemp': 18.0, 'barometer': 1020.0}
        sky.insert_fields(pkt)
        assert 356000.0 < pkt['earthMoonDistance'] < 407000.0    # km, not miles

    def test_throttled_packets_keep_last_good_value(self):
        # A field whose computation fails on a recompute round must keep
        # its last good value for the throttled packets that follow (the
        # 3.x behavior), not vanish from the cache.
        sky = self.fresh_sky(update_rate_secs=300)
        pkt1 = self.insert(sky, TIME_TS)
        original = sky.get_moon_phase
        sky.get_moon_phase = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom'))
        try:
            pkt2 = self.insert(sky, TIME_TS + 400)         # recompute round, phase fails
            assert 'moonPhase' not in pkt2
        finally:
            sky.get_moon_phase = original
        pkt3 = self.insert(sky, TIME_TS + 402)             # throttled: last good served
        assert pkt3['moonPhase'] == pkt1['moonPhase']
        assert pkt3['moonFullness'] == pkt1['moonFullness']

    def test_day_cache_failure_retries_next_packet(self):
        # A transient failure must not poison the day cache for the rest of
        # the local day.
        sky = self.fresh_sky()
        original = sky.get_rise_set_transit
        sky.get_rise_set_transit = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom'))
        try:
            pkt1 = self.insert(sky, TIME_TS)
            assert 'moonrise' not in pkt1
            assert 'sunrise' in pkt1                       # other sections still served
        finally:
            sky.get_rise_set_transit = original
        pkt2 = self.insert(sky, TIME_TS + 2)               # same day: retried, healed
        assert 'moonrise' in pkt2

    def test_event_cache_failure_retries_next_packet(self):
        sky = self.fresh_sky()
        original = sky.get_next_fullmoon_and_newmoon
        sky.get_next_fullmoon_and_newmoon = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom'))
        try:
            pkt1 = self.insert(sky, TIME_TS)
            assert 'nextFullMoon' not in pkt1
        finally:
            sky.get_next_fullmoon_and_newmoon = original
        pkt2 = self.insert(sky, TIME_TS + 2)               # same day: retried, healed
        assert 'nextFullMoon' in pkt2
        assert 'nextNewMoon' in pkt2


class TestLoopPacketPinned:
    """Pinned regression values for the loop fields, captured from the 3.1
    release (whose embedded report almanac was the previous oracle).  These
    always run, whether or not weewx-skyfield is available."""

    @pytest.fixture(scope='class')
    @staticmethod
    def pkt(sky):
        p = {'dateTime': TIME_TS, 'usUnits': weewx.US, 'outTemp': 65.0, 'barometer': 30.0}
        sky.insert_fields(p)
        return p

    EXPECTED_TIMES = {
        'sunrise'     : 1750510083.5,
        'sunset'      : 1750563176.2,
        'sunTransit'  : 1750536630.2,
        'moonrise'    : 1750497776.9,
        'nextFullMoon': 1752179807.6,
        'nextNewMoon' : 1750847497.1,
        'nextEquinox' : 1758565160.5,
        'nextSolstice': 1766329385.1,
    }

    def test_event_times(self, pkt):
        for name, expected in self.EXPECTED_TIMES.items():
            assert pkt[name] == pytest.approx(expected, abs=TIME_TOL), name

    def test_daylight(self, pkt):
        assert pkt['daylightDur'] == pytest.approx(53092.8, abs=TIME_TOL)

    def test_sun_position(self, pkt):
        assert pkt['sunAzimuth'] == pytest.approx(127.847, abs=ANGLE_TOL)
        assert pkt['sunAltitude'] == pytest.approx(69.409, abs=ANGLE_TOL)

    def test_moon_phase(self, pkt):
        assert pkt['moonPhase'] == 'waning crescent (decreasing from full)'

    def test_distances_us_miles(self, pkt):
        assert pkt['earthSunDistance'] == pytest.approx(94466502.7, rel=1e-6)
        assert pkt['earthMoonDistance'] == pytest.approx(226459.8, rel=1e-6)

    @needs_catalog
    def test_proxima_distance(self, pkt):
        assert pkt['earthProximaCentauriDistance'] == pytest.approx(4.22301, abs=1e-4)

    def test_planet_positions(self, pkt):
        assert pkt['marsAzimuth'] == pytest.approx(85.551, abs=ANGLE_TOL)
        assert pkt['marsAltitude'] == pytest.approx(13.577, abs=ANGLE_TOL)
        assert pkt['jupiterAzimuth'] == pytest.approx(124.127, abs=ANGLE_TOL)

    def test_moon_phase_index(self, pkt):
        # Must agree with the pinned moonPhase string (waning crescent).
        assert pkt['moonPhaseIndex'] == 7
        assert pkt['moonWaxing'] == 0


class TestLoopPacketConsistency:
    """The loop packet fields must agree with the weewx-skyfield extension's
    report almanac (both derive from the same definitions)."""

    def test_zero_celsius_is_a_measurement(self, sky):
        """outTemp of exactly 0.0 degC must be used for refraction, not
        treated as missing: the sun's refracted altitude at sunrise must
        vary monotonically as the temperature passes through zero."""
        from datetime import datetime, timezone
        sunrise_dt = datetime.fromtimestamp(1750510082, timezone.utc)
        alts = [sky.get_az_alt_ra_dec(sky.ts, sky.sun, sunrise_dt, tempC, 1013.0)[1]
                for tempC in (-0.5, 0.0, 0.5)]
        assert alts[0] > alts[1] > alts[2]    # colder air refracts more

    def test_sunrise_matches_loop_packet(self, sky, wxskyfield_almanac):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US, 'outTemp': 65.0, 'barometer': 30.0}
        sky.insert_fields(pkt)
        assert pkt['sunrise'] == pytest.approx(wxskyfield_almanac.sunrise.raw, abs=1.0)
        assert pkt['sunset'] == pytest.approx(wxskyfield_almanac.sunset.raw, abs=1.0)
        assert pkt['moonrise'] == pytest.approx(wxskyfield_almanac.moon.rise.raw, abs=1.0)
        assert pkt['sunTransit'] == pytest.approx(wxskyfield_almanac.sun.transit.raw, abs=1.0)
        assert pkt['nextFullMoon'] == pytest.approx(wxskyfield_almanac.next_full_moon.raw, abs=1.0)
        assert pkt['nextEquinox'] == pytest.approx(wxskyfield_almanac.next_equinox.raw, abs=1.0)
        assert pkt['moonPhase'] == wxskyfield_almanac.moon_phase

    def test_twilight_and_daylight_match_loop_packet(self, sky, wxskyfield_almanac):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        assert pkt['civilTwilightStart'] == pytest.approx(
            wxskyfield_almanac(horizon=-6).sun(use_center=1).rise.raw, abs=1.0)
        assert pkt['nauticalTwilightEnd'] == pytest.approx(
            wxskyfield_almanac(horizon=-12).sun(use_center=1).set.raw, abs=1.0)
        assert pkt['astronomicalTwilightStart'] == pytest.approx(
            wxskyfield_almanac(horizon=-18).sun(use_center=1).rise.raw, abs=1.0)
        assert pkt['daylightDur'] == pytest.approx(wxskyfield_almanac.sun.visible.raw, abs=1.0)
        assert pkt['yesterdayDaylightDur'] == pytest.approx(
            wxskyfield_almanac(almanac_time=TIME_TS - 86400).sun.visible.raw, abs=1.0)
        assert pkt['tomorrowSunrise'] == pytest.approx(
            wxskyfield_almanac(almanac_time=TIME_TS + 86400).sunrise.raw, abs=1.0)

    def test_ra_dec_match_loop_packet(self, sky, wxskyfield_almanac):
        # The loop packet's RA/Dec are in coordinates of date, matching the
        # almanac's topo_ra/topo_dec.
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        assert pkt['sunRightAscension'] == pytest.approx(wxskyfield_almanac.sun.topo_ra.raw, abs=1e-3)
        assert pkt['sunDeclination'] == pytest.approx(wxskyfield_almanac.sun.topo_dec.raw, abs=1e-3)
        assert pkt['moonRightAscension'] == pytest.approx(wxskyfield_almanac.moon.topo_ra.raw, abs=1e-3)
        assert pkt['moonDeclination'] == pytest.approx(wxskyfield_almanac.moon.topo_dec.raw, abs=1e-3)

    def test_distances_match_loop_packet(self, sky, wxskyfield_almanac):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.METRIC}
        sky.insert_fields(pkt)
        km_per_au = celestial.AU_KM
        assert pkt['earthSunDistance'] == pytest.approx(wxskyfield_almanac.sun.earth_distance * km_per_au, rel=1e-9)
        assert pkt['earthMoonDistance'] == pytest.approx(wxskyfield_almanac.moon.earth_distance * km_per_au, rel=1e-9)
        assert pkt['earthPlutoDistance'] == pytest.approx(wxskyfield_almanac.pluto.earth_distance * km_per_au, rel=1e-9)

    def test_planet_az_alt_match_loop_packet(self, sky, wxskyfield_almanac):
        # The binder's az/alt use the almanac's default temperature/pressure
        # (15.0 degC / 1010.0 mbar), so feed the loop path exactly those.
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.METRIC, 'outTemp': 15.0, 'barometer': 1010.0}
        sky.insert_fields(pkt)
        for planet in ('mercury', 'mars', 'saturn', 'neptune', 'pluto'):
            binder = getattr(wxskyfield_almanac, planet)
            assert pkt[planet + 'Azimuth'] == pytest.approx(binder.az, abs=1e-3), planet
            assert pkt[planet + 'Altitude'] == pytest.approx(binder.alt, abs=1e-3), planet
        assert pkt['moonPhaseIndex'] == wxskyfield_almanac.moon_index

    @needs_catalog
    def test_proxima_matches_report_tag(self, sky, wxskyfield_almanac):
        pkt = {'dateTime': TIME_TS, 'usUnits': weewx.US}
        sky.insert_fields(pkt)
        ly = wxskyfield_almanac.proxima_centauri.earth_distance / celestial.AU_PER_LIGHT_YEAR
        assert pkt['earthProximaCentauriDistance'] == pytest.approx(ly, abs=1e-6)


class TestInMemoryEphemeris:
    """The engine reads the .bsp fully into RAM (InMemorySpiceKernel).
    'weectl extension install' over a live weewxd rewrites the ephemeris in
    place; a memory-mapped kernel dies with SIGBUS when that happens, so
    replacing or truncating the file under a loaded kernel must not disturb
    its computations."""

    def test_kernel_matches_mmap_and_survives_truncation(self, sky, tmp_path):
        src = os.path.join(REPO_ROOT, 'bin', 'user', 'celestial_de421.bsp')
        copy = str(tmp_path / 'celestial_de421.bsp')
        shutil.copyfile(src, copy)
        t = sky.ts.utc(2025, 6, 21, 19)

        # Same answers as skyfield's own (mmap) loader on the pristine file.
        reference = skyfield.api.load_file(src)
        ref_ra, ref_dec, _ = reference['earth'].at(t).observe(reference['mars']).radec()
        kernel = celestial.InMemorySpiceKernel(copy)
        ra, dec, _ = kernel['earth'].at(t).observe(kernel['mars']).radec()
        assert ra.radians == ref_ra.radians
        assert dec.radians == ref_dec.radians

        # Truncate the backing file to zero bytes underneath the kernel --
        # the in-place rewrite window that used to SIGBUS weewxd.
        open(copy, 'wb').close()
        ra2, dec2, _ = kernel['earth'].at(t).observe(kernel['mars']).radec()
        assert ra2.radians == ra.radians
        assert dec2.radians == dec.radians

    def test_engine_uses_in_memory_kernel(self, sky):
        assert isinstance(sky.planets, celestial.InMemorySpiceKernel)
