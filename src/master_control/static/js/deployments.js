/* Master Control — Deployments */

/* === List page === */

async function loadDeployments() {
    try {
        const deployments = await api.listDeployments(20);
        renderDeploymentsList(deployments);
    } catch (err) {
        document.getElementById('deployments-list').innerHTML =
            '<p class="text-dim">Failed to load deployments.</p>';
    }
}

function renderDeploymentsList(deployments) {
    const el = document.getElementById('deployments-list');
    if (!deployments.length) {
        el.innerHTML = '<div class="empty-state">No deployments yet.</div>';
        return;
    }
    el.innerHTML = deployments.map(d => `
        <div class="deployment-card" onclick="location.href='/deployments/${d.id}'">
            <div class="deployment-card-header">
                <div><code>${d.id.substring(0, 8)}</code> · <strong>${d.version}</strong></div>
                ${badge(d.status)}
            </div>
            <div class="deployment-card-meta">
                <span>Targets: ${d.target_clients.join(', ')}</span>
                <span>Batch: ${d.batch_size}</span>
                <span>${fmtTime(d.created_at)}</span>
            </div>
        </div>`).join('');
}

function toggleCreateForm() {
    document.getElementById('create-form').classList.toggle('hidden');
}

async function createDeployment(event) {
    event.preventDefault();
    const form = event.target;
    const data = {
        version: form.version.value,
        batch_size: parseInt(form.batch_size.value, 10),
        health_check_timeout: parseFloat(form.health_check_timeout.value),
        auto_rollback: form.auto_rollback.checked,
    };
    try {
        const result = await api.createDeployment(data);
        location.href = `/deployments/${result.id}`;
    } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
    }
    return false;
}

/* === Detail page === */

async function loadDeploymentDetail() {
    try {
        const d = await api.getDeployment(DEPLOYMENT_ID);
        renderDeploymentDetail(d);
    } catch (err) {
        document.getElementById('deployment-details').innerHTML =
            '<p class="text-dim">Failed to load deployment.</p>';
    }
}

function renderDeploymentDetail(d) {
    const s = document.getElementById('deployment-status');
    s.textContent = d.status;
    s.className = `badge badge-${d.status}`;

    document.getElementById('deployment-version').textContent = `Version: ${d.version}`;

    const cancelBtn = document.getElementById('cancel-btn');
    if (d.status === 'pending' || d.status === 'in_progress') {
        cancelBtn.classList.remove('hidden');
    } else {
        cancelBtn.classList.add('hidden');
    }

    document.getElementById('deployment-details').innerHTML = `
        <dt>Version</dt><dd>${d.version}</dd>
        <dt>Status</dt><dd>${badge(d.status)}</dd>
        <dt>Batch Size</dt><dd>${d.batch_size}</dd>
        <dt>Targets</dt><dd>${d.target_clients.join(', ')}</dd>
        <dt>Created</dt><dd>${fmtTime(d.created_at)}</dd>
        ${d.started_at ? `<dt>Started</dt><dd>${fmtTime(d.started_at)}</dd>` : ''}
        ${d.completed_at ? `<dt>Completed</dt><dd>${fmtTime(d.completed_at)}</dd>` : ''}
        ${d.error ? `<dt>Error</dt><dd class="text-danger">${d.error}</dd>` : ''}`;

    const tbody = document.getElementById('client-statuses-tbody');
    if (!d.client_statuses.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-dim">No client records.</td></tr>';
        return;
    }
    tbody.innerHTML = d.client_statuses.map(c => `
        <tr>
            <td><a href="/clients/${c.client_name}">${c.client_name}</a></td>
            <td>${c.batch_number}</td>
            <td>${badge(c.status)}</td>
            <td>${c.previous_version || '—'}</td>
            <td>${fmtTime(c.started_at)}</td>
            <td>${fmtTime(c.completed_at)}</td>
            <td class="${c.error ? 'text-danger' : ''}">${c.error || '—'}</td>
        </tr>`).join('');
}

async function cancelDeployment() {
    if (!confirm('Cancel this deployment?')) return;
    try {
        await api.cancelDeployment(DEPLOYMENT_ID);
        showToast('Deployment cancelled.');
        setTimeout(loadDeploymentDetail, 500);
    } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
    }
}

/* === Init === */

if (typeof PAGE_MODE !== 'undefined' && PAGE_MODE === 'list') {
    new Refresher(loadDeployments, 10000).start();
} else if (typeof PAGE_MODE !== 'undefined' && PAGE_MODE === 'detail') {
    new Refresher(loadDeploymentDetail, 3000).start();
}
