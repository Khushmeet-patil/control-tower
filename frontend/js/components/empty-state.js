/** createEmptyState({ title: 'No items', message: 'Try another filter', icon: 'inbox', action: node }) */
import { icon as makeIcon } from '../core/icons.js';
import { el } from '../core/utils.js';

export function createEmptyState({ title = 'Nothing here yet', message, icon = 'inbox', action } = {}) {
  return el('div', { class: 'ct-empty' },
    el('div', { class: 'ct-empty__icon' }, makeIcon(icon, { size: 40 })),
    el('div', { class: 'ct-empty__title' }, title),
    message ? el('p', { class: 'ct-small' }, message) : null,
    action ? el('div', { style: { marginTop: '16px' } }, action) : null);
}
