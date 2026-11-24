# AI/ML Phase 1 & 1.1 Implementation Report: Dependencies, Database Foundation & Schema Consistency

**Document:** `docs/AIML_PHASE1_IMPLEMENTATION_REPORT.md`  
**Phase:** Phase 1 & Phase 1.1 — Dependencies, Database Foundation & Schema Consistency  
**System:** KuberLens (Indian Stock Market Research & Intelligence Platform)  
**Executed Date:** 2026-11-24  
**Status:** 🟢 **COMPLETED & VERIFIED (READY FOR PHASE 2)**  

---

## 1. Executive Summary

Phase 1 and Phase 1.1 establish the mathematical, dependency, and database foundation for supervised machine learning in KuberLens without modifying existing transaction accounting, broker integrations, or the active user-facing UI.

All objectives of Phase 1 and Phase 1.1 as specified in `docs/AIML_ROADMAP.md` (v2.1), `docs/AIML_ARCHITECTURE.md` (v2.1), and Phase 1.1 schema corrections have been implemented, verified, and regression-tested:
1. **Core ML Dependencies Installed & Tested:** `lightgbm` (4.7.0), `scikit-learn` (1.9.1), `joblib` (1.6.0), and `scipy` (1.18.1) installed in Python 3.13.3 with Apple Silicon OpenMP runtime (`libomp` 23.1.6).
2. **Safe Pre-Migration Database Backups:** Dual verified backups created and tested for restorability (`backups/db_pre_phase1.sqlite3`, `backups/db_pre_phase1_1.sqlite3`, and `backups/db_post_phase1_1.sqlite3` with SQLite `PRAGMA integrity_check` passing).
3. **ORM Schema Extensions & Separation of Concerns:**
   - Separated operational execution trigger mode (`MLExecutionMode`) from statistical/data inference quality state (`MLInferenceState`).
   - Added `MLInferenceState`, `MLExecutionMode`, `MLModelState`, `MLDatasetSnapshot`, `MLFeatureDefinition`, `MLMonitoringEvent`, `MLPredictionArchive`, and extended `MLModelRecord` and `MLPrediction` in `apps/ml_engine/models.py`.
4. **Zero-Data-Loss Migration Chain (0002 -> 0003 -> 0004 -> 0005):**
   - Migration `0002`: Schema extensions with nullable/default fields.
   - Migration `0003`: Legacy data backfill and duplicate archiving. All 70 historical legacy predictions were preserved (30 unique active records retained in `MLPrediction`, and 40 duplicate keys safely preserved in `MLPredictionArchive` with original primary keys, timestamps, and confidence scores). 1 legacy model backfilled as `LEGACY_HEURISTIC` / `HEURISTIC_RULE_BASED`.
   - Migration `0004`: Database constraint enforcement (`UniqueConstraint` ensuring at most one `APPROVED` model per prediction horizon, and `UniqueConstraint` on `(listing, model_record, horizon_sessions, as_of_session)`).
   - Migration `0005`: Separated inference state from execution mode; enforced `calibrated_probability=NULL`, `is_heuristic=True`, `inference_state=HEURISTIC_FALLBACK`, `calibration_status=UNCALIBRATED` across legacy heuristic predictions while preserving original confidence scores and timestamps.
5. **Admin & Configuration:** Model directory registered in Django settings (`ML_MODEL_DIR = BASE_DIR / "models"`), `.gitignore` updated for artifacts and backups, and all models registered in `apps/ml_engine/admin.py` with execution mode and inference state filters.
6. **Full Test Suite Validation:** 13 unit tests in `tests/test_ml_models.py` covering model creation, approved-model uniqueness, atomic promotion/rollback, inference state separation, execution modes, NULL calibrated probability enforcement, archive preservation, and database backup restoration. Full platform test suite executed: **297 / 297 tests passing (100% pass rate)**.

---

## 2. Files Created and Modified

