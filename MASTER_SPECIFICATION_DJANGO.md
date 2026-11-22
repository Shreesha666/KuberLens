# MASTER_SPECIFICATION_DJANGO.md
# Indian Stock Market Research & Intelligence Platform

**Document Type:** Master Product & Technical Specification  
**Application:** Personal Indian Stock Market Research, Portfolio & Primary Market Intelligence Platform  
**Backend:** Python + Django  
**Frontend:** Django Templates + Bootstrap 5 + HTMX  
**Frontend Charting:** TradingView Lightweight Charts (stock & technical charts) + Apache ECharts (dashboard & financial analytics)  
**Typography System:** CoolAdmin-inspired Hierarchy + Inter Variable Font + Tabular Numerals (`tabular-nums`)  
**Database:** PostgreSQL  
**Background Processing:** Celery + Redis  
**Market Data Providers:** Jugaad-Data + Yahoo Finance + ipos.markets REST API + NSE India / BSE India / SEBI  
**Future Broker Integration:** Zerodha Kite Connect  
**Market Coverage:** NSE and BSE equities + Mainboard & SME IPOs (NSE Emerge / BSE SME)  
**Future Market Coverage:** Futures and Options  
**Architecture:** Django Modular Monolith  
**Development Environment:** Local-first, production-ready design

---

# 1. PROJECT VISION

Build a comprehensive Indian stock market research, portfolio management, technical analysis, primary market (IPO) intelligence, and AI-assisted investment platform.

The application should help the user make informed investment and trading decisions using:

- Indian stock market data.
- Historical price analysis.
- Technical indicators.
- Fundamental analysis.
- Primary market (IPO) research, canonical lifecycle tracking, live subscription analytics, valuation, allotment planning, and listing performance.
- Portfolio and existing holdings analysis.
- Stock screening.
- Swing trading opportunities.
- Risk management.
- AI-powered research.
- Machine learning experiments.
- Market news and corporate events.
- Alerts and notifications.
- Strategy backtesting.

The platform must support both existing investors and new investment opportunities across secondary and primary markets.

It must distinguish between:
1. A stock that the user already owns.
2. A stock that the user is considering buying.
3. A stock that the user is monitoring for swing trading.
4. An upcoming, live, or closed IPO that the user is evaluating or bidding on.

These situations require different analysis, metrics, and recommendations.

The platform is intended for personal research and decision support. It must not automatically execute trades or submit bids.

---

# 2. CORE DESIGN PRINCIPLES

1. Use Django as the primary backend framework.
2. Implement a modular monolith.
3. Create separate Django apps for distinct business functionalities.
4. Use one common HTML application shell.
5. Keep the sidebar and top header persistent.
6. Dynamically load module content in the central content area.
7. Use reusable components and template inheritance.
8. Keep business logic outside Django views.
9. Keep external data providers behind adapters.
10. Keep financial calculations deterministic and testable.
11. Use background processing for expensive operations.
12. Store historical market and IPO data in PostgreSQL.
13. Use Redis for caching and Celery task coordination.
14. Maintain a provider-independent data model.
15. Make all major features independently testable.
16. Avoid duplicated business logic and circular dependencies.
17. Never fabricate market or IPO data.
18. Display data source and freshness.
19. Preserve historical portfolio transactions.
20. Keep broker integration optional.
21. Enforce strict numerical readability with tabular numerals across all financial values.
22. Strictly separate charting roles: TradingView Lightweight Charts for price/technical charts, Apache ECharts for dashboard and analytical visualizations.

---

# 3. TECHNOLOGY STACK

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Backend | Django |
| Frontend | Django Templates |
| UI Framework | Bootstrap 5 |
| Dynamic navigation | HTMX |
| Browser scripting | JavaScript (ES6+) |
| Technical Price Charts | TradingView Lightweight Charts (v4.x/v5.x) |
| Dashboard & Analytics Charts | Apache ECharts (v5.x) |
| Typography System | Inter Variable Font + CoolAdmin-inspired Hierarchy + Tabular Numerals (`font-variant-numeric: tabular-nums`) |
| API framework | Django REST Framework |
| Database | PostgreSQL |
| Cache | Redis |
| Background tasks | Celery |
| Scheduler | Celery Beat |
| Secondary Market Data | Jugaad-Data + Yahoo Finance |
| Primary Market / IPO Data | ipos.markets REST API + NSE India + BSE India + SEBI |
| Data analysis | Pandas, NumPy |
| Technical analysis | pandas-ta / TA-Lib where available |
| AI integration | Provider-independent AI service |
| Testing | Pytest / Django Test Framework |
| Code quality | Ruff / Black |
| Configuration | python-dotenv |

Use compatible, maintained package versions. Pin the actual selected versions in the dependency files.

---

# 4. DJANGO PROJECT ARCHITECTURE

## 4.1 Project directory

```text
indian_stock_intelligence/
│
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── MASTER_SPECIFICATION_DJANGO.md
├── IMPLEMENTATION_STATUS.md
├── ARCHITECTURE.md
│
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py
│
├── apps/
│   ├── core/
│   ├── accounts/
│   ├── dashboard/
│   ├── market/
│   ├── instruments/
│   ├── stocks/
│   ├── technical_analysis/
│   ├── fundamental_analysis/
│   ├── portfolio/
│   ├── holdings/
│   ├── ipo/
│   ├── trading/
│   ├── screener/
│   ├── watchlists/
│   ├── ai_analysis/
│   ├── ml_engine/
│   ├── news/
│   ├── alerts/
│   ├── backtesting/
│   ├── brokers/
│   ├── reports/
│   ├── notifications/
│   └── settings_app/
│
├── integrations/
│   ├── market_data/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── normalizer.py
│   │   ├── health.py
│   │   └── providers/
│   │       ├── jugaad/
│   │       ├── yahoo/
│   │       └── zerodha/
│   ├── ipo_providers/
│   │   ├── base.py
│   │   ├── ipos_markets.py
│   │   ├── nse.py
│   │   ├── bse.py
│   │   └── sebi.py
│   ├── ai_providers/
│   ├── news_providers/
│   └── broker_providers/
│
├── services/
│   ├── market_data/
│   ├── indicators/
│   ├── fundamentals/
│   ├── ipo/
│   │   ├── lifecycle.py
│   │   ├── subscription.py
│   │   ├── research.py
│   │   ├── valuation.py
│   │   ├── scoring.py
│   │   ├── planner.py
│   │   ├── allotment.py
│   │   ├── comparison.py
│   │   ├── performance.py
│   │   └── sync.py
│   ├── portfolio/
│   ├── risk/
│   ├── recommendations/
│   └── common/
│
├── templates/
│   ├── base/
│   ├── components/
│   ├── ipo/
│   │   ├── dashboard.html
│   │   ├── issues_list.html
│   │   ├── calendar.html
│   │   ├── bid_planner.html
│   │   ├── applications.html
│   │   ├── performance.html
│   │   ├── comparison.html
│   │   ├── detail.html
│   │   └── partials/
│   └── errors/
│
├── static/
│   ├── css/
│   │   ├── typography.css
│   │   └── custom.css
│   ├── js/
│   │   ├── charts-lightweight.js
│   │   ├── charts-echarts.js
│   │   └── htmx-lifecycle.js
│   ├── images/
│   └── vendor/
│
├── media/
├── logs/
├── scripts/
├── tests/
└── docs/
```

## 4.2 Django app responsibilities

| Django app | Responsibility |
|---|---|
| core | Shared utilities, base functionality, mixins |
| accounts | User authentication and preferences |
| dashboard | Executive market dashboard |
| market | Market overview, indices, sector metrics |
| instruments | Exchange and instrument master |
| stocks | Stock profiles, search, fundamentals, financials |
| technical_analysis | Technical indicators, overlays, signals |
| fundamental_analysis | Financial metrics, ratios, peer valuation |
| portfolio | Portfolio management, asset allocation |
| holdings | Existing holdings, buy/sell transactions |
| ipo | IPO Intelligence Centre: canonical lifecycle, live subscription analytics, fundamental valuation, quantitative scoring, bid planner, allotment probability, and listing performance |
| trading | Swing trading, trade setups, position sizing, trade journal |
| screener | Custom stock screening, saved presets |
| watchlists | User watchlists, alerts monitoring |
| ai_analysis | AI stock research and multi-perspective insights |
| ml_engine | Machine learning models, price predictions |
| news | Financial news and corporate action calendar |
| alerts | Price, technical, and portfolio alerts |
| backtesting | Historical strategy backtesting and drawdown analysis |
| brokers | Broker connectivity (Zerodha Kite) |
| reports | Analytical reports, PDF/CSV exports |
| notifications | In-app and external user notifications |
| settings_app | Application configuration, provider health |

Every app must have clearly defined responsibilities.

Do not place all application logic inside `views.py` or `models.py`.

---

# 5. USER INTERFACE ARCHITECTURE

## 5.1 Common HTML shell

Create a single common HTML application shell.

The shell must include:

- Left sidebar.
- Top header.
- Main content section.
- Global notifications.
- Optional footer.

The sidebar and header must remain visible when switching modules.

Only the central content section should update during normal module navigation.

## 5.2 Sidebar structure

**OVERVIEW**
- Dashboard
- Market Overview

**RESEARCH**
- Stock Analysis
- Technical Analysis
- Fundamental Analysis
- Stock Screener
- Sector Analysis
- News & Events

**IPO INTELLIGENCE**
- IPO Dashboard
- Primary Issues Desk (Catalog & Filters)
- IPO Calendar
- Bid Planner & Lot Calculator
- Allotment Tracker
- Listing Performance
- Compare IPOs
- Fundamental Research & Valuation

**MY INVESTMENTS**
- Portfolio Overview
- My Holdings
- Watchlists
- Investment Journal

**TRADING**
- Swing Trading
- Trading Signals
- Strategy Backtesting
- Risk Management

**INTELLIGENCE**
- AI Stock Research
- AI Recommendations
- ML Predictions
- Alerts & Notifications

**SYSTEM**
- Data Sources & Health
- Broker Connections
- Reports & Exports
- Application Settings

## 5.3 Dynamic module navigation

Use Django template inheritance and HTMX.

Example:

```html
<div id="main-content">
    <!-- Selected module content -->
</div>
```

Requirements:

1. Clicking a sidebar link loads the module into `#main-content`.
2. The sidebar remains unchanged.
3. The header remains unchanged.
4. Update browser URL using history support (`hx-push-url="true"`).
5. Highlight the active navigation item.
6. Show loading indicators.
7. Support browser back and forward.
8. Support direct access to every module URL.
9. Support full-page fallback if HTMX is unavailable.
10. Return partial templates for HTMX requests and full templates for normal requests (`HTMXResponseMixin`).

Use a shared base template.

Do not create a separate HTML shell for every Django app.

## 5.4 Header

Include:

- Application logo and title.
- Market status indicator (Market Open / Closed with countdown).
- Major Indian indices: NIFTY 50, SENSEX, NIFTY BANK.
- Global stock and IPO search bar.
- Notifications dropdown with unread badge.
- Data freshness indicator and sync status.
- User settings and profile menu.

Do not hardcode market values.

## 5.5 Typography and Text Styling System (CoolAdmin Reference)

The visual design system adopts **ONLY** the typography system and text styling inspired by the CoolAdmin template (`typo.html`), preserving the existing Tabler / Bootstrap 5 shell, HTMX navigation, cards, widgets, and layout.

### A. Strict Scope
- **Adopt typography and text styling only.**
- Do not copy CoolAdmin's layout, dashboard structure, cards, or widgets.
- Maintain consistent font rendering and hierarchy across all Django applications.

### B. Font Family & Rendering
- **Primary Font Family:** Inter variable font (`Inter`, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif).
- **Fallback Stack:** Standard system sans-serif fonts.
- **Rendering:** Anti-aliased font smoothing (`-webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;`).

