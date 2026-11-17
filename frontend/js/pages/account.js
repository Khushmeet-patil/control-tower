/** My account (/pages/account.html): which notifications you get and how, your calendar feed for
 *  Outlook, and your personal API tokens (for Power BI, scripts and tools that write back). */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { el, formatDate, formatDateTime } from '../core/utils.js';
import { openChangePassword } from '../components/change-password.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog, openModal } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';

const { user, content } = await initLayout({ active: null, title: 'My account' });

content.append(pageHeader('My account', `${user.full_name} · ${user.email}`, [
  el('button', { class: 'ct-btn', type: 'button', onClick: openChangePassword }, icon('key', { size: 16 }), 'Change password')]));

// ------------------------------------------------------------------ notifications
const prefsCard = el('section', { class: 'ct-card', id: 'notifications' });
content.append(prefsCard);

async function renderPrefs() {
  let prefs;
  try { prefs = await api.get('/notifications/preferences'); } catch (err) { showError(err); return; }
  const toggles = new Map();
  const box = (kind, channel, checked, disabled) => {
    const input = el('input', { type: 'checkbox', checked, disabled, 'aria-label': `${kind.label}: ${channel === 'in_app' ? 'in Control Tower' : 'by email'}` });
    toggles.set(`${kind.kind}:${channel}`, input);
    return input;
  };
  const table = el('table', { class: 'ct-table ct-pref-table' },
    el('thead', {}, el('tr', {}, el('th', {}, 'Tell me when…'), el('th', {}, 'In Control Tower'), el('th', {}, 'By email'))),
    el('tbody', {}, prefs.kinds.map((k) => el('tr', {},
      el('td', {}, el('strong', {}, k.label), el('div', { class: 'ct-muted ct-small' }, k.description)),
      el('td', {}, box(k, 'in_app', k.in_app)),
      el('td', {}, box(k, 'email', k.email, !prefs.email_available))))));
  const save = el('button', { class: 'ct-btn ct-btn--primary', type: 'button', onClick: async () => {
    const kinds = {};
    for (const k of prefs.kinds) kinds[k.kind] = { in_app: toggles.get(`${k.kind}:in_app`).checked, email: toggles.get(`${k.kind}:email`).checked };
    try { await api.put('/notifications/preferences', { kinds }); showToast('Notification settings saved', 'success'); } catch (err) { showError(err); }
  } }, 'Save');
  prefsCard.replaceChildren(
    el('h2', { class: 'ct-section-title' }, 'Notifications'),
    prefs.email_available ? null : el('p', { class: 'ct-muted ct-small' }, 'Email is not set up on this server yet, so only in-app notifications are sent.'),
    el('div', { class: 'ct-table-wrap' }, table),
    el('div', { style: { marginTop: '12px' } }, save));
}
renderPrefs();

// ------------------------------------------------------------------ calendar feed
if (can(user, 'work.view')) {
  const card = el('section', { class: 'ct-card', id: 'calendar' },
    el('h2', { class: 'ct-section-title' }, 'Calendar feed (Outlook)'),
    el('p', { class: 'ct-muted' }, 'Your deadlines (work you own, are responsible for or are assigned to) and your time off, as a calendar you can subscribe to. In Outlook: Add calendar → Subscribe from web → paste the address. It updates about every hour.'),
    el('button', { class: 'ct-btn', type: 'button', onClick: async () => {
      try {
        const link = await api.post('/calendar/link', {});
        openModal({ title: 'Your calendar address', body: el('div', { class: 'ct-stack' },
          el('p', {}, 'Copy it now: it is shown only once. Anyone with this address can see your deadlines, so keep it private. Revoke it below (Calendar feed) if it leaks.'),
          el('div', { class: 'ct-secret' }, link.url),
          el('button', { class: 'ct-btn', type: 'button', onClick: () => navigator.clipboard?.writeText(link.url).then(() => showToast('Copied', 'success')) }, 'Copy')) });
        renderTokens();
      } catch (err) { showError(err); }
    } }, icon('calendar', { size: 16 }), 'Make a calendar address'));
  content.append(card);
}

// ------------------------------------------------------------------ API tokens
const tokensCard = el('section', { class: 'ct-card', id: 'tokens' });
content.append(tokensCard);

