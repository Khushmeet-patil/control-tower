/** Schedule: milestones (or any item type) under one item or across everything visible,
 *  as a timeline with a "today" line and a table of planned vs actual dates. */
import { api } from '../core/api.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { lookupOptions, lookupValue, lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createTimeline } from '../components/timeline.js';
import { showError } from '../components/toast.js';
import { createWorkTable } from '../components/work-table.js';

const { content } = await initLayout({ active: 'schedule', title: 'Schedule', permission: 'work.view' });
const params = new URLSearchParams(location.search);
const milestone = lookupValues('item_type').find((v) => v.code === 'milestone')?.id;

const tops = await api.get('/work-items', { top_level: '1', per_page: 200, sort: 'code' }).then((d) => d.items).catch(() => []);
const scopeSelect = el('select', { class: 'ct-select', 'aria-label': 'Show the schedule of' },
  el('option', { value: '' }, 'Everything I can see'),
  tops.map((t) => el('option', { value: t.id }, `${t.code} ${t.title}`)));
const typeSelect = el('select', { class: 'ct-select', 'aria-label': 'Item type' },
  el('option', { value: '' }, 'All types'),
  lookupOptions('item_type').map((o) => el('option', { value: o.value }, o.label)));
scopeSelect.value = params.get('under') || '';
typeSelect.value = params.get('type') ?? (milestone ? String(milestone) : '');

const timelineCard = el('section', { class: 'ct-card' });
const tableCard = el('section', { class: 'ct-card' });
content.append(
  pageHeader('Schedule', 'Planned dates against today. Overdue items are red; open one to update it.'),
  el('section', { class: 'ct-card' }, el('div', { class: 'ct-toolbar', style: { borderBottom: 0 } }, scopeSelect, typeSelect)),
  timelineCard, tableCard);

async function refresh() {
  const query = { ancestor_id: scopeSelect.value, item_type_id: typeSelect.value };
  const next = new URLSearchParams({ under: scopeSelect.value, type: typeSelect.value });
  history.replaceState(null, '', `?${next}`);
  try {
    const data = await api.get('/work-items', { ...query, per_page: 200, sort: 'planned_end' });
    const timeline = createTimeline(data.items, {
      label: (i) => `${i.code} ${i.title}`,
      color: (i) => (i.is_overdue ? 'var(--ct-danger)' : lookupValue(i.status_id)?.color),
      onClick: (i) => { location.href = `/pages/item.html?id=${i.id}`; },
    });
    timelineCard.replaceChildren(el('div', { class: 'ct-card__body' },
      timeline || el('p', { class: 'ct-muted' }, 'Nothing with planned dates to draw yet.'),
      data.total > data.items.length ? el('p', { class: 'ct-muted ct-small', style: { marginTop: '8px' } }, `Showing the first ${data.items.length} of ${data.total}.`) : null));
  } catch (err) { showError(err); }
  tableCard.replaceChildren(createWorkTable({
    params: query,
    columns: ['item', 'status', 'responsible', 'planned_start', 'planned_end', 'actual', 'evidence'],
    defaultSort: 'planned_end',
    emptyState: { title: 'Nothing scheduled', message: 'Try another item or type.' },
  }).element);
}

scopeSelect.addEventListener('change', refresh);
typeSelect.addEventListener('change', refresh);
refresh();
