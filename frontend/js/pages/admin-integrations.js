/** Integrations (/pages/admin/integrations.html): how Control Tower talks to other systems.
 *  - Status: email (SMTP), Microsoft Entra ID sign-in, the public address used in links.
 *  - Webhooks and Microsoft Teams channels: what is sent where, test messages, secrets.
 *  - Deliveries: every email and webhook message, with failures and retries.
 *  - API tokens: everyone's tokens, which administrators can revoke. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { el, formatDateTime } from '../core/utils.js';
import { createDataTable } from '../components/data-table.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog, openModal } from '../components/modal.js';
import { createTabs } from '../components/tabs.js';
import { showError, showToast } from '../components/toast.js';
import { treeOptions } from '../components/tree.js';

const { content } = await initLayout({ active: 'integrations', title: 'Integrations', permission: 'integrations.manage' });
const [status, units] = await Promise.all([
  api.get('/integrations/status').catch((e) => { showError(e); return null; }),
  api.get('/units').then((d) => d.items).catch(() => []),
]);
let catalog = { entities: [], operations: [], alerts: [], formats: [] };

const pill = (ok, yes, no) => el('span', { class: `ct-status-pill ${ok ? 'is-good' : 'is-warn'}` }, ok ? yes : no);
const statusCard = status ? el('section', { class: 'ct-grid-3' },
  el('div', { class: 'ct-card' }, el('h3', {}, 'Email'), pill(status.email.configured, 'Set up', 'Not set up'),
    el('p', { class: 'ct-muted ct-small' }, status.email.configured ? `Sent through ${status.email.server} as ${status.email.from}.`
      : 'Set MAIL_SERVER (and MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM) in backend/.env. Until then people get in-app notifications only.')),
  el('div', { class: 'ct-card' }, el('h3', {}, 'Microsoft Entra ID'), pill(status.entra.configured, 'Sign-in on', 'Not set up'),
    el('p', { class: 'ct-muted ct-small' }, status.entra.configured
      ? [`Redirect address to register: ${status.entra.redirect_uri}. `, status.entra.password_sign_in ? 'Passwords still work too.' : 'Only administrators may still use passwords.']
      : 'Set ENTRA_TENANT_ID, ENTRA_CLIENT_ID and ENTRA_CLIENT_SECRET in backend/.env to add “Sign in with Microsoft”. Accounts are matched by email.')),
  el('div', { class: 'ct-card' }, el('h3', {}, 'Scheduled jobs'), el('p', { class: 'ct-muted ct-small' },
    'Send queued email and webhooks every minute: ', el('code', {}, 'flask --app run notify --deliver'), '. Daily checks (due soon, overdue, turned Red), e.g. at 07:00: ',
    el('code', {}, 'flask --app run notify --checks'), '. Links in messages use ', el('code', {}, status.base_url || 'APP_BASE_URL'), '.'))) : null;

const panels = { webhooks: el('div', { class: 'ct-stack' }), deliveries: el('div'), tokens: el('div') };
const tabs = createTabs({
  tabs: [{ key: 'webhooks', label: 'Webhooks & Teams', render: () => panels.webhooks },
    { key: 'deliveries', label: 'Deliveries', render: () => panels.deliveries },
    { key: 'tokens', label: 'API tokens', render: () => panels.tokens }],
  active: 'webhooks',
});

content.append(
  pageHeader('Integrations', 'Notifications by email and Microsoft Teams, webhooks for other systems, API tokens, and Microsoft sign-in.'),
  statusCard, el('section', { class: 'ct-card' }, tabs.element));

// ------------------------------------------------------------------ webhooks
const hooks = createDataTable({
  columns: [
    { key: 'name', label: 'Webhook', render: (w) => el('div', {}, el('strong', {}, w.name), el('div', { class: 'ct-muted ct-small' }, `${w.format === 'teams' ? 'Teams channel' : 'JSON'} · ${w.host}`)) },
    { key: 'events', label: 'Sends', render: (w) => el('div', { class: 'ct-small' }, w.events.join(', ')) },
    { key: 'unit', label: 'Work in', render: (w) => w.unit?.name || 'Whole organisation' },
    { key: 'is_active', label: 'State', render: (w) => pill(w.is_active, 'On', 'Off') },
    { key: 'deliveries', label: 'Sent / waiting / failed', render: (w) => `${w.deliveries.sent} / ${w.deliveries.pending} / ${w.deliveries.failed}` },
    { key: 'actions', label: '', render: (w) => el('div', { style: { display: 'flex', gap: '6px', flexWrap: 'wrap' } },
      el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: (e) => { e.stopPropagation(); testHook(w); } }, 'Send test'),
      el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: (e) => { e.stopPropagation(); editHook(w); } }, 'Edit'),
      el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: (e) => { e.stopPropagation(); rotate(w); } }, 'New secret'),
      el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', type: 'button', onClick: (e) => { e.stopPropagation(); removeHook(w); } }, 'Delete')) },
  ],
  fetchPage: async (q) => { const d = await api.get('/webhooks', q); catalog = d.catalog; return d; },
  emptyState: { title: 'No webhooks', message: 'Add a Microsoft Teams channel to post alerts there, or a webhook to send changes to another system.', icon: 'plug' },
});
hooks.setFilters({});
panels.webhooks.append(
  el('div', { class: 'ct-detail-head' }, el('p', { class: 'ct-muted', style: { margin: 0 } },
    'Teams: in the channel, add the “Incoming Webhook” connector (or a Workflows webhook) and paste its address here with the Teams format. Other systems get signed JSON (header X-ControlTower-Signature = sha256 HMAC of the body with the secret).'),
  el('button', { class: 'ct-btn ct-btn--primary', type: 'button', onClick: () => editHook(null) }, icon('plus', { size: 16 }), 'Webhook')),
  hooks.element);

function eventFields(selected = []) {
  const ops = (code) => (code === 'approval_request' ? ['create', 'approve', 'reject', 'complete', 'cancel'] : ['create', 'update', 'delete']);
  const options = [
    ...catalog.alerts.map((a) => ({ value: a.code, label: a.label, group: 'Alerts (also sent as notifications)' })),
    ...catalog.entities.flatMap((e) => [{ value: `${e.code}.*`, label: 'Every change', group: e.label },
      ...ops(e.code).map((op) => ({ value: `${e.code}.${op}`, label: op[0].toUpperCase() + op.slice(1), group: e.label }))]),
  ];
  return { key: 'events', label: 'What to send', type: 'checkboxes', options, full: true, value: selected };
}

async function editHook(w) {
  if (!catalog.formats.length) catalog = (await api.get('/webhooks', { per_page: 1 }).catch(() => ({ catalog }))).catalog;
  openFormModal({
    title: w ? `Edit ${w.name}` : 'New webhook',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'format', label: 'Format', type: 'select', options: (catalog.formats.length ? catalog.formats : [{ code: 'json', label: 'Signed JSON' }, { code: 'teams', label: 'Microsoft Teams channel' }]).map((f) => ({ value: f.code, label: f.label })) },
      { key: 'url', label: 'Address', type: 'url', required: true, full: true, help: w ? 'Leave as it is unless the address changed.' : 'Starts with https://' },
      { key: 'unit_id', label: 'Only work in', type: 'select', options: treeOptions(units), placeholder: 'The whole organisation' },
      { key: 'is_active', label: 'State', type: 'checkbox', checkboxLabel: 'On', default: true },
      eventFields(w?.events || ['alert.item_red', 'alert.approval_needed']),
      { key: 'description', label: 'Notes', type: 'textarea', full: true },
    ],
    values: w ? { ...w } : { format: 'teams', is_active: true },
    onSubmit: (v) => {
      const body = { ...v, unit_id: v.unit_id || null };
      return w ? api.patch(`/webhooks/${w.id}`, { ...body, version: w.version }) : api.post('/webhooks', body);
    },
    onDone: (saved) => {
      hooks.reload();
      if (!w && saved.secret) showSecret(saved);
      else showToast('Webhook saved', 'success');
    },
  });
}

function showSecret(w) {
  openModal({ title: `Secret for ${w.name}`, body: el('div', { class: 'ct-stack' },
    el('p', {}, 'Systems receiving this webhook use the secret to check that messages really come from Control Tower. It is shown only now. (Teams does not need it.)'),
    el('div', { class: 'ct-secret' }, w.secret)) });
}

async function testHook(w) {
  try {
    const d = await api.post(`/webhooks/${w.id}/test`, {});
    showToast(d.status === 'sent' ? `Test sent (HTTP ${d.response_code})` : `Test failed: ${d.last_error}`, d.status === 'sent' ? 'success' : 'error');
    hooks.reload();
  } catch (err) { showError(err); }
}

async function rotate(w) {
  if (!await confirmDialog({ title: 'Make a new secret?', message: 'The receiving system must be given the new secret, or it will reject the messages.', confirmLabel: 'New secret' })) return;
  try { showSecret(await api.post(`/webhooks/${w.id}/rotate-secret`, {})); } catch (err) { showError(err); }
}

async function removeHook(w) {
  if (!await confirmDialog({ title: `Delete ${w.name}?`, message: 'Nothing more is sent to it. Messages waiting to be sent are dropped.', confirmLabel: 'Delete', danger: true })) return;
  try { await api.del(`/webhooks/${w.id}`, { reason: 'Webhook removed' }); hooks.reload(); } catch (err) { showError(err); }
}

// ------------------------------------------------------------------ deliveries
const STATE = { sent: 'is-good', pending: 'is-warn', failed: 'is-bad' };
const deliveries = createDataTable({
  columns: [
    { key: 'created_at', label: 'Queued', render: (d) => formatDateTime(d.created_at) },
    { key: 'channel', label: 'To', render: (d) => el('div', {}, d.channel === 'email' ? 'Email' : 'Webhook', el('div', { class: 'ct-muted ct-small' }, d.target)) },
    { key: 'event', label: 'Event', render: (d) => el('div', {}, d.event, d.subject ? el('div', { class: 'ct-muted ct-small' }, d.subject) : null) },
    { key: 'status', label: 'State', render: (d) => el('span', { class: `ct-status-pill ${STATE[d.status] || ''}` }, d.status) },
    { key: 'attempts', label: 'Tries', render: (d) => String(d.attempts) },
    { key: 'last_error', label: 'Problem', render: (d) => (d.last_error ? el('span', { class: 'ct-text-danger ct-small' }, d.last_error) : '—') },
    { key: 'actions', label: '', render: (d) => (d.status !== 'sent' ? el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: async () => {
      try { await api.post(`/deliveries/${d.id}/retry`, {}); showToast('Will be sent again by the next run', 'success'); deliveries.reload(); } catch (err) { showError(err); }
    } }, 'Retry') : null) },
  ],
  fetchPage: (q) => api.get('/deliveries', q),
  emptyState: { title: 'Nothing sent yet', message: 'Emails and webhook messages appear here when they are queued.', icon: 'inbox' },
});
const deliveryFilter = el('select', { class: 'ct-select', 'aria-label': 'State', onChange: (e) => deliveries.setFilters({ status: e.target.value }) },
  el('option', { value: '' }, 'Every state'), ['pending', 'sent', 'failed'].map((s) => el('option', { value: s }, s)));
deliveries.setFilters({});
panels.deliveries.append(el('div', { style: { marginBottom: '12px' } }, deliveryFilter), deliveries.element);

// ------------------------------------------------------------------ all tokens
const tokens = createDataTable({
  columns: [
    { key: 'name', label: 'Token', render: (t) => el('div', {}, el('strong', {}, t.name), el('div', { class: 'ct-muted ct-small' }, `${t.prefix}…`)) },
    { key: 'owner', label: 'Acts as', render: (t) => t.owner?.full_name || '—' },
    { key: 'scopes', label: 'Scopes', render: (t) => t.scopes.join(', ') },
    { key: 'state', label: 'State', render: (t) => el('span', { class: `ct-status-pill ${{ active: 'is-good', expired: 'is-warn', revoked: 'is-bad' }[t.state]}` }, t.state) },
    { key: 'last_used_at', label: 'Last used', render: (t) => (t.last_used_at ? formatDateTime(t.last_used_at) : '—') },
    { key: 'actions', label: '', render: (t) => (t.state === 'active' ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', type: 'button', onClick: async () => {
      if (!await confirmDialog({ title: `Revoke “${t.name}”?`, message: `Anything using ${t.owner?.full_name}'s token stops working at once.`, confirmLabel: 'Revoke', danger: true })) return;
      try { await api.post(`/api-tokens/${t.id}/revoke`, { reason: 'Revoked by an administrator' }); tokens.reload(); } catch (err) { showError(err); }
    } }, 'Revoke') : null) },
  ],
  fetchPage: (q) => api.get('/api-tokens', q),
  emptyState: { title: 'No API tokens', message: 'People make their own under My account.', icon: 'key' },
});
tokens.setFilters({});
panels.tokens.append(tokens.element);
