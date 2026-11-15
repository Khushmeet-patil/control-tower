/**
 * Renders the application shell (sidebar + top bar) for every signed-in page.
 *
 *   const { user, content } = await initLayout({ active: 'home', title: 'My Home' });
 *   content.append(...);
 *
 * Add new screens to NAV below — one place for all navigation.
 * Published settings (lookups, custom fields, terms) are loaded before the page runs, so pages
 * can use core/lookups.js straight away.
 */
import { loginUrl } from './api.js';
import { getCurrentUser, logout } from './auth.js';
import { icon } from './icons.js';
import { el } from './utils.js';
import { loadSettings, term } from './lookups.js';
import { openChangePassword } from '../components/change-password.js';

// `perm`: the item shows only if the user holds that permission code.
// `term`: the label comes from an admin-renameable term (plural form).
const NAV = [
  {
    section: null,
    items: [
      { key: 'home', label: 'My Home', href: '/pages/home.html', icon: 'home' },
    ],
  },
  {
    section: 'Work',
    items: [
      { key: 'action-centre', label: 'Action Centre', href: '/pages/action-centre.html', icon: 'target', perm: 'work.view' },
      { key: 'work', label: 'Portfolio', href: '/pages/work.html', icon: 'briefcase', perm: 'work.view' },
      { key: 'my-work', label: 'My work', href: '/pages/my-work.html', icon: 'tasks', perm: 'work.view' },
      { key: 'schedule', label: 'Schedule', href: '/pages/schedule.html', icon: 'calendar', perm: 'work.view' },
      { key: 'approvals', label: 'Approvals', href: '/pages/approvals.html', icon: 'check', perm: 'work.view' },
      { key: 'team', label: 'My team', href: '/pages/team.html', icon: 'users', perm: 'work.manage' },
    ],
  },
  {
    section: 'Insights',
    items: [
      { key: 'dashboards', label: 'Dashboards', href: '/pages/dashboards.html', icon: 'chart', perm: 'work.view' },
      { key: 'adoption', label: 'Adoption', href: '/pages/adoption.html', icon: 'flag', perm: 'work.view' },
    ],
  },
  {
    section: 'Organisation',
    items: [
      { key: 'organisation', label: 'Organisation', href: '/pages/organisation.html', icon: 'org', perm: 'org.view' },
      { key: 'functions', label: 'Functions', term: 'function', href: '/pages/functions.html', icon: 'layers', perm: 'functions.view' },
      { key: 'people', label: 'People', term: 'person', href: '/pages/people.html', icon: 'users', perm: 'people.view' },
    ],
  },
  {
    section: 'Administration',
    items: [
      { key: 'roles', label: 'Roles & access', href: '/pages/admin/roles.html', icon: 'shield', perm: 'roles.manage' },
      { key: 'lookups', label: 'Lookups & colours', href: '/pages/admin/lookups.html', icon: 'list', perm: 'settings.manage' },
      { key: 'fields', label: 'Custom fields', href: '/pages/admin/fields.html', icon: 'form', perm: 'settings.manage' },
      { key: 'rules', label: 'Health rules', href: '/pages/admin/rules.html', icon: 'target', perm: 'settings.manage' },
      { key: 'workflows', label: 'Approval chains', href: '/pages/admin/workflows.html', icon: 'check', perm: 'settings.manage' },
      { key: 'terms', label: 'Terminology', href: '/pages/admin/terminology.html', icon: 'type', perm: 'settings.manage' },
      { key: 'versions', label: 'Settings versions', href: '/pages/admin/versions.html', icon: 'versions', perm: 'settings.manage' },
      { key: 'audit', label: 'Audit log', href: '/pages/admin/audit.html', icon: 'history', perm: 'audit.view' },
    ],
  },
];

/** True if the signed-in user holds the permission code. */
export function can(user, permission) {
  return !permission || user.is_admin || (user.permissions || []).includes(permission);
}

function canSee(entry, user) {
  return can(user, entry.perm);
}

function buildSidebar(active, user) {
  const nav = el('nav', { class: 'ct-sidebar__nav', 'aria-label': 'Main' });
  for (const group of NAV) {
    const items = group.items.filter((i) => canSee(i, user));
    if (!items.length) continue;
    if (group.section) nav.append(el('div', { class: 'ct-sidebar__section' }, group.section));
    for (const item of items) {
      nav.append(el('a', {
        class: `ct-sidebar__link${item.key === active ? ' is-active' : ''}`,
        href: item.href,
        'aria-current': item.key === active ? 'page' : null,
        dataset: { nav: item.key },
      }, icon(item.icon), item.term ? term(item.term, { plural: true, fallback: item.label }) : item.label));
    }
  }
  return el('aside', { class: 'ct-sidebar' },
    el('a', { class: 'ct-sidebar__brand', href: '/pages/home.html', style: { textDecoration: 'none' } },
      el('span', { class: 'ct-sidebar__logo' }, 'CT'), 'Control Tower'),
    nav);
}

