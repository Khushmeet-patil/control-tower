/** Demand intake (/pages/demand.html): the prototype's Demand Intake screen on real data.
 *  Requests with urgency, priority and effort; "Assess & decide" shows the delivering unit's free
 *  capacity, any shortfall and the lower-priority work that could be deferred; Accept can create a
 *  draft initiative in the same step. ?assess=<id> opens the assessment straight away (Action Centre). */
import { api } from '../core/api.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { icon } from '../core/icons.js';
import { lookupBadge, lookupOptions, lookupValues } from '../core/lookups.js';
import { el, formatDate } from '../core/utils.js';
import { createDataTable } from '../components/data-table.js';
import { createFilterBar } from '../components/filter-bar.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog, openModal } from '../components/modal.js';
import { createPersonCell } from '../components/person.js';
import { showError, showToast } from '../components/toast.js';
import { treeOptions } from '../components/tree.js';
import { healthBadgeFromCode } from '../components/health.js';

const { content } = await initLayout({ active: 'demand', title: 'Demand intake', permission: 'work.view' });
const units = await api.get('/units').then((d) => d.items).catch(() => []);
const url = new URLSearchParams(location.search);

const table = createDataTable({
  columns: [
    { key: 'code', label: 'ID', sortable: true },
    { key: 'title', label: 'Request', sortable: true, render: (r) => el('div', { class: 'ct-work-title' }, el('strong', {}, r.title),
      el('span', { class: 'ct-work-title__code' }, [r.unit?.name, r.work_item ? `became ${r.work_item.code}` : null].filter(Boolean).join(' · '))) },
    { key: 'requester', label: 'Requester', render: (r) => createPersonCell(r.requester) },
    { key: 'priority_id', label: 'Priority / urgency', sortable: true, render: (r) => el('div', { class: 'ct-tag-list' },
      r.priority_id ? lookupBadge(r.priority_id) : '—', r.urgency_id ? lookupBadge(r.urgency_id) : null) },
    { key: 'effort_pct', label: 'Effort (pts)', sortable: true, render: (r) => r.effort_pct ?? el('span', { class: 'ct-muted' }, 'not estimated') },
    { key: 'requested_on', label: 'Requested', sortable: true, render: (r) => el('div', {}, formatDate(r.requested_on),
      r.needed_by ? el('div', { class: 'ct-muted ct-small' }, `needed by ${formatDate(r.needed_by)}`) : null) },
    { key: 'decision_id', label: 'Decision', render: (r) => (r.decision_id ? lookupBadge(r.decision_id) : '—') },
    { key: 'actions', label: '', render: (r) => el('div', { class: 'ct-stack', style: { gap: '4px' } },
      el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: (e) => { e.stopPropagation(); assess(r.id); } },
        r.permissions.can_decide && r.awaiting ? 'Assess & decide' : 'Assess'),
      r.permissions.can_edit ? el('button', { class: 'ct-btn ct-btn--sm', onClick: (e) => { e.stopPropagation(); edit(r); } }, 'Edit') : null,
      r.permissions.can_delete && !r.work_item ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', onClick: (e) => { e.stopPropagation(); remove(r); } }, 'Delete') : null) },
  ],
  fetchPage: (q) => api.get('/demand', q),
  defaultSort: '-requested_on',
  onRowClick: (r) => assess(r.id),
  emptyState: { title: 'No requests', message: 'Requests for new work appear here.', icon: 'inbox' },
});

const filters = createFilterBar({
  fields: [
    { key: 'q', type: 'search', placeholder: 'Search requests…' },
    { key: 'awaiting', type: 'select', label: 'Requests', options: [{ value: '1', label: 'Awaiting decision' }] },
    { key: 'decision_id', type: 'select', label: 'Decisions', options: lookupOptions('demand_decision') },
    { key: 'priority_id', type: 'select', label: 'Priorities', options: lookupOptions('priority') },
    { key: 'unit_id', type: 'select', label: 'Units', options: treeOptions(units) },
  ],
  onChange: (v) => table.setFilters(v),
});
if (url.get('awaiting')) { filters.setValue('awaiting', '1'); }
table.setFilters(filters.getValues());

content.append(
  pageHeader('Demand intake', 'Requests for new work. Assess them against the free capacity of the team that would deliver them, then decide.',
    [el('button', { class: 'ct-btn ct-btn--primary', onClick: () => edit(null) }, icon('plus', { size: 16 }), 'Request')]),
  filters.element,
  el('section', { class: 'ct-card' }, table.element));

if (url.get('assess')) assess(Number(url.get('assess')));

// ------------------------------------------------------------------ raise and edit
function edit(existing) {
  openFormModal({
    title: existing ? `${existing.code} · ${existing.title}` : 'New request',
    intro: existing ? null : 'Effort is in capacity points: 1 point = 1% of one person\'s week (so 100 = one person full time). Leave it empty if you do not know yet.',
    fields: [
      { key: 'title', label: 'Request name', required: true, full: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'business_value', label: 'Business value', type: 'textarea' },
      { key: 'sponsor', label: 'Sponsor' },
      { key: 'unit_id', label: 'Team that would deliver it', type: 'select', options: treeOptions(units), help: 'Empty = your own unit.' },
      { key: 'urgency_id', label: 'Urgency', type: 'select', options: lookupOptions('urgency', existing?.urgency_id) },
      { key: 'priority_id', label: 'Priority', type: 'select', options: lookupOptions('priority', existing?.priority_id) },
      { key: 'effort_pct', label: 'Effort (capacity points)', type: 'number' },
      { key: 'needed_by', label: 'Needed by', type: 'date' },
      { key: 'dependencies', label: 'Dependencies', type: 'textarea' },
      { key: 'remarks', label: 'Remarks', type: 'textarea' },
      existing ? { key: 'reason', label: 'Reason for change', full: true } : null,
    ].filter(Boolean),
    values: existing || {},
    submitLabel: existing ? 'Save' : 'Submit request',
    onSubmit: (v) => (existing ? api.patch(`/demand/${existing.id}`, { ...v, version: existing.version }) : api.post('/demand', v)),
    onDone: (saved) => { showToast(existing ? 'Request saved' : `${saved.code} submitted`, 'success'); table.reload(); },
  });
}

