"""
test_celestial.py

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Tests for weewx-celestial: the bundled Celestial skin (the live
Geocentric panel, the sky dome and the Next Visible Pass panel, rendered end to
end through Cheetah's errorCatcher), the --migrate-loopdata-fields
utility that rewrites a pre-6.0 [LoopData] [[Include]] fields line to
weewx-loopdata almanac entries, and the --add-satellite /
--remove-satellite utility.

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
import re
import sys
import time
import types

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

# When the identity check proves weewx-skyfield itself serves the page, the
# footer credit names it and links its project page -- in every language.
# (The skyhint's install pointer uses the same anchor, so footer-linkage
# assertions must key on the credit phrasing, not this string alone.)
LINKED_NAME = ('<a href="https://github.com/chaunceygardiner/weewx-skyfield">'
               'weewx-skyfield</a>')

# Where the independent weewx-skyfield extension may be found: a sibling
# checkout of its repo, or the installed copy on this machine.  The sibling
# comes FIRST: during cross-repo co-development it carries the consumer
# contract the next release builds against, while the installed copy can
# lag mid-flight (on 2026-08-05 a stale install without satellite_names
# silently emptied the satellite roster in every render test).
WXSKYFIELD_DIRS = [
    os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield', 'bin', 'user'),
    '/home/weewx/bin/user',
]

# Where the sibling weewx-loopdata checkout may be found (its parser is the
# oracle for the migration tests' almanac grammar).
LOOPDATA_DIRS = [
    os.path.join(os.path.dirname(REPO_ROOT), 'weewx-loopdata', 'bin', 'user'),
    '/home/weewx/bin/user',
]

SKIN_DIR = os.path.join(REPO_ROOT, 'skins', 'Celestial')


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


def make_sky_page(texts=None):
    """The real weewx-skyfield SkyPage for render tests (what the
    celestial_sky shim serves in production), built with the report's
    [Texts] the way the shim passes skin_dict.  Skips when no
    weewx-skyfield is available."""
    load_wxskyfield()
    import wxskyfield_sky
    return wxskyfield_sky.SkyPage({'Texts': texts} if texts else {})


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


@pytest.fixture(scope='session')
def wxskyfield_sat_sky():
    """A satellites-configured Sky: skyfield 2.0's archived solstice-era
    fixture TLEs (deterministic pins: the ISS's Jun 22 03:11 PDT visible
    pass; Tiangong crosses all week but never visibly).  Skips when the
    sibling checkout's fixtures are not available."""
    mod, user_root = load_wxskyfield()
    sat_dir = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                           'tests', 'data')
    if not os.path.exists(os.path.join(sat_dir, 'wxskyfield_sat_25544.tle')):
        pytest.skip('the weewx-skyfield fixture TLEs are not available')
    s = mod.Sky(user_root, load_stars=True,
                satellites={'iss': 25544, 'tiangong': 48274}, sat_dir=sat_dir)
    assert s.is_valid()
    return s


@pytest.fixture()
def wxskyfield_sat_almanac(wxskyfield_sat_sky):
    """An Almanac served by the satellites-configured skyfield almanac."""
    mod, _ = load_wxskyfield()
    with saved_almanacs():
        assert mod.register_almanac(wxskyfield_sat_sky)
        yield weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                    formatter=weewx.units.get_default_formatter())


@pytest.fixture(scope='session')
def wxskyfield_comet_sky():
    """A satellites-AND-comets-configured Sky: the satellite fixture TLEs
    plus skyfield 2.1's archived MPC rows (deterministic pins: Halley
    faint at 35.9 AU, Hale-Bopp below the horizon, C/9999 Z9 'bright' the
    fabricated always-naked-eye comet, 220P/McNaught with the 2026-06-14
    perihelion).  Both families on one Sky so the render and browser
    tests exercise the whole page.  Skips when the sibling checkout's
    fixtures (or its comet support, pre-2.1) are not available."""
    mod, user_root = load_wxskyfield()
    data_dir = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                            'tests', 'data')
    if not os.path.exists(os.path.join(data_dir, 'wxskyfield_comets.txt')):
        pytest.skip('the weewx-skyfield comet fixtures are not available')
    if not os.path.exists(os.path.join(data_dir, 'wxskyfield_sat_25544.tle')):
        pytest.skip('the weewx-skyfield fixture TLEs are not available')
    try:
        s = mod.Sky(user_root, load_stars=True,
                    satellites={'iss': 25544, 'tiangong': 48274},
                    sat_dir=data_dir,
                    comets={'halley': '1P', 'hale_bopp': 'C/1995 O1',
                            'bright': 'C/9999 Z9', 'mcnaught': '220P'},
                    comet_dir=data_dir)
    except TypeError:
        pytest.skip('this weewx-skyfield has no comet support (pre-2.1)')
    assert s.is_valid()
    return s


@pytest.fixture()
def wxskyfield_comet_almanac(wxskyfield_comet_sky):
    """An Almanac served by the comets-configured skyfield almanac."""
    mod, _ = load_wxskyfield()
    with saved_almanacs():
        assert mod.register_almanac(wxskyfield_comet_sky)
        yield weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                    formatter=weewx.units.get_default_formatter())


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

    def test_no_service_no_shim(self):
        """7.0 removed the 6.x service stub and the CelestialSkyPage shim
        from celestial.py; neither name may quietly return THERE (weectl
        uninstall is the prescribed upgrade path, and a data_services
        leftover naming user.celestial.Celestial must keep crashing
        loudly).  8.0's guarded $sky_page access lives in celestial_sky.py,
        deliberately a separate module -- celestial.py stays the CLI."""
        assert not hasattr(celestial, 'Celestial')
        assert not hasattr(celestial, 'CelestialSkyPage')

    def test_version_lockstep(self):
        """The version lives in three places, kept identical: install.py,
        CELESTIAL_VERSION, and the skin.conf [Extras] version."""
        install_src = open(os.path.join(REPO_ROOT, 'install.py')).read()
        m = re.search(r'version\s*=\s*"([^"]+)"', install_src)
        assert m is not None
        assert m.group(1) == celestial.CELESTIAL_VERSION
        skin_src = open(os.path.join(SKIN_DIR, 'skin.conf')).read()
        m = re.search(r'^\s*version\s*=\s*(\S+)', skin_src, re.MULTILINE)
        assert m is not None
        assert m.group(1) == celestial.CELESTIAL_VERSION


class TestCelestialSkyPage:
    """The 8.0 shim (bin/user/celestial_sky.py): presence detection ONLY.
    $sky_page is the real weewx-skyfield SkyPage when its search list
    imports, None otherwise -- and the shim itself must never fail, since
    skin.conf names it unconditionally and a search-list failure kills the
    whole report."""

    @staticmethod
    def _search_list(celestial_sky):
        class Obj:
            pass
        generator = Obj()
        generator.skin_dict = {}
        return celestial_sky.CelestialSkyPage(generator)

    def test_absent_skyfield_yields_none(self, monkeypatch):
        import celestial_sky
        monkeypatch.setattr(celestial_sky, 'SkyPage', None)
        sl = self._search_list(celestial_sky)
        assert sl.get_extension_list(None, None) == [{'sky_page': None}]

    def test_failing_sky_page_yields_none(self, monkeypatch):
        """Any construction failure (a future incompatibility) degrades to
        the hidden-dome page, never a dead report."""
        import celestial_sky

        class Boom:
            def __init__(self, skin_dict):
                raise RuntimeError('boom')

        monkeypatch.setattr(celestial_sky, 'SkyPage', Boom)
        sl = self._search_list(celestial_sky)
        assert sl.get_extension_list(None, None) == [{'sky_page': None}]

    def test_present_skyfield_yields_real_sky_page(self):
        """With the sibling checkout importable the template's $sky_page is
        skyfield's own SkyPage -- the shim wraps nothing."""
        import importlib
        load_wxskyfield()          # puts the checkout on sys.path, or skips
        import celestial_sky
        celestial_sky = importlib.reload(celestial_sky)
        assert celestial_sky.SkyPage is not None
        sl = self._search_list(celestial_sky)
        [entry] = sl.get_extension_list(None, None)
        assert type(entry['sky_page']).__name__ == 'SkyPage'
        assert hasattr(entry['sky_page'], 'dome_svg')


