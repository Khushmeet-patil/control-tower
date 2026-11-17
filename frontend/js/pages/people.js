/** People directory: everyone the user may see, with add/edit for those who manage people.
 *  Admin-defined custom fields (published settings) add columns, filters and form fields automatically. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { customFields, loadSettings, lookupOptions, term } from '../core/lookups.js';
import { el, formatDateTime } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { customColumns, customFilterFields, customFormFields, customValueNode, withCustomValues } from '../components/custom-fields.js';
import { createDataTable } from '../components/data-table.js';
import { createFilterBar } from '../components/filter-bar.js';
import { openFormModal } from '../components/form-builder.js';
import { openModal } from '../components/modal.js';
import { createPersonCell } from '../components/person.js';
import { showError, showToast } from '../components/toast.js';
import { treeOptions } from '../components/tree.js';

await loadSettings().catch(() => null); // terms are needed for the page title
const PEOPLE = term('person', { plural: true, fallback: 'People' });
const PERSON = term('person', { fallback: 'Person' });
const { user, content } = await initLayout({ active: 'people', title: PEOPLE, permission: 'people.view' });
const canManage = can(user, 'people.manage');
const canAssignRoles = can(user, 'roles.manage');

const [units, functions, roles] = await Promise.all([
  api.get('/units').then((d) => d.items),
  api.get('/functions').then((d) => d.items),
  api.get('/roles').then((d) => d.items),
]).catch((err) => { showError(err); return [[], [], []]; });

const unitOptions = treeOptions(units);
const functionOptions = treeOptions(functions);
const roleOptions = roles.map((r) => ({ value: r.id, label: r.name, help: r.description }));

// ------------------------------------------------------------------ list
const table = createDataTable({
  columns: [
    { key: 'full_name', label: 'Name', sortable: true, render: (p) => createPersonCell(p, p.email) },
    { key: 'job_title', label: 'Job title', sortable: true },
    { key: 'unit', label: 'Unit', render: (p) => p.unit?.name || '—' },
    { key: 'function', label: 'Function', render: (p) => p.function?.name || '—' },
    { key: 'manager', label: 'Reports to', render: (p) => p.manager?.full_name || '—' },
    { key: 'roles', label: 'Roles', render: (p) => el('div', { class: 'ct-tag-list' }, p.roles.map((r) => createBadge(r.name))) },
    ...customColumns('person'),
    { key: 'is_active', label: 'Status', sortable: true, render: (p) => createBadge(p.is_active ? 'Active' : 'Inactive', p.is_active ? 'var(--ct-success)' : 'var(--ct-text-subtle)') },
  ],
  fetchPage: (params) => api.get('/people', params),
  defaultSort: 'full_name',
  onRowClick: (p) => openPerson(p.id),
  emptyState: { title: `No ${PEOPLE.toLowerCase()} found`, message: 'Try changing the filters.', icon: 'users' },
});

const filters = createFilterBar({
  fields: [
    { key: 'q', type: 'search', placeholder: 'Search name, email, title…' },
    { key: 'unit_id', type: 'select', label: 'Units', options: unitOptions },
    { key: 'function_id', type: 'select', label: 'Functions', options: functionOptions },
    { key: 'role_id', type: 'select', label: 'Roles', options: roles.map((r) => ({ value: r.id, label: r.name })) },
    { key: 'is_active', type: 'select', label: 'Statuses', options: [{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }] },
    ...customFilterFields('person'),
  ],
  onChange: (values) => table.setFilters({ ...values, include_descendants: values.unit_id || values.function_id ? '1' : '' }),
});

content.append(
  pageHeader(PEOPLE, 'Everyone you can see, with their unit, function and reporting line.',
    canManage ? [el('button', { class: 'ct-btn ct-btn--primary', onClick: () => openEditor(null) }, icon('plus', { size: 16 }), `Add ${PERSON.toLowerCase()}`)] : []),
  el('section', { class: 'ct-card' }, filters.element, table.element),
);

// ------------------------------------------------------------------ view / edit
async function openPerson(id) {
  try {
    const person = await api.get(`/people/${id}`);
    if (canManage) openEditor(person); else openViewer(person);
  } catch (err) { showError(err); }
}

function openViewer(p) {
  const kv = (label, value) => [el('dt', {}, label), el('dd', {}, value)];
  openModal({
    title: p.full_name,
    body: el('dl', { class: 'ct-kv' },
      kv('Email', p.email),
      kv('Job title', p.job_title || '—'),
      kv('Unit', p.unit?.name || '—'),
      kv('Function', p.function?.name || '—'),
      kv('Reports to', p.manager?.full_name || '—'),
      kv('Roles', el('div', { class: 'ct-tag-list' }, p.roles.map((r) => createBadge(r.name)))),
      kv('Status', p.is_active ? 'Active' : 'Inactive'),
      customFields('person').map((f) => kv(f.label, customValueNode(f, p)))),
  });
}

function openEditor(existing) {
  const isSelf = existing?.id === user.id;
  const fields = [
    { key: 'full_name', label: 'Full name', required: true },
    { key: 'email', label: 'Email', type: 'email', required: true },
    { key: 'job_title', label: 'Job title' },
    { key: 'employee_code', label: 'Employee code' },
    { key: 'unit_id', label: 'Unit (administrative)', type: 'select', options: unitOptions, required: !user.is_admin && user.scope !== 'all' },
    { key: 'function_id', label: 'Function', type: 'select', options: functionOptions },
    { key: 'manager_id', label: 'Reports to', type: 'person', value: existing?.manager, exclude: existing ? [existing.id] : [] },
    existing ? null : { key: 'password', label: 'Temporary password', type: 'password', required: true, help: 'At least 8 characters. Ask them to change it after signing in.' },
    canAssignRoles ? { key: 'role_ids', label: 'Roles', type: 'checkboxes', options: roleOptions, help: existing ? null : 'Leave empty to give the default role.' } : null,
    { key: 'is_active', label: 'Active', type: 'checkbox', checkboxLabel: 'Active (can sign in)', default: true, disabled: isSelf },
    user.is_admin ? { key: 'is_admin', label: 'Administrator', type: 'checkbox', checkboxLabel: 'Platform administrator (full access)', disabled: isSelf } : null,
    { key: 'skill_ids', label: 'Skills', type: 'checkboxes', options: lookupOptions('skill'), help: 'Used to find people with spare capacity.' },
    { key: 'capacity_pct', label: 'Working capacity %', type: 'number', help: '100 = full time; 50 = half time. Empty = full time.' },
    { key: 'backlog_days', label: 'Estimated backlog (person-days)', type: 'number' },
    { key: 'work_days', label: 'Working days', type: 'checkboxes', full: true,
      options: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, i) => ({ value: i, label: d })),
      default: [0, 1, 2, 3, 4], help: 'The days they normally work. Capacity counts only these days (and public holidays are taken off).' },
    ...customFormFields('person', existing),
    existing ? { key: 'reason', label: 'Reason for change', help: 'Saved in the audit log.', full: true } : null,
  ].filter(Boolean);

  const extraActions = existing ? [{ label: 'Reset password', onClick: async (close) => { close(); resetPassword(existing); } }] : [];

  openFormModal({
    title: existing ? existing.full_name : `Add ${PERSON.toLowerCase()}`,
    intro: existing?.last_login_at ? `Last signed in ${formatDateTime(existing.last_login_at)}.` : null,
    fields,
    values: existing || {},
    submitLabel: existing ? 'Save changes' : 'Add person',
    extraActions,
    onSubmit: (raw) => {
      const values = withCustomValues(raw);
      if (isSelf) { delete values.is_active; delete values.is_admin; }
      if (!existing && canAssignRoles && !values.role_ids?.length) delete values.role_ids;
      return existing
        ? api.patch(`/people/${existing.id}`, { ...values, version: existing.version })
        : api.post('/people', values);
    },
    onDone: () => {
      showToast(existing ? 'Changes saved' : `${PERSON} added`, 'success');
      table.reload();
    },
  });
}

function resetPassword(person) {
  openFormModal({
    title: `Reset password · ${person.full_name}`,
    wide: false,
    submitLabel: 'Reset password',
    fields: [
      { key: 'password', label: 'New temporary password', type: 'password', required: true, full: true, help: 'At least 8 characters.' },
      { key: 'reason', label: 'Reason', full: true },
    ],
    onSubmit: (v) => api.post(`/people/${person.id}/reset-password`, v),
    onDone: () => showToast('Password reset', 'success'),
  });
}

// Deep link from other screens: /pages/people.html?person=12
const linked = Number(new URLSearchParams(location.search).get('person'));
if (linked) openPerson(linked);
