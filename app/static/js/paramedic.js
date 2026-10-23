/* MediDispatch GH - paramedic app controller (feed, new case, case page). */
(function () {
  "use strict";
  var MD = window.MD;
  var esc = MD.esc;
  var myPos = null;

  function locate(cb) {
    if (!("geolocation" in navigator)) { cb(null); return; }
    navigator.geolocation.getCurrentPosition(function (p) {
      myPos = { lat: p.coords.latitude, lon: p.coords.longitude, acc: Math.round(p.coords.accuracy || 0) };
      cb(myPos);
    }, function () { cb(null); }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 });
  }

  // =========================================================================
  // Feed
  // =========================================================================
  function initFeed() {
    var list = document.getElementById("feed-list");
    var capBody = document.querySelector("#cap-table tbody");
    var known = {};
    var first = true;

    function loadFeed() {
      var q = myPos ? "?lat=" + myPos.lat + "&lon=" + myPos.lon : "";
      MD.api("/paramedic/api/feed" + q).then(function (res) {
        renderFeed(res.reports || []);
      }).catch(function (err) {
        if (first) list.innerHTML = '<li class="empty">' + esc(err.message) + "</li>";
      });
    }

    function renderFeed(items) {
      first = false;
      if (!items.length) {
        list.innerHTML = '<li class="empty">No unclaimed reports right now.</li>';
        return;
      }
      list.innerHTML = items.map(function (r) {
        var dist = r.distance_km !== null && r.distance_km !== undefined
          ? '<span class="dist">' + r.distance_km.toFixed(1) + " <small>km</small></span>"
          : '<span class="muted">' + (r.has_gps ? "distance unknown" : "no GPS") + "</span>";
        return '<li class="case-card rail" data-sev="none">' +
          '<span class="case-claim"><span><strong>' + esc(r.situation_label) + "</strong><br>" +
          '<span class="case-meta"><span class="figure">' + esc(r.reference) + "</span>" +
          '<span data-ago="' + esc(r.created_at) + '">' + MD.ago(r.created_at) + "</span>" +
          (r.photo_count ? "<span>" + r.photo_count + " photo" + (r.photo_count > 1 ? "s" : "") + "</span>" : "") +
          "</span></span>" + dist + "</span>" +
          '<button class="btn btn-danger" type="button" data-claim="' + r.id + '">Claim and respond</button>' +
          "</li>";
      }).join("");
      items.forEach(function (r) { known[r.id] = true; });
    }

    list.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-claim]");
      if (!btn) return;
      btn.disabled = true;
      btn.textContent = "Claiming...";
      MD.api("/paramedic/api/claim/" + btn.getAttribute("data-claim"), { method: "POST", json: {} })
        .then(function (res) { window.location.href = res.url; })
        .catch(function (err) {
          MD.toast(err.message, "error");
          loadFeed();
        });
    });

    function loadCapacity() {
      MD.api("/paramedic/api/hospitals").then(function (res) {
        var rows = (res.hospitals || []).map(function (h) {
          return "<tr><td>" + esc(h.name) + '<br><span class="muted">' + esc(h.region) + "</span></td>" +
            '<td class="num' + (h.er_beds_available <= 0 ? " cap-zero" : "") + '">' + h.er_beds_available + "</td>" +
            '<td class="num' + (h.icu_beds_available <= 0 ? " cap-zero" : "") + '">' + h.icu_beds_available + "</td>" +
            '<td class="muted">' + MD.ago(h.capacity_updated_at ? h.capacity_updated_at : null) + "</td></tr>";
        });
        capBody.innerHTML = rows.join("") || '<tr><td colspan="4" class="empty">No hospitals registered.</td></tr>';
      }).catch(function () { /* keep previous */ });
    }

    locate(function (pos) {
      document.getElementById("feed-loc").textContent = pos ? "Sorted by distance from you" : "Location off - sorted by time";
      loadFeed();
    });

    MD.live.connect({
      onResync: function () { loadFeed(); loadCapacity(); },
      events: {
        report_new: function (r) {
          if (!known[r.id]) { MD.toast("New report: " + r.situation_label, "critical"); MD.beep(); }
          loadFeed();
        },
        emergency_updated: function () { loadFeed(); },
        capacity_updated: function () { loadCapacity(); },
      },
    });
    loadCapacity();
  }

  // =========================================================================
  // New case
  // =========================================================================
  function initNew() {
    var pill = document.getElementById("nc-gps");
    locate(function (pos) {
      if (pos) {
        document.getElementById("nc-lat").value = pos.lat;
        document.getElementById("nc-lon").value = pos.lon;
        document.getElementById("nc-acc").value = pos.acc;
        pill.textContent = "Scene location captured (about " + pos.acc + " m).";
        pill.setAttribute("data-state", "ok");
      } else {
        pill.textContent = "Couldn't get location - hospital matching will rank by capability only.";
        pill.setAttribute("data-state", "error");
      }
    });
  }

  // =========================================================================
  // Case page
  // =========================================================================
  function initCase(root) {
    var caseId = root.getAttribute("data-case-id");
    var form = document.getElementById("vitals-form");
    var triageBody = document.getElementById("triage-body");
    var matchBody = document.getElementById("match-body");
    var aiLine = document.getElementById("ai-line");
    var assignedName = document.getElementById("assigned-name");

    var MEWS_LABELS = { respiratory_rate: "RR", heart_rate: "HR", systolic_bp: "SBP", temperature: "Temp", avpu: "AVPU" };
    var AI_TEXT = {
      ok: "AI assist: online",
      offline: "AI offline - MEWS rules used",
      timeout: "AI timed out - MEWS rules used",
      invalid: "AI reply rejected - MEWS rules used",
      circuit_open: "AI paused after errors - MEWS rules used",
      disabled: "AI disabled - MEWS rules used",
      fallback: "AI unavailable - MEWS rules used",
    };

    function setFieldErrors(fields) {
      form.querySelectorAll("[data-error-for]").forEach(function (el) {
        var name = el.getAttribute("data-error-for");
        el.textContent = (fields && fields[name]) || "";
        var input = form.querySelector('[name="' + name + '"]');
        if (input) input.setAttribute("aria-invalid", fields && fields[name] ? "true" : "false");
      });
    }

    function renderTriage(t) {
      if (!t || !t.mews) return;
      var comps = Object.keys(t.mews.components || {}).map(function (k) {
        var pts = t.mews.components[k];
        return '<span class="comp" data-pts="' + pts + '">' + esc(MEWS_LABELS[k] || MD.humanize(k)) + "<b>" + pts + "</b></span>";
      }).join("");
      var flags = (t.red_flags || []).length
        ? '<ul class="flags">' + t.red_flags.map(function (f) { return "<li>" + esc(f) + "</li>"; }).join("") + "</ul>" : "";
      var actions = (t.actions || []).map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("");
      var ai = t.ai || {};
      var aiBox = "";
      if (ai.status === "ok") {
        var verdict = ai.raised ? "raised severity to " + esc(ai.severity)
          : ai.attempted_downgrade ? "suggested " + esc(ai.severity) + " - ignored, the AI cannot lower MEWS"
          : "agreed with " + esc(ai.severity);
        aiBox = '<div class="ai-box"><h3>AI suggestions (advisory)</h3>' +
          '<p class="muted">' + esc(ai.model || "Model") + " " + verdict +
          (ai.latency_ms ? " in " + (ai.latency_ms / 1000).toFixed(1) + "s" : "") + ".</p>" +
          (ai.actions && ai.actions.length ? "<ul>" + ai.actions.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + "</ul>" : "") +
          (ai.rationale ? '<p class="muted">' + esc(ai.rationale) + "</p>" : "") + "</div>";
      }
      aiLine.textContent = AI_TEXT[ai.status] || "";

      triageBody.innerHTML =
        '<div class="tri-top">' +
          '<div class="mews-big"><span class="figure">' + t.mews.score + "</span><small>MEWS</small></div>" +
          '<div class="tri-final"><span class="muted">Final severity</span>' + MD.sevBadge(t.final_severity) +
          (t.final_severity !== t.mews.severity ? '<span class="muted">MEWS alone: ' + esc(t.mews.severity) + "</span>" : "") +
          "</div></div>" +
        '<div class="tri-components">' + comps + "</div>" + flags +
        "<h3>Immediate actions</h3><ol class=\"actions-list\">" + actions + "</ol>" + aiBox +
        '<p class="disclaimer">' + esc(t.disclaimer || "") + "</p>";

      var sev = document.getElementById("case-sev");
      sev.className = "sev sev-large sev-" + MD.sevKey(t.final_severity);
      sev.textContent = t.final_severity;
      document.getElementById("case-head").setAttribute("data-sev", MD.sevKey(t.final_severity));
    }

    function renderMatches(m) {
      if (!m) return;
      var warnings = (m.warnings || []).map(function (w) { return '<p class="warn">' + esc(w) + "</p>"; }).join("");
      var currentName = assignedName ? assignedName.textContent : "";
      var cards = (m.matches || []).map(function (h, i) {
        var tags = (h.matched || []).map(function (x) { return '<span class="tag tag-ok">' + esc(MD.humanize(x)) + "</span>"; }).join("") +
          (h.missing || []).map(function (x) { return '<span class="tag tag-missing">No ' + esc(MD.humanize(x)) + "</span>"; }).join("");
        var notes = (h.notes || []).map(function (n) { return '<p class="warn">' + esc(n) + "</p>"; }).join("");
        var assigned = currentName === h.name;
        return '<div class="match" data-assigned="' + (assigned ? "yes" : "no") + '">' +
          '<div class="match-top"><strong>' + (i === 0 ? "Best match: " : "") + esc(h.name) + "</strong>" +
          '<span class="match-eta">' + (h.eta_minutes !== null ? "~" + h.eta_minutes + " <small>min</small>" : "") + "</span></div>" +
          '<p class="match-meta">' + esc(h.level || "") + (h.distance_km !== null ? " | " + h.distance_km + " km" : "") +
          " | ER beds " + h.er_beds_available + " | ICU " + h.icu_beds_available +
          (h.phone ? ' | <a href="tel:' + esc(h.phone) + '">' + esc(h.phone) + "</a>" : "") + "</p>" +
          tags + notes +
          (assigned ? '<p class="muted">Hospital notified.</p>'
                    : '<button class="btn ' + (i === 0 ? "btn-primary" : "") + '" type="button" data-assign="' + h.hospital_id + '" data-name="' + esc(h.name) + '">Send patient here</button>') +
          "</div>";
      }).join("");
      matchBody.innerHTML = warnings + (cards || '<p class="empty">No hospitals available.</p>');
    }

    function loadMatches() {
      var q = myPos ? "?lat=" + myPos.lat + "&lon=" + myPos.lon : "";
      MD.api("/paramedic/api/case/" + caseId + "/matches" + q)
        .then(function (res) { renderMatches(res.matching); })
        .catch(function () { /* stays as is */ });
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var fd = new FormData(form);
      var vitals = {};
      ["respiratory_rate", "heart_rate", "systolic_bp", "diastolic_bp", "temperature", "spo2", "gcs", "glucose", "age", "avpu", "sex"]
        .forEach(function (k) { var val = fd.get(k); if (val !== null && val !== "") vitals[k] = val; });
      var btn = document.getElementById("triage-btn");
      btn.disabled = true;
      btn.textContent = "Scoring...";
      setFieldErrors(null);
      MD.api("/paramedic/api/case/" + caseId + "/triage", {
        json: { vitals: vitals, symptoms: fd.get("symptoms") || "" },
        timeout: 30000,
      }).then(function (res) {
        renderTriage(res.triage);
        renderMatches(res.matching);
        document.getElementById("triage-panel").scrollIntoView({ behavior: "smooth", block: "start" });
      }).catch(function (err) {
        if (err.status === 422) setFieldErrors(err.data.fields);
        MD.toast(err.message, "error");
      }).then(function () {
        btn.disabled = false;
        btn.textContent = "Re-run triage";
      });
    });

    matchBody.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-assign]");
      if (!btn) return;
      var name = btn.getAttribute("data-name");
      if (!window.confirm("Send patient to " + name + "? The hospital will be alerted now.")) return;
      btn.disabled = true;
      MD.api("/paramedic/api/case/" + caseId + "/assign", { json: { hospital_id: btn.getAttribute("data-assign") } })
        .then(function (res) {
          assignedName.textContent = res.hospital;
          document.getElementById("case-status").textContent = "En Route";
          MD.toast(res.hospital + " alerted.", "ok");
          loadMatches();
        })
        .catch(function (err) { btn.disabled = false; MD.toast(err.message, "error"); });
    });

    document.querySelectorAll("[data-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var action = btn.getAttribute("data-action");
        var prompts = {
          release: "Release this report back to the feed for another crew?",
          arrived: "Confirm the patient has been handed over at the hospital?",
          resolved: "Close this case without transport?",
          cancelled: "Cancel this case as a false alarm?",
        };
        if (!window.confirm(prompts[action])) return;
        var url = action === "release"
          ? "/paramedic/api/case/" + caseId + "/release"
          : "/paramedic/api/case/" + caseId + "/status";
        MD.api(url, { json: action === "release" ? {} : { status: action } })
          .then(function (res) {
            if (res.url) { window.location.href = res.url; return; }
            document.getElementById("case-status").textContent = res.status_label;
            MD.toast("Case updated: " + res.status_label, "ok");
            if (action !== "arrived") setTimeout(function () { window.location.href = "/paramedic/"; }, 900);
          })
          .catch(function (err) { MD.toast(err.message, "error"); });
      });
    });

    var initial = {};
    try { initial = JSON.parse(document.getElementById("triage-data").textContent || "{}"); } catch (e) { initial = {}; }
    if (initial && initial.mews) {
      renderTriage(initial);
      loadMatches();
    }
    locate(function () { if (initial && initial.mews) loadMatches(); });

    if (MD.live) {
      MD.live.connect({
        onResync: function () {},
        events: {
          capacity_updated: function () { if (initial && initial.mews) loadMatches(); },
          emergency_updated: function (e) {
            if (String(e.id) === String(caseId)) document.getElementById("case-status").textContent = e.status_label;
          },
          report_new: function (r) { MD.toast("New bystander report: " + r.situation_label, "critical"); },
        },
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-page]");
    if (!root) return;
    var page = root.getAttribute("data-page");
    if (page === "feed") initFeed();
    else if (page === "new") initNew();
    else if (page === "case") initCase(root);
  });
})();
