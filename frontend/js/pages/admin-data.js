/** Data & Backup (/pages/admin/data.html): the prototype's Data & Backup screen on the server.
 *  - Import: download a template, upload Excel or CSV, review the preview (nothing is saved yet; every
 *    row's outcome and every bad cell is listed), then import. Rows go through the same checks and audit
 *    log as screen edits.
 *  - Past imports, exports of the work list (Excel, CSV, JSON), and backup status for administrators. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { el, formatDateTime } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createDataTable } from '../components/data-table.js';
import { confirmDialog } from '../components/modal.js';
import { showError, showToast } from '../components/toast.js';

const { user, content } = await initLayout({ active: 'data', title: 'Data & Backup', permission: 'imports.run' });
const { items: entities } = await api.get('/imports/entities').catch((e) => { showError(e); return { items: [] }; });

const OUTCOME = {
  create: ['New', 'var(--ct-success)'], update: ['Update', 'var(--ct-accent)'], unchanged: ['No change', 'var(--ct-border-strong)'],
  invalid: ['Problem', 'var(--ct-danger)'], skipped: ['Skipped', 'var(--ct-border-strong)'],
};
const outcomeBadge = (a) => createBadge(...(OUTCOME[a] || [a, 'var(--ct-border-strong)']));
const STATUS = { previewed: ['Previewed, not imported', 'var(--ct-warning)'], committed: ['Imported', 'var(--ct-success)'], discarded: ['Discarded', 'var(--ct-border-strong)'] };
const MAX_BYTES = 5 * 1024 * 1024;

// ------------------------------------------------------------------ import
const entitySelect = el('select', { class: 'ct-select', id: 'import-entity', 'aria-label': 'What to import' },
  entities.map((e) => el('option', { value: e.code }, e.label)));
const modeSelect = el('select', { class: 'ct-select', id: 'import-mode', 'aria-label': 'Mode' },
  el('option', { value: 'add' }, 'Add only: refuse rows that already exist'),
  el('option', { value: 'update' }, 'Add and update: update existing rows with the filled-in cells'));
const fileInput = el('input', { class: 'ct-input', type: 'file', id: 'import-file', accept: '.xlsx,.csv', 'aria-label': 'File' });
const templateLink = el('a', { class: 'ct-btn' }, icon('upload', { size: 16 }), 'Download template');
const columnsNote = el('p', { class: 'ct-small ct-muted' });
const previewBtn = el('button', { class: 'ct-btn ct-btn--primary', onClick: preview }, 'Preview');
const resultSlot = el('div');

function describeEntity() {
  const e = entities.find((x) => x.code === entitySelect.value);
  if (!e) return;
  templateLink.href = `/api/v1/imports/templates/${e.code}.xlsx`;
  const required = e.columns.filter((c) => c.required).map((c) => c.label);
  columnsNote.textContent = `Each row is identified by ${e.identity}. Required columns: ${required.join(', ')}.`
    + (e.custom_columns.length ? ` Custom fields: ${e.custom_columns.join(', ')}.` : '') + (e.order_note ? ` ${e.order_note}` : '');
}
entitySelect.addEventListener('change', describeEntity);
describeEntity();

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = () => reject(new Error('The file could not be read'));
    reader.readAsDataURL(file);
  });
}

async function preview() {
  const file = fileInput.files[0];
  if (!file) { showToast('Choose an Excel or CSV file first', 'info'); return; }
  if (file.size > MAX_BYTES) { showToast('Files can be up to 5 MB; split it into smaller files', 'error'); return; }
  previewBtn.disabled = true;
  resultSlot.replaceChildren(el('p', { class: 'ct-muted' }, 'Checking every row…'));
  try {
    const batch = await api.post('/imports', { entity: entitySelect.value, mode: modeSelect.value, filename: file.name, content: await readFile(file) });
    showBatch(batch);
    pastImports.reload();
  } catch (err) {
    resultSlot.replaceChildren(el('div', { class: 'ct-form-error' }, err.message));
  } finally {
    previewBtn.disabled = false;
  }
}

function summaryLine(s) {
  return [s.create && `${s.create} new`, s.update && `${s.update} to update`, s.unchanged && `${s.unchanged} unchanged`,
    s.invalid && `${s.invalid} with problems`, s.skipped && `${s.skipped} example rows skipped`].filter(Boolean).join(' · ') || 'No rows';
}

function showBatch(batch) {
  const s = batch.summary;
  let onlyProblems = s.invalid > 0;
  const tableSlot = el('div');
  const draw = () => {
    const rows = batch.results.filter((r) => !onlyProblems || r.action === 'invalid');
    tableSlot.replaceChildren(rows.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
      el('thead', {}, el('tr', {}, ['Row', 'ID', 'Outcome', 'Details'].map((h) => el('th', {}, h)))),
      el('tbody', {}, rows.map((r) => el('tr', { class: r.action === 'invalid' ? 'is-late' : null },
        el('td', {}, String(r.row)), el('td', {}, r.key), el('td', {}, outcomeBadge(r.action)),
        el('td', {}, r.errors.length
          ? el('ul', { class: 'ct-error-list' }, r.errors.map((e) => el('li', {}, e.column ? `${e.column}: ${e.message}` : e.message)))
          : r.record ? (batch.entity === 'work_items' && r.record.id && batch.status === 'committed'
            ? el('a', { href: `/pages/item.html?id=${r.record.id}` }, r.record.label) : r.record.label) : r.note || ''))))))
      : el('p', { class: 'ct-muted' }, 'No rows with problems.'));
  };
  const toggle = el('label', { class: 'ct-checkbox' },
    el('input', { type: 'checkbox', checked: onlyProblems, onChange: (e) => { onlyProblems = e.target.checked; draw(); } }), 'Only rows with problems');
  const willSave = s.create + s.update;
  const actions = batch.can_commit ? [
    el('button', { class: 'ct-btn ct-btn--primary', disabled: !willSave, onClick: () => commit(batch, willSave) },
      `Import ${willSave} row${willSave === 1 ? '' : 's'}`),
    el('button', { class: 'ct-btn', onClick: () => discard(batch) }, 'Discard'),
  ] : [];
  draw();
  resultSlot.replaceChildren(el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, `${batch.filename} · ${batch.entity_label}`),
      createBadge(...STATUS[batch.status])),
    el('div', { class: 'ct-card__body ct-stack' },
      el('p', {}, el('strong', {}, summaryLine(s)),
        batch.status === 'previewed' ? el('span', { class: 'ct-muted' }, '. Nothing has been saved yet.') : null),
      s.invalid && batch.status === 'previewed' ? el('p', { class: 'ct-small ct-muted' }, 'Rows with problems are left out. Fix them in the file and upload it again, or import the rest now.') : null,
      s.ignored_columns?.length ? el('div', { class: 'ct-notice ct-notice--quiet' }, `Columns not recognised and ignored: ${s.ignored_columns.join(', ')}`) : null,
      el('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' } }, ...actions, toggle),
      tableSlot)));
}

async function commit(batch, n) {
  if (!await confirmDialog({ title: `Import ${n} rows?`, message: 'They are saved now, through the same checks as the screens, and recorded in the audit log. The file is checked again first, so changes made since the preview are taken into account.', confirmLabel: 'Import' })) return;
  try {
    const done = await api.post(`/imports/${batch.id}/commit`, {});
    showToast(`Imported: ${summaryLine(done.summary)}`, done.summary.invalid ? 'info' : 'success');
    showBatch(done);
    pastImports.reload();
  } catch (err) { showError(err); }
}

async function discard(batch) {
  try { showBatch(await api.post(`/imports/${batch.id}/discard`, {})); pastImports.reload(); } catch (err) { showError(err); }
}

// ------------------------------------------------------------------ past imports
const pastImports = createDataTable({
  columns: [
    { key: 'filename', label: 'File', render: (b) => el('div', { class: 'ct-work-title' }, el('strong', {}, b.filename),
      el('span', { class: 'ct-work-title__code' }, `${b.entity_label} · ${b.mode === 'update' ? 'add and update' : 'add only'}`)) },
    { key: 'status', label: 'Status', render: (b) => createBadge(...STATUS[b.status]) },
    { key: 'summary', label: 'Rows', render: (b) => summaryLine(b.summary) },
    { key: 'owner', label: 'By', render: (b) => b.owner?.full_name || '—' },
    { key: 'created_at', label: 'When', render: (b) => formatDateTime(b.committed_at || b.created_at) },
  ],
  fetchPage: (q) => api.get('/imports', q),
  onRowClick: async (b) => { try { showBatch(await api.get(`/imports/${b.id}`)); resultSlot.scrollIntoView({ behavior: 'smooth' }); } catch (err) { showError(err); } },
  pageSize: 10,
  emptyState: { title: 'No imports yet', icon: 'upload' },
});

// ------------------------------------------------------------------ exports
const exportBtn = (fmt, label) => el('a', { class: 'ct-btn', href: `/api/v1/exports/work-items.${fmt}?level=all` }, label);

// ------------------------------------------------------------------ backups
const backupSlot = el('div', { class: 'ct-card__body' }, el('p', { class: 'ct-muted' }, 'Loading…'));
async function loadBackups() {
  let s;
  try { s = await api.get('/backups'); } catch (err) { backupSlot.replaceChildren(el('p', { class: 'ct-muted' }, err.message)); return; }
  const kb = (b) => `${Math.max(1, Math.round(b / 1024)).toLocaleString()} KB`;
  backupSlot.replaceChildren(el('div', { class: 'ct-stack' },
    el('div', { class: `ct-notice${s.overdue ? ' ct-notice--warning' : ' ct-notice--quiet'}` },
      el('span', { class: 'ct-notice__text' }, s.last
        ? `Last backup ${formatDateTime(s.last.created_at)} (${s.age_days === 0 ? 'today' : `${s.age_days} day${s.age_days === 1 ? '' : 's'} ago`}), ${s.last.verified ? 'verified' : 'NOT verified'}. ${s.count} backups kept (${kb(s.total_bytes)}), each for ${s.keep_days} days.`
        : 'No backup has been taken yet.')),
    el('p', { class: 'ct-small ct-muted' }, 'Backups are taken on the server by a scheduled job, not from the browser: ',
      el('code', {}, 'flask --app run backup'), ' (daily). Restore with ', el('code', {}, 'flask --app run restore <file> --yes'),
      ' after stopping the app; the current data is backed up first. Keep a copy of the backup folder off this server.'),
    s.items.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
      el('thead', {}, el('tr', {}, ['Taken', 'File', 'Size', 'Checked', 'Work items'].map((h) => el('th', {}, h)))),
      el('tbody', {}, s.items.map((b) => el('tr', {},
        el('td', {}, formatDateTime(b.created_at)), el('td', {}, el('code', {}, b.file)), el('td', {}, kb(b.bytes)),
        el('td', {}, b.verified ? createBadge('Verified', 'var(--ct-success)') : createBadge('Not verified', 'var(--ct-danger)')),
        el('td', {}, b.row_counts?.work_items ?? '—')))))) : null));
}

content.append(
  pageHeader('Data & Backup', 'Bring spreadsheets in, take the data out, and check that backups are running.'),
  el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, 'Import from Excel or CSV')),
    el('div', { class: 'ct-card__body ct-stack' },
      el('p', { class: 'ct-small ct-muted' }, 'Start from the template: it lists every column, the allowed values and example rows (rows whose ID starts with EXAMPLE are skipped). Import people first, then work, then assignments. Dates may be 2026-12-31, 31/12/2026 or 31-Dec-2026.'),
      el('div', { class: 'ct-steps' },
        el('div', { class: 'ct-field' }, el('label', { class: 'ct-label', for: 'import-entity' }, '1. What'), entitySelect),
        el('div', { class: 'ct-field' }, el('label', { class: 'ct-label', for: 'import-mode' }, '2. Mode'), modeSelect),
        el('div', { class: 'ct-field' }, el('label', { class: 'ct-label', for: 'import-file' }, '3. File (.xlsx or .csv, up to 5 MB)'), fileInput)),
      columnsNote,
      el('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } }, previewBtn, templateLink))),
  resultSlot,
  el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, 'Past imports')), pastImports.element),
  el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, 'Export all the work you can see')),
    el('div', { class: 'ct-card__body', style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
      exportBtn('xlsx', 'Excel'), exportBtn('csv', 'CSV'), exportBtn('json', 'JSON'),
      el('span', { class: 'ct-small ct-muted', style: { alignSelf: 'center' } }, 'For a filtered list, use “Export to Excel” on the Portfolio.'))),
  can(user, 'settings.manage') ? el('section', { class: 'ct-card', id: 'backups' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, 'Backups')), backupSlot) : null);

if (can(user, 'settings.manage')) loadBackups();
