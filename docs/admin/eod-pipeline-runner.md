# Batch EOD Shadow Pipeline Runner

<span class="badge-status badge-verified">Verified Working</span>

- **Admin URL:** `/admin/ml_engine/mlshadowpipelinerun/run-pipeline/`
- **CLI Command:** `python manage.py run_shadow_eod_pipeline`

## 1. Operational Overview
The **End-Of-Day (EOD) Shadow Pipeline** is the automated batch process that runs every evening after Indian market close (16:30 IST).

```mermaid
flowchart TD
    Start[16:30 IST Trigger] --> Sync[Sync EOD Daily Candles from NSE/Yahoo]
    Sync --> Ind[Compute Technical Indicators: SMA, RSI, MACD, ADX]
    Ind --> Reg[Classify Market Regimes: Bullish, Bearish, Range-Bound]
    Reg --> Veto[Run MLRiskVetoEngine: Compute 5-Pillar Scores]
    Veto --> Shadow[Evaluate Mature Shadow Setups 5d, 10d, 20d Returns]
    Shadow --> End[Log Pipeline Execution Summary to DB]
```

## 2. CLI Execution
To manually trigger the pipeline for the entire stock universe:
```bash
python manage.py run_shadow_eod_pipeline
```

To run for a specific symbol:
```bash
python manage.py run_shadow_eod_pipeline --symbol COALINDIA
```
