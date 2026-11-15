/** Action Centre: the manager's weekly review page, laid out like the reference prototype
 *  (reference/MY Control Tower 1.html, "Action Centre"):
 *    KPI strip · Top 5 actions for me · progress board · hold points | priority × health + watchlist ·
 *    distributions (priority, status, category, health) · capacity | technical completion vs adoption |
 *    milestones completed per month · upcoming milestones | blockers & pending decisions · data quality
 *  All limited to the work I can see; every number opens the list behind it. */
import { api } from '../core/api.js';
import { initLayout, pageHeader, refreshApprovalCount } from '../core/layout.js';
import { lookupBadge, lookupValue, lookupValues } from '../core/lookups.js';
import { el, formatDate } from '../core/utils.js';
import { createActionList } from '../components/action-list.js';
import { createEmptyState } from '../components/empty-state.js';
import { createKpis } from '../components/kpi.js';
import { createPersonCell } from '../components/person.js';
import { createProgressBar } from '../components/progress-bar.js';
import { createCapacityBars } from '../components/capacity.js';
import { healthBadge } from '../components/health.js';
import { showError } from '../components/toast.js';
import { openReview } from '../components/approval.js';
import { portfolioUrl } from '../components/work-table.js';

const { content } = await initLayout({ active: 'action-centre', title: 'Action Centre', permission: 'work.view' });
const TONE = { red: 'var(--ct-danger)', amber: 'var(--ct-warning)', grey: 'var(--ct-text-subtle)' };
const portfolio = portfolioUrl;
const link = (ref, text) => (ref?.id ? el('a', { href: `/pages/item.html?id=${ref.id}` }, text ?? `${ref.code} ${ref.title}`) : el('span', { class: 'ct-muted' }, ref?.title || '—'));
const sub = (...parts) => el('div', { class: 'ct-muted ct-small' }, parts.filter(Boolean).join(' · '));

function table(headers, rows, empty = 'No records yet') {
  return el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table' },
    el('thead', {}, el('tr', {}, headers.map((h) => el('th', { scope: 'col' }, h)))),
    el('tbody', {}, rows.length ? rows : el('tr', {}, el('td', { colspan: headers.length, class: 'ct-muted ct-small' }, empty)))));
}
const healthColor = (code) => lookupValues('health', { includeRetired: true }).find((v) => v.code === code)?.color;

function card(title, body, extra) {
  return el('section', { class: 'ct-card' },
    el('div', { class: 'ct-card__header' }, el('h3', { class: 'ct-card__title' }, title), extra || null),
    el('div', { class: 'ct-card__body' }, body));
}

function spreadBars(rows, labelOf, colorOf, filterOf) {
  if (!rows.length) return el('p', { class: 'ct-muted ct-small' }, 'No data');
  const max = Math.max(...rows.map((r) => r.count));
  return el('div', {}, rows.map((r) => {
    const bar = createProgressBar(r.count, { max, label: labelOf(r.value), color: colorOf(r.value), suffix: '' });
    const f = filterOf(r.value);
    return f ? el('a', { href: portfolio(f), style: { color: 'inherit', textDecoration: 'none' } }, bar) : bar;
  }));
}

