"""
test_celestial.py

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Tests for weewx-celestial: the bundled Celestial skin (the live
Geocentric panel, the sky dome and the Next Visible Pass panel, rendered end to
end through Cheetah's errorCatcher), the page's field set and its
declaration to weewx-loopdata (the skin's own skin.conf, and the
satellite and comet groups the installer writes), the installer, and the
--add-satellite / --remove-satellite and --add-comet / --remove-comet
utilities.

Run with the WeeWX virtual environment's Python, from the root of this repo:
    /home/weewx/weewx-venv/bin/python -m pytest tests

The skin-render tests use the independent weewx-skyfield extension (the
installed copy or a sibling checkout) as the report almanac, exactly as
production does; they skip when it is not available.  The field-set
tests cross-check every declared entry against the sibling weewx-loopdata
checkout's almanac-field parser and declaration reader when that repo is
available.
"""

import contextlib
import inspect
import json
import logging
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

# WeeWX only began handing the report's [Almanac] section to the almanac in
# 5.3 (`texts=`); 5.2, this extension's stated minimum, has no such keyword
# and raises TypeError on the constructor.  Tests that assert TRANSLATED
# body names are therefore asserting a 5.3+ capability and must skip on 5.2
# rather than fail -- the page itself renders fine there, with capitalized
# English body names, which is what
# TestSampleSkinRenders::test_renders_on_weewx_5_2_without_texts pins.
WEEWX_HAS_ALMANAC_TEXTS = 'texts' in inspect.signature(
    weewx.almanac.Almanac.__init__).parameters
requires_almanac_texts = pytest.mark.skipif(
    not WEEWX_HAS_ALMANAC_TEXTS,
    reason='WeeWX 5.3+ required: 5.2 cannot carry the report [Almanac] '
           'body names (the page renders, in English)')

# Where the sibling weewx-loopdata checkout may be found (its parser is the
# oracle for the field-set tests' almanac grammar, and its declaration
# reader the oracle for how skin.conf and weewx.conf merge).
LOOPDATA_DIRS = [
    os.path.join(os.path.dirname(REPO_ROOT), 'weewx-loopdata', 'bin', 'user'),
    '/home/weewx/bin/user',
]

SKIN_DIR = os.path.join(REPO_ROOT, 'skins', 'Celestial')

# The report name the render harness generates the page under, and the
# key every served loop-data file carries: weewx-loopdata 7.0 writes each
# declaring report's fields under the REPORT's name, and the page unwraps
# its own.  $REPORT_NAME is a core tag on every WeeWX this extension
# supports (reportengine sets it on the skin dict; verified on the 5.2.0
# wheel), so the harness may supply it.
REPORT_NAME = 'CelestialReport'


def loop_file(record):
    """loop-data.txt as weewx-loopdata 7.0 writes it for this page: the
    flat record under the report's name."""
    return json.dumps({REPORT_NAME: record})


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