const STATE = { active: 'is-good', expired: 'is-warn', revoked: 'is-bad' };

async function renderTokens() {
  if (!can(user, 'api.tokens') && !can(user, 'work.view')) return;
  let data = { items: [], scopes: {} };
  try { data = await api.get('/api-tokens', { mine: 1, per_page: 100 }); } catch (err) {
    if (err.status !== 403) showError(err);
    if (err.status === 403) { tokensCard.remove(); return; }
  }
  const rows = data.items.map((t) => el('tr', {},
    el('td', {}, el('strong', {}, t.name), el('div', { class: 'ct-muted ct-small' }, `${t.prefix}…`)),
    el('td', {}, t.scopes.join(', ')),
    el('td', {}, el('span', { class: `ct-status-pill ${STATE[t.state] || ''}` }, t.state)),
    el('td', {}, t.expires_at ? formatDate(t.expires_at) : 'Never'),
    el('td', {}, t.last_used_at ? formatDateTime(t.last_used_at) : '—'),
    el('td', {}, t.state === 'active' ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', type: 'button', onClick: async () => {
      if (!await confirmDialog({ title: `Revoke “${t.name}”?`, message: 'Anything using this token stops working at once.', confirmLabel: 'Revoke', danger: true })) return;
      try { await api.post(`/api-tokens/${t.id}/revoke`, { reason: 'Revoked by its owner' }); showToast('Token revoked', 'success'); renderTokens(); } catch (err) { showError(err); }
    } }, 'Revoke') : null)));
  tokensCard.replaceChildren(
    el('div', { class: 'ct-detail-head' }, el('h2', { class: 'ct-section-title' }, 'API tokens'),
      can(user, 'api.tokens') ? el('button', { class: 'ct-btn ct-btn--primary', type: 'button', onClick: newToken }, icon('plus', { size: 16 }), 'New token') : null),
    el('p', { class: 'ct-muted' }, 'A token acts as you, with your current access and never more. Use it in Power BI (Get data → Web → Advanced, header Authorization = Bearer <token>) with the reporting addresses below, or in scripts. Read tokens only read; write tokens can change records, and every change is in the audit log as made through the API.'),
    el('ul', { class: 'ct-change-list' },
      ['work-items', 'assignments', 'people', 'units'].map((d) => el('li', {}, el('code', {}, `${location.origin}/api/v1/reporting/${d}`), ' (add ?format=csv for CSV)'))),
    rows.length ? el('div', { class: 'ct-table-wrap', style: { marginTop: '12px' } }, el('table', { class: 'ct-table' },
      el('thead', {}, el('tr', {}, ['Name', 'Scopes', 'State', 'Expires', 'Last used', ''].map((h) => el('th', {}, h)))),
      el('tbody', {}, rows))) : el('p', { class: 'ct-muted ct-small' }, 'No tokens yet.'));
}

function newToken() {
  openFormModal({
    title: 'New API token',
    intro: 'The token is shown once, after you create it. Store it like a password.',
    fields: [
      { key: 'name', label: 'What it is for', required: true, full: true, placeholder: 'e.g. Power BI portfolio report' },
      { key: 'scope', label: 'Access', type: 'select', options: [{ value: 'read', label: 'Read only' }, { value: 'write', label: 'Read and write' }], default: 'read' },
      { key: 'expires_in_days', label: 'Expires after (days)', type: 'number', default: 90, help: '1 to 366 days.' },
    ],
    values: { scope: 'read', expires_in_days: 90 },
    submitLabel: 'Create token',
    onSubmit: (v) => api.post('/api-tokens', { name: v.name, scopes: [v.scope || 'read'], expires_in_days: v.expires_in_days || 90 }),
    onDone: (t) => {
      openModal({ title: 'Your new token', body: el('div', { class: 'ct-stack' },
        el('p', {}, 'Copy it now. It will not be shown again.'),
        el('div', { class: 'ct-secret' }, t.token),
        el('button', { class: 'ct-btn', type: 'button', onClick: () => navigator.clipboard?.writeText(t.token).then(() => showToast('Copied', 'success')) }, 'Copy')) });
      renderTokens();
    },
  });
}
renderTokens();
