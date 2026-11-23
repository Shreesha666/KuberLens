/**
 * Institutional Stock Market Analytics Charting Engine
 * Powered by:
 * 1. TradingView Lightweight Charts (v4.2.1) - Primary Candlestick, Volume & Technical Indicator Engine
 * 2. Apache ECharts (v5.5.1) - Dashboard Analytics & Portfolio Visualizations
 *
 * Modeled after top institutional broker interfaces (TradingView / Zerodha Kite).
 * Supports comprehensive technical indicators: SMA (20, 50, 200), EMA (9, 20, 50), VWAP,
 * Bollinger Bands, Donchian High/Low Channels, RSI (14), MACD, Stochastic RSI, and ATR (14).
 */

// ============================================================================
// 1. TRADINGVIEW LIGHTWEIGHT CHARTS ENGINE
// ============================================================================

function normalizeChartDate(t) {
    if (!t) return new Date().toISOString().split('T')[0];
    if (typeof t === 'string') return t.split('T')[0];
    if (typeof t === 'object') {
        if (t.year !== undefined && t.month !== undefined && t.day !== undefined) {
            const m = String(t.month).padStart(2, '0');
            const d = String(t.day).padStart(2, '0');
            return `${t.year}-${m}-${d}`;
        }
        if (t instanceof Date) return t.toISOString().split('T')[0];
    }
    if (typeof t === 'number') {
        const d = new Date(t > 1e11 ? t : t * 1000);
        return d.toISOString().split('T')[0];
    }
    return String(t);
}

class TradingViewStockChart {
    constructor(containerId, dataUrl, options = {}) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.dataUrl = dataUrl;
        this.options = options;

        this.chart = null;
        this.rsiChart = null;
        this.macdChart = null;
        this.stochChart = null;
        this.atrChart = null;

        // Series references
        this.candlestickSeries = null;
        this.lineSeries = null;
        this.areaSeries = null;
        this.volumeSeries = null;

        // Moving Average & Trend Overlays
        this.sma20Series = null;
        this.sma50Series = null;
        this.sma200Series = null;
        this.ema9Series = null;
        this.ema20Series = null;
        this.ema50Series = null;
        this.vwapSeries = null;
        this.supertrendBullSeries = null;
        this.supertrendBearSeries = null;
        this.sarSeries = null;

        // Volatility & Channel Overlays
        this.bbUpperSeries = null;
        this.bbLowerSeries = null;
        this.donchianUpperSeries = null;
        this.donchianLowerSeries = null;

        // Price lines (Trade Levels & Fibonacci)
        this.priceLines = [];
        this.fibPriceLines = [];

        // Cached Data
        this.rawCandles = [];
        this.levels = null;
        this.fibonacci = null;
        this.currentDays = 180;
        this.currentChartType = 'candlestick';

        // Indicator visibility state
        this.indicatorState = {
            sma20: true,
            sma50: true,
            sma200: false,
            ema9: false,
            ema20: false,
            ema50: false,
            vwap: false,
            supertrend: false,
            sar: false,
            fibonacci: false,
            bb: false,
            donchian: false,
            rsi: false,
            macd: false,
            stoch: false,
            atr: false,
            levels: true,
        };