async function render() {
  let ac;
  try { ac = await api.get('/action-centre'); } catch (err) { showError(err); content.append(createEmptyState({ title: 'Could not load the Action Centre', message: err.message })); return; }
  const reload = () => { render(); refreshApprovalCount(); };

  const kpis = createKpis(ac.kpis.map((k) => ({
    value: k.value, label: k.label, color: k.value ? TONE[k.tone] : null,
    href: k.filters ? portfolio(k.filters) : k.key === 'approvals' ? '/pages/approvals.html' : k.key === 'dq' ? '#dq' : null,
  })));

  // ---- initiative progress board (in delivery, worst health first; progress = validated work)
  const board = table(['Item', 'Priority', 'Accountable', 'Health', 'Progress', 'Next milestone', 'Next action'], ac.board.map((b) => el('tr', {},
    el('td', {}, el('strong', {}, link(b, b.title)), sub(b.code, b.category_id ? lookupValue(b.category_id)?.label : null)),
    el('td', {}, b.priority_id ? lookupBadge(b.priority_id) : '—'),
    el('td', {}, createPersonCell(b.accountable)),
    el('td', { title: b.health.reason }, healthBadge(b.health)),
    el('td', { style: { minWidth: '130px' } }, createProgressBar(b.progress), b.to_validate ? sub(`⏳ ${b.to_validate} to validate`) : null),
    el('td', {}, b.next_milestone ? [link(b.next_milestone, b.next_milestone.title), sub(formatDate(b.next_milestone.planned_end), b.next_milestone.holder?.full_name)]
      : el('span', { class: 'ct-text-danger' }, 'none')),
    el('td', {}, b.next_action ? [link(b.next_action, b.next_action.title), sub(formatDate(b.next_action.planned_end), b.next_action.owner?.full_name)] : '—'))),
  'No top-level work in delivery.');

  // ---- hold points: where I am needed
  const holds = table(['Type', 'Item', 'Owner', 'When', ''], ac.hold_points.map((h) => el('tr', {},
    el('td', {}, h.action_type_id ? lookupBadge(h.action_type_id) : h.type),
    el('td', {}, link(h.item, h.item.title), h.in ? el('div', { class: 'ct-muted ct-small', title: h.in.title }, `in ${h.in.code}`) : null),
    el('td', {}, h.owner?.full_name || '—'),
    el('td', { class: h.when.startsWith('overdue') ? 'ct-text-danger' : null }, h.when),
    el('td', {}, h.approval_id ? el('button', { class: 'ct-btn ct-btn--sm ct-btn--primary', onClick: () => openReview(h.approval_id, { onDone: reload }) }, 'Review')
      : h.item.id ? el('a', { class: 'ct-btn ct-btn--sm', href: `/pages/item.html?id=${h.item.id}` }, h.type === 'Setup gap' ? 'Fix' : 'Open') : null))),
  'Nothing is waiting for you.');

  // ---- priority × health, then the watchlist under it (as in the prototype)
  const matrix = el('div', { class: 'ct-table-wrap' }, el('table', { class: 'ct-table ct-matrix' },
    el('thead', {}, el('tr', {}, el('th', {}, 'Priority'), ['red', 'amber', 'grey', 'green'].map((h) => el('th', {}, lookupBadge(ac.health_ids[h]))))),
    el('tbody', {}, ac.matrix.map((row) => el('tr', {}, el('td', {}, row.label),
      ['red', 'amber', 'grey', 'green'].map((h) => el('td', {}, row.cells[h]
        ? el('a', { href: portfolio({ level: 'top', priority_id: row.priority_id, health: h }) }, String(row.cells[h]))
        : el('span', { class: 'ct-muted' }, '·'))))))));
  const watchlist = ac.watchlist.length ? el('div', { class: 'ct-stack', style: { gap: '8px' } }, ac.watchlist.map((w) => el('div', {},
    el('strong', {}, `${w.count} `), w.rule,
    el('div', { class: 'ct-small' }, w.items.slice(0, 4).map((i, n) => [n ? ', ' : '', link(i, i.title)]), w.items.length > 4 ? ' …' : ''))))
    : el('p', { class: 'ct-muted ct-small' }, 'Nothing on the watchlist.');

  // ---- distributions
  const lookupSpread = (title, key, empty) => card(title, spreadBars(ac.spread[key], (v) => lookupValue(v)?.label || empty,
    (v) => lookupValue(v)?.color, (v) => (v ? { level: 'top', [key]: v } : null)));
  const healthSpread = card('Health (top-level work)', spreadBars(ac.spread.health, (v) => (v ? lookupValues('health').find((x) => x.code === v)?.label || v : 'Not assessed'),
    (v) => healthColor(v), (v) => (v ? { level: 'top', health: v } : { level: 'top', health: 'na' })));

  // ---- capacity, adoption, monthly completions
  const capacity = ac.capacity.length ? el('div', {}, ac.capacity.map((r) => el('div', { class: 'ct-capacity-row' },
    createCapacityBars([r]),
    r.open_actions ? el('a', { class: 'ct-small', href: portfolio(r.open_actions_filters) }, `${r.open_actions} open`) : el('span', { class: 'ct-muted ct-small' }, '0 open'))))
    : el('p', { class: 'ct-muted ct-small' }, 'Nobody has an allocation on open work.');
  const stages = lookupValues('adoption_stage', { includeRetired: true });
  const adoption = el('div', {}, ac.adoption.stages.map((s) => createProgressBar(s.count, { max: ac.adoption.total || 1, suffix: '',
    label: stages.find((x) => x.id === s.stage_id)?.label || '—' })),
  el('a', { class: 'ct-small', href: '/pages/adoption.html' }, 'Adoption tracker'));
  const maxMonth = Math.max(1, ...ac.completed_by_month.map((m) => m.count));
  const months = ac.completed_by_month.some((m) => m.count) ? el('div', {}, ac.completed_by_month.map((m) => {
    const label = new Date(`${m.month}-01T00:00:00`).toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
    const bar = createProgressBar(m.count, { max: maxMonth, label, suffix: '', color: 'var(--ct-success)' });
    return m.count ? el('a', { class: 'ct-plain-link', href: portfolio(m.filters) }, bar) : bar;
  })) : el('p', { class: 'ct-muted ct-small' }, 'No validated milestones yet.');

  // ---- upcoming milestones, blockers & pending decisions
  const upcoming = table(['Milestone', 'Belongs to', 'Due', 'Holder'], ac.upcoming_milestones.map((m) => el('tr', {},
    el('td', {}, link(m, m.title)), el('td', {}, m.in ? link(m.in, m.in.title) : '—'), el('td', {}, formatDate(m.planned_end)),
    el('td', {}, m.holder?.full_name || '—'))), 'No milestones due in the next 14 days.');
  const blockers = table(['Item', 'Type', 'Owner', 'Age / due'], ac.blockers_decisions.map((a) => el('tr', { class: a.is_late ? 'is-late' : null },
    el('td', {}, link(a, a.title)), el('td', {}, el('div', { class: 'ct-tag-list' }, lookupBadge(a.action_type_id), a.severity_id ? lookupBadge(a.severity_id) : null)),
    el('td', {}, a.owner?.full_name || '—'),
    el('td', {}, a.is_blocker ? `${a.age_days} days` : formatDate(a.planned_end)))), 'No open blockers or pending decisions.');

  const dq = ac.data_quality.length ? el('ul', { class: 'ct-change-list' }, ac.data_quality.map((d) => el('li', {},
    link(d.item), ': ', d.reason, d.owner ? el('span', { class: 'ct-muted' }, ` (${d.owner.full_name})`) : null)))
    : el('p', { class: 'ct-muted ct-small' }, 'No data-quality flags.');

  content.replaceChildren(...[
    pageHeader('Action Centre', 'Your weekly review: where you are needed, ranked. Every number opens the items behind it.'),
    kpis,
    card('Top 5 actions for me', createActionList(ac.top, { onChange: reload }),
      el('span', { class: 'ct-muted ct-small' }, 'Ranked by rule score + priority + days late or waiting')),
    card('Initiative progress board', board, el('span', { class: 'ct-muted ct-small' }, 'In delivery · worst health first · progress = validated work')),
    el('div', { class: 'ct-grid-2' },
      card(`Hold points: where I am needed${ac.hold_points_total > ac.hold_points.length ? ` (${ac.hold_points.length} of ${ac.hold_points_total})` : ''}`, holds),
      card('Priority × health', el('div', { class: 'ct-stack' }, matrix, el('h4', { class: 'ct-section-title' }, 'Watchlist'), watchlist))),
    el('div', { class: 'ct-grid-4' },
      lookupSpread('By priority', 'priority_id', 'No priority'), lookupSpread('By status', 'status_id', 'No status'),
      lookupSpread('By category', 'category_id', 'No category'), healthSpread),
    el('div', { class: 'ct-grid-3' },
      card(`Team capacity (buffer ${100 - ac.usable_pct}%)`, capacity, el('a', { class: 'ct-small', href: '/pages/team.html' }, 'My team')),
      card('Technical completion vs adoption', adoption),
      card('Milestones completed (by month)', months)),
    el('div', { class: 'ct-grid-2' },
      card('Upcoming milestones (14 days)', upcoming, el('a', { class: 'ct-small', href: portfolio(ac.upcoming_filters) }, 'See all')),
      card(`Blockers & pending decisions (${ac.blockers_decisions_total})`, blockers)),
    ac.needed_total > ac.top.length ? card(`Also needs me (${ac.needed_total - ac.top.length})`, createActionList(ac.needed.slice(ac.top.length), { numbered: false, onChange: reload })) : null,
    ac.data_quality_total ? el('div', { id: 'dq' }, card(`Data-quality flags (${ac.data_quality_total})`, dq)) : null,
  ].filter(Boolean));
}

render();
