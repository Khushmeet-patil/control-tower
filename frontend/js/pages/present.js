/** Presenter (/pages/present.html?id=…&page=…): one dashboard page at a time, full screen.
 *  Keys: → / Space / PageDown next, ← / PageUp previous, N speaker notes, F full screen.
 *  In snapshot mode every figure comes from the snapshot, so links to today's lists are left out. */
import { api } from '../core/api.js';
import { icon } from '../core/icons.js';
import { initLayout } from '../core/layout.js';
import { el, formatDate } from '../core/utils.js';
import { createBadge } from '../components/badge.js';
import { createWidget } from '../components/dashboard-widget.js';
import { createEmptyState } from '../components/empty-state.js';

const { content } = await initLayout({ active: 'presentations', title: 'Present', permission: 'work.view' });
const params = new URLSearchParams(location.search);

let pres;
try {
  pres = await api.get(`/presentations/${Number(params.get('id'))}`);
} catch (err) {
  content.replaceChildren(createEmptyState({ title: 'Presentation not found', message: err.message,
    action: el('a', { class: 'ct-btn', href: '/pages/presentations.html' }, 'All presentations') }));
  throw err;
}
document.title = `${pres.name} · Control Tower`;
document.querySelector('.ct-topbar__title').textContent = pres.name;

let index = Math.min(Math.max(Number(params.get('page') || 1) - 1, 0), pres.pages.length - 1);
let showNotes = false;
const cache = new Map();

const counter = el('span', { class: 'ct-muted ct-small' });
const titleNode = el('h1', { class: 'ct-present__title' });
const body = el('div', { class: 'ct-present__body' });
const notes = el('aside', { class: 'ct-present__notes ct-hidden', 'aria-label': 'Speaker notes' });
const frozen = pres.mode === 'snapshot';
const source = frozen
  ? createBadge(`Snapshot “${pres.snapshot?.label}” · ${formatDate(pres.snapshot?.as_of)}${pres.snapshot?.status === 'approved' ? ' · approved' : ''}`, 'var(--ct-accent)')
  : createBadge('Live figures', 'var(--ct-success)');

/** A bar button: `face` is what it shows (an icon or a short text), `label` its accessible name. */
const ctl = (label, face, onClick) => el('button', { class: 'ct-btn ct-btn--sm ct-btn--ghost', title: label, 'aria-label': label, onClick }, face);
const deck = el('div', { class: 'ct-present', tabindex: '-1' },
  el('header', { class: 'ct-present__bar' },
    el('div', { class: 'ct-present__heading' }, titleNode, el('div', { class: 'ct-tag-list' }, source, pres.status === 'published' ? createBadge('Published review pack', 'var(--ct-success)') : null)),
    el('div', { class: 'ct-present__controls' },
      ctl('Previous page', '←', () => go(index - 1)), counter, ctl('Next page', '→', () => go(index + 1)),
      ctl('Speaker notes (N)', icon('form', { size: 16 }), toggleNotes), ctl('Full screen (F)', icon('grid', { size: 16 }), fullscreen),
      el('a', { class: 'ct-btn ct-btn--sm ct-btn--ghost', href: '/pages/presentations.html' }, 'Exit'))),
  body, notes);
content.replaceChildren(deck);

async function pageData(page) {
  if (!cache.has(page.id)) cache.set(page.id, api.get(`/presentations/${pres.id}/pages/${page.id}/data`));
  return cache.get(page.id);
}

async function render() {
  const page = pres.pages[index];
  counter.textContent = `${index + 1} / ${pres.pages.length}`;
  titleNode.textContent = page.title;
  notes.replaceChildren(el('h4', { class: 'ct-section-title' }, 'Speaker notes'), el('p', { class: 'ct-prose' }, page.notes || 'No notes for this page.'));
  body.replaceChildren(el('p', { class: 'ct-muted' }, 'Loading…'));
  const url = new URL(location.href);
  url.searchParams.set('page', String(index + 1));
  history.replaceState(null, '', url);
  try {
    const d = await pageData(page);
    if (pres.pages[index] !== page) return; // moved on meanwhile
    if (d.error) { body.replaceChildren(createEmptyState({ title: 'This page cannot be shown', message: d.error })); return; }
    body.replaceChildren(d.widgets.length
      ? el('div', { class: 'ct-widgets' }, d.widgets.map((w) => createWidget(w, d.data[w.id] || { error: 'No data' }, { frozen })))
      : createEmptyState({ title: 'This dashboard has no widgets' }));
    const next = pres.pages[index + 1];
    if (next) pageData(next); // load ahead
  } catch (err) {
    body.replaceChildren(createEmptyState({ title: 'Could not load this page', message: err.message }));
  }
}

function go(i) {
  if (i < 0 || i >= pres.pages.length || i === index) return;
  index = i;
  render();
}

function toggleNotes() {
  showNotes = !showNotes;
  notes.classList.toggle('ct-hidden', !showNotes);
}

function fullscreen() {
  if (document.fullscreenElement) document.exitFullscreen();
  else deck.requestFullscreen?.().catch(() => {});
}

document.addEventListener('keydown', (e) => {
  if (e.target.closest('input, textarea, select')) return;
  if (['ArrowRight', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); go(index + 1); }
  if (['ArrowLeft', 'PageUp'].includes(e.key)) { e.preventDefault(); go(index - 1); }
  if (e.key === 'n' || e.key === 'N') toggleNotes();
  if (e.key === 'f' || e.key === 'F') fullscreen();
});

render();
