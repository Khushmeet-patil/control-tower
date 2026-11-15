/** Approvals (the prototype's Validation Gate): what waits for me, what I submitted, what I decided,
 *  and requests stuck with nobody to ask. */
import { api } from '../core/api.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge } from '../core/lookups.js';
import { el, formatDate } from '../core/utils.js';
import { approvalBadge, openReview, waitingOn } from '../components/approval.js';
import { createDataTable } from '../components/data-table.js';
import { createKpis } from '../components/kpi.js';
import { createPersonCell } from '../components/person.js';
import { createTabs } from '../components/tabs.js';
import { safeLink } from '../components/work-table.js';

const { user, content } = await initLayout({ active: 'approvals', title: 'Approvals', permission: 'work.view' });
const showBlocked = user.is_admin || can(user, 'work.manage');

const itemCell = (r) => el('div', { class: 'ct-work-title' },
  el('a', { href: `/pages/item.html?id=${r.work_item.id}&tab=approvals` }, r.work_item.title),
  el('span', { class: 'ct-work-title__code' }, r.work_item.code, ' · ', r.chain_name));
const stepCell = (r) => (r.current_step !== null
  ? el('div', {}, `${r.current_step + 1} of ${r.step_count}: ${r.current_step_name}`)
  : el('span', { class: 'ct-muted' }, '—'));

const COLUMNS = {
  item: { key: 'item', label: 'Item', render: itemCell },
  type: { key: 'type', label: 'Type', render: (r) => lookupBadge(r.work_item.item_type_id) },
  step: { key: 'step', label: 'Step', render: stepCell },
  submitted: { key: 'submitted', label: 'Marked complete by', render: (r) => createPersonCell(r.submitted_by, formatDate(r.submitted_at)) },
  waiting: { key: 'waiting', label: 'Waiting', render: (r) => (r.waiting_days === null ? '—' : el('span', { class: r.waiting_days > 3 ? 'ct-text-danger' : null }, `${r.waiting_days} d`)) },
  evidence: { key: 'evidence', label: 'Evidence', render: (r) => (r.work_item.evidence_url ? safeLink(r.work_item.evidence_url, 'Open') : el('span', { class: 'ct-text-danger' }, 'none')) },
  status: { key: 'status', label: 'Status', render: (r) => approvalBadge(r.status) },
  with: { key: 'with', label: 'Waiting on', render: (r) => (r.status === 'pending' ? waitingOn(r) : '—') },
  note: { key: 'note', label: 'Why it waits', render: (r) => r.waiting_note || '—' },
  action: { key: 'action', label: '', render: (r) => el('button', { class: `ct-btn ct-btn--sm${r.can_decide ? ' ct-btn--primary' : ''}`, onClick: () => openReview(r.id, { onDone: refresh }) }, r.can_decide ? 'Review' : 'Open') },
};

function table(box, columns, empty) {
  return createDataTable({
    columns: columns.map((c) => COLUMNS[c]),
    fetchPage: (q) => api.get('/approvals', { ...q, box }),
    pageSize: 20,
    emptyState: empty,
  });
}

const tables = {};
const tabDefs = [
  { key: 'mine', label: 'Waiting for me', columns: ['item', 'type', 'step', 'submitted', 'waiting', 'evidence', 'action'], empty: { title: 'Nothing waits for you', message: 'Completed work that needs your approval appears here.', icon: 'check' } },
  { key: 'submitted', label: 'Submitted by me', columns: ['item', 'status', 'step', 'with', 'waiting', 'action'], empty: { title: 'Nothing submitted', message: 'Work you mark complete appears here while it is approved.' } },
  { key: 'decided', label: 'My decisions', columns: ['item', 'status', 'submitted', 'action'], empty: { title: 'No decisions yet' } },
  showBlocked ? { key: 'blocked', label: 'Nobody to ask', columns: ['item', 'step', 'note', 'waiting', 'action'], empty: { title: 'No stuck approvals', icon: 'check' } } : null,
].filter(Boolean);

const kpiSlot = el('div');
const tabs = createTabs({
  tabs: tabDefs.map((t) => ({ key: t.key, label: t.label, render: () => { tables[t.key] = table(t.key, t.columns, t.empty); return tables[t.key].element; } })),
  active: new URLSearchParams(location.search).get('box') || 'mine',
  onChange: (key) => history.replaceState(null, '', `?box=${key}`),
});

async function refresh() {
  Object.values(tables).forEach((t) => t.reload());
  const c = await api.get('/approvals/counts').catch(() => null);
  if (!c) return;
  kpiSlot.replaceChildren(createKpis([
    { value: c.waiting_for_me, label: 'Waiting for my approval', color: c.waiting_for_me ? 'var(--ct-warning)' : null, onClick: () => tabs.select('mine') },
    { value: c.submitted_pending, label: 'My work awaiting approval', onClick: () => tabs.select('submitted') },
    showBlocked ? { value: c.blocked, label: 'Stuck: nobody to ask', color: c.blocked ? 'var(--ct-danger)' : null, onClick: () => tabs.select('blocked') } : null,
  ]));
}

content.append(
  pageHeader('Approvals', 'Completed work counts towards progress only after the people in its approval chain approve it. Rejecting sends it back with your note.'),
  kpiSlot,
  el('section', { class: 'ct-card' }, tabs.element));
refresh();
