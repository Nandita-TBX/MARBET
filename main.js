// ── API HELPER ────────────────────────────────────────────────────────────────
async function api(url, method = 'GET', body = null) {
  try {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    const res  = await fetch(url, opts);
    return await res.json();
  } catch (e) {
    console.error('API error:', e);
    return { success: false, message: 'Network error.' };
  }
}

// ── TOAST ─────────────────────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── LOGOUT ────────────────────────────────────────────────────────────────────
async function logout() {
  await api('/api/logout', 'POST');
  window.location.href = '/';
}