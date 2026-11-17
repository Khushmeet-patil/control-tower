/** Actions & decisions (/pages/actions.html): the prototype's Actions & Decisions screen.
 *  Every action item you can see (decisions, approvals, blockers, commitments, actions) at any level,
 *  with counts that open the same list: open blockers, decisions pending, overdue, critical. */
import { api } from '../core/api.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge, lookupOptions, lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createFilterBar } from '../components/filter-bar.js';
import { createKpis } from '../components/kpi.js';
import { createWorkTable, countWork } from '../components/work-table.js';
import { treeOptions } from '../components/tree.js';

const { user, content } = await initLayout({ active: 'actions', title: 'Actions & decisions', permission: 'work.view' });
const actionType = lookupValues('item_type').find((t) => t.code === 'action');
const code = (list, c) => lookupValues(list).find((v) => v.code === c)?.id;
const units = await api.get('/units').then((d) => d.items).catch(() => []);
const base = actionType ? { item_type_id: actionType.id } : {};
const url = new URLSearchParams(location.search);

const table = createWorkTable({
  params: base,
  columns: ['item', 'accountable', 'status', 'planned_end'],
  defaultSort: 'planned_end',
  extraColumns: [
    { key: 'action_type_id', label: 'Kind', render: (i) => (i.action_type_id ? lookupBadge(i.action_type_id) : '—') },
    { key: 'severity_id', label: 'Severity', render: (i) => (i.severity_id ? lookupBadge(i.severity_id) : '—') },
  ],
  emptyState: { title: 'No actions', message: 'Actions, decisions and blockers raised on work appear here.' },
});

const filters = createFilterBar({
  fields: [
    { key: 'q', type: 'search', placeholder: 'Search actions…' },
    { key: 'action_type_id', type: 'select', label: 'Every kind', options: lookupOptions('action_type') },
    { key: 'severity_id', type: 'select', label: 'Any severity', options: lookupOptions('severity') },
    { key: 'status_id', type: 'select', label: 'Any status', options: lookupOptions('status') },
    { key: 'open', type: 'select', label: 'Open and closed', options: [{ value: '1', label: 'Open only' }] },
    { key: 'overdue', type: 'select', label: 'Any date', options: [{ value: '1', label: 'Overdue' }] },
    { key: 'unit_id', type: 'select', label: 'Every unit', options: treeOptions(units) },
    { key: 'mine', type: 'select', label: 'Everyone\'s', options: [{ value: 'any', label: 'Mine' }, { value: 'accountable', label: 'I am accountable' }] },
  ],
  onChange: (v) => table.setFilters(toQuery(v)),
});
for (const k of ['action_type_id', 'severity_id', 'status_id', 'open', 'overdue', 'unit_id', 'mine']) if (url.get(k)) filters.setValue(k, url.get(k));
if (!url.toString()) filters.setValue('open', '1');

function toQuery(v) {
  const q = { ...base, ...v };
  if (q.unit_id) q.include_descendants = '1';
  return q;
}

const tiles = [
  { label: 'Open blockers', filters: { action_type_id: code('action_type', 'blocker'), open: '1' }, color: 'var(--ct-danger)' },
  { label: 'Decisions pending', filters: { action_type_id: code('action_type', 'decision'), open: '1' } },
  { label: 'Approvals to get', filters: { action_type_id: code('action_type', 'approval'), open: '1' } },
  { label: 'Overdue actions', filters: { overdue: '1' }, color: 'var(--ct-danger)' },
  { label: 'Critical', filters: { severity_id: code('severity', 'critical'), open: '1' }, color: 'var(--ct-warning)' },
].map((t) => ({ ...t, filters: Object.fromEntries(Object.entries(t.filters).filter(([, v]) => v)) }));
const counts = await Promise.all(tiles.map((t) => countWork(toQuery(t.filters)).catch(() => null)));
const kpis = createKpis(tiles.map((t, n) => ({
  value: counts[n], label: t.label, color: counts[n] ? t.color : null,
  onClick: () => {
    filters.reset();
    for (const [k, v] of Object.entries(t.filters)) filters.setValue(k, String(v));
  },
})));

table.setFilters(toQuery(filters.getValues()));
content.append(
  pageHeader('Actions & decisions', 'Decisions, approvals, blockers and commitments raised on work, with who owns them and when they are due.',
    can(user, 'work.create') ? [el('button', { class: 'ct-btn ct-btn--primary', type: 'button', onClick: async () => {
      const { openWorkItemEditor } = await import('../components/work-item-form.js');
      openWorkItemEditor({ itemTypeId: actionType?.id, onDone: () => table.reload() });
    } }, 'New action')] : []),
  kpis,
  filters.element,
  el('section', { class: 'ct-card' }, table.element));
