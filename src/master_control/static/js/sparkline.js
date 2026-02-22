/* Master Control — Sparkline Utility */

class SparklineStore {
    constructor(maxPoints = 60) {
        this.maxPoints = maxPoints;
        this.data = {};
    }

    addDataPoint(clientName, metric, value) {
        if (!this.data[clientName]) {
            this.data[clientName] = {};
        }
        if (!this.data[clientName][metric]) {
            this.data[clientName][metric] = [];
        }
        this.data[clientName][metric].push({ ts: Date.now(), value });
        if (this.data[clientName][metric].length > this.maxPoints) {
            this.data[clientName][metric].shift();
        }
    }

    getDataPoints(clientName, metric) {
        return this.data[clientName]?.[metric] || [];
    }
}

class Sparkline {
    constructor(width = 100, height = 30) {
        this.width = width;
        this.height = height;
        this.pad = 2;
    }

    render(dataPoints, color = '#3b82f6') {
        if (!dataPoints || dataPoints.length < 2) {
            return `<svg width="${this.width}" height="${this.height}" class="sparkline">` +
                `<line x1="0" y1="${this.height / 2}" x2="${this.width}" y2="${this.height / 2}" ` +
                `stroke="var(--border)" stroke-width="1" stroke-dasharray="2,2"/>` +
                `</svg>`;
        }

        const values = dataPoints.map(d => d.value);
        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min || 1;
        const cw = this.width - 2 * this.pad;
        const ch = this.height - 2 * this.pad;
        const step = cw / (values.length - 1);

        const points = values.map((v, i) => {
            const x = this.pad + i * step;
            const y = this.pad + ch - ((v - min) / range) * ch;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(' ');

        return `<svg width="${this.width}" height="${this.height}" class="sparkline">` +
            `<polyline points="${points}" fill="none" stroke="${color}" ` +
            `stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>` +
            `</svg>`;
    }
}

window.sparklineStore = new SparklineStore(60);