### C. Typography Scale & Hierarchy
Adopt a strict typographic hierarchy:

| Element | CSS Selector / Class | Font Size | Font Weight | Line Height | Usage |
|---|---|---|---|---|---|
| Page Title | `h1`, `.h1` | 1.75rem – 2.0rem (28–32px) | 700 (Bold) | 1.25 | Primary module page titles |
| Section Header | `h2`, `.h2` | 1.375rem – 1.5rem (22–24px) | 600–700 | 1.3 | Major module sections & panels |
| Subsection Title | `h3`, `.h3` | 1.125rem – 1.25rem (18–20px) | 600 (Semibold) | 1.35 | Widget headers, card titles |
| Component Header | `h4`–`h6` | 0.9375rem – 1.0rem (15–16px) | 600 (Semibold) | 1.4 | Table titles, group captions |
| Body Text | `p`, `body` | 0.875rem (14px) | 400 (Regular) | 1.5 | Standard body descriptions |
| Small / Meta | `small`, `.small` | 0.75rem – 0.8125rem (12–13px) | 400–500 | 1.4 | Timestamps, subtitles, badges |
| Micro / Captions | `.text-xs` | 0.6875rem (11px) | 500 (Medium) | 1.3 | Footnotes, tag labels, exchange indicators |

### D. Centralized Design Tokens & Color Palette
Centralize all typography variables in a shared stylesheet (`static/css/typography.css`):

```css
:root {
    --font-family-base: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --font-family-mono: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;

    --font-size-xs: 0.6875rem;   /* 11px */
    --font-size-sm: 0.75rem;     /* 12px */
    --font-size-base: 0.875rem;  /* 14px */
    --font-size-md: 0.9375rem;   /* 15px */
    --font-size-lg: 1.0rem;      /* 16px */
    --font-size-xl: 1.25rem;     /* 20px */
    --font-size-2xl: 1.5rem;     /* 24px */
    --font-size-3xl: 1.75rem;    /* 28px */

    --font-weight-normal: 400;
    --font-weight-medium: 500;
    --font-weight-semibold: 600;
    --font-weight-bold: 700;

    --line-height-base: 1.5;
    --line-height-heading: 1.25;

    /* Semantic Text Colors */
    --text-primary: #1e293b;
    --text-secondary: #475569;
    --text-muted: #64748b;
    --text-disabled: #94a3b8;
    --text-link: #0284c7;

    /* Financial Semantic Colors */
    --color-positive: #10b981;       /* Bullish / Profit / Gain */
    --color-negative: #ef4444;       /* Bearish / Loss / Drawdown */
    --color-warning: #f59e0b;        /* Caution / Pending / Allotment Finalized */
    --color-info: #0284c7;           /* Neutral / Informational / Active Bids */
}
```

### E. Financial Data Typography & Tabular Numerals
Because this is a professional financial intelligence platform, numeric readability is paramount:

1. **Tabular Numerals:** Always use tabular numbers for financial and statistical figures to prevent horizontal jitter when values update and ensure vertical alignment in tables:
   ```css
   .num-mono, .financial-value {
       font-variant-numeric: tabular-nums;
       font-feature-settings: "tnum" 1;
       font-family: var(--font-family-mono);
   }
   ```
2. **Numbers Requiring Tabular Styling:**
   - Stock prices, day changes, and percentage moves.
   - Portfolio current values, invested amounts, and unrealized/realized P&L.
   - Financial ratios: P/E, P/B, EV/EBITDA, ROE, ROCE, Debt/Equity.
   - Trading levels: Entry price, Stop Loss, Target 1, Target 2.
   - Primary market figures: IPO price bands, lot sizes, min application investment, issue size in ₹ Cr, subscription multiples, and GMP.
3. **Table Column Alignment:** Numerical columns (prices, quantities, amounts, percentages) must be right-aligned (`text-end`).
4. **Indian Currency Notation:**
   - Standardize amounts using the Indian numbering format (`₹XX,XX,XXX.XX` via `intcomma_inr`).
   - For issue sizes and market caps, express values in `₹... Cr` with the currency symbol and `Cr` unit styled in clean sans-serif outside monospace numerals to avoid character clipping.

### F. Component-Level Typography
- **Tables:** Headings in uppercase, muted small (`0.75rem`), letter-spaced (`0.05em`), font weight 600. Table cells in 0.875rem body text.
- **Form Controls:** Labels in 0.8125rem font-weight 500 (`text-secondary`); input placeholders in muted italic/normal; helper text in 0.75rem.
- **Breadcrumbs:** Clean inline paths with small font size (`0.8125rem`), active page in bold body color.
- **Badges & Status Labels:** Compact padding (`px-2 py-0.5`), font weight 600, font size `0.72rem–0.75rem`, border-radius matching design system.
- **Empty States:** Clear bold title (`h5 fw-bold`), muted supportive text (`small text-muted`), actionable reset button.

---

## 5.6 Dual-Engine Charting Architecture (Lightweight Charts + Apache ECharts)

The platform enforces a strict dual-library charting architecture:

| Library | Role | Scope & Use Cases |
|---|---|---|
| **TradingView Lightweight Charts** (v4.x/v5.x) | Primary Stock & Technical Price Charts | Candlesticks, OHLC, volume histogram (synchronized pane), SMA 20/50/200, EMA 9/20/50, Bollinger Bands, separate panes for RSI 14 & MACD, trading level overlays (Entry, Target 1, Target 2, Stop Loss), crosshair tooltips, time/price scales, zoom/scroll, and post-listing price history for listed IPOs. |
| **Apache ECharts** (v5.x) | Dashboard Analytics & Visualizations | Executive dashboard charts, portfolio allocation donuts, sector exposure bars, market breadth (advance/decline), stock performance comparisons, sector heatmaps, backtesting equity curves & drawdown distributions, and IPO subscription velocity & 7-factor radar scoring charts. |

### A. Strict Charting Restrictions
- **Lightweight Charts** is the mandatory engine for stock price and technical charts.
- **Apache ECharts** is the mandatory engine for general financial analytics and multi-dimensional dashboards.
- **Never** use ECharts to duplicate the main candlestick chart.
- **Never** introduce paid or closed-source charting alternatives (e.g. TradingView Advanced Charts paid library, Highcharts commercial license).
- **Never** introduce mock or synthetic candle data.

### B. TradingView Lightweight Charts Specification
1. **Chart Header & Toolbar:**
   - Stock name, symbol, and exchange badge (NSE/BSE).
   - Live / last close price, absolute change, percentage change.
   - Market data source and freshness timestamp.
   - Timeframe selector: `1D`, `1W`, `1M`.
   - Chart type toggle: Candlestick, Line, Area.
   - Indicator dropdown: SMA 20, SMA 50, EMA 20, Bollinger Bands, RSI 14, MACD.
   - Controls: Reset zoom, crosshair toggle, fullscreen.
2. **Main Price Chart:**
   - Candlesticks: Up candle `#10b981`, Down candle `#ef4444`, clean subtle grid lines.
   - SMA Overlays: SMA 20 (Blue `#3b82f6`), SMA 50 (Orange `#f97316`).
   - Price scale on right side; time scale on bottom with Indian market trading hours (09:15 – 15:30 IST).
   - Interactive crosshair with floating price and date markers.
   - Top-left floating OHLC legend showing values at crosshair position.
3. **Synchronized Volume Pane:**
   - Volume histogram rendered in an independent synchronized pane directly below price.
   - Green/red bars matching candlestick direction; independent volume scale.
4. **Trading Level Overlays:**
   - Target 1: Green dashed horizontal line (`#10b981`).
   - Target 2: Teal dashed horizontal line (`#14b8a6`).
   - Stop Loss: Red dashed horizontal line (`#ef4444`).
   - Entry Price: Neutral blue/gray line (`#64748b`).
   - Explicit price labels on the right-hand price scale.
5. **Separate Indicator Panes:**
   - RSI 14: Dedicated bottom pane with overbought (70) and oversold (30) threshold lines.
   - MACD (12, 26, 9): Dedicated pane with MACD line, signal line, and momentum histogram.

### C. Apache ECharts Specification
1. **Portfolio Asset Allocation:** Donut chart with inner radius 55%, outer radius 75%, showing asset classes, sectors, and top 10 holdings with custom tooltip formatting.
2. **Sector Exposure & Heatmap:** Interactive treemap or bar charts showing portfolio weight vs benchmark weight.
3. **Market Breadth:** Advance/decline ratio bar, 52-week highs vs lows comparison.
4. **IPO Subscription Velocity:** Stacked category subscription bars (QIB, NII, Retail) across issue days.
5. **IPO Quantitative Scoring Radar:** 7-axis radar chart displaying scores for Business, Financials, Valuation, Growth, Governance, Issue Structure, and Demand.
6. **Backtesting Performance:** Equity curve with underwater drawdown chart and benchmark comparison line.

### D. HTMX Chart Lifecycle & Clean Teardown Protocol
Because the application uses HTMX for dynamic partial page swaps, frontend charting must strictly adhere to the chart lifecycle to prevent memory leaks and zombie event listeners:

1. **Initialization:** Charts must initialize on `htmx:afterSwap` and `htmx:load` events, targeting container elements present in the swapped DOM.
2. **Disposal & Teardown:**
   - Before `#main-content` is swapped out (`htmx:beforeSwap`), all active chart instances must be cleanly disposed:
     - Lightweight Charts: `chartInstance.remove(); chartInstance = null;`
     - ECharts: `echartsInstance.dispose(); echartsInstance = null;`
3. **Resize Observers:** Attach a `ResizeObserver` to the chart container rather than global window listeners to guarantee responsive re-rendering when sidebars collapse or window dimensions change.
4. **History Restoration:** When navigating via browser back/forward buttons (`htmx:historyRestore`), re-initialize the chart instances from the restored DOM container.
5. **Theme Synchronization:** Chart themes (light / dark) must listen to theme toggle events and update grid lines, background colors, and crosshairs without reloading the page.

---

---

# 6. MARKET DATA PROVIDER ARCHITECTURE

This is one of the most important parts of the application.

The system must support multiple providers without coupling business logic to any specific provider.

## 6.1 Initial provider strategy

**Initial Provider 1: Jugaad-Data**

Repository:

https://github.com/jugaad-py/jugaad-data

Python installation:

```bash
pip install jugaad-data
```

Use as the preferred initial provider for supported Indian NSE data.

Potential functionality, subject to endpoint availability:

- Historical equity data.
- Historical index data.
- NSE bhavcopy.
- Live quote data.
- F&O data.
- Delivery information where available.

Important:
Jugaad-Data uses NSE website endpoints. It is not a guaranteed licensed real-time market data feed. Handle endpoint changes, throttling, availability and terms responsibly.

**Initial Provider 2: Yahoo Finance**

Documentation:

https://ranaroussi.github.io/yfinance/

Installation:

```bash
pip install yfinance
```

Use Yahoo Finance as a secondary historical data source.

Potential functionality:

- Historical OHLCV.
- Historical index data.
- Additional chart history.
- Price-history comparison.
- Research support.

Examples of Yahoo symbols:

```text
RELIANCE.NS
TCS.NS
INFY.NS
SBIN.NS
RELIANCE.BO
```

Important:
Yahoo Finance data can be delayed, incomplete or unavailable for certain symbols and intervals. `yfinance` is an open-source interface to Yahoo Finance, not an official Yahoo market-data API. Respect Yahoo's terms and do not assume that the data can be redistributed.

**Future Provider 3: Zerodha Kite Connect**

Integration will be optional and implemented in a future phase.

Potential functionality:

- Broker authentication.
- Instrument master.
- Live quotes.
- Historical candles.
- Holdings.
- Positions.

Do not make Kite mandatory for the application to function.

## 6.2 Provider responsibilities

