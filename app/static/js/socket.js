/* MediDispatch GH - realtime connection (Socket.IO) with polling fallback.
 *
 * MD.live.connect({ events: {name: fn}, onResync: fn, pollMs: 20000 })
 *
 * Broadcasts carry summaries only; pages call onResync() to fetch audited
 * details over HTTP. If WebSockets are unavailable or drop, a polling timer
 * keeps calling onResync so the screen never goes stale.
 */
(function () {
  "use strict";
  var MD = (window.MD = window.MD || {});

  function setState(state, text) {
    document.querySelectorAll("[data-conn]").forEach(function (el) {
      el.setAttribute("data-state", state);
      el.textContent = text;
    });
  }

  MD.live = {
    socket: null,
    connect: function (opts) {
      opts = opts || {};
      var events = opts.events || {};
      var resync = opts.onResync || function () {};
      var pollMs = opts.pollMs || 20000;
      var pollTimer = null;

      function startPolling() {
        if (pollTimer) return;
        pollTimer = setInterval(resync, pollMs);
      }
      function stopPolling() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      }

      // Safety-net poll runs slowly even while live, in case an event is missed.
      setInterval(resync, Math.max(pollMs * 3, 60000));

      if (typeof window.io !== "function") {
        setState("down", "Polling");
        startPolling();
        return null;
      }

      var socket = window.io({ transports: ["websocket", "polling"], reconnectionDelayMax: 8000 });
      MD.live.socket = socket;
      setState("connecting", "Connecting");

      socket.on("connect", function () {
        setState("live", "Live");
        stopPolling();
        resync();
      });
      socket.on("disconnect", function () {
        setState("down", "Reconnecting");
        startPolling();
      });
      socket.on("connect_error", function () {
        setState("down", "Offline - polling");
        startPolling();
      });
      Object.keys(events).forEach(function (name) {
        socket.on(name, function (payload) {
          try { events[name](payload); } catch (e) { if (window.console) console.error(e); }
        });
      });
      return socket;
    },
  };
})();
