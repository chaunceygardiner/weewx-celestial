"""
test_celestial.py

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Tests for weewx-celestial 6.0: the bundled Celestial skin (rendered end to
end through Cheetah's errorCatcher), the CelestialSkyPage search-list shim,
and the --migrate-loopdata-fields utility that rewrites a pre-6.0
[LoopData] [[Include]] fields line to weewx-loopdata almanac entries.

Run with the WeeWX virtual environment's Python, from the root of this repo:
    /home/weewx/weewx-venv/bin/python -m pytest tests

The skin-render tests use the independent weewx-skyfield extension (the
installed copy or a sibling checkout) as the report almanac, exactly as
production does; they skip when it is not available.  The migration tests
cross-check every produced entry against the sibling weewx-loopdata
checkout's almanac-field parser when that repo is available.
"""

import contextlib
import os
import sys
import time

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TEST_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, 'bin', 'user'))

# The rendered values (and WeeWX's notion of "today's" rise/set) depend on
# the local timezone, so pin it.
os.environ['TZ'] = 'America/Los_Angeles'
time.tzset()

import weewx
import weewx.almanac
import weewx.units

import celestial

LATITUDE    = 37.4419
LONGITUDE   = -122.143
ALTITUDE_M  = 9.0
TIME_TS     = 1750532400      # 2025-06-21 12:00:00 PDT

# Where the independent weewx-skyfield extension may be found: the installed
# copy on this machine, or a sibling checkout of its repo.
WXSKYFIELD_DIRS = [
    '/home/weewx/weewx-data/bin/user',
    os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield', 'bin', 'user'),
]

# Where the sibling weewx-loopdata checkout may be found (its parser is the
# oracle for the migration tests' almanac grammar).
LOOPDATA_DIRS = [
    os.path.join(os.path.dirname(REPO_ROOT), 'weewx-loopdata', 'bin', 'user'),
    '/home/weewx/weewx-data/bin/user',
]


def load_wxskyfield():
    """Import the weewx-skyfield extension (the report almanac the skin
    renders from) and return (module, its user_root), or skip the calling
    test."""
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


def load_loopdata():
    """Import the sibling weewx-loopdata checkout's module, or skip the
    calling test."""
    for d in LOOPDATA_DIRS:
        if os.path.exists(os.path.join(d, 'loopdata.py')):
            if d not in sys.path:
                sys.path.append(d)     # append, NOT insert(0); see above
            import loopdata
            return loopdata
    pytest.skip('the weewx-loopdata checkout is not available')


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
    """Just enough of a WeeWX report generator for the search-list shim."""
    def __init__(self):
        self.bound = []

    def bind(self, event, callback):
        self.bound.append(event)


class TestServiceStub:
    """6.0 has no loop-field service, but a weewx.conf that still lists
    user.celestial.Celestial (an install over the top of 5.x, without the
    uninstall) must start cleanly: the stub logs the cleanup instruction,
    binds nothing, and exits."""

    def test_stub_starts_and_binds_nothing(self, caplog):
        import logging
        engine = StubEngine()
        with caplog.at_level(logging.WARNING):
            celestial.Celestial(engine, {})
        assert engine.bound == []
        assert 'Remove user.celestial.Celestial from data_services' in caplog.text


