/** Work item workspace (/pages/item.html?id=…&tab=people): header, KPIs and tabs for
 *  details, work breakdown (children + timeline), people (owners and assignments) and history. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, refreshApprovalCount } from '../core/layout.js';
import { customFields, lookupBadge, lookupOptions, lookupValue, lookupValues } from '../core/lookups.js';
import { el, formatDate, formatDateTime, formatValue, humanize } from '../core/utils.js';
import { approvalBadge, createStepTracker, openComplete, openReview, openWithdraw, waitingOn } from '../components/approval.js';
import { customValueNode } from '../components/custom-fields.js';
import { createFindings, healthBadge } from '../components/health.js';
import { createDataTable } from '../components/data-table.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { createKpis } from '../components/kpi.js';
import { createPersonCell } from '../components/person.js';
import { createProgressBar } from '../components/progress-bar.js';
import { createTabs } from '../components/tabs.js';
import { createAdoptionChecklist } from '../components/adoption.js';
import { loadColor } from '../components/capacity.js';
import { createGantt } from '../components/gantt.js';
import { showError, showToast } from '../components/toast.js';
import { createWorkTable, overdueBadge, safeLink } from '../components/work-table.js';
import { openNewWorkItem, openWorkItemEditor } from '../components/work-item-form.js';
import { createToolGrid } from '../components/tools.js';

const { content } = await initLayout({ active: 'work', title: 'Work item', permission: 'work.view' });
const params = new URLSearchParams(location.search);
const itemId = Number(params.get('id'));

async function load() {
  try {
    return await api.get(`/work-items/${itemId}`);
  } catch (err) {
    content.replaceChildren(createEmptyState({
      title: err.status === 404 ? 'Item not found' : 'Could not load this item',
      message: err.status === 404 ? 'It may have been deleted, or it is outside the work you can see.' : err.message,
      action: el('a', { class: 'ct-btn', href: '/pages/work.html' }, 'Back to Portfolio'),
    }));
    return null;
  }
}

async function render(tab) {
  const item = await load();
  if (!item) return;
  document.title = `${item.code} ${item.title} · Control Tower`;
  document.querySelector('.ct-topbar__title').textContent = `${item.code} · ${item.title}`;
  const perms = item.permissions;
  let currentTab = tab || params.get('tab') || 'details';
  const reload = (t) => render(t ?? currentTab);

  const approval = item.approval;
  const actions = [
    approval?.status === 'pending' ? el('button', { class: 'ct-btn', onClick: () => openReview(approval.id, { onDone: () => { reload('approvals'); refreshApprovalCount(); } }) },
      icon('check', { size: 16 }), 'Approval') : null,
    perms.can_complete ? el('button', { class: 'ct-btn', onClick: () => openComplete(item, { onDone: () => reload(item.child_count ? null : 'approvals') }) }, icon('check', { size: 16 }), 'Mark complete') : null,
    perms.can_edit ? el('button', { class: 'ct-btn', onClick: () => openWorkItemEditor({ item, onDone: () => reload() }) }, icon('edit', { size: 16 }), 'Edit') : null,
    perms.can_add_child ? el('button', { class: 'ct-btn ct-btn--primary', onClick: () => openNewWorkItem({ parent: item, onDone: () => reload('children') }) }, icon('plus', { size: 16 }), 'Add child') : null,
    perms.can_add_child ? el('button', { class: 'ct-btn', title: 'Add a ready-made breakdown under this item', onClick: () => addFromTemplate(item, () => reload('children')) }, icon('copy', { size: 16 }), 'From template') : null,
    el('button', { class: 'ct-btn', title: 'Reuse this item and its breakdown later', onClick: () => saveAsTemplate(item) }, 'Save as template'),
    perms.can_delete ? el('button', { class: 'ct-btn ct-btn--danger', onClick: () => remove(item) }, icon('trash', { size: 16 }), 'Delete') : null,
  ];

  const header = el('div', { class: 'ct-stack', style: { gap: '8px' } },
    el('nav', { class: 'ct-breadcrumb', 'aria-label': 'Breadcrumb' },
      el('a', { href: '/pages/work.html' }, 'Portfolio'),
      item.ancestors.map((a) => [el('span', { class: 'ct-breadcrumb__sep' }, '/'),
        a.id ? el('a', { href: `/pages/item.html?id=${a.id}` }, `${a.code} ${a.title}`) : el('span', { title: a.title }, a.code)])),
    el('div', { class: 'ct-detail-head' },
      el('div', { class: 'ct-stack', style: { gap: '6px' } },
        el('div', { class: 'ct-detail-head__title' },
          el('span', { class: 'ct-work-title__code' }, item.code),
          el('h1', {}, item.title)),
        el('div', { class: 'ct-tag-list' }, healthBadge(item.health), lookupBadge(item.item_type_id), lookupBadge(item.status_id),
          item.priority_id ? lookupBadge(item.priority_id) : null, item.category_id ? lookupBadge(item.category_id) : null,
          item.action_type_id ? lookupBadge(item.action_type_id) : null, item.severity_id ? lookupBadge(item.severity_id) : null,
          overdueBadge(item), approvalBadge(item.approval_status))),
      el('div', { class: 'ct-actions' }, actions)),
    approval?.status === 'pending' ? el('div', { class: 'ct-notice' },
        el('span', { class: 'ct-notice__text' }, `Marked complete. Step ${approval.current_step} of ${approval.step_count} (${approval.step_name}) is waiting on `,
          el('strong', {}, approval.current_approver?.full_name || (approval.current_role ? `anyone with the ${approval.current_role} role` : 'nobody yet')),
          approval.waiting_note ? ` · ${approval.waiting_note}` : '', '. It counts towards progress once approved.')) : null,
    approval?.status === 'rejected' && item.approval_status === 'rejected' ? el('div', { class: 'ct-notice', style: { borderLeftColor: 'var(--ct-danger)' } },
      el('span', { class: 'ct-notice__text' }, 'Approval was refused and the item was sent back. See the Approvals tab for the note.')) : null);

  const peopleCount = await api.get(`/work-items/${item.id}/assignments`).then((d) => d.items.length).catch(() => '—');
  const kpis = createKpis([
    { value: `${item.progress}%`, label: item.child_count ? 'Progress (approved work below)' : 'Progress (counts once approved)' },
    { value: item.child_count, label: 'Child items', onClick: () => tabs.select('children') },
    { value: item.overdue_children, label: 'Overdue child items', color: item.overdue_children ? 'var(--ct-danger)' : null, onClick: () => tabs.select('children') },
    { value: peopleCount, label: 'People assigned', onClick: () => tabs.select('people') },
    { value: formatDate(item.planned_end), label: 'Target', color: item.is_overdue ? 'var(--ct-danger)' : null },
  ]);

  const tabs = createTabs({
    tabs: [
      { key: 'details', label: 'Details', render: () => detailsTab(item) },
      { key: 'children', label: `Work breakdown (${item.child_count})`, render: () => childrenTab(item, reload) },
      { key: 'people', label: 'People', render: () => peopleTab(item, reload) },
      { key: 'approvals', label: 'Approvals', render: () => approvalsTab(item, reload) },
      { key: 'tools', label: 'Tools', render: () => toolsTab(item, reload) },
      { key: 'history', label: 'History', render: () => historyTab(item) },
    ],
    active: currentTab,
    onChange: (key) => {
      currentTab = key;
      const next = new URLSearchParams(location.search);
      next.set('tab', key);
      history.replaceState(null, '', `?${next}`);
    },
  });

  content.replaceChildren(header, kpis, el('section', { class: 'ct-card' }, tabs.element));
}

// ------------------------------------------------------------------ details
function detailsTab(item) {
  const kv = (label, value) => [el('dt', {}, label), el('dd', {}, value ?? '—')];
  const people = (list) => (list.length ? el('div', { class: 'ct-stack', style: { gap: '4px' } }, list.map((p) => createPersonCell(p, p.job_title))) : '—');
  const prose = (title, text) => (text ? [el('h4', { class: 'ct-section-title' }, title), el('p', { class: 'ct-prose' }, text)] : null);
  const fields = customFields('work_item').filter((f) => !f.item_type_ids?.length || f.item_type_ids.includes(item.item_type_id));
  const h = item.health;
  const healthPanel = el('section', { class: 'ct-stack', style: { gap: '8px', marginBottom: '24px' } },
    el('h4', { class: 'ct-section-title', style: { marginTop: 0 } }, 'Why it has this health ', healthBadge(h)),
    h?.code ? createFindings(h.findings, { empty: 'No rule found a problem: on track.' })
      : el('p', { class: 'ct-muted ct-small' }, h?.reason || 'Not assessed.'),
    h?.findings?.some((f) => f.kind === 'data_quality') ? [el('h4', { class: 'ct-section-title' }, 'Data-quality flags'),
      createFindings(h.findings, { kind: 'data_quality' })] : null,
    h?.findings?.some((f) => f.kind === 'signal') ? [el('h4', { class: 'ct-section-title' }, 'Signals (do not change the health)'),
      createFindings(h.findings, { kind: 'signal' })] : null);
  return el('div', {},
    healthPanel,
    el('div', { class: 'ct-grid-2' },
      el('dl', { class: 'ct-kv' },
        kv('Accountable', el('div', { class: 'ct-stack', style: { gap: '2px' } }, createPersonCell(item.accountable, item.accountable?.job_title),
          el('span', { class: 'ct-muted ct-small' }, item.parent ? (item.owner_overridden ? 'Set for this item (differs from the parent\'s)' : 'Inherited from the parent') : ''))),
        kv('Responsible', people(item.responsibles)),
        kv('Unit', item.unit?.name),
        kv('Function', item.function?.name),
        kv('Parent', item.parent ? el('a', { href: `/pages/item.html?id=${item.parent.id}` }, `${item.parent.code} ${item.parent.title}`) : 'None (top level)')),
      el('dl', { class: 'ct-kv' },
        kv('Planned', `${formatDate(item.planned_start)} → ${formatDate(item.planned_end)}`),
        kv('Actual', `${formatDate(item.actual_start)} → ${formatDate(item.actual_end)}`),
        kv('Progress', el('div', { style: { maxWidth: '240px' } }, createProgressBar(item.progress))),
        kv('Evidence', safeLink(item.evidence_url)),
        kv('Depends on', item.dependencies.length ? el('div', { class: 'ct-stack', style: { gap: '4px' } }, item.dependencies.map((d) =>
          el('span', {}, el('a', { href: `/pages/item.html?id=${d.id}` }, `${d.code} ${d.title}`), ' ', lookupBadge(d.status_id)))) : '—'),
        fields.map((f) => kv(f.label, customValueNode(f, item))),
        kv('Last updated', formatDateTime(item.updated_at)))),
    !item.parent_id || item.adoption_stage_ids?.length ? [el('h4', { class: 'ct-section-title' }, 'Adoption'),
      createAdoptionChecklist(item, { editable: item.permissions.level === 'manage', onSaved: () => render('details') })] : null,
    prose('Description', item.description), prose('Business objective', item.objective),
    prose(lookupValue(item.item_type_id)?.code === 'action' ? 'Impact' : 'Key risks', item.risks), prose('Remarks', item.remarks));
}

// ------------------------------------------------------------------ children
function childrenTab(item, reload) {
  const wrap = el('div', { class: 'ct-stack' });
  const timelineSlot = el('div');
  api.get('/work-items', { parent_id: item.id, per_page: 200, sort: 'planned_end' }).then(async (data) => {
    const ids = data.items.map((i) => i.id).join(',');
    const links = ids ? (await api.get('/work-items/dependencies', { ids }).catch(() => ({ items: [] }))).items : [];
    const milestone = lookupValues('item_type').find((t) => t.code === 'milestone')?.id;
    const timeline = createGantt(data.items, {
      links,
      isMilestone: (i) => i.item_type_id === milestone,
      label: (i) => `${i.code} ${i.title}`,
      color: (i) => (i.is_overdue ? 'var(--ct-danger)' : lookupValue(i.status_id)?.color),
      onClick: (i) => { location.href = `/pages/item.html?id=${i.id}`; },
    });
    timelineSlot.replaceChildren(timeline || el('p', { class: 'ct-muted ct-small' }, 'The timeline appears once child items have planned dates.'));
  }).catch(showError);
  wrap.append(
    el('div', { class: 'ct-detail-head' },
      el('p', { class: 'ct-muted ct-small' }, 'Items directly under this one. Open an item to break it down further.'),
      item.permissions.can_add_child ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => openNewWorkItem({ parent: item, onDone: () => reload('children') }) }, icon('plus', { size: 14 }), 'Add child') : null),
    timelineSlot,
    el('div', { class: 'ct-card', style: { boxShadow: 'none', border: '1px solid var(--ct-border)' } },
      createWorkTable({
        params: { parent_id: item.id },
        columns: ['item_short', 'type', 'health', 'status', 'responsible', 'progress', 'planned_end'],
        defaultSort: 'planned_end',
        emptyState: { title: 'No child items yet', message: item.permissions.can_add_child ? 'Use “Add child” to delegate parts of this work.' : '' },
      }).element));
  return wrap;
}

// ------------------------------------------------------------------ people
function peopleTab(item, reload) {
  const wrap = el('div', { class: 'ct-stack' });
  const canAssign = item.permissions.can_assign;
  const tableSlot = el('div');

  async function loadAssignments() {
    try {
      const { items } = await api.get(`/work-items/${item.id}/assignments`);
      if (!items.length) {
        tableSlot.replaceChildren(createEmptyState({ title: 'Nobody assigned yet', icon: 'users',
          message: canAssign ? 'Assign people with a role and an allocation %, so workload adds up across all their work.' : '' }));
        return;
      }
      const total = items.reduce((s, a) => s + a.allocation_pct, 0);
      tableSlot.replaceChildren(el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
        el('thead', {}, el('tr', {}, ['Person', 'Role', 'Allocation here', 'Total load today', 'Dates', 'Duties', ''].map((h) => el('th', {}, h)))),
        el('tbody', {}, items.map((a) => el('tr', {},
          el('td', {}, createPersonCell(a.person, a.person.job_title)),
          el('td', {}, lookupBadge(a.role_id)),
          el('td', { class: 'ct-progress-cell' }, createProgressBar(a.allocation_pct)),
          el('td', {}, loadCell(a.person_load)),
          el('td', { class: 'ct-small' }, a.start_date || a.end_date ? `${formatDate(a.start_date)} → ${formatDate(a.end_date)}` : 'Whole item'),
          el('td', { class: 'ct-small ct-prose' }, a.duties || '—'),
          el('td', {}, canAssign ? el('div', { class: 'ct-actions' },
            el('button', { class: 'ct-btn ct-btn--sm', onClick: () => editAssignment(a) }, 'Edit'),
            el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', onClick: () => removeAssignment(a) }, 'Remove')) : null)))),
        el('tfoot', {}, el('tr', {}, el('td', { colspan: 2, class: 'ct-muted ct-small' }, 'Total on this item'), el('td', {}, `${total}%`), el('td', { colspan: 4 }))))));
    } catch (err) { showError(err); }
  }

  function loadCell(load) {
    if (!load) return '—';
    const over = load.pct > 100;
    return el('span', { class: over ? 'ct-text-danger' : null, title: `${load.items} open item(s)` }, `${load.pct}%`, over ? ' (over 100%)' : '');
  }

  /** Who could take this on: people in the item's unit, most free capacity first (skills optional). */
  function suggestionsPanel(onPick) {
    const list = el('div', { class: 'ct-suggestions' }, el('p', { class: 'ct-muted ct-small' }, 'Loading suggestions…'));
    const skill = el('select', { class: 'ct-select', 'aria-label': 'Skill', style: { maxWidth: '220px' }, onChange: () => load() },
      el('option', { value: '' }, 'Any skill'), lookupOptions('skill').map((o) => el('option', { value: o.value }, o.label)));
    const load = () => api.get(`/work-items/${item.id}/assignment-suggestions`, { skill_ids: skill.value }).then((d) => {
      list.replaceChildren(...(d.items.length ? d.items.map((r) => el('div', { class: 'ct-suggestion' },
        el('div', {}, createPersonCell(r.person, [r.person.job_title, r.skill_ids.map((id) => lookupValue(id)?.label).filter(Boolean).join(', ')].filter(Boolean).join(' · '))),
        el('div', { title: `${r.load_pct}% allocated of ${r.usable_pct}% usable` }, createProgressBar(r.load_pct, { color: loadColor(r.status) }),
          el('div', { class: 'ct-muted ct-small' }, `${r.free_pct}% free`)),
        el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: () => onPick(r.person) }, 'Choose')))
        : [el('p', { class: 'ct-muted ct-small' }, 'Nobody in this unit has the skill and is available.')]));
    }).catch(() => list.replaceChildren(el('p', { class: 'ct-muted ct-small' }, 'Suggestions are not available.')));
    load();
    return el('div', { class: 'ct-field ct-field--full' },
      el('div', { class: 'ct-detail-head' }, el('span', { class: 'ct-label' }, 'Suggested (most free capacity first)'), skill), list);
  }

  function assignmentForm(existing, preset = null) {
    const loadNote = el('div', { class: 'ct-field__help' }, existing ? '' : 'Pick a person to see their current load.');
    const showLoad = async (person) => {
      if (!person) { loadNote.textContent = ''; return; }
      const data = await api.get('/assignments/load', { person_ids: person.id }).catch(() => null);
      const load = data?.items?.[String(person.id)];
      loadNote.textContent = load ? `${person.full_name} is allocated ${load.pct}% today across ${load.items} open item(s).` : '';
    };
    if (existing) showLoad(existing.person);
    const modal = openFormModal({
      title: existing ? `Assignment · ${existing.person.full_name}` : `Assign a person to ${item.code}`,
      fields: [
        { key: 'person_id', label: 'Person', type: 'person', required: true, value: existing?.person || preset, onChange: showLoad, full: true },
        { key: 'role_id', label: 'Functional role', type: 'select', options: lookupOptions('functional_role', existing?.role_id) },
        { key: 'allocation_pct', label: 'Allocation %', type: 'number', required: true, help: 'Share of their time on this item.' },
        { key: 'start_date', label: 'From', type: 'date', help: 'Empty = from now.' },
        { key: 'end_date', label: 'Until', type: 'date', help: 'Empty = until the item closes.' },
        { key: 'duties', label: 'Duties', type: 'textarea' },
        existing ? { key: 'reason', label: 'Reason for change', full: true } : null,
      ].filter(Boolean),
      values: existing || { allocation_pct: 20 },
      submitLabel: existing ? 'Save' : 'Assign',
      onSubmit: (v) => (existing
        ? api.patch(`/assignments/${existing.id}`, { ...v, version: existing.version })
        : api.post(`/work-items/${item.id}/assignments`, v)),
      onDone: () => { showToast(existing ? 'Assignment updated' : 'Person assigned', 'success'); reload('people'); },
    });
    modal.element.querySelector('.ct-picker')?.closest('.ct-field')?.append(loadNote);
    if (preset) showLoad(preset);
    if (!existing) {
      modal.element.querySelector('.ct-picker')?.closest('.ct-field')?.after(
        suggestionsPanel((person) => { modal.close(); assignmentForm(null, person); }));
    }
  }
  const editAssignment = (a) => assignmentForm(a);

  async function removeAssignment(a) {
    askReason({
      title: `Remove ${a.person.full_name}?`,
      message: `Their ${a.allocation_pct}% allocation on ${item.code} stops counting towards their workload.`,
      confirmLabel: 'Remove',
      onConfirm: (reason) => api.del(`/assignments/${a.id}`, { reason }),
      onDone: () => { showToast('Assignment removed', 'success'); reload('people'); },
    });
  }

  wrap.append(
    el('div', { class: 'ct-grid-2' },
      el('div', {}, el('h4', { class: 'ct-section-title' }, 'Accountable owner'), createPersonCell(item.accountable, item.accountable?.job_title)),
      el('div', {}, el('h4', { class: 'ct-section-title' }, 'Responsible owners'),
        el('div', { class: 'ct-stack', style: { gap: '6px' } }, item.responsibles.map((p) => createPersonCell(p, p.job_title))))),
    el('div', { class: 'ct-detail-head' },
      el('h4', { class: 'ct-section-title' }, 'Assigned people'),
      canAssign ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => assignmentForm(null) }, icon('plus', { size: 14 }), 'Assign person') : null),
    tableSlot);
  loadAssignments();
  return wrap;
}

