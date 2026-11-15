/**
 * Ranked actions from GET /action-centre ("top" or "needed").
 * createActionList(entries, { numbered: true, onChange }) — each shows what, why, the next action,
 * who owns it, the due date, and the scoring factors behind its rank. Approvals open the review dialog.
 */
import { el, formatDate } from '../core/utils.js';
import { openReview } from './approval.js';
import { createEmptyState } from './empty-state.js';

export function createActionList(entries, { numbered = true, onChange, empty } = {}) {
  if (!entries.length) {
    return createEmptyState({ title: 'Nothing needs you right now', icon: 'check',
      message: empty || 'Actions appear here when the rules find a problem on work you answer for, or when work waits for your approval.' });
  }
  return el('div', { class: 'ct-stack', style: { gap: '10px' } }, entries.map((e, i) => el('div', { class: `ct-top is-${e.outcome}` },
    numbered ? el('span', { class: 'ct-top__rank' }, String(i + 1)) : null,
    el('div', { class: 'ct-top__body' },
      el('div', { class: 'ct-detail-head' },
        el('strong', {}, e.what, ': ', e.item.id ? el('a', { href: `/pages/item.html?id=${e.item.id}${e.kind === 'approval' ? '&tab=approvals' : ''}` }, `${e.item.code} ${e.item.title}`) : e.item.title),
        e.kind === 'approval' ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => openReview(e.approval_id, { onDone: onChange }) }, 'Review') : null),
      el('div', { class: 'ct-muted ct-small' }, el('strong', {}, 'Why: '), e.why),
      e.next ? el('div', { class: 'ct-small' }, el('strong', {}, 'Next: '), e.next,
        e.owner ? [' · ', el('strong', {}, 'Owner: '), e.owner.full_name] : null,
        e.due ? [' · ', el('strong', {}, 'Due: '), formatDate(e.due)] : null) : null,
      el('div', { class: 'ct-top__factors', title: 'How this was ranked' },
        el('span', { class: 'ct-factor' }, `Score ${e.score}`),
        e.factors.map((f) => el('span', { class: 'ct-factor' }, `${f.label} +${f.points}`)))))));
}
