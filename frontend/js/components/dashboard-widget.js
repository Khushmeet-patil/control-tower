/**
 * One dashboard widget, drawn from GET /dashboards/<id>/data.
 *   createWidget(widget, data, { groupLabel }) → <section class="ct-card ct-widget">
 * Every number, bar, slice and row opens the Portfolio list (or item) behind it.
 */
import { lookupBadge, lookupValue, lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createActionList } from './action-list.js';
import { createChart } from './chart.js';
import { createEmptyState } from './empty-state.js';
import { createProgressBar } from './progress-bar.js';
import { createTimeline } from './timeline.js';
import { portfolioUrl, workTitleCell } from './work-table.js';
import { healthBadge } from './health.js';
import { createPersonCell } from './person.js';
import { createDataTable } from './data-table.js';

const healthValue = (code) => lookupValues('health', { includeRetired: true }).find((v) => v.code === code);

/** Label and colour of a chart group value. */
export function groupDisplay(groupBy, g) {
  if (g.value === null || g.value === undefined) return { label: 'Not set', color: 'var(--ct-border-strong)' };
  if (groupBy === 'health') {
    if (g.value === 'na') return { label: 'Not assessed', color: 'var(--ct-border-strong)' };
    const v = healthValue(g.value);
    return { label: v?.label || g.value, color: v?.color };
  }
  if (groupBy === 'accountable_id') return { label: g.person?.full_name || `Person ${g.value}`, color: 'var(--ct-accent)' };
  const v = lookupValue(g.value);
  return { label: v?.label || String(g.value), color: v?.color };
}

const go = (filters) => { window.location.href = portfolioUrl(filters); };

function body(widget, data) {
  if (data.error) return createEmptyState({ title: 'This widget cannot be shown', message: data.error, icon: 'shield' });
  switch (widget.type) {
    case 'kpi':
      return el('a', { class: 'ct-widget__kpi', href: portfolioUrl(data.filters), title: 'Open the list behind this number' },
        el('b', {}, String(data.value)), el('span', { class: 'ct-muted ct-small' }, data.value === 1 ? 'item' : 'items'));
    case 'chart': {
      if (!data.groups.length) return el('p', { class: 'ct-muted ct-small' }, 'Nothing matches.');
      const shown = data.groups.map((g) => groupDisplay(data.group_by, g));
      return createChart({
        type: widget.chart || 'bar', labels: shown.map((s) => s.label), values: data.groups.map((g) => g.count),
        colors: shown.map((s) => s.color), onClick: (i) => data.groups[i].filters && go(data.groups[i].filters),
      });
    }
    case 'progress':
      if (!data.items.length) return el('p', { class: 'ct-muted ct-small' }, 'Nothing matches.');
      return el('div', { class: 'ct-stack', style: { gap: '6px' } },
        el('div', { class: 'ct-small ct-muted' }, `Weighted average of ${data.counted} item(s): `, el('strong', {}, `${data.average}%`)),
        data.items.map((i) => el('a', { href: `/pages/item.html?id=${i.id}`, class: 'ct-plain-link' }, createProgressBar(i.progress, { label: `${i.code} ${i.title}` }))));
    case 'timeline':
      return createTimeline(data.items, {
        label: (i) => `${i.code} ${i.title}`,
        color: (i) => (i.is_overdue ? 'var(--ct-danger)' : lookupValue(i.status_id)?.color),
        onClick: (i) => { window.location.href = `/pages/item.html?id=${i.id}`; },
      }) || el('p', { class: 'ct-muted ct-small' }, 'Nothing with a target date matches.');
    case 'table':
      return createDataTable({
        columns: [
          { key: 'title', label: 'Item', render: (i) => workTitleCell(i, { showParent: false }) },
          { key: 'health', label: 'Health', render: (i) => healthBadge(i.health) },
          { key: 'status_id', label: 'Status', render: (i) => lookupBadge(i.status_id) },
          { key: 'accountable', label: 'Accountable', render: (i) => createPersonCell(i.accountable) },
          { key: 'progress', label: 'Progress', render: (i) => el('div', { class: 'ct-progress-cell' }, createProgressBar(i.progress)) },
        ],
        fetchPage: async () => ({ items: data.items, total: data.items.length, page: 1, per_page: data.items.length || 1, pages: 1 }),
        onRowClick: (row) => { window.location.href = `/pages/item.html?id=${row.id}`; },
        rowClass: (row) => (row.is_overdue ? 'is-late' : null),
        emptyState: { title: 'Nothing matches', message: '' },
      }).element;
    case 'actions':
      return createActionList(data.entries, { numbered: true });
    default:
      return el('p', { class: 'ct-muted' }, 'Unknown widget');
  }
}

export function createWidget(widget, data, { actions = [] } = {}) {
  const more = data && !data.error && widget.type !== 'actions' && widget.type !== 'kpi'
    ? el('a', { class: 'ct-small', href: portfolioUrl(data.filters) }, `All ${data.total}`) : null;
  return el('section', { class: `ct-card ct-widget ct-widget--${widget.type}${widget.width === 2 ? ' ct-widget--wide' : ''}` },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, widget.title), el('div', { class: 'ct-actions' }, more, actions)),
    el('div', { class: 'ct-card__body' }, data ? body(widget, data) : el('p', { class: 'ct-muted ct-small' }, 'Loading…')));
}
