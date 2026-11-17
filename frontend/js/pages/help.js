/** Help (/pages/help.html): the user manual (the prototype's "User Manual" screen), written for
 *  people using Control Tower day to day. Sections are linked from a contents list. */
import { initLayout, pageHeader } from '../core/layout.js';
import { el } from '../core/utils.js';

const { content } = await initLayout({ active: 'help', title: 'Help' });

const SECTIONS = [
  ['start', 'Getting started', [
    'Sign in with your work email. What you see depends on your role and your place in the organisation: managers see their own unit and everything below it; others see the work they are accountable, responsible or assigned on.',
    'My Home lists what you are accountable and responsible for, your tasks, approvals waiting for you and upcoming deadlines. The Action Centre shows the five things that most need you, and why.',
    'Use the search box at the top to find work by code or title, and “Quick add” to create something from any page.',
  ]],
  ['work', 'Work, ownership and delegation', [
    'Everything is a work item: programmes, projects, milestones, tasks and actions (decisions, blockers, approvals…). Items form a tree; open one to see its details, its work breakdown, people, approvals, tools and full history.',
    'Every item has one accountable owner and one or more responsible owners. Child items inherit the owners of their parent unless you choose others; handing an item over to someone else needs a reason, which is kept in the history.',
    'To delegate, add child items under your item and assign them to a team or person. Assignments record each person\'s role, allocation % and dates; they make up people\'s load.',
  ]],
  ['progress', 'Progress, completion and approval', [
    'Progress is worked out, not typed: an item with children takes the weighted progress of its children, and only work that has been validated counts. Items without children use their own progress %.',
    'When you finish something, use “Mark complete”. If an approval chain applies (by default the functional lead, then the accountable manager), the item waits in Approvals until every step has approved it. Approvers tick the checklist and may send it back with a note.',
  ]],
  ['health', 'Health and the Action Centre', [
    'Each item in delivery is Red, Amber, Grey (information missing) or Green. Hover a health badge to see why; the item page lists every reason and the recommended action. Health rules and their thresholds are settings, changed by administrators under Health rules.',
    'The Action Centre ranks what needs you: red work, ageing blockers, approvals waiting, overdue decisions, milestones due soon but not started, overloaded people and adoption signals. Every number opens the list behind it.',
  ]],
  ['team', 'My team and capacity', [
    'Managers see their unit\'s people with allocated and free capacity (after the buffer), who is overloaded or underused, skills, time off and the next eight weeks. Record time off with “Time off”, and find people by skill.',
    'Demand intake collects requests for new work. “Assess & decide” shows whether the delivering team has the capacity and which lower-priority work could make room; accepting can create the draft initiative straight away.',
  ]],
  ['insights', 'Dashboards, snapshots and presentations', [
    'Dashboards are built from widgets (numbers, tables, charts, progress, timelines) on saved Portfolio filters. A shared dashboard shows every viewer only their own work.',
    'Snapshots store the figures as they were, weekly and on demand. Snapshots & trends shows the trend over time and what has slipped since the baseline.',
    'Presentations put dashboards in order with speaker notes, shown full screen (F for full screen, arrows to move, N for notes). Publish one on an approved snapshot to make a review pack that never changes; export it to PowerPoint, PDF or Excel.',
  ]],
  ['tools', 'Tools', [
    'The Tool Centre lists the tools you may use: links to tools hosted elsewhere, forms that fill in fields of a work item, and readiness checklists. Opening a tool is recorded; forms and checklists save to the item and show in its history.',
  ]],
  ['data', 'Importing and exporting', [
    'Data & Backup (for people with the import permission): download a template, fill it in, upload it and check the preview. Nothing is saved until you choose Import; rows with problems are listed with the reason for each cell. Import people first, then work, then assignments.',
    '“Add only” refuses rows that already exist. “Add and update” changes existing rows with the cells you filled in; empty cells leave values as they are. Work items are matched by their code or by your own External ID, so the same spreadsheet can be imported again.',
    'Every list can be exported: “Export to Excel” on the Portfolio uses the current filters; Data & Backup exports all the work you can see as Excel, CSV or JSON.',
  ]],
  ['notifications', 'Notifications', [
    'The bell in the top bar tells you when you are assigned to work, when ownership of an item is handed to you, when an approval waits for you or yours is decided, when your work turns Red, is due in the next few days or becomes overdue, and when a request you raised is decided. Opening a notification takes you to the work and marks it read.',
    'Choose what you get, in Control Tower and by email, under your name → My account & notifications. Email is sent only if your administrator has set it up.',
  ]],
  ['actions', 'Actions & decisions', [
    'Actions & decisions lists every action item you can see: decisions, approvals to obtain, blockers and commitments, at any level of the work. The tiles count open blockers, pending decisions, overdue and critical actions; choose one to filter the list.',
  ]],
  ['planning', 'What-if scenarios and templates', [
    'What-if scenarios (for managers) let you try changes before making them: move dates, change status, priority or the accountable owner, add someone to work, change their allocation or take them off. The Effect section shows date clashes (dependencies, parent dates, past dates) and everyone\'s load week by week before and after. Nothing changes until you choose Apply; then every change is checked again and made at once, as one entry in the audit log. If anything was changed by someone else in the meantime, the scenario asks you to plan that change again.',
    'Templates are reusable breakdowns. On any item choose “Save as template”; later, “From template” adds the same items under another item, with their dates counted from the start date you choose. Templates are private unless shared by someone allowed to share them.',
  ]],
  ['calendars', 'Working days and holidays', [
    'Each person\'s working days are on their profile (People → Edit). Holidays are set for the whole organisation or for a unit and everything below it. Capacity counts only working days, so a holiday or a shorter week lowers what someone can take on that week, like time off.',
  ]],
  ['schedule', 'Schedule and board', [
    'The Schedule and the Work breakdown of an item show a Gantt chart: bars from planned start to finish with progress inside, milestones as diamonds, a red line for today, and arrows for dependencies (red when something starts before what it depends on finishes). Zoom with Weeks, Months, Quarters or Fit.',
    'On the Portfolio board you can drag a card to another column to change its status; the usual checks apply. While editing a dashboard you can drag widgets to rearrange them.',
  ]],
  ['integrations', 'Outlook, Power BI and other tools', [
    'Outlook: under My account, “Make a calendar address” gives a private address with your deadlines and time off. In Outlook choose Add calendar → Subscribe from web and paste it.',
    'Power BI and scripts: under My account make an API token (it acts as you, with your access). In Power BI use Get data → Web → Advanced, the address /api/v1/reporting/work-items (or assignments, people, units), and the header Authorization = Bearer followed by your token.',
    'Link tools can receive the item they are opened from, for example the project code, so the tool opens on the right project.',
  ]],
  ['admin', 'For administrators', [
    'Lookups and colours, custom fields, terminology, health rules, approval chains and the status flow are settings: change them as a draft, then publish; older versions can be restored from Settings versions. Roles & access decide what each role may do and how far it can see.',
    'Status flow limits where work may go next from each status, per item type; a status left free may change to anything.',
    'Integrations: post alerts to Microsoft Teams channels and send changes to other systems with webhooks, see every email and webhook message sent (and retry failures), revoke anyone\'s API token, and check email and Microsoft sign-in. With Microsoft Entra ID set up, people sign in with their work account; their account is matched by email the first time.',
    'Every change is in the Audit log: who, when, the old and new values, the reason and where it came from (screen, import, API, tool, integration, system).',
    'Backups are taken on the server by the scheduled “flask backup” job and checked automatically; a reminder appears here when the last backup is older than a week. Notifications need two scheduled jobs too: “flask notify --deliver” every minute and “flask notify --checks” once a day.',
  ]],
];

content.append(
  pageHeader('Help', 'How Control Tower works, for people who use it every day.'),
  el('section', { class: 'ct-card' }, el('div', { class: 'ct-card__body ct-help' },
    el('nav', { 'aria-label': 'Contents' }, el('h3', { class: 'ct-section-title', style: { marginTop: 0 } }, 'Contents'),
      el('ul', {}, SECTIONS.map(([id, title]) => el('li', {}, el('a', { href: `#${id}` }, title))))),
    SECTIONS.map(([id, title, paragraphs]) => el('section', { id },
      el('h2', {}, title), paragraphs.map((p) => el('p', {}, p)))))));

if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
