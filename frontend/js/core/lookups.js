/**
 * Published settings for the whole page: lookups (with colours), custom fields and terms.
 * Loaded once per page from GET /settings and cached; pages never hard-code a label or colour.
 *
 *   await loadSettings();
 *   lookupBadge(item.status_id)            → coloured badge (retired values still show)
 *   lookupOptions('priority', currentId)    → [{ value, label }] for a select (active + current)
 *   term('person', { plural: true })        → 'People' (or whatever the admin renamed it to)
 *   customFields('person')                  → active custom field definitions
 */
import { api } from './api.js';
import { createBadge } from '../components/badge.js';

let settingsPromise = null;
let settings = { lookups: {}, fields: {}, terms: {}, version: null };
const valueIndex = new Map();

export function loadSettings({ refresh = false } = {}) {
  if (!settingsPromise || refresh) {
    settingsPromise = api.get('/settings').then((data) => {
      settings = data;
      valueIndex.clear();
      for (const list of Object.values(data.lookups)) {
        for (const v of list.values) valueIndex.set(v.id, { ...v, list: list.code });
      }
      return data;
    }).catch((err) => {
      settingsPromise = null; // allow a retry; callers fall back to defaults
      throw err;
    });
  }
  return settingsPromise;
}

/** Values of a list, in admin order. Retired values are left out unless `includeRetired`. */
export function lookupValues(listCode, { includeRetired = false } = {}) {
  const values = settings.lookups[listCode]?.values || [];
  return includeRetired ? values : values.filter((v) => v.is_active);
}

export function lookupValue(id) {
  return valueIndex.get(Number(id)) || null;
}

/** Options for a select: active values, plus the current value even if it has been retired. */
export function lookupOptions(listCode, current = null) {
  const keep = new Set([current].flat().filter((v) => v !== null && v !== undefined).map(Number));
  return lookupValues(listCode, { includeRetired: true })
    .filter((v) => v.is_active || keep.has(v.id))
    .map((v) => ({ value: v.id, label: v.is_active ? v.label : `${v.label} (retired)`, color: v.color }));
}

export function defaultLookupValue(listCode) {
  return lookupValues(listCode).find((v) => v.is_default)?.id ?? null;
}

/** Coloured badge for a stored lookup value id; '—' text when empty or unknown. */
export function lookupBadge(id) {
  const v = lookupValue(id);
  if (!v) return document.createTextNode('—');
  const badge = createBadge(v.label, v.color);
  if (!v.is_active) {
    badge.title = 'Retired value';
    badge.classList.add('is-retired');
  }
  return badge;
}

export function term(key, { plural = false, fallback } = {}) {
  const t = settings.terms[key];
  if (!t) return fallback ?? key;
  return plural ? t.plural : t.singular;
}

export function customFields(entityType) {
  return settings.fields[entityType] || [];
}

export function fieldTypes() {
  return settings.field_types || {};
}

export function entityTypes() {
  return settings.entity_types || {};
}
