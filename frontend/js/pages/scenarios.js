/** What-if scenarios (/pages/scenarios.html): plan changes to dates, owners, status and people, see the
 *  effect on the schedule and on everyone's capacity week by week, then apply them all at once (or not).
 *  Nothing changes live data until "Apply"; applying re-checks every change and is one audited action.
 *  ?id=<scenario> opens one scenario. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge, lookupOptions } from '../core/lookups.js';
import { el, formatDate, formatDateTime } from '../core/utils.js';
import { createDataTable } from '../components/data-table.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog, openModal } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';
import { pickWorkItem } from '../components/work-picker.js';

const { content } = await initLayout({ active: 'scenarios', title: 'What-if scenarios', permission: 'scenarios.use' });
const id = Number(new URLSearchParams(location.search).get('id')) || null;

const STATUS = { draft: ['Draft', ''], applied: ['Applied', 'is-good'], discarded: ['Discarded', 'is-bad'] };
const statusPill = (s) => el('span', { class: `ct-status-pill ${STATUS[s]?.[1] || ''}` }, STATUS[s]?.[0] || s);
const FIELD = {
  planned_start: 'Planned start', planned_end: 'Planned finish', status_id: 'Status', priority_id: 'Priority',
  accountable_id: 'Accountable', unit_id: 'Unit', weight: 'Weight', person_id: 'Person', allocation_pct: 'Allocation %',
  start_date: 'From', end_date: 'To', role_id: 'Role',
};
const KIND = { item: 'Change work', assignment: 'Change assignment', new_assignment: 'Add person', remove_assignment: 'Remove person' };
const people = {};

function personName(pid) {
  if (!pid) return '—';
  if (!people[pid]) {
    people[pid] = el('span', {}, `person #${pid}`);
    api.get(`/people/${pid}`).then((p) => { people[pid].textContent = p.full_name; }).catch(() => {});
  }
  return people[pid].cloneNode(true);
}

function show(field, v) {
  if (v === null || v === undefined || v === '') return el('span', { class: 'ct-muted' }, '—');
  if (['status_id', 'priority_id', 'role_id'].includes(field)) return lookupBadge(v);
  if (['planned_start', 'planned_end', 'start_date', 'end_date'].includes(field)) return formatDate(v);
  if (['accountable_id', 'person_id'].includes(field)) return personName(v);
  if (field === 'allocation_pct') return `${v}%`;
  return String(v);
}

if (id) renderScenario(id); else renderList();

// ------------------------------------------------------------------ list
function renderList() {
  const table = createDataTable({
    columns: [
      { key: 'name', label: 'Scenario', render: (s) => el('div', {}, el('strong', {}, s.name), s.description ? el('div', { class: 'ct-muted ct-small' }, s.description) : null) },
      { key: 'status', label: 'Status', render: (s) => statusPill(s.status) },
      { key: 'change_count', label: 'Changes' },
      { key: 'owner', label: 'Owner', render: (s) => s.owner?.full_name || '—' },
      { key: 'updated_at', label: 'Updated', render: (s) => formatDateTime(s.applied_at || s.updated_at) },
    ],
    fetchPage: (q) => api.get('/scenarios', q),
    onRowClick: (s) => { location.href = `?id=${s.id}`; },
    emptyState: { title: 'No scenarios yet', message: 'Plan changes here before making them: see the effect on deadlines and on people\'s capacity first.', icon: 'branch' },
  });
  table.setFilters({});
  content.append(
    pageHeader('What-if scenarios', 'Try out changes to dates, owners and people without touching live work. Apply them when you are happy, all at once.',
      [el('button', { class: 'ct-btn ct-btn--primary', type: 'button', onClick: newScenario }, icon('plus', { size: 16 }), 'New scenario')]),
    el('section', { class: 'ct-card' }, table.element));
}

function newScenario() {
  openFormModal({
    title: 'New scenario',
    fields: [{ key: 'name', label: 'Name', required: true, full: true, placeholder: 'e.g. Delay the beta by two weeks' },
      { key: 'description', label: 'What are you testing?', type: 'textarea' }],
    onSubmit: (v) => api.post('/scenarios', v),
    onDone: (s) => { location.href = `?id=${s.id}`; },
  });
}

// ------------------------------------------------------------------ one scenario
async function renderScenario(scenarioId) {
  let s;
  try { s = await api.get(`/scenarios/${scenarioId}`); } catch (err) {
    content.replaceChildren(createEmptyState({ title: 'Scenario not found', message: err.message, action: el('a', { class: 'ct-btn', href: '/pages/scenarios.html' }, 'All scenarios') }));
    return;
  }
  const editable = s.can_edit;
  const actions = [el('a', { class: 'ct-btn', href: '/pages/scenarios.html' }, 'All scenarios'),
    el('button', { class: 'ct-btn', type: 'button', onClick: () => duplicate(s) }, icon('copy', { size: 16 }), 'Copy')];
  if (editable) {
    actions.push(
      el('button', { class: 'ct-btn', type: 'button', onClick: () => discard(s) }, 'Discard'),
      el('button', { class: 'ct-btn ct-btn--primary', type: 'button', disabled: !s.changes.length, onClick: () => apply(s) }, icon('check', { size: 16 }), 'Apply'));
  }
  const header = pageHeader(s.name, null, actions);
  const meta = el('p', { class: 'ct-muted' }, statusPill(s.status), ` · ${s.change_count} change${s.change_count === 1 ? '' : 's'} · by ${s.owner?.full_name || '—'}`,
    s.applied_at ? ` · applied ${formatDateTime(s.applied_at)}` : '', s.description ? ` · ${s.description}` : '');

  const stale = s.changes.filter((c) => c.stale);
  const changeRows = s.changes.map((c) => {
    const fields = Object.keys(c.changes || {});
    const what = c.kind === 'remove_assignment' ? el('span', {}, 'Remove ', c.person?.full_name || 'person', ' from the work')
      : el('ul', { class: 'ct-change-list', style: { paddingLeft: '16px' } }, fields.map((f) => el('li', {},
        el('strong', {}, FIELD[f] || f), ': ', c.kind === 'new_assignment' ? '' : show(f, c.current[f]), c.kind === 'new_assignment' ? '' : ' → ', show(f, c.changes[f]))));
    return el('tr', { class: c.stale ? 'is-late' : null },
      el('td', {}, c.item ? el('a', { href: `/pages/item.html?id=${c.item.id}` }, `${c.item.code} ${c.item.title}`) : '—',
        c.person && c.kind !== 'new_assignment' ? el('div', { class: 'ct-muted ct-small' }, c.person.full_name) : null),
      el('td', {}, KIND[c.kind] || c.kind, c.stale ? el('div', { class: 'ct-text-danger ct-small' }, 'Changed since planned') : null),
      el('td', {}, what, c.note ? el('div', { class: 'ct-muted ct-small' }, c.note) : null),
      el('td', {}, editable ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', type: 'button', onClick: async () => {
        try { await api.del(`/scenarios/${s.id}/changes/${c.id}`); renderAgain(); } catch (err) { showError(err); }
      } }, 'Remove') : null));
  });
  const changesCard = el('section', { class: 'ct-card' },
    el('div', { class: 'ct-detail-head' }, el('h2', { class: 'ct-section-title' }, 'Planned changes'),
      editable ? el('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
        el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: () => changeItem(s) }, 'Change dates, status or owner'),
        el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: () => addPerson(s) }, 'Add a person'),
        el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: () => changeAssignment(s) }, 'Change or remove someone')) : null),
    stale.length ? el('div', { class: 'ct-notice ct-notice--warning' }, `${stale.length} planned change${stale.length === 1 ? ' is' : 's are'} out of date: the record changed after it was planned. Remove and plan ${stale.length === 1 ? 'it' : 'them'} again before applying.`) : null,
    s.changes.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
      el('thead', {}, el('tr', {}, ['Work', 'Change', 'What', ''].map((h) => el('th', {}, h)))),
      el('tbody', {}, changeRows)))
      : el('p', { class: 'ct-muted' }, 'No changes planned yet. Add one with the buttons above.'));

  const impactSlot = el('div', { class: 'ct-stack' });
  const weeksSelect = el('select', { class: 'ct-select', 'aria-label': 'Weeks to show', onChange: () => loadImpact() },
    [4, 8, 12, 26].map((w) => el('option', { value: w, selected: w === 12 }, `${w} weeks`)));
  const impactCard = el('section', { class: 'ct-card' },
    el('div', { class: 'ct-detail-head' }, el('h2', { class: 'ct-section-title' }, 'Effect'), weeksSelect), impactSlot);

  content.replaceChildren(header, meta, changesCard, impactCard);
  loadImpact();

  async function loadImpact() {
    if (!s.changes.length) { impactSlot.replaceChildren(el('p', { class: 'ct-muted' }, 'Plan a change to see its effect.')); return; }
    impactSlot.replaceChildren(el('p', { class: 'ct-muted' }, 'Working it out…'));
    try {
      const data = await api.get(`/scenarios/${s.id}/impact`, { weeks: weeksSelect.value });
      impactSlot.replaceChildren(scheduleView(data.schedule), capacityView(data.capacity));
    } catch (err) { impactSlot.replaceChildren(el('p', { class: 'ct-text-danger' }, err.message)); }
  }

  function renderAgain() { renderScenario(s.id); }
  s.reload = renderAgain;
}

function scheduleView(problems) {
  return el('div', {},
    el('h3', { class: 'ct-section-title' }, 'Schedule'),
    problems.length ? el('ul', { class: 'ct-change-list' }, problems.map((p) => el('li', { class: 'ct-text-danger' }, p.message)))
      : el('p', { class: 'ct-muted' }, 'No clashes with dependencies, parent dates or past dates.'));
}

function capacityView(rows) {
  if (!rows.length) return el('div', {}, el('h3', { class: 'ct-section-title' }, 'Capacity'), el('p', { class: 'ct-muted' }, 'Nobody\'s allocation changes.'));
  const weeks = rows[0].weeks.map((w) => w.week_start);
  const cell = (w) => el('span', { class: `ct-week-cell is-${w.status_after}`, title: `Before ${w.load_before}% (${w.status_before}) · after ${w.load_after}% of ${w.usable_pct}% usable` },
    w.load_before === w.load_after ? `${w.load_after}%` : `${w.load_before}→${w.load_after}%`);
  const delta = (before, after) => {
    const d = after - before;
    return el('span', { class: `ct-delta ${d > 0 ? 'is-up' : d < 0 ? 'is-down' : ''}` }, d === 0 ? '—' : `${d > 0 ? '+' : ''}${d}`);
  };
  return el('div', {},
    el('h3', { class: 'ct-section-title' }, 'Capacity'),
    el('p', { class: 'ct-muted ct-small' }, 'Load per week before → after, against each person\'s usable capacity (after the buffer). Red = overloaded, amber = under half used, grey = away.'),
    el('div', { class: 'ct-week-grid' }, el('table', {},
      el('thead', {}, el('tr', {}, el('th', {}, 'Person'), el('th', {}, 'Overloaded weeks'), el('th', {}, 'Peak'),
        weeks.map((w) => el('th', {}, formatDate(w))))),
      el('tbody', {}, rows.map((r) => el('tr', {},
        el('td', {}, r.person?.full_name || '—'),
        el('td', {}, `${r.overloaded_weeks_before} → ${r.overloaded_weeks_after} `, delta(r.overloaded_weeks_before, r.overloaded_weeks_after)),
        el('td', {}, `${r.peak_before}% → ${r.peak_after}%`),
        r.weeks.map((w) => el('td', {}, cell(w)))))))));
}

// ------------------------------------------------------------------ adding changes
const clean = (v) => Object.fromEntries(Object.entries(v).filter(([, x]) => x !== null && x !== undefined && x !== ''));

async function addChange(s, body) {
  await api.post(`/scenarios/${s.id}/changes`, body);
  showToast('Added to the scenario', 'success');
  s.reload();
}

async function changeItem(s) {
  const item = await pickWorkItem({ title: 'Which work item?' });
  if (!item) return;
  openFormModal({
    title: `${item.code} · ${item.title}`,
    intro: 'Fill in only what you want to change. Current values are shown.',
    fields: [
      { key: 'planned_start', label: `Planned start (now ${formatDate(item.planned_start) || '—'})`, type: 'date' },
      { key: 'planned_end', label: `Planned finish (now ${formatDate(item.planned_end) || '—'})`, type: 'date' },
      { key: 'status_id', label: 'Status', type: 'select', options: lookupOptions('status', item.status_id) },
      { key: 'priority_id', label: 'Priority', type: 'select', options: lookupOptions('priority', item.priority_id) },
      { key: 'accountable_id', label: `Accountable (now ${item.accountable?.full_name || '—'})`, type: 'person' },
      { key: 'weight', label: `Weight (now ${item.weight})`, type: 'number' },
      { key: 'note', label: 'Note', full: true },
    ],
    values: {},
    submitLabel: 'Add to scenario',
    onSubmit: (v) => {
      const { note, ...rest } = v;
      const changes = clean(rest);
      for (const k of Object.keys(changes)) if (changes[k] === item[k]) delete changes[k];
      return addChange(s, { kind: 'item', target_id: item.id, changes, note });
    },
  });
}

async function addPerson(s) {
  const item = await pickWorkItem({ title: 'Add someone to which work item?' });
  if (!item) return;
  openFormModal({
    title: `Add a person to ${item.code}`,
    fields: [
      { key: 'person_id', label: 'Person', type: 'person', required: true },
      { key: 'allocation_pct', label: 'Allocation %', type: 'number', required: true },
      { key: 'role_id', label: 'Role', type: 'select', options: lookupOptions('functional_role') },
      { key: 'start_date', label: 'From', type: 'date' },
      { key: 'end_date', label: 'To', type: 'date' },
      { key: 'note', label: 'Note', full: true },
    ],
    submitLabel: 'Add to scenario',
    onSubmit: (v) => {
      const { note, ...rest } = v;
      return addChange(s, { kind: 'new_assignment', work_item_id: item.id, changes: clean(rest), note });
    },
  });
}

async function changeAssignment(s) {
  const item = await pickWorkItem({ title: 'Whose assignment? Pick the work item first' });
  if (!item) return;
  let rows;
  try { rows = (await api.get(`/work-items/${item.id}/assignments`)).items; } catch (err) { showError(err); return; }
  if (!rows.length) { showToast(`Nobody is assigned to ${item.code}`, 'info'); return; }
  const modal = openModal({
    title: `People on ${item.code}`,
    body: el('div', { class: 'ct-stack', style: { gap: '8px' } }, rows.map((a) => el('div', { class: 'ct-detail-head' },
      el('span', {}, el('strong', {}, a.person?.full_name), ` · ${a.allocation_pct}%`, a.start_date || a.end_date ? ` · ${formatDate(a.start_date) || '…'} → ${formatDate(a.end_date) || '…'}` : ''),
      el('span', { style: { display: 'flex', gap: '6px' } },
        el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: () => { modal.close(); editAssignment(s, a); } }, 'Change'),
        el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', type: 'button', onClick: async () => {
          modal.close();
          try { await addChange(s, { kind: 'remove_assignment', target_id: a.id }); } catch (err) { showError(err); }
        } }, 'Remove'))))),
    actions: [{ label: 'Cancel' }],
  });
}

function editAssignment(s, a) {
  openFormModal({
    title: `${a.person?.full_name} on this work`,
    intro: 'Fill in only what you want to change.',
    fields: [
      { key: 'allocation_pct', label: `Allocation % (now ${a.allocation_pct}%)`, type: 'number' },
      { key: 'start_date', label: `From (now ${formatDate(a.start_date) || '—'})`, type: 'date' },
      { key: 'end_date', label: `To (now ${formatDate(a.end_date) || '—'})`, type: 'date' },
      { key: 'person_id', label: 'Hand to someone else', type: 'person' },
      { key: 'note', label: 'Note', full: true },
    ],
    submitLabel: 'Add to scenario',
    onSubmit: (v) => {
      const { note, ...rest } = v;
      return addChange(s, { kind: 'assignment', target_id: a.id, changes: clean(rest), note });
    },
  });
}

// ------------------------------------------------------------------ apply, discard, copy
async function apply(s) {
  if (!await confirmDialog({ title: `Apply “${s.name}”?`, message: `${s.change_count} change${s.change_count === 1 ? '' : 's'} will be made to live work, as one action in the audit log. If any of them is no longer possible, none is made.`, confirmLabel: 'Apply' })) return;
  try {
    await api.post(`/scenarios/${s.id}/apply`, {});
    showToast('Scenario applied', 'success');
    s.reload();
  } catch (err) {
    showError(err);
    s.reload();
  }
}

async function discard(s) {
  if (!await confirmDialog({ title: `Discard “${s.name}”?`, message: 'Nothing was changed by this scenario; it is kept for reference as discarded.', confirmLabel: 'Discard', danger: true })) return;
  try { await api.post(`/scenarios/${s.id}/discard`, {}); s.reload(); } catch (err) { showError(err); }
}

async function duplicate(s) {
  try {
    const copy = await api.post(`/scenarios/${s.id}/duplicate`, {});
    showToast('Copied as a new draft', 'success');
    location.href = `?id=${copy.id}`;
  } catch (err) { showError(err); }
}
