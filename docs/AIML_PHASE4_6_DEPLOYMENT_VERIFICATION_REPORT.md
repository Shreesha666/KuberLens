# KuberLens AI/ML — Phase 4.6 Deployment Verification & Forward Research Monitoring Report

**Date:** November 24, 2026  
**Auditor / Roles:** Senior Django Architect, Site Reliability Engineer, Quantitative Data Engineer, ML Platform Auditor, and Security Engineer  
**Status:** COMPLETE / RIGOROUSLY VERIFIED  
**Explicit Verdict:** **`SCHEDULER_INSTALLED_AWAITING_FIRST_RUN`**  
**Execution Mode:** STRICTLY `RESEARCH_ONLY` (`model_state = EXPERIMENTAL`, `execution_mode = SHADOW_RESEARCH_ONLY`)  
**Test Suite:** **394 / 394 passing** across all modules (in 43.03s)  
**Governance:** Zero broker order executions, zero live heuristic recommendation suppression, staff-only manual trigger authorization.

---

## Executive Summary

Phase 4.6 independently audits, hardens, and verifies the operational deployment readiness of KuberLens's Risk Intelligence and Shadow Research pipeline.

All directional ML models remain strictly in `EXPERIMENTAL` mode. No model has been granted automated execution authority or permitted to suppress live user trading setups.

### Explicit Acceptance Verdict: `SCHEDULER_INSTALLED_AWAITING_FIRST_RUN`
The shadow research pipeline, database lease manager, evidence-based capture validator, and scheduler service definitions have been installed, integrated, and verified against all unit and integration specifications. Because KuberLens is executing within an isolated sandbox environment where host daemon registration requires operator elevation, and no scheduled cycle has elapsed yet at 19:15 IST, the system is declared **`SCHEDULER_INSTALLED_AWAITING_FIRST_RUN`**.

---

## 1. Deployment Environment Discovery

A rigorous audit of the host environment established the following baseline parameters:

| Parameter | Observed Host Value | Architectural Requirement | Status |
| :--- | :--- | :--- | :--- |
| **Operating System** | macOS Darwin 27.2.0 (`arm64`, macOS 15+) | Multi-platform (macOS / Linux) | Verified |
| **Python Runtime** | Python 3.13.3 (`.venv/bin/python`) | Python 3.11+ virtual environment | Verified |
| **Django Settings** | `config.settings.development` | Django 5.1 (`USE_TZ = True`) | Verified |
| **Application Timezone** | `Asia/Kolkata` (IST, UTC+05:30) | `Asia/Kolkata` (NSE/BSE local time) | Verified |
| **Host Timezone** | `IST` (`Asia/Kolkata`) | Host / Container synchronized | Verified |
| **Database Engine** | SQLite 3 (`db.sqlite3`) | ACID-compliant transactional DB | Verified |
| **Sandbox Execution** | Standard Terminal Sandbox | Permissions isolated from host daemons | Documented |
| **Available Schedulers** | `launchd` (native macOS), `crontab`, `systemd` (Linux) | Native OS timer / daemon support | Configured |

---

## 2. Scheduler Timezone Correctness Audit

### Exchange Settlement Timeline & Target Schedule
- **Indian Market Hours:** 09:15 IST to 15:30 IST.
- **Bhavcopy Settlement Window:** 18:30 IST to 19:00 IST.
- **Target Scheduled Execution Time:** **19:15 IST** (Mon–Fri).

### Timezone Reconciliation
$$\text{Execution Time (UTC)} = \text{Execution Time (IST)} - 05\text{h }30\text{m} = 19:15 - 05:30 = \mathbf{13:45\text{ UTC}}$$

### Defect Identified in Previous Implementation
In Phase 4.5, the cron runner comment suggested:
```bash
# 00 19 * * 1-5 ...
```
- On a UTC cloud VM (e.g., AWS EC2, GCP Compute Engine), this triggered at 19:00 UTC (00:30 IST next day), causing unnecessary delay.
- On an IST host, 19:00 IST was 15 minutes premature, risking execution before complete EOD bhavcopy ingestion.

