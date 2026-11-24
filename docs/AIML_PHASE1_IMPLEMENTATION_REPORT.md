# AI/ML Phase 1 Implementation Report: Dependencies & Database Foundation

**Document:** `docs/AIML_PHASE1_IMPLEMENTATION_REPORT.md`  
**Phase:** Phase 1 — Dependencies & Database Foundation  
**System:** KuberLens (Indian Stock Market Research & Intelligence Platform)  
**Executed Date:** 2026-11-24  
**Status:** 🟢 **COMPLETED & VERIFIED (READY FOR PHASE 2)**  

---

## 1. Executive Summary

Phase 1 establishes the mathematical, dependency, and database foundation for supervised machine learning in KuberLens without modifying existing transaction accounting, broker integrations, or the active user-facing UI.

All objectives of Phase 1 as specified in `docs/AIML_ROADMAP.md` (v2.1) and `docs/AIML_ARCHITECTURE.md` (v2.1) have been implemented, verified, and regression-tested:
1. **Core ML Dependencies Installed & Tested:** `lightgbm` (4.7.0), `scikit-learn` (1.9.1), `joblib` (1.6.0), and `scipy` (1.18.1) installed in Python 3.13.3 with Apple Silicon OpenMP runtime (`libomp` 23.1.6).
2. **Safe Pre-Migration Database Backup:** Verified dual backup created at `backups/db_pre_phase1.sqlite3` (146 MB SQLite binary) and `backups/ml_engine_backup_pre_phase1.json` (63 KB JSON fixture).
3. **ORM Schema Extensions Implemented:** Added `MLInferenceState`, `MLModelState`, `MLDatasetSnapshot`, `MLFeatureDefinition`, `MLMonitoringEvent`, `MLPredictionArchive`, and extended `MLModelRecord` and `MLPrediction` in `apps/ml_engine/models.py`.
4. **Three-Stage Zero-Data-Loss Migration:** 
   - Migration `0002`: Schema extensions with nullable/default fields.
   - Migration `0003`: Legacy data backfill and duplicate archiving. All 70 historical legacy predictions were preserved (30 unique active records retained in `MLPrediction`, and 40 duplicate keys safely preserved in `MLPredictionArchive` with original primary keys, timestamps, and confidence scores). 1 legacy model backfilled as `LEGACY_HEURISTIC` / `HEURISTIC_RULE_BASED`.
   - Migration `0004`: Database constraint enforcement (`UniqueConstraint` ensuring at most one `APPROVED` model per prediction horizon, and `UniqueConstraint` on `(listing, model_record, horizon_sessions, as_of_session)`).
5. **Admin & Configuration:** Model directory registered in Django settings (`ML_MODEL_DIR = BASE_DIR / "models"`), `.gitignore` updated for artifacts and backups, and all models registered in `apps/ml_engine/admin.py`.
6. **Full Test Suite Validation:** 9 new comprehensive model and migration tests added in `tests/test_ml_models.py`. Full platform test suite executed: **293 / 293 tests passing (100% pass rate)**.

---

## 2. Files Created and Modified

| Action | Path | Description |
|---|---|---|
| **Modified** | `requirements/base.txt` | Added `lightgbm>=4.5.0`, `scikit-learn>=1.5.2`, `joblib>=1.4.2`, `scipy>=1.14.1` |
| **Modified** | `.gitignore` | Added rules for `models/**/*.joblib`, `models/**/*.parquet`, `models/artifacts/`, and `backups/` |
| **Modified** | `config/settings/base.py` | Defined `ML_MODEL_DIR = BASE_DIR / "models"` with automatic directory creation |
| **Modified** | `apps/ml_engine/models.py` | Added 4 new models, 2 enum classes, and extended `MLModelRecord` & `MLPrediction` |
| **Modified** | `apps/ml_engine/admin.py` | Registered new models (`MLDatasetSnapshot`, `MLFeatureDefinition`, `MLPredictionArchive`, `MLMonitoringEvent`) and updated list displays for `MLModelRecord` and `MLPrediction` |
| **Modified** | `services/ml/engine.py` | Updated `StockMLRanker` to populate new fields (`horizon_sessions`, `as_of_session`, `raw_probability`, `calibrated_probability`, `is_heuristic`) and maintain daily idempotency |
| **Created** | `apps/ml_engine/migrations/0002_aiml_schema_extensions.py` | Stage 1 migration: new tables and non-breaking column additions |
| **Created** | `apps/ml_engine/migrations/0003_legacy_data_backfill_and_archive.py` | Stage 2 migration: legacy backfill and duplicate preservation into `MLPredictionArchive` |
| **Created** | `apps/ml_engine/migrations/0004_enforce_database_constraints.py` | Stage 3 migration: strict uniqueness constraints and nullability enforcement |
| **Created** | `tests/test_ml_models.py` | 9 unit tests for Phase 1 models, constraints, and atomic lifecycle operations |
| **Created** | `backups/db_pre_phase1.sqlite3` | Raw SQLite binary backup before applying Phase 1 migrations |
| **Created** | `backups/ml_engine_backup_pre_phase1.json` | Django JSON dumpdata fixture of `ml_engine` app prior to migration |
| **Created** | `docs/AIML_PHASE1_IMPLEMENTATION_REPORT.md` | This formal implementation and verification report |
| **Modified** | `IMPLEMENTATION_STATUS.md` | Updated platform status to 293 passing tests and documented Phase 1 completion |

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

