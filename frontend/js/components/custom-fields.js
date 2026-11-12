/**
 * Admin-defined custom fields, turned into the standard building blocks:
 *   customFormFields('person', record)   → form-builder field definitions (keys 'custom_fields.<code>')
 *   withCustomValues(values)             → moves those keys into { custom_fields: {...} } for the API
 *   customFilterFields('person')         → filter-bar fields (keys 'cf.<code>', understood by list APIs)
 *   customColumns('person')              → data-table columns for fields marked "show in list"
 *   customValueNode(field, record)       → display node for one value (badges keep their lookup colour)
 * Requires loadSettings() from core/lookups.js to have finished.
 */
import { el, formatDate } from '../core/utils.js';
import { customFields, lookupBadge, lookupOptions } from '../core/lookups.js';
import { createPersonCell } from './person.js';

const PREFIX = 'custom_fields.';
const FORM_TYPE = { text: 'text', number: 'number', date: 'date', url: 'url', select: 'select', multi_select: 'multiselect', person: 'person' };

export function customFormFields(entityType, record = null) {
  const values = record?.custom_fields || {};
  return customFields(entityType).map((f) => {
    const current = values[f.code] ?? null;
    const def = {
      key: PREFIX + f.code, label: f.label, type: FORM_TYPE[f.field_type] || 'text',
      required: f.is_required, help: f.help_text || null, value: current,
    };
    if (f.field_type === 'select' || f.field_type === 'multi_select') def.options = lookupOptions(f.lookup, current);
    if (f.field_type === 'person') def.value = record?.custom_people?.[f.code] || null;
    if (f.field_type === 'url') def.placeholder = 'https://';
    return def;
  });
}

/** { name: 'x', 'custom_fields.budget': 5 } → { name: 'x', custom_fields: { budget: 5 } } */
export function withCustomValues(values) {
  const out = {};
  const custom = {};
  for (const [key, value] of Object.entries(values)) {
    if (key.startsWith(PREFIX)) custom[key.slice(PREFIX.length)] = Array.isArray(value) && !value.length ? null : value;
    else out[key] = value;
  }
  if (Object.keys(custom).length) out.custom_fields = custom;
  return out;
}

/** Filters for list-based fields (the ones a select can express). */
export function customFilterFields(entityType) {
  return customFields(entityType)
    .filter((f) => f.is_filterable && (f.field_type === 'select' || f.field_type === 'multi_select'))
    .map((f) => ({ key: `cf.${f.code}`, type: 'select', label: f.label, options: lookupOptions(f.lookup) }));
}

export function customColumns(entityType) {
  return customFields(entityType)
    .filter((f) => f.show_in_list)
    .map((f) => ({ key: `cf.${f.code}`, label: f.label, render: (row) => customValueNode(f, row) }));
}

export function customValueNode(field, record) {
  const value = record?.custom_fields?.[field.code];
  if (value === null || value === undefined || value === '') return el('span', { class: 'ct-muted' }, '—');
  switch (field.field_type) {
    case 'select': return lookupBadge(value);
    case 'multi_select': return el('div', { class: 'ct-tag-list' }, value.map((id) => lookupBadge(id)));
    case 'date': return formatDate(value);
    case 'number': return Number(value).toLocaleString();
    case 'person': return createPersonCell(record.custom_people?.[field.code] || { full_name: `#${value}` });
    case 'url': {
      const safe = /^https?:\/\//i.test(value) ? value : null;
      return safe ? el('a', { href: safe, target: '_blank', rel: 'noopener noreferrer' }, value) : String(value);
    }
    default: return String(value);
  }
}
