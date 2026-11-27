if (requireAuth()) {
  const fromEl = document.getElementById('from');
  const toEl = document.getElementById('to');

  function renderUsage(data) {
    fromEl.value = data.from || '';
    toEl.value = data.to || '';
    const rows = data.rows || [];
    const summary = data.summary || { users: [], failed_logins: 0, blocked_logins: 0 };
    const empty = rows.length === 0;
    document.getElementById('usage-empty').hidden = !empty;
    document.getElementById('usage-content').hidden = empty;
    if (empty) return;
    document.getElementById('summary-body').innerHTML = summary.users.map(u =>
      `<tr><td>${escapeHtml(u.username)}</td><td>${escapeHtml(u.requests)}</td><td>${escapeHtml(u.logins)}</td><td>${escapeHtml(u.active_days)}</td></tr>`
    ).join('');
    document.getElementById('usage-totals').innerHTML =
      `Failed logins: <strong>${escapeHtml(summary.failed_logins)}</strong> &middot; Blocked logins: <strong>${escapeHtml(summary.blocked_logins)}</strong>`;
    document.getElementById('rows-body').innerHTML = rows.map(r =>
      `<tr><td>${escapeHtml(r.day)}</td><td>${escapeHtml(r.username)}</td><td>${escapeHtml(r.network)}</td><td>${escapeHtml(r.country)}</td><td>${escapeHtml(r.requests)}</td><td>${escapeHtml(r.logins)}</td><td>${escapeHtml(r.failed_logins)}</td><td>${escapeHtml(r.blocked_logins)}</td></tr>`
    ).join('');
  }

  async function loadUsage(query) {
    try {
      renderUsage(await api('/usage' + (query || '')));
    } catch (err) {
      showFlash(err.message, 'error');
    }
  }

  document.getElementById('show-usage').addEventListener('click', () => {
    const params = new URLSearchParams({ from: fromEl.value, to: toEl.value });
    loadUsage('?' + params.toString());
  });

  loadUsage();
}