// ------------------------------------------------------------------ approvals
function approvalsTab(item, reload) {
  const wrap = el('div', { class: 'ct-stack' }, el('p', { class: 'ct-muted' }, 'Loading…'));
  api.get('/approvals', { box: 'item', work_item_id: item.id, per_page: 20 }).then((data) => {
    if (!data.items.length) {
      wrap.replaceChildren(createEmptyState({ title: 'No approvals yet', icon: 'check',
        message: 'When this item is marked complete, it goes through its approval chain (if one applies to this type of work).' }));
      return;
    }
    const done = () => { reload('approvals'); refreshApprovalCount(); };
    wrap.replaceChildren(...data.items.map((r, i) => el('section', { class: 'ct-card', style: { boxShadow: 'none', border: '1px solid var(--ct-border)' } },
      el('div', { class: 'ct-card__header' },
        el('div', {}, el('h3', { class: 'ct-card__title' }, i === 0 ? 'Latest approval' : `Earlier approval`, ' ', approvalBadge(r.status)),
          el('p', { class: 'ct-muted ct-small' }, `${r.chain_name} · marked complete by ${r.submitted_by?.full_name || 'the system'} on ${formatDate(r.submitted_at)}`,
            r.status === 'pending' ? ` · waiting on ${waitingOn(r)}` : '')),
        el('div', { class: 'ct-actions' },
          r.can_decide ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => openReview(r.id, { onDone: done }) }, 'Review') : null,
          r.can_retry ? el('button', { class: 'ct-btn ct-btn--sm', onClick: async () => { try { await api.post(`/approvals/${r.id}/retry`, {}); done(); } catch (err) { showError(err); } } }, 'Look for an approver again') : null,
          r.can_withdraw ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', onClick: () => openWithdraw(r, { onDone: done }) }, 'Withdraw') : null)),
      el('div', { class: 'ct-card__body' }, createStepTracker(r)))));
  }).catch((err) => { wrap.replaceChildren(createEmptyState({ title: 'Could not load approvals', message: err.message })); });
  return wrap;
}