function buildUserMenu(user) {
  const panel = el('div', { class: 'ct-user-menu__panel ct-hidden', role: 'menu' },
    el('div', { class: 'ct-user-menu__info' },
      el('div', { style: { fontWeight: 600 } }, user.full_name),
      el('div', { class: 'ct-muted ct-small' }, user.email)),
    el('button', { class: 'ct-btn ct-btn--ghost ct-btn--block', style: { justifyContent: 'flex-start' }, role: 'menuitem', onClick: openChangePassword },
      icon('key', { size: 16 }), 'Change password'),
    el('button', { class: 'ct-btn ct-btn--ghost ct-btn--block', style: { justifyContent: 'flex-start' }, role: 'menuitem', onClick: logout },
      icon('logout', { size: 16 }), 'Sign out'));

  const trigger = el('button', {
    class: 'ct-btn ct-btn--ghost', 'aria-haspopup': 'true', 'aria-expanded': 'false',
    onClick: (e) => {
      e.stopPropagation();
      const open = panel.classList.toggle('ct-hidden') === false;
      trigger.setAttribute('aria-expanded', String(open));
    },
  }, el('span', { class: 'ct-avatar' }, user.initials), el('span', { class: 'ct-small ct-user-menu__name' }, user.full_name));

  document.addEventListener('click', () => {
    panel.classList.add('ct-hidden');
    trigger.setAttribute('aria-expanded', 'false');
  });
  return el('div', { class: 'ct-user-menu' }, trigger, panel);
}

/** Search work from any page (opens the Portfolio filtered by the text). */
function buildSearch() {
  const input = el('input', { class: 'ct-input', type: 'search', placeholder: 'Search work…', 'aria-label': 'Search work' });
  const form = el('form', { class: 'ct-topbar__search', role: 'search', onSubmit: (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (q) window.location.href = `/pages/work.html?q=${encodeURIComponent(q)}`;
  } }, el('span', { class: 'ct-topbar__search-icon' }, icon('search', { size: 16 })), input);
  return form;
}

/** "+ New" on every page: pick a type, fill the form, then go to the new item. */
function buildQuickAdd() {
  return el('button', {
    class: 'ct-btn ct-btn--primary ct-btn--sm', type: 'button',
    onClick: async () => {
      const { openNewWorkItem } = await import('../components/work-item-form.js');
      openNewWorkItem({ onDone: (saved) => { window.location.href = `/pages/item.html?id=${saved.id}`; } });
    },
  }, icon('plus', { size: 16 }), el('span', { class: 'ct-topbar__btn-label' }, 'New'));
}

export async function initLayout({ active, title, permission }) {
  const user = await getCurrentUser();
  if (!user) {
    window.location.href = loginUrl();
    return new Promise(() => {}); // stop the page while redirecting
  }
  document.title = `${title} · Control Tower`;
  // Settings failures should not block the page; labels fall back to their defaults.
  await loadSettings().catch(() => null);

  const content = el('main', { class: 'ct-content', id: 'content' });
  const app = el('div', { class: 'ct-app' });
  const menuBtn = el('button', {
    class: 'ct-btn ct-btn--ghost ct-btn--icon ct-topbar__menu-btn', 'aria-label': 'Open menu',
    onClick: (e) => { e.stopPropagation(); app.classList.toggle('is-nav-open'); },
  }, icon('menu'));

  const topbar = el('header', { class: 'ct-topbar' },
    menuBtn,
    el('div', { class: 'ct-topbar__title' }, title),
    can(user, 'work.view') ? buildSearch() : null,
    can(user, 'work.create') ? buildQuickAdd() : null,
    buildUserMenu(user));

  app.append(buildSidebar(active, user), el('div', { class: 'ct-main' }, topbar, content));
  app.addEventListener('click', (e) => {
    if (app.classList.contains('is-nav-open') && !e.target.closest('.ct-sidebar')) app.classList.remove('is-nav-open');
  });

  document.body.replaceChildren(app);
  if (can(user, 'work.view')) refreshApprovalCount();

  // Page-level guard: the server enforces access anyway; this avoids showing a page the user cannot use.
  if (!can(user, permission)) {
    const { createEmptyState } = await import('../components/empty-state.js');
    content.append(createEmptyState({
      title: 'You do not have access to this page',
      message: 'Ask an administrator if you need it.',
      icon: 'shield',
      action: el('a', { class: 'ct-btn', href: '/pages/home.html' }, 'Go to My Home'),
    }));
    return new Promise(() => {}); // stop the page here
  }
  return { user, content };
}

/** Number of approvals waiting for the user, shown next to "Approvals" in the sidebar. */
export async function refreshApprovalCount() {
  const link = document.querySelector('[data-nav="approvals"]');
  if (!link) return;
  try {
    const { api } = await import('./api.js');
    const { waiting_for_me: n } = await api.get('/approvals/counts');
    link.querySelector('.ct-nav-count')?.remove();
    if (n) link.append(el('span', { class: 'ct-nav-count', title: `${n} waiting for your approval` }, String(n)));
  } catch { /* the count is a convenience; never block the page */ }
}

/** Standard page heading: title, optional subtitle, optional action buttons on the right. */
export function pageHeader(title, subtitle, actions = []) {
  return el('div', { class: 'ct-page-header' },
    el('div', { class: 'ct-page-header__text' },
      el('h1', {}, title),
      subtitle ? el('p', { class: 'ct-muted' }, subtitle) : null),
    actions.length ? el('div', { style: { display: 'flex', gap: '8px' } }, actions) : null);
}
