# KuberLens — AI/ML Implementation Specification

**Document:** `IMPLEMENTATION_AIML.md`  
**Project:** KuberLens — Indian Equity Research & Decision-Support Platform  
**Version:** 1.0  
**Date:** 2026-11-24  
**Status:** Proposed extension to the existing Django implementation

> **IMPORTANT:** This document extends, and does not replace, `MASTER_SPECIFICATION_DJANGO.md`. Inspect the actual code and `IMPLEMENTATION_STATUS.md` before changing anything. Existing working features, models, migrations, interfaces, and data services must be reused. AI recommendations are research support, not guaranteed returns or autonomous trade instructions.

## 1. Objectives

Build a reproducible, testable AI/ML subsystem for NSE/BSE equities that can:

1. Estimate probabilities of forward price movement at 5, 10 and 20 trading-session horizons.
2. Provide experimental return/price forecasts separately from classification signals.
3. Combine validated model outputs with technical, fundamental, regime and risk signals.
4. Explain `BUY`, `HOLD`, `SELL`, `AVOID`, or `INSUFFICIENT_DATA` assessments in context.
5. Analyze existing holdings separately from potential new investments and swing-trading candidates.
6. Backtest using point-in-time information and realistic Indian market costs.
7. Monitor data quality, model performance, calibration, drift and operational failures.

**Out of scope initially:** guaranteed profit predictions, high-frequency trading, live broker order execution, and training large language models from scratch.

## 2. Integration and source-of-truth rules

Priority for interpreting the existing application:

1. Existing runtime code and migrations — what is actually implemented.
2. `MASTER_SPECIFICATION_DJANGO.md` — overall architecture and product intent.
3. `IMPLEMENTATION_STATUS.md` — recorded progress; verify against code.
4. This document — AI/ML extension requirements.

If these conflict, document the discrepancy and propose a minimally disruptive resolution before modifying code. Never silently recreate an existing app, table, service, or feature. Preserve the existing persistent Django template shell, sidebar, HTMX partial updates, and styling.

## 3. Technology choices

| Layer | Preferred choice | Notes |
|---|---|---|
| Application | Existing Django project | Keep modular-monolith architecture |
| Async work | Existing Celery + Redis | Training and batch inference outside request cycle |
| Storage | Existing PostgreSQL | Reuse instrument/market tables; migrations only when needed |
| Data analysis | pandas, NumPy | Pin compatible versions |
| Indicators | Existing technical-analysis code | Avoid duplicate indicator implementations |
| First supervised model | LightGBM | Strong tabular baseline; validate empirically |
| Challenger models | XGBoost, scikit-learn Random Forest | Add only after baseline validation |
| Forecasting research | Amazon Chronos-2 | Optional; distinct prediction type and evaluation |
| Model tracking | Existing registry or MLflow | Choose after repository audit |
| Frontend | Existing Django Templates + HTMX | No full frontend rewrite |
| Broker integration | Existing Zerodha adapter if present | Read-only initially; never place orders |

**Licensing:** Check the license of each repository, distributed model weights, datasets, and upstream market-data provider separately before commercial use or redistribution. Open-source code does not automatically grant rights to market data.

## 4. Mandatory first action: repository audit

Before implementation, Google Antigravity must inspect:

- Django apps, URL configuration, service interfaces, templates, APIs and tests.
- Market/instrument identifiers, historical OHLCV models, data providers, caching and freshness metadata.
- Technical/fundamental calculations and their timestamp semantics.
- Holdings, portfolio, swing scanner, backtesting and risk-related features.
- Existing `ai_analysis`, `ml_engine`, Celery, Redis, model tracking and background jobs.
- Migrations, dependency manifests, secrets/configuration and deployment setup.

Create `docs/AIML_GAP_ANALYSIS.md`, classifying requirements as `IMPLEMENTED`, `PARTIAL`, `MISSING`, or `BLOCKED`, with evidence (file paths and functions/classes), dependencies, risks and proposed reuse. **Do not change application code in the audit phase.**

## 5. Proposed logical architecture