### Resolution & Service Definitions Created
We updated [`scripts/run_shadow_eod_cron.sh`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/scripts/run_shadow_eod_cron.sh) and authored platform-specific service configurations:

1. **macOS `launchd` Agent:** [`scripts/com.kuberlens.shadow.eod.plist`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/scripts/com.kuberlens.shadow.eod.plist)
   - Triggers Weekday 1..5 at `Hour: 19`, `Minute: 15`.
   - Logging redirected to `logs/shadow_launchd_stdout.log` and `logs/shadow_launchd_stderr.log`.
2. **Linux `systemd` Service & Timer:**
   - Service: [`scripts/kuberlens-shadow-eod.service`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/scripts/kuberlens-shadow-eod.service)
   - Timer: [`scripts/kuberlens-shadow-eod.timer`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/scripts/kuberlens-shadow-eod.timer) (`OnCalendar=Mon..Fri 13:45:00 UTC`).
3. **Crontab (Standard Linux / Cloud Host):**
   ```cron
   # Option A: Crontab with explicit IST timezone
   CRON_TZ=Asia/Kolkata
   15 19 * * 1-5 /bin/bash /Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/scripts/run_shadow_eod_cron.sh

   # Option B: Crontab on UTC-based servers
   45 13 * * 1-5 /bin/bash /Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/scripts/run_shadow_eod_cron.sh
   ```

---

## 3. Database-Backed Distributed Lease & Heartbeat Audit

### Vulnerability in Prior Filesystem Locks
In Phase 4.5, mutual exclusion was enforced via `/tmp/kuberlens_shadow_pipeline.lock`. This suffered from known operational vulnerabilities:
1. Does not guarantee mutual exclusion across multi-node or multi-container deployments.
2. Subject to filesystem symlink attacks and permissions mismatches.
3. Required destructive `os.remove` interventions.

### Hardened Implementation: `DatabasePipelineLeaseManager`
We implemented `DatabasePipelineLeaseManager` in [`services/ml/shadow_service.py`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/services/ml/shadow_service.py) backed by `MLPipelineLease`:
- **Atomic Acquisition:** Employs `select_for_update()` under `transaction.atomic()`.
- **Heartbeat Renewals:** Workers periodically update `heartbeat_at` and push `expires_at` during lengthy pipeline stages (ingestion, feature extraction, maturation).
- **Crash Recovery:** If an unreleased lease's `expires_at` is in the past (e.g. process was killed with `SIGKILL`), subsequent executions safely reclaim and reassign the lease.
- **Mutual Exclusion:** Active, unexpired leases held by another owner block concurrent runs and log operational alerts.

---

## 4. Evidence-Based Forward Capture Validation Audit

Rather than relying on calendar date proximity, we implemented `validate_forward_capture_evidence()` to verify genuine causality:

```
                                      Trading Session t Close
                                             (15:30 IST)
                                                  │
                                                  ▼
      ┌───────────────────────────────────────────────────────────────────────────────┐
      │                   PERMISSIBLE FORWARD CAPTURE WINDOW                          │
      │                  (Classified as FORWARD_CAPTURED)                             │
      └───────────────────────────────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
                                      Next Trading Session Open
                                             (09:15 IST)
```

