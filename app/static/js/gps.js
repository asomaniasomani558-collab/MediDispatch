/* MediDispatch GH - GPS helper for the civilian app.
 *
 * MD.gps.watch(onFix, onError)   keep the latest fix fresh (watchPosition)
 * MD.gps.startPinging(sendFn)    call sendFn(latestFix) every 10 seconds
 * MD.gps.stop()                  stop everything (user choice / report closed)
 * MD.gps.latest                  last {lat, lon, acc, at} or null
 *
 * Location is only read after the user starts a report, and only sent to
 * this site. The user can stop sharing at any time.
 */
(function () {
  "use strict";
  var MD = (window.MD = window.MD || {});
  var PING_MS = 10000;

  var watchId = null;
  var pingTimer = null;

  MD.gps = {
    latest: null,
    supported: "geolocation" in navigator,

    watch: function (onFix, onError) {
      if (!this.supported) {
        if (onError) onError({ code: 0, message: "Location is not supported on this phone." });
        return;
      }
      if (watchId !== null) return;
      var self = this;
      watchId = navigator.geolocation.watchPosition(
        function (pos) {
          self.latest = {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            acc: Math.round(pos.coords.accuracy || 0),
            at: Date.now(),
          };
          if (onFix) onFix(self.latest);
        },
        function (err) {
          if (onError) onError(err);
        },
        { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 }
      );
    },

    startPinging: function (sendFn) {
      if (pingTimer) return;
      var self = this;
      function tick() {
        if (self.latest) sendFn(self.latest);
      }
      tick();
      pingTimer = setInterval(tick, PING_MS);
    },

    stop: function () {
      if (watchId !== null && this.supported) navigator.geolocation.clearWatch(watchId);
      watchId = null;
      if (pingTimer) clearInterval(pingTimer);
      pingTimer = null;
    },

    isActive: function () {
      return watchId !== null;
    },

    describeError: function (err) {
      if (!err) return "Location unavailable.";
      if (err.code === 1) return "Location permission denied. Tell the crew where you are when they call.";
      if (err.code === 2) return "Can't get a GPS signal. Move to open sky if safe.";
      if (err.code === 3) return "Still searching for GPS...";
      return err.message || "Location unavailable.";
    },
  };
})();
