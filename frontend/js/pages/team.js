/** My team (/pages/team.html?unit=…): the prototype's Team & Capacity screen on real data.
 *  People with skills, load against their own usable capacity (part time and time off count), free
 *  capacity, initiatives, open actions and backlog; "find by skill"; the next 8 weeks of load; capacity
 *  and progress of each unit below; overdue work. Only units the viewer manages can be opened, and
 *  every number opens the list behind it. Managers record time off and capacity profiles here. */
import { api } from '../core/api.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge, lookupOptions } from '../core/lookups.js';
import { el, formatDate } from '../core/utils.js';
import { createWeekStrip, loadColor, loadStatusBadge, skillBadges } from '../components/capacity.js';
import { openFormModal } from '../components/form-builder.js';
import { openModal } from '../components/modal.js';
import { showToast } from '../components/toast.js';
import { createEmptyState } from '../components/empty-state.js';
import { createKpis } from '../components/kpi.js';
import { createPersonCell } from '../components/person.js';
import { createProgressBar } from '../components/progress-bar.js';
import { showError } from '../components/toast.js';
import { flattenTree } from '../components/tree.js';
import { createWorkTable, portfolioUrl } from '../components/work-table.js';

const { user, content } = await initLayout({ active: 'team', title: 'My team', permission: 'work.view' });
const canManagePeople = can(user, 'people.manage');
let skillFilter = '';

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

  // The prototype's Team & Capacity table: who, role, skills, allocated, free, status, initiatives,
  // open actions and backlog. "Find by skill" narrows it and puts the most free capacity first.
  const skillPicker = el('select', { class: 'ct-select', 'aria-label': 'Find by skill', style: { width: '300px', maxWidth: '100%' },
    onChange: (e) => { skillFilter = e.target.value; render(team.unit.id); } },
  el('option', { value: '' }, 'Find by skill (shows spare capacity)'),
  lookupOptions('skill').map((o) => el('option', { value: o.value, selected: String(o.value) === skillFilter }, o.label)));
  const shown = skillFilter
    ? team.members.filter((m) => m.skill_ids.includes(Number(skillFilter))).sort((x, y) => y.free_pct - x.free_pct)
    : team.members;
  const members = shown.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
    el('thead', {}, el('tr', {}, ['Person / role', 'Skills', 'Allocated', 'Free', 'Status', 'Initiatives', 'Open actions', 'Backlog (pd)', 'Overdue',
      canManagePeople ? '' : null].filter((h) => h !== null).map((h) => el('th', { scope: 'col' }, h)))),
    el('tbody', {}, shown.map((m) => {
      const count = (key) => countLink(m.counts.find((c) => c.key === key));
      return el('tr', { class: m.status === 'overloaded' ? 'is-late' : null },
        el('td', {}, createPersonCell(m.person, [m.person.job_title, m.person.function].filter(Boolean).join(' · '))),
        el('td', {}, skillBadges(m.skill_ids)),
        el('td', { style: { minWidth: '150px' }, title: `${m.load_pct}% allocated of ${m.usable_pct}% usable${m.capacity_pct < 100 ? ` (works ${m.capacity_pct}%)` : ''}` },
          createProgressBar(m.load_pct, { color: loadColor(m.status) }),
          m.capacity_pct < 100 ? el('div', { class: 'ct-muted ct-small' }, `works ${m.capacity_pct}%`) : null),
        el('td', {}, `${m.free_pct}%`),
        el('td', {}, loadStatusBadge(m.status),
          m.next_time_off ? el('div', { class: 'ct-muted ct-small' }, `Off ${formatDate(m.next_time_off.start_date)}–${formatDate(m.next_time_off.end_date)}`) : null),
        el('td', { class: 'ct-small' },
          m.initiatives.length ? m.initiatives.map((i, n) => [n ? ', ' : '', el('a', { href: `/pages/item.html?id=${i.id}` }, i.title)]) : el('span', { class: 'ct-muted' }, '—'),
          m.hidden_items ? el('div', { class: 'ct-muted', title: 'Work outside your area also counts in this person\'s load' }, `+${m.hidden_items} you cannot open`) : null),
        el('td', {}, count('actions')),
        el('td', {}, m.backlog_days ?? '—'),
        el('td', {}, count('overdue')),
        canManagePeople ? el('td', {}, el('div', { class: 'ct-stack', style: { gap: '4px' } },
          el('button', { class: 'ct-btn ct-btn--sm', onClick: () => openTimeOff(m.person, () => render(team.unit.id)) }, 'Time off'),
          el('button', { class: 'ct-btn ct-btn--sm ct-btn--ghost', onClick: () => editProfile(m.person, () => render(team.unit.id)) }, 'Capacity'))) : null);
    }))))
    : createEmptyState({ title: skillFilter ? 'Nobody here has that skill' : 'Nobody in this unit yet', icon: 'users' });

  const weeksSlot = el('div', {}, el('p', { class: 'ct-muted ct-small' }, 'Loading…'));
  api.get('/capacity/timeline', { unit_id: team.unit.id, weeks: 8 }).then((t) => {
    if (!t.people.length) { weeksSlot.replaceChildren(el('p', { class: 'ct-muted ct-small' }, 'Nobody to show.')); return; }
    weeksSlot.replaceChildren(el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
      el('thead', {}, el('tr', {}, el('th', { scope: 'col' }, 'Person'),
        el('th', { scope: 'col' }, el('div', { class: 'ct-weeks-head' }, t.weeks.map((w) => el('span', {}, new Date(`${w}T00:00:00`).toLocaleDateString(undefined, { day: '2-digit', month: 'short' }))))))),
      el('tbody', {}, t.people.map((p) => el('tr', {}, el('td', {}, p.person.full_name), el('td', { style: { minWidth: '360px' } }, createWeekStrip(p.weeks))))))));
  }).catch(() => weeksSlot.replaceChildren(el('p', { class: 'ct-muted ct-small' }, 'The weekly view is not available.')));

  const subunits = team.subunits.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
    el('thead', {}, el('tr', {}, ['Unit', 'Progress', 'Capacity used', 'Free (pts)', 'Open', 'Overdue', 'Red'].map((h) => el('th', { scope: 'col' }, h)))),
    el('tbody', {}, team.subunits.map((s) => el('tr', {},
      el('td', {}, el('button', { class: 'ct-link-button', type: 'button', onClick: () => render(s.unit.id) }, s.unit.name)),
      el('td', { style: { minWidth: '160px' } }, createProgressBar(s.progress)),
      el('td', { style: { minWidth: '150px' }, title: `${s.capacity.load_pct} of ${s.capacity.usable_pct} usable points, ${s.capacity.people} people` },
        createProgressBar(s.capacity.load_pct, { max: s.capacity.usable_pct || 1, suffix: ` / ${s.capacity.usable_pct}` })),
      el('td', {}, String(s.capacity.free_pct)),
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
    el('div', { class: 'ct-toolbar' }, skillPicker,
      el('span', { class: 'ct-muted ct-small' }, `Usable capacity = ${team.usable_pct}% for full time (buffer ${team.buffer_pct}% for unplanned work); less for part time and time off`)),
    el('div', { id: 'people' }, card('Team & capacity', members,
      el('span', { class: 'ct-muted ct-small' }, 'Allocation on open work today'))),
    card('Next 8 weeks', weeksSlot, el('span', { class: 'ct-muted ct-small' }, 'Allocated % per week · dates of assignments and time off count')),
    subunits ? card('Units below', subunits) : null,
    card('Overdue work', overdue.element, el('a', { class: 'ct-small', href: portfolioUrl(team.overdue_filters) }, 'Open in Portfolio')),
  ].filter(Boolean));
}

