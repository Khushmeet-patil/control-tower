/** My work: what the signed-in person is accountable for, responsible for and assigned to (open items). */
import { initLayout, pageHeader } from '../core/layout.js';
import { el } from '../core/utils.js';
import { createKpis } from '../components/kpi.js';
import { countWork, createWorkTable } from '../components/work-table.js';

const { content } = await initLayout({ active: 'my-work', title: 'My work', permission: 'work.view' });

const SECTIONS = [
  { mine: 'accountable', title: 'I am accountable for', note: 'You answer for the outcome.', columns: ['item', 'type', 'status', 'responsible', 'progress', 'planned_end'] },
  { mine: 'responsible', title: 'I am responsible for', note: 'You lead the delivery day to day.', columns: ['item', 'type', 'status', 'accountable', 'progress', 'planned_end'] },
  { mine: 'assigned', title: 'I am assigned to', note: 'You contribute with an allocation.', columns: ['item', 'type', 'status', 'accountable', 'progress', 'planned_end'] },
];

const kpiSlot = el('div');
content.append(
  pageHeader('My work', 'Open items you own or work on. Finished and cancelled items are hidden.'),
  kpiSlot,
  ...SECTIONS.map((s) => el('section', { class: 'ct-card', id: `mine-${s.mine}` },
    el('div', { class: 'ct-card__header' }, el('div', {}, el('h3', { class: 'ct-card__title' }, s.title), el('p', { class: 'ct-muted ct-small' }, s.note))),
    createWorkTable({ params: { mine: s.mine, open: '1' }, columns: s.columns, defaultSort: 'planned_end', pageSize: 10,
      emptyState: { title: 'Nothing here', message: 'Items appear here when you are named on them.' } }).element)),
);

const [accountable, responsible, assigned, overdue] = await Promise.all([
  countWork({ mine: 'accountable', open: '1' }), countWork({ mine: 'responsible', open: '1' }),
  countWork({ mine: 'assigned', open: '1' }), countWork({ mine: 'any', overdue: '1' }),
]).catch(() => ['—', '—', '—', '—']);
const jump = (id) => () => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
kpiSlot.append(createKpis([
  { value: accountable, label: 'Accountable for', onClick: jump('mine-accountable') },
  { value: responsible, label: 'Responsible for', onClick: jump('mine-responsible') },
  { value: assigned, label: 'Assigned to', onClick: jump('mine-assigned') },
  { value: overdue, label: 'Overdue, involving me', color: overdue ? 'var(--ct-danger)' : null, href: '/pages/work.html?mine=any&overdue=1&level=all' },
]));
