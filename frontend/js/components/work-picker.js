/** Pick a work item by searching its code or title (any level you can see).
 *  const item = await pickWorkItem({ title: 'Which item?' });  → the item, or null if cancelled. */
import { api } from '../core/api.js';
import { el } from '../core/utils.js';
import { lookupBadge } from '../core/lookups.js';
import { openModal } from './modal.js';

export function pickWorkItem({ title = 'Choose a work item', params = {} } = {}) {
  return new Promise((resolve) => {
    let chosen = null;
    const input = el('input', { class: 'ct-input', type: 'search', placeholder: 'Code or title…', 'aria-label': 'Search work' });
    const results = el('div', { class: 'ct-stack', style: { gap: '4px', maxHeight: '320px', overflowY: 'auto' } });
    let timer;
    const search = async () => {
      try {
        const data = await api.get('/work-items', { q: input.value.trim(), per_page: 15, sort: 'code', ...params });
        results.replaceChildren(...(data.items.length ? data.items.map((i) => el('button', {
          class: 'ct-btn ct-btn--ghost', type: 'button', style: { justifyContent: 'flex-start', textAlign: 'left' },
          onClick: () => { chosen = i; modal.close(); },
        }, el('span', { class: 'ct-work-title__code' }, i.code), ' ', i.title, ' ', i.status_id ? lookupBadge(i.status_id) : null))
          : [el('p', { class: 'ct-muted ct-small' }, 'Nothing found.')]));
      } catch (err) { results.replaceChildren(el('p', { class: 'ct-text-danger ct-small' }, err.message)); }
    };
    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 250); });
    const modal = openModal({ title, body: el('div', { class: 'ct-stack' }, input, results), actions: [{ label: 'Cancel' }],
      onClose: () => resolve(chosen) });
    search();
    setTimeout(() => input.focus(), 50);
  });
}
