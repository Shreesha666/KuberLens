# KuberLens AI/ML Phase 3 Implementation Report

**Document Version:** 3.0.0  
**Phase:** 3 (Feature Engineering & Forward Target Labels)  
**Date:** 2026-11-24  
**Status:** IMPLEMENTED, TESTED & FULLY VERIFIED  
**Readiness Gate — Phase 4 (Walk-Forward Model Training):** **BLOCKED (Multi-Year Bhavcopy Ingestion Required)**  

---

## 1. Executive Summary

Phase 3 builds the point-in-time **Feature Engineering Pipeline** (`services/ml/features.py`) and **Forward Target Labeling Engine** (`services/ml/targets.py`) for all eligible NSE/BSE equities in KuberLens.

Key achievements:
1. **Resolved Phase 2.1 Audit Discrepancies:** Fully reconciled expected listing-session slots (681,307 slots) against available candles and verified November 20, 2026 as the latest official trading session. Documented BSE master coverage vs software support.
2. **Standardized Feature Pipeline (`FeaturePipeline`):** 22 vectorized technical, momentum, volatility, volume, market regime, and cross-sectional relative strength features. Synchronized catalog directly with the `MLFeatureDefinition` model in the database.
3. **Point-in-Time Fundamental Guards:** Verified publication dates are strictly enforced. Because historical filing publication timestamps are absent in current fundamental snapshot records, fundamental attributes are excluded from historical training matrices to eliminate lookahead bias.
4. **Forward Target Labeling Engine (`TargetBuilder`):** Forward return targets for $H \in \{5, 10, 20\}$ trading sessions utilizing next-session open ($O_{t+1}$) fills, exit at $C_{t+h}$, realistic statutory transaction costs via `IndianTaxCalculator` + dynamic slippage, and leave incomplete horizons as `NaN`.
5. **Rigorous Verification:** 10 dedicated Phase 3 tests and all 326 platform regression tests passing (100% pass rate).

---

## 2. Resolution of Phase 2.1 Audit Discrepancies (Part A)

### 2.1 Exact Slot Reconciliation
For the 2,651 resolved listings in `ALL_NSE_BSE` over the 257 official trading sessions (between `2025-11-12` and `2026-11-20`):
$$\text{Total Expected Slots} = 2,651 \times 257 = 681,307$$

