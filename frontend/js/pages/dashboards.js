/** Dashboards (/pages/dashboards.html?id=…): pick a dashboard, see its widgets, and build your own.
 *  Widgets show only the work the viewer may see; every number opens the list behind it.
 *  Personal dashboards for everyone; sharing needs `dashboards.share`. */
import { api } from '../core/api.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { icon } from '../core/icons.js';
import { lookupOptions, lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createWidget } from '../components/dashboard-widget.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';

const { user, content } = await initLayout({ active: 'dashboards', title: 'Dashboards', permission: 'work.view' });

let meta = { items: [], widget_types: {}, group_by: {}, charts: {} };
let views = [];
let current = null; // the open dashboard (with widgets)
let editing = false;

const opts = (obj) => Object.entries(obj).map(([value, label]) => ({ value, label }));
const setUrl = (id) => history.replaceState(null, '', id ? `?id=${id}` : location.pathname);

async function load(selectId) {
  try {
    [meta, views] = await Promise.all([api.get('/dashboards'), api.get('/views', { page: 'work' }).then((d) => d.items)]);
  } catch (err) { showError(err); return; }
  const id = selectId || Number(new URLSearchParams(location.search).get('id')) || meta.items[0]?.id;
  if (!id || !meta.items.some((d) => d.id === id)) { current = null; render(); return; }
  await open(id);
}

async function open(id) {
  try { current = await api.get(`/dashboards/${id}`); } catch (err) { showError(err); return; }
  setUrl(id);
  render();
  const data = await api.get(`/dashboards/${id}/data`).catch((err) => { showError(err); return { widgets: {} }; });
  if (current?.id === id) render(data.widgets);
}

// ------------------------------------------------------------------ screen
function render(data = null) {
  const picker = el('select', { class: 'ct-select', 'aria-label': 'Dashboard', style: { minWidth: '220px' },
    onChange: (e) => { editing = false; open(Number(e.target.value)); } },
  meta.items.map((d) => el('option', { value: d.id, selected: d.id === current?.id }, `${d.name}${d.is_shared ? ' (shared)' : ''}`)));
  const actions = [
    meta.items.length ? picker : null,
    current?.can_edit ? el('button', { class: `ct-btn${editing ? ' ct-btn--primary' : ''}`, onClick: () => { editing = !editing; render(data); } },
      icon(editing ? 'check' : 'edit', { size: 16 }), editing ? 'Done' : 'Edit') : null,
    el('button', { class: 'ct-btn ct-btn--primary', onClick: () => editDashboard(null) }, icon('plus', { size: 16 }), 'New dashboard'),
  ].filter(Boolean);
  const header = pageHeader(current?.name || 'Dashboards',
    current ? (current.description || (current.is_shared ? `Shared by ${current.owner?.full_name || 'an administrator'}` : 'Your personal dashboard'))
      : 'Build pages of numbers, charts and lists from your saved filters.', actions);

  if (!current) {
    content.replaceChildren(header, createEmptyState({ title: 'No dashboards yet', icon: 'chart',
      message: 'Create one and add widgets: numbers, charts, progress, timelines and lists, each built on a filter or a saved view.',
      action: el('button', { class: 'ct-btn ct-btn--primary', onClick: () => editDashboard(null) }, 'New dashboard') }));
    return;
  }

  const toolbar = editing ? el('div', { class: 'ct-notice ct-notice--quiet' },
    el('span', { class: 'ct-notice__text' }, 'Editing: add, change, move or remove widgets. Changes are saved straight away.'),
    el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => editWidget(null) }, icon('plus', { size: 14 }), 'Add widget'),
    el('button', { class: 'ct-btn ct-btn--sm', onClick: () => editDashboard(current) }, 'Name & sharing'),
    el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', onClick: removeDashboard }, 'Delete dashboard')) : null;

  const widgets = current.widgets.length ? el('div', { class: 'ct-widgets' }, current.widgets.map((w, i) => createWidget(w, data ? (data[w.id] || { error: 'No data' }) : null, {
    actions: editing ? [
      el('button', { class: 'ct-btn ct-btn--ghost ct-btn--sm', title: 'Move earlier', 'aria-label': 'Move earlier', disabled: i === 0, onClick: () => move(i, -1) }, icon('chevronLeft', { size: 14 })),
      el('button', { class: 'ct-btn ct-btn--ghost ct-btn--sm', title: 'Move later', 'aria-label': 'Move later', disabled: i === current.widgets.length - 1, onClick: () => move(i, 1) }, icon('chevronRight', { size: 14 })),
      el('button', { class: 'ct-btn ct-btn--ghost ct-btn--sm', title: 'Change', 'aria-label': 'Change widget', onClick: () => editWidget(i) }, icon('edit', { size: 14 })),
      el('button', { class: 'ct-btn ct-btn--ghost ct-btn--sm', title: 'Remove', 'aria-label': 'Remove widget', onClick: () => removeWidget(i) }, icon('trash', { size: 14 })),
    ] : [],
  })))
    : createEmptyState({ title: 'No widgets yet', icon: 'chart', message: current.can_edit ? 'Choose Edit, then Add widget.' : 'The owner has not added any widgets yet.' });

  content.replaceChildren(...[header, toolbar, widgets].filter(Boolean));
}

