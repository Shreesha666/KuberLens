# Out-of-Sample Forward Shadow Evidence

<span class="badge-status badge-verified">Verified Working</span>

## Overview
The Forward Shadow Evaluation Pipeline operates strictly out-of-sample:
- Logs candidate setups without contaminating production rules.
- Tracks 5-day, 10-day, and 20-day forward returns.
- Deducts realistic Indian equity cash delivery (CNC) charges:
  - Securities Transaction Tax (STT): 0.1% buy & sell turnover.
  - Exchange turnover fees, GST (18%), SEBI turnover charges, and Stamp Duty (0.015%).
  - Execution slippage: 0.05% per side.
