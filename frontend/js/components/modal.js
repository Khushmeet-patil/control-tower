/**
 * openModal({
 *   title: 'Edit unit',
 *   body: nodeOrString,
 *   wide: false,
 *   actions: [
 *     { label: 'Cancel' },                                    // closes
 *     { label: 'Save', variant: 'primary', onClick: async (close) => { ...; close(); } },
 *   ],
 * }) → { close, element }
 */
import { icon } from '../core/icons.js';
import { el } from '../core/utils.js';
import { showError } from './toast.js';

export function openModal({ title, body, actions = [{ label: 'Close' }], wide = false, onClose } = {}) {
  const previousFocus = document.activeElement;
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    document.removeEventListener('keydown', onKey);
    backdrop.remove();
    previousFocus?.focus?.();
    onClose?.();
  };

  const onKey = (e) => { if (e.key === 'Escape') close(); };

  const buttons = actions.map((action) => {
    const btn = el('button', { class: `ct-btn${action.variant ? ` ct-btn--${action.variant}` : ''}`, type: 'button' }, action.label);
    btn.addEventListener('click', async () => {
      if (!action.onClick) return close();
      btn.disabled = true;
      try { await action.onClick(close); } catch (err) { showError(err); } finally { btn.disabled = false; }
    });
    return btn;
  });

  const titleId = `modal-title-${Math.random().toString(36).slice(2, 8)}`;
  const dialog = el('div', { class: `ct-modal${wide ? ' ct-modal--wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId },
    el('div', { class: 'ct-modal__header' },
      el('h3', { id: titleId }, title),
      el('button', { class: 'ct-btn ct-btn--ghost ct-btn--icon', 'aria-label': 'Close', onClick: close }, icon('close'))),
    el('div', { class: 'ct-modal__body' }, body),
    buttons.length ? el('div', { class: 'ct-modal__footer' }, buttons) : null);

  const backdrop = el('div', { class: 'ct-modal-backdrop', onMousedown: (e) => { if (e.target === backdrop) close(); } }, dialog);
  document.body.append(backdrop);
  document.addEventListener('keydown', onKey);
  (dialog.querySelector('input, select, textarea') || dialog.querySelector('.ct-modal__footer .ct-btn:last-child') || dialog).focus?.();

  return { close, element: dialog };
}

/** Simple yes/no confirmation. Resolves true when confirmed. */
export function confirmDialog({ title = 'Are you sure?', message, confirmLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    let result = false;
    openModal({
      title,
      body: el('p', {}, message),
      onClose: () => resolve(result),
      actions: [
        { label: 'Cancel' },
        { label: confirmLabel, variant: danger ? 'danger' : 'primary', onClick: (close) => { result = true; close(); } },
      ],
    });
  });
}
