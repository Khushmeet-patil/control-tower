/**
 * Charts (Chart.js, vendored in /assets/vendor so the app needs no internet access).
 *
 *   createChart({ type: 'bar' | 'doughnut', labels, values, colors, onClick: (index) => {} })
 * returns an element at once and draws into it when the library has loaded. Colours may be hex values
 * (lookup colours) or CSS variables such as 'var(--ct-accent)'; variables are resolved from tokens.css.
 * Clicking a bar or slice calls onClick with its index, so every segment can open the list behind it.
 */
import { el } from '../core/utils.js';

let loading;
function loadChartJs() {
  if (window.Chart) return Promise.resolve(window.Chart);
  loading ||= new Promise((resolve, reject) => {
    const script = el('script', { src: '/assets/vendor/chart.umd.min.js' });
    script.addEventListener('load', () => resolve(window.Chart));
    script.addEventListener('error', () => reject(new Error('Could not load the chart library')));
    document.head.append(script);
  });
  return loading;
}

/** 'var(--ct-accent)' → '#2563EB' (canvas cannot read CSS variables). */
export function cssColor(value, fallback = '--ct-accent') {
  const v = value || `var(${fallback})`;
  const m = /^var\((--[\w-]+)\)$/.exec(v.trim());
  if (!m) return v;
  return getComputedStyle(document.documentElement).getPropertyValue(m[1]).trim() || '#64748B';
}

export function createChart({ type = 'bar', labels, values, colors = [], onClick, height = 220, label = 'Items' }) {
  const canvas = el('canvas', { role: 'img', 'aria-label': `${label}: ${labels.map((l, i) => `${l} ${values[i]}`).join(', ')}` });
  const wrap = el('div', { class: 'ct-chart', style: { height: `${height}px` } }, canvas);
  loadChartJs().then((Chart) => {
    const text = cssColor('var(--ct-text-muted)');
    const grid = cssColor('var(--ct-border)');
    const fill = labels.map((_, i) => cssColor(colors[i]));
    // eslint-disable-next-line no-new
    new Chart(canvas, {
      type,
      data: { labels, datasets: [{ label, data: values, backgroundColor: fill, borderColor: type === 'doughnut' ? cssColor('var(--ct-surface)') : fill,
        borderWidth: type === 'doughnut' ? 2 : 0, borderRadius: type === 'bar' ? 4 : 0, maxBarThickness: 36 }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        indexAxis: type === 'bar' && labels.length > 5 ? 'y' : 'x',
        plugins: { legend: { display: type === 'doughnut', position: 'right', labels: { color: text, boxWidth: 12 } },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.formattedValue} ${label.toLowerCase()}` } } },
        scales: type === 'bar' ? {
          x: { ticks: { color: text, precision: 0 }, grid: { color: grid, drawTicks: false }, border: { display: false } },
          y: { ticks: { color: text, precision: 0 }, grid: { color: grid, drawTicks: false }, border: { display: false } },
        } : {},
        onClick: onClick ? (_, elements) => { if (elements.length) onClick(elements[0].index); } : undefined,
        onHover: onClick ? (evt, elements) => { evt.native.target.style.cursor = elements.length ? 'pointer' : 'default'; } : undefined,
      },
    });
  }).catch(() => wrap.replaceChildren(el('p', { class: 'ct-muted ct-small' }, 'The chart could not be drawn.')));
  return wrap;
}

/**
 * Line chart with several series (trends over snapshots):
 *   createLineChart({ labels, series: [{ label: 'Overdue', values: [...], color: 'var(--ct-danger)' }], onClick })
 */
export function createLineChart({ labels, series, onClick, height = 240, yMax = null }) {
  const canvas = el('canvas', { role: 'img', 'aria-label': series.map((s) => `${s.label}: ${s.values.join(', ')}`).join('; ') });
  const wrap = el('div', { class: 'ct-chart', style: { height: `${height}px` } }, canvas);
  loadChartJs().then((Chart) => {
    const text = cssColor('var(--ct-text-muted)');
    const grid = cssColor('var(--ct-border)');
    // eslint-disable-next-line no-new
    new Chart(canvas, {
      type: 'line',
      data: { labels, datasets: series.map((s) => ({ label: s.label, data: s.values, borderColor: cssColor(s.color),
        backgroundColor: cssColor(s.color), tension: 0.25, pointRadius: 3, borderWidth: 2 })) },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { position: 'bottom', labels: { color: text, boxWidth: 12 } } },
        scales: {
          x: { ticks: { color: text }, grid: { display: false } },
          y: { ticks: { color: text, precision: 0 }, grid: { color: grid }, beginAtZero: true, ...(yMax ? { max: yMax } : {}) },
        },
        onClick: onClick ? (_, elements) => { if (elements.length) onClick(elements[0].index); } : undefined,
      },
    });
  }).catch(() => wrap.replaceChildren(el('p', { class: 'ct-muted ct-small' }, 'The chart could not be drawn.')));
  return wrap;
}
