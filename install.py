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
from io import StringIO

import configobj
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

    # The page's live values reach it only through weewx-loopdata 7.0's
    # per-report declaration (the skin's own [LoopData] [[fields]], and
    # the groups configure() writes): an older weewx-loopdata never reads
    # either, writes no entry under this report's name, and the page says
    # BAD DATA for ever with nothing in any log to say why.  So the
    # install refuses, here, where the user is reading.
    #
    # Only an INSTALL is gated.  WeeWX keeps a copy of this file under
    # user/installer/celestial and runs loader() from it for `weectl
    # extension list` and `weectl extension uninstall` too (WeeWX 4's
    # wee_extension likewise), and those catch only ExtensionError --
    # a SystemExit here would leave a station that has since removed or
    # downgraded weewx-loopdata unable to list its extensions or to
    # uninstall this one.  The Python and WeeWX checks above have the
    # same shape but cannot regress after install; this one can.
    # (John's ruling, 2026-08-25, for celestial, weatherboard and
    # liveseasons alike.)
    if installing():
        from weeutil.weeutil import version_compare
        try:
            from user.loopdata import LOOP_DATA_VERSION
        except ImportError as e:
            # Absent is one thing, broken is another, and the advice
            # differs: only a module that is not THERE earns "install
            # weewx-loopdata".  A user/loopdata.py present but failing
            # on a dependency of its own raises ImportError too --
            # ModuleNotFoundError naming something else, or a plain
            # ImportError -- and telling that user to install what they
            # have sends them the wrong way.
            if (isinstance(e, ModuleNotFoundError)
                    and e.name in ('user', 'user.loopdata')):
                sys.exit("weewx-celestial requires weewx-loopdata 7.0 or later, "
                         "and none is installed (user.loopdata cannot be "
                         "imported).  Install weewx-loopdata first, then "
                         "weewx-celestial.")
            sys.exit("weewx-celestial requires weewx-loopdata 7.0 or later, and "
                     "the installed one cannot be imported (%s: %s).  Repair or "
                     "reinstall weewx-loopdata first, then install "
                     "weewx-celestial." % (type(e).__name__, e))
        except Exception as e:
            sys.exit("weewx-celestial requires weewx-loopdata 7.0 or later, and "
                     "the installed one cannot be imported (%s: %s).  Repair or "
                     "reinstall weewx-loopdata first, then install "
                     "weewx-celestial." % (type(e).__name__, e))
        # WeeWX's own natural compare: '7' == '7.0', '7.10' > '7.2',
        # '7.0a1' > '7.0' (a dev build of 7.0 is 7.0), '6.9b1' < '7.0'.
        if version_compare(str(LOOP_DATA_VERSION), '7.0') < 0:
            sys.exit("weewx-celestial requires weewx-loopdata 7.0 or later, found "
                     "%s.  Upgrade weewx-loopdata first, then install "
                     "weewx-celestial." % LOOP_DATA_VERSION)

    return CelestialInstaller()


def installing():
    """True when the command line is installing an extension: weectl
    spells it `extension install`; WeeWX 4's wee_extension is optparse,
    whose documented usage is `--install=FILE` and which also takes any
    unambiguous prefix (`--inst`), so its test is the prefix `--i` --
    wee_extension has no other option starting so (--list, --uninstall,
    --config, --bin-root, --tmpdir, --dry-run, --verbosity), weectl's
    extension subcommands none, and an argument value never starts with
    `--`.  Same shape as weatherboard and liveseasons (John's ruling,
    2026-08-26)."""
    return any(arg == 'install' or arg.startswith('--i') for arg in sys.argv)


