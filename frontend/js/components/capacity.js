/**
 * Workload against usable capacity (the prototype's Team & Capacity bands).
 *   loadStatusBadge('overloaded')            → coloured badge
 *   createCapacityBars(rows)                 → one bar per person: load %, coloured by band
 * Rows come from the API: { person, load_pct, free_pct, status }.
 */
import { el } from '../core/utils.js';
import { createBadge } from './badge.js';
import { createProgressBar } from './progress-bar.js';

export const LOAD_STATUS = {
  overloaded: ['Overloaded', 'var(--ct-danger)'],
  balanced: ['Balanced', 'var(--ct-success)'],
  underutilised: ['Underutilised', 'var(--ct-warning)'],
};

export function loadStatusBadge(status) {
  const [label, color] = LOAD_STATUS[status] || [status, 'var(--ct-border-strong)'];
  return createBadge(label, color);
}

export function loadColor(status) {
  return (LOAD_STATUS[status] || [])[1] || null;
}

export function createCapacityBars(rows) {
  if (!rows.length) return el('p', { class: 'ct-muted ct-small' }, 'Nobody has an allocation on open work.');
  return el('div', {}, rows.map((r) => el('div', { title: `${r.person.full_name}: ${r.load_pct}% allocated, ${r.free_pct}% free (${LOAD_STATUS[r.status]?.[0] || r.status})` },
    createProgressBar(r.load_pct, { label: r.person.full_name, color: loadColor(r.status) }))));
}
