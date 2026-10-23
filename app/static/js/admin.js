/* MediDispatch GH - admin dashboard: live health tiles, clients and logs. */
(function () {
  "use strict";
  var MD = window.MD;
  var esc = MD.esc;

  function fmtTime(epoch) {
    var d = new Date(epoch * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  }
  function agoEpoch(epoch) { return epoch ? MD.ago(new Date(epoch * 1000).toISOString()) : "-"; }

  function hydrateTimes() {
    document.querySelectorAll("[data-epoch-time]").forEach(function (el) {
      el.textContent = fmtTime(Number(el.getAttribute("data-epoch-time")));
    });
    document.querySelectorAll("[data-epoch-ago]").forEach(function (el) {
      el.textContent = agoEpoch(Number(el.getAttribute("data-epoch-ago")));
    });
    document.querySelectorAll("[data-epoch]").forEach(function (el) {
      var v = Number(el.getAttribute("data-epoch"));
      if (v) el.textContent = new Date(v * 1000).toLocaleString() + " (" + agoEpoch(v) + ")";
    });
  }

  function setTile(id, ok, state, meta) {
    var tile = document.getElementById(id);
    if (!tile) return;
    tile.setAttribute("data-ok", ok);
    tile.querySelector(".tile-state").textContent = state;
    if (meta !== undefined) tile.querySelector(".tile-meta").textContent = meta;
  }

  function refreshHealth() {
    MD.api("/admin/api/health").then(function (res) {
      var h = res.health;
      var s = res.stats;
      setTile("t-db", h.database.online ? "yes" : "no", h.database.online ? "Online" : "DOWN",
        (h.database.dialect || "") + (h.database.latency_ms !== undefined ? " - " + h.database.latency_ms + " ms" : ""));
      setTile("t-redis", !h.redis.configured ? "na" : h.redis.online ? "yes" : "no",
        !h.redis.configured ? "Not configured" : h.redis.online ? "Online" : "DOWN");
      var ai = h.ai;
      setTile("t-ai", ai.online && ai.model_available ? "yes" : ai.online ? "warn" : "no",
        ai.online && ai.model_available ? "Online" : ai.online ? "Model missing" : "Offline - MEWS fallback",
        ai.model + (ai.availability_pct !== null ? " - " + ai.availability_pct + "% availability" : ""));
      setTile("t-ws", "yes", String(h.websockets.count));

      var map = { "s-open": s.open, "s-unclaimed": s.unclaimed, "s-24h": s.last_24h,
        "s-full": s.hospitals_full + "/" + s.hospitals_active, "s-photos": s.photos_stored, "s-audit": s.audit_entries };
      Object.keys(s.by_severity).forEach(function (k) { map["s-" + k.toLowerCase()] = s.by_severity[k]; });
      Object.keys(map).forEach(function (id) { var el = document.getElementById(id); if (el) el.textContent = map[id]; });

      var rows = h.websockets.clients.map(function (c) {
        return "<tr><td>" + esc(c.username) + "</td><td>" + esc(c.role) + "</td><td>" + esc(c.hospital_id || "-") +
          "</td><td>" + agoEpoch(c.connected_at) + "</td><td>" + esc(c.ip || "") + "</td></tr>";
      });
      document.getElementById("ws-body").innerHTML = rows.join("") || '<tr><td colspan="5" class="empty">No live clients.</td></tr>';
    }).catch(function (err) { MD.toast("Health check failed: " + err.message, "error"); });
  }

  function refreshLogs() {
    var level = document.getElementById("log-level").value;
    MD.api("/admin/api/logs?level=" + encodeURIComponent(level)).then(function (res) {
      var box = document.getElementById("logs");
      box.innerHTML = (res.logs || []).map(function (l) {
        return '<div class="log log-' + esc(l.level.toLowerCase()) + '"><time>' + fmtTime(l.time) + "</time><b>" +
          esc(l.level) + "</b><span>" + esc(l.logger) + "</span><p>" + esc(l.message) + "</p></div>";
      }).join("") || '<p class="empty">No log entries at this level.</p>';
    }).catch(function () { /* keep */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.querySelector('[data-page="admin-dashboard"]')) return;
    hydrateTimes();
    document.getElementById("log-level").addEventListener("change", refreshLogs);
    setInterval(function () { refreshHealth(); refreshLogs(); }, 10000);
    if (MD.live) {
      MD.live.connect({
        pollMs: 30000,
        onResync: function () { refreshHealth(); },
        events: { report_new: function () { refreshHealth(); }, capacity_updated: function () { refreshHealth(); } },
      });
    }
  });
})();