class TestSampleSkinRenders:
    """Render the bundled sample skin end to end, through Cheetah's
    errorCatcher, exactly as weewx does.  Template.compile alone is NOT
    enough: with #errorCatcher Echo, Cheetah re-compiles each placeholder's
    source at render time, and that path rejects constructs plain
    compilation accepts (e.g. a conditional expression inside $(...) loses
    its else-value and dies with SyntaxError only at render time)."""

    @staticmethod
    def render(almanac_obj, with_time_zone=True, lang='en', texts=None, labels=None,
               sky_page=None):
        from Cheetah.Template import Template

        class Obj:
            def __init__(self, **kw):
                self.__dict__.update(kw)

        class Extras(dict):
            def has_key(self, key):
                return key in self

        # The i18n channels, defaulted the way an untranslated report sees
        # them: $gettext is the [Texts] lookup with per-string identity
        # fallback (exactly weewx.cheetahgenerator.Gettext), $lang the
        # skin.conf default.  Every searchList entry MUST mirror a tag
        # core weewx really provides -- 7.2 shipped a $Labels reference
        # because this searchList supplied a 'Labels' entry core weewx
        # never provides, and every production page died with
        # "cannot find 'Labels'".  Hemisphere
        # letters therefore flow the core way: weewx.station.Station
        # builds latitude/longitude 3-tuples (degrees, minutes, letter)
        # from [Labels] hemispheres; the stub does the same.
        texts = texts or {}
        labels = labels or {'hemispheres': ['N', 'S', 'E', 'W']}
        hemis = labels['hemispheres']
        source = open(os.path.join(SKIN_DIR, 'index.html.tmpl')).read()
        # Inline the include so its directives and placeholders are also
        # exercised through the errorCatcher render path.
        include = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        assert '#include "realtime_updater.inc"' in source
        source = source.replace('#include "realtime_updater.inc"', include)
        # expiration_time is HOURS (skin default 24): the include computes
        # 1000*60*60*expiration_time ms, and a value past ~596 hours
        # overflows the browser's 32-bit timer delay -- 86400 here once
        # wrapped to "due immediately" under a fake test clock.
        extras = Extras(loop_data_file='/gauge-data/loop-data.txt',
                        expiration_time=24, refresh_rate=2,
                        version=celestial.CELESTIAL_VERSION)
        if with_time_zone:
            extras['time_zone'] = 'America/Los_Angeles'
        template = Template(source, searchList=[{
            'almanac': almanac_obj,
            'current': Obj(dateTime=Obj(raw=TIME_TS), interval=Obj(raw=5)),
            # windrun stands in for group_distance (this extension registers
            # no observation types).
            'unit': Obj(label=Obj(windrun=' miles'),
                        unit_type=Obj(windrun='mile')),
            'station': Obj(location='Test Station',
                           latitude=('37', '26.55',
                                     hemis[0] if LATITUDE >= 0 else hemis[1]),
                           longitude=('122', '08.45',
                                      hemis[2] if LONGITUDE >= 0 else hemis[3]),
                           stn_info=Obj(latitude_f=LATITUDE, longitude_f=LONGITUDE)),
            'Extras': extras,
            'lang': lang,
            'gettext': lambda key: texts.get(key, key),
            # What celestial_sky.CelestialSkyPage serves in production: the
            # real weewx-skyfield SkyPage, or None when skyfield is absent
            # (the dome panel then degrades to its skyhint).
            'sky_page': sky_page,
        }])
        return str(template)

    def cell(self, html, cell_id):
        match = re.search(r'id="%s"[^>]*>([^<]*)<' % re.escape(cell_id), html)
        assert match is not None, cell_id
        return match.group(1)

    def test_renders_with_skyfield_almanac(self, wxskyfield_almanac):
        html = self.render(wxskyfield_almanac, sky_page=make_sky_page())
        # The roster first-paints from the report almanac: distances as
        # grouped miles (the render passes US units), raw AU and altitude
        # on the sub-line -- for every body including Proxima Centauri.
        assert re.match(r'[\d,]+$', self.cell(html, 'almanac.moon.earth_distance'))
        assert re.match(r'[\d,]+$', self.cell(html, 'almanac.pluto.earth_distance'))
        assert re.match(r'[\d,]+$', self.cell(html, 'almanac.proxima_centauri.earth_distance'))
        assert self.cell(html, 'geo-au-moon').endswith(' au')
        assert self.cell(html, 'geo-au-proxima_centauri').endswith(' au')
        # At local noon on the solstice the sun is up over Palo Alto.
        assert self.cell(html, 'geo-alt-sun').startswith('alt ')
        # Every row rendered; each altitude cell is filled one way or the
        # other.
        for body in ('moon', 'sun', 'mercury', 'venus', 'mars', 'jupiter',
                     'saturn', 'uranus', 'neptune', 'pluto', 'proxima_centauri'):
            assert 'id="geo-row-%s"' % body in html
            alt_cell = self.cell(html, 'geo-alt-%s' % body)
            assert alt_cell.startswith('alt ') or alt_cell == 'below horizon', body
        # The dial container and the inlined javascript engine rendered.
        assert 'id="dial"' in html
        assert 'function buildDial(' in html
        assert 'function setOdometer(' in html
        assert '/gauge-data/loop-data.txt' in html
        # The stylesheet URL is version-tagged so browser caches refetch
        # it after an upgrade (skin.conf supplies version in production).
        assert 'href="celestial.css?v=%s"' % celestial.CELESTIAL_VERSION in html
        assert 'PER_AU = 92955807' in html and "DIST_LABEL = ' miles'" in html
        assert '37.44' in html
        # A capable almanac serves the page: no install hint, and the
        # footer carries the full Skyfield credit (Proxima proves the star
        # catalog) -- naming weewx-skyfield with its manual linked, since
        # the identity check proves it is truly ours.
        assert 'skyhint' not in html
        assert 'Hipparcos' in html
        assert 'Calculated with %s: Skyfield' % LINKED_NAME in html
        # The dome panel embedded skyfield's dome_svg, with the data-body
        # consumer hooks the javascript nudges (the sun is up at the
        # solstice noon).  No satellites on this fixture's Sky: the
        # satellite roster hides, the dome still draws.
        assert 'Sky dome chart' in html
        assert '<g class="dome-body" data-body="sun">' in html
        assert 'id="sat-row-iss"' not in html
        # No satellites: the Next Visible Pass chart has nothing to show, so its
        # section first-paints hidden -- the fragment refetch unhides it
        # if a pass ever enters the elements' validity window.
        assert '<section id="pass-sec" hidden>' in html
        assert 'passhead' not in html

    def test_foreign_skyfield_almanac_not_credited(self, wxskyfield_sky):
        """The independent weewx-skyfield-almanac extension also names its
        class SkyfieldAlmanacType and can pass the Proxima capability probe;
        the footer must then keep the unnamed full credit -- no manual link,
        no claim that weewx-skyfield served the page."""
        mod, _ = load_wxskyfield()
        Foreign = type('SkyfieldAlmanacType', (mod.SkyfieldAlmanacType,),
                       {'__module__': 'skyfieldalmanac'})
        with saved_almanacs():
            weewx.almanac.almanacs[:] = [Foreign(wxskyfield_sky)]
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE,
                                        altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            html = self.render(alm)
        assert 'Hipparcos' in html                       # probe passed...
        assert 'Calculated with <a' not in html          # ...identity did not
        assert 'Calculated with weewx-skyfield' not in html

    def test_renders_with_satellites(self, wxskyfield_sat_almanac):
        """Satellites configured (the skyfield 2.0 fixture TLEs): the dome
        panel's roster first-paints the deterministic fixture pass -- the
        ISS's Jun 22 03:11 PDT visible pass with its appears/peaks/
        disappears line, Tiangong's honest no-pass row -- and the Next
        Pass chart carries the arc."""
        html = self.render(wxskyfield_sat_almanac, sky_page=make_sky_page())
        assert 'id="sat-row-iss"' in html and 'id="sat-row-tiangong"' in html
        line = self.cell(html, 'sat-line-iss')
        assert 'Jun 22 03:11' in line and 'in 15 h' in line
        sub = self.cell(html, 'sat-pass-iss')
        assert 'SSW' in sub and 'SE' in sub and 'ENE' in sub
        assert '19' in sub and '10 min' in sub
        assert self.cell(html, 'sat-line-tiangong') == 'no visible pass in the coming week'
        assert self.cell(html, 'sat-pass-tiangong') == ''
        # The dome-side roster: the next pass of ANY kind, tagged from
        # next_pass.visible.  The fixture's next ISS crossing is six
        # minutes after TIME_TS -- a daytime, not-visible pass (12:06
        # PDT, peak 36 SW) -- and Tiangong crosses at 12:37 (peak 37 N),
        # likewise not visible.
        any_line = self.cell(html, 'sat-any-line-iss')
        assert 'Jun 21 12:06' in any_line and 'in 6 min' in any_line
        any_sub = self.cell(html, 'sat-any-pass-iss')
        assert 'WNW' in any_sub and 'SW' in any_sub and 'SSE' in any_sub
        assert '36' in any_sub and '11 min' in any_sub
        assert 'not visible' in any_sub
        assert 'Jun 21 12:37' in self.cell(html, 'sat-any-line-tiangong')
        assert 'not visible' in self.cell(html, 'sat-any-pass-tiangong')
        # Split by panel: the any-pass roster lives with the dome, the
        # visible-pass roster inside the Next Visible Pass section.
        assert (html.index('id="sat-any-row-iss"') < html.index('id="pass-sec"')
                < html.index('id="sat-row-iss"'))
        # The page's single dome-track lives on the Next Visible Pass chart (the
        # dome deliberately draws no arc: an undated future track on the
        # now-sky would cross stars it will never cross) -- the fixture
        # ISS pass under its dated head line, with the data-body hook the
        # live sweep drives, and the chart's own SVG ids beside the
        # dome's so the two coexist on one page.
        assert html.count('<g class="dome-track"') == 1
        assert '<g class="dome-track" data-body="iss" ' in html
        assert '<section id="pass-sec">' in html
        # 'Iss' is the title-cased fallback: this harness almanac carries
        # no [Almanac] texts.  In production the report's lang file ships
        # iss = ISS (pinned by TestI18n), the same channel as body names.
        assert '<span class="passname">Iss</span>' in html
        when = re.search(r'passwhen mono">([^<]*)<', html)
        assert when is not None
        assert 'Jun 22' in when.group(1)
        assert '03:11' in when.group(1) and '03:21' in when.group(1)
        assert '19' in when.group(1)
        assert 'id="skygp"' in html and 'id="domecp"' in html
        assert 'id="skyg"' in html and 'id="domec"' in html

    def test_pass_row_day_count_is_calendar_days(self, wxskyfield_sat_sky):
        """A pass row's whole-day countdown stands on the same line as the
        pass's own date, so it counts LOCAL CALENDAR DAYS -- the way the
        person reading that date counts.  Elapsed seconds divided down
        disagree with the date beside them twice a day: rounding up calls
        a pass 26 hours out "in 2 days" when it falls tomorrow (Jacques
        Terrettaz's report against weewx-skyfield's countdown chips, the
        2026-08-12 partial solar eclipse, issue #6), and rounding down
        calls one 32 hours out "in 1 day" when it falls the day after.
        The fixture's Jun 21 03:59 PDT visible pass is both boundaries,
        seen from two different mornings."""
        mod, _ = load_wxskyfield()
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sat_sky)

            def line(now_ts):
                alm = weewx.almanac.Almanac(now_ts, LATITUDE, LONGITUDE,
                                            altitude=ALTITUDE_M,
                                            formatter=weewx.units.get_default_formatter())
                rise = alm.iss.next_visible_pass.rise.raw
                assert abs(rise - 1750503568) < 1, 'fixture pass moved'
                return self.cell(self.render(alm, sky_page=make_sky_page()), 'sat-line-iss')

            # Jun 20 02:00 PDT: the pass is 26 hours out and TOMORROW.
            tomorrow = line(1750410000)
            assert 'Jun 21 03:59' in tomorrow
            assert 'in 1 day' in tomorrow
            # Jun 19 20:00 PDT: 32 hours out, and the day after tomorrow.
            two_days = line(1750388400)
            assert 'Jun 21 03:59' in two_days
            assert 'in 2 days' in two_days
            # Under a day the row keeps its finer elapsed-time resolution:
            # that is what a go-watch reader wants, whichever side of
            # midnight the pass falls on.
            assert 'in 16 h' in line(1750446000)          # Jun 20 12:00 PDT

    def test_renders_with_comets(self, wxskyfield_comet_almanac):
        """Comets configured (the skyfield 2.1 fixture MPC rows): the
        Geocentric roster gains one guarded row per comet (Halley's cells
        filled -- 35.9 AU, honestly faint; Hale-Bopp below the horizon at
        the fixture noon), the javascript gets the same enumeration
        through COMET_NAMES, the countdown row first-paints its always-on
        chips from the report almanac, and the embedded dome carries the
        comet marks' data-bright/comet-tail hooks through untouched."""
        html = self.render(wxskyfield_comet_almanac, sky_page=make_sky_page())
        for comet in ('halley', 'hale_bopp', 'bright', 'mcnaught'):
            assert 'id="geo-row-%s"' % comet in html
            # Every perihelion guest bakes its target even while hidden
            # (all four fixture perihelia are outside the 30-day
            # window; Hale-Bopp's is decades PAST -- the epoch still
            # bakes, the window check keeps the chip hidden).
            assert re.search(r'id="chip-peri-%s" data-ts="\d+" hidden' % comet,
                             html)
        # The roster reads nearest-tier outward: comets sit between
        # Pluto and the stellar rim, never past Proxima.
        assert (html.index('id="geo-row-pluto"')
                < html.index('id="geo-row-halley"')
                < html.index('id="geo-row-mcnaught"')
                < html.index('id="geo-row-proxima_centauri"'))
        assert re.match(r'[\d,]+$', self.cell(html, 'almanac.halley.earth_distance'))
        assert self.cell(html, 'geo-au-halley').endswith(' au')
        assert self.cell(html, 'geo-alt-halley').startswith('alt ')
        assert self.cell(html, 'geo-alt-hale_bopp') == 'below horizon'
        assert 'COMET_NAMES = ["halley", "hale_bopp", "bright", "mcnaught"];' in html
        assert 'function renderComets(' in html
        # The countdown row: the pass chip and the windowed guests
        # first-paint hidden; the sun, shower and darkness chips
        # first-paint the COUNTDOWN ITSELF -- the remaining time at
        # generation, in the shape the javascript ticks: hh:mm:ss
        # inside the final day, days-hours-minutes beyond (seconds are
        # noise at that range) -- never the event's clock time alone (a
        # countdown chip whose only number is a wall-clock time reads
        # as remaining time and lies); the clock time / moon note is
        # the small detail beside it (noon: sunset comes before
        # sunrise, ~8 h out; the fixture shower peak is ~38 days out,
        # so its countdown reads days-hours-minutes).
        assert 'id="countdown"' in html
        # The pass chip first-paints the soonest visible pass (the
        # fixture ISS pass tomorrow morning, ~15 h out) -- all four
        # always-on chips stand from the first byte, none pops in on
        # the first loop packet.
        assert re.search(r'id="chip-pass" data-ts="\d+" data-set="\d+"', html)
        assert self.cell(html, 'chip-pass-k') == 'Iss'
        assert self.cell(html, 'chip-pass-d') == 'appears in'
        assert re.match(r'\d{2}:\d{2}:\d{2}$', self.cell(html, 'chip-pass-v'))
        # The supermoon and eclipse guests bake their targets (and the
        # eclipse its kind-derived label) even while out of window --
        # nothing determinable at report time waits for the feed.
        assert re.search(r'id="chip-super" data-ts="\d+" hidden', html)
        assert re.search(r'id="chip-eclipse" data-ts="\d+" hidden', html)
        assert self.cell(html, 'chip-eclipse-k') in ('lunar eclipse',
                                                     'solar eclipse')
        assert self.cell(html, 'chip-sun-k') == 'sunset'
        assert re.match(r'\d{2}:\d{2}:\d{2}$', self.cell(html, 'chip-sun-v'))
        assert re.match(r'\d{2}:\d{2}$', self.cell(html, 'chip-sun-d'))
        assert self.cell(html, 'chip-shower-k') == 'Southern Delta Aquariids'
        assert re.match(r'\d{1,3}d \d{1,2}h \d{1,2}m$', self.cell(html, 'chip-shower-v'))
        assert 'moon ' in self.cell(html, 'chip-shower-d')
        assert self.cell(html, 'chip-dark-k') == 'darkness begins'
        assert re.match(r'\d{2}:\d{2}:\d{2}$', self.cell(html, 'chip-dark-v'))
        assert re.match(r'\d{2}:\d{2}$', self.cell(html, 'chip-dark-d'))
        # The season chip: from the June fixture the next event is
        # September's equinox, 93 days out -- outside the 30-day window,
        # so the chip first-paints hidden, but its label and target bake
        # so the javascript can unhide it the moment the window opens
        # (northern station: 'autumn begins').
        assert re.search(r'id="chip-season" data-ts="\d+" hidden', html)
        assert self.cell(html, 'chip-season-k') == 'autumn begins'
        assert self.cell(html, 'chip-season-v') == ''
        # Earth's apsis chip: the fixture aphelion is ~12 days out --
        # INSIDE the window, so this guest first-paints visible and
        # counting, date detail underneath.
        assert re.search(r'id="chip-apsis" data-ts="\d+">', html)
        assert self.cell(html, 'chip-apsis-k') == 'Earth aphelion'
        assert re.match(r'\d{1,2}d \d{1,2}h \d{1,2}m$', self.cell(html, 'chip-apsis-v'))
        assert re.match(r'\w+ \d{1,2} \d{2}:\d{2}$', self.cell(html, 'chip-apsis-d'))
        # The embedded dome passes the 2.1 comet markup through intact:
        # Halley's hollow diamond (mag 25.6) and the fabricated
        # always-bright comet's solid one, tails and all.  (No radiant at
        # the June fixture instant -- active_meteor_showers is empty.)
        assert 'data-body="halley" data-bright="0"' in html
        assert 'data-body="bright" data-bright="1"' in html
        assert 'class="comet-tail"' in html

    def test_comet_absence_renders_absence(self):
        """An elementless comet (MPC drops faded ones) serves None across
        its surface: the roster row renders honestly EMPTY cells -- never
        the string "None" -- and its perihelion chip stays hidden."""
        mod, user_root = load_wxskyfield()
        data_dir = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                                'tests', 'data')
        if not os.path.exists(os.path.join(data_dir, 'wxskyfield_comets.txt')):
            pytest.skip('the weewx-skyfield comet fixtures are not available')
        try:
            ghost_sky = mod.Sky(user_root, load_stars=False,
                                comets={'ghost': '998P'}, comet_dir=data_dir)
        except TypeError:
            pytest.skip('this weewx-skyfield has no comet support (pre-2.1)')
        with saved_almanacs():
            assert mod.register_almanac(ghost_sky)
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE,
                                        altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            html = self.render(alm, sky_page=make_sky_page())
        assert 'id="geo-row-ghost"' in html
        assert self.cell(html, 'almanac.ghost.earth_distance') == ''
        assert self.cell(html, 'geo-au-ghost') == ''
        assert self.cell(html, 'geo-alt-ghost') == ''
        assert 'id="chip-peri-ghost" hidden' in html
        assert self.cell(html, 'chip-peri-ghost-k') == ''

    @staticmethod
    def render_dome_fragment(name, search):
        """Render a dome fragment template FILE-based, so Cheetah's real
        #include path runs: the include compiles separately and sees
        only `#set global` variables -- textual inlining hid exactly
        that (a local $frag_k rendered fine in the test and failed in
        production).  Cheetah resolves the #include path against the
        CWD, which weewx's generator (and so this test) makes the skin
        directory."""
        from Cheetah.Template import Template
        cwd = os.getcwd()
        os.chdir(SKIN_DIR)
        try:
            return str(Template(file=os.path.join(SKIN_DIR, name),
                                searchList=[search]))
        finally:
            os.chdir(cwd)

    def test_dome_fragment_template(self, wxskyfield_almanac):
        """dome-svg.txt.tmpl, the refetch fragment (stagger slot 0): the
        self-describing wrapper around the dome SVG (data-body hooks
        included) with a capable $sky_page, and EMPTY without one --
        never error text the javascript would inject.  Without a
        $current the interval falls back to 300 s: step 60, count 5."""
        out = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'almanac': wxskyfield_almanac, 'sky_page': make_sky_page()})
        assert out.lstrip().startswith('<div class="domefrag" data-dome-ts="')
        assert 'data-dome-ts="%d"' % TIME_TS in out
        assert 'data-dome-slot="0"' in out
        assert 'data-dome-step="60"' in out
        assert 'data-dome-count="5"' in out
        assert '<svg' in out
        assert 'data-body="sun"' in out
        empty = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'almanac': wxskyfield_almanac, 'sky_page': None})
        assert empty.strip() == ''

    def test_dome_fragment_stagger(self, wxskyfield_almanac):
        """The staggered slots: at a 5-minute interval slots 0-4 carry
        skies 60 s apart and slots 5-9 are honestly empty; at a 2-hour
        interval all ten slots emit at interval/10 spacing, so any
        archive interval gets full-cycle coverage.  The shifted almanac
        rides core WeeWX's $almanac(almanac_time=...) -- the sky must
        actually differ between slots."""
        from types import SimpleNamespace

        def render(name, interval_minutes):
            current = SimpleNamespace(
                interval=SimpleNamespace(raw=interval_minutes))
            return self.render_dome_fragment(name, {
                'almanac': wxskyfield_almanac, 'sky_page': make_sky_page(),
                'current': current})

        out0 = render('dome-svg.txt.tmpl', 5)
        out4 = render('dome-svg-4.txt.tmpl', 5)
        assert 'data-dome-ts="%d"' % (TIME_TS + 4 * 60) in out4
        # ts is the slot's OWN depicted time, so the slot number must ride
        # along: it is what lets the javascript recover the cycle base
        # (ts - slot*step) instead of walking relative to the displayed
        # fragment -- the 8.0 zigzag regression.
        assert 'data-dome-slot="4"' in out4
        assert 'data-dome-step="60"' in out4 and 'data-dome-count="5"' in out4
        assert out0 != out4          # four minutes of sky rotation
        for k in (5, 9):
            empty = render('dome-svg-%d.txt.tmpl' % k, 5)
            assert empty.strip() == '', k
        slow9 = render('dome-svg-9.txt.tmpl', 120)
        assert 'data-dome-ts="%d"' % (TIME_TS + 9 * 720) in slow9
        assert 'data-dome-slot="9"' in slow9
        assert 'data-dome-step="720"' in slow9
        assert 'data-dome-count="10"' in slow9

    def test_dome_slot_walk_is_monotonic(self):
        """The zigzag regression (caught in the NOAA-21 live capture): the
        fragment's data-dome-ts is its OWN depicted time, so the walk must
        recover the cycle base through data-dome-slot (base = ts -
        slot*step) before computing the next slot.  Walking from ts
        directly made the next slot RELATIVE to whichever slot was showing
        and the dome stepped 0,2,1,3,2 -- forward two minutes, back one --
        every cycle.  Pins the include's reading of the contract, and
        simulates both arithmetics to hold the fixed one monotonic and
        prove the broken one was not."""
        src = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        assert "getAttribute('data-dome-slot')" in src
        assert re.search(r'm\.ts\s*-\s*m\.slot\s*\*\s*m\.step', src)
        # The backward guard: a late cycle answering the slot-0 ask with
        # the previous cycle's file must not step the sky backward.
        assert re.search(r'parseFloat\(m\[1\]\)\s*<\s*cur\.ts', src)

        step, count = 60, 5

        def walk(fixed, lag):
            # Fetches at :25 past each minute against cycles generated
            # every count*step seconds, whose files land lag seconds after
            # the cycle instant.  fixed applies the repaired arithmetic
            # AND the backward guard (both are the fix); the pre-fix walk
            # ran the fragment's own depicted time as the base, unguarded.
            shown = (0, 0)                    # (cycle base, slot)
            depicted = []
            for t in range(25, 1800, step):
                base = shown[0] + (0 if fixed else shown[1] * step)
                k = (t - base) // step
                k = k if 1 <= k < count else 0
                on_disk = ((t - lag) // (count * step)) * (count * step)
                fetched = (max(0, on_disk), k)
                if fetched != shown and (not fixed or
                        fetched[0] + fetched[1] * step
                        >= shown[0] + shown[1] * step):
                    shown = fetched
                depicted.append(shown[0] + shown[1] * step)
            return depicted

        # Prompt cycles: monotonic, one step per minute in steady state.
        good = walk(fixed=True, lag=15)
        assert all(b - a in (0, step) for a, b in zip(good, good[1:]))
        assert good[-count:] == list(range(good[-1] - (count - 1) * step,
                                           good[-1] + step, step))
        # Late cycles (files land 200 s in): the guard holds the dome on
        # the freshest sky it has, then catches up forward when the files
        # land -- never a step backward.
        late = walk(fixed=True, lag=200)
        assert all(b >= a for a, b in zip(late, late[1:]))
        # The pre-fix arithmetic really did zigzag -- the regression is real.
        bad = walk(fixed=False, lag=15)
        assert any(b < a for a, b in zip(bad, bad[1:]))

    def test_pass_chart_fragment_template(self, wxskyfield_sat_almanac):
        """pass-chart.txt.tmpl, the refetch fragment: the dated head line
        and the chart SVG (dome-track hook included) with a capable
        $sky_page and a pass to show, and EMPTY without a $sky_page --
        the javascript hides the panel on a deliberate empty and keeps
        its chart on junk, so the fragment must never carry error
        text."""
        from Cheetah.Template import Template
        source = open(os.path.join(SKIN_DIR, 'pass-chart.txt.tmpl')).read()
        out = str(Template(source, searchList=[{
            'almanac': wxskyfield_sat_almanac, 'sky_page': make_sky_page()}]))
        assert out.lstrip().startswith('<div class="passhead">')
        assert '<svg' in out
        assert '<g class="dome-track" data-body="iss" ' in out
        empty = str(Template(source, searchList=[{
            'almanac': wxskyfield_sat_almanac, 'sky_page': None}]))
        assert empty.strip() == ''

    def test_pass_chart_fragment_empty_without_satellites(self, wxskyfield_almanac):
        """No configured satellites: pass_chart_html itself returns '' and
        the fragment ships empty -- the hidden-panel signal, not an
        error."""
        from Cheetah.Template import Template
        source = open(os.path.join(SKIN_DIR, 'pass-chart.txt.tmpl')).read()
        out = str(Template(source, searchList=[{
            'almanac': wxskyfield_almanac, 'sky_page': make_sky_page()}]))
        assert out.strip() == ''

    def test_javascript_reads_only_the_field_set(self):
        """The javascript's loop-data keys, expanded the way the include
        builds them (a per-body prefix plus .az/.alt/.earth_distance, and
        the literal moon-phase and dateTime keys), must equal
        _MIGRATION_NEW_FIELDS exactly -- the skin consumes the whole
        migrated field set and nothing else."""
        include = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        m = re.search(r'var GEO_BODIES = \[(.*?)\];', include, re.DOTALL)
        assert m is not None
        bodies = re.findall(r"'([a-z_]+)'", m.group(1))
        assert len(bodies) == 11
        keys = set()
        for body in bodies:
            for suffix in ('.az', '.alt', '.earth_distance'):
                keys.add('almanac.%s%s' % (body, suffix))
        # The literal (non-constructed) keys the include reads -- the
        # moon-phase pair, the anchor, and the countdown chips' event
        # instants (8.1): the sun pair, astronomical darkness (the
        # parenthesized horizon spelling, byte-exact with the fields
        # line), the shower peak/label pair, the supermoon and the
        # eclipse trio.
        for literal in ('current.dateTime.raw', 'almanac.moon.phase',
                        'almanac.next_full_moon.unix_epoch.raw',
                        'almanac.next_new_moon.unix_epoch.raw',
                        'almanac.sun.next_setting.unix_epoch.raw',
                        'almanac.sun.next_rising.unix_epoch.raw',
                        'almanac(horizon=-18).sun.next_setting.unix_epoch.raw',
                        'almanac(horizon=-18).sun.next_rising.unix_epoch.raw',
                        'almanac.next_equinox.unix_epoch.raw',
                        'almanac.next_solstice.unix_epoch.raw',
                        'almanac.next_perihelion.unix_epoch.raw',
                        'almanac.next_aphelion.unix_epoch.raw',
                        'almanac.next_meteor_shower.peak.unix_epoch.raw',
                        'almanac.next_meteor_shower.label',
                        'almanac.next_supermoon.unix_epoch.raw',
                        'almanac.next_eclipse.unix_epoch.raw',
                        'almanac.next_eclipse_kind'):
            assert "'%s'" % literal in include or '"%s"' % literal in include, literal
            keys.add(literal)
        # The eclipse TYPE is deliberately NOT a loopdata field: the
        # type detail is generation-painted from the report tag
        # ($almanac.next_eclipse_type in the template) and never
        # rewritten live, so the line carries no field for it.
        assert 'almanac.next_eclipse_type' not in celestial._MIGRATION_NEW_FIELDS
        # The satellite layer is DYNAMIC: SAT_NAMES is generated from
        # skyfield 2.0's public $sky_page.satellite_names() (the template
        # builds the roster rows from the same enumeration), and the
        # javascript composes each satellite's keys from the pinned
        # suffix set below.  _MIGRATION_NEW_FIELDS therefore carries the
        # installer-DEFAULT satellites only (iss, tiangong); extra
        # [[Satellites]] entries take the same suffix set by hand -- the
        # README documents the pattern.
        assert 'satellite_names()' in include
        # Per satellite, the javascript reads two pass chains through one
        # row renderer (renderPassRow composes base + attribute): the
        # chart-side next_visible_pass and the dome-side next_pass, the
        # latter adding its visible bool for the row's tag.  The base and
        # attribute literals must each appear in the include -- the
        # composition the test mirrors here.
        sats = ['iss', 'tiangong']
        PASS_BASES = ('.next_pass', '.next_visible_pass')
        PASS_ATTRS = (
            '.rise.unix_epoch.raw',
            '.set.unix_epoch.raw',
            '.max_altitude.degree_angle.raw',
            '.duration.second.raw',
            '.rise_azimuth.ordinal_compass',
            '.culmination_azimuth.ordinal_compass',
            '.set_azimuth.ordinal_compass',
        )
        for literal in (('.az', '.alt', '.sunlit', '.label', '.visible')
                        + PASS_BASES + PASS_ATTRS):
            assert "'%s'" % literal in include, literal
        for sat in sats:
            for suffix in ('.az', '.alt', '.sunlit', '.label'):
                keys.add('almanac.%s%s' % (sat, suffix))
            for base in PASS_BASES:
                for attr in PASS_ATTRS:
                    keys.add('almanac.%s%s%s' % (sat, base, attr))
            keys.add('almanac.%s.next_pass.visible' % sat)
        # The comet layer is dynamic the same way: COMET_NAMES from
        # skyfield 2.1's public comet_names(), the per-comet keys
        # composed from the suffix set below.  _MIGRATION_NEW_FIELDS
        # carries the installer-DEFAULT comets (halley, hale_bopp);
        # extra [[Comets]] entries take the same six-entry pattern
        # (--add-comet writes it).
        assert 'comet_names()' in include
        for literal in ('.mag', '.perihelion.unix_epoch.raw'):
            assert "'%s'" % literal in include, literal
        for comet in ('halley', 'hale_bopp'):
            for suffix in ('.az', '.alt', '.earth_distance', '.mag', '.label',
                           '.perihelion.unix_epoch.raw'):
                keys.add('almanac.%s%s' % (comet, suffix))
        assert keys == set(celestial._MIGRATION_NEW_FIELDS)
        # The pre-7.6 unpinned moon keys survive as read fallbacks, so a
        # fields line migrated under <= 7.5 keeps working across the
        # upgrade with no weewx.conf change -- and the pass times,
        # duration and peak altitude keep bare-.raw fallbacks for the same
        # reason (a hand-written unpinned fields line).
        for legacy in ('almanac.next_full_moon.raw', 'almanac.next_new_moon.raw'):
            assert "'%s'" % legacy in include or '"%s"' % legacy in include, legacy
        for legacy_attr in ('.rise.raw', '.set.raw',
                            '.max_altitude.raw', '.duration.raw'):
            assert "'%s'" % legacy_attr in include, legacy_attr

    def test_no_window_global_collisions(self):
        """The include's script runs at window scope, so its top-level
        names must never shadow window built-ins: `var history` cost hours
        on 2026-07-23 -- the declaration silently fails to bind against
        the read-only History object and everything downstream throws.
        This lints every top-level var, function and bare assignment in
        the include against the hazardous window property names."""
        BANNED = {'history', 'location', 'name', 'top', 'parent', 'self',
                  'frames', 'length', 'status', 'opener', 'closed', 'event',
                  'origin', 'screen', 'navigator', 'document', 'window',
                  'external', 'crypto', 'performance', 'print', 'close',
                  'open', 'stop', 'focus', 'blur', 'scroll', 'alert',
                  'confirm', 'prompt', 'toolbar', 'menubar', 'scrollbars',
                  'statusbar', 'locationbar', 'personalbar', 'localStorage',
                  'sessionStorage', 'indexedDB', 'caches', 'customElements',
                  'frameElement', 'speechSynthesis', 'visualViewport'}
        include = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        # Top level in this file is two-space indentation directly under
        # <script>; nested code is indented further.
        names = set(re.findall(r'^  var ([A-Za-z_$][\w$]*)', include, re.MULTILINE))
        names |= set(re.findall(r'^  function ([A-Za-z_$][\w$]*)', include, re.MULTILINE))
        names |= set(re.findall(r'^  ([A-Za-z_$][\w$]*) =', include, re.MULTILINE))
        assert names, 'the top-level name scan matched nothing; fix the regexes'
        collisions = names & BANNED
        assert not collisions, collisions

    def test_page_runs_in_a_real_browser(self, wxskyfield_sat_almanac, tmp_path):
        """The one test that executes the page's javascript where it
        actually runs: headless Chromium (the weewx-skyfield repo's
        playwright env), a served page, and a loop-data feed that advances
        across polls.  Asserts the live machinery all comes up -- no page
        errors, dial dots drawn, rate lines derived, trails visible --
        which is exactly the coverage that would have caught the
        `var history` window-global collision (invisible to every
        non-browser harness, because only a browser predefines
        window.history).  Skips when the playwright env is absent."""
        import http.server
        import json as jsonlib
        import socketserver
        import subprocess
        import threading

        pwenv = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                             'tools', 'pwenv', 'bin', 'python')
        if not os.path.exists(pwenv):
            pytest.skip('the weewx-skyfield tools/pwenv playwright env is not available')

        # Three packets, 2 s apart, computed by the same registered
        # almanac the page rendered from (the fixture keeps it registered
        # for the duration of this test).
        bodies = ['sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter',
                  'saturn', 'uranus', 'neptune', 'pluto', 'proxima_centauri']
        packets = []
        for ts in (TIME_TS, TIME_TS + 2, TIME_TS + 4):
            alm = weewx.almanac.Almanac(ts, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            r = {'current.dateTime.raw': ts,
                 'almanac.moon.phase': alm.moon.phase,
                 'almanac.next_full_moon.unix_epoch.raw': alm.next_full_moon.raw,
                 'almanac.next_new_moon.unix_epoch.raw': alm.next_new_moon.raw}
            for b in bodies:
                obj = getattr(alm, b)
                r['almanac.%s.az' % b] = obj.az
                r['almanac.%s.alt' % b] = obj.alt
                r['almanac.%s.earth_distance' % b] = obj.earth_distance
            # The satellite layer's keys, from the same registered almanac
            # (Tiangong's pass fields serialize as honest JSON nulls).
            for s in ('iss', 'tiangong'):
                sat = getattr(alm, s)
                r['almanac.%s.az' % s] = sat.az
                r['almanac.%s.alt' % s] = sat.alt
                r['almanac.%s.sunlit' % s] = sat.sunlit
                r['almanac.%s.label' % s] = str(sat.label)
                p = sat.next_visible_pass
                r['almanac.%s.next_visible_pass.rise.unix_epoch.raw' % s] = p.rise.raw
                r['almanac.%s.next_visible_pass.set.unix_epoch.raw' % s] = p.set.raw
                r['almanac.%s.next_visible_pass.max_altitude.degree_angle.raw' % s] = \
                    p.max_altitude.raw
                r['almanac.%s.next_visible_pass.duration.second.raw' % s] = p.duration.raw
                r['almanac.%s.next_visible_pass.rise_azimuth.ordinal_compass' % s] = \
                    str(p.rise_azimuth.ordinal_compass())
                r['almanac.%s.next_visible_pass.culmination_azimuth.ordinal_compass' % s] = \
                    str(p.culmination_azimuth.ordinal_compass())
                r['almanac.%s.next_visible_pass.set_azimuth.ordinal_compass' % s] = \
                    str(p.set_azimuth.ordinal_compass())
                p2 = sat.next_pass
                r['almanac.%s.next_pass.rise.unix_epoch.raw' % s] = p2.rise.raw
                r['almanac.%s.next_pass.set.unix_epoch.raw' % s] = p2.set.raw
                r['almanac.%s.next_pass.max_altitude.degree_angle.raw' % s] = \
                    p2.max_altitude.raw
                r['almanac.%s.next_pass.duration.second.raw' % s] = p2.duration.raw
                r['almanac.%s.next_pass.rise_azimuth.ordinal_compass' % s] = \
                    str(p2.rise_azimuth.ordinal_compass())
                r['almanac.%s.next_pass.culmination_azimuth.ordinal_compass' % s] = \
                    str(p2.culmination_azimuth.ordinal_compass())
                r['almanac.%s.next_pass.set_azimuth.ordinal_compass' % s] = \
                    str(p2.set_azimuth.ordinal_compass())
                r['almanac.%s.next_pass.visible' % s] = p2.visible
            packets.append(jsonlib.dumps(r).encode())

        (tmp_path / 'index.html').write_text(
            self.render(wxskyfield_sat_almanac, sky_page=make_sky_page()))
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        served = {'n': 0}

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body = packets[min(served['n'], len(packets) - 1)]
                    served['n'] += 1
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return super().do_GET()

            def translate_path(self, path):
                return str(tmp_path / path.split('?')[0].lstrip('/'))

            def log_message(self, *a):
                pass

        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        runner = tmp_path / 'runner.py'
        runner.write_text(
            'import json, sys\n'
            'from playwright.sync_api import sync_playwright\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    page = browser.new_page()\n'
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            "    page.goto('http://127.0.0.1:%d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    page.wait_for_timeout(5500)\n'
            '    out = {\n'
            "        'errors': errors,\n"
            "        'rate': page.inner_text('#geo-rate-mercury'),\n"
            "        'dots': page.eval_on_selector_all(\n"
            "            '#dial .geodot:not([display])', 'els => els.length'),\n"
            "        'trails': page.eval_on_selector_all(\n"
            '            \'#dial line.trail:not([display="none"])\', "els => els.length"),\n'
            "        'dome': page.eval_on_selector_all('#dome-svg svg', 'els => els.length'),\n"
            "        'nudged': page.eval_on_selector_all(\n"
            "            '#dome-svg g.dome-body[transform]', 'els => els.length'),\n"
            "        'satdots': page.eval_on_selector_all('#dome-svg .satdot', 'els => els.length'),\n"
            "        'satline': page.inner_text('#sat-line-iss'),\n"
            "        'passchart': page.eval_on_selector_all('#pass-chart svg', 'els => els.length'),\n"
            "        'passwhen': page.inner_text('#pass-chart .passwhen'),\n"
            "        'anyline': page.inner_text('#sat-any-line-iss'),\n"
            "        'anysub': page.inner_text('#sat-any-pass-iss'),\n"
            "        'passnudged': page.eval_on_selector_all(\n"
            "            '#pass-chart g.dome-body[transform]', 'els => els.length'),\n"
            '    }\n'
            '    browser.close()\n'
            'print(json.dumps(out))\n' % port)
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        assert 'receding' in out['rate'] or 'approaching' in out['rate']
        assert out['dots'] >= 9            # sun + planets drawn (moon is a group)
        assert out['trails'] > 200         # 24 segments x 11 bodies, visible
        assert served['n'] >= 2            # the page really polled repeatedly
        # The dome came up live: the embedded backdrop is present, the
        # above-horizon marks picked up nudge transforms (the sun is up at
        # the fixture noon), no live satellite marker (the ISS is below the
        # horizon), and the ISS countdown row went live (the javascript
        # rewrites the first-paint line with its own date · countdown).
        assert out['dome'] == 1
        assert out['nudged'] >= 1
        assert out['satdots'] == 0
        assert 'Jun 22' in out['satline']
        # The fixture pass is behind the browser's real clock, so this row
        # sits in the window between a pass's set and the feed's next_pass
        # rollover: satWhen must say "just set", never clamp the negative
        # countdown to "in 1 min".
        assert 'just set' in out['satline']
        assert 'in 1 min' not in out['satline']
        # The Next Visible Pass chart came up (the fixture ISS pass is tomorrow
        # morning) and its featured dot was NOT swept: the pass is not in
        # progress, so renderPass leaves the chart standing as drawn.
        assert out['passchart'] == 1
        assert '03:11' in out['passwhen']
        assert out['passnudged'] == 0
        # The dome-side any-pass roster went live: the ISS's next
        # crossing is the fixture's daytime Jun 21 pass, tagged not
        # visible.
        assert 'Jun 21' in out['anyline']
        assert 'not visible' in out['anysub']

    def test_pass_countdown_day_count_in_a_real_browser(self, wxskyfield_almanac,
                                                        tmp_path):
        """satWhen's whole-day countdown, run where it runs: the live twin
        of test_pass_row_day_count_is_calendar_days.  The count sits on the
        same line as the pass's date (fmtDayHM), so it is a LOCAL CALENDAR
        day difference -- the boundaries below are exactly the two cases
        elapsed-seconds arithmetic gets wrong, rounding up (26 hours out
        but tomorrow) and rounding down (47 hours out but three dates
        along).  The browser here deliberately sits in Auckland while the
        page displays America/Los_Angeles: the 40-hour case reads two days
        in the station's zone and one in the browser's, so it fails if the
        reckoning ever slips to new Date(...).getDate().  Skips when the
        playwright env is absent."""
        import http.server
        import json as jsonlib
        import socketserver
        import subprocess
        import threading

        pwenv = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                             'tools', 'pwenv', 'bin', 'python')
        if not os.path.exists(pwenv):
            pytest.skip('the weewx-skyfield tools/pwenv playwright env is not available')

        # The fall-back Sunday, where 24 elapsed hours land back on the
        # same date and the floor at 1 keeps the row off "in 0 days".
        fall_back = time.mktime((2026, 11, 1, 0, 30, 0, 0, 0, -1))
        cases = [(TIME_TS, 26 * 3600),        # tomorrow, though 26 hours out
                 (TIME_TS, 47 * 3600),        # two dates along, though under 48 h
                 (TIME_TS, 40 * 3600),        # two in Los Angeles, one in Auckland
                 (fall_back, 24 * 3600),      # a 25-hour day is still one day
                 (TIME_TS, 3 * 3600),         # under a day: elapsed time, by design
                 (TIME_TS, 600)]

        (tmp_path / 'index.html').write_text(
            self.render(wxskyfield_almanac, sky_page=make_sky_page()))
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def translate_path(self, path):
                return str(tmp_path / path.split('?')[0].lstrip('/'))

        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        runner = tmp_path / 'runner.py'
        runner.write_text(
            'import json\n'
            'from playwright.sync_api import sync_playwright\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            "    ctx = browser.new_context(timezone_id='Pacific/Auckland')\n"
            '    page = ctx.new_page()\n'
            "    page.goto('http://127.0.0.1:%d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            "    when = page.evaluate('%s.map("
            'function(c) { return satWhen(c[0] + c[1], null, c[0]); })\')\n'
            '    browser.close()\n'
            "print(json.dumps(when))\n" % (port, jsonlib.dumps(cases)))
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        assert jsonlib.loads(proc.stdout) == ['in 1 day', 'in 2 days', 'in 2 days',
                                              'in 1 day', 'in 3 h', 'in 10 min']

    def test_tap_tooltips_in_a_real_browser(self, wxskyfield_sat_almanac, tmp_path):
        """Tap tooltips (sky.js, copied from weewx-skyfield) on all three
        panels that carry <title> marks: an exact tap on a dome mark, on
        the pass chart's featured dot, and on a Geocentric dial dot (whose
        titles this skin's own javascript builds from the loop feed, the
        roster's translated vocabulary) shows the chip with that mark's
        own title text, a tap outside any svg hides it, and a dome
        fragment swap -- the real refreshDome path, fired by
        fast-forwarding the page clock past DOME_REFRESH -- dismisses an
        open chip (this page is live; a chip is a transient answer, never
        a stale overlay) while the document-level delegation keeps working
        on the swapped-in marks with no rebinding.  Skips when the
        playwright env is absent."""
        import http.server
        import json as jsonlib
        import socketserver
        import subprocess
        import threading

        pwenv = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                             'tools', 'pwenv', 'bin', 'python')
        if not os.path.exists(pwenv):
            pytest.skip('the weewx-skyfield tools/pwenv playwright env is not available')

        sky_page = make_sky_page()
        (tmp_path / 'index.html').write_text(
            self.render(wxskyfield_sat_almanac, sky_page=sky_page))
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())
        # The fragment refreshDome swaps in when the fast-forwarded minute
        # arrives: the same dome re-rendered, under a fresh wrapper
        # identity.  The dome/pass chip machinery is independent of loop
        # data (the swap dismissal must be too); only the dial's titles
        # below need the packet.
        # The staged timestamp must be NEWER than the rendered page's
        # (TIME_TS): the backward guard rejects an older sky.
        (tmp_path / 'dome-svg.txt').write_text(
            '<div class="domefrag" data-dome-ts="%d" data-dome-step="60" '
            'data-dome-count="1">%s</div>'
            % (TIME_TS + 60, str(sky_page.dome_svg(wxskyfield_sat_almanac))))
        assert '<svg' in (tmp_path / 'dome-svg.txt').read_text()
        # One loop packet with known mars numbers: the dial's marks and
        # their <title>s exist only once a packet arrives, and a single
        # packet derives no rates, so the title holds exactly these values.
        (tmp_path / 'gauge-data').mkdir()
        (tmp_path / 'gauge-data' / 'loop-data.txt').write_text(jsonlib.dumps({
            'current.dateTime.raw': int(time.time()),
            'almanac.mars.az': 120.0,
            'almanac.mars.alt': 30.0,
            'almanac.mars.earth_distance': 1.66}))

        requested = []

        class Handler(http.server.SimpleHTTPRequestHandler):
            def translate_path(self, path):
                requested.append(path.split('?')[0])
                return str(tmp_path / path.split('?')[0].lstrip('/'))

            def log_message(self, *a):
                pass

        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        runner = tmp_path / 'runner.py'
        runner.write_text(
            'import json, time\n'
            'from playwright.sync_api import sync_playwright\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    # Tall enough that every panel is in view: scrolling would\n'
            '    # dismiss the chip (by design), so the taps must not scroll.\n'
            "    page = browser.new_page(viewport={'width': 1280, 'height': 4000})\n"
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            '    page.clock.install()\n'
            "    page.goto('http://127.0.0.1:%d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    def chip():\n'
            '        return page.evaluate(\n'
            '            """() => { var t = document.querySelector(\'.skytip\');\n'
            '            return t === null ? null :\n'
            "            {shown: t.style.display === 'block', text: t.textContent}; }\"\"\")\n"
            '    def tap(sel):\n'
            '        el = page.locator(sel).first\n'
            '        el.scroll_into_view_if_needed()\n'
            '        box = el.bounding_box()\n'
            "        page.mouse.click(box['x'] + box['width'] / 2,\n"
            "                         box['y'] + box['height'] / 2)\n"
            '    out = {}\n'
            '    sun = \'#dome-svg g.dome-body[data-body="sun"]\'\n'
            "    out['sun_title'] = page.locator(sun + ' title').first.text_content()\n"
            '    tap(sun)\n'
            "    out['sun_chip'] = chip()\n"
            '    page.mouse.click(4, 4)\n'
            "    out['after_empty_tap'] = chip()\n"
            '    iss = \'#pass-chart g.dome-body[data-body="iss"]\'\n'
            "    out['iss_title'] = page.locator(iss + ' title').first.text_content()\n"
            '    tap(iss)\n'
            "    out['iss_chip'] = chip()\n"
            '    page.clock.fast_forward(61000)\n'
            '    time.sleep(1.5)\n'
            "    out['after_swap'] = chip()\n"
            "    out['swapped_dome_ts'] = page.evaluate(\n"
            '        """() => document.querySelector(\'#dome-svg div[data-dome-ts]\')\n'
            '            .getAttribute(\'data-dome-ts\')""")\n'
            '    tap(sun)\n'
            "    out['swapped_chip'] = chip()\n"
            "    out['chips'] = page.evaluate(\n"
            '        """() => document.querySelectorAll(\'.skytip\').length""")\n'
            "    mars = '#dial circle.fill-mars'\n"
            '    page.wait_for_selector(mars, timeout=15000)\n'
            "    out['dial_title'] = page.evaluate(\n"
            '        """() => document.querySelector(\'#dial circle.fill-mars\')\n'
            '            .parentNode.querySelector(\'title\').textContent""")\n'
            '    tap(mars)\n'
            "    out['dial_chip'] = chip()\n"
            "    out['errors'] = errors\n"
            '    browser.close()\n'
            'print(json.dumps(out))\n' % port)
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        # An exact tap shows the mark's own <title> text in the chip.
        assert out['sun_title'].strip()
        assert out['sun_chip'] == {'shown': True, 'text': out['sun_title']}
        # A tap outside any svg dismisses it.
        assert out['after_empty_tap']['shown'] is False
        # The pass chart's featured dot is covered by the same delegation.
        assert out['iss_title'].strip()
        assert out['iss_chip'] == {'shown': True, 'text': out['iss_title']}
        # The fragment swap really happened (the staged wrapper's identity
        # replaced the rendered one) and dismissed the open chip.
        assert '/dome-svg.txt' in requested, requested
        assert out['swapped_dome_ts'] == str(TIME_TS + 60)
        assert out['after_swap']['shown'] is False
        # Delegation binds to nothing, so the swapped-in dome's marks work
        # untouched -- and the same almanac instant renders the same title.
        assert out['swapped_chip'] == {'shown': True, 'text': out['sun_title']}
        assert out['chips'] == 1
        # The Geocentric dial: its marks' titles are built by this skin's
        # own javascript from the loop packet, in the roster's vocabulary,
        # and the same document-level delegation serves the tap.
        assert '/gauge-data/loop-data.txt' in requested, requested
        assert out['dial_title'] == 'Mars · alt 30.0° · 1.660000 au'
        assert out['dial_chip'] == {'shown': True, 'text': out['dial_title']}

    def test_pass_sweep_dot_flips_sunlit_in_a_real_browser(
            self, wxskyfield_sat_almanac, tmp_path):
        """The 8.1 fix for the 8.0 ship-review finding: mid-pass the
        chart's sweeping dot wears the satellite's LIVE sunlit state --
        solid dot vs hollow in-shadow ring, the dome marker's own toggle
        -- not the culmination's state for the whole ride (NOAA-21 Aug 8:
        a shadow culmination drew the ring from rise while the dome
        correctly showed the live shadow entry, the two panels
        disagreeing).  The feed lies the fixture pass into progress
        around the browser's real clock and walks sunlit true -> false ->
        true: the dot must flip to the exact fill/stroke INVERSION of its
        generated look (how the generator itself draws a shadowed
        satellite -- no color knowledge, no CSS coupling) in agreement
        with the dome's live marker, and restore the generated attributes
        when sunlit returns.  Skips when the playwright env is absent."""
        import http.server
        import json as jsonlib
        import re as relib
        import socketserver
        import subprocess
        import threading

        pwenv = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                             'tools', 'pwenv', 'bin', 'python')
        if not os.path.exists(pwenv):
            pytest.skip('the weewx-skyfield tools/pwenv playwright env is not available')

        html = self.render(wxskyfield_sat_almanac, sky_page=make_sky_page())
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        # The generated look, straight from the rendered chart (the only
        # data-sunlit iss group on the page: the ISS is below the horizon
        # at the fixture instant, so the dome draws no marker for it).
        # The fixture pass CULMINATES IN SHADOW -- visible at its ends,
        # ringed at its peak: the NOAA-21 shape of the ship-review finding
        # exactly, so the generated dot is the ring and the live-sunlit
        # phases below flip it solid.
        m = relib.search(r'<g class="dome-body" data-body="iss" data-sunlit="(\d)">'
                         r'<circle[^>]*fill="([^"]+)" stroke="([^"]+)"', html)
        assert m is not None
        gen_sunlit, gen_fill, gen_stroke = m.group(1), m.group(2), m.group(3)
        assert gen_sunlit == '0'
        # Each live state's expected look, relative to the generated pair:
        # the shadowed look is always the exact inversion of the sunlit one.
        shadow_fill, shadow_stroke = gen_fill, gen_stroke
        lit_fill, lit_stroke = gen_stroke, gen_fill

        # Five packets, one per 2 s poll: the pass in progress around the
        # browser's real clock, sunlit walking true -> false -> true (the
        # last packet repeats forever, so the restore state is stable).
        # A dark sky (sun at -30) keeps the dome marker un-faint: the
        # shadow ring is the only toggle under test.
        now = time.time()

        def packet(i, sunlit):
            return jsonlib.dumps({
                'current.dateTime.raw': now + 2 * i,
                'almanac.sun.alt': -30.0,
                'almanac.iss.az': 120.0 + 0.5 * i,
                'almanac.iss.alt': 45.0 + 0.1 * i,
                'almanac.iss.sunlit': sunlit,
                'almanac.iss.label': 'ISS',
                'almanac.iss.next_visible_pass.rise.unix_epoch.raw': now - 60,
                'almanac.iss.next_visible_pass.set.unix_epoch.raw': now + 600,
            }).encode()
        packets = [packet(0, True), packet(1, False), packet(2, False),
                   packet(3, False), packet(4, True)]
        served = {'n': 0}

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body = packets[min(served['n'], len(packets) - 1)]
                    served['n'] += 1
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return super().do_GET()

            def translate_path(self, path):
                return str(tmp_path / path.split('?')[0].lstrip('/'))

            def log_message(self, *a):
                pass

        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        runner = tmp_path / 'runner.py'
        runner.write_text(
            'import json\n'
            'from playwright.sync_api import sync_playwright\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    page = browser.new_page()\n'
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            "    page.goto('http://127.0.0.1:%(port)d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    # The sweep engaged: the feed put the pass in progress.\n'
            "    page.wait_for_selector('#pass-chart g.dome-body[transform]',\n"
            '                           timeout=15000)\n'
            '    # The shadow packets: chart dot ringed, dome dot ringed --\n'
            '    # the two panels agreeing is the point of the fix.\n'
            '    page.wait_for_function("""() => {\n'
            "      var c = document.querySelector('#pass-chart g.dome-body[data-body=iss] circle');\n"
            "      return c !== null && c.getAttribute('fill') === '%(sfill)s' &&\n"
            "             c.getAttribute('stroke') === '%(sstroke)s' &&\n"
            "             document.querySelector('#dome-svg .satdot.shadow') !== null;\n"
            '    }""", timeout=20000)\n'
            '    # Sunlit returns: the chart dot flips to the inversion of its\n'
            '    # generated shadow look, in step with the dome, mid-sweep.\n'
            '    page.wait_for_function("""() => {\n'
            "      var c = document.querySelector('#pass-chart g.dome-body[data-body=iss] circle');\n"
            "      return c !== null && c.getAttribute('fill') === '%(lfill)s' &&\n"
            "             c.getAttribute('stroke') === '%(lstroke)s' &&\n"
            "             document.querySelector('#dome-svg .satdot') !== null &&\n"
            "             document.querySelector('#dome-svg .satdot.shadow') === null;\n"
            '    }""", timeout=20000)\n'
            "    out = {'errors': errors,\n"
            "           'swept': page.eval_on_selector_all(\n"
            "               '#pass-chart g.dome-body[transform]', 'els => els.length')}\n"
            '    browser.close()\n'
            'print(json.dumps(out))\n'
            % {'port': port, 'sfill': shadow_fill, 'sstroke': shadow_stroke,
               'lfill': lit_fill, 'lstroke': lit_stroke})
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        assert out['swept'] == 1           # still mid-pass at the final sample
        assert served['n'] >= 5            # every phase of the walk was served

    def test_countdown_chips_tick_and_roll_in_a_real_browser(
            self, wxskyfield_comet_almanac, tmp_path):
        """Countdown central, where it actually runs: synthetic
        event instants around the browser's real clock (the chips are
        pure client arithmetic, so the feed can stage any sky).  Pins:
        the sun chip ticks hh:mm:ss from the FEED and ROLLS from sunset
        to sunrise when the feed's event expiry replaces the passed
        instant (the min() flip); the darkness chip ticks from its
        generation-baked data-ts target with NO feed key at all -- a
        countdown needs no feed to count; the shower chip shows a
        days-hours-minutes value under its live label; the pass chip
        shows the staged pass's label and 'appears in'; the windowed
        guests obey their 30-day window (supermoon and one perihelion
        in, eclipse and the other perihelion honestly out); zero page
        errors.  Skips when the playwright env is absent."""
        import http.server
        import json as jsonlib
        import socketserver
        import subprocess
        import threading

        pwenv = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                             'tools', 'pwenv', 'bin', 'python')
        if not os.path.exists(pwenv):
            pytest.skip('the weewx-skyfield tools/pwenv playwright env is not available')

        now = time.time()
        html = self.render(wxskyfield_comet_almanac, sky_page=make_sky_page())
        # Rewire the darkness chip to the STATIC path: its feed key is
        # deliberately absent from the packets below, and its baked
        # data-ts target moves near the browser clock -- the chip must
        # tick from the generation-baked target alone (a countdown
        # needs no feed to count; the feed's job is the roll).
        html, n_subs = re.subn(r'(id="chip-dark" data-ts=")\d+(")',
                               r'\g<1>%d\g<2>' % int(now + 5000), html)
        assert n_subs == 1
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        def packet(i, rolled):
            return jsonlib.dumps({
                'current.dateTime.raw': now + 2 * i,
                # Sunset 4 s out; once it passes, the "feed" rolls
                # next_setting to tomorrow and the min() flips the chip
                # to the sooner sunrise.
                'almanac.sun.next_setting.unix_epoch.raw':
                    (now + 86404) if rolled else (now + 4),
                'almanac.sun.next_rising.unix_epoch.raw': now + 40000,
                'almanac.next_meteor_shower.peak.unix_epoch.raw': now + 3 * 86400,
                'almanac.next_meteor_shower.label': 'Perseids',
                # An equinox/solstice 10 days out: the season chip shows,
                # named by the event's month and hemisphere.
                'almanac.next_equinox.unix_epoch.raw': now + 10 * 86400,
                'almanac.next_solstice.unix_epoch.raw': now + 100 * 86400,
                'almanac.next_supermoon.unix_epoch.raw': now + 10 * 86400,
                # Outside the 30-day window: the chip must stay hidden.
                'almanac.next_eclipse.unix_epoch.raw': now + 40 * 86400,
                'almanac.next_eclipse_kind': 'lunar',
                'almanac.mcnaught.perihelion.unix_epoch.raw': now + 5 * 86400,
                'almanac.mcnaught.label': 'McNaught',
                'almanac.halley.perihelion.unix_epoch.raw': now + 1000 * 86400,
                'almanac.iss.label': 'ISS',
                'almanac.iss.next_visible_pass.rise.unix_epoch.raw': now + 300,
                'almanac.iss.next_visible_pass.set.unix_epoch.raw': now + 900,
            }).encode()
        packets = [packet(0, False), packet(1, False), packet(2, True),
                   packet(3, True)]
        served = {'n': 0}

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body = packets[min(served['n'], len(packets) - 1)]
                    served['n'] += 1
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return super().do_GET()

            def translate_path(self, path):
                return str(tmp_path / path.split('?')[0].lstrip('/'))

            def log_message(self, *a):
                pass

        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        runner = tmp_path / 'runner.py'
        runner.write_text(
            'import json, re\n'
            'from playwright.sync_api import sync_playwright\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    page = browser.new_page()\n'
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            "    page.goto('http://127.0.0.1:%d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    # The first packet lands and the sun chip ticks sunset.\n'
            '    page.wait_for_function("""() => {\n'
            "      var k = document.getElementById('chip-sun-k');\n"
            "      var v = document.getElementById('chip-sun-v');\n"
            "      return k !== null && k.textContent === 'sunset' &&\n"
            "             /^\\\\d{2}:\\\\d{2}:\\\\d{2}$/.test(v.textContent);\n"
            '    }""", timeout=15000)\n'
            '    # The darkness chip is inside its final day, so it ticks\n'
            '    # hh:mm:ss: two samples a second apart must differ (the\n'
            '    # 1 s local tick at work).\n'
            "    v1 = page.inner_text('#chip-dark-v')\n"
            '    page.wait_for_timeout(1500)\n'
            "    v2 = page.inner_text('#chip-dark-v')\n"
            '    # The roll: the feed replaced the passed sunset with\n'
            "    # tomorrow's, and the min() flips the chip to sunrise.\n"
            '    page.wait_for_function("""() => {\n'
            "      var k = document.getElementById('chip-sun-k');\n"
            "      return k !== null && k.textContent === 'sunrise';\n"
            '    }""", timeout=20000)\n'
            '    def hidden(cid):\n'
            "        return page.eval_on_selector('#' + cid,\n"
            "            'el => el.hasAttribute(\"hidden\")')\n"
            '    out = {\n'
            "        'errors': errors,\n"
            "        'v1': v1, 'v2': v2,\n"
            "        'shower_k': page.inner_text('#chip-shower-k'),\n"
            "        'shower_v': page.inner_text('#chip-shower-v'),\n"
            "        'pass_hidden': hidden('chip-pass'),\n"
            "        'pass_k': page.inner_text('#chip-pass-k'),\n"
            "        'pass_d': page.inner_text('#chip-pass-d'),\n"
            "        'pass_v': page.inner_text('#chip-pass-v'),\n"
            "        'sun_d': page.inner_text('#chip-sun-d'),\n"
            "        'dark_hidden': hidden('chip-dark'),\n"
            "        'season_hidden': hidden('chip-season'),\n"
            "        'season_k': page.inner_text('#chip-season-k'),\n"
            "        'super_hidden': hidden('chip-super'),\n"
            "        'eclipse_hidden': hidden('chip-eclipse'),\n"
            "        'peri_mcnaught_hidden': hidden('chip-peri-mcnaught'),\n"
            "        'peri_mcnaught_k': page.inner_text('#chip-peri-mcnaught-k'),\n"
            "        'peri_halley_hidden': hidden('chip-peri-halley'),\n"
            '    }\n'
            '    browser.close()\n'
            'print(json.dumps(out))\n' % port)
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        assert out['v1'] != out['v2']              # the value really ticks
        assert re.match(r'^\d{2}:\d{2}:\d{2}$', out['v1'])
        # Days out, the countdown is days-hours-minutes (seconds are
        # noise at that range); the staged peak is 3 days ahead.
        assert re.match(r'^2d 23h \d{1,2}m$', out['shower_v'])
        assert out['shower_k'] == 'Perseids'       # the live label took over
        assert out['pass_hidden'] is False
        assert out['pass_k'] == 'ISS'
        assert out['pass_d'] == 'appears in'
        assert re.match(r'^\d{2}:\d{2}:\d{2}$', out['pass_v'])
        # The live detail renders EXACTLY the template's %H:%M shape (no
        # locale AM/PM): the first live rewrite must not reformat what
        # the report painted.  After the roll the chip counts to the
        # staged sunrise.
        assert out['sun_d'] == time.strftime('%H:%M',
                                             time.localtime(now + 40000))
        assert out['dark_hidden'] is False
        # The season chip: the staged equinox is 10 days out (in the
        # window), and its label follows the event's month and the
        # station's hemisphere -- computed here exactly as the page
        # computes it.
        assert out['season_hidden'] is False
        season_month = int(time.strftime('%m', time.localtime(now + 10 * 86400)))
        if 2 <= season_month <= 4:
            expected_season = 'spring begins'
        elif 5 <= season_month <= 7:
            expected_season = 'summer begins'
        elif 8 <= season_month <= 10:
            expected_season = 'autumn begins'
        else:
            expected_season = 'winter begins'
        assert out['season_k'] == expected_season
        assert out['super_hidden'] is False        # 10 days: in the window
        assert out['eclipse_hidden'] is True       # 40 days: honestly out
        assert out['peri_mcnaught_hidden'] is False
        assert out['peri_mcnaught_k'] == 'McNaught perihelion'
        assert out['peri_halley_hidden'] is True   # ~3 years: honestly out

    def test_comet_dial_mark_renders_in_a_real_browser(
            self, wxskyfield_comet_almanac, tmp_path):
        """The comet layer on the dial, where it actually runs: packets
        computed by the registered comets-configured almanac.  Pins:
        Halley's diamond is the hollow faint look (mag 25.6), the
        fabricated always-bright comet's is solid; six tail rays drawn,
        the center ray pointing away from the sun's own dial point (the
        anti-sunward anchor); the one-hour trail appears once two packets
        derive rates; the tooltip carries the magnitude; the comets
        absent from the feed (no fields) render absence; and the
        embedded dome's comet groups pass through the live machinery
        untouched -- present, un-nudged, no page errors (must-handle #1's
        live half).  Skips when the playwright env is absent."""
        import http.server
        import json as jsonlib
        import socketserver
        import subprocess
        import threading

        pwenv = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                             'tools', 'pwenv', 'bin', 'python')
        if not os.path.exists(pwenv):
            pytest.skip('the weewx-skyfield tools/pwenv playwright env is not available')

        bodies = ['sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter',
                  'saturn', 'uranus', 'neptune', 'pluto', 'proxima_centauri']
        packets = []
        for ts in (TIME_TS, TIME_TS + 2, TIME_TS + 4):
            alm = weewx.almanac.Almanac(ts, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            r = {'current.dateTime.raw': ts,
                 'almanac.moon.phase': alm.moon.phase,
                 'almanac.next_full_moon.unix_epoch.raw': alm.next_full_moon.raw,
                 'almanac.next_new_moon.unix_epoch.raw': alm.next_new_moon.raw}
            for b in bodies:
                obj = getattr(alm, b)
                r['almanac.%s.az' % b] = obj.az
                r['almanac.%s.alt' % b] = obj.alt
                r['almanac.%s.earth_distance' % b] = obj.earth_distance
            # Two of the four configured comets in the feed (halley
            # honestly faint, the fabricated one bright); hale_bopp and
            # mcnaught stay absent -- their dial marks must not draw.
            for c in ('halley', 'bright'):
                comet = getattr(alm, c)
                r['almanac.%s.az' % c] = comet.az
                r['almanac.%s.alt' % c] = comet.alt
                r['almanac.%s.earth_distance' % c] = comet.earth_distance
                r['almanac.%s.mag' % c] = comet.mag
                r['almanac.%s.label' % c] = str(comet.label)
            packets.append(jsonlib.dumps(r).encode())

        (tmp_path / 'index.html').write_text(
            self.render(wxskyfield_comet_almanac, sky_page=make_sky_page()))
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        served = {'n': 0}

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body = packets[min(served['n'], len(packets) - 1)]
                    served['n'] += 1
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return super().do_GET()

            def translate_path(self, path):
                return str(tmp_path / path.split('?')[0].lstrip('/'))

            def log_message(self, *a):
                pass

        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        runner = tmp_path / 'runner.py'
        runner.write_text(
            'import json\n'
            'from playwright.sync_api import sync_playwright\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    page = browser.new_page()\n'
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            "    page.goto('http://127.0.0.1:%d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    page.wait_for_timeout(5500)\n'
            '    tail_ok = page.evaluate("""() => {\n'
            '      // The visible comet groups: diamond center from the path\n'
            '      // d, center-ray direction vs the (comet - sun) vector.\n'
            "      var sun = document.querySelector('#dial .geodot.fill-sun');\n"
            '      if (sun === null) { return false; }\n'
            "      var sx = parseFloat(sun.getAttribute('cx'));\n"
            "      var sy = parseFloat(sun.getAttribute('cy'));\n"
            '      var ok = 0;\n'
            "      document.querySelectorAll('#dial g.geocomet').forEach(function(g) {\n"
            "        if (g.getAttribute('display') === 'none') { return; }\n"
            "        var d = g.querySelector('path').getAttribute('d');\n"
            "        var m = /M ([\\\\d.-]+),([\\\\d.-]+)/.exec(d);\n"
            '        var cx0 = parseFloat(m[1]), cy0 = parseFloat(m[2]) + 5.0;\n'
            "        var rays = g.querySelectorAll('line.comet-tail');\n"
            "        var r = rays[1];\n"
            "        var vx = parseFloat(r.getAttribute('x2')) - parseFloat(r.getAttribute('x1'));\n"
            "        var vy = parseFloat(r.getAttribute('y2')) - parseFloat(r.getAttribute('y1'));\n"
            '        if (vx * (cx0 - sx) + vy * (cy0 - sy) > 0) { ok += 1; }\n'
            '      });\n'
            '      return ok;\n'
            '    }""")\n'
            '    titles = page.evaluate("""() => {\n'
            '      var out = [];\n'
            "      document.querySelectorAll('#dial g.geocomet title').forEach(function(t) {\n"
            '        out.push(t.textContent);\n'
            '      });\n'
            '      return out;\n'
            '    }""")\n'
            '    out = {\n'
            "        'errors': errors,\n"
            "        'faint': page.eval_on_selector_all(\n"
            "            '#dial path.cometdot.faint', 'els => els.length'),\n"
            "        'solid': page.eval_on_selector_all(\n"
            "            '#dial path.cometdot:not(.faint)', 'els => els.length'),\n"
            "        'shown': page.eval_on_selector_all(\n"
            '            \'#dial g.geocomet:not([display="none"])\', "els => els.length"),\n'
            "        'rays': page.eval_on_selector_all(\n"
            '            \'#dial line.comet-tail:not([display="none"])\', "els => els.length"),\n'
            "        'trails': page.eval_on_selector_all(\n"
            '            \'#dial line.trail.stroke-comet:not([display="none"])\', "els => els.length"),\n'
            "        'tail_ok': tail_ok,\n"
            "        'titles': titles,\n"
            "        'dome_halley': page.eval_on_selector_all(\n"
            '            \'#dome-svg g.dome-body[data-body="halley"]\', "els => els.length"),\n'
            "        'dome_halley_nudged': page.eval_on_selector_all(\n"
            '            \'#dome-svg g.dome-body[data-body="halley"][transform]\', "els => els.length"),\n'
            "        'au_cell': page.inner_text('#geo-au-halley'),\n"
            "        'ghost_au': page.inner_text('#geo-au-mcnaught'),\n"
            '    }\n'
            '    browser.close()\n'
            'print(json.dumps(out))\n' % port)
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        assert out['shown'] == 2               # halley + bright; the absent two hide
        assert out['faint'] == 1               # halley, mag 25.6: hollow
        assert out['solid'] >= 1               # the fabricated naked-eye comet
        assert out['rays'] == 6                # three per drawn comet
        assert out['trails'] == 48             # 24 segments x 2 drawn comets
        assert out['tail_ok'] == 2             # both tails point anti-sunward
        assert any('Halley' in t and 'mag 25.6' in t for t in out['titles'])
        # The embedded dome's comet marks pass through the live machinery
        # untouched: present, never nudged (comets are in no nudge list).
        assert out['dome_halley'] == 1
        assert out['dome_halley_nudged'] == 0
        assert out['au_cell'].endswith(' au')  # the roster cell went live
        # A comet ABSENT from the feed (mcnaught: real elements, no
        # fields) keeps its report-time first paint -- the dual-source
        # doctrine -- while its dial mark stays undrawn (shown == 2).
        assert out['ghost_au'].endswith(' au')

    def test_page_reports_fetch_failure_in_badge(self, wxskyfield_almanac, tmp_path):
        """The 404 case a misconfigured loop_data_file produces (loopdata
        writing outside HTML_ROOT -- say /dev/shm -- with nothing on the
        web server serving it): the poll gets the server's HTML error page,
        and the badge must say so.  Through 7.0 the only trace was a
        JSON.parse error in the console and a silently dead page.  Skips
        when the playwright env is absent."""
        import http.server
        import json as jsonlib
        import socketserver
        import subprocess
        import threading

        pwenv = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                             'tools', 'pwenv', 'bin', 'python')
        if not os.path.exists(pwenv):
            pytest.skip('the weewx-skyfield tools/pwenv playwright env is not available')

        (tmp_path / 'index.html').write_text(self.render(wxskyfield_almanac))
        (tmp_path / 'celestial.css').write_bytes(
            open(os.path.join(SKIN_DIR, 'celestial.css'), 'rb').read())

        # No special-casing of /gauge-data/loop-data.txt: the poll gets the
        # stock HTML 404 page, exactly what a misconfigured server serves.
        class Handler(http.server.SimpleHTTPRequestHandler):
            def translate_path(self, path):
                return str(tmp_path / path.split('?')[0].lstrip('/'))

            def log_message(self, *a):
                pass

        httpd = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        runner = tmp_path / 'runner.py'
        runner.write_text(
            'import json\n'
            'from playwright.sync_api import sync_playwright\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    page = browser.new_page()\n'
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            "    page.goto('http://127.0.0.1:%d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    page.wait_for_timeout(1500)\n'
            "    out = {'errors': errors, 'badge': page.inner_text('#live-label')}\n"
            '    browser.close()\n'
            'print(json.dumps(out))\n' % port)
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        assert 'NO DATA (HTTP 404)' in out['badge']
        assert 'check loop_data_file' in out['badge']

    def test_no_hex_colors_in_cheetah_files(self):
        """Cheetah owns '#': hex color literals in the template or the
        javascript include would be eaten as directives/comments.  All
        colors must come from classes in celestial.css."""
        for name in ('index.html.tmpl', 'realtime_updater.inc'):
            source = open(os.path.join(SKIN_DIR, name)).read()
            assert not re.search(r'#[0-9A-Fa-f]{6}\b', source), name

    def test_template_constants_consistent(self):
        """The template and the javascript include each hardcode the AU
        conversion constants; they must agree with each other and with the
        IAU values.  The AU-per-light-year divisor (Proxima's dial label)
        lives in the include."""
        template = open(os.path.join(SKIN_DIR, 'index.html.tmpl')).read()
        include = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        for source, name in ((template, 'index.html.tmpl'), (include, 'realtime_updater.inc')):
            per_au = {float(m) for m in re.findall(r'\$per_au = ([0-9.e+]+)', source)}
            assert per_au == {9.2955807e7, 1.4959787e8}, name
        assert re.search(r'AU_PER_LY = 63241\.077', include)

    def test_sky_js_and_skytip_in_step_with_skyfield(self):
        """sky.js is COPIED from weewx-skyfield -- that repo is the source
        of truth, celestial re-copies on upgrade and never forks -- and the
        .skytip rule in celestial.css is sky.css's rule verbatim: the same
        cross-repo rule as the lang files' shared vocabulary.  Only the
        provenance header may differ, so the comparison strips comments and
        pins the executable text.  Skips when no weewx-skyfield skin is
        available."""
        candidates = [
            os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                         'skins', 'Skyfield'),
            '/home/weewx/skins/Skyfield',
        ]
        sky_skin = next((d for d in candidates
                         if os.path.exists(os.path.join(d, 'sky.js'))), None)
        if sky_skin is None:
            pytest.skip('the weewx-skyfield sky.js is not available')

        def code(path):
            src = open(path, encoding='utf-8').read()
            src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
            return [line.strip() for line in src.splitlines() if line.strip()]

        assert (code(os.path.join(SKIN_DIR, 'sky.js'))
                == code(os.path.join(sky_skin, 'sky.js')))

        def skytip_rule(path):
            m = re.search(r'\.skytip\{[^}]*\}', open(path, encoding='utf-8').read())
            assert m is not None, path
            return m.group(0)

        assert (skytip_rule(os.path.join(SKIN_DIR, 'celestial.css'))
                == skytip_rule(os.path.join(sky_skin, 'sky.css')))

    def test_renders_with_pyephem_almanac(self):
        """With PyEphem but no weewx-skyfield, the roster first-paints
        complete except the Proxima Centauri row (PyEphem's star catalog
        lacks it) and the footer credits the extended almanac generically.
        Pins the fallback story."""
        ephem = pytest.importorskip('ephem')
        assert ephem  # silence unused-import linting
        with saved_almanacs():
            weewx.almanac.almanacs[:] = [weewx.almanac.PyEphemAlmanacType()]
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            assert alm.hasExtras
            html = self.render(alm)
        assert re.match(r'[\d,]+$', self.cell(html, 'almanac.moon.earth_distance'))
        assert re.match(r'[\d,]+$', self.cell(html, 'almanac.pluto.earth_distance'))
        assert self.cell(html, 'geo-alt-sun').startswith('alt ')
        # Proxima: PyEphem cannot serve it; the guarded cells render empty
        # (the row itself stays, for the javascript).
        assert self.cell(html, 'almanac.proxima_centauri.earth_distance') == ''
        assert self.cell(html, 'geo-au-proxima_centauri') == ''
        assert 'id="geo-row-proxima_centauri"' in html
        # An extended almanac serves the Geocentric (no hint there), but
        # PyEphem cannot draw the dome: exactly one skyhint on the page --
        # the dome panel's install pointer.  The footer must NOT claim
        # Skyfield or the star catalog, and the generic credit's mention of
        # weewx-skyfield stays unlinked -- PyEphem may be the engine
        # serving the page.
        assert html.count('class="skyhint"') == 1
        assert 'live sky dome' in html
        assert 'Hipparcos' not in html
        assert "extended almanac" in html
        assert 'Calculated with <a' not in html

    def test_renders_without_extended_almanac(self):
        """With only the weeutil almanac (no PyEphem, no Skyfield), the page
        must still generate: every roster cell empty for the javascript, an
        install hint in the panel, and the footer credits the built-in
        almanac."""
        with saved_almanacs():
            weewx.almanac.almanacs[:] = [weewx.almanac.WeeutilAlmanacType()]
            plain = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                          formatter=weewx.units.get_default_formatter())
            assert not plain.hasExtras
            # Render without a time_zone Extras key: the include must
            # auto-detect the station machine's zone (/etc/localtime
            # symlink, /etc/timezone fallback).
            html = self.render(plain, with_time_zone=False)
        for body in ('moon', 'sun', 'pluto', 'proxima_centauri'):
            assert self.cell(html, 'almanac.%s.earth_distance' % body) == '', body
            assert self.cell(html, 'geo-alt-%s' % body) == '', body
        # Two install hints: the Geocentric's (no extended almanac at all)
        # and the dome panel's.
        assert html.count('class="skyhint"') == 2
        assert 'https://github.com/chaunceygardiner/weewx-skyfield' in html
        assert "built-in almanac" in html
        assert 'Hipparcos' not in html
        assert 'Calculated with <a' not in html
        auto_tz = ''
        try:
            auto_tz = os.readlink('/etc/localtime').split('zoneinfo/')[-1]
        except OSError:
            try:
                auto_tz = open('/etc/timezone').read().strip()
            except OSError:
                pass
        assert "time_zone = '%s'" % auto_tz in html


