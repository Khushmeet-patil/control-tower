/** Portfolio: all work the user may see, with filters, health, saved views and a list or board layout.
 *  URL parameters pre-fill the filters (e.g. ?q=portal, ?health=red&level=all, ?view=12). Filters that
 *  have no dropdown (from Action Centre drill-downs, e.g. action_type_id__in) are applied as given and
 *  shown in a notice, so a number you click always matches the list you get. */
import { api } from '../core/api.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { lookupOptions, lookupValue, lookupValues, term } from '../core/lookups.js';
import { el, formatDate } from '../core/utils.js';
import { customColumns, customFilterFields } from '../components/custom-fields.js';
import { createFilterBar } from '../components/filter-bar.js';
import { healthBadge } from '../components/health.js';
import { createKpis } from '../components/kpi.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog } from '../components/modal.js';
import { createAvatar } from '../components/person.js';
import { showError, showToast } from '../components/toast.js';
import { treeOptions } from '../components/tree.js';
import { countWork, createWorkTable, itemUrl } from '../components/work-table.js';

const { user, content } = await initLayout({ active: 'work', title: 'Portfolio', permission: 'work.view' });
const ITEMS = term('work_item', { plural: true, fallback: 'Work items' });
const units = await api.get('/units').then((d) => d.items).catch(() => []);

const FIELDS = [
  { key: 'q', type: 'search', placeholder: 'Search code, title, description…' },
  { key: 'level', type: 'select', label: 'Levels', options: [{ value: 'top', label: 'Top level only' }, { value: 'all', label: 'Every level' }] },
  { key: 'health', type: 'select', label: 'Health', options: [
    ...lookupValues('health').map((v) => ({ value: v.code, label: v.label })), { value: 'red,amber', label: 'Red or Amber' }, { value: 'na', label: 'Not assessed' }] },
  { key: 'mine', type: 'select', label: 'People', options: [
    { value: 'any', label: 'I am involved' }, { value: 'accountable', label: 'I am accountable' },
    { value: 'responsible', label: 'I am responsible' }, { value: 'assigned', label: 'I am assigned' }] },
  { key: 'item_type_id', type: 'select', label: 'Types', options: lookupOptions('item_type') },
  { key: 'status_id', type: 'select', label: 'Statuses', options: lookupOptions('status') },
  { key: 'priority_id', type: 'select', label: 'Priorities', options: lookupOptions('priority') },
  { key: 'category_id', type: 'select', label: 'Categories', options: lookupOptions('category') },
  { key: 'unit_id', type: 'select', label: 'Units', options: treeOptions(units) },
  { key: 'overdue', type: 'select', label: 'Dates', options: [{ value: '1', label: 'Overdue only' }] },
  ...customFilterFields('work_item'),
];
const FIELD_KEYS = new Set(FIELDS.map((f) => f.key));
const EXTRA_LABELS = {
  open: 'open items only', action_type_id: 'action type', action_type_id__in: 'action types', top_level: 'top level',
  involves: 'involving', accountable_id: 'accountable', allocated_to: 'allocated now to', approval_status: 'approval',
  actual_end__gte: 'finished from', actual_end__lte: 'finished until', due_within: 'due within (days)',
};
// Drill-down filters whose value is a person id (shown by name) or plain text, not a lookup value.
const PERSON_KEYS = new Set(['involves', 'accountable_id', 'allocated_to']);
const PLAIN_KEYS = new Set(['approval_status', 'actual_end__gte', 'actual_end__lte', 'due_within', 'open', 'top_level']);
const personNames = {};

// ------------------------------------------------------------------ state
const url = new URLSearchParams(location.search);
let extra = {};          // filters without a dropdown (drill-downs and saved views)
let layout = url.get('layout') === 'board' ? 'board' : 'list';
let views = [];
let currentView = Number(url.get('view')) || null;

const table = createWorkTable({
  columns: ['item', 'type', 'health', 'priority', 'accountable', 'status', 'progress', 'planned_end', 'unit'],
  extraColumns: customColumns('work_item'),
  defaultSort: 'code',
});
const boardSlot = el('div', { class: 'ct-hidden' });
const extraNotice = el('div', { class: 'ct-hidden' });
let applying = false;
const filters = createFilterBar({ fields: FIELDS, onChange: () => { if (!applying) apply(); }, actions: [] });

function toQuery(values) {
  const { level, ...rest } = { ...extra, ...values };
  return { ...rest, top_level: level === 'all' ? '' : '1', include_descendants: rest.unit_id ? '1' : '' };
}

function apply() {
  const values = filters.getValues();
  const query = toQuery(values);
  if (layout === 'board') renderBoard(query); else table.setFilters(query);
  const next = new URLSearchParams(Object.entries({ ...extra, ...values }).filter(([, v]) => v));
  if (currentView) next.set('view', currentView);
  if (layout === 'board') next.set('layout', 'board');
  history.replaceState(null, '', next.toString() ? `?${next}` : location.pathname);
  renderExtra();
  renderViewBar();
}

