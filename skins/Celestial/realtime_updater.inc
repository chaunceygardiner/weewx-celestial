## Copyright (C)2022 by John A Kline (john@johnkline.com)
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

        document.getElementById("current.Sunrise.raw").innerHTML = pacificHMS(result["current.Sunrise.raw"]);
        document.getElementById("current.SunTransit.raw").innerHTML = pacificHMS(result["current.SunTransit.raw"]);
        document.getElementById("current.Sunset.raw").innerHTML = pacificHMS(result["current.Sunset.raw"]);
        document.getElementById("daylight").innerHTML = daylightString(result["current.yesterdaySunshineDur.raw"], result["current.daySunshineDur.raw"]);
        document.getElementById("current.AstronomicalTwilightStart.raw").innerHTML = pacificHMS(result["current.AstronomicalTwilightStart.raw"]);
        document.getElementById("current.NauticalTwilightStart.raw").innerHTML = pacificHMS(result["current.NauticalTwilightStart.raw"]);
        document.getElementById("current.CivilTwilightStart.raw").innerHTML = pacificHMS(result["current.CivilTwilightStart.raw"]);
        document.getElementById("current.CivilTwilightEnd.raw").innerHTML = pacificHMS(result["current.CivilTwilightEnd.raw"]);
        document.getElementById("current.NauticalTwilightEnd.raw").innerHTML = pacificHMS(result["current.NauticalTwilightEnd.raw"]);
        document.getElementById("current.AstronomicalTwilightEnd.raw").innerHTML = pacificHMS(result["current.AstronomicalTwilightEnd.raw"]);
        document.getElementById("current.SunAzimuth.raw").innerHTML = result["current.SunAzimuth.raw"].toFixed(1) + "&deg;";
        document.getElementById("current.SunAltitude.raw").innerHTML = result["current.SunAltitude.raw"].toFixed(1) + "&deg;";
        document.getElementById("current.SunRightAscension.raw").innerHTML = result["current.SunRightAscension.raw"].toFixed(1) + "&deg;";
        document.getElementById("current.SunDeclination.raw").innerHTML = result["current.SunDeclination.raw"].toFixed(1) + "&deg;";
        document.getElementById("current.NextEquinox").innerHTML = result["current.NextEquinox"];
        document.getElementById("current.NextSolstice").innerHTML = result["current.NextSolstice"];
        document.getElementById("current.Moonrise.raw").innerHTML = pacificHMS(result["current.Moonrise.raw"]);
        document.getElementById("current.MoonTransit.raw").innerHTML = pacificHMS(result["current.MoonTransit.raw"]);
        document.getElementById("current.Moonset.raw").innerHTML = pacificHMS(result["current.Moonset.raw"]);
        document.getElementById("current.MoonAzimuth.raw").innerHTML = result["current.MoonAzimuth.raw"].toFixed(1) + "&deg;";
        document.getElementById("current.MoonAltitude.raw").innerHTML = result["current.MoonAltitude.raw"].toFixed(1) + "&deg;";
        document.getElementById("current.MoonRightAscension.raw").innerHTML = result["current.MoonRightAscension.raw"].toFixed(1) + "&deg;";
        document.getElementById("current.MoonDeclination.raw").innerHTML = result["current.MoonDeclination.raw"].toFixed(1) + "&deg;";
        document.getElementById("current.MoonPhase").innerHTML = result["current.MoonPhase"];
        document.getElementById("current.MoonFullness").innerHTML = result["current.MoonFullness"] + " full";
        document.getElementById("current.NextNewMoon").innerHTML = result["current.NextNewMoon"];
        document.getElementById("current.NextFullMoon").innerHTML = result["current.NextFullMoon"];
        document.getElementById("current.EarthMoonDistance").innerHTML = numberWithCommas(result["current.EarthMoonDistance"]);
        document.getElementById("current.EarthSunDistance").innerHTML = numberWithCommas(result["current.EarthSunDistance"]);
        document.getElementById("current.EarthMercuryDistance").innerHTML = numberWithCommas(result["current.EarthMercuryDistance"]);
        document.getElementById("current.EarthVenusDistance").innerHTML = numberWithCommas(result["current.EarthVenusDistance"]);
        document.getElementById("current.EarthMarsDistance").innerHTML = numberWithCommas(result["current.EarthMarsDistance"]);
        document.getElementById("current.EarthJupiterDistance").innerHTML = numberWithCommas(result["current.EarthJupiterDistance"]);
        document.getElementById("current.EarthSaturnDistance").innerHTML = numberWithCommas(result["current.EarthSaturnDistance"]);
        document.getElementById("current.EarthUranusDistance").innerHTML = numberWithCommas(result["current.EarthUranusDistance"]);
        document.getElementById("current.EarthNeptuneDistance").innerHTML = numberWithCommas(result["current.EarthNeptuneDistance"]);
        document.getElementById("current.EarthPlutoDistance").innerHTML = numberWithCommas(result["current.EarthPlutoDistance"]);
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
