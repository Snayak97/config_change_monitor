/**
 * Real-time frontend interaction logic for Configuration Change Monitoring System
 */

// Tab Navigation
const tabButtons = document.querySelectorAll('.nav-item');
const tabPanes = document.querySelectorAll('.tab-pane');
const pageTitle = document.getElementById('page-title');
const pageDesc = document.getElementById('page-desc');

const tabMeta = {
  overview: { title: 'System Overview', desc: 'Real-time configuration tracking, diff computation & event bus status' },
  files: { title: 'Monitored Files', desc: 'Multi-format files monitored simultaneously with debouncing and SHA-256 checks' },
  events: { title: 'Change Events Stream', desc: 'Structured change sets containing added, updated, removed, and type changes' },
  webhook: { title: 'Webhook History', desc: 'Incoming payloads delivered by the notification pipeline with HMAC signature' },
  dlq: { title: 'DLQ & Fault Tolerance', desc: 'Dead Letter Queue storing failed events with circuit breaker status' }
};

function switchTab(tabId) {
  tabButtons.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });
  tabPanes.forEach(pane => {
    pane.classList.toggle('active', pane.id === `tab-${tabId}`);
  });
  if (tabMeta[tabId]) {
    pageTitle.textContent = tabMeta[tabId].title;
    pageDesc.textContent = tabMeta[tabId].desc;
  }
}

tabButtons.forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// Toast notification helper
function showToast(message, isError = false) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.style.borderColor = isError ? '#ef4444' : '#3b82f6';
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3500);
}

// Data fetching and live dashboard updates
async function fetchHealth() {
  try {
    const res = await fetch('/health');
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById('stat-files-count').textContent = data.monitored_files_count;
    document.getElementById('stat-queue-depth').textContent = data.queue_depth;
    document.getElementById('stat-dlq-count').textContent = data.dlq_records_count;
    document.getElementById('uptime-display').textContent = `Uptime: ${Math.floor(data.uptime_seconds)}s`;
    document.getElementById('badge-files').textContent = data.monitored_files_count;
    document.getElementById('badge-dlq').textContent = data.dlq_records_count;

    // Render Circuit Breakers
    const cbContainer = document.getElementById('circuit-breakers-container');
    cbContainer.innerHTML = '';
    const cbs = data.circuit_breakers || {};
    for (const [name, cb] of Object.entries(cbs)) {
      const card = document.createElement('div');
      card.className = 'cb-card';
      card.innerHTML = `
        <div class="cb-info">
          <h4>${name}</h4>
          <span>Failures: ${cb.failure_count} / ${cb.failure_threshold}</span>
        </div>
        <div class="cb-pill ${cb.state}">${cb.state}</div>
      `;
      cbContainer.appendChild(card);
    }
  } catch (err) {
    console.error('Failed to fetch health:', err);
  }
}

