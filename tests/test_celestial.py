"""
test_celestial.py

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Tests for weewx-celestial 7.0: the bundled Celestial skin (the live
Geocentric panel, rendered end to end through Cheetah's errorCatcher) and
the --migrate-loopdata-fields utility that rewrites a pre-6.0
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
import re
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
        """7.0 removed the 6.x service stub and the CelestialSkyPage shim;
        neither name may quietly return (weectl uninstall is the prescribed
        upgrade path, and the skin embeds no $sky_page)."""
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


class TestSampleSkinRenders:
    """Render the bundled sample skin end to end, through Cheetah's
    errorCatcher, exactly as weewx does.  Template.compile alone is NOT
    enough: with #errorCatcher Echo, Cheetah re-compiles each placeholder's
    source at render time, and that path rejects constructs plain
    compilation accepts (e.g. a conditional expression inside $(...) loses
    its else-value and dies with SyntaxError only at render time)."""

    @staticmethod
    def render(almanac_obj, with_time_zone=True):
        from Cheetah.Template import Template

        class Obj:
            def __init__(self, **kw):
                self.__dict__.update(kw)

        class Extras(dict):
            def has_key(self, key):
                return key in self

        source = open(os.path.join(SKIN_DIR, 'index.html.tmpl')).read()
        # Inline the include so its directives and placeholders are also
        # exercised through the errorCatcher render path.
        include = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        assert '#include "realtime_updater.inc"' in source
        source = source.replace('#include "realtime_updater.inc"', include)
        extras = Extras(loop_data_file='/gauge-data/loop-data.txt',
                        expiration_time=86400, refresh_rate=2,
                        version=celestial.CELESTIAL_VERSION)
        if with_time_zone:
            extras['time_zone'] = 'America/Los_Angeles'
        template = Template(source, searchList=[{
            'almanac': almanac_obj,
            'current': Obj(dateTime=Obj(raw=TIME_TS)),
            # windrun stands in for group_distance (this extension registers
            # no observation types).
            'unit': Obj(label=Obj(windrun=' miles'),
                        unit_type=Obj(windrun='mile')),
            'station': Obj(location='Test Station',
                           stn_info=Obj(latitude_f=LATITUDE, longitude_f=LONGITUDE)),
            'Extras': extras,
        }])
        return str(template)

    def cell(self, html, cell_id):
        match = re.search(r'id="%s"[^>]*>([^<]*)<' % re.escape(cell_id), html)
        assert match is not None, cell_id
        return match.group(1)

    def test_renders_with_skyfield_almanac(self, wxskyfield_almanac):
        html = self.render(wxskyfield_almanac)
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
        # catalog).
        assert 'skyhint' not in html
        assert 'Hipparcos' in html

    def test_javascript_reads_only_the_field_set(self):
        """The javascript's loop-data keys, expanded the way the include
        builds them (a per-body prefix plus .az/.alt/.earth_distance, and
        the literal moon-phase and dateTime keys), must equal
        _MIGRATION_NEW_FIELDS exactly -- the skin consumes the whole
        migrated field set and nothing else."""
        include = open(os.path.join(SKIN_DIR, 'realtime_updater.inc')).read()
        bodies = re.findall(r"\['([a-z_]+)',\s*'[A-Za-z]+'\]", include)
        assert len(bodies) == 11
        keys = set()
        for body in bodies:
            for suffix in ('.az', '.alt', '.earth_distance'):
                keys.add('almanac.%s%s' % (body, suffix))
        # The literal (non-constructed) keys the include reads.
        for literal in ('current.dateTime.raw', 'almanac.moon.phase',
                        'almanac.next_full_moon.raw', 'almanac.next_new_moon.raw'):
            assert "'%s'" % literal in include or '"%s"' % literal in include, literal
            keys.add(literal)
        assert keys == set(celestial._MIGRATION_NEW_FIELDS)

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

    def test_page_runs_in_a_real_browser(self, wxskyfield_almanac, tmp_path):
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
                 'almanac.next_full_moon.raw': alm.next_full_moon.raw,
                 'almanac.next_new_moon.raw': alm.next_new_moon.raw}
            for b in bodies:
                obj = getattr(alm, b)
                r['almanac.%s.az' % b] = obj.az
                r['almanac.%s.alt' % b] = obj.alt
                r['almanac.%s.earth_distance' % b] = obj.earth_distance
            packets.append(jsonlib.dumps(r).encode())

        (tmp_path / 'index.html').write_text(self.render(wxskyfield_almanac))
        (tmp_path / 'celestial.css').write_bytes(
            open(os.path.join(SKIN_DIR, 'celestial.css'), 'rb').read())

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
        # An extended almanac serves the page: no install hint; the footer
        # must NOT claim Skyfield or the star catalog.
        assert 'skyhint' not in html
        assert 'Hipparcos' not in html
        assert "extended almanac" in html

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
        assert html.count('class="skyhint"') == 1
        assert 'https://github.com/chaunceygardiner/weewx-skyfield' in html
        assert "built-in almanac" in html
        assert 'Hipparcos' not in html
        auto_tz = ''
        try:
            auto_tz = os.readlink('/etc/localtime').split('zoneinfo/')[-1]
        except OSError:
            try:
                auto_tz = open('/etc/timezone').read().strip()
            except OSError:
                pass
        assert "time_zone = '%s'" % auto_tz in html


class TestMigrateLoopdataFields:
    """The --migrate-loopdata-fields utility: rewrites celestial loop-field
    entries (including pre-3.0 PascalCase names) to weewx-loopdata almanac
    entries in place, drops moonWaxing and the duplicates the rewrites
    create, appends the current sample-report fields, and touches nothing
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
        assert 'almanac.mars.az' in fields          # sample-report fields appended
        assert 'almanac.proxima_centauri.az' in fields
        # The rest of the configuration survives the round trip.
        assert migrated['Station']['location'] == 'Test Station'
        # The original file is untouched.
        assert 'current.Sunrise.raw' in conf.read_text()
