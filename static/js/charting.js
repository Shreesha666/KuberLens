/**
 * Institutional Stock Market Analytics Charting Engine
 * Powered by:
 * 1. TradingView Lightweight Charts (v4.2.1) - Primary Candlestick, Volume & Indicator Engine
 * 2. Apache ECharts (v5.5.1) - Dashboard Analytics & Portfolio Visualizations
 *
 * Designed for Django + HTMX single-page dynamic applications with full dark/light theme support.
 */

// ============================================================================
// 1. TRADINGVIEW LIGHTWEIGHT CHARTS ENGINE
// ============================================================================

class TradingViewStockChart {
    constructor(containerId, dataUrl, options = {}) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.dataUrl = dataUrl;
        this.options = options;

        this.chart = null;
        this.rsiChart = null;
        this.macdChart = null;

        // Series references
        this.candlestickSeries = null;
        this.lineSeries = null;
        this.areaSeries = null;
        this.volumeSeries = null;
        this.sma20Series = null;
        this.sma50Series = null;
        this.ema20Series = null;
        this.bbUpperSeries = null;
        this.bbLowerSeries = null;

        // Price lines (Trade Levels)
        this.priceLines = [];

        // Cached Data
        this.rawCandles = [];
        this.levels = null;
        this.currentDays = 180;
        this.currentChartType = 'candlestick';

