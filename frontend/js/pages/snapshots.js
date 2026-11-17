/** Snapshots & trends (/pages/snapshots.html): stored figures over time.
 *  - Trend: open, overdue, red and amber work and weighted progress, from each snapshot.
 *  - Against the baseline: top-level (or all) work then and now: slipped dates, progress, health.
 *  - Snapshots: take one (snapshots.manage), approve and choose the baseline (snapshots.approve),
 *    export to Excel. Every figure is limited to the work you may see. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { lookupValues } from '../core/lookups.js';
import { el, formatDate } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createLineChart } from '../components/chart.js';
import { createDataTable } from '../components/data-table.js';
import { createEmptyState } from '../components/empty-state.js';
import { createFilterBar } from '../components/filter-bar.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog } from '../components/modal.js';
import { healthBadgeFromCode } from '../components/health.js';
import { showError, showToast } from '../components/toast.js';

const { user, content } = await initLayout({ active: 'snapshots', title: 'Snapshots & trends', permission: 'work.view' });

const scope = createFilterBar({
  fields: [{ key: 'level', type: 'select', label: 'Top-level work', options: [{ value: 'all', label: 'All work (every level)' }] }],
  onChange: () => { renderTrend(); renderCompare(); },
});
const query = () => ({ level: scope.getValues().level || 'top' });
const healthColor = (code, fallback) => lookupValues('health', { includeRetired: true }).find((v) => v.code === code)?.color || fallback;
const download = (path) => { window.location.href = `/api/v1${path}?${new URLSearchParams(query())}`; };

const trendSlot = el('div', {}, el('p', { class: 'ct-muted' }, 'Loading…'));
const compareSlot = el('div', {}, el('p', { class: 'ct-muted' }, 'Loading…'));

const table = createDataTable({
  columns: [
    { key: 'label', label: 'Snapshot', sortable: true, render: (s) => el('div', { class: 'ct-work-title' }, el('strong', {}, s.label),
      el('span', { class: 'ct-work-title__code' }, s.notes || (s.kind === 'weekly' ? `Weekly (${s.period})` : 'On demand'))) },
    { key: 'as_of', label: 'As of', sortable: true, render: (s) => el('div', {}, formatDate(s.as_of),
      el('div', { class: 'ct-muted ct-small' }, s.taken_by ? `by ${s.taken_by.full_name}` : 'scheduled')) },
    { key: 'status', label: 'Status', sortable: true, render: (s) => el('div', { class: 'ct-tag-list' },
      s.status === 'approved' ? createBadge('Approved', 'var(--ct-success)') : createBadge('Draft', 'var(--ct-border-strong)'),
      s.is_baseline ? createBadge('Baseline', 'var(--ct-accent)') : null,
      s.used_by ? el('span', { class: 'ct-muted ct-small' }, `used by ${s.used_by} presentation(s)`) : null) },
    { key: 'item_count', label: 'Items', render: (s) => s.item_count },
    { key: 'actions', label: '', render: (s) => el('div', { class: 'ct-tag-list' },
      s.permissions.can_approve ? button('Approve', () => approve(s), 'primary') : null,
      s.permissions.can_set_baseline ? button('Make baseline', () => makeBaseline(s)) : null,
      button('Excel', () => download(`/snapshots/${s.id}/export.xlsx`)),
      s.permissions.can_edit ? button('Edit', () => edit(s)) : null,
      s.permissions.can_delete ? button('Delete', () => remove(s), 'danger') : null) },
  ],
  fetchPage: (q) => api.get('/snapshots', q),
  defaultSort: '-as_of',
  emptyState: { title: 'No snapshots yet', message: 'Take one now, or schedule the weekly snapshot.', icon: 'versions' },
});

function button(label, onClick, variant) {
  return el('button', { class: `ct-btn ct-btn--sm${variant ? ` ct-btn--${variant}` : ''}`, onClick: (e) => { e.stopPropagation(); onClick(); } }, label);
}

content.append(
  pageHeader('Snapshots & trends', 'Figures stored as they were, so earlier reviews never change. Each snapshot shows only the work you may see.', [
    el('button', { class: 'ct-btn', onClick: () => download('/exports/work-items.xlsx') },
      icon('upload', { size: 16 }), 'Export live work'),
    can(user, 'snapshots.manage') ? el('button', { class: 'ct-btn ct-btn--primary', onClick: take }, icon('plus', { size: 16 }), 'Take snapshot') : null,
  ].filter(Boolean)),
  scope.element,
  el('div', { class: 'ct-grid-2' },
    el('section', { class: 'ct-card' }, el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, 'Trend')),
      el('div', { class: 'ct-card__body' }, trendSlot)),
    el('section', { class: 'ct-card' }, el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, 'Against the baseline')),
      el('div', { class: 'ct-card__body' }, compareSlot))),
  el('section', { class: 'ct-card', style: { marginTop: 'var(--ct-space-4)' } }, table.element));

async function renderTrend() {
  let data;
  try { data = await api.get('/snapshots/trend', query()); } catch (err) { trendSlot.replaceChildren(createEmptyState({ title: 'Could not load the trend', message: err.message })); return; }
  const pts = data.points;
  if (pts.length < 1) { trendSlot.replaceChildren(createEmptyState({ title: 'No snapshots yet', message: 'The trend appears once snapshots are taken.', icon: 'chart' })); return; }
  const labels = pts.map((p) => `${formatDate(p.as_of)}${p.is_baseline ? ' (baseline)' : ''}`);
  trendSlot.replaceChildren(
    createLineChart({ labels, series: [
      { label: 'Open', values: pts.map((p) => p.open), color: 'var(--ct-accent)' },
      { label: 'Overdue', values: pts.map((p) => p.overdue), color: 'var(--ct-text-muted)' },
      { label: 'Red', values: pts.map((p) => p.red), color: healthColor('red', 'var(--ct-danger)') },
      { label: 'Amber', values: pts.map((p) => p.amber), color: healthColor('amber', 'var(--ct-warning)') },
    ] }),
    el('h4', { class: 'ct-section-title' }, 'Weighted progress %'),
    createLineChart({ labels, height: 160, yMax: 100, series: [{ label: 'Progress %', values: pts.map((p) => p.progress), color: 'var(--ct-success)' }] }));
}

const CHANGE = { added: 'New since', removed: 'Gone since', changed: 'Changed', same: 'Unchanged' };

async function renderCompare() {
  let data;
  try { data = await api.get('/snapshots/compare', { ...query(), snapshot: 'baseline' }); } catch (err) {
    compareSlot.replaceChildren(createEmptyState({ title: err.status === 404 ? 'No baseline yet' : 'Could not compare', icon: 'flag',
      message: err.status === 404 ? 'Approve a snapshot and make it the baseline to see what has moved since.' : err.message }));
    return;
  }
  const s = data.summary;
  const moved = data.items.filter((i) => i.change !== 'same');
  compareSlot.replaceChildren(
    el('p', { class: 'ct-small ct-muted' }, `Baseline “${data.snapshot.label}”, ${formatDate(data.snapshot.as_of)}: `,
      el('strong', {}, `${s.slipped} slipped`), `, ${s.pulled_in} pulled in, ${s.added} new, ${s.removed} gone.`),
    moved.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
      el('thead', {}, el('tr', {}, ['Item', 'Finish (then → now)', 'Progress', 'Health', ''].map((h) => el('th', {}, h)))),
      el('tbody', {}, moved.map((i) => el('tr', { class: (i.slip_days || 0) > 0 ? 'is-late' : null },
        el('td', {}, i.now ? el('a', { href: `/pages/item.html?id=${i.id}` }, `${i.code} ${i.title}`) : `${i.code} ${i.title}`),
        el('td', {}, `${formatDate(i.was?.planned_end) || '—'} → ${formatDate(i.now?.planned_end) || '—'}`,
          i.slip_days ? el('div', { class: 'ct-small', style: { color: i.slip_days > 0 ? 'var(--ct-danger)' : 'var(--ct-success)' } },
            `${i.slip_days > 0 ? '+' : ''}${i.slip_days} days`) : null),
        el('td', {}, i.was && i.now ? `${i.was.progress}% → ${i.now.progress}%` : '—'),
        el('td', {}, el('div', { class: 'ct-tag-list' }, i.was ? healthBadgeFromCode(i.was.health) : null, i.was && i.now ? '→' : null,
          i.now ? healthBadgeFromCode(i.now.health) : null)),
        el('td', { class: 'ct-muted ct-small' }, i.change === 'changed' ? '' : CHANGE[i.change]))))))
      : el('p', { class: 'ct-muted' }, 'Nothing has moved since the baseline.'));
}

function take() {
  openFormModal({
    title: 'Take a snapshot', wide: false,
    intro: 'Stores the figures of all work as they are now. They never change afterwards; approve it to use it in a review pack.',
    fields: [{ key: 'label', label: 'Label', placeholder: 'e.g. Month-end review', full: true }, { key: 'notes', label: 'Notes', type: 'textarea' }],
    submitLabel: 'Take snapshot',
    onSubmit: (v) => api.post('/snapshots', v),
    onDone: (s) => { showToast(`“${s.label}” taken (${s.item_count} items)`, 'success'); refresh(); },
  });
}

function edit(s) {
  openFormModal({
    title: `Edit ${s.label}`, wide: false, intro: 'Only the label and notes can change; the figures never do.',
    fields: [{ key: 'label', label: 'Label', required: true, full: true }, { key: 'notes', label: 'Notes', type: 'textarea' },
      { key: 'reason', label: 'Reason for change', full: true }],
    values: s,
    onSubmit: (v) => api.patch(`/snapshots/${s.id}`, { ...v, version: s.version }),
    onDone: () => { showToast('Snapshot saved', 'success'); table.reload(); },
  });
}

async function approve(s) {
  if (!await confirmDialog({ title: `Approve ${s.label}?`, message: 'Approved snapshots can be used by published review packs and are kept for the record.', confirmLabel: 'Approve' })) return;
  try { await api.post(`/snapshots/${s.id}/approve`, {}); showToast('Approved', 'success'); refresh(); } catch (err) { showError(err); }
}

async function makeBaseline(s) {
  if (!await confirmDialog({ title: `Make ${s.label} the baseline?`, message: 'Work is compared against the baseline from now on. The previous baseline stays as an approved snapshot.', confirmLabel: 'Make baseline' })) return;
  try { await api.post(`/snapshots/${s.id}/baseline`, {}); showToast('Baseline set', 'success'); refresh(); } catch (err) { showError(err); }
}

async function remove(s) {
  if (!await confirmDialog({ title: `Delete ${s.label}?`, message: 'Draft snapshots that nothing uses can be deleted. The audit log keeps a record.', confirmLabel: 'Delete', danger: true })) return;
  try { await api.del(`/snapshots/${s.id}`, { reason: 'Not needed' }); showToast('Deleted', 'success'); refresh(); } catch (err) { showError(err); }
}

function refresh() { table.reload(); renderTrend(); renderCompare(); }

renderTrend();
renderCompare();
