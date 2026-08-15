"""
celestial_sky.py

Copyright (C)2022-2026 by John A Kline (john@johnkline.com)
Distributed under the terms of the GNU Public License (GPLv3)

Guarded access to weewx-skyfield's $sky_page for the Celestial skin.  The
skin's dome panel embeds $sky_page.dome_svg, but the report must never
name user.wxskyfield_sky in skin.conf directly: the CheetahGenerator
imports search_list_extensions at report time, and a failed import kills
the whole page.  This shim is celestial-owned -- the import above always
succeeds -- and makes $sky_page optional instead of required: the real
SkyPage when weewx-skyfield's search list is present, None otherwise, so
the template's #if guard hides the dome and the rest of the live page
renders on every almanac tier.

Presence detection is this module's ONLY job.  It must never grow real
logic, wrap SkyPage's methods, or version-check: an older skyfield's dome
simply lacks the satellite layer and the data-body hooks, and the page's
javascript degrades feature by feature on its own.

The one thing it does besides: log this skin's version at the first
report that renders the page, and again whenever that version changes
(8.3.1).  With no service since 7.0, nothing of this extension's runs at
startup, so the log -- the first place anyone looks when a station
misbehaves -- never named it at all.  The string comes from the skin's
own [Extras] version, so what is logged is the version that actually
rendered the page, not what some other file claims is installed.

Why the version and not a plain "have I logged this" flag: WeeWX imports
a search list once per weewxd process (importlib, then sys.modules) but
re-reads skin.conf every report cycle.  So a skin upgraded under a
running weewxd renders at its new version while this module is still the
old code -- and once a station is on 8.3.1 or later, comparing versions
is what lets that upgrade announce itself at the next cycle instead of
staying quiet until somebody restarts.  Installing over a running weewxd
still cannot change the CODE that is loaded; only a restart does that.
"""

import logging

from typing import Any, Dict, List, Optional

from weewx.cheetahgenerator import SearchList

log = logging.getLogger(__name__)

# In an installed WeeWX, bin/user modules import only as the user package;
# the bare spelling serves the test suite, which puts the sibling
# checkout's bin/user itself on sys.path.
try:
    from user.wxskyfield_sky import SkyPage  # type: ignore[import-not-found]
except ImportError:
    try:
        from wxskyfield_sky import SkyPage  # type: ignore[import-not-found, no-redef]
    except ImportError:
        SkyPage = None  # type: ignore[assignment, misc]


_logged_version: Optional[str] = None


def _log_version(generator) -> None:
    """Announce the skin's version at the first report that renders the
    page, and again if it ever changes -- never once per cycle, since
    reports run every archive interval and this is identification, not a
    heartbeat.  Guarded to the last brace: a search list that raises
    kills the whole page, and no log line is worth that."""
    global _logged_version
    try:
        # The generator, not its skin_dict: reading the attribute at the
        # CALL site would put it outside this guard, which is where the
        # promise below stops being true (8.3.2).
        version = getattr(generator, 'skin_dict', {}).get('Extras', {}).get('version')
        if version and version != _logged_version:
            _logged_version = version
            log.info('Celestial version is %s.', version)
    except Exception:
        pass


class CelestialSkyPage(SearchList):
    """Exposes $sky_page to the Celestial skin's templates -- the real
    weewx-skyfield SkyPage when available, else None."""

    def __init__(self, generator) -> None:
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup) -> List[Dict[str, Any]]:
        _log_version(self.generator)
        sky_page: Optional[Any] = None
        if SkyPage is None:
            log.info('weewx-skyfield sky page not installed; the dome panel is hidden')
        else:
            try:
                # The report's skin_dict carries [Texts]/[Labels] for this
                # page's language, exactly as skyfield's own skin passes it.
                sky_page = SkyPage(self.generator.skin_dict)
            except Exception as e:
                log.error('weewx-skyfield SkyPage failed (%s); the dome panel is hidden', e)
        return [{'sky_page': sky_page}]
