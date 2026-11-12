/**
 * Draft/publish bar shown on every settings screen.
 *
 *   const banner = createSettingsBanner({ onChange: reloadPage });
 *   content.append(banner.element);
 *   banner.refresh();   // call after every draft edit
 *
 * Edits to lookups, custom fields and terms are a DRAFT. Nothing changes for other users until
 * an admin publishes; the draft can also be discarded. Older versions are on the versions page.
 */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { loadSettings } from '../core/lookups.js';
import { el, formatDateTime, formatValue, humanize } from '../core/utils.js';
import { createForm } from './form-builder.js';
import { confirmDialog, openModal } from './modal.js';
import { showError, showToast } from './toast.js';

const CHANGE_TEXT = { added: 'Added', changed: 'Changed', retired: 'Retired', restored: 'Restored', removed: 'Removed' };

export function changeListNode(changes) {
  return el('ul', { class: 'ct-change-list' }, changes.map((c) => el('li', {},
    el('strong', {}, `${CHANGE_TEXT[c.change] || humanize(c.change)}: `), c.name,
    c.change === 'changed' && c.fields?.length
      ? el('span', { class: 'ct-muted' }, ' — ', c.fields.map((f) => `${humanize(f.field)} ${formatValue(f.old)} → ${formatValue(f.new)}`).join('; '))
      : null)));
}

export function createSettingsBanner({ onChange, historyLink = true } = {}) {
  const element = el('div', { class: 'ct-notice ct-notice--quiet' }, 'Checking settings…');
  let status = null;

  async function refresh() {
    try {
      status = await api.get('/settings/status');
      render();
    } catch (err) { showError(err); }
  }

  function render() {
    const live = status.current
      ? `Live: version ${status.current.number}, published ${formatDateTime(status.current.published_at)} by ${status.current.published_by_name}.`
      : 'Nothing published yet.';
    if (!status.has_changes) {
      element.className = 'ct-notice ct-notice--quiet';
      element.replaceChildren(el('span', { class: 'ct-notice__text' }, live, ' No unpublished changes.'),
        historyLink ? el('a', { class: 'ct-btn ct-btn--sm ct-btn--ghost', href: '/pages/admin/versions.html' }, icon('versions', { size: 16 }), 'History') : null);
      return;
    }
    const n = status.changes.length;
    element.className = 'ct-notice';
    element.replaceChildren(
      el('span', { class: 'ct-notice__text' },
        el('strong', {}, `${n} unpublished change${n === 1 ? '' : 's'}. `),
        'Other people keep seeing the live version until you publish. ', el('span', { class: 'ct-muted' }, live)),
      el('button', { class: 'ct-btn ct-btn--sm', onClick: discard }, 'Discard'),
      el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: review }, icon('upload', { size: 16 }), 'Review & publish'));
  }

  function review() {
    const form = createForm({ fields: [{ key: 'note', label: 'What changed (optional)', full: true, placeholder: 'e.g. Added Business Impact field' }], columns: 1 });
    openModal({
      title: 'Publish settings',
      wide: true,
      body: el('div', { class: 'ct-stack' },
        el('p', { class: 'ct-muted ct-small' }, 'These changes go live for everyone. You can roll back to an earlier version at any time.'),
        changeListNode(status.changes), form.element),
      actions: [
        { label: 'Cancel' },
        {
          label: 'Publish', variant: 'primary',
          onClick: async (close) => {
            try {
              const v = await api.post('/settings/publish', form.getValues());
              close();
              showToast(`Version ${v.number} is live`, 'success');
              await loadSettings({ refresh: true });
              await refresh();
              onChange?.();
            } catch (err) { form.setErrors(err); }
          },
        },
      ],
    });
  }

  async function discard() {
    const ok = await confirmDialog({
      title: 'Discard unpublished changes?',
      message: `All ${status.changes.length} changes go back to the live version. New lists, values and fields are retired, not deleted.`,
      confirmLabel: 'Discard changes', danger: true,
    });
    if (!ok) return;
    try {
      await api.post('/settings/discard', {});
      showToast('Changes discarded', 'success');
      await refresh();
      onChange?.();
    } catch (err) { showError(err); }
  }

  return { element, refresh };
}
