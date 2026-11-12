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
