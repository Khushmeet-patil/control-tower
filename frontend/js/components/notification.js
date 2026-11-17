/** One notification: title, text, when, and a link. Opening it marks it read.
 *  renderNotification(n, { compact, onRead }) → element (the bell's panel and the Notifications page). */
import { api } from '../core/api.js';
import { el, formatDateTime } from '../core/utils.js';

export function renderNotification(n, { compact = false, onRead } = {}) {
  const markRead = async () => {
    if (n.read) return;
    n.read = true;
    row.classList.remove('is-unread');
    await api.post('/notifications/read', { ids: [n.id] }).catch(() => null);
    onRead?.();
  };
  // Links are always paths on this site (set by the server); never follow anything else.
  const href = n.link && n.link.startsWith('/') && !n.link.startsWith('//') ? n.link : null;
  const title = href
    ? el('a', { class: 'ct-notification__title', href, onClick: () => { markRead(); } }, n.title)
    : el('strong', { class: 'ct-notification__title' }, n.title);
  const row = el('div', { class: `ct-notification${n.read ? '' : ' is-unread'}${compact ? ' is-compact' : ''}` },
    el('span', { class: 'ct-notification__dot', 'aria-hidden': 'true' }),
    el('div', { class: 'ct-notification__body' },
      title,
      n.body && !compact ? el('p', { class: 'ct-notification__text' }, n.body) : null,
      el('span', { class: 'ct-muted ct-small' }, `${n.kind_label} · ${formatDateTime(n.created_at)}`)),
    !n.read && !compact ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--ghost', type: 'button', onClick: markRead }, 'Mark read') : null);
  return row;
}
