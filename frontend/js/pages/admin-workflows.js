/** Approval chains: who must approve completed work before it counts, step by step. Edits are a draft;
 *  publish them from the banner. Requests already running keep the steps they started with. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge, lookupOptions } from '../core/lookups.js';
import { clear, el } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { createSettingsBanner } from '../components/settings-banner.js';
import { showError, showToast } from '../components/toast.js';
import { treeOptions } from '../components/tree.js';

const { content } = await initLayout({ active: 'workflows', title: 'Approval chains', permission: 'settings.manage' });

let chains = [];
let kinds = {};
let missing = {};
let selectedId = Number(new URLSearchParams(location.search).get('chain')) || null;
const [roles, units] = await Promise.all([
  api.get('/roles').then((d) => d.items).catch(() => []),
  api.get('/units').then((d) => d.items).catch(() => []),
]);

const banner = createSettingsBanner({ onChange: load });
const nav = el('ul', { class: 'ct-list', role: 'listbox', 'aria-label': 'Approval chains' });
const detail = el('section', { class: 'ct-card' });

content.append(
  pageHeader('Approval chains',
    'Completed work goes through the most specific chain that matches it: a chain for its unit beats an organisation-wide one, and a chain for its type beats one for every type. Work with no chain counts as finished straight away.',
    [el('button', { class: 'ct-btn ct-btn--primary', onClick: () => editChain(null) }, icon('plus', { size: 16 }), 'New chain')]),
  banner.element,
  el('div', { class: 'ct-split' },
    el('section', { class: 'ct-card' }, el('div', { class: 'ct-card__header' }, el('h3', {}, 'Chains'), el('span', { class: 'ct-muted ct-small' }, 'Steps')), nav),
    detail));

async function load() {
  try {
    const data = await api.get('/approval-chains');
    chains = data.items;
    kinds = data.approver_kinds;
    missing = data.when_missing;
    if (!chains.some((c) => c.id === selectedId)) selectedId = chains[0]?.id ?? null;
    renderNav();
    renderDetail();
  } catch (err) { showError(err); }
  banner.refresh();
}

function renderNav() {
  clear(nav);
  for (const c of chains) {
    nav.append(el('li', {}, el('button', {
      class: `ct-list__item${c.id === selectedId ? ' is-selected' : ''}`, role: 'option', 'aria-selected': String(c.id === selectedId),
      onClick: () => { selectedId = c.id; history.replaceState(null, '', `?chain=${c.id}`); renderNav(); renderDetail(); },
    }, el('span', { class: 'ct-list__label' }, c.name, c.is_active ? '' : ' (retired)'),
    el('span', { class: 'ct-list__meta' }, String(c.steps.filter((s) => s.is_active).length)))));
  }
}

function appliesTo(c) {
  const types = c.item_type_ids.length ? el('span', { class: 'ct-tag-list', style: { display: 'inline-flex' } }, c.item_type_ids.map((id) => lookupBadge(id))) : 'every item type';
  return el('span', {}, 'Applies to ', types, ' in ', c.unit ? el('strong', {}, `${c.unit.name} and the units below it`) : 'the whole organisation');
}

function approverText(s) {
  if (s.approver_kind === 'role') return `${s.approver_kind_label}: ${s.approver_role || '—'}`;
  if (s.approver_kind === 'person') return `${s.approver_kind_label}: ${s.approver_person?.full_name || '—'}`;
  return s.approver_kind_label;
}

function renderDetail() {
  clear(detail);
  const c = chains.find((x) => x.id === selectedId);
  if (!c) {
    detail.append(createEmptyState({ title: 'No approval chains', message: 'Without a chain, completed work counts at once.', icon: 'check' }));
    return;
  }
  const steps = c.steps;
  detail.append(
    el('div', { class: 'ct-card__body ct-stack' },
      el('div', { class: 'ct-detail-head' },
        el('div', { class: 'ct-stack', style: { gap: '4px' } },
          el('div', { class: 'ct-detail-head__title' }, el('h2', {}, c.name), c.is_active ? null : createBadge('Retired')),
          el('div', { class: 'ct-small' }, appliesTo(c)),
          c.description ? el('div', { class: 'ct-muted ct-small' }, c.description) : null),
        el('div', { class: 'ct-actions' },
          el('button', { class: 'ct-btn ct-btn--sm', onClick: () => editChain(c) }, icon('edit', { size: 16 }), 'Edit chain'),
          el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => editStep(c, null) }, icon('plus', { size: 16 }), 'Add step')))),
    el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
      el('thead', {}, el('tr', {}, ['Order', 'Step', 'Approver', 'If nobody can approve', 'Requires', 'Status', ''].map((h) => el('th', { scope: 'col' }, h)))),
      el('tbody', {}, steps.length ? steps.map((s) => el('tr', {
        class: `is-clickable${s.is_active ? '' : ' ct-row-retired'}`, tabindex: '0',
        onClick: () => editStep(c, s), onKeydown: (e) => { if (e.key === 'Enter') editStep(c, s); },
      },
        el('td', {}, String(s.sort_order)),
        el('td', {}, el('strong', {}, s.name)),
        el('td', {}, approverText(s)),
        el('td', {}, missing[s.when_missing] || s.when_missing),
        el('td', { class: 'ct-small' }, [
          s.checklist.length ? `${s.checklist.length} check(s)` : null,
          s.require_evidence ? 'evidence link' : null,
          s.require_comment ? 'comment' : null].filter(Boolean).join(' · ') || '—'),
        el('td', {}, s.is_active ? 'Active' : 'Retired'),
        el('td', { style: { textAlign: 'right' } }, icon('edit', { size: 16 }))))
        : el('tr', {}, el('td', { colspan: 7 }, createEmptyState({ title: 'No steps', message: 'A chain without steps is ignored.' })))))),
    el('div', { class: 'ct-card__body' }, el('p', { class: 'ct-muted ct-small' },
      'Rules that always apply: nobody approves their own work (their line manager does instead); someone who already approved an earlier step is not asked again; rejecting always needs a note and sends the work back to In progress.')));
}

function editChain(chain) {
  openFormModal({
    title: chain ? `Edit chain · ${chain.name}` : 'New approval chain',
    fields: [
      { key: 'name', label: 'Name', required: true },
      chain ? null : { key: 'code', label: 'Code', required: true, help: 'Lowercase letters, numbers and _. Cannot change later.' },
      { key: 'item_type_ids', label: 'Item types', type: 'checkboxes', options: lookupOptions('item_type', chain?.item_type_ids || []), help: 'None ticked = every type.' },
      { key: 'unit_id', label: 'Unit', type: 'select', options: treeOptions(units), placeholder: '— Whole organisation —', help: 'Applies to this unit and the units below it.' },
      { key: 'sort_order', label: 'Order', type: 'number', help: 'Breaks ties between equally specific chains (lowest first).' },
      chain ? { key: 'is_active', label: 'Active', type: 'checkbox', checkboxLabel: 'Active (untick to retire)' } : null,
      { key: 'description', label: 'Description', type: 'textarea' },
      chain ? { key: 'reason', label: 'Reason for change', full: true, help: 'Saved in the audit log.' } : null,
    ].filter(Boolean),
    values: chain || {},
    submitLabel: chain ? 'Save chain' : 'Create chain',
    onSubmit: (v) => (chain ? api.patch(`/approval-chains/${chain.id}`, { ...v, version: chain.version }) : api.post('/approval-chains', v)),
    onDone: (saved) => { selectedId = saved.id; showToast('Saved as a draft. Publish to use it.', 'success'); load(); },
  });
}

function editStep(chain, step) {
  const kindOptions = Object.entries(kinds).map(([value, label]) => ({ value, label }));
  openFormModal({
    title: step ? `Edit step · ${step.name}` : `Add a step to ${chain.name}`,
    intro: 'For “Anyone with a role” pick the role; for “A named person” pick the person. Other approver types are worked out from the item itself.',
    fields: [
      { key: 'name', label: 'Step name', required: true, help: 'e.g. “Functional lead review”' },
      { key: 'sort_order', label: 'Order', type: 'number', help: step ? null : 'Empty = after the last step.' },
      { key: 'approver_kind', label: 'Who approves', type: 'select', options: kindOptions, required: true },
      { key: 'approver_role_id', label: 'Role (for “Anyone with a role”)', type: 'select', options: roles.map((r) => ({ value: r.id, label: r.name })) },
      { key: 'approver_person_id', label: 'Person (for “A named person”)', type: 'person', value: step?.approver_person || null },
      { key: 'when_missing', label: 'If nobody can approve', type: 'select', required: true, options: Object.entries(missing).map(([value, label]) => ({ value, label })) },
      { key: 'checklist', label: 'Checklist (one check per line)', type: 'textarea', help: 'The approver must tick every check to approve.' },
      { key: 'require_evidence', label: 'Evidence', type: 'checkbox', checkboxLabel: 'The item must have an evidence link (checked when it is marked complete)' },
      { key: 'require_comment', label: 'Comment', type: 'checkbox', checkboxLabel: 'The approver must write a comment to approve' },
      step ? { key: 'is_active', label: 'Active', type: 'checkbox', checkboxLabel: 'Active (untick to retire)' } : null,
      step ? { key: 'reason', label: 'Reason for change', full: true, help: 'Saved in the audit log.' } : null,
    ].filter(Boolean),
    values: step ? { ...step, checklist: step.checklist.join('\n') } : { approver_kind: 'functional_lead', when_missing: 'skip' },
    submitLabel: step ? 'Save step' : 'Add step',
    onSubmit: (v) => {
      const body = { ...v, checklist: (v.checklist || '').split('\n').map((x) => x.trim()).filter(Boolean) };
      return step ? api.patch(`/approval-steps/${step.id}`, { ...body, version: step.version })
        : api.post('/approval-steps', { ...body, chain_id: chain.id });
    },
    onDone: () => { showToast('Saved as a draft. Publish to use it.', 'success'); load(); },
  });
}

load();
