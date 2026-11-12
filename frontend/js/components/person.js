/** Small person display helpers used in tables, pickers and detail views. */
import { el } from '../core/utils.js';

export function createAvatar(person, { small = false } = {}) {
  const initials = person?.initials || (person?.full_name || '?').split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase();
  return el('span', { class: `ct-avatar${small ? ' ct-avatar--sm' : ''}`, 'aria-hidden': 'true' }, initials);
}

/** Avatar + name (+ optional second line). Shows '—' when there is no person. */
export function createPersonCell(person, subtitle) {
  if (!person) return el('span', { class: 'ct-muted' }, '—');
  return el('span', { class: 'ct-person' },
    createAvatar(person, { small: true }),
    el('span', { class: 'ct-person__text' },
      el('span', {}, person.full_name),
      subtitle ? el('span', { class: 'ct-person__sub' }, subtitle) : null));
}