class TestEngineGuards:
    """WeeWX version guards."""

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
            # windrun stands in for group_distance (this extension no longer
            # registers distance observation types).
            'unit': Obj(label=Obj(windrun=' miles'),
                        unit_type=Obj(windrun='mile')),
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
        assert ':' in self.cell(html, 'almanac.sunrise.raw')          # a time
        assert '&deg;' in self.cell(html, 'almanac.moon.az')          # an angle
        assert 'miles' in self.cell(html, 'almanac.pluto.earth_distance')
        assert 'light years' in self.cell(html, 'almanac.proxima_centauri.earth_distance')
        assert 'than yesterday' in html                               # daylight computed
        # The inlined realtime_updater.inc rendered too.
        assert 'function setHtml(' in html
        assert '/gauge-data/loop-data.txt' in html
        # The live-page structure rendered.
        assert 'celestial.css' in html
        assert 'id="moon-disc"' in html
        assert 'id="day-strip"' in html
        assert 'id="planet-mercury"' in html and 'id="planet-pluto"' in html
        assert 'id="count-equinox"' in html
        # The javascript consumes the loopdata almanac fields (planet keys
        # are built dynamically), the AU conversion constants and the
        # station latitude.
        assert "'almanac.' + planet + '.az'" in html
        assert "'almanac.' + planet + '.alt'" in html
        assert "'almanac.' + planet + '.earth_distance'" in html
        assert 'almanac.moon_index' in html
        assert 'PER_AU = 92955807' in html and "DIST_LABEL = ' miles'" in html
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

    def test_renders_skyfield_19_tags(self, wxskyfield_almanac):
        """weewx-skyfield 1.9 added constellations and station-visible
        eclipses; the skin uses them wherever it renders its own
        presentation, at report time only (no loop fields).  Values are
        pinned for Palo Alto at TIME_TS -- see weewx-skyfield's
        TestConstellations/TestEclipses for the cross-checked sources."""
        try:
            wxskyfield_almanac.saturn.constellation
        except Exception:
            pytest.skip('the weewx-skyfield oracle predates 1.9')
        html = self.render(wxskyfield_almanac)
        # The countdown row gains a static next-eclipse chip via the
        # combined tags: from Palo Alto the sooner eclipse is the
        # 2026-03-03 total lunar (the 2025-09-07 total is not visible).
        assert '<span class="k">lunar eclipse</span>' in html
        assert 'Mar 3 2026' in html
        # Sun and moon cards: constellation rows, and per-kind eclipse
        # rows whose dates carry the year (an eclipse can be years out).
        assert '>Gemini<' in html                  # the sun, just past the boundary
        assert '>Aries<' in html                   # the moon
        assert '03/03/2026' in html                # lunar eclipse row
        assert '(total)' in html
        assert '01/14/2029' in html                # solar eclipse row: the 2029 partial
        assert '(partial)' in html
        # Every planet chip names its constellation, statically, after the
        # javascript-filled chipsub (renderPlanets targets the first).
        assert 'in Pisces' in html                 # saturn
        assert 'in Leo' in html                    # mars
        assert html.count('<div class="chipsub mono">in ') == 8

    def test_no_hex_colors_in_cheetah_files(self):
        """Cheetah owns '#': hex color literals in the template or the
        javascript include would be eaten as directives/comments.  All
        colors must come from classes in celestial.css."""
        import re
        skin_dir = os.path.join(REPO_ROOT, 'skins', 'Celestial')
        for name in ('index.html.tmpl', 'realtime_updater.inc'):
            source = open(os.path.join(skin_dir, name)).read()
            assert not re.search(r'#[0-9A-Fa-f]{6}\b', source), name

    def test_template_constants_consistent(self):
        """The template and the javascript include each hardcode the AU
        conversion constants; they must agree with each other and with the
        IAU values."""
        import re
        skin_dir = os.path.join(REPO_ROOT, 'skins', 'Celestial')
        template = open(os.path.join(skin_dir, 'index.html.tmpl')).read()
        include = open(os.path.join(skin_dir, 'realtime_updater.inc')).read()
        for source, name in ((template, 'index.html.tmpl'), (include, 'realtime_updater.inc')):
            per_au = {float(m) for m in re.findall(r'\$per_au = ([0-9.e+]+)', source)}
            assert per_au == {9.2955807e7, 1.4959787e8}, name
        # The AU-per-light-year divisor for Proxima, in both files.
        assert re.search(r'earth_distance / 63241\.077', template)
        assert re.search(r'proximaAU / 63241\.077', include)

    def test_renders_with_pyephem_almanac(self):
        """With PyEphem but no weewx-skyfield, the report-time page is
        complete except the Proxima Centauri row (PyEphem's star catalog
        lacks it), the sky charts (install hints) and the 1.9-tag cells
        (omitted).  Pins the 6.0 fallback story."""
        ephem = pytest.importorskip('ephem')
        assert ephem  # silence unused-import linting
        with saved_almanacs():
            weewx.almanac.almanacs[:] = [weewx.almanac.PyEphemAlmanacType()]
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            assert alm.hasExtras
            html = self.render(alm)
        assert ':' in self.cell(html, 'almanac.sunrise.raw')
        assert ':' in self.cell(html, 'almanac(horizon=-18).sun(use_center=1).rise.raw')
        assert '&deg;' in self.cell(html, 'almanac.moon.az')
        assert 'miles' in self.cell(html, 'almanac.pluto.earth_distance')
        assert 'than yesterday' in html
        # Proxima: PyEphem cannot serve it; the guarded cell renders empty.
        assert self.cell(html, 'almanac.proxima_centauri.earth_distance') == ''
        # No weewx-skyfield: chart hints, and the 1.9-tag cells are omitted.
        assert html.count('class="skyhint"') == 7
        assert 'eclipse' not in html.lower()
        assert 'Constellation' not in html

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
        assert self.cell(html, 'almanac.sunrise.raw') == ''
        assert self.cell(html, 'almanac.proxima_centauri.earth_distance') == ''
        assert 'Proxima Centauri' in html
        # The 1.9-tag cells (eclipses, constellations) are omitted
        # entirely, not rendered empty.
        assert 'eclipse' not in html.lower()
        assert 'Constellation' not in html
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


