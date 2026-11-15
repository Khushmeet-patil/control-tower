/**
 * Tabs that build their panel lazily on first open.
 * const tabs = createTabs({ tabs: [{ key: 'details', label: 'Details', render: () => node }], active: 'details',
 *                           onChange: (key) => {} });
 * card.append(tabs.element);  tabs.select('people');  tabs.refresh('people')  // rebuild one panel
 */
import { el } from '../core/utils.js';

export function createTabs({ tabs, active, onChange }) {
  const buttons = new Map();
  const panels = new Map();
  const bar = el('div', { class: 'ct-tabs', role: 'tablist' });
  const body = el('div', { class: 'ct-tabs__body' });
  let current = null;

  function build(key) {
    const tab = tabs.find((t) => t.key === key);
    const panel = el('div', { role: 'tabpanel' }, tab.render());
    panels.set(key, panel);
    return panel;
  }

  function select(key) {
    if (!tabs.some((t) => t.key === key)) key = tabs[0].key;
    current = key;
    for (const [k, b] of buttons) {
      b.classList.toggle('is-active', k === key);
      b.setAttribute('aria-selected', String(k === key));
    }
    body.replaceChildren(panels.get(key) || build(key));
    onChange?.(key);
  }

  for (const tab of tabs) {
    const b = el('button', { class: 'ct-tabs__tab', type: 'button', role: 'tab', onClick: () => select(tab.key) }, tab.label);
    buttons.set(tab.key, b);
    bar.append(b);
  }
  select(active || tabs[0].key);

  return {
    element: el('div', {}, bar, body),
    select,
    refresh(key = current) {
      panels.delete(key);
      if (key === current) select(key);
    },
  };
}
