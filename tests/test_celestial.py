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
        # The literal (non-constructed) keys the include reads.
        for literal in ('current.dateTime.raw', 'almanac.moon.phase',
                        'almanac.next_full_moon.unix_epoch.raw',
                        'almanac.next_new_moon.unix_epoch.raw'):
            assert "'%s'" % literal in include or '"%s"' % literal in include, literal
            keys.add(literal)
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
    """The install-time fields hint: weectl's configure() hook compares the
    station's [LoopData] [[Include]] fields line with what the page reads
    -- the bundled migrator run in memory as the oracle, [Skyfield]
    [[Satellites]] included -- and prints the migration commands when
    entries are missing.  A hint only: it never touches the configuration
    (configure always returns False) and never fails the install."""

    class _Printer:
        def __init__(self):
            self.lines = []

        def out(self, msg, level=1):
            self.lines.append(msg)

    def _engine(self, config):
        import types
        return types.SimpleNamespace(config_dict=config,
                                     printer=self._Printer(),
                                     dry_run=False,
                                     root_dict={'WEEWX_ROOT': '/wx'},
                                     config_path='/wx/weewx.conf')

    def _installer(self):
        return load_installer().CelestialInstaller()

    def test_hint_when_fields_missing(self):
        engine = self._engine(
            {'LoopData': {'Include': {'fields': ['current.outTemp']}}})
        assert self._installer().configure(engine) is False
        text = '\n'.join(engine.printer.lines)
        # 37 base entries plus 19 each for the default satellites (no
        # [Skyfield] section to follow), and the commands are concrete:
        # the engine's own BIN_DIR and config path, the running python.
        assert 'missing 75 entries' in text
        assert '--migrate-loopdata-fields' in text
        assert 'cd /wx/bin' in text
        assert '--config /wx/weewx.conf' in text
        assert sys.executable in text
        # The review command is a word-diff: the fields line is one long
        # comma-separated value, and a plain diff shows two unreadable lines.
        assert 'git diff --no-index --word-diff /wx/weewx.conf' in text

    def test_hint_counts_follow_satellites(self):
        engine = self._engine(
            {'Skyfield': {'Satellites': {'terra': '25994'}},
             'LoopData': {'Include': {'fields': ['current.outTemp']}}})
        assert self._installer().configure(engine) is False
        text = '\n'.join(engine.printer.lines)
        assert 'missing 56 entries' in text     # 37 base + 19 for terra

    def test_silent_when_complete_for_configured_satellites(self):
        """A line complete for the CONFIGURED set stays silent -- the
        absent installer defaults must not be nagged about."""
        complete, _ = celestial.migrate_loopdata_fields(
            ['current.outTemp'], satellites=['terra'])
        engine = self._engine(
            {'Skyfield': {'Satellites': {'terra': '25994'}},
             'LoopData': {'Include': {'fields': complete}}})
        assert self._installer().configure(engine) is False
        assert engine.printer.lines == []

    def test_renames_hinted(self):
        complete, _ = celestial.migrate_loopdata_fields([])
        engine = self._engine(
            {'LoopData': {'Include': {'fields': ['current.Sunrise.raw'] + complete}}})
        self._installer().configure(engine)
        text = '\n'.join(engine.printer.lines)
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
