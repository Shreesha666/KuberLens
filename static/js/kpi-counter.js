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

  // Dashboard-specific state tracking for rolling odometer effect
  window._dashboardFirstLoadDone = window._dashboardFirstLoadDone || false;
  window._dashboardKpiState = window._dashboardKpiState || {};

  function isDashboardElement(el) {
    if (!el) return false;
    return Boolean(el.closest("#dashboard-root") || el.closest("[data-dashboard-root]"));
  }

  // CodeFronts mechanical rolling odometer tumbler digit animation
  function renderRollingOdometer(el, targetVal, options, kpiId) {
    const newStr = formatNumber(targetVal, options);
    const prevState = (window._dashboardKpiState && window._dashboardKpiState[kpiId]) ? window._dashboardKpiState[kpiId] : null;
    const prevStr = (prevState && prevState.str) ? prevState.str : (el.textContent.trim() || newStr);

    // Pulse card glow indicator if numeric value changed
    const parentCard = el.closest(".kpi-card, .stat-card-elevated");
    if (parentCard && prevState && prevState.num !== targetVal) {
      parentCard.classList.remove("kpi-updated");
      void parentCard.offsetWidth;
      parentCard.classList.add("kpi-updated");
    }

    el.innerHTML = "";
    const wrap = document.createElement("span");
    wrap.className = "odo-wrap";

    // Build cells matching newStr structure; start strips at previous digits from right-alignment
    for (let i = 0; i < newStr.length; i++) {
      const ch = newStr[i];
      if (ch >= "0" && ch <= "9") {
        const d = parseInt(ch, 10);
        // Align digits from the right to preserve decimal and unit places
        const offsetFromRight = newStr.length - 1 - i;
        const prevIdx = prevStr.length - 1 - offsetFromRight;
        let startDigit = d;
        if (prevIdx >= 0 && prevIdx < prevStr.length && prevStr[prevIdx] >= "0" && prevStr[prevIdx] <= "9") {
          startDigit = parseInt(prevStr[prevIdx], 10);
        }

        const cell = document.createElement("span");
        cell.className = "odo-cell";
        cell.dataset.d = String(startDigit);

        const strip = document.createElement("span");
        strip.className = "odo-strip";
        strip.style.setProperty("--odo-y", (-startDigit * 10) + "%");

        let html = "";
        for (let num = 0; num <= 9; num++) {
          html += "<i>" + num + "</i>";
        }
        strip.innerHTML = html;
        cell.appendChild(strip);
        wrap.appendChild(cell);
      } else {
        const charSpan = document.createElement("span");
        charSpan.className = "odo-char";
        charSpan.textContent = ch;
        wrap.appendChild(charSpan);
      }
    }

    el.appendChild(wrap);
    void wrap.offsetWidth; // Force layout reflow so starting positions are committed

    // Trigger sliding animation to new digits
    requestAnimationFrame(function () {
      for (let i = 0; i < newStr.length; i++) {
        const ch = newStr[i];
        const child = wrap.children[i];
        if (!child) continue;

        if (ch >= "0" && ch <= "9") {
          const d = parseInt(ch, 10);
          const strip = child.querySelector(".odo-strip");
          if (strip) {
            strip.style.setProperty("--odo-y", (-d * 10) + "%");
            child.dataset.d = String(d);
          }
        }
      }
    });

    // Record new state
    window._dashboardKpiState = window._dashboardKpiState || {};
    window._dashboardKpiState[kpiId] = {
      num: targetVal,
      str: newStr
    };
  }

  function animateOdometerCounter(el, kpiId) {
    if (!el) return;

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
  function initKpiCounters(container) {
    const root = container || document;

    // Reset dashboard flag when dashboard root is no longer in DOM
    const dashboardRoot = document.getElementById("dashboard-root") || document.querySelector("[data-dashboard-root]");
    if (!dashboardRoot) {
      window._dashboardFirstLoadDone = false;
      window._dashboardKpiState = {};
    }

    const counters = root.querySelectorAll("[data-kpi-counter]");
    if (!counters.length) return;

    let hasDashboardCounters = false;

    counters.forEach(function (counterEl, idx) {
      const onDashboard = isDashboardElement(counterEl);
      if (onDashboard) hasDashboardCounters = true;

      const kpiId = counterEl.getAttribute("data-kpi-id") || ("kpi-" + idx);

      if (onDashboard) {
        if (!window._dashboardFirstLoadDone) {
          // First load of Dashboard: Smooth text count-up animation
          animateCounter(counterEl);
          // Seed initial target state for upcoming 15s refresh
          const rawTarget = counterEl.getAttribute("data-target");
          if (rawTarget !== null) {
            const targetVal = parseFloat(rawTarget);
            if (!isNaN(targetVal)) {
              const format = counterEl.getAttribute("data-format") || "standard";
              const rawDecimals = counterEl.getAttribute("data-decimals");
              const decimals = rawDecimals !== null ? parseInt(rawDecimals, 10) : (Number.isInteger(targetVal) ? 0 : 2);
              const prefix = counterEl.getAttribute("data-prefix") || "";
              const suffix = counterEl.getAttribute("data-suffix") || "";
              const showSign = counterEl.getAttribute("data-show-sign") === "true";
              const options = { format, decimals, prefix, suffix, showSign };
              window._dashboardKpiState[kpiId] = {
                num: targetVal,
                str: formatNumber(targetVal, options)
              };
            }
          }
        } else {
          // Subsequent 15-second background refresh on Dashboard: CodeFronts mechanical rolling odometer effect
          animateOdometerCounter(counterEl, kpiId);
        }
      } else {
        // Outside dashboard: Standard number counter
        animateCounter(counterEl);
      }
    });

    if (hasDashboardCounters && !window._dashboardFirstLoadDone) {
      setTimeout(function () {
        window._dashboardFirstLoadDone = true;
      }, 1400);
    }
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