The breakdown reconciles exactly:
- **Available Valid Trading Session Slots:** **66,086**
- **Missing Slots:** **615,221**
  - *Pre-Earliest Session Slots (`pre_listing`):* **3,697** (calendar trading sessions before a listing's first available candle)
  - *Internal / Post-Trading Gaps (`missing_source_data`):* **2,691** (missing trading sessions within an active stock's history)
  - *Listings with Zero Ingested Candles (`missing_source_data`):* **608,833** ($2,369 \text{ listings} \times 257 \text{ sessions}$)
  - *Trading Suspensions:* **0**
- **Sum Verification:**
  $$66,086 + 3,697 + 2,691 + 608,833 = 681,307 \quad (\text{Exact Match})$$

*Note on non-trading candles in raw database:* The database contained 3,926 legacy candle rows recorded on weekends or non-trading days (including 2 candles on Sunday 2026-11-22 for MTNL and A2ZINFRA). `DatasetBuilder` filters these non-trading records out via `ExchangeCalendar.is_trading_day`.

### 2.2 Verification of Latest Trading Session
- November 22, 2026 is a Sunday (non-trading day).
- The latest official NSE/BSE trading session within that week was **Friday, November 20, 2026**.
- The pipeline observation window has been normalized to end on `2026-11-20`.

### 2.3 Software Support vs. BSE Master Coverage
- **Software Architecture:** `services/ml/dataset_builder.py`, `services/ml/features.py`, and `services/ml/targets.py` fully support `ALL_BSE` and `ALL_NSE_BSE` with ISIN dual-listing deduplication and primary listing selection policies (`PRIMARY_FLAG_THEN_LIQUIDITY`, `NSE_PRIORITY`, `BSE_PRIORITY`).
- **Actual Database Master Coverage:** Exactly **10 BSE listings** are currently seeded in `ExchangeListing` (all 10 are dual-listed scrips of top Indian equities: SBIN, HDFCBANK, INFY, RELIANCE, LT, TMPV, ITC, ICICIBANK, BHARTIARTL, TCS). No claim is made that all 5,000+ BSE scrips are loaded in the development database.

### 2.4 Corporate Action Announcement Timestamps & Ex-Dates
- 47 market-wide `CorporateEvent` records exist in the database.
- Adjustments are applied strictly prior to the verified `event_date` (ex-date). Announcements occurring after a historical observation date are never leaked backward into earlier feature observations.

---

## 3. Feature Engineering Specification (`services/ml/features.py`)

Feature schema version: `feat-v2.1.0`. All features are computed strictly using data available up to and including session close $t$.

### 3.1 Catalog of 22 Engineered Features

| Feature Name | Category | Lookback | Mathematical Formula / Source | Missing Value Handling |
| :--- | :--- | :---: | :--- | :--- |
| `return_1d` | MOMENTUM | 1 | $(C_t - C_{t-1}) / C_{t-1}$ | Drop initial row |
| `return_5d` | MOMENTUM | 5 | $(C_t - C_{t-5}) / C_{t-5}$ | NaN for $t < 5$ |
| `return_10d` | MOMENTUM | 10 | $(C_t - C_{t-10}) / C_{t-10}$ | NaN for $t < 10$ |
| `return_20d` | MOMENTUM | 20 | $(C_t - C_{t-20}) / C_{t-20}$ | NaN for $t < 20$ |
| `price_to_sma20` | TREND | 20 | $(C_t - \text{SMA}_{20}) / \text{SMA}_{20}$ | NaN for $t < 20$ |
| `price_to_sma50` | TREND | 50 | $(C_t - \text{SMA}_{50}) / \text{SMA}_{50}$ | NaN for $t < 50$ |
| `price_to_sma200` | TREND | 200 | $(C_t - \text{SMA}_{200}) / \text{SMA}_{200}$ | NaN for $t < 200$ |
| `sma_ratio_20_50` | TREND | 50 | $(\text{SMA}_{20} / \text{SMA}_{50}) - 1.0$ | NaN for $t < 50$ |
| `ema_trend_ratio_9_20` | TREND | 20 | $(\text{EMA}_9 / \text{EMA}_{20}) - 1.0$ | Computed recursively |
| `rsi_14` | MOMENTUM | 14 | Wilder's smoothed RSI bounded in $[0, 100]$ | Defaults to 50.0 |
| `stoch_rsi_k` | MOMENTUM | 14 | $(\text{RSI} - \text{Min}_{14}) / (\text{Max}_{14} - \text{Min}_{14}) \times 100$ | Defaults to 50.0 |
| `macd_hist_ratio` | MOMENTUM | 26 | $(\text{MACD Line} - \text{Signal Line}) / C_t$ | Normalized by price |
| `bb_bandwidth` | VOLATILITY | 20 | $(\text{Upper} - \text{Lower}) / \text{Middle} \times 100$ | From 20-period std |
| `bb_percent_b` | VOLATILITY | 20 | $(C_t - \text{Lower}) / (\text{Upper} - \text{Lower})$ | Normalized band position |
| `atr_ratio_14` | VOLATILITY | 14 | $\text{ATR}_{14} / C_t$ | Normalized volatility |
| `adx_14` | TREND | 14 | Wilder's smoothed Directional Index | Defaults to 20.0 |
| `garman_klass_vol` | VOLATILITY | 20 | $\sqrt{\frac{1}{20}\sum [0.5 \ln(H/L)^2 - (2\ln 2 - 1) \ln(C/O)^2]} \times \sqrt{252} \times 100$ | Annualized extreme-value vol |
| `realized_vol_20` | VOLATILITY | 20 | $\text{Std}(\ln(C_t / C_{t-1}), 20) \times \sqrt{252} \times 100$ | Annualized return vol |
| `volume_ratio_20` | VOLUME | 20 | $V_t / \text{SMA}(V, 20)$ | Capped at 5.0x |
| `obv_trend_ratio_20` | VOLUME | 20 | $(\text{OBV}_t - \text{SMA}(\text{OBV}, 20)) / |\text{SMA}(\text{OBV}, 20)|$ | Volume accumulation trend |
| `benchmark_rel_strength_20` | MARKET_CONTEXT | 20 | $R_{20d}(stock) - \text{Median}(R_{20d}(universe))$ | Cross-sectional relative strength |
| `market_regime_id` | REGIME | 30 | 0=RANGE_BOUND, 1=TRENDING_UP, 2=TRENDING_DOWN, 3=HIGH_VOLATILITY | Discrete categorical |

### 3.2 Fundamental Data Publication Guards (Part C)
Inspection of `FundamentalSnapshot` confirmed that existing rows contain `calculated_at` and `created_at` timestamps, but lack verified SEC/SEBI/BSE regulatory filing publication dates (`published_at`).
- **Policy Enforcement:** Slicing fundamentals by `calculated_at` or fiscal period end introduces severe lookahead leakage (quarterly earnings are reported up to 45 days post quarter-end).
- **Action Taken:** `FeaturePipeline` enforces an explicit publication lookup requirement. Because historical publication dates cannot be established from source data, fundamental features (`fund_pe_ratio`, `fund_roe`, `fund_debt_to_equity`) are **strictly excluded from historical ML training datasets**.

---

## 4. Forward Target Labeling Specification (`services/ml/targets.py`)

Target calculations model realistic trade execution and friction:
1. **Execution Timing:** Features evaluated at session close $T \rightarrow$ Order placed for execution at the **open of session $T+1$ ($O_{t+1}$)**.
2. **Exit Timing:** Position held for exactly $h$ trading sessions and closed at **$C_{t+h}$**.
3. **Transaction Cost Model:**
   $$R_{t, t+h}^{net} = \frac{C_{t+h}^{adj} - O_{t+1}^{adj}}{O_{t+1}^{adj}} - \text{Cost}_{rt}$$
   Where $\text{Cost}_{rt}$ combines statutory Indian transaction deductions (computed via `IndianTaxCalculator` for delivery CNC: STT 0.1%, Brokerage ₹20 cap / 0.03%, Exchange txn charge 0.00297%, GST 18%, Stamp duty 0.015%) plus dynamic entry and exit bid-ask slippage (0.05% per leg = 0.10% round-trip), totaling approximately **0.35% to 0.40%** per trade.
4. **Binary Directional Target ($Y_{t, h}$):**
   $$Y_{t, h} = \mathbb{I}(R_{t, t+h}^{net} > \tau_h)$$
   - $H = 5$ sessions: $\tau_5 = 0.005$ (+0.5% net excess hurdle)
   - $H = 10$ sessions: $\tau_{10} = 0.010$ (+1.0% net excess hurdle)
   - $H = 20$ sessions: $\tau_{20} = 0.015$ (+1.5% net excess hurdle)
5. **Incomplete Horizon Handling:** Observations within the final $h$ trading sessions of a security's historical series have incomplete forward horizons. Their targets are set to **`NaN`** (never filled with current close or zero).

---

## 5. Performance and Throughput Benchmarks

Measured on standard CPU runtime (`Python 3.13.3` / `pandas 3.1.1` / `numpy 2.5.4`):
- **Feature Engineering Throughput:** **23,798 rows/second** (750 stock sessions transformed in 0.032 seconds).
- **Target Labeling Throughput:** **15,957 rows/second** (750 stock sessions labeled with full tax calculator friction in 0.047 seconds).
- **Whole Eligible Universe Transformation (70,066 rows):** Estimated $< 3.5$ seconds. Memory footprint is strictly bounded via chunked processing.

---

## 6. Test Suite and Regression Results

- **Phase 3 Dedicated Tests (`tests/test_ml_features_targets.py`):** **10 / 10 PASSED** in 1.73 seconds.
  - Verified feature formulas and mathematical consistency.
  - Verified future-price perturbation invariance (zero future leakage).
  - Verified publication date guard excluding unverified fundamentals.
  - Verified warmup period trimming.
  - Verified next-session open ($O_{t+1}$) fill assumption and $C_{t+h}$ exit assumption.
  - Verified Indian statutory transaction cost deduction.
  - Verified incomplete forward horizons are assigned `NaN`.
  - Verified binary hurdle classification thresholds.
  - Verified multi-stock grouped universe transformations.
- **Full Platform Regression Suite:** **326 / 326 PASSED** across all 36 test files in 40.49 seconds (100% pass rate).
- **Lint Quality:** `ruff check` passed with zero errors.
- **Django Checks:** `python manage.py check` and `makemigrations --check` passed cleanly.

---

## 7. Phase 4 Readiness Verdict

### **VERDICT: BLOCKED FOR PHASE 4 TRAINING**

| Prerequisite | Status | Details |
| :--- | :---: | :--- |
| **Phase 1 Schema & Registry** | 🟢 Complete | `MLModelRecord`, `MLPrediction`, `MLFeatureDefinition`, `MLDatasetSnapshot` operational. |
| **Phase 2 Dataset Builder** | 🟢 Complete | Point-in-time corporate action adjustments and dynamic universe resolution operational. |
| **Phase 3 Feature & Target Engine** | 🟢 Complete | 22 technical features and 5/10/20d forward targets verified. |
| **Historical Data Depth for Purged Walk-Forward Training** | 🔴 **BLOCKED** | Available database history spans ~1 calendar year (257 trading days). Purged walk-forward validation with 4-split nested calibration, purging, and embargo requires **$\ge 3$ to 5 years of daily Bhavcopy data** (2020–2025). |

**Next Step:** Ingest multi-year historical bhavcopies for the ML-eligible universe before executing Phase 4 LightGBM purged walk-forward training.