| Requirement | Primary | Secondary |
|---|---|---|
| NSE historical equity | Jugaad | Yahoo |
| NSE daily bhavcopy | Jugaad | None by default |
| Historical indices | Jugaad | Yahoo |
| Daily stock charts | Jugaad | Yahoo |
| Historical comparison | Jugaad | Yahoo |
| Current quotes | Jugaad where available | Yahoo indicative only |
| Intraday research | Validate source capability | Validate source capability |
| Delivery information | Jugaad supported reports | None by default |
| F&O research | Jugaad where available | Future provider |
| Broker holdings | Manual entry | Kite in future |
| Broker live data | Not required initially | Kite in future |

Do not assume that the same provider is best for every data type.

## 6.3 Provider interface

Create a provider abstraction.

```python
from abc import ABC, abstractmethod

class MarketDataProvider(ABC):

    @abstractmethod
    def get_quote(self, instrument):
        pass

    @abstractmethod
    def get_historical_data(
        self,
        instrument,
        start_date,
        end_date,
        interval
    ):
        pass

    @abstractmethod
    def get_instruments(self):
        pass

    @abstractmethod
    def health_check(self):
        pass
```

Implement:

```text
JugaadDataProvider
YahooFinanceProvider
ZerodhaKiteProvider
```

Each provider must implement the common interface.

Provider-specific functions must remain inside the adapter.

Business apps must call the common MarketDataService.

## 6.4 MarketDataService

Create a central service:

```python
class MarketDataService:

    def get_quote(self, instrument):
        pass

    def get_historical_data(
        self,
        instrument,
        start_date,
        end_date,
        interval
    ):
        pass

    def refresh_instrument(self, instrument):
        pass

    def get_provider_status(self):
        pass
```

The service must:

- Select the configured provider.
- Apply provider priority.
- Normalise results.
- Validate results.
- Cache eligible results.
- Handle failures.
- Record provider information.
- Support fallback where appropriate.

## 6.5 Normalised data schema

Standard OHLCV format:

```text
instrument_id
symbol
exchange
timestamp
interval
open
high
low
close
volume
adjusted_close
source_provider
source_timestamp
retrieved_at
is_delayed
data_status
```

Use DecimalField for financial values in the database.

Store timestamps in UTC.

Retain exchange-local session information where necessary.

Keep adjusted and unadjusted prices separate.

## 6.6 Data quality

Validate:

- OHLC relationships.
- Missing candles.
- Duplicate candles.
- Invalid prices.
- Negative volume.
- Timestamp alignment.
- Corporate actions.
- Provider discrepancies.
- Historical gaps.
- Adjusted versus unadjusted values.

When providers disagree:

1. Compare instrument identity.
2. Compare exchange.
3. Compare session and timestamp.
4. Check corporate action adjustments.
5. Check source delay.
6. Apply configured source priority.
7. Record the discrepancy.

Never average conflicting stock prices.

Do not silently overwrite higher-quality data with lower-quality data.

## 6.7 Fallback behaviour

If Jugaad fails:

- Use Yahoo only if suitable for the requested data type.
- Mark the actual source.
- Show a fallback warning.
- Record the error.
- Never label historical or delayed data as live.

Do not use Yahoo as an automatic fallback for exchange-sensitive intraday signals unless its data suitability has been verified.

## 6.8 Data provider settings

Create a Data Sources page.

Show:

- Provider.
- Enabled/disabled status.
- Supported data types.
- Last successful request.
- Last successful refresh.
- Data freshness.
- Health status.
- Last error.
- Configured priority.

Allow provider priority to be configured independently by data type.

---

# 7. MARKET DATA STORAGE AND COLLECTION

Create models for:

- Instrument.
- Exchange.
- MarketQuote.
- HistoricalCandle.
- CorporateAction.
- MarketIndex.
- DataProvider.
- DataRefreshLog.
- DataQualityIssue.

Use unique constraints for:

```text
instrument + timestamp + interval
```

Implement:

- Initial historical data import.
- Incremental historical updates.
- Daily market data refresh.
- Index refresh.
- Data validation.
- Retry and failure tracking.

Use Celery tasks for bulk imports and scheduled updates.

Do not perform lengthy imports during HTTP page requests.

Avoid repeated requests to NSE endpoints.

Respect provider terms, rate limits and usage restrictions.

---

# 8. INSTRUMENT AND STOCK MANAGEMENT

Maintain an instrument master for NSE and BSE.

Fields:

- Symbol.
- Trading symbol.
- Company name.
- Exchange.
- Instrument token.
- ISIN.
- Sector.
- Industry.
- Market cap category.
- Listing status.
- Instrument type.

Support search by:

- Company name.
- NSE symbol.
- BSE symbol.
- ISIN.

Stock detail page must include:

- Current quote.
- Historical chart.
- Technical indicators.
- Fundamental analysis.
- News.
- Corporate events.
- AI analysis.
- Watchlist status.
- Holding status.
- User notes.

Maintain correct mappings between provider symbols and internal instruments.

## 8.1 Company Logo Subsystem & Offline Persistence

To prevent external network latency and eliminate broken images across the UI, implement an institutional-grade, local-disk-first logo subsystem (`services/logos/service.py`) and dedicated proxy endpoint (`/stocks/<symbol>/logo/`):

1. **Local-Disk-First Architecture**:
   - Stock vector logos are stored permanently on local disk at `static/branding/stock_logos/{SYMBOL}.svg` (or `.png`).
   - Served in **< 1 millisecond** with zero external network requests and **0 MB server RAM consumption**.
2. **Multi-Tier Resolution Strategy & Sources**:
   - **Tier 1 (Local Disk)**: Reads pre-downloaded vector files directly from disk (`< 1ms`).
   - **Tier 2 (In-Memory Cache)**: Checks Django cache for high-concurrency partial requests.
   - **Tier 3 (Shareperks ISIN CDN - Primary CDN)**: Queries `https://company-logo.shareperks.in/logo/{isin}/icon.svg` (officially co-engineered by Dharun Ashokkumar and Shareperks). Resolves vector SVGs directly via the instrument's unique ISIN code (e.g. `INE002A01018` for Reliance, `INE155A01022` for Tata Motors, `INE062A01020` for SBI).
   - **Tier 4 (Cross-Exchange & Direct Symbol CDNs)**: Fetches official SVG vectors from `dharunashokkumar/indian-listed-company-logos` on GitHub/jsDelivr (`data/logos/nse/NSE_{symbol}.svg` and `data/logos/bse/BSE_{symbol}.svg`). Automatically maps BSE numeric scrip codes (e.g. `500112`) to their sibling primary NSE ticker (`SBIN`) to guarantee official vector coverage across exchanges.
   - **Tier 5 (Deterministic Vector Monogram)**: If an obscure SME/microcap stock or ETF basket lacks an official logo, generates a high-DPI SVG monogram badge using the symbol's initials and a deterministic brand color palette. The monogram is permanently saved to disk so future requests render in 0 ms.
3. **Batch Synchronization Command**:
   ```bash
   python manage.py sync_stock_logos [--force] [--concurrency 16] [--symbols SYMBOL1,SYMBOL2]
   ```
   - Multithreaded CLI tool synchronizing logos for all distinct symbols currently present in the database's `ExchangeListing` table.
   - *Active Tracking Universe vs Full Market Universe*: The command queries `ExchangeListing.objects.values_list("symbol", flat=True).distinct()`. In the initial seeded database, there are **284 benchmark listings** (Nifty 50, Nifty Next 50, Nifty Midcap 150 benchmark listings, IPO radar, and tracked equities). As additional stocks from the broader ~2,700 NSE or ~5,700 BSE universe are imported, their logos are automatically saved on-demand via Tier 3/4 write-through caching, or can be bulk-synced using this command.
   - Storage footprint is extremely lightweight: **~365 KB for 284 benchmark stocks** (< 0.4 MB) and projected at ~20 MB for the full 8,000+ NSE/BSE universe with zero RAM overhead.

---

# 9. DASHBOARD MODULE

Create a dashboard as the application's landing page.

## Market summary

- NIFTY 50.
- SENSEX.
- NIFTY BANK.
- NIFTY IT.
- India VIX.
- Market status.
- Advance/decline ratio where available.

## Portfolio summary

- Total invested amount.
- Current market value.
- Unrealised P&L.
- Realised P&L.
- Day P&L.
- Overall return.

## Market opportunities

- Top gainers.
- Top losers.
- Stocks near breakouts.
- Strong technical setups.
- Stocks approaching support/resistance.

## User summary

- Watchlists.
- Existing holdings.
- Active trade setups.
- Recent alerts.
- Latest AI analysis.
- Upcoming corporate events.

All values must come from actual stored or retrieved data.

Display data freshness.

---

# 10. TECHNICAL ANALYSIS MODULE

Implement institutional-grade indicators (`tech-v2.0.0`) with vectorized computation in `services/indicators/calculator.py` and persistent snapshots in `apps/technical_analysis/models.py`.

## Trend

- SMA 20, SMA 50, SMA 100, SMA 200.
- EMA 9, EMA 20, EMA 50.
- MACD (12, 26, 9) with histogram and centerline signal.
- **SuperTrend (10, 3)** (`tech-v2.0.0`):
  - Upper Band $= \frac{\text{High} + \text{Low}}{2} + 3.0 \times \text{ATR}_{10}$.
  - Lower Band $= \frac{\text{High} + \text{Low}}{2} - 3.0 \times \text{ATR}_{10}$.
  - Direction indicator ($+1$ Bullish green trailing support / $-1$ Bearish red overhead resistance).

## Momentum

- RSI 14 (Wilder's smoothing).
- Stochastic RSI (14, 3, 3).
- **Wilder's Directional Movement Index & ADX (14)** (`tech-v2.0.0`):
  - True Range: $\text{TR}_t = \max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)$.
  - Directional Movements: $+\text{DM} = \max(H_t - H_{t-1}, 0)$ if $(H_t - H_{t-1}) > (L_{t-1} - L_t)$ else $0$; $-\text{DM} = \max(L_{t-1} - L_t, 0)$ if $(L_{t-1} - L_t) > (H_t - H_{t-1})$ else $0$.
  - 14-period Wilder RMA smoothing for $+\text{DI}_{14}$ and $-\text{DI}_{14}$.
  - Directional Index: $\text{DX} = 100 \times \frac{|+\text{DI} - -\text{DI}|}{+\text{DI} + -\text{DI}}$.
  - Trend Confirmation: $\text{ADX}_{14} = \text{WilderEMA}(\text{DX}, 14)$. Values $\ge 25.0$ confirm robust directional trend momentum; values $< 20.0$ classify price action as choppy range-bound consolidation.
- Rate of Change (ROC 10).

## Volatility

- Bollinger Bands (20 periods, 2 standard deviations) with Bollinger Bandwidth (BBW).
- Average True Range (ATR 14).
- Historical close-to-close rolling volatility.

## Volume & Benchmark

- Volume 20-day moving average.
- Relative volume (RVOL) surge ratio.
- Volume breakout detection ($> 1.5\times$ 20 SMA).
- On-Balance Volume (OBV).
- **Cumulative Volume Weighted Average Price (VWAP)** (`tech-v2.0.0`):
  - $\text{VWAP} = \frac{\sum (\text{Typical Price} \times \text{Volume})}{\sum \text{Volume}}$ where $\text{Typical Price} = \frac{H + L + C}{3}$.
  - Serves as the institutional liquidity benchmark. Price holding above VWAP indicates institutional buyer dominance; price trading below VWAP indicates distribution pressure.

## Price structure & Retracement

