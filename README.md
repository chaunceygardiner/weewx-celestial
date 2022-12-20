# weewx-celestial
*Open source plugin for WeeWX software.

Copyright (C)2020 by John A Kline (john@johnkline.com)

**This extension requires Python 3.7 or later and WeeWX 4.**


## Description

Celestial is a WeeWX service that inserts celestial observations into loop packets.
The information is then available via
[weewx-loopdata plugin](https://github.com/chaunceygardiner/weewx-loopdata), as `current.<celestial-obs>`

See weewx-celestial in action with at
[www.paloaltoweather.com/celestial.html](https://www.paloaltoweather.com/celestial.html)

The following observations are available in the LOOP packet:

`current.SunAzimuth`
`current.SunAltitude`
`current.SunRightAscension`
`current.SunDeclination`
`current.MoonAzimuth`
`current.MoonAltitude`
`current.MoonRightAscension`
`current.MoonDeclination`
`current.MoonFullness`
`current.MoonPhase`
`current.EarthSunDistance`
`current.EarthMoonDistance`
`current.EarthMercuryDistance`
`current.EarthVenusDistance`
`current.EarthMarsDistance`
`current.EarthJupiterDistance`
`current.EarthSaturnDistance`
`current.EarthUranusDistance`
`current.EarthNeptuneDistance`
`current.EarthPlutoDistance`

# Installation Instructions

1. Install the prerequisite pyephem package.  On debian, that can be accomplished with:
   `sudo apt install python3-ephem` 

1. Download the lastest release, weewx-celestial-0.3.zip, from the
   [GitHub Repository](https://github.com/chaunceygardiner/weewx-celestial).

1. Run the following command.

   `sudo /home/weewx/bin/wee_extension --install weewx-celestial-0.3.zip`

   Note: this command assumes weewx is installed in /home/weewx.  If it's installed
   elsewhere, adjust the path of wee_extension accordingly.

1. Restart WeeWX.

1. The following entry is created in `weewx.conf`.  To disable `weewx-celestial` without
   uninstalling it, change the enable line to false.
```
[Celestial]
    enable = true
```


## Why require Python 3.7 or later?

Celestial code includes type annotation which do not work with Python 2, nor in
earlier versions of Python 3.


## Licensing

weewx-celestial is licensed under the GNU Public License v3.
