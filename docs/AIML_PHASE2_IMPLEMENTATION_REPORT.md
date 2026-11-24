# AI/ML Phase 2 Implementation Report: Historical Dataset Builder & Corporate Action Adjustment

**Document:** `docs/AIML_PHASE2_IMPLEMENTATION_REPORT.md`  
**Phase:** Phase 2 — Historical Dataset Builder & Corporate Action Adjustment  
**System:** KuberLens (Indian Stock Market Research & Intelligence Platform)  
**Executed Date:** 2026-11-24  
**Status:** 🟢 **COMPLETED & VERIFIED (READY FOR PHASE 3)**  

---

## 1. Executive Summary

Phase 2 implements the point-in-time historical dataset extraction, data quality validation, and corporate-action adjustment engine for KuberLens. It establishes a reproducible pipeline for extracting multi-asset OHLCV time-series, separating raw execution prices from adjusted research prices, validating OHLC integrity, detecting missing and duplicate trading sessions, and applying verified split and bonus adjustments without lookahead leakage.

All requirements of Phase 2 as specified in `docs/AIML_ROADMAP.md` (v2.1) and `docs/AIML_ARCHITECTURE.md` (v2.1) have been implemented, verified with unit tests, and validated against the local production-grade SQLite database:
1. **Core Service (`services/ml/dataset_builder.py`):** Implemented `CorporateActionAdjuster`, `DataQualityValidator`, and `DatasetBuilder`.
2. **CLI Management Command (`apps/ml_engine/management/commands/build_ml_dataset.py`):** Implemented options for `--start-date`, `--end-date`, `--exchange`, `--universe`, `--snapshot-name`, and `--dry-run`.
3. **Point-in-Time Corporate Action Adjustment:** Market-wide corporate events are sliced strictly from `apps.news.models.CorporateEvent` where `event_date <= as_of_date`. Future corporate actions are strictly excluded to prevent lookahead bias.
4. **Tested Mathematical Multiplier Conventions:** Verified support for 5-for-1 splits ($f=0.20$), 1:1 bonuses ($f=0.50$), 3:1 bonuses ($f=0.25$), and general $A:B$ bonus and split structures.
5. **Raw vs. Adjusted Price Separation:** Raw prices and volumes (`open_raw`, `high_raw`, `low_raw`, `close_raw`, `volume_raw`) are preserved alongside adjusted metrics (`open_adj`, `high_adj`, `low_adj`, `close_adj`, `volume_adj`, `adjustment_factor`). Database records in `HistoricalCandle` and `HoldingTransaction` are never modified.
6. **Data Quality & Quarantine:** Validates OHLC bounds, flags non-positive prices and negative volumes, detects missing/duplicate sessions against `ExchangeCalendar`, flags unexplained price jumps (>50% without corporate actions), and quarantines invalid candles from the clean dataset.
7. **Canonical Hashing & Snapshot Persistence:** Generates deterministic SHA-256 content hashes over canonical CSV representations, records universe hashes, and creates `MLDatasetSnapshot` records.
8. **Real-Data Execution:** Successfully executed against the database across all 268 NIFTY 250 constituents, extracting 66,997 clean daily samples across 257 trading sessions with 97.28% average session coverage in ~2.5 seconds.
9. **Full Platform Regression Suite:** **310 / 310 tests passing (100% pass rate)**.

---

## 2. Files Created and Modified

| Action | Path | Description |
|---|---|---|
| **Created** | `services/ml/dataset_builder.py` | `CorporateActionAdjuster`, `DataQualityValidator`, and `DatasetBuilder` service classes |
| **Created** | `apps/ml_engine/management/__init__.py` | Package initializer for management commands |
| **Created** | `apps/ml_engine/management/commands/__init__.py` | Package initializer for management commands |
| **Created** | `apps/ml_engine/management/commands/build_ml_dataset.py` | CLI command for dataset extraction, quality audit, and snapshot persistence |
| **Created** | `tests/test_ml_dataset_builder.py` | 13 unit tests covering holidays, formulas, point-in-time leakage prevention, quarantine, and hash reproducibility |
| **Created** | `models/datasets/nifty250_historical_dataset_v_20251112_20261122.csv` | Real-data dataset snapshot artifact (7.5 MB, 66,997 rows) |
| **Created** | `docs/AIML_PHASE2_IMPLEMENTATION_REPORT.md` | This formal implementation and verification report |
| **Modified** | `IMPLEMENTATION_STATUS.md` | Updated platform test count to 310 passing tests and recorded Phase 2 completion |

