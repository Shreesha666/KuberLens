# EOD Pipeline & Cache Diagnostics

<span class="badge-status badge-verified">Verified Working</span>

## Understanding Cache Messages
When inspecting the diagnostics bar beneath the stock price:

```text
[x] EOD Session: Nov. 23, 2026 | YAHOO | feat-v2.1.0 | [Sync EOD] | (i) Sync status: Zero candles returned by provider.
```

- **EOD Session Date:** Represents the latest trading session for which official closing candles are recorded.
- **Provider:** Shows which feed supplied the data (e.g. `YAHOO` or `NSE`).
- **Feature Version:** Shows the active ML feature engineering pipeline version (`feat-v2.1.0`).
- **Sync status message:**
  - `Zero candles returned by provider`: The provider was polled, but no newer trading day has closed. This is normal on weekends, market holidays, or during market hours before EOD settlement.
