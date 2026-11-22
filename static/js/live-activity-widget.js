/**
 * Live Activity & Watcher Momentum Widget (CodeFronts cnc-07 mechanical rolling odometer)
 * Provides smooth per-digit sliding, real-time SVG sparkline charting, and session analytics.
 */

(function () {
  'use strict';

  function initLiveActivityWidgets(root) {
    var scope = root || document;
    var widgets = scope.querySelectorAll('[data-live-activity]');

    widgets.forEach(function (widget) {
      if (widget.dataset.wired === '1') return;
      widget.dataset.wired = '1';

      var digitsWrap = widget.querySelector('.law-digits');
      var sparkline = widget.querySelector('.law-sparkline');
      var sparkArea = widget.querySelector('.law-spark-area');
      var peakEl = widget.querySelector('.law-peak');
      var avgEl = widget.querySelector('.law-avg');
      var srStatus = widget.querySelector('.law-sr');

      if (!digitsWrap) return;

      var baseCount = parseInt(widget.dataset.baseCount || widget.dataset.target, 10);
      if (isNaN(baseCount) || baseCount <= 0) {
        baseCount = 138;
      }

      var currentVal = baseCount;
      var peakVal = Math.round(baseCount * 1.55);
      var avgVal = Math.round(baseCount * 1.05);

      if (peakEl) peakEl.textContent = peakVal;
      if (avgEl) avgEl.textContent = avgVal;

      // Seed 28 historical points for sparkline
      var historyLength = 28;
      var history = [];
      for (var i = 0; i < historyLength; i++) {
        var jitter = (Math.random() - 0.48) * (baseCount * 0.18);
        history.push(Math.max(12, Math.round(baseCount + jitter)));
      }

      function buildCells(len) {
        digitsWrap.innerHTML = '';
        for (var i = 0; i < len; i++) {
          var cell = document.createElement('span');
          cell.className = 'law-cell';

          var strip = document.createElement('span');
          strip.className = 'law-strip';
          var numbersHtml = '';
          for (var d = 0; d <= 9; d++) {
            numbersHtml += '<i>' + d + '</i>';
          }
          strip.innerHTML = numbersHtml;

          cell.appendChild(strip);
          digitsWrap.appendChild(cell);
        }
      }

      function updateSparkline() {
        if (!sparkline) return;
        var minVal = Math.min.apply(null, history) * 0.92;
        var maxVal = Math.max.apply(null, history) * 1.08;
        var range = Math.max(1, maxVal - minVal);
        var svgWidth = 200;
        var svgHeight = 36;
        var padding = 3;

        var points = history.map(function (val, idx) {
          var x = (idx / (history.length - 1)) * svgWidth;
          var norm = (val - minVal) / range;
          var y = (svgHeight - padding) - (norm * (svgHeight - (padding * 2)));
          return x.toFixed(1) + ',' + y.toFixed(1);
        });

        var pointsStr = points.join(' ');
        sparkline.setAttribute('points', pointsStr);

        if (sparkArea) {
          var areaPoints = '0,' + svgHeight + ' ' + pointsStr + ' ' + svgWidth + ',' + svgHeight;
          sparkArea.setAttribute('points', areaPoints);
        }
      }

      function setCount(val) {
        var s = String(val);
        if (digitsWrap.children.length !== s.length) {
          buildCells(s.length);
        }

        for (var i = 0; i < s.length; i++) {
          var digitChar = s[i];
          var cell = digitsWrap.children[i];
          if (cell && cell.dataset.d !== digitChar) {
            cell.dataset.d = digitChar;
            var digitNum = parseInt(digitChar, 10);
            var stripEl = cell.firstElementChild;
            if (stripEl) {
              stripEl.style.setProperty('--law-y', (-digitNum * 10) + '%');
            }
          }
        }

        // Peak tracking
        if (val > peakVal) {
          peakVal = val;
          if (peakEl) peakEl.textContent = peakVal;
        }

        // Shift sparkline history
        history.push(val);
        history.shift();
        updateSparkline();

        // Screen reader announcement (throttled)
        if (srStatus) {
          srStatus.textContent = val + ' market participants tracking setup';
        }
      }

      // Initial render
      setCount(currentVal);
      updateSparkline();

      // Live tick simulation (realistic intraday order flow oscillation)
      var intervalMs = parseInt(widget.dataset.interval || '2800', 10);
      var timerId = setInterval(function () {
        // Disconnect if element was removed by HTMX swap
        if (!document.body.contains(widget)) {
          clearInterval(timerId);
          return;
        }

        // Only fluctuate when tab is active and visible
        if (document.visibilityState !== 'visible') return;

        var delta = Math.round((Math.random() - 0.48) * 9);
        currentVal = Math.max(18, currentVal + delta);
        setCount(currentVal);
      }, intervalMs);

      window.addEventListener('pagehide', function () {
        clearInterval(timerId);
      }, { once: true });
    });
  }

  // Export globally
  window.initLiveActivityWidgets = initLiveActivityWidgets;

  // Initialize on full page load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initLiveActivityWidgets(document);
    });
  } else {
    initLiveActivityWidgets(document);
  }

  // Support HTMX swaps
  document.addEventListener('htmx:afterSwap', function (evt) {
    var target = evt.detail && evt.detail.target ? evt.detail.target : document;
    initLiveActivityWidgets(target);
  });

  document.addEventListener('htmx:load', function (evt) {
    var target = evt.detail && evt.detail.elt ? evt.detail.elt : document;
    initLiveActivityWidgets(target);
  });
})();
