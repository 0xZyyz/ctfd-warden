/* Warden: report browser-automation marks to the server.
 * Selenium, Playwright and Puppeteer leave these even when they drive a real browser with a normal
 * User-Agent. Nothing is sent for ordinary browsers or logged-out visitors. */
(function () {
  "use strict";
  try {
    var init = window.init || {};
    if (!init.userId || !init.csrfNonce) return;

    var signals = [];
    if (navigator.webdriver) signals.push("navigator.webdriver");
    var windowMarks = /^(cdc_|\$cdc_|__webdriver|__selenium|__driver|_Selenium_IDE|__nightmare|__playwright|__pw_|__puppeteer|callPhantom|_phantom|domAutomation|__fxdriver|__lastWatirAlert|calledSelenium|_WEBDRIVER_ELEM_CACHE)/;
    var documentMarks = /^(\$cdc_|\$wdc_|__webdriver|__selenium|__driver)/;
    var name = Object.getOwnPropertyNames(window).find(function (k) { return windowMarks.test(k); });
    if (name) signals.push("window." + name.slice(0, 24));
    name = Object.getOwnPropertyNames(document).find(function (k) { return documentMarks.test(k); });
    if (name) signals.push("document." + name.slice(0, 24));
    if (!signals.length) return;

    var send = function () {
      fetch((init.urlRoot || "") + "/warden/client-signal", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "CSRF-Token": init.csrfNonce },
        body: JSON.stringify({ signals: signals, page: location.pathname }),
      }).catch(function () {});
    };
    if (document.readyState === "complete") send();
    else window.addEventListener("load", send);
  } catch (e) {
    /* never break the page */
  }
})();
