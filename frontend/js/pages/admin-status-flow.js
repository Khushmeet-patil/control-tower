/** Status flow (/pages/admin/status-flow.html): which status work may move to next, per item type.
 *  A status left "free" may change to anything. Rules for a type replace the "every type" rules for it.
 *  Edits are a draft; publish them from the banner. Approvals still move rejected work back themselves. */
import { api } from '../core/api.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge, lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createSettingsBanner } from '../components/settings-banner.js';
import { showError, showToast } from '../components/toast.js';

const { content } = await initLayout({ active: 'status-flow', title: 'Status flow', permission: 'settings.manage' });
const statuses = lookupValues('status');
const types = lookupValues('item_type');
let rules = [];
let scope = '';

const banner = createSettingsBanner({ onChange: load });
const typeSelect = el('select', { class: 'ct-select', 'aria-label': 'Item type', onChange: (e) => { scope = e.target.value; render(); } },
  el('option', { value: '' }, 'Every type (unless a type has its own rules)'), types.map((t) => el('option', { value: t.id }, t.label)));
const grid = el('section', { class: 'ct-card' });

content.append(
  pageHeader('Status flow', 'Choose where work may go next from each status. A status left free may change to anything; once every status is free, statuses change freely (as before). Draft until published.'),
  banner.element,
  el('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', margin: '0 0 16px' } }, el('span', { class: 'ct-label' }, 'Rules for'), typeSelect),
  grid);

async function load() {
  try { rules = (await api.get('/status-transitions')).items; } catch (err) { showError(err); return; }
  render();
  banner.refresh();
}

function render() {
  const typeId = scope ? Number(scope) : null;
  const mine = rules.filter((r) => r.item_type_id === typeId);
  const own = typeId !== null && mine.some((r) => r.is_active);
  const note = typeId === null ? 'These apply to every type that has no rules of its own.'
    : own ? 'This type has its own rules: the “every type” rules do not apply to it.'
      : 'This type has no rules of its own, so the “every type” rules apply. Limiting a status here gives it its own rules.';
  grid.replaceChildren(
    el('p', { class: 'ct-muted ct-small' }, note),
    el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table ct-pref-table' },
      el('thead', {}, el('tr', {}, el('th', {}, 'From'), el('th', {}, 'Limited?'), statuses.map((s) => el('th', {}, lookupBadge(s.id))), el('th', {}))),
      el('tbody', {}, statuses.map((from) => row(from, mine.find((r) => r.from_status_id === from.id), typeId))))));
}

function row(from, rule, typeId) {
  const limited = el('input', { type: 'checkbox', checked: !!rule?.is_active, 'aria-label': `Limit moves from ${from.label}` });
  const boxes = new Map();
  const cells = statuses.map((to) => {
    if (to.id === from.id) return el('td', { class: 'ct-muted' }, '—');
    const box = el('input', { type: 'checkbox', checked: (rule?.to_status_ids || []).includes(to.id), disabled: !rule?.is_active,
      'aria-label': `${from.label} → ${to.label}` });
    boxes.set(to.id, box);
    return el('td', {}, box);
  });
  limited.addEventListener('change', () => { for (const b of boxes.values()) b.disabled = !limited.checked; });
  const save = el('button', { class: 'ct-btn ct-btn--sm', type: 'button', onClick: async () => {
    const to = [...boxes].filter(([, b]) => b.checked).map(([id]) => id);
    try {
      if (rule) await api.patch(`/status-transitions/${rule.id}`, { to_status_ids: to, is_active: limited.checked, version: rule.version });
      else if (limited.checked) await api.post('/status-transitions', { item_type_id: typeId, from_status_id: from.id, to_status_ids: to });
      showToast('Saved to the draft', 'success');
      load();
    } catch (err) { showError(err); }
  } }, 'Save');
  return el('tr', {}, el('td', {}, lookupBadge(from.id)), el('td', {}, limited), cells, el('td', {}, save));
}

load();