- Support & Resistance pivot levels.
- Swing highs & swing lows.
- 20-day price breakout signals (RESISTANCE_BREAKOUT / SUPPORT_BREAKDOWN).
- Moving average crossovers (Golden Cross: SMA 50 crossing above SMA 200; Death Cross: SMA 50 crossing below SMA 200).
- Parabolic SAR ($0.02$ step, $0.20$ max).
- Fibonacci Retracements ($0.0\%, 23.6\%, 38.2\%, 50.0\%, 61.8\%, 78.6\%, 100.0\%$).

## Timeframes

- 5 minutes.
- 15 minutes.
- 30 minutes.
- 1 hour.
- Daily.
- Weekly.
- Monthly.

Only expose intervals supported by the selected data source.

## Signal generation

Generate:

- Bullish trend.
- Bearish trend.
- RSI overbought.
- RSI oversold.
- MACD crossover.
- Moving average crossover.
- Volume breakout.
- Support breakout.
- Resistance breakout.

Every signal must show:

- Trigger condition.
- Indicator values.
- Timestamp.
- Data source.
- Signal validity.

---

# 11. FUNDAMENTAL ANALYSIS MODULE

Collect and calculate:

- Revenue.
- Revenue growth.
- Operating profit.
- Operating margin.
- Net profit.
- EPS.
- P/E.
- P/B.
- ROE.
- ROCE.
- Debt-to-equity.
- Current ratio.
- Dividend yield.
- Free cash flow.
- Promoter holding.
- FII holding.
- DII holding.

Do not assume Jugaad or Yahoo provides complete reliable fundamentals.

Use a separate fundamental-data provider interface.

If a reliable source is unavailable, allow manual data entry or mark the field unavailable.

## Fundamental scoring (`fund-v2.0.0`)

Evaluate:

- Growth (revenue & profit YoY).
- Profitability (ROE, ROCE, operating & net margins).
- Valuation (P/E relative to sector, P/B, EV/EBITDA).
- Financial health (Debt/Equity, current ratio, interest coverage).
- Ownership (promoter, FII, DII stability).
- Dividend history & yield.

### Institutional Scoring & Guardrails (`fund-v2.0.0`)

1. **Piotroski 9-Point F-Score ($0 \le F \le 9$)**:
   - **Profitability (4 pts)**:
     - Positive ROA ($\text{ROA} > 0$).
     - Positive Operating Cash Flow ($\text{CFO} > 0$).
     - Increasing ROA YoY ($\Delta \text{ROA} > 0$).
     - Accruals quality: Cash Flow from Operations exceeding Net Income ($\text{CFO} > \text{Net Income}$).
   - **Leverage & Liquidity (3 pts)**:
     - Decreasing or stable long-term financial leverage ($\Delta \text{Debt/Equity} \le 0$).
     - Improving current liquidity ratio ($\Delta \text{Current Ratio} > 0$).
     - Zero shareholder dilution (no new share issuances).
   - **Operating Efficiency (2 pts)**:
     - Expanding Gross Margin YoY ($\Delta \text{Gross Margin} > 0$).
     - Improving Asset Turnover YoY ($\Delta \text{Asset Turnover} > 0$).
   - **Value Trap Guardrail**: Any stock scoring $F \le 3$ is automatically flagged as a **Value Trap Hazard**, warning that low P/E multiples reflect operational deterioration rather than a genuine bargain.

2. **Altman Z-Score Solvency Evaluation**:
   $$Z = 1.2 X_1 + 1.4 X_2 + 3.3 X_3 + 0.6 X_4 + 0.999 X_5$$
   - $Z \ge 2.99$: **Safe Zone** (negligible default risk, pristine solvency).
   - $1.81 \le Z < 2.99$: **Grey Zone** (moderate leverage caution).
   - $Z < 1.81$: **Distress Zone** (heightened risk of bankruptcy / credit failure). AI models automatically downgrade views to `AVOID` or `WATCH`.