// ------------------------------------------------------------------ history
const LOOKUP_FIELDS = new Set(['status_id', 'priority_id', 'category_id', 'item_type_id', 'action_type_id', 'severity_id', 'role_id']);

function historyValue(field, value) {
  if (value !== null && value !== undefined && LOOKUP_FIELDS.has(field)) return lookupBadge(value);
  return formatValue(value);
}

const HISTORY_PREFIX = { assignment: 'Assignment ', tool_response: 'Checklist ' };

// ------------------------------------------------------------------ tools
/** Tools that apply to this item: links open (logged), forms and checklists save to it. */
function toolsTab(item, reload) {
  const slot = el('div', {}, el('p', { class: 'ct-muted' }, 'Loading tools…'));
  api.get('/tools', { work_item_id: item.id }).then((data) => {
    slot.replaceChildren(data.items.length
      ? el('div', { class: 'ct-stack' },
        el('p', { class: 'ct-muted ct-small' }, 'Tools for this item. Opening a tool is recorded; forms and checklists save here and show in History.'),
        createToolGrid(data.items, { item, onChanged: () => reload('tools') }))
      : createEmptyState({ title: 'No tools for this item', message: 'Tools linked to this item, its unit or its type appear here.', icon: 'grid' }));
  }).catch((err) => slot.replaceChildren(createEmptyState({ title: 'Could not load tools', message: err.message })));
  return slot;
}

