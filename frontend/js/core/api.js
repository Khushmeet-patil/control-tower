/**
 * The only way the frontend talks to the server.
 *   const data = await api.get('/audit-events', { page: 1, operation: 'create' });
 *   await api.post('/units', { name: 'QA' });
 * Errors throw ApiError { status, code, message, details }.
 */
const BASE = '/api/v1';

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function loginUrl() {
  const next = window.location.pathname + window.location.search;
  return next && next !== '/' && !next.startsWith('/index.html') ? `/?next=${encodeURIComponent(next)}` : '/';
}

function queryString(params) {
  if (!params) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    search.set(key, Array.isArray(value) ? value.join(',') : value);
  }
  const s = search.toString();
  return s ? `?${s}` : '';
}

async function request(method, path, { params, body } = {}) {
  const options = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
  if (method !== 'GET') {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body ?? {});
  }

  let response;
  try {
    response = await fetch(BASE + path + queryString(params), options);
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection.');
  }

  let data = null;
  try { data = await response.json(); } catch { /* empty body */ }

  if (!response.ok) {
    const err = data?.error || {};
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.location.href = loginUrl();
    }
    throw new ApiError(response.status, err.code || 'error', err.message || 'Request failed', err.details);
  }
  return data;
}

export const api = {
  get: (path, params) => request('GET', path, { params }),
  post: (path, body) => request('POST', path, { body }),
  put: (path, body) => request('PUT', path, { body }),
  patch: (path, body) => request('PATCH', path, { body }),
  del: (path, body) => request('DELETE', path, { body }),
};
