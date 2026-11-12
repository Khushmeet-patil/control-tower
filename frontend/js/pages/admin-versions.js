/** Settings versions: every publish is kept; any earlier version can be made live again. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { loadSettings } from '../core/lookups.js';
import { el, formatDateTime } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createDataTable } from '../components/data-table.js';
import { createForm } from '../components/form-builder.js';
import { openModal } from '../components/modal.js';
import { createSettingsBanner } from '../components/settings-banner.js';
import { showToast } from '../components/toast.js';

const { content } = await initLayout({ active: 'versions', title: 'Settings versions', permission: 'settings.manage' });

const banner = createSettingsBanner({ onChange: () => table.reload(), historyLink: false });

const table = createDataTable({
  columns: [
    { key: 'number', label: 'Version', sortable: true, render: (v) => el('span', {}, el('strong', {}, `v${v.number}`), ' ', v.is_current ? createBadge('Live', 'var(--ct-success)') : null) },
    { key: 'note', label: 'Note', render: (v) => v.note || el('span', { class: 'ct-muted' }, '—') },
    { key: 'change_count', label: 'Changes', render: (v) => String(v.change_count) },
    { key: 'published_at', label: 'Published', render: (v) => el('span', {}, formatDateTime(v.published_at), el('div', { class: 'ct-muted ct-small' }, v.published_by_name || '')) },
    {
      key: 'actions', label: '', render: (v) => (v.is_current ? null : el('button', {
        class: 'ct-btn ct-btn--sm', onClick: (e) => { e.stopPropagation(); rollback(v); },
      }, icon('refresh', { size: 16 }), 'Roll back to this')),
    },
  ],
  fetchPage: (params) => api.get('/settings/versions', params),
  defaultSort: '-number',
  emptyState: { title: 'No versions yet', icon: 'versions' },
});

content.append(
  pageHeader('Settings versions', 'Each publish of lookups, custom fields and terminology is kept here. Rolling back publishes the older settings as a new version, so nothing is lost.'),
  banner.element,
  el('section', { class: 'ct-card' }, table.element),
);

function rollback(version) {
  const form = createForm({ fields: [{ key: 'reason', label: 'Reason', full: true, placeholder: 'Why go back?' }], columns: 1 });
  openModal({
    title: `Roll back to version ${version.number}?`,
    body: el('div', { class: 'ct-stack' },
      el('p', {}, `Settings go back to how they were in version ${version.number} (${version.note || 'no note'}). This is published straight away as a new version.`),
      el('p', { class: 'ct-muted ct-small' }, 'Unpublished draft changes are replaced. Lists, values and fields added since then are retired, not deleted, so existing records keep their labels.'),
      form.element),
    actions: [
      { label: 'Cancel' },
      {
        label: 'Roll back', variant: 'danger',
        onClick: async (close) => {
          try {
            const v = await api.post(`/settings/versions/${version.id}/rollback`, form.getValues());
            close();
            showToast(`Rolled back. Version ${v.number} is live.`, 'success');
            await loadSettings({ refresh: true });
            banner.refresh();
            table.reload();
          } catch (err) { form.setErrors(err); }
        },
      },
    ],
  });
}

banner.refresh();