| Action | Path | Description |
|---|---|---|
| **Modified** | `requirements/base.txt` | Added `lightgbm>=4.5.0`, `scikit-learn>=1.5.2`, `joblib>=1.4.2`, `scipy>=1.14.1` |
| **Modified** | `.gitignore` | Added rules for `models/**/*.joblib`, `models/**/*.parquet`, `models/artifacts/`, and `backups/` |
| **Modified** | `config/settings/base.py` | Defined `ML_MODEL_DIR = BASE_DIR / "models"` with automatic directory creation |
| **Modified** | `apps/ml_engine/models.py` | Implemented `MLExecutionMode`, `MLInferenceState`, `MLModelState`, `MLDatasetSnapshot`, `MLFeatureDefinition`, `MLPredictionArchive`, `MLMonitoringEvent`, and extended `MLModelRecord` & `MLPrediction` |
| **Modified** | `apps/ml_engine/admin.py` | Registered all models with list displays and filters for `execution_mode`, `inference_state`, `calibration_status`, and `model_state` |
| **Modified** | `services/ml/engine.py` | Updated `StockMLRanker` to enforce heuristic prediction contract (`calibrated_probability=None`, `is_heuristic=True`, `execution_mode=ONLINE_REALTIME`, `inference_state=HEURISTIC_FALLBACK`) |
| **Created** | `apps/ml_engine/migrations/0002_aiml_schema_extensions.py` | Stage 1 migration: new tables and non-breaking column additions |
| **Created** | `apps/ml_engine/migrations/0003_legacy_data_backfill_and_archive.py` | Stage 2 migration: legacy backfill and duplicate preservation into `MLPredictionArchive` |
| **Created** | `apps/ml_engine/migrations/0004_enforce_database_constraints.py` | Stage 3 migration: strict uniqueness constraints and nullability enforcement |
| **Created** | `apps/ml_engine/migrations/0005_separate_inference_state_and_execution_mode.py` | Phase 1.1 forward migration: adds `execution_mode` to `MLPrediction` and `MLPredictionArchive`, updates `MLInferenceState` choices, enforces heuristic prediction standards |
| **Created** | `tests/test_ml_models.py` | 13 unit tests for Phase 1 and 1.1 models, constraints, and atomic lifecycle operations |
| **Created** | `backups/db_pre_phase1.sqlite3` | Raw SQLite binary backup before applying Phase 1 migrations |
| **Created** | `backups/db_pre_phase1_1.sqlite3` | SQLite binary backup before Phase 1.1 schema adjustments |
| **Created** | `backups/db_post_phase1_1.sqlite3` | Verified restorable SQLite binary backup after Phase 1.1 |
| **Created** | `backups/ml_engine_backup_post_phase1_1.json` | Django JSON dumpdata fixture of `ml_engine` app |
| **Created** | `docs/AIML_PHASE1_IMPLEMENTATION_REPORT.md` | This formal implementation and verification report |
| **Modified** | `IMPLEMENTATION_STATUS.md` | Updated platform status to 297 passing tests and documented Phase 1.1 completion |

---

## 3. Dependency Environment & Versions

| Package | Installed Version | Python Compatibility | Verification Status |
|---|---|---|---|
| **Python** | 3.13.3 | Core runtime | Verified |
| **Django** | 5.1.15 | Core framework | Verified |
| **NumPy** | 2.5.4 | Pre-existing baseline | Verified |
| **LightGBM** | 4.7.0 | Python 3.13 Apple Silicon binary wheel | Verified (paired with `libomp` 23.1.6) |
| **scikit-learn** | 1.9.1 | Python 3.13 wheel | Verified |
| **joblib** | 1.6.0 | Pure Python | Verified |
| **SciPy** | 1.18.1 | Python 3.13 wheel | Verified |
| **OpenMP Runtime** | 23.1.6 (`libomp`) | Installed via Homebrew for macOS Apple Silicon | Verified |

---

## 4. Phase 1.1 Architecture & Schema Corrections

### 4.1. Correction 1: Separation of Inference State from Execution Mode
Previously, runtime trigger modes and statistical data states were conflated. In Phase 1.1, these are separated into two distinct orthogonal enums:

1. **`MLInferenceState` (`models.TextChoices`)** — Statistical & data quality classification of the prediction:
   - `APPROVED_MODEL`: Generated by an active, validated, approved supervised ML model with calibrated probabilities.
   - `EXPERIMENTAL_MODEL`: Generated by a candidate or experimental model undergoing shadow evaluation.
   - `HEURISTIC_FALLBACK`: Generated by rule-based heuristic calculations.
   - `STALE_DATA`: Generated when recent market data close is older than session freshness limits.
   - `INSUFFICIENT_DATA`: Generated when historical candles are below minimum lookback requirements (e.g. <30 daily candles).

2. **`MLExecutionMode` (`models.TextChoices`)** — Operational orchestration mode:
   - `ONLINE_REALTIME`: Triggered interactively via user research views or ad-hoc web requests.
   - `EOD_BATCH_SCHEDULED`: Triggered by scheduled end-of-day Celery batch processing following bhavcopy ingestion.
   - `MANUAL_ADHOC`: Triggered by administrative management commands or manual research triggers.
   - `BACKTEST_SIMULATED`: Triggered within backtesting or paper-trading simulation loops.

Both `MLPrediction` and `MLPredictionArchive` now maintain `execution_mode` (indexed `CharField`), while `MLPrediction.inference_state` is constrained to `MLInferenceState.choices`.

### 4.2. Correction 2: Legacy Heuristic Probability Standards
For all existing and future heuristic predictions:
- `is_heuristic = True`
- `inference_state = MLInferenceState.HEURISTIC_FALLBACK` (or `INSUFFICIENT_DATA`)
- `execution_mode = MLExecutionMode.ONLINE_REALTIME`
- `calibration_status = "UNCALIBRATED"`
- `calibrated_probability = NULL` (strictly `None`, never conflated with uncalibrated confidence scores)
- `confidence_score`: Preserves the original heuristic score (e.g. `0.5100`, `0.6200`)
- `id`, `prediction_timestamp`, and historical audit timestamps are strictly preserved without modification.

`StockMLRanker.evaluate_and_predict` has been updated to enforce these invariants on all future rule-based outputs.

---

## 5. Migration Execution & Zero-Loss Verification

### 5.1. Applied Migration Chain
- **`0002_aiml_schema_extensions.py`**: Created new tables (`MLDatasetSnapshot`, `MLFeatureDefinition`, `MLPredictionArchive`, `MLMonitoringEvent`) and added transitional nullable columns to `MLModelRecord` and `MLPrediction`.
- **`0003_legacy_data_backfill_and_archive.py`**:
  - Identified 1 existing `MLModelRecord` (heuristic ranker). Set `model_state="LEGACY_HEURISTIC"`, `algorithm="HEURISTIC_RULE_BASED"`, `horizon_sessions=10`.
  - Deduped 70 historical predictions sharing `(listing_id, model_record_id, horizon_sessions, as_of_session)`. Exactly 30 unique records retained in `MLPrediction`, and 40 duplicate records safely archived in `MLPredictionArchive` with `archive_reason="MIGRATION_DUPLICATE_KEY_RESOLUTION"`.
- **`0004_enforce_database_constraints.py`**: Made `as_of_session` non-nullable and enforced database uniqueness constraints:
  - `UniqueConstraint(fields=["horizon_sessions"], condition=Q(model_state="APPROVED"), name="unique_approved_model_per_horizon")`
  - `UniqueConstraint(fields=["listing", "model_record", "horizon_sessions", "as_of_session"], name="unique_listing_model_horizon_session")`
- **`0005_separate_inference_state_and_execution_mode.py`**:
  - Added `execution_mode` to `MLPrediction` and `MLPredictionArchive`.
  - Updated `inference_state` choices on `MLPrediction`.
  - Backfilled active predictions to `execution_mode="ONLINE_REALTIME"`, `inference_state="HEURISTIC_FALLBACK"`, `calibration_status="UNCALIBRATED"`, `calibrated_probability=None`.
  - Backfilled archived predictions to `execution_mode="ONLINE_REALTIME"`.

### 5.2. Pre- and Post-Migration Data Counts