// ------------------------------------------------------------------ time off and capacity profile
function openTimeOff(person, onDone) {
  const list = el('div', {}, el('p', { class: 'ct-muted ct-small' }, 'Loading…'));
  const load = () => api.get('/time-off', { person_id: person.id, current: '1' }).then((d) => {
    list.replaceChildren(d.items.length ? el('ul', { class: 'ct-change-list' }, d.items.map((t) => el('li', {},
      t.kind_id ? lookupBadge(t.kind_id) : null, ` ${formatDate(t.start_date)} – ${formatDate(t.end_date)}`, t.note ? el('span', { class: 'ct-muted' }, ` · ${t.note}`) : null,
      t.can_edit ? [' ', el('button', { class: 'ct-link-button ct-small', type: 'button', onClick: async () => {
        await api.del(`/time-off/${t.id}`, { reason: 'Time off removed' }).catch(showError); load(); onDone();
      } }, 'Remove')] : null)))
      : el('p', { class: 'ct-muted ct-small' }, 'No time off coming up.'));
  }).catch(showError);
  load();
  const modal = openModal({ title: `Time off · ${person.full_name}`, body: list, actions: [
    { label: 'Close' },
    { label: 'Add time off', variant: 'primary', onClick: () => {
      modal.close();
      openFormModal({
        title: `Add time off · ${person.full_name}`, wide: false,
        fields: [
          { key: 'start_date', label: 'First day', type: 'date', required: true },
          { key: 'end_date', label: 'Last day', type: 'date', required: true },
          { key: 'kind_id', label: 'Kind', type: 'select', options: lookupOptions('time_off_type') },
          { key: 'note', label: 'Note', type: 'text' },
        ],
        onSubmit: (v) => api.post('/time-off', { ...v, person_id: person.id }),
        onDone: () => { showToast('Time off saved', 'success'); onDone(); openTimeOff(person, onDone); },
      });
    } },
  ] });
}

async function editProfile(person, onDone) {
  let p;
  try { p = await api.get(`/people/${person.id}`); } catch (err) { showError(err); return; }
  openFormModal({
    title: `Capacity · ${p.full_name}`,
    fields: [
      { key: 'skill_ids', label: 'Skills', type: 'checkboxes', options: lookupOptions('skill') },
      { key: 'capacity_pct', label: 'Working capacity %', type: 'number', help: '100 = full time; 50 = half time.' },
      { key: 'backlog_days', label: 'Estimated backlog (person-days)', type: 'number' },
      { key: 'reason', label: 'Reason for change', full: true },
    ],
    values: p,
    onSubmit: (v) => api.patch(`/people/${p.id}`, { ...v, version: p.version }),
    onDone: () => { showToast('Capacity saved', 'success'); onDone(); },
  });
}

render(new URLSearchParams(location.search).get('unit'));
