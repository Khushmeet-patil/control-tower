/**
 * Row of number tiles (the reference prototype's KPI strip).
 * createKpis([{ value: 12, label: 'Open items', color: 'var(--ct-danger)', href: '/pages/work.html?overdue=1' }])
 * A tile with `href` or `onClick` drills into the records behind the number.
 */
import { el } from '../core/utils.js';

export function createKpis(tiles) {
  return el('div', { class: 'ct-kpis' }, tiles.filter(Boolean).map((t) => {
    const value = el('b', { class: 'ct-kpi__value', style: t.color ? { color: t.color } : null }, String(t.value ?? '—'));
    const label = el('span', { class: 'ct-kpi__label' }, t.label);
    if (t.href) return el('a', { class: 'ct-kpi', href: t.href, title: t.title || null }, value, label);
    if (t.onClick) return el('button', { class: 'ct-kpi', type: 'button', onClick: t.onClick, title: t.title || null }, value, label);
    return el('div', { class: 'ct-kpi', title: t.title || null }, value, label);
  }));
}