---

## 3. DatasetBuilder Architecture & Design

### 3.1. Architectural Separation
The pipeline enforces four distinct separation-of-concerns layers:
1. **Source Data Layer:** Reads raw, immutable `HistoricalCandle` records and verified `CorporateEvent` records. No write operations occur on historical market data or holding ledgers.
2. **Quality Validation Layer (`DataQualityValidator`):**
   - Verifies that $Low \le Open \le High$ and $Low \le Close \le High$.
   - Verifies that $High \ge Low > 0$ and $Open > 0, Close > 0$.
   - Verifies that $Volume \ge 0$.
   - Flags extreme unexplained overnight price jumps ($|(C_t - C_{t-1}) / C_{t-1}| > 50\%$ with no corporate event on session $t$).
   - Flags missing expected sessions from `ExchangeCalendar`.
   - Invalid records are recorded in quarantine logs and excluded from the clean training set; no synthetic prices are fabricated.
3. **Adjustment Layer (`CorporateActionAdjuster`):** Slices corporate actions strictly $\le \text{as\_of\_date}$, parses announced ratios, and computes point-in-time backward adjustment factors.
4. **Canonical Persistence Layer:** Formats columns deterministically, computes bit-for-bit reproducible SHA-256 content hashes, saves dataset artifacts under `models/datasets/`, and updates `MLDatasetSnapshot`.

### 3.2. Canonical Schema Specification
The canonical dataset output contains 15 standardized columns:
- `symbol`: Exchange ticker symbol (e.g. `RELIANCE`, `TCS`).
- `isin`: International Securities Identification Number (e.g. `INE002A01018`).
- `session_date`: Exchange trading session date (`YYYY-MM-DD`).
- `open_raw`: Raw traded opening price (4 decimal places).
- `high_raw`: Raw traded high price (4 decimal places).
- `low_raw`: Raw traded low price (4 decimal places).
- `close_raw`: Raw traded closing price (4 decimal places).
- `volume_raw`: Raw traded share volume (integer).
- `adjustment_factor`: Point-in-time cumulative multiplier $F(t)$ (6 decimal places).
- `open_adj`: Point-in-time backward adjusted opening price ($P_{raw} \times F(t)$).
- `high_adj`: Point-in-time backward adjusted high price ($P_{raw} \times F(t)$).
- `low_adj`: Point-in-time backward adjusted low price ($P_{raw} \times F(t)$).
- `close_adj`: Point-in-time backward adjusted closing price ($P_{raw} \times F(t)$).
- `volume_adj`: Backward adjusted share volume ($\text{round}(V_{raw} / F(t))$).
- `source_provider`: Ingestion data provider (e.g. `YAHOO`, `JUGAAD`, `SEEDED`).

---

## 4. Corporate Action Adjustment Formulas & Leakage Prevention

### 4.1. Tested Adjustment Formulas

#### 1. Stock Split (Sub-division of share face value)
- **Convention:** 1 old share splits into $N$ new shares (e.g. "split from face value ₹10 to ₹2", or a 5-for-1 split).
- **Multiplier Factor:** $f = \frac{1}{N}$.
- **Tested Verification:**
  - Stock trades at ₹1,500.00 pre-split ($N=5$).
  - Factor: $f = \frac{1}{5} = 0.200000$.
  - Adjusted pre-split price: $₹1,500.00 \times 0.20 = ₹300.00$.
  - Adjusted pre-split volume: $10,000 / 0.20 = 50,000$ shares.

#### 2. Bonus Issue (Free proportional share allocation)
- **Convention:** $A:B$ bonus issue indicates $A$ additional bonus shares issued for every $B$ existing shares held. Total shares held post-bonus becomes $B + A$.
- **Multiplier Factor:** $f = \frac{B}{B + A}$.
- **Tested Verification (1:1 Bonus):**
  - $A=1, B=1 \implies f = \frac{1}{1 + 1} = 0.500000$.
  - Pre-bonus price of ₹2,000.00 becomes $₹2,000.00 \times 0.50 = ₹1,000.00$.
