# PaperTrading Implementation Status Matrix & Architecture Specification

**Project:** KuberLens — Indian Stock Market Intelligence & Quantitative Analytics  
**Document Purpose:** Master blueprint, architectural specification, and living implementation tracker for the **PaperTrading Virtual Brokerage Module**.  
**References:**
- [Open-Papertrade (GitHub)](https://github.com/Open-Papertrade/Open-Papertrade) — Quantitative engine, portfolio state management, behavioral coaching.
- [TradePaper (GitHub)](https://github.com/adityas27/TradePaper) — Streamlined Indian market trading interface, order modal paradigms.  
**Last Updated:** 2026-11-18  
**Current State:** ⚪ **PLAN APPROVED & READY FOR PHASE 1 IMPLEMENTATION**

---

## 1. Status Legend

| Status | Meaning |
|---|---|
| 🟢 **COMPLETED** | Fully implemented, migrated, covered with tests, and meets all acceptance criteria |
| 🟡 **IN PROGRESS** | Currently being designed or implemented |
| ⚪ **NOT STARTED** | Scheduled in the roadmap but work has not begun |
| 🔴 **BLOCKED** | Work cannot proceed due to missing dependencies or external factors |

---

## 2. Core Architectural Principles

1. **Strict Zero-Contamination Isolation**:
   - Paper trading data resides in a dedicated app (`apps/paper_trading/`).
   - 100% physically decoupled from real user portfolios (`apps/portfolio/`), broker credentials (`apps/brokers/`), and Demat accounts. Real accounting and tax reports remain completely untouched.
2. **Realistic Indian Market Simulation (Not a Simplified Toy)**:
   - **Product Types**:
     - `CNC` (Cash & Carry / Delivery & Swing): 100% upfront cash required; held overnight.
     - `MIS` (Margin Intraday Square-off): 5× intraday leverage; auto-squared off at 15:20 IST.
   - **Order Types**:
     - `MARKET`: Instant simulated fill against live LTP with dynamic bid-ask slippage (0.05%–0.10%).
     - `LIMIT`: Pending order resting on book until live market price crosses limit threshold.
     - `SL-L` / `SL-M`: Stop-Loss triggers when market reaches activation threshold.
     - `GTT` (Good-Till-Triggered): Three-leg bracket order incorporating target and ATR stop loss.
   - **Statutory Taxes & Brokerage Deduction**:
     - Simulates real-world net P&L by deducting Securities Transaction Tax (STT), Exchange transaction charges, SEBI turnover fees, Stamp duty, and 18% GST.
3. **Deep KuberLens Ecosystem Synergy**:
   - **1-Click Autofill**: Order drawer auto-populates entry, target (T1/T2), and stop-loss from the quantitative recommendation engine.
   - **Swing Scanner Integration**: Direct "Paper Trade Setup" trigger from quantitative scanner cards.
   - **Trade Journal Bridge**: 1-click export of completed paper trades to the immutable `TradeJournal` for post-trade retrospective analysis.
   - **AI Behavioral Coaching**: Post-session analysis flagging revenge trading, premature exits, and stop-loss discipline.

---

## 3. Phase-by-Phase Roadmap & Delivery Status

| Phase | Description | Status | Deliverables / Components |
|---|---|:---:|---|
| **Phase 1: Foundation & Models** | Dedicated Django app, relational schema, migrations, and account signals | ⚪ **NOT STARTED** | `apps/paper_trading/`, `PaperAccount`, `PaperOrder`, `PaperPosition`, `PaperTrade`, auto-provisioning signal |
| **Phase 2: Execution & Tax Engine** | Order validation, margin calculator, slippage simulation, and Indian tax math | ⚪ **NOT STARTED** | `services/paper_trading/engine.py`, `tax_calculator.py`, limit order evaluation runner |
| **Phase 3: Interactive Order Drawer** | Kite-style slide-out order placement component with 1-click recommendations | ⚪ **NOT STARTED** | Alpine.js + HTMX drawer, integrated into `/stocks/<symbol>/` and Swing Scanner |
| **Phase 4: Paper Trading Terminal** | Full dedicated dashboard with positions, active orders, tradebook, and MTM updates | ⚪ **NOT STARTED** | `/papertrading/` terminal, equity curve chart, statistics cards, account reset modal |
| **Phase 5: Intelligence & Journal Sync** | Trade Journal export bridge and AI Behavioral Coach | ⚪ **NOT STARTED** | 1-click `TradeJournal` sync, discipline score, R:R violation alerts |
| **Phase 6: Testing & Performance** | Comprehensive regression tests and execution benchmarks | ⚪ **NOT STARTED** | `tests/test_paper_trading.py`, margin stress tests, multi-order execution verification |

---

## 4. Technical Specification

### 4.1 Data Models (`apps/paper_trading/models.py`)

```python
# 1. Virtual Account
class PaperAccount(AuditedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="paper_account")
    initial_capital = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("1000000.00")) # ₹10 Lakhs
    cash_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("1000000.00"))
    margin_utilized = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    realized_pnl = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

# 2. Orders (Pending & Historical)
class PaperOrder(AuditedModel):
    account = models.ForeignKey(PaperAccount, on_delete=models.CASCADE, related_name="orders")
    listing = models.ForeignKey(ExchangeListing, on_delete=models.CASCADE, related_name="paper_orders")
    order_side = models.CharField(max_length=4, choices=[("BUY", "Buy"), ("SELL", "Sell")])
    product_type = models.CharField(max_length=4, choices=[("CNC", "Delivery (CNC)"), ("MIS", "Intraday (MIS)")])
    order_type = models.CharField(max_length=10, choices=[("MARKET", "Market"), ("LIMIT", "Limit"), ("SL_LIMIT", "SL-Limit"), ("SL_MARKET", "SL-Market")])
    quantity = models.PositiveIntegerField()
    limit_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    trigger_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    target_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    stop_loss_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    status = models.CharField(max_length=12, choices=[("PENDING", "Pending"), ("FILLED", "Filled"), ("CANCELLED", "Cancelled"), ("REJECTED", "Rejected")])
    rejection_reason = models.CharField(max_length=255, blank=True)

# 3. Open Positions (Real-time MTM)
class PaperPosition(AuditedModel):
    account = models.ForeignKey(PaperAccount, on_delete=models.CASCADE, related_name="positions")
    listing = models.ForeignKey(ExchangeListing, on_delete=models.CASCADE, related_name="paper_positions")
    product_type = models.CharField(max_length=4, choices=[("CNC", "Delivery"), ("MIS", "Intraday")])
    quantity = models.IntegerField() # Positive = Long, Negative = Short
    average_price = models.DecimalField(max_digits=12, decimal_places=4)
    current_price = models.DecimalField(max_digits=12, decimal_places=4)
    unrealized_pnl = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    stop_loss = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    target = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

# 4. Executed Trades (Tradebook Ledger)
class PaperTrade(AuditedModel):
    order = models.ForeignKey(PaperOrder, on_delete=models.CASCADE, related_name="trades")
    execution_price = models.DecimalField(max_digits=12, decimal_places=4)
    quantity = models.PositiveIntegerField()
    turnover = models.DecimalField(max_digits=14, decimal_places=2)
    brokerage = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("20.00")) # Flat ₹20 discount broker
    taxes_and_charges = models.DecimalField(max_digits=10, decimal_places=2) # STT + Exch + SEBI + Stamp + GST
    net_realized_pnl = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
```

---

### 4.2 Indian Statutory Charges Math (`services/paper_trading/tax_calculator.py`)

| Component | Delivery (CNC) | Intraday (MIS) | Notes |
|---|---|---|---|
| **Brokerage** | Flat ₹20 or 0.03% (lower) | Flat ₹20 or 0.03% (lower) | Discount brokerage model |
| **STT / CTT** | 0.1% on Buy & Sell | 0.025% on Sell only | Securities Transaction Tax |
| **Exchange Txn Charge** | 0.00297% of turnover | 0.00297% of turnover | NSE transaction fee |
| **GST** | 18% on (Brokerage + Txn Charges) | 18% on (Brokerage + Txn Charges) | Standard GST rate |
| **SEBI Turnover Fee** | ₹10 per crore (0.0001%) | ₹10 per crore (0.0001%) | Regulatory fee |
| **Stamp Duty** | 0.015% on Buy turnover | 0.003% on Buy turnover | Indian Stamp Act |

---

### 4.3 UI/UX Specifications

1. **Quick Order Drawer (Slide-out)**:
   - Floating action pill on Stock Detail (`/stocks/<symbol>/`): **"⚡ Paper Trade"**.
   - Keyboard shortcut: Press `B` (Buy) or `S` (Sell).
   - Dynamic real-time calculation:
     - `Turnover = Quantity × Price`
     - `Required Margin = Turnover` (for CNC) or `Turnover / 5` (for MIS).
     - Live validation: disables submit if `Required Margin > Available Cash`.
2. **Dedicated Terminal (`/papertrading/`)**:
   - **Header**: Capital Summary (Total Value, Cash, Margin Used, Today's PnL with green/red pill badges, Win Rate %).
   - **Tab 1: Positions**: Real-time MTM cards, 1-click "Exit / Square-off", "Trim 50%".
   - **Tab 2: Orders**: Active pending Limit / SL orders with cancel/modify buttons.
   - **Tab 3: Tradebook**: Historical executed orders with tax breakdown drill-down.
   - **Tab 4: Performance & Analytics**: Equity growth curve, Sharpe ratio, win/loss stats.
   - **Header Action**: "🔄 Reset Account" button opening a confirmation modal.

---

## 5. Verification & Acceptance Criteria

- [ ] `PaperAccount` auto-provisions on first visit with configurable ₹10,00,000 balance.
- [ ] Market orders execute immediately with slippage within 0.05% of latest quote.
- [ ] Limit orders remain pending until LTP breaches the trigger/limit price.
- [ ] Exact statutory tax breakdown matches standard Zerodha / NSE brokerage calculators.
- [ ] Positions update real-time via HTMX polling (`hx-trigger="every 5s"`).
- [ ] Resetting the account purges existing paper trades/positions cleanly without affecting real portfolios.
- [ ] Minimum 20 automated unit and integration tests passing in `tests/test_paper_trading.py`.
