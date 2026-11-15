/** Health rules: the checks that colour work Red, Amber or Grey (and the data-quality flags), with their
 *  thresholds, recommended actions, escalation and Action Centre score. Edits are a draft; publish them. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge, lookupOptions, lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createEmptyState } from '../components/empty-state.js';
import { openFormModal } from '../components/form-builder.js';
import { openModal } from '../components/modal.js';
import { createSettingsBanner } from '../components/settings-banner.js';
import { showError, showToast } from '../components/toast.js';

const { content } = await initLayout({ active: 'rules', title: 'Health rules', permission: 'settings.manage' });

let data = { items: [], types: [], choices: {}, kinds: {}, outcomes: {}, escalate_to: {} };
const banner = createSettingsBanner({ onChange: load });
const body = el('div', { class: 'ct-stack' });
const healthId = (code) => lookupValues('health', { includeRetired: true }).find((v) => v.code === code)?.id;

content.append(
  pageHeader('Health rules',
    'Each rule checks every item of the chosen types. Health is the worst colour any health rule gives, and parents take the worst colour of their children. Data-quality rules only raise flags. Missing information is Grey, never Green.',
    [el('button', { class: 'ct-btn ct-btn--primary', onClick: () => chooseType() }, icon('plus', { size: 16 }), 'New rule')]),
  banner.element, body);

async function load() {
  try {
    data = await api.get('/health-rules');
    render();
  } catch (err) { showError(err); }
  banner.refresh();
}

function paramText(rule) {
  const type = data.types.find((t) => t.code === rule.rule_type);
  return (type?.params || []).map((p) => {
    const v = rule.params[p.key];
    if (Array.isArray(v)) return v.length ? `${p.label}: ${v.map((id) => lookupValues(p.type.split(':')[1], { includeRetired: true }).find((x) => x.id === id)?.label || id).join(', ')}` : null;
    if (p.type.startsWith('choice:')) return `${p.label}: ${data.choices[p.type.split(':')[1]]?.[v] || v}`;
    return v ? `${p.label}: ${v}` : null;
  }).filter(Boolean).join(' · ');
}

function render() {
  body.replaceChildren(...Object.entries(data.kinds).map(([kind, label]) => {
    const rules = data.items.filter((r) => r.kind === kind);
    return el('section', { class: 'ct-card' },
      el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, `${label} rules`),
        el('span', { class: 'ct-muted ct-small' }, kind === 'health' ? 'Colour the item and everything above it' : 'Listed as flags; do not change the colour')),
      rules.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
        el('thead', {}, el('tr', {}, ['Rule', 'Condition', 'Applies to', 'Gives', 'Score', 'Escalate to', 'Status', ''].map((h) => el('th', {}, h)))),
        el('tbody', {}, rules.map((r) => el('tr', {
          class: `is-clickable${r.is_active ? '' : ' ct-row-retired'}`, tabindex: '0',
          onClick: () => editRule(r), onKeydown: (e) => { if (e.key === 'Enter') editRule(r); },
        },
          el('td', {}, el('strong', {}, r.name), r.recommended_action ? el('div', { class: 'ct-muted ct-small' }, `Next: ${r.recommended_action}`) : null),
          el('td', { class: 'ct-small' }, r.rule_type_label, paramText(r) ? el('div', { class: 'ct-muted' }, paramText(r)) : null),
          el('td', {}, r.item_type_ids.length ? el('div', { class: 'ct-tag-list' }, r.item_type_ids.map((id) => lookupBadge(id))) : 'Every type'),
          el('td', {}, healthId(r.outcome) ? lookupBadge(healthId(r.outcome)) : createBadge(r.outcome)),
          el('td', {}, String(r.score)),
          el('td', { class: 'ct-small' }, data.escalate_to[r.escalate_to] || r.escalate_to),
          el('td', {}, r.is_active ? 'Active' : 'Retired'),
          el('td', { style: { textAlign: 'right' } }, icon('edit', { size: 16 })))))))
        : el('div', { class: 'ct-card__body' }, createEmptyState({ title: 'No rules', icon: 'target' })));
  }));
}

function chooseType() {
  const modal = openModal({
    title: 'New rule: what should it check?',
    wide: true,
    body: el('div', { class: 'ct-type-grid' }, data.types.map((t) => el('button', {
      class: 'ct-btn ct-type-grid__btn', type: 'button', title: t.description, style: { height: 'auto', padding: '10px 12px', flexDirection: 'column', alignItems: 'flex-start', whiteSpace: 'normal', textAlign: 'left' },
      onClick: () => { modal.close(); editRule(null, t.code); },
    }, el('strong', {}, t.label), el('span', { class: 'ct-muted ct-small' }, t.description)))),
    actions: [{ label: 'Cancel' }],
  });
}

function paramFields(type, values) {
  return type.params.map((p) => {
    const key = `param.${p.key}`;
    const value = values?.[p.key] ?? p.default;
    if (p.type.startsWith('lookup:')) return { key, label: p.label, type: 'checkboxes', options: lookupOptions(p.type.split(':')[1], value), value, help: p.help };
    if (p.type.startsWith('choice:')) return { key, label: p.label, type: 'select', required: true, value,
      options: Object.entries(data.choices[p.type.split(':')[1]] || {}).map(([v, l]) => ({ value: v, label: l })) };
    return { key, label: p.label, type: 'number', value, help: p.help };
  });
}

function editRule(rule, newType = null) {
  const type = data.types.find((t) => t.code === (rule?.rule_type || newType));
  openFormModal({
    title: rule ? `Edit rule · ${rule.name}` : `New rule · ${type.label}`,
    intro: type.description,
    fields: [
      { key: 'name', label: 'Name', required: true, help: 'Shown with every finding, e.g. “Overdue (high priority)”.' },
      rule ? null : { key: 'code', label: 'Code', required: true, help: 'Lowercase letters, numbers and _. Cannot change later.' },
      { key: 'kind', label: 'Kind', type: 'select', required: true, options: Object.entries(data.kinds).map(([value, label]) => ({ value, label })) },
      { key: 'outcome', label: 'Colour it gives', type: 'select', required: true, options: Object.entries(data.outcomes).map(([value, label]) => ({ value, label })) },
      ...paramFields(type, rule?.params),
      { key: 'item_type_ids', label: 'Checks these item types', type: 'checkboxes', options: lookupOptions('item_type', rule?.item_type_ids || []), help: 'None ticked = every type.' },
      { key: 'score', label: 'Action Centre score (0–100)', type: 'number', required: true, help: 'Base points when ranking the Top 5; priority and days late are added.' },
      { key: 'escalate_to', label: 'Escalate to', type: 'select', required: true, options: Object.entries(data.escalate_to).map(([value, label]) => ({ value, label })) },
      { key: 'recommended_action', label: 'Recommended action', type: 'textarea', help: 'You can use {accountable}, {responsible}, {escalation}, {days} and {item}.' },
      { key: 'sort_order', label: 'Order', type: 'number' },
      rule ? { key: 'is_active', label: 'Active', type: 'checkbox', checkboxLabel: 'Active (untick to retire)' } : null,
      { key: 'description', label: 'Notes', type: 'textarea' },
      rule ? { key: 'reason', label: 'Reason for change', full: true, help: 'Saved in the audit log.' } : null,
    ].filter(Boolean),
    values: rule || { kind: 'health', outcome: 'amber', score: 50, escalate_to: 'accountable' },
    submitLabel: rule ? 'Save rule' : 'Create rule',
    onSubmit: (v) => {
      const params = {};
      const out = {};
      for (const [k, value] of Object.entries(v)) {
        if (k.startsWith('param.')) params[k.slice(6)] = value ?? (type.params.find((p) => p.key === k.slice(6))?.type.startsWith('lookup:') ? [] : 0);
        else out[k] = value;
      }
      const payload = { ...out, params };
      return rule ? api.patch(`/health-rules/${rule.id}`, { ...payload, version: rule.version })
        : api.post('/health-rules', { ...payload, rule_type: type.code });
    },
    onDone: () => { showToast('Saved as a draft. Publish to use it.', 'success'); load(); },
  });
}

load();
