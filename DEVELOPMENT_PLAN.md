# Development Plan & Implementation Roadmap

**Project:** Indian Stock Market Research & Intelligence Platform  
**Architecture:** Django Modular Monolith  
**Reference Document:** `MASTER_SPECIFICATION_DJANGO.md`  
**Execution Strategy:** Incremental, test-driven, phase-gated delivery  
**Revision:** 2.1 (Final Architecture Refinements Applied)

---

## 1. Pre-Flight Setup & Environment Preparation (Prerequisite for Phase 1)

Before writing application code, the environment and workspace scaffolding must be prepared:
1. **Repository Setup:** Initialize Git repository and standard `.gitignore`.
2. **Virtual Environment:** Configure Python 3.12+ virtualenv.
3. **Environment Secrets:** Author `.env.example` containing configuration variables, including `FIELD_ENCRYPTION_KEY` (Fernet 32-byte key for stored credentials).
4. **Database & Cache Services:** Provide Docker Compose / local service configuration for PostgreSQL 16 and Redis 7.

---

## 2. Phase-by-Phase Implementation Specifications

---

### Phase 1: Django Foundation, Operations & Dynamic UI Shell [STATUS: COMPLETED 🟢]

- **Objective:** Establish the Django modular monolith foundation, configure database and cache backends, install `django-htmx`, implement the persistent HTML shell with Bootstrap 5 and HTMX, and deliver dynamic content swapping without full page refreshes, with full history restoration, active sidebar state preservation, and documented operational runbooks.
- **Status:** **COMPLETED & VALIDATED (2026-11-12)**. 16/16 automated tests passed with 93% code coverage.
- **Django Apps Involved:** `core`, `accounts`, `dashboard`
- **Files to Create or Modify:**
  - `config/settings/base.py`, `development.py`, `production.py`
  - `config/urls.py`, `config/wsgi.py`, `config/celery.py`
  - `apps/core/models.py`, `apps/core/mixins.py`, `apps/core/templatetags/core_tags.py`
  - `apps/accounts/models.py`, `apps/accounts/views.py`, `apps/accounts/forms.py`
  - `apps/dashboard/views.py`, `apps/dashboard/urls.py`
  - `templates/base/shell.html`, `templates/base/_header.html`, `templates/base/_sidebar.html`, `templates/base/_footer.html`
  - `templates/dashboard/dashboard.html`, `templates/dashboard/partials/dashboard_partial.html`
  - `static/css/theme.css`, `static/js/app.js`
  - `scripts/backup_db.sh`, `scripts/restore_db.sh`
- **Database Models:**
  - `accounts.CustomUser` (AbstractUser extension with timezone and phone number)
  - `accounts.UserPreference` (Theme toggle, default watchlists, email alert switches)
  - `core.AuditedModel` (Abstract base with `created_at`, `updated_at`)
- **Dependencies:** `django`, `psycopg[binary]`, `django-environ`, `redis`, `celery`, `django-htmx`, `cryptography`
- **Implementation Sequence:**
  1. Initialize Django project structure with split settings and `django_htmx` middleware.
  2. Implement custom user model and run initial migrations against PostgreSQL.
  3. Construct base HTML shell with persistent sidebar, top header, and dynamic `#main-content`.
  4. Implement `HTMXResponseMixin` supporting dual-template rendering using `request.htmx`.
  5. Add client-side listeners for `htmx:historyRestore` and `htmx:afterOnLoad` to preserve active navigation state.
  6. Mount dashboard route verifying dynamic HTMX module swap and direct browser URL access.
  7. Add automated PostgreSQL backup and restore scripts.
- **Testing Strategy:**
  - Unit tests for `CustomUser` creation and authentication backends.
  - Integration tests for `HTMXResponseMixin` verifying partial template rendering on `request.htmx=True` and full shell on direct HTTP GET.
  - Direct URL access tests for bookmarking.
  - Test verifying sidebar `.active` class assignment on both server-rendered and HTMX dynamic transitions and history restoration (`htmx:historyRestore`).
- **Acceptance Criteria:**
  - Application boots cleanly; `/dashboard/` loads full shell.
  - Clicking sidebar links replaces `#main-content` without reloading the page or flashing header/sidebar.
  - Browser back/forward correctly updates the module content, URL, and active sidebar item.
