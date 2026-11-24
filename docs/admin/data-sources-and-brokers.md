# Data Provider Failovers & Broker Connections

<span class="badge-status badge-verified">Verified Working</span>

- **Actual URLs:** `/settings/data-sources/` and `/brokers/`
- **Route Names:** `settings_app:data_sources`, `brokers:settings`

![Data Sources Configuration](../assets/screenshots/35_data_sources.png)
![Broker Connections](../assets/screenshots/36_broker_connections.png)

## Managing Market Feeds
- **Provider Ordering:** Configure primary and secondary fallback data feeds (Yahoo Finance, NSE Direct).
- **Rate Limiting & Cache:** Set default cache TTL (default 900 seconds / 15 minutes) to protect upstream API quotas.
- **Broker OAuth:** Connect Zerodha Kite Connect, Angel One SmartAPI, Upstox, or Dhan for live trade execution and portfolio synchronization.