def _wcag_ratio(fg, bg):
    """Contrast ratio between two #rrggbb colors (WCAG relative
    luminance).  Used where a value has to be legible rather than merely
    correct -- the light plate's own choices, which no cross-repo pin
    covers."""
    def channel(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def luminance(color):
        color = color.lstrip('#')
        r, g, b = (channel(int(color[i:i + 2], 16)) for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def make_sky_page(texts=None, theme=None):
    """The real weewx-skyfield SkyPage for render tests (what the
    celestial_sky shim serves in production), built with the report's
    [Texts] the way the shim passes skin_dict.  `theme` is the report's
    own theme option, which SkyPage reads out of that same skin dict --
    the whole plumbing behind the light plate (8.3).  Skips when no
    weewx-skyfield is available."""
    load_wxskyfield()
    import wxskyfield_sky
    skin_dict = {}
    if texts:
        skin_dict['Texts'] = texts
    if theme is not None:
        skin_dict['theme'] = theme
    return wxskyfield_sky.SkyPage(skin_dict)


def rewindow_pass_chart(markup, rise, sset):
    """Move a rendered pass chart's OWN window (skyfield 2.3.2's
    data-rise/data-set on the track) to the given epochs.  The fixture
    pass is in June 2025; a browser test that wants the sweep to run must
    put the chart's window around its real clock, because renderPass
    judges the chart against these, not the feed.  `rise=None` STRIPS the
    window instead -- a pre-2.3.2 chart, for the fallback path.  Skips
    when the rendered chart carries no window (an older weewx-skyfield),
    where neither move nor strip would mean anything."""
    repl = (r'\1' if rise is None
            else r'\1data-rise="%d" data-set="%d" ' % (rise, sset))
    out, n = re.subn(r'(<g class="dome-track" data-body="[^"]+" )'
                     r'data-rise="\d+" data-set="\d+" ', repl, markup)
    if n == 0:
        if rise is None:
            return markup       # nothing to strip: already the state wanted
        pytest.skip('this weewx-skyfield emits no data-rise/data-set (pre-2.3.2)')
    return out


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

    def test_version_is_logged_once_per_process(self, monkeypatch, caplog):
        """With no service since 7.0, this is the extension's ONLY voice
        in the weewx log -- the first place anyone looks when a station
        misbehaves, and the first thing an issue report needs.  It names
        the version out of the skin that is actually rendering, at the
        first report that renders the page -- again when that version
        CHANGES (a skin upgraded under a running weewxd), never once per
        cycle (reports run every archive interval; this is
        identification, not a heartbeat).  A skin with no version logs
        nothing rather than something misleading."""
        import celestial_sky
        monkeypatch.setattr(celestial_sky, 'SkyPage', None)
        monkeypatch.setattr(celestial_sky, '_logged_version', None)

        class Obj:
            pass
        generator = Obj()
        generator.skin_dict = {'Extras': {'version': '9.9'}}
        sl = celestial_sky.CelestialSkyPage(generator)
        with caplog.at_level(logging.INFO, logger='celestial_sky'):
            sl.get_extension_list(None, None)
            sl.get_extension_list(None, None)
        lines = [r.getMessage() for r in caplog.records
                 if 'Celestial version' in r.getMessage()]
        assert lines == ['Celestial version is 9.9.']

        # An upgrade under a running weewxd DOES speak again: WeeWX
        # re-reads skin.conf every cycle, so the version it renders with
        # can change while this module stays the copy weewxd imported.
        generator.skin_dict = {'Extras': {'version': '9.10'}}
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='celestial_sky'):
            sl.get_extension_list(None, None)
            sl.get_extension_list(None, None)
        assert [r.getMessage() for r in caplog.records
                if 'Celestial version' in r.getMessage()] \
            == ['Celestial version is 9.10.']

        # A versionless skin dict is silent, and never raises: a search
        # list that throws takes the whole page down with it.
        monkeypatch.setattr(celestial_sky, '_logged_version', None)
        generator.skin_dict = {}
        caplog.clear()
        with caplog.at_level(logging.INFO, logger='celestial_sky'):
            assert sl.get_extension_list(None, None) == [{'sky_page': None}]
        assert [r.getMessage() for r in caplog.records
                if 'Celestial version' in r.getMessage()] == []

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
               sky_page=None, current=None):
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
            # The default carries no $current.interval.second, the shape
            # a pre-8.3.2 report hands the page: the wrapper's #try then
            # falls back to 300 s.  A test that cares about the fragment
            # set passes its own.
            'current': current or Obj(dateTime=Obj(raw=TIME_TS), interval=Obj(raw=5)),
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
            'REPORT_NAME': REPORT_NAME,
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
        # The station clock's pre-packet anchor, baked from the report's
        # own instant.  Asserted on the RENDERED value, never on the
        # template text: under #errorCatcher Echo a bad placeholder is
        # echoed as error prose instead of raising, so a broken bake
        # would ship a page whose clock never started.
        assert 'GEN_TS = %d;' % int(TIME_TS) in html
        # The header's "updated" stamp first-paints that same instant, in
        # the shape fmtHMS repaints it in (%H:%M:%S, station-local, the
        # chip-detail precedent) -- the page displays on its own, and the
        # first packet must not reformat what the report painted.  Noon
        # PDT on the solstice; asserted on the rendered value for the
        # same errorCatcher reason.  8.3.4 shipped this span empty (and a
        # live clock beside it that is gone: read from the station it was
        # this stamp shown twice).
        assert '<span id="last-update">12:00:00</span>' in html
        assert 'id="live-clock"' not in html
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

    def test_dome_fragment_survives_any_group_interval(self, wxskyfield_almanac):
        """$current.interval arrives in whatever unit the report's
        group_interval asks for, so a station carrying `group_interval =
        hour` reports a five-minute interval as 0.0833.  Read with .raw
        and int()ed, that is ZERO -- every slot's offset then fails the
        offset test and ALL TEN fragments render empty, with nothing in
        the log because nothing failed.  The open page keeps its
        generation-time sky for ever.  That is Jacques Terrettaz's issue
        #4, and it is why the templates read .second.raw.  Pinned for
        both templates, since they repeat the arithmetic."""

        class Val:
            """A $current.interval as WeeWX delivers it: .raw in the
            report's own unit, .second.raw always in seconds."""

            def __init__(self, raw, seconds):
                self.raw = raw
                self.second = type('S', (), {'raw': seconds})()

        # The second case is what WeeWX really hands a group_interval =
        # hour station: the conversion is floating point, so seconds come
        # back as 299.99988 and a truncating int() would cost the set a
        # slot (verified against weewx.units, not assumed).
        for label, interval in (('hours', Val(0.08333333, 300.0)),
                                ('hours, as converted', Val(0.0833333, 299.99988)),
                                ('minutes', Val(5.0, 300.0)),
                                ('seconds', Val(300.0, 300.0))):
            out = self.render_dome_fragment('dome-svg.txt.tmpl', {
                'almanac': wxskyfield_almanac,
                'sky_page': make_sky_page(),
                'current': type('C', (), {'interval': interval})(),
            })
            assert '<svg' in out, label
            assert 'data-dome-step="60"' in out, label
            assert 'data-dome-count="5"' in out, label

        # A nonsense interval falls back rather than emptying the set.
        out = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'almanac': wxskyfield_almanac,
            'sky_page': make_sky_page(),
            'current': type('C', (), {'interval': Val(0.0, 0.0)})(),
        })
        assert '<svg' in out
        assert 'data-dome-count="5"' in out

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

    def test_light_theme_paints_the_page_and_its_charts_on_paper(self, wxskyfield_almanac):
        """theme = light is the WHOLE page: the class the stylesheet's
        light plate hangs on, and the embedded dome rendered on
        skyfield's matching paper palette.  A night dome inside a light
        page (the LiveSeasons shape, correct there) is the one outcome
        this page must never produce, so the night plate's own gradient
        stop is asserted ABSENT rather than the paper one merely
        present."""
        html = self.render(wxskyfield_almanac,
                           sky_page=make_sky_page(theme='light'))
        assert '<html lang="en" class="theme-light">' in html
        low = html.lower()
        assert '#efece2' in low          # the paper dome's outer stop
        assert '#8a94a6' in low          # ... and its rim
        assert '#161f3d' not in low      # the night dome's first stop

    def test_dark_theme_is_the_default_and_unchanged(self, wxskyfield_almanac):
        """No theme option: the night page, exactly as through 8.2 --
        the upgrade is a drop-in and nobody's page moves."""
        html = self.render(wxskyfield_almanac, sky_page=make_sky_page())
        assert '<html lang="en" class="theme-dark">' in html
        low = html.lower()
        assert '#161f3d' in low
        assert '#efece2' not in low

    def test_auto_theme_follows_the_sun(self, wxskyfield_almanac):
        """theme = auto resolves at GENERATION time -- light while the
        sun is up, dark otherwise -- and the dome follows it, because
        both come from the same palette() call.  Noon and midnight on
        the same solstice day over Palo Alto."""
        sky_page = make_sky_page(theme='auto')
        noon = self.render(wxskyfield_almanac, sky_page=sky_page)
        assert '<html lang="en" class="theme-light">' in noon
        assert '#efece2' in noon.lower()
        midnight_alm = weewx.almanac.Almanac(
            TIME_TS + 12 * 3600, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
            formatter=weewx.units.get_default_formatter())
        night = self.render(midnight_alm, sky_page=sky_page)
        assert '<html lang="en" class="theme-dark">' in night
        assert '#161f3d' in night.lower()

    def test_theme_is_dark_without_a_capable_sky_page(self, wxskyfield_almanac):
        """The light plate is the paper the embedded charts are drawn
        on, and $sky_page is what draws them: with no skyfield the page
        stays dark rather than half-dressed.  Guarded, so an unusable
        sky_page can never cost the page itself (7.2's lesson)."""
        assert '<html lang="en" class="theme-dark">' in self.render(
            wxskyfield_almanac, sky_page=None)

    def test_unknown_theme_is_logged(self, wxskyfield_almanac, caplog):
        """A theme that is not dark, light or auto is a misconfigured
        report, and the page swallows the exception to stay whole -- so
        it must say so in the log, or the mistake is invisible for
        ever."""
        with caplog.at_level(logging.WARNING):
            self.render(wxskyfield_almanac,
                        sky_page=make_sky_page(theme='papyrus'))
        warnings = [r.getMessage() for r in caplog.records
                    if r.levelno >= logging.WARNING]
        assert any('theme' in m and 'dark, light and auto' in m
                   for m in warnings), warnings

    def test_a_good_theme_logs_nothing(self, wxskyfield_almanac, caplog):
        """... and a correctly configured report is silent, on every one
        of the three values."""
        for theme in ('dark', 'light', 'auto'):
            caplog.clear()
            with caplog.at_level(logging.WARNING):
                self.render(wxskyfield_almanac,
                            sky_page=make_sky_page(theme=theme))
            assert [r.getMessage() for r in caplog.records
                    if r.levelno >= logging.WARNING] == [], theme

    def test_old_skyfield_without_themes_is_quiet(self, wxskyfield_almanac, caplog):
        """A weewx-skyfield too old to have theme() is not a
        misconfiguration and must not be reported as one: there is no
        way to know whether anyone asked for a theme, and the page has
        always rendered dark there."""
        class NoThemeSkyPage:
            def dome_svg(self, alm, **kw):
                return ''

            def pass_chart_html(self, alm, **kw):
                return ''

        with caplog.at_level(logging.WARNING):
            html = self.render(wxskyfield_almanac, sky_page=NoThemeSkyPage())
        assert '<html lang="en" class="theme-dark">' in html
        assert [r.getMessage() for r in caplog.records
                if r.levelno >= logging.WARNING] == []

    def test_unknown_theme_costs_the_plate_not_the_panels(self, wxskyfield_almanac):
        """skyfield raises on an unknown theme -- deliberately, so a
        template author sees a typo.  Here that raise must cost only the
        plate: the page renders whole, on the night plate, dome and pass
        panel included.  (It would not, if the palette were a second
        $sky_page call inside the dome's own guard.)"""
        html = self.render(wxskyfield_almanac,
                           sky_page=make_sky_page(theme='papyrus'))
        assert '<html lang="en" class="theme-dark">' in html
        assert '#161f3d' in html.lower()      # the night dome, drawn
        assert 'domepanel' in html            # ... and not the skyhint

    def test_light_dome_fragment(self, wxskyfield_almanac):
        """The refetched dome fragment carries the page's palette too.
        This is the flicker trap: a fragment left on the default night
        palette would repaint the dome dark 60 seconds after a light
        page loaded, and again on every refetch."""
        out = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'almanac': wxskyfield_almanac,
            'sky_page': make_sky_page(theme='light')})
        assert '#efece2' in out.lower()
        assert '#161f3d' not in out.lower()

    def test_dome_fragment_declares_its_plate(self, wxskyfield_almanac):
        """Each backdrop says which plate it is drawn on.  A page wears
        the plate it was GENERATED with -- the charts carry their colors
        in their own markup -- but goes on refetching fragments, so on
        theme = auto the cycle that crosses sunrise would drop a paper
        dome into a night page and leave it there.  The stamp is what
        lets the javascript notice."""
        for theme, palette in (('light', 'light'), ('dark', 'night')):
            out = self.render_dome_fragment('dome-svg.txt.tmpl', {
                'almanac': wxskyfield_almanac,
                'sky_page': make_sky_page(theme=theme)})
            assert 'data-dome-palette="%s"' % palette in out, theme

    def test_updater_reloads_once_when_the_plate_flips(self):
        """The javascript half: compare the fetched backdrop's plate with
        the page's own, reload on a mismatch, and reload only ONCE -- a
        page whose plate keeps disagreeing (a cached copy, say) must wear
        one stale plate rather than reload for ever.  Source-pinned;
        there is no browser in CI."""
        js = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        assert re.search(r"var PAGE_PALETTE\s*=", js), 'the page plate is gone'
        assert "indexOf('theme-light')" in js
        guard = re.search(r"data-dome-palette.*?\n(.*?)\n\s*var m = ", js, re.S)
        assert guard is not None, 'the plate comparison moved'
        body = guard.group(1)
        assert 'PAGE_PALETTE' in body, body
        assert 'plateReloadTried' in body and 'markPlateReload' in body, body
        assert 'window.location.reload()' in body, body
        # In step again clears the guard, or the SECOND flip never
        # reloads (sunset works, the next sunrise does not).
        assert 'clearPlateReload()' in body, body
        # The guard must outlive the reload it bounds: an in-page flag is
        # reset by that very navigation, so a page served from cache
        # would reload every DOME_REFRESH seconds for ever.  Proven in a
        # browser (playwright, this release); pinned here because CI has
        # no browser.
        assert 'sessionStorage' in js
        assert re.search(r"var PLATE_KEY = 'celestial-plate-reload'", js)
        for fn in ('plateReloadTried', 'markPlateReload', 'clearPlateReload'):
            assert re.search(r'function %s\(' % fn, js), fn
        # Every sessionStorage touch is wrapped: it throws outright in
        # some privacy modes, and this must never cost the dome.
        for call in ('getItem', 'setItem', 'removeItem'):
            m = re.search(r'try \{\s*\n[^}]*sessionStorage\.%s' % call, js)
            assert m is not None, call
        # ... with the in-page flag as the fallback where it does throw
        assert re.search(r'var plateReloaded = false', js)

    def test_dome_fragment_palette_is_the_page_instant_not_the_slot(self):
        """On theme = auto the palette must be resolved against the
        PAGE's almanac, never the slot's re-bound one: a stagger slot
        minutes past sunrise would otherwise render paper inside a page
        that is still night, and flip the dome on refetch.  Pinned on
        the source, since the bug only shows within minutes of
        sunrise."""
        frag = open(os.path.join(SKIN_DIR, 'dome-svg-frag.inc')).read()
        call = re.search(r'\$sky_page\.dome_svg\((.*?)\)</div>', frag)
        assert call is not None, 'the dome_svg call moved'
        # The slot's re-bound almanac draws the sky; the palette does not
        # come from it.
        assert 'almanac_time=$frag_ts' in call.group(1)
        assert 'palette=$palette' in call.group(1)
        resolve = re.search(r'#set \$palette = .*?theme\((.*?)\)', frag)
        assert resolve is not None, 'the palette resolution moved'
        assert resolve.group(1) == '$almanac', resolve.group(1)

    def test_dome_fragment_stagger(self, wxskyfield_almanac):
        """The staggered slots: at a 5-minute interval slots 0-4 carry
        skies 60 s apart and slots 5-9 are honestly empty; at a 2-hour
        interval all ten slots emit at interval/10 spacing, so any
        archive interval gets full-cycle coverage.  The shifted almanac
        rides core WeeWX's $almanac(almanac_time=...) -- the sky must
        actually differ between slots."""
        from types import SimpleNamespace

        def render(name, interval_minutes):
            # .second.raw is what the templates read, and deliberately so:
            # .raw arrives in the report's own group_interval unit (see
            # test_dome_fragment_survives_any_group_interval).
            current = SimpleNamespace(
                interval=SimpleNamespace(
                    raw=interval_minutes,
                    second=SimpleNamespace(raw=interval_minutes * 60)))
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

    def test_dome_fragment_count_declares_what_it_emits(self, wxskyfield_almanac):
        """The emission gate is `offset < interval`, so a step that does
        not divide the archive interval writes one more fragment than
        floor division counts: a 350 s interval emits six 60 s slots and
        through 8.3.5 both wrappers declared five.  The generator paid for
        that sixth dome every cycle -- the most expensive thing this skin
        does -- and the walk, which clamps to count - 1, could never ask
        for it, so the last 50 s of every cycle showed the slot before.
        Declared == emitted, and the last slot askable, on intervals that
        do NOT divide: neither this repo nor liveseasons had such a
        station, which is how it survived four review rounds."""
        from types import SimpleNamespace

        def current(seconds):
            return SimpleNamespace(
                dateTime=SimpleNamespace(raw=TIME_TS),
                interval=SimpleNamespace(
                    raw=seconds / 60.0,
                    second=SimpleNamespace(raw=float(seconds))))

        def emitted(seconds):
            """The slots this interval actually writes, and what each one
            says about the set it belongs to."""
            out = []
            for k in range(10):
                name = 'dome-svg.txt.tmpl' if k == 0 else 'dome-svg-%d.txt.tmpl' % k
                frag = self.render_dome_fragment(name, {
                    'almanac': wxskyfield_almanac, 'sky_page': make_sky_page(),
                    'current': current(seconds)})
                if frag.strip():
                    out.append((k, frag))
            return out

        # 350 s / 60 s: six slots, covering 300 of the 350; the tail is
        # left to the last one by the walk's clamp, which is why that slot
        # has to be inside the declared count.
        for interval, step, want in ((350, 60, 6), (90, 60, 2), (150, 60, 3)):
            slots = emitted(interval)
            assert [k for k, _ in slots] == list(range(want)), interval
            for k, frag in slots:
                assert 'data-dome-count="%d"' % want in frag, (interval, k)
                assert 'data-dome-step="%d"' % step in frag, (interval, k)
                assert 'data-dome-interval="%d"' % interval in frag, (interval, k)
                assert 'data-dome-slot="%d"' % k in frag, (interval, k)
            # Askable: the highest slot written is the highest the walk
            # can name (domeWant clamps k to count - 1).
            assert slots[-1][0] == want - 1, interval
            # The page's own baked wrapper counts the same set -- it is
            # the one the open page reads its meta from.
            html = self.render(wxskyfield_almanac, sky_page=make_sky_page(),
                               current=current(interval))
            assert 'data-dome-count="%d"' % want in html, interval
            assert 'data-dome-interval="%d"' % interval in html, interval

        # A dividing interval is untouched: floor and ceil agree there,
        # which is every standard WeeWX interval and every one a Vantage
        # console can be set to.
        assert [k for k, _ in emitted(300)] == [0, 1, 2, 3, 4]
        assert 'data-dome-count="5"' in emitted(300)[0][1]

    def test_dome_slot_walk_is_monotonic(self):
        """The zigzag regression (caught in the NOAA-21 live capture): the
        fragment's data-dome-ts is its OWN depicted time, so the walk must
        recover the cycle base through data-dome-slot (base = ts -
        slot*step) before computing the next slot.  Walking from ts
        directly made the next slot RELATIVE to whichever slot was showing
        and the dome stepped 0,2,1,3,2 -- forward two minutes, back one --
        every cycle.  8.3.5 removed the cause: the base no longer comes
        from the fragment at all.  Pins that it has not come back, and
        keeps the simulation of both arithmetics as the record of what
        fragment-relative walking actually did."""
        src = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        # 8.3.5 settles the zigzag by removing its cause rather than
        # correcting for it: the cycle base is computed from the
        # STATION's clock against the archive interval, so no arithmetic
        # anywhere is relative to the fragment being displayed and the
        # walk cannot be made relative again by accident.  The old
        # de-relativizing expression must therefore be GONE, not present.
        assert re.search(r'Math\.floor\(\(serverNow\(\) - phase\)\s*/\s*m\.interval\)'
                         r'\s*\*\s*m\.interval\s*\+\s*phase', src)
        # ts - slot*step is back, but for the PHASE only -- a property of
        # the station's records, the same in a stale fragment as a fresh
        # one.  The cycle still comes from the clock, which is the half
        # that must never be read off the page.
        assert re.search(r'var phase = \(\(m\.ts - m\.slot \* m\.step\) % m\.interval'
                         r' \+ m\.interval\) % m\.interval;', src)
        # The backward guard: a late cycle answering an ask with the
        # previous cycle's file must not step the sky backward -- and
        # (8.3.5) a fragment stamped the same as the dome on the page IS
        # that dome, refused too, judged against the DOM at compare time.
        assert re.search(r'parseFloat\(m\[1\]\)\s*<=\s*cur\.ts', src)

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
                        > shown[0] + shown[1] * step):
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

    def test_dome_never_shows_a_sky_ahead_of_the_station(self):
        """The page must never display a backdrop depicting a time the
        station has not reached.  It could: the walk recovered the cycle
        base from the fragment it was HOLDING, and moments after the
        station rolls to a new cycle the page is still holding the
        previous one -- its clock (the last loop packet's stamp, delta
        behind the station) agrees it is still in the old cycle, so it
        names that cycle's late slot.  The filename carries no cycle
        identity, so the station answers with THAT slot of the cycle it
        now holds: a sky most of a cycle into the future, applied because
        it is newer, and then locked in by the same-or-older guard until
        the true time catches up to it.

        The fix takes the base from the station's own clock instead of
        from the fragment on the page -- report cycles are generated for
        the last archive record, so every base is a multiple of the
        archive interval -- which makes the wanted slot's depicted time
        at or behind serverNow() by construction, and the ask
        unmakeable.  Simulates both arithmetics across every fetch phase;
        the window is only (delta - lag) wide per cycle, so a single
        phase would miss it."""
        step, count, cycle, refresh = 60, 5, 300, 60

        def worst_lead(aligned, delta, lag, phase):
            # How far AHEAD of the station's true time the displayed
            # backdrop ever gets.  delta: how far the page's clock (the
            # last packet's stamp) trails the station.  lag: how long
            # after a cycle instant its fragments land on disk.
            shown, shown_slot, lead, behind = 0, 0, 0, 0
            for t in range(600 + phase, 5400, refresh):
                server_now = t - delta
                on_disk = max(0, ((t - lag) // cycle) * cycle)
                if aligned:
                    base = (server_now // cycle) * cycle
                    k = min(max((server_now - base) // step, 0), count - 1)
                    if base + k * step <= shown:
                        continue           # nothing owed; do not even ask
                else:
                    base = shown - shown_slot * step
                    k = (server_now - base) // step
                    k = k if 1 <= k < count else 0
                got = on_disk + k * step
                if got > shown and not (aligned and got > server_now):
                    # Newer than the sky on the page, and -- once the base
                    # comes from the station's clock -- not depicting a
                    # time that clock has not reached.  The ceiling is
                    # only safe alongside the want-gate above: a page
                    # whose clock is stale computes want == shown and
                    # never asks, so the legitimately-ahead answer to a
                    # slot-0 ask after a sleep cannot arise to be refused.
                    shown, shown_slot = got, k
                lead = max(lead, shown - t)
                if shown:                  # past the cold start
                    behind = max(behind, t - shown)
            return lead, behind

        # A GW1000-class station: 20 s between loop writes, fragments on
        # disk 10 s after the cycle instant.
        phases = range(0, refresh)
        fixed = [worst_lead(True, 20, 10, p) for p in phases]
        assert all(lead <= 0 for lead, _ in fixed)
        # ...and it stays LIVE: refusing everything would satisfy the line
        # above.  Two slots is the bound, not one -- once a cycle the
        # page declines the answer that ran ahead and waits for the new
        # cycle's slot 0 -- plus the clock's own lag and the fragments'
        # time to reach disk.  Behind by a slot beats ahead by four.
        assert all(behind <= 2 * step + 20 + 10 for _, behind in fixed)
        # The arithmetic it replaces really did run ahead, by most of a
        # cycle, so the regression this pins is real.
        assert max(lead for lead, _ in
                   (worst_lead(False, 20, 10, p) for p in phases)) >= 3 * step

    def test_hardware_logger_phase_does_not_freeze_the_dome(self):
        """Archive records are one interval apart, but not necessarily ON
        a multiple of it.  Software record generation computes them as
        int(t/interval)*interval, so the phase is zero by construction; a
        HARDWARE logger stamps them on its own local boundaries by its
        own clock, so they can sit at a constant offset -- a console in a
        half-hour UTC zone writing hourly records.  That is the case the
        phase read covers, and the only one it can: a remainder modulo
        the interval cannot see an offset of a whole interval and cannot
        undo one of any size, so a console clock out of true against
        weewxd's system time is a different fault with a different
        answer (the dome freezes and says so; see
        test_a_station_stamped_ahead_is_not_accused_of_writing_nothing).

        Assuming a zero phase names a slot too high by phase/step, so
        most replies come back stamped ahead of the page's clock and the
        ceiling refuses them: the page pays for a whole sky a minute and
        applies almost none of them, and the stagger this fragment set
        exists for is half lost.  (Not a freeze -- the clamp at the last
        slot means the clock does catch up to some asks -- so nothing on
        the page ever says anything is wrong.)  The phase is therefore
        read off the fragment (its own base, ts - slot*step) while the
        cycle still comes from the clock."""
        interval, step, count = 3600, 360, 10
        phase, delta, lag = 1800, 20, 10        # India, hourly records

        def run(phase_aware):
            shown, last_want, last_fetch = None, None, -10 ** 9
            fetched = applied = 0
            for t in range(4 * interval, 12 * interval, 60):
                server_now = t - delta
                if shown is None:               # the page as generated
                    shown = ((t // interval) * interval + phase) - interval
                if phase_aware:
                    base = ((server_now - phase) // interval) * interval + phase
                else:
                    base = (server_now // interval) * interval
                k = min(max((server_now - base) // step, 0), count - 1)
                want = base + k * step
                if want <= shown:
                    continue
                if want == last_want and t - last_fetch < 60:
                    continue
                fetched += 1
                last_want, last_fetch = want, t
                # The station answers the slot number out of the cycle it
                # holds, whose base carries the real phase.
                on_disk = ((t - lag - phase) // interval) * interval + phase
                got = on_disk + k * step
                if got > shown and got <= server_now:
                    shown, applied = got, applied + 1
            return applied, fetched

        # Phase-aware: every ask lands, one per slot the sky advances --
        # eight hourly cycles of ten slots, and not one wasted request.
        applied, fetched = run(True)
        assert applied == fetched, (applied, fetched)
        assert applied >= 8 * count, (applied, fetched)
        # Phase-blind: six times the traffic, almost all of it refused by
        # the ceiling, and the sky steps at about half the rate it should.
        # Nothing SAYS anything is wrong -- the dome does keep advancing,
        # so the frozen line never fires; it just costs a whole sky a
        # minute and quietly loses half the stagger.
        blind_applied, blind_fetched = run(False)
        assert blind_fetched > 5 * fetched, (blind_fetched, fetched)
        assert blind_applied < applied // 2, (blind_applied, applied)

    def test_late_cycle_does_not_storm_the_backdrop_fetch(self):
        """The wanted slot is checked on every loop packet, because the
        packet is the only thing that moves the clock -- so a want that
        goes UNMET repeats at the poll rate, not once a minute.  A
        station late writing a cycle the page's clock has already entered
        answers every ask with the previous cycle's file, refused as
        older, leaving the want unmet: unpaced, the page pulls a whole
        sky every refresh_rate seconds until the report lands.  So a
        repeat of the same want is paced at DOME_REFRESH while a want
        that has MOVED still goes at once."""
        step, count, cycle, rate, dome_refresh = 60, 5, 300, 2, 60

        def fetches(paced, lag):
            # Whole-sky requests in an hour.  lag: how long after a cycle
            # instant its fragments reach disk.
            shown, last_fetch, last_want, n = 0, -10 ** 9, 0, 0
            for t in range(600, 4200, rate):
                base = (t // cycle) * cycle
                k = min(max((t - base) // step, 0), count - 1)
                want = base + k * step
                if want <= shown:
                    continue
                if paced and want == last_want and t - last_fetch < dome_refresh:
                    continue
                n += 1
                last_fetch, last_want = t, want
                on_disk = max(0, ((t - lag) // cycle) * cycle)
                got = on_disk + k * step
                if got > shown and got <= t:
                    shown = got
            return n

        # One fetch per slot the sky advances, and not one more -- an hour
        # of 60 s slots is 60 requests -- whether the station is prompt or
        # more than half a cycle late.
        assert fetches(True, 10) == 3600 // step
        assert fetches(True, 200) == 3600 // step
        # Unpaced, the late station is answered with a fetch storm.
        assert fetches(False, 200) > 15 * fetches(True, 200)
        src = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        assert re.search(r'if \(\(want === null \|\| want\.ts === lastDomeWant\)'
                         r'\s*&& Date\.now\(\) / 1000 - lastDomeFetch < DOME_REFRESH\) \{',
                         src), 'the repeat-want pacing is gone'
        assert re.search(r'lastDomeWant = want === null \? 0 : want\.ts;', src)

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

    def test_pass_chart_states_its_own_window(self, wxskyfield_sat_almanac):
        """In-step pin against the sibling: the chart weewx-skyfield emits
        carries data-rise/data-set on the track, in exactly the shape
        readPassBase reads and rewindow_pass_chart rewrites -- integer
        epochs, on the dome-track element, after data-body.  Without this
        pin a sibling that reordered or reshaped the attributes would turn
        every 8.3.3 browser test into a silent skip while renderPass fell
        back to the feed's window in the field.  Skips only when the
        sibling is older than 2.3.2 (the fallback tier), never on shape."""
        from Cheetah.Template import Template
        wxskyfield, _ = load_wxskyfield()
        if tuple(int(x) for x in wxskyfield.WXSKYFIELD_VERSION.split('.')[:3]) < (2, 3, 2):
            pytest.skip('weewx-skyfield %s predates data-rise/data-set (2.3.2)'
                        % wxskyfield.WXSKYFIELD_VERSION)
        source = open(os.path.join(SKIN_DIR, 'pass-chart.txt.tmpl')).read()
        out = str(Template(source, searchList=[{
            'almanac': wxskyfield_sat_almanac, 'sky_page': make_sky_page()}]))
        m = re.search(r'<g class="dome-track" data-body="iss" '
                      r'data-rise="(\d+)" data-set="(\d+)" ', out)
        assert m, 'the track carries no data-rise/data-set in the expected shape'
        rise, sset = int(m.group(1)), int(m.group(2))
        nvp = wxskyfield_sat_almanac.iss.next_visible_pass
        assert rise == int(round(nvp.rise.raw)) and sset == int(round(nvp.set.raw))
        assert rise < sset
        # And the include reads exactly these two names off the track.
        src = open(os.path.join(SKIN_DIR, 'realtime_updater.inc'),
                   encoding='utf-8').read()
        assert "attrNum(track, 'data-rise')" in src
        assert "attrNum(track, 'data-set')" in src

    def test_page_reads_one_clock_and_it_is_the_stations(self):
        """8.3.5's rule, pinned where it can be enforced: the loop
        packet's own timestamp IS the page's time -- the instant every
        value in that packet was computed for -- and before the first
        packet the page's generation instant.  Nothing in between: 8.3.4
        carried the station clock forward on the browser's stopwatch,
        which matched no data on the page and stepped back by up to a
        poll whenever a packet arrived later than the one before; 8.3.3
        and earlier read the browser's calendar outright and needed a
        freshness test and a latch to police it.  The browser is asked
        only how long something took (a difference between two of its
        own readings, which no viewer's skew can color), never what time
        it is.

        Consequently nothing that reads the clock is repainted by a
        timer: the countdown chips, the satellite rosters and the pass
        verdict render on the packet that moved it, and the header
        clock is gone (read from the station it was the "updated" stamp
        shown twice).  The one-second tick survives for extrapolated
        MOTION -- the dial's bodies, the dome's marks, the pass chart's
        sweep, each on packetAge -- and for elapsed-time housekeeping.
        Same rule, same survivors as weewx-liveseasons 8.4.4.

        Structural rather than a browser run on purpose: the rule is
        about which names appear where.  The rendered-value half (GEN_TS
        and the baked "updated" stamp) is in test_renders_with_skyfield_almanac;
        the browser half (a viewer's clock half an hour wrong changes
        nothing) is test_viewer_clock_skew_changes_nothing_in_a_real_browser."""
        src = open(os.path.join(SKIN_DIR, 'realtime_updater.inc'),
                   encoding='utf-8').read()
        # THE clock: the packet's stamp, or the generation instant.
        assert re.search(r'function serverNow\(\) \{', src)
        assert re.search(r'return latestTs === 0 \? GEN_TS : latestTs;', src), \
            'serverNow is the packet stamp, or GEN_TS before the first packet'
        assert 'GEN_TS = $int($almanac.time_ts);' in src, \
            'GEN_TS must be baked from the report generation instant'
        # The stopwatch, the only way the browser clock is read: packetAge
        # (both readings the browser's own), and no other subtraction of
        # anything from Date.now() but another Date.now() reading.  Every
        # Date.now() in the file is either that stopwatch or a cache
        # buster; a browser reading may not be stored as the page's time.
        assert re.search(r'function packetAge\(\) \{', src)
        assert re.search(r'Date\.now\(\) / 1000 - latestRecvTs', src), \
            'packetAge must measure the packet age on the browser clock alone'
        for gone in ('PAGE_LOAD', 'stationNow', 'stationClock', 'feedFresh',
                     'STALE_PACKET', 'b.over'):
            assert gone not in src, '%s should be gone' % gone
        assert not re.search(r'nowTs\s*-\s*latestTs', src)
        assert not re.search(r'latestTs\s*-\s*nowTs', src)
        assert not re.search(r'Date\.now\(\)[^\n]*-[^\n]*latestTs', src)
        assert not re.search(r'latestTs[^\n]*-[^\n]*Date\.now\(\)', src)
        assert not re.search(r'GEN_TS \+ \(Date\.now', src), \
            'the pre-packet clock does not run: it is GEN_TS, full stop'
        assert not re.search(r"latestTs = \(typeof lastTs === 'number'\)", src), \
            'the browser clock must never be stored as the station time'
        assert re.search(r'latestTs = lastTs;', src)
        # The four extrapolation sites all take the stopwatch reading.
        assert len(re.findall(r'var dt = packetAge\(\);', src)) == 4, \
            'the dial, dome, satellites and pass sweep all extrapolate on packetAge'
        # The consumers of an absolute instant all take the station's:
        # the chips and the satellite rosters open on serverNow, the pass
        # verdict reads it, the backdrop's staleness and the frozen
        # line's "from" time read it, and the slot walk reads it three
        # times -- the cycle base, the slot within it, and the ceiling
        # that refuses a fragment depicting a time the station has not
        # reached.  Eight call sites, no other clock anywhere.
        for fn in ('renderCountdown', 'renderSatRosters'):
            assert re.search(r'function %s\(\) \{' % fn, src), fn
        assert len(re.findall(r'var nowTs = serverNow\(\);', src)) == 2
        assert re.search(r'function renderPass\(\) \{', src)
        assert re.search(r'var now = serverNow\(\);', src)
        assert re.search(r'function domeStaleFor\(\) \{', src), \
            'the backdrop is judged on the page clock, no browser instant passed in'
        assert re.search(r'var over = \(serverNow\(\) - m\.ts\)', src)
        assert re.search(r'fmtBackdropWhen\(domeFragMeta\(\)\.ts, serverNow\(\)\)', src)
        assert re.search(r'var base = Math\.floor\(\(serverNow\(\) - phase\) / m\.interval\)'
                         r' \* m\.interval \+ phase;', src)
        assert re.search(r'var k = Math\.floor\(\(serverNow\(\) - base\) / m\.step\);', src)
        assert re.search(r'parseFloat\(m\[1\]\) > serverNow\(\)', src), \
            'the ceiling that refuses a sky the station has not reached is gone'
        # Counted over code only: the comments legitimately name the
        # function while explaining what reads it and why.
        assert len([l for l in src.split('\n') if 'serverNow()' in l
                    and not l.lstrip().startswith('//')]) == 8 + 1, \
            'eight serverNow call sites plus the definition; a new one needs a reason here'
        # No timer drives a clock reader.  localTick paints motion and
        # housekeeping only; the chips, rosters and "updated" stamp
        # render in the packet handler.
        # Code only -- the comments legitimately name what left.
        def code(block):
            return '\n'.join(l for l in block.split('\n') if not l.lstrip().startswith('//'))
        tick = code(src[src.index('function localTick() {'):src.index('function updateCurrent() {')])
        for reader in ('renderCountdown', 'renderSatRosters', 'live-clock',
                       'serverNow', 'last-update'):
            assert reader not in tick, '%s must not run on the tick' % reader
        for motion in ('renderGeo()', 'renderDome(nowTs)', 'renderPass()',
                       'updateDomeStale(nowTs)', 'domeWake()'):
            assert motion in tick, motion
        onload = src[src.index('function updateCurrent() {'):src.index('xhttp.onerror = function() {', src.index('function updateCurrent() {'))]
        for reader in ('renderPacket(nowTs);',
                       'setHtml("last-update", fmtHMS(lastTs));'):
            assert reader in onload, reader
        # ...and the five renders only on a NEW packet: a dead feed whose
        # last file is served again on every poll moves nothing, so
        # nothing is painted; the badge and the stamp stay outside the
        # gate, since the age they report goes on growing.
        # The backdrop check rides in the gate with them: the packet is
        # the only thing that moves the clock, so it is the only thing
        # that can change which slot the sky should be showing.  Nearly
        # every one of these returns at refreshDome's want-gate without
        # a request.
        gate = re.search(r'if \(latestTs !== prevTs\) \{\s*if \(document\.readyState === \'loading\'\) \{\s*renderWanted = true;[^\n]*\s*\}'
                         r'\s*refreshDome\(\);'
                         r'\s*renderPacket\(nowTs\);\s*\}', code(onload))
        assert gate is not None, 'the poll-side renders are not gated on a new packet'
        gate_at = onload.index("if (latestTs !== prevTs) {\n          if (document.readyState")
        assert 'setHtml("live-label"' in onload[:gate_at]
        assert 'setHtml("last-update"' in onload[:gate_at]
        # A first packet that lands while the page is still parsing leaves
        # a flag, and the load handler re-runs the five renders once on
        # `latest`: the two packet-only paints (chips, rosters) would
        # otherwise no-op on ids not yet in the DOM and, on a re-served
        # dead feed, never repaint.
        assert re.search(r"if \(document\.readyState === 'loading'\) \{\s*renderWanted = true;", code(onload))
        # The five paints live in renderPacket, called from both sites --
        # the list drifted apart in two copies once already -- and the
        # load handler's call is GUARDED: addLoadEvent chains handlers
        # with no try of its own, and this one runs before the backdrop's
        # deferred refetch.
        assert re.search(r'function renderPacket\(nowTs\) \{(?:\s*//[^\n]*\n)*'
                         r'\s*renderCountdown\(\);\s*renderSatRosters\(\);'
                         r'\s*renderGeo\(\);\s*renderDome\(nowTs\);\s*renderPass\(\);\s*\}',
                         src), 'the five packet paints are not in one place'
        assert re.search(r'addLoadEvent\(function\(\) \{\s*if \(renderWanted && latest !== null\) \{\s*renderWanted = false;'
                         r'\s*try \{\s*renderPacket\(Date\.now\(\) / 1000\);\s*\} catch',
                         code(src)), 'the load-time re-render of a mid-parse first packet is gone or unguarded'
        # The pass chart before a packet: untouched, and no load-time
        # render reaching for it (a page opened after the set shows the
        # chart as drawn until the first packet -- John, 2026-08-16).
        assert 'DOMContentLoaded' not in src
        assert re.search(r'if \(latest === null\) \{\n(\s*//[^\n]*\n)+\s*return;\n\s*\}\n\s*// The window the chart is judged against', src), \
            'pre-packet renderPass returns without touching the chart'
        # The "updated" stamp repaints in the template's own shape (24-hour
        # HH:MM:SS, en-GB hour12 off, the fmtHM precedent), so the first
        # packet never reformats the first paint.
        assert re.search(r"function fmtHMS\(ts\) \{[^}]*'en-GB'[^}]*hour12: false", src, re.S)
        # A record with no station timestamp is dropped whole -- it can
        # never become the clock's anchor, as it did through 8.3.3.  (A
        # 2026-08-17 ruling: celestial keeps this where liveseasons
        # adopts such a record silently -- celestial serves other
        # people's stations, and its badge must name a misconfiguration.)
        assert re.search(r"if \(typeof lastTs !== 'number'\) \{", src)
        assert re.search(r'console\.log\(.loop record has no '
                         r'current\.dateTime\.raw; ignored.\)', src)
        # The LIVE badge's age is two same-clock terms, never a crossing:
        # how stale the record already was when the page found it (its
        # station time against the page's, GEN_TS) plus how long since a
        # fresh one arrived here (browser against browser).  Without the
        # first term the badge calls an hour-old re-served file LIVE to
        # anyone who has just loaded the page.
        assert re.search(r'var age = Math\.round\(Math\.max\(0, GEN_TS - latestTs\)\s*'
                         r'\+ \(nowTs - latestRecvTs\)\);', src)

    def test_light_pass_chart_fragment(self, wxskyfield_sat_almanac):
        """The Next Visible Pass chart follows the page's plate too --
        the other refetched fragment, the same flicker trap (it
        refetches every 300 s)."""
        from Cheetah.Template import Template
        source = open(os.path.join(SKIN_DIR, 'pass-chart.txt.tmpl')).read()
        out = str(Template(source, searchList=[{
            'almanac': wxskyfield_sat_almanac,
            'sky_page': make_sky_page(theme='light')}]))
        assert '<svg' in out
        assert '#efece2' in out.lower()
        assert '#161f3d' not in out.lower()

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
        PAGE_FIELDS exactly -- the skin consumes the whole
        page field set and nothing else."""
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
        assert 'almanac.next_eclipse_type' not in celestial.PAGE_FIELDS
        # The satellite layer is DYNAMIC: SAT_NAMES is generated from
        # skyfield 2.0's public $sky_page.satellite_names() (the template
        # builds the roster rows from the same enumeration), and the
        # javascript composes each satellite's keys from the pinned
        # suffix set below.  PAGE_FIELDS therefore carries the
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
        # composed from the suffix set below.  PAGE_FIELDS
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
        assert keys == set(celestial.PAGE_FIELDS)
        # The pre-7.6 unpinned moon keys survive as read fallbacks, and
        # the pass times, duration and peak altitude keep bare-.raw
        # fallbacks likewise: the skin's own declaration is pinned, but a
        # group of your own in the report's stanza that overrides one of
        # the skin's with the bare spellings still drives the page.
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
        import re as relib
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
        # The packets carry the BROWSER's clock, not the fixture's, while
        # their astronomy stays the fixture's.  A real station's feed and
        # the machine reading it agree on the time; this harness would
        # otherwise present a feed a year stale, and the page treats a
        # feed more than EXTRAP_MAX behind as dead -- correctly -- and
        # puts the dome's marks back where the backdrop drew them.  The
        # embedded backdrop is restamped below for the same reason.
        wall = int(time.time())
        packets = []
        for i, ts in enumerate((TIME_TS, TIME_TS + 2, TIME_TS + 4)):
            alm = weewx.almanac.Almanac(ts, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            r = {'current.dateTime.raw': wall + 2 * i,
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
            packets.append(loop_file(r).encode())

        html = self.render(wxskyfield_sat_almanac, sky_page=make_sky_page())
        html = relib.sub(r'data-dome-ts="\d+"', 'data-dome-ts="%d"' % wall,
                         html, count=1)
        (tmp_path / 'index.html').write_text(html)
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
            "        'passdot': page.get_attribute(\n"
            "            '#pass-chart g.dome-body[data-body=iss]', 'display'),\n"
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
        # morning, June 2025) and its featured dot was NOT swept.  Judged
        # by the chart's OWN data-rise/data-set against the browser's real
        # clock that pass is long over, so the dot is hidden -- the
        # load-after-set case, a page opened after the pass ended and
        # before the next chart arrived, which 8.3.3 fixes by reading the
        # chart's window rather than remembering whether it swept.
        assert out['passchart'] == 1
        assert '03:11' in out['passwhen']
        assert out['passnudged'] == 0
        if re.search(r'<g class="dome-track"[^>]* data-set="\d+"', html):
            assert out['passdot'] == 'none'
        else:
            # A pre-2.3.2 skyfield's chart states no window: the feed's
            # governs, and it too is long past, so the chart stands as
            # drawn -- the documented fallback.
            assert out['passdot'] is None
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
        html = self.render(wxskyfield_sat_almanac, sky_page=sky_page)
        # Everything here is staged against the page's BAKED dome stamp,
        # never wall-clock: the slot the page asks for follows from its
        # own clock (the loop packet's stamp) against the archive
        # interval, so a packet stamped `int(time.time())` made the asked
        # slot depend on the minute the suite happened to run in -- and
        # the assertion below could then only say "some fragment", which
        # a walk regressed to always naming slot 0 would satisfy.  Three
        # 60 s slots past the cycle base the page was generated for: the
        # page must ask for slot 3, every run.
        PACKET_TS = TIME_TS + 3 * 60
        # The pass chart's featured dot must be ON the chart to be tapped:
        # judged by the chart's own window (skyfield 2.3.2) against the
        # page clock, the June 2025 fixture pass is long over and the dot
        # hidden, so the window is put a day AHEAD -- the chart then
        # stands as drawn, which is the tappable state.
        far = TIME_TS + 86400
        html = rewindow_pass_chart(html, far, far + 600)
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())
        # The fragment refreshDome swaps in when the fast-forwarded minute
        # arrives: the same dome re-rendered, under a fresh wrapper
        # identity.  The dome/pass chip machinery is independent of loop
        # data (the swap dismissal must be too); only the dial's titles
        # below need the packet.
        # The staged timestamps must be NEWER than the rendered page's
        # (TIME_TS) and no newer than the page's CLOCK: the backward guard
        # rejects an older sky and the ceiling refuses one the station has
        # not reached.  TWO of them, because the page refetches once when
        # its first loop packet lands (8.3.5; at load through 8.3.4): the
        # first lands then, and the SECOND is the one the fast-forwarded
        # minute brings -- which is the swap whose chip-dismissal is under
        # test.  Each describes itself exactly as a real fragment does, so
        # the walk goes on working off the sky it has applied.
        def staged(ts, slot):
            return ('<div class="domefrag" data-dome-ts="%d" '
                    'data-dome-slot="%d" data-dome-step="60" '
                    'data-dome-count="5" data-dome-interval="300">%s</div>'
                    % (ts, slot, str(sky_page.dome_svg(wxskyfield_sat_almanac))))
        # The first answer is a slot behind the ask -- a station late
        # writing the cycle, and the everyday reason a want goes unmet --
        # so the second fetch has somewhere to move to.
        domefrags = [staged(PACKET_TS - 60, 2), staged(PACKET_TS, 3)]
        assert '<svg' in domefrags[0]
        fetched = {'n': 0}
        # One loop packet with known mars numbers: the dial's marks and
        # their <title>s exist only once a packet arrives, and a single
        # packet derives no rates, so the title holds exactly these values.
        (tmp_path / 'gauge-data').mkdir()
        (tmp_path / 'gauge-data' / 'loop-data.txt').write_text(loop_file({
            'current.dateTime.raw': PACKET_TS,
            'almanac.mars.az': 120.0,
            'almanac.mars.alt': 30.0,
            'almanac.mars.earth_distance': 1.66}))

        requested = []

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                # Any slot: the page asks for the one its station's clock
                # names (8.3.5), and this feed runs on the real clock, so
                # which slot that is depends on when the suite is run.
                if self.path.startswith('/dome-svg'):
                    requested.append(self.path.split('?')[0])
                    body = domefrags[min(fetched['n'],
                                         len(domefrags) - 1)].encode()
                    fetched['n'] += 1
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return super().do_GET()

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
        # replaced the rendered one) and dismissed the open chip.  The
        # slot is the one the station's clock names, asserted by number:
        # 8.3.5 stopped spending a request on slot 0, the sky the page
        # already has, before the first packet had said what time it was,
        # and this is the walk saying so out loud.
        assert [r for r in requested if r.startswith('/dome-svg')] == \
            ['/dome-svg-3.txt', '/dome-svg-3.txt'], requested
        assert out['swapped_dome_ts'] == str(PACKET_TS)
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
        # The page is rendered for the fixture instant while this test's
        # packets carry the browser's real clock, and the include judges
        # the backdrop's age against the feed's clock: left alone, the
        # embedded backdrop would read a year stale and the dome would
        # freeze (see the staleness test below).  Stamping it with the
        # feed's own time removes a mismatch the harness invents -- in
        # production the page and the packets come from one station.
        html = relib.sub(r'data-dome-ts="\d+"',
                         'data-dome-ts="%d"' % int(time.time()), html, count=1)
        # Likewise the chart's OWN window (skyfield 2.3.2's data-rise /
        # data-set): the sweep runs only inside it, so it is put around
        # the browser's clock like the feed's window below.
        html = rewindow_pass_chart(html, int(time.time()) - 60,
                                   int(time.time()) + 600)
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
            return loop_file({
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

    def test_pass_sweep_dot_hides_when_the_pass_ends_in_a_real_browser(
            self, wxskyfield_sat_almanac, tmp_path):
        """8.3.3: when the pass ENDS the sweeping dot leaves the chart; it
        never jumps back up the arc it just rode.  8.0 through 8.3.2 put
        the dot back at its generated position at that instant -- the
        culmination, MID-ARC -- under a header still naming the finished
        pass, for up to CHART_REFRESH seconds (weewx-loopdata's NOAA-21
        capture of 2026-08-15, frame f0498 at the 02:58:35 set instant).
        The cause was judging the chart against the FEED's next_visible_pass,
        which rolls to the following pass moments after set; the fix
        judges it against the chart's OWN window, skyfield 2.3.2's
        data-rise/data-set on the track, so nothing has to be remembered.

        The chart's window is put around the browser's real clock -- in
        progress at load, ending a few seconds later -- and the feed lies
        the satellite overhead, then rolls to the following pass exactly as
        loopdata's event expiry does.  Proven: the sweep engages, the dot
        and its label hide at the set and stay hidden through the roll; a
        refetch that re-serves the SAME finished chart (the report has not
        rerun) hides it again with nothing carried over; and a page LOADED
        after the set -- the case no memory could reach -- comes up hidden
        on its first packet.  Also (8.4) that STAYING hidden is free:
        the ticks past the set write no attributes at all.  Skips when
        the playwright env is absent."""
        import http.server
        import json as jsonlib
        import re as relib
        import socketserver
        import subprocess
        import threading
        from Cheetah.Template import Template

        pwenv = os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                             'tools', 'pwenv', 'bin', 'python')
        if not os.path.exists(pwenv):
            pytest.skip('the weewx-skyfield tools/pwenv playwright env is not available')

        sky_page = make_sky_page()
        html = self.render(wxskyfield_sat_almanac, sky_page=sky_page)
        # The refetched fragment is the REAL fragment template's output --
        # what production serves -- re-windowed identically below, so a
        # refetch brings back the same finished chart.
        frag = str(Template(open(os.path.join(SKIN_DIR, 'pass-chart.txt.tmpl')).read(),
                            searchList=[{'almanac': wxskyfield_sat_almanac,
                                         'sky_page': sky_page}]))
        # The chart's own window -- in progress now, over in a few
        # seconds -- is anchored to the browser's FIRST REQUEST for the
        # page, at serve time, so nothing that precedes it (a fresh
        # python, chromium's launch) can eat the margin: the handler
        # re-windows index.html and the fragment when first asked for
        # them.  A pre-2.3.2 sibling skips here, as everywhere.
        if not re.search(r'<g class="dome-track"[^>]* data-set="\d+"', html):
            pytest.skip('this weewx-skyfield emits no data-rise/data-set (pre-2.3.2)')
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())
        win = {}

        def windowed(markup):
            if not win:
                t0 = int(time.time())
                win['rise'], win['set'] = t0 - 60, t0 + 30
                win['t0'] = t0
            out = relib.sub(r'data-dome-ts="\d+"', 'data-dome-ts="%d"' % win['t0'],
                            markup, count=1)
            return rewindow_pass_chart(out, win['rise'], win['set'])

        # The generated dot's position: what the mark must NOT snap back
        # to once the pass is over.
        m = relib.search(r'<g class="dome-body" data-body="iss" data-sunlit="\d">'
                         r'<circle cx="([0-9.]+)" cy="([0-9.]+)"', html)
        assert m is not None
        gen_cx = m.group(1)

        state = {'n': 0, 'charts': 0}

        def packet():
            # The satellite overhead throughout; the feed's window in
            # progress for the first polls, then rolled to the following
            # pass an hour out (loopdata's event expiry) -- which the
            # chart's own window makes irrelevant, and the test proves so.
            i = state['n']
            now = time.time()
            chart_rise, chart_set = win.get('rise', now - 60), win.get('set', now + 30)
            rolled = now >= chart_set
            return loop_file({
                'current.dateTime.raw': now,
                'almanac.sun.alt': -30.0,
                'almanac.iss.az': 120.0 + 0.5 * i,
                'almanac.iss.alt': 45.0 - 0.5 * i,
                'almanac.iss.sunlit': True,
                'almanac.iss.label': 'ISS',
                'almanac.iss.next_visible_pass.rise.unix_epoch.raw':
                    chart_rise + (3600 if rolled else 0),
                'almanac.iss.next_visible_pass.set.unix_epoch.raw':
                    chart_set + (3600 if rolled else 0),
            }).encode()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body = packet()
                    state['n'] += 1
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.startswith('/pass-chart.txt'):
                    state['charts'] += 1
                    self._text(windowed(frag))
                    return
                if self.path.split('?')[0] == '/index.html':
                    self._text(windowed(html))
                    return
                return super().do_GET()

            def _text(self, text):
                body = text.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

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
            "G = '#pass-chart g.dome-body[data-body=iss]'\n"
            'HIDDEN = """() => {\n'
            "  var g = document.querySelector('\"\"\" + G + \"\"\"');\n"
            "  var t = document.querySelector('#pass-chart text[data-body=iss]');\n"
            "  return g !== null && g.getAttribute('display') === 'none' &&\n"
            "         (t === null || t.getAttribute('display') === 'none');\n"
            '}"""\n'
            'OBSERVE = """() => {\n'
            '  window.__muts = 0;\n'
            '  var els = [document.querySelector(\'"""  + G + """\'),\n'
            "             document.querySelector('#pass-chart text[data-body=iss]')];\n"
            '  window.__obs = new MutationObserver(function(rs) {\n'
            '    window.__muts += rs.length; });\n'
            '  els.forEach(function(el) {\n'
            "    if (el !== null) { window.__obs.observe(el, {attributes: true}); } });\n"
            '}"""\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    page = browser.new_page()\n'
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            "    page.goto('http://127.0.0.1:%(port)d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            "    # The chart's own set, read where the page reads it.\n"
            '    CHART_SET = float(page.evaluate("""() =>\n'
            "      document.querySelector('#pass-chart g.dome-track').getAttribute('data-set')\"\"\"))\n"
            '    # In the window: the sweep engages.\n'
            "    page.wait_for_selector(G + '[transform]', timeout=15000)\n"
            '    # The set instant: dot and label hide -- and stay hidden\n'
            '    # once the feed rolls (the roll follows the set in the\n'
            "    # handler; the roll's arrival is awaited below).\n"
            '    page.wait_for_function(HIDDEN, timeout=35000)\n'
            '    page.wait_for_function("""() => latest !== null &&\n'
            "      latest['almanac.iss.next_visible_pass.rise.unix_epoch.raw'] > \"\"\" + str(CHART_SET),\n"
            '      timeout=15000)\n'
            '    page.wait_for_timeout(1500)      # one localTick after the roll\n'
            '    # Past the set, renderPass hides the mark on every tick:\n'
            '    # hiding what is already hidden must write NOTHING.\n'
            '    page.evaluate(OBSERVE)\n'
            '    page.wait_for_timeout(5000)      # five localTicks\n'
            "    out = {'errors': errors,\n"
            "           'muts': page.evaluate('() => window.__muts'),\n"
            "           'display': page.get_attribute(G, 'display'),\n"
            "           'cx': page.get_attribute(G + ' circle', 'cx')}\n"
            '    # A refetch of the unchanged chart: the swapped-in chart is\n'
            '    # judged on its own window and comes up hidden at once.\n'
            "    page.evaluate('() => { window.__g0 = passBase.g; }')\n"
            "    page.evaluate('refreshPass()')\n"
            "    page.wait_for_function('() => passBase !== null && passBase.g !== window.__g0',\n"
            '                           timeout=10000)\n'
            "    out['display_after_refetch'] = page.get_attribute(G, 'display')\n"
            "    out['transform_after_refetch'] = page.get_attribute(G, 'transform')\n"
            "    out['cx_after_refetch'] = page.get_attribute(G + ' circle', 'cx')\n"
            '    # A page LOADED after the set: hidden on its first packet.\n'
            "    page.goto('http://127.0.0.1:%(port)d/index.html')\n"
            '    page.wait_for_function(HIDDEN, timeout=15000)\n'
            "    out['transform_after_reload'] = page.get_attribute(G, 'transform')\n"
            '    browser.close()\n'
            'print(json.dumps(out))\n'
            % {'port': port})
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        # Hidden through the set and the roll; the circle itself never
        # rewritten -- the mark hides, it is not re-placed.
        assert out['display'] == 'none'
        # ...and staying hidden is free: five seconds of ticks past the
        # set write not one attribute.  Through 8.3.5 setShown wrote
        # display="none" unconditionally, so the dot group and its label
        # took two mutations a second until the next chart refetch --
        # the asDrawn latch's twin, on the branch that latch cannot
        # reach (hidden is deliberately not the drawn state).
        assert out['muts'] == 0, out['muts']
        assert out['cx'] == gen_cx
        # The refetch really happened, and the fresh chart -- no transform
        # yet, nothing carried over -- is hidden on its own window.
        assert state['charts'] >= 1, 'the chart was never refetched'
        assert out['display_after_refetch'] == 'none'
        assert out['transform_after_refetch'] is None
        assert out['cx_after_refetch'] == gen_cx
        # And a page that was not watching comes up hidden too.
        assert out['transform_after_reload'] is None

    def test_chart_standing_as_drawn_before_a_pass_costs_nothing_in_a_real_browser(
            self, wxskyfield_sat_almanac, tmp_path):
        """The other end of the window from the churn above.  Through the
        hours before a pass rises renderPass has nothing to sweep, so it
        restores the chart to the state the station drew it in -- and did
        so on every one-second tick, rewriting the same attributes to the
        same values for hours on a chart nothing had touched.  8.3.5 put
        the asDrawn latch in front of that; 8.4 pins it, because the
        fix had no test of its own on this side (liveseasons measured it,
        celestial took it on trust).

        The chart's window is moved an hour ahead of the page's clock, a
        packet lands so renderPass runs at all, and every attribute write
        on the mark -- group, label and the dot circle whose fill/stroke
        pair passDotLit rewrites -- is counted across five ticks.  Staged
        against the page's own baked instant, never wall-clock.  Skips
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

        PACKET_TS = TIME_TS + 60
        html = self.render(wxskyfield_sat_almanac, sky_page=make_sky_page())
        # An hour out: well past the sweep, and past the "today" wording
        # of every roster line -- this test is about the chart alone.
        html = rewindow_pass_chart(html, PACKET_TS + 3600, PACKET_TS + 4200)
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())
        # A live feed, one packet repeated: renderPass returns at its
        # latest === null guard until one lands, and a single stamp keeps
        # the page's clock still, which is the state the latch is for.
        (tmp_path / 'gauge-data').mkdir()
        (tmp_path / 'gauge-data' / 'loop-data.txt').write_text(loop_file({
            'current.dateTime.raw': PACKET_TS,
            'almanac.iss.az': 120.0,
            'almanac.iss.alt': 45.0,
            'almanac.iss.sunlit': True,
            'almanac.sun.az': 180.0,
            'almanac.sun.alt': 30.0,
            'almanac.sun.earth_distance': 1.016}))

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
            "G = '#pass-chart g.dome-body[data-body=iss]'\n"
            'OBSERVE = """() => {\n'
            '  window.__muts = 0;\n'
            '  var els = [document.querySelector(\'"""  + G + """\'),\n'
            '             document.querySelector(\'"""  + G + """ circle\'),\n'
            "             document.querySelector('#pass-chart text[data-body=iss]')];\n"
            '  window.__obs = new MutationObserver(function(rs) {\n'
            '    window.__muts += rs.length; });\n'
            '  els.forEach(function(el) {\n'
            "    if (el !== null) { window.__obs.observe(el, {attributes: true}); } });\n"
            '}"""\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    page = browser.new_page()\n'
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            "    page.goto('http://127.0.0.1:%d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    # The feed is running: renderPass is doing its work.\n'
            "    page.wait_for_function('() => latest !== null', timeout=15000)\n"
            '    page.wait_for_timeout(1500)\n'
            '    page.evaluate(OBSERVE)\n'
            '    page.wait_for_timeout(5000)      # five localTicks\n'
            '    out = {\n'
            "        'errors': errors,\n"
            "        'muts': page.evaluate('() => window.__muts'),\n"
            "        'display': page.get_attribute(G, 'display'),\n"
            "        'transform': page.get_attribute(G, 'transform'),\n"
            "        'asDrawn': page.evaluate('() => passBase.asDrawn'),\n"
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
        # The chart stands exactly as the station drew it: shown, no
        # sweep transform, and the page knows it.
        assert out['display'] is None, out
        assert out['transform'] is None, out
        assert out['asDrawn'] is True, out
        # ...and standing there costs nothing.  Without the latch the
        # dot's fill/stroke pair is rewritten on every tick, for the
        # whole stretch before the pass -- hours, on a real station.
        assert out['muts'] == 0, out['muts']

    def test_pass_chart_without_its_own_window_falls_back_to_the_feed_in_a_real_browser(
            self, wxskyfield_sat_almanac, tmp_path):
        """An older weewx-skyfield's chart carries no data-rise/data-set;
        renderPass then judges the chart against the FEED's
        next_visible_pass window -- 8.3.2's behavior exactly, the fix
        needing the chart's own times.  Exercised, not grepped: the
        chart's window is STRIPPED, the feed lies the pass into progress
        and then past its set, and the dot must sweep on the feed's
        window and, at the feed's set, be RESTORED to the drawn chart
        (the old behavior -- no better, and no hide the old code did not
        do).  Skips when the playwright env is absent."""
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
        html = relib.sub(r'data-dome-ts="\d+"',
                         'data-dome-ts="%d"' % int(time.time()), html, count=1)
        html = rewindow_pass_chart(html, None, None)      # a pre-2.3.2 chart
        assert 'data-set=' not in html.split('id="pass-chart"', 1)[1].split('</svg>', 1)[0]
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        state = {'n': 0, 't0': None}

        def packet():
            # The feed's window, anchored to the browser's first poll: in
            # progress for the first three polls, then past its set.
            if state['t0'] is None:
                state['t0'] = time.time()
            i, t0 = state['n'], state['t0']
            past = i >= 3
            return loop_file({
                'current.dateTime.raw': time.time(),
                'almanac.sun.alt': -30.0,
                'almanac.iss.az': 120.0 + 0.5 * i,
                'almanac.iss.alt': 45.0,
                'almanac.iss.sunlit': True,
                'almanac.iss.label': 'ISS',
                'almanac.iss.next_visible_pass.rise.unix_epoch.raw': t0 - 60,
                'almanac.iss.next_visible_pass.set.unix_epoch.raw':
                    t0 - 1 if past else t0 + 600,
            }).encode()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body = packet()
                    state['n'] += 1
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
            "G = '#pass-chart g.dome-body[data-body=iss]'\n"
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    page = browser.new_page()\n'
            '    errors = []\n'
            "    page.on('pageerror', lambda e: errors.append(str(e)))\n"
            "    page.goto('http://127.0.0.1:%(port)d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    # The feed window governs: the sweep engages on it.\n'
            "    page.wait_for_selector(G + '[transform]', timeout=15000)\n"
            "    # The feed's set passes: RESTORED, not hidden -- the drawn\n"
            '    # chart, transform gone, display untouched.\n'
            '    page.wait_for_function("""() => {\n'
            "      var g = document.querySelector('\"\"\" + G + \"\"\"');\n"
            "      return g !== null && !g.hasAttribute('transform') &&\n"
            "             g.getAttribute('display') !== 'none';\n"
            '    }""", timeout=20000)\n'
            "    out = {'errors': errors}\n"
            '    browser.close()\n'
            'print(json.dumps(out))\n'
            % {'port': port})
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        assert state['n'] >= 4, 'the past-set packets were never served'

    def test_dome_refetch_seeds_nothing_at_load(self):
        """The include is inline at the TOP of <body> and the dome sits
        hundreds of lines below it, and the poll interval is armed at
        script eval -- so nothing that decides whether a fetched
        fragment is the sky already on the page may depend on load
        order.  8.3.2 through 8.3.4 seeded an applied-
        fragment identity from a load handler and compared against it in
        the response handler; the first-packet refetch (8.3.5) could run
        from an interval poll before that handler, and re-injected the
        page's own sky.  Now there is no seed: the response handler
        refuses a fragment whose depicted instant is the same as or
        older than the dome on the page, read at that moment.  Pins the
        shape: no seedAppliedFrag, no load-time refetch, the first-packet
        refetch in updateCurrent, the same-or-older guard, and the
        loadend re-check that closes the in-flight window."""
        src = open(os.path.join(SKIN_DIR, 'realtime_updater.inc'),
                   encoding='utf-8').read()
        assert 'seedAppliedFrag' not in src
        # No UNCONDITIONAL load-time refetch.  The one load handler that
        # can call refreshDome does so only to make a refetch that was
        # asked for while the document was still parsing (see below).
        for m_ in re.finditer(r'addLoadEvent\(function\(\) \{(.*?)\n  \}\);', src, re.S):
            body = m_.group(1)
            if 'refreshDome' in body:
                assert re.search(r'if \(domeRefetchWanted\) \{\s*domeRefetchWanted = false;\s*refreshDome\(\);',
                                 body), 'an unguarded load-time refetch is back'
        # A refetch asked for while the document is still streaming --
        # the first packet from the eval-armed interval poll on a slow
        # link -- is deferred to that handler, never made against an
        # absent or half-parsed dome.
        assert re.search(r"if \(document\.readyState === 'loading'\) \{(?:\s*//[^\n]*\n)*\s*domeRefetchWanted = true;\s*return;",
                         src), 'refreshDome no longer defers while the document parses'
        # Which slot to ask for is a question about the STATION's clock
        # and the archive interval, and nothing else -- never about the
        # fragment the page happens to be holding, whose cycle may
        # already be the previous one.  There is no clock-age threshold
        # any more: 8.3.5's STALE_CLOCK only ever bit when set below the
        # station's loop-write interval (so a healthy page on any slower
        # driver refetched the whole sky most minutes to be refused), and
        # the fault it guarded grew worse as the clock got fresher.
        # Code only: the comments legitimately name what left, and why.
        src_code = '\n'.join(l for l in src.split('\n')
                             if not l.lstrip().startswith('//'))
        for gone in ('STALE_CLOCK', 'domeClockStale', 'domeRefetchOnPacket'):
            assert gone not in src_code, '%s is back' % gone
        # A fetch goes out only when the wanted slot is not the one on the
        # page.  This is the whole bandwidth story AND what makes the
        # ceiling safe: a page whose clock has stopped asks for the slot
        # it already shows, so it never asks blind.
        assert re.search(r'var want = meta === null \? null : domeWant\(meta\);'
                         r'\s*if \(want !== null && want\.ts <= meta\.ts\) \{'
                         r'(?:\s*//[^\n]*\n)*\s*return;', src), \
            'refreshDome no longer gates on the wanted slot'
        assert re.search(r'parseFloat\(m\[1\]\)\s*<=\s*cur\.ts', src), \
            'the same-or-older guard is gone'
        assert re.search(r'parseFloat\(m\[1\]\)\s*>\s*serverNow\(\)', src), \
            'the guard against a sky the station has not reached is gone'
        # No re-ask on completion.  It compared the slot the fetch was for
        # against the slot the clock named on completion, and because the
        # name turned on a freshness flag that flipped twice per loop
        # interval rather than on the slot number, a station whose fetches
        # outlasted the threshold re-asked for ever: two whole skies per
        # packet, under a comment asserting it could not loop.
        assert re.search(r'xhttp\.onloadend = function\(\) \{\s*domeFetchInFlight = false;'
                         r'(?:\s*//[^\n]*\n)*\s*\};', src), \
            'onloadend does more than clear the in-flight flag'
        # The first packet needs no case of its own: every new packet
        # checks, and the first is simply the one that moves the clock
        # furthest -- off GEN_TS, which names the slot the page was
        # generated with, onto the station's real time.
        assert 'if (prevTs === 0) {' not in src, \
            'the first packet has a special case again'
        # And the template really does put the script above the dome, which
        # is why the response handler must read the page rather than a
        # load-time memory of it.
        tmpl = open(os.path.join(SKIN_DIR, 'index.html.tmpl'),
                    encoding='utf-8').read()
        assert (tmpl.index('realtime_updater.inc')
                < tmpl.index('id="dome-svg"')), \
            'the include no longer precedes the dome; the ordering argument above changes'

    def test_freeze_restores_the_drawn_sky_in_a_real_browser(
            self, wxskyfield_sat_almanac, tmp_path):
        """The freeze puts the dome back the way the almanac drew it.

        The other stale test starts stale, so nothing is ever nudged and
        it cannot see this at all.  Here the page starts CURRENT and the
        live layer really runs: bodies take nudge transforms, the sun --
        drawn up at the fixture noon -- is fed below the horizon so the
        live layer HIDES it, and a satellite marker is created.  Then the
        station's clock leaps two hours (the feed carries it, and the
        freeze is judged by it), the fragments 404 so no swap can clear
        the markup and fake the result, and the freeze engages.

        Pins: no mark keeps a transform, NO MARK KEEPS A display -- a
        body the live layer hid must come back, or the frozen plate shows
        a daytime sky with no sun in it -- and no live satellite marker
        survives.  The display half was found by the liveseasons port's
        review of this same function.  Skips when the playwright env is
        absent."""
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

        now = int(time.time())
        html = self.render(wxskyfield_sat_almanac, sky_page=make_sky_page())
        # Current, so the page starts live rather than frozen.
        html = relib.sub(r'data-dome-ts="\d+"', 'data-dome-ts="%d"' % now,
                         html, count=1)
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        def packet(ts, sun_alt):
            return loop_file({
                'current.dateTime.raw': ts,
                # Below the horizon: the live layer HIDES the sun, which
                # the backdrop drew high (fixture noon).
                'almanac.sun.az': 200.0, 'almanac.sun.alt': sun_alt,
                'almanac.sun.earth_distance': 1.016,
                'almanac.mercury.az': 150.0, 'almanac.mercury.alt': 20.0,
                'almanac.mercury.earth_distance': 0.85,
                'almanac.mars.az': 100.0, 'almanac.mars.alt': 35.0,
                'almanac.mars.earth_distance': 0.9,
                'almanac.iss.az': 120.0, 'almanac.iss.alt': 45.0,
                'almanac.iss.sunlit': True, 'almanac.iss.label': 'ISS',
            }).encode()

        # Live for the first few polls, then the station's clock jumps.
        packets = ([packet(now + 2 * i, -5.0) for i in range(4)]
                   + [packet(now + 7200 + 2 * i, -5.0) for i in range(6)])
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
                return super().do_GET()   # dome-svg.txt: 404, no swap

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
            '    # The live layer really ran: marks moved, the set sun was\n'
            '    # hidden, a satellite marker was drawn.\n'
            "    page.wait_for_selector('#dome-svg g.dome-body[transform]', timeout=15000)\n"
            '    out = {\n'
            "        'live_nudged': page.eval_on_selector_all(\n"
            "            '#dome-svg g.dome-body[transform]', 'els => els.length'),\n"
            "        'live_hidden': page.eval_on_selector_all(\n"
            "            '#dome-svg g.dome-body[display]', 'els => els.length'),\n"
            "        'live_satdots': page.eval_on_selector_all(\n"
            "            '#dome-svg .satdot', 'els => els.length'),\n"
            '    }\n'
            '    # ...and then the station clock leaps and the freeze engages.\n'
            "    page.wait_for_selector('#dome-stale:not([hidden])', timeout=20000)\n"
            '    page.wait_for_timeout(2500)\n'
            "    out['nudged'] = page.eval_on_selector_all(\n"
            "        '#dome-svg g.dome-body[transform], #dome-svg text[data-body][transform]',\n"
            "        'els => els.length')\n"
            "    out['hidden'] = page.eval_on_selector_all(\n"
            "        '#dome-svg g.dome-body[display], #dome-svg text[data-body][display]',\n"
            "        'els => els.length')\n"
            "    out['satdots'] = page.eval_on_selector_all(\n"
            "        '#dome-svg .satdot', 'els => els.length')\n"
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
        # The live layer did all three things, so the restore has work to do.
        assert out['live_nudged'] >= 1, out
        assert out['live_hidden'] >= 1, out
        assert out['live_satdots'] >= 1, out
        # And the freeze undid every one of them.
        assert out['nudged'] == 0, out
        assert out['hidden'] == 0, out
        assert out['satdots'] == 0, out

    def test_stalled_feed_restores_the_drawn_sky_in_a_real_browser(
            self, wxskyfield_sat_almanac, tmp_path):
        """A feed that STALLS is the commonest way a feed dies, and the
        hardest case: weewx-loopdata stops writing while the web server
        goes on serving the last file, so every poll is a 200 carrying
        identical json.  Nothing fails.  The station's clock inside those
        packets stops, which also stops the backdrop-age judgement that
        reads it -- so unless the page notices that a repeat is not news,
        both of its restore paths are dead at once and the dome is left
        showing a current star field wearing hour-old bodies.

        A 503-shaped test passes happily over this: it must stall, not
        fail.  Here the live layer nudges for real, the feed then repeats
        one packet for ever, and the page's clock is driven past
        EXTRAP_MAX -- after which every mark must be back where the
        backdrop drew it.  Skips when the playwright env is absent."""
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

        now = int(time.time())
        html = self.render(wxskyfield_sat_almanac, sky_page=make_sky_page())
        html = relib.sub(r'data-dome-ts="\d+"', 'data-dome-ts="%d"' % now,
                         html, count=1)
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        def packet(ts):
            return loop_file({
                'current.dateTime.raw': ts,
                'almanac.sun.az': 200.0, 'almanac.sun.alt': 30.0,
                'almanac.sun.earth_distance': 1.016,
                'almanac.mercury.az': 150.0, 'almanac.mercury.alt': 20.0,
                'almanac.mercury.earth_distance': 0.85,
                'almanac.iss.az': 120.0, 'almanac.iss.alt': 45.0,
                'almanac.iss.sunlit': True, 'almanac.iss.label': 'ISS',
            }).encode()

        # Three fresh packets, then the same one for ever: the file on the
        # far end has stopped being rewritten.
        packets = [packet(now), packet(now + 2), packet(now + 4)]
        stalled = packet(now + 4)
        served = {'n': 0}

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body = (packets[served['n']] if served['n'] < len(packets)
                            else stalled)
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
            '    page.clock.install()\n'
            "    page.goto('http://127.0.0.1:%d/index.html')\n"
            "    page.wait_for_load_state('networkidle')\n"
            '    # The live layer ran on the fresh packets.\n'
            "    page.wait_for_selector('#dome-svg g.dome-body[transform]', timeout=15000)\n"
            "    out = {'live_nudged': page.eval_on_selector_all(\n"
            "        '#dome-svg g.dome-body[transform]', 'els => els.length'),\n"
            "        'live_satdots': page.eval_on_selector_all(\n"
            "            '#dome-svg .satdot', 'els => els.length')}\n"
            '    # Now the feed repeats itself while the clock runs past\n'
            '    # EXTRAP_MAX.  Every poll still answers 200.  Stepped, not\n'
            '    # leapt: each step needs the event loop back to deliver the\n'
            '    # XHR the timers just fired.\n'
            '    for _ in range(16):\n'
            '        page.clock.fast_forward(10000)\n'
            '        page.wait_for_timeout(120)\n'
            "    out['nudged'] = page.eval_on_selector_all(\n"
            "        '#dome-svg g.dome-body[transform], #dome-svg text[data-body][transform]',\n"
            "        'els => els.length')\n"
            "    out['hidden'] = page.eval_on_selector_all(\n"
            "        '#dome-svg g.dome-body[display], #dome-svg text[data-body][display]',\n"
            "        'els => els.length')\n"
            "    out['satdots'] = page.eval_on_selector_all(\n"
            "        '#dome-svg .satdot', 'els => els.length')\n"
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
        assert out['live_nudged'] >= 1, out       # the live layer really ran
        assert out['live_satdots'] >= 1, out
        assert served['n'] > len(packets), out    # and the feed kept answering
        # The stall was noticed even though every poll succeeded.
        assert out['nudged'] == 0, out
        assert out['hidden'] == 0, out
        assert out['satdots'] == 0, out

    @pytest.mark.parametrize('serve_fragment,reason', [
        # Fetches succeed and the file they return is old: the station
        # has stopped writing new ones (or its report cadence is longer
        # than this page has learned).  The case no status code reveals.
        (True, 'no newer backdrop has arrived'),
        # Nothing is served where the page looks.
        (False, 'dome-svg.txt returns HTTP 404'),
    ])
    def test_stale_backdrop_freezes_the_dome_in_a_real_browser(
            self, wxskyfield_sat_almanac, tmp_path, serve_fragment, reason):
        """A backdrop that stops advancing freezes the dome and says so.
        The page is rendered for the fixture instant and fed packets on
        the browser's real clock -- the station saying, in effect, that
        the sky on screen is a year old -- which is the shape of every
        real fault here (fragments not generated, not served, or a
        stalled report cycle).  Pins: no dome-body picks up a nudge
        transform and no live satellite marker is drawn (bodies and
        satellites freeze together -- a satellite flying over a
        motionless star field is the lie this prevents), the health line
        under the panel is SHOWN and names the RIGHT reason of the two
        the first-packet refetch can reach, and the rest of the page goes on
        living: the dial still nudges and both satellite rosters still
        roll, because neither stands on the backdrop.  Skips when the
        playwright env is absent."""
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

        # Rendered for the fixture instant, and deliberately NOT restamped:
        # the embedded backdrop's data-dome-ts is a year behind the feed.
        (tmp_path / 'index.html').write_text(
            self.render(wxskyfield_sat_almanac, sky_page=make_sky_page()))
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())
        # The first-packet refetch (8.3.5) fires within the test's life, so
        # which reason the line carries is decided here: a fragment that
        # answers with the same old sky, or nothing to answer at all.
        if serve_fragment:
            frag = self.render_dome_fragment('dome-svg.txt.tmpl', {
                'sky_page': make_sky_page(),
                'almanac': wxskyfield_sat_almanac,
            })
            assert '<svg' in frag
            assert relib.search(r'data-dome-ts="\d+"', frag)   # fixture-old
            (tmp_path / 'dome-svg.txt').write_text(frag)

        # On a cycle boundary, so the slot the page asks for is slot 0 and
        # this harness needs only the one file.  The station's clock names
        # the slot (8.3.5), and an unaligned clock would land the ask on
        # whichever of the five slots real time happened to fall in --
        # making both the served-fragment case and the filename in the
        # 404 message depend on when the suite was run.
        now = (time.time() // 300) * 300

        def packet(i):
            # A live sky: the sun and the ISS both up and moving, so a
            # dome that had NOT frozen would nudge marks and draw a
            # satellite marker within the first two packets.
            return loop_file({
                'current.dateTime.raw': now + 2 * i,
                'almanac.sun.az': 180.0 + 0.5 * i,
                'almanac.sun.alt': 30.0,
                'almanac.sun.earth_distance': 1.016,
                'almanac.mercury.az': 150.0 + 0.5 * i,
                'almanac.mercury.alt': 20.0,
                'almanac.mercury.earth_distance': 0.85 + 0.001 * i,
                'almanac.iss.az': 120.0 + 0.5 * i,
                'almanac.iss.alt': 45.0 + 0.1 * i,
                'almanac.iss.sunlit': True,
                'almanac.iss.label': 'ISS',
                # A pass in progress right now, nothing like the fixture's
                # Jun 22 first paint: the rosters must roll to THIS.
                'almanac.iss.next_pass.rise.unix_epoch.raw': now - 60,
                'almanac.iss.next_pass.set.unix_epoch.raw': now + 600,
                'almanac.iss.next_pass.max_altitude.degree_angle.raw': 45.0,
                'almanac.iss.next_pass.visible': True,
                'almanac.iss.next_visible_pass.rise.unix_epoch.raw': now - 60,
                'almanac.iss.next_visible_pass.set.unix_epoch.raw': now + 600,
                'almanac.iss.next_visible_pass.max_altitude.degree_angle.raw': 45.0,
            }).encode()
        packets = [packet(i) for i in range(4)]
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
            '    # The line appears on the one-second tick, feed or no feed.\n'
            "    page.wait_for_selector('#dome-stale:not([hidden])', timeout=15000)\n"
            '    page.wait_for_timeout(5500)\n'
            '    def marks():\n'
            "        return page.evaluate('''() => {\n"
            "          var out = [];\n"
            "          document.querySelectorAll('#dome-svg g.dome-body[transform]')\n"
            "            .forEach(function(g) { out.push(g.getAttribute('data-body') +\n"
            "                                   ':' + g.getAttribute('transform')); });\n"
            "          document.querySelectorAll('#dome-svg .satdot').forEach(\n"
            "            function(c) { out.push('sat:' + c.getAttribute('cx') +\n"
            "                                   ',' + c.getAttribute('cy')); });\n"
            "          return out.join('|'); }''')\n"
            '    out = {\n'
            "        'errors': errors,\n"
            "        'stale': page.inner_text('#dome-stale'),\n"
            "        'nudged': page.eval_on_selector_all(\n"
            "            '#dome-svg g.dome-body[transform]', 'els => els.length'),\n"
            "        'satdots': page.eval_on_selector_all('#dome-svg .satdot', 'els => els.length'),\n"
            "        'marks': marks(),\n"
            "        'dialnudged': page.eval_on_selector_all(\n"
            "            '#dial .geodot:not([display])', 'els => els.length'),\n"
            "        'rate': page.inner_text('#geo-rate-mercury'),\n"
            "        'anyline': page.inner_text('#sat-any-line-iss'),\n"
            "        'passline': page.inner_text('#sat-line-iss'),\n"
            '    }\n'
            '    # Two and a half seconds of feed later, every mark on\n'
            '    # the dome must be exactly where it was: THAT is\n'
            '    # frozen.  Not "never nudged" -- the freeze waits for\n'
            '    # the first refetch to come back, so a mark may take\n'
            '    # one nudge before it engages, and a transform once\n'
            '    # set is not removed.\n'
            '    page.wait_for_timeout(2500)\n'
            "    out['marks_later'] = marks()\n"
            "    out['rate_later'] = page.inner_text('#geo-rate-mercury')\n"
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
        # The dome froze, whole -- bodies and satellites together:
        # not one mark moved across two and a half seconds of live
        # feed, while that feed was demonstrably still arriving (the
        # dial below went on deriving rates from it).
        assert out['marks'] == out['marks_later']
        # ... and said so, with the reason and a way out.
        assert 'Star field frozen' in out['stale']
        assert reason in out['stale'], out['stale']
        assert 'what to check' in out['stale']
        # ... while the rest of the page went on living.
        assert out['dialnudged'] >= 9
        assert 'receding' in out['rate'] or 'approaching' in out['rate']
        assert ('receding' in out['rate_later']
                or 'approaching' in out['rate_later'])
        assert served['n'] >= 2
        # The satellite ROSTERS are loop-feed arithmetic and must roll
        # through a frozen dome -- they used to sit inside the dome's
        # render and froze with it, leaving a roster that contradicted
        # the countdown chip ticking two inches above it (8.3.2).  Both
        # tables must have left the fixture's Jun 22 first paint for the
        # pass the feed says is happening now.
        assert 'overhead now' in out['anyline'], out['anyline']
        assert 'overhead now' in out['passline'], out['passline']

    def test_a_station_stamped_ahead_is_not_accused_of_writing_nothing(
            self, wxskyfield_almanac, tmp_path):
        """A station whose archive records are stamped ahead of its own
        loop packets -- a console clock out of true against weewxd's
        system time -- answers every request perfectly with a sky the
        page's one clock says has not happened yet.  The page must refuse
        it (that is the ceiling, and it cannot tell such a fragment from
        the next cycle's sky it exists to refuse), but the line under the
        panel must not then blame the station for not generating
        backdrops: through 8.3.5 the fetch was marked healthy before both
        refusals, so the reader was sent looking for a report cycle that
        was running the whole time.

        The phase read cannot rescue this and never could: a remainder
        modulo the interval cannot see an offset of a whole interval, and
        an offset of any size leaves the reply ahead of the clock.  So
        the freeze stands and the line names it.  Skips when the
        playwright env is absent."""
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

        (tmp_path / 'index.html').write_text(
            self.render(wxskyfield_almanac, sky_page=make_sky_page()))
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        # On a cycle boundary, so the walk asks for slot 0 and this
        # harness needs only the one file (the same staging the frozen-
        # backdrop test uses).
        now = (time.time() // 300) * 300
        # The console runs twenty minutes fast: a whole number of
        # five-minute intervals, which is exactly the offset the phase
        # arithmetic is blind to.  The fragment is otherwise perfect --
        # a real sky, served with a 200.
        AHEAD = 1200
        frag = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'sky_page': make_sky_page(), 'almanac': wxskyfield_almanac})
        assert '<svg' in frag
        frag = relib.sub(r'data-dome-ts="\d+"',
                         'data-dome-ts="%d"' % (now + AHEAD), frag, count=1)
        (tmp_path / 'dome-svg.txt').write_text(frag)

        def packet(i):
            return loop_file({
                'current.dateTime.raw': now + 2 * i,
                'almanac.sun.az': 180.0 + 0.5 * i,
                'almanac.sun.alt': 30.0,
                'almanac.sun.earth_distance': 1.016,
            }).encode()
        packets = [packet(i) for i in range(4)]
        served = {'n': 0, 'frags': 0}

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
                if self.path.split('?')[0].startswith('/dome-svg'):
                    served['frags'] += 1
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
            "    page.wait_for_selector('#dome-stale:not([hidden])', timeout=15000)\n"
            '    page.wait_for_timeout(3000)\n'
            '    out = {\n'
            "        'errors': errors,\n"
            "        'stale': page.inner_text('#dome-stale'),\n"
            '        # The sky on the page is still the one it was'
            ' generated with:\n'
            '        # the ahead fragment was refused, not applied.\n'
            "        'domets': page.eval_on_selector(\n"
            "            '#dome-svg div[data-dome-ts]',\n"
            "            'el => el.getAttribute(\"data-dome-ts\")'),\n"
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
        # The station was asked, and answered.
        assert served['frags'] >= 1
        # The sky the station has not reached was NOT applied.
        assert out['domets'] == str(TIME_TS), out
        # And the line names the fault by its own kind, rather than
        # accusing a station that is generating backdrops perfectly.
        assert 'Star field frozen' in out['stale'], out['stale']
        assert "dome-svg.txt is stamped ahead of the station's clock" \
            in out['stale'], out['stale']
        assert 'no newer backdrop has arrived' not in out['stale'], out['stale']

    def test_resume_steps_the_backdrop_on_the_catch_up_packet_in_a_real_browser(
            self, wxskyfield_almanac, tmp_path):
        """A page coming back from a sleeping laptop or a background tab
        gets a fresh backdrop within its own poll, not at the next minute
        boundary -- otherwise the sky sits an hour behind live marks for
        up to a minute, and posts the frozen line at a station doing
        nothing wrong.

        8.3.5 made that fetch the visibilitychange handler's job, which
        meant asking on a clock that had not moved yet; the ask named a
        slot from the cycle the page fell asleep in, and the station
        answered it out of the cycle it now held -- a sky most of a cycle
        in the future.  The resume is the loop feed's now: the catch-up
        packet moves the clock, the moved clock wants a different slot,
        and the fetch follows immediately.  Pins all three of it -- a
        page in step spends NO request (the sky it holds is the one
        wanted), the catch-up packet steps it at once and well inside
        DOME_REFRESH, and the frozen line never flashes.  Skips when the
        playwright env is absent."""
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

        # The page as generated (backdrop at the fixture instant), and
        # beside it the fragment the station would have written since --
        # stamped NOW, the way a live station's current slot would be.
        (tmp_path / 'index.html').write_text(
            self.render(wxskyfield_almanac, sky_page=make_sky_page()))
        frag = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'sky_page': make_sky_page(),
            'almanac': wxskyfield_almanac,
        })
        assert '<svg' in frag
        # The station's cycle, exactly as it writes it: the page's baked
        # backdrop is slot 0 at the fixture instant (which is a multiple
        # of the 300 s archive interval, as every archive record is), and
        # the slots beside it are a minute apart.  The handler serves
        # whichever the page asks for, so what it asks for is the test.
        SLEPT = 180                    # three slots' worth of sleep

        def stamped(slot):
            f = relib.sub(r'data-dome-ts="\d+"',
                          'data-dome-ts="%d"' % (TIME_TS + slot * 60),
                          frag, count=1)
            return relib.sub(r'data-dome-slot="\d+"',
                             'data-dome-slot="%d"' % slot, f, count=1)
        polls = {'n': 0}
        asked = []                     # every backdrop fragment requested
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        def packet_for(ts):
            return loop_file({
                'current.dateTime.raw': ts,
                'almanac.sun.az': 200.0, 'almanac.sun.alt': 60.0,
                'almanac.sun.earth_distance': 1.016,
            }).encode()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    # The station's clock: the fixture instant while the
                    # page is in step, and then -- the machine having been
                    # asleep for three slots -- the catch-up packet.  The
                    # feed is what resumes; nothing else in the page can.
                    polls['n'] += 1
                    packet = packet_for(TIME_TS + (0 if polls['n'] <= 2
                                                   else SLEPT))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(packet)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(packet)
                    return
                if self.path.startswith('/dome-svg'):
                    asked.append(self.path.split('?')[0])
                    slot = relib.match(r'/dome-svg-(\d+)\.txt', self.path)
                    body = stamped(int(slot.group(1)) if slot else 0).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain')
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
            '    # In step: the page holds the slot its own clock names.\n'
            '    # That it asks for nothing meanwhile is proved server\n'
            '    # side, by what was requested at all.\n'
            "    before = page.get_attribute('#dome-svg div[data-dome-ts]', 'data-dome-ts')\n"
            '    # ...and then the catch-up packet lands (the feed now\n'
            '    # reports three slots later, as it would for a machine\n'
            '    # coming back from sleep).  Well inside the 60 s interval,\n'
            '    # the backdrop follows it.\n'
            '    page.wait_for_function("""(was) => {\n'
            "      var d = document.querySelector('#dome-svg div[data-dome-ts]');\n"
            "      return d !== null && d.getAttribute('data-dome-ts') !== was;\n"
            '    }""", arg=before, timeout=20000)\n'
            '    out = {\n'
            "        'errors': errors,\n"
            "        'before': before,\n"
            "        'after': page.get_attribute('#dome-svg div[data-dome-ts]', 'data-dome-ts'),\n"
            "        'staleflash': page.eval_on_selector(\n"
            "            '#dome-stale', 'el => el.hidden'),\n"
            '    }\n'
            '    browser.close()\n'
            'print(json.dumps(out))\n' % {'port': port})
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        # In step, and it stayed that way without spending a request: the
        # backdrop is still the one the page was generated with.
        assert int(out['before']) == TIME_TS
        # The catch-up packet moved the clock three slots, and the page
        # asked for that slot -- once, and nothing else ever.  Slot 0, the
        # sky it already had, is never among them: a page in step spends
        # no requests, which is the whole bandwidth story.
        assert int(out['after']) == TIME_TS + SLEPT
        assert asked == ['/dome-svg-3.txt'], asked
        assert out['staleflash'] is True                # and never accused anyone

    def test_first_packet_refetch_before_load_does_not_churn_the_dome_in_a_real_browser(
            self, wxskyfield_almanac, tmp_path):
        """The dome's first refetch fires on the FIRST loop packet
        (8.3.5), and that packet can arrive before window.onload: the
        poll interval is armed at script eval, so a page whose load
        drags past refresh_rate -- sky.js is a deferred script, and here
        it is served four seconds slow -- has its first packet answered
        by the interval, not the load handler.  An earlier cut of this release seeded
        the applied-fragment identity from a load handler and compared
        the refetch against that memory, so this ordering re-injected
        the very sky on the page: baselines thrown away, generated
        satellite marks unhidden, an open tap chip dismissed.  Now the
        response handler judges against the dome on the page at the
        moment of comparison -- same-or-older depicted instant, no swap
        -- and nothing is seeded, so there is no ordering to get right.
        Pins: the dome fetch goes out before the document is complete,
        the fragment (stamped exactly as the page's dome) is refused,
        the dome on the page is untouched, no page errors.  Skips when
        the playwright env is absent."""
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

        html = self.render(wxskyfield_almanac, sky_page=make_sky_page())
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())
        page_dome_ts = relib.search(r'data-dome-ts="(\d+)"', html).group(1)
        # The fragment the station would serve for slot 0 of THIS cycle:
        # the same sky the page holds, stamped the same.
        frag = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'sky_page': make_sky_page(),
            'almanac': wxskyfield_almanac,
        })
        assert 'data-dome-ts="%s"' % page_dome_ts in frag
        packet = loop_file({
            'current.dateTime.raw': int(time.time()),
            'almanac.sun.az': 200.0, 'almanac.sun.alt': 60.0,
            'almanac.sun.earth_distance': 1.016,
        }).encode()
        served = []

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body, ctype = packet, 'application/json'
                elif self.path.startswith('/dome-svg'):
                    served.append(self.path.split('?')[0])
                    body, ctype = frag.encode(), 'text/plain'
                elif self.path.startswith('/sky.js'):
                    time.sleep(4)          # the slow load: onload waits on this
                    return super().do_GET()
                else:
                    return super().do_GET()
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

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
            '    # Do not wait for load: the point is what happens before it.\n'
            "    with page.expect_request(lambda r: 'dome-svg' in r.url, timeout=15000) as req:\n"
            "        page.goto('http://127.0.0.1:%(port)d/index.html', wait_until='commit')\n"
            "    ready_at_fetch = page.evaluate('document.readyState')\n"
            "    page.wait_for_load_state('load')\n"
            '    page.wait_for_timeout(1500)\n'
            '    out = {\n'
            "        'errors': errors,\n"
            "        'ready_at_fetch': ready_at_fetch,\n"
            "        'applied': page.evaluate('appliedDomeFrag'),\n"
            "        'latestTs': page.evaluate('latestTs'),\n"
            "        'dome_ts': page.get_attribute('#dome-svg div[data-dome-ts]', 'data-dome-ts'),\n"
            '    }\n'
            '    browser.close()\n'
            'print(json.dumps(out))\n' % {'port': port})
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        assert served, 'the first-packet refetch never went out'
        assert out['ready_at_fetch'] != 'complete', \
            'the refetch was meant to beat window.onload; it did not (%s)' % out['ready_at_fetch']
        assert out['latestTs'] > 0                       # a packet did land
        assert out['applied'] is None, \
            'the same-stamped fragment was swapped in: %s' % out['applied']
        assert out['dome_ts'] == page_dome_ts            # the page's own dome stands

    def test_first_packet_refetch_waits_for_the_dome_to_parse_in_a_real_browser(
            self, wxskyfield_almanac, tmp_path):
        """The other half of the slow-load story: the first packet can
        arrive while the DOME ITSELF is still streaming in -- the
        include sits at the top of <body>, the poll interval is armed at
        script eval, and the dome is a couple of hundred kilobytes
        further down.  A refetch made then is judged against a dome that
        is absent or half-parsed: the response handler either throws the
        fragment away (having set domeChecked, so a cached page could
        freeze and post the frozen line against a healthy station until
        the next interval) or replaces the children of a wrapper the
        parser is still filling.  So refreshDome defers while
        document.readyState is 'loading' and the load handler makes the
        refetch it owes.  Here index.html is served in two chunks with a
        four-second stall INSIDE the dome, and the fragment is stamped a
        minute newer than the page's dome so a refetch that lands shows.
        Pins: the packet arrives during the stall, renderDome on that
        packet reads no baselines from the half-parsed dome, no dome
        fetch goes out until the document has parsed, exactly one goes
        out then, the newer sky is applied, one svg in the wrapper, no
        errors.
        Skips when the playwright env is absent."""
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

        html = self.render(wxskyfield_almanac, sky_page=make_sky_page())
        page_dome_ts = int(relib.search(r'data-dome-ts="(\d+)"', html).group(1))
        cut = html.index('id="dome-svg"') + 2000      # well inside the dome
        head, tail = html[:cut].encode(), html[cut:].encode()
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())
        frag = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'sky_page': make_sky_page(),
            'almanac': wxskyfield_almanac,
        })
        frag = relib.sub(r'data-dome-ts="\d+"', 'data-dome-ts="%d"' % (page_dome_ts + 60),
                         frag, count=1).encode()
        packet = loop_file({
            'current.dateTime.raw': int(time.time()),
            'almanac.sun.az': 200.0, 'almanac.sun.alt': 60.0,
            'almanac.sun.earth_distance': 1.016,
        }).encode()
        log = []          # (monotonic seconds, what)
        t0 = time.monotonic()

        class Handler(http.server.SimpleHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self):
                path = self.path.split('?')[0]
                if path in ('/', '/index.html'):
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(head) + len(tail)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(head)
                    self.wfile.flush()
                    log.append((time.monotonic() - t0, 'stall-begin'))
                    time.sleep(4)
                    self.wfile.write(tail)
                    log.append((time.monotonic() - t0, 'stall-end'))
                    return
                if path.startswith('/gauge-data/loop-data.txt'):
                    log.append((time.monotonic() - t0, 'packet'))
                    body, ctype = packet, 'application/json'
                elif path.startswith('/dome-svg'):
                    log.append((time.monotonic() - t0, 'dome ' + path))
                    body, ctype = frag, 'text/plain'
                else:
                    return super().do_GET()
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

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
            "    page.goto('http://127.0.0.1:%(port)d/index.html', wait_until='commit')\n"
            '    # The packet lands mid-stall: catch the page in that state.\n'
            "    page.wait_for_function('typeof latestTs !== \"undefined\" && latestTs > 0', timeout=15000)\n"
            "    mid = page.evaluate('({ready: document.readyState, baseNull: domeBase === null, svgParsed: domeSvg() !== null})')\n"
            "    page.wait_for_load_state('load')\n"
            '    page.wait_for_timeout(2500)\n'
            '    out = {\n'
            "        'errors': errors,\n"
            "        'mid': mid,\n"
            "        'dome_ts': page.get_attribute('#dome-svg div[data-dome-ts]', 'data-dome-ts'),\n"
            "        'svgs': page.evaluate(\"document.querySelectorAll('#dome-svg svg').length\"),\n"
            "        'wanted': page.evaluate('domeRefetchWanted'),\n"
            '    }\n'
            '    browser.close()\n'
            'print(json.dumps(out))\n' % {'port': port})
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        stall_begin = [t for t, w in log if w == 'stall-begin'][0]
        stall_end = [t for t, w in log if w == 'stall-end'][0]
        packets = [t for t, w in log if w == 'packet']
        domes = [t for t, w in log if w.startswith('dome ')]
        assert any(stall_begin < t < stall_end for t in packets), \
            'no packet arrived during the stall; the ordering under test never happened: %r' % log
        assert domes, 'the deferred refetch never went out: %r' % log
        assert all(t > stall_end for t in domes), \
            'a dome fetch went out while the document was still parsing: %r' % log
        assert len(domes) == 1, log
        assert out['mid']['ready'] == 'loading', \
            'the packet was meant to land mid-parse; it did not (%r)' % out['mid']
        # The precondition the next pin depends on: the dome's <svg> start
        # tag HAD parsed by then (renderDome returns at svg === null before
        # its readyState guard), so the cut really is inside the dome.
        assert out['mid']['svgParsed'] is True, \
            'the cut fell before the <svg>; the baseline pin below would be vacuous (%r)' % out['mid']
        # renderDome, called on that packet, must not have read baselines
        # from the half-parsed dome (skyfield's sibling finding, 8.3.5).
        assert out['mid']['baseNull'] is True, 'domeBase was read from a half-parsed dome'
        assert int(out['dome_ts']) == page_dome_ts + 60     # the newer sky applied
        assert out['svgs'] == 1                              # into a whole wrapper, once
        assert out['wanted'] is False

    def test_first_packet_before_the_chips_parse_is_repainted_at_load_in_a_real_browser(
            self, wxskyfield_almanac, tmp_path):
        """The countdown chips and the satellite rosters paint only on a
        NEW loop packet, never on the tick (8.3.5).  A first packet that
        lands while the page is still streaming -- the poll interval is
        armed at script eval, near the top of <body> -- finds their ids
        not yet in the DOM and setHtml says nothing; on a live feed the
        next distinct packet heals it, but on a dead feed re-serving its
        last file the new-packet gate never opens again and the chips
        and rosters would wear the generated first paint for the life of
        the page while the badge told the packet's time.  So a packet
        that lands during parsing leaves renderWanted, and the load
        handler re-runs the five renders once on `latest`.  Here
        index.html is served with a four-second stall just BEFORE the
        countdown row, the feed carries the darkness pair a known hour
        out, and the packet is served identically on every poll (the
        dead-feed shape).  Pins: the packet arrives during the stall
        with the chip not yet in the DOM, and after load the chip shows
        the packet's arithmetic, not the baked value.  Skips when the
        playwright env is absent."""
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

        html = self.render(wxskyfield_almanac, sky_page=make_sky_page())
        baked_dark = relib.search(r'id="chip-dark-v"[^>]*>([^<]*)<', html).group(1)
        cut = html.index('<div class="countdown')
        head, tail = html[:cut].encode(), html[cut:].encode()
        assert b'id="chip-dark-v"' not in head
        assert b'setInterval(updateCurrent' in head     # the include has parsed and run
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())
        now = int(time.time())
        packet = loop_file({
            'current.dateTime.raw': now,
            'almanac(horizon=-18).sun.next_setting.unix_epoch.raw': now + 3600,
            'almanac(horizon=-18).sun.next_rising.unix_epoch.raw': now + 7200,
            'almanac.sun.az': 200.0, 'almanac.sun.alt': 60.0,
            'almanac.sun.earth_distance': 1.016,
        }).encode()
        log = []
        t0 = time.monotonic()

        class Handler(http.server.SimpleHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self):
                path = self.path.split('?')[0]
                if path in ('/', '/index.html'):
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(head) + len(tail)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(head)
                    self.wfile.flush()
                    log.append((time.monotonic() - t0, 'stall-begin'))
                    time.sleep(4)
                    self.wfile.write(tail)
                    log.append((time.monotonic() - t0, 'stall-end'))
                    return
                if path.startswith('/gauge-data/loop-data.txt'):
                    log.append((time.monotonic() - t0, 'packet'))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(packet)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(packet)
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
            "    page.goto('http://127.0.0.1:%(port)d/index.html', wait_until='commit')\n"
            "    page.wait_for_function('typeof latestTs !== \"undefined\" && latestTs > 0', timeout=15000)\n"
            "    mid = page.evaluate('({ready: document.readyState, chipThere: document.getElementById(\"chip-dark-v\") !== null, wanted: renderWanted})')\n"
            "    page.wait_for_load_state('load')\n"
            '    page.wait_for_timeout(2500)\n'
            '    out = {\n'
            "        'errors': errors,\n"
            "        'mid': mid,\n"
            "        'dark': page.text_content('#chip-dark-v'),\n"
            "        'wanted': page.evaluate('renderWanted'),\n"
            "        'latestTs': page.evaluate('latestTs'),\n"
            '    }\n'
            '    browser.close()\n'
            'print(json.dumps(out))\n' % {'port': port})
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        stall_begin = [t for t, w in log if w == 'stall-begin'][0]
        stall_end = [t for t, w in log if w == 'stall-end'][0]
        assert any(stall_begin < t < stall_end for t, w in log if w == 'packet'), \
            'no packet arrived during the stall: %r' % log
        # The preconditions the pin depends on: caught mid-parse, chip not
        # yet in the DOM, the flag left.
        assert out['mid']['ready'] == 'loading', out['mid']
        assert out['mid']['chipThere'] is False, out['mid']
        assert out['mid']['wanted'] is True, out['mid']
        # After load: the chip shows the packet's arithmetic -- exactly an
        # hour, because the clock is the packet's stamp and the re-served
        # feed never moves it (one clock: nothing here counts the seconds
        # since) -- not the baked value; and the feed never produced a
        # second distinct packet to do it.
        assert out['latestTs'] == now
        assert out['dark'] != baked_dark, 'the chip still wears the generated first paint'
        assert out['dark'] == '01:00:00', out['dark']
        assert out['wanted'] is False

    @pytest.mark.parametrize('behind', [False, True])
    def test_cycle_roll_never_lands_a_sky_ahead_of_the_station_in_a_real_browser(
            self, behind, wxskyfield_almanac, tmp_path):
        """The fault the whole slot rule exists for, in a browser.

        The page holds the previous cycle's LAST slot -- the ordinary
        state for the first minute of every cycle, since the backdrop
        steps one slot at a time -- and the station rolls to a new cycle.
        The page's clock is the last loop packet's stamp, so for a moment
        it still reads as inside the old cycle and names that cycle's
        late slot.  The filename carries a slot number and no cycle
        identity, so the station answers out of the cycle it NOW holds:
        through 8.3.4 the page applied a sky four minutes into the
        future -- it was newer than the dome on the page -- and the
        same-or-older guard then held it there until the true time caught
        up to it.  8.3.5's clock-age threshold only narrowed the window,
        and cost a whole-sky refetch most minutes on any station whose
        loop writes were slower than the threshold to do it.

        The base now comes from the station's clock against the archive
        interval, so through the roll the wanted slot is the one already
        showing and nothing is asked at all; when the clock crosses the
        roll, slot 0 of the new cycle is wanted, asked and applied.  Pins
        it on the wire: slot 4 asked once, legitimately, inside its own
        cycle; nothing asked at all while the page's clock and the
        station's cycle disagree; the four-minutes-ahead sky never
        displayed; and the page lands on the new cycle's base.  Skips
        when the playwright env is absent."""
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

        (tmp_path / 'index.html').write_text(
            self.render(wxskyfield_almanac, sky_page=make_sky_page()))
        frag = self.render_dome_fragment('dome-svg.txt.tmpl', {
            'sky_page': make_sky_page(),
            'almanac': wxskyfield_almanac,
        })
        assert '<svg' in frag
        # The fixture instant is a multiple of the 300 s archive interval,
        # as every archive record is, so it serves as a cycle base.
        STEP, ROLL = 60, 300
        OLD, NEW = TIME_TS, TIME_TS + ROLL
        AHEAD = NEW + 4 * STEP         # what the old walk used to apply

        def stamped(base, slot):
            f = relib.sub(r'data-dome-ts="\d+"',
                          'data-dome-ts="%d"' % (base + slot * STEP),
                          frag, count=1)
            return relib.sub(r'data-dome-slot="\d+"',
                             'data-dome-slot="%d"' % slot, f, count=1)

        # Walked by poll count, in the two states a page can be in when
        # the station rolls -- and it takes a different guard to survive
        # each, so both are run.
        #
        # IN STEP (behind=False): the page steps to the old cycle's last
        # slot first, and when the roll comes the slot its clock names is
        # the one it is already showing.  Nothing is asked at all.  This
        # is what the base computed from the STATION's clock buys; a base
        # taken from the fragment on the page names the same slot but out
        # of a cycle that has moved on.
        #
        # BEHIND (behind=True): the page never got that slot -- its fetch
        # cadence skipped it -- so at the roll it genuinely wants slot 4
        # and asks for it.  The base cannot help: the ask is correct for
        # the cycle the page is in.  The station answers out of the cycle
        # it now holds, and only the ceiling on the reply refuses a sky
        # the station has not reached.
        def phase(n):
            if n <= 2:
                return (OLD + 290, NEW) if behind else (OLD + 4 * STEP, OLD)
            if n <= 5 and not behind:
                return OLD + 290, NEW
            return OLD + ROLL + 10, NEW

        polls = {'n': 0}
        asked = []
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    polls['n'] += 1
                    body = loop_file({
                        'current.dateTime.raw': phase(polls['n'])[0],
                        'almanac.sun.az': 200.0, 'almanac.sun.alt': 60.0,
                        'almanac.sun.earth_distance': 1.016,
                    }).encode()
                elif self.path.startswith('/dome-svg'):
                    asked.append(self.path.split('?')[0])
                    slot = relib.match(r'/dome-svg-(\d+)\.txt', self.path)
                    # Whatever slot is asked for, out of the cycle the
                    # station holds RIGHT NOW -- which is the whole point:
                    # the request cannot name a cycle.
                    body = stamped(phase(polls['n'])[1],
                                   int(slot.group(1)) if slot else 0).encode()
                else:
                    return super().do_GET()
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

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
            '    # Every distinct sky the page DISPLAYS, in order: the\n'
            '    # ahead-of-the-station one must never be among them.\n'
            '    seen = []\n'
            '    for _ in range(250):\n'
            "        v = page.get_attribute('#dome-svg div[data-dome-ts]',\n"
            "                               'data-dome-ts')\n"
            '        if not seen or seen[-1] != v:\n'
            '            seen.append(v)\n'
            "        if v == '%(landed)d':\n"
            '            break\n'
            '        page.wait_for_timeout(100)\n'
            "    out = {'errors': errors, 'seen': seen}\n"
            '    browser.close()\n'
            'print(json.dumps(out))\n' % {'port': port, 'landed': NEW})
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=120)
        finally:
            httpd.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)
        assert out['errors'] == []
        seen = [int(v) for v in out['seen']]
        # The sky four minutes into the future was never displayed...
        assert AHEAD not in seen, seen
        assert all(v <= NEW for v in seen), seen
        # ...the in-step page stepped through the old cycle's last slot
        # legitimately, while the behind one never displayed it at all
        # (the only copy it was ever offered came out of the new cycle,
        # and was refused)...
        assert (OLD + 4 * STEP in seen) is not behind, seen
        # ...and both ended on the new cycle's base.
        assert seen[-1] == NEW, seen
        # On the wire, the same two requests either way: slot 4 once --
        # applied inside its own cycle, refused when answered out of the
        # next one -- and then slot 0 of the new cycle.  Never a repeat
        # while the want stands unmet.
        assert asked == ['/dome-svg-4.txt', '/dome-svg.txt'], asked

    def test_countdown_chips_tick_and_roll_in_a_real_browser(
            self, wxskyfield_comet_almanac, tmp_path):
        """Countdown central, where it actually runs: synthetic
        event instants around the browser's real clock (the chips are
        pure client arithmetic, so the feed can stage any sky).  Pins:
        the sun chip counts hh:mm:ss from the FEED and ROLLS from sunset
        to sunrise when the feed's event expiry replaces the passed
        instant (the min() flip); the darkness chip counts from its
        generation-baked data-ts target with NO feed KEY at all -- a
        countdown needs no key to count, only the page's clock, which
        the packets move (8.3.5: at loop cadence, no timer); the shower
        chip shows a
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
            return loop_file({
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
            '    # The first packet lands and the sun chip counts to sunset.\n'
            '    page.wait_for_function("""() => {\n'
            "      var k = document.getElementById('chip-sun-k');\n"
            "      var v = document.getElementById('chip-sun-v');\n"
            "      return k !== null && k.textContent === 'sunset' &&\n"
            "             /^\\\\d{2}:\\\\d{2}:\\\\d{2}$/.test(v.textContent);\n"
            '    }""", timeout=15000)\n'
            '    # The darkness chip is inside its final day, so it counts\n'
            '    # hh:mm:ss -- on the packets, which are 2 s apart here: the\n'
            '    # value must CHANGE within a few polls.  (A fixed 1.5 s\n'
            '    # sample was the 8.3.4 one-second tick at work; it would\n'
            '    # now miss a packet a quarter of the time.)\n'
            "    v1 = page.inner_text('#chip-dark-v')\n"
            '    page.wait_for_function("""(v1) => {\n'
            "      var v = document.getElementById('chip-dark-v');\n"
            "      return v !== null && v.textContent !== v1;\n"
            '    }""", arg=v1, timeout=8000)\n'
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
        assert out['v1'] != out['v2']              # the value really moves
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

    def test_viewer_clock_skew_changes_nothing_in_a_real_browser(
            self, wxskyfield_sat_almanac, tmp_path):
        """8.3.5's rule, where it can be broken: the browser's clock is
        set half an hour wrong -- both ways -- and nothing on the page
        may show it.  The page's time is the loop packet's own stamp
        (serverNow), or GEN_TS before the first packet; the browser is
        never asked what time it is.

        Live legs (+30 min, -30 min): once a packet has landed,
        serverNow() IS that packet's stamp, exactly; the "updated" stamp
        paints it, in the template's own 24-hour shape; the darkness
        chip -- counting from a generation-baked target near the real
        clock, no feed key -- reads the remaining time by the station's
        clock, not the viewer's (a page on the browser clock would be
        thirty minutes off, and would show it in the first second); the
        LIVE badge reads LIVE (its age has no cross-clock term, so the
        skew never becomes "1800s ago").  The comparison of serverNow
        against real time is valid ONLY because browser and "station"
        are the same machine in this harness.

        No-feed leg (+30 min, the loop file 404s): serverNow() === GEN_TS
        exactly, for as long as the page stands (not "about half an hour
        from real time" -- GEN_TS is the render's own instant); the
        "updated" stamp is the template's first paint of that instant;
        the darkness chip stands at its baked first paint; and the badge
        names the fault.  Skips when the playwright env is absent."""
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
        SKEW = 1800
        DARK_TARGET = int(now + 5000)
        html = self.render(wxskyfield_sat_almanac, sky_page=make_sky_page())
        html, n_subs = re.subn(r'(id="chip-dark" data-ts=")\d+(")',
                               r'\g<1>%d\g<2>' % DARK_TARGET, html)
        assert n_subs == 1
        gen_hms = time.strftime('%H:%M:%S', time.localtime(TIME_TS))
        assert '<span id="last-update">%s</span>' % gen_hms in html
        baked_dark = re.search(r'id="chip-dark-v"[^>]*>([^<]*)<', html).group(1)
        (tmp_path / 'index.html').write_text(html)
        for asset in ('celestial.css', 'sky.js'):
            (tmp_path / asset).write_bytes(
                open(os.path.join(SKIN_DIR, asset), 'rb').read())

        def packet(i):
            return loop_file({
                'current.dateTime.raw': int(now + 2 * i),
                'almanac.sun.next_setting.unix_epoch.raw': int(now + 3000),
                'almanac.sun.next_rising.unix_epoch.raw': int(now + 40000),
            }).encode()
        served = {'n': 0}

        class Live(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    body = packet(served['n'])
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

        class NoFeed(Live):
            def do_GET(self):
                if self.path.startswith('/gauge-data/loop-data.txt'):
                    self.send_error(404)
                    return
                return super().do_GET()

        live = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Live)
        nofeed = socketserver.ThreadingTCPServer(('127.0.0.1', 0), NoFeed)
        threading.Thread(target=live.serve_forever, daemon=True).start()
        threading.Thread(target=nofeed.serve_forever, daemon=True).start()
        runner = tmp_path / 'runner.py'
        runner.write_text(
            'import json, time\n'
            'from playwright.sync_api import sync_playwright\n'
            'LIVE = %d\n'
            'NOFEED = %d\n'
            'SKEW = %d\n'
            'GEN_TS = %d\n'
            'DARK_TARGET = %d\n'
            'out = {}\n'
            'with sync_playwright() as p:\n'
            '    browser = p.chromium.launch()\n'
            '    for name, port, skew in (("plus", LIVE, SKEW), ("minus", LIVE, -SKEW),\n'
            '                             ("nofeed", NOFEED, SKEW)):\n'
            '        page = browser.new_page()\n'
            '        errors = []\n'
            "        page.on('pageerror', lambda e: errors.append(str(e)))\n"
            '        # The viewer\'s clock, wrong by skew; timers keep flowing.\n'
            '        page.clock.install(time=time.time() + skew)   # epoch seconds\n'
            "        page.goto('http://127.0.0.1:%%d/index.html' %% port)\n"
            "        page.wait_for_load_state('networkidle')\n"
            '        leg = {"errors": errors}\n'
            '        if name != "nofeed":\n'
            '            page.wait_for_function("() => latest !== null", timeout=15000)\n'
            '            leg["real_now"] = time.time()\n'
            '            leg["state"] = page.evaluate("""() => ({\n'
            '                serverNow: serverNow(), latestTs: latestTs,\n'
            '                browserNow: Date.now() / 1000,\n'
            "                updated: document.getElementById('last-update').textContent,\n"
            "                updatedExpected: fmtHMS(latestTs),\n"
            "                badge: document.getElementById('live-label').textContent,\n"
            "                dark: document.getElementById('chip-dark-v').textContent,\n"
            "                darkHidden: document.getElementById('chip-dark').hasAttribute('hidden')})\"\"\")\n"
            '        else:\n'
            "            page.wait_for_selector('#live-label:not(:empty)', timeout=15000)\n"
            '            page.wait_for_timeout(5000)\n'
            '            leg["state"] = page.evaluate("""() => ({\n'
            '                serverNow: serverNow(), latestTs: latestTs, latest: latest,\n'
            '                browserNow: Date.now() / 1000,\n'
            "                updated: document.getElementById('last-update').textContent,\n"
            "                badge: document.getElementById('live-label').textContent,\n"
            "                dark: document.getElementById('chip-dark-v').textContent})\"\"\")\n"
            '        out[name] = leg\n'
            '        page.close()\n'
            '    browser.close()\n'
            'print(json.dumps(out))\n'
            % (live.server_address[1], nofeed.server_address[1], SKEW,
               int(TIME_TS), DARK_TARGET))
        try:
            proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                  text=True, timeout=180)
        finally:
            live.shutdown()
            nofeed.shutdown()
        assert proc.returncode == 0, proc.stderr
        out = jsonlib.loads(proc.stdout)

        def hms_seconds(text):
            h, m, s = (int(x) for x in text.split(':'))
            return h * 3600 + m * 60 + s

        for name, sign in (('plus', 1), ('minus', -1)):
            leg = out[name]
            st = leg['state']
            assert leg['errors'] == [], (name, leg['errors'])
            # The skew really was installed: the browser is ~30 min out.
            assert abs((st['browserNow'] - leg['real_now']) - sign * SKEW) < 30, name
            # The page's clock is the packet's stamp, exactly -- not the
            # browser's, not the stamp carried forward.
            assert st['serverNow'] == st['latestTs'], name
            assert abs(st['serverNow'] - leg['real_now']) < 15, \
                (name, 'same-machine harness: the stamp is real time')
            # The "updated" stamp paints that instant, in the template's
            # own 24-hour shape (fmtHMS's en-GB pin) -- never the viewer's.
            assert st['updated'] == st['updatedExpected'], name
            assert st['updated'] == time.strftime('%H:%M:%S',
                                                  time.localtime(st['latestTs'])), name
            # The darkness chip counts from its baked target on the
            # STATION's clock: about 5000 s, not 5000 -/+ 1800.
            assert st['darkHidden'] is False, name
            remaining = hms_seconds(st['dark'])
            assert abs(remaining - (DARK_TARGET - st['serverNow'])) <= 3, \
                (name, st['dark'], DARK_TARGET - st['serverNow'])
            assert abs(remaining - (DARK_TARGET - st['browserNow'])) > SKEW - 60, \
                (name, 'the chip is reading the viewer clock')
            # No cross-clock term in the badge: LIVE, not "1800s ago".
            assert st['badge'] == 'LIVE', (name, st['badge'])

        leg = out['nofeed']
        st = leg['state']
        assert leg['errors'] == []
        assert st['latest'] is None and st['latestTs'] == 0
        assert st['serverNow'] == int(TIME_TS), \
            'with no packet the page clock is GEN_TS, exactly, and does not run'
        assert st['updated'] == gen_hms, 'the baked first paint stands'
        assert st['dark'] == baked_dark, 'no packet, no repaint'
        # (The pre-packet chart standing untouched is pinned structurally
        # -- the `latest === null` return in renderPass -- not here: the
        # baked chart carries no transform and passStandsAsDrawn's first
        # act is to remove one, so no attribute read could tell the two
        # apart.)
        assert st['badge'].startswith('NO DATA (HTTP 404)'), st['badge']

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
            packets.append(loop_file(r).encode())

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

    def test_page_reports_a_file_without_its_entry_in_badge(self, wxskyfield_almanac,
                                                             tmp_path):
        """A loop-data file that parses but carries no entry under this
        report's name -- a weewx-loopdata older than 7.0 (flat keys, the
        record itself at the top level), or this report not declaring
        its fields -- must read BAD DATA, not silently stand: the file is
        there, this page's data is not.  Both shapes are served here,
        and neither may throw.  Skips when the playwright env is
        absent."""
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
        record = {'current.dateTime.raw': int(time.time()),
                  'almanac.sun.az': 200.0, 'almanac.sun.alt': 60.0,
                  'almanac.sun.earth_distance': 1.016}
        shapes = {
            # loopdata 7.0 serving another report's entry and not ours.
            'other-report': jsonlib.dumps({'LoopDataReport': record}),
            # a pre-7.0 loopdata: the record flat at the top level.
            'flat-legacy': jsonlib.dumps(record),
        }
        (tmp_path / 'gauge-data').mkdir()

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
            '    page.wait_for_timeout(2500)\n'
            "    out = {'errors': errors, 'badge': page.inner_text('#live-label')}\n"
            '    browser.close()\n'
            'print(json.dumps(out))\n' % port)
        try:
            for shape, body in shapes.items():
                (tmp_path / 'gauge-data' / 'loop-data.txt').write_text(body)
                proc = subprocess.run([pwenv, str(runner)], capture_output=True,
                                      text=True, timeout=120)
                assert proc.returncode == 0, proc.stderr
                out = jsonlib.loads(proc.stdout)
                assert out['errors'] == [], shape
                assert 'BAD DATA' in out['badge'], (shape, out['badge'])
                assert 'check loop_data_file' in out['badge'], shape
        finally:
            httpd.shutdown()

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

    def test_chart_palette_in_step_with_skyfield(self):
        """The dial's grid color, its Mars dot and the three dome label
        colors are weewx-skyfield's values copied in -- the same cross-repo
        rule as sky.js and the .skytip rule above, and the same reason: the
        dome and the Next Visible Pass chart arrive as skyfield's own SVG
        with their colors already inside them, so a value that drifts on
        this side puts two shades of one thing on one page.  skyfield 2.2
        retuning this palette (grid, night Mars, the small labels) is
        exactly the event this pins.  grid and mars live in skyfield's
        PALETTES dict, because the charts emit those two inline; the label
        colors live in its sky.css.  Skips when no weewx-skyfield is
        available."""
        candidates = [
            os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                         'skins', 'Skyfield'),
            '/home/weewx/skins/Skyfield',
        ]
        sky_skin = next((d for d in candidates
                         if os.path.exists(os.path.join(d, 'sky.css'))), None)
        sky_py = next((os.path.join(d, 'wxskyfield_sky.py')
                       for d in WXSKYFIELD_DIRS
                       if os.path.exists(os.path.join(d, 'wxskyfield_sky.py'))),
                      None)
        if sky_skin is None or sky_py is None:
            pytest.skip('weewx-skyfield is not available')

        cel_css = open(os.path.join(SKIN_DIR, 'celestial.css'),
                       encoding='utf-8').read()
        sky_css = open(os.path.join(sky_skin, 'sky.css'), encoding='utf-8').read()

        def token(css, name):
            """The value of a --custom-property in the :root block."""
            m = re.search(r'--%s:\s*(#[0-9A-Fa-f]{6})' % name, css)
            assert m is not None, name
            return m.group(1).upper()

        def label_fill(css, cls):
            """The fill of a class's OWN rule.  Anchored at line start so the
            `:root.theme-light` overrides -- which this night-only page does
            not copy -- can never be the one that matches."""
            m = re.search(r'^\.%s\{([^}]*)\}' % cls, css, re.M | re.S)
            assert m is not None, cls
            fill = re.search(r'fill:\s*(#[0-9A-Fa-f]{6})', m.group(1))
            assert fill is not None, cls
            return fill.group(1).upper()

        # skyfield's 'night' palette is the one celestial gets: the template
        # calls dome_svg($almanac) with no palette argument, and dome_svg
        # defaults to 'night'.
        sky_src = open(sky_py, encoding='utf-8').read()
        night = re.search(r"\n    'night':\s*\{(.*?)\n    \},", sky_src, re.S)
        assert night is not None, sky_py

        def palette_color(key):
            m = re.search(r"'%s':\s*'(#[0-9A-Fa-f]{6})'" % key, night.group(1))
            assert m is not None, key
            return m.group(1).upper()

        assert token(cel_css, 'grid') == palette_color('grid')
        assert token(cel_css, 'c-mars') == palette_color('mars')
        for cls in ('skylab', 'starlab', 'conlab'):
            assert label_fill(cel_css, cls) == label_fill(sky_css, cls), cls

        # The LIGHT plate (8.3).  Here the whole token set is skyfield's,
        # not just two values: on this plate celestial renders the dome
        # and the pass chart on skyfield's own paper palette, so every
        # color the page draws beside them has to be the same paper.
        # John's rule cutting this release: if the light theme hardcodes
        # body colors, they come FROM PALETTES['light'] rather than being
        # invented.  This is that rule, enforced.
        light_block = re.search(r':root\.theme-light\{(.*?)\}', cel_css, re.S)
        assert light_block is not None, 'the light theme block is gone'

        def light_token(name):
            m = re.search(r'--%s:\s*(#[0-9A-Fa-f]{6})' % name, light_block.group(1))
            assert m is not None, name
            return m.group(1).upper()

        light = re.search(r"\n    'light':\s*\{(.*?)\n    \},", sky_src, re.S)
        assert light is not None, sky_py

        def light_color(key, section=None):
            hay = light.group(1)
            if section is not None:
                sub = re.search(r"'%s':\s*\{(.*?)\}" % section, hay, re.S)
                assert sub is not None, section
                hay = sub.group(1)
            m = re.search(r"'%s':\s*'(#[0-9A-Fa-f]{6})'" % key, hay)
            assert m is not None, (section, key)
            return m.group(1).upper()

        for tok, key in (('night', 'dome_stops'), ('ink', 'ink'), ('muted', 'muted'),
                         ('brass', 'brass'), ('line', 'line'), ('grid', 'grid'),
                         ('halo', 'halo')):
            if key == 'dome_stops':
                # The page background is the paper the dome fades out to.
                m = re.search(r"'dome_stops':\s*\(.*?'(#[0-9A-Fa-f]{6})'\)\)",
                              light.group(1), re.S)
                assert m is not None
                assert light_token(tok) == m.group(1).upper()
            else:
                assert light_token(tok) == light_color(key), tok
        for body in ('sun', 'moon', 'mercury', 'venus', 'mars', 'jupiter',
                     'saturn', 'uranus', 'neptune', 'pluto'):
            assert light_token('c-' + body) == light_color(body, 'body'), body
        # Earth is the documented exception (John's call, 8.3): skyfield
        # draws it only in its orrery, a panel this page does not embed,
        # so the dial's center dot is the one mark with no counterpart on
        # this page to disagree with -- and it keeps its own green
        # identity on BOTH plates instead of turning blue on paper.
        # Pinned as an exception, so a future tidy-up that "corrects" it
        # to skyfield's earth_fill trips this test and reads why.
        assert light_token('c-earth') != light_color('earth_fill')
        assert light_token('e-earth') != light_color('earth_stroke')
        for tok in ('c-earth', 'e-earth'):
            value = light_token(tok)
            r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
            assert g > r and g > b, '%s (%s) left the green family' % (tok, value)
            # ... and dark enough to be a mark on paper at all, which the
            # night green (2.35:1 on white) is not.
            assert _wcag_ratio(value, '#FFFFFF') >= 4.5, (tok, value)
        # The pale bodies' edges, and Proxima wearing the moon's.
        for body in ('sun', 'moon', 'venus'):
            assert light_token('e-' + body) == light_color(body, 'ring'), body
        assert light_token('c-proxima') == light_color('moon', 'ring')

        def light_rule_fill(css, cls):
            m = re.search(r':root\.theme-light \.%s\{([^}]*)\}' % cls, css)
            assert m is not None, cls
            fill = re.search(r'fill:\s*(#[0-9A-Fa-f]{6}|var\(--[a-z]+\))',
                             m.group(1))
            assert fill is not None, cls
            return fill.group(1).upper()

        for cls in ('skylab', 'starlab', 'conlab'):
            assert light_rule_fill(cel_css, cls) == light_rule_fill(sky_css, cls), cls
        # The moon's disc: skyfield's own paper values, including the ring
        # that is all that draws a disc whose lit limb is nearly the page.
        for cls, key in (('moon-dark', 'moon_dark'), ('moon-lit', 'moon_lit')):
            assert light_rule_fill(cel_css, cls) == light_color(key), cls
        rim = re.search(r':root\.theme-light \.moon-rim\{([^}]*)\}', cel_css)
        assert rim is not None
        assert light_color('moon_ring') in rim.group(1).upper()

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

    @staticmethod
    def _body_names(html):
        """The roster's display names, and the javascript's BODY_LABELS."""
        rows = re.findall(r'<span class="chip [^"]*"></span>([^<]*)<', html)
        labels = json.loads(
            re.search(r'BODY_LABELS = (\{.*?\});', html).group(1))
        return rows, labels

    def test_body_names_come_from_almanac_texts(self, wxskyfield_almanac):
        """On WeeWX 5.3 and later the roster and the javascript both name
        the bodies from the report's [Almanac] section."""
        wxskyfield_almanac.texts = {'moon': 'Mond', 'jupiter': 'Jupiter'}
        rows, labels = self._body_names(self.render(wxskyfield_almanac))
        assert 'Mond' in rows
        assert labels['moon'] == 'Mond'
        # A body the [Almanac] section does not name still gets its
        # capitalized tag.
        assert labels['neptune'] == 'Neptune'

    @pytest.mark.parametrize('tier', ['pyephem', 'weeutil'])
    def test_renders_on_weewx_5_2_without_texts(self, tier):
        """WeeWX only grew Almanac.texts in 5.3; install.py's floor is 5.2.
        The page must still generate there, naming the bodies in
        capitalized English.

        The 5.2 shape is a trap, which is why the template reads __dict__
        rather than the attribute: with PyEphem registered, $almanac.texts
        does not raise -- Almanac.__getattr__ walks the almanacs and
        PyEphemAlmanacType's catch-all hands back an AlmanacBinder for a
        "heavenly body" named texts.  The lookup SUCCEEDS and returns
        something truthy (so a getattr() default can never fire); the page
        dies one step later on .get.  Without PyEphem the shape differs
        again -- WeeutilAlmanacType raises UnknownType and Almanac's own
        __getattr__ raises AttributeError -- hence both tiers here."""
        if tier == 'pyephem':
            pytest.importorskip('ephem')
        with saved_almanacs():
            weewx.almanac.almanacs[:] = [
                weewx.almanac.PyEphemAlmanacType() if tier == 'pyephem'
                else weewx.almanac.WeeutilAlmanacType()]
            alm = weewx.almanac.Almanac(TIME_TS, LATITUDE, LONGITUDE,
                                        altitude=ALTITUDE_M,
                                        formatter=weewx.units.get_default_formatter())
            # Exactly 5.2: the attribute was never set.  Note the
            # constructor is called WITHOUT texts= -- 5.2's Almanac has no
            # such keyword and raises TypeError, so passing it here (even
            # to delete the result) would make this very test unrunnable
            # on the WeeWX it is about.  pop() covers both: a no-op on
            # 5.2, the deletion that simulates it on 5.3+.
            alm.__dict__.pop('texts', None)
            if tier == 'pyephem':
                assert isinstance(alm.texts, weewx.almanac.AlmanacBinder)
            html = self.render(alm)
        rows, labels = self._body_names(html)
        assert 'Moon' in rows and 'Jupiter' in rows
        assert labels['moon'] == 'Moon'
        assert labels['neptune'] == 'Neptune'
        # The rest of the page is unaffected: the roster still carries a
        # row per body for the javascript to keep live.
        assert 'id="geo-row-proxima_centauri"' in html

    def test_raising_sky_page_degrades_instead_of_killing_the_page(
            self, wxskyfield_almanac):
        """A $sky_page whose METHODS raise (weewx-skyfield hitting its own
        WeeWX 5.2 incompatibility, say) must degrade the dome and pass
        panels, never take the page down with it -- which is what makes
        this skin's own 5.2 fix sufficient on its own.  Every $sky_page
        call site is wrapped in a bare #try; this pins that.  Verified on
        a real WeeWX 5.2 instance 2026-08-13, where the page generated at
        83,732 bytes with only the separate dome/pass FRAGMENT templates
        skipped."""

        class RaisingSkyPage:
            def _boom(self, *args, **kwargs):
                raise KeyError('Texts')
            dome_svg = _boom
            pass_chart_html = _boom
            satellite_names = _boom
            comet_names = _boom

        html = self.render(wxskyfield_almanac, sky_page=RaisingSkyPage())
        # The page is whole: header, roster row per body, footer.
        assert '<html lang="en" class="theme-dark">' in html
        assert 'id="geo-row-proxima_centauri"' in html
        assert re.match(r'[\d,]+$', self.cell(html, 'almanac.moon.earth_distance'))
        # The dome degrades to its install hint, exactly as when
        # weewx-skyfield is absent altogether.
        assert html.count('class="skyhint"') == 1
        assert 'live sky dome' in html


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

    @requires_almanac_texts
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
        assert '<html lang="de" class="theme-dark">' in html
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

    @requires_almanac_texts
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
        assert '<html lang="fr" class="theme-dark">' in html
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
        # Jacques Terrettaz's 2026-08-15 correction: the roster reads
        # "se rapproche a 28 km/s", so the verb carries its preposition.
        assert '"approaching": "se rapproche \\u00e0"' in html
        # The footer carries the full French Skyfield credit, naming
        # weewx-skyfield with the project link.
        assert 'Calculé avec %s : Skyfield' % LINKED_NAME in html

    @requires_almanac_texts
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
        assert '<html lang="nl" class="theme-dark">' in html
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

    @requires_almanac_texts
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
        assert '<html lang="es" class="theme-dark">' in html
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

    @requires_almanac_texts
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
        assert '<html lang="it" class="theme-dark">' in html
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

    @requires_almanac_texts
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
        assert '<html lang="no" class="theme-dark">' in html
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

    @requires_almanac_texts
    def test_shipped_danish_renders(self, wxskyfield_sky):
        """The shipped da.conf, fed through the same channels the report
        engine uses, renders a Danish page -- the template's static
        strings and the json feeds the javascript composes from alike.
        Danish is the one file a native speaker wrote entire (Gert
        Andersen, 7.8), which is the better reason to render it, not a
        lesser one: it was the only shipped language never rendered end
        to end until 8.3."""
        mod, _ = load_wxskyfield()
        conf = self.lang_conf(self.LANG_DIR, 'da.conf')
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sky)
            alm = weewx.almanac.Almanac(
                TIME_TS, LATITUDE, LONGITUDE, altitude=ALTITUDE_M,
                formatter=weewx.units.Formatter(
                    ordinate_names=list(conf['Units']['Ordinates']['directions'])),
                texts=dict(conf['Almanac']))
            html = TestSampleSkinRenders.render(
                alm, lang='da', texts=dict(conf['Texts']),
                labels={'hemispheres': list(conf['Labels']['hemispheres'])})
        assert '<html lang="da" class="theme-dark">' in html
        assert 'Geocentrisk (live)' in html
        # The roster first-paints Danish: the sun is up at the solstice
        # noon, and the distance cells carry the Danish au unit (au, as
        # in English -- unlike the German and Swedish AE).
        assert 'højde ' in html
        assert ' au<' in html
        # The javascript feeds: Danish body names and cardinals (json,
        # non-ASCII \u-escaped), and the composed-string dictionary.
        # Danish compass east is Ø, so the cardinal ring proves the
        # ordinates flowed through as well as the body names.
        assert '"moon": "M\\u00e5ne"' in html
        assert '"neptune": "Neptun"' in html
        assert '["N", "\\u00d8", "S", "V"]' in html
        assert '"below horizon": "under horisonten"' in html
        assert '"approaching": "n\\u00e6rmer sig"' in html
        # The footer carries the full Danish Skyfield credit, naming
        # weewx-skyfield with the project link.
        assert 'Beregnet med %s: Skyfield' % LINKED_NAME in html

    @requires_almanac_texts
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
        assert '<html lang="sv" class="theme-dark">' in html
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