| Table | Pre-Phase 1 Rows | Post-Phase 1.1 Rows | Status |
|---|:---:|:---:|---|
| `MLModelRecord` | 1 | 1 | 🟢 Backfilled to `LEGACY_HEURISTIC` |
| `MLPrediction` | 70 | 30 | 🟢 30 unique active records (`calibrated_probability=None`, `is_heuristic=True`) |
| `MLPredictionArchive` | 0 | 40 | 🟢 40 duplicates preserved with original IDs & timestamps |
| **Total Preserved Predictions** | **70** | **70** | 🟢 **Zero historical records discarded (100% preservation)** |

### 5.3. Backup & Restoration Verification
- Restorability test executed against `backups/db_post_phase1_1.sqlite3`:
  - `PRAGMA integrity_check;` returned `[('ok',)]`.
  - Full table query verification confirmed all 30 active predictions, 40 archived predictions, and 1 model record were completely restored and readable.
  - Django JSON fixture at `backups/ml_engine_backup_post_phase1_1.json` verified with all 71 objects.

---

## 6. Automated Test Suite Results

### 6.1. Dedicated Test Suite (`tests/test_ml_models.py`)
Thirteen specialized unit tests executed:
1. `test_create_dataset_snapshot`: Verifies snapshot creation, hash tracking, and unique constraint on `(snapshot_name, as_of_session)`.
2. `test_feature_definition_uniqueness`: Verifies feature definition versioning and unique constraint on `(name, version)`.
3. `test_at_most_one_approved_model_per_horizon_constraint`: Verifies database constraint rejecting two `APPROVED` models for the same horizon (e.g. 10 days), while allowing multiple `RETIRED` or `EXPERIMENTAL` models.
4. `test_atomic_promotion_and_rollback`: Tests atomic promotion workflow where an existing approved model is retired, a candidate is approved, and rollbacks restore the previous approved model safely.
5. `test_unique_listing_model_horizon_session_constraint`: Verifies unique constraint on `(listing, model_record, horizon_sessions, as_of_session)` preventing duplicate daily predictions.
6. `test_prediction_archive_preservation`: Verifies that archived predictions retain original primary keys, labels, probabilities, and archive reasons.
7. `test_execution_mode_and_inference_state_separation`: Verifies all 5 `MLInferenceState` choices and all 4 `MLExecutionMode` choices can be assigned and queried independently.
8. `test_heuristic_predictions_have_null_calibrated_probability`: Verifies that heuristic predictions strictly enforce `is_heuristic=True`, `inference_state=HEURISTIC_FALLBACK`, `calibration_status="UNCALIBRATED"`, and `calibrated_probability=None`.
9. `test_stock_ml_ranker_heuristic_prediction_contract`: Verifies that `StockMLRanker.evaluate_and_predict` satisfies the heuristic prediction contract.
10. `test_database_backup_integrity_and_restorability`: Verifies SQLite binary backup restorability and integrity check.
11. `test_monitoring_event_creation`: Verifies event creation for data drift and calibration anomalies.
12. `test_models_directory_exists`: Verifies `settings.ML_MODEL_DIR` is configured and physically exists.
13. `test_name_uniqueness`: Verifies feature name uniqueness.

**Result:** `13 passed in 3.11s`

### 6.2. Full Platform Regression Suite
Full test suite executed across all 34 test files:
- **Total Tests Collected:** 297
- **Passed:** 297
- **Failed:** 0
- **Pass Rate:** 🟢 **100%**
- **Execution Time:** ~40 seconds

---

## 7. Migration Consistency & Unresolved Issues

- **Migration Consistency:** `python manage.py makemigrations --check` reports **No changes detected** (code 0). Schema models and migration history are in 100% synchronization.
- **Unresolved Issues:** None.
- **No changes made to:** Portfolio accounting, broker integrations, live UI templates, or existing migration files (`0001` through `0004`).

---

## 8. Final Recommendation

**Status:** 🟢 **READY_FOR_PHASE_2**

Phase 1 and Phase 1.1 provide the complete schema, dependency, execution mode separation, and data-integrity foundation. The platform is in a clean, fully passing state and ready to proceed to **Phase 2: Historical Dataset Builder & Corporate Action Adjustment**, as detailed in `docs/AIML_ROADMAP.md`.
