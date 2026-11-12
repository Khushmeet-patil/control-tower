/** Current user session helpers. */
import { api, ApiError } from './api.js';

let currentUserPromise = null;

/** Returns the signed-in user, or null. Cached for the page's lifetime. */
export function getCurrentUser({ refresh = false } = {}) {
  if (!currentUserPromise || refresh) {
    currentUserPromise = api.get('/auth/me')
      .then((data) => data.user)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      });
  }
  return currentUserPromise;
}

export async function login(email, password, remember = false) {
  const data = await api.post('/auth/login', { email, password, remember });
  currentUserPromise = Promise.resolve(data.user);
  return data.user;
}

export async function logout() {
  try { await api.post('/auth/logout'); } finally {
    currentUserPromise = null;
    window.location.href = '/';
  }
}