class TestI18n:
    """The page's translation plumbing (7.2) -- the same machinery
    weewx-skyfield 1.12/1.13 ships: [Texts] is gettext-style (the English
    string IS the key; a report falls back to it one string at a time),
    body names ride the report's [Almanac] section (the same source as
    $almanac.<body>.label -- every almanac tier has .texts), compass
    cardinals the formatter's [Units] [[Ordinates]] directions, hemisphere
    letters [Labels] hemispheres.  The live javascript composes strings
    too, so the template feeds it the translated values (BODY_LABELS,
    CARDINALS, T) through json.dumps."""

    LANG_DIR = os.path.join(SKIN_DIR, 'lang')
    BODIES = ['sun', 'moon', 'mercury', 'venus', 'earth', 'mars', 'jupiter',
              'saturn', 'uranus', 'neptune', 'pluto', 'proxima_centauri']

    # [Texts] keys that render INSIDE the embedded dome: wxskyfield_sky's
    # SkyPage translates its own strings through the report's skin_dict,
    # which in production carries THIS skin's lang file -- so these are
    # part of the page's dictionary even though no $gettext literal in our
    # sources names them.  test_dome_text_keys_in_step pins the list
    # against the sibling wxskyfield_sky.py source.
    DOME_TEXT_KEYS = {
        'Sky dome chart',
        '{name} — alt {alt}°, az {az}°, mag {mag}',
        '{name} — alt {alt}°, az {az}°',
        '{name} — alt {alt}°, az {az}° — in shadow',
        '{name} — alt {alt}°, az {az}°, {pct}% illuminated',
        '{name} pass — {rise} → {set}, peak {alt}°',
        # The pass chart's own strings (the same SkyPage renders it).
        'Pass sky chart',
        '{date} · {rise} → {set} · peak {alt}°',
        '%a %b %-d',
        # The 2.1 dome's radiant marks (drawn while a shower is active;
        # the comet marks reuse the mag tooltip above).
        '{name} radiant — ZHR {zhr}, peak {date}',
    }

    @staticmethod
    def lang_conf(dirname, name):
        configobj = pytest.importorskip('configobj')
        return configobj.ConfigObj(os.path.join(dirname, name),
                                   encoding='utf-8', file_error=True)

    @classmethod
    def rendered_keys(cls):
        """Every translation key the page can render: the
        $gettext("...")/$gettext('...') literals in the template and the
        include (keys are single-line literals by convention), plus the
        embedded dome's own strings (DOME_TEXT_KEYS)."""
        keys = set()
        for name in ('index.html.tmpl', 'realtime_updater.inc'):
            with open(os.path.join(SKIN_DIR, name), encoding='utf-8') as f:
                found = re.findall(r'\$gettext\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)',
                                   f.read())
            assert found, name
            keys |= {a or b for a, b in found}
        return keys | cls.DOME_TEXT_KEYS

    def test_dome_text_keys_in_step(self):
        """DOME_TEXT_KEYS must be strings wxskyfield_sky's source really
        renders (self._t('...') literals): a key that drifts from the
        sibling would ship a translation nothing looks up.  Skips when no
        weewx-skyfield source is available."""
        for d in WXSKYFIELD_DIRS:
            path = os.path.join(d, 'wxskyfield_sky.py')
            if os.path.exists(path):
                break
        else:
            pytest.skip('the weewx-skyfield source is not available')
        src = open(path, encoding='utf-8').read()
        served = (set(re.findall(r"self\._t\('([^']+)'", src))
                  | set(re.findall(r'self\._t\("([^"]+)"', src)))
        assert sorted(self.DOME_TEXT_KEYS - served) == []

    def test_en_conf_ships_exactly_what_renders(self):
        """Both directions: a rendered key missing from lang/en.conf fails,
        and an en.conf key nothing renders fails -- the English file is the
        reference dictionary for translators, and it must grow and shrink
        with the features that render it."""
        conf = self.lang_conf(self.LANG_DIR, 'en.conf')
        shipped = dict(conf['Texts'])
        rendered = self.rendered_keys()
        assert sorted(rendered - set(shipped)) == [], 'rendered but not in en.conf'
        assert sorted(set(shipped) - rendered) == [], 'in en.conf but never rendered'
        # English is the identity translation: every value equals its key
        # (so the file doubles as the untranslated reference).
        assert [k for k, v in shipped.items() if v != k] == []
        # Every English format string must itself format cleanly: the
        # javascript's fmt and the template fall back to it.
        for k in rendered:
            k.format(**{name: 'x' for name in set(re.findall(r'\{(\w+)\}', k))})

    def test_en_conf_core_sections(self):
        """The lang file is self-contained: the core-standard sections the
        page reads (hemispheres, ordinates, moon phases), a display name
        for every body the page draws, and the full constellation set for
        reports and loopdata targets in this language."""
        conf = self.lang_conf(self.LANG_DIR, 'en.conf')
        assert list(conf['Labels']['hemispheres']) == ['N', 'S', 'E', 'W']
        assert len(conf['Units']['Ordinates']['directions']) == 17
        assert len(conf['Almanac']['moon_phases']) == 8
        for body in self.BODIES:
            expected = ('Proxima Centauri' if body == 'proxima_centauri'
                        else body.title())
            assert conf['Almanac'][body] == expected
        # Satellite display names ride the same channel (the loopdata
        # target report's [Almanac] evaluates almanac.<sat>.label): the
        # well-known tags must not fall back to title-case ('Iss').
        assert conf['Almanac']['iss'] == 'ISS'
        assert conf['Almanac']['tiangong'] == 'Tiangong'
        assert conf['Almanac']['hst'] == 'HST'
        # Comet display names ride the same channel (8.1): the installer
        # defaults must not fall back to title-case ('Hale_Bopp').
        assert conf['Almanac']['halley'] == 'Halley'
        assert conf['Almanac']['hale_bopp'] == 'Hale-Bopp'
        # The twelve IMO majors, for almanac.next_meteor_shower.label and
        # the shower chip.
        assert len(conf['Almanac']['MeteorShowers']) == 12
        assert conf['Almanac']['MeteorShowers']['perseids'] == 'Perseids'
        assert len(conf['Almanac']['Constellations']) == 88

    def test_shipped_lang_files_are_consistent(self):
        """Every shipped lang file must parse, translate only keys en.conf
        ships (a stale key would silently never render), keep each value's
        placeholders exactly its key's set (a renamed one knocks the string
        back to English at run time), and carry the core sections."""
        rendered = self.rendered_keys()
        abbrs = set(self.lang_conf(self.LANG_DIR, 'en.conf')['Almanac']['Constellations'])
        names = sorted(os.listdir(self.LANG_DIR))
        assert 'en.conf' in names and 'de.conf' in names
        for name in names:
            conf = self.lang_conf(self.LANG_DIR, name)
            for key, val in dict(conf['Texts']).items():
                assert key in rendered, (name, key)
                assert isinstance(val, str), (name, key)
                assert (set(re.findall(r'\{(\w+)\}', val))
                        == set(re.findall(r'\{(\w+)\}', key))), (name, key)
            assert len(conf['Labels']['hemispheres']) == 4, name
            assert len(conf['Units']['Ordinates']['directions']) == 17, name
            assert len(conf['Almanac']['moon_phases']) == 8, name
            for body in self.BODIES:
                assert conf['Almanac'][body], (name, body)
            # Constellation keys are the IAU abbreviations; a key outside
            # the set would silently never be looked up.
            assert set(conf['Almanac']['Constellations']) == abbrs, name

    def test_de_conf_is_complete(self):
        """German is a full translation: every rendered key is covered, so
        a new feature's strings fail here until de.conf learns them."""
        conf = self.lang_conf(self.LANG_DIR, 'de.conf')
        assert sorted(self.rendered_keys() - set(conf['Texts'])) == []

    def test_fr_conf_is_complete(self):
        """French likewise ships complete."""
        conf = self.lang_conf(self.LANG_DIR, 'fr.conf')
        assert sorted(self.rendered_keys() - set(conf['Texts'])) == []

    def test_nl_conf_is_complete(self):
        """Dutch likewise ships complete."""
        conf = self.lang_conf(self.LANG_DIR, 'nl.conf')
        assert sorted(self.rendered_keys() - set(conf['Texts'])) == []

    def test_es_conf_is_complete(self):
        """Spanish likewise ships complete."""
        conf = self.lang_conf(self.LANG_DIR, 'es.conf')
        assert sorted(self.rendered_keys() - set(conf['Texts'])) == []

    def test_da_conf_is_complete(self):
        """Danish likewise ships complete."""
        conf = self.lang_conf(self.LANG_DIR, 'da.conf')
        assert sorted(self.rendered_keys() - set(conf['Texts'])) == []

    def test_it_conf_is_complete(self):
        """Italian likewise ships complete."""
        conf = self.lang_conf(self.LANG_DIR, 'it.conf')
        assert sorted(self.rendered_keys() - set(conf['Texts'])) == []

    def test_no_conf_is_complete(self):
        """Norwegian likewise ships complete."""
        conf = self.lang_conf(self.LANG_DIR, 'no.conf')
        assert sorted(self.rendered_keys() - set(conf['Texts'])) == []

    def test_sv_conf_is_complete(self):
        """Swedish likewise ships complete."""
        conf = self.lang_conf(self.LANG_DIR, 'sv.conf')
        assert sorted(self.rendered_keys() - set(conf['Texts'])) == []

    def test_lang_files_in_step_with_skyfield(self):
        """The shared vocabulary is copied verbatim from weewx-skyfield's
        lang files (German and French native-speaker reviewed; Danish
        contributed by a native speaker; Dutch, Spanish, Italian,
        Norwegian and Swedish Beta): body names, moon phases,
        hemispheres, ordinates, all 88 constellation names, and every
        [Texts] key both pages render -- the same cross-repo rule as
        celestial.css staying in step with sky.css.
        Skips when no weewx-skyfield lang directory is available."""
        candidates = [
            os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                         'skins', 'Skyfield', 'lang'),
            '/home/weewx/skins/Skyfield/lang',
        ]
        sky_lang = next((d for d in candidates
                         if os.path.exists(os.path.join(d, 'de.conf'))), None)
        if sky_lang is None:
            pytest.skip('the weewx-skyfield lang directory is not available')
        for name in ('en.conf', 'de.conf', 'fr.conf', 'nl.conf', 'es.conf',
                     'da.conf', 'it.conf', 'no.conf', 'sv.conf'):
            if not os.path.exists(os.path.join(sky_lang, name)):
                # An installed skyfield older than the sibling checkout may
                # not ship this language yet; the sibling checkout does.
                continue
            sky = self.lang_conf(sky_lang, name)
            cel = self.lang_conf(self.LANG_DIR, name)
            assert (dict(cel['Almanac']['Constellations'])
                    == dict(sky['Almanac']['Constellations'])), name
            for body in ['sun', 'moon', 'earth', 'mercury', 'venus', 'mars',
                         'jupiter', 'saturn', 'uranus', 'neptune']:
                assert cel['Almanac'][body] == sky['Almanac'][body], (name, body)
            for sat in ['iss', 'tiangong', 'hst']:
                # Pre-2.0 skyfield lang files ship no satellite names.
                if sat in sky['Almanac']:
                    assert cel['Almanac'][sat] == sky['Almanac'][sat], (name, sat)
            for comet in ['halley', 'hale_bopp']:
                # Pre-2.1 skyfield lang files ship no comet names.
                if comet in sky['Almanac']:
                    assert cel['Almanac'][comet] == sky['Almanac'][comet], (name, comet)
            if 'MeteorShowers' in sky['Almanac']:
                assert (dict(cel['Almanac']['MeteorShowers'])
                        == dict(sky['Almanac']['MeteorShowers'])), name
            assert (list(cel['Almanac']['moon_phases'])
                    == list(sky['Almanac']['moon_phases'])), name
            assert (list(cel['Labels']['hemispheres'])
                    == list(sky['Labels']['hemispheres'])), name
            assert (list(cel['Units']['Ordinates']['directions'])
                    == list(sky['Units']['Ordinates']['directions'])), name
            for key in set(cel['Texts']) & set(sky['Texts']):
                assert cel['Texts'][key] == sky['Texts'][key], (name, key)

    def test_shipped_german_renders(self, wxskyfield_sky):
        """The shipped de.conf, fed through the same channels the report
        engine uses (gettext from [Texts], almanac texts from [Almanac],
        formatter ordinates, [Labels] hemispheres), renders a German page
        -- the template's static strings and the json feeds the javascript
        composes from alike."""
        mod, _ = load_wxskyfield()
        conf = self.lang_conf(self.LANG_DIR, 'de.conf')
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sky)
            alm = weewx.almanac.Almanac(
                TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                formatter=weewx.units.Formatter(
                    ordinate_names=list(conf['Units']['Ordinates']['directions'])),
                texts=dict(conf['Almanac']))
            html = TestSampleSkinRenders.render(
                alm, lang='de', texts=dict(conf['Texts']),
                labels={'hemispheres': list(conf['Labels']['hemispheres'])})
        assert '<html lang="de">' in html
        assert 'Die geozentrische Ansicht' in html
        # The roster first-paints German: the sun is up at the solstice
        # noon, and the distance cells carry the German au unit.
        assert 'Höhe ' in html
        assert ' AE<' in html
        # The javascript feeds: German body names and cardinals (json,
        # non-ASCII \u-escaped), and the composed-string dictionary.
        assert '"moon": "Mond"' in html
        assert '"neptune": "Neptun"' in html
        assert '["N", "O", "S", "W"]' in html
        assert '"below horizon": "unter dem Horizont"' in html
        assert '"approaching": "n\\u00e4hert sich"' in html
        # The footer carries the full German Skyfield credit, naming
        # weewx-skyfield with the project link (ours truly serves this
        # render; the substitution survives translation).
        assert 'Berechnet mit %s: Skyfield' % LINKED_NAME in html

    def test_shipped_french_renders(self, wxskyfield_sky):
        """The shipped fr.conf, fed through the same channels the report
        engine uses, renders a French page -- the template's static strings
        and the json feeds the javascript composes from alike."""
        mod, _ = load_wxskyfield()
        conf = self.lang_conf(self.LANG_DIR, 'fr.conf')
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sky)
            alm = weewx.almanac.Almanac(
                TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                formatter=weewx.units.Formatter(
                    ordinate_names=list(conf['Units']['Ordinates']['directions'])),
                texts=dict(conf['Almanac']))
            html = TestSampleSkinRenders.render(
                alm, lang='fr', texts=dict(conf['Texts']),
                labels={'hemispheres': list(conf['Labels']['hemispheres'])})
        assert '<html lang="fr">' in html
        assert 'La vue géocentrique' in html
        # The roster first-paints French: the sun is up at the solstice
        # noon, and the distance cells carry the French au unit.
        assert 'hauteur ' in html
        assert ' ua<' in html
        # The javascript feeds: French body names and cardinals (json),
        # and the composed-string dictionary.
        assert '"moon": "Lune"' in html
        assert '"mercury": "Mercure"' in html
        assert '["N", "E", "S", "O"]' in html
        assert '"below horizon": "sous l\'horizon"' in html
        assert '"approaching": "se rapproche"' in html
        # The footer carries the full French Skyfield credit, naming
        # weewx-skyfield with the project link.
        assert 'Calculé avec %s : Skyfield' % LINKED_NAME in html

    def test_shipped_dutch_renders(self, wxskyfield_sky):
        """The shipped nl.conf, fed through the same channels the report
        engine uses, renders a Dutch page -- the template's static strings
        and the json feeds the javascript composes from alike."""
        mod, _ = load_wxskyfield()
        conf = self.lang_conf(self.LANG_DIR, 'nl.conf')
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sky)
            alm = weewx.almanac.Almanac(
                TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                formatter=weewx.units.Formatter(
                    ordinate_names=list(conf['Units']['Ordinates']['directions'])),
                texts=dict(conf['Almanac']))
            html = TestSampleSkinRenders.render(
                alm, lang='nl', texts=dict(conf['Texts']),
                labels={'hemispheres': list(conf['Labels']['hemispheres'])})
        assert '<html lang="nl">' in html
        assert 'De geocentrische weergave' in html
        # The roster first-paints Dutch: the sun is up at the solstice
        # noon, and the distance cells carry the Dutch au unit.
        assert 'hoogte ' in html
        assert ' AE<' in html
        # The javascript feeds: Dutch body names and cardinals (json),
        # and the composed-string dictionary.  Dutch east is O and south
        # is Z, so the cardinal ring proves the ordinates flowed through.
        assert '"moon": "Maan"' in html
        assert '"mercury": "Mercurius"' in html
        assert '["N", "O", "Z", "W"]' in html
        assert '"below horizon": "onder de horizon"' in html
        assert '"approaching": "nadert"' in html
        # The footer carries the full Dutch Skyfield credit, naming
        # weewx-skyfield with the project link.
        assert 'Berekend met %s: Skyfield' % LINKED_NAME in html

    def test_shipped_spanish_renders(self, wxskyfield_sky):
        """The shipped es.conf, fed through the same channels the report
        engine uses, renders a Spanish page -- the template's static strings
        and the json feeds the javascript composes from alike."""
        mod, _ = load_wxskyfield()
        conf = self.lang_conf(self.LANG_DIR, 'es.conf')
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sky)
            alm = weewx.almanac.Almanac(
                TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                formatter=weewx.units.Formatter(
                    ordinate_names=list(conf['Units']['Ordinates']['directions'])),
                texts=dict(conf['Almanac']))
            html = TestSampleSkinRenders.render(
                alm, lang='es', texts=dict(conf['Texts']),
                labels={'hemispheres': list(conf['Labels']['hemispheres'])})
        assert '<html lang="es">' in html
        assert 'La vista geocéntrica' in html
        # The roster first-paints Spanish: the sun is up at the solstice
        # noon, and the distance cells carry the Spanish au unit.
        assert 'altura ' in html
        assert ' ua<' in html
        # The javascript feeds: Spanish body names and cardinals (json),
        # and the composed-string dictionary.  Spanish west is O, so the
        # cardinal ring proves the ordinates flowed through.
        assert '"moon": "Luna"' in html
        assert '"mercury": "Mercurio"' in html
        assert '["N", "E", "S", "O"]' in html
        assert '"below horizon": "bajo el horizonte"' in html
        assert '"approaching": "se acerca"' in html
        # The footer carries the full Spanish Skyfield credit, naming
        # weewx-skyfield with the project link.
        assert 'Calculado con %s: Skyfield' % LINKED_NAME in html

    def test_shipped_italian_renders(self, wxskyfield_sky):
        """The shipped it.conf, fed through the same channels the report
        engine uses, renders an Italian page -- the template's static
        strings and the json feeds the javascript composes from alike."""
        mod, _ = load_wxskyfield()
        conf = self.lang_conf(self.LANG_DIR, 'it.conf')
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sky)
            alm = weewx.almanac.Almanac(
                TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                formatter=weewx.units.Formatter(
                    ordinate_names=list(conf['Units']['Ordinates']['directions'])),
                texts=dict(conf['Almanac']))
            html = TestSampleSkinRenders.render(
                alm, lang='it', texts=dict(conf['Texts']),
                labels={'hemispheres': list(conf['Labels']['hemispheres'])})
        assert '<html lang="it">' in html
        assert 'La vista geocentrica' in html
        # The roster first-paints Italian: the sun is up at the solstice
        # noon, and the distance cells carry the Italian au unit.
        assert 'altezza ' in html
        assert ' ua<' in html
        # The javascript feeds: Italian body names and cardinals (json),
        # and the composed-string dictionary.  Italian west is O, so the
        # cardinal ring proves the ordinates flowed through.
        assert '"moon": "Luna"' in html
        assert '"jupiter": "Giove"' in html
        assert '["N", "E", "S", "O"]' in html
        assert '"below horizon": "sotto l\'orizzonte"' in html
        assert '"approaching": "si avvicina"' in html
        # The footer carries the full Italian Skyfield credit, naming
        # weewx-skyfield with the project link.
        assert 'Calcolato con %s: Skyfield' % LINKED_NAME in html

    def test_shipped_norwegian_renders(self, wxskyfield_sky):
        """The shipped no.conf, fed through the same channels the report
        engine uses, renders a Norwegian page -- the template's static
        strings and the json feeds the javascript composes from alike."""
        mod, _ = load_wxskyfield()
        conf = self.lang_conf(self.LANG_DIR, 'no.conf')
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sky)
            alm = weewx.almanac.Almanac(
                TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                formatter=weewx.units.Formatter(
                    ordinate_names=list(conf['Units']['Ordinates']['directions'])),
                texts=dict(conf['Almanac']))
            html = TestSampleSkinRenders.render(
                alm, lang='no', texts=dict(conf['Texts']),
                labels={'hemispheres': list(conf['Labels']['hemispheres'])})
        assert '<html lang="no">' in html
        assert 'Den geosentriske visningen' in html
        # The roster first-paints Norwegian: the sun is up at the solstice
        # noon, and the distance cells carry the Norwegian au unit.
        assert 'høyde ' in html
        assert ' AE<' in html
        # The javascript feeds: Norwegian body names and cardinals (json,
        # non-ASCII \u-escaped: east is Ø), and the composed-string
        # dictionary.
        assert '"moon": "M\\u00e5nen"' in html
        assert '"mercury": "Merkur"' in html
        assert '["N", "\\u00d8", "S", "V"]' in html
        assert '"below horizon": "under horisonten"' in html
        assert '"approaching": "n\\u00e6rmer seg"' in html
        # The footer carries the full Norwegian Skyfield credit, naming
        # weewx-skyfield with the project link.
        assert 'Beregnet med %s: Skyfield' % LINKED_NAME in html

    def test_shipped_swedish_renders(self, wxskyfield_sky):
        """The shipped sv.conf, fed through the same channels the report
        engine uses, renders a Swedish page -- the template's static
        strings and the json feeds the javascript composes from alike."""
        mod, _ = load_wxskyfield()
        conf = self.lang_conf(self.LANG_DIR, 'sv.conf')
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sky)
            alm = weewx.almanac.Almanac(
                TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                formatter=weewx.units.Formatter(
                    ordinate_names=list(conf['Units']['Ordinates']['directions'])),
                texts=dict(conf['Almanac']))
            html = TestSampleSkinRenders.render(
                alm, lang='sv', texts=dict(conf['Texts']),
                labels={'hemispheres': list(conf['Labels']['hemispheres'])})
        assert '<html lang="sv">' in html
        assert 'Den geocentriska vyn' in html
        # The roster first-paints Swedish: the sun is up at the solstice
        # noon, and the distance cells carry the Swedish au unit.
        assert 'höjd ' in html
        assert ' AE<' in html
        # The javascript feeds: Swedish body names and cardinals (json),
        # and the composed-string dictionary.  Swedish compass east is O
        # (the coordinates' Ö lives in the hemisphere letters), so the
        # cardinal ring proves the ordinates flowed through.
        assert '"moon": "M\\u00e5nen"' in html
        assert '"mercury": "Merkurius"' in html
        assert '["N", "O", "S", "V"]' in html
        assert '"below horizon": "under horisonten"' in html
        assert '"approaching": "n\\u00e4rmar sig"' in html
        # The footer carries the full Swedish Skyfield credit, naming
        # weewx-skyfield with the project link.
        assert 'Beräknat med %s: Skyfield' % LINKED_NAME in html


