#!/usr/bin/env bash
# ==============================================================================
# KuberLens EOD Shadow Evaluation Automated Runner
# Complies with Master Specification § 18 and AIML Architecture v2.1
#
# Target Execution Time: 19:15 IST (Mon-Fri after NSE/BSE EOD Bhavcopy settlement)
# Timezone Conversion:
#   - Indian Standard Time (IST): 19:15 IST (UTC+05:30)
#   - Universal Coordinated Time (UTC): 13:45 UTC (19:15 - 05:30)
#
# Option A: Crontab on IST Host (or with CRON_TZ supported):
#   CRON_TZ=Asia/Kolkata
#   15 19 * * 1-5 /bin/bash /Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/scripts/run_shadow_eod_cron.sh
#
# Option B: Crontab on UTC Host (Standard Cloud Linux VM / AWS EC2):
#   45 13 * * 1-5 /bin/bash /Users/shreeshagundmi/python_scripts_shreesha/stockmarket_analytics_django/scripts/run_shadow_eod_cron.sh
#
# Option C: macOS launchd Service (Native Darwin Daemon):
#   cp scripts/com.kuberlens.shadow.eod.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.kuberlens.shadow.eod.plist
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Activate virtual environment
if [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.venv/bin/activate"
elif [ -f "/opt/venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "/opt/venv/bin/activate"
fi

PYTHON_EXEC="${PROJECT_ROOT}/.venv/bin/python"
if [ ! -x "${PYTHON_EXEC}" ]; then
    PYTHON_EXEC="$(command -v python3)"
fi

LOG_FILE="${PROJECT_ROOT}/logs/shadow_pipeline_cron.log"
mkdir -p "${PROJECT_ROOT}/logs"

echo "========================================================================" >> "${LOG_FILE}"
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting Automated EOD Ingestion & Shadow Pipeline..." >> "${LOG_FILE}"

# Step 1: Execute automated daily EOD market data ingestion for pilot equities & benchmark
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [Step 1/2] Ingesting authentic EOD candles..." >> "${LOG_FILE}"
"${PYTHON_EXEC}" manage.py ingest_eod_data >> "${LOG_FILE}" 2>&1 || true

# Step 2: Execute EOD Shadow Evaluation Pipeline with catchup and data readiness gate
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [Step 2/2] Running EOD shadow evaluation..." >> "${LOG_FILE}"
if "${PYTHON_EXEC}" manage.py run_shadow_eod_pipeline --ingest-eod --catchup-missed "$@" >> "${LOG_FILE}" 2>&1; then
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Shadow Pipeline completed successfully." >> "${LOG_FILE}"
    exit 0
else
    EXIT_CODE=$?
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Shadow Pipeline finished with exit code ${EXIT_CODE}." >> "${LOG_FILE}"
    exit "${EXIT_CODE}"
fi
