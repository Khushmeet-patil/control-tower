import { api } from '../core/api.js';
import { getCurrentUser, login } from '../core/auth.js';

const form = document.getElementById('login-form');
const errorBox = document.getElementById('login-error');
const submit = form.querySelector('button[type="submit"]');

function nextUrl() {
  const next = new URLSearchParams(window.location.search).get('next');
  // Only allow same-site relative paths.
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/pages/home.html';
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove('ct-hidden');
}

getCurrentUser().then((user) => { if (user) window.location.replace(nextUrl()); }).catch(() => {});

// A failed Microsoft sign-in comes back here with ?error=<message>.
const returned = new URLSearchParams(window.location.search).get('error');
if (returned) showError(returned === 'entra_not_configured' ? 'Microsoft sign-in is not set up.' : returned.slice(0, 300));

// "Sign in with Microsoft" when the server has Entra ID set up; password sign-in may be switched off.
api.get('/auth/entra')
  .then((cfg) => {
    if (!cfg?.enabled) return;
    document.getElementById('entra-block').classList.remove('ct-hidden');
    document.getElementById('entra-button').href = `/api/v1/auth/entra/login?next=${encodeURIComponent(nextUrl())}`;
    if (!cfg.password_sign_in) {
      document.getElementById('entra-or').textContent = 'Administrators can still use a password below.';
      document.getElementById('login-intro').textContent = 'Use your Microsoft work account.';
    }
  })
  .catch(() => {});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorBox.classList.add('ct-hidden');
  const email = form.email.value.trim();
  const password = form.password.value;
  if (!email || !password) {
    showError('Enter your email and password.');
    return;
  }
  submit.disabled = true;
  submit.textContent = 'Signing in…';
  try {
    await login(email, password, document.getElementById('remember').checked);
    window.location.replace(nextUrl());
  } catch (err) {
    showError(err.message);
    submit.disabled = false;
    submit.textContent = 'Sign in';
    form.password.select();
  }
});
