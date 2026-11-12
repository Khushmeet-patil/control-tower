/** Terminology: rename the words the platform uses (e.g. "People" → "Colleagues"). Edits are a draft. */
import { api } from '../core/api.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { clear, el } from '../core/utils.js';
import { openFormModal } from '../components/form-builder.js';
import { createSettingsBanner } from '../components/settings-banner.js';
import { showError, showToast } from '../components/toast.js';

const { content } = await initLayout({ active: 'terms', title: 'Terminology', permission: 'settings.manage' });

const banner = createSettingsBanner({ onChange: load });
const tbody = el('tbody');

content.append(
  pageHeader('Terminology', 'Rename the words used across the platform to match your organisation. Item type names (e.g. Programme) are edited under Lookups & colours.'),
  banner.element,
  el('section', { class: 'ct-card' },
    el('div', { class: 'ct-table-wrap' },
      el('table', { class: 'ct-table' },
        el('thead', {}, el('tr', {}, ['Term', 'Singular', 'Plural', 'Default'].map((h) => el('th', { scope: 'col' }, h)))),
        tbody))),
);

async function load() {
  try {
    const terms = (await api.get('/terms')).items;
    clear(tbody);
    for (const t of terms) {
      const renamed = t.singular !== t.default_singular || t.plural !== t.default_plural;
      tbody.append(el('tr', { class: 'is-clickable', tabindex: '0', onClick: () => edit(t), onKeydown: (e) => { if (e.key === 'Enter') edit(t); } },
        el('td', {}, el('div', { style: { fontWeight: 600 } }, t.default_singular), el('div', { class: 'ct-muted ct-small' }, t.description || '')),
        el('td', {}, t.singular),
        el('td', {}, t.plural),
        el('td', { class: 'ct-muted ct-small' }, renamed ? `${t.default_singular} / ${t.default_plural}` : 'Not renamed')));
    }
  } catch (err) { showError(err); }
  banner.refresh();
}

function edit(t) {
  const isRenamed = t.singular !== t.default_singular || t.plural !== t.default_plural;
  openFormModal({
    title: `Rename · ${t.default_singular}`,
    wide: false,
    intro: t.description,
    fields: [
      { key: 'singular', label: 'Singular', required: true, full: true },
      { key: 'plural', label: 'Plural', required: true, full: true },
      { key: 'reason', label: 'Reason for change', help: 'Saved in the audit log.', full: true },
    ],
    values: t,
    submitLabel: 'Save',
    extraActions: isRenamed ? [{
      label: 'Reset to default',
      onClick: async (close) => {
        try {
          await api.patch(`/terms/${t.id}`, { singular: t.default_singular, plural: t.default_plural, version: t.version, reason: 'Reset to default' });
          close();
          showToast('Term reset (draft)', 'success');
          load();
        } catch (err) { showError(err); }
      },
    }] : [],
    onSubmit: (v) => api.patch(`/terms/${t.id}`, { ...v, version: t.version }),
    onDone: () => { showToast('Term saved (draft)', 'success'); load(); },
  });
}

load();
