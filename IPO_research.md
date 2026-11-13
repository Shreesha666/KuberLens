# FEATURE IMPLEMENTATION: IPO RESEARCH & INTELLIGENCE CENTRE

## 1. Role

Act as a Senior Django Software Architect, Indian Equity Market Research Analyst, Financial Data Engineer and Full-Stack Developer.

Implement a comprehensive IPO Research & Intelligence module for my existing Indian Stock Market Research Platform.

This is a new feature within the existing project, not a standalone application.

Read the existing:
- MASTER_SPECIFICATION_DJANGO.md
- ARCHITECTURE.md
- IMPLEMENTATION_STATUS.md
- DEVELOPMENT_PLAN.md

Follow the existing Django modular monolith architecture, UI design system, authentication, charting architecture and market data integration standards.

## 2. Main Objective

Build an IPO Intelligence Centre covering the entire Indian IPO lifecycle:

1. DRHP Filed
2. SEBI / Exchange Approval
3. Upcoming IPOs
4. Live IPOs
5. Closed IPOs
6. Allotment Status
7. Listing
8. Post-listing Performance

Support both:
- Mainboard IPOs
- SME IPOs (NSE Emerge and BSE SME)

The system should provide research, analytics, recommendations, bidding calculations and investment tracking.

## 3. Navigation and UI

Add a new main sidebar menu:

IPO Intelligence

Submenus:

- IPO Dashboard
- Upcoming IPOs
- Live IPOs
- Closed IPOs
- IPO Calendar
- IPO Recommendations
- IPO Comparison
- IPO Research
- Bid Planner
- Allotment Tracker
- IPO Performance
- IPO Watchlist
- IPO Investment Journal
- Data Sources & Health

Use the existing application shell and HTMX navigation.

Do not create a separate layout or duplicate the common sidebar.

## 4. IPO Dashboard

Create an executive IPO dashboard showing:

- Upcoming IPO count.
- Currently open IPO count.
- Recently closed IPO count.
- Upcoming allotment dates.
- Upcoming listing dates.
- Best-rated IPO candidates.
- IPOs with highest subscription.
- IPOs with highest reported GMP.
- Recent listing performance.
- Mainboard versus SME statistics.
- IPO sector distribution.

Use Apache ECharts for dashboard visualizations.

All values must come from actual stored or verified source data.

## 5. IPO Master Data and Lifecycle

Create a canonical IPO master record with:

- Company name.
- IPO identifier.
- Company description.
- Industry and sector.
- Mainboard / SME classification.
- Exchange.
- IPO status.
- DRHP filing date.
- SEBI observation / approval information, where applicable.
- Opening date.
- Closing date.
- Allotment date.
- Refund / unblock date, where verifiable.
- Demat credit date, where available.
- Listing date.
- Price band.
- Issue price.
- Lot size.
- Minimum investment.
- Total issue size.
- Fresh issue amount.
- OFS amount.
- Total shares offered.
- Retail reservation.
- QIB reservation.
- NII reservation.
- Employee / shareholder reservation, if applicable.
- Promoter holding before and after issue.
- Lead managers.
- Registrar.
- DRHP URL.
- RHP URL.
- Prospectus URL.
- Official NSE/BSE issue URL.
- Last verified timestamp.

Support changes in dates, price bands, issue sizes and other details with an audit trail.

Use appropriate IPO lifecycle statuses instead of relying on manually entered labels.

Distinguish confirmed, provisional, withdrawn, postponed and cancelled issues.

## 6. Data Collection and Provider Architecture

Create provider-independent IPO data adapters.

Priority sources:

### Primary official sources

1. NSE India:
   https://www.nseindia.com/market-data/all-upcoming-issues-ipo

2. NSE Issue Information:
   https://www.nseindia.com/market-data/issue-information

3. NSE IPO bid verification:
   https://www.nseindia.com/invest/check-trades-bids-verify-ipo-bids

4. BSE India:
   https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p

5. SEBI:
   https://www.sebi.gov.in/

6. SEBI Investor:
   https://investor.sebi.gov.in/

### Supplementary sources

