/**
 * Builds forms from a list of field definitions — every create/edit screen uses this, and in
 * Phase 2 admin-defined custom fields will flow through it unchanged.
 *
 * const form = createForm({
 *   fields: [
 *     { key: 'name', label: 'Name', type: 'text', required: true },
 *     { key: 'unit_id', label: 'Unit', type: 'select', options: [{ value: 1, label: 'Engineering' }] },
 *     { key: 'manager_id', label: 'Reports to', type: 'person', value: { id, full_name } },
 *     { key: 'role_ids', label: 'Roles', type: 'checkboxes', options: [...], full: true },
 *     { key: 'is_active', label: 'Active', type: 'checkbox' },
 *   ],
 *   values: { name: 'Platform Team' },
 * });
 * form.getValues()    → { name, unit_id (number|null), manager_id, role_ids: [..], is_active }
 * form.setErrors(err) → shows an ApiError on the matching field (or at the top)
 *
 * Types: text, email, password, number, date, url, color, textarea, select, checkbox,
 *        checkboxes (multiselect is the same), person, people (several persons → [ids]).
 * Person fields accept `onChange(person)`.
 * Admin-defined custom fields become these definitions via components/custom-fields.js.
 */
import { el } from '../core/utils.js';
import { openModal } from './modal.js';
import { createPeoplePicker, createPersonPicker } from './person-picker.js';

let uid = 0;