function historyTab(item) {
  return createDataTable({
    columns: [
      { key: 'occurred_at', label: 'When', render: (e) => formatDateTime(e.occurred_at) },
      { key: 'actor_name', label: 'Who', render: (e) => e.actor_name || 'System' },
      { key: 'what', label: 'What', render: (e) => `${HISTORY_PREFIX[e.entity_type] || ''}${e.field ? humanize(e.field.replace(/_id(s)?$/, '$1')) : humanize(e.operation)}` },
      { key: 'change', label: 'Change', render: (e) => (e.field
        ? el('span', {}, el('span', { class: 'ct-diff-old' }, historyValue(e.field, e.old_value)), ' → ', el('span', { class: 'ct-diff-new' }, historyValue(e.field, e.new_value)))
        : e.operation === 'create' ? 'Created' : humanize(e.operation)) },
      { key: 'reason', label: 'Reason', render: (e) => e.reason || '—' },
    ],
    fetchPage: (q) => api.get(`/work-items/${item.id}/history`, q),
    pageSize: 20,
    emptyState: { title: 'No history yet', icon: 'history' },
  }).element;
}

// ------------------------------------------------------------------ delete
function remove(item) {
  askReason({
    title: `Delete ${item.code}?`,
    message: 'The item disappears from lists but stays in the audit history. Assignments on it stop counting.',
    confirmLabel: 'Delete',
    onConfirm: (reason) => api.del(`/work-items/${item.id}`, { reason }),
    onDone: () => {
      showToast(`${item.code} deleted`, 'success');
      location.href = item.parent ? `/pages/item.html?id=${item.parent.id}&tab=children` : '/pages/work.html';
    },
  });
}

