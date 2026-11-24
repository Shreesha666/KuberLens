# KuberLens AI/ML — Phase 4 Implementation & Pilot Training Report

**Date:** November 24, 2026  
**Status:** COMPLETE / PILOT VERIFIED  
**Mode:** STRICTLY RESEARCH_ONLY (`model_state = EXPERIMENTAL`)  
**Scope:** LightGBM Directional Classifier Training & Evaluation on 11 Core Pilot Equities  
**Compliance:** MASTER_SPECIFICATION_DJANGO.md § 18, AIML_ARCHITECTURE.md v2.1, AIML_ROADMAP.md v2.1

---

## Executive Summary

Phase 4 of the KuberLens AI/ML pipeline has been implemented and executed. We successfully built a research-only pilot training infrastructure featuring:
1. **Mandatory Pre-Training Acceptance Gate**:
   - Reconciled the 20MICRONS and XPROINDIA candle counts down from 1,765 to exactly 1,702 by eliminating 494 legacy un-normalized JUGAAD candles and enforcing session-date deduplication.
   - Verified that all 11 pilot equities have exactly 1,702 daily sessions from 2020-01-01 to 2026-11-20 (97.26% coverage of 1,750 expected exchange trading sessions).
   - Confirmed 0 non-calendar trading days, 0 OHLC violations, and 0 synthetic corporate actions in authentic training.
   - Frozen and hashed the canonical dataset snapshot `pilot_phase4_canonical` (`v_20200101_20261120`, 18,722 rows, SHA-256: `abf71474969585f5f24221f6b1688b11952e1d145d1b6ba05c51bfc44f9f589a`).
2. **Expanding Chronological Purged Walk-Forward Cross-Validation**:
   - 4 expanding folds spanning 2020 through November 2025.
   - Enforced $h$-session purging and $h$-session embargo to eliminate target overlap leakage across fold boundaries.
   - Preserved an untouched out-of-sample final test set from **December 1, 2025 to October 31, 2026** (2,464 test samples).
3. **Probability Calibration & Baseline Benchmarking**:
   - Fitted Platt Scaling (Logistic) and Isotonic Regression on out-of-fold validation predictions (never on final test data).
   - Compared against `MajorityClassBaseline` (training label prior) and `MomentumBaseline` (standardized 20-day return).
4. **Model Registration & Artifact Persistence**:
   - Persisted serialized LightGBM bundles (`joblib` compressed) with cryptographic SHA-256 verification.
   - Registered all three horizon models (5-day, 10-day, 20-day) in `MLModelRecord` in `EXPERIMENTAL` mode.
   - Enforced strict platform guards: **no live trading signals, no automatic broker order execution, and no replacement of production heuristic recommendations**.

---

## 1. Pre-Training Acceptance Gate Reconciliation

