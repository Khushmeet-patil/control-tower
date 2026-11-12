/** showToast('Saved', 'success') — types: info | success | warning | error */
import { el } from '../core/utils.js';

function container() {
  let box = document.querySelector('.ct-toasts');
  if (!box) {
    box = el('div', { class: 'ct-toasts', role: 'status', 'aria-live': 'polite' });
    document.body.append(box);
  }
  return box;
}

export function showToast(message, type = 'info', timeout = 4000) {
  const toast = el('div', { class: `ct-toast ct-toast--${type}` }, message);
  container().append(toast);
  setTimeout(() => toast.remove(), timeout);
  return toast;
}

/** Show an ApiError (or any error) as a toast. */
export function showError(err) {
  return showToast(err?.message || 'Something went wrong', 'error', 6000);
}
