# Copyright 2022-2026 by John A Kline <john@johnkline.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import os
import sys
import weewx
from setup import ExtensionInstaller

def loader():
    if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 9):
        sys.exit("weewx-celestial requires Python 3.9 or later, found %s.%s" % (
            sys.version_info[0], sys.version_info[1]))

    # Compare on (major, minor).  A version string whose leading components
    # are not plain integers (e.g., a dev build) is given the benefit of the
    # doubt.
    try:
        parts = weewx.__version__.split('.')
        weewx_version = (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except ValueError:
        weewx_version = None
    if weewx_version is not None and weewx_version < (5, 2):
        sys.exit("weewx-celestial requires WeeWX 5.2 or later, found %s" % weewx.__version__)

    return CelestialInstaller()

class CelestialInstaller(ExtensionInstaller):
    def __init__(self):
        super(CelestialInstaller, self).__init__(
            version = "8.0",
            name = 'celestial',
            description = 'A live celestial report driven by weewx-loopdata almanac fields.',
            author = "John A Kline",
            author_email = "john@johnkline.com",
            config = {
                'StdReport': {
                    'CelestialReport': {
                        'HTML_ROOT':'celestial',
                        'enable': 'true',
                        'skin':'Celestial',
                        'Extras': {
                            'loop_data_file'   : '../loop-data.txt',
                            'refresh_rate'     : 2,
                            'expiration_time'  : 24,
                            'page_update_pwd'  : 'foobar',
                        },
                    },
                },
            },
            files = [
                ('bin/user', [
                    'bin/user/celestial.py',
                    'bin/user/celestial_sky.py',
                    ]),
                ('skins/Celestial', [
                    'skins/Celestial/celestial.css',
                    'skins/Celestial/dome-svg.txt.tmpl',
                    'skins/Celestial/dome-svg-1.txt.tmpl',
                    'skins/Celestial/dome-svg-2.txt.tmpl',
                    'skins/Celestial/dome-svg-3.txt.tmpl',
                    'skins/Celestial/dome-svg-4.txt.tmpl',
                    'skins/Celestial/dome-svg-5.txt.tmpl',
                    'skins/Celestial/dome-svg-6.txt.tmpl',
                    'skins/Celestial/dome-svg-7.txt.tmpl',
                    'skins/Celestial/dome-svg-8.txt.tmpl',
                    'skins/Celestial/dome-svg-9.txt.tmpl',
                    'skins/Celestial/dome-svg-frag.inc',
                    'skins/Celestial/index.html.tmpl',
                    'skins/Celestial/pass-chart.txt.tmpl',
                    'skins/Celestial/realtime_updater.inc',
                    'skins/Celestial/skin.conf',
                    'skins/Celestial/sky.js',
                    ]),
                ('skins/Celestial/lang', [
                    'skins/Celestial/lang/en.conf',
                    'skins/Celestial/lang/de.conf',
                    'skins/Celestial/lang/fr.conf',
                    'skins/Celestial/lang/nl.conf',
                    'skins/Celestial/lang/es.conf',
                    'skins/Celestial/lang/da.conf',
                    'skins/Celestial/lang/it.conf',
                    'skins/Celestial/lang/no.conf',
                    'skins/Celestial/lang/sv.conf',
                    ]),
            ])

    def configure(self, engine):
        """Compare the station's [LoopData] [[Include]] fields line with
        what the sample page reads and, when entries are missing (or
        pre-6.0 names linger), print the --migrate-loopdata-fields
        commands that fix it.  A hint only: weectl's conditional merge
        cannot append into another extension's comma-list value, so the
        installer never edits [LoopData] itself.  The bundled migrator
        runs in memory as the oracle -- one source of truth for the field
        set, the configuration's own [Skyfield] [[Satellites]] included.
        Never modifies the configuration (always returns False), and
        never fails the install."""
        try:
            self._print_fields_hint(engine)
        except Exception as e:
            engine.printer.out('Could not check the [LoopData] fields line '
                               '(%s); the README shows what the page reads.' % e)
        return False

    def _print_fields_hint(self, engine):
        celestial = self._load_bundled_celestial()
        config = engine.config_dict
        try:
            fields = config['LoopData']['Include']['fields']
        except KeyError:
            engine.printer.out(
                'Note: no [LoopData] [[Include]] fields entry found.  The '
                "page's live values are weewx-loopdata almanac fields; "
                'install weewx-loopdata, then run the bundled '
                '--migrate-loopdata-fields utility to write the fields line '
                '(the README shows the commands).')
            return
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split(',') if f.strip()]
        _, report = celestial.migrate_loopdata_fields(
            list(fields), celestial._configured_satellites(config))
        gaps = []
        if report['added']:
            gaps.append('is missing %d entries the page reads'
                        % len(report['added']))
        if report['renamed']:
            gaps.append('carries %d entries with outdated spellings'
                        % len(report['renamed']))
        if not gaps:
            return
        config_path = getattr(engine, 'config_path', '/home/weewx/weewx.conf')
        # The user package's parent: WEEWX_ROOT/bin, exactly where
        # _gen_file_paths just put this extension's 'bin/user' files.
        bin_dir = os.path.abspath(os.path.join(
            engine.root_dict.get('WEEWX_ROOT', '/home/weewx'), 'bin'))
        engine.printer.out(
            'Note: the [LoopData] [[Include]] fields line %s.  This installer '
            'never edits [LoopData]; the bundled migrator updates the line in '
            'one idempotent pass:' % ' and '.join(gaps))
        engine.printer.out('    cd %s' % bin_dir)
        engine.printer.out('    %s -m user.celestial --migrate-loopdata-fields '
                           '--config %s --output /tmp/weewx.conf.migrated'
                           % (sys.executable, config_path))
        engine.printer.out('    git diff --no-index --word-diff %s '
                           '/tmp/weewx.conf.migrated' % config_path)
        engine.printer.out('Review the changes (the utility lists each one; '
                           'the word-diff shows them in place -- a plain diff '
                           'is unreadable on one long fields line), then move '
                           'the file into place.  See the README for detail.')

    @staticmethod
    def _load_bundled_celestial():
        """The bundled celestial.py, imported from this extension's own
        tree (beside this install.py) under a private module name: the
        migrator is the field-set oracle, and this hint must never
        duplicate it."""
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'bin', 'user', 'celestial.py')
        spec = importlib.util.spec_from_file_location(
            '_celestial_install_hint', path)
        if spec is None or spec.loader is None:
            raise ImportError('cannot load %s' % path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
