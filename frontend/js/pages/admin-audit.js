/** Audit log: every change in the platform, filterable, with a detail view per event. */
import { api } from '../core/api.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { el, formatDateTime, formatValue, humanize } from '../core/utils.js';
import { createDataTable } from '../components/data-table.js';
import { createFilterBar } from '../components/filter-bar.js';
import { openModal } from '../components/modal.js';
import { createBadge } from '../components/badge.js';
import { showError } from '../components/toast.js';

const { content } = await initLayout({ active: 'audit', title: 'Audit log', permission: 'audit.view' });

function changeCell(row) {
  if (row.operation !== 'update') return el('span', { class: 'ct-muted' }, '—');
  return el('span', {},
    el('span', { class: 'ct-diff-old' }, formatValue(row.old_value)), ' → ',
    el('span', { class: 'ct-diff-new' }, formatValue(row.new_value)));
}

function toApiFilters(values) {
  const { from, to, ...rest } = values;
  return {
    ...rest,
    occurred_at__gte: from ? `${from}T00:00:00` : undefined,
    occurred_at__lte: to ? `${to}T23:59:59` : undefined,
  };
}

let filterBar;

function showDetail(row) {
  const kv = (label, value) => [el('dt', {}, label), el('dd', {}, value)];
  const sameAction = el('a', {
    href: '#',
    onClick: (e) => { e.preventDefault(); modal.close(); filterBar.reset(); table.setFilters({ correlation_id: row.correlation_id }); },
  }, 'Show all changes from this action');

  const modal = openModal({
    title: `${humanize(row.operation)} · ${humanize(row.entity_type)} #${row.entity_id ?? '—'}`,
    wide: true,
    body: el('div', {},
      el('dl', { class: 'ct-kv' },
        kv('When', formatDateTime(row.occurred_at)),
        kv('Who', row.actor_name || 'System'),
        kv('Source', humanize(row.source)),
        kv('Field', row.field ? humanize(row.field) : '—'),
        kv('Previous value', el('code', {}, formatValue(row.old_value))),
        kv('New value', el('code', {}, formatValue(row.new_value))),
        kv('Reason', row.reason || '—'),
        kv('Correlation ID', el('code', {}, row.correlation_id))),
      el('p', { style: { marginTop: '16px' } }, sameAction)),
  });
}

const table = createDataTable({
  columns: [
    { key: 'occurred_at', label: 'When', sortable: true, width: '170px', render: (r) => formatDateTime(r.occurred_at) },
    { key: 'actor_name', label: 'Who', render: (r) => r.actor_name || 'System' },
    { key: 'operation', label: 'Action', sortable: true, render: (r) => createBadge(humanize(r.operation)) },
    { key: 'entity_type', label: 'Record', sortable: true, render: (r) => `${humanize(r.entity_type)} #${r.entity_id ?? '—'}` },
    { key: 'field', label: 'Field', render: (r) => (r.field ? humanize(r.field) : '—') },
    { key: 'change', label: 'Change', render: changeCell },
    { key: 'source', label: 'Source', sortable: true, render: (r) => humanize(r.source) },
  ],
  fetchPage: (params) => api.get('/audit-events', params),
  defaultSort: '-occurred_at',
  onRowClick: showDetail,
  emptyState: { title: 'No audit events', message: 'Try changing or clearing the filters.' },
});

filterBar = createFilterBar({
  fields: [
    { key: 'q', type: 'search', placeholder: 'Search person, field, reason…' },
    { key: 'entity_type', type: 'select', label: 'Record types' },
    { key: 'operation', type: 'select', label: 'Actions' },
    { key: 'source', type: 'select', label: 'Sources' },
    { key: 'from', type: 'date', label: 'From date' },
    { key: 'to', type: 'date', label: 'To date' },
  ],
  onChange: (values) => table.setFilters(toApiFilters(values)),
});

content.append(
  pageHeader('Audit log', 'Every change in the platform: who, what, when and why.'),
  el('section', { class: 'ct-card' }, filterBar.element, table.element),
);

api.get('/audit-events/facets').then((facets) => {
  for (const key of ['entity_type', 'operation', 'source']) {
    filterBar.setOptions(key, facets[key].map((v) => ({ value: v, label: humanize(v) })));
  }
}).catch(showError);