class TestMigrateLoopdataFields:
    """The --migrate-loopdata-fields utility: rewrites celestial loop-field
    entries (including pre-3.0 PascalCase names) to weewx-loopdata almanac
    entries in place, drops moonWaxing and the duplicates the rewrites
    create, appends the current sample-report fields (satellite entries
    following the configuration's [Skyfield] [[Satellites]], the installer
    defaults only when there is no [[Satellites]] to follow), and touches
    nothing else."""

    def test_camel_names_map_to_almanac(self):
        fields = ['current.outTemp', 'current.sunrise.raw', 'current.sunset',
                  'current.civilTwilightStart.raw', 'current.tomorrowSunrise.raw',
                  'current.yesterdayDaylightDur.raw', 'current.sunTransit.raw',
                  'day.rain.sum']
        new, report = celestial.migrate_loopdata_fields(fields)
        # Rewrites happen in place, order preserved, renditions honored.
        # Raw times and durations arrive with pinned units (.unix_epoch,
        # .second): the old loop fields' fixed meanings survive any [Units]
        # [[Groups]] overrides on loopdata's target report.
        assert new[:8] == ['current.outTemp', 'almanac.sunrise.unix_epoch.raw', 'almanac.sunset',
                           'almanac(horizon=-6).sun(use_center=1).rise.unix_epoch.raw',
                           'almanac(days=1).sunrise.unix_epoch.raw',
                           'almanac(days=-1).sun.visible.second.raw',
                           'almanac.sun.transit.unix_epoch.raw', 'day.rain.sum']
        assert ('current.sunrise.raw', 'almanac.sunrise.unix_epoch.raw') in report['renamed']

    def test_pascal_names_chain_through(self):
        """Pre-3.0 PascalCase entries collapse to camelCase first, then map
        to almanac entries -- one pass migrates even a 2.x fields line."""
        fields = ['current.Sunrise.raw', 'current.EarthMoonDistance',
                  'current.daySunshineDur.raw']
        new, report = celestial.migrate_loopdata_fields(fields)
        assert new[:3] == ['almanac.sunrise.unix_epoch.raw', 'almanac.moon.earth_distance',
                           'almanac.sun.visible.second.raw']

    def test_angle_renditions(self):
        """.raw angles become the plain-degree tags; formatted angles become
        the ValueHelper tags."""
        fields = ['current.sunAzimuth.raw', 'current.sunAzimuth',
                  'current.moonDeclination.raw', 'current.marsAltitude.raw']
        new, _ = celestial.migrate_loopdata_fields(fields)
        assert new[:4] == ['almanac.sun.az', 'almanac.sun.azimuth',
                           'almanac.moon.dec', 'almanac.mars.alt']

    def test_pre_76_moon_keys_upgrade_to_pinned(self):
        """A fields line migrated under <= 7.5 carries the moon-phase keys
        unpinned; a re-run upgrades them to the pinned spellings the 7.6
        sample page reads, and a second run is a no-op."""
        fields = ['almanac.next_full_moon.raw', 'almanac.next_new_moon.raw',
                  'current.outTemp']
        new, report = celestial.migrate_loopdata_fields(fields)
        assert 'almanac.next_full_moon.unix_epoch.raw' in new
        assert 'almanac.next_new_moon.unix_epoch.raw' in new
        assert not any(f.endswith('_moon.raw') for f in new)
        assert ('almanac.next_full_moon.raw',
                'almanac.next_full_moon.unix_epoch.raw') in report['renamed']
        twice, report2 = celestial.migrate_loopdata_fields(new)
        assert twice == new and report2['renamed'] == []

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

    def test_migrated_line_stays_comma_free(self):
        """Every appended entry is single-kwarg (no commas), so the
        [LoopData] [[Include]] fields value stays a bare comma-separated
        list."""
        for field in celestial._MIGRATION_NEW_FIELDS:
            assert ',' not in field, field

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

    def test_satellite_fields_evaluate_in_loopdata(self, wxskyfield_sat_sky):
        """The whole pipeline the satellite layer depends on: every
        satellite entry in _MIGRATION_NEW_FIELDS EVALUATES through the
        sibling weewx-loopdata's own evaluator (parse, chain walk, format
        spec, json coercion -- evaluate/to_json_value touch no instance
        state, so they are called unbound) against a satellites-configured
        skyfield 2.0 almanac, reproducing the fixture pins.  A second act
        pins STALENESS (loopdata 6.9): driven through a real evaluator's
        packet path, a next_pass group expires at the pass's own set
        instant, not at midnight -- the page's "just set" branch is
        visible only between a set and the next loop packet, as its
        comment in realtime_updater.inc always claimed."""
        loopdata = load_loopdata()
        mod, _ = load_wxskyfield()
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sat_sky)
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE,
                                        altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            values = {}
            for entry in celestial._MIGRATION_NEW_FIELDS:
                if not entry.startswith(('almanac.iss.', 'almanac.tiangong.')):
                    continue
                af = loopdata.LoopData.parse_almanac_field(entry)
                assert af is not None, entry
                obj = loopdata.AlmanacFieldEvaluator.evaluate(None, af, alm, TIME_TS)
                values[entry] = loopdata.AlmanacFieldEvaluator.to_json_value(
                    None, af, obj)
        # The ISS at the fixture noon (below the horizon), and its next
        # visible pass -- the skyfield test suite's regression values.
        assert abs(values['almanac.iss.alt'] - (-17.7318)) < 0.01
        assert abs(values['almanac.iss.az'] - 309.1526) < 0.01
        assert values['almanac.iss.sunlit'] in (True, False)
        assert values['almanac.iss.label'] == 'Iss'
        rise = values['almanac.iss.next_visible_pass.rise.unix_epoch.raw']
        assert abs(rise - 1750587085.008) < 1.0
        assert values['almanac.iss.next_visible_pass.set.unix_epoch.raw'] > rise
        assert abs(values['almanac.iss.next_visible_pass.max_altitude.degree_angle.raw']
                   - 19.3) < 0.1
        assert abs(values['almanac.iss.next_visible_pass.duration.second.raw'] / 60.0
                   - 10) < 1.0
        assert values['almanac.iss.next_visible_pass.rise_azimuth.ordinal_compass'] == 'SSW'
        assert values['almanac.iss.next_visible_pass.culmination_azimuth.ordinal_compass'] == 'SE'
        assert values['almanac.iss.next_visible_pass.set_azimuth.ordinal_compass'] == 'ENE'
        # Tiangong: usable elements, but no visible pass in the window --
        # the pass fields are honestly None (the page's no-pass row).
        assert values['almanac.tiangong.sunlit'] in (True, False)
        assert values['almanac.tiangong.next_visible_pass.rise.unix_epoch.raw'] is None

        # Act two, the staleness pin: the fields of one pass form a group
        # that loopdata caches and expires as a unit at the pass's set.
        pin_fields = [
            'almanac.iss.next_pass.rise.unix_epoch.raw',
            'almanac.iss.next_pass.set.unix_epoch.raw',
            'almanac.iss.next_pass.duration.second.raw',
            'almanac.iss.next_pass.max_altitude.degree_angle.raw',
            'almanac.iss.next_pass.visible',
        ]
        # The evaluator reads its Configuration by attribute, so a
        # namespace with the seven attributes it touches serves.
        cfg = types.SimpleNamespace(
            almanac_fields=loopdata.LoopData.get_almanac_fields(pin_fields),
            latitude=LATITUDE, longitude=LONGITUDE, altitude_m=ALTITUDE_M,
            almanac_texts={}, formatter=weewx.units.get_default_formatter(),
            converter=weewx.units.Converter())
        assert len(cfg.almanac_fields) == len(pin_fields)
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sat_sky)
            evaluator = loopdata.AlmanacFieldEvaluator(cfg)
            # All five fields name the same pass: one group.
            assert len(evaluator.groups) == 1

            def loop_packet(ts):
                pkt = {}
                evaluator.insert_fields(pkt, {'dateTime': ts, 'usUnits': weewx.METRIC})
                return pkt

            first = loop_packet(TIME_TS)
            rise1 = first['almanac.iss.next_pass.rise.unix_epoch.raw']
            set1 = first['almanac.iss.next_pass.set.unix_epoch.raw']
            assert TIME_TS < rise1 < set1

            # Mid-pass: rise is behind us, but the group's expiry is set,
            # so the cached in-progress pass keeps serving ("overhead now").
            mid = loop_packet(int((rise1 + set1) // 2))
            assert mid['almanac.iss.next_pass.rise.unix_epoch.raw'] == rise1
            assert mid['almanac.iss.next_pass.set.unix_epoch.raw'] == set1

            # The first packet after set: the pass has ended, the group has
            # expired, and the recompute serves the FOLLOWING pass -- every
            # leaf from the same computation, pinned by duration matching
            # the new rise/set (a torn group would carry the old pass's).
            after = loop_packet(int(set1) + 1)
            rise2 = after['almanac.iss.next_pass.rise.unix_epoch.raw']
            set2 = after['almanac.iss.next_pass.set.unix_epoch.raw']
            assert rise2 > set1
            assert set2 > rise2
            assert abs(after['almanac.iss.next_pass.duration.second.raw']
                       - (set2 - rise2)) < 1.0
            assert after['almanac.iss.next_pass.visible'] in (True, False)

            # Re-armed: the following pass now serves from cache.
            again = loop_packet(int(set1) + 3)
            assert again['almanac.iss.next_pass.rise.unix_epoch.raw'] == rise2
            assert again['almanac.iss.next_pass.set.unix_epoch.raw'] == set2

    def test_comet_fields_evaluate_in_loopdata(self, wxskyfield_comet_sky):
        """Every comet entry in _MIGRATION_NEW_FIELDS (and the mcnaught
        substitution) evaluates through the sibling weewx-loopdata's own
        evaluator against a comets-configured skyfield 2.1 almanac,
        reproducing the skyfield fixture pins.  Halley is honestly faint
        (mag 25.6 -- the page's hollow diamond) and 35.9 AU out; the
        perihelion instants are raw TT-derived epochs that can lie far
        past (Hale-Bopp 1997) or future (Halley 2061)."""
        loopdata = load_loopdata()
        mod, _ = load_wxskyfield()
        entries = []
        for tag in ('halley', 'mcnaught', 'hale_bopp'):
            entries.extend(celestial.comet_fields(tag))
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_comet_sky)
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE,
                                        altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            values = {}
            for entry in entries:
                af = loopdata.LoopData.parse_almanac_field(entry)
                assert af is not None, entry
                obj = loopdata.AlmanacFieldEvaluator.evaluate(None, af, alm, TIME_TS)
                values[entry] = loopdata.AlmanacFieldEvaluator.to_json_value(
                    None, af, obj)
        assert abs(values['almanac.halley.az'] - 113.786) < 0.01
        assert abs(values['almanac.halley.alt'] - 32.829) < 0.01
        assert abs(values['almanac.halley.earth_distance'] - 35.9066) < 0.001
        assert abs(values['almanac.halley.mag'] - 25.64) < 0.01
        assert values['almanac.halley.label'] == 'Halley'
        assert abs(values['almanac.halley.perihelion.unix_epoch.raw']
                   - 2890316269) < 120
        assert abs(values['almanac.mcnaught.perihelion.unix_epoch.raw']
                   - 1781405334) < 120
        assert abs(values['almanac.hale_bopp.perihelion.unix_epoch.raw']
                   - 859596458) < 120

    def test_countdown_fields_evaluate_in_loopdata(self, wxskyfield_comet_sky):
        """The nine countdown base entries evaluate through the sibling
        weewx-loopdata against the skyfield 2.1 almanac: the sun pair is
        always ahead (next_* semantics), astronomical darkness falls
        after sunset, the shower peak/label pair is consistent (Southern
        Delta Aquariids from the June fixture), and the supermoon and
        eclipse instants reproduce skyfield's own pins."""
        loopdata = load_loopdata()
        mod, _ = load_wxskyfield()
        entries = [f for f in celestial._MIGRATION_NEW_FIELDS
                   if ('.next_setting.' in f or '.next_rising.' in f
                       or f.startswith(('almanac.next_equinox.',
                                        'almanac.next_solstice.',
                                        'almanac.next_perihelion.',
                                        'almanac.next_aphelion.',
                                        'almanac.next_meteor_shower.',
                                        'almanac.next_supermoon.',
                                        'almanac.next_eclipse')))]
        assert len(entries) == 13
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_comet_sky)
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE,
                                        altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            values = {}
            for entry in entries:
                af = loopdata.LoopData.parse_almanac_field(entry)
                assert af is not None, entry
                obj = loopdata.AlmanacFieldEvaluator.evaluate(None, af, alm, TIME_TS)
                values[entry] = loopdata.AlmanacFieldEvaluator.to_json_value(
                    None, af, obj)
        setting = values['almanac.sun.next_setting.unix_epoch.raw']
        rising = values['almanac.sun.next_rising.unix_epoch.raw']
        dark = values['almanac(horizon=-18).sun.next_setting.unix_epoch.raw']
        dark_end = values['almanac(horizon=-18).sun.next_rising.unix_epoch.raw']
        assert TIME_TS < setting < TIME_TS + 86400
        assert TIME_TS < rising < TIME_TS + 86400
        assert setting < rising          # fixture noon: sunset comes first
        assert dark > setting            # true darkness falls after sunset
        assert TIME_TS < dark_end < TIME_TS + 86400
        # The season pair: from the June fixture the next equinox is
        # September's, the next solstice December's -- both ahead,
        # equinox first.
        equinox = values['almanac.next_equinox.unix_epoch.raw']
        solstice = values['almanac.next_solstice.unix_epoch.raw']
        assert TIME_TS < equinox < solstice < TIME_TS + 200 * 86400
        # Earth's apsis pair (skyfield 2.1's next_perihelion/
        # next_aphelion, built on this page's ask): from the June
        # fixture the aphelion is ~12 days ahead (early July -- inside
        # the chip's 30-day window, so the fixture page shows the
        # chip), the perihelion next January.
        aphelion = values['almanac.next_aphelion.unix_epoch.raw']
        perihelion = values['almanac.next_perihelion.unix_epoch.raw']
        assert TIME_TS < aphelion < TIME_TS + 30 * 86400
        assert aphelion < perihelion < TIME_TS + 250 * 86400
        peak = values['almanac.next_meteor_shower.peak.unix_epoch.raw']
        assert abs(peak - 1753814687) < 600       # Southern Delta Aquariids
        assert values['almanac.next_meteor_shower.label'] == 'Southern Delta Aquariids'
        assert abs(values['almanac.next_supermoon.unix_epoch.raw']
                   - 1762348758) < 600
        assert values['almanac.next_eclipse.unix_epoch.raw'] > TIME_TS
        assert values['almanac.next_eclipse_kind'] in ('lunar', 'solar')

    def test_satellites_follow_configured_set(self):
        """With a configured satellite set, the appended satellite entries
        are that set exactly -- the nineteen-entry pattern per tag, in
        configuration order, the installer defaults nowhere in sight --
        and a second run adds nothing."""
        new, report = celestial.migrate_loopdata_fields(
            ['current.outTemp'], satellites=['terra', 'noaa21'])
        assert len([f for f in new if f.startswith('almanac.terra.')]) == 19
        assert len([f for f in new if f.startswith('almanac.noaa21.')]) == 19
        assert 'almanac.noaa21.next_pass.visible' in new
        assert not any(f.startswith(('almanac.iss.', 'almanac.tiangong.'))
                       for f in new)
        assert new.index('almanac.terra.az') < new.index('almanac.noaa21.az')
        assert any('almanac.terra.*' in note and '[[Satellites]]' in note
                   for note in report['notes'])
        twice, report2 = celestial.migrate_loopdata_fields(
            new, satellites=['terra', 'noaa21'])
        assert twice == new and report2['added'] == []

    def test_empty_satellites_appends_none_keeps_existing(self):
        """A present-but-empty [[Satellites]] is authoritative: no
        satellite fields are appended (a deliberately emptied set is not
        resurrected), but satellite entries already on the line are
        non-celestial-style untouchables and stay."""
        fields = ['current.outTemp', 'almanac.iss.az']
        new, report = celestial.migrate_loopdata_fields(fields, satellites=[])
        assert [f for f in new if f.startswith('almanac.iss.')] == ['almanac.iss.az']
        assert not any(f.startswith('almanac.tiangong.') for f in new)
        assert any('empty' in note and '--add-satellite' in note
                   for note in report['notes'])

    def test_no_satellites_section_appends_defaults(self):
        """No [[Satellites]] to follow (weewx-skyfield absent or pre-2.0):
        the installer defaults are provisioned, and the note says so."""
        new, report = celestial.migrate_loopdata_fields(['current.outTemp'])
        assert len([f for f in new if f.startswith('almanac.iss.')]) == 19
        assert len([f for f in new if f.startswith('almanac.tiangong.')]) == 19
        assert any('installer defaults' in note for note in report['notes'])

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
        assert ('current.Sunrise.raw', 'almanac.sunrise.unix_epoch.raw') in report['renamed']
        import configobj
        migrated = configobj.ConfigObj(str(out))
        fields = migrated['LoopData']['Include']['fields']
        assert 'almanac.sunrise.unix_epoch.raw' in fields
        assert 'current.Sunrise.raw' not in fields
        assert 'current.outTemp' in fields          # non-celestial preserved
        assert 'almanac.mars.az' in fields          # sample-report fields appended
        assert 'almanac.proxima_centauri.az' in fields
        assert 'almanac.iss.az' in fields           # no [Skyfield]: default satellites
        # The rest of the configuration survives the round trip.
        assert migrated['Station']['location'] == 'Test Station'
        # The original file is untouched.
        assert 'current.Sunrise.raw' in conf.read_text()

    def test_conf_rewrite_follows_skyfield_satellites(self, tmp_path):
        """The migrator reads [Skyfield] [[Satellites]] from the very
        configuration it rewrites: fields for the configured satellites,
        none for the installer defaults the user does not have."""
        conf = tmp_path / 'weewx.conf'
        conf.write_text(
            '[Skyfield]\n'
            '    [[Satellites]]\n'
            '        terra = 25994\n'
            '        noaa21 = 54234\n'
            '[LoopData]\n'
            '    [[Include]]\n'
            '        fields = current.outTemp\n'
        )
        out = tmp_path / 'weewx.conf.migrated'
        report = celestial.migrate_loopdata_conf(str(conf), str(out))
        import configobj
        fields = configobj.ConfigObj(str(out))['LoopData']['Include']['fields']
        assert len([f for f in fields if f.startswith('almanac.terra.')]) == 19
        assert len([f for f in fields if f.startswith('almanac.noaa21.')]) == 19
        assert not any(f.startswith(('almanac.iss.', 'almanac.tiangong.'))
                       for f in fields)
        assert any('[[Satellites]]' in note for note in report['notes'])

    def test_comets_follow_configured_set(self):
        """With a configured comet set, the appended comet entries are
        that set exactly -- the six-entry pattern per tag, in
        configuration order, the installer default nowhere in sight --
        and a second run adds nothing."""
        new, report = celestial.migrate_loopdata_fields(
            ['current.outTemp'], satellites=[], comets=['a3', 'encke'])
        assert len([f for f in new if f.startswith('almanac.a3.')]) == 6
        assert len([f for f in new if f.startswith('almanac.encke.')]) == 6
        assert 'almanac.a3.perihelion.unix_epoch.raw' in new
        assert not any(f.startswith(('almanac.halley.', 'almanac.hale_bopp.'))
                       for f in new)
        assert new.index('almanac.a3.az') < new.index('almanac.encke.az')
        assert any('almanac.a3.*' in note and '[[Comets]]' in note
                   for note in report['notes'])
        twice, report2 = celestial.migrate_loopdata_fields(
            new, satellites=[], comets=['a3', 'encke'])
        assert twice == new and report2['added'] == []

    def test_empty_comets_appends_none_keeps_existing(self):
        """A present-but-empty [[Comets]] is authoritative: no comet
        fields are appended (a deliberately emptied set is not
        resurrected), but comet entries already on the line stay."""
        fields = ['current.outTemp', 'almanac.halley.az']
        new, report = celestial.migrate_loopdata_fields(
            fields, satellites=[], comets=[])
        assert [f for f in new if f.startswith('almanac.halley.')] == [
            'almanac.halley.az']
        assert any('[[Comets]]' in note and '--add-comet' in note
                   for note in report['notes'])

    def test_no_comets_section_appends_defaults(self):
        """No [[Comets]] to follow (weewx-skyfield absent or pre-2.1):
        the installer defaults (halley and hale_bopp) are provisioned,
        and the note says so."""
        new, report = celestial.migrate_loopdata_fields(['current.outTemp'])
        assert len([f for f in new if f.startswith('almanac.halley.')]) == 6
        assert len([f for f in new if f.startswith('almanac.hale_bopp.')]) == 6
        assert any('almanac.halley.*' in note and 'almanac.hale_bopp.*' in note
                   and 'installer defaults' in note
                   for note in report['notes'])

    def test_conf_rewrite_follows_skyfield_comets(self, tmp_path):
        """The migrator reads [Skyfield] [[Comets]] from the very
        configuration it rewrites: fields for the configured comets,
        none for the installer default the user does not have."""
        conf = tmp_path / 'weewx.conf'
        conf.write_text(
            '[Skyfield]\n'
            '    [[Satellites]]\n'
            '        iss = 25544\n'
            '    [[Comets]]\n'
            '        a3 = "C/2023 A3"\n'
            '[LoopData]\n'
            '    [[Include]]\n'
            '        fields = current.outTemp\n'
        )
        out = tmp_path / 'weewx.conf.migrated'
        report = celestial.migrate_loopdata_conf(str(conf), str(out))
        import configobj
        fields = configobj.ConfigObj(str(out))['LoopData']['Include']['fields']
        assert len([f for f in fields if f.startswith('almanac.a3.')]) == 6
        assert len([f for f in fields if f.startswith('almanac.iss.')]) == 19
        assert not any(f.startswith(('almanac.halley.', 'almanac.tiangong.'))
                       for f in fields)
        assert any('[[Comets]]' in note for note in report['notes'])