- **Tested Verification (3:1 Bonus):**
  - $A=3, B=1 \implies f = \frac{1}{1 + 3} = 0.250000$.
  - Pre-bonus price of ₹4,000.00 becomes $₹4,000.00 \times 0.25 = ₹1,000.00$.

### 4.2. Cumulative Point-in-Time Multipliers
For a time-series of candles spanning multiple corporate actions:
$$F(t) = \prod_{e \in \text{actions}, t < e.\text{ex\_date} \le T_{\text{as\_of}}} e.f$$
- Candles on or after all known ex-dates have $F(t) = 1.000000$.
- Candles prior to an ex-date are scaled by the cumulative product of subsequent corporate action factors.
- **Leakage Prevention:** Any corporate action with $\text{ex\_date} > T_{\text{as\_of}}$ is strictly excluded. When building a dataset as of $T$, future splits and bonuses do not alter historical prices.

---

## 5. Actual Historical Data Coverage & Audit Findings

### 5.1. Listing Universe & Coverage Audit
- **Broader Market Master:** 2,651 tradeable NSE listings in the database.
- **Eligible Target Universe:** 268 tradeable NSE listings representing the NIFTY LargeMidcap 250 universe.
- **Available Candle Window:** `2025-11-12` to `2026-11-22` (~1 calendar year).
- **Exchange Trading Sessions:** 257 verified trading sessions identified by `ExchangeCalendar` (excluding weekends and gazetted holidays like Republic Day, Independence Day, Christmas, Holi, Diwali).
- **Available Samples in Database:** 70,066 total candles across 282 listings.
- **NIFTY 250 Active Extracted Samples:** 66,997 clean daily candles across all 268 universe constituents.
- **Coverage Metric:**
  - Listings with $\ge 10$ sessions: **268 / 268 (100%)**.
  - Average session coverage across constituents: **97.28%**.
  - Zero listings excluded for insufficient data.

### 5.2. Data Quality & Integrity Findings
- **OHLC Consistency:** 0 invalid candles (0 non-positive prices, 0 High < Low anomalies, 0 negative volumes).
- **Suspicious Price Jumps:** 0 unexplained jumps $> 50\%$ in the extracted NIFTY 250 dataset.
- **Missing Trading Sessions:** 2.72% average missing sessions per stock, attributable to listing inception dates or trading halts. Missing dates are explicitly audited and omitted without synthetic fabrication.
- **Corporate Actions Applied in 1-Year Window:** In the current 1-year historical window (`2025-11-12` to `2026-11-22`), active NIFTY 250 corporate events (`ABCAPITAL` 1:5 split on 2026-11-25 and `A2ZINFRA` 1:1 bonus on 2026-11-26) occur after the closing session of the candle window. When evaluated with an extended as-of date $\ge 2026-11-25$, point-in-time adjustments correctly triggered.

---

## 6. Snapshot Metadata & Reproducibility Verification

### 6.1. Real-Data Snapshot Summary
- **Snapshot ID:** `1200fcee-2558-4679-ade3-2bcae49d7a52`
- **Snapshot Version:** `v_20251112_20261122`
- **Name:** `nifty250_historical_dataset`
- **Quality Status:** `VALIDATED` (Coverage 97.28% $\ge$ 80% threshold)
- **Artifact Path:** `models/datasets/nifty250_historical_dataset_v_20251112_20261122.csv` (7.5 MB)
- **Total Samples:** 66,997 rows, 15 columns
- **Universe Hash (SHA-256):** `38f3ac25dae8a65e94be8122394d21ee6d62a98f121dfbfb929ec76f1839db0d`
- **Canonical Content Hash (SHA-256):** `9530b73b5850012557240257adea5cb6165f67f3343c5b424ea5b8b339d73cc3`

### 6.2. Hash Invariance & Reproducibility
- Unit test `test_canonical_hash_reproducibility` proves that two independent extraction passes over identical candles generate 100% identical SHA-256 hashes.
- Mutating a single price value in a 67,000-row dataset immediately alters the resulting SHA-256 hash, guaranteeing cryptographic tamper detection.

---

## 7. Performance & Benchmarks