```text
NSE/BSE Data Sources / Existing Market Providers
                     |
           Market Data Validation
                     |
          Historical Dataset Builder
                     |
           Feature / Label Pipeline
                     |
       Versioned Train / Validate / Test
                     |
           Model Training & Registry
                     |
        Scheduled Prediction / Inference
                     |
      Calibrated Signals + Forecast Outputs
                     |
 Technical + Fundamental + Regime + Liquidity
                     |
             Independent Risk Engine
                     |
       Explainable Decision-Support Engine
                     |
      Stock / Portfolio / Swing Trading UI
```

**Responsibilities (adapt to actual code):**

- `ml_engine`: datasets, feature/label definitions, training, experiments, registry, inference, evaluation, drift.
- `ai_analysis`: evidence aggregation, calibrated prediction interpretation, recommendations, explanations, risk-gated output.
- Existing `market`, `instruments`, `technical_analysis`, `fundamental_analysis`, `portfolio`, `holdings`, `trading`, `backtesting`: authoritative domain logic.
- Existing Celery tasks: dataset refresh, feature computation, inference, retraining and monitoring.

Avoid circular imports; use explicit service interfaces and shared immutable prediction schemas.

## 6. Market data requirements

### 6.1 Instruments and identity

- Use stable exchange + instrument identifiers; support NSE/BSE listings and symbol changes.
- Keep trading calendars, holidays, splits, bonuses, dividends and delistings explicit.
- Preserve source and adjustment metadata; never silently mix adjusted and unadjusted prices.
- Support historical constituent universes where available; document survivorship limitations.

### 6.2 Minimum OHLCV schema

`instrument_id`, `exchange`, `session_date`, `open`, `high`, `low`, `close`, `volume`, `adjustment_policy`, `provider`, `ingested_at`, `quality_status`, and relevant freshness fields.

### 6.3 Data quality

Validate uniqueness, monotonic session dates, OHLC consistency, nonnegative volume, missing sessions, duplicate candles, suspicious price jumps and corporate-action alignment. Quarantine suspect records. Track dataset snapshots with reproducible query/config hashes and coverage dates.

### 6.4 Data providers

Reuse existing providers. Jugaad-Data and yfinance may be candidates for historical research/fallback, but verify current availability, terms, adjustments and completeness. Broker-authorized data may supplement research; do not assume free public sources provide licensed real-time exchange data.

Never display delayed/EOD observations as real-time. Preserve `source_type` and `freshness_status` metadata throughout the pipeline.

## 7. Features and target definitions

### 7.1 Initial features

- Returns: 1, 5, 10, 20 sessions; log returns where appropriate.
- Trend: SMA/EMA 20, 50, 200; distance to averages; crossovers.
- Momentum: RSI 14, MACD, rate of change, relative strength.
- Volatility: ATR 14, rolling realized volatility, Bollinger width.
- Volume/liquidity: relative volume, turnover, rolling volume averages.
- Market context: NIFTY 50 direction/volatility and sector-relative performance.
- Fundamentals (later): only point-in-time values known by prediction date, including disclosure/publication timestamps.

Every feature must have a declared lookback, input source, availability timestamp, missing-value rule and version. Reuse existing indicator services.

### 7.2 Prediction horizons

Start with **5, 10 and 20 trading sessions**. Define targets explicitly, e.g. whether future adjusted return exceeds a configurable threshold. Optionally add triple-barrier labels later, with clear stop/take-profit/horizon rules.

Avoid leakage: never use future candles, restated fundamentals before publication, future index constituents, or global normalization fit on test data. Features computed at the close can only be acted upon at the next executable time under the backtest's fill assumptions.

## 8. Training pipeline

1. Select eligible instruments and an as-of dataset snapshot.
2. Validate historical coverage and point-in-time feature availability.
3. Construct features and targets; exclude incomplete future labels.
4. Split chronologically; use walk-forward validation and purging/embargo where label windows overlap.
5. Train a simple baseline (e.g. constant-rate, momentum rule or logistic regression).
6. Train **LightGBM first**; compare against baseline.
7. Tune hyperparameters only within training/validation windows.
8. Calibrate probabilities on a separate calibration window where practical.
9. Evaluate once on untouched out-of-sample periods.
10. Save artifact, feature schema, dataset snapshot, configuration, code revision and metrics.