class TestSatelliteUtility:
    """The --add-satellite / --remove-satellite utility: the three
    weewx.conf edits a satellite takes -- the [Skyfield] [[Satellites]]
    entry, the nineteen fields-line entries, the [StdReport] [[Defaults]]
    [[[Almanac]]] display name -- each independently idempotent, so any
    mixed starting state converges."""

    BASE_CONF = (
        '# a comment\n'
        '[Station]\n'
        '    location = Test Station\n'
        '[Skyfield]\n'
        '    satellite_downloads = true\n'
        '    [[Satellites]]\n'
        '        iss = 25544\n'
        '        tiangong = 48274\n'
        '[LoopData]\n'
        '    [[Include]]\n'
        '        fields = current.dateTime.raw, almanac.sun.az, almanac.iss.az\n'
    )

    def _write_conf(self, tmp_path, text=None):
        conf = tmp_path / 'weewx.conf'
        conf.write_text(self.BASE_CONF if text is None else text)
        return conf

    def test_pattern_is_nineteen_tag_substituted(self):
        """The per-satellite pattern is the almanac.iss.* subset of
        _MIGRATION_NEW_FIELDS with the tag substituted -- one source of
        truth with the page's satellite consumption -- and stays
        comma-free (the fields line is a bare comma-separated list)."""
        fields = celestial.satellite_fields('zenit23088')
        iss_fields = [f for f in celestial._MIGRATION_NEW_FIELDS
                      if f.startswith('almanac.iss.')]
        assert len(fields) == 19
        assert fields == [f.replace('almanac.iss.', 'almanac.zenit23088.')
                          for f in iss_fields]
        for field in fields:
            assert ',' not in field, field

    def test_added_entries_parse_in_loopdata(self):
        """Every entry the utility appends parses in the sibling
        weewx-loopdata checkout's almanac grammar."""
        loopdata = load_loopdata()
        for entry in celestial.satellite_fields('zenit23088'):
            assert loopdata.LoopData.parse_almanac_field(entry) is not None, entry

    def test_add_conf_roundtrip(self, tmp_path):
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(
            str(conf), str(out), 'zenit23088', '23088', 'Zenit-2 23088')
        assert report['satellites_entry'] == 'added'
        assert len(report['fields_added']) == 19
        assert report['name_entry'] == 'added'
        import configobj
        new = configobj.ConfigObj(str(out))
        assert new['Skyfield']['Satellites']['zenit23088'] == '23088'
        assert new['Skyfield']['Satellites']['iss'] == '25544'   # untouched
        fields = new['LoopData']['Include']['fields']
        assert 'almanac.zenit23088.az' in fields
        assert 'almanac.zenit23088.next_pass.visible' in fields
        assert fields[:3] == ['current.dateTime.raw', 'almanac.sun.az',
                              'almanac.iss.az']                  # appended, not reordered
        assert new['StdReport']['Defaults']['Almanac']['zenit23088'] == 'Zenit-2 23088'
        # The rest of the configuration survives; the original is untouched.
        assert new['Station']['location'] == 'Test Station'
        assert 'zenit23088' not in conf.read_text()

    def test_add_is_idempotent(self, tmp_path):
        conf = self._write_conf(tmp_path)
        once = tmp_path / 'once.conf'
        celestial.add_satellite_conf(str(conf), str(once),
                                     'zenit23088', '23088', 'Zenit-2 23088')
        twice = tmp_path / 'twice.conf'
        report = celestial.add_satellite_conf(str(once), str(twice),
                                              'zenit23088', '23088', 'Zenit-2 23088')
        assert report['satellites_entry'] == 'unchanged'
        assert report['fields_added'] == []
        assert report['name_entry'] == 'unchanged'
        import configobj
        assert (configobj.ConfigObj(str(once))['LoopData']['Include']['fields']
                == configobj.ConfigObj(str(twice))['LoopData']['Include']['fields'])

    def test_add_converges_mixed_states(self, tmp_path):
        """John's scenario: the satellite was already added per
        weewx-skyfield's instructions -- the [[Satellites]] entry exists,
        the fields do not.  The entry is kept and the fields appended.
        And the reverse: fields hand-added, entry missing."""
        conf = self._write_conf(tmp_path, self.BASE_CONF.replace(
            '        tiangong = 48274\n',
            '        tiangong = 48274\n        zenit23088 = 23088\n'))
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out),
                                              'zenit23088', '23088')
        assert report['satellites_entry'] == 'unchanged'
        assert len(report['fields_added']) == 19
        # The reverse: every field present, no [[Satellites]] entry.
        hand_fields = ', '.join(celestial.satellite_fields('zenit23088'))
        conf2 = tmp_path / 'weewx2.conf'
        conf2.write_text(self.BASE_CONF.replace(
            'almanac.iss.az\n', 'almanac.iss.az, %s\n' % hand_fields))
        out2 = tmp_path / 'weewx2.conf.new'
        report2 = celestial.add_satellite_conf(str(conf2), str(out2),
                                               'zenit23088', '23088')
        assert report2['satellites_entry'] == 'added'
        assert report2['fields_added'] == []

    def test_add_updates_differing_norad(self, tmp_path):
        """The invocation is authoritative: an existing entry with a
        different catalog number is updated and reported."""
        conf = self._write_conf(tmp_path, self.BASE_CONF.replace(
            '        tiangong = 48274\n',
            '        tiangong = 48274\n        zenit23088 = 99999\n'))
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out),
                                              'zenit23088', '23088')
        assert report['satellites_entry'] == 'updated'
        assert report['previous_norad'] == '99999'
        import configobj
        assert configobj.ConfigObj(str(out))['Skyfield']['Satellites']['zenit23088'] == '23088'

    def test_add_name_handling(self, tmp_path):
        """Without --name: no [[[Almanac]]] entry is written, an existing
        one is never deleted, and the hint shows the title-cased default.
        With --name: an existing entry updates."""
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'a.conf'
        report = celestial.add_satellite_conf(str(conf), str(out),
                                              'zenit23088', '23088')
        assert report['name_entry'] == 'not given'
        assert any('Zenit23088' in h for h in report['hints'])
        import configobj
        assert 'zenit23088' not in configobj.ConfigObj(str(out)).get(
            'StdReport', {}).get('Defaults', {}).get('Almanac', {})
        # Name it, then re-run without --name: the name survives.
        out2 = tmp_path / 'b.conf'
        celestial.add_satellite_conf(str(out), str(out2),
                                     'zenit23088', '23088', 'Zenit-2 23088')
        out3 = tmp_path / 'c.conf'
        report3 = celestial.add_satellite_conf(str(out2), str(out3),
                                               'zenit23088', '23088')
        assert report3['name_entry'] == 'not given'
        assert not any('Zenit23088' in h for h in report3['hints'])
        new3 = configobj.ConfigObj(str(out3))
        assert new3['StdReport']['Defaults']['Almanac']['zenit23088'] == 'Zenit-2 23088'
        # A differing --name updates in place: the rename path.
        out4 = tmp_path / 'd.conf'
        report4 = celestial.add_satellite_conf(str(out3), str(out4),
                                               'zenit23088', '23088', 'Zenit-2')
        assert report4['name_entry'] == 'updated'
        assert configobj.ConfigObj(str(out4))['StdReport']['Defaults']['Almanac']['zenit23088'] == 'Zenit-2'

    def test_add_refuses_bad_tags_and_numbers(self, tmp_path):
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'weewx.conf.new'
        for tag in ('moon', 'venus', 'proxima_centauri',  # almanac bodies
                    'sat_25544',                          # alternate-spelling namespace
                    'Zenit', 'zenit-2', '2001', ''):      # not lowercase identifiers
            with pytest.raises(ValueError):
                celestial.add_satellite_conf(str(conf), str(out), tag, '23088')
        with pytest.raises(ValueError):
            celestial.add_satellite_conf(str(conf), str(out), 'zenit23088', '23088a')
        assert not out.exists()   # nothing was written

    def test_add_requires_fields_line(self, tmp_path):
        """Without a [LoopData] [[Include]] fields entry there is nothing
        to append to: the error points at --migrate-loopdata-fields."""
        conf = self._write_conf(tmp_path, '[Station]\n    location = Test\n')
        out = tmp_path / 'weewx.conf.new'
        with pytest.raises(ValueError, match='migrate-loopdata-fields'):
            celestial.add_satellite_conf(str(conf), str(out), 'zenit23088', '23088')

    def test_remove_conf_roundtrip(self, tmp_path):
        conf = self._write_conf(tmp_path)
        added = tmp_path / 'added.conf'
        celestial.add_satellite_conf(str(conf), str(added),
                                     'zenit23088', '23088', 'Zenit-2 23088')
        # A hand-added entry with almanac arguments belongs to the
        # satellite too; removal sweeps every spelling.
        import configobj
        cfg = configobj.ConfigObj(str(added))
        cfg['LoopData']['Include']['fields'].append(
            'almanac(horizon=10).zenit23088.next_pass.rise.unix_epoch.raw')
        cfg.write()
        out = tmp_path / 'removed.conf'
        report = celestial.remove_satellite_conf(str(added), str(out), 'zenit23088')
        assert report['satellites_entry'] == 'removed'
        assert report['norad'] == '23088'
        assert len(report['fields_removed']) == 20
        assert report['name_entry'] == 'removed'
        assert any('wxskyfield_sat_23088.tle' in h for h in report['hints'])
        new = configobj.ConfigObj(str(out))
        assert 'zenit23088' not in new['Skyfield']['Satellites']
        fields = new['LoopData']['Include']['fields']
        assert not any('zenit23088' in f for f in fields)
        assert 'almanac.iss.az' in fields            # other satellites untouched
        assert 'almanac.sun.az' in fields
        assert 'zenit23088' not in new['StdReport']['Defaults']['Almanac']
        # Removing an absent satellite is a no-op, not an error.
        out2 = tmp_path / 'removed2.conf'
        report2 = celestial.remove_satellite_conf(str(out), str(out2), 'zenit23088')
        assert report2['satellites_entry'] == 'absent'
        assert report2['fields_removed'] == []
        assert report2['name_entry'] == 'absent'

    def test_remove_default_satellite_warns(self, tmp_path):
        """iss/tiangong removal works like any other -- with the warning
        that a weewx-skyfield upgrade's conditional merge re-adds the
        [[Satellites]] entry (only), so the removal wants re-running."""
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'weewx.conf.new'
        report = celestial.remove_satellite_conf(str(conf), str(out), 'iss')
        assert report['satellites_entry'] == 'removed'
        assert report['fields_removed'] == ['almanac.iss.az']
        assert any('installer default' in h for h in report['hints'])
        import configobj
        new = configobj.ConfigObj(str(out))
        assert 'iss' not in new['Skyfield']['Satellites']
        assert new['Skyfield']['Satellites']['tiangong'] == '48274'

    def test_add_refuses_comet_tags(self, tmp_path):
        """Satellites and comets share the almanac.<tag> namespace: a
        configured [[Comets]] tag is refused, and so is the comet
        installer default even when no [[Comets]] section exists (the
        next weewx-skyfield install re-adds it)."""
        conf = self._write_conf(tmp_path, self.BASE_CONF.replace(
            '    [[Satellites]]\n',
            '    [[Comets]]\n        encke = 2P\n    [[Satellites]]\n'))
        out = tmp_path / 'weewx.conf.new'
        with pytest.raises(ValueError, match='comet tag'):
            celestial.add_satellite_conf(str(conf), str(out), 'encke', '23088')
        conf2 = self._write_conf(tmp_path)          # no [[Comets]] at all
        with pytest.raises(ValueError, match='comet tag'):
            celestial.add_satellite_conf(str(conf2), str(out), 'halley', '23088')
        assert not out.exists()


