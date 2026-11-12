import { initLayout, pageHeader } from '../core/layout.js';
import { el, greeting } from '../core/utils.js';
import { createEmptyState } from '../components/empty-state.js';

const { user, content } = await initLayout({ active: 'home', title: 'My Home' });

function panel(title, empty) {
  return el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', {}, title)),
    createEmptyState(empty));
}

content.append(
  pageHeader(`${greeting()}, ${user.full_name.split(' ')[0]}`, 'Your work, approvals and team at a glance.'),
  el('div', { class: 'ct-grid' },
    panel('I am accountable for', { title: 'No items yet', message: 'Work you are accountable for will appear here.' }),
    panel('I am responsible for', { title: 'No items yet', message: 'Work you lead day to day will appear here.' }),
    panel('Awaiting my approval', { title: 'All clear', message: 'Approvals waiting for you will appear here.', icon: 'check' }),
  ),
);