class TestPageFields:
    """PAGE_FIELDS is the one source of truth for what the page reads,
    and weewx-loopdata 7.0 reads it in two halves: the static fields
    from the skin's own skin.conf ([LoopData] [[fields]]), the satellite
    and comet fields from the groups declare_page_fields writes under
    the report's stanza in weewx.conf.  These tests pin both halves to
    the list, and every entry to the sibling weewx-loopdata's grammar
    and evaluator."""

    @staticmethod
    def _skin_conf():
        import configobj
        return configobj.ConfigObj(os.path.join(SKIN_DIR, 'skin.conf'),
                                   encoding='utf-8', file_error=True)

    def test_skin_conf_declares_the_static_fields(self):
        """skins/Celestial/skin.conf's [LoopData] [[fields]] groups, in
        order, are exactly PAGE_FIELDS less the satellite and comet
        patterns -- same entries, same order, none twice.  Both
        directions: a field the page gained and the skin does not
        declare never reaches loop-data.txt; a field declared and not
        read is evaluated on every packet for nothing."""
        groups = self._skin_conf()['LoopData']['fields']
        declared = []
        for group, value in groups.items():
            assert not isinstance(value, dict), group
            declared.extend([value] if isinstance(value, str) else list(value))
        assert len(declared) == len(set(declared)), 'a field declared twice'
        assert declared == celestial.static_page_fields()
        assert 'almanac.iss.az' not in declared        # the installer's
        assert 'almanac.halley.az' not in declared     # ... and comets

    def test_loopdata_reads_the_skin_declaration(self):
        """The sibling weewx-loopdata's own declaration reader, given the
        shipped skin.conf as the skin dict, yields the static field set
        -- the contract itself, not a re-implementation of it."""
        loopdata = load_loopdata()
        if not hasattr(loopdata.LoopData, 'declared_fields_from_skin_dict'):
            pytest.skip('the sibling weewx-loopdata predates 7.0')
        fields = loopdata.LoopData.declared_fields_from_skin_dict(
            self._skin_conf(), REPORT_NAME)
        assert fields == celestial.static_page_fields()

    def test_loopdata_reads_the_whole_declaration(self):
        """End to end: skin.conf merged with the stanza the installer
        writes (declare_page_fields on a station with no [Skyfield]
        section -- the installer defaults), read by the sibling
        weewx-loopdata's declaration reader the way WeeWX merges a
        report's configuration (ConfigObj's recursive merge, the
        report's stanza last), is PAGE_FIELDS exactly, in order."""
        import configobj
        loopdata = load_loopdata()
        if not hasattr(loopdata.LoopData, 'declared_fields_from_skin_dict'):
            pytest.skip('the sibling weewx-loopdata predates 7.0')
        config = configobj.ConfigObj()
        celestial.declare_page_fields(config, ensure_default=True)
        skin_dict = self._skin_conf()
        skin_dict.merge(config['StdReport'][REPORT_NAME])
        fields = loopdata.LoopData.declared_fields_from_skin_dict(
            skin_dict, REPORT_NAME)
        assert fields == list(celestial.PAGE_FIELDS)

    def test_page_fields_stay_comma_free(self):
        """Every entry is single-kwarg (no commas), so no group line ever
        needs a quoted entry -- weewx-loopdata splits an unquoted comma
        into two bogus fields."""
        for field in celestial.PAGE_FIELDS:
            assert ',' not in field, field

    def test_page_fields_parse_in_loopdata(self):
        """Every almanac entry the page reads must parse in the sibling
        weewx-loopdata checkout's almanac grammar."""
        loopdata = load_loopdata()
        for entry in celestial.PAGE_FIELDS:
            if not entry.startswith('almanac'):
                assert entry == 'current.dateTime.raw'
                continue
            assert loopdata.LoopData.parse_almanac_field(entry) is not None, entry

    def test_satellite_fields_evaluate_in_loopdata(self, wxskyfield_sat_sky):
        """The whole pipeline the satellite layer depends on: every
        satellite entry in PAGE_FIELDS EVALUATES through the
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
            for entry in celestial.PAGE_FIELDS:
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
        # loopdata 7.0 builds one evaluator per report from the report's
        # context (its fields, [Almanac] texts, formatter and converter)
        # and the shared configuration (the station's position); both
        # are read by attribute, so two namespaces serve.
        ctx = types.SimpleNamespace(
            almanac_fields=loopdata.LoopData.get_almanac_fields(pin_fields),
            almanac_texts={}, formatter=weewx.units.get_default_formatter(),
            converter=weewx.units.Converter())
        cfg = types.SimpleNamespace(
            latitude=LATITUDE, longitude=LONGITUDE, altitude_m=ALTITUDE_M)
        assert len(ctx.almanac_fields) == len(pin_fields)
        with saved_almanacs():
            assert mod.register_almanac(wxskyfield_sat_sky)
            evaluator = loopdata.AlmanacFieldEvaluator(ctx, cfg)
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
        """Every comet entry in PAGE_FIELDS (and the mcnaught
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
        entries = [f for f in celestial.PAGE_FIELDS
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



class TestDeclarePageFields:
    """declare_page_fields: the satellite and comet groups of every
    Celestial report's [[[LoopData]]] [[[[fields]]]] section converge
    to the configured [Skyfield] sets -- replaced wholesale, removed
    when the set is empty, the installer defaults only when there is no
    section to follow, and nothing else in the section touched.  The
    installer and the --add/--remove verbs both run it, so it is tested
    once, here, on plain dicts and on ConfigObj alike."""

    @staticmethod
    def _groups(config, report='CelestialReport'):
        return config['StdReport'][report]['LoopData']['fields']

    def test_no_skyfield_section_declares_the_defaults(self):
        config = {}
        report = celestial.declare_page_fields(config, ensure_default=True)
        groups = self._groups(config)
        assert list(groups) == ['satellites', 'comets']
        assert groups['satellites'] == (celestial.satellite_fields('iss')
                                        + celestial.satellite_fields('tiangong'))
        assert groups['comets'] == (celestial.comet_fields('halley')
                                    + celestial.comet_fields('hale_bopp'))
        assert len(groups['satellites']) == 38 and len(groups['comets']) == 12
        assert report['satellites'] == ['iss', 'tiangong']
        assert report['comets'] == ['halley', 'hale_bopp']
        assert report['satellites_defaulted'] and report['comets_defaulted']
        assert report['reports'] == ['CelestialReport']
        assert set(report['changes']) == {'CelestialReport'}
        assert set(report['changes']['CelestialReport']) == {'satellites', 'comets'}
        old, new = report['changes']['CelestialReport']['satellites']
        assert old == [] and new == groups['satellites']

    def test_follows_the_configured_sets(self):
        """The configured tags, in configuration order, the defaults
        nowhere in sight; a [Skyfield] with no [[Comets]] still falls
        back to the comet defaults."""
        config = {'Skyfield': {'Satellites': {'terra': '25994', 'noaa21': '54234'}}}
        report = celestial.declare_page_fields(config, ensure_default=True)
        groups = self._groups(config)
        assert groups['satellites'] == (celestial.satellite_fields('terra')
                                        + celestial.satellite_fields('noaa21'))
        assert not any(f.startswith(('almanac.iss.', 'almanac.tiangong.'))
                       for f in groups['satellites'])
        assert groups['comets'] == (celestial.comet_fields('halley')
                                    + celestial.comet_fields('hale_bopp'))
        assert not report['satellites_defaulted'] and report['comets_defaulted']

    def test_empty_section_declares_none_and_removes_the_group(self):
        """A present-but-empty [[Satellites]] is authoritative: no
        satellite fields, and a group left over from an earlier set is
        removed rather than left declaring satellites the station no
        longer tracks."""
        config = {'Skyfield': {'Satellites': {}, 'Comets': {'encke': '2P'}},
                  'StdReport': {'CelestialReport': {'skin': 'Celestial', 'LoopData': {'fields': {
                      'satellites': celestial.satellite_fields('iss'),
                      'mine': ['current.outTemp']}}}}}
        report = celestial.declare_page_fields(config)
        groups = self._groups(config)
        assert 'satellites' not in groups
        assert groups['comets'] == celestial.comet_fields('encke')
        assert groups['mine'] == ['current.outTemp']        # never touched
        old, new = report['changes']['CelestialReport']['satellites']
        assert old == celestial.satellite_fields('iss') and new == []

    def test_no_section_created_for_nothing(self):
        """Empty sets on a station with no declaration: nothing to write,
        so no [[[LoopData]]] section appears."""
        config = {'Skyfield': {'Satellites': {}, 'Comets': {}}}
        report = celestial.declare_page_fields(config, ensure_default=True)
        assert report['changes'] == {}
        assert config == {'Skyfield': {'Satellites': {}, 'Comets': {}}}

    def test_idempotent(self):
        config = {'Skyfield': {'Satellites': {'terra': '25994'}}}
        celestial.declare_page_fields(config, ensure_default=True)
        before = json.dumps(config, sort_keys=True)
        report = celestial.declare_page_fields(config, ensure_default=True)
        assert report['changes'] == {}
        assert json.dumps(config, sort_keys=True) == before

    def test_replaces_a_stale_group_wholesale(self):
        """The group is the declaration's, not a list to append to: a
        hand-added entry in it, or a satellite since removed, goes."""
        config = {'Skyfield': {'Satellites': {'terra': '25994'}},
                  'StdReport': {'CelestialReport': {'skin': 'Celestial', 'LoopData': {'fields': {
                      'satellites': celestial.satellite_fields('iss')
                      + ['almanac(horizon=10).terra.az']}}}}}
        celestial.declare_page_fields(config)
        assert self._groups(config)['satellites'] == celestial.satellite_fields('terra')

    def test_apply_false_reports_without_writing(self):
        config = {'Skyfield': {'Satellites': {'terra': '25994'}}}
        report = celestial.declare_page_fields(config, apply=False, ensure_default=True)
        assert set(report['changes']['CelestialReport']) == {'satellites', 'comets'}
        assert config == {'Skyfield': {'Satellites': {'terra': '25994'}}}

    def test_every_celestial_report_is_declared(self):
        """One skin under two reports (two languages, say): loopdata
        serves each under its own name, so each carries the groups.
        CelestialReport is declared whether or not it exists yet; any
        other report is found by its skin; other skins are not."""
        config = {'StdReport': {'HTML_ROOT': 'public_html',
                                'CelestialDE': {'skin': 'Celestial', 'lang': 'de'},
                                'LoopDataReport': {'skin': 'LoopData'}}}
        report = celestial.declare_page_fields(config, ensure_default=True)
        assert report['reports'] == ['CelestialReport', 'CelestialDE']
        assert set(report['changes']) == {'CelestialReport', 'CelestialDE'}
        assert 'LoopData' not in config['StdReport']['LoopDataReport']
        assert (self._groups(config, 'CelestialDE')['satellites']
                == self._groups(config)['satellites'])

    def test_only_the_installer_adds_the_default_report(self):
        """Without ensure_default -- the --add/--remove verbs' case --
        [[CelestialReport]] is never created: a report holding only a
        [[[LoopData]]] section has no skin, and reportengine dies on it
        every cycle.  A Celestial report under another name is declared
        under its own name; with no Celestial report at all nothing is
        written and the report says so."""
        config = {'StdReport': {'Himmel': {'skin': 'Celestial'}}}
        report = celestial.declare_page_fields(config)
        assert report['reports'] == ['Himmel']
        assert 'CelestialReport' not in config['StdReport']
        assert self._groups(config, 'Himmel')['satellites'] == (
            celestial.satellite_fields('iss') + celestial.satellite_fields('tiangong'))
        bare = {'Skyfield': {'Satellites': {'iss': '25544'}}}
        report = celestial.declare_page_fields(bare)
        assert report['reports'] == [] and report['changes'] == {}
        assert bare == {'Skyfield': {'Satellites': {'iss': '25544'}}}

    def test_a_reused_report_name_under_another_skin_is_not_ours(self):
        """ensure_default seeds [[CelestialReport]] only where the name is
        free or already this skin's: a section of that name running some
        OTHER skin (reused after an uninstall, repurposed) belongs to
        somebody else, and declaring fifty almanac fields under it would
        have weewx-loopdata evaluate them every packet for a page that is
        not there.  A section with no skin at all IS ours -- the fresh
        install, whose skin weectl merges in right after."""
        theirs = {'StdReport': {'CelestialReport': {'skin': 'Seasons'}}}
        report = celestial.declare_page_fields(theirs, ensure_default=True)
        assert report['reports'] == [] and report['changes'] == {}
        assert theirs['StdReport']['CelestialReport'] == {'skin': 'Seasons'}
        # ... and the real page's report, under its own name, still is.
        both = {'StdReport': {'CelestialReport': {'skin': 'Seasons'},
                              'Himmel': {'skin': 'Celestial'}}}
        assert celestial.declare_page_fields(
            both, ensure_default=True)['reports'] == ['Himmel']
        # No skin key yet: the fresh install, and ours.
        fresh = {'StdReport': {'CelestialReport': {'HTML_ROOT': 'celestial'}}}
        assert celestial.declare_page_fields(
            fresh, ensure_default=True)['reports'] == ['CelestialReport']

    def test_flat_fields_line_is_refused(self):
        """A `fields =` line where the [[[[fields]]]] section belongs --
        the shape weewx-loopdata 7.0 itself refuses -- is a ValueError
        naming the report, raised before anything is written: with two
        Celestial reports and the SECOND malformed, the first is left
        undeclared too (a half-declared configuration must not be what
        the installer then saves).  A [[[LoopData]]] that is not a
        section at all is the same error, not a TypeError."""
        config = {'StdReport': {'CelestialReport': {'skin': 'Celestial'},
                                'Himmel': {'skin': 'Celestial',
                                           'LoopData': {'fields': ['a', 'b']}}}}
        with pytest.raises(ValueError, match=r'\[\[Himmel\]\].*flat fields = line.*named groups'):
            celestial.declare_page_fields(config)
        assert config['StdReport']['CelestialReport'] == {'skin': 'Celestial'}
        assert config['StdReport']['Himmel']['LoopData']['fields'] == ['a', 'b']
        scalar = {'StdReport': {'CelestialReport': {'skin': 'Celestial', 'LoopData': 'x'}}}
        with pytest.raises(ValueError, match=r'\[\[CelestialReport\]\].*is not a section'):
            celestial.declare_page_fields(scalar)

    def test_configobj_round_trip(self, tmp_path):
        """On a real ConfigObj the groups land as one comma-separated
        line each, under the report's stanza, and read back as lists;
        a single-entry group reads back as a str, which the next run
        must treat as one field (never split by character)."""
        import configobj
        conf = tmp_path / 'weewx.conf'
        conf.write_text('[Skyfield]\n    [[Satellites]]\n        iss = 25544\n'
                        '    [[Comets]]\n        encke = 2P\n'
                        '[StdReport]\n    [[CelestialReport]]\n'
                        '        skin = Celestial\n')
        config = configobj.ConfigObj(str(conf))
        celestial.declare_page_fields(config)
        config.write()
        text = conf.read_text()
        assert '[[[LoopData]]]' in text and '[[[[fields]]]]' in text
        assert 'satellites = almanac.iss.az, almanac.iss.alt,' in text
        assert 'comets = almanac.encke.az,' in text
        again = configobj.ConfigObj(str(conf))
        assert again['StdReport']['CelestialReport']['skin'] == 'Celestial'
        assert (again['StdReport']['CelestialReport']['LoopData']['fields']['satellites']
                == celestial.satellite_fields('iss'))
        assert celestial.declare_page_fields(again)['changes'] == {}
        # A one-entry group is a str to ConfigObj.
        again['StdReport']['CelestialReport']['LoopData']['fields']['comets'] = \
            'almanac.encke.az'
        report = celestial.declare_page_fields(again)
        old, new = report['changes']['CelestialReport']['comets']
        assert old == ['almanac.encke.az']


class TestSatelliteUtility:
    """The --add-satellite / --remove-satellite utility: the three
    weewx.conf edits a satellite takes -- the [Skyfield] [[Satellites]]
    entry, its nineteen declared fields (the report's satellites group,
    rebuilt for the configured set), the [StdReport] [[Defaults]]
    [[[Almanac]]] display name -- each independently idempotent, so any
    mixed starting state converges."""

    # A station the installer has already declared for: the satellites
    # group carries the two defaults, as configure() writes it.
    BASE_CONF = (
        '# a comment\n'
        '[Station]\n'
        '    location = Test Station\n'
        '[Skyfield]\n'
        '    satellite_downloads = true\n'
        '    [[Satellites]]\n'
        '        iss = 25544\n'
        '        tiangong = 48274\n'
        '[StdReport]\n'
        '    [[CelestialReport]]\n'
        '        skin = Celestial\n'
        '        [[[LoopData]]]\n'
        '            [[[[fields]]]]\n'
        '                satellites = %s\n'
        % ', '.join(celestial.satellite_fields('iss')
                    + celestial.satellite_fields('tiangong'))
    )

    @staticmethod
    def _group(conf_path, group='satellites'):
        import configobj
        groups = configobj.ConfigObj(str(conf_path))['StdReport'][
            'CelestialReport']['LoopData']['fields']
        value = groups.get(group, [])
        return [value] if isinstance(value, str) else list(value)

    def _write_conf(self, tmp_path, text=None):
        conf = tmp_path / 'weewx.conf'
        conf.write_text(self.BASE_CONF if text is None else text)
        return conf

    def test_pattern_is_nineteen_tag_substituted(self):
        """The per-satellite pattern is the almanac.iss.* subset of
        PAGE_FIELDS with the tag substituted -- one source of
        truth with the page's satellite consumption -- and stays
        comma-free (a group line is a bare comma-separated list)."""
        fields = celestial.satellite_fields('zenit23088')
        iss_fields = [f for f in celestial.PAGE_FIELDS
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
        fields = self._group(out)
        assert 'almanac.zenit23088.az' in fields
        assert 'almanac.zenit23088.next_pass.visible' in fields
        # The group is rebuilt in configuration order: the defaults first,
        # the new satellite last.
        assert fields == (celestial.satellite_fields('iss')
                          + celestial.satellite_fields('tiangong')
                          + celestial.satellite_fields('zenit23088'))
        assert report['fields_added'] == celestial.satellite_fields('zenit23088')
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
        assert self._group(once) == self._group(twice)

    def test_add_converges_mixed_states(self, tmp_path):
        """John's scenario: the satellite was already added per
        weewx-skyfield's instructions -- the [[Satellites]] entry exists,
        the fields do not.  The entry is kept and the fields declared.
        And the reverse: fields declared by hand, entry missing."""
        conf = self._write_conf(tmp_path, self.BASE_CONF.replace(
            '        tiangong = 48274\n',
            '        tiangong = 48274\n        zenit23088 = 23088\n'))
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out),
                                              'zenit23088', '23088')
        assert report['satellites_entry'] == 'unchanged'
        assert len(report['fields_added']) == 19
        # The reverse: every field declared, no [[Satellites]] entry.
        hand_fields = ', '.join(celestial.satellite_fields('zenit23088'))
        conf2 = tmp_path / 'weewx2.conf'
        conf2.write_text(self.BASE_CONF.replace(
            'almanac.tiangong.next_pass.visible\n',
            'almanac.tiangong.next_pass.visible, %s\n' % hand_fields))
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

    def test_add_before_install_declares_nothing(self, tmp_path):
        """A configuration with no Celestial report at all -- weewx-celestial
        not yet installed -- gets the [[Satellites]] entry and NO
        declaration: a [[CelestialReport]] created here would hold only
        [[[LoopData]]], no skin, and reportengine dies on such a section
        every cycle.  The installer declares when it comes; the hint
        says so."""
        conf = self._write_conf(tmp_path, '[Station]\n    location = Test\n')
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out), 'zenit23088', '23088')
        assert report['satellites_entry'] == 'added'
        assert report['fields_added'] == [] and report['reports'] == []
        assert any('No report runs the Celestial skin yet' in h for h in report['hints'])
        import configobj
        assert 'StdReport' not in configobj.ConfigObj(str(out)) or \
            'CelestialReport' not in configobj.ConfigObj(str(out))['StdReport']

    def test_add_declares_under_the_report_that_runs_the_skin(self, tmp_path):
        """The Celestial skin under a name of the user's own and no
        [[CelestialReport]]: the groups go under that name, and no ghost
        [[CelestialReport]] appears (the review's KeyError 'skin' case)."""
        conf = self._write_conf(tmp_path, self.BASE_CONF.replace(
            '    [[CelestialReport]]\n', '    [[Himmel]]\n'))
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out), 'noaa21', '54234')
        assert report['reports'] == ['Himmel']
        assert report['fields_added'] == celestial.satellite_fields('noaa21')
        import configobj
        new = configobj.ConfigObj(str(out))
        assert 'CelestialReport' not in new['StdReport']
        assert (new['StdReport']['Himmel']['LoopData']['fields']['satellites']
                == celestial.satellite_fields('iss') + celestial.satellite_fields('tiangong')
                + celestial.satellite_fields('noaa21'))

    def test_add_says_what_the_other_family_got(self, tmp_path):
        """One declaration covers both families, so --add-satellite on a
        station with no [[Comets]] section declares weewx-skyfield's
        default comets as well -- exactly as the next install would.
        Unannounced that is four edits where the manual promises three,
        so the hint names them; with the section already declared for,
        nothing is said."""
        conf = self._write_conf(tmp_path)          # no [[Comets]] at all
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out), 'noaa21', '54234')
        assert report['fields_added'] == celestial.satellite_fields('noaa21')
        [note] = [h for h in report['hints'] if 'both families' in h]
        assert '12 comet fields (halley, hale_bopp) were declared as well' in note
        assert "weewx-skyfield's installer defaults" in note
        assert '[[Comets]]' in note and '--add-comet' in note
        assert self._group(out, 'comets') == (celestial.comet_fields('halley')
                                              + celestial.comet_fields('hale_bopp'))
        # Re-run: the comets group is right now, so nothing more is said.
        again = celestial.add_satellite_conf(str(out), str(tmp_path / 'b.conf'),
                                             'noaa21', '54234')
        assert not any('both families' in h for h in again['hints'])

    def _run_cli(self, tmp_path, *args):
        """The utility as a user runs it: python -m user.celestial from
        the directory holding the `user` package.  Returns its output
        (the log goes to stderr through weeutil.logger's handler)."""
        import subprocess
        proc = subprocess.run(
            [sys.executable, '-m', 'user.celestial'] + list(args),
            cwd=os.path.join(REPO_ROOT, 'bin'), capture_output=True,
            text=True, timeout=180)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout + proc.stderr

    def test_a_no_op_removal_claims_nothing_about_the_declaration(self, tmp_path):
        """"fields already declared for x" answers "did my add take?".
        On a removal of a tag that was never configured it answers a
        question nobody asked, with the opposite of the truth -- and it
        printed directly under 'no [Skyfield] [[Satellites]] entry for
        zenit99'.  The add verbs keep the line."""
        conf = self._write_conf(tmp_path)
        text = self._run_cli(tmp_path, '--remove-satellite', 'zenit99',
                             '--config', str(conf),
                             '--output', str(tmp_path / 'removed.conf'))
        assert 'no [Skyfield] [[Satellites]] entry for zenit99' in text
        assert 'already declared' not in text
        # The add verb still says it, on a run that changes nothing.
        text = self._run_cli(tmp_path, '--add-satellite', 'iss=25544',
                             '--config', str(conf),
                             '--output', str(tmp_path / 'added.conf'))
        assert 'fields already declared for iss' in text

    def test_every_verb_reports_both_directions_of_its_own_family(self, tmp_path):
        """Each verb REBUILDS its family's group from the configured set,
        so an add can delete (a stale entry the rebuild drops) and a
        remove can write (a set the rebuild re-derives).  Reporting only
        the direction the verb is named for left the other silent."""
        # An add that deletes: zenit declared, but not configured.
        stale = self.BASE_CONF.rstrip('\n') + (
            ', almanac.zenit.az, almanac.zenit.alt\n')
        conf = self._write_conf(tmp_path, stale)
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out), 'noaa21', '54234')
        assert report['fields_added'] == celestial.satellite_fields('noaa21')
        assert report['fields_removed'] == ['almanac.zenit.az', 'almanac.zenit.alt']
        # A remove that writes: no [[Satellites]] section at all, so the
        # rebuild re-derives the installer defaults (John has twice
        # ruled that behaviour stands -- but it may not happen SILENTLY).
        bare = ('[Station]\n    location = Test\n[StdReport]\n'
                '    [[CelestialReport]]\n        skin = Celestial\n')
        conf2 = self._write_conf(tmp_path, bare)
        out2 = tmp_path / 'b.conf'
        report2 = celestial.remove_satellite_conf(str(conf2), str(out2), 'zenit')
        assert report2['satellites_entry'] == 'absent'
        assert report2['fields_removed'] == []
        assert report2['fields_added'] == (celestial.satellite_fields('iss')
                                           + celestial.satellite_fields('tiangong'))

    def test_the_other_familys_note_names_the_tags_that_changed(self, tmp_path):
        """The cross-family note takes its tags from the entries that
        changed, not from the family's current set: a run that UNdeclares
        the other family (its [Skyfield] set emptied since the last one)
        has an empty current list, and the note must not read "12 comet
        fields (none)"."""
        # An emptied [[Comets]] (authoritative), and a comets group left
        # from when it was not: this run undeclares halley.
        conf = self._write_conf(tmp_path, self.BASE_CONF.replace(
            '[StdReport]\n', '    [[Comets]]\n[StdReport]\n') + (
            '                comets = %s\n'
            % ', '.join(celestial.comet_fields('halley'))))
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out), 'noaa21', '54234')
        [note] = [h for h in report['hints'] if 'both families' in h]
        assert '6 comet fields (halley) were undeclared as well' in note
        assert '(none)' not in note
        # An UNdeclaring run is not the defaults standing in for a
        # missing section, so that clause must not ride along.
        assert 'installer defaults' not in note
        assert self._group(out, 'comets') == []

    def test_add_reports_a_second_reports_restored_group(self, tmp_path):
        """Two Celestial reports, the first already right, the second's
        group deleted by hand: the add restores the second and says so
        -- fields_added is the union over every report declared under."""
        conf = self._write_conf(tmp_path, self.BASE_CONF + (
            '    [[Himmel]]\n        skin = Celestial\n'))
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_satellite_conf(str(conf), str(out), 'noaa21', '54234')
        assert report['reports'] == ['CelestialReport', 'Himmel']
        assert report['fields_added'] == (
            celestial.satellite_fields('noaa21') + celestial.satellite_fields('iss')
            + celestial.satellite_fields('tiangong'))

    def test_remove_conf_roundtrip(self, tmp_path):
        conf = self._write_conf(tmp_path)
        added = tmp_path / 'added.conf'
        celestial.add_satellite_conf(str(conf), str(added),
                                     'zenit23088', '23088', 'Zenit-2 23088')
        # The group is the declaration's and is rebuilt for the
        # remaining set, so a hand-added entry in it goes with the
        # satellite (a field of your own belongs in a group of your own).
        import configobj
        cfg = configobj.ConfigObj(str(added))
        cfg['StdReport']['CelestialReport']['LoopData']['fields']['satellites'].append(
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
        fields = self._group(out)
        assert not any('zenit23088' in f for f in fields)
        assert fields == (celestial.satellite_fields('iss')
                          + celestial.satellite_fields('tiangong'))  # others untouched
        assert 'zenit23088' not in new['StdReport']['Defaults']['Almanac']
        # Removing an absent satellite is a no-op, not an error.
        out2 = tmp_path / 'removed2.conf'
        report2 = celestial.remove_satellite_conf(str(out), str(out2), 'zenit23088')
        assert report2['satellites_entry'] == 'absent'
        assert report2['fields_removed'] == []
        assert report2['name_entry'] == 'absent'

    def test_remove_reminds_about_stranded_legacy_entries(self, tmp_path):
        """The legacy [[Include]] line is never edited by the verbs; a
        removal whose tag it still carries says how many entries are
        stranded there (any almanac spelling), and nothing when it
        carries none."""
        conf = self._write_conf(tmp_path, self.BASE_CONF + (
            '[LoopData]\n    [[Include]]\n        fields = %s\n'
            % ', '.join(['current.outTemp'] + celestial.satellite_fields('iss')
                        + ['almanac(horizon=10).iss.next_pass.rise.unix_epoch.raw'])))
        out = tmp_path / 'weewx.conf.new'
        report = celestial.remove_satellite_conf(str(conf), str(out), 'iss')
        assert any(h.startswith('20 entries for iss remain on the legacy')
                   for h in report['hints'])
        import configobj
        line = configobj.ConfigObj(str(out))['LoopData']['Include']['fields']
        assert len(line) == 21                       # untouched
        report = celestial.remove_satellite_conf(str(out), str(tmp_path / 'b.conf'),
                                                 'tiangong')
        assert not any('remain on the legacy' in h for h in report['hints'])

    def test_remove_default_satellite_warns(self, tmp_path):
        """iss/tiangong removal works like any other -- with the warning
        that a weewx-skyfield upgrade's conditional merge re-adds the
        [[Satellites]] entry (only), so the removal wants re-running."""
        conf = self._write_conf(tmp_path)
        out = tmp_path / 'weewx.conf.new'
        report = celestial.remove_satellite_conf(str(conf), str(out), 'iss')
        assert report['satellites_entry'] == 'removed'
        assert report['fields_removed'] == celestial.satellite_fields('iss')
        assert self._group(out) == celestial.satellite_fields('tiangong')
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
    edits a comet takes -- the [Skyfield] [[Comets]] entry, its six
    declared fields (the report's comets group, rebuilt for the
    configured set), the [StdReport] [[Defaults]] [[[Almanac]]] display
    name -- each independently idempotent, mirroring the satellite
    utility."""

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
        '[StdReport]\n'
        '    [[CelestialReport]]\n'
        '        skin = Celestial\n'
        '        [[[LoopData]]]\n'
        '            [[[[fields]]]]\n'
        '                satellites = %s\n'
        '                comets = %s\n'
        % (', '.join(celestial.satellite_fields('iss')),
           ', '.join(celestial.comet_fields('halley')))
    )

    _group = staticmethod(TestSatelliteUtility._group)

    def _write_conf(self, tmp_path, text=None):
        conf = tmp_path / 'weewx.conf'
        conf.write_text(self.BASE_CONF if text is None else text)
        return conf

    def test_pattern_is_six_tag_substituted(self):
        """The per-comet pattern is the almanac.halley.* subset of
        PAGE_FIELDS with the tag substituted -- one source of
        truth with the page's comet consumption -- and stays comma-free
        (a group line is a bare comma-separated list)."""
        fields = celestial.comet_fields('mcnaught')
        halley_fields = [f for f in celestial.PAGE_FIELDS
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
        fields = self._group(out, 'comets')
        assert 'almanac.mcnaught.az' in fields
        assert 'almanac.mcnaught.perihelion.unix_epoch.raw' in fields
        assert fields == (celestial.comet_fields('halley')
                          + celestial.comet_fields('mcnaught'))  # configuration order
        assert report['fields_added'] == celestial.comet_fields('mcnaught')
        assert self._group(out) == celestial.satellite_fields('iss')  # untouched
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
        assert self._group(once, 'comets') == self._group(twice, 'comets')

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

    def test_add_before_install_declares_nothing(self, tmp_path):
        """No Celestial report yet: the [[Comets]] entry is written, no
        declaration is (see the satellite twin), and the hint says so."""
        conf = self._write_conf(tmp_path, '[Station]\n    location = Test\n')
        out = tmp_path / 'weewx.conf.new'
        report = celestial.add_comet_conf(str(conf), str(out), 'encke', '2P')
        assert report['comets_entry'] == 'added'
        assert report['fields_added'] == [] and report['reports'] == []
        assert any('No report runs the Celestial skin yet' in h for h in report['hints'])

    def test_remove_conf_roundtrip(self, tmp_path):
        conf = self._write_conf(tmp_path)
        added = tmp_path / 'added.conf'
        celestial.add_comet_conf(str(conf), str(added),
                                 'mcnaught', '220P', 'McNaught')
        # The group is rebuilt for the remaining set, so a hand-added
        # entry in it goes with the comet.
        import configobj
        cfg = configobj.ConfigObj(str(added))
        cfg['StdReport']['CelestialReport']['LoopData']['fields']['comets'].append(
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
        fields = self._group(out, 'comets')
        assert not any('mcnaught' in f for f in fields)
        assert fields == celestial.comet_fields('halley')    # other comets untouched
        assert self._group(out) == celestial.satellite_fields('iss')
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
        assert report['fields_removed'] == celestial.comet_fields('halley')
        assert any('installer default' in h for h in report['hints'])
        import configobj
        new = configobj.ConfigObj(str(out))
        assert 'halley' not in new['Skyfield']['Comets']
        assert new['Skyfield']['Satellites']['iss'] == '25544'   # untouched
        # The emptied set removes the group rather than leaving it empty.
        assert 'comets' not in new['StdReport']['CelestialReport']['LoopData']['fields']


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


class TestInstallerDeclaresFields:
    """The install-time declaration: weectl's configure() hook writes the
    satellite and comet groups under the report's stanza ([StdReport]
    [[CelestialReport]] [[[LoopData]]] [[[[fields]]]]) for the station's
    configured [Skyfield] sets, through the bundled celestial.py's
    declare_page_fields -- rebuilt on every install, silent when already
    right, dry-run honored, never a failed install.  The legacy
    [LoopData] [[Include]] fields line is never written -- only read, to
    count the entries this page now declares itself."""

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

    @staticmethod
    def _groups(config):
        return config['StdReport']['CelestialReport']['LoopData']['fields']

    def test_declares_the_defaults_on_a_bare_station(self):
        """No [Skyfield] to follow: the installer defaults are declared,
        the note says whose defaults they are, and configure returns
        True so weectl saves."""
        engine = self._engine({})
        assert self._installer().configure(engine) is True
        groups = self._groups(engine.config_dict)
        assert groups['satellites'] == (celestial.satellite_fields('iss')
                                        + celestial.satellite_fields('tiangong'))
        assert groups['comets'] == (celestial.comet_fields('halley')
                                    + celestial.comet_fields('hale_bopp'))
        text = '\n'.join(engine.printer.lines)
        assert ('Declared 38 satellite fields (iss, tiangong) under [StdReport] '
                '[[CelestialReport]] [[[LoopData]]] [[[[fields]]]] satellites.') in text
        assert ('Declared 12 comet fields (halley, hale_bopp) under [StdReport] '
                '[[CelestialReport]] [[[LoopData]]] [[[[fields]]]] comets.') in text
        assert text.count("weewx-skyfield's installer defaults") == 2
        assert 'Restart weewxd' in text
        # The legacy line is nobody's business here.
        assert 'LoopData' not in engine.config_dict
        assert '[[Include]]' not in text

    def test_follows_the_configured_sets(self):
        engine = self._engine(
            {'Skyfield': {'Satellites': {'terra': '25994'}, 'Comets': {'encke': '2P'}}})
        assert self._installer().configure(engine) is True
        groups = self._groups(engine.config_dict)
        assert groups['satellites'] == celestial.satellite_fields('terra')
        assert groups['comets'] == celestial.comet_fields('encke')
        text = '\n'.join(engine.printer.lines)
        assert 'Declared 19 satellite fields (terra)' in text
        assert 'Declared 6 comet fields (encke)' in text
        assert 'installer defaults' not in text

    def test_silent_when_already_declared(self):
        """A station whose groups already match the configured sets is
        left silent and untouched -- an upgrade must not re-announce
        the declaration for the rest of the station's life."""
        config = {'Skyfield': {'Satellites': {'terra': '25994'}}}
        celestial.declare_page_fields(config, ensure_default=True)
        before = json.dumps(config, sort_keys=True)
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        assert engine.printer.lines == []
        assert json.dumps(engine.config_dict, sort_keys=True) == before

    def test_rebuilds_a_stale_group(self):
        """A satellite added to [[Satellites]] by hand since the last
        install is declared on the next one: the group tracks the set."""
        config = {'Skyfield': {'Satellites': {'iss': '25544'}}}
        celestial.declare_page_fields(config)
        config['Skyfield']['Satellites']['terra'] = '25994'
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert self._groups(config)['satellites'] == (
            celestial.satellite_fields('iss') + celestial.satellite_fields('terra'))
        assert 'Declared 38 satellite fields (iss, terra)' in '\n'.join(engine.printer.lines)

    def test_emptied_set_removes_the_group(self):
        """A deliberately emptied [[Comets]] is authoritative for the
        installer too: the comets group goes, and the note says why."""
        config = {'Skyfield': {'Satellites': {'iss': '25544'}, 'Comets': {}}}
        celestial.declare_page_fields({'Skyfield': {'Satellites': {'iss': '25544'}}})
        config['StdReport'] = {'CelestialReport': {'LoopData': {'fields': {
            'satellites': celestial.satellite_fields('iss'),
            'comets': celestial.comet_fields('halley')}}}}
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert 'comets' not in self._groups(config)
        text = '\n'.join(engine.printer.lines)
        assert ('Removed [StdReport] [[CelestialReport]] [[[LoopData]]] [[[[fields]]]] '
                'comets: [Skyfield] [[Comets]] is empty, so the page reads no comet '
                'fields.') in text

    def test_other_groups_untouched(self):
        config = {'StdReport': {'CelestialReport': {'LoopData': {'fields': {
            'mine': ['current.outTemp', 'current.barometer']}}}}}
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        groups = self._groups(config)
        assert groups['mine'] == ['current.outTemp', 'current.barometer']
        assert set(groups) == {'mine', 'satellites', 'comets'}

    def test_dry_run_touches_nothing(self):
        """weectl --dry-run: the would-declare lines print, the
        configuration is not modified, configure returns False."""
        engine = self._engine({}, dry_run=True)
        assert self._installer().configure(engine) is False
        assert engine.config_dict == {}
        text = '\n'.join(engine.printer.lines)
        assert 'Would declare 38 satellite fields (iss, tiangong)' in text
        assert '(dry run)' in text
        assert 'Restart weewxd' not in text

    def test_never_fails_the_install(self):
        """A flat `fields =` line where the section of groups belongs
        degrades to the could-not-declare line -- naming the offending
        report and the shape wanted -- never an exception."""
        engine = self._engine(
            {'StdReport': {'CelestialReport': {'LoopData': {'fields': ['a', 'b']}}}})
        assert self._installer().configure(engine) is False
        text = '\n'.join(engine.printer.lines)
        assert 'Could not declare' in text
        assert '[[CelestialReport]] [[[LoopData]]] carries a flat fields = line' in text
        assert 'named groups' in text

    def test_legacy_line_entries_it_now_declares_are_counted(self):
        """The legacy [[Include]] line is never edited, only counted: the
        entries on it this page now declares are evaluated twice per
        packet by loopdata 7.0, and the install says so -- exactly N,
        the line left as it is -- and says nothing when the line carries
        none of ours, or is absent."""
        legacy = ['current.outTemp'] + celestial.static_page_fields() + \
            celestial.satellite_fields('iss') + ['almanac.iss.next_pass.rise']
        config = {'Skyfield': {'Satellites': {'iss': '25544'}, 'Comets': {}},
                  'LoopData': {'Include': {'fields': list(legacy)}}}
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        text = '\n'.join(engine.printer.lines)
        assert ('still carries 69 entries this page now declares itself; '
                'weewx-loopdata evaluates those twice per loop packet') in text
        assert config['LoopData']['Include']['fields'] == legacy    # untouched
        # Only what THIS station declares counts: tiangong's entries on
        # the line are not ours here, since [[Satellites]] lacks it.
        config['LoopData']['Include']['fields'] = celestial.satellite_fields('tiangong')
        engine = self._engine(config)
        self._installer().configure(engine)
        assert 'still carries' not in '\n'.join(engine.printer.lines)
        engine = self._engine({'LoopData': {'FileSpec': {}}})
        self._installer().configure(engine)
        assert 'still carries' not in '\n'.join(engine.printer.lines)

    def test_a_disabled_target_report_shares_nothing(self):
        """weewx-loopdata builds its declaring contexts from the ENABLED
        reports but renders the legacy line through target_report
        whatever its enable says.  So a disabled target declares
        nothing, the line shares with nothing, and its entries ARE
        evaluated a second time -- the shortcut must not silence the
        note there."""
        legacy = ['current.outTemp'] + celestial.static_page_fields()
        config = {'Skyfield': {'Satellites': {}, 'Comets': {}},
                  'StdReport': {'CelestialReport': {'skin': 'Celestial',
                                                    'enable': 'false'}},
                  'LoopData': {'Include': {'fields': list(legacy)},
                               'Formatting': {'target_report': 'CelestialReport'}}}
        engine = self._engine(config)
        self._installer().configure(engine)
        assert 'still carries 50 entries' in '\n'.join(engine.printer.lines)
        # Enabled again (explicitly, and by saying nothing): shared.
        for enable in ('true', None):
            section = {'skin': 'Celestial'}
            if enable is not None:
                section['enable'] = enable
            config['StdReport']['CelestialReport'] = section
            engine = self._engine(config)
            self._installer().configure(engine)
            assert 'still carries' not in '\n'.join(engine.printer.lines)

    def test_nothing_is_counted_twice_that_loopdata_renders_once(self):
        """weewx-loopdata renders the legacy line through its
        target_report, so where that IS one of the reports declaring
        these fields it renders the shared entries once for both -- they
        cost nothing, and the note must not claim otherwise.  (Naming
        target_report to the user would teach a setting that dies with
        the line, so it is read and never mentioned.)"""
        legacy = ['current.outTemp'] + celestial.static_page_fields()
        base = {'Skyfield': {'Satellites': {}, 'Comets': {}},
                'LoopData': {'Include': {'fields': list(legacy)},
                             'Formatting': {'target_report': 'CelestialReport'}}}
        engine = self._engine(base)
        self._installer().configure(engine)
        assert 'still carries' not in '\n'.join(engine.printer.lines)
        # A Celestial report of another name, named as the target: same.
        other = {'Skyfield': {'Satellites': {}, 'Comets': {}},
                 'StdReport': {'Himmel': {'skin': 'Celestial'}},
                 'LoopData': {'Include': {'fields': list(legacy)},
                              'Formatting': {'target_report': 'Himmel'}}}
        engine = self._engine(other)
        self._installer().configure(engine)
        assert 'still carries' not in '\n'.join(engine.printer.lines)
        # Any other target report renders them a second time: counted.
        elsewhere = {'Skyfield': {'Satellites': {}, 'Comets': {}},
                     'LoopData': {'Include': {'fields': list(legacy)},
                                  'Formatting': {'target_report': 'LiveSeasonsReport'}}}
        engine = self._engine(elsewhere)
        self._installer().configure(engine)
        assert 'still carries 50 entries' in '\n'.join(engine.printer.lines)

    def test_uninstall_prunes_the_whole_stanza(self):
        """The whole install/uninstall round trip through weecfg's own
        merge and prune: configure() writes the groups, weectl's
        conditional merge adds the installer's config around them, and
        weectl extension uninstall's remove_and_prune must take the
        whole [[CelestialReport]] away -- a leftover section holding
        only [[[LoopData]]] has no skin, and reportengine dies on it
        every archive cycle.  The installer's config dict lists the
        subsection (empty) for exactly this; the merge must add nothing
        of its own for it."""
        import configobj
        import weecfg
        from weeutil.config import conditional_merge
        installer = self._installer()
        config = configobj.ConfigObj()
        assert installer.configure(self._engine(config)) is True
        conditional_merge(config, installer['config'])
        stanza = config['StdReport']['CelestialReport']
        assert stanza['skin'] == 'Celestial'
        assert set(stanza['LoopData']['fields']) == {'satellites', 'comets'}
        weecfg.remove_and_prune(config, installer['config'])
        # (weecfg prunes an emptied [StdReport] as well; the point is
        # that no [[CelestialReport]] survives.)
        assert 'CelestialReport' not in config.get('StdReport', {})

    def test_merge_adds_no_groups_when_the_sets_are_empty(self):
        """Empty [Skyfield] sets: configure() writes no group, and the
        installer's empty [[[LoopData]]] [[[[fields]]]] entry must not
        resurrect the defaults through the conditional merge."""
        import configobj
        from weeutil.config import conditional_merge
        installer = self._installer()
        config = configobj.ConfigObj()
        config['Skyfield'] = {'Satellites': {}, 'Comets': {}}
        installer.configure(self._engine(config))
        conditional_merge(config, installer['config'])
        assert dict(config['StdReport']['CelestialReport']['LoopData']['fields']) == {}