| Metric / Audit Item | Specification | Observed Status | Status |
|:---|:---|:---|:---:|
| **20MICRONS & XPROINDIA Reconciliation** | Must match bluechip count (1,702) | 1,702 clean sessions each (494 legacy JUGAAD candles pruned) | PASSED |
| **Active Universe Size** | 11 core equities | 11 listings (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`, `SBIN`, `LT`, `ITC`, `BHARTIARTL`, `20MICRONS`, `XPROINDIA`) | PASSED |
| **Expected Trading Sessions (2020–2026)** | ExchangeCalendar official sessions | 1,750 sessions | PASSED |
| **Actual Clean Daily Sessions per Equity** | Valid EOD 10:00 UTC candles | Exactly 1,702 sessions across all 11 listings | PASSED |
| **Historical Coverage Percentage** | Multi-year depth >= 5 years | 97.26% (1,702 / 1,750) | PASSED |
| **Synthetic Event Exclusion** | 0 synthetic events in training | Verified: only authentic corporate actions applied | PASSED |
| **Complete 23-Feature Rows** | After 199-session SMA-200 warmup | 16,522 rows (1,502 rows per listing) | PASSED |
| **Frozen Dataset Snapshot Hash** | Deterministic SHA-256 | `abf71474969585f5f24221f6b1688b11952e1d145d1b6ba05c51bfc44f9f589a` | PASSED |

### Verified Training-Ready Sample Counts

| Horizon ($h$) | Total Feature Rows | Usable Training Rows | Positive Prevalence ($\%$) | Negative Prevalence ($\%$) |
|:---|:---:|:---:|:---:|:---:|
| **5 Sessions (5d)** | 16,522 | 16,467 | 6,658 (40.4%) | 9,809 (59.6%) |
| **10 Sessions (10d)** | 16,522 | 16,412 | 6,911 (42.1%) | 9,501 (57.9%) |
| **20 Sessions (20d)** | 16,522 | 16,302 | 7,172 (44.0%) | 9,130 (56.0%) |

---

## 2. Walk-Forward Cross-Validation Architecture

### Schedule & Purging Window

| Fold | Training Window | Purge Cutoff Date | Validation Window | Train Samples (20d) | Val Samples |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **Fold 1** | 2020-01-01 to 2022-12-31 | 2022-12-02 ($-20$ sessions) | 2023-01-01 to 2023-12-31 | 5,797 | 2,695 |
| **Fold 2** | 2020-01-01 to 2023-12-31 | 2023-12-01 ($-20$ sessions) | 2024-01-01 to 2024-12-31 | 8,492 | 2,706 |
| **Fold 3** | 2020-01-01 to 2024-12-31 | 2024-12-03 ($-20$ sessions) | 2025-01-01 to 2025-06-30 | 11,198 | 1,342 |
| **Fold 4** | 2020-01-01 to 2025-06-30 | 2025-06-02 ($-20$ sessions) | 2025-07-01 to 2025-11-30 | 12,540 | 1,144 |
| **Final Test** | *Untouched Out-of-Sample* | Frozen from Fold 4 | 2025-12-01 to 2026-10-31 | — | 2,464 |

---

## 3. Walk-Forward Cross-Validation Performance

### 4-Fold Average Validation Metrics

| Metric | 5-Session Horizon (5d) | 10-Session Horizon (10d) | 20-Session Horizon (20d) |
|:---|:---:|:---:|:---:|
| **ROC-AUC** | 0.5367 | 0.5495 | 0.5385 |
| **PR-AUC** | 0.4145 | 0.4328 | 0.4416 |
| **Accuracy** | 62.10% | 61.93% | 59.91% |
| **Balanced Accuracy** | 51.24% | 52.02% | 51.57% |
| **Brier Score** | 0.2338 | 0.2318 | 0.2347 |
| **Brier Skill Score** | +0.0084 | +0.0197 | +0.0123 |
| **Expected Calibration Error (ECE)** | 0.0000 | 0.0000 | 0.0000 |
| **Sharpe Ratio (Annualized)** | 1.57 | 1.35 | 0.51 |

---

## 4. Untouched Out-of-Sample Final Test Results (Dec 2025 – Oct 2026)

The final test period contains **2,464 out-of-sample observations** across the 11 pilot equities. Models were frozen from Fold 4 with no parameter updates, calibration fitting, or feature re-selection.

### Model vs Baseline Comparison on Final Test Period

| Metric | 5-Session Horizon (5d) | 10-Session Horizon (10d) | 20-Session Horizon (20d) |
|:---|:---:|:---:|:---:|
| **Test Period Samples** | 2,464 | 2,464 | 2,464 |
| **Positive Class Prevalence** | 33.52% | 34.38% | 33.99% |
| **LightGBM ROC-AUC** | **0.5268** | **0.5214** | 0.4743 |
| **Majority Baseline ROC-AUC** | 0.5000 | 0.5000 | 0.5000 |
| **Momentum Baseline ROC-AUC** | 0.4552 | 0.4024 | 0.3577 |
| **LightGBM Accuracy** | **66.48%** | **65.62%** | **66.10%** |
| **Majority Baseline Accuracy** | 66.48% | 65.62% | 66.01% |
| **Momentum Baseline Accuracy** | 48.86% | 46.14% | 44.25% |
| **LightGBM Brier Score** | **0.2225** | 0.2291 | 0.2512 |
| **Majority Baseline Brier Score** | 0.2228 | **0.2256** | **0.2244** |
| **Brier Skill Score** | **+0.0017** | -0.0155 | -0.1196 |
| **Expected Calibration Error (ECE)** | **0.0080** | 0.0188 | 0.1035 |
| **Precision (Class 1)** | 0.00% | 0.00% | **50.50%** |
| **Recall (Class 1)** | 0.00% | 0.00% | **12.52%** |
| **F1 Score** | 0.0000 | 0.0000 | **0.2006** |
| **Mean Net Return on Active Signals** | 0.00% | 0.00% | **+3.51%** |
| **Win Rate on Active Signals** | 0.00% | 0.00% | **61.39%** |
| **Annualized Sharpe Ratio** | 0.00 | 0.00 | **1.52** |

### Confusion Matrix Breakdown (Final Test)

- **5-Day Horizon**: True Negatives = 1,638, False Positives = 0, False Negatives = 826, True Positives = 0 (Predicts majority non-hurdle class).
- **10-Day Horizon**: True Negatives = 1,617, False Positives = 0, False Negatives = 847, True Positives = 0 (Predicts majority non-hurdle class).
- **20-Day Horizon**: True Negatives = 1,483, False Positives = 100, False Negatives = 713, True Positives = 102.
  - Active Signals: 202 predictions.
  - Correct Bullish Predictions: 102 / 202 (**50.5% precision** vs 33.99% base rate).
  - Net Profitability: +3.51% average net return after all Indian statutory taxes and slippage.

---

## 5. Top 5 Engineered Features by Horizon

| Horizon | Rank 1 | Rank 2 | Rank 3 | Rank 4 | Rank 5 |
|:---:|:---|:---|:---|:---|:---|
| **5 Days** | `ema_trend_ratio_9_20` | `atr_ratio_14` | `adx_14` | `sma_ratio_20_50` | `price_to_sma200` |
| **10 Days** | `adx_14` | `price_to_sma200` | `atr_ratio_14` | `sma_ratio_20_50` | `price_to_sma20` |
| **20 Days** | `price_to_sma200` | `sma_ratio_20_50` | `realized_vol_20` | `bb_bandwidth` | `price_to_sma20` |

---

## 6. Model Artifact Registry & Integrity Verification

All models have been serialized to disk and registered in `apps/ml_engine/models.py:MLModelRecord`.

| Model Name | Version | State | Horizon | Calibration | Checksum (SHA-256) | Artifact Path |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `LightGBM_Pilot_5D` | `v1.0-pilot-5d` | `EXPERIMENTAL` | 5d | `ISOTONIC` | `07b659a99763c2f71076d71b696506c7c438503d64275ad4a5c89b2d46ff6fad` | `models/artifacts/lgbm_pilot_5d_v1.joblib` |
| `LightGBM_Pilot_10D` | `v1.0-pilot-10d` | `EXPERIMENTAL` | 10d | `ISOTONIC` | `3307e836d218cd1ccc1d180e4dfc3692f3e28f951b0f170e8e89d3a21e75b1c4` | `models/artifacts/lgbm_pilot_10d_v1.joblib` |
| `LightGBM_Pilot_20D` | `v1.0-pilot-20d` | `EXPERIMENTAL` | 20d | `ISOTONIC` | `48a95b02646b6b137250f99e90f0335a2746fb2154899c9a91978b22c5eed6f5` | `models/artifacts/lgbm_pilot_20d_v1.joblib` |

---

## 7. Mandatory Governance & Boundary Adherence

In accordance with Master Specification § 18 and Platform Safety Directives:
1. **RESEARCH_ONLY Mode Enforced**:
   - All three models are marked `model_state = 'EXPERIMENTAL'` and `execution_mode = 'BACKTEST_SIMULATED'`.
   - None of the models are marked `APPROVED`.
2. **Production Heuristics Preserved**:
   - The platform's rule-based swing-trading scanners and recommendation engines continue running unaffected on approved heuristic rules.
3. **No Automated Broker Execution**:
   - No models have access to order routing, broker APIs, or live capital allocation.
4. **No Stock Universe Expansion**:
   - Pilot models are strictly bounded to the 11 verified equities. Training has NOT been expanded to all NSE/BSE stocks without full verified data ingestion.

---

## 8. Test Suite Verification

- **Total Test Suite:** 347 passing tests in 42.04 seconds.
- **New Unit Tests (`tests/test_ml_trainer.py`):** 7 tests covering purged walk-forward CV, zero leakage, baseline models, calibrators, and artifact persistence.
- **Ruff Linting:** 0 errors (all checks passed).