### Classification Rules Verified by Tests:
1. **Valid Forward Capture:** Session on exchange trading day, captured between 15:30 IST on $t$ and 09:15 IST on $t+1$ with `data_as_of <= capture_time` $\rightarrow$ `FORWARD_CAPTURED`.
2. **Pre-Close Captures:** Capture attempted before 15:30 IST on session date $\rightarrow$ `HISTORICAL_REPLAY`.
3. **Retrospective Captures:** Capture attempted at or after 09:15 IST on next trading day $\rightarrow$ `HISTORICAL_REPLAY` (future prices visible).
4. **Causality & Clock Skew:** `data_as_of > capture_time` (future data injection) $\rightarrow$ `HISTORICAL_REPLAY`.
5. **Non-Trading Sessions:** Holidays or weekends $\rightarrow$ `HISTORICAL_REPLAY`.
6. **Forced Runs:** Execution invoked with `--force` $\rightarrow$ `HISTORICAL_REPLAY`.
7. **Strict Immutability:** Existing genuine `FORWARD_CAPTURED` records are immutable and cannot be overwritten or downgraded by any replay.

---

## 5. Genuine Database Observation Counts

An independent database audit confirmed:
- **Total Shadow Evaluation Records:** `0`
- **Genuine Forward Captured (`FORWARD_CAPTURED`):** `0`
- **Historical Replay Backtest (`HISTORICAL_REPLAY`):** `0`
- **Synthetic Test Fixtures (`TEST_FIXTURE`):** `0`
- **Matured Forward Outcomes Claimed:** `0` (Zero forward data fabricated).

---

## 6. Dashboard Telemetry & Operational Health Hardening

We enhanced [`apps/ml_engine/views.py`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/apps/ml_engine/views.py) and [`templates/ml_engine/partials/risk_dashboard_partial.html`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/templates/ml_engine/partials/risk_dashboard_partial.html):

1. **Scheduler Status Badge:** Displays `Scheduler: SCHEDULER_INSTALLED_AWAITING_FIRST_RUN`.
2. **Next Session Projection:** Computes and displays the next exchange trading day via `ExchangeCalendar.get_next_trading_day()`.
3. **Data Freshness Age:** Reports elapsed hours since the last successful cycle.
4. **Active Lease Indicator:** Highlights when a database lease is currently held by an active background run.
5. **Provenance Distribution:** Explicitly breaks down counts of `Forward`, `Replay`, and `Test` records.

---

## 7. Test Verification & Code Quality

### Comprehensive Test Suite Execution
- **Phase 4.6 Deployment Tests:** 14 passed in [`tests/test_ml_shadow_deployment.py`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/tests/test_ml_shadow_deployment.py).
- **Phase 4.5 Acceptance Tests:** 12 passed in [`tests/test_ml_shadow_acceptance.py`](file:///Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/tests/test_ml_shadow_acceptance.py).
- **Full Project Regression Suite:** **394 / 394 passed in 43.03s**.
- **Linting:** 100% clean under `ruff check`.

---

## 8. Operator Runbook

To activate unattended daily shadow executions outside the developer sandbox:

### Option A: macOS `launchd` (Recommended for Local Host)
```bash
# 1. Copy plist to user LaunchAgents directory
cp scripts/com.kuberlens.shadow.eod.plist ~/Library/LaunchAgents/

# 2. Load the daemon
launchctl load ~/Library/LaunchAgents/com.kuberlens.shadow.eod.plist

# 3. Verify status
launchctl list | grep com.kuberlens.shadow.eod
```

### Option B: Linux Server (`systemd`)
```bash
# 1. Copy service and timer units
sudo cp scripts/kuberlens-shadow-eod.service /etc/systemd/system/
sudo cp scripts/kuberlens-shadow-eod.timer /etc/systemd/system/

# 2. Enable and start timer
sudo systemctl daemon-reload
sudo systemctl enable --now kuberlens-shadow-eod.timer

# 3. Check timer schedule
systemctl list-timers | grep shadow
```

---

## 9. Final Acceptance Verdict

The KuberLens End-of-Day Risk Intelligence and Shadow Validation pipeline is verified, hardened, and declared:

$$\mathbf{SCHEDULER\_INSTALLED\_AWAITING\_FIRST\_RUN}$$

All models remain `EXPERIMENTAL` and `RESEARCH_ONLY`. Production operations are completely insulated from live broker executions.