- OpenIPO: https://www.openipo.in/
- IPOinfo: https://www.ipoinfo.ai/
- Registrar websites.
- Issuer company websites.
- Official company filings and annual reports.

### Data source implementation rules

- Build separate adapters for NSE, BSE, SEBI and supplementary sources.
- Use a normalized internal IPO data model.
- Do not tightly couple the application to any single provider.
- Do not assume websites expose stable public APIs.
- Verify access permissions, terms, rate limits and data licensing before automated ingestion.
- Do not bypass anti-bot controls or authentication restrictions.
- Support manual data entry and CSV/document import as fallbacks.
- Implement scheduled ingestion using Celery.
- Implement retry handling, duplicate detection and source health monitoring.
- Record source URL, retrieved_at, published_at, verification status and source priority.
- Preserve historical changes in subscription and issue details.
- Flag conflicting information from different sources for review.
- Never silently replace verified official information with unofficial data.

Create a source reliability classification:

- OFFICIAL_EXCHANGE
- OFFICIAL_REGULATOR
- OFFICIAL_ISSUER
- OFFICIAL_REGISTRAR
- THIRD_PARTY
- UNOFFICIAL_MARKET_ESTIMATE

## 7. Live IPO Subscription Analytics

Track category-wise subscription:

- QIB.
- NII.
- Retail.
- Employee.
- Shareholder.
- Other applicable categories.

Store:

- Shares offered.
- Shares bid.
- Subscription multiple.
- Number of applications, when published.
- Cut-off bids, when available.
- Price-wise bidding information, when available.
- Observation timestamp.
- Data source.

Create time-series snapshots rather than overwriting previous subscription data.

Display:

- Overall subscription.
- Category-wise subscription.
- Day-wise subscription.
- Demand momentum.
- Category comparison.
- Final subscription.
- Number of applications where available.

Use Apache ECharts for these visualizations.

Clearly identify data that is indicative, delayed or incomplete.

## 8. IPO Fundamental Research Engine

Create an IPO research module.

Extract and store information from DRHP, RHP, prospectus and annual reports.

Analyze:

### Business
- Business model.
- Products and services.
- Industry.
- Competitive positioning.
- Customer concentration.
- Supplier concentration.
- Geographical concentration.

### Financial analysis
- Revenue for the last three financial years, where available.
- Revenue growth.
- EBITDA.
- EBITDA margin.
- PAT.
- PAT margin.
- EPS.
- Net worth.
- Borrowings.
- Cash flow from operations.
- Free cash flow.
- Return on Equity.
- Return on Capital Employed.

### Valuation
- IPO P/E.
- P/B.
- EV/EBITDA.
- Market capitalization at issue price.
- Peer company valuation.
- Discount or premium to peers.

### IPO structure
- Fresh issue.
- Offer for Sale.
- Use of proceeds.
- Debt repayment.
- Capital expenditure.
- General corporate purposes.
- Promoter dilution.

### Governance and risk
- Promoter background.
- Litigation.
- Related-party transactions.
- Auditor qualifications.
- Contingent liabilities.
- Regulatory risks.
- Business concentration risks.

Every extracted financial figure must retain its reporting period, document reference and source.

Do not treat missing values as zero.

## 9. IPO Scoring and Recommendation Engine

Create a transparent weighted scoring model.

Suggested starting weights:

- Business quality: 20%.
- Financial strength: 20%.
- Valuation: 20%.
- Growth potential: 15%.
- Management and governance: 10%.
- IPO structure and use of proceeds: 10%.
- Subscription and market demand: 5%.

Total: 100%.

These weights must be configurable.

Display:

- Individual category scores.
- Overall score.
- Strengths.
- Weaknesses.
- Risk factors.
- Data completeness.
- Confidence level.
- Explanation of recommendation.

Recommendation classifications:

- STRONG_RESEARCH_CANDIDATE
- CONSIDER_APPLYING
- APPLY_WITH_CAUTION
- AVOID
- INSUFFICIENT_DATA

Do not allow subscription, GMP or market sentiment alone to determine an IPO recommendation.

