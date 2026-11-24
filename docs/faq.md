# Frequently Asked Questions (FAQ)

### Q: Why does the Stock Header show "15m delay"?
**A:** KuberLens connects to free public market data feeds which enforce a standard 15-minute delay during exchange trading hours (`09:15 - 15:30 IST`). Official End-Of-Day (EOD) closing bars are refreshed after market close.

### Q: What does "Sync status: Zero candles returned by provider" mean?
**A:** This indicates that the external data provider was polled, but no newer completed trading candles are available (e.g. on non-trading weekends, official exchange holidays, or intraday before exchange EOD settlement).

### Q: Does a "Bullish Expansion (0.77)" forecast guarantee a positive trade?
**A:** No. All ML scores are probabilistic statistical signals based on historical feature distributions. Unforeseen market news, liquidity changes, or macroeconomic shifts can invalidate setups. Always utilize stop-losses.

### Q: How do I export my capital gains for tax filing?
**A:** Navigate to **System > Reports & Exports** (`/reports/`), choose the relevant Financial Year (e.g. FY 2025-26), and click **Download Tax P&L Statement (Excel/PDF)**.
