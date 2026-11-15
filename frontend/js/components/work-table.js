/**
 * Work item lists, used by Portfolio, My Work, Schedule, the item page and My Home.
 *
 * const table = createWorkTable({
 *   params: { top_level: 1 },                 // fixed API filters, merged with setFilters()
 *   columns: ['item', 'type', 'priority', 'accountable', 'status', 'progress', 'planned_end'],
 *   pageSize: 25, defaultSort: 'planned_end',
 * });
 * Rows open the item page; overdue rows are tinted. All labels and colours come from lookups.
 */
import { api } from '../core/api.js';
import { el, formatDate } from '../core/utils.js';
import { lookupBadge } from '../core/lookups.js';
import { createBadge } from './badge.js';
import { createDataTable } from './data-table.js';
import { createPersonCell } from './person.js';
import { createProgressBar } from './progress-bar.js';
import { healthBadge } from './health.js';

const APPROVAL = { pending: ['Awaiting approval', 'var(--ct-warning)'], rejected: ['Returned', 'var(--ct-danger)'] };
function approvalNote(item) {
  const a = APPROVAL[item.approval_status];
  return a ? createBadge(a[0], a[1]) : null;
}

export const itemUrl = (item) => `/pages/item.html?id=${item.id}`;

/** The Portfolio, filtered: every number on a dashboard, team or home page opens the list behind it.
 *  The level is always stated (default top level, as the server counts it), so the page never guesses. */
export const portfolioUrl = (filters) => `/pages/work.html?${new URLSearchParams(Object.entries({ level: 'top', ...filters })
  .filter(([, v]) => v !== '' && v !== null && v !== undefined))}`;

/** Code + title (+ parent) linking to the item page. */
export function workTitleCell(item, { showParent = true } = {}) {
  return el('div', { class: 'ct-work-title' },
    el('a', { href: itemUrl(item) }, item.title),
    el('span', { class: 'ct-work-title__code' }, item.code,
      showParent && item.parent ? ` · in ${item.parent.code} ${item.parent.title}` : ''));
}

export function overdueBadge(item) {
  return item.is_overdue ? createBadge('Overdue', 'var(--ct-danger)') : null;
}

export function dateCell(item, key = 'planned_end') {
  return el('span', { class: item.is_overdue && key === 'planned_end' ? 'ct-text-danger' : null }, formatDate(item[key]));
}

const COLUMNS = {
  item: { key: 'title', label: 'Item', sortable: true, render: (i) => workTitleCell(i) },
  item_short: { key: 'title', label: 'Item', sortable: true, render: (i) => workTitleCell(i, { showParent: false }) },
  type: { key: 'item_type_id', label: 'Type', render: (i) => lookupBadge(i.item_type_id) },
  health: { key: 'health', label: 'Health', render: (i) => el('div', { class: 'ct-health-cell', title: i.health?.reason || '' }, healthBadge(i.health),
    i.health?.code && i.health.code !== 'green' ? el('span', { class: 'ct-health-cell__reason' }, i.health.reason) : null) },
  category: { key: 'category_id', label: 'Category', render: (i) => lookupBadge(i.category_id) },
  priority: { key: 'priority_id', label: 'Priority', sortable: true, render: (i) => lookupBadge(i.priority_id) },
  status: { key: 'status_id', label: 'Status', sortable: true, render: (i) => el('div', { class: 'ct-tag-list' }, lookupBadge(i.status_id), approvalNote(i), overdueBadge(i)) },
  accountable: { key: 'accountable', label: 'Accountable', render: (i) => createPersonCell(i.accountable) },
  responsible: { key: 'responsibles', label: 'Responsible', render: (i) => el('div', { class: 'ct-stack', style: { gap: '4px' } }, i.responsibles.map((p) => createPersonCell(p))) },
  unit: { key: 'unit', label: 'Unit', render: (i) => i.unit?.name || '—' },
  progress: { key: 'progress', label: 'Progress', render: (i) => el('div', { class: 'ct-progress-cell' }, createProgressBar(i.progress)) },
  planned_start: { key: 'planned_start', label: 'Start', sortable: true, render: (i) => formatDate(i.planned_start) },
  planned_end: { key: 'planned_end', label: 'Target', sortable: true, render: (i) => dateCell(i) },
  actual: { key: 'actual_end', label: 'Actual', render: (i) => (i.actual_start || i.actual_end ? `${formatDate(i.actual_start)} → ${formatDate(i.actual_end)}` : '—') },
  evidence: { key: 'evidence_url', label: 'Evidence', render: (i) => safeLink(i.evidence_url, 'Open') },
};

export function safeLink(url, text) {
  if (!url || !/^https?:\/\//i.test(url)) return el('span', { class: 'ct-muted' }, '—');
  return el('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, text || url);
}

export function createWorkTable({ params = {}, columns = ['item', 'type', 'priority', 'accountable', 'status', 'progress', 'planned_end'],
  pageSize = 25, defaultSort = 'code', emptyState = {}, extraColumns = [] } = {}) {
  return createDataTable({
    columns: [...columns.map((c) => (typeof c === 'string' ? COLUMNS[c] : c)), ...extraColumns],
    fetchPage: (query) => api.get('/work-items', { ...params, ...query }),
    defaultSort,
    pageSize,
    onRowClick: (row) => { window.location.href = itemUrl(row); },
    rowClass: (row) => (row.is_overdue ? 'is-late' : null),
    emptyState: { title: 'No work items', message: 'Nothing matches these filters.', icon: 'inbox', ...emptyState },
  });
}

/** Total count for a filter (used by KPI tiles), without loading the rows. */
export async function countWork(params) {
  const data = await api.get('/work-items', { ...params, per_page: 1 });
  return data.total;
}
