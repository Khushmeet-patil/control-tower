/**
 * Health display: colours come from the Health lookup list, reasons from the rules engine.
 *   healthBadge(item.health)            → badge with the reason as tooltip ('n/a' when not assessed)
 *   createFindings(health.findings)     → explained list: rule, reason, source item, next action, escalation
 */
import { lookupBadge, lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createBadge } from './badge.js';
import { createPersonCell } from './person.js';

export function healthBadge(health) {
  if (!health || !health.code) {
    const b = createBadge('n/a', 'var(--ct-border-strong)');
    b.title = health?.reason || 'Not assessed';
    return b;
  }
  const badge = lookupBadge(health.value_id);
  if (badge.nodeType === 1) badge.title = health.reason;
  return badge;
}

/** Badge for a health code ('red', 'amber'…), when only the code is known. */
export function healthBadgeFromCode(code) {
  const v = lookupValues('health', { includeRetired: true }).find((x) => x.code === code);
  return v ? lookupBadge(v.id) : createBadge('n/a', 'var(--ct-border-strong)');
}

function itemLink(ref) {
  return ref?.id ? el('a', { href: `/pages/item.html?id=${ref.id}` }, `${ref.code} ${ref.title}`) : el('span', { class: 'ct-muted' }, ref?.title || '—');
}

export function createFindings(findings, { kind = 'health', empty = 'No issues found.' } = {}) {
  const list = findings.filter((f) => f.kind === kind);
  if (!list.length) return el('p', { class: 'ct-muted ct-small' }, empty);
  return el('ul', { class: 'ct-findings' }, list.map((f) => el('li', { class: `ct-findings__item is-${f.outcome}` },
    el('div', { class: 'ct-findings__head' }, f.outcome_id ? lookupBadge(f.outcome_id) : null, el('strong', {}, f.rule)),
    el('div', {}, f.reason),
    el('div', { class: 'ct-findings__meta ct-small' },
      f.via_child || (f.source && f.source.id && f.rule === 'Child item') ? el('span', {}, 'Caused by ', itemLink(f.source)) : null,
      f.recommended_action ? el('span', {}, el('strong', {}, 'Next: '), f.recommended_action) : null,
      f.escalate_to ? el('span', { class: 'ct-findings__owner' }, 'Escalate to ', createPersonCell(f.escalate_to)) : null))));
}
