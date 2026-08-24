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
            version = "8.4",
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
                            'loop_data_file'   : '../loopdata/loop-data.txt',
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
        """Two install-time steps, each independently guarded, each
        APPEND-ONLY in the sense that matters: nothing a user already
        has is rewritten.

        1. Bring the station's [LoopData] [[Include]] fields line up to
        date with what the sample page reads.  Entries the page reads
        that are missing from the line are appended in place (an append
        cannot break another page's consumption of the same line;
        weectl saves the modified configuration and keeps its own
        backup) -- existing entries are never renamed, removed or
        reordered.  The migrator's destructive half (pre-6.0 renames,
        drops) stays behind the human-reviewed --migrate-loopdata-fields
        flow and is only hinted.  The bundled migrator runs in memory as
        the oracle -- one source of truth for the field set, the
        configuration's own [Skyfield] [[Satellites]] and [[Comets]]
        included.

        2. Point the page at wherever weewx-loopdata actually writes,
        derived from the configuration rather than guessed.

        Honors weectl's dry run.  Returns True exactly when the
        configuration was modified; either step failing degrades to a
        note, never a failed install."""
        modified = False
        try:
            modified |= self._update_fields(engine)
        except Exception as e:
            engine.printer.out('Could not check the [LoopData] fields line '
                               '(%s); the README shows what the page reads.' % e)
        try:
            modified |= self._set_loop_data_file(engine)
        except Exception as e:
            engine.printer.out('Could not work out where weewx-loopdata '
                               'writes (%s); if the page\'s badge reads NO '
                               'DATA (HTTP 404), loop_data_file is the line '
                               'to fix (see the README).' % e)
        return modified

    def _set_loop_data_file(self, engine):
        """Derive Extras loop_data_file -- the URL the page polls -- from
        where weewx-loopdata is configured to write.

        The page fetches loop_data_file relative to ITS report's
        HTML_ROOT; weewx-loopdata writes [LoopData] [[FileSpec]]
        loop_data_dir relative to its TARGET report's HTML_ROOT.  Two
        different reports, so a shipped default can only be right for
        the layout it was chosen for -- the stock one, both extensions
        untouched -- and a station that has moved either half 404s,
        which is the commonest failure this page has.  weewx.conf holds
        both halves, so the answer is arithmetic, not a search: a file
        found on disk would not give its URL anyway.

        Writes only when there is no setting to respect.  configure()
        runs BEFORE weectl merges this installer's own config, and that
        merge is conditional (weeutil.config.conditional_merge fills in
        only what is absent), so a value written here stands and the
        shipped default becomes the fallback for a station this cannot
        read.  An existing setting is never rewritten -- it may be
        answering a web-server alias this code cannot see -- only
        flagged when it disagrees.  Returns True exactly when the
        configuration was modified."""
        config = engine.config_dict
        if 'LoopData' not in config:
            return False        # the fields step has already said its piece
        reports = config.get('StdReport')
        if not reports:
            return False        # no reports at all: nothing certain to say
        file_spec = config['LoopData'].get('FileSpec', {})
        target = config['LoopData'].get('Formatting', {}).get(
            'target_report', 'LoopDataReport')

        weewx_root = engine.root_dict.get('WEEWX_ROOT', '')
        # A report's HTML_ROOT is either its own or [StdReport]'s, and is
        # relative to WEEWX_ROOT (os.path.join honors an absolute one).
        reports_root = reports.get('HTML_ROOT', 'public_html')

        def html_root(section):
            return os.path.normpath(os.path.join(
                weewx_root, section.get('HTML_ROOT', reports_root)))

        ours = reports.get('CelestialReport')
        if ours is not None and 'HTML_ROOT' in ours:
            our_root = html_root(ours)
        else:
            # Either no section yet (a first install) or one without an
            # HTML_ROOT of its own.  Both end the same way: weectl is
            # about to inject this installer's HTML_ROOT under
            # [StdReport]'s, which is what ExtensionEngine.prepend_path
            # does, and conditional_merge fills it in because it is
            # absent.  Measuring from [StdReport]'s root instead would
            # write a value one directory short -- the 404 this whole
            # step exists to prevent.
            our_root = os.path.normpath(os.path.join(
                weewx_root, reports_root,
                self['config']['StdReport']['CelestialReport']['HTML_ROOT']))

        if target == 'CelestialReport':
            # weewx-loopdata targets THIS report -- the natural move for a
            # station whose loop values must carry this report's [Almanac]
            # names.  It writes relative to our own HTML_ROOT, which is
            # the root just worked out, and that answer holds in all three
            # shapes: no section yet (a first install), a section without
            # an HTML_ROOT of its own, and a section carrying one.  Asking
            # html_root() for it instead would be right only in the third.
            target_root = our_root
        elif target not in reports:
            # weewx-loopdata logs 'Could not find target_report ... LoopData
            # is exiting' and writes nothing at all, so this station has no
            # feed to point at.  Worth a line at the one moment the user is
            # reading installer output.
            engine.printer.out(
                "Note: [LoopData] [[Formatting]] target_report names '%s', "
                'which this configuration does not have -- weewx-loopdata '
                'will not start, so where it would write cannot be worked '
                'out here.  The shipped loop_data_file default stands.'
                % target)
            return False
        else:
            target_root = html_root(reports[target])

        where = os.path.normpath(os.path.join(
            target_root, file_spec.get('loop_data_dir', '.')))
        written = os.path.join(where, file_spec.get('filename',
                                                    'loop-data.txt'))

        # Containment is a question about a URL that LEAVES the page's
        # own directory, and only about that.  A loop-data file in our
        # own directory, or below it, has a certain URL whatever the web
        # server calls its root -- the relative path never climbs out --
        # so no tree question arises and none is asked.
        #
        # For a URL that does climb out, BOTH ends have to sit under
        # [StdReport]'s HTML_ROOT for it to mean anything.  /dev/shm, a
        # loop-data directory of its own, a report rendering into a web
        # root of its own: all real layouts, and in every one of them
        # only the web server's aliases say what URL reaches what.  A
        # shared FILESYSTEM ancestor is not an answer -- weewx.conf
        # cannot say which directory is the web root -- and relpath would
        # invent one anyway (../../../../var/www/...).  Declining costs a
        # note; guessing costs a page that says NO DATA while the
        # installer insists it set the right value.
        served = os.path.normpath(os.path.join(weewx_root, reports_root))

        def under(root, path):
            return path == root or path.startswith(root + os.sep)

        # NO note in this step fires when nothing was decided.  A station
        # that already carries a loop_data_file has settled this question
        # -- the recommended /dev/shm arrangement carries an aliased URL
        # this code could never derive -- so telling it again at every
        # upgrade, for the rest of its life, is nagging about a setting
        # the user made correctly.  The same test governs the two-senders
        # note below.
        settled = bool((ours or {}).get('Extras', {}).get('loop_data_file'))

        if not under(our_root, where):
            if not under(served, where):
                if settled:
                    return False
                engine.printer.out(
                    'Note: weewx-loopdata writes %s, outside the reports '
                    'tree (%s), so the URL serving it cannot be derived '
                    "here.  If the page's badge reads NO DATA (HTTP 404), "
                    'set [StdReport] [[CelestialReport]] [[[Extras]]] '
                    'loop_data_file to the URL your web server maps it to: '
                    '%s' % (written, served, self._PLACEMENT_URL))
                return False
            if not under(served, our_root):
                if settled:
                    return False
                engine.printer.out(
                    'Note: this report renders into %s, outside the reports '
                    'tree (%s), so the URL from it to %s cannot be derived '
                    'here.  Set [StdReport] [[CelestialReport]] [[[Extras]]] '
                    'loop_data_file to the URL your web server maps that '
                    'file to: %s' % (our_root, served, written,
                                     self._PLACEMENT_URL))
                return False

        # A URL, not a path: separators stay forward slashes.
        derived = os.path.relpath(written, our_root).replace(os.sep, '/')
        extras = ours.get('Extras') if ours is not None else None
        current = extras.get('loop_data_file') if extras else None

        if current == derived:
            return False        # nothing decided here, so nothing to say

        # A file in the reports tree travels with the report sync, and
        # weewx-loopdata may be sending the same file itself.  Whether
        # that is a problem turns on where the two DESTINATIONS are, and
        # this code cannot tell: the transports name them differently,
        # and an alias or a symlink defeats comparing the strings.  So
        # the note asks rather than asserts.  Where loopdata is not
        # sending the file at all, the report sync is simply how it
        # travels and there is nothing to say -- say nothing.  It rides
        # with an install that DECIDES something, above: a station whose
        # setting already agrees hears this once, not at every upgrade
        # for the rest of its life.
        # ... and only where a report sync REACHES the file.  The Ftp
        # and Rsync skins copy [StdReport]'s HTML_ROOT; a loop-data file
        # outside it -- the file beside this page when weewx-loopdata
        # targets this report, and this report renders into a web root of
        # its own -- is copied by nobody, so there are not two senders.
        rsync = config['LoopData'].get('RsyncSpec', {})
        syncer = (self._tree_syncing_report(reports)
                  if under(served, where)
                  and str(rsync.get('enable', 'false')).lower() not in (
                      'false', 'no', '0') else None)
        if syncer is not None:
            engine.printer.out(
                'Note: weewx-loopdata sends the loop-data file itself at '
                "loop cadence, and report '%s' copies the reports tree -- "
                'this file included -- at report cadence.  Worth checking '
                'whether those two end up in the same place: if they do, '
                "the report cycle's older copy can arrive last.  Keeping "
                'the file outside the reports tree settles it either way: '
                '%s' % (syncer, self._PLACEMENT_URL))

        # `not current`, not `is None`: an empty loop_data_file is not a
        # URL anyone is relying on, and `settled` above judges the same
        # value with bool() -- the two must agree on what "set" means.
        if not current:
            if getattr(engine, 'dry_run', False):
                engine.printer.out(
                    'Would set [StdReport] [[CelestialReport]] [[[Extras]]] '
                    'loop_data_file = %s (dry run).' % derived)
                return False
            section = reports.setdefault('CelestialReport', {})
            section.setdefault('Extras', {})['loop_data_file'] = derived
            engine.printer.out(
                'Set [StdReport] [[CelestialReport]] [[[Extras]]] '
                'loop_data_file = %s -- where weewx-loopdata writes '
                '([LoopData] [[FileSpec]] loop_data_dir, relative to %s'
                "'s HTML_ROOT)." % (derived, target))
            return True
        engine.printer.out(
            'Note: loop_data_file is %s, but weewx-loopdata writes where %s '
            "points ([LoopData] [[FileSpec]] loop_data_dir, relative to %s's "
            'HTML_ROOT)%s  An existing setting is never changed here -- if '
            "the page's badge reads NO DATA (HTTP 404), this is the line to "
            'fix.' % (current, derived, target,
                      ', and that file is there.' if os.path.isfile(written)
                      else '.'))
        return False

    def _update_fields(self, engine):
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
            return False
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split(',') if f.strip()]
        _, report = celestial.migrate_loopdata_fields(
            list(fields), celestial._configured_satellites(config),
            celestial._configured_comets(config))
        modified = False
        if report['added']:
            if getattr(engine, 'dry_run', False):
                engine.printer.out(
                    'Would append %d entries the page reads to [LoopData] '
                    '[[Include]] fields (dry run; existing entries are '
                    'never touched).' % len(report['added']))
            else:
                config['LoopData']['Include']['fields'] = (
                    list(fields) + list(report['added']))
                engine.printer.out(
                    'Appended %d entries the page reads to [LoopData] '
                    '[[Include]] fields (append-only: existing entries are '
                    'never renamed, removed or reordered):'
                    % len(report['added']))
                for name in report['added']:
                    engine.printer.out('    ' + name)
                engine.printer.out(
                    'Restart weewxd so weewx-loopdata reloads the line.')
                modified = True
        if report['renamed']:
            config_path = getattr(engine, 'config_path', '/home/weewx/weewx.conf')
            # The user package's parent: WEEWX_ROOT/bin, exactly where
            # _gen_file_paths just put this extension's 'bin/user' files.
            bin_dir = os.path.abspath(os.path.join(
                engine.root_dict.get('WEEWX_ROOT', '/home/weewx'), 'bin'))
            engine.printer.out(
                'Note: the [LoopData] [[Include]] fields line carries %d '
                'entries with outdated spellings.  Renames deserve review, '
                'so this installer never applies them; the bundled migrator '
                'updates the line in one idempotent pass:'
                % len(report['renamed']))
            # On a deb/rpm package install WeeWX's own code lives in
            # /usr/share/weewx, on sys.path only because /usr/bin/weectl
            # exports PYTHONPATH -- a pasted bare command dies importing
            # weewx.  Carry the running weewx's location explicitly;
            # redundant on venv installs, essential on package installs.
            weewx_dir = os.path.dirname(os.path.dirname(
                os.path.abspath(weewx.__file__)))
            engine.printer.out('    cd %s' % bin_dir)
            engine.printer.out('    PYTHONPATH=%s %s -m user.celestial '
                               '--migrate-loopdata-fields '
                               '--config %s --output /tmp/weewx.conf.migrated'
                               % (weewx_dir, sys.executable, config_path))
            engine.printer.out('    git diff --no-index --word-diff %s '
                               '/tmp/weewx.conf.migrated' % config_path)
            engine.printer.out('Review the changes (the utility lists each one; '
                               'the word-diff shows them in place -- a plain diff '
                               'is unreadable on one long fields line), then move '
                               'the file into place.  See the README for detail.')
        return modified

    _PLACEMENT_URL = ('https://chaunceygardiner.github.io/weewx-celestial/'
                      'configuration.html#where-the-loop-data-file-should-live')

    @staticmethod
    def _tree_syncing_report(reports):
        """The name of an enabled report that copies the whole HTML tree
        (WeeWX's own Ftp and Rsync skins), or None.  Enablement is read
        the way WeeWX reads it: the report's own 'enable' if it has one,
        else [StdReport]'s, else it runs."""
        from weeutil.weeutil import to_bool

        def enabled(section):
            for value in (section.get('enable'), reports.get('enable')):
                if value is None:
                    continue
                try:
                    return to_bool(value)
                except ValueError:
                    return True         # unparseable: assume it runs
            return True

        for name in reports:
            section = reports[name]
            if not isinstance(section, dict):
                continue                        # [StdReport]'s own scalars
            if str(section.get('skin', '')).lower() not in ('ftp', 'rsync'):
                continue
            if enabled(section):
                return name
        return None

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
