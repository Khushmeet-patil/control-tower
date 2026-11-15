/**
 * Search-as-you-type person selector (searches /people within the user's scope).
 *
 * const picker = createPersonPicker({ value: { id, full_name } | null, placeholder, onChange, disabled });
 * picker.getValue() → id | null
 */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { clear, debounce, el } from '../core/utils.js';
import { createAvatar } from './person.js';

export function createPersonPicker({ value = null, placeholder = 'Search people…', onChange, id, exclude = [], disabled = false } = {}) {
  let selected = value;
  let results = [];
  let active = -1;

  const input = el('input', { class: 'ct-input', type: 'search', placeholder, autocomplete: 'off', id, role: 'combobox', 'aria-expanded': 'false' });
  const list = el('div', { class: 'ct-picker__list ct-hidden', role: 'listbox' });
  const element = el('div', { class: `ct-picker${disabled ? ' is-disabled' : ''}` });

  function choose(person) {
    selected = person;
    closeList();
    render();
    onChange?.(person);
  }

  function closeList() {
    list.classList.add('ct-hidden');
    input.setAttribute('aria-expanded', 'false');
  }

  function renderList() {
    clear(list);
    if (!results.length) {
      list.append(el('div', { class: 'ct-picker__option ct-muted' }, 'No people found'));
    }
    results.forEach((p, i) => {
      list.append(el('div', {
        class: `ct-picker__option${i === active ? ' is-active' : ''}`, role: 'option',
        onMousedown: (e) => { e.preventDefault(); choose(p); },
      }, createAvatar(p, { small: true }),
      el('span', { class: 'ct-person__text' }, el('span', {}, p.full_name),
        el('span', { class: 'ct-person__sub' }, [p.job_title, p.unit?.name].filter(Boolean).join(' · ')))));
    });
    list.classList.remove('ct-hidden');
    input.setAttribute('aria-expanded', 'true');
  }

  const search = debounce(async () => {
    const q = input.value.trim();
    try {
      const data = await api.get('/people', { q, per_page: 8, is_active: 'true' });
      results = data.items.filter((p) => !exclude.includes(p.id));
      active = results.length ? 0 : -1;
      if (document.activeElement === input) renderList();
    } catch { /* ignore search errors while typing */ }
  }, 250);

  input.addEventListener('input', search);
  input.addEventListener('focus', search);
  input.addEventListener('blur', () => setTimeout(closeList, 100));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!results.length) return;
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
      renderList();
    } else if (e.key === 'Enter' && active >= 0 && !list.classList.contains('ct-hidden')) {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === 'Escape') {
      e.stopPropagation();
      closeList();
    }
  });

  function render() {
    clear(element);
    if (selected) {
      element.append(el('div', { class: 'ct-picker__selected' },
        createAvatar(selected, { small: true }),
        el('span', { class: 'ct-tree__label' }, selected.full_name),
        disabled ? null : el('button', {
          class: 'ct-btn ct-btn--ghost ct-btn--sm ct-btn--icon', type: 'button', 'aria-label': `Remove ${selected.full_name}`,
          onClick: () => { choose(null); setTimeout(() => input.focus(), 0); },
        }, icon('close', { size: 14 }))));
    } else {
      input.value = '';
      input.disabled = disabled;
      element.append(input, list);
    }
  }

  render();
  return { element, getValue: () => selected?.id ?? null, focus: () => input.focus() };
}

/**
 * Several people: chips plus a search box to add more.
 * createPeoplePicker({ value: [{ id, full_name }] }) → { element, getValue() → [ids] }
 */
export function createPeoplePicker({ value = [], placeholder = 'Add a person…', id, disabled = false } = {}) {
  let people = [...value];
  const chips = el('div', { class: 'ct-tag-list' });
  const slot = el('div');
  const element = el('div', { class: `ct-people-picker${disabled ? ' is-disabled' : ''}` }, chips, slot);

  function render() {
    chips.replaceChildren(...people.map((p) => el('span', { class: 'ct-chip' },
      createAvatar(p, { small: true }), p.full_name,
      disabled ? null : el('button', {
        class: 'ct-chip__remove', type: 'button', 'aria-label': `Remove ${p.full_name}`,
        onClick: () => { people = people.filter((x) => x.id !== p.id); render(); },
      }, icon('close', { size: 12 })))));
    if (disabled) { slot.replaceChildren(); return; }
    const picker = createPersonPicker({
      id, placeholder, exclude: people.map((p) => p.id),
      onChange: (p) => { if (p && !people.some((x) => x.id === p.id)) people.push(p); render(); setTimeout(() => picker.focus(), 0); },
    });
    slot.replaceChildren(picker.element);
  }

  render();
  return { element, getValue: () => people.map((p) => p.id) };
}
