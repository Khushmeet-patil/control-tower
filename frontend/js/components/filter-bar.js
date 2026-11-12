/**
 * A row of filter controls that reports a plain object of values.
 *
 * createFilterBar({
 *   fields: [
 *     { key: 'q', type: 'search', placeholder: 'Search…' },
 *     { key: 'status', type: 'select', label: 'Status', options: [{ value: 'open', label: 'Open' }] },
 *     { key: 'from', type: 'date', label: 'From' },
 *   ],
 *   onChange: (values) => table.setFilters(values),
 *   actions: [buttonNode],      // optional, shown on the right
 * }) → { element, getValues(), setValue(key, value), setOptions(key, options), reset() }
 */
import { icon } from '../core/icons.js';
import { debounce, el } from '../core/utils.js';

export function createFilterBar({ fields, onChange, actions = [] }) {
  const controls = new Map();
  const emit = () => onChange?.(getValues());
  const emitDebounced = debounce(emit, 300);

  function buildControl(field) {
    if (field.type === 'search') {
      const input = el('input', { class: 'ct-input', type: 'search', placeholder: field.placeholder || 'Search…', 'aria-label': field.label || 'Search', onInput: emitDebounced });
      return input;
    }
    if (field.type === 'select') {
      const select = el('select', { class: 'ct-select', 'aria-label': field.label, onChange: emit });
      fillOptions(select, field.label, field.options || []);
      return select;
    }
    if (field.type === 'date') {
      return el('input', { class: 'ct-input', type: 'date', 'aria-label': field.label, title: field.label, onChange: emit });
    }
    throw new Error(`Unknown filter type: ${field.type}`);
  }

  function fillOptions(select, label, options) {
    const current = select.value;
    select.replaceChildren(el('option', { value: '' }, `All ${label ? label.toLowerCase() : ''}`.trim()),
      ...options.map((o) => el('option', { value: o.value }, o.label ?? o.value)));
    if ([...select.options].some((o) => o.value === current)) select.value = current;
  }

  function getValues() {
    const values = {};
    for (const [key, control] of controls) if (control.value) values[key] = control.value;
    return values;
  }

  const element = el('div', { class: 'ct-toolbar' });
  for (const field of fields) {
    const control = buildControl(field);
    controls.set(field.key, control);
    if (field.type === 'search') {
      element.append(el('label', { style: { position: 'relative', display: 'inline-flex', alignItems: 'center' } },
        el('span', { class: 'ct-muted', style: { position: 'absolute', left: '10px', display: 'inline-flex' } }, icon('search', { size: 16 })),
        control));
      control.style.paddingLeft = '32px';
    } else {
      element.append(control);
    }
  }

  const resetBtn = el('button', { class: 'ct-btn ct-btn--ghost ct-btn--sm', type: 'button', onClick: () => reset() }, 'Clear');
  element.append(resetBtn, el('div', { class: 'ct-toolbar__spacer' }), ...actions);

  function reset() {
    for (const control of controls.values()) control.value = '';
    emit();
  }

  return {
    element,
    getValues,
    reset,
    setValue(key, value) { const c = controls.get(key); if (c) { c.value = value ?? ''; emit(); } },
    setOptions(key, options) {
      const field = fields.find((f) => f.key === key);
      fillOptions(controls.get(key), field?.label, options);
    },
  };
}
