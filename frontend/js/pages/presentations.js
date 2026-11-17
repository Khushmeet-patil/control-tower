/** Presentations (/pages/presentations.html): management reviews made of dashboard pages with
 *  speaker notes. Present them full screen on live figures or from a snapshot; publish a review pack
 *  locked to an approved snapshot (it never changes afterwards); export to PowerPoint, PDF or Excel. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { el, formatDate } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createEmptyState } from '../components/empty-state.js';
import { createForm } from '../components/form-builder.js';
import { confirmDialog, openModal } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';

const { user, content } = await initLayout({ active: 'presentations', title: 'Presentations', permission: 'work.view' });

const list = el('div');
content.append(
  pageHeader('Presentations', 'Dashboard pages arranged into a review, with speaker notes. Present live, or publish a pack locked to an approved snapshot.',
    [el('button', { class: 'ct-btn ct-btn--primary', onClick: () => edit(null) }, icon('plus', { size: 16 }), 'New presentation')]),
  list);

const exportUrl = (p, fmt) => `/api/v1/presentations/${p.id}/export.${fmt}`;

function sourceText(p) {
  if (p.mode === 'live') return 'Live figures';
  return p.snapshot ? `Snapshot “${p.snapshot.label}”, ${formatDate(p.snapshot.as_of)}${p.snapshot.status === 'approved' ? '' : ' (not approved)'}` : 'Snapshot (missing)';
}

function card(p) {
  const btn = (label, onClick, variant) => el('button', { class: `ct-btn ct-btn--sm${variant ? ` ct-btn--${variant}` : ''}`, onClick }, label);
  return el('article', { class: 'ct-card ct-tool-card' },
    el('div', { class: 'ct-tool-card__head' },
      el('span', { class: 'ct-tool-card__icon', 'aria-hidden': 'true' }, icon('chart', { size: 20 })),
      el('div', { class: 'ct-tool-card__title' }, el('strong', {}, p.name),
        el('span', { class: 'ct-muted ct-small' }, `${p.pages.length} page${p.pages.length === 1 ? '' : 's'} · ${p.owner?.full_name || ''}${p.is_shared ? ' · shared' : ''}`))),
    el('div', { class: 'ct-tag-list' },
      p.status === 'published' ? createBadge('Published review pack', 'var(--ct-success)') : createBadge('Draft', 'var(--ct-border-strong)'),
      el('span', { class: 'ct-muted ct-small' }, sourceText(p))),
    p.description ? el('p', { class: 'ct-tool-card__desc' }, p.description) : null,
    el('div', { class: 'ct-tool-card__actions' },
      el('a', { class: 'ct-btn ct-btn--sm ct-btn--primary', href: `/pages/present.html?id=${p.id}` }, 'Present'),
      p.can_edit ? btn('Edit', () => edit(p)) : null,
      p.can_publish ? btn('Publish', () => publish(p)) : null,
      btn('Duplicate', () => duplicate(p)),
      ...['pptx', 'pdf', 'xlsx'].map((fmt) => el('a', { class: 'ct-btn ct-btn--sm ct-btn--ghost', href: exportUrl(p, fmt) }, fmt.toUpperCase())),
      p.can_edit ? btn('Delete', () => remove(p), 'danger') : null));
}

async function load() {
  try {
    const { items } = await api.get('/presentations');
    list.replaceChildren(items.length ? el('div', { class: 'ct-tool-grid' }, items.map(card))
      : el('section', { class: 'ct-card' }, createEmptyState({ title: 'No presentations yet', message: 'Put dashboards together into a review.', icon: 'chart' })));
  } catch (err) { showError(err); }
}

// ------------------------------------------------------------------ editor
async function edit(existing) {
  let dashboards; let snapshots;
  try {
    [dashboards, snapshots] = await Promise.all([api.get('/dashboards').then((d) => d.items), api.get('/snapshots', { per_page: 100 }).then((d) => d.items)]);
  } catch (err) { showError(err); return; }
  if (!dashboards.length) { showToast('Make a dashboard first: each page shows one.', 'info'); return; }
  const form = createForm({
    fields: [
      { key: 'name', label: 'Name', required: true, maxlength: 120 },
      { key: 'mode', label: 'Figures', type: 'select', required: true, options: [{ value: 'live', label: 'Live' }, { value: 'snapshot', label: 'From a snapshot' }] },
      { key: 'snapshot_id', label: 'Snapshot', type: 'select', help: 'Only approved snapshots can be published as a review pack.',
        options: snapshots.map((s) => ({ value: s.id, label: `${s.label} · ${formatDate(s.as_of)}${s.status === 'approved' ? '' : ' (draft)'}${s.is_baseline ? ' · baseline' : ''}` })) },
      can(user, 'dashboards.share') ? { key: 'is_shared', label: 'Shared', type: 'checkbox', checkboxLabel: 'Share with everyone (each sees only their own figures)' } : null,
      { key: 'description', label: 'Description', type: 'textarea' },
      existing ? { key: 'reason', label: 'Reason for change', full: true } : null,
    ].filter(Boolean),
    values: existing ? { ...existing } : { mode: 'live' },
  });

  const rows = el('div', { class: 'ct-stack', style: { gap: '8px' } });
  const pages = (existing?.pages || [{ dashboard_id: dashboards[0].id }]).map((p) => ({ ...p }));
  const options = (selected) => dashboards.map((d) => el('option', { value: String(d.id), selected: d.id === selected }, `${d.name}${d.is_shared ? '' : ' (personal)'}`));
  function draw() {
    rows.replaceChildren(...pages.map((p, i) => el('div', { class: 'ct-page-row' },
      el('div', { class: 'ct-page-row__head' },
        el('strong', {}, `Page ${i + 1}`),
        el('select', { class: 'ct-select', 'aria-label': 'Dashboard', onChange: (e) => { p.dashboard_id = Number(e.target.value); } }, options(p.dashboard_id)),
        el('input', { class: 'ct-input', placeholder: 'Title (default: the dashboard name)', value: p.title || '', 'aria-label': 'Page title', onInput: (e) => { p.title = e.target.value; } }),
        el('button', { class: 'ct-btn ct-btn--sm ct-btn--ghost', title: 'Move up', disabled: i === 0, onClick: () => { [pages[i - 1], pages[i]] = [pages[i], pages[i - 1]]; draw(); } }, '↑'),
        el('button', { class: 'ct-btn ct-btn--sm ct-btn--ghost', title: 'Move down', disabled: i === pages.length - 1, onClick: () => { [pages[i + 1], pages[i]] = [pages[i], pages[i + 1]]; draw(); } }, '↓'),
        el('button', { class: 'ct-btn ct-btn--sm ct-btn--ghost', title: 'Remove page', disabled: pages.length === 1, onClick: () => { pages.splice(i, 1); draw(); } }, icon('trash', { size: 14 }))),
      el('textarea', { class: 'ct-textarea', placeholder: 'Speaker notes', rows: 2, 'aria-label': 'Speaker notes', onInput: (e) => { p.notes = e.target.value; } }, p.notes || ''))));
  }
  draw();

  openModal({
    title: existing ? `Edit ${existing.name}` : 'New presentation',
    wide: true,
    body: el('div', { class: 'ct-stack' }, form.element,
      el('div', {}, el('h4', { class: 'ct-section-title' }, 'Pages'), rows,
        el('button', { class: 'ct-btn ct-btn--sm', style: { marginTop: '8px' }, onClick: () => { pages.push({ dashboard_id: dashboards[0].id }); draw(); } },
          icon('plus', { size: 14 }), 'Add page'))),
    actions: [{ label: 'Cancel' }, {
      label: existing ? 'Save' : 'Create', variant: 'primary',
      onClick: async (close) => {
        if (!form.validate()) return;
        const v = form.getValues();
        const body = { ...v, snapshot_id: v.mode === 'snapshot' ? v.snapshot_id : null,
          pages: pages.map((p) => ({ id: p.id, dashboard_id: p.dashboard_id, title: p.title || null, notes: p.notes || null })) };
        try {
          const saved = existing ? await api.patch(`/presentations/${existing.id}`, { ...body, version: existing.version })
            : await api.post('/presentations', Object.fromEntries(Object.entries(body).filter(([, x]) => x !== null && x !== undefined)));
          close();
          showToast(existing ? 'Saved' : `${saved.name} created`, 'success');
          load();
        } catch (err) { form.setErrors(err); }
      },
    }],
  });
}

async function publish(p) {
  if (!await confirmDialog({ title: `Publish ${p.name}?`,
    message: `It becomes a review pack locked to “${p.snapshot.label}”: its pages, filters and figures are frozen, and it can no longer be changed or deleted. Duplicate it later to make a new version.`,
    confirmLabel: 'Publish' })) return;
  try { await api.post(`/presentations/${p.id}/publish`, {}); showToast('Published', 'success'); load(); } catch (err) { showError(err); }
}

async function duplicate(p) {
  try { const copy = await api.post(`/presentations/${p.id}/duplicate`, {}); showToast(`${copy.name} created`, 'success'); load(); } catch (err) { showError(err); }
}

async function remove(p) {
  if (!await confirmDialog({ title: `Delete ${p.name}?`, message: 'The audit log keeps a record.', confirmLabel: 'Delete', danger: true })) return;
  try { await api.del(`/presentations/${p.id}`, { reason: 'Not needed' }); showToast('Deleted', 'success'); load(); } catch (err) { showError(err); }
}

load();
