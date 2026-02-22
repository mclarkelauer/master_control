/* Master Control — Fleet Overview */

let allClients = [];
let currentFilter = 'all';
let currentSort = 'name';
let sortAscending = true;
let viewMode = localStorage.getItem('fleetViewMode') || 'grid';

function memPct(c) {
    const sys = c.system || {};
    return sys.memory_total_mb ? (sys.memory_used_mb / sys.memory_total_mb * 100) : 0;
}

async function loadFleet() {
    try {
        const clients = await api.listClients();
        allClients = clients;

        clients.forEach(c => {
            const sys = c.system || {};
            sparklineStore.addDataPoint(c.name, 'cpu', sys.cpu_percent || 0);
            sparklineStore.addDataPoint(c.name, 'memory', memPct(c));
        });

        renderSummary(clients);
        applyFiltersAndSort();
    } catch (err) {
        document.getElementById('client-grid').innerHTML =
            '<p class="text-dim">Failed to load fleet data.</p>';
    }
}

function applyFiltersAndSort() {
    const search = (document.getElementById('search-input')?.value || '').toLowerCase();

    let filtered = allClients.filter(c => {
        if (currentFilter !== 'all' && c.status !== currentFilter) return false;
        if (search && !c.name.toLowerCase().includes(search) &&
            !c.host.toLowerCase().includes(search)) return false;
        return true;
    });

    filtered.sort((a, b) => {
        let va, vb;
        switch (currentSort) {
            case 'name':     va = a.name.toLowerCase(); vb = b.name.toLowerCase(); break;
            case 'cpu':      va = a.system?.cpu_percent || 0; vb = b.system?.cpu_percent || 0; break;
            case 'memory':   va = memPct(a); vb = memPct(b); break;
            case 'workloads':va = a.workloads_running; vb = b.workloads_running; break;
            case 'last_seen':va = a.last_seen ? new Date(a.last_seen).getTime() : 0;
                             vb = b.last_seen ? new Date(b.last_seen).getTime() : 0; break;
            default:         va = 0; vb = 0;
        }
        if (va < vb) return sortAscending ? -1 : 1;
        if (va > vb) return sortAscending ? 1 : -1;
        return 0;
    });

    if (viewMode === 'grid') renderGrid(filtered);
    else renderTable(filtered);
}

function renderSummary(clients) {
    const total = clients.length;
    const online = clients.filter(c => c.status === 'online').length;
    document.getElementById('total-count').textContent = total;
    document.getElementById('online-count').textContent = online;
    document.getElementById('offline-count').textContent = total - online;
}

function renderGrid(clients) {
    const grid = document.getElementById('client-grid');
    grid.className = 'client-grid';

    if (!clients.length) {
        grid.innerHTML = '<div class="empty-state">No clients match your filters.</div>';
        return;
    }

    const spark = new Sparkline(80, 25);

    grid.innerHTML = clients.map(c => {
        const sys = c.system || {};
        const mp = Math.round(memPct(c));
        const cpuSvg = spark.render(sparklineStore.getDataPoints(c.name, 'cpu'), 'var(--primary)');
        const memSvg = spark.render(sparklineStore.getDataPoints(c.name, 'memory'), 'var(--warning)');

        return `
        <div class="client-card" onclick="location.href='/clients/${c.name}'">
            <div class="client-card-header">
                <h3>${c.name}</h3>
                ${badge(c.status)}
            </div>
            <div class="client-card-meta">${c.host}:${c.api_port}</div>
            <div class="client-card-stats">
                <span class="label">CPU</span><span>${(sys.cpu_percent || 0).toFixed(1)}%</span>
                <span class="label">Memory</span><span>${mp}%</span>
                <span class="label">Workloads</span><span>${c.workloads_running}/${c.workload_count}</span>
                <span class="label">Failed</span><span class="${c.workloads_failed ? 'text-danger' : ''}">${c.workloads_failed}</span>
            </div>
            <div class="sparkline-container">
                <span class="sparkline-label">CPU</span>${cpuSvg}
            </div>
            <div class="sparkline-container">
                <span class="sparkline-label">Mem</span>${memSvg}
            </div>
            <div class="client-card-footer">
                Version: ${c.deployed_version || 'unknown'} · ${timeAgo(c.last_seen)}
            </div>
        </div>`;
    }).join('');
}

function renderTable(clients) {
    const grid = document.getElementById('client-grid');
    grid.className = '';

    if (!clients.length) {
        grid.innerHTML = '<div class="empty-state">No clients match your filters.</div>';
        return;
    }

    const rows = clients.map(c => {
        const sys = c.system || {};
        const mp = Math.round(memPct(c));
        return `
        <tr onclick="location.href='/clients/${c.name}'">
            <td class="client-name">${c.name}</td>
            <td>${badge(c.status)}</td>
            <td>${c.host}:${c.api_port}</td>
            <td>${(sys.cpu_percent || 0).toFixed(1)}%</td>
            <td>${mp}%</td>
            <td>${c.workloads_running}/${c.workload_count}</td>
            <td>${c.deployed_version || 'unknown'}</td>
            <td>${timeAgo(c.last_seen)}</td>
        </tr>`;
    }).join('');

    grid.innerHTML = `
        <div class="table-wrap">
        <table class="client-table">
            <thead><tr>
                <th>Name</th><th>Status</th><th>Host</th>
                <th>CPU</th><th>Memory</th><th>Workloads</th>
                <th>Version</th><th>Last Seen</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>
        </div>`;
}

/* Event handlers */

function setupHandlers() {
    document.getElementById('search-input').addEventListener('input', applyFiltersAndSort);

    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.status;
            applyFiltersAndSort();
        });
    });

    document.getElementById('sort-select').addEventListener('change', e => {
        currentSort = e.target.value;
        applyFiltersAndSort();
    });

    document.getElementById('sort-direction').addEventListener('click', e => {
        sortAscending = !sortAscending;
        e.currentTarget.textContent = sortAscending ? '↓' : '↑';
        applyFiltersAndSort();
    });

    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            viewMode = btn.dataset.view;
            localStorage.setItem('fleetViewMode', viewMode);
            applyFiltersAndSort();
        });
    });

    // Restore persisted view mode
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewMode);
    });
}

document.addEventListener('DOMContentLoaded', setupHandlers);
new Refresher(loadFleet, 5000).start();
