// frontend/app.js
// Shared JavaScript used by all pages

const API_BASE = 'http://127.0.0.1:8000/api/v1';

// ── Direction toggle (used on dashboard + translate page) ──────────────

let currentDirection = 'en_to_lg';

function setDirection(dir) {
  currentDirection = dir;
  const btnEnLg = document.getElementById('btn-en-lg');
  const btnLgEn = document.getElementById('btn-lg-en');
  if (btnEnLg) btnEnLg.classList.toggle('active', dir === 'en_to_lg');
  if (btnLgEn) btnLgEn.classList.toggle('active', dir === 'lg_to_en');
}

// ── Backend health check (used on dashboard) ───────────────────────────

async function loadBackendStatus() {
  const statusEl = document.getElementById('backend-status');
  const dotEl = document.getElementById('backend-dot');

  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (statusEl) statusEl.textContent = 'Online';
    if (dotEl) {
      dotEl.classList.add('dot--online');
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = 'Offline';
    if (dotEl) dotEl.classList.add('dot--offline');
  }
}

// ── Collection stats (used on dashboard) ──────────────────────────────

async function loadCollectionStats() {
  const totalRecordsEl = document.getElementById('total-records');
  const totalCollectionsEl = document.getElementById('total-collections');
  const gridEl = document.getElementById('collections-grid');

  try {
    const res = await fetch(`${API_BASE}/knowledge/stats`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // data.collections is expected to be an object like:
    // { vocabulary: 294, sentences: 110, grammar: 28, proverbs: 60 }
    const collections = data.collections || {};
    const names = Object.keys(collections);
    const total = names.reduce((sum, k) => sum + (collections[k] || 0), 0);

    if (totalRecordsEl) totalRecordsEl.textContent = total.toLocaleString();
    if (totalCollectionsEl) totalCollectionsEl.textContent = names.length;

    // Render collection cards
    if (gridEl) {
      const icons = {
        vocabulary: '📖',
        sentences: '💬',
        grammar: '📐',
        proverbs: '🌿',
      };

      gridEl.innerHTML = names.map(name => `
        <div class="card card--collection">
          <div class="card-icon">${icons[name] || '📁'}</div>
          <div class="card-body">
            <div class="card-label">${capitalize(name)}</div>
            <div class="card-value">${(collections[name] || 0).toLocaleString()} records</div>
          </div>
        </div>
      `).join('');
    }

  } catch (err) {
    if (totalRecordsEl) totalRecordsEl.textContent = 'Error';
    if (gridEl) {
      gridEl.innerHTML = `
        <div class="card card--error">
          <p>Could not load stats. Is the backend running?</p>
        </div>
      `;
    }
  }
}

// ── Quick translate widget (used on dashboard) ─────────────────────────

async function quickTranslate() {
  const input = document.getElementById('q-input');
  const resultEl = document.getElementById('q-result');
  const errorEl = document.getElementById('q-error');

  if (!input || !input.value.trim()) return;

  resultEl.classList.add('hidden');
  errorEl.classList.add('hidden');

  try {
    const res = await fetch(`${API_BASE}/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: input.value.trim(),
        direction: currentDirection,
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.status === 'not_found') {
      resultEl.innerHTML = `
        <span class="q-notfound">No translation found in current dataset.</span>
      `;
    } else {
      resultEl.innerHTML = `
        <span class="q-translated">${data.translated_text}</span>
        <span class="q-badge q-badge--${data.match_type}">${data.match_type}</span>
        <span class="q-source">${data.matched_collection || ''}</span>
      `;
    }
    resultEl.classList.remove('hidden');

  } catch (err) {
    errorEl.textContent = `Error: ${err.message}`;
    errorEl.classList.remove('hidden');
  }
}

// ── Utilities ──────────────────────────────────────────────────────────

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// Allow Enter key on quick translate input
document.addEventListener('DOMContentLoaded', () => {
  const qInput = document.getElementById('q-input');
  if (qInput) {
    qInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') quickTranslate();
    });
  }
});