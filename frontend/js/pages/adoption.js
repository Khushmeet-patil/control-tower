/** Adoption (/pages/adoption.html): the prototype's adoption tracker for top-level work.
 *  Tick a stage to record it (audited; only the item's managers can). "Built, not adopted" and
 *  "Ready for rollout" come from the signal rules, so admins can change when they appear. */
import { api } from '../core/api.js';
import { initLayout, pageHeader } from '../core/layout.js';
import { lookupBadge, lookupValues } from '../core/lookups.js';
import { el } from '../core/utils.js';
import { adoptionStages, createStageToggle, editEvidence, evidenceNode } from '../components/adoption.js';
import { createBadge } from '../components/badge.js';
import { createEmptyState } from '../components/empty-state.js';
import { createProgressBar } from '../components/progress-bar.js';
import { showError } from '../components/toast.js';
import { workTitleCell } from '../components/work-table.js';

const { content } = await initLayout({ active: 'adoption', title: 'Adoption', permission: 'work.view' });
const cancelled = lookupValues('status', { includeRetired: true }).find((v) => v.code === 'cancelled')?.id;

async function render() {
  let items; let ac;
  try {
    [items, ac] = await Promise.all([
      api.get('/work-items', { top_level: '1', per_page: 200, sort: 'code' }).then((d) => d.items.filter((i) => i.status_id !== cancelled)),
      api.get('/action-centre'),
    ]);
  } catch (err) { showError(err); content.replaceChildren(createEmptyState({ title: 'Could not load adoption', message: err.message })); return; }

  const stages = adoptionStages();
  const flags = {}; // item id → signal rule names (from the published signal rules)
  for (const w of ac.watchlist) for (const ref of w.items) if (ref.id) (flags[ref.id] ||= []).push(w.rule);

  const summary = el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, 'Technical completion vs adoption'),
      el('span', { class: 'ct-muted ct-small' }, `${ac.adoption.total} top-level item(s), not cancelled`)),
    el('div', { class: 'ct-card__body' }, ac.adoption.stages.map((s) => createProgressBar(s.count, {
      max: ac.adoption.total || 1, label: stages.find((x) => x.id === s.stage_id)?.label || '—', suffix: '' }))));

  const table = items.length ? el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
    el('thead', {}, el('tr', {}, el('th', { scope: 'col' }, 'Item'), el('th', { scope: 'col' }, 'Status'),
      stages.map((s) => el('th', { scope: 'col', class: 'ct-center' }, s.label)), el('th', { scope: 'col' }, 'Evidence'))),
    el('tbody', {}, items.map((i) => el('tr', {},
      el('td', {}, workTitleCell(i, { showParent: false }),
        flags[i.id] ? el('div', { class: 'ct-tag-list', style: { marginTop: '4px' } }, flags[i.id].map((f) => createBadge(f, 'var(--ct-warning)'))) : null),
      el('td', {}, lookupBadge(i.status_id)),
      stages.map((s) => el('td', { class: 'ct-center' }, createStageToggle(i, s, { onSaved: render }))),
      el('td', {}, evidenceNode(i.adoption_evidence), ' ',
        el('button', { class: 'ct-link-button ct-small', type: 'button', onClick: () => editEvidence(i, { onSaved: render }) }, 'Change')))))))
    : createEmptyState({ title: 'No top-level work yet', icon: 'flag' });

  content.replaceChildren(
    pageHeader('Adoption', 'Development → testing → acceptance → training → rollout → adoption. Click a stage to tick it. Technical completion without adoption is flagged: value is not delivered until users adopt.'),
    summary,
    el('section', { class: 'ct-card' }, el('div', { class: 'ct-card__body' }, table)));
}

render();