class TestCometUtility:
    """The --add-comet / --remove-comet utility: the three weewx.conf
    edits a comet takes -- the [Skyfield] [[Comets]] entry, the six
    fields-line entries, the [StdReport] [[Defaults]] [[[Almanac]]]
    display name -- each independently idempotent, mirroring the
    satellite utility."""

    BASE_CONF = (
        '# a comment\n'
        '[Station]\n'
        '    location = Test Station\n'
        '[Skyfield]\n'
        '    comet_downloads = true\n'
        '    [[Satellites]]\n'
        '        iss = 25544\n'
        '    [[Comets]]\n'
        '        halley = 1P\n'
        '[LoopData]\n'
        '    [[Include]]\n'
        '        fields = current.dateTime.raw, almanac.sun.az, almanac.halley.az\n'
    )

    def _write_conf(self, tmp_path, text=None):
        conf = tmp_path / 'weewx.conf'
        conf.write_text(self.BASE_CONF if text is None else text)
        return conf

    def test_pattern_is_six_tag_substituted(self):
        """The per-comet pattern is the almanac.halley.* subset of
        _MIGRATION_NEW_FIELDS with the tag substituted -- one source of
        truth with the page's comet consumption -- and stays comma-free
        (the fields line is a bare comma-separated list)."""
        fields = celestial.comet_fields('mcnaught')
        halley_fields = [f for f in celestial._MIGRATION_NEW_FIELDS
                         if f.startswith('almanac.halley.')]
        assert len(fields) == 6
        assert fields == [f.replace('almanac.halley.', 'almanac.mcnaught.')
                          for f in halley_fields]
        for field in fields:
            assert ',' not in field, field

    def test_added_entries_parse_in_loopdata(self):
        """Every entry the utility appends parses in the sibling
        weewx-loopdata checkout's almanac grammar."""
        loopdata = load_loopdata()
        for entry in celestial.comet_fields('mcnaught'):
            assert loopdata.LoopData.parse_almanac_field(entry) is not None, entry

    def test_add_conf_roundtrip(self, tmp_path):
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_comet_conf(
            str(conf), str(out), 'mcnaught', '220P', 'McNaught')
        assert report['comets_entry'] == 'added'
        assert len(report['fields_added']) == 6
        assert report['name_entry'] == 'added'
        import configobj
        new = configobj.ConfigObj(str(out))
        assert new['Skyfield']['Comets']['mcnaught'] == '220P'
        assert new['Skyfield']['Comets']['halley'] == '1P'       # untouched
        fields = new['LoopData']['Include']['fields']
        assert 'almanac.mcnaught.az' in fields
        assert 'almanac.mcnaught.perihelion.unix_epoch.raw' in fields
        assert fields[:3] == ['current.dateTime.raw', 'almanac.sun.az',
                              'almanac.halley.az']               # appended, not reordered
        assert new['StdReport']['Defaults']['Almanac']['mcnaught'] == 'McNaught'
        # The rest of the configuration survives; the original is untouched.
        assert new['Station']['location'] == 'Test Station'
        assert 'mcnaught' not in conf.read_text()

    def test_add_accepts_spaced_designation(self, tmp_path):
        """Provisional designations carry a space (C/2023 A3) and
        fragment suffixes a hyphen (C/1947 X1-B); both round-trip
        through the config grammar (never a comma, so the [[Comets]]
        value cannot break it)."""
        conf = self._write_conf(tmp_path)
        import configobj
        for tag, designation in (('a3', 'C/2023 A3'),
                                 ('southern', 'C/1947 X1-B')):
            out = tmp_path / ('%s.conf' % tag)
            report = celestial.add_comet_conf(str(conf), str(out),
                                              tag, designation)
            assert report['comets_entry'] == 'added'
            assert configobj.ConfigObj(str(out))['Skyfield']['Comets'][tag] \
                == designation

    def test_add_is_idempotent(self, tmp_path):
        conf = self._write_conf(tmp_path)
        once = tmp_path / 'once.conf'
        celestial.add_comet_conf(str(conf), str(once),
                                 'mcnaught', '220P', 'McNaught')
        twice = tmp_path / 'twice.conf'
        report = celestial.add_comet_conf(str(once), str(twice),
                                          'mcnaught', '220P', 'McNaught')
        assert report['comets_entry'] == 'unchanged'
        assert report['fields_added'] == []
        assert report['name_entry'] == 'unchanged'
        import configobj
        assert (configobj.ConfigObj(str(once))['LoopData']['Include']['fields']
                == configobj.ConfigObj(str(twice))['LoopData']['Include']['fields'])

    def test_add_updates_differing_designation(self, tmp_path):
        """The invocation is authoritative: an existing entry with a
        different designation is updated and reported."""
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_comet_conf(str(conf), str(out), 'halley', '109P')
        assert report['comets_entry'] == 'updated'
        assert report['previous_designation'] == '1P'
        import configobj
        assert configobj.ConfigObj(str(out))['Skyfield']['Comets']['halley'] == '109P'

    def test_add_refuses_bad_tags_and_designations(self, tmp_path):
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'weewx.conf.new'
        for tag in ('moon', 'venus', 'proxima_centauri',  # almanac bodies
                    'Halley', 'hale-bopp', '2p', ''):     # not lowercase identifiers
            with pytest.raises(ValueError):
                celestial.add_comet_conf(str(conf), str(out), tag, '1P')
        for tag in ('iss', 'tiangong'):  # satellite tags: configured + default
            with pytest.raises(ValueError, match='satellite tag'):
                celestial.add_comet_conf(str(conf), str(out), tag, '1P')
        for designation in ('1p', 'halley', '2023 A3', '1P,2P', 'P/', ''):
            with pytest.raises(ValueError):
                celestial.add_comet_conf(str(conf), str(out), 'encke', designation)
        assert not out.exists()   # nothing was written

    def test_add_requires_fields_line(self, tmp_path):
        """Without a [LoopData] [[Include]] fields entry there is nothing
        to append to: the error points at --migrate-loopdata-fields."""
        conf = self._write_conf(tmp_path, '[Station]\n    location = Test\n')
        out = tmp_path / 'weewx.conf.new'
        with pytest.raises(ValueError, match='migrate-loopdata-fields'):
            celestial.add_comet_conf(str(conf), str(out), 'encke', '2P')

    def test_remove_conf_roundtrip(self, tmp_path):
        conf = self._write_conf(tmp_path)
        added = tmp_path / 'added.conf'
        celestial.add_comet_conf(str(conf), str(added),
                                 'mcnaught', '220P', 'McNaught')
        # A hand-added entry with almanac arguments belongs to the comet
        # too; removal sweeps every spelling.
        import configobj
        cfg = configobj.ConfigObj(str(added))
        cfg['LoopData']['Include']['fields'].append(
            'almanac(horizon=10).mcnaught.az')
        cfg.write()
        out = tmp_path / 'removed.conf'
        report = celestial.remove_comet_conf(str(added), str(out), 'mcnaught')
        assert report['comets_entry'] == 'removed'
        assert report['designation'] == '220P'
        assert len(report['fields_removed']) == 7
        assert report['name_entry'] == 'removed'
        new = configobj.ConfigObj(str(out))
        assert 'mcnaught' not in new['Skyfield']['Comets']
        fields = new['LoopData']['Include']['fields']
        assert not any('mcnaught' in f for f in fields)
        assert 'almanac.halley.az' in fields         # other comets untouched
        assert 'almanac.sun.az' in fields
        assert 'mcnaught' not in new['StdReport']['Defaults']['Almanac']
        # Removing an absent comet is a no-op, not an error.
        out2 = tmp_path / 'removed2.conf'
        report2 = celestial.remove_comet_conf(str(out), str(out2), 'mcnaught')
        assert report2['comets_entry'] == 'absent'
        assert report2['fields_removed'] == []
        assert report2['name_entry'] == 'absent'

    def test_remove_default_comet_warns(self, tmp_path):
        """halley removal works like any other -- with the warning that a
        weewx-skyfield upgrade's conditional merge re-adds the [[Comets]]
        entry (only), so the removal wants re-running."""
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'weewx.conf.new'
        report = celestial.remove_comet_conf(str(conf), str(out), 'halley')
        assert report['comets_entry'] == 'removed'
        assert report['fields_removed'] == ['almanac.halley.az']
        assert any('installer default' in h for h in report['hints'])
        import configobj
        new = configobj.ConfigObj(str(out))
        assert 'halley' not in new['Skyfield']['Comets']
        assert new['Skyfield']['Satellites']['iss'] == '25544'   # untouched


