/* MediDispatch GH - hospital command centre controller.
 * Queue is (re)loaded over audited HTTP whenever a socket event says
 * something changed; sockets themselves never carry patient details.
 */
(function () {
  "use strict";
  var MD = window.MD;
  var esc = MD.esc;

  var queue = [];
  var selectedId = null;
  var seen = {};
  var firstLoad = true;
  var loading = false;
  var pendingReload = false;

  var VITAL_LABELS = [
    ["respiratory_rate", "Resp. rate", "/min"], ["heart_rate", "Heart rate", "bpm"],
    ["systolic_bp", "Systolic", "mmHg"], ["diastolic_bp", "Diastolic", "mmHg"],
    ["temperature", "Temp", "°C"], ["spo2", "SpO2", "%"], ["gcs", "GCS", ""],
    ["glucose", "Glucose", "mmol/L"], ["avpu", "AVPU", ""], ["age", "Age", "yrs"], ["sex", "Sex", ""],
  ];
  var MEWS_KEY = { respiratory_rate: 1, heart_rate: 1, systolic_bp: 1, temperature: 1, avpu: 1 };

  // ---- Queue ------------------------------------------------------------------
  function loadQueue() {
    if (loading) { pendingReload = true; return; }
    loading = true;
    MD.api("/hospital/api/queue").then(function (res) {
      var incoming = res.queue || [];
      var fresh = [];
      incoming.forEach(function (e) {
        if (!seen[e.id] && !firstLoad) fresh.push(e);
        seen[e.id] = true;
      });
      queue = incoming;
      renderQueue(fresh);
      if (fresh.length) {
        var critical = fresh.some(function (e) { return e.severity === "CRITICAL" || e.severity === "HIGH"; });
        MD.toast(fresh.length + " new inbound patient" + (fresh.length > 1 ? "s" : "") +
          (critical ? " - HIGH PRIORITY" : ""), critical ? "critical" : "ok", 10000);
        MD.beep();
        if (critical) setTimeout(MD.beep, 350);
      }
      firstLoad = false;
      renderDetail();
    }).catch(function (err) {
      MD.toast("Queue: " + err.message, "error");
    }).then(function () {
      loading = false;
      if (pendingReload) { pendingReload = false; loadQueue(); }
    });
  }

  function renderQueue(fresh) {
    var body = document.getElementById("queue-body");
    var freshIds = {};
    (fresh || []).forEach(function (e) { freshIds[e.id] = true; });
    if (!queue.length) {
      body.innerHTML = '<tr><td colspan="9" class="empty">No inbound patients. New hand-overs appear here instantly.</td></tr>';
    } else {
      body.innerHTML = queue.map(function (e) {
        return '<tr class="rail' + (freshIds[e.id] ? " fresh" : "") + '" data-sev="' + MD.sevKey(e.severity) +
          '" data-id="' + e.id + '" tabindex="0" aria-selected="' + (e.id === selectedId) + '">' +
          "<td>" + MD.sevBadge(e.severity) + "</td>" +
          '<td class="num mews">' + (e.mews_score === null ? "-" : e.mews_score) + "</td>" +
          '<td class="ref">' + esc(e.reference) + "</td>" +
          "<td>" + esc(e.situation_label) + "</td>" +
          "<td>" + esc(e.reporter_name || "-") + "</td>" +
          '<td class="nowrap">' + (e.reporter_phone ? '<a href="tel:' + esc(e.reporter_phone) + '">' + esc(e.reporter_phone) + "</a>" : "-") + "</td>" +
          "<td>" + MD.statusBadge(e.status, e.status_label) + "</td>" +
          '<td class="nowrap" data-ago="' + esc(e.updated_at) + '">' + MD.ago(e.updated_at) + "</td>" +
          '<td class="num">' + (e.photo_count || 0) + "</td></tr>";
      }).join("");
    }
    var counts = {};
    queue.forEach(function (e) { var k = e.severity || "UNTRIAGED"; counts[k] = (counts[k] || 0) + 1; });
    document.getElementById("queue-counts").innerHTML = ["CRITICAL", "HIGH", "MODERATE", "LOW"]
      .filter(function (k) { return counts[k]; })
      .map(function (k) { return '<span class="sev sev-' + k.toLowerCase() + '">' + counts[k] + " " + k + "</span>"; })
      .join("");
  }

  function selectRow(id) {
    selectedId = id;
    document.querySelectorAll("#queue-body tr[data-id]").forEach(function (tr) {
      tr.setAttribute("aria-selected", String(Number(tr.getAttribute("data-id")) === id));
    });
    renderDetail();
  }

  // ---- Detail -------------------------------------------------------------------
  function renderDetail() {
    var box = document.getElementById("detail-body");
    var e = queue.filter(function (x) { return x.id === selectedId; })[0];
    if (!e) {
      box.innerHTML = '<p class="empty">Select a patient in the queue.</p>';
      return;
    }
    var t = e.triage || {};
    var comps = (t.mews && t.mews.components) || {};
    var v = e.vitals || {};
    var vitals = VITAL_LABELS.filter(function (row) { return v[row[0]] !== null && v[row[0]] !== undefined; })
      .map(function (row) {
        var pts = MEWS_KEY[row[0]] ? comps[row[0]] : "";
        return '<div class="vt" data-pts="' + (pts === undefined ? "" : pts) + '"><small>' + row[1] + "</small><b>" +
          esc(v[row[0]]) + "</b> " + '<small class="muted">' + row[2] + "</small></div>";
      }).join("");

    var loc = e.location;
    var gps = loc
      ? '<span class="figure">' + loc.lat.toFixed(5) + ", " + loc.lon.toFixed(5) + "</span>" +
        (loc.acc ? ' <span class="muted">(about ' + loc.acc + " m)</span>" : "") +
        ' <a href="https://www.openstreetmap.org/?mlat=' + loc.lat + "&mlon=" + loc.lon + '#map=17/' + loc.lat + "/" + loc.lon +
        '" target="_blank" rel="noopener noreferrer">map</a>' +
        '<br><span class="muted">Updated ' + MD.ago(e.location_updated_at) + "</span>"
      : '<span class="tag tag-missing">No GPS shared</span>';

    var photos = (e.media || []).map(function (m, i) {
      return '<a href="/api/media/' + m.id + '" target="_blank" rel="noopener"><img src="/api/media/' + m.id +
        '" alt="Bystander photo ' + (i + 1) + '" loading="lazy"></a>';
    }).join("");

    var actions = (t.actions || []).map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("");
    var ai = t.ai || {};
    var aiNote = ai.status === "ok"
      ? (ai.raised ? "AI raised severity from " + esc(t.baseline_severity) + " to " + esc(ai.severity) + "." : "AI agreed with the MEWS baseline.")
      : "AI not used (" + esc(ai.status || e.ai_status || "not run") + ") - MEWS rules applied.";
    var flags = (t.red_flags || []).map(function (f) { return "<li>" + esc(f) + "</li>"; }).join("");

    var btns = [];
    if (e.status === "en_route") btns.push('<button class="btn btn-primary" data-act="acknowledge">Acknowledge - team ready</button>');
    if (e.status === "en_route" || e.status === "acknowledged") btns.push('<button class="btn btn-ok" data-act="arrived">Patient arrived</button>');
    btns.push('<button class="btn btn-ghost" data-act="resolve">Close case</button>');

    box.innerHTML =
      '<div class="d-head"><div><h3>' + esc(e.situation_label) + "</h3>" +
      '<span class="ref figure">' + esc(e.reference) + "</span> " + MD.statusBadge(e.status, e.status_label) + "</div>" +
      MD.sevBadge(e.severity) + "</div>" +
      '<div class="d-section"><h4>Reporter</h4>' + esc(e.reporter_name || "Not given") +
      (e.reporter_phone ? ' - <a href="tel:' + esc(e.reporter_phone) + '">' + esc(e.reporter_phone) + "</a>" : "") +
      "<br>Crew: " + esc(e.paramedic_name || "-") + "</div>" +
      '<div class="d-section"><h4>Location</h4>' + gps + "</div>" +
      (vitals ? '<div class="d-section"><h4>Vitals (MEWS ' + (e.mews_score === null ? "-" : e.mews_score) + ")</h4>" +
        '<div class="vitals-table">' + vitals + "</div></div>" : "") +
      (e.symptoms ? '<div class="d-section"><h4>Symptoms / history</h4><p>' + esc(e.symptoms) + "</p></div>" : "") +
      (flags ? '<div class="d-section"><h4>Red flags</h4><ul class="d-list">' + flags + "</ul></div>" : "") +
      (actions ? '<div class="d-section"><h4>Triage actions</h4><ol class="d-list">' + actions + "</ol>" +
        '<p class="panel-note">' + aiNote + "</p></div>" : "") +
      (photos ? '<div class="d-section"><h4>Bystander photos</h4><div class="d-photos">' + photos + "</div></div>" : "") +
      '<div class="d-section"><h4>Timeline</h4><ul class="timeline">' +
      "<li><span>Reported</span>" + MD.time(e.created_at) + "</li>" +
      "<li><span>Last update</span>" + MD.time(e.updated_at) + "</li></ul></div>" +
      '<div class="d-actions">' + btns.join("") + "</div>";
  }

  // ---- Nearby -----------------------------------------------------------------------
  function loadNearby() {
    MD.api("/hospital/api/nearby").then(function (res) {
      var list = document.getElementById("near-list");
      var items = res.reports || [];
      list.innerHTML = items.length ? items.map(function (r) {
        return "<li><span>" + esc(r.situation_label) + '<br><span class="muted">' + MD.ago(r.created_at) + "</span></span>" +
          '<span class="figure">' + r.distance_km.toFixed(1) + ' <small class="muted">km</small></span></li>';
      }).join("") : '<li class="empty">No unassigned reports nearby.</li>';
    }).catch(function () { /* keep */ });
  }

  // ---- Capacity --------------------------------------------------------------------
  function wireCapacity() {
    var form = document.getElementById("cap-form");
    function markZero() {
      form.querySelectorAll('input[type="number"]').forEach(function (inp) {
        inp.setAttribute("data-zero", Number(inp.value) <= 0 ? "yes" : "no");
      });
    }
    form.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-step]");
      if (!btn) return;
      var input = document.getElementById(btn.getAttribute("data-for"));
      var max = input.hasAttribute("max") ? Number(input.getAttribute("max")) : Infinity;
      input.value = Math.max(0, Math.min(max, (Number(input.value) || 0) + Number(btn.getAttribute("data-step"))));
      markZero();
    });
    form.addEventListener("input", markZero);
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var specs = {};
      form.querySelectorAll('input[name="spec"]').forEach(function (cb) { specs[cb.value] = cb.checked; });
      MD.api("/hospital/api/capacity", {
        json: {
          er_beds_available: form.er_beds_available.value,
          icu_beds_available: form.icu_beds_available.value,
          general_beds_available: form.general_beds_available.value,
          specialists: specs,
        },
      }).then(function () {
        document.getElementById("cap-updated").textContent = "Updated just now";
        MD.toast("Capacity published to all crews.", "ok");
      }).catch(function (err) { MD.toast(err.message, "error"); });
    });
    markZero();
  }

  // ---- Wiring -------------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    var body = document.getElementById("queue-body");
    body.addEventListener("click", function (ev) {
      var tr = ev.target.closest("tr[data-id]");
      if (tr && !ev.target.closest("a")) selectRow(Number(tr.getAttribute("data-id")));
    });
    body.addEventListener("keydown", function (ev) {
      var tr = ev.target.closest("tr[data-id]");
      if (tr && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); selectRow(Number(tr.getAttribute("data-id"))); }
    });

    document.getElementById("detail-body").addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-act]");
      if (!btn || selectedId === null) return;
      var act = btn.getAttribute("data-act");
      if (act === "resolve" && !window.confirm("Close this case? It will leave the queue.")) return;
      btn.disabled = true;
      MD.api("/hospital/api/case/" + selectedId + "/" + act, { method: "POST", json: {} })
        .then(function (res) { MD.toast("Status: " + res.status_label, "ok"); loadQueue(); })
        .catch(function (err) { btn.disabled = false; MD.toast(err.message, "error"); });
    });

    wireCapacity();
    MD.live.connect({
      pollMs: 15000,
      onResync: function () { loadQueue(); loadNearby(); },
      events: {
        emergency_updated: function () { loadQueue(); },
        emergency_removed: function (p) { if (p.id === selectedId) selectedId = null; loadQueue(); },
        nearby_report: function (r) {
          MD.toast("Unassigned report " + r.distance_km + " km away: " + r.situation_label, "", 7000);
          loadNearby();
        },
      },
    });
    loadQueue();
    loadNearby();
  });
})();
