/** Tools registry (admin): add, change and retire tools, and decide who may use them.
 *  Every change is audited. A tool applies organisation-wide unless limited to items or units;
 *  roles and item types narrow it further. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { lookupOptions } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createDataTable } from '../components/data-table.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog, openModal } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';
import { appliesToText, KIND_LABEL } from '../components/tools.js';
import { treeOptions } from '../components/tree.js';

const { content } = await initLayout({ active: 'admin-tools', title: 'Tools registry', permission: 'tools.manage' });

const [options, units] = await Promise.all([
  api.get('/tools/options').catch((e) => { showError(e); return { form_fields: [], roles: [] }; }),
  api.get('/units').then((d) => d.items).catch(() => []),
]);

const KIND_INTRO = {
  link: 'A tool deployed elsewhere. People who may use it see it in the Tool Centre and on matching items; opening it checks access and is logged.',
  form: 'A set of work item fields filled in together (for example a risk review). Saving updates the item with the usual permissions and history.',
  checklist: 'A readiness assessment: items to tick on a work item, with a pass mark. Answers are kept per item and audited.',
};

const table = createDataTable({
  columns: [
    { key: 'name', label: 'Tool', sortable: true, render: (t) => el('div', { class: 'ct-work-title' },
      el('strong', {}, `${t.icon || '🔗'} ${t.name}`), el('span', { class: 'ct-work-title__code' }, t.kind === 'link' ? t.url : KIND_LABEL[t.kind])) },
    { key: 'kind', label: 'Kind', sortable: true, render: (t) => KIND_LABEL[t.kind] },
    { key: 'applies', label: 'Who may use it', render: (t) => appliesToText(t) },
    { key: 'is_active', label: 'State', sortable: true, render: (t) => (t.is_active ? createBadge('Active', 'var(--ct-success)') : createBadge('Retired', 'var(--ct-text-subtle)')) },
    { key: 'actions', label: '', render: (t) => el('div', { class: 'ct-tag-list' },
      el('button', { class: 'ct-btn ct-btn--sm', onClick: (e) => { e.stopPropagation(); edit(t); } }, 'Edit'),
      el('button', { class: 'ct-btn ct-btn--sm', onClick: (e) => { e.stopPropagation(); toggle(t); } }, t.is_active ? 'Retire' : 'Reactivate'),
      el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', onClick: (e) => { e.stopPropagation(); remove(t); } }, 'Delete')) },
  ],
  fetchPage: (q) => api.get('/tools', { ...q, manage: 1 }),
  defaultSort: 'sort_order',
  onRowClick: (t) => edit(t),
  rowClass: (t) => (t.is_active ? null : 'ct-row-retired'),
  emptyState: { title: 'No tools yet', message: 'Add links to the tools your teams use, or build forms and checklists.', icon: 'grid' },
});

content.append(
  pageHeader('Tools registry', 'The tools shown in the Tool Centre and on work items, and who may use them. Changes are audited.',
    [el('a', { class: 'ct-btn', href: '/pages/tools.html' }, 'Open Tool Centre'),
      el('button', { class: 'ct-btn ct-btn--primary', onClick: chooseKind }, icon('plus', { size: 16 }), 'New tool')]),
  el('section', { class: 'ct-card' }, table.element));

function chooseKind() {
  const modal = openModal({
    title: 'New tool',
    body: el('div', { class: 'ct-stack' }, Object.entries(KIND_LABEL).map(([kind, label]) => el('button', {
      class: 'ct-btn ct-type-grid__btn', style: { height: 'auto', padding: '12px', flexDirection: 'column', alignItems: 'flex-start' },
      onClick: () => { modal.close(); edit(null, kind); },
    }, el('strong', {}, label), el('span', { class: 'ct-muted ct-small', style: { whiteSpace: 'normal', textAlign: 'left' } }, KIND_INTRO[kind])))),
    actions: [{ label: 'Cancel' }],
  });
}

const paramsText = (p) => Object.entries(p || {}).map(([k, v]) => `${k}=${v}`).join('\n');
function parseParams(text) {
  const out = {};
  for (const line of (text || '').split('\n').map((l) => l.trim()).filter(Boolean)) {
    const at = line.indexOf('=');
    if (at < 1) throw Object.assign(new Error(`Write each pair as name=value: “${line}”`), { details: { field: 'context_params' } });
    out[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  }
  return out;
}

function edit(existing, newKind = null) {
  const kind = existing?.kind || newKind;
  const def = existing?.raw_definition || {};
  const fields = [
    { key: 'name', label: 'Name', required: true, maxlength: 120 },
    { key: 'icon', label: 'Icon', maxlength: 16, placeholder: '🔗', help: 'An emoji or short symbol.' },
    kind === 'link' ? { key: 'url', label: 'Web address', type: 'url', required: true, full: true, placeholder: 'https://' } : null,
    { key: 'description', label: 'Description', type: 'textarea' },
    kind === 'form' ? { key: 'form_fields', label: 'Fields the form fills in', type: 'checkboxes', required: true,
      options: options.form_fields.map((f) => ({ value: f.code, label: f.label, group: f.custom ? 'Custom fields' : 'Work item fields' })) } : null,
    kind === 'checklist' ? { key: 'checklist_items', label: 'Checklist items (one per line)', type: 'textarea', required: true } : null,
    kind === 'checklist' ? { key: 'pass_pct', label: 'Pass mark (% of items ticked)', type: 'number', default: 100 } : null,
    { key: 'work_item_codes', label: 'Only on these items (codes, comma separated)', full: true, placeholder: 'PRJ-001, PGM-002',
      help: 'The items and everything below them. Leave empty, with no units, for organisation-wide.' },
    { key: 'unit_ids', label: 'Only for these units (and the units below them)', type: 'checkboxes', options: treeOptions(units) },
    { key: 'role_ids', label: 'Only for people with these roles', type: 'checkboxes', options: options.roles.map((r) => ({ value: r.id, label: r.name })),
      help: 'None ticked = any role.' },
    { key: 'item_type_ids', label: 'Only on these item types', type: 'checkboxes', options: lookupOptions('item_type', existing?.item_type_ids) },
    kind === 'link' ? { key: 'context_params', label: 'Project data to pass to the tool', type: 'textarea', placeholder: 'project={code}',
      help: 'Added to the address when someone opens the tool from an item. One name={placeholder} per line. Placeholders: {code}, {id}, {title}, {type}, {status}, {unit}, {unit_code}, {user_email}, {user_id}. Example: project={code} opens …?project=PRJ-004.' } : null,
    { key: 'sort_order', label: 'Order', type: 'number', help: 'Lower numbers are listed first.' },
    { key: 'is_active', label: 'Active', type: 'checkbox', checkboxLabel: 'Active (shown to people who may use it)', default: true },
    existing ? { key: 'reason', label: 'Reason for change', full: true, help: 'Saved in the audit log.' } : null,
  ].filter(Boolean);

  openFormModal({
    title: existing ? `Edit ${existing.name}` : `New ${KIND_LABEL[kind].toLowerCase()} tool`,
    intro: KIND_INTRO[kind],
    fields,
    values: existing ? {
      ...existing, work_item_codes: existing.work_item_codes.join(', '), context_params: paramsText(existing.context_params),
      form_fields: def.fields || [], checklist_items: (def.items || []).map((i) => i.label).join('\n'), pass_pct: def.pass_pct ?? 100,
    } : { is_active: true, pass_pct: 100 },
    submitLabel: existing ? 'Save' : 'Add tool',
    onSubmit: (v) => {
      const { form_fields: formFields, checklist_items: checklistItems, pass_pct: passPct, ...body } = v;
      body.work_item_codes = (v.work_item_codes || '').split(/[\s,]+/).filter(Boolean);
      if ('context_params' in v) body.context_params = parseParams(v.context_params);
      if (kind === 'form') body.definition = { fields: formFields };
      if (kind === 'checklist') {
        const previous = new Map((def.items || []).map((i) => [i.label, i.code]));  // keep codes, so answers stay linked
        body.definition = { pass_pct: passPct ?? 100, items: (checklistItems || '').split('\n').map((l) => l.trim()).filter(Boolean)
          .map((label) => (previous.has(label) ? { code: previous.get(label), label } : { label })) };
      }
      body.sort_order = body.sort_order ?? 0;
      if (existing) return api.patch(`/tools/${existing.id}`, { ...body, version: existing.version });
      body.kind = kind;
      return api.post('/tools', Object.fromEntries(Object.entries(body).filter(([, x]) => x !== null)));
    },
    onDone: (saved) => { showToast(existing ? 'Tool saved' : `${saved.name} added`, 'success'); table.reload(); },
  });
}

async function toggle(t) {
  try {
    await api.patch(`/tools/${t.id}`, { is_active: !t.is_active, version: t.version, reason: t.is_active ? 'Retired' : 'Reactivated' });
    showToast(t.is_active ? `${t.name} retired` : `${t.name} reactivated`, 'success');
    table.reload();
  } catch (err) { showError(err); }
}

async function remove(t) {
  if (!await confirmDialog({ title: `Delete ${t.name}?`, message: 'It disappears for everyone. Checklist answers and the audit log are kept. Retiring hides it but keeps it in this list.', confirmLabel: 'Delete', danger: true })) return;
  try { await api.del(`/tools/${t.id}`, { reason: 'Tool removed' }); showToast('Tool deleted', 'success'); table.reload(); } catch (err) { showError(err); }
}
