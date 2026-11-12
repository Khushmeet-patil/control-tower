/** "Change password" dialog, opened from the user menu. */
import { api } from '../core/api.js';
import { openFormModal } from './form-builder.js';
import { showToast } from './toast.js';

export function openChangePassword() {
  openFormModal({
    title: 'Change password',
    wide: false,
    submitLabel: 'Change password',
    fields: [
      { key: 'current_password', label: 'Current password', type: 'password', required: true, full: true },
      { key: 'new_password', label: 'New password', type: 'password', required: true, full: true, help: 'At least 8 characters.' },
    ],
    onSubmit: (v) => api.post('/auth/change-password', v),
    onDone: () => showToast('Password changed', 'success'),
  });
}
