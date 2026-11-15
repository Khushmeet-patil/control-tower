import { initLayout, pageHeader, can } from '../core/layout.js';
import { el, greeting } from '../core/utils.js';
import { createEmptyState } from '../components/empty-state.js';
import { createKpis } from '../components/kpi.js';
import { countWork, createWorkTable } from '../components/work-table.js';
import { loadStatusBadge } from '../components/capacity.js';
import { api } from '../core/api.js';
import { formatDate } from '../core/utils.js';
import { openReview } from '../components/approval.js';
import { createPersonCell } from '../components/person.js';
import { createActionList } from '../components/action-list.js';
import { createProgressBar } from '../components/progress-bar.js';
import { portfolioUrl } from '../components/work-table.js';

const { user, content } = await initLayout({ active: 'home', title: 'My Home' });

function card(title, body, link) {
  return el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, title), link ? el('a', { class: 'ct-small', href: link }, 'See all') : null),
    body);
}

content.append(pageHeader(`${greeting()}, ${user.full_name.split(' ')[0]}`, 'Your work, approvals and team at a glance.'));

if (can(user, 'work.view')) {
  const kpiSlot = el('div');
  const mine = (key, columns) => createWorkTable({ params: { mine: key, open: '1' }, columns, defaultSort: 'planned_end', pageSize: 5,
    emptyState: { title: 'No open items', message: '' } }).element;
  const topSlot = el('div', { class: 'ct-card__body' }, el('p', { class: 'ct-muted' }, 'Loading…'));
  const loadTop = () => api.get('/action-centre').then((ac) => topSlot.replaceChildren(createActionList(ac.top, { onChange: loadTop })))
    .catch(() => topSlot.replaceChildren(createEmptyState({ title: 'Could not load your actions' })));
  content.append(
    kpiSlot,
    el('section', { class: 'ct-card' },
      el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, 'Top 5 actions for me'), el('a', { class: 'ct-small', href: '/pages/action-centre.html' }, 'Action Centre')),
      topSlot),
    el('div', { class: 'ct-grid-2' },
      card('I am accountable for', mine('accountable', ['item_short', 'status', 'progress', 'planned_end']), '/pages/my-work.html#mine-accountable'),
      card('I am responsible for', mine('responsible', ['item_short', 'status', 'progress', 'planned_end']), '/pages/my-work.html#mine-responsible')),
    el('div', { class: 'ct-grid-2' },
      card('My assignments', mine('assigned', ['item_short', 'status', 'planned_end']), '/pages/my-work.html#mine-assigned'),
      card('Awaiting my approval', approvalsBody(), '/pages/approvals.html')),
    el('div', { class: 'ct-grid-2' },
      card('Upcoming deadlines (next 14 days)', createWorkTable({ params: { mine: 'any', due_within: '14' }, columns: ['item_short', 'status', 'planned_end'],
        defaultSort: 'planned_end', pageSize: 5, emptyState: { title: 'Nothing due in the next 14 days', message: '', icon: 'check' } }).element,
      portfolioUrl({ level: 'all', mine: 'any', due_within: '14' })),
      can(user, 'work.manage') ? teamCard() : null),
  );
  loadTop();
  const [accountable, responsible, overdue, due, approvals] = await Promise.all([
    countWork({ mine: 'accountable', open: '1' }), countWork({ mine: 'responsible', open: '1' }), countWork({ mine: 'any', overdue: '1' }),
    countWork({ mine: 'any', due_within: '14' }), api.get('/approvals/counts').then((c) => c.waiting_for_me),
  ]).catch(() => ['—', '—', '—', '—', '—']);
  kpiSlot.append(createKpis([
    { value: accountable, label: 'Accountable for', href: '/pages/my-work.html#mine-accountable' },
    { value: responsible, label: 'Responsible for', href: '/pages/my-work.html#mine-responsible' },
    { value: overdue, label: 'Overdue, involving me', color: overdue ? 'var(--ct-danger)' : null, href: portfolioUrl({ level: 'all', mine: 'any', overdue: '1' }) },
    { value: due, label: 'Due in 14 days', href: portfolioUrl({ level: 'all', mine: 'any', due_within: '14' }) },
    { value: approvals, label: 'Awaiting my approval', color: approvals ? 'var(--ct-warning)' : null, href: '/pages/approvals.html' },
  ]));
} else {
  content.append(card('Welcome', createEmptyState({ title: 'No work access yet', message: 'Ask an administrator to give you a role that can see work.' })));
}

/** Managers and executives: their unit's exceptions and the progress of the units below it
 *  (for organisation-wide roles this is the executive roll-up by division). */
function teamCard() {
  const body = el('div', { class: 'ct-card__body' }, el('p', { class: 'ct-muted' }, 'Loading…'));
  const section = card('My team', body, '/pages/team.html');
  api.get('/team').then((team) => {
    section.querySelector('.ct-card__title').textContent = `My team · ${team.unit.name}`;
    const pick = (key) => team.kpis.find((k) => k.key === key);
    const tiles = ['open', 'overdue', 'red', 'approval'].map(pick).filter(Boolean).map((k) => ({
      value: k.value, label: k.label, href: portfolioUrl(k.filters),
      color: k.value && k.tone === 'red' ? 'var(--ct-danger)' : k.value && k.tone === 'amber' ? 'var(--ct-warning)' : null }));
    const overloaded = team.members.filter((m) => m.status === 'overloaded');
    body.replaceChildren(el('div', { class: 'ct-stack' },
      createKpis(tiles),
      createProgressBar(team.progress, { label: `${team.unit.name} progress` }),
      team.subunits.map((u) => el('a', { class: 'ct-plain-link', href: `/pages/team.html?unit=${u.unit.id}` }, createProgressBar(u.progress, { label: u.unit.name }))),
      overloaded.length ? el('div', { class: 'ct-small' }, loadStatusBadge('overloaded'), ' ', overloaded.map((m) => `${m.person.full_name} (${m.load_pct}%)`).join(', '))
        : el('p', { class: 'ct-muted ct-small' }, 'Nobody is overloaded.')));
  }).catch((err) => body.replaceChildren(createEmptyState({ title: err.status === 403 ? 'You do not manage a unit' : 'Could not load your team', message: '' })));
  return section;
}

/** The first approvals waiting for me, each with a Review button. */
function approvalsBody() {
  const body = el('div', { class: 'ct-card__body' }, el('p', { class: 'ct-muted' }, 'Loading…'));
  const load = () => api.get('/approvals', { box: 'mine', per_page: 5 }).then((data) => {
    if (!data.items.length) {
      body.replaceChildren(createEmptyState({ title: 'All clear', message: 'Completed work waiting for your approval appears here.', icon: 'check' }));
      return;
    }
    body.replaceChildren(el('div', { class: 'ct-stack', style: { gap: '12px' } }, data.items.map((r) => el('div', { class: 'ct-detail-head' },
      el('div', { class: 'ct-work-title' },
        el('a', { href: `/pages/item.html?id=${r.work_item.id}&tab=approvals` }, r.work_item.title),
        el('span', { class: 'ct-work-title__code' }, `${r.work_item.code} · ${r.current_step_name} · since ${formatDate(r.submitted_at)}`)),
      el('div', { class: 'ct-actions' }, createPersonCell(r.submitted_by),
        el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => openReview(r.id, { onDone: load }) }, 'Review'))))));
  }).catch(() => body.replaceChildren(createEmptyState({ title: 'Could not load approvals' })));
  load();
  return body;
}
