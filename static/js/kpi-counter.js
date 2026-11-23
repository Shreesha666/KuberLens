/**
 * KuberLens - High-Performance KPI Number Counter Animation Engine
 * Supports Indian Numbering Format (Lakhs/Crores), Currency, Decimals,
 * Deceleration Curves, and Seamless HTMX Updates.
 */
(function () {
  "use strict";

  // Easing function: smooth decelerating exponential curve (cubic-bezier(0.16, 1, 0.3, 1) equivalent)
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function easeOutQuart(t) {
    return 1 - Math.pow(1 - t, 4);
  }

  // Format number according to specified format options
  function formatNumber(val, options) {
    const format = options.format || "standard";
    const decimals = typeof options.decimals === "number" ? options.decimals : (Number.isInteger(val) ? 0 : 2);
    const prefix = options.prefix || "";
    const suffix = options.suffix || "";
    const showSign = options.showSign || false;

    const isNegative = val < 0;
    const absVal = Math.abs(val);

    let formattedNum = "";

    if (format === "inr") {
      formattedNum = absVal.toLocaleString("en-IN", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });

      if (isNegative) {
        return `-₹${formattedNum}${suffix}`;
      } else if (showSign && absVal > 0) {
        return `+₹${formattedNum}${suffix}`;
      } else {
        return `₹${formattedNum}${suffix}`;
      }
    } else {
      formattedNum = absVal.toLocaleString("en-IN", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });

      let sign = "";
      if (isNegative) {
        sign = "-";
      } else if (showSign && absVal > 0) {
        sign = "+";
      }

      return `${sign}${prefix}${formattedNum}${suffix}`;
    }
  }

  function animateCounter(el) {
    if (!el) return;

    // Check user preference for reduced motion
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const rawTarget = el.getAttribute("data-target");
    if (rawTarget === null || rawTarget === undefined || rawTarget.trim() === "") {
      return;
    }

    const targetVal = parseFloat(rawTarget);
    if (isNaN(targetVal)) return;

    const format = el.getAttribute("data-format") || "standard";
    const rawDecimals = el.getAttribute("data-decimals");
    const decimals = rawDecimals !== null ? parseInt(rawDecimals, 10) : (Number.isInteger(targetVal) ? 0 : 2);
    const prefix = el.getAttribute("data-prefix") || "";
    const suffix = el.getAttribute("data-suffix") || "";
    const showSign = el.getAttribute("data-show-sign") === "true";
    const duration = parseInt(el.getAttribute("data-duration") || "1300", 10);

    const options = { format, decimals, prefix, suffix, showSign };

    // If reduced motion is requested, render instantly
    if (prefersReducedMotion) {
      el.textContent = formatNumber(targetVal, options);
      el.setAttribute("data-current-val", targetVal);
      return;
    }

    // Determine starting value
    let startVal = 0;
    if (el._currentAnimatedVal !== undefined) {
      startVal = el._currentAnimatedVal;
    } else if (el.hasAttribute("data-start")) {
      startVal = parseFloat(el.getAttribute("data-start")) || 0;
    }

    // If starting and target are identical, just format
    if (startVal === targetVal && el.textContent.trim() !== "") {
      return;
    }

    // Cancel existing animation on this element if any
    if (el._animationFrameId) {
      cancelAnimationFrame(el._animationFrameId);
      el._animationFrameId = null;
    }

    // Clean up any odometer DOM wrapper if present
    if (el.querySelector(".odo-wrap")) {
      el.innerHTML = "";
    }

    const startTime = performance.now();
    const delta = targetVal - startVal;

    // Optional visual pulse indicator on card
    const parentCard = el.closest(".kpi-card, .stat-card-elevated");
    if (parentCard && el._hasAnimatedBefore) {
      parentCard.classList.remove("kpi-updated");
      void parentCard.offsetWidth; // trigger reflow
      parentCard.classList.add("kpi-updated");
    }
    el._hasAnimatedBefore = true;

    function step(currentTime) {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const easedProgress = easeOutQuart(progress);

      const currentVal = startVal + delta * easedProgress;
      el._currentAnimatedVal = currentVal;
      el.textContent = formatNumber(currentVal, options);

      if (progress < 1) {
        el._animationFrameId = requestAnimationFrame(step);
      } else {
        el._currentAnimatedVal = targetVal;
        el.textContent = formatNumber(targetVal, options);
        el.setAttribute("data-current-val", targetVal);
        el._animationFrameId = null;

        // Custom event notification
        el.dispatchEvent(new CustomEvent("kpi-counter:completed", { detail: { value: targetVal } }));
      }
    }

    el._animationFrameId = requestAnimationFrame(step);
  }

  // Dashboard-specific state tracking for rolling odometer effect
  window._dashboardFirstLoadDone = window._dashboardFirstLoadDone || false;
  window._dashboardKpiState = window._dashboardKpiState || {};

  function isOdometerEligible(el) {
    if (!el) return false;
    return Boolean(
      el.closest("#dashboard-root") ||
      el.closest("[data-dashboard-root]") ||
      el.closest("#stock-quote-container") ||
      el.closest("[data-stock-quote-widget]")
    );
  }

  // CodeFronts mechanical rolling odometer tumbler digit animation
  function renderRollingOdometer(el, targetVal, options, kpiId) {
    if (!el) return;
    const newStr = formatNumber(targetVal, options);
    const prevState = (window._dashboardKpiState && window._dashboardKpiState[kpiId]) ? window._dashboardKpiState[kpiId] : null;
    const prevStr = (prevState && prevState.str) ? prevState.str : (el.textContent.trim() || newStr);

    console.log("[KuberLens] Rolling Odometer for", kpiId, "prev:", prevStr, "new:", newStr);

    // Pulse card glow indicator
    const parentCard = el.closest(".kpi-card, .stat-card-elevated");
    if (parentCard) {
      parentCard.classList.remove("kpi-updated");
      void parentCard.offsetWidth;
      parentCard.classList.add("kpi-updated");
    }

    el.innerHTML = "";
    const wrap = document.createElement("span");
    wrap.className = "odo-wrap";

    const isIdentical = (prevState && prevState.num === targetVal);
    const stripsToAnimate = [];

    // Build cells matching newStr structure
    for (let i = 0; i < newStr.length; i++) {
      const ch = newStr[i];
      if (ch >= "0" && ch <= "9") {
        const d = parseInt(ch, 10);
        const offsetFromRight = newStr.length - 1 - i;
        const prevIdx = prevStr.length - 1 - offsetFromRight;

        let startDigit = d;
        if (!isIdentical && prevIdx >= 0 && prevIdx < prevStr.length && prevStr[prevIdx] >= "0" && prevStr[prevIdx] <= "9") {
          startDigit = parseInt(prevStr[prevIdx], 10);
        } else if (isIdentical && offsetFromRight < 3) {
          // If value is identical, roll the last digits by 1 notch so user visually sees the mechanical refresh
          startDigit = (d + 9) % 10;
        }

        const cell = document.createElement("span");
        cell.className = "odo-cell";
        cell.dataset.d = String(d);

        const strip = document.createElement("span");
        strip.className = "odo-strip";
        strip.style.transform = "translateY(" + (-startDigit * 10) + "%)";

        let html = "";
        for (let num = 0; num <= 9; num++) {
          html += "<i>" + num + "</i>";
        }
        strip.innerHTML = html;
        cell.appendChild(strip);
        wrap.appendChild(cell);

        stripsToAnimate.push({
          strip: strip,
          startDigit: startDigit,
          targetDigit: d,
          delay: (newStr.length - 1 - offsetFromRight) * 25
        });
      } else {
        const charSpan = document.createElement("span");
        charSpan.className = "odo-char";
        charSpan.textContent = ch;
        wrap.appendChild(charSpan);
      }
    }

    el.appendChild(wrap);
    void wrap.offsetWidth; // Force layout paint

    // Animate using Web Animations API for guaranteed smooth mechanical roll
    requestAnimationFrame(function () {
      stripsToAnimate.forEach(function (item) {
        if (typeof item.strip.animate === "function") {
          const anim = item.strip.animate(
            [
              { transform: "translateY(" + (-item.startDigit * 10) + "%)" },
              { transform: "translateY(" + (-item.targetDigit * 10) + "%)" }
            ],
            {
              duration: 750,
              delay: item.delay,
              easing: "cubic-bezier(0.16, 1, 0.3, 1)",
              fill: "forwards"
            }
          );
          anim.onfinish = function () {
            item.strip.style.transform = "translateY(" + (-item.targetDigit * 10) + "%)";
          };
        } else {
          item.strip.style.transform = "translateY(" + (-item.targetDigit * 10) + "%)";
        }
      });
    });

    // Record state
    window._dashboardKpiState = window._dashboardKpiState || {};
    window._dashboardKpiState[kpiId] = {
      num: targetVal,
      str: newStr
    };
  }

  function animateOdometerCounter(el, kpiId) {
    if (!el) return;

    // Cancel any active smooth text counter animation frame
    if (el._animationFrameId) {
      cancelAnimationFrame(el._animationFrameId);
      el._animationFrameId = null;
    }

    const rawTarget = el.getAttribute("data-target");
    if (rawTarget === null || rawTarget === undefined || rawTarget.trim() === "") {
      return;
    }

    const targetVal = parseFloat(rawTarget);
    if (isNaN(targetVal)) return;

    const format = el.getAttribute("data-format") || "standard";
    const rawDecimals = el.getAttribute("data-decimals");
    const decimals = rawDecimals !== null ? parseInt(rawDecimals, 10) : (Number.isInteger(targetVal) ? 0 : 2);
    const prefix = el.getAttribute("data-prefix") || "";
    const suffix = el.getAttribute("data-suffix") || "";
    const showSign = el.getAttribute("data-show-sign") === "true";

    const options = { format, decimals, prefix, suffix, showSign };

    // Respect reduced motion
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) {
      el.textContent = formatNumber(targetVal, options);
      el.setAttribute("data-current-val", targetVal);
      return;
    }

    renderRollingOdometer(el, targetVal, options, kpiId);
  }

  // Initialize all KPI counters inside a target container
  // animMode: "counter" (smooth text count-up, default for manual load/refresh) or "odometer" (15s rolling digits)
  function initKpiCounters(container, animMode) {
    const root = container || document;
    const mode = animMode || "counter";

    const counters = root.querySelectorAll("[data-kpi-counter]");
    if (!counters.length) return;

    counters.forEach(function (counterEl, idx) {
      const isOdoEligible = isOdometerEligible(counterEl);
      const kpiId = counterEl.getAttribute("data-kpi-id") || ("kpi-" + idx);

      // Record baseline target for future odometer transitions
      const rawTarget = counterEl.getAttribute("data-target");
      if (rawTarget !== null) {
        const targetVal = parseFloat(rawTarget) || 0;
        const format = counterEl.getAttribute("data-format") || "standard";
        const rawDecimals = counterEl.getAttribute("data-decimals");
        const decimals = rawDecimals !== null ? parseInt(rawDecimals, 10) : (Number.isInteger(targetVal) ? 0 : 2);
        const prefix = counterEl.getAttribute("data-prefix") || "";
        const suffix = counterEl.getAttribute("data-suffix") || "";
        const showSign = counterEl.getAttribute("data-show-sign") === "true";
        const options = { format, decimals, prefix, suffix, showSign };

        window._dashboardKpiState = window._dashboardKpiState || {};
        if (!window._dashboardKpiState[kpiId]) {
          window._dashboardKpiState[kpiId] = {
            num: targetVal,
            str: formatNumber(targetVal, options)
          };
        }
      }

      if (isOdoEligible && mode === "odometer") {
        // EXCLUSIVELY run mechanical rolling odometer on 15-second background refresh (Dashboard & Stock Quote Widget)
        animateOdometerCounter(counterEl, kpiId);
      } else {
        // EXCLUSIVELY run smooth text count-up on manual refresh, initial load, or non-odometer pages
        animateCounter(counterEl);
      }
    });
  }

  // Export globally for programmatic control & verification
  window.initKpiCounters = initKpiCounters;
  window.animateCounter = animateCounter;
  window.renderRollingOdometer = renderRollingOdometer;
  window.animateOdometerCounter = animateOdometerCounter;
  window.testRollingOdometer = function (kpiId, testValue) {
    kpiId = kpiId || "portfolio_value";
    testValue = (testValue !== undefined) ? testValue : Math.round(Math.random() * 50000 + 100000);
    const el = document.querySelector('[data-kpi-id="' + kpiId + '"]') || document.querySelector('[data-kpi-counter]');
    if (!el) {
      console.warn("Element not found for kpiId:", kpiId);
      return;
    }
    el.setAttribute("data-target", testValue);
    animateOdometerCounter(el, kpiId);
    console.log("Rolled", kpiId, "to", testValue);
  };

  // 1. Initial Page Load / Manual Browser Refresh (F5 / Navigation) -> ALWAYS smooth text count-up
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initKpiCounters(document, "counter");
    }, { once: true });
  } else {
    initKpiCounters(document, "counter");
  }

  // 2. HTMX After Swap Event -> Detect 15s Background Poll vs Manual User Actions
  function handleHtmxAfterSwap(evt) {
    if (!evt || !evt.detail) return;
    const target = evt.detail.target || evt.detail.elt || document;

    // Detect if this HTMX swap came from the 15-second background refresh timer
    const elt = evt.detail.elt;
    const isSilentRefresh = Boolean(
      (elt && elt.hasAttribute && elt.hasAttribute("data-silent-refresh")) ||
      (elt && elt.closest && elt.closest("[data-silent-refresh]"))
    );
    const reqPath = (evt.detail.pathInfo && evt.detail.pathInfo.requestPath) ? evt.detail.pathInfo.requestPath : "";
    const xhrUrl = (evt.detail.xhr && evt.detail.xhr.responseURL) ? evt.detail.xhr.responseURL : "";
    const is15sUrl = reqPath.includes("refresh=15s") || xhrUrl.includes("refresh=15s") || reqPath.includes("/quote/") || xhrUrl.includes("/quote/");

    const is15sBackgroundRefresh = Boolean(isSilentRefresh || is15sUrl);

    if (is15sBackgroundRefresh) {
      // 15-second background refresh: RUN ONLY ROLLING ODOMETER
      initKpiCounters(target, "odometer");
    } else {
      // Manual action (clicking 'Refresh Overview', navigation tabs): RUN ONLY SMOOTH TEXT COUNTER
      initKpiCounters(target, "counter");
    }
  }

  // Register exclusively on htmx:afterSwap to prevent duplicate execution from htmx:load
  if (typeof document !== "undefined") {
    document.body.addEventListener("htmx:afterSwap", handleHtmxAfterSwap);
  }
})();

