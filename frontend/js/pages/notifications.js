/** Notifications (/pages/notifications.html): everything the bell has told you, newest first.
 *  Filter to unread or one kind; open one to go to the work it is about (it is then marked read). */
import { api } from '../core/api.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { el } from '../core/utils.js';
import { renderNotification } from '../components/notification.js';
import { createEmptyState } from '../components/empty-state.js';
import { showError, showToast } from '../components/toast.js';

const { content } = await initLayout({ active: null, title: 'Notifications' });
const prefs = await api.get('/notifications/preferences').catch(() => ({ kinds: [] }));

const state = { page: 1, unread: '', kind: '' };
const list = el('div', { class: 'ct-card', style: { padding: 0 } });
const more = el('button', { class: 'ct-btn', type: 'button', onClick: () => load(state.page + 1) }, 'Show more');
const unreadSelect = el('select', { class: 'ct-select', 'aria-label': 'Show', onChange: (e) => { state.unread = e.target.value; load(1); } },
  el('option', { value: '' }, 'All'), el('option', { value: '1' }, 'Unread only'));
const kindSelect = el('select', { class: 'ct-select', 'aria-label': 'Kind', onChange: (e) => { state.kind = e.target.value; load(1); } },
  el('option', { value: '' }, 'Every kind'), prefs.kinds.map((k) => el('option', { value: k.kind }, k.label)));

async function load(page) {
  try {
    const data = await api.get('/notifications', { page, per_page: 30, unread: state.unread, kind: state.kind });
    state.page = page;
    const rows = data.items.map((n) => renderNotification(n));
    if (page === 1) list.replaceChildren(...(rows.length ? rows : [createEmptyState({ title: 'No notifications', message: 'You will be told here when work needs you.', icon: 'bell' })]));
    else list.append(...rows);
    more.classList.toggle('ct-hidden', page * 30 >= data.total);
  } catch (err) { showError(err); }
}

content.append(
  pageHeader('Notifications', 'Assignments, approvals waiting for you, work that turned Red or is due, and decisions on your requests.', [
    el('a', { class: 'ct-btn', href: '/pages/account.html#notifications' }, 'Choose what you get'),
    el('button', { class: 'ct-btn ct-btn--primary', type: 'button', onClick: async () => {
      try { await api.post('/notifications/read', { all: true }); showToast('All marked read', 'success'); load(1); } catch (err) { showError(err); }
    } }, 'Mark all read')]),
  el('div', { class: 'ct-filter-bar', style: { display: 'flex', gap: '8px', marginBottom: '16px' } }, unreadSelect, kindSelect),
  list,
  el('div', { style: { textAlign: 'center', marginTop: '16px' } }, more));
load(1);
