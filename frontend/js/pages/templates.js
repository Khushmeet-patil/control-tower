/** Templates (/pages/templates.html): reusable work breakdowns (e.g. a launch: milestones and tasks with
 *  their timing). Save one from any item ("Save as template" on the item page), edit its outline here, and
 *  create real work from it: dates are worked out from the start date you choose. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge, lookupValues } from '../core/lookups.js';
import { el, formatDateTime } from '../core/utils.js';
import { createDataTable } from '../components/data-table.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog, openModal } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';
import { treeOptions } from '../components/tree.js';
import { pickWorkItem } from '../components/work-picker.js';

const { user, content } = await initLayout({ active: 'templates', title: 'Templates', permission: 'work.view' });
const types = lookupValues('item_type');
const units = await api.get('/units').then((d) => d.items).catch(() => []);

const table = createDataTable({
  columns: [
    { key: 'name', label: 'Template', render: (t) => el('div', {}, el('strong', {}, t.name), t.description ? el('div', { class: 'ct-muted ct-small' }, t.description) : null) },
    { key: 'root_type_ids', label: 'Starts with', render: (t) => el('div', { class: 'ct-tag-list' }, t.root_type_ids.map((i) => lookupBadge(i))) },
    { key: 'node_count', label: 'Items' },
    { key: 'is_shared', label: 'Who can use it', render: (t) => (t.is_shared ? 'Everyone' : 'Only you') },
    { key: 'owner', label: 'Owner', render: (t) => t.owner?.full_name || '—' },
    { key: 'updated_at', label: 'Updated', render: (t) => formatDateTime(t.updated_at) },
    { key: 'actions', label: '', render: (t) => el('div', { style: { display: 'flex', gap: '6px' } },
      el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', type: 'button', onClick: (e) => { e.stopPropagation(); useTemplate(t); } }, 'Use'),
      t.can_edit ? el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: (e) => { e.stopPropagation(); edit(t.id); } }, 'Edit') : null,
      t.can_edit ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', type: 'button', onClick: (e) => { e.stopPropagation(); remove(t); } }, 'Delete') : null) },
  ],
  fetchPage: (q) => api.get('/templates', q),
  onRowClick: (t) => edit(t.id),
  emptyState: { title: 'No templates yet', message: 'Open an item with a good breakdown and choose “Save as template”, or start one here.', icon: 'copy' },
});
table.setFilters({});

content.append(
  pageHeader('Templates', 'Reusable work breakdowns. Using one creates the items for you, with dates shifted to your start date.', [
    el('button', { class: 'ct-btn', type: 'button', onClick: saveFromItem }, 'Save an item as a template'),
    el('button', { class: 'ct-btn ct-btn--primary', type: 'button', onClick: () => edit(null) }, icon('plus', { size: 16 }), 'New template')]),
  el('section', { class: 'ct-card' }, table.element));

const opened = Number(new URLSearchParams(location.search).get('id'));
if (opened) edit(opened);

async function saveFromItem() {
  const item = await pickWorkItem({ title: 'Save which item (with everything under it)?' });
  if (!item) return;
  openFormModal({
    title: `Save ${item.code} as a template`,
    fields: [
      { key: 'name', label: 'Template name', required: true, full: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      can(user, 'templates.share') ? { key: 'is_shared', label: 'Sharing', type: 'checkbox', checkboxLabel: 'Everyone can use it' } : null,
    ].filter(Boolean),
    values: { name: item.title },
    onSubmit: (v) => api.post('/templates/from-item', { work_item_id: item.id, ...v }),
    onDone: (t) => { showToast('Template saved', 'success'); table.reload(); edit(t.id); },
  });
}

async function remove(t) {
  if (!await confirmDialog({ title: `Delete “${t.name}”?`, message: 'Work already made from it is not affected.', confirmLabel: 'Delete', danger: true })) return;
  try { await api.del(`/templates/${t.id}`, { reason: 'Template deleted' }); table.reload(); } catch (err) { showError(err); }
}

// ------------------------------------------------------------------ outline editor
function flatten(nodes, depth = 0, out = []) {
  for (const n of nodes) {
    out.push({ ...n, depth, children: undefined });
    flatten(n.children || [], depth + 1, out);
  }
  return out;
}

function nest(rows) {
  const roots = [];
  const stack = [];
  for (const r of rows) {
    const node = { title: r.title, item_type_id: r.item_type_id, description: r.description || undefined, objective: r.objective || undefined,
      weight: r.weight || undefined, start_offset: r.start_offset ?? undefined, duration: r.duration ?? undefined, children: [] };
    while (stack.length > r.depth) stack.pop();
    (stack.length ? stack[stack.length - 1].children : roots).push(node);
    stack.push(node);
  }
  return roots;
}

async function edit(templateId) {
  let t = { name: '', description: '', is_shared: false, structure: [{ title: '', item_type_id: types.find((x) => x.code === 'project')?.id || types[0]?.id, children: [] }], can_edit: true };
  if (templateId) {
    try { t = await api.get(`/templates/${templateId}`); } catch (err) { showError(err); return; }
  }
  const readOnly = !t.can_edit;
  let rows = flatten(t.structure);
  const name = el('input', { class: 'ct-input', value: t.name, disabled: readOnly, 'aria-label': 'Template name', placeholder: 'Template name' });
  const description = el('textarea', { class: 'ct-textarea', disabled: readOnly, 'aria-label': 'Description', placeholder: 'What is it for?' }, t.description || '');
  const shared = el('input', { type: 'checkbox', checked: t.is_shared, disabled: readOnly || !can(user, 'templates.share') });
  const outline = el('div', { class: 'ct-outline' });

  const typeSelect = (r) => el('select', { class: 'ct-select', disabled: readOnly, 'aria-label': 'Type', onChange: (e) => { r.item_type_id = Number(e.target.value); } },
    types.map((x) => el('option', { value: x.id, selected: x.id === r.item_type_id }, x.label)));
  const num = (r, key, label) => el('input', { class: 'ct-input', type: 'number', min: 0, value: r[key] ?? '', disabled: readOnly, 'aria-label': label, placeholder: label,
    onInput: (e) => { r[key] = e.target.value === '' ? null : Number(e.target.value); } });
  const btn = (label, glyph, onClick, disabled = false) => el('button', { class: 'ct-btn ct-btn--ghost ct-btn--icon ct-btn--sm', type: 'button', 'aria-label': label, title: label, disabled, onClick }, glyph);

  function draw() {
    outline.replaceChildren(
      el('div', { class: 'ct-outline__row ct-muted ct-small' }, el('span', {}, 'Item'), el('span', {}, 'Type'), el('span', {}, 'Starts day'), el('span', {}, 'Lasts (days)'), el('span', {})),
      ...rows.map((r, i) => el('div', { class: 'ct-outline__row' },
        el('div', { class: 'ct-outline__title', style: { paddingLeft: `${r.depth * 20}px` } },
          el('input', { class: 'ct-input', value: r.title, disabled: readOnly, 'aria-label': 'Title', placeholder: 'Title', onInput: (e) => { r.title = e.target.value; } })),
        typeSelect(r), num(r, 'start_offset', 'Day'), num(r, 'duration', 'Days'),
        readOnly ? el('span') : el('div', { class: 'ct-outline__actions' },
          btn('Move left', '←', () => { if (r.depth > 0) { shiftBranch(i, -1); draw(); } }, r.depth === 0),
          btn('Move right (under the item above)', '→', () => { if (i > 0 && r.depth <= rows[i - 1].depth) { shiftBranch(i, 1); draw(); } }, i === 0 || r.depth > rows[i - 1].depth),
          btn('Add an item under this one', '+', () => { rows.splice(branchEnd(i), 0, { title: '', item_type_id: types.find((x) => x.code === 'task')?.id || r.item_type_id, depth: r.depth + 1 }); draw(); }),
          btn('Remove (with what is under it)', '×', () => { rows.splice(i, branchEnd(i) - i); if (!rows.length) rows.push({ title: '', item_type_id: r.item_type_id, depth: 0 }); draw(); })))),
      readOnly ? null : el('button', { class: 'ct-btn ct-btn--sm', type: 'button', style: { alignSelf: 'flex-start' }, onClick: () => { rows.push({ title: '', item_type_id: types.find((x) => x.code === 'milestone')?.id || types[0].id, depth: 0 }); draw(); } }, '+ Top-level item'));
  }
  const branchEnd = (i) => { let j = i + 1; while (j < rows.length && rows[j].depth > rows[i].depth) j += 1; return j; };
  const shiftBranch = (i, by) => { for (let j = i; j < branchEnd(i); j += 1) rows[j].depth += by; };
  draw();

  openModal({
    title: templateId ? t.name : 'New template',
    wide: true,
    body: el('div', { class: 'ct-stack' },
      el('div', { class: 'ct-grid-2' }, el('label', { class: 'ct-field' }, el('span', { class: 'ct-label' }, 'Name'), name),
        el('label', { class: 'ct-field' }, el('span', { class: 'ct-label' }, 'Description'), description)),
      el('label', { class: 'ct-checkbox' }, shared, ' Everyone can use it', can(user, 'templates.share') ? null : el('span', { class: 'ct-muted ct-small' }, ' (you cannot share templates)')),
      el('p', { class: 'ct-muted ct-small' }, '“Starts day” counts from the start date chosen when the template is used (0 = that day). Leave timing empty for items without dates.'),
      outline),
    actions: readOnly ? [{ label: 'Close' }, { label: 'Use', variant: 'primary', onClick: (close) => { close(); useTemplate(t); } }] : [
      { label: 'Cancel' },
      { label: 'Save', variant: 'primary', onClick: async (close) => {
        const body = { name: name.value.trim(), description: description.value.trim() || null, is_shared: shared.checked, structure: nest(rows) };
        if (templateId) await api.patch(`/templates/${templateId}`, { ...body, version: t.version });
        else await api.post('/templates', body);
        showToast('Template saved', 'success');
        close();
        table.reload();
      } }],
  });
}

// ------------------------------------------------------------------ use
function useTemplate(t) {
  useTemplate.parent = null;
  openFormModal({
    title: `Use “${t.name}”`,
    intro: 'The items are created now, as you, with your usual rights. To put them under an existing item, use “Choose the item to put it under…” first; otherwise they start at the top level. Owners and units are inherited from that item unless you choose them.',
    fields: [
      { key: 'title', label: 'Name of the top item (optional)', full: true },
      { key: 'start_date', label: 'Start date', type: 'date', help: 'Dates in the template count from this day.' },
      { key: 'unit_id', label: 'Unit', type: 'select', options: treeOptions(units) },
      { key: 'accountable_id', label: 'Accountable owner', type: 'person' },
      { key: 'reason', label: 'Reason (for the audit log)', full: true },
    ],
    extraActions: [{ label: 'Choose the item to put it under…', onClick: async () => {
      const parent = await pickWorkItem({ title: 'Put it under which item?' });
      if (parent) { useTemplate.parent = parent; showToast(`It will go under ${parent.code}`, 'info'); }
    } }],
    submitLabel: 'Create work',
    onSubmit: (v) => api.post(`/templates/${t.id}/use`, {
      title: v.title || null, start_date: v.start_date || null, parent_id: useTemplate.parent?.id || null,
      unit_id: v.unit_id || null, accountable_id: v.accountable_id || null, reason: v.reason || null,
    }),
    onDone: (res) => {
      useTemplate.parent = null;
      showToast(`Created ${res.items.map((i) => i.code).join(', ')}`, 'success');
      if (res.items[0]) location.href = `/pages/item.html?id=${res.items[0].id}`;
    },
  });
}
