/** Holidays (/pages/holidays.html): public holidays for the whole organisation or for a unit (and the
 *  units below it). Capacity treats them like time off for everyone they apply to. Each person's own
 *  working days are set on their profile (People → Edit → Working days). */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { el, formatDate } from '../core/utils.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { confirmDialog } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';
import { treeOptions } from '../components/tree.js';

const { user, content } = await initLayout({ active: 'holidays', title: 'Holidays', permission: 'people.view' });
const units = await api.get('/units').then((d) => d.items).catch(() => []);
const thisYear = new Date().getFullYear();
let year = thisYear;
const canAdd = can(user, 'settings.manage') || can(user, 'people.manage');

const list = el('section', { class: 'ct-card' });
const yearSelect = el('select', { class: 'ct-select', 'aria-label': 'Year', onChange: (e) => { year = Number(e.target.value); load(); } },
  [thisYear - 1, thisYear, thisYear + 1, thisYear + 2].map((y) => el('option', { value: y, selected: y === thisYear }, String(y))));

content.append(
  pageHeader('Holidays', 'Public holidays reduce everyone\'s available capacity on those days, like time off. A holiday set on a unit applies to its people and the units below it.',
    [yearSelect, canAdd ? el('button', { class: 'ct-btn ct-btn--primary', type: 'button', onClick: () => edit(null) }, icon('plus', { size: 16 }), 'Holiday') : null].filter(Boolean)),
  list);

async function load() {
  let data;
  try { data = await api.get('/holidays', { year }); } catch (err) { showError(err); return; }
  if (!data.items.length) {
    list.replaceChildren(createEmptyState({ title: `No holidays in ${year}`, message: canAdd ? 'Add the public holidays your people do not work.' : 'None have been set.', icon: 'sun' }));
    return;
  }
  list.replaceChildren(el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
    el('thead', {}, el('tr', {}, ['Date', 'Holiday', 'Applies to', ''].map((h) => el('th', {}, h)))),
    el('tbody', {}, data.items.map((h) => el('tr', {},
      el('td', {}, formatDate(h.holiday_date), el('div', { class: 'ct-muted ct-small' }, new Date(`${h.holiday_date}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long' }))),
      el('td', {}, h.name),
      el('td', {}, h.unit ? `${h.unit.name} and below` : 'Everyone'),
      el('td', {}, h.can_edit ? el('div', { style: { display: 'flex', gap: '6px' } },
        el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: () => edit(h) }, 'Edit'),
        el('button', { class: 'ct-btn ct-btn--sm ct-btn--danger', type: 'button', onClick: () => remove(h) }, 'Delete')) : null)))))));
}

function edit(h) {
  const everyone = can(user, 'settings.manage');
  openFormModal({
    title: h ? `Edit ${h.name}` : 'New holiday',
    fields: [
      { key: 'holiday_date', label: 'Date', type: 'date', required: true },
      { key: 'name', label: 'Name', required: true },
      { key: 'unit_id', label: 'Applies to', type: 'select', options: treeOptions(units), full: true,
        placeholder: everyone ? 'Everyone (the whole organisation)' : 'Choose a unit you manage' },
      h ? { key: 'reason', label: 'Reason for change', full: true } : null,
    ].filter(Boolean),
    values: h ? { holiday_date: h.holiday_date, name: h.name, unit_id: h.unit_id } : {},
    onSubmit: (v) => {
      const body = { ...v, unit_id: v.unit_id || null };
      return h ? api.patch(`/holidays/${h.id}`, { ...body, version: h.version }) : api.post('/holidays', body);
    },
    onDone: () => { showToast('Holiday saved', 'success'); load(); },
  });
}

async function remove(h) {
  if (!await confirmDialog({ title: `Delete ${h.name}?`, message: 'Capacity on that day goes back to normal.', confirmLabel: 'Delete', danger: true })) return;
  try { await api.del(`/holidays/${h.id}`, { reason: 'Holiday removed' }); load(); } catch (err) { showError(err); }
}

load();