- **Potential Risks & Mitigations:**
  - *Risk:* HTMX history restoration cache showing outdated DOM states.  
    *Mitigation:* Configure `hx-history="false"` on sensitive dynamic widgets or handle `htmx:historyRestore`.

---

### Phase 2: Market Data Providers, Trading Calendar & Historical Storage

- **Status:** 🟢 **COMPLETED (2026-11-12)** &bull; 43 tests passing (81% overall coverage)
- **Objective:** Create the provider-independent market data integration layer, implement Jugaad-Data (primary NSE) and Yahoo Finance (secondary fallback) adapters, integrate the Indian Exchange Trading Calendar, implement the two-dimensional status model (`source_type` & `freshness_status`), and store raw immutable historical candles in PostgreSQL with critical compound indexes.
- **Django Apps Involved:** `instruments`, `market`, `settings_app`, `integrations/market_data`, `services/market_data`, `services/calendar`
- **Files to Create or Modify:**
  - `integrations/market_data/base.py` (`MarketDataProvider` ABC & DTOs with `SourceType` and `FreshnessStatus`)
  - `integrations/market_data/providers/jugaad/adapter.py`
  - `integrations/market_data/providers/yahoo/adapter.py`
  - `integrations/market_data/registry.py`, `normalizer.py`, `health.py`
  - `services/calendar/exchange_calendar.py` (NSE holiday calendar & session hours)
  - `services/market_data/service.py` (`MarketDataService`)
  - `apps/market/models.py`, `apps/instruments/models.py`
  - `apps/market/tasks.py` (Celery daily Bhavcopy ingest with calendar check)
  - `apps/settings_app/views.py` (Data source health UI)
- **Database Models:**
  - `instruments.Exchange` (Code: NSE, BSE; Timezone: Asia/Kolkata)
  - `instruments.Instrument` (Canonical: ISIN, legal name, sector, industry, market cap)
  - `instruments.ExchangeListing` (Exchange, symbol, trading_symbol, series, token, is_primary)
  - `market.MarketQuote` (LTP, change, volume, source_provider, retrieved_at, source_type, freshness_status, measured_latency_ms)
  - `market.HistoricalCandle` (Listing, timestamp, interval, OHLCV, adjusted_close, source)
  - `market.DataProvider` & `market.DataRefreshLog` & `market.DataQualityIssue`
- **Critical Database Indexes:**
  - `market_historicalcandle`: `CREATE UNIQUE INDEX (listing_id, interval, timestamp)` and `CREATE INDEX (listing_id, interval, timestamp DESC)`.
  - `market_marketquote`: `CREATE INDEX (listing_id, retrieved_at DESC)`.
- **Dependencies:** `jugaad-data`, `yfinance`, `pandas`, `requests`
- **Implementation Sequence:**
  1. Implement `Instrument` (canonical) and `ExchangeListing` models with unique constraints.
  2. Implement `services.calendar.ExchangeCalendar` storing NSE holidays and trading sessions.
  3. Author abstract `MarketDataProvider` and standardized DTOs enforcing `SourceType` and `FreshnessStatus`.
  4. Implement `JugaadDataProvider` using a single persistent session and platform User-Agent.
  5. Implement `YahooFinanceProvider` for fallback and comparative historical data (explicit 15m delay).
  6. Build `MarketDataService` orchestrating caching, provider fallback, and quality checks.
  7. Create Celery tasks for bulk Bhavcopy ingestion verifying exchange calendar before execution.
- **Testing Strategy:**
  - Unit tests using mocked JSON / CSV payloads for Jugaad and Yahoo.
  - Validation test for OHLC inequalities ($Low \le Close \le High$) and negative volume rejection.
  - Provider failure test verifying graceful fallback to Yahoo if Jugaad fails.
  - Stale data detection test verifying transition to `STALE` and `OFFLINE`.
  - Duplicate ingestion test ensuring idempotent Bhavcopy ingestion without duplicate records.
  - Calendar tests ensuring scheduled ingestion skips official NSE holidays.
