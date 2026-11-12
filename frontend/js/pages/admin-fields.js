/** Custom fields: admin-defined fields that appear in forms, lists, filters and the API without code changes. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { entityTypes, fieldTypes } from '../core/lookups.js';
import { clear, el } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { createSettingsBanner } from '../components/settings-banner.js';
import { showError, showToast } from '../components/toast.js';

const { content } = await initLayout({ active: 'fields', title: 'Custom fields', permission: 'settings.manage' });

const ENTITIES = entityTypes();
const TYPES = fieldTypes();
const LIST_TYPES = ['select', 'multi_select'];
let entity = new URLSearchParams(location.search).get('entity') || Object.keys(ENTITIES)[0] || 'person';
let lists = [];
let fields = [];

const banner = createSettingsBanner({ onChange: load });
const tabs = el('div', { class: 'ct-tabs', role: 'tablist' });
const tbody = el('tbody');

content.append(
  pageHeader('Custom fields',
    'Extra fields for your records. Once published they appear in forms, list columns, filters and the API.',
    [el('button', { class: 'ct-btn ct-btn--primary', onClick: () => edit(null) }, icon('plus', { size: 16 }), 'New field')]),
  banner.element,
  el('section', { class: 'ct-card' }, tabs,
    el('div', { class: 'ct-table-wrap' },
      el('table', { class: 'ct-table' },
        el('thead', {}, el('tr', {}, ['Field', 'Type', 'Options from', 'Required', 'In list', 'Filter', 'Status'].map((h) => el('th', { scope: 'col' }, h)))),
        tbody))),
);

function renderTabs() {
  tabs.replaceChildren(...Object.entries(ENTITIES).map(([key, label]) => el('button', {
    class: `ct-tabs__tab${key === entity ? ' is-active' : ''}`, role: 'tab', 'aria-selected': String(key === entity),
    onClick: () => { entity = key; history.replaceState(null, '', `?entity=${key}`); renderTabs(); load(); },
  }, label)));
}

const listName = (id) => lists.find((l) => l.id === id)?.name || '—';
const yes = (flag) => (flag ? 'Yes' : '—');

async function load() {
  try {
    [lists, fields] = await Promise.all([
      api.get('/lookup-types').then((d) => d.items),
      api.get('/field-definitions', { entity_type: entity }).then((d) => d.items),
    ]);
    clear(tbody);
    if (!fields.length) {
      tbody.append(el('tr', {}, el('td', { colspan: 7 }, createEmptyState({
        title: `No custom fields for ${ENTITIES[entity]?.toLowerCase() || entity}`, message: 'Add one, then publish to make it live.', icon: 'form' }))));
    }
    for (const f of fields) {
      tbody.append(el('tr', {
        class: `is-clickable${f.is_active ? '' : ' ct-row-retired'}`, tabindex: '0',
        onClick: () => edit(f), onKeydown: (e) => { if (e.key === 'Enter') edit(f); },
      },
        el('td', {}, el('div', { style: { fontWeight: 600 } }, f.label), el('div', { class: 'ct-muted ct-small' }, f.code)),
        el('td', {}, TYPES[f.field_type] || f.field_type),
        el('td', {}, LIST_TYPES.includes(f.field_type) ? el('a', { href: `/pages/admin/lookups.html?list=${f.lookup_type_id}`, onClick: (e) => e.stopPropagation() }, listName(f.lookup_type_id)) : '—'),
        el('td', {}, yes(f.is_required)),
        el('td', {}, yes(f.show_in_list)),
        el('td', {}, yes(f.is_filterable)),
        el('td', {}, f.is_active ? createBadge('Active', 'var(--ct-success)') : createBadge('Retired'))));
    }
  } catch (err) { showError(err); }
  banner.refresh();
}

function edit(field) {
  const itemTypes = lists.find((l) => l.code === 'item_type')?.values.filter((v) => v.is_active) || [];
  openFormModal({
    title: field ? `Edit field · ${field.label}` : `New field on ${ENTITIES[entity]?.toLowerCase() || entity}`,
    intro: field ? `Type: ${TYPES[field.field_type]}${LIST_TYPES.includes(field.field_type) ? ` (options from ${listName(field.lookup_type_id)})` : ''}. The code, type and list cannot change once created, so stored values stay valid.` : null,
    fields: [
      { key: 'label', label: 'Label', required: true },
      field ? null : { key: 'code', label: 'Code', required: true, help: 'Lowercase letters, numbers and _ (e.g. business_impact). Used in the API.' },
      field ? null : { key: 'field_type', label: 'Type', type: 'select', required: true, options: Object.entries(TYPES).map(([value, label]) => ({ value, label })) },
      field ? null : {
        key: 'lookup_type_id', label: 'Options from list', type: 'select',
        options: lists.filter((l) => l.is_active).map((l) => ({ value: l.id, label: l.name })),
        help: 'Select fields only. Values and colours come from this list (manage it under Lookups & colours).',
      },
      { key: 'help_text', label: 'Help text', full: true, help: 'Shown under the field in forms.' },
      { key: 'sort_order', label: 'Order', type: 'number' },
      { key: 'is_required', label: 'Required', type: 'checkbox', checkboxLabel: 'Required' },
      { key: 'show_in_list', label: 'In list', type: 'checkbox', checkboxLabel: 'Show as a column in lists' },
      { key: 'is_filterable', label: 'Filter', type: 'checkbox', checkboxLabel: 'Can be used to filter lists' },
      entity === 'work_item' && itemTypes.length ? {
        key: 'item_type_ids', label: 'Only for item types', type: 'checkboxes',
        options: itemTypes.map((v) => ({ value: v.id, label: v.label, color: v.color })), help: 'Leave all unticked to use it on every item type.',
      } : null,
      field ? { key: 'is_active', label: 'Active', type: 'checkbox', checkboxLabel: 'Active (untick to retire; stored values are kept)' } : null,
      field ? { key: 'reason', label: 'Reason for change', help: 'Saved in the audit log.', full: true } : null,
    ].filter(Boolean),
    values: field || { field_type: 'text', is_filterable: true },
    submitLabel: field ? 'Save field' : 'Create field',
    onSubmit: (v) => (field
      ? api.patch(`/field-definitions/${field.id}`, { ...v, version: field.version })
      : api.post('/field-definitions', { ...v, entity_type: entity, lookup_type_id: LIST_TYPES.includes(v.field_type) ? v.lookup_type_id : null })),
    onDone: () => { showToast(field ? 'Field saved (draft)' : 'Field created (draft)', 'success'); load(); },
  });
}

renderTabs();
load();