Do not claim a model is useful based solely on accuracy. Evaluate precision/recall, PR-AUC or ROC-AUC as appropriate, Brier score, calibration curves, cross-sectional ranking quality, performance by regime, stability and post-cost strategy results.

**Retraining:** Start with a configurable monthly cadence, subject to evidence. Daily batch inference may run after validated EOD data arrives. Do not automatically promote newly trained models.

## 9. Model registry and inference contracts

Store model ID/version, algorithm, horizon, target definition, training interval, validation interval, feature schema hash, dataset version, artifact URI, metrics, calibration method, approval state and deployment timestamp.

Recommended model states: `EXPERIMENTAL`, `VALIDATED`, `PAPER_TRADING`, `APPROVED`, `RETIRED`, `FAILED`.

Prediction output should include:

```json
{
  "instrument_id": "example-instrument-id",
  "exchange": "NSE",
  "as_of_session": "YYYY-MM-DD",
  "horizon_sessions": 10,
  "model_id": "lightgbm-direction-v1",
  "model_version": "1.0.0",
  "target_definition": "positive_forward_return",
  "probability": null,
  "calibration_status": "UNAVAILABLE",
  "data_freshness": "EOD",
  "quality_status": "PENDING",
  "generated_at": "ISO-8601 timestamp"
}
```

Values are illustrative; `probability` must be computed and calibrated, never fabricated. Make inference idempotent for the same instrument, model version, horizon and as-of session.

## 10. Advanced models and Chronos-2

After LightGBM is validated:

- Add XGBoost as a supervised challenger and Random Forest as a simpler benchmark.
- Integrate Chronos-2 as an **experimental time-series forecasting adapter**, not as an automatic buy/sell classifier.
- Evaluate forecast accuracy against naive/random-walk baselines across horizons and regimes.
- Record forecast quantiles/intervals and numerical forecast units explicitly.
- Do not average Chronos price forecasts with classifier probabilities as if they share a scale.
- Check runtime hardware, memory, weight licensing and model download/deployment constraints.

FinRL/reinforcement learning may be researched later, but is **not required for the initial production decision-support workflow**.

## 11. Ensemble and decision-support engine

A decision must combine validated evidence without disguising uncertainty. Candidate inputs:

- Calibrated supervised probabilities.
- Forecast evidence (only when validated and transformed into comparable, justified features).
- Technical indicators and price structure.
- Fundamental evidence and its disclosure freshness.
- Market/sector regime.
- Liquidity and volatility.
- Portfolio concentration, position size and risk constraints.

If using initial heuristic weights, label them as **configurable experimental defaults**, not optimized or statistically proven. Validate and recalibrate any weighted score before use.

Output states: `BUY`, `HOLD`, `SELL`, `AVOID`, `INSUFFICIENT_DATA`.

For existing holdings, consider cost basis, concentration, holding period and risk; for new positions, consider entry criteria; for swing trading, consider signal horizon, stop/invalidation and liquidity. These are distinct contexts and must not share identical rules by default.

### 11.1 Independent risk veto

A risk gate may suppress or downgrade recommendations when:

- Data is stale, incomplete or inconsistent.
- The model is unvalidated, uncalibrated or degraded.
- Liquidity is insufficient or volatility exceeds policy.
- Portfolio concentration or exposure limits would be breached.
- The instrument is under relevant trading restrictions or cannot be priced reliably.

Risk checks are deterministic, separately testable and auditable. A model cannot override a risk veto.

### 11.2 Explainability

Show top supporting/opposing factors, data timestamp, horizon, model version, calibration state, applicable risk warnings and the reasons behind any veto. Use SHAP or similar feature explanations only where appropriate and clearly distinguish model explanations from causal claims.

## 12. Backtesting and evaluation

Reuse the existing backtesting engine. Require:

- Chronological walk-forward testing and out-of-sample evaluation.
- Explicit next-bar execution assumptions and no future data.
- Corporate actions, tradability, market holidays and survivorship limitations.
- Realistic India-specific costs: brokerage, STT, exchange/SEBI charges, GST, stamp duty, DP charges where applicable, slippage and spread.
- Turnover, maximum drawdown, Sharpe/Sortino where valid, win rate, average return, profit factor, hit rate, calibration and benchmark comparisons.
- Stress tests across market regimes, liquid/illiquid instruments and data outages.

Report predictive quality **separately** from simulated trading profitability. Include transaction-cost assumptions and limitations prominently. Require paper trading before operational promotion.

## 13. Proposed persistence model (adapt; do not duplicate)

Create tables only when not already covered by existing models:

| Logical entity | Core purpose |
|---|---|
| `MLDatasetSnapshot` | Data window, universe, version, coverage and quality |
| `MLFeatureDefinition` | Feature name, parameters, lookback, version and timing |
| `MLTrainingRun` | Parameters, data/code versions, status, metrics and logs |
| `MLModelVersion` | Model metadata, artifact path, approval and rollback |
| `MLPrediction` | Instrument, horizon, as-of time, output and freshness |
| `MLEvaluationRun` | Walk-forward folds, metrics, costs and benchmark |
| `AIDecision` | Recommendation, evidence, veto, rationale and context |
| `MLMonitoringEvent` | Drift, data-quality, inference failure and alerts |

Add indexes for instrument/date/horizon/model and unique constraints to prevent duplicate predictions. Define retention, artifact access and migration plans.

## 14. Services, APIs and UI

Reuse existing routes and HTMX partial patterns. Candidate service interfaces:

- `DatasetBuilder.build(as_of, universe, config)`
- `FeaturePipeline.transform(dataset_version, feature_version)`
- `TrainingService.train(model_config, dataset_version)`
- `ModelRegistry.get_approved(horizon)`
- `PredictionService.predict(instrument_id, as_of, horizon)`
- `DecisionEngine.assess(instrument_id, context, as_of)`
- `RiskEngine.evaluate(context, signals)`
- `EvaluationService.backtest(model_version, strategy_config)`

Suggested UI locations:

1. Stock detail: horizon-specific signal, evidence, freshness, model/version and risk.
2. Holdings: hold/sell/trim/review assessment contextualized by actual portfolio exposure.
3. Swing scanner: ranked validated candidates with liquidity/risk gates.
4. AI/ML overview: model health, latest inference, evaluation and paper-trading status.
5. Model detail: metrics, calibration, training window, dataset and limitations.

Always show `LOADING`, `STALE_DATA`, `MODEL_UNAVAILABLE`, `INSUFFICIENT_DATA` and `ERROR` states rather than inventing a recommendation.

## 15. Celery scheduling and operational behavior

Suggested logical tasks (reuse existing task names/services if present):

- `refresh_market_history`
- `validate_market_dataset`
- `build_aiml_features`
- `run_eod_predictions`
- `evaluate_model_performance`
- `train_candidate_models`
- `monitor_data_and_model_drift`

Tasks must be idempotent, retry-safe, observable and guarded against concurrent conflicting runs. Never run expensive model training synchronously in an HTTP request. Prevent incomplete EOD candles from triggering inference.

## 16. Security, audit and reliability

- Never commit broker tokens, credentials or model storage secrets.
- Restrict training, model approval and rollback to authorized administrators.
- Audit dataset/model versions, prediction timestamps and decision outputs.
- Validate external inputs; isolate serialized model artifacts from untrusted sources.
- Track memory/CPU/GPU consumption and task timeouts.
- Provide safe fallback when models or market-data providers fail.
- Do not enable automated order placement in this implementation.

## 17. Phased delivery plan