## 4. Models and Schema Extensions

### 4.1. New Enums and Models
1. **`MLInferenceState` (`models.TextChoices`)**:
   - `ONLINE_REALTIME`, `EOD_BATCH_SCHEDULED`, `MANUAL_ADHOC`, `BACKTEST_SIMULATED`.
2. **`MLModelState` (`models.TextChoices`)**:
   - `DRAFT`, `CANDIDATE_TRAINED`, `VALIDATED`, `APPROVED`, `REJECTED`, `RETIRED`, `LEGACY_HEURISTIC`.
3. **`MLDatasetSnapshot`**:
   - Manages point-in-time training and validation datasets.
   - Fields: `snapshot_name`, `as_of_session`, `start_date`, `end_date`, `sha256_hash`, `row_count`, `feature_count`, `parquet_path`, `storage_backend`, `metadata`.
   - Constraints: `UniqueConstraint(fields=["snapshot_name", "as_of_session"])`.
4. **`MLFeatureDefinition`**:
   - Catalog of point-in-time features preventing train/inference drift.
   - Fields: `name`, `version`, `feature_family`, `data_type`, `imputation_strategy`, `source_table`, `is_active`, `description`.
   - Constraints: `UniqueConstraint(fields=["name", "version"])`.
5. **`MLPredictionArchive`**:
   - Append-only historical archive preserving predictions removed from active tables during deduplication or schema transitions.
   - Fields: `original_prediction_id`, `listing`, `model_record`, `horizon_sessions`, `as_of_session`, `predicted_probability`, `predicted_label`, `confidence_score`, `archive_reason`, `original_created_at`, `archived_at`.
6. **`MLMonitoringEvent`**:
   - Audits data drift, calibration degradation, and model promotions/rollbacks.
   - Fields: `event_type`, `model_record`, `horizon_sessions`, `severity`, `metric_name`, `metric_value`, `threshold_value`, `details`.

### 4.2. Extended Existing Models
1. **`MLModelRecord`**:
   - Added: `dataset_snapshot` (FK `MLDatasetSnapshot`), `previous_approved_version` (FK self), `artifact_path`, `artifact_hash`, `algorithm`, `horizon_sessions`, `calibration_method`, `brier_score`, `brier_skill_score`, `pr_auc`, `model_state`.
   - Constraint: `UniqueConstraint(fields=["horizon_sessions"], condition=Q(model_state="APPROVED"), name="unique_approved_model_per_horizon")` enforcing **at most one APPROVED model per prediction horizon**.
2. **`MLPrediction`**:
   - Added: `horizon_sessions` (default 5), `as_of_session`, `target_definition`, `raw_probability`, `calibrated_probability`, `calibration_status`, `is_heuristic`, `inference_state`.
   - Constraint: `UniqueConstraint(fields=["listing", "model_record", "horizon_sessions", "as_of_session"], name="unique_listing_model_horizon_session")`.

---

## 5. Migration Execution & Zero-Loss Verification

### 5.1. Three-Stage Migration Protocol
The migration was staged into three separate files to guarantee database integrity and allow rolling back any step without loss of legacy records:
- **`0002_aiml_schema_extensions.py`**: Created new tables (`MLDatasetSnapshot`, `MLFeatureDefinition`, `MLPredictionArchive`, `MLMonitoringEvent`) and added transitional nullable columns to `MLModelRecord` and `MLPrediction`.
- **`0003_legacy_data_backfill_and_archive.py`**:
  - Identified 1 existing `MLModelRecord` (heuristic ranker). Set `model_state="LEGACY_HEURISTIC"`, `algorithm="HEURISTIC_RULE_BASED"`, `horizon_sessions=5`.
  - Identified 70 existing `MLPrediction` records.
  - Deduped records sharing `(listing_id, model_record_id, horizon_sessions, as_of_session)`. Exactly 30 unique records were retained in `MLPrediction`, and 40 duplicate records were archived in `MLPredictionArchive` with `archive_reason="MIGRATION_DUPLICATE_KEY_RESOLUTION"`.
  - Backfilled all 30 active predictions: `is_heuristic=True`, `calibration_status="UNCALIBRATED"`, `target_definition="HEURISTIC_FALLBACK"`, `raw_probability=confidence_score`, `calibrated_probability=confidence_score`, `inference_state="ONLINE_REALTIME"`.