async function fetchFiles() {
  try {
    const res = await fetch('/files');
    if (!res.ok) return;
    const files = await res.json();
    const tbody = document.getElementById('files-table-body');
    tbody.innerHTML = '';

    files.forEach(f => {
      const tr = document.createElement('tr');
      const hashShort = f.last_hash ? f.last_hash.substring(0, 12) + '...' : 'none';
      tr.innerHTML = `
        <td><strong>${f.path}</strong><br><small style="color: #6b7280">${f.absolute_path}</small></td>
        <td><span class="format-badge ${f.format}">${f.format.toUpperCase()}</span></td>
        <td>${(f.size_bytes / 1024).toFixed(2)} KB</td>
        <td><span class="checksum" title="${f.last_hash}">${hashShort}</span></td>
        <td><span class="status-badge ${f.status}">${f.status}</span></td>
        <td>${f.last_modified_timestamp ? new Date(f.last_modified_timestamp).toLocaleTimeString() : 'N/A'}</td>
        <td>
          <button class="btn btn-ghost btn-sm" onclick="removeWatch('${encodeURIComponent(f.absolute_path)}')">Unwatch</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Failed to fetch files:', err);
  }
}

async function fetchEvents() {
  try {
    const res = await fetch('/events?limit=50');
    if (!res.ok) return;
    const events = await res.json();

    document.getElementById('stat-events-count').textContent = events.length;
    document.getElementById('badge-events').textContent = events.length;

    renderOverviewEvents(events.slice(0, 5));
    renderEventsAccordion(events);
  } catch (err) {
    console.error('Failed to fetch events:', err);
  }
}

function renderOverviewEvents(events) {
  const container = document.getElementById('overview-events-list');
  container.innerHTML = '';
  if (!events.length) {
    container.innerHTML = '<p style="color: #6b7280; font-size: 13px;">No configuration change events recorded yet.</p>';
    return;
  }

  events.forEach(ev => {
    const item = document.createElement('div');
    item.className = 'event-item';
    item.innerHTML = `
      <div class="event-header">
        <div class="event-header-left">
          <span class="event-file-name">${ev.file}</span>
          <div class="event-diff-summary">
            ${Object.keys(ev.changes.added).length ? `<span class="diff-tag added">+${Object.keys(ev.changes.added).length} added</span>` : ''}
            ${Object.keys(ev.changes.updated).length ? `<span class="diff-tag updated">~${Object.keys(ev.changes.updated).length} updated</span>` : ''}
            ${Object.keys(ev.changes.removed).length ? `<span class="diff-tag removed">-${Object.keys(ev.changes.removed).length} removed</span>` : ''}
            ${Object.keys(ev.changes.type_changes).length ? `<span class="diff-tag type">!${Object.keys(ev.changes.type_changes).length} type</span>` : ''}
          </div>
        </div>
        <span class="event-time">${new Date(ev.timestamp).toLocaleTimeString()}</span>
      </div>
    `;
    container.appendChild(item);
  });
}

function renderEventsAccordion(events) {
  const container = document.getElementById('events-accordion-container');
  container.innerHTML = '';
  if (!events.length) {
    container.innerHTML = '<p style="color: #6b7280; font-size: 14px;">No change events recorded.</p>';
    return;
  }

  events.forEach(ev => {
    const item = document.createElement('div');
    item.className = 'event-item';
    item.innerHTML = `
      <div class="event-header">
        <div class="event-header-left">
          <span class="event-file-name">📄 ${ev.file}</span>
          <div class="event-diff-summary">
            ${Object.keys(ev.changes.added).length ? `<span class="diff-tag added">+${Object.keys(ev.changes.added).length} added</span>` : ''}
            ${Object.keys(ev.changes.updated).length ? `<span class="diff-tag updated">~${Object.keys(ev.changes.updated).length} updated</span>` : ''}
            ${Object.keys(ev.changes.removed).length ? `<span class="diff-tag removed">-${Object.keys(ev.changes.removed).length} removed</span>` : ''}
            ${Object.keys(ev.changes.type_changes).length ? `<span class="diff-tag type">!${Object.keys(ev.changes.type_changes).length} type changes</span>` : ''}
          </div>
        </div>
        <span class="event-time">${ev.timestamp}</span>
      </div>
      <div class="event-body">
        <h4 style="margin-bottom: 8px; font-size: 13px; color: #9ca3af;">Structured Event JSON:</h4>
        <pre class="code-block">${JSON.stringify(ev, null, 2)}</pre>
      </div>
    `;

    const header = item.querySelector('.event-header');
    const body = item.querySelector('.event-body');
    header.addEventListener('click', () => {
      body.classList.toggle('open');
    });

    container.appendChild(item);
  });
}

async function fetchWebhookHistory() {
  try {
    const res = await fetch('/api/v1/test-webhook/history');
    if (!res.ok) return;
    const history = await res.json();
    document.getElementById('badge-webhook').textContent = history.length;

    const container = document.getElementById('webhook-history-container');
    container.innerHTML = '';
    if (!history.length) {
      container.innerHTML = '<p style="color: #6b7280; font-size: 14px;">No webhooks received yet. Modify any monitored configuration file to trigger a webhook!</p>';
      return;
    }

    history.forEach(item => {
      const card = document.createElement('div');
      card.className = 'event-item';
      card.innerHTML = `
        <div class="event-header">
          <div class="event-header-left">
            <span class="event-file-name">🔔 Webhook Received [${item.payload.file || 'event'}]</span>
            <span class="diff-tag added">200 OK</span>
          </div>
          <span class="event-time">${item.received_at}</span>
        </div>
        <div class="event-body open">
          <div style="margin-bottom: 6px; font-size: 12px; color: #9ca3af;">
            <strong>HMAC Signature:</strong> <code>${item.signature || 'none'}</code>
          </div>
          <pre class="code-block">${JSON.stringify(item.payload, null, 2)}</pre>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    console.error('Failed to fetch webhook history:', err);
  }
}

async function fetchDLQ() {
  try {
    const res = await fetch('/api/v1/dlq');
    if (!res.ok) return;
    const records = await res.json();
    const container = document.getElementById('dlq-records-container');
    container.innerHTML = '';

    if (!records.length) {
      container.innerHTML = '<p style="color: #10b981; font-size: 14px;">✅ Dead Letter Queue is currently empty! All events were delivered successfully.</p>';
      return;
    }

    records.forEach(rec => {
      const card = document.createElement('div');
      card.className = 'event-item';
      card.innerHTML = `
        <div class="event-header">
          <div class="event-header-left">
            <span class="event-file-name">⚠️ Target: ${rec.target_name}</span>
            <span class="diff-tag removed">Attempts: ${rec.attempt_count}</span>
          </div>
          <button class="btn btn-primary btn-sm" onclick="replayDLQ('${rec.id}')">Replay Event</button>
        </div>
        <div class="event-body open">
          <p style="color: #f87171; font-size: 13px; margin-bottom: 8px;"><strong>Error:</strong> ${rec.last_error}</p>
          <pre class="code-block">${JSON.stringify(rec.event, null, 2)}</pre>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    console.error('Failed to fetch DLQ:', err);
  }
}

async function replayDLQ(recordId) {
  try {
    const res = await fetch(`/api/v1/dlq/replay/${recordId}`, { method: 'POST' });
    if (res.ok) {
      showToast('Event replayed successfully!');
      fetchDLQ();
      fetchHealth();
    } else {
      const err = await res.json();
      showToast(`Replay failed: ${err.detail}`, true);
    }
  } catch (e) {
    showToast(`Error replaying DLQ event: ${e}`, true);
  }
}

async function removeWatch(encodedPath) {
  const path = decodeURIComponent(encodedPath);
  if (!confirm(`Stop monitoring '${path}'?`)) return;
  try {
    const res = await fetch(`/watch/${encodedPath}`, { method: 'DELETE' });
    if (res.ok) {
      showToast(`Unwatched: ${path}`);
      fetchFiles();
      fetchHealth();
    } else {
      showToast('Failed to unwatch path', true);
    }
  } catch (e) {
    showToast(`Error: ${e}`, true);
  }
}

// Watch Modal Logic
const modal = document.getElementById('watch-modal');
const btnOpenModal = document.getElementById('btn-add-watch');
const btnOpenModalTrigger = document.getElementById('btn-add-file-trigger');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnCancelModal = document.getElementById('btn-cancel-modal');
const btnSubmitWatch = document.getElementById('btn-submit-watch');
const watchInputPath = document.getElementById('watch-input-path');

function openModal() {
  modal.classList.add('open');
  watchInputPath.focus();
}

function closeModal() {
  modal.classList.remove('open');
}

btnOpenModal.addEventListener('click', openModal);
if (btnOpenModalTrigger) btnOpenModalTrigger.addEventListener('click', openModal);
btnCloseModal.addEventListener('click', closeModal);
btnCancelModal.addEventListener('click', closeModal);

btnSubmitWatch.addEventListener('click', async () => {
  const path = watchInputPath.value.trim();
  if (!path) {
    showToast('Please enter a valid path', true);
    return;
  }

  try {
    const res = await fetch('/watch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });

    if (res.ok) {
      showToast(`Started monitoring: ${path}`);
      closeModal();
      watchInputPath.value = '';
      fetchFiles();
      fetchHealth();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Failed to watch path', true);
    }
  } catch (e) {
    showToast(`Network error: ${e}`, true);
  }
});

// Quick simulate change trigger
document.getElementById('btn-quick-test').addEventListener('click', async () => {
  try {
    const res = await fetch('/api/v1/simulate-change', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      showToast(`Simulation triggered: ${data.message}`);
      setTimeout(() => {
        fetchEvents();
        fetchWebhookHistory();
        fetchHealth();
      }, 700);
    } else {
      showToast('Simulation API failed', true);
    }
  } catch (e) {
    showToast(`Simulation error: ${e}`, true);
  }
});

// Clear Webhook History
document.getElementById('btn-clear-webhook-history')?.addEventListener('click', () => {
  document.getElementById('webhook-history-container').innerHTML = '<p style="color: #6b7280;">History cleared.</p>';
  document.getElementById('badge-webhook').textContent = '0';
  showToast('Webhook history cleared');
});

// Polling Loop
function refreshAll() {
  fetchHealth();
  fetchFiles();
  fetchEvents();
  fetchWebhookHistory();
  fetchDLQ();
}

// Initial load
refreshAll();
// Periodic polling every 3 seconds
setInterval(refreshAll, 3000);
