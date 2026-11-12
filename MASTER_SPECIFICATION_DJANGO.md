# MASTER_SPECIFICATION_DJANGO.md
# Indian Stock Market Research & Intelligence Platform

**Document Type:** Master Product & Technical Specification  
**Application:** Personal Indian Stock Market Research and Intelligence Platform  
**Backend:** Python + Django  
**Frontend:** Django Templates + Bootstrap 5 + HTMX  
**Database:** PostgreSQL  
**Background Processing:** Celery + Redis  
**Initial Market Data:** Jugaad-Data + Yahoo Finance  
**Future Broker Integration:** Zerodha Kite Connect  
**Initial Market Coverage:** NSE and BSE equities  
**Future Market Coverage:** Futures and Options  
**Architecture:** Django Modular Monolith  
**Development Environment:** Local-first, production-ready design

---

# 1. PROJECT VISION

Build a comprehensive Indian stock market research, portfolio management, technical analysis and AI-assisted investment intelligence platform.

The application should help the user make informed investment and trading decisions using:

- Indian stock market data.
- Historical price analysis.
- Technical indicators.
- Fundamental analysis.
- Portfolio and existing holdings analysis.
- Stock screening.
- Swing trading opportunities.
- Risk management.
- AI-powered research.
- Machine learning experiments.
- Market news and corporate events.
- Alerts and notifications.
- Strategy backtesting.

The platform must support both existing investors and new investment opportunities.

It must distinguish between:
1. A stock that the user already owns.
2. A stock that the user is considering buying.
3. A stock that the user is monitoring for swing trading.

These situations require different analysis and recommendations.

The platform is intended for personal research and decision support. It must not automatically execute trades.

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
12. Store historical market data in PostgreSQL.
13. Use Redis for caching and Celery task coordination.
14. Maintain a provider-independent data model.
15. Make all major features independently testable.
16. Avoid duplicated business logic and circular dependencies.
17. Never fabricate market data.
18. Display data source and freshness.
19. Preserve historical portfolio transactions.
20. Keep broker integration optional.

---

# 3. TECHNOLOGY STACK

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Backend | Django |
| Frontend | Django Templates |
| UI Framework | Bootstrap 5 |
| Dynamic navigation | HTMX |
| Browser scripting | JavaScript |
| API framework | Django REST Framework |
| Database | PostgreSQL |
| Cache | Redis |
| Background tasks | Celery |
| Scheduler | Celery Beat |
| Data analysis | Pandas, NumPy |
| Technical analysis | pandas-ta / TA-Lib where available |
| Charts | Lightweight Charts / Plotly |
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
│   ├── ai_providers/
│   ├── news_providers/
│   └── broker_providers/
│
├── services/
│   ├── market_data/
│   ├── indicators/
│   ├── fundamentals/
│   ├── portfolio/
│   ├── risk/
│   ├── recommendations/
│   └── common/
│
├── templates/
│   ├── base/
│   ├── components/
│   └── errors/
│
├── static/
│   ├── css/
│   ├── js/
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
| core | Shared utilities, base functionality |
| accounts | User authentication and preferences |
| dashboard | Main dashboard |
| market | Market overview and indices |
| instruments | Exchange and instrument master |
| stocks | Stock profiles and stock search |
| technical_analysis | Technical indicators and signals |
| fundamental_analysis | Financial metrics and valuation |
| portfolio | Portfolio management |
| holdings | Existing holdings and transactions |
| trading | Swing trading and trade journal |
| screener | Custom stock screening |
| watchlists | User watchlists |
| ai_analysis | AI stock research |
| ml_engine | Machine learning |
| news | News and corporate events |
| alerts | Price and technical alerts |
| backtesting | Historical strategy testing |
| brokers | Broker connectivity |
| reports | Reports and exports |
| notifications | In-app and external notifications |
| settings_app | Application and provider settings |

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
- Data Sources
- Broker Connections
- Reports
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
4. Update browser URL using history support.
5. Highlight the active navigation item.
6. Show loading indicators.
7. Support browser back and forward.
8. Support direct access to every module URL.
9. Support full-page fallback if HTMX is unavailable.
10. Return partial templates for HTMX requests and full templates for normal requests.

Use a shared base template.

Do not create a separate HTML shell for every Django app.

## 5.4 Header

Include:

- Application logo and title.
- Market status.
- NIFTY 50.
- SENSEX.
- NIFTY BANK.
- Global stock search.
- Notifications.
- Data freshness indicator.
- User settings.

Do not hardcode market values.

## 5.5 Design

- Professional financial dashboard.
- Responsive desktop and tablet design.
- Light and dark modes.
- Clear financial typography.
- Green for positive values.
- Red for negative values.
- Neutral information styling.
- Reusable cards, tables and charts.
- Loading skeletons.
- Friendly empty states.
- Clear source and timestamp labels.

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

Implement the following indicators.

## Trend

- SMA 20.
- SMA 50.
- SMA 100.
- SMA 200.
- EMA 9.
- EMA 20.
- EMA 50.
- MACD.

## Momentum

- RSI 14.
- Stochastic RSI.
- ADX.
- Rate of Change.

