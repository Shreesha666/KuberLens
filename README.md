# KuberLens — Indian Stock Market Research & Intelligence Platform

[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.1-success.svg)](https://www.djangoproject.com/)
[![HTMX](https://img.shields.io/badge/UI-HTMX%20%2B%20Bootstrap%205-purple.svg)](https://htmx.org/)
[![Tests](https://img.shields.io/badge/Tests-226%20Passed%20(100%25)-brightgreen.svg)](tests/)
[![Code Style](https://img.shields.io/badge/Linter-Ruff%20Clean-black.svg)](https://github.com/astral-sh/ruff)
[![Architecture](https://img.shields.io/badge/Architecture-Django%20Modular%20Monolith-orange.svg)](ARCHITECTURE.md)

An institutional-grade personal stock market research, technical analysis, portfolio intelligence, quantitative swing trading, and decision-support platform engineered specifically for the Indian equity markets (**National Stock Exchange (NSE)** and **Bombay Stock Exchange (BSE)**).

---

## Table of Contents

1. [Architecture & Design Principles](#1-architecture--design-principles)
2. [Key Capabilities & Modules](#2-key-capabilities--modules)
3. [Company Logo Integration (api.dharun.dev)](#3-company-logo-integration-apidharundev)
4. [Dual-Perspective Recommendation Framework](#4-dual-perspective-recommendation-framework)
5. [Interactive HTML5 Canvas Charting](#5-interactive-html5-canvas-charting)
6. [Technology Stack](#6-technology-stack)
7. [Environment Variables & Configuration](#7-environment-variables--configuration)
8. [Local Development Quickstart](#8-local-development-quickstart)
9. [Platform Navigation & URL Directory](#9-platform-navigation--url-directory)
10. [Automated Testing & Code Quality](#10-automated-testing--code-quality)
11. [Operations, Backup & Docker Runbook](#11-operations-backup--docker-runbook)

---

## 1. Architecture & Design Principles

The platform is designed as a **Django Modular Monolith** adhering to clean domain-driven architecture and strict separation of concerns:

- **Presentation Layer (Dynamic UI Shell):** Built with `django-htmx` and Bootstrap 5. Provides single-page application (SPA) responsiveness through dynamic partial swapping (`#main-content`) with browser URL push, back/forward history restoration (`htmx:historyRestore`), and full fallback HTML rendering on direct page loads and refreshes.
- **Canonical Asset Separation:** Canonical company/asset identity (`Instrument` uniquely identified by international ISIN) is strictly decoupled from exchange trading symbols (`ExchangeListing` for NSE and BSE).
- **Immutable Financial Ledger:** Portfolio accounting operates on an append-only transaction ledger (`HoldingTransaction`). Current holding states and lots are deterministically derived via pure FIFO accounting.
- **Pure Service Layers:** Domain calculations (FIFO lot matching, technical indicators, fundamental health scores, ATR risk parameters, regime classifiers) live in isolated service layers under `services/`, free of view logic and HTTP side-effects.
- **Credential Protection at Rest:** Symmetric authenticated encryption (**Fernet / AES-128-CBC + HMAC-SHA256**) for all external broker secrets and access tokens.
- **2D Market Data State Machine:** Quotes maintain distinct state representations (live trading session snapshot vs. official exchange Bhavcopy End-of-Day settlement).

---

## 2. Key Capabilities & Modules

### 📈 Market Overview & Intelligence Dashboard
- Real-time market indices ticker (**NIFTY 50**, **SENSEX**, **NIFTY BANK**) with intraday change and percentage drift.
- Market breadth metrics (advance/decline ratios, 52-week highs/lows distribution).
- Active trading session detection backed by an Indian exchange holiday calendar (accounting for Muhurat trading, national holidays, and weekend closures).

### 🔍 Stock Research & Institutional Profiles
- **Global Instant Autocomplete:** Fast header search supporting NSE/BSE ticker symbols, company legal names, display names, and ISIN numbers.
- **Interactive Candlestick & Volume Chart:** High-performance HTML5 canvas chart with SMA 20/50 overlays, volume bars, hover crosshairs, and tactical level projection rays.
- **Technical Indicator Engine:** Wilder's RSI (14), MACD (12, 26, 9), Bollinger Bands (20, 2σ), Average True Range (ATR 14), Stochastic RSI, Moving Averages (SMA 20/50/100/200, EMA 9/20/50), and On-Balance Volume (OBV).
- **Fundamental Health Scoring:** 5-factor composite fundamental framework evaluating Profitability, Balance Sheet Solvency, Valuation vs. Sector Median, Growth, and Shareholding Quality.

### 💼 Portfolio Intelligence & FIFO Accounting
- **Automated FIFO Lot Matching:** Deterministic allocation of sell orders against earliest active buy lots.
- **Capital Charge Capitalization:** Buy brokerages, STT, and exchange turnover charges are capitalized into lot acquisition costs; sell charges reduce net realized capital gains.
- **Corporate Action Redistribution:** Non-dilutive adjustments for bonus issues, stock splits, and cash dividends across open historical lots without ledger corruption.
- **Concentration & Risk Guardrails:** Real-time portfolio concentration tracking with automatic alerts when any single equity exposure exceeds safe allocation thresholds.

### 🚀 Primary Market & IPO Intelligence Suite
- **Canonical Lifecycle & Issues Desk:** Live tracking across Mainboard and SME exchanges through DRHP Filed, SEBI Approved, Live, Closed, Allotted, and Listed stages, with server-side pagination.
- **Empirical Listing Gain & Pop Predictor:** Multi-factor forecast combining Grey Market Premium (GMP ~50%), Day-3 QIB subscription (~30%), and fundamental scoring (~20%) to project expected listing price ranges and actionable recommendations (`Strong Apply`, `Retail Lottery`, `Apply with Caution`, `Avoid`).
- **Interactive Bid Planner & DRHP Simulation Mode:** Dynamic lot sizing, category limit enforcement (Retail ₹2L cutoff, sHNI, bHNI), UPI mandate vs. ASBA NetBanking routing, and interactive estimation modeling for pre-RHP pipeline issues.
- **Mathematical SEBI Retail Lottery Calculator:** Models mathematical allotment odds ($1 - (1 - 1/S)^k$) across distinct family member Demat/PAN accounts.
- **Central Family Demat & PAN Vault (`/ipo/family-vault/`):** Centrally manage profiles for Self, Spouse, Parents, Siblings, and HUF with masked PANs and Demat BOIDs, featuring **1-Click Batch Bidding** in the Bid Planner.
- **Automated Multi-Registrar Allotment Verifier:** Integrated adapters for **Link Intime, KFintech, and Bigshare** to check allotment outcomes directly from the Application Tracker.
- **IPO Strategy Backtest Workspace (`/ipo/backtest/`):** Test quantitative investment hypotheses against historical Indian IPO debuts, computing win rates, average debut returns, and simulated ₹1 Lakh portfolio growth.
- **1-Click Portfolio Sync:** Automatically convert allotted IPO application shares into active Portfolio Holdings with full FIFO transaction audit preservation.
- **Multi-IPO Comparison Matrix (`/ipo/compare/`):** Side-by-side comparison of 2 to 4 IPOs across valuation multiples, 3-year CAGR growth, balance sheet health, and subscription velocity.

### 🎯 Quantitative Swing Trading & Risk Hub
- **4 Quantitative Setup Scanners:**
  1. *SMA Pullback in Trend:* Bullish trending stocks retracing to key moving averages with declining volume.
  2. *Oversold Mean-Reversion:* Strong fundamental equities with RSI < 35 testing lower Bollinger bands.
  3. *Volatility Breakout Expansion:* Consolidation squeezes expanding with surging volume.
  4. *Volume Climax Absorption:* High-volume institutional accumulation wicks at support.
- **Mathematical Position Sizer:** Calculates exact share quantities based on maximum percentage account risk, entry price, and Chandelier volatility stop loss.
- **SEBI-Aligned Trade Journal:** Mandatory pre-trade psychology checklist, execution trade log, planned vs. actual R-multiples, and post-trade emotional discipline reviews.

### 🤖 Machine Learning & Market Regime Engine
- Time-series statistical regime classifier: categorizes market environments into **Trending Expansion (Bullish Drift)**, **Range-Bound (Mean Reversion)**, or **High Volatility (Turbulent Expansion)**.
- ML ranking engine predicting short-term directional probabilities from multi-factor feature contributions with zero chronological look-ahead bias.

### 📊 Strategy Backtesting Engine
- Chronological event-driven simulation with realistic Indian market constraints.
- Integrated slippage modeling (10 bps) and statutory Indian transaction taxes (STT, GST, SEBI turnover fees).
- Visual equity curves and institutional performance KPIs: CAGR, Sharpe Ratio, Maximum Drawdown, Win Rate, and Profit Factor.

### 🔗 Broker Integration & F&O Derivatives Master
- Read-only **Zerodha Kite Connect v3** API adapter for automated portfolio holdings synchronization.
- Fernet-encrypted token and API key storage with manual disconnect controls.
- Derivative contracts master tracking active NSE futures and options series.

### 🔔 News, Alerts & Report Generation
- Multi-variable threshold alerts (price crossovers, RSI oversold/overbought, portfolio stop-loss breaches) with cooldown deduplication.
- In-app notification center with dynamic unread indicator.
- Institutional report generation: printable PDF/HTML tear-sheets and CSV ledger exports.

---

## 3. Company Logo Subsystem & Offline Vector Persistence

The platform implements an institutional-grade, **Local-Disk-First** vector brand logo subsystem (`services/logos/service.py`) and internal streaming proxy (`/stocks/<symbol>/logo/`). It guarantees **< 1ms response times**, zero external network delays, zero memory footprint, and 100% offline resilience across all Indian equities on NSE and BSE.

### Architecture & Service Design
- **Local-Disk-First Lookups:** Logos are permanently stored as vector SVGs in `static/branding/stock_logos/{SYMBOL}.svg`. If the file exists on disk, it is served directly in sub-millisecond time with **0 MB RAM usage**.
- **ISIN & Multi-CDN Resolution:**
  - **Shareperks ISIN CDN (`company-logo.shareperks.in`):** Primary production vector CDN co-engineered by Dharun Ashokkumar and Shareperks, resolving logos by unique ISIN (`https://company-logo.shareperks.in/logo/{isin}/icon.svg`).
  - **GitHub / jsDelivr CDNs (`dharunashokkumar/indian-listed-company-logos`):** Serves exact NSE and BSE vector SVGs (`data/logos/nse/NSE_{symbol}.svg`).
  - **Cross-Exchange Sibling Resolution:** Automatically maps BSE numeric scrip codes (e.g. `500112`) to their NSE listing (`SBIN`) to guarantee official vector downloads across exchanges.
  - **Legacy API Gateway Fallback:** In the event that `api.dharun.dev` encounters Cloudflare 530 origin downtime, the service automatically and seamlessly falls back to Shareperks and GitHub CDNs.
- **On-Demand Write-Through Disk Cache:** If an un-cached stock is queried, the system attempts a fast CDN lookup. Upon success, the SVG is written directly to disk so future requests never hit the network.
- **Deterministic SVG Monogram Fallbacks:** For obscure SME or micro-cap listings lacking an official logo, the service automatically generates a crisp, high-DPI SVG monogram badge (using the symbol's initials and a deterministic brand color palette) and saves it to disk. **Broken images and blank placeholders are 100% eliminated.**
- **Batch Synchronization CLI Command:**
  Pre-download official vector logos and pre-generate monograms for your entire active stock universe in one shot:
  ```bash
  # Synchronize all active stock listings in parallel (16 threads)
  python manage.py sync_stock_logos --concurrency 16

  # Force re-download and overwrite existing files
  python manage.py sync_stock_logos --force

  # Download specific tickers
  python manage.py sync_stock_logos --symbols RELIANCE,TCS,INFY,HDFCBANK
  ```
  *Active Database Universe vs Total Market Universe:* The command operates on all distinct symbols currently stored in `ExchangeListing`. The seeded database contains **284 benchmark listings** (Nifty 50, Nifty Next 50, Nifty Midcap 150 benchmark listings, IPO radar, and tracked equities). Whenever additional stocks from the broader ~2,700 NSE or ~5,700 BSE universe are added to the database, running this command syncs their logos instantly.
  *Footprint:* **~365 KB for 284 benchmark stocks** (< 0.4 MB total disk space). Even for the full universe of 8,000+ NSE/BSE stocks, total disk storage remains capped at ~20 MB with zero impact on RAM.

- **Template Tag Helper:**
  Any Django template can render a responsive, self-healing logo using the `stock_logo` tag:
  ```html
  {% load core_tags %}

  <!-- Standard 36px brand logo -->
  {% stock_logo listing size=36 css_class="rounded-2 shadow-xs" %}

  <!-- Large 52px profile header logo -->
  {% stock_logo listing size=52 css_class="rounded-3 border" %}
  ```

---

## 4. Dual-Perspective Recommendation Framework

Standard financial platforms offer a single static "Buy/Sell" rating that misleads investors depending on their current exposure. This platform implements a **Dual-Perspective Recommendation Engine** (`services/recommendations/evaluator.py`) evaluating two independent operational strategies:

```
                      ┌────────────────────────────────────────┐
                      │        Institutional Analysis          │
                      │  Technical + Fundamental + Confluence  │
                      └───────────────────┬────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
   ┌─────────────────────────────┐                 ┌─────────────────────────────┐
   │  Existing Holder Strategy   │                 │  New Prospective Investor   │
   ├─────────────────────────────┤                 ├─────────────────────────────┤
   │ • Capital Preservation      │                 │ • Tactical Entry Price Zone │
   │ • Partial Profit Trimming   │                 │ • Chandelier ATR Stop Loss  │
   │ • Trailing Stop Adjustment  │                 │ • Structural Targets (T1/T2)│
   │ • Anti-Averaging Down Guard │                 │ • Minimum 2.0x Risk/Reward  │
   │ • Dividend Yield Strategy   │                 │ • Confluence Score (0-100%) │
   └─────────────────────────────┘                 └─────────────────────────────┘
```

### 1. Existing Holder Strategy (Portfolio Preservation)
- **Trim & Take Partial Profits:** Triggers when an equity reaches extreme overbought levels (RSI > 75 or price > 20% above SMA 50) or achieves a massive unrealized gain, advising the investor to de-risk.
- **Capital Preservation / Exit:** Identifies structural breakdowns below key multi-week moving averages (SMA 50 / SMA 200).
- **Anti-Averaging-Down Safeguard:** Strictly forbids adding capital to a declining position if fundamental health scores (solvency, ROCE, margins) are deteriorating.

### 2. New Prospective Investor (Quantitative Entry Criteria)
- **4-Pillar Confluence Scoring (0–100%):** Synthesizes Technical Trend (30%), Fundamental Health (25%), Volatility/ATR Value (25%), and Market Regime Alignment (20%).
- **Volatility-Adjusted Chandelier Stop Loss:** Calculated dynamically as $\text{Stop Loss} = \text{Structural Support} - (1.5 \times \text{ATR}_{14})$.
- **Measured Structural Targets:**
  - **Target 1 ($T_1$):** Nearest overhead swing resistance or $\text{Entry} + (1.5 \times \text{Risk})$.
  - **Target 2 ($T_2$):** Fibonacci / expansion target or $\text{Entry} + (2.5 \times \text{Risk})$.
- **Risk-to-Reward Filter:** Prospective BUY ratings require a minimum Risk-to-Reward ratio of **2.0:1**.

---

## 5. Interactive HTML5 Canvas Charting

The interactive price chart (`static/js/charting.js`) is an institutional-grade, zero-dependency HTML5 Canvas charting engine designed for speed and clarity:

- **Zero External Dependencies:** 100% pure client-side canvas implementation (no heavy charting bundles or CDN scripts).
- **Dual Overlays:** Smoothly renders SMA 20 (Royal Blue) and SMA 50 (Amber) alongside daily OHLC candlesticks.
- **Proportional Volume Histogram:** Semi-transparent green/red volume bars rendered below price action.
- **Tactical Level Projection Rays:** Institutional trade levels (Stop Loss in Red, Target 1 in Emerald, Target 2 in Teal) render as **forward-looking projection rays** originating from the recent trading cycle (~25 sessions) towards the right price axis with anchor origin points.
- **Collision-Free Price Axis:** Dynamic collision detection suppresses standard Y-axis grid numbers when an active Stop Loss or Target pill badge occupies the same vertical pixel space.
- **Interactive Tooltip Crosshair:** Mousemove crosshair displaying exact date, Open, High, Low, and Close figures in a crisp floating pill.

---

## 6. Technology Stack

| Layer | Component / Tool | Purpose |
|---|---|---|
| **Language** | Python 3.12 / 3.13 | High-performance modern Python runtime |
| **Framework** | Django 5.1 (Modular Monolith) | Robust web foundation, ORM, and auth |
| **Front-End** | Bootstrap 5 + HTMX (`django-htmx`) | Reactive, dynamic SPA-like UI without Node.js |
| **Charting** | HTML5 2D Canvas Engine | Custom zero-dependency financial candlestick charts |
| **Database** | PostgreSQL 16+ (or SQLite for dev) | ACID-compliant relational data and JSONB |
| **Task Queue** | Celery 5.4 + Redis 7 | Asynchronous data ingestion and calculations |
| **Market Data** | Jugaad-Data & Yahoo Finance | NSE Bhavcopy and historical candle feeds |
| **Logo Provider** | `api.dharun.dev` | Official vector Indian equity brand logos |
| **Security** | Fernet (Cryptography) | AES-128-CBC + HMAC credential encryption |
| **Code Quality** | Pytest, Pytest-Django, Ruff | 183 automated tests, 100% pass, strict linting |

---

## 7. Environment Variables & Configuration

Create a `.env` file in the project root based on `.env.example`:

```env
# Django Core
DJANGO_SECRET_KEY=your_secure_random_key_here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database (PostgreSQL recommended; SQLite fallback if not set)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/stock_intelligence

# Redis & Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Field Encryption Key (Fernet 32-byte base64 key for broker secrets)
FIELD_ENCRYPTION_KEY=YD6S9lYBUKY0Lvb-7nPCU5alx8INSUhwX3NjuSlaYX0=

# Market Data Providers
ENABLE_JUGAAD_DATA=True
ENABLE_YAHOO_FINANCE=True
MARKET_DATA_PROVIDER_PRIORITY=jugaad,yahoo

# Company Logo API (api.dharun.dev)
DHARUN_LOGO_API_URL=https://api.dharun.dev/v1/logos
DHARUN_API_KEY=your_dharun_api_key_here

# AI Research Provider (Optional: "gemini" or "fallback")
AI_PROVIDER=fallback
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```

---

## 8. Local Development Quickstart

### 1. Clone & Set Up Virtual Environment
```bash
git clone <repository_url>
cd stockmarket_analytics_django

python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements/local.txt
```

### 3. Run Database Migrations
```bash
python manage.py migrate
```

### 4. Create Development Administrator
```bash
python manage.py create_dev_user
```
*Default Credentials:*
- **Username:** `admin`
- **Password:** `Admin@12345`

### 5. Seed Demonstration & Market Universe Data
Run the following idempotent management commands in order:
```bash
# 1. Seed benchmark exchanges and top equity listings
python manage.py seed_instruments

# 2. Seed NIFTY Large & Midcap 250 universe (268 equity listings across all sectors)
python manage.py seed_nifty250

# 3. Seed historical candles, technical indicators, and fundamental snapshots
python manage.py seed_stock_research

# 4. Seed demo portfolio with FIFO multi-lot buys, partial sales, dividends, and cash balances
python manage.py seed_portfolio

# 5. Seed stock screener presets and default watchlists
python manage.py seed_screener_and_watchlists

# 6. Seed financial news articles and corporate actions calendar (splits, dividends, bonus)
python manage.py seed_news_and_events
```

### 6. (Optional) Run Celery Background Workers
```bash
# Terminal 2: Run Celery Worker
celery -A config worker --loglevel=info

# Terminal 3: Run Celery Beat (Periodic Market Data Ingestion)
celery -A config beat --loglevel=info
```

### 7. Start the Development Server
```bash
python manage.py runserver 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 9. Platform Navigation & URL Directory

| Module | URL | Description |
|---|---|---|
| **Executive Dashboard** | [`/`](http://localhost:8000/) | Live indices ticker, portfolio summary, regime distribution |
| **Stock Directory** | [`/stocks/`](http://localhost:8000/stocks/) | Searchable Indian equities directory with live quotes and logos |
| **Stock Profile** | [`/stocks/<symbol>/`](http://localhost:8000/stocks/RELIANCE/) | Full institutional research, canvas chart, dual recommendations |
| **Technical Analysis Hub** | [`/research/technical/`](http://localhost:8000/research/technical/) | Indicator snapshots, RSI oversold/overbought, moving average crosses |
| **Fundamental Analysis Hub**| [`/research/fundamental/`](http://localhost:8000/research/fundamental/) | Valuation multiples, ROCE/ROE rankings, financial health scores |
| **IPO Intelligence Centre** | [`/ipo/`](http://localhost:8000/ipo/) | Executive primary market dashboard, capital mobilization, sync |
| **Primary Issues Desk** | [`/ipo/issues/`](http://localhost:8000/ipo/issues/) | Mainboard & SME IPO directory with server-side pagination |
| **IPO Detail Profile** | [`/ipo/<symbol>/`](http://localhost:8000/ipo/NTPCGREEN/) | Complete RHP research, 5-pillar radar scores, GMP, and timeline stepper |
| **Interactive Bid Planner** | [`/ipo/<symbol>/bid-planner/`](http://localhost:8000/ipo/NTPCGREEN/bid-planner/) | Lot sizing calculator, SEBI lottery odds, simulation mode |
| **Family Demat Vault** | [`/ipo/family-vault/`](http://localhost:8000/ipo/family-vault/) | Central family PAN/BOID management with 1-click batch bidding |
| **IPO Strategy Backtester** | [`/ipo/backtest/`](http://localhost:8000/ipo/backtest/) | Quantitative IPO debut simulator (GMP, QIB %, ₹1L compounding) |
| **My IPO Applications** | [`/ipo/applications/`](http://localhost:8000/ipo/applications/) | Bid mandate tracker, registrar allotment verification, portfolio sync |
| **IPO Calendar** | [`/ipo/calendar/`](http://localhost:8000/ipo/calendar/) | Chronological monthly calendar of opens, closes, and listings |
| **Multi-IPO Comparison** | [`/ipo/compare/`](http://localhost:8000/ipo/compare/) | Side-by-side comparison matrix across valuation & financials |
| **AI Recommendations** | [`/modules/ai_recommendations/`](http://localhost:8000/modules/ai_recommendations/) | Dual perspective recommendations & multi-factor trade setups |
| **Portfolio Overview** | [`/portfolio/`](http://localhost:8000/portfolio/) | Net worth, asset allocation, sector exposure, risk distribution |
| **Holdings & FIFO Lots** | [`/portfolio/holdings/`](http://localhost:8000/portfolio/holdings/) | Open holding lots, unrealized P&L, lot acquisition costs |
| **Stock Screener** | [`/screener/`](http://localhost:8000/screener/) | Multi-variable quantitative equity scanner with CSV export |
| **My Watchlists** | [`/watchlists/`](http://localhost:8000/watchlists/) | User watchlists with price targets, stop losses, and quick add |
| **Swing Trade Scanner** | [`/trading/`](http://localhost:8000/trading/) | Quantitative swing setups (Pullback, Breakout, Climax) |
| **Trade Journal** | [`/trading/journal/`](http://localhost:8000/trading/journal/) | SEBI-aligned pre-trade checklist, emotional discipline log |
| **Position Sizer** | [`/trading/position-sizer/`](http://localhost:8000/trading/position-sizer/) | Volatility ATR mathematical position sizing calculator |
| **ML & Market Regimes** | [`/ml/`](http://localhost:8000/ml/) | Market regime classification & statistical stock ranking |
| **Strategy Backtesting** | [`/backtesting/`](http://localhost:8000/backtesting/) | Historical strategy simulation engine with slippage & fees |
| **Broker Connections** | [`/brokers/`](http://localhost:8000/brokers/) | Zerodha Kite Connect credentials & holdings sync |
| **F&O Derivatives** | [`/brokers/derivatives/`](http://localhost:8000/brokers/derivatives/) | NSE active Futures & Options contract master |
| **News & Corporate Events**| [`/news/`](http://localhost:8000/news/) | Real-time news feed, corporate filings, earnings announcements |
| **Alerts Engine** | [`/alerts/`](http://localhost:8000/alerts/) | Automated price, indicator, and stop-loss alert triggers |
| **Reports Center** | [`/reports/`](http://localhost:8000/reports/) | Institutional printable PDF tear-sheets and CSV exports |

---

## 10. Automated Testing & Code Quality

The platform enforces high test coverage and strict linting:

### Run Complete Test Suite (226 Tests)
```bash
pytest
```

### Run Tests with Line-by-Line Coverage Report
```bash
pytest --cov=apps --cov=services --cov=integrations --cov-report=term-missing
```

### Run Linter Checks (Ruff)
```bash
ruff check .
```

### Test Suite Distribution
- `tests/test_ipo.py`: Complete primary market suite (39 tests: master models, lifecycle milestones, time-series subscription, radar geometry, empirical listing gain predictor, family vault batch apply, registrar adapters, and strategy backtest workspace).
- `tests/test_logos.py`: Logo proxy, cache TTL, and SVG monogram fallback tests.
- `tests/test_recommendations.py`: Dual-perspective logic, ATR stop loss, and structural targets.
- `tests/test_portfolio_accounting.py`: FIFO lot matching, corporate actions, and fee capitalization.
- `tests/test_indicators.py`: Technical indicator mathematical precision vs. benchmarks.
- `tests/test_fundamentals.py`: 5-factor scoring and valuation metrics.
- `tests/test_stocks.py`: Autocomplete, research profiles, and chart data JSON APIs.
- `tests/test_trading_views.py`: Swing scanner, position sizer, and trade journal checklists.
- `tests/test_backtesting.py`: Chronological simulation engine and transaction costs.
- `tests/test_ml_engine.py`: Regime classifier and feature score ranking.
- `tests/test_brokers.py`: Fernet encrypted credentials, Kite client, and derivatives.

---

## 11. Operations, Backup & Docker Runbook

### Automated PostgreSQL Backup & Restore
Automated operational scripts are provided in `scripts/`:

```bash
# Backup database with timestamp and gzip compression
./scripts/backup_db.sh

# Restore from a backup archive
./scripts/restore_db.sh backups/db_backup_20261112.sql.gz
```

### Production Deployment Security Audit
Verify deployment security settings against Django's checklist:
```bash
python manage.py check --deploy --settings=config.settings.production
```

### Docker Containerization
Run the full platform stack (Web + PostgreSQL + Redis + Celery Worker + Celery Beat) using Docker Compose:
```bash
# Build and run containers in detached mode
docker-compose up -d --build

# Run migrations inside container
docker-compose exec web python manage.py migrate

# Seed baseline data
docker-compose exec web python manage.py seed_instruments
docker-compose exec web python manage.py seed_stock_research
```

---

## License & Regulatory Disclaimer

**Mandatory Regulatory Notice:** This software is designed exclusively for personal research, educational analysis, and risk modeling. Predictive research opinions, trade level projections, and algorithmic signals are calculated strictly from historical distributions and mathematical formulas. These models do not guarantee future returns and should not be construed as investment advice.
