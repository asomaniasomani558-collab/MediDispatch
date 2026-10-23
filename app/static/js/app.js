/* MediDispatch GH - shared helpers (vanilla JS, no frameworks).
 * Exposes window.MD: api(), toast(), esc(), ago(), sev helpers, clock, confirms.
 */
(function () {
  "use strict";

  var MD = (window.MD = window.MD || {});

  // ---- CSRF ------------------------------------------------------------------
  MD.csrf = function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  };

  function setCsrf(token) {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && token) meta.setAttribute("content", token);
  }

  MD.refreshCsrf = function () {
    return fetch("/civilian/api/csrf", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) { setCsrf(d.csrf_token); return d.csrf_token; });
  };

  // ---- Fetch wrapper -----------------------------------------------------------
  function ApiError(message, status, data) {
    this.name = "ApiError";
    this.message = message;
    this.status = status;
    this.data = data || {};
  }
  ApiError.prototype = Object.create(Error.prototype);
  MD.ApiError = ApiError;

  /**
   * MD.api(url, {method, json, formData, headers, timeout})
   * Resolves with parsed JSON. Rejects with ApiError (status 0 = network/offline).
   * Retries once automatically if the CSRF token expired.
   */
  MD.api = function (url, opts, _retried) {
    opts = opts || {};
    var method = (opts.method || (opts.json || opts.formData ? "POST" : "GET")).toUpperCase();
    var headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    var body;
    if (opts.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.json);
    } else if (opts.formData) {
      body = opts.formData;
    }
    if (method !== "GET") headers["X-CSRFToken"] = MD.csrf();

    var controller = "AbortController" in window ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, opts.timeout || 20000) : null;

    return fetch(url, {
      method: method,
      headers: headers,
      body: body,
      credentials: "same-origin",
      signal: controller ? controller.signal : undefined,
    })
      .then(function (res) {
        if (timer) clearTimeout(timer);
        var ct = res.headers.get("Content-Type") || "";
        var parse = ct.indexOf("application/json") !== -1 ? res.json() : res.text().then(function () { return {}; });
        return parse.then(function (data) {
          if (res.ok) return data;
          if (res.status === 400 && data && data.code === "csrf" && !_retried) {
            return MD.refreshCsrf().then(function () { return MD.api(url, opts, true); });
          }
          throw new ApiError((data && data.error) || "Request failed (" + res.status + ")", res.status, data);
        });
      })
      .catch(function (err) {
        if (timer) clearTimeout(timer);
        if (err instanceof ApiError) throw err;
        var msg = err && err.name === "AbortError" ? "The request timed out." : "No connection to the server.";
        throw new ApiError(msg, 0, {});
      });
  };

  // ---- Text helpers ------------------------------------------------------------
  MD.esc = function (value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  MD.ago = function (iso) {
    if (!iso) return "-";
    var t = Date.parse(iso);
    if (isNaN(t)) return "-";
    var s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 60) return s + "s ago";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  };

  MD.time = function (iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    return isNaN(d) ? "-" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  MD.sevKey = function (sev) { return (sev || "none").toLowerCase(); };
  MD.sevBadge = function (sev) {
    return '<span class="sev sev-' + MD.sevKey(sev) + '">' + MD.esc(sev || "UNTRIAGED") + "</span>";
  };
  MD.statusBadge = function (status, label) {
    return '<span class="status status-' + MD.esc(status) + '">' + MD.esc(label || status) + "</span>";
  };

  var LABELS = {
    icu_bed: "ICU bed", ct_scanner: "CT scanner", cath_lab: "Cath lab", blood_bank: "Blood bank",
    burns_unit: "Burns unit", burns_specialist: "Burns specialist", trauma_surgeon: "Trauma surgeon",
    general_surgeon: "General surgeon", spo2: "SpO2", gcs: "GCS", avpu: "AVPU",
  };
  MD.humanize = function (key) {
    if (LABELS[key]) return LABELS[key];
    var text = String(key || "").replace(/_/g, " ");
    return text.charAt(0).toUpperCase() + text.slice(1);
  };

  // ---- Toasts --------------------------------------------------------------------
  MD.toast = function (message, kind, ms) {
    var box = document.getElementById("toasts");
    if (!box) {
      box = document.createElement("div");
      box.id = "toasts";
      box.className = "toasts";
      box.setAttribute("role", "status");
      box.setAttribute("aria-live", "polite");
      document.body.appendChild(box);
    }
    var el = document.createElement("div");
    el.className = "toast" + (kind ? " toast-" + kind : "");
    el.textContent = message;
    box.appendChild(el);
    setTimeout(function () { el.remove(); }, ms || 6000);
  };

  // ---- Audio cue for critical arrivals (opt-in by page) -----------------------------
  MD.beep = function () {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = MD._audio || (MD._audio = new Ctx());
      var o = ctx.createOscillator();
      var g = ctx.createGain();
      o.type = "square";
      o.frequency.value = 880;
      g.gain.value = 0.05;
      o.connect(g); g.connect(ctx.destination);
      o.start();
      o.stop(ctx.currentTime + 0.25);
    } catch (e) { /* audio is optional */ }
  };

  // ---- Page wiring ---------------------------------------------------------------
  function startClock() {
    var nodes = document.querySelectorAll("[data-clock]");
    if (!nodes.length) return;
    function tick() {
      var now = new Date();
      var txt = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
      nodes.forEach(function (n) { n.textContent = txt; });
    }
    tick();
    setInterval(tick, 1000);
  }

  function wireConfirms() {
    document.addEventListener("submit", function (ev) {
      var form = ev.target;
      var msg = form.getAttribute && form.getAttribute("data-confirm");
      if (msg && !window.confirm(msg)) ev.preventDefault();
    });
  }

  function wireAgo() {
    function refresh() {
      document.querySelectorAll("[data-ago]").forEach(function (n) {
        n.textContent = MD.ago(n.getAttribute("data-ago"));
      });
    }
    refresh();
    setInterval(refresh, 15000);
  }

  document.addEventListener("DOMContentLoaded", function () {
    startClock();
    wireConfirms();
    wireAgo();
  });
})();