- **Acceptance Criteria:**
  - Historical NSE stock candles can be imported via Celery or management command.
  - Quotes distinctly present `source_type` (`DIRECT`, `DELAYED`, `EOD`) and `freshness_status` (`FRESH`, `CACHED`, `STALE`, `OFFLINE`).
  - Admin/Data Sources view shows accurate health and latency for both providers.
- **Potential Risks & Mitigations:**
  - *Risk:* NSE endpoint rate limiting or schema changes breaking Jugaad-Data.  
    *Mitigation:* Exponential backoff, 1.5s delay between requests, honest User-Agent, and automatic failover to Yahoo.

---

### Phase 3: Instrument & Stock Research Engine (Raw vs. Derived Separation)

- **Status:** 🟢 **COMPLETED (2026-11-12)** &bull; 63 tests passing (87% overall coverage)
- **Objective:** Provide a fast stock directory, autocomplete search, detailed profile pages, historical interactive charts, and versioned technical/fundamental calculation engines separated from raw candle data.
- **Django Apps Involved:** `stocks`, `instruments`, `technical_analysis`, `fundamental_analysis`
- **Files to Create or Modify:**
  - `apps/stocks/views.py`, `apps/stocks/urls.py`
  - `apps/stocks/templates/stocks/stock_detail.html`
  - `services/indicators/calculator.py` (SMA, EMA, RSI, MACD, Bollinger Bands, ATR)
  - `services/fundamentals/analyzer.py` (Ratios, valuation metrics, scores)
  - `apps/technical_analysis/models.py` (`TechnicalIndicatorSnapshot` with calculation version)
  - `apps/fundamental_analysis/models.py` (`FundamentalSnapshot` with calculation version)
  - `apps/technical_analysis/tasks.py` (Celery indicator calculation chained *after* ingest)
  - `static/js/charting.js` (Lightweight Charts integration)
- **Database Models:**
  - `technical_analysis.TechnicalIndicatorSnapshot` (Listing, SMA20/50/200, RSI, MACD, calculation_version, calculated_at)
  - `fundamental_analysis.FundamentalSnapshot` (Instrument, P/E, P/B, ROE, ROCE, D/E, Profit Margins, calculation_version)
- **Critical Database Indexes:**
  - `technical_analysis_technicalindicatorsnapshot`: `CREATE INDEX (listing_id, interval, timestamp DESC)`.
- **Dependencies:** `pandas`, `numpy`
- **Implementation Sequence:**
  1. Build global stock search with debounce and HTMX autocomplete in the header across canonical instruments and listings.
  2. Implement `services.indicators.calculator` computing trend, momentum, and volatility with version tagging.
  3. Create Celery task chain ensuring indicators calculate only *after* successful Bhavcopy ingestion.
  4. Build stock detail view displaying quote summary, interactive candlestick chart, and indicator tables.
  5. Integrate fundamental ratios and multi-factor scoring card.
- **Testing Strategy:**
  - Numerical parity unit tests comparing calculated RSI/MACD/SMA against known benchmarks.
  - Recalculation test verifying indicators can be recomputed from raw candles without re-downloading data.
  - Search view tests verifying symbol, company name, and ISIN matching.
- **Acceptance Criteria:**
  - User can search any NSE stock and load its profile in `#main-content`.
  - Candlestick chart renders historical daily prices with interactive volume and moving averages.
  - Indicators are calculated deterministically without fabricating missing points and display calculation version.
- **Potential Risks & Mitigations:**
  - *Risk:* Heavy indicator calculations blocking server workers.  
    *Mitigation:* Offload EOD indicator recalculation to Celery workers with precalculated snapshots stored in PostgreSQL.

---

### Phase 4: Portfolio Accounting: Immutable Ledger & FIFO Lot Matching

- **Status:** 🟢 **COMPLETED (2026-11-12)** &bull; 80 tests passing (87% overall coverage)
- **Objective:** Build multi-portfolio tracking where immutable transaction records serve as the single source of truth, implementing FIFO lot matching for partial sales, capital charges allocation, adjustment/reversal entries, corporate actions handling, and automated reconciliation tests.
- **Django Apps Involved:** `portfolio`, `holdings`, `stocks`, `news`
- **Files to Create or Modify:**
  - `apps/portfolio/models.py`, `apps/portfolio/views.py`, `apps/portfolio/urls.py`
  - `apps/holdings/models.py`, `apps/holdings/views.py`
  - `services/portfolio/accounting.py` (FIFO lot matcher, cost basis, realized & unrealized P&L)
  - `services/portfolio/corporate_actions.py` (Bonus, split, dividend adjustment processor)
  - `services/recommendations/evaluator.py` (Holder vs New Buyer recommendations)
  - `templates/portfolio/overview.html`, `templates/portfolio/holding_detail.html`
