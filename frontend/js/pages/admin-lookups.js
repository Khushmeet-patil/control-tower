/** Lookups & colours: the lists behind every coloured value (status, priority, item type, …). Edits are a draft. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { clear, el } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { createSettingsBanner } from '../components/settings-banner.js';
import { showError, showToast } from '../components/toast.js';

const { content } = await initLayout({ active: 'lookups', title: 'Lookups & colours', permission: 'settings.manage' });

let lists = [];
let selectedId = Number(new URLSearchParams(location.search).get('list')) || null;
let showRetired = false;

const banner = createSettingsBanner({ onChange: load });
const listNav = el('ul', { class: 'ct-list', role: 'listbox', 'aria-label': 'Lists' });
const detail = el('section', { class: 'ct-card' });

content.append(
  pageHeader('Lookups & colours',
    'The values people pick from, with the colour each one shows. Retired values disappear from pickers but stay visible on old records.',
    [el('button', { class: 'ct-btn ct-btn--primary', onClick: () => editList(null) }, icon('plus', { size: 16 }), 'New list')]),
  banner.element,
  el('div', { class: 'ct-split' },
    el('section', { class: 'ct-card' },
      el('div', { class: 'ct-card__header' }, el('h3', {}, 'Lists'), el('span', { class: 'ct-muted ct-small' }, 'Values')),
      listNav),
    detail),
);

async function load() {
  try {
    lists = (await api.get('/lookup-types')).items;
    if (!lists.some((l) => l.id === selectedId)) selectedId = lists[0]?.id ?? null;
    renderNav();
    renderDetail();
  } catch (err) { showError(err); }
  banner.refresh();
}

function renderNav() {
  clear(listNav);
  for (const l of lists) {
    const active = l.values.filter((v) => v.is_active).length;
    listNav.append(el('li', {}, el('button', {
      class: `ct-list__item${l.id === selectedId ? ' is-selected' : ''}`, role: 'option', 'aria-selected': String(l.id === selectedId),
      onClick: () => { selectedId = l.id; history.replaceState(null, '', `?list=${l.id}`); renderNav(); renderDetail(); },
    }, el('span', { class: 'ct-list__label' }, l.name, l.is_active ? '' : ' (retired)'), el('span', { class: 'ct-list__meta' }, String(active)))));
  }
}

function renderDetail() {
  clear(detail);
  const list = lists.find((l) => l.id === selectedId);
  if (!list) {
    detail.append(createEmptyState({ title: 'No lists yet', message: 'Create a list to start.', icon: 'list' }));
    return;
  }
  const values = list.values.filter((v) => showRetired || v.is_active);
  const retiredCount = list.values.length - list.values.filter((v) => v.is_active).length;
  const toggle = el('input', { type: 'checkbox', checked: showRetired, onChange: (e) => { showRetired = e.target.checked; renderDetail(); } });

  detail.append(
    el('div', { class: 'ct-card__body ct-stack' },
      el('div', { class: 'ct-detail-head' },
        el('div', {},
          el('div', { class: 'ct-detail-head__title' }, el('h2', {}, list.name),
            list.is_system ? createBadge('Built-in') : null, list.is_active ? null : createBadge('Retired')),
          el('div', { class: 'ct-muted ct-small' }, `Code: ${list.code}`, list.description ? ` · ${list.description}` : '')),
        el('div', { class: 'ct-actions' },
          el('button', { class: 'ct-btn ct-btn--sm', onClick: () => editList(list) }, icon('edit', { size: 16 }), 'Edit list'),
          el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => editValue(list, null), disabled: !list.is_active }, icon('plus', { size: 16 }), 'Add value')))),
    el('div', { class: 'ct-toolbar' },
      el('span', { class: 'ct-muted ct-small' }, 'Order sets how values appear in pickers and reports.'),
      el('div', { class: 'ct-toolbar__spacer' }),
      retiredCount ? el('label', { class: 'ct-checkbox' }, toggle, `Show retired (${retiredCount})`) : null),
    el('div', { class: 'ct-table-wrap' },
      el('table', { class: 'ct-table' },
        el('thead', {}, el('tr', {}, ['Value', 'Code', 'Colour', 'Order', 'Status', ''].map((h) => el('th', { scope: 'col' }, h)))),
        el('tbody', {}, values.length ? values.map((v) => el('tr', {
          class: `is-clickable${v.is_active ? '' : ' ct-row-retired'}`, tabindex: '0',
          onClick: () => editValue(list, v), onKeydown: (e) => { if (e.key === 'Enter') editValue(list, v); },
        },
          el('td', {}, createBadge(v.label, v.color), ' ', v.is_default ? el('span', { class: 'ct-muted ct-small' }, 'Default') : null),
          el('td', { class: 'ct-small' }, v.code),
          el('td', { class: 'ct-small', style: { fontFamily: 'var(--ct-font-mono)' } }, v.color),
          el('td', {}, String(v.sort_order)),
          el('td', {}, v.is_active ? 'Active' : 'Retired', v.is_system ? el('span', { class: 'ct-muted ct-small' }, ' · built-in') : null),
          el('td', { style: { textAlign: 'right' } }, icon('edit', { size: 16 }))))
          : el('tr', {}, el('td', { colspan: 6 }, createEmptyState({ title: 'No values', message: 'Add the first value to this list.' })))))));
}

function editList(list) {
  openFormModal({
    title: list ? `Edit list · ${list.name}` : 'New list',
    fields: [
      { key: 'name', label: 'Name', required: true },
      list ? null : { key: 'code', label: 'Code', required: true, help: 'Lowercase letters, numbers and _ (e.g. business_impact). Cannot change later.' },
      { key: 'sort_order', label: 'Order', type: 'number' },
      list && !list.is_system ? { key: 'is_active', label: 'Active', type: 'checkbox', checkboxLabel: 'Active (retired lists cannot be used by new fields)' } : null,
      { key: 'description', label: 'Description', type: 'textarea' },
      list ? { key: 'reason', label: 'Reason for change', help: 'Saved in the audit log.', full: true } : null,
    ].filter(Boolean),
    values: list || { sort_order: (lists.length + 1) * 10 },
    submitLabel: list ? 'Save list' : 'Create list',
    onSubmit: (v) => (list ? api.patch(`/lookup-types/${list.id}`, { ...v, version: list.version }) : api.post('/lookup-types', v)),
    onDone: (saved) => { selectedId = saved.id; showToast(list ? 'List saved (draft)' : 'List created (draft)', 'success'); load(); },
  });
}

function editValue(list, value) {
  openFormModal({
    title: value ? `Edit value · ${value.label}` : `Add value to ${list.name}`,
    fields: [
      { key: 'label', label: 'Label', required: true, help: 'What people see. Renaming updates every record that uses it.' },
      value ? null : { key: 'code', label: 'Code', required: true, help: 'Lowercase letters, numbers and _. Cannot change later.' },
      { key: 'color', label: 'Colour', type: 'color', required: true },
      { key: 'sort_order', label: 'Order', type: 'number', help: value ? null : 'Leave empty to add it at the end.' },
      { key: 'is_default', label: 'Default', type: 'checkbox', checkboxLabel: 'Pre-select this value on new records' },
      value ? { key: 'is_active', label: 'Active', type: 'checkbox', checkboxLabel: 'Active (untick to retire)', disabled: value.is_system, help: value.is_system ? 'Built-in values cannot be retired.' : null } : null,
      { key: 'description', label: 'Description', type: 'textarea' },
      value ? { key: 'reason', label: 'Reason for change', help: 'Saved in the audit log.', full: true } : null,
    ].filter(Boolean),
    values: value || { color: '#94A3B8' },
    submitLabel: value ? 'Save value' : 'Add value',
    onSubmit: (v) => {
      if (value?.is_system) delete v.is_active;
      return value
        ? api.patch(`/lookup-values/${value.id}`, { ...v, version: value.version })
        : api.post('/lookup-values', { ...v, lookup_type_id: list.id });
    },
    onDone: () => { showToast(value ? 'Value saved (draft)' : 'Value added (draft)', 'success'); load(); },
  });
}

load();