class TestInstallerLoader:
    """install.py's loader() refuses to install beside a weewx-loopdata
    older than 7.0, or none: the page's values reach it only through
    7.0's per-report declaration, and an older loopdata never reads it
    -- the page would say BAD DATA for ever with nothing in any log to
    say why.  A dev build is given the benefit of the doubt, exactly as
    the WeeWX floor is."""

    def _with_loopdata(self, monkeypatch, version):
        import types
        user = types.ModuleType('user')
        if version is not None:
            loopdata = types.ModuleType('user.loopdata')
            loopdata.LOOP_DATA_VERSION = version
            user.loopdata = loopdata
            monkeypatch.setitem(sys.modules, 'user.loopdata', loopdata)
        else:
            monkeypatch.delitem(sys.modules, 'user.loopdata', raising=False)
        monkeypatch.setitem(sys.modules, 'user', user)

    INSTALL_ARGV = ['weectl', 'extension', 'install', 'weewx-celestial.zip']

    @pytest.mark.parametrize('version', ['7.0', '7', '7.1', '7.10', '8.0', '7.0a1'])
    def test_loads_with_loopdata_7(self, monkeypatch, version):
        """7.0 and later load -- a bare '7' included (it must read as
        7.0, not as a tuple that orders below it) -- and a dev build is
        given the benefit of the doubt."""
        self._with_loopdata(monkeypatch, version)
        monkeypatch.setattr(sys, 'argv', self.INSTALL_ARGV)
        installer = load_installer().loader()
        assert installer['name'] == 'celestial'
        assert installer['version'] == celestial.CELESTIAL_VERSION

    @pytest.mark.parametrize('version', ['6.11.2', '6.9', '5.0', '6.9b1'])
    def test_refuses_an_older_loopdata(self, monkeypatch, version):
        self._with_loopdata(monkeypatch, version)
        monkeypatch.setattr(sys, 'argv', self.INSTALL_ARGV)
        with pytest.raises(SystemExit) as info:
            load_installer().loader()
        message = str(info.value)
        assert 'weewx-loopdata 7.0 or later' in message
        assert 'found %s' % version in message

    @pytest.mark.parametrize('argv', [
        ['weectl', 'extension', 'install', 'weewx-celestial.zip'],
        ['wee_extension', '--install', 'weewx-celestial.zip'],
        # optparse's documented spelling, and its unambiguous-prefix one
        ['wee_extension', '--install=weewx-celestial.zip'],
        ['wee_extension', '--inst', 'weewx-celestial.zip'],
    ])
    def test_refuses_without_loopdata(self, monkeypatch, argv):
        self._with_loopdata(monkeypatch, None)
        monkeypatch.setattr(sys, 'argv', argv)
        with pytest.raises(SystemExit) as info:
            load_installer().loader()
        message = str(info.value)
        assert 'weewx-loopdata 7.0 or later' in message
        assert 'none is installed' in message

    @pytest.mark.parametrize('source, wanted', [
        ("raise RuntimeError('boom')\n", 'RuntimeError: boom'),
        # The shape that matters most: present, but a dependency of its
        # own is not.  That is an ImportError too, and telling this user
        # to install what they already have sends them the wrong way.
        ('import a_dependency_this_station_lacks\n',
         "ModuleNotFoundError: No module named 'a_dependency_this_station_lacks'"),
        # A loopdata predating LOOP_DATA_VERSION (2020): the module is
        # there and imports, the NAME is not.  That is a plain
        # ImportError whose .name IS 'user.loopdata', so only the
        # ModuleNotFoundError test keeps it out of the not-installed
        # branch -- narrowing that guard to a bare name check would
        # report an installed loopdata as missing.
        ('# a loopdata older than LOOP_DATA_VERSION\n',
         "ImportError: cannot import name 'LOOP_DATA_VERSION'"),
    ])
    def test_a_broken_loopdata_is_named_not_called_absent(self, monkeypatch, tmp_path,
                                                          source, wanted):
        """A user/loopdata.py present but failing to import (a half-copied
        file, a missing dependency) is reported as such, with the
        exception -- not as 'none is installed', and not as a raw
        traceback."""
        (tmp_path / 'user').mkdir()
        (tmp_path / 'user' / '__init__.py').write_text('')
        (tmp_path / 'user' / 'loopdata.py').write_text(source)
        monkeypatch.delitem(sys.modules, 'user', raising=False)
        monkeypatch.delitem(sys.modules, 'user.loopdata', raising=False)
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.setattr(sys, 'argv', self.INSTALL_ARGV)
        with pytest.raises(SystemExit) as info:
            load_installer().loader()
        message = str(info.value)
        assert 'cannot be imported (' in message
        assert wanted in message
        assert 'none is installed' not in message

    @pytest.mark.parametrize('argv', [
        ['weectl', 'extension', 'list'],
        ['weectl', 'extension', 'uninstall', 'celestial'],
        ['wee_extension', '--list'],
        ['wee_extension', '--uninstall', 'celestial'],
    ])
    @pytest.mark.parametrize('version', [None, '6.11.2'])
    def test_only_an_install_is_gated(self, monkeypatch, argv, version):
        """WeeWX runs the CACHED install.py's loader() for `extension
        list` and `extension uninstall` as well, catching only
        ExtensionError: a SystemExit there would leave a station that
        has since removed or downgraded weewx-loopdata unable to list
        its extensions or to remove this one.  So with loopdata absent
        or too old, everything but an install still gets the
        installer."""
        self._with_loopdata(monkeypatch, version)
        monkeypatch.setattr(sys, 'argv', argv)
        installer = load_installer().loader()
        assert installer['name'] == 'celestial'