- **Database Models:**
  - `portfolio.Portfolio` (User, name, currency, cash_balance)
  - `holdings.HoldingTransaction` (Immutable Ledger: Portfolio, Listing, type: BUY/SELL/DIVIDEND/BONUS/SPLIT/BUY_REVERSAL/SELL_REVERSAL, qty, price, brokerage, statutory_taxes, executed_at, reference_transaction_id, notes)
  - `holdings.Holding` (Derived view: Portfolio, Listing, total_quantity, avg_buy_price, invested_amt, current_value, unrealised_pnl, realised_pnl)
  - `holdings.LotAllocation` (Audit tracking of which BUY lots were closed by which SELL transaction)
- **Critical Database Indexes:**
  - `holdings_holdingtransaction`: `CREATE INDEX (portfolio_id, listing_id, executed_at ASC)` and `CREATE INDEX (portfolio_id, transaction_type, executed_at)`.
- **Dependencies:** None additional (Python `decimal.Decimal` module)
- **Implementation Sequence:**
  1. Implement `HoldingTransaction` model with detailed fields for execution price, brokerage, and statutory taxes.
  2. Implement `FIFOAccountingEngine` matching sells to open buy lots, capitalizing buy charges and deducting sell charges.
  3. Build `Holding.reconcile()` method deriving current holding state deterministically from transactions.
  4. Implement corporate action handlers for bonus shares, stock splits, and cash dividends.
  5. Implement `Holder vs New Buyer` recommendation block on stock profile and holding views.
- **Testing Strategy:**
  - Unit tests for FIFO lot matching across multiple purchases and partial sells.
  - Multi-lot buy test verifying brokerage and statutory taxes are capitalized into unit cost basis.
  - Sell test verifying realized P&L is net of sales brokerage and statutory charges.
  - Reversal transaction test verifying `BUY_REVERSAL` reconciles holding back to zero without deleting records.
  - Corporate action tests verifying stock split doubles quantity and halves cost basis without altering invested capital.
  - Reconciliation test asserting that the sum of unclosed FIFO lots exactly matches `Holding.total_quantity` and `Holding.invested_amount`.
- **Acceptance Criteria:**
  - Portfolios accurately calculate invested capital, day P&L, unrealized P&L, and realized P&L.
  - Stock detail page displays distinct recommendation panels: "Existing Holder" vs "New Investor".
  - Transaction history is completely preserved when positions are partially or fully sold.
- **Potential Risks & Mitigations:**
  - *Risk:* Drift between derived holding values and transaction history.  
    *Mitigation:* Automated test on every transaction write verifying `Holding.reconcile()` matches the derived state.

---

### Phase 5: Stock Screener & Watchlists

- **Status:** 🟢 **COMPLETED (2026-11-12)** &bull; 98 tests passing (84% overall coverage)
- **Objective:** Develop a dynamic multi-variable stock screener supporting technical and fundamental criteria against pre-calculated snapshots, alongside customizable user watchlists.
- **Django Apps Involved:** `screener`, `watchlists`, `stocks`
- **Files to Create or Modify:**
  - `apps/screener/models.py`, `apps/screener/views.py`, `apps/screener/urls.py`
  - `apps/watchlists/models.py`, `apps/watchlists/views.py`, `apps/watchlists/urls.py`
  - `services/screener/engine.py` (Query builder and filtering pipeline)
  - `templates/screener/screener.html`, `templates/watchlists/watchlist_detail.html`
- **Database Models:**
  - `screener.ScreenerConfiguration` (User, name, filter_criteria JSON, created_at)
  - `screener.ScreenerResult` (ScreenerConfiguration, Listing, matched_values JSON, calculation_version, run_timestamp)
  - `watchlists.Watchlist` (User, name, description)
  - `watchlists.WatchlistItem` (Watchlist, Listing, added_price, target_price, notes)
