/**
 * Expandable tree built from a FLAT list of { id, parent_id, ... } — used by every hierarchy
 * (organisation units, functions, and later work items).
 *
 * const tree = createTree({
 *   items,                                    // flat list
 *   label: (item) => item.name,               // text shown (also used for search)
 *   meta: (item) => `${item.member_count}`,   // optional small text on the right
 *   color: (item) => item.unit_type?.color,   // optional coloured dot
 *   onSelect: (item) => {...},
 * });
 * tree.select(id); tree.filter('eng'); tree.setItems(newItems);
 */
import { icon } from '../core/icons.js';
import { clear, el } from '../core/utils.js';

/** Order a flat list depth-first and attach `depth` — also used for indented <select> options. */
export function flattenTree(items, label = (i) => i.name) {
  const ids = new Set(items.map((i) => i.id));
  const children = new Map();
  for (const item of items) {
    const parent = ids.has(item.parent_id) ? item.parent_id : null;
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(item);
  }
  for (const list of children.values()) list.sort((a, b) => label(a).localeCompare(label(b)));
  const out = [];
  const walk = (parent, depth) => {
    for (const item of children.get(parent) || []) {
      out.push({ ...item, depth });
      walk(item.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

/** Options for a <select>/form-builder select, indented to show the hierarchy. */
export function treeOptions(items, label = (i) => i.name) {
  return flattenTree(items, label).map((i) => ({ value: i.id, label: `${'   '.repeat(i.depth)}${label(i)}` }));
}

function highlight(text, query) {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query);
  if (idx < 0) return text;
  return [text.slice(0, idx), el('mark', {}, text.slice(idx, idx + query.length)), text.slice(idx + query.length)];
}

export function createTree({ items = [], label = (i) => i.name, meta, color, onSelect, emptyText = 'Nothing to show' }) {
  const state = { items, selectedId: null, collapsed: new Set(), query: '' };
  const element = el('div', { class: 'ct-tree-scroll', role: 'tree' });

  function childrenMap() {
    const ids = new Set(state.items.map((i) => i.id));
    const map = new Map();
    for (const item of state.items) {
      const parent = ids.has(item.parent_id) ? item.parent_id : null;
      if (!map.has(parent)) map.set(parent, []);
      map.get(parent).push(item);
    }
    for (const list of map.values()) list.sort((a, b) => label(a).localeCompare(label(b)));
    return map;
  }

  /** With a search query: ids of matches plus all their ancestors. */
  function matchingIds(map) {
    if (!state.query) return null;
    const byId = new Map(state.items.map((i) => [i.id, i]));
    const keep = new Set();
    for (const item of state.items) {
      if (!label(item).toLowerCase().includes(state.query)) continue;
      let current = item;
      while (current && !keep.has(current.id)) {
        keep.add(current.id);
        current = byId.get(current.parent_id);
      }
    }
    return keep;
  }

  function renderLevel(parentId, map, keep) {
    const list = (map.get(parentId) || []).filter((i) => !keep || keep.has(i.id));
    if (!list.length) return null;
    const ul = el('ul', { class: 'ct-tree', role: parentId === null ? null : 'group' });
    for (const item of list) {
      const hasChildren = (map.get(item.id) || []).some((c) => !keep || keep.has(c.id));
      const collapsed = !keep && state.collapsed.has(item.id);
      const toggle = el('button', {
        class: `ct-tree__toggle${hasChildren ? '' : ' ct-tree__toggle--leaf'}${collapsed ? ' is-collapsed' : ''}`,
        type: 'button', tabindex: '-1', 'aria-label': collapsed ? 'Expand' : 'Collapse',
        onClick: (e) => {
          e.stopPropagation();
          if (state.collapsed.has(item.id)) state.collapsed.delete(item.id); else state.collapsed.add(item.id);
          render();
        },
      }, icon('chevronDown', { size: 14 }));
      const row = el('div', {
        class: `ct-tree__row${item.id === state.selectedId ? ' is-selected' : ''}`,
        role: 'treeitem', tabindex: '0', dataset: { id: item.id },
        'aria-selected': String(item.id === state.selectedId),
        'aria-expanded': hasChildren ? String(!collapsed) : null,
        onClick: () => select(item.id, true),
        onKeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(item.id, true); } },
      },
      toggle,
      color ? el('span', { class: 'ct-tree__dot', style: color(item) ? { background: color(item) } : null }) : null,
      el('span', { class: 'ct-tree__label', title: label(item) }, highlight(label(item), state.query)),
      meta ? el('span', { class: 'ct-tree__meta' }, meta(item)) : null);
      const li = el('li', {}, row);
      if (hasChildren && !collapsed) li.append(renderLevel(item.id, map, keep));
      ul.append(li);
    }
    return ul;
  }

  function render() {
    const map = childrenMap();
    const keep = matchingIds(map);
    clear(element);
    const tree = renderLevel(null, map, keep);
    element.append(tree || el('p', { class: 'ct-muted ct-small', style: { padding: '8px' } }, state.query ? 'No matches' : emptyText));
  }

  function select(id, fromUser = false) {
    state.selectedId = id;
    // Make sure the selected node is visible.
    const byId = new Map(state.items.map((i) => [i.id, i]));
    let parent = byId.get(byId.get(id)?.parent_id);
    while (parent) { state.collapsed.delete(parent.id); parent = byId.get(parent.parent_id); }
    render();
    const item = byId.get(id);
    if (item && fromUser) onSelect?.(item);
    element.querySelector('.is-selected')?.scrollIntoView({ block: 'nearest' });
  }

  render();
  return {
    element,
    select: (id) => select(id, true),
    highlightOnly: (id) => select(id, false),
    setItems(newItems) { state.items = newItems; render(); },
    filter(query) { state.query = (query || '').trim().toLowerCase(); render(); },
    get items() { return state.items; },
  };
}