- **`0004_enforce_database_constraints.py`**: Made `as_of_session` non-nullable and enforced database uniqueness constraints.

### 5.2. Pre- and Post-Migration Data Counts

| Table | Pre-Migration Rows | Post-Migration Rows | Status |
|---|:---:|:---:|---|
| `MLModelRecord` | 1 | 1 | 🟢 Backfilled to `LEGACY_HEURISTIC` |
| `MLPrediction` | 70 | 30 | 🟢 30 unique active records retained |
| `MLPredictionArchive` | 0 | 40 | 🟢 40 duplicates preserved with original IDs |
| **Total Preserved Predictions** | **70** | **70** | 🟢 **Zero historical records discarded (100% preservation)** |

---

## 6. Automated Test Suite Results

### 6.1. Phase 1 Dedicated Test Suite (`tests/test_ml_models.py`)
Nine specialized unit tests were authored and executed:
1. `test_create_dataset_snapshot`: Verifies snapshot creation, hash tracking, and unique constraint on `(snapshot_name, as_of_session)`.
2. `test_feature_definition_uniqueness`: Verifies feature definition versioning and unique constraint on `(name, version)`.
3. `test_at_most_one_approved_model_per_horizon`: Verifies database constraint rejecting two `APPROVED` models for the same horizon (e.g. 5 days), while allowing multiple `RETIRED` or `CANDIDATE_TRAINED` models.
4. `test_atomic_model_promotion_and_rollback`: Tests atomic promotion workflow where an existing approved model is retired, a candidate is approved, and rollbacks restore the previous approved model safely.
5. `test_prediction_uniqueness_constraint`: Verifies unique constraint on `(listing, model_record, horizon_sessions, as_of_session)` preventing duplicate daily predictions.
6. `test_legacy_prediction_flags`: Verifies that legacy/heuristic predictions are flagged with `is_heuristic=True`, `calibration_status="UNCALIBRATED"`, and `target_definition="HEURISTIC_FALLBACK"`.
7. `test_prediction_archive_preservation`: Verifies that archived predictions retain original primary keys, labels, probabilities, and archive reasons.
8. `test_monitoring_event_creation`: Verifies event creation for data drift and calibration anomalies.
9. `test_models_directory_exists`: Verifies `settings.ML_MODEL_DIR` is configured and physically exists.

**Result:** `9 passed in 1.54s`

### 6.2. Full Platform Regression Suite
Full test suite executed across all 34 test files:
- **Total Tests Collected:** 293
- **Passed:** 293
- **Failed:** 0
- **Pass Rate:** 🟢 **100%**
- **Execution Time:** ~39 seconds

---

## 7. Phase 1 Acceptance Checklist

- [x] `requirements/base.txt` updated with LightGBM, scikit-learn, joblib, SciPy.
- [x] Package versions verified for Python 3.13 compatibility in the active virtual environment.
- [x] Verified database backup created before applying schema migrations.
- [x] `MLInferenceState` and `MLModelState` enums implemented.
- [x] `MLDatasetSnapshot`, `MLFeatureDefinition`, `MLMonitoringEvent`, and `MLPredictionArchive` models implemented.
- [x] `MLModelRecord` extended with artifact metadata, lifecycle state, and evaluation metrics.
- [x] `MLPrediction` extended with probability calibration, horizon, and heuristic tracking fields.
- [x] Three-stage migration protocol executed successfully.
- [x] Exactly zero legacy prediction records lost (duplicates preserved in `MLPredictionArchive`).
- [x] At most one `APPROVED` model per horizon enforced at the database level.
- [x] Django Admin registrations updated for all new and extended models.
- [x] Settings updated with `ML_MODEL_DIR`.
- [x] `.gitignore` updated for artifacts and backups.
- [x] All 293 automated tests passing.
- [x] No changes made to portfolio accounting, broker integrations, or live UI templates.

---

## 8. Recommendation

**Status:** 🟢 **READY_FOR_PHASE_2**

Phase 1 provides the complete schema, dependency, and data-integrity foundation. The repository is in a clean, fully passing state and ready to proceed to **Phase 2: Historical Dataset Builder & Corporate Action Adjustment**, as detailed in `docs/AIML_ROADMAP.md`.