- **Dependencies:** None additional
- **Implementation Sequence:**
  1. Author `ScreenerService` translating JSON filter definitions into optimized Django ORM queries against `TechnicalIndicatorSnapshot` and `FundamentalSnapshot`.
  2. Build interactive screener UI with dropdown criteria (RSI range, SMA alignment, P/E ratio, Market Cap).
  3. Implement Watchlist CRUD operations with HTMX inline additions and reordering.
- **Testing Strategy:**
  - Filter unit tests verifying accuracy of combinations (e.g. RSI < 30 AND Close > SMA200).
  - Benchmark performance tests on scanning the complete active universe.
- **Acceptance Criteria:**
  - User can create, run, and save custom screening presets.
  - Results show exactly which conditions each stock fulfilled.
  - Watchlists dynamically reflect latest market quotes and status badges.
- **Potential Risks & Mitigations:**
  - *Risk:* Complex screener queries causing high database CPU utilization.  
    *Mitigation:* Screen against pre-indexed snapshot tables rather than raw tick tables.

---

### Phase 6: Swing Trading & Risk Management Engine

- **Objective:** Build swing trading setup generation (1–8 week horizon), position sizing calculator, stop-loss invalidation tracker, and an immutable trade journal.
- **Django Apps Involved:** `trading`, `stocks`, `services/risk`
- **Files to Create or Modify:**
  - `apps/trading/models.py`, `apps/trading/views.py`, `apps/trading/urls.py`
  - `services/risk/calculator.py` (Position sizing, risk-to-reward ratio)
  - `services/trading/scanner.py` (Swing setup detection)
  - `templates/trading/swing_scanner.html`, `templates/trading/trade_journal.html`
- **Database Models:**
  - `trading.TradeSetup` (Listing, strategy, entry_min, entry_max, stop_loss, target_1, target_2, risk_reward, status)
  - `trading.TradeJournal` (User, Listing, TradeSetup, entry_date, entry_price, exit_date, exit_price, quantity, realised_pnl, lessons_learned)
- **Dependencies:** None additional
- **Implementation Sequence:**
  1. Author `services.risk.calculator` enforcing position sizing formulas based on trading capital and maximum risk percent.
  2. Implement swing trading scanner identifying consolidation breakouts and pullbacks.
  3. Build trade journal with execution recording and post-trade performance analytics.
- **Testing Strategy:**
  - Unit tests verifying position sizing zero-division protection when stop loss equals entry price.
  - Validation test rejecting trade setups with Risk-to-Reward ratio below 1:1.5.
- **Acceptance Criteria:**
  - Swing scanner surfaces qualified trade setups with clear entry, stop-loss, and target levels.
  - Trade journal records entries, exits, and realized P&L with lessons learned.
- **Potential Risks & Mitigations:**
  - *Risk:* Over-trading or aggressive sizing by users.  
    *Mitigation:* Hard-coded UI risk warnings when proposed trade risk exceeds 2% of total trading capital.

---

### Phase 7: AI Stock Research Engine

- **Objective:** Deploy structured AI research agents (Investor AI, Swing Trader AI, Portfolio Risk Manager) consuming strictly validated financial data to provide qualitative decision support with prompt versioning.
- **Django Apps Involved:** `ai_analysis`, `stocks`, `portfolio`, `integrations/ai_providers`
- **Files to Create or Modify:**
  - `integrations/ai_providers/base.py`, `client.py`
  - `services/ai/prompts.py` (Strict JSON output templates)
  - `apps/ai_analysis/models.py`, `apps/ai_analysis/views.py`
  - `templates/ai_analysis/stock_ai_memo.html`
- **Database Models:**
  - `ai_analysis.AIAnalysis` (Listing, model_name, prompt_version, analysis_type, structured_output JSON, timestamp)
- **Dependencies:** AI provider SDK (e.g. `google-genai` / `anthropic` / `openai`)
- **Implementation Sequence:**
  1. Author abstract AI provider client with structured schema enforcement.
  2. Implement data preparation service assembling verified prices, indicators, and holdings context into a prompt payload.
  3. Create views rendering AI memos with explicit data source timestamps, caveats, and confidence levels.
