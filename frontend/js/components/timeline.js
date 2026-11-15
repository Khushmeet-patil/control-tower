/**
 * Simple timeline (Gantt) of items with planned dates, with a line for today.
 * createTimeline(items, { label: (i) => i.title, color: (i) => '#2563EB', onClick: (i) => {} })
 * Items need planned_end (planned_start optional). Returns null when nothing can be drawn.
 */
import { el, formatDate } from '../core/utils.js';

const DAY = 86400000;
const toTime = (d) => new Date(`${d}T00:00:00`).getTime();

export function createTimeline(items, { label = (i) => i.title, color = () => null, onClick, today = new Date() } = {}) {
  const rows = items.filter((i) => i.planned_end);
  if (!rows.length) return null;
  const now = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const start = (i) => toTime(i.planned_start || i.planned_end);
  const lo = Math.min(now, ...rows.map(start));
  const hi = Math.max(now, ...rows.map((i) => toTime(i.planned_end))) + DAY;
  const span = hi - lo || DAY;
  const pos = (t) => ((t - lo) / span) * 100;

  const lines = rows.map((i) => {
    const left = pos(start(i));
    const width = Math.max(pos(toTime(i.planned_end) + DAY) - left, 1.5);
    const bar = el('i', { class: 'ct-timeline__bar', style: { left: `${left}%`, width: `${width}%` } });
    const c = color(i);
    if (c) bar.style.setProperty('--bar-color', c);
    const name = onClick
      ? el('button', { class: 'ct-timeline__name ct-link-button', type: 'button', onClick: () => onClick(i) }, label(i))
      : el('span', { class: 'ct-timeline__name' }, label(i));
    return el('div', { class: 'ct-timeline__row', title: `${label(i)}: ${formatDate(i.planned_start)} → ${formatDate(i.planned_end)}` },
      name,
      el('div', { class: 'ct-timeline__track' }, bar, el('b', { class: 'ct-timeline__today', style: { left: `${pos(now)}%` } })));
  });

  return el('div', { class: 'ct-timeline' },
    el('div', { class: 'ct-timeline__scale ct-muted' },
      el('span', {}, formatDate(new Date(lo).toISOString().slice(0, 10))),
      el('span', {}, 'Line = today'),
      el('span', {}, formatDate(new Date(hi - DAY).toISOString().slice(0, 10)))),
    lines);
}
