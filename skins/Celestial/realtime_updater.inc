## Copyright (C)2022-2025 by John A Kline (john@johnkline.com)
## See LICENSE.txt for your rights
#errorCatcher Echo
#encoding UTF-8
<script>
  #if $Extras.has_key('page_update_pwd')
    page_update_pwd = '$Extras.page_update_pwd';
  #else
    page_update_pwd = 'foo';
  #end if
  #if $Extras.has_key('refresh_rate')
    refresh_rate = $Extras.refresh_rate;
  #else
    refresh_rate = 2;
  #end if
  #if $Extras.has_key('expiration_time')
    expiration_time = $Extras.expiration_time;
  #else
    expiration_time = 24;
  #end if
  function addLoadEvent(func) {
    var oldonload = window.onload;
    if (typeof window.onload != 'function') {
      window.onload = func;
    } else {
      window.onload = function() {
        if (oldonload) {
          oldonload();
        }
        func();
      }
    }
  }
  function getUrlParam(paramName) {
      var name, regexS, regex, results;
      name = paramName.replace(/(\[|\])/g, '\\$1');
      regexS = '[\\?&]' + name + '=([^&#]*)';
      regex = new RegExp(regexS);
      results = regex.exec(window.location.href);
      if (results === null) {
          return '';
      } else {
          return results[1];
      }
  }
  var pageTimedOut = false;
  function expirePage() {
    pageTimedOut = true;
  }
  function setUpExpiredClickListener() {
    var liveLabel = document.getElementById("live-label");
    if (liveLabel != "CLICK-ME") {
      liveLabel.innerHTML = "CLICK-ME";
      // set an onclick event on live-label to restart everything
      liveLabel.addEventListener("click", clickListener);
    }
  }
  function clickListener() {
    // disable the onClick event again
    var liveLabel = document.getElementById("live-label");
    liveLabel.removeEventListener('click', clickListener);
    liveLabel.innerHTML = "";
    // restart everything
    pageTimedOut = false;
    // restart the page timeout
    setPageExpirationTimer();
  }
  function setPageExpirationTimer() {
    if (getUrlParam('pageUpdate') !== page_update_pwd) {
      // expire in N hours
      setTimeout(expirePage, 1000 * 60 * 60 * expiration_time);
    }
  }
  setPageExpirationTimer();
  setInterval(updateCurrent, 2000);
  addLoadEvent(updateCurrent);
  function pacificHMS(ts) {
    return new Date(ts * 1000).toLocaleString("en-US", {timeZone: "America/Los_Angeles", hour: '2-digit', minute:'2-digit', second:'2-digit'});
  }
  function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function daylightString(yesterday_daylight_secs, today_daylight_secs) {
    // 	9 hours, 35 minutes, 56 seconds
    //  0 minutes, 2 seconds less than yesterday
    var hours = Math.floor(today_daylight_secs / 3600);
    var minutes = Math.floor((today_daylight_secs % 3600) / 60);
    var seconds = Math.round(today_daylight_secs % 60);
    delta = Math.abs(Math.round(yesterday_daylight_secs - today_daylight_secs));
    var deltaMinutes = Math.floor((delta % 3600) / 60);
    var deltaSeconds = delta % 60;
    var moreLess = "same"
    if (today_daylight_secs < yesterday_daylight_secs) {
      moreLess = "less";
    } else if (today_daylight_secs > yesterday_daylight_secs) {
      moreLess = "more";
    }
    return hours + ' hours, ' + minutes + ' minutes, ' + seconds + " seconds<br>" + deltaMinutes + " minutes, " + deltaSeconds + " seconds " + moreLess + " than yesterday";
  }
  // Read a value under its 3.0 name, falling back to the pre-3.0 name so an
  // un-migrated [LoopData] fields list in weewx.conf keeps this page updating.
  function lookup(result, key) {
    if (result[key] !== undefined) {
      return result[key];
    }
    var old = {
      "current.daylightDur.raw": "current.daySunshineDur.raw",
      "current.yesterdayDaylightDur.raw": "current.yesterdaySunshineDur.raw"
    }[key];
    if (old === undefined) {
      // The 3.0 rename lowercased the first letter of the field name
      // (current.Sunrise.raw became current.sunrise.raw).
      var parts = key.split(".");
      parts[1] = parts[1].charAt(0).toUpperCase() + parts[1].slice(1);
      old = parts.join(".");
    }
    return result[old];
  }
  function updateCurrent() {
    if (pageTimedOut) {
        setUpExpiredClickListener();
        return false;
    }
    var xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
      try {
        var result = JSON.parse(this.responseText);

        // Check the date
        // "dateTime": 1578965850,
        var lastUpdate = new Date(result["current.dateTime.raw"] * 1000);
        var age = Math.round(Math.abs(new Date() - lastUpdate) / 1000);
        var element = document.getElementById("live-label");
        element.style.fontWeight = "bolder";
        if (age <= 6) {
          element.innerHTML = "LIVE&nbsp;&nbsp;";
        } else {
          element.innerHTML = age + "s ago&nbsp;&nbsp;";
        }

        // Display the time of the last update.
        var activityElement = document.getElementById("last-update");
        activityElement.innerHTML = lastUpdate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});

        document.getElementById("current.sunrise.raw").innerHTML = pacificHMS(lookup(result, "current.sunrise.raw"));
        document.getElementById("current.sunTransit.raw").innerHTML = pacificHMS(lookup(result, "current.sunTransit.raw"));
        document.getElementById("current.sunset.raw").innerHTML = pacificHMS(lookup(result, "current.sunset.raw"));
        document.getElementById("current.tomorrowSunrise.raw").innerHTML = pacificHMS(lookup(result, "current.tomorrowSunrise.raw"));
        document.getElementById("current.tomorrowSunset.raw").innerHTML = pacificHMS(lookup(result, "current.tomorrowSunset.raw"));
        document.getElementById("daylight").innerHTML = daylightString(lookup(result, "current.yesterdayDaylightDur.raw"), lookup(result, "current.daylightDur.raw"));
        document.getElementById("current.astronomicalTwilightStart.raw").innerHTML = pacificHMS(lookup(result, "current.astronomicalTwilightStart.raw"));
        document.getElementById("current.nauticalTwilightStart.raw").innerHTML = pacificHMS(lookup(result, "current.nauticalTwilightStart.raw"));
        document.getElementById("current.civilTwilightStart.raw").innerHTML = pacificHMS(lookup(result, "current.civilTwilightStart.raw"));
        document.getElementById("current.civilTwilightEnd.raw").innerHTML = pacificHMS(lookup(result, "current.civilTwilightEnd.raw"));
        document.getElementById("current.nauticalTwilightEnd.raw").innerHTML = pacificHMS(lookup(result, "current.nauticalTwilightEnd.raw"));
        document.getElementById("current.astronomicalTwilightEnd.raw").innerHTML = pacificHMS(lookup(result, "current.astronomicalTwilightEnd.raw"));
        document.getElementById("current.sunAzimuth.raw").innerHTML = lookup(result, "current.sunAzimuth.raw").toFixed(1) + "&deg;";
        document.getElementById("current.sunAltitude.raw").innerHTML = lookup(result, "current.sunAltitude.raw").toFixed(1) + "&deg;";
        document.getElementById("current.sunRightAscension.raw").innerHTML = lookup(result, "current.sunRightAscension.raw").toFixed(1) + "&deg;";
        document.getElementById("current.sunDeclination.raw").innerHTML = lookup(result, "current.sunDeclination.raw").toFixed(1) + "&deg;";
        document.getElementById("current.nextEquinox").innerHTML = lookup(result, "current.nextEquinox");
        document.getElementById("current.nextSolstice").innerHTML = lookup(result, "current.nextSolstice");
        document.getElementById("current.moonrise").innerHTML = lookup(result, "current.moonrise");
        document.getElementById("current.moonTransit").innerHTML = lookup(result, "current.moonTransit");
        document.getElementById("current.moonset").innerHTML = lookup(result, "current.moonset");
        document.getElementById("current.moonAzimuth.raw").innerHTML = lookup(result, "current.moonAzimuth.raw").toFixed(1) + "&deg;";
        document.getElementById("current.moonAltitude.raw").innerHTML = lookup(result, "current.moonAltitude.raw").toFixed(1) + "&deg;";
        document.getElementById("current.moonRightAscension.raw").innerHTML = lookup(result, "current.moonRightAscension.raw").toFixed(1) + "&deg;";
        document.getElementById("current.moonDeclination.raw").innerHTML = lookup(result, "current.moonDeclination.raw").toFixed(1) + "&deg;";
        document.getElementById("current.moonPhase").innerHTML = lookup(result, "current.moonPhase");
        document.getElementById("current.moonFullness").innerHTML = lookup(result, "current.moonFullness") + " full";
        document.getElementById("current.nextNewMoon").innerHTML = lookup(result, "current.nextNewMoon");
        document.getElementById("current.nextFullMoon").innerHTML = lookup(result, "current.nextFullMoon");
        document.getElementById("current.earthMoonDistance").innerHTML = numberWithCommas(lookup(result, "current.earthMoonDistance"));
        document.getElementById("current.earthSunDistance").innerHTML = numberWithCommas(lookup(result, "current.earthSunDistance"));
        document.getElementById("current.earthMercuryDistance").innerHTML = numberWithCommas(lookup(result, "current.earthMercuryDistance"));
        document.getElementById("current.earthVenusDistance").innerHTML = numberWithCommas(lookup(result, "current.earthVenusDistance"));
        document.getElementById("current.earthMarsDistance").innerHTML = numberWithCommas(lookup(result, "current.earthMarsDistance"));
        document.getElementById("current.earthJupiterDistance").innerHTML = numberWithCommas(lookup(result, "current.earthJupiterDistance"));
        document.getElementById("current.earthSaturnDistance").innerHTML = numberWithCommas(lookup(result, "current.earthSaturnDistance"));
        document.getElementById("current.earthUranusDistance").innerHTML = numberWithCommas(lookup(result, "current.earthUranusDistance"));
        document.getElementById("current.earthNeptuneDistance").innerHTML = numberWithCommas(lookup(result, "current.earthNeptuneDistance"));
        document.getElementById("current.earthPlutoDistance").innerHTML = numberWithCommas(lookup(result, "current.earthPlutoDistance"));
        // Light years; only present when the star catalog is enabled and the
        // field is in the [LoopData] fields list.
        var proximaLY = result["current.earthProximaCentauriDistance.raw"];
        if (proximaLY !== undefined) {
          document.getElementById("current.earthProximaCentauriDistance.raw").innerHTML = proximaLY.toFixed(2) + " light years";
        }
      } catch (e) {
        console.log(e);
      }
    }
    xhttp.onerror = function() {
      try {
        // Status not OK (!= 200).
        var element = document.getElementById("live-label");
        element.innerHTML = "";
        console.log('status: ' + this.status);
      } catch (e) {
        console.log(e);
      }
    }
    try {
      xhttp.timeout = 1800;
      xhttp.open("GET", "$Extras.loop_data_file", true);
      xhttp.send();
    } catch (e) {
      console.log(e);
    }
  }
</script>
