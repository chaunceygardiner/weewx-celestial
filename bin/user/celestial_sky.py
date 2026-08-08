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


class CelestialSkyPage(SearchList):
    """Exposes $sky_page to the Celestial skin's templates -- the real
    weewx-skyfield SkyPage when available, else None."""

    def __init__(self, generator) -> None:
        SearchList.__init__(self, generator)

    def get_extension_list(self, timespan, db_lookup) -> List[Dict[str, Any]]:
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
