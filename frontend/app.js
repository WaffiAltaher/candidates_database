// API configuration — single container backend
const API_BASE = 'https://candidatesdb25d8ab32-candidates-api.functions.fnc.nl-ams.scw.cloud';
const API = {
  auth: API_BASE,
  candidates: API_BASE,
  search: API_BASE,
  upload: API_BASE,
};

function getToken() {
  return localStorage.getItem('auth_token');
}

function setToken(token) {
  localStorage.setItem('auth_token', token);
}

function clearToken() {
  localStorage.removeItem('auth_token');
}

function requireAuth() {
  if (!getToken()) {
    window.location.href = '/login.html';
    return false;
  }
  return true;
}

async function api(path, options = {}) {
  const token = getToken();
  const headers = options.headers || {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  const resp = await fetch(path, { ...options, headers });
  if (resp.status === 401) {
    clearToken();
    window.location.href = '/login.html';
    return null;
  }
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || resp.statusText);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

function showFlash(message, type = 'success') {
  let container = document.getElementById('flash-container');
  if (!container) return;
  const div = document.createElement('div');
  div.className = `flash flash-${type}`;
  div.textContent = message;
  container.appendChild(div);
  setTimeout(() => div.remove(), 5000);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}