def load_installer():
    """The repo's install.py, imported under a private name with the real
    weecfg ExtensionInstaller standing in for weectl's 'setup' shim (the
    'install' module slot is never disturbed)."""
    import importlib.util
    import types
    from weecfg.extension import ExtensionInstaller
    setup_stub = types.ModuleType('setup')
    setup_stub.ExtensionInstaller = ExtensionInstaller
    saved = sys.modules.get('setup')
    sys.modules['setup'] = setup_stub
    try:
        spec = importlib.util.spec_from_file_location(
            '_celestial_install_test', os.path.join(REPO_ROOT, 'install.py'))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop('setup', None)
        else:
            sys.modules['setup'] = saved
    return module


class TestInstallerFieldsHint:
    """The install-time fields update: weectl's configure() hook brings
    the station's [LoopData] [[Include]] fields line up to date with
    what the page reads -- the bundled migrator run in memory as the
    oracle, [Skyfield] [[Satellites]] and [[Comets]] included.
    APPEND-ONLY: missing entries are appended in place (configure
    returns True and weectl saves); existing entries are never renamed,
    removed or reordered -- the migrator's destructive half stays
    behind the human-reviewed CLI flow and is only hinted.  Honors
    weectl's dry run and never fails the install."""

    class _Printer:
        def __init__(self):
            self.lines = []

        def out(self, msg, level=1):
            self.lines.append(msg)

    def _engine(self, config, dry_run=False):
        import types
        return types.SimpleNamespace(config_dict=config,
                                     printer=self._Printer(),
                                     dry_run=dry_run,
                                     root_dict={'WEEWX_ROOT': '/wx'},
                                     config_path='/wx/weewx.conf')

    def _installer(self):
        return load_installer().CelestialInstaller()

    def test_appends_missing_fields(self):
        """A line missing entries gains exactly the migrator's appends,
        AFTER the existing entries (never reordered), and configure
        returns True so weectl saves the configuration."""
        engine = self._engine(
            {'LoopData': {'Include': {'fields': ['current.outTemp']}}})
        assert self._installer().configure(engine) is True
        new_line = engine.config_dict['LoopData']['Include']['fields']
        # 50 base entries plus 19 each for the default satellites and 6
        # each for the default comets (no [Skyfield] section to follow).
        assert new_line[0] == 'current.outTemp'
        assert len(new_line) == 101
        assert 'almanac.halley.az' in new_line
        assert 'almanac.iss.next_pass.visible' in new_line
        text = '\n'.join(engine.printer.lines)
        assert 'Appended 100 entries' in text
        assert '    almanac.sun.az' in text        # each entry is listed
        assert 'Restart weewxd' in text
        assert 'outdated spellings' not in text    # nothing to hint here

    def test_appends_follow_satellites_and_comets(self):
        engine = self._engine(
            {'Skyfield': {'Satellites': {'terra': '25994'}},
             'LoopData': {'Include': {'fields': ['current.outTemp']}}})
        assert self._installer().configure(engine) is True
        # 50 base + 19 for terra + 6 each for halley and hale_bopp (a
        # [Skyfield] with no [[Comets]] section still falls back to the
        # comet defaults).
        assert 'Appended 81 entries' in '\n'.join(engine.printer.lines)
        new_line = engine.config_dict['LoopData']['Include']['fields']
        assert 'almanac.terra.az' in new_line
        assert not any(f.startswith('almanac.iss.') for f in new_line)

    def test_silent_when_complete_for_configured_satellites(self):
        """A line complete for the CONFIGURED set stays silent and
        untouched -- the absent installer defaults must not be added or
        nagged about."""
        complete, _ = celestial.migrate_loopdata_fields(
            ['current.outTemp'], satellites=['terra'])
        engine = self._engine(
            {'Skyfield': {'Satellites': {'terra': '25994'}},
             'LoopData': {'Include': {'fields': list(complete)}}})
        assert self._installer().configure(engine) is False
        assert engine.printer.lines == []
        assert engine.config_dict['LoopData']['Include']['fields'] == complete

    def test_silent_for_emptied_comets(self):
        """A deliberately emptied [[Comets]] is authoritative for the
        installer too: a line complete for the configured sets is left
        alone, never re-provisioned with the halley defaults."""
        complete, _ = celestial.migrate_loopdata_fields(
            ['current.outTemp'], satellites=['terra'], comets=[])
        engine = self._engine(
            {'Skyfield': {'Satellites': {'terra': '25994'}, 'Comets': {}},
             'LoopData': {'Include': {'fields': list(complete)}}})
        assert self._installer().configure(engine) is False
        assert engine.printer.lines == []
        assert engine.config_dict['LoopData']['Include']['fields'] == complete

    def test_dry_run_touches_nothing(self):
        """weectl --dry-run: the would-append count prints, the
        configuration is not modified, configure returns False."""
        engine = self._engine(
            {'LoopData': {'Include': {'fields': ['current.outTemp']}}},
            dry_run=True)
        assert self._installer().configure(engine) is False
        assert engine.config_dict['LoopData']['Include']['fields'] == \
            ['current.outTemp']
        text = '\n'.join(engine.printer.lines)
        assert 'Would append 100 entries' in text

    def test_renames_hinted_never_applied(self):
        """Outdated spellings are the migrator's destructive half: the
        installer prints the reviewed-migration commands but NEVER
        rewrites an existing entry -- the legacy entry survives
        verbatim, and with nothing to append the configuration is
        unmodified."""
        complete, _ = celestial.migrate_loopdata_fields([])
        line = ['current.Sunrise.raw'] + complete
        engine = self._engine(
            {'LoopData': {'Include': {'fields': list(line)}}})
        assert self._installer().configure(engine) is False
        assert engine.config_dict['LoopData']['Include']['fields'] == line
        text = '\n'.join(engine.printer.lines)
        assert 'outdated spellings' in text
        assert '--migrate-loopdata-fields' in text
        assert 'cd /wx/bin' in text
        assert '--config /wx/weewx.conf' in text
        # The command must carry the running weewx's location: on a
        # deb/rpm package install WeeWX lives in /usr/share/weewx, on
        # sys.path only inside weectl, and the bare 7.8-8.0 hint died
        # there with ModuleNotFoundError: weewx.
        weewx_dir = os.path.dirname(os.path.dirname(
            os.path.abspath(weewx.__file__)))
        assert ('PYTHONPATH=%s %s -m user.celestial'
                % (weewx_dir, sys.executable)) in text
        # The review command is a word-diff: the fields line is one long
        # comma-separated value, and a plain diff shows two unreadable lines.
        assert 'git diff --no-index --word-diff /wx/weewx.conf' in text

    def test_appends_and_hints_together(self):
        """A legacy line missing entries gets BOTH: the safe appends
        applied (configure returns True), the renames only hinted --
        and the legacy entry still survives verbatim."""
        engine = self._engine(
            {'LoopData': {'Include': {'fields': ['current.Sunrise.raw']}}})
        assert self._installer().configure(engine) is True
        new_line = engine.config_dict['LoopData']['Include']['fields']
        assert new_line[0] == 'current.Sunrise.raw'
        # The rename target (almanac.sunrise.unix_epoch.raw) is not a
        # page field, so it is NOT appended -- renames stay manual.
        assert 'almanac.sunrise.unix_epoch.raw' not in new_line
        text = '\n'.join(engine.printer.lines)
        assert 'Appended 100 entries' in text
        assert 'outdated spellings' in text

    def test_hint_when_no_loopdata(self):
        engine = self._engine({})
        assert self._installer().configure(engine) is False
        text = '\n'.join(engine.printer.lines)
        assert 'no [LoopData] [[Include]] fields entry' in text
        assert 'weewx-loopdata' in text

    def test_never_fails_the_install(self):
        """A configuration shaped wrong (fields not list-or-string) must
        degrade to the could-not-check line, never an exception."""
        engine = self._engine(
            {'LoopData': {'Include': {'fields': 3.14}}})
        assert self._installer().configure(engine) is False
        assert any('Could not check' in line for line in engine.printer.lines)


# ─────────────────────────────────────────────────────────────────────
# The manual, pinned to the code.
#
# docs/ is hand-written prose that restates machine-readable facts: the
# fields the skin consumes, the per-satellite and per-comet patterns,
# and the skin's own [Texts] dictionary.  A hand-maintained copy of a
# generated fact drifts silently -- 8.1 shipped an i18n.md dictionary
# with one wrong string and one missing one, and nothing noticed until
# a human read both files side by side.  These audits fail when the
# manual and the code disagree, in EITHER direction: a field the code
# gained and the docs missed, and a field the docs still promise after
# the code dropped it.  The second is the one that bites at a release.
# ─────────────────────────────────────────────────────────────────────

DOCS_DIR = os.path.join(REPO_ROOT, 'docs')

# The bodies the Geocentric dial places, in _MIGRATION_NEW_FIELDS order.
# Named here so the countdown-chip audit can subtract them; the skin's
# own count is pinned separately by the render tests.
_DIAL_BODIES = ('sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter',
                'saturn', 'uranus', 'neptune', 'pluto', 'proxima_centauri')

# The installer's default satellite and comet tags -- what the shipped
# fields line (and therefore the manual's copy of it) is written for.
_DEFAULT_SAT_TAGS   = ('iss', 'tiangong')
_DEFAULT_COMET_TAGS = ('halley', 'hale_bopp')


def _doc_text(name):
    with open(os.path.join(DOCS_DIR, name), encoding='utf-8') as f:
        return f.read()


def _fenced_blocks(text):
    """Every fenced code block's body, in document order."""
    return re.findall(r'^```[a-z]*\n(.*?)^```', text, re.S | re.M)


def _block_containing(text, needle, without=None):
    """The one fenced block carrying `needle` (and not `without`)."""
    hits = [b for b in _fenced_blocks(text)
            if needle in b and (without is None or without not in b)]
    assert len(hits) == 1, (
        'expected exactly one fenced block containing %r%s, found %d'
        % (needle, '' if without is None else ' and not %r' % without,
           len(hits)))
    return hits[0]


def _fields_in(block):
    """The field entries in a block, in order: the fields line grammar is
    a bare comma-separated list, so split on commas and drop whitespace
    (the manual wraps the per-tag patterns across lines for legibility)."""
    return [entry.strip() for entry in block.replace('\n', ' ').split(',')
            if entry.strip()]


def _heading_anchor(text):
    """kramdown's auto_id for a heading: inline markup stripped,
    lowercased, characters outside [a-z0-9 _-] dropped, then spaces (not
    runs of them -- one hyphen per space) turned into hyphens.  Pinned
    against the real generated ids by test_anchor_rule_matches_kramdown."""
    t = re.sub(r'`([^`]*)`', r'\1', text)
    t = re.sub(r'\*\*?([^*]*)\*\*?', r'\1', t)
    t = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)
    t = t.strip().lower()
    t = ''.join(c for c in t if c.isalnum() or c in ' _-')
    return t.replace(' ', '-')


def _headings(text):
    """Every heading in a markdown page, code fences excluded."""
    out, in_fence = [], False
    for line in text.splitlines():
        if line.startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r'^#{1,6}\s+(.*?)\s*$', line)
        if m:
            out.append(m.group(1))
    return out


def _ini_pairs(text):
    """The quoted key = value pairs of a [Texts]-style block, in order."""
    pairs = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        m = re.match(r'''^("[^"]*"|'[^']*')\s*=\s*("[^"]*"|'[^']*')\s*$''', s)
        if m:
            pairs.append((m.group(1)[1:-1], m.group(2)[1:-1]))
    return pairs