| Operation | Scale | Execution Time | Throughput |
|---|---|:---:|:---:|
| **Expected Session Calculation** | 257 trading days (1 year) | 0.8 ms | ~320,000 days/sec |
| **Listing Extraction & Validation** | 268 listings (67,000 rows) | 1.82 s | ~147 listings/sec |
| **Point-in-Time Corporate Multiplier** | 268 listings | 0.12 s | ~2,200 listings/sec |
| **Canonical Sorting & Content Hashing** | 66,997 rows (7.5 MB CSV) | 0.41 s | ~163,000 rows/sec |
| **Total End-to-End Build & Save** | **268 stocks, 66,997 samples** | **~2.45 s** | **~27,300 rows/sec** |

---

## 8. Automated Test Suite Results

### 8.1. Dedicated Phase 2 Test Suite (`tests/test_ml_dataset_builder.py`)
Thirteen unit tests executed:
1. `test_5_for_1_split_ratio_parsing`: Verifies 5-for-1 split factor calculation ($f=0.20$), pre-split price scaling (₹1,500 $\rightarrow$ ₹300), and volume scaling ($10,000 \rightarrow 50,000$).
2. `test_1_to_1_bonus_ratio_parsing`: Verifies 1:1 bonus factor calculation ($f=0.50$) and price scaling (₹2,000 $\rightarrow$ ₹1,000).
3. `test_3_to_1_bonus_ratio_parsing`: Verifies 3:1 bonus factor calculation ($f=0.25$) and price scaling (₹4,000 $\rightarrow$ ₹1,000).
4. `test_2_to_1_and_1_to_2_bonus_parsing`: Verifies 2:1 ($f=0.333333$) and 1:2 ($f=0.666667$) bonus factors.
5. `test_valid_candle`: Verifies validation acceptance of clean OHLC records.
6. `test_invalid_ohlc_relationships`: Verifies rejection of High < Low, Open/Close outside [Low, High], and negative volume.
7. `test_detect_suspicious_jumps`: Verifies detection of >50% unexplained jumps and suppression when corporate ex-dates match.
8. `test_date_filtering_and_market_holidays`: Verifies exclusion of exchange holidays (Christmas, Republic Day) and weekends.
9. `test_point_in_time_adjustment_and_raw_price_separation`: Verifies pre-split price scaling, post-split neutrality, zero lookahead leakage when as-of date precedes ex-date, and preservation of raw DB records.
10. `test_canonical_hash_reproducibility`: Verifies 100% hash reproducibility on identical data and hash sensitivity to price alterations.
11. `test_quarantine_invalid_candles`: Verifies exclusion of invalid candles and recording of quarantine error details.
12. `test_snapshot_persistence_and_idempotency`: Verifies snapshot persistence, disk storage, and idempotent re-runs.
13. `test_management_command_execution`: Verifies CLI command execution with options and dry-run output formatting.

**Result:** `13 passed in 1.95s`

### 8.2. Full Platform Regression Suite
Full test suite executed across all 35 test files:
- **Total Tests Collected:** 310
- **Passed:** 310
- **Failed:** 0
- **Pass Rate:** 🟢 **100%**
- **Execution Time:** ~42 seconds

---

## 9. Limitations & Safeguard Disclosures

1. **Available Historical Depth:**
   - As explicitly required by the safeguards, the system does not assume five years of complete historical data exist in the development database.
   - The current database contains **1 full calendar year** of daily candles (257 trading sessions, 66,997 clean samples for NIFTY 250).
   - This 1-year depth is completely sufficient for initial Phase 3 feature engineering, walk-forward testing protocols, and model architecture validation.
   - For multi-year production backtesting spanning 2020–2026, additional historical Bhavcopies will be ingested via the existing `import_market_data` ingestion command.
2. **Survivorship Bias:**
   - The NIFTY 250 universe is constructed using current constituent definitions. Historical delistings prior to the current universe composition are not represented.

---

## 10. Recommendation

**Status:** 🟢 **READY_FOR_PHASE_3**

Phase 2 is fully implemented, verified, and operational. The dataset builder reliably extracts point-in-time data, enforces verified corporate action mathematics without leakage, audits data quality, and produces cryptographically verifiable snapshot artifacts.

The repository is clean and ready to proceed to **Phase 3: Feature Engineering and Target Labels** as specified in `docs/AIML_ROADMAP.md`.