function setFilters(all, { replace = true } = {}) {
  applying = true;
  if (replace) filters.reset();
  extra = {};
  for (const [k, v] of Object.entries(all)) {
    if (['view', 'layout'].includes(k)) continue;
    if (FIELD_KEYS.has(k)) filters.setValue(k, v); else extra[k] = v;
  }
  if (!all.level) filters.setValue('level', all.q || all.overdue || all.mine || all.health || Object.keys(extra).length ? 'all' : 'top');
  applying = false;
  apply();
}

function renderExtra() {
  const keys = Object.keys(extra).filter((k) => extra[k]);
  extraNotice.className = keys.length ? 'ct-notice' : 'ct-hidden';
  extraNotice.replaceChildren(
    el('span', { class: 'ct-notice__text' }, 'Also filtered by: ', keys.map((k) => {
      if (PERSON_KEYS.has(k)) return `${EXTRA_LABELS[k]} ${personName(extra[k])}`;
      if (PLAIN_KEYS.has(k)) return k === 'open' || k === 'top_level' ? EXTRA_LABELS[k] : `${EXTRA_LABELS[k] || k} ${extra[k]}`;
      const ids = String(extra[k]).split(',').map((v) => lookupValue(v)?.label).filter(Boolean);
      return `${EXTRA_LABELS[k] || k}${ids.length ? ` (${ids.join(', ')})` : ''}`;
    }).join(' · ')),
    el('button', { class: 'ct-btn ct-btn--sm', onClick: () => { extra = {}; apply(); } }, 'Remove'));
}

/** A person's name for the notice; fetched once, then the notice redraws. */
function personName(id) {
  if (personNames[id]) return personNames[id];
  personNames[id] = `person #${id}`;
  api.get(`/people/${id}`).then((p) => { personNames[id] = p.full_name; renderExtra(); }).catch(() => {});
  return personNames[id];
}

// ------------------------------------------------------------------ board
async function renderBoard(query) {
  boardSlot.replaceChildren(el('p', { class: 'ct-muted', style: { padding: '16px' } }, 'Loading…'));
  try {
    const data = await api.get('/work-items', { ...query, per_page: 200, sort: 'planned_end' });
    const statuses = lookupValues('status', { includeRetired: true }).filter((s) => s.is_active || data.items.some((i) => i.status_id === s.id));
    const columns = statuses.map((s) => ({ s, items: data.items.filter((i) => i.status_id === s.id) }))
      .filter((c) => c.items.length || c.s.is_active);
    boardSlot.replaceChildren(...[
      data.total > data.items.length ? el('p', { class: 'ct-muted ct-small', style: { padding: '8px 16px 0' } }, `Showing the first ${data.items.length} of ${data.total}; narrow the filters to see the rest.`) : null,
      el('div', { class: 'ct-board' }, columns.map(({ s, items }) => el('section', { class: 'ct-board__col', 'aria-label': s.label },
        el('div', { class: 'ct-board__head' }, el('span', {}, el('span', { class: 'ct-dot', style: { background: s.color, marginRight: '6px' } }), s.label), el('span', { class: 'ct-muted' }, String(items.length))),
        items.map((i) => el('a', { class: `ct-board__card${i.is_overdue ? ' is-late' : ''}`, href: itemUrl(i) },
          el('div', { class: 'ct-detail-head' }, el('span', { class: 'ct-work-title__code' }, i.code), healthBadge(i.health)),
          el('strong', {}, i.title),
          el('div', { class: 'ct-detail-head ct-small ct-muted' },
            el('span', { class: 'ct-person' }, createAvatar(i.accountable, { small: true }), i.accountable?.full_name || '—'),
            el('span', { class: i.is_overdue ? 'ct-text-danger' : null }, formatDate(i.planned_end))))),
        items.length ? null : el('p', { class: 'ct-muted ct-small', style: { padding: '4px 6px' } }, 'Nothing here'))))].filter(Boolean));
  } catch (err) {
    boardSlot.replaceChildren(createEmptyState({ title: 'Could not load the board', message: err.message }));
    showError(err);
  }
}

function setLayout(next) {
  layout = next;
  table.element.classList.toggle('ct-hidden', layout === 'board');
  boardSlot.classList.toggle('ct-hidden', layout !== 'board');
  apply();
}

// ------------------------------------------------------------------ saved views
const viewSelect = el('select', { class: 'ct-select', 'aria-label': 'Saved views', style: { width: '220px' } });
const viewBar = el('div', { class: 'ct-toolbar' });
const layoutButtons = el('div', { class: 'ct-actions' },
  el('button', { class: 'ct-btn ct-btn--sm', 'data-layout': 'list', onClick: () => setLayout('list') }, 'List'),
  el('button', { class: 'ct-btn ct-btn--sm', 'data-layout': 'board', onClick: () => setLayout('board') }, 'Board'));

