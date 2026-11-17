/**
 * Workload against usable capacity (the prototype's Team & Capacity bands).
 *   loadStatusBadge('overloaded')            → coloured badge
 *   createCapacityBars(rows)                 → one bar per person: load %, coloured by band
 *   skillBadges([ids])                       → the person's skills (Skill lookup colours)
 *   createWeekStrip(weeks)                   → week-by-week load cells (time-phased allocation, time off)
 * Rows come from the API: { person, load_pct, usable_pct, free_pct, status }.
 */
import { lookupBadge } from '../core/lookups.js';
import { el, formatDate } from '../core/utils.js';
import { createBadge } from './badge.js';
import { createProgressBar } from './progress-bar.js';

export const LOAD_STATUS = {
  overloaded: ['Overloaded', 'var(--ct-danger)'],
  balanced: ['Balanced', 'var(--ct-success)'],
  underutilised: ['Underutilised', 'var(--ct-warning)'],
  on_leave: ['On leave', 'var(--ct-text-subtle)'],
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

export function skillBadges(ids) {
  if (!ids?.length) return el('span', { class: 'ct-muted' }, '—');
  return el('div', { class: 'ct-tag-list' }, ids.map((id) => lookupBadge(id)));
}

/** One cell per week: load % (coloured by band) against usable capacity; time off shows as "off". */
export function createWeekStrip(weeks) {
  return el('div', { class: 'ct-weeks' }, weeks.map((w) => {
    const [label, color] = LOAD_STATUS[w.status] || ['', null];
    const cell = el('span', { class: `ct-weeks__cell is-${w.status}`,
      title: `Week of ${formatDate(w.week_start)}: ${w.load_pct}% allocated, ${w.usable_pct}% usable (${label})` },
    w.status === 'on_leave' ? 'off' : `${w.load_pct}`);
    if (color) cell.style.setProperty('--cell-color', color);
    return cell;
  }));
}