3. **DuPont 3-Stage ROE Decomposition**:
   $$\text{ROE} = \underbrace{\frac{\text{Net Income}}{\text{Revenue}}}_{\text{Net Profit Margin}} \times \underbrace{\frac{\text{Revenue}}{\text{Total Assets}}}_{\text{Asset Turnover}} \times \underbrace{\frac{\text{Total Assets}}{\text{Shareholders' Equity}}}_{\text{Equity Multiplier}}$$
   Reveals whether return on equity is driven by genuine operational efficiency, high asset turnover, or hazardous balance sheet financial leverage.

Display:

- Overall score (0-100).
- Piotroski F-Score (0-9).
- Altman Z-Score with solvency classification (Safe / Grey / Distress).
- DuPont Asset Turnover and Equity Multiplier metrics.
- Positive factors.
- Negative factors (Value Trap warnings if $F \le 3$, Solvency alerts if $Z < 1.81$).
- Missing data tracking.
- Sector comparison.

Do not apply universal valuation thresholds across different sectors.

---

# 12. PORTFOLIO AND HOLDINGS MODULE

This is a critical feature.

The platform must recognise that a user may already own a stock.

## Portfolio functionality

Allow manual holdings entry.

Fields:

- Stock.
- Exchange.
- Quantity.
- Average buy price.
- Purchase date.
- Current price.
- Invested amount.
- Current value.
- Unrealised P&L.
- Realised P&L.
- Return percentage.
- Notes.

Support multiple transactions for the same stock.

Calculate weighted average purchase price correctly.

Preserve transaction history when shares are sold.

Account for splits, bonuses and other corporate actions where supported.

## Portfolio dashboard

Display:

- Total capital invested.
- Current portfolio value.
- Unrealised P&L.
- Realised P&L.
- Day P&L.
- Stock allocation.
- Sector allocation.
- Concentration risk.
- Dividend income where available.

## Existing holdings analysis

For each owned stock:

1. Current market condition.
2. Average buy price.
3. Current price.
4. Unrealised P&L.
5. Technical trend.
6. Fundamental outlook.
7. Risk level.
8. Support and resistance.
9. Suggested action.
10. Invalidation conditions.

Possible actions:

- HOLD.
- ADD / ACCUMULATE.
- PARTIAL PROFIT BOOKING.
- EXIT.
- REDUCE EXPOSURE.
- REVIEW.

Never recommend averaging down simply because the stock price has declined.

Before recommending an additional purchase, assess:

- Fundamental condition.
- Reason for price decline.
- Portfolio concentration.
- Sector exposure.
- Available capital.
- Risk tolerance.
- Investment horizon.

## Existing holder versus new investor

Every stock analysis must provide separate sections.

**Existing holder:**

- Hold/add/reduce/exit.
- Existing average price.
- Portfolio allocation.
- Risk to existing capital.

**New investor:**

- Potential entry zone.
- Entry conditions.
- Stop-loss or invalidation.
- Target levels.
- Risk/reward.
- Suitable horizon.

These recommendations may be different.

---

# 13. IPO RESEARCH & INTELLIGENCE CENTRE

## 13.1 Role & Objective
Build an end-to-end primary market research and intelligence centre covering the complete Indian IPO lifecycle across both:
- **Mainboard IPOs** (NSE and BSE)
- **SME IPOs** (NSE Emerge and BSE SME)

The module provides deterministic fundamental research, time-series subscription tracking, quantitative scoring, lot-sizing bid calculators, allotment probability estimation, personal application management, and post-listing performance tracking.

## 13.2 Canonical IPO Lifecycle & Status Machine
Track the entire regulatory and offering lifecycle with strict status transitions:
1. `DRHP_FILED` — Draft Red Herring Prospectus submitted to SEBI.
2. `SEBI_APPROVED` — SEBI observation / exchange in-principle approval issued.
3. `ANNOUNCED` / `UPCOMING` — Price band, lot size, and issue dates scheduled.
4. `LIVE` — Bidding window open (accepting bids).
5. `CLOSED` — Bidding window closed; book building concluded.
6. `ALLOTMENT_FINALIZED` — Basis of allotment approved by exchange & registrar.
7. `REFUND_INITIATED` — UPI mandate unblocking / escrow refunds released.
8. `DEMAT_TRANSFER` — Shares credited to successful applicants' demat accounts.
9. `LISTED` — First day of trading on secondary exchange; post-listing performance begins.
10. `WITHDRAWN` / `CANCELLED` / `POSTPONED` — Issues retracted or deferred.

## 13.3 Data Ingestion & Multi-Provider Architecture
Support automated ingestion with zero hardcoded or synthetic data:
- **Primary Source Adapter:** REST client for `https://ipos.markets` (`/data/issues_index.json`, `/data/overview.json`, `/data/issues/<symbol>.json`) capturing:
  - Complete live and upcoming pipeline (145+ issues including DRHPs).
  - Benchmark listed debut issues with verified historical open, close, and listing dates.
  - Subscription snapshots, issue price bands, lot sizes, issue sizes in ₹ Cr.
- **Official Exchange & Regulatory Fallbacks:**
  - NSE India: `https://www.nseindia.com/market-data/all-upcoming-issues-ipo`
  - BSE India: Public issues portal
  - SEBI: DRHP and regulatory observation repository
  - Registrar portals: Link Intime, KFin Technologies, Bigshare, Skyline.
- **Source Reliability Hierarchy:**
  `OFFICIAL_EXCHANGE` > `OFFICIAL_REGULATOR` > `OFFICIAL_ISSUER` > `OFFICIAL_REGISTRAR` > `THIRD_PARTY` > `UNOFFICIAL_MARKET_ESTIMATE`.
- **Audit & Sync:** Automated sync via `sync_ipo_data` management command, periodic Celery tasks, and HTMX one-click sync button in the dashboard. Never fabricate dates (`today - timedelta`); all dates must be authentic ISO calendar dates.

## 13.4 IPO Master Data Model (`IPOMaster`)
The canonical master record includes:
- **Identity:** `symbol`, `company_name`, `isin`, `issue_type` (`MAINBOARD`, `SME`), `exchange` (`NSE`, `BSE`, `BOTH`), `sector`, `industry`, `description`.
- **Status & Timeline:** `status`, `drhp_filing_date`, `sebi_approval_date`, `open_date`, `close_date`, `allotment_date`, `refund_date`, `demat_credit_date`, `listing_date`.
- **Issue Structure & Capital:** `price_band_min`, `price_band_max`, `issue_price`, `lot_size`, `min_investment`, `total_issue_size_cr`, `fresh_issue_cr`, `offer_for_sale_cr`, `total_shares_offered`.
- **Quotas & Dilution:** `retail_quota_percent` (min 35% for profitability route, min 10% for QIB route), `qib_quota_percent`, `nii_quota_percent`, `employee_quota_percent`, `promoter_holding_pre_issue`, `promoter_holding_post_issue`.
- **Key Parties & Filings:** `lead_managers`, `registrar`, `registrar_portal_url`, `drhp_url`, `rhp_url`, `prospectus_url`, `official_exchange_url`.
- **Listing Metrics:** `listing_day_open`, `listing_day_close`, `listing_day_high`, `listing_day_low`, `listing_day_gain_percent`, `current_market_price`, `total_gain_since_listing`.

## 13.5 Fundamental Research & Valuation Engine (`IPOFundamentals`)
Extract and compute financial metrics from official RHP/DRHP disclosures:
- **Multi-Year Financials:** 3-year history for Revenue, EBITDA, PAT, EPS, Net Worth, Total Borrowings, Operating Cash Flow, Free Cash Flow.
- **Growth & Margins:** 3-year Revenue CAGR, PAT CAGR, EBITDA Margin %, PAT Margin %.
- **Return & Solvency Ratios:** ROE %, ROCE %, Debt-to-Equity, Interest Coverage Ratio, Asset Turnover.
- **Valuation Benchmarks:** Post-issue P/E, P/B, EV/EBITDA, Market Cap at cut-off price, comparison against listed peer industry P/E (discount/premium %).
- **Proceeds Allocation:** Fresh issue capital breakdown across Capex, Debt Repayment, Working Capital, and General Corporate Purposes (GCP capped at 25% by SEBI regulations).
- **Governance & Risk Factors:** Related-party transactions, outstanding promoter litigation, customer/supplier concentration, auditor qualifications.

## 13.6 Quantitative Scoring & Recommendation Engine
A transparent, deterministic 7-dimension scoring model (0–100 scale):
1. **Business Quality & Competitive Moat (20%)** — Market positioning, industry tailwinds, customer concentration.
2. **Financial Strength & Cash Generation (20%)** — Revenue CAGR, EBITDA margins, RoNW/ROE, operating cash flow positivity.
3. **Valuation & Peer Pricing (20%)** — Post-issue P/E vs industry median, P/B vs peers, discount/premium.
4. **Growth Potential (15%)** — Historical addressable market expansion, capacity utilization.
5. **Management & Corporate Governance (10%)** — Promoter track record, litigation quantum, audit remarks.
6. **Issue Structure & Use of Proceeds (10%)** — Proportion of fresh issue vs OFS, debt retirement priority.
7. **Demand & Subscription Velocity (5%)** — QIB demand momentum, institutional backing.

### Recommendation Classes:
- `STRONG_RESEARCH_CANDIDATE` (Score >= 80)
- `CONSIDER_APPLYING` (Score 65–79)
- `APPLY_WITH_CAUTION` (Score 50–64)
- `AVOID` (Score < 50)
- `INSUFFICIENT_DATA` (Incomplete RHP disclosures or missing financials)

### Multi-Horizon Assessments:
Evaluate and report separately on:
- **Listing Gain Potential** (Driven by demand momentum, valuation gap, and market sentiment).
- **Short-Term Horizon** (1–3 months post-listing price discovery).
- **Long-Term Investment Potential** (3–5 years business compounding fundamentals).

Generate 7-axis geometry for Apache ECharts Radar visualization.

## 13.7 Live Subscription Analytics (`IPOSubscriptionSnapshot`)
Capture time-series subscription snapshots across the bidding window:
- Category breakdowns: QIB (Anchor + Regular), NII (sNII for ₹2L–₹10L, bNII for >₹10L), Retail Individual Investors (RII), Employees, Existing Shareholders.
- Metrics recorded: Shares offered, shares bid, subscription multiple (x), total valid applications received, cut-off bid share.
- Visualizations: Day-wise demand curves, category progress bars, institutional momentum indicators.

## 13.8 Grey Market Premium (GMP) Analytics (`IPOGMPRecord`)
Optional tracking of informal market sentiment:
- Fields: Reported GMP (₹), source/collector name, observation timestamp, estimated listing price (`price_band_max + gmp`), estimated listing gain %.
- **Mandatory Disclaimers:** GMP is strictly unofficial, unregulated, and subject to speculative manipulation. It must never be combined with official exchange subscription data without explicit disclaimers and must remain user-toggleable.

## 13.9 Interactive Bid Planner & Lot Calculator
An interactive financial planning calculator for investors:
- **Investor Categories:**
  - Retail Individual Investor (RII): Application amount <= ₹2,00,000.
  - Small Non-Institutional Investor (sNII): ₹2,00,000 < Amount <= ₹10,00,000.
  - Big Non-Institutional Investor (bNII): Amount > ₹10,00,000.
- **Calculations:**
  - Exact minimum lot investment (`price_band_max * lot_size`).
  - Maximum allowable lots within user's capital budget for selected category.
  - Total blocked capital via ASBA / UPI mandate.
  - Scenario outcomes at +10%, +25%, +50%, and -10% listing day pricing.
- **Strict Limitation:** Analysis and planning tool only. Never submit bids or interface directly with banking/UPI payment gateways.

## 13.10 Retail Allotment Probability Engine
Deterministic simulation of retail allotment probability based on official SEBI basis-of-allotment mechanisms:
- In oversubscribed retail issues, SEBI mandates a computer-generated lottery where each successful retail applicant receives exactly one minimum lot.
- Formula:
  $$\text{Allotment Probability} = \min\left(1.0, \frac{\text{Total Retail Lots Available}}{\text{Total Valid Retail Applications}}\right)$$
- Accounts for valid application counts vs raw subscription multiples.
- Emphasizes that applying for multiple retail lots does NOT increase allotment probability under lottery rules; applying from multiple family accounts (distinct PANs) is the only legitimate method. Never suggest multiple applications under a single PAN (invalidates the bid).

## 13.11 Personal Allotment & Application Tracker (`IPOApplication`)
Personal journal for logging applications and monitoring outcomes:
- Tracks: IPO, Investor category, Application number, Bid price, Lots applied, Amount blocked, UPI mandate status (`PENDING`, `APPROVED`, `FAILED`), Allotment status (`APPLIED`, `ALLOTTED`, `PARTIALLY_ALLOTTED`, `NOT_ALLOTTED`, `REFUNDED`), Demat credit confirmation.
- **Portfolio Integration:** One-click conversion of successful allotments into active `Holding` records in `apps.holdings`, preserving cost basis, allotment transaction date, and initial allocation weight.

## 13.12 Post-Listing Performance Analytics (`IPOListingPerformance`)
Tracks secondary market performance following market debut:
- Listing Day Metrics: Day-1 open price, day-1 high, day-1 low, day-1 close, listing day gain % vs issue price.
- Multi-Horizon Returns: Performance tracked across 1 Week, 1 Month, 3 Months, 6 Months, and 1 Year against NIFTY 50 and sector benchmarks.
- Current Market Price (CMP) and total gain % since debut.
- TradingView Lightweight Charts for daily post-listing price history.

## 13.13 Primary Issues Desk Catalog & Pagination
The catalog at `/ipo/issues/` presents a searchable, filterable directory of all issues:
- **Tab Filters:** `All`, `Live / Open`, `Upcoming Pipeline`, `Closed / Listed`.
- **Segment Filters:** `All Segments`, `Mainboard Only`, `SME Only`.
- **Fast Search:** Instant substring search across symbol, company name, sector, and industry.
- **Sorting:** By issue open date, issue size (Cr), listing gain %, or alphabetical name.
- **Server-Side Pagination:** 15 issues per page with elided navigation (`page_range`), entry summaries (`Showing 1 to 15 of 162 issues`), full query parameter preservation across page jumps (`tab`, `type`, `q`, `sort`, `page`), and HTMX push URL navigation (`hx-push-url="true"`).

## 13.14 IPO Calendar
Chronological month and week views displaying key event dates: DRHP filings, issue opening, issue closing, allotment finalization, refund releases, demat transfers, and listing debuts.

## 13.15 Executive Dashboard UI
The central dashboard at `/ipo/` provides high-level market visibility:
- **Executive KPI Cards:** Live & Open Issues count, Upcoming Pipeline count, Total Pipeline Issue Size (₹ Cr formatted with `intcomma_inr`), Average Debut Return %.
- **Live & Upcoming Spotlight:** Quick-action table with pricing strips, lot sizes, dates, and direct links to issue profiles.
- **Recent Listings Debut:** Card-based showcase of recent exchange debuts with issue price, opening price, issue size, and day-1 gains.
- **Real-Time Data Sync:** Visual sync indicator and HTMX button triggering live fetch from `ipos.markets`.

## 13.16 Empirical Listing Gain & Bid Recommendation Predictor Engine
- **Service Location:** `services/ipo/predictor.py` (`predict_listing_gain(ipo, user=None)`)
- **Mathematical Multi-Factor Weighting:**
  Combines three empirical pillars observed across historical Indian primary market debuts:
  1. **Grey Market Premium (GMP Weight ~50%):** Direct forward indicator from unregulated/street trades, converted to percentage pop above the upper price cap.
  2. **Day-3 QIB Subscription Momentum (~30%):** Institutional anchor demand. QIB oversubscription $>50\times$ yields high listing conviction; $<1\times$ signals institutional indifference.
  3. **Fundamental Quality Score (~20%):** Derived from the 5-pillar scoring engine (Valuation, Growth, Health, Quality, Subscription) out of 100.
- **Computed Outputs:**
  - Expected Listing Price Range (`₹predicted_price_min – ₹predicted_price_max`)
  - Predicted Debut Pop (`+X% to +Y%`) and Midpoint Forecast %
  - Confidence Tier: `HIGH`, `MEDIUM`, or `LOW` (based on data density of GMP quotes and QIB bids)
  - Actionable Decision Tiers:
    - `STRONG_APPLY`: Expected pop $\ge 20\%$ with robust institutional support.
    - `APPLY_RETAIL_LOTTERY`: Solid pop ($\ge 15\%$) but heavily oversubscribed; maximum 1 lot per PAN strategy recommended.
    - `APPLY_FOR_LONG_TERM`: Moderate debut gains ($\ge 5\%$) backed by strong fundamental scores ($\ge 70/100$).
    - `APPLY_WITH_CAUTION`: Marginal pop ($0\%\text{--}10\%$) with negative valuation or market sentiment risks.
    - `AVOID`: Flat or negative expected returns ($<0\%$) or severe fundamental red flags.
  - Recommended Exit Strategy: Explicit listing day guidelines (`FLIP_AT_OPEN`, `PARTIAL_PROFIT_TAKE`, `HOLD_FOR_TARGET`, `AVOID_OR_WITHDRAW`).

## 13.17 Central Family Member Demat & PAN Vault
- **Model:** `IPOFamilyMember` (`apps/ipo/models.py`)
- **Route:** `/ipo/family-vault/` (`IPOFamilyVaultView`)
- **Relationship Hierarchy:** Self, Spouse, Mother, Father, Son, Daughter, Brother, Sister, HUF (Hindu Undivided Family), Other.
- **Data Security & Privacy:**
  - Masked PAN storage and presentation (`ABCDE****F`).
  - Demat BOID (16-digit CDSL / 8-char NSDL format).
  - Default UPI Virtual Payment Address (VPA) and linked ASBA Bank name.
- **1-Click Batch Bidding Integration (`IPOBatchApplyView`, `/ipo/<symbol>/batch-apply/`):**
  - Integrated into the Bid Planner UI.
  - Allows selecting active family members to instantly create distinct `IPOApplication` records with a single click.
  - Automatically associates each application with the designated `IPOFamilyMember` foreign key.
  - Multiplies retail allotment lottery odds legally across distinct PANs:
    $$P(\ge 1\text{ allotment}) = 1 - \left(1 - \frac{1}{S_{\text{retail}}}\right)^k$$
    where $k$ is the number of distinct family PANs and $S_{\text{retail}}$ is the retail subscription multiple.

## 13.18 Automated Multi-Registrar Allotment Verification Engine
- **Service Package:** `services/ipo/registrars/`
- **Adapter Factory:** `get_registrar_adapter(registrar_name)`
- **Registrar Support Matrix:**
  1. **Link Intime India (`LinkIntimeAdapter`):** Automated verification via LinkIntime's public allotment inquiry endpoint, handling PAN matching and share allotment retrieval.
  2. **KFin Technologies (`KFintechAdapter`):** Queries KFintech primary market allotment portal with PAN and Application Number parsing.
  3. **Bigshare Services (`BigshareAdapter`):** Handles Bigshare's allotment lookup service.
- **Application Tracker Integration:**
  - Endpoint: `/ipo/applications/<uuid:pk>/registrar-check/` (`IPORegistrarCheckView`).
  - One-click verification button rendered directly on each tracked application card in `/ipo/applications/`.
  - Automatically updates `allotment_status` (`ALLOTTED`, `NOT_ALLOTTED`, `AWAITING`), `lots_allotted`, `refund_status`, and records timestamped audit notes.

## 13.19 IPO Strategy Backtesting Workspace
- **Service Location:** `services/ipo/backtester.py` (`run_ipo_backtest`)
- **Route:** `/ipo/backtest/` (`IPOBacktestWorkspaceView`)
- **Quantitative Parameter Controls:**
  - Minimum GMP Threshold % (e.g., $10\%$, $20\%$, $50\%$).
  - Minimum Institutional QIB Multiple (e.g., $1\times$, $5\times$, $10\times$).
  - Board Type Filter: All Exchanges, Mainboard Only, SME Only.
  - Lookback Horizon: 3 Months, 6 Months, 1 Year, 3 Years, All-Time.
- **Hypothetical Simulation Engine:**
  - Evaluates every historical IPO against the parameterized strategy rules.
  - Simulates a standard retail lot allocation per qualified IPO.
  - Tracks ₹1,00,000 starting portfolio compounding through listing day debut pops.
- **Interactive Visualizations & Metrics:**
  - Strategy Win Rate % (percentage of traded IPOs closing positive on listing day).
  - Average Listing Day Pop % across qualifying issues.
  - Total Cumulative Profit (₹) and Profit Factor ($\text{Gross Wins} / \text{Gross Losses}$).
  - Comparative Performance Table detailing each historical IPO's signal, allocation, and debut return.

## 13.20 Pre-RHP Pipeline Simulation Mode & Sizing Guardrails
- **Pre-RHP Simulation Mode:** For draft prospectuses (DRHP filed, SEBI observation pending) where official price bands and lot sizes have not yet been announced, the Bid Planner automatically enters **Simulation Mode**:
  - Unlocks custom share price input and estimated lot size input.
  - Dynamically recalculates total capital commitments, category limit compliance (Retail $\le ₹2,00,000$, sHNI $₹2L\text{--}₹10L$, bHNI $>₹10L$), and UPI mandate routing in real time via HTMX without page reloads.
- **Payment Routing Guardrails:**
  - Applications $\le ₹5,00,000$ route to **UPI Mandate 2.0**.
  - Applications $> ₹5,00,000$ (bHNI or high sHNI) automatically prompt for **ASBA NetBanking Mandate** per SEBI regulatory ceilings.

---

# 14. STOCK SCREENER MODULE

Create configurable screening.

Categories:

- Value stocks.
- Growth stocks.
- Dividend stocks.
- Quality stocks.
- Momentum stocks.
- Breakout stocks.
- Oversold stocks.
- Swing candidates.
- High-volume stocks.
- 52-week high stocks.
- 52-week low stocks.

Custom filters:

- Market capitalisation.
- RSI.
- SMA position.
- EMA position.
- ROE.
- ROCE.
- Debt-to-equity.
- Volume.
- Relative volume.
- Dividend yield.
- P/E.
- Revenue growth.

Allow users to:

- Combine filters.
- Save screening criteria.
- Re-run saved screeners.
- Export results.
- View why a stock matched.

---

# 15. WATCHLIST MODULE

Support multiple watchlists.

Examples:

- Long-term investment.
- Swing trading.
- Dividend stocks.
- Growth stocks.
- Existing holdings.
- Research later.

Features:

- Add/remove stocks.
- Notes.
- Current price.
- Price movement.
- Technical status.
- Latest signal.
- Alert configuration.

---

# 16. TRADING AND SWING TRADING MODULE

Primary trading horizon: 1–8 weeks.

The application is not intended for continuous intraday trading.

## Swing scanner

Example filters:

- Price above SMA 50.
- Price above SMA 200.
- RSI within configurable range.
- Positive MACD.
- Relative volume above threshold.
- Breakout above recent resistance.
- Adequate liquidity.
- Acceptable risk/reward.

All filters must be configurable.

## Trade setup

Each setup must include:

- Stock.
- Symbol.
- Current price.
- Setup timestamp.
- Strategy.
- Entry zone.
- Stop-loss.
- Target 1.
- Target 2.
- Risk/reward.
- Suggested quantity.
- Expected holding period.
- Explanation.
- Invalidation conditions.

## Risk management & Institutional Cockpit

The platform implements an **Institutional Risk Management Cockpit** (`apps/trading/views.py:RiskManagementView`) mapped to `/trading/risk-management/` and aliased to `/modules/risk_management/`.

### Core Capabilities:
1. **Portfolio Telemetry & Value at Risk (VaR)**:
   - Total open stop-loss risk (₹ and % of capital).
   - Single-asset concentration percentage vs 20% institutional ceiling.
   - Setup asymmetry tracking (Average Risk-to-Reward ratio across open setups).
   - Capital Preservation Health Index (0–100 quantitative score).
2. **Interactive Quantitative Position Sizer**:
   - Real-time HTMX calculation (`/trading/calculate-size/`) deriving exact shares from stop-loss distance:
   ```python
   risk_amount = trading_capital * (risk_percentage / 100)
   risk_per_share = entry_price - stop_loss
   quantity = int(risk_amount / risk_per_share)
   ```
   - Features one-click risk preset guardrails (`1.0% Conservative`, `1.5% Standard`, `2.0% Aggressive`, `3.0% Max`).
   - Renders 3-tile precision metrics (Suggested Qty, Capital at Risk, Capital Required) with non-wrapping currency typography (`static/css/risk-management.css`) and dynamic visual Setup Asymmetry (R:R) bar.
   - Automatically checks capital requirements, enforces 20% single-stock concentration ceilings, and validates zero or negative stop-loss distances.
3. **Portfolio Concentration & Exposure Limits**:
   - Live single-stock exposure progress bars with SVG stock logos, clear sector tags, and a physical red 20% SEBI limit ceiling reference marker on each track.
   - Sector allocation breakdown with colorful status chips and 30% concentration alerts.
4. **Active Swing Trades & Stop-Loss Exposure Monitor**:
   - Table tracking all open trades with entry, stop-loss, target, risk per share, total capital at risk, and one-click exit controls.

## Trading journal

Store:

- Entry date.
- Entry price.
- Exit date.
- Exit price.
- Quantity.
- Strategy.
- Entry reason.
- Exit reason.
- Realised P&L.
- Lessons learned.

---

# 16.1 PAPER TRADING VIRTUAL BROKERAGE SANDBOX

A dedicated, institutional-grade simulated brokerage module (`apps/paper_trading/`) allowing traders and investors to paper trade Indian equities in real-time under realistic market conditions without risking real capital.

## Core Architectural Principles

1. **Strict Zero-Contamination Isolation**:
   - The paper trading subsystem is physically decoupled from real user portfolios (`apps/portfolio/`), broker credentials (`apps/brokers/`), and Demat accounts.
   - Virtual transactions never pollute real accounting ledgers, P&L calculations, or tax reports.
   - A dedicated `PaperAccount` is auto-provisioned upon user creation or first terminal visit with a configurable virtual capital balance (default: **₹10,00,000 / ₹10 Lakhs**).
   - "Reset Capital" capability allows users to cleanly purge all virtual positions and orders to start afresh with ₹10 Lakhs.

2. **Realistic Indian Market Simulation**:
   - **Product Types**:
     - `CNC` (Cash & Carry / Delivery): Requires 100% upfront cash balance; held overnight for swing or long-term horizons.
     - `MIS` (Margin Intraday Square-off): Provides 5× intraday leverage (20% margin requirement).
   - **Order Execution Types**:
     - `MARKET`: Instant atomic simulated fill against live LTP with dynamic bid-ask slippage (0.05%–0.10%).
     - `LIMIT`: Stored as `PENDING` on the simulated order book, executing automatically when live market prices cross the limit threshold.
     - `SL-L` / `SL-M`: Stop-loss orders activating when trigger prices are breached.
     - `GTT` (Good-Till-Triggered) Bracket Orders: Automatically attaches protective stop-loss and multi-tier profit target orders.
   - **Indian Statutory Charges & Friction Math (`services/paper_trading/tax_calculator.py`)**:
     - **Brokerage**: Flat ₹20 or 0.03% of turnover (whichever is lower).
     - **Securities Transaction Tax (STT)**: 0.1% on Buy & Sell for `CNC`; 0.025% on Sell only for `MIS`.
     - **Exchange Transaction Charges**: 0.00297% of turnover (NSE standard).
     - **GST**: 18% levied on (Brokerage + Exchange Transaction Charges).
     - **SEBI Turnover Fee**: ₹10 per crore (0.0001% of turnover).
     - **Stamp Duty**: 0.015% on Buy turnover for `CNC`; 0.003% on Buy turnover for `MIS`.

3. **Relational Database Schema (`apps/paper_trading/models.py`)**:
   - **`PaperAccount`**: One-to-one with user, `initial_capital`, `cash_balance`, `margin_utilized`, `realized_pnl`, `is_active`.
   - **`PaperOrder`**: Relates to `PaperAccount` and `ExchangeListing`. Fields: `order_side` (`BUY`/`SELL`), `product_type` (`CNC`/`MIS`), `order_type` (`MARKET`/`LIMIT`/`SL_LIMIT`/`SL_MARKET`), `quantity`, `limit_price`, `trigger_price`, `target_price`, `stop_loss_price`, `status` (`PENDING`/`FILLED`/`CANCELLED`/`REJECTED`), `rejection_reason`.
   - **`PaperPosition`**: Open positions tracking live mark-to-market. Fields: `product_type`, `quantity` (+ Long / - Short), `average_price`, `current_price`, `unrealized_pnl`, `stop_loss`, `target`.
   - **`PaperTrade`**: Historical execution ledger. Fields: `execution_price`, `quantity`, `turnover`, `brokerage`, `taxes_and_charges`, `net_realized_pnl`.

4. **User Interface Architecture**:
   - **Kite-Style Slide-Out Order Drawer (`order_drawer.html`)**:
     - Opened via `"⚡ Paper Trade"` CTA on stock detail pages or global keyboard shortcuts (`B` for Buy / `S` for Sell).
     - Modern color palette: Soft emerald green (`#10b981`) for BUY, soft crimson/rose (`#f43f5e`) for SELL.
     - 1-Click Quant Presets auto-populating Target 1, Target 2, and ATR Stop-Loss from the quantitative technical engine.
     - Real-time client-side calculation of turnover, required margin, and statutory charges before placement.
   - **Paper Trading Terminal (`/papertrading/`)**:
     - Zerodha Kite-style horizontal metrics strip: Total Account Value, Available Cash, Open Floating P&L, Realized Net P&L formatted in Indian Rupees (`indian_inr`).
     - Sub-filter tabs for Orders (`All`, `Pending`, `Executed`).
     - Responsive table architecture with zero horizontal scrollbars.
     - One-click position square-off and pending order cancellation.

5. **AI Behavioral Coach & Discipline Audit (`PaperTradingBehavioralCoach`)**:
   - Continuously audits user execution patterns and computes a Discipline Score (0–100):
     - **Stop-Loss Coverage**: Flags naked/unprotected exposure if trades are placed without stop-loss orders.
     - **Sizing Discipline**: Enforces a strict 20% max equity concentration cap per position.
     - **Overtrading Velocity Alert**: Flags high intraday trade velocity to mitigate commission drag and decision fatigue.
     - **Emotional Impulse Control**: Detects rapid revenge-trading re-entries following losing trades.
   - **Trade Journal Bridge**: 1-click sync allowing traders to export closed paper trades into the permanent `TradeJournal` for post-trade retrospective analysis.

---

# 17. FUTURES AND OPTIONS ARCHITECTURE

Prepare the system for F&O without making it part of the first release.

Future features:

- Futures historical analysis.
- Options chain.
- Open interest.
- Change in OI.
- Volume.
- Implied volatility.
- Put-call ratio.
- Expiry calendar.
- Strike analysis.
- Futures basis.
- Options strategy research.

Important:

- Use appropriate instrument identifiers.
- Respect lot-size and expiry changes.
- Avoid assuming cash-equity indicators apply directly to options.
- Validate data availability and licensing.
- Add F&O backtesting separately.
- Do not implement automated derivatives trading.

---

# 18. AI STOCK ANALYSIS MODULE

Build an AI research service that consumes structured data.

AI must not invent prices, financial values or indicator readings.

## AI roles

### Investor AI

Long-term research:

- Business quality.
- Growth.
- Financial health.
- Valuation.
- Sector position.
- Dividend history.
- Long-term risks.

### Swing Trader AI

Short-term research:

- Trend.
- Momentum.
- Volume.
- Breakout potential.
- Entry conditions.
- Stop-loss.
- Targets.
- Risk/reward.

### Portfolio Risk Manager

Existing holdings:

- Concentration.
- Position size.
- Downside risk.
- Sector exposure.
- Correlation where data permits.
- Hold/add/reduce/exit assessment.

## AI analysis output

Every analysis must contain:

1. Stock and symbol.
2. Timestamp.
3. Data freshness.
4. Analysis horizon.
5. Overall view.
6. Positive factors.
7. Negative factors.
8. Technical analysis.
9. Fundamental analysis.
10. Risk assessment.
11. Existing-holder view.
12. New-investor view.
13. Entry conditions.
14. Invalidation conditions.
15. Confidence level.
16. Data sources and assumptions.

Labels:

- BUY CANDIDATE.
- HOLD.
- WATCH.
- AVOID.
- REDUCE.
- EXIT.

These are research opinions, not guarantees.

Store prompt version, model identifier, input data references and output.

Keep the AI provider configurable (`GeminiAIProvider` with fallback to deterministic quantitative engine).

### Deterministic Quantitative AI Engine (`structured-rules-v2`)

Implemented in `integrations/ai_providers/fallback.py`, this engine synthesizes institutional data into structured analysis without hallucinating:

1. **Investor Persona**:
   - Requires fundamental score $\ge 70$, Piotroski F-Score $\ge 6$, Altman Z-score $\ge 2.0$, and price above 200 SMA to recommend `BUY_CANDIDATE`.
   - **Value Trap Guardrail**: Downgrades to `WATCH` if Piotroski F-score $\le 3$.
   - **Solvency Guardrail**: Downgrades to `AVOID` if Altman Z-score $< 1.81$ (Distress Zone).
2. **Swing Trader Persona**:
   - Validates trend momentum: Requires ADX(14) $\ge 20$, SuperTrend Bullish, and price holding above VWAP.
   - **Volatility-Anchored Bracket Targets**:
     - $\text{Stop-Loss} = \text{LTP} - 1.5 \times \text{ATR}_{14}$ (below recent swing low).
     - $\text{Target 1} = \text{LTP} + 2.0 \times \text{ATR}_{14}$ (1:1.33 R:R).
     - $\text{Target 2} = \text{LTP} + 3.5 \times \text{ATR}_{14}$ (1:2.33 R:R).
3. **Risk Manager Persona**:
   - Enforces a 15% single-stock portfolio concentration cap.
   - Mandates a strict $-8\%$ capital preservation stop-loss threshold.
4. **Mandatory Institutional Disclaimer**:
   - Every brief carries an explicit disclaimer: *"DISCLAIMER: Algorithmic decision-support model outputs are mathematical estimations and do not constitute guaranteed returns or SEBI-registered investment advice. All trading involves capital-at-risk."*

---

# 19. MACHINE LEARNING MODULE

Introduce statistical and machine learning models based on reliable historical daily candlestick repositories.

## Time Series Regime Classifier & Ranker (`regime_v2`)

Implemented in `services/ml/engine.py` under model name `time_series_regime_ranker` (version `v2.0`):

1. **Garman-Klass Extreme-Value Volatility Estimator ($\sigma_{\text{GK}}$)**:
   Overcomes the limitations of close-to-close rolling deviation by utilizing the full OHLC bar (open, high, low, close), providing up to 8× greater statistical efficiency:
   $$\sigma_{\text{GK}}^2 = \frac{1}{N} \sum_{i=1}^N \left[ 0.5 \left(\ln\frac{H_i}{L_i}\right)^2 - (2\ln 2 - 1)\left(\ln\frac{C_i}{O_i}\right)^2 \right]$$
   Annualized volatility: $\sigma_{\text{GK, Ann}} = \sqrt{252 \times \sigma_{\text{GK}}^2}$.

2. **Market Regime Classification**:
   - Evaluates multi-factor signals across trend slope (SMA 20 vs SMA 50 ratio), momentum (RSI 14), Bollinger Bandwidth, and Garman-Klass volatility:
     - `BULLISH_TRENDING`: Strong upward price structure with controlled volatility.
     - `BEARISH_TRENDING`: Downward trend structure below key moving averages.
     - `RANGE_BOUND`: Low directional momentum with price oscilating between support and resistance.
     - `HIGH_VOLATILITY_EXPANSION`: Wide Bollinger Bandwidth combined with high Garman-Klass volatility indicating turbulent distribution.
     - `LOW_VOLATILITY_COMPRESSION`: Severe Bollinger squeeze signaling imminent directional volatility breakout.

3. **Requirements & Validation**:
   - Time-series-aware validation (forward walk, no chronological random shuffling).
   - Zero look-ahead bias and survivorship bias mitigation.
   - Comparison against baseline rule models (naive momentum, random walk).
   - Persists predictions in `MLPrediction` with complete feature contribution breakdowns (`garman_klass_volatility`, `sma_20_50_ratio`, `bollinger_bandwidth`).
- Store model version.
- Store training range.
- Store features.
- Store evaluation metrics.
- Store prediction timestamp.

Never display predictions as guaranteed future prices.

---

# 20. NEWS AND CORPORATE EVENTS

Support:

- Company news.
- Quarterly results.
- Dividends.
- Bonus issues.
- Stock splits.
- Buybacks.
- Board meetings.
- Earnings dates.
- Regulatory announcements.
- Sector news.

Store:

- Headline.
- Source.
- Published time.
- Related stock.
- URL.
- Summary.
- Sentiment, if calculated.

Distinguish published facts from AI-generated summaries.

Respect content licensing and source terms.

---

# 21. ALERTS AND NOTIFICATIONS

## Price alerts

- Price above level.
- Price below level.
- Percentage movement.

## Technical alerts

- RSI threshold.
- MACD crossover.
- Moving average crossover.
- Volume breakout.
- Support/resistance breakout.

## Portfolio alerts

- Stop-loss reached.
- Target reached.
- Portfolio drawdown.
- Concentration threshold.

## System alerts

- Provider unavailable.
- Authentication expired.
- Rate limit.
- Data refresh failed.
- Background task failure.

Channels:

- In-app.
- Email, if configured.
- Additional integrations in future.

Support market-hours-only trading alerts.

Prevent duplicate notifications for unchanged alert conditions.

---

# 22. BACKTESTING MODULE

Support:

- Strategy creation.
- Entry conditions.
- Exit conditions.
- Stop-loss.
- Target.
- Position sizing.
- Brokerage costs.
- Slippage.
- Date range.
- Benchmark comparison.

Metrics:

- Total return.
- CAGR.
- Win rate.
- Average profit.
- Average loss.
- Maximum drawdown.
- Profit factor.
- Trade count.
- Average holding period.
- Equity curve.

Avoid:

- Look-ahead bias.
- Survivorship bias.
- Unrealistic fills.
- Missing transaction costs.
- Incorrect corporate-action treatment.

Clearly show assumptions and limitations.

---

# 23. ZERODHA KITE CONNECT — FUTURE INTEGRATION

Zerodha Kite Connect must be optional.

Do not implement it in the initial release.

Prepare the adapter architecture for future activation.

Potential features:

- Authentication.
- Instrument master.
- Live quotes.
- Historical candles.
- Holdings.
- Positions.

Security:

- Backend-only credentials.
- Environment variable or secure secret storage.
- No tokens in frontend.
- No secrets in logs.
- Expiry handling.
- Authentication error tracking.

Initial application mode must be research-only.

No automatic order placement.

No automatic buying or selling.

No broker order modifications.

Verify current Kite API documentation, availability, pricing, permissions and rate limits before implementation.

---

# 24. REPORTS MODULE

Generate:

- Portfolio reports.
- Holdings analysis.
- Stock research.
- Swing setups.
- Trading journal.
- Backtesting.
- Dividend tracking.
- Watchlist summaries.

Support CSV and PDF exports.

Include:

- Generated timestamp.
- Data source.
- Period.
- Assumptions.

---

# 25. DATABASE ARCHITECTURE

Use PostgreSQL.

Core entities:

```text
User
UserPreference
Instrument
Exchange
Sector
MarketQuote
HistoricalCandle
CorporateAction
FundamentalSnapshot
TechnicalIndicatorSnapshot
Portfolio
Holding
HoldingTransaction
IPOMaster
IPOFundamentals
IPOSubscriptionSnapshot
IPOGMPRecord
IPODocument
IPOApplication
IPOListingPerformance
Watchlist
WatchlistItem
Trade
TradeJournal
ScreenerConfiguration
ScreenerResult
AIAnalysis
MLModel
MLPrediction
NewsArticle
CorporateEvent
Alert
Notification
BrokerConnection
DataProvider
DataRefreshLog
DataQualityIssue
Backtest
BacktestTrade
Report
```

Requirements:

- Foreign keys.
- Appropriate indexes.
- Unique constraints.
- DecimalField for financial values.
- UTC timestamps.
- Transaction history preservation.
- Database migrations.
- Efficient bulk operations.

Do not delete historical transactions when shares are sold.

---

# 26. BACKGROUND PROCESSING

Use Celery + Redis.

Background tasks:

- Historical data import.
- Daily market refresh.
- Quote refresh.
- Technical indicator calculation.
- Fundamental refresh.
- IPO catalog and upcoming pipeline synchronization (`sync_ipos_markets_task`).
- Live IPO subscription snapshot polling during bidding hours (10:00 – 17:00 IST).
- Post-listing market price and CMP synchronization.
- IPO milestone and schedule alert triggers.
- Screener execution.
- AI analysis.
- News collection.
- Alert evaluation.
- Report generation.
- Backtesting.

Tasks must:

- Use structured logging.
- Handle errors.
- Retry appropriately.
- Prevent duplicate processing.
- Record execution status.
- Be idempotent where possible.

Do not block normal page requests with long-running tasks.

---

# 27. API ARCHITECTURE

Use Django REST Framework.

Suggested endpoints:

```text
/api/v1/market/
/api/v1/instruments/
/api/v1/stocks/
/api/v1/ipo/
/api/v1/portfolio/
/api/v1/holdings/
/api/v1/watchlists/
/api/v1/screener/
/api/v1/analysis/
/api/v1/alerts/
/api/v1/backtesting/
/api/v1/brokers/
```

Requirements:

- Authentication.
- Permissions.
- Input validation.
- Pagination.
- Filtering.
- Consistent response format.
- Rate limiting.
- API documentation.

---

# 28. SECURITY

Implement:

- Django authentication.
- CSRF protection.
- Secure sessions.
- Permission checks.
- Input validation.
- SQL injection protection.
- XSS protection.
- Secure secret management.
- Environment-specific settings.
- Audit logs for sensitive actions.

Never expose credentials, API tokens or passwords in frontend code, logs or source control.

Do not use DEBUG=True in production.

---

# 29. TESTING

## Unit tests

- Indicator calculations.
- Portfolio calculations.
- Average price.
- P&L.
- Risk sizing.
- Screener conditions.
- Provider normalisation.
- Data validation.
- IPO lifecycle transitions and milestone calculation.
- IPO subscription snapshot and velocity calculations.
- IPO financial ratio and valuation metrics.
- IPO 7-factor quantitative scoring engine.
- IPO bid planner lot limits and blocked funds.
- Retail allotment probability mathematical bounds.
- IPO issues list pagination slicing and query preservation.

## Integration tests

- Database operations.
- Jugaad adapter.
- Yahoo adapter.
- `ipos.markets` REST API client and sync service.
- Future Kite adapter.
- Celery tasks.
- HTMX navigation.
- API permissions.

## UI tests

- Sidebar navigation.
- Persistent header.
- Module loading.
- Browser back/forward.
- Direct URLs.
- Responsive layouts.
- Loading and error states.
- TradingView Lightweight Charts initialization and cleanup.
- Apache ECharts initialization and cleanup.

Use mocked provider responses in automated tests.

Tests must not depend on live market availability.

---

# 30. LOGGING AND MONITORING

Track:

- Application errors.
- Provider failures.
- Data refresh failures.
- Broker connectivity.
- Background task failures.
- AI provider errors.
- Slow requests.
- Data freshness.
- IPO sync health and stale prospectus alerts.

Create an administrative data-source health view.

Do not log secrets.

---

# 31. ENVIRONMENT CONFIGURATION

Example `.env.example`:

```dotenv
DJANGO_SECRET_KEY=replace_me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgresql://user:password@localhost:5432/stock_intelligence

REDIS_URL=redis://localhost:6379/0

# Secondary market data
ENABLE_JUGAAD_DATA=True
ENABLE_YAHOO_FINANCE=True
MARKET_DATA_PROVIDER_PRIORITY=jugaad,yahoo

# Primary market (IPO) data
ENABLE_IPOS_MARKETS=True
IPOS_MARKETS_BASE_URL=https://ipos.markets

# Future broker integration
ENABLE_ZERODHA=False
ZERODHA_API_KEY=
ZERODHA_API_SECRET=

# AI integration
AI_PROVIDER=
AI_API_KEY=

# Data configuration
MARKET_DATA_CACHE_TTL=60
HISTORICAL_DATA_CACHE_TTL=86400
IPO_DATA_CACHE_TTL=300
```

Do not commit the actual `.env` file.

Provide setup instructions for macOS and Linux.

---

# 32. IMPLEMENTATION ROADMAP

## Phase 1 — Django foundation

- Project setup.
- PostgreSQL.
- Environment settings.
- Common base template.
- Sidebar.
- Header.
- HTMX navigation.
- Authentication.
- Shared components.

Acceptance:
The application starts and navigation works without reloading the common shell.

## Phase 2 — Market data providers

- Jugaad-Data adapter.
- Yahoo Finance adapter.
- Provider abstraction.
- Data normalisation.
- Historical data storage.
- Provider health.
- Data quality checks.
- Data-source settings page.

Acceptance:
Historical NSE stock data can be imported and viewed, with source and freshness recorded.

## Phase 3 — Stock research & Chart UI

- Instrument master.
- Stock search.
- Stock detail.
- TradingView Lightweight Charts integration for price and volume.
- Technical indicators and signal overlays.
- Fundamental data model.
- Sector analysis.
- CoolAdmin-inspired typography system with tabular numerals.

Acceptance:
A user can search a stock and inspect available historical, technical and fundamental information with interactive Lightweight Charts.

## Phase 4 — Portfolio

- Manual portfolio creation.
- Transactions.
- Holdings.
- Average price.
- P&L.
- Portfolio analytics (Apache ECharts donut & exposure widgets).
- Existing-holder recommendations.

Acceptance:
Portfolio calculations are accurate and transaction history is preserved.

## Phase 4B — Primary Market & IPO Intelligence Centre

- Canonical IPO Master data model and lifecycle transitions.
- `ipos.markets` REST ingestion and official exchange adapters.
- Primary Issues Desk with server-side pagination, search, segment and tab filters.
- Live subscription velocity tracking and category breakdowns.
- Fundamental financial research and peer valuation engine.
- 7-factor quantitative scoring and multi-horizon recommendation engine.
- Interactive bid planner and lottery-based retail allotment probability engine.
- Personal application journal with one-click portfolio conversion.
- Post-listing performance tracking and TradingView chart integration.
- Executive dashboard with CoolAdmin typography and Apache ECharts widgets.

Acceptance:
Users can inspect upcoming/live/closed IPOs, calculate bid capital, estimate allotment odds, review quantitative scores, and track post-listing gains.

## Phase 5 — Screener and watchlists

- Custom screening with multi-factor technical, fundamental, and market criteria.
- One-Click Strategy Presets:
  - Deep Value (`preset=value`)
  - High Quality Moats (`preset=quality`)
  - High Growth (`preset=growth`)
  - Bullish Momentum (`preset=momentum`)
  - Oversold Pullback (`preset=oversold_swing`)
  - Bluechip Large Cap Leaders (`preset=large_cap_leaders`)
  - High Dividend Yield (`preset=dividend` - Dividend Yield ≥ 2.0%, Debt/Equity ≤ 1.2, Quality Score ≥ 50)
- Parameter filter builder with Dividend Yield (`min_dividend_yield`), P/E, ROE, ROCE, Sales Growth, D/E, RSI, MAs.
- Saved filters and export to CSV.
- Watchlists and quick stock monitoring.

Acceptance:
Users can create, run, export, and save custom screeners and watchlists with one-click presets.

## Phase 6 — Swing trading

- Swing scanner.
- Setup generation.
- Risk calculations.
- Position sizing.
- Trade journal.

Acceptance:
Every trade setup includes entry, stop-loss, targets and risk/reward.

## Phase 7 — AI research

- AI provider abstraction.
- Investor AI.
- Swing Trader AI.
- Portfolio Risk Manager.
- Stored analysis.
- Source references.

Acceptance:
AI analysis uses actual structured data and identifies missing information.

## Phase 8 — News and alerts

- News.
- Corporate events.
- Price alerts.
- Technical alerts.
- Portfolio alerts.
- Notifications.

Acceptance:
Alerts execute reliably and avoid duplicate notifications.

## Phase 9 — Backtesting and ML

- Strategy engine.
- Backtesting.
- Performance metrics.
- ML experiments.

Acceptance:
Historical strategies can be tested with transaction costs and without look-ahead leakage.

## Phase 10 — F&O and Kite integration

- F&O instrument support.
- Options data model.
- Options research.
- Zerodha Kite adapter.
- Broker authentication.
- Read-only broker sync.

Acceptance:
Optional integrations work without making the application dependent on them.

## Phase 11 — Production readiness

- Security review.
- Performance optimisation.
- Test coverage.
- Documentation.
- Backups.
- Deployment.

---

# 33. CRITICAL BUSINESS RULES

1. Existing holdings must always be considered in stock analysis.
2. Existing-holder and new-investor recommendations must be separate.
3. Never recommend averaging down without a fresh assessment.
4. Never fabricate market data.
5. Every analysis must show its data timestamp.
6. Clearly distinguish live, delayed, cached and historical data.
7. Every trade setup must include risk and invalidation conditions.
8. AI predictions must never be presented as guarantees.
9. Do not automatically execute broker orders.
10. Preserve historical portfolio transactions.
11. Do not silently ignore missing data.
12. Keep provider integrations separate from business logic.
13. The application must work without Zerodha.
14. Keep AI and data providers replaceable.
15. Do not implement all phases simultaneously.
16. Never fabricate IPO data or dates. All issue dates, price bands, lot sizes, and issue sizes must come from verified sources (`ipos.markets`, NSE/BSE, SEBI).
17. Grey Market Premium (GMP) is strictly unofficial and unregulated. It must never be presented as an official indicator or guaranteed price discovery and must remain toggleable.
18. Never guarantee IPO allotment or promise listing gains. Transparently state the lottery basis for oversubscribed retail applications.
19. Financial numbers must always use tabular figures (`tabular-nums`) and standard Indian numbering (`₹... Cr` formatted with `intcomma_inr`).
20. Dual charting separation is strict: TradingView Lightweight Charts for stock/IPO price history; Apache ECharts for dashboard analytics. Never use commercial/paid alternatives or duplicate the candlestick engine.

---

# 34. GOOGLE ANTIGRAVITY IMPLEMENTATION INSTRUCTIONS

Act as a senior software architect and experienced Django developer.

Treat this document as the single source of truth for project architecture and functionality.

## Before coding

1. Inspect the existing repository.
2. Identify the current framework and files.
3. Identify existing functionality.
4. Identify reusable code.
5. Identify security and architecture issues.
6. Compare the repository with this specification.
7. Prepare an implementation plan.
8. Create or update `IMPLEMENTATION_STATUS.md`.
9. Identify files and apps to create or modify.
10. Explain the proposed changes before major implementation.

Do not blindly overwrite existing working code.

## Coding rules

- Use separate Django apps for business functionality.
- Use one common HTML shell.
- Keep sidebar and header persistent.
- Load modules dynamically in the content area.
- Use HTMX with full-page fallback.
- Put business logic in services.
- Put provider logic in adapters.
- Use PostgreSQL.
- Use Celery for background jobs.
- Write tests.
- Protect credentials.
- Avoid unnecessary complexity.
- Do not use fake market data in production functionality.
- Do not claim incomplete features are completed.

## Provider implementation rules

Implement Jugaad-Data and Yahoo Finance first.

Do not implement Zerodha Kite yet.

Build the common provider abstraction so Kite can be introduced later without changing the stock analysis, portfolio, technical analysis or screener modules.

Use mocked provider data for automated tests.

Do not make tests depend on live NSE or Yahoo availability.

## Implementation workflow

Work one phase at a time.

For each phase:

1. Explain the changes.
2. Implement the feature.
3. Run migrations.
4. Run tests.
5. Fix errors.
6. Update documentation.
7. Update `IMPLEMENTATION_STATUS.md`.
8. Summarise completion and remaining work.

Do not proceed with destructive changes without approval.

## Required documentation

Maintain:

- README.md
- MASTER_SPECIFICATION_DJANGO.md
- IMPLEMENTATION_STATUS.md
- ARCHITECTURE.md
- DATA_SOURCES.md
- API_DOCUMENTATION.md
- DEPLOYMENT.md
- SECURITY.md

---

# 35. DEFINITION OF DONE

The initial usable application must have:

- Working Django project.
- PostgreSQL integration.
- Authentication.
- Persistent sidebar.
- Persistent header.
- Dynamic module navigation.
- Browser history support.
- Jugaad-Data integration.
- Yahoo Finance integration.
- Primary Market / IPO Intelligence Centre (`ipos.markets` + NSE/BSE feeds, canonical lifecycle, subscription analytics, valuation engine, quantitative scoring, bid planner, allotment tracker, post-listing performance).
- Primary Issues Desk with server-side pagination, search, and segment filtering.
- TradingView Lightweight Charts integration for stock price and technical charts.
- Apache ECharts integration for dashboard analytics and radar visualizations.
- CoolAdmin-inspired typography system with Inter font, strict hierarchy, and tabular numerals.
- Common market data service.
- Historical data storage.
- Data validation.
- Provider health tracking.
- Stock search.
- Historical charts.
- Technical indicators.
- Manual portfolio management.
- Accurate holdings calculations.
- Separate existing-holder and new-investor analysis.
- Watchlists.
- Swing trading scanner.
- Risk management.
- AI research integration.
- Background jobs.
- Logs.
- Automated tests.
- Security controls.
- Documentation.

---

# 36. FINAL ARCHITECTURAL DIRECTION

Build a dependable Django modular monolith.

Initial data providers:
- Jugaad-Data: primary Indian NSE data provider where supported.
- Yahoo Finance: secondary historical data provider.
- `ipos.markets`: primary Indian IPO intelligence data provider.

Future provider:
- Zerodha Kite Connect: optional broker and market data integration.

Prioritise:

1. Reliable data.
2. Correct portfolio calculations.
3. Clear data-source tracking.
4. Accurate technical analysis.
5. Portfolio-aware recommendations.
6. Maintainable Django architecture.
7. Consistent user experience.
8. AI and ML after the foundation is reliable.

Do not overengineer the initial release.

The first objective is a working, trustworthy stock research platform. Advanced AI, ML, F&O and broker integration should be added incrementally.

**END OF MASTER SPECIFICATION**