class TestInstallerLoopDataFile:
    """The install-time loop_data_file derivation: the page fetches a URL
    relative to ITS report's HTML_ROOT, weewx-loopdata writes a path
    relative to its TARGET report's HTML_ROOT, and the two stock defaults
    do not meet -- the commonest failure this page has (badge: NO DATA
    (HTTP 404)).  weewx.conf holds both halves, so configure() derives
    the answer.  It writes only when there is no setting to respect; an
    existing one is flagged when it disagrees, never rewritten, and a
    file written outside the reports tree is hinted, never guessed at."""

    class _Printer:
        def __init__(self):
            self.lines = []

        def out(self, msg, level=1):
            self.lines.append(msg)

    def _engine(self, config, dry_run=False, weewx_root='/wx'):
        import types
        return types.SimpleNamespace(config_dict=config,
                                     printer=self._Printer(),
                                     dry_run=dry_run,
                                     root_dict={'WEEWX_ROOT': weewx_root},
                                     config_path='/wx/weewx.conf')

    def _installer(self):
        return load_installer().CelestialInstaller()

    @staticmethod
    def _config(file_spec, target_report='LoopDataReport',
                target_root='public_html/loopdata', ours=None):
        """A station with nothing for the declaration step to write
        (empty [Skyfield] sets, and no group to remove), so anything
        printed comes from the step under test."""
        reports = {'HTML_ROOT': 'public_html',
                   target_report: {'HTML_ROOT': target_root}}
        if ours is not None:
            reports['CelestialReport'] = ours
        return {'Skyfield': {'Satellites': {}, 'Comets': {}},
                'StdReport': reports,
                'LoopData': {'FileSpec': file_spec,
                             'Formatting': {'target_report': target_report}}}

    def _derived(self, config, engine=None):
        return config['StdReport']['CelestialReport']['Extras'][
            'loop_data_file']

    def test_derives_the_stock_layout(self):
        """Stock loopdata (loop_data_dir = .) writes into loopdata/;
        stock celestial renders into celestial/.  The page must poll
        ../loopdata/loop-data.txt -- which the derivation writes, so the
        shipped default is never even consulted."""
        config = self._config({'loop_data_dir': '.',
                               'filename': 'loop-data.txt'})
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert self._derived(config) == '../loopdata/loop-data.txt'
        text = '\n'.join(engine.printer.lines)
        assert 'loop_data_file = ../loopdata/loop-data.txt' in text
        assert 'LoopDataReport' in text

    def test_derives_the_web_root_layout(self):
        """loop_data_dir = .. is the other documented arrangement: one
        feed at the web root, shared by every live page."""
        config = self._config({'loop_data_dir': '..'})
        assert self._installer().configure(self._engine(config)) is True
        assert self._derived(config) == '../loop-data.txt'

    def test_follows_the_target_report(self):
        """loop_data_dir is relative to the TARGET report, so a station
        feeding another skin's page lands somewhere else entirely."""
        config = self._config({'loop_data_dir': '.'},
                              target_report='BelchertownReport',
                              target_root='public_html/belchertown')
        assert self._installer().configure(self._engine(config)) is True
        assert self._derived(config) == '../belchertown/loop-data.txt'

    def test_follows_a_custom_filename(self):
        config = self._config({'loop_data_dir': '.',
                               'filename': 'gauge-data.txt'})
        assert self._installer().configure(self._engine(config)) is True
        assert self._derived(config) == '../loopdata/gauge-data.txt'

    def test_follows_our_own_html_root(self):
        """The page's own HTML_ROOT is half the sum: a report nested a
        level deeper climbs a level further."""
        config = self._config(
            {'loop_data_dir': '.'},
            ours={'HTML_ROOT': 'public_html/sky/celestial'})
        assert self._installer().configure(self._engine(config)) is True
        assert self._derived(config) == '../../loopdata/loop-data.txt'

    def test_a_section_without_its_own_html_root_still_measures_right(self):
        """A [[CelestialReport]] that exists but carries no HTML_ROOT --
        someone added `enable = false` by hand, say.  weectl fills the
        HTML_ROOT in moments later (conditional_merge, after configure),
        so measuring from [StdReport]'s root would write a value one
        directory short: `loopdata/loop-data.txt`, which the page then
        fetches as celestial/loopdata/loop-data.txt.  That is the exact
        404 this step exists to prevent."""
        config = self._config({'loop_data_dir': '.'},
                              ours={'enable': 'false'})
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert self._derived(config) == '../loopdata/loop-data.txt'

    def test_a_file_in_our_own_directory_needs_no_tree_at_all(self):
        """Containment is a question about a URL that LEAVES the page's
        directory.  A loop-data file in our own directory -- which is
        where loopdata writes when it targets THIS report -- has a
        certain URL whatever the web server calls its root, so the tree
        question is never asked.  Here our report renders outside
        [StdReport]'s HTML_ROOT, which used to make the installer decline
        and blame loopdata for a refusal our own root had caused."""
        config = self._config({'loop_data_dir': '.'},
                              ours={'HTML_ROOT': '/var/www/html/celestial'})
        config['LoopData']['Formatting'][
            'target_report'] = 'CelestialReport'
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert self._derived(config) == 'loop-data.txt'
        assert 'outside the reports tree' not in '\n'.join(
            engine.printer.lines)

    def test_a_file_below_our_own_directory_is_derived_too(self):
        """Same certainty one level down: the URL still never climbs out
        of the page's own subtree."""
        config = self._config({'loop_data_dir': 'feed'})
        config['LoopData']['Formatting'][
            'target_report'] = 'CelestialReport'
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert self._derived(config) == 'feed/loop-data.txt'

    def test_the_two_senders_note_rides_installs_that_decide(self):
        """A station whose loop_data_file already agrees hears the
        two-senders note once, not at every upgrade for the rest of its
        life: nothing was derived, written or changed, so there is
        nothing to say."""
        def sync_config(loop_data_file):
            config = self._config(
                {'loop_data_dir': '.'},
                ours={'HTML_ROOT': 'public_html/celestial',
                      'Extras': {'loop_data_file': loop_data_file}})
            config['StdReport']['FtpToMyHost'] = {'skin': 'Ftp'}
            config['LoopData']['RsyncSpec'] = {'enable': 'true'}
            return config

        quiet = self._engine(sync_config('../loopdata/loop-data.txt'))
        assert self._installer().configure(quiet) is False
        assert quiet.printer.lines == []

        deciding = self._engine(sync_config('../loop-data.txt'))
        assert self._installer().configure(deciding) is False
        assert 'Worth checking' in '\n'.join(deciding.printer.lines)

    def test_our_own_root_outside_the_tree_is_hinted_too(self):
        """Containment is needed at BOTH ends, and it is measured against
        [StdReport]'s HTML_ROOT.  A report rendering into a web root of
        its own gets the hint rather than a derived value: a shared
        FILESYSTEM ancestor does not say which directory the web server
        serves, so relpath there would be a filesystem answer to a URL
        question -- and one stated as though the installer knew."""
        # Only OUR root is outside: with loopdata's outside too, the
        # first guard fires and this branch is never reached.
        config = self._config({'loop_data_dir': '.'},
                              ours={'HTML_ROOT': '/var/www/html/celestial'})
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        assert 'Extras' not in config['StdReport']['CelestialReport']
        text = '\n'.join(engine.printer.lines)
        assert 'renders into /var/www/html/celestial' in text
        assert 'outside the reports tree' in text
        assert 'where-the-loop-data-file-should-live' in text

    def test_no_two_senders_note_where_no_sync_reaches_the_file(self):
        """The Ftp and Rsync skins copy [StdReport]'s HTML_ROOT.  When
        weewx-loopdata targets THIS report and this report renders into a
        web root of its own, the loop-data file sits beside the page,
        outside the tree those skins copy -- so nobody copies it and
        there are not two senders to warn about."""
        config = self._config({'loop_data_dir': '.'},
                              ours={'HTML_ROOT': '/var/www/html/celestial'})
        config['LoopData']['Formatting']['target_report'] = 'CelestialReport'
        config['LoopData']['RsyncSpec'] = {'enable': 'true'}
        config['StdReport']['FtpToMyHost'] = {'skin': 'Ftp'}
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert self._derived(config) == 'loop-data.txt'
        assert 'Worth checking' not in '\n'.join(engine.printer.lines)

    def test_no_note_fires_when_nothing_was_decided(self):
        """One rule for every note this step prints.  A station that
        already carries a loop_data_file has settled the question -- the
        manual's own recommended arrangement puts the file on a memory
        filesystem behind a web-server alias, a URL this code could never
        derive -- so both out-of-tree notes stay quiet for it.  Telling
        such a station to set the option it has correctly set, at every
        upgrade for the rest of its life, is nagging."""
        for name, ours, spec in (
                ('loopdata outside the tree',
                 {'HTML_ROOT': 'public_html/celestial',
                  'Extras': {'loop_data_file': '/loop-data/loop-data.txt'}},
                 {'loop_data_dir': '/dev/shm/weewx'}),
                ('this report outside the tree',
                 {'HTML_ROOT': '/var/www/html/celestial',
                  'Extras': {'loop_data_file': '/x/loop-data.txt'}},
                 {'loop_data_dir': '.'})):
            config = self._config(spec, ours=ours)
            engine = self._engine(config)
            assert self._installer().configure(engine) is False, name
            assert engine.printer.lines == [], name

        # ... and the same station with nothing set still hears it once.
        config = self._config({'loop_data_dir': '/dev/shm/weewx'})
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        assert 'outside the reports tree' in '\n'.join(engine.printer.lines)

    def test_outside_the_reports_tree_is_hinted_never_guessed(self):
        """/dev/shm, or any directory the web server reaches by alias:
        real layouts whose URL lives in those aliases, not in weewx.conf.
        Say so; never invent a ../../../.. path that is a filesystem
        answer to a URL question."""
        config = self._config({'loop_data_dir': '/home/weewx/loopdata'})
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        assert 'CelestialReport' not in config['StdReport']
        text = '\n'.join(engine.printer.lines)
        assert 'outside the reports tree' in text
        assert '/home/weewx/loopdata/loop-data.txt' in text
        assert 'NO DATA (HTTP 404)' in text

    def test_an_empty_setting_is_no_setting(self):
        """`loop_data_file =` with nothing after it is not a URL anyone
        is relying on.  Treating it as a value to respect printed
        'loop_data_file is , but weewx-loopdata writes where ... points'
        and declined to write -- and disagreed with the rule that quiets
        the notes, which judges the same value with bool()."""
        config = self._config(
            {'loop_data_dir': '.'},
            ours={'HTML_ROOT': 'public_html/celestial',
                  'Extras': {'loop_data_file': ''}})
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert self._derived(config) == '../loopdata/loop-data.txt'
        text = '\n'.join(engine.printer.lines)
        assert 'loop_data_file is ,' not in text
        assert 'Set [StdReport]' in text

    def test_an_agreeing_setting_is_silent(self):
        config = self._config(
            {'loop_data_dir': '.'},
            ours={'HTML_ROOT': 'public_html/celestial',
                  'Extras': {'loop_data_file': '../loopdata/loop-data.txt'}})
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        assert engine.printer.lines == []

    def test_a_disagreeing_setting_is_flagged_never_rewritten(self):
        """An existing value may be answering a web-server alias this
        code cannot see.  Flag the disagreement, leave the line alone."""
        config = self._config(
            {'loop_data_dir': '.'},
            ours={'HTML_ROOT': 'public_html/celestial',
                  'Extras': {'loop_data_file': '../loop-data.txt'}})
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        assert self._derived(config) == '../loop-data.txt'      # untouched
        text = '\n'.join(engine.printer.lines)
        assert '../loop-data.txt' in text and '../loopdata/loop-data.txt' in text
        assert 'never changed' in text

    def test_a_disagreeing_setting_says_when_the_file_is_there(self, tmp_path):
        """The one thing the disk is asked: does the derived path hold a
        file?  Evidence for the reader, never the basis of the choice --
        on a first install the file legitimately does not exist yet."""
        (tmp_path / 'public_html' / 'loopdata').mkdir(parents=True)
        (tmp_path / 'public_html' / 'loopdata' / 'loop-data.txt').write_text(
            '{}')
        config = self._config(
            {'loop_data_dir': '.'},
            ours={'HTML_ROOT': 'public_html/celestial',
                  'Extras': {'loop_data_file': '../loop-data.txt'}})
        engine = self._engine(config, weewx_root=str(tmp_path))
        assert self._installer().configure(engine) is False
        assert 'and that file is there' in '\n'.join(engine.printer.lines)

    def test_dry_run_touches_nothing(self):
        config = self._config({'loop_data_dir': '.'})
        engine = self._engine(config, dry_run=True)
        assert self._installer().configure(engine) is False
        assert 'CelestialReport' not in config['StdReport']
        assert 'Would set' in '\n'.join(engine.printer.lines)

    def test_flags_the_two_senders_without_asserting_a_clash(self):
        """weewx-loopdata sending the file itself while a report sync
        copies the tree it sits in.  Whether those land in the same place
        is not knowable from here -- the transports name destinations
        differently, and an alias defeats a string compare -- so the note
        ASKS.  Advice either way: the value is still derived and
        written."""
        config = self._config({'loop_data_dir': '.'})
        config['StdReport']['FtpToMyHost'] = {'skin': 'Ftp'}
        config['LoopData']['RsyncSpec'] = {'enable': 'true'}
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        text = '\n'.join(engine.printer.lines)
        assert 'FtpToMyHost' in text and 'the same place' in text
        assert 'Worth checking' in text          # asks, never asserts
        assert 'where-the-loop-data-file-should-live' in text
        assert self._derived(config) == '../loopdata/loop-data.txt'

    def test_silent_when_the_report_sync_is_the_only_route(self):
        """An FTP-only station is not misconfigured: the report sync is
        how its pages reach their server at all, so the file belongs in
        the tree and the page updates at report cadence.  Telling that
        user their feed is stale would be noise about a setup that is
        as good as it can be."""
        config = self._config({'loop_data_dir': '.'})
        config['StdReport']['FtpToMyHost'] = {'skin': 'Ftp'}
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert 'Worth checking' not in '\n'.join(engine.printer.lines)

    def test_no_sync_warning_when_that_report_is_disabled(self):
        config = self._config({'loop_data_dir': '.'})
        config['StdReport']['FtpToMyHost'] = {'skin': 'Ftp',
                                              'enable': 'false'}
        config['LoopData']['RsyncSpec'] = {'enable': 'true'}
        engine = self._engine(config)
        assert self._installer().configure(engine) is True
        assert 'Worth checking' not in '\n'.join(engine.printer.lines)

    def test_no_sync_warning_when_the_file_is_outside_the_tree(self):
        """Out of the tree is the arrangement the warning argues for --
        so it has nothing to say, and the note that does fire names the
        manual section rather than leaving the reader to invent it."""
        config = self._config({'loop_data_dir': '/dev/shm/weewx'})
        config['StdReport']['FtpToMyHost'] = {'skin': 'Ftp'}
        config['LoopData']['RsyncSpec'] = {'enable': 'true'}
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        text = '\n'.join(engine.printer.lines)
        assert 'Worth checking' not in text
        assert 'where-the-loop-data-file-should-live' in text

    def test_silent_without_loopdata(self):
        """No [LoopData] at all: the declaration step still declares
        (it reads [Skyfield], not [LoopData]) and this step says nothing
        -- there is nothing to derive from."""
        engine = self._engine({'StdReport': {'HTML_ROOT': 'public_html'}})
        assert self._installer().configure(engine) is True
        text = '\n'.join(engine.printer.lines)
        assert 'Declared 38 satellite fields' in text
        assert 'loop_data_file' not in text

    def test_an_unknown_target_report_is_named(self):
        """target_report naming a report this configuration does not have
        is not a quiet corner: weewx-loopdata logs 'Could not find
        target_report ... LoopData is exiting' and writes nothing, so the
        station has no feed at all.  No HTML_ROOT to measure from, so
        nothing is derived -- but the user hears about it while they are
        reading installer output."""
        config = self._config({'loop_data_dir': '.'})
        config['LoopData']['Formatting']['target_report'] = 'NoSuchReport'
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        assert 'CelestialReport' not in config['StdReport']
        text = '\n'.join(engine.printer.lines)
        assert "target_report names 'NoSuchReport'" in text
        assert 'will not start' in text

    def test_loopdata_targeting_this_report_derives_a_bare_filename(self):
        """weewx-loopdata pointed at THIS report -- the natural move for a
        station whose loop values must carry this report's [Almanac]
        names.  loop_data_dir is then relative to our OWN HTML_ROOT, so
        the file lands beside the page and the URL is its bare name.
        Three shapes, one answer: no section yet (weectl injects it
        seconds from now), a section without an HTML_ROOT of its own, and
        a section carrying one."""
        for ours in (None, {'enable': 'false'},
                     {'HTML_ROOT': 'public_html/celestial'}):
            config = self._config({'loop_data_dir': '.'}, ours=ours)
            config['LoopData']['Formatting'][
                'target_report'] = 'CelestialReport'
            engine = self._engine(config)
            assert self._installer().configure(engine) is True, ours
            assert self._derived(config) == 'loop-data.txt', ours
            assert 'will not start' not in '\n'.join(engine.printer.lines)

    def test_never_fails_the_install(self):
        config = self._config({'loop_data_dir': 3.14})
        engine = self._engine(config)
        assert self._installer().configure(engine) is False
        assert any('Could not work out where weewx-loopdata writes' in line
                   for line in engine.printer.lines)

    def test_written_value_survives_weectls_own_merge(self):
        """The load-bearing weectl facts, pinned because the derivation
        rests on them: install_from_dir calls configure() BEFORE
        _inject_config, and _inject_config merges conditionally.  So a
        value written here stands and this installer's shipped default is
        only the fallback.  Were the order to
        reverse, or the merge become unconditional, every derived value
        would be silently overwritten with the default that 404s."""
        import inspect
        import weecfg.extension
        import weeutil.config
        from copy import deepcopy
        source = inspect.getsource(weecfg.extension.ExtensionEngine
                                   .install_from_dir)
        assert (source.index('installer.configure(')
                < source.index('_inject_config(')), source
        assert 'conditional_merge' in inspect.getsource(
            weecfg.extension.ExtensionEngine._inject_config)
        # And conditional_merge really does leave a present value alone.
        config = self._config({'loop_data_dir': '.'})
        assert self._installer().configure(self._engine(config)) is True
        weeutil.config.conditional_merge(
            config,
            # EXACTLY what install.py injects, read from the installer
            # itself: a simulation of the merge that used a value the
            # installer no longer ships proves nothing about the real one.
            {'StdReport': {'CelestialReport': deepcopy(
                self._installer()['config']['StdReport']['CelestialReport'])}})
        assert self._derived(config) == '../loopdata/loop-data.txt'
        assert config['StdReport']['CelestialReport']['Extras'][
            'refresh_rate'] == 2        # the rest of the stanza still lands



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