- **Testing Strategy:**
  - Mocked LLM unit tests validating JSON schema parsing and gracefully handling malformed responses.
  - Prompt regression tests preventing hallucinated price citations.
- **Acceptance Criteria:**
  - AI analysis displays structured opinions labeled BUY CANDIDATE / HOLD / WATCH / AVOID / REDUCE / EXIT.
  - Analysis explicitly identifies missing data points rather than guessing.
- **Potential Risks & Mitigations:**
  - *Risk:* LLM hallucination of financial figures.  
    *Mitigation:* Strictly pass factual context in prompt and validate output against database ground truth.

---

### Phase 8: News, Corporate Events & Alert Dispatcher

- **Objective:** Aggregate exchange announcements, dividends, splits, and deliver multi-channel price, technical, and portfolio threshold alerts.
- **Django Apps Involved:** `news`, `alerts`, `notifications`
- **Files to Create or Modify:**
  - `apps/news/models.py`, `apps/news/views.py`
  - `apps/alerts/models.py`, `apps/alerts/tasks.py`, `apps/alerts/engine.py`
  - `apps/notifications/models.py`, `apps/notifications/views.py`
  - `templates/alerts/alerts_list.html`
- **Database Models:**
  - `news.CorporateEvent` (Instrument, event_type: SPLIT/BONUS/DIVIDEND/EARNINGS, record_date, details)
  - `news.NewsArticle` (Instrument, headline, source, url, published_at, summary)
  - `alerts.AlertRule` (User, Listing, metric, condition, threshold, is_triggered, active)
  - `notifications.Notification` (User, title, message, channel, is_read, sent_at)
- **Dependencies:** None additional
- **Implementation Sequence:**
  1. Build alert evaluation engine executed via Celery during market sessions.
  2. Implement corporate actions data model linked to stock timeline.
  3. Create persistent notification drawer in header with unread badge counter.
- **Testing Strategy:**
  - Unit tests verifying alert state transitions (active $\rightarrow$ triggered $\rightarrow$ acknowledged).
  - Deduplication tests preventing repeated alerts for identical market triggers.
- **Acceptance Criteria:**
  - Alerts trigger reliably when threshold conditions are satisfied.
  - Duplicate notifications are suppressed.
- **Potential Risks & Mitigations:**
  - *Risk:* High frequency alert polling overloading database.  
    *Mitigation:* Evaluate alerts in-memory against Redis quote cache rather than repeatedly querying PostgreSQL.

---

### Phase 9: Strategy Backtesting & Machine Learning Engine

- **Objective:** Deliver historical strategy backtesting with realistic slippage and transaction costs, complemented by time-series ML models for market regime classification.
- **Django Apps Involved:** `backtesting`, `ml_engine`
- **Files to Create or Modify:**
  - `apps/backtesting/models.py`, `apps/backtesting/views.py`
  - `services/backtesting/engine.py` (Event-driven backtester)
  - `apps/ml_engine/models.py`, `services/ml/regime_detector.py`
  - `templates/backtesting/backtest_view.html`
- **Database Models:**
  - `backtesting.BacktestSession` (User, strategy_name, params JSON, start_date, end_date, total_return, cagr, max_drawdown, win_rate)
  - `backtesting.BacktestTrade` (Session, Listing, entry_time, exit_time, entry_price, exit_price, pnl)
  - `ml_engine.MLModelSnapshot` (Model type, features, training_date_range, evaluation_metrics)
- **Dependencies:** `scikit-learn`, `joblib`
- **Implementation Sequence:**
  1. Build event-driven backtesting engine with explicit commission and slippage penalties.
  2. Compute quantitative metrics: Sharpe ratio, Maximum Drawdown, Profit Factor, Equity Curve.
  3. Implement time-series ML regime detector (Trend / Range / High Volatility) without look-ahead bias.
- **Testing Strategy:**
  - Backtest math verification against known reference trade series.
  - Time-series validation ensuring no future data leakage into training folds.
- **Acceptance Criteria:**
  - Backtester outputs equity curve and comprehensive performance summary.
  - ML outputs are presented strictly as probabilistic classifications, never guaranteed prices.
