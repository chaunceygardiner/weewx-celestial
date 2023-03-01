# Copyright 2022-2023 by John A Kline <john@johnkline.com>
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

import sys
import weewx
from setup import ExtensionInstaller

def loader():
    if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 7):
        sys.exit("weewx-celestial requires Python 3.7 or later, found %s.%s" % (
            sys.version_info[0], sys.version_info[1]))

    if weewx.__version__ < "4":
        sys.exit("weewx-celestial requires WeeWX 4, found %s" % weewx.__version__)

    return CelestialInstaller()

class CelestialInstaller(ExtensionInstaller):
    def __init__(self):
        super(CelestialInstaller, self).__init__(
            version = "1.0",
            name = 'celestial',
            description = 'Inserts celestial observations into loop packets.',
            author = "John A Kline",
            author_email = "john@johnkline.com",
            data_services = 'user.celestial.Celestial',
            config = {
                'Celestial': {
                    'enable':'true',
                },
                'StdReport': {
                    'CelestialReport': {
                        'HTML_ROOT':'celestial',
                        'enable': 'true',
                        'skin':'Celestial',
                        'Extras': {
                            'loop_data_file'   : '../loop-data.txt',
                            'expiration_time'  : 24,
                            'page_update_pwd'  : 'foobar',
                        },
                    },
                },
            },
            files = [
                ('bin/user', [
                    'bin/user/celestial.py',
                    ]),
                ('skins/Celestial', [
                    'skins/Celestial/index.html.tmpl',
                    'skins/Celestial/realtime_updater.inc',
                    'skins/Celestial/skin.conf',
                    ]),
            ])