class TestManualInStepWithCode:
    """The manual's machine-checkable claims, pinned to the code that
    makes them true.  Every audit compares in BOTH directions."""

    # ── the extractors themselves ────────────────────────────────────
    # A green audit that silently parses nothing is worse than no audit,
    # so each extractor is pinned to landmarks and a plausible size
    # before it is trusted to compare anything.

    def test_extractors_find_what_they_claim_to_find(self):
        page = _doc_text('fields-reference.md')
        line = _fields_in(_block_containing(page, 'current.dateTime.raw'))
        assert len(line) == len(celestial._MIGRATION_NEW_FIELDS), (
            'the complete-line block parsed to %d entries' % len(line))
        assert 'almanac.sun.az' in line and 'almanac.hale_bopp.mag' in line

        texts = _ini_pairs(_block_containing(_doc_text('i18n-dictionary.md'), '"LIVE"'))
        assert len(texts) > 70, 'the dictionary block parsed to %d entries' % len(texts)
        assert ('LIVE', 'LIVE') in texts

        heads = _headings(_doc_text('reading-the-page.md'))
        assert 'The Geocentric' in heads and 'The sky dome' in heads

    def test_anchor_rule_matches_kramdown(self):
        """Landmarks read off the site jekyll actually generated -- the
        rule is subtle (one hyphen per SPACE, so punctuation between two
        words leaves a double hyphen) and worth pinning by example."""
        assert _heading_anchor('The header, and the badge that tells the truth') \
            == 'the-header-and-the-badge-that-tells-the-truth'
        assert _heading_anchor('### Satellites (19 entries each)'.lstrip('# ')) \
            == 'satellites-19-entries-each'
        assert _heading_anchor('The chart — `name`') == 'the-chart--name'
        assert _heading_anchor('The almanac tiers') == 'the-almanac-tiers'

    # ── the fields reference ─────────────────────────────────────────

    def test_fields_reference_line_matches_migration_field_set(self):
        """docs/fields-reference.md's complete line IS the field set the
        migrator appends -- same entries, same order.  Both directions:
        an entry the code gained, and an entry the docs still promise."""
        documented = _fields_in(
            _block_containing(_doc_text('fields-reference.md'),
                              'current.dateTime.raw'))
        shipped = list(celestial._MIGRATION_NEW_FIELDS)
        assert set(documented) - set(shipped) == set(), (
            'the manual documents fields the skin does not read: %s'
            % sorted(set(documented) - set(shipped)))
        assert set(shipped) - set(documented) == set(), (
            'the skin reads fields the manual does not document: %s'
            % sorted(set(shipped) - set(documented)))
        assert documented == shipped, (
            'same fields, different order -- the manual line is meant to '
            'be pasted, so it must match what the migrator writes')

    def test_fields_reference_per_tag_patterns(self):
        """The nineteen-entry satellite and six-entry comet patterns are
        the code's own, with the tag substituted."""
        page = _doc_text('fields-reference.md')
        sat = _fields_in(_block_containing(
            page, 'almanac.iss.next_pass.visible',
            without='current.dateTime.raw'))
        assert sat == celestial.satellite_fields('iss')
        comet = _fields_in(_block_containing(
            page, 'almanac.halley.mag', without='current.dateTime.raw'))
        assert comet == celestial.comet_fields('halley')

    def test_fields_reference_countdown_table_is_complete(self):
        """Every event field the chips run on appears in the countdown
        table, and nothing else does."""
        page = _doc_text('fields-reference.md')
        section = page.split('### The countdown chips', 1)[1].split('###', 1)[0]
        tabled = set()
        for line in section.splitlines():
            if line.startswith('|'):
                tabled.update(re.findall(r'`([^`]+)`', line))

        accounted = {'current.dateTime.raw'}
        for body in _DIAL_BODIES:
            accounted.update('almanac.%s.%s' % (body, m)
                             for m in ('az', 'alt', 'earth_distance'))
        accounted.update(('almanac.moon.phase',
                          'almanac.next_full_moon.unix_epoch.raw',
                          'almanac.next_new_moon.unix_epoch.raw'))
        for tag in _DEFAULT_SAT_TAGS:
            accounted.update(celestial.satellite_fields(tag))
        for tag in _DEFAULT_COMET_TAGS:
            accounted.update(celestial.comet_fields(tag))
        expected = set(celestial._MIGRATION_NEW_FIELDS) - accounted

        assert tabled == expected, (
            'countdown table vs the event fields the skin reads:\n'
            '  missing from the table: %s\n'
            '  in the table but not read: %s'
            % (sorted(expected - tabled), sorted(tabled - expected)))

    # ── the translation dictionary ───────────────────────────────────

    def test_translation_dictionary_matches_en_conf(self):
        """docs/i18n.md prints lang/en.conf's [Texts] as shipped, so it
        must BE lang/en.conf's [Texts] -- keys, values and order."""
        with open(os.path.join(REPO_ROOT, 'skins', 'Celestial', 'lang',
                               'en.conf'), encoding='utf-8') as f:
            en = f.read()
        section = re.split(r'^\[[A-Za-z]', re.split(r'^\[Texts\]\s*$', en,
                                                    flags=re.M)[1],
                           flags=re.M)[0]
        shipped = _ini_pairs(section)
        documented = _ini_pairs(
            _block_containing(_doc_text('i18n-dictionary.md'), '"LIVE"'))

        s_keys = [k for k, _ in shipped]
        d_keys = [k for k, _ in documented]
        assert set(s_keys) - set(d_keys) == set(), (
            'strings the skin renders that the manual omits: %s'
            % sorted(set(s_keys) - set(d_keys)))
        assert set(d_keys) - set(s_keys) == set(), (
            'strings the manual documents that the skin does not render: %s'
            % sorted(set(d_keys) - set(s_keys)))
        assert documented == shipped, (
            'the dictionary differs from en.conf in value or order')

    def test_translation_status_table_matches_shipped_lang_files(self):
        """docs/i18n.md's status table has a row per shipped translation
        -- and en.conf, the reference dictionary, is not a translation, so
        it must NOT have one.  A new lang file with no row ships
        uncredited and unlabelled; a row whose file is gone credits a
        language the skin no longer speaks.  The spelled-out count in the
        lead sentence is pinned to the same set."""
        page = _doc_text('i18n.md')
        tabled = [m for m in re.findall(
            r'^\|[^|]+\|\s*`lang/(\w+)\.conf`\s*\|', page, flags=re.M)]
        shipped = {f[:-5] for f in os.listdir(
            os.path.join(REPO_ROOT, 'skins', 'Celestial', 'lang'))
            if f.endswith('.conf')} - {'en'}

        assert len(tabled) == len(set(tabled)), \
            'a language is tabled twice: %s' % tabled
        assert set(tabled) == shipped, (
            'languages shipped but not tabled: %s; tabled but not shipped: %s'
            % (sorted(shipped - set(tabled)), sorted(set(tabled) - shipped)))
        assert 'en' not in tabled, \
            'en.conf is the reference dictionary, not a translation'

        words = {8: 'Eight', 9: 'Nine', 10: 'Ten', 11: 'Eleven', 12: 'Twelve'}
        assert '**%s translations ship with the skin**' % words[len(shipped)] \
            in page, ('the lead sentence does not say %s translations'
                      % words[len(shipped)])

        # Each row LEADS with its review status, in one of three
        # vocabularies: 'Reviewed' (a native speaker read this skin's own
        # strings), 'Partly reviewed' (only the vocabulary shared with
        # weewx-skyfield, reviewed over there) or 'Beta'.  An untouched
        # Beta row for a language since signed off is the drift that
        # matters most here, and prose in the status cell instead of one
        # of these words is how that starts.
        #
        # A review is also DATED: every one of these files grows with each
        # release that adds strings, so an undated "reviewed" claims a
        # review of a file larger than the one anybody read.  Nothing can
        # check that the date is the right one -- only that a claim of
        # review carries the release it was made against.
        for row in re.findall(r'^\|[^|]+\|\s*`lang/\w+\.conf`\s*\|([^|]*)\|',
                              page, flags=re.M):
            row = row.strip()
            assert row.startswith(('Reviewed', 'Partly reviewed', 'Beta')), \
                'a language row does not lead with its review status: %r' % row
            if not row.startswith('Beta'):
                assert re.match(r'(Partly r|R)eviewed as of \d+\.\d+ ', row), \
                    'a review is claimed without the release it was made '\
                    'against: %r' % row

    # ── the manual's own links ───────────────────────────────────────

    def test_internal_links_and_anchors_resolve(self):
        """Every .md link and #anchor between manual pages resolves.
        Moving prose between pages is exactly what breaks these, and
        nothing else notices until a reader clicks."""
        pages = sorted(f for f in os.listdir(DOCS_DIR) if f.endswith('.md'))
        anchors = {}
        for name in pages:
            text = _doc_text(name)
            anchors[name] = {_heading_anchor(h) for h in _headings(text)}

        broken = []
        for name in pages:
            for target in re.findall(r'\]\((?!https?:|mailto:)([^)\s]+)\)',
                                     _doc_text(name)):
                path, _, anchor = target.partition('#')
                page = name if path == '' else path
                if not page.endswith('.md'):
                    continue          # images and other assets
                if page not in anchors:
                    broken.append('%s -> %s (no such page)' % (name, target))
                elif anchor and anchor not in anchors[page]:
                    broken.append('%s -> %s (no such anchor)' % (name, target))
        assert not broken, 'broken manual links:\n  ' + '\n  '.join(broken)

    # ── the report's options ─────────────────────────────────────────
    # Three sources that must agree: what skin.conf DECLARES (with its
    # default), what the templates READ, and what the manual DOCUMENTS.
    # The disagreements are what matter, and each direction catches a
    # different bug -- an option read but never declared has no default
    # and silently breaks the page when a station omits it; an option
    # documented but neither declared nor read is a promise that does
    # nothing, which is the direction users report as a bug.

    # Read by the templates but deliberately NOT declared in skin.conf.
    # Every one is guarded with $Extras.has_key, so absence is a
    # supported state rather than a missing default:
    _UNDECLARED_BY_DESIGN = {
        # Commented out in skin.conf on purpose: with no setting, the
        # STATION's zone is auto-detected at report time, which is the
        # behaviour remote viewers of a public page want.
        'time_zone',
        # Optional overrides of the page heading and the HTML <title>;
        # absent, the skin composes both from the station's location.
        'title', 'meta_title',
    }

    # Declared in skin.conf but not a user-facing setting:
    _NOT_A_USER_OPTION = {
        # The version tag appended to the celestial.css and sky.js URLs
        # so browsers refetch them after an upgrade.  Bumped by the
        # release process, never by a station.
        'version',
    }

    # Documented as report options but not `[Extras]` keys at all:
    _CORE_REPORT_OPTIONS = {
        # WeeWX's own per-report option, merged from the lang file; it
        # belongs in the manual but is not this skin's to declare.
        'lang',
    }

    def _declared_options(self):
        """{option: default} from the shipped skin.conf's [Extras]."""
        path = os.path.join(REPO_ROOT, 'skins', 'Celestial', 'skin.conf')
        with open(path, encoding='utf-8') as f:
            body = f.read().split('[Extras]', 1)[1]
        body = re.split(r'^\[', body, flags=re.M)[0]
        out = {}
        for line in body.splitlines():
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$', s)
            if m:
                out[m.group(1)] = m.group(2).strip('\'"')
        return out

    def _read_options(self):
        """The $Extras keys the shipped templates actually consult."""
        found = set()
        for name in ('index.html.tmpl', 'realtime_updater.inc'):
            path = os.path.join(REPO_ROOT, 'skins', 'Celestial', name)
            with open(path, encoding='utf-8') as f:
                text = f.read()
            found.update(re.findall(r'\$Extras\.has_key\(\s*[\'"]([A-Za-z_]\w*)', text))
            found.update(re.findall(r'\$Extras\.([A-Za-z_]\w*)', text))
        return found - {'has_key'}

    def _documented_options(self):
        """{option: documented default} from the Configuration page: the
        sample [Extras] block, plus every option bullet."""
        page = _doc_text('configuration.md')
        sample = _block_containing(page, 'CelestialReport')
        # Only the [[[Extras]]] sub-block: the lines above it (HTML_ROOT,
        # enable, skin) are WeeWX's own report keys, not this skin's
        # options, and are shown for context.
        assert '[[[Extras]]]' in sample, 'sample config lost its [[[Extras]]]'
        extras = sample.split('[[[Extras]]]', 1)[1]
        documented = {}
        for line in extras.splitlines():
            m = re.match(r'^\s+([a-z_]+)\s*=\s*(.*?)\s*$', line)
            if m:
                documented[m.group(1)] = m.group(2).strip('\'"')
        for m in re.finditer(r'^- `([a-z_]+)`', page, re.M):
            documented.setdefault(m.group(1), None)
        for m in re.finditer(r'^- `([a-z_]+)` / `([a-z_]+)`', page, re.M):
            documented.setdefault(m.group(1), None)
            documented.setdefault(m.group(2), None)
        return documented

    def test_option_extractors_find_what_they_claim_to_find(self):
        """Landmarks and plausible sizes, so a pattern that stops
        matching fails loudly instead of passing empty."""
        declared, read, documented = (self._declared_options(),
                                      self._read_options(),
                                      self._documented_options())
        for landmark in ('loop_data_file', 'refresh_rate', 'expiration_time'):
            assert landmark in declared, landmark
            assert landmark in read, landmark
            assert landmark in documented, landmark
        assert len(declared) >= 5 and len(read) >= 6 and len(documented) >= 6

    def test_every_option_read_has_a_default_or_is_guarded(self):
        """An option the templates read but skin.conf never declares has
        no default -- unless its absence is a supported state."""
        undeclared = (self._read_options() - set(self._declared_options())
                      - self._UNDECLARED_BY_DESIGN)
        assert undeclared == set(), (
            'read by the skin but not declared in skin.conf, and not in '
            'the by-design exemption list: %s' % sorted(undeclared))

    def test_every_shipped_option_is_documented(self):
        undocumented = (set(self._declared_options())
                        - set(self._documented_options())
                        - self._NOT_A_USER_OPTION)
        assert undocumented == set(), (
            'shipped in skin.conf but missing from the Configuration '
            'page: %s' % sorted(undocumented))

    def test_no_option_is_documented_that_does_nothing(self):
        phantom = (set(self._documented_options())
                   - set(self._declared_options()) - self._read_options()
                   - self._CORE_REPORT_OPTIONS)
        assert phantom == set(), (
            'documented but neither declared nor read by the skin -- the '
            'manual promises an option that does nothing: %s' % sorted(phantom))

    def test_documented_defaults_match_the_shipped_ones(self):
        """The Configuration page's sample block is what a fresh install
        gets, so its values must be skin.conf's."""
        declared, documented = self._declared_options(), self._documented_options()
        wrong = {name: (value, declared[name])
                 for name, value in documented.items()
                 if value is not None and name in declared
                 and value != declared[name]}
        assert wrong == {}, (
            'documented default != shipped default (documented, shipped): %s'
            % wrong)

    # ── the manual's page furniture ──────────────────────────────────
    # Every page carries the same two-line header under its H1: the
    # in-body link to the full manual and to the GitHub project, then a
    # rule.  The links are there for a reason John cares about -- the
    # MANUAL ranks in search results and the repository does not, so
    # every page needs a body-text way back to the project; sidebar
    # chrome does not count, and neither does it exist for someone
    # reading the .md on github.com or in the release zip.  This is the
    # one kind of drift no content audit can see: identical furniture on
    # every page, until it silently isn't (weewx-skyfield's i18n page
    # was missing its rule from 1.12 until 2026-08-11).

    # Home states the same two destinations as just-the-docs buttons
    # instead of the prose line, so the backlink is present without
    # printing the same URL twice on one screen.  Pinned below rather
    # than merely exempted.
    _NO_LINK_LINE = {'index.md'}

    _MANUAL_URL = 'https://chaunceygardiner.github.io/weewx-celestial/'
    _PROJECT_URL = 'https://github.com/chaunceygardiner/weewx-celestial'
    _ISSUES_URL = 'https://github.com/chaunceygardiner/weewx-celestial/issues'

    def test_every_page_carries_the_manual_and_project_links(self):
        pages = sorted(f for f in os.listdir(DOCS_DIR) if f.endswith('.md'))
        assert len(pages) >= 10, 'only %d pages found' % len(pages)
        for name in pages:
            text = _doc_text(name)
            # Home IS the manual's front page; a link to itself would be
            # furniture without a destination.  Every other page carries
            # both, so a reader who arrives from a search result can get
            # to the whole manual and to the project.
            if name not in self._NO_LINK_LINE:
                assert self._MANUAL_URL in text, '%s: no link to the manual' % name
            assert self._PROJECT_URL in text, '%s: no link to the project' % name
            assert self._ISSUES_URL in text, '%s: no link to the issue tracker' % name

    def test_link_line_is_followed_by_a_blank_line_then_a_rule(self):
        """The blank line is load-bearing and is its own assertion: a
        `---` directly under the link line is not a missing rule, it is
        a setext heading -- kramdown turns the navigation furniture into
        an H2, which lands in the same heading space the link audit
        validates anchors against."""
        checked = 0
        for name in sorted(f for f in os.listdir(DOCS_DIR)
                           if f.endswith('.md') and f not in self._NO_LINK_LINE):
            lines = _doc_text(name).split('\n')
            idx = [i for i, l in enumerate(lines)
                   if l.startswith('[weewx-celestial manual]')]
            assert len(idx) == 1, '%s: expected one link line, found %d' % (name, len(idx))
            i = idx[0]
            assert lines[i - 2].startswith('# ') and lines[i - 1].strip() == '', (
                '%s: the link line belongs under the H1, one blank line down'
                % name)
            assert lines[i + 1].strip() == '', (
                '%s: no blank line under the link line -- `---` directly '
                'beneath it would make the link line a setext H2, not a rule'
                % name)
            assert lines[i + 2].strip() == '---', (
                '%s: the link line is not followed by a rule' % name)
            checked += 1
        assert checked >= 9, 'only %d pages checked for furniture' % checked

    def test_home_states_the_same_two_destinations(self):
        """Home's exemption from the link line is a different shape, not
        a missing backlink."""
        home = _doc_text('index.md')
        assert '](%s){: .btn' % self._PROJECT_URL in home, (
            'Home no longer offers the project as a button; either restore '
            'it or give Home the standard link line')
        assert self._MANUAL_URL in home or 'permalink: /' in home

    # ── the installer's stanza ───────────────────────────────────────
    # The Configuration page opens by printing the [[CelestialReport]]
    # stanza a fresh install writes.  That is a falsifiable claim about
    # a DIFFERENT file (install.py's config dict), and nothing else keeps
    # it true: skin.conf's defaults and the installer's are separate
    # sources that happen to agree today.  Credit to the weewx-loopdata
    # session, which found its own manual promising values its installer
    # does not write.

    def _installer_config_pairs(self):
        """install.py's config dict, flattened to leaf key/value pairs.
        Parsed with ast rather than imported: install.py imports weecfg
        at module scope, which a bare test run may not have."""
        import ast
        with open(os.path.join(REPO_ROOT, 'install.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        found = [node.value for node in ast.walk(tree)
                 if isinstance(node, ast.keyword) and node.arg == 'config']
        assert len(found) == 1, 'expected one config= in install.py, found %d' % len(found)
        config = ast.literal_eval(found[0])

        pairs = {}
        def flatten(d):
            for key, value in d.items():
                if isinstance(value, dict):
                    flatten(value)
                else:
                    assert key not in pairs, 'duplicate leaf key %r' % key
                    pairs[key] = value
        flatten(config)
        return pairs

    def _documented_stanza_pairs(self):
        """Every key = value in the Configuration page's sample stanza,
        at any nesting level -- the report's own keys included, unlike
        _documented_options, which is deliberately Extras-only."""
        sample = _block_containing(_doc_text('configuration.md'), 'CelestialReport')
        pairs = {}
        for line in sample.splitlines():
            m = re.match(r'^\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$', line)
            if m:
                pairs[m.group(1)] = m.group(2).strip('\'"')
        return pairs

    def test_installer_stanza_extractors_find_what_they_claim(self):
        shipped = self._installer_config_pairs()
        documented = self._documented_stanza_pairs()
        assert len(shipped) >= 7, 'install.py parsed to %d leaf pairs' % len(shipped)
        for landmark in ('HTML_ROOT', 'skin', 'loop_data_file', 'refresh_rate'):
            assert landmark in shipped, landmark
            assert landmark in documented, landmark

    def test_manual_prints_the_stanza_the_installer_writes(self):
        """Every key/value a fresh install writes appears verbatim in the
        Configuration page's sample, and the sample invents nothing."""
        shipped = self._installer_config_pairs()
        documented = self._documented_stanza_pairs()

        missing = {k: v for k, v in shipped.items() if k not in documented}
        assert missing == {}, (
            'the installer writes these, and the manual\'s sample stanza '
            'does not show them: %s' % missing)

        wrong = {k: (documented[k], str(v)) for k, v in shipped.items()
                 if k in documented and documented[k] != str(v)}
        assert wrong == {}, (
            'sample stanza disagrees with what the installer writes '
            '(documented, installed): %s' % wrong)

        invented = set(documented) - set(shipped)
        assert invented == set(), (
            'the sample stanza shows settings a fresh install does not '
            'write: %s' % sorted(invented))

    # ── absolute links to the published site ─────────────────────────
    # GitHub Pages serves what jekyll BUILDS: `installation.html`, not
    # `installation/index.html`.  So /installation.html is 200 and
    # /installation/ is 404, and a natural-looking trailing-slash URL in
    # the README is a dead link on the project's front page that no
    # between-pages link audit can see.  Credit to the weewx-skyfield
    # session, which shipped twelve of them and measured it.

    _SITE = 'https://chaunceygardiner.github.io/weewx-celestial/'

    def _absolute_site_links(self):
        """Every absolute link to one of these three published manuals,
        with the file it names."""
        sources = {'README.md': os.path.join(REPO_ROOT, 'README.md'),
                   'changes.txt': os.path.join(REPO_ROOT, 'changes.txt'),
                   'install.py': os.path.join(REPO_ROOT, 'install.py')}
        for name in sorted(os.listdir(DOCS_DIR)):
            if name.endswith('.md'):
                sources[name] = os.path.join(DOCS_DIR, name)
        found = []
        for name, path in sources.items():
            with open(path, encoding='utf-8') as f:
                text = f.read()
            for url in re.findall(
                    r'https://chaunceygardiner\.github\.io/[^\s)"\'<>]+', text):
                found.append((name, url.rstrip('.,')))
        return found

    def test_published_links_are_the_root_or_end_in_html(self):
        """A path that is neither the site root nor an .html file is the
        trailing-slash 404, or relies on Pages' extensionless fallback
        rather than a file that was built."""
        assert len(self._absolute_site_links()) >= 15, 'extractor found too few links'
        bad = []
        for name, url in self._absolute_site_links():
            path = url.split('github.io/', 1)[1]
            page = path.split('/', 1)[1] if '/' in path else ''
            if page == '' or url.endswith('.html'):
                continue
            bad.append('%s -> %s' % (name, url))
        assert not bad, (
            'links to a published manual must be the site root or end in '
            '.html; these will 404 or depend on a fallback:\n  '
            + '\n  '.join(bad))

    def test_links_to_our_own_manual_name_pages_that_exist(self):
        """An .html URL into celestial's own manual must correspond to a
        page in docs/ -- otherwise it is well-formed and still dead."""
        pages = {f[:-3] + '.html' for f in os.listdir(DOCS_DIR) if f.endswith('.md')}
        pages.add('index.html')
        missing = []
        for name, url in self._absolute_site_links():
            if not url.startswith(self._SITE) or not url.endswith('.html'):
                continue
            page = url[len(self._SITE):]
            if page not in pages:
                missing.append('%s -> %s (no docs/%s)'
                               % (name, url, page[:-5] + '.md'))
        assert not missing, 'dead links into our own manual:\n  ' + '\n  '.join(missing)

    def test_home_names_the_shipped_version(self):
        """Home tells a visitor which version the manual documents, and
        that claim is about celestial.py -- so it cannot be left behind
        by a release."""
        home = _doc_text('index.md')
        m = re.search(r'^This manual documents weewx-celestial \*\*([0-9.]+)\*\*',
                      home, re.M)
        assert m, 'Home no longer states which version it documents'
        assert m.group(1) == celestial.CELESTIAL_VERSION, (
            'Home says %s, the extension is %s'
            % (m.group(1), celestial.CELESTIAL_VERSION))

    def test_readme_offers_the_same_three_destinations_as_home(self):
        """The README is the project's front door for anyone arriving
        from GitHub, so it carries the manual, the download and the
        issue tracker up top -- the mirror of Home's three buttons.
        GitHub markdown cannot render buttons (no CSS), so the shape is
        a bold link row; what is pinned here is the DESTINATIONS."""
        with open(os.path.join(REPO_ROOT, 'README.md'), encoding='utf-8') as f:
            head = f.read().split('\n## ', 1)[0]   # above the first section
        for label, url in (
                ('the manual', self._MANUAL_URL),
                ('the release zip',
                 'https://github.com/chaunceygardiner/weewx-celestial/'
                 'releases/latest/download/weewx-celestial.zip'),
                ('the issue tracker', self._ISSUES_URL)):
            assert url in head, (
                'the README does not link %s above its first section' % label)