# The stanza a fresh install writes into weewx.conf, as text rather than a
# dict so that ConfigObj carries its comments into the user's file.  An
# option that only selects a default is written commented out, so that the
# extension's own fallback -- and a better one in some later release -- goes
# on governing; weectl fills in absent keys only and never rewrites a value
# that is already there, so a value written live here would pin the station
# to it for ever.
CONFIG = """
[StdReport]
    [[CelestialReport]]
        # The page's language.  Every string the page composes is
        # translated at generation time, so this is read here, not in the
        # browser; see the manual's Translations page for what ships.
        # Left commented, the skin's own value answers -- unless you set
        # a language in [StdReport] [[Defaults]], which beats the skin;
        # uncommenting here beats both.
        #lang = en

        # The page's plate: dark (the night page), light (the paper-atlas
        # page), or auto -- light while the sun is up at generation time,
        # dark otherwise.  The whole page follows it, the sky dome and
        # Next Visible Pass chart included.  Spelled and valued exactly as
        # weewx-skyfield's Sky page spells it, so the two configure alike.
        #theme = dark

        # The Celestial report: one live page, generated every archive
        # interval and kept moving between cycles by weewx-loopdata.
        # Its files land in a subdirectory of your HTML_ROOT.
        HTML_ROOT = celestial
        enable = true
        skin = Celestial
        [[[Extras]]]
            # Where the page fetches its live values from -- the file
            # weewx-loopdata writes.  If not a full path, it is relative
            # to this report's HTML_ROOT.  The install works this out
            # from your own [LoopData] settings, so the value here should
            # already be right; the file must also be reachable through
            # your web server, or the page's badge reads NO DATA (HTTP
            # 404).
            loop_data_file = ../loopdata/loop-data.txt

            # Seconds between fetches of that file.  Match
            # weewx-loopdata's write cadence, which is your station's
            # loop cadence (2 seconds for the Vantage driver).
            #refresh_rate = 2

            # Hours the page keeps polling before it gives up, so an
            # abandoned browser tab does not poll forever.  Clicking the
            # LIVE badge starts it again.
            #expiration_time = 24

            # The timezone of every time shown on the page.  Leave it
            # commented and the STATION's zone is auto-detected at
            # generation time, so remote viewers of a public page see
            # station time -- which is why this one ships without a
            # value: absence IS the setting.  The line below is an
            # EXAMPLE, not a default.  Any IANA name forces that zone;
            # the word browser forces the viewer's own.
            #time_zone = America/New_York

            # PLACEHOLDER -- choose your own password.  Loading the page
            # as ?pageUpdate=<this password> exempts it from expiring,
            # which is what a kiosk display wants.  Note the URL
            # parameter is pageUpdate, not page_update_pwd.  The password
            # is visible to anyone reading the page source.
            page_update_pwd = foobar
        [[[LoopData]]]
            [[[[fields]]]]
"""


