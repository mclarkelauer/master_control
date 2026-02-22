/* Master Control — Client Detail */

async function loadClient() {
    try {
        const [client, workloads] = await Promise.all([
            api.getClient(CLIENT_NAME),
            api.getClientWorkloads(CLIENT_NAME),
        ]);
        renderInfo(client);
        renderWorkloads(workloads);
    } catch (err) {
        document.getElementById('client-subtitle').textContent = 'Failed to load client data.';
    }
}

function renderInfo(c) {
    const s = document.getElementById('client-status');
    s.textContent = c.status;
    s.className = `badge badge-${c.status}`;
    document.getElementById('client-subtitle').textContent =
        `${c.host}:${c.api_port} · Last seen ${timeAgo(c.last_seen)}`;

    const sys = c.system || {};
    document.getElementById('system-metrics').innerHTML = `
        <div class="metric"><div class="value">${(sys.cpu_percent || 0).toFixed(1)}%</div><div class="label">CPU</div></div>
        <div class="metric"><div class="value">${Math.round(sys.memory_used_mb || 0)} / ${Math.round(sys.memory_total_mb || 0)} MB</div><div class="label">Memory</div></div>
        <div class="metric"><div class="value">${(sys.disk_used_gb || 0).toFixed(1)} / ${(sys.disk_total_gb || 0).toFixed(1)} GB</div><div class="label">Disk</div></div>
        <div class="metric"><div class="value">${c.deployed_version || 'unknown'}</div><div class="label">Version</div></div>`;

    document.getElementById('client-details').innerHTML = `
        <dt>Host</dt><dd>${c.host}</dd>
        <dt>Port</dt><dd>${c.api_port}</dd>
        <dt>Status</dt><dd>${c.status}</dd>
        <dt>Workloads</dt><dd>${c.workloads_running} running / ${c.workload_count} total</dd>
        <dt>Failed</dt><dd class="${c.workloads_failed ? 'text-danger' : ''}">${c.workloads_failed}</dd>
        <dt>Last Seen</dt><dd>${fmtTime(c.last_seen)}</dd>`;
}

function renderWorkloads(workloads) {
    const tbody = document.getElementById('workload-tbody');
    if (!workloads.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-dim">No workloads.</td></tr>';
        return;
    }
    tbody.innerHTML = workloads.map(w => `
        <tr>
            <td><strong>${w.name}</strong></td>
            <td>${w.type}</td>
            <td>${w.run_mode}</td>
            <td>${badge(w.status)}</td>
            <td>${w.pid || '—'}</td>
            <td>${w.run_count}</td>
            <td>${fmtTime(w.last_started)}</td>
            <td class="actions">
                <button class="btn btn-sm" onclick="doAction('start','${w.name}')">Start</button>
                <button class="btn btn-sm" onclick="doAction('stop','${w.name}')">Stop</button>
                <button class="btn btn-sm" onclick="doAction('restart','${w.name}')">Restart</button>
                <button class="btn btn-sm" onclick="showLogs('${w.name}')">Logs</button>
            </td>
        </tr>`).join('');
}

async function doAction(action, workload) {
    try {
        const fn = action === 'start' ? api.startWorkload
                 : action === 'stop'  ? api.stopWorkload
                 : api.restartWorkload;
        const result = await fn.call(api, CLIENT_NAME, workload);
        showToast(result.message);
        setTimeout(loadClient, 500);
    } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
    }
}

async function showLogs(workload) {
    document.getElementById('logs-title').textContent = `Logs: ${workload}`;
    document.getElementById('logs-content').textContent = 'Loading…';
    document.getElementById('logs-modal').classList.remove('hidden');
    try {
        const result = await api.getWorkloadLogs(CLIENT_NAME, workload);
        document.getElementById('logs-content').textContent =
            result.lines ? result.lines.join('\n') : 'No log output.';
    } catch (err) {
        document.getElementById('logs-content').textContent = `Error: ${err.message}`;
    }
}

function closeLogs() {
    document.getElementById('logs-modal').classList.add('hidden');
}

async function reloadConfigs() {
    try {
        const result = await api.reloadClient(CLIENT_NAME);
        const changes = result.changes || {};
        const parts = [];
        if (changes.added?.length)     parts.push(`added: ${changes.added.join(', ')}`);
        if (changes.removed?.length)   parts.push(`removed: ${changes.removed.join(', ')}`);
        if (changes.restarted?.length) parts.push(`restarted: ${changes.restarted.join(', ')}`);
        if (changes.unchanged?.length) parts.push(`unchanged: ${changes.unchanged.length}`);
        showToast(parts.length ? parts.join(' · ') : 'No changes detected.');
        setTimeout(loadClient, 500);
    } catch (err) {
        showToast(`Reload failed: ${err.message}`, 'error');
    }
}

new Refresher(loadClient, 5000).start();