/** Confirmation that records why (the reason goes to the audit log). */
function askReason({ title, message, confirmLabel, onConfirm, onDone }) {
  openFormModal({
    title, wide: false, intro: message, submitLabel: confirmLabel,
    fields: [{ key: 'reason', label: 'Reason', required: true, full: true, help: 'Saved in the audit log.' }],
    onSubmit: (v) => onConfirm(v.reason),
    onDone,
  });
}

if (!itemId) {
  content.append(createEmptyState({ title: 'No item selected', action: el('a', { class: 'ct-btn', href: '/pages/work.html' }, 'Open Portfolio') }));
} else {
  render();
}

// ------------------------------------------------------------------ templates (Phase 10)
function saveAsTemplate(item) {
  openFormModal({
    title: `Save ${item.code} as a template`,
    intro: 'The item and everything under it that you can see is saved with its timing (days from its start), not its people or status.',
    fields: [
      { key: 'name', label: 'Template name', required: true, full: true },
      { key: 'description', label: 'Description', type: 'textarea' },
    ],
    values: { name: item.title },
    onSubmit: (v) => api.post('/templates/from-item', { work_item_id: item.id, ...v }),
    onDone: (t) => showToast(`Saved as template “${t.name}” (${t.node_count} items)`, 'success'),
  });
}

async function addFromTemplate(item, onDone) {
  let templates;
  try { templates = (await api.get('/templates', { per_page: 100 })).items; } catch (err) { showError(err); return; }
  if (!templates.length) { showToast('No templates yet. Save one from an item, or make one under Templates.', 'info'); return; }
  openFormModal({
    title: `Add from a template under ${item.code}`,
    fields: [
      { key: 'template', label: 'Template', type: 'select', required: true, options: templates.map((t) => ({ value: t.id, label: `${t.name} (${t.node_count} items)` })), full: true },
      { key: 'start_date', label: 'Start date', type: 'date', help: 'The template\'s dates count from this day.' },
      { key: 'title', label: 'Name of the top item (optional)' },
    ],
    values: { start_date: item.planned_start },
    submitLabel: 'Add',
    onSubmit: (v) => api.post(`/templates/${v.template}/use`, { parent_id: item.id, start_date: v.start_date || null, title: v.title || null }),
    onDone: (res) => { showToast(`Added ${res.items.map((i) => i.code).join(', ')}`, 'success'); onDone(); },
  });
}