async function loadViews() {
  views = (await api.get('/views', { page: 'work' }).catch(() => ({ items: [] }))).items;
  renderViewBar();
}

function renderViewBar() {
  const shared = views.filter((v) => v.is_shared);
  const mine = views.filter((v) => !v.is_shared);
  const option = (v) => el('option', { value: v.id, selected: v.id === currentView }, v.name);
  viewSelect.replaceChildren(el('option', { value: '' }, 'Saved views…'),
    mine.length ? el('optgroup', { label: 'My views' }, mine.map(option)) : null,
    shared.length ? el('optgroup', { label: 'Shared views' }, shared.map(option)) : null);
  const view = views.find((v) => v.id === currentView);
  for (const b of layoutButtons.children) b.classList.toggle('ct-btn--primary', b.dataset.layout === layout);
  viewBar.replaceChildren(...[viewSelect,
    el('button', { class: 'ct-btn ct-btn--sm', onClick: () => saveView(null) }, 'Save as new view'),
    view?.can_edit ? el('button', { class: 'ct-btn ct-btn--sm', onClick: () => saveView(view) }, 'Update view') : null,
    view?.can_edit ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', onClick: () => deleteView(view) }, 'Delete view') : null,
    el('div', { class: 'ct-toolbar__spacer' }), layoutButtons].filter(Boolean));
}

viewSelect.addEventListener('change', () => {
  currentView = Number(viewSelect.value) || null;
  const view = views.find((v) => v.id === currentView);
  if (view) {
    layout = view.layout;
    table.element.classList.toggle('ct-hidden', layout === 'board');
    boardSlot.classList.toggle('ct-hidden', layout !== 'board');
    setFilters(view.filters);
  } else {
    apply();
  }
});

function saveView(existing) {
  const filtersNow = Object.fromEntries(Object.entries({ ...extra, ...filters.getValues() }).filter(([, v]) => v));
  openFormModal({
    title: existing ? `Update “${existing.name}”` : 'Save this view',
    wide: false,
    intro: 'Saves the current filters and layout. A shared view shows each person only the work they may see.',
    fields: [
      { key: 'name', label: 'Name', required: true, full: true },
      can(user, 'views.share') ? { key: 'is_shared', label: 'Shared', type: 'checkbox', checkboxLabel: 'Share with everyone' } : null,
    ].filter(Boolean),
    values: existing || {},
    onSubmit: (v) => (existing
      ? api.patch(`/views/${existing.id}`, { ...v, filters: filtersNow, layout, version: existing.version })
      : api.post('/views', { ...v, page: 'work', filters: filtersNow, layout })),
    onDone: async (saved) => { currentView = saved.id; showToast('View saved', 'success'); await loadViews(); apply(); },
  });
}

async function deleteView(view) {
  if (!await confirmDialog({ title: `Delete “${view.name}”?`, message: view.is_shared ? 'It disappears for everyone.' : 'Only your saved view is removed.', confirmLabel: 'Delete', danger: true })) return;
  try {
    await api.del(`/views/${view.id}`, {});
    currentView = null;
    showToast('View deleted', 'success');
    await loadViews();
    apply();
  } catch (err) { showError(err); }
}

// ------------------------------------------------------------------ KPIs
const kpiSlot = el('div');
async function loadKpis() {
  const [all, red, overdue, accountable] = await Promise.all([
    countWork({ top_level: '1' }), countWork({ health: 'red' }), countWork({ overdue: '1' }), countWork({ mine: 'accountable', open: '1' }),
  ]).catch(() => ['—', '—', '—', '—']);
  const show = (values) => () => { currentView = null; setFilters(values); };
  kpiSlot.replaceChildren(createKpis([
    { value: all, label: `Top-level ${ITEMS.toLowerCase()}`, onClick: show({ level: 'top' }) },
    { value: red, label: 'Red (all levels)', color: red ? 'var(--ct-danger)' : null, onClick: show({ level: 'all', health: 'red' }) },
    { value: overdue, label: 'Overdue (all levels)', color: overdue ? 'var(--ct-danger)' : null, onClick: show({ level: 'all', overdue: '1' }) },
    { value: accountable, label: 'Open, I am accountable', onClick: show({ level: 'all', mine: 'accountable' }) },
  ]));
}

content.append(
  pageHeader('Portfolio', `Every ${term('work_item', { fallback: 'work item' }).toLowerCase()} you can see, with its health. Hover a health badge for the reason; open an item for the full explanation.`),
  kpiSlot,
  el('section', { class: 'ct-card' }, viewBar, filters.element, extraNotice, table.element, boardSlot),
);

await loadViews();
const start = Object.fromEntries([...url.entries()]);
const startView = views.find((v) => v.id === currentView);
if (startView) {
  layout = startView.layout;
  setFilters(startView.filters);
} else {
  currentView = null;
  setFilters(start);
}
table.element.classList.toggle('ct-hidden', layout === 'board');
boardSlot.classList.toggle('ct-hidden', layout !== 'board');
if (layout === 'board') apply();
loadKpis();
