/**
 * Gantt chart: bars from planned start to planned finish, progress inside each bar, milestones as
 * diamonds, a red line for today, arrows for dependencies ("this cannot start before that finishes"),
 * a red arrow when a dependency is broken, and zoom (weeks / months / quarters / fit).
 *
 * createGantt(items, { links: [{ work_item_id, depends_on_id }], label, color, onClick, isMilestone })
 * Items need planned_end (planned_start optional). Returns null when there is nothing to draw.
 */
import { el, formatDate } from '../core/utils.js';

const DAY = 86400000;
const ROW = 28;
const toTime = (d) => new Date(`${d}T00:00:00`).getTime();
const ZOOM = { week: 28, month: 7, quarter: 2.4 }; // pixels per day

export function createGantt(items, { links = [], label = (i) => i.title, color = () => null, onClick, isMilestone = () => false } = {}) {
  const rows = items.filter((i) => i.planned_end);
  if (!rows.length) return null;
  const today = new Date();
  const now = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const start = (i) => toTime(i.planned_start || i.planned_end);
  const lo = Math.min(now, ...rows.map(start)) - 3 * DAY;
  const hi = Math.max(now, ...rows.map((i) => toTime(i.planned_end))) + 4 * DAY;
  const days = Math.round((hi - lo) / DAY);

  const scroll = el('div', { class: 'ct-gantt__scroll' });
  const zoomButtons = {};
  let zoom = 'fit';

  function draw() {
    const width = Math.max(scroll.clientWidth - 230, 400);
    const perDay = zoom === 'fit' ? width / days : ZOOM[zoom];
    const trackWidth = Math.round(days * perDay);
    const x = (t) => ((t - lo) / DAY) * perDay;
    const index = new Map(rows.map((r, n) => [r.id, n]));

    const ticks = [];
    const tick = new Date(lo);
    tick.setDate(1);
    const stepMonths = perDay < 3 ? 3 : 1;
    while (tick.getTime() < hi) {
      if (tick.getTime() >= lo) {
        ticks.push(el('span', { class: 'ct-gantt__tick', style: { left: `${x(tick.getTime())}px` } },
          tick.toLocaleDateString(undefined, { month: 'short', year: tick.getMonth() === 0 || ticks.length === 0 ? 'numeric' : undefined })));
      }
      tick.setMonth(tick.getMonth() + stepMonths);
    }
    if (perDay >= 14) { // weekly ticks when zoomed in
      const w = new Date(lo);
      w.setDate(w.getDate() + ((8 - w.getDay()) % 7));
      while (w.getTime() < hi) {
        ticks.push(el('span', { class: 'ct-gantt__tick ct-muted', style: { left: `${x(w.getTime())}px`, opacity: 0.6 } }, String(w.getDate())));
        w.setDate(w.getDate() + 7);
      }
    }

    const bars = rows.map((i) => {
      const milestone = isMilestone(i);
      const left = x(start(i));
      const barWidth = Math.max(x(toTime(i.planned_end) + DAY) - left, 6);
      const bar = el('i', { class: `ct-gantt__bar${milestone ? ' is-milestone' : ''}${i.is_overdue ? ' is-late' : ''}`,
        style: { left: `${milestone ? x(toTime(i.planned_end)) - 6 : left}px`, width: `${barWidth}px` } },
      !milestone && i.progress ? el('span', { class: 'ct-gantt__progress', style: { width: `${Math.min(100, i.progress)}%` } }) : null);
      const c = color(i);
      if (c) bar.style.setProperty('--bar-color', c);
      const name = onClick
        ? el('button', { class: 'ct-gantt__name ct-link-button', type: 'button', onClick: () => onClick(i) }, label(i))
        : el('span', { class: 'ct-gantt__name' }, label(i));
      return el('div', { class: 'ct-gantt__row', title: `${label(i)}: ${formatDate(i.planned_start)} → ${formatDate(i.planned_end)}${i.progress != null ? ` · ${i.progress}%` : ''}` },
        name, el('div', { class: 'ct-gantt__track', style: { width: `${trackWidth}px` } }, bar));
    });

    // dependency arrows: from the end of what it depends on to the start of the dependent item
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'ct-gantt__links');
    svg.setAttribute('width', String(trackWidth + 230));
    svg.setAttribute('height', String(rows.length * ROW + 22));
    const marker = document.createElementNS(ns, 'defs');
    marker.innerHTML = '<marker id="ct-gantt-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="currentColor"/></marker>';
    svg.append(marker);
    for (const link of links) {
      const a = index.get(link.depends_on_id);
      const b = index.get(link.work_item_id);
      if (a === undefined || b === undefined) continue;
      const from = rows[a];
      const to = rows[b];
      const x1 = 220 + x(toTime(from.planned_end) + DAY);
      const x2 = 220 + x(start(to));
      const y1 = 22 + a * ROW + ROW / 2;
      const y2 = 22 + b * ROW + ROW / 2;
      const mid = x1 + 8;
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('d', `M${x1},${y1} H${mid} V${y2} H${x2}`);
      path.setAttribute('marker-end', 'url(#ct-gantt-arrow)');
      if (start(to) <= toTime(from.planned_end)) path.setAttribute('class', 'is-clash');
      svg.append(path);
    }

    const inner = el('div', { class: 'ct-gantt__inner', style: { width: `${trackWidth + 230}px` } },
      el('div', { class: 'ct-gantt__head' }, el('span', { class: 'ct-gantt__label-col' }), el('div', { class: 'ct-gantt__ticks', style: { width: `${trackWidth}px` } }, ticks)),
      bars,
      el('b', { class: 'ct-gantt__today', style: { left: `${220 + x(now)}px` } }),
      svg);
    scroll.replaceChildren(inner);
    if (zoom !== 'fit') scroll.scrollLeft = Math.max(0, x(now) - 200);
  }

  const controls = el('div', { class: 'ct-gantt__bar-controls' },
    el('span', { class: 'ct-muted ct-small' }, 'Zoom'),
    ...['fit', 'week', 'month', 'quarter'].map((z) => {
      zoomButtons[z] = el('button', { class: `ct-btn ct-btn--sm${z === zoom ? ' ct-btn--primary' : ''}`, type: 'button', onClick: () => {
        zoom = z;
        for (const [k, b] of Object.entries(zoomButtons)) b.classList.toggle('ct-btn--primary', k === z);
        draw();
      } }, { fit: 'Fit', week: 'Weeks', month: 'Months', quarter: 'Quarters' }[z]);
      return zoomButtons[z];
    }),
    el('span', { class: 'ct-muted ct-small', style: { marginLeft: 'auto' } }, 'Red line = today · arrows = depends on · red arrow = starts before what it depends on finishes'));

  const root = el('div', { class: 'ct-gantt' }, controls, scroll);
  // Draw once the chart is on the page (its width is needed for "fit").
  requestAnimationFrame(draw);
  let resizeTimer;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (root.isConnected) draw(); }, 150); });
  return root;
}