Show separate investment-horizon assessments:

- Listing gain potential.
- Short-term investment potential.
- Long-term investment potential.

Do not promise listing gains or returns.

## 10. GMP Analytics

Implement optional Grey Market Premium tracking.

Requirements:

- Store reported GMP value.
- Store source.
- Observation timestamp.
- Source type.
- Historical GMP movement.
- Estimated premium percentage.
- Estimated listing price.
- Estimated listing gain.

Clearly label GMP as unofficial, unregulated and potentially unreliable.

Never combine GMP with official subscription data without identifying its unofficial status.

Never treat GMP as a guaranteed listing-price prediction.

Allow users to disable GMP completely.

## 11. IPO Bid Planner

Build an interactive bid calculator.

Inputs:

- IPO selection.
- Investor category.
- Available investment budget.
- Price band.
- Lot size.
- Number of lots.
- Bid price.
- Cut-off option where applicable.

Calculate:

- Minimum application amount.
- Amount per lot.
- Total application amount.
- Maximum lots within budget.
- Funds blocked.
- Potential listing gain/loss at configurable scenarios.
- Capital required for multiple IPO applications.

Show different scenarios for:
- Lower price band.
- Upper price band.
- Cut-off bidding.

Respect applicable investor-category eligibility and current regulatory limits.

Never submit an IPO application or authorize a payment.

The application is an analysis and planning tool only.

## 12. Allotment Probability Engine

Create a separate allotment probability estimation service.

Inputs should include:

- Category.
- Category-wise shares reserved.
- Valid application count, if available.
- Category-wise subscription.
- Lot size.
- Final issue structure.
- Historical allotment basis.

For retail oversubscribed IPOs, provide a transparent approximate lottery-based estimate where sufficient data exists.

Use valid application counts where available.

Do not assume subscription multiple alone gives exact allotment probability.

Support:
- Scenario-based probability estimates.
- Confidence level.
- Data completeness.
- Assumptions.
- Probability range.
- Historical comparison.

Clearly distinguish:

1. Allotment probability.
2. Investment attractiveness.
3. Expected listing outcome.

Never guarantee allotment.

Do not recommend multiple applications under the same PAN.

Do not claim that bidding for more retail lots necessarily improves allotment odds.

Use official published basis-of-allotment data to validate the model.

## 13. Allotment Tracker

Track the user's IPO applications manually.

Fields:

- IPO.
- Investor category.
- Application date.
- Application number.
- Bid price.
- Number of lots.
- Applied amount.
- UPI mandate status.
- Allotment status.
- Allotted quantity.
- Allotted amount.
- Refund / unblock status.
- Listing credit status.

Support:
- Applied.
- Mandate pending.
- Mandate approved.
- Rejected.
- Allotted.
- Partially allotted.
- Not allotted.
- Withdrawn.

Do not store UPI PINs, bank passwords or sensitive authentication credentials.

Provide registrar and official exchange links for checking actual application status.

## 14. IPO Performance Analytics

After listing, track:

- Issue price.
- Listing price.
- Listing gain/loss.
- Day-one high and low.
- Closing price on listing day.
- Current price.
- 1-week return.
- 1-month return.
- 3-month return.
- 6-month return.
- 1-year return.
- Maximum drawdown.
- Return versus benchmark.
- Return versus sector index.

Use existing market data providers for historical and current listed-stock prices.

Use TradingView Lightweight Charts for post-listing price charts.

Use Apache ECharts for IPO performance comparisons, return distributions and sector analytics.

Handle IPO listing dates and historical data availability correctly.

## 15. IPO Comparison

Allow users to compare multiple IPOs side by side.

Compare:

- Business sector.
- Issue size.
- Price band.
- P/E.
- P/B.
- Revenue growth.
- PAT growth.
- Debt.
- ROE.
- ROCE.
- Fresh issue versus OFS.
- Promoter holding.
- Peer valuation.
- Research score.
- Subscription.
- GMP, if enabled.
- Risk classification.

Include a comparison chart and a clear explanation of why one IPO scores higher than another.

## 16. IPO Watchlist and Alerts

