/* MediDispatch GH - civilian (bystander) app controller.
 *
 * Screens: start -> who -> what -> sending -> help
 * Resilience:
 *   - state is kept in localStorage, so a reload or crash resumes the report;
 *   - if the network is down, the report is queued and retried automatically;
 *   - first-aid steps are embedded in the page, so they show with no network;
 *   - "Call 112" is a plain tel: link that always works.
 */
(function () {
  "use strict";
  var MD = window.MD;
  var STORE_KEY = "md_civilian_v1";
  var TOKEN_HEADER = "X-Civilian-Token";
  var RETRY_MS = 5000;
  var STATUS_POLL_MS = 15000;

  var firstAid = {};
  try { firstAid = JSON.parse(document.getElementById("first-aid-data").textContent); } catch (e) { firstAid = {}; }

  var state = load();
  var draft = { name: "", phone: "" };
  var retryTimer = null;
  var statusTimer = null;

  // ---- Storage ----------------------------------------------------------------
  function load() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch (e) { return {}; }
  }
  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) { /* private mode */ }
  }
  function clearState() {
    state = {};
    try { localStorage.removeItem(STORE_KEY); } catch (e) { /* ignore */ }
  }

  // ---- Screens -------------------------------------------------------------------
  function show(name) {
    document.querySelectorAll("[data-screen]").forEach(function (s) {
      s.classList.toggle("hidden", s.getAttribute("data-screen") !== name);
    });
    window.scrollTo(0, 0);
    var heading = document.querySelector('[data-screen="' + name + '"] h1');
    if (heading) { heading.setAttribute("tabindex", "-1"); heading.focus({ preventScroll: true }); }
  }

  function setGpsText(text, st) {
    document.querySelectorAll("[data-gps-status]").forEach(function (el) {
      el.textContent = text;
      el.setAttribute("data-state", st || "");
    });
  }

  function fieldError(name, msg) {
    var el = document.querySelector('[data-error-for="' + name + '"]');
    if (el) el.textContent = msg || "";
    var input = document.querySelector('[name="' + name + '"]');
    if (input) input.setAttribute("aria-invalid", msg ? "true" : "false");
  }

  // ---- GPS ------------------------------------------------------------------------
  function startGps() {
    MD.gps.watch(function (fix) {
      setGpsText("Location found (accurate to about " + fix.acc + " m)", "ok");
    }, function (err) {
      setGpsText(MD.gps.describeError(err), err && err.code === 3 ? "" : "error");
    });
  }

  function startPinging() {
    MD.gps.startPinging(function (fix) {
      if (!state.token) return;
      MD.api("/civilian/api/ping", {
        json: { lat: fix.lat, lon: fix.lon, acc: fix.acc },
        headers: authHeaders(),
        timeout: 9000,
      }).then(function (res) {
        setGpsText("Sharing your location every 10 seconds (about " + fix.acc + " m)", "ok");
        renderStatus(res.status);
      }).catch(handleSessionError);
    });
  }

  function authHeaders() {
    var h = {};
    h[TOKEN_HEADER] = state.token || "";
    return h;
  }

  // ---- Report submission -----------------------------------------------------------
  function buildReport(situation) {
    var fix = MD.gps.latest;
    return {
      name: draft.name,
      phone: draft.phone,
      situation: situation,
      lat: fix ? fix.lat : null,
      lon: fix ? fix.lon : null,
      acc: fix ? fix.acc : null,
    };
  }

  function sendReport(report) {
    state.pending = report;
    state.situation = report.situation;
    save();
    show("sending");
    document.getElementById("sending-title").textContent = "Sending your report...";
    document.getElementById("sending-detail").textContent = "Keep this page open.";

    // Refresh coordinates at the moment of sending if we have newer ones.
    if (MD.gps.latest) {
      report.lat = MD.gps.latest.lat; report.lon = MD.gps.latest.lon; report.acc = MD.gps.latest.acc;
    }

    MD.api("/civilian/api/report", { json: report, timeout: 15000 }).then(function (res) {
      if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
      state = { token: res.token, reference: res.reference, situation: report.situation, phone: report.phone };
      save();
      enterHelp(res.status);
    }).catch(function (err) {
      if (err.status === 422) {
        var fields = (err.data && err.data.fields) || {};
        delete state.pending; save();
        if (fields.name || fields.phone) {
          show("who");
          fieldError("name", fields.name);
          fieldError("phone", fields.phone);
        } else {
          show("what");
          fieldError("situation", fields.situation || err.message);
        }
        return;
      }
      if (err.status === 429) {
        document.getElementById("sending-title").textContent = "Please call " + window.MD_EMERGENCY;
        document.getElementById("sending-detail").textContent = err.message;
        return;
      }
      // Network / server trouble: keep the report and retry.
      document.getElementById("sending-title").textContent = "Can't reach the server yet";
      document.getElementById("sending-detail").textContent =
        "We'll keep trying every few seconds. If someone's life is in danger, call now.";
      retryTimer = setTimeout(function () { sendReport(state.pending); }, RETRY_MS);
    });
  }

  // ---- Help screen ------------------------------------------------------------------
  function enterHelp(status) {
    document.getElementById("h-ref").textContent = state.reference || "-";
    var list = document.getElementById("aid-steps");
    list.innerHTML = "";
    (firstAid[state.situation] || firstAid.other || []).forEach(function (step) {
      var li = document.createElement("li");
      li.textContent = step;
      list.appendChild(li);
    });
    show("help");
    if (status) renderStatus(status);
    startGps();
    startPinging();
    if (!statusTimer) statusTimer = setInterval(pollStatus, STATUS_POLL_MS);
    pollStatus();
  }

  function pollStatus() {
    if (!state.token) return;
    MD.api("/civilian/api/status", { headers: authHeaders(), timeout: 9000 })
      .then(function (res) { renderStatus(res.status); })
      .catch(handleSessionError);
  }

  var STATUS_COPY = {
    reported: ["Report received", "We're alerting the nearest ambulance crew. Stay where you are if it's safe.", "waiting"],
    claimed: ["A crew is responding", "Keep your phone close - they may call you to find you.", "assigned"],
    triaged: ["The crew is with the patient", "They're assessing and treating now.", "assigned"],
    en_route: ["On the way to hospital", "", "transport"],
    acknowledged: ["On the way to hospital", "The hospital is ready to receive the patient.", "transport"],
    arrived: ["Arrived at hospital", "The patient has been handed over.", "transport"],
    resolved: ["Report closed", "Thank you for helping. You can close this page.", "closed"],
    cancelled: ["Report cancelled", "If help is still needed, start a new report or call now.", "closed"],
  };

  function renderStatus(s) {
    if (!s) return;
    var copy = STATUS_COPY[s.status] || ["Report received", "", "waiting"];
    var detail = copy[1];
    if ((s.status === "en_route" || s.status === "acknowledged") && s.hospital) {
      detail = "Going to " + s.hospital + ". " + detail;
    }
    document.querySelector("[data-status-text]").textContent = copy[0];
    document.querySelector("[data-status-detail]").textContent = detail;
    document.querySelector(".status-card").setAttribute("data-phase", copy[2]);
    document.getElementById("cancel-report").classList.toggle("hidden", s.status !== "reported");
    var count = document.getElementById("cam-count");
    count.textContent = s.photo_count ? s.photo_count + " of " + s.max_photos + " photos sent." : "";

    if (!s.open) closeLocally();
  }

  function closeLocally() {
    MD.gps.stop();
    if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
    MD.camera.disable();
    setGpsText("Location sharing has stopped.", "");
    document.getElementById("gps-stop").classList.add("hidden");
    document.getElementById("cancel-report").classList.add("hidden");
    document.getElementById("new-report").classList.remove("hidden");
  }

  function handleSessionError(err) {
    if (err && err.status === 401) {
      MD.toast("This report session has expired. Call " + window.MD_EMERGENCY + " if you still need help.", "error", 10000);
      closeLocally();
      clearState();
    }
  }

  function uploadPhoto(blob) {
    var fd = new FormData();
    fd.append("photo", blob, "photo.jpg");
    fd.append("consent", "yes");
    return MD.api("/civilian/api/photo", { formData: fd, headers: authHeaders(), timeout: 30000 })
      .then(function (res) { renderStatus(res.status); return res; });
  }

  // ---- Wiring ------------------------------------------------------------------------
  function wire() {
    window.MD_EMERGENCY = (document.querySelector(".civ-call") || {}).textContent
      ? document.querySelector(".civ-call").textContent.replace("Call ", "").trim() : "112";

    document.getElementById("help-btn").addEventListener("click", function () {
      show("who");
      startGps();  // ask for location permission right away
    });

    document.getElementById("who-form").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var name = document.getElementById("r-name").value.trim();
      var phone = document.getElementById("r-phone").value.trim();
      var digits = phone.replace(/[^\d]/g, "");
      var ok = true;
      fieldError("name", ""); fieldError("phone", "");
      if (name.length < 2) { fieldError("name", "Please enter your name."); ok = false; }
      if (digits.length < 9 || digits.length > 15) { fieldError("phone", "Enter a valid phone number, e.g. 024 123 4567."); ok = false; }
      if (!ok) return;
      draft.name = name;
      draft.phone = phone;
      show("what");
    });

    document.querySelectorAll("[data-situation]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        fieldError("situation", "");
        sendReport(buildReport(btn.getAttribute("data-situation")));
      });
    });

    document.querySelectorAll("[data-back]").forEach(function (btn) {
      btn.addEventListener("click", function () { show(btn.getAttribute("data-back")); });
    });

    document.getElementById("gps-stop").addEventListener("click", function () {
      if (MD.gps.isActive()) {
        MD.gps.stop();
        setGpsText("Location sharing stopped. The crew may call you for directions.", "error");
        this.textContent = "Share my location again";
      } else {
        startGps();
        startPinging();
        this.textContent = "Stop sharing location";
      }
    });

    document.getElementById("cancel-report").addEventListener("click", function () {
      if (!window.confirm("Cancel this report? Only do this if help is no longer needed.")) return;
      MD.api("/civilian/api/cancel", { method: "POST", json: {}, headers: authHeaders() })
        .then(function (res) { renderStatus(res.status); })
        .catch(function (err) { MD.toast(err.message, "error"); });
    });

    document.getElementById("new-report").addEventListener("click", function () {
      clearState();
      window.location.reload();
    });

    function updateNet() {
      document.getElementById("net-banner").classList.toggle("hidden", navigator.onLine);
      if (navigator.onLine && state.pending && !state.token) {
        if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
        sendReport(state.pending);
      }
    }
    window.addEventListener("online", updateNet);
    window.addEventListener("offline", updateNet);
    document.getElementById("net-banner").classList.toggle("hidden", navigator.onLine);

    MD.camera.init(uploadPhoto);
  }

  function resume() {
    if (state.token) {
      enterHelp(null);
    } else if (state.pending) {
      draft.name = state.pending.name;
      draft.phone = state.pending.phone;
      sendReport(state.pending);
    } else {
      show("start");
    }
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/civilian/sw.js", { scope: "/civilian/" }).catch(function () { /* optional */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wire();
    resume();
  });
})();
