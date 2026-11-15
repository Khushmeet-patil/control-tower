/**
 * Server-paged data table used for EVERY list in the platform.
 *
 * const table = createDataTable({
 *   columns: [
 *     { key: 'name', label: 'Name', sortable: true },
 *     { key: 'status', label: 'Status', render: (row) => createBadge(row.status_label, row.status_color) },
 *   ],
 *   fetchPage: ({ page, per_page, sort, ...filters }) => api.get('/things', { page, per_page, sort, ...filters }),
 *   defaultSort: '-updated_at',
 *   pageSize: 25,
 *   onRowClick: (row) => {...},
 *   rowClass: (row) => (row.is_overdue ? 'is-late' : null),   // optional extra class per row
 *   emptyState: { title: 'No records', message: 'Try changing the filters' },
 * });
 * card.append(table.element);
 * table.setFilters({ status: 'open' });  table.reload();
 *
 * fetchPage must resolve to { items, page, per_page, total, pages } (the shared API list format).
 */
import { icon } from '../core/icons.js';
import { clear, el, formatValue } from '../core/utils.js';
import { createEmptyState } from './empty-state.js';
import { showError } from './toast.js';

export function createDataTable({ columns, fetchPage, defaultSort = '', pageSize = 25, onRowClick, rowClass, emptyState = {} }) {
  const state = { page: 1, perPage: pageSize, sort: defaultSort, filters: {}, requestId: 0 };

  const thead = el('thead');
  const tbody = el('tbody');
  const table = el('table', { class: 'ct-table' }, thead, tbody);
  const summary = el('span');
  const pageLabel = el('span');
  const prevBtn = el('button', { class: 'ct-btn ct-btn--sm', type: 'button', 'aria-label': 'Previous page', onClick: () => goTo(state.page - 1) }, icon('chevronLeft', { size: 16 }));
  const nextBtn = el('button', { class: 'ct-btn ct-btn--sm', type: 'button', 'aria-label': 'Next page', onClick: () => goTo(state.page + 1) }, icon('chevronRight', { size: 16 }));
  const footer = el('div', { class: 'ct-table-footer' }, summary, el('div', { class: 'ct-pager' }, prevBtn, pageLabel, nextBtn));
  const body = el('div', { class: 'ct-table-wrap' }, table);
  const element = el('div', { class: 'ct-data-table' }, body, footer);

  function renderHeader() {
    const [sortKey, desc] = state.sort.startsWith('-') ? [state.sort.slice(1), true] : [state.sort, false];
    const row = el('tr');
    for (const col of columns) {
      const active = col.sortable && sortKey === col.key;
      const th = el('th', {
        class: col.sortable ? 'is-sortable' : null,
        style: col.width ? { width: col.width } : null,
        'aria-sort': active ? (desc ? 'descending' : 'ascending') : null,
        scope: 'col',
      }, col.label, active ? el('span', { class: 'ct-sort' }, desc ? '↓' : '↑') : null);
      if (col.sortable) {
        th.tabIndex = 0;
        const toggle = () => {
          state.sort = active && !desc ? `-${col.key}` : col.key;
          state.page = 1;
          load();
        };
        th.addEventListener('click', toggle);
        th.addEventListener('keydown', (e) => { if (e.key === 'Enter') toggle(); });
      }
      row.append(th);
    }
    thead.replaceChildren(row);
  }

  function renderMessageRow(node) {
    tbody.replaceChildren(el('tr', { class: 'ct-table__loading' }, el('td', { colspan: columns.length }, node)));
  }

  function renderRows(items) {
    clear(tbody);
    if (!items.length) {
      renderMessageRow(createEmptyState({ title: 'No records found', ...emptyState }));
      return;
    }
    for (const item of items) {
      const tr = el('tr', { class: [onRowClick ? 'is-clickable' : null, rowClass?.(item)].filter(Boolean).join(' ') || null });
      for (const col of columns) {
        const value = col.render ? col.render(item) : formatValue(item[col.key]);
        tr.append(el('td', {}, value));
      }
      if (onRowClick) {
        tr.tabIndex = 0;
        tr.addEventListener('click', (e) => { if (!e.target.closest('a, button')) onRowClick(item); });
        tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') onRowClick(item); });
      }
      tbody.append(tr);
    }
  }

  function renderFooter(data) {
    const from = data.total ? (data.page - 1) * data.per_page + 1 : 0;
    const to = Math.min(data.page * data.per_page, data.total);
    summary.textContent = data.total ? `Showing ${from}–${to} of ${data.total}` : '';
    pageLabel.textContent = data.pages ? `Page ${data.page} of ${data.pages}` : '';
    prevBtn.disabled = data.page <= 1;
    nextBtn.disabled = data.page >= data.pages;
  }

  async function load() {
    renderHeader();
    const requestId = ++state.requestId;
    renderMessageRow('Loading…');
    try {
      const data = await fetchPage({ page: state.page, per_page: state.perPage, sort: state.sort || undefined, ...state.filters });
      if (requestId !== state.requestId) return; // a newer request superseded this one
      renderRows(data.items);
      renderFooter(data);
    } catch (err) {
      if (requestId !== state.requestId) return;
      renderMessageRow(createEmptyState({ title: 'Could not load data', message: err.message, icon: 'refresh' }));
      showError(err);
    }
  }

  function goTo(page) {
    state.page = Math.max(1, page);
    load();
  }

  load();

  return {
    element,
    reload: load,
    setFilters(filters) {
      state.filters = { ...filters };
      state.page = 1;
      load();
    },
  };
}
