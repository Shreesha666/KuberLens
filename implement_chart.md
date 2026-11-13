# TASK: Redesign Stock Analytics Chart UI Using TradingView Lightweight Charts + Apache ECharts

Act as a Senior Financial Dashboard UI/UX Designer, Django Architect and Frontend Charting Engineer.

I already have an implemented stock analytics chart. I want to upgrade its visual design and charting technology.

## 1. Mandatory Charting Libraries

You MUST use the following two open-source libraries:

### A. TradingView Lightweight Charts — Main Stock Chart

GitHub: https://github.com/tradingview/lightweight-charts

Documentation: https://tradingview.github.io/lightweight-charts/

This library MUST replace the existing chart-rendering implementation for stock price analytics.

Use it for:
- Candlestick charts.
- OHLC price charts.
- Volume histograms.
- SMA 20 and SMA 50 overlays.
- EMA and Bollinger Bands overlays.
- RSI and MACD separate panes.
- Entry price, Target 1, Target 2 and Stop Loss lines.
- Crosshair, tooltips, zoom and scrolling.
- Interactive time and price scales.

### B. Apache ECharts — Dashboard Analytics

GitHub: https://github.com/apache/echarts

Documentation: https://echarts.apache.org/

Use it for:
- Portfolio allocation donut charts.
- Sector exposure charts.
- Market breadth and advance/decline charts.
- Stock performance comparisons.
- Sector heatmaps.
- Portfolio performance charts.
- Backtesting equity curves and drawdown.
- Risk and statistical visualizations.

IMPORTANT:
- Lightweight Charts is the primary library for stock price charts.
- ECharts is the primary library for general financial analytics and dashboard visualizations.
- Do not use ECharts to duplicate the main candlestick chart.
- Do not retain the old chart library as the primary chart engine.
- Do not replace either library with a paid alternative.

## 2. UI Redesign Requirements

Use my existing chart screenshot as the design reference.

Create a premium, modern financial trading interface.

### Chart header
Include:
- Stock name and symbol.
- NSE/BSE badge.
- Current price and percentage change.
- Market data source and freshness.
- Timeframe selector: 1D, 1W, 1M.
- Chart type selector.
- Indicators dropdown.
- Drawing tools.
- Reset zoom.
- Fullscreen.

### Main price chart — Lightweight Charts

Implement:
- Green/red candlesticks.
- Blue SMA 20.
- Orange SMA 50.
- Clean grid lines.
- Right-side price scale.
- Bottom date scale.
- Interactive crosshair.
- OHLC tooltip.
- Responsive resizing.

### Volume — Lightweight Charts

Implement:
- Volume histogram in a synchronized pane.
- Green/red volume bars.
- Independent volume scale.

### Trading levels — Lightweight Charts

Implement:
- Target 1: Green dashed horizontal line.
- Target 2: Teal dashed horizontal line.
- Stop Loss: Red dashed horizontal line.
- Entry Price: Optional neutral line.
- Price labels on the right scale.

Preserve existing trading-level calculations and data sources.

### Technical indicators — Lightweight Charts

Support:
- SMA 20.
- SMA 50.
- EMA 20.
- EMA 50.
- Bollinger Bands.
- RSI 14 in a separate pane.
- MACD (12, 26, 9) in a separate pane.

Users should be able to show/hide indicators independently.

### Dashboard analytics — Apache ECharts

Build reusable visualizations for:
- Portfolio allocation.
- Sector exposure.
- Market breadth.
- Stock comparison.
- Sector performance heatmap.
- Backtesting performance.

All ECharts visualizations must follow the same visual design system as the main stock chart.

## 3. Visual Design System

Create a consistent professional design:

- Premium financial dashboard appearance.
- Dark and light themes.
- Professional green/red financial colours.
- Consistent typography and spacing.
- Compact toolbar and legends.
- Minimal unnecessary borders.
- Clear labels and tooltips.
- Responsive desktop/tablet/mobile layouts.

Make the chart the primary focus of the stock analytics page.


## 4. Django and HTMX Integration

- Continue using Django as the backend.
- Reuse existing market data and indicator services.
- Do not fabricate or hardcode stock prices.
- Preserve source_type and freshness_status.
- Ensure charts initialize after HTMX content swaps.
- Ensure charts are cleaned up when navigating away.
- Support browser back/forward restoration.
- Avoid duplicate chart instances.
- Avoid unnecessary database changes.

## 5. Implementation Order

Follow this sequence:

1. Inspect the existing chart implementation.
2. Identify the current chart library and existing functionality.
3. Install TradingView Lightweight Charts.
4. Migrate the main candlestick chart to Lightweight Charts.
5. Migrate volume, SMA overlays and trading levels.
6. Implement the reusable indicator and pane architecture.
7. Install Apache ECharts.
8. Create reusable ECharts dashboard components.
9. Integrate ECharts into the relevant existing dashboard visualizations.
10. Apply consistent dark/light styling.
11. Test responsiveness, HTMX lifecycle and browser history.
12. Update project documentation.

Check the current official documentation and use compatible stable library versions.

## 6. Strict Restrictions

- Do not redesign the entire application.
- Do not unnecessarily change the sidebar or global navigation.
- Do not modify stock calculations or portfolio accounting.
- Do not introduce mock market data.
- Do not use TradingView Advanced Charts.
- Do not use paid charting libraries.
- Do not duplicate charting libraries.
- Do not break existing functionality.

## 7. Acceptance Criteria

The task is complete only when:

1. The existing main stock chart is rendered using TradingView Lightweight Charts.
2. Candlesticks, volume, SMA 20 and SMA 50 work.
3. Target 1, Target 2 and Stop Loss are displayed correctly.
4. Interactive chart controls work.
5. Apache ECharts is integrated for dashboard analytics.
6. Dark and light themes work.
7. Charts work after HTMX navigation and browser history restoration.
8. Responsive layouts work.
9. Existing backend data and calculations remain intact.
10. Tests pass and final screenshots demonstrate the redesigned interface.

Provide a final implementation report listing installed libraries, versions, changed files, screenshots, tests and known limitations.

Do not begin unrelated project phases.