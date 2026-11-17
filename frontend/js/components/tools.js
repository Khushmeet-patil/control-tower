/**
 * Tools, shared by the Tool Centre and the item page's Tools tab.
 *
 *   createToolGrid(tools, { item, onChanged, onUse })  → grid of tool cards
 *   useTool(tool, { item, onChanged })                  → open a link, fill in a form, or answer a checklist
 *   openChecklistResults(tool)                          → a checklist's results across visible items
 *
 * Links: the address is never in the list; the server checks access, logs the opening and returns it.
 * Forms and checklists save to the work item, so they need one (`item`, the full item detail).
 */
import { api } from '../core/api.js';
import { el, formatDateTime } from '../core/utils.js';
import { lookupValue } from '../core/lookups.js';
import { withCustomValues } from './custom-fields.js';
import { openFormModal } from './form-builder.js';
import { openModal } from './modal.js';
import { showError, showToast } from './toast.js';
import { workItemFormFields } from './work-item-form.js';

export const KIND_LABEL = { link: 'Link', form: 'Form', checklist: 'Checklist' };
const KIND_HELP = {
  link: 'Opens in a new tab.',
  form: 'Fills in fields of a work item.',
  checklist: 'Readiness check on a work item.',
};

/** Where a tool applies, in words: "Organisation-wide", "PRJ-001 · Operations · Managers". */
export function appliesToText(tool) {
  const a = tool.applies_to;
  const parts = [
    ...a.work_items.map((w) => w.code),
    ...a.units.map((u) => u.name),
  ];
  const where = parts.length ? parts.join(', ') : 'Organisation-wide';
  const types = a.item_type_ids.map((id) => lookupValue(id)?.label).filter(Boolean);
  return [where, types.length ? `on ${types.join(', ').toLowerCase()}` : null,
    a.roles.length ? `for ${a.roles.map((r) => r.name).join(', ')}` : null].filter(Boolean).join(' · ');
}

export function scoreBadge(response, passPct) {
  if (!response) return el('span', { class: 'ct-tool-score is-none' }, 'Not assessed');
  return el('span', { class: `ct-tool-score ${response.passed ? 'is-pass' : 'is-fail'}`, title: `Pass mark ${passPct}%` },
    `${response.score_pct}% · ${response.passed ? 'ready' : 'not ready'}`);
}

function toolCard(tool, { item, onChanged, onUse }) {
  const action = (() => {
    if (tool.kind === 'link') return { label: 'Open', run: () => useTool(tool, { item, onChanged }) };
    if (item) return { label: tool.kind === 'checklist' ? (tool.response ? 'Update' : 'Assess') : 'Fill in', run: () => useTool(tool, { item, onChanged }) };
    return onUse ? { label: 'Use on an item…', run: () => onUse(tool) } : null;
  })();
  return el('article', { class: 'ct-card ct-tool-card' },
    el('div', { class: 'ct-tool-card__head' },
      el('span', { class: 'ct-tool-card__icon', 'aria-hidden': 'true' }, tool.icon || '🔗'),
      el('div', { class: 'ct-tool-card__title' },
        el('strong', {}, tool.name),
        el('span', { class: 'ct-muted ct-small' }, tool.kind === 'link' && tool.host ? `${KIND_LABEL.link} · ${tool.host}` : KIND_LABEL[tool.kind]))),
    tool.description ? el('p', { class: 'ct-tool-card__desc' }, tool.description) : null,
    el('div', { class: 'ct-muted ct-small' }, appliesToText(tool)),
    item && tool.kind === 'checklist' ? el('div', {}, scoreBadge(tool.response, tool.definition.pass_pct),
      tool.response ? el('span', { class: 'ct-muted ct-small' }, ` ${tool.response.submitted_by?.full_name || ''}, ${formatDateTime(tool.response.submitted_at)}`) : null) : null,
    el('div', { class: 'ct-tool-card__actions' },
      action ? el('button', { class: `ct-btn ct-btn--sm${tool.kind === 'link' ? ' ct-btn--primary' : ''}`, onClick: action.run,
        disabled: item && tool.kind === 'form' && tool.can_use === false ? true : null }, action.label) : null,
      !item && tool.kind === 'checklist' ? el('button', { class: 'ct-btn ct-btn--sm', onClick: () => openChecklistResults(tool) }, 'Results') : null,
      el('span', { class: 'ct-muted ct-small' }, item || tool.kind === 'link' ? '' : KIND_HELP[tool.kind])));
}

export function createToolGrid(tools, { item = null, onChanged, onUse } = {}) {
  return el('div', { class: 'ct-tool-grid' }, tools.map((t) => toolCard(t, { item, onChanged, onUse })));
}