## Volatility

- Bollinger Bands.
- ATR.
- Historical volatility.

## Volume

- Volume moving average.
- Relative volume.
- Volume breakout.
- OBV.

## Price structure

- Support.
- Resistance.
- Swing highs.
- Swing lows.
- Breakouts.
- Moving average crossovers.

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

## Fundamental scoring

Evaluate:

- Growth.
- Profitability.
- Valuation.
- Financial health.
- Ownership.
- Dividend history.

Display:

- Overall score.
- Positive factors.
- Negative factors.
- Missing data.
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

# 13. STOCK SCREENER MODULE

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

# 14. WATCHLIST MODULE

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

# 15. TRADING AND SWING TRADING MODULE

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

## Risk management

Calculate position sizing based on:

- Available capital.
- Maximum risk percentage.
- Entry.
- Stop-loss.
- Quantity.

Example:

```python
risk_amount = trading_capital * risk_percentage

risk_per_share = abs(entry_price - stop_loss)

quantity = int(risk_amount / risk_per_share)
```

Validate zero or negative stop-loss distances.

Apply practical liquidity and order-size limits.

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

# 16. FUTURES AND OPTIONS ARCHITECTURE

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

# 17. AI STOCK ANALYSIS MODULE

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

Keep the AI provider configurable.

---

# 18. MACHINE LEARNING MODULE

Introduce ML only after reliable historical data is available.

Potential features:

- Trend classification.
- Momentum classification.
- Volatility classification.
- Breakout research.
- Stock ranking.
- Anomaly detection.
- Market regime classification.

Requirements:

- Time-series-aware validation.
- No random chronological shuffling.
- No look-ahead bias.
- Avoid survivorship bias.
- Compare with rule-based baselines.
- Store model version.
- Store training range.
- Store features.
- Store evaluation metrics.
- Store prediction timestamp.

Never display predictions as guaranteed future prices.

---

# 19. NEWS AND CORPORATE EVENTS

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

# 20. ALERTS AND NOTIFICATIONS

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

# 21. BACKTESTING MODULE

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

# 22. ZERODHA KITE CONNECT — FUTURE INTEGRATION

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

# 23. REPORTS MODULE

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

# 24. DATABASE ARCHITECTURE

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

# 25. BACKGROUND PROCESSING

Use Celery + Redis.

Background tasks:

- Historical data import.
- Daily market refresh.
- Quote refresh.
- Technical indicator calculation.
- Fundamental refresh.
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

# 26. API ARCHITECTURE

Use Django REST Framework.

Suggested endpoints:

```text
/api/v1/market/
/api/v1/instruments/
/api/v1/stocks/
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

# 27. SECURITY

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

# 28. TESTING

## Unit tests

- Indicator calculations.
- Portfolio calculations.
- Average price.
- P&L.
- Risk sizing.
- Screener conditions.
- Provider normalisation.
- Data validation.

## Integration tests

- Database operations.
- Jugaad adapter.
- Yahoo adapter.
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

Use mocked provider responses in automated tests.

Tests must not depend on live market availability.

---

# 29. LOGGING AND MONITORING

Track:

- Application errors.
- Provider failures.
- Data refresh failures.
- Broker connectivity.
- Background task failures.
- AI provider errors.
- Slow requests.
- Data freshness.

Create an administrative data-source health view.

Do not log secrets.

---

# 30. ENVIRONMENT CONFIGURATION

Example `.env.example`:

```dotenv
DJANGO_SECRET_KEY=replace_me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgresql://user:password@localhost:5432/stock_intelligence

REDIS_URL=redis://localhost:6379/0

# Initial market data
ENABLE_JUGAAD_DATA=True
ENABLE_YAHOO_FINANCE=True
MARKET_DATA_PROVIDER_PRIORITY=jugaad,yahoo

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
```

Do not commit the actual `.env` file.

Provide setup instructions for macOS and Linux.

---

# 31. IMPLEMENTATION ROADMAP

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

## Phase 3 — Stock research

- Instrument master.
- Stock search.
- Stock detail.
- Historical charts.
- Technical indicators.
- Fundamental data model.
- Sector analysis.

Acceptance:
A user can search a stock and inspect available historical, technical and fundamental information.

## Phase 4 — Portfolio

- Manual portfolio creation.
- Transactions.
- Holdings.
- Average price.
- P&L.
- Portfolio analytics.
- Existing-holder recommendations.

Acceptance:
Portfolio calculations are accurate and transaction history is preserved.

## Phase 5 — Screener and watchlists

- Custom screening.
- Saved filters.
- Watchlists.
- Stock monitoring.

Acceptance:
Users can create and save screeners and watchlists.

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

# 32. CRITICAL BUSINESS RULES

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

---

# 33. GOOGLE ANTIGRAVITY IMPLEMENTATION INSTRUCTIONS

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

# 34. DEFINITION OF DONE

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

# 35. FINAL ARCHITECTURAL DIRECTION

Build a dependable Django modular monolith.

Initial data providers:
- Jugaad-Data: primary Indian NSE data provider where supported.
- Yahoo Finance: secondary historical data provider.

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