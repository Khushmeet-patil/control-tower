/** Roles & access: what each role may do (permissions) and see (scope). Stored as data. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { clear, el } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';

const { content } = await initLayout({ active: 'roles', title: 'Roles & access', permission: 'roles.manage' });

const SCOPE_TEXT = {
  own: { label: 'Own', help: 'Only themselves and work assigned to them.' },
  unit: { label: 'Unit', help: 'Their own unit and every unit below it.' },
  all: { label: 'Whole organisation', help: 'Everything in the organisation.' },
};

const catalog = (await api.get('/permissions').catch((e) => { showError(e); return { items: [] }; })).items;
const permissionOptions = catalog.map((p) => ({ value: p.code, label: p.label, group: p.group }));

const tableBody = el('tbody');
content.append(
  pageHeader('Roles & access', 'A role sets what people may do (permissions) and how far they can see (scope). Changes apply immediately.',
    [el('button', { class: 'ct-btn ct-btn--primary', onClick: () => openEditor(null) }, icon('plus', { size: 16 }), 'New role')]),
  el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__body ct-small ct-muted' },
      'Besides their role, people also see the units they head, the people in functions they lead, and their own reporting line.'),
    el('div', { class: 'ct-table-wrap' },
      el('table', { class: 'ct-table' },
        el('thead', {}, el('tr', {}, ['Role', 'Scope', 'Permissions', 'People', ''].map((h) => el('th', { scope: 'col' }, h)))),
        tableBody))),
);

async function load() {
  try {
    const roles = (await api.get('/roles')).items;
    clear(tableBody);
    if (!roles.length) {
      tableBody.append(el('tr', {}, el('td', { colspan: 5 }, createEmptyState({ title: 'No roles' }))));
      return;
    }
    for (const r of roles) {
      const tr = el('tr', { class: 'is-clickable', tabindex: '0', onClick: () => openEditor(r), onKeydown: (e) => { if (e.key === 'Enter') openEditor(r); } },
        el('td', {},
          el('div', { style: { fontWeight: 600 } }, r.name, ' ',
            r.is_default ? createBadge('Default', 'var(--ct-accent)') : null, ' ',
            r.is_system ? createBadge('Built-in') : null),
          el('div', { class: 'ct-muted ct-small' }, r.description || '')),
        el('td', {}, SCOPE_TEXT[r.scope]?.label || r.scope),
        el('td', {}, `${r.permission_codes.length} of ${catalog.length}`),
        el('td', {}, String(r.people_count)),
        el('td', { style: { textAlign: 'right' } },
          !r.is_system ? el('button', {
            class: 'ct-btn ct-btn--ghost ct-btn--sm ct-btn--icon', 'aria-label': `Delete ${r.name}`,
            onClick: (e) => { e.stopPropagation(); remove(r); },
          }, icon('trash', { size: 16 })) : null));
      tableBody.append(tr);
    }
  } catch (err) { showError(err); }
}

function openEditor(role) {
  openFormModal({
    title: role ? `Edit role · ${role.name}` : 'New role',
    fields: [
      { key: 'name', label: 'Name', required: true },
      role ? null : { key: 'code', label: 'Code', required: true, help: 'Lowercase letters, numbers and _ (e.g. project_manager). Cannot change later.' },
      {
        key: 'scope', label: 'Scope (what they can see)', type: 'select', required: true,
        options: Object.entries(SCOPE_TEXT).map(([value, s]) => ({ value, label: `${s.label} — ${s.help}` })),
      },
      { key: 'is_default', label: 'Default', type: 'checkbox', checkboxLabel: 'Give this role to new people automatically' },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'permission_codes', label: 'Permissions (what they can do)', type: 'checkboxes', options: permissionOptions },
      role ? { key: 'reason', label: 'Reason for change', help: 'Saved in the audit log.', full: true } : null,
    ].filter(Boolean),
    values: role || { scope: 'own', permission_codes: ['org.view', 'functions.view', 'people.view'] },
    submitLabel: role ? 'Save changes' : 'Create role',
    onSubmit: (v) => (role ? api.patch(`/roles/${role.id}`, { ...v, version: role.version }) : api.post('/roles', v)),
    onDone: () => { showToast(role ? 'Role saved' : 'Role created', 'success'); load(); },
  });
}

async function remove(role) {
  const ok = await confirmDialog({ title: `Delete ${role.name}?`, message: 'The role must not be assigned to anyone.', confirmLabel: 'Delete', danger: true });
  if (!ok) return;
  try {
    await api.del(`/roles/${role.id}`, {});
    showToast('Role deleted', 'success');
    load();
  } catch (err) { showError(err); }
}

load();