export function useTool(tool, { item = null, onChanged } = {}) {
  if (tool.kind === 'link') return openLink(tool, item);
  if (!item) return null;
  return tool.kind === 'form' ? openToolForm(tool, item, onChanged) : openChecklist(tool, item, onChanged);
}

async function openLink(tool, item) {
  // Open the tab now (browsers block tabs opened after a network wait), then send it on once access is confirmed.
  const tab = window.open('about:blank', '_blank');
  if (tab) tab.opener = null;
  try {
    const { url } = await api.post(`/tools/${tool.id}/open`, { work_item_id: item?.id ?? null });
    if (tab) tab.location.href = url;
    else window.location.href = url;
  } catch (err) {
    tab?.close();
    showError(err);
  }
}

async function openToolForm(tool, item, onChanged) {
  const codes = tool.definition.fields.map((f) => f.code);
  const all = await workItemFormFields({ item });
  const fields = codes.map((c) => all.find((f) => f.key === c)).filter(Boolean);
  const editable = fields.filter((f) => !f.disabled);
  if (!editable.length) {
    openModal({ title: tool.name, body: el('p', {}, 'You cannot change these fields on this item. Its owners can.') });
    return;
  }
  openFormModal({
    title: `${tool.icon || ''} ${tool.name} · ${item.code}`.trim(),
    intro: [tool.description, 'Saved to the work item; the change is recorded in its history.'].filter(Boolean).join(' '),
    fields: [...fields, { key: 'reason', label: 'Reason for change', full: true, help: 'Saved in the audit log.' }],
    values: item,
    submitLabel: 'Save to item',
    onSubmit: (raw) => {
      const { reason, ...rest } = raw;
      const keep = Object.fromEntries(Object.entries(rest).filter(([k]) => editable.some((f) => f.key === k)));
      return api.post(`/tools/${tool.id}/submit`, { work_item_id: item.id, values: withCustomValues(keep), version: item.version, reason });
    },
    onDone: () => { showToast(`${tool.name} saved to ${item.code}`, 'success'); onChanged?.(); },
  });
}

function openChecklist(tool, item, onChanged) {
  const { items, pass_pct: passPct } = tool.definition;
  const current = tool.response;
  const readOnly = tool.can_use === false;
  openFormModal({
    title: `${tool.icon || ''} ${tool.name} · ${item.code}`.trim(),
    intro: [tool.description, `Pass mark: ${passPct}% of the items.`,
      current ? `Last saved by ${current.submitted_by?.full_name || 'someone'}, ${formatDateTime(current.submitted_at)}: ${current.score_pct}%.` : null,
      readOnly ? 'Only people working on this item can change the answers.' : null].filter(Boolean).join(' '),
    fields: [
      ...items.map((i) => ({ key: `a:${i.code}`, label: i.label, type: 'checkbox', full: true, disabled: readOnly })),
      { key: 'notes', label: 'Notes', type: 'textarea', disabled: readOnly },
      readOnly ? null : { key: 'reason', label: 'Reason for change', full: true, help: 'Saved in the audit log.' },
    ].filter(Boolean),
    values: { ...Object.fromEntries(items.map((i) => [`a:${i.code}`, Boolean(current?.answers?.[i.code])])), notes: current?.notes },
    submitLabel: readOnly ? 'Close' : 'Save',
    onSubmit: async (v) => {
      if (readOnly) return null;
      const answers = Object.fromEntries(items.map((i) => [i.code, Boolean(v[`a:${i.code}`])]));
      return api.put(`/tools/${tool.id}/response`, { work_item_id: item.id, answers, notes: v.notes, reason: v.reason, version: current?.version ?? null });
    },
    onDone: (saved) => {
      if (!saved) return;
      showToast(`${tool.name}: ${saved.score_pct}% (${saved.passed ? 'ready' : 'not ready'})`, saved.passed ? 'success' : 'info');
      onChanged?.();
    },
  });
}

export async function openChecklistResults(tool) {
  let data;
  try { data = await api.get(`/tools/${tool.id}/responses`); } catch (err) { showError(err); return; }
  const passPct = tool.definition.pass_pct;
  const body = data.items.length
    ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
      el('thead', {}, el('tr', {}, ['Item', 'Result', 'By', 'When'].map((h) => el('th', {}, h)))),
      el('tbody', {}, data.items.map((r) => el('tr', {},
        el('td', {}, el('a', { href: `/pages/item.html?id=${r.work_item.id}&tab=tools` }, `${r.work_item.code} ${r.work_item.title}`)),
        el('td', {}, scoreBadge(r, passPct)),
        el('td', {}, r.submitted_by?.full_name || '—'),
        el('td', {}, formatDateTime(r.submitted_at)))))))
    : el('p', { class: 'ct-muted' }, 'No work item you can see has been assessed yet.');
  openModal({ title: `${tool.name}: results`, body, wide: true });
}