async function remove(r) {
  if (!await confirmDialog({ title: `Delete ${r.code}?`, message: `“${r.title}” will be removed. The audit log keeps a record.`, confirmLabel: 'Delete', danger: true })) return;
  try { await api.del(`/demand/${r.id}`, { reason: 'Request withdrawn' }); showToast('Request deleted', 'success'); table.reload(); } catch (err) { showError(err); }
}

// ------------------------------------------------------------------ assess & decide
const VERDICT = {
  not_estimated: () => 'Effort not estimated: the impact cannot be assessed. Ask for clarification.',
  shortfall: (a) => `Shortfall of ${a.shortfall_pts} pts: accepting this means moving an existing commitment.`,
  fits: () => 'Fits within free capacity.',
};

async function assess(id) {
  let a;
  try { a = await api.get(`/demand/${id}/assessment`); } catch (err) { showError(err); return; }
  const r = a.request;
  const decider = r.permissions.can_decide;
  const body = el('div', { class: 'ct-stack' },
    el('p', {}, [r.priority_id ? lookupBadge(r.priority_id) : 'No priority', ' · ',
      `Effort ${r.effort_pct ?? '?'} pts · Requested ${formatDate(r.requested_on)}`, r.needed_by ? ` · Needed by ${formatDate(r.needed_by)}` : '',
      ' · ', r.decision_id ? lookupBadge(r.decision_id) : null]),
    r.business_value ? el('p', { class: 'ct-prose' }, el('strong', {}, 'Business value: '), r.business_value) : null,
    el('p', {}, el('strong', {}, `Free capacity in ${r.unit?.name || 'the team'}`), ` (after the ${a.buffer_pct}% buffer): ${a.free_pts} pts across ${a.people} people.`),
    el('div', { class: `ct-verdict is-${a.verdict}` }, VERDICT[a.verdict](a)),
    a.verdict === 'shortfall' && r.priority_id ? el('div', {},
      el('p', {}, el('strong', {}, 'Lower-priority work in delivery that could be deferred:')),
      a.candidates.length ? el('ul', { class: 'ct-change-list' }, a.candidates.map((c) => el('li', {},
        el('a', { href: `/pages/item.html?id=${c.id}` }, `${c.code} ${c.title}`), ' ', lookupBadge(c.priority_id), ' ', healthBadgeFromCode(c.health),
        el('span', { class: 'ct-muted' }, ` · ${c.allocated_pts} pts allocated`))))
        : el('p', { class: 'ct-muted' }, 'None: nothing lower priority to move, so this would displace equal or higher priority work.')) : null,
    r.decision_note ? el('p', { class: 'ct-small' }, el('strong', {}, 'Last decision note: '), r.decision_note,
      r.decided_by ? el('span', { class: 'ct-muted' }, ` (${r.decided_by.full_name}, ${formatDate(r.decided_at)})`) : null) : null,
    r.work_item ? el('p', {}, 'Became ', el('a', { href: `/pages/item.html?id=${r.work_item.id}` }, `${r.work_item.code} ${r.work_item.title}`)) : null);

  const decisionButtons = decider && !r.work_item ? a.decisions.map((d) => ({
    label: { accepted: 'Accept', rejected: 'Reject', deferred: 'Defer', clarification: 'Ask to clarify' }[d.code] || d.label,
    variant: d.code === 'accepted' ? 'primary' : null,
    onClick: (close) => { close(); decide(r, d); },
  })) : [];
  openModal({ title: `${r.code} · ${r.title}`, body, wide: true, actions: [{ label: 'Close' }, ...decisionButtons] });
}

function decide(r, decision) {
  const accepting = decision.code === 'accepted';
  const types = lookupValues('item_type');
  const project = types.find((t) => t.code === 'project');
  openFormModal({
    title: `${decision.label} · ${r.code}`,
    intro: accepting ? 'Accepting can create a draft initiative (Not started) from the request: its name, description, business value, priority and needed-by date are copied over.' : null,
    fields: [
      accepting ? { key: 'create', label: 'Create', type: 'checkbox', checkboxLabel: 'Create a draft initiative now', default: true } : null,
      accepting ? { key: 'item_type_id', label: 'As', type: 'select', options: types.map((t) => ({ value: t.id, label: t.label })) } : null,
      accepting ? { key: 'accountable_id', label: 'Accountable owner', type: 'person', help: 'Empty = you.' } : null,
      { key: 'note', label: accepting ? 'Note' : 'Note (required)', type: 'textarea', required: !accepting },
    ].filter(Boolean),
    values: { create: true, item_type_id: project?.id },
    submitLabel: decision.label,
    onSubmit: (v) => api.post(`/demand/${r.id}/decide`, {
      decision_id: decision.id, note: v.note,
      initiative: accepting && v.create ? { item_type_id: v.item_type_id, accountable_id: v.accountable_id, unit_id: r.unit_id } : null,
    }),
    onDone: (saved) => {
      showToast(saved.work_item ? `Accepted: ${saved.work_item.code} created` : `${r.code}: ${decision.label}`, 'success');
      table.reload();
      if (saved.work_item) window.location.href = `/pages/item.html?id=${saved.work_item.id}`;
    },
  });
}
