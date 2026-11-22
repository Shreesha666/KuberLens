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

  // Initialize all KPI counters inside a target container
  function initKpiCounters(container) {
    const root = container || document;
    const counters = root.querySelectorAll("[data-kpi-counter]");
    counters.forEach(function (counterEl) {
      animateCounter(counterEl);
    });
  }

  // Export globally for programmatic control
  window.initKpiCounters = initKpiCounters;
  window.animateCounter = animateCounter;

  // Auto-run on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initKpiCounters(document);
    });
  } else {
    initKpiCounters(document);
  }

  // Auto-run on HTMX swaps and dynamic partial loads
  if (typeof document !== "undefined") {
    document.body.addEventListener("htmx:afterSwap", function (evt) {
      const target = (evt.detail && evt.detail.target) ? evt.detail.target : document;
      initKpiCounters(target);
    });

    document.body.addEventListener("htmx:load", function (evt) {
      const target = (evt.detail && evt.detail.elt) ? evt.detail.elt : document;
      initKpiCounters(target);
    });
  }
})();

