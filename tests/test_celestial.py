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

# When the identity check proves weewx-skyfield itself serves the page, the
# footer credit names it and links its project page -- in every language.
# (The skyhint's install pointer uses the same anchor, so footer-linkage
# assertions must key on the credit phrasing, not this string alone.)
LINKED_NAME = ('<a href="https://github.com/chaunceygardiner/weewx-skyfield">'
               'weewx-skyfield</a>')

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
    def render(almanac_obj, with_time_zone=True, lang='en', texts=None, labels=None):
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
                           latitude=('37', '26.55',
                                     hemis[0] if LATITUDE >= 0 else hemis[1]),
                           longitude=('122', '08.45',
                                      hemis[2] if LONGITUDE >= 0 else hemis[3]),
                           stn_info=Obj(latitude_f=LATITUDE, longitude_f=LONGITUDE)),
            'Extras': extras,
            'lang': lang,
            'gettext': lambda key: texts.get(key, key),
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
        # catalog) -- naming weewx-skyfield with its manual linked, since
        # the identity check proves it is truly ours.
        assert 'skyhint' not in html
        assert 'Hipparcos' in html
        assert 'Calculated with %s: Skyfield' % LINKED_NAME in html

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
        assert keys == set(celestial._MIGRATION_NEW_FIELDS)
        # The pre-7.6 unpinned moon keys survive as read fallbacks, so a
        # fields line migrated under <= 7.5 keeps working across the
        # upgrade with no weewx.conf change.
        for legacy in ('almanac.next_full_moon.raw', 'almanac.next_new_moon.raw'):
            assert "'%s'" % legacy in include or '"%s"' % legacy in include, legacy

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
                 'almanac.next_full_moon.unix_epoch.raw': alm.next_full_moon.raw,
                 'almanac.next_new_moon.unix_epoch.raw': alm.next_new_moon.raw}
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
        # must NOT claim Skyfield or the star catalog, and the generic
        # credit's mention of weewx-skyfield stays unlinked -- PyEphem may
        # be the engine serving the page.
        assert 'skyhint' not in html
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
        assert html.count('class="skyhint"') == 1
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

    @staticmethod
    def lang_conf(dirname, name):
        configobj = pytest.importorskip('configobj')
        return configobj.ConfigObj(os.path.join(dirname, name),
                                   encoding='utf-8', file_error=True)

    @staticmethod
    def rendered_keys():
        """Every translation key the page can render, read from the
        $gettext("...")/$gettext('...') literals in the template and the
        include (keys are single-line literals by convention)."""
        keys = set()
        for name in ('index.html.tmpl', 'realtime_updater.inc'):
            with open(os.path.join(SKIN_DIR, name), encoding='utf-8') as f:
                found = re.findall(r'\$gettext\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)',
                                   f.read())
            assert found, name
            keys |= {a or b for a, b in found}
        return keys

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

    def test_lang_files_in_step_with_skyfield(self):
        """The shared vocabulary is copied verbatim from weewx-skyfield's
        lang files (German and French native-speaker reviewed; Danish
        contributed by a native speaker; Dutch and Spanish Beta): body
        names, moon phases, hemispheres, ordinates, all 88 constellation
        names, and every [Texts] key both pages render -- the same
        cross-repo rule as celestial.css staying in step with sky.css.
        Skips when no weewx-skyfield lang directory is available."""
        candidates = [
            os.path.join(os.path.dirname(REPO_ROOT), 'weewx-skyfield',
                         'skins', 'Skyfield', 'lang'),
            '/home/weewx/weewx-data/skins/Skyfield/lang',
        ]
        sky_lang = next((d for d in candidates
                         if os.path.exists(os.path.join(d, 'de.conf'))), None)
        if sky_lang is None:
            pytest.skip('the weewx-skyfield lang directory is not available')
        for name in ('en.conf', 'de.conf', 'fr.conf', 'nl.conf', 'es.conf',
                     'da.conf'):
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
        # The rest of the configuration survives the round trip.
        assert migrated['Station']['location'] == 'Test Station'
        # The original file is untouched.
        assert 'current.Sunrise.raw' in conf.read_text()