# The bodies the Geocentric dial places, in PAGE_FIELDS order.
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
        import configobj
        import io
        page = _doc_text('fields-reference.md')
        shown = configobj.ConfigObj(io.StringIO(
            _block_containing(page, 'clock = current.dateTime.raw')))
        declared = [f for value in shown['LoopData']['fields'].values()
                    for f in ([value] if isinstance(value, str) else value)]
        assert len(declared) == len(celestial.static_page_fields()), (
            'the shipped-declaration block parsed to %d entries' % len(declared))
        assert 'almanac.sun.az' in declared and 'almanac.next_eclipse_kind' in declared
        stanza = configobj.ConfigObj(io.StringIO(
            _block_containing(page, 'satellites = almanac.iss.az')))
        groups = stanza['StdReport']['CelestialReport']['LoopData']['fields']
        assert len(groups['satellites']) == 38 and len(groups['comets']) == 12
        assert 'almanac.hale_bopp.mag' in groups['comets']

        texts = _ini_pairs(_block_containing(_doc_text('i18n-dictionary.md'), '"LIVE"'))
        assert len(texts) > 70, 'the dictionary block parsed to %d entries' % len(texts)
        assert ('LIVE', 'LIVE') in texts

        heads = _headings(_doc_text('reading-the-page.md'))
        assert 'The Geocentric' in heads and 'The sky dome' in heads

    def test_installer_placement_url_names_a_real_heading(self):
        """install.py prints a manual URL at the one moment a user is
        looking straight at this problem -- the loop-data file landing
        outside the reports tree, or inside a tree a report sync copies.
        A hand-written anchor no heading generates is a dead link, and
        nothing else on either side would catch it."""
        with open(os.path.join(REPO_ROOT, 'install.py'), encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'configuration\.html#([a-z0-9-]+)', src)
        assert m, 'install.py no longer names the placement section'
        anchors = {_heading_anchor(h)
                   for h in _headings(_doc_text('configuration.md'))}
        assert m.group(1) in anchors, (
            'install.py points at #%s, which configuration.md does not '
            'generate: %s' % (m.group(1), sorted(anchors)))

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

    def test_fields_reference_prints_the_shipped_declaration(self):
        """docs/fields-reference.md prints the skin.conf declaration as
        shipped, so it must BE skins/Celestial/skin.conf's [LoopData]
        section -- groups, entries and order, comments aside -- and the
        weewx.conf stanza it prints for the installer's defaults must be
        what declare_page_fields writes for them.  Both directions."""
        import configobj
        import io
        page = _doc_text('fields-reference.md')
        shown = configobj.ConfigObj(io.StringIO(
            _block_containing(page, 'clock = current.dateTime.raw')))
        shipped = configobj.ConfigObj(os.path.join(SKIN_DIR, 'skin.conf'),
                                      encoding='utf-8', file_error=True)
        assert list(shown) == ['LoopData']
        assert dict(shown['LoopData']['fields']) == dict(shipped['LoopData']['fields'])
        assert list(shown['LoopData']['fields']) == list(shipped['LoopData']['fields']), \
            'same groups, different order'
        stanza = configobj.ConfigObj(io.StringIO(
            _block_containing(page, 'satellites = almanac.iss.az')))
        written = configobj.ConfigObj()
        celestial.declare_page_fields(written, ensure_default=True)
        assert (dict(stanza['StdReport']['CelestialReport']['LoopData']['fields'])
                == dict(written['StdReport']['CelestialReport']['LoopData']['fields']))

    def test_fields_reference_per_tag_patterns(self):
        """The nineteen-entry satellite and six-entry comet patterns are
        the code's own, with the tag substituted."""
        # The needles name the pattern blocks' line breaks: the installer's
        # stanza carries the same entries on one line each.
        page = _doc_text('fields-reference.md')
        sat = _fields_in(_block_containing(
            page, 'almanac.iss.label,\nalmanac.iss.next_visible_pass'))
        assert sat == celestial.satellite_fields('iss')
        comet = _fields_in(_block_containing(
            page, 'almanac.halley.label,\nalmanac.halley.perihelion'))
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
        expected = set(celestial.PAGE_FIELDS) - accounted

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
                assert re.match(r'(Partly r|R)eviewed as of \d+\.\d+(\.\d+)? ', row), \
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
        """{option: default} from the shipped skin.conf: the [Extras]
        block, plus the REPORT-level options above the first section --
        `lang`, and `theme` since 8.3.  Those two are not in [Extras] (a
        report option, not a skin extra: weewx-skyfield reads `theme`
        out of the report's own skin dict), and a harness that only
        looked in [Extras] would let a root option ship undocumented."""
        path = os.path.join(REPO_ROOT, 'skins', 'Celestial', 'skin.conf')
        with open(path, encoding='utf-8') as f:
            text = f.read()
        blocks = [re.split(r'^\[', text.split('[Extras]', 1)[1], flags=re.M)[0],
                  re.split(r'^\[', text, flags=re.M)[0]]
        out = {}
        for body in blocks:
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
        # 'HTML_ROOT = celestial', not 'CelestialReport': the page names
        # the report in a second block too (the loop-data placement
        # section's absolute-URL example), and only the installer's own
        # stanza carries the report's HTML_ROOT.
        sample = _block_containing(page, 'HTML_ROOT = celestial')
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
        sample = _block_containing(_doc_text('configuration.md'),
                                   'HTML_ROOT = celestial')
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

        # The two groups configure() writes are not in the config dict
        # (they follow the station's [Skyfield] sets), and the stanza
        # must show them: a reader cribbing from it needs the whole
        # shape of what a fresh install writes.
        invented = set(documented) - set(shipped)
        assert {'satellites', 'comets'} <= invented, (
            'the sample stanza no longer shows the satellites/comets groups '
            'the installer writes')
        invented -= {'satellites', 'comets'}
        assert invented == set(), (
            'the sample stanza shows settings a fresh install does not '
            'write: %s' % sorted(invented))

    def test_skin_conf_ships_the_installers_defaults(self):
        """Two files answer the same question -- skins/Celestial/skin.conf's
        [Extras] and install.py's config dict -- and weewx.conf's copy is
        the one report time reads (build_skin_dict merges the report's
        stanza last).  So a skin.conf that drifts is invisible: it breaks
        nothing until someone reads it as documentation, cribs from it, or
        deletes the weewx.conf entry.  weewx-loopdata shipped exactly that
        drift on loop_data_file, found 2026-08-22.  Every option both
        files declare must agree."""
        import configobj
        extras = configobj.ConfigObj(os.path.join(SKIN_DIR, 'skin.conf'),
                                     encoding='utf-8',
                                     file_error=True)['Extras']
        shipped = self._installer_config_pairs()
        shared = [name for name in extras if name in shipped]
        assert 'loop_data_file' in shared and len(shared) >= 4, shared
        wrong = {name: (extras[name], str(shipped[name])) for name in shared
                 if str(extras[name]) != str(shipped[name])}
        assert wrong == {}, (
            'skin.conf and install.py disagree (skin.conf, install.py): %s'
            % wrong)

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
            # A #fragment is not part of the path Pages serves: judge the
            # page, or an anchored deep link reads as a trailing-slash
            # 404 that isn't one (and skips the page-exists check below).
            url = url.split('#', 1)[0]
            path = url.split('github.io/', 1)[1]
            page = path.split('/', 1)[1] if '/' in path else ''
            if page == '' or url.endswith('.html'):
                continue
            bad.append('%s -> %s' % (name, url))
        assert not bad, (
            'links to a published manual must be the site root or end in '
            '.html; these will 404 or depend on a fallback:\n  '
            + '\n  '.join(bad))

    def test_referenced_images_exist(self):
        """Every image the README and the manual show must be a file this
        repository ships.  The manual reaches its images over
        raw.githubusercontent, which serves master -- so a screenshot
        that is renamed, or referenced before it is committed, is a
        broken image on the published site and no link check sees it
        (the link tests read hrefs, not img sources)."""
        sources = {'README.md': os.path.join(REPO_ROOT, 'README.md')}
        for name in sorted(os.listdir(DOCS_DIR)):
            if name.endswith('.md'):
                sources[name] = os.path.join(DOCS_DIR, name)
        raw = 'https://raw.githubusercontent.com/chaunceygardiner/weewx-celestial/master/'
        seen, missing = 0, []
        for name, path in sources.items():
            with open(path, encoding='utf-8') as f:
                text = f.read()
            for src in re.findall(r'!\[[^\]]*\]\(([^)\s]+)\)', text):
                if src.startswith(raw):
                    target = os.path.join(REPO_ROOT, src[len(raw):])
                elif src.startswith('http'):
                    continue            # someone else's image; not ours to pin
                else:
                    target = os.path.join(os.path.dirname(path), src)
                seen += 1
                if not os.path.exists(target):
                    missing.append('%s -> %s' % (name, src))
        assert seen >= 10, 'image extractor found too few images (%d)' % seen
        assert not missing, ('the manual shows images this repo does not '
                             'ship:\n  ' + '\n  '.join(missing))

    def test_links_to_our_own_manual_name_pages_that_exist(self):
        """An .html URL into celestial's own manual must correspond to a
        page in docs/ -- otherwise it is well-formed and still dead."""
        pages = {f[:-3] + '.html' for f in os.listdir(DOCS_DIR) if f.endswith('.md')}
        pages.add('index.html')
        missing = []
        for name, url in self._absolute_site_links():
            url = url.split('#', 1)[0]      # the anchor is not a filename
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