| Step | Scope | Required acceptance evidence |
|---|---|---|
| 1 | Repository audit | `docs/AIML_GAP_ANALYSIS.md`; no code changes |
| 2 | Integration architecture | `docs/AIML_ARCHITECTURE.md`, `docs/AIML_ROADMAP.md`; approved boundaries |
| 3 | Historical data foundation | Validated datasets, reproducible snapshots, tests |
| 4 | Feature/label engineering | Timestamp-safe features, label tests, no leakage |
| 5 | First LightGBM model | Reproducible training, baseline, registry, calibration |
| 6 | Evaluation/backtesting | Walk-forward report, realistic costs, risk analysis |
| 7 | Decision/risk engine | Explainable contextual outputs, deterministic veto tests |
| 8 | Dashboard integration | Stock/portfolio/swing UI, states and integration tests |
| 9 | Advanced models | Independently validated XGBoost/RF/Chronos adapters |
| 10 | Automation/monitoring | Scheduled inference, alerts, drift, rollback, runbooks |

**Gate:** Complete and review each step before starting the next. Skip work already implemented and verified in the actual repository. Do not deploy experimental models as approved decision signals.

## 18. Testing and definition of done

Minimum tests:

- OHLCV validation and adjustment correctness.
- Feature values, lookback warm-up and as-of timestamps.
- Leakage checks, chronological splits and label overlap.
- Deterministic training with fixed seed/config where feasible.
- Model serialization, registry, compatibility and rollback.
- Calibration and benchmark evaluation.
- Prediction idempotency, stale data and missing models.
- Risk veto and contextual recommendation logic.
- Backtest transaction costs and execution timing.
- Django routes, HTMX partials, permissions and Celery task failures.

A phase is complete only when relevant tests pass, documentation and `IMPLEMENTATION_STATUS.md` are updated, and a concise report lists changed files, migrations, commands executed, results, limitations and next steps.

## 19. Instructions to Google Antigravity

### First prompt — run once

```text
You are integrating AI/ML into my EXISTING KuberLens Django application.

Read MASTER_SPECIFICATION_DJANGO.md, IMPLEMENTATION_STATUS.md,
and IMPLEMENTATION_AIML.md, then inspect the actual source code.

DO NOT implement AI/ML yet.

Create docs/AIML_GAP_ANALYSIS.md with file-level evidence for existing,
partial, missing and blocked requirements. Identify reusable services,
architecture conflicts, dependencies and data risks.

Do not replace the master specification, recreate existing Django apps,
redesign the UI, modify migrations or overwrite working code.

Present the gap analysis and wait for my approval.
```

### Second prompt — after reviewing the audit

```text
Using the approved AIML_GAP_ANALYSIS.md, create
 docs/AIML_ARCHITECTURE.md and docs/AIML_ROADMAP.md.

Preserve existing app boundaries and infrastructure. Reuse current
market, technical, fundamental, holdings, portfolio, backtesting,
Celery and HTMX services wherever possible.

Specify model/data contracts, migration requirements, tests, risk controls,
and acceptance criteria for each incremental phase.

Do not write application code yet. Wait for approval.
```

### Reusable phase execution prompt

```text
Implement ONLY the next approved phase in docs/AIML_ROADMAP.md.

Before editing, list existing reusable components and files to change.
Implement the smallest compatible change. Add tests and migrations only
when necessary. Run relevant tests and fix failures.

Do not implement later phases or rewrite completed functionality.
Update IMPLEMENTATION_STATUS.md and relevant AI/ML documentation.

Report changed files, executed commands, test results, unresolved issues,
and the proposed next phase. Stop for review.
```

## 20. Reference repositories

These are implementation/research references, **not proof of NSE/BSE-trained profitable models**:

- LightGBM — https://github.com/microsoft/LightGBM
- XGBoost — https://github.com/dmlc/xgboost
- scikit-learn — https://github.com/scikit-learn/scikit-learn
- Chronos forecasting — https://github.com/amazon-science/chronos-forecasting
- FinRL — https://github.com/AI4Finance-Foundation/FinRL
- MLflow — https://github.com/mlflow/mlflow
- Jugaad-Data — https://github.com/jugaad-py/jugaad-data
- yfinance — https://github.com/ranaroussi/yfinance

Check repository and model-weight licenses, model cards, provider terms and version compatibility at integration time.

---

**Recommended immediate action:** Place this file in the project root and execute only the **First prompt** in Section 19. Review the generated gap analysis before writing AI/ML code.