        // Indicator visibility state
        this.indicatorState = {
            sma20: true,
            sma50: true,
            ema20: false,
            bb: false,
            rsi: false,
            macd: false,
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
            bg: isDark ? '#0f172a' : '#ffffff',
            text: isDark ? '#94a3b8' : '#64748b',
            grid: isDark ? 'rgba(51, 65, 85, 0.25)' : 'rgba(226, 232, 240, 0.8)',
            border: isDark ? '#334155' : '#e2e8f0',
            crosshair: isDark ? 'rgba(148, 163, 184, 0.4)' : 'rgba(100, 116, 139, 0.4)',
            upColor: '#10b981',       // Emerald
            downColor: '#ef4444',     // Crimson
            sma20Color: '#2563eb',    // Royal Blue
            sma50Color: '#f59e0b',    // Amber
            ema20Color: '#8b5cf6',    // Purple
            bbColor: 'rgba(139, 92, 246, 0.6)',
        };
    }

    init() {
        if (typeof LightweightCharts === 'undefined') {
            console.error('TradingView Lightweight Charts library is not loaded.');
            return;
        }

        // Clean up any existing instances in this container
        this.destroy();

        const colors = this.getThemeColors();
        const width = this.container.clientWidth || 800;
        const height = this.options.height || 420;

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
                    top: 0.08,
                    bottom: 0.24, // Leaves space for volume histogram
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
            handleScroll: {
                mouseWheel: true,
                pressedMouseMove: true,
            },
            handleScale: {
                axisPressedMouseMove: true,
                mouseWheel: true,
                pinch: true,
            },
        });

        // Initialize Series
        this.candlestickSeries = this.chart.addCandlestickSeries({
            upColor: colors.upColor,
            downColor: colors.downColor,
            borderVisible: false,
            wickUpColor: colors.upColor,
            wickDownColor: colors.downColor,
        });

        this.volumeSeries = this.chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: '', // Overlay series inside main pane
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });

        this.sma20Series = this.chart.addLineSeries({
            color: colors.sma20Color,
            lineWidth: 1.5,
            title: 'SMA 20',
            crosshairMarkerVisible: true,
        });

        this.sma50Series = this.chart.addLineSeries({
            color: colors.sma50Color,
            lineWidth: 1.5,
            title: 'SMA 50',
            crosshairMarkerVisible: true,
        });

        this.ema20Series = this.chart.addLineSeries({
            color: colors.ema20Color,
            lineWidth: 1.5,
            title: 'EMA 20',
            crosshairMarkerVisible: true,
            visible: false,
        });

        this.bbUpperSeries = this.chart.addLineSeries({
            color: colors.bbColor,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            title: 'BB Upper',
            crosshairMarkerVisible: false,
            visible: false,
        });

        this.bbLowerSeries = this.chart.addLineSeries({
            color: colors.bbColor,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            title: 'BB Lower',
            crosshairMarkerVisible: false,
            visible: false,
        });

        // Crosshair legend inspection
        this.chart.subscribeCrosshairMove((param) => this.handleCrosshairMove(param));

        // Auto-Resize Observer
        this.resizeObserver = new ResizeObserver((entries) => {
            if (!entries || entries.length === 0 || !this.chart) return;
            const newRect = entries[0].contentRect;
            if (newRect.width > 0) {
                this.chart.applyOptions({ width: newRect.width });
                if (this.rsiChart) this.rsiChart.applyOptions({ width: newRect.width });
                if (this.macdChart) this.macdChart.applyOptions({ width: newRect.width });
            }
        });
        this.resizeObserver.observe(this.container);

        // Fetch Data
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
                this.populateSeries();
            })
            .catch(err => {
                console.error("Failed to load TradingView chart data:", err);
            });
    }

    populateSeries() {
        if (!this.chart || !this.rawCandles || this.rawCandles.length === 0) return;

        const candleData = [];
        const volumeData = [];
        const sma20Data = [];
        const sma50Data = [];
        const ema20Data = [];
        const bbUpperData = [];
        const bbLowerData = [];
        const rsiData = [];
        const macdLineData = [];
        const macdSignalData = [];
        const macdHistData = [];

        for (const c of this.rawCandles) {
            const time = c.time; // YYYY-MM-DD
            candleData.push({
                time: time,
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close,
            });

            const isUp = c.close >= c.open;
            volumeData.push({
                time: time,
                value: c.volume,
                color: isUp ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
            });

            if (c.sma20 !== null && c.sma20 !== undefined) {
                sma20Data.push({ time: time, value: c.sma20 });
            }
            if (c.sma50 !== null && c.sma50 !== undefined) {
                sma50Data.push({ time: time, value: c.sma50 });
            }
            if (c.ema20 !== null && c.ema20 !== undefined) {
                ema20Data.push({ time: time, value: c.ema20 });
            }
            if (c.bb_upper !== null && c.bb_upper !== undefined) {
                bbUpperData.push({ time: time, value: c.bb_upper });
            }
            if (c.bb_lower !== null && c.bb_lower !== undefined) {
                bbLowerData.push({ time: time, value: c.bb_lower });
            }
            if (c.rsi14 !== null && c.rsi14 !== undefined) {
                rsiData.push({ time: time, value: c.rsi14 });
            }
            if (c.macd_line !== null && c.macd_line !== undefined) {
                macdLineData.push({ time: time, value: c.macd_line });
            }
            if (c.macd_signal !== null && c.macd_signal !== undefined) {
                macdSignalData.push({ time: time, value: c.macd_signal });
            }
            if (c.macd_hist !== null && c.macd_hist !== undefined) {
                macdHistData.push({
                    time: time,
                    value: c.macd_hist,
                    color: c.macd_hist >= 0 ? '#10b981' : '#ef4444',
                });
            }
        }

        // Set series data
        if (this.currentChartType === 'candlestick') {
            this.candlestickSeries.setData(candleData);
        } else if (this.currentChartType === 'area') {
            const areaData = candleData.map(c => ({ time: c.time, value: c.close }));
            if (this.areaSeries) this.areaSeries.setData(areaData);
        } else if (this.currentChartType === 'line') {
            const lineData = candleData.map(c => ({ time: c.time, value: c.close }));
            if (this.lineSeries) this.lineSeries.setData(lineData);
        }

        this.volumeSeries.setData(volumeData);
        this.sma20Series.setData(sma20Data);
        this.sma50Series.setData(sma50Data);
        this.ema20Series.setData(ema20Data);
        this.bbUpperSeries.setData(bbUpperData);
        this.bbLowerSeries.setData(bbLowerData);

        // Apply visibility according to state
        this.sma20Series.applyOptions({ visible: this.indicatorState.sma20 });
        this.sma50Series.applyOptions({ visible: this.indicatorState.sma50 });
        this.ema20Series.applyOptions({ visible: this.indicatorState.ema20 });
        this.bbUpperSeries.applyOptions({ visible: this.indicatorState.bb });
        this.bbLowerSeries.applyOptions({ visible: this.indicatorState.bb });

        // Institutional Trade Level Price Lines
        this.renderTradeLevels();

        // Sub-Panes: RSI & MACD
        this.cachedSubPaneData = {
            rsi: rsiData,
            macdLine: macdLineData,
            macdSignal: macdSignalData,
            macdHist: macdHistData,
        };

        if (this.indicatorState.rsi) this.renderRsiPane(rsiData);
        if (this.indicatorState.macd) this.renderMacdPane(macdLineData, macdSignalData, macdHistData);

        // Fit content into visible container
        this.chart.timeScale().fitContent();

        // Update initial crosshair legend with latest candle
        if (this.rawCandles.length > 0) {
            const latest = this.rawCandles[this.rawCandles.length - 1];
            this.updateLegend(latest);
        }
    }

    renderTradeLevels() {
        // Clear existing price lines
        for (const pl of this.priceLines) {
            try {
                this.candlestickSeries.removePriceLine(pl);
            } catch (e) {
                // Ignore removal errors if series was recreated
            }
        }
        this.priceLines = [];

        if (!this.indicatorState.levels || !this.levels) return;

        // 1. Stop Loss (Red Dashed)
        if (this.levels.stop_loss && this.levels.stop_loss > 0) {
            const slLine = this.candlestickSeries.createPriceLine({
                price: parseFloat(this.levels.stop_loss),
                color: '#dc2626',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `SL ₹${this.levels.stop_loss}`,
            });
            this.priceLines.push(slLine);
        }

        // 2. Target 1 (Green Dashed)
        if (this.levels.target_1 && this.levels.target_1 > 0) {
            const t1Line = this.candlestickSeries.createPriceLine({
                price: parseFloat(this.levels.target_1),
                color: '#059669',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `T1 ₹${this.levels.target_1}`,
            });
            this.priceLines.push(t1Line);
        }

        // 3. Target 2 (Teal Dashed)
        if (this.levels.target_2 && this.levels.target_2 > 0) {
            const t2Line = this.candlestickSeries.createPriceLine({
                price: parseFloat(this.levels.target_2),
                color: '#0d9488',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `T2 ₹${this.levels.target_2}`,
            });
            this.priceLines.push(t2Line);
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
                height: 130,
                layout: {
                    background: { type: 'solid', color: colors.bg },
                    textColor: colors.text,
                    fontSize: 10,
                },
                grid: {
                    vertLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted },
                    horzLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted },
                },
                rightPriceScale: {
                    borderColor: colors.border,
                    scaleMargins: { top: 0.1, bottom: 0.1 },
                },
                timeScale: {
                    visible: false, // Hidden to share timescale with main chart
                },
            });

            this.rsiSeries = this.rsiChart.addLineSeries({
                color: '#8b5cf6',
                lineWidth: 1.5,
                title: 'RSI 14',
            });

            // Oversold 30 & Overbought 70 reference lines
            this.rsiSeries.createPriceLine({
                price: 70,
                color: '#ef4444',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: '70 OB',
            });
            this.rsiSeries.createPriceLine({
                price: 30,
                color: '#10b981',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: '30 OS',
            });

            // Synchronize visible time range
            this.chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
                if (this.rsiChart && range) {
                    this.rsiChart.timeScale().setVisibleLogicalRange(range);
                }
            });
        }

        if (this.rsiSeries && rsiData) {
            this.rsiSeries.setData(rsiData);
        }
    }

    renderMacdPane(lineData, signalData, histData) {
        const macdContainer = document.getElementById('tradingview-macd-container');
        if (!macdContainer) return;

        macdContainer.classList.remove('d-none');
        if (!this.macdChart) {
            const colors = this.getThemeColors();
            this.macdChart = LightweightCharts.createChart(macdContainer, {
                width: this.container.clientWidth,
                height: 130,
                layout: {
                    background: { type: 'solid', color: colors.bg },
                    textColor: colors.text,
                    fontSize: 10,
                },
                grid: {
                    vertLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted },
                    horzLines: { color: colors.grid, style: LightweightCharts.LineStyle.Dotted },
                },
                rightPriceScale: {
                    borderColor: colors.border,
                    scaleMargins: { top: 0.1, bottom: 0.1 },
                },
                timeScale: {
                    visible: false,
                },
            });

            this.macdHistSeries = this.macdChart.addHistogramSeries({
                lineWidth: 1,
                title: 'Histogram',
            });

            this.macdLineSeries = this.macdChart.addLineSeries({
                color: '#2563eb',
                lineWidth: 1.5,
                title: 'MACD',
            });

            this.macdSignalSeries = this.macdChart.addLineSeries({
                color: '#f59e0b',
                lineWidth: 1.5,
                title: 'Signal',
            });

            this.chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
                if (this.macdChart && range) {
                    this.macdChart.timeScale().setVisibleLogicalRange(range);
                }
            });
        }

        if (this.macdHistSeries && histData) this.macdHistSeries.setData(histData);
        if (this.macdLineSeries && lineData) this.macdLineSeries.setData(lineData);
        if (this.macdSignalSeries && signalData) this.macdSignalSeries.setData(signalData);
    }

    setChartType(type) {
        if (type === this.currentChartType) return;
        this.currentChartType = type;

        const colors = this.getThemeColors();
        const candleData = this.rawCandles.map(c => ({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        }));
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
                    topColor: 'rgba(37, 99, 235, 0.4)',
                    bottomColor: 'rgba(37, 99, 235, 0.02)',
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
                this.lineSeries = this.chart.addLineSeries({
                    color: '#2563eb',
                    lineWidth: 2,
                });
            }
            this.lineSeries.applyOptions({ visible: true });
            this.lineSeries.setData(lineData);
        }
    }

    handleCrosshairMove(param) {
        if (!param || !param.time || !param.seriesData) {
            // Restore latest candle when not hovering
            if (this.rawCandles.length > 0) {
                this.updateLegend(this.rawCandles[this.rawCandles.length - 1]);
            }
            return;
        }

        const data = param.seriesData.get(this.candlestickSeries)
            || param.seriesData.get(this.areaSeries)
            || param.seriesData.get(this.lineSeries);

        if (data) {
            const raw = this.rawCandles.find(c => c.time === param.time);
            if (raw) {
                this.updateLegend(raw);
            } else if (data.open !== undefined) {
                this.updateLegend({
                    time: param.time,
                    open: data.open,
                    high: data.high,
                    low: data.low,
                    close: data.close,
                    volume: 0,
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
        const sma20El = document.getElementById('legend-sma20');
        const sma50El = document.getElementById('legend-sma50');
        const sma20Wrap = document.getElementById('legend-sma20-wrap');
        const sma50Wrap = document.getElementById('legend-sma50-wrap');

        if (dateEl) dateEl.textContent = candle.time;
        if (openEl) openEl.textContent = `₹${Number(candle.open).toFixed(2)}`;
        if (highEl) highEl.textContent = `₹${Number(candle.high).toFixed(2)}`;
        if (lowEl) lowEl.textContent = `₹${Number(candle.low).toFixed(2)}`;
        if (closeEl) closeEl.textContent = `₹${Number(candle.close).toFixed(2)}`;
        if (volEl) volEl.textContent = candle.volume > 0 ? candle.volume.toLocaleString('en-IN') : '-';

        if (sma20El && sma20Wrap) {
            if (candle.sma20 && this.indicatorState.sma20) {
                sma20Wrap.classList.remove('d-none');
                sma20El.textContent = `₹${Number(candle.sma20).toFixed(2)}`;
            } else {
                sma20Wrap.classList.add('d-none');
            }
        }

        if (sma50El && sma50Wrap) {
            if (candle.sma50 && this.indicatorState.sma50) {
                sma50Wrap.classList.remove('d-none');
                sma50El.textContent = `₹${Number(candle.sma50).toFixed(2)}`;
            } else {
                sma50Wrap.classList.add('d-none');
            }
        }
    }

    bindToolbarEvents() {
        // 1. Timeframe Buttons
        const tfGroup = document.getElementById('chart-timeframe-group');
        if (tfGroup) {
            tfGroup.querySelectorAll('button[data-days]').forEach(btn => {
                btn.onclick = () => {
                    tfGroup.querySelectorAll('button').forEach(b => b.classList.remove('active', 'btn-primary'));
                    tfGroup.querySelectorAll('button').forEach(b => b.classList.add('btn-outline-secondary'));
                    btn.classList.add('active', 'btn-primary');
                    btn.classList.remove('btn-outline-secondary');
                    const days = parseInt(btn.getAttribute('data-days'), 10);
                    this.loadData(days);
                };
            });
        }

        // 2. Chart Type Buttons
        const typeGroup = document.getElementById('chart-type-group');
        if (typeGroup) {
            typeGroup.querySelectorAll('button[data-type]').forEach(btn => {
                btn.onclick = () => {
                    typeGroup.querySelectorAll('button').forEach(b => b.classList.remove('active', 'btn-secondary'));
                    btn.classList.add('active', 'btn-secondary');
                    const type = btn.getAttribute('data-type');
                    this.setChartType(type);
                };
            });
        }

        // 3. Indicator Toggles
        document.querySelectorAll('.indicator-toggle').forEach(input => {
            input.onchange = (e) => {
                const ind = e.target.getAttribute('data-indicator');
                const checked = e.target.checked;
                this.indicatorState[ind] = checked;

                if (ind === 'sma20' && this.sma20Series) this.sma20Series.applyOptions({ visible: checked });
                if (ind === 'sma50' && this.sma50Series) this.sma50Series.applyOptions({ visible: checked });
                if (ind === 'ema20' && this.ema20Series) this.ema20Series.applyOptions({ visible: checked });
                if (ind === 'bb') {
                    if (this.bbUpperSeries) this.bbUpperSeries.applyOptions({ visible: checked });
                    if (this.bbLowerSeries) this.bbLowerSeries.applyOptions({ visible: checked });
                }
                if (ind === 'rsi') {
                    const rsiContainer = document.getElementById('tradingview-rsi-container');
                    if (checked) {
                        this.renderRsiPane(this.cachedSubPaneData ? this.cachedSubPaneData.rsi : []);
                    } else if (rsiContainer) {
                        rsiContainer.classList.add('d-none');
                    }
                }
                if (ind === 'macd') {
                    const macdContainer = document.getElementById('tradingview-macd-container');
                    if (checked) {
                        const d = this.cachedSubPaneData;
                        this.renderMacdPane(d ? d.macdLine : [], d ? d.macdSignal : [], d ? d.macdHist : []);
                    } else if (macdContainer) {
                        macdContainer.classList.add('d-none');
                    }
                }

                // Update crosshair legend
                if (this.rawCandles.length > 0) {
                    this.updateLegend(this.rawCandles[this.rawCandles.length - 1]);
                }
            };
        });

        // 4. Trade Levels Toggle
        const levelsBtn = document.getElementById('btn-toggle-levels');
        if (levelsBtn) {
            levelsBtn.onclick = () => {
                this.indicatorState.levels = !this.indicatorState.levels;
                levelsBtn.classList.toggle('active', this.indicatorState.levels);
                levelsBtn.classList.toggle('btn-secondary', this.indicatorState.levels);
                this.renderTradeLevels();
            };
        }

        // 5. Fit Content (Reset Zoom)
        const fitBtn = document.getElementById('btn-reset-zoom');
        if (fitBtn) {
            fitBtn.onclick = () => {
                if (this.chart) this.chart.timeScale().fitContent();
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
            if (this.chart) {
                this.chart.applyOptions({
                    layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text },
                    grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
                    rightPriceScale: { borderColor: colors.border },
                    timeScale: { borderColor: colors.border },
                });
            }
            if (this.rsiChart) {
                this.rsiChart.applyOptions({
                    layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text },
                    grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
                });
            }
            if (this.macdChart) {
                this.macdChart.applyOptions({
                    layout: { background: { type: 'solid', color: colors.bg }, textColor: colors.text },
                    grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
                });
            }
        });

        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['data-bs-theme'],
        });
    }

    destroy() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
        }
        if (this.rsiChart) {
            this.rsiChart.remove();
            this.rsiChart = null;
        }
        if (this.macdChart) {
            this.macdChart.remove();
            this.macdChart = null;
        }
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

    /**
     * Initializes a Donut chart for Portfolio Allocation or Sector Exposure
     */
    initDonut(domId, data, title = '') {
        const dom = document.getElementById(domId);
        if (!dom || typeof echarts === 'undefined') return null;

        const chart = echarts.init(dom, this.isDark() ? 'dark' : null);
        const common = this.getCommonTheme();

        const option = {
            backgroundColor: common.backgroundColor,
            title: title ? { text: title, left: 'center', textStyle: common.textStyle } : undefined,
            tooltip: {
                ...common.tooltip,
                trigger: 'item',
                formatter: '{b}: ₹{c} ({d}%)',
            },
            legend: {
                orient: 'horizontal',
                bottom: '0',
                textStyle: common.textStyle,
            },
            series: [
                {
                    type: 'pie',
                    radius: ['45%', '70%'],
                    avoidLabelOverlap: false,
                    itemStyle: {
                        borderRadius: 6,
                        borderColor: this.isDark() ? '#0f172a' : '#ffffff',
                        borderWidth: 2,
                    },
                    label: { show: false },
                    emphasis: {
                        label: { show: true, fontSize: 13, fontWeight: 'bold' },
                    },
                    data: data, // [{ name: 'IT', value: 120000 }, ...]
                },
            ],
        };

        chart.setOption(option);
        window.addEventListener('resize', () => chart.resize());
        return chart;
    },

    /**
     * Initializes an Area/Line chart for Backtesting Equity Curves & Drawdown
     */
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

    // Clean up previous instance on this container if present
    if (container._stockChartInstance && typeof container._stockChartInstance.destroy === 'function') {
        container._stockChartInstance.destroy();
    }

    const chart = new TradingViewStockChart(containerId, dataUrl);
    container._stockChartInstance = chart;
    return chart;
};

// Cleanup charts before HTMX content swaps to prevent memory leaks
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