export function createForm({ fields, values = {}, columns = 2 }) {
  const controls = new Map();
  const wrappers = new Map();
  const formError = el('div', { class: 'ct-form-error ct-hidden', role: 'alert', style: { marginBottom: '16px' } });

  function buildControl(field, id) {
    // `field.value` overrides the record value — e.g. a person field holds { id, full_name }, not just the id.
    const value = field.value !== undefined ? field.value : (values[field.key] ?? field.default);
    switch (field.type) {
      case 'textarea':
        return { node: el('textarea', { class: 'ct-textarea', id, placeholder: field.placeholder, disabled: field.disabled }, value ?? ''),
          get: (n) => n.value.trim() || null };
      case 'select': {
        const options = field.options || [];
        const select = el('select', { class: 'ct-select', id, disabled: field.disabled },
          field.required && value != null ? null : el('option', { value: '' }, field.placeholder || '— None —'),
          options.map((o, i) => el('option', { value: String(i), selected: o.value === value }, o.label)));
        return { node: select, get: (n) => (n.value === '' ? null : options[Number(n.value)].value) };
      }
      case 'checkbox': {
        const box = el('input', { type: 'checkbox', id, checked: Boolean(value), disabled: field.disabled });
        return { node: el('label', { class: 'ct-checkbox' }, box, field.checkboxLabel || field.label), get: () => box.checked, labelInside: true };
      }
      case 'color': {
        const start = /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#94A3B8';
        const swatch = el('input', { type: 'color', class: 'ct-color__swatch', value: start, disabled: field.disabled, 'aria-label': field.label });
        const hex = el('input', { class: 'ct-input', id, value: start.toUpperCase(), maxlength: 7, disabled: field.disabled });
        swatch.addEventListener('input', () => { hex.value = swatch.value.toUpperCase(); });
        hex.addEventListener('input', () => { if (/^#[0-9a-f]{6}$/i.test(hex.value)) swatch.value = hex.value; });
        return { node: el('div', { class: 'ct-color' }, swatch, hex), get: () => hex.value.trim().toUpperCase() || null };
      }
      case 'multiselect':
      case 'checkboxes': {
        const selected = new Set(value || []);
        const boxes = [];
        const group = el('div', { class: 'ct-checkgroup', id });
        let lastGroup = null;
        for (const o of field.options || []) {
          if (o.group && o.group !== lastGroup) {
            group.append(el('div', { class: 'ct-checkgroup__title' }, o.group));
            lastGroup = o.group;
          }
          const box = el('input', { type: 'checkbox', checked: selected.has(o.value), disabled: field.disabled });
          boxes.push([box, o.value]);
          const dot = o.color ? el('span', { class: 'ct-dot', style: { background: o.color } }) : null;
          group.append(el('label', { class: 'ct-checkbox', title: o.help || null }, box, dot, o.label));
        }
        return { node: group, get: () => boxes.filter(([b]) => b.checked).map(([, v]) => v) };
      }
      case 'person': {
        const picker = createPersonPicker({ value: value || null, id, placeholder: field.placeholder, exclude: field.exclude, onChange: field.onChange, disabled: field.disabled });
        return { node: picker.element, get: () => picker.getValue() };
      }
      case 'people': {
        const picker = createPeoplePicker({ value: value || [], id, placeholder: field.placeholder, disabled: field.disabled });
        return { node: picker.element, get: () => picker.getValue() };
      }
      case 'number':
        return { node: el('input', { class: 'ct-input', type: 'number', id, value: value ?? '', disabled: field.disabled }),
          get: (n) => (n.value === '' ? null : Number(n.value)) };
      default: // text, email, password, date, url
        return {
          node: el('input', {
            class: 'ct-input', type: field.type || 'text', id, value: value ?? '', placeholder: field.placeholder,
            autocomplete: field.type === 'password' ? 'new-password' : 'off', disabled: field.disabled, maxlength: field.maxlength,
          }),
          get: (n) => n.value.trim() || null,
        };
    }
  }

  const grid = el('div', { class: columns > 1 ? 'ct-form-grid' : 'ct-stack' });
  for (const field of fields.filter((f) => !f.hidden)) {
    const id = `f-${field.key}-${++uid}`;
    const control = buildControl(field, id);
    controls.set(field.key, control);
    const error = el('div', { class: 'ct-field__error ct-hidden' });
    const wrapper = el('div', { class: `ct-field${field.full || ['textarea', 'checkboxes', 'multiselect', 'people'].includes(field.type) ? ' ct-field--full' : ''}` },
      control.labelInside ? null : el('label', { class: 'ct-label', for: id }, field.label, field.required ? el('span', { class: 'ct-required', 'aria-hidden': 'true' }, '*') : null),
      control.node,
      field.help ? el('div', { class: 'ct-field__help' }, field.help) : null,
      error);
    wrapper.errorNode = error;
    wrappers.set(field.key, wrapper);
    grid.append(wrapper);
  }

  function clearErrors() {
    formError.classList.add('ct-hidden');
    for (const w of wrappers.values()) {
      w.classList.remove('has-error');
      w.errorNode.classList.add('ct-hidden');
    }
  }

  function fieldError(key, message) {
    const w = wrappers.get(key);
    if (!w) return false;
    w.classList.add('has-error');
    w.errorNode.textContent = message;
    w.errorNode.classList.remove('ct-hidden');
    return true;
  }

  return {
    element: el('div', {}, formError, grid),
    getValues() {
      const out = {};
      for (const [key, control] of controls) out[key] = control.get(control.node);
      return out;
    },
    /** Client-side required check. Returns true when valid. */
    validate() {
      clearErrors();
      let ok = true;
      for (const field of fields.filter((f) => f.required && !f.hidden)) {
        const v = controls.get(field.key).get(controls.get(field.key).node);
        if (v === null || v === '' || (Array.isArray(v) && !v.length)) ok = fieldError(field.key, 'This field is required') && false;
      }
      return ok;
    },
    setErrors(err) {
      clearErrors();
      const details = err?.details;
      const list = Array.isArray(details) ? details : details?.field ? [{ field: details.field, message: err.message }] : [];
      // Match the full key first (e.g. "custom_fields.budget"), then its last part (e.g. "body.email" → "email").
      const shown = list.map((d) => fieldError(String(d.field), d.message)
        || fieldError(String(d.field).split('.').pop(), d.message)).some(Boolean);
      if (!shown) {
        formError.textContent = err?.message || 'Something went wrong';
        formError.classList.remove('ct-hidden');
      }
    },
  };
}

/**
 * Form inside a modal. onSubmit(values) may throw an ApiError; it is shown on the form.
 * Return value of onSubmit is passed to onDone. Extra footer actions can be added via `extraActions`.
 */
export function openFormModal({ title, fields, values, submitLabel = 'Save', onSubmit, onDone, wide = true, intro, extraActions = [] }) {
  const form = createForm({ fields, values });
  const modal = openModal({
    title,
    wide,
    body: el('div', {}, intro ? el('p', { class: 'ct-muted ct-small', style: { marginBottom: '16px' } }, intro) : null, form.element),
    actions: [
      ...extraActions,
      { label: 'Cancel' },
      {
        label: submitLabel,
        variant: 'primary',
        onClick: async (close) => {
          if (!form.validate()) return;
          try {
            const result = await onSubmit(form.getValues());
            close();
            onDone?.(result);
          } catch (err) {
            form.setErrors(err);
          }
        },
      },
    ],
  });
  modal.element.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'search') {
      e.preventDefault();
      modal.element.querySelector('.ct-btn--primary')?.click();
    }
  });
  return { ...modal, form };
}
