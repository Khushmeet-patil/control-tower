/** Tool Centre (/pages/tools.html): the tools you may use. Links open in a new tab (access checked and
 *  logged on the server). Forms and checklists work on a work item: "Use on an item…" finds one and
 *  opens its Tools tab. Tool managers get a link to the registry. */
import { api } from '../core/api.js';
import { can, initLayout, pageHeader } from '../core/layout.js';
import { icon } from '../core/icons.js';
import { lookupBadge } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { createEmptyState } from '../components/empty-state.js';
import { createFilterBar } from '../components/filter-bar.js';
import { openModal } from '../components/modal.js';
import { showError } from '../components/toast.js';
import { appliesToText, createToolGrid, KIND_LABEL } from '../components/tools.js';

const { user, content } = await initLayout({ active: 'tools', title: 'Tool Centre', permission: 'work.view' });

const slot = el('div');
const filters = createFilterBar({
  fields: [
    { key: 'q', type: 'search', placeholder: 'Search tools…' },
    { key: 'kind', type: 'select', label: 'All kinds', options: Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label })) },
  ],
  onChange: load,
});

content.append(
  pageHeader('Tool Centre', 'Tools for your work. Links open the tool in a new tab; forms and checklists save to a work item.',
    can(user, 'tools.manage') ? [el('a', { class: 'ct-btn', href: '/pages/admin/tools.html' }, icon('edit', { size: 16 }), 'Manage tools')] : []),
  filters.element,
  slot);

async function load() {
  let data;
  try { data = await api.get('/tools', filters.getValues()); } catch (err) { showError(err); return; }
  slot.replaceChildren(data.items.length
    ? createToolGrid(data.items, { onUse: chooseItem })
    : el('section', { class: 'ct-card' }, createEmptyState({ title: 'No tools', message: 'No tools are available to you here yet.', icon: 'grid' })));
}

/** Find the work item to use a form or checklist on, then open its Tools tab. */
function chooseItem(tool) {
  const types = tool.applies_to.item_type_ids;
  const results = el('div', { class: 'ct-stack', style: { gap: '4px' } });
  const search = el('input', { class: 'ct-input', type: 'search', placeholder: 'Search by code or title…', 'aria-label': 'Search work items' });
  let timer;
  const find = async () => {
    try {
      const data = await api.get('/work-items', { q: search.value.trim(), per_page: 10, sort: 'code', item_type_id__in: types.length ? types : null });
      results.replaceChildren(...(data.items.length ? data.items.map((w) => el('a', {
        class: 'ct-btn ct-btn--ghost', style: { justifyContent: 'flex-start' },
        href: `/pages/item.html?id=${w.id}&tab=tools`,
      }, lookupBadge(w.item_type_id), el('strong', {}, w.code), w.title)) : [el('p', { class: 'ct-muted ct-small' }, 'No matching work.')]));
    } catch (err) { showError(err); }
  };
  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(find, 250); });
  openModal({
    title: `${tool.name}: choose a work item`,
    body: el('div', { class: 'ct-stack' },
      el('p', { class: 'ct-muted ct-small' }, `The tool opens on the item's Tools tab. It applies to: ${appliesToText(tool)}.`),
      tool.applies_to.work_items.length ? el('div', { class: 'ct-tag-list' }, tool.applies_to.work_items.map((w) => el('a', {
        class: 'ct-btn ct-btn--sm', href: `/pages/item.html?id=${w.id}&tab=tools` }, `${w.code} ${w.title}`))) : null,
      search, results),
    actions: [{ label: 'Cancel' }],
  });
  find();
  search.focus();
}

load();
