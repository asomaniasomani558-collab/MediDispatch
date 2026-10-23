/* MediDispatch GH - consent-first camera for bystander photos.
 *
 * Privacy guarantees (enforced here, not just promised in the UI):
 *  - The camera never starts without the consent checkbox AND a tap on
 *    "Turn on camera".
 *  - While on, the live <video> preview is visible on screen with a
 *    "Camera on" badge. Nothing is streamed or recorded.
 *  - Only a single still frame is uploaded, and only after "Send photo".
 *  - The camera stops on: Stop camera, Capture, leaving/hiding the page,
 *    or the report closing. Tracks are fully released (light turns off).
 */
(function () {
  "use strict";
  var MD = (window.MD = window.MD || {});

  function $(id) { return document.getElementById(id); }

  MD.camera = {
    stream: null,
    stillBlob: null,
    stillUrl: null,
    uploadFn: null,     // set by civilian.js: function(blob) -> Promise
    onSent: null,

    init: function (uploadFn, onSent) {
      this.uploadFn = uploadFn;
      this.onSent = onSent;
      var self = this;
      var hasMedia = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

      $("cam-open").addEventListener("click", function () { self.show("consent"); });
      $("cam-cancel").addEventListener("click", function () { self.reset(); });
      $("cam-agree").addEventListener("change", function () {
        $("cam-start").disabled = !this.checked;
        $("cam-file-wrap").classList.toggle("hidden", !this.checked || hasMedia);
      });
      $("cam-start").addEventListener("click", function () {
        if (!$("cam-agree").checked) return;
        if (hasMedia) self.start(); else $("cam-file").click();
      });
      $("cam-stop").addEventListener("click", function () { self.stop(); self.show("consent"); });
      $("cam-capture").addEventListener("click", function () { self.capture(); });
      $("cam-retake").addEventListener("click", function () { self.discardStill(); self.start(); });
      $("cam-discard").addEventListener("click", function () { self.discardStill(); self.reset(); });
      $("cam-send").addEventListener("click", function () { self.send(); });
      $("cam-file").addEventListener("change", function () {
        var file = this.files && this.files[0];
        if (!file) return;
        if (!$("cam-agree").checked) { this.value = ""; return; }
        self.setStill(file);
        this.value = "";
      });

      // Never leave the camera running in the background.
      document.addEventListener("visibilitychange", function () {
        if (document.hidden && self.stream) { self.stop(); self.show("consent"); }
      });
      window.addEventListener("pagehide", function () { self.stop(); });
    },

    show: function (panel) {
      ["intro", "consent", "live", "review"].forEach(function (name) {
        $("cam-" + name).classList.toggle("hidden", name !== panel);
      });
    },

    start: function () {
      var self = this;
      self.stop();
      navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1600 }, height: { ideal: 1200 } },
        audio: false,
      }).then(function (stream) {
        self.stream = stream;
        var video = $("cam-video");
        video.srcObject = stream;
        self.show("live");
      }).catch(function (err) {
        MD.toast(err && err.name === "NotAllowedError"
          ? "Camera permission was declined. You can still choose a photo instead."
          : "Camera unavailable. You can choose a photo instead.", "error");
        $("cam-file-wrap").classList.remove("hidden");
        self.show("consent");
      });
    },

    stop: function () {
      if (this.stream) {
        this.stream.getTracks().forEach(function (t) { t.stop(); });
        this.stream = null;
      }
      var video = $("cam-video");
      if (video) video.srcObject = null;
    },

    capture: function () {
      var video = $("cam-video");
      if (!this.stream || !video.videoWidth) return;
      var canvas = document.createElement("canvas");
      var scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      this.stop(); // camera off as soon as the frame is taken
      var self = this;
      canvas.toBlob(function (blob) { if (blob) self.setStill(blob); }, "image/jpeg", 0.85);
    },

    setStill: function (blob) {
      this.discardStill();
      this.stillBlob = blob;
      this.stillUrl = URL.createObjectURL(blob);
      $("cam-still").src = this.stillUrl;
      this.show("review");
    },

    discardStill: function () {
      if (this.stillUrl) URL.revokeObjectURL(this.stillUrl);
      this.stillUrl = null;
      this.stillBlob = null;
      $("cam-still").removeAttribute("src");
    },

    send: function () {
      var self = this;
      if (!self.stillBlob || !self.uploadFn) return;
      var btn = $("cam-send");
      btn.disabled = true;
      btn.textContent = "Sending...";
      self.uploadFn(self.stillBlob).then(function (res) {
        MD.toast("Photo sent to the crew.", "ok");
        self.discardStill();
        self.show("intro");
        if (self.onSent) self.onSent(res);
      }).catch(function (err) {
        MD.toast(err.message || "Photo could not be sent.", "error");
      }).then(function () {
        btn.disabled = false;
        btn.textContent = "Send photo";
      });
    },

    reset: function () {
      this.stop();
      this.discardStill();
      $("cam-agree").checked = false;
      $("cam-start").disabled = true;
      this.show("intro");
    },

    disable: function () {
      this.reset();
      $("cam-open").disabled = true;
    },
  };
})();