class CelestialInstaller(ExtensionInstaller):
    def __init__(self):
        super(CelestialInstaller, self).__init__(
            version = "9.0",
            name = 'celestial',
            description = 'A live celestial report driven by weewx-loopdata almanac fields.',
            author = "John A Kline",
            author_email = "john@johnkline.com",
            # The satellites and comets groups configure() writes live
            # under [[[LoopData]]] [[[[fields]]]].  CONFIG lists that
            # section EMPTY so that weectl extension uninstall prunes it:
            # weecfg's remove_and_prune pops a section it is told about
            # once it has no subsections left, and says nothing about one
            # it is not -- without this entry the uninstall left a
            # [[CelestialReport]] holding only [[[LoopData]]], with no
            # skin, and reportengine died on it (KeyError 'skin') every
            # archive cycle.  Empty, so that the conditional merge after
            # configure() adds nothing of its own.
            config = configobj.ConfigObj(StringIO(CONFIG)),
            files = [
                ('bin/user', [
                    'bin/user/celestial.py',
                    'bin/user/celestial_page.py',
                    'bin/user/celestial_sky.py',
                    ]),
                ('skins/Celestial', [
                    'skins/Celestial/celestial.css',
                    'skins/Celestial/celestial-page.css',
                    'skins/Celestial/celestial.js',
                    'skins/Celestial/index.html.tmpl',
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
        """Two install-time steps, each independently guarded, and neither
        rewrites anything a user has set by hand.

        1. Declare the page's per-configuration fields to weewx-loopdata.
        The skin's skin.conf declares the fields that do not depend on
        the station; the satellite and comet fields follow the station's
        [Skyfield] [[Satellites]] and [[Comets]], so they are written
        here, under the report's own stanza ([StdReport]
        [[CelestialReport]] [[[LoopData]]] [[[[fields]]]], the satellites
        and comets groups), rebuilt on every install so they track the
        configured set.  Those two groups are this installer's; nothing
        else in the section is touched, and the legacy [LoopData]
        [[Include]] fields line is never written -- only read, to count
        the entries on it this page now declares itself -- it is
        weewx-loopdata's, deprecated in 7.0 and removed by a later
        release of it.

        2. Point the page at wherever weewx-loopdata actually writes,
        derived from the configuration rather than guessed.

        Honors weectl's dry run.  Returns True exactly when the
        configuration was modified; either step failing degrades to a
        note, never a failed install."""
        modified = False
        try:
            modified |= self._declare_fields(engine)
        except Exception as e:
            engine.printer.out('Could not declare the satellite and comet '
                               'fields (%s); the manual\'s Fields reference '
                               'shows the groups to write under [StdReport] '
                               '[[CelestialReport]] [[[LoopData]]] '
                               '[[[[fields]]]].' % e)
        try:
            modified |= self._set_loop_data_file(engine)
        except Exception as e:
            engine.printer.out('Could not work out where weewx-loopdata '
                               'writes (%s); if the page\'s badge reads NO '
                               'DATA (HTTP 404), loop_data_file is the line '
                               'to fix (see the README).' % e)
        return modified

    def _declare_fields(self, engine):
        """The satellite and comet declaration (configure's step 1), done
        by the bundled celestial.py's declare_page_fields -- the same
        code the --add-satellite/--add-comet verbs run, so the installer
        and the verbs cannot disagree about what a satellite needs.
        Reports what changed, group by group; a configuration already
        declaring the right sets is left silent and untouched.  Returns
        True exactly when the configuration was modified."""
        celestial = self._load_bundled_celestial()
        config = engine.config_dict
        dry_run = getattr(engine, 'dry_run', False)
        # ensure_default: only the installer may add [[CelestialReport]]
        # before it exists -- weectl's conditional merge fills in its skin
        # and HTML_ROOT right after this hook.
        report = celestial.declare_page_fields(config, apply=not dry_run,
                                               ensure_default=True)
        # The legacy [LoopData] [[Include]] fields line is never edited
        # here, only counted: entries on it that this page now declares
        # itself are evaluated twice per packet by weewx-loopdata 7.0
        # (which defers de-duplicating until every extension declares),
        # and the line is other pages' as well, so the user decides.
        twice = celestial.legacy_entries_declared(
            config, report['satellites'], report['comets'], report['reports'])
        if not report['changes'] and not twice and not report['refused'] \
                and not report['misplaced']:
            return False
        for section, groups in report['changes'].items():
            for group, (old, new) in groups.items():
                tags = report[group]
                where = ('[StdReport] [[%s]] [[[LoopData]]] [[[[fields]]]] %s'
                         % (section, group))
                if dry_run:
                    verb = 'Would declare' if new else 'Would remove'
                elif new:
                    verb = 'Declared'
                else:
                    verb = 'Removed'
                if new:
                    engine.printer.out(
                        '%s %d %s fields (%s) under %s%s.'
                        % (verb, len(new), group[:-1], ', '.join(tags), where,
                           ' (dry run)' if dry_run else ''))
                    if report['%s_defaulted' % group]:
                        # Only under a DECLARED set: the defaults govern
                        # exactly when there is no section to follow, which
                        # is also the only way a declared set is non-empty
                        # without one.  A group removed because no panel of
                        # a consumer's page reads it has nothing to do with
                        # the station's [Skyfield] sets, and the receipt
                        # below it gives the real reason.
                        engine.printer.out(
                            "    (weewx-skyfield's installer defaults: the "
                            'configuration has no [Skyfield] [[%s]] to follow.  '
                            'Re-install weewx-celestial after configuring your '
                            'own, or use --add-%s.)'
                            % (group.capitalize(), group[:-1]))
                elif group in report['unread'].get(section, {}):
                    # Removed because no panel of the report reads it:
                    # the receipt below says so, in celestial.py's words.
                    engine.printer.out('%s %s%s.' % (verb, where,
                                                      ' (dry run)' if dry_run else ''))
                else:
                    engine.printer.out(
                        '%s %s: [Skyfield] [[%s]] is empty, so the page '
                        'reads no %s fields%s.'
                        % (verb, where, group.capitalize(), group[:-1],
                           ' (dry run)' if dry_run else ''))
        # The receipts celestial.py owns, in the same words the verbs
        # print them, after the lines they explain: the station's
        # misplaced key, if any; each report skipped for a fault of its
        # own (a celestial_panels naming something that is not a panel,
        # or written as a section), costing that report's declaration
        # and nobody else's, named every run until it is fixed; and each
        # group removed because no panel of its report reads it.
        for line in celestial.receipts(report):
            engine.printer.out(line)
        if report['changes'] and not dry_run:
            engine.printer.out('Restart weewxd so weewx-loopdata reads the '
                               'declaration.')
        if twice:
            engine.printer.out(
                'Note: [LoopData] [[Include]] fields still carries %d '
                'entries this page now declares itself; weewx-loopdata '
                'evaluates those twice per loop packet until the line is '
                'trimmed or retired.  It is left as it is -- other pages '
                'may read it.' % len(twice))
        return bool(report['changes']) and not dry_run

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
            # Nothing to derive from: both halves of the answer live in
            # weewx-loopdata's own section.  Nothing is said, either --
            # the declaration step reads [Skyfield], not [LoopData], so
            # (unlike 8.4's fields step, which printed an install-it
            # note here) neither step has anything to report.  The
            # loader gate means weewx-loopdata 7.0 IS installed, so a
            # missing section is a hand edit; the Installation page says
            # the shipped loop_data_file default stands for it.
            return False
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
        tree (beside this install.py) under a private module name: it is
        the field-set oracle, and this installer must never duplicate
        it."""
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
