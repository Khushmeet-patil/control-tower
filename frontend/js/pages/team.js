/** My team (/pages/team.html?unit=…): the units a manager runs, their people, load against usable
 *  capacity, progress of each unit below, and overdue work. Only units the viewer manages can be opened,
 *  and every number opens the list behind it. */
import { api } from '../core/api.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { el } from '../core/utils.js';
import { loadColor, loadStatusBadge } from '../components/capacity.js';
import { createEmptyState } from '../components/empty-state.js';
import { createKpis } from '../components/kpi.js';
import { createPersonCell } from '../components/person.js';
import { createProgressBar } from '../components/progress-bar.js';
import { showError } from '../components/toast.js';
import { flattenTree } from '../components/tree.js';
import { createWorkTable, portfolioUrl } from '../components/work-table.js';

const { content } = await initLayout({ active: 'team', title: 'My team', permission: 'work.view' });

const TONE = { red: 'var(--ct-danger)', amber: 'var(--ct-warning)' };

function card(title, body, extra) {
  return el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, title), extra || null),
    el('div', { class: 'ct-card__body' }, body));
}

/** A number that opens the Portfolio filtered to the items it counts. */
function countLink(metric) {
  if (!metric.value) return el('span', { class: 'ct-muted' }, '0');
  return el('a', { href: portfolioUrl(metric.filters), class: metric.tone === 'red' ? 'ct-text-danger' : null,
    title: `Open the ${metric.value} item(s)` }, String(metric.value));
}

async function render(unitId) {
  let team;
  try { team = await api.get('/team', { unit_id: unitId }); } catch (err) {
    content.replaceChildren(pageHeader('My team'), createEmptyState({ title: err.status === 403 ? 'No team to show' : 'Could not load the team',
      message: err.message, icon: 'users' }));
    if (err.status !== 403) showError(err);
    return;
  }
  history.replaceState(null, '', `?unit=${team.unit.id}`);

  const picker = team.units.length > 1 ? el('select', { class: 'ct-select', 'aria-label': 'Unit', style: { minWidth: '220px' },
    onChange: (e) => render(e.target.value) },
  flattenTree(team.units).map((u) => el('option', { value: u.id, selected: u.id === team.unit.id }, `${'\u00a0\u00a0'.repeat(u.depth)}${u.name}`))) : null;

  const kpis = createKpis(team.kpis.map((k) => ({
    value: k.value, label: k.label, color: k.value && TONE[k.tone] ? TONE[k.tone] : null,
    href: k.filters ? portfolioUrl(k.filters) : k.key === 'members' || k.key === 'overloaded' ? '#people' : null,
  })).concat([{ value: `${team.progress}%`, label: 'Progress (validated, weighted)' }]));

  // The prototype's Team & Capacity table: who, role, allocated, free, status, initiatives, open actions.
  const members = team.members.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
    el('thead', {}, el('tr', {}, ['Person', 'Role / function', 'Allocated', 'Free', 'Status', 'Initiatives', 'Open actions', 'Involved (open)', 'Overdue']
      .map((h) => el('th', { scope: 'col' }, h)))),
    el('tbody', {}, team.members.map((m) => {
      const count = (key) => countLink(m.counts.find((c) => c.key === key));
      return el('tr', { class: m.status === 'overloaded' ? 'is-late' : null },
        el('td', {}, createPersonCell(m.person)),
        el('td', {}, m.person.job_title || '—', m.person.function ? el('div', { class: 'ct-muted ct-small' }, m.person.function) : null),
        el('td', { style: { minWidth: '150px' } }, createProgressBar(m.load_pct, { color: loadColor(m.status) })),
        el('td', {}, `${m.free_pct}%`),
        el('td', {}, loadStatusBadge(m.status)),
        el('td', { class: 'ct-small' },
          m.initiatives.length ? m.initiatives.map((i, n) => [n ? ', ' : '', el('a', { href: `/pages/item.html?id=${i.id}` }, i.title)]) : el('span', { class: 'ct-muted' }, '—'),
          m.hidden_items ? el('div', { class: 'ct-muted', title: 'Work outside your area also counts in this person\'s load' }, `+${m.hidden_items} you cannot open`) : null),
        el('td', {}, count('actions')),
        el('td', {}, count('open')),
        el('td', {}, count('overdue')));
    }))))
    : createEmptyState({ title: 'Nobody in this unit yet', icon: 'users' });

  const subunits = team.subunits.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
    el('thead', {}, el('tr', {}, ['Unit', 'Progress', 'Open', 'Overdue', 'Red'].map((h) => el('th', { scope: 'col' }, h)))),
    el('tbody', {}, team.subunits.map((s) => el('tr', {},
      el('td', {}, el('button', { class: 'ct-link-button', type: 'button', onClick: () => render(s.unit.id) }, s.unit.name)),
      el('td', { style: { minWidth: '160px' } }, createProgressBar(s.progress)),
      el('td', {}, countLink(s.open)), el('td', {}, countLink(s.overdue)), el('td', {}, countLink(s.red)))))))
    : null;

  const overdue = createWorkTable({
    params: { unit_id: team.unit.id, include_descendants: '1', overdue: '1' },
    columns: ['item', 'type', 'accountable', 'status', 'planned_end'], defaultSort: 'planned_end', pageSize: 10,
    emptyState: { title: 'Nothing overdue', message: 'Overdue work in this unit and the units below it appears here.', icon: 'check' },
  });

  content.replaceChildren(...[
    pageHeader(team.unit.name, `${team.unit.head ? `Led by ${team.unit.head.full_name} · ` : ''}people, load and progress of this unit and every unit below it.`,
      picker ? [picker] : []),
    kpis,
    el('div', { id: 'people' }, card('Team & capacity', members,
      el('span', { class: 'ct-muted ct-small' }, `Usable capacity = ${team.usable_pct}% (buffer ${team.buffer_pct}% for unplanned work) · allocation on open work today`))),
    subunits ? card('Units below', subunits) : null,
    card('Overdue work', overdue.element, el('a', { class: 'ct-small', href: portfolioUrl(team.overdue_filters) }, 'Open in Portfolio')),
  ].filter(Boolean));
}

render(new URLSearchParams(location.search).get('unit'));