Allow users to save IPOs to a personal watchlist.

Implement alerts for:

- New DRHP filing.
- New IPO announcement.
- IPO opening.
- IPO closing.
- Price band announcement.
- Subscription milestones.
- Allotment date.
- Listing date.
- Significant GMP change, if enabled.
- New RHP or prospectus.
- Major issue schedule revision.

Support in-app notifications and optional email alerts.

## 17. IPO Investment Journal

Allow users to record:

- IPO applied.
- Category.
- Number of lots.
- Application amount.
- Allotment result.
- Allotted quantity.
- Listing-day decision.
- Exit price.
- Realized P&L.
- Investment rationale.
- Post-investment review.

Generate personal IPO performance reports.

## 18. Technical Architecture

Integrate with the existing Django project.

Suggested modular structure:

ipo/
  models/
    ipo_issue.py
    ipo_document.py
    ipo_subscription.py
    ipo_valuation.py
    ipo_application.py
    ipo_allotment.py
    ipo_performance.py
  services/
    lifecycle.py
    subscription.py
    research.py
    valuation.py
    recommendation.py
    bidding.py
    allotment_probability.py
    performance.py
  providers/
    base.py
    nse.py
    bse.py
    sebi.py
    registrar.py
    third_party.py
  tasks/
    ingestion.py
    subscription_updates.py
    performance_updates.py
  views/
  api/
  forms/
  templates/
  tests/

Adapt to the project's existing conventions.

Use PostgreSQL, Celery and Redis according to the current architecture.

Use Apache ECharts for IPO dashboard analytics and TradingView Lightweight Charts for listed IPO price history.

## 19. Security and Data Quality

- Enforce authenticated access.
- Keep user application records private.
- Validate imported files.
- Protect against duplicate ingestion.
- Record audit history.
- Use source timestamps.
- Identify stale data.
- Handle conflicting source values.
- Protect uploaded documents.
- Avoid storing unnecessary sensitive financial information.
- Do not expose credentials or API keys in frontend code.

## 20. Implementation Roadmap

Implement incrementally:

Phase A:
- IPO master model.
- IPO lifecycle.
- Upcoming, live and closed IPO pages.
- Official source adapters.
- IPO calendar.

Phase B:
- Live subscription tracking.
- Historical subscription snapshots.
- IPO document management.
- Financial data extraction.

Phase C:
- Fundamental research.
- Valuation and peer comparison.
- IPO scoring and recommendations.

Phase D:
- Bid planner.
- Allotment probability estimator.
- Allotment tracker.

Phase E:
- Post-listing performance.
- IPO comparison.
- Watchlist and alerts.
- Investment journal.

Phase F:
- Advanced analytics.
- Historical backtesting of IPO scoring.
- Recommendation calibration and performance reporting.

Do not attempt to implement all phases in one uncontrolled change.

## 21. Testing Requirements

Create tests for:

- IPO lifecycle transitions.
- Duplicate issue ingestion.
- Data source conflicts.
- Subscription calculations.
- Category-wise subscription.
- Financial ratios.
- Valuation calculations.
- IPO score calculation.
- Missing financial information.
- Bid amount and lot calculations.
- Investor-category validation.
- Allotment probability edge cases.
- Allotment status changes.
- Listing return calculations.
- Corporate actions after listing, where applicable.
- User-specific application privacy.
- HTMX navigation.
- Chart rendering with missing data.

Test calculations using known reference examples.

## 22. Documentation and Final Report

Update:

- MASTER_SPECIFICATION_DJANGO.md
- ARCHITECTURE.md
- IMPLEMENTATION_STATUS.md
- DEVELOPMENT_PLAN.md
- README.md
- DATA_SOURCES.md

Document all source URLs, collection methods, permissions, rate limits and fallback behaviour.

First inspect the existing codebase and prepare an implementation plan with proposed database models, app boundaries, data sources and dependencies.

Then implement Phase A only.

After Phase A, run migrations, tests, data-quality checks and UI validation.

Report completed work, test results, source limitations and outstanding tasks.

STOP and wait for approval before Phase B.