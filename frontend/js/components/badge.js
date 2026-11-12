/**
 * createBadge('Blocked', '#B42318') — coloured dot + label.
 * Colours for statuses/priorities come from lookup values (Phase 2), never hard-coded in pages.
 */
import { el } from '../core/utils.js';

export function createBadge(label, color) {
  const badge = el('span', { class: 'ct-badge' }, label);
  if (color) badge.style.setProperty('--badge-color', color);
  return badge;
}
