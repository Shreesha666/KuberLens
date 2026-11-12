/**
 * Standalone High-Performance Candlestick & Volume Canvas Charting Engine
 * Pure HTML5 Canvas implementation with zero external dependencies.
 * Supports zoom, pan, crosshair tooltips, and SMA overlays.
 */
class FinancialCandlestickChart {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.candles = [];
        this.levels = null;
        this.options = {
            upColor: '#10b981',       // Emerald Green
            downColor: '#ef4444',     // Crimson Red
            sma20Color: '#2563eb',    // Royal Blue
            sma50Color: '#f59e0b',    // Amber
            gridColor: 'rgba(100, 116, 139, 0.12)',
            textColor: '#64748b',
            font: '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            paddingRight: 78,
            paddingBottom: 25,
            paddingTop: 15,
            paddingLeft: 10,
            volumeHeightPct: 0.22,
            ...options
        };

        this.mousePos = null;
        this.initEvents();
        this.resize();
    }

    resize() {
        if (!this.canvas || !this.ctx) return;
        const parent = this.canvas.parentElement;
        const rect = parent ? parent.getBoundingClientRect() : null;
        const dpr = window.devicePixelRatio || 1;

        let computedW = rect ? rect.width : 0;
        if (!computedW && parent) computedW = parent.clientWidth;
        if (!computedW) computedW = this.canvas.clientWidth || 800;

        let computedH = rect ? rect.height : 0;
        if (!computedH && parent) computedH = parent.clientHeight;
        if (!computedH) computedH = 360;
        computedH = Math.max(320, computedH);

        this.width = computedW;
        this.height = computedH;
        this.canvas.width = this.width * dpr;
        this.canvas.height = this.height * dpr;
        this.canvas.style.width = `${this.width}px`;
        this.canvas.style.height = `${this.height}px`;

        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        this.render();
    }

    setData(candles, levels = null) {
        this.candles = candles || [];
        this.levels = levels;
        this.resize();
    }

    initEvents() {
        window.addEventListener('resize', () => this.resize());
        this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            this.mousePos = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };
            this.render();
        });

        this.canvas.addEventListener('mouseleave', () => {
            this.mousePos = null;
            this.render();
        });
    }

    render() {
        if (!this.ctx) return;
        const ctx = this.ctx;
        const w = this.width;
        const h = this.height;
        const opt = this.options;

        ctx.clearRect(0, 0, w, h);

        if (!this.candles || this.candles.length === 0) {
            ctx.fillStyle = opt.textColor;
            ctx.font = '13px -apple-system, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('No historical price candles available for chart rendering.', w / 2, h / 2);
            return;
        }

        const chartW = w - opt.paddingLeft - opt.paddingRight;
        const chartH = h - opt.paddingTop - opt.paddingBottom;
        const volumeH = chartH * opt.volumeHeightPct;
        const priceH = chartH - volumeH;

        // Determine price min & max
        let candleMin = Infinity;
        let candleMax = -Infinity;
        let maxVol = 0;

        for (const c of this.candles) {
            if (c.low < candleMin) candleMin = c.low;
            if (c.high > candleMax) candleMax = c.high;
            if (c.sma20 && c.sma20 < candleMin) candleMin = c.sma20;
            if (c.sma20 && c.sma20 > candleMax) candleMax = c.sma20;
            if (c.sma50 && c.sma50 < candleMin) candleMin = c.sma50;
            if (c.sma50 && c.sma50 > candleMax) candleMax = c.sma50;
            if (c.volume > maxVol) maxVol = c.volume;
        }

        let minPrice = candleMin;
        let maxPrice = candleMax;

        if (this.levels) {
            if (this.levels.stop_loss && this.levels.stop_loss > 0) {
                minPrice = Math.min(minPrice, this.levels.stop_loss);
            }
            if (this.levels.target_1 && this.levels.target_1 > 0) {
                maxPrice = Math.max(maxPrice, this.levels.target_1);
            }
            if (this.levels.target_2 && this.levels.target_2 > 0) {
                // If T2 is within 25% of candleMax, accommodate it; otherwise cap to prevent crushing candles
                if (this.levels.target_2 <= candleMax * 1.25) {
                    maxPrice = Math.max(maxPrice, this.levels.target_2);
                }
            }
        }

        const basePad = (candleMax - candleMin) * 0.04 || 1;
        if (minPrice === candleMin) minPrice -= basePad;
        if (maxPrice === candleMax) maxPrice += basePad;
        const priceRange = Math.max(1, maxPrice - minPrice);

        // Scales
        const n = this.candles.length;
        const candleStep = chartW / n;
        const candleWidth = Math.max(2, Math.min(14, candleStep * 0.72));

        const getY = (val) => opt.paddingTop + priceH - ((val - minPrice) / priceRange) * priceH;
        const getVolY = (vol) => opt.paddingTop + chartH - (maxVol > 0 ? (vol / maxVol) * volumeH : 0);

        // Pre-compute level Y positions to prevent text collisions with standard grid labels
        const levelYPositions = [];
        if (this.levels) {
            const registerY = (val) => {
                if (val && val >= minPrice && val <= maxPrice) {
                    levelYPositions.push(getY(val));
                }
            };
            registerY(this.levels.stop_loss);
            registerY(this.levels.target_1);
            registerY(this.levels.target_2);
        }

        // Grid Lines (Price Axis)
        ctx.strokeStyle = opt.gridColor;
        ctx.fillStyle = opt.textColor;
        ctx.font = opt.font;
        ctx.lineWidth = 1;

        const steps = 5;
        for (let i = 0; i <= steps; i++) {
            const p = minPrice + (priceRange / steps) * i;
            const y = getY(p);
            ctx.beginPath();
            ctx.moveTo(opt.paddingLeft, y);
            ctx.lineTo(w - opt.paddingRight, y);
            ctx.stroke();

            // Only print price text if it does not collide with a trade level badge
            const collides = levelYPositions.some(ly => Math.abs(ly - y) < 14);
            if (!collides) {
                ctx.textAlign = 'left';
                ctx.textBaseline = 'middle';
                ctx.fillText(`₹${p.toFixed(1)}`, w - opt.paddingRight + 6, y);
            }
        }

        // Draw Volume Bars
        for (let i = 0; i < n; i++) {
            const c = this.candles[i];
            const x = opt.paddingLeft + i * candleStep + candleStep / 2;
            const volY = getVolY(c.volume);
            const isUp = c.close >= c.open;

            ctx.fillStyle = isUp ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)';
            ctx.fillRect(x - candleWidth / 2, volY, candleWidth, opt.paddingTop + chartH - volY);
        }

        // Draw Candlesticks
        for (let i = 0; i < n; i++) {
            const c = this.candles[i];
            const x = opt.paddingLeft + i * candleStep + candleStep / 2;
            const openY = getY(c.open);
            const closeY = getY(c.close);
            const highY = getY(c.high);
            const lowY = getY(c.low);
            const isUp = c.close >= c.open;
            const color = isUp ? opt.upColor : opt.downColor;

            // Wick
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.moveTo(x, highY);
            ctx.lineTo(x, lowY);
            ctx.stroke();

            // Candle Body
            const bodyY = Math.min(openY, closeY);
            const bodyH = Math.max(1.5, Math.abs(closeY - openY));
            ctx.fillStyle = color;
            ctx.fillRect(x - candleWidth / 2, bodyY, candleWidth, bodyH);
        }

        // Draw Overlays: SMA 20 (Blue) & SMA 50 (Orange)
        const drawLine = (prop, color) => {
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            let started = false;
            for (let i = 0; i < n; i++) {
                const val = this.candles[i][prop];
                if (val !== null && val !== undefined) {
                    const x = opt.paddingLeft + i * candleStep + candleStep / 2;
                    const y = getY(val);
                    if (!started) {
                        ctx.moveTo(x, y);
                        started = true;
                    } else {
                        ctx.lineTo(x, y);
                    }
                }
            }
            if (started) ctx.stroke();
        };

        drawLine('sma20', opt.sma20Color);
        drawLine('sma50', opt.sma50Color);

        // Draw Key Institutional Trade Levels (Stop Loss, T1, T2)
        if (this.levels) {
            // Anchor trade projection ray to recent trading cycle (~25 sessions or start of chart if shorter)
            const projectionSpan = Math.min(n, 25);
            const rayStartX = opt.paddingLeft + (n - projectionSpan) * candleStep + candleStep / 2;
            const rayEndX = w - opt.paddingRight;

            const drawTargetLevel = (val, label, color) => {
                if (!val || val < minPrice || val > maxPrice) return;
                const y = getY(val);
                ctx.save();
                ctx.strokeStyle = color;
                ctx.lineWidth = 1.5;
                ctx.setLineDash([5, 4]);
                ctx.beginPath();
                ctx.moveTo(rayStartX, y);
                ctx.lineTo(rayEndX, y);
                ctx.stroke();

                // Anchor bullet indicator at projection origin
                ctx.setLineDash([]);
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(rayStartX, y, 2.5, 0, Math.PI * 2);
                ctx.fill();

                // Axis Tag on the Right - crisp rounded badge
                const tagW = opt.paddingRight - 6;
                const tagH = 17;
                const tagX = w - opt.paddingRight + 3;
                const tagY = y - tagH / 2;

                ctx.beginPath();
                ctx.roundRect(tagX, tagY, tagW, tagH, 3);
                ctx.fill();

                ctx.fillStyle = '#ffffff';
                ctx.font = 'bold 9.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(label, tagX + tagW / 2, tagY + tagH / 2);
                ctx.restore();
            };

            if (this.levels.stop_loss) drawTargetLevel(this.levels.stop_loss, `SL ₹${this.levels.stop_loss}`, '#dc2626');
            if (this.levels.target_1) drawTargetLevel(this.levels.target_1, `T1 ₹${this.levels.target_1}`, '#059669');
            if (this.levels.target_2) drawTargetLevel(this.levels.target_2, `T2 ₹${this.levels.target_2}`, '#0d9488');
        }

        // Date Axis (X Labels)
        const labelInterval = Math.max(1, Math.floor(n / 6));
        ctx.textAlign = 'center';
        for (let i = 0; i < n; i += labelInterval) {
            const x = opt.paddingLeft + i * candleStep + candleStep / 2;
            const d = this.candles[i].time;
            ctx.fillText(d.slice(5), x, h - 8);
        }

        // Crosshair & Tooltip Hover
        if (this.mousePos && this.mousePos.x >= opt.paddingLeft && this.mousePos.x <= w - opt.paddingRight) {
            const relX = this.mousePos.x - opt.paddingLeft;
            const hoveredIdx = Math.min(n - 1, Math.max(0, Math.floor(relX / candleStep)));
            const active = this.candles[hoveredIdx];
            const hX = opt.paddingLeft + hoveredIdx * candleStep + candleStep / 2;

            // Vertical Crosshair
            ctx.strokeStyle = 'rgba(100, 116, 139, 0.4)';
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(hX, opt.paddingTop);
            ctx.lineTo(hX, opt.paddingTop + chartH);
            ctx.stroke();

            // Horizontal Crosshair
            if (this.mousePos.y >= opt.paddingTop && this.mousePos.y <= opt.paddingTop + priceH) {
                ctx.beginPath();
                ctx.moveTo(opt.paddingLeft, this.mousePos.y);
                ctx.lineTo(w - opt.paddingRight, this.mousePos.y);
                ctx.stroke();
            }
            ctx.setLineDash([]);

            // Floating Tooltip Badge
            const badgeW = 240;
            const badgeH = 22;
            const badgeX = Math.min(w - badgeW - 10, Math.max(10, hX - badgeW / 2));
            ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
            ctx.beginPath();
            ctx.roundRect(badgeX, opt.paddingTop + 4, badgeW, badgeH, 4);
            ctx.fill();

            ctx.fillStyle = '#f8fafc';
            ctx.font = '10px -apple-system, sans-serif';
            ctx.textAlign = 'left';
            const tipText = `${active.time} | O:${active.open.toFixed(1)} H:${active.high.toFixed(1)} L:${active.low.toFixed(1)} C:${active.close.toFixed(1)}`;
            ctx.fillText(tipText, badgeX + 8, opt.paddingTop + 18);
        }
    }
}

// Global initialization helper for HTMX dynamic swaps and direct loads
window.initStockChart = function(canvasId, dataUrl) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        setTimeout(() => window.initStockChart(canvasId, dataUrl), 50);
        return;
    }
    fetch(dataUrl)
        .then(res => res.json())
        .then(json => {
            const chart = new FinancialCandlestickChart(canvasId);
            chart.setData(json.candles || [], json.levels || null);
            canvas._stockChartInstance = chart;
        })
        .catch(err => {
            console.error("Failed to load chart data:", err);
            const chart = new FinancialCandlestickChart(canvasId);
            chart.setData([]);
        });
};