// ------------------------------------------------------------------ saving
async function saveWidgets(widgets, reason) {
  try {
    current = await api.patch(`/dashboards/${current.id}`, { widgets, version: current.version, reason });
    await open(current.id);
  } catch (err) { showError(err); throw err; }
}

function move(i, step) {
  const w = [...current.widgets];
  [w[i], w[i + step]] = [w[i + step], w[i]];
  saveWidgets(w, 'Widget moved').catch(() => {});
}

async function removeWidget(i) {
  if (!await confirmDialog({ title: 'Remove widget?', message: `“${current.widgets[i].title}” will be removed from this dashboard.`, confirmLabel: 'Remove', danger: true })) return;
  saveWidgets(current.widgets.filter((_, n) => n !== i), 'Widget removed').catch(() => {});
}

async function removeDashboard() {
  if (!await confirmDialog({ title: 'Delete dashboard?', message: `“${current.name}” and its widgets will be deleted. Saved views are not affected.`, confirmLabel: 'Delete', danger: true })) return;
  try {
    await api.del(`/dashboards/${current.id}`, { reason: 'Dashboard deleted' });
    showToast('Dashboard deleted', 'success');
    editing = false;
    setUrl(null);
    load();
  } catch (err) { showError(err); }
}

function editDashboard(dashboard) {
  openFormModal({
    title: dashboard ? 'Dashboard name and sharing' : 'New dashboard',
    wide: false,
    fields: [
      { key: 'name', label: 'Name', type: 'text', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      can(user, 'dashboards.share') ? { key: 'is_shared', label: 'Shared with everyone (each person sees only their own work in it)', type: 'checkbox' } : null,
    ].filter(Boolean),
    values: dashboard || {},
    submitLabel: dashboard ? 'Save' : 'Create',
    onSubmit: (v) => (dashboard
      ? api.patch(`/dashboards/${dashboard.id}`, { ...v, version: dashboard.version })
      : api.post('/dashboards', { ...v, widgets: [] })),
    onDone: (saved) => { editing = true; load(saved.id); },
  });
}

// ------------------------------------------------------------------ widget editor
const FILTER_KEYS = ['level', 'item_type_id', 'status_id', 'priority_id', 'category_id', 'health', 'mine', 'dates'];
const DATES = { open: { open: '1' }, overdue: { overdue: '1' }, due14: { due_within: '14' } };

function toForm(w) {
  const f = w?.filters || {};
  const dates = f.overdue ? 'overdue' : f.due_within ? 'due14' : f.open ? 'open' : null;
  return { title: w?.title, type: w?.type || 'kpi', view_id: w?.view_id || null, group_by: w?.group_by || 'status_id',
    chart: w?.chart || 'bar', limit: w?.limit || null, width: String(w?.width || 1), ...f, level: f.level || 'all', dates };
}

function fromForm(v, old) {
  const filters = { ...(old?.view_id ? {} : old?.filters || {}) };
  for (const k of FILTER_KEYS) delete filters[k];
  delete filters.open; delete filters.overdue; delete filters.due_within;
  for (const k of FILTER_KEYS.filter((x) => x !== 'dates')) if (v[k] !== null && v[k] !== undefined && v[k] !== '') filters[k] = String(v[k]);
  Object.assign(filters, DATES[v.dates] || {});
  return { id: old?.id, type: v.type, title: v.title, view_id: v.view_id || null, filters: v.view_id ? {} : filters,
    group_by: v.group_by, chart: v.chart, limit: v.limit, width: Number(v.width) };
}

function editWidget(index) {
  const old = index === null ? null : current.widgets[index];
  const lookupFilter = (key, list, label) => ({ key, label, type: 'select', options: lookupOptions(list) });
  openFormModal({
    title: old ? 'Change widget' : 'Add widget',
    intro: 'Choose what to show and which work it covers: a saved view, or the filters below. Everyone sees only the work they may open.',
    fields: [
      { key: 'title', label: 'Title', type: 'text', required: true },
      { key: 'type', label: 'Widget', type: 'select', required: true, options: opts(meta.widget_types) },
      { key: 'view_id', label: 'Saved view (overrides the filters below)', type: 'select', full: true,
        options: views.map((v) => ({ value: v.id, label: `${v.name}${v.is_shared ? ' (shared)' : ''}` })) },
      { key: 'level', label: 'Levels', type: 'select', options: [{ value: 'top', label: 'Top level only' }, { value: 'all', label: 'Every level' }] },
      lookupFilter('item_type_id', 'item_type', 'Item type'),
      lookupFilter('status_id', 'status', 'Status'),
      lookupFilter('priority_id', 'priority', 'Priority'),
      lookupFilter('category_id', 'category', 'Category'),
      { key: 'health', label: 'Health', type: 'select', options: [...lookupValues('health').map((h) => ({ value: h.code, label: h.label })), { value: 'red,amber', label: 'Red or Amber' }] },
      { key: 'mine', label: 'People', type: 'select', options: [{ value: 'any', label: 'I am involved' }, { value: 'accountable', label: 'I am accountable' }, { value: 'responsible', label: 'I am responsible' }, { value: 'assigned', label: 'I am assigned' }] },
      { key: 'dates', label: 'Dates', type: 'select', options: [{ value: 'open', label: 'Open items only' }, { value: 'overdue', label: 'Overdue' }, { value: 'due14', label: 'Due in the next 14 days' }] },
      { key: 'group_by', label: 'Chart groups by', type: 'select', options: opts(meta.group_by), help: 'Status charts only' },
      { key: 'chart', label: 'Chart style', type: 'select', options: opts(meta.charts), help: 'Status charts only' },
      { key: 'limit', label: 'Rows shown', type: 'number', help: 'Tables, progress and timelines' },
      { key: 'width', label: 'Width', type: 'select', required: true, options: [{ value: '1', label: 'Normal' }, { value: '2', label: 'Wide' }] },
    ],
    values: toForm(old),
    submitLabel: old ? 'Save' : 'Add',
    onSubmit: (v) => {
      const widget = fromForm(v, old);
      const widgets = old ? current.widgets.map((w, i) => (i === index ? widget : w)) : [...current.widgets, widget];
      return api.patch(`/dashboards/${current.id}`, { widgets, version: current.version, reason: old ? 'Widget changed' : 'Widget added' });
    },
    onDone: (saved) => { current = saved; open(saved.id); },
  });
}

load();