- **Potential Risks & Mitigations:**
  - *Risk:* Survivorship bias in historical backtests.  
    *Mitigation:* Maintain delisted symbols in the instrument master where historical bhavcopies provide them.

---

### Phase 10: F&O Preparation & Optional Zerodha Kite Integration

- **Objective:** Prepare data structures for Futures & Options analysis and build the optional, read-only Zerodha Kite Connect adapter with Fernet-encrypted credential storage.
- **Django Apps Involved:** `brokers`, `market`
- **Files to Create or Modify:**
  - `integrations/broker_providers/zerodha/client.py`
  - `apps/brokers/models.py`, `apps/brokers/views.py`
  - `templates/brokers/broker_settings.html`
- **Database Models:**
  - `brokers.BrokerConnection` (User, broker_name, api_key_enc, request_token, access_token_enc, token_expires_at, is_active)
  - `market.DerivativeContract` (Underlying, expiry_date, strike_price, option_type, lot_size)
- **Dependencies:** `kiteconnect`, `cryptography`
- **Implementation Sequence:**
  1. Implement read-only Zerodha Kite OAuth connection flow with AES/Fernet encryption for stored tokens.
  2. Implement Kite data adapter for quotes, instrument master, and read-only holding synchronization.
  3. Add security protections: strict backend secret storage, zero order-placement code.
- **Testing Strategy:**
  - Mocked HTTP OAuth token exchange tests.
  - Verification that platform runs completely when Kite credentials are empty.
  - Encryption test verifying secret values in the database are ciphertext, decryptable only with `FIELD_ENCRYPTION_KEY`.
- **Acceptance Criteria:**
  - User can connect Kite account; holdings sync automatically into Portfolio.
  - Absolutely no automatic or manual trading endpoints exist.
- **Potential Risks & Mitigations:**
  - *Risk:* Token expiration or broker API outages.  
    *Mitigation:* Catch authentication exceptions gracefully, tag connection as `EXPIRED`, and prompt user to re-authenticate without crashing the app.

---

### Phase 11: Production Hardening, Audit & Deployment

- **Objective:** Perform end-to-end security audit, database query optimization, automated test suite completion, Docker containerization, and production deployment configuration.
- **Django Apps Involved:** All apps
- **Files to Create or Modify:**
  - `Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`
  - `config/settings/production.py`
  - `scripts/backup_db.sh`, `scripts/health_check.py`
  - `docs/DEPLOYMENT.md`, `docs/SECURITY.md`
- **Database Models:** None
- **Dependencies:** `gunicorn`, `whitenoise`
- **Implementation Sequence:**
  1. Complete Django deployment checklist (`python manage.py check --deploy`).
  2. Add database indexes on all foreign keys and query filters.
  3. Configure Docker production build with non-root user and minimal attack surface.
  4. Author comprehensive operational documentation.
- **Testing Strategy:**
  - Full automated regression test run achieving target coverage.
  - Load testing on stock detail and screener endpoints.
- **Acceptance Criteria:**
  - Zero security warnings from Django deploy check.
  - Dockerized build boots cleanly with PostgreSQL, Redis, Celery worker, and Celery beat.
- **Potential Risks & Mitigations:**
  - *Risk:* High latency on cold starts.  
    *Mitigation:* Warm up Redis quote cache during Celery startup.

---

## 3. Immediate Next Steps: Ready for Phase 2

Phase 1 has been completed and verified. Upon your explicit approval, we will initiate **Phase 2: Market Data Providers, Trading Calendar & Historical Storage**:
1. Implement `instruments.Exchange` and `instruments.Instrument` / `ExchangeListing` models.
2. Implement `services.calendar.ExchangeCalendar` (NSE trading holidays and session hours).
3. Author `integrations.market_data.base.MarketDataProvider` abstract base class and standardized DTOs enforcing `SourceType` and `FreshnessStatus`.
4. Implement `JugaadDataProvider` for NSE historical OHLCV and daily Bhavcopy.
5. Implement `YahooFinanceProvider` for comparative historical data and fallback.
6. Build `MarketDataService` orchestrating caching, provider fallback, and quality checks.
7. Create Celery tasks for scheduled Bhavcopy ingestion and populate initial NSE instrument master.