class TestMigrateLoopdataFields:
    """The --migrate-loopdata-fields utility: rewrites celestial loop-field
    entries (including pre-3.0 PascalCase names) to weewx-loopdata almanac
    entries in place, drops moonWaxing and the duplicates the rewrites
    create, appends the 6.0 sample-report fields, and touches nothing
    else."""

    def test_camel_names_map_to_almanac(self):
        fields = ['current.outTemp', 'current.sunrise.raw', 'current.sunset',
                  'current.civilTwilightStart.raw', 'current.tomorrowSunrise.raw',
                  'current.yesterdayDaylightDur.raw', 'current.sunTransit.raw',
                  'day.rain.sum']
        new, report = celestial.migrate_loopdata_fields(fields)
        # Rewrites happen in place, order preserved, renditions honored.
        assert new[:8] == ['current.outTemp', 'almanac.sunrise.raw', 'almanac.sunset',
                           'almanac(horizon=-6).sun(use_center=1).rise.raw',
                           'almanac(days=1).sunrise.raw',
                           'almanac(days=-1).sun.visible.raw',
                           'almanac.sun.transit.raw', 'day.rain.sum']
        assert ('current.sunrise.raw', 'almanac.sunrise.raw') in report['renamed']

    def test_pascal_names_chain_through(self):
        """Pre-3.0 PascalCase entries collapse to camelCase first, then map
        to almanac entries -- one pass migrates even a 2.x fields line."""
        fields = ['current.Sunrise.raw', 'current.EarthMoonDistance',
                  'current.daySunshineDur.raw']
        new, report = celestial.migrate_loopdata_fields(fields)
        assert new[:3] == ['almanac.sunrise.raw', 'almanac.moon.earth_distance',
                           'almanac.sun.visible.raw']

    def test_angle_renditions(self):
        """.raw angles become the plain-degree tags; formatted angles become
        the ValueHelper tags."""
        fields = ['current.sunAzimuth.raw', 'current.sunAzimuth',
                  'current.moonDeclination.raw', 'current.marsAltitude.raw']
        new, _ = celestial.migrate_loopdata_fields(fields)
        assert new[:4] == ['almanac.sun.az', 'almanac.sun.azimuth',
                           'almanac.moon.dec', 'almanac.mars.alt']

    def test_moonwaxing_dropped_with_note(self):
        fields = ['current.moonWaxing.raw', 'current.outTemp']
        new, report = celestial.migrate_loopdata_fields(fields)
        assert 'current.moonWaxing.raw' in report['dropped']
        assert not any('moonWaxing' in f for f in new)
        assert any('next_full_moon' in note for note in report['notes'])

    def test_distance_and_fullness_notes(self):
        _, report = celestial.migrate_loopdata_fields(['current.earthMarsDistance'])
        assert any('astronomical units' in note for note in report['notes'])
        _, report = celestial.migrate_loopdata_fields(['current.moonFullness.raw'])
        assert any('almanac.moon.phase' in note for note in report['notes'])

    def test_rewrites_dedup(self):
        # moonFullness and moonFullness.raw both land on almanac.moon.phase.
        fields = ['current.moonFullness', 'current.moonFullness.raw']
        new, report = celestial.migrate_loopdata_fields(fields)
        assert new.count('almanac.moon.phase') == 1
        assert report['dropped'] == ['almanac.moon.phase']

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

    def test_produced_entries_parse_in_loopdata(self):
        """Every almanac entry the migrator can produce -- the appended
        sample-report set and every map target -- must parse in the sibling
        weewx-loopdata checkout's almanac grammar."""
        loopdata = load_loopdata()
        entries = set(celestial._MIGRATION_NEW_FIELDS)
        for raw_entry, formatted_entry in celestial._ALMANAC_FIELD_MAP.values():
            entries.add(raw_entry)
            entries.add(formatted_entry)
        for entry in sorted(entries):
            if not entry.startswith('almanac'):
                assert entry == 'current.dateTime.raw'
                continue
            assert loopdata.LoopData.parse_almanac_field(entry) is not None, entry

    def test_new_fields_cover_the_skin(self):
        """Every almanac key the sample skin's javascript reads must be in
        the appended field set (the dynamically built planet keys are
        expanded here the way the javascript builds them)."""
        import re
        include = open(os.path.join(REPO_ROOT, 'skins', 'Celestial',
                                    'realtime_updater.inc')).read()
        static_keys = set(re.findall(r'''["'](almanac[^"'$]*)["']''', include))
        static_keys.discard('almanac.')          # the concatenation prefix
        keys = {k for k in static_keys if "' + planet + '" not in k}
        for suffix in ('.az', '.alt', '.earth_distance'):
            for planet in celestial._MIGRATION_PLANETS:
                keys.add('almanac.%s%s' % (planet, suffix))
        appended = set(celestial._MIGRATION_NEW_FIELDS)
        # setFullTime reads key + '.raw'; the base keys are element ids only.
        for key in sorted(keys):
            assert key in appended or key + '.raw' in appended, key

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
        assert ('current.Sunrise.raw', 'almanac.sunrise.raw') in report['renamed']
        import configobj
        migrated = configobj.ConfigObj(str(out))
        fields = migrated['LoopData']['Include']['fields']
        assert 'almanac.sunrise.raw' in fields
        assert 'current.Sunrise.raw' not in fields
        assert 'current.outTemp' in fields          # non-celestial preserved
        assert 'almanac.mars.az' in fields          # 6.0 fields appended
        # The rest of the configuration survives the round trip.
        assert migrated['Station']['location'] == 'Test Station'
        # The original file is untouched.
        assert 'current.Sunrise.raw' in conf.read_text()
