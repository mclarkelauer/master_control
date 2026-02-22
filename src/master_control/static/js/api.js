/* Master Control — API Client */

class APIClient {
    constructor(baseURL, token) {
        this.baseURL = baseURL;
        this.headers = { 'Content-Type': 'application/json' };
        if (token) this.headers['Authorization'] = `Bearer ${token}`;
    }

    async _fetch(endpoint, options = {}) {
        const resp = await fetch(`${this.baseURL}${endpoint}`, {
            ...options,
            headers: { ...this.headers, ...options.headers },
        });
        if (!resp.ok) {
            const body = await resp.text();
            throw new Error(body || resp.statusText);
        }
        return resp.json();
    }

    /* Fleet */
    listClients()              { return this._fetch('/fleet/clients'); }
    getClient(name)            { return this._fetch(`/fleet/clients/${name}`); }
    getClientWorkloads(name)   { return this._fetch(`/fleet/clients/${name}/workloads`); }
    startWorkload(client, wl)  { return this._fetch(`/fleet/clients/${client}/workloads/${wl}/start`, { method: 'POST' }); }
    stopWorkload(client, wl)   { return this._fetch(`/fleet/clients/${client}/workloads/${wl}/stop`, { method: 'POST' }); }
    restartWorkload(client, wl){ return this._fetch(`/fleet/clients/${client}/workloads/${wl}/restart`, { method: 'POST' }); }
    getWorkloadLogs(client, wl, lines = 100) { return this._fetch(`/fleet/clients/${client}/workloads/${wl}/logs?lines=${lines}`); }
    reloadClient(name)         { return this._fetch(`/fleet/clients/${name}/reload`, { method: 'POST' }); }

    /* Deployments */
    listDeployments(limit = 20)  { return this._fetch(`/fleet/deployments?limit=${limit}`); }
    getDeployment(id)            { return this._fetch(`/fleet/deployments/${id}`); }
    createDeployment(data)       { return this._fetch('/fleet/deployments', { method: 'POST', body: JSON.stringify(data) }); }
    cancelDeployment(id)         { return this._fetch(`/fleet/deployments/${id}/cancel`, { method: 'POST' }); }
}

window.api = new APIClient(window.API_BASE, window.API_TOKEN);

/* Shared utilities */
function showToast(message, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
}

function badge(status) {
    return `<span class="badge badge-${status}">${status}</span>`;
}

function timeAgo(iso) {
    if (!iso) return '—';
    const diff = Date.now() - new Date(iso).getTime();
    const s = Math.floor(diff / 1000);
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return new Date(iso).toLocaleDateString();
}

function fmtTime(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString();
}

/* Auto-refresh helper */
class Refresher {
    constructor(fn, intervalMs) {
        this._fn = fn;
        this._ms = intervalMs;
        this._id = null;
    }
    start() {
        this._fn();
        this._id = setInterval(() => this._fn(), this._ms);
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) { clearInterval(this._id); }
            else { this._fn(); this._id = setInterval(() => this._fn(), this._ms); }
        });
    }
}
