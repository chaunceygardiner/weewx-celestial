---
title: The translation dictionary
layout: default
nav_order: 10
description: The complete [Texts] dictionary the Celestial page renders, as shipped — the reference for starting a new translation, kept identical to the skin's lang/en.conf by a test.
---

# The translation dictionary

[weewx-celestial manual](https://chaunceygardiner.github.io/weewx-celestial/) · [weewx-celestial on GitHub](https://github.com/chaunceygardiner/weewx-celestial) · [Report an issue](https://github.com/chaunceygardiner/weewx-celestial/issues)

---

Every string the page renders, and nothing else.  This is a copy of
`skins/Celestial/lang/en.conf`'s `[Texts]` section as shipped — the
installed file is always authoritative for your version, and a test keeps
this page identical to it, so what you read here is what the skin
renders.

To start a translation, copy `en.conf` to `<code>.conf` beside it and
translate the values; the keys stay English, and anything you leave out
falls back to English one string at a time.  The mechanics, the other
three translation channels, and the station-wide `[[Defaults]]` route are
on [Translations](i18n.md).  The installed `en.conf` also carries the
`[Labels]`, `[Units]` and `[Almanac]` sections, which are not repeated
here.

```ini
[Texts]

    # ── page prose (index.html.tmpl; the panels' strings render from
    #    celestial_page.py) ───────────────────────────────────────────────
    "The live sky over {location}." = "The live sky over {location}."
    'Celestial <span class="over">over</span> {location}' = 'Celestial <span class="over">over</span> {location}'
    "updated" = "updated"
    "The geocentric · live" = "The geocentric · live"
    "Install {skyfield} (strongly recommended, and required for Proxima Centauri) or PyEphem so the almanac can serve this panel's positions and distances." = "Install {skyfield} (strongly recommended, and required for Proxima Centauri) or PyEphem so the almanac can serve this panel's positions and distances."
    "Geocentric chart: bodies placed by compass azimuth and log distance from Earth" = "Geocentric chart: bodies placed by compass azimuth and log distance from Earth"
    "plan view — compass bearing, east to the right · rings step ×10 in distance · solid&nbsp;=&nbsp;above the horizon, dashed&nbsp;=&nbsp;below · trails show the last hour of motion" = "plan view — compass bearing, east to the right · rings step ×10 in distance · solid&nbsp;=&nbsp;above the horizon, dashed&nbsp;=&nbsp;below · trails show the last hour of motion"
    "Calculated with WeeWX's built-in almanac" = "Calculated with WeeWX's built-in almanac"
    "Calculated with the station's extended almanac (weewx-skyfield or PyEphem)" = "Calculated with the station's extended almanac (weewx-skyfield or PyEphem)"
    "Calculated with Skyfield, JPL's DE421 ephemeris and the Hipparcos star catalog (Credit: ESA)" = "Calculated with Skyfield, JPL's DE421 ephemeris and the Hipparcos star catalog (Credit: ESA)"
    "Calculated with weewx-skyfield: Skyfield, JPL's DE421 ephemeris and the Hipparcos star catalog (Credit: ESA)" = "Calculated with weewx-skyfield: Skyfield, JPL's DE421 ephemeris and the Hipparcos star catalog (Credit: ESA)"
    "live via weewx-loopdata" = "live via weewx-loopdata"

    # ── live strings (celestial.js, fed by the page's config block; the roster's first paint in
    #    celestial_page.py uses the same keys) ────────────────────────────
    "alt {alt}°" = "alt {alt}°"
    "below horizon" = "below horizon"
    "{dist} au" = "{dist} au"
    "receding" = "receding"
    "approaching" = "approaching"
    "LIVE" = "LIVE"
    "{age}s ago" = "{age}s ago"
    "NO DATA (HTTP {status}) — check loop_data_file" = "NO DATA (HTTP {status}) — check loop_data_file"
    "BAD DATA — check loop_data_file" = "BAD DATA — check loop_data_file"
    "OFFLINE" = "OFFLINE"
    "CLICK-ME" = "CLICK-ME"
    "{ly} ly" = "{ly} ly"
    "Proxima" = "Proxima"

    # ── sky dome panel (the satellite rows share their keys with
    #    weewx-skyfield's Sky page, translations verbatim) ──────────────
    "The sky dome · live" = "The sky dome · live"
    "Install {skyfield} so the almanac can draw the live sky dome." = "Install {skyfield} so the almanac can draw the live sky dome."
    "The page's fragment set is missing or invalid in [CelestialFragments] — see the weewxd log." = "The page's fragment set is missing or invalid in [CelestialFragments] — see the weewxd log."
    "This page's report does not name the {panel} panel in celestial_panels, so its live fields are not declared — name it, re-run weectl extension install and restart weewxd." = "This page's report does not name the {panel} panel in celestial_panels, so its live fields are not declared — name it, re-run weectl extension install and restart weewxd."
    "This page's report carries an invalid celestial_panels — see the weewxd log." = "This page's report carries an invalid celestial_panels — see the weewxd log."
    "This page's report's field declaration is out of date — re-run weectl extension install (or the --add-satellite/--add-comet utility) and restart weewxd." = "This page's report's field declaration is out of date — re-run weectl extension install (or the --add-satellite/--add-comet utility) and restart weewxd."
    "The sky dome could not be drawn — see the weewxd log." = "The sky dome could not be drawn — see the weewxd log."
    "North at the top, east at the left — the sky-chart orientation, as if lying on your back looking up.  Altitude rings at 30° and 60°; the rim is the horizon." = "North at the top, east at the left — the sky-chart orientation, as if lying on your back looking up.  Altitude rings at 30° and 60°; the rim is the horizon."
    "Hover or tap any mark for its coordinates." = "Hover or tap any mark for its coordinates."
    "Satellites · the next visible pass" = "Satellites · the next visible pass"
    "appears {rise} · peaks {alt}° {culm} · disappears {set} · {m} min" = "appears {rise} · peaks {alt}° {culm} · disappears {set} · {m} min"
    "no visible pass in the coming week" = "no visible pass in the coming week"

    # ── the dome's any-pass roster (celestial's own wording — skyfield's
    #    page has no next_pass table) ────────────────────────────────────
    "Satellites · the next pass overhead" = "Satellites · the next pass overhead"
    "no pass in the coming week" = "no pass in the coming week"
    "visible" = "visible"
    "not visible" = "not visible"
    "no usable orbital elements — see the weewxd log" = "no usable orbital elements — see the weewxd log"

    # ── the Next Visible Pass chart panel (both strings shared with
    #    weewx-skyfield's Sky page, translations verbatim) ──────────────
    "The Next Visible Pass · the sky at its peak" = "The Next Visible Pass · the sky at its peak"
    "The whole sky as it will stand at the pass's highest point, on the date above — the dashed arc is the satellite's path, its rise and set times at the ends.  Only stars bright enough for a twilight sky are drawn: a visible pass happens while your sky is half dark." = "The whole sky as it will stand at the pass's highest point, on the date above — the dashed arc is the satellite's path, its rise and set times at the ends.  Only stars bright enough for a twilight sky are drawn: a visible pass happens while your sky is half dark."

    # ── strings rendered inside the embedded dome and chart
    #    (weewx-skyfield's dome_svg and pass_chart_html translate
    #    through this report's [Texts]), plus the rosters' composed
    #    head lines -- date ('%b %-d', a strftime format), time and
    #    countdown -- built the same way at report time and live ──────
    "Sky dome chart" = "Sky dome chart"
    "{name} — alt {alt}°, az {az}°, mag {mag}" = "{name} — alt {alt}°, az {az}°, mag {mag}"
    "{name} — alt {alt}°, az {az}°" = "{name} — alt {alt}°, az {az}°"
    "{name} — alt {alt}°, az {az}° — in shadow" = "{name} — alt {alt}°, az {az}° — in shadow"
    "{name} — alt {alt}°, az {az}°, {pct}% illuminated" = "{name} — alt {alt}°, az {az}°, {pct}% illuminated"
    "{name} pass — {rise} → {set}, peak {alt}°" = "{name} pass — {rise} → {set}, peak {alt}°"
    "Pass sky chart" = "Pass sky chart"
    "{date} · {rise} → {set} · peak {alt}°" = "{date} · {rise} → {set} · peak {alt}°"
    "%b %-d" = "%b %-d"
    "%a %b %-d" = "%a %b %-d"
    "overhead now" = "overhead now"
    "in {m} min" = "in {m} min"
    "in {h} h" = "in {h} h"
    "in {n} day" = "in {n} day"
    "in {n} days" = "in {n} days"

    # ── the moment between a pass's end and the feed's rollover to the
    #    next pass (celestial's own wording) ─────────────────────────────
    "just set" = "just set"

    # ── countdown central and the comet layer (8.1; the eclipse vocabulary,
    #    the perihelion label, the moon note and the radiant tooltip are
    #    shared with weewx-skyfield, translations verbatim) ────────────
    "sunset" = "sunset"
    "sunrise" = "sunrise"
    "darkness begins" = "darkness begins"
    "darkness ends" = "darkness ends"
    "spring begins" = "spring begins"
    "summer begins" = "summer begins"
    "autumn begins" = "autumn begins"
    "winter begins" = "winter begins"
    "Earth perihelion" = "Earth perihelion"
    "Earth aphelion" = "Earth aphelion"
    "supermoon" = "supermoon"
    "appears in" = "appears in"
    "{d}d {h}h {m}m" = "{d}d {h}h {m}m"
    "mag {mag}" = "mag {mag}"
    "moon {pct}%" = "moon {pct}%"
    "lunar eclipse" = "lunar eclipse"
    "solar eclipse" = "solar eclipse"
    "penumbral" = "penumbral"
    "partial" = "partial"
    "total" = "total"
    "annular" = "annular"
    "{name} perihelion" = "{name} perihelion"
    "{name} radiant — ZHR {zhr}, peak {date}" = "{name} radiant — ZHR {zhr}, peak {date}"

    # ── the dome's health line (8.3.1): shown when the backdrop
    #    refetches stop landing and the star field is no longer
    #    advancing.  {file} is filled in with the fragment that failed
    #    -- keep the placeholder, never translate or drop it ────────────────────────────────────
    "Star field frozen — this sky is from {time} ({why})" = "Star field frozen — this sky is from {time} ({why})"
    "no newer backdrop has arrived" = "no newer backdrop has arrived"
    "{file} returns HTTP {status}" = "{file} returns HTTP {status}"
    "{file} is not a sky fragment" = "{file} is not a sky fragment"
    "{file} is empty" = "{file} is empty"
    "no response for {file}" = "no response for {file}"
    "{file} is stamped ahead of the station's clock" = "{file} is stamped ahead of the station's clock"
    "what to check" = "what to check"
```
