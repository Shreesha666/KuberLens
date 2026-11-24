# Market Feeds, Data Sources & EOD Sync

<span class="badge-status badge-verified">Verified Working</span>

![Data Sources Configuration](../assets/screenshots/35_data_sources.png)

## Data Architecture & Freshness Pipeline

KuberLens utilizes a multi-tiered data fetching architecture:

```mermaid
flowchart TD
    Req[User Requests Stock Candle Data] --> CacheCheck{Cache Fresh?<br/>TTL 15m}
    CacheCheck -- YES --> ServeCache[Serve Cached Data from Redis/DB]
    CacheCheck -- NO --> Provider[Fetch from Yahoo Finance / NSE Direct]
    Provider --> ValCheck{Candles Returned?}
    ValCheck -- YES --> Store[Persist to DB & Update Cache]
    ValCheck -- NO --> Fallback[Fallback to Stored Historical EOD]
    Store --> Render[Render UI & Update Indicators]
    Fallback --> WarnBadge[Display Cache Warning: Zero candles returned]
```

## Understanding Data Freshness Badges

On the Stock Intelligence header and overview screens, you will encounter the following real-time badges:

1. <span class="badge-status badge-delayed">DELAYED (15m delay)</span>: Indicates intraday market prices are delayed by 15 minutes as per standard non-commercial exchange distribution terms.
2. <span class="badge-status badge-cached">CACHED</span>: Indicates candle data was retrieved from the local database cache within its 15-minute Time-To-Live (TTL) window, avoiding unnecessary external API rate limits.
3. `EOD Session: Nov. 23, 2026`: Displays the mature calendar date of the last completed trading day.
4. `Sync status: Zero candles returned by provider`: Appears when the upstream provider returned no new daily bars (e.g. during market holidays, weekends, or before exchange EOD settlement).

## Manual EOD Synchronization
To manually pull the latest candles and trigger recalculation of moving averages, RSI, and ML regimes:
1. Navigate to the stock detail page (e.g. `/stocks/COALINDIA/`).
2. Click the **Sync EOD** button located in the data diagnostics toolbar.
3. The platform sends an asynchronous background request to refresh candles.