        if (this.container) {
            this.init();
        }
    }

    isDarkMode() {
        const docTheme = document.documentElement.getAttribute('data-bs-theme');
        if (docTheme) return docTheme === 'dark';
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    getThemeColors() {
        const isDark = this.isDarkMode();
        return {
            bg: isDark ? '#131722' : '#ffffff',
            text: isDark ? '#787b86' : '#5d606b',
            grid: isDark ? 'rgba(42, 46, 57, 0.45)' : 'rgba(240, 243, 250, 0.85)',
            border: isDark ? '#2a2e39' : '#e0e3eb',
            crosshair: isDark ? 'rgba(120, 123, 134, 0.5)' : 'rgba(150, 153, 164, 0.5)',
            // Top broker financial colors (TradingView / Zerodha Kite palette)
            upColor: '#089981',       // TradingView Emerald
            downColor: '#f23645',     // TradingView Crimson
            sma20Color: '#2563eb',    // Royal Blue
            sma50Color: '#f59e0b',    // Amber
            sma200Color: '#e11d48',   // Rose Crimson (Long-Term Trend)
            ema9Color: '#06b6d4',     // Cyan (Fast Momentum Trigger)
            ema20Color: '#8b5cf6',    // Violet (Swing Momentum)
            ema50Color: '#ec4899',    // Pink (Medium Trend)
            vwapColor: '#eab308',     // Gold (Volume-Weighted Average)
            supertrendBull: '#089981',// Emerald Bull
            supertrendBear: '#f23645',// Crimson Bear
            sarColor: '#f59e0b',      // Amber SAR
            bbColor: 'rgba(139, 92, 246, 0.65)',
        };
    }

    init() {
        if (typeof LightweightCharts === 'undefined') {
            console.error('TradingView Lightweight Charts library is not loaded.');
            return;
        }

        this.destroy();

        const colors = this.getThemeColors();
        const width = this.container.clientWidth || 800;
        const height = this.options.height || 460;

        // Create Main TradingView Chart
        this.chart = LightweightCharts.createChart(this.container, {
            width: width,
            height: height,
            layout: {
                background: { type: 'solid', color: colors.bg },
                textColor: colors.text,
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace',
                fontSize: 11,
            },
            grid: {
                vertLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted },
                horzLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
                vertLine: {
                    color: colors.crosshair,
                    width: 1,
                    style: LightweightCharts.LineStyle.Dashed,
                    labelBackgroundColor: colors.border,
                },
                horzLine: {
                    color: colors.crosshair,
                    width: 1,
                    style: LightweightCharts.LineStyle.Dashed,
                    labelBackgroundColor: colors.border,
                },
            },
            rightPriceScale: {
                borderColor: colors.border,
                scaleMargins: {
                    top: 0.1,
                    bottom: 0.18,
                },
                alignLabels: true,
            },
            timeScale: {
                borderColor: colors.border,
                timeVisible: true,
                secondsVisible: false,
                fixLeftEdge: true,
                fixRightEdge: true,
            },
            handleScroll: { mouseWheel: true, pressedMouseMove: true },
            handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
        });

        // 1. Candlestick Series (Main Price)
        this.candlestickSeries = this.chart.addCandlestickSeries({
            upColor: colors.upColor,
            downColor: colors.downColor,
            borderVisible: false,
            wickUpColor: colors.upColor,
            wickDownColor: colors.downColor,
        });

        // 2. Volume Series (Isolated scale, occupying only bottom 16%)
        this.volumeSeries = this.chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
        });

        this.chart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.84, bottom: 0 },
            visible: false,
        });

        // 3. Moving Average & Trend Overlays
        this.sma20Series = this.chart.addLineSeries({
            color: colors.sma20Color,
            lineWidth: 1.5,
            title: 'SMA 20',
            crosshairMarkerVisible: true,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.sma50Series = this.chart.addLineSeries({
            color: colors.sma50Color,
            lineWidth: 1.5,
            title: 'SMA 50',
            crosshairMarkerVisible: true,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.sma200Series = this.chart.addLineSeries({
            color: colors.sma200Color,
            lineWidth: 1.5,
            title: 'SMA 200',
            crosshairMarkerVisible: true,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.ema9Series = this.chart.addLineSeries({
            color: colors.ema9Color,
            lineWidth: 1.5,
            title: 'EMA 9',
            crosshairMarkerVisible: true,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.ema20Series = this.chart.addLineSeries({
            color: colors.ema20Color,
            lineWidth: 1.5,
            title: 'EMA 20',
            crosshairMarkerVisible: true,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.ema50Series = this.chart.addLineSeries({
            color: colors.ema50Color,
            lineWidth: 1.5,
            title: 'EMA 50',
            crosshairMarkerVisible: true,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.vwapSeries = this.chart.addLineSeries({
            color: colors.vwapColor,
            lineWidth: 1.5,
            title: 'VWAP',
            crosshairMarkerVisible: true,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.supertrendBullSeries = this.chart.addLineSeries({
            color: colors.supertrendBull,
            lineWidth: 2,
            title: 'SuperTrend Bull',
            crosshairMarkerVisible: true,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.supertrendBearSeries = this.chart.addLineSeries({
            color: colors.supertrendBear,
            lineWidth: 2,
            title: 'SuperTrend Bear',
            crosshairMarkerVisible: true,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.sarSeries = this.chart.addLineSeries({
            color: colors.sarColor,
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dotted,
            pointMarkersVisible: true,
            title: 'Parabolic SAR',
            crosshairMarkerVisible: true,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        // 4. Volatility & Channel Overlays
        this.bbUpperSeries = this.chart.addLineSeries({
            color: colors.bbColor,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            title: 'BB Upper',
            crosshairMarkerVisible: false,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.bbLowerSeries = this.chart.addLineSeries({
            color: colors.bbColor,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            title: 'BB Lower',
            crosshairMarkerVisible: false,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.donchianUpperSeries = this.chart.addLineSeries({
            color: 'rgba(8, 153, 129, 0.75)',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            title: 'Resistance (20D)',
            crosshairMarkerVisible: false,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        this.donchianLowerSeries = this.chart.addLineSeries({
            color: 'rgba(242, 54, 69, 0.75)',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            title: 'Support (20D)',
            crosshairMarkerVisible: false,
            visible: false,
            lastValueVisible: false,
            priceLineVisible: false,
        });

        // Crosshair move handler
        this.chart.subscribeCrosshairMove((param) => this.handleCrosshairMove(param));

        // Auto-Resize Observer
        this.resizeObserver = new ResizeObserver((entries) => {
            if (!entries || entries.length === 0 || !this.chart) return;
            const newRect = entries[0].contentRect;
            if (newRect.width > 0) {
                this.chart.applyOptions({ width: newRect.width });
                if (this.rsiChart) this.rsiChart.applyOptions({ width: newRect.width });
                if (this.macdChart) this.macdChart.applyOptions({ width: newRect.width });
                if (this.stochChart) this.stochChart.applyOptions({ width: newRect.width });
                if (this.atrChart) this.atrChart.applyOptions({ width: newRect.width });
            }
        });
        this.resizeObserver.observe(this.container);

        this.loadData(this.currentDays);
        this.bindToolbarEvents();
        this.observeThemeChanges();
    }

    loadData(days = 180) {
        this.currentDays = days;
        const url = `${this.dataUrl}?days=${days}`;

        fetch(url)
            .then(res => res.json())
            .then(json => {
                this.rawCandles = json.candles || [];
                this.levels = json.levels || null;
                this.fibonacci = json.fibonacci || null;
                this.populateSeries();
            })
            .catch(err => {
                console.error("Failed to load TradingView chart data:", err);
            });
    }

    refreshData(silent = true) {
        if (!this.dataUrl) return;
        const url = `${this.dataUrl}?days=${this.currentDays}&_t=${Date.now()}`;
        fetch(url)
            .then(res => res.json())
            .then(json => {
                this.rawCandles = json.candles || [];
                this.levels = json.levels || null;
                this.fibonacci = json.fibonacci || null;
                this.populateSeries();
            })
            .catch(err => {
                if (!silent) console.error("Failed to sync TradingView chart data:", err);
            });
    }

    updateLiveBar(quoteData) {
        if (!this.chart || !quoteData) return;
        const price = parseFloat(quoteData.price);
        if (isNaN(price) || price <= 0) return;

        const openVal = quoteData.open ? parseFloat(quoteData.open) : null;
        const highVal = quoteData.high ? parseFloat(quoteData.high) : null;
        const lowVal = quoteData.low ? parseFloat(quoteData.low) : null;
        const volVal = quoteData.volume ? parseInt(quoteData.volume, 10) : 0;

        // Default to today's date YYYY-MM-DD
        const todayStr = normalizeChartDate(quoteData.time);

        let lastCandle = (this.rawCandles && this.rawCandles.length > 0)
            ? this.rawCandles[this.rawCandles.length - 1]
            : null;

        let targetTime = todayStr;
        let open = openVal || price;
        let high = highVal || price;
        let low = lowVal || price;
        let volume = volVal;

        if (lastCandle) {
            const lastCandleDate = normalizeChartDate(lastCandle.time);
            if (lastCandleDate === todayStr) {
                // Update today's existing candle in real-time
                targetTime = todayStr;
                open = lastCandle.open;
                high = Math.max(lastCandle.high, price, highVal || price);
                low = Math.min(lastCandle.low, price, lowVal || price);
                volume = volVal || lastCandle.volume;
                lastCandle.close = price;
                lastCandle.high = high;
                lastCandle.low = low;
                lastCandle.volume = volume;
            } else if (lastCandleDate < todayStr) {
                // Advance to a new forming candle for today
                targetTime = todayStr;
                open = openVal || lastCandle.close || price;
                high = Math.max(open, price, highVal || price);
                low = Math.min(open, price, lowVal || price);
                const newCandle = { time: targetTime, open, high, low, close: price, volume };
                this.rawCandles.push(newCandle);
            }
        }

        const bar = {
            time: targetTime,
            open: open,
            high: high,
            low: low,
            close: price,
            volume: volume
        };

        try {
            if (this.candlestickSeries) {
                this.candlestickSeries.update(bar);
            }
            if (this.lineSeries) {
                this.lineSeries.update({ time: targetTime, value: price });
            }
            if (this.areaSeries) {
                this.areaSeries.update({ time: targetTime, value: price });
            }
            if (this.volumeSeries && volume > 0) {
                this.volumeSeries.update({
                    time: targetTime,
                    value: volume,
                    color: price >= open ? 'rgba(34, 197, 94, 0.45)' : 'rgba(239, 68, 68, 0.45)'
                });
            }
            this.updateLegend(bar);
        } catch (e) {
            console.warn("[TradingViewStockChart] Error updating live bar:", e);
        }
    }

    populateSeries() {
        if (!this.chart || !this.rawCandles || this.rawCandles.length === 0) return;

        const candleData = [];
        const volumeData = [];
        const sma20Data = [];
        const sma50Data = [];
        const sma200Data = [];
        const ema9Data = [];
        const ema20Data = [];
        const ema50Data = [];
        const vwapData = [];
        const stBullData = [];
        const stBearData = [];
        const sarData = [];
        const bbUpperData = [];
        const bbLowerData = [];
        const donchianUpperData = [];
        const donchianLowerData = [];
        const rsiData = [];
        const macdLineData = [];
        const macdSignalData = [];
        const macdHistData = [];
        const stochKData = [];
        const stochDData = [];
        const atrData = [];

        for (const c of this.rawCandles) {
            const time = c.time;
            candleData.push({ time, open: c.open, high: c.high, low: c.low, close: c.close });

            const isUp = c.close >= c.open;
            volumeData.push({
                time,
                value: c.volume,
                color: isUp ? 'rgba(8, 153, 129, 0.25)' : 'rgba(242, 54, 69, 0.25)',
            });

            if (c.sma20 !== null && c.sma20 !== undefined) sma20Data.push({ time, value: c.sma20 });
            if (c.sma50 !== null && c.sma50 !== undefined) sma50Data.push({ time, value: c.sma50 });
            if (c.sma200 !== null && c.sma200 !== undefined) sma200Data.push({ time, value: c.sma200 });
            if (c.ema9 !== null && c.ema9 !== undefined) ema9Data.push({ time, value: c.ema9 });
            if (c.ema20 !== null && c.ema20 !== undefined) ema20Data.push({ time, value: c.ema20 });
            if (c.ema50 !== null && c.ema50 !== undefined) ema50Data.push({ time, value: c.ema50 });
            if (c.vwap !== null && c.vwap !== undefined) vwapData.push({ time, value: c.vwap });

            // SuperTrend (Clean segmented lines using whitespace breaks)
            if (c.supertrend !== null && c.supertrend !== undefined) {
                if (c.supertrend_dir === 1) {
                    stBullData.push({ time, value: c.supertrend });
                    stBearData.push({ time });
                } else {
                    stBearData.push({ time, value: c.supertrend });
                    stBullData.push({ time });
                }
            }

            // Parabolic SAR
            if (c.sar !== null && c.sar !== undefined) sarData.push({ time, value: c.sar });

            if (c.bb_upper !== null && c.bb_upper !== undefined) bbUpperData.push({ time, value: c.bb_upper });
            if (c.bb_lower !== null && c.bb_lower !== undefined) bbLowerData.push({ time, value: c.bb_lower });
            if (c.resistance !== null && c.resistance !== undefined) donchianUpperData.push({ time, value: c.resistance });
            if (c.support !== null && c.support !== undefined) donchianLowerData.push({ time, value: c.support });
            if (c.rsi14 !== null && c.rsi14 !== undefined) rsiData.push({ time, value: c.rsi14 });
            if (c.macd_line !== null && c.macd_line !== undefined) macdLineData.push({ time, value: c.macd_line });
            if (c.macd_signal !== null && c.macd_signal !== undefined) macdSignalData.push({ time, value: c.macd_signal });
            if (c.macd_hist !== null && c.macd_hist !== undefined) {
                macdHistData.push({ time, value: c.macd_hist, color: c.macd_hist >= 0 ? '#089981' : '#f23645' });
            }
            if (c.stoch_k !== null && c.stoch_k !== undefined) stochKData.push({ time, value: c.stoch_k });
            if (c.stoch_d !== null && c.stoch_d !== undefined) stochDData.push({ time, value: c.stoch_d });
            if (c.atr14 !== null && c.atr14 !== undefined) atrData.push({ time, value: c.atr14 });
        }

        // Apply Chart Types
        if (this.currentChartType === 'candlestick') {
            this.candlestickSeries.setData(candleData);
        } else if (this.currentChartType === 'area') {
            if (this.areaSeries) this.areaSeries.setData(candleData.map(c => ({ time: c.time, value: c.close })));
        } else if (this.currentChartType === 'line') {
            if (this.lineSeries) this.lineSeries.setData(candleData.map(c => ({ time: c.time, value: c.close })));
        }

        this.volumeSeries.setData(volumeData);
        this.sma20Series.setData(sma20Data);
        this.sma50Series.setData(sma50Data);
        this.sma200Series.setData(sma200Data);
        this.ema9Series.setData(ema9Data);
        this.ema20Series.setData(ema20Data);
        this.ema50Series.setData(ema50Data);
        this.vwapSeries.setData(vwapData);
        this.supertrendBullSeries.setData(stBullData);
        this.supertrendBearSeries.setData(stBearData);
        this.sarSeries.setData(sarData);
        this.bbUpperSeries.setData(bbUpperData);
        this.bbLowerSeries.setData(bbLowerData);
        this.donchianUpperSeries.setData(donchianUpperData);
        this.donchianLowerSeries.setData(donchianLowerData);

        // Synchronize Visibility
        this.sma20Series.applyOptions({ visible: this.indicatorState.sma20 });
        this.sma50Series.applyOptions({ visible: this.indicatorState.sma50 });
        this.sma200Series.applyOptions({ visible: this.indicatorState.sma200 });
        this.ema9Series.applyOptions({ visible: this.indicatorState.ema9 });
        this.ema20Series.applyOptions({ visible: this.indicatorState.ema20 });
        this.ema50Series.applyOptions({ visible: this.indicatorState.ema50 });
        this.vwapSeries.applyOptions({ visible: this.indicatorState.vwap });
        this.supertrendBullSeries.applyOptions({ visible: this.indicatorState.supertrend });
        this.supertrendBearSeries.applyOptions({ visible: this.indicatorState.supertrend });
        this.sarSeries.applyOptions({ visible: this.indicatorState.sar });
        this.bbUpperSeries.applyOptions({ visible: this.indicatorState.bb });
        this.bbLowerSeries.applyOptions({ visible: this.indicatorState.bb });
        this.donchianUpperSeries.applyOptions({ visible: this.indicatorState.donchian });
        this.donchianLowerSeries.applyOptions({ visible: this.indicatorState.donchian });

        // Trade Levels (SL, T1, T2)
        this.renderTradeLevels();

        // Fibonacci Retracements
        this.renderFibonacciLevels();

        // Cached Data for Sub-Panes
        this.cachedSubPaneData = {
            rsi: rsiData,
            macdLine: macdLineData,
            macdSignal: macdSignalData,
            macdHist: macdHistData,
            stochK: stochKData,
            stochD: stochDData,
            atr: atrData,
        };

        if (this.indicatorState.rsi) this.renderRsiPane(rsiData);
        if (this.indicatorState.macd) this.renderMacdPane(macdLineData, macdSignalData, macdHistData);
        if (this.indicatorState.stoch) this.renderStochPane(stochKData, stochDData);
        if (this.indicatorState.atr) this.renderAtrPane(atrData);

        this.chart.timeScale().fitContent();

        if (this.rawCandles.length > 0) {
            this.updateLegend(this.rawCandles[this.rawCandles.length - 1]);
        }
    }

    renderTradeLevels() {
        for (const pl of this.priceLines) {
            try { this.candlestickSeries.removePriceLine(pl); } catch (e) {}
        }
        this.priceLines = [];

        if (!this.indicatorState.levels || !this.levels) return;

        // Stop Loss
        if (this.levels.stop_loss && this.levels.stop_loss > 0) {
            this.priceLines.push(this.candlestickSeries.createPriceLine({
                price: parseFloat(this.levels.stop_loss),
                color: '#ef4444',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'SL',
            }));
        }

        // Target 1
        if (this.levels.target_1 && this.levels.target_1 > 0) {
            this.priceLines.push(this.candlestickSeries.createPriceLine({
                price: parseFloat(this.levels.target_1),
                color: '#089981',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'T1',
            }));
        }

        // Target 2
        if (this.levels.target_2 && this.levels.target_2 > 0) {
            this.priceLines.push(this.candlestickSeries.createPriceLine({
                price: parseFloat(this.levels.target_2),
                color: '#06b6d4',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'T2',
            }));
        }
    }

    renderFibonacciLevels() {
        for (const pl of this.fibPriceLines) {
            try { this.candlestickSeries.removePriceLine(pl); } catch (e) {}
        }
        this.fibPriceLines = [];

        if (!this.indicatorState.fibonacci) return;

        let fib = this.fibonacci;
        if (!fib && this.rawCandles.length > 0) {
            let high = -Infinity;
            let low = Infinity;
            for (const c of this.rawCandles) {
                if (c.high > high) high = c.high;
                if (c.low < low) low = c.low;
            }
            const diff = high - low;
            if (diff > 0) {
                fib = {
                    level_0: high,
                    level_236: +(high - (0.236 * diff)).toFixed(2),
                    level_382: +(high - (0.382 * diff)).toFixed(2),
                    level_500: +(high - (0.500 * diff)).toFixed(2),
                    level_618: +(high - (0.618 * diff)).toFixed(2),
                    level_786: +(high - (0.786 * diff)).toFixed(2),
                    level_100: low,
                };
            }
        }

        if (!fib) return;

        const fibDefs = [
            { key: 'level_0', title: 'Fib 0.0%', color: '#94a3b8', lineStyle: LightweightCharts.LineStyle.Solid },
            { key: 'level_236', title: 'Fib 23.6%', color: '#06b6d4', lineStyle: LightweightCharts.LineStyle.Dashed },
            { key: 'level_382', title: 'Fib 38.2%', color: '#8b5cf6', lineStyle: LightweightCharts.LineStyle.Dashed },
            { key: 'level_500', title: 'Fib 50.0%', color: '#f59e0b', lineStyle: LightweightCharts.LineStyle.Dashed },
            { key: 'level_618', title: 'Fib 61.8% (Golden)', color: '#10b981', lineStyle: LightweightCharts.LineStyle.Solid },
            { key: 'level_786', title: 'Fib 78.6%', color: '#ec4899', lineStyle: LightweightCharts.LineStyle.Dashed },
            { key: 'level_100', title: 'Fib 100.0%', color: '#94a3b8', lineStyle: LightweightCharts.LineStyle.Solid },
        ];

        for (const def of fibDefs) {
            const val = fib[def.key];
            if (val !== undefined && val !== null && val > 0) {
                this.fibPriceLines.push(this.candlestickSeries.createPriceLine({
                    price: parseFloat(val),
                    color: def.color,
                    lineWidth: def.lineStyle === LightweightCharts.LineStyle.Solid ? 1.5 : 1,
                    lineStyle: def.lineStyle,
                    axisLabelVisible: true,
                    title: def.title,
                }));
            }
        }
    }

    renderRsiPane(rsiData) {
        const rsiContainer = document.getElementById('tradingview-rsi-container');
        if (!rsiContainer) return;
        rsiContainer.classList.remove('d-none');

        if (!this.rsiChart) {
            const colors = this.getThemeColors();
            this.rsiChart = LightweightCharts.createChart(rsiContainer, {
                width: this.container.clientWidth,
                height: 120,
                layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text, fontSize: 10 },
                grid: { vertLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted }, horzLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted } },
                rightPriceScale: { borderColor: colors.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
                timeScale: { visible: false },
            });

            this.rsiSeries = this.rsiChart.addLineSeries({ color: '#8b5cf6', lineWidth: 1.5, title: 'RSI 14' });
            this.rsiSeries.createPriceLine({ price: 70, color: '#ef4444', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '70 OB' });
            this.rsiSeries.createPriceLine({ price: 30, color: '#089981', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '30 OS' });

            this.chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
                if (this.rsiChart && range) this.rsiChart.timeScale().setVisibleLogicalRange(range);
            });
        }
        if (this.rsiSeries && rsiData) this.rsiSeries.setData(rsiData);
    }

    renderMacdPane(lineData, signalData, histData) {
        const macdContainer = document.getElementById('tradingview-macd-container');
        if (!macdContainer) return;
        macdContainer.classList.remove('d-none');

        if (!this.macdChart) {
            const colors = this.getThemeColors();
            this.macdChart = LightweightCharts.createChart(macdContainer, {
                width: this.container.clientWidth,
                height: 120,
                layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text, fontSize: 10 },
                grid: { vertLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted }, horzLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted } },
                rightPriceScale: { borderColor: colors.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
                timeScale: { visible: false },
            });

            this.macdHistSeries = this.macdChart.addHistogramSeries({ lineWidth: 1, title: 'Histogram' });
            this.macdLineSeries = this.macdChart.addLineSeries({ color: '#2563eb', lineWidth: 1.5, title: 'MACD' });
            this.macdSignalSeries = this.macdChart.addLineSeries({ color: '#f59e0b', lineWidth: 1.5, title: 'Signal' });

            this.chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
                if (this.macdChart && range) this.macdChart.timeScale().setVisibleLogicalRange(range);
            });
        }
        if (this.macdHistSeries && histData) this.macdHistSeries.setData(histData);
        if (this.macdLineSeries && lineData) this.macdLineSeries.setData(lineData);
        if (this.macdSignalSeries && signalData) this.macdSignalSeries.setData(signalData);
    }

    renderStochPane(kData, dData) {
        const stochContainer = document.getElementById('tradingview-stoch-container');
        if (!stochContainer) return;
        stochContainer.classList.remove('d-none');

        if (!this.stochChart) {
            const colors = this.getThemeColors();
            this.stochChart = LightweightCharts.createChart(stochContainer, {
                width: this.container.clientWidth,
                height: 120,
                layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text, fontSize: 10 },
                grid: { vertLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted }, horzLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted } },
                rightPriceScale: { borderColor: colors.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
                timeScale: { visible: false },
            });

            this.stochKSeries = this.stochChart.addLineSeries({ color: '#2563eb', lineWidth: 1.5, title: '%K' });
            this.stochDSeries = this.stochChart.addLineSeries({ color: '#f59e0b', lineWidth: 1.5, title: '%D' });

            this.stochKSeries.createPriceLine({ price: 80, color: '#ef4444', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '80 OB' });
            this.stochKSeries.createPriceLine({ price: 20, color: '#089981', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: '20 OS' });

            this.chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
                if (this.stochChart && range) this.stochChart.timeScale().setVisibleLogicalRange(range);
            });
        }
        if (this.stochKSeries && kData) this.stochKSeries.setData(kData);
        if (this.stochDSeries && dData) this.stochDSeries.setData(dData);
    }

    renderAtrPane(atrData) {
        const atrContainer = document.getElementById('tradingview-atr-container');
        if (!atrContainer) return;
        atrContainer.classList.remove('d-none');

        if (!this.atrChart) {
            const colors = this.getThemeColors();
            this.atrChart = LightweightCharts.createChart(atrContainer, {
                width: this.container.clientWidth,
                height: 120,
                layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text, fontSize: 10 },
                grid: { vertLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted }, horzLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted } },
                rightPriceScale: { borderColor: colors.border, scaleMargins: { top: 0.1, bottom: 0.1 } },
                timeScale: { visible: false },
            });

            this.atrSeries = this.atrChart.addLineSeries({ color: '#06b6d4', lineWidth: 1.5, title: 'ATR (14)' });

            this.chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
                if (this.atrChart && range) this.atrChart.timeScale().setVisibleLogicalRange(range);
            });
        }
        if (this.atrSeries && atrData) this.atrSeries.setData(atrData);
    }

    setChartType(type) {
        if (type === this.currentChartType) return;
        this.currentChartType = type;

        const candleData = this.rawCandles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close }));
        const lineData = this.rawCandles.map(c => ({ time: c.time, value: c.close }));

        if (type === 'candlestick') {
            if (this.areaSeries) this.areaSeries.applyOptions({ visible: false });
            if (this.lineSeries) this.lineSeries.applyOptions({ visible: false });
            this.candlestickSeries.applyOptions({ visible: true });
            this.candlestickSeries.setData(candleData);
        } else if (type === 'area') {
            this.candlestickSeries.applyOptions({ visible: false });
            if (this.lineSeries) this.lineSeries.applyOptions({ visible: false });
            if (!this.areaSeries) {
                this.areaSeries = this.chart.addAreaSeries({
                    topColor: 'rgba(37, 99, 235, 0.28)',
                    bottomColor: 'rgba(37, 99, 235, 0.01)',
                    lineColor: '#2563eb',
                    lineWidth: 2,
                });
            }
            this.areaSeries.applyOptions({ visible: true });
            this.areaSeries.setData(lineData);
        } else if (type === 'line') {
            this.candlestickSeries.applyOptions({ visible: false });
            if (this.areaSeries) this.areaSeries.applyOptions({ visible: false });
            if (!this.lineSeries) {
                this.lineSeries = this.chart.addLineSeries({ color: '#2563eb', lineWidth: 2 });
            }
            this.lineSeries.applyOptions({ visible: true });
            this.lineSeries.setData(lineData);
        }
    }

    handleCrosshairMove(param) {
        if (!param || !param.time || !param.seriesData) {
            if (this.rawCandles && this.rawCandles.length > 0) {
                this.updateLegend(this.rawCandles[this.rawCandles.length - 1]);
            }
            return;
        }

        const dateStr = normalizeChartDate(param.time);

        const data = param.seriesData.get(this.candlestickSeries)
            || param.seriesData.get(this.areaSeries)
            || param.seriesData.get(this.lineSeries);

        if (data) {
            const raw = this.rawCandles ? this.rawCandles.find(c => normalizeChartDate(c.time) === dateStr) : null;
            if (raw) {
                this.updateLegend(raw);
            } else if (data.open !== undefined) {
                const volData = this.volumeSeries ? param.seriesData.get(this.volumeSeries) : null;
                const volVal = volData ? (volData.value || 0) : 0;
                this.updateLegend({
                    time: dateStr,
                    open: data.open,
                    high: data.high,
                    low: data.low,
                    close: data.close,
                    volume: volVal,
                });
            }
        }
    }

    updateLegend(candle) {
        if (!candle) return;

        const dateEl = document.getElementById('legend-date');
        const openEl = document.getElementById('legend-open');
        const highEl = document.getElementById('legend-high');
        const lowEl = document.getElementById('legend-low');
        const closeEl = document.getElementById('legend-close');
        const volEl = document.getElementById('legend-volume');

        const dateStr = normalizeChartDate(candle.time);
        const isUp = candle.close >= candle.open;
        const colorClass = isUp ? 'text-success' : 'text-danger';

        if (dateEl) dateEl.textContent = dateStr;
        if (openEl) openEl.textContent = Number(candle.open).toFixed(2);
        if (highEl) highEl.textContent = Number(candle.high).toFixed(2);
        if (lowEl) lowEl.textContent = Number(candle.low).toFixed(2);
        if (closeEl) {
            closeEl.textContent = Number(candle.close).toFixed(2);
            closeEl.className = `${colorClass} fw-bold`;
        }
        if (volEl) {
            let v = Number(candle.volume);
            if (isNaN(v) || v <= 0) {
                if (this.rawCandles && this.rawCandles.length > 0) {
                    const match = this.rawCandles.find(c => normalizeChartDate(c.time) === dateStr);
                    if (match && match.volume > 0) v = Number(match.volume);
                }
            }
            if (v >= 10000000) volEl.textContent = `${(v / 10000000).toFixed(2)}Cr`;
            else if (v >= 100000) volEl.textContent = `${(v / 100000).toFixed(2)}L`;
            else if (v >= 1000) volEl.textContent = `${(v / 1000).toFixed(1)}k`;
            else volEl.textContent = (v && v > 0) ? v.toLocaleString('en-IN') : '-';
        }

        const updateTag = (wrapId, valId, val, show) => {
            const wrap = document.getElementById(wrapId);
            const el = document.getElementById(valId);
            if (wrap && el) {
                if (val && show) {
                    wrap.classList.remove('d-none');
                    el.textContent = Number(val).toFixed(2);
                } else {
                    wrap.classList.add('d-none');
                }
            }
        };

        updateTag('legend-sma20-wrap', 'legend-sma20', candle.sma20, this.indicatorState.sma20);
        updateTag('legend-sma50-wrap', 'legend-sma50', candle.sma50, this.indicatorState.sma50);
        updateTag('legend-sma200-wrap', 'legend-sma200', candle.sma200, this.indicatorState.sma200);
        updateTag('legend-ema9-wrap', 'legend-ema9', candle.ema9, this.indicatorState.ema9);
        updateTag('legend-ema20-wrap', 'legend-ema20', candle.ema20, this.indicatorState.ema20);
        updateTag('legend-vwap-wrap', 'legend-vwap', candle.vwap, this.indicatorState.vwap);
        updateTag('legend-supertrend-wrap', 'legend-supertrend', candle.supertrend, this.indicatorState.supertrend);
        const stEl = document.getElementById('legend-supertrend');
        if (stEl && candle.supertrend_dir) {
            stEl.style.color = candle.supertrend_dir === 1 ? '#089981' : '#f23645';
        }
        updateTag('legend-sar-wrap', 'legend-sar', candle.sar, this.indicatorState.sar);
    }

    bindToolbarEvents() {
        // 1. Timeframe Range Selector (TradingView Bottom Bar: 1D 5D 1M 3M 6M YTD 1Y 5Y All)
        const tfGroup = document.getElementById('chart-timeframe-group');
        if (tfGroup) {
            tfGroup.querySelectorAll('.timeframe-btn').forEach(btn => {
                btn.onclick = () => {
                    tfGroup.querySelectorAll('.timeframe-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    const rawVal = btn.getAttribute('data-days');
                    let days = 180;
                    if (rawVal === 'ytd') {
                        const now = new Date();
                        const startOfYear = new Date(now.getFullYear(), 0, 1);
                        days = Math.max(1, Math.ceil((now - startOfYear) / (1000 * 60 * 60 * 24)));
                    } else {
                        days = parseInt(rawVal, 10);
                    }
                    this.loadData(days);
                };
            });
        }

        // 2. Chart Type Dropdown
        document.querySelectorAll('[data-chart-type]').forEach(item => {
            item.onclick = (e) => {
                e.preventDefault();
                const type = item.getAttribute('data-chart-type');
                document.querySelectorAll('[data-chart-type]').forEach(i => i.classList.remove('active'));
                item.classList.add('active');

                const labelEl = document.getElementById('chart-type-label');
                if (labelEl) labelEl.textContent = type.charAt(0).toUpperCase() + type.slice(1);
                this.setChartType(type);
            };
        });

        // 3. Indicator Toggles
        document.querySelectorAll('.indicator-toggle').forEach(input => {
            input.onchange = (e) => {
                const ind = e.target.getAttribute('data-indicator');
                const checked = e.target.checked;
                this.indicatorState[ind] = checked;

                if (ind === 'sma20' && this.sma20Series) this.sma20Series.applyOptions({ visible: checked });
                if (ind === 'sma50' && this.sma50Series) this.sma50Series.applyOptions({ visible: checked });
                if (ind === 'sma200' && this.sma200Series) this.sma200Series.applyOptions({ visible: checked });
                if (ind === 'ema9' && this.ema9Series) this.ema9Series.applyOptions({ visible: checked });
                if (ind === 'ema20' && this.ema20Series) this.ema20Series.applyOptions({ visible: checked });
                if (ind === 'ema50' && this.ema50Series) this.ema50Series.applyOptions({ visible: checked });
                if (ind === 'vwap' && this.vwapSeries) this.vwapSeries.applyOptions({ visible: checked });

                if (ind === 'supertrend') {
                    if (this.supertrendBullSeries) this.supertrendBullSeries.applyOptions({ visible: checked });
                    if (this.supertrendBearSeries) this.supertrendBearSeries.applyOptions({ visible: checked });
                }
                if (ind === 'sar' && this.sarSeries) {
                    this.sarSeries.applyOptions({ visible: checked });
                }
                if (ind === 'fibonacci') {
                    this.renderFibonacciLevels();
                }

                if (ind === 'bb') {
                    if (this.bbUpperSeries) this.bbUpperSeries.applyOptions({ visible: checked });
                    if (this.bbLowerSeries) this.bbLowerSeries.applyOptions({ visible: checked });
                }
                if (ind === 'donchian') {
                    if (this.donchianUpperSeries) this.donchianUpperSeries.applyOptions({ visible: checked });
                    if (this.donchianLowerSeries) this.donchianLowerSeries.applyOptions({ visible: checked });
                }

                if (ind === 'rsi') {
                    const c = document.getElementById('tradingview-rsi-container');
                    if (checked) this.renderRsiPane(this.cachedSubPaneData ? this.cachedSubPaneData.rsi : []);
                    else if (c) c.classList.add('d-none');
                }
                if (ind === 'macd') {
                    const c = document.getElementById('tradingview-macd-container');
                    if (checked) {
                        const d = this.cachedSubPaneData;
                        this.renderMacdPane(d ? d.macdLine : [], d ? d.macdSignal : [], d ? d.macdHist : []);
                    } else if (c) c.classList.add('d-none');
                }
                if (ind === 'stoch') {
                    const c = document.getElementById('tradingview-stoch-container');
                    if (checked) {
                        const d = this.cachedSubPaneData;
                        this.renderStochPane(d ? d.stochK : [], d ? d.stochD : []);
                    } else if (c) c.classList.add('d-none');
                }
                if (ind === 'atr') {
                    const c = document.getElementById('tradingview-atr-container');
                    if (checked) this.renderAtrPane(this.cachedSubPaneData ? this.cachedSubPaneData.atr : []);
                    else if (c) c.classList.add('d-none');
                }

                if (this.rawCandles.length > 0) this.updateLegend(this.rawCandles[this.rawCandles.length - 1]);
            };
        });

        // 4. Trade Levels Toggle
        const levelsBtn = document.getElementById('btn-toggle-levels');
        if (levelsBtn) {
            levelsBtn.onclick = () => {
                this.indicatorState.levels = !this.indicatorState.levels;
                levelsBtn.classList.toggle('active', this.indicatorState.levels);
                levelsBtn.classList.toggle('btn-primary', this.indicatorState.levels);
                levelsBtn.classList.toggle('text-white', this.indicatorState.levels);
                this.renderTradeLevels();
            };
        }

        // 5. Fit Content (Reset Zoom) & Refresh Data
        const fitBtn = document.getElementById('btn-reset-zoom');
        if (fitBtn) {
            fitBtn.onclick = () => { if (this.chart) this.chart.timeScale().fitContent(); };
        }
        const refreshBtn = document.getElementById('btn-chart-refresh');
        if (refreshBtn) {
            refreshBtn.onclick = () => {
                const icon = refreshBtn.querySelector('i');
                if (icon) icon.classList.add('spin-animation');
                refreshBtn.classList.add('disabled');
                this.refreshData(false);
                setTimeout(() => {
                    refreshBtn.classList.remove('disabled');
                    if (icon) icon.classList.remove('spin-animation');
                }, 800);
            };
        }

        // 6. Fullscreen Toggle
        const fsBtn = document.getElementById('btn-chart-fullscreen');
        const card = document.getElementById('stock-chart-card');
        if (fsBtn && card) {
            fsBtn.onclick = () => {
                if (!document.fullscreenElement) {
                    card.requestFullscreen().catch(err => console.error(err));
                    fsBtn.innerHTML = '<i class="bi bi-fullscreen-exit"></i>';
                } else {
                    document.exitFullscreen().catch(err => console.error(err));
                    fsBtn.innerHTML = '<i class="bi bi-fullscreen"></i>';
                }
            };
        }
    }

    observeThemeChanges() {
        const observer = new MutationObserver(() => {
            const colors = this.getThemeColors();
            const applyOpts = (c) => {
                if (c) {
                    c.applyOptions({
                        layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text },
                        grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
                        rightPriceScale: { borderColor: colors.border },
                        timeScale: { borderColor: colors.border },
                    });
                }
            };
            applyOpts(this.chart);
            applyOpts(this.rsiChart);
            applyOpts(this.macdChart);
            applyOpts(this.stochChart);
            applyOpts(this.atrChart);
        });

        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-bs-theme'] });
    }

    destroy() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        for (const pl of this.fibPriceLines) {
            try { this.candlestickSeries.removePriceLine(pl); } catch (e) {}
        }
        this.fibPriceLines = [];
        if (this.chart) { this.chart.remove(); this.chart = null; }
        if (this.rsiChart) { this.rsiChart.remove(); this.rsiChart = null; }
        if (this.macdChart) { this.macdChart.remove(); this.macdChart = null; }
        if (this.stochChart) { this.stochChart.remove(); this.stochChart = null; }
        if (this.atrChart) { this.atrChart.remove(); this.atrChart = null; }
    }
}


// ============================================================================
// 2. APACHE ECHARTS DASHBOARD ANALYTICS ENGINE
// ============================================================================

window.EChartsAnalytics = {
    isDark() {
        const docTheme = document.documentElement.getAttribute('data-bs-theme');
        return docTheme === 'dark';
    },

    getCommonTheme() {
        const dark = this.isDark();
        return {
            backgroundColor: 'transparent',
            textStyle: {
                color: dark ? '#94a3b8' : '#64748b',
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            },
            tooltip: {
                backgroundColor: dark ? 'rgba(15, 23, 42, 0.92)' : 'rgba(255, 255, 255, 0.95)',
                borderColor: dark ? '#334155' : '#e2e8f0',
                textStyle: { color: dark ? '#f8fafc' : '#0f172a' },
                padding: [8, 12],
            },
        };
    },

    initDonut(domId, data, title = '') {
        const dom = document.getElementById(domId);
        if (!dom || typeof echarts === 'undefined') return null;

        const chart = echarts.init(dom, this.isDark() ? 'dark' : null);
        const common = this.getCommonTheme();

        const option = {
            backgroundColor: common.backgroundColor,
            title: title ? { text: title, left: 'center', textStyle: common.textStyle } : undefined,
            tooltip: { ...common.tooltip, trigger: 'item', formatter: '{b}: ₹{c} ({d}%)' },
            legend: { orient: 'horizontal', bottom: '0', textStyle: common.textStyle },
            series: [{
                type: 'pie',
                radius: ['45%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: { borderRadius: 6, borderColor: this.isDark() ? '#0f172a' : '#ffffff', borderWidth: 2 },
                label: { show: false },
                emphasis: { label: { show: true, fontSize: 13, fontWeight: 'bold' } },
                data: data,
            }],
        };

        chart.setOption(option);
        window.addEventListener('resize', () => chart.resize());
        return chart;
    },

    initLine(domId, xData, seriesList) {
        const dom = document.getElementById(domId);
        if (!dom || typeof echarts === 'undefined') return null;

        const chart = echarts.init(dom, this.isDark() ? 'dark' : null);
        const common = this.getCommonTheme();
        const dark = this.isDark();

        const option = {
            backgroundColor: common.backgroundColor,
            tooltip: { ...common.tooltip, trigger: 'axis' },
            grid: { top: 30, right: 20, bottom: 30, left: 50 },
            xAxis: {
                type: 'category',
                data: xData,
                axisLine: { lineStyle: { color: dark ? '#334155' : '#cbd5e1' } },
                axisLabel: common.textStyle,
            },
            yAxis: {
                type: 'value',
                splitLine: { lineStyle: { color: dark ? 'rgba(51, 65, 85, 0.3)' : 'rgba(226, 232, 240, 0.8)' } },
                axisLabel: common.textStyle,
            },
            series: seriesList.map(s => ({
                name: s.name,
                type: 'line',
                smooth: true,
                data: s.data,
                itemStyle: { color: s.color || '#2563eb' },
                areaStyle: s.area ? { opacity: 0.15 } : undefined,
            })),
        };

        chart.setOption(option);
        window.addEventListener('resize', () => chart.resize());
        return chart;
    },
};


// ============================================================================
// 3. GLOBAL HTMX-READY INITIALIZATION HELPER
// ============================================================================

window.initStockChart = function(containerId, dataUrl) {
    const container = document.getElementById(containerId);
    if (!container) {
        setTimeout(() => window.initStockChart(containerId, dataUrl), 50);
        return;
    }

    if (container._stockChartInstance && typeof container._stockChartInstance.destroy === 'function') {
        container._stockChartInstance.destroy();
    }

    const chart = new TradingViewStockChart(containerId, dataUrl);
    container._stockChartInstance = chart;
    return chart;
};

document.addEventListener('htmx:beforeSwap', function(evt) {
    const target = evt.detail.target;
    if (target) {
        const chartContainers = target.querySelectorAll('[id^="tradingview-chart-container"], [id^="stock-chart-canvas"]');
        chartContainers.forEach(c => {
            if (c._stockChartInstance && typeof c._stockChartInstance.destroy === 'function') {
                c._stockChartInstance.destroy();
                c._stockChartInstance = null;
            }
        });
    }
});

// Sync live price updates directly into TradingView Lightweight Chart & Chart Toolbar Header
document.addEventListener('htmx:afterSwap', function(evt) {
    const quoteEl = document.getElementById('stock-quote-container');
    if (quoteEl && quoteEl.dataset.price) {
        const symbol = quoteEl.dataset.symbol || '';
        const price = quoteEl.dataset.price;
        const change = quoteEl.dataset.change;
        const changePct = quoteEl.dataset.changePercent;

        // 1. Update Chart Toolbar Header Live Price
        const headingPriceEl = document.getElementById('chart-heading-price');
        if (headingPriceEl) {
            const counterEl = headingPriceEl.querySelector('[data-kpi-counter]') || headingPriceEl;
            counterEl.setAttribute('data-target', price);
            if (typeof window.animateOdometerCounter === 'function') {
                window.animateOdometerCounter(counterEl, 'chart_price_' + symbol);
            } else {
                counterEl.textContent = '₹' + Number(price).toFixed(2);
            }
        }

        // 2. Update Chart Toolbar Header Change Badge
        const headingChangeEl = document.getElementById('chart-heading-change');
        if (headingChangeEl && change !== undefined && change !== '') {
            const chgNum = parseFloat(change);
            const chgPctNum = parseFloat(changePct);
            if (!isNaN(chgNum) && !isNaN(chgPctNum)) {
                const isUp = chgNum >= 0;
                const sign = isUp ? '+' : '';
                headingChangeEl.className = `badge ${isUp ? 'bg-success-subtle text-success' : 'bg-danger-subtle text-danger'} fw-semibold`;
                headingChangeEl.textContent = `${sign}${chgNum.toFixed(2)} (${chgPctNum.toFixed(2)}%)`;
            }
        }

        // 3. Update Chart Intraday Candle & Price Scale Line
        const chartContainer = document.getElementById('tradingview-chart-container');
        if (chartContainer && chartContainer._stockChartInstance && typeof chartContainer._stockChartInstance.updateLiveBar === 'function') {
            chartContainer._stockChartInstance.updateLiveBar({
                price: price,
                open: quoteEl.dataset.open,
                high: quoteEl.dataset.high,
                low: quoteEl.dataset.low,
                volume: quoteEl.dataset.volume,
                time: quoteEl.dataset.time
            });
        }
    }
});
