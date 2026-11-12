/**
 * One screen for every hierarchy: tree on the left, details + members on the right.
 * Used by Organisation (administrative units) and Functions (functional hierarchy).
 * Each page passes a config — see organisation.js and functions.js.
 */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { clear, el, humanize } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createDataTable } from '../components/data-table.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog } from '../components/modal.js';
import { createPersonCell } from '../components/person.js';
import { showError, showToast } from '../components/toast.js';
import { createTree, treeOptions } from '../components/tree.js';

export async function mountHierarchyPage(cfg) {
  const { user, content } = await initLayout({ active: cfg.navKey, title: cfg.title, permission: cfg.viewPermission });
  const canManage = can(user, cfg.managePermission);
  const isGlobal = user.is_admin || user.scope === 'all';

  let items = [];
  let types = [];
  let current = null;

  // ---------------------------------------------------------------- layout
  const detailCard = el('section', { class: 'ct-card' });
  const membersCard = el('section', { class: 'ct-card' });
  const search = el('input', { class: 'ct-input', type: 'search', placeholder: `Search ${cfg.plural}…`, 'aria-label': `Search ${cfg.plural}` });
  const tree = createTree({
    label: (i) => i.name,
    meta: (i) => (i.member_count ? String(i.member_count) : ''),
    color: cfg.hasTypes ? (i) => i.unit_type?.color : null,
    onSelect: (item) => showDetail(item.id),
    emptyText: `No ${cfg.plural} yet`,
  });
  search.addEventListener('input', () => tree.filter(search.value));

  const topActions = [];
  if (canManage && (isGlobal || !cfg.hasTypes)) {
    topActions.push(el('button', { class: 'ct-btn ct-btn--primary', onClick: () => openEditor(null, null) },
      icon('plus', { size: 16 }), `New ${cfg.hasTypes ? 'top-level ' : ''}${cfg.singular}`));
  }

  content.append(
    pageHeader(cfg.title, cfg.subtitle, topActions),
    el('div', { class: 'ct-split' },
      el('section', { class: 'ct-card' },
        el('div', { class: 'ct-card__header' }, el('h3', {}, 'Structure'), el('span', { class: 'ct-muted ct-small' }, 'People')),
        el('div', { style: { padding: '12px 12px 0' } }, search),
        tree.element),
      el('div', { class: 'ct-stack' }, detailCard, membersCard)),
  );

  // ---------------------------------------------------------------- data
  async function loadTree(selectId) {
    const data = await api.get(cfg.endpoint);
    items = data.items;
    tree.setItems(items);
    const target = selectId ?? Number(new URLSearchParams(location.search).get('id')) ?? null;
    const fallback = items.find((i) => !items.some((p) => p.id === i.parent_id));
    const pick = items.find((i) => i.id === target) || fallback;
    if (pick) showDetail(pick.id); else renderEmpty();
  }

  function renderEmpty() {
    clear(detailCard).append(createEmptyState({ title: `No ${cfg.plural} yet`, message: canManage ? `Create the first ${cfg.singular} to get started.` : '' }));
    clear(membersCard);
  }

  async function showDetail(id) {
    tree.highlightOnly(id);
    history.replaceState(null, '', `?id=${id}`);
    try {
      current = await api.get(`${cfg.endpoint}/${id}`);
      renderDetail(current);
      renderMembers(current);
    } catch (err) { showError(err); }
  }

  // ---------------------------------------------------------------- detail
  function renderDetail(d) {
    const manageThis = canManage && d.can_manage;
    const leader = d[cfg.leaderKey];
    const actions = [];
    if (manageThis) {
      actions.push(el('button', { class: 'ct-btn ct-btn--sm', onClick: () => openEditor(null, d) }, icon('plus', { size: 16 }), `Add ${cfg.childLabel}`));
      actions.push(el('button', { class: 'ct-btn ct-btn--sm', onClick: () => openEditor(d, null) }, icon('edit', { size: 16 }), 'Edit'));
      if (d.can_move_or_delete) {
        actions.push(el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', onClick: () => remove(d) }, icon('trash', { size: 16 }), 'Delete'));
      }
    }
    const crumbs = d.path.length ? el('nav', { class: 'ct-breadcrumb', 'aria-label': 'Path' },
      d.path.flatMap((p) => [
        p.visible ? el('a', { href: `?id=${p.id}`, onClick: (e) => { e.preventDefault(); showDetail(p.id); } }, p.name) : el('span', {}, p.name),
        el('span', { class: 'ct-breadcrumb__sep' }, '/'),
      ]), el('span', {}, d.name)) : null;

    const kv = (label, value) => [el('dt', {}, label), el('dd', {}, value)];
    clear(detailCard).append(
      el('div', { class: 'ct-card__body ct-stack' },
        crumbs,
        el('div', { class: 'ct-detail-head' },
          el('div', { class: 'ct-detail-head__title' },
            el('h2', {}, d.name),
            cfg.hasTypes && d.unit_type ? createBadge(d.unit_type.name, d.unit_type.color) : null),
          el('div', { class: 'ct-actions' }, actions)),
        el('dl', { class: 'ct-kv' },
          kv(cfg.leaderLabel, createPersonCell(leader)),
          kv('Code', d.code || '—'),
          kv(humanize(cfg.childPlural), String(d.child_count)),
          kv('People (direct)', String(d.member_count)),
          kv('Description', d.description || '—'))));
  }

  // ---------------------------------------------------------------- members
  function renderMembers(d) {
    const include = el('input', { type: 'checkbox' });
    const table = createDataTable({
      columns: [
        { key: 'full_name', label: 'Name', sortable: true, render: (p) => createPersonCell(p, p.email) },
        { key: 'job_title', label: 'Job title', sortable: true },
        cfg.memberFilter === 'unit_id'
          ? { key: 'function', label: 'Function', render: (p) => p.function?.name || '—' }
          : { key: 'unit', label: 'Unit', render: (p) => p.unit?.name || '—' },
        { key: 'manager', label: 'Reports to', render: (p) => p.manager?.full_name || '—' },
      ],
      fetchPage: (params) => api.get('/people', { ...params, [cfg.memberFilter]: d.id, include_descendants: include.checked ? '1' : '' }),
      defaultSort: 'full_name',
      pageSize: 10,
      onRowClick: (p) => { location.href = `/pages/people.html?person=${p.id}`; },
      emptyState: { title: 'No people', message: `Nobody you can see is in this ${cfg.singular}.`, icon: 'users' },
    });
    include.addEventListener('change', () => table.reload());
    clear(membersCard).append(
      el('div', { class: 'ct-card__header' },
        el('h3', {}, 'People'),
        el('label', { class: 'ct-checkbox' }, include, `Include ${cfg.childPlural}`)),
      table.element);
  }

  // ---------------------------------------------------------------- create / edit / delete
  async function openEditor(existing, parent) {
    if (cfg.hasTypes && !types.length) types = (await api.get('/unit-types')).items;
    // A node cannot move under itself or its descendants.
    const blocked = new Set();
    if (existing) {
      const stack = [existing.id];
      while (stack.length) {
        const id = stack.pop();
        blocked.add(id);
        items.filter((i) => i.parent_id === id).forEach((c) => stack.push(c.id));
      }
    }
    const parentOptions = treeOptions(items.filter((i) => !blocked.has(i.id)));
    const fields = [
      { key: 'name', label: 'Name', required: true, maxlength: 200 },
      { key: 'code', label: 'Code', maxlength: 50, help: 'Optional short code, unique.' },
      cfg.hasTypes ? { key: 'unit_type_id', label: 'Type', type: 'select', required: true, options: types.map((t) => ({ value: t.id, label: t.name })) } : null,
      {
        key: 'parent_id', label: `Parent ${cfg.singular}`, type: 'select', options: parentOptions,
        placeholder: '— Top level —', disabled: existing && !existing.can_move_or_delete,
        help: existing && !existing.can_move_or_delete ? 'You cannot move the top unit of your own area.' : null,
      },
      { key: cfg.leaderField, label: cfg.leaderLabel, type: 'person', value: existing?.[cfg.leaderKey] },
      { key: 'description', label: 'Description', type: 'textarea' },
      existing ? { key: 'reason', label: 'Reason for change', help: 'Saved in the audit log.', full: true } : null,
    ].filter(Boolean);

    const defaults = existing
      ? { ...existing }
      : { parent_id: parent?.id ?? null, unit_type_id: cfg.hasTypes ? suggestType(parent) : undefined };

    openFormModal({
      title: existing ? `Edit ${existing.name}` : parent ? `Add ${cfg.childLabel} to ${parent.name}` : `New ${cfg.singular}`,
      fields,
      values: defaults,
      submitLabel: existing ? 'Save changes' : `Create ${cfg.singular}`,
      onSubmit: (values) => {
        if (existing) {
          if (!existing.can_move_or_delete) delete values.parent_id;
          return api.patch(`${cfg.endpoint}/${existing.id}`, { ...values, version: existing.version });
        }
        delete values.reason;
        return api.post(cfg.endpoint, values);
      },
      onDone: (saved) => {
        showToast(existing ? 'Changes saved' : `${humanize(cfg.singular)} created`, 'success');
        loadTree(saved.id).catch(showError);
      },
    });
  }

  /** Suggest the next level down (e.g. a Division's child is a Department). */
  function suggestType(parent) {
    if (!types.length) return undefined;
    if (!parent?.unit_type) return types[0].id;
    const idx = types.findIndex((t) => t.id === parent.unit_type.id);
    return (types[idx + 1] || types[types.length - 1]).id;
  }

  async function remove(d) {
    const ok = await confirmDialog({
      title: `Delete ${d.name}?`,
      message: `The ${cfg.singular} is removed from the structure. Its history stays in the audit log.`,
      confirmLabel: 'Delete', danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`${cfg.endpoint}/${d.id}`, {});
      showToast(`${humanize(cfg.singular)} deleted`, 'success');
      await loadTree(d.parent_id);
    } catch (err) { showError(err); }
  }

  await loadTree().catch(showError);
}
