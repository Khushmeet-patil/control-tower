/**
 * createProgressBar(65)                          → thin bar + "65%"
 * createProgressBar(3, { max: 10, label: 'Red' }) → labelled distribution row: "Red ▬▬ 3"
 * Colour defaults to the accent; pass a lookup colour or a CSS variable to override.
 */
import { el } from '../core/utils.js';

export function createProgressBar(value, { max = 100, label = null, color = null, suffix = max === 100 ? '%' : '' } = {}) {
  const pct = max ? Math.max(0, Math.min(100, (Number(value) || 0) / max * 100)) : 0;
  const fill = el('i', { class: 'ct-bar__fill', style: { width: `${pct}%` } });
  if (color) fill.style.setProperty('--bar-color', color);
  return el('div', { class: 'ct-bar-row', title: label ? `${label}: ${value}${suffix}` : `${value}${suffix}` },
    label !== null ? el('span', { class: 'ct-bar-row__label' }, label) : null,
    el('div', { class: 'ct-bar', role: 'progressbar', 'aria-valuenow': String(value), 'aria-valuemin': '0', 'aria-valuemax': String(max) }, fill),
    el('b', {}, `${value ?? 0}${suffix}`));
}
