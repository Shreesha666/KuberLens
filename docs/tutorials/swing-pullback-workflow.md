# Tutorial: Swing Pullback Workflow

## Goal
Identify, validate, and simulate a high-conviction swing pullback trade on an NSE large-cap stock.

### Step 1: Scan for Pullback Setups
1. Navigate to **Trading > Swing Scanner** (`/trading/`).
2. Select the **Pullback to 20 EMA** scan preset.
3. Verify that candidate stocks have daily trading volume $> 500,000$.

### Step 2: Validate via Single Stock Intelligence
1. Open the candidate stock detail page (e.g. `/stocks/COALINDIA/`).
2. Verify **Pillar 3**: Market Regime is `BULLISH_TREND` or healthy `RANGE_BOUND`.
3. Verify **Pillar 4**: Risk Score is $\le 40$ and badge displays <span class="badge-status badge-verified">RISK PASSED</span>.
4. Verify **Pillar 1**: Price is holding above the rising 50-day and 200-day SMAs.

### Step 3: Calculate Position Size & Execute
1. Navigate to **Trading > Risk Management** (`/trading/risk-management/`).
2. Enter your account capital and set risk to 1%.
3. Enter entry price and stop loss (just below recent swing low).
4. Note the calculated share quantity and execute the order in **Paper Trading Terminal**.